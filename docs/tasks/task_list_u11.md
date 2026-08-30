# U11 — Rent model v2 — task list

> **Conventions for this file are in [`README.md`](README.md).** Section numbers (§1–§9)
> and decision numbers (#1–#17) refer to
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

### U11.1 — Model-form probe *(approved Aug 29, 2026; runs first)*

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
  `rent_estimate_unavailable` (critical) for `rent_anchored_to_fmr` +
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

### U11.2 — Feature measurement

CV-ablation pricing of corpus columns the model does not use: amenity/pet fields,
listing month (seasonality), sqft-per-bedroom, bath:bed ratio — each reported as
incremental MAE against the U11.1 winner. **Standing constraint:** features stay
structural; no market identifier. The FMR-ratio target exists to keep the model
market-free (§2), and a metro dummy would reintroduce exactly the dollar-level
memorization the ratio removes.

### U11.3 — The anchor (gated on Q1, decided on U11.1–2's numbers)

If taken: re-anchor the target on ZORI (cut-list 6) — the largest lever and the largest
cost. If not taken: record the decision and its evidence in the §7 register, and the
U8.4b drift correction remains the vintage-drift instrument.

### U11.4 — Adoption, tuning, and validation artifacts

Hyperparameter tuning for whatever form survives, under the same CV; retrain and persist
with the per-metro breakdown (`TrainingReport.mae_dollars_by_metro` travels with the
artifact); the leave-one-metro-out run as *transfer* evidence (OQ-12's first half, still
open — LOMO answers what the holdout split cannot); by-metro reporting as the standard
for every future retrain. Handoff to U8's sequence for re-record and batch
re-derivation.

### U11.M — Maintenance *(separate commit, per §8)*

Clear the `TODO(cut-list)` at `config.py:295` and `agents/valuation_rent.py` as
resolved-or-superseded; update the cut-list rows for 1a and 6 in §6; update the `TODO`
inventory in [`../design/engineering_standards.md`](../design/engineering_standards.md).
