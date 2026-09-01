"""Scenario/Forecast agent — U6. Projects rent and price forward, or says why it can't.

**Two quantities, two sources, and mixing them was the original design.** §1 specified
Tree-of-Thought branching over rent-growth and appreciation paths *"informed by
metro-level housing trend data"* — that is, taking rent growth off Redfin's sale-price
series. Decision #16 split them, on a measured negative correlation between the two.

**Decision #21 kept the split and replaced the reason, along with the rent series.** The
correlation was re-derived at U9.3 (`scripts/growth_correlation.py`) and is a property of
the *rent series* rather than of the market: pooled r = −0.317 measured against the HUD
schedule, −0.197 once HUD's two national step-up years come out, and **+0.222 against
market rent**, with r² never above 0.10 in any pass. Since #19 this system's published
rent estimate is anchored to market rent, so #16's own argument — project forward the
same anchor the estimate was built on — now selects Zillow's ZORI index. Redfin for price,
ZORI for rent through `tools/rent_growth.py`, and the HUD schedule kept there as the
fallback where ZORI has no county deep enough to band. The four defects this closes are
worked through in `docs/design/evaluator.md`.

**What this agent projects from, and why it isn't a value estimate.** Decision #15
leaves `DealState.value_estimate` null — Redfin's extract is pre-aggregated to one
median per metro-period, so it carries no property-level signal, and this repo's demo
asking prices were themselves calibrated to that median, which would have produced
reports where the "estimate" matched the asking price to within $140. §7 left U6 to pick
a projection base, and the choice is the **asking price**: an observed fact about this
property rather than an estimate of it. The claim the report makes is therefore
*"pay this today, and here is what the metro's measured trend implies"* — which needs no
value estimate to be meaningful, and does not pretend to be one.

**The search is over an enumerated space, so no figure here is invented.** Four
framings — two rent treatments × two price treatments, and since #21 both are the same
question (exclude the 2020–2022 window, or keep it) asked of two series — then nine band
pairings under each. `tools/tot.py` explains why enumeration rather than sampling, and what follows
from it: nothing sampled, a data-determined branching factor, and a pipeline that stays
deterministic end to end.

**The pairing level is where the reasoning was designed to happen, and #21 hollowed out
its criterion — stated here rather than in a commit message, because a reader comparing
this docstring to the code should not have to discover it.** Three rent bands and three
price bands give nine combinations. The level existed to avoid the naive diagonal, on the
grounds that rent and price growth move opposite each other; that measurement did not
survive re-derivation, so there is now **no directional prior at all** and the nine
candidates are scored on flags, band widths and sample sizes. That is honest and it is
thin. The redesign — stop asking which pairing is most likely, which needs a joint
distribution this data cannot supply, and ask which projections *this deal's evidence*
supports showing — is adopted and deferred on schedule as OQ-22.

**Two search levels, then deterministic reconciliation** — stated plainly because
`config.TOT_MAX_DEPTH` is 3 and it would be easy to imply three levels of search. Depth
1 scores framings, depth 2 scores pairings, and the third step assigns the
optimistic/base/pessimistic labels by projected outcome and checks that the survivors
are actually distinct. That last step is arithmetic, not search, and inventing a scored
level to fill the number would be the kind of decoration §8 exists to prevent.

**Evidence pulls go through the MCP server's own registry, in-process.** The evaluator
builds its tool menu from `mcp_server.server.list_tools()` — the same names, schemas and
descriptions any external MCP host sees — and dispatches to the same functions, without
the JSON-RPC hop. Decision #13's honest accounting applies: the protocol buys portability
and a second consumer, not capability, and paying a subprocess, an async rewrite and a
tracing gap to make an in-process call look remote would be buying the appearance of
integration. The server remains the definition site and stays runnable for any host.

Reason/Act/Observe/Decide:

- **Reason.** Establish what this deal can actually support: a rent estimate to project,
  an asking price to project, an FMR history deep enough to band, and a Redfin metro.
  Each can fail independently, and each failure is named rather than collapsed.
- **Act.** Enumerate the framings, then the pairings under the survivors, scoring each
  level with the evaluator and pruning against a recorded threshold.
- **Observe.** Check the surviving set against itself — do three branches imply three
  materially different outcomes, or has the search returned one answer three times? A
  near-tie at the top means the selection was arbitrary, and that is reported.
- **Decide.** Emit three scenarios with the treatment each rests on, the fiscal years
  screened out of the rent bands, and a ledger of every hypothesis considered and why
  each was discarded — so a reader can see what the search rejected, not only what it
  chose.
"""

from __future__ import annotations

import asyncio
import json
from functools import lru_cache
from typing import Any, Callable, Optional

import config
import mcp_server
from state import (
    BranchLedgerEntry,
    DealState,
    FlagKind,
    ForecastDetail,
    Scenario,
    Severity,
    flag,
)
from tools import growth_bands, redfin_data, rent_growth, tot
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted

AGENT = "scenario_forecast"

BAND_NAMES = ("pessimistic", "base", "optimistic")


# ---------------------------------------------------------------------------
# Evidence surface: the MCP server's registry, called in-process
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _evidence_surface() -> tuple[str, dict[str, Callable[..., Any]]]:
    """The evaluator's tool menu and dispatch table, read from the MCP server itself.

    `@server.tool()` returns the decorated function unchanged, so `mcp_server.get_fmr`
    is directly callable and is the *same object* an MCP host reaches over stdio. The
    menu text comes from `server.list_tools()`, so the descriptions the evaluator reads
    are the descriptions the server publishes — there is one definition of this tool
    surface, not two that can drift.

    Degrades to an empty menu rather than raising: an evaluator with no evidence tools
    still scores from the bands it was handed, which is worse but not broken.
    """
    try:
        tools = asyncio.run(mcp_server.server.list_tools())
    except (RuntimeError, AttributeError, OSError):
        return "", {}

    lines: list[str] = []
    dispatch: dict[str, Callable[..., Any]] = {}
    for spec in tools:
        function = getattr(mcp_server, spec.name, None)
        if function is None:
            continue
        dispatch[spec.name] = function
        params = ", ".join((spec.input_schema or {}).get("properties", {}))
        headline = (spec.description or "").strip().split("\n")[0]
        lines.append(f"- {spec.name}({params}): {headline}")
    return "\n".join(lines), dispatch


