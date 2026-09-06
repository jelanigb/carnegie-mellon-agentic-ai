# Carnegie-Mellon Agentic AI Program: Capstone Checkpoint 7.1

# Multi-Family Residential Deal Evaluator

**Author:** Jelani Gould-Bailey  
**GenAI Research Assistance:** Anthropic Claude Opus 5  
**Coding Assistance:** Claude Code  
**Last Major Update:** Sept 5, 2026

## 1\. Project Title

Multi-Family Residential Deal Evaluator

## 2\. Problem and user

This seven-agent system evaluates small multi-family (2-4 unit) properties for real estate investors. Given a listing, it automates extraction of deal terms, comp retrieval, rent estimation, scenario forecasting, and authors a final report.

One challenge today is that the small multi-family segment has far less available data than single-family homes, and a robust evaluation requires several kinds of judgment: comparable-property analysis, rent estimation, and forward-looking scenario forecasting. Investors traditionally rely on static calculators and manual rules of thumb

### User Base:

1. **The Investor** — reads the final report and decides whether to invest. They are the end customer; clean reports go to them without edits.  
2. **The Real Estate Agent** — presents the report to the Investor. Certain flags route the draft to the Agent for human review, to decide how to frame the findings and disclosures.  
3. **The IT Specialist** — supports the Real Estate Agent, and steps in when system-generated errors during report generation require a closer look.

Why an agent and not a spreadsheet? Because the arithmetic isn't the hard part. The hard part is what to do when the evidence runs thin. Widen the comparable search, or report that you couldn't? Trust the listing's stated rent, or the model's? Those are sequential decisions where each one changes the next — and every one of them needs to be disclosed.

## 3\. System goal and scope

The system ingests a text-based multi-family listing and generates a report for The Investor. Success is a complete report with the property's data and suitable comparables, a rent-growth forecast, a value-appreciation forecast, and transparent disclosure of anything noteworthy or difficult encountered along the way. Depending on the nature and number of disclosures, the report may be flagged for closer review by the Real Estate Agent or the IT Specialist.

The report must answer 2 distinct questions: ***"Can the system stand behind its own numbers?"*** and ***"Is this a good deal?"***

**Scope:** 2-4 unit residential properties in Chicago, Los Angeles, Cleveland, and NYC (comp index only). No properties \> 4 units. The agentic system provides decision support without write access or execution capabilities (cannot make purchases).

## 4\. Final system architecture

