# Multi-Family Residential Deal Evaluator — Implementation Plan
**Handoff doc for Claude Code**
Author: Jelani Gould-Bailey · Last updated: Aug 4, 2026

---

## 1. Project Summary

This is a capstone project for a CMU Agentic AI executive education program. The system
is a **seven-agent pipeline** that evaluates small multi-family (2–4 unit) residential
properties as investment candidates:

1. **Planner** — inspects the deal, decides which downstream steps are needed, routes
   between agents, governs retries/escalation.
2. **Extractor** — parses an unstructured listing into structured deal terms; generates
   clarifying questions on missing fields; flags assumptions when no answer is available.
3. **Comps/Retrieval** — RAG-based comp finder over a rental listings corpus; adaptively
   relaxes search criteria (radius, match strictness) if matches are sparse, and flags
   when it does.
4. **Valuation & Rent** — rent regression model + comps-based value estimate.
5. **Scenario/Forecast** — Tree-of-Thought reasoning over rent-growth/appreciation
   scenarios (optimistic/base/pessimistic), informed by metro-level housing trend data.
6. **Critic/Reviewer** — checks consistency across upstream outputs, aggregates all flags
   into an overall confidence score, can route low-confidence deals to a
   "needs human review" state.
7. **Summarizer** — produces the final investor-facing report; required to surface all
   upstream flags prominently, not just bottom-line numbers.

**Unifying design principle — "Transparent Degradation":** whenever an agent proceeds on
incomplete or relaxed information (a widened comp radius, an unresolved clarifying
question, a low-confidence estimate), it attaches a named flag to its output. Flags
propagate downstream through the Critic to the Summarizer, so the final report always
discloses *when and how* the system deviated from the ideal path rather than silently
absorbing the gap. This principle should be visible in code, not just in the report —
every agent function should be able to append to a shared `flags` list in state, and nothing
should quietly overwrite or drop a flag on its way downstream.

**Data sources (finalized):**
- **Kaggle apartment rental dataset** — unit-level features (beds/baths, sqft, location,
  amenities, rent) for comps retrieval and rent-structure regression training.
  Candidate: https://www.kaggle.com/datasets/shashanks1202/apartment-rent-data
  (verify column fit against the comps schema below; confirm/parse the `time` column,
  likely a Unix timestamp — dataset is known to be ~2017–2019 vintage).
- **HUD Fair Market Rents (FMR)** — free, public, county-level, annual, rent-specific
  time series. Used to anchor the Kaggle-derived rent structure to current dollars.
  API: https://www.huduser.gov/portal/dataset/fmr-api.html (free account + bearer token
  required — set this up before Week 4).
- **Redfin Data Center — Housing Market Tracker, filtered to `property_type =
  Multi-Family (2-4 Unit)`** — free, public, time series (median sale price, days on
  market, inventory) available down to neighborhood/ZIP/city/county/state, filterable
  by property type. This is the sole appreciation source (see §2 — Redfin Home Price
  Index does not cover multi-family and is not used). https://www.redfin.com/news/data-center/downloads/

---

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

Two problems surfaced while planning the data layer, and both are resolved the same way:
ground every dollar figure in a *dated, purpose-matched* source rather than trusting a
single dataset to do more than it can.

### Problem 1 — the Kaggle rent data has no reliable current date
The Kaggle apartment dataset is a single historical scrape (~2017–2019). Any rent
estimate trained directly on it is calibrated to that era's price level, not today's.
Left uncorrected, a "$1,450/month" prediction is a 2018 number in a 2026 costume, and
every downstream valuation and scenario built on it inherits that bias.

### Problem 2 — Redfin measures price, not rent
Redfin's data (Housing Market Tracker, RHPI) tracks home *sale* prices. Home price
appreciation and rent growth diverge meaningfully over multi-year windows — most
visibly 2020–2022, when price growth far outpaced rent growth as low rates pulled
buyers in. Using Redfin's price trend to adjust a *rent* number would import
interest-rate-driven price dynamics into a quantity they don't actually explain.

### Resolution: separate "structure" from "level," and match each quantity to a same-kind source

**Rent-level anchoring (Valuation & Rent agent):**
1. Train the regression on rent *normalized by that row's local HUD FMR at the time it
   was recorded* (rent ÷ FMR-for-that-county-and-year), not raw dollars. The model
   learns a structural relationship — "this bed/bath/sqft/amenity combination rents at
   ~1.15× the local FMR" — that ages far more slowly than a dollar figure.
