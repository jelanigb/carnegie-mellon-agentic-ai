"""Single source of truth for tunable parameters.

Per docs/implementation_plan.md §8, no agent may hardcode any value that appears here.
These get tuned across U4-U7, and a value buried inside an agent function is a value
that cannot be tuned without a code change.

Values marked PROVISIONAL are initial guesses awaiting empirical tuning; the unit that
tunes each one is named alongside it.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
SRC_DIR = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Comps retrieval loop — the X / Y / Z parameters from Checkpoint 2.1, Loop 2
# --------------------------------------------------------------------------

# X: initial search radius. Widened on each relaxation pass.
#
# Tuned in U4 against measured comp density per market (comps within radius, 2BR exact):
#
#     market        0.5mi   1mi   2mi   3mi   5mi
#     Los Angeles       7    50+   50+   50+   50+
#     Cleveland         0     0    50+   50+   50+
#     Chicago           3     3     5    22    50+
#     Brooklyn          0     1     4    38    50+
#
# At the original X=1.0 every market except Los Angeles relaxed at least once, so the
# relaxation flag fired on essentially every run and therefore carried no information.
# X=2.0 lets the two dense markets clear the threshold on the first pass, so a
# relaxation flag now means something specific happened rather than being routine.
INITIAL_SEARCH_RADIUS_MILES = 2.0
RADIUS_EXPANSION_FACTOR = 2.0  # PROVISIONAL — tune in U4
MAX_SEARCH_RADIUS_MILES = (
    15.0  # hard ceiling; beyond this a "comp" is not comparable
)

# Y: exit condition. The loop stops once this many qualifying comps are found.
# Also the number of results retrieved, which Checkpoint 3.1 asks to be stated
# explicitly as a design decision rather than left implicit.
MIN_QUALIFYING_COMPS = 8  # PROVISIONAL — tune in U4

# Z: iteration cap. On exhaustion the loop exits with a sparse-comps flag rather
# than returning a silently weak result.
MAX_RETRIEVAL_ITERATIONS = 4  # PROVISIONAL — tune in U4

# Hard match criteria, relaxed in order as the loop widens its search.
# Minimum number of *distinct coordinates* a comp set should represent before it is
# reported without a spatial-concentration disclosure.
#
# Measured Aug 22, 2026, and this threshold is set against that measurement rather than
# chosen for roundness. 92% of the corpus carries no street address, and those rows sit
# on city-area placeholder coordinates — so a comp set can satisfy MIN_QUALIFYING_COMPS
# while describing far fewer places than listings. Running the shipped retrieval path on
# the three demo subjects: Los Angeles returned 8 comps from 3 coordinates, Chicago 5
# from 2, Cleveland 8 from **1**.
#
# 3 is therefore the value that separates the case that is arguably fine (LA) from the
# two that need saying out loud, rather than a bar every metro clears — per §2's tuning
# principle, a signal that never fires conveys nothing. PROVISIONAL — U8 has the case
# volume to settle it.
COMP_MIN_DISTINCT_LOCATIONS = 3

# Decimal places for a reported comp distance. Was 3 (~1.6 m implied precision), which
# was false precision on a coordinate that is a city-area placeholder for most rows.
# One decimal (~160 m) still distinguishes a neighbouring block from the next
# neighbourhood without claiming the corpus knows where a building is.
COMP_DISTANCE_DECIMALS = 1

COMP_MATCH_BEDROOM_TOLERANCE = 0  # exact bed match before relaxation
COMP_MATCH_SQFT_TOLERANCE_PCT = 0.25  # PROVISIONAL — tune in U4

# Share of the returned comp set that may fall outside the *unrelaxed* match criteria
# above before the drift is disclosed (U7.3).
#
# The relaxation loop already flags each concession it makes, but a concession is not the
# same thing as a consequence: dropping the square-footage band permits dissimilar comps,
# it does not guarantee them. What matters to a reader is how many actually came back
# unlike the subject, which is only knowable after the final query returns.
#
# Measured on the demo subjects, both against a 950 sqft subject and a +/-25% band:
#   Los Angeles, no relaxation      0 of 8 outside  (range 979-1167)
#   Chicago, sqft band dropped      3 of 8 outside  (range 510-2000)
# Mean drift barely separates those two — +13.3% against +17.8% — because one 2,000 sqft
# comp and one 510 sqft comp pull in opposite directions. A count of comps outside the
# band separates them cleanly, which is why the check is written on the count.
#
# 0.25 admits one outlier in a set of eight and discloses two. PROVISIONAL — tune in U8
# against the eval batch, where a case can be built to sit either side of the line.
COMP_MAX_OUTSIDE_MATCH_SHARE = 0.25


# --------------------------------------------------------------------------
# Critic / human review
# --------------------------------------------------------------------------

# Below this confidence, the deal routes to human review instead of the Summarizer.
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.60  # PROVISIONAL — tune in U7

# Bounds the Critic -> Planner rework cycle. §3 requires every cycle to be bounded by
# an explicit counter in state rather than by LangGraph's recursion_limit, so that
# exhaustion escalates gracefully instead of raising.
MAX_REWORKS = 2  # PROVISIONAL — tune in U7

# Severity weights used when aggregating flags into a confidence score.
FLAG_SEVERITY_PENALTY = {
    "info": 0.0,
    "warn": 0.15,
    "critical": 0.40,
}  # PROVISIONAL — tune in U7


# --------------------------------------------------------------------------
# Extraction loop
# --------------------------------------------------------------------------

# Bounded retries before the Extractor escalates rather than looping (Checkpoint 2.1,
# Loop 1). Each retry re-prompts with the Pydantic ValidationError text.
MAX_EXTRACTION_RETRIES = 3

# Fields without which downstream valuation is not meaningful. Missing ones become
# clarifying questions; unresolvable ones become flagged assumptions.
# Names must match DealTerms attributes exactly — these are looked up by getattr.
REQUIRED_DEAL_FIELDS = ("full_address", "price", "unit_count")

# How far a caller-supplied coordinate may sit from the geocode of the listing's own
# address before the two are treated as describing different places (U3).
#
# The conflict is escalated rather than resolved, because the system cannot tell which
# input the caller meant: the address with its correct coordinates, or the coordinates
# with a mistyped address. What it *can* do is refuse to pick one silently. The
# geocoded point is what the pipeline carries — the report prints the address, so comp
# retrieval is anchored to the same place the report names rather than to a location the
# reader never sees.
#
# 0.5 mi is set against what the error costs downstream rather than against geocoding
# precision: INITIAL_SEARCH_RADIUS_MILES is 2.0, so a half-mile displacement moves a
# meaningful share of the comp set.
#
# One measurement exists, and it argues the line is tight rather than loose. U2's Chicago
# demo carried hand-picked "Logan Square" coordinates that sit 0.54 mi from the Census
# parcel geocode of the address in its own listing text — i.e. a neighbourhood-level
# coordinate chosen by a careful person trips this. Read either way: the threshold
# catches a real discrepancy, or it fires on inputs nobody would call wrong. Left at 0.5
# because the flag escalates rather than blocks, and because a threshold wide enough to
# never fire is the failure mode §2 warns about in the search-radius tuning.
#
# PROVISIONAL — one data point is not a tuning. U8 has the volume to settle it.
COORDINATE_CONFLICT_THRESHOLD_MILES = 0.5


# --------------------------------------------------------------------------
# Data layer
# --------------------------------------------------------------------------

# Inference metros (§2). Settled after the density check in
# scripts/verify_metro_selection.py overturned the original NY/Chicago/Philadelphia
# hypothesis.
INFERENCE_METROS = ("Chicago", "Los Angeles", "Cleveland")

# Redfin: drop implausible medians before any aggregation. The raw extract contains
# non-arm's-length transfers ($1, $101, $500) that would corrupt a median or a YoY
# calculation.
#
# Resolved to $10,000 — the low end of §2's proposed $10-20k range — on measured
# evidence: 63 of 58,863 non-null rows (0.107%) fall below $10k, and 90.5% of those
# report HOMES SOLD == 1, the signature of a single non-market transfer. A $20k floor
# would drop 294 rows (0.499%) instead, and in the $10-20k band the single-sale share
# falls to 72.7% while some metros show a *sustained* cheap tail — real distressed
# activity. $20k would delete observations rather than clean them.
#
# Scope note: this floor is inert for all three inference metros, whose minimum medians
# are Chicago $207,500, LA $695,000, Cleveland $58,333. It is insurance for the tier-3
# fallback and future metro additions, not a fix to a defect in the current pipeline.
REDFIN_MIN_MEDIAN_SALE_PRICE = 10_000

# The extract on disk is Monthly; §2 specifies a rolling window computed locally
# rather than re-downloading a Rolling-3-Months extract.
REDFIN_ROLLING_WINDOW_PERIODS = 3

# Interest rates near zero pushed price growth well above trend in this window.
# Blending it silently would skew the "base case" toward an anomalous stretch, so any
# average including it carries kind="anomalous_period_included".
ANOMALOUS_PERIOD = ("2020-01-01", "2022-12-31")

# Kaggle: outlier bounds. The extract is 99.5% complete on core features, with only
# 79 rows outside these bounds, so this trims noise rather than reshaping the data.
KAGGLE_MIN_RENT = 300.0
KAGGLE_MAX_RENT = 10_000.0

# Training metros (§7 decision #4, closed Aug 21, 2026). Distinct from INFERENCE_METROS
# above, and deliberately a superset of it: the regression predicts a *ratio* to local
# FMR rather than a dollar level, so it benefits from markets it will never be asked to
# price, while comp retrieval needs density in the specific subject market.
#
# Selected on Kaggle rent density alone — every metro in §2's density table at >=200
# usable rows, minus Boston. The table's own verdict column fails Cincinnati on Redfin
# sales volume; that bar is an *inference* requirement (an appreciation series) and the
# rent model reads Redfin at no point, so Cincinnati is selected here with 798 usable
# rows. Boston is excluded as blocked rather than unselected: county_crosswalk.py
# returns None throughout New England (TODO(geography)), so its rows cannot be
# FMR-normalized and would drop silently at training time.
#
# Keyed state -> city-name patterns, the shape tools/kaggle_data.filter_markets consumes.
# Matching is word-boundary, not substring, so "Cleveland" rolls up "Cleveland Heights"
# while "Queens" does not match "Queensbury" — both real cases in this data.
#
# Measured 5,717 usable rows (scripts/train_rent_model.py --dry-run re-derives it).
# Note for anyone reconciling against §2: that section quotes 21,768 rows for a
# candidate ~10-metro shortlist, which no metro-filtered count reproduces. The six
# states these metros sit in hold 22,323 usable rows between them, so the older figure
# is a state-level rollup. 5,717 is the metro-filtered number and the one to trust.
TRAINING_METROS: dict[str, list[str]] = {
    "CA": ["Los Angeles"],
    "OH": ["Cincinnati", "Cleveland"],
    "IL": ["Chicago"],
    "NJ": ["Newark", "Jersey City"],
    "NY": ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"],
    "PA": ["Pittsburgh", "Philadelphia"],
}



# Comp-index scope. The third of this project's three metro scopes, and the one that
# decides which listings can be *retrieved* as comparables — distinct from
# INFERENCE_METROS (which markets have a Redfin appreciation series) and from
# TRAINING_METROS (which listings the regression learns from). See
# docs/design/data_sources.md for all three side by side.
#
# The inference trio plus New York. New York is indexed **deliberately**, as the
# sparse-comps case: §2 measured it as genuinely thin in Staten Island while dense in
# central Brooklyn, which makes it the one market that exercises the relaxation loop to
# exhaustion against real data. It is why the Staten Island demo returns no comps and no
# market benchmark while still producing a rent estimate.
#
# New York rolls up its boroughs, which appear as separate `cityname` values. Matching is
# word-boundary (tools/kaggle_data.city_matches): "Cleveland" must catch "Cleveland
# Heights" while "Queens" must not catch "Queensbury" and "Bronx" must not catch
# "Bronxville" — all real cases in this data.
#
# Lived in scripts/build_comps_index.py until Aug 22, 2026. Moved here because §8 makes
# config.py the only home for a tunable parameter, and because a metro scope defined in a
# script is a metro scope nobody finds when asking which markets the system covers —
# which is exactly how it got missed.
#
# Changing this requires a re-index: .venv/bin/python scripts/build_comps_index.py
INDEXED_MARKETS: dict[str, list[str]] = {
    "IL": ["Chicago"],
    "CA": ["Los Angeles"],
    "OH": ["Cleveland"],
    "NY": ["New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"],
}

# --------------------------------------------------------------------------
# Rent regression (U5 — tools/model/rent_model.py)
# --------------------------------------------------------------------------
# The target is rent / FMR-for-that-row's-county-and-year, not rent. §2's rent-anchoring
# design in one line: a 2018-19 corpus cannot supply a 2026 dollar figure, but the
# *ratio* of a unit's rent to its local FMR is a structural property that ages far more
# slowly than the dollar level does. Training learns the ratio; prediction multiplies it
# by today's FMR for the subject's own county.

RENT_MODEL_PATH = DATA_DIR / "processed" / "rent_model.joblib"

# Features. Deliberately small and all structural — no free text, no market identifier.
# Excluding the metro is the point rather than an omission: a metro dummy would let the
# model memorize a per-market rent level, which is exactly the dollar-level dependence
# the FMR ratio exists to remove. What generalizes to an unseen market is how much a
# bedroom or a square foot moves rent *relative to local FMR*, and that is all these
# columns carry.
RENT_MODEL_FEATURES = ("bedrooms", "bathrooms", "square_feet")

# One fitted coefficient is worth knowing about before reading a prediction, because
# it looks like a defect and is not: **`bedrooms` comes out negative** (-0.33 per
# bedroom as of the ZIP-anchored retrain, Aug 22, 2026; -0.44 before it). The target is
# a *ratio to FMR*, not a rent, and HUD's
# schedule climbs with bedroom count faster than real rents do — LA's FY2026 4BR FMR
# is 1.41x its 2BR, while actual 4BR rents are not — so the ratio genuinely falls as
# bedrooms rise. The consequence is real and bounded: a high bedroom count on a small
# footprint drives the predicted ratio below RENT_MODEL_MIN_RATIO, and the Valuation
# agent refuses the estimate rather than reporting it. Pinned by
# tests/test_flag_propagation.py::test_an_implausible_prediction_is_refused_rather_than_reported.

# TODO(cut-list): feature engineering and model form are deferred, not dismissed — §6's
# cut list, item 1a, carries the measurement and the reasoning. In short: the estimator is
# a vanilla LinearRegression on these three raw columns, it underfits rather than overfits
# (train-vs-holdout gap $0.04), and a random forest on identical data and features reaches
# $434 MAE against this model's $524 — about 17% of the error is in model form alone.
# Deferred because this project's subject is agent architecture, and because added capacity
# introduces a real overfitting risk this model cannot currently have (poly-3 scored
# R² -13.3 on the same probe), so it needs proper validation rather than one split.

# Holdout is random rather than by-metro. A by-metro split would answer a different and
# more demanding question — does the model transfer to a market it never saw — which is
# worth asking but is not the claim this build makes; §2 scopes the model to the three
# inference metros, all of which are in the training set. Recorded because the weaker
# split is a real limitation of the reported MAE and should be disclosed, not because it
# is wrong for the purpose. TODO(U8): add a leave-one-metro-out run as evaluation
# evidence if the buffer week allows; it needs no new data, only a second fit.
RENT_MODEL_HOLDOUT_FRACTION = 0.20
RENT_MODEL_RANDOM_SEED = 42

# Below this, refuse to train rather than emit a model fit on too little data. Set
# against the measured 5,717-row training set, so it trips on a broken filter or a
# missing corpus rather than on ordinary variation.
RENT_MODEL_MIN_TRAINING_ROWS = 1_000

# Ratio bounds. A rent/FMR ratio outside this range is a data defect, not a luxury unit:
# the corpus carries rows whose square_feet or bedrooms are transcription errors, and an
# unbounded ratio lets one of them dominate a least-squares fit. Bounds are wide enough
# to keep genuine high-end and subsidized units.
RENT_MODEL_MIN_RATIO = 0.25
RENT_MODEL_MAX_RATIO = 4.0

# HUD publishes FMR by federal fiscal year. The corpus spans Dec 2018 - Dec 2019, so a
# row is normalized against the FMR year its own listing date falls in, not against a
# single assumed vintage. FY N runs Oct 1 (N-1) through Sep 30 N.
RENT_MODEL_FMR_FISCAL_YEAR_START_MONTH = 10

# Whether to reconstruct a ZIP-level FMR schedule for fiscal years HUD did not publish
# one for, by carrying each ZIP's position within its county backwards from the current
# year. See tools/model/rent_model._zip_anchor_tables.
#
# **Set from a measurement that split the change in half.** Anchoring at ZIP resolution
# is supposed to absorb local rent level, which shows up as *lower* dispersion in the
# rent-to-FMR ratio. Measured on the training shortlist, by how the ZIP schedule was
# obtained:
#
#     published   n=1,109   CV 44.3% -> 35.9%   (-19.1%)   works as intended
#     back-cast   n=4,281   CV 34.0% -> 36.2%   (+6.6%)    adds noise
#
# So the ZIP anchor earns its place and the back-cast does not. The relativity it carries
# back is stable enough to look reasonable (r = 0.873 Cook / 0.771 Philadelphia, median
# error ~5%) but that residual error is comparable to the within-county signal it is
# trying to capture, so it imports more noise than structure.
RENT_MODEL_BACKCAST_ZIP_FMR = False


# --------------------------------------------------------------------------
# Valuation agent (U5 — agents/valuation_rent.py)
# --------------------------------------------------------------------------
# The agent's Observe step re-expresses each retrieved comp's rent in the subject's
# current dollars (rent / that comp's own county-and-year FMR, times the subject's
# current FMR) and compares the model's estimate against the median of those. Both
# constants below govern that comparison, not the model itself.

# Below this many successfully normalized comps, the cross-check is not run at all and
# the report says so. A "median" of one or two comps is a number, not a distribution,
# and disagreeing with it would say more about the comps than about the estimate.
# Set at 3 rather than tuned: it is the smallest count for which a median is not simply
# one of the two values, and the measured cost is one demo deal (Staten Island, which
# retrieves no comps at all and would fail this check regardless).
RENT_COMP_CROSSCHECK_MIN_COMPS = 3

# How far the modelled rent may sit from the comp median before the report says the two
# disagree.
#
# Set against measured divergence rather than chosen. Five subjects, Aug 22, 2026 —
# the three synthetic ones in scripts/valuation_evidence.py and the demo listings in
# demo_deals.py, whose addresses geocode elsewhere in the same metros:
#
#   -21.6%  Los Angeles (Echo Park)   -30.4%  Chicago (Logan Square)
#   -40.0%  Cleveland (Ohio City)
#
# **Re-measured after ZIP-resolution anchoring landed the same day: -10.7% / -14.3% /
# -13.9%.** The threshold was kept at 0.30 rather than tightened to match, and the reason
# is the point of the change. Those divergences used to be dominated by the model's
# inability to see below the county line, so the flag fired on a known structural blind
# spot rather than on anything about the deal. With the anchor at ZIP resolution the
# residual is uniform across all three markets — an 18.4-point spread collapsed to 3.6 —
# which is what a model characteristic looks like rather than a location effect.
#
# So the flag is now silent on all three inference markets by design, and that is the
# correct state: it is available to detect a genuine anomaly instead of reporting a
# mechanism. TODO(U8): confirm against the eval batch that something still trips it —
# a flag nothing can raise would corrupt the coverage assertion, and this one moved from
# firing on 2 of 5 subjects to 0 of 5 in a single change.
#
# **What the flag is actually detecting, corrected Aug 22, 2026.** An earlier reading of
# this held that the markets it fires on are the ones whose comp sets are unrepresentative.
# Measured against the right baseline — the candidate pool at the same radius, rather than
# the whole metro — that is wrong: semantic ranking moves the comp median only +2.7% /
# +21.6% / +4.2%, while the neighborhood itself moves it +5.1% / +40.1% / +66.2%. The comps
# are reporting real neighborhood premiums correctly.
#
# What diverges is the *model*, because RENT_MODEL_FEATURES excludes any market identifier
# and the FMR anchor is county-level, so nothing in the pipeline represents sub-metro rent
# variation. This threshold therefore currently fires on a known structural blind spot
# rather than on an anomaly, which is a real limitation of the check and not a tuning
# problem. §2, "The rent estimate is location-blind below the county."
#
# PROVISIONAL on both counts. Five subjects show the signal separates but cannot place the
# line precisely — Chicago straddling it is the proof. Retune in U8 against the eval batch,
# and revisit the whole check if a ZIP-level anchor lands (docs/design/data_sources.md, "The
# sub-metro gap"). `scripts/valuation_evidence.py --diagnose-divergence` reproduces it.
RENT_COMP_DIVERGENCE_THRESHOLD_PCT = 0.30


# --------------------------------------------------------------------------
# Scenario / Forecast agent (U6 - agents/scenario_forecast.py)
# --------------------------------------------------------------------------
# Two quantities, two sources, and they are NOT interchangeable (decision #16): Redfin
# drives price appreciation, HUD FMR history drives rent growth. Measured across the
# inference trio, the two are negatively correlated (pooled r = -0.309), so a rent
# forecast taken off the price series would point the wrong way.

# How far the scenarios project. Five years is the standard multi-family hold period,
# and it is long enough that the choice of growth band is visible rather than academic:
# on Chicago's rent series the two defensible base cases (4.34%/yr with the FY2023-24
# cohort shift included, 1.80%/yr with it screened out) compound to 23.7% against 9.3%
# over this horizon - $2,474 against $2,186 on a $2,000 rent. That gap is the reason
# this node branches instead of committing to one framing.
FORECAST_HORIZON_YEARS = 5

# --- FMR rent-growth series (tools/fmr_history.py) -------------------------
# HUD publishes FY2017 onward through the API this project already caches, giving nine
# year-over-year observations. Note the asymmetry with the price series: Redfin supplies
# 88 *monthly* YoY observations, so the two series cannot use the same band construction
# and do not (see FMR_BAND_* below).
FMR_HISTORY_FIRST_YEAR = 2017

# Below this many usable YoY observations, no rent-growth band is produced at all. A
# "range" over three points describes the sample, not the market. Follows the precedent
# set by RENT_COMP_MIN_COMPS_FOR_CROSS_CHECK: refuse the figure rather than qualify it.
FMR_HISTORY_MIN_YOY_OBSERVATIONS = 5

# The cohort panel: every HUD FMR area this project touches, FY2017-2026, all five
# bedroom fields. Committed rather than pulled at runtime - deriving the cohort live
# would cost ~100 API calls on a cold cache inside a per-deal node. Rebuild with
# `scripts/fmr_history_evidence.py --build-panel` when a fiscal year is published.
FMR_COHORT_PANEL_PATH = SRC_DIR / "tools" / "data" / "fmr_cohort_panel.json"

# --- Cohort-shift screen ---------------------------------------------------
# A fiscal year where *every* area in the panel moved together, well above the long-run
# baseline. FY2023 (+5.10pp) and FY2024 (+7.48pp) are the two in the current panel.
#
# **This screen replaces the "methodology jump" screen the plan originally specified,
# and the rename is the point.** Whether HUD changed its methodology or the 2021-22
# market surge reached an administrative series two years late is not determinable from
# FMR alone - both produce a cohort-wide move. What IS observable is whether every area
# moved at once, so that is what this measures and what the report says. Attribution
# waits for Zillow ZORI, which is market-observed (decision #16).
#
# Measured, not chosen: sorting the nine fiscal years by cohort excess leaves a 4.05pp
# gap between the largest ordinary year (FY2021, +1.05pp) and the smallest shifted one
# (FY2023, +5.10pp). Any threshold in 2-5pp selects the same two years, so this value
# sits in the middle of a wide indifference band rather than on a boundary.
# Reproduce with `scripts/fmr_history_evidence.py`.
FMR_COHORT_SHIFT_EXCESS_PP = 3.0

# One area departing from its own cohort, which is a *local* event rather than a
# national one - Jersey City FY2026 (+20.2% against a 4.2% cohort) is the panel's
# clearest case. Disclosed, never excluded: a local move is exactly the market signal a
# forecast should carry. Set at the panel's p90 |deviation| (7.7pp), rounded, so it
# marks the tail rather than ordinary dispersion (median 2.7pp).
FMR_LOCAL_DEVIATION_PP = 8.0

# --- Rent band construction ------------------------------------------------
# **Bands are the worst and best fiscal years actually observed; the base case is the
# geometric mean of the retained years.** Nine annual points cannot support Redfin's
# definition, where "optimistic" is the best sustained 12-observation stretch, so the
# construction had to be chosen rather than copied. Four candidates were measured:
#
#   * min / geometric mean / max (adopted). Coherent by construction, and each outer
#     band names a real fiscal year the report can cite.
#   * p25 / arithmetic mean / p75. **Rejected on its own output:** mixing a mean with
#     percentiles does not order. Chicago reported base 4.34% against an optimistic
#     4.09% on the unscreened series, and base 1.80% against a *pessimistic* 1.92% on
#     the screened one - a base case outside its own band, in both directions.
#   * p25 / median / p75. Orders correctly, but on 7-9 points the percentiles are
#     interpolations between adjacent observations rather than genuinely more robust
#     summaries, and the median moves in discrete jumps - Cleveland's shifts 2.64pp on a
#     one-slot change, more than its mean does.
#   * A sustained 3-year window, the closest analogue to the price-side method.
#     **Rejected on measurement:** screening FY2023-24 breaks the run of consecutive
#     years, so only three windows qualify and FY2025-26 - the two most recent
#     observations, the ones a forecast leans on hardest - fall out of all of them.
#
# Geometric rather than arithmetic because the projection compounds: an arithmetic mean
# of annual rates overstates cumulative growth (measured here at 0.07-0.16pp/yr across
# the trio, ~1pp over the five-year horizon).
#
# **The known weakness, recorded rather than papered over:** min and max are extreme
# order statistics, so they can only widen as the series lengthens, unlike percentiles.
# Measured by recomputing what each statistic would have reported at n=5, 6 and 7, the
# minimum has not moved at all in any of the three metros and the maximum moved less
# than p75 did in Cleveland - so the drift is structural but not yet observable, and the
# series grows by one observation per year. The IQR below exists partly so that
# comparison stays available if it ever does bite.
FMR_BAND_USE_OBSERVED_EXTREMES = True

# Disclosed alongside the bands, never as the bands. The interquartile range shows
# whether an extreme is an isolated spike or part of a cluster: Chicago's -4.2% minimum
# against a 1.9% p25 says the pessimistic band rests on an outlier, which the headline
# triple alone cannot reveal. Rendered in the report's disclosure block under its own
# name so it cannot be mistaken for the projection basis.
FMR_IQR_LOWER_PERCENTILE = 25
FMR_IQR_UPPER_PERCENTILE = 75

# --------------------------------------------------------------------------
# Models (OpenRouter)
# --------------------------------------------------------------------------
#
# Decision #8, closed Aug 16, 2026 — see §7 for the full table.
#
# **Paid variants, not `:free`.** The project constraint is to prefer free tools *where
# their quality is good*, and on this axis the free tier failed a different test: its
# `:free` variants are served from provider-shared pools, so two bake-off passes measured
# availability rather than capability — models lost whole listings to 429s, and which
# ones failed moved between passes. On paid variants, across two further passes, all
# seven candidates returned 3/3 schema-valid, 23/23 hand-checked fields, correct
# assumption verdicts, and **zero 429s**. The comparison only became a comparison once it
# was paid for.
#
# Cost is why that trade is easy rather than a compromise: one extraction is ~1.8K input
# and ~300 output tokens, so the model below runs about **$0.00015 per call** — roughly
# 6,700 extractions per dollar, against a $100 project ceiling. The free tier was costing
# more in evidence quality than paid inference costs in money.
#
# **Why this model.** With correctness tied across all seven, the remaining signals were
# latency and price. `nemotron-3-nano-30b-a3b` was the balance pick: perfect on every
# pass (including both free-tier passes, where it was the only family that never
# 429'd), the cheapest of the nemotron family, and second-fastest overall at 18.0s/11.3s
# for three listings. Two alternatives, recorded so the choice stays reviewable rather
# than looking inevitable: `google/gemma-4-26b-a4b-it` was fastest on both passes
# (8.2s/6.5s) at 2.3x the price, and `openai/gpt-oss-20b` was cheapest at $0.00009 but
# slower. Note gemma-4-26b scored a *spurious assumption* on both free-tier passes and
# neither paid pass — free and paid variants of one model name are not always the same
# deployment, which is worth knowing before trusting a free-tier measurement of anything.
#
# **Staleness is the durable risk, not selection.** The four IDs these replace were valid
# when written and dead six days later: `meta-llama/llama-3.3-70b-instruct:free` stopped
# being free, with no free Llama variant left. That would have surfaced as an opaque
# error mid-extraction. `tools/llm_client.verify_models_live()` now checks these against
# the live catalogue and `main.py` calls it before building the graph, so a dead ID fails
# loudly at launch instead.
#
# The four-way split remains structural. Only MODEL_EXTRACTION is exercised by a built
# agent; the Critic and Summarizer make no LLM calls yet, so there is still nothing to
# choose them against — the same reasoning §7 used to defer this decision originally,
# now scoped to three roles instead of four. Revisit at U7 and U9.

MODEL_DEV = "nvidia/nemotron-3-nano-30b-a3b"
MODEL_EXTRACTION = "nvidia/nemotron-3-nano-30b-a3b"
MODEL_CRITIC = "nvidia/nemotron-3-nano-30b-a3b"
MODEL_SUMMARIZER = "nvidia/nemotron-3-nano-30b-a3b"
# Added in U6. The Scenario agent's evaluator scores enumerated hypotheses and selects
# which evidence to pull for them; that is a judgement task rather than an extraction
# task, so it gets its own role even though every role currently resolves to the same
# model. Same reasoning as the original four-way split: the seam is where a future
# bake-off happens, and naming it costs nothing now.
MODEL_SCENARIO = "nvidia/nemotron-3-nano-30b-a3b"

LLM_TIMEOUT_SECONDS = 90
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.0  # deterministic everywhere; see TOT_TEMPERATURE


# --------------------------------------------------------------------------
# Model response cache (tools/llm_cache.py)
# --------------------------------------------------------------------------

# "off" | "read_write" | "replay". Env-driven so a run can switch without an edit —
# `LLM_CACHE_MODE=replay .venv/bin/python ...` is how an evaluation run pins itself to
# recorded responses.
#
# Measured justification: a live call ran 9.9-23s per listing across the U3 bake-off,
# against milliseconds for a local read. The cache is a latency and reproducibility
# mechanism first; the free tier's 50/day cap is what prompted it, but paid inference
# removes that pressure without removing either of the other two reasons.
LLM_CACHE_MODE = os.environ.get("LLM_CACHE_MODE", "read_write")

# Two stores, one mechanism, split by whether the contents belong in git.
#
# The default is under `data/` (gitignored) because a development loop iterating on a
# prompt generates a recording per revision, and committing that churn would spend review
# attention — the project's scarcest resource — on files nobody needs to read.
#
# `src/eval/data/` is the committed counterpart: the recordings an evaluation replays
# have to travel with the repo, or a fresh clone cannot reproduce the results the report
# quotes. U8 points at it explicitly; nothing writes there by accident.
LLM_CACHE_DIR = DATA_DIR / "processed" / "llm_cache"
EVAL_DATA_DIR = SRC_DIR / "eval" / "data"
EVAL_RESULTS_DIR = SRC_DIR / "eval" / "results"
EVAL_RECORDINGS_DIR = EVAL_DATA_DIR / "llm_recordings"


# --------------------------------------------------------------------------
# Retrieval / embeddings
# --------------------------------------------------------------------------

# Local embedding model — no API cost, runs comfortably on CPU.
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
CHROMA_PERSIST_DIR = DATA_DIR / "processed" / "chroma"
CHROMA_COLLECTION = "rental_comps"

# §2: each listing is embedded as one document rather than chunked. Listings are short,
# self-contained records whose fields are mutually dependent, so splitting one would
# separate a rent figure from the context that makes it interpretable.
CHUNK_LISTINGS = False

# U4 ablation: when False, the retrieval node returns no comps, so the pipeline can be
# run with and without grounding on identical inputs. Checkpoint 3.1 asks for evidence
# that retrieval meaningfully influences output; this produces that comparison directly.
RETRIEVAL_ENABLED = True


# --------------------------------------------------------------------------
# Observability
# --------------------------------------------------------------------------

LANGSMITH_PROJECT = "deal-evaluator"
LANGSMITH_ENABLED = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"


# --------------------------------------------------------------------------
# Tree-of-Thought reasoning (§7 decisions #12, #14 — U6/U7)
# --------------------------------------------------------------------------
# Applied inside two nodes only: Scenario/Forecast (U6) and the Critic's cross-agent
# consistency checks (U7). The rest of the pipeline is ordered by data dependency, so
# there is nothing there to search over.
#
# Every value below is PROVISIONAL and tuned in U8, where the eval harness supplies
# synthetic cases whose correct branch is known by construction. They are named here
# rather than inside the agent because a tunable hardcoded in an agent is a defect (§8).

# Candidate hypotheses generated per expansion. Anchored to the Tree-of-Thought paper's
# b=5 on Game of 24 (4% -> 74% over chain-of-thought), not yet to this project's data.
TOT_BRANCHING_FACTOR = 5

# Depth 1 picks framing (window + appreciation tier), 2 selects a rate within it, 3
# reconciles survivors into the three reported scenarios. Deeper adds no new question.
TOT_MAX_DEPTH = 3

# Survivors carried forward per level. Three, because three scenarios are reported.
TOT_BEAM_WIDTH = 3

# ...except at the framing level, where exactly one survives, and the difference is not
# a tuning choice. A framing is which treatment of the data the whole forecast rests on
# (are the FY2023-24 cohort-shift years screened out of the rent bands? is 2020-2022 in
# the price bands?). Carrying three framings forward produces three scenarios built on
# three different readings of the same series - not a scenario set, and impossible to
# describe with one provenance statement.
#
# **Found by reading the output rather than by reasoning about it.** The first Chicago
# run reported an optimistic case of +19.03%/yr rent directly beneath a basis block
# stating that FY2023-24 had been held out - and 19.03% *is* Chicago's FY2024 figure,
# arriving from a framing that had not screened it. All four framings are still scored
# and compared before the cut; only one is carried.
TOT_FRAMING_BEAM_WIDTH = 1

# No rejection threshold at the framing level, and this is a statement about what a
# framing is rather than a loosened bar. A threshold asks "did this hypothesis survive
# contact with the data?" — a real question about a band pairing, and a category error
# about a framing, since framings are enumerated from the treatments the evidence
# actually supports and are therefore all defensible by construction. Decision #12 says
# as much: this fork is in the design precisely because it has no single correct answer.
#
# **Also found by reading output.** With the uniform 0.40 applied, an evaluator applying
# ordinary skepticism scored all four Los Angeles framings below it and emptied the beam
# on a deal whose rent and price series were both fully available. The level's job is to
# select, and selection is what TOT_FRAMING_BEAM_WIDTH does.
TOT_FRAMING_PRUNE_THRESHOLD = 0.0

# Two reported scenarios whose projected outcomes differ by less than this are not
# telling a reader two things. Used by the reconciliation step to disclose that the
# search returned fewer distinct answers than it has labels for.
TOT_SCENARIO_DISTINCTNESS_PCT = 1.0

# Branches scoring below this are discarded. Pruning is never silent: each discarded
# branch writes {id, parent, depth, score, prune_reason} to the ledger on DealState so
# the report can disclose what was considered and why it was dropped (decision #14).
TOT_PRUNE_THRESHOLD = 0.40

# Scores within this distance are treated as tied, and resolved toward the more
# conservative growth assumption rather than by arbitrary ordering. For an investment
# tool the cost of being wrong is not symmetric.
TOT_TIE_EPSILON = 0.05

# **Currently unused, and kept deliberately rather than by oversight.** This was the
# sampling temperature for hypothesis generation, and the documented exception to
# LLM_TEMPERATURE = 0.0 above. U6 enumerates its hypothesis space instead of sampling it
# (decision #17), so nothing reads this and the whole pipeline runs deterministic —
# the exception the comment on LLM_TEMPERATURE describes no longer exists in the
# Scenario node.
#
# Retained because the Critic's search (U7, decision #12) is unbuilt and its space is
# not yet known to be enumerable: candidate objections are generated rather than drawn
# from a fixed lattice, which is the case sampling exists for. If U7 also enumerates,
# delete this and the LLM_TEMPERATURE comment together.
TOT_TEMPERATURE = 0.7  # unused by the built system; see above

# Write the complete reasoning tree to EVAL_RESULTS_DIR. Off in production runs, where
# the ledger on state is enough to disclose; on for eval runs, which need to reconstruct
# why the evaluator scored what it did. Unlike LangSmith traces, the dump does not expire.
TOT_PERSIST_FULL_TREE = False

# How many evidence tools the evaluator may pull per level. The tools are read-only and
# in-process, so the cost is latency and prompt size rather than money — but an
# evaluator that pulls everything is running a fixed battery, which is the behaviour
# selective evidence pulling exists to avoid.
TOT_MAX_EVIDENCE_CALLS = 3


# --------------------------------------------------------------------------
# MCP reference server (§7 decision #13 — mcp_server.py)
# --------------------------------------------------------------------------
# Read-only surface over tools/hud_fmr.py and tools/redfin_data.py. Consumed by the U6
# ToT evaluator's per-branch evidence pulls, and by any MCP host during U8 evaluation and
# the Week 7 demonstration. The pipeline itself does not require it — see the decision
# log for the honest accounting of what it does and does not buy.

MCP_SERVER_NAME = "deal-evaluator-reference"

# Default number of recent monthly periods returned by get_appreciation_history.
# Twelve gives a full year of trailing movement to compare against the long-run bands.
MCP_APPRECIATION_HISTORY_PERIODS = 12
