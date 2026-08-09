"""(cityname, state) -> county FIPS `entityid` crosswalk for the metro shortlist.

Why this module exists
----------------------
The Kaggle rental corpus carries `cityname`, `state`, `latitude`, and `longitude`, but
no county or ZIP column (docs/implementation_plan.md §2, "Two data gaps" — Gap 1). The
entire rent-level anchoring strategy keys on a county FIPS code: HUD FMR lookups are
addressed by a 10-digit `entityid` obtained from `fmr/listCounties/{state}`, and
`DealTerms.county_fips` is meant to hold exactly that value. Without a bridge from city
to county, no training row can be normalized by its local FMR and no subject property
can be anchored to current dollars.

§2 resolves the gap by hand-verifying a crosswalk for the curated training shortlist
rather than taking on a spatial dependency. A `latitude`/`longitude` -> FIPS join against
Census TIGER shapefiles would be exact and would generalize to the full 100K rows, but it
requires `geopandas` plus shapefile management for a lookup that, at this scope, is a
few dozen constants. The spatial join is documented in §2 as the scale-up path; it is not
worth the dependency now.

Accuracy caveat (read before extending this table)
--------------------------------------------------
Several large cities span more than one county. This table records the *principal*
county — the one containing the bulk of the city's population and housing stock — and
marks the entry `multi_county=True`. That is an approximation, and it is acceptable here
for a specific reason: the FMR figure it retrieves is a **metro-level anchor, not a
parcel-level assessment**. HUD publishes FMRs by FMR area, which for these cities is a
metro-wide (HUD Metro FMR Area) figure that the neighboring counties in the same CBSA
typically share. A Houston listing mapped to Harris rather than Fort Bend resolves to
the same Houston-area FMR schedule in the overwhelming majority of cases. The residual
error is second-order against a model whose target is a *ratio* to local FMR, and it is
bounded by the fact that the ratio is applied against a same-metro anchor at prediction
time. A parcel-accurate mapping would matter for a tax or entitlement calculation; it
does not change this system's estimates materially.

Coverage
--------
Every `(cityname, state)` pair with at least 500 listings in the Kaggle corpus (28
pairs, ~26% of all rows), plus Newark, NJ. The 500-listing bar is the same one
`scripts/verify_metro_selection.py` uses for metro viability, so coverage here and metro
selection there are driven by one threshold rather than two unrelated ones. Newark is
included below the bar (56 listings) because §2 names "Newark / Jersey City" as the
documented alternate metro; carrying only Jersey City would leave that alternate half
mapped. The inference trio (Chicago/Cook, Los Angeles/Los Angeles, Cleveland/Cuyahoga)
is a subset, as §2 requires.

Verification
------------
Every `entityid` below was read from a live `fmr/listCounties/{state}` response, not
written from memory. `verify_against_hud()` re-runs that check — it re-fetches each
state's county list and confirms both that the entityid exists and that the county name
matches what this table claims. `main()` prints the full crosswalk with HUD's own county
names alongside, so the table can be checked visually rather than trusted.

Run: .venv/bin/python tools/county_crosswalk.py
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

try:  # Support both `python tools/county_crosswalk.py` and `import tools.county_crosswalk`.
    from tools.hud_fmr import HudFmrClient
except ImportError:  # pragma: no cover - import-path convenience only
    from hud_fmr import HudFmrClient


@dataclass(frozen=True)
class CountyRef:
    """One resolved county, as HUD identifies it.

    `entityid` is the 10-digit FIPS-style code HUD's FMR endpoints are addressed by;
    `county_name` and `town_name` are carried so the mapping can be verified against a
    live `listCounties` response instead of being trusted on sight.
    """

    entityid: str
    county_name: str
    state: str
    town_name: str = ""
    multi_county: bool = False


# The city-to-county mapping. Keys are (cityname, state) exactly as the Kaggle corpus
# spells them; lookup() normalizes both sides, so the literal spelling here is for
# readability rather than matching.
#
# `multi_county=True` marks a city whose boundaries cross county lines. The county
# chosen is the principal one, with the rationale on the same line. See the module
# docstring for why a principal-county approximation is acceptable against a
# metro-level FMR anchor.
#
# TODO(geography): New England entries need verification before use. HUD defines FMR
# areas by *town* rather than county in CT, ME, MA, NH, RI, and VT. Boston was tested
# and works — listCounties/MA returns a usable town entityid (2502507000, place code in
# the last five digits instead of the 99999 county placeholder) and get_fmr handles it
# unchanged. That was verified for Boston only; Providence RI and the other five states
# are untested. Do not assume the town regime behaves identically across all of them.
#
# TODO(U5): every entry marked multi_county=True should cause the Valuation agent to
# raise FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY, so the FMR figure derived from it is
# disclosed as resting on a principal-county approximation rather than an exact match.
# The flag kind exists in state.py; nothing raises it yet.
CROSSWALK: dict[tuple[str, str], CountyRef] = {
    # --- Inference trio (§2) ---------------------------------------------------
    # Chicago crosses into DuPage County only at the O'Hare airport annexation strip,
    # which contains effectively no residential stock.
    ("Chicago", "IL"): CountyRef("1703199999", "Cook County", "IL", multi_county=True),
    # The City of Los Angeles lies wholly within Los Angeles County; the surrounding
    # CBSA extends into Orange County, but the city itself does not.
    ("Los Angeles", "CA"): CountyRef("0603799999", "Los Angeles County", "CA"),
    ("Cleveland", "OH"): CountyRef("3903599999", "Cuyahoga County", "OH"),

    # --- Texas -----------------------------------------------------------------
    # Dallas extends into Collin, Denton, Kaufman, and Rockwall; Dallas County holds
    # the large majority of the city's population and nearly all of its older
    # multi-family stock.
    ("Dallas", "TX"): CountyRef("4811399999", "Dallas County", "TX", multi_county=True),
    # Houston extends into Fort Bend and Montgomery; Harris County contains roughly
    # nine-tenths of the city.
    ("Houston", "TX"): CountyRef("4820199999", "Harris County", "TX", multi_county=True),
    # San Antonio extends slightly into Comal and Medina; Bexar County is effectively
    # coextensive with the city.
    ("San Antonio", "TX"): CountyRef("4802999999", "Bexar County", "TX", multi_county=True),
    # Austin extends into Williamson and Hays; Travis County holds the urban core.
    ("Austin", "TX"): CountyRef("4845399999", "Travis County", "TX", multi_county=True),
    # Arlington, TX sits entirely within Tarrant County. Note the collision with
    # Arlington County, VA below — this is precisely why the key is (city, state).
    ("Arlington", "TX"): CountyRef("4843999999", "Tarrant County", "TX"),

    # --- Colorado ---------------------------------------------------------------
    # Denver is a consolidated city-county; the city and the county are the same entity.
    ("Denver", "CO"): CountyRef("0803199999", "Denver County", "CO"),
    ("Colorado Springs", "CO"): CountyRef("0804199999", "El Paso County", "CO"),

    # --- California -------------------------------------------------------------
    ("San Diego", "CA"): CountyRef("0607399999", "San Diego County", "CA"),

    # --- Nevada / Arizona / Nebraska --------------------------------------------
    # The City of Las Vegas is wholly within Clark County (as is unincorporated
    # "Las Vegas" in the Strip corridor, which many listings actually describe).
    ("Las Vegas", "NV"): CountyRef("3200399999", "Clark County", "NV"),
    ("Tucson", "AZ"): CountyRef("0401999999", "Pima County", "AZ"),
    # Omaha has annexed a strip into Sarpy County; Douglas County remains the core.
    ("Omaha", "NE"): CountyRef("3105599999", "Douglas County", "NE", multi_county=True),

    # --- Georgia ----------------------------------------------------------------
    # Atlanta straddles Fulton and DeKalb. Fulton holds roughly 90% of the city's
    # population and is the county HUD's Atlanta FMR area is anchored on.
    ("Atlanta", "GA"): CountyRef("1312199999", "Fulton County", "GA", multi_county=True),

    # --- North Carolina ---------------------------------------------------------
    ("Charlotte", "NC"): CountyRef("3711999999", "Mecklenburg County", "NC"),
    # Raleigh extends marginally into Durham County; Wake County is the city proper.
    ("Raleigh", "NC"): CountyRef("3718399999", "Wake County", "NC", multi_county=True),
    ("Greensboro", "NC"): CountyRef("3708199999", "Guilford County", "NC"),

    # --- Ohio -------------------------------------------------------------------
    ("Cincinnati", "OH"): CountyRef("3906199999", "Hamilton County", "OH"),
    # Columbus extends into Delaware and Fairfield; Franklin County is the core.
    ("Columbus", "OH"): CountyRef("3904999999", "Franklin County", "OH", multi_county=True),

    # --- Florida ----------------------------------------------------------------
    ("Tampa", "FL"): CountyRef("1205799999", "Hillsborough County", "FL"),

    # --- Illinois (see inference trio above for Chicago) ------------------------

    # --- Virginia ---------------------------------------------------------------
    # Virginia's independent cities are not part of any county and carry their own
    # FIPS codes. HUD lists them under `county_name` with a lowercase "city" suffix.
    # Richmond is the ambiguity worth naming: VA has both "Richmond city" (the
    # independent city, FIPS 5176099999) and "Richmond County" (a rural county in the
    # Northern Neck, FIPS 5115999999). Kaggle's "Richmond, VA" listings are the city.
    ("Richmond", "VA"): CountyRef("5176099999", "Richmond city", "VA"),
    ("Norfolk", "VA"): CountyRef("5171099999", "Norfolk city", "VA"),
    ("Alexandria", "VA"): CountyRef("5151099999", "Alexandria city", "VA"),
    # Arlington, VA is a county with no incorporated municipality inside it, so the
    # "city" in a listing address and the county are the same jurisdiction.
    ("Arlington", "VA"): CountyRef("5101399999", "Arlington County", "VA"),

    # --- Massachusetts ----------------------------------------------------------
    # New England exception. HUD defines FMR areas by *town* in the six New England
    # states, so `listCounties/MA` returns town-level rows: county_name "Suffolk
    # County", town_name "Boston city", and an entityid whose last five digits are the
    # place code (07000) rather than the 99999 county placeholder. That entityid works
    # against fmr/data unchanged — verified, see the module notes — so the town-based
    # regime is absorbed here in the crosswalk rather than needing a branch in
    # tools/hud_fmr.py.
    ("Boston", "MA"): CountyRef("2502507000", "Suffolk County", "MA", town_name="Boston city"),

    # --- Missouri ---------------------------------------------------------------
    # Kansas City spans Jackson, Clay, Platte, and Cass. Jackson County holds the
    # downtown core and the bulk of the pre-war multi-family stock.
    ("Kansas City", "MO"): CountyRef("2909599999", "Jackson County", "MO", multi_county=True),

    # --- New Jersey (§2's documented alternate metro) ---------------------------
    ("Jersey City", "NJ"): CountyRef("3401799999", "Hudson County", "NJ"),
    ("Newark", "NJ"): CountyRef("3401399999", "Essex County", "NJ"),
}

# The §2 inference trio, kept as a named constant so downstream code can assert
# coverage rather than restating the three cities.
INFERENCE_TRIO: tuple[tuple[str, str], ...] = (
    ("Chicago", "IL"),
    ("Los Angeles", "CA"),
    ("Cleveland", "OH"),
)

_WHITESPACE = re.compile(r"\s+")


def _normalize_city(cityname: str) -> str:
    """Fold a city name to a comparison key.

    Kaggle's `cityname` values are free text from listing feeds, so casing and
    punctuation vary ("St. Louis" / "St Louis", trailing whitespace). Periods and
    repeated whitespace are the two variations actually observed; both are removed
    rather than attempting broader fuzzy matching, which would risk false positives
    between genuinely different cities.
    """
    folded = cityname.strip().lower().replace(".", "")
    return _WHITESPACE.sub(" ", folded)


def _normalize_state(state: str) -> str:
    return state.strip().upper()


# Normalized lookup index, built once at import. This is a derived constant, not
# mutable state: nothing rebinds or mutates it after module load.
_INDEX: dict[tuple[str, str], CountyRef] = {
    (_normalize_city(city), _normalize_state(state)): ref
    for (city, state), ref in CROSSWALK.items()
}


def lookup_county(cityname: Optional[str], state: Optional[str]) -> Optional[CountyRef]:
    """Resolve (cityname, state) to a `CountyRef`, or None if uncovered.

    Returns None rather than raising: an uncovered city is an expected, routine
    outcome for a crosswalk that deliberately covers a shortlist, and the caller
    (the Valuation & Rent agent) needs to turn it into an
    `fmr_unavailable_for_county` flag rather than an exception. Missing inputs are
    treated the same way, since `DealTerms.city` and `.state` are both Optional.
    """
    if not cityname or not state:
        return None
    return _INDEX.get((_normalize_city(cityname), _normalize_state(state)))


def lookup_county_fips(cityname: Optional[str], state: Optional[str]) -> Optional[str]:
    """Resolve (cityname, state) to a 10-digit HUD `entityid`, or None if uncovered.

    This is the value `DealTerms.county_fips` holds and the value
    `hud_fmr.get_fmr()` is addressed by; no reformatting sits between them.
    """
    ref = lookup_county(cityname, state)
    return ref.entityid if ref is not None else None


def covered_cities() -> tuple[tuple[str, str], ...]:
    """Every (cityname, state) pair this crosswalk resolves, in table order."""
    return tuple(CROSSWALK.keys())


def covered_states() -> tuple[str, ...]:
    """Distinct state codes in the crosswalk, sorted — one HUD call per state."""
    return tuple(sorted({state for _, state in CROSSWALK.keys()}))


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of checking one crosswalk row against a live `listCounties` response."""

    cityname: str
    state: str
    entityid: str
    claimed_county: str
    hud_county: Optional[str]  # None when the entityid is absent from HUD's list
    hud_town: Optional[str]
    matches: bool


