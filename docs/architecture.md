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
| LLM calls | OpenRouter (`:free` tier models) via the OpenAI-compatible SDK | Program-endorsed, $0 |
| Observability | **LangSmith** free Developer tier | Multi-step agent loops are impractical to debug from logs alone; traces also document actual system behavior |
| Retrieval / RAG | `sentence-transformers` (local) + `ChromaDB`, **hybrid**: metadata filters for hard constraints, embeddings for description/amenity text | Free, local, and a more honest design than pure vector search over structured data |
| Regression | `pandas` + `numpy` + `scikit-learn` | Existing strength; lowest-surprise component |
| State persistence | LangGraph checkpointer (SQLite) | Comes with the framework; also enables `interrupt()` |
| Demo surface | **Streamlit**, run locally | ~50 lines; far better on video than a terminal recording |
| Dev environment | VS Code + Claude Code | — |

**Total cost: $0.** Streamlit is open-source and free to run locally; Community Cloud
is only relevant for public hosting, which this project does not require — the demo app
stays local. LangGraph is MIT-licensed. LangSmith's free tier covers a solo developer's
usage. OpenRouter `:free`
models, HUD, Redfin, and Kaggle are all free. Against the $100 project budget, the only
plausible spend is ~$10–20 of OpenRouter credits *if* free-tier rate limits become a
real time sink — but the capstone brief says *"you are expected to design your capstone
and test it using freely available model access,"* so free models are the default and
paid credits are a documented contingency, not the plan.

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
    │   ├── extractor.py           # ⬜ stub (regex parse); real LLM call is U3
    │   ├── comps_retrieval.py     # ✅ adaptive relaxation loop
    │   ├── valuation_rent.py      # ⬜ stub; U5
    │   ├── scenario_forecast.py   # ⬜ stub; U6
    │   ├── critic.py              # ◐ confidence + escalation built; consistency checks U7
    │   ├── summarizer.py          # ✅ real markdown, disclosure-first; polish in U9
    │   └── human_review.py        # ✅ the interrupt() escalation node
    ├── tools/
    │   ├── __init__.py
    │   ├── llm_client.py          # ✅ OpenRouter wrapper + schema-validated retry loop
    │   ├── vector_store.py        # ✅ Chroma setup + embedding + hybrid query
    │   ├── kaggle_data.py         # ✅ single cleaning path: dedupe, completeness, city match
    │   ├── rent_model.py          # sklearn regression: train/load/predict (FMR-normalized target)
    │   ├── hud_fmr.py             # ✅ HUD FMR API client (§9)
    │   ├── county_crosswalk.py    # ✅ lat/lon → county_fips via point-in-polygon join (rewritten Aug 15, 2026)
    │   ├── redfin_data.py         # ✅ load + query, rolling-3 + growth bands computed here
    │   └── tracing.py             # ✅ LangSmith project wiring; env-driven, never required
    ├── scripts/
    │   ├── pull_fmr_sample.py     # ✅ real HUD pull smoke test
    │   ├── verify_metro_selection.py # ✅ reproduces the §2 metro evidence
    │   ├── build_comps_index.py   # ✅ one-off: embed + load Chroma (3,880 listings)
    │   ├── retrieval_evidence.py  # ✅ Checkpoint 3.1 evidence: 3 density cases + config-flag ablation
    │   ├── retrieval_ablation_llm.py # ✅ Checkpoint 3.1: ungrounded LLM vs. grounded retrieval
    │   ├── train_rent_model.py    # one-off: fit + report holdout MAE
    │   └── export_graph_diagram.py # ✅ generates the diagram AND asserts decision #9's topology
    ├── notebooks/
    │   └── 01_data_exploration.ipynb
    ├── eval/
    │   ├── listings/              # synthetic listings, each engineered to trip a known flag
    │   ├── expected.yaml          # listing → expected flags / status
    │   └── run_eval.py            # batch runner → results table for the report
    ├── tests/
    │   ├── conftest.py            # ✅ puts src/ on the import path
    │   └── test_flag_propagation.py  # ✅ the one test that must never fail — 14 cases
    ├── app.py                     # Streamlit demo UI (local only)
    └── main.py                    # ✅ entrypoint: run full pipeline on one listing
```

`agents/human_review.py` was not in the original tree. It is not a specialist — it makes
no estimate and reaches no conclusion — but it *is* a node function, and putting it in
`graph.py` would have mixed a behaviour into a module that is otherwise pure wiring.

