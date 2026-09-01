"""HUD FMR published history as a rent-growth series (§7 decision #16, U6).

Why this module exists
----------------------
The Scenario/Forecast agent needs a rent-growth rate, and §1 originally specified taking
one from Redfin's sale-price series. Measured against this project's own data before U6
was built, rent growth and price growth are **negatively** correlated across the
inference trio (pooled r = -0.309), so that series would have pointed the forecast the
wrong way. Rent growth needs a rent-native source, and HUD's published FMR history is
the one this project already has: FY2017 onward through the client in `hud_fmr.py`,
already cached, no new dependency.

It is also the only candidate that is *architecturally* consistent. The rent estimate is
`ratio x FMR` (§2), so projecting the FMR anchor forward while holding the structural
ratio constant forecasts rent by the same mechanism that produced the estimate - no
second normalization basis, no new vintage problem.

Three things the measurement changed about the design
-----------------------------------------------------
Reproduce all three with `scripts/fmr_history_evidence.py`.

1. **The anomalous window is not the same years on the two series.**
   `config.ANOMALOUS_PERIOD` is calendar 2020-2022, which is correct for Redfin and
   wrong here. On FMR those three fiscal years are ordinary (cohort medians 2.73 / 5.22
   / 3.09 against a 4.17% baseline); the surge lands in **FY2023 and FY2024**, because
   FMR is administrative and lags - the FY2024 schedules were published in Sept 2023 on
   2021-22 data. Applying the price window to this series would drop three normal years
   and keep both distorted ones. Hence a separate screen rather than a shared constant.

2. **"Methodology jump" is an attribution this data cannot support, so it is not
   claimed.** The plan named Chicago's +19.0% FY2024 as a HUD methodology change. All
   ten areas in the panel moved that year (median 11.65%, minimum 6.5%); Chicago's move
   is 61% cohort and 7.4pp local, and Los Angeles's +14.5% is mostly cohort. A
   cohort-wide shift is equally consistent with a methodology change and with the
   2021-22 market surge reaching an administrative series two years late. What is
   observable is *whether every area moved at once*, so that is what
   `cohort_shift_years` measures and what the report says. Zillow ZORI, being
   market-observed, is what could attribute it later (decision #16).

3. **The growth rate is county-level even where the rent anchor is ZIP-level.** HUD's
   Small Area FMR history is too shallow to difference: the panel has nine years of ZIP
   schedules for Chicago, **two** for Los Angeles and Cleveland, and none for New York,
   Newark or Boston. Two years is one YoY observation. So `resolution` is always
   `"county"` here, and the Valuation agent's ZIP-level anchor pairs with a county-level
   growth rate. That is a disclosure the report must make, not a defect to hide - the
   alternative is a growth rate for one metro and none for the other two.

Flag-worthy conditions are **returned as data**, never printed or raised, exactly as in
`redfin_data.py` and for the same reason: it keeps this module from importing
`state.py`. `RentGrowthBands` carries everything the Scenario agent needs to construct
its flags.

Run: .venv/bin/python tools/fmr_history.py
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools import hud_fmr

# Which spatial resolution a growth rate was differenced at. A constant rather than a
# literal at each use site because the value is compared in the agent and rendered in
# the report; see point 3 in the module docstring for why it is currently always this.
RESOLUTION_COUNTY = "county"


@dataclass(frozen=True)
class CohortPanel:
    """Every HUD FMR area this project touches, FY2017 onward, all five bedroom fields.

    The cohort is what makes a national move distinguishable from a local one. A single
    metro's +19% tells you nothing on its own: it could be that metro, or it could be
    every metro. Committed to disk rather than pulled per run - deriving it live costs
    roughly 100 API calls on a cold cache, inside a node that runs once per deal.

    **Its limits, stated because the panel looks more authoritative than it is.** These
    are the ten HUD areas behind this project's own training metros, not a national
    sample, and they skew large and coastal/midwest. The FY2023-24 shift is visible in
    all ten independently, which is what makes the *direction* trustworthy; the 4.17%
    baseline is a property of this panel and would move with a different one.
    """

    built_at: str
    first_year: int
    last_year: int
    # area name -> bedroom field -> fiscal year -> FMR dollars
    rents: dict[str, dict[str, dict[int, float]]]
    # area name -> the entityid it was pulled with, for reproduction
    entityids: dict[str, str]

    @property
    def area_names(self) -> list[str]:
        return sorted(self.rents)

    @property
    def n_areas(self) -> int:
        return len(self.rents)

    def yoy(self, area: str, bedroom_field: str) -> dict[int, float]:
        """Year-over-year percent change for one area and bedroom count."""
        by_year = self.rents.get(area, {}).get(bedroom_field, {})
        return {
            year: (by_year[year] / by_year[year - 1] - 1) * 100.0
            for year in sorted(by_year)
            if year - 1 in by_year and by_year[year - 1]
        }

    def cohort_medians(self, bedroom_field: str) -> dict[int, float]:
        """Median YoY across areas, per fiscal year.

        Median rather than mean: one area can carry a genuine local shock (Jersey City
        FY2026, +20.2%) and a mean would let it move the baseline it is supposed to be
        measured against.
        """
        per_year: dict[int, list[float]] = {}
        for area in self.rents:
            for year, value in self.yoy(area, bedroom_field).items():
                per_year.setdefault(year, []).append(value)
        return {year: statistics.median(v) for year, v in sorted(per_year.items()) if v}

    def baseline_pct(self, bedroom_field: str) -> Optional[float]:
        """The long-run level the cohort medians are judged against.

        Median of the yearly cohort medians - a median of medians, which is deliberate.
        The quantity being estimated is "an ordinary year for this panel," and a mean
        over nine years would let the two shifted ones raise the bar they are being
        compared to.
        """
        medians = list(self.cohort_medians(bedroom_field).values())
        return statistics.median(medians) if medians else None

    def cohort_shift_years(
        self,
        bedroom_field: str,
        excess_pp: float = config.FMR_COHORT_SHIFT_EXCESS_PP,
    ) -> tuple[int, ...]:
        """Fiscal years where the whole panel moved together, well above baseline.

        See `config.FMR_COHORT_SHIFT_EXCESS_PP` for why the threshold sits in a wide
        indifference band rather than on a boundary.
        """
        baseline = self.baseline_pct(bedroom_field)
        if baseline is None:
            return ()
        return tuple(
            year
            for year, median in self.cohort_medians(bedroom_field).items()
            if median - baseline >= excess_pp
        )


@dataclass(frozen=True)
class RentGrowthSeries:
    """One county's FMR history for one bedroom count, plus what it cost to build.

    `years_unavailable` is not an error list to be swallowed. HUD serves some
    county-years and not others, and a band computed over six years is weaker than one
    computed over nine; the caller is expected to disclose which it got.
    """

    entityid: str
    area_name: str
    bedrooms: int
    bedroom_field: str
    bedroom_cap_exceeded: bool
    resolution: str
    fmr_by_year: dict[int, float]
    years_unavailable: tuple[int, ...]

    @property
    def yoy_by_year(self) -> dict[int, float]:
        return {
            year: (self.fmr_by_year[year] / self.fmr_by_year[year - 1] - 1) * 100.0
            for year in sorted(self.fmr_by_year)
            if year - 1 in self.fmr_by_year and self.fmr_by_year[year - 1]
        }

    @property
    def first_year(self) -> Optional[int]:
        return min(self.fmr_by_year) if self.fmr_by_year else None

    @property
    def last_year(self) -> Optional[int]:
        return max(self.fmr_by_year) if self.fmr_by_year else None


@dataclass(frozen=True)
class RentGrowthBands:
    """Optimistic / base / pessimistic annual rent growth, plus its own provenance.

    Every field the Scenario agent would need to raise a flag is here as data. Nothing
    in this module constructs a `Flag`; see the module docstring.

    `available` is False when the series could not support a band at all - too few
    observations after screening. That is a reportable finding rather than an exception,
    and `unavailable_reason` carries the sentence the report should print.
    """

    available: bool
    entityid: str
    area_name: str
    bedrooms: int
    resolution: str
    unavailable_reason: Optional[str] = None

    # The three bands, in percent per year: the worst fiscal year observed, the
    # geometric mean of the retained years, the best fiscal year observed. See the
    # `FMR_BAND_*` block in config.py for the three constructions this was chosen over,
    # including the one rejected because its base case landed outside its own band.
    base_yoy_pct: Optional[float] = None
    optimistic_yoy_pct: Optional[float] = None
    pessimistic_yoy_pct: Optional[float] = None

    # Which fiscal year each outer band is. Carried because a band that names its year
    # is checkable - "the worst year on record, FY2018" is a claim a reader can go and
    # verify, where "-4.2%" alone is not.
    optimistic_year: Optional[int] = None
    pessimistic_year: Optional[int] = None

    # Disclosed beside the bands, never as the bands (config.FMR_IQR_*_PERCENTILE).
    # Distinguishes an isolated spike from a cluster.
    iqr_lower_yoy_pct: Optional[float] = None
    iqr_upper_yoy_pct: Optional[float] = None

    # Supporting detail.
    median_yoy_pct: Optional[float] = None
    arithmetic_mean_yoy_pct: Optional[float] = None
    n_yoy_observations: int = 0
    first_year: Optional[int] = None
    last_year: Optional[int] = None

    # Cohort-shift provenance, returned rather than acted on.
    cohort_shift_years_detected: tuple[int, ...] = ()
    cohort_shift_years_excluded: tuple[int, ...] = ()
    cohort_shift_excluded: bool = False
    cohort_baseline_pct: Optional[float] = None
    cohort_n_areas: int = 0

    # Fiscal years where *this* area departed from its own cohort by more than
    # `config.FMR_LOCAL_DEVIATION_PP`. Disclosed, never excluded: a local move is the
    # market signal a forecast should be carrying, unlike a national schedule change.
    local_deviation_years: tuple[int, ...] = ()

    years_unavailable: tuple[int, ...] = ()

    def projected_multiple(self, rate_pct: float, years: int) -> float:
        """Compound `rate_pct` over `years`. Here rather than in the agent so the two
        series' projections cannot drift apart in how they compound."""
        return (1.0 + rate_pct / 100.0) ** years