2. At prediction time, multiply the model's output ratio by *today's* HUD FMR for the
   subject property's county. This produces a current-dollar estimate anchored to a
   real, dated reference point instead of an implicit 2018 price level.
3. Flag every estimate that used this anchoring path (`kind="rent_anchored_to_fmr"`,
   `severity="info"`) so the report can disclose the mechanism, and flag separately
   (`kind="fmr_unavailable_for_county"`, `severity="warn"`) if HUD has no FMR entry for
   the subject county and a coarser (state/national) fallback had to be used.

**Appreciation forecasting (Scenario/Forecast agent):**
- Use the Housing Market Tracker filtered to `property_type = Multi-Family (2-4 Unit)`
  as the appreciation/trend series — this matches the asset class directly rather than
  relying on a blended series dominated by single-family transaction volume. Small
  multi-family is bought by a different buyer pool (investors pricing off cap rates)
  than single-family (owner-occupants), so an asset-matched trend line is a real
  accuracy improvement, not just a nice-to-have.
- Redfin Home Price Index (RHPI) is **not used** — it covers single-family homes only
  and has no multi-family series, so it can't substitute or supplement here.
- **Geographic level: metro is the primary tier, not ZIP.** Redfin's `REGION TYPE`
  offers ZIP, metro, and other levels directly (no manual ZIP→county rollup needed).
  For the target inference metros (New York, Chicago, Philadelphia — all large CBSAs),
  metro-level `HOMES SOLD` counts are in the dozens to low hundreds per period, versus
  ZIP-level counts that are frequently single digits with wild YoY swings from small
  denominators. Metro-level is directionally what the Scenario/Forecast agent needs
  (bands for optimistic/base/pessimistic), not sub-market precision, so the added
  stability outweighs the lost granularity. Revised three-tier design, with the tier
  used flagged (`kind="appreciation_source"`, `severity="info"` for tiers 1–2,
  `"warn"` for tier 3):
  1. **Metro-level, multi-family filtered (default — build this now).** Adequate
     sample for any of the target metros; this is the only tier required for the
     pipeline to work end-to-end.
  2. **ZIP-level, multi-family filtered (deferred / stretch goal).** Would apply only
     when the subject ZIP clears a minimum-sample gate (e.g. `HOMES SOLD` ≥ ~8–10 for
     the period). Not built in the current phase — the ZIP extract already pulled
     shows single-digit sample counts and YoY swings in the thousands of percent even
     within a large metro (NY), so this tier would clear its own usability gate rarely
     enough that it isn't worth building alongside the core pipeline. Documented as
     future work, the same way cross-deal episodic memory was deferred in Checkpoint
     2.1 — real, but not blocking.
  3. **Metro-level, all-residential, unfiltered (fallback).** For the rare case where
     even metro-level multi-family volume is too thin — unlikely for the target metros
     but kept for robustness against edge cases or future metro additions.
- **Use a consistent period frequency — `Rolling 3 Months`, not `Monthly`.** Redfin
  offers both; rolling 3-month windows smooth out the single-month sample-size noise
  seen even at metro level for smaller markets, and consistency matters more than
  granularity here since the pipeline compares periods to each other.
- **Apply a minimum-price floor before any sample-size logic runs.** Raw extracts
  contain implausible `MEDIAN SALE PRICE NSA` values ($1, $100, $975) — near-certainly
  non-arm's-length transfers (quitclaim deeds, corrective deeds, nominal-consideration
  transfers) rather than real market sales. Drop any period below a floor (start around
  $10,000–$20,000 and adjust after inspecting the target metros' actual distributions)
  before it can corrupt a median or a YoY calculation.
- **Pull roughly 2018–present**, not just the last year or two. This window is sized
  for the Scenario/Forecast agent's own needs — real historical variance to ground its
  optimistic/base/pessimistic branches (e.g. base = long-run average growth, optimistic
  = best sustained stretch observed, pessimistic = worst) — and is **independent of
  Kaggle's ~2017–2019 vintage**; the two datasets don't need matching date ranges,
  since HUD FMR is what bridges Kaggle's vintage to today (see rent-level anchoring
  above), not Redfin's date range. 2018–present just needs to capture a pre-COVID
  baseline alongside the anomalous period, rather than only the anomaly; reaching back
  to Kaggle's exact start year isn't required.
