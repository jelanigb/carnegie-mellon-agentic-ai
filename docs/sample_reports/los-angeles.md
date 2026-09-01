# Deal Evaluation — 1425 W Sunset Blvd, Los Angeles, CA 90026

**Confidence:** 1.00 (escalation threshold 0.60) · **Disclosures:** 3 · **Comparables:** 8

## Disclosures

3 disclosure(s) were raised during this evaluation. Each is listed in full below, grouped by whether it describes this property or the data available for its market, and ordered most severe first within each.

### About this property (3)

*Specific to this listing or this run — some of these may be resolvable.*

**Disclosure (3)** — a mechanism used, disclosed for transparency; not a weakness

- **`rent_anchored_to_market_index`** — Estimated rent of $2,861/mo is a modelled ratio of 1.06 applied to a reference rent of $2,691 for ZIP 90026, read from Zillow's published rent index for 2026-07-31 and stepped to 2 bedrooms using the federal rent schedule's own ratio between unit sizes. It is not an observed rent for this building. The ratio comes from a model trained on 2018-19 listings normalized against the same index at their own listing months, so what it carries forward is how this property compares to its neighbors rather than what anything cost in 2019.
  *raised by:* `valuation_rent`
- **`appreciation_source`** — Price appreciation is projected from Redfin metro-level Multi-Family (2-4 units) median sale price for the Los Angeles metro, over 52 year-over-year observations. This project has one appreciation series: the ZIP-level tier was closed on sample size (median 2 sales per ZIP-period) and no all-residential extract exists here, so there is no fallback below this one.
  *raised by:* `scenario_forecast`
- **`forecast_branches_near_tied`** — The two best-scoring scenario pairings were separated by 0.050, inside the 0.05 tie threshold — the evaluator found both equally defensible. Both appear in the scenario table below, and each scenario's label comes from its projected outcome, so no reported figure depends on which of the two nominally ranked first. A tie here is common and often correct: two pairings that mirror each other are equally consistent with the opposite-direction relationship between rent and price growth this project measured. The scores also come from a single model call whose repeat runs measurably vary, so a gap this small can be a property of this one sample.
  *raised by:* `scenario_forecast`

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

Projected from modelled rent $2,861/mo and the **asking price** $1,049,000. The price side compounds the asking price rather than an estimated value — this system does not produce one, and says so above.

Scenarios are named for their **combined** outcome across both quantities. Because rent growth and price growth are negatively correlated in this project's data, a single column need not fall in label order — the pessimistic case can carry the higher projected price and still be the worse outcome overall. Each row states which band it drew from on each side.

| Scenario | Rent growth | Price growth | Rent in yr 5 | Price in yr 5 |
| --- | --- | --- | --- | --- |
| **Pessimistic** | -0.68%/yr (pessimistic) | +4.50%/yr (optimistic) | $2,765 | $1,307,246 |
| **Base** | +7.26%/yr (base) | -0.80%/yr (pessimistic) | $4,062 | $1,007,894 |
| **Optimistic** | +14.49%/yr (optimistic) | -0.80%/yr (pessimistic) | $5,628 | $1,007,894 |

- **Pessimistic** *(scored 0.85)* — A pessimistic rent outlook combined with an optimistic price growth assumption aligns with the historically negative correlation between rent and price trends.
- **Base** *(scored 0.80)* — Base rent growth paired with a pessimistic price projection reflects the opposite‑direction movement typical of the market.
- **Optimistic** *(scored 0.85)* — Optimistic rent growth alongside a pessimistic price outlook mirrors the expected opposite dynamics in the market.

Each score is how well the forecast search judged that hypothesis to be supported by the evidence it was given, from 0 to 1 — shown because a scenario the system itself rated weakly should be read as one. Two cautions: the scenario names above come from each row's projected outcome and not from these scores, so a higher-scoring row is not a more likely one; and the scores come from a single model call whose repeat runs measurably vary, so small differences between them are not reliable.

#### How these bands were built

**Rent** — HUD Fair Market Rent history for Los Angeles-Long Beach-Glendale, CA HUD Metro FMR Area, 2-bedroom, at county resolution over FY2018–2026 (9 year-over-year observations). The bands are the worst and best fiscal years observed (FY2022 and FY2024); the base case is their compound average.
  Interquartile range of those annual changes: 5.21% to 9.21% — shown so an extreme band that rests on an isolated year is visible as one.

**Price** — Redfin metro-level Multi-Family (2–4 unit) median sale price for Los Angeles, 52 year-over-year observations, 2020–2022 excluded.

#### What the forecast search considered

13 hypotheses were evaluated and 9 discarded. Pruning is recorded rather than silent: an evaluator that quietly drops a correct-but-unusual branch looks identical to one working properly.

- `f-11` (0.80) — Pairs a moderate rent growth with low price growth, consistent with the negative correlation, but relies on a smaller rent sample, making it less robust than f-01. **Discarded:** Scored 0.80, outside the top 1 at this level.
- `f-00` (0.30) — Pairs a high rent growth rate with a similarly high price appreciation rate, which conflicts with the observed negative correlation between rent and price growth in Los Angeles, making it the least defensible. **Discarded:** Scored 0.30, outside the top 1 at this level.
- `f-10` (0.20) — Uses a reduced rent sample and pairs a moderate‑high rent growth with high price growth, again contradicting the negative correlation, placing it near the bottom of defensibility. **Discarded:** Scored 0.20, outside the top 1 at this level.
- `f-01-pesspess` (0.25) — Both rent and price growth are projected to decline, a combination that is statistically rare given their negative correlation in Los Angeles. **Discarded:** Scored 0.25, below the 0.40 threshold this project requires before a hypothesis is carried forward.
- `f-01-optiopti` (0.20) — Both rent and price are projected to rise sharply, a simultaneous extreme that is uncommon given their negative correlation. **Discarded:** Scored 0.20, below the 0.40 threshold this project requires before a hypothesis is carried forward.
- `f-01-basebase` (0.70) — Both rent and price are forecast at their average historical rates, representing a neutral scenario with limited evidence of extremity. **Discarded:** Scored 0.70, outside the top 3 at this level.
- `f-01-baseopti` (0.65) — Base rent growth combined with an optimistic price increase is moderately consistent with the inverse relationship observed. **Discarded:** Scored 0.65, outside the top 3 at this level.
- `f-01-pessbase` (0.55) — Pessimistic rent growth is paired with a moderate price appreciation rate, which is plausible but not strongly supported by the observed inverse relationship. **Discarded:** Scored 0.55, outside the top 3 at this level.
- `f-01-optibase` (0.60) — Optimistic rent growth paired with a base price appreciation rate is plausible but less directly supported by the correlation pattern. **Discarded:** Scored 0.60, outside the top 3 at this level.

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

*Generated by the multi-family deal evaluator · run started 2026-08-31 11:00 · planner invocations 1 · rework passes 0*