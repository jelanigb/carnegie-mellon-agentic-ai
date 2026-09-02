"""Single source of truth for tunable parameters.

Per docs/implementation_plan.md §8, no agent may hardcode any value that appears here.
These get tuned across U4-U7, and a value buried inside an agent function is a value
that cannot be tuned without a code change.

Values marked PROVISIONAL are initial guesses awaiting empirical tuning; the unit that
tunes each one is named alongside it.

**Reconciled Aug 31, 2026 (U8.M), because that convention had quietly decayed.** Seven
constants still named U4 or U8 as their tuning owner after both units had closed — two of
them settled by decision #5 three units earlier — which reads as scheduled work and is
really unowned work. Every value that U8 measured now states *what* was measured and that
it is **held** rather than tuned; every value nothing measured says so plainly and names no
unit. The one PROVISIONAL block left is the Tree-of-Thought group, retargeted to U9 with
its condition unchanged (OQ-5). Grep `PROVISIONAL` at unit close alongside `TODO(`.
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
# **Never tuned, and no unit owns tuning it — stated Aug 31, 2026 rather than left
# naming a unit that closed.** U4 tuned the *initial* radius against measured density
# curves (1.0 -> 2.0 mi) and set this multiplier by inspection alongside it. Doubling
# reaches the 15-mile ceiling in three expansions, which is the property that was
# wanted; whether a gentler factor would return better comps before giving up has not
# been measured.
RADIUS_EXPANSION_FACTOR = 2.0
MAX_SEARCH_RADIUS_MILES = (
    15.0  # hard ceiling; beyond this a "comp" is not comparable
)

# Y: exit condition. The loop stops once this many qualifying comps are found.
# Also the number of results retrieved, which Checkpoint 3.1 asks to be stated
# explicitly as a design decision rather than left implicit.
# **Settled as decision #5's Y at U4** — the label here read PROVISIONAL until Aug 31,
# 2026, three units after the decision that closed it. U8.6b added a second measurement
# and it is a negative one: a 144-point grid across the four indexed markets returned
# exactly 8 comps at 98 points, 0 at 30, and 7 at **none**, so this line cannot be
# straddled on its own — reaching 7 requires the loop to exhaust its radius expansions
# and match relaxations first, each of which raises its own flag.
MIN_QUALIFYING_COMPS = 8

# Z: iteration cap. On exhaustion the loop exits with a sparse-comps flag rather
# than returning a silently weak result.
# **Settled as decision #5's Z at U4**; the PROVISIONAL label here was stale from U4's
# close until Aug 31, 2026.
MAX_RETRIEVAL_ITERATIONS = 4

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
# principle, a signal that never fires conveys nothing.
#
# **HELD Aug 30, 2026 (U8.6b).** The corpus's own distribution supplies both sides of
# this line without any fixture engineering: a Bed-Stuy subject returns 8 comps on **1**
# coordinate, a Hell's Kitchen subject 8 on **5**. A threshold that real geography
# straddles unaided is discriminating; 3 is kept.
COMP_MIN_DISTINCT_LOCATIONS = 3

# Decimal places for a reported comp distance. Was 3 (~1.6 m implied precision), which
# was false precision on a coordinate that is a city-area placeholder for most rows.
# One decimal (~160 m) still distinguishes a neighbouring block from the next
# neighbourhood without claiming the corpus knows where a building is.
COMP_DISTANCE_DECIMALS = 1

COMP_MATCH_BEDROOM_TOLERANCE = 0  # exact bed match before relaxation
# **Never tuned, and no unit owns tuning it (Aug 31, 2026).** Set by inspection at U4.
# It is more load-bearing than it looks: `COMP_MAX_OUTSIDE_MATCH_SHARE` measures drift
# *against this band*, so widening it would quiet the drift disclosure without changing
# a single comp — which is why the two should be re-read together if either moves.
COMP_MATCH_SQFT_TOLERANCE_PCT = 0.25

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
# 0.25 admits one outlier in a set of eight and discloses two.
#
# **HELD Aug 30, 2026 on the straddle pair U8.6b built, rather than tuned.** Chicago
# Uptown at 1,100 sq ft returns 2 of 8 outside the band (0.25, clears) and at 1,300
# sq ft returns 3 of 8 (0.38, fires) — the same building, 200 sq ft apart. Since
# U8.6e ungated the Critic's first interaction check, that difference decides the
# **verdict** and not only the disclosure, which makes this the most brittle line in
# the system and the reason the pair is published rather than only measured
# (`eval/results/results.md`, `chicago-uptown-band-under` / `-over`). Nothing in the
# batch argues for a different value; the brittleness is disclosed instead.
COMP_MAX_OUTSIDE_MATCH_SHARE = 0.25


# --------------------------------------------------------------------------
# Critic / human review
# --------------------------------------------------------------------------

# Below this confidence, the deal routes to human review instead of the Summarizer.
# **HELD Aug 30, 2026 (#6)** — not tuned. Through this point the threshold moves
# 0.30-0.70 without changing a verdict in the 21-case eval batch, and no case argues
# it is wrong; `eval/results/sensitivity.md` publishes the region and says why that is
# a robustness claim rather than an optimum.
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.60

# Bounds the Critic -> Planner rework cycle. §3 requires every cycle to be bounded by
# an explicit counter in state rather than by LangGraph's recursion_limit, so that
# exhaustion escalates gracefully instead of raising.
#
# **SWEPT Aug 31, 2026 (U8.M) and held at 2 — the budget is behaviorally inert across
# 1, 2 and 3.** `scripts/rework_budget_sweep.py` runs the replay tier at each value;
# **no verdict changes at any of them.** Only one case in the batch reworks at all
# (`chicago-geocoder-outage`), it spends exactly whatever budget it is given, and it
# escalates on `rework_limit_reached` at 1, 2 and 3 alike, at confidence 0.70 every
# time. The golden tier is inert by construction and is not swept: a rework needs a
# *retryable* objection, only I3-on-outage is retryable, and no golden case raises it.
#
# **Read that as unfalsified rather than optimal, and the limitation is specific.** The
# one case that reworks carries an outage injected for the whole run, so a later lap
# cannot reach a geocoder that is not coming back — which is precisely the condition
# under which no budget can outperform any other. **A *transient* outage, clearing on
# the second pass, is where 1 and 2 would differ, and no case simulates one.** Testing
# it needs a fault that lifts partway through a run, which the harness's `Fault`
# mechanism does not currently express.
#
# **A consequence for §6's cut list, which priced this without measuring it.** Item 5
# is "reduce the rework depth to `MAX_REWORKS = 1`". On this batch that cut costs
# **nothing measurable** — same verdicts, same confidence, same escalation ground. It
# would cost the *demonstration* rather than the behavior: at 1, the bounded cycle is
# still exercised but only once, so the case stops showing that the counter survives a
# second lap.
MAX_REWORKS = 2

# Severity weights used when aggregating flags into a confidence score.
#
# **HELD on measurement Aug 30, 2026 (#6), not tuned.** `scripts/confidence_sensitivity.py`
# swept these against the 21-case eval batch: 63 of 160 grid points decide it identically
# to the shipped values, and holding the threshold at 0.60 every warn weight from 0.100 to
# 0.200 changes no verdict. Zero cases argue the shipped numbers are wrong — which is a
# robustness result, not an optimality one, and a batch that cannot separate two settings
# is saying it has no evidence either way. **The critical weight is inert across its whole
# range including 0.00**: every deal carrying a critical escalates on the independent rule
# at `critic.escalation_decision` regardless. Before re-pricing, read that sweep and the
# note at `critic.confidence_from_flags` — the "two-warn floor" this comment used to cite
# was measured false at U7.6.
FLAG_SEVERITY_PENALTY = {
    "info": 0.0,
    "warn": 0.15,
    "critical": 0.40,
}  # HELD Aug 30, 2026 (#6) — see the note above


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
# **Still one data point, and U8 did not supply a second — stated Aug 31, 2026 rather
# than left naming a closed unit.** The eval batch reaches this threshold through a
# single case (`coord-conflict`, a demo baseline), so it has no more volume here than
# U2 did. Settling it needs listings carrying deliberately-offset coordinates at a
# range of distances, which no fixture supplies. Held at 0.5 on the reasoning above:
# the flag escalates rather than blocks, and a threshold wide enough never to fire is
# the failure mode §2 warns about.
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

# --------------------------------------------------------------------------
# Sub-metro sale-price benchmark (U8.8, OQ-7, #11)
# --------------------------------------------------------------------------
#
# The price-side counterpart to ZIP-resolution rent anchoring. Until U8.8 the market
# benchmark was one Redfin median per *metro*, so every 2-4 unit property in Chicago was
# read against the same number — §2's "location-blind below the county" limitation,
# surviving on the price side after the rent side had fixed it.
#
# Built by `scripts/build_sale_benchmarks.py` into a committed table, so the pipeline
# never makes a network call to render a benchmark. That script's docstring carries the
# source-by-source reasoning; what belongs here is the tunables.

SALE_BENCHMARK_PATH = SRC_DIR / "tools" / "data" / "zip_sale_benchmarks.json"

# How far back sales are pooled. A median needs a sample, and a ZIP does not produce one
# in a month: pooling widens the sample at the cost of mixing price levels across the
# window, which is the same trade REDFIN_ROLLING_WINDOW_PERIODS makes over three months
# with a metro's volume behind it. Set at ~3.5 years because the alternative is a table
# whose thin ZIPs are all below any usable floor.
SALE_BENCHMARK_WINDOW_START = "2023-01-01"

# Sales below this are not market transactions. $10,000 rather than a figure of this
# project's own choosing, because Cook County's assessor publishes its own screen at
# exactly that level (`sale_filter_less_than_10k`) and the New York side should not
# apply a different definition of "not a real sale" than the market it is printed
# beside. Distinct from REDFIN_MIN_MEDIAN_SALE_PRICE, which floors a *median* of many
# sales rather than one sale.
SALE_BENCHMARK_MIN_SALE_PRICE = 10_000

# Redfin's own "Multi-Family (2-4 unit)" definition, applied to the New York rows so the
# ZIP tier and the metro tier are describing the same kind of property. Cook County
# publishes no unit count — see SALE_BENCHMARK_COOK_CLASS.
SALE_BENCHMARK_MIN_UNITS = 2
SALE_BENCHMARK_MAX_UNITS = 4

# New York building-class categories kept. **Measured rather than assumed** — filtering
# on the unit count alone (2-4 residential, 0 commercial, $10k floor, since 2023) returns
# 27,504 sales, of which 20,439 are two-family, 5,536 three-family and 1,333 walk-up
# rentals. The remaining 195 are the reason this list exists: 125 labelled ONE FAMILY
# DWELLING, 47 vacant land, and a tail of garages, religious and educational facilities
# carrying a residential unit count through a data-entry artifact.
SALE_BENCHMARK_NYC_CATEGORIES = (
    "02 TWO FAMILY DWELLINGS",
    "03 THREE FAMILY DWELLINGS",
    "07 RENTALS - WALKUP APARTMENTS",
    "14 RENTALS - 4-10 UNIT",
)

# Cook County's closest class to "2-4 unit multi-family", and it is **2-6 units**, not
# 2-4: class 211 is "apartment building with two to six units". Neither Cook dataset
# carries a unit count to narrow it with, so the widening is disclosed per market rather
# than hidden — `SALE_BENCHMARK_SOURCES[...]["definition"]` travels into the report.
SALE_BENCHMARK_COOK_CLASS = "211"

# Which assessment year's parcel universe supplies the pin -> ZIP join. A parcel's ZIP
# does not move, so this only decides how many parcels exist to match against; the
# latest complete year is used rather than the newest partial one.
SALE_BENCHMARK_COOK_PARCEL_YEAR = "2025"

# How many sales a ZIP needs before its median replaces the metro figure. **Set on the
# measured distribution at U8.8, not provisional** — the reasoning is below.
#
# Measured over the window (`scripts/build_sale_benchmarks.py` re-prints it): New York
# 164 ZIPs, min 1 / p10 8 / median 131 / max 659; Chicago 140 ZIPs, min 1 / p10 4 /
# median 34 / max 851. Both distributions have a long thin tail and a dense middle, so
# the floor is picking where the tail starts rather than trading much away — at 20 it
# keeps 136 of 164 New York ZIPs and 86 of 140 Chicago ones; at 50 it would keep 117 and
# 61. Every fixture ZIP this project uses is far above it (Bed-Stuy 11216, Tottenville
# 10307, Logan Square 60647, Uptown 60640).
#
# The report always names the count behind the figure, so a reader can discount a thin
# median whatever this is set to, and a ZIP below the floor falls back to the metro
# median with the reason disclosed rather than silently.
SALE_BENCHMARK_MIN_SALES = 20

# Portals, datasets and what each market's rows actually contain. Here rather than in
# the builder because the *definition* string reaches the reader through the report, and
# a reader-facing description of what a number covers is not a script's private detail.
# Los Angeles is deliberately absent: California assessor rolls publish assessed value
# under Proposition 13, not transaction price, so this build has no local sale-price
# tier there and says so.
SALE_BENCHMARK_SOURCES: dict[str, dict] = {
    "new_york": {
        "label": "New York",
        "portal": "https://data.cityofnewyork.us",
        "sales_dataset": "w2pb-icbu",
        "attribution": "NYC Department of Finance, via NYC Open Data",
        "definition": "2-4 unit residential buildings with no commercial space",
    },
    "chicago": {
        "label": "Chicago",
        "portal": "https://datacatalog.cookcountyil.gov",
        "sales_dataset": "wvhk-k5uv",
        "parcel_dataset": "nj4t-kc8j",
        "attribution": "Cook County Assessor's Office, via Cook County Open Data",
        "definition": "2-6 unit apartment buildings (assessor class 211)",
    },
}


# ---------------------------------------------------------------------------
# The recommendation (U9.4) — axis 2, "is this a good deal?"
# ---------------------------------------------------------------------------
#
# **Set at stated percentiles of real transactions, not at round numbers.** Measured by
# `scripts/sale_premium_distribution.py` over 44,358 individual sales in 222 ZIPs — the
# same sales behind `tools/data/zip_sale_benchmarks.json`, which publishes their medians
# and no dispersion at all. Full write-up: `docs/design/recommendation.md`.
#
# Why a percentile rather than a judgment: the report can then say what the threshold
# *means*. "Priced above roughly nine in ten recorded sales in this ZIP" is a claim a
# reader can check; "priced more than 52% above the median" is a number they cannot place.
#
# ZIP tier, pooled, premium -> percentile of actual sales at or below it:
#   +15% -> 68%   +20% -> 72%   +30% -> 80%   +40% -> 85%   +50% -> 89%   +75% -> 95%
# The two markets measured separately agree closely (New York p90 +44%, Chicago p90 +66%),
# and weighting every ZIP equally instead of pooling moves nothing below +30%.
RECOMMENDATION_ZIP_CAUTION_PREMIUM = 0.30   # p80 of ZIP-tier sales
RECOMMENDATION_ZIP_REJECT_PREMIUM = 0.52    # p90 of ZIP-tier sales

# **The metro pair is extrapolated and the report says so.** A metro median describes
# properties an hour apart with one number, so its spread is roughly twice as wide and the
# two markets disagree at every percentile (p80: New York +52%, Chicago +67%; p90: +97%
# against +117%). Chicago's — the wider — are taken, because thresholds set from the
# narrower market would call ordinary Chicago sales unusual.
#
# **Los Angeles is absent from the measurement entirely**, since California publishes
# assessed value under Proposition 13 rather than transaction price — which is also why it
# has no local tier to begin with. So these two numbers rest on the assumption that LA's
# metro dispersion resembles Cook County's. That is an assumption, it is labelled as one
# here and disclosed in the report, and a California transaction-price source is what
# would close it.
RECOMMENDATION_METRO_CAUTION_PREMIUM = 0.67  # p80 of Chicago metro-tier sales
RECOMMENDATION_METRO_REJECT_PREMIUM = 1.17   # p90 of Chicago metro-tier sales

# The percentiles above, carried so the report can state them without a second table.
# Changing a threshold without changing these would make the report describe the old one.
RECOMMENDATION_CAUTION_PERCENTILE = 0.80
RECOMMENDATION_REJECT_PERCENTILE = 0.90

# The model-proposes / rule-decides cross-check (OQ-22). Off makes the Critic skip its
# model call entirely; the rule's verdict is unaffected either way, which is the property
# that makes the cross-check safe to disable in a hermetic test.
RECOMMENDATION_CROSS_CHECK_ENABLED = True

# The model-written lede above the report (U9.4). One switch for the tests, the eval
# runner and the demo surface. Off renders no summary section at all — distinct from the
# call failing, which renders a sentence saying so.
SUMMARY_NARRATIVE_ENABLED = True


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
# anchor-normalized — the bedroom step is keyed on the county — and would drop
# silently at training time.
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
# exhaustion against real data. It is why the Staten Island demo returns no comps while
# still producing a rent estimate. (Until U8.4c it also returned no market benchmark —
# that turned out to be a stale filter, not a Redfin coverage fact; see
# REDFIN_TARGET_METROS below.)
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

# Redfin `REGION NAME` per market — the sale-price series' reach (U8.4c).
#
# Lived in tools/redfin_data.py as a trio-only mapping from before New York entered the
# demo, and was never revisited — so every "Redfin doesn't cover New York" statement
# downstream was reporting this filter's output as a fact about Redfin. Checked against
# the raw extract Aug 29, 2026: "New York, NY metro area" is present with 102
# fully-populated months at 700-950 multi-family sales per month. Moved here (§8: config
# is the only home for tunables; this one predates config.py and never migrated) and
# keyed by the same market labels INDEXED_MARKETS produces, with the tie asserted below
# so the price series' reach and the system's market list cannot drift apart again.
# tools/redfin_data.load_redfin additionally asserts every region here exists in the
# extract, so a silent absence becomes a loud one.
REDFIN_TARGET_METROS: dict[str, str] = {
    "Chicago": "Chicago, IL metro area",
    "Los Angeles": "Los Angeles, CA metro area",
    "Cleveland": "Cleveland, OH metro area",
    "New York": "New York, NY metro area",
}

assert set(REDFIN_TARGET_METROS) == {
    patterns[0] for patterns in INDEXED_MARKETS.values()
}, (
    "REDFIN_TARGET_METROS and INDEXED_MARKETS name different market sets. They are two "
    "views of one scope — a market the system admits subjects from must name its Redfin "
    "region (or be removed from both), or the price side silently regrows the stale "
    "trio-only filter U8.4c removed."
)

# --------------------------------------------------------------------------
# Rent regression (U5 — tools/model/rent_model.py)
# --------------------------------------------------------------------------
# The target is rent / anchor-for-that-row's-ZIP-and-month, not rent. §2's rent-anchoring
# design in one line: a 2018-19 corpus cannot supply a 2026 dollar figure, but the
# *ratio* of a unit's rent to its local market rent is a structural property that ages far
# more slowly than the dollar level does. Training learns the ratio; prediction multiplies
# it by today's market rent for the subject's own ZIP.
#
# **The anchor was county-and-fiscal-year FMR until Aug 30, 2026 (U11.3).** It is now
# Zillow's ZORI at the row's own ZIP and own listing month, times the HUD schedule's ratio
# between unit sizes — market level, administrative shape. The design above is unchanged;
# only which reference it multiplies by moved. See `RENT_ANCHOR_*` below.

RENT_MODEL_PATH = DATA_DIR / "processed" / "rent_model.joblib"

# Features. Deliberately small and all structural — no free text, no market identifier.
# Excluding the metro is the point rather than an omission: a metro dummy would let the
# model memorize a per-market rent level, which is exactly the dollar-level dependence
# the anchor ratio exists to remove. What generalizes to an unseen market is how much a
# bedroom or a square foot moves rent *relative to the local anchor*, and that is all
# these columns carry.
RENT_MODEL_FEATURES = ("bedrooms", "bathrooms", "square_feet")

# **A note kept because it explains why the competence check moved, not because the
# coefficient still exists.** Under the LinearRegression this model shipped with until
# Aug 30, 2026, `bedrooms` came out *negative* (-0.33 per bedroom; -0.44 before ZIP
# anchoring). That was never a defect: the target is a ratio to FMR, and HUD's schedule
# climbs with bedroom count faster than real rents do — LA's FY2026 4BR FMR is 1.41x its
# 2BR while actual 4BR rents are not — so the ratio genuinely falls as bedrooms rise.
#
# It mattered operationally, though, and that is the part that changed. A high bedroom
# count on a small footprint drove the *predicted ratio* below RENT_MODEL_MIN_RATIO, and
# the Valuation agent refused the estimate. **A tree-based model cannot do that.** Its
# prediction is an average of training targets already bounded to the plausible band, so
# it clamps to the nearest leaf instead of extrapolating: measured Aug 30, 2026, a
# 2bd / 100,000 sqft subject that LinearRegression prices at a ratio of 62.21 (refused)
# is priced by gradient boosting at 2.20, and by a random forest at 3.00 — both entirely
# reportable numbers for a property neither model has any basis to speak to.
#
# So the refusal was fired by an artifact of one estimator's extrapolation rather than by
# a deliberate check, and swapping the estimator would have retired it silently. It is now
# an explicit **input-domain** check instead — see RENT_MODEL_DOMAIN_PERCENTILES below —
# which asks whether the subject resembles anything in the training data at all, and is
# the same question regardless of what form the estimator takes. Pinned by
# tests/test_flag_propagation.py::test_an_implausible_prediction_is_refused_rather_than_reported.

# The estimator. **Gradient boosting since U11.1 (Aug 30, 2026); a vanilla
# LinearRegression before that**, which is what §6 cut-list item 1a deferred and what
# `scripts/model_form_probe.py` reopened once k-fold cross-validation could replace the
# single split OQ-4 objected to. Measured on 5 folds over the 5,686-row frame:
#
#     LinearRegression   CV MAE $513.67   fold sd 13.51   R² 0.263   train/holdout gap   $0.32
#     RandomForest       CV MAE $428.83   fold sd  8.55   R² 0.454   train/holdout gap $140.41
#     GradientBoosting   CV MAE $450.71   fold sd  7.29   R² 0.427   train/holdout gap  $18.34
#
# **Random forest wins on error and was not taken.** Its $140 train-vs-holdout gap against
# the shipped model's $0.32 is the overfitting risk item 1a's deferral named, spent in one
# go; gradient boosting takes 12.2% of the error for an $18 gap and the tightest fold
# spread of the three. That is the architect's call (Aug 30, 2026), made on the balance of
# error against variance rather than on the headline figure alone.
#
# **Library defaults, deliberately.** Tuning is U11.4's, on the form this selects. Tuning
# inside the comparison would have made it a comparison of tuning effort.
RENT_MODEL_ESTIMATOR = "gradient_boosting"

# Cross-validation replaces the single 20% split, which closes the condition OQ-4 attached
# to reopening model form at all. Two consequences beyond the headline number, both worth
# having on their own: every row is scored exactly once by a model that never saw it, so
# the per-metro slices below are thick enough to read (New York is n=264 rather than a
# fifth of that); and the persisted artifact is refit on **all** the data afterwards,
# where the single-split version shipped a model fit on 80% and threw the rest away.
RENT_MODEL_CV_FOLDS = 5

# Holdout is random rather than by-metro. A by-metro split would answer a different and
# more demanding question — does the model transfer to a market it never saw — which is
# worth asking but is not the claim this build makes; §2 scopes the model to the three
# inference metros, all of which are in the training set. Recorded because the weaker
# split is a real limitation of the reported MAE and should be disclosed, not because it
# is wrong for the purpose.
#
# **Superseded twice, and both halves are now settled.** U11.4 replaced the single split
# with `RENT_MODEL_CV_FOLDS`-fold cross-validation plus a full-data refit, so this
# fraction no longer governs the shipped artifact — it survives only as the
# `train_test_split` some evidence scripts still use. And the leave-one-metro-out run this
# TODO asked for was **cut to §6 cut-list 1a on Aug 30, 2026** by the architect, with the
# transfer question left open and disclosed rather than answered (OQ-12). A k-fold holdout
# structurally cannot answer it — every fold still contains all four markets — so the
# report should say the question is open rather than let a cross-validated MAE imply it
# was settled.
RENT_MODEL_HOLDOUT_FRACTION = 0.20
RENT_MODEL_RANDOM_SEED = 42

# Below this, refuse to train rather than emit a model fit on too little data. Set
# against the measured 5,717-row training set, so it trips on a broken filter or a
# missing corpus rather than on ordinary variation.
RENT_MODEL_MIN_TRAINING_ROWS = 1_000

# Ratio bounds. A rent-to-anchor ratio outside this range is a data defect, not a luxury
# unit:
# the corpus carries rows whose square_feet or bedrooms are transcription errors, and an
# unbounded ratio lets one of them dominate a least-squares fit. Bounds are wide enough
# to keep genuine high-end and subsidized units.
RENT_MODEL_MIN_RATIO = 0.25
RENT_MODEL_MAX_RATIO = 4.0

# Input-domain check: does this subject resemble anything the model trained on? Added
# U11.1 (Aug 30, 2026) — see the note on the retired bedrooms coefficient above for why
# the output-side band above could no longer answer that on its own.
#
# **The tunable half is here; the measured half travels with the artifact**, the same
# split U8.4 settled for the per-metro error figure. These percentiles decide where the
# line sits; the *values* it lands on are properties of the training frame and are stored
# on `TrainingReport` so they cannot drift from the model that was fit on it.
#
# **Guarded on square-feet-per-bedroom rather than on each feature alone, because a
# per-feature range does not catch what actually goes wrong.** Measured on the frame:
# square_feet spans 130 to 9,175, so the `la-oversized-loft` fixture's 5,000 sqft sits
# comfortably *inside* it and a min/max guard would wave it through. What is abnormal is
# the combination — two bedrooms across 5,000 sqft is 2,500 sqft per bedroom against a
# corpus median of 574 and a p99.9 of 1,454. The same quantity catches the other end:
# the 6bd / 500 sqft refusal fixture is 83 sqft per bedroom, below the p0.1 of 150.
#
# 0.1% at each tail rather than 1%: this refuses to produce a number at all, so it should
# fire on properties that are genuinely unlike the training data rather than on the
# ordinary tails of it. `chicago-uptown-oversized` at 800 sqft/bedroom sits around the
# 84th percentile and is correctly priced rather than refused.
RENT_MODEL_DOMAIN_PERCENTILES = (0.001, 0.999)

# --------------------------------------------------------------------------
# The anchor (U11.3 — the reference the model learns a ratio to)
# --------------------------------------------------------------------------
# **Zillow ZORI for the level and the location; HUD FMR for the bedroom shape.** Taken
# Aug 30, 2026 by the architect on `scripts/anchor_probe.py`'s five-candidate comparison,
# scored in dollars on the 5,671 rows every candidate can price:
#
#     fmr    (status quo)                453.10   Chi 458  LA 451  Cle 372  NY 995
#     zori   (zip -> county)             443.78   Chi 322  LA 494  Cle 361  NY 751
#     hyb    (this one)                  439.03   Chi 337  LA 484  Cle 356  NY 812
#     fmr+   (FMR, ZORI where absent)    453.10   -- identical to fmr; nothing to cover
#     fmr/z  (FMR where ZIP, ZORI else)  484.17   -- worse than doing nothing
#
# **Why hybrid rather than pure ZORI**, which is better in two of four markets: ZORI
# publishes one smoothed series per ZIP across all unit types and has **no bedroom
# dimension at all**, so a pure-ZORI anchor asks `RENT_MODEL_FEATURES`' `bedrooms` column
# to carry a signal the anchor used to supply, and retires `FMR_BEDROOM_CAP_EXCEEDED`
# along with it. The hybrid takes ZORI's level and location — which is where the gain is —
# and keeps FMR only for the *shape* across bedroom counts, with its level divided out.
# Breadth over depth, and the numbers are better than the status quo nearly everywhere.
#
# **The measured gain is uneven and the overall figure hides it:** New York -18%
# (995 -> 812) and Chicago -26% (458 -> 337), against Los Angeles +7% *worse*. Los Angeles
# is 41% of the frame and drags the headline. Chicago is the finding that carried the
# decision — it is already 100% ZIP-anchored under FMR, so resolution cannot explain a 26%
# improvement there, and ZORI is simply a better reference series than an administrative
# schedule whatever the grain.
#
# The bedroom count whose FMR figure is the denominator of the shape. 2BR because it is
# the corpus's modal unit, so the shape is ~1.0 for the typical row and the anchor's level
# stays interpretable as "market rent for this ZIP".
RENT_ANCHOR_SHAPE_REFERENCE_BEDROOMS = 2

# How stale the market index's newest observation may be before the report says so.
# Zillow publishes on a lag, and a thin ZIP's series can end earlier than the panel's
# newest column, so this is measured per subject rather than per file. Replaces
# RENT_DRIFT_MAX_ZORI_STALENESS_MONTHS, which asked the same question of the same series
# for the correction that this anchor makes unnecessary.
RENT_ANCHOR_MAX_STALENESS_MONTHS = 6

# Below this many ZIPs behind a county median, the county tier is a county median in name
# only. Measured Aug 30, 2026 (`scripts/zori_county_tier.py`): median 8 ZIPs, p10 6,
# **min 1**. None of the counties this system infers in are near the floor, so this guards
# a path the demo set does not exercise rather than one it does.
RENT_ANCHOR_MIN_COUNTY_ZIPS = 3

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

# How much worse a market's own per-metro holdout MAE must be than the model's overall
# holdout MAE before `FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED` fires (U8.4, OQ-3).
# A ratio to the overall figure rather than a fixed dollar amount, so the line does not
# need re-tuning every time a retrain moves the headline MAE.
#
# First measured Aug 29, 2026 on the FMR anchor: overall $524.03, the trio within 1.1x,
# New York at 2.00x. **Re-measured Aug 31, 2026 under #19's hybrid anchor and the gap
# survives the anchor change**: overall $452.40; Chicago 0.76x, Cleveland 0.79x, Los
# Angeles 1.13x, New York **1.89x**. Every figure moved and the shape did not.
#
# **HELD rather than tuned, and U8.6b measured why it cannot be tuned.** No listing can
# straddle this line: it compares a *market's* error to the overall figure, and a
# subject cannot move its own market's ratio. With markets sitting at <=1.13x and
# 1.89x, any threshold between them decides identically — so the batch has no evidence
# to choose within that interval, and 1.5 is kept as its midpoint rather than as a
# tuned value. Published as a negative result in U8.6b's table.
RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD = 1.5


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
# mechanism.
#
# **Confirmed against the eval batch, twice, and the second time is the more interesting
# one.** U8.2 built `chicago-uptown-duplex` to answer this and it fired at +46.6%. After
# U11.3's anchor change that same unmodified listing measures **−6.1%**, so the case
# stopped tripping the flag and was retargeted as a control. The kind is still covered —
# `chicago-uptown-oversized` (+80.0%), `cleveland-triplex` (−36.4%) and
# `cleveland-divergence-over` (−30.8%) all raise it, and the last of those is a straddle
# fixture sited a fraction of a point past this line on purpose (U8.6b).
#
# **What that change also did, found only by re-deriving the batch:** every objection in
# `critic._interaction_objections` is gated behind this flag, so making it rarer made the
# Critic quieter — including on the one retryable objection that drives the rework cycle.
# See `tasks/task_list_u8.md` U8.6e. Whether that gate is correctly placed is an open
# design question, not a defect in this threshold.
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
# **The revisit condition this comment set has since been met, and the paragraph above is
# now history rather than current.** It said to revisit the whole check if a ZIP-level
# anchor landed. #19 landed one (ZORI at the subject's own ZIP), so the model is no
# longer blind to sub-metro rent variation and this threshold no longer fires on a
# structural blind spot. The effect is measurable on one fixture: `chicago-uptown-duplex`
# read +48% against the comps under the FMR anchor and reads **-6.1%** under the hybrid.
#
# **HELD at 0.30 Aug 30, 2026 on U8.6b's straddle pair, not tuned.** A Cleveland subject
# at 1,000 sq ft measures **-30.8%** (fires) and the same building at 1,050 sq ft
# measures **-28.9%** (clears) — same coordinate, same eight comps, none out of band. A
# 5% change in floor area flips it, which is the tightest line measured anywhere in this
# system and is published as such rather than tuned away.
# `scripts/valuation_evidence.py --diagnose-divergence` reproduces the original
# diagnosis; `scripts/straddle_probe.py` reproduces the pair.
RENT_COMP_DIVERGENCE_THRESHOLD_PCT = 0.30

# How far the listing's **stated** rents may sit from the modelled rent before the report
# calls the gap out rather than only reporting it. `None` means the comparison is always
# rendered and never editorialized, which is the shipped state.
#
# **DECIDED Aug 30, 2026 as #20: hold at `None`, and do not delete the constant.** The
# history below is kept because the reason changed twice and the second reason is the one
# that holds. It was None rather than tuned because the gap measured on the demo listings was ~-29% on all three (Aug 24, 2026:
# Los Angeles -28.8%, Chicago -29.0%, Staten Island -26.8%), and that offset was structural
# rather than a property of any listing. FMR is a 40th-percentile rent; the corpus the rent
# model learned from rented at ~1.40x FMR; #11 calibrated these listings to FMR itself. A
# threshold placed against those three numbers would have been measuring this repository's
# own fixtures, which is the error the three-question check in §8 exists to catch.
#
# **Re-measured Aug 30, 2026, because U11.3 removed the premise.** The estimate is no
# longer anchored to a 40th-percentile administrative figure — the anchor is Zillow's
# market rent index — so the structural offset that made this untunable is gone. Across
# the 13 eval fixtures carrying independently-set rents: **mean -11.4%, median -9.7%,
# range -39.4% to +66.6%.** Dispersed and sign-varying, which is what a property of the
# deal looks like rather than a property of the anchor.
#
# **So it became tunable, and a second measurement then argued against tuning it.**
# `scripts/stated_rent_gap.py` prints beside each fixture's gap the flags its report
# already raises. **Every fixture a 20-35% threshold would fire on already carries a flag
# naming a more specific cause** — comps matched outside the band, the bedroom cap, a
# market whose scored error is elevated — 6 of 6 at 25%. So the emphasis would restate an
# existing disclosure in vaguer words and attribute it to the listing's stated rent, which
# is the one thing in the comparison the system did not derive.
#
# **Hence #20: a disclosure, never a check, held on a measured reason rather than on the
# expired one.** The constant stays at `None` and is **not deleted**, because the option is
# now foreclosed by evidence rather than by arithmetic, and the evidence could change: a
# fixture set whose gaps are not already explained by a more specific flag would reopen it.
#
# The demo deals cannot settle it either way: `demo_deals.DemoDeal.rent_basis` is
# `hud_fmr:2`, so #11 set their stated rents from the old anchor and their gap measures the
# schedule-versus-market spread. That is a finding about the demo set (#11's rent side needs
# re-calibrating to the market index), not evidence about this threshold.
RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD = None

# --- ZORI comparison (U8.0, OQ-6) -----------------------------------------
# The month read as "the corpus vintage" and the bedroom counts the mix-weighted FMR
# denominator is built from. See tools/zori.py for why the denominator has to be
# mix-weighted at all: ZORI is one figure per ZIP across unit types, FMR is per bedroom.
#
# 2019-06 rather than the corpus's exact median listing date: ZORI is monthly and the
# corpus spans ~2018-09 to 2019-09, so any single month is an approximation of a window.
# Mid-window is chosen over an endpoint because the comparison is a level read, and an
# endpoint would carry whatever trend ran through the year.
ZORI_VINTAGE_MONTH = "2019-06-30"

# A ZCTA needs this many corpus rows before it gets its own printed row. Below it the
# corpus mean is a handful of listings and the bedroom mix it supplies is not a mix. This
# governs the *display* only: the aggregate is row-weighted across every covered ZCTA, so
# a thin ZCTA still contributes in proportion to its evidence instead of being discarded
# by a cutoff that exists for readability.
ZORI_MIN_CORPUS_ROWS_PER_ZCTA = 30

# How far the vintage read may be substituted when a ZCTA's ZORI series starts after
# ZORI_VINTAGE_MONTH. ZORI coverage begins when Zillow has enough listings in a ZIP, so
# thinner ZIPs start later. 12 months rather than unlimited because the comparison is a
# level read against a fixed corpus window: a 2021 substitution is being read as if it
# were 2019 and lands on the far side of the 2021-22 rent surge, which would import the
# surge into the "before" figure and understate the drift being measured.
ZORI_MAX_VINTAGE_SUBSTITUTION_MONTHS = 12

# **The rent-drift correction was removed at U11.3.** U8.4b multiplied every estimate by
# (ZORI/FMR today) / (ZORI/FMR at vintage) to remove a measured FMR-versus-market bias.
# The anchor is now that market index itself, read at each row's own listing month, so
# the bias is divided out where it arises rather than corrected afterwards.
# RENT_DRIFT_FACTOR_MIN/MAX and RENT_DRIFT_MAX_ZORI_STALENESS_MONTHS went with it; the
# staleness question survives as RENT_ANCHOR_MAX_STALENESS_MONTHS, asked of the anchor
# rather than of the correction.


# --------------------------------------------------------------------------
# Scenario / Forecast agent (U6 - agents/scenario_forecast.py)
# --------------------------------------------------------------------------
# Two quantities, two sources, still not interchangeable — but the reason changed at
# decision #21. Redfin drives price appreciation; **Zillow ZORI drives rent growth**,
# with HUD FMR history as the fallback where ZORI has no county. #16 kept them apart on
# a measured negative correlation (pooled r = -0.309); `scripts/growth_correlation.py`
# re-derived that number and found it to be a property of the *rent series* rather than
# of the market — -0.317 on FMR, -0.197 once HUD's two national step-up years are
# removed, and **+0.222 on market rent** — with r-squared never above 0.10 in any pass.
# They stay separate because they measure different things, which was always the better
# half of the argument.

# How far the scenarios project. Five years is the standard multi-family hold period,
# and it is long enough that the choice of framing is visible rather than academic: on
# Los Angeles the two defensible price treatments diverge by more than four percentage
# points a year at the optimistic band, which compounds to a materially different exit
# over this horizon. That gap is the reason this node branches instead of committing to
# one framing.
FORECAST_HORIZON_YEARS = 5

# --- The shared band estimator (tools/growth_bands.py) ---------------------
# These two were module constants in `tools/redfin_data.py` from U6, correctly: the
# price series was the only series banded, so they described one series and belonged to
# it. Decision #21 makes rent monthly as well and puts both sides through one estimator,
# at which point a value read by two modules is a tunable with two homes - which is what
# §8's "config.py is the only home for tunable parameters" rule exists to prevent. Moved
# here on that rule rather than on preference.

# Width of a "sustained stretch" when deriving optimistic/pessimistic bands, in periods.
# One year. A single extreme month is sampling noise at these volumes; a band built on
# it would be indefensible. Requiring twelve consecutive months of elevated (or
# depressed) growth means the optimistic and pessimistic cases describe conditions the
# market actually held, not its best and worst single prints.
SUSTAINED_STRETCH_PERIODS = 12

# The anomalous window §2 requires be flagged wherever it feeds an average. Near-zero
# policy rates through this stretch pushed price growth well above trend; blending it
# silently into a "base case" would describe an unusual few years as normal.
#
# ISO strings rather than timestamps so this module keeps its two-import surface -
# `tools/growth_bands.py` parses them once. Applied to *both* series under #21, where
# only the price side carried the exclusion before.
ANOMALOUS_PERIOD_START = "2020-01-01"
ANOMALOUS_PERIOD_END = "2022-12-31"

# The first month either series may contribute a *level* to, and therefore the start of
# the span both are banded over. Applied before differencing, not after, which is the
# whole point: a year-over-year observation dated 2018-06 is a comparison against
# 2017-06, so windowing the differences would silently admit a year of history one
# series has and the other does not.
#
# **Measured, and it is the price series' own start.** Redfin's extract begins
# 2018-01-01 for every configured metro, so applying this to the price side is a no-op
# today and is written anyway: it makes the shared span a property of the code rather
# than a coincidence of the file on disk. ZORI reaches back to 2015-01 and is the side
# this actually trims.
#
# The cost of not doing it was measured on ZORI before the window existed: New York's
# pessimistic rent band was -22.6%/yr, a real Bronx figure from a twelve-month stretch
# ending 2017-05 — three years before the price series has anything to say. A window one
# year later still leaves the class: Chicago's pessimistic band moves 1.45pp depending on
# whether a stretch ending 2018-12 is admitted, and nothing on the price side covers it.
FORECAST_SERIES_WINDOW_START = "2018-01-01"

# --- ZORI rent-growth series (tools/rent_growth.py) — decision #21 ---------
# The forecast's rent bands come from Zillow's Observed Rent Index at the subject's
# county, not from HUD's Fair Market Rent schedule. #16 chose FMR on an architectural
# argument — "the rent estimate is `ratio x FMR`, so projecting the anchor forward
# forecasts rent by the same mechanism that produced the estimate" — and that argument
# now selects ZORI, because since #19 the estimate is `ratio x ZORI(ZIP) x FMR-bedroom
# -step`. Following #16's own reasoning to where the system moved, rather than
# overturning it. The four defects this closes are in `docs/design/evaluator.md`.

# The county tier, not the ZIP tier, and the reason is coverage rather than preference:
#   - ZIP 10307 has no ZORI series at all, and it is the `staten-island` demo deal's own
#     ZIP. That deal has no Redfin metro, so rent is the only side it gets — a ZIP-first
#     design would turn a one-sided forecast into no forecast.
#   - 65-95% of the ZIPs inside this project's own market counties start after 2018-01
#     (median start 2021-2024), so a ZIP-first design falls back to county for most
#     subjects anyway and varies the *history length* by ZIP.
#   - Where both exist the answer barely moves: LA 90026 gives +0.68/+2.37/+3.86 against
#     the county's +1.25/+2.51/+4.76.
# The consequence is disclosed rather than hidden: the estimate is anchored at the ZIP
# and its growth is measured at the county, and RENT_GROWTH_SOURCE says so.
ZORI_GROWTH_RESOLUTION = "county"

# How many distinct twelve-month stretches the outer rent bands must be chosen from
# before ZORI is used at all. Below it the county falls through to the FMR schedule.
#
# **Measured, and the first rule tried was not enough.** The obvious threshold is the
# estimator's own requirement — at least one contiguous twelve-month run, or "the worst
# sustained stretch" silently becomes "the worst single month". That is a genuine cliff
# (62% of ZORI's 1,211 counties clear it, 38% do not, and a count-based test agrees to
# within four counties) and it is necessary. It is not sufficient: Adams County IL clears
# it on 14 months of history and publishes a five-year projection banded
# +9.18/+9.86/+10.51.
#
# The failure is not that a thin series looks unreliable. It is that it looks
# **confident**: min and max over three overlapping views of the same year are nearly the
# same number. Median band width across the covered counties, by how many distinct
# stretches the extremes were chosen from —
#
#     1-3 stretches    13 counties    0.13pp     <- reads as near-certainty
#     4-11 stretches   84 counties    1.85pp
#     12-23 stretches 117 counties    4.46pp
#     24-43 stretches 531 counties    6.15pp
#
# So the requirement is a full year's worth of *distinct* stretches, which is the same
# twelve the window itself is built from rather than a second number to defend. It needs
# ~23 contiguous months and drops 97 of the 745 counties that pass the weaker rule.
# **Not a cliff** — the underlying distribution is smooth through this region, unlike the
# one-run test — so this is a judgment, recorded as one.
ZORI_GROWTH_MIN_SUSTAINED_STRETCHES = SUSTAINED_STRETCH_PERIODS

# The reader-facing name of the series. Mirrors redfin_data.SERIES_DESCRIPTION.
ZORI_GROWTH_SERIES_DESCRIPTION = (
    "Zillow Observed Rent Index, county-level monthly median across all unit types"
)

# --- FMR rent-growth series (tools/fmr_history.py) — the fallback ----------
# Kept, not retired: measured across ZORI's county table, only 1,211 counties are
# covered at all and 62% of those can form a sustained stretch, so outside indexed
# markets the FMR schedule is the common path rather than an edge case. It reaches any
# county through the HUD API this project already caches.
#
# HUD publishes FY2017 onward, giving nine year-over-year observations. **The estimator
# asymmetry survives here and only here**: nine annual points cannot carry a twelve-month
# sustained window, so the fallback keeps single-fiscal-year extremes (FMR_BAND_* below)
# while the primary path uses the shared monthly estimator. That is the asymmetry #21
# closes on the path every demo deal takes, and discloses on the path none of them do.
FMR_HISTORY_FIRST_YEAR = 2017

# The fiscal years the fallback holds out when the forecast's depth-1 search asks for the
# 2020-2022 window excluded. The same question the price side is asked, put to an annual
# series: FMR fiscal years are named for the year they begin, so these are the schedule's
# own labels for the window ANOMALOUS_PERIOD_START/END bound on a monthly series.
FMR_ANOMALOUS_FISCAL_YEARS = (2020, 2021, 2022)

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
# **No longer a forecast branch, and still load-bearing (decision #21).** The screen was
# built to hold HUD's national step-ups out of the rent bands; the rent bands no longer
# come from HUD on any path a demo deal takes, so the depth-1 rent fork is now the same
# 2020-2022 question the price side is asked and this screen does not enter it.
#
# It is kept because it is the *evidence that retired itself*. Removing FY2023-24 — the
# two years this screen identifies — is what collapsed the rent/price correlation from
# -0.317 to -0.197 in pass 2 of `scripts/growth_correlation.py`, and that pass is a third
# of the argument for #21. Deleting the machinery would delete the reproduction of the
# finding that justified deleting it.
#
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
LLM_TEMPERATURE = 0.0  # deterministic everywhere


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
#
# **Env-overridable as of U9.5, for the same reason `LLM_CACHE_MODE` above is.** The eval
# runner selects the store by assigning this constant, which serves the batch and nothing
# else — but `main.py` renders a *report*, and the batch does not: an escalating case
# pauses at `human_review` and the runner never resumes it, so no run of the harness ever
# reaches the Summarizer on those rows. The demo deals therefore need recording through
# `main.py`'s full path, resume and written summary included, and that needs a way to
# point at the committed store without editing this file. `LLM_CACHE_MODE=replay
# LLM_CACHE_DIR=src/eval/data/llm_recordings .venv/bin/python main.py --deal <key>` is a
# reproducible demo run, which is what U9.7's replay-by-default surface rests on.
LLM_CACHE_DIR = Path(os.environ["LLM_CACHE_DIR"]) if os.environ.get("LLM_CACHE_DIR") \
    else DATA_DIR / "processed" / "llm_cache"
EVAL_DATA_DIR = SRC_DIR / "eval" / "data"
EVAL_RESULTS_DIR = SRC_DIR / "eval" / "results"
EVAL_RECORDINGS_DIR = EVAL_DATA_DIR / "llm_recordings"

# Census Geocoder address→coordinate store (U8.6e, Aug 30, 2026).
#
# **Committed, unlike the LLM development cache above, and for the same reason
# `EVAL_RECORDINGS_DIR` is committed.** A replayed eval case's forecast prompt embeds the
# flag set, and the flag set depends on whether the Census answered — so a live geocode
# upstream of a recorded model call makes the recording unreproducible on a fresh clone or
# a flaky network. `tools/geocoding.py`'s docstring carries the measurement. Only outcomes
# the Census actually returned are stored; a timeout never is.
GEOCODE_CACHE_PATH = EVAL_DATA_DIR / "geocode_cache.json"


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

# Third-party library logging — off by default, and "off" here means *restoring* the
# root logger rather than silencing anything. Nothing in this project logs; the ~190
# lines that print before every report arrive because decision #13's MCP reference
# server reconfigures logging for the whole process when it is constructed. See
# `tools/logging_setup.py` for the measurement and why the fix is shaped that way.
#
# `LIBRARY_LOGS=true` gets the chatter back for debugging a retrieval or an HTTP
# failure. The env var is read once at import; the attribute is read each time the
# context manager runs, so a caller can also flip it in-process the way `main.py`
# flips `RETRIEVAL_ENABLED` for the ablation.
LIBRARY_LOGS_ENABLED = os.environ.get("LIBRARY_LOGS", "").lower() == "true"


# --------------------------------------------------------------------------
# Tree-of-Thought reasoning (§7 decisions #12, #14 — U6)
# --------------------------------------------------------------------------
# Applied inside one node: Scenario/Forecast (U6). The rest of the pipeline is ordered
# by data dependency, so there is nothing there to search over.
#
# Decision #12 originally reserved a second consumer, the Critic's cross-agent
# consistency checks (U7). **Retired on evidence, U7.7:** the checks that shipped in
# U7.2/U7.3 (`agents/critic.py:_interaction_objections`, the comp-drift check in
# `agents/comps_retrieval.py`) are pure functions over `state.flags` — no LLM call, no
# generated candidates, nothing to search over. See `history/decision_log.md` #12.
#
# Every value below is PROVISIONAL. **Retargeted U8 -> U9 on Aug 30, 2026 (OQ-5): U8
# planned no subsection for these and built none**, so naming U8 here overstated what was
# scheduled. The condition is unchanged and unmet — tuning needs cases whose correct
# branch is known by construction, and none exist.
#
# **Two measurements did land and are what is known about any of these.**
# `TOT_TIE_EPSILON` is not meaningfully straddleable: the gap it compares is
# noise-dominated (OQ-17), so a recorded straddle would measure the recording (U8.6b).
# And U8.6c published the depth-2 **cut margin** — the line the beam width actually cuts
# on — which across the golden batch is often zero or negative, meaning the discarded
# pairing outscored the reported one and lost on `tot._rank`'s conservatism preference.
# Tuning against the golden batch was considered and declined: those fixtures were
# authored by the unit that would have tuned against them.
#
# They are named here rather than inside the agent because a tunable hardcoded in an
# agent is a defect (§8).

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
