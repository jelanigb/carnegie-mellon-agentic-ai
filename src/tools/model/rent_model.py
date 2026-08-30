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
   `RENT_ANCHORED_TO_MARKET_INDEX` (info). The number is not a market observation; it is a
   modeled ratio times a government reference figure, and the report says so.
2. **No FMR, no estimate.** A subject whose county will not resolve — New England, or no
   coordinates at all — has no anchor, so this path produces nothing and raises
   `RENT_ANCHOR_UNAVAILABLE` rather than falling back to a raw comp mean. A raw comp
   mean is precisely the unanchored 2019 figure the design forbids.
3. **The ratio assumption is load-bearing, and it has been measured and found false.**
   It holds that rent-to-FMR structure is stable over ~7 years. U8.0 tested that against
   Zillow's ZORI series and found the FMR schedule rising +51.9% while market rents rose
   +33.5% over the same interval, so the anchor drifted ~18 points away from the market
   it prices and the raw product reads high. `tools/rent_drift.py` corrects for it per
   ZCTA at prediction time and discloses the correction; §6's cut-list item 6 carries the
   structural fix the correction stands in for. This paragraph previously said nothing in
   the project verified the assumption, which was true when written and stopped being
   true at U8.0.

Feature choice is deliberately narrow and excludes any market identifier — see
`config.RENT_MODEL_FEATURES` for why a metro dummy would defeat the ratio design. The
estimator's *form* is `config.RENT_MODEL_ESTIMATOR`, gradient boosting since U11.1, and
that constant carries the cross-validated evidence for the choice.
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
    rows_missing_anchor: int
    rows_outside_ratio_bounds: int
    rows_trained: int
    holdout_rows: int
    counties: int
    fiscal_years: list[int] = field(default_factory=list)
    # Anchor tier, split. The mixed basis is a real limitation of the target and has to
    # be visible in the report that justifies the model, not only in the code: a row
    # anchored to its own ZIP's ZORI series and one anchored to its county's median are
    # ratios to different denominators. Kept rather than restricting training to
    # ZIP-covered rows, because a ZIP's series begins only when Zillow has enough
    # listings there and excluding the rest would discard 27% of the corpus (U11.3).
    rows_anchored_at_zip: int = 0
    rows_anchored_at_county: int = 0
    distinct_zctas: int = 0
    mae_ratio: float = 0.0
    mae_dollars_at_holdout_fmr: float = 0.0
    baseline_mae_ratio: float = 0.0
    baseline_mae_dollars: float = 0.0
    r2: float = 0.0
    # How the scores above were obtained. 0 means the single-split protocol this model
    # used before U11.1; anything else is the number of cross-validation folds, in which
    # case `holdout_rows` equals `rows_trained` because every row is held out exactly once.
    cv_folds: int = 0
    # In-fold training error, in dollars, averaged across folds. Reported beside the
    # held-out figure because the *gap* between them is the overfitting guard §6 cut-list
    # item 1a's deferral was justified by, and a held-out score alone cannot show it.
    train_mae_dollars: float = 0.0
    # Only one of these is populated, depending on what the estimator exposes: a linear
    # model has `coef_`, an ensemble has `feature_importances_`, and neither has both.
    # Kept as two fields rather than one renamed "diagnostics" because they are not the
    # same quantity and a reader should not have to guess which one they are looking at.
    coefficients: dict = field(default_factory=dict)
    feature_importances: dict = field(default_factory=dict)
    # The input-domain bounds this frame supports, measured here and carried on the
    # artifact for the reason `mae_dollars_by_metro` is (U8.4 Q2(c)): it is a *measured
    # property of the fit*, not a tunable, so putting it in `config.py` would let it drift
    # from the model it describes. The percentiles that place it are the tunable, and they
    # are in `config.RENT_MODEL_DOMAIN_PERCENTILES`.
    feature_ranges: dict = field(default_factory=dict)
    sqft_per_bedroom_bounds: tuple = ()
    # Per-metro breakdown of the same holdout residuals above, keyed by the labels in
    # `config.INDEXED_MARKETS` (already documented there as "the inference trio plus New
    # York"). {"New York": {"mae_dollars": 1065.xx, "n": 41}, ...}. A groupby over
    # residuals already computed, not a second fit — see `_mae_dollars_by_metro` (U8.4,
    # OQ-3). A metro absent here had zero holdout rows.
    mae_dollars_by_metro: dict = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"shortlist rows           {self.rows_in_shortlist:>7,}",
            f"  dropped, no county     {self.rows_unresolved_county:>7,}",
            f"  dropped, no anchor     {self.rows_missing_anchor:>7,}",
            f"  dropped, ratio bounds  {self.rows_outside_ratio_bounds:>7,}",
            f"trained on               {self.rows_trained:>7,}"
            f"   ({self.counties} counties, FY {self.fiscal_years})",
            f"  anchored at ZIP        {self.rows_anchored_at_zip:>7,}"
            f"   ({self.distinct_zctas} distinct ZCTAs)",
            f"  anchored at county     {self.rows_anchored_at_county:>7,}",
            f"holdout rows             {self.holdout_rows:>7,}",
            "",
            f"scored by                {self.cv_folds}-fold cross-validation"
            if self.cv_folds
            else "scored by                a single holdout split",
            f"MAE (rent/FMR ratio)     {self.mae_ratio:>7.4f}",
            f"MAE (dollars)            {self.mae_dollars_at_holdout_fmr:>7.2f}",
            f"R^2                      {self.r2:>7.4f}",
            f"MAE in-fold (dollars)    {self.train_mae_dollars:>7.2f}",
            f"  train/holdout gap      "
            f"{self.mae_dollars_at_holdout_fmr - self.train_mae_dollars:>7.2f}"
            f"   <- the overfitting guard",
            "",
            "Baseline — predict the training-set mean ratio for every row:",
            f"  MAE (ratio)            {self.baseline_mae_ratio:>7.4f}",
            f"  MAE (dollars)          {self.baseline_mae_dollars:>7.2f}",
        ]
        if self.sqft_per_bedroom_bounds:
            low, high = self.sqft_per_bedroom_bounds
            lo_pct, hi_pct = config.RENT_MODEL_DOMAIN_PERCENTILES
            lines.append("")
            lines.append(
                f"Input domain — sqft per bedroom, p{lo_pct:.1%} to p{hi_pct:.1%}: "
                f"{low:,.0f} to {high:,.0f}"
            )
        if self.mae_dollars_by_metro:
            lines.append("")
            lines.append("MAE (dollars) by metro:")
            for metro, stats in self.mae_dollars_by_metro.items():
                lines.append(
                    f"  {metro:<14} {stats['mae_dollars']:>7.2f}   (n={stats['n']:,})"
                )
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


