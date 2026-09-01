# U9 — Report, recommendation, and the demo surface — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#20) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

**The last build unit. Feeds the final report and the video (Checkpoint 7.1).**

**Rewritten Aug 31, 2026, after the architect ran the pipeline and read two reports.**
The first draft of this file planned "Summarizer polish + a Streamlit app" against §6's
sizing. Reading actual output changed the unit: the report has no recommendation, the
reports-versus-escalates distinction was never defined against any user, the forecast
pairs two series built by different methods, and the demo deals cannot be reproduced from
a fresh clone. **None of that was visible from the code; all of it was visible from one
run.** The lesson belongs at the top of this file rather than in its close-out: this
project's own principle is to test premises against data, and the report's readability was
a premise nobody had tested for seven units.

---

## The schedule, stated first because it decides the rest

**Today is Aug 31. Code freezes Fri Sept 4, extending to Sat Sept 5 if tweaks are still
landing** — the architect's clarification Aug 31: the Sept 4 date assumed two full days for
recording and the write-up, and there is wiggle room inside that. **Five build days, not
four.** Against §6's ~2–3 hrs of review per unit that is realistically **six to seven
change sets, not twelve.**

**Sept 5 is elastic, not free.** It is the reserve for finishing something already in
flight, not room to start another subsection — spending it on new work re-creates the
failure mode §6's freeze exists to prevent, which is arriving at the deadline still
integrating.

The subsections below are in build order, revised by the architect Aug 31: the README
first, the live tier pinned before new deals are added to it. The **cut line** before U9.8
marks where I expect the freeze to land.

**Nothing below the shed line is speculative work** — each item is either a disclosed gap
the report names or a deliberate deferral with its reasoning recorded. That is the same
treatment §6's cut list gives, applied inside a unit.

---

## Personas, and the two axes — the design this unit rests on

**Settled Aug 31, 2026 by the architect.** No persona, user journey, or intended-user
definition existed anywhere in this repository before today; it was skipped, not
documented elsewhere. Checkpoint 7.1 asks for "the intended user" directly, so this is a
report section as much as a design input.

| | Persona | Relationship to the system | Reads |
| --- | --- | --- | --- |
| **a** | **IT / operations** | Confirms the system is working as intended | Eval batches, logs, traces — never an individual deal |
| **b** | **Real-estate agent** — *the core internal user* | Reviews deals before they reach an investor | The full report, including its evidence |
| **c** | **Investor** — *the external customer* | Holds capital, makes the buy decision | The recommendation and the figures behind it |
| **d** | **Another agent** — *future, unsupported today* | Calls this system for an evaluation on a human's behalf | The state object, via a protocol |

