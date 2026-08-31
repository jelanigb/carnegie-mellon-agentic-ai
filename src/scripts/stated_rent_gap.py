"""Is the stated-versus-modelled rent gap tunable, and what would it take to know? (U8.7)

    .venv/bin/python scripts/stated_rent_gap.py

`config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD` is `None`: the report renders the
comparison between a listing's stated rents and the modelled rent, and never editorializes
about it. U7.5 held it there because the gap was ~-29% on every demo listing and that
offset was *structural* — the estimate was a ratio to a 40th-percentile administrative
rent, the corpus behind the ratio rented well above it, so the gap measured the percentile
spread rather than the deal. U11.3 replaced that anchor with a market rent index and the
premise expired, which re-opened the question and is why this script exists.

**Two measurements, and they answer different halves of the question.**

1. **Is the gap a property of the deal?** Section 1 runs every golden fixture whose stated
   rents were set independently of the anchor and reports the distribution. Dispersed and
   sign-varying is what a deal property looks like; a near-constant is what an anchor
   artifact looks like.

2. **Would a threshold discriminate?** The same section prints, beside each gap, the flags
   the report already raised on that deal. A threshold that fires only where the report
   already names a more specific cause is not adding information — it is restating an
   existing disclosure in vaguer words, and blaming the listing's stated rent for a
   weakness the system has already attributed elsewhere.

**Section 2 tests the path U8.7 named as the way to get better evidence**, rather than
assuming it works: re-calibrating `demo_deals.DemoDeal.rent_basis` from `hud_fmr:2` to the
market-index anchor, to add six observations from outside the fixture set. Held as an
assumption until measured, and worth measuring precisely because the whole subsection is
about a premise that expired while nobody was looking.

**What the fixture rents are and are not.** They were chosen to look plausible for the
unit rather than derived from any published figure, so they are independent of the anchor —
which is the property this measurement needs — but they are invented rather than observed.
A distribution over them describes how the model prices unit types, sampled at 13 invented
points. That is a real limit on what any threshold read off it can claim, and it is the
reason this script prints the flag column rather than only the summary statistics.

No live model calls: the golden tier supplies complete `DealTerms` and replays recorded
forecast responses, the same environment `eval/runner.py` builds.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from demo_deals import DEMO_DEALS, DemoDeal
from eval import cases as eval_cases
from eval.cases import Tier
from eval.runner import _case_environment
from graph import build_graph
from state import DealState, DealTerms
from tools import county_crosswalk, geocoding, hud_fmr, zcta_crosswalk, zori
from tools.model import rent_model

# Candidate placements, spanning the region U8.7 identified as the shape of a usable
# disclosure — above the middle cluster, below the extreme tail.
CANDIDATE_THRESHOLDS = (0.20, 0.25, 0.30, 0.35, 0.40)

# Flags that name a specific reason this deal's rent estimate is hard to trust. The
# question in section 1 is whether a gap threshold fires anywhere these do not: if it
# never does, the emphasis it gates is a second notice of something already disclosed.
SPECIFIC_CAUSES = (
    "comps_outside_match_criteria",
    "fmr_bedroom_cap_exceeded",
    "rent_anchor_county_level",
    "rent_anchor_index_stale",
    "rent_diverges_from_comps",
    "rent_estimate_market_error_elevated",
    "sparse_comps",
)


def _fixture_gaps() -> list[dict]:
    """Every golden fixture that produced both a rent estimate and stated rents."""
    rows = []
    for case in eval_cases.ENGINEERED_CASES:
        if case.tier is not Tier.GOLDEN:
            continue
        terms = case.terms.model_copy(deep=True) if case.terms else DealTerms()
        if case.supplied_coords is not None:
            terms.latitude, terms.longitude = case.supplied_coords
        state = DealState(
            raw_listing_text=case.listing or f"[golden fixture: {case.key}]",
            deal_terms=terms,
        )
        with _case_environment(case, False):
            out = build_graph().invoke(
                state,
                {"configurable": {"thread_id": f"gap-{case.key}-{uuid4().hex[:8]}"}},
            )
        estimate = out.get("rent_estimate")
        resolved = out.get("deal_terms")
        stated = list(resolved.unit_rents) if resolved and resolved.unit_rents else []
        if not estimate or not stated:
            continue
        mean_stated = sum(stated) / len(stated)
        kinds = {f.kind.value for f in out.get("flags", [])}
        rows.append(
            {
                "key": case.key,
                "terms_id": id(case.terms),
                "stated": mean_stated,
                "modelled": estimate,
                "gap": (mean_stated - estimate) / estimate,
                "causes": sorted(kinds & set(SPECIFIC_CAUSES)),
            }
        )
    rows.sort(key=lambda r: -r["gap"])
    # **De-duplicated on the fixture, not on the case.** Two cases can share one
    # `DealTerms` object — `la-stale-rent-index` is `la-ordinary-duplex` run against an
    # index pinned to an old observation, so the listing and its stated rents are
    # identical and only an injected fault differs. Counting both would enter one
    # observation twice and tighten the distribution for free. Keyed on the terms object
    # itself rather than on the numbers, so a fault that *did* move the estimate would
    # still be recognised as the same underlying listing.
    first_seen: dict[int, str] = {}
    kept, dropped = [], []
    for row in rows:
        origin = first_seen.get(row["terms_id"])
        if origin is None:
            first_seen[row["terms_id"]] = row["key"]
            kept.append(row)
        else:
            row["duplicate_of"] = origin
            dropped.append(row)
    return kept, dropped


def _summarize(gaps: list[float]) -> str:
    ordered = sorted(gaps)
    middle = len(ordered) // 2
    median = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2
    )
    return (
        f"n = {len(gaps)} · mean {sum(gaps) / len(gaps):+.1%} · median {median:+.1%} · "
        f"range {min(gaps):+.1%} to {max(gaps):+.1%}"
    )


def section_one() -> None:
    print("=" * 96)
    print("1. THE FIXTURE DISTRIBUTION, AND WHETHER A THRESHOLD WOULD DISCRIMINATE")
    print("=" * 96)
    rows, dropped = _fixture_gaps()
    print(f"{'fixture':<30}{'stated':>10}{'modelled':>11}{'gap':>9}   causes already disclosed")
    print("-" * 96)
    for r in rows:
        print(
            f"{r['key']:<30}{r['stated']:>10,.0f}{r['modelled']:>11,.0f}{r['gap']:>+9.1%}"
            f"   {', '.join(r['causes']) or '(none)'}"
        )
    print()
    for row in dropped:
        print(f"excluded: {row['key']} is the same listing as {row['duplicate_of']} with "
              f"a fault injected ({row['gap']:+.1%}) — one observation, not two.")
    print(_summarize([r["gap"] for r in rows]))
    print()
    print("Firing behavior, per candidate threshold. **The last column is the finding.**")
    print(f"{'threshold':>10}{'fires on':>10}{'of which already explained':>30}")
    for threshold in CANDIDATE_THRESHOLDS:
        firing = [r for r in rows if abs(r["gap"]) > threshold]
        explained = [r for r in firing if r["causes"]]
        print(f"{threshold:>10.0%}{len(firing):>10}{f'{len(explained)} of {len(firing)}':>30}")
    print()


def _address_of(deal: DemoDeal) -> tuple[str, str, str, str | None]:
    """The listing's address, parsed the way `verify_demo_calibration.py` parses it."""
    head = deal.listing.split(".")[0].replace("For sale:", "").strip()
    parts = [p.strip() for p in head.split(",")]
    state_zip = parts[2].split()
    return parts[0], parts[1], state_zip[0], (state_zip[1] if len(state_zip) > 1 else None)