@dataclass
class AnchorTables:
    """Everything `anchor_for_row` reads, assembled once rather than per row.

    Training resolves ~5,700 rows and the comp cross-check resolves at most
    `config.MIN_QUALIFYING_COMPS`, so both want the ZORI panel and the county medians
    loaded once; `zori` caches them per process and this holds the references plus a memo
    for the per-ZIP series, which is a row-by-row lookup over a 9 MB frame otherwise.
    """

    fmr_county: dict
    zori_panel: object = None
    zori_county_median: object = None
    zori_county_zips: object = None
    _series: dict = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.zori_panel is not None

    def series(self, zcta: Optional[str]):
        """This ZIP's monthly series, memoized. `None` where ZORI does not cover it."""
        if not zcta or self.zori_panel is None:
            return None
        if zcta not in self._series:
            from tools import zori

            self._series[zcta] = zori.series_for_zip(self.zori_panel, zcta)
        return self._series[zcta]


def build_anchor_tables(
    pairs: set[tuple[str, int]], client: hud_fmr.HudFmrClient
) -> AnchorTables:
    """Assemble the anchor's inputs for a set of (county entityid, fiscal year) pairs.

    The FMR half is fetched per pair because the bedroom *shape* is county-and-year
    specific; the ZORI half is process-cached and shared.
    """
    from tools import zori

    tables = AnchorTables(fmr_county=_fmr_table(pairs, client))
    tables.zori_panel = zori.panel()
    county = zori.county_median_tables()
    if county is not None:
        tables.zori_county_median, tables.zori_county_zips = county
    return tables


