# Deal Evaluation — 1425 W Sunset Blvd, Los Angeles, CA 90026

> **Recommendation — Proceed.** The asking price is in line with the typical sale price for this area, which is within the ordinary range for recorded sales across this metro area.
>
> ✅ **System check — reported.** The figures below cleared the system's own checks without needing a human to release them.

## Summary

The property at 1425 W Sunset Blvd in Los Angeles is a two‑unit residential building with an asking price of $1,049,000 and an estimated rent of $2,861 per unit per month. The report recommends proceeding with the investment because the price falls within the typical range for comparable sales in the area. The system’s automated checks were cleared without any human review. Four informational disclosures were raised.

**Confidence:** 1.00 (escalation threshold 0.60) · **Disclosures:** 4 · **Comparables:** 8

## Disclosures — 4 (4 informational)

4 disclosure(s) were raised during this evaluation. Each is listed in full below, grouped by whether it describes this property or the data available for its market, and ordered most severe first within each. Entries that describe a mechanism rather than a weakness are collapsed; anything that qualifies a number below is open.

### About this property (4)

*Specific to this listing or this run — some of these may be resolvable.*

**Disclosure (4)** — a mechanism used, disclosed for transparency; not a weakness

<details>
<summary><b><code>rent_anchored_to_market_index</code></b> — Estimated rent of $2,861/mo is a modelled ratio of 1.06 applied to a reference rent of $2,691 for ZIP 90026, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes</summary>

Estimated rent of $2,861/mo is a modelled ratio of 1.06 applied to a reference rent of $2,691 for ZIP 90026, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes. It is not an observed rent for this building. The ratio comes from a model trained on 2018-19 listings normalized against the same index at their own listing months, so what it carries forward is how this property compares to its neighbors rather than what anything cost in 2019.

*raised by:* `valuation_rent`
</details>

<details>
<summary><b><code>appreciation_source</code></b> — Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the Los Angeles metro, over 52 year-over-year observations</summary>

Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the Los Angeles metro, over 52 year-over-year observations. This project has one appreciation series: the ZIP-level tier was closed on sample size (median 2 sales per ZIP-period) and no all-residential extract exists here, so there is no fallback below this one.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>rent_growth_source</code></b> — Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Los Angeles County, CA, a median across the 254 postal codes it covers over 55 year-over-year observations from 2019-01 to 2026-07</summary>

Rent growth is projected from Zillow Observed Rent Index, county-level monthly median across all unit types at Los Angeles County, CA, a median across the 254 postal codes it covers over 55 year-over-year observations from 2019-01 to 2026-07. Note the difference in geography from the rent estimate itself, which is anchored at this property's own postal code: a single postal code's rent index either does not reach back far enough to measure a five-year trend or does not exist at all, so the trend is measured across the surrounding county and the estimate is not.

*raised by:* `scenario_forecast`
</details>

<details>
<summary><b><code>forecast_branches_near_tied</code></b> — The last scenario pairing to make the table and the best one left out of it were separated by less than 0.05, which this system treats as no meaningful difference</summary>

The last scenario pairing to make the table and the best one left out of it were separated by less than 0.05, which this system treats as no meaningful difference. This line matters in a way a tie between two reported scenarios does not: it decides which pairings are shown at all, so the set of scenarios below could as defensibly have been a different set. The pairing that missed it is listed in the search ledger with its own score and the reason it was dropped. As with every score here, it comes from a single model call whose repeat runs measurably vary.

*raised by:* `scenario_forecast`
</details>


## Findings

| Metric | Value | Basis |
| --- | --- | --- |
| Asking price | $1,049,000 | listing |
| Units | 2 | listing |
| Estimated rent | $2,861/mo per unit ± $452 overall, ± $509 in Los Angeles | regression_model, ratio 1.06 × market rent $2,691 (ZIP 90026) as of 2026-07 |
| Estimated value | not produced | no property-level sale data exists in this project's sources; see the market benchmark below |

### Market benchmark

Typical **Multi-Family (2-4 unit)** sale in the Los Angeles metro: **$1,047,955**, the median over the last 3 monthly periods (~311 sales per period, Redfin).
This listing asks $1,049,000 — **0% above** that benchmark.

*This build has neighborhood sale records for Chicago and New York only, and ZIP 90026 is not among them — so the figure shown is the metro-wide one. Los Angeles County publishes assessed values rather than sale prices, which are a different measure and are not substituted here.*

> **This is not an estimate of this property's value.** The source is pre-aggregated to one median per metro per month and exposes no individual sales, so it carries no square footage, unit count or condition — the same figure describes every 2-4 unit property in the metro. It is a market reference for reading the asking price against, and nothing more.

### How the rent figure was reached

A gradient-boosted tree model over bedrooms, bathrooms and square footage, fit to 5,701 listings, trained Aug 30, 2026. Every listing was scored by a version of the model that had not been shown it, and on that basis it missed by **$452/mo on average** (0.269 in ratio terms). That is the error band on the figure above, and it is wide.

