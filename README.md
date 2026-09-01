# Multi-Family Deal Evaluator

A capstone project for Carnegie Mellon's Agentic AI executive-education program: an
agentic pipeline that evaluates small multi-family (2–4 unit) residential listings as
investment candidates, and discloses — rather than hides — every place its own evidence
runs thin.

**This README is written for reviewing vs. running yourself.** The graded artifact is
whether the project holds up to inspection, so the sections below lead with where the
evidence already lives (sample reports, evaluation results, the graph diagram).

## What it is

A seven-agent pipeline, orchestrated as a [LangGraph](https://github.com/langchain-ai/langgraph)
graph with an explicit human-in-the-loop pause:

1. **Planner** — inspects the deal, decides which downstream steps run, routes between
   agents, governs retries and escalation.
2. **Extractor** — parses an unstructured listing into structured deal terms, resolves
   the address to coordinates, raises clarifying questions on anything it can't resolve.
3. **Comps/Retrieval** — a RAG comp finder over a rental-listings corpus (ChromaDB +
   sentence-transformers), adaptively relaxing search radius and match criteria when
   matches are sparse, and flagging when it does.
4. **Valuation/Rent** — a gradient-boosted rent regression model, anchored to a
   ZIP-level market rent index, cross-checked against the retrieved comps.
5. **Scenario/Forecast** — a Tree-of-Thought search over rent-growth and
   price-appreciation scenarios, scored by an LLM and pruned to a beam of survivors.
6. **Critic/Reviewer** — checks consistency across upstream outputs, aggregates every
   disclosure into a confidence score, and routes low-confidence or contradictory deals
   to a human-review pause rather than reporting them as settled.
7. **Summarizer** — renders the final report, required to surface every upstream
   disclosure rather than only the headline numbers.

**The unifying design principle is Transparent Degradation:** whenever an agent proceeds
on incomplete, relaxed, or stale evidence, it attaches a named, typed flag to its output
rather than absorbing the gap silently. Flags propagate through the Critic to the
Summarizer, so a report always says *when and how* the system deviated from the ideal
path. This is enforced structurally, not just as a style rule — flag kinds are drawn from
a closed enum (`state.FlagKind`), and a dedicated test suite
(`tests/test_flag_propagation.py`) asserts that a flag raised anywhere survives every
downstream node and appears in the report.

A deal that the Critic can't stand behind pauses at a genuine LangGraph `interrupt()`
rather than degrading its own confidence claim — see `agents/human_review.py` and
`docs/design/personas.md` for who that pause is for and which desk it routes to.

## Where the evidence already lives

- **`docs/sample_reports/`** — two full reports the pipeline produced, committed as-is:
  `los-angeles.md` (a clean run) and `staten-island.md` (an escalated one, sparse
  comps). Read these before running anything — they're the fastest way to see what the
  system actually outputs, disclosures included.
- **`src/eval/results/results.md` and `sensitivity.md`** — the evaluation harness's
  output: a batch of 28 real and engineered cases run through the compiled graph, a
  flag-coverage census, and a sweep over the confidence-scoring weights. This is what a
  correctness or calibration claim in this project is actually measured against, and the
  inputs it runs on (`src/eval/data/`, `src/eval/cases.py`) are committed alongside it.
- **`docs/diagrams/deal_evaluator_graph.mmd` / `.png`** — the graph topology, generated
  directly from the compiled graph rather than drawn by hand
  (`scripts/export_graph_diagram.py`), so it can't drift from the code.
- **`docs/implementation_plan.md`** — the plan of record: what was built, in what order,
  every architectural decision with its reasoning (§7), and a document map to everything
  else in `docs/`.

## Running it

```bash
cd src
.venv/bin/pip install -r requirements.txt          # or: python -m venv .venv first

# Two API keys, read from the environment:
export OPENROUTER_API_KEY=...    # LLM access, via OpenRouter
export HUD_FMR_TOKEN=...         # HUD Fair Market Rent API (free account)

.venv/bin/python main.py --deal los-angeles         # dense market, clean run
.venv/bin/python main.py --deal staten-island       # thin market, escalates to review
.venv/bin/python main.py --deal chicago             # moderate: retrieval relaxes once
.venv/bin/python main.py --deal no-geography         # an address nothing can resolve
.venv/bin/python main.py --deal coord-conflict      # supplied coords vs. the address
.venv/bin/python main.py --deal overpriced          # asking price well above benchmark

.venv/bin/python -m pytest tests/ -q                # the two load-bearing suites
.venv/bin/python -m eval.runner --tier golden       # the eval batch, no live calls
```

**A fresh clone cannot run this beyond the two commands above using recorded data**
The trained rent model (`data/processed/rent_model.joblib`, ~140 KB) is committed, so
scoring a listing works out of the box. Two things are not committed, both
deliberately:

- **The source rental-listings corpus (Kaggle-licensed) and the ChromaDB comp index
  built from it.** Rebuild with `scripts/build_comps_index.py` once the source CSV is in
  place; `docs/design/data_sources.md` names where each dataset comes from.
- **The rent model's training data.** The model itself ships trained; retrain from
  scratch with `scripts/train_rent_model.py` if you have an alternate source corpus.

`src/eval/` is the exception to both: its inputs (golden fixtures, recorded LLM
responses, a geocode cache) are committed in full, so `eval.runner --tier golden` or
`--tier replay` reproduces the evaluation results above with no external calls and no
missing data — that reproducibility is the point of the tier split
(`src/eval/README.md`).

## Documentation map

`docs/implementation_plan.md` carries the authoritative one (with read-order guidance);
the short version:

- **`docs/implementation_plan.md`** — plan of record, architecture rationale, the
  decisions register (§7).
- **`docs/design/`** — what the system currently *is*: architecture, state schema, data
  sources and strategy, the evaluator, the personas this system is built for.
- **`docs/history/`** — how it got that way: a full decision log and a chronological
  changelog.
- **`docs/open_questions.md`** — everything currently unresolved, and what would close
  it.

## Stated limitations

This is a seven-week capstone build, not a production system, and several gaps are
disclosed deliberately rather than hidden:

- **The forecast's rent/price pairing search is being reworked.** The two sample reports
  above were read closely partway through the build and surfaced a real defect: the rent
  growth series and the price series were built by different methods over different
  windows, which the reports themselves show as an implausible pairing in places. The
  fix — re-sourcing rent growth to match the same market index the rent estimate is
  anchored to — is in progress; see `docs/implementation_plan.md` and
  `docs/design/evaluator.md` for the measurement behind it.
- **A sparse-market deal (e.g. `staten-island`) is not yet reproducible from a fresh
  clone.** Its live evaluation currently reads from a development cache rather than a
  committed recording, so a re-run can return a different comp count than the committed
  sample report shows. Recording it like every other evaluation tier is in progress.
- **Live model calls are not perfectly deterministic, even at `temperature=0`.**
  OpenRouter can route "the same model" to different backend deployments per request,
  and scores can swing meaningfully between otherwise-identical calls. This mainly
  affects the forecast's scenario-scoring step; a committed recording (the eval harness's
  `golden`/`replay` tiers) is exact regardless, since it never calls a model live.
- **There is no demo UI yet.** The pipeline runs from the command line
  (`main.py`) today; a Streamlit surface is planned but not yet built.
- **Test coverage is deliberately scoped, not exhaustive.** Two suites are load-bearing —
  flag propagation and the evaluation harness — and broad unit coverage was a deliberate
  cut, not an oversight; see `docs/implementation_plan.md` §8.
- **No cap-rate or NOI-based investment scoring.** This project has no operating-expense
  data (taxes, insurance, vacancy, maintenance), so it does not estimate net operating
  income and will not invent one. What it computes today is the asking price against a
  market benchmark; a gross rent multiplier (which needs nothing beyond data already in
  this project) is planned but not yet built.

## License

MIT — see `LICENSE`.
