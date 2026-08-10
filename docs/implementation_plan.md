# Multi-Family Residential Deal Evaluator — Implementation Plan

**Technical plan of record.**
Author: Jelani Gould-Bailey · Last updated: Aug 10, 2026

## How this project is built

This is the engineering plan for a capstone system built during CMU's Agentic AI
executive education program. It is written as a working document: architecture,
sequencing, data strategy, and the reasoning behind each decision, updated as
assumptions get tested against real data.

**Working model.** I set the architecture, data strategy, and execution sequence, and
I review every change. Implementation is executed with Claude Code against the
specifications in this document. This mirrors how I work as an engineering manager —
the leverage is in the design decisions, the data reasoning, and the review standard,
and this document is where that work lives. Sections §2 (data strategy), §3 (stack
rationale), §5 (state design), and §6 (sequencing) are the substance of the project;
the code is the expression of them.

Two conventions follow from that and are enforced throughout: every non-obvious
decision is recorded here *with its reasoning*, and every assumption is labeled as an
assumption until it has been checked against data. §2 contains a worked example of the
second — a metro-selection hypothesis I held confidently, tested, and found to be
wrong.

> **Aug 8, 2026 — major revision.** Three changes. (1) **Sequencing is now driven by
> dependency and risk rather than the syllabus calendar.** The program's weekly
> checkpoints assess a written design update alongside a working agent update; they do
> not require that a given capability be built only in the week its module is taught.
> Ordering the build by dependency and technical risk is therefore both permitted and
> better engineering — see §6. (2) **LangGraph is adopted immediately** rather than
> migrated to later; the earlier staged plan existed only to track the syllabus, and
> with that constraint gone it would have meant building the orchestration layer twice
> (§3). (3) §2's metro hypothesis was tested against both datasets and replaced.

---

## 1. Project Summary

This is a capstone project for a CMU Agentic AI executive education program. The system
is a **seven-agent pipeline** that evaluates small multi-family (2–4 unit) residential
properties as investment candidates:

1. **Planner** — inspects the deal, decides which downstream steps are needed, routes
   between agents, governs retries/escalation.
2. **Extractor** — parses an unstructured listing into structured deal terms; generates
   clarifying questions on missing fields; flags assumptions when no answer is available.
3. **Comps/Retrieval** — RAG-based comp finder over a rental listings corpus; adaptively
   relaxes search criteria (radius, match strictness) if matches are sparse, and flags
   when it does.
4. **Valuation & Rent** — rent regression model + comps-based value estimate.
5. **Scenario/Forecast** — Tree-of-Thought reasoning over rent-growth/appreciation
   scenarios (optimistic/base/pessimistic), informed by metro-level housing trend data.
6. **Critic/Reviewer** — checks consistency across upstream outputs, aggregates all flags
   into an overall confidence score, can route low-confidence deals to a
   "needs human review" state.
7. **Summarizer** — produces the final investor-facing report; required to surface all
   upstream flags prominently, not just bottom-line numbers.

**Unifying design principle — "Transparent Degradation":** whenever an agent proceeds on
incomplete or relaxed information (a widened comp radius, an unresolved clarifying
question, a low-confidence estimate), it attaches a named flag to its output. Flags
propagate downstream through the Critic to the Summarizer, so the final report always
discloses *when and how* the system deviated from the ideal path rather than silently
absorbing the gap. This principle should be visible in code, not just in the report —
every agent function should be able to append to a shared `flags` list in state, and nothing
should quietly overwrite or drop a flag on its way downstream.

**Data sources (finalized):**

- **Kaggle apartment rental dataset** — unit-level features (beds/baths, sqft, location,
  amenities, rent) for comps retrieval and rent-structure regression training.
  Candidate: <https://www.kaggle.com/datasets/shashanks1202/apartment-rent-data>
  (verify column fit against the comps schema below; confirm/parse the `time` column,
  likely a Unix timestamp — dataset is known to be ~2017–2019 vintage).
- **HUD Fair Market Rents (FMR)** — free, public, county-level, annual, rent-specific
  time series. Used to anchor the Kaggle-derived rent structure to current dollars.
  API: <https://www.huduser.gov/portal/dataset/fmr-api.html> (free account + bearer token
  required — set this up before Week 4).
- **Redfin Data Center — Housing Market Tracker, filtered to `property_type =
  Multi-Family (2-4 Unit)`** — free, public, time series (median sale price, days on
  market, inventory) available down to neighborhood/ZIP/city/county/state, filterable
  by property type. This is the sole appreciation source (see §2 — Redfin Home Price
  Index does not cover multi-family and is not used). <https://www.redfin.com/news/data-center/downloads/>

---

## 2. Data Strategy: Reconciling Kaggle/Redfin Vintage and Category Mismatch

Two problems surfaced while planning the data layer, and both are resolved the same way:
ground every dollar figure in a *dated, purpose-matched* source rather than trusting a
single dataset to do more than it can.

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

### Resolution: separate "structure" from "level," and match each quantity to a same-kind source

**Rent-level anchoring (Valuation & Rent agent):**

1. Train the regression on rent *normalized by that row's local HUD FMR at the time it
   was recorded* (rent ÷ FMR-for-that-county-and-year), not raw dollars. The model
   learns a structural relationship — "this bed/bath/sqft/amenity combination rents at
   ~1.15× the local FMR" — that ages far more slowly than a dollar figure.
2. At prediction time, multiply the model's output ratio by *today's* HUD FMR for the
   subject property's county. This produces a current-dollar estimate anchored to a
   real, dated reference point instead of an implicit 2018 price level.
3. Flag every estimate that used this anchoring path (`kind="rent_anchored_to_fmr"`,
   `severity="info"`) so the report can disclose the mechanism, and flag separately
   (`kind="fmr_unavailable_for_county"`, `severity="warn"`) if HUD has no FMR entry for
   the subject county and a coarser (state/national) fallback had to be used.

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

**Verified sufficiency of the training data (Aug 8, 2026).** The Kaggle extract holds
99,492 rows, of which **99,007 (99.5%) are complete on every core feature** — price,
bedrooms, bathrooms, square_feet, latitude, longitude, cityname, state. Notably
`square_feet` has **zero** missing values, which removes the most likely blocker for a
sqft-aware comp match and regression. A candidate ~10-metro training shortlist yields
**21,768 complete rows**, which is abundant for a regression on roughly 8–12 features.

Price distribution is sane (median $1,350; IQR $1,014–$1,795) with negligible outlier
contamination — 8 rows below $300 and 71 above $10,000, removable by the same
min/max filter pattern §2 already applies to the Redfin extract.

**Conclusion: row count is not a binding constraint on training, and never was.** The
binding constraint is the county/FIPS mapping and FMR-pull effort per added metro,
exactly as this section originally predicted. Adding a metro to the training set costs
crosswalk entries and API calls, not data.

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
  set doesn't meaningfully raise the FMR API cost. The practical constraint is data
  cleaning and county/FIPS mapping effort, not FMR access. A curated shortlist of
  roughly 5–8 metros (rather than the full dataset) keeps that cleanup bounded while
  still giving the regression meaningfully more diversity than 2–3 metros alone. The
  2–3 inference metros should be a subset of this training shortlist, so they're
  guaranteed adequate comp density and a validated data pipeline.
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
Boston-Cambridge-Quincy HUD Metro FMR Area. The town regime is absorbed entirely by the
crosswalk layer; no client change is required.

Boston is therefore reclassified from *excluded, technically blocked* to **viable but
not selected**. It is not adopted because the existing trio already spans three
structurally different markets and is already indexed and parameter-tuned, so swapping
would cost rework for no capability gained. Two caveats bound the correction: it was
verified for Boston specifically, not for all six New England states (Providence RI
remains untested), and the crosswalk would map Boston to a *town* entityid rather than
a county one — immaterial for FMR, which is all it currently feeds, but relevant if
anything later keys on county FIPS.

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

*Resolution:* since training is scoped to a curated ~5–8 metro shortlist anyway, build
a hand-verified `(cityname, state) → county_fips` crosswalk for those cities — roughly
30–50 entries, no new dependencies, about an hour. A lat/lon → FIPS spatial join
against Census TIGER shapefiles (via `geopandas`) is the scale-up path if the full
100K rows are ever needed; **not worth the dependency now.**

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

---

## 3. Stack Decision: LangGraph from day one

