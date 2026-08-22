"""Resolves `DealTerms.county_fips` from a subject property's coordinates.

Replaced Aug 15, 2026 — from a hand-maintained table to a spatial join
------------------------------------------------------------------------
This module originally hand-maintained a `(cityname, state) -> county FIPS` table for a
29-city shortlist, each entry verified against a live HUD `listCounties` response (see
git history / docs/changelog.md for that version). Once `tools/geocoding.py` existed to
put a subject property at a real coordinate (decision #10), that table became strictly
dominated by a geometric point-in-polygon join against the same coordinate:

- It needs no per-city curation and covers every US county, not a hand-picked shortlist —
  it resolved Miami-Dade County correctly for a Miami-area point the old table had no
  entry for at all.
- It resolves the *exact* county for a point rather than the old table's "principal
  county" approximation for cities spanning several (Chicago, Dallas, Houston, ...).
- It reproduces the old table exactly everywhere both apply: verified directly against
  all three inference-trio metros (entityids matched digit-for-digit) and against the old
  table's two hand-special-cased hard cases — Richmond, VA's independent-city status and
  Denver's consolidated city-county — both resolve correctly via geometry with no special
  code, because Census's own county-equivalent boundaries already represent them that way.

Trade-off: this only runs once a subject has coordinates, so a listing with a known city
but no resolvable geocode now gets no `county_fips` either, where the old table could
resolve one from the city string alone. Given `vector_store.query_comps` already
hard-requires coordinates for comp retrieval, a coordinate-less subject was already the
system's worst case; this removes one of the two things it can still get from geometry
disconnected from geocoding, not one of the two paths that mattered independently.

`normalize_city`/`normalize_state` are kept as-is — `tools/geocoding.py`'s corpus-centroid
fallback still keys on (city, state) strings from the Kaggle corpus and needs to fold them
identically, which has nothing to do with how county resolution works.

New England — explicitly out of scope, not silently wrong
------------------------------------------------------------
HUD defines FMR areas by *town*, not county, in six New England states (CT, ME, MA, NH,
RI, VT); Boston's own entityid is a place FIPS (`2502507000`, town regime) rather than the
county-level `<state><county>99999` pattern every other state uses. A plain county polygon
join can name the correct *county* there (verified: a Boston point resolves to Suffolk
County) but cannot produce the entityid HUD actually expects. `lookup_county_fips` detects
a resolved point landing in one of those six states and returns `None` rather than a wrong
entityid — the same "decline rather than guess" discipline `tools/geocoding.py` applies to
an uncovered city.

TODO(geography): building the town/place-level boundary layer this would need is future
work, not started. Same status the old table already carried for New England (verified for
Boston only, by a live HUD call rather than geometry — see git history). Whoever picks this
up should use Census's *county subdivision* (New England towns are county subdivisions,
not places) boundary file, keyed the same way as `_counties()` below, and branch on the
six-state set already named in `_NEW_ENGLAND_STATEFP`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import Point

_WHITESPACE = re.compile(r"\s+")

CENSUS_COUNTY_BOUNDARIES_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
)
# Computed directly rather than via `import config`, matching tools/hud_fmr.py: this
# module is meant to be runnable standalone (`python tools/county_crosswalk.py`), and
# from that entry point `tools/` is on sys.path but `src/` is not, so `import config`
# fails there even though it works fine when imported as `tools.county_crosswalk`.
_REPO_ROOT = Path(__file__).resolve().parents[2]

# Cartographic boundary file (1:500,000, generalized) rather than full-resolution
# TIGER/Line — "which county contains this point" doesn't need parcel-level boundary
# precision, and the generalized file is a fraction of the size (~12 MB vs. ~1.7 GB).
_CACHE_PATH = _REPO_ROOT / "data" / "raw" / "census_county_boundaries.zip"

# HUD defines FMR areas by *town*, not county, in these six states — see the module
# docstring. STATEFP values: CT 09, ME 23, MA 25, NH 33, RI 44, VT 50.
_NEW_ENGLAND_STATEFP = {"09", "23", "25", "33", "44", "50"}

# A geocoded point can fall just outside a county polygon at this file's 1:500,000
# generalization — typically a coastline drawn slightly inland of the true edge. A real
# estate address is on land by construction, so snapping to the nearest county within a
# small tolerance is safe; beyond it, something is actually wrong (bad coordinates) and
# this should surface as a miss rather than a guess. Not observed to trigger in testing
# (Staten Island and Miami Beach shoreline points both resolved on an exact match), kept
# as a documented safety net rather than removed, since it costs one `.distance()` call
# only on the rare path where the exact match already failed.
_NEAREST_COUNTY_MAX_MILES = 5.0
# Degrees-to-miles is a rough conversion (ignores the longitude/latitude compression
# `tools/vector_store.py`'s haversine handles exactly), which is fine here: this number
# only gates whether a near-miss is trusted, not a distance reported to a user.
_APPROX_MILES_PER_DEGREE = 69.0


def normalize_city(cityname: str) -> str:
    """Fold a city name to a comparison key.

    Kaggle's `cityname` values are free text from listing feeds, so casing and
    punctuation vary ("St. Louis" / "St Louis", trailing whitespace). Periods and
    repeated whitespace are the two variations actually observed; both are removed
    rather than attempting broader fuzzy matching, which would risk false positives
    between genuinely different cities.

    Public (not prefixed) because `tools/geocoding.py`'s corpus-centroid fallback keys
    into the same corpus and must fold names identically — a drift between two
    independent normalizers would show up as silent lookup misses, not an error.
    """
    folded = cityname.strip().lower().replace(".", "")
    return _WHITESPACE.sub(" ", folded)


def normalize_state(state: str) -> str:
    return state.strip().upper()


_counties_cache: Optional[gpd.GeoDataFrame] = None


def _counties() -> gpd.GeoDataFrame:
    """Lazy-loaded, cached county boundary GeoDataFrame.

    Downloaded once to `data/raw/` (gitignored, same as every other pulled dataset in
    this project) and read from disk on every call after that — county boundaries don't
    change mid-project, so there is nothing to invalidate the cache against. Without
    this, every subject property would re-download an ~12 MB file from Census, which
    is real added latency and a real network dependency on the comp-retrieval critical
    path for no benefit over reading a local file.
    """
    global _counties_cache
    if _counties_cache is not None:
        return _counties_cache

    if not _CACHE_PATH.exists():
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(CENSUS_COUNTY_BOUNDARIES_URL, timeout=60)
        response.raise_for_status()
        _CACHE_PATH.write_bytes(response.content)

    _counties_cache = gpd.read_file(_CACHE_PATH)
    return _counties_cache


def _entityid_from_geoid(geoid: str) -> str:
    """HUD's county-level `entityid` is state FIPS + county FIPS + a "99999" county
    placeholder. Verified against all three inference-trio counties, plus Richmond VA's
    independent-city GEOID and Denver's consolidated city-county GEOID, before this
    module was rewritten to rely on it — see the module docstring.
    """
    return f"{geoid}99999"


def county_fips_from_point(latitude: float, longitude: float) -> Optional[str]:
    """Resolve a coordinate to a HUD county `entityid` via exact point-in-polygon
    geometry against Census's county boundaries.

    Returns `None` for a New England point (module docstring — the entityid pattern
    this function produces is wrong there, not merely approximate) or a point that
    doesn't resolve to any US county, including one outside every polygon by more than
    `_NEAREST_COUNTY_MAX_MILES`.
    """
    counties = _counties()
    point = Point(longitude, latitude)

    match = counties[counties.contains(point)]
    if match.empty:
        distances = counties.geometry.distance(point)
        nearest_idx = distances.idxmin()
        nearest_miles = distances[nearest_idx] * _APPROX_MILES_PER_DEGREE
        if nearest_miles > _NEAREST_COUNTY_MAX_MILES:
            return None
        match = counties.loc[[nearest_idx]]

    row = match.iloc[0]
    if row["STATEFP"] in _NEW_ENGLAND_STATEFP:
        return None
    return _entityid_from_geoid(row["GEOID"])


def county_fips_for_points(
    latitudes: "list[float]", longitudes: "list[float]"
) -> "list[Optional[str]]":
    """Batch form of `county_fips_from_point`, for callers resolving thousands of rows.

    Added in U5, where the rent regression must resolve a county for every training row
    so its rent can be normalized against that row's own local FMR.

    **Measured, because the obvious reasoning about why was wrong.** The expected
    justification was that `counties.contains(point)` scans ~3,200 polygons per call
    with no spatial index, making the per-point path quadratic-ish in aggregate. That
    mechanism does not hold: shapely 2.0 vectorizes `contains`, so a single call is
    already fast, and at n=120 the per-point loop *beat* this function 0.05s to 0.72s —
    `sjoin` has fixed setup cost that small inputs never amortize. The batch form earns
    its place only at U5's actual scale, where the fixed cost is paid once: **5,717 rows
    resolve in 0.03s here against 2.51s per-point, a 90x difference, with zero
    disagreement between the two paths across all 5,717.**

    So: use this above a few hundred points, and `county_fips_from_point` below that.
    The crossover is real and in the low hundreds, not a rounding detail.

    **Semantics are identical to the per-point function, deliberately.** The fast path
    handles exact containment; any point the join leaves unmatched falls through to
    `county_fips_from_point` itself, which applies the nearest-county tolerance. So the
    tolerance path, New England exclusion, and the `None` contract are shared code
    rather than reimplemented here — a second implementation that drifted from the first
    would produce a training set whose counties disagree with the ones resolved at
    inference time, which is the kind of mismatch that produces a plausible-looking
    model that is wrong in a way no test would catch.

    Returns a list positionally aligned with the inputs; `None` at a position means the
    same thing it means for a single point.
    """
    counties = _counties()

    points = gpd.GeoDataFrame(
        {"_row": range(len(latitudes))},
        geometry=[Point(lon, lat) for lat, lon in zip(latitudes, longitudes)],
        crs=counties.crs,
    )
    joined = gpd.sjoin(points, counties, how="left", predicate="within")
    # A point on a shared county border matches both polygons and yields two rows.
    # Keep the first: the alternative is an arbitrary tie-break dressed up as a choice,
    # and the two counties' FMRs are what actually differ, not the point's location.
    joined = joined[~joined["_row"].duplicated(keep="first")]

    resolved: "list[Optional[str]]" = [None] * len(latitudes)
    for row_idx, statefp, geoid in zip(
        joined["_row"], joined.get("STATEFP"), joined.get("GEOID")
    ):
        if geoid is None or (isinstance(geoid, float) and geoid != geoid):
            # Unmatched by the join — defer to the per-point path for its tolerance.
            resolved[row_idx] = county_fips_from_point(
                latitudes[row_idx], longitudes[row_idx]
            )
            continue
        if statefp in _NEW_ENGLAND_STATEFP:
            resolved[row_idx] = None
            continue
        resolved[row_idx] = _entityid_from_geoid(geoid)

    return resolved


def lookup_county_fips(
    latitude: Optional[float], longitude: Optional[float]
) -> Optional[str]:
    """Resolve a subject property's coordinates to a HUD county `entityid`, or `None`
    if unresolved — missing coordinates, a point outside every county, or a New England
    point. `agents/extractor.py` is the caller; a `None` here is what eventually raises
    `FlagKind.FMR_UNAVAILABLE_FOR_COUNTY` downstream in the Valuation agent.
    """
    if latitude is None or longitude is None:
        return None
    return county_fips_from_point(latitude, longitude)


def main() -> None:
    """Resolve a handful of known points, for eyeballing rather than automated
    verification — `scripts/verify_county_geometry.py` is the real check, including a
    live HUD cross-check of every entityid this prints.
    """
    samples = {
        "Chicago, IL": (41.8781, -87.6298),
        "Los Angeles, CA": (34.0522, -118.2437),
        "Cleveland, OH": (41.4993, -81.6944),
        "Miami, FL (no hand-maintained entry ever existed for this)": (25.8023, -80.2012),
        "Richmond city, VA (independent city, formerly special-cased)": (37.5407, -77.4360),
        "Denver, CO (consolidated city-county, formerly special-cased)": (39.7392, -104.9903),
        "Boston, MA (New England — should resolve to None)": (42.3601, -71.0589),
        "Missing coordinates": (None, None),
    }
    print(f"{'label':<62} {'entityid':<14}")
    print("-" * 76)
    for label, (lat, lon) in samples.items():
        result = lookup_county_fips(lat, lon)
        print(f"{label:<62} {result or 'None'}")


if __name__ == "__main__":
    main()
