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
| `design/evaluator.md` | What the forecast's Tree-of-Thought evaluator scores, the four defects found at U9.6, and the re-measured rent/price correlation that retired #16's pairing premise | Touching the forecast, the scenario table, or the evaluator prompt |
| `design/forecast_starting_point_spike.md` | A spike, not a build: what OQ-22's re-purposed forecast would produce, why the model-scored version was not adopted (5/8 stability on the easy deal), and the deterministic rule that reproduces its modal answer. Evidence in `src/eval/data/exploratory/` | Deciding OQ-22, or before re-opening the starting-point question |
| `design/personas.md` | The four personas this system is built for, their journeys, and the escalation routing rule (which human-review desk a pause is waiting on) | Touching `human_review`, the escalation payload, or writing report content aimed at a specific reader |
| `design/recommendation.md` | What the system is willing to say about a *deal* rather than about its own numbers: the two axes, the four verdicts, the 44,358-sale percentile evidence under their thresholds, and the model-proposes/rule-decides cross-check | Touching `critic.recommend` or `cross_check`, or any threshold on the asking price |
| `sample_reports/` | Three full reports the pipeline produced, committed as-is — a clean run, an escalated one, and one where the *deal* rather than the software is the problem | Seeing real output without running anything, or checking what a change does to the report |
| `demo.md` | The eight demo listings in plain language — what each exists to show, and what in the output demonstrates it | Preparing a demo or a recording, adding a demo deal, or explaining why a given listing is in the set |
| `presentation.md` | Checkpoint 7.1's deliverables: the slide outline timed to 9:30, the narration script, the demo beat sheet, the report's section-by-section source map, and the elevator pitch. The capture commands stay in [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9 | Preparing or recording the presentation, or writing the final report |
| `history/decision_log.md` | All 21 numbered decisions with their full reasoning, grouped by system area | Revisiting a decision, or checking a premise before relying on it again |
| `history/changelog.md` | Chronological code changes, by date and unit | Closing a unit; tracing when something landed |
| `diagrams/` | Graph topology generated from the compiled graph (`.mmd`, `.png`) | Reviewing or describing the topology |

**Section numbers (§1–§9) and decision numbers (#1–#21) always refer to this file** —
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
| **U5** ✅ | Rent model: FMR-normalized regression on the #4 shortlist, holdout MAE, Valuation agent, `rent_anchored_to_market_index` / `rent_anchor_unavailable` / `fmr_bedroom_cap_exceeded` flags. **LLM fallback descoped** — cut-list item 3 taken in advance, shipping as a documented gap | — | [Rent & valuation](history/decision_log.md#rent--valuation) |
| **U6** ✅ | Scenario/Forecast: beam search over an **enumerated** hypothesis space — 4 framings, then 9 band pairings — with an LLM evaluator pulling evidence through the MCP tool registry in-process. Rent growth and price appreciation forecast **separately** (#16), projected 5 years from the **asking price** (#15) | **4.1** | [Forecasting](history/decision_log.md#forecasting--reasoning) |
| **U7** ✅ | Critic: three cross-agent **interaction** checks (a combination changing what a measurement means — the four checks §1 named did not survive contact with the built system), comp-attribute drift owned by Retrieval, confidence scoring evidenced on the real pipeline, a rework cycle that fires on its own and is bounded by its counter rather than by score decay, human-review escalation via `interrupt()` | **6.1** | [Orchestration](history/decision_log.md#orchestration--control-flow) |
| **U8** ✅ | Eval harness, stated as what it produced rather than as what it was sized as. **28 rows across three tiers** — 21 with a verdict *declared before the first run*, 7 live demo baselines — with **30 of 30 flag kinds raised, none uncovered and none unreachable**, and verdict agreement 18/21 with every mismatch triaged. Plus: a published parameter sweep closing #6, six straddle fixtures measuring brittleness at the per-flag lines, per-metro rent-error disclosure, pass-scoped flags, and a sub-metro price benchmark that arrived from the cut list. **Absorbed U10** — the demo deals are rows in the same batch, so the end-to-end evidence is a harness output rather than a separate pass. **The figures above are U8's at its close and the batch has grown since**: U9.6 added two demo deals, so `eval/results/results.md` now reports **30 rows, 23 predicted, agreement 20/23, and 30 of 30 flag kinds raised**. Stated here because the final report quotes these numbers and this table is where it will read them | **6.1** + report + video | [Orchestration](history/decision_log.md#orchestration--control-flow), [Eval & demo](history/decision_log.md#evaluation--demo) |
| **U11** ✅ | Rent model, re-opened on measurement rather than on plan. Model form cross-validated and moved to **gradient boosting** (#18); the rent anchor re-based on a **ZORI/FMR hybrid** — ZORI for the level at the subject's own ZIP, HUD for the bedroom step (#19), which spent §6 cut-list item 6 and retired U8.4b's drift correction structurally. Per metro: New York $981 → $855, Chicago $454 → $343, overall flat — the headline hides the result, which is why per-metro reporting is now standard | — | [Rent & valuation](history/decision_log.md#rent--valuation) |
| **U9** ✅ | **Planned as "Summarizer polish + a Streamlit app" and rewritten after the architect ran the pipeline and read two reports** — none of what the unit became was visible from the code. **Two axes separated and never merged**: `needs_human_review` is a statement about the software, `recommendation` about the property. **A second reasoning locus** — the model proposes a verdict from the same state, the deterministic rule decides, and disagreement is disclosed rather than resolved. Rent growth re-sourced to ZORI (**#21**) after its pairing premise was re-measured and found false. Personas and an escalation *routing* rule. The **Streamlit surface** (#3; §6 cut-list item 4 **spent**), a sixth demo deal so the set shows a clean run twice, and the live tier pinned so **all 30 eval rows and three sample reports replay from a clone**. **U9.9's capture is outstanding at close** — see the note below | report + video | [Eval & demo](history/decision_log.md#evaluation--demo), [Models & infra](history/decision_log.md#models--infrastructure), [Forecasting](history/decision_log.md#forecasting--reasoning) |
| — | **Code frozen Sept 4, 2026.** Final report + 8–10 min video, due Sept 7 | **7.1** | — |

### Notes on the sequence

**Multi-agent coordination is working by Week 4 rather than Week 6.** This is the
direct payoff of ordering by dependency: the coordination design gets described from a
running graph and real traces rather than from a design sketch. Each weekly checkpoint
asks for a written design update alongside a working agent update, so building the
capability before writing about it improves both halves of the submission.

**U10 folded into U8 — Aug 26, 2026.** U10 was end-to-end runs across the three metros
capturing traces, screenshots and diagrams; U8 is already a batch runner over engineered
listings. Running the demo deals through the same harness produces the same artifacts from
one code path instead of two, and it removes the failure mode where the demo evidence and
the evaluation evidence are generated differently and disagree.

**U8.9 — the subsection that would have built the absorbed capture scope — was dropped
Aug 30, 2026 and reassigned whole to U9.7/U9.9**, so the traces, screenshots and diagram
listed below were still outstanding when U8 closed. Noted here because this table is read
every session and the U8 row otherwise reads as if the absorption fully landed
(maintenance item M4). [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9. Taken to buy schedule under
the Sept 4 freeze, but it is the better structure regardless: **the demo becomes a row set
in the evaluation, not a separate performance.** The absorbed scope, so it is not lost when
U8 is planned: per-metro runs across all three metros, LangSmith traces captured, demo
screenshots, and the graph diagram generated from the compiled graph.

**U9 closed Sept 2, 2026 with U9.9 — the capture — outstanding, and it is the unit's one
gap.** Live runs, LangSmith traces, screenshots off the shipped surface. It is not deferred
work in the ordinary sense: every prerequisite is discharged and verified, and a runbook with
the exact commands is in [`tasks/task_list_u9.md`](tasks/task_list_u9.md) §U9.9. What it needs
is a live account and a screen. **Noted here rather than only in the task file for the same
reason M4 added U8.9's drop to the U8 row** — this table is read every session, and a ✅ with
an outstanding subsection under it is exactly the kind of thing that stops being visible.
[OQ-13](open_questions.md) is the entry that carries it, and it is the only open question U9
was expected to close and did not.

### Cut list, in order

If the schedule slips, shed scope in this order rather than improvising:

1. ~~**ZIP-tier appreciation**~~ — **not deferred: closed on evidence, and this row said the
   wrong thing until Sept 2, 2026.** It read *"already deferred in §2 — keep it deferred"*,
   which describes a choice still available to make. It is not: the Redfin ZIP extract carries
   a **median 2 homes sold per ZIP-period**, so a year-over-year rate computed off it is noise
   rather than a finer-grained signal. Recorded at `tools/redfin_data.SERIES_DESCRIPTION`,
   where the three-member `AppreciationTier` enum was reduced to a description at U6 because
   two of its three rungs were unreachable. **Corrected here rather than left**, because a cut
   list is read at exactly the moment someone is looking for scope to reclaim, and an item that
   reads as *deferred* invites a re-open that measurement has already foreclosed. The price
   side stays metro-grain; what became sub-metro is the sale-price *benchmark* (item 2) and the
   rent anchor (#19), both of which need a median rather than a rate and are therefore not
   defeated by thin per-period counts.
1a. **Rent-model feature engineering and model form** (deferred Aug 22, 2026). Roughly 17%
   of rent error is available to model form alone, measured, with no new data and no new
   features. Deferred anyway; the probe and the two reasons are in
   [`history/decision_log.md`](history/decision_log.md#rent--valuation).

   **Split Aug 30, 2026 at U11, because half of it was spent and half of it was not.**
   *Model form* left this list by being taken: U11.1 measured the three candidates under
   k-fold cross-validation and the architect adopted gradient boosting (#18). *Feature
   engineering* stays cut, and three further refinements join it here rather than being
   tracked as unfinished U11 work:

   - **Feature engineering** (U11.2) — interaction and derived terms above the three raw
     features. Never measured.
   - **Hyperparameter tuning** — the adopted form ships at library defaults, deliberately
     and on the record at `config.RENT_MODEL_ESTIMATOR`. Tuning is the classic way to
     spend a day buying a number that a 5-fold CV cannot distinguish from noise.
   - **Leave-one-metro-out validation** — the transfer evidence OQ-12's first half asks
     for. It answers a question the holdout split cannot, and it is the one of the three
     worth regretting.

   **Cut Aug 30, 2026 by the architect, and the reasoning is about what the model is
   for.** The anchor change (item 6, below) was the lever with a *measured* defect behind
   it and it has been spent. These three are refinements to a model that is now
   defensible: cross-validated, per-metro reported, with its worst market disclosed to
   the reader rather than averaged away. The remaining schedule buys more by closing U8's
   evaluation than by taking another percent off a headline MAE — and an undisclosed
   percent is worth less to this project than a disclosed limitation, which is what these
   become. Recorded in [`tasks/task_list_u11.md`](tasks/task_list_u11.md) U11.2 / U11.4.
2. **Public-record for-sale ground truth** (decision #11) — the county-assessor dataset.
   Cut before the LLM fallback because it is a new data source arriving late, attached to
   the one unit that must not slip.

   **Taken Aug 28, 2026 at U8.8, and respecified — this item's stated cost was stale.**
   It read "cutting it costs a validated value estimate", which describes something the
   system stopped producing three units ago: **#15 made `value_estimate` permanently
   `None`** in U6. There is no value estimate to validate. Nor can assessor data score the
   demo deals' asking prices, because those listings are synthetic — the property is not
   for sale and #11 set the asking price *from* the Redfin metro median, so there is no
   real asking price and no real sale to score it against.

   What the dataset can actually deliver is a **sub-metro sale-price benchmark** replacing
   the metro median in `ValuationDetail.benchmark_median_sale_price` — the price-side
   counterpart to the ZIP-resolution rent anchoring that already landed, and what makes
   #15's labelled benchmark local rather than metro-wide. Real value, and a different one
   from the value this list priced.

   **Its risk is unchanged and is managed by date rather than by position.** It is the one
   item in U8 whose cost is not bounded in advance — an address-to-parcel join is the same
   class of work that produced U3's geocoding tier fallbacks — so it is scheduled *behind*
   the harness core with a **drop-dead of Mon Sept 1**. If the join is not working by then
   the cut is taken with three days in hand and the gap is written up.
   [`tasks/task_list_u8.md`](tasks/task_list_u8.md) Q3.

   **TAKEN Aug 30, 2026 at U8.8, two days inside the drop-dead — this item leaves the list
   by being spent, like items 3 and 6.** ZIP-tier benchmarks ship for New York and Chicago
   from county-assessor transaction records; Los Angeles and Cleveland keep the metro figure
   with the reason disclosed per deal, because California assessors publish assessed value
   rather than sale price. **The risk the date was set against never materialized, and the
   reason is the third instance of one pattern.** It was priced as an address-to-parcel
   join; a *benchmark* needs a median over the subject's ZIP and never identifies the
   subject's parcel, so no fuzzy address matching exists anywhere in the change set. The
   only join is Cook's, on the assessor's own primary key, measured at 96.8% with the misses
   counted rather than dropped silently.

   **The pattern, stated here because it has now happened three times in two units and is a
   property of this list rather than of any item on it:** item 2a's price was "a §5 change
   touching every agent that raises a flag" and measured as 37 call sites and one commit;
   item 6's was "drops 27% of the training rows" and measured as 0.3%; this one's was an
   unbounded join that the respecified deliverable does not contain. **Every one was
   estimated when written and wrong in the direction that made the item look expensive.** A
   cut-list price is a guess recorded under schedule pressure, and it decays as the item it
   describes is respecified. **Re-measure a cut-list item before spending it, and again
   before cutting it** — cutting on a stale price is the same error as spending on one, with
   nothing to catch it afterwards.
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

   **Taken Aug 28, 2026 at U8.5, and this item's cost was overstated.** "A §5 change
   touching every agent that raises a flag" reads as expensive and was never measured.
   Measured: **37 `flag()` call sites across five agents, every one inside a node function
   that already holds `state`**, plus six helper functions that would take a pass index as
   an argument, against a single central `state.flag()` constructor. That is one mechanical
   commit plus the Critic's per-pass filter. It stays on this list at this position as the
   record of the judgment, but the judgment was made against a price roughly an order of
   magnitude too high, and the lesson generalizes: **a cut-list item whose cost was
   estimated rather than measured should be re-measured before it is spent.**
3. ~~**LLM rent fallback path**~~ — **taken Aug 21, 2026, ahead of any slip.** Documented
   as designed-but-unbuilt; Checkpoint 2.1 already anticipated this exact trade. Recorded
   here rather than struck out, because this item left the cut list by being *spent*, not
   by becoming unnecessary — the remaining list is one item shorter than it looks.
4. ~~**Streamlit app**~~ — **TAKEN Sept 1, 2026 at U9.7, and like items 2, 3 and 6 this one
   leaves the list by being *spent* rather than shed.** The surface shipped: it **replays by
   default** from committed recordings, so a demo is instant, deterministic and costs no
   quota; it carries a **genuine review pause** whose typed note reaches the report verbatim;
   and it declares each simulated fault before running it, so a demonstration cannot be
   mistaken for an incident.

   **The fallback this row named is being produced anyway, and that is not the same as the
   item being shed.** U9.9 captures a terminal recording and LangSmith traces *alongside* the
   surface, as evidence for Checkpoints 5.1 and 6.1, rather than *instead of* it. Worth
   stating because a fallback that is also an artifact makes a spent item look like a taken
   cut — and this list's whole value is that the difference stays legible.

   **This item's price was not wrong, which is itself worth one line** after items 2, 2a and 6
   were each mis-priced in the direction that made them look expensive. It was never priced at
   all: it named a substitute and no cost. The substitute turned out to be *complementary*, so
   nothing here had to be re-measured before it was spent — the check item 2's close asks for
   found nothing to correct.
5. **Critic rework-loop depth** — reduce to single-pass review with escalation,
   keeping the cycle in the graph but capping `MAX_REWORKS = 1`.

   **Priced by measurement Aug 31, 2026 (U8.M), which is the discipline item 2's close
   asked for — and this one's estimate was not wrong, it was absent.**
   `scripts/rework_budget_sweep.py` runs the replay tier at budgets of 1, 2 and 3: **no
   verdict changes at any of them.** The single case that reworks spends whatever budget it
   is given and escalates on the exhausted budget every time, at the same confidence. So
   this cut costs **nothing measurable in behavior** — what it costs is the
   *demonstration*: at 1 the bounded cycle is exercised once rather than twice, and the
   case stops showing that the counter survives a second lap. **That is a cheaper cut than
   its position implies**, and it is left at position 5 anyway, because the batch's only
   rework case carries a permanently-injected outage — the one condition under which no
   budget can beat another. A transient outage clearing on the second pass is where a
   budget of 1 and 2 would part company, and nothing simulates one.

6. **Re-anchor the rent model on ZORI instead of FMR** (added Aug 28, 2026, on U8.0's
   finding). U8.0 measured the FMR schedule rising +51.9% against market rent's +33.5%
   since the corpus vintage, so the ratio the model learned is anchored to a series that
   has drifted ~18 points away from the market it prices. U8 takes the per-ZCTA
   *correction* (U8.4b); this item is the structural fix the correction stands in for.

   **The evidence is measured, and it is genuinely mixed** —
   `scripts/zori_evidence.py --anchor-comparison`, on the 4,144 rows both anchors can
   price. ZORI covers essentially every ZIP the corpus occupies (5,662 of 5,686) and
   4,147 rows carry an observation at their own listing month, against ZIP-level FMR's
   ~1,100 — so coverage, the reason this was assumed impossible, is not the obstacle.
   But the ratio it produces is *looser* (CV 36.3% against 33.1%), so it is not an easier
   target to learn. What it does better is absorb location: per-city mean ratios spread
   0.172 against FMR's 0.257. Since `RENT_MODEL_FEATURES` carries no market identifier by
   design, whatever the anchor fails to absorb is error the model structurally cannot
   recover — which is §2's "location-blind below the county" limitation, and the property
   an anchor exists to supply.

   **Its cost is a U5 rewrite**: the model, the Valuation agent, `RENT_ANCHORED_TO_MARKET_INDEX`,
   #11's demo calibration, and the reasoning in §2 and #16 all assume the FMR anchor. It
   also drops 27% of the training rows. **Placed last deliberately, and the position means
   what the list says it means — it is shed last, not first.** That is a deliberate choice
   by the architect (Aug 28, 2026) rather than an oversight about where speculative scope
   normally belongs: this is the only item on the list that fixes a *measured* defect in a
   number the report publishes, and the rest fix gaps in scope.

   **TAKEN Aug 30, 2026 at U11.3 — this item leaves the list by being spent, like item 3
   above.** Not in the form written here. `scripts/anchor_probe.py` scored five candidates
   and the architect adopted the **hybrid**: ZORI at the subject's own ZIP for the market
   *level*, HUD FMR for the bedroom *shape*. Two things this row asserted turned out to be
   wrong, and both were wrong in the direction that made the item look more expensive than
   it was:

   - **"It also drops 27% of the training rows" — no.** The 27% is rows whose ZIP carries
     no ZORI observation at their own listing month, and those fall back to a county
     median exactly as the FMR anchor already did. Measured: 0.3% of rows end up with no
     anchor, not 27%.
   - **"It assumes the FMR anchor" — half true.** The hybrid keeps FMR in the system for
     the bedroom schedule, so `FMR_BEDROOM_CAP_EXCEEDED` and the rest of that vocabulary
     survive with their meaning intact. Pure ZORI would have retired them; that was part
     of why the hybrid won.

   What it bought, per metro: **New York $981 → $855, Chicago $454 → $343**, Cleveland
   $366 → $357, Los Angeles $450 → $509, overall flat. The overall figure hides the
   result, which is the point of reporting per metro. It also retired the U8.4b drift
   correction *structurally* — the anchor reads a market index at the same month on both
   ends, so the schedule-versus-market gap is divided out where it arises rather than
   corrected after the fact.

**Never cut:** the flag propagation test (U2), the eval harness (U8), or the report and
video reserve at the end.

### The hard constraint

**Code freezes Fri Sept 4, 2026. The final weekend is the report and the video.**

The realistic failure mode for a fixed-deadline project like this is arriving at the end
still integrating, and shipping a rushed write-up of a system nobody has time to evaluate.
A frozen build guarantees there is something coherent to measure, document, and
demonstrate. Any unit unfinished at that point **ships as-is and is documented explicitly
as future work** — stating a known limitation is better engineering communication than
concealing it, and it is consistent with the Transparent Degradation principle the system
itself implements.

**Revised Aug 26, 2026, by the architect.** Two things changed at once. The submission
date moved earlier than this plan had recorded, and the reserve this section originally
claimed — a full frozen week — was written into the plan during its first drafting rather
than decided. It is now sized deliberately: **nine days of build (Aug 26 – Sept 4), then
the weekend for the write-up.** That is a smaller reserve than the original text asserted,
taken with the deadline nearer, and it is a judgment about this build rather than a
general rule: U7 is mid-flight, U8's harness is the evaluation evidence and cannot be cut,
and the report is largely assembled from artifacts those two units produce rather than
written from scratch.

**Streamlit stays in scope** (cut-list item 4), decided the same day. It is the demo
surface, and the fallback — a terminal recording plus traces — is available late if the
schedule forces it, which is precisely what makes it safe to keep rather than shed early.

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
| 3 | Demo surface | Eval & demo | U9 | ✅ **Streamlit, run locally — landed Sept 1, 2026 at U9.7 and confirmed at U9's close.** Taken early and never revisited, which is unusual on this list and is why the confirmation is recorded rather than assumed. What shipped is narrower than "a Streamlit app" and the narrowness is the design: it **replays by default**, so a demo is deterministic and costs no quota; it renders the Summarizer's own markdown split at its `##` headings and **never lays the evidence out from state**, because two renderings of one body of evidence drift the first time either is edited; it carries a **genuine review pause** whose typed note reaches the report verbatim, which no terminal recording can show; and it declares each simulated fault before running it. Spends §6 cut-list item 4 |
| 4 | Training metro shortlist | Data & sources | U5 | ✅ Eight metros; 5,717 usable rows |
| 5 | X / Y / Z retrieval loop parameters | Retrieval | U4 | ✅ X = 2.0 mi, Y = 8, Z = 4; rationale in `config.py` |
| 6 | Confidence threshold for escalation | Orchestration | U7 → **U8** | ✅ **HELD on measurement Aug 30, 2026, and the claim is robustness rather than optimality.** Threshold 0.60 and warn 0.15 unchanged, now with the stable region published (`eval/results/sensitivity.md`): **63 of 160 grid points** decide the 21-case batch identically, and through the shipped point the threshold moves 0.30–0.70 and the warn weight 0.100–0.200 with no verdict changing. Both axes were widened after the first sweep reported 0.30 as a bound when 0.30 was the *edge of the search*; on the widened grid the plateau ends at a measured 0.25, so that bound now means what it says. **The critical weight is inert across its whole range including zero** — every deal carrying a critical escalates on the independent rule regardless, which is the confirmation U7 left open. Zero cases give evidence the shipped numbers are wrong; a batch that cannot separate two settings has no evidence either way, and the close says so rather than claiming an optimum |
| 7 | Redfin minimum-price floor | Data & sources | U1 | ✅ $10,000; inert for all three inference metros |
| 8 | OpenRouter model per role | Models & infra | U3 → **U9** | ✅ **BOTH HALVES CLOSED Sept 2, 2026 at U9's close** — `nvidia/nemotron-3-nano-30b-a3b`, paid variant, and all five role constants still hold the one ID. **Critic half** closed in U7: the checks that shipped are pure functions, so `MODEL_CRITIC` is untested *by construction* rather than by omission. **Summarizer half closes as inherited, not selected**, and that distinction is the verdict. The Summarizer now makes real calls — U9.4's written lede and the recommendation cross-check — so the setting is exercised rather than dormant, which is the condition OQ-9 named. But it was chosen in U3's bake-off on **schema-valid extraction, latency and price**; **no pass has ever scored a model on prose**, and saying the Summarizer's model was selected for the Summarizer's job is a claim the record does not support. What is known about the prose is a negative result, carried as OQ-26: the lede needed two prompt passes and a structural change before it stopped describing rental comparables as sales, and iteration stopped there because under OQ-17 further tuning fits a single draw. Re-opening it would invalidate the lede recording on every eval row |
| 9 | Planner topology — pre-flight vs. supervisor | Orchestration | U2 | ✅ Pre-flight + rework re-entry; one back edge, asserted on every diagram export |
| 10 | Geocoding source for `latitude`/`longitude` | Geography | U3 | ✅ Census Geocoder + corpus-centroid fallback; county now resolved by point-in-polygon |
| 11 | Grounding for demo and evaluation deal terms | Data & sources | U3 → **U8** | ✅ **Both halves settled Aug 30, 2026.** Demo listings calibrated against Redfin + FMR (U3); the public-record half **built at U8.8, two days inside its drop-dead**, respecified as a sub-metro sale-price *benchmark* rather than ground truth — #15 had removed the value estimate it was written to score. ZIP tier live for **New York and Chicago** from county-assessor transaction records (27,309 and 18,251 sales); **Los Angeles and Cleveland keep the metro figure with the reason disclosed per deal**, because California assessors publish assessed value and a Prop 13 base-year figure is a different instrument. The entry's original source list was wrong on LA County for exactly that reason. Q3's unbounded address-to-parcel join never appears: a benchmark needs a median over the subject's ZIP, never its parcel |
| 12 | Tree-of-Thought scope | Forecasting | U6 → **U7** | ✅ Selective ToT — Scenario/Forecast only. Critic half retired on evidence (U7.7): the checks that shipped are pure deterministic functions, nothing to search over |
| 13 | MCP adoption | Models & infra | U6 | ✅ Read-only reference server; adopted for portability and a second consumer, not capability. CrewAI declined |
| 14 | ToT branch-state persistence | Forecasting | U6 | ✅ Compact ledger in state, full tree to `eval/results/` behind a flag |
| 15 | Property-level value estimate | Rent & valuation | U6 | ✅ Not produced. `value_estimate` stays `None`; metro median carried as a labelled benchmark |
| 16 | Rent-growth source | Forecasting | U6 → **U9** | 🟨 **RENT HALF SUPERSEDED, Aug 31, 2026 — see #21.** Price from Redfin and the separate-forecast structure both stand. The rent half does not: it chose HUD FMR on the argument that projecting the anchor forward forecasts rent by the mechanism that produced the estimate, and #19 changed that mechanism to ZORI. Its **pooled r = −0.309** was re-measured at U9.3 and is an artifact of the FMR schedule — market rent against the same prices gives **+0.222**. **Its ZORI half built Aug 28, 2026 (U8.0) and found the anchor drifting**: FMR +51.9% against market rent +33.5% since the corpus vintage, so the model over-predicts. Corrected per-ZCTA at U8.4b; re-anchoring is cut-list item 6 |
| 17 | ToT structure at build time | Forecasting | U6 | ✅ Enumerate the space, do not sample it; pipeline stays deterministic |
| 18 | Rent-model form | Rent & valuation | **U11** | ✅ **Gradient boosting**, adopted Aug 30, 2026 on `scripts/model_form_probe.py`'s numbers. CV MAE $513.67 → $450.71 (−12.2%) at a train/holdout gap of $18.34, against random forest's $140.41 — the better-scoring form was not the one taken. k-fold cross-validation replaces the single 20% split, and the artifact is refit on all 5,686 rows. The refusal band moved from the model's output to its **input**, since a tree cannot extrapolate an implausible ratio and the old guard would have retired silently |
| 19 | Rent anchor | Rent & valuation | **U11** | ✅ **Hybrid: Zillow ZORI for the rent level at the subject's own ZIP, HUD FMR for the bedroom step.** Adopted Aug 30, 2026 over four alternatives scored in dollars under one CV (`scripts/anchor_probe.py`). Per metro: New York $981 → $855, Chicago $454 → $343, Los Angeles $450 → $509, overall flat — the headline hides the result, which is why per-metro reporting is now standard. Retires #16's per-ZCTA drift correction structurally: both ends read the index at the same month, so the schedule-vs-market gap divides out where it arises. Spends §6 cut-list item 6, whose stated cost was wrong in two ways (0.3% of rows lost, not 27%; FMR retained, not abandoned) |
| 20 | Stated-rent comparison | Rent & valuation | U7 → **U8** | ✅ **Disclosure, never a check.** Held Aug 30, 2026 on measurement rather than on the expired reason it had been held on before. U7.5 declined to promote it because the stated-versus-modelled gap was a constant ~−29% — an artifact of anchoring to a 40th-percentile schedule — and #19 removed that offset, leaving a dispersed, sign-varying distribution (13 fixtures, mean −11.4%, range −39.4% to +66.6%) that genuinely describes each deal. It stays a disclosure anyway: every fixture a 20–35% threshold would fire on **already carries a flag naming a more specific cause** — 6 of 6 at 25% — so the emphasis would restate an existing disclosure in vaguer words and attribute it to the listing's stated rent. `RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD` stays `None` and is **not** deleted, because the option is now foreclosed by evidence rather than by arithmetic. Reproduce with `scripts/stated_rent_gap.py` |
| 21 | Forecast rent-growth source and the pairing premise | Forecasting | **U9** | ✅ **ADOPTED Aug 31, 2026 by the architect; builds at U9.3.** Re-source rent growth from **HUD FMR to Zillow ZORI**, FMR retained as the county-level fallback — supersedes #16's rent half by following its own architectural argument to where #19 moved the system. Closes four defects at once: the false pairing premise, U8.0's ~2pp/yr FMR overstatement, the band-estimator asymmetry (both series become monthly under one function), and the cohort-shift screen that existed only to mask HUD's administrative step-ups. **The premise it retires was measured, not assumed**: `scripts/growth_correlation.py` gives pooled **r = −0.317** on FMR, **−0.197** once the two national step-up years are removed, and **+0.222** on market rent — the sign is a property of the rent series, not the market, and r² never exceeds 0.10. Full reasoning and the four defects in [`design/evaluator.md`](design/evaluator.md) |


---

## 8. Engineering Standards

**→ [`design/engineering_standards.md`](design/engineering_standards.md).**

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**→ [`design/hud_fmr_client.md`](design/hud_fmr_client.md).**
