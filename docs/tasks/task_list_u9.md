# U9 — Summarizer polish + Streamlit demo surface — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#20) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

**The last build unit. Feeds the final report and the video (Checkpoint 7.1).** §6 sizes
U9 as *"Summarizer polish + Streamlit demo app"*, and that sizing is now three units
short of what U9 actually owes: five open questions were retargeted here, decision #8 has
a half waiting on it, and **U8.9's absorbed U10 scope was dropped on Aug 30 with no
successor** — live end-to-end runs, LangSmith traces, the graph diagram, and demo
screenshots have had no owner since. The architect took all of it into U9 on Aug 31.

**The schedule is the binding constraint and it is stated here rather than discovered on
Sept 3.** Today is Aug 31; the code freeze is **Fri Sept 4**. That is four build days for
nine change sets, against §6's ~2–3 hrs of review per unit. The plan manages that
structurally — see *Sequence* and *What sheds* — not by optimism.

---

## What U9 owes, and where each obligation came from

| Obligation | Source | Lands in |
| --- | --- | --- |
| Streamlit demo surface | §6 U9 row; decision **#3**; §6 cut-list item **4** | U9.4 |
| Summarizer polish | §6 U9 row; `agents/summarizer.py` docstring | U9.2b |
| Summarizer model role | decision **#8** (🟨 part open), **OQ-9** | U9.2 |
| A sixth demo deal, in Chicago | **OQ-21** | U9.1 |
| ToT constants written up as a disclosed gap | **OQ-5** (retargeted U8 → U9) | U9.6 |
| Checkpoint criteria as build artifacts | **OQ-14** (5.1 half) | Q3 |
| LangSmith account and trace capture | **OQ-13** | U9.7 |
| Live runs, traces, diagram, screenshots | **U8.9**, dropped Aug 30 | U9.7 |
| On-disk credential fallback, before a public demo | **OQ-10** | U9.6 / Q4 |
| Root `README.md` | **Checkpoint 7.1**, graded | U9.5 |
| `TODO` inventory reconciliation | **U8.M**, still 🟨 | U9.M |

**The root README is 0 bytes today.** 7.1 grades the submission on *"a link to a public
GitHub repository that is accessible and includes a README, core project files, and clear
instructions for review or use."* Nothing in the plan owned it before this unit. It is
listed above with the rest, but it is the only line whose absence is scored directly.

---

## Sequence, and why

**Three ordering rules, in priority order.**

1. **Anything that can move a published number lands before anything that captures one.**
   U9.1 adds a row to the demo set and U9.2 adds a model call inside the pipeline; both
   precede U9.7's capture, or the screenshots and the results table describe different
   builds. This is the same rule U8.10 used to put its prose passes ahead of its `src/`
   passes, applied in the opposite direction because U9's risk is in the code.
2. **The forced re-record follows its cause immediately.** U9.2 puts an LLM call in a node
   every eval row reaches, so both offline tiers `CacheMiss` until U9.3 re-records them.
   The tree is red between those two commits — permitted by §8 when the completing
   subsection is named, which it is.
3. **Capture runs last and runs late.** LangSmith's free tier expires traces after 14 days
   (OQ-13), so trace capture belongs beside the write-up, not ahead of it. Screenshots
   have to show the surface that ships, which is not known until U9.4 is done.

**Why the demo deal (U9.1) goes first rather than last.** It is the only subsection that
changes an input, and every artifact downstream quotes the demo table. It is also the
cheapest — U8.6b already found and measured the siting, so nothing has to be searched for.

---

## Unit-level open questions

**Q1–Q2 block U9.1 and U9.2 and are needed before coding starts. Q3–Q5 block only their
own subsections and can be answered in flight.**

### Q1 — When the narrative call fails, does that raise a flag or a sentence?

The lede is a live model call inside a node, so it can fail — quota, a dead ID, a schema
refusal. Transparent Degradation says the report must say so. The question is *how*.