- **Flag the 2020–2022 window explicitly wherever it feeds an average or scenario
  band** (`kind="anomalous_period_included"`, `severity="info"`). Near-zero interest
  rates pulled price growth well above trend during this stretch; blending it in
  silently risks skewing "base case" toward an unusual few years rather than normal
  market behavior. Flagging it keeps the choice visible and defensible either way.
- Redfin data is never used to adjust rent dollars — only price/appreciation.
- Filter to the target metros immediately on load — Redfin data is only used for
  per-deal inference lookups (never for training), so it only ever needs to cover the
  2–3 inference metros, not a national pull.

**Out of scope for now:** Investor Home Purchases and Existing Home Sales datasets —
no clear role in the current agent design; documented as potential future enrichment
(e.g., a market-competitiveness signal) rather than built now.

### Metro Scope: Training vs. Inference

Two different scopes are needed, and they shouldn't be the same size:

- **Inference/demo scope: 2–3 metros.** Kept small deliberately — enough to show the
  system working on genuinely different markets without turning metro selection into
  its own research project. This is the set actual pipeline runs and checkpoint demos
  will use.
- **Training scope: broader than the inference set, but not the full nationwide
  Kaggle dataset.** The regression predicts a *ratio to local FMR*, not a raw dollar
  figure, so it benefits from more diverse training data — restricting training to only
  2–3 metros risks overfitting to those markets' specific feature/price relationships.
  At the same time, because the Kaggle dataset is a single-vintage scrape, the HUD FMR
  pull needed to normalize the training target is bounded by *the number of distinct
  counties represented*, not by the number of training rows — so widening the training
  set doesn't meaningfully raise the FMR API cost. The practical constraint is data
  cleaning and county/FIPS mapping effort, not FMR access. A curated shortlist of
  roughly 5–8 metros (rather than the full dataset) keeps that cleanup bounded while
  still giving the regression meaningfully more diversity than 2–3 metros alone. The
  2–3 inference metros should be a subset of this training shortlist, so they're
  guaranteed adequate comp density and a validated data pipeline.
- **Before finalizing metro choices:** run a quick `groupby` count on the Kaggle
  dataset by city/metro to confirm actual listing density — the candidates below are
  based on known housing-stock patterns, not on this dataset's specific coverage, and
  need to be checked against it directly (Week 3 task).

**Candidate metros (why they fit):** small multi-family (2–4 unit) stock is
concentrated in the Northeast and older Midwest/Rust Belt cities, plus parts of
California — New York's outer-borough brownstones/rowhouses, Chicago's two-/three-flats,
and Philadelphia's duplexed rowhomes are the classic examples, alongside Providence,
Newark/Jersey City, Cleveland, Milwaukee, Buffalo, Detroit, and parts of Los Angeles.
**New York, Chicago, and Philadelphia** are the working trio: each has a dense,
well-documented 2-4 unit housing stock (giving Redfin's property-type filter and HUD
FMR real signal to work with), is a large enough metro to likely have solid Kaggle
listing volume, and matches the target user persona (an individual investor evaluating
small multi-family deals) better than a market where 2-4 unit product is rare. New York
is the largest of the candidates and its multifamily housing stock is especially
concentrated in the outer boroughs, which also helps the training-shortlist goal.
Treat this as a starting hypothesis to confirm against the Kaggle groupby check above,
not a final answer.

**Why New York over Boston specifically:** HUD defines FMR areas by *town* rather than
county in the six New England states (CT, ME, MA, NH, RI, VT) — Boston would have hit
that exception. New York, Chicago, and Philadelphia are all standard county-based FMR
states, so `tools/hud_fmr.py` can assume county-keyed lookups throughout without a
regional branch. One caveat that applies regardless of which three metros are chosen:
large, high-cost metros are often **Small Area FMR (SAFMR)** areas, where HUD publishes
ZIP-level figures instead of one metro-wide number — New York is a likely SAFMR metro,
but so could Chicago or Philadelphia be. That response-shape handling (see §HUD FMR API
notes below) is a general build requirement, not something specific to the New York
swap.

**Verified Aug 8, 2026 against the live API (see §9):** this hypothesis was backwards.
**New York County returns the flat (non-SAFMR) shape**; **Cook County (Chicago) and
Philadelphia County are both SAFMR** (ZIP-keyed `basicdata` list). Doesn't change the
build requirement — the client still has to handle both shapes for the trio either
way — but corrects the assumption above for anyone reading this section later.