def verify_against_hud(
    client: Optional[HudFmrClient] = None,
) -> list[VerificationResult]:
    """Re-check every entityid against `fmr/listCounties/{state}`.

    This is the point of the module: FIPS codes written from memory are wrong often
    enough, and silently enough, that the crosswalk is only trustworthy if the check
    is executable. One HUD call per distinct state (14 as of this writing), served
    from `hud_fmr`'s on-disk cache after the first run.
    """
    client = client or HudFmrClient()

    hud_by_state: dict[str, dict[str, dict]] = {}
    for state in covered_states():
        hud_by_state[state] = {
            row["fips_code"]: row for row in client.list_counties(state)
        }

    results: list[VerificationResult] = []
    for (cityname, state), ref in CROSSWALK.items():
        row = hud_by_state[state].get(ref.entityid)
        hud_county = row.get("county_name") if row else None
        hud_town = row.get("town_name") if row else None
        matches = (
            row is not None
            and hud_county == ref.county_name
            and (hud_town or "") == ref.town_name
        )
        results.append(
            VerificationResult(
                cityname=cityname,
                state=state,
                entityid=ref.entityid,
                claimed_county=ref.county_name,
                hud_county=hud_county,
                hud_town=hud_town,
                matches=matches,
            )
        )
    return results


