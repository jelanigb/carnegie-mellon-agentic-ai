"""Train and persist the anchor-normalized rent model (U5; form and anchor per #18/#19).

A script rather than a test, per §8's split: this makes real HUD FMR calls and reads the
full Kaggle corpus, so a failure here *is* the finding and must not be hidden behind a
mock. `tests/` stays hermetic.

    .venv/bin/python scripts/train_rent_model.py            # train, score, persist
    .venv/bin/python scripts/train_rent_model.py --dry-run  # assemble and report only

`--dry-run` exists because the training-set size is itself a documented quantity — §7
decision #4 (training metro shortlist) requires the row count to be re-derived rather than inherited from §2, whose
21,768 figure turned out to describe a state-level rollup rather than a metro-filtered
set. This is the re-derivation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools.model import rent_model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble the training frame and report it; do not fit or persist.",
    )
    args = parser.parse_args()

    metros = sum(len(v) for v in config.TRAINING_METROS.values())
    print(f"Training metros: {len(config.TRAINING_METROS)} states, "
          f"{metros} city patterns (§7 decision #4 (training metro shortlist))")
    print(f"Features: {', '.join(config.RENT_MODEL_FEATURES)}")
    print()

    if args.dry_run:
        df, report = rent_model.build_training_frame()
        print(report.summary().split("\n\nscored by")[0])
        print()
        print("rent/anchor ratio distribution:")
        print(df["rent_to_anchor"].describe().to_string())
        return

    model, report = rent_model.train()
    print(report.summary())
    print()
    # Whichever the fitted form exposes — a linear model has coefficients, an ensemble has
    # importances, and the label has to say which, because "per unit change in the ratio"
    # is a true statement about one and a false one about the other.
    if report.coefficients:
        print("coefficients (per unit change in the rent-to-anchor ratio):")
        for name, value in report.coefficients.items():
            print(f"  {name:<16} {value:>12.6f}")
    elif report.feature_importances:
        print(f"feature importances ({config.RENT_MODEL_ESTIMATOR}, share of split gain):")
        for name, value in sorted(
            report.feature_importances.items(), key=lambda kv: -kv[1]
        ):
            print(f"  {name:<16} {value:>12.4f}")

    rent_model.save(model, report)
    print()
    print(f"saved -> {config.RENT_MODEL_PATH}")


if __name__ == "__main__":
    main()
