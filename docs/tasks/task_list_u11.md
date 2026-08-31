# U11 — Rent model v2 — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#20) refer to
> [`../implementation_plan.md`](../implementation_plan.md).

**Created Aug 29, 2026, by the architect's direction during U8.6.** Model quality had no
concrete home in the plan — it existed only as OQ-4 / §6 cut-list 1a ("closes only if
schedule allows") and cut-list 6 (re-anchor on ZORI). The architect's call: *"if the
model is not good it undermines confidence in the forecasting part of the system"* — so
the work becomes a unit, sequenced **after U8.4b/U8.4c land and before U8.6's numbers
close**, because tuning confidence against estimates a model change then invalidates is
the mistake U8.4b's original sequencing note existed to prevent.

**Why U11 and not U10:** U10's scope was absorbed into U8.9 (Aug 26, 2026); reusing the
number would collide with every historical reference to that absorption.

**The prior evidence this unit starts from** (`config.py`'s cut-list note, measured
before U8):

| | |
| --- | --- |
| Shipped model | vanilla `LinearRegression` on 3 raw features |
| Underfit, not overfit | train-vs-holdout gap $0.04 |
| Random forest, same data/features | **$434 MAE vs $524 — ~17% of error is model form alone** |
| Polynomial-3, same probe | R² −13.3 — catastrophic, not a candidate |
| Per-metro (U8.4) | trio ≤1.1x overall MAE; New York 2.00x |

**The structure is a ladder: each rung is gated on the previous rung's measurement, and
adoption decisions are the architect's, made on the numbers.** Batch re-derivation and
U8.6's close live in U8's sequence, not here — this unit produces a model and its
evidence.

## Unit-level open questions

### Q1 — Is ZORI re-anchoring (rung 3) in scope for this pass?

The architect leans toward it but ruled (Aug 29, 2026) that the decision **waits for
rungs 1–2's output**, per the project's evidence-first principle. What is known going in:
U8.0 measured ZORI covering 5,662 of 5,686 corpus ZIPs with better geographic
normalization than FMR (per-city ratio spread 0.172 vs 0.257) — and the cost: a target
redefinition (a U5-scale rewrite) plus ~27% of training rows (the county-anchored rows
have no ZORI denominator). Rungs 1–2 decide whether cheaper levers close enough of the
gap first.

## Subsections

### U11.1 ✅ — Model-form probe *(approved Aug 29, 2026; runs first)*

`scripts/model_form_probe.py`: LinearRegression vs RandomForest vs GradientBoosting on
the identical feature set and identical FMR-ratio target, under **k-fold cross-validation**
— which satisfies OQ-4's own condition that proper validation replace the single split —
reporting per candidate:

- overall CV MAE (mean ± spread across folds),
- **per-metro MAE and the New York ratio** (via the U8.4 `INDEXED_MARKETS` grouping —
  the flag instrument, so the probe answers whether form changes what the system
  *discloses*, not only what it scores),
- **per-subject estimate deltas for the demo/eval fixtures**, against the flag
  boundaries each deal sits near (`RENT_COMP_DIVERGENCE_THRESHOLD_PCT`, the
  `RENT_MODEL_MIN/MAX_RATIO` refusal band).

**Triage rule, fixed in advance per Q1-of-U8's precedent:** if the New York ratio stays
≥ 1.5 under every candidate *and* no fixture's delta crosses a flag boundary, model form
changes only the headline number — adoption is a live decision on accuracy grounds
alone. If either condition breaks, the probe has found that form changes system
*behavior*, and the adoption decision carries that evidence.

---

**Built Aug 30, 2026** — `scripts/model_form_probe.py`, 5-fold CV over the 5,686-row
frame, no model calls, nothing written to disk. **Condition A holds and condition B
breaks, so the triage rule returns the second branch: model form changes what the system
discloses, not only what it scores.**

**1. Accuracy.** Cross-validated, so this is the like-for-like comparison; the shipped
artifact's $524.03 came from a single 20% split and is reference, not baseline.

| Candidate | CV MAE $ | fold sd | MAE ratio | R² | train MAE $ | **train/holdout gap** |
| --- | --- | --- | --- | --- | --- | --- |
| LinearRegression | 513.67 | 13.51 | 0.4000 | 0.263 | 513.35 | **0.32** |
| RandomForest | **428.83** | 8.55 | 0.3160 | 0.454 | 288.42 | **140.41** |
| GradientBoosting | 450.71 | 7.29 | 0.3472 | 0.427 | 432.37 | **18.34** |

**The 17% figure survives proper validation** — RandomForest is 16.5% better than the
shipped form under CV, against the 17% the single-split probe measured. That was the open
question about the number and it is now closed.

**The gap column is the finding the headline hides, and it is why the probe reports it.**
`config.py`'s deferral named added capacity's overfitting risk as one of its two reasons.
RandomForest's held-out win is real, and it is bought with a $140 train-vs-holdout gap
against the shipped model's $0.32 — it memorizes heavily. GradientBoosting takes 12.2% of
the error for a $18 gap. **On variance, GBM is the better-behaved candidate; on error, RF
wins.** That trade is the architect's call and the probe does not make it.

**2. Per-metro, and the New York ratio.** Pooled out-of-fold, so every row is scored once
by a model that never saw it — which is what makes New York's n=264 slice readable at all.

| Candidate | Chicago | Los Angeles | Cleveland | **New York** |
| --- | --- | --- | --- | --- |
| LinearRegression | 483 (0.94x) | 512 (1.00x) | 455 (0.89x) | 1,050 (**2.04x**) |
| RandomForest | 454 (1.06x) | 480 (1.12x) | 222 (0.52x) | 986 (**2.30x**) |
| GradientBoosting | 454 (1.01x) | 450 (1.00x) | 366 (0.81x) | 982 (**2.18x**) |

**Condition A holds: New York stays above 1.5x under every candidate.** But the direction
is worth stating because it is counter-intuitive and it reaches the reader: both trees
improve New York *absolutely* ($1,050 → $986 / $982) and make it *relatively worse*,
because the overall figure improves faster than New York does. `RENT_ESTIMATE_MARKET_ERROR_ELEVATED`'s
message quotes that multiple, so adopting a tree makes every New York report say the
estimate is 2.2–2.3x the headline error rather than 2.0x. No model form on the table
retires this disclosure; the model is not the reason New York is hard.

**3. Per-fixture behavior — condition B breaks, on two fixtures, and both are load-bearing
cases rather than incidental ones.**

- **`la-oversized-loft` stops being refused.** LinearRegression predicts a ratio outside
  `RENT_MODEL_MIN/MAX_RATIO` and the agent refuses the estimate — which is the entire
  point of the fixture. RandomForest predicts 3.00 and GradientBoosting 2.20, both inside
  the band, so both **produce an estimate instead**, and the flag set swaps
  `rent_estimate_unavailable` (critical) for `rent_anchored_to_market_index` +
  `rent_diverges_from_comps` + `rent_drift_correction_applied`. It is the **only case that
  targets** `RENT_ESTIMATE_UNAVAILABLE`. Whether the census still covers that kind through
  another case's cascade (the `extraction_unavailable` row raises four criticals) is a
  batch question this probe does not answer and **U11.4's re-derivation must check**.
- **`chicago-uptown-duplex` stops diverging under RandomForest** — +46.6% → +26.2%,
  inside the ±30% line, so `rent_diverges_from_comps` does not fire. This is the case
  U8.2 built to close OQ-12's second half, on the strength that *nothing about the
  property is engineered*. GradientBoosting keeps it at +33.2% — 3.2 points of margin,
  which is thin. The **kind** stays covered either way (three other fixtures still
  diverge: −36.1% LA, +75.4% Chicago oversized, −48.1% Cleveland), so this is a loss of
  the specific case's argument rather than of coverage.

**Estimates move by more than the accuracy table suggests, and not in one direction.**
Ordinary 2bd/950sqft subjects come down under RF (−$386 LA, −$404 Chicago); the
five-bedroom goes *up* $1,086. `chicago-uptown-oversized` moves −$1,151 under RF and
+$498 under GBM — **the two trees disagree by $1,650 on the same subject**, which is a
sharper statement about extrapolation beyond the corpus's ordinary footprint than either
one's MAE is.

**What this hands the architect.** Adoption is not the accuracy-only decision the triage
rule's first branch would have made it. Any adoption re-records the batch (the scoring
prompt embeds the rent estimate), invalidates two engineered cases' arguments, and moves
New York's disclosed multiple. Reproduce with
`.venv/bin/python scripts/model_form_probe.py`; `--no-fixtures` runs reports 1–2 alone.

