"""FMR-normalized rent regression (U5, §2's rent-anchoring design).

**The problem this module exists to solve is vintage, not accuracy.** The Kaggle rental
corpus is a scrape spanning Dec 2018 - Dec 2019. A regression fit on its rent column
predicts 2019 dollars, and a 2019 dollar figure presented in a 2026 report is wrong
while looking entirely reasonable — no error bar, no missing value, nothing a reader
could catch. §8 states the invariant that follows: never let an unanchored Kaggle dollar
figure reach the Summarizer.

**The fix is to model a ratio instead of a level.** For every training row, rent is
divided by the HUD Fair Market Rent for that row's own county and its own fiscal year.
What the model learns is therefore how bedrooms, bathrooms, and square footage move rent
*relative to the local FMR* — a structural relationship that ages far more slowly than a
dollar level does. At prediction time the predicted ratio is multiplied by *today's* FMR
for the subject's county, producing a current-dollar figure anchored to a dated public
reference the report can cite.

Three consequences worth stating, because each is a limitation rather than a feature:

1. **The anchoring is disclosed, always.** Every estimate on this path raises
   `RENT_ANCHORED_TO_FMR` (info). The number is not a market observation; it is a
   modeled ratio times a government reference figure, and the report says so.
2. **No FMR, no estimate.** A subject whose county will not resolve — New England, or no
   coordinates at all — has no anchor, so this path produces nothing and raises
   `FMR_UNAVAILABLE_FOR_COUNTY` rather than falling back to a raw comp mean. A raw comp
   mean is precisely the unanchored 2019 figure the design forbids.
3. **The ratio assumption is load-bearing and untested against 2026 data.** It holds
   that rent-to-FMR structure is stable over ~7 years. Nothing in this repo verifies
   that, because verifying it needs current-vintage rent data this project does not
   have. It is an assumption, labelled as one, and the largest single source of error in
   the rent estimate.

Feature choice is deliberately narrow and excludes any market identifier — see
`config.RENT_MODEL_FEATURES` for why a metro dummy would defeat the ratio design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

import config
from tools import county_crosswalk, hud_fmr, kaggle_data


@dataclass
class TrainingReport:
    """What a training run produced, including everything it discarded.

    The dropped-row counts are not diagnostics — they are the reason to trust or
    distrust the MAE below them. A model fit on 40% of the intended corpus because FMR
    lookups quietly failed would report a perfectly respectable error against a training
    set that no longer represents the shortlist it claims to.
    """

    rows_in_shortlist: int
    rows_unresolved_county: int
    rows_missing_fmr: int
    rows_outside_ratio_bounds: int
    rows_trained: int
    holdout_rows: int
    counties: int
    fiscal_years: list[int] = field(default_factory=list)
    mae_ratio: float = 0.0
    mae_dollars_at_holdout_fmr: float = 0.0
    baseline_mae_ratio: float = 0.0
    baseline_mae_dollars: float = 0.0
    r2: float = 0.0
    coefficients: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"shortlist rows           {self.rows_in_shortlist:>7,}",
            f"  dropped, no county     {self.rows_unresolved_county:>7,}",
            f"  dropped, no FMR        {self.rows_missing_fmr:>7,}",
            f"  dropped, ratio bounds  {self.rows_outside_ratio_bounds:>7,}",
            f"trained on               {self.rows_trained:>7,}"
            f"   ({self.counties} counties, FY {self.fiscal_years})",
            f"holdout rows             {self.holdout_rows:>7,}",
            "",
            f"MAE (rent/FMR ratio)     {self.mae_ratio:>7.4f}",
            f"MAE (dollars)            {self.mae_dollars_at_holdout_fmr:>7.2f}",
            f"R^2                      {self.r2:>7.4f}",
            "",
            "Baseline — predict the training-set mean ratio for every row:",
            f"  MAE (ratio)            {self.baseline_mae_ratio:>7.4f}",
            f"  MAE (dollars)          {self.baseline_mae_dollars:>7.2f}",
        ]
        return "\n".join(lines)


def fmr_fiscal_year(timestamp: pd.Timestamp) -> int:
    """Federal fiscal year for a listing date. FY N runs Oct 1 (N-1) - Sep 30 N.

    Per-row rather than a single assumed vintage: the corpus straddles a fiscal-year
    boundary (930 rows in calendar 2018, 4,787 in 2019), so normalizing everything
    against one FMR year would misprice one side of it against the other's schedule.
    """
    if timestamp.month >= config.RENT_MODEL_FMR_FISCAL_YEAR_START_MONTH:
        return int(timestamp.year) + 1
    return int(timestamp.year)


def _fmr_table(
    pairs: set[tuple[str, int]], client: hud_fmr.HudFmrClient
) -> dict[tuple[str, int], dict]:
    """Fetch the FMR rent schedule for each (county entityid, fiscal year) pair.

    One call per *pair*, not per row. `get_fmr` returns every bedroom field at once, so
    thousands of rows resolve against a handful of responses — U5's shortlist needs 15
    counties across 2 fiscal years. `tools/hud_fmr.py` caches to disk on top of that, so
    a re-run costs no calls at all.

    A pair that fails is recorded as missing rather than raised: one county's absent
    schedule should cost its own rows, not the entire training run.
    """
    table: dict[tuple[str, int], dict] = {}
    for entityid, year in sorted(pairs):
        try:
            table[(entityid, year)] = client.get_fmr(entityid, year=year).rents
        except (hud_fmr.HudFmrApiError, KeyError, StopIteration):
            continue
    return table


def build_training_frame(
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> tuple[pd.DataFrame, TrainingReport]:
    """Assemble the FMR-normalized training set from the Kaggle corpus.

    Returns the frame and a report of everything dropped on the way, so a caller can
    see the shape of what survived rather than only its size.
    """
    client = client or hud_fmr.HudFmrClient()

    corpus = kaggle_data.load_clean()
    df = kaggle_data.filter_markets(corpus, config.TRAINING_METROS).copy()
    report = TrainingReport(
        rows_in_shortlist=len(df),
        rows_unresolved_county=0,
        rows_missing_fmr=0,
        rows_outside_ratio_bounds=0,
        rows_trained=0,
        holdout_rows=0,
        counties=0,
    )

    df["county_fips"] = county_crosswalk.county_fips_for_points(
        df["latitude"].tolist(), df["longitude"].tolist()
    )
    unresolved = df["county_fips"].isna()
    report.rows_unresolved_county = int(unresolved.sum())
    df = df[~unresolved]

    listed = pd.to_datetime(pd.to_numeric(df["time"], errors="coerce"), unit="s")
    df["fiscal_year"] = listed.apply(fmr_fiscal_year)

    pairs = set(zip(df["county_fips"], df["fiscal_year"]))
    table = _fmr_table(pairs, client)

    def _anchor(row) -> float:
        rents = table.get((row["county_fips"], row["fiscal_year"]))
        if rents is None:
            return float("nan")
        field_name, _ = hud_fmr.bedroom_field(int(row["bedrooms"]))
        try:
            return float(rents[field_name])
        except (KeyError, TypeError, ValueError):
            return float("nan")

    df["fmr"] = df.apply(_anchor, axis=1)
    missing = df["fmr"].isna() | (df["fmr"] <= 0)
    report.rows_missing_fmr = int(missing.sum())
    df = df[~missing]

    df["rent_to_fmr"] = df["price"] / df["fmr"]
    in_bounds = df["rent_to_fmr"].between(
        config.RENT_MODEL_MIN_RATIO, config.RENT_MODEL_MAX_RATIO
    )
    report.rows_outside_ratio_bounds = int((~in_bounds).sum())
    df = df[in_bounds]

    report.counties = int(df["county_fips"].nunique())
    report.fiscal_years = sorted(int(y) for y in df["fiscal_year"].unique())
    return df.reset_index(drop=True), report


def train(
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> tuple[object, TrainingReport]:
    """Fit the ratio regression and score it on a held-out slice.

    Reports against a mean-ratio baseline as well as in absolute terms. An MAE alone
    cannot say whether the features carry signal — per §8, a check whose result was
    structurally guaranteed proves nothing, and "predict the average ratio for every
    row" is the null hypothesis this model has to beat to justify existing at all.
    """
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    df, report = build_training_frame(client=client)
    if len(df) < config.RENT_MODEL_MIN_TRAINING_ROWS:
        raise ValueError(
            f"only {len(df)} usable training rows, below "
            f"RENT_MODEL_MIN_TRAINING_ROWS={config.RENT_MODEL_MIN_TRAINING_ROWS}. "
            "This indicates a broken filter or an unavailable corpus, not ordinary "
            "variation — refusing to fit rather than shipping a model nobody can trust."
        )

    features = list(config.RENT_MODEL_FEATURES)
    X = df[features].to_numpy(dtype=float)
    y = df["rent_to_fmr"].to_numpy(dtype=float)
    fmr = df["fmr"].to_numpy(dtype=float)

    X_train, X_test, y_train, y_test, _, fmr_test = train_test_split(
        X, y, fmr,
        test_size=config.RENT_MODEL_HOLDOUT_FRACTION,
        random_state=config.RENT_MODEL_RANDOM_SEED,
    )

    model = LinearRegression().fit(X_train, y_train)
    predicted = model.predict(X_test)

    report.rows_trained = int(len(X_train))
    report.holdout_rows = int(len(X_test))
    report.mae_ratio = float(mean_absolute_error(y_test, predicted))
    report.r2 = float(r2_score(y_test, predicted))
    # Dollar error is the ratio error re-expressed at each holdout row's own FMR, which
    # is what a reader of the report actually experiences.
    report.mae_dollars_at_holdout_fmr = float(
        np.mean(np.abs((predicted - y_test) * fmr_test))
    )

    baseline = np.full_like(y_test, float(np.mean(y_train)))
    report.baseline_mae_ratio = float(mean_absolute_error(y_test, baseline))
    report.baseline_mae_dollars = float(
        np.mean(np.abs((baseline - y_test) * fmr_test))
    )
    report.coefficients = {
        name: float(coef) for name, coef in zip(features, model.coef_)
    }
    report.coefficients["intercept"] = float(model.intercept_)

    return model, report


def save(model: object) -> None:
    import joblib

    config.RENT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": list(config.RENT_MODEL_FEATURES)},
                config.RENT_MODEL_PATH)


def load() -> Optional[dict]:
    """Load the persisted model, or `None` if it has not been trained.

    `None` rather than an exception: an untrained model is a condition the Valuation
    agent discloses through the normal flag mechanism, not a crash. The pipeline must
    still run and still produce a report on a machine where nobody has run training.
    """
    if not config.RENT_MODEL_PATH.exists():
        return None
    import joblib

    return joblib.load(config.RENT_MODEL_PATH)


def predict_ratio(bundle: dict, bedrooms: float, bathrooms: float,
                  square_feet: float) -> float:
    """Predict rent-to-FMR ratio for one subject. Returns the raw model output.

    Bounds are applied by the caller rather than here, so that a prediction landing
    outside the plausible range stays visible as a modeling result instead of being
    silently clipped into looking reasonable.
    """
    values = {"bedrooms": bedrooms, "bathrooms": bathrooms, "square_feet": square_feet}
    row = [[float(values[name]) for name in bundle["features"]]]
    return float(bundle["model"].predict(row)[0])
