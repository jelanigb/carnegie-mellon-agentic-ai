# Carnegie-Mellon Agentic AI Program: Capstone Checkpoint 7.1

# Multi-Family Residential Deal Evaluator
**Author:** Jelani Gould-Bailey  
**GenAI Research Assistance:** Anthropic Claude Opus 5  
**Coding Assistance:** Claude Code  
**Last Major Update:** Sept 4, 2026


## 1\. Project Title

Multi-Family Residential Deal Evaluator

## 2\. Problem and user

This seven-agent system helps residential real estate investors evaluate small multi-family (2-4 unit) properties as investment opportunities. Given a property listing as input, it automates and reasons through the work needed to produce an investor-facing report: extracting deal terms, retrieving relevant comps, estimating rent against real-world data, forecasting scenarios, and authoring the aggregated, transparent deal report.

One challenge today is that small multi-family segment has far less available data than single-family homes, and a robust evaluation requires several kinds of judgment: comparable-property analysis, rent estimation, and forward-looking scenario forecasting. Individual investors typically do this manually, using rules of thumb and static calculators.

### User Base:

1. **The Investor** — reads the final report and decides whether to invest. The end customer; clean reports go to them without edits.
2. **The Real Estate Agent** — presents the report to the Investor. Certain flags route the draft to the Agent for human review, to decide how to frame the findings and disclosures.
3. **The IT Specialist** — supports the Agent, and steps in when system-generated errors during report generation require a closer look.

Why an agent and not a spreadsheet? Because the arithmetic isn't the hard part. The hard part is what to do when the evidence runs thin. Widen the comparable search, or report that you couldn't? Trust the listing's stated rent, or the model's? Those are sequential decisions where each one changes the next — and every one of them needs to be disclosed.

## 3\. System goal and scope

The system ingests a text-based multi-family listing and generates a report for The Investor. Success is a report carrying the property's data and suitable comparables, a rent-growth forecast, a value-appreciation forecast, and transparent disclosure of anything noteworthy or difficult encountered along the way. Depending on the nature and number of disclosures, the report may be flagged for closer review by the Real Estate Agent or the IT Specialist.

The report answers 2 distinct questions: ***"Can the system stand behind its own numbers?"*** and ***"Is this a good deal?"***

Scope boundaries: three tuned markets (Chicago, Los Angeles, Cleveland, plus New York in the comp index); no single-family homes and no properties above 4 units. The agentic system is a forecaster providing decision support — it takes no action, holds no write access, and buys nothing.

## 4\. Final system architecture