### U11.2 ✂️ — Feature measurement — **CUT Aug 30, 2026 to §6 cut-list 1a**

**Never run.** The architect cut it, with U11.4's tuning and LOMO, once the anchor lever
landed. Reasoning in [`../implementation_plan.md`](../implementation_plan.md) §6 item 1a;
the short form is that the anchor was the lever with a measured defect behind it, and
these are refinements to a model that is now cross-validated, per-metro reported, and
honest in the report about its worst market. Scope kept below so the item is re-openable
as written rather than re-derived.

CV-ablation pricing of corpus columns the model does not use: amenity/pet fields,
listing month (seasonality), sqft-per-bedroom, bath:bed ratio — each reported as
incremental MAE against the U11.1 winner. **Standing constraint:** features stay
structural; no market identifier. The FMR-ratio target exists to keep the model
market-free (§2), and a metro dummy would reintroduce exactly the dollar-level
memorization the ratio removes.

### U11.3 ✅ — The anchor (gated on Q1, decided on U11.1–2's numbers)

If taken: re-anchor the target on ZORI (cut-list 6) — the largest lever and the largest
cost. If not taken: record the decision and its evidence in the §7 register, and the
U8.4b drift correction remains the vintage-drift instrument.

---

**Measured Aug 30, 2026 — `scripts/anchor_probe.py`, five candidates, one CV, gradient
boosting, scored in dollars on the 5,671 rows all five can price.** The decision is the
architect's; this is the evidence for it.

