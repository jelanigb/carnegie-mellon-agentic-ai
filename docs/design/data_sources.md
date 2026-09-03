**Reference map for the plan of record, §2 — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#22) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

# Data Sources: what each one is, and what it feeds

Related: [`data_strategy.md`](data_strategy.md) (§2 — *why* these sources, and the
findings against them) · [`architecture.md`](architecture.md) (§3, §4) ·
[`hud_fmr_client.md`](hud_fmr_client.md) (§9)

## Why this file exists

This project uses four external sources for three different purposes, and the same
source is used differently depending on the purpose. The rent regression and comp
retrieval both draw on the Kaggle corpus but filter it to different metros and consume
different columns. HUD FMR appears at four separate points in one pipeline run, playing
a different role each time. Redfin never touches a rent figure at all.

None of that was written down in one place. §2 explains *why* each source was chosen and
was written before most of the code existed; `config.py` holds the parameters;
the module docstrings hold the mechanics. Assembling "which dataset is used in which
process" meant reading six files and holding the answer in your head — and the answer
drifted from §2 as the build progressed.

**This file is the map. §2 stays the argument.** Where a number appears in both, this
one is derived from the code and is the one to trust.

---

## The map

| Source | Vintage | Finest geography it carries | Geography this system actually uses | What it feeds |
| --- | --- | --- | --- | --- |
| **Kaggle rent corpus** | Dec 7 2018 – Dec 26 2019, static | Street address (**8% of rows**), else city | Latitude/longitude per row (city-area placeholder for 92%) | Rent-model training · comp index |
| **HUD FMR API** | Live, by federal fiscal year, **FY2017–2026 history** | **ZIP** (SAFMR counties only) | **County** | Anchor's **bedroom step** only (U11.3) · demo calibration · **rent-growth series — fallback only since #21 (U9.3)** |
| **Redfin sale medians** | Jan 2018 – Jun 2026, monthly | Metro (this extract); ZIP extract exists unused | Metro | Market benchmark **where no local records exist** · **price** appreciation (U6) · demo calibration |
| **NYC DOF sales** | 2023-01 – present, per transaction | Parcel (`bbl`, lat/lon) | **ZIP** | Market benchmark, New York (U8.8) |
| **Cook County Assessor** | 2023-01 – present, per transaction | Parcel (`pin`) | **ZIP**, via the parcel universe | Market benchmark, Chicago (U8.8) |
| **Zillow ZORI** | 2015-01 – present, monthly | **ZIP** (8,543 nationally) | **ZIP**, county median where a ZIP's series does not reach | Anchor's **rent level** — training denominator, inference anchor, comp cross-check (U11.3) · the independent rent check (#16, U8.0) · **the forecast's rent-growth series, at county (#21, U9.3)** |
| **Census Geocoder** | Live | Parcel / street address | Parcel, with city-centroid fallback | Subject-property coordinates |
| **Census county boundaries** | TIGER/Line 2023 | County polygon | County | Coordinate → county FIPS |
| **Census ZCTA boundaries** | Cartographic 2020 | ZCTA polygon (~33,800) | ZCTA | Coordinate → ZIP, for ZIP-level FMR |
| *(derived)* **Chroma index** | Inherits Kaggle | Inherits Kaggle | Inherits Kaggle | Comp retrieval only |

**Read the two geography columns as a pair.** The gap between them is where this
system's precision is lost by choice rather than by the data's limits, and it is the
single most useful thing on this page — writing this file is what surfaced the HUD row's
gap, which had gone unnoticed through three units and was closed the same day (below).
Every gap on this map has now been closed or narrowed with its residue stated; the last
one, Redfin's, closed Aug 30, 2026 from an unexpected direction — see "The same gap on
the price side" below.

| Source | Gap | Status |
| --- | --- | --- |
| HUD FMR | County used where ZIP published | ✅ **Closed Aug 22, 2026**, then **superseded Aug 30, 2026** — HUD no longer supplies the rent level at all, so its ZIP/county gap stopped mattering. See "The anchor moved" below |
| Zillow ZORI | Some ZIP series begin after the corpus's 2018-19 vintage, so a row's own listing month may have no observation at its own ZIP | 🟨 **Disclosed, not closed** — and much smaller than it looked. Measured Aug 30, 2026: the gap is 27% of training rows at ZIP grain, and a county-median fallback recovers 99.0% of it, leaving **0.3%** with no anchor. Where the fallback fires, `rent_anchor_county_level` says so at warn severity |
| Redfin | Metro used; a ZIP extract sits unused on disk | ✅ **Narrowed Aug 30, 2026 (U8.8), from a different direction than this row proposed.** The *appreciation series* stays metro and that remains correct — measured, the ZIP extract has a median of **2 sales per period** nationally, and a YoY growth rate off 2 sales is noise. The *benchmark* is now ZIP-level in New York and Chicago, sourced from county-assessor transaction records rather than from the unused Redfin ZIP extract: those carry every sale rather than a pre-aggregated median, so the sample question this row raised does not arise. Los Angeles and Cleveland keep the metro figure, disclosed per deal |
| NYC DOF / Cook Assessor | Parcel carried, ZIP used | 🟨 **By design, not a gap.** The deliverable is a *benchmark*, which needs a median over the subject's neighborhood and never needs to identify the subject's parcel — which is also why U8's Q3 priced this item at an address-to-parcel join it turned out not to contain |

---

## Kaggle rent corpus

`data/apartments_for_rent_classified_100K.csv` · UCI ML Repository, CC BY 4.0 ·
loader `tools/kaggle_data.py` (the **only** supported entry point)

| | |
| --- | --- |
| Raw rows | 99,492 |
| After `load_clean()` | **98,844** (de-duplicated, core-field-complete, rent-bounded) |
| Vintage | Dec 7, 2018 – Dec 26, 2019 |
| Geographic columns | `address`, `cityname`, `state`, `latitude`, `longitude` |
| **No county column. No ZIP column.** | Both are derived — see §2, "Two data gaps" |
| `address` populated | **8%** (92% null) |
| Source concentration | 91% `RentDigs.com` (90,428 of 98,844); 25 distinct sources |

**Geographic level, precisely.** Every row has a coordinate, but a coordinate is not an
address. For the 8% of rows carrying a street address the coordinate is likely
parcel-level; for the other 92% it is a city-area placeholder that many listings share —
one point in Jersey City stands in for 497 listings spanning $1,200–$5,240. `Comp.location_precision`
records which kind each comp is (`"address"` / `"area"`), and the report discloses the
composition of every comp set. The tag is **not** used to rank or filter: coverage is 42%
in Chicago, 5% in Los Angeles, 2% in Cleveland, so preferring addressed comps would empty
the Cleveland set.

### Used for — 1. Rent-model training

`tools/model/rent_model.py`, filtered to `config.TRAINING_METROS`.

| | |
| --- | --- |
| Rows in shortlist | 5,717 |
| Dropped: county unresolved / FMR missing / ratio bounds | 0 / 0 / 29 |
| Trained | **4,550** · Holdout **1,138** |
| Counties · fiscal years | 15 · FY2019–FY2020 |
| Columns consumed | `bedrooms`, `bathrooms`, `square_feet`, `price`, `latitude`, `longitude`, `time` |

The target is `price ÷ anchor-for-that-row's-ZIP-and-month`, **not** `price` — where the anchor is ZORI at that ZIP and month times the HUD bedroom step for its county (U11.3; it was county-and-fiscal-year FMR outright until Aug 30, 2026).
Reproduce with `.venv/bin/python scripts/train_rent_model.py --dry-run`.

### Used for — 2. Comp index

`scripts/build_comps_index.py`, filtered to `config.INDEXED_MARKETS` → ChromaDB.

| | |
| --- | --- |
| Listings indexed | **3,880** |
| Document granularity | One document per listing, **never chunked** (§6) |
| Embedded text | Description + amenity free-text |
| Carried as metadata | beds, baths, sqft, lat/long, `listed_epoch`, `location_precision`, source |

### Not used for

**Any dollar figure that reaches the report unmodified.** This is the invariant in §8:
the corpus is a 2018–19 scrape, so a raw rent or a mean of comp rents is a 2019 figure
that would appear in a 2026 report wearing no date. Every rent number passes through FMR
normalization first — including the comp cross-check, which normalizes each comp
individually rather than averaging them.

---

## HUD FMR API

`tools/hud_fmr.py` · live API + on-disk cache (`data/raw/hud_fmr_cache.json`) ·
token `HUD_FMR_TOKEN` · full detail in [`hud_fmr_client.md`](hud_fmr_client.md) (§9)

**Geographic level: county, by `entityid` = state FIPS + county FIPS + `99999`.**
Published by federal fiscal year (FY N runs Oct 1 N−1 → Sep 30 N), with rent figures for
Efficiency through Four-Bedroom. Nothing above four bedrooms exists, so a 5+ bedroom unit
is priced against the four-bedroom figure and `FlagKind.FMR_BEDROOM_CAP_EXCEEDED` says so.

> **ZIP resolution, and the vintage trap inside it.** Cook (Chicago), Los Angeles and
> Cuyahoga (Cleveland) are **Small Area FMR** counties — HUD publishes a separate
> schedule per ZIP, and within a single county those span roughly 2x. The pipeline
> anchors on them as of Aug 22, 2026. Richmond County (Staten Island) is not SAFMR and
> is county-only, which raises `FlagKind.RENT_ANCHOR_COUNTY_LEVEL`.
>
> **SAFMR coverage is younger than the rent corpus, and that nearly broke the change.**
> Los Angeles publishes 474 ZIP schedules for FY2026 and **zero** for FY2019; Cuyahoga
> went 0 → 126 over the same window. Only Cook had ZIP-level data in the corpus's own
> vintage (344 → 370). So ZIP resolution exists on the inference side and largely does
> not on the training side — and the two must match, because the model learns a *ratio*
> and a ratio to a ZIP denominator is a different quantity from a ratio to a county one.
> `rent_model._zip_anchor_tables` resolves this by carrying each ZIP's position *within
> its county* backwards from the current year and applying it to the row's own year's
> county FMR: the dollar level always comes from the row's own vintage, only the
> within-county shape is imported. Tested where both years exist — r = 0.873 (Cook),
> 0.771 (Philadelphia), median back-cast error 4.5% / 5.1%.

### The anchor moved on Aug 30, 2026 (U11.3), and this section is the before-and-after

**HUD FMR used to be the rent anchor outright.** Every rent figure was `ratio × FMR`, the
ratio learned against each training row's own county-and-fiscal-year schedule and
multiplied back by the subject's current one. U8.0 then measured the schedule rising
**+51.9%** against market rent's **+33.5%** since the corpus vintage — so the reference
the model learned against had drifted ~18 points away from the market it was pricing, and
that drift landed in every estimate.

**It is now `ratio × (market rent level × bedroom step)`**, where the level is Zillow's
ZORI at the subject's own ZIP and only the *step* — how a three-bedroom prices against a
two-bedroom in this county — comes from HUD. The schedule's own level cancels out of the
step, so its drift can no longer reach a rent figure. Both ends read the market index at
the same kind of month, so the vintage divides out where it arises rather than being
corrected afterwards; U8.4b's drift correction retired with the change.

| # | Role | Where | Which source, now |
| --- | --- | --- | --- |
| 1 | **Training denominator** — makes the target a ratio | `rent_model.build_training_frame` | ZORI at each row's own ZIP and own **listing month**, × HUD bedroom step for its county/fiscal year |
| 2 | **Inference anchor** — converts the ratio back to dollars | `agents/valuation_rent.py` | ZORI at the subject's ZIP, **newest observed month**, × HUD bedroom step (FY2026) |
| 3 | **Comp cross-check denominator** | `rent_model.anchor_comp_rents` | Same function as role 1, per comp, at each comp's own month |
| 4 | **Demo calibration** | `scripts/verify_demo_calibration.py` | Geocoded county, FY2026 |
| 5 | **Rent-growth series (U6)** | `tools/fmr_history.py` | HUD FY2017–2026 history — **still genuinely FMR**, see below |

Roles 1 and 2 are the whole rent-anchoring design and the change did not alter its shape:
train on a ratio that ages slowly, multiply by a current dated reference. What changed is
which reference, and role 3 is what keeps the cross-check a fair comparison rather than a
2019-vs-2026 vintage error.

**Role 5 did not move at U11.3 and moved at U9.3, which is the whole story of this
project's recurring defect in miniature.** Through U8 the forecast's rent-growth bands
still came from HUD FMR history (#16), on the argument that a series of the same
administrative figure over ten years is a legitimate rent-growth signal and a different
question from what today's rent *level* is. That argument was sound and it stopped
applying the moment role 2 changed reference: #16's own reasoning is *project forward the
anchor the estimate was built on*, and since #19 that anchor is ZORI. **Decision #21
(U9.3) re-sourced role 5 to ZORI's county median**, with FMR history kept as the fallback
where no ZORI county reaches back far enough to band. A premise corrected in one place and
left standing in another — see `design/evaluator.md` for the four defects that followed
from the eleven units it stood.

What follows below is the FMR-anchored design as it stood, kept because the measurements
in it are the evidence the change was made on.

**A fifth role lands at U6: the rent-growth series.** The API serves ten fiscal years
(FY2017–2026, verified for all three inference counties), which is a rent-native growth
series at county and ZIP resolution costing no new dependency. It is also the only
candidate consistent with the anchoring design by construction — the estimate is
`ratio × FMR`, so projecting the anchor forward while holding the ratio constant forecasts
rent by the same mechanism that produced it. **Caveat that U6 must handle:** FMR is an
administrative 40th-percentile figure, and the history contains year-to-year jumps far
larger than any single market moved — Chicago +19.0% in FY2024, Los Angeles +14.5%.
Zillow ZORI is the independent check (decision #16).

> **Measured at U6 (Aug 22, 2026), and this section previously called those jumps
> "methodology jumps rather than market moves." That attribution is not supportable from
> FMR alone and has been withdrawn.** Across a panel of the ten distinct HUD FMR areas
> behind this project's training metros, **every one of them moved in FY2024** (cohort
> median 11.65%, minimum 6.5%). Chicago's +19.0% decomposes into 11.7 points of
> cohort and 7.4 points of local movement — 61% of it is shared with every other market
> in the panel — and Los Angeles's +14.5% is mostly cohort. A cohort-wide move is equally
> consistent with HUD changing its methodology and with the 2021–22 market surge reaching
> an administrative series two years late, and nothing in FMR separates the two. So the
> screen `tools/fmr_history.py` implements measures **co-movement**, which is observable,
> and the report claims nothing about cause. ZORI, being market-observed, is what could
> attribute it.
>
> **A second finding matters more for the code.** The rent series' anomalous years are
> **FY2023 and FY2024**, not the calendar 2020–2022 window `config.ANOMALOUS_PERIOD`
> defines for the price series — those three fiscal years run at 2.73% / 5.22% / 3.09%
> against a 4.17% baseline, i.e. entirely ordinary. Applying the price window to the rent
> series would have dropped three normal years and kept both distorted ones. The two
> series carry separate windows for this reason.
>
> Reproduce with `scripts/fmr_history_evidence.py`. The panel is committed at
> `src/tools/data/fmr_cohort_panel.json`; it is ten large coastal/midwest areas, not a
> national sample, so the direction is trustworthy and the baseline level is not.
>
> **Attributed at U8.0 (Aug 28, 2026), by the ZORI pull this note said was what could do
> it.** Market rent rose **+33.5%** since the corpus vintage while the FMR schedule rose
> **+51.9%** — so the administrative series outran the market it prices by 18.5 points,
> which is the attribution this screen deliberately declined to make from FMR alone. The
> consequence is not confined to the screen: the rent model learns a ratio against the
> vintage schedule and multiplies it by today's, so **every uncorrected estimate read
> high**. U8.4b corrects it per-ZIP at prediction time (`tools/rent_drift.py`) and
> discloses the factor; measured corrections run 0.744 (Los Angeles 90026) to 0.934
> (Bedford-Stuyvesant 11216).

---

## Redfin sale-price medians

`data/redfin_property_types_monthly_all_metros_multi_family_2_4_units_2018_Jan_to_2026_Jun.csv`
· loader `tools/redfin_data.py`

| | |
| --- | --- |
| `REGION TYPE` | **Metro only** — 943 metros nationally, filtered to 4 |
| `PROPERTY TYPE` | `Multi-Family (2-4 Units)` only |
| `FREQUENCY` | Monthly |
| Range | Jan 2018 – Jun 2026 (102 periods) |
| Rows after filtering | **408** (4 metros × 102 periods) |
| Columns used | `MEDIAN SALE PRICE NSA ($)`, `HOMES SOLD` |

**New York was absent from this filter until Aug 29, 2026, and the absence was reported
downstream as a fact about Redfin (U8.4c).** The mapping was written when §2 scoped the
price series to the inference trio, before New York was indexed as the sparse-comps
case, and it was never revisited — so `benchmark_unavailable_reason` said "Redfin's
extract does not cover this city" about a metro the extract covers with **102
fully-populated months at 700–950 sales each**. The membership now lives in
`config.REDFIN_TARGET_METROS`, is asserted equal to `INDEXED_MARKETS`' own label set, and
`load_redfin` raises if a configured region is missing from the file rather than
returning an empty frame that reads downstream as absent coverage.

**It is pre-aggregated. There are zero individual sales in it** — one median per
metro-month, carrying no square footage, unit count, or condition. That is why decision
#15 declined to produce a property-level `value_estimate` from it: the same figure would
describe a 2-unit duplex and a 4-unit building in the same metro.

> A **ZIP-level** Redfin extract for the same property type is on disk at
> `data/old/redfin_property_types_monthly_all_zips_multi_family_2_4_units_key_metrics_2024_Jan_to_2026_Jun.csv`
> (48 MB, Jan 2024 – Jun 2026) and is **not used, correctly.** §2 rejected the ZIP tier
> for the appreciation series on sample-size grounds, and the full extract bears that out:
> median **2** homes sold per ZIP-period, 75th percentile 4. A year-over-year growth rate
> computed off two sales is noise, so metro is the right tier for U6 and that is settled.
>
> The narrower question — whether the *market benchmark*, which is a level rather than a
> growth rate, could use ZIP where volume allows — is genuinely open but small. The three
> demo ZIPs carry 15 (90026), 42 (60647) and 35 (44109) sales per period, which is ample
> for a median. It would make an already-labelled reference figure more specific; it would
> not change any estimate.

### Used for

- **Market benchmark** in the report (`agents/valuation_rent.py`) — smoothed over
  `config.REDFIN_ROLLING_WINDOW_PERIODS` (3), because Cleveland's month-over-month median
  swings 6.9% (max 14.4%) against 1.5% in Chicago
- **Price appreciation forecast** — U6, `agents/scenario_forecast.py` is still a stub.
  **Price only.** §1 originally had this series driving *rent* growth too; measured, rent
  and price growth are negatively correlated (pooled r = −0.309 across the trio), so rent
  growth comes from HUD FMR history instead. Decision #16, §2's Problem 2
- **Demo asking-price calibration** (`scripts/verify_demo_calibration.py`)
- **MCP reference server** (`mcp_server.py`, decision #13)

### Not used for

**Any rent figure, ever.** §2, Problem 2: Redfin tracks *sale* prices, and home-price
appreciation diverges from rent growth over multi-year windows — most visibly 2020–2022,
when low rates pulled price growth far above rent growth. Using it to adjust a rent
number would import interest-rate-driven price dynamics into a quantity they do not
explain.

---

## Census Geocoder

`tools/geocoding.py` · live, free, no key

Two tiers, and the caller discloses which one produced a result:

| Tier | Geographic level | Flag raised |
| --- | --- | --- |
| `CENSUS_GEOCODER` | Parcel / street address | none |
| `CITY_CENTROID` | City centroid, computed from the corpus itself | `COORDINATES_FROM_CITY_CENTROID` |

Feeds `DealTerms.latitude/longitude` for the **subject property only**. Comps are never
geocoded — they carry the corpus's own coordinates.

## Census ZCTA boundaries

`tools/zcta_crosswalk.py` · `cb_2020_us_zcta520_500k` (67 MB, cached) · 33,791 polygons

Point-in-polygon join, coordinate → 5-digit ZCTA, so a rent figure can be anchored at ZIP
resolution rather than county. Added Aug 22, 2026; see "The sub-metro gap" above.

**GENZ2020 rather than 2023** because Census publishes no ZCTA layer in the 2021–2023
cartographic releases — verified by listing the directories, not assumed. Generalized
(1:500,000) rather than full-resolution TIGER, matching the county file's reasoning.

**A miss is cheap here, unlike the county join.** A county miss means no estimate at all,
so `county_crosswalk` snaps to the nearest county within five miles. A ZCTA miss just
falls back to the county schedule the caller would have used anyway, so there is no
nearest-ZCTA tolerance — guessing at a boundary would buy nothing and cost precision that
looked real. `None` means "use the county anchor," not "failure."

**ZCTA is not ZIP**, and this is the approximation to keep in mind: USPS ZIPs are
collections of mail *delivery routes*, not areas, and USPS publishes no polygons at all.
Census ZCTAs approximate them by assigning each census block its most common ZIP. Most
match; PO-box-only ZIPs have no ZCTA. HUD's SAFMR is keyed on real ZIPs, so a lookup can
miss a ZIP that genuinely exists. Measured on the training set: 5,717 of 5,717 rows
resolved to a ZCTA, and every ZCTA in a SAFMR county was present in HUD's list — zero
misses, though that is a property of these metros rather than a guarantee.

## Census county boundaries

`tools/county_crosswalk.py` · TIGER/Line `cb_2023_us_county_500k` (11 MB, cached)

Point-in-polygon join, coordinate → county FIPS → HUD `entityid`. Replaced a
hand-maintained city→county table on Aug 15, 2026, so a multi-county city now resolves to
the county the point actually falls in rather than a "principal" county.

**Returns `None` throughout New England** (`TODO(geography)`): HUD prices those six states
by town, and a county polygon cannot produce a town-level entityid. A `None` here becomes
`FlagKind.RENT_ANCHOR_UNAVAILABLE` and **no rent estimate at all**.

---

## The sub-metro gap — found by writing this page, closed the same day

Two rows of the map originally had a gap between "finest geography carried" and
"geography used." The HUD row's was the significant one, and it had survived three units
unnoticed:

- **HUD FMR** carried ZIP-level schedules for all three inference counties. The pipeline
  read the county-wide figure.
- **`RENT_MODEL_FEATURES`** deliberately excludes any market identifier, so the model
  cannot represent location at all. That remains the right call — a metro dummy would let
  it memorize a per-market dollar level, defeating the ratio design — but it means *the
  FMR anchor is the only channel through which location enters a rent estimate.*

County-level anchor + location-blind model meant **nothing in the pipeline could
represent sub-metro rent variation.** The measured cost: the modelled rent sat 21.6% /
30.4% / 40.0% below the local comp median in Echo Park, Logan Square and Ohio City — all
neighborhoods that genuinely rent above their metro median.

**What closing it required.** A ZCTA polygon join (`tools/zcta_crosswalk.py`, mirroring
the county crosswalk), a bulk ZIP schedule fetch (`hud_fmr.get_fmr_zip_table`, no extra
HTTP requests — the SAFMR payload already carries every ZIP), back-casting to reconcile
the vintage mismatch above, and one shared `anchor_for_row` used by training, the comp
cross-check and inference alike so the three cannot drift onto different denominators.

**Result, and it is a partial win rather than the clean one first reported.**

| Metro | Training vintage has ZIP FMR? | Divergence before | After |
| --- | --- | --- | --- |
| Chicago (Cook) | **Yes** — 344 ZIPs in FY2019 | −30.4% | **−9.9%** |
| Los Angeles | No — 0 in FY2019, 474 in FY2026 | −21.6% | −21.0% |
| Cleveland (Cuyahoga) | No — 0 in FY2019, 126 in FY2026 | −40.0% | −39.6% |

Only the county with published ZIP data in the *corpus's own vintage* improved, and it
improved a lot. The other two are anchored at county resolution on both sides and raise
`FlagKind.RENT_ANCHOR_COUNTY_LEVEL`.

**An intermediate version of this looked much better and was wrong**, which is worth
recording because the mistake is the one this project keeps having to catch. Back-casting
the ZIP relativity to every county produced convergence across all three markets
(−10.7% / −14.3% / −13.9%) and that was briefly reported as success. It was an artifact:
the same reconstructed ZIP schedule normalizes *both* the training rows and the comps, so
a shared error cancels in the comparison between them while remaining in the estimate.
The independent check is whether the anchor explains rent variation at all, measured as
dispersion in the rent-to-FMR ratio:

| ZIP schedule source | n | CV county | CV ZIP | Change |
| --- | --- | --- | --- | --- |
| **published** | 1,109 | 44.3% | **35.9%** | **−19.1%** |
| back-cast | 4,281 | 34.0% | 36.2% | +6.6% |

The published anchor absorbs local rent level as intended; the reconstructed one adds
noise. `config.RENT_MODEL_BACKCAST_ZIP_FMR` is therefore `False`, with the machinery kept
and the measurement recorded beside it.

**What it cost.** Holdout dollar MAE $519 → $524, R² 0.173 → 0.159, on 1,105 ZIP-anchored
rows of 5,686. Small, and expected for the same reason as before: variation moved into
the denominator is variation three structural features no longer have to explain.

**One correctness constraint this exposed.** Inference may only anchor at ZIP for a county
the model was *fit* on at ZIP resolution — not for one HUD happens to publish ZIP
schedules for today. The persisted training report carries `zip_anchored_counties` and
`agents/valuation_rent.py` gates on it. Without that gate a Los Angeles subject would
multiply a county-relative ratio by a FY2026 ZIP-level figure.

**Three approximations this rests on**, each disclosed at its site: ZCTA is not ZIP (USPS
publishes no polygons); the boundary file is 2020 vintage; and 92% of corpus coordinates
are city-area placeholders, so for those rows this resolves the placeholder's ZIP rather
than the property's.

## The same gap on the price side — closed for two markets of four (U8.8, Aug 30, 2026)

The section above is about rent. The **price** benchmark had the identical shape of
problem for longer: `ValuationDetail.benchmark_median_sale_price` was one Redfin median
per *metro*, so every 2-4 unit property in Chicago was read against the same number. What
closed it is county-assessor transaction records, aggregated per ZIP into a committed
table (`scripts/build_sale_benchmarks.py` → `tools/data/zip_sale_benchmarks.json`, read
by `tools/sale_benchmarks.py`).

| Market | Route | Local tier? |
| --- | --- | --- |
| **New York** | NYC Open Data `w2pb-icbu` — ZIP, unit count and sale price in one table | ✅ 164 ZIPs, 27,309 sales since 2023 |
| **Chicago** | Cook County `wvhk-k5uv` (sales) joined to `nj4t-kc8j` (parcels) on an exact `pin`, 96.8% matched | ✅ 140 ZIPs, 18,251 sales |
| **Los Angeles** | — | ❌ California rolls publish **assessed value** under Proposition 13, not transaction price. A different instrument; not substituted silently |
| **Cleveland** | — | ❌ Not in scope for this pass |

**Three properties of this worth carrying**, because each is the kind of thing that
misleads if it is not stated:

- **The two markets do not define multi-family identically.** New York publishes a unit
  count, so its rows are 2-4 units with no commercial space — Redfin's own definition.
  Cook publishes a property *class*, and the closest, 211, spans **2-6 units**; neither
  Cook dataset carries a unit count to narrow it. The definition travels with each figure
  into the report rather than being averaged away.
- **Cook's own non-arm's-length screens are used** (`is_multisale`,
  `sale_filter_deed_type`, `sale_filter_same_sale_within_365`, `sale_filter_less_than_10k`)
  rather than a price floor invented here — the publisher's judgment about which
  transfers are not market sales, better sourced than this project's own would be.
- **Neither dataset carries a licence field in its Socrata metadata.** Admissibility under
  §8 rests on the "public record" clause rather than on an open licence, and each figure
  carries the issuing office's attribution into the report.

**It makes the demo listings look cheap, and that is #11 showing through rather than a
defect.** Those asking prices were set *from* the metro median, so against their own ZIP
they read low — a Chicago Uptown fixture asking $530,000 sits 39% below ZIP 60640's
$867,500 median while that ZIP itself runs 77% above the Chicago metro's $490,903. The
figures stand as committed and the gap is written up rather than calibrated away.

## Metro scopes

Three different scopes, each answering a different question. They are **not**
interchangeable, and conflating them is the most common way to misread a row count.

| Scope | Count | Defined at | Question it answers |
| --- | --- | --- | --- |
| `INFERENCE_METROS` | 3 | `config.py` | §2's original inference trio (Chicago / LA / Cleveland) |
| `REDFIN_TARGET_METROS` | 4 | `config.py` | Which markets have a Redfin appreciation series and benchmark? |
| `TRAINING_METROS` | 8 (6 states, 14 city patterns) | `config.py` | Which listings does the regression learn from? |
| `INDEXED_MARKETS` | 4 | `config.py` | Which listings can be retrieved as comps? |

`INDEXED_MARKETS` is the trio **plus New York**, indexed deliberately as the sparse-comps
case rather than excluded. Until Aug 29, 2026 this section said that is "why Staten Island
returns comps and a rent estimate but **no market benchmark** — outside Redfin's
coverage." That was wrong, and the row above records the correction: New York is inside
Redfin's coverage and was outside *this build's filter*. Staten Island now gets a
benchmark and a price forecast; what it still lacks is comps, which is the real gap.

Training is a superset of inference by design: the model predicts a *ratio*, so it
benefits from markets it will never price, while comp retrieval needs density in the
specific subject market (§2, "Training vs. Inference").

---

## Invariants

Four rules connect these sources. Each exists because breaking it produces an answer that
looks right.

1. **Never let Redfin data touch a rent dollar figure.** Sale-price dynamics ≠ rent
   dynamics.
2. **Never let an unanchored Kaggle dollar figure reach the Summarizer.** Every rent
   number passes through FMR normalization first — including comp-derived ones.
3. **No FMR, no estimate.** There is no coarser fallback. A subject whose county will not
   resolve gets a critical flag and no rent figure, because the only available substitute
   is a raw comp mean, which rule 2 forbids.
4. **`tools/kaggle_data.load_clean()` is the only entry point to the corpus.** One
   cleaning path, so a data-quality decision cannot drift between the index, the
   regression, and the evidence scripts.
