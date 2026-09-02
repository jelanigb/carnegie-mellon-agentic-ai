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

### U9.3 ✅ — The forecast: re-source rent growth, and repair the search

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
| **Los Angeles** | ZORI rent | +1.25 | **+2.51** | +4.76 | **3.5pp** |
| | price | −0.80 | **+2.10** | +4.50 | 5.3pp |
| **Chicago** | ZORI rent | +3.03 | +4.68 | +6.66 | 3.6pp |
| | price | −1.56 | +6.76 | +10.51 | 12.1pp |
| **Cleveland** | ZORI rent | −0.11 | +5.67 | +11.27 | 11.4pp |
| | price | −4.66 | +7.26 | +15.72 | 20.4pp |
| **New York (Bronx)** | ZORI rent | +3.12 | +7.04 | +12.31 | 9.2pp |
| | price | +1.65 | +3.73 | +5.90 | 4.3pp |
| **Staten Island (Richmond)** | ZORI rent | +3.93 | +7.00 | +10.45 | 6.5pp |
| | price | *no Redfin metro* | | | |

> **These are the corrected figures, and the correction is itself a finding.** The table
> #21 was adopted on was measured by windowing the *year-over-year observations* to 2018+;
> re-derived at build time, windowing the *level series* — which is what "match Redfin's
> span" actually asks for, since a 2018-06 difference reaches back to 2017-06 — moves
> Chicago's pessimistic band 1.45pp, from +1.58 to +3.03. The lower figure rested on a
> twelve-month stretch ending **2018-12**, which the price series does not cover: the same
> mismatched-span defect the window was introduced to remove. Nothing in #21's argument
> moves — LA is rent ~+2.5 against price +2.10 either way, and the FMR band is four times
> wider either way. **Staten Island is added because the published rows never contained
> it**: the "New York" row is Bronx (36005), taken from the HUD entityid prefix, while the
> `staten-island` demo deal resolves to Richmond (36085).

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

### U9.4 ✅ — The report: two axes, a recommendation and its cross-check, a lede, a template

**The architect's first priority, and the thing the demo actually shows.** Four changes to
one surface, landing together because they are one reviewable rework of the report's top.

**Measured before building, Sept 1, 2026, and the measurement changed the unit.** Full
investigation and the rule's design in
[`../design/recommendation.md`](../design/recommendation.md); the evidence is reproducible
with `scripts/sale_premium_distribution.py`. **The threshold at the center of this
subsection had nothing under it** — the committed benchmark table holds one median per ZIP
and no dispersion — so 44,358 real sales were re-pulled to ask what a premium is actually
worth. ZIP tier: +15% is the 68th percentile of actual sales, +30% the 80th, +50% the 89th.
A threshold is defensible there. **Metro tier is twice as wide and Los Angeles is not in
the data at all** (Proposition 13 publishes assessed value, not price), so every metro
figure is extrapolated from New York and Chicago.

**That falsified the worked example this subsection was planned around**, and the
correction is a subsection of its own. `overpriced` is a Los Angeles deal, 90027 has **no
ZIP benchmark**, so its +55% is 55% over a *metro* median — the **78th percentile**, an
ordinary sale. **Re-sited to a market with a local tier** (architect, Sept 1) rather than
bending the threshold to fit the fixture; the three alternatives and why each was declined
are in the design doc. It lands in U9.4 rather than U9.6 so that U9.5 records it once.

**1. The recommendation is computed by the Critic, not the Summarizer.** The Critic
already aggregates flags into confidence and decides routing; a recommendation is the same
kind of judgment over the same state, and putting it there keeps the Summarizer's rule
that it *reports* rather than computes. A new `DealState` field carries the verdict and
the reasons behind it.

**Four verdicts, and reject needs two independent failures.** *No recommendation* (no price
or no benchmark) · *Do not proceed* (premium past the reject threshold **and** an
uncorroborated rent claim) · *Proceed with caution* (either one alone) · *Proceed*.
Thresholds are set at stated percentiles rather than round numbers — caution at p80, reject
at p90 — so the report can say what a threshold means. Reject takes two instruments because
the benchmark is explicitly not a valuation: the report says so in bold, and resting an
outright rejection on that one figure would contradict the caveat beside it. The rule reads
neither the confidence score nor the escalation decision, because those are axis 1.

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

- **Rule:** asking price 55% above the ZIP benchmark → past the caution threshold, rents
  corroborated so the reject condition is not met → *"Proceed with caution — priced
  materially above comparable sales."*
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

#### What landed, Sept 1 — six commits, and two findings the plan did not contain

**The rule was built the wrong way round first, and `staten-island` caught it.** The first
draft let an uncorroborated rent reach *caution* on its own, which put an axis-1 fact — can
the comp cross-check run in this market — onto the axis-2 line, re-merging the two axes one
line below where the unit had just separated them. The price finding is now the only thing
that can *start* a verdict and the rent side only ever modifies one; reject still needs
both. Regression test: `test_an_uncorroborated_rent_alone_does_not_reach_caution`.

**The suite had silently started making live calls**, through the new Critic path, and
nothing caught it but the wall clock — 48s before the `conftest.py` seam, 13s after. Worth
carrying as a pattern: a new model call in a shared node reaches every test that renders a
report, and no test fails when it does.

**One residual, flagged rather than fixed.** The written summary needed two prompt passes
and then a structural change — dropping the disclosure excerpts entirely — before it stopped
mischaracterizing evidence, twice describing rental comparables as sales. Iteration stopped
there on U9.3's precedent, since further tuning fits a single draw (OQ-17). **The figures it
quotes are checked; its prose is not**, and the final report should say so rather than
present the lede as verified output. U9.5's recording pass freezes one draw per row, which
converts this from run-to-run exposure into a fixed artifact that can be read once and
checked — the strongest mitigation available inside the freeze.