**Revised (Aug 8, 2026).** This section previously specified plain Python now with a
LangGraph migration staged for Week 6. That staging existed to keep the build aligned
with the order the syllabus introduced concepts. Once sequencing was freed to follow
dependency and risk instead (see the revision note at the top), the staged approach
became strictly dominated: it is the only available option that requires building the
orchestration layer twice, and it spends the scarcest resource on the project —
review-and-integration time — on a rewrite that produces no new capability.

**Decision: adopt LangGraph immediately; the plain-Python orchestration layer is not
built at all.** The four design conventions written to make the migration cheap (below)
were good conventions independent of the migration, so they survive intact — LangGraph
now enforces most of them structurally rather than by discipline.

### The stack

| Layer | Choice | Why |
| --- | --- | --- |
| Orchestration | **LangGraph** — `StateGraph`, conditional edges, checkpointer | See below |
| State schema | **Pydantic v2** (not dataclasses) | `ValidationError` text feeds the Extractor's retry prompt; dataclasses give nothing there |
| LLM calls | OpenRouter (`:free` tier models) via the OpenAI-compatible SDK | Program-endorsed, $0 |
| Observability | **LangSmith** free Developer tier | Multi-step agent loops are impractical to debug from logs alone; traces also document actual system behavior |
| Retrieval / RAG | `sentence-transformers` (local) + `ChromaDB`, **hybrid**: metadata filters for hard constraints, embeddings for description/amenity text | Free, local, and a more honest design than pure vector search over structured data |
| Regression | `pandas` + `numpy` + `scikit-learn` | Existing strength; lowest-surprise component |
| State persistence | LangGraph checkpointer (SQLite) | Comes with the framework; also enables `interrupt()` |
| Demo surface | **Streamlit**, run locally | ~50 lines; far better on video than a terminal recording |
| Dev environment | VS Code + Claude Code | — |

**Total cost: $0.** Streamlit is open-source and free to run locally; Community Cloud
is only relevant for public hosting, which this project does not require — the demo app
stays local. LangGraph is MIT-licensed. LangSmith's free tier covers a solo developer's
usage. OpenRouter `:free`
models, HUD, Redfin, and Kaggle are all free. Against the $100 project budget, the only
plausible spend is ~$10–20 of OpenRouter credits *if* free-tier rate limits become a
real time sink — but the capstone brief says *"you are expected to design your capstone
and test it using freely available model access,"* so free models are the default and
paid credits are a documented contingency, not the plan.

> ⚠️ **LangSmith free-tier traces expire after 14 days.** Capture screenshots for the
> report as you go; do not assume Week 4 traces will still be viewable in Week 7.

### Rationale

1. **Reducers make Transparent Degradation structural rather than disciplinary.**
   Declaring `flags: Annotated[list[Flag], operator.add]` means a node returning flags
   *appends* rather than overwrites. Flag loss — the failure that would defeat this
   project's central design principle — becomes impossible by construction rather than
   a convention upheld in code review. This is the strongest single argument for the
   framework on this project: the architecture and the tool agree on what must never
   happen, and the tool enforces it.
2. **`interrupt()` is the human-review escalation.** The system needs to pause, surface
   partial state to a human, and resume from that point. That is a first-class
   LangGraph primitive and a genuinely error-prone thing to hand-roll correctly.
3. **The architecture diagram is generated from the graph.**
   `graph.get_graph().draw_mermaid_png()` renders the real topology from the real code,
   so documentation cannot silently drift from the system it describes.
4. **Conditional edges are the Planner.** Routing across seven agents plus a bounded
   Critic → Planner rework cycle is precisely the shape the library exists to express.

**Trade-off accepted:** a framework dependency and its learning curve, on a project
with a fixed deadline. Mitigated by training on LangGraph up front and by keeping all agent logic in plain
functions that hold no framework-specific code — if LangGraph became a liability, the
nodes would port to a hand-rolled loop without touching the reasoning logic.

### Design conventions

- Every agent is a **node function**: state in, **partial state update** out. Note
  *partial* — returning the whole mutated state object is the most common LangGraph
  error.
- **No agent calls another agent directly.** Routing lives in edges and `route_*`
  functions, never inside a specialist.
- **State is a single typed object** (§5), never scattered across variables.
- **Flags and retries are state-encoded, not control-flow-encoded.** Conditional edges
  read state to route; anything outside state is invisible to the graph.

New addition: **every cycle must be bounded by an explicit counter in state**, not by
LangGraph's `recursion_limit`. Hitting the limit raises an opaque exception; a counter
lets the system escalate to human review gracefully, which is the behavior Checkpoint
2.1 actually specified.

---

## 4. Proposed Repository Structure

**Note:** Paths in the rest of this doc that reference `tools/`, `agents/`, `config.py`, etc. are relative to `src/`.

```
carnegie_mellon_agentic_repo/
├── data/                          # gitignored — Kaggle CSV, Redfin CSVs, cached HUD FMR responses
│   ├── raw/
│   └── processed/
├── docs/
│   ├── implementation_plan.md     # this file — the reasoning record
│   ├── changelog.md               # ✅ the chronological record: what code landed when (§8)
│   └── diagrams/                  # ✅ generated from the compiled graph, not drawn
└── src/                           # project root for all application code
    ├── README.md
    ├── requirements.txt
    ├── .venv/                     # gitignored — dedicated virtualenv
    ├── config.py                  # ✅ X/Y/Z loop parameters, model names, thresholds
    ├── state.py                   # ✅ DealState / Flag / DealTerms / Comp — Pydantic (§5)
    ├── graph.py                   # ✅ StateGraph assembly: nodes, edges, routing, compile()
    ├── nodes.py                   # ✅ node-name string constants (avoids silent typo bugs)
    ├── agents/
    │   ├── __init__.py
    │   ├── planner.py             # ✅ pre-flight plan + every route_* function
    │   ├── extractor.py           # ⬜ stub (regex parse); real LLM call is U3
    │   ├── comps_retrieval.py     # ✅ adaptive relaxation loop
    │   ├── valuation_rent.py      # ⬜ stub; U5
    │   ├── scenario_forecast.py   # ⬜ stub; U6
    │   ├── critic.py              # ◐ confidence + escalation built; consistency checks U7
    │   ├── summarizer.py          # ✅ real markdown, disclosure-first; polish in U9
    │   └── human_review.py        # ✅ the interrupt() escalation node
    ├── tools/
    │   ├── __init__.py
    │   ├── llm_client.py          # ✅ OpenRouter wrapper + schema-validated retry loop
    │   ├── vector_store.py        # ✅ Chroma setup + embedding + hybrid query
    │   ├── kaggle_data.py         # ✅ single cleaning path: dedupe, completeness, city match
    │   ├── rent_model.py          # sklearn regression: train/load/predict (FMR-normalized target)
    │   ├── hud_fmr.py             # ✅ HUD FMR API client (§9)
    │   ├── county_crosswalk.py    # ✅ (cityname, state) → county_fips, 29 entries HUD-verified
    │   ├── redfin_data.py         # ✅ load + query, rolling-3 + growth bands computed here
    │   └── tracing.py             # ✅ LangSmith project wiring; env-driven, never required
    ├── scripts/
    │   ├── pull_fmr_sample.py     # ✅ real HUD pull smoke test
    │   ├── verify_metro_selection.py # ✅ reproduces the §2 metro evidence
    │   ├── build_comps_index.py   # ✅ one-off: embed + load Chroma (3,880 listings)
    │   ├── retrieval_evidence.py  # ✅ Checkpoint 3.1 evidence: 3 density cases + config-flag ablation
    │   ├── retrieval_ablation_llm.py # ✅ Checkpoint 3.1: ungrounded LLM vs. grounded retrieval
    │   ├── train_rent_model.py    # one-off: fit + report holdout MAE
    │   └── export_graph_diagram.py # ✅ generates the diagram AND asserts decision #9's topology
    ├── notebooks/
    │   └── 01_data_exploration.ipynb
    ├── eval/
    │   ├── listings/              # synthetic listings, each engineered to trip a known flag
    │   ├── expected.yaml          # listing → expected flags / status
    │   └── run_eval.py            # batch runner → results table for the report
    ├── tests/
    │   ├── conftest.py            # ✅ puts src/ on the import path
    │   └── test_flag_propagation.py  # ✅ the one test that must never fail — 14 cases
    ├── app.py                     # Streamlit demo UI (local only)
    └── main.py                    # ✅ entrypoint: run full pipeline on one listing
```

`agents/human_review.py` was not in the original tree. It is not a specialist — it makes
no estimate and reaches no conclusion — but it *is* a node function, and putting it in
`graph.py` would have mixed a behaviour into a module that is otherwise pure wiring.

