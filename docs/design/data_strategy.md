**§2 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#21) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

> **Looking for which dataset feeds which process?** That is
> [`data_sources.md`](data_sources.md) — a source-by-source map with row counts,
> geographic levels, and exact consumers. **This section is the *argument*: why these
> sources, and what measuring them found.** Where a figure appears in both, the map is
> derived from the code and is the one to trust.

Two problems surfaced while planning the data layer, and both are resolved the same way:
ground every dollar figure in a *dated, purpose-matched* source rather than trusting a
single dataset to do more than it can.

### Provenance and licence of the rent corpus

Recorded Aug 22, 2026 — a gap rather than a change. §8's data rule turns on whether a
source is *openly licensed or a public record*, naming scraped listings as the case the
distinction exists for, and this project's primary dataset had no licence recorded
anywhere.

The corpus is **UCI Machine Learning Repository dataset #555, "Apartment for Rent
Classified"** (donated 25 Dec 2019, DOI [10.24432/C5X623](https://doi.org/10.24432/C5X623)),
licensed **CC BY 4.0**. It is therefore admissible under the first branch of the rule —
openly licensed — rather than needing an exception. The listings within it originated on
classified sites (`source` values include RentDigs.com and RentLingo), but the compilation
this project consumes is a licensed research dataset, and no scraping is performed here.

CC BY requires attribution, which is why the citation above is stated rather than left
implicit.

### Problem 1 — the Kaggle rent data has no reliable current date

The Kaggle apartment dataset is a single historical scrape (~2017–2019). Any rent
estimate trained directly on it is calibrated to that era's price level, not today's.
Left uncorrected, a "$1,450/month" prediction is a 2018 number in a 2026 costume, and
every downstream valuation and scenario built on it inherits that bias.

### Problem 2 — Redfin measures price, not rent

Redfin's data (Housing Market Tracker, RHPI) tracks home *sale* prices. Home price
appreciation and rent growth diverge meaningfully over multi-year windows — most
visibly 2020–2022, when price growth far outpaced rent growth as low rates pulled
buyers in. Using Redfin's price trend to adjust a *rent* number would import
interest-rate-driven price dynamics into a quantity they don't actually explain.

**Measured Aug 22, 2026, and it is worse than "weak" — the relationship is inverted.**
This section asserted the divergence from housing-market reasoning rather than from this
project's own data. Tested against it, using HUD FMR's published history as the rent
series and the Redfin extract as the price series, both annualized across the inference
trio for FY2019–FY2026:

| | Correlation of rent growth with price growth |
| --- | --- |
| Pooled, 24 metro-years | **r = −0.309** |
| Chicago | −0.135 |
| Los Angeles | −0.226 |
| Cleveland | −0.530 |

Negative in all three metros independently. A rent forecast driven by a price series
would not merely be imprecise — it would point **the wrong way**. And the mechanism is
the one predicted above: across 2021–22, price grew **+11.7%** while rent grew **+2.8%**,
an 8.9-point gap in exactly the low-rate window this section names.

*Caveats, because the sample is small.* Eight annual observations per metro is thin and
growth-rate correlations are noisy, so the coefficient itself should not be defended. The
*direction* is consistent across three independent markets with a documented mechanism,
which is what makes it more than an artifact. Reproduce with the FMR client's historical
years against `tools/redfin_data.load_redfin`.

**Consequence for U6.** §1 specifies the Scenario/Forecast agent as *"Tree-of-Thought
reasoning over rent-growth/appreciation scenarios, informed by metro-level housing trend
data,"* and `agents/scenario_forecast.py` inherited that wording. **The rent half of that
premise does not survive this measurement.** Redfin stays the source for *price*
appreciation, which is what it measures; rent growth needs a rent-native series. See
[`data_sources.md`](data_sources.md) — HUD FMR publishes ten years of history through the
client this project already uses, at county and ZIP resolution, which makes it the
candidate that costs nothing new and stays consistent with the anchoring design.

### Resolution: separate "structure" from "level," and match each quantity to a same-kind source

**Rent-level anchoring (Valuation & Rent agent):**

1. Train the regression on rent *normalized by that row's local HUD FMR at the time it
   was recorded* (rent ÷ FMR-for-that-county-and-year), not raw dollars. The model
   learns a structural relationship — "this bed/bath/sqft/amenity combination rents at
   ~1.15× the local FMR" — that ages far more slowly than a dollar figure.
2. At prediction time, multiply the model's output ratio by *today's* HUD FMR for the
   subject property's county. This produces a current-dollar estimate anchored to a
   real, dated reference point instead of an implicit 2018 price level.
3. Flag every estimate that used this anchoring path (`kind="rent_anchored_to_market_index"`,
   `severity="info"`) so the report can disclose the mechanism, and flag separately
   (`kind="rent_anchor_unavailable"`) when the subject county will not resolve.

   **Revised at implementation (U5, Aug 22, 2026): that second flag is `critical`, not
   `warn`, and there is no coarser fallback.** As written above it assumed a
   state/national FMR could stand in, which would have made the flag mean "this figure
   is less precise." It cannot: a state-level FMR is not a rent this property could
   command, and the nearest available substitute — a mean of the retrieved comps — is
   precisely the unanchored 2019 dollar figure §8 forbids reaching the Summarizer. So
   the path produces **no rent figure at all**, and the severity follows the
   consequence. `SPARSE_COMPS` already sets that precedent, being `critical` at zero
   comps and `warn` otherwise.

**Appreciation forecasting (Scenario/Forecast agent):**

- Use the Housing Market Tracker filtered to `property_type = Multi-Family (2-4 Unit)`
  as the appreciation/trend series — this matches the asset class directly rather than
  relying on a blended series dominated by single-family transaction volume. Small
  multi-family is bought by a different buyer pool (investors pricing off cap rates)
  than single-family (owner-occupants), so an asset-matched trend line is a real
  accuracy improvement, not just a nice-to-have.