def _geometric_mean_pct(rates_pct: list[float]) -> float:
    """Average annual rate that compounds to the same total as `rates_pct` did.

    The arithmetic mean is the wrong estimator for a quantity that compounds - it
    overstates cumulative growth, measured here at 0.07-0.16pp/yr across the inference
    trio. The retained years may be non-consecutive once the cohort-shift screen has run
    (FY2018-2022 plus FY2025-2026), so this is the geometric mean of the retained annual
    factors rather than a first-to-last CAGR, which would silently span the excluded
    years.
    """
    product = 1.0
    for rate in rates_pct:
        product *= 1.0 + rate / 100.0
    return (product ** (1.0 / len(rates_pct)) - 1.0) * 100.0


def _percentile(sorted_values: list[float], percentile: float) -> float:
    """Linear-interpolated percentile, matching numpy's default `linear` method.

    Written out rather than imported so this module stays free of pandas/numpy - it is
    reached from a per-deal node, and `hud_fmr.py` beneath it has no heavy imports
    either.
    """
    if not sorted_values:
        raise ValueError("no values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (
        position - lower
    )


def load_cohort_panel(
    path: Path = config.FMR_COHORT_PANEL_PATH,
) -> Optional[CohortPanel]:
    """Read the committed panel, or None if it has not been built.

    None rather than an exception: a missing panel degrades the forecast to "no cohort
    screen was applied," which the report can state, rather than killing a run over a
    file that only refines the band.
    """
    if not path.exists():
        return None
    raw = json.loads(path.read_text())
    rents = {
        area: {
            bedroom_field: {int(year): float(rent) for year, rent in by_year.items()}
            for bedroom_field, by_year in by_field.items()
        }
        for area, by_field in raw["rents"].items()
    }
    return CohortPanel(
        built_at=raw["built_at"],
        first_year=int(raw["first_year"]),
        last_year=int(raw["last_year"]),
        rents=rents,
        entityids=raw["entityids"],
    )