- **(a) Render an in-report sentence**, no new `FlagKind`: *"A written summary could not be
  generated for this run; the disclosures and figures below are unaffected."*
- **(b) Add `FlagKind.SUMMARY_NARRATIVE_UNAVAILABLE`** at info severity and let it render
  through `_flag_section` like every other disclosure.

**Recommendation: (a), on two reasons, the second of which is principled rather than
cheap.** First, cost: U8's headline census is **30 of 30 flag kinds raised, none uncovered
and none unreachable**, and a 31st kind breaks that claim unless a case covers it — which
needs a *new declared fault*, because `Fault.LLM_UNAVAILABLE` kills the run at extraction
and never reaches the Summarizer (`cleveland-model-outage` escalates with 0 comps). That is
a fault, a case, and a recording, for one sentence. Second, and this is the part worth
keeping: **every other flag in this system propagates.** A flag exists so downstream
agents and the Critic can act on it. The Summarizer is terminal — a flag raised there has
no consumer except the report it is already printed in, so it would be flag-shaped
notation rather than a flag. Naming that boundary is better than blurring it.

### Q2 — `DemoDeal.rent_basis` is stale across the whole set. Re-base six, or one?

U8.7 found every demo deal carries `rent_basis="hud_fmr:2"` — rents set from the anchor
**#19 retired**. OQ-21 requires the *new* deal to declare against the current anchor "or it
ships stale on day one." It does not say what happens to the other five.

- **(a) The new deal declares against #19's hybrid anchor; the five existing deals stay as
  they are, with the staleness stated** in `demo_deals.py` and in the report's limitations.
- **(b) Re-base all six** under #19, re-derive every figure, update
  `verify_demo_calibration.py`'s expectations, re-run the live tier.

**Recommendation: (a), and it is a schedule judgment I want on the record as one.** (b) is
the better end state and I am not pretending otherwise: a set with two rent bases is a wart,
and the report has to explain it. But (b) changes the stated rents in six listings three
days before the freeze, which moves every live-tier baseline row, every demo report, and the
asking-price and stated-rent disclosures that #20 was just closed against. The cost is not
the re-derivation; it is that the published table would be re-derived after the unit that
scored it closed. (a) costs a paragraph. **If Q2 goes to (b), it must land as U9.1 and
nothing else in the unit may start until its batch re-run is green.**

### Q3 — OQ-14's 5.1 half: already discharged, or does U9 owe artifacts?

OQ-14 asks that checkpoints publishing completion criteria have the unit *produce* each
one rather than write it up afterward, and names 5.1 as the remaining half (6.1's was
discharged at U7.8). But 5.1 is an **architecture-design** checkpoint — roles, coordination
strategy, communication approach — and `docs/private/checkpoints/checkpoint_5.1_response.md`
exists, so it has been submitted.

- **(a) Close OQ-14 as discharged**, recording that 5.1 asked for design rationale rather
  than build artifacts, so the treatment U4 got does not apply to it — and that 6.1's half
  closed at U7.8.
- **(b) U9 produces the 5.1 artifacts anyway** — the regenerated topology diagram and a
  trace showing the back edge firing, both of which U9.7 captures regardless.

**Recommendation: (a), noting that (b) happens as a side effect.** U9.7 regenerates the
diagram and captures traces for the report; if the architect wants those attributed to 5.1
it costs a sentence in the close-out rather than a subsection.

### Q4 — OQ-10: drop the on-disk credential fallback before the public demo?

OQ-10 says "raise before any public demo," and U9 *is* the public demo. Three sites:
`tools/hud_fmr.py:24`, `tools/llm_client.py:41`, `tools/diagnostics.py:36`.

- **(a) Keep the fallback, document it, and fix the one real exposure.**
- **(b) Drop the fallback, require env vars**, and update the README's setup instructions.