### HUD FMR API: Implementation Notes

Concrete details for `tools/hud_fmr.py`, from the API docs
(https://www.huduser.gov/portal/dataset/fmr-api.html):

- **`year` is a single fiscal year per call, and must be pulled per (county, year)
  pair, not once overall.** Two distinct kinds of pulls are needed: (1) the Kaggle
  vintage year(s) for training normalization — if Kaggle rows span more than one year,
  that's multiple distinct `year` values, not one blanket value; (2) a current anchor
  year for inference. Don't hardcode the current year — call once *without* the `year`
  parameter (defaults to latest available) and read the `year` field back from the
  response, so the code doesn't go stale if this is still running months from now.
- **`entityid` for a county is the 10-digit FIPS-style code** (e.g. `5100199999`),
  obtained via `fmr/listCounties/{state}` — this is exactly what `DealTerms.county_fips`
  is meant to hold, so no reformatting should be needed between the Extractor's output
  and the FMR lookup.
- **Handle the Small Area FMR (SAFMR) response shape.** For metros where HUD publishes
  ZIP-level FMRs, `basicdata` comes back as a *list* keyed by `zip_code` (plus one entry
  literally named `"MSA level"` for the metro-wide aggregate) instead of a single flat
  object. This is likely for at least one of New York, Chicago, or Philadelphia — check
  early with a real call rather than assuming the flat-dict shape everywhere. Code
  should: look for an entry matching the subject property's ZIP; fall back to the
  `"MSA level"` entry if no ZIP-specific match exists.
- **Bedroom sizes cap at Four-Bedroom.** No API field exists beyond 4BR. If the
  Extractor ever produces a 5+ bedroom unit, fall back to the 4BR figure and flag it
  (`kind="fmr_bedroom_cap_exceeded"`, `severity="info"`) rather than erroring.
- **Auth and rate limit**, as already planned: bearer token in the `Authorization`
  header, 60 requests/minute — reinforces why local caching (fips + year → result) in
  `tools/hud_fmr.py` matters, since a training set spanning many counties means many
  distinct calls during development.

---

## 3. Stack Decision: Option A now, Option B (LangGraph) later

### What we're building with (Option A — "Minimal & Explicit")

| Layer | Choice | Why |
|---|---|---|
| Orchestration | Plain Python — dataclass/TypedDict state, one function per agent, explicit loop in Planner | See rationale below |
| LLM calls | OpenRouter (mix of free/cheap models for dev, stronger models for extraction/critic/summarizer) | Keeps token spend near $0 during iteration |
| Retrieval / RAG | `sentence-transformers` (local embeddings) + `ChromaDB` (local vector store) | Free, local, no infra to manage, fine on 24GB RAM |
| Regression | `pandas` + `numpy` + `scikit-learn` | Already comfortable with this |
| State persistence | SQLite or per-run JSON | Single-deal state doesn't need more |
| Dev environment | VS Code + Claude Code | — |

### Rationale for starting with plain Python instead of LangGraph

1. **The course hasn't covered LangGraph yet**, and the checkpoint 2.1 document already
   frames orchestration in library-agnostic terms — "state machine pattern," not a named
   library. Plain Python *is* that state machine, just without the abstraction layer. This
   means nothing conceptual has to be redone when the framework is introduced — only the
   glue code changes.
2. **The early checkpoints don't need what LangGraph is good at.** Checkpoints 2–4
   (reasoning loops, RAG, Tree-of-Thought) are single-agent-scoped: one agent, one loop,
   one exit condition. A `while` loop with a `retry_count` and a `flags.append(...)` does
   this with less code and less to debug than a graph library, while making every state
   transition maximally visible for the checkpoint write-ups (screenshots of code = the
   graph, essentially).
3. **LangGraph earns its complexity starting at checkpoint 5** (Multi-Agent Architecture
   and Coordination): conditional routing between 7 agents, a Critic → Planner rework
   loop, bounded re-runs before escalation. That's exactly the shape LangGraph's
   conditional edges and shared state graph are built for. Introducing it *here*, once the
   course has covered it and once there's a concrete coordination problem to solve, means
   the framework is doing real work instead of being learned in the abstract.
4. **Risk management for a 7-week timeline.** Learning agent design and a new
   orchestration framework in the same week is the likeliest way to lose a week to
   framework debugging instead of pipeline progress. Sequencing framework adoption after
   the underlying agent logic already works removes that risk from the critical early
   weeks.

### Migration plan to Option B (LangGraph)

**Target: Week 6, aligned with Checkpoint 5.1 (Multi-Agent Architecture and Coordination
Plan).**

To make that migration cheap, Option A code should follow these conventions from day one:

- Every agent is a **pure-ish function of the shared state**: `def extractor_agent(state: DealState) -> DealState`. This is exactly LangGraph's node signature — porting a node is close to a copy-paste plus a decorator/registration call.
- **No agent calls another agent directly.** All routing decisions happen in the Planner
  (or a dedicated `route()` function), never inside a specialist agent. This mirrors
  LangGraph's separation of nodes from edges and means the routing logic — not just the
  agent logic — transfers cleanly.
- **State is a single typed object** (see schema below) passed by reference through every
  step, never scattered across separate variables. This is a direct stand-in for
  LangGraph's shared graph state.
- **Flags and retries are state-encoded, not control-flow-encoded** (i.e., a flag is a
  list entry in state, not a side effect like a print statement or a raised exception used
  for control flow). LangGraph conditional edges read state to decide routing, so anything
  encoded outside state won't be visible to the graph.

When Week 6 arrives, the migration should mostly consist of: wrapping each existing agent
function as a LangGraph node, replacing the Planner's manual `if/elif` routing with
conditional edges, and replacing the manual retry loop with LangGraph's cycle support. The
underlying agent logic (prompts, parsing, regression calls, retrieval calls) should not
need to change.

---

## 4. Proposed Repository Structure

**Note (Aug 8, 2026):** the repo already exists with `data/`, `docs/`, and `ignore/`
(secrets, gitignored) at the top level, so `src/` — not a new `deal-evaluator/`
wrapper — is the project root for all application code below. Paths in the rest of
this doc that reference `tools/`, `agents/`, `config.py`, etc. are relative to `src/`.

```
carnegie_mellon_agentic_repo/
├── data/                          # gitignored — Kaggle CSV, Redfin CSVs, cached HUD FMR responses
│   ├── raw/
│   └── processed/
├── docs/
│   └── private/                   # gitignored — capstone docs, this implementation plan
├── ignore/                        # gitignored — secrets (HUD FMR bearer token, etc.)
└── src/                           # project root for all application code
    ├── README.md
    ├── requirements.txt
    ├── .venv/                     # gitignored — dedicated virtualenv
    ├── config.py                  # X/Y/Z loop parameters, model names, thresholds
    ├── state.py                   # DealState schema (see §5)
    ├── agents/
    │   ├── __init__.py
    │   ├── planner.py
    │   ├── extractor.py
    │   ├── comps_retrieval.py
    │   ├── valuation_rent.py
    │   ├── scenario_forecast.py
    │   ├── critic.py
    │   └── summarizer.py
    ├── tools/
    │   ├── __init__.py
    │   ├── llm_client.py          # thin OpenRouter wrapper, model selection
    │   ├── vector_store.py        # Chroma setup + embedding + query helpers
    │   ├── rent_model.py          # sklearn regression: train/load/predict (FMR-normalized target)
    │   ├── hud_fmr.py             # HUD FMR API client: fetch by county + fiscal year, cache locally
    │   └── redfin_data.py         # load + query Housing Market Tracker CSVs + RHPI
    ├── scripts/
    │   └── pull_fmr_sample.py     # smoke-test script: real HUD pull for a few counties/years
    ├── notebooks/
    │   └── 01_data_exploration.ipynb # EDA on all three sources before committing to schema
    ├── tests/
    │   ├── test_extractor.py
    │   ├── test_comps_retrieval.py
    │   └── fixtures/
    │       └── sample_listings/   # synthetic test listings (per program data rules)
    └── main.py                    # entrypoint: run full pipeline on one listing
```

---

## 5. State Schema (design target for `state.py`)

```python
from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime

@dataclass
class Flag:
    source_agent: str          # e.g. "comps_retrieval", "valuation_rent"
    kind: str                  # e.g. "relaxed_search_radius", "unresolved_field",
                                # "low_confidence_estimate", "fallback_used",
                                # "rent_anchored_to_fmr", "fmr_unavailable_for_county",
                                # "appreciation_source"
    detail: str                # human-readable explanation
    severity: Literal["info", "warn", "critical"]

@dataclass
class DealTerms:
    address: Optional[str] = None
    price: Optional[float] = None
    unit_count: Optional[int] = None
    unit_rents: list[float] = field(default_factory=list)
    square_footage: Optional[float] = None
    county_fips: Optional[str] = None    # needed to key HUD FMR + Redfin lookups
    # ... additional fields as extraction schema is finalized

@dataclass
class Comp:
    listing_id: str
    similarity_score: float
    rent: float
    beds: int
    baths: float
    square_feet: float
    distance_miles: float

@dataclass
class DealState:
    # inputs
    raw_listing_text: str

    # extraction
    deal_terms: DealTerms = field(default_factory=DealTerms)
    clarifying_questions: list[str] = field(default_factory=list)

    # retrieval
    comps: list[Comp] = field(default_factory=list)
    search_radius_miles: float = 1.0   # X, widened on relaxation
    retrieval_iterations: int = 0

    # valuation
    rent_estimate: Optional[float] = None
    rent_estimate_ratio_to_fmr: Optional[float] = None  # model's raw structural output
    fmr_anchor_used: Optional[float] = None              # today's FMR figure applied
    value_estimate: Optional[float] = None
    rent_estimate_source: Literal["regression_model", "llm_fallback", None] = None

    # forecast
    # "zip_multifamily" is a documented future option (deferred — see §2); not
    # produced by the current build.
    appreciation_source: Literal[
        "metro_multifamily", "zip_multifamily", "metro_all_residential", None
    ] = None
    scenarios: dict = field(default_factory=dict)  # optimistic/base/pessimistic branches

    # review
    confidence_score: Optional[float] = None
    needs_human_review: bool = False

    # cross-cutting
    flags: list[Flag] = field(default_factory=list)
    status: Literal["in_progress", "needs_review", "complete", "failed"] = "in_progress"
    created_at: datetime = field(default_factory=datetime.now)
```

This is a starting point — Claude Code should refine field names once the Extractor's
actual output schema and each data source's actual columns are confirmed (see Week 3
tasks below).

