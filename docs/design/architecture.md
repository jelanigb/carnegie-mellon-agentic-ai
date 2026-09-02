**§§3–4 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#20) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

## 3. Stack Decision: LangGraph from day one

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
- **Agents communicate only through shared state.** A node reads `DealState` and
  returns a partial update; it never invokes another agent, and never hands data to
  one. Routing is a separate concern that lives in edges and `route_*` functions,
  never inside a specialist — and a `route_*` function returns the *name* of the next
  node, carrying no payload of its own.
- **State is a single typed object** (§5), never scattered across variables.
- **Flags and retries are state-encoded, not control-flow-encoded.** Conditional edges
  read state to route; anything outside state is invisible to the graph.

New addition: **every cycle must be bounded by an explicit counter in state**, not by
LangGraph's `recursion_limit`. Hitting the limit raises an opaque exception; a counter
lets the system escalate to human review gracefully, which is the behavior Checkpoint
2.1 actually specified.


### Coordination and communication

Documented here Aug 24, 2026, as current state. The *decision* that produced it is #9 in
[`../history/decision_log.md`](../history/decision_log.md#orchestration--control-flow); the
topology is asserted on every diagram export by `scripts/export_graph_diagram.py`.

**The pipeline is strictly sequential.** `graph.py` wires a static spine —
Extractor → Comps → Valuation → Scenario → Critic — and that ordering is fixed by data
dependency, not chosen at runtime: Valuation consumes `state.comps`, Scenario consumes
`rent_estimate`. **There is no parallelism and no fan-out anywhere in the graph.**

**The Planner runs pre-flight, not as a supervisor.** It writes a plan into state once, up
front, and a conditional edge reads it. Specialists do not return to it between hops. Its
real degrees of freedom are which optional steps to skip, rework routing, and escalation.

**One back edge, and it is the only cycle.** `Critic → Planner`, bounded by
`rework_count` against `config.MAX_REWORKS`. Any second loop-closing edge is a defect and
the export fails on it.

**"Cross-agent" means across agents' outputs, not across concurrent streams.** The Critic's
consistency checks compare what *different agents wrote to state* — the Extractor's stated
rents against Valuation's modelled rent, the Scenario agent's projection base against the
price the Extractor read. It sits last in the spine precisely because it is the only node
positioned to see all of them. This is worth stating because "cross-agent checking" reads
like concurrency and is not.

**Communication is one-way along the spine, two-way only at the rework edge.** Every node
reads `DealState` and returns a partial update; nothing is passed between agents directly.
The single validation loop-back is the Critic's, which is the whole of this system's
two-way communication.


### Known limitation: live model output is not perfectly reproducible, even at temperature 0

Documented here Aug 29, 2026, found while building U8.5's OQ-16 case and diagnosed with a
direct experiment rather than left as a guess — full reasoning in
[`../open_questions.md`](../open_questions.md) (OQ-17), no unit assigned.

**What was observed.** `scenario_forecast`'s Tree-of-Thought scorer (`config.MODEL_SCENARIO
= "nvidia/nemotron-3-nano-30b-a3b"`, `config.LLM_TEMPERATURE = 0.0`) gave different
depth-2 pairing scores across live re-runs of the same prompt — enough, on roughly 1 in
15-20 attempts, to flip which of two candidates the search preferred and trip
`FlagKind.FORECAST_BRANCHES_NEAR_TIED`. The same variance showed up unprompted in a
`live`-tier eval re-run of the `los-angeles` demo deal.

**What temperature does and does not control.** Temperature governs the *sampling* step —
how a probability distribution over the next token gets turned into a choice. Setting it
to 0 removes that step's randomness by always taking the highest-probability token
(effectively greedy decoding). It says nothing about how the underlying probabilities
(the logits) get *computed* in the first place, and that computation is not guaranteed to
be bit-identical between two calls with the same input:

- GPU matrix operations (attention, matmuls, softmax reductions) run in parallel across
  many cores, and floating-point addition is not associative —
  `(a + b) + c` and `a + (b + c)` can round differently. The order partial sums combine
  can vary run to run under real serving conditions — continuous-batching servers process
  many concurrent requests together, and which other requests happen to be batched
  alongside yours can change the numerical path even though the "logical" input did not.
- These differences are usually too small to matter, except exactly when two candidate
  tokens are near-tied — which is precisely the failure mode `FORECAST_BRANCHES_NEAR_TIED`
  exists to name at the *output* level. Because generation is autoregressive, one flipped
  early token can cascade into a materially different rest of the response.
- `nvidia/nemotron-3-nano-30b-a3b`'s `-a3b` suffix ("30B total, ~3B active per token") is
  standard notation for a sparse Mixture-of-Experts model. MoE routing amplifies this
  problem rather than absorbing it: which expert sub-network handles a token is a hard,
  discrete switch decided by a gating score, not a smooth function — the same small
  numerical noise that might nudge a dense model's output by a hair can send an MoE
  model's token through a genuinely different expert, producing a qualitatively different
  answer rather than a slightly different one.

**Confirmed empirically, and the confirmation matters because the two candidate causes
call for different responses.** Eight identical calls to the model at `temperature=0.0`
were fired directly against the OpenRouter API, bypassing this project's cache entirely:

1. **OpenRouter routes "the same model" across different backend deployments per
   request.** The eight calls landed on four different providers (Novita, Crusoe, Nebius,
   DeepInfra) running three different `vllm` server versions. Even a trivial "what is 2+2"
   prompt came back differently formatted depending which one answered — direct evidence
   that "the same model" served through an aggregator is not one fixed numerical artifact.
2. **Pinning the request to one provider (OpenRouter's `provider.order` /
   `allow_fallbacks` routing parameters) removes that layer — confirmed via the response's
   `provider` and `system_fingerprint` fields staying constant across repeated calls — but
   a second, larger layer of variance survives untouched.** Scores for the same candidate
   on the same fixed deployment still swung from 0.05 to 0.95 across repeated identical
   calls. `seed` was tested on top of the pinned provider and made no measurable
   difference — expected, since `temperature=0` removes the sampling step a seed would
   otherwise control, so a seed has nothing left to fix. The residual variance has to live
   in the forward pass itself, consistent with the batching/floating-point mechanism
   above.

**Neither `seed` nor provider-pinning is worth adopting as a mitigation.** Both were
tested rather than assumed. `seed` costs nothing (an extra request field, no added
latency) but measurably did not help. Pinning a provider also costs nothing in latency,
but it trades away OpenRouter's automatic failover for a benefit the experiment showed
does not materialize — the dominant source of variance survives the pin. Given this
project's own history of live-model reliability problems (§3 above — free-tier rate
limits, an account-wide daily cap, a model behaving differently across variants), giving
up automatic failover is a real cost for no measured gain, and neither change is made.

**What this means for the system, not just the observation.** This is not fixable by a
client-side parameter, and chasing exact reproducibility from a hosted, aggregated model
is the wrong target. The right target — not yet acted on, tracked as OQ-17 — is a system
that discloses this rather than presents one noisy sample as a stable judgment: a
committed eval recording is unaffected (replay reads a frozen response, so `golden` and
`replay` rows are exact regardless), but a `live` row, and any future live surface, can
legitimately differ between runs of what looks like the identical deal. A resilient
design should expect that and still produce a defensible result, rather than assume a
single live call is reproducible.

---

## 4. Proposed Repository Structure

**Note:** Paths in the rest of this doc that reference `tools/`, `agents/`, `config.py`, etc. are relative to `src/`.

```
carnegie_mellon_agentic_repo/
├── data/                          # gitignored — Kaggle CSV, Redfin/Zillow CSVs, cached HUD responses
│   ├── raw/
│   └── processed/                 # trained rent model, Chroma index, checkpointer, dev LLM cache
├── docs/
│   ├── implementation_plan.md     # plan of record: §6 sequence, §7 decisions register
│   ├── open_questions.md          # every unresolved question, by system area
│   ├── demo.md                    # the demo guide: what each deal shows
│   ├── design/                    # what the system IS — architecture, state, data, evaluator, personas
│   ├── history/                   # how it got that way — changelog, decision_log
│   ├── sample_reports/            # two committed reports, replayed byte-identically from a clone
│   └── diagrams/                  # generated from the compiled graph, not drawn
└── src/                           # project root for all application code
    ├── requirements.txt
    ├── .venv/                     # gitignored — dedicated virtualenv
    ├── config.py                  # the only home for tunable parameters (§8)
    ├── state.py                   # DealState / Flag / DealTerms / Comp / Scenario — Pydantic (§5)
    ├── graph.py                   # StateGraph assembly: nodes, edges, routing, compile(), serde
    ├── nodes.py                   # node-name string constants (avoids silent typo bugs)
    ├── demo_deals.py              # the synthetic listings + the public source behind every figure
    ├── main.py                    # entrypoint: one listing end to end; --deal / --fault / --no-retrieval
    ├── app.py                     # Streamlit demo surface; replay by default (U9.7)
    ├── mcp_server.py              # MCP read-only reference server (FMR + appreciation)
    ├── agents/
    │   ├── planner.py             # pre-flight plan + every route_* function
    │   ├── extractor.py           # schema-validated LLM call + geocoding + county
    │   ├── comps_retrieval.py     # adaptive relaxation loop + comp-attribute drift check
    │   ├── valuation_rent.py      # anchored rent estimate, comp cross-check, benchmark, GRM
    │   ├── scenario_forecast.py   # ToT beam search over enumerated framings/pairings
    │   ├── critic.py              # confidence, escalation, interaction checks, the recommendation
    │   ├── summarizer.py          # the report: two axes, verdict, disclosures, evidence
    │   └── human_review.py        # the interrupt() escalation node
    ├── tools/
    │   ├── llm_client.py          # OpenRouter wrapper + schema-validated retry loop + cache
    │   ├── llm_cache.py           # on-disk response cache; off / read_write / replay
    │   ├── diagnostics.py         # full error detail to stdout, account id redacted (U9.M)
    │   ├── logging_setup.py       # keeps one library's constructor from configuring the process
    │   ├── faults.py              # the three declared faults + their injector (U9.7a)
    │   ├── tracing.py             # LangSmith project wiring; env-driven, never required
    │   ├── vector_store.py        # Chroma setup + embedding + hybrid query
    │   ├── kaggle_data.py         # single cleaning path: dedupe, completeness, city match
    │   ├── hud_fmr.py             # HUD FMR API client (§9)
    │   ├── fmr_history.py         # FMR published history — the rent-growth fallback since #21
    │   ├── zori.py                # Zillow ZORI panel: the rent anchor's level (#19)
    │   ├── rent_growth.py         # rent-growth bands from ZORI, FMR history behind it (#21)
    │   ├── redfin_data.py         # load + query; sale-price series and its metro coverage
    │   ├── growth_bands.py        # one band estimator, shared by both series (U9.3)
    │   ├── sale_benchmarks.py     # county-assessor ZIP sale medians (#11, U8.8)
    │   ├── county_crosswalk.py    # lat/lon → county_fips via point-in-polygon join
    │   ├── zcta_crosswalk.py      # lat/lon → ZCTA, for ZIP-tier anchoring and benchmarks
    │   ├── geocoding.py           # address → lat/lon: Census primary, corpus centroid fallback
    │   ├── tot.py                 # the beam search itself — no domain knowledge (#12, #14)
    │   └── model/rent_model.py    # gradient-boosted rent model: anchor, train, load, predict
    ├── eval/                      # the harness (U8); its outputs are the evaluation evidence
    │   ├── README.md              # layout, the three case tiers, record/replay usage
    │   ├── cases.py               # every case, its target flag and its declared verdict
    │   ├── runner.py              # batch runner → results.md; replay by default since U9.5
    │   ├── data/golden_fixtures.py # golden DealTerms fixtures + the listings they came from
    │   ├── data/llm_recordings/   # recorded model responses, replayed by llm_cache
    │   └── results/               # results.md + sensitivity.md — committed; the report cites them
    ├── scripts/                   # 29 one-off evidence, probe and build scripts (see below)
    └── tests/                     # 107 hermetic tests across 7 files; no network, no model calls
        ├── conftest.py            # puts src/ on the import path; keeps the suite off the network
        ├── test_flag_propagation.py       # the suite that must never fail
        ├── test_critic_interactions.py    # the three cross-agent interaction checks
        ├── test_report_verdict.py         # the recommendation rule and its cross-check
        ├── test_forecast_tie_disclosures.py # ties, cut margins, and the ledger's prune reasons
        ├── test_stated_rent_disclosure.py # stated rents against the modelled figure
        ├── test_gross_rent_multiplier.py  # the multiple, its inputs, and its absences
        └── test_diagnostics_redaction.py  # the account id never reaching a recorded terminal
```

**This tree is re-derived from the filesystem, not edited — Sept 2, 2026 (maintenance
item M7).** The previous version had drifted far enough to be actively misleading: it
listed `eval/run_eval.py` and `eval/expected.yaml`, **neither of which was ever built**
(the harness landed as `cases.py` and `runner.py`), marked the Critic and Summarizer
unfinished after both had shipped, described `tests/` as one file of 24 cases when there
are seven files and 107, and omitted every `tools/` module added since U6. A file listed
here that does not exist is worse than an omission — it sends a reviewer looking for
something that never existed — and this tree is one of the first things a reader of a
public repository opens.

**The fix is the method, not the content.** It was regenerated against
`find src -name '*.py'`, and editing it entry by entry is exactly what let it drift. The
`✅`/`◐` build-status markers are gone with it: they encoded a moment in the build, they
were never updated as that moment passed, and `history/changelog.md` answers "when did
this land" properly. `scripts/` is given as a count rather than enumerated for the same
reason — it turns over faster than this document is read, and each script's own docstring
says what it measures.

`agents/human_review.py` was not in the original tree. It is not a specialist — it makes
no estimate and reaches no conclusion — but it *is* a node function, and putting it in
`graph.py` would have mixed a behaviour into a module that is otherwise pure wiring.

