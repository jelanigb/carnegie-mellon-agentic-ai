# Maintenance tasks — not tied to a unit

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#22) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

### M1 — Name the decision at every citation site

~50 code comments cite decisions bare (`decision #9`, `§7 decision #4`). A reader who does
not already know what #9 was has to leave the file to find out. Append a short gloss at
each site — `decision #9 (Planner topology)` — matching the names now in §7's register.
Comment-only; no logic. Sites: `graph.py`, `config.py`, `state.py`, `critic.py`, `tot.py`,
`planner.py`, `mcp_server.py`, `llm_client.py`, `fmr_history.py`, `geocoding.py`,
`county_crosswalk.py`, `main.py`, and six scripts.

**Reconfirmed by documentation audit, Aug 31, 2026** — still open, no sites touched since
raised. Carried here rather than in `open_questions.md` because it's comment-only
maintenance, not a design question.

### M2 ✅ — Audit the remaining agents' flag messages for internal vocabulary *(done Sept 2, 2026)*

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

**Reconfirmed by documentation audit, Aug 31, 2026** — `main.py:10` still reads
`# the U4 ablation` in the CLI help text, unchanged since Aug 26. Still the only live
site the scan named as worth a pass.

**Closed Sept 2, 2026 at U9.M.** `--help` now says *"run without the comparable-rentals
corpus, so the deal is evaluated ungrounded"* and states what the before/after is evidence
of, which is the thing a demo audience actually needs from that line. The module docstring
keeps the `U4 ablation` gloss in a parenthetical — its audience has the repository open,
and §8 says that is precisely where a citation belongs.

**Four sites the original scan did not cover, found and fixed in the same pass**, because
they are the same defect in the other direction — a docstring asserting something
measurement has retired. `state.Scenario`, `tools/fmr_history.py`,
`scripts/forecast_evidence.py` and `tests/test_flag_propagation.py` all still stated the
rent/price correlation as `pooled r = -0.309` and used it to justify the pairing search,
after decision #21 re-derived it as a property of the *rent series* (+0.222 on market
rent, r² never above 0.10). `config.py` had been corrected at U9.3 and was the model for
the other four. Docstrings are the one place §8 asks for precise citation, which is
exactly why a stale one there is worse than a stale sentence in prose.

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

### M4 ✅ — §6's U8 row doesn't disclose that U8.9 was dropped *(done Sept 2, 2026)*

**Found by documentation audit, Aug 31, 2026.** `implementation_plan.md` §6's U8 row says
U8 "Absorbed U10" and lists per-metro live runs, LangSmith traces, demo screenshots and
the graph diagram as part of that absorption — but doesn't say that U8.9, the subsection
that would have built exactly that scope, was **dropped** Aug 30, 2026 and reassigned
whole to **U9.7** (`task_list_u9.md`). The reassignment itself is clean and correctly
cited there against OQ-13; the gap is that §6 — the file read every session — reads as if
the absorption fully landed. A reader who doesn't also open `task_list_u8.md` would not
learn that traces, screenshots and the diagram are still outstanding.

Fix: add one clause to the U8 row's Findings text naming the drop and pointing at U9.7.
Prose-only; no logic.

### M5 ✅ — §6's unit table has no row for U11 *(done Sept 2, 2026)*