def _stated_unit(deal: DemoDeal) -> tuple[int, float, float] | None:
    """The unit spec the listing states, for the bedroom count its rent basis names.

    Every demo deal with a rent basis states one unit type across its units, so a single
    spec describes the whole building. Read off `rent_basis` and the listing text rather
    than re-running the Extractor: this script is asking what the *anchor* would do, and a
    model call would add a source of variation that has nothing to do with the question.
    """
    if deal.rent_basis is None or not deal.unit_rents:
        return None
    source, _, bedrooms = deal.rent_basis.partition(":")
    if source != "hud_fmr":
        return None
    # Bathrooms and floor area as the listings state them; every one of these is a
    # 1-bathroom unit and they differ only in size.
    square_feet = 900.0 if "900 sq ft" in deal.listing else 950.0
    return int(bedrooms), 1.0, square_feet


def section_two() -> None:
    print("=" * 96)
    print("2. WOULD RE-CALIBRATING THE DEMO DEALS TO THE MARKET INDEX ADD OBSERVATIONS?")
    print("=" * 96)
    client = hud_fmr.HudFmrClient()
    bundle = rent_model.load()
    fiscal_year = rent_model.fmr_fiscal_year(pd.Timestamp.now())

    rows = []
    for deal in DEMO_DEALS.values():
        unit = _stated_unit(deal)
        if unit is None:
            continue
        bedrooms, bathrooms, square_feet = unit
        street, city, state, zip_code = _address_of(deal)
        geo = geocoding.geocode(street, city, state, zip_code)
        if geo is None:
            continue
        fips = county_crosswalk.lookup_county_fips(geo.latitude, geo.longitude)
        if fips is None:
            continue
        subject_zip = zip_code or zcta_crosswalk.lookup_zcta(geo.latitude, geo.longitude)

        tables = rent_model.build_anchor_tables({(fips, fiscal_year)}, client)
        month = zori.latest_month(tables.zori_panel)
        market_anchor, tier = rent_model.anchor_for_row(
            bedrooms, fips, fiscal_year, month, subject_zip, tables
        )
        ratio = rent_model.predict_ratio(bundle, bedrooms, bathrooms, square_feet)
        modelled = ratio * market_anchor
        stated = sum(deal.unit_rents) / len(deal.unit_rents)
        rows.append(
            {
                "key": deal.key,
                "zip": subject_zip,
                "tier": tier,
                "fmr": float(client.get_fmr_for_bedroom(fips, bedrooms)["rent"]),
                "market": market_anchor,
                "ratio": ratio,
                "modelled": modelled,
                "stated": stated,
                "gap_committed": (stated - modelled) / modelled,
                # A rent calibrated *to* the market anchor is the anchor, so its gap is
                # `1/ratio - 1` and nothing else. Computed rather than asserted.
                "gap_recalibrated": (market_anchor - modelled) / modelled,
            }
        )

    print(f"Market index read at {month}; FMR schedule FY{fiscal_year}.\n")
    print(
        f"{'deal':<16}{'ZIP':>7}{'tier':>8}{'FMR':>8}{'market':>9}{'ratio':>8}"
        f"{'modelled':>10}{'stated':>9}{'gap now':>10}{'if recal':>10}"
    )
    print("-" * 96)
    for r in rows:
        print(
            f"{r['key']:<16}{r['zip']:>7}{r['tier']:>8}{r['fmr']:>8,.0f}{r['market']:>9,.0f}"
            f"{r['ratio']:>8.3f}{r['modelled']:>10,.0f}{r['stated']:>9,.0f}"
            f"{r['gap_committed']:>+10.1%}{r['gap_recalibrated']:>+10.1%}"
        )
    print()
    print(f"as committed (hud_fmr:2)     {_summarize([r['gap_committed'] for r in rows])}")
    print(f"re-calibrated to the index   {_summarize([r['gap_recalibrated'] for r in rows])}")
    print()
    print(
        "**Read the last column as a shape, not as a level.** A stated rent set equal to\n"
        "the market anchor makes the gap `1/ratio - 1` by construction, so it measures the\n"
        "model's predicted ratio and carries no information about the property. Deals\n"
        "sharing a unit spec return the identical figure. The six observations this path\n"
        "was expected to add are not independent of the estimate they would be compared to."
    )


def main() -> None:
    section_one()
    section_two()
    print()
    print(f"Shipped: RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD = "
          f"{config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD}")


if __name__ == "__main__":
    main()
