# Deal Evaluation — 7001 Amboy Rd, Staten Island, NY 10307

> **Recommendation — Proceed.** The asking price is 17% below the typical sale price for this area.
>
> 🚩 **System check — escalated to human review.** This deal did not clear the system's automated checks on its own; the disclosures below say why. **This is a statement about the evaluation, not about the property.**
>
> **Reviewer note:** [demo] Reviewed and released for reporting. A real reviewer would resolve the disclosures in this report before proceeding.

*An independent review of the same evidence reached a different conclusion — **Proceed with caution**. Its reasoning: Price is 17% below market but rent lacks local confirmation, so treat as a cautious opportunity. The recommendation above follows this system's stated rule, which is the one that decides; the disagreement is disclosed here rather than resolved. A deal the two readings agree on is a more comfortable one to hold than a deal they split over.*

## Summary

The property at 7001 Amboy Rd, Staten Island, NY 10307 is a three‑unit residential building with an asking price of $875,000 and an estimated rent of $2,654 per month per unit. The report recommends proceeding with the investment because the asking price is 17% below the typical sale price for the area. An independent review reached a different conclusion, advising to proceed with caution, and the report notes this disagreement without resolving it. The evaluation was escalated to a human reviewer because it did not clear the system's automated checks, and 12 disclosures were raised.

**Confidence:** 0.00 (escalation threshold 0.60) · **Disclosures:** 12 · **Comparables:** 0

*1.00 deducted from a starting 1.00: 0.70 from this property, 0.30 from how much is known about this market. Both halves are itemized under Disclosures below.*

## Disclosures — 12 (1 critical, 5 warning, 6 informational)

12 disclosure(s) were raised during this evaluation. Each is listed in full below, grouped by whether it describes this property or the data available for its market, and ordered most severe first within each. Entries that describe a mechanism rather than a weakness are collapsed; anything that qualifies a number below is open.

### About this property (10)

*Specific to this listing or this run — some of these may be resolvable.*

**Critical (1)** — the estimate below should not be relied on without addressing this

- **`sparse_comps`** — Found 0 qualifying comps after 4 iteration(s); the threshold is 8. Estimates derived from this set carry materially wider uncertainty than a full comp set would imply.  
  *raised by:* `comps_retrieval`

**Warning (3)** — materially widens the uncertainty on the estimate below

- **`relaxed_search_radius`** — Only 0 comps within 2.0 mi (threshold 8); widened to 4.0 mi. Comps are drawn from a broader area than ideal.  
  *raised by:* `comps_retrieval`
- **`relaxed_search_radius`** — Only 0 comps within 4.0 mi (threshold 8); widened to 8.0 mi. Comps are drawn from a broader area than ideal.  
  *raised by:* `comps_retrieval`
- **`low_confidence_estimate`** — Confidence 0.00 is below the 0.60 threshold; routing to human review rather than reporting as a normal result. The largest single deduction is about this specific listing, so there may be something a reviewer can act on: Found 0 qualifying comps after 4 iteration(s); the threshold is 8.  
  *raised by:* `critic`

**Disclosure (6)** — a mechanism used, disclosed for transparency; not a weakness

<details>
<summary><b><code>relaxed_match_criteria</code></b> — Only 0 comps within 2.0 mi; dropped the square-footage band to widen the candidate set</summary>

*raised by:* `comps_retrieval`
</details>

<details>
<summary><b><code>rent_anchored_to_market_index</code></b> — Estimated rent of $2,654/mo is a modelled ratio of 1.02 applied to a reference rent of $2,600 for county 3608599999, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes</summary>

Estimated rent of $2,654/mo is a modelled ratio of 1.02 applied to a reference rent of $2,600 for county 3608599999, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes. It is not an observed rent for this building. The ratio comes from a model trained on 2018-19 listings normalized against the same index at their own listing months, so what it carries forward is how this property compares to its neighbors rather than what anything cost in 2019.

*raised by:* `valuation_rent`
</details>

<details>
<summary><b><code>appreciation_source</code></b> — Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the New York metro, over 88 year-over-year observations</summary>

Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the New York metro, over 88 year-over-year observations. This project has one appreciation series: the ZIP-level tier was closed on sample size (median 2 sales per ZIP-period) and no all-residential extract exists here, so there is no fallback below this one.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>anomalous_period_included</code></b> — The price bands include the 2020-2022 window, which is 41% of the observations</summary>