**Recommendation: (a), because the two halves of this question have different answers and
the entry conflates them.** The fallback itself leaks nothing: `ignore/` is gitignored, so
a public repository never carries a key, and requiring env vars would make a fresh clone
harder to run — which is the thing 7.1 grades the README on. The *real* exposure is
`diagnostics.py:36`, which deliberately prints the account identifier and is fine in a
terminal and wrong in a recording, and **Week 7's deliverable is a recording.** That is
fixed by redaction at U9.M regardless of which way (a)/(b) goes, and it should be fixed
whether or not the fallback stays.

### Q5 — What sheds if U9.4 is not working on the morning of Sept 3?

The Streamlit surface is §6 cut-list **item 4**, and it is the only item on that list with
a *pre-agreed* fallback: a terminal recording plus LangSmith traces. §6 kept it in scope on
Aug 26 precisely because the fallback is available late — "which is precisely what makes it
safe to keep rather than shed early."

**Recommendation: shed in this order, and state the decision date.** U9.2b (polish) first —
it is cosmetic and the report never quotes it. Then U9.4 to its documented fallback, taken
**no later than the morning of Wed Sept 3**, so U9.7's capture has a full day against
whichever surface exists. **U9.5 (README) and U9.7 (capture) never shed**: one is graded
directly and the other is the report's evidence. The lede (U9.2) does not shed after U9.3
lands, because un-landing it would force a second re-record.

---

## Subsections

### U9.1 ⬜ — The sixth demo deal (OQ-21)

**Nothing here needs searching for.** U8.6b already measured the siting: **Chicago Uptown
at 1,100 sq ft** returns 8 comparables with 2 outside the size band — the share the
threshold admits — raises **no warn-severity disclosure at all**, and runs at confidence
**1.00**. It exists in the eval set today as the golden fixture
`chicago-uptown-band-under`, whose 1,300 sq ft sibling escalates, so the pair also
documents how narrow the clean margin is.

**Why the set needs it.** After U8.6e's ungate, `chicago` escalates on
`comps_outside_match_criteria` (3 of 8 comps outside the band) and `los-angeles` is the
only demo deal reaching 1.00 and reporting clean. One clean run against five escalations
understates a system whose whole argument is that it reports cleanly when it can.
**`chicago` is not touched** — that escalation is the system working, and re-siting it
would spend the escalating deal to buy the clean one.

- New `DemoDeal` in `demo_deals.py`, calibrated under **#11**: every figure names the
  public source it derives from, `_check_listing_states` holds the prose and the fields
  together, and `scripts/verify_demo_calibration.py` re-derives it from live sources.
- `rent_basis` declared per **Q2**.
- `main.py`'s `--deal` choices and the docstring's usage block pick it up automatically
  from `DEMO_DEALS`; the docstring's hand-written line list does not, and needs the row.
- A `live`-tier baseline row in `eval/cases.py`, with `VerdictSource` set the way every
  other demo row is — a **measured** baseline, never a predicted verdict. It must not be
  scored in the 21-case agreement figure.
- Re-derive the demo table.

**Review attention:** the calibration, and specifically that the new deal's figures are
derived rather than chosen to produce a clean run. A demo deal calibrated *toward* an
outcome is the error #6 rejected the demo set as a tuning instrument for.

### U9.2 ⬜ — The Summarizer's narrative lede (decision #8, OQ-9)

**Decided Aug 31, 2026 by the architect: the Summarizer gets a model call.** A short
executive summary above the report, with the full deterministic report intact beneath it.

**The model is `config.MODEL_SUMMARIZER`, unchanged — and that is a zero-change decision,
not an omission.** All five `MODEL_*` roles already hold
`nvidia/nemotron-3-nano-30b-a3b`, and `MODEL_SUMMARIZER` is already in
`verify_models_live()`'s default set (`tools/llm_client.py:164`), so it is already guarded
at launch. A second ID would add a second thing that can be dead on demo day, which is
decision #8's own durable lesson.

