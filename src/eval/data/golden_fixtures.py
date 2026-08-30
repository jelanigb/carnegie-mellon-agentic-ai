"""The golden `DealTerms` fixtures the engineered cases run on (U8.2).

Separate from `eval/cases.py` for the same reason `demo_deals.py` is separate from
`main.py`: a fixture is *data with a provenance*, and a case is a *claim about it*. Keeping
them apart means the claim can be reviewed without re-reading five property descriptions,
and a fixture can be reused by more than one case without either owning it.

What is real here and what is engineered
-----------------------------------------
The split is the same one `demo_deals.py` draws, and it is drawn again rather than
inherited, because these fixtures are *calibrated to fail* and that changes what honesty
requires of them.

- **Real:** the street address, and therefore the coordinates, the county, the ZIP, and
  the HUD Fair Market Rent that county and ZIP attract. Every coordinate below was
  returned by the Census geocoder for the address beside it, on Aug 28, 2026, and is
  committed rather than looked up at run time — see "Why coordinates are hard-coded".
- **Engineered:** exactly one attribute per fixture, named in its `engineered` field. That
  attribute is what the case targets.
- **Invented:** that the property is for sale at all, its unit mix, and its condition. No
  fixture below describes a real offer.

**The asking prices are not anchored to a benchmark, and that is a deliberate difference
from `demo_deals.py`.** Those listings exist to produce a worked example a reader takes
seriously, so #11 anchored every figure to a market source. These exist to trip a named
degradation path, and only one of them (`chicago-five-bedroom`) has an asking price that
matters to its target at all. Anchoring the rest would spend calibration effort on figures
no case reads, and would imply a market claim the fixture is not making. Each price is
stated as plausible-for-the-metro and labelled as such rather than sourced.

Why coordinates are hard-coded rather than geocoded at run time
-----------------------------------------------------------------
Geocoding is a Census API call. A fixture that resolved its own coordinates would put a
network dependency — and a third party's uptime — inside the tier `eval/README.md` defines
as fast and reproducible, and a batch whose rows move when someone else's service is slow
is not measuring this repository. So the fixture carries the answer and the address it came
from, and `scripts/` can re-derive the pair whenever anyone wants to check it. This is the
same arrangement `tools/county_crosswalk.py` uses for its FIPS codes.

`county_fips` is deliberately **not** carried. It is resolved from the coordinates by a
local point-in-polygon join (U8.1b), which is network-free, so leaving it out costs nothing
and keeps one derived value from being hand-copied into a place it could go stale.

Why these three metros and not one
------------------------------------
Los Angeles, Chicago and Cleveland are §2's inference trio, and the fixtures are spread
across them on purpose. `agents/critic.confidence_from_flags` carries a `TODO(U8)` noting
that three of the six demo deals share one county's FMR-anchor warning — a fact about the
demo set reusing one county, not about deals in general — and that the eval batch is what
would show whether that skew is an artifact. A batch sited in one county would reproduce
the artifact instead of measuring it.

The consequence shows up immediately and is worth stating rather than leaving as a
coincidence: Cook County publishes Small Area (ZIP-level) FMRs and Los Angeles and Cuyahoga
do not, so a Chicago fixture carries one fewer warn-severity flag than an otherwise
identical Los Angeles one, before anything about the deal is considered. Two fixtures below
sit either side of that line.

A fourth metro, added for a different reason (U8.4)
-----------------------------------------------------
The New York fixture below is not part of the three-metro skew check above — it exists to
test `FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED` (OQ-3) on a listing with a real,
non-empty comp set. The `staten-island` demo deal already trips that flag, but it does so
by accident: that deal escalates on zero comps, so the market-error disclosure is invisible
against a report that was already going to a human reviewer for an unrelated reason. This
fixture sits in a part of New York the corpus covers densely, so the flag fires on a report
that is not already determined by something else.
"""

from __future__ import annotations

from dataclasses import dataclass

from state import DealTerms


@dataclass(frozen=True)
class GoldenFixture:
    """A complete `DealTerms` plus a statement of what was bent to make it fail.

    `engineered` is prose rather than a field name because the reader it is written for is
    reviewing whether the fixture is honest, not indexing it. `terms` is a factory rather
    than an instance so that no two cases can share and mutate one object — the runner
    copies defensively as well, and both are cheap.
    """

    key: str
    address: str
    # What is deliberately abnormal, and what is ordinary. One sentence.
    engineered: str
    terms: DealTerms


def _terms(**kwargs) -> DealTerms:
    return DealTerms(**kwargs)


