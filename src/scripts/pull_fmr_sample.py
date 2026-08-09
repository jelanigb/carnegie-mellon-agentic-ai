"""Smoke test for tools/hud_fmr.py: real pulls (not mocked) against the live HUD
FMR API for the three candidate metros, across a Kaggle-vintage year and the
current year, to prove auth, both response shapes, and caching all work.

Run: .venv/bin/python scripts/pull_fmr_sample.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.hud_fmr import HudFmrClient  # noqa: E402

CANDIDATE_COUNTIES = [
    ("NY", "New York County"),
    ("IL", "Cook County"),
    ("PA", "Philadelphia County"),
]
KAGGLE_VINTAGE_YEAR = 2019


def find_entityid(client: HudFmrClient, state_code: str, county_name: str) -> str:
    counties = client.list_counties(state_code)
    match = next(c for c in counties if c["county_name"] == county_name)
    return match["fips_code"]


def main() -> None:
    client = HudFmrClient()

    print(f"{'county':<24} {'entityid':<12} {'year':<6} {'safmr':<7} {'msa_fallback':<13} 2BR rent")
    for state_code, county_name in CANDIDATE_COUNTIES:
        entityid = find_entityid(client, state_code, county_name)

        for year in (KAGGLE_VINTAGE_YEAR, None):
            result = client.get_fmr(entityid, year=year)
            two_br = result.rents.get("Two-Bedroom")
            print(
                f"{county_name:<24} {entityid:<12} {result.year:<6} "
                f"{str(result.is_safmr):<7} {str(result.used_msa_fallback):<13} ${two_br}"
            )

    print("\nRe-running the same query to confirm cache hit (should be instant, no HTTP call)...")
    start = time.monotonic()
    entityid = find_entityid(client, "IL", "Cook County")
    client.get_fmr(entityid, year=None)
    elapsed = time.monotonic() - start
    print(f"Second call took {elapsed:.3f}s (cache hit if well under the 1s rate-limit floor)")


if __name__ == "__main__":
    main()
