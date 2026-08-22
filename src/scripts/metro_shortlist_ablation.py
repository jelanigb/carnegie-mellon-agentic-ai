"""Does training on more metros help, and where? (§7 decision #4)

Decision #4 selected an eight-metro training shortlist on the argument that a *ratio*
target — rent ÷ local FMR — benefits more from structural market diversity than from raw
volume. This script tests that argument three ways, because "does breadth help" turns out
to have different answers depending on what is being predicted.

    .venv/bin/python scripts/metro_shortlist_ablation.py [--seeds N]

**A correctness note that is the reason this file exists rather than a scratch script.**
The first version of this analysis reported that trio-only training beat the eight-metro
set everywhere. That was an artifact of a bug, not a finding. `kaggle_data.filter_markets`
concatenates with `ignore_index=True`, so the frame it returns is re-indexed 0..n-1 and
its labels cannot be joined back to the frame it was derived from. Taking `.index` from it
and passing that to `df.loc[...]` silently selects *positionally* — the "trio" set so
built contained 2,354 Los Angeles rows, 1,233 Ohio rows spanning both Cleveland and
Cincinnati, and no Chicago at all. Every conclusion drawn from it was inverted.

`_market_index` below therefore computes membership as a boolean mask against the frame's
own index and never round-trips through `filter_markets`. Per §8, an evidence artifact
should say what it could have returned had things been fine: this one could have agreed
with the original result, and instead reverses it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split

import config
from tools import kaggle_data
from tools.model import rent_model

TRIO = {"CA": ["Los Angeles"], "IL": ["Chicago"], "OH": ["Cleveland"]}
FIVE = {
    "CA": ["Los Angeles"],
    "IL": ["Chicago"],
    "OH": ["Cincinnati", "Cleveland"],
    "NJ": ["Newark", "Jersey City"],
}
NEW_YORK = {"NY": ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"]}


def _market_index(df: pd.DataFrame, markets: dict) -> list:
    """Row labels in `df` matching `markets`, computed on df's own index.

    Deliberately does not call `kaggle_data.filter_markets` — see the module docstring
    for what that costs here.
    """
    mask = pd.Series(False, index=df.index)
    for state, patterns in markets.items():
        in_state = df["state"] == state
        hits = df["cityname"].apply(lambda c, p=patterns: kaggle_data.city_matches(c, p))
        mask |= in_state & hits
    return sorted(df.index[mask])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    args = parser.parse_args()

    df, report = rent_model.build_training_frame()
    features = list(config.RENT_MODEL_FEATURES)

    def fit(idx):
        return LinearRegression().fit(
            df.loc[idx, features].to_numpy(dtype=float),
            df.loc[idx, "rent_to_fmr"].to_numpy(dtype=float),
        )

    def mae(model, idx) -> float:
        X = df.loc[idx, features].to_numpy(dtype=float)
        y = df.loc[idx, "rent_to_fmr"].to_numpy(dtype=float)
        fmr = df.loc[idx, "fmr"].to_numpy(dtype=float)
        return float(np.mean(np.abs((model.predict(X) - y) * fmr)))

    trio = _market_index(df, TRIO)
    five = _market_index(df, FIVE)
    eight = _market_index(df, config.TRAINING_METROS)

    print(f"Frame {len(df):,} rows, {report.counties} counties, FY {report.fiscal_years}")
    print(f"  trio {len(trio):,}  five {len(five):,}  eight {len(eight):,}")
    print(f"  trio by state: {df.loc[trio, 'state'].value_counts().to_dict()}\n")

    # 1. The metros the system actually prices.
    print(f"=== 1. Held-out inference-trio properties ({args.seeds} splits) ===")
    variants = {"trio only": trio, "five metros": five, "eight metros": eight}
    scores = {k: [] for k in variants}
    for seed in range(args.seeds):
        _, holdout = train_test_split(trio, test_size=0.20, random_state=seed)
        holdout = set(holdout)
        for name, pool in variants.items():
            scores[name].append(mae(fit(sorted(set(pool) - holdout)), sorted(holdout)))
    stacked = np.array([scores[k] for k in variants])
    winner = stacked.argmin(axis=0)
    for i, name in enumerate(variants):
        v = np.array(scores[name])
        print(f"  {name:<14} ${v.mean():>8.2f} ± {v.std():5.2f}   "
              f"wins {int((winner == i).sum()):>2}/{args.seeds}")

    # 2. A market that is indexed for comps but peripheral to training.
    print(f"\n=== 2. Held-out New York properties ({args.seeds} splits) ===")
    ny = _market_index(df, NEW_YORK)
    trio_ny, eight_ny = [], []
    for seed in range(args.seeds):
        _, test = train_test_split(ny, test_size=0.30, random_state=seed)
        test = set(test)
        trio_ny.append(mae(fit(sorted(set(trio) - test)), sorted(test)))
        eight_ny.append(mae(fit(sorted(set(eight) - test)), sorted(test)))
    t, e = np.array(trio_ny), np.array(eight_ny)
    print(f"  {len(ny)} NY rows   trio ${t.mean():.2f} ± {t.std():.2f}   "
          f"eight ${e.mean():.2f} ± {e.std():.2f}   "
          f"eight wins {int((e < t).sum())}/{args.seeds}")

    # 3. The generalization question: a market the model has never seen.
    print("\n=== 3. Leave-one-metro-out: transfer to an unseen market ===")
    print(f"  {'held out':<14} {'trio-trained':>13} {'eight-trained':>14} {'winner':>8}")
    print("  " + "-" * 52)
    for name, markets in (("Los Angeles", {"CA": ["Los Angeles"]}),
                          ("Chicago", {"IL": ["Chicago"]}),
                          ("Cleveland", {"OH": ["Cleveland"]})):
        target = set(_market_index(df, markets))
        a = mae(fit(sorted(set(trio) - target)), sorted(target))
        b = mae(fit(sorted(set(eight) - target)), sorted(target))
        print(f"  {name:<14} {a:>13.2f} {b:>14.2f} {('trio' if a < b else 'eight'):>8}")


if __name__ == "__main__":
    main()