### U9.5 ✅ — Pin the live tier, and settle Staten Island

**The architect's second priority.** `staten-island` publishes 1 comp / 12 disclosures in
`eval/results/results.md` and produces 0 comps / 9 disclosures today, reproducibly across
two runs.

#### Measured Sept 1, before starting — the tiers are not stale, they are broken

**Both offline tiers error on every row.** A golden-tier run returns `CacheMiss` on all 15
cases and a flag census of 0 of 30. The cause is U9.3, not U9.4: rewriting `_context_block`
and `_DEPTH_INSTRUCTIONS` is a prompt change, and it invalidated every forecast recording on
Aug 31; U9.4's two new model calls stack on top of that rather than causing it. **The
committed `eval/results/results.md` was last written Aug 30 at U8.6e**, so the published
evaluation describes a build two units old, and its `overpriced` row is the Los Angeles
siting U9.4 replaced.

That moves this subsection from *next in line* to *on the critical path*: the eval harness is
one of the two suites §6 never cuts, the final report quotes its numbers, and right now a
fresh clone reproduces none of them. `CacheMiss` subclasses `Exception` rather than
`LlmError`, so it is not swallowed by the lede's or the cross-check's degradation handlers —
the row fails loudly, which is why this was visible at all.

**The development cache is empty — 0 files, where this section recorded 258.** The warm-cache
condition that made a live row non-deterministic is therefore gone, and a live run today is
an honest measurement rather than a mixture. That is the precondition the Staten Island
diagnosis below asks for, already satisfied.

#### Staten Island: settled, and it was never a defect

**Measured against the corpus directly, no model calls.** 0 listings within 4 miles of
7001 Amboy Rd; **7 within 8 miles, none of them 2-bedroom**, against a 2-bedroom subject.
At the widest radius the relaxation ladder reaches, with the square-footage band already
dropped, there are **zero eligible candidates** — so no extraction of this listing can
produce a comp. Zero is structural. The published `1` was the stale development-cache
extraction the tier pin retires, and the deal's own declaration was right all along.

**A second-order finding for U9.M, recorded because it is concrete evidence for an item
that was previously an argument.** The ladder spends all four iterations on the size band
and two radius widenings and **never reaches the bedroom count** — which is the binding
filter on this deal. So the ladder as ordered could not rescue this deal even in principle.
That does not change U9's scope (reordering moves comp sets across all 28 rows), but it
turns the docstring correction into a documented instance rather than a general caution.

#### A dependency U9.7 has on this pass, found here and not in the plan

**The eval batch cannot record what the demo surface will replay.** An escalating case
pauses at `human_review` and `run_case` never resumes it, so **no run of the harness ever
reaches the Summarizer on those rows** — and therefore never records the written summary's
prompt. Three demo deals escalate (`staten-island`, `no-geography`, `coord-conflict`), plus
`chicago`.

**That matters because a miss is fatal rather than graceful.** `CacheMiss` subclasses
`Exception`, not `LlmError`, and `LlmClient.complete` lets it through, so it passes
straight by `_lede_section`'s `except (LlmError, RuntimeError, OSError)` and takes the
Summarizer node down. U9.7's replay-by-default surface would crash on exactly the deals
whose degraded paths make the best demo.

**Fixed by recording, not by widening the catch** — and the choice is deliberate. Catching
`CacheMiss` in the Summarizer would make a drifted prompt render a report with its summary
quietly missing, which is the failure the replay design exists to make loud. Instead the
demo deals are recorded through `main.py`'s full path, resume and summary included, so the
miss never occurs. That needs `config.LLM_CACHE_DIR` to be env-overridable the way
`LLM_CACHE_MODE` already is; it now is.

#### Two decisions taken Sept 1 by the architect

1. **Replay by default; `--live` opts in.** All rows replay from committed recordings, so
   every published figure is reproducible from a fresh clone. A genuinely live run becomes an
   explicit flag — which is the path U9.7's paste box and U9.9's live capture still use.
   Chosen over keeping a tier that calls the model on every run, because the reproducibility
   gap is the thing this subsection exists to retire.
2. **`results.md` gains a recommendation column.** U9.4 added axis 2 and the harness cannot
   currently see it; the rule was made deterministic precisely so a batch could score it.
   Baselines carry their measured verdict. **Declared axis-2 verdicts for the 21 predicted
   cases are *not* taken** — authoring 21 predictions after the rule exists is what
   `VerdictSource.PREDICTED` exists to prevent, and the batch would score the rule against
   itself.

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

**The check U8.8 and U8.10f used does not transfer to this pass, and substituting it would
be false comfort.** Those passes asserted the table was byte-identical because their changes
were verdict-inert by design. This one is not: U9.3 moved every band, U9.4 added a verdict
and re-sited `overpriced`. **So the check is that every moved row has a named cause** — the
table is re-derived, then read row by row against those two change sets, and any movement
neither explains is a defect to chase rather than a diff to accept. The recording diff should
still be **additions only**: superseded recordings are orphaned, not deleted, so what the old
table was produced from stays in the repository.

**Carry one prompt change into this pass, from U9.3.** `TODO(U9.5)` at
`agents/scenario_forecast._DEPTH_INSTRUCTIONS`: depth 1 should be told that treating both
series alike is not, by itself, a reason to prefer a framing. Since #21 both forks ask the
same question — does the 2020–2022 rate regime belong in the record — of two different
series, and that put a cheap generic argument within reach that did not exist when the two
axes described different events. Los Angeles took it, scoring `f-00` at 0.95 for *"uses
the same 2020-2022 window for both rent and price"*.