**(d) is not speculative and the report should say why.** The MCP reference server
(decision #13) already exposes this project's tools to an external host. The unbuilt half
is the inverse — exposing *the evaluation itself* as a callable capability — and naming
that as the concrete next step is stronger than a generic "future work" line.

### Escalation routes by flag type — not to one desk

**Chosen over routing everything to the agent, because it is what the flags already
mean.** A geocoder outage and a sparse comp set are both "escalate" today, and they call
for different people:

- **Infrastructure flags → (a) IT.** The geocoder was unreachable, the model was
  unavailable, no rent index covers this county. Nothing about the deal is in question;
  the system could not do its job.
- **Deal-substance flags → (b) the agent.** Sparse comps, a price far off its benchmark,
  a rent claim the model disputes. The system worked correctly and found something a
  person should judge.

This needs a routing rule and it changes the human-review payload, which is why it is
U9.2 rather than a note in the Summarizer.

### The two axes — the fix for "reports vs. escalates"

**The report currently states one axis and readers assume it is the other.**

- **Axis 1 — can the system stand behind its own numbers?** `reports` / `escalates`.
  Computed today. This is a statement about the *software*.
- **Axis 2 — is this a good deal?** **The system has never stated this.** Neither report
  says whether the property is worth buying.

A reader sees "🚩 Escalated to human review" and concludes the deal is bad. On
`staten-island` that is precisely backwards: it escalates because there are no
comparables, while asking **17% below its ZIP median**. **The two axes are rendered as two
separate lines that never merge**, and that single change is the largest readability gain
available in this unit.

---

## Subsections

### U9.1 ✅ — Root `README.md` and the committed model *(never sheds)*

0 bytes today, and 7.1 requires *"a README that explains the project, architecture, setup,
and usage"* plus *"clear instructions for running or reviewing the project."*

**Written for reviewing rather than running, per the architect's Aug 31 call** — the
instructions ask a technical audience to *understand and review*, and the graded artifact
is the repository's legibility, not a working install on someone else's machine. So: what
the system is, the architecture, how to run it, where the evidence lives
(`eval/results/`, the diagram, saved reports), and **stated limitations**, because a README
that hides them contradicts the principle the system implements.

**Commit the 196 KB rent model**, and commit the two demo reports as sample outputs. The
Chroma index (51 MB) and the source CSVs stay out — Kaggle-licensed, and large — with the
rebuild path documented. Worth stating plainly in the README that a clone cannot run the
pipeline without that step, rather than letting a reviewer discover it.

**Must not reference** `docs/private/`, `ignore/`, `data/` or `CLAUDE.md` — all gitignored,
and §8 forbids describing private paths in public files.

### U9.2 ✅ — Personas, journeys, and the escalation routing rule

**Doc-first, then the one code change that follows from it.**
`docs/design/personas.md`: the four personas above, each with its journey, and the
routing rule. Referenced from the document map in §6 and from the report.

The code half is small and is the reason this is not purely a doc commit: the
`human_review` interrupt payload currently says only *"Confidence below threshold or
rework budget exhausted."* It should name **which desk** the deal is waiting on, derived
from the flag kinds that caused the escalation. `agents/critic.py`,
`agents/human_review.py`.

**Also fixes the note bug the architect found.** `main.py`'s canned resume text says *"A
real reviewer would resolve the disclosures above before proceeding"* — true in the
terminal, where the interrupt payload prints the flags above it, and **false once the same
string is replayed into the report banner**, where disclosures render below. The layout is
right; the string is wrong. It also stops being a placeholder once a real reviewer persona
exists.

### U9.3 ⬜ — The forecast: re-source rent growth, and repair the search

**The largest change in this unit, and it supersedes half of decision #16.** Full
investigation, all four defects and the re-measurement, in
[`../design/evaluator.md`](../design/evaluator.md). This section is what gets built.

**Raised by the architect Aug 31, 2026**, reading the LA report: rent compounds +7.26%/yr
while the price falls −0.80%/yr, in two of three rows including the one labelled
*Optimistic*.

#### The premise that failed

`scripts/growth_correlation.py` — written for this, because **#16's number was measured
once before U6 and never committed as a script.**

| Pass | Rent series | Pooled | Chicago | LA | Cleveland | New York |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | HUD FMR | **−0.317** (r² 0.100) | −0.200 | −0.337 | −0.654 | **+0.120** |
| 2 | FMR, FY2023–24 removed | **−0.197** (r² 0.039) | **+0.229** | −0.228 | −0.360 | **+0.390** |
| 3 | **Zillow ZORI** | **+0.222** (r² 0.049) | −0.537 | **+0.233** | **+0.715** | −0.089 |

The evaluator is told rent and price *"move opposite each other here."* **They do not.**
That is true of the HUD schedule against Redfin prices and **false of market rent against
the same prices** — and this system's published estimate has been anchored to market rent
since #19. Pass 2 shows ~40% of the negative signal is two fiscal years HUD moved the
schedule nationally, which this project's own cohort screen exists to identify as
non-market.

#### What is built

**1. Rent growth re-sourced from HUD FMR to Zillow ZORI.** #16 chose FMR on an
architectural argument — *"the rent estimate is `ratio × FMR`, so projecting the anchor
forward forecasts rent by the same mechanism that produced the estimate."* **That argument
now selects ZORI**: since #19 the estimate is `ratio × ZORI(ZIP) × FMR-bedroom-step`, so
projecting the anchor forward means projecting ZORI. This follows #16's reasoning to where
the system moved rather than overturning it.

Measured, both series windowed 2018+ under one estimator with 2020–22 excluded on both:

| | | pess | base | opti | width |
| --- | --- | --- | --- | --- | --- |
| **Los Angeles** | ZORI rent | +1.25 | **+2.65** | +4.83 | **3.6pp** |
| | price | −0.80 | **+2.10** | +4.50 | 5.3pp |
| **Chicago** | ZORI rent | +1.58 | +4.13 | +6.66 | 5.1pp |
| | price | −1.56 | +6.76 | +10.51 | 12.1pp |
| **Cleveland** | ZORI rent | −0.11 | +5.43 | +11.27 | 11.4pp |
| | price | −4.66 | +7.26 | +15.72 | 20.4pp |
| **New York** | ZORI rent | +3.12 | +7.12 | +12.31 | 9.2pp |
| | price | +1.65 | +3.73 | +5.90 | 4.3pp |

Against LA's FMR bands today — **−0.68 / +7.26 / +14.49, width 15.2pp** — the band is four
times narrower and the base case a third of the size.

**Two windowing decisions, explicit rather than default, both found by measurement:**

- **Window ZORI to 2018+ to match Redfin's span.** Unwindowed, New York's pessimistic band
  is **−22.6%**, a real Bronx figure from a stretch ending **2017-05** — before the price
  series begins.
- **Apply the 2020–22 exclusion to the rent side too.** Only the price side has it today.

**FMR history stays as the documented fallback** where ZORI has no county — the same shape
as #19's hybrid, and it keeps `tools/fmr_history.py` earning its place.

**2. The estimator asymmetry closes as a side effect.** Both series become monthly, so
`redfin_data.compute_growth_bands` serves both: one estimator, one exclusion window, one
span. The 15.2-vs-5.3-point mismatch was an artifact of single-fiscal-year extremes against
12-month sustained stretches, and re-sourcing removes the cause rather than patching it.

**3. The cohort-shift machinery retires.** It exists solely to screen HUD's administrative
step-ups. A market series has none, so the screen, its `ForecastDetail` fields and its
report text go — and the depth-1 rent fork becomes *include or exclude 2020–22*, the same
question already asked of price. **Four framings, one question asked of two series**, which
is easier to explain than the asymmetric pair it replaces.

**4. The evaluator's instructions are corrected.** Two independent errors:

- **It is told something false.** Replace with the measured truth: the relationship is weak
  (r² 0.04–0.10 across every pass), its sign differs by market and flips with the rent
  series, so **no directional pairing rule is supported** — do not assume the diagonal, and
  do not assume its opposite.
- **It misread its task.** It scored base/base down for *"limited evidence of extremity."*
  State that the base case is the default the others depart from and needs no such evidence.

**This lands as its own commit.** It changes what every forecast is scored against, and a
prompt change with that reach should be attributable to one diff.

**5. A beam slot reserved for base/base**, so the neutral case is always reported. It
scored 0.70, cleared the 0.40 threshold, and lost on rank to three anti-correlated
pairings — so today the row labelled *Base* is base-rent with pessimistic-price and the
true base case appears nowhere.

**6. The report leads with two tables, and the search is untouched.** Rent and price get a
three-row table each, which is also how #16 forecasts them; the combined scenarios become a
secondary view with base/base present. **In separate tables the labels become true again** —
each names its own band rather than a combined outcome that may contain neither extreme.
All 9 pairings and the full ledger survive, so nothing is lost from the reasoning.

**7. The reasoning is made visible, and this is the demo beat.** Depth 1 and depth 2 render
as separate blocks with the question each answers, and **the winning framing's score is
shown** — today only pruned branches carry scores, so a reader sees three losers and never
learns what beat them:

```
Step 1 — Which reading of the history?        4 considered, 1 chosen
  f-01  0.85  Keep every rent year; exclude the 2020-22 price surge   ← chosen
  f-11  0.80  ...also screen the step-up years
  f-00  0.30  Include everything
  f-10  0.20  Screen rent years; include the price surge
Step 2 — Which band combinations to report?   9 considered, 3 kept
```

This is where the system visibly *reasons* rather than computes, and it needs no new
machinery — every framing already carries a score and a written rationale; the report just
flattens both levels into one undifferentiated list.

**It must also say the reasoning is a sample.** OQ-17 measured this model's scores swinging
widely on identical prompts. The *bands are deterministic*, so the numbers a reader takes
away do not move; only the commentary does, and the panel should say so.

#### Not taken

**Splitting rent and price into separate forecasts entirely.** It would delete depth 2 —
nothing left to pair — collapsing the search to four framings at beam width 1, reducing "13
hypotheses evaluated" to four, and stranding U8.6c's cut-margin measurement. Decoupling the
*presentation* gets the readability without spending the reasoning level.

#### Consequences for the sequence

**This is why U9.3 moved ahead of the report and the recording pass.** It changes every
forecast prompt, so it must land before U9.5 records anything — otherwise the tiers are
recorded twice. Also a text bug it fixes: the report says *"the base case is their compound
average"* right after naming two fiscal years, which reads as the average of those two; the
code takes the geometric mean of all retained years.

**Adopted Aug 31, 2026 by the architect as decision #21**, superseding #16's rent half. The
cohort-shift screen retires with the switch rather than being kept — the alternative was
offered and declined, on the reasoning that code whose only purpose was masking an FMR
artifact should not outlive the artifact.

### U9.4 ⬜ — The report: two axes, a recommendation and its cross-check, a lede, a template

**The architect's first priority, and the thing the demo actually shows.** Four changes to
one surface, landing together because they are one reviewable rework of the report's top.

**1. The recommendation is computed by the Critic, not the Summarizer.** The Critic
already aggregates flags into confidence and decides routing; a recommendation is the same
kind of judgment over the same state, and putting it there keeps the Summarizer's rule
that it *reports* rather than computes. A new `DealState` field carries the verdict and
the reasons behind it.

**Deterministic, and the reasoning is measured rather than stylistic.** OQ-17 found this
model scoring an identical prompt 0.05 on one call and 0.95 on the next, same deployment,
`temperature=0`. A recommendation behind that would make the same deal "proceed" on
Tuesday and "do not proceed" on Wednesday with nothing able to explain why, and it would
create a second axis the eval harness cannot score. **"Agentic" is not "stochastic"** —
the Critic's escalate decision is already a pure function and it is what makes this system
autonomous rather than advisory.

**1b. The model-proposes / rule-decides cross-check — ADOPTED Aug 31, 2026**, having been
written into this file as a deferral earlier the same day. The architect took it after
establishing that this system has only **one reasoning locus** (OQ-22): the forecast's
search is the only place a model exercises judgment, since #12's Critic half was retired on
evidence at U7.7 and only two agents call a model at all. This is the cheapest place to add
a second, and it lands where the reader is actually looking.

**How it works.** The model produces **its own independent verdict from the same state**,
used only as a cross-check. On the `overpriced` deal:

- **Rule:** asking price 55% above the ZIP benchmark → exceeds threshold → *"Proceed with
  caution — priced materially above comparable sales."*
- **Model, same state, independently:** may weigh it differently — the premium is declared,
  the rents are corroborated — and reach *"Do not proceed; the premium is not supported by
  the rent it generates."*
- **The report shows the rule's verdict, always.** On disagreement it adds a line saying an
  independent review of the same evidence reached a different conclusion, that the verdict
  follows the system's stated rule, and that the disagreement is **disclosed rather than
  resolved**.

**The disagreement is the product.** A deal where both agree is more trustworthy than one
where they split, and the reader learns which they are holding. **Reproducibility is
untouched** — the rule always decides, so the model can never move a verdict, only annotate
it. That is what makes this safe against OQ-17 where a model-decides design would not be.

**Cost:** one extra call, the comparison, a disclosure line, tests, and a recording per eval
row — the recordings ride U9.5's pass at no extra cost if the sequence holds.

**2. Two axes, two lines, never merged** — per the section above.

**3. The lede.** A short model-written summary above the report, `config.MODEL_SUMMARIZER`
unchanged (all five roles already hold the same ID, already guarded by
`verify_models_live()`). It **renders the verdict the rule computed; it does not reach
one.** Constraints: additive only, nothing removed or reworded by the model; the prompt
quotes rounded reader-facing figures, so it does not add a second instance of OQ-18's
float-in-prompt fragility; no internal vocabulary (§8); `config.SUMMARY_NARRATIVE_ENABLED`
so tests and the runner have one switch.

**On failure it renders a sentence, not a flag** — *"A written summary could not be
generated for this run; the disclosures and figures below are unaffected."* **Q1, answered
Aug 31.** A 31st `FlagKind` would break U8's 30-of-30 census unless a new declared fault
could reach it, and more fundamentally **every other flag in this system propagates** — a
flag raised in the terminal node has no consumer but the report already printing it.

**4. The template and the layout.** The architect's finding: a reader seeing many of these
reports meets the same boilerplate disclosures every time, and the pricing is buried. One
report with **progressive detail** — recommendation and headline figures first,
disclosures condensed with full text expandable, evidence (branch ledger, comp table, band
derivations) below.

**Two renderings — one investor-facing, one internal — is the cleaner design and is
deliberately not taken**, on timeline. Recorded so the report can say the demo reflects
seven weeks rather than the idealized end state, and so the next reader sees a choice
rather than an oversight.

**Tests must not start making live calls.** `tests/` calls `summarizer_agent()` directly
in ~76 places; `conftest.py` needs the same treatment `offline_scenario_evaluator` gives
the forecast, plus one test exercising the failure sentence.

### U9.5 ⬜ — Pin the live tier, and settle Staten Island

**The architect's second priority.** `staten-island` publishes 1 comp / 12 disclosures in
`eval/results/results.md` and produces 0 comps / 9 disclosures today, reproducibly across
two runs.

**The cause is structural and was found while explaining the tiers.** `_case_environment`
overrides the response cache for `golden` and `replay` only; **`live` rows fall through to
the default `LLM_CACHE_MODE=read_write` against `data/processed/llm_cache/` — 258 files,
gitignored.** So a live row is served from a *development* cache when warm and calls the
model when not. Two consequences:

1. **The seven live rows cannot be reproduced from a fresh clone**, by construction —
   against `eval/README.md`'s own argument that a figure a clone cannot re-derive is an
   assertion rather than evidence. They are unscored baselines, so it is defensible; it is
   nowhere stated.
2. It is the likely Staten Island mechanism: comp retrieval keys off the Extractor's
   bed/bath/floor-area parse, the deal sits at 1 comp against a threshold of 8, and one
   different cached extraction moves it to 0.

**The fix is to record the demo deals like every other tier**, which retires the class
rather than the instance and makes all 28 rows reproducible. **Confirm the mechanism
first** — clear the two cache entries, re-run, see whether the parse differs — because
recording a wrong extraction would freeze the defect instead of fixing it.

**This lands behind U9.4 deliberately, and the architect's ordering is right on a
dependency they may not have priced:** the lede adds a model call to a node every row
reaches, so both offline tiers need re-recording anyway. Recording after the Summarizer
rework makes that **one recording pass covering both** instead of two.

**The check is U8.8's and U8.10f's:** re-run both offline tiers and compare the table
byte-for-byte on confidence, disclosures, outcome and verdict. The recording diff should
be **additions only**.

### U9.6 ⬜ — The demo deals: one new, one shadow

**OQ-21's sixth deal.** Chicago Uptown at **1,100 sq ft** — U8.6b already found and
measured it: 8 comparables, 2 outside the size band, **no warn-severity disclosure**,
confidence **1.00**. It exists as the golden fixture `chicago-uptown-band-under`, whose
1,300 sq ft sibling escalates, so the pair also documents how narrow the clean margin is.
Calibrated under #11; `rent_basis` declared against #19's hybrid anchor.

**Plus one shadow deal, not five.** `los-angeles-current` beside `los-angeles`: the same
property re-based on the current anchor, originals untouched. **The architect proposed five
shadows and this is the counter-proposal they accepted** — five would need five
calibrations, five sets of `verify_demo_calibration.py` expectations and five new rows in a
table U9.5 is already repairing. One proves the method and gives a visible before/after on
the anchor change; four more are mechanical repeats if the schedule allows, and shedding
four unbuilt deals costs nothing while shedding four half-built ones costs the batch.

### U9.7 ⬜ — The Streamlit surface (decision #3, §6 cut-list item 4)

`src/app.py`, run as `.venv/bin/streamlit run app.py` from `src/`. Pure Python: the
pipeline is untouched and the app is a form plus `st.markdown(report)`.

**Replay by default, paste forces live.** The demo deals run from committed recordings —
instant, deterministic, no quota. A pasted listing has no recording, so it runs live and
**the surface says so**. That default is a direct answer to OQ-17, which names a live
Streamlit demo as exposed to run-to-run variance measured at ~1 in 15–20 attempts, on the
`los-angeles` deal specifically. A demo that replays cannot drift mid-presentation.

Renders: the listing → status strip (recommendation, confidence, threshold, disclosure
counts, comps) → lede → disclosures, property-scoped first → findings → comps → forecast
and ledger collapsed. **The `human_review` interrupt as a genuine pause**, with the desk it
routed to (U9.2), a note box and a Resume control — `main.py` auto-resumes with a canned
note, and letting a person type it is the honest version and the clearest human-oversight
evidence 7.1 asks for.

**A fault selector**, exposing `eval/cases.Fault` — `LLM_UNAVAILABLE`, `GEOCODER_OUTAGE`,
`STALE_RENT_INDEX` — which exist and are well-built but are reachable only from the eval
runner today. Needed for the demo's degraded-path moment, because a model outage cannot be
produced on demand. **Three demo deals already degrade naturally** (`no-geography`,
`staten-island`, `coord-conflict`) and those are the stronger demonstration, so the
selector is for the one failure a real input cannot reach.

**Two mechanical risks, named because they are how Streamlit demos break:** the script
re-runs top to bottom on every interaction, so the graph invoke must be guarded and its
result held in `st.session_state`; and the checkpointer needs a stable per-session
`thread_id`, since reusing one resumes a paused thread instead of starting a deal.

---

### ✂️ Cut line — I expect the freeze to land here

Everything below is real and none of it is speculative. If Sept 4 arrives with U9.7
unfinished, **stop at the line and write the rest up as gaps** rather than half-landing
them. §6's cut-list item 4 has a pre-agreed fallback — a terminal recording plus traces —
available late, which is what made keeping Streamlit safe.

**U9.9 sits below the line and is marked never sheds, which is not a contradiction.** If
the line is reached, capture happens *instead of* what stands above it, not after. The
report's own evidence outranks a further improvement to a surface.

---


### U9.8 ⬜ — Gross rent multiplier *(below the line; first thing built if the schedule allows)*

**The computable subset of investor criteria.** Matching against investor targets was
explored Aug 31 and is blocked honestly: cap rate needs **NOI**, which needs operating
expenses — taxes, insurance, vacancy, maintenance, management — and this project models
none of them. Assuming an expense ratio would put an unanchored number at the center of
the investment recommendation, which is the exact thing §2's invariants forbid.

**GRM needs nothing new**: price ÷ annual gross rent. Measured on the two reports —
**LA 15.3, Staten Island 9.2** — and it inverts the impression the banner gives, since the
escalated deal is the cheaper one per dollar of rent. An implied market GRM (ZIP benchmark
÷ modelled rent) gives it a comparison from data already committed. Roughly U9.6's size:
a Valuation computation, a state field, a report block.

### U9.9 ⬜ — Capture: live runs, traces, diagram, screenshots *(absorbed U8.9)*

Dropped from U8 on Aug 30 with no successor. Runs last: LangSmith free-tier traces expire
after **14 days** (OQ-13, no key present as of Aug 24), and screenshots must show the
surface that ships.

Live end-to-end runs; traces; the diagram regenerated via `scripts/export_graph_diagram.py`,
which asserts the topology including the single Critic→Planner back edge; screenshots off
the Streamlit surface. **Redact `tools/diagnostics.py:36` before any capture** — it
deliberately prints the account identifier, correct for a terminal and wrong for a recording.

**Demo shape, settled Aug 31:** the architect narrates as architect, not in persona. Clean
run, then an escalated run, then under the hood, with the investor-facing sections named
verbally. Live runs included, with waiting time edited out.

### U9.10 ⬜ — OQ-5, OQ-10 and OQ-14 written up

**OQ-5** — the four ToT constants were set by reading output, not tuning. What is known:
`TOT_TIE_EPSILON` is **not meaningfully straddleable** (noise-dominated, U8.6b/OQ-17), and
U8.6c's depth-2 cut margins found the discarded pairing often *outscoring* the reported one
and losing on `tot._rank`'s conservatism preference. Tuning against the golden batch was
**considered and declined** — those fixtures were authored by the unit that would tune
against them. Closing condition unchanged and unmet: a known-correct branch.

**OQ-10 closes Aug 31, 2026 by the architect: keep the fallback, fix the real exposure.**
`ignore/` is gitignored, so no key reaches the public repository, and requiring env vars
would only make a fresh clone harder to run — which is what 7.1 grades. The actual exposure
is `tools/diagnostics.py:36` printing an account identifier into a **recording**, fixed at
U9.M regardless of which way this went. The two halves of this question had different
answers and the entry conflated them.

**OQ-14 closes as discharged, same date.** Checkpoint 5.1 asked for design rationale —
roles, coordination strategy, communication approach — not build artifacts, so the treatment
U4 gave its acceptance criteria does not apply, and 5.1's response is submitted. 6.1's half
closed at U7.8. U9.9 regenerates the diagram and captures traces regardless, so attributing
those to 5.1 costs a sentence in the close-out rather than a subsection here.

### U9.M ⬜ — Maintenance *(separate commit, per §8)*

- **Logging.** 193 lines of HuggingFace/`sentence-transformers` HTTP noise print before
  every report. **Keep it as debug logging behind a toggle, defaulting quiet** (architect,
  Aug 31), so a demo recording is clean and a developer can still get it back.
- The `TODO(security)` redaction at `diagnostics.py:36`.
- **U8.M's remainder**: reconcile the `TODO` inventory in `engineering_standards.md`
  against `grep -rn "TODO(" src/`, and resolve the six `TODO(U8)` sites now U8 is closed —
  `config.py:685`'s says *"set a number, or delete this"*, and **#20 answered it**: the
  threshold stays `None` deliberately, foreclosed by evidence. A rewrite, not a deletion.
- **M2**: `main.py`'s CLI help says *"the U4 ablation"* — the one reader-facing site.
- **M6's docstring half**: `agents/comps_retrieval.py` states the relaxation order is set by
  "how much accuracy each concession costs", calling square footage the weakest signal — the
  rent model measures it as the **strongest** (0.502 against bedrooms' 0.300). Correct the
  docstring to say the order is inherited from U4 and that the measured importances do not
  support the claim. **Reordering the ladder is not U9 scope** — it would move comp sets
  across all 28 eval rows.
- **M4 and M5** from `maintenance.md`: §6's U8 row does not disclose that U8.9 was dropped,
  and §6's unit table has no U11 row at all.

### U9.11 ⬜ — Close-out

Review the changelog rows each commit already wrote; do not reconstruct them.

- **§6**: U9 ⬜ → ✅, restated as produced. **Cut-list item 4 leaves the list** — spent if
  the app shipped, *taken* if the fallback was used, and the difference stated.
- **§7**: **#3** confirmed landed; **#8** 🟨 → ✅ with both halves resolved and the
  Summarizer's model recorded as **inherited** — selected in U3's bake-off on schema-valid
  extraction, not on prose quality, and claiming otherwise is a claim the record does not
  support.
- **`open_questions.md`**: OQ-5, OQ-9, OQ-10, OQ-13, OQ-14, OQ-21 close. **OQ-17, OQ-18 and OQ-22 stay open** — OQ-22 is what #21 leaves behind rather than what it fixes. **OQ-17 and
  OQ-18 stay open** — the replay default mitigates OQ-17's exposure without answering it.
  **New entries**: #16's rent-growth source (U9.3 finding 1), and the two-renderings and
  model-proposes deferrals.
- **`decision_log.md`**: #8's Summarizer half; #3's outcome; the recommendation design.
- **`tasks/README.md`**: the U9 row.

---

## Status at a glance

| | Subsection | Status |
| --- | --- | --- |
| ✅ | **U9.1** README + committed model | Done Aug 31, 2026 |
| ✅ | **U9.2** personas, journeys, routing | Done Aug 31, 2026 — `docs/design/personas.md` + `state.ReviewDesk`/`desk_of` + the resume-note bug |
| ⬜ | **U9.3** forecast: ZORI re-source, evaluator, two tables | **Largest; supersedes half of #16** |
| ⬜ | **U9.4** report: axes, recommendation + cross-check, lede, template | Renders U9.3; adds the 2nd reasoning locus |
| ⬜ | **U9.5** pin the live tier; Staten Island | One recording pass, behind U9.3+U9.4 |
| ⬜ | **U9.6** sixth deal + one shadow | Recorded correctly the first time |
| ⬜ | **U9.7** Streamlit surface | Pre-agreed fallback if it slips |
| | *✂️ cut line* | |
| ⬜ | **U9.8** gross rent multiplier | First below the line if U9.1–U9.7 land early |
| ⬜ | **U9.9** capture: runs, traces, diagram, screenshots | Never sheds |
| ⬜ | **U9.10** OQ-5 / OQ-10 / OQ-14 written up | All three settled Aug 31 |
| ⬜ | **U9.M** maintenance | — |
| ⬜ | **U9.11** close-out | — |

**Twelve change sets against five days; the honest read is that seven land** — and U9.3
grew substantially on Aug 31, so that estimate is tighter than it was. The cut line is where
it falls.

**The ordering is the architect's, revised twice on Aug 31, and each revision fixed a
dependency rather than a preference.**

- **README first.** Graded directly, short, and leaving a graded deliverable to the end is
  how it gets written badly at midnight.
- **The forecast before the report**, because the report renders what the forecast
  produces, and rewriting the scenario section against bands that are about to change is
  work done twice.
- **Both before the recording pass.** U9.3 changes every forecast prompt and U9.4's lede
  adds a model call to a node every eval row reaches. Landing them first makes U9.5 **one
  recording pass covering the lede, the new bands and the demo deals together** instead of
  three.
- **The live tier pinned before new deals are added to it**, so the deals are recorded
  correctly on their first run.
