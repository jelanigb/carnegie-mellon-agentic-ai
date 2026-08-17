"""The synthetic listings `main.py` runs, and where each of their numbers comes from.

Why this is a module rather than a dict in `main.py`
------------------------------------------------------
Every figure in these listings used to be invented — plausible, roughly right, and
unjustified. That is a defensible thing for a fixture whose job is to exercise a code
path, and an indefensible one for a fixture whose output a human reads as a worked
example. These deals are the second kind: they produce the reports in the write-up and
the demo video, and a reader has no way to tell a number chosen from market data from a
number chosen to look reasonable.

So each deal now carries its numbers *and* the basis for them, and
`scripts/verify_demo_calibration.py` re-derives that basis from live sources and reports
the drift. The committed values stay stable and reviewable; their provenance stays
checkable. This is the same arrangement `tools/county_crosswalk.py` uses for its FIPS
codes and `scripts/verify_metro_selection.py` for the metro choice — a committed value
next to the script that can prove it.

What is real and what is invented
-----------------------------------
- **Real:** the street address, and therefore the geocode, the county, and the FMR that
  county attracts. The asking price is anchored to Redfin's median sale price for
  Multi-Family (2-4 unit) properties in that metro. The stated rents are anchored to
  HUD's FY2026 Fair Market Rent for the resolved county at the listing's bedroom count.
- **Invented:** that the property is for sale at all, its unit mix, condition, amenities,
  and the specific figures within the tolerances below. No listing here describes a real
  offer, and none should be read as one.

Why FMR and not the corpus for rents
--------------------------------------
The Kaggle corpus is 2018-19. These listings purport to be current, so calibrating their
rents against a corpus median would embed a seven-year vintage gap in the demo — exactly
the mismatch §2's FMR-anchoring design exists to remove. FMR is published annually and
county-level, so it is the current-dollar figure already available to this project.

One property of FMR worth stating rather than discovering later: it is a 40th-percentile
rent, not a market median, so a listing calibrated to it sits at the affordable end of
its market by construction. That is acceptable for a demo and would not be acceptable for
an accuracy benchmark, which is a separate job wanting a separate dataset (see the
public-records item in §7).

The Staten Island exception, which is deliberate
--------------------------------------------------
Redfin's extract covers Chicago, Cleveland, and Los Angeles only, so the Staten Island
deal has no price basis and its asking figure is unanchored. It is kept that way on
purpose: §2 designates New York as the case grounded in real market thinness rather than
constructed scarcity, and that thinness turns out to run deeper than comp density — no
comps, no appreciation series, and no sale-price benchmark either. Labelling the gap is
worth more than hiding it behind a number that looks like the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Tolerances the verification script holds these values to. Wide on price because a
# specific building legitimately differs from its metro's median — the check is "is this
# figure in the neighbourhood of the market", not "is it the market". Tighter on rent
# because a stated rent is a fact about the property, and FMR is county-level rather than
# metro-level, so there is less legitimate spread to allow for.
PRICE_TOLERANCE = 0.15
RENT_TOLERANCE = 0.10


@dataclass(frozen=True)
class DemoDeal:
    """A synthetic listing plus the provenance of every figure inside it.

    `price` and `unit_rents` duplicate numbers that also appear in `listing` as text. The
    duplication is the point: the listing is unstructured text because that is what the
    Extractor consumes, and these fields are what a verification script can check without
    parsing prose. They are asserted equal at import — see `_check_listing_states`.
    """

    key: str
    listing: str
    # Non-None only where the deal exists to demonstrate a supplied-coordinate conflict.
    supplied_coords: Optional[tuple[float, float]] = None

    price: Optional[float] = None
    unit_rents: tuple[float, ...] = ()

    # How to re-derive each figure. `redfin_metro_median` names a metro in
    # `tools/redfin_data.py`; `hud_fmr` names the bedroom count to look up against the
    # county the listing's own address resolves to. `None` means the figure has no
    # market basis, which is a statement rather than an omission — see the module
    # docstring on Staten Island.
    price_basis: Optional[str] = None
    rent_basis: Optional[str] = None
    notes: str = ""


def _check_listing_states(deal: DemoDeal) -> None:
    """Fail at import if a figure drifts out of the listing text it is meant to mirror.

    The failure this prevents is quiet: someone edits the asking price in the prose and
    not the field, the verification script keeps checking the old number, and the
    provenance silently stops describing the listing anyone actually reads.
    """
    if deal.price is not None:
        rendered = f"${deal.price:,.0f}"
        if rendered not in deal.listing:
            raise ValueError(
                f"Demo deal {deal.key!r}: price {rendered} is not stated in the listing "
                f"text. The structured figure and the prose have diverged."
            )
    for rent in deal.unit_rents:
        rendered = f"${rent:,.0f}"
        if rendered not in deal.listing:
            raise ValueError(
                f"Demo deal {deal.key!r}: rent {rendered} is not stated in the listing "
                f"text. The structured figure and the prose have diverged."
            )


DEMO_DEALS: dict[str, DemoDeal] = {
    "los-angeles": DemoDeal(
        key="los-angeles",
        listing=(
            "For sale: 1425 W Sunset Blvd, Los Angeles, CA 90026. Charming 2-unit "
            "duplex in Echo Park, each unit 2 bed / 1 bath, approx 950 sq ft per unit. "
            "Renovated kitchens, in-unit laundry, off-street parking. Current tenants "
            "pay $2,850 and $2,950 per month. Asking $1,049,000."
        ),
        price=1_049_000,
        unit_rents=(2_850, 2_950),
        price_basis="redfin_metro_median:Los Angeles",
        rent_basis="hud_fmr:2",
    ),
    "chicago": DemoDeal(
        key="chicago",
        listing=(
            "For sale: 2500 N Kedzie Blvd, Chicago, IL 60647. Classic Logan Square "
            "2-flat, 2 bed / 1 bath per unit, approx 950 sq ft each. Original woodwork, "
            "full basement, two-car garage. Current tenants pay $1,750 and $1,800 per "
            "month. Asking $499,000."
        ),
        price=499_000,
        unit_rents=(1_750, 1_800),
        price_basis="redfin_metro_median:Chicago",
        rent_basis="hud_fmr:2",
    ),
    "staten-island": DemoDeal(
        key="staten-island",
        listing=(
            "For sale: 7001 Amboy Rd, Staten Island, NY 10307. Tottenville 3-unit "
            "building, 2 bed / 1 bath units, approx 900 sq ft each. Deep lot, needs "
            "updating. Current tenants pay $2,850, $2,900 and $2,975 per month. "
            "Asking $875,000."
        ),
        price=875_000,
        unit_rents=(2_850, 2_900, 2_975),
        # No Redfin coverage for the New York metro — deliberately unanchored, see the
        # module docstring. The rents *are* anchored: Richmond County has an FMR even
        # though the sale-price series does not reach it.
        price_basis=None,
        rent_basis="hud_fmr:2",
        notes=(
            "Asking price has no market basis; Redfin's extract does not cover New "
            "York. Retained as the case where reality supplies nothing — no comps, no "
            "appreciation series, no price benchmark."
        ),
    ),
    "no-geography": DemoDeal(
        key="no-geography",
        listing=(
            "For sale: 42 Quarry Ridge Rd, Tallow Bend, WY 82001. Well-kept 2-unit "
            "property, 2 bed / 1 bath per unit, approx 1,000 sq ft each. Detached "
            "garage, large lot. Asking $340,000."
        ),
        price=340_000,
        # Nothing to anchor to, and that is the entire point of this deal: the address
        # resolves to no parcel and no corpus city, so there is no county, no FMR, and
        # no metro. A calibrated figure here would imply a market this listing does not
        # have.
        price_basis=None,
        rent_basis=None,
        notes=(
            "Address verified to resolve through neither the Census geocoder nor the "
            "corpus centroid. Figures are illustrative by necessity."
        ),
    ),
    "coord-conflict": DemoDeal(
        key="coord-conflict",
        listing=(
            "For sale: 1425 W Sunset Blvd, Los Angeles, CA 90026. Charming 2-unit "
            "duplex in Echo Park, each unit 2 bed / 1 bath, approx 950 sq ft per unit. "
            "Current tenants pay $2,850 and $2,950 per month. Asking $1,049,000."
        ),
        # Santa Monica, ~14 mi west of the address the listing gives.
        supplied_coords=(34.0195, -118.4912),
        price=1_049_000,
        unit_rents=(2_850, 2_950),
        price_basis="redfin_metro_median:Los Angeles",
        rent_basis="hud_fmr:2",
        notes="The Los Angeles deal with coordinates describing a different property.",
    ),
}


for _deal in DEMO_DEALS.values():
    _check_listing_states(_deal)
