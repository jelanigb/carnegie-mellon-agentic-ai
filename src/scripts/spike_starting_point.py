"""What would OQ-22's re-purposed depth 2 actually produce? (U9 spike, Sept 2 2026)

    .venv/bin/python scripts/spike_starting_point.py --tier 0
    .venv/bin/python scripts/spike_starting_point.py --tier 1 --shape framing
    .venv/bin/python scripts/spike_starting_point.py --tier 2 --runs 8

**What this is for.** OQ-22 defers a redesign of the forecast's depth-2 level: stop asking
*which band pairing is most likely* - which needs a joint rent/price distribution this
project's data cannot supply - and ask instead *which projections does this deal's evidence
support showing, and how wide should the starting point be?* The entry sizes that as "a full
change set of new design" and defers it past the freeze.

This script exists so the design can be **read before it is built**, without touching
`agents/scenario_forecast.py`, `agents/summarizer.py`, `tools/tot.py` or `state.py`. It
imports the shipped enumerators and the shipped scorer, substitutes its own context block and
its own candidate payloads, and prints what the report *would* have said. Nothing here is
wired into the pipeline and nothing it writes is read by anything else.

**Three tiers, answering three different questions.**

  * **Tier 0 - arithmetic, no model call.** How wide is the starting-point treatment against
    the growth bands it would sit beside? If the estimate's error band dominates the growth
    bands, the re-purposed table stops being a growth forecast and becomes an
    estimate-uncertainty display, which is a design question that no amount of prompt work
    answers.
  * **Tier 1 - one live search per deal.** Can the evaluator answer the new question at all,
    or does it produce mush? Prints today's rows beside the re-purposed rows.
  * **Tier 2 - the same search N times.** OQ-17 says repeat calls on this model move
    materially. The starting-point treatment swings the projected rent by roughly 2x, so a
    treatment that is unstable across identical calls is worse than not having one. **This is
    the tier that can kill the design**, and it is the reason the other two are not enough.

**Two shapes, because OQ-22's literal reading is not obviously the right one.**

  * `--shape pairing` is OQ-22 as written: the starting-point treatment joins
    `(rent_band, price_band)` in the depth-2 payload, giving 9 x 3 = 27 candidates.
  * `--shape framing` puts it at depth 1 instead, giving 4 x 3 = 12 framings and one
    surviving treatment for the whole forecast. The argument for it is that "how far do we
    trust the estimate we are compounding?" is a property of the *deal*, identical across all
    nine pairings - so asking it nine times at depth 2 asks one question nine times, triples
    the level's prompt, and spreads one answer across candidates that can disagree with each
    other. Depth 1 is also the level measured clean: across the committed recordings the
    framing was decided on the model's own scores 78 times out of 78, where depth 2's cut
    falls inside a conservatism tie-break on 51% of levels.

**Isolation, because another session is working in this tree.** Every live call is made with
`LLM_CACHE_DIR` pointed at a scratchpad directory, so nothing this script does can land a
recording in `eval/data/llm_recordings/`. Tier 2 additionally runs with `LLM_CACHE_MODE=off`,
because a cache keyed on the prompt would serve the same response N times and measure
nothing. Writes only to `--out`, which defaults to a scratchpad path.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents import scenario_forecast as sf
from state import DealState, ForecastDetail, ValuationDetail
from tools import tot

# --------------------------------------------------------------------------
# The starting-point treatments this spike enumerates
# --------------------------------------------------------------------------
# A width multiplier on the rent model's own holdout error, which is the only measured
# statement this project has about how far the compounded estimate might be off. 0.0 is
# today's behavior in every case - the point estimate, compounded as though exact.
#
# Three rather than two because the interesting deals are not at the extremes: `los-angeles`
# has eight comps agreeing within 1% and `staten-island` has none at all, but a deal with
# three comps at 12% divergence is the case a two-way choice cannot express.
STARTING_POINTS: tuple[tuple[str, float, str], ...] = (
    ("point", 0.0, "project from the point estimate, as though it were exact"),
    ("half", 0.5, "project from the estimate +/- half its measured error"),
    ("full", 1.0, "project from the estimate +/- its full measured error"),
)


@dataclass
class Evidence:
    """What the deal's own run measured about the estimate the forecast compounds.

    Every field here is already on `ValuationDetail` and **none of it reaches the forecast
    evaluator today** - `_context_block` passes flag *names* and the point estimate. That is
    the gap this spike is really testing, and it is smaller than OQ-22 assumed.
    """

    deal: str
    rent_estimate: Optional[float]
    mae_overall: Optional[float]
    mae_metro: Optional[float]
    metro: Optional[str]
    comps_available: int
    comps_cross_checked: int
    comps_zip_anchored: int
    comp_implied_median: Optional[float]
    divergence_pct: Optional[float]
    anchor_tier: Optional[str]
    anchor_zip: Optional[str]
    flags: tuple[str, ...]

    @property
    def error(self) -> Optional[float]:
        """The metro-specific error where one exists, else the overall figure.

        The metro figure is the honest one for a starting-point decision: it is what the
        model missed by in *this* market, and `staten-island`'s $855 against a $452 pooled
        average is the whole reason the treatment would differ by deal.
        """
        return self.mae_metro if self.mae_metro is not None else self.mae_overall

    def error_share(self) -> Optional[float]:
        if self.error is None or not self.rent_estimate:
            return None
        return self.error / self.rent_estimate


# The nodes that run at or before `scenario_forecast` (see `graph.py`'s edges). A flag
# raised by the Critic or the Summarizer is downstream of the forecast and was NOT in the
# evaluator's prompt when the shipped run scored its candidates, so including it here would
# hand the spike evidence the real node never had and quietly overstate the design.
UPSTREAM_AGENTS = ("planner", "extractor", "comps_retrieval", "valuation_rent")


def _upstream_flags(state: DealState) -> tuple[str, ...]:
    return tuple(sorted({
        f.kind.value for f in state.flags
        if getattr(f, "agent", None) in UPSTREAM_AGENTS
    }))


def _load_evidence(state: DealState, deal: str) -> Evidence:
    detail: Optional[ValuationDetail] = state.valuation_detail
    return Evidence(
        deal=deal,
        rent_estimate=state.rent_estimate,
        mae_overall=getattr(detail, "model_mae_dollars", None),
        mae_metro=getattr(detail, "subject_metro_mae_dollars", None),
        metro=getattr(detail, "subject_metro", None),
        comps_available=getattr(detail, "comps_available", 0) or 0,
        comps_cross_checked=getattr(detail, "comps_cross_checked", 0) or 0,
        comps_zip_anchored=getattr(detail, "comps_zip_anchored", 0) or 0,
        comp_implied_median=getattr(detail, "comp_implied_rent_median", None),
        divergence_pct=getattr(detail, "divergence_pct", None),
        anchor_tier=getattr(detail, "anchor_tier", None),
        anchor_zip=getattr(detail, "anchor_zip", None),
        flags=_upstream_flags(state),
    )


# --------------------------------------------------------------------------
# Tier 0 - arithmetic
# --------------------------------------------------------------------------


def _compound(base: float, pct: float, years: int) -> float:
    return base * (1 + pct / 100.0) ** years


def tier0(evidence: Evidence, bands: tuple[float, float, float], horizon: int) -> dict:
    """How wide is the starting-point treatment against the growth bands beside it?

    Reports the two spreads separately and their ratio. A ratio above 1 means the section
    would be dominated by what the system does not know about *today's* rent rather than by
    what the market did to rents over five years - which is defensible, and is a different
    section from the one the report has now.
    """
    pess, base, opti = bands
    rent = evidence.rent_estimate
    err = evidence.error
    if rent is None or err is None:
        return {"deal": evidence.deal, "unavailable": True}

    band_lo = _compound(rent, pess, horizon)
    band_hi = _compound(rent, opti, horizon)
    start_lo = _compound(rent - err, base, horizon)
    start_hi = _compound(rent + err, base, horizon)
    both_lo = _compound(rent - err, pess, horizon)
    both_hi = _compound(rent + err, opti, horizon)

    band_width = band_hi - band_lo
    start_width = start_hi - start_lo
    return {
        "deal": evidence.deal,
        "rent_estimate": rent,
        "error": err,
        "error_share_pct": 100.0 * err / rent,
        "bands_pct": bands,
        "growth_only": (band_lo, band_hi, band_width),
        "starting_point_only": (start_lo, start_hi, start_width),
        "both": (both_lo, both_hi, both_hi - both_lo),
        "ratio": (start_width / band_width) if band_width else None,
        "band_spread_share_pct": 100.0 * band_width / rent,
    }


# --------------------------------------------------------------------------
# Tier 3 - the same decision, made by a rule
# --------------------------------------------------------------------------
# **Written after Tier 2, and because of it.** The evaluator answers the starting-point
# question correctly in the modal case and unstably at the margin - 5/8 on `los-angeles`,
# where two runs in eight chose the full error band on a deal eight comparables corroborate
# to within 1%. A treatment that swings the reported year-5 rent by ~2x cannot be decided by
# a coin whose bias is the provider fleet.
#
# Every input the model was reasoning from is already a measured, deterministic field on
# `ValuationDetail`. So the rule below asks the same question of the same evidence and
# answers it the same way, with no call and no variance. It is the `critic.cross_check`
# pattern from U9.4 inverted: there the model annotates a rule's verdict; here the rule
# replaces a judgment the model cannot hold steady.
#
# The thresholds are stated, not tuned. Nothing in this project's fixtures declares a
# correct starting point, so tuning them against the demo deals would be scoring a rule
# against a reading of itself - the error `VerdictSource` exists to prevent.
RULE_MIN_COMPS = 3
# A RATIO, matching `ValuationDetail.divergence_pct` and `config.
# RENT_COMP_DIVERGENCE_THRESHOLD_PCT` (0.30), both of which carry a `_pct` suffix while
# holding ratios. The shipped pair is internally consistent; this constant is named the same
# way so it can be compared against them without a conversion, and the unit is stated here
# because the suffix says otherwise. A first draft of this rule compared the ratio against
# 10.0 and the check was silently inert.
RULE_MAX_DIVERGENCE_RATIO = 0.10


def rule_starting_point(evidence: Evidence) -> tuple[str, str]:
    """Deterministic starting-point treatment, plus the sentence explaining it.

    Reads corroboration the way the report already describes it to a reader: how many
    comparables independently checked the estimate, how far they landed from it, and whether
    the estimate is anchored at the property's own postal code or at a county median.
    """
    if evidence.anchor_tier == "county":
        return "full", (
            "the estimate is anchored at a county median rather than this property's own "
            "postal code, and rents span roughly 2x within a county"
        )
    if not evidence.comps_cross_checked:
        return "full", "no comparable rental independently checks this estimate"

    divergence = abs(evidence.divergence_pct or 0.0)  # ratio, not percent
    if (
        evidence.comps_cross_checked >= RULE_MIN_COMPS
        and divergence <= RULE_MAX_DIVERGENCE_RATIO
        and evidence.anchor_tier == "zip"
    ):
        return "point", (
            f"{evidence.comps_cross_checked} comparables independently imply a rent within "
            f"{divergence:.1%} of this estimate, at postal-code resolution"
        )
    return "half", (
        f"{evidence.comps_cross_checked} comparable(s) check this estimate and land "
        f"{divergence:.1%} away, which is partial corroboration rather than none"
    )


# --------------------------------------------------------------------------
# The re-purposed prompt
# --------------------------------------------------------------------------


def _evidence_block(evidence: Evidence) -> str:
    """The part `_context_block` does not carry today.

    Written as measurements with their sample sizes rather than as a verdict, because the
    whole point of the re-purposing is that the *evaluator* weighs this evidence. A block
    that said "this estimate is well corroborated" would be making the decision in the
    prompt and then asking the model to agree with it.
    """
    lines = ["Evidence about the rent estimate this forecast would compound:"]
    if evidence.rent_estimate is not None:
        lines.append(f"  - Modelled rent: ${evidence.rent_estimate:,.0f}/mo.")
    if evidence.mae_overall is not None:
        lines.append(
            f"  - The rent model's holdout error is ${evidence.mae_overall:,.0f}/mo "
            f"averaged across every market it was trained on."
        )
    if evidence.mae_metro is not None and evidence.metro:
        share = ""
        if evidence.rent_estimate:
            share = f" ({100 * evidence.mae_metro / evidence.rent_estimate:.0f}% of the estimate)"
        lines.append(
            f"  - In {evidence.metro} specifically the same measurement missed by "
            f"${evidence.mae_metro:,.0f}/mo{share}."
        )
    if evidence.comps_available:
        lines.append(
            f"  - {evidence.comps_available} comparable rental(s) were retrieved, "
            f"{evidence.comps_cross_checked} of which normalized cleanly enough to "
            f"cross-check the estimate, {evidence.comps_zip_anchored} at postal-code "
            f"resolution."
        )
    else:
        lines.append(
            "  - NO comparable rentals were retrieved, so nothing independent checks this "
            "estimate."
        )
    if evidence.comp_implied_median is not None and evidence.divergence_pct is not None:
        direction = "above" if evidence.divergence_pct > 0 else "below"
        lines.append(
            f"  - Those comps imply ${evidence.comp_implied_median:,.0f}/mo; the model sits "
            f"{abs(evidence.divergence_pct):.0f}% {direction} that."
        )
    if evidence.anchor_tier == "zip" and evidence.anchor_zip:
        lines.append(
            f"  - The estimate is anchored at the property's own postal code "
            f"({evidence.anchor_zip})."
        )
    elif evidence.anchor_tier == "county":
        lines.append(
            "  - The estimate is anchored at the COUNTY median rather than the property's "
            "own postal code, because no postal-code rent index covered it. Rents span "
            "roughly 2x within a single county."
        )
    lines.append(f"  - Flags raised upstream: {', '.join(evidence.flags) or 'none'}.")
    return "\n".join(lines)


def _starting_point_instruction() -> str:
    """The question the re-purposing substitutes, stated once.

    **Depth 2's shipped instruction already asks half of this** - "You are choosing which
    projections are worth showing a reader, not ranking which is most likely to happen" - so
    what is added here is not a new question so much as the evidence needed to answer the one
    already being asked, plus an explicit axis for it.
    """
    options = "\n".join(
        f"  - `{name}`: {description}" for name, _, description in STARTING_POINTS
    )
    return (
        "Each candidate also carries a STARTING-POINT treatment. The growth bands describe "
        "what the market did; the starting point describes how far the estimate being "
        "compounded can be trusted, and the two are independent judgments.\n"
        f"{options}\n"
        "Choose the treatment this deal's evidence supports. An estimate that several "
        "comparables independently corroborate to within a few percent can defensibly be "
        "compounded as a point; an estimate that nothing checks, or that rests on a "
        "county-wide anchor when postal-code resolution was unavailable, is a range being "
        "printed as a number and should be projected from its measured error instead. "
        "Widening the starting point is not pessimism - it is the honest width of what is "
        "known, and it applies symmetrically in both directions."
    )


def _repurposed_context(
    state: DealState, detail: ForecastDetail, evidence: Evidence, horizon: int
) -> str:
    """The shipped context block, plus the evidence it does not carry today."""
    return (
        f"{sf._context_block(state, detail, horizon)}\n\n"
        f"{_evidence_block(evidence)}\n\n"
        f"{_starting_point_instruction()}"
    )


# --------------------------------------------------------------------------
# Candidate enumeration - the two shapes
# --------------------------------------------------------------------------


def _with_start(candidate: tot.Candidate, name: str, multiple: float, note: str) -> tot.Candidate:
    payload = dict(candidate.payload)
    payload["starting_point"] = name
    payload["starting_multiple"] = multiple
    return tot.Candidate(
        id=f"{candidate.id}+{name}",
        parent=candidate.parent,
        depth=candidate.depth,
        payload=payload,
        summary=f"{candidate.summary}; starting point: {note}",
    )


def _expander(shape: str, rent_bands, price_bands):
    """Build the expander for the requested shape, reusing the shipped enumerators."""

    def expand(depth: int, parents: list[tot.Candidate]) -> list[tot.Candidate]:
        if depth == 1:
            base = sf._framings(rent_bands, price_bands)
            if shape != "framing":
                return base
            return [
                _with_start(c, name, mult, note)
                for c in base
                for name, mult, note in STARTING_POINTS
            ]
        if depth == 2:
            base = sf._pairings(parents)
            if shape != "pairing":
                # The framing already fixed the treatment; carry it down unchanged so the
                # projection step can read it off either level.
                out = []
                for c in base:
                    parent = next((p for p in parents if p.id == c.parent), None)
                    payload = dict(c.payload)
                    if parent is not None:
                        payload["starting_point"] = parent.payload.get("starting_point")
                        payload["starting_multiple"] = parent.payload.get("starting_multiple")
                    out.append(
                        tot.Candidate(
                            id=c.id, parent=c.parent, depth=2, payload=payload,
                            summary=c.summary,
                        )
                    )
                return out
            return [
                _with_start(c, name, mult, note)
                for c in base
                for name, mult, note in STARTING_POINTS
            ]
        return []

    return expand


# --------------------------------------------------------------------------
# Running one search
# --------------------------------------------------------------------------


def _run_search(
    state: DealState, shape: str, horizon: int
) -> tuple[tot.SearchResult, Evidence, ForecastDetail, Any, Any]:
    detail = ForecastDetail(
        horizon_years=horizon,
        projection_base_price=state.deal_terms.price,
        projection_base_source="asking price" if state.deal_terms.price is not None else None,
        projection_base_rent=state.rent_estimate,
    )
    rent_bands, price_bands = sf._build_bands(state, detail)
    evidence = _load_evidence(state, state.deal_terms.full_address or "deal")

    # Score against the flag set the forecast node actually saw. `state` here is a
    # FINISHED run, so its flags include the Critic's and the Summarizer's; handing those
    # to the evaluator would let the spike reason from evidence the shipped node never had.
    upstream = state.model_copy(update={
        "flags": [f for f in state.flags if getattr(f, "agent", None) in UPSTREAM_AGENTS]
    })
    context = _repurposed_context(upstream, detail, evidence, horizon)

    result = tot.beam_search(
        expand=_expander(shape, rent_bands, price_bands),
        hard_check=sf._hard_check,
        score=sf._make_scorer(context, detail),
        beam_width={1: config.TOT_FRAMING_BEAM_WIDTH, 2: config.TOT_BEAM_WIDTH},
        prune_threshold={
            1: config.TOT_FRAMING_PRUNE_THRESHOLD,
            2: config.TOT_PRUNE_THRESHOLD,
        },
        conservatism_key=sf._conservatism,
        reserved=sf._is_neutral_pairing,
    )
    return result, evidence, detail, rent_bands, price_bands


def _project(candidate: tot.Candidate, evidence: Evidence, horizon: int) -> dict:
    """Project one survivor under its own starting-point treatment."""
    payload = candidate.payload
    rent = evidence.rent_estimate
    err = evidence.error or 0.0
    multiple = payload.get("starting_multiple") or 0.0
    rent_rate = payload.get("rent_rate")
    price_rate = payload.get("price_rate")

    row: dict[str, Any] = {
        "id": candidate.id,
        "score": candidate.score,
        "rent_band": payload.get("rent_band"),
        "price_band": payload.get("price_band"),
        "starting_point": payload.get("starting_point"),
        "rationale": candidate.summary,
    }
    if rent is not None and rent_rate is not None:
        spread = err * multiple
        row["rent_low"] = _compound(rent - spread, rent_rate, horizon)
        row["rent_high"] = _compound(rent + spread, rent_rate, horizon)
        row["rent_point"] = _compound(rent, rent_rate, horizon)
    if price_rate is not None and evidence is not None:
        row["price_rate"] = price_rate
    return row


# --------------------------------------------------------------------------
# Deal loading
# --------------------------------------------------------------------------


from contextlib import contextmanager


@contextmanager
def _committed_recordings():
    """Force replay against the committed store for the duration of a block.

    `LlmClient` builds its `ResponseCache` from `config` at construction time, so scoping
    the two settings here is enough. **Loading a deal must never be a live call**: the
    pipeline's own prompts are already recorded, the spike's question is about the forecast
    level alone, and under `--tier 2` (which runs with the cache off so repeat calls actually
    reach the API) an unscoped load would re-run extraction, retrieval and the Summarizer
    live for every deal - spending the budget on the one part of the run this spike is not
    asking about.
    """
    dir_before, mode_before = config.LLM_CACHE_DIR, config.LLM_CACHE_MODE
    config.LLM_CACHE_DIR = Path("eval/data/llm_recordings")
    config.LLM_CACHE_MODE = "replay"
    try:
        yield
    finally:
        config.LLM_CACHE_DIR, config.LLM_CACHE_MODE = dir_before, mode_before


def _load_state(deal_key: str) -> DealState:
    """Replay one demo deal and return its final state.

    Replay rather than a live run: the pipeline's own calls are already recorded, this
    script's question is about the forecast level only, and paying for an extraction and a
    summary to get at a `ValuationDetail` would be spending the budget on the wrong thing.
    """
    import sqlite3
    from contextlib import closing
    from uuid import uuid4

    from langgraph.checkpoint.sqlite import SqliteSaver

    import demo_deals
    from graph import build_graph, state_serde
    from main import CHECKPOINT_DB, _initial_state

    deal = demo_deals.DEMO_DEALS[deal_key]

    with closing(sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)) as conn:
        graph = build_graph(checkpointer=SqliteSaver(conn, serde=state_serde()))
        # A FRESH id per load, exactly as `main.main` does. A stable one resumes the
        # thread from wherever it stopped, which on a second run means invoking a
        # completed graph with new input and getting a state the recordings never saw.
        cfg = {"configurable": {"thread_id": f"spike-{deal_key}-{uuid4().hex[:8]}"}}
        with _committed_recordings():
            result = graph.invoke(
                _initial_state(deal.listing, deal.supplied_coords), cfg
            )
            if "__interrupt__" in result:
                from langgraph.types import Command

                result = graph.invoke(Command(resume="[spike] released"), cfg)
    return DealState(**{k: v for k, v in result.items() if k != "__interrupt__"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tier", type=int, default=0, choices=(0, 1, 2, 3))
    parser.add_argument("--shape", default="framing", choices=("framing", "pairing"))
    parser.add_argument("--deals", default="los-angeles,staten-island")
    parser.add_argument("--runs", type=int, default=8)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    horizon = config.FORECAST_HORIZON_YEARS
    deals = [d.strip() for d in args.deals.split(",") if d.strip()]
    print(f"tier {args.tier} | shape {args.shape} | deals {deals} | horizon {horizon}y")
    print(f"cache dir : {config.LLM_CACHE_DIR}")
    print(f"cache mode: {config.LLM_CACHE_MODE}\n")

    record: dict[str, Any] = {"tier": args.tier, "shape": args.shape, "deals": {}}

    for key in deals:
        print(f"\n{'=' * 78}\n{key}\n{'=' * 78}")
        state = _load_state(key)
        evidence = _load_evidence(state, key)

        # The bands the SHIPPED run actually reported, read off the state the graph
        # already produced. **Not by re-running the agent**: `_context_block` embeds the
        # flags raised so far, and on a finished state that set includes every downstream
        # flag the forecast node never saw - a different prompt, and a cache miss against
        # recordings that are perfectly valid.
        detail = state.forecast_detail
        if detail is None:
            print("  no forecast detail on state")
            continue

        bands = None
        if detail.rent_growth_base_pct is not None:
            bands = (
                detail.rent_growth_pessimistic_pct,
                detail.rent_growth_base_pct,
                detail.rent_growth_optimistic_pct,
            )

        if args.tier == 0:
            if bands is None:
                print("  no rent bands - nothing to compare")
                continue
            out = tier0(evidence, bands, horizon)
            record["deals"][key] = {"tier0": out, "evidence": vars(evidence)}
            _print_tier0(out, evidence)
            continue

        if args.tier == 1:
            result, evidence, detail, _, _ = _run_search(state, args.shape, horizon)
            rows = [_project(c, evidence, horizon) for c in result.survivors]
            record["deals"][key] = {
                "evidence": vars(evidence),
                "rows": rows,
                "ledger": [
                    {
                        "id": c.id, "depth": c.depth, "score": c.score,
                        "pruned": c.prune_reason, "summary": c.summary,
                    }
                    for c in result.ledger
                ],
            }
            _print_tier1(rows, result, evidence, horizon)
            continue

        if args.tier == 2:
            record["deals"][key] = _tier2(state, args.shape, horizon, args.runs)
            continue

        if args.tier == 3:
            if bands is None:
                print("  no rent bands - nothing to project")
                continue
            treatment, why = rule_starting_point(evidence)
            multiple = dict((n, m) for n, m, _ in STARTING_POINTS)[treatment]
            err = evidence.error or 0.0
            rent = evidence.rent_estimate
            spread = err * multiple
            rows = []
            for name, pct in zip(("weakest", "long-run", "strongest"), bands):
                rows.append({
                    "band": name, "pct": pct,
                    "low": _compound(rent - spread, pct, horizon),
                    "high": _compound(rent + spread, pct, horizon),
                })
            record["deals"][key] = {
                "evidence": vars(evidence), "treatment": treatment,
                "why": why, "rows": rows,
            }
            print(f"  rule -> {treatment.upper()}  ({why})")
            print(f"  comps_xchecked={evidence.comps_cross_checked} "
                  f"divergence={evidence.divergence_pct if evidence.divergence_pct is None else format(evidence.divergence_pct, '.2%')} "
                  f"anchor={evidence.anchor_tier}")
            for r in rows:
                if spread:
                    print(f"    {r['band']:9s} {r['pct']:+.2f}%/yr  "
                          f"yr{horizon} ${r['low']:,.0f} - ${r['high']:,.0f}")
                else:
                    print(f"    {r['band']:9s} {r['pct']:+.2f}%/yr  yr{horizon} ${r['low']:,.0f}")

    out_path = Path(
        args.out
        or (Path(os.environ.get("SPIKE_OUT", ".")) / f"spike_tier{args.tier}_{args.shape}.json")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {out_path}")


def _print_tier0(out: dict, evidence: Evidence) -> None:
    if out.get("unavailable"):
        print("  no rent estimate or no error measurement - cannot compare")
        return
    gl, gh, gw = out["growth_only"]
    sl, sh, sw = out["starting_point_only"]
    bl, bh, bw = out["both"]
    print(f"  rent ${out['rent_estimate']:,.0f}/mo  +/- ${out['error']:,.0f} "
          f"({out['error_share_pct']:.0f}% of the estimate)")
    print(f"  bands {out['bands_pct'][0]:+.2f} / {out['bands_pct'][1]:+.2f} / "
          f"{out['bands_pct'][2]:+.2f} %/yr\n")
    print(f"  growth bands alone    ${gl:,.0f} - ${gh:,.0f}   width ${gw:,.0f}")
    print(f"  starting point alone  ${sl:,.0f} - ${sh:,.0f}   width ${sw:,.0f}")
    print(f"  both                  ${bl:,.0f} - ${bh:,.0f}   width ${bw:,.0f}")
    if out["ratio"]:
        print(f"\n  -> starting point is {out['ratio']:.2f}x the growth bands' width")
    print(f"  -> 5yr band spread is {out['band_spread_share_pct']:.0f}% of the estimate")


def _print_tier1(rows: list[dict], result, evidence: Evidence, horizon: int) -> None:
    chosen = {r["starting_point"] for r in rows}
    print(f"\n  starting-point treatment(s) chosen: {sorted(c for c in chosen if c)}")
    print(f"  {len(result.ledger)} candidates, {result.n_pruned} pruned\n")
    for r in rows:
        band = f"{r['rent_band']}/{r['price_band']}"
        start = r["starting_point"] or "-"
        if "rent_low" in r:
            print(f"  {band:24s} start={start:5s} score={r['score']:.2f}  "
                  f"yr{horizon} rent ${r['rent_low']:,.0f} - ${r['rent_high']:,.0f}")
        else:
            print(f"  {band:24s} start={start:5s} score={r['score']:.2f}")


def _tier2(state: DealState, shape: str, horizon: int, runs: int) -> dict:
    """The same search N times, measuring whether the treatment is stable.

    **The tier that can kill the design.** A starting-point treatment that swings the
    headline number by ~2x has to be reproducible across identical calls, and OQ-17 has
    already measured this model's scores moving materially between them.
    """
    picks: list[Optional[str]] = []
    scores: list[float] = []
    for i in range(runs):
        result, evidence, _, _, _ = _run_search(state, shape, horizon)
        survivors = result.survivors
        chosen = {c.payload.get("starting_point") for c in survivors}
        pick = sorted(c for c in chosen if c)
        picks.append("+".join(pick) if pick else None)
        top = max((c.score or 0.0) for c in survivors) if survivors else 0.0
        scores.append(top)
        print(f"  run {i + 1}/{runs}: treatment={picks[-1]}  top score={top:.2f}")

    counts: dict[str, int] = {}
    for p in picks:
        counts[str(p)] = counts.get(str(p), 0) + 1
    modal = max(counts.values()) if counts else 0
    print(f"\n  treatment distribution: {counts}")
    print(f"  stability: {modal}/{runs} runs agreed on the modal treatment")
    if len(scores) > 1:
        print(f"  top score mean {statistics.mean(scores):.3f}, "
              f"stdev {statistics.pstdev(scores):.3f}, "
              f"range {min(scores):.2f}-{max(scores):.2f}")
    return {
        "runs": runs, "picks": picks, "counts": counts,
        "stability": modal / runs if runs else None,
        "scores": scores,
    }


if __name__ == "__main__":
    main()
