# Multi-Family Residential Deal Evaluator — Implementation Plan

**Technical plan of record.**
Author: Jelani Gould-Bailey · Last updated: Aug 15, 2026

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
decision is recorded here *with its reasoning*, and every assumption is labeled as an
assumption until it has been checked against data. §2 contains a worked example of the
second — a metro-selection hypothesis I held confidently, tested, and found to be
wrong.

> **Aug 8, 2026 — major revision.** Three changes. (1) **Sequencing is now driven by
> dependency and risk rather than the syllabus calendar.** The program's weekly
> checkpoints assess a written design update alongside a working agent update; they do
> not require that a given capability be built only in the week its module is taught.
> Ordering the build by dependency and technical risk is therefore both permitted and
> better engineering — see §6. (2) **LangGraph is adopted immediately** rather than
> migrated to later; the earlier staged plan existed only to track the syllabus, and
> with that constraint gone it would have meant building the orchestration layer twice
> (§3). (3) §2's metro hypothesis was tested against both datasets and replaced.

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

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

**Moved to [`docs/data_strategy.md`](data_strategy.md).**

---

## 3. Stack Decision: LangGraph from day one

**Moved to [`docs/architecture.md`](architecture.md).**

---

## 4. Proposed Repository Structure

**Moved to [`docs/architecture.md`](architecture.md).**

---

## 5. State Schema (design target for `state.py`)

**Moved to [`docs/state_schema.md`](state_schema.md).**

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
review capacity on re-establishing context. The decisions log in §7 exists to close
those out early.

### The units

**Resequenced Aug 8, 2026 — U4 pulled ahead of U2/U3.** Checkpoint 3.1 fell due before
the original Week 5 slot for retrieval. U4 turned out not to depend on either the
walking skeleton or the Extractor: it needs `state.py` and `config.py` (both U1), a
subject property can be constructed directly as a `DealTerms` object rather than
extracted from listing text, and a node function is callable with or without a graph
around it. This is the payoff of freezing the interface contract in U1 — with schema and
node signatures fixed, units can land in any order. Note the distinction being relied on:
U1 is the *interface* risk and had to come first; U2 is *integration* risk, which is
safe to defer.