def get_rent_growth_series(
    entityid: str,
    bedrooms: int,
    client: Optional[hud_fmr.HudFmrClient] = None,
    first_year: int = config.FMR_HISTORY_FIRST_YEAR,
    last_year: Optional[int] = None,
) -> RentGrowthSeries:
    """Pull one county's FMR history for one bedroom count.

    **Bedroom count is the subject's own, not a fixed Two-Bedroom standard**, and that
    is measured rather than assumed: within a county-year the five bedroom fields move
    by a median 2.16pp against a median level of ~5pp (p90 4.19pp, max 5.28pp). That is
    too much to treat as noise. Using the subject's own count also keeps the growth rate
    on the same field as the anchor the Valuation agent multiplied by.

    County resolution only; see point 3 in the module docstring.

    `last_year` defaults to whatever HUD currently serves, discovered from a no-year
    call rather than read from a constant. That follows `agents/valuation_rent.py`,
    which anchors against the latest schedule and records `anchor["year"]` after the
    fact: a configured "current year" is a value that goes stale silently every October.
    """
    client = client or hud_fmr.HudFmrClient()
    bedroom_field, bedroom_cap_exceeded = hud_fmr.bedroom_field(bedrooms)

    if last_year is None:
        try:
            last_year = int(client.get_fmr(entityid).year)
        except (hud_fmr.HudFmrApiError, KeyError, TypeError, ValueError, RuntimeError):
            # No current schedule means no series worth building. Returning an empty
            # one lets the caller report "no rent-growth band" through the same path
            # that handles a too-short history, rather than through an exception.
            return RentGrowthSeries(
                entityid=entityid,
                area_name="",
                bedrooms=bedrooms,
                bedroom_field=bedroom_field,
                bedroom_cap_exceeded=bedroom_cap_exceeded,
                resolution=RESOLUTION_COUNTY,
                fmr_by_year={},
                years_unavailable=(),
            )

    fmr_by_year: dict[int, float] = {}
    unavailable: list[int] = []
    area_name = ""
    for year in range(first_year, last_year + 1):
        try:
            result = client.get_fmr(entityid, year=year)
        except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError):
            unavailable.append(year)
            continue
        rent = result.rents.get(bedroom_field)
        if rent is None:
            unavailable.append(year)
            continue
        fmr_by_year[year] = float(rent)
        area_name = area_name or result.area_name

    return RentGrowthSeries(
        entityid=entityid,
        area_name=area_name,
        bedrooms=bedrooms,
        bedroom_field=bedroom_field,
        bedroom_cap_exceeded=bedroom_cap_exceeded,
        resolution=RESOLUTION_COUNTY,
        fmr_by_year=fmr_by_year,
        years_unavailable=tuple(unavailable),
    )


