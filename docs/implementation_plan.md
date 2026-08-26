# Multi-Family Residential Deal Evaluator — Implementation Plan

**Technical plan of record.**
Author: Jelani Gould-Bailey · Last updated: Aug 24, 2026

> **This document states the current design.** The reasoning that produced it — including
> premises that were measured and disproved — lives in
> [`history/decision_log.md`](history/decision_log.md). Unresolved questions live in
> [`open_questions.md`](open_questions.md). Split out Aug 24, 2026, so that what a session
> must load stays separable from what it can look up.

## How this project is built

This is the engineering plan for a capstone system built during CMU's Agentic AI
executive education program. It is written as a working document: architecture,
sequencing, data strategy, and the reasoning behind each decision, updated as
assumptions get tested against real data.

**Working model.** I set the architecture, data strategy, and execution sequence, and
I review every change. Implementation is executed with Claude Code against the
specifications in this document. This mirrors how I work as an engineering manager —
the leverage is in the design decisions, the data reasoning, and the review standard,
and this document is where that work lives. Sections §2 (data strategy), §3 (stack
rationale), §5 (state design), and §6 (sequencing) are the substance of the project;
the code is the expression of them.

Two conventions follow from that and are enforced throughout: every non-obvious
decision is recorded *with its reasoning* — in §7's register here, at length in
[`history/decision_log.md`](history/decision_log.md) — and every assumption is labeled
as an assumption until it has been checked against data. §2 contains a worked example
of the second — a metro-selection hypothesis I held confidently, tested, and found to
be wrong.


---

## Document map

**Read every session:** this file and [`open_questions.md`](open_questions.md).
**Read at unit start:** the current unit's file in [`tasks/`](tasks/) — for example
[`tasks/task_list_u7.md`](tasks/task_list_u7.md).
**Everything else is on demand**, and the folder says which kind it is — `design/` is what
the system currently *is*, `history/` is *how it got that way*.

| Document | What is in it | Read it when |
| --- | --- | --- |
| **`implementation_plan.md`** (this file) | §1 summary, §6 execution order and unit table, §7 decisions register, cut list, the hard constraint | Every session |
| **`open_questions.md`** | Every unresolved question, grouped by system area, each naming the unit that must close it | Every session |
| **`tasks/task_list_<unit>.md`** | That unit decomposed into commit-sized subsections, with its blocking questions stated up front. One file per unit, so a session loads only the unit it is on — [`tasks/README.md`](tasks/README.md) indexes them | Starting or resuming a unit |
| `design/architecture.md` | §3 stack rationale, §4 repository structure, the design conventions node code must follow | Touching the graph or adding a node |
| `design/state_schema.md` | §5 — `DealState` and every field, with provenance and reducer semantics | Adding, reading, or changing a state field |
| `design/data_strategy.md` | §2 — Kaggle/Redfin vintage and category reconciliation, metro selection, sparsity, ZIP anchoring | Reasoning about any rent or price number |
| `design/data_sources.md` | Which dataset feeds which process, at which geographic level | **Before touching anything data-related** |
| `design/engineering_standards.md` | §8 — the bar every change set is held to in review | **Before writing code** |
| `design/hud_fmr_client.md` | §9 — `tools/hud_fmr.py` behaviour, caching, rate limits | Touching FMR |
| `history/decision_log.md` | All 17 numbered decisions with their full reasoning, grouped by system area | Revisiting a decision, or checking a premise before relying on it again |
| `history/changelog.md` | Chronological code changes, by date and unit | Closing a unit; tracing when something landed |
| `diagrams/` | Graph topology generated from the compiled graph (`.mmd`, `.png`) | Reviewing or describing the topology |

**Section numbers (§1–§9) and decision numbers (#1–#17) always refer to this file** —
§-numbers to its sections, #-numbers to the decisions register in §7. Code comments and
the other documents cite them bare, so this is the resolution rule for all of them.

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
  Candidate: <https://www.kaggle.com/datasets/shashanks1202/apartment-rent-data>
  (verify column fit against the comps schema below; confirm/parse the `time` column,
  likely a Unix timestamp — dataset is known to be ~2017–2019 vintage).
- **HUD Fair Market Rents (FMR)** — free, public, county-level, annual, rent-specific
  time series. Used to anchor the Kaggle-derived rent structure to current dollars.
  API: <https://www.huduser.gov/portal/dataset/fmr-api.html> (free account + bearer token
  required — set this up before Week 4).
