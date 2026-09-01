# Deal Evaluation — 7001 Amboy Rd, Staten Island, NY 10307

> 🚩 **Escalated to human review.** This deal did not clear the system's automated checks on its own. See the disclosures below for why.
>
> **Reviewer note:** [demo] Reviewed and released for reporting. A real reviewer would resolve the disclosures above before proceeding.

**Confidence:** 0.00 (escalation threshold 0.60) · **Disclosures:** 9 · **Comparables:** 0

*1.40 deducted from a starting 1.00: 1.10 from this property, 0.30 from how much is known about this market. Both halves are itemized under Disclosures below.*

## Disclosures

9 disclosure(s) were raised during this evaluation. Each is listed in full below, grouped by whether it describes this property or the data available for its market, and ordered most severe first within each.

### About this property (7)

*Specific to this listing or this run — some of these may be resolvable.*

**Critical (2)** — the estimate below should not be relied on without addressing this

- **`sparse_comps`** — Found 0 qualifying comps after 4 iteration(s); the threshold is 8. Estimates derived from this set carry materially wider uncertainty than a full comp set would imply.
  *raised by:* `comps_retrieval`
- **`forecast_unavailable`** — The scenario search ended with no surviving hypothesis. Every candidate at depth 2 scored below the 0.40 threshold. The beam is empty, which is a finding about the evidence rather than a reason to lower the bar. Every candidate considered is listed in the branch ledger with the reason it was discarded.
  *raised by:* `scenario_forecast`

**Warning (3)** — materially widens the uncertainty on the estimate below

- **`relaxed_search_radius`** — Only 0 comps within 2.0 mi (threshold 8); widened to 4.0 mi. Comps are drawn from a broader area than ideal.
  *raised by:* `comps_retrieval`
- **`relaxed_search_radius`** — Only 0 comps within 4.0 mi (threshold 8); widened to 8.0 mi. Comps are drawn from a broader area than ideal.
  *raised by:* `comps_retrieval`
- **`low_confidence_estimate`** — Confidence 0.00 is below the 0.60 threshold; routing to human review rather than reporting as a normal result. The largest single deduction is about this specific listing, so there may be something a reviewer can act on: Found 0 qualifying comps after 4 iteration(s); the threshold is 8.
  *raised by:* `critic`

**Disclosure (2)** — a mechanism used, disclosed for transparency; not a weakness

- **`relaxed_match_criteria`** — Only 0 comps within 2.0 mi; dropped the square-footage band to widen the candidate set.
  *raised by:* `comps_retrieval`
- **`rent_anchored_to_market_index`** — Estimated rent of $2,654/mo is a modelled ratio of 1.02 applied to a reference rent of $2,600 for county 3608599999, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes. It is not an observed rent for this building. The ratio comes from a model trained on 2018-19 listings normalized against the same index at their own listing months, so what it carries forward is how this property compares to its neighbors rather than what anything cost in 2019.
  *raised by:* `valuation_rent`

### About our coverage of this market (2)

*True of every listing in this market, not of this property in particular; they still widen the uncertainty on the numbers below.*

**Warning (2)** — materially widens the uncertainty on the estimate below

- **`rent_estimate_market_error_elevated`** — The rent model's historical error in New York is $855, 1.9x the $452 error quoted elsewhere in this report as the model's typical accuracy, measured on 264 held-out New York listings. This is a known weakness of the model in this particular market, not a property of this deal or a sign the model has never seen a market like it — New York listings are part of what the model trained on; they are just harder to price accurately than most. Treat this estimate as less reliable than the headline error band on its own would suggest.
  *raised by:* `valuation_rent`
- **`rent_anchor_county_level`** — This estimate is anchored to a county-wide market rent figure rather than to this ZIP code's own, because the rent index Zillow publishes for ZIP 10307 does not cover the period this estimate reads from. Rents span roughly 2x within a single county, so a county anchor cannot distinguish an expensive neighborhood from a cheap one — the estimate describes the county's rent level, not this address's.
  *raised by:* `valuation_rent`

## Findings

| Metric | Value | Basis |
| --- | --- | --- |
| Asking price | $875,000 | listing |
| Units | 3 | listing |
| Estimated rent | $2,654/mo per unit ± $452 overall, ± $855 in New York | regression_model, ratio 1.02 × market rent $2,600 (county-wide) as of 2026-07 |
| Estimated value | not produced | no property-level sale data exists in this project's sources; see the market benchmark below |

### Market benchmark

Typical **2-4 unit residential buildings with no commercial space** sale in **ZIP 10307**: **$1,054,490**, the median of 152 recorded sales since 2023-01-01 (NYC Department of Finance, via NYC Open Data).
This listing asks $875,000 — **17% below** that benchmark.

For contrast, the median across the whole New York metro is $976,721 (Redfin, 2-4 unit) — this neighborhood runs **8% above** it. The neighborhood figure is the one used above, because a metro-wide median describes properties an hour apart identically.

> **This is not an estimate of this property's value.** The records behind it are other properties' sales in this ZIP over the period named, with no adjustment for size, unit count or condition — and the local definition of a multi-family sale is the one quoted above, which differs between markets because the counties publishing the records define it differently. It is a market reference for reading the asking price against, and nothing more.

### How the rent figure was reached

A gradient-boosted tree model over bedrooms, bathrooms and square footage, fit to 5,701 listings, trained Aug 30, 2026. Every listing was scored by a version of the model that had not been shown it, and on that basis it missed by **$452/mo on average** (0.269 in ratio terms). That is the error band on the figure above, and it is wide.

That figure is the model's error averaged across every market it was trained on. In **New York** specifically, the same measurement missed by **$855/mo** (n=264 listings) — materially worse than the figure above, see the disclosure below.

**Cross-check against the comps: not run** — no comps were retrieved, below the 3 needed for a median to describe a distribution rather than a single listing. The estimate above rests on the model alone, with no local evidence corroborating it.

### The listing's stated rents

The listing states $2,850, $2,900 and $2,975 per month across 3 units — an average of **$2,908** per unit, **$8,725/mo** in total.

This system estimates **$2,654/mo** for a 2-bedroom unit, or **$7,962/mo** across 3 units. The stated rents sit **10% above** that estimate.

> **Stated rents above the estimate are worth verifying against leases rather than taken from the listing.** The estimate describes a unit of this size and configuration in this ZIP code; rents materially above it usually have an explanation the listing has not given — short-term or furnished tenancies, rents including utilities or parking, or figures that are asking rather than collected.

### Scenarios

Every candidate at depth 2 scored below the 0.40 threshold. The beam is empty, which is a finding about the evidence rather than a reason to lower the bar.

## Comparable Rentals

**No qualifying comparables were retrieved.** Any rent figure in this report is therefore ungrounded in local market evidence. See the disclosures above for what the retrieval loop attempted.

---

*Generated by the multi-family deal evaluator · run started 2026-08-31 11:44 · planner invocations 1 · rework passes 0*