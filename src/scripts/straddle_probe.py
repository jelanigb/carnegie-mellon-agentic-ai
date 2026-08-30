"""Where does a subject have to sit to land either side of a per-flag threshold? (U8.6b)

    .venv/bin/python scripts/straddle_probe.py

**What this is for.** U8.6's sensitivity sweep found that the confidence threshold and the
severity weights have a *dead zone* — the scores are quantized to multiples of the warn
weight, so nothing in the batch can distinguish a threshold anywhere in (0.40, 0.70] from
the shipped 0.60. The verdict-deciding lines are therefore not in the confidence
parameters at all; they are in the **per-flag thresholds** that decide whether a third
warn fires in the first place. U8.6b measures rigidity *there*, by building pairs of
near-identical fixtures either side of each line.

Siting those pairs needs a search, and the search must not cost model calls. So this
script runs the **real** comp-retrieval and Valuation agents — the two that produce every
quantity a per-flag threshold is compared against — over a grid of candidate subjects, and
prints the measured quantity beside its threshold. Nothing here asserts; it reports where
the lines fall so the fixtures can be written against measurements rather than guesses.

Neither agent calls a model (`agents/summarizer.py` and the ToT forecast are the LLM
consumers, and both sit downstream), so a full sweep is free apart from the FMR cache and
the Chroma index.

**Four of the six tunables in U8.6b's table are searched here; two are not, and the reason
is a property of the tunable rather than a gap in this script:**

  * `RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD` — the compared quantity is a *market's*
    holdout error ratio, which no listing can move. Not straddleable by any deal.
  * `TOT_TIE_EPSILON` — the compared quantity comes from an LLM judge whose single-draw
    noise (OQ-17) is an order of magnitude larger than the epsilon, so a recorded straddle
    would measure the recording rather than the threshold.

Writes nothing.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents.comps_retrieval import _outside_match_criteria, comps_retrieval_agent
from agents.valuation_rent import valuation_rent_agent
from eval.data import golden_fixtures
from tools import county_crosswalk
from state import DealState, DealTerms


@dataclass
class Probe:
    """Every quantity a per-flag threshold in U8.6b's table is compared against."""

    comps: int
    distinct_locations: int
    outside_share: float
    outside_count: int
    divergence_pct: Optional[float]
    rent_estimate: Optional[float]
    anchor: Optional[float]
    anchor_tier: Optional[str]
    kinds: tuple[str, ...]


def probe(terms: DealTerms) -> Probe:
    """Run the two deterministic agents and read the thresholds' own inputs back out."""
    # The county is resolved here because a golden fixture supplies coordinates and lets
    # the *Extractor* derive the county from them — and the Extractor is the one agent on
    # this path that calls a model. Doing the polygon lookup directly is the same
    # operation without the call. Skipping it would have the Valuation agent refuse every
    # subject for a missing county and report a clean sweep of empty rows.
    if terms.county_fips is None:
        terms = terms.model_copy(update={
            "county_fips": county_crosswalk.lookup_county_fips(
                terms.latitude, terms.longitude
            )
        })
    state = DealState(raw_listing_text="[straddle probe]", deal_terms=terms)
    update = comps_retrieval_agent(state)
    state = state.model_copy(update={k: v for k, v in update.items() if k != "flags"})
    kinds = [f.kind.value for f in update.get("flags", [])]

    val = valuation_rent_agent(state)
    state = state.model_copy(update={k: v for k, v in val.items() if k != "flags"})
    kinds += [f.kind.value for f in val.get("flags", [])]

    detail = state.valuation_detail
    coords = {(c.latitude, c.longitude) for c in state.comps
              if c.latitude is not None and c.longitude is not None}
    outside = _outside_match_criteria(state.comps, terms) if state.comps else []
    return Probe(
        comps=len(state.comps),
        distinct_locations=len(coords),
        outside_share=len(outside) / len(state.comps) if state.comps else 0.0,
        outside_count=len(outside),
        divergence_pct=detail.divergence_pct if detail else None,
        rent_estimate=state.rent_estimate,
        anchor=state.rent_anchor_used,
        anchor_tier=detail.anchor_tier if detail else None,
        kinds=tuple(sorted(set(kinds))),
    )


def _row(label: str, p: Probe) -> None:
    div = f"{p.divergence_pct:+7.1%}" if p.divergence_pct is not None else "      -"
    rent = f"{p.rent_estimate:,.0f}" if p.rent_estimate is not None else "-"
    print(f"  {label:<28} n={p.comps:<3} loc={p.distinct_locations:<3} "
          f"outside={p.outside_count}/{p.comps} ({p.outside_share:.2f})  "
          f"div={div}  rent={rent:>7}  {p.anchor_tier or '-':<7}")