# --------------------------------------------------------------------------
# Los Angeles — 1200 S Hoover St, 90006 (Pico-Union). Los Angeles County, 06037.
# Census geocode Aug 28, 2026: 34.049278, -118.284093.
#
# **This block used to say every LA fixture carries a county-level anchoring warn, and
# that stopped being true on Aug 30, 2026 (U11.3).** HUD published no Small Area FMR for
# LA County at the corpus's vintage, so under the old anchor every subject here was
# county-anchored unconditionally and the control scored 0.85 rather than 1.00. The
# anchor is now Zillow's market index at the subject's own ZIP, which covers 90006 — so
# the warn is gone and the control scores clean. Left as a note rather than deleted,
# because a stale *baseline* is how a batch quietly stops measuring what it claims to.
# --------------------------------------------------------------------------

_LA = dict(
    full_address="1200 S Hoover St, Los Angeles, CA 90006",
    street_address="1200 S Hoover St",
    city="Los Angeles",
    state="CA",
    zip_code="90006",
    latitude=34.049278,
    longitude=-118.284093,
)

FIXTURES: dict[str, GoldenFixture] = {}


def _add(fixture: GoldenFixture) -> GoldenFixture:
    FIXTURES[fixture.key] = fixture
    return fixture


LA_ORDINARY = _add(GoldenFixture(
    key="la-ordinary-duplex",
    address=_LA["full_address"],
    engineered=(
        "Nothing. This is the control: an ordinary two-bedroom duplex in a dense market, "
        "priced and sized like the comps around it. It exists so the batch contains a "
        "case that should *not* escalate."
    ),
    terms=_terms(**_LA, price=1_000_000, unit_count=2, bedrooms=2, bathrooms=1.0,
                 square_footage=950.0, unit_rents=[2_200.0, 2_300.0]),
))

LA_OVERSIZED_LOFT = _add(GoldenFixture(
    key="la-oversized-loft",
    address=_LA["full_address"],
    engineered=(
        "Floor area. 5,000 sq ft on two bedrooms — a converted loft, and far outside "
        "anything a 2018-19 rental corpus of small multi-family units contains. Bedrooms, "
        "bathrooms and the market are ordinary."
    ),
    terms=_terms(**_LA, price=2_400_000, unit_count=2, bedrooms=2, bathrooms=2.0,
                 square_footage=5_000.0, unit_rents=[6_500.0, 6_800.0]),
))

LA_THREE_BEDROOM = _add(GoldenFixture(
    key="la-three-bedroom-comp-drift",
    address=_LA["full_address"],
    engineered=(
        "Bedroom count against a thin local supply. Three bedrooms at 1,000 sq ft is an "
        "ordinary unit; what is engineered is that the retrieval loop must widen its "
        "match criteria to find eight of them here, so the comp set comes back unlike "
        "the subject on an attribute the rent estimate prices on."
    ),
    terms=_terms(**_LA, price=1_100_000, unit_count=2, bedrooms=3, bathrooms=1.0,
                 square_footage=1_000.0, unit_rents=[3_300.0, 3_400.0]),
))


# --------------------------------------------------------------------------
# Chicago — Cook County, 17031. Was "the one demo-adjacent county with Small Area FMRs,
# so these fixtures anchor at ZIP resolution and carry one fewer warn than their LA
# counterparts" — true until U11.3, and no longer a distinction: the market-index anchor
# resolves at ZIP tier in all four markets. What Chicago still gives the batch is the
# market where the re-anchoring moved the *estimate* most (metro MAE $454 → $343).
# --------------------------------------------------------------------------

_CHI_UPTOWN = dict(
    full_address="5100 N Kenmore Ave, Chicago, IL 60640",
    street_address="5100 N Kenmore Ave",
    city="Chicago",
    state="IL",
    zip_code="60640",
    latitude=41.975320,
    longitude=-87.656463,
)

_CHI_LOGAN = dict(
    full_address="3300 W Fullerton Ave, Chicago, IL 60647",
    street_address="3300 W Fullerton Ave",
    city="Chicago",
    state="IL",
    zip_code="60647",
    latitude=41.924731,
    longitude=-87.710836,
)

CHI_UPTOWN_ORDINARY = _add(GoldenFixture(
    key="chicago-uptown-duplex",
    address=_CHI_UPTOWN["full_address"],
    engineered=(
        "Nothing about the property. Two bedrooms, one bath, 950 sq ft, in a dense "
        "rental market — the comps come back matching on every attribute the search "
        "constrains. What this fixture is for is the *disagreement* that survives all "
        "that matching."
    ),
    terms=_terms(**_CHI_UPTOWN, price=530_000, unit_count=2, bedrooms=2, bathrooms=1.0,
                 square_footage=950.0, unit_rents=[1_800.0, 1_850.0]),
))