**Not a defect, and the measurement says so.** On `staten-island` the off-diagonal `f-01`
won at **0.96** against the diagonal `f-11`'s **0.15**, arguing from a real asymmetry:
Richmond's ZORI series begins 2020-08, *inside* the excluded window, so holding it out
amputates the front of its history and leaves 43 observations from 2023-01 — where Los
Angeles keeps its 2019 block and loses a middle segment. Three of the four framings have
been chosen across five demo deals, so the level still decides something. This is one weak
argument being available, not a level that stopped working.

**It rides here because it is a prompt change**, and a prompt change invalidates every
forecast recording. Landing it in this pass costs one re-recording instead of two, which is
the same dependency that put U9.5 behind U9.3 and U9.4 in the first place.

### U9.6 ✅ — The demo deals: one new, one shadow

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

#### Measured Sept 1, before starting — what the stale rent basis actually costs, per deal

**The whole unit turns on one number that had never been read per-deal.** OQ-21 says the
new deal's rents must be declared against the index the system now uses "or it ships stale
on day one", and the shadow exists to show that change on an existing deal. How large that
change is was never measured. It is, at FY2026 against the market index at 2026-07:

| ZIP | FMR 2BR (the basis on file) | market index | basis → index | stated rents | stated vs. index |
| --- | --- | --- | --- | --- | --- |
| 90026 Echo Park (`los-angeles`) | $2,903 | $2,691 | **−7.3%** | $2,900 | **+7.8%** |
| 60640 Uptown (`overpriced`) | $1,781 | $2,026 | **+13.8%** | $1,775 | **−12.4%** |
| 60647 Logan Square (`chicago`) | $1,781 | $2,371 | **+33.1%** | $1,775 | **−25.1%** |

**Two things fall out, and the second contradicts what this repository has been saying.**

- **The offset is not uniform and it is not even one-signed.** `demo_deals.py`'s docstring
  explains the staleness with "HUD's 40th percentile runs about a third under the market",
  which is true in Logan Square and **false in Echo Park**, where the county schedule runs
  7% *above* the ZIP's market index. LA's FMR comes back `used_msa_fallback: True` — a
  county-wide figure spanning Malibu to Compton — so it is not a sub-market number at all,
  and it happens to land above Echo Park rather than below it. The docstring generalizes
  from Chicago to the set; only Chicago supports it.
- **`los-angeles` is the smallest of the three moves, and it is still the right shadow.**
  The point of the shadow is not the size of the number but that it is the *only*
  difference between two otherwise identical reports — and only on `los-angeles` is the
  report clean enough for that to be visible. The line that moves is *"the stated rents sit
  **1% above** that estimate"* → **~6% below**, a sign flip on an isolated line in a
  1.00-confidence report. A Logan Square shadow moves +33% but lands it inside a report
  that escalates and carries ten disclosures, where a reader cannot attribute anything. The
  measurement is recorded here because it is a finding either way, not because it changes
  the choice.

**The bedroom half of the hybrid anchor is inert on every deal in this set.**
`config.RENT_ANCHOR_SHAPE_REFERENCE_BEDROOMS = 2` and every demo listing is 2-bedroom, so
the FMR step is exactly 1.0 and `anchor = ZORI(ZIP)` with nothing composed. The
verification must still compose both halves anyway — a basis that silently drops the term
it does not currently need would be wrong the first time a deal is not 2-bedroom, and
would look correct until then.

#### Subsections, each its own commit

**U9.6a — the rent basis the system actually uses.** `demo_deals.py` gains a
`market_anchor:<bedrooms>` basis kind beside `hud_fmr:<bedrooms>`, and
`verify_demo_calibration.py` learns to re-derive it — through `rent_model.anchor_for_row`,
the same function the pipeline anchors on, rather than a second implementation of the
formula. No deal changes. It lands first because it defines what "calibrated" means for
every deal after it, and because both deals below depend on it.

**U9.6b — the sixth deal.** Chicago Uptown, 1,100 sq ft, at the golden fixtures' own
address (**5100 N Kenmore Ave, 60640**) so the demo deal *is* the property U8.6b measured
rather than a second one nearby. Price calibrated to `zip_sale_benchmark:60640` — $867,500
over 148 recorded sales — with no declared premium, so the report reads *in line with*
comparable sales in this ZIP and axis 2 returns *Proceed*. Rents at `market_anchor:2`
(~$2,026). `demo_deals.py`, `main.py`'s docstring, `eval/cases._DEMO_BASELINES`.

**U9.6c — the shadow.** `los-angeles-current`: `los-angeles` with its two stated rents
re-based from $2,850 / $2,950 to the market index (~$2,650 / $2,730), `rent_basis`
`market_anchor:2`, everything else byte-identical including the price basis — #19 was a
rent decision and the asking price has no business moving with it. The original is
untouched.

**U9.6d — record the two rows and re-derive the table.** `--record` scoped to the two new
cases only; then the full batch in replay. **The check is that the other 28 rows come back
byte-identical** — nothing in this unit changes a prompt, so any movement is a defect to
chase rather than a diff to accept. `results.md` goes 28 → 30 rows and its regression count
6/7 → 8/9. `sensitivity.md` is untouched *if* the two rows are baselines (Q2 below).

**U9.6e — `docs/demo.md`.** The two new deals get sections, and the document's existing
figures get corrected. **It is materially stale and this unit makes it worse:** it
describes `overpriced` as a Los Feliz listing in Los Angeles at 0.85 (it is an Uptown
listing in Chicago at 1.00 since U9.4), `chicago` as reporting at 0.85 (it escalates),
`los-angeles` as carrying 3 disclosures (4), and Staten Island as 4 info / 8 warn (6 info,
5 warn, 1 critical). It also has no notion of axis 2, which is the thing U9.4 built. Scope
call at Q3 below.

#### Decisions taken inside this subsection rather than raised