def _pull_evidence(requests: list[dict], detail: ForecastDetail) -> str:
    """Execute the evaluator's chosen tool calls and return their results as text.

    Bounded by `config.TOT_MAX_EVIDENCE_CALLS`. A tool that raises is reported to the
    evaluator as unavailable rather than killing the node — the same Transparent
    Degradation the tools themselves apply to their own returns.
    """
    _, dispatch = _evidence_surface()
    collected: list[str] = []
    for request in requests[: config.TOT_MAX_EVIDENCE_CALLS]:
        name = request.get("tool")
        function = dispatch.get(name)
        if function is None:
            collected.append(f"{name}: no such tool")
            continue
        arguments = request.get("arguments") or {}
        try:
            result = function(**arguments)
        except Exception as exc:  # noqa: BLE001 - a bad tool call must not end the run
            collected.append(f"{name}({arguments}): unavailable ({type(exc).__name__})")
            continue
        detail.evidence_tools_called.append(name)
        collected.append(f"{name}({arguments}) -> {json.dumps(result, default=str)}")
    return "\n".join(collected)


# ---------------------------------------------------------------------------
# The enumerated space
# ---------------------------------------------------------------------------


def _framings(
    rent_bands: dict[bool, rent_growth.RentGrowthBands],
    price_bands: dict[bool, redfin_data.GrowthBands],
) -> list[tot.Candidate]:
    """Every treatment combination the evidence supports. Two by two, or fewer.

    A side with only one usable treatment contributes one option rather than two, which
    is why this enumerates from what was actually computed instead of from a constant.

    **The two axes ask the same question of both series since decision #21**, where they
    used to ask different ones — screen HUD's national step-ups out of rent, or exclude
    the 2020-2022 rate window from price. That was two questions in one fork, and a
    reader had to hold both to read a framing id. Now `f-01` means "keep 2020-2022 in the
    rent bands, hold it out of the price bands", and the diagonal framings are the ones
    that treat the same window the same way on both sides.
    """
    candidates: list[tot.Candidate] = []
    for exclude_rent, rent in sorted(rent_bands.items()):
        for exclude_price, price in sorted(price_bands.items()):
            candidates.append(
                tot.Candidate(
                    id=f"f-{int(exclude_rent)}{int(exclude_price)}",
                    depth=1,
                    payload={
                        "exclude_rent": exclude_rent,
                        "exclude_price": exclude_price,
                        "rent": rent,
                        "price": price,
                    },
                    summary="; ".join(
                        [_rent_note(rent, exclude_rent), _price_note(price, exclude_price)]
                    ),
                )
            )
    return candidates


def _rent_note(rent: Optional[rent_growth.RentGrowthBands], excluded: bool) -> str:
    """One clause describing the rent treatment, safe when the side is unavailable."""
    if rent is None or not rent.available:
        return "rent: no usable rent-growth series"
    window = "2020-2022 excluded" if excluded else "2020-2022 included"
    return (
        f"rent: {window}, base {rent.base_yoy_pct:.2f}%/yr over "
        f"n={rent.n_yoy_observations}"
    )


def _price_note(price: Optional[redfin_data.GrowthBands], excluded: bool) -> str:
    """One clause describing the price treatment, safe when the side is unavailable."""
    if price is None:
        return "price: no sale-price series for this metro"
    window = "2020-2022 excluded" if excluded else "2020-2022 included"
    return (
        f"price: {window}, base {price.base_yoy_pct:.2f}%/yr over "
        f"n={price.n_yoy_observations}"
    )


def _band_value(bands: Any, name: Optional[str]) -> Optional[float]:
    if bands is None or name is None:
        return None
    return getattr(bands, f"{name}_yoy_pct", None)


def _pairings(parents: list[tot.Candidate]) -> list[tot.Candidate]:
    """Nine band pairings under each surviving framing.

    The diagonal is included rather than assumed. It is what a linear chain would emit,
    so excluding it here would rig the comparison the search exists to make.
    """
    candidates: list[tot.Candidate] = []
    for parent in parents:
        rent = parent.payload["rent"]
        price = parent.payload["price"]
        # A side with no series contributes one empty slot rather than three identical
        # ones — otherwise a one-sided forecast would generate nine candidates that are
        # really three, and the ledger would report a search that never happened.
        rent_options = BAND_NAMES if rent is not None and rent.available else (None,)
        price_options = BAND_NAMES if price is not None else (None,)
        for rent_name in rent_options:
            for price_name in price_options:
                rent_rate = _band_value(rent, rent_name)
                price_rate = _band_value(price, price_name)
                candidates.append(
                    tot.Candidate(
                        id=f"{parent.id}-{(rent_name or 'none')[:4]}{(price_name or 'none')[:4]}",
                        parent=parent.id,
                        depth=2,
                        payload={
                            "framing": parent.payload,
                            "rent_band": rent_name,
                            "price_band": price_name,
                            "rent_rate": rent_rate,
                            "price_rate": price_rate,
                        },
                        summary=" paired with ".join(
                            [
                                _side_note("rent", rent_name, rent_rate),
                                _side_note("price", price_name, price_rate),
                            ]
                        ),
                    )
                )
    return candidates


def _side_note(side: str, band_name: Optional[str], rate: Optional[float]) -> str:
    if band_name is None or rate is None:
        return f"no {side} projection"
    return f"{band_name} {side} ({rate:.2f}%/yr)"


def _hard_check(candidate: tot.Candidate) -> Optional[str]:
    """Free, decisive checks that run before any model call.

    Deliberately thin, and worth saying why rather than padding it: the space is
    enumerated from measured bands, so the usual hard constraint — "is this rate
    something the market has ever done?" — is satisfied by construction. Every rate here
    *is* an observed figure. What remains is genuine: a band that could not be computed,
    and a pairing whose two sides are numerically identical to another's.
    """
    payload = candidate.payload
    if candidate.depth == 2:
        if payload["rent_rate"] is None and payload["price_rate"] is None:
            return "Neither side of this pairing produced a usable growth rate."
    return None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

