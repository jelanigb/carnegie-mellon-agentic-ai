# Where reasoning lives in this system

**What this document answers:** how many places in this pipeline exercise *judgment*, what
kind each one is, and — the part that matters more — where judgment was deliberately kept
out. Written because "agentic" is easy to claim and hard to point at, and because the
honest inventory here is smaller and more specific than the phrase implies.

Companion documents: [`architecture.md`](architecture.md) (§3, §4) for the topology these
loci sit in, [`evaluator.md`](evaluator.md) for what the forecast's search actually scores,
and [`recommendation.md`](recommendation.md) for the two axes the Critic's cross-check
annotates.

## The boundary this document draws

**Reasoning here means a model exercising judgment over evidence, or an agent running a
Reason/Act/Observe/Decide loop over its own results.** Two things are deliberately outside
that line, and saying so is the point of drawing it:

- **The learned models are not reasoning loci, and that says nothing against them.** The rent
  regressor (gradient boosting, `tools/model/rent_model.py`) and the comp embedder
  (`sentence-transformers/all-MiniLM-L6-v2`, `tools/vector_store.py`) each produce one thing
  — a number, a ranking — and neither weighs alternatives, revises on observation, or
  declines. What *is* a reasoning locus is the loop built on top of the second one: the
  Comps agent's adaptive RAG loop re-queries the vector index on what the last query
  returned. The embedder is the substrate that loop searches over; the judgment is in the
  loop.
- **Deterministic rules that make decisions** — the Planner's routing, the confidence sum,
  the escalation rule, the recommendation verdict — are the system's most consequential
  judgments and *none* of them is a model call. That is a decision, recorded below, not a
  gap.

## The four places a model is asked to judge

Seven model calls on a full run, across four of the seven agents:

