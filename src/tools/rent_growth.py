"""The forecast's rent-growth bands, and which series produced them (decision #21 — forecast rent source).

Why this module exists
----------------------
Through U8 the forecast projected rent forward on HUD's Fair Market Rent schedule, chosen
by decision #16 (rent-growth source) on an argument about mechanism rather than about data: *"the rent estimate
is `ratio x FMR`, so projecting the anchor forward while holding the structural ratio
constant forecasts rent by the same mechanism that produced the estimate."* That argument
was right and it now points somewhere else. Since #19 the estimate is `ratio x ZORI(ZIP) x
FMR-bedroom-step`, so projecting the anchor forward means projecting **ZORI**. This module
follows #16's own reasoning to where the system moved.

What that fixed, measured rather than asserted — full workings in
`docs/design/evaluator.md`, reproducible with `scripts/growth_correlation.py`:

- **A false premise.** The Tree-of-Thought search preferred *anti-correlated* rent/price
  pairings because this project measured rent and price growth moving opposite each other.
  Re-derived, that is a property of the *rent series*, not of the market: pooled r = -0.317
  against FMR, -0.197 once HUD's two national step-up years are removed, and **+0.222
  against market rent**. r-squared never exceeds 0.10 in any pass, so the honest reading is
  that no directional rule is supported in either direction.
- **A ~2pp/yr overstatement.** U8.0 measured the FMR schedule rising +51.9% since the
  corpus vintage against market rent's +33.5%. The Los Angeles demo projected rent at
  **+7.26%/yr** against a price *falling* 0.80%/yr; on ZORI the same deal reads +2.51%
  against +2.10%, which is the picture nobody had to be talked into.
- **An estimator asymmetry.** FMR is annual, so its outer bands were single-fiscal-year
  extremes while the price side used twelve-month sustained stretches — a rent band three
  times wider as an artifact of method. Both series are monthly now and both go through
  `tools/growth_bands.py`.

The county tier, and why not the ZIP tier
-----------------------------------------
The estimate is anchored at the subject's own ZIP and its growth is measured at the
subject's county. That is a real inconsistency and it is disclosed rather than hidden,
because the alternative is worse on the deals this system actually has:

- **ZIP 10307 has no ZORI series at all**, and it is the `staten-island` demo deal's ZIP.
  That deal resolves no Redfin metro, so rent is the only side of its forecast — a
  ZIP-first design turns a one-sided forecast into no forecast.
- 65-95% of the ZIPs inside this project's market counties start after 2018-01, so a
  ZIP-first design falls back to county for most subjects anyway, and varies the length of
  history behind a band by which ZIP the subject sits in.
- Where both tiers exist the answer barely moves: LA 90026 gives +0.68/+2.37/+3.86 against
  its county's +1.25/+2.51/+4.76.

When the FMR fallback runs
--------------------------
ZORI's county table covers 1,211 counties and the fallback carries 46% of them, for two
reasons that were found in that order.

**38% cannot form a single contiguous twelve-month run** of year-over-year observations
once the window and the 2020-2022 exclusion are applied, and below that line the shared
estimator silently redefines its own outer bands from "worst sustained stretch" to "worst
single month" — Defect 3 reappearing inside the change that closed it.

**A further 8% clear that bar and still cannot support a range.** Adams County IL passes
on 14 months of history and bands a five-year projection at +9.18/+9.86/+10.51: the
definition holds, and min and max over three overlapping views of one year are nearly the
same number. A thin series does not produce a visibly unreliable forecast, it produces a
confident-looking one, which is the worse failure. So the requirement is a full year's
worth of *distinct* stretches — see `config.ZORI_GROWTH_MIN_SUSTAINED_STRETCHES`, which
carries the measured distribution and records that this second threshold, unlike the
first, sits on a smooth distribution and is a judgment rather than a cliff.

The fallback keeps the FMR schedule's annual construction, because nine annual points
cannot carry a twelve-month window. The asymmetry #21 closes therefore survives on the
fallback path, which no demo deal and no eval case reaches, and `RENT_GROWTH_SOURCE`
discloses it when it does.

Flag-worthy conditions are returned as data, never printed or raised — the same division
`tools/redfin_data.py` keeps, and for the same reason: it is what stops a data module from
importing `state.py`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Allow `import config` when a tool module is run directly as a script, not only when
# imported from the src/ root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools import fmr_history, growth_bands, zori

# Which series produced a band set. Carried as data so `RENT_GROWTH_SOURCE` can name it
# and the report can say which construction the numbers came from.
SOURCE_ZORI = "zori"
SOURCE_FMR = "fmr"


@dataclass(frozen=True)
class RentGrowthBands:
    """Optimistic / base / pessimistic rent growth, and the provenance to weigh it.

    One shape for two sources, deliberately. The Scenario agent enumerates framings over
    whatever the rent side returns, and a search whose candidate payload changed type
    depending on which series was available would have to branch on that everywhere it
    reads a band. The fields only one source can populate are Optional and named for what
    they are.
    """

    available: bool
    source: Optional[str] = None
    source_description: Optional[str] = None
    resolution: Optional[str] = None
    area_name: Optional[str] = None
    unavailable_reason: Optional[str] = None

    # The three bands, in percent per year.
    base_yoy_pct: Optional[float] = None
    optimistic_yoy_pct: Optional[float] = None
    pessimistic_yoy_pct: Optional[float] = None

    n_yoy_observations: int = 0
    # Reader-facing span labels: months on ZORI ("2019-01"), fiscal years on FMR
    # ("FY2018"). Strings rather than dates because the two sources genuinely do not
    # describe the same kind of period, and rendering that difference away would be a
    # claim the data does not support.
    first_observation: Optional[str] = None
    last_observation: Optional[str] = None

    # Which fork of the depth-1 search this band set represents. The same question the
    # price side is asked, which is the point of #21's re-sourcing.
    anomalous_period_excluded: bool = False
    anomalous_period_share: float = 0.0

    # ZORI only: how many ZIPs the county median aggregates. Travels with the median for
    # the reason `CompAnchoring.comps_used` does — a median over one ZIP is a county
    # median in name only.
    zips_in_county: Optional[int] = None

    # FMR fallback only: the schedule's construction is annual, so its outer bands name a
    # fiscal year rather than the end of a stretch.
    optimistic_year: Optional[int] = None
    pessimistic_year: Optional[int] = None
    bedrooms: Optional[int] = None


def county_geoid(entityid: str) -> str:
    """The five-digit Census county GEOID inside a HUD entityid.

    **These are two different identifiers and the pipeline carries the wrong one for this
    purpose.** `DealTerms.county_fips` holds what HUD wants — `tools/county_crosswalk.py`
    builds it as `<state><county>99999`, ten characters — while `tools/zori.py` keys its
    county medians on the five-digit Census GEOID the boundary file publishes. The first
    five characters bridge them, which `scripts/growth_correlation.py` already relies on
    for the same reason.

    Safe only because the crosswalk returns `None` for New England, where HUD switches to
    a town-level place FIPS and the leading five characters are not a county at all. If
    that ever gains a town regime (see the crosswalk's `TODO(geography)`), this assumption
    goes with it.
    """
    return str(entityid)[:5]


def _county_name(county_fips: str) -> Optional[str]:
    """The county's own name, for the report. Absent is not an error."""
    try:
        from tools import county_crosswalk

        counties = county_crosswalk._counties()
        match = counties[counties["GEOID"] == county_geoid(county_fips)]
        if match.empty:
            return None
        row = match.iloc[0]
        return f"{row['NAMELSAD']}, {row['STUSPS']}"
    except (ImportError, KeyError, AttributeError, OSError):
        return None


def zori_bands(
    county_fips: str, exclude_anomalous_period: bool
) -> Optional[RentGrowthBands]:
    """Bands from the ZORI county median, or None if this county cannot support them.

    None means "ask the fallback", and it is returned for three distinct conditions the
    caller does not need to tell apart: the panel is not on disk, the county is absent
    from it, or its history is too short to form a sustained stretch. Each is a reason to
    use the FMR schedule instead, and `RENT_GROWTH_SOURCE` reports which series ran rather
    than why the other one did not.
    """
    tables = zori.county_median_tables()
    if tables is None:
        return None
    medians, zip_counts = tables
    geoid = county_geoid(county_fips)
    if geoid not in medians.index:
        return None

    yoy = growth_bands.yoy_from_levels(medians.loc[geoid])
    bands = growth_bands.bands_from_yoy(
        yoy, exclude_anomalous_period=exclude_anomalous_period
    )
    if bands is None or (
        bands.n_sustained_stretches < config.ZORI_GROWTH_MIN_SUSTAINED_STRETCHES
    ):
        return None

    zips = zip_counts.loc[geoid].max() if geoid in zip_counts.index else None
    return RentGrowthBands(
        available=True,
        source=SOURCE_ZORI,
        source_description=config.ZORI_GROWTH_SERIES_DESCRIPTION,
        resolution=config.ZORI_GROWTH_RESOLUTION,
        area_name=_county_name(county_fips),
        base_yoy_pct=bands.base_yoy_pct,
        optimistic_yoy_pct=bands.optimistic_yoy_pct,
        pessimistic_yoy_pct=bands.pessimistic_yoy_pct,
        n_yoy_observations=bands.n_yoy_observations,
        first_observation=str(pd.Timestamp(bands.first_observation).strftime("%Y-%m")),
        last_observation=str(pd.Timestamp(bands.last_observation).strftime("%Y-%m")),
        anomalous_period_excluded=bands.anomalous_period_excluded,
        anomalous_period_share=bands.anomalous_period_share,
        zips_in_county=int(zips) if zips is not None and not pd.isna(zips) else None,
    )


def fmr_bands(
    county_fips: str, bedrooms: int, exclude_anomalous_period: bool
) -> RentGrowthBands:
    """Bands from the HUD schedule — the fallback, normalised to the shared shape.

    The 2020-2022 window becomes FY2020-2022 here: the same question the price side is
    asked, put to a series published once a year. The cohort-shift screen is *not* applied
    — it existed to hold HUD's national step-ups out of the bands, and it is no longer a
    branch of the search (see `config.FMR_COHORT_SHIFT_EXCESS_PP` for where it went and
    why it was kept).
    """
    series = fmr_history.get_rent_growth_series(county_fips, bedrooms)
    excluded = config.FMR_ANOMALOUS_FISCAL_YEARS if exclude_anomalous_period else ()
    bands = fmr_history.compute_rent_growth_bands(series, exclude_years=excluded)

    if not bands.available:
        return RentGrowthBands(
            available=False,
            source=SOURCE_FMR,
            unavailable_reason=bands.unavailable_reason,
            area_name=bands.area_name or None,
            bedrooms=bedrooms,
        )

    return RentGrowthBands(
        available=True,
        source=SOURCE_FMR,
        source_description=(
            "HUD Fair Market Rent published schedule, annual, at the subject's county"
        ),
        resolution=bands.resolution,
        area_name=bands.area_name or None,
        base_yoy_pct=bands.base_yoy_pct,
        optimistic_yoy_pct=bands.optimistic_yoy_pct,
        pessimistic_yoy_pct=bands.pessimistic_yoy_pct,
        n_yoy_observations=bands.n_yoy_observations,
        first_observation=f"FY{bands.first_year}" if bands.first_year else None,
        last_observation=f"FY{bands.last_year}" if bands.last_year else None,
        anomalous_period_excluded=exclude_anomalous_period,
        optimistic_year=bands.optimistic_year,
        pessimistic_year=bands.pessimistic_year,
        bedrooms=bedrooms,
    )


def get_rent_growth_bands(
    county_fips: str, bedrooms: Optional[int], exclude_anomalous_period: bool
) -> RentGrowthBands:
    """ZORI where it reaches, the HUD schedule where it does not.

    `bedrooms` is only consulted on the fallback, and its absence is only fatal there:
    ZORI publishes one figure per county across unit types, so a subject with no resolved
    bedroom count still gets a rent projection where FMR would have refused one. That is a
    coverage gain #21 did not set out to make and it is worth stating, because the
    Extractor's bedroom parse is the single most common thing to fail on a real listing.
    """
    bands = zori_bands(county_fips, exclude_anomalous_period)
    if bands is not None:
        return bands

    if bedrooms is None:
        return RentGrowthBands(
            available=False,
            unavailable_reason=(
                "No market rent index covers this county, and the published Fair Market "
                "Rent schedule that would have served instead is quoted per bedroom "
                "count — which this listing did not state. Rent growth is measured on "
                "the same reference the rent estimate was anchored to, and across the "
                "published schedule the bedroom fields move by a median 2.16 percentage "
                "points within a single area-year, which is too much to substitute a "
                "default for."
            ),
        )
    return fmr_bands(county_fips, bedrooms, exclude_anomalous_period)
