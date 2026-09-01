"""The optimistic / base / pessimistic band estimator, independent of which series it reads.

Why this module exists
----------------------
The band arithmetic lived inside `tools/redfin_data.py` from U6, because the price series
was the only monthly series the forecast projected. Decision #21 re-sources rent growth
from HUD's annual FMR schedule to Zillow's monthly ZORI index, which makes both sides of
the forecast monthly and makes a single estimator possible — and `docs/design/evaluator.md`
Defect 3 is the reason it is necessary rather than merely tidy.

**Defect 3, in one line: the two bands were not comparable.** The rent side took extremes
over *single fiscal years* and the price side over *twelve-month sustained stretches*, which
made the rent band roughly 3x wider as an artifact of method rather than of market — 15.2
points against 5.3 on Los Angeles. Every pairing the Tree-of-Thought search produced
inherited that asymmetry, which is why rent appeared to outrun price under every combination
the search could reach. Two series scored by one function cannot drift that way again.

What this module is and is not
------------------------------
It is arithmetic over a year-over-year series: the worst sustained stretch, the mean, the
best sustained stretch, plus the provenance a report needs to discount them. It holds no
opinion about what the series measures, does not read a file, and does not construct a
`Flag` — `redfin_data` and the Scenario agent keep those responsibilities, for the reason
`redfin_data`'s own docstring gives: keeping the judgment here and the flag construction
there is what stops a data module from importing `state.py`.

Nothing in it is new. Every line was moved from `redfin_data.compute_growth_bands` and
`_sustained_means` unchanged, and `compute_growth_bands` now delegates to it, so the price
bands this project has published since U6 are byte-identical across the move.
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

# Periods per year, used for the year-over-year lag. Both series this estimator serves are
# monthly: Redfin's extract is published monthly, and ZORI is one observation per month.
# Structural rather than tunable — it is what "year over year" means on monthly data — so
# it stays here rather than in config.py.
PERIODS_PER_YEAR = 12

# `config` carries these as ISO strings so it need not import pandas; parsed once here
# rather than at every comparison.
ANOMALOUS_PERIOD_START = pd.Timestamp(config.ANOMALOUS_PERIOD_START)
ANOMALOUS_PERIOD_END = pd.Timestamp(config.ANOMALOUS_PERIOD_END)


@dataclass(frozen=True)
class SeriesBands:
    """Three bands over one year-over-year series, plus the provenance to weigh them.

    Deliberately narrower than `redfin_data.GrowthBands`, which wraps this and adds the
    price side's own provenance (its metro, its price floor, how many periods that floor
    dropped). A field belongs here only if it is a fact about *any* series; a field about
    where the numbers came from belongs to the caller that knows.
    """

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
    first_observation: Optional[pd.Timestamp]
    last_observation: Optional[pd.Timestamp]

    # How many distinct sustained stretches the outer bands were chosen from. Zero means
    # no contiguous run was long enough to fill even one window, and the bands fell back
    # to single-month extremes.
    #
    # **Two separate things go wrong as this number falls, and only the first is
    # obvious.** At zero the estimator quietly changes definition — "the worst sustained
    # stretch" becomes "the worst single month", which is Defect 3, the asymmetry this
    # module exists to close, reappearing inside the module that closed it. Above zero
    # but low, the definition holds and the *range* stops meaning anything: min and max
    # over three overlapping views of the same year are nearly the same number. Measured
    # across ZORI's 1,211 counties, median band width runs 0.13pp at 1-3 stretches,
    # 1.85pp at 4-11, and 6.15pp at 24-43 — so a thin series does not produce a visibly
    # unreliable forecast, it produces a **confident-looking** one.
    #
    # Returned rather than acted on, like every other field here. `tools/rent_growth.py`
    # is where it becomes a threshold.
    n_sustained_stretches: int

    # Flag-worthy provenance, returned rather than acted on.
    includes_anomalous_period: bool
    anomalous_period_share: float          # share of YoY observations inside 2020-2022
    anomalous_period_excluded: bool        # True if the caller asked for them removed
    optimistic_stretch_in_anomalous_period: bool


def window_levels(levels: pd.Series) -> pd.Series:
    """Trim a monthly level series to the shared forecast window, sorted and dated.

    **On levels, never on the differences, and that distinction decides published
    numbers.** A year-over-year observation dated 2018-06 is a comparison against
    2017-06; filtering the differences to "2018 onward" therefore admits a year of
    history that only one series has. Measured on Chicago, the two readings give
    pessimistic rent bands of +3.03%/yr and +1.58%/yr, and the lower one rests on a
    twelve-month stretch ending 2018-12 that the price series does not cover at all —
    which is the mismatched-span defect the window exists to remove, not an instance of
    it being removed. See `config.FORECAST_SERIES_WINDOW_START`.

    Accepts ZORI's string-keyed month index as readily as a DatetimeIndex, because the
    two series arrive differently shaped and normalising here is cheaper than at each
    call site.
    """
    series = levels.dropna()
    series.index = pd.to_datetime(series.index)
    series = series.sort_index()
    return series[series.index >= pd.Timestamp(config.FORECAST_SERIES_WINDOW_START)]


def yoy_from_levels(levels: pd.Series) -> pd.Series:
    """Percent change against twelve months earlier, over the shared window.

    The rent side's whole path from a published index to a band, in one line, because
    ZORI arrives already smoothed by Zillow. The price side does not use this: Redfin's
    extract needs a price floor, a complete monthly calendar and a rolling median first,
    and `redfin_data.get_appreciation_series` owns those steps.
    """
    windowed = window_levels(levels)
    return (windowed.pct_change(periods=PERIODS_PER_YEAR) * 100.0).dropna()


def is_in_anomalous_period(index: pd.DatetimeIndex) -> pd.Series:
    """Which observations fall inside the 2020-2022 window §2 requires be flagged."""
    return pd.Series(
        (index >= ANOMALOUS_PERIOD_START) & (index <= ANOMALOUS_PERIOD_END),
        index=index,
    )


def sustained_means(yoy: pd.Series, window_periods: int) -> pd.Series:
    """Rolling mean of `yoy`, computed within contiguous monthly runs only.

    A plain `.rolling()` would happily average across a hole in the index. That is
    harmless on a complete series but wrong the moment 2020-2022 is excluded: the window
    would splice 2019 onto 2023 and report the result as a twelve-month stretch the
    market never had. Runs are segmented on month adjacency so a "sustained stretch"
    always means genuinely consecutive months.
    """
    if yoy.empty:
        return yoy
    index = pd.DatetimeIndex(yoy.index)
    month_ordinal = pd.Series(index.year * 12 + index.month, index=yoy.index)
    run_id = month_ordinal.diff().ne(1).cumsum()
    means = [
        run.rolling(window=window_periods, min_periods=window_periods).mean()
        for _, run in yoy.groupby(run_id)
    ]
    return pd.concat(means).dropna()


def bands_from_yoy(
    yoy: pd.Series,
    sustained_window_periods: int = config.SUSTAINED_STRETCH_PERIODS,
    exclude_anomalous_period: bool = False,
) -> Optional[SeriesBands]:
    """Derive optimistic / base / pessimistic bands from a year-over-year series.

    The three bands follow §2's definitions directly: base is long-run average growth,
    optimistic is the best sustained stretch actually observed, pessimistic the worst.
    "Sustained" means the mean over `sustained_window_periods` consecutive year-over-year
    observations, so no band rests on a single month's print.

    `exclude_anomalous_period` re-computes with 2020-2022 removed. It exists because the
    Scenario/Forecast agent's Tree-of-Thought branching benefits from being able to
    compare the two rather than asserting one; either choice is defensible, and the
    result records which was made so the report can say so.

    Returns `None` when nothing survives the filtering, rather than raising. The caller
    knows which series this was and can say so; this function does not.
    """
    yoy = yoy.dropna()
    in_anomalous = is_in_anomalous_period(pd.DatetimeIndex(yoy.index))
    anomalous_share = float(in_anomalous.mean()) if len(yoy) else 0.0

    if exclude_anomalous_period:
        yoy = yoy[~in_anomalous.reindex(yoy.index).fillna(False)]

    if yoy.empty:
        return None

    # Sustained stretches. If no contiguous run is long enough to fill one window, fall
    # back to the full-series extremes rather than returning nothing - a short series
    # still yields a usable band, and the narrower basis is visible via
    # `n_yoy_observations`.
    sustained = sustained_means(yoy, sustained_window_periods)
    n_sustained_stretches = int(len(sustained))
    if sustained.empty:
        sustained = yoy

    optimistic_end = sustained.idxmax()
    pessimistic_end = sustained.idxmin()

    # A stretch covers [end - (window - 1) months, end]; it touches the anomalous window
    # if those intervals overlap at all.
    optimistic_start = optimistic_end - pd.DateOffset(
        months=sustained_window_periods - 1
    )
    optimistic_in_anomalous = bool(
        optimistic_end >= ANOMALOUS_PERIOD_START
        and optimistic_start <= ANOMALOUS_PERIOD_END
    )

    return SeriesBands(
        base_yoy_pct=float(yoy.mean()),
        optimistic_yoy_pct=float(sustained.max()),
        pessimistic_yoy_pct=float(sustained.min()),
        median_yoy_pct=float(yoy.median()),
        stdev_yoy_pct=float(yoy.std()),
        n_yoy_observations=int(len(yoy)),
        sustained_window_periods=sustained_window_periods,
        optimistic_stretch_end=optimistic_end,
        pessimistic_stretch_end=pessimistic_end,
        first_observation=pd.Timestamp(yoy.index.min()),
        last_observation=pd.Timestamp(yoy.index.max()),
        n_sustained_stretches=n_sustained_stretches,
        includes_anomalous_period=(not exclude_anomalous_period) and anomalous_share > 0,
        anomalous_period_share=anomalous_share,
        anomalous_period_excluded=exclude_anomalous_period,
        optimistic_stretch_in_anomalous_period=optimistic_in_anomalous,
    )
