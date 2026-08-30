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
