"""Coordinate → ZIP (ZCTA), so a rent figure can be anchored below the county.

**Why this exists.** `tools/model/rent_model.py` learns rent as a ratio to the local HUD
Fair Market Rent, and `agents/valuation_rent.py` multiplies that ratio by the FMR for the
subject's own area. Until Aug 22, 2026 "local area" meant *county*, which put a hard floor
under the estimate's spatial resolution: `config.RENT_MODEL_FEATURES` deliberately carries
no market identifier, so the FMR anchor is the **only** channel through which location
enters a rent estimate at all. A county-level anchor therefore meant the system could not
represent neighborhood variation of any kind.

That was measurable and large. HUD publishes Small Area FMRs (SAFMR) — a separate schedule
per ZIP — for 9 of the 15 counties in the training set, covering 94.4% of its rows, and
within a single county those ZIP schedules span roughly 2x:

    Cook (Chicago)        370 ZIPs   $1,170-$2,670   vs county-wide $1,781
    Los Angeles           474 ZIPs   $2,070-$4,350   vs county-wide $2,903
    Cuyahoga (Cleveland)  126 ZIPs     $970-$1,920   vs county-wide $1,279

The measured neighborhood effects the county anchor was blind to (+5.1% / +40.1% / +66.2%
in Echo Park, Logan Square and Ohio City) sit well inside that range, so the resolution to
close the gap is available in an API this project already calls and already caches.

**Why a polygon join rather than reading a ZIP off the coordinate.** A coordinate is
precise, but it does not *contain* a ZIP: a lat/long is a position, a ZIP is an
administrative label assigned to an area, and going from one to the other requires a
mapping from regions of space to labels. Since ZIPs cover areas, that mapping is a set of
shapes. This is the identical operation `tools/county_crosswalk.py` performs for counties
and it involves no projection change — point and polygon are both WGS84 already. The
alternatives lose on the tradeoff that module already settled: a reverse-geocoding call per
point is fine for one subject and not for 5,688 training rows, and a ZIP-centroid table
with nearest-match misassigns every point near a boundary.

**Three approximations, each of which the caller must be able to see.**

1. **ZCTA is not ZIP.** USPS ZIP codes are collections of mail *delivery routes*, not
   areas, and USPS publishes no polygons at all. Census publishes ZIP Code Tabulation
   Areas, which approximate them by assigning each census block its most common ZIP. Most
   match; PO-box-only ZIPs have no ZCTA whatsoever. HUD's SAFMR is keyed on real ZIPs, so
   a ZCTA lookup can miss a ZIP that genuinely exists.
2. **The boundary file is 2020 vintage** (Census stopped publishing generalized ZCTA
   cartographic boundaries after that release; GENZ2021-2023 have no ZCTA layer). ZCTA
   boundaries move slowly, but a ZIP created since 2020 will not resolve.
3. **A coordinate is only as good as what produced it.** 92% of the rent corpus carries a
   city-area placeholder rather than a street address (§2), so for those rows this resolves
   the *placeholder's* ZIP. That still adds real resolution inside a large county — a
   placeholder in Long Beach and one in Santa Monica land in different ZIPs — but it is not
   a claim about the individual property, and nothing downstream should treat it as one.

**A miss is cheap by design, which is why there is no nearest-ZCTA tolerance here.**
`tools/county_crosswalk.py` snaps to the nearest county within five miles because a county
miss means no estimate at all. A ZCTA miss means the caller falls back to the county
schedule it would have used anyway, so guessing at a boundary buys nothing and costs
precision that would look real. `None` here means "use the county anchor," not "failure."
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import Point

# Generalized (1:500,000) rather than full-resolution TIGER/Line, matching the county
# file's reasoning: "which ZIP contains this point" does not need parcel-level boundary
# precision, and the generalized file is 67 MB against roughly 800 MB.
#
# GENZ2020 rather than GENZ2023 because Census publishes no ZCTA layer in the 2021-2023
# cartographic releases — verified by listing the directories, not assumed.
CENSUS_ZCTA_BOUNDARIES_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip"
)

# Computed directly rather than via `import config`, matching tools/county_crosswalk.py
# and tools/hud_fmr.py: this module is runnable standalone, and from that entry point
# `tools/` is on sys.path but `src/` is not.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CACHE_PATH = _REPO_ROOT / "data" / "raw" / "census_zcta_boundaries.zip"

# The 2020 ZCTA layer names its identifier column with the vintage suffix.
_GEOID_COLUMN = "GEOID20"

_zctas_cache: Optional[gpd.GeoDataFrame] = None


def _zctas() -> gpd.GeoDataFrame:
    """Lazy-loaded, cached ZCTA boundary GeoDataFrame.

    Downloaded once to `data/raw/` (gitignored, like every other pulled dataset here) and
    read from disk afterwards. Same reasoning as `county_crosswalk._counties`, with more
    force: this file is 67 MB, so re-fetching it per subject property would put a
    substantial download on the valuation critical path for no benefit.
    """
    global _zctas_cache
    if _zctas_cache is not None:
        return _zctas_cache

    if not _CACHE_PATH.exists():
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(CENSUS_ZCTA_BOUNDARIES_URL, timeout=300)
        response.raise_for_status()
        _CACHE_PATH.write_bytes(response.content)

    _zctas_cache = gpd.read_file(_CACHE_PATH)
    return _zctas_cache


def zcta_from_point(latitude: float, longitude: float) -> Optional[str]:
    """Resolve one coordinate to a 5-digit ZCTA, or `None` if it falls in none.

    `None` is an ordinary outcome, not an error — see the module docstring on why there
    is no nearest-ZCTA tolerance.
    """
    zctas = _zctas()
    match = zctas[zctas.contains(Point(longitude, latitude))]
    if match.empty:
        return None
    return str(match.iloc[0][_GEOID_COLUMN])


def zctas_for_points(
    latitudes: "list[float]", longitudes: "list[float]"
) -> "list[Optional[str]]":
    """Batch form, for callers resolving thousands of rows.

    Same shape and the same reasoning as `county_crosswalk.county_fips_for_points`, whose
    docstring records the measurement: `sjoin` has a fixed setup cost that only amortizes
    above a few hundred points, so the per-point function is genuinely faster below that.
    This file has roughly 33,000 polygons against the county file's 3,200, which moves the
    crossover down rather than up.

    Unlike the county version there is no per-point fallback for unmatched rows, because
    there is no tolerance path to fall back *to*: an unmatched point is `None` in both
    functions, so the two cannot disagree.

    Returns a list positionally aligned with the inputs.
    """
    zctas = _zctas()
    points = gpd.GeoDataFrame(
        {"_row": range(len(latitudes))},
        geometry=[Point(lon, lat) for lat, lon in zip(latitudes, longitudes)],
        crs=zctas.crs,
    )
    joined = gpd.sjoin(points, zctas, how="left", predicate="within")
    # A point on a shared ZCTA border matches both polygons. Keep the first, for the same
    # reason the county join does: the alternative is an arbitrary tie-break presented as
    # a decision.
    joined = joined[~joined["_row"].duplicated(keep="first")]

    resolved: "list[Optional[str]]" = [None] * len(latitudes)
    for row_idx, geoid in zip(joined["_row"], joined.get(_GEOID_COLUMN)):
        if geoid is None or (isinstance(geoid, float) and geoid != geoid):
            continue
        resolved[row_idx] = str(geoid)
    return resolved


def lookup_zcta(
    latitude: Optional[float], longitude: Optional[float]
) -> Optional[str]:
    """`None`-tolerant single-point entry point, mirroring
    `county_crosswalk.lookup_county_fips`. A subject or comp with no coordinate resolves
    to no ZCTA and falls back to its county anchor.
    """
    if latitude is None or longitude is None:
        return None
    return zcta_from_point(latitude, longitude)
