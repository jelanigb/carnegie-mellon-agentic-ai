"""Evidence for U5 — the rent estimate, end to end, against live services.

A script rather than a test, per §8's split: this geocodes nothing but does resolve real
county polygons, call the real HUD FMR API, and query the real Chroma index, so a
failure here *is* the finding and must not be hidden behind a mock. `tests/` stays
hermetic; `tests/test_flag_propagation.py` covers the same agent with a fake schedule.

What it produces that prose cannot:

  1. **The anchored figure with its inputs beside it** — ratio, FMR, fiscal year — so
     the claim "this is not an observed market rent" is checkable rather than asserted.
  2. **The comp cross-check on real comps**, including how many of the retrieved set
     survived normalization. This is the number `config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT`
     is set from: a threshold that fired on every market would carry no information, and
     §2 has already made that mistake once (the initial 1.0-mile search radius relaxed
     on essentially every run until it was retuned against measured density).
  3. **The degradation paths, on subjects that genuinely trip them** rather than on
     fixtures engineered to. Staten Island retrieves too few comps to cross-check and
     sits in the one metro Redfin's extract never reached.

Four subjects: the inference trio (§2) plus Staten Island, carried over from
`scripts/retrieval_evidence.py` so the two scripts describe the same properties and can
be read against each other.

Run: .venv/bin/python scripts/valuation_evidence.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from agents.comps_retrieval import comps_retrieval_agent
from agents.valuation_rent import valuation_rent_agent
from state import DealState, DealTerms
from tools import county_crosswalk, hud_fmr, kaggle_data, zcta_crosswalk, zori
from tools.vector_store import haversine_miles
from tools.model import rent_model

# The same synthetic subjects `scripts/retrieval_evidence.py` uses. Coordinates are real
# locations; the deal terms are synthetic, per the program's requirement that no real
# listing data be used. `county_fips` is deliberately *not* written here — it is
# resolved below from the coordinates, so this script exercises the real crosswalk
# rather than trusting a value typed into a fixture.
SUBJECTS = {
    "Los Angeles (dense)": DealTerms(
        full_address="[synthetic] 2-unit duplex, Echo Park, Los Angeles CA",
        price=1_049_000, unit_count=2, bedrooms=2, bathrooms=1.0,
        square_footage=950, city="Los Angeles", state="CA",
        latitude=34.0522, longitude=-118.2437,
    ),
    "Chicago (moderate)": DealTerms(
        full_address="[synthetic] 2-flat, Logan Square, Chicago IL",
        price=499_000, unit_count=2, bedrooms=2, bathrooms=1.0,
        square_footage=950, city="Chicago", state="IL",
        latitude=41.9227, longitude=-87.6982,
    ),
    "Cleveland (thin, single-coordinate comps)": DealTerms(
        full_address="[synthetic] 2-unit, Ohio City, Cleveland OH",
        price=245_000, unit_count=2, bedrooms=2, bathrooms=1.0,
        square_footage=1_000, city="Cleveland", state="OH",
        latitude=41.4670, longitude=-81.7001,
    ),
    "Staten Island (no comps, no Redfin coverage)": DealTerms(
        full_address="[synthetic] 3-unit building, Tottenville, Staten Island NY",
        price=875_000, unit_count=3, bedrooms=2, bathrooms=1.0,
        square_footage=900, city="Staten Island", state="NY",
        latitude=40.5083, longitude=-74.2422,
    ),
}


def _money(value) -> str:
    return f"${value:,.0f}" if value is not None else "—"


def run(label: str, subject: DealTerms) -> None:
    subject = subject.model_copy(
        update={
            "county_fips": county_crosswalk.lookup_county_fips(
                subject.latitude, subject.longitude
            )
        }
    )
    state = DealState(raw_listing_text="[synthetic subject]", deal_terms=subject)
    state = state.model_copy(update=comps_retrieval_agent(state))
    update = valuation_rent_agent(state)
    state = state.model_copy(update={k: v for k, v in update.items() if k != "flags"})
    detail = state.valuation_detail

    print(f"\n{'=' * 74}\n{label}\n{'=' * 74}")
    print(f"  county            {subject.county_fips or 'UNRESOLVED'}")
    print(f"  comps retrieved   {len(state.comps)}")

    if state.rent_estimate is None:
        print("  rent estimate     NOT PRODUCED")
    else:
        print(
            f"  rent estimate     {_money(state.rent_estimate)}/mo per unit   "
            f"= ratio {state.rent_estimate_ratio_to_anchor:.3f} "
            f"x market rent {_money(state.rent_anchor_used)} "
            f"({detail.anchor_tier} tier, {detail.anchor_index_month}, "
            f"FY{detail.fmr_shape_year} bedroom shape)"
        )
        print(f"  scored MAE        ± {_money(detail.model_mae_dollars)}/mo")

    if detail.comp_implied_rent_median is not None:
        print(
            f"  comp cross-check  {detail.comps_cross_checked}/{detail.comps_available} "
            f"normalized -> median {_money(detail.comp_implied_rent_median)}/mo "
            f"(p25 {_money(detail.comp_implied_rent_p25)}, "
            f"p75 {_money(detail.comp_implied_rent_p75)})"
        )
        print(
            f"  divergence        {detail.divergence_pct:+.1%}   "
            f"threshold ±{config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:.0%}   "
            f"{'FLAGGED' if abs(detail.divergence_pct) > config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT else 'within'}"
        )
    else:
        print(
            f"  comp cross-check  NOT RUN "
            f"({detail.comps_cross_checked}/{detail.comps_available} normalized, "
            f"need {config.RENT_COMP_CROSSCHECK_MIN_COMPS})"
        )

    if detail.benchmark_median_sale_price is not None:
        drift = (subject.price - detail.benchmark_median_sale_price) / (
            detail.benchmark_median_sale_price
        )
        print(
            f"  market benchmark  {_money(detail.benchmark_median_sale_price)} "
            f"({detail.benchmark_metro}, {detail.benchmark_periods_averaged} periods, "
            f"~{detail.benchmark_homes_sold_per_period:,.0f} sales/period)   "
            f"asking is {drift:+.0%}"
        )
    else:
        print(f"  market benchmark  NONE — {detail.benchmark_unavailable_reason}")

    for f in update["flags"]:
        print(f"  [{f.severity:>8}] {f.kind}")


# The metro each subject sits in, as (state, city pattern) for `kaggle_data`. Only the
# diagnostic below needs it — the main run resolves everything from coordinates.
_METRO_OF = {
    "Los Angeles (dense)": ("CA", "Los Angeles"),
    "Chicago (moderate)": ("IL", "Chicago"),
    "Cleveland (thin, single-coordinate comps)": ("OH", "Cleveland"),
}


def diagnose_divergence() -> None:
    """Attribute the estimate-vs-comps gap to the model or to the comp set.

    **Written because the first live run of the cross-check produced a result that
    looked like one thing and was another.** The estimate came in below the comp median
    in all three markets — 21.6%, 30.4%, 40.0% — and a consistent direction across three
    independent markets reads as a biased model. Acting on that reading would have meant
    retraining, or quietly widening the threshold until the flag stopped firing.

    The check is to normalize a third quantity the same way and see which input moves.
    **Choose that third quantity carefully — the first attempt got this wrong.** Comparing
    each comp set against its metro's *entire* 2-bedroom population showed the comps
    sitting far above it and indicted retrieval. But comps come from a 2-4 mile radius, so
    that comparison measures the neighborhood, not the ranking. Against the candidate pool
    at the same radius, ranking moves the median only +2.7% / +21.6% / +4.2% against a
    neighborhood effect of +5.1% / +40.1% / +66.2%.

    So the divergence belongs to the model. **The reason it does changed at U11.3 and the
    conclusion did not**, which is worth stating because the old reason is quoted in
    several places: the model used to be location-blind below the county, since a
    county-grain FMR was the only channel through which location entered. It no longer is
    — the anchor reads the market index at the subject's own ZIP wherever that ZIP is
    covered. What remains is that `config.RENT_MODEL_FEATURES` still carries no market
    identifier by design, so everything the *anchor* fails to absorb is still error the
    model structurally cannot recover. The blind spot moved from the county line down to
    whatever the ZIP-level index misses; it did not close.

    **The baselines are read from the training frame rather than re-derived here**, and
    that is the repair the U11.3 rename forced. This function used to normalize the metro
    population against FMR while the comps beside it were normalized against the hybrid
    anchor — two denominators, printed as though they were one, which would have made the
    attribution meaningless in exactly the quiet way §2 exists to prevent. Reusing
    `build_training_frame` means the population and the comps cannot disagree about what a
    ratio is.

    Slow — the frame resolves a county polygon and a ZCTA per corpus row — so it is opt-in
    rather than part of the default run.
    """
    client = hud_fmr.HudFmrClient()
    bundle = rent_model.load()
    if bundle is None:
        print("No trained model on disk; run scripts/train_rent_model.py first.")
        return
    frame, _ = rent_model.build_training_frame(client)

    print(f"\n{'=' * 74}\nDivergence attribution — is it the model or the comp set?"
          f"\n{'=' * 74}")
    print("  All three rows are rent-to-anchor ratios, normalized identically.\n")

    for label, (state_code, city) in _METRO_OF.items():
        subject = SUBJECTS[label]
        fips = county_crosswalk.lookup_county_fips(subject.latitude, subject.longitude)

        # The subject's own anchor, resolved exactly as the agent resolves it — hybrid,
        # at the market index's newest month — so `retrieved` below is a ratio against
        # the same denominator the training rows carry.
        fiscal_year = rent_model.fmr_fiscal_year(pd.Timestamp.now())
        tables = rent_model.build_anchor_tables({(fips, fiscal_year)}, client)
        month = zori.latest_month(tables.zori_panel) if tables.available else None
        subject_zip = subject.zip_code or zcta_crosswalk.lookup_zcta(
            subject.latitude, subject.longitude
        )
        subject_anchor, _tier = rent_model.anchor_for_row(
            int(subject.bedrooms), fips, fiscal_year, month, subject_zip, tables
        )

        predicted = rent_model.predict_ratio(
            bundle, subject.bedrooms, subject.bathrooms, subject.square_footage
        )

        terms = subject.model_copy(update={"county_fips": fips})
        deal = DealState(raw_listing_text="[synthetic subject]", deal_terms=terms)
        deal = deal.model_copy(update=comps_retrieval_agent(deal))
        anchoring = rent_model.anchor_comp_rents(deal.comps, subject_anchor, client)
        retrieved = [r / subject_anchor for r in anchoring.implied_rents]

        # The whole metro's comparable population, straight off the training frame — the
        # same rows, the same anchor, the same bounds the model was fitted under.
        df = frame[
            (frame["state"] == state_code)
            & frame["cityname"].apply(lambda c: kaggle_data.city_matches(c, [city]))
            & (frame["bedrooms"] == int(subject.bedrooms))
        ].copy()
        population = df["rent_to_anchor"]

        # The second baseline, and the one that makes the attribution correct: the same
        # corpus rows, restricted to the radius retrieval actually settled on. Comparing
        # a comp set to its whole metro measures the neighborhood; comparing it to its own
        # candidate pool measures the ranking. Only the second answers the question asked.
        # Row-wise rather than a vectorized copy of the formula: `haversine_miles` is
        # scalar-only, and a second implementation here could drift from the one comp
        # retrieval actually uses to trim its radius. A few thousand rows in a script is
        # not worth that risk.
        df["dist"] = df.apply(
            lambda r: haversine_miles(
                subject.latitude, subject.longitude, r["latitude"], r["longitude"]
            ),
            axis=1,
        )
        local = df[df["dist"] <= deal.search_radius_miles]["rent_to_anchor"]

        if not retrieved or population.empty or local.empty:
            print(f"\n  {label}: insufficient data to attribute.")
            continue

        comp_median = float(np.median(retrieved))
        pop_median = float(population.median())
        local_median = float(local.median())
        print(f"\n  {label}  (anchor ${subject_anchor:,.0f} at {month}, "
              f"radius {deal.search_radius_miles:.1f} mi)")
        print(f"    model prediction          ratio {predicted:.3f}")
        print(f"    retrieved comps    n={len(retrieved):<5} median {comp_median:.3f}")
        print(f"    local pool @radius n={len(local):<5} median {local_median:.3f}")
        print(f"    whole metro        n={len(population):<5} median {pop_median:.3f}")
        print(f"      neighborhood effect  (local vs metro)     "
              f"{local_median / pop_median - 1:+7.1%}   <-- dominates")
        print(f"      ranking effect       (retrieved vs local) "
              f"{comp_median / local_median - 1:+7.1%}")
        print(f"      model vs local pool                       "
              f"{predicted / local_median - 1:+7.1%}   <-- the actual divergence")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--diagnose-divergence",
        action="store_true",
        help="Attribute the estimate-vs-comps gap to the model or to the comp set (slow).",
    )
    args = parser.parse_args()

    print("U5 valuation evidence — live HUD FMR, real county polygons, real comp index")
    print(f"model: {config.RENT_MODEL_PATH.name}   "
          f"features: {', '.join(config.RENT_MODEL_FEATURES)}")
    for label, subject in SUBJECTS.items():
        run(label, subject)
    if args.diagnose_divergence:
        diagnose_divergence()
    print()


if __name__ == "__main__":
    main()
