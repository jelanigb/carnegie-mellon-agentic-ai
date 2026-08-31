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

**That reasoning was superseded on Aug 30, 2026 (#19), and the figures were kept as
committed anyway.** The rent estimate is no longer anchored to FMR at all — the anchor is
Zillow's ZIP-level market rent index, and FMR is reduced to the bedroom step — so these
listings are calibrated against a benchmark the system otherwise no longer uses. The
consequence shows on one deal: `chicago`'s stated rents sit ~25% below Logan Square's own
market index, because HUD's 40th percentile runs about a third under the market in that
ZIP. Los Angeles, Staten Island and the mispriced Los Feliz listing are all within 10%.

Re-calibrating was measured at U8.7 and declined, on the same reasoning that kept
`staten-island`'s asking price: **nothing computes from a stated rent** — no flag, no
confidence contribution, no verdict — so a stale basis here cannot make the system wrong,
only make one listing less lifelike, and saying so is worth more than moving figures the
write-up and the video quote. Two things would change that answer: an audience who would
read Chicago's rents as implausible, or promoting the stated-rent comparison to a check,
which U8.7 also declined. A third consideration cuts against re-calibrating outright —
the estimate *is* that index times a modelled ratio, so calibrating stated rents to it
would make every demo report's stated-versus-modelled section print the same figure. That
is the defect `price_premium_to_basis` exists to prevent on the price side, and it would
need the same device on this one.

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

    # A deliberate, stated offset from `price_basis`. `None` means the asking price is
    # calibrated *to* the basis and the verification script holds it there.
    #
    # This exists so a listing can be mispriced on purpose without the provenance
    # becoming a lie. Every other deal is priced at its metro median because that is the
    # only defensible figure available; the consequence, recorded in U7's Q4, is that the
    # report's asking-price-versus-benchmark disclosure reads 0% on every one of them — a
    # real check this repository's own fixtures could not exercise. Stating the premium
    # keeps the price re-derivable from a live source while making the check mean
    # something.
    price_premium_to_basis: Optional[float] = None

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
        notes=(
            "Stated rents predate the anchor change (#19) and sit ~25% below this ZIP's "
            "market rent index: HUD's 40th-percentile schedule runs about a third under "
            "the market in Logan Square, and these were calibrated to HUD. Retained as "
            "committed per U8.7 — see the module docstring for why, and for what would "
            "change the answer."
        ),
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
        # Set without a market basis, and the reason recorded at the time — "Redfin's
        # extract does not cover New York" — turned out to be false (U8.4c): the extract
        # was fine; this build's trio-only filter was the gap. Now that the New York
        # series is loaded, the committed $875,000 measures ~11% below the metro's
        # multi-family median (~$981K, Jun 2026) — a plausible Staten Island discount
        # the divergence check does not flag — so the figure stands as committed rather
        # than being recalibrated, and the report benchmarks it like any other deal.
        price_basis=None,
        rent_basis="hud_fmr:2",
        notes=(
            "Asking price predates the New York price benchmark (see U8.4c) and sits "
            "~11% below the metro multi-family median. Retained as the sparse-comps "
            "case: zero comparables is the real, measured gap this deal exists to show."
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
    "overpriced": DemoDeal(
        key="overpriced",
        listing=(
            "For sale: 1801 N Vermont Ave, Los Angeles, CA 90027. Los Feliz 2-unit "
            "property, each unit 2 bed / 1 bath, approx 950 sq ft per unit. Strong "
            "rental history, excellent walkability, tremendous upside for the right "
            "buyer. Current tenants pay $2,800 and $2,900 per month. Asking $1,625,000."
        ),
        price=1_625_000,
        unit_rents=(2_800, 2_900),
        price_basis="redfin_metro_median:Los Angeles",
        # ~55% above the metro median, deliberately. Everything else about this listing
        # is ordinary — same market, same unit mix, same FMR-anchored rents as the Los
        # Angeles deal — so the asking price is the only thing that moved, and the
        # report's price-versus-benchmark disclosure is the only place it shows up.
        price_premium_to_basis=0.55,
        rent_basis="hud_fmr:2",
        notes=(
            "Deliberately mispriced. Exists because every other demo listing is "
            "calibrated to the same benchmark the report reads its asking price "
            "against, so the disclosure reads 0% on all of them and cannot be seen to "
            "work. Read as a fixture for that check, not as a claim that Los Feliz "
            "trades at this price."
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