**How #8 and OQ-9 close, and the wording matters.** OQ-9's stated condition is met — the
Summarizer calls a model, so the role is exercised rather than untested. But the ID was
selected in U3's bake-off on **schema-valid extraction**, not on prose quality, and it is
inherited here rather than measured for this job. #8 closes as ✅ with the role exercised
and **the inheritance stated as an inheritance**. Claiming it was chosen on evidence for
summarization would be a claim the record does not support.

**Four constraints, each of which is a property something else in the system depends on:**

1. **Additive only.** The lede is prepended; nothing in the existing report is removed,
   reworded by the model, or summarized away. §1 requires every flag rendered, never
   counted, and a stochastic component in front of the disclosure text would put that
   guarantee at the mercy of a sampler. The model writes *about* the run; the report still
   states it.
2. **The prompt quotes rounded, reader-facing figures.** This is what a lede needs anyway,
   and it also sidesteps **OQ-18's mechanism** by construction: the existing replay
   fragility comes from `scenario_forecast._context_block` embedding a freshly-computed
   float, and the new call must not add a second instance of it.
3. **Reader-facing text carries no internal vocabulary** (§8). The lede is the most
   reader-facing string in the repository. The prompt states that constraint explicitly and
   passes plain-language inputs, not enum values or config names.
4. **Failure renders per Q1** and never blocks the report.

Also: `config.SUMMARY_NARRATIVE_ENABLED`, because `config.py` is the only home for a
tunable, and because the eval runner and the hermetic suites need one switch to reach.

**The test suites must not start making live calls.** `tests/` calls `summarizer_agent()`
directly in ~76 places and has an `offline_scenario_evaluator` fixture that replaces
`LlmClient` with a refusing stub. The same treatment is needed here, in `conftest.py`, and
**one test should exercise the failure path** so Q1's rendering is covered rather than
assumed.

### U9.2b ⬜ — Summarizer polish *(sheddable, per Q5)*

Wording and layout of the deterministic report — the "polished in U9" the module docstring
has promised since U2. The **structure and the disclosure rules are settled and are not in
scope**; this is prose. Kept as its own commit so that shedding it costs nothing and so a
reviewer is not reading cosmetic diffs alongside a new model call.

### U9.3 ⬜ — Re-record the offline tiers, and prove the lede verdict-inert

**Forced by U9.2**, and the reason is exact: the Summarizer is a node every eval row
reaches, so under `LLM_CACHE_MODE=replay` a lede prompt with no recording raises
`CacheMiss` and both offline tiers die. `.venv/bin/python -m eval.runner --tier golden
--record`, same for `replay`, then re-run without the flag.

**The claim to verify — not assume — is that the batch is unchanged.** The Summarizer runs
last and computes nothing (its docstring: *"Nothing here re-derives an upstream figure"*),
so confidence, flags, verdicts and coverage are all fixed before it is invoked. That makes
the lede **verdict-inert by construction**, which is exactly the kind of claim U8.8 and
U8.10f checked rather than asserted: re-run both tiers and compare the results table
**byte-for-byte** on confidence, disclosures, outcome, target-fired and verdict. Any
difference is a defect in U9.2, not a new baseline.

**Review attention:** the diff of `eval/data/llm_recordings/` should be **additions only**.
A modified existing recording means U9.2 changed a prompt it had no business touching.

### U9.4 ⬜ — The Streamlit demo surface (decision #3, §6 cut-list item 4)

`src/app.py`, run as `.venv/bin/streamlit run app.py` from `src/`.

**Execution model, decided Aug 31: replay by default, and a paste box that forces live.**
The six (or seven, after U9.1) calibrated demo deals run from the committed recordings —
instant, reproducible on any fresh clone, no quota. A pasted listing has no recording, so
it cannot replay; the app switches that run to live **and says so on the surface**.

**That default is a direct answer to OQ-17, not a convenience.** OQ-17 names "any future
live surface, including a Streamlit demo that calls the model live" as exposed to run-to-run
variance — measured at roughly 1 in 15–20 live attempts flipping a near-tie into an extra
warn, which happened unprompted to the `los-angeles` demo deal itself. A demo that replays
cannot drift mid-presentation. Making the replay/live distinction **visible** rather than
hidden also puts the recording design itself into the demo, which is one of the more
defensible things this repository has built.

