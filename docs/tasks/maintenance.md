# Maintenance tasks — not tied to a unit

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#20) refer to
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

### M3 ✅ — Rename `_resolve_geography`'s `supplied` parameter *(done Aug 28, 2026)*

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

**Done Aug 28, 2026**, ahead of U8.2 rather than after it, since U8.1/U8.1b had just been
committed and the rename could land on a clean tree as its own change set — which is what
§8's separation rule is actually for.

Six substitutions in `agents/extractor.py`: the signature, both `is not None` branches, the
`haversine_miles` call, the conflict message's two interpolations, and the keyword call site
at the geography-only path. The positional call site needed no change.

**Every other occurrence of "supplied" in the file was left alone, deliberately** — they are
English ("caller-supplied coordinates"), not the identifier, and rewriting prose to match a
parameter rename would have made the diff harder to review for no gain. One docstring line
*did* change, because it referred to the parameter by name rather than describing the idea.

**Both renamed branches were executed rather than only compiled.** A rename that breaks an
unexercised branch passes a test suite silently, so each was run against a live geocode: the
conflict branch (coordinates 3.12 mi from the resolved parcel → `SUPPLIED_COORDINATES_CONFLICT`,
message rendering correctly across the re-wrapped f-string) and the fallback branch (an
unresolvable address → `GEOCODING_UNAVAILABLE`, caller coordinates used as given). 60 tests
pass.
