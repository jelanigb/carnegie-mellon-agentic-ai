**Part of the plan of record — see [`implementation_plan.md`](implementation_plan.md) §§3–4.**

## 3. Stack Decision: LangGraph from day one

### Section Links

- [§1](implementation_plan.md#1-project-summary)
- [§2](implementation_plan.md#2-data-strategy-reconciling-kaggleredfin-vintage-and-category-mismatch)
- [§3](implementation_plan.md#3-stack-decision-langgraph-from-day-one)
- [§4](implementation_plan.md#4-proposed-repository-structure)
- [§5](implementation_plan.md#5-state-schema-design-target-for-statepy)
- [§6](implementation_plan.md#6-execution-order)
- [§7](implementation_plan.md#7-immediate-next-actions)
- [§8](implementation_plan.md#8-engineering-standards)
- [§9](implementation_plan.md#9-current-build-hud-fmr-api-client-toolshud_fmrpy)

**Revised (Aug 8, 2026).** This section previously specified plain Python now with a
LangGraph migration staged for Week 6. That staging existed to keep the build aligned
with the order the syllabus introduced concepts. Once sequencing was freed to follow
dependency and risk instead (see the revision note at the top), the staged approach
became strictly dominated: it is the only available option that requires building the
orchestration layer twice, and it spends the scarcest resource on the project —
review-and-integration time — on a rewrite that produces no new capability.

**Decision: adopt LangGraph immediately; the plain-Python orchestration layer is not
built at all.** The four design conventions written to make the migration cheap (below)
were good conventions independent of the migration, so they survive intact — LangGraph
now enforces most of them structurally rather than by discipline.

### The stack

| Layer | Choice | Why |
| --- | --- | --- |
| Orchestration | **LangGraph** — `StateGraph`, conditional edges, checkpointer | See below |
| State schema | **Pydantic v2** (not dataclasses) | `ValidationError` text feeds the Extractor's retry prompt; dataclasses give nothing there |
| LLM calls | OpenRouter via the OpenAI-compatible SDK — **paid variants since Aug 16, 2026** (decision #8) | Free variants proved unmeasurable, not merely slow; see the cost note below |
| Observability | **LangSmith** free Developer tier | Multi-step agent loops are impractical to debug from logs alone; traces also document actual system behavior |
| Retrieval / RAG | `sentence-transformers` (local) + `ChromaDB`, **hybrid**: metadata filters for hard constraints, embeddings for description/amenity text | Free, local, and a more honest design than pure vector search over structured data |
| Regression | `pandas` + `numpy` + `scikit-learn` | Existing strength; lowest-surprise component |
| State persistence | LangGraph checkpointer (SQLite) | Comes with the framework; also enables `interrupt()` |
| Demo surface | **Streamlit**, run locally | ~50 lines; far better on video than a terminal recording |
| Dev environment | VS Code + Claude Code | — |

**Total cost: $10, and the contingency became the plan (Aug 16, 2026).** Streamlit is
open-source and free to run locally; Community Cloud is only relevant for public hosting,
which this project does not require — the demo app stays local. LangGraph is MIT-licensed.
LangSmith's free tier covers a solo developer's usage. HUD, Redfin, Kaggle, and the Census
geocoder are all free and remain so.

The one exception is model access. This section originally called ~$10–20 of OpenRouter
credits a contingency *"if free-tier rate limits become a real time sink."* They did, and
for a sharper reason than time: the free tier's `:free` variants are served from
provider-shared pools, so measurements taken through it were not reproducible. Two
bake-off passes disagreed about which models worked, a third was blocked entirely by an
account-wide 50-requests-per-day cap, and one model behaved differently on its free and
paid variants given an identical prompt. The capstone brief's *"freely available model
access"* is satisfiable on quality — the same models are available either way — but not
on the ability to measure anything about them.

**$10 spent of the $100 budget**, which buys 1,000 free-model requests per day and access
to paid variants at roughly **$0.00015 per extraction** — about 6,700 extractions to the
dollar. The full remaining build is expected to cost cents, not dollars. Decision #8 in
§7 carries the measurements; `tools/llm_cache.py` reduces repeat spend and, more usefully,
makes evaluation runs reproducible.

> ⚠️ **LangSmith free-tier traces expire after 14 days.** Capture screenshots for the
> report as you go; do not assume Week 4 traces will still be viewable in Week 7.

### Rationale

1. **Reducers make Transparent Degradation structural rather than disciplinary.**
   Declaring `flags: Annotated[list[Flag], operator.add]` means a node returning flags
   *appends* rather than overwrites. Flag loss — the failure that would defeat this
   project's central design principle — becomes impossible by construction rather than
   a convention upheld in code review. This is the strongest single argument for the
   framework on this project: the architecture and the tool agree on what must never
   happen, and the tool enforces it.
2. **`interrupt()` is the human-review escalation.** The system needs to pause, surface
   partial state to a human, and resume from that point. That is a first-class
   LangGraph primitive and a genuinely error-prone thing to hand-roll correctly.
3. **The architecture diagram is generated from the graph.**
   `graph.get_graph().draw_mermaid_png()` renders the real topology from the real code,
   so documentation cannot silently drift from the system it describes.
4. **Conditional edges are the Planner.** Routing across seven agents plus a bounded
   Critic → Planner rework cycle is precisely the shape the library exists to express.

**Trade-off accepted:** a framework dependency and its learning curve, on a project
with a fixed deadline. Mitigated by training on LangGraph up front and by keeping all agent logic in plain
functions that hold no framework-specific code — if LangGraph became a liability, the
nodes would port to a hand-rolled loop without touching the reasoning logic.

### Design conventions

- Every agent is a **node function**: state in, **partial state update** out. Note
  *partial* — returning the whole mutated state object is the most common LangGraph
  error.
- **No agent calls another agent directly.** Routing lives in edges and `route_*`
  functions, never inside a specialist.
- **State is a single typed object** (§5), never scattered across variables.
- **Flags and retries are state-encoded, not control-flow-encoded.** Conditional edges
  read state to route; anything outside state is invisible to the graph.

New addition: **every cycle must be bounded by an explicit counter in state**, not by
LangGraph's `recursion_limit`. Hitting the limit raises an opaque exception; a counter
lets the system escalate to human review gracefully, which is the behavior Checkpoint
2.1 actually specified.


---

## 4. Proposed Repository Structure

**Note:** Paths in the rest of this doc that reference `tools/`, `agents/`, `config.py`, etc. are relative to `src/`.

```
carnegie_mellon_agentic_repo/
├── data/                          # gitignored — Kaggle CSV, Redfin CSVs, cached HUD FMR responses
│   ├── raw/
│   └── processed/
├── docs/
│   ├── implementation_plan.md     # this file — the reasoning record
│   ├── changelog.md               # ✅ the chronological record: what code landed when (§8)
│   └── diagrams/                  # ✅ generated from the compiled graph, not drawn
└── src/                           # project root for all application code
    ├── README.md
    ├── requirements.txt
    ├── .venv/                     # gitignored — dedicated virtualenv
    ├── config.py                  # ✅ X/Y/Z loop parameters, model names, thresholds
    ├── state.py                   # ✅ DealState / Flag / DealTerms / Comp — Pydantic (§5)
    ├── graph.py                   # ✅ StateGraph assembly: nodes, edges, routing, compile()
    ├── nodes.py                   # ✅ node-name string constants (avoids silent typo bugs)
    ├── agents/
    │   ├── __init__.py
    │   ├── planner.py             # ✅ pre-flight plan + every route_* function
    │   ├── extractor.py           # ✅ schema-validated LLM call + geocoding + county
    │   ├── comps_retrieval.py     # ✅ adaptive relaxation loop
    │   ├── valuation_rent.py      # ⬜ stub; U5
    │   ├── scenario_forecast.py   # ⬜ stub; U6
    │   ├── critic.py              # ◐ confidence + escalation built; consistency checks U7
    │   ├── summarizer.py          # ✅ real markdown, disclosure-first; polish in U9
    │   └── human_review.py        # ✅ the interrupt() escalation node
    ├── tools/
    │   ├── __init__.py
    │   ├── llm_client.py          # ✅ OpenRouter wrapper + schema-validated retry loop + cache
    │   ├── llm_cache.py           # ✅ on-disk response cache; off / read_write / replay
    │   ├── diagnostics.py         # ✅ full error detail to stdout, kept out of the report
    │   ├── vector_store.py        # ✅ Chroma setup + embedding + hybrid query
    │   ├── kaggle_data.py         # ✅ single cleaning path: dedupe, completeness, city match
    │   ├── rent_model.py          # sklearn regression: train/load/predict (FMR-normalized target)
    │   ├── hud_fmr.py             # ✅ HUD FMR API client (§9)
    │   ├── county_crosswalk.py    # ✅ lat/lon → county_fips via point-in-polygon join (rewritten Aug 15, 2026)
    │   ├── geocoding.py           # ✅ address → lat/lon: Census primary, corpus centroid fallback
    │   ├── redfin_data.py         # ✅ load + query, rolling-3 + growth bands computed here
    │   └── tracing.py             # ✅ LangSmith project wiring; env-driven, never required
    ├── demo_deals.py              # ✅ the synthetic listings + provenance for every figure
    ├── scripts/
    │   ├── pull_fmr_sample.py     # ✅ real HUD pull smoke test
    │   ├── pull_geocode_sample.py # ✅ real Census geocoder calls: all three tiers
    │   ├── verify_county_geometry.py # ✅ point-in-polygon results cross-checked against live HUD
    │   ├── verify_metro_selection.py # ✅ reproduces the §2 metro evidence
    │   ├── extraction_evidence.py # ✅ Loop 1 behaviour + the decision #8 model bake-off
    │   ├── verify_demo_calibration.py # ✅ re-derives each demo figure from Redfin + HUD
    │   ├── build_comps_index.py   # ✅ one-off: embed + load Chroma (3,880 listings)
    │   ├── retrieval_evidence.py  # ✅ Checkpoint 3.1 evidence: 3 density cases + config-flag ablation
    │   ├── retrieval_ablation_llm.py # ✅ Checkpoint 3.1: ungrounded LLM vs. grounded retrieval
    │   ├── train_rent_model.py    # one-off: fit + report holdout MAE
    │   └── export_graph_diagram.py # ✅ generates the diagram AND asserts decision #9's topology
    ├── notebooks/
    │   └── 01_data_exploration.ipynb
    ├── eval/                      # ◐ scaffolding + README landed U3; harness itself is U8
    │   ├── README.md              # ✅ layout, the two case tiers, record/replay usage
    │   ├── data/                  # golden DealTerms fixtures + the listings they came from
    │   │   └── llm_recordings/    # recorded model responses, replayed by llm_cache
    │   ├── results/               # generated result tables (committed — the report cites them)
    │   ├── expected.yaml          # listing → expected flags / status
    │   └── run_eval.py            # batch runner → results table for the report
    ├── tests/
    │   ├── conftest.py            # ✅ puts src/ on the import path
    │   └── test_flag_propagation.py  # ✅ the one test that must never fail — 24 hermetic cases
    ├── app.py                     # Streamlit demo UI (local only)
    └── main.py                    # ✅ entrypoint: run full pipeline on one listing
```

`agents/human_review.py` was not in the original tree. It is not a specialist — it makes
no estimate and reaches no conclusion — but it *is* a node function, and putting it in
`graph.py` would have mixed a behaviour into a module that is otherwise pure wiring.

