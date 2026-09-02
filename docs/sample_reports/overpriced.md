# Deal Evaluation — 4700 N Racine Ave, Chicago, IL 60640

> **Recommendation — Proceed with caution.** The asking price is 55% above the typical sale price for this area — higher than roughly 90% of recorded sales in this ZIP code.
>
> ✅ **System check — reported.** The figures below cleared the system's own checks without needing a human to release them.

*An independent review of the same evidence reached a different conclusion — **Do not proceed**. Its reasoning: The asking price is 55% above recent sales in the ZIP, making it overpriced despite comparable rents. The recommendation above follows this system's stated rule, which is the one that decides; the disagreement is disclosed here rather than resolved. A deal the two readings agree on is a more comfortable one to hold than a deal they split over.*

**Also behind this recommendation:**

- Nearby listings do corroborate the rent this deal's income depends on, so the premium is at least supported by the income it generates.

## Summary

The property at 4700 N Racine Ave in Chicago, IL 60640 is a two‑unit residential building. It is listed for $1,345,000 with an estimated rent of $2,154 per month per unit. The report recommends proceeding with caution because the asking price is about 55% above the typical sale price in the area and exceeds roughly 90% of recorded sales in the ZIP code, though nearby listings support the rent level. An independent review reached a different conclusion to do not proceed, and the report notes this disagreement without resolving it, and the automated checks were cleared without human review.

**Confidence:** 1.00 (escalation threshold 0.60) · **Disclosures:** 6 · **Comparables:** 8

## Disclosures — 6 (6 informational)

6 disclosure(s) were raised during this evaluation. Each is listed in full below, grouped by whether it describes this property or the data available for its market, and ordered most severe first within each. Entries that describe a mechanism rather than a weakness are collapsed; anything that qualifies a number below is open.

### About this property (6)

*Specific to this listing or this run — some of these may be resolvable.*

**Disclosure (6)** — a mechanism used, disclosed for transparency; not a weakness

<details>
<summary><b><code>relaxed_match_criteria</code></b> — Only 7 comps within 2.0 mi; dropped the square-footage band to widen the candidate set</summary>

*raised by:* `comps_retrieval`
</details>

<details>
<summary><b><code>rent_anchored_to_market_index</code></b> — Estimated rent of $2,154/mo is a modelled ratio of 1.06 applied to a reference rent of $2,026 for ZIP 60640, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes</summary>

Estimated rent of $2,154/mo is a modelled ratio of 1.06 applied to a reference rent of $2,026 for ZIP 60640, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes. It is not an observed rent for this building. The ratio comes from a model trained on 2018-19 listings normalized against the same index at their own listing months, so what it carries forward is how this property compares to its neighbors rather than what anything cost in 2019.

*raised by:* `valuation_rent`
</details>

<details>
<summary><b><code>appreciation_source</code></b> — Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the Chicago metro, over 88 year-over-year observations</summary>

Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the Chicago metro, over 88 year-over-year observations. This project has one appreciation series: the ZIP-level tier was closed on sample size (median 2 sales per ZIP-period) and no all-residential extract exists here, so there is no fallback below this one.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>anomalous_period_included</code></b> — The price bands include the 2020-2022 window, which is 41% of the observations</summary>

The price bands include the 2020-2022 window, which is 41% of the observations. Near-zero rates pulled price growth well above trend in that stretch, and the optimistic band rests on it.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>rent_growth_source</code></b> — Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Cook County, IL, a median across the 126 postal codes it covers over 91 year-over-year observations from 2019-01 to 2026-07</summary>

Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Cook County, IL, a median across the 126 postal codes it covers over 91 year-over-year observations from 2019-01 to 2026-07. Note the difference in geography from the rent estimate itself, which is anchored at this property's own postal code: a single postal code's rent index either does not reach back far enough to measure a five-year trend or does not exist at all, so the trend is measured across the surrounding county and the estimate is not.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>forecast_branches_near_tied</code></b> — The last scenario pairing to make the table and the best one left out of it were not separated on score at all — the pairing left out scored 0.00 *above* the one kept, and the order was settled by this system's standing preference for the more conservative reading, which applies wherever two scores sit within 0.05 of each other</summary>