---

## 6. Phased Plan (mapped to remaining checkpoints)

| Week | Checkpoint | Build target |
|---|---|---|
| **3 (now)** | — (catch-up week) | Repo scaffold, `DealState` schema, EDA on all three data sources, HUD FMR API access set up, Extractor agent + clarification loop working end-to-end on a synthetic listing |
| 4 | 3.1 RAG and Retrieval Design | Comps/Retrieval agent: embeddings + Chroma index over Kaggle data, adaptive relaxation loop, sparse-comps flag; rent regression trained on FMR-normalized target |
| 5 | 4.1 Tree-of-Thought Integration | Valuation & Rent agent (FMR-anchored regression + fallback), Scenario/Forecast agent with 2–3 branch ToT reasoning over Housing Market Tracker / RHPI data |
| 6 | 5.1 Multi-Agent Architecture | **Migrate orchestration from plain Python to LangGraph.** Planner becomes a graph with conditional edges; Critic → Planner rework loop implemented as a cycle |
| 7 | 6.1 Safety Guardrails | Critic/Reviewer confidence scoring, human-review escalation, logging, eval harness against success criteria from Checkpoint 1.1 |
| Final | 7.1 Report + Presentation | Summarizer polish, end-to-end runs on several sample properties, report + video |

---

## 7. Week 3 Task List (what to hand Claude Code first)