_SELECTION_SYSTEM = (
    "You are evaluating candidate forecast hypotheses for a US multi-family real estate "
    "deal. Before scoring, you may pull evidence from the read-only tools listed. "
    "Choose only tools that would change how you score these specific candidates."
)

_SCORING_SYSTEM = (
    "You score candidate forecast hypotheses from 0.0 to 1.0 on how defensible each is "
    "for this specific deal. You never invent growth rates: every rate you are shown was "
    "measured from a published series, and your job is to judge which combination is "
    "most defensible, not to propose new numbers."
)


def _selection_prompt(candidates: list[tot.Candidate], context: str, menu: str) -> str:
    listing = "\n".join(f"  {c.id}: {c.summary}" for c in candidates)
    return (
        f"{context}\n\nCandidates:\n{listing}\n\nAvailable evidence tools:\n{menu}\n\n"
        f"Request at most {config.TOT_MAX_EVIDENCE_CALLS} tool calls whose results would "
        f"change your scoring. Request none if the information above is sufficient."
    )


# The two levels ask different questions, and conflating them is what emptied the beam
# on a fully-available Los Angeles deal. Depth 1 compares treatments of the data, all of
# which are defensible by construction, so the task is to rank them relative to each
# other. Depth 2 judges whether a specific pairing holds up, where a low score is a real
# verdict.
_DEPTH_INSTRUCTIONS = {
    1: (
        "These are alternative TREATMENTS of the same underlying data, and every one of "
        "them is defensible — they differ in which years feed the bands, not in whether "
        "they are legitimate. Your task is to RANK them relative to each other for this "
        "particular deal, not to judge whether each passes an absolute bar. Use the full "
        "0.0-1.0 range: the treatment you would choose should score near 1.0, and the "
        "least suitable near 0.0. Do not score them all low."
    ),
    2: (
        "These are specific band pairings under the chosen treatment, and the three that "
        "survive become the pessimistic, base and optimistic rows of a five-year "
        "outlook. **You are choosing which projections are worth showing a reader, not "
        "ranking which is most likely to happen.** Those are different questions and "
        "getting them confused empties the table: an extreme band is by construction "
        "less probable than the middle one, so scoring on probability marks down every "
        "hypothesis that is not neutral and leaves the report with a single row and no "
        "range at all. The reader needs the range - that is what the three labels are "
        "for.\n"
        "So score each pairing on whether both of its bands are WELL FOUNDED: how many "
        "observations sit behind them, whether the outer ones rest on a sustained stretch "
        "the market actually held rather than an isolated print, and whether anything "
        "flagged upstream undermines the estimate being compounded. A band drawn from a "
        "real, disclosed extreme of the history is well founded even though it is "
        "unlikely.\n"
        "Two specific errors to avoid, both of which have been made here before. First, "
        "base rent paired with base price is the DEFAULT the other eight depart from, not "
        "a hypothesis that has to justify itself - it needs no evidence of extremity, "
        "since being unextreme is what it is for. Second, a low score is still a real "
        "verdict and a pairing below 0.4 is discarded, so reserve it for a pairing whose "
        "bands are genuinely poorly founded - too few observations, or an extreme that "
        "rests on data this deal's own flags call into question - and not for a pairing "
        "that is merely a strong claim."
    ),
}


def _scoring_prompt(
    depth: int, candidates: list[tot.Candidate], context: str, evidence: str
) -> str:
    listing = "\n".join(f"  {c.id}: {c.summary}" for c in candidates)
    evidence_block = f"\n\nEvidence pulled:\n{evidence}" if evidence else ""
    instruction = _DEPTH_INSTRUCTIONS.get(depth, _DEPTH_INSTRUCTIONS[2])
    return (
        f"{context}\n\nCandidates:\n{listing}{evidence_block}\n\n{instruction}\n\n"
        f"Score each candidate 0.0-1.0 and give a one-sentence rationale that a reader of "
        f"the final report would find useful. Return one entry per candidate id."
    )


def _heuristic_scores(
    candidates: list[tot.Candidate],
) -> list[tuple[float, str]]:
    """Deterministic fallback when the model is unreachable.

    **Scored on band width rather than on direction since #21.** This function used to
    reward pairings that put rent and price at opposite extremes, on a measured negative
    correlation; that correlation did not survive re-derivation (see `_context_block`),
    so the rule it implemented has no evidence behind it and rewarding its opposite would
    have none either. What is left is the one thing a scorer with no model can defend:
    prefer the pairing that claims least. The neutral pairing scores highest, a single
    extreme costs less than two, and both-extremes scores lowest — an ordering that
    follows from how much of the band range a hypothesis is asserting, not from any claim
    about how the two series move together.

    This is a degradation, not a design — but it keeps a forecast available when the
    model is not, and it is reported through the rationale text rather than presented as
    an evaluator judgement.
    """
    rank = {"pessimistic": -1, "base": 0, "optimistic": 1}
    scored: list[tuple[float, str]] = []
    for candidate in candidates:
        if candidate.depth != 2:
            scored.append(
                (
                    0.60,
                    f"{candidate.summary} (scored without model evaluation)",
                )
            )
            continue
        # A side with no series contributes no opinion: rank 0 leaves the divergence
        # term measuring only the side that exists, rather than crashing on a None key.
        rent_rank = rank.get(candidate.payload.get("rent_band"), 0)
        price_rank = rank.get(candidate.payload.get("price_band"), 0)
        # How far from the neutral pairing this hypothesis reaches, counting each side.
        # A side with no series contributes rank 0 and therefore no distance, which
        # leaves a one-sided deal scored on the side it actually has.
        reach = abs(rent_rank) + abs(price_rank)
        score = 0.70 - 0.15 * reach
        scored.append(
            (
                round(min(max(score, 0.0), 1.0), 2),
                f"{candidate.summary} — scored without model evaluation, on how far the "
                f"pairing departs from the neutral case alone.",
            )
        )
    return scored


