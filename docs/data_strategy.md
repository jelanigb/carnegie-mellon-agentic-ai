**Part of the plan of record — see [`implementation_plan.md`](implementation_plan.md) §2.**

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
#10, §7), the geometric join stopped being a training-only scale-up option and became a
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