CHI_UPTOWN_OVERSIZED = _add(GoldenFixture(
    key="chicago-uptown-oversized",
    address=_CHI_UPTOWN["full_address"],
    engineered=(
        "Floor area, and only just enough of it. 1,600 sq ft on two bedrooms is a large "
        "but entirely ordinary unit; it is large enough that the retrieval loop has to "
        "drop its floor-area band to fill the comp set, and not so large that it also "
        "has to widen the search radius. That distinction is the whole point of the "
        "fixture — the radius concession is warn-severity and would push the confidence "
        "score below the escalation threshold on its own, which is precisely the thing "
        "this case needs *not* to happen."
    ),
    terms=_terms(**_CHI_UPTOWN, price=600_000, unit_count=2, bedrooms=2, bathrooms=2.0,
                 square_footage=1_600.0, unit_rents=[2_450.0, 2_550.0]),
))

CHI_UPTOWN_BAND_UNDER = _add(GoldenFixture(
    key="chicago-uptown-band-under",
    address=_CHI_UPTOWN["full_address"],
    engineered=(
        "Floor area, and *only* floor area, chosen so the comp set comes back with "
        "exactly two of eight comparables outside the size band. Its sibling below is "
        "the same building 200 sq ft larger, which makes it three of eight. Nothing "
        "else about either property differs."
    ),
    terms=_terms(**_CHI_UPTOWN, price=560_000, unit_count=2, bedrooms=2, bathrooms=1.0,
                 square_footage=1_100.0, unit_rents=[2_050.0, 2_100.0]),
))

CHI_UPTOWN_BAND_OVER = _add(GoldenFixture(
    key="chicago-uptown-band-over",
    address=_CHI_UPTOWN["full_address"],
    engineered=(
        "The straddle partner of the fixture above: 1,300 sq ft instead of 1,100, which "
        "takes the out-of-band comp count from two to three and trips the drift "
        "disclosure. 18% more floor area is the whole difference."
    ),
    terms=_terms(**_CHI_UPTOWN, price=590_000, unit_count=2, bedrooms=2, bathrooms=1.0,
                 square_footage=1_300.0, unit_rents=[2_250.0, 2_300.0]),
))

CHI_FIVE_BEDROOM = _add(GoldenFixture(
    key="chicago-five-bedroom",
    address=_CHI_LOGAN["full_address"],
    engineered=(
        "Bedroom count, past the top of HUD's published schedule. Five bedrooms per unit "
        "is unusual and legal; HUD prices nothing above four, so the anchor every rent "
        "figure in this system is built on has to be substituted."
    ),
    terms=_terms(**_CHI_LOGAN, price=750_000, unit_count=2, bedrooms=5, bathrooms=2.0,
                 square_footage=2_000.0, unit_rents=[3_200.0, 3_300.0]),
))


# --------------------------------------------------------------------------
# Cleveland — Cuyahoga County, 39035. §2's thin-but-real market: the comp corpus places
# 92% of its rows on city-area placeholder coordinates, and Cleveland is the extreme —
# measured Aug 22, 2026, eight comps from a single point.
# --------------------------------------------------------------------------

_CLE = dict(
    full_address="3200 W 25th St, Cleveland, OH 44109",
    street_address="3200 W 25th St",
    city="Cleveland",
    state="OH",
    zip_code="44109",
    latitude=41.466991,
    longitude=-81.700101,
)

CLE_ORDINARY = _add(GoldenFixture(
    key="cleveland-triplex",
    address=_CLE["full_address"],
    engineered=(
        "Nothing about the property — an ordinary three-unit building at the market's "
        "own bedroom count and size. The engineering is the *market*: this is the one "
        "inference metro where the comp set collapses onto a single coordinate, so the "
        "only independent check on the rent estimate is a point sample."
    ),
    terms=_terms(**_CLE, price=225_000, unit_count=3, bedrooms=2, bathrooms=1.0,
                 square_footage=900.0, unit_rents=[1_050.0, 1_075.0, 1_100.0]),
))

CLE_DIVERGENCE_OVER = _add(GoldenFixture(
    key="cleveland-divergence-over",
    address=_CLE["full_address"],
    engineered=(
        "Floor area, and *only* floor area, sited at 1,000 sq ft so the model comes in "
        "30.8% below the comp median — eight tenths of a point past the line. Its "
        "sibling below is the same building 50 sq ft larger and lands 28.9% below, "
        "which clears. The pair exists to measure how hard that line is to cross."
    ),
    terms=_terms(**_CLE, price=235_000, unit_count=3, bedrooms=2, bathrooms=1.0,
                 square_footage=1_000.0, unit_rents=[1_100.0, 1_125.0, 1_150.0]),
))

CLE_DIVERGENCE_UNDER = _add(GoldenFixture(
    key="cleveland-divergence-under",
    address=_CLE["full_address"],
    engineered=(
        "The straddle partner of the fixture above, 5% larger. Everything the comp "
        "search sees is unchanged — same coordinate, same eight comps, same zero out of "
        "band — so the divergence flag is the only thing that differs between them."
    ),
    terms=_terms(**_CLE, price=240_000, unit_count=3, bedrooms=2, bathrooms=1.0,
                 square_footage=1_050.0, unit_rents=[1_150.0, 1_175.0, 1_200.0]),
))


