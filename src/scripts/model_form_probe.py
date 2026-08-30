"""Does the rent model's *form* change what the system says? (U11.1, OQ-4, §6 cut list 1a)

    .venv/bin/python scripts/model_form_probe.py [--folds N] [--no-fixtures]

`config.py`'s `TODO(cut-list)` records that the shipped estimator is a vanilla
`LinearRegression` on three raw columns, that it underfits rather than overfits
(train-vs-holdout gap $0.04), and that a random forest on identical data and features
reached $434 MAE against $524 — **about 17% of the rent error is in model form alone.**
It also records the two reasons that was deferred: added capacity carries a real
overfitting risk this model cannot currently have (a polynomial-3 probe scored R² -13.3),
and the measurement rested on a single split. This script removes the second objection by
scoring every candidate under **k-fold cross-validation**, which is the condition OQ-4
itself attached to closing.

**Three reports, and the third is the one that matters.**

1. **Accuracy** — cross-validated MAE per candidate, in ratio and in dollars, with the
   fold spread, plus each candidate's in-fold *training* error beside its held-out error.
   The second number is not decoration: it is the overfitting guard the deferral was
   justified by, and a candidate that wins on held-out error while opening a large
   train/holdout gap is a different proposition from one that wins without.
2. **Per-metro error, and specifically the New York ratio** — grouped by
   `config.INDEXED_MARKETS`, the same grouping
   `tools.model.rent_model._mae_dollars_by_metro` produces the shipped figures with, so
   the probe and the flag cannot drift apart. New York's ratio to the overall figure is
   what `FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED` fires on, so this asks whether
   model form changes what the system *discloses*, not only what it scores.
3. **Per-fixture behavior** — each eval fixture run through the **real Valuation agent**
   with each candidate swapped in, reporting the estimate, the predicted ratio against
   the `RENT_MODEL_MIN/MAX_RATIO` refusal band, the comp divergence against
   `RENT_COMP_DIVERGENCE_THRESHOLD_PCT`, and any change in the flag set.

**The third report runs the agent rather than reimplementing it, deliberately.** Every
boundary this probe cares about is decided inside `agents/valuation_rent.py` — the
refusal band, the divergence check, the metro-error threshold, the drift correction — and
a script that recomputed them would be measuring its own copy of the rules. Swapping the
persisted bundle and calling the node function means a flag-set delta reported here is a
flag-set delta the pipeline would actually produce.

**The comparison baseline is LinearRegression under this same protocol, not the artifact
on disk.** The shipped model's $524.03 was scored on one 20% split; comparing a
cross-validated candidate against it would blend a change in form with a change in
validation protocol and attribute both to the form. The shipped figures are printed for
reference and are not the baseline any delta is measured against.

**Candidates run at library defaults.** Hyperparameter tuning is U11.4's, on whatever
form survives this. Tuning inside the probe would turn a comparison of model forms into a
comparison of how much tuning effort each one received.

**Triage rule, fixed here before the first run** (per §8, and per Q1-of-U8's precedent
that a rule written after seeing the result is not a rule):

- **If New York's ratio stays ≥ `RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD` under every
  candidate *and* no fixture's flag set changes** — model form moves only the headline
  number. Adoption is then a live decision on accuracy grounds alone.
- **If either condition breaks** — form changes system *behavior*, and the adoption
  decision carries that evidence rather than an accuracy table alone.

Both are results. A probe that could only return "adopt" would not be worth running.

**What this script does and does not touch.** It makes **no model calls**: the corpus,
the county and ZCTA polygon joins, the Chroma comp index and the ZORI panel are all
local, and HUD FMR is cached on disk after the first pull. It writes nothing — no model
artifact is persisted, and `config.RENT_MODEL_PATH` is left exactly as it was found.

**Scope note on the fixture set.** The eval golden fixtures are used and the six demo
deals are not, because a demo deal is raw listing text whose structured terms exist only
downstream of an LLM extraction, and re-typing its bedrooms and floor area here would
duplicate figures `demo_deals._check_listing_states` exists to keep from drifting. The
fixtures cover all four markets in `INDEXED_MARKETS`, New York included, which is what
the triage rule reads.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold

import config
from agents.comps_retrieval import comps_retrieval_agent
from agents.valuation_rent import valuation_rent_agent
from eval.data import golden_fixtures
from state import DealState, DealTerms
from tools import county_crosswalk
from tools.model import rent_model

# Name -> a factory returning an *unfitted* estimator. A factory rather than an instance
# so each fold fits a fresh model; reusing one instance across folds would leak the
# previous fold's fit into the next one's timing and, for the ensembles, its warm state.
#
# `random_state` is threaded from the same seed the shipped training run uses, so a
# re-run of this probe reproduces exactly. The trees are otherwise at library defaults —
# see the module docstring on why tuning belongs in U11.4.
CANDIDATES: dict[str, Callable[[], object]] = {
    "LinearRegression": lambda: LinearRegression(),
    "RandomForest": lambda: RandomForestRegressor(
        random_state=config.RENT_MODEL_RANDOM_SEED
    ),
    "GradientBoosting": lambda: GradientBoostingRegressor(
        random_state=config.RENT_MODEL_RANDOM_SEED
    ),
}

# The shipped form. Every delta in the fixture report is measured against this candidate
# under this protocol, never against the artifact on disk — see the module docstring.
BASELINE = "LinearRegression"


@dataclass
class CvResult:
    """One candidate's cross-validated scores, plus the model a shipping run would fit.

    `oof_*` are computed over out-of-fold predictions pooled across every fold, so each
    row is scored exactly once by a model that never saw it. The per-fold lists are kept
    separately because a mean without its spread cannot say whether two candidates are
    distinguishable — the same reason U8.6's sweep reports a stable region rather than an
    optimum.
    """

    name: str
    fold_mae_dollars: list[float] = field(default_factory=list)
    fold_mae_ratio: list[float] = field(default_factory=list)
    fold_train_mae_dollars: list[float] = field(default_factory=list)
    oof_mae_dollars: float = 0.0
    oof_mae_ratio: float = 0.0
    oof_r2: float = 0.0
    by_metro: dict = field(default_factory=dict)
    full_fit: object = None

    @property
    def train_holdout_gap(self) -> float:
        """Held-out error minus in-fold training error, in dollars.

        The overfitting guard. `config.py` records the shipped model's as $0.04 — an
        underfit — and names added capacity's overfitting risk as one of the two reasons
        model form was deferred. A candidate that wins on held-out error while opening a
        wide gap here has bought accuracy with variance.
        """
        return float(np.mean(self.fold_mae_dollars) - np.mean(self.fold_train_mae_dollars))

    def metro_ratio(self, label: str) -> Optional[float]:
        """This market's error as a multiple of the candidate's own overall error.

        The quantity `FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED` fires on, so it is
        computed the way the flag computes it — against this candidate's headline figure,
        not against the shipped model's.
        """
        stats = self.by_metro.get(label)
        if not stats or not self.oof_mae_dollars:
            return None
        return stats["mae_dollars"] / self.oof_mae_dollars


def cross_validate(
    df: pd.DataFrame, name: str, factory: Callable[[], object], folds: int
) -> CvResult:
    """Score one candidate under k-fold CV, and fit the model a shipping run would ship.

    Under k-fold every row is held out exactly once, so the pooled out-of-fold vector is
    a prediction for the entire frame by models that never saw the row they scored. That
    is what makes a per-metro breakdown possible at all here: a single 20% split leaves
    New York with a holdout slice thin enough that the figure moves with the seed, which
    is the weakness OQ-4 named in the measurement it deferred.
    """
    features = list(config.RENT_MODEL_FEATURES)
    X = df[features].to_numpy(dtype=float)
    y = df["rent_to_anchor"].to_numpy(dtype=float)
    fmr = df["anchor"].to_numpy(dtype=float)

    result = CvResult(name=name)
    oof = np.full(len(df), np.nan)

    splitter = KFold(
        n_splits=folds, shuffle=True, random_state=config.RENT_MODEL_RANDOM_SEED
    )
    for train_idx, test_idx in splitter.split(X):
        model = factory().fit(X[train_idx], y[train_idx])
        predicted = model.predict(X[test_idx])
        oof[test_idx] = predicted
        result.fold_mae_ratio.append(
            float(mean_absolute_error(y[test_idx], predicted))
        )
        # Dollar error is the ratio error re-expressed at each row's own FMR — what a
        # reader of the report experiences — matching `rent_model.train`'s definition so
        # the two numbers are comparable.
        result.fold_mae_dollars.append(
            float(np.mean(np.abs((predicted - y[test_idx]) * fmr[test_idx])))
        )
        in_fold = model.predict(X[train_idx])
        result.fold_train_mae_dollars.append(
            float(np.mean(np.abs((in_fold - y[train_idx]) * fmr[train_idx])))
        )

    result.oof_mae_ratio = float(mean_absolute_error(y, oof))
    result.oof_mae_dollars = float(np.mean(np.abs((oof - y) * fmr)))
    result.oof_r2 = float(r2_score(y, oof))
    # Reused rather than reimplemented. The grouping is the whole point of this report —
    # it has to be the one the shipped figures and the flag were produced with — and that
    # function's docstring records a join bug (`filter_markets`' `ignore_index=True`) that
    # a second implementation would be free to repeat. Every row is a holdout row under
    # CV, so the full index is the holdout index.
    result.by_metro = rent_model._mae_dollars_by_metro(
        df, df.index.to_numpy(), oof, y, fmr
    )
    result.full_fit = factory().fit(X, y)
    return result


def bundle_for(
    cv: CvResult, frame_report: rent_model.TrainingReport, rows: int
) -> dict:
    """A model bundle in the shape `rent_model.load()` returns, never written to disk.

    Built by `dataclasses.replace` on the frame's own report rather than by hand, so the
    fields the Valuation agent reads cannot drift from `TrainingReport`'s definition. The
    frame-shaped counts (rows dropped, counties, anchoring basis) are properties of the
    training frame and are identical across candidates; only the scored fields differ.

    `mae_dollars_at_holdout_fmr` carries the **cross-validated** figure, which is what
    makes the metro ratio internally consistent: `_attach_metro_error` divides a market's
    error by this number, so a per-metro CV figure over a single-split headline would
    report a ratio between two different measurements.
    """
    report = replace(
        frame_report,
        # Under k-fold every row is trained on in all folds but one and held out in
        # exactly one, so both counts are the whole frame rather than a split of it —
        # which is the property that makes the per-metro slices thick enough to read.
        rows_trained=rows,
        holdout_rows=rows,
        mae_ratio=cv.oof_mae_ratio,
        mae_dollars_at_holdout_fmr=cv.oof_mae_dollars,
        r2=cv.oof_r2,
        mae_dollars_by_metro=cv.by_metro,
    )
    return {
        "model": cv.full_fit,
        "features": list(config.RENT_MODEL_FEATURES),
        "report": asdict(report),
        "trained_at": None,
    }


@contextlib.contextmanager
def swapped_model(bundle: dict):
    """Make `rent_model.load()` return this candidate for the duration of the block.

    Patched at the module attribute rather than by writing `config.RENT_MODEL_PATH`,
    because a probe must not leave a candidate model on disk where the next pipeline run
    would pick it up as the shipped one. `agents/valuation_rent.py` imports the module
    and calls `rent_model.load()` through it, so this reaches the agent.
    """
    original = rent_model.load
    rent_model.load = lambda: bundle
    try:
        yield
    finally:
        rent_model.load = original


@dataclass
class FixtureRow:
    """What one candidate did to one fixture, at the boundaries the flags sit on."""

    candidate: str
    estimate: Optional[float]
    ratio: Optional[float]
    divergence_pct: Optional[float]
    flag_kinds: frozenset


def _subject(terms: DealTerms) -> DealTerms:
    """The fixture's terms with `county_fips` resolved from its own coordinates.

    Resolved here rather than carried in the fixture, for the reason
    `scripts/valuation_evidence.py` records: it exercises the real crosswalk instead of
    trusting a FIPS code typed into a fixture file.
    """
    return terms.model_copy(
        update={
            "county_fips": county_crosswalk.lookup_county_fips(
                terms.latitude, terms.longitude
            )
        }
    )


def run_fixture(fixture, bundles: dict[str, dict]) -> list[FixtureRow]:
    """Run one fixture through the real Valuation agent once per candidate.

    Comp retrieval happens **once** and its result is shared across candidates: the comp
    set is a function of the subject's geography and attributes, not of the rent model,
    so re-running it per candidate would cost three index queries to produce three
    identical answers — and would make any difference between candidates impossible to
    attribute cleanly.
    """
    state = DealState(
        raw_listing_text=f"[golden fixture] {fixture.key}",
        deal_terms=_subject(fixture.terms),
    )
    state = state.model_copy(update=comps_retrieval_agent(state))

    rows: list[FixtureRow] = []
    for name, bundle in bundles.items():
        with swapped_model(bundle):
            update = valuation_rent_agent(state)
        detail = update["valuation_detail"]
        rows.append(
            FixtureRow(
                candidate=name,
                estimate=update.get("rent_estimate"),
                ratio=update.get("rent_estimate_ratio_to_fmr"),
                divergence_pct=detail.divergence_pct,
                flag_kinds=frozenset(f.kind for f in update["flags"]),
            )
        )
    return rows


def _fmt(value: Optional[float], spec: str) -> str:
    return format(value, spec) if value is not None else "—"


def report_accuracy(results: dict[str, CvResult], folds: int) -> None:
    print(f"\n=== 1. Cross-validated accuracy ({folds}-fold) ===")
    print(
        f"  {'candidate':<18} {'MAE $':>9} {'fold sd':>8} {'MAE ratio':>10} "
        f"{'R2':>7} {'train $':>9} {'gap $':>8}"
    )
    print("  " + "-" * 74)
    for name, cv in results.items():
        print(
            f"  {name:<18} {cv.oof_mae_dollars:>9.2f} "
            f"{np.std(cv.fold_mae_dollars):>8.2f} {cv.oof_mae_ratio:>10.4f} "
            f"{cv.oof_r2:>7.4f} {np.mean(cv.fold_train_mae_dollars):>9.2f} "
            f"{cv.train_holdout_gap:>8.2f}"
        )
    print(
        "\n  'gap $' is held-out minus in-fold training error — the overfitting guard\n"
        "  §6 cut-list 1a's deferral was justified by. config.py records the shipped\n"
        "  model's single-split gap as $0.04."
    )


def report_by_metro(results: dict[str, CvResult]) -> None:
    labels = [patterns[0] for patterns in config.INDEXED_MARKETS.values()]
    print("\n=== 2. Per-metro error, and the New York ratio ===")
    header = "  " + f"{'candidate':<18}" + "".join(f"{label:>18}" for label in labels)
    print(header)
    print("  " + "-" * (18 + 18 * len(labels)))
    for name, cv in results.items():
        cells = []
        for label in labels:
            stats = cv.by_metro.get(label)
            if not stats:
                cells.append(f"{'—':>18}")
                continue
            ratio = cv.metro_ratio(label)
            cells.append(f"{stats['mae_dollars']:>10,.0f} ({ratio:.2f}x)")
        print(f"  {name:<18}" + "".join(cells))
    counts = ", ".join(
        f"{label} n={results[BASELINE].by_metro[label]['n']:,}"
        for label in labels
        if label in results[BASELINE].by_metro
    )
    print(f"\n  Holdout rows per metro (identical across candidates): {counts}")
    print(
        f"  A ratio at or above {config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD} raises\n"
        f"  RENT_ESTIMATE_MARKET_ERROR_ELEVATED on every subject in that market."
    )


def report_fixtures(rows_by_fixture: dict[str, list[FixtureRow]]) -> bool:
    """Print the per-fixture table. Returns True if any candidate changed a flag set."""
    print("\n=== 3. Per-fixture behavior, through the real Valuation agent ===")
    any_delta = False
    for key, rows in rows_by_fixture.items():
        base = next(r for r in rows if r.candidate == BASELINE)
        print(f"\n  {key}")
        for row in rows:
            marks = []
            if row.ratio is not None and not (
                config.RENT_MODEL_MIN_RATIO <= row.ratio <= config.RENT_MODEL_MAX_RATIO
            ):
                marks.append("RATIO OUTSIDE BAND")
            if (
                row.divergence_pct is not None
                and abs(row.divergence_pct) > config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT
            ):
                marks.append("DIVERGES")
            gained = sorted(k.value for k in row.flag_kinds - base.flag_kinds)
            lost = sorted(k.value for k in base.flag_kinds - row.flag_kinds)
            if gained or lost:
                any_delta = True
                marks.append(
                    "FLAGS " + " ".join([f"+{k}" for k in gained] + [f"-{k}" for k in lost])
                )
            delta = (
                f"{row.estimate - base.estimate:+8,.0f}"
                if row.estimate is not None and base.estimate is not None
                else f"{'—':>8}"
            )
            print(
                f"    {row.candidate:<18} est {_fmt(row.estimate, '>8,.0f')} "
                f"({delta})  ratio {_fmt(row.ratio, '>5.2f')}  "
                f"div {_fmt(row.divergence_pct, '>+7.1%')}   "
                + ("  ".join(marks) if marks else "")
            )
    print(
        f"\n  Bands: refusal outside {config.RENT_MODEL_MIN_RATIO}-"
        f"{config.RENT_MODEL_MAX_RATIO}; divergence beyond "
        f"±{config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:.0%}. '(delta)' is against "
        f"{BASELINE}\n  under this same protocol, not against the artifact on disk."
    )
    return any_delta


def report_triage(
    results: dict[str, CvResult], flag_delta_seen: Optional[bool]
) -> None:
    """Apply the rule fixed in this file's docstring before the first run."""
    ny_label = config.INDEXED_MARKETS["NY"][0]
    threshold = config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD
    ratios = {name: cv.metro_ratio(ny_label) for name, cv in results.items()}
    ny_stays_elevated = all(r is not None and r >= threshold for r in ratios.values())

    print("\n=== Triage, per the rule fixed before the run ===")
    detail = ", ".join(f"{n} {_fmt(r, '.2f')}x" for n, r in ratios.items())
    print(f"  {ny_label} ratio under every candidate: {detail}")
    print(
        f"  Condition A — {ny_label} stays >= {threshold}x everywhere: "
        f"{'YES' if ny_stays_elevated else 'NO'}"
    )
    if flag_delta_seen is None:
        print("  Condition B — no fixture flag set changes: NOT MEASURED (--no-fixtures)")
        return
    print(
        f"  Condition B — no fixture flag set changes: "
        f"{'YES' if not flag_delta_seen else 'NO'}"
    )
    if ny_stays_elevated and not flag_delta_seen:
        print(
            "\n  VERDICT: model form moves only the headline number. What the system\n"
            "  discloses is unchanged, so adoption is a live decision on accuracy\n"
            "  grounds alone — the architect's call on the table above."
        )
    else:
        print(
            "\n  VERDICT: model form changes system *behavior*, not only its score.\n"
            "  The adoption decision carries this evidence: a candidate that moves a\n"
            "  flag set moves what a reader is told, not just how accurate it is."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folds", type=int, default=5, help="k for the cross-validation (default 5)"
    )
    parser.add_argument(
        "--no-fixtures",
        action="store_true",
        help="skip report 3, which needs the comp index and the HUD FMR cache",
    )
    args = parser.parse_args()

    # Built once and shared. Assembling it resolves county polygons for every corpus row
    # and pulls a FMR schedule per (county, fiscal year); it is identical across
    # candidates by construction, since only the estimator changes.
    df, frame_report = rent_model.build_training_frame()
    print(f"Frame {len(df):,} rows, {frame_report.counties} counties, "
          f"FY {frame_report.fiscal_years}")
    print(f"  features {list(config.RENT_MODEL_FEATURES)}, target rent/FMR ratio")

    shipped = rent_model.load()
    if shipped is not None:
        report = shipped.get("report") or {}
        by_metro = report.get("mae_dollars_by_metro") or {}
        ny = by_metro.get(config.INDEXED_MARKETS["NY"][0], {})
        print(
            f"  shipped artifact, for reference (single 20% split): "
            f"${report.get('mae_dollars_at_holdout_fmr', 0):,.2f} overall"
            + (f", ${ny['mae_dollars']:,.2f} New York" if ny else "")
        )

    results = {
        name: cross_validate(df, name, factory, args.folds)
        for name, factory in CANDIDATES.items()
    }

    report_accuracy(results, args.folds)
    report_by_metro(results)

    flag_delta_seen: Optional[bool] = None
    if not args.no_fixtures:
        bundles = {
            name: bundle_for(cv, frame_report, len(df))
            for name, cv in results.items()
        }
        rows_by_fixture = {
            key: run_fixture(fixture, bundles)
            for key, fixture in golden_fixtures.FIXTURES.items()
        }
        flag_delta_seen = report_fixtures(rows_by_fixture)

    report_triage(results, flag_delta_seen)


if __name__ == "__main__":
    main()
