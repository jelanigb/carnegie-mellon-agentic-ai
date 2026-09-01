"""Check every figure in `demo_deals.py` against the live source it claims to come from.

    .venv/bin/python scripts/verify_demo_calibration.py

The demo listings are synthetic, and until Aug 16, 2026 their numbers were also
arbitrary — plausible figures chosen to look reasonable, with nothing recording why. That
is a poor foundation for fixtures whose reports appear in the write-up and the demo
video, where a reader cannot distinguish a market-derived number from an invented one.

Each deal now names the basis for its figures and this script re-derives them:

- **Asking price** against `tools/redfin_data.py`'s median sale price for Multi-Family
  (2-4 unit) properties in the named metro, most recent period available.
- **Stated rents** against whichever anchor the deal declares, both resolved from the
  listing's *own address* — so the check exercises the same geocoding and
  county-resolution path the pipeline uses, rather than a county name written down here.

  - `hud_fmr:<beds>` — `tools/hud_fmr.py`'s Fair Market Rent for the resolved county.
    What #11 calibrated the original listings against.
  - `market_anchor:<beds>` — **the figure the rent estimate is actually built on today**
    (#19): the market rent index at the subject's own ZIP times FMR's bedroom step,
    composed by `rent_model.anchor_for_row`, the same function training and the Valuation
    agent call. Added U9.6, because a deal declared against the retired anchor ships
    stale on day one (OQ-21).

  **The two are not a fixed offset apart, and a reader should not assume one.** Measured
  Sept 1, 2026 at FY2026 against the index at 2026-07: the schedule runs **7.3% above**
  the market index in ZIP 90026, **13.8% below** it in 60640 and **33.1% below** it in
  60647. `demo_deals.py`'s docstring explains the gap as HUD's 40th percentile running
  under the market, which holds in Chicago and is backwards in Echo Park — where the
  figure returns `used_msa_fallback`, so it describes Los Angeles County rather than any
  sub-market at all.

**What this check could return if the system were misbehaving** (§8). It is not a
formality: it compares committed constants against live API responses that this repo does
not control, so it fails when a figure drifts, when a metro leaves the Redfin extract,
when HUD republishes an FMR, or when an address stops resolving. Two deals are expected
to report NO BASIS rather than a match — `staten-island`'s price (Redfin does not cover
New York) and everything about `no-geography` (an address deliberately resolving
nowhere). Those are assertions about the world, so the script prints them as results
rather than skipping them: if `no-geography` ever acquires a county, the case has stopped
testing what it was built to test.

Tolerances live in `demo_deals.py`. They are wide on price because a specific building
legitimately differs from its metro's median — the question is whether the figure sits in
the neighbourhood of the market, not whether it equals it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_deals import DEMO_DEALS, PRICE_TOLERANCE, RENT_TOLERANCE, DemoDeal
import pandas as pd

from tools import (
    county_crosswalk,
    geocoding,
    hud_fmr,
    redfin_data,
    sale_benchmarks,
    zcta_crosswalk,
    zori,
)
from tools.model import rent_model


def _redfin_median(metro: str) -> float | None:
    df = redfin_data.load_redfin()
    rows = df[df["metro"] == metro].sort_values("period")
    if rows.empty:
        return None
    return float(rows.iloc[-1]["median_sale_price"])


def _resolve_geography(deal: DemoDeal) -> tuple[str | None, str | None, str]:
    """Geocode the listing's address the way the pipeline does, then resolve county and ZIP.

    Deliberately re-runs the real lookups rather than accepting a county written into the
    fixture: a calibration that trusted a hand-entered county would keep passing after
    the geocoder started placing the address somewhere else.

    **The ZIP comes from `zcta_crosswalk.resolve_subject_zip`, the same rule the pipeline
    uses** — the listing's own stated ZIP where there is one, the point-in-polygon join
    otherwise. The market-index half of the anchor is read at that ZIP, so a check that
    resolved it by a rule of its own would verify a figure no report prints. This script
    reproduced that rule for one commit; extracted at U9.6 so it cannot drift.
    """
    # The address is the first sentence's tail — parsed loosely on purpose, since this is
    # a verification script and a brittle parse here would fail for its own reasons.
    head = deal.listing.split(".")[0].replace("For sale:", "").strip()
    parts = [p.strip() for p in head.split(",")]
    if len(parts) < 3:
        return None, None, "could not parse an address out of the listing"

    street, city = parts[0], parts[1]
    state_zip = parts[2].split()
    state = state_zip[0]
    zip_code = state_zip[1] if len(state_zip) > 1 else None

    result = geocoding.geocode(street, city, state, zip_code)
    if result is None:
        return None, None, "address resolves to no coordinates"
    fips = county_crosswalk.lookup_county_fips(result.latitude, result.longitude)
    if fips is None:
        return None, None, f"{result.source} gave coordinates, but no county resolved"
    zcta = zcta_crosswalk.resolve_subject_zip(
        zip_code, result.latitude, result.longitude
    )
    return fips, zcta, f"{result.source} -> county {fips}"


def _hud_fmr_anchor(fips: str, zcta: str | None, bedrooms: int) -> tuple[float, str]:
    """HUD's Fair Market Rent for the resolved county — what #11 calibrated against.

    Retained rather than migrated. Four listings are still declared on it, and U8.7's
    decision to leave their figures as committed is recorded in `demo_deals.py`: nothing
    computes from a stated rent, so a stale basis makes a listing less lifelike without
    making the system wrong. A basis this script could no longer check would be the
    version of that which *does* cost something.
    """
    fmr = hud_fmr.HudFmrClient().get_fmr_for_bedroom(fips, bedrooms)
    return float(fmr["rent"]), f"FY{fmr['year']} {bedrooms}BR FMR"


def _market_anchor(fips: str, zcta: str | None, bedrooms: int) -> tuple[float, str]:
    """The figure the rent estimate is actually built on today (#19, U9.6).

    Composed through `rent_model.anchor_for_row` — the same function the training frame
    and `agents/valuation_rent` both call — rather than reimplemented here, for the reason
    that function's own docstring gives: a model trained against one reference and applied
    against another is wrong by the spread between them, and a *verifier* that computed a
    third reference would hide exactly that. The tier travels with the figure because a
    county-tier anchor is a materially weaker basis for a stated rent than a ZIP-tier one,
    and the two are not distinguishable from the number alone.

    **The bedroom step is exactly 1.0 for every deal in this set, and it is composed
    anyway.** `config.RENT_ANCHOR_SHAPE_REFERENCE_BEDROOMS` is 2 and every demo listing is
    two-bedroom, so the FMR half divides out today. Dropping it would look correct until
    the first deal that is not two-bedroom and be silently wrong from then on.
    """
    client = hud_fmr.HudFmrClient()
    fiscal_year = rent_model.fmr_fiscal_year(pd.Timestamp.now())
    tables = rent_model.build_anchor_tables({(fips, fiscal_year)}, client)
    month = zori.latest_month(tables.zori_panel) if tables.available else None
    if month is None:
        raise LookupError("no market rent index is loaded on this machine")
    anchor, tier = rent_model.anchor_for_row(
        bedrooms, fips, fiscal_year, month, zcta, tables
    )
    if anchor != anchor:  # NaN — neither the ZIP nor the county tier produced a figure
        raise LookupError(
            f"no market index figure for ZIP {zcta} or county {fips} at {month}"
        )
    return anchor, f"{month} market index x FY{fiscal_year} {bedrooms}BR step ({tier} tier)"


# Every rent basis a deal may declare, and how to re-derive it. A table rather than a
# branch so that adding a basis is one entry, and so an unknown basis is reported as
# unknown rather than silently taking the first branch's path.
_RENT_BASES = {
    "hud_fmr": _hud_fmr_anchor,
    "market_anchor": _market_anchor,
}


def check_price(deal: DemoDeal) -> list[str]:
    if deal.price_basis is None:
        return [f"  price      ${deal.price:>12,.0f}   NO BASIS — {deal.notes or 'stated as unanchored'}"]

    source, _, target = deal.price_basis.partition(":")
    if source == "redfin_metro_median":
        median = _redfin_median(target)
        if median is None:
            return [f"  price      FAIL — Redfin extract has no metro {target!r}"]
        against = f"Redfin {target} median"
    elif source == "zip_sale_benchmark":
        # **The tier a deal is calibrated to should be the tier its report reads**
        # (U9.4). `valuation_rent` prefers the ZIP benchmark and falls back to the metro
        # median, so a deal sited in a market with a local tier and calibrated to the
        # metro figure is verified against a number its own report never prints. Read
        # from the committed table rather than the network for the same reason
        # `tools/sale_benchmarks.py` does: a calibration check that depends on a
        # municipal portal being up reports differently depending on the weather.
        benchmark = sale_benchmarks.lookup(target)
        if benchmark is None:
            return [
                f"  price      FAIL — no ZIP benchmark for {target!r} "
                f"({sale_benchmarks.unavailable_reason(target, None)})"
            ]
        median = benchmark.median_sale_price
        against = (
            f"ZIP {target} median (n={benchmark.n_sales:,}, "
            f"{benchmark.market_label})"
        )
    else:
        return [f"  price      UNKNOWN BASIS {deal.price_basis!r}"]

    drift = (deal.price - median) / median
    # A deal may declare a deliberate premium over its basis. The check is then whether
    # the price still sits where the deal *says* it sits — the provenance is the claim
    # being verified, and an intentional offset is part of the claim rather than a
    # failure of it.
    expected = deal.price_premium_to_basis or 0.0
    verdict = "ok" if abs(drift - expected) <= PRICE_TOLERANCE else "OUT OF TOLERANCE"
    declared = (
        f"   (declared {expected:+.0%} premium)" if deal.price_premium_to_basis else ""
    )
    return [
        f"  price      ${deal.price:>12,.0f}   vs {against} "
        f"${median:,.0f}   {drift:+.1%}{declared}   {verdict}"
    ]


def check_rents(deal: DemoDeal) -> list[str]:
    if deal.rent_basis is None:
        if deal.unit_rents:
            return ["  rents      FAIL — rents stated with no basis recorded"]
        return ["  rents      none stated, no basis claimed — consistent"]

    source, _, bedrooms = deal.rent_basis.partition(":")
    if source not in _RENT_BASES:
        return [f"  rents      UNKNOWN BASIS {deal.rent_basis!r}"]

    fips, zcta, how = _resolve_geography(deal)
    if fips is None:
        return [f"  rents      FAIL — {how}"]

    try:
        anchor, against = _RENT_BASES[source](fips, zcta, int(bedrooms))
    except (LookupError, hud_fmr.HudFmrApiError, KeyError, RuntimeError) as exc:
        # Reported as a failure rather than raised, for the same reason the NO BASIS rows
        # are printed rather than skipped: a basis that stopped being resolvable is a
        # result this script exists to surface, and one deal failing should not stop the
        # other seven from being checked.
        return [f"  rents      FAIL — {source} basis unavailable: "
                f"{type(exc).__name__}: {exc}"]

    lines = [f"  rents      basis: {how}, {against} ${anchor:,.0f}"]
    for rent in deal.unit_rents:
        drift = (rent - anchor) / anchor
        verdict = "ok" if abs(drift) <= RENT_TOLERANCE else "OUT OF TOLERANCE"
        lines.append(f"               ${rent:>8,.0f}   {drift:+.1%}   {verdict}")
    return lines


def main() -> None:
    print("=" * 78)
    print("DEMO LISTING CALIBRATION")
    print("=" * 78)
    print(f"Tolerances: price ±{PRICE_TOLERANCE:.0%}, rent ±{RENT_TOLERANCE:.0%}\n")

    failures = 0
    for deal in DEMO_DEALS.values():
        print(f"--- {deal.key} ---")
        for line in check_price(deal) + check_rents(deal):
            print(line)
            if "OUT OF TOLERANCE" in line or "FAIL" in line:
                failures += 1
        print()

    if failures:
        print(f"{failures} figure(s) no longer match their stated basis. Either the "
              f"market moved and the fixtures should be re-calibrated, or a basis is "
              f"wrong.")
        raise SystemExit(1)
    print("All calibrated figures match their stated basis.")


if __name__ == "__main__":
    main()