def compute_rent_growth_bands(
    series: RentGrowthSeries,
    panel: Optional[CohortPanel] = None,
    exclude_cohort_shift_years: bool = False,
    exclude_years: tuple[int, ...] = (),
) -> RentGrowthBands:
    """Derive optimistic / base / pessimistic annual rent growth from an FMR series.

    **Two exclusions, and they are not alternatives — they answer different questions.**

    `exclude_years` holds out fiscal years the caller names. `tools/rent_growth.py` passes
    `config.FMR_ANOMALOUS_FISCAL_YEARS` through it, so the fallback path is asked the same
    2020-2022 question the price side is asked, which is what decision #21 made the
    depth-1 rent fork.

    `exclude_cohort_shift_years` holds out the years *this panel* found every area moving
    together in. It was the Scenario agent's fork through U8 and is no longer: the forecast
    stopped reading the FMR schedule on any path a demo deal takes, so a screen for HUD's
    administrative step-ups has nothing to screen there. It stays because
    `scripts/growth_correlation.py` and `scripts/fmr_history_evidence.py` need it — removing
    FY2023-24 is what collapsed the rent/price correlation from -0.317 to -0.197, and that
    is a third of the evidence for #21. The machinery that retired itself is the machinery
    that reproduces the retirement.
    """
    yoy = series.yoy_by_year
    detected: tuple[int, ...] = ()
    baseline: Optional[float] = None
    local_deviation: tuple[int, ...] = ()
    n_areas = 0

    if panel is not None:
        detected = panel.cohort_shift_years(series.bedroom_field)
        baseline = panel.baseline_pct(series.bedroom_field)
        n_areas = panel.n_areas
        cohort = panel.cohort_medians(series.bedroom_field)
        local_deviation = tuple(
            year
            for year, value in yoy.items()
            if year in cohort
            and abs(value - cohort[year]) >= config.FMR_LOCAL_DEVIATION_PP
        )

    excluded = detected if (exclude_cohort_shift_years and panel is not None) else ()
    held_out = set(excluded) | set(exclude_years)
    kept = {year: value for year, value in yoy.items() if year not in held_out}

    common = dict(
        entityid=series.entityid,
        area_name=series.area_name,
        bedrooms=series.bedrooms,
        resolution=series.resolution,
        cohort_shift_years_detected=detected,
        cohort_shift_years_excluded=excluded,
        cohort_shift_excluded=bool(excluded),
        cohort_baseline_pct=baseline,
        cohort_n_areas=n_areas,
        local_deviation_years=local_deviation,
        years_unavailable=series.years_unavailable,
        n_yoy_observations=len(kept),
    )

    if len(kept) < config.FMR_HISTORY_MIN_YOY_OBSERVATIONS:
        reason = (
            f"HUD published {len(kept)} usable year-over-year observations for "
            f"{series.area_name or series.entityid} "
            f"({series.bedroom_field}), below the {config.FMR_HISTORY_MIN_YOY_OBSERVATIONS} "
            f"this project requires before quoting a growth range. No rent-growth band "
            f"was produced; a range over that few points describes the sample rather "
            f"than the market."
        )
        return RentGrowthBands(available=False, unavailable_reason=reason, **common)

    values = sorted(kept.values())
    best_year = max(kept, key=kept.get)
    worst_year = min(kept, key=kept.get)
    return RentGrowthBands(
        available=True,
        base_yoy_pct=_geometric_mean_pct(values),
        optimistic_yoy_pct=kept[best_year],
        pessimistic_yoy_pct=kept[worst_year],
        optimistic_year=best_year,
        pessimistic_year=worst_year,
        iqr_lower_yoy_pct=_percentile(values, config.FMR_IQR_LOWER_PERCENTILE),
        iqr_upper_yoy_pct=_percentile(values, config.FMR_IQR_UPPER_PERCENTILE),
        median_yoy_pct=statistics.median(values),
        arithmetic_mean_yoy_pct=statistics.mean(values),
        first_year=min(kept),
        last_year=max(kept),
        **common,
    )