| Anchor | MAE $ | Chicago | Los Angeles | Cleveland | New York |
| --- | --- | --- | --- | --- | --- |
| `fmr` — status quo | 453.10 | 458 | **451** | 372 | 995 |
| `zori` — zip→county | 443.78 | **322** | 494 | 361 | **751** |
| `hyb` — ZORI × FMR bedroom shape | **439.03** | 337 | 484 | **356** | 812 |
| `fmr+` — FMR, ZORI where absent | 453.10 | 458 | 451 | 372 | 995 |
| `fmr/z` — FMR where ZIP, ZORI where county | 484.17 | 444 | 550 | 361 | 772 |

**Three findings, and one of them kills an idea this file proposed.**

**1. `fmr/z` is the worst candidate on the table — worse than doing nothing.** The
proposal was to swap ZORI into exactly the three markets where FMR is county-grain and
leave Chicago's ZIP-level schedule alone, which targets the defect precisely and looked
like the cheap win. It measures **$484 against the status quo's $453**, and it is worse
even in the markets it was supposed to help (Los Angeles 550 against `fmr`'s 451 *and*
`zori`'s 494). The stated risk was that it puts a third denominator in one training set;
that cost is real and it exceeds the grain it buys. **Measured and rejected**, which is
the outcome the probe existed to make possible.

**2. `fmr+` is identical to `fmr`, by construction rather than by coincidence.** No row is
dropped for a missing FMR, so the ZORI fallback never fires — a coverage lever with
nothing to cover on the training side. It would still let a New England subject be priced
at inference, but that is OQ-8's problem and not the anchor's.

**3. The gain is real but small overall, and large in exactly the market that needs it.**
`hyb` takes 3.1% off the headline. Underneath that: **New York −18% (995 → 812) and
Chicago −26% (458 → 337)**, against **Los Angeles +7% worse (451 → 484)**. Los Angeles is
41% of the frame, so it drags an overall figure that understates what happens in the two
markets where the current anchor is weakest. Pure `zori` is stronger still in those two
(New York −25%, Chicago −30%) and weaker in Los Angeles.

**Chicago is the result that changes the reasoning.** It is the one market already 100%
ZIP-anchored under FMR, so grain cannot explain a 26–30% improvement there. ZORI is
simply a better reference series than the administrative schedule, independent of
resolution — which is a broader claim than cut-list item 6 makes and a stronger argument
for taking it.

**A hypothesis tested and not supported, recorded so it is not re-run.** Los Angeles is
the market ZORI makes worse and also the one where the county fallback carries the most
weight (14% of its rows, against a county spanning Malibu to Compton), so the fallback
looked like the culprit. Split by tier, it is not: within Los Angeles the county tier
scores **468** against the ZIP tier's **487**. The county fallback is sound and Los
Angeles genuinely prices better against FMR. (The headline split — county $337.53 against
ZIP $462.94 — is confounded by metro mix and should not be read as the county tier being
better in general.)

---

**TAKEN Aug 30, 2026: the hybrid. Built the same day.** The architect's reasoning was
breadth over depth — the bedroom dimension is worth keeping and the numbers beat the
status quo nearly everywhere.

**Retrained on the new target:** CV MAE $452.40 (against the FMR-anchored GBM's $450.71 —
flat overall), train/holdout gap $21.45, and the per-metro story the overall figure hides:
**New York $981 → $855, Chicago $454 → $343**, Cleveland $366 → $357, Los Angeles
$450 → $509. New York's ratio to the headline falls from 2.18x to **1.89x**, so
`RENT_ESTIMATE_MARKET_ERROR_ELEVATED` still fires and still should.

**Los Angeles gains ZIP-grain anchoring it never had.** Verified live on 90026: the anchor
resolves at ZIP tier ($2,691), the estimate is $2,861/mo at a ratio of 1.063, and 8 of 8
comps normalize to a median of $3,081 for a −7.1% divergence. Under FMR every Los Angeles
subject was county-anchored and carried `RENT_ANCHOR_COUNTY_LEVEL` unconditionally; it no
longer does, which is a real disclosure change and will move confidence scores.

**The drift correction retired structurally rather than by deletion**, as U11.3's plan
said it would: the anchor reads a market index at the same month on both ends, so the
schedule-versus-market gap U8.4b measured is divided out where it arises. The flag it
raised is repurposed as an index-staleness disclosure.

**Landed incomplete on purpose, and here is exactly what was left** (per §8, the completing
work is named rather than implied). **All five closed Aug 30, 2026** — the names below are
written as they stood *before* the rename, since a later sed pass over this file
retroactively replaced them and made the list contradict itself.

1. ✅ **`FlagKind` members still carried FMR names** — `RENT_ANCHORED_TO_FMR`,
   `FMR_ANCHOR_COUNTY_LEVEL`, `FMR_UNAVAILABLE_FOR_COUNTY`. Their *messages* were correct
   and reader-facing text was honest; the enum member names and `ValuationDetail.fmr_*`
   fields were not. Renamed to `RENT_ANCHORED_TO_MARKET_INDEX`, `RENT_ANCHOR_COUNTY_LEVEL`
   and `RENT_ANCHOR_UNAVAILABLE`, with `fmr_resolution`/`fmr_zip`/`fmr_year` →
   `anchor_tier`/`anchor_zip`/`fmr_shape_year`. **`FMR_BEDROOM_CAP_EXCEEDED` deliberately
   kept its name**: the four-bedroom ceiling really is a property of the federal schedule,
   which the hybrid still reads. It changed `f.kind.value`, so it rode the re-record.
2. ✅ **`agents/summarizer.py` rendered the anchor as an FMR figure.** The basis line said
   `ratio 1.06 x FY2026 FMR $2,691 (ZIP 90026)`; it now says `x market rent $2,691 (ZIP
   90026, as of 2026-07-31)`. The *other* FMR sentence in that file was left alone and is
   still correct — the forecast's rent-growth bands do come from FMR history (#16).
3. ✅ **`tools/rent_drift.py` was unused** and is deleted, with `tests/test_rent_drift.py`
   and the `config.RENT_DRIFT_*` block. `RENT_DRIFT_CORRECTION_APPLIED` was **retired** on
   the `LLM_RENT_FALLBACK_USED` precedent (a kind nothing can raise corrupts the census);
   `RENT_DRIFT_CORRECTION_UNAVAILABLE` was **repurposed** as `RENT_ANCHOR_INDEX_STALE`.
   Taken as a decision rather than a side effect, as this item asked.
4. ✅ **`scripts/anchor_probe.py` and `scripts/zori_evidence.py` read the old frame shape**
   (`fmr`, `fmr_resolution`, `rent_to_fmr`) and would not run. Both repaired, along with
   `scripts/metro_shortlist_ablation.py` and `scripts/valuation_evidence.py` — the last of
   which was worse than stale, since it had begun comparing the metro population on the FMR
   anchor against comps on the hybrid one and printing the two as "normalized identically".
   The retired FMR anchor now lives in one place, `rent_model.fmr_baseline`, rather than
   being re-derived in three scripts.
5. ✅ **Re-record and batch re-derivation** taken once, after items 1–3, in U8's sequence.
   Result: 28 cases, no errors, 18/21 predicted-verdict agreement, 30 of 30 flag kinds.

**What this leaves the architect.** `hyb` is the best overall, is the architect's stated
preference, and has an architectural advantage the table does not show: **it keeps FMR in
the system**, so `FMR_BEDROOM_CAP_EXCEEDED`, `RENT_ANCHOR_COUNTY_LEVEL` and the rest of the
anchor vocabulary keep meaning what they mean, where pure `zori` would retire them. Against
that, `zori` is materially better in the two markets whose disclosures this unit exists to
improve. Neither is free: both are the U5-scale rewrite, and both largely retire U8.4b's
drift correction, which is what cut-list item 6 says the correction stands in for.

### U11.4 ✅ — Adoption, tuning, and validation artifacts

**Partially landed Aug 30, 2026, ahead of its place in the sequence** — the architect took
gradient boosting on U11.1's numbers, and the adoption was folded in with the probe work
rather than held for a separate review pass. What landed: `config.RENT_MODEL_ESTIMATOR`
and `RENT_MODEL_CV_FOLDS`, `rent_model._estimator`, `train()` rewritten to k-fold CV plus a
full-data refit, `TrainingReport` carrying `cv_folds` / `train_mae_dollars` /
`feature_importances`, and the input-domain guard that replaces the refusal mechanism the
form change would otherwise have retired silently (see U11.1 above).

Retrained and persisted: **CV MAE $450.71**, R² 0.427, train/holdout gap $18.34, per-metro
Chicago $453.67 / Los Angeles $449.75 / Cleveland $366.36 / **New York $981.51 (2.18x)**.
Feature importances square_feet 0.43, bedrooms 0.32, bathrooms 0.25 — the negative-bedrooms
artifact is gone with the linear form. All 72 tests pass.

**Closed Aug 30, 2026. What was outstanding here is now either done or cut**, and the
split is deliberate:

- **Done:** the adoption itself, the retrain-and-persist with the per-metro breakdown
  travelling on the artifact, and by-metro reporting as the standard for every future
  retrain.
- **Handed off, not cut:** the re-record and the batch re-derivation, which live in U8's
  sequence and are the gate on U8.6's close. **The re-record was deliberately not taken
  in this unit**, since the anchor decision would have moved every rent estimate again
  and the recordings should be cut once for both changes — the same reasoning U8's
  sequence item 3 used for U8.4b+U8.4c.
- **CUT to §6 cut-list 1a:** hyperparameter tuning under the same CV (the form ships at
  library defaults, deliberately — see `config.RENT_MODEL_ESTIMATOR`), and the
  leave-one-metro-out run as transfer evidence.

**LOMO is the one worth naming as a limitation rather than only as a cut.** OQ-12's first
half asks whether the model transports to a market it never trained on, and a k-fold
holdout structurally cannot answer it — every fold still contains all four markets. The
report should say that the transfer question is open rather than let the cross-validated
MAE imply it was settled. OQ-12 stays open in
[`../open_questions.md`](../open_questions.md) for exactly that reason.

### U11.5 🟨 — The FMR vocabulary the rename pass did not reach *(items 1 and 6 done; 2–5 close with U8's documentation close-out)*

**Opened Aug 30, 2026 by the architect**, after an audit of this unit against the code
found that U11.3's item-1 rename covered the `FlagKind` members, the `ValuationDetail`
fields and the Summarizer's basis line — and stopped there. The rent model's own prose
and identifiers still describe the anchor the unit retired. **Sequenced deliberately with
U8.10 rather than now**: it is documentation and naming, one item excepted, and batching
it with the other doc close-out is one review pass instead of two.

**None of this changes a number.** The estimates, the anchor and every measured figure in
this unit are correct as they stand; what is wrong is what the code *says* about them.

| | Site | What is wrong |
| --- | --- | --- |
| **1** ✅ | `agents/summarizer._rent_basis_section` | **Done Aug 30, 2026, pulled ahead of U8.10 at the architect's direction.** It was *two* false claims rather than one: *"A linear regression on bedrooms, bathrooms and square footage"* (gradient boosting since #18) and *"On a held-out slice"* (the single 20% split #18 replaced with cross-validation plus a full-data refit). The second understated the evidence — every row is now scored once by a fold that never saw it, and the per-metro n is the market's full row count rather than a fifth of it, so "n=2,372 listings" replaces "n=2,372 held-out listings". Verified in a live report; no re-record, since the model description reaches no prompt |
| **2** | `TrainingReport.mae_dollars_at_holdout_fmr` | The name says FMR; the quantity is dollars at the hybrid anchor. **The one item that is not purely cosmetic:** the field is serialized into the persisted bundle and `valuation_rent._attach_model_provenance` reads it by string key, so a rename needs a retrain or a both-keys read. Name it in the change set rather than discovering it mid-rename |
| **3** | `rent_model.predict_ratio` | Docstring: "Predict rent-to-FMR ratio for one subject" |
| **4** | `rent_model.build_training_frame` | Docstring: "Assemble the FMR-normalized training set from the Kaggle corpus" |
| **5** | `rent_model.train` | Comment at the CV block: "Dollar error is the ratio error re-expressed at each row's own FMR" |
| **6** ✅ | [`../open_questions.md`](../open_questions.md) OQ-4 | **Done Aug 30, 2026**, with U8's close-out. Retargeted rather than closed: the model-form half closes as #18, tuning / LOMO / feature engineering stay deferred, both dead citations replaced, and the original wording is kept above the change so the retarget is legible. *What was wrong:* stale on both halves: it reads "Deferred deliberately… **closes only if** schedule allows and proper validation replaces the single split", and U11.1 ran 5-fold CV while U11.4 adopted gradient boosting — its own stated closing condition is met, with the remainder (features, tuning, LOMO) cut to §6 1a. Both citations are also dead: `config.py:272` is now `REDFIN_TARGET_METROS` and `agents/valuation_rent.py:78` is the LLM-fallback TODO. Needs the "retargeted rather than closed" treatment U8.10 already uses |

**Already done, recorded so the next reader does not redo it:** `tools/model/rent_model.py`'s
**module docstring** was rewritten Aug 30, 2026. It had described the retired anchor as
the shipped design — rent divided by the county FMR and multiplied by today's FMR, with
`tools/rent_drift.py` correcting the drift — in the file whose docstring carries this
model's design reasoning. Fixed there and then because it was a false description of the
system rather than a naming inconsistency; the rest waits.

**What is deliberately *not* on this list.** `agents/valuation_rent.py:664` and
`rent_model.py:645` name `LinearRegression` in the past tense, describing what shipped
*before* U11.1 and why the input-domain guard replaced its refusal path. Those are
correct history and rewriting them would delete the reasoning. `FMR_BEDROOM_CAP_EXCEEDED`
and `fmr_shape_year` likewise keep their names on purpose — the bedroom step really is
the federal schedule's.

### U11.M ✅ — Maintenance *(separate commit, per §8)*

Clear the `TODO(cut-list)` at `config.py:295` and `agents/valuation_rent.py` as
resolved-or-superseded; update the cut-list rows for 1a and 6 in §6; update the `TODO`
inventory in [`../design/engineering_standards.md`](../design/engineering_standards.md).

---

**Done Aug 30, 2026.**

- **`TODO(cut-list)` is down from three sites to one.** Model form was *spent*, not
  deferred — `config.RENT_MODEL_ESTIMATOR` replaced the note, and
  `scripts/model_form_probe.py`'s docstring now says the paragraph it argues against
  describes the state *before* it ran. The surviving site is the descoped LLM rent fallback
  (§6 item 3), which is genuinely still deferred.
- **`TODO(U8)` is down from nine sites to six.** Closed: leave-one-metro-out (cut to §6 1a,
  transfer question disclosed via OQ-12), the rent-comp divergence confirmation, and the
  stated-rent threshold's blocking measurement. Still open: #6's numbers (now closed as a
  decision but the constants stay marked provisional), pass-scoped flags, and checks A/B —
  whose *veto* was overturned by re-measurement, so it is a live decision rather than a
  settled one.
- **§6 cut-list rows 1a and 6 rewritten.** Item 6 leaves the list by being **spent**, like
  item 3, and two of its stated costs were wrong in the direction that made it look
  expensive: it drops 0.3% of training rows rather than 27%, and it keeps FMR rather than
  abandoning it. Item 1a was **split** — model form spent, feature engineering plus tuning
  plus LOMO cut.
- **The `TODO` inventory in `engineering_standards.md` reconciled** against
  `grep -rn "TODO(" src/`, which is the check that table exists to pass.
- **Four evidence scripts repaired**, listed under U11.3 item 4 above. One of them was
  actively wrong rather than merely broken.