**Found by documentation audit, Aug 31, 2026, prompted by the architect asking whether
U11 counts as closed.** It does — `tasks/README.md` marks it "✅ complete Aug 31, 2026",
every subsection (U11.1–U11.5, U11.M) carries a terminal status, and its two live
decisions (#18 gradient boosting, #19 the hybrid anchor) are both ✅ in §7's register with
full reasoning in `decision_log.md`. But §6's unit table — the plan-of-record's own list
of units — has no row for U11 at all: it goes U7, U8, U9 with nothing between. U11 exists
only in its own task file and in the §7 decisions it produced, not in the table that is
supposed to be the at-a-glance record of what shipped.

Fix: add a U11 row between U8 and U9, stated as what it produced (model form, the hybrid
anchor, the two decisions) the same way the other closed rows are. Prose-only; no logic.

### M6 ✅ — The comp relaxation ladder's stated rationale is contradicted by the rent model *(docstring corrected Sept 2, 2026; the reorder is now `TODO(retrieval)`)*

**Found Aug 31, 2026, during U9's reasoning-layer review.** The architect asked whether the
ladder's ordering was still sound given #19 moved the anchor to a rent index without a
bedroom dimension. It is not — but the cause is older than #19 and is worth recording
precisely, because the ordering may still be right for a different reason than the one
stated.

`agents/comps_retrieval.py`'s module docstring says relaxation is *"ordered by how much
accuracy each concession costs: the square-footage band goes first (**weakest signal**),
then the search radius widens, then bedroom-count tolerance loosens (**strongest signal**,
conceded last)."*

**Measured against the shipped gradient-boosting rent model** (`tools/model/rent_model.py`,
`RENT_MODEL_ESTIMATOR` since #18):

| Feature | Importance |
| --- | --- |
| **square_feet** | **0.502** |
| bedrooms | 0.300 |
| bathrooms | 0.198 |

**Square footage is the strongest feature at 1.7× bedrooms, and it is the first thing the
ladder concedes.**

**The cause is sequencing, not #19.** The ladder was written in **U4**; the rent model did
not exist until **U5**. "Weakest signal" was an assumption about what determines rent, made
before there was a model to ask — and it was never revisited when one arrived. #19 is
innocent here: bedrooms remain live in the system through FMR's bedroom step and through
`RENT_MODEL_FEATURES`.

**A second argument points the same way and is *unverified*.** A bedroom mismatch has a
correction available — #19's FMR bedroom step can adjust a comp's rent across bedroom
counts — while a square-footage mismatch has none. If that holds, the ladder concedes the
**uncorrectable** attribute first and the correctable one last, which is backwards. **This
has not been checked** against how the comp cross-check actually normalizes, and it should
be before any reordering is taken.

**Two caveats against over-reading the table.** Feature importance in the rent *model* is
not the same quantity as comp *comparability* — comps feed a cross-check, not the model —
and importances are unreliable under correlated features, which floor area and bedroom count
certainly are. The direction is clear enough to retire the stated rationale; it is not clear
enough on its own to justify a new order.

**Not scheduled inside U9, deliberately.** Changing the ladder changes which comps every
deal retrieves, which moves comp counts, the drift flag, confidence and verdicts across all
28 eval rows — a re-derivation of the published table five days before the freeze, against a
finding that is real but whose fix is not yet established. **What is worth doing now is the
docstring**: state that the order is inherited from U4 and that the measured importances do
not support the "weakest signal" claim, so the next reader is not misled by a rationale the
evidence contradicts.

**Closes when** either the docstring is corrected alone, or a later pass measures comp
comparability directly — U4's ablation harness is the instrument — and reorders on that.
Reproduce the importances by loading `config.RENT_MODEL_PATH` and reading
`bundle["model"].feature_importances_` against `config.RENT_MODEL_FEATURES`.

**Tagged at the site Sept 2, 2026 at U9.11, and the gap is worth naming because this entry
created it.** M6 closed on its first condition — the docstring — which left the *reorder*
deferred in prose across three documents and tagged nowhere, so `grep -rn "TODO(" src/`
could not see it and §8's inventory was correct while being incomplete. It is now
`TODO(retrieval)` at the branch that applies the order, stating what is missing, why it is
deferred (a reorder re-derives all 30 eval rows) and what closing it takes. **The lesson
generalizes: when a maintenance item closes in half, tag the half that stays open before
marking the entry done** — recorded in `engineering_standards.md` beside the two drift
rules, neither of which could have caught this one.

**One thing the tag adds that this entry did not say.** The order lives in
`agents/comps_retrieval.py` as control flow, not in `config.py`. That is defensible while
it is inherited and unmeasured; the moment it is *chosen* on evidence it becomes a tuned
parameter and belongs in `config.py` under §8's single-home rule.

**Relevant to OQ-22, and now tracked as OQ-24 in its own right.** Retrieval relaxation is
the strongest candidate for a further reasoning locus in this system, and this finding is
why: *which* criterion to relax for a given deal is a real judgment with alternatives and a
measurable outcome, and the fixed ladder answering it today rests on a premise that
measurement contradicts. The measurement above is what OQ-24 must take **first** — if the
best fixed order captures the gain, there is no locus to buy.

### M7 ✅ — `architecture.md`'s repository tree has drifted from the build *(re-derived Sept 2, 2026)*

**Found Sept 1, 2026 while adding `tools/faults.py` and `app.py` to it (U9.7e).** Those
two entries are now correct; several others are not, and they were not touched because
fixing them properly is an audit rather than an edit:

- `agents/critic.py` is marked ◐ *"consistency checks U7"* — U7 shipped them and U7.7
  retired #12's Critic half on evidence.
- `agents/summarizer.py` says *"polish in U9"*; U9.4 rewrote its top half entirely.
- `eval/` is marked ◐ *"harness itself is U8"* and lists `expected.yaml` and
  `run_eval.py`, **neither of which exists** — the harness landed as `cases.py` and
  `runner.py`.
- `tests/` lists one suite at *"24 hermetic cases"*; there are five files and 97 tests.
- `tools/` omits every module added since U6 — `zori.py`, `sale_benchmarks.py`,
  `fmr_history.py`, `growth_bands.py`, `rent_growth.py`, `tot.py`, `zcta_crosswalk.py`.

**Why it matters more than an ordinary stale doc:** this tree is one of the first things
a reviewer of a public repository reads, and a file listed in it that does not exist
(`run_eval.py`) is worse than an omission — it sends the reader looking for something
that was never built. **Closes when** the tree is re-derived against `find src -name
'*.py'` rather than edited entry by entry, which is the only way it stops drifting again.

---

### M8 ✅ — The scenario table never states the error band it compounds from *(done Sept 2, 2026)*

Every row of the five-year outlook compounds `ForecastDetail.projection_base_rent` as though
it were exact. On `staten-island` that number carries a metro holdout error of **±$855 — 32%
of the estimate — against a five-year band spread of 43%**, so the three rows differ from each
other by less than the error bar on the number all three start from, and the section does not
say so. `los-angeles` is milder and the same shape: ±18% against a 20% spread.

**One sentence, no new measurement.** `ValuationDetail.subject_metro_mae_dollars` (falling
back to `model_mae_dollars`) is on state where the projection is rendered, and the rent-basis
section above the table already prints both figures — *"±$452 overall, ±$509 in Los Angeles"*.
What is missing is the link between that error and the projection that compounds it.
`TODO(U9.M)` sits at the site, in `agents/summarizer._scenario_section`.

**Language, not calculation** — nothing about which scenarios are selected or what they
project changes. That distinction is why this is maintenance rather than a design question:
the fix states a fact the system already holds, and takes no position on the open one.

**Raised Sept 2, 2026 by the U9 spike on OQ-22's starting-point treatment**
([`design/forecast_starting_point_spike.md`](../design/forecast_starting_point_spike.md)).
That spike proposed *projecting* from the error band and the mechanism was not adopted —
the evaluator held its choice on only 5 of 8 repeat runs. **Stating the band is the part that
survives that finding**, and it stands whichever way OQ-22 is eventually decided, including
the wording-only route the architect is testing.

**Closed Sept 2, 2026, the same day it was raised**, ahead of U9.11 so the unit does not
close with a `TODO` pointing at a subsection marked done — which is the inconsistency the
close-out exists to catch. `agents/summarizer._projection_rent_error` renders one sentence
beside *"Projected from…"*: **±$855/mo, 32% of the estimate** on `staten-island`, ±$509
(18%) on `los-angeles`, ±$343 (16%) on `overpriced`. It prefers the subject's own metro
over the pooled figure, the same order and for the same reason as the Findings table, and
returns nothing rather than a hedge when no band is on state.

**What the sentence says, and what it deliberately does not.** It states that every row
compounds one modelled rent, that the rent carries that error, and that no row widens for
it — so the spread between rows is the range of *markets* this deal could meet, not the
range this system's own rent figure could take. It does **not** re-project anything: the
spike's mechanism stays unadopted, and taking the language half alone is what let this land
in a freeze week. All three sample reports re-derived; **all 30 eval rows byte-identical**,
no re-record.

## Closed Sept 2, 2026 at U9.M — what each fix actually was

**M4** — `implementation_plan.md` §6's U8 row now names U8.9's drop and points at U9.9, so
a reader of the file that is loaded every session learns that the absorbed capture scope
was still outstanding when U8 closed.

**M5** — §6's unit table gains a U11 row between U8 and U9, stated as what it produced
(#18's model form, #19's hybrid anchor, the per-metro result) the way every other closed
row is. U11 had existed only in its own task file and in the decisions it produced.

**M6** — the docstring half only, which is what the entry recommended. The ladder still
concedes floor area first; what changed is that `agents/comps_retrieval.py` now says the
order is inherited from U4, that the shipped rent model measures `square_feet` at 0.502
against `bedrooms` at 0.300, and that the *cause is sequencing* — the ladder predates the
model by a unit. **Both cautions against over-reading that are carried too**, since
feature importance in the rent model is not comp comparability and importances are
unreliable under correlated features. Reordering still moves comp sets across all 30 eval
rows and stays out of scope.

**M7** — the tree was **re-derived against `find src -name '*.py'`**, not edited, which is
what the entry said was the only fix that stops it drifting again. The `✅`/`◐` status
markers went with it: they encoded a moment in the build and were never updated as it
passed, and `changelog.md` answers "when did this land" properly. `scripts/` is a count
rather than an enumeration, because it turns over faster than this document is read.
