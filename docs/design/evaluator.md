# The forecast evaluator — what it scores, and why the output reads the way it does

**Written Aug 31, 2026, at U9.6.** Section numbers (§1–§9) and decision numbers (#1–#20)
refer to [`../implementation_plan.md`](../implementation_plan.md).

**This document exists because the architect read a report and did not believe it.** The
Los Angeles demo deal projects rent compounding **+7.26%/yr** while the price *falls*
**−0.80%/yr**, in two of three scenario rows, including the row labelled *Optimistic*. That
is counter-intuitive for US residential real estate and a demo audience will not accept it.

Investigating it found four defects and one **false premise**, and the false premise is the
one that matters: **the negative rent/price correlation the whole pairing design rests on
is a property of the HUD rent schedule, not of the housing market.** Measured against
market rent instead, the correlation is *positive*.

Everything below is reproducible with `scripts/growth_correlation.py`.

---

## 1. What the search actually does

Three steps, of which only the first two are a search. `agents/scenario_forecast.py` states
this plainly because `config.TOT_MAX_DEPTH = 3` invites the reader to assume three.

| Depth | What is enumerated | Beam | Prune |
| --- | --- | --- | --- |
| **1 — framings** | **4**: two rent treatments (screen the cohort shift or not) × two price treatments (exclude 2020–2022 or not) | `TOT_FRAMING_BEAM_WIDTH = 1` | `0.0` |
| **2 — pairings** | **9**: 3 rent bands × 3 price bands, under the surviving framing | `TOT_BEAM_WIDTH = 3` | `TOT_PRUNE_THRESHOLD = 0.40` |
| **3 — labels** | Nothing. Assigns optimistic/base/pessimistic **by projected outcome** and checks the survivors are distinct | — | — |

4 + 9 = the **13 hypotheses** a report's branch ledger states. Depth 3 is arithmetic;
inventing a scored level to fill the number would be the decoration §8 forbids.

### What depth 1 is actually choosing — the part that is easiest to misread

**The bands themselves are not chosen by the search.** `compute_growth_bands` is
arithmetic: hand it a series, get back the worst 12-month sustained stretch, the mean, and
the best. No judgment, no model call.

**Depth 1 chooses which version of history to compute those bands from.** The candidate id
encodes it — `f-{screen_rent}{exclude_price}`, built in `_framings`:

| id | Rent treatment | Price treatment |
| --- | --- | --- |
| `f-00` | keep every fiscal year | 2020–2022 **included** |
| **`f-01`** | keep every fiscal year | 2020–2022 **excluded** |
| `f-10` | screen out HUD's cohort-shift years | 2020–2022 included |
| `f-11` | screen out cohort-shift years | 2020–2022 excluded |

The Los Angeles run chose **`f-01`**. `TOT_FRAMING_BEAM_WIDTH = 1`, so exactly one survives
and the other three are pruned.

**These are real analyst judgments, and they are the most defensible reasoning in the
system:**

- *Should the 2020–22 price surge count as a condition that could recur, or a rate-driven
  one-off?*
- *Should HUD's national step-ups count as market moves, or as administrative artifacts?*

Reasonable people differ on both, the answer changes every number downstream, and the
evaluator scores each reading against evidence. **That is what this search is for.**

**A consequence worth stating, because it decides how the report should be laid out:** since
depth 1 determines the band values, it determines the numbers in a *decoupled* rent table
and price table on its own. Presenting rent and price separately therefore does not strand
the search — it **relocates which level the reader sees**, from the weakly-grounded pairing
to the well-grounded framing.

**Depth 2 is the designed reasoning core, by explicit intent.** From the agent's own design
docstring: *"the obvious three — optimistic with optimistic, and so on down the diagonal —
are the ones this project's own measurement argues against, because rent and price growth
move opposite each other here. A linear chain emits the diagonal without noticing."*

So the pairing level exists **specifically** to avoid the naive diagonal, and the thing
that justifies it is #16's negative correlation. **Section 3 shows that justification does
not hold.**

---

## 2. The four defects, as observed on the Los Angeles run

### Defect 1 — the neutral scenario is pruned *for being neutral*

The full depth-2 scoring:

| Pairing | Score | Fate |
| --- | --- | --- |
| rent **pessimistic** + price **optimistic** | 0.85 | reported as "Pessimistic" |
| rent **optimistic** + price **pessimistic** | 0.85 | reported as "Optimistic" |
| rent **base** + price **pessimistic** | 0.80 | reported as "Base" |
| **rent base + price base** | **0.70** | **pruned — "outside the top 3"** |
| rent base + price optimistic | 0.65 | pruned |
| rent optimistic + price base | 0.60 | pruned |
| rent pessimistic + price base | 0.55 | pruned |
| both pessimistic | 0.25 | below the 0.40 threshold |
| both optimistic | 0.20 | below the 0.40 threshold |

Base/base cleared the prune threshold and **lost on rank**: `TOT_BEAM_WIDTH` is 3 and it
came fourth. Nothing reserves a slot for the neutral case and nothing ever did — the beam is
a pure top-*k*.

**The evaluator's stated reason is the defect.** Its rationale for base/base was *"a neutral
scenario with **limited evidence of extremity**."* That is the evaluator misreading its own
task: **a base case does not need evidence of extremity — it is the default the other two
are departures from.** It was asked *"how well is this hypothesis supported by the
evidence?"*, and under a prompt whose evidence includes "rent and price move opposite," an
anti-correlated pairing reads as better supported than a neutral one.

**Consequence:** the row labelled **"Base" is base-rent paired with pessimistic-price**, and
the true base/base case appears **nowhere in the report**. A reader asking *"what do you
actually expect?"* has no row to look at. This is the direct cause of the depreciation
confusion.

### Defect 2 — the labels do not describe the data under them

Depth 3 assigns optimistic/base/pessimistic **by projected combined outcome**, from
whichever pairings survived. **Nothing in the logic guarantees all three bands of either
series appear**, and on the LA run the price base band (+2.10%) appears in no row at all.

So "Optimistic" can carry — and here does carry — the *pessimistic* price band. The report
explains this honestly in a paragraph. Explaining a confusing thing clearly does not make it
less confusing.

### Defect 3 — the two series' bands are not built comparably

| | Rent (HUD FMR, LA county, 2br) | Price (Redfin MF 2–4, LA metro) |
| --- | --- | --- |
| Pessimistic | −0.68% — worst **single fiscal year** | −0.80% — worst **rolling 12-month stretch** |
| Base | +7.26% — geometric mean of 9 retained years | +2.10% — arithmetic mean of 52 monthly prints |
| Optimistic | +14.49% — best **single fiscal year** | +4.50% — best **rolling 12-month stretch** |
| Excluded | cohort-shift years (none fired for LA) | **2020–2022** |
| **Width** | **15.2 points** | **5.3 points** |

Single-year extremes against 12-month smoothed stretches makes the rent band roughly **3×
wider as an artifact of method**, not of market. Every pairing inherits it, which is why rent
appears to outrun price under every combination the search can produce.

The exclusion windows also differ — cohort-shift fiscal years on one side, the 2020–2022
rate window on the other — so the two bands do not even describe the same span.

### Defect 4 — an annual correlation is applied to a five-year compounded projection

Even taking the correlation at face value, it is measured on **year-over-year** changes. A
weak annual tendency to move in opposite directions does not imply the two series diverge
**monotonically for five consecutive years**, which is what compounding an anti-correlated
pair asserts. Over the LA horizon that turns a modest statistical lean into ×1.42 rent
against ×0.96 price.

---

## 3. The false premise — and this is the important part

#16 records: *"pooled r = −0.309 across 24 metro-years, negative in all three metros
independently."* That measurement was taken **before U6 was built** and **was never
committed as a script**. `scripts/growth_correlation.py` now re-derives it, and adds the
control that was never run.

### It reproduces, and then it falls apart

| Pass | Rent series | Pooled | Chicago | Los Angeles | Cleveland | New York |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | HUD FMR | **−0.317** (r² 0.100) | −0.200 | −0.337 | −0.654 | **+0.120** |
| **2** | HUD FMR, FY2023–24 removed | **−0.197** (r² 0.039) | **+0.229** | −0.228 | −0.360 | **+0.390** |
| **3** | **Zillow ZORI (market rent)** | **+0.222** (r² 0.049) | −0.537 | **+0.233** | **+0.715** | −0.089 |

**Three findings, each stronger than the last.**

**(a) The headline survives; the "all metros" claim does not.** Pooled r = −0.317 against
#16's −0.309 — the premise reproduces, which is worth stating plainly because it is the
first assumption in this project to be re-checked and *hold*. But #16's *"negative in all
three metros independently"* was true of the inference trio and **New York, added at U8.4c,
is positive (+0.120)**. The claim as written is false for the current market set — and
New York is where the `staten-island` demo deal lives.

**(b) Roughly 40% of the negative signal is two administrative years.** Removing FY2023–24 —
the panel-wide HUD steps that this project's *own* cohort screen exists to identify as
non-market — collapses the pooled correlation from −0.317 to **−0.197, r² = 0.039**. Chicago
and New York both flip positive.

**(c) Measured against market rent, the correlation is positive.** Same price series, same
years, same metros, only the rent measurement differs: **ZORI gives pooled r = +0.222.**
Cleveland flips from −0.654 to **+0.715**. The sign is not a property of the market; it is a
property of *which rent series you ask*.

### What that means for the pairing design

`agents/scenario_forecast.py` prefers anti-correlated pairings because rent and price
*"move opposite each other here."* **They do not.** That statement is true of the HUD Fair
Market Rent schedule against Redfin prices, and false of market rent against the same
prices — and the estimate this system publishes has been anchored to **market rent since
#19**.

**This is the same defect as §6 cut-list item 6, in a second location.** U8.0 measured FMR
rising +51.9% against market rent's +33.5% since the corpus vintage. #19 acted on that and
re-anchored the rent *estimate*. **#16's correlation was measured on FMR and never
re-measured**, so the forecast's pairing logic still runs on the property that finding
retired. A premise corrected in one place and left standing in another — the fifth instance
of this pattern in the project, and the one with the widest blast radius, because it decides
the shape of every forecast the system publishes.

**The rent-growth *source* is the same story.** #16 chose HUD FMR history for rent growth
and the forecast still uses it, so a rent projection of +7.26%/yr is on a schedule measured
at ~6.2%/yr against market rent's ~4.2%/yr. Re-sourcing it is **#16 reopened** — a unit, not
a subsection — and ships as a disclosed gap.

---

## 4. What U9.6 changes, and what it does not

**Not taken: splitting rent and price into separate forecasts.** It was considered. Doing so
would delete depth 2 entirely — there would be nothing left to pair — collapsing the search
to four framings at beam width 1 and reducing "13 hypotheses evaluated" to four. That is a
real loss of the reasoning level U6 was built to demonstrate, and it would strand U8.6c's
cut-margin measurement.

**Taken instead: decouple the search from the presentation, and fix the premise at its
source.** The search keeps all 9 pairings and the full ledger. The *report* leads with rent
and price as two separate three-row tables — which is also how #16 forecasts them — and
carries the combined scenarios as a secondary view.

**In separate tables the labels become true again**, which is defect 2's real fix: each
series shows its own pessimistic / base / optimistic, so the label names the band rather
than a combined outcome that may contain neither extreme.

### Rent growth moves from HUD FMR to Zillow ZORI

**#16's own architectural argument selects ZORI once you apply it to today's system.** It
chose FMR because *"the rent estimate is `ratio × FMR`, so projecting the anchor forward
while holding the structural ratio constant forecasts rent by the same mechanism that
produced the estimate."* Since **#19** the estimate is `ratio × ZORI(ZIP) ×
FMR-bedroom-step` — so projecting the anchor forward now means projecting **ZORI**. This
follows #16's reasoning to where the system moved rather than overturning it.

Measured with both series windowed to 2018+, one estimator, 2020–22 excluded on both:

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

LA's FMR bands today are **−0.68 / +7.26 / +14.49, width 15.2pp** — four times wider, base
case three times higher. Rent +2.65% against price +2.10% is a coherent picture; rent
+7.26% against price −0.80% is the one nobody believed.

**Two windowing decisions, both found by measurement and both explicit rather than
default:**

- **Window ZORI to 2018+ to match Redfin's span.** Unwindowed, New York's pessimistic rent
  band is **−22.6%** — a real Bronx figure from a 12-month stretch ending **2017-05**,
  before the price series begins. Mismatched spans put a pre-window artifact in a report.
- **Apply the 2020–22 exclusion to the rent side too.** Only price has it today.

**FMR history stays as the documented fallback** where ZORI has no county — the same shape
as #19's hybrid.

**Three defects close on this one change**: the false premise, the ~2pp/yr growth
overstatement U8.0 measured, and the estimator asymmetry — the last because both series
become monthly and one band function serves both. **The cohort-shift screen retires with
it**, since it exists only to paper over HUD's administrative step-ups, and the depth-1 rent
fork becomes *include or exclude 2020–22* — the same question already asked of price.

### The change list

| | Change | Defect |
| --- | --- | --- |
| 1 | Re-source rent growth from FMR to ZORI, FMR as fallback | premise, 3 |
| 2 | Window both series to 2018+; exclude 2020–22 on both | 3 |
| 3 | Report rent and price bands as two primary tables | 2 |
| 4 | Reserve a beam slot for base/base | 1 |
| 5 | Correct the evaluator's evidence and its reading of its own task | 1, 4 |
| 6 | Render depth 1 and depth 2 separately, and show the winner's score | — |
| 7 | One sentence telling the reader nine pairings existed | 2 |

**Change 5 is the one to review hardest.** It is a prompt change that alters what every
forecast is scored against, and its justification is entirely in section 3 above. It lands
as its own commit for that reason.

### Making the reasoning visible

The material already exists and is presented badly. Every framing carries a score and a
written rationale — `f-11 (0.80) "…relies on a smaller rent sample, making it less robust
than f-01"` — but the report flattens depth 1 and depth 2 into one list of 13 headed *"What
the forecast search considered"*, and **renders only pruned branches, so the winning
framing's score never appears at all.** A reader sees three losers and never learns what
beat them.

```
Step 1 — Which reading of the history?        4 considered, 1 chosen
  f-01  0.85  Keep every rent year; exclude the 2020-22 price surge   ← chosen
  f-11  0.80  ...also screen the step-up years
  f-00  0.30  Include everything
  f-10  0.20  Screen rent years; include the price surge
Step 2 — Which band combinations to report?   9 considered, 3 kept
```

This is the moment the system visibly *reasons* rather than computes, and it is the clearest
thing in the build to put on screen during a demo.

**It must also say the reasoning is a sample.** OQ-17 measured this model's scores swinging
widely on identical prompts at temperature 0. The **bands are deterministic**, so no number
a reader takes away moves between runs — only the commentary on them does, and the panel
should say so rather than presenting a single draw as a stable ranking.

### What depth 2 becomes, and why not yet

**#21 fixed a false premise and, in doing so, hollowed out the level that premise
justified.** Before it, depth 2 had a clear — if wrong — decision criterion: *prefer
anti-correlated pairings.* After it, there is no directional prior at all, and nine
candidates are scored on flags, band widths and sample sizes. That is honest and it is thin.

**Decided Aug 31, 2026: depth 2 ships as-is with the corrected instructions, and the
re-purposing below is adopted as the answer, deferred on schedule.** With r² between 0.04
and 0.10 across every pass, this panel supports no confident directional rule, and the final
report should describe the level that way rather than as settled reasoning.

**The adopted redesign: stop asking which pairing is most likely — that needs a joint
distribution this data cannot supply — and ask which projections this deal's evidence
supports showing.** The bands describe what the *market* did; the deal's evidence describes
how far to trust the *estimate the projection compounds from*, and depth 2 ignores the
second entirely:

| | `los-angeles` | `staten-island` |
| --- | --- | --- |
| Rent estimate | $2,861 **±$509** | $2,654 **±$855** |
| Comps | 8, all ZIP-anchored | **0** |
| Comp cross-check | implies $2,875 — **1% away** | **not run** |
| Anchor | ZIP 90026 | **county-wide** |

Both get the same three bands today and both are projected five years forward with equal
apparent confidence. Re-purposed, `los-angeles` projects from the point estimate because
eight comparables corroborate it within 1%, and `staten-island` projects from its error
band's edges — or declines the optimistic case — because nothing checks it. **Deal-specific,
grounded in evidence already in the prompt, and needing no correlation at all**, which is
what makes it survive #21.

Deferred because it is a full change set of new design: the prompt's question changes, the
candidate payload gains a starting-point treatment beside `(rent_band, price_band)`,
`_pairings` and the scenario assembly change shape, `Scenario`/`ForecastDetail` gain a
field, and everything re-records. Tracked as **OQ-22**.

### The wider question this belongs to

Only two agents in this system call a model, and #12's Critic half was retired on evidence
at U7.7 — so this search is the **only reasoning locus in the build**, one 4→1 selection and
one 9→3 selection. U9.4 adds a second at the recommendation (model proposes, rule decides,
disagreement disclosed). The strongest remaining candidate is **retrieval relaxation**, where
`maintenance.md` M6 records that the fixed ladder's stated rationale is contradicted by the
rent model's own feature importances.
