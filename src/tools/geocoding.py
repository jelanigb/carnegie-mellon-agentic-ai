"""Resolves `DealTerms.latitude/longitude` — decision #10 in docs/implementation_plan.md §7.

Why this module exists
-----------------------
§5 lists `latitude`/`longitude` as DERIVED "by lookup," but until now no lookup existed:
`tools/county_crosswalk.py` resolves county FIPS only, and `tools/vector_store.py`
hard-requires coordinates to run a radius query at all. A subject property parsed from
listing text — full address, city, state, ZIP — had no path to a point on the map, so
comp retrieval degraded to zero regardless of extraction quality. See the decision-#10
detail in the plan for the full accounting of how the gap sat unnoticed.

Two-tier design, same shape as the county crosswalk
-----------------------------------------------------
1. **Primary: the US Census Bureau's public geocoder** (`geocode_census`). Free, no API
   key, no usage-terms ambiguity (a federal public dataset — unlike Nominatim, whose ToS
   restrict heavy or commercial use). Matches against TIGER/Line address ranges, so a
   hit is accurate to the parcel, not the city.
2. **Fallback: a corpus-derived city centroid** (`city_centroid`), used when the primary
   call fails outright or returns no match. Deliberately not a hand-maintained table —
   the mean lat/lon of a city's own listings in the
   Kaggle corpus is a better-fitted centroid than an arbitrary city-hall point (it sits
   where the comp density actually is, which is what the radius search cares about), and
   it costs no manual curation. It also naturally covers every city the corpus has
   listings for, not just the 29 the county crosswalk hand-verifies. Its accuracy ceiling
   is bounded by construction: this fallback exists only to unblock retrieval for a
   metro the corpus already covers, and if the corpus doesn't cover the subject's city,
   comp retrieval would return nothing useful even with a perfect geocode.

   **Nothing here geocodes the corpus.** Every Kaggle row already carries real, original
   `latitude`/`longitude` — scraped fields, present before this module exists, and
   required by `kaggle_data.CORE_FIELDS` for a row to survive cleaning at all. The only
   thing this module ever geocodes is the *subject* property, once per pipeline run.
   `_city_centroids()` merely averages coordinates the corpus already has, grouped by
   city/state, so `geocode()` has a real fallback location to hand back for the subject
   when Census can't place its street address.

`geocode()` tries (1), then (2), and returns `None` only if both fail — no address text
to work with, or a city absent from the corpus entirely. The caller (the Extractor, once
wired — see the TODO in `agents/extractor.py`) is responsible for turning `.source` into
the right disclosure: a `census_geocoder` result raises no flag, the same asymmetry the
crosswalk already applies to an unambiguous county match; a `city_centroid` result raises
one of two warn-level flags depending on `.primary_unavailable` —
`FlagKind.COORDINATES_FROM_CITY_CENTROID` when the address simply had nothing to resolve
to, or `FlagKind.GEOCODER_SERVICE_UNAVAILABLE` when the Census call could not be made at
all (warn either way — the radius search is exactly where a city-level approximation costs
accuracy, worst in a large metro like Los Angeles, and that cost is identical whatever the
cause); `None` raises `FlagKind.GEOCODING_UNAVAILABLE` (critical — retrieval cannot run at
all).

The two centroid flags are split because only one of them is worth retrying: a service
outage may resolve on a later run, an address with no street number will not. The Critic's
rework cycle branches on that.

Kept out of scope deliberately
-------------------------------
No disk cache, unlike `tools/hud_fmr.py`. That client caches because a training pull
hits the same (county, year) key repeatedly across thousands of rows against a 60/minute
throttle. Geocoding is called at most once per subject property per pipeline run — there
is no hot loop here to protect, and adding one would be exactly the premature machinery
§8 warns against.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

import requests

from tools import diagnostics
from tools.county_crosswalk import normalize_city, normalize_state

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


class GeocodeSource(StrEnum):
    """Which of the two tiers in the module docstring produced a `GeocodeResult`.

    The caller reads this to decide the disclosure (see the docstring's last paragraph
    above): `CENSUS_GEOCODER` raises nothing, `CITY_CENTROID` raises one of two warn
    flags chosen by `GeocodeResult.primary_unavailable`. A closed type means that branch
    in the Extractor can't silently stop matching because of a typo on either side.

    The cause of a fallback is deliberately *not* a third member here. This enum answers
    "which tier produced the coordinate"; the tier is the same either way, and folding a
    reason into it would make the type answer two questions at once.
    """

    CENSUS_GEOCODER = "census_geocoder"
    CITY_CENTROID = "city_centroid"

# The "current" public address reference vintage, as opposed to a historical benchmark
# (Census also publishes point-in-time snapshots for reproducibility research, which is
# not the concern here).
_CENSUS_BENCHMARK = "Public_AR_Current"
_TIMEOUT_SECONDS = 10


class GeocodingError(Exception):
    """The Census Geocoder request itself failed — network error, non-200, or a response
    that didn't parse as the expected shape.

    Distinct from a clean response with zero address matches, which is a routine, expected
    outcome (an incomplete or unrecognized address) and is represented by `geocode_census`
    returning `None`, not by raising. `geocode()` catches this and falls through to the
    centroid fallback; it is exposed publicly so a caller can distinguish "the
    API was unreachable" from "the API ran and found nothing" (e.g. for smoke testing).
    """


@dataclass
class GeocodeResult:
    latitude: float
    longitude: float
    matched_address: str
    source: GeocodeSource

    # True only when the Census *request* failed — as distinct from it running and
    # finding no match. Both produce a centroid fallback and used to be
    # indistinguishable to the caller, which mattered because they call for opposite
    # responses: an outage is worth retrying, an address with no street number is not.
    # `source` says which tier produced the coordinate; this says why the tier above it
    # did not. Only meaningful when `source is CITY_CENTROID`.
    primary_unavailable: bool = False


def _oneline_address(
    street_address: Optional[str],
    city: Optional[str],
    state: Optional[str],
    zip_code: Optional[str],
) -> str:
    parts = [p for p in (street_address, city, state, zip_code) if p]
    return ", ".join(parts)


def geocode_census(
    street_address: Optional[str],
    city: Optional[str],
    state: Optional[str],
    zip_code: Optional[str] = None,
) -> Optional[GeocodeResult]:
    """Primary lookup against the Census Bureau's public geocoder.

    Returns `None` for "ran fine, no match" (e.g. a city-only address with no street
    number — nothing wrong happened, there just isn't enough to geocode to a parcel).
    Raises `GeocodingError` for "the call itself failed," so `geocode()` below can tell
    the two apart and only the second one triggers the centroid fallback for the right
    reason rather than papering over a network problem.
    """
    oneline = _oneline_address(street_address, city, state, zip_code)
    if not oneline:
        return None

    try:
        response = requests.get(
            CENSUS_GEOCODER_URL,
            params={"address": oneline, "benchmark": _CENSUS_BENCHMARK, "format": "json"},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        matches = payload["result"]["addressMatches"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise GeocodingError(f"Census Geocoder request failed for {oneline!r}: {exc}") from exc

    if not matches:
        return None

    best = matches[0]
    coords = best["coordinates"]
    return GeocodeResult(
        latitude=float(coords["y"]),
        longitude=float(coords["x"]),
        matched_address=best.get("matchedAddress", oneline),
        source=GeocodeSource.CENSUS_GEOCODER,
    )


@functools.lru_cache(maxsize=1)
def _city_centroids() -> dict[tuple[str, str], tuple[float, float]]:
    """Mean lat/lon per (city, state), averaged from coordinates the corpus already has.

    No geocoding happens here — every row already carries real `latitude`/`longitude`
    from the original Kaggle scrape. This just aggregates those existing values into a
    per-city average, to serve as a fallback *subject* coordinate (see `city_centroid`).

    Lazy and cached rather than eager: most calls to `geocode()` resolve on the Census
    path and never touch this, so nothing should pay for loading and grouping ~99K rows
    unless the fallback is actually needed. Imported here rather than at module level for
    the same reason — importing `tools.kaggle_data` triggers no I/O by itself, but keeping
    the dependency local makes the laziness obvious at the call site.
    """
    from tools import kaggle_data

    df = kaggle_data.load_clean()
    grouped = (
        df.assign(
            _city=df["cityname"].map(normalize_city),
            _state=df["state"].map(normalize_state),
        )
        .groupby(["_city", "_state"])[["latitude", "longitude"]]
        .mean()
    )
    return {
        (city, state): (float(row.latitude), float(row.longitude))
        for (city, state), row in grouped.iterrows()
    }


def city_centroid(
    city: Optional[str],
    state: Optional[str],
    primary_unavailable: bool = False,
) -> Optional[GeocodeResult]:
    """Fallback lookup: the mean coordinates of every corpus listing in (city, state).

    Returns `None` if the city isn't in the corpus at all — which also means comp
    retrieval would find nothing there regardless of how the subject was geocoded, so
    there is no accuracy lost by declining to invent a coordinate for it.

    `primary_unavailable` is passed through to the result rather than inspected here:
    this function does not know why it was called, and the caller does.
    """
    if not city or not state:
        return None
    coords = _city_centroids().get((normalize_city(city), normalize_state(state)))
    if coords is None:
        return None
    lat, lon = coords
    return GeocodeResult(
        latitude=lat,
        longitude=lon,
        matched_address=f"{city}, {state} (corpus centroid — city-level approximation)",
        source=GeocodeSource.CITY_CENTROID,
        primary_unavailable=primary_unavailable,
    )


def geocode(
    street_address: Optional[str],
    city: Optional[str],
    state: Optional[str],
    zip_code: Optional[str] = None,
) -> Optional[GeocodeResult]:
    """Resolve a subject property to coordinates: Census primary, corpus-centroid
    fallback. Never raises — a request failure degrades to the fallback rather than
    propagating, matching how every other derived-tier lookup in this system behaves.
    Returns `None` only if both tiers come up empty.
    """
    primary_unavailable = False
    try:
        result = geocode_census(street_address, city, state, zip_code)
    except GeocodingError as exc:
        # Previously silent, and it was the worst place in the system to be silent: the
        # caller sees only "no parcel match", which is indistinguishable from the
        # geocoder having run fine and found nothing. Those call for opposite responses
        # — one is an outage to retry, the other is an address to correct.
        #
        # U3 logged the distinction here but let both cases raise the same flag, noting
        # that "the resulting flag says the same thing either way". U7 needs them apart:
        # the Critic's rework cycle is worth spending on an outage, because re-running
        # the Extractor re-attempts the call, and is worth nothing on an address that
        # will never resolve. So the cause now rides on the result.
        diagnostics.log_exception(
            "geocoding.geocode: the Census request failed (as distinct from running "
            "and finding no match); falling through to the corpus city centroid",
            exc,
        )
        result = None
        primary_unavailable = True

    if result is not None:
        return result
    return city_centroid(city, state, primary_unavailable=primary_unavailable)