- **No `rent_premium_to_basis` field.** `demo_deals.py`'s docstring predicted that
  calibrating stated rents to the market index would make the stated-versus-modelled
  section an artifact of the calibration — the defect `price_premium_to_basis` exists to
  prevent on the price side. It does not follow here, and the reason is arithmetic: the
  estimate is `ratio × index`, so a listing calibrated to the index prints `1/ratio − 1`,
  which is the model's own read on *this* unit against its ZIP's typical rent, and differs
  by deal. Two of eight deals move to the new basis, so the section still varies across the
  set either way. The field would ship unused; recorded here so the docstring's caution is
  answered rather than ignored.
- **The new deal is not given a declared price premium.** `overpriced` is the deal that
  exercises a non-zero premium and it is 500 feet away in the same ZIP. Making this one
  clean on both axes is what OQ-21 asked for, and the two together become a pair that
  differs in the asking price and nothing else — same neighborhood, same profile, same
  axis-1 outcome, *different recommendation*. That is the sharpest demonstration available
  that axis 2 is computed rather than decorative.

#### Blocking questions — answered before U9.6b starts

**Q1 — has OQ-21's premise already been met?** OQ-21 was raised when `chicago` began
escalating and `los-angeles` "became the only demo deal reaching 1.00 and reporting clean".
That is no longer true: U9.4 re-sited `overpriced` to Uptown and it now reports at **1.00**
with six info-severity disclosures. So the set already shows a clean run twice on axis 1.
**What it does not have is a second deal clean on *both* axes** — `overpriced` is
*Proceed with caution* by construction — and `los-angeles`'s own *Proceed* rests on a
premium that is 0% because #11 derived its asking price from the same metro median the
report benchmarks it against (the circularity at `critic.recommend`'s zero-premium branch,
OQ-20's). The new deal is the first demo listing whose *Proceed* is measured against a
local benchmark built from 148 real recorded sales. **Recommended: proceed, on that
restated purpose rather than on OQ-21's original wording**, and note the restatement when
OQ-21 closes.

**Q2 — `BASELINE` or `PREDICTED`? ANSWERED Sept 1 by the architect: `PREDICTED`, and the
question was posed on a misreading.** It was put as "both deals are sited on published
measurements they are expected to reproduce, so declaring a verdict is closer to
transcription than prediction" — which treats `BASELINE` as meaning *the outcome was
knowable in advance*. It does not. `cases.py`'s rule is that a verdict is `PREDICTED` when
it is **derived from the target flag's severity and the shipped escalation rule, and from
nothing else**, and `BASELINE` is the narrower label for a case **whose own outcome was
already published** — the U7.8 table. Neither new deal has one, so `PREDICTED` is not
merely defensible, it is the only accurate label.

**Three things settle it, and each was already in the repository:**

- **The existing 21 were sited by measurement too.** `scripts/straddle_probe.py` found
  `chicago-uptown-band-under`'s 1,100 sq ft by running the real retrieval and Valuation
  agents over a grid. Those fixtures "were run while they were being designed", in
  `cases.py`'s own words. Knowing what a case will do has never been what separates the
  two labels.
- **The prediction can fail, and its nearest neighbour did.** `chicago-uptown-band-over`
  is the same address and the same fixture family, 200 sq ft away, with a verdict derived
  the same mechanical way — and it is a **MISMATCH**. The escalation decision is
  combinatorial (score threshold, *or* any critical, *or* an exhausted rework budget, with
  the interaction objections gated on whether the comp cross-check ran and whether it
  diverged), so a clean-looking deal is not a safe bet. **18/21 rather than 21/21 is the
  evidence the instrument works**, and it is the reason to put honest predictions into it
  rather than hold them out.
- **The "free agreements inflate the score" worry was answered before it was raised.**
  `scripts/confidence_sensitivity.py`'s docstring already states that *"the cases were
  written knowing the shipped values, so agreement measures the fixtures"* — which is
  precisely why that sweep asks a **robustness** question rather than an agreement one.
  The contamination this question worried about is the contamination that script was built
  around.

**Precedent, and it argues for the addition rather than merely permitting it.**
`la-ordinary-duplex` and `chicago-uptown-duplex` are `targets=()` controls predicting
`reports`, and `cases.py` says they exist because "a batch of nothing but escalating cases
can be scored 100% by a threshold of 1.0, so agreement would measure nothing." Two more
`reports` controls make the agreement figure more two-sided, not less.

**The discipline this puts on U9.6b and U9.6c.** Each note must derive its verdict
mechanically — *no warn-severity disclosure is expected, so the score holds at 1.00 and the
deal reports* — and must **not** say "because `chicago-uptown-band-under` measured 1.00".
The second is transcription wearing a prediction's label, which is the exact thing
`VerdictSource` exists to catch. Consequences: the scoring population goes **21 → 23**, and
`sensitivity.md` re-derives (one replay batch to collect flag sets, then an in-memory
sweep). Whether the **63-of-160 plateau moves is reported, not assumed** — two cases at
1.00 with no warns should be non-discriminating at every threshold on the grid, and if the
plateau moves anyway that is a finding about the sweep rather than a diff to accept.

#### What landed, Sept 1 — six commits, both predictions held, and two defects found

**`chicago-uptown`** reports at 1.00 / 5 info / *Proceed*; **`los-angeles-current`** at
1.00 / 4 info / *Proceed*, raising exactly what `los-angeles` raises. The other **28 rows
are byte-identical**, so the whole diff is two additions and agreement moving 18/21 →
20/23. `sensitivity.md`'s grid and its 63-of-160 plateau are unchanged.

**The shadow's result is one line, which is what it was built for.** Same property, same
$2,861 estimate — the model never sees a stated rent, so its output cannot move — and the
comparison beneath it flips from **1% above** to **6% below**.

**Two defects found while building, neither in the plan:**

1. **The sensitivity sweep's live-tier exclusion was silent and had just become
   load-bearing.** `scoring_cases()` already drops `BASELINE`, so filtering live rows
   removed nothing while every live case carried one. U9.6's two deals declare
   `PREDICTED`, making that filter the only thing keeping them out — and the artifact's
   header still claimed to cover "21 cases with a verdict declared before the run" when 23
   now exist. The behavior is right and was the original intent; it was undocumented, and
   `results.md` and `sensitivity.md` had silently started counting different populations.
2. **`docs/demo.md` carried a claim that was wrong rather than stale.** It said the U4
   ablation was the only run landing at exactly 0.60 and escalating on the critical rule
   instead of the score. `coord-conflict` does too, and `chicago` escalates at 0.70.

**And one correction to this unit's own record:** every changelog row and docstring it
added was first dated **Sept 2** when the work was done **Sept 1**. Fixed in its own
commit, because date traceability is the whole reason the changelog exists.

**One item deliberately left for U9.11.** OQ-21 closes there, not here, and its close must
record that **the entry's premise was met before the deal was built** — U9.4's re-siting
of `overpriced` gave the set a second clean axis-1 run, so the deal ships on the restated
purpose (the first *Proceed* measured against a benchmark it was not derived from) rather
than on OQ-21's original wording.

**One stale claim found and deliberately not fixed.** `eval/cases.py`'s
`chicago-five-bedroom` note says "the county-level anchoring warning that three of the six
demo deals share". The count is now wrong and the claim probably is too — U11.3 made that
warn rare, and `golden_fixtures.py` records it co-occurring on **0 of 21 cases**. Fixing it
needs a measurement rather than a word change, so it belongs to U9.M rather than to a
silent edit here.

**Q3 — is `docs/demo.md` in this unit or its own?** It is four units stale and this unit
adds two more deals to it. Folding it in keeps the demo guide true; splitting it out keeps
U9.6 to three code commits with three days left and U9.7 unstarted.

### U9.7 ✅ — The Streamlit surface (decision #3, §6 cut-list item 4)

`src/app.py`, run as `.venv/bin/streamlit run app.py` from `src/`. Pure Python: the
pipeline is untouched and the app renders what the Summarizer already produces.

**Replay by default, and the surface says which mode it is in.** The demo deals run from
committed recordings — instant, deterministic, no quota. That default is a direct answer
to OQ-17, which names a live Streamlit demo as exposed to run-to-run variance measured at
~1 in 15–20 attempts, on the `los-angeles` deal specifically. A demo that replays cannot
drift mid-presentation.

Renders: the listing → status strip (recommendation, confidence, threshold, disclosure
counts, comps) → lede → disclosures → findings → comps → forecast and ledger collapsed.
**The `human_review` interrupt as a genuine pause**, with the desk it routed to (U9.2), a
note box and a Resume control — `main.py` auto-resumes with a canned note, and letting a
person type it is the honest version and the clearest human-oversight evidence 7.1 asks
for.

**Two mechanical risks, named because they are how Streamlit demos break:** the script
re-runs top to bottom on every interaction, so the graph invoke must be guarded and its
result held in `st.session_state`; and the checkpointer needs a stable per-session
`thread_id`, since reusing one resumes a paused thread instead of starting a deal.

#### Measured Sept 1, before starting — four premises, three confirmed and one defect

**Every claim below was run rather than reasoned about**, because this unit's own
opening records that reading one actual run changed the whole unit. What follows is what
the surface can and cannot replay, established before anything was built against it.

| Path | Replays from committed recordings? | Evidence |
| --- | --- | --- |
| The 8 demo deals, escalation and resume included | **yes** | Both sample reports re-derived byte-identical |
| A reviewer's **free-text** note at the pause | **yes** | The note reaches no prompt — `_lede_prompt` never reads it; verified by resuming under a novel note |
| `LLM_UNAVAILABLE` | **yes, for free** | Patches `LlmClient.complete` *above* the cache, so no lookup happens. Completes, 5 flags, escalates at 0.00 |
| `GEOCODER_OUTAGE`, `STALE_RENT_INDEX` | **no** | The fault changes state that reaches the forecast prompt → `CacheMiss` |
| `--no-retrieval` | **no, but barely** | Replays *to the pause*, then misses on the post-resume summary call alone |
| A pasted listing | **no, by construction** | No recording exists for a prompt nobody has seen |

**The free-text note replaying is the single most load-bearing result here**, and it was
not obvious: it is what makes a genuine human-in-the-loop pause compatible with a
deterministic demo. If the note had reached the lede's prompt, the surface would have had
to choose between honest oversight and reproducibility.

**The ablation's near-miss is a gap U9.5 left, not a new problem.** That subsection
recorded the demo deals through `main.py`'s full path precisely because the eval harness
never resumes and so never records the Summarizer's summary call. It did that for the
eight deals in `DEMO_DEALS` and not for the ablation variant, which is an eval row
(`chicago--no-retrieval`) rather than a demo deal. One recording closes it.

**And one real defect, found by reading a log line nobody was reading.**
`graph.state_serde()`'s allowlist was missing four types reachable from `DealState` —
`ConfidenceBreakdown` (U7), `FlagScope` (U8.5), `Recommendation` and
`RecommendationDetail` (U9.4). The two `BaseModel` types deserialized to a plain **dict**
on the resume path. No report was ever wrong, because Pydantic re-validates at the node
boundary — but `graph.invoke`'s *return value* carries the raw dict, and **this surface's
status strip is the first caller in the project that reads a typed field off a resumed
run.** `main.py` reads only `report_markdown`; the eval harness never resumes. Fixed and
verified as maintenance ahead of this subsection: 97 tests pass, all 30 eval rows and both
sample reports byte-identical. **The recurrence is the finding** — the rule that would
have prevented it was already written in that function's own docstring, by the pass that
learned it in U5.

#### Three decisions taken Sept 1 by the architect

1. **One rendering, split on its own headings.** The report is rendered as the Summarizer
   emitted it, split at each `##` into a collapsible section, with the top matter
   (verdict, system check, lede) always visible and the status strip built from typed
   state. **Chosen over the app laying out its own components**, which would create the
   second rendering U9.4 recorded as deliberately not taken: two renderings of the same
   evidence drift the first time either is edited, and the report is the artifact under
   review. Progressive detail is bought mechanically rather than by re-authoring.
2. **All three faults, pre-recorded.** The degraded-path demo stays offline and identical
   every time. Costs one recording session and puts the recordings in the diff, against
   the alternative of 30–60 seconds of dead air and OQ-17 exposure at the exact moment the
   demo is showing a failure path.
3. **The retrieval ablation gets a control**, on the measurement that it costs one
   recording rather than a design change. It is Checkpoint 3.1's headline evidence and the
   surface can show it as a before/after on one listing — 8 comps and a warn against 0
   comps and a critical — from the same code path as everything else, rather than citing a
   number from `results.md`.

#### Subsections, each its own commit

**U9.7a — one fault-injection seam, and a CLI that can reach every state the surface
replays.** The injection logic lives inside `eval/runner._case_environment`, which takes
an `EvalCase`; the app needs the same three faults against a `DemoDeal`. Extracted to a
shared context manager both call, rather than reimplemented — on the precedent
`hud_fmr.bedroom_field` states explicitly, that a rule reimplemented at a second call
site produces *"a training set capped differently from the inference path"*, which is a
silent defect rather than a loud one. **A fault that behaved differently in the demo than
in the evaluation would invalidate both at once**, and neither would say so. `main.py` gains
`--fault`, which is also how U9.7b records. No behavior change to any existing row.

**U9.7b — record the three new combinations.** `chicago --no-retrieval`,
`los-angeles --fault geocoder-outage`, `los-angeles --fault stale-rent-index`, each
through `main.py`'s full path so the resume and the written summary are captured — the
thing U9.5 established the eval batch structurally cannot do. `los-angeles` is the siting
for both faults because it is the one demo deal that reports clean at 1.00, so the
contrast is attributable to the fault and nothing else; it is also where the existing
golden fixture `la-stale-rent-index` already sites that fault. **The check is that the 30
eval rows come back byte-identical** — nothing in this subsection changes a prompt an
existing row uses — and that the recording diff is **additions only**.

**U9.7c — the surface.** `app.py`: deal picker, guarded invoke held in
`st.session_state`, a stable per-session `thread_id`, cached graph and index resources,
replay pinned by assigning `config.LLM_CACHE_MODE`/`LLM_CACHE_DIR` the way
`eval/runner._case_environment` does. Status strip from typed state; report split on `##`
into expanders. **The model liveness check is skipped when the run will not go live** —
in replay it can only add a network round-trip and a failure mode to a path that calls no
model.

**U9.7d — the pause, the controls, and the mode badge.** The `human_review` interrupt
rendered as a genuine pause: the desk it routed to, the flags that caused it, the
unanswered questions, an editable note and a Resume control. Plus the ablation checkbox,
the fault selector, and the paste box — all three unified by **one question the surface
answers before it runs anything: is this combination recorded, or will it call the
model?** A live run is stated and confirmed rather than discovered. That is Transparent
Degradation applied to the surface itself, and it is one mechanism serving four controls
instead of four special cases. **The largest of the four commits and where review should
focus**; it splits cleanly at the pause if review capacity says so.

**U9.7e — docs.** README gains the app and **its stale figures are corrected**: it says
28 eval cases where there are now 30, and lists 6 demo deals where there are 8, both
since U9.6. `docs/demo.md` gains the surface. Folded in here rather than left to U9.M
because the README is a graded artifact (7.1) and the numbers are wrong today.

#### What landed, Sept 1 — five commits, and every premise held

**`src/app.py` ships**, and §6's cut-list item 4 **leaves the list by being spent** rather
than shed — the fourth item to do so, after #3's LLM rent fallback, #11's public-record
benchmark and #19's anchor.

| Run | Confidence | Disclosures | Comps | Recommendation |
| --- | --- | --- | --- | --- |
| `los-angeles` | 1.00 | 4 | 8 | Proceed |
| `staten-island`, released by a reviewer | 0.00 | 12 | 0 | Proceed ⚖ |
| `chicago`, no comparables | 0.60 | 6 | **0** | Proceed ⚖ |
| `los-angeles` + address lookup down | 0.85 | **20** | 8 | Proceed |
| `los-angeles` + stale rent index | 0.85 | 6 | 8 | Proceed |
| `los-angeles` + model unreachable | 0.00 | 5 | 0 | No recommendation |

**Every figure matches the command line exactly**, which is the check that the surface
renders the pipeline rather than a second reading of it. Verified through Streamlit's own
`AppTest` rather than by eye, including the full oversight path: escalate, route to the
agent desk, type a novel note, release, and read the note back verbatim in the finished
report.

**The geocoder row is the best single demo beat and was not planned as one.** 20
disclosures against the same deal's baseline 4, because the outage is the system's *only*
retryable objection — so the Critic sends the deal back to the Planner, the retry fails
the same way, and the bounded rework cycle visibly spends its budget before escalating.
Three passes of the same flag, and the counter terminating is the thing Checkpoint 6.1
asks to see.

**Two findings the plan did not contain.**

1. **`Proceed ⚖` on a resumed run only renders because of the serde repair.** The
   disagreement marker lives on `RecommendationDetail`, which reached the status strip as
   a bare `dict` before the allowlist was fixed. The pre-flight predicted an
   `AttributeError` here; this is that prediction being confirmed from the other side.
2. **The simulated-failure marker was internal vocabulary in reader-facing text**, and
   nobody had noticed because until now only the eval harness produced it. *"[eval fault
   injection, case 'x']"* is wrong twice over on a demo run — neither an evaluation nor a
   case — and it renders in the report. Rewritten, and **the safety of rewriting it was
   measured rather than argued**: it reaches no prompt, confirmed by re-deriving all 30
   rows byte-identical rather than by reading the two call sites.

