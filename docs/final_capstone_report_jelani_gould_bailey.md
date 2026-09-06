# Carnegie-Mellon Agentic AI Program: Capstone Checkpoint 7.1

# Multi-Family Residential Deal Evaluator

**Author:** Jelani Gould-Bailey  
**GenAI Research Assistance:** Anthropic Claude Opus 5  
**Coding Assistance:** Claude Code  
**Last Major Update:** Sept 5, 2026

## 1\. Project Title

Multi-Family Residential Deal Evaluator

## 2\. Problem and user

This seven-agent system helps residential real estate investors evaluate small multi-family (2-4 unit) properties as investment opportunities. Given a property listing as input, it automates and reasons through the work needed to produce an investor-facing report: extracting deal terms, retrieving relevant comps, estimating rent against real-world data, forecasting scenarios, and authoring the aggregated, transparent deal report.

One challenge today is that the small multi-family segment has far less available data than single-family homes, and a robust evaluation requires several kinds of judgment: comparable-property analysis, rent estimation, and forward-looking scenario forecasting. Individual investors typically do this manually, using rules of thumb and static calculators.

### User Base:

1. **The Investor** — reads the final report and decides whether to invest. They are the end customer; clean reports go to them without edits.  
2. **The Real Estate Agent** — presents the report to the Investor. Certain flags route the draft to the Agent for human review, to decide how to frame the findings and disclosures.  
3. **The IT Specialist** — supports the Real Estate Agent, and steps in when system-generated errors during report generation require a closer look.

Why an agent and not a spreadsheet? Because the arithmetic isn't the hard part. The hard part is what to do when the evidence runs thin. Widen the comparable search, or report that you couldn't? Trust the listing's stated rent, or the model's? Those are sequential decisions where each one changes the next — and every one of them needs to be disclosed.

## 3\. System goal and scope

The system ingests a text-based multi-family listing and generates a report for The Investor. Success is a complete report with the property's data and suitable comparables, a rent-growth forecast, a value-appreciation forecast, and transparent disclosure of anything noteworthy or difficult encountered along the way. Depending on the nature and number of disclosures, the report may be flagged for closer review by the Real Estate Agent or the IT Specialist.

The report must answer 2 distinct questions: ***"Can the system stand behind its own numbers?"*** and ***"Is this a good deal?"***

Scope boundaries: three tuned markets (Chicago, Los Angeles, Cleveland, plus New York in the comp index); no single-family homes and no properties above 4 units. The agentic system is a forecaster providing decision support — it has no write access and does not purchase anything or complete transactions on behalf of The Investor.

## 4\. Final system architecture