---

## 5. State Schema (design target for `state.py`)

**Changed Aug 8, 2026: Pydantic v2 instead of dataclasses**, and `flags` now carries a
LangGraph reducer. Both changes are load-bearing:

- **Pydantic** because the Extractor's clarification loop (Checkpoint 2.1, Loop 1)
  needs to observe *how* a parse was malformed and reformulate. A Pydantic
  `ValidationError` is structured, human-readable text that can be injected directly
  into the retry prompt. A dataclass just raises `TypeError` or silently accepts
  garbage.
- **`Annotated[list[Flag], operator.add]`** because without a reducer, any node
  returning `{"flags": [...]}` *overwrites* the accumulated list. That would silently
  destroy Transparent Degradation the first time two agents both raised flags. With
  it, each node returns only the flags it personally raised and accumulation is
  guaranteed by the framework.

**Flag kinds and severities are `StrEnum`, not bare strings** (revised Aug 9, 2026).
§8's review checklist already required that flag kinds be "drawn from a defined set, not
ad-hoc strings." As a class of string constants that was a rule a reviewer had to
remember; as an enum with `Flag.kind` typed against it, Pydantic rejects an unknown kind
at construction. This is the same reasoning that justified the reducer on `flags` — an
invariant the design depends on belongs in the type system, not in vigilance. The
concrete payoff is in U8: `set(FlagKind)` is enumerable, so the eval harness can assert
*coverage* — that every degradation path the system defines is actually exercised by a
test case — which turns "flags fire" into a materially stronger claim. `StrEnum` members
are `str`, so serialization and comparison are unchanged.

```python
import operator
from enum import StrEnum
from typing import Annotated, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Severity(StrEnum):
    INFO = "info"; WARN = "warn"; CRITICAL = "critical"

class FlagKind(StrEnum):
    UNRESOLVED_FIELD = "unresolved_field"
    RELAXED_SEARCH_RADIUS = "relaxed_search_radius"
    SPARSE_COMPS = "sparse_comps"
    RENT_ANCHORED_TO_FMR = "rent_anchored_to_fmr"
    FMR_UNAVAILABLE_FOR_COUNTY = "fmr_unavailable_for_county"
    COUNTY_FROM_PRINCIPAL_COUNTY = "county_from_principal_county"
    # ... 17 kinds total; see src/state.py for the full set

class Flag(BaseModel):
    source_agent: str          # e.g. "comps_retrieval", "valuation_rent"
    kind: FlagKind             # closed set — a typo raises rather than silently
                               # producing a flag that never matches
    detail: str                # human-readable explanation
    severity: Severity

class DealTerms(BaseModel):
    price: Optional[float] = None
    unit_count: Optional[int] = None
    unit_rents: list[float] = Field(default_factory=list)
    square_footage: Optional[float] = None

    # Geography, grouped by provenance — see below
    full_address: Optional[str] = None     # OBSERVED: verbatim from the listing
    street_address: Optional[str] = None   # PARSED
    city: Optional[str] = None             # PARSED — crosswalk input
    state: Optional[str] = None            # PARSED — crosswalk input
    zip_code: Optional[str] = None         # PARSED — enables SAFMR ZIP-level lookup
    county_fips: Optional[str] = None      # DERIVED by crosswalk; keys HUD FMR
    latitude: Optional[float] = None       # DERIVED
    longitude: Optional[float] = None      # DERIVED

class Comp(BaseModel):
    listing_id: str
    similarity_score: float
    rent: float
    beds: int
    baths: float
    square_feet: float
    distance_miles: float
    listing_source: Optional[str] = None   # originating site, for citation

class DealState(BaseModel):
    # inputs
    raw_listing_text: str

    # extraction
    deal_terms: DealTerms = Field(default_factory=DealTerms)
    clarifying_questions: Annotated[list[str], operator.add] = Field(default_factory=list)

    # retrieval
    comps: list[Comp] = Field(default_factory=list)
    search_radius_miles: float = 1.0   # X, widened on relaxation
    retrieval_iterations: int = 0

    # valuation
    rent_estimate: Optional[float] = None
    rent_estimate_ratio_to_fmr: Optional[float] = None  # model's raw structural output
    fmr_anchor_used: Optional[float] = None              # today's FMR figure applied
    value_estimate: Optional[float] = None
    rent_estimate_source: Literal["regression_model", "llm_fallback", None] = None

    # forecast
    # "zip_multifamily" is a documented future option (deferred — see §2); not
    # produced by the current build.
    appreciation_source: Literal[
        "metro_multifamily", "zip_multifamily", "metro_all_residential", None
    ] = None
    scenarios: dict = Field(default_factory=dict)  # optimistic/base/pessimistic branches

    # review
    confidence_score: Optional[float] = None
    needs_human_review: bool = False
    critic_rejected: bool = False
    rework_count: int = 0               # bounds the Critic → Planner cycle (§3)

    # cross-cutting
    flags: Annotated[list[Flag], operator.add] = Field(default_factory=list)
    status: Literal["in_progress", "needs_review", "complete", "failed"] = "in_progress"
    created_at: datetime = Field(default_factory=datetime.now)
```

Note which fields do and don't get reducers. `flags` and `clarifying_questions`
accumulate across multiple nodes, so both need `operator.add`. `comps` is written by
exactly one node (each retrieval iteration *replaces* the working set rather than
appending to it), so a reducer there would be wrong — it would pile up stale
candidates from relaxed passes alongside the final set. All three cases are asserted
directly in `tests/test_flag_propagation.py`, including the negative one: a future edit
adding a reducer to `comps` would make the comp list look richer than the retrieval was.

### Fields added in U2

Four, each forced by something the walking skeleton had to express:

- **`plan: list[str]`** and **`planner_invocations: int`** — decision #9 has the Planner
  write a plan into state rather than a router re-deriving it, and §3 requires routing
  to be state-encoded. `planner_invocations` makes that decision's own stated invariant
  (`planner_invocations == 1 + rework_count`) assertable in a test instead of only
  observable in a trace. No reducer on either: one node writes them, and a rework
  re-entry *replaces* the plan rather than extending it.
- **`human_review_note: Optional[str]`** — whatever the reviewer supplied on resume,
  rendered verbatim in the report.
- **`stub_nodes: Annotated[list[str], operator.add]`** — which nodes ran as placeholders,
  so the report can say a section is *unbuilt* rather than merely empty.

**Why `stub_nodes` is not a `Flag`.** This was the closest call in U2, and it went
against the obvious answer. A `FlagKind.STUB_OUTPUT` would have reused existing
machinery, and it would have been wrong twice over. First, it would corrupt what U8's
coverage check means: that check compares raised kinds against `set(FlagKind)` to claim
every *designed* degradation path is exercised, and a build-status marker is not a
degradation path. Second, it would fire on every run of this build — and §2 already
settled the principle when tuning X to 2.0 miles, that a signal which is always on
conveys nothing. A flag describes what the deal or the data did; a stub describes the
state of the software. Keeping them in separate channels is what lets the report say
both things without either diluting the other.

### Geography fields are grouped by provenance

The address originally sat as a single `address` field beside the deal economics, with
`city`/`state`/`zip`/`county_fips` in a separate block — an arrangement that left it
genuinely unclear whether `address` meant a street line or a full address, and whether
the components duplicated it. Resolved into three tiers, because *how* a value was
obtained determines how far it can be trusted:

- **Observed** (`full_address`) — copied verbatim from the listing. Cannot be wrong,
  only absent. Also the human-readable identifier the Summarizer uses, since a full
  address is what an investor recognizes.
- **Parsed** (`street_address`, `city`, `state`, `zip_code`) — decomposed from the
  observed text by the Extractor. Can be wrong, and a misparse is silent unless the
  original is retained to check against.
- **Derived** (`county_fips`, `latitude`, `longitude`) — produced by lookup, never read
  from the listing. These carry known approximation error and are the tier that raises
  flags: the crosswalk selects a *principal* county for the ten cities spanning several
  (Chicago, Dallas, Houston among them), so `county_fips` there is a defensible
  approximation rather than a fact — and every FMR figure keyed on it inherits that
  approximation. Hence `FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY`.

Keeping `full_address` alongside the parsed components is deliberate redundancy rather
than an oversight: it preserves the audit trail. If a report cites Cook County for a
property, the chain from raw string → parsed city → derived FIPS remains inspectable,
which is what makes a wrong answer diagnosable instead of merely wrong.

### `Comp.listing_source`