def _make_scorer(context: str, detail: ForecastDetail) -> tot.Scorer:
    """Build the level scorer: one evidence-selection call, then one scoring call."""
    menu, _ = _evidence_surface()

    def score(depth: int, candidates: list[tot.Candidate]) -> list[tuple[float, str]]:
        from pydantic import BaseModel, Field

        class _ToolRequest(BaseModel):
            tool: str
            arguments: dict = Field(default_factory=dict)

        class _Selection(BaseModel):
            requests: list[_ToolRequest] = Field(default_factory=list)

        class _Score(BaseModel):
            id: str
            score: float
            rationale: str

        class _Scores(BaseModel):
            scores: list[_Score]

        try:
            client = LlmClient()
            evidence = ""
            if menu:
                selection, _ = client.call_with_schema(
                    _selection_prompt(candidates, context, menu),
                    _Selection,
                    model=config.MODEL_SCENARIO,
                    system=_SELECTION_SYSTEM,
                )
                if selection.requests:
                    evidence = _pull_evidence(
                        [r.model_dump() for r in selection.requests], detail
                    )

            result, _ = client.call_with_schema(
                _scoring_prompt(depth, candidates, context, evidence),
                _Scores,
                model=config.MODEL_SCENARIO,
                system=_SCORING_SYSTEM,
            )
        except (LlmError, SchemaValidationExhausted, RuntimeError, OSError):
            return _heuristic_scores(candidates)

        by_id = {s.id: s for s in result.scores}
        out: list[tuple[float, str]] = []
        for candidate, fallback in zip(candidates, _heuristic_scores(candidates)):
            scored = by_id.get(candidate.id)
            if scored is None:
                out.append(fallback)
                continue
            out.append(
                (min(max(scored.score, 0.0), 1.0), scored.rationale or candidate.summary)
            )
        return out

    return score


def _is_neutral_pairing(candidate: tot.Candidate) -> bool:
    """The base-rent / base-price pairing, which the report must always be able to show.

    **The question a reader asks first is "what do you actually expect?", and until #21
    the report frequently had no row that answered it.** Base/base is not privileged
    because it is more likely - the labels come from projected outcome, so it may well
    render as the optimistic row - but because it is the only pairing that asserts nothing
    beyond the two central estimates, and a three-row outlook that cannot include it is
    describing a range with no middle.

    The evaluator's instructions were corrected in the same unit to stop marking the
    neutral case down for *being* neutral, and on a live Los Angeles run that alone lifted
    it from 0.70 to 0.94. **Both changes are kept, because they answer different
    failures**: the instruction fixes the evaluator's reading of its task, and this fixes
    a beam that is a pure top-*k* being asked a question about coverage. A prompt that
    scores well today is not a guarantee, and OQ-17 measures how far this model's scores
    move between identical calls.

    A one-sided deal has no neutral *pairing* - `_pairings` gives the absent side a single
    `None` slot - so this reads both bands rather than assuming two exist.
    """
    payload = candidate.payload
    return (
        candidate.depth == 2
        and payload.get("rent_band") == "base"
        and payload.get("price_band") == "base"
    )


def _conservatism(candidate: tot.Candidate) -> float:
    """Tie-break key: lower is more conservative, so it sorts first.

    Uses the pairing's combined growth assumption, because for an investment tool the
    cost of being wrong is asymmetric — overstating growth is the expensive direction.
    """
    payload = candidate.payload
    if candidate.depth != 2:
        rent = payload.get("rent")
        price = payload.get("price")
        return (getattr(rent, "base_yoy_pct", 0.0) or 0.0) + (
            getattr(price, "base_yoy_pct", 0.0) or 0.0
        )
    return (payload.get("rent_rate") or 0.0) + (payload.get("price_rate") or 0.0)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def _build_bands(
    state: DealState, detail: ForecastDetail
) -> tuple[
    dict[bool, rent_growth.RentGrowthBands], dict[bool, redfin_data.GrowthBands]
]:
    """Compute both treatments of both series, recording why either side is missing."""
    terms = state.deal_terms
    rent_bands: dict[bool, rent_growth.RentGrowthBands] = {}
    price_bands: dict[bool, redfin_data.GrowthBands] = {}

    # --- rent side ---------------------------------------------------------
    if terms.county_fips is None:
        detail.rent_growth_unavailable_reason = (
            "The subject resolved to no county, so there is no local rent index to "
            "difference. Rent growth in this system is the change in the same reference "
            "the rent estimate was multiplied by; without a county there is no reference "
            "and no series."
        )
    else:
        # Both treatments of the *same* fork the price side answers - see `_framings`.
        # A bedroom count is consulted only if this falls through to the published
        # schedule, so a listing that never resolved one still gets a rent projection
        # where it previously got none; `tools/rent_growth.py` handles that ordering.
        for exclude in (False, True):
            bands = rent_growth.get_rent_growth_bands(
                terms.county_fips,
                int(terms.bedrooms) if terms.bedrooms is not None else None,
                exclude_anomalous_period=exclude,
            )
            if bands.available:
                rent_bands[exclude] = bands
                # Recorded here rather than waiting for `_record_band_provenance`, which
                # runs after the search: the evaluator's context block names the series
                # it is scoring, and it is built before the first candidate exists. Both
                # treatments read the same series, so either one answers.
                detail.rent_growth_source = bands.source
                detail.rent_growth_source_description = bands.source_description
            elif detail.rent_growth_unavailable_reason is None:
                detail.rent_growth_unavailable_reason = bands.unavailable_reason

    # --- price side --------------------------------------------------------
    metro = (state.valuation_detail.benchmark_metro if state.valuation_detail else None)
    if metro is None:
        detail.price_growth_unavailable_reason = (
            (state.valuation_detail.benchmark_unavailable_reason if state.valuation_detail else None)
            or "No Redfin metro was resolved for this subject, so there is no "
               "multi-family sale-price series to project from."
        )
    else:
        try:
            appreciation = redfin_data.get_appreciation_series(
                redfin_data.load_redfin(), metro=metro
            )
            for exclude in (False, True):
                price_bands[exclude] = redfin_data.compute_growth_bands(
                    appreciation, exclude_anomalous_period=exclude
                )
        except (KeyError, ValueError, FileNotFoundError, OSError) as exc:
            detail.price_growth_unavailable_reason = (
                f"The Redfin appreciation series for {metro} could not be built "
                f"({type(exc).__name__}), so no price projection was produced."
            )

    return rent_bands, price_bands