The price bands include the 2020-2022 window, which is 41% of the observations. Near-zero rates pulled price growth well above trend in that stretch, and the optimistic band rests on it.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>rent_growth_source</code></b> — Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Richmond County, NY, a median across the 9 postal codes it covers over 60 year-over-year observations from 2021-08 to 2026-07</summary>

Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Richmond County, NY, a median across the 9 postal codes it covers over 60 year-over-year observations from 2021-08 to 2026-07. Note the difference in geography from the rent estimate itself, which is anchored at this property's own postal code: a single postal code's rent index either does not reach back far enough to measure a five-year trend or does not exist at all, so the trend is measured across the surrounding county and the estimate is not.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>forecast_branches_near_tied</code></b> — The two best-scoring scenario pairings were separated by less than 0.05, this system's tie threshold — the evaluator found both equally defensible</summary>

The two best-scoring scenario pairings were separated by less than 0.05, this system's tie threshold — the evaluator found both equally defensible. Both appear in the scenario table below, and each scenario's label comes from its projected outcome, so no reported figure depends on which of the two nominally ranked first. A tie here is common and often correct: two pairings that mirror each other make equally strong claims about a relationship between rent and price growth that this project has measured and found weak. The scores also come from a single model call whose repeat runs measurably vary, so a gap this small can be a property of this one sample.

*raised by:* `scenario_forecast`
</details>


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

### Scenarios — 5-year outlook

#### What each series has done

Measured ranges, one per quantity, each labelled for its own band rather than for a combined outcome. Given a stretch of history these figures are arithmetic and do not move between runs — but *which* stretch of history is a judgment, and this run made it one way (2020–2022 kept in both); the reasoning behind it is shown under **Step 1** below.

| | Weakest sustained stretch | Long-run average | Strongest sustained stretch | Measured over |
| --- | --- | --- | --- | --- |
| **Monthly rent** | +3.93%/yr | +6.77%/yr | +10.45%/yr | 60 year-over-year observations |
| **Sale price** | +1.32%/yr | +5.61%/yr | +14.16%/yr | 88 year-over-year observations; strongest stretch falls in 2020–2022 |

Projected from modelled rent $2,654/mo and the **asking price** $875,000. The price side compounds the asking price rather than an estimated value — this system does not produce one, and says so above.

Each row is named for the combination it describes, and the bands beside each figure are the same ones in the table above. **Rows are ordered worst to best by combined outcome**, so the central case is not necessarily in the middle. Rent and price are paired here rather than forecast independently, and this project has measured how the two move together: weakly, and not in a consistent direction. Read each row as one internally consistent story about this market, not as evidence that rent and price tend to move that way.

| Scenario | Rent growth | Price growth | Rent in yr 5 | Price in yr 5 | Why this row is shown |
| --- | --- | --- | --- | --- | --- |
| **Rents stall, prices fall** | +3.93%/yr (weakest stretch) | +1.32%/yr (weakest stretch) | $3,218 | $934,077 | **0.85** — outscored the pairings left out |
| **Rents stall, prices hold** | +3.93%/yr (weakest stretch) | +5.61%/yr (long-run average) | $3,218 | $1,149,405 | **0.80** — outscored the pairings left out |
| **Central case** | +6.77%/yr (long-run average) | +5.61%/yr (long-run average) | $3,682 | $1,149,405 | **0.70** — the neutral case, always shown |

**Not represented above:** the strongest stretch for rent and the strongest stretch for sale price. Every band is measured and printed in the table at the top of this section; what the rows show is which *combinations* the search judged worth reporting, and a band reaching no row means it did not survive that judgment in any pairing. The bottom row is therefore the best case among those reported, not the best case measured.

- **Rents stall, prices fall** — Both bands correspond to low growth extremes that are observed across many periods and are not undermined by upstream flags.
- **Rents stall, prices hold** — Pessimistic rent growth is low and observed, while base price growth is moderate and supported by multiple observations.
- **Central case** — Both bands represent moderate growth levels that are observed across the series and are not flagged as unreliable.

The score in the last column is how well the forecast search judged that combination to be supported by the evidence it was given, from 0 to 1 — shown because a scenario the system itself rated weakly should be read as one. Two cautions: a score says how well evidenced a combination is, not how likely it is, so a higher-scoring row is not a more probable outcome; and the scores come from a single model call whose repeat runs measurably vary, so small differences between them are not reliable — which is why a row kept on the tie-break says so rather than reporting the gap.