1. Scaffold the repo structure above; set up `venv`, `requirements.txt`
   (`pandas`, `numpy`, `scikit-learn`, `chromadb`, `sentence-transformers`, `openai`
   or `requests` for OpenRouter, `python-dotenv`).
2. Sign up for a free HUD User account and API token; confirm a test call to
   `fmr/data/<county_fips>` returns data.
3. Download and do a first-pass EDA on: the Kaggle apartment dataset (confirm/parse the
   `time` column and its actual vintage), a Redfin Housing Market Tracker pull —
   `Rolling 3 Months` frequency, `Metro` region type only (ZIP-level is deferred, see
   §2), `property_type = Multi-Family (2-4 Units)`, filtered to the candidate metros,
   ~2018–present — and a sample HUD FMR pull for 2–3 counties across different years.
   Confirm actual columns available, apply the minimum-price floor to the Redfin
   extract, and adjust `DealTerms` / `Comp` schema fields to match reality rather than
   assumption.
3a. Run a `groupby` listing-count check on the Kaggle dataset by city/metro to confirm
   real data density for the candidate metros in §2 (New York, Chicago, Philadelphia as
   the working hypothesis); finalize the ~5–8 metro training shortlist and the 2–3
   metro inference subset before building the comps index in Week 4.
4. Implement `DealState`, `Flag`, `DealTerms`, `Comp` in `state.py`.
5. Implement `tools/llm_client.py`: a thin wrapper around the OpenRouter API supporting
   model selection per call (cheap model for dev-loop testing, stronger model reserved
   for extraction/critic/summarizer).