| Agent | Calls | What the model is asked for | What it cannot do |
| --- | --- | --- | --- |
| **Extractor** (`agents/extractor.py`, `_extract_terms`) | 1, plus schema-repair retries | Turn an unstructured listing into typed deal terms, naming its own assumptions and clarifying questions | Estimate a value the listing does not state — rents, price and per-unit figures are read, never inferred |
| **Scenario/Forecast** (`agents/scenario_forecast.py`, `_make_scorer`) | 4 — two per beam level, two levels | **Two distinct roles.** First: choose which read-only evidence tools to pull. Second: score enumerated candidates 0.0–1.0 with a rationale | Propose a hypothesis or a growth rate. The space is enumerated, not sampled (#17) |
| **Critic** (`agents/critic.py`, `cross_check`) | 1 | Reach its own verdict on the deal from the same evidence the rule read | Change the verdict. It annotates; the rule decides |
| **Summarizer** (`agents/summarizer.py`, `_lede_section`) | 1 | Write the report's opening paragraph | Reach a conclusion, choose what the report contains, or quote a disclosure |

An extraction call is skipped where the Planner routes around the Extractor (decision #9 —
deal terms already complete), so a golden-tier eval row costs six.

### 1. The Extractor — natural language into typed terms

The only locus whose job is comprehension rather than judgment, and the only one where the
model's output is *load-bearing* rather than additive: every downstream figure rests on the
terms it returns. What contains that risk is the schema, the closed set of assumptions the
model must declare, and the rule that a stated value is never recorded as an inference —
"three-family home" states its unit count, "triplex" infers it, and only the second earns an
assumption, because every assumption lowers the deal's confidence score.

### 2. The forecast — the model judges an enumerated space, and pulls its own evidence

This is the deepest reasoning in the build and the only place a search runs. Two things about
it are easy to state backwards:

- **The model does not forecast.** Four framings and nine band pairings are *enumerated* from
  measured series (#17 — asking a model for five hypotheses over a four-point space would make
  it invent growth rates). Its job is to rank and to prune, never to produce a number.
- **The evidence-selection call is a real tool-use loop**, not a formality. The menu is read
  from the MCP server's own `list_tools()` (#13), so the descriptions the evaluator reads are
  the ones the server publishes, and the tools it calls are the same objects an external MCP
  host reaches. Bounded by `config.TOT_MAX_EVIDENCE_CALLS`; a tool that raises is reported
  back as unavailable rather than ending the node.

When the model is unreachable, `_heuristic_scores` scores on how far a pairing departs from
the neutral case. **That is a degradation, not a parallel rules-based comparison** — it runs
only in the model's absence, and says so in the rationale text that reaches the report.

### 3. The Critic — a second verdict, which can never become the verdict

**"Independent" means independent of `critic.recommend`**, the deterministic rule that
produces the report's actual recommendation from the asking-price premium against ZIP or
metro sale percentiles, plus whether the comp cross-check corroborated the rent. The model is
handed that same evidence in the rule's own rounded figures — and deliberately **not** the
confidence score, the flag list, or whether the deal escalated, since those are axis 1 and a
second opinion that read them would be answering the first line's question over again.

Its verdict lands beside the rule's on `RecommendationDetail.model_verdict`. The report prints
the rule's, and prints a footnote **only where the two differ** (`RecommendationDetail.cross_check_disagrees`).
The disagreement is disclosed rather than resolved, because a deal both readings agree on is a
more comfortable one to hold than a deal they split over.

**Why the asymmetry is load-bearing:** this model scores an identical prompt 0.05 on one call
and 0.95 on the next at `temperature=0` (OQ-17). A design where the model decided would make
the same deal proceed on Tuesday and not on Wednesday, and the eval harness could score
neither outcome. This exists (U9.4, from OQ-22) because once decision #12's Critic half was
retired on evidence at U7.7, the forecast's search was the *only* place a model exercised
judgment in the build — a system described as agentic rested that claim on one node.

### 4. The Summarizer — prose, and nothing else

It renders the verdict the rule reached and cannot restate it differently. It is handed
counts of the disclosures rather than their text, after two live runs mis-relayed excerpts —
"limited comparable data" on a run whose comp set was full, and a *rental* comp count
described as recorded sales. Every disclosure it summarizes is printed in full directly
beneath it, so no reader depends on the paragraph. On failure it renders a sentence saying so
rather than raising a flag.

## The Reason/Act/Observe/Decide loops

Every agent in this build states its loop in its own module docstring, and three of them run
one that genuinely iterates. They are the loops where an agent acts, reads the result of its
own action, and chooses the next action from it — which is the property that separates this
system from a chain of prompts, and it holds whether or not a model is in the loop.

- **The schema-repair loop** (`tools/llm_client.py`, `call_with_schema`) — the tightest ReAct
  loop in the system, and the only place a model is asked to correct itself. A response that
  fails Pydantic validation is not an error to swallow: the `ValidationError` text and the
  rejected response are appended to the prompt and re-sent, so the model is told precisely
  what was wrong. Bounded by `config.MAX_EXTRACTION_RETRIES`; exhaustion raises, and the
  caller decides how to degrade. The attempt count is returned to the caller so a run that
  needed three tries is visible afterward rather than silently identical to one that needed
  one.
- **The adaptive RAG loop** (`agents/comps_retrieval.py`) — **this system's retrieval
  augmentation, and it is agentic rather than single-shot.** Each pass runs a *hybrid* query
  against the ChromaDB comp index: hard constraints — geography, bedroom count, an optional
  size band — as exact metadata filters, and embedding similarity over description and
  amenity text ranking whatever survives them (`tools/vector_store.query_comps`). The split
  is deliberate: a two-bedroom near the subject is either in the candidate set or it is not,
  while *renovated*, *garden level* and *walk-up* are exactly what no structured column
  captures. The subject's quantitative attributes are kept **out** of the embedded query
  text, so fuzzy matching cannot reintroduce error into constraints that were already exact.

  The loop is the reasoning. A shortfall in what comes back is an observation, not an error:
  the agent concedes exactly one criterion, raises a flag naming what it gave up, and
  **re-queries the index with the adapted parameters** — up to `config.MAX_RETRIEVAL_ITERATIONS`
  times, exiting with a sparse-comps disclosure rather than presenting a thin set as a full
  one. It then measures what the widening actually admitted, which is a separate question from
  whether it happened: relaxing a filter *permits* dissimilar comps without producing them,
  and only measured drift raises `COMPS_OUTSIDE_MATCH_CRITERIA`. The module docstring's
  closing line is the case for the whole design: *a single prompt has no way to inspect the
  result of its own retrieval and adjust*.
- **The bounded rework cycle** (`agents/critic.py` → `agents/planner.route_after_critic`) —
  the graph's one back edge. The Critic observes contradictions that exist only in the
  *combination* of upstream flags, and decides between reporting, one more pass, and
  escalation. Pure functions over accumulated state, bounded by `config.MAX_REWORKS`.

## Where a model was deliberately declined

Recorded because these are the load-bearing decisions, and each was taken on evidence rather
than on cost:

| Where | Why no model |
| --- | --- |
| **Confidence score, escalation, consistency checks** | Pure functions over the accumulated flag list. Decision #12 reserved the Critic for Tree-of-Thought; U7.7 retired that half on evidence — what shipped has no generated candidates and nothing to search over |
| **The recommendation verdict** | Deterministic under OQ-17's measured variance, so the same deal reaches the same verdict twice and the eval harness can score it (U9.4) |
| **Planner routing** | Pre-flight, not supervisor (#9). The pipeline order is fixed by data dependency, so there is nothing to choose between |
| **The comp relaxation order** | The loop adapts; *which* criterion it concedes is a fixed ladder inherited from U4. Whether that choice should be a per-deal judgment is open as OQ-24, gated on measuring comp comparability first |
| **A rent figure when the anchor path fails** | Cut in advance (§6 cut list item 3, tagged at `agents/valuation_rent.py`). An unanchored model rent figure is the exact failure §2 exists to prevent; shipping one needs the grounded-vs-ungrounded comparison `scripts/retrieval_ablation_llm.py` did for comps, repeated for rents |

**The through-line: the model proposes and the rules decide.** Every model call in this system
is either upstream of a rule (extraction, scoring) or beside one (the cross-check, the lede).
None of them is the last word on anything a reader acts on — which is what keeps a
non-deterministic component inside a system whose results are meant to reproduce.