def _record_band_provenance(
    detail: ForecastDetail,
    rent: Optional[rent_growth.RentGrowthBands],
    price: Optional[redfin_data.GrowthBands],
) -> None:
    """Copy the chosen framing's provenance onto the detail object for the report."""
    if rent is not None:
        detail.rent_growth_source = rent.source
        detail.rent_growth_source_description = rent.source_description
        detail.rent_growth_area_name = rent.area_name
        detail.rent_growth_resolution = rent.resolution
        detail.rent_growth_n_observations = rent.n_yoy_observations
        detail.rent_growth_first_observation = rent.first_observation
        detail.rent_growth_last_observation = rent.last_observation
        detail.rent_growth_pessimistic_pct = rent.pessimistic_yoy_pct
        detail.rent_growth_base_pct = rent.base_yoy_pct
        detail.rent_growth_optimistic_pct = rent.optimistic_yoy_pct
        detail.rent_growth_zips_in_county = rent.zips_in_county
        detail.rent_anomalous_period_excluded = rent.anomalous_period_excluded
        detail.rent_anomalous_period_share = rent.anomalous_period_share
        detail.rent_growth_bedrooms = rent.bedrooms
        detail.rent_growth_pessimistic_year = rent.pessimistic_year
        detail.rent_growth_optimistic_year = rent.optimistic_year
    if price is not None:
        detail.price_growth_metro = price.metro
        detail.price_growth_n_observations = price.n_yoy_observations
        detail.price_growth_pessimistic_pct = price.pessimistic_yoy_pct
        detail.price_growth_base_pct = price.base_yoy_pct
        detail.price_growth_optimistic_pct = price.optimistic_yoy_pct
        detail.anomalous_period_excluded = price.anomalous_period_excluded
        detail.anomalous_period_share = price.anomalous_period_share
        detail.optimistic_stretch_in_anomalous_period = (
            price.optimistic_stretch_in_anomalous_period
        )


def _to_scenarios(
    survivors: list[tot.Candidate],
    base_rent: Optional[float],
    base_price: Optional[float],
    horizon: int,
) -> list[Scenario]:
    """Project each survivor and label the set by outcome — the reconciliation step.

    Labels are assigned here rather than chosen by the evaluator: a scenario's name has
    to describe its outcome, or a reader comparing three rows cannot trust the column.

    **Ordering is by the sum of the two growth multiples, and that is a stated convention
    rather than a return model.** Ranking on rent alone produced exactly the incoherence
    this step exists to prevent - a first Chicago run labelled a path "pessimistic" while
    it projected a price of $1.29M against the "optimistic" path's $390K, because the two
    shared a rent band and the price column was never consulted. Weighting the two sides
    equally is a choice; a real total-return model would weight them by holding period,
    leverage and exit assumption, none of which this system has. What matters is that the
    label follows both quantities and that the reader is told how.
    """
    projected: list[tuple[float, Scenario]] = []
    for candidate in survivors:
        payload = candidate.payload
        rent_rate = payload.get("rent_rate")
        price_rate = payload.get("price_rate")
        scenario = Scenario(
            name="",
            rent_band=payload.get("rent_band"),
            price_band=payload.get("price_band"),
            rent_growth_pct_per_year=rent_rate,
            price_growth_pct_per_year=price_rate,
            projected_monthly_rent=(
                base_rent * (1 + rent_rate / 100.0) ** horizon
                if base_rent is not None and rent_rate is not None
                else None
            ),
            projected_price=(
                base_price * (1 + price_rate / 100.0) ** horizon
                if base_price is not None and price_rate is not None
                else None
            ),
            rationale=candidate.summary,
            evaluator_score=candidate.score,
        )
        projected.append((_outcome_rank(scenario, base_rent, base_price), scenario))

    projected.sort(key=lambda pair: pair[0])
    names = _labels_for(len(projected))
    for name, (_, scenario) in zip(names, projected):
        scenario.name = name
    return [scenario for _, scenario in projected]


def _outcome_rank(
    scenario: Scenario, base_rent: Optional[float], base_price: Optional[float]
) -> float:
    """Sum of the growth multiples on the sides that were actually projected.

    Unit-free, so a rent in dollars per month and a price in dollars do not have to be
    made commensurable. A side with no projection contributes 1.0 - no change - which
    leaves the ordering driven by whichever side exists.
    """
    total = 0.0
    for projected, base in (
        (scenario.projected_monthly_rent, base_rent),
        (scenario.projected_price, base_price),
    ):
        total += projected / base if projected is not None and base else 1.0
    return total


def _labels_for(count: int) -> list[str]:
    """Names for however many branches survived.

    Fewer than three survivors is a real outcome — pruning is allowed to leave two — and
    labelling two branches "pessimistic" and "optimistic" with no base case says more
    than padding the set would.
    """
    if count >= 3:
        return ["pessimistic"] + ["base"] * (count - 2) + ["optimistic"]
    if count == 2:
        return ["pessimistic", "optimistic"]
    return ["base"]


