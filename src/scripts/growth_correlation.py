"""Re-measure the rent/price growth correlation the forecast's pairing logic rests on.

**Why this script exists at all.** Decision #16 states the relationship between rent
growth and price growth as *"pooled r = −0.309 across 24 metro-years, negative in all
three metros independently"*, and `agents/scenario_forecast.py` hands that finding to the
Tree-of-Thought evaluator as evidence. It is the reason the search prefers *anti-correlated*
band pairings over the diagonal. But the measurement behind it was taken once, before U6
was built, and **was never committed as a script** — the decision log says only "tested
against this project's own data." A number that decides how every forecast is assembled and
cannot be re-derived is an assertion, which is the same standard `eval/README.md` applies to
the evaluation's own figures.

Written Aug 31, 2026 at U9.6, when the architect asked whether the correlation was still
accurate given how many of this project's data sources have moved since U6. It was not.

**What it measures, and the one choice that decides the answer.** For each indexed market:
annual rent growth against annual price growth, pooled and per metro. Price is always
Redfin's multi-family 2-4 unit median sale price. **Rent is computed twice** — once from
HUD FMR (the series #16 chose and `tools/fmr_history.py` still serves to the forecast) and
once from Zillow ZORI (market-observed rent, the series #19 adopted for the anchor). That
second pass is the whole point: FMR is an administrative schedule and ZORI is a market
observation, and the sign of the correlation is not the same for both.

    .venv/bin/python scripts/growth_correlation.py

Nothing is written to disk and no model is called. Reads the committed cohort panel, the
Redfin extract and the ZORI panel.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

import config
from tools.fmr_history import get_rent_growth_series, load_cohort_panel
from tools.redfin_data import get_appreciation_series, load_redfin
from tools.zori import county_median_tables

# HUD area name and county FIPS per market. The FIPS is the entityid's first five
# characters — HUD's metro entityids are county-prefixed — so these two are not
# independent facts and cannot drift apart.
MARKETS: dict[str, tuple[str, str]] = {
    "Chicago": ("Chicago-Joliet-Naperville, IL HUD Metro FMR Area", "17031"),
    "Los Angeles": ("Los Angeles-Long Beach-Glendale, CA HUD Metro FMR Area", "06037"),
    "Cleveland": ("Cleveland, OH HUD Metro FMR Area", "39035"),
    "New York": ("New York, NY HUD Metro FMR Area", "36005"),
}

# The fiscal years HUD moved the schedule nationally. `tools/fmr_history.py`'s cohort
# screen exists to detect exactly these, on the reasoning that a panel-wide step is an
# administrative decision rather than a market move. Excluding them is therefore a test
# the project's own design already argues for.
COHORT_SHIFT_YEARS = (2023, 2024)


def _price_growth(metro: str, redfin: pd.DataFrame) -> dict[int, float]:
    """Calendar-year mean of monthly year-over-year price change."""
    yoy = get_appreciation_series(redfin, metro).frame["yoy_pct"].dropna()
    return yoy.groupby(yoy.index.year).mean().to_dict()


def _fmr_growth(area: str, panel) -> dict[int, float]:
    return get_rent_growth_series(panel.entityids[area], 2).yoy_by_year


def _zori_growth(fips: str, medians: pd.DataFrame) -> dict[int, float]:
    """Calendar-year mean of monthly year-over-year market-rent change."""
    if fips not in medians.index:
        return {}
    series = medians.loc[fips].dropna()
    series.index = pd.to_datetime(series.index)
    yoy = ((series / series.shift(12) - 1) * 100).dropna()
    return yoy.groupby(yoy.index.year).mean().to_dict()


def _frame(rent_by_market: dict[str, dict[int, float]],
           price_by_market: dict[str, dict[int, float]]) -> pd.DataFrame:
    rows = [
        (metro, year, rent[year], price_by_market[metro][year])
        for metro, rent in rent_by_market.items()
        for year in sorted(set(rent) & set(price_by_market[metro]))
    ]
    return pd.DataFrame(rows, columns=["metro", "year", "rent", "price"])


def _report(frame: pd.DataFrame, label: str) -> float:
    """Pearson r, printed with r² because the strength is what gets over-read."""
    if len(frame) < 3:
        print(f"{label:<44} n={len(frame):>3}  (too few observations)")
        return float("nan")
    r = float(np.corrcoef(frame.rent, frame.price)[0, 1])
    print(f"{label:<44} n={len(frame):>3}  r={r:+.3f}  r²={r * r:.3f}")
    return r


def _pass(frame: pd.DataFrame, title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")
    _report(frame, "POOLED")
    for metro in MARKETS:
        _report(frame[frame.metro == metro], f"  {metro}")


def main() -> None:
    panel = load_cohort_panel()
    if panel is None:
        raise SystemExit(
            f"No cohort panel at {config.FMR_COHORT_PANEL_PATH}. "
            f"The FMR half of this measurement cannot run without it."
        )
    redfin = load_redfin()
    zori = county_median_tables()

    price = {m: _price_growth(m, redfin) for m in MARKETS}
    fmr = _frame({m: _fmr_growth(area, panel) for m, (area, _) in MARKETS.items()}, price)

    print("\nAnnual growth, percent per year — HUD FMR two-bedroom vs Redfin 2-4 unit\n")
    print(fmr.pivot(index="year", columns="metro", values="rent").round(1).to_string())

    _pass(fmr, "1. HUD FMR rent growth vs price growth — the series #16 measured")
    print(
        "\n#16 recorded pooled r = -0.309 across 24 metro-years and 'negative in all\n"
        "three metros independently'. That scope was the inference trio; New York\n"
        "entered the market set at U8.4c and is reported above alongside it."
    )

    _pass(
        fmr[~fmr.year.isin(COHORT_SHIFT_YEARS)],
        f"2. Same, excluding FY{COHORT_SHIFT_YEARS[0]}-{COHORT_SHIFT_YEARS[1]} — "
        f"the panel-wide FMR steps",
    )
    print(
        "\nThese are the years this project's own cohort screen flags as administrative\n"
        "rather than market. If the relationship is a property of the market it should\n"
        "survive their removal."
    )

    if zori is None:
        print("\nZORI panel unavailable; the market-rent pass is skipped.")
        return
    medians, _ = zori
    zori_frame = _frame(
        {m: _zori_growth(fips, medians) for m, (_, fips) in MARKETS.items()}, price
    )
    print("\nAnnual growth, percent per year — Zillow ZORI vs Redfin 2-4 unit\n")
    print(zori_frame.pivot(index="year", columns="metro", values="rent").round(1).to_string())
    _pass(zori_frame, "3. MARKET rent growth (ZORI) vs price growth — the control")
    print(
        "\nThe same price series, the same years, the same metros. Only the rent series\n"
        "differs. Whatever separates this pass from pass 1 is a property of the rent\n"
        "measurement, not of the housing market."
    )


if __name__ == "__main__":
    main()
