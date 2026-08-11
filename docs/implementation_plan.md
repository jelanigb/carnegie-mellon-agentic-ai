# Multi-Family Residential Deal Evaluator — Implementation Plan

**Technical plan of record.**
Author: Jelani Gould-Bailey · Last updated: Aug 10, 2026

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
| **U3** | Extractor: real LLM call, Pydantic validate→retry loop, clarifying questions, assumption flags, bounded escalation; 3 synthetic listings | 2.1 evidence |
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
2. **LLM rent fallback path** — document as designed-but-unbuilt; Checkpoint 2.1
   already anticipated this exact trade.
3. **Streamlit app** — fall back to a terminal recording plus LangSmith traces.
4. **Critic rework-loop depth** — reduce to single-pass review with escalation,
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
| 4 | Training metro shortlist (~5–8, superset of the trio) | ⬜ `county_crosswalk.py` now covers 29 cities (every ≥500-listing pair); final selection pending |
| 5 | X / Y / Z loop parameters | ✅ X=2.0 mi, Y=8, Z=4 — tuned in U4 against measured density curves; rationale in `config.py` |
| 6 | Confidence threshold for human-review escalation | ⬜ provisional 0.60 set; tune in U7. **U2 added a second, independent escalation ground** — any critical flag escalates regardless of score (see §6, finding 1); confirm rather than re-derive |
| 7 | Redfin minimum-price floor | ✅ $10,000, with evidence (§2) — note it is inert for all three inference metros |
| 8 | OpenRouter model per role (dev / extraction / critic / summarizer) | ⬜ **placeholders confirmed dead (Aug 9)** — see below; still deferrable to U3 |
| 9 | Planner topology — pre-flight vs. supervisor | ✅ **pre-flight + rework re-entry** (Aug 9, 2026); built and topology-asserted in U2 |
| 10 | **Geocoding source** — how `DealTerms.latitude/longitude` get derived | ⬜ **opened Aug 10, 2026 in U2.** Blocks U3 |

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

U1, U4, and U2 are complete. What remains, in the order it is needed:

1. **LangSmith account** — create it and set `LANGSMITH_TRACING=true` and
   `LANGSMITH_API_KEY`. **No longer a blocker on building**, since U2's wiring is
   env-driven and the graph runs without it (`tools/tracing.py`, which prints on every
   run whether tracing is on). It *is* a blocker on the trace evidence Checkpoint 5.1
   wants, and traces expire after 14 days on the free tier, so it should be set up
   before U3 rather than before the write-up.
2. **Decision #8** — model IDs. Placeholders confirmed dead (see the decision #8 detail
   above); deliberately deferred to U3, which it blocks.
3. **Decision #10** — geocoding source. Opened in U2 (detail above); blocks U3, since a
   real extractor producing text-only geography still cannot retrieve comps without it.
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
`tests/test_flag_propagation.py` (14 cases, all passing).

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