Checkpoint 2.1 justifies retrieval partly on the grounds that it "allows the report to
cite which ones were used." An id alone establishes that a record exists somewhere; an
id plus its originating site tells a reader where to check it. `listing_source` closes
that gap.

It carries a second signal that turned out to matter. The corpus is **91%
RentDigs.com**, and in practice all eight comps returned for the Los Angeles case come
from that single aggregator. Eight comps from one feed are less independent than eight
comps from eight sources, and a count alone conceals the difference. Surfacing the
source lets the Critic detect that concentration and the report disclose it — the same
principle as every other flag in the system, applied to a dimension that was previously
invisible. Optional, because the LLM fallback estimator produces no citable origin at
all, and that absence should be representable rather than filled with a placeholder.

This is a starting point — field names get refined once the Extractor's actual output
schema is confirmed (Unit 3, §6).

---

## 6. Execution Order

Revised Aug 8, 2026, around three principles.

**1. Walking skeleton first.** The previous ordering built the Summarizer last, in the
final week — meaning the component that produces the system's actual output would have
been the least exercised and the most schedule-exposed. Inverted: all seven agents are
stubbed and wired into a running graph in Week 4. From that point there is always a
working end-to-end system, and every subsequent unit replaces one stub with a real
implementation — a small, bounded, independently reviewable change. This converts the
dominant schedule risk from *"will the pieces integrate?"* (discovered late, expensive)
to *"how good is each piece?"* (discovered continuously, cheap).

**2. Within the build phase, order by technical risk rather than pipeline position.**
Retrieval is built before the rent regression even though it sits later in the data
flow, because Chroma and embeddings are the least familiar components in the stack
while the regression is the most familiar. Unknowns get front-loaded into the weeks
that still have recovery room.

**3. Work is decomposed into review-sized units, not calendar weeks.** The binding
constraint on this project is ~5–6 hrs/week of design and review capacity. Each unit
below is scoped to roughly 2–3 hours of review — two per week, with the buffer week
absorbing four. A corollary worth stating because ignoring it is expensive: a design
decision deferred past the unit that needs it blocks implementation *and* consumes
review capacity on re-establishing context. The decisions log in §7 exists to close
those out early.

### The units

**Resequenced Aug 8, 2026 — U4 pulled ahead of U2/U3.** Checkpoint 3.1 fell due before
the original Week 5 slot for retrieval. U4 turned out not to depend on either the
walking skeleton or the Extractor: it needs `state.py` and `config.py` (both U1), a
subject property can be constructed directly as a `DealTerms` object rather than
extracted from listing text, and a node function is callable with or without a graph
around it. This is the payoff of freezing the interface contract in U1 — with schema and
node signatures fixed, units can land in any order. Note the distinction being relied on:
U1 is the *interface* risk and had to come first; U2 is *integration* risk, which is
safe to defer.