The last scenario pairing to make the table and the best one left out of it were not separated on score at all — the pairing left out scored 0.00 *above* the one kept, and the order was settled by this system's standing preference for the more conservative reading, which applies wherever two scores sit within 0.05 of each other. This line matters in a way a tie between two reported scenarios does not: it decides which pairings are shown at all, so the set of scenarios below could as defensibly have been a different set. The pairing that missed it is listed in the search ledger with its own score and the reason it was dropped. As with every score here, it comes from a single model call whose repeat runs measurably vary.

*raised by:* `scenario_forecast`
</details>


## Findings

| Metric | Value | Basis |
| --- | --- | --- |
| Asking price | $1,345,000 | listing |
| Units | 2 | listing |
| Estimated rent | $2,154/mo per unit ± $452 overall, ± $343 in Chicago | regression_model, ratio 1.06 × market rent $2,026 (ZIP 60640) as of 2026-07 |
| Estimated value | not produced | no property-level sale data exists in this project's sources; see the market benchmark below |

### Market benchmark

Typical **2-6 unit apartment buildings (assessor class 211)** sale in **ZIP 60640**: **$867,500**, the median of 148 recorded sales since 2023-01-01 (Cook County Assessor's Office, via Cook County Open Data).
This listing asks $1,345,000 — **55% above** that benchmark.

For contrast, the median across the whole Chicago metro is $490,903 (Redfin, 2-4 unit) — this neighborhood runs **77% above** it. The neighborhood figure is the one used above, because a metro-wide median describes properties an hour apart identically.

> **This is not an estimate of this property's value.** The records behind it are other properties' sales in this ZIP over the period named, with no adjustment for size, unit count or condition — and the local definition of a multi-family sale is the one quoted above, which differs between markets because the counties publishing the records define it differently. It is a market reference for reading the asking price against, and nothing more.

### How the rent figure was reached

A gradient-boosted tree model over bedrooms, bathrooms and square footage, fit to 5,701 listings, trained Aug 30, 2026. Every listing was scored by a version of the model that had not been shown it, and on that basis it missed by **$452/mo on average** (0.269 in ratio terms). That is the error band on the figure above, and it is wide.

That figure is the model's error averaged across every market it was trained on. In **Chicago** specifically, the same measurement missed by **$343/mo** (n=630 listings) — in line with the figure above.

**Cross-check against the comps:** 8 of 8 retrieved comps normalized cleanly to their own area and fiscal year, 8 of them at ZIP resolution, implying **$2,293/mo** (middle half $2,145–$2,727). The model sits 6% below that.

### The listing's stated rents

The listing states $1,750 and $1,800 per month across 2 units — an average of **$1,775** per unit, **$3,550/mo** in total.

This system estimates **$2,154/mo** for a 2-bedroom unit, or **$4,308/mo** across 2 units. The stated rents sit **18% below** that estimate.

> **A gap in this direction is common and is not on its own evidence that the property is under-rented.** The estimate describes what a unit of this size and configuration rents for in this ZIP code today; a stated rent is what sitting tenants are actually paying, which lags the market wherever leases were signed earlier or renewed below market. It is also an estimate with a stated error band — see the rent disclosures above — and a gap inside that band is not a disagreement.

### Price against rent

At the modelled rent, this property's gross rent is **$51,691 a year** across 2 units, so the asking price is **26.0×** annual gross rent.

The typical recorded sale in this ZIP code would buy the same rent at **16.8×**. That is the *same* comparison as the price-versus-benchmark figure above rather than a second one — both multiples divide by the same rent, so the gap between them is the price gap restated. It is shown because the multiple is the unit this comparison is usually made in.

> **This is a gross multiple, not a yield, and the difference is the expenses.** It divides the price by rent before taxes, insurance, vacancy, maintenance or management — none of which this system models, and all of which a buyer pays. A capitalization rate would account for them; producing one here would mean assuming an expense ratio and presenting the assumption as a finding, so this report stops at the ratio its data can support and says where the line is.

### Scenarios — 5-year outlook

#### What each series has done

Measured ranges, one per quantity, each labelled for its own band rather than for a combined outcome. Given a stretch of history these figures are arithmetic and do not move between runs — but *which* stretch of history is a judgment, and this run made it one way (2020–2022 kept in both); the reasoning behind it is shown under **Step 1** below.

| | Weakest sustained stretch | Long-run average | Strongest sustained stretch | Measured over |
| --- | --- | --- | --- | --- |
| **Monthly rent** | -1.03%/yr | +4.08%/yr | +7.26%/yr | 91 year-over-year observations |
| **Sale price** | -4.80%/yr | +8.92%/yr | +20.97%/yr | 88 year-over-year observations; strongest stretch falls in 2020–2022 |

Projected from modelled rent $2,154/mo and the **asking price** $1,345,000. The price side compounds the asking price rather than an estimated value — this system does not produce one, and says so above.

Each row is named for the combination it describes, and the bands beside each figure are the same ones in the table above. **Rows are ordered worst to best by combined outcome**, so the central case is not necessarily in the middle. Rent and price are paired here rather than forecast independently, and this project has measured how the two move together: weakly, and not in a consistent direction. Read each row as one internally consistent story about this market, not as evidence that rent and price tend to move that way.

| Scenario | Rent growth | Price growth | Rent in yr 5 | Price in yr 5 | Why this row is shown |
| --- | --- | --- | --- | --- | --- |
| **Prices fall, rents hold** | +4.08%/yr (long-run average) | -4.80%/yr (weakest stretch) | $2,630 | $1,051,983 | **0.75** — outscored the pairings left out |
| **Rents stall, prices hold** | -1.03%/yr (weakest stretch) | +8.92%/yr (long-run average) | $2,045 | $2,062,119 | **0.70** — level with 2 other pairings, kept as the more cautious |
| **Central case** | +4.08%/yr (long-run average) | +8.92%/yr (long-run average) | $2,630 | $2,062,119 | **0.90** — outscored the pairings left out |

**Not represented above:** the strongest stretch for rent and the strongest stretch for sale price. Every band is measured and printed in the table at the top of this section; what the rows show is which *combinations* the search judged worth reporting, and a band reaching no row means it did not survive that judgment in any pairing. The bottom row is therefore the best case among those reported, not the best case measured.

- **Prices fall, rents hold** — Base rent is well supported, and the price pessimism aligns with observed negative periods, providing solid grounding.
- **Rents stall, prices hold** — The price assumption uses a median growth rate with ample observations, while the rent extreme is based on limited data.
- **Central case** — Both rent and price use median growth rates backed by the largest number of observations, making them highly defensible.

The score in the last column is how well the forecast search judged that combination to be supported by the evidence it was given, from 0 to 1 — shown because a scenario the system itself rated weakly should be read as one. Two cautions: a score says how well evidenced a combination is, not how likely it is, so a higher-scoring row is not a more probable outcome; and the scores come from a single model call whose repeat runs measurably vary, so small differences between them are not reliable — which is why a row kept on the tie-break says so rather than reporting the gap.

#### How these bands were built

**Rent** — Zillow Observed Rent Index, county-level monthly median across all unit types for Cook County, IL, a median across the 126 postal codes within it, covering 2019-01 to 2026-07 (91 year-over-year observations). The outer bands are the worst and best twelve-month stretches the index actually held, not its worst and best single months; the base case is the average across every month kept.
  This is measured across the county, while the rent estimate above is anchored to this property's own postal code. A single postal code's rent index generally does not reach back far enough to measure a five-year trend, so the trend is read at the wider geography and the estimate is not.
  2020–2022 included — the same treatment question asked of the sale-price series below, so the two describe the same span of history.

**Price** — Redfin metro-level Multi-Family (2–4 unit) median sale price for Chicago, 88 year-over-year observations, 2020–2022 included.

#### How the forecast search reasoned

13 hypotheses were evaluated and 9 discarded, across two questions asked in order. Pruning is recorded rather than silent: an evaluator that quietly drops a correct-but-unusual branch looks identical to one working properly.

**Step 1 — which reading of the history should every band be built from?**  
*4 considered, 1 kept.*

- **`f-00` (0.96) — Both rent and price bands retain the full pre‑anomalous sample and include the 2020‑2022 period, minimizing data loss while preserving sufficient observation count for stable band estimation. ← carried forward**
- `f-10` (0.71) — Rent excludes the anomalous period, losing 36 of 91 observations, but price retains its full 88‑observation band, so the overall data loss is lower and the resulting bands remain sufficiently wide. **Discarded:** Scored 0.71, outside the top 1 at this level.
- `f-01` (0.48) — The price band excludes the anomalous period, dropping 36 of 88 observations and yielding a narrower, less‑stable band, whereas rent retains its full sample, creating an asymmetric cost that weakens the pairing. **Discarded:** Scored 0.48, outside the top 1 at this level.
- `f-11` (0.12) — Both series exclude the anomalous period, each losing a substantial portion of data (over a third), resulting in the smallest and least representative bands for this market. **Discarded:** Scored 0.12, outside the top 1 at this level.

**Step 2 — which combinations of those bands are worth showing?**  
*9 considered, 3 kept.*

- **`f-00-basebase` (0.90) — Both rent and price use median growth rates backed by the largest number of observations, making them highly defensible. ← carried forward**
- **`f-00-basepess` (0.75) — Base rent is well supported, and the price pessimism aligns with observed negative periods, providing solid grounding. ← carried forward**
- `f-00-optibase` (0.70) — Base price is well founded, but the optimistic rent growth relies on a narrow set of observations. **Discarded:** Scored 0.70, level with the last one kept — too close for this system to call a difference — so it was this system's standing preference for the more cautious reading, not the score, that left this one out.
- **`f-00-pessbase` (0.70) — The price assumption uses a median growth rate with ample observations, while the rent extreme is based on limited data. ← carried forward**
- `f-00-baseopti` (0.65) — Base rent is robust, while the optimistic price, though an observed extreme, rests on a short‑lived spike. **Discarded:** Scored 0.65, level with the last one kept — too close for this system to call a difference — so it was this system's standing preference for the more cautious reading, not the score, that left this one out.
- `f-00-pesspess` (0.55) — Both rent and price assumptions are drawn from low‑observation extremes, making them only modestly well‑founded. **Discarded:** Scored 0.55, outside the top 3 at this level.
- `f-00-optipess` (0.55) — The optimistic rent growth is based on limited data, and it is paired with a price decline that lacks sustained evidence. **Discarded:** Scored 0.55, outside the top 3 at this level.
- `f-00-optiopti` (0.50) — Both components are high‑growth extremes that are observed only in brief periods, limiting their overall defensibility. **Discarded:** Scored 0.50, outside the top 3 at this level.
- `f-00-pessopti` (0.45) — The optimistic price growth is an extrapolation beyond the observed sustained window, reducing its evidential support. **Discarded:** Scored 0.45, outside the top 3 at this level.

*The scores and the wording above come from one model call, and repeat calls on identical input have been measured moving materially. Read this as a sample of the reasoning rather than a stable ranking — small differences between scores are not reliable. The bands themselves are arithmetic and do not move.*

## Comparable Rentals

8 comparable listing(s) retrieved within 2.0 miles after 2 retrieval pass(es).

| Listing ID | Rent | Beds | Baths | Sq Ft | Distance | Similarity | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `5121924855` | $1,380 | 2 | 1 | 858 | 1.7 mi | 0.657 | RentDigs.com |
| `5162453640` | $3,167 | 2 | 2 | 1,186 | 0.9 mi | 0.510 | RENTCafé |
| `5121793891` | $1,600 | 2 | 1 | 1,300 | 0.9 mi | 0.473 | RentDigs.com |
| `5121925863` | $1,350 | 2 | 1 | 753 | 1.7 mi | 0.442 | RentDigs.com |
| `5121925891` | $1,330 | 2 | 1 | 770 | 1.7 mi | 0.436 | RentDigs.com |
| `5121923737` | $1,495 | 2 | 1 | 1,100 | 1.7 mi | 0.431 | RentDigs.com |
| `5121796945` | $1,990 | 2 | 2 | 1,025 | 0.9 mi | 0.416 | RentDigs.com |
| `5121869337` | $2,144 | 2 | 2 | 1,046 | 0.5 mi | 0.397 | RentDigs.com |

**Source concentration:** 7 of 8 comparables come from one feed (`RentDigs.com`) across 2 sources total.

**Location precision:** 7 of 8 comparables are positioned at a city-area coordinate rather than a street address; their distances are approximate.

---

*Generated by the multi-family deal evaluator · run started 2026-09-02 10:03 · planner invocations 1 · rework passes 0*