6. Implement `tools/hud_fmr.py`: fetch-and-cache FMR by county + fiscal year, with a
   documented fallback (state or national average) when a county has no entry.
   **Detailed build plan for this item: see §9.** Built ahead of the rest of this task
   list, since Kaggle/Redfin data already exist in `data/` and don't depend on it —
   getting a real HUD data pull working doesn't need `config.py`/`state.py`/`agents/`
   to exist first.
7. Implement `agents/extractor.py`: the Extraction and Clarification loop from Checkpoint
   2.1 — parse listing → identify missing/ambiguous required fields → retry, ask, or flag
   an assumption → bounded retries → escalate.
8. Build 2–3 synthetic test listings (per program data rules: no real proprietary data)
   and confirm the Extractor produces a complete `DealTerms` object (including
   `county_fips`) or a well-formed set of clarifying questions + flags for each.
9. Stub out `agents/planner.py` with the manual routing logic that will later become
   LangGraph edges — even a simple `if extraction_incomplete: ... elif ready_for_retrieval: ...`
   is fine for now, as long as it only reads/writes `DealState`.

---

## 8. Notes for Claude Code

- Follow the four conventions in §3 (pure state-in/state-out agent functions, no
  agent-to-agent calls, single typed state object, flags encoded in state) from the first
  line of code — they're what makes the Week 6 LangGraph migration cheap instead of a
  rewrite.
- Every agent function should have a docstring stating its Reason/Act/Observe/Decide loop
  (matching the structure in Checkpoint 2.1), so the eventual code can be dropped directly
  into the final report as evidence of the reasoning loop design.
- Keep `config.py` as the single place for tunable parameters (search radius X, comp count
  threshold Y, iteration cap Z, confidence threshold for human review) — these will need
  to be tuned during Week 4–7 and should not be hardcoded inside agent functions.
- Never let Redfin data touch a rent dollar figure, and never let Kaggle's raw (unanchored)
  dollar figures reach the Summarizer — always pass through FMR normalization first. This
  is the concrete code-level expression of the rent-level anchoring design in §2.
- All test/dev data must be synthetic or public per program requirements — do not pull in
  real scraped listings.

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**Status:** built and verified against the live API, Aug 8, 2026. `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py`, `requirements.txt`, and a dedicated `.venv/` all exist
under `src/` as planned below.

**What the real pull found (corrects an assumption in §2):** the smoke test ran
`get_fmr` for all three candidate counties at both `year=2019` (Kaggle vintage) and
`year=None` (resolved to 2026, the current FY) —

| County | entityid | SAFMR? | 2BR FMR, 2019 | 2BR FMR, 2026 |
|---|---|---|---|---|
| New York County, NY | `3606199999` | **No** — flat shape | $1,831 | $2,910 |
| Cook County, IL | `1703199999` | **Yes** — SAFMR list shape | $1,212 | $1,781 |
| Philadelphia County, PA | `4210199999` | **Yes** — SAFMR list shape | $1,200 | $1,810 |

§2 had hypothesized New York was the likely SAFMR metro among the three — reality is
the opposite: New York is flat, and Chicago/Philadelphia are the SAFMR ones. Both
correctly fell back to the `"MSA level"` entry (metro-level default, no `zip_code`
passed), confirming the SAFMR branch is genuinely exercised, not just written
defensively. Cache verified too: an immediate repeat call returned in 0.000s (cache
hit, no second HTTP request).

**Scope:** deliberately narrow — just the client and a real smoke-test pull, so a
working HUD data pull exists as soon as possible. Explicitly **not** included here:
`config.py`, `state.py`, `agents/`, `tests/`, or the rest of the Week 3 Task List
scaffold (item 1) — those are a separate, later pass. Kaggle and Redfin data already
sit in `data/` (repo root) and don't depend on any of this.

**Files added:**
```
src/
├── requirements.txt          # requests, python-dotenv
├── .venv/                    # gitignored — dedicated virtualenv for this project
├── tools/
│   ├── __init__.py
│   └── hud_fmr.py            # the client
└── scripts/
    └── pull_fmr_sample.py    # runnable smoke test — a real pull, not a mock
```