def scenario_forecast_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    terms = state.deal_terms
    horizon = config.FORECAST_HORIZON_YEARS
    detail = ForecastDetail(
        horizon_years=horizon,
        projection_base_price=terms.price,
        projection_base_source="asking price" if terms.price is not None else None,
        projection_base_rent=state.rent_estimate,
    )
    flags: list = []

    rent_bands, price_bands = _build_bands(state, detail)

    if not rent_bands and not price_bands:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FORECAST_UNAVAILABLE,
                "No forecast was produced: neither a rent-growth series nor a "
                f"sale-price series was available. Rent side — "
                f"{detail.rent_growth_unavailable_reason} Price side — "
                f"{detail.price_growth_unavailable_reason}",
                Severity.CRITICAL,
            )
        )
        return {"forecast_detail": detail, "flags": flags}

    if not rent_bands or not price_bands:
        missing, reason = (
            ("rent growth", detail.rent_growth_unavailable_reason)
            if not rent_bands
            else ("price appreciation", detail.price_growth_unavailable_reason)
        )
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FORECAST_UNAVAILABLE,
                f"The forecast covers only one side of this deal: no {missing} "
                f"projection was produced. {reason} The scenarios below are real for "
                f"the side that was available and silent on the other.",
                Severity.WARN,
            )
        )

    # A missing side still has to contribute exactly one option, or the product that
    # enumerates the framings collapses to nothing and a one-sided forecast — which is a
    # real, reportable outcome — would look identical to a total failure.
    if not rent_bands:
        rent_bands = {False: None}
    if not price_bands:
        price_bands = {False: None}

    context = _context_block(state, detail, horizon)

    def expand(depth: int, parents: list[tot.Candidate]) -> list[tot.Candidate]:
        if depth == 1:
            return _framings(rent_bands, price_bands)
        if depth == 2:
            return _pairings(parents)
        # Depth 3 is reconciliation, which is arithmetic rather than search — see the
        # module docstring. Returning nothing ends the beam cleanly.
        return []

    result = tot.beam_search(
        expand=expand,
        hard_check=_hard_check,
        score=_make_scorer(context, detail),
        beam_width={
            1: config.TOT_FRAMING_BEAM_WIDTH,
            2: config.TOT_BEAM_WIDTH,
        },
        prune_threshold={
            1: config.TOT_FRAMING_PRUNE_THRESHOLD,
            2: config.TOT_PRUNE_THRESHOLD,
        },
        conservatism_key=_conservatism,
        reserved=_is_neutral_pairing,
    )

    detail.framings_considered = sum(1 for c in result.ledger if c.depth == 1)
    detail.branches_generated = len(result.ledger)
    detail.branches_pruned = result.n_pruned
    detail.top_two_score_gap = result.top_two_score_gap

    ledger = [
        BranchLedgerEntry(
            id=c.id,
            parent=c.parent,
            depth=c.depth,
            agent=AGENT,
            summary=c.summary,
            score=c.score,
            prune_reason=c.prune_reason,
        )
        for c in result.ledger
    ]

    if not result.survivors:
        detail.search_exhausted_reason = result.exhausted_reason
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FORECAST_UNAVAILABLE,
                f"The scenario search ended with no surviving hypothesis. "
                f"{result.exhausted_reason} Every candidate considered is listed in the "
                f"branch ledger with the reason it was discarded.",
                Severity.CRITICAL,
            )
        )
        return {"forecast_detail": detail, "branch_ledger": ledger, "flags": flags}

    chosen = result.survivors[0].payload.get("framing") or result.survivors[0].payload
    _record_band_provenance(detail, chosen.get("rent"), chosen.get("price"))

    scenarios = _to_scenarios(
        result.survivors, state.rent_estimate, terms.price, horizon
    )

    flags.extend(
        _disclosure_flags(detail, result, chosen, scenarios, state.planner_invocations)
    )

    return {
        "scenarios": scenarios,
        "forecast_detail": detail,
        "appreciation_source": (
            redfin_data.SERIES_DESCRIPTION if chosen.get("price") is not None else None
        ),
        "branch_ledger": ledger,
        "flags": flags,
    }


def _context_block(state: DealState, detail: ForecastDetail, horizon: int) -> str:
    """What the evaluator is told about the deal before it scores anything."""
    terms = state.deal_terms
    raised = ", ".join(sorted({f.kind.value for f in state.flags})) or "none"
    return (
        f"Deal: {terms.full_address or 'unidentified property'}, "
        f"{terms.unit_count or '?'} units, {terms.bedrooms or '?'} bed / "
        f"{terms.bathrooms or '?'} bath, {terms.square_footage or '?'} sqft.\n"
        f"Asking price: {terms.price if terms.price is not None else 'not stated'}. "
        f"Modelled monthly rent: {state.rent_estimate if state.rent_estimate is not None else 'not produced'}.\n"
        f"Forecast horizon: {horizon} years.\n"
        f"Flags already raised upstream: {raised}.\n\n"
        f"{_availability_note(detail)}\n\n"
        f"Measured context you must respect: this project has measured the "
        f"relationship between rent growth and sale-price growth and found it WEAK and "
        f"UNSTABLE. Pooled across its markets it is r = -0.317 against the federal rent "
        f"schedule, -0.197 once two nationwide administrative increases are removed, and "
        f"+0.222 against market rent - which is the series the bands below are built "
        f"from. It changes sign by market: positive in Cleveland and Los Angeles, "
        f"negative in Chicago, on the same measurement. r-squared never exceeds 0.10 in "
        f"any of those passes.\n"
        f"THEREFORE: no directional rule about pairings is supported. Do NOT prefer "
        f"pairings that put rent and price at opposite extremes, and do NOT prefer the "
        f"diagonal either. An earlier version of these instructions asserted a negative "
        f"relationship as fact; it was wrong, and a pairing must now earn its score from "
        f"this deal's own evidence - the flags raised upstream, how wide each band is, "
        f"how many observations sit behind it, and how much of the estimate being "
        f"compounded is corroborated. In particular, a weak relationship is not an "
        f"argument against pairings whose two sides move in opposite directions; it is "
        f"equally an argument against pairings whose sides move together. It removes the "
        f"question from consideration rather than answering it.\n"
        f"About the 2020-2022 window, which is what the treatment choice above turns on: "
        f"near-zero policy rates through that stretch pulled sale-price growth well above "
        f"trend, and this project requires the window be disclosed wherever it feeds an "
        f"average. Including it treats those conditions as something that could recur; "
        f"excluding it treats them as a one-off, at the cost of sample size. Both are "
        f"defensible readings of the same history and the choice is yours to argue - but "
        f"argue it about the history, not about whether the two series were treated "
        f"alike. Rent bands come from "
        f"{detail.rent_growth_source_description or 'a local rent index'} and price bands "
        f"from Redfin metro multi-family sales; both are monthly market series, banded "
        f"over the same span by the same estimator."
    )