- Redfin Home Price Index (RHPI) is **not used** — it covers single-family homes only
  and has no multi-family series, so it can't substitute or supplement here.
- **Geographic level: metro is the primary tier, not ZIP.** Redfin's `REGION TYPE`
  offers ZIP, metro, and other levels directly (no manual ZIP→county rollup needed).
  For the target inference metros (**Chicago, Los Angeles, Cleveland** — see the metro
  selection subsection below), metro-level `HOMES SOLD` medians are 362 / 302 / 149 per
  period, versus ZIP-level counts that are frequently single digits with wild YoY swings
  from small denominators. Metro-level is directionally what the Scenario/Forecast agent needs
  (bands for optimistic/base/pessimistic), not sub-market precision, so the added
  stability outweighs the lost granularity. Revised three-tier design, with the tier
  used flagged (`kind="appreciation_source"`, `severity="info"` for tiers 1–2,
  `"warn"` for tier 3):

  > **Built at U6 (Aug 24, 2026): the ladder has one rung, and the type that described it
  > was removed.** Tier 2 is closed on the sample-size evidence this very paragraph gives
  > (median 2 homes sold per ZIP-period). Tier 3 needs an all-residential Redfin extract
  > that does not exist in this project — and §2's own asset-match argument says a 2–4
  > unit forecast should not fall back onto single-family dynamics even if it did. Since
  > tier 1's series never goes thin (minimum 81 sales/month across 102 periods in the
  > sparsest metro), the fallback would never fire. `appreciation_source` now carries a
  > description of the series rather than a tier label; see §7 decision #17.
  1. **Metro-level, multi-family filtered (default for the project).** Adequate
     sample for any of the target metros; this is the only tier required for the
     pipeline to work end-to-end.
  2. **ZIP-level, multi-family filtered (deferred / stretch goal).** Would apply only
     when the subject ZIP clears a minimum-sample gate (e.g. `HOMES SOLD` ≥ ~8–10 for
     the period). Not built in the current phase — the ZIP extract already pulled
     shows single-digit sample counts and YoY swings in the thousands of percent even
     within a large metro (NY), so this tier would clear its own usability gate rarely
     enough that it isn't worth building alongside the core pipeline. Documented as
     future work, the same way cross-deal episodic memory was deferred in Checkpoint
     2.1 — real, but not blocking.
  3. **Metro-level, all-residential, unfiltered (fallback).** For the rare case where
     even metro-level multi-family volume is too thin — unlikely for the target metros
     but kept for robustness against edge cases or future metro additions.
- **Use a consistent period frequency — rolling 3-month, not single-month.** Rolling
  3-month windows smooth out the single-month sample-size noise seen even at metro level
  for smaller markets, and consistency matters more than granularity here since the
  pipeline compares periods to each other. *(Implementation note, Aug 8: the extract on
  disk is `Monthly`. Compute the rolling window in `tools/redfin_data.py` rather than
  re-downloading — see "Two data gaps" below.)*
- **Apply a minimum-price floor before any sample-size logic runs.** Raw extracts
  contain implausible `MEDIAN SALE PRICE NSA ($)` values ($1, $101, $500) —
  near-certainly non-arm's-length transfers (quitclaim deeds, corrective deeds,
  nominal-consideration transfers) rather than real market sales.

  **Resolved to $10,000, the low end of the range originally proposed** (verified
  Aug 8, 2026 across 58,863 non-null price rows). Evidence: 63 rows (0.107%) fall below
  $10k and **90.5% of those report `HOMES SOLD == 1`** — the signature of a single
  non-market transfer. Raising the floor to $20k would drop 294 rows (0.499%) instead,
  and in the $10–20k band the single-sale share falls to 72.7% while metros such as
  Weirton WV show a *sustained* cheap tail across many periods — real distressed
  activity. A $20k floor would delete observations rather than clean them.

  **Honest scope note: this floor is inert for all three inference metros.** Their
  minimum median sale prices are Chicago $207,500, LA $695,000, and Cleveland $58,333 —
  between 6× and 70× any candidate floor, so zero periods are dropped for any of them.
  The floor is genuine insurance for the tier-3 all-residential fallback and for any
  future metro addition, but it does not change a single number in the current
  pipeline, and this section previously implied otherwise.
- **Pull roughly 2018–present**, not just the last year or two. This window is sized
  for the Scenario/Forecast agent's own needs — real historical variance to ground its
  optimistic/base/pessimistic branches (e.g. base = long-run average growth, optimistic
  = best sustained stretch observed, pessimistic = worst) — and is **independent of
  Kaggle's ~2017–2019 vintage**; the two datasets don't need matching date ranges,
  since HUD FMR is what bridges Kaggle's vintage to today (see rent-level anchoring
  above), not Redfin's date range. 2018–present just needs to capture a pre-COVID
  baseline alongside the anomalous period, rather than only the anomaly; reaching back
  to Kaggle's exact start year isn't required.
- **Flag the 2020–2022 window explicitly wherever it feeds an average or scenario
  band** (`kind="anomalous_period_included"`, `severity="info"`). Near-zero interest
  rates pulled price growth well above trend during this stretch; blending it in
  silently risks skewing "base case" toward an unusual few years rather than normal
  market behavior. Flagging it keeps the choice visible and defensible either way.

  **Excluding that window creates a discontinuity, not merely a filter** (found while
  building `tools/redfin_data.py`). Dropping 2020–2022 leaves a gap in the series, and
  a naive `.rolling()` splices across it — silently averaging 2019 onto 2023 and
  reporting the result as a run of consecutive months. The sustained-stretch
  calculation therefore segments on month adjacency before averaging. This was a live
  defect rather than a hypothetical: fixing it moved Chicago's excluded pessimistic
  band from −1.92% to −1.56%. Any future work that filters periods out of these series
  must handle the resulting gap explicitly.