That figure is the model's error averaged across every market it was trained on. In **Los Angeles** specifically, the same measurement missed by **$509/mo** (n=2372 listings) — in line with the figure above.

**Cross-check against the comps:** 8 of 8 retrieved comps normalized cleanly to their own area and fiscal year, 8 of them at ZIP resolution, implying **$2,875/mo** (middle half $2,773–$3,872). The model sits 1% below that.

### The listing's stated rents

The listing states $2,850 and $2,950 per month across 2 units — an average of **$2,900** per unit, **$5,800/mo** in total.

This system estimates **$2,861/mo** for a 2-bedroom unit, or **$5,722/mo** across 2 units. The stated rents sit **1% above** that estimate.

> **Stated rents above the estimate are worth verifying against leases rather than taken from the listing.** The estimate describes a unit of this size and configuration in this ZIP code; rents materially above it usually have an explanation the listing has not given — short-term or furnished tenancies, rents including utilities or parking, or figures that are asking rather than collected.

### Scenarios — 5-year outlook

#### What each series has done

Measured ranges, one per quantity, each labelled for its own band rather than for a combined outcome. Given a stretch of history these figures are arithmetic and do not move between runs — but *which* stretch of history is a judgment, and this run made it one way (2020–2022 held out of both); the reasoning behind it is shown under **Step 1** below.

| | Weakest sustained stretch | Long-run average | Strongest sustained stretch | Measured over |
| --- | --- | --- | --- | --- |
| **Monthly rent** | +1.25%/yr | +2.51%/yr | +4.76%/yr | 55 year-over-year observations |
| **Sale price** | -0.80%/yr | +2.10%/yr | +4.50%/yr | 52 year-over-year observations |

Projected from modelled rent $2,861/mo and the **asking price** $1,049,000. The price side compounds the asking price rather than an estimated value — this system does not produce one, and says so above.

Each row is named for the combination it describes, and the bands beside each figure are the same ones in the table above. **Rows are ordered worst to best by combined outcome**, so the central case is not necessarily in the middle. Rent and price are paired here rather than forecast independently, and this project has measured how the two move together: weakly, and not in a consistent direction. Read each row as one internally consistent story about this market, not as evidence that rent and price tend to move that way.

| Scenario | Rent growth | Price growth | Rent in yr 5 | Price in yr 5 | Why this row is shown |
| --- | --- | --- | --- | --- | --- |
| **Prices fall, rents hold** | +2.51%/yr (long-run average) | -0.80%/yr (weakest stretch) | $3,239 | $1,007,894 | **0.85** — level with 3 other pairings, kept as the more cautious |
| **Rents stall, prices hold** | +1.25%/yr (weakest stretch) | +2.10%/yr (long-run average) | $3,045 | $1,164,118 | **0.85** — level with 3 other pairings, kept as the more cautious |
| **Central case** | +2.51%/yr (long-run average) | +2.10%/yr (long-run average) | $3,239 | $1,164,118 | **0.96** — outscored the pairings left out |

**Not represented above:** the strongest stretch for rent and the strongest stretch for sale price. Every band is measured and printed in the table at the top of this section; what the rows show is which *combinations* the search judged worth reporting, and a band reaching no row means it did not survive that judgment in any pairing. The bottom row is therefore the best case among those reported, not the best case measured.

- **Prices fall, rents hold** — Base rent growth is paired with a pessimistic price projection that rests on low‑end historical data with adequate observations.
- **Rents stall, prices hold** — The pessimistic rent estimate is paired with a central price trend that is well supported by 52 monthly observations.
- **Central case** — Both rent and price use central historical growth rates that are directly observed and therefore most robustly founded.

The score in the last column is how well the forecast search judged that combination to be supported by the evidence it was given, from 0 to 1 — shown because a scenario the system itself rated weakly should be read as one. Two cautions: a score says how well evidenced a combination is, not how likely it is, so a higher-scoring row is not a more probable outcome; and the scores come from a single model call whose repeat runs measurably vary, so small differences between them are not reliable — which is why a row kept on the tie-break says so rather than reporting the gap.

#### How these bands were built

**Rent** — Zillow Observed Rent Index, county-level monthly median across all unit types for Los Angeles County, CA, a median across the 254 postal codes within it, covering 2019-01 to 2026-07 (55 year-over-year observations). The outer bands are the worst and best twelve-month stretches the index actually held, not its worst and best single months; the base case is the average across every month kept.
  This is measured across the county, while the rent estimate above is anchored to this property's own postal code. A single postal code's rent index generally does not reach back far enough to measure a five-year trend, so the trend is read at the wider geography and the estimate is not.
  2020–2022 excluded — the same treatment question asked of the sale-price series below, so the two describe the same span of history.

**Price** — Redfin metro-level Multi-Family (2–4 unit) median sale price for Los Angeles, 52 year-over-year observations, 2020–2022 excluded.

#### How the forecast search reasoned

