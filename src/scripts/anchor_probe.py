"""Which anchor should the rent model learn a ratio to? (U11.3, §6 cut-list item 6)

    .venv/bin/python scripts/anchor_probe.py [--folds N]

The model does not predict rent; it predicts *rent divided by a reference figure*, and
multiplies that ratio by the subject's current reference at prediction time (§2). The
reference has been HUD Fair Market Rent since U5. This script asks whether it should be,
by scoring candidate anchors against each other on the same corpus, the same features and
the same estimator.

**Why the question is open.** U8.0 measured the FMR schedule rising +51.9% against market
rent's +33.5% since the corpus vintage, so the anchor drifted ~18 points away from the
market it prices; U8.4b corrects for that per ZCTA at prediction time, and cut-list item 6
carries the structural fix the correction stands in for. Separately, an anchor exists to
absorb *location* — `config.RENT_MODEL_FEATURES` carries no market identifier by design,
so whatever the anchor fails to absorb is error the model structurally cannot recover —
and ZORI's per-city mean ratios spread 0.172 against FMR's 0.257.

**The five candidates.**

======  ==================================================================
`fmr`   Status quo. `rent / FMR(zip -> county)`, the anchor U5 shipped.
`zori`  `rent / ZORI(zip -> county)` at the row's own listing month.
`hyb`   `rent / [ZORI(zip -> county) x FMR bedroom ratio]`. ZORI supplies
        the level and the location; FMR supplies only the *shape* across
        bedroom counts, which ZORI does not publish at all.
`fmr+`  FMR, with ZORI where FMR is unavailable. A coverage lever.
`fmr/z` FMR where HUD publishes a ZIP-level schedule, ZORI where FMR would
        otherwise be county-grain. Targets the defect rather than the
        anchor: Chicago is 100% ZIP-anchored under FMR and Los Angeles,
        Cleveland and New York are 100% county-anchored, so this swaps a
        ZIP-grain market series into exactly the three markets that lose
        sub-county resolution today.
======  ==================================================================

**ZORI has no bedroom dimension, and that is the substantive asymmetry.** HUD publishes
FMR per bedroom count (0-4BR); Zillow's ZORI file is one smoothed series per ZIP across
all unit types. So `zori` asks the model's `bedrooms` feature to carry a signal the anchor
used to supply, and `hyb` exists to test whether handing that back matters. It is also why
the negative `bedrooms` coefficient the linear model used to produce is an FMR artifact —
see `config.RENT_MODEL_FEATURES`.

**Comparison, and what makes it fair.** The candidates learn different quantities — a
ratio to FMR is not a ratio to ZORI — so ratio-space error is not comparable across them.
Every figure below is therefore in **dollars**: each candidate's prediction is multiplied
back by that row's own anchor and compared against the row's actual rent, which is the
number a reader of the report is exposed to. Candidates are additionally scored on the
**intersection** of rows all of them can price, so a candidate cannot win by declining the
hard rows; per-candidate coverage is reported separately, above the scores.

**It states what it could have returned, per §8.** `fmr` winning would close item 6 as
measured-and-rejected and leave U8.4b's correction as the vintage instrument. `zori` or
`hyb` winning would price the rewrite against a measured gain rather than an assumed one.
`fmr/z` winning would say the anchor is not wrong in general, only where it is coarse —
the cheapest of the three outcomes and the one no one has proposed. A near-tie is also a
result: it would mean the anchor is not where the remaining error lives, and would
redirect U11 at features instead.

Runs the configured estimator (`config.RENT_MODEL_ESTIMATOR`) so the comparison is against
the form actually shipping. No model calls; no artifact is written.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

import config
from tools import hud_fmr, kaggle_data, zori
from tools.model import rent_model

REFERENCE_BEDROOMS = 2


@dataclass
class Anchor:
    """One candidate reference series, per corpus row."""

    key: str
    label: str
    values: np.ndarray
    notes: str = ""
    coverage: float = field(default=0.0)


def _listing_month(frame: pd.DataFrame) -> pd.Series:
    """Each row's own listing month, keyed as ZORI's month columns are (`%Y-%m-%d`)."""
    listed = pd.to_datetime(pd.to_numeric(frame["time"], errors="coerce"), unit="s")
    return listed.dt.to_period("M").dt.to_timestamp("M").dt.strftime("%Y-%m-%d")


def _zori_anchor(frame: pd.DataFrame, panel: pd.DataFrame) -> np.ndarray:
    """ZORI at each row's own ZIP and month, falling back to its county's median.

    The fallback is not a nicety: 1,515 of 5,686 rows sit before their own ZIP's series
    begins, and without a county tier the ZORI anchor would discard 27% of the corpus.
    `scripts/zori_county_tier.py` measures the recovery at 99.0%.
    """
    series = {z: zori.series_for_zip(panel, z) for z in frame["zcta"].dropna().unique()}
    county_median, _ = zori.county_medians(panel)

    values = np.full(len(frame), np.nan)
    # Which tier priced each row, recorded rather than discarded: `_diagnose_fallback`
    # reads it, and the two tiers are different denominators whatever the caller does.
    tier = np.array(["none"] * len(frame), dtype=object)
    for position, (_, row) in enumerate(frame.iterrows()):
        month = row["month"]
        one = series.get(row["zcta"])
        if one is not None and month in one.index and not pd.isna(one[month]):
            values[position] = float(one[month])
            tier[position] = "zip"
            continue
        geoid = row["geoid"]
        if geoid in county_median.index and month in county_median.columns:
            fallback = county_median.at[geoid, month]
            if not pd.isna(fallback):
                values[position] = float(fallback)
                tier[position] = "county"
    frame["zori_tier"] = tier
    return values


def _bedroom_shape(frame: pd.DataFrame, client: hud_fmr.HudFmrClient) -> np.ndarray:
    """FMR's bedroom multiplier for each row: its own bedroom FMR over the 2BR figure.

    The *shape* of the schedule across bedroom counts, with its level divided out — which
    is the one thing FMR supplies that ZORI cannot, since ZORI publishes a single series
    per ZIP across all unit types. Taken at the row's own county and fiscal year so the
    shape is the one in force where and when the row was listed.
    """
    pairs = set(zip(frame["county_fips"], frame["fiscal_year"]))
    table = rent_model._fmr_table(pairs, client)
    reference_field, _ = hud_fmr.bedroom_field(REFERENCE_BEDROOMS)

    values = np.full(len(frame), np.nan)
    for position, (_, row) in enumerate(frame.iterrows()):
        rents = table.get((row["county_fips"], row["fiscal_year"]))
        if not rents:
            continue
        own_field, _ = hud_fmr.bedroom_field(int(row["bedrooms"]))
        try:
            own, reference = float(rents[own_field]), float(rents[reference_field])
        except (KeyError, TypeError, ValueError):
            continue
        if reference > 0 and own > 0:
            values[position] = own / reference
    return values


def _score(
    frame: pd.DataFrame, anchor: Anchor, subset: np.ndarray, folds: int
) -> tuple[float, dict]:
    """Cross-validated dollar MAE for one anchor, plus its per-metro breakdown.

    Dollars rather than ratio units, because the candidates learn different quantities and
    only the re-expressed figure is comparable across them: the prediction is multiplied
    back by the row's own anchor and compared against its actual rent.
    """
    rows = frame.loc[subset]
    features = list(config.RENT_MODEL_FEATURES)
    X = rows[features].to_numpy(dtype=float)
    reference = anchor.values[subset]
    rent = rows["price"].to_numpy(dtype=float)
    y = rent / reference

    out_of_fold = np.full(len(rows), np.nan)
    splitter = KFold(
        n_splits=folds, shuffle=True, random_state=config.RENT_MODEL_RANDOM_SEED
    )
    for train_index, test_index in splitter.split(X):
        model = rent_model._estimator().fit(X[train_index], y[train_index])
        out_of_fold[test_index] = model.predict(X[test_index])

    dollars = np.abs(out_of_fold * reference - rent)

    by_metro: dict[str, float] = {}
    for state, patterns in config.INDEXED_MARKETS.items():
        mask = (rows["state"] == state) & rows["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        if int(mask.sum()):
            by_metro[patterns[0]] = float(dollars[mask.to_numpy()].mean())
    return float(dollars.mean()), by_metro


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=int, default=config.RENT_MODEL_CV_FOLDS)
    args = parser.parse_args()

    frame, report = rent_model.build_training_frame()
    frame["month"] = _listing_month(frame)
    frame["zcta"] = frame["zcta"].astype("string")
    frame["geoid"] = frame["county_fips"].astype(str).str[:5]
    print(f"Frame {len(frame):,} rows, {report.counties} counties, "
          f"FY {report.fiscal_years}")
    print(f"Estimator {config.RENT_MODEL_ESTIMATOR}, {args.folds}-fold CV, "
          f"features {list(config.RENT_MODEL_FEATURES)}\n")

    fmr = frame["fmr"].to_numpy(dtype=float)
    zori_values = _zori_anchor(frame, zori.load())
    shape = _bedroom_shape(frame, hud_fmr.HudFmrClient())
    is_zip_fmr = frame["fmr_resolution"].isin(["zip", "zip_backcast"]).to_numpy()

    # `fmr+` differs from `fmr` only on rows FMR cannot price — and `build_training_frame`
    # has already dropped those, so on this frame the two are the same array by
    # construction. Reported rather than silently omitted: "identical" is the finding.
    fmr_plus = np.where(np.isnan(fmr), zori_values, fmr)

    candidates = [
        Anchor("fmr", "FMR (status quo)", fmr),
        Anchor("zori", "ZORI, zip->county", zori_values,
               "no bedroom dimension"),
        Anchor("hyb", "ZORI x FMR bedroom shape", zori_values * shape,
               "ZORI level, FMR shape"),
        Anchor("fmr+", "FMR, ZORI where absent", fmr_plus,
               "coverage lever only"),
        Anchor("fmr/z", "FMR where ZIP, ZORI where county",
               np.where(is_zip_fmr, fmr, zori_values),
               "targets the coarse markets"),
    ]

    usable = []
    for candidate in candidates:
        ok = np.isfinite(candidate.values) & (candidate.values > 0)
        candidate.coverage = float(ok.mean())
        usable.append(ok)
    common = np.logical_and.reduce(usable)

    print("Coverage — rows each candidate can price at all:")
    for candidate in candidates:
        print(f"  {candidate.key:<6} {candidate.label:<34} {candidate.coverage:>7.1%}"
              + (f"   ({candidate.notes})" if candidate.notes else ""))
    identical = np.allclose(fmr_plus, fmr, equal_nan=True)
    if identical:
        print("  NOTE: fmr+ is identical to fmr on this frame — no row was dropped for a "
              "missing FMR,\n        so the ZORI fallback never fires. A coverage lever "
              "with nothing to cover.")
    print(f"\nScored on the {int(common.sum()):,} rows every candidate can price "
          f"({common.mean():.1%} of the frame).\n")

    labels = [patterns[0] for patterns in config.INDEXED_MARKETS.values()]
    header = f"  {'anchor':<7} {'MAE $':>9}" + "".join(f"{label:>13}" for label in labels)
    print(header)
    print("  " + "-" * (17 + 13 * len(labels)))
    for candidate in candidates:
        overall, by_metro = _score(frame, candidate, common, args.folds)
        cells = "".join(
            f"{by_metro.get(label, float('nan')):>13,.0f}" for label in labels
        )
        print(f"  {candidate.key:<7} {overall:>9,.2f}" + cells)

    print("\n  Dollars throughout: each prediction multiplied back by its own row's "
          "anchor and\n  compared against that row's actual rent, which is the only "
          "figure comparable\n  across anchors that are different quantities.")

    _diagnose_fallback(frame, zori_values, shape, common, args.folds)


def _diagnose_fallback(
    frame: pd.DataFrame,
    zori_values: np.ndarray,
    shape: np.ndarray,
    common: np.ndarray,
    folds: int,
) -> None:
    """Split the ZORI anchor's error by whether the row used its ZIP or its county.

    **Written because the headline table raised a question it could not answer.** Los
    Angeles is the one market ZORI makes *worse* (+9.5%), and it is also the market where
    the county fallback carries the most weight — 14% of its rows, against a county
    median spanning Malibu to Compton. If the fallback is the cause, then ZORI's cost is
    a fixable property of the tier rather than of the series, and that changes what
    U11.3 should build. If the two tiers score alike, the loss is real and Los Angeles
    simply prices better against the administrative schedule.

    A tier is a different denominator, so this is a split of one anchor's residuals
    rather than a comparison of two anchors — the same distinction
    `rent_model.anchor_for_row` draws between `zip` and `county` resolution today.
    """
    panel_series_used = frame["zori_tier"].to_numpy()
    print("\n=== ZORI anchor, split by which tier priced the row ===")
    hybrid = zori_values * shape
    for tier in ("zip", "county"):
        subset = common & (panel_series_used == tier)
        if int(subset.sum()) < folds:
            print(f"  {tier:<7} too few rows to score")
            continue
        overall, by_metro = _score(
            frame, Anchor("hyb", "", hybrid), subset, folds
        )
        cells = "  ".join(f"{k} {v:,.0f}" for k, v in by_metro.items())
        print(f"  {tier:<7} n={int(subset.sum()):>5,}  MAE ${overall:>8,.2f}   {cells}")
    print(
        "  A county-tier row is anchored to a median over its whole county; where that\n"
        "  county is large and heterogeneous the anchor carries little location signal,\n"
        "  which is the thing the anchor exists to supply."
    )


if __name__ == "__main__":
    main()