**Auth:** the bearer token already exists at `ignore/fmr_key` (repo root, gitignored,
confirmed to be a raw JWT with no `KEY=` prefix). `hud_fmr.py` resolves the token as:
`HUD_FMR_TOKEN` env var if set, else read `ignore/fmr_key` relative to the repo root.
No `.env` file is required for this to work; the env var is only an override.

**Base URL:** `https://www.huduser.gov/hudapi/public`

**Endpoints wrapped:**

| Function | Endpoint | Purpose |
|---|---|---|
| `list_states()` | `GET /fmr/listStates` | state code ↔ name lookup |
| `list_counties(state_code)` | `GET /fmr/listCounties/{state_code}` | county name → 10-digit FIPS `entityid` lookup |
| `get_fmr(entityid, year=None)` | `GET /fmr/data/{entityid}?year={year}` | raw FMR record for one county/metro + one fiscal year; omitting `year` returns the latest available and the response's own `year` field is read back rather than assumed |
| `get_fmr_for_bedroom(entityid, bedrooms, year=None, zip_code=None)` | wraps `get_fmr` | single rent figure for a given bedroom count |

**Behavior:**

1. **SAFMR response-shape handling — metro-level by default.** `get_fmr` inspects
   whether the response's `basicdata` is a flat dict (ordinary metro/county) or a
   list (Small Area FMR — ZIP-keyed entries plus one `"MSA level"` entry), per §2's
   HUD FMR API notes. Both shapes are normalized into one consistent return shape so
   callers never need to branch on it. **`zip_code` defaults to `None`, so the result
   is always metro-level**, matching the Kaggle and Redfin data (§2) — for a
   non-SAFMR county there's only ever one metro-wide record anyway, and for a SAFMR
   county the client falls back to the `"MSA level"` entry and reports
   `used_msa_fallback=True`. Passing an explicit `zip_code` (if it matches an entry)
   is supported so the SAFMR branch doesn't crash or silently misparse, but nothing
   in this build calls it that way — it's dead code for now, kept for the same reason
   §2 documents ZIP-level Redfin as deferred-but-real future work rather than built
   today.
2. **Bedroom cap.** `get_fmr_for_bedroom` caps at `four_bedroom` for `bedrooms >= 4`
   and returns `bedroom_cap_exceeded=True` in the result rather than raising. Turning
   this into an actual `Flag` (`kind="fmr_bedroom_cap_exceeded"`) is the Valuation &
   Rent agent's job once `state.py` exists — out of scope for this client.
3. **Year resolution.** Every result carries the `year` HUD actually returned, never
   the caller's requested year, so downstream code can't silently assume a stale or
   wrong year was honored.
4. **Local caching.** On-disk JSON cache at `data/raw/hud_fmr_cache.json` (repo root,
   already gitignored), keyed by `(endpoint, entityid, year)`. Avoids re-hitting the
   API for repeat lookups during dev and later training-data prep.
5. **Rate limiting.** A client-side throttle enforces HUD's 60 requests/minute cap
   (simple minimum interval between calls); cache hits bypass the throttle entirely
   since they never hit the network.
6. **Errors.** A small `HudFmrApiError` is raised on non-200 responses (status +
   body included). No silent state/national-average fallback is implemented yet —
   that logic belongs to the Valuation & Rent agent's flag-aware design in §2, which
   needs `Flag`/`DealState` to exist first.

**Smoke test (`scripts/pull_fmr_sample.py`):** pulls real FMR data for 2-3 counties
across the candidate metros (New York City, Cook County/Chicago, Philadelphia County)
across two years — one Kaggle-vintage year (e.g. 2018) and the current/latest year
(via `year=None`) — and prints/saves the parsed result. This is meant to produce
visible proof the client authenticates correctly and actually exercises both response
shapes, not just pass a unit test against fixture data.

**Verification before calling this done:**
- Real (not mocked) calls to `list_counties` and `get_fmr` succeed against the live
  API using the token in `ignore/fmr_key`.
- At least one of the three candidate counties returns a SAFMR (list) shape,
  confirming that code path is actually exercised.
- Running the same query twice hits the on-disk cache on the second call (no second
  HTTP request — verified via a log line or timing), and the cache file lands in
  `data/raw/`, not committed to git.