- Redfin data is never used to adjust rent dollars — only price/appreciation.
- Filter to the target metros immediately on load — Redfin data is only used for
  per-deal inference lookups (never for training), so it only ever needs to cover the
  2–3 inference metros, not a national pull.

**Out of scope for now:** Investor Home Purchases and Existing Home Sales datasets —
no clear role in the current agent design; documented as potential future enrichment
(e.g., a market-competitiveness signal) rather than built now.

### Training vs. Inference: different data requirements

These two scopes fail for different reasons, and conflating them leads to solving the
wrong problem. Stated explicitly because the distinction determines how the New York
coverage gap is handled (below):

- **Training** needs *volume and feature diversity across many markets*, because the
  regression learns a structural relationship (rent as a ratio to local FMR) that
  should generalize. It does not care whether any single market is densely covered.
- **Inference** needs *comp density in the specific subject market*, because comps must
  be geographically near the subject property to be meaningful. A national corpus does
  not help price a building in a market the corpus barely covers.

**Verified sufficiency of the training data (Aug 8, 2026; counts corrected Aug 22,
2026).** The Kaggle extract holds 99,492 rows, of which **98,923 (99.4%) are complete on
every core feature** — price, bedrooms, bathrooms, square_feet, latitude, longitude,
cityname, state — and **98,844** survive the rent bounds as well. Notably `square_feet`
has **zero** missing values, which removes the most likely blocker for a sqft-aware comp
match and regression.

> **⚠️ The training-set size originally stated here was wrong, and this is the most
> misread number in the project.** This paragraph claimed a candidate ~10-metro shortlist
> yields **21,768 complete rows**. It does not, and no metro-filtered count reproduces
> it: 21,768 is a *state-level* rollup — the six states the shortlist's metros sit in hold
> 22,323 usable rows between them, which is what that figure was actually counting.
>
> **The real training-set size is 5,717 rows** (of which 4,550 are trained on and 1,138
> held out), re-derived against the settled eight-metro shortlist and reproducible with
> `.venv/bin/python scripts/train_rent_model.py --dry-run`. Per §8, a training-set size
> nobody measured is not a measurement.
>
> The correction is stated here, at the point the wrong number appeared, rather than only
> in §7 and `config.py` where it was first recorded — because this section is titled
> *Data Strategy* and *Training vs. Inference*, so it is where anyone looking for the
> training row count will look first. See [`data_sources.md`](data_sources.md) for the
> full source-by-source map.

Price distribution is sane (median $1,350; IQR $1,014–$1,795) with negligible outlier
contamination — 8 rows below $300 and 71 above $10,000, removable by the same
min/max filter pattern §2 already applies to the Redfin extract.

**Conclusion: row count is not a binding constraint on training, and never was.** That
conclusion survives the correction above — 5,717 rows is still ample for a regression on
three features, and the eight-metro shortlist was selected on per-metro density rather
than on the aggregate. The
binding constraint was the county/FIPS mapping and FMR-pull effort per added metro,
exactly as this section originally predicted. Adding a metro to the training set cost
crosswalk entries and API calls, not data.

**Partly superseded Aug 15, 2026.** The county/FIPS half of that constraint is gone —
`tools/county_crosswalk.py`'s rewrite (decision #10 follow-on, §7) resolves county from
a row's own coordinates via geometry, not a hand-maintained per-city table, so adding a
metro no longer costs crosswalk entries at all. FMR-pull effort per distinct county is
still real (still bounded by county count, not row count, and still cached by
`tools/hud_fmr.py`), so it isn't zero — but the *cleaning* effort called out in the next
section (word-boundary city-name matching per metro in `tools/kaggle_data.py`) is now
the larger of the two remaining costs, where it used to be roughly comparable to the
crosswalk-curation cost.

### Metro Scope: Training vs. Inference

Two different scopes are needed, and they shouldn't be the same size:

- **Inference/demo scope: 2–3 metros.** Kept small deliberately — enough to show the
  system working on genuinely different markets without turning metro selection into
  its own research project. This is the set actual pipeline runs and checkpoint demos
  will use.
