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

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd

import config
from tools import county_crosswalk, hud_fmr, kaggle_data, zcta_crosswalk


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
    # Anchor resolution, split. The mixed basis is a real limitation of the target and
    # has to be visible in the report that justifies the model, not only in the code:
    # a row anchored at ZIP and a row anchored at county are ratios to different
    # denominators. Kept because restricting training to SAFMR counties would drop New
    # York entirely and train on a basis inference does not always see.
    rows_anchored_at_zip: int = 0
    rows_anchored_at_zip_backcast: int = 0
    rows_anchored_at_county: int = 0
    distinct_zctas: int = 0
    # The counties whose training rows were anchored at ZIP resolution. Inference must
    # consult this rather than asking HUD whether a ZIP schedule exists *today*: SAFMR
    # coverage expanded after 2020, so Los Angeles has ZIP schedules for FY2026 and none
    # for the corpus's FY2019. Anchoring such a subject at ZIP would multiply a
    # county-relative ratio by a ZIP-level figure — two different denominators. The
    # model can only be applied on the basis it was fit on.
    zip_anchored_counties: list = field(default_factory=list)
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
            f"  anchored at ZIP        {self.rows_anchored_at_zip:>7,}"
            f"   ({self.distinct_zctas} distinct ZCTAs,"
            f" {self.rows_anchored_at_zip_backcast:,} back-cast)",
            f"  anchored at county     {self.rows_anchored_at_county:>7,}",
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
        # The county's *current* schedule too, keyed "current". `_zip_anchor_tables`
        # needs it as the denominator of the ZIP relativity it carries backwards; it
        # costs one cached call per county and keeps that logic from making its own.
        if (entityid, "current") not in table:
            try:
                table[(entityid, "current")] = client.get_fmr(entityid).rents
            except (hud_fmr.HudFmrApiError, KeyError, StopIteration):
                pass
    return table


def _zip_anchor_tables(
    pairs: set[tuple[str, int]],
    client: hud_fmr.HudFmrClient,
    county_table: dict[tuple[str, int], dict],
) -> tuple[dict[tuple[str, int], dict], dict[tuple[str, int], str]]:
    """ZIP-resolution FMR schedules per (county, fiscal year), back-cast where needed.

    Returns `(tables, basis)` — absolute rents by ZIP, and how each pair's table was
    obtained (`"published"`, `"backcast"`, or `"none"`).

    **The problem this solves is that Small Area FMR coverage is younger than the rent
    corpus.** HUD expanded SAFMR substantially after 2020: Los Angeles County publishes
    474 ZIP schedules for FY2026 and **zero** for FY2019, and Cuyahoga went 0 → 126 over
    the same window. Cook County is the exception at 344 → 370. So ZIP resolution exists
    on the *inference* side (FY2026) and is largely absent on the *training* side
    (FY2019-2020), and anchoring the two differently is not an option — the model learns
    a ratio, and a ratio to a ZIP denominator is a different quantity from a ratio to a
    county denominator. Training one way and predicting the other is wrong by the spread
    between them, which HUD publishes as roughly 2x within a single county.

    **So the ZIP's position relative to its county is carried backwards in time.** Where
    a fiscal year has no published ZIP schedule but the current year does, each ZIP's
    FMR is reconstructed as `(current ZIP ÷ current county) × that year's county FMR`.
    The dollar level therefore always comes from the row's own year — the vintage
    discipline §2 exists to protect is untouched — and only the *within-county shape* is
    imported from today.

    **That assumption is tested rather than asserted, on the two counties where both
    years are published.** Correlation between FY2019 and FY2026 ZIP-to-county ratios is
    r = 0.873 (Cook) and r = 0.771 (Philadelphia); back-cast error is a median 4.5% /
    5.1% with a p90 near 19%. Against that, the county anchor's blind spot is the entire
    neighborhood effect — measured at +40.1% (Logan Square) and +66.2% (Ohio City). The
    trade is roughly 5% of new error to remove 40-66% of existing error, and it is
    disclosed as `"backcast"` so a reader is never told a reconstructed figure is a
    published one.

    Reconstruction is deliberately *not* attempted for a county that has no ZIP schedule
    in any year — there is no shape to import, and inventing one would be fabrication.
    """
    tables: dict[tuple[str, int], dict] = {}
    basis: dict[tuple[str, int], str] = {}

    current_cache: dict[str, dict] = {}
    for entityid, year in sorted(pairs):
        try:
            published = client.get_fmr_zip_table(entityid, year=year)
        except (hud_fmr.HudFmrApiError, KeyError, StopIteration):
            published = {}

        if published:
            tables[(entityid, year)] = published
            basis[(entityid, year)] = "published"
            continue

        if not config.RENT_MODEL_BACKCAST_ZIP_FMR:
            tables[(entityid, year)] = {}
            basis[(entityid, year)] = "none"
            continue

        if entityid not in current_cache:
            try:
                current_cache[entityid] = client.get_fmr_zip_table(entityid)
            except (hud_fmr.HudFmrApiError, KeyError, StopIteration):
                current_cache[entityid] = {}
        current_zips = current_cache[entityid]
        county_now = county_table.get((entityid, "current"))
        if not current_zips or not county_now:
            tables[(entityid, year)] = {}
            basis[(entityid, year)] = "none"
            continue

        county_then = county_table.get((entityid, year))
        if not county_then:
            tables[(entityid, year)] = {}
            basis[(entityid, year)] = "none"
            continue

        rebuilt: dict[str, dict] = {}
        for zip_code, rents in current_zips.items():
            row: dict[str, float] = {}
            for field_name, value in rents.items():
                try:
                    now, then = float(county_now[field_name]), float(county_then[field_name])
                    if now > 0:
                        row[field_name] = float(value) / now * then
                except (KeyError, TypeError, ValueError):
                    continue
            if row:
                rebuilt[zip_code] = row
        tables[(entityid, year)] = rebuilt
        basis[(entityid, year)] = "backcast" if rebuilt else "none"

    return tables, basis


