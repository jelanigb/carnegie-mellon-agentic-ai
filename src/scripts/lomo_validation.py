"""What does the rent model cost in a market it has never seen? (§6 cut list 1a, OQ-4)

    .venv/bin/python scripts/lomo_validation.py [--json]

**The one measurement §6's cut list called "worth regretting", taken Sept 2, 2026** — two
days inside the freeze, because it turned out to cost a script and no re-record. It was cut
Aug 30 alongside hyperparameter tuning and feature engineering; those two change the shipped
model and would force a re-record of every eval row, and this one does not change anything.
It fits models the pipeline never loads and prints a number.

**The question, and why k-fold cannot answer it.** `train()` scores the model under 5-fold
cross-validation, and every fold contains rows from all nine training metros. So the reported
error — $451 pooled, $855 in New York — is the error on a *new listing in a market the model
has already learned*. That is the right figure for this system, because every market it
indexes is in the training set. It says nothing about a market the model has never seen, and
"how well does it transfer?" is a question a reader will ask and the report has otherwise had
to answer with a shrug.

**Leave-one-metro-out answers exactly that.** Hold out one metro entirely, fit on the rest,
score the held-out rows. Repeat per metro. Every scored row is then from a market absent from
its model's training data.

**The two figures must not be substituted for each other, and this script prints them side by
side so they cannot be** — OQ-4 carries that warning because they were nearly conflated once.
LOMO is an *upper bound* on the error a Staten Island subject faces, not an estimate of it:
New York is in the training set, so the shipped model has seen New York and the LOMO figure
describes a model that has not. Reporting LOMO as "the model's error" would overstate what
this system actually does; reporting only the k-fold figure would leave the transfer question
unanswered. Both, labelled, is the honest form.

**Metro grouping, and the one judgment in it.** `config.TRAINING_METROS` maps a state to city
patterns, and those patterns mean two different things depending on the state. Ohio's
`["Cincinnati", "Cleveland"]` are two distinct metros; New York's six entries are boroughs of
one. So New York's boroughs roll up — the same rollup `config.INDEXED_MARKETS` performs and
documents at its own definition — and every other pattern is its own group. Rows are labelled
by the same `kaggle_data.city_matches` word-boundary rule the shipped per-metro breakdown
uses, so this script and `rent_model._mae_dollars_by_metro` cannot drift apart on which rows
belong to which market.

**The baseline travels with each fold**, refit on that fold's training rows: predict the mean
ratio for every held-out row. Without it a LOMO MAE cannot be read — a large number might mean
the features fail to transfer, or it might mean the market's rents are simply further from the
pooled mean, and only the comparison separates those. This is §8's rule that an evidence
artifact must state what its check could have returned.

**One confound, stated rather than controlled for, because the direction is known.** A LOMO
fold removes a whole market, and the markets are not the same size — Los Angeles is 42% of the
corpus and Newark is 1%. So Los Angeles's fold trains on 58% of the data and its gap against
the k-fold figure blends *market absence* with *a much smaller training set*. Both push the
error the same way, which is why the figure is still a valid **upper bound** and is labelled
as one; it is not a clean estimate of market absence alone. The `train %` column prints each
fold's training share so a reader can see which metros carry the confound. Controlling for it
properly needs a size-matched arm that has seen part of the held-out market, which is a
different and larger measurement.

**Nothing here touches the shipped artifact.** `config.RENT_MODEL_PATH` is never read and
never written; `save()` is never called. The fits are in-memory and discarded, exactly as
`scripts/model_form_probe.py` does it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from tools import kaggle_data
from tools.model import rent_model


def metro_groups() -> dict[str, tuple[str, list[str]]]:
    """The leave-one-out units, as `label -> (state, patterns)`.

    New York's six boroughs are one metro and are rolled up; every other pattern in
    `config.TRAINING_METROS` stands alone. See the module docstring for why the same
    config structure means two different things in two different states.
    """
    groups: dict[str, tuple[str, list[str]]] = {}
    for state, patterns in config.TRAINING_METROS.items():
        if state == "NY":
            groups["New York"] = (state, list(patterns))
            continue
        for pattern in patterns:
            groups[pattern] = (state, [pattern])
    return groups


def _mask_for(df, state: str, patterns: list[str]):
    """Rows belonging to one metro, matched the way the shipped breakdown matches them."""
    return (df["state"] == state) & df["cityname"].apply(
        lambda c, p=patterns: kaggle_data.city_matches(c, p)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="emit the results as JSON instead of a table")
    args = parser.parse_args()

    df, build_report = rent_model.build_training_frame()
    features = list(config.RENT_MODEL_FEATURES)
    X = df[features].to_numpy(dtype=float)
    y = df["rent_to_anchor"].to_numpy(dtype=float)
    anchor = df["anchor"].to_numpy(dtype=float)

    if not args.json:
        print(f"Leave-one-metro-out — {config.RENT_MODEL_ESTIMATOR}, "
              f"{len(df):,} rows, features {features}")
        print("Every scored row is from a market its model never saw. Read against the "
              "k-fold column,\nwhich is the error the system actually reports "
              "(every indexed market is in training).\n")

    # The shipped, in-sample-market figures, for the side-by-side. Recomputed here under
    # the same protocol `train()` uses rather than read off the persisted report, so the
    # two columns differ only in the fold structure and not in anything else.
    _, kfold_report = rent_model.train()
    kfold_by_metro = kfold_report.mae_dollars_by_metro

    rows = []
    for label, (state, patterns) in sorted(metro_groups().items()):
        mask = _mask_for(df, state, patterns).to_numpy()
        n = int(mask.sum())
        if n == 0:
            continue
        model = rent_model._estimator().fit(X[~mask], y[~mask])
        predicted = model.predict(X[mask])
        lomo_mae = float(np.mean(np.abs((predicted - y[mask]) * anchor[mask])))
        # Refit per fold, on the same rows the model saw — computing it over everything
        # would let the baseline see the market it is scored on.
        baseline = float(np.mean(y[~mask]))
        baseline_mae = float(np.mean(np.abs((baseline - y[mask]) * anchor[mask])))
        rows.append({
            "metro": label,
            "n": n,
            "lomo_mae_dollars": lomo_mae,
            "lomo_baseline_mae_dollars": baseline_mae,
            "beats_baseline": lomo_mae < baseline_mae,
            "kfold_mae_dollars": kfold_by_metro.get(label, {}).get("mae_dollars"),
            "train_share": (len(df) - n) / len(df),
        })

    # Pooled LOMO: every row scored once, by a model that never saw its market. Weighted
    # by row count rather than averaged over metros, so a thin market cannot swing it.
    total_rows = sum(r["n"] for r in rows)
    pooled_lomo = sum(r["lomo_mae_dollars"] * r["n"] for r in rows) / total_rows
    pooled_baseline = sum(r["lomo_baseline_mae_dollars"] * r["n"] for r in rows) / total_rows

    summary = {
        "estimator": config.RENT_MODEL_ESTIMATOR,
        "rows": int(len(df)),
        "rows_scored": total_rows,
        "pooled_lomo_mae_dollars": pooled_lomo,
        "pooled_lomo_baseline_mae_dollars": pooled_baseline,
        "kfold_mae_dollars": kfold_report.mae_dollars,
        "kfold_baseline_mae_dollars": kfold_report.baseline_mae_dollars,
        "transfer_cost_dollars": pooled_lomo - kfold_report.mae_dollars,
        "metros": rows,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return

    print(f"{'metro':<16}{'n':>7}{'train %':>9}{'LOMO $':>10}{'baseline $':>13}"
          f"{'beats?':>9}{'k-fold $':>11}")
    print("-" * 75)
    for r in rows:
        kfold = f"{r['kfold_mae_dollars']:,.0f}" if r["kfold_mae_dollars"] else "—"
        print(f"{r['metro']:<16}{r['n']:>7,}{r['train_share']:>8.0%} "
              f"{r['lomo_mae_dollars']:>9,.0f}"
              f"{r['lomo_baseline_mae_dollars']:>13,.0f}"
              f"{'yes' if r['beats_baseline'] else 'NO':>9}{kfold:>11}")
    print("-" * 75)
    print(f"{'pooled':<16}{total_rows:>7,}{'':>9}{pooled_lomo:>10,.0f}"
          f"{pooled_baseline:>13,.0f}{'':>9}{kfold_report.mae_dollars:>11,.0f}")
    print()
    print(f"Transfer cost: ${summary['transfer_cost_dollars']:,.0f}/mo "
          f"({summary['transfer_cost_dollars'] / kfold_report.mae_dollars:+.0%} against "
          f"the k-fold figure).")
    print("The k-fold column is what the report publishes and is the right figure for "
          "this system;\nthe LOMO column is an upper bound on a market the model has "
          "never seen (OQ-4).")
    print("`train %` is the confound: a fold that drops a large market also trains on far "
          "less data,\nand both effects push the error the same way. See the module "
          "docstring.")
    print(f"\nTraining frame: {build_report.rows_trained or len(df):,} rows, "
          f"{build_report.counties} counties.")


if __name__ == "__main__":
    main()