def main() -> None:
    """Print the trio's rent-growth bands both ways. Smoke test, not evidence -
    `scripts/fmr_history_evidence.py` is the artifact."""
    panel = load_cohort_panel()
    if panel is None:
        print(
            f"No cohort panel at {config.FMR_COHORT_PANEL_PATH}. "
            f"Build it: .venv/bin/python scripts/fmr_history_evidence.py --build-panel"
        )
        return

    print(f"Panel: {panel.n_areas} HUD areas, FY{panel.first_year}-{panel.last_year}\n")
    client = hud_fmr.HudFmrClient()
    for label, entityid in (
        ("Los Angeles", "0603799999"),
        ("Chicago", "1703199999"),
        ("Cleveland", "3903599999"),
    ):
        series = get_rent_growth_series(entityid, bedrooms=2, client=client)
        for exclude in (False, True):
            bands = compute_rent_growth_bands(
                series, panel, exclude_cohort_shift_years=exclude
            )
            if not bands.available:
                print(f"{label:12s} exclude={exclude!s:5s}  {bands.unavailable_reason}")
                continue
            print(
                f"{label:12s} exclude={exclude!s:5s}  "
                f"pess {bands.pessimistic_yoy_pct:6.2f}% (FY{bands.pessimistic_year})  "
                f"base {bands.base_yoy_pct:5.2f}%  "
                f"opt {bands.optimistic_yoy_pct:6.2f}% (FY{bands.optimistic_year})   "
                f"n={bands.n_yoy_observations}  "
                f"IQR [{bands.iqr_lower_yoy_pct:.2f}, {bands.iqr_upper_yoy_pct:.2f}]"
            )
        print()


if __name__ == "__main__":
    main()