What it renders:

- The listing text, then the run, then `report_markdown` — the same string `main.py`
  prints, so the surface and the terminal cannot disagree about what the system said.
- Confidence, the disclosure counts by severity, and the comp table.
- **The `human_review` interrupt as a genuine pause.** `main.py` auto-resumes with a canned
  note so one command produces a complete report; the app should let a person type the
  note and resume, which is the honest version of what the interrupt is for and the
  clearest demonstration of human oversight that 7.1 asks about.
- `verify_models_live()` on the live path only — a replay run must not fail because a model
  ID died.

**Two mechanical risks worth naming in advance**, since both are how Streamlit demos
usually break: the script re-runs top to bottom on **every** widget interaction, so the
graph invoke must be guarded and its result held in `st.session_state` or a cached
resource, and the checkpointer needs a stable per-session `thread_id` — reusing one across
deals resumes a paused thread instead of starting a new deal, which `main.py`'s
`--thread-id` help already warns about.

### U9.5 ⬜ — Root `README.md` (Checkpoint 7.1)

Currently 0 bytes, and graded directly. Written for a reviewer who has never seen the
repository:

- What the system is and who it is for — §1's seven-agent pipeline and Transparent
  Degradation, in plain words.
- **Install and run**, verbatim-runnable: the venv at `src/.venv`, commands run from
  `src/`, `main.py --deal <key>`, the Streamlit app, `pytest`, and the eval harness.
- Where the evidence lives: `eval/results/results.md`, `eval/results/sensitivity.md`, the
  diagram, and the document map in `implementation_plan.md`.
- **Stated limitations**, because the system's own design principle is disclosure and a
  README that hides them contradicts the thing it is describing.

**Two hard constraints.** It must not reference `docs/private/`, `ignore/`, `data/`, or
`CLAUDE.md` — all gitignored, and §8 forbids describing private paths in public files. And
it must not carry internal vocabulary a reviewer cannot resolve.

### U9.6 ⬜ — The disclosed gaps: OQ-5's ToT constants, and OQ-10's answer

Docs and comments only; no logic.

**OQ-5** was retargeted here over the recommendation, on the architect's argument that the
constants get a sentence written by the unit that builds the surface a reader meets them
through. What is written: `TOT_BRANCHING_FACTOR`, `TOT_MAX_DEPTH`, `TOT_BEAM_WIDTH` and
`TOT_PRUNE_THRESHOLD` were set by reading output rather than by tuning; the two
measurements that exist are that `TOT_TIE_EPSILON` is **not meaningfully straddleable**
because the gap it compares is noise-dominated (U8.6b/OQ-17), and U8.6c's published depth-2
**cut margins**, which found the discarded pairing often outscoring the reported one and
losing on `tot._rank`'s conservatism preference. Tuning against the golden batch was
**considered and declined** — those fixtures were authored by the unit that would have
tuned against them. The closing condition is unchanged and unmet: a known-correct branch.

**OQ-10** closes per **Q4**, whichever way it goes, with the reasoning recorded rather than
the verdict alone.

### U9.7 ⬜ — Absorbed U8.9: live runs, traces, diagram, screenshots

**Dropped from U8 on Aug 30 with no successor; taken into U9 on Aug 31.** Runs last, per
ordering rule 3.

- **Live end-to-end runs** across the metros as `live` rows in the same table — the thing
  `eval/README.md` says belongs beside the offline tiers so *"works against a real model"*
  is demonstrated rather than assumed. Expect run-to-run variation and report what was
  observed; per OQ-17 a live row is a sample, not a fixed value, and saying so is the
  honest framing.
- **LangSmith** (OQ-13): no key was present in `ignore/` as of Aug 24, so the account is
  set up here. Free-tier traces expire after **14 days**, which is why this is last.