- **Redfin Data Center — Housing Market Tracker, filtered to `property_type =
  Multi-Family (2-4 Unit)`** — free, public, time series (median sale price, days on
  market, inventory) available down to neighborhood/ZIP/city/county/state, filterable
  by property type. This is the sole appreciation source (see §2 — Redfin Home Price
  Index does not cover multi-family and is not used). <https://www.redfin.com/news/data-center/downloads/>

---

---

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

**→ [`design/data_strategy.md`](design/data_strategy.md).**

---

## 3. Stack Decision: LangGraph from day one

**→ [`design/architecture.md`](design/architecture.md).**

---

## 4. Proposed Repository Structure

**→ [`design/architecture.md`](design/architecture.md).**

---

## 5. State Schema (design target for `state.py`)

**→ [`design/state_schema.md`](design/state_schema.md).**

---

## 6. Execution Order

Revised Aug 8, 2026, around three principles.

**1. Walking skeleton first.** The previous ordering built the Summarizer last, in the
final week — meaning the component that produces the system's actual output would have
been the least exercised and the most schedule-exposed. Inverted: all seven agents are
stubbed and wired into a running graph in Week 4. From that point there is always a
working end-to-end system, and every subsequent unit replaces one stub with a real
implementation — a small, bounded, independently reviewable change. This converts the
dominant schedule risk from *"will the pieces integrate?"* (discovered late, expensive)
to *"how good is each piece?"* (discovered continuously, cheap).

**2. Within the build phase, order by technical risk rather than pipeline position.**
Retrieval is built before the rent regression even though it sits later in the data
flow, because Chroma and embeddings are the least familiar components in the stack
while the regression is the most familiar. Unknowns get front-loaded into the weeks
that still have recovery room.

**3. Work is decomposed into review-sized units, not calendar weeks.** The binding
constraint on this project is ~5–6 hrs/week of design and review capacity. Each unit
below is scoped to roughly 2–3 hours of review — two per week, with the buffer week
absorbing four. A corollary worth stating because ignoring it is expensive: a design
decision deferred past the unit that needs it blocks implementation *and* consumes
review capacity on re-establishing context. [`open_questions.md`](open_questions.md)
and the per-unit breakdown in [`tasks/`](tasks/) exist to close those out
before a unit starts rather than during it.

### The units

Completed units are stated here as what they produced. The findings that came out of
building them — including the ones that changed the design — are in
[`history/decision_log.md`](history/decision_log.md), linked per row.