| Unit | Build target | Feeds checkpoint |
| --- | --- | --- |
| **Week 4 — Foundation** | | |
| **U1** ✅ | `state.py` (Pydantic + reducers), `config.py`, `nodes.py`, `llm_client.py` (schema-validated retry), `kaggle_data.py`, `county_crosswalk.py` (29 entries, HUD-verified), `redfin_data.py`; FMR pull for the trio × {2019, latest} | — |
| **U4** ✅ | Comps/Retrieval: Chroma index (3,880 listings), one document per listing, hybrid metadata-filter + embedding query, top-`Y` results, adaptive relaxation loop, sparse-comps flag; **two ablations** — retrieval-off config flag and ungrounded-LLM comparison; X/Y/Z tuned against measured density | **3.1** |
| **U2** ✅ | **Walking skeleton.** 8 nodes wired in `graph.py` on the pre-flight Planner topology (decision #9) incl. the single Critic→Planner back edge and the `human_review` interrupt; Planner and Summarizer built for real; flag propagation proven end-to-end by a 14-case suite; diagram generated from the compiled graph *and* asserting the topology; LangSmith wiring env-driven | **5.1** (fully) |
| **Week 5 — Input** | | |
| **U3** | Extractor: real LLM call, Pydantic validate→retry loop, clarifying questions, assumption flags, bounded escalation; 3 synthetic listings | 2.1 evidence |
| **Week 6 — Estimation & Forecast** | | |
| **U5** | Rent model: FMR-normalized regression, holdout MAE, Valuation agent, LLM fallback path + `rent_anchored_to_fmr` / `fmr_unavailable_for_county` flags | — |
| **U6** | Scenario/Forecast: `redfin_data.py` (rolling-3, min-price floor), ToT branching over optimistic/base/pessimistic, `anomalous_period_included` flag | **4.1** |
| **Buffer week — Guardrails, Eval, Demo** | | |
| **U7** | Critic: cross-agent consistency checks, confidence scoring, bounded rework cycle, human-review escalation via `interrupt()` | **6.1** |
| **U8** | Eval harness: 8–10 synthetic listings each engineered to trip a *specific* flag, **plus the New York sparse-comps case run against real data** (see §2); batch runner → results table | **6.1** + report |
| **U9** | Summarizer polish + Streamlit demo app | report + video |
| **U10** | End-to-end runs across all three metros; capture traces, screenshots, diagrams | report + video |
| **Week 7 — Deliverables** | | |
| — | **Code frozen.** Final report + 8–10 min video. | **7.1** |

### Notes on the sequence

**Multi-agent coordination is working by Week 4 rather than Week 6.** This is the
direct payoff of ordering by dependency: the coordination design gets described from a
running graph and real traces rather than from a design sketch. Each weekly checkpoint
asks for a written design update alongside a working agent update, so building the
capability before writing about it improves both halves of the submission.

**Retrieval design decisions (U4).** Each rental listing is embedded as a **single
document, not chunked.** Listings are short, self-contained records whose fields are
mutually dependent — splitting one would separate a rent figure from the bed/bath/sqft
context that makes it interpretable, and could surface half a comparable as a match.
Chunking earns its keep on long documents with independent sections; this corpus has
neither property. Structured fields (beds, baths, sqft, geography) are carried as
metadata for hard filtering; the embedded text covers description and amenity free-text,
where semantic similarity adds signal over exact matching. **Result count is `Y` from
`config.py`** — the retrieval loop's exit condition is "at least Y qualifying comps,"
which makes the number of retrieved results a tuned parameter rather than an arbitrary
constant.

**U4 acceptance criteria.** The retrieval checkpoint is assessed against five specific
elements, so U4 is specified to produce each one as an artifact rather than leaving them
to be written up after the fact:

| Required element | Where U4 produces it |
| --- | --- |
| Architectural decision on whether retrieval is required, with justification | §2 of Checkpoint 2.1 already argues this: the failure mode being defended against is fabricated comps presented at full confidence. Restated with the built system as evidence. |
| Evidence a semantic retrieval mechanism is integrated against an external source | Chroma index over the Kaggle corpus; index build script + row counts per metro |
| Demonstration that retrieval meaningfully influences output | **Two ablations — see below.** `retrieval_ablation_llm.py` (ungrounded LLM vs. grounded, primary) and the `RETRIEVAL_ENABLED` config flag in `retrieval_evidence.py` (secondary) |
| Key design decisions: source selection, segmentation/chunking, number of results | The paragraph above: one-document-per-listing, hybrid metadata + embedding, top-`Y` |
| One retrieval failure mode + how the design manages it | Sparse comps in thin sub-markets → adaptive relaxation loop, bounded by `Z` iterations, with `relaxed_search_radius` and sparse-comps flags disclosed in the report |

**The ablation falls out of the walking skeleton for free.** U2 leaves a stubbed
retrieval node in place; U4 replaces it. Running the same listing through both versions
produces a direct before/after comparison on identical inputs, which is the "output
comparison" the criteria ask for. Keep the stub reachable behind a config flag
(`RETRIEVAL_ENABLED`) rather than deleting it in U4; it costs nothing. LangSmith traces
of both runs supply the same evidence in a second form.

> **Revised Aug 9, 2026 — the config-flag ablation is necessary but not sufficient, and
> a second one was built.** The paragraph above called it "the cleanest available
> evidence that retrieval changes system behavior." That claim was too strong, and the
> gap is worth recording because it is the same class of error this system exists to
> prevent.
>
> Setting `RETRIEVAL_ENABLED=False` makes the retrieval node return zero comps and raise
> a CRITICAL flag, so the pipeline degrades to *no estimate available*. That is an
> **absence**, not the failure Checkpoint 2.1 actually named — "fabricated grounding
> presented at full confidence." It cannot produce a fabrication, because there is no LLM
> anywhere in the retrieval path: `comps_retrieval.py` is Chroma plus arithmetic. So the
> flag ablation proves retrieval is load-bearing while leaving 2.1's central claim as an
> inherited argument rather than an observation.
>
> `scripts/retrieval_ablation_llm.py` closes that. Two free-tier models of different
> sizes are asked for comps for the Case A subject with no corpus access, filling a schema
> mirroring `state.Comp`'s citable fields. Results: **0 of 16 returned comps exist in the
> evidence base**, one address (`5678 Echo Park Ave`) was disproved against public mapping
> data — not a vacant lot but an invalid *range*, since that street tops out in the
> 2300s–2400s — and rent dispersion collapsed from CV 19.7% (retrieved) to 3.1% / 4.3%
> (invented).
> The larger model was the only one reporting *high* confidence, on an evidentiary basis
> identical to the smaller one's — zero checkable comps either way.
>
> **Two methodological corrections came out of building it, both worth carrying forward.**
>
> 1. **A verification that cannot fail is not a verification.** The corpus lookup was
>    initially presented as proof of fabrication. It is not: corpus ids are uniformly
>    10-digit numerals while the models returned `LA001` and `ECHO12345`, so *zero of
>    sixteen could have matched on format alone*. The null result was structural rather
>    than earned. The script now reports `id_format_matches_corpus` alongside the lookup
>    so the limitation is visible in the output. Address cross-checking is no substitute —
>    the corpus `address` column is ~95% null for Los Angeles. What actually establishes
>    invention is convergent, and the strongest strand came from a *manual* check no code
>    in this repo could have performed: the disproved address is invalid by range, and
>    5678 is the second element of the `1234 / 5678 / 9101` sequence both models emitted —
>    so the street number came from a counting template rather than from the street.
>    Alongside that: no resolvable citation (brand names, no URLs), identically templated
>    ids, and the dispersion collapse. **Any future evidence artifact must state what its
>    check could have returned had the system been behaving well** — and note that the
>    decisive check here was external, which is an argument for keeping a human
>    verification step in the U8 harness rather than automating it away.
> 2. **Point estimates across grounded and ungrounded runs are not comparable, and the
>    reason is a U5 dependency.** The prompt specifies no time period, so model estimates
>    are undated, while the grounded figure is a raw similarity-weighted mean over the
>    2018–19 corpus with no FMR anchoring. Any percentage gap conflates fabrication error
>    with vintage mismatch. Coefficient of variation is used instead, being a within-set
>    measure and therefore vintage-independent. **This is a concrete instance of the §2
>    rent-anchoring design being load-bearing:** once U5 anchors comp-derived rents to
>    current-dollar FMR, this comparison becomes meaningful and should be revisited.

### U2 — what the walking skeleton found (Aug 10, 2026)

The graph runs end to end on five paths, all reproducible from `main.py`. The three
density cases are the same subjects `scripts/retrieval_evidence.py` measures, reused so
skeleton behaviour is comparable against the U4 retrieval evidence rather than against a
separate set of inputs:

| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | 1.00 | **0** | reports normally |
| `chicago` | 8 | 0.85 | 2 (1 info, 1 warn) | reports normally |
| `staten-island` | 0 | 0.30 | 5 (incl. 1 critical) | pauses at `human_review` |
| `no-coords` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |
| `chicago --no-retrieval` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |

The Los Angeles row carries the same weight it does in §2: a clean run raising *no*
flags, escalating nothing, is what establishes that the other four rows mean something.

**Three findings, each of which changed the build.**

**1. A single critical flag did not escalate. Fixed.** One critical flag costs 0.40
against the provisional weights, putting confidence at exactly 0.60 — and
`0.60 < 0.60` is false, so the `no-coords` and `--no-retrieval` runs reported a deal
with zero comparables as an ordinary result. The report defines critical as *"the
estimate below should not be relied on without addressing this"*, so the system was
contradicting its own stated meaning. The Critic now escalates on either ground
independently: below-threshold confidence, **or** any critical flag. Keeping them
separate is deliberate rather than a stopgap — it makes the guarantee independent of
weights that U7 is still going to change. Decision #6 should confirm it, not re-derive
it. Regression test included, and written to assert the guarantee rather than the
arithmetic that currently produces it.

This is the boundary-condition class of defect that only surfaces by running the thing.
It was invisible to the tests as first written, because those exercised the two paths
that were obviously interesting (clean run, floor-collapse run) and not the one sitting
exactly on the threshold.

**2. "Exactly one cycle" is not a checkable property. "Exactly one back edge" is.** The
diagram exporter verifies decision #9's topology rather than only illustrating it, and
its first version failed against a correct graph — reporting two cycles where the design
permits one. Both were real simple cycles (`planner → extractor → … → critic → planner`
and `planner → comps → … → critic → planner`), traversing the same single
`critic → planner` back edge. Simple-cycle count grows combinatorially with every legal
skip branch, so it was measuring branch count while claiming to measure loop count. One
back edge is one place the graph can loop, whatever the number of routes into it; the
check and the onboarding checklist both now say back edge. The wording in the original
decision was ambiguous rather than wrong, but an ambiguous invariant cannot be asserted,
and this one is now asserted on every export.

**3. Nothing in this system derives latitude/longitude** — raised as decision #10 rather
than resolved at implementation time, per §8. §5 lists the coordinates as DERIVED "by
lookup" and no lookup exists: the crosswalk resolves county only, and the evidence
scripts hardcode real coordinates for their synthetic subjects. `vector_store.query_comps`
hard-requires coordinates, so a subject without them retrieves nothing regardless of how
good the extraction was. `--deal no-coords` runs the dense Los Angeles deal with them
withheld, so what the gap costs is demonstrated rather than described.

**Decisions taken during the build**, recorded here because each is the kind that is
cheap to make deliberately and expensive to unwind:

- **The Planner is built, not stubbed.** §6 listed all seven agents as stubs, but the
  Planner has no later unit assigned — and needs none. Decision #9 established that it
  never chooses an ordering, so its whole job is deterministic: which optional steps to
  skip, rework routing, escalation. There is nothing for an LLM to decide, which is also
  why U2 could land with decision #8 still open.
- **The Valuation stub deliberately produces no number.** The obvious placeholder —
  average the comps and call it an estimate — would violate the §8 invariant that no
  unanchored Kaggle dollar figure reaches the Summarizer. A comps mean over a 2018–19
  corpus is a 2018 number in a 2026 report wearing no date, which is precisely what §2's
  anchoring design exists to prevent. A stub is not a license to breach an invariant the
  rest of the system is built around. The visible consequence — the report saying the
  valuation is unbuilt — is a true statement, where a placeholder number would have been
  a false one.
- **`_consistency_objections()` exists as a real function returning an empty list**,
  rather than being omitted until U7. It keeps the rework branch present, reachable, and
  testable at a single substitution point, which is how the cycle is proven bounded now
  rather than in U7.
- **The rework counter increments on Planner re-entry, not on Critic rejection.** The two
  are not equivalent: a rejection that escalates straight to a human is not a rework, and
  counting it as one would silently shorten the budget.
- **Confidence excludes the Critic's own derived flags.** A rework pass re-runs the
  Critic, the reducer appends its previous `low_confidence_estimate` flag, and counting
  that would let the score drive itself down on each lap of a cycle that exists to
  improve the deal. Latent today (nothing triggers rework yet) and cheaper to prevent
  than to diagnose later.
- **A reviewed deal keeps `status="needs_review"`.** Overwriting it at the Summarizer
  would erase the difference between "the system was confident" and "a human signed off".

**Two things worth knowing for review.** LangGraph 1.x warns on every custom type it
deserializes from a checkpoint without an explicit allowlist — *"this will be blocked in
a future version"* — so the paused-and-resumed path was on a deprecation clock and the
warnings buried the interrupt payload. `graph.state_serde()` registers the six state
types that cross that boundary, which is also the safer posture: the default
deserializes any type a checkpoint file names. Note that the fluent
`JsonPlusSerializer().with_msgpack_allowlist(...)` silently returns `self` unchanged when
the base allowlist is the permissive default; the constructor argument is required.
Separately, the `TODO(U2)` in `hud_fmr.py` is cleared: cache writes are now atomic
(write-to-temp then rename), and the residual concurrency limitation is documented on the
class as accepted rather than left as an open item — the loss is one cache miss against a
60/minute budget.

**Still outstanding for U2's checkpoint evidence:** LangSmith. The wiring is done and
env-driven (`tools/tracing.py`), and every run prints whether tracing is on, so a run
believed to be captured and silently not captured is not a failure mode here. Traces
themselves need the account.

**U8 is the highest-leverage unit in the plan.** A set of synthetic listings each
engineered to trigger a specific named flag — missing price, 5+ bedroom unit (FMR
bedroom cap), a county with no FMR entry, a location with no qualifying comps, an
internally inconsistent listing — serves three purposes at once: it is the evaluation
results section of the final report, the guardrails evidence for the safety checkpoint,
and the clearest available demonstration that Transparent Degradation works end to end.
It is protected from the cut list for that reason.

U8 also carries the **New York sparse-comps case** (§2), which is the one degradation
scenario grounded in real market data rather than a constructed listing. Synthetic
cases prove the mechanism fires; the New York case proves it fires when reality — not
the author — supplies the gap. Both forms of evidence are worth having, and the
distinction between them is worth drawing explicitly in the report.

### Cut list, in order

If the schedule slips, shed scope in this order rather than improvising:

1. **ZIP-tier appreciation** (already deferred in §2 — keep it deferred).
2. **LLM rent fallback path** — document as designed-but-unbuilt; Checkpoint 2.1
   already anticipated this exact trade.
3. **Streamlit app** — fall back to a terminal recording plus LangSmith traces.
4. **Critic rework-loop depth** — reduce to single-pass review with escalation,
   keeping the cycle in the graph but capping `MAX_REWORKS = 1`.

**Never cut:** the flag propagation test (U2), the eval harness (U8), or the Week 7
report reserve.

### The hard constraint

**Week 7 is reserved entirely for the report and video, with the code frozen.** The
realistic failure mode for a fixed-deadline project like this is arriving at the final
week still integrating, and shipping a rushed write-up of a system nobody has time to
evaluate. A frozen build a week out guarantees there is something coherent to measure,
document, and demonstrate. Any unit unfinished at that point ships as-is and is
documented explicitly as future work — stating a known limitation is better engineering
communication than concealing it, and it is consistent with the Transparent Degradation
principle the system itself implements.

---

## 7. Immediate Next Actions

### Decisions log

Each of these blocks implementation downstream; they are listed in the order they are
needed. Target: all closed during Week 4.

| # | Decision | Status |
| --- | --- | --- |
| 1 | Orchestration framework | ✅ LangGraph, day one |
| 2 | Inference metro trio | ✅ Chicago, LA, Cleveland |
| 3 | Demo surface | ✅ Streamlit, local, scheduled U9 |
| 4 | Training metro shortlist (~5–8, superset of the trio) | ⬜ `county_crosswalk.py` now covers 29 cities (every ≥500-listing pair); final selection pending |
| 5 | X / Y / Z loop parameters | ✅ X=2.0 mi, Y=8, Z=4 — tuned in U4 against measured density curves; rationale in `config.py` |
| 6 | Confidence threshold for human-review escalation | ⬜ provisional 0.60 set; tune in U7. **U2 added a second, independent escalation ground** — any critical flag escalates regardless of score (see §6, finding 1); confirm rather than re-derive |
| 7 | Redfin minimum-price floor | ✅ $10,000, with evidence (§2) — note it is inert for all three inference metros |
| 8 | OpenRouter model per role (dev / extraction / critic / summarizer) | ⬜ **placeholders confirmed dead (Aug 9)** — see below; still deferrable to U3 |
| 9 | Planner topology — pre-flight vs. supervisor | ✅ **pre-flight + rework re-entry** (Aug 9, 2026); built and topology-asserted in U2 |
| 10 | **Geocoding source** — how `DealTerms.latitude/longitude` get derived | ⬜ **opened Aug 10, 2026 in U2.** Blocks U3 |

**Decision #8 detail (Aug 9, 2026).** The `TODO(U3)` in `config.py` warned that the four
model IDs were unverified placeholders. Checked against OpenRouter's live catalogue while
building `retrieval_ablation_llm.py`: **`meta-llama/llama-3.3-70b-instruct:free` no longer
exists.** The model is still listed but is paid-only, and there is now *no* free Llama
variant at all. All four placeholders are therefore dead, and U3 cannot run until this is
set.

The decision remains **deferrable to U3** and is deliberately left open. Nothing before U3
makes an LLM call — the retrieval path contains none, and `retrieval_ablation_llm.py` names
its models locally rather than reading `config.MODEL_*`. Choosing well needs real extraction
output to judge against, which does not exist yet. Verified live and responding as of
Aug 9: `openai/gpt-oss-20b:free` and `nvidia/nemotron-3-super-120b-a12b:free`;
`google/gemma-4-31b-it:free` returned a provider 429. Note the current four-way split is
structural, not a real selection — all four constants are identical.

**The durable lesson is about staleness, not selection.** A model ID that was valid when
this document was written was invalid six days later, and the failure would have surfaced
as an opaque runtime error mid-U3. Free-tier catalogues churn, so these constants should
not be treated as set-once. U3 should add a startup liveness check that fails loudly at
launch if a configured model is absent from `/api/v1/models`, rather than discovering it on
first invocation.

**Decision #10 detail (opened Aug 10, 2026).** §5 lists `latitude`/`longitude` as DERIVED
"produced by lookup, never read from the listing" — and no lookup produces them. The
crosswalk resolves county FIPS only; the U4 evidence scripts hardcode real coordinates
for their synthetic subjects, which is legitimate for a measurement script and is not a
pipeline. This sat unnoticed because the one agent that needs coordinates was built by a
script that supplied them.

It matters because `vector_store.query_comps` hard-requires them: without coordinates
there is no bounding box, no radius filter, and no comps at all, whatever the extraction
quality. So this gates the entire grounded path for any listing arriving as text, which
is exactly what U3 produces. Three options, none yet chosen:

1. **A geocoding API call** (Census Geocoder is free and public; Nominatim has usage
   terms worth reading). Accurate to the parcel, adds a network dependency and a failure
   mode on the critical path.
2. **A city-centroid table** extending `county_crosswalk.py`, with a disclosed
   approximation flag. No new dependency and consistent with how the county gap was
   resolved in §2 — but a centroid is a poor subject location in a large metro, and the
   radius search is precisely where that error lands. Los Angeles is the worst case for
   it.
3. **Require coordinates on the input**, treating geocoding as out of scope and
   documenting it. Honest, and it makes the demo depend on hand-supplied data for a field
   the design calls derived.

Recommendation is (1) with (2) as the fallback path when the call fails, since that
combination degrades in exactly the way the rest of the system does — flagged, disclosed,
still producing an answer. Raised rather than resolved per §8, since it is a data-source
decision and those belong in this log.

**Decision #9 detail.** The pipeline order is fixed by data dependency — Valuation consumes
`state.comps`, Scenario consumes `rent_estimate`/`value_estimate` — so the sequence
Extractor → Comps → Valuation → Scenario → Critic is not something the Planner chooses. The
open question was only where the Planner *sits*, and two topologies were considered:

- **A — pre-flight + rework re-entry. Selected.** `START → Planner`; the Planner writes a plan
  into state (which optional steps run); a mostly static chain follows, with conditional edges
  only where skipping is legal; `Critic → Planner` is the sole cycle in the graph.
- **B — supervisor hub-and-spoke.** Every specialist returns to the Planner, which re-decides
  each hop. Rejected.

B was rejected because it pays six extra Planner invocations per run — LLM calls, latency, and
non-determinism — to re-derive an ordering that was never in question, and because it puts
several cycles in the graph, which makes the Checkpoint 5.1 coordination description harder
rather than easier. Nothing is given up: the Planner's real degrees of freedom under A are
which optional steps to skip, retry/rework routing, and escalation, all expressed as
conditional edges. This is what §3 rationale item 4 already asserted — *"conditional edges are
the Planner"* — so A ratifies the stated design rather than changing it.

**Consequences for U2**, which builds `graph.py` against this:

- Exactly one cycle exists (`Critic → Planner`), bounded by `rework_count`. Any second cycle
  appearing in the generated diagram is a defect, and that makes the diagram a review
  instrument rather than only an illustration.
- The Planner node runs at most `1 + rework_count` times per deal, which is the figure the
  Checkpoint 5.1 coordination section should quote.
- Specialists have static outgoing edges except where skipping is legal, so `route_*`
  functions stay few and small — consistent with §3's "no agent calls another agent directly."

Recorded because the hand-drawn diagram in `lang_graph_onboarding.md` §4 showed B's shape (and
showed it incoherently — see the correction note there), which is how an unclosed decision
surfaced as a documentation defect rather than as a question. Per §8, decisions of this kind
get raised rather than resolved by assumption at implementation time; this one was.

