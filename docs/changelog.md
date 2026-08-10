# Changelog

**Chronological record of code changes.**
Author: Jelani Gould-Bailey · Last updated: Aug 10, 2026

## Why this file exists

The build is sequenced by dependency and technical risk rather than by the syllabus
calendar — see `implementation_plan.md` §6 for that decision and its rationale. Units
therefore land out of order relative to the order the program teaches and assesses the
material: retrieval (U4) shipped before the walking skeleton (U2), and code feeding
Checkpoint 6.1 exists before the checkpoints between them are due.

That trade is worth making, but it costs traceability: with unit order decoupled from
checkpoint order, nothing otherwise maps shipped code back to the requirement it
satisfies. This file is that map.

## What belongs here

**Code changes, not decisions.** Decisions live in `implementation_plan.md` — the §7
decisions log for open questions, and the per-unit sections for reasoning and findings.
A decision that has not produced code is not a changelog entry. Where a change needs
justification, the row cites the plan section rather than restating the argument.

**One conceptual change per row, however many files it touched.** A change spanning an
agent, a state field, and a config entry is one row naming all three; it is not three
rows. The unit of a row is the change, not the file.

## Conventions

- `##` heading per date the work was **done**. Newest date first.
- **Date added** is when the row was written, which is the same day for work logged as
  it lands and a later date for anything backfilled. Rows are ordered newest-first by
  that date, so retroactive entries are visibly retroactive rather than quietly folded
  into the original day's record.
- **Related checkpoint** names every checkpoint a change feeds, or `maintenance` for
  work that serves none — hygiene and defect repair are real work, and forcing a
  checkpoint onto them would make the column less trustworthy everywhere else.

---

## Aug 10, 2026 — U2, walking skeleton

| Date added | Unit | Work done | Related checkpoint |
| --- | --- | --- | --- |
| Aug 10, 2026 | U2 | **Graph assembly.** `graph.py` — eight nodes wired on the pre-flight Planner topology, one `Critic → Planner` back edge, two conditional edges, compiled with a checkpointer; conditional-edge targets validated against `nodes.ALL_NODES` at import | 5.1 |
| Aug 10, 2026 | U2 | **Planner and routing.** `agents/planner.py` — writes the execution plan into state and owns both `route_*` functions; `state.py` gains `plan` and `planner_invocations`, the latter making the "at most `1 + rework_count` invocations" invariant assertable | 5.1 |
| Aug 10, 2026 | U2 | **Bounded rework cycle.** The counter increments on Planner re-entry rather than on Critic rejection, so escalation is not miscounted as rework; exhaustion routes to human review instead of raising `recursion_limit` | 5.1, 6.1 |
| Aug 10, 2026 | U2 | **Human-review escalation.** `agents/human_review.py` — `interrupt()` node surfacing confidence, warn/critical flags and unanswered questions; resumes from checkpoint into the Summarizer; `state.py` gains `human_review_note` | 6.1 |
| Aug 10, 2026 | U2 | **Critic confidence and escalation.** `agents/critic.py` — flag-severity aggregation using the `config.py` weights, escalation decision, and `_consistency_objections()` as a live seam for U7's cross-agent checks. Derived flags excluded from their own score to prevent feedback across rework passes | 6.1 |
| Aug 10, 2026 | U2 | **Escalation defect fixed.** A lone critical flag scored exactly at the 0.60 threshold and failed to escalate, so zero-comparable deals reported as ordinary results. `agents/critic.py` now escalates on low confidence **or** any critical flag; `agents/summarizer.py` banner reworded to stop attributing every escalation to the score. Regression test added (plan §6, finding 1) | 6.1 |
| Aug 10, 2026 | U2 | **Summarizer.** `agents/summarizer.py` — real markdown, disclosure-first: every flag rendered in full with its source agent and severity guidance, comp table with `listing_source`, source-concentration disclosure, and absence stated rather than omitted | 2.1, 6.1 |
| Aug 10, 2026 | U2 | **Stubbed specialists.** `agents/extractor.py` (deterministic regex parse, real `unresolved_field` flags and crosswalk county lookup), `agents/valuation_rent.py`, `agents/scenario_forecast.py`. Stubs emit no estimates, so no unanchored figure reaches the report; `state.stub_nodes` carries build status outside the flag stream | 5.1 |
| Aug 10, 2026 | U2 | **Flag-propagation test suite.** `tests/test_flag_propagation.py` (14 cases) and `tests/conftest.py`; `pytest` added to `requirements.txt`. Covers first-node-to-report propagation, multi-agent accumulation, all three reducer annotations incl. the negative case on `comps`, full-text rendering, cycle termination, and interrupt/resume | 6.1 |
| Aug 10, 2026 | U2 | **Generated architecture diagram.** `scripts/export_graph_diagram.py` renders `docs/diagrams/deal_evaluator_graph.{mmd,png}` from the compiled graph and asserts the topology — one back edge, two branching nodes, all declared nodes registered. The hand-drawn placeholder in `lang_graph_onboarding.md` §4 was deleted and replaced with the generated output | 5.1, 7.1 |
| Aug 10, 2026 | U2 | **Entrypoint.** `main.py` — five runnable paths (dense, moderate, thin, no-coordinates, retrieval-off), interrupt/resume handling, and a SQLite checkpointer | 5.1, 7.1 |
| Aug 10, 2026 | U2 | **Observability wiring.** `tools/tracing.py` — env-driven LangSmith project setup that reports on every run whether tracing is actually on, so a run believed captured and silently not captured is not a failure mode | 5.1 |
| Aug 10, 2026 | U2 | **Checkpoint serialization.** `graph.state_serde()` registers the six state types with LangGraph's msgpack allowlist, clearing deprecation warnings that would have blocked the resume path in a future version and switching deserialization to deny-by-default | 6.1, maintenance |
| Aug 10, 2026 | U2 | **HUD cache hardening.** `tools/hud_fmr.py` — `_DiskCache.set()` now writes to a temporary file and renames atomically, so a crash mid-write can no longer truncate the accumulated cache. Clears `TODO(U2)`; residual concurrency limit documented as accepted | maintenance |