**One thing deliberately left behind.** `architecture.md`'s repository tree lists
`eval/run_eval.py` and `eval/expected.yaml`, neither of which exists, and marks the Critic
and Summarizer as unfinished. `app.py` and `tools/faults.py` were added to it correctly;
the rest is recorded as **M7** in `maintenance.md`, because re-deriving that tree from the
filesystem is the only fix that stops it drifting again, and editing it entry by entry is
what let it drift.

#### Open, and deliberately not resolved here

**Whether the surface should ever be the thing that goes live.** The paste box forces a
live call by construction, and OQ-17 says a live call on this model can move a verdict on
a genuinely borderline deal. The surface discloses the mode; it does not defend against
the variance, and nothing in this unit can. Named so the final report describes the demo
as replayed evidence plus one live path, rather than as a live system.


### U9.7T ⬜ — The scenario table: name the rows for what they say, and the ledger for what decided them

**Raised by the architect Sept 1–2, 2026, reading `docs/sample_reports/los-angeles.md`.**
The reported symptom: *"the scenario table shows base in the pessimistic row and pessimistic
in the base row."* It is expected behavior, it is documented in three places, and it is still
unreadable — which is the same lesson U9.3 recorded and only half-acted on. **Inserted above
the cut line on Sept 2 at the architect's direction**, ahead of U9.8/U9.9/U9.M.