A seven-agent pipeline orchestrated via a [LangGraph](https://github.com/langchain-ai/langgraph) state graph, with an explicit human-in-the-loop pause node.

![The compiled graph: start to planner, then extractor, comps_retrieval, valuation_rent, scenario_forecast, critic — which branches to human_review, back to planner, or straight to summarizer](diagrams/deal_evaluator_graph_lr.png)

*Generated from the compiled graph, not drawn. Dotted edges are conditional.*

### Agents

1. **Planner** — Inspects deals pre-flight, determines steps, and manages graph routing.  
2. **Extractor** — Parses listings into typed terms, geocodes addresses, and logs all assumptions.  
3. **Retrieval** — RAG over a rental corpus in a vector store; progressively relaxes search criteria when sparse, flagging along the way.  
4. **Valuation** — Custom gradient-boosted rent model anchored to ZIP-level market indices and cross-checked against comps.  
5. **Forecast** — Tree-of-Thought search over rent-growth and price-appreciation scenarios, scored by an LLM and pruned to a beam of survivors.  
6. **Critic** — Cross-agent consistency checks, confidence scoring, buy/pass decisions, and the decision to report, rework or escalate.  
7. **Summarizer** — Compiles the final report, surfacing all upstream disclosures.

### Coordination, state and memory

The pipeline runs **strictly sequentially with at most one loop**. Fixed data dependencies dictate ordering; there is no parallelism or fan out. The Planner sets state pre-flight rather than supervising dynamically.

Memory is a typed Pydantic state object backed by SQLite checkpointing. Agents communicate exclusively through partial state updates with append-only disclosure logging for auditability; no agent directly invokes another. This ensures separation-of-concerns and clear auditability.

The single back edge (Critic → Planner) and every loop in the system are bounded by an explicit counter. Human intervention is triggered by a LangGraph `interrupt()` call that pauses the graph and surfaces the reason why.

### Reasoning, retrieval and tools

The system is a hybrid system which combines deterministic logic with LLMs. Full runs execute **seven model calls across four agents**. Core decision-making (scoring, routing, buy/pass recommendations) relies on deterministic functions over accumulated state (vs. model calls).

- **Tree-of-Thought (Forecast)** runs beam search over an enumerated space: four framings of which years feed each series, then nine rent-band/price-band pairings. The model ranks and prunes; it never produces a growth rate. Every candidate and its prune reason reaches a ledger printed in the final report.  
- **Adaptive RAG (Retrieval)** is a reason/act/observe loop. A shortfall is treated as an observation: concede one criterion, name it, then re-query.  
- **Tools** come from a read-only MCP server, whose `list_tools()` builds the Forecast evaluator's menu (so the tool surface has one definition rather than two that can drift).  
- **Logging** is LangSmith tracing across every node; **evaluation** invokes this same compiled graph.

### Core architectural principles

**Transparent Degradation, enforced structurally.** An agent proceeding on incomplete or relaxed evidence attaches a named, severity-graded flag defined in an enum, making coverage of the failure modes countable. An append-only reducer makes disclosure loss impossible.

**Independent Decision Axes.** Confidence scoring (system numbers) and deal quality (investment merit) are computed separately; a deal can require human review while remaining viable.

**Rule-Gated AI:** every model call sits upstream of a rule or beside one, never as the last word.

**Ground Assumptions in Data.** Every load-bearing assumption was tested against real data, and several failed, leading to iterative design revisions.

## 5\. Design evolution across the program

While the pipeline's stages remained stable since the early days of the project, many other parts of the project changed, often driven by new data.

**Data sources moved closer to the estimate:** Comps and rent-model training draw on a UCI apartment-rental corpus of \~99,000 listings from 2018–19 which has beds, baths, square footage, coordinates and rent together at unit level. However, because it is seven years stale, the model learns each rent as a *ratio* to a published index rather than as a dollar figure, then multiplies by today's index.

That makes the index a first-order choice, and my first one was wrong. HUD Fair Market Rents are county-level, annual, and pitched at the bottom 40% of the market; the evaluation harness caught FMR rising \+51.9% since the corpus vintage against market rent's \+33.5% (an 18-point bias in every estimate). The anchor is now a hybrid — Zillow's ZIP-level monthly index for market rent, HUD for the bedroom step Zillow does not publish — and **both ends of the ratio read the same series**, so drift divides out instead of multiplying through. Per-metro error fell from $981 → $855 in New York and $454 → $343 in Chicago. On the price side, a metro median gave way to ZIP-level assessor sales.

**Scope Refinement due to lack of evidence:** I dropped ZIP-level appreciation and property value models due to sparse data coverage. Tree-of-Thought was not added to nodes where deterministic logic yielded better decisions

**Harness Expansion:** Coverage of the 30 typed disclosure flags went from 60 → 100%. As more cases were added, they exposed several logic failures in the system.

**Rent Model Evolution:** Moved from linear regression (LR) to a gradient-boosting regressor (GBR) on cross-validated (CV) evidence. The initial LR training run used an 80/20 split and no CV. I later tested 3 models and ran 5-fold CV. MAE dropped from $513.67 (LR) to $450.71 (GBR), with only a moderate train-versus-holdout gap ($18.34).

**Transparent Degradation Maturity:** The idea began as "append a flag to a list," then became a closed enum so coverage could be counted; then severity grades were added, so a single disqualifying observation escalates on its own rule regardless of the confidence score. It further evolved into a scope classifier separating disclosures about target property from those about its market. It also became a routing classifier: when the graph halts at its human-review `interrupt()`, which human sees the report is determined by the disclosure types.

## 6\. Implementation overview

The project is written in Python 3.13 using a single virtualenv.

| Layer | Choice | How it supports the design |
| :---- | :---- | :---- |
| **Orchestration** | LangGraph `StateGraph` — 8 nodes, conditional edges, SQLite checkpointer | `Annotated[list[Flag], operator.add]` makes the disclosure channel append-only by construction; `interrupt()` is a first-class pause-and-resume primitive |
| **State** | Pydantic v2 | One typed state object; its `ValidationError` text feeds the Extractor's retry prompt |
| **LLM** | `nvidia/nemotron-3-nano-30b-a3b` via OpenRouter's OpenAI-compatible SDK, temperature 0 | Chosen empirically over 7 candidates scored on schema-valid extraction, field accuracy, latency and cost. |
| **Retrieval** | ChromaDB (persistent, cosine) \+ `sentence-transformers/all-MiniLM-L6-v2`, local | 3,880 listings, one document each, never chunked. Bedroom count and geography run as exact metadata filters and are deliberately kept **out** of the embedded text, so the model cannot return a 3-bedroom as a near-match for a 2-bedroom. Embeddings rank only free text — "renovated", "garden level" — which no structured column captures |
| **Rent model** | scikit-learn `GradientBoostingRegressor`, pandas/numpy | Three structural features and **no market identifier by design**, so location enters only through the anchor — the Zillow/HUD index reading for the target property's own ZIP. The target is a rent-to-anchor *ratio*, which lets a model trained on 2018–19 listings apply to today's index. Zillow's per-ZIP series has different start dates, so a training row whose ZIP had no reading at its own listing month falls back to a county median; only 0.3% of rows end up with no anchor at all and are dropped. |
| **Rent data** | HUD Fair Market Rent API; Zillow ZORI | The hybrid anchor: ZORI for market level at the target property's ZIP, HUD for the bedroom step |
| **Price data** | Redfin Data Center (2–4 unit listings); NYC and Cook County assessor open data | Metro appreciation series, and ZIP-level sale benchmarks |
| **Geography** | Census Geocoder; Census TIGER boundaries via `geopandas` | Address → coordinates with a corpus-centroid fallback; coordinate → ZIP and county by point-in-polygon join |
| **Tool protocol** | MCP (`mcp_server.py`) — four read-only tools | Serves the Forecast evaluator in-process and any external MCP host, from one definition |
| **Observability** | LangSmith | Traces every node; env-driven and opt-in, and each run prints whether it is tracing |
| **Demo surface** | Streamlit, local | Replays from committed recordings, carries a genuine review pause whose typed note reaches the report, simulates three declared faults |
| **Testing** | pytest — 107 hermetic tests; the `eval/` harness | Flag propagation and the eval harness were "must do" items in the implementation plan, and exposed multiple logic errors along the way. |

### Project stats

| Measure | Value |
| :---- | :---- |
| Lines of Python (excl. docstrings & code comments) | 14,894 across 84 files |
| Commits · active span | 165 · 27 days |
| Evaluation cases · tests | 30 · 107 |
| Project cost | $50 (out of $100 total budget). |

### LLM Coding Agent

I acted as the system architect and chief data scientist, guiding system design and key implementation decisions. Anthropic's Claude Code executed most of the coding under rigorous review, feedback, and approval. This arrangement allowed for greater scalable execution vs. me writing all code firsthand (especially given the 7-week project window). 

## 7\. Evaluation and results

**Evaluations run on a 30-case batch harness** using the compiled production graph. Cases include golden fixtures with deal terms supplied, replay cases against recorded responses, and 8 demo listings. 21 cases are designed to trigger specific disclosures with pre-declared target outcomes. **Every case declares its expected outcome before the run** (without that, the exercise is self-confirming).

| Criterion | Result |
| :---- | :---- |
| **Verdict agreement** — report-or-escalate vs. the declared verdict | **20 of 23** scored cases; all three disagreements triaged |
| **Disclosure coverage** — of the 30 typed kinds | **30 of 30 raised**, 0 uncovered, 0 unreachable |
| **Parameter robustness** — how far the threshold and weights can move | **63 of 160** swept configurations decide all 21 cases identically; the threshold moves 0.30–0.70 with no verdict changing |
| **Rule independence** — does the critical rule do work the score does not? | The critical weight is **inert across its whole range, including zero** |
| **Regression** — do published rows reproduce on a fresh build? | **6 of 7** |
| **Rent accuracy** — 5-fold cross-validated, out-of-fold | **$452 MAE** vs. a $590 baseline (**23.3%** better), R² 0.409. Chicago $343, Cleveland $357, Los Angeles $509, **New York $855** |
| **Transfer** — added error in an unseen market | **$512/mo** under leave-one-metro-out against the $452 above — **13% more error**; still beats a predict-the-average baseline in **all nine** held-out markets |
| **Groundedness** — retrieval on vs. off, identical target property | 8 of 8 retrieved comps exist in the evidence base; **0 of 8** ungrounded ones do |
| **Search value** — beam search vs. a linear chain | Across four target properties it kept the first-enumerated framing **0 times**; on Cleveland the base case differs by −22.0% on rent, \+26.4% on price |

**Summary:** 14 cases reported and 16 escalated — 8 on a critical disclosure the confidence score alone would have let through, and 1 on an exhausted rework budget.

**Two caveats:** The escalation rate reflects engineered test *fixtures*, not agent performance. Only system confidence is scored; property purchase quality lacks ground truth since target property listings are all synthetic and unsold. However, buy-axis thresholds draw from 44,358 real sales across 222 ZIP codes.

## 8\. Safety and reliability considerations

**The system's entire risk surface is the report**, as it lacks write access or action capabilities. The primary risk is presenting plausible but ungrounded errors confidently.

**System-level guardrails:** Agents operate independently, returning partial state updates to an append-only disclosure log. Cycles are bounded by explicit state counters rather than framework recursion limits. Exceeding a counter terminates the loop, logs the exhausted resource, and routes the deal to human review with a full report. The MCP tool surface is strictly read-only.

**Agent-level guardrails:** Extraction uses schema validation with up to three retries before omitting deal terms and raising a critical disclosure (omitting fallback regex parsers to prevent obsolescence). The geocoder discloses its precision tier without inventing coordinates, only retryable errors enter rework, and out-of-bounds target properties are rejected.

**Human oversight:** The graph pauses if confidence falls below 0.60, **any critical disclosure is raised**, or the rework budget expires with pending objections. Escalation checks precede rework to prevent redundant execution. Calls to `interrupt()` present actionable grounds (scores, disclosures, open questions) and route issues to the Real Estate Agent for deal substance or the IT Specialist for infrastructure. This design prioritizes explicit escalation over silent errors.

## 9\. Limitations and next steps

### Limitations:

**Data.** The comp corpus relies heavily on 2018–19 aggregator data. Rent model transfer to unseen markets adds \~13% error. New York exhibits high per-market error driven by uncaptured within-ZIP rent dispersion rather than data volume. California publishes assessed values, not sale prices, so Los Angeles falls back to a metro-level price benchmark. Operating-expense data gaps necessitate using gross rent multipliers over NOI/cap rates.

**Reasoning and reporting.** Forecast band-pairing rests on a weak rent-to-price growth relationship (r² ≤ 0.10) and is disclosed as tentative.

**LLM non-determinism.** Live model calls to OpenRouter were found to vary across deployments and runs, though committed evaluation recordings remain exact.

### Potential Next steps:

1. **Expose evaluation as an MCP capability** for external real-estate agents.  
2. **Use Tree of Thought** for dynamic, deal-specific retrieval relaxation.  
3. **Sample forecast scoring multiple times** to disclose score variance.  
4. **Incorporate operating-expense data** to calculate true return metrics (Gross Rent Multiplier is used today).

## 10\. Public GitHub repository

[**https://github.com/jelanigb/carnegie-mellon-agentic-ai**](https://github.com/jelanigb/carnegie-mellon-agentic-ai) — public, MIT licensed.

1. **README** — [`README.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md): project, architecture, setup, usage, and a plain statement of limitations. Written for *reviewing* rather than running.  
2. **Source code** — [`src/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src): the seven agents in [`src/agents/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/agents), graph assembly in [`graph.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/graph.py), state schema in [`state.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/state.py), every tunable parameter in [`config.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/config.py).  
3. **Sample inputs** — the eight demo listings in [`src/demo_deals.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/demo_deals.py); [`docs/demo.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/demo.md) explains what each exists to show.  
4. **Sample outputs** — three sample reports:  
   1. [`staten-island.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/staten-island.md) **escalates** at 0.00 and *still* recommends proceeding;  
   2. [`los-angeles.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/los-angeles.md) reports at confidence 1.00 and recommends *Proceed*;  
   3. [`overpriced.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/overpriced.md) is the mirror, confident at 1.00 with the *deal* as the problem.  
5. **Evaluation artifacts** — Eval inputs in [`src/eval/data/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/eval/data) and eval results in [`src/eval/results/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/eval/results).  
6. **Review instructions** — The Readme has a [section pointing to project evidence](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md#where-the-evidence-already-lives) and a detailed [section for running the project](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md#running-it). Note that not all data sources are committed and anyone cloning the repo needs their own API keys; [`data/README.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/data/README.md) names every dataset, its source and license, and the command that consumes it.