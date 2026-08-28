# Maintenance tasks — not tied to a unit

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#17) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

### M1 — Name the decision at every citation site

~50 code comments cite decisions bare (`decision #9`, `§7 decision #4`). A reader who does
not already know what #9 was has to leave the file to find out. Append a short gloss at
each site — `decision #9 (Planner topology)` — matching the names now in §7's register.
Comment-only; no logic. Sites: `graph.py`, `config.py`, `state.py`, `critic.py`, `tot.py`,
`planner.py`, `mcp_server.py`, `llm_client.py`, `fmr_history.py`, `geocoding.py`,
`county_crosswalk.py`, `main.py`, and six scripts.

### M2 — Audit the remaining agents' flag messages for internal vocabulary

The Aug 24 rule (§8, "Reader-facing text carries no internal vocabulary") was applied to
the Critic's objections and one Summarizer line. A scan of every non-docstring string in
`src/` found 28 carrying internal vocabulary; **25 of those are legitimately
developer-facing** — evidence scripts under `scripts/`, test assertions, and
`tools/llm_client.py`'s "update config.py" error, all of which are read by someone with
the repository open and should keep citing precisely.

What is worth a pass: `main.py`'s CLI help text mentions "the U4 ablation", which a demo
audience could see. Low priority, comment-and-string only. Reproduce the scan with the
AST walk that found them — string constants that are not docstrings, matched against
`§\d`, `#\d+`, `\bU\d`, `config\.[A-Z_]+`.

### M3 — Rename `_resolve_geography`'s `supplied` parameter

**Raised Aug 28, 2026 by the architect**, reviewing U8.1b. `agents/extractor.py:224` takes
`supplied: Optional[tuple[float, float]]`, and the name says where the value came from
without saying what it is — a reader has to check the annotation to learn it is a
coordinate pair at all.

Contained: the signature, ~8 references in the body, and two call sites (`extractor.py:383`
and `:427`), all within `agents/extractor.py`. No test or script references it. Rename only;
no logic.

**Settled Aug 28, 2026: `supplied_lat_long`.** The original instruction was `lat_long`,
which fixes the type ambiguity on its own. `supplied_lat_long` was preferred because
`_resolve_geography`'s entire job is comparing the *caller's* coordinates against the
*geocoder's* — `parcel.latitude`, `resolved.latitude` are both in scope — so a bare
`lat_long` would have resolved one ambiguity by creating another: which of the two?

**Sequenced after U8.2 is committed**, per §8's rule that maintenance lands separately from
logic.
