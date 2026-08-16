"""Smoke test for tools/geocoding.py: real calls (not mocked) proving both tiers work
and prove it for the right reason.

Three cases, each targeting a specific path:

1. A real, complete address in each inference-trio metro -> Census Geocoder should
   match directly.
2. A city/state with no street address -> Census has nothing to match, so this should
   fall through to the corpus centroid.
3. A city with no listings in the Kaggle corpus at all -> both tiers should come up
   empty, proving `geocode()` returns None rather than inventing a coordinate.

Run: .venv/bin/python scripts/pull_geocode_sample.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import geocoding  # noqa: E402

# Real street addresses in the inference trio (§2), chosen only to be geocodable —
# no connection to any actual listing or transaction.
CASE_1_FULL_ADDRESS = [
    ("233 S Wacker Dr", "Chicago", "IL", "60606"),
    ("200 N Spring St", "Los Angeles", "CA", "90012"),
    ("601 Lakeside Ave", "Cleveland", "OH", "44114"),
]

# City/state only, no street — Census should find nothing to match against.
CASE_2_CITY_ONLY = ("Chicago", "IL")

# Outside the Kaggle corpus's coverage entirely.
CASE_3_UNCOVERED = ("Nowhereville", "WY")


def main() -> None:
    print("=== Case 1: full address -> Census Geocoder should match directly ===")
    for street, city, state, zip_code in CASE_1_FULL_ADDRESS:
        result = geocoding.geocode_census(street, city, state, zip_code)
        if result is None:
            print(f"  {street}, {city}, {state} {zip_code}: NO MATCH (unexpected)")
        else:
            print(
                f"  {street}, {city}, {state} {zip_code} -> "
                f"({result.latitude:.4f}, {result.longitude:.4f}) "
                f"via {result.source}: {result.matched_address!r}"
            )

    print("\n=== Case 2: city/state only -> Census should return no match, "
          "geocode() should fall back to the corpus centroid ===")
    city, state = CASE_2_CITY_ONLY
    census_only = geocoding.geocode_census(None, city, state)
    print(f"  geocode_census(None, {city!r}, {state!r}) = {census_only!r} "
          f"({'as expected' if census_only is None else 'UNEXPECTED MATCH'})")
    fallback = geocoding.geocode(None, city, state)
    if fallback is None:
        print("  geocode() also returned None (unexpected — the corpus should cover "
              "an inference-trio city)")
    else:
        print(
            f"  geocode(None, {city!r}, {state!r}) -> "
            f"({fallback.latitude:.4f}, {fallback.longitude:.4f}) via {fallback.source}"
        )

    print("\n=== Case 3: city absent from the corpus -> both tiers should come up "
          "empty ===")
    city, state = CASE_3_UNCOVERED
    result = geocoding.geocode(None, city, state)
    print(f"  geocode(None, {city!r}, {state!r}) = {result!r} "
          f"({'as expected' if result is None else 'UNEXPECTED MATCH'})")


if __name__ == "__main__":
    main()
