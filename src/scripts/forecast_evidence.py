"""Evidence for U6 — does the Tree-of-Thought search change the forecast?

A script rather than a test, per §8's split: this calls the real HUD FMR API, reads the
real Redfin extract, and makes real model calls, so a failure here *is* the finding.
`tests/test_flag_propagation.py` covers the same agent hermetically, with the evaluator
forced down its deterministic fallback.

**The claim under test is the one Checkpoint 4.1 rests on**, and it is not "ToT ran." It
is that a *linear* chain fails here through premature commitment — that committing to the
first plausible framing and pairing the bands the obvious way produces a materially
different forecast from one that compares the alternatives. That is measurable, so it is
measured rather than argued.

The linear baseline is defined deliberately and stated so it can be disputed: the first
framing in enumeration order (every published year kept, 2020-2022 included — the "use
all the data" reading a chain reaches first), with the three **diagonal** pairings
(pessimistic-with-pessimistic, base-with-base, optimistic-with-optimistic). That is what
a competent implementation without a search would emit, and it is exactly the pairing
this project's own measurement argues against: rent and price growth are negatively
correlated here (pooled r = -0.309), so the diagonal describes a market behaving in a way
it usually has not.

**What this check could have returned had the search been decoration** — the §8 standard:

  * The search could have selected the first framing on every subject, in which case the
    framing level would be doing no work and should be cut to a constant.
  * It could have selected the diagonal pairings anyway, in which case the nine-way
    pairing enumeration would be an expensive way to reach the obvious answer.
  * The two forecasts could have landed within rounding of each other, in which case the
    node would be spending model calls to change nothing.

Any of those would be an argument for simplifying U6, and each is reported below whether
or not it holds.

Run: .venv/bin/python scripts/forecast_evidence.py
     .venv/bin/python scripts/forecast_evidence.py --subject "Chicago (moderate)"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
from agents.comps_retrieval import comps_retrieval_agent
from agents.scenario_forecast import (
    BAND_NAMES,
    _band_value,
    _build_bands,
    _to_scenarios,
    scenario_forecast_agent,
)
from agents.valuation_rent import valuation_rent_agent
from state import DealState, ForecastDetail
from tools import county_crosswalk

# The same four subjects `scripts/valuation_evidence.py` uses — the inference trio plus
# Staten Island — imported rather than restated so the three evidence scripts describe
# the same properties and can be read against each other. That script carried them over
# from `scripts/retrieval_evidence.py` for the same reason.
from valuation_evidence import SUBJECTS


def _prepared_state(terms) -> DealState:
    """Run the upstream nodes so the forecast sees what it sees in a real run.

    Geography is resolved from the subject's own coordinates rather than typed in, so
    this exercises the real crosswalk — the same reasoning `valuation_evidence.py` gives
    for not hard-coding `county_fips` into a fixture.
    """
    terms = terms.model_copy(deep=True)
    if terms.county_fips is None and terms.latitude is not None:
        terms.county_fips = county_crosswalk.county_fips_from_point(
            terms.latitude, terms.longitude
        )
    state = DealState(raw_listing_text=terms.full_address or "", deal_terms=terms)
    state = state.model_copy(update=comps_retrieval_agent(state))
    state = state.model_copy(update=valuation_rent_agent(state))
    return state


def _linear_baseline(state: DealState) -> list:
    """What a chain that commits to the first framing and pairs the obvious way emits."""
    detail = ForecastDetail(horizon_years=config.FORECAST_HORIZON_YEARS)
    rent_bands, price_bands = _build_bands(state, detail)
    if not rent_bands and not price_bands:
        return []

    # First in enumeration order: nothing screened, nothing excluded.
    rent = rent_bands.get(False) or (next(iter(rent_bands.values()), None))
    price = price_bands.get(False) or (next(iter(price_bands.values()), None))

    from tools import tot

    diagonal = [
        tot.Candidate(
            id=f"linear-{name}",
            depth=2,
            payload={
                "rent_band": name if rent is not None and rent.available else None,
                "price_band": name if price is not None else None,
                "rent_rate": _band_value(rent, name),
                "price_rate": _band_value(price, name),
            },
            summary=f"{name} rent paired with {name} price (diagonal)",
            score=None,
        )
        for name in BAND_NAMES
    ]
    return _to_scenarios(
        diagonal,
        state.rent_estimate,
        state.deal_terms.price,
        config.FORECAST_HORIZON_YEARS,
    )


def _fmt(scenarios: list) -> list[str]:
    rows = []
    for s in scenarios:
        rent = (
            f"{s.rent_growth_pct_per_year:+.2f}%"
            if s.rent_growth_pct_per_year is not None
            else "  —   "
        )
        price = (
            f"{s.price_growth_pct_per_year:+.2f}%"
            if s.price_growth_pct_per_year is not None
            else "  —   "
        )
        rent_5 = (
            f"${s.projected_monthly_rent:,.0f}"
            if s.projected_monthly_rent is not None
            else "—"
        )
        price_5 = f"${s.projected_price:,.0f}" if s.projected_price is not None else "—"
        rows.append(
            f"    {s.name:12s} rent {rent} -> {rent_5:>9s}   "
            f"price {price} -> {price_5:>12s}"
        )
    return rows


def _delta(searched: list, linear: list) -> str:
    """How far apart the two forecasts are, on the base case."""

    def base_of(scenarios):
        for scenario in scenarios:
            if scenario.name == "base":
                return scenario, True
        return (scenarios[len(scenarios) // 2], False) if scenarios else (None, False)

    (a, a_is_base), (b, b_is_base) = base_of(searched), base_of(linear)
    if a is None or b is None:
        return "    base case: not comparable (one side produced no scenarios)"
    # Pruning can leave two survivors, in which case there is no row labelled "base" and
    # the middle one stands in. Saying so matters: comparing a two-scenario set's middle
    # against a three-scenario set's base is not the like-for-like the line implies.
    caveat = (
        ""
        if a_is_base and b_is_base
        else "  [no 'base' row on one side; middle scenario substituted]"
    )
    parts = []
    for label, left, right in (
        ("rent", a.projected_monthly_rent, b.projected_monthly_rent),
        ("price", a.projected_price, b.projected_price),
    ):
        if left is None or right is None or not right:
            continue
        parts.append(
            f"{label} {(left / right - 1) * 100:+.1f}% "
            f"(${left:,.0f} vs ${right:,.0f})"
        )
    return (
        "    base case difference: "
        + ("; ".join(parts) or "no comparable side")
        + caveat
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", help="run one demo deal by name")
    args = parser.parse_args()

    names = [args.subject] if args.subject else list(SUBJECTS)

    same_framing = 0
    same_pairings = 0
    compared = 0

    for name in names:
        print("=" * 78)
        print(name)
        print("=" * 78)

        state = _prepared_state(SUBJECTS[name])
        update = scenario_forecast_agent(state)
        searched = update.get("scenarios") or []
        detail = update.get("forecast_detail")
        ledger = update.get("branch_ledger") or []

        if not searched:
            reason = " ".join(
                text
                for text in (
                    detail.rent_growth_unavailable_reason if detail else None,
                    detail.price_growth_unavailable_reason if detail else None,
                    detail.search_exhausted_reason if detail else None,
                )
                if text
            )
            print(f"  no scenarios — {reason}\n")
            continue

        linear = _linear_baseline(state)

        print("  Tree-of-Thought search:")
        print("\n".join(_fmt(searched)))
        print("\n  Linear baseline (first framing, diagonal pairings):")
        print("\n".join(_fmt(linear)) if linear else "    none")
        print()
        print(_delta(searched, linear))

        framings = [e for e in ledger if e.depth == 1]
        chosen_framing = next((e for e in framings if not e.prune_reason), None)
        first_framing = framings[0] if framings else None
        if chosen_framing and first_framing:
            compared += 1
            if chosen_framing.id == first_framing.id:
                same_framing += 1
                print("    framing: the search kept the first-enumerated framing")
            else:
                print(
                    f"    framing: the search rejected the first-enumerated framing "
                    f"({first_framing.id}) for {chosen_framing.id}"
                )
        diagonals = sum(
            1
            for s in searched
            if s.rent_band is not None and s.rent_band == s.price_band
        )
        if diagonals == len(searched):
            same_pairings += 1
            print("    pairings: all diagonal — the search reached the obvious answer")
        else:
            print(
                f"    pairings: {len(searched) - diagonals} of {len(searched)} are "
                f"off-diagonal, i.e. combinations a chain would not have produced"
            )
        print(
            f"    ledger: {len(ledger)} hypotheses recorded, "
            f"{sum(1 for e in ledger if e.prune_reason)} discarded"
        )
        if detail and detail.evidence_tools_called:
            print(
                f"    evidence pulled via the MCP tool registry: "
                f"{', '.join(sorted(set(detail.evidence_tools_called)))}"
            )
        print()

    if compared:
        print("=" * 78)
        print(
            f"Across {compared} subject(s) with a two-level search: the first-enumerated "
            f"framing survived {same_framing} time(s); an all-diagonal pairing set was "
            f"chosen {same_pairings} time(s)."
        )
        print(
            "Both counts equalling the subject count would mean the search reaches what a "
            "linear chain reaches, and U6 should be simplified to a constant."
        )


if __name__ == "__main__":
    main()
