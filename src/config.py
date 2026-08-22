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

LLM_TIMEOUT_SECONDS = 90
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.0  # deterministic by default; ToT overrides


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

# Branches scoring below this are discarded. Pruning is never silent: each discarded
# branch writes {id, parent, depth, score, prune_reason} to the ledger on DealState so
# the report can disclose what was considered and why it was dropped (decision #14).
TOT_PRUNE_THRESHOLD = 0.40

# Scores within this distance are treated as tied, and resolved toward the more
# conservative growth assumption rather than by arbitrary ordering. For an investment
# tool the cost of being wrong is not symmetric.
TOT_TIE_EPSILON = 0.05

# Sampling temperature for hypothesis generation. This is the documented exception to
# LLM_TEMPERATURE = 0.0 above: diversity is bought deliberately at one seam rather than
# leaking across a pipeline that is otherwise reproducible.
TOT_TEMPERATURE = 0.7

# Write the complete reasoning tree to EVAL_RESULTS_DIR. Off in production runs, where
# the ledger on state is enough to disclose; on for eval runs, which need to reconstruct
# why the evaluator scored what it did. Unlike LangSmith traces, the dump does not expire.
TOT_PERSIST_FULL_TREE = False


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