- **Training scope: broader than the inference set, but not the full nationwide
  Kaggle dataset.** The regression predicts a *ratio to local FMR*, not a raw dollar
  figure, so it benefits from more diverse training data — restricting training to only
  2–3 metros risks overfitting to those markets' specific feature/price relationships.
  At the same time, because the Kaggle dataset is a single-vintage scrape, the HUD FMR
  pull needed to normalize the training target is bounded by *the number of distinct
  counties represented*, not by the number of training rows — so widening the training
  set doesn't meaningfully raise the FMR API cost. The practical constraint was data
  cleaning and county/FIPS mapping effort, not FMR access — as of the Aug 15, 2026
  crosswalk rewrite (§7, decision #10 follow-on), county/FIPS mapping is no longer part
  of that cost at all, since it now resolves from a row's own coordinates rather than a
  hand-curated per-city table; data cleaning (word-boundary city-name matching per
  metro, `tools/kaggle_data.py`) is what remains. A curated shortlist of roughly 5–8
  metros (rather than the full dataset) keeps that cleanup bounded while still giving
  the regression meaningfully more diversity than 2–3 metros alone. The 2–3 inference
  metros should be a subset of this training shortlist, so they're guaranteed adequate
  comp density and a validated data pipeline.
- **Before finalizing metro choices:** run a quick `groupby` count on the Kaggle
  dataset by city/metro to confirm actual listing density — the candidates below are
  based on known housing-stock patterns, not on this dataset's specific coverage, and
  need to be checked against it directly. **Done — see the metro selection subsection
  below; the inference trio is settled and the training shortlist is decision #4 in §7.**

### Metro Selection: hypothesis tested and replaced (Aug 8, 2026)

**The original hypothesis was New York, Chicago, Philadelphia**, reasoned from
housing-stock knowledge: small multi-family (2–4 unit) stock concentrates in the
Northeast and older Midwest/Rust Belt cities plus parts of California — New York's
outer-borough brownstones, Chicago's two-/three-flats, Philadelphia's duplexed
rowhomes, alongside Providence, Cleveland, Milwaukee, Buffalo, Detroit, and Los
Angeles. That reasoning was sound about *housing stock* but said nothing about
*whether the two datasets actually cover those markets*.

The plan called for confirming it with a `groupby` before building. **That check has
now been run against both datasets, and the hypothesis did not survive it.**

Reproduce with `src/scripts/verify_metro_selection.py`. Bars are provisional and stated
in the script: ≥500 Kaggle listings, ≥100 median sales per period. Kaggle counts are
**usable** rows — after de-duplication, completeness filtering, and rent-bound trimming
(`tools/kaggle_data.py`) — since only usable rows can enter the comp index.

| Metro | Kaggle rent listings | Redfin 2–4 unit sales (median/period) | Verdict |
| --- | --- | --- | --- |
| **Los Angeles** | 2,372 | 302 | ✅ passes both |
| Newark / Jersey City | 561 | 746 | ✅ passes both — see note |
| **Chicago** | 631 | 362 | ✅ passes both |
| **Cleveland** | 606 | 149 | ✅ passes both |
| Boston | 599 | 258 | ✅ passes both — viable alternate, see note |
| Cincinnati | 798 | 62 | ❌ sales volume too thin |
| **New York** | 271 (incl. all boroughs) | 746 | ❌ comps too thin |
| Pittsburgh | 248 | 76 | ❌ weak on both |
| **Philadelphia** | 230 | 43 | ❌ weak on both |
| Milwaukee | 98 | 170 | ❌ comps too thin |
| Detroit | 84 | 66 | ❌ weak on both |
| Buffalo | 24 | 118 | ❌ comps too thin |

**Two data defects corrected these counts (Aug 8, 2026).** The first pass reported
slightly higher figures because of two bugs found while building the comp index:
84 exact duplicate `id` rows, and naive substring city matching that counted
*Queensbury* (upstate NY, ~200 miles away) as Queens and *Bronxville* (Westchester) as
the Bronx. Both are fixed in `tools/kaggle_data.py` via de-duplication and
word-boundary matching — the latter still rolls "Cleveland Heights" into Cleveland,
which is correct, while rejecting the two false positives. No verdict changed, but the
episode is why the cleaning logic now lives in one module that every consumer shares
rather than being re-implemented per script.

New York has the highest 2–4 unit transaction volume of any metro in the extract, but
only 271 Kaggle rent listings across all five boroughs — too thin to serve as a
selected inference metro, since comps are the grounding mechanism the whole design
depends on. (That aggregate turned out to understate what is retrievable in practice;
see "Sparsity is a property of sub-locations" below, which measures the difference and
corrects the conclusion originally drawn from this number.) Philadelphia is weak on
both axes and can support neither half of the pipeline.
Milwaukee, Buffalo, and Detroit are classic small-multifamily markets that the
housing-stock reasoning correctly identified but that this particular Kaggle scrape
barely covers — a reminder that corpus coverage and market characteristics are
independent questions.

**Documented alternate — Newark / Jersey City.** This pairing clears both bars (561
listings; it shares the New York CBSA, hence the 746 sales figure) and would offer
New York metro exposure with an adequate comp corpus. **Caveat: the 561 is ~90% Jersey
City** — the actual split is Jersey City 505, Newark 56. If this alternate is ever
activated it is effectively a Jersey City corpus; Newark cannot carry one alone. Essex and Hudson counties are
county-based FMR, so it carries no New England complication. It is not in the selected
trio because Chicago, LA, and Cleveland already provide three structurally different
markets, and because the shared CBSA means its appreciation series would duplicate
New York's rather than add an independent one. Recorded here as a viable substitute if
one of the three proves problematic later.

### Corpus coordinates are city-area placeholders for most rows (Aug 22, 2026)

Found while investigating why U5's rent regression fit so weakly, and it turned out to
be the more consequential of the two findings. **92% of the corpus carries no street
address** (91,027 of 98,844 usable rows), and those rows do not carry a per-property
coordinate either — they carry what is effectively a city-area placeholder.

The evidence is the clustering, not the precision. Coordinates are stored to four
decimals (~11 m), so this is substitution rather than rounding:

| rows | count | rows per distinct coordinate | median cluster |
| --- | --- | --- | --- |
| `address` present | 7,817 | 3.3 | 1 |
| `address` null | 91,027 | 15.0 | 5 |

The clearest single case: Jersey City holds 505 listings at **4** distinct coordinates,
497 of them on one point — a set spanning $1,200–$5,240 and 400–2,750 sq ft, which is
not one building.

**This reaches shipped output.** Running the retrieval path on the three demo subjects,
through real Census geocoding:

| Metro | Comps returned | Distinct locations |
| --- | --- | --- |
| Los Angeles | 8 | 3 |
| Chicago | 5 | 2 |
| **Cleveland** | **8** | **1** |

Cleveland's eight comparables are one point — rents $1,875–$2,329, sq ft 1,005–1,133.
`vector_store.py` was also reporting `distance_miles` to three decimals, i.e. ~1.6 m of
implied precision on a coordinate that does not know where the building is.

**What this does and does not undermine.** It does *not* touch the anti-fabrication
argument: the comps are real records that demonstrably exist, which is what Checkpoint
2.1 claims and what the U4 ablation measured. Nor does it affect FMR normalization,
which needs only city-level accuracy — zero of 5,717 training rows failed county
resolution. What it does undermine is any claim about *spatial* discrimination. The
X=2.0/Y=8/Z=4 parameters were tuned against a distance signal that takes 2–4 values
inside the radius, so the relaxation loop expands against a step function rather than a
density curve. The density table in the next section is measured in *listings*, and
should be read as listings rather than as places.

It also explains U5's weak fit. Rent relative to local FMR is driven substantially by
where a unit is, and location is unavailable here at any useful granularity — which is
a ceiling on the rent model, not a defect in it.

**Handled by disclosure rather than by correction, because correction is not available.**
Each comp now carries `location_precision` (`"address"` / `"area"`), derived from
address presence at index time; `FlagKind.COMPS_SPATIALLY_CONCENTRATED` fires when a
comp set resolves to fewer than `COMP_MIN_DISTINCT_LOCATIONS` places; reported distances
dropped to one decimal; and the report states the composition of every comp set beside
the existing source-concentration line.

`Comp` also gained `latitude`/`longitude` in the same pass, so that place count is
computed from the points themselves rather than inferred from distances — a
distance-keyed count merges two buildings that sit equidistant in opposite directions,
and moves whenever the display precision changes. The coordinates were already being
read from the index to compute each distance and then discarded, so this cost no
re-index. It also unblocks per-comp FMR normalization, which the rent-anchoring
invariant above requires of any comp-derived rent figure.

**The tag is deliberately not used to rank or filter**, and the coverage numbers are why:
Chicago is 42% addressed, Los Angeles 5%, Cleveland 2%. Preferring addressed comps would
empty the Cleveland set entirely. **The signal is also strong rather than clean** — 74
coordinates in the training shortlist carry both addressed and null-address rows (2,390
rows), so an `"address"` tag makes a coordinate probable, not certain. Recorded that way
rather than as a clean partition, since overstating a precision signal is the exact error
the field exists to prevent.

One footnote on method, because it repeats a lesson this section already contains: the
UCI dataset page states *"has Missing Values? No."* It has 92% nulls in `address`. The
metadata was wrong, and the only reason the project knows is that it measured — the same
way the metro-selection hypothesis was overturned in the first place. Earlier in the
process I did not spend enough time on an important CRISP-DM step (Data Understanding),
because I was focused more on the agent harness than on the data. The key learning for
future projects is not to rush that step: skipping it here has forced the approach to be
revised several times in later phases.

### The rent estimate is location-blind below the county (U5, Aug 22, 2026)

The Valuation agent's Observe step re-expresses every retrieved comp's rent in the
subject's current dollars — each comp divided by the FMR for *its own* county and fiscal
year, then multiplied by the subject's current FMR — and compares the modelled rent
against their median. On its first live run the model came in **below** the comp median
in all five subjects tested: 13.0% and 21.6% (Los Angeles), 29.7% and 30.4% (Chicago),
40.0% (Cleveland).

**This section originally concluded that the comp sets were unrepresentative. That was
wrong, and the error is worth keeping rather than deleting**, because it is the same
mistake this document already records twice: reaching a conclusion from a comparison
whose baseline was not checked. The first analysis compared each comp set against its
metro's *entire* 2-bedroom population and found the comps sitting +7.9% / +70.4% /
+73.1% above it — which does look like retrieval selecting expensive listings. But a comp
set is drawn from within a 2–4 mile radius, and comparing a neighborhood against a metro
measures the neighborhood, not the retrieval.

Against the **right** baseline — every corpus row passing the same hard filters at the
same radius — the skew decomposes very differently:

| Metro | Neighborhood effect *(local pool vs. metro)* | Ranking effect *(retrieved vs. local pool)* |
| --- | --- | --- |
| Los Angeles | +5.1% | **+2.7%** |
| Chicago | +40.1% | **+21.6%** |
| Cleveland | +66.2% | **+4.2%** |

Semantic ranking contributes far less than location does in every market measured — and
in Los Angeles and Cleveland, an order of magnitude less. Retrieval's
result also sits at the 58th, 76th and 76th percentile of 500 random eight-comp draws
from the same candidate pool — unremarkable. **Echo Park, Logan Square and Ohio City
genuinely rent above their metro medians, and the comps are reporting that correctly.**

**The real finding is a structural blind spot, and it is on the model side.**
`RENT_MODEL_FEATURES` deliberately excludes any market identifier — a metro dummy would
let the regression memorize a per-market dollar level, defeating the ratio design — so
the FMR anchor is the *only* channel through which location enters a rent estimate. That
anchor is county-level. Nothing in the pipeline can therefore represent sub-metro rent
variation, and `rent_diverges_from_comps` is currently detecting that blind spot rather
than an anomaly. See [`data_sources.md`](data_sources.md), "The sub-metro gap," for what
is available and unused.

### Closed Aug 22, 2026 — ZIP-resolution anchoring

The blind spot was closable with data the project already had. HUD publishes Small Area
FMRs — a schedule per ZIP — for all three inference counties, spanning roughly 2x within
a single county, which is more than enough resolution to cover the neighborhood effects
above. `tools/zcta_crosswalk.py` resolves a coordinate to a ZCTA, and training, the comp
cross-check and inference all anchor through one shared function so they cannot drift
onto different denominators.

**One obstacle was nearly disqualifying and is worth recording, because it is the same
vintage problem this section is about, in a new place.** SAFMR coverage is *younger than
the rent corpus*: Los Angeles publishes 474 ZIP schedules for FY2026 and **zero** for
FY2019; Cuyahoga went 0 → 126. Only Cook had ZIP data in the corpus's own vintage. So
ZIP resolution existed on the inference side and not the training side — and anchoring
the two differently is not an option, because a ratio to a ZIP denominator is a different
quantity from a ratio to a county one.

The fix carries each ZIP's position *within its county* backwards from the current year
and applies it to the row's own year's county FMR. **The dollar level always comes from
the row's own vintage; only the within-county shape is imported.** That assumption is
tested rather than asserted, on the two counties where both years are published:
correlation r = 0.873 (Cook) and 0.771 (Philadelphia), median back-cast error 4.5% and
5.1%. Against a county anchor's blind spot of +40.1% to +66.2%, that is roughly 5% of new
error to remove 40-66% of existing error — and back-cast rows are labelled as such rather
than presented as published figures.

**Result — partial, and the partial-ness is the finding.** Only Cook County had
published ZIP schedules in the corpus's own FY2019 vintage, and only Chicago improved:
−30.4% → **−9.9%**. Los Angeles (−21.6% → −21.0%) and Cleveland (−40.0% → −39.6%) are
anchored at county resolution on both sides and now say so via
`FlagKind.RENT_ANCHOR_COUNTY_LEVEL`.

### Reopened and re-closed Aug 30, 2026 (U11.3) — the anchor is a market index now

**Everything above is the FMR-anchored design, and it was superseded rather than
refined.** The section above closes with a partial result — Chicago improved, Los Angeles
and Cleveland did not, because HUD had published no ZIP schedules in those counties at the
corpus's vintage. That partial-ness was the whole reason to look again.

**What replaced it.** The anchor is now `ZORI at the row's own ZIP and own month × the
HUD schedule's ratio between unit sizes`. Zillow publishes a monthly ZIP-level rent index
covering 5,662 of the corpus's 5,686 ZIPs — so ZIP grain exists in *every* market at the
corpus's own vintage, which is exactly what the SAFMR route could not supply. HUD is kept
only for the bedroom step, whose own level cancels, so the schedule's drift against the
market can no longer reach a rent figure.

**Measured, per metro** (`scripts/anchor_probe.py`, five candidates under one
cross-validation):

| Metro | FMR anchor | Hybrid anchor | |
| --- | --- | --- | --- |
| New York | $981 | **$855** | −13% |
| Chicago | $454 | **$343** | −24% |
| Cleveland | $366 | **$357** | −2% |
| Los Angeles | $450 | $509 | **+13% worse** |
| Overall | $451 | $452 | flat |

**The overall figure is flat and that is not the result.** Los Angeles is 41% of the
training frame, so it drags a headline that hides a 13–24% improvement in the two markets
whose disclosures this work exists to fix. **Chicago is the finding that changes the
reasoning**: it was already 100% ZIP-anchored under FMR, so resolution cannot explain a
24% improvement there. ZORI is simply a better reference series than the administrative
schedule, independent of grain — a broader claim than "close the sub-county gap," and a
stronger argument than the one this section was originally making.

**One hypothesis tested and not supported**, recorded so it is not re-run: Los Angeles is
both the market ZORI makes worse and the one where the county fallback carries the most
weight, so the fallback looked like the culprit. Split by tier, it is not — within Los
Angeles the county tier scores 468 against the ZIP tier's 487. Los Angeles genuinely
prices better against FMR.

**And the blind spot above narrowed without closing.** "The FMR anchor is the only channel
through which location enters, and that anchor is county-level" was literally true in Los
Angeles and New York; it is not any more. What remains is that `RENT_MODEL_FEATURES` still
carries no market identifier, so whatever the anchor fails to absorb is still error the
model structurally cannot recover — now below the *ZIP* rather than below the county.
`rent_diverges_from_comps` should fire less often and mean something narrower when it
does, and the batch confirms it: `chicago-uptown-duplex` measured +46.6% divergence under
FMR and −6.1% under the hybrid, on a listing nothing was bent in.

---

**The back-cast was tried, looked better, and was rejected on measurement.**
Reconstructing ZIP schedules for every county produced convergence across all three
markets (−10.7% / −14.3% / −13.9%), which was briefly taken as success. It was an
artifact: the same reconstructed schedule normalizes both the training rows and the
comps, so a shared error cancels in the comparison while surviving in the estimate — the
same circularity as calibrating a demo price to a benchmark and then reporting agreement
with it. The independent test is whether the anchor explains rent variation at all:

| ZIP schedule source | n | CV county | CV ZIP | Change |
| --- | --- | --- | --- | --- |
| **published** | 1,109 | 44.3% | **35.9%** | **−19.1%** |
| back-cast | 4,281 | 34.0% | 36.2% | +6.6% |

`config.RENT_MODEL_BACKCAST_ZIP_FMR = False`. The relativity it carries back is stable
enough to look reasonable (r = 0.873 Cook / 0.771 Philadelphia, median error ~5%), but
that residual is comparable to the within-county signal it is trying to capture.

Holdout dollar MAE moved $519 → $524 and R² 0.173 → 0.159.

**One confound that limits how far even the corrected reading can be pushed.****One confound that limits how far even the corrected reading can be pushed.**
Cleveland's local pool is 123 rows sitting on **four distinct coordinates, 66% of them on
one**. Its +66.2% "neighborhood effect" is not a verified fact about Ohio City; it is one
city-area placeholder standing in for much of the city. Los Angeles (9 coordinates) and
Chicago (21) are better but still coarse. The coordinate limitation above sets a ceiling
on how precisely any of this can be measured, which is the honest state of it.

Reproduce with `scripts/valuation_evidence.py --diagnose-divergence`.

### What this cost, and the process lesson

The revisions this refers to are all recorded in this section rather than summarized
away: the metro-selection hypothesis overturned by a `groupby` that should have run
first; the county crosswalk rebuilt from a hand-maintained table to a geometric join;
the training-row count corrected from a state-level rollup to a metro-filtered one; and
the coordinate finding above, which surfaced only because a weak regression fit prompted
a look at the data underneath it. None were especially expensive to find late, but they all would have been
cheaper to find early.

### Sparsity is a property of sub-locations, not metros

New York's thin coverage is a **retrieval** problem, not a training problem. Per the
distinction above, the rent regression would serve a New York property perfectly well —
it learns a structural rent-to-FMR ratio from the national corpus and anchors it with
New York County's own FMR. Only comp retrieval is affected.

**Correction (Aug 8, 2026, measured in U4).** This section previously asserted that New
York would therefore serve as the system's sparse-comps demonstration, reasoning from
its low borough-wide count of 271 listings. Measurement disproved it. Comp density by
radius, 2-bedroom exact match:

| Market | 0.5 mi | 1 mi | 2 mi | 3 mi | 5 mi |
| --- | --- | --- | --- | --- | --- |
| Los Angeles (Echo Park) | 7 | 50+ | 50+ | 50+ | 50+ |
| Cleveland (downtown) | 0 | 0 | 50+ | 50+ | 50+ |
| Chicago (Logan Square) | 3 | 3 | 5 | 22 | 50+ |
| Brooklyn (Bed-Stuy) | 0 | 1 | 4 | **38** | 50+ |

Bedford-Stuyvesant returns 38 comps within three miles. The 271 New York listings are
not spread thinly across the metro — they **cluster densely in central Brooklyn**, so a
subject property there retrieves a perfectly adequate comp set. A borough-wide count is
simply the wrong statistic for a question that is answered locally.

**Sparsity in this corpus is a property of specific sub-locations, not of metros.**
Staten Island holds 6 listings in the entire borough; a Tottenville subject exhausts
relaxation and reaches zero qualifying comps. That is the genuine degradation case, and
it is what U8 carries — a real location that is really under-covered, rather than a
metro assumed to be under-covered on the strength of an aggregate.

Verified behavior across the three retained cases (`scripts/retrieval_evidence.py`):

| Case | Iterations | Final radius | Comps | Flags |
| --- | --- | --- | --- | --- |
| Los Angeles — dense | 1 | 2.0 mi | 8 | **none** |
| Chicago — moderate | 3 | 4.0 mi | 8 | 1 info, 1 warn |
| Staten Island — thin | 4 (cap) | 8.0 mi | **0** | 3 + `sparse_comps` **critical** |

The Los Angeles row matters as much as the Staten Island one: a clean run raising *no*
flags is what establishes that the flags are informative rather than merely always-on.
This point generalizes — a degradation signal that fires on every run conveys nothing,
and the parameter tuning in `config.py` was driven by exactly that consideration.

**Remediation, if production coverage were ever needed.** The Two Sigma Connect /
RentHop Kaggle dataset (~49k New York listings, ~2016 vintage) is the obvious source.
It is not adopted here: it would cost roughly a full work unit in loader, schema
mapping, and re-indexing, and its column set requires verification — square footage in
particular, which the current corpus has at 100% completeness and which the comp match
and regression both consume. The 2016 vintage would *not* be a problem, since the
FMR normalization design handles mixed vintages by construction, normalizing each row
against its own year's FMR. Documented as a known, scoped remediation rather than an
unexamined gap.

One caution recorded for anyone extending this: several New York "rental" datasets in
circulation are Airbnb data. Nightly short-term rates are a different quantity from
monthly long-term rent and would corrupt both the comp corpus and the FMR-normalized
regression while appearing superficially valid.

**Final trio: Chicago, Los Angeles, Cleveland.** Each is strong on both datasets, each
is a genuine 2–4 unit market (LA and Cleveland were both already named in the original
candidate list), and all three sit in standard county-based FMR states — Cook County IL
(`1703199999`), Los Angeles County CA (`0603799999`), Cuyahoga County OH
(`3903599999`), all three entityids verified against the live API.

**Correction — the stated reason for excluding Boston was wrong.** This section
previously excluded Boston because HUD defines FMR areas by *town* rather than county
in the six New England states, and assumed that would force a regional branch in
`tools/hud_fmr.py`. A live call disproved it: `fmr/listCounties/MA` returns town rows
carrying fully usable entityids (Boston city is `2502507000` — Suffolk County, with a
place code in the last five digits instead of the `99999` county placeholder), and
`get_fmr` consumes it unchanged, returning a flat response shape for the
Boston-Cambridge-Quincy HUD Metro FMR Area. The town regime was absorbed entirely by the
crosswalk layer; no client change was required.

Boston is therefore reclassified from *excluded, technically blocked* to **viable but
not selected**. It is not adopted because the existing trio already spans three
structurally different markets and is already indexed and parameter-tuned, so swapping
would cost rework for no capability gained. Two caveats bound the correction: it was
verified for Boston specifically, not for all six New England states (Providence RI
remains untested), and the crosswalk mapped Boston to a *town* entityid rather than
a county one — immaterial for FMR, which is all it currently feeds, but relevant if
anything later keys on county FIPS.

**No longer true as written, Aug 15, 2026.** "Absorbed entirely by the crosswalk layer"
described the *old* hand-maintained table, which was just a lookup and didn't care
whether a stored value was a county-level or town-level entityid — Boston's town
entityid sat in the table like any other row. The rewritten `county_crosswalk.py` (§7,
decision #10 follow-on) resolves county from geometry, and a county polygon join
structurally cannot produce a town-level entityid — so it does not absorb the New
England regime, it explicitly declines it (a resolved point in one of the six states
returns `None`, `TODO(geography)`). Boston's live-verified entityid above is still
correct and still proves `tools/hud_fmr.py`'s client handles the shape; what's no longer
true is that a caller reaches it through the crosswalk. Building that back — a Census
*county subdivision* boundary layer, since New England towns are county subdivisions,
not places — is exactly the future work `county_crosswalk.py`'s own docstring names.

**Why this correction is documented rather than quietly applied.** The original
hypothesis was reasoned from real domain knowledge and was confidently held — and it
was wrong in a way that would have degraded every downstream component had it gone
unchecked. Recording the hypothesis, the test, and the correction is the same
discipline the system itself implements: the failure worth guarding against is not
being wrong, but being wrong without disclosing it.

**SAFMR is a property of a county-*year*, not of a county (verified Aug 8, 2026).**
This is the most consequential correction in this section, because every earlier
version of this document — and §9 below — framed SAFMR as a fixed attribute of a
county. It is not. HUD expanded ZIP-level publication between 2019 and 2026, so the
same county returns different response shapes depending on the fiscal year requested:

| County | FY2019 | FY2026 |
| --- | --- | --- |
| Cook (Chicago) | SAFMR | SAFMR |
| Los Angeles | **flat** | **SAFMR** |
| Cuyahoga (Cleveland) | **flat** | **SAFMR** |

This matters directly to the design in this section. Training normalization queries the
Kaggle vintage year (2019, flat for two of the three), while inference queries the
current year (2026, SAFMR for all three) — so the *same county* takes different code
paths depending on which the caller asks for. `tools/hud_fmr.py` normalizes both shapes
already, so there is no defect; but any reasoning that treats "is this county SAFMR?"
as a stable fact is wrong, and code must never cache that answer across years.

### Two data gaps found during the same check

**Gap 1 — the Kaggle dataset has no county or ZIP column.** Actual columns are
`id, category, title, body, amenities, bathrooms, bedrooms, currency, fee, has_photo,
pets_allowed, price, price_display, price_type, square_feet, address, cityname, state,
latitude, longitude, source, time`. The entire FMR normalization strategy keys on
`county_fips`, so this gap sits directly underneath the rent model and was previously
invisible in this plan.

*Resolution (original, Aug 8, 2026):* since training is scoped to a curated ~5–8 metro
shortlist anyway, build a hand-verified `(cityname, state) → county_fips` crosswalk for
those cities — roughly 30–50 entries, no new dependencies, about an hour. A lat/lon →
FIPS spatial join against Census TIGER shapefiles (via `geopandas`) is the scale-up path
if the full 100K rows are ever needed; **not worth the dependency now.**

**Superseded Aug 15, 2026 — the scale-up path turned out to be the right call from the
start, and the "not worth it" judgment was made without testing it.** Once
`tools/geocoding.py` existed to put a *subject* property at a real coordinate (decision

# 10, §7), the geometric join stopped being a training-only scale-up option and became a

strict improvement on the hand-maintained table for every consumer, subject-side
included: no per-city curation, coverage of any US county rather than a hand-picked
shortlist, and the *exact* county for a point rather than the table's principal-county
approximation for cities spanning several. Measured before switching: `pip install
geopandas` — 3.3s, prebuilt wheels, no GDAL compilation, ~31MB; the Census county
boundary file loads in another ~3.3s and is cached locally after the first pull. Every
Kaggle row already carries real `latitude`/`longitude` from the original scrape (this
gap was always about the *county* column, never about coordinates), so the same join
now resolves training-row counties too, for any city in the corpus — not just the
curated shortlist this resolution originally scoped itself to. `county_crosswalk.py`
was rewritten in place rather than left as a separate scale-up module; see its own
docstring and decision #10's closing detail in §7 for the full accounting, including the
one gap carried forward rather than solved: HUD's town-based (not county-based) FMR
areas in the six New England states, tracked as `TODO(geography)`.

**Gap 2 — the Redfin extract on disk is `Monthly`, not `Rolling 3 Months`** as §2
specifies (verified: `FREQUENCY` is uniformly `Monthly`, `REGION TYPE` uniformly
`Metro`, 943 distinct metros, 102 periods each, Jan 2018 – Jun 2026). Do **not**
re-download — compute a trailing 3-period rolling median in pandas at load time in
`tools/redfin_data.py`. Same result, and it keeps the smoothing window as a tunable in
`config.py` rather than baked into a file.

**Kaggle vintage confirmed:** the `time` column is a Unix timestamp spanning **Dec 2018
– Dec 2019**. FY2019/FY2020 is therefore the correct FMR normalization year, confirming
the §9 smoke test's choice of `year=2019`.

### HUD FMR API: Implementation Notes

Concrete details for `tools/hud_fmr.py`, from the API docs
(<https://www.huduser.gov/portal/dataset/fmr-api.html>):

- **`year` is a single fiscal year per call, and must be pulled per (county, year)
  pair, not once overall.** Two distinct kinds of pulls are needed: (1) the Kaggle
  vintage year(s) for training normalization — if Kaggle rows span more than one year,
  that's multiple distinct `year` values, not one blanket value; (2) a current anchor
  year for inference. Don't hardcode the current year — call once *without* the `year`
  parameter (defaults to latest available) and read the `year` field back from the
  response, so the code doesn't go stale if this is still running months from now.
- **`entityid` for a county is the 10-digit FIPS-style code** (e.g. `5100199999`),
  obtained via `fmr/listCounties/{state}` — this is exactly what `DealTerms.county_fips`
  is meant to hold, so no reformatting should be needed between the Extractor's output
  and the FMR lookup.
- **Handle the Small Area FMR (SAFMR) response shape.** For metros where HUD publishes
  ZIP-level FMRs, `basicdata` comes back as a *list* keyed by `zip_code` (plus one entry
  literally named `"MSA level"` for the metro-wide aggregate) instead of a single flat
  object. Confirmed for Cook County (Chicago); **Los Angeles and Cuyahoga counties are
  unverified and get a real call in U1** rather than an assumed shape. Code should: look
  for an entry matching the subject property's ZIP; fall back to the `"MSA level"` entry
  if no ZIP-specific match exists.
- **Bedroom sizes cap at Four-Bedroom.** No API field exists beyond 4BR. If the
  Extractor ever produces a 5+ bedroom unit, fall back to the 4BR figure and flag it
  (`kind="fmr_bedroom_cap_exceeded"`, `severity="info"`) rather than erroring.
- **Auth and rate limit**, as already planned: bearer token in the `Authorization`
  header, 60 requests/minute — reinforces why local caching (fips + year → result) in
  `tools/hud_fmr.py` matters, since a training set spanning many counties means many
  distinct calls during development.