def main() -> None:
    """Print the crosswalk with HUD's own county names for visual verification."""
    print("=== (cityname, state) -> county FIPS crosswalk ===")
    print(f"{len(CROSSWALK)} cities across {len(covered_states())} states: "
          f"{', '.join(covered_states())}\n")

    print("Verifying every entityid against live fmr/listCounties/{state} ...\n")
    results = verify_against_hud()

    header = (
        f"{'city':<18} {'st':<3} {'entityid':<12} {'HUD county (live)':<24} "
        f"{'town':<14} {'multi':<6} ok"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        ref = CROSSWALK[(result.cityname, result.state)]
        print(
            f"{result.cityname:<18} {result.state:<3} {result.entityid:<12} "
            f"{(result.hud_county or 'NOT FOUND'):<24} "
            f"{(result.hud_town or '-'):<14} "
            f"{('yes' if ref.multi_county else '-'):<6} "
            f"{'OK' if result.matches else 'MISMATCH'}"
        )

    mismatches = [r for r in results if not r.matches]
    print(f"\nVerified {len(results) - len(mismatches)}/{len(results)} rows against "
          f"the live HUD county list.")
    if mismatches:
        print("\nUNRESOLVED / MISMATCHED — these must be corrected before use:")
        for result in mismatches:
            print(
                f"  {result.cityname}, {result.state}: crosswalk claims "
                f"'{result.claimed_county}' for {result.entityid}; "
                f"HUD returns '{result.hud_county or 'no such entityid'}'"
            )

    print("\n=== Cities spanning multiple counties (principal county used) ===")
    for (cityname, state), ref in CROSSWALK.items():
        if ref.multi_county:
            print(f"  {cityname}, {state} -> {ref.county_name}")
    print("  Approximation is acceptable here: the FMR retrieved is a metro-level")
    print("  anchor, and adjacent counties in the same CBSA generally share it.")

    print("\n=== Inference trio (§2) resolution check ===")
    for cityname, state in INFERENCE_TRIO:
        ref = lookup_county(cityname, state)
        status = f"{ref.entityid}  {ref.county_name}" if ref else "UNRESOLVED"
        print(f"  {cityname}, {state:<3} -> {status}")

    print("\n=== Lookup behavior ===")
    for cityname, state in [
        ("  chicago ", "il"),      # normalization: case + whitespace
        ("Arlington", "VA"),        # (city, state) key disambiguates ...
        ("Arlington", "TX"),        # ... two different Arlingtons
        ("Peoria", "IL"),           # outside the shortlist
        (None, "IL"),               # missing input from an incomplete extraction
    ]:
        label = f"({cityname!r}, {state!r})"
        print(f"  {label:<28} -> {lookup_county_fips(cityname, state)}")


if __name__ == "__main__":
    main()