#### How these bands were built

**Rent** — Zillow Observed Rent Index, county-level monthly median across all unit types for Richmond County, NY, a median across the 9 postal codes within it, covering 2021-08 to 2026-07 (60 year-over-year observations). The outer bands are the worst and best twelve-month stretches the index actually held, not its worst and best single months; the base case is the average across every month kept.
  This is measured across the county, while the rent estimate above is anchored to this property's own postal code. A single postal code's rent index generally does not reach back far enough to measure a five-year trend, so the trend is read at the wider geography and the estimate is not.
  2020–2022 included — the same treatment question asked of the sale-price series below, so the two describe the same span of history.

**Price** — Redfin metro-level Multi-Family (2–4 unit) median sale price for New York, 88 year-over-year observations, 2020–2022 included.

#### How the forecast search reasoned

13 hypotheses were evaluated and 9 discarded, across two questions asked in order. Pruning is recorded rather than silent: an evaluator that quietly drops a correct-but-unusual branch looks identical to one working properly.

**Step 1 — which reading of the history should every band be built from?**  
*4 considered, 1 kept.*

- **`f-00` (0.95) — Both series retain the full pre‑ and post‑window observations, maximizing sample size and avoiding the loss of any historical data. ← carried forward**
- `f-10` (0.60) — The rent growth band excludes the 2020‑2022 period, losing 17 observations but still retains the full price observation set, making it moderately defensible. **Discarded:** Scored 0.60, outside the top 1 at this level.
- `f-01` (0.45) — The price growth band excludes the 2020‑2022 period, dropping 36 observations and leaving a narrower span that weakens its defensibility. **Discarded:** Scored 0.45, outside the top 1 at this level.
- `f-11` (0.15) — Both series exclude the 2020‑2022 window, incurring the greatest loss of data and offering the weakest basis for the forecast. **Discarded:** Scored 0.15, outside the top 1 at this level.

**Step 2 — which combinations of those bands are worth showing?**  
*9 considered, 3 kept.*

- **`f-00-pesspess` (0.85) — Both bands correspond to low growth extremes that are observed across many periods and are not undermined by upstream flags. ← carried forward**
- **`f-00-pessbase` (0.80) — Pessimistic rent growth is low and observed, while base price growth is moderate and supported by multiple observations. ← carried forward**
- `f-00-pessopti` (0.75) — Pessimistic rent is well observed, but the optimistic price growth relies on a high extreme that appears only in a few periods. **Discarded:** Scored 0.75, inside the top 3 at this level, but displaced so that the neutral case is always among those reported.
- `f-00-baseopti` (0.70) — Base rent is moderately supported, while optimistic price growth is an extreme observed only briefly. **Discarded:** Scored 0.70, outside the top 3 at this level.
- **`f-00-basebase` (0.70) — Both bands represent moderate growth levels that are observed across the series and are not flagged as unreliable. ← carried forward**
- `f-00-basepess` (0.65) — Base rent growth is higher than typical observed levels and may be less corroborated, though the pessimistic price growth is supported. **Discarded:** Scored 0.65, outside the top 3 at this level.
- `f-00-optibase` (0.65) — Optimistic rent growth is weakly supported, but base price growth has moderate observation backing. **Discarded:** Scored 0.65, outside the top 3 at this level.
- `f-00-optipess` (0.60) — Optimistic rent growth is an extreme with limited observations, paired with a low price growth that is observed but less frequent. **Discarded:** Scored 0.60, outside the top 3 at this level.
- `f-00-optiopti` (0.55) — Both bands are high extremes that are observed only in short bursts, making them the least well founded of the set. **Discarded:** Scored 0.55, outside the top 3 at this level.

*The scores and the wording above come from one model call, and repeat calls on identical input have been measured moving materially. Read this as a sample of the reasoning rather than a stable ranking — small differences between scores are not reliable. The bands themselves are arithmetic and do not move.*

## Comparable Rentals

**No qualifying comparables were retrieved.** Any rent figure in this report is therefore ungrounded in local market evidence. See the disclosures above for what the retrieval loop attempted.

---

*Generated by the multi-family deal evaluator · run started 2026-09-02 02:05 · planner invocations 1 · rework passes 0*