def bedroom_shape(
    bedrooms: int, county_fips: str, fiscal_year: int, fmr_county: dict
) -> tuple[float, bool]:
    """FMR's multiplier for this bedroom count, with the schedule's level divided out.

    Returns `(shape, cap_exceeded)`. The shape is this bedroom count's FMR over the
    `config.RENT_ANCHOR_SHAPE_REFERENCE_BEDROOMS` figure for the same county and year, so
    it is ~1.0 for a typical unit and carries only the schedule's *relative* structure
    across unit sizes.

    **This is the one thing FMR still supplies after U11.3, and the reason the anchor is a
    hybrid rather than pure ZORI.** Zillow publishes a single smoothed series per ZIP
    across all unit types — no bedroom dimension exists in it at all — so an anchor built
    from ZORI alone would price a studio and a four-bedroom against the same reference and
    leave `RENT_MODEL_FEATURES`' `bedrooms` column to absorb the difference. Dividing the
    level out is what lets the two sources compose: ZORI decides *how expensive this
    place is*, FMR decides only *how the schedule steps between unit sizes*, and the
    schedule's own drift against the market (U8.0) cancels out of a within-year ratio.

    `hud_fmr.bedroom_field` caps at four bedrooms and reports it, so a five-bedroom
    subject is priced on the four-bedroom step and the caller discloses that — which is
    why `FMR_BEDROOM_CAP_EXCEEDED` survives this change with its meaning intact.
    """
    rents = fmr_county.get((county_fips, fiscal_year))
    field_name, capped = hud_fmr.bedroom_field(int(bedrooms))
    reference_field, _ = hud_fmr.bedroom_field(
        config.RENT_ANCHOR_SHAPE_REFERENCE_BEDROOMS
    )
    if not rents:
        return float("nan"), capped
    try:
        own, reference = float(rents[field_name]), float(rents[reference_field])
    except (KeyError, TypeError, ValueError):
        return float("nan"), capped
    if own <= 0 or reference <= 0:
        return float("nan"), capped
    return own / reference, capped


def anchor_for_row(
    bedrooms: int,
    county_fips: str,
    fiscal_year: int,
    month: str,
    zcta: Optional[str],
    tables: AnchorTables,
) -> tuple[float, str]:
    """The reference figure to normalize one row against, and the tier it came from.

    **The single place anchoring is decided**, shared by training and by the comp
    cross-check so the two cannot drift. A model trained against one reference and applied
    against another would be quietly wrong by the spread between them — the kind of
    mismatch that produces a plausible model no test would catch.

    `anchor = ZORI(this ZIP, this month) x FMR bedroom shape`, with the ZORI term falling
    back to the county's median across its covered ZIPs. Returns `(anchor, tier)` where
    tier is `"zip"`, `"county"`, or `"none"` when no usable figure exists.

    **The county tier is not a nicety.** A ZIP's ZORI series begins only when Zillow has
    enough listings there, so 1,515 of the corpus's 5,686 rows sit before their own ZIP's
    series starts; without the fallback the anchor would discard 27% of the training data.
    `scripts/zori_county_tier.py` measures the recovery at 99.0%. The two tiers are
    different denominators — a county median carries far less location signal than a ZIP
    series — which is why the tier is returned rather than absorbed, and why the report
    discloses it.
    """
    shape, _ = bedroom_shape(bedrooms, county_fips, fiscal_year, tables.fmr_county)
    if shape != shape:  # NaN — no FMR schedule, so no bedroom step to apply
        return float("nan"), "none"

    series = tables.series(zcta)
    if series is not None and month in series.index:
        value = series[month]
        if not pd.isna(value) and float(value) > 0:
            return float(value) * shape, "zip"

    median = tables.zori_county_median
    if median is not None:
        geoid = str(county_fips)[:5]
        if geoid in median.index and month in median.columns:
            value = median.at[geoid, month]
            if not pd.isna(value) and float(value) > 0:
                return float(value) * shape, "county"

    return float("nan"), "none"