def _availability_note(detail: ForecastDetail) -> str:
    """Tell the evaluator which sides exist, so it does not penalise an absence.

    **Added after a Staten Island run returned no forecast at all.** Redfin's extract
    does not reach that metro, so every candidate carried a rent band and no price band;
    the evaluator, told only that rent and price growth are negatively correlated — a
    claim #21 has since retired — scored each of them below the prune threshold and the
    beam emptied. The deal had a perfectly
    good rent forecast and the report said nothing — which is the degradation failure
    this project exists to prevent, produced by a prompt that described a two-sided
    problem to a one-sided deal.
    """
    if detail.rent_growth_unavailable_reason and not detail.price_growth_unavailable_reason:
        return (
            "IMPORTANT: this deal has NO rent-growth series — "
            f"{detail.rent_growth_unavailable_reason} Candidates therefore carry a price "
            "band only. Judge each on whether that price treatment is defensible for this "
            "deal. Do not penalise a candidate for the missing rent side; it is a gap in "
            "the data, not a weakness of the hypothesis."
        )
    if detail.price_growth_unavailable_reason and not detail.rent_growth_unavailable_reason:
        return (
            "IMPORTANT: this deal has NO price-appreciation series — "
            f"{detail.price_growth_unavailable_reason} Candidates therefore carry a rent "
            "band only. Judge each on "
            "whether that rent treatment is defensible for this deal. Do not penalise a "
            "candidate for the missing price side; it is a gap in the data, not a "
            "weakness of the hypothesis."
        )
    return "Both a rent-growth series and a price-appreciation series are available."


def _disclosure_flags(
    detail: ForecastDetail,
    result: tot.SearchResult,
    chosen: dict,
    scenarios: list[Scenario],
    planner_invocations: int,
) -> list:
    """Every flag that describes how the surviving forecast was reached."""
    flags: list = []
    price = chosen.get("price")
    rent = chosen.get("rent")

    if price is not None:
        flags.append(
            flag(
                AGENT,
                FlagKind.APPRECIATION_SOURCE,
                f"Price appreciation is projected from {redfin_data.SERIES_DESCRIPTION} "
                f"for the {price.metro} metro, over {price.n_yoy_observations} "
                f"year-over-year observations. This project has one appreciation series: "
                f"the ZIP-level tier was closed on sample size (median 2 sales per "
                f"ZIP-period) and no all-residential extract exists here, so there is no "
                f"fallback below this one.",
                Severity.INFO,
                planner_invocations,
            )
        )
        if price.includes_anomalous_period:
            flags.append(
                flag(
                    AGENT,
                    FlagKind.ANOMALOUS_PERIOD_INCLUDED,
                    f"The price bands include the 2020-2022 window, which is "
                    f"{price.anomalous_period_share:.0%} of the observations. Near-zero "
                    f"rates pulled price growth well above trend in that stretch"
                    + (
                        ", and the optimistic band rests on it."
                        if price.optimistic_stretch_in_anomalous_period
                        else "."
                    ),
                    Severity.INFO,
                    planner_invocations,
                )
            )

    if rent is not None and rent.available:
        where = (
            f" at {rent.area_name}" if rent.area_name else ""
        )
        span = (
            f" over {rent.n_yoy_observations} year-over-year observations from "
            f"{rent.first_observation} to {rent.last_observation}"
            if rent.first_observation and rent.last_observation
            else ""
        )
        if rent.source == rent_growth.SOURCE_ZORI:
            breadth = (
                f", a median across the {rent.zips_in_county} postal codes it covers"
                if rent.zips_in_county
                else ""
            )
            basis = (
                f"Rent growth is projected from {rent.source_description}{where}"
                f"{breadth}{span}. Note the difference in geography from the rent "
                f"estimate itself, which is anchored at this property's own postal code: "
                f"a single postal code's rent index either does not reach back far enough "
                f"to measure a five-year trend or does not exist at all, so the trend is "
                f"measured across the surrounding county and the estimate is not."
            )
        else:
            basis = (
                f"No market rent index reaches this county with enough history to measure "
                f"a trend, so rent growth is projected from {rent.source_description}"
                f"{where}{span}. This is a published schedule rather than observed market "
                f"rents, and it is revised once a year — so its best and worst cases are "
                f"single years rather than the twelve-month stretches the sale-price bands "
                f"below use, and its range will read wider for that reason alone."
            )
        flags.append(
            flag(
                AGENT,
                FlagKind.RENT_GROWTH_SOURCE,
                basis,
                Severity.INFO,
                planner_invocations,
            )
        )

    # Two near-ties are possible and they mean different things, so they are reported
    # separately rather than collapsed into one score gap — and since U8.6c they carry
    # different severities, because the two ties have different stakes:
    #
    # - A *framing* tie (depth 1) is WARN. `TOT_FRAMING_BEAM_WIDTH` is 1, so the losing
    #   framing — a whole reading of the data — is discarded on the conservatism
    #   tie-break, and the basis of every number in the forecast was chosen by policy
    #   rather than by evidence. That is real doubt about the forecast.
    # - A *pairing* tie (depth 2) is INFO. `TOT_BEAM_WIDTH` is 3, so both tied pairings
    #   survive into the reported scenario set; labels are assigned by projected outcome
    #   (never by score rank) and band provenance comes from the framing every pairing
    #   shares — so nothing a reader sees hinges on which pairing nominally led. Charging
    #   0.15 of confidence for a distinction that does not survive to the report was
    #   pricing the hypothesis space's symmetry as deal doubt: mirror pairings
    #   (rent-up/price-down against rent-down/price-up) are genuinely equally defensible,
    #   and the evaluator scoring them identically is the scoring working, not a
    #   degradation. **That argument was made under the negative correlation #21 retired
    #   and survives its retirement intact** — indeed more cleanly, since with no
    #   directional prior at all there is nothing left that could have separated the two.
    #
    # - A *cut-boundary* tie at depth 2 is INFO, and it is the one U8.6c added because
    #   nothing measured it. The pairing tie above compares #1 against #2, which the
    #   demotion argument shows is inert: both survive. The line between #3 and #4 is
    #   where the beam width bites, so it decides which pairings are reported at all —
    #   the one rank comparison at this depth that does reach the reader. It is INFO
    #   rather than WARN for two reasons: the discarded pairing is already published in
    #   the branch ledger with its own score and the reason it was dropped, so this
    #   disclosure names a margin the reader can already see rather than revealing a
    #   hidden loss; and the gap is measured with the same instrument whose single-draw
    #   noise (OQ-17) exceeds `TOT_TIE_EPSILON` by an order of magnitude, which is
    #   exactly the argument that demoted the pairing tie. **Recorded as a judgment
    #   rather than a fact** — the framing tie is WARN on the reasoning that a discarded
    #   candidate is a real loss, and that reasoning transfers here in weakened form. It
    #   is a one-word change if the architect prices it differently.
    #
    # All three messages state the one-sample caveat OQ-17 measured: a live scoring call is
    # not perfectly deterministic even at temperature 0 (OpenRouter routes across
    # non-identical backend deployments, and even one pinned deployment's scores swing
    # call to call — see docs/design/architecture.md §3), so a near-tie can be a property
    # of this one draw rather than a stable judgment. The structural response — scoring
    # k times and disclosing disagreement — remains OQ-17's open question, not this
    # flag's job.
    framing_gap = result.score_gap_by_depth.get(1)
    if framing_gap is not None and framing_gap < config.TOT_TIE_EPSILON:
        flags.append(
            flag(
                AGENT,
                FlagKind.FORECAST_BRANCHES_NEAR_TIED,
                f"The two best *framings* scored within {framing_gap:.3f} of each other, "
                f"inside the {config.TOT_TIE_EPSILON} tie threshold. A framing decides "
                f"which years feed every band, so this means the whole forecast rests on "
                f"a reading the evaluator could not separate from its alternative, "
                f"resolved by a fixed preference for the more conservative one. The "
                f"branch ledger lists the framing that lost and what it would have "
                f"implied. One caution in reading this: the scores come from a single "
                f"model call whose repeat runs measurably vary, so a gap this small can "
                f"also be a property of this one sample rather than a stable judgment "
                f"about the evidence.",
                Severity.WARN,
                planner_invocations,
            )
        )

    pairing_gap = result.score_gap_by_depth.get(2)
    if pairing_gap is not None and pairing_gap < config.TOT_TIE_EPSILON:
        flags.append(
            flag(
                AGENT,
                FlagKind.FORECAST_BRANCHES_NEAR_TIED,
                f"The two best-scoring scenario pairings were separated by "
                f"{pairing_gap:.3f}, inside the {config.TOT_TIE_EPSILON} tie threshold — "
                f"the evaluator found both equally defensible. Both appear in the "
                f"scenario table below, and each scenario's label comes from its "
                f"projected outcome, so no reported figure depends on which of the two "
                f"nominally ranked first. A tie here is common and often correct: two "
                f"pairings that mirror each other make equally strong claims about a "
                f"relationship between rent and price growth that this project has "
                f"measured and found weak. The scores also come from a single model call whose "
                f"repeat runs measurably vary, so a gap this small can be a property of "
                f"this one sample.",
                Severity.INFO,
                planner_invocations,
            )
        )

    cut_gap = result.cut_boundary_gap_by_depth.get(2)
    if cut_gap is not None and cut_gap < config.TOT_TIE_EPSILON:
        # Two different sentences, because a non-positive margin is the stronger finding
        # and describing it as "separated by 0.05, inside the 0.05 threshold" would be
        # both self-contradictory and a weaker claim than the truth. `tot._rank` groups
        # candidates within `TOT_TIE_EPSILON` and sorts that group by conservatism, so a
        # margin at or below zero means the tie-break, not the evaluator, chose which
        # pairing was reported.
        if cut_gap > 0:
            margin = (
                f"were separated by {cut_gap:.3f}, inside the "
                f"{config.TOT_TIE_EPSILON} threshold this system treats as no meaningful "
                f"difference"
            )
        else:
            margin = (
                f"were not separated on score at all — the pairing left out scored "
                f"{abs(cut_gap):.3f} *above* the one kept, and the order was settled by "
                f"this system's standing preference for the more conservative reading, "
                f"which applies wherever two scores sit within "
                f"{config.TOT_TIE_EPSILON} of each other"
            )
        flags.append(
            flag(
                AGENT,
                FlagKind.FORECAST_BRANCHES_NEAR_TIED,
                f"The last scenario pairing to make the table and the best one left out "
                f"of it {margin}. This line matters in a way a tie between two reported "
                f"scenarios does not: it decides which pairings are shown at all, so the "
                f"set of scenarios below could as defensibly have been a different set. "
                f"The pairing that missed it is listed in the search ledger with its own "
                f"score and the reason it was dropped. As with every score here, it comes "
                f"from a single model call whose repeat runs measurably vary.",
                Severity.INFO,
                planner_invocations,
            )
        )

    flags.extend(_distinctness_flags(scenarios, planner_invocations))
    return flags


