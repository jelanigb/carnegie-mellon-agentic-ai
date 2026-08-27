"""Check every figure in `demo_deals.py` against the live source it claims to come from.

    .venv/bin/python scripts/verify_demo_calibration.py

The demo listings are synthetic, and until Aug 16, 2026 their numbers were also
arbitrary — plausible figures chosen to look reasonable, with nothing recording why. That
is a poor foundation for fixtures whose reports appear in the write-up and the demo
video, where a reader cannot distinguish a market-derived number from an invented one.

Each deal now names the basis for its figures and this script re-derives them:

- **Asking price** against `tools/redfin_data.py`'s median sale price for Multi-Family
  (2-4 unit) properties in the named metro, most recent period available.
- **Stated rents** against `tools/hud_fmr.py`'s FY2026 Fair Market Rent for the county
  the listing's *own address* geocodes to — so the check exercises the same geocoding and
  county-resolution path the pipeline uses, rather than a county name written down here.

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
from tools import county_crosswalk, geocoding, hud_fmr, redfin_data


def _redfin_median(metro: str) -> float | None:
    df = redfin_data.load_redfin()
    rows = df[df["metro"] == metro].sort_values("period")
    if rows.empty:
        return None
    return float(rows.iloc[-1]["median_sale_price"])


def _resolve_county(deal: DemoDeal) -> tuple[str | None, str]:
    """Geocode the listing's address the way the pipeline does, then resolve its county.

    Deliberately re-runs the real lookups rather than accepting a county written into the
    fixture: a calibration that trusted a hand-entered county would keep passing after
    the geocoder started placing the address somewhere else.
    """
    # The address is the first sentence's tail — parsed loosely on purpose, since this is
    # a verification script and a brittle parse here would fail for its own reasons.
    head = deal.listing.split(".")[0].replace("For sale:", "").strip()
    parts = [p.strip() for p in head.split(",")]
    if len(parts) < 3:
        return None, "could not parse an address out of the listing"

    street, city = parts[0], parts[1]
    state_zip = parts[2].split()
    state = state_zip[0]
    zip_code = state_zip[1] if len(state_zip) > 1 else None

    result = geocoding.geocode(street, city, state, zip_code)
    if result is None:
        return None, "address resolves to no coordinates"
    fips = county_crosswalk.lookup_county_fips(result.latitude, result.longitude)
    if fips is None:
        return None, f"{result.source} gave coordinates, but no county resolved"
    return fips, f"{result.source} -> county {fips}"


def check_price(deal: DemoDeal) -> list[str]:
    if deal.price_basis is None:
        return [f"  price      ${deal.price:>12,.0f}   NO BASIS — {deal.notes or 'stated as unanchored'}"]

    source, _, metro = deal.price_basis.partition(":")
    if source != "redfin_metro_median":
        return [f"  price      UNKNOWN BASIS {deal.price_basis!r}"]

    median = _redfin_median(metro)
    if median is None:
        return [f"  price      FAIL — Redfin extract has no metro {metro!r}"]

    drift = (deal.price - median) / median
    # A deal may declare a deliberate premium over its basis. The check is then whether
    # the price still sits where the deal *says* it sits — the provenance is the claim
    # being verified, and an intentional offset is part of the claim rather than a
    # failure of it.
    expected = deal.price_premium_to_basis or 0.0
    verdict = "ok" if abs(drift - expected) <= PRICE_TOLERANCE else "OUT OF TOLERANCE"
    against = (
        f"   (declared {expected:+.0%} premium)" if deal.price_premium_to_basis else ""
    )
    return [
        f"  price      ${deal.price:>12,.0f}   vs Redfin {metro} median "
        f"${median:,.0f}   {drift:+.1%}{against}   {verdict}"
    ]


def check_rents(deal: DemoDeal) -> list[str]:
    if deal.rent_basis is None:
        if deal.unit_rents:
            return ["  rents      FAIL — rents stated with no basis recorded"]
        return ["  rents      none stated, no basis claimed — consistent"]

    source, _, bedrooms = deal.rent_basis.partition(":")
    if source != "hud_fmr":
        return [f"  rents      UNKNOWN BASIS {deal.rent_basis!r}"]

    fips, how = _resolve_county(deal)
    if fips is None:
        return [f"  rents      FAIL — {how}"]

    client = hud_fmr.HudFmrClient()
    fmr = client.get_fmr_for_bedroom(fips, int(bedrooms))
    anchor = float(fmr["rent"])

    lines = [f"  rents      basis: {how}, FY{fmr['year']} {bedrooms}BR FMR ${anchor:,.0f}"]
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