| Unit | Build target | Feeds | Findings |
| --- | --- | --- | --- |
| **U1** ✅ | `state.py` (Pydantic + reducers), `config.py`, `nodes.py`, `llm_client.py` (schema-validated retry), `kaggle_data.py`, `county_crosswalk.py`, `redfin_data.py`; FMR pull for the trio × {2019, latest} | — | — |
| **U4** ✅ | Comps/Retrieval: Chroma index (3,880 listings), one document per listing, hybrid metadata-filter + embedding query, top-`Y` results, adaptive relaxation loop, sparse-comps flag; **two ablations**; X/Y/Z tuned against measured density | **3.1** | [Retrieval](history/decision_log.md#retrieval) |
| **U2** ✅ | **Walking skeleton.** 8 nodes wired in `graph.py` on the pre-flight Planner topology (#9) incl. the single Critic→Planner back edge and the `human_review` interrupt; Planner and Summarizer built for real; flag propagation proven by a 14-case suite; diagram generated from the compiled graph *and* asserting the topology | **5.1** | [Orchestration](history/decision_log.md#orchestration--control-flow) |
| **U3** ✅ | Extractor: real LLM call, Pydantic validate→retry loop, clarifying questions, assumption flags, bounded escalation. Wires geocoding into the pipeline, adds the model liveness check, takes the flag suite to 24 cases | 2.1 evidence | [Models & infra](history/decision_log.md#models--infrastructure), [Geography](history/decision_log.md#geography--anchoring) |
| **U5** ✅ | Rent model: FMR-normalized regression on the #4 shortlist, holdout MAE, Valuation agent, `rent_anchored_to_fmr` / `fmr_unavailable_for_county` / `fmr_bedroom_cap_exceeded` flags. **LLM fallback descoped** — cut-list item 3 taken in advance, shipping as a documented gap | — | [Rent & valuation](history/decision_log.md#rent--valuation) |
| **U6** ✅ | Scenario/Forecast: beam search over an **enumerated** hypothesis space — 4 framings, then 9 band pairings — with an LLM evaluator pulling evidence through the MCP tool registry in-process. Rent growth and price appreciation forecast **separately** (#16), projected 5 years from the **asking price** (#15) | **4.1** | [Forecasting](history/decision_log.md#forecasting--reasoning) |
| **U7** ⬜ | Critic: cross-agent consistency checks, confidence scoring, bounded rework cycle, human-review escalation via `interrupt()` | **6.1** | [open questions](open_questions.md#orchestration--control-flow) |
| **U8** ⬜ | Eval harness: 8–10 synthetic listings each engineered to trip a *specific* flag, **plus the New York sparse-comps case run against real data**; batch runner → results table | **6.1** + report | [open questions](open_questions.md#evaluation--demo) |
| **U9** ⬜ | Summarizer polish + Streamlit demo app | report + video | — |
| **U10** ⬜ | End-to-end runs across all three metros; capture traces, screenshots, diagrams | report + video | — |
| — | **Week 7 — code frozen.** Final report + 8–10 min video | **7.1** | — |

### Notes on the sequence

**Multi-agent coordination is working by Week 4 rather than Week 6.** This is the
direct payoff of ordering by dependency: the coordination design gets described from a
running graph and real traces rather than from a design sketch. Each weekly checkpoint
asks for a written design update alongside a working agent update, so building the
capability before writing about it improves both halves of the submission.

### Cut list, in order

If the schedule slips, shed scope in this order rather than improvising:

1. **ZIP-tier appreciation** (already deferred in §2 — keep it deferred).
1a. **Rent-model feature engineering and model form** (deferred Aug 22, 2026 — keep it
   deferred). Roughly 17% of rent error is available to model form alone, measured, with
   no new data and no new features. Deferred anyway; the probe and the two reasons are in
   [`history/decision_log.md`](history/decision_log.md#rent--valuation).
2. **Public-record for-sale ground truth** (decision #11) — the county-assessor dataset
   that would let the *value* estimate be scored rather than only demonstrated. Cut
   before the LLM fallback because it is a new data source arriving late, attached to the
   one unit that must not slip. Cutting it costs a validated value estimate, not a
   working one: demo deals stay calibrated against Redfin and FMR, and the rent model
   keeps real ground truth from the held-out corpus slice. Document the gap explicitly.
2a. **Pass-scoped flags** (raised Aug 25, 2026 in U7; scheduled at U8). `DealState.flags`
   is append-only by design, so nothing distinguishes *raised this pass* from *ever
   raised*. Every Critic interaction check reads the accumulated list as current truth,
   which means a rework that **succeeds** — the geocoder answers, the divergence clears —
   still re-raises the objection it was sent back to fix, and tells the reader something
   that is no longer true. Stamping each flag with the `planner_invocations` that produced
   it fixes all of them at once.

   Cut *after* the ground truth above and before the demo, on this reasoning: it is a
   correctness problem in reader-facing text rather than in any number, it only surfaces
   on a rework lap, and every rework lap ends at human review by construction — so a
   person sees the full flag list and the stale sentence together. Real, bounded, and
   visibly wrong to the one audience guaranteed to be looking. Cutting it costs precision
   in a paragraph, not a wrong estimate. Detail in
   [`tasks/task_list_u7.md`](tasks/task_list_u7.md) Q6; `TODO(U8)` at both sites.
3. ~~**LLM rent fallback path**~~ — **taken Aug 21, 2026, ahead of any slip.** Documented
   as designed-but-unbuilt; Checkpoint 2.1 already anticipated this exact trade. Recorded
   here rather than struck out, because this item left the cut list by being *spent*, not
   by becoming unnecessary — the remaining list is one item shorter than it looks.
4. **Streamlit app** — fall back to a terminal recording plus LangSmith traces.
5. **Critic rework-loop depth** — reduce to single-pass review with escalation,
   keeping the cycle in the graph but capping `MAX_REWORKS = 1`.

**Never cut:** the flag propagation test (U2), the eval harness (U8), or the Week 7
report reserve.

### The hard constraint

**Week 7 is reserved entirely for the report and video, with the code frozen.** The
realistic failure mode for a fixed-deadline project like this is arriving at the final
week still integrating, and shipping a rushed write-up of a system nobody has time to
evaluate. A frozen build a week out guarantees there is something coherent to measure,
document, and demonstrate. Any unit unfinished at that point ships as-is and is
documented explicitly as future work — stating a known limitation is better engineering
communication than concealing it, and it is consistent with the Transparent Degradation
principle the system itself implements.

---


---

## 7. Decisions Register

**The index to [`history/decision_log.md`](history/decision_log.md)**, which carries the
full reasoning for every row. Open questions are **not** here — they are in
[`open_questions.md`](open_questions.md), kept separate because that file is loaded every
session and this one is a lookup table.

Each decision has a stable number. Code comments and the other documents cite them bare
("decision #9"), so this table is what resolves them.

| # | Decision | Area | Landed | Verdict |
| --- | --- | --- | --- | --- |
| 1 | Orchestration framework | Orchestration | U1 | ✅ LangGraph, from day one |
| 2 | Inference metro trio | Data & sources | U1 | ✅ Chicago, Los Angeles, Cleveland |
| 3 | Demo surface | Eval & demo | U9 | ✅ Streamlit, local |
| 4 | Training metro shortlist | Data & sources | U5 | ✅ Eight metros; 5,717 usable rows |
| 5 | X / Y / Z retrieval loop parameters | Retrieval | U4 | ✅ X = 2.0 mi, Y = 8, Z = 4; rationale in `config.py` |
| 6 | Confidence threshold for escalation | Orchestration | **U7** | ⬜ **OPEN** — provisional 0.60. Any critical flag already escalates independently of score; confirm rather than re-derive → [open](open_questions.md#orchestration--control-flow) |
| 7 | Redfin minimum-price floor | Data & sources | U1 | ✅ $10,000; inert for all three inference metros |
| 8 | OpenRouter model per role | Models & infra | U3 | ✅ `nvidia/nemotron-3-nano-30b-a3b`, paid variant. Critic/Summarizer roles revisit at U7/U9 |
| 9 | Planner topology — pre-flight vs. supervisor | Orchestration | U2 | ✅ Pre-flight + rework re-entry; one back edge, asserted on every diagram export |
| 10 | Geocoding source for `latitude`/`longitude` | Geography | U3 | ✅ Census Geocoder + corpus-centroid fallback; county now resolved by point-in-polygon |
| 11 | Grounding for demo and evaluation deal terms | Data & sources | U3 → **U8** | 🟨 **PART OPEN** — demo listings calibrated against Redfin + FMR; public-record ground truth planned, on the cut list → [open](open_questions.md#data--sources) |
| 12 | Tree-of-Thought scope | Forecasting | U6 → **U7** | ✅ Selective ToT — Scenario/Forecast and the Critic's consistency checks only. Critic half unbuilt |
| 13 | MCP adoption | Models & infra | U6 | ✅ Read-only reference server; adopted for portability and a second consumer, not capability. CrewAI declined |
| 14 | ToT branch-state persistence | Forecasting | U6 | ✅ Compact ledger in state, full tree to `eval/results/` behind a flag |
| 15 | Property-level value estimate | Rent & valuation | U6 | ✅ Not produced. `value_estimate` stays `None`; metro median carried as a labelled benchmark |
| 16 | Rent-growth source | Forecasting | U6 | ✅ Rent from HUD FMR history, price from Redfin — forecast separately (pooled r = −0.309) |
| 17 | ToT structure at build time | Forecasting | U6 | ✅ Enumerate the space, do not sample it; pipeline stays deterministic |


---

## 8. Engineering Standards

**→ [`design/engineering_standards.md`](design/engineering_standards.md).**

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**→ [`design/hud_fmr_client.md`](design/hud_fmr_client.md).**