A seven-agent pipeline orchestrated as a [LangGraph](https://github.com/langchain-ai/langgraph) state graph, with an eighth node that is an explicit human-in-the-loop pause.

![The compiled graph: start to planner, then extractor, comps_retrieval, valuation_rent, scenario_forecast, critic — which branches to human_review, back to planner, or straight to summarizer](diagrams/deal_evaluator_graph_lr.png)

*Generated from the compiled graph, not drawn. Dotted edges are conditional.*

### Agents

1. **Planner** — pre-flight: inspects the deal, decides which steps run, and owns every routing decision in the graph.
2. **Extractor** — parses the listing into typed deal terms and geocodes the address, naming every assumption it has to make.
3. **Retrieval** — RAG over a rental corpus in a vector store; relaxes its criteria one step at a time when matches are sparse, flagging each concession.
4. **Valuation** — a gradient-boosted rent model anchored to a market rent index at the property's ZIP, cross-checked against the retrieved comps.
5. **Forecast** — Tree-of-Thought search over rent-growth and price-appreciation scenarios, scored by an LLM and pruned to a beam of survivors.
6. **Critic** — cross-agent consistency checks, confidence scoring, the buy/pass recommendation, and the decision to report, rework or escalate.
7. **Summarizer** — renders the report, surfacing every upstream disclosure rather than only the headline numbers.

### Coordination, state and memory

The pipeline is **strictly sequential with exactly one cycle**. Ordering is fixed by data dependency rather than chosen at runtime — Valuation consumes the comps, Forecast the rent estimate — so there is no parallelism or fan-out. The Planner is **pre-flight, not a supervisor**: it writes a plan into state once, and a conditional edge reads it.

Memory is a typed Pydantic state object on a SQLite checkpointer. Agent communication happens srictly through the state object: every node returns a *partial* update, no agent invokes another, and routing functions return a node name carrying no payload. Disclosures accumulate through an append-only reducer. The single back edge (Critic → Planner) and every loop in the system are bounded by an explicit counter. Human intervention is triggered by a LangGraph `interrupt()` call that pauses the graph and surfaces the reason why.

### Reasoning, retrieval and tools

The agentic system is a hybrid system which mixes deterministic logic with LLM interactions. A full run makes **seven model calls across four of the agents**. The most consequential judgments — confidence scoring, escalation, routing and the buy/pass verdict — are deterministic functions evaluating accumulated state, rather than model calls.

- **Tree-of-Thought (Forecast)** runs beam search over an *enumerated* space: four framings of which years feed each series, then nine rent-band/price-band pairings. The model ranks and prunes; it never produces a growth rate. Every candidate and its prune reason reaches a ledger printed in the report.
- **Adaptive RAG (Retrieval)** is a reason/act/observe loop. A shortfall is treated as an observation: concede one criterion, name it, re-query.
- **Tools** come from a read-only MCP server, whose `list_tools()` builds the Forecast evaluator's menu (so the tool surface has one definition rather than two that can drift).
- **Logging** is LangSmith tracing across every node; **evaluation** invokes this same compiled graph.

### Core architectural principles

**Transparent Degradation, enforced structurally.** An agent proceeding on incomplete or relaxed evidence attaches a named, severity-graded flag. Kinds come from a closed enum of 30, making coverage of the system's own failure modes countable; the append-only reducer makes disclosure loss impossible by construction.

**Two axes, never merged.** Confidence in the system's numbers and the quality of the deal are computed by different rules and rendered separately. Neither is an input to the other, so a deal can escalate for review and still be worth buying.

**The model proposes and the rules decide** — every model call sits upstream of a rule or beside one, never as the last word.

**Measure rather than assume** — throughout the project, assumptions changed in light of empirical data, which led to design changes.

## 5\. Design evolution across the program

While the pipeline's stages remained stable since the early days of the project, almost everything underneath it changed. In each case a measurement forced the change.

**Data sources moved closer to the estimate.** Comps and rent-model training both draw on a Kaggle apartment-rental corpus of ~99,000 listings from 2018–19 — the only free unit-level source I found carrying beds, baths, square footage, coordinates and rent together. Because it is seven years stale, the model never learns a dollar rent; it learns the *ratio* of a listing's rent to a published index, and multiplies that ratio by today's index at prediction time.

That makes the choice of index load-bearing, and my first choice was wrong. Rent was originally anchored to HUD Fair Market Rents (FMR) — county-level and annual — and the evaluation harness surfaced the defect: FMR had risen +51.9% since the corpus vintage while market rent rose +33.5%, an 18-point bias in every estimate. I pivoted to Zillow's rent index, which is ZIP-level and monthly but carries no bedroom breakdown, so the anchor is now a hybrid: Zillow for the ZIP-level market rent, HUD for the bedroom step. **Both ends of the ratio now read the same market series** — training divides each 2018–19 rent by the index at that listing's own ZIP and month, and prediction multiplies by the index at the subject's ZIP today — so an index that drifts away from the market it measures divides out instead of multiplying through. Metro-level Mean Absolute Error (MAE) dropped from $981 → $855 in New York and $454 → $343 in Chicago. On the price side, I switched from a coarser metro median benchmark to a ZIP-level dataset of ~45,000 county-assessor sales.

**Several planned capabilities were eliminated because they lacked supporting evudence.** ZIP-level appreciation and property-level value estimates were both dropped due to insufficient data coverage. Tree-of-Thought was removed from a node, because the decision points were better served by deterministic logic.

**The evaluation harness became the thing every claim is measured against.** Coverage of the 30 typed disclosure kinds began at 17 of 28 and now stands at 30 of 30. Closing that gap changed the system: writing the additional cases against uncovered scenarios exposed several logic feailures in the system.

**The rent model moved from linear regression (LR) to a gradient-boosting regressor (GBR)** on cross-validated evidence. The intiial LR training run used an 80/20 spit. When we revisited models and feature engineering, 5-fold cross-validation (CV) was run. MAE dropped from $513.67 (LR) to $450.71 (GBR), with a moderate increase in train-versus-holdout gap ($18.34). Random forest was also evaluated but had mixed results relative to GBR.

**Transparent Degradation matured from a convention into a typed, routed object.** The idea began as "append a flag to a list," then became a closed enum so coverage could be counted; then severity grades, so a single disqualifying observation escalates on its own rule rather than through a threshold. It then went to a scope classifier separating disclosures about *this property* from those about *its market*; and finally became a routing classifier: when the graph halts at its human-review `interrupt()`, the kinds of disclosure that caused the halt determine whether it is the IT Specialist or the Real Estate Agent who is asked to look.

## 6\. Implementation overview

The project is written in Python 3.13 using a single virtualenv.

| Layer | Choice | How it supports the design |
| --- | --- | --- |
| **Orchestration** | LangGraph `StateGraph` — 8 nodes, conditional edges, SQLite checkpointer | `Annotated[list[Flag], operator.add]` makes the disclosure channel append-only by construction; `interrupt()` is a first-class pause-and-resume primitive |
| **State** | Pydantic v2 | One typed state object; its `ValidationError` text feeds the Extractor's retry prompt |
| **LLM** | `nvidia/nemotron-3-nano-30b-a3b` via OpenRouter's OpenAI-compatible SDK, temperature 0 | Chosen empirically over 7 candidates scored on schema-valid extraction, field accuracy, latency and cost. |
| **Retrieval** | ChromaDB (persistent, cosine) + `sentence-transformers/all-MiniLM-L6-v2`, local | 3,880 listings, one document each, never chunked. Bedroom count and geography run as exact metadata filters and are deliberately kept **out** of the embedded text, so the model cannot return a 3-bedroom as a near-match for a 2-bedroom. Embeddings rank only free text — "renovated", "garden level" — which no structured column captures |
| **Rent model** | scikit-learn `GradientBoostingRegressor`, pandas/numpy | Three structural features and **no market identifier by design**, so location only arrives through the anchor. The target is a rent-to-anchor *ratio*, which lets a model trained on 2018–19 listings apply to today's index. Zillow's per-ZIP series start at different dates, so a training row whose ZIP had no reading at its own listing month falls back to a county median; only 0.3% of rows end up with no anchor and are dropped |
| **Rent data** | HUD Fair Market Rent API; Zillow ZORI | The hybrid anchor: ZORI for market level at the subject's ZIP, HUD for the bedroom step |
| **Price data** | Redfin Data Center (2–4 unit); NYC and Cook County assessor open data | Metro appreciation series, and ZIP-level sale benchmarks |
| **Geography** | Census Geocoder; Census TIGER boundaries via `geopandas` | Address → coordinates with a corpus-centroid fallback; coordinate → ZIP and county by point-in-polygon join |
| **Tool protocol** | MCP (`mcp_server.py`) — four read-only tools | Serves the Forecast evaluator in-process and any external MCP host, from one definition |
| **Observability** | LangSmith | Traces every node; env-driven and opt-in, and each run prints whether it is tracing |
| **Demo surface** | Streamlit, local | Replays from committed recordings, carries a genuine review pause whose typed note reaches the report, simulates three declared faults |
| **Testing** | pytest — 107 hermetic tests; the `eval/` harness | Flag propagation and the eval harness were "must do" items in the implementation plan |

### Project stats

| Measure | Value |
| --- | --- |
| Lines of Python (excl. docstrings & code comments) | 14,894 across 84 files |
| Commits · active span | 165 · 27 days |
| Evaluation cases · tests | 30 · 107 |
| Project budget · spend | $100 · $50 |

## 7\. Evaluation and results

**Every evaluation number comes from a batch harness that invokes the same compiled graph the production entry point runs**, so a result cannot come from a code path that has drifted. The batch is **30 cases** — golden fixtures with deal terms supplied, replay cases running the Extractor against recorded responses, and the eight demo listings plus one ablation — all of which replay from a fresh clone with no live model call. Twenty-one are engineered to trip one specific disclosure each, and **every case declares its expected outcome before the run**; without that the exercise is self-confirming, since demo listings are calibrated to run *clean* and engineered ones to *fail*.

| Criterion | Result |
| --- | --- |
| **Verdict agreement** — report-or-escalate vs. the declared verdict | **20 of 23** scored cases; all three disagreements triaged |
| **Disclosure coverage** — of the 30 typed kinds | **30 of 30 raised**, 0 uncovered, 0 unreachable |
| **Parameter robustness** — how far the threshold and weights can move | **63 of 160** swept configurations decide all 21 cases identically; the threshold moves 0.30–0.70 with no verdict changing |
| **Rule independence** — does the critical rule do work the score does not? | The critical weight is **inert across its whole range, including zero** |
| **Regression** — do published rows reproduce on a fresh build? | **6 of 7** |
| **Rent accuracy** — 5-fold cross-validated, out-of-fold | **$452 MAE** vs. a $590 baseline (**23.3%** better), R² 0.409. Chicago $343, Cleveland $357, Los Angeles $509, **New York $855** |
| **Transfer** — added error in an unseen market | **$512/mo** under leave-one-metro-out against the $452 above — **13% more error**; still beats a predict-the-average baseline in **all nine** held-out markets |
| **Groundedness** — retrieval on vs. off, identical subject | 8 of 8 retrieved comps exist in the evidence base; **0 of 8** ungrounded ones do |
| **Search value** — beam search vs. a linear chain | Across four subjects it kept the first-enumerated framing **0 times**; on Cleveland the base case differs by −22.0% on rent, +26.4% on price |

**The headline results.** Of the 30 cases, 14 report and 16 escalate to human review. The system's report-or-escalate decision matched the verdict declared before the run in **20 of 23** scored cases, and the batch raised **every one of the 30 defined disclosure kinds**. Both escalation grounds that operate independently of the confidence score are demonstrated rather than asserted: **8 deals escalated on a single critical disclosure** where the score alone would have let them report, and **1 on an exhausted rework budget**.

Two caveats belong with those numbers. The escalation rate describes the *fixtures* rather than the agent, since 21 of the 30 cases were engineered to trip a specific disclosure. And only the first of the report's two axes is scored: whether the *property* is a good buy has no ground truth here, because the listings are synthetic and no sale ever happened. Those thresholds rest on external evidence instead — 44,358 real transactions across 222 ZIP codes.

## 8\. Safety and reliability considerations

**The system's entire risk surface is the report** — it takes no action and holds no write access. So the characteristic failure is not a wrong number but a wrong number presented as a right one: plausible, well-formatted, confidently stated, with nothing underneath it.

**System-level guardrails.** No agent invokes another or hands data to another; every node returns a partial state update rather than the whole mutated object. The disclosure channel is append-only through a reducer rather than a convention. Every cycle is bounded by an explicit counter in the state object (extraction retries at 3, retrieval relaxation at 4, rework passes at 2, search depth at 3) — never by the framework's recursion limit, because a framework limit raises opaquely where a counter escalates gracefully. The MCP tool surface is read-only by design: there is no write tool anywhere in the system.

**Agent-level guardrails.** Extraction is schema-validated with bounded retries and then *refuses*: the validation error and rejected response are fed back into the prompt, and after three attempts the agent writes no deal terms at all and raises a critical disclosure. I decided not to include a fallback regex parser as I was concerned it may drift unintentionally. The geocoder will not invent a coordinate; it offers three tiers of granularity and discloses which fired. Only retryable errors get a rework pass. A subject outside the training data's shape is refused rather than priced.

**Human oversight.** Three independent conditions pause the graph: confidence below 0.60, **any single critical disclosure regardless of score**, and an exhausted rework budget with an objection outstanding. Escalation is checked *before* rework, so a deal the system knows a human should see doesn't get re-run. The pause provides grounds for surfacing rather than a state dump, and is routed to the right human: IT issues route to the IT Specialist; deal-substance disclosures go to the Real Estate Agent. A reviewed deal still produces a report and keeps its `needs_review` status after sign-off, preserving the distinction between *"the system was confident"* and *"a person signed off."*

This escalation methodology was intentional: for an investment tool I decided that being wrong silently is worse than occasionally raising too many deals for human review.

## 9\. Limitations and next steps

**Data.** There are a number of opportunities to add additional data in the future. The comp corpus is 2018–19 vintage and 91% one aggregator; more variation and newer data would be useful. The rent model was only trained on certain markets, and transfer costs ~13%. New York carries the largest per-market error as a result of sub-ZIP dispersion; due to limitations in the training data this cannot be improved. The ZIP-level sale benchmark has limitations -- California publishes assessed value rather than transaction price. And there is no cap rate or net operating income calculation, because this project has no operating-expense data (gross rent multiplier is used instead).

**Reasoning and reporting.** The forecast's band-pairing step rests on a measured relationship between rent growth and price growth that turns out to be weak: r² never exceeds 0.10, so under 10% of the movement in one is explained by the other, and the correlation changes sign depending on the market. The pairing is disclosed as thin rather than presented as settled reasoning. A known limitiation is that live model calls are not perfectly deterministic even at temperature 0. OpenRouter also routes the same model to different deployments, and even pinned to one, scores swing from 0.05 to 0.95 on an identical prompt. Committed recordings are exact regardless, so this only impacts live runs.

**Potential Next steps**:

1. **Expose the pipeline itself as an MCP-callable capability.** Half the plumbing exists and is tested — the read-only server already exposes this project's data tools; the unbuilt half is exposing *the evaluation* as something another agent could invoke on a person's behalf. This could be useful to extend the forecasting to a third party real-estate service agent, for example.
2. **Make the retrieval relaxation choice a per-deal reasoning step** — The current relaxation-order is rule-based, but nuances of individual deals could result in differnet choices as the result of a reasoning step.
3. **Sample the forecast's scorer more than once and disclose disagreement**, rather than trusting a single draw from a model that had measured instability.
4. **Add operating-expense data** — the one addition that would move the system from a gross rent multiplier to a real return figure.

## 10\. Public GitHub repository

**<https://github.com/jelanigb/carnegie-mellon-agentic-ai>** — public, MIT licensed.

1. **README** — [`README.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md): project, architecture, setup, usage, and a plain statement of limitations. Written for *reviewing* rather than running.
2. **Source code** — [`src/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src): the seven agents in [`src/agents/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/agents), graph assembly in [`graph.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/graph.py), state schema in [`state.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/state.py), every tunable parameter in [`config.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/config.py).
3. **Sample inputs** — the eight demo listings in [`src/demo_deals.py`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/src/demo_deals.py); [`docs/demo.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/demo.md) explains what each exists to show.
4. **Sample outputs** — three sample reports: [`staten-island.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/staten-island.md) **escalates** at 0.00 and *still* recommends proceeding; [`los-angeles.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/los-angeles.md) reports at confidence 1.00 and recommends *Proceed*; ; [`overpriced.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/docs/sample_reports/overpriced.md) is the mirror, confident at 1.00 with the *deal* as the problem.
5. **Evaluation artifacts** — Eval inputs in [`src/eval/data/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/eval/data) and eval results in [`src/eval/results/`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/tree/main/src/eval/results)
6. **Review instructions** — The Readme has a [section pointing to project evidence](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md#where-the-evidence-already-lives) and a [section for running the project](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/README.md#running-it). The source datasets are not committed — the rental corpus alone expands to 97 MB — so [`data/README.md`](https://github.com/jelanigb/carnegie-mellon-agentic-ai/blob/main/data/README.md) names every dataset, its source, its license and the command that consumes it. Three files are fetched by hand: the corpus ([Apartment for Rent Classified](https://archive.ics.uci.edu/dataset/555/apartment+for+rent+classified), UCI ML Repository, CC BY 4.0), Zillow's rent index and a Redfin export. The Census boundary layers download themselves, and the vector index is *built* from the corpus by one script rather than shipped. The *trained* model artifact does ship, so scoring a listing works out of the box. **The evaluation is the deliberate exception and is the part a reviewer should run** — its inputs are committed in full, so running `python -m eval.runner --tier golden` reproduces every figure with no external calls, no API keys and no missing data.