Each weekly checkpoint publishes explicit completion criteria. Where those exist, the
corresponding unit is specified to produce each required element as a build artifact
rather than as a write-up authored afterward — see the U4 acceptance criteria in §6 for
the pattern. Apply the same treatment to 4.1, 5.1, and 6.1 as their criteria are
published.

### Open items

U1, U4, and U2 are complete. What remains, in the order it is needed:

1. **LangSmith account** — create it and set `LANGSMITH_TRACING=true` and
   `LANGSMITH_API_KEY`. **No longer a blocker on building**, since U2's wiring is
   env-driven and the graph runs without it (`tools/tracing.py`, which prints on every
   run whether tracing is on). It *is* a blocker on the trace evidence Checkpoint 5.1
   wants, and traces expire after 14 days on the free tier, so it should be set up
   before U3 rather than before the write-up.
2. **Decision #8** — model IDs. Placeholders confirmed dead (see the decision #8 detail
   above); deliberately deferred to U3, which it blocks.
3. **Decision #10** — geocoding source. Opened in U2 (detail above); blocks U3, since a
   real extractor producing text-only geography still cannot retrieve comps without it.
4. **Decision #4** — finalize the training shortlist from the 29 crosswalk entries.
   Blocks U5.
5. ~~**OpenRouter API key**~~ — ✅ **closed Aug 9, 2026.** Stored at `ignore/openrouter_key`
   (gitignored); `llm_client._load_token()` reads `OPENROUTER_API_KEY` first and falls back
   to that file. Verified by live calls in `retrieval_ablation_llm.py`.

