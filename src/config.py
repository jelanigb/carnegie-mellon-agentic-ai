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


# --------------------------------------------------------------------------
# Models (OpenRouter)
# --------------------------------------------------------------------------
#
# TODO(U3): DECISION #8 IN §7 IS STILL OPEN. These four model IDs are unverified
# placeholders — OpenRouter's free-tier catalogue changes often, so confirm each against
# https://openrouter.ai/models before the first real agent run. The program advises
# free-tier access, so any replacement should carry the `:free` suffix. Note the four
# are currently identical; the split below is structural, not yet a real selection.
#
# The split is deliberate: a cheap model for high-volume dev iteration, and stronger
# models reserved for the three roles where output quality most affects the result.

MODEL_DEV = "meta-llama/llama-3.3-70b-instruct:free"
MODEL_EXTRACTION = "meta-llama/llama-3.3-70b-instruct:free"
MODEL_CRITIC = "meta-llama/llama-3.3-70b-instruct:free"
MODEL_SUMMARIZER = "meta-llama/llama-3.3-70b-instruct:free"

LLM_TIMEOUT_SECONDS = 90
LLM_MAX_RETRIES = 3
LLM_TEMPERATURE = 0.0  # deterministic by default; ToT overrides


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