def anchor_for_row(
    bedrooms: int,
    county_fips: str,
    fiscal_year: int,
    zcta: Optional[str],
    county_table: dict,
    zip_tables: dict,
    zip_basis: Optional[dict] = None,
) -> tuple[float, str]:
    """The FMR to normalize one row against, and the resolution it came from.

    **The single place ZIP-vs-county anchoring is decided**, shared by training and by
    the comp cross-check so the two cannot drift. A model trained against ZIP schedules
    and applied against county ones would be quietly wrong by up to the spread between
    them, which HUD publishes as roughly 2x within a single county — the kind of
    mismatch that produces a plausible model no test would catch.

    Returns `(fmr, resolution)` where resolution is `"zip"` (HUD published a Small Area
    FMR for this ZIP in this fiscal year), `"zip_backcast"` (the ZIP's position within
    its county was carried back from the current year — see `_zip_anchor_tables`), or
    `"county"`. `(nan, "none")` means no schedule had a usable figure.

    The three are kept distinct rather than collapsed to "zip / not zip" because they
    carry different confidence, and the report says which one produced a given estimate.
    """
    field_name, _ = hud_fmr.bedroom_field(int(bedrooms))

    if zcta:
        rents = zip_tables.get((county_fips, fiscal_year), {}).get(zcta)
        if rents:
            try:
                value = float(rents[field_name])
                if value > 0:
                    basis = (zip_basis or {}).get((county_fips, fiscal_year), "published")
                    return value, "zip_backcast" if basis == "backcast" else "zip"
            except (KeyError, TypeError, ValueError):
                pass

    rents = county_table.get((county_fips, fiscal_year))
    if rents:
        try:
            value = float(rents[field_name])
            if value > 0:
                return value, "county"
        except (KeyError, TypeError, ValueError):
            pass

    return float("nan"), "none"


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

    # ZIP resolution where HUD publishes Small Area FMRs, county resolution elsewhere.
    # Batch-joined for the reason county_crosswalk.county_fips_for_points documents: this
    # is thousands of points, well above the crossover where sjoin's fixed cost amortizes.
    df["zcta"] = zcta_crosswalk.zctas_for_points(
        df["latitude"].tolist(), df["longitude"].tolist()
    )

    pairs = set(zip(df["county_fips"], df["fiscal_year"]))
    table = _fmr_table(pairs, client)
    zip_tables, zip_basis = _zip_anchor_tables(pairs, client, table)

    anchors = df.apply(
        lambda row: anchor_for_row(
            row["bedrooms"], row["county_fips"], row["fiscal_year"],
            row["zcta"], table, zip_tables, zip_basis,
        ),
        axis=1,
    )
    df["fmr"] = [a[0] for a in anchors]
    df["fmr_resolution"] = [a[1] for a in anchors]
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
    report.rows_anchored_at_zip = int(
        df["fmr_resolution"].isin(["zip", "zip_backcast"]).sum()
    )
    report.rows_anchored_at_zip_backcast = int((df["fmr_resolution"] == "zip_backcast").sum())
    report.rows_anchored_at_county = int((df["fmr_resolution"] == "county").sum())
    report.zip_anchored_counties = sorted(
        df.loc[df["fmr_resolution"].isin(["zip", "zip_backcast"]), "county_fips"].unique()
    )
    report.distinct_zctas = int(df.loc[df["fmr_resolution"].isin(["zip", "zip_backcast"]), "zcta"].nunique())
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


def save(model: object, report: TrainingReport) -> None:
    """Persist the fitted model together with the run that produced it.

    **The report travels with the model on purpose.** Without it the holdout MAE lives
    only in the training script's stdout, which means the report can print an estimate
    with no error band beside it — a point estimate reading as more precise than the
    thing that produced it, which is the presentation §1 objects to. It also means the
    quoted error is necessarily the one *this* artifact scored: a retrain that moved the
    MAE moves the number in the report, rather than leaving a stale figure in a docstring
    somewhere describing a model that is no longer on disk.

    `dataclasses.asdict` rather than the object itself, so the bundle stays plain data
    and loading it does not require this module's class definitions to be import-stable.
    """
    import joblib

    config.RENT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": list(config.RENT_MODEL_FEATURES),
            "report": asdict(report),
            "trained_at": datetime.now(),
        },
        config.RENT_MODEL_PATH,
    )


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