A seven-agent pipeline orchestrated as a [LangGraph](https://github.com/langchain-ai/langgraph) state graph, with an eighth node that is an explicit human-in-the-loop pause.

![The compiled graph: start to planner, then extractor, comps_retrieval, valuation_rent, scenario_forecast, critic — which branches to human_review, back to planner, or straight to summarizer](diagrams/deal_evaluator_graph_lr.png)

*Generated from the compiled graph, not drawn. Dotted edges are conditional.*

### Agents

1. **Planner** — pre-flight: inspects the deal, decides which steps run, and owns every routing decision in the graph.  
2. **Extractor** — parses the listing into typed deal terms and geocodes the address, naming every assumption it has to make.  
3. **Retrieval** — RAG over a rental corpus in a vector store; relaxes its criteria one step at a time when matches are sparse, flagging each concession.  
4. **Valuation** — a custom gradient-boosted rent model anchored to a market rent index at the property's ZIP, cross-checked against the retrieved comps.  
5. **Forecast** — Tree-of-Thought search over rent-growth and price-appreciation scenarios, scored by an LLM and pruned to a beam of survivors.  
6. **Critic** — cross-agent consistency checks, confidence scoring, the buy/pass recommendation, and the decision to report, rework or escalate.  
7. **Summarizer** — renders the report, surfacing every upstream disclosure rather than only the headline numbers.

### Coordination, state and memory

The pipeline is **strictly sequential with exactly one cycle**. Ordering is fixed by data dependency rather than chosen at runtime — Valuation consumes the comps, Forecast the rent estimate — so there is no parallelism or fan-out. The Planner is **pre-flight, not a supervisor**: it writes a plan into state once, and a conditional edge reads it.

Memory is a typed Pydantic state object on a SQLite checkpointer, and agents communicate strictly through it: every node returns a partial update, no agent directly invokes another, and routing functions return a node name carrying no payload. Disclosures accumulate through an append-only reducer. This ensures clear auditability: no agent can directly shape what a later one receives, and the Critic ends up checking evidence no upstream agent could have tailored for it.

The single back edge (Critic → Planner) and every loop in the system are bounded by an explicit counter. Human intervention is triggered by a LangGraph `interrupt()` call that pauses the graph and surfaces the reason why.

### Reasoning, retrieval and tools

The system is a hybrid, mixing deterministic logic with LLM calls. A full run makes **seven model calls across four of the agents**, but the most consequential judgments — confidence scoring, escalation, routing and the buy/pass verdict — are deterministic functions over accumulated state rather than model calls.

- **Tree-of-Thought (Forecast)** runs beam search over an enumerated space: four framings of which years feed each series, then nine rent-band/price-band pairings. The model ranks and prunes; it never produces a growth rate. Every candidate and its prune reason reaches a ledger printed in the final report.  
- **Adaptive RAG (Retrieval)** is a reason/act/observe loop. A shortfall is treated as an observation: concede one criterion, name it, then re-query.  
- **Tools** come from a read-only MCP server, whose `list_tools()` builds the Forecast evaluator's menu (so the tool surface has one definition rather than two that can drift).  
- **Logging** is LangSmith tracing across every node; **evaluation** invokes this same compiled graph.

### Core architectural principles

**Transparent Degradation, enforced structurally.** An agent proceeding on incomplete or relaxed evidence attaches a named, severity-graded flag defined in an enum, making coverage of the failure modes countable. An append-only reducer makes disclosure loss impossible.

**Two axes, never merged.** The system’s 2 central questions (confidence in the system's numbers and the quality of the deal) are computed by different rules and rendered separately. Neither is an input to the other, so a deal can escalate for review and still be worth buying.

**The model proposes, but the rules decide** — every model call sits upstream of a rule or beside one, never as the last word.

**Measure rather than assume** — every load-bearing assumption was tested against real data, and several failed: the original metro selection, the sparse-market case, and the rent/price relationship the forecast was built on.

## 5\. Design evolution across the program

While the pipeline's stages remained stable since the early days of the project, many other parts of the project changed, often driven by new data.

**Data sources moved closer to the estimate.** Comps and rent-model training draw on a UCI apartment-rental corpus of \~99,000 listings from 2018–19 which has beds, baths, square footage, coordinates and rent together at unit level. However, because it is seven years stale, the model learns each rent as a *ratio* to a published index rather than as a dollar figure, then multiplies by today's index.

That makes the index a first-order choice, and my first one was wrong. HUD Fair Market Rents are county-level, annual, and pitched at the bottom 40% of the market; the evaluation harness caught FMR rising \+51.9% since the corpus vintage against market rent's \+33.5% (an 18-point bias in every estimate). The anchor is now a hybrid — Zillow's ZIP-level monthly index for market rent, HUD for the bedroom step Zillow does not publish — and **both ends of the ratio read the same series**, so drift divides out instead of multiplying through. Per-metro error fell from $981 → $855 in New York and $454 → $343 in Chicago. On the price side, a metro median gave way to ZIP-level assessor sales.

**Several planned capabilities were eliminated because they lacked supporting evidence.** ZIP-level appreciation and property-level value estimates were both dropped due to insufficient data coverage. Tree-of-Thought was not added to nodes where deterministic logic yielded better decisions.

**The evaluation harness now measures every claim.** Coverage of the 30 typed disclosure flags went from 60 → 100%. As more cases were added, they exposed several logic failures in the system.

**The rent model evolved from linear regression (LR) to a gradient-boosting regressor (GBR)** on cross-validated (CV) evidence. The initial LR training run used an 80/20 spit and no CV. I ran 5-fold CV when revisited feature engineering and modelling, and tested 3 different models. MAE dropped from $513.67 (LR) to $450.71 (GBR), with only a moderate increase in train-versus-holdout gap ($18.34). Random forest was also evaluated but had mixed results.

**Transparent Degradation matured from an architecture principle into a typed, routed object.** The idea began as "append a flag to a list," then became a closed enum so coverage could be counted; then severity grades were added, so a single disqualifying observation escalates on its own rule regardless of the confidence score. It further evolved into a scope classifier separating disclosures about target property from those about its market. It also became a routing classifier: when the graph halts at its human-review `interrupt()`, which human sees the report is determined by the disclosure types.

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

I used Anthropic's Claude Code extensively in this project. Early in the project I decided it was most efficient for me to play an architect role: delivering the overall architecture and design and making key implementation decisions along the way. I also wore a "chief data scientist" hat when working on the model. The bulk of the coding was done by Claude Code, with me reviewing all commit candidates, providing feedback, changes and final approval. Although I am strong in Python, this arrangement allowed for much greater scalable execution than would have been possible with me writing all of the code firsthand (especially given the 7-week project window).

## 7\. Evaluation and results

**Every evaluation number comes from a batch harness that invokes the same compiled graph the production entry point runs**, so a result cannot come from a code path that has drifted. The batch is **30 cases** — golden fixtures with deal terms supplied, replay cases running the Extractor against recorded responses, and the eight demo listings plus one ablation — all of which replay from a fresh clone with no live model call. Twenty-one cases are engineered to trip a specific disclosure, and **every case declares its expected outcome before the run**; without that the exercise is self-confirming, since demo listings are calibrated to run *clean* and engineered ones to *fail*.

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

**Beyond the table:** Of the 30 cases, 14 report and 16 escalate to human review — and both escalation grounds that operate independently of the confidence score are demonstrated rather than asserted: **8 deals escalated on a single critical disclosure** where the score alone would have let them report, and **1 on an exhausted rework budget**.

**Two caveats:** That escalation rate describes the *fixtures* rather than the agent, since most cases were engineered to trip something. And only the first of the report's two axes is scored: whether the property is a good buy has no ground truth here, because the target property listings are synthetic and no sale ever happened. The thresholds behind that axis do rest on real sales, however — 44,358 recorded transactions across 222 ZIP codes, from New York City Department of Finance and Cook County Assessor records.

## 8\. Safety and reliability considerations

**The system's entire risk surface is the report**. The system takes no action and holds no write access. So the characteristic failure is not a wrong number but a wrong number presented as a right one: plausible, well-formatted, confidently stated, with nothing solid underneath it.

**System-level guardrails:** No agent invokes another or hands data to another; every node returns a partial state update rather than the whole mutated object. The disclosure channel is append-only by construction. Every cycle is bounded by an explicit counter in the state object, never by the framework's recursion limit. Hitting a framework limit throws an exception and ends the run with no report at all; hitting a counter exits the loop, raises a disclosure naming what was exhausted, and routes the deal to human review — so the reader still gets a report, and it says what happened. The MCP tool surface is read-only by design to avoid risks created with writes.

**Agent-level guardrails:** Extraction is schema-validated with bounded retries: on rejection, a validation error and rejected response are fed back into the prompt, and after three attempts the agent writes no deal terms at all and raises a critical disclosure. I decided not to include a fallback regex parser as I was concerned it may be difficult to keep up-to-date.

The geocoder will not invent a coordinate; it offers three tiers of granularity and discloses which one fired. Only retryable errors get a rework pass. A target property whose bedrooms, bathrooms or floor area fall outside the ranges the model was trained on is refused rather than priced.

**Human oversight:** Three independent conditions pause the graph: confidence below 0.60, **any single critical disclosure regardless of score**, and an exhausted rework budget with an objection outstanding. Escalation is checked before rework, so a deal the system knows a human should see doesn't get re-run. The `interrupt()` surfaces the *grounds* for stopping — the confidence score, every warn-or-critical disclosure, and any unanswered clarifying questions — rather than a state dump a reviewer cannot act on. A routing rule then picks the desk: infrastructure disclosures such as an unreachable geocoder or model go to the IT Specialist, while deal-substance disclosures go to the Real Estate Agent. This escalation methodology was intentional: for an investment tool I decided that being wrong silently is worse than occasionally escalating too many deals to the Real Estate Agent for review.

## 9\. Limitations and next steps

### Limitations:

**Data.** There are a number of opportunities to add additional data in the future. The comp corpus is 2018–19 vintage and 91% from one aggregator; more variation and newer data would be useful. The rent model was trained on eight metros, and transfer to an unseen market costs \~13%. New York carries the largest per-market error, and measurement showed more New York data would not close it: holding New York out of training entirely moves the figure only 2%, so the cause is within-ZIP rent dispersion that three location-blind features cannot recover — a property of the feature set rather than of the corpus. The ZIP-level sale benchmark also has limitations \-- by law, California publishes assessed value rather than transaction price. And there is no cap rate or net operating income calculation, because this project has no operating-expense data (gross rent multiplier is used instead).

**Reasoning and reporting.** The forecast's band-pairing step rests on a measured relationship between rent growth and price growth that turns out to be weak: r² never exceeds 0.10, so under 10% of the movement in one is explained by the other, and the correlation changes sign depending on the market. This pairing is disclosed as thin rather than presented as settled reasoning.

**LLM non-determinism.** Model calls are not perfectly deterministic even at temperature 0\. OpenRouter routes the same model name to different backend deployments, so two calls may not be apples-to-apples — and even pinned to one deployment, scores swing from 0.05 to 0.95 on an identical prompt. Committed recordings are exact regardless, so this affects only live runs.

### Potential Next steps:

1. **Expose the pipeline itself as an MCP-callable capability.** Half the plumbing exists and is tested — the read-only server already exposes this project's data tools; the unbuilt half is exposing *the evaluation* as something another agent could invoke on a person's behalf. This could be useful to extend the forecasting to a third party real-estate service agent surfaced on a broker’s site or market site, as a real-world example.  
2. **Make the retrieval relaxation choice a per-deal reasoning step**. The current relaxation-order is rule-based, but nuances of individual deals make this a better fit for Tree of Thought with some guidance.  
3. **Sample the forecast's scorer more than once and disclose disagreement**, rather than trusting a single draw from a model that had measured instability.  
4. **Add operating-expense data** — the one addition that would move the system from a gross rent multiplier to a real return figure.

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