def county_zip_count(tables: AnchorTables, county_fips: str, month: str) -> int:
    """How many ZIPs stood behind a county-tier anchor, for the caller to disclose.

    A county median over one ZIP is a county median in name only, and nothing else in the
    returned figure distinguishes it from a median over thirty — the same reason
    `CompAnchoring.comps_used` travels beside `comps_available`.
    """
    counts = tables.zori_county_zips
    if counts is None:
        return 0
    geoid = str(county_fips)[:5]
    if geoid not in counts.index or month not in counts.columns:
        return 0
    value = counts.at[geoid, month]
    return 0 if pd.isna(value) else int(value)


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
        rows_missing_anchor=0,
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

    # Each row is anchored at its own listing month, not at a fixed date: a 2018 listing
    # and a 2019 one faced different markets, and pinning both to one month would import
    # that year's trend into the ratio as noise. Keyed as ZORI's month columns are.
    df["month"] = listed.dt.to_period("M").dt.to_timestamp("M").dt.strftime("%Y-%m-%d")

    pairs = set(zip(df["county_fips"], df["fiscal_year"]))
    tables = build_anchor_tables(pairs, client)

    anchors = df.apply(
        lambda row: anchor_for_row(
            row["bedrooms"], row["county_fips"], row["fiscal_year"],
            row["month"], row["zcta"], tables,
        ),
        axis=1,
    )
    df["anchor"] = [a[0] for a in anchors]
    df["anchor_tier"] = [a[1] for a in anchors]
    missing = df["anchor"].isna() | (df["anchor"] <= 0)
    report.rows_missing_anchor = int(missing.sum())
    df = df[~missing]

    df["rent_to_anchor"] = df["price"] / df["anchor"]
    in_bounds = df["rent_to_anchor"].between(
        config.RENT_MODEL_MIN_RATIO, config.RENT_MODEL_MAX_RATIO
    )
    report.rows_outside_ratio_bounds = int((~in_bounds).sum())
    df = df[in_bounds]

    report.counties = int(df["county_fips"].nunique())
    report.fiscal_years = sorted(int(y) for y in df["fiscal_year"].unique())
    report.rows_anchored_at_zip = int((df["anchor_tier"] == "zip").sum())
    report.rows_anchored_at_county = int((df["anchor_tier"] == "county").sum())
    report.distinct_zctas = int(df.loc[df["anchor_tier"] == "zip", "zcta"].nunique())
    _measure_domain(df, report)
    return df.reset_index(drop=True), report


def _measure_domain(df: pd.DataFrame, report: TrainingReport) -> None:
    """Record what this frame can speak to, for `subject_is_out_of_domain` to read later.

    Measured on the frame that survived every filter above rather than on the raw corpus,
    because the model is fit on the survivors and it is the survivors' range that bounds
    what it has seen.

    `bedrooms == 0` rows are excluded from the per-bedroom ratio rather than coerced: a
    studio has a floor area but no per-bedroom figure, and dividing by zero to produce an
    infinity would drag the upper bound to meaninglessness.
    """
    report.feature_ranges = {
        name: (float(df[name].min()), float(df[name].max()))
        for name in config.RENT_MODEL_FEATURES
    }
    per_bedroom = (
        df.loc[df["bedrooms"] > 0, "square_feet"] / df.loc[df["bedrooms"] > 0, "bedrooms"]
    ).dropna()
    if not per_bedroom.empty:
        low, high = config.RENT_MODEL_DOMAIN_PERCENTILES
        report.sqft_per_bedroom_bounds = (
            float(per_bedroom.quantile(low)),
            float(per_bedroom.quantile(high)),
        )