**Presentation and disclosure only. The search is not touched** — no prompt changes, no
candidate payload changes, no re-record. That boundary is deliberate: the deeper question
about depth 2 is OQ-22's and is not affordable before the freeze (see *Open* below).

#### Three findings, each measured before the plan was written

**1 — the same three words carry two meanings in one row.** The row label names the
*combined* outcome rank among survivors (`scenario_forecast._to_scenarios`); the
parenthetical names the *band one series* drew from. U9.3's fix was partial: `_band_tables`
correctly abandoned the optimistic/base/pessimistic vocabulary for "Weakest sustained
stretch / Long-run average / Strongest sustained stretch", and the combined table directly
beneath it was never brought into line. So the report now prints plain words for the bands
in one table and internal band names for the same bands in the next.

**2 — the labels claim a spread the set does not have.** `_labels_for` stamps
`pessimistic / base / optimistic` onto whatever three survive, unconditionally. On
`los-angeles` the "Optimistic" row is base rent × base price, and **neither series' strongest
band appears in any row**. A reader takes +2.51%/+2.10% for the upside case when it is the
central case and no upside case was shown.

**3 — the ledger attributes to the model a decision policy made, on half of all runs.**
Measured across `eval/data/llm_recordings/`, reproducing `tot._rank`'s grouping exactly:

| Level | Recorded levels | Decided by the model's scores | Decided by the conservatism tie-break |
| --- | --- | --- | --- |
| Depth 1 — which framing | 78 | **78 (100%)** | 0 |
| Depth 2 — which pairings | 79 | 39 (49%) | **40 (51%)** |

Depth 1 is clean: the single reading of history the whole forecast rests on is genuinely the
model's, every recorded time. **Depth 2 is not**: on 51% of levels the beam's cut falls
*inside* a tie group (2–6 candidates wide), so `tot._rank`'s "prefer the lower combined
growth assumption" chooses which pairings reach the report. `los-angeles` is one of these —
`basebase` won outright at 0.96, and the other two rows came out of a four-way group at
0.85/0.85/0.80/0.80 the evaluator could not separate.

**And `tot.py`'s cut path calls that a score loss.** A candidate cut by the tie-break gets
`Scored 0.80, outside the top 3 at this level`, indistinguishable from one that was
outscored; only reservation-displacement gets its own wording. This is the *"pruning that
leaves no trace"* failure `tools/tot.py`'s own docstring says the ledger exists to prevent,
surviving one layer up — and it is the only one of the three findings that is an
**auditability** defect rather than a readability one.

#### Subsections, each its own commit

**U9.7Ta — rows named for what they say.** Row label becomes a deterministic 3×3 lookup on
`(rent_band, price_band)` — "Central case", "Prices fall, rents hold", "Rents stall, prices
hold" — and the cells carry the plain band words `_band_tables` already uses. No model call,
no new variance. Retires `_labels_for` and the combined-outcome naming convention; the
`Scenario.name` field keeps its shape, so nothing downstream changes.

**U9.7Tb — a "why this row is shown" column.** Carries the evaluator score and the actual
mechanism: won outright / neutral case, always shown / tied with N others, kept as the more
cautious. This pulls `forecast_branches_near_tied` down from a collapsed `<details>` sixty
lines above the table to the row it qualifies. Replaces the score parenthetical in the
bullets beneath.

**U9.7Tc — the ledger tells the truth about tie-break losses.** `tot.beam_search` gains a
third prune reason for a candidate inside the cut tie group, saying it tied and lost on the
conservatism preference rather than that it was outscored. **The one commit here that is not
presentation** — it changes `BranchLedgerEntry.prune_reason` text for ~51% of runs — and
where review should focus.

**U9.7Td — state band coverage.** When a band appears in no row, say so beneath the table.
Answers finding 2 without touching selection.