@dataclass
class CompAnchoring:
    """Comp rents re-expressed in the subject's current dollars, plus what was lost.

    `comps_used` against `comps_available` is the disclosure, not a diagnostic. A
    cross-check that survived on 3 of 8 comps is a much weaker check than one that
    survived on 8, and a single "comps used" count cannot distinguish them.
    """

    implied_rents: list[float] = field(default_factory=list)
    comps_used: int = 0
    comps_available: int = 0
    # How many of `comps_used` were anchored at ZIP rather than county resolution.
    # Reported rather than assumed uniform: a comp set spanning a SAFMR county and a
    # non-SAFMR one is normalized on two different bases.
    zip_anchored: int = 0

    @property
    def median(self) -> Optional[float]:
        return float(np.median(self.implied_rents)) if self.implied_rents else None

    def percentile(self, q: float) -> Optional[float]:
        return float(np.percentile(self.implied_rents, q)) if self.implied_rents else None


def anchor_comp_rents(
    comps: list,
    subject_fmr: float,
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> CompAnchoring:
    """Re-express each comp's rent as "what a unit like this would rent for, here, today."

    This is the same normalization the training set uses, run in reverse and pointed at
    the subject: divide the comp's rent by the FMR for *its own* county and *its own*
    fiscal year to recover a structural ratio, then multiply by the subject's current
    FMR. Two distortions come out in that round trip — the comp's vintage (the corpus is
    a 2018-19 scrape) and the comp's location (a comp inside the search radius can sit
    in a different county with a different rent schedule).

    **Why not simply average the comps' rents.** That figure is an unanchored 2019
    dollar amount, and §8 forbids one reaching the Summarizer. Comparing a 2026 model
    output against it would not be a cross-check at all — it would reproduce the exact
    vintage error §2's whole design exists to prevent, while looking like a validation.
    This project has already made that mistake once, against the Chicago demo's rents,
    and caught it only by measuring.

    A comp is dropped when it carries no coordinate, no listing date, an unresolvable
    county, an absent FMR, or a ratio outside `config.RENT_MODEL_MIN/MAX_RATIO` — the
    same bounds the training set applies, because a ratio that would have been a data
    defect in training is still one here. Dropped comps are counted, never silently
    discarded: the count is what tells the report how much the check is worth.

    Per-point county resolution rather than the batch form, deliberately. A comp set is
    at most `config.MIN_QUALIFYING_COMPS` rows, far below the low-hundreds crossover
    `county_crosswalk.county_fips_for_points` documents, where `sjoin`'s fixed setup
    cost never amortizes.
    """
    client = client or hud_fmr.HudFmrClient()
    result = CompAnchoring(comps_available=len(comps))
    if not comps or not subject_fmr or subject_fmr <= 0:
        return result

    resolved: list[tuple[object, str, int, "Optional[str]"]] = []
    for comp in comps:
        if comp.latitude is None or comp.longitude is None or comp.listed_date is None:
            continue
        fips = county_crosswalk.lookup_county_fips(comp.latitude, comp.longitude)
        if fips is None:
            continue
        # Per-point rather than the batch join: a comp set is at most
        # config.MIN_QUALIFYING_COMPS rows, far below the crossover where sjoin's fixed
        # setup cost amortizes — the same call this module's county lookup makes here.
        zcta = zcta_crosswalk.lookup_zcta(comp.latitude, comp.longitude)
        resolved.append(
            (comp, fips, fmr_fiscal_year(pd.Timestamp(comp.listed_date)), zcta)
        )

    pairs = {(fips, year) for _, fips, year, _ in resolved}
    table = _fmr_table(pairs, client)
    zip_tables, zip_basis = _zip_anchor_tables(pairs, client, table)

    for comp, fips, year, zcta in resolved:
        # Same function training uses, deliberately. If a comp were anchored at county
        # resolution while the training rows behind the model were anchored at ZIP, the
        # cross-check would compare two ratios with different denominators and report the
        # difference as a disagreement about rent.
        comp_fmr, resolution = anchor_for_row(
            comp.beds, fips, year, zcta, table, zip_tables, zip_basis
        )
        if resolution == "none" or comp_fmr != comp_fmr:
            continue
        ratio = comp.rent / comp_fmr
        if not (config.RENT_MODEL_MIN_RATIO <= ratio <= config.RENT_MODEL_MAX_RATIO):
            continue
        result.implied_rents.append(ratio * subject_fmr)
        if resolution in ("zip", "zip_backcast"):
            result.zip_anchored += 1

    result.comps_used = len(result.implied_rents)
    return result