def subject_is_out_of_domain(
    bundle: dict, bedrooms: float, bathrooms: float, square_feet: float
) -> Optional[str]:
    """Why this subject is outside what the model trained on, or `None` if it is inside.

    **The competence check, and it is deliberately separate from the estimator.** Until
    U11.1 this question was answered as a side effect: the shipped LinearRegression
    extrapolated a negative `bedrooms` coefficient into an implausible *ratio*, which the
    Valuation agent's output-side band caught. A tree-based estimator cannot produce an
    implausible ratio — its prediction is an average of training targets already bounded
    to that band — so it clamps to its nearest leaf and returns a confident number for a
    property it has no basis to price. Measured Aug 30, 2026: a 2bd / 100,000 sqft subject
    prices at 62.21 under the old form (refused) and at 2.20 under this one (reported).
    Swapping the form without this check would therefore have retired a disclosure
    silently, which is the failure §8's Transparent Degradation principle exists to
    prevent.

    Asked of the *inputs* rather than the output, so the answer does not depend on which
    estimator is fitted, and returned as a reader-facing clause rather than a boolean so
    the caller can say which attribute is unlike the training data and by how much.

    An older artifact carries no bounds — it was persisted before they were measured — and
    returns `None` rather than refusing everything: an absent measurement is not evidence
    that a subject is out of domain.
    """
    report = bundle.get("report") or {}
    values = {"bedrooms": bedrooms, "bathrooms": bathrooms, "square_feet": square_feet}

    for name, bounds in (report.get("feature_ranges") or {}).items():
        value = values.get(name)
        if value is None:
            continue
        low, high = float(bounds[0]), float(bounds[1])
        if not low <= float(value) <= high:
            readable = name.replace("_", " ")
            return (
                f"its {readable} of {float(value):,.0f} falls outside the {low:,.0f} to "
                f"{high:,.0f} range covered by every listing the model learned from"
            )

    bounds = report.get("sqft_per_bedroom_bounds") or ()
    if len(bounds) == 2 and bedrooms and float(bedrooms) > 0 and square_feet:
        per_bedroom = float(square_feet) / float(bedrooms)
        low, high = float(bounds[0]), float(bounds[1])
        if not low <= per_bedroom <= high:
            return (
                f"its {per_bedroom:,.0f} square feet per bedroom is outside the "
                f"{low:,.0f} to {high:,.0f} range the model's training listings span — "
                f"the floor area and the bedroom count are each ordinary, but the "
                f"combination is not one it has seen"
            )
    return None