Built and verified against real data, requiring no rework: `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py` (§9), `scripts/verify_metro_selection.py`,
`tools/kaggle_data.py`, `tools/county_crosswalk.py`, `tools/redfin_data.py`,
`tools/vector_store.py`, `agents/comps_retrieval.py`, `scripts/build_comps_index.py`,
`scripts/retrieval_evidence.py`, and `scripts/retrieval_ablation_llm.py` (the last also
being the first live exercise of `tools/llm_client.py` — `call_with_schema`'s retry loop
fired for real, one model needing two attempts to produce schema-valid output). Added and
verified in U2: `graph.py`, `main.py`, `agents/planner.py`, `agents/summarizer.py`,
`agents/human_review.py`, `tools/tracing.py`, `scripts/export_graph_diagram.py`, and
`tests/test_flag_propagation.py` (14 cases, all passing).

### Prerequisite reading (before U2 review)

Ramp up on LangGraph (roughly
3 hours). This sits on the critical path: the review standard applied to Weeks 4–6 is
only as good as the reviewer's fluency in the framework, and §6 of that document is the
checklist applied to every unit.

---

## 8. Engineering Standards

These are the standards every change set is held to in review. They are recorded here
rather than left implicit so that the bar is the same whether a given unit is written
in a focused session or across a fragmented week.

### Architecture

- **Follow the design conventions in §3**: node functions returning *partial* state
  updates, no agent-to-agent calls, a single typed state object, flags and retries
  encoded in state, every cycle bounded by an explicit counter. LangGraph enforces
  several of these structurally; the partial-update rule and the bounded-cycle rule
  remain a review responsibility.
- **Never let Redfin data touch a rent dollar figure**, and never let unanchored Kaggle
  dollar figures reach the Summarizer — every rent number passes through FMR
  normalization first. This is the code-level expression of the rent-level anchoring
  design in §2, and it is the kind of invariant that degrades silently if unwatched.
- **`config.py` is the single home for tunable parameters** — search radius X, comp
  count threshold Y, iteration cap Z, confidence threshold, `MAX_REWORKS`, Redfin price
  floor. These are tuned across U4–U7; a value hardcoded inside an agent is a defect,
  not a shortcut.

### Documentation

- **Every agent function carries a docstring stating its Reason/Act/Observe/Decide
  loop**, matching the structure specified in the Checkpoint 2.1 design. The reasoning
  loop is a design commitment, and keeping it stated at the point of implementation is
  what keeps the code and the design document from diverging.
- **Decisions are surfaced, not guessed.** Anything that belongs in the §7 decisions log
  gets raised for a decision rather than resolved by assumption. Such decisions are
  inexpensive to make deliberately and expensive to unwind once code depends on them.

- **Every unit closes by appending to `docs/progress_tracker.md`** (added Aug 10, 2026).
  A `##` heading per date, and beneath it a table of `unit | work done | related
  checkpoint` — one update per row, each naming the checkpoint that row's work feeds.

  This exists because of §6's central sequencing decision. Ordering the build by
  dependency and technical risk instead of by the syllabus calendar is the right call and
  is defended at length there, but it has a cost that decision did not account for: once
  unit order is decoupled from checkpoint order, nothing maps delivered work back to the
  requirement it satisfies. U4 shipped before U2; work feeding Checkpoint 6.1 exists
  before 4.1 and 5.1 are due. Reconstructing that mapping from git history at report time
  is exactly the sort of late, avoidable work the Week 7 freeze exists to prevent.

  **The tracker is a separate file rather than another section here, and the split is by
  kind rather than by length.** This document is the *reasoning* record — why a decision
  was made, what was tested, what turned out to be wrong. The tracker is the
  *chronological* record — what landed, when, and which checkpoint it serves. Two
  different questions, asked by readers in two different situations. Merging them would
  also mean this document grows a log section on every unit, and it is already long
  enough that new material competes with existing material for attention.

  Written as part of finishing the unit, alongside the updates to this document — not as
  a later reconciliation pass, which is the form of this task that reliably does not
  happen. Reasoning is not duplicated into the tracker; a row that needs justification
  cites the section here instead.

- **An evidence artifact must state what its check could have returned had the system
  been behaving well** (added Aug 9, 2026). A verification whose negative result was
  structurally guaranteed proves nothing, however convincing the output looks — and a
  document that overstates its own verification commits exactly the error Transparent
  Degradation exists to prevent, one level up. The corpus-membership check in
  `retrieval_ablation_llm.py` is the worked example: it could never have matched, because
  the id formats are disjoint, and it now prints that fact next to its own result. This
  standard applies to every artifact feeding a checkpoint or the final report, including
  the U8 eval harness.