def sweep_sqft(base: DealTerms, label: str, values: list[float]) -> None:
    """`COMP_MAX_OUTSIDE_MATCH_SHARE` and `MIN_QUALIFYING_COMPS`, both moved by floor area.

    Square footage is the one subject attribute that moves the outside-match count without
    changing what the property *is* — the bedroom count is matched exactly and relaxed only
    as a whole, so varying it changes the comp pool's composition rather than its distance
    from the subject. That is what makes a sqft pair a straddle rather than two different
    experiments.
    """
    print(f"\n=== {label} — square footage against "
          f"COMP_MAX_OUTSIDE_MATCH_SHARE ({config.COMP_MAX_OUTSIDE_MATCH_SHARE}) "
          f"and MIN_QUALIFYING_COMPS ({config.MIN_QUALIFYING_COMPS}) ===")
    for sqft in values:
        _row(f"{sqft:,.0f} sqft", probe(base.model_copy(update={"square_footage": sqft})))


def sweep_divergence(base: DealTerms, label: str, values: list[float]) -> None:
    """`RENT_COMP_DIVERGENCE_THRESHOLD_PCT`, moved through the subject's own attributes.

    The divergence is `(estimate - comp median) / comp median`, and the estimate is the
    model's ratio times the anchor. Bathrooms move the ratio without moving the comp set's
    composition much, so they are the cleaner lever than floor area here: a sqft change
    moves *both* sides of the comparison and can leave the divergence unmoved for the
    wrong reason.
    """
    print(f"\n=== {label} — bathrooms against RENT_COMP_DIVERGENCE_THRESHOLD_PCT "
          f"({config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:.0%}) ===")
    for baths in values:
        _row(f"{baths:g} bath", probe(base.model_copy(update={"bathrooms": baths})))


def main() -> None:
    print(f"Thresholds: outside_share {config.COMP_MAX_OUTSIDE_MATCH_SHARE}, "
          f"min_comps {config.MIN_QUALIFYING_COMPS}, "
          f"min_locations {config.COMP_MIN_DISTINCT_LOCATIONS}, "
          f"divergence {config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:.0%}")

    la = golden_fixtures.LA_ORDINARY.terms
    chi = golden_fixtures.CHI_UPTOWN_ORDINARY.terms
    ny = golden_fixtures.NY_BEDSTUY_ORDINARY.terms

    print("\n=== The shipped fixtures, as they stand ===")
    for fixture in (golden_fixtures.LA_ORDINARY, golden_fixtures.CHI_UPTOWN_ORDINARY,
                    golden_fixtures.CHI_UPTOWN_OVERSIZED, golden_fixtures.CLE_ORDINARY,
                    golden_fixtures.NY_BEDSTUY_ORDINARY):
        _row(fixture.key, probe(fixture.terms))

    sweep_sqft(la, "Los Angeles", [700, 800, 900, 950, 1_100, 1_300, 1_600, 2_000])
    sweep_sqft(chi, "Chicago Uptown", [700, 800, 950, 1_100, 1_300, 1_600, 2_000])
    sweep_divergence(chi, "Chicago Uptown", [1.0, 1.5, 2.0, 2.5, 3.0])
    sweep_divergence(la, "Los Angeles", [1.0, 1.5, 2.0, 2.5, 3.0])

    # `COMP_MIN_DISTINCT_LOCATIONS` needs no sweep — New York supplies a natural control.
    # Bed-Stuy carries 87 of its 89 corpus rows on a single placeholder coordinate, while
    # Manhattan's rows are spread across dozens. Two subjects in the same city, the same
    # market-level flags, and opposite sides of the line, which is a cleaner straddle than
    # anything an engineered attribute could produce.
    print(f"\n=== New York — the natural control for COMP_MIN_DISTINCT_LOCATIONS "
          f"({config.COMP_MIN_DISTINCT_LOCATIONS}) ===")
    _row("bed-stuy (placeholder)", probe(ny))
    manhattan = ny.model_copy(update={
        "full_address": "410 W 45th St, New York, NY 10036",
        "street_address": "410 W 45th St",
        "city": "New York",
        "zip_code": "10036",
        "latitude": 40.760, "longitude": -73.992,
    })
    _row("manhattan (dispersed)", probe(manhattan))


if __name__ == "__main__":
    main()