- **Graph diagram** regenerated from the compiled graph via
  `scripts/export_graph_diagram.py`, which asserts the topology including the single
  Critic→Planner back edge.
- **Screenshots** off the Streamlit surface — or terminal captures, if Q5's fallback was
  taken.
- **Redact `tools/diagnostics.py:36` before any capture.** The full error text
  deliberately includes the account identifier; correct for a terminal, wrong for a
  recording, and the deliverable is a recording.

### U9.M ⬜ — Maintenance *(separate commit, per §8)*

- **U8.M's remainder**, still 🟨: reconcile the `TODO` inventory in
  `design/engineering_standards.md` against `grep -rn "TODO(" src/`. The inventory's whole
  value is that the two agree.
- The six `TODO(U8)` sites (`critic.py` ×4, `config.py` ×2) — U8 is closed, so each is
  resolved, re-scoped, or deleted. `config.py:685`'s says outright *"set a number, or
  delete this and the emphasis it gates"*, and **#20 answered it**: the threshold stays
  `None` deliberately, foreclosed by evidence rather than by arithmetic. That is a rewrite,
  not a deletion.
- **M2**: `main.py`'s CLI help says *"the U4 ablation"*, which a demo audience can see —
  the one site M2's scan found that is genuinely reader-facing.
- The `TODO(security)` redaction, per Q4.

### U9.8 ⬜ — Close-out

Per §8: review the changelog rows this unit's commits already wrote — do not reconstruct
them — then settle the register and empty the open questions.

- **§6**: the U9 row ⬜ → ✅, restated as what it produced. **Cut-list item 4 leaves the
  list** — by being spent if the app shipped, by being *taken* if Q5's fallback was
  invoked, and the difference must be stated. §6's own lesson from three consecutive
  mis-priced items applies: re-measure the item's cost before recording the outcome.
- **§7**: **#3** (Streamlit) confirmed as landed rather than merely scheduled; **#8** 🟨 → ✅
  with both halves resolved and the Summarizer's model recorded as *inherited*, per U9.2.
- **`open_questions.md`**: OQ-5, OQ-9, OQ-13, OQ-21 close; OQ-14 closes per Q3; OQ-10
  closes per Q4. **OQ-17 and OQ-18 stay open** — U9 does not resolve either, and the
  Streamlit surface's replay default is a mitigation of OQ-17's exposure, not an answer to
  it. Update the `Last reviewed:` line.
- **`decision_log.md`**: #8's Summarizer half under *Models & infrastructure*; #3's outcome
  under *Evaluation & demo*, which currently records only that the decision was taken early
  and never revisited.
- **`tasks/README.md`**: the U9 row, and U8's row 🚧 → ✅.

---

## Status at a glance

| | Subsection | Status |
| --- | --- | --- |
| ⬜ | **U9.1** sixth demo deal (OQ-21) | Blocked on Q2 |
| ⬜ | **U9.2** Summarizer narrative lede (#8, OQ-9) | Blocked on Q1 |
| ⬜ | **U9.2b** Summarizer polish | Sheddable (Q5) |
| ⬜ | **U9.3** re-record offline tiers | Forced by U9.2 |
| ⬜ | **U9.4** Streamlit surface (#3) | Fallback pre-agreed (Q5) |
| ⬜ | **U9.5** root README (7.1) | Never sheds |
| ⬜ | **U9.6** OQ-5 and OQ-10 written up | Q4 |
| ⬜ | **U9.7** live runs, traces, diagram, screenshots | Never sheds; runs last |
| ⬜ | **U9.M** maintenance | — |
| ⬜ | **U9.8** close-out | — |

**Nine change sets, four days, against a review budget sized for two or three.** The unit
is over-subscribed and the shed order in **Q5** is the mechanism for that, decided in
advance rather than improvised on Sept 3 — which is the discipline §6's cut list exists to
enforce, applied inside a unit for the first time.