**U9.7Te — the tie-epsilon wording.** `forecast_branches_near_tied` currently prints
*"separated by 0.050, inside the 0.05 threshold"*, which contradicts itself: the real gap is
`0.04999999999999993` rendered at 3dp. Print "less than 0.05" and drop the figure.
**Wording only — the comparison is not touched** (see *Open* below).

**U9.7Tf — re-derive and check.** Replay the batch and both sample reports. **No re-record:
nothing above changes a prompt.** The check is that all 30 verdicts, confidences and
disclosure counts are unchanged while report *text* moves — any verdict movement is a defect
to chase, not a diff to accept.

**U9.7Tg — docs.** OQ-22 and `design/evaluator.md` gain the 51% measurement, and both lose a
premise that expired (below). `design/evaluator.md`'s Defect 2 entry records that U9.3's fix
was partial and what finished it.

#### A premise behind OQ-22's deferral expired on Sept 1, and both documents still assert it

OQ-22 and `design/evaluator.md` argue the pairing level must survive because the forecast's
search is *"the only reasoning locus in the build."* **That stopped being true when U9.4
landed `critic.cross_check`**, which the status table already calls the 2nd reasoning locus.
Deleting or re-pointing depth 2 no longer costs the system its only demonstration of
reasoning. This does not change what U9.7B builds; it changes the argument OQ-22 will be
decided on after the freeze, so it is recorded rather than acted on.

#### Blocking question — answer before U9.7Ta starts

**Row order, once the names no longer encode rank.** Combined-outcome ordering was
load-bearing while the labels were a ranking; with content names it is a free choice.
Neutral-first reads as "here is what we expect, and here are the two departures from it";
worst-to-best preserves today's ordering and the reader's habit. Not resolved — the
architect selected content-named rows without settling the sort.

#### Open, and deliberately not resolved here

**Whether `within 0.05` should mean `<=` inclusive.** The comparison is decided by floating
point at the boundary: of 2dp score pairs a nominal 0.05 apart, 26 land "tied" and 31 do not,
and both render as `0.050`. Making it inclusive would also widen `tot._rank`'s tie groups, so
it can change which pairings survive — **11 recorded depth-2 levels sit at that boundary and
would flip**, needing a re-record and a 30-row diff. **Architect's call Sept 2: not now.**
`config.py` already records that this epsilon is noise-dominated and "not meaningfully
straddleable" (OQ-17), which is the argument for not spending a re-record on it before the
freeze. U9.7Be fixes the sentence and leaves the semantics.

**Whether depth 2 should be re-pointed at all.** OQ-22's re-purposing — ask what this deal's
evidence supports showing rather than which pairing is most likely — is the right long answer
and stays deferred. One measurement taken Sept 2 that OQ-22 does not have: projecting from
the rent estimate's error band edges rather than its point estimate produces a spread
**2.04×** the growth bands' own width on `los-angeles` and **2.07×** on `staten-island`. The
re-purposed table would therefore be mostly an estimate-uncertainty display rather than a
growth forecast. That is arguably the honest answer — Staten Island's error band is ±32% of
its estimate against a 43% five-year band spread — but it changes what the section *is*, and
settling it is design work this unit does not have room for.

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
| ✅ | **U9.3** forecast: ZORI re-source, evaluator, two tables | Done Aug 31, 2026 — five commits; supersedes half of #16 |
| ✅ | **U9.4** report: axes, recommendation + cross-check, lede, template | Done Sept 1, 2026 — six commits; `critic.recommend` + `cross_check`, the 2nd reasoning locus, `overpriced` re-sited to Uptown 60640 |
| ✅ | **U9.5** pin the live tier; Staten Island | Done Sept 1, 2026 — five commits; all 28 rows + both sample reports replay from a clone, 0 verdicts moved, `sensitivity.md` byte-identical |
| ✅ | **U9.6** sixth deal + one shadow | Done Sept 1, 2026 — six commits; `chicago-uptown` + `los-angeles-current`, both `PREDICTED` and both held; 30 rows, 28 byte-identical |
| ✅ | **U9.7** Streamlit surface | Done Sept 1, 2026 — five commits; replay by default, a genuine review pause, and the three faults recorded. Cut-list item 4 **spent, not shed** |
| ⬜ | **U9.7B** scenario table: content-named rows, an honest ledger | Inserted above the line Sept 2 — presentation + disclosure only, search untouched |
| | *✂️ cut line* | |
| ⬜ | **U9.8** gross rent multiplier | First below the line if U9.1–U9.7 land early |
| ⬜ | **U9.9** capture: runs, traces, diagram, screenshots | Never sheds |
| ⬜ | **U9.10** OQ-5 / OQ-10 / OQ-14 written up | All three settled Aug 31 |
| ⬜ | **U9.M** maintenance | — |
| ⬜ | **U9.11** close-out | — |

**Twelve change sets against five days; the honest read is that seven land** — and U9.3
grew substantially on Aug 31, so that estimate is tighter than it was. The cut line is where
it falls.

**Where that estimate stands after U9.6, with three build days left.** Six have landed
(U9.1–U9.6) — **U9.7 is now the only item above the cut line remaining**, so the
seven-of-twelve prediction is on track to be met exactly. U9.9 sits below the line and
never sheds, so the realistic shape is now **U9.7 → U9.9 capture → U9.M → U9.11**, with U9.7
the one item genuinely at risk and its fallback already pre-agreed.

**One thing U9.5 changes about U9.7's risk, and it is a reduction.** The surface's stated
default — *"the demo deals run from committed recordings — instant, deterministic, no
quota"* — is now true rather than planned, and was not before this subsection: the demo
deals had no committed recordings at all, and the written summary's would have crashed the
node rather than degraded. The app is now a form plus `st.markdown(report)` over a path
proven to replay byte-identically.

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