13 hypotheses were evaluated and 9 discarded, across two questions asked in order. Pruning is recorded rather than silent: an evaluator that quietly drops a correct-but-unusual branch looks identical to one working properly.

**Step 1 — which reading of the history should every band be built from?**  
*4 considered, 1 kept.*

- **`f-11` (0.95) — Excludes the 2020‑2022 anomalous period from both series, preserving the most representative sample size and aligning with the documented exclusion of that period. ← carried forward**
- `f-01` (0.70) — Rent retains the anomalous period while price excludes it, creating an asymmetric treatment that may overstate rent growth relative to price. **Discarded:** Scored 0.70, outside the top 1 at this level.
- `f-10` (0.55) — Price retains the anomalous period while rent excludes it, leading to an asymmetric treatment that likely overstates price growth and is less consistent with the evidence of anomalous period exclusion. **Discarded:** Scored 0.55, outside the top 1 at this level.
- `f-00` (0.30) — Includes the 2020‑2022 anomalous period for both rent and price, which inflates growth estimates and does not reflect the typical market conditions the model aims to capture. **Discarded:** Scored 0.30, outside the top 1 at this level.

**Step 2 — which combinations of those bands are worth showing?**  
*9 considered, 3 kept.*

- **`f-11-basebase` (0.96) — Both rent and price use central historical growth rates that are directly observed and therefore most robustly founded. ← carried forward**
- **`f-11-basepess` (0.85) — Base rent growth is paired with a pessimistic price projection that rests on low‑end historical data with adequate observations. ← carried forward**
- **`f-11-pessbase` (0.85) — The pessimistic rent estimate is paired with a central price trend that is well supported by 52 monthly observations. ← carried forward**
- `f-11-optibase` (0.80) — Optimistic rent growth is paired with a central price trend that is well documented across many monthly data points. **Discarded:** Scored 0.80, level with the last one kept — too close for this system to call a difference — so it was this system's standing preference for the more cautious reading, not the score, that left this one out.
- `f-11-baseopti` (0.80) — Base rent growth is combined with an optimistic price projection that is observed but not sustained over a long period. **Discarded:** Scored 0.80, level with the last one kept — too close for this system to call a difference — so it was this system's standing preference for the more cautious reading, not the score, that left this one out.
- `f-11-pesspess` (0.78) — Pessimistic rent and price growth are both derived from low‑end historical extremes with solid observation counts, making this pair reliably low‑end. **Discarded:** Scored 0.78, outside the top 3 at this level.
- `f-11-optiopti` (0.75) — Both rent and price use optimistic growth rates that reflect high‑end historical values but are not consistently sustained. **Discarded:** Scored 0.75, outside the top 3 at this level.
- `f-11-optipess` (0.70) — An optimistic rent growth estimate is paired with a pessimistic price outlook, both of which are extreme but each has sufficient observation backing. **Discarded:** Scored 0.70, outside the top 3 at this level.
- `f-11-pessopti` (0.70) — Pessimistic rent growth is combined with an optimistic price outlook that, while based on observed high values, lacks a sustained stretch. **Discarded:** Scored 0.70, outside the top 3 at this level.

*The scores and the wording above come from one model call, and repeat calls on identical input have been measured moving materially. Read this as a sample of the reasoning rather than a stable ranking — small differences between scores are not reliable. The bands themselves are arithmetic and do not move.*

## Comparable Rentals

8 comparable listing(s) retrieved within 2.0 miles after 1 retrieval pass(es).

| Listing ID | Rent | Beds | Baths | Sq Ft | Distance | Similarity | Source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `5508712149` | $2,774 | 2 | 2 | 979 | 1.6 mi | 0.742 | RentDigs.com |
| `5508704042` | $2,655 | 2 | 2 | 979 | 1.6 mi | 0.733 | RentDigs.com |
| `5508708763` | $2,940 | 2 | 2 | 1,160 | 1.6 mi | 0.725 | RentDigs.com |
| `5508753767` | $2,295 | 2 | 1 | 730 | 0.6 mi | 0.710 | RentDigs.com |
| `5198620546` | $3,532 | 2 | 2 | 1,033 | 1.2 mi | 0.707 | RentDigs.com |
| `5198622109` | $4,000 | 2 | 2 | 1,128 | 1.2 mi | 0.685 | RentDigs.com |
| `5508715886` | $3,795 | 2 | 2 | 1,135 | 1.6 mi | 0.676 | RentDigs.com |
| `5508754131` | $2,350 | 2 | 2 | 800 | 0.6 mi | 0.672 | RentDigs.com |

**Source concentration:** all 8 comparables come from a single feed (`RentDigs.com`). They are less independent than the count suggests.

**Location precision:** none of these 8 comparables carries a street address in the source data; each is positioned at a city-area coordinate. Distances are approximate and should be read as *within this market*, not as measured separations.

---

*Generated by the multi-family deal evaluator · run started 2026-09-02 02:05 · planner invocations 1 · rework passes 0*