| Unit | Build target | Feeds checkpoint |
| --- | --- | --- |
| **Week 4 — Foundation** | | |
| **U1** ✅ | `state.py` (Pydantic + reducers), `config.py`, `nodes.py`, `llm_client.py` (schema-validated retry), `kaggle_data.py`, `county_crosswalk.py` (29 entries, HUD-verified), `redfin_data.py`; FMR pull for the trio × {2019, latest} | — |
| **U4** ✅ | Comps/Retrieval: Chroma index (3,880 listings), one document per listing, hybrid metadata-filter + embedding query, top-`Y` results, adaptive relaxation loop, sparse-comps flag; **two ablations** — retrieval-off config flag and ungrounded-LLM comparison; X/Y/Z tuned against measured density | **3.1** |
| **U2** ✅ | **Walking skeleton.** 8 nodes wired in `graph.py` on the pre-flight Planner topology (decision #9) incl. the single Critic→Planner back edge and the `human_review` interrupt; Planner and Summarizer built for real; flag propagation proven end-to-end by a 14-case suite; diagram generated from the compiled graph *and* asserting the topology; LangSmith wiring env-driven | **5.1** (fully) |
| **Week 5 — Input** | | |
| **U3** ✅ | Extractor: real LLM call, Pydantic validate→retry loop, clarifying questions, assumption flags, bounded escalation; 3 synthetic listings. Also wires geocoding into the pipeline (decision #10's remaining half), adds the model liveness check, and takes the flag-propagation suite to 24 hermetic cases | 2.1 evidence |
| **Week 6 — Estimation & Forecast** | | |
| **U5** | Rent model: FMR-normalized regression, holdout MAE, Valuation agent, LLM fallback path + `rent_anchored_to_fmr` / `fmr_unavailable_for_county` flags | — |
| **U6** | Scenario/Forecast: `redfin_data.py` (rolling-3, min-price floor), ToT branching over optimistic/base/pessimistic, `anomalous_period_included` flag | **4.1** |
| **Buffer week — Guardrails, Eval, Demo** | | |
| **U7** | Critic: cross-agent consistency checks, confidence scoring, bounded rework cycle, human-review escalation via `interrupt()` | **6.1** |
| **U8** | Eval harness: 8–10 synthetic listings each engineered to trip a *specific* flag, **plus the New York sparse-comps case run against real data** (see §2); batch runner → results table | **6.1** + report |
| **U9** | Summarizer polish + Streamlit demo app | report + video |
| **U10** | End-to-end runs across all three metros; capture traces, screenshots, diagrams | report + video |
| **Week 7 — Deliverables** | | |
| — | **Code frozen.** Final report + 8–10 min video. | **7.1** |

### Notes on the sequence

**Multi-agent coordination is working by Week 4 rather than Week 6.** This is the
direct payoff of ordering by dependency: the coordination design gets described from a
running graph and real traces rather than from a design sketch. Each weekly checkpoint
asks for a written design update alongside a working agent update, so building the
capability before writing about it improves both halves of the submission.

**Retrieval design decisions (U4).** Each rental listing is embedded as a **single
document, not chunked.** Listings are short, self-contained records whose fields are
mutually dependent — splitting one would separate a rent figure from the bed/bath/sqft
context that makes it interpretable, and could surface half a comparable as a match.
Chunking earns its keep on long documents with independent sections; this corpus has
neither property. Structured fields (beds, baths, sqft, geography) are carried as
metadata for hard filtering; the embedded text covers description and amenity free-text,
where semantic similarity adds signal over exact matching. **Result count is `Y` from
`config.py`** — the retrieval loop's exit condition is "at least Y qualifying comps,"
which makes the number of retrieved results a tuned parameter rather than an arbitrary
constant.

**U4 acceptance criteria.** The retrieval checkpoint is assessed against five specific
elements, so U4 is specified to produce each one as an artifact rather than leaving them
to be written up after the fact:

| Required element | Where U4 produces it |
| --- | --- |
| Architectural decision on whether retrieval is required, with justification | §2 of Checkpoint 2.1 already argues this: the failure mode being defended against is fabricated comps presented at full confidence. Restated with the built system as evidence. |
| Evidence a semantic retrieval mechanism is integrated against an external source | Chroma index over the Kaggle corpus; index build script + row counts per metro |
| Demonstration that retrieval meaningfully influences output | **Two ablations — see below.** `retrieval_ablation_llm.py` (ungrounded LLM vs. grounded, primary) and the `RETRIEVAL_ENABLED` config flag in `retrieval_evidence.py` (secondary) |
| Key design decisions: source selection, segmentation/chunking, number of results | The paragraph above: one-document-per-listing, hybrid metadata + embedding, top-`Y` |
| One retrieval failure mode + how the design manages it | Sparse comps in thin sub-markets → adaptive relaxation loop, bounded by `Z` iterations, with `relaxed_search_radius` and sparse-comps flags disclosed in the report |

**The ablation falls out of the walking skeleton for free.** U2 leaves a stubbed
retrieval node in place; U4 replaces it. Running the same listing through both versions
produces a direct before/after comparison on identical inputs, which is the "output
comparison" the criteria ask for. Keep the stub reachable behind a config flag
(`RETRIEVAL_ENABLED`) rather than deleting it in U4; it costs nothing. LangSmith traces
of both runs supply the same evidence in a second form.

> **Revised Aug 9, 2026 — the config-flag ablation is necessary but not sufficient, and
> a second one was built.** The paragraph above called it "the cleanest available
> evidence that retrieval changes system behavior." That claim was too strong, and the
> gap is worth recording because it is the same class of error this system exists to
> prevent.
>
> Setting `RETRIEVAL_ENABLED=False` makes the retrieval node return zero comps and raise
> a CRITICAL flag, so the pipeline degrades to *no estimate available*. That is an
> **absence**, not the failure Checkpoint 2.1 actually named — "fabricated grounding
> presented at full confidence." It cannot produce a fabrication, because there is no LLM
> anywhere in the retrieval path: `comps_retrieval.py` is Chroma plus arithmetic. So the
> flag ablation proves retrieval is load-bearing while leaving 2.1's central claim as an
> inherited argument rather than an observation.
>
> `scripts/retrieval_ablation_llm.py` closes that. Two free-tier models of different
> sizes are asked for comps for the Case A subject with no corpus access, filling a schema
> mirroring `state.Comp`'s citable fields. Results: **0 of 16 returned comps exist in the
> evidence base**, one address (`5678 Echo Park Ave`) was disproved against public mapping
> data — not a vacant lot but an invalid *range*, since that street tops out in the
> 2300s–2400s — and rent dispersion collapsed from CV 19.7% (retrieved) to 3.1% / 4.3%
> (invented).
> The larger model was the only one reporting *high* confidence, on an evidentiary basis
> identical to the smaller one's — zero checkable comps either way.
>
> **Two methodological corrections came out of building it, both worth carrying forward.**
>
> 1. **A verification that cannot fail is not a verification.** The corpus lookup was
>    initially presented as proof of fabrication. It is not: corpus ids are uniformly
>    10-digit numerals while the models returned `LA001` and `ECHO12345`, so *zero of
>    sixteen could have matched on format alone*. The null result was structural rather
>    than earned. The script now reports `id_format_matches_corpus` alongside the lookup
>    so the limitation is visible in the output. Address cross-checking is no substitute —
>    the corpus `address` column is ~95% null for Los Angeles. What actually establishes
>    invention is convergent, and the strongest strand came from a *manual* check no code
>    in this repo could have performed: the disproved address is invalid by range, and
>    5678 is the second element of the `1234 / 5678 / 9101` sequence both models emitted —
>    so the street number came from a counting template rather than from the street.
>    Alongside that: no resolvable citation (brand names, no URLs), identically templated
>    ids, and the dispersion collapse. **Any future evidence artifact must state what its
>    check could have returned had the system been behaving well** — and note that the
>    decisive check here was external, which is an argument for keeping a human
>    verification step in the U8 harness rather than automating it away.
> 2. **Point estimates across grounded and ungrounded runs are not comparable, and the
>    reason is a U5 dependency.** The prompt specifies no time period, so model estimates
>    are undated, while the grounded figure is a raw similarity-weighted mean over the
>    2018–19 corpus with no FMR anchoring. Any percentage gap conflates fabrication error
>    with vintage mismatch. Coefficient of variation is used instead, being a within-set
>    measure and therefore vintage-independent. **This is a concrete instance of the §2
>    rent-anchoring design being load-bearing:** once U5 anchors comp-derived rents to
>    current-dollar FMR, this comparison becomes meaningful and should be revisited.

### U2 — what the walking skeleton found (Aug 10, 2026)

The graph runs end to end on five paths, all reproducible from `main.py`. The three
density cases are the same subjects `scripts/retrieval_evidence.py` measures, reused so
skeleton behaviour is comparable against the U4 retrieval evidence rather than against a
separate set of inputs:

| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | 1.00 | **0** | reports normally |
| `chicago` | 8 | 0.85 | 2 (1 info, 1 warn) | reports normally |
| `staten-island` | 0 | 0.30 | 5 (incl. 1 critical) | pauses at `human_review` |
| `no-coords` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |
| `chicago --no-retrieval` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |

The Los Angeles row carries the same weight it does in §2: a clean run raising *no*
flags, escalating nothing, is what establishes that the other four rows mean something.

**Re-measured Aug 16, 2026, with the real Extractor (U3).** The stub is gone, coordinates
are geocoded from each listing's own address rather than supplied, and every run makes a
live model call:

| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | 1.00 | **0** | reports normally |
| `chicago` | 8 | 0.85 | 2 | reports normally |
| `staten-island` | 0 | 0.30 | 5 (incl. 1 critical) | pauses at `human_review` |
| `no-geography` | 0 | 0.20 | 3 (incl. 2 critical) | pauses at `human_review` |
| `coord-conflict` | 8 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |
| `chicago --no-retrieval` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |

Three things in this table are worth more than the numbers.

**The clean Los Angeles run survived the transition**, which was not a given: U3 nearly
lost it. An invented street address resolves to no parcel, falls back to the city
centroid, and raises a warn flag — so every demo run would have carried a disclosure and
this row would have stopped being a baseline. Moving the demo listings onto real
addresses (invented deal terms, real streets) is what preserved it.

**Staten Island still finds zero comps**, for the reason it always did. That was the
other transition risk: the corpus centroid for Staten Island sits 7.55 mi from
Tottenville, in a denser part of the island, so a centroid fallback would have quietly
turned the thin-market case into a different market. The real address keeps the case
measuring what §2 says it measures.

**`coord-conflict` escalates at confidence 0.60 — exactly the boundary** where U2's
escalation defect lived. It escalates on the critical-flag rule rather than on the score,
which is the independent guarantee finding 1 established, now exercised by a case that
arrives at that number honestly instead of by construction.

**Three findings, each of which changed the build.**

**1. A single critical flag did not escalate. Fixed.** One critical flag costs 0.40
against the provisional weights, putting confidence at exactly 0.60 — and
`0.60 < 0.60` is false, so the `no-coords` and `--no-retrieval` runs reported a deal
with zero comparables as an ordinary result. The report defines critical as *"the
estimate below should not be relied on without addressing this"*, so the system was
contradicting its own stated meaning. The Critic now escalates on either ground
independently: below-threshold confidence, **or** any critical flag. Keeping them
separate is deliberate rather than a stopgap — it makes the guarantee independent of
weights that U7 is still going to change. Decision #6 should confirm it, not re-derive
it. Regression test included, and written to assert the guarantee rather than the
arithmetic that currently produces it.

This is the boundary-condition class of defect that only surfaces by running the thing.
It was invisible to the tests as first written, because those exercised the two paths
that were obviously interesting (clean run, floor-collapse run) and not the one sitting
exactly on the threshold.

**2. "Exactly one cycle" is not a checkable property. "Exactly one back edge" is.** The
diagram exporter verifies decision #9's topology rather than only illustrating it, and
its first version failed against a correct graph — reporting two cycles where the design
permits one. Both were real simple cycles (`planner → extractor → … → critic → planner`
and `planner → comps → … → critic → planner`), traversing the same single
`critic → planner` back edge. Simple-cycle count grows combinatorially with every legal
skip branch, so it was measuring branch count while claiming to measure loop count. One
back edge is one place the graph can loop, whatever the number of routes into it; the
check and the onboarding checklist both now say back edge. The wording in the original
decision was ambiguous rather than wrong, but an ambiguous invariant cannot be asserted,
and this one is now asserted on every export.

**3. Nothing in this system derives latitude/longitude** — raised as decision #10 rather
than resolved at implementation time, per §8. §5 lists the coordinates as DERIVED "by
lookup" and no lookup exists: the crosswalk resolves county only, and the evidence
scripts hardcode real coordinates for their synthetic subjects. `vector_store.query_comps`
hard-requires coordinates, so a subject without them retrieves nothing regardless of how
good the extraction was. `--deal no-coords` runs the dense Los Angeles deal with them
withheld, so what the gap costs is demonstrated rather than described.

**Decisions taken during the build**, recorded here because each is the kind that is
cheap to make deliberately and expensive to unwind:

- **The Planner is built, not stubbed.** §6 listed all seven agents as stubs, but the
  Planner has no later unit assigned — and needs none. Decision #9 established that it
  never chooses an ordering, so its whole job is deterministic: which optional steps to
  skip, rework routing, escalation. There is nothing for an LLM to decide, which is also
  why U2 could land with decision #8 still open.
- **The Valuation stub deliberately produces no number.** The obvious placeholder —
  average the comps and call it an estimate — would violate the §8 invariant that no
  unanchored Kaggle dollar figure reaches the Summarizer. A comps mean over a 2018–19
  corpus is a 2018 number in a 2026 report wearing no date, which is precisely what §2's
  anchoring design exists to prevent. A stub is not a license to breach an invariant the
  rest of the system is built around. The visible consequence — the report saying the
  valuation is unbuilt — is a true statement, where a placeholder number would have been
  a false one.
- **`_consistency_objections()` exists as a real function returning an empty list**,
  rather than being omitted until U7. It keeps the rework branch present, reachable, and
  testable at a single substitution point, which is how the cycle is proven bounded now
  rather than in U7.
- **The rework counter increments on Planner re-entry, not on Critic rejection.** The two
  are not equivalent: a rejection that escalates straight to a human is not a rework, and
  counting it as one would silently shorten the budget.
- **Confidence excludes the Critic's own derived flags.** A rework pass re-runs the
  Critic, the reducer appends its previous `low_confidence_estimate` flag, and counting
  that would let the score drive itself down on each lap of a cycle that exists to
  improve the deal. Latent today (nothing triggers rework yet) and cheaper to prevent
  than to diagnose later.
- **A reviewed deal keeps `status="needs_review"`.** Overwriting it at the Summarizer
  would erase the difference between "the system was confident" and "a human signed off".

**Two things worth knowing for review.** LangGraph 1.x warns on every custom type it
deserializes from a checkpoint without an explicit allowlist — *"this will be blocked in
a future version"* — so the paused-and-resumed path was on a deprecation clock and the
warnings buried the interrupt payload. `graph.state_serde()` registers the six state
types that cross that boundary, which is also the safer posture: the default
deserializes any type a checkpoint file names. Note that the fluent
`JsonPlusSerializer().with_msgpack_allowlist(...)` silently returns `self` unchanged when
the base allowlist is the permissive default; the constructor argument is required.
Separately, the `TODO(U2)` in `hud_fmr.py` is cleared: cache writes are now atomic
(write-to-temp then rename), and the residual concurrency limitation is documented on the
class as accepted rather than left as an open item — the loss is one cache miss against a
60/minute budget.

**Still outstanding for U2's checkpoint evidence:** LangSmith. The wiring is done and
env-driven (`tools/tracing.py`), and every run prints whether tracing is on, so a run
believed to be captured and silently not captured is not a failure mode here. Traces
themselves need the account.

**U8 is the highest-leverage unit in the plan.** A set of synthetic listings each
engineered to trigger a specific named flag — missing price, 5+ bedroom unit (FMR
bedroom cap), a county with no FMR entry, a location with no qualifying comps, an
internally inconsistent listing — serves three purposes at once: it is the evaluation
results section of the final report, the guardrails evidence for the safety checkpoint,
and the clearest available demonstration that Transparent Degradation works end to end.
It is protected from the cut list for that reason.

U8 also carries the **New York sparse-comps case** (§2), which is the one degradation
scenario grounded in real market data rather than a constructed listing. Synthetic
cases prove the mechanism fires; the New York case proves it fires when reality — not
the author — supplies the gap. Both forms of evidence are worth having, and the
distinction between them is worth drawing explicitly in the report.

### Cut list, in order

If the schedule slips, shed scope in this order rather than improvising:

1. **ZIP-tier appreciation** (already deferred in §2 — keep it deferred).
2. **Public-record for-sale ground truth** (decision #11) — the county-assessor dataset
   that would let the *value* estimate be scored rather than only demonstrated. Cut
   before the LLM fallback because it is a new data source arriving late, attached to the
   one unit that must not slip. Cutting it costs a validated value estimate, not a
   working one: demo deals stay calibrated against Redfin and FMR, and the rent model
   keeps real ground truth from the held-out corpus slice. Document the gap explicitly.
3. **LLM rent fallback path** — document as designed-but-unbuilt; Checkpoint 2.1
   already anticipated this exact trade.
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

## 7. Immediate Next Actions

### Decisions log

Each of these blocks implementation downstream; they are listed in the order they are
needed. Target: all closed during Week 4.

| # | Decision | Status |
| --- | --- | --- |
| 1 | Orchestration framework | ✅ LangGraph, day one |
| 2 | Inference metro trio | ✅ Chicago, LA, Cleveland |
| 3 | Demo surface | ✅ Streamlit, local, scheduled U9 |
| 4 | Training metro shortlist (~5–8, superset of the trio) | ⬜ final selection pending. `county_crosswalk.py`'s coverage is no longer a constraint on this (Aug 15, 2026 rewrite resolves any US county from coordinates, not a hand-picked city list) — the decision now turns purely on comp density, per §2 |
| 5 | X / Y / Z loop parameters | ✅ X=2.0 mi, Y=8, Z=4 — tuned in U4 against measured density curves; rationale in `config.py` |
| 6 | Confidence threshold for human-review escalation | ⬜ provisional 0.60 set; tune in U7. **U2 added a second, independent escalation ground** — any critical flag escalates regardless of score (see §6, finding 1); confirm rather than re-derive |
| 7 | Redfin minimum-price floor | ✅ $10,000, with evidence (§2) — note it is inert for all three inference metros |
| 8 | OpenRouter model per role (dev / extraction / critic / summarizer) | ✅ **`nvidia/nemotron-3-nano-30b-a3b`, paid variant** (Aug 16, 2026) — measured over four bake-off passes; see below. Liveness now checked at launch by `verify_models_live()`. Critic and Summarizer roles hold the same value and are revisited at U7/U9, since neither makes an LLM call yet |
| 9 | Planner topology — pre-flight vs. supervisor | ✅ **pre-flight + rework re-entry** (Aug 9, 2026); built and topology-asserted in U2 |
| 10 | **Geocoding source** — how `DealTerms.latitude/longitude` get derived | ✅ **Census Geocoder + corpus-centroid fallback** (Aug 11, 2026); `tools/geocoding.py` built and verified live. Wiring into the real Extractor remains U3 — see below |
| 11 | **Grounding for demo and evaluation deal terms** | 🟨 **Half taken (Aug 16, 2026).** Demo listings are now calibrated against Redfin metro medians and HUD FMR, with `scripts/verify_demo_calibration.py` re-deriving every figure. Real for-sale ground truth via county public records is **planned, scheduled at U8, and on the cut list** — see below |

**Decision #8 detail (Aug 9, 2026).** The `TODO(U3)` in `config.py` warned that the four
model IDs were unverified placeholders. Checked against OpenRouter's live catalogue while
building `retrieval_ablation_llm.py`: **`meta-llama/llama-3.3-70b-instruct:free` no longer
exists.** The model is still listed but is paid-only, and there is now *no* free Llama
variant at all. All four placeholders are therefore dead, and U3 cannot run until this is
set.

The decision remains **deferrable to U3** and is deliberately left open. Nothing before U3
makes an LLM call — the retrieval path contains none, and `retrieval_ablation_llm.py` names
its models locally rather than reading `config.MODEL_*`. Choosing well needs real extraction
output to judge against, which does not exist yet. Verified live and responding as of
Aug 9: `openai/gpt-oss-20b:free` and `nvidia/nemotron-3-super-120b-a12b:free`;
`google/gemma-4-31b-it:free` returned a provider 429. Note the current four-way split is
structural, not a real selection — all four constants are identical.

**The durable lesson is about staleness, not selection.** A model ID that was valid when
this document was written was invalid six days later, and the failure would have surfaced
as an opaque runtime error mid-U3. Free-tier catalogues churn, so these constants should
not be treated as set-once. U3 should add a startup liveness check that fails loudly at
launch if a configured model is absent from `/api/v1/models`, rather than discovering it on
first invocation.

**Closed Aug 16, 2026 (U3) — `nvidia/nemotron-3-nano-30b-a3b`, on the paid variant.**
The route to that answer is worth more than the answer, because the first two passes
measured the wrong thing.

**Pass 3 and 4, paid variants — the comparison only became a comparison once it was paid
for.** Every candidate returned 3/3 schema-valid extractions, 23/23 hand-checked fields,
correct assumption verdicts on all three listings, and **zero 429s**, with no model ever
needing a schema retry. Correctness ties completely, so the remaining signals are latency
and price:

| model | pass 3 | pass 4 | $/extraction |
| --- | --- | --- | --- |
| `google/gemma-4-26b-a4b-it` | 8.2s | 6.5s | 0.00034 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 13.7s | 9.3s | 0.00216 |
| **`nvidia/nemotron-3-nano-30b-a3b`** | **18.0s** | **11.3s** | **0.00015** |
| `openai/gpt-oss-20b` | 24.6s | 19.2s | 0.00009 |
| `nvidia/nemotron-3-super-120b-a12b` | 35.0s | 19.9s | 0.00027 |
| `google/gemma-4-31b-it` | 35.7s | 12.4s | 0.00028 |
| `nvidia/nemotron-3.5-lightning` | 44.7s | 32.9s | 0.00020 |

Selected on balance rather than on any single column: perfect on all four passes, the
cheapest of its family, and second-fastest overall. Two alternatives are recorded so the
choice stays reviewable rather than looking inevitable — gemma-4-26b was fastest on both
passes at 2.3× the price, and gpt-oss-20b was cheapest but slower. At $0.00015 per
extraction, roughly 6,700 extractions to the dollar, price is not the deciding axis at
this project's volume; it is recorded because a cost table nobody wrote is a cost nobody
notices later.

**One finding that outlives this decision: a free variant and a paid variant of the same
model name are not necessarily the same deployment.** `gemma-4-26b` scored a spurious
assumption on *both* free passes and on *neither* paid pass, with an identical prompt.
Whatever the cause — quantization, a different serving provider — it means a free-tier
measurement is not automatically evidence about the paid variant of the same name, and
neither is the reverse.

**This is a documented departure from the project's "prefer free tools" constraint**,
taken because the constraint's own qualifier — *where their quality is good* — is what
failed. See open item 0 below for the accounting.

**Passes 1 and 2, free variants — kept because the failure is the evidence.**
`--tier free` still reproduces them. These passes are what established that the free
tier's `:free` variants are served from provider-shared pools, so what they measured was
availability, not capability: models lost whole listings to 429s and *which* models
failed moved between passes. `openai/gpt-oss-20b:free` scored 3/3 on the first pass and
1/3 on the second; `google/gemma-4-31b-it:free` scored 0/3 then 1/3. The four
`nvidia/nemotron-3*` variants completed both passes, which is the only signal that
survived into the paid comparison.

| model | pass 1 | pass 2 | fields | assumptions | secs |
| --- | --- | --- | --- | --- | --- |
| `nvidia/nemotron-3-nano-30b-a3b:free` | 3/3 | 3/3 | 23/23 | all correct | 29.6 |
| `nvidia/nemotron-3-super-120b-a12b:free` | 3/3 | 3/3 | 23/23 | all correct | 34.6 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 3/3 | 3/3 | 23/23 | all correct | 66.0 |
| `nvidia/nemotron-3.5-lightning:free` | 3/3 | 3/3 | 23/23 | all correct | 69.8 |
| `openai/gpt-oss-20b:free` | 3/3 | **1/3 (429)** | 23/23 | all correct | 31.9 |
| `google/gemma-4-26b-a4b-it:free` | 3/3 | 3/3 | 23/23 | **1 wrong** | 54.1 |
| `google/gemma-4-31b-it:free` | **0/3 (429)** | **1/3 (429)** | — | — | — |

**Every model that completed a listing scored 23/23 on hand-checked field accuracy, at
one attempt per listing — the retry loop never fired.** So accuracy discriminates almost
nothing here, and saying so is the honest reading: per §8, a check where everything
passes is evidence about the check, not a verdict on the candidates. These listings
separate a working extractor from a broken one, not a good one from a better one. That
held on the paid passes too, which is why the decision came down to latency and price.

**Two method corrections came out of these passes**, and the bake-off carries both now.
The free-tier table confounded availability with capability — a 429 scored identically to
a malformed extraction, so `gemma-4-31b` looked incapable when it was merely queued.
`run_case` now backs off `(5, 15, 30)` seconds on rate limits only, and counts them in a
separate column, so the two are measured independently. And the bake-off runs with the
response cache **off**: it measures a provider's live behaviour, and a replayed response
would report the recording's latency as if it were today's.

The single assumption error is worth recording because of what it was. `gemma-4-26b`
flagged a *stated* unit count as an inference. The same failure appeared in the
configured model's first run and was fixed in the prompt rather than in the scoring: a
phrase carrying the number ("three-unit", "three-family", "2-flat") states it, while a
numberless type word ("duplex", "triplex") is an inference. Over-flagging is a real
defect rather than harmless caution — every assumption costs confidence and reaches the
reader as a caveat, so a system that flags everything is indistinguishable to them from
one that flags nothing, which is §2's always-on-signal argument applied to extraction.

**Decision #10 detail (opened Aug 10, 2026).** §5 lists `latitude`/`longitude` as DERIVED
"produced by lookup, never read from the listing" — and no lookup produces them. The
crosswalk resolves county FIPS only; the U4 evidence scripts hardcode real coordinates
for their synthetic subjects, which is legitimate for a measurement script and is not a
pipeline. This sat unnoticed because the one agent that needs coordinates was built by a
script that supplied them.

It matters because `vector_store.query_comps` hard-requires them: without coordinates
there is no bounding box, no radius filter, and no comps at all, whatever the extraction
quality. So this gates the entire grounded path for any listing arriving as text, which
is exactly what U3 produces. Three options, none yet chosen:

1. **A geocoding API call** (Census Geocoder is free and public; Nominatim has usage
   terms worth reading). Accurate to the parcel, adds a network dependency and a failure
   mode on the critical path.
2. **A city-centroid table** extending `county_crosswalk.py`, with a disclosed
   approximation flag. No new dependency and consistent with how the county gap was
   resolved in §2 — but a centroid is a poor subject location in a large metro, and the
   radius search is precisely where that error lands. Los Angeles is the worst case for
   it.
3. **Require coordinates on the input**, treating geocoding as out of scope and
   documenting it. Honest, and it makes the demo depend on hand-supplied data for a field
   the design calls derived.

Recommendation is (1) with (2) as the fallback path when the call fails, since that
combination degrades in exactly the way the rest of the system does — flagged, disclosed,
still producing an answer. Raised rather than resolved per §8, since it is a data-source
decision and those belong in this log.

**Closed Aug 11, 2026 — option (1)+(2) as recommended, with one change from the original
sketch.** Option 2 as written proposed "a city-centroid table extending
`county_crosswalk.py`" — a hand-curated table, mirroring how the county gap was closed.
Built instead: `city_centroid()` in `tools/geocoding.py` computes the mean lat/lon of a
city's own listings directly from the Kaggle corpus (`tools/kaggle_data.load_clean()`),
rather than a maintained constant. Two reasons this is better than the sketch, not just
different from it: it needs no hand-curation or per-city verification the way the FIPS
table does, and it is a tighter-fitted centroid than an arbitrary city-hall point — it
sits where the corpus's own comp density actually is, which is what the radius search
downstream cares about. It also covers every city the corpus has listings for rather
than only the 29-city crosswalk shortlist. `geocode_census()` (primary) and
`city_centroid()` (fallback) share one normalization path with the county crosswalk —
`county_crosswalk.normalize_city/normalize_state`, promoted from private to public for
exactly this reuse — so the two lookups can't drift apart on how they fold the same
corpus's city names.

Verified live (`scripts/pull_geocode_sample.py`, real calls, not mocked): a complete
street address in each inference-trio metro resolves via the Census Geocoder; a
city/state pair with no street number correctly finds no Census match and falls through
to the corpus centroid; a city genuinely outside the corpus's coverage correctly resolves
to neither and returns `None` rather than inventing a coordinate. Two new flag kinds
carry the disclosure — `COORDINATES_FROM_CITY_CENTROID` (warn) and
`GEOCODING_UNAVAILABLE` (critical) — added to `state.py` alongside
`COUNTY_FROM_PRINCIPAL_COUNTY` on the same precedent: the enum member exists ahead of the
code that raises it, same as that one did in U1.

**What's still open, and it's deliberately not closed here.** The tool is built and
verified in isolation; it is not yet called from `agents/extractor.py`. Wiring it in
would resolve real addresses for `test_flag_propagation.py`'s `LISTING_MISSING_PRICE`
fixture, which currently relies on a *complete* address plus *withheld* coordinates to
exercise the Comps agent's no-coordinates short-circuit without touching Chroma. That
suite is the one thing in this project that must never fail for the wrong reason (§8), so
wiring geocoding into the stub extractor now would silently change what it tests rather
than extend it. That wiring — plus updating the fixture to a genuinely ungeocodable
address so the suite keeps testing the same guarantee on purpose — is U3 work, tracked as
the `TODO(U3)` in `extractor.py`.

**Follow-on, Aug 15, 2026 — the county crosswalk (§2, "Two data gaps," Gap 1) is
replaced by a consequence of decision #10.** Reviewing decision #10 surfaced that a
listing's `city` field is sometimes a neighborhood rather than the postal city ("Wynwood"
for Miami) — real estate marketing convention, not a parsing bug. Testing it directly
(`tools/geocoding.py`'s primary path) showed comp retrieval is unaffected — it's
coordinate-based, and Census resolves the correct point off street + ZIP regardless of
the city token supplied — but `county_crosswalk.py`'s old (city, state) string lookup
would still miss, and Census's own response carries a canonical city
(`addressComponents.city`) that was never being read back. Comparing two fixes — correct
the string before the crosswalk lookup, versus resolve county directly from the subject's
already-derived coordinates — showed the second strictly dominates the first: it doesn't
depend on the crosswalk table's coverage at all (Miami resolved correctly despite never
having a table entry), it's immune to the city-string question entirely, and it works
regardless of which geocoding tier produced the coordinate. It's also a strict accuracy
improvement even for the cities the old table did cover, since it resolves the *exact*
county for a point rather than the table's principal-county approximation for the ten
cities spanning several.

**Built.** `tools/county_crosswalk.py` is rewritten in place: `lookup_county_fips` now
takes `(latitude, longitude)` and does a point-in-polygon join against Census's county
boundary file (cached locally after the first pull) instead of a hand-maintained
29-city table. `normalize_city`/`normalize_state` are unchanged and still serve
`tools/geocoding.py`'s corpus-centroid fallback. Cost was measured, not assumed — the
original §2 text called the spatial-join scale-up path "not worth the dependency"
without testing it; `geopandas` installs in ~3.3s from prebuilt wheels at ~31MB, and the
county boundary file loads in ~3.3s and is cached after that (see `data_strategy.md`'s
Gap 1 for the full accounting). Verified live in `scripts/verify_county_geometry.py`:
reproduces all three inference-trio entityids exactly, resolves Miami-Dade correctly
where the old table had nothing, and resolves the old table's two hand-special-cased
hard cases (Richmond VA's independent-city status, Denver's consolidated city-county)
correctly with no special-case code — each cross-checked against a live HUD
`listCounties` response, not just against the geometry's own claim.

**Carried forward as future work, not solved:** HUD prices FMRs by *town*, not county,
in the six New England states, and a county polygon join cannot produce the town-level
entityid that regime needs. A resolved point landing in one of those six states now
returns `None` — declining rather than guessing, the same discipline `geocoding.py`
applies to an uncovered city — rather than emitting a plausible-looking wrong entityid.
Tagged `TODO(geography)` at the site, same status the old table already carried for New
England (verified for Boston only). Doesn't block the inference trio (none are New
England).

**One accepted narrowing, stated because it's a real behavior change, not a pure
refactor:** county resolution now runs on coordinates, so a subject with a known city but
no resolvable geocode gets no `county_fips` either, where the old table could still
resolve one from the city string alone. Given `vector_store.query_comps` already
hard-requires coordinates for comp retrieval, a coordinate-less subject was already this
system's worst case; this removes one of the two things such a subject could still get
independently, not one of the two paths that mattered independently of each other.

**Decision #11 detail (opened and half-taken Aug 16, 2026).** Raised in review of U3's
demo listings, whose deal terms — price, rents, unit mix — were invented. The literal
program requirement was satisfied (nothing scraped, nothing proprietary), but the
objection was sharper than compliance: *even synthetic examples should have some basis in
reality*, and these numbers had none recorded.

The concern is not cosmetic, because these terms are load-bearing. `bedrooms` and
`square_footage` are hard filters on comp retrieval; `price` and `unit_rents` are what U5
will value the deal from. An implausible subject produces a confident-looking report about
a property that could not exist — uncomfortably adjacent to the fabrication failure this
system exists to prevent, with the difference that the *grounding* (comps, FMR, Redfin)
stays real and only the subject is hypothetical.

**Taken now: calibrate against sources already in the repo.** Each demo figure names its
basis in `demo_deals.py`, and `scripts/verify_demo_calibration.py` re-derives it live —
asking price against Redfin's median sale price for Multi-Family (2-4 unit) in that
metro, stated rents against HUD's FY2026 FMR for the county *the listing's own address
geocodes to*, so the check exercises the real geocoding path rather than a county written
into the fixture. Behaviour across all five demo deals was unchanged by the recalibration,
which is the expected result: the figures were already roughly right, and what they
lacked was provenance rather than accuracy.

**One correction worth recording, because it is the mistake this project is about.** The
review initially appeared to show the Chicago demo's rents sitting 27% above market. It
did not: that gap was measured against the *2018-19* Kaggle corpus median while the rents
were current-dollar figures. Against FY2026 FMR for Cook County they sit within 4%. The
error was comparing two vintages — precisely what §2's FMR-anchoring design exists to
prevent — committed while arguing for better data discipline. It is also why demo rents
are anchored to FMR rather than to the corpus: the corpus is seven years stale, and
calibrating current listings against it would build the vintage gap into the demo.

**Two limits of this, stated rather than left to be discovered.** FMR is a 40th-percentile
rent, not a market median, so calibrated listings sit at the affordable end of their
market by construction — acceptable for a demo, not acceptable for an accuracy benchmark.
And there is still **no ground truth for the value estimate**: a demo deal has a defensible
asking price but no known correct answer, so U5's valuation cannot be scored the way its
rent model can.

**Planned, not taken: real for-sale deals from county public records.** Rejected
alternatives first. *Scraped listings* carry ToS exposure, go stale, and would place real
current offers in a public repository. *Real listings copied by hand* share the staleness
problem and still supply no known-correct value. **County assessor open data** (Cook, LA
County, NYC) dominates both: legally unambiguous, free, stable, and richer in exactly the
fields needed — address, sale price, unit count, square footage, year built.

Scheduled at **U8**, where evaluation evidence lands, and placed on §6's cut list at
position 2. That placement is deliberate: U8 is the one unit protected from cutting, and
attaching a new data source with its own cleaning and coverage work to it would put the
protected unit at risk. If it is cut, the rent model still has real ground truth from a
held-out slice of the Kaggle corpus — real listing text, real rents, which is also what
the Checkpoint 1.1 feedback asked for ("lock one metro and a small held-out test set
early") — and the value estimate is documented as unvalidated.

**Settled Aug 16, 2026, before the work rather than during it.** The open question was
whether this breaches the standing data rule. It does not, and §8 now says why rather
than leaving it to a judgment call at implementation time: the rule turns on "public,"
which is defined there as *openly licensed or a public record* — not *publicly visible*.
Assessor records are the first; scraped listings are only the second. So the planned work
is admissible under the standard as written, and scraping remains excluded by the same
sentence rather than by a separate prohibition.

Worth noting the rule was also relaxed from an absolute to a norm in the same pass, which
is what makes a recorded exception possible at all. That is the general pattern this log
exists for, applied to the standards document itself.

**Decision #9 detail.** The pipeline order is fixed by data dependency — Valuation consumes
`state.comps`, Scenario consumes `rent_estimate`/`value_estimate` — so the sequence
Extractor → Comps → Valuation → Scenario → Critic is not something the Planner chooses. The
open question was only where the Planner *sits*, and two topologies were considered:

- **A — pre-flight + rework re-entry. Selected.** `START → Planner`; the Planner writes a plan
  into state (which optional steps run); a mostly static chain follows, with conditional edges
  only where skipping is legal; `Critic → Planner` is the sole cycle in the graph.
- **B — supervisor hub-and-spoke.** Every specialist returns to the Planner, which re-decides
  each hop. Rejected.

B was rejected because it pays six extra Planner invocations per run — LLM calls, latency, and
non-determinism — to re-derive an ordering that was never in question, and because it puts
several cycles in the graph, which makes the Checkpoint 5.1 coordination description harder
rather than easier. Nothing is given up: the Planner's real degrees of freedom under A are
which optional steps to skip, retry/rework routing, and escalation, all expressed as
conditional edges. This is what §3 rationale item 4 already asserted — *"conditional edges are
the Planner"* — so A ratifies the stated design rather than changing it.

**Consequences for U2**, which builds `graph.py` against this:

- Exactly one cycle exists (`Critic → Planner`), bounded by `rework_count`. Any second cycle
  appearing in the generated diagram is a defect, and that makes the diagram a review
  instrument rather than only an illustration.
- The Planner node runs at most `1 + rework_count` times per deal, which is the figure the
  Checkpoint 5.1 coordination section should quote.
- Specialists have static outgoing edges except where skipping is legal, so `route_*`
  functions stay few and small — consistent with §3's "no agent calls another agent directly."

Recorded because the hand-drawn diagram in `lang_graph_onboarding.md` §4 showed B's shape (and
showed it incoherently — see the correction note there), which is how an unclosed decision
surfaced as a documentation defect rather than as a question. Per §8, decisions of this kind
get raised rather than resolved by assumption at implementation time; this one was.

Each weekly checkpoint publishes explicit completion criteria. Where those exist, the
corresponding unit is specified to produce each required element as a build artifact
rather than as a write-up authored afterward — see the U4 acceptance criteria in §6 for
the pattern. Apply the same treatment to 4.1, 5.1, and 6.1 as their criteria are
published.

### Open items

U1, U4, U2, and U3 are complete. What remains, in the order it is needed:

0. ~~**Free-tier request cap**~~ — ✅ **closed Aug 16, 2026. $10 of credits purchased;
   the build now runs on paid model variants.** Kept in full because the reasoning is a
   budget decision the project constraints speak to directly.

   The free tier is 50 model requests per day, account-wide. Measured, not read off a
   docs page: three bake-off passes plus development exhausted it, and the header
   confirms it (`X-RateLimit-Limit: 50`, `limit_source: openrouter_free_tier_daily`).
   OpenRouter raises this to 1,000/day for $10 in credits — 10% of the project's $100
   ceiling.

   It bites hardest on **U8**, whose whole design is a batch of 8–10 listings run
   repeatedly until the flag coverage is right, and on the Week 7 demo, which must
   produce output on demand.

   **Resolved: move to paid inference, and build the cache anyway.** Two findings
   settled it. First, the daily cap is only one of *two* rate limits — the errors
   distinguish `openrouter_free_tier_daily` (the account's 50/day, which credits raise to
   1,000) from `upstream_provider_shared_pool` (a provider-side pool shared across all
   free users of a `:free` variant, which credits do not address). Only paid variants
   clear both, which is what made the model bake-off a fair comparison rather than a
   measurement of who was queued behind whom — **passes 3 and 4 recorded zero 429s across
   all seven candidates, against repeated losses on the free tier.** Second, the cost is
   not close to material: at $0.00015 per extraction on the selected model, the entire
   remaining build — development, eval batches, demo runs — is measured in dimes.

   **On the "prefer free tools" constraint**, which this departs from: the constraint's
   qualifier is *where their quality is good*, and the free tier failed exactly there.
   Not on model quality — the same models are available either way — but on the
   reproducibility of any measurement taken through it. Two passes could not agree on
   which models worked, and one model behaved differently on its free and paid variants
   with an identical prompt. A tier that cannot support a repeatable measurement is not
   a cheaper version of the same thing.

   The cache landed regardless, because its justification was never really quota.
   Measured: **0.06 ms for a cache hit against 9.9–23 s for a live call.** It is a
   development-latency mechanism first and a reproducibility mechanism second — an
   evaluation whose inputs are re-sampled from a stochastic endpoint on each run cannot
   show that a change in results came from a change in this system. See
   `src/eval/README.md` for the two-tier case design that follows from it.

   Worth noting what already worked: the cap was hit accidentally, and the system
   degraded correctly rather than crashing (critical flag, escalation, full report). That
   was not free — it took the `LlmError` conversion in `tools/llm_client.py`, which the
   accidental outage is what exposed.

   Worth noting what already works: the cap was hit accidentally, and the system degraded
   correctly rather than crashing (critical flag, escalation, full report). That was not
   free — it took the `LlmError` conversion in `tools/llm_client.py`, which the
   accidental outage is what exposed.

1. **LangSmith account** — create it and set `LANGSMITH_TRACING=true` and
   `LANGSMITH_API_KEY`. **No longer a blocker on building**, since U2's wiring is
   env-driven and the graph runs without it (`tools/tracing.py`, which prints on every
   run whether tracing is on). It *is* a blocker on the trace evidence Checkpoint 5.1
   wants, and traces expire after 14 days on the free tier, so it should be set up
   before U3 rather than before the write-up.
2. ~~**Decision #8**~~ — ✅ **closed Aug 16, 2026.** `nvidia/nemotron-3-nano-30b-a3b`
   on the paid variant, measured across four bake-off passes; detail above. Revisit the
   Critic and Summarizer roles at U7/U9, when they first make calls of their own.
3. ~~**Decision #10**~~ — ✅ **fully closed Aug 16, 2026.** Source chosen and built
   Aug 11 (`tools/geocoding.py`); wired into the Extractor in U3. The paired fixture
   update was resolved differently than specified: stubbing the Extractor's outbound
   calls makes the fixture's address text inert, so moving it to an ungeocodable address
   became unnecessary rather than done. Recorded because a plan item closed by being
   obviated is easy to mistake later for one quietly skipped.
4. **Decision #4** — finalize the training shortlist from the 29 crosswalk entries.
   Blocks U5.
5. ~~**OpenRouter API key**~~ — ✅ **closed Aug 9, 2026.** Stored at `ignore/openrouter_key`
   (gitignored); `llm_client._load_token()` reads `OPENROUTER_API_KEY` first and falls back
   to that file. Verified by live calls in `retrieval_ablation_llm.py`.

Built and verified against real data, requiring no rework: `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py` (§9), `scripts/verify_metro_selection.py`,
`tools/kaggle_data.py`, `tools/county_crosswalk.py`, `tools/redfin_data.py`,
`tools/vector_store.py`, `agents/comps_retrieval.py`, `scripts/build_comps_index.py`,
`scripts/retrieval_evidence.py`, and `scripts/retrieval_ablation_llm.py` (the last also
being the first live exercise of `tools/llm_client.py` — `call_with_schema`'s retry loop
fired for real, one model needing two attempts to produce schema-valid output). Added and
verified in U2: `graph.py`, `main.py`, `agents/planner.py`, `agents/summarizer.py`,
`agents/human_review.py`, `tools/tracing.py`, `scripts/export_graph_diagram.py`, and
`tests/test_flag_propagation.py` (14 cases, all passing). Added and verified Aug 11,
2026 (decision #10): `tools/geocoding.py` and `scripts/pull_geocode_sample.py` — not yet
called from the pipeline; see decision #10's closing detail above. Rewritten and
verified Aug 15, 2026 (decision #10 follow-on): `tools/county_crosswalk.py` (now a
point-in-polygon join, replacing the hand-maintained table) and
`scripts/verify_county_geometry.py` — this one *is* called from the pipeline
(`agents/extractor.py`), unlike geocoding itself. Added and verified in U3:
`agents/extractor.py` (real, no longer a stub — `tools/geocoding.py` is now called from
the pipeline too), `scripts/extraction_evidence.py`, `verify_models_live()` in
`tools/llm_client.py`, and `tests/test_flag_propagation.py` at 24 cases. Verified against
live services throughout — including, unplanned, the whole pipeline under a real provider
outage.

### Prerequisite reading (before U2 review)

Ramp up on LangGraph (roughly
3 hours). This sits on the critical path: the review standard applied to Weeks 4–6 is
only as good as the reviewer's fluency in the framework, and §6 of that document is the
checklist applied to every unit.

---

## 8. Engineering Standards

**Moved to [`docs/engineering_standards.md`](engineering_standards.md).**

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**Moved to [`docs/hud_fmr_client.md`](hud_fmr_client.md).**