# --------------------------------------------------------------------------
# New York (Brooklyn) — Kings County, 36047. Added U8.4, for a different reason than the
# three above: see "A fourth metro, added for a different reason" in the module docstring.
# Census geocode Aug 29, 2026: 40.672786, -73.950302. Sited in Bedford-Stuyvesant, one of
# the corpus's densest New York clusters (`scripts/retrieval_evidence.py`'s module
# docstring measured 38 comps within 3 miles here), specifically so this fixture returns a
# real comp set rather than reproducing the `staten-island` demo's zero-comp accident.
# --------------------------------------------------------------------------

_NY_BEDSTUY = dict(
    full_address="756 Nostrand Ave, Brooklyn, NY 11216",
    street_address="756 Nostrand Ave",
    city="Brooklyn",
    state="NY",
    zip_code="11216",
    latitude=40.672786,
    longitude=-73.950302,
)

NY_BEDSTUY_ORDINARY = _add(GoldenFixture(
    key="ny-bedstuy-triplex",
    address=_NY_BEDSTUY["full_address"],
    engineered=(
        "Nothing about the property — an ordinary three-unit building at the market's "
        "own bedroom count and size. The engineering is the *market*, the same way it is "
        "for the Cleveland fixture above: New York's own holdout residual runs roughly "
        "double the model's overall figure, a known weakness this fixture surfaces "
        "outside the zero-comp accident the real `staten-island` deal shows it through. "
        "Retrieval here also settles onto a handful of coordinates rather than one, the "
        "same concentration Cleveland shows — denser, at 8 comps rather than a point "
        "sample, but not evenly spread."
    ),
    terms=_terms(**_NY_BEDSTUY, price=1_050_000, unit_count=3, bedrooms=2, bathrooms=1.0,
                 square_footage=900.0, unit_rents=[2_500.0, 2_600.0, 2_650.0]),
))


# --------------------------------------------------------------------------
# New York, the other two sitings (U8.6b's straddle pairs). Both are the same borough
# system and the same market-level disclosures as Bed-Stuy above; what differs is how the
# corpus is distributed under them, which is the quantity two of U8.6b's thresholds are
# compared against. **Geography is the engineering here, so no property attribute had to
# be bent** — which is what makes these the cleanest straddles in the batch.
# Census geocodes Aug 30, 2026.
# --------------------------------------------------------------------------

_NY_MANHATTAN = dict(
    full_address="530 W 45th St, New York, NY 10036",
    street_address="530 W 45th St",
    city="New York",
    state="NY",
    zip_code="10036",
    latitude=40.762049,
    longitude=-73.995412,
)

_NY_WAKEFIELD = dict(
    full_address="1500 E 233rd St, Bronx, NY 10466",
    street_address="1500 E 233rd St",
    city="Bronx",
    state="NY",
    zip_code="10466",
    latitude=40.889188,
    longitude=-73.832145,
)

NY_MANHATTAN_DISPERSED = _add(GoldenFixture(
    key="ny-manhattan-dispersed",
    address=_NY_MANHATTAN["full_address"],
    engineered=(
        "Nothing about the property, and nothing about the market either — the "
        "engineering is the *siting*. Bed-Stuy above returns eight comps standing on a "
        "single placeholder coordinate; Hell's Kitchen returns eight standing on five. "
        "Same city, same borough system, same elevated-market-error disclosure, opposite "
        "sides of the spatial-concentration line."
    ),
    terms=_terms(**_NY_MANHATTAN, price=2_400_000, unit_count=3, bedrooms=2,
                 bathrooms=1.0, square_footage=900.0,
                 unit_rents=[3_400.0, 3_500.0, 3_600.0]),
))

NY_WAKEFIELD_SEVEN_COMPS = _add(GoldenFixture(
    key="ny-wakefield-seven-comps",
    address=_NY_WAKEFIELD["full_address"],
    engineered=(
        "Again the siting, not the property: the northern edge of the Bronx is the one "
        "place in four indexed markets where retrieval exhausts its radius expansions "
        "and still returns seven comps instead of eight. **This is a straddle that does "
        "not straddle cleanly, and it is kept for that finding** — reaching seven means "
        "the relaxation ladder ran to the end first, so the case necessarily carries the "
        "radius and match-criteria concessions too."
    ),
    terms=_terms(**_NY_WAKEFIELD, price=850_000, unit_count=3, bedrooms=2, bathrooms=1.0,
                 square_footage=900.0, unit_rents=[2_200.0, 2_250.0, 2_300.0]),
))