- **Deferred work is recorded as a tagged `TODO` at the site it affects**, not left in
  conversation. Format is `TODO(<scope>):` where scope is the unit that will address it
  (`U2`, `U5`) or a category (`security`, `geography`), so `grep -rn "TODO(U5)" src/`
  returns that unit's backlog directly. Each states what is missing, why it was
  deferred, and what it would take — a bare `TODO` marks a problem without helping
  anyone act on it. Current inventory:

  | Tag | Location | Item |
  |---|---|---|
  | `TODO(U3)` | `config.py` | Model IDs **confirmed dead**, not merely unverified (decision #8); add a startup liveness check |
  | `TODO(U3)` | `extractor.py` | Nothing derives latitude/longitude, and comp retrieval hard-requires them (decision #10) |
  | `TODO(U5)` | `state.py`, `build_comps_index.py` | Index the `time` column so `Comp.listed_date` allows per-row FMR normalization |
  | `TODO(U5)` | `county_crosswalk.py` | Nothing yet raises `COUNTY_FROM_PRINCIPAL_COUNTY` for multi-county cities |
  | `TODO(U7)` | `critic.py` | Cross-agent consistency checks — `_consistency_objections()` returns empty until then |
  | `TODO(U7)` | `critic.py` | Confirm the critical-flag escalation rule when the severity weights are tuned (§6, finding 1) |
  | ~~`TODO(U2)`~~ | `hud_fmr.py` | ✅ **cleared Aug 10, 2026** — writes are atomic; the residual concurrency limit is documented on `_DiskCache` as accepted |
  | `TODO(security)` | `hud_fmr.py`, `llm_client.py` | Whether to drop on-disk credential fallbacks in favour of env-var-only |
  | `TODO(geography)` | `county_crosswalk.py` | New England town-based FMR verified for Boston only, not the other five states |

### Testing

Testing is scoped deliberately rather than exhaustively, and the scope is documented
here so the choice is legible.

Two things are tested unconditionally, because they are the project's load-bearing
claims:

1. **`test_flag_propagation.py`** — a flag raised in the Extractor survives every
   downstream node and appears in the rendered report. Transparent Degradation is the
   central design principle of this system; a silent flag loss would invalidate every
   output the system produces while leaving it looking correct. This test never gets cut.

   **Built in U2: 14 cases**, structured around the ways the guarantee can break rather
   than around the modules implementing it — first-node flag reaching the last node,
   flags from two agents coexisting, the reducer annotations still being present
   (including the negative case: `comps` must *not* have one), every flag rendered in
   full rather than counted, the rework cycle terminating and disclosing that it did,
   and the interrupt pausing and resuming with the reviewer's note in the report.

   Two constraints on the suite are deliberate. It **avoids the Chroma corpus** on every
   case but one: a must-never-fail test should fail only when the thing it tests is
   broken, and a dependency on a built index and a downloadable embedding model would
   let it fail for unrelated reasons. A test that cries wolf stops being consulted. The
   exception is a grounded Los Angeles run that skips cleanly when the index is absent —
   and its role is the same one §2 gives the LA row in the retrieval evidence: a suite
   where every case is degraded cannot show that the degradation signals mean anything.
2. **The `eval/` harness (U8)** — synthetic listings engineered to trigger each named
   flag, run as a batch with results tabulated. This functions as the system's
   behavioral test suite and as its evaluation evidence.

Broad unit-test coverage is **deferred, not dismissed.** With a fixed deadline, coverage
competes directly against the two suites above, and those carry far more information per
hour invested — they test system-level behavior against the design's actual claims
rather than restating implementation details. Additional coverage gets added
retroactively if the buffer week allows. This is a scheduling judgment about sequence,
and it is recorded as such rather than left as an unexplained gap.

### Change management

- **One unit per change set**, self-contained, accompanied by a summary of what changed
  and where the reviewer's attention is most warranted. A diff spanning five loosely
  related files costs more review time than the batching saves.
- **All test and development data is synthetic or public**, per program requirements.
  No scraped or proprietary listings enter this repository at any point.

---

## 9. Current Build: HUD FMR API Client (`tools/hud_fmr.py`)

**Status:** built and verified against the live API, Aug 8, 2026. `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py`, `requirements.txt`, and a dedicated `.venv/` all exist
under `src/` as planned below.

**What the real pull found (corrects an assumption in §2):** the smoke test ran
`get_fmr` for all three candidate counties at both `year=2019` (Kaggle vintage) and
`year=None` (resolved to 2026, the current FY) —

| County | entityid | SAFMR? | 2BR FMR, 2019 | 2BR FMR, 2026 |
| --- | --- | --- | --- | --- |
| New York County, NY | `3606199999` | **No** — flat shape | $1,831 | $2,910 |
| Cook County, IL | `1703199999` | **Yes** — SAFMR list shape | $1,212 | $1,781 |
| Philadelphia County, PA | `4210199999` | **Yes** — SAFMR list shape | $1,200 | $1,810 |

§2 had hypothesized New York was the likely SAFMR metro among the three — reality is
the opposite: New York is flat, and Chicago/Philadelphia are the SAFMR ones. Both
correctly fell back to the `"MSA level"` entry (metro-level default, no `zip_code`
passed), confirming the SAFMR branch is genuinely exercised, not just written
defensively. Cache verified too: an immediate repeat call returned in 0.000s (cache
hit, no second HTTP request).

> **Superseded in part (Aug 8, 2026, later the same day).** Two things changed. The
> inference trio became **Chicago, Los Angeles, Cleveland** (§2 — the NY/Philadelphia
> hypothesis failed a data-density check). More importantly, the framing above — "is
> this county SAFMR?" — is itself wrong: **SAFMR is a property of a county-year**, and
> the same county returns different shapes for 2019 and 2026. See §2 for the measured
> table. This section's data remains valid evidence that the client authenticates and
> handles both response shapes; it should not be read as establishing a fixed SAFMR
> status for any county. U1 confirmed the trio's entityids and both shapes.

**Scope:** deliberately narrow — just the client and a real smoke-test pull, so a
working HUD data pull exists as soon as possible. Explicitly **not** included here:
`config.py`, `state.py`, `agents/`, `tests/`, or the rest of the scaffold — those are
U1 (§7). Kaggle and Redfin data already sit in `data/` (repo root) and don't depend on
any of this.

**Files added:**

```
src/
├── requirements.txt          # requests, python-dotenv
├── .venv/                    # gitignored — dedicated virtualenv for this project
├── tools/
│   ├── __init__.py
│   └── hud_fmr.py            # the client
└── scripts/
    └── pull_fmr_sample.py    # runnable smoke test — a real pull, not a mock
```

**Auth:** a bearer token from a free HUD User account, supplied via the `HUD_FMR_TOKEN`
environment variable with an untracked local file as a fallback. Credentials are never
committed and are not described further here.

**Base URL:** `https://www.huduser.gov/hudapi/public`

**Endpoints wrapped:**

| Function | Endpoint | Purpose |
| --- | --- | --- |
| `list_states()` | `GET /fmr/listStates` | state code ↔ name lookup |
| `list_counties(state_code)` | `GET /fmr/listCounties/{state_code}` | county name → 10-digit FIPS `entityid` lookup |
| `get_fmr(entityid, year=None)` | `GET /fmr/data/{entityid}?year={year}` | raw FMR record for one county/metro + one fiscal year; omitting `year` returns the latest available and the response's own `year` field is read back rather than assumed |
| `get_fmr_for_bedroom(entityid, bedrooms, year=None, zip_code=None)` | wraps `get_fmr` | single rent figure for a given bedroom count |

**Behavior:**

1. **SAFMR response-shape handling — metro-level by default.** `get_fmr` inspects
   whether the response's `basicdata` is a flat dict (ordinary metro/county) or a
   list (Small Area FMR — ZIP-keyed entries plus one `"MSA level"` entry), per §2's
   HUD FMR API notes. Both shapes are normalized into one consistent return shape so
   callers never need to branch on it. **`zip_code` defaults to `None`, so the result
   is always metro-level**, matching the Kaggle and Redfin data (§2) — for a
   non-SAFMR county there's only ever one metro-wide record anyway, and for a SAFMR
   county the client falls back to the `"MSA level"` entry and reports
   `used_msa_fallback=True`. Passing an explicit `zip_code` (if it matches an entry)
   is supported so the SAFMR branch neither errors nor silently misparses, though no
   current caller uses it. It is retained deliberately: ZIP-level lookup is the natural
   extension point if the deferred ZIP-tier work in §2 is ever taken up, and the branch
   is cheaper to keep correct now than to reconstruct later.
2. **Bedroom cap.** `get_fmr_for_bedroom` caps at `four_bedroom` for `bedrooms >= 4`
   and returns `bedroom_cap_exceeded=True` in the result rather than raising. Turning
   this into an actual `Flag` (`kind="fmr_bedroom_cap_exceeded"`) is the Valuation &
   Rent agent's job once `state.py` exists — out of scope for this client.
3. **Year resolution.** Every result carries the `year` HUD actually returned, never
   the caller's requested year, so downstream code can't silently assume a stale or
   wrong year was honored.
4. **Local caching.** On-disk JSON cache at `data/raw/hud_fmr_cache.json` (repo root,
   already gitignored), keyed by `(endpoint, entityid, year)`. Avoids re-hitting the
   API for repeat lookups during dev and later training-data prep.
5. **Rate limiting.** A client-side throttle enforces HUD's 60 requests/minute cap
   (simple minimum interval between calls); cache hits bypass the throttle entirely
   since they never hit the network.
6. **Errors.** A small `HudFmrApiError` is raised on non-200 responses (status +
   body included). No silent state/national-average fallback is implemented yet —
   that logic belongs to the Valuation & Rent agent's flag-aware design in §2, which
   needs `Flag`/`DealState` to exist first.

**Smoke test (`scripts/pull_fmr_sample.py`):** pulls real FMR data for 2-3 counties
across the candidate metros (New York City, Cook County/Chicago, Philadelphia County)
across two years — one Kaggle-vintage year (e.g. 2018) and the current/latest year
(via `year=None`) — and prints/saves the parsed result. This is meant to produce
visible proof the client authenticates correctly and actually exercises both response
shapes, not just pass a unit test against fixture data.

**Verification before calling this done:**

- Real (not mocked) calls to `list_counties` and `get_fmr` succeed against the live
  API using the configured token.
- At least one of the three candidate counties returns a SAFMR (list) shape,
  confirming that code path is actually exercised.
- Running the same query twice hits the on-disk cache on the second call (no second
  HTTP request — verified via a log line or timing), and the cache file lands in
  `data/raw/`, not committed to git.
