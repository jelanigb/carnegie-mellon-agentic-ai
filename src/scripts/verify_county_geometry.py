"""Verification for the Aug 15, 2026 rewrite of tools/county_crosswalk.py: from a
hand-maintained (city, state) -> FIPS table to a point-in-polygon geometric join.

Two things are checked, both against live data rather than trusted on sight:

1. Every entityid this module derives from a coordinate actually exists in HUD's own
   `listCounties` response for that state, and names the county we expect. This is the
   same discipline the old crosswalk's `verify_against_hud()` applied to hand-typed FIPS
   codes; the numbers here aren't hand-typed, but "the geometry says GEOID X" and "HUD
   recognizes GEOID X as a real, correctly-named county" are still two different claims,
   and only a live call proves the second one.
2. The specific cases the rewrite was justified on are still true: the inference trio
   matches the old table's hand-verified entityids exactly, the two cities the old table
   had to hand-special-case (Richmond VA's independent-city status, Denver's consolidated
   city-county) resolve correctly with no special code, a point with no old-table entry
   at all (Miami) resolves anyway, and a New England point correctly declines rather than
   producing a wrong entityid.

Run: .venv/bin/python scripts/verify_county_geometry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import county_crosswalk  # noqa: E402
from tools.hud_fmr import HudFmrClient  # noqa: E402

# label -> (lat, lon, postal_state, expected_entityid_or_None, expected_hud_county_name)
# `postal_state` is only for the HUD `listCounties` call, which takes a postal
# abbreviation ("IL"), not the numeric FIPS prefix embedded in the entityid ("17") —
# the two look similar enough to conflate, so it's passed explicitly rather than sliced
# out of the entityid below.
CASES = {
    "Chicago, IL (inference trio)": (41.8781, -87.6298, "IL", "1703199999", "Cook County"),
    "Los Angeles, CA (inference trio)": (34.0522, -118.2437, "CA", "0603799999", "Los Angeles County"),
    "Cleveland, OH (inference trio)": (41.4993, -81.6944, "OH", "3903599999", "Cuyahoga County"),
    "Miami, FL (no old-table entry existed)": (25.8023, -80.2012, "FL", "1208699999", "Miami-Dade County"),
    "Richmond city, VA (independent city)": (37.5407, -77.4360, "VA", "5176099999", "Richmond city"),
    "Denver, CO (consolidated city-county)": (39.7392, -104.9903, "CO", "0803199999", "Denver County"),
    "Boston, MA (New England — must be None)": (42.3601, -71.0589, "MA", None, None),
}


def main() -> None:
    client = HudFmrClient()
    hud_counties_by_state: dict[str, dict[str, str]] = {}

    print(f"{'case':<45} {'derived':<13} {'expected':<13} {'HUD name':<20} ok")
    print("-" * 100)

    all_ok = True
    for label, (lat, lon, postal_state, expected_entityid, expected_name) in CASES.items():
        derived = county_crosswalk.lookup_county_fips(lat, lon)

        if expected_entityid is None:
            ok = derived is None
            hud_name = "-"
        else:
            if postal_state not in hud_counties_by_state:
                hud_counties_by_state[postal_state] = {
                    row["fips_code"]: row["county_name"]
                    for row in client.list_counties(postal_state)
                }
            hud_name = hud_counties_by_state[postal_state].get(derived, "NOT FOUND")
            ok = derived == expected_entityid and hud_name == expected_name

        all_ok &= ok
        print(
            f"{label:<45} {str(derived):<13} {str(expected_entityid):<13} "
            f"{hud_name:<20} {'OK' if ok else 'MISMATCH'}"
        )

    print()
    print("All checks passed." if all_ok else "SOME CHECKS FAILED — see MISMATCH rows above.")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