def _mae_dollars_by_metro(
    df: pd.DataFrame,
    holdout_index: np.ndarray,
    predicted: np.ndarray,
    y_test: np.ndarray,
    fmr_test: np.ndarray,
) -> dict:
    """Break the holdout residuals already computed down by metro (U8.4, OQ-3).

    A groupby over an existing result, not a second fit: `predicted`, `y_test` and
    `fmr_test` are the same arrays `train()` already scored, in the same order as
    `holdout_index` because all four came out of the same `train_test_split` call.

    Grouped by `config.INDEXED_MARKETS`, whose own docstring already names it "the
    inference trio plus New York" — exactly the comparison OQ-3 needs: the model's error
    where it is actually used, against the market it is weakest in. Matched the way
    `scripts/metro_shortlist_ablation.py` established as correct — a boolean mask against
    `df`'s own index — rather than round-tripped through `kaggle_data.filter_markets`,
    whose `ignore_index=True` re-indexing silently breaks that join (see that script's
    module docstring for the bug this repeats the fix for, not the mistake).

    `n` travels with each figure: a holdout slice can be thin, and a MAE over forty rows
    should not be presented like one over five thousand.
    """
    residual_dollars = np.abs((predicted - y_test) * fmr_test)
    holdout = df.loc[holdout_index]
    by_metro: dict[str, dict] = {}
    for state, patterns in config.INDEXED_MARKETS.items():
        label = patterns[0]
        mask = (holdout["state"] == state) & holdout["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        n = int(mask.sum())
        if n == 0:
            continue
        by_metro[label] = {
            "mae_dollars": float(residual_dollars[mask.to_numpy()].mean()),
            "n": n,
        }
    return by_metro


def _estimator():
    """A fresh, unfitted estimator of the configured form.

    A factory rather than a module-level instance because cross-validation fits one per
    fold and a shared instance would carry the previous fold's state into the next. The
    import is local for the reason the rest of this module's sklearn imports are: the
    pipeline loads a persisted model and never trains, so a machine running the graph
    should not pay sklearn's import cost to do it.
    """
    if config.RENT_MODEL_ESTIMATOR == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(random_state=config.RENT_MODEL_RANDOM_SEED)
    if config.RENT_MODEL_ESTIMATOR == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(random_state=config.RENT_MODEL_RANDOM_SEED)
    if config.RENT_MODEL_ESTIMATOR == "linear":
        from sklearn.linear_model import LinearRegression

        return LinearRegression()
    raise ValueError(
        f"config.RENT_MODEL_ESTIMATOR={config.RENT_MODEL_ESTIMATOR!r} names no known "
        f"form. Expected 'gradient_boosting', 'random_forest' or 'linear'. Refusing to "
        f"fall back to a default, because a silently substituted estimator would ship a "
        f"model nobody chose."
    )


def train(
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> tuple[object, TrainingReport]:
    """Fit the ratio model under k-fold cross-validation, then refit it on everything.

    Reports against a mean-ratio baseline as well as in absolute terms. An MAE alone
    cannot say whether the features carry signal — per §8, a check whose result was
    structurally guaranteed proves nothing, and "predict the average ratio for every
    row" is the null hypothesis this model has to beat to justify existing at all.

    **Cross-validated since U11.1**, which is the condition OQ-4 attached to reopening
    model form at all, and the reason the per-metro breakdown is worth reading: the
    previous single 20% split scored New York on a slice thin enough to move with the
    seed. It also reports the in-fold training error beside the held-out one, because the
    *gap* is the overfitting guard that justified deferring model form in the first place
    and a held-out score alone cannot show it.
    """
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import KFold

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
    y = df["rent_to_anchor"].to_numpy(dtype=float)
    fmr = df["anchor"].to_numpy(dtype=float)

    # Out-of-fold predictions: every row scored exactly once, by a model fit without it.
    # That is what lets the per-metro breakdown below be read at all — under the previous
    # single 20% split New York's holdout slice was thin enough that the figure moved with
    # the seed, which is the weakness OQ-4 named when it asked for proper validation.
    out_of_fold = np.full(len(df), np.nan)
    baseline_out_of_fold = np.full(len(df), np.nan)
    in_fold_mae: list[float] = []

    splitter = KFold(
        n_splits=config.RENT_MODEL_CV_FOLDS,
        shuffle=True,
        random_state=config.RENT_MODEL_RANDOM_SEED,
    )
    for train_index, test_index in splitter.split(X):
        model = _estimator().fit(X[train_index], y[train_index])
        out_of_fold[test_index] = model.predict(X[test_index])
        # The null hypothesis, refit per fold like the model it is compared against.
        # Computing it once on the full frame would let it see the rows it is scored on,
        # which would flatter the baseline and understate what the features are worth.
        baseline_out_of_fold[test_index] = float(np.mean(y[train_index]))
        in_fold = model.predict(X[train_index])
        in_fold_mae.append(
            float(np.mean(np.abs((in_fold - y[train_index]) * fmr[train_index])))
        )

    # The artifact is refit on everything. The scores above already establish what it
    # generalizes to, so holding 20% back from the model that actually ships would discard
    # data for a second, worse estimate of a number cross-validation has already produced.
    model = _estimator().fit(X, y)

    report.cv_folds = int(config.RENT_MODEL_CV_FOLDS)
    report.rows_trained = int(len(df))
    report.holdout_rows = int(len(df))
    report.mae_ratio = float(mean_absolute_error(y, out_of_fold))
    report.r2 = float(r2_score(y, out_of_fold))
    # Dollar error is the ratio error re-expressed at each row's own FMR, which is what a
    # reader of the report actually experiences.
    report.mae_dollars_at_holdout_fmr = float(np.mean(np.abs((out_of_fold - y) * fmr)))
    report.train_mae_dollars = float(np.mean(in_fold_mae))
    report.mae_dollars_by_metro = _mae_dollars_by_metro(
        df, df.index.to_numpy(), out_of_fold, y, fmr
    )

    report.baseline_mae_ratio = float(mean_absolute_error(y, baseline_out_of_fold))
    report.baseline_mae_dollars = float(
        np.mean(np.abs((baseline_out_of_fold - y) * fmr))
    )
    # Whichever the fitted form exposes; see `TrainingReport` on why these are two fields.
    if hasattr(model, "coef_"):
        report.coefficients = {
            name: float(coef) for name, coef in zip(features, model.coef_)
        }
        report.coefficients["intercept"] = float(model.intercept_)
    if hasattr(model, "feature_importances_"):
        report.feature_importances = {
            name: float(value)
            for name, value in zip(features, model.feature_importances_)
        }

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
    subject_anchor: float,
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> CompAnchoring:
    """Re-express each comp's rent as "what a unit like this would rent for, here, today."

    This is the same normalization the training set uses, run in reverse and pointed at
    the subject: divide the comp's rent by the anchor for *its own* ZIP at *its own*
    listing month to recover a structural ratio, then multiply by the subject's anchor.
    Two distortions come out in that round trip — the comp's vintage (the corpus is a
    2018-19 scrape) and the comp's location (a comp inside the search radius can sit in a
    different ZIP, and a different county, with a different rent level).

    **Since U11.3 the vintage comes out where it arises rather than being corrected
    afterwards.** The anchor is a monthly market series, so a 2019 comp is divided by the
    2019 market and the subject is multiplied by today's; the schedule-vs-market drift
    U8.0 measured never enters, and `tools/rent_drift.py`'s symmetric correction was
    retired with it.

    **Why not simply average the comps' rents.** That figure is an unanchored 2019
    dollar amount, and §8 forbids one reaching the Summarizer. Comparing a 2026 model
    output against it would not be a cross-check at all — it would reproduce the exact
    vintage error §2's whole design exists to prevent, while looking like a validation.
    This project has already made that mistake once, against the Chicago demo's rents,
    and caught it only by measuring.

    A comp is dropped when it carries no coordinate, no listing date, an unresolvable
    county, an unresolvable anchor, or a ratio outside `config.RENT_MODEL_MIN/MAX_RATIO` — the
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
    if not comps or not subject_anchor or subject_anchor <= 0:
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
        listed = pd.Timestamp(comp.listed_date)
        resolved.append(
            (
                comp,
                fips,
                fmr_fiscal_year(listed),
                listed.to_period("M").to_timestamp("M").strftime("%Y-%m-%d"),
                zcta,
            )
        )

    pairs = {(fips, year) for _, fips, year, _, _ in resolved}
    tables = build_anchor_tables(pairs, client)

    for comp, fips, year, month, zcta in resolved:
        # Same function training uses, deliberately. If a comp were anchored at county
        # resolution while the training rows behind the model were anchored at ZIP, the
        # cross-check would compare two ratios with different denominators and report the
        # difference as a disagreement about rent. Each comp is read at *its own* listing
        # month, so its vintage is divided out the same way training divided out the row's.
        comp_anchor, tier = anchor_for_row(
            comp.beds, fips, year, month, zcta, tables
        )
        if tier == "none" or comp_anchor != comp_anchor:
            continue
        ratio = comp.rent / comp_anchor
        if not (config.RENT_MODEL_MIN_RATIO <= ratio <= config.RENT_MODEL_MAX_RATIO):
            continue
        result.implied_rents.append(ratio * subject_anchor)
        if tier == "zip":
            result.zip_anchored += 1

    result.comps_used = len(result.implied_rents)
    return result
