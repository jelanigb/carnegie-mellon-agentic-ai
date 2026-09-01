"""Load and query the Redfin Housing Market Tracker extract (2-4 unit multi-family).

Why this module exists
----------------------
This is the appreciation source for the Scenario/Forecast agent
(docs/implementation_plan.md §2). It is the *only* one: Redfin's Home Price Index covers
single-family homes and has no multi-family series, so the Housing Market Tracker
filtered to `PROPERTY TYPE = Multi-Family (2-4 Units)` is what grounds the
optimistic/base/pessimistic bands. Small multi-family is bought by investors pricing off
cap rates rather than by owner-occupants, so an asset-matched trend line is an accuracy
decision, not a cosmetic one.

Three transformations happen here rather than downstream, and each exists for a reason:

1. **Filter to the target metros at load.** The extract carries 943 metros; this
   pipeline uses Redfin only for per-deal inference lookups, never for training, so it
   never needs more than the markets the system admits subjects from. Reading 38 columns
   for 943 metros to answer a question about four is wasted memory and a wider surface
   for a wrong-region bug. **The membership comes from `config.REDFIN_TARGET_METROS`
   (U8.4c)** — it lived here as a trio-only constant from before New York entered the
   demo, and downstream text reported that filter's output as "Redfin doesn't cover New
   York", which a check of the raw extract found to be false. The load now *asserts*
   every configured region exists in the extract, so the failure mode is loud.

2. **Apply a minimum-price floor before any aggregation.** See `MIN_SALE_PRICE_USD`
   below for the number and the evidence behind it.

3. **Compute a trailing rolling median locally.** §2 specifies a rolling 3-month
   frequency; the extract on disk is `Monthly` (Gap 2 in §2). Computing the window here
   rather than re-downloading keeps the smoothing width a tunable rather than a property
   of a file, and produces the same series. One caveat stated plainly: a median of three
   monthly medians is not the pooled median of three months of transactions. The pooled
   version requires transaction-level data Redfin does not publish, and the difference is
   immaterial against a series whose purpose is directional banding.

Flag-worthy conditions are **returned as data**, never printed or raised. `GrowthBands`
carries `includes_anomalous_period` and `source_description`; the Scenario agent converts
those into `anomalous_period_included` and `appreciation_source` `Flag` objects. Keeping
the judgment here and the flag construction there is what stops this module from needing
to import `state.py`.

Run: .venv/bin/python tools/redfin_data.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Allow `import config` when this module is run directly as a script, not only when
# imported from the src/ root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools import growth_bands

REDFIN_CSV = (
    config.DATA_DIR
    / "redfin_property_types_monthly_all_metros_multi_family_2_4_units_2018_Jan_to_2026_Jun.csv"
)

# Source column names. The extract's headers carry unit suffixes ("($)", "(%)"), which
# are easy to mistype silently, so they are named once here.
COL_PERIOD_BEGIN = "PERIOD BEGIN"
COL_REGION_NAME = "REGION NAME"
COL_REGION_TYPE = "REGION TYPE"
COL_PROPERTY_TYPE = "PROPERTY TYPE"
COL_FREQUENCY = "FREQUENCY"
COL_HOMES_SOLD = "HOMES SOLD"
COL_MEDIAN_SALE_PRICE = "MEDIAN SALE PRICE NSA ($)"

_USECOLS = [
    COL_PERIOD_BEGIN,
    COL_REGION_NAME,
    COL_REGION_TYPE,
    COL_PROPERTY_TYPE,
    COL_FREQUENCY,
    COL_HOMES_SOLD,
    COL_MEDIAN_SALE_PRICE,
]

# The markets the system admits subjects from, mapped to the extract's own `REGION NAME`
# spelling. Defined in config.py (U8.4c) — see the history there; the module alias stays
# because every consumer (the valuation benchmark, the forecast's price side, the MCP
# server's tool descriptions) reads it under this name.
TARGET_METROS: dict[str, str] = config.REDFIN_TARGET_METROS

# --- Tunables. The header here used to say these "move to config.py in U1, because
# --- config.py does not exist yet" — written before it did. Two have since moved on the
# --- occasion that made them shared rather than on a scheduled sweep, and the rest are
# --- named and justified below.

# Smoothing width, in periods. §2 specifies a rolling 3-month series; the extract is
# Monthly, so three periods is three months. Trailing (not centered) because a forecast
# agent may only use information available as of the period it is standing on.
ROLLING_WINDOW_PERIODS = 3

# Minimum plausible metro-level median sale price.
#
# Sourced from config.py rather than defined here: per the engineering standards in §8,
# config.py is the single home for tunable parameters. This value previously lived in
# both files with *different* numbers ($10k here, $20k there), which meant tuning the
# documented knob would silently have changed nothing. The evidence for $10,000 is
# recorded alongside the value in config.py.
#
# The empirical work that chose it is summarized there:
#   - 63 of 58,863 non-null rows (0.107%) fall below $10,000, 90.5% of them single-sale.
#     Lowest values are $1 (Warren PA), $101, $500, $550 - not real market prices.
#   - A $20,000 floor drops 294 rows (0.499%); in the $10-20k band the single-sale share
#     falls to 72.7% and some metros show a sustained cheap tail, i.e. real distressed
#     activity. $20k would delete observations rather than clean them.
MIN_SALE_PRICE_USD = config.REDFIN_MIN_MEDIAN_SALE_PRICE

# Periods per year in this extract, used for the year-over-year lag. Monthly data.
PERIODS_PER_YEAR = growth_bands.PERIODS_PER_YEAR

# The band estimator's own tunables. They described one series when this module was the
# only one banded; #21 puts the rent side through the same function, so they now live in
# `config.py` and are re-exported here because every existing consumer — the forecast
# agent, `scripts/growth_correlation.py`, `scripts/fmr_history_evidence.py` — reads them
# under these names.
SUSTAINED_STRETCH_PERIODS = config.SUSTAINED_STRETCH_PERIODS
ANOMALOUS_PERIOD_START = growth_bands.ANOMALOUS_PERIOD_START
ANOMALOUS_PERIOD_END = growth_bands.ANOMALOUS_PERIOD_END

# What this series actually is, in the words the report should use. Mirrors
# DealState.appreciation_source in §5.
#
# **This was an `AppreciationTier` enum until U6 (Aug 24, 2026), and the ladder it
# belonged to turned out to have one rung.** `zip_multifamily` is closed on evidence -
# the ZIP extract carries a median 2 homes sold per ZIP-period, so a year-over-year rate
# off it is noise - and `metro_all_residential` is closed by decision: no such extract
# exists in this project, and §2's asset-match argument says a 2-4 unit forecast should
# not fall back onto single-family dynamics anyway. A three-member type advertising a
# fallback the system cannot reach is a claim about the design that the build does not
# support, so the type went and a description stayed. The closed rungs are recorded in
# §7 where closed decisions live.
SERIES_DESCRIPTION = "Redfin metro-level Multi-Family (2-4 units) median sale price"


@dataclass(frozen=True)
class AppreciationSeries:
    """One metro's smoothed appreciation series, with the provenance needed to flag it.

    `frame` is indexed by period start and carries `median_sale_price` (raw, post-floor)
    alongside `rolling_median` and `yoy_pct`. The scalar fields record what was done to
    produce it, so a downstream agent can disclose the treatment without re-deriving it.
    """

    metro: str
    region_name: str
    source_description: str
    frame: pd.DataFrame
    window_periods: int
    price_floor: float
    periods_dropped_below_floor: int
    first_period: pd.Timestamp
    last_period: pd.Timestamp

    @property
    def n_periods(self) -> int:
        return int(self.frame["median_sale_price"].notna().sum())


@dataclass(frozen=True)
class GrowthBands:
    """Optimistic / base / pessimistic year-over-year growth, plus its own provenance.

    Every field a Flag would need is here as data. Nothing in this module prints or
    raises on a flag-worthy condition: `includes_anomalous_period` and `source_description` are
    inputs the Scenario/Forecast agent turns into `anomalous_period_included` and
    `appreciation_source` flags respectively.
    """

    metro: str
    source_description: str

    # The three bands, in percent per year.
    base_yoy_pct: float          # long-run mean growth
    optimistic_yoy_pct: float    # best sustained stretch observed
    pessimistic_yoy_pct: float   # worst sustained stretch observed

    # Supporting detail.
    median_yoy_pct: float
    stdev_yoy_pct: float
    n_yoy_observations: int
    sustained_window_periods: int
    optimistic_stretch_end: Optional[pd.Timestamp]
    pessimistic_stretch_end: Optional[pd.Timestamp]

    # Flag-worthy provenance, returned rather than acted on.
    includes_anomalous_period: bool
    anomalous_period_share: float          # share of YoY observations inside 2020-2022
    anomalous_period_excluded: bool        # True if the caller asked for them removed
    optimistic_stretch_in_anomalous_period: bool
    price_floor: float
    periods_dropped_below_floor: int
    window_periods: int


def load_redfin(
    path: Path = REDFIN_CSV,
    metros: Optional[dict[str, str]] = None,
    price_floor: float = MIN_SALE_PRICE_USD,
) -> pd.DataFrame:
    """Read the extract, filter to the target metros, and mark sub-floor periods.

    Returns a tidy frame with one row per (metro, period) and columns
    `metro`, `region_name`, `period`, `homes_sold`, `median_sale_price`,
    `below_price_floor`.

    The floor is *marked* here and *applied* in `get_appreciation_series`. Dropping
    at load would be simpler but would discard the count of what was dropped, which is
    itself reportable evidence about a metro's data quality. The guarantee §2 asks for
    still holds: nothing is aggregated between marking and dropping.
    """
    metros = metros if metros is not None else TARGET_METROS
    wanted = set(metros.values())

    raw = pd.read_csv(path, usecols=_USECOLS)
    frame = raw[raw[COL_REGION_NAME].isin(wanted)].copy()

    # Loud, not silent (U8.4c). A configured region absent from the extract used to
    # produce an empty per-metro frame that read downstream as "Redfin doesn't cover
    # this metro" — which is how a stale filter got reported as a coverage fact for
    # months. A missing region is a configuration or file defect and must say so.
    missing = wanted - set(frame[COL_REGION_NAME].unique())
    if missing:
        raise ValueError(
            f"Configured Redfin regions absent from the extract at {path.name}: "
            f"{sorted(missing)}. Either the region spelling in "
            f"config.REDFIN_TARGET_METROS is wrong or the extract is stale."
        )

    label_by_region = {region: label for label, region in metros.items()}
    frame["metro"] = frame[COL_REGION_NAME].map(label_by_region)
    frame["region_name"] = frame[COL_REGION_NAME]
    frame["period"] = pd.to_datetime(frame[COL_PERIOD_BEGIN])
    frame["homes_sold"] = pd.to_numeric(frame[COL_HOMES_SOLD], errors="coerce")
    frame["median_sale_price"] = pd.to_numeric(
        frame[COL_MEDIAN_SALE_PRICE], errors="coerce"
    )
    frame["below_price_floor"] = frame["median_sale_price"] < price_floor

    columns = [
        "metro",
        "region_name",
        "period",
        "homes_sold",
        "median_sale_price",
        "below_price_floor",
    ]
    return (
        frame[columns]
        .sort_values(["metro", "period"])
        .reset_index(drop=True)
    )


def get_appreciation_series(
    frame: pd.DataFrame,
    metro: str,
    window_periods: int = ROLLING_WINDOW_PERIODS,
    price_floor: float = MIN_SALE_PRICE_USD,
    source_description: str = SERIES_DESCRIPTION,
) -> AppreciationSeries:
    """Build one metro's smoothed appreciation series.

    Order of operations is load-bearing and matches §2: drop sub-floor periods, then
    reindex onto a complete monthly calendar, then smooth, then difference. Reindexing
    before smoothing matters because a dropped or absent period would otherwise make a
    "12-period" year-over-year comparison span something other than twelve months.
    """
    metro_rows = frame[frame["metro"] == metro]
    if metro_rows.empty:
        raise KeyError(
            f"Metro {metro!r} not present in the loaded frame. "
            f"Available: {sorted(frame['metro'].unique())}"
        )

    region_name = str(metro_rows["region_name"].iloc[0])
    kept = metro_rows[~metro_rows["below_price_floor"]]
    dropped = int(metro_rows["below_price_floor"].sum())

    series = (
        kept.set_index("period")[["median_sale_price", "homes_sold"]]
        .sort_index()
    )
    # Complete monthly calendar: a gap must read as a gap, not as a shorter lag.
    calendar = pd.date_range(series.index.min(), series.index.max(), freq="MS")
    series = series.reindex(calendar)
    series.index.name = "period"

    series["rolling_median"] = (
        series["median_sale_price"]
        .rolling(window=window_periods, min_periods=window_periods)
        .median()
    )
    series["yoy_pct"] = (
        series["rolling_median"].pct_change(periods=PERIODS_PER_YEAR) * 100.0
    )

    return AppreciationSeries(
        metro=metro,
        region_name=region_name,
        source_description=source_description,
        frame=series,
        window_periods=window_periods,
        price_floor=price_floor,
        periods_dropped_below_floor=dropped,
        first_period=series.index.min(),
        last_period=series.index.max(),
    )


def compute_growth_bands(
    series: AppreciationSeries,
    sustained_window_periods: int = SUSTAINED_STRETCH_PERIODS,
    exclude_anomalous_period: bool = False,
) -> GrowthBands:
    """Derive optimistic / base / pessimistic year-over-year bands from a series.

    The arithmetic moved to `tools/growth_bands.py` at U9.3 and is unchanged there; what
    stays here is the part that is about *this* series — pulling the year-over-year column
    off the frame, naming the metro when the filtering leaves nothing, and attaching the
    price side's own provenance to the result. `growth_bands.bands_from_yoy` returns None
    rather than raising for exactly that reason: it does not know which series it was
    handed, and this function does.

    See the estimator's docstring for what "sustained" means and why
    `exclude_anomalous_period` is a fork the caller chooses rather than a setting.
    """
    bands = growth_bands.bands_from_yoy(
        series.frame["yoy_pct"],
        sustained_window_periods=sustained_window_periods,
        exclude_anomalous_period=exclude_anomalous_period,
    )
    if bands is None:
        raise ValueError(
            f"No year-over-year observations for {series.metro} after filtering. "
            f"Series covers {series.first_period.date()} to {series.last_period.date()}."
        )

    return GrowthBands(
        metro=series.metro,
        source_description=series.source_description,
        base_yoy_pct=bands.base_yoy_pct,
        optimistic_yoy_pct=bands.optimistic_yoy_pct,
        pessimistic_yoy_pct=bands.pessimistic_yoy_pct,
        median_yoy_pct=bands.median_yoy_pct,
        stdev_yoy_pct=bands.stdev_yoy_pct,
        n_yoy_observations=bands.n_yoy_observations,
        sustained_window_periods=bands.sustained_window_periods,
        optimistic_stretch_end=bands.optimistic_stretch_end,
        pessimistic_stretch_end=bands.pessimistic_stretch_end,
        includes_anomalous_period=bands.includes_anomalous_period,
        anomalous_period_share=bands.anomalous_period_share,
        anomalous_period_excluded=bands.anomalous_period_excluded,
        optimistic_stretch_in_anomalous_period=(
            bands.optimistic_stretch_in_anomalous_period
        ),
        price_floor=series.price_floor,
        periods_dropped_below_floor=series.periods_dropped_below_floor,
        window_periods=series.window_periods,
    )


def _print_series_tail(series: AppreciationSeries, periods: int = 12) -> None:
    tail = series.frame.tail(periods)
    print(f"  last {periods} periods (raw monthly vs. "
          f"{series.window_periods}-period rolling median):")
    print(f"    {'period':<10} {'homes sold':>10} {'raw median':>13} "
          f"{'rolling':>13} {'YoY %':>8}")
    for period, row in tail.iterrows():
        sold = "-" if pd.isna(row["homes_sold"]) else f"{row['homes_sold']:,.0f}"
        raw = "-" if pd.isna(row["median_sale_price"]) else f"${row['median_sale_price']:,.0f}"
        roll = "-" if pd.isna(row["rolling_median"]) else f"${row['rolling_median']:,.0f}"
        yoy = "-" if pd.isna(row["yoy_pct"]) else f"{row['yoy_pct']:+.1f}"
        print(f"    {period.date().isoformat():<10} {sold:>10} {raw:>13} "
              f"{roll:>13} {yoy:>8}")


def _print_bands(label: str, bands: GrowthBands) -> None:
    print(f"  {label}")
    print(f"    optimistic (best {bands.sustained_window_periods}-period stretch): "
          f"{bands.optimistic_yoy_pct:+.2f}% / yr "
          f"(ending {bands.optimistic_stretch_end.date()})")
    print(f"    base       (long-run mean YoY):              "
          f"{bands.base_yoy_pct:+.2f}% / yr")
    print(f"    pessimistic(worst {bands.sustained_window_periods}-period stretch): "
          f"{bands.pessimistic_yoy_pct:+.2f}% / yr "
          f"(ending {bands.pessimistic_stretch_end.date()})")
    print(f"    median YoY {bands.median_yoy_pct:+.2f}%   "
          f"stdev {bands.stdev_yoy_pct:.2f}   n={bands.n_yoy_observations}")
    print(f"    flag data: source={bands.source_description!r}  "
          f"includes_anomalous_period={bands.includes_anomalous_period}  "
          f"anomalous_share={bands.anomalous_period_share:.1%}  "
          f"optimistic_stretch_in_anomalous_period="
          f"{bands.optimistic_stretch_in_anomalous_period}")


def main() -> None:
    """Print each target metro's series and bands so the output can be checked by eye."""
    print(f"Loading {REDFIN_CSV.name}")
    frame = load_redfin()
    print(f"Filtered to {len(TARGET_METROS)} target metros: "
          f"{len(frame):,} rows (extract holds 943 metros)")
    print(f"Price floor: ${MIN_SALE_PRICE_USD:,} | "
          f"rolling window: {ROLLING_WINDOW_PERIODS} periods | "
          f"sustained stretch: {SUSTAINED_STRETCH_PERIODS} periods\n")

    for metro in TARGET_METROS:
        series = get_appreciation_series(frame, metro)
        print("=" * 78)
        print(f"{metro}  —  {series.region_name}")
        print(f"  source: {series.source_description}")
        print(f"  {series.n_periods} periods, "
              f"{series.first_period.date()} to {series.last_period.date()}; "
              f"{series.periods_dropped_below_floor} period(s) dropped below the "
              f"${series.price_floor:,.0f} floor")
        _print_series_tail(series)
        print()
        _print_bands("bands — full history (2020-2022 included):",
                     compute_growth_bands(series))
        print()
        _print_bands("bands — 2020-2022 excluded:",
                     compute_growth_bands(series, exclude_anomalous_period=True))
        print()

    print("=" * 78)
    print("Flag-worthy conditions above are returned as GrowthBands fields, not raised:")
    print("  includes_anomalous_period -> Flag(kind='anomalous_period_included', 'info')")
    print("  source_description        -> Flag(kind='appreciation_source', 'info')")
    print("Constructing those Flag objects is the Scenario/Forecast agent's job (§2, §5).")


if __name__ == "__main__":
    main()