def _distinctness_flags(scenarios: list[Scenario], planner_invocations: int) -> list:
    """Report when the search returned fewer distinct answers than it has labels for.

    The reconciliation step promises three scenarios that bracket an outcome range. When
    two of them land within `config.TOT_SCENARIO_DISTINCTNESS_PCT` of each other, the
    labels imply a spread the numbers do not contain, and a reader comparing rows would
    take the difference for signal.
    """
    collisions: list[str] = []
    for i, first in enumerate(scenarios):
        for second in scenarios[i + 1 :]:
            if _outcomes_match(first, second):
                collisions.append(f"{first.name} and {second.name}")
    if not collisions:
        return []
    return [
        flag(
            AGENT,
            FlagKind.FORECAST_BRANCHES_NEAR_TIED,
            f"The surviving scenarios are not fully distinct: {', '.join(collisions)} "
            f"project outcomes within {config.TOT_SCENARIO_DISTINCTNESS_PCT:.0f}% of each "
            f"other. The labels imply a spread these figures do not contain, which "
            f"usually means the underlying bands are close together rather than that the "
            f"search failed.",
            Severity.INFO,
            planner_invocations,
        )
    ]


def _outcomes_match(first: Scenario, second: Scenario) -> bool:
    """True when two scenarios project effectively the same outcome on every side that
    both of them produced."""
    compared = False
    for attribute in ("projected_monthly_rent", "projected_price"):
        left = getattr(first, attribute)
        right = getattr(second, attribute)
        if left is None or right is None or not left:
            continue
        compared = True
        if abs(left - right) / abs(left) * 100.0 > config.TOT_SCENARIO_DISTINCTNESS_PCT:
            return False
    return compared
