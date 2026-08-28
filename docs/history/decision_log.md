# Decision Log

**Why the system is built the way it is — including what was originally thought and why
it changed.** This is the historical record split out of
[`implementation_plan.md`](../implementation_plan.md) §7 on Aug 24, 2026. The plan is a
plan of record and states the *current* design; this file holds the reasoning that
produced it, the premises that were measured and disproved, and the corrections made
along the way.

**Section numbers (§1–§9) and decision numbers (#1–#17) throughout this repository refer
to [`implementation_plan.md`](../implementation_plan.md)** — §-numbers to its sections,
#-numbers to the decisions register in its §7. That register is the index to this file.

**Read this on demand, not by default.** Nothing here is needed to implement a unit. It
is here for three cases: a decision is being revisited, a premise needs checking before
it is relied on again, or a reader wants to know why an obvious-looking alternative was
not taken.

**Organised by the part of the system each decision affects**, not by date, because that
is how they get looked up. Every entry names its decision number, the unit it landed in,
and its date, so a chronological or by-unit lookup still works via search.

## Contents

- [Data & sources](#data--sources) — #2, #4, #7, #11
- [Geography & anchoring](#geography--anchoring) — #10
- [Retrieval](#retrieval) — #5, and U4's design and ablation record
- [Rent & valuation](#rent--valuation) — #15, and the deferred model-form probe
- [Forecasting & reasoning](#forecasting--reasoning) — #12, #13, #14, #16, #17
- [Orchestration & control flow](#orchestration--control-flow) — #1, #6, #9, U2's findings, and U7's Critic record
- [Models & infrastructure](#models--infrastructure) — #8, #13, and the free-tier accounting
- [Evaluation & demo](#evaluation--demo) — #3, and U8's standing
- [Appendix — build inventory](#appendix--build-inventory-as-of-u6)

---

## Data & sources

Decisions #2 (inference metro trio) and #7 (Redfin minimum-price floor) were taken and
evidenced entirely inside [`../design/data_strategy.md`](../design/data_strategy.md) §2,
including the worked example of a metro-selection hypothesis held confidently, tested,
and found wrong. They are not duplicated here.

### #4 · U5 · Aug 21, 2026 — training metro shortlist

**Decision #4 detail (closed Aug 21, 2026) — eight training metros.** The shortlist is
**Los Angeles, Cincinnati, Chicago, Cleveland, Jersey City/Newark, New York, Pittsburgh,
and Philadelphia**: every metro in §2's density table carrying ≥200 usable rent
listings, minus Boston. Roughly 5,717 usable rows across eight structurally different
markets, and a superset of the inference trio as §2 requires.

**The selection rule is deliberately not the one §2's table implies.** That table applies
two bars to every metro — Kaggle rent listings *and* Redfin 2–4 unit sales volume — and
the verdict column marks a metro failed if it misses either. That is the right rule for an
*inference* metro, which needs both comps and an appreciation series. It is the wrong rule
for a *training* metro, which needs neither: the regression consumes Kaggle rent rows and
HUD FMR, and touches Redfin at no point. Applying the inference rule to the training
shortlist would have discarded **Cincinnati**, whose 798 usable rent listings make it the
second-densest rent corpus in the extract, on the strength of a sales figure the rent model
never reads. Recorded because the table's own verdict column says `❌ sales volume too
thin` next to a metro this decision selects, and that disagreement should look deliberate
rather than careless.

**Boston is excluded as blocked, not as unselected**, which is a different status from the
"viable but not selected" §2 assigns it. Since the Aug 15 crosswalk rewrite, a resolved
point in any of the six New England states returns `None` (`TODO(geography)`), so Boston's
599 rows cannot be FMR-normalized. Including it without building the Census
county-subdivision layer first would not fail loudly — the rows would drop at
normalization and the training set would be quietly 599 rows smaller than the shortlist
claims. Building that layer was considered and declined here on schedule grounds; it stays
`TODO(geography)`.

**One quantity had to be re-measured before U5 trained anything — done Aug 22, 2026.**
§2 quoted 21,768 complete rows for "a candidate ~10-metro training shortlist," which did
not reconcile with the per-metro counts in the same section: those are usable rows after
de-duplication, completeness filtering, and rent-bound trimming, and the 21,768 predates
the two data defects corrected on Aug 8. Per §8, a training-set size nobody measured is
not a measurement, so it was re-derived from `tools/kaggle_data.py` against the actual
shortlist rather than inherited. **Result: 5,717 usable rows**, reproducible with
`scripts/train_rent_model.py --dry-run`, and the older figure is now identified in
`config.py` as a state-level rollup — the six states these metros sit in hold 22,323
usable rows between them, which is what it was actually counting.

**What this cost to implement** turned out to be less than estimated. The original note
here budgeted for writing word-boundary city patterns for the five metros outside the
inference trio; they already existed in `scripts/verify_metro_selection.py` from the
Aug 8 density check and only had to move into `config.py` as `TRAINING_METROS`. The
remaining cost is one HUD FMR pull per distinct county — bounded by county count rather
than row count, cached by `tools/hud_fmr.py`, and measured at 15 counties across two
fiscal years, so 30 calls.

**The reasoning behind the eight-metro shortlist was tested (Aug 22, 2026), and it holds
where it matters.** Reproduce with `scripts/metro_shortlist_ablation.py`. The test holds
the evaluation set fixed and varies only what the model trains on; comparing each variant
against its own holdout would confound the training choice with the test choice.

Three questions, because "does breadth help" has different answers depending on what is
being predicted:

| Test | trio only | five metros | eight metros |
| --- | --- | --- | --- |
| Held-out inference-trio properties, 20 splits | $519.45 (0/20) | **$515.49 (19/20)** | $517.72 (1/20) |
| Held-out New York properties, 20 splits | $1,064.79 | — | $1,068.47 |
| Transfer to an unseen metro (leave-one-out) | worse on 3/3 | — | **better on 3/3** |

**On the metros the system prices, the three variants are within $4 of each other** —
under 1%, and small against a ±$12 spread across splits. Breadth neither helps nor hurts
there in any way worth acting on.

**On a metro the model has never seen, breadth clearly wins.** Excluding the target metro
entirely and predicting it: Los Angeles $537.87 with eight metros against $612.17 with the
trio, Chicago $612.23 against $635.97, Cleveland $455.85 against $457.92. This is the
generalization case, it is the case §2's diversity argument was actually about, and the
eight-metro set wins all three.

**So decision #4 stands, and so does its rationale.** The shortlist is kept.

**One number worth carrying forward as a limitation:** New York predicts at ~$1,065 MAE
against ~$518 for the trio — twice the error, under either training set. New York is in
`build_comps_index.INDEXED_MARKETS`, so a Staten Island subject reaches the rent model and
gets an estimate roughly half as reliable as a Los Angeles one. That is a disclosure
requirement for U7/U8, not a training-set problem: no shortlist tested here fixes it.

**Correction, recorded rather than quietly fixed.** The first run of this analysis
reported the opposite on every count — that trio-only training beat eight metros
everywhere, by $12 on the trio and $36 on New York. That was a defect, not a finding.
`kaggle_data.filter_markets` concatenates with `ignore_index=True`, so its result cannot
be joined back to the frame it came from; taking `.index` off it and passing that to
`df.loc[...]` selected rows *positionally*. The "trio" set so constructed held 2,354 Los
Angeles rows, 1,233 Ohio rows mixing Cleveland with Cincinnati, and **no Chicago at all**.
The script now computes membership as a boolean mask on the frame's own index and prints
its trio composition by state on every run, so the same failure would be visible rather
than silent. Recorded because a reversed result that was acted on is exactly the class of
error §8's evidence standard exists to catch, and because the corrected answer happens to
agree with the original decision — which is the case where a quiet fix would have left no
trace that anything had been wrong.


### #11 · U3 → U8 · Aug 16, 2026 — grounding for demo and evaluation deal terms

**Decision #11 detail (opened and half-taken Aug 16, 2026).** Raised in review of U3's
demo listings, whose deal terms — price, rents, unit mix — were invented. The literal
program requirement was satisfied (nothing scraped, nothing proprietary), but the
objection was sharper than compliance: *even synthetic examples should have some basis in
reality*, and these numbers had none recorded.

The concern is not cosmetic, because these terms are load-bearing. `bedrooms` and
`square_footage` are hard filters on comp retrieval; `price` and `unit_rents` are what U5
will value the deal from. An implausible subject produces a confident-looking report about
a property that could not exist — uncomfortably adjacent to the fabrication failure this
system exists to prevent, with the difference that the *grounding* (comps, FMR, Redfin)
stays real and only the subject is hypothetical.

**Taken now: calibrate against sources already in the repo.** Each demo figure names its
basis in `demo_deals.py`, and `scripts/verify_demo_calibration.py` re-derives it live —
asking price against Redfin's median sale price for Multi-Family (2-4 unit) in that
metro, stated rents against HUD's FY2026 FMR for the county *the listing's own address
geocodes to*, so the check exercises the real geocoding path rather than a county written
into the fixture. Behaviour across all five demo deals was unchanged by the recalibration,
which is the expected result: the figures were already roughly right, and what they
lacked was provenance rather than accuracy.

**One correction worth recording, because it is the mistake this project is about.** The
review initially appeared to show the Chicago demo's rents sitting 27% above market. It
did not: that gap was measured against the *2018-19* Kaggle corpus median while the rents
were current-dollar figures. Against FY2026 FMR for Cook County they sit within 4%. The
error was comparing two vintages — precisely what §2's FMR-anchoring design exists to
prevent — committed while arguing for better data discipline. It is also why demo rents
are anchored to FMR rather than to the corpus: the corpus is seven years stale, and
calibrating current listings against it would build the vintage gap into the demo.

**Two limits of this, stated rather than left to be discovered.** FMR is a 40th-percentile
rent, not a market median, so calibrated listings sit at the affordable end of their
market by construction — acceptable for a demo, not acceptable for an accuracy benchmark.
And there is still **no ground truth for the value estimate**: a demo deal has a defensible
asking price but no known correct answer, so U5's valuation cannot be scored the way its
rent model can.

**Planned, not taken: real for-sale deals from county public records.** Rejected
alternatives first. *Scraped listings* carry ToS exposure, go stale, and would place real
current offers in a public repository. *Real listings copied by hand* share the staleness
problem and still supply no known-correct value. **County assessor open data** (Cook, LA
County, NYC) dominates both: legally unambiguous, free, stable, and richer in exactly the
fields needed — address, sale price, unit count, square footage, year built.

Scheduled at **U8**, where evaluation evidence lands, and placed on §6's cut list at
position 2. That placement is deliberate: U8 is the one unit protected from cutting, and
attaching a new data source with its own cleaning and coverage work to it would put the
protected unit at risk. If it is cut, the rent model still has real ground truth from a
held-out slice of the Kaggle corpus — real listing text, real rents, which is also what
the Checkpoint 1.1 feedback asked for ("lock one metro and a small held-out test set
early") — and the value estimate is documented as unvalidated.

**Settled Aug 16, 2026, before the work rather than during it.** The open question was
whether this breaches the standing data rule. It does not, and §8 now says why rather
than leaving it to a judgment call at implementation time: the rule turns on "public,"
which is defined there as *openly licensed or a public record* — not *publicly visible*.
Assessor records are the first; scraped listings are only the second. So the planned work
is admissible under the standard as written, and scraping remains excluded by the same
sentence rather than by a separate prohibition.

Worth noting the rule was also relaxed from an absolute to a norm in the same pass, which
is what makes a recorded exception possible at all. That is the general pattern this log
exists for, applied to the standards document itself.


---

## Geography & anchoring

### #10 · U3 · Aug 10–15, 2026 — geocoding source, and the county crosswalk rewrite it caused

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

**Closed Aug 11, 2026 — option (1)+(2) as recommended, with one change from the original
sketch.** Option 2 as written proposed "a city-centroid table extending
`county_crosswalk.py`" — a hand-curated table, mirroring how the county gap was closed.
Built instead: `city_centroid()` in `tools/geocoding.py` computes the mean lat/lon of a
city's own listings directly from the Kaggle corpus (`tools/kaggle_data.load_clean()`),
rather than a maintained constant. Two reasons this is better than the sketch, not just
different from it: it needs no hand-curation or per-city verification the way the FIPS
table does, and it is a tighter-fitted centroid than an arbitrary city-hall point — it
sits where the corpus's own comp density actually is, which is what the radius search
downstream cares about. It also covers every city the corpus has listings for rather
than only the 29-city crosswalk shortlist. `geocode_census()` (primary) and
`city_centroid()` (fallback) share one normalization path with the county crosswalk —
`county_crosswalk.normalize_city/normalize_state`, promoted from private to public for
exactly this reuse — so the two lookups can't drift apart on how they fold the same
corpus's city names.

Verified live (`scripts/pull_geocode_sample.py`, real calls, not mocked): a complete
street address in each inference-trio metro resolves via the Census Geocoder; a
city/state pair with no street number correctly finds no Census match and falls through
to the corpus centroid; a city genuinely outside the corpus's coverage correctly resolves
to neither and returns `None` rather than inventing a coordinate. Two new flag kinds
carry the disclosure — `COORDINATES_FROM_CITY_CENTROID` (warn) and
`GEOCODING_UNAVAILABLE` (critical) — added to `state.py` alongside
`COUNTY_FROM_PRINCIPAL_COUNTY` on the same precedent: the enum member exists ahead of the
code that raises it, same as that one did in U1.

**What's still open, and it's deliberately not closed here.** The tool is built and
verified in isolation; it is not yet called from `agents/extractor.py`. Wiring it in
would resolve real addresses for `test_flag_propagation.py`'s `LISTING_MISSING_PRICE`
fixture, which currently relies on a *complete* address plus *withheld* coordinates to
exercise the Comps agent's no-coordinates short-circuit without touching Chroma. That
suite is the one thing in this project that must never fail for the wrong reason (§8), so
wiring geocoding into the stub extractor now would silently change what it tests rather
than extend it. That wiring — plus updating the fixture to a genuinely ungeocodable
address so the suite keeps testing the same guarantee on purpose — is U3 work, tracked as
the `TODO(U3)` in `extractor.py`.

**Follow-on, Aug 15, 2026 — the county crosswalk (§2, "Two data gaps," Gap 1) is
replaced by a consequence of decision #10.** Reviewing decision #10 surfaced that a
listing's `city` field is sometimes a neighborhood rather than the postal city ("Wynwood"
for Miami) — real estate marketing convention, not a parsing bug. Testing it directly
(`tools/geocoding.py`'s primary path) showed comp retrieval is unaffected — it's
coordinate-based, and Census resolves the correct point off street + ZIP regardless of
the city token supplied — but `county_crosswalk.py`'s old (city, state) string lookup
would still miss, and Census's own response carries a canonical city
(`addressComponents.city`) that was never being read back. Comparing two fixes — correct
the string before the crosswalk lookup, versus resolve county directly from the subject's
already-derived coordinates — showed the second strictly dominates the first: it doesn't
depend on the crosswalk table's coverage at all (Miami resolved correctly despite never
having a table entry), it's immune to the city-string question entirely, and it works
regardless of which geocoding tier produced the coordinate. It's also a strict accuracy
improvement even for the cities the old table did cover, since it resolves the *exact*
county for a point rather than the table's principal-county approximation for the ten
cities spanning several.

**Built.** `tools/county_crosswalk.py` is rewritten in place: `lookup_county_fips` now
takes `(latitude, longitude)` and does a point-in-polygon join against Census's county
boundary file (cached locally after the first pull) instead of a hand-maintained
29-city table. `normalize_city`/`normalize_state` are unchanged and still serve
`tools/geocoding.py`'s corpus-centroid fallback. Cost was measured, not assumed — the
original §2 text called the spatial-join scale-up path "not worth the dependency"
without testing it; `geopandas` installs in ~3.3s from prebuilt wheels at ~31MB, and the
county boundary file loads in ~3.3s and is cached after that (see [`../design/data_strategy.md`](../design/data_strategy.md)'s
Gap 1 for the full accounting). Verified live in `scripts/verify_county_geometry.py`:
reproduces all three inference-trio entityids exactly, resolves Miami-Dade correctly
where the old table had nothing, and resolves the old table's two hand-special-cased
hard cases (Richmond VA's independent-city status, Denver's consolidated city-county)
correctly with no special-case code — each cross-checked against a live HUD
`listCounties` response, not just against the geometry's own claim.

**Carried forward as future work, not solved:** HUD prices FMRs by *town*, not county,
in the six New England states, and a county polygon join cannot produce the town-level
entityid that regime needs. A resolved point landing in one of those six states now
returns `None` — declining rather than guessing, the same discipline `geocoding.py`
applies to an uncovered city — rather than emitting a plausible-looking wrong entityid.
Tagged `TODO(geography)` at the site, same status the old table already carried for New
England (verified for Boston only). Doesn't block the inference trio (none are New
England).

**One accepted narrowing, stated because it's a real behavior change, not a pure
refactor:** county resolution now runs on coordinates, so a subject with a known city but
no resolvable geocode gets no `county_fips` either, where the old table could still
resolve one from the city string alone. Given `vector_store.query_comps` already
hard-requires coordinates for comp retrieval, a coordinate-less subject was already this
system's worst case; this removes one of the two things such a subject could still get
independently, not one of the two paths that mattered independently of each other.


---

## Retrieval

Decision #5 (X = 2.0 mi, Y = 8, Z = 4) was tuned in U4 against measured density curves;
its rationale is carried in `src/config.py` at the constants themselves rather than
duplicated here.

### U4 · Aug 8–9, 2026 — retrieval design, acceptance criteria, and the ablation correction

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

---

## Rent & valuation

### #15 · U6 · Aug 22, 2026 — no property-level value estimate

**Decision #15 detail (Aug 22, 2026) — no property-level value estimate.** The question
arrived as a loose end rather than a decision: `DealState.value_estimate` had a field, a
Summarizer row reading *"not produced — valuation agent unbuilt (U5)"*, and no documented
method anywhere. Three options were weighed, and the measurement that settled it is worth
recording because the intuition pointing the other way was reasonable.

The objection to a Redfin-anchored estimate was that a metro median is coarse. The
counter-objection was sharper: **this project's comps are already coarse**, since 92% of
the corpus carries no street address and sits on city-area placeholder coordinates, so if
metro-level granularity disqualifies a value estimate it should equally disqualify the
comp-based rent work. Measured, that turns out to be false, and the distinction is not a
matter of degree:

| | Rent path | Redfin value path |
| --- | --- | --- |
| Observations exposed | 5,717 individual listings | **0** — extract is pre-aggregated |
| Rows available | one per listing | one median per metro-period (306 total) |
| Property attributes | beds, baths, sqft | none |

The comps' *coordinates* are coarse; their *rents* are not. Inside Chicago's busiest
coordinate, 150 listings share one point and their rents span $760–$6,995 — CV 48.7%
against 49.7% for the whole metro. That coordinate carries almost no information, but
every row on it is still an individual rent with its own bed/bath/sqft, and that is what
the model consumes. Redfin's extract has no equivalent: `load_redfin` returns
`median_sale_price` and `homes_sold` per metro-month and nothing beneath it. A value
estimate built from it would return **the same dollar figure for a 2-unit duplex and a
4-unit building in the same metro**, not because adjustment was skipped but because
there is nothing in the inputs to adjust with.

Where the coarseness *can* be scored — rent, where both options exist — predicting the
metro median for every listing gives MAE $600 (Chicago) / $793 (Los Angeles) / $526
(Cleveland) against the model's $519. Los Angeles the model is 35% better; **Cleveland it
is a wash.** So a metro median is weak-but-real for rent. For value it is not
weak-but-real; it is the only thing there is.

**And there is a trap specific to this repo.** Decision #11 calibrated the demo asking
prices *to that same Redfin median* (`demo_deals.price_basis`). The latest Los Angeles
median is $1,048,866 and the LA demo asks $1,049,000; Chicago is $499,460 against
$499,000. Emitting the median as `value_estimate` would produce reports where the
estimated value matches the asking price to within $140 — reading as striking validation
while proving only that both numbers came from one source. That is the §8 failure this
project has now caught itself on three times: the `LA001` id-format ablation, the
2018-vs-2026 vintage comparison, and this.

**Taken:** the field stays `None`; the median is carried as
`ValuationDetail.benchmark_median_sale_price` and rendered under its own heading as a
market reference the asking price is read *against*, with the pre-aggregation stated in
the report itself. Smoothed over three periods rather than read off the latest, because
Cleveland's month-over-month median swings 6.9% (max 14.4%) against 1.5% in Chicago.

**Left open for U6, deliberately.** Decision #9 has the Scenario agent consuming
`rent_estimate`/`value_estimate`, so a null value estimate means U6 needs another
projection base. The asking price is the obvious candidate — an observed fact about the
property rather than an estimate, and *"pay $1,049,000 today, here is what the metro
multi-family trend implies"* needs no value estimate at all. Not settled here, because
U6 is where the appreciation evidence is and this decision should be made in front of it.

**Closed Aug 24, 2026: the asking price it is**, carried as
`ForecastDetail.projection_base_price` with `projection_base_source` naming it in words
so the report never implies a valuation happened. `value_estimate` is therefore `None`
permanently rather than pending, and nothing in the built system writes it.


### Cut list 1a · U5 · Aug 22, 2026 — rent-model feature engineering and model form

Deferred, not dismissed. Still on §6's cut list; this is the measurement behind that
placement.

**Rent-model feature engineering and model form** (deferred Aug 22, 2026 — keep it
deferred). The shipped estimator is a vanilla `LinearRegression` on three raw features
with no transforms, interactions, or regularization. Its weakness is *underfitting*,
not overfitting: measured train-vs-holdout gap is $0.04 on 896 rows per parameter, so
there is no variance problem to solve, only unused capacity.

Probed on the inference trio, same features and same data, 10 splits:

| Model form | MAE | R² |
| --- | --- | --- |
| `LinearRegression` (shipped) | $524 | 0.28 |
| Poly-2 + Ridge | $496 | 0.27 |
| Poly-3 + Ridge | $524 | **−13.3** |
| Gradient boosting | $446 | 0.49 |
| **Random forest** | **$434** | **0.52** |

So roughly **17% of rent error is available to model form alone**, with no new data and
no new features. Deferred anyway, for two stated reasons: the project's subject is agent
architecture rather than regression quality, and the choice deserves a closer look than
the schedule affords — the poly-3 row is the warning, where added capacity produces
genuine overfitting (R² −13.3) of exactly the kind the linear model cannot exhibit.
Any future pass needs proper validation rather than a single split, and should be
weighed against the §2 finding that location — the dominant driver — is unavailable in
this corpus at useful granularity, which may cap the real ceiling well below the probe.

---

## Forecasting & reasoning

Decision #13 (MCP) was taken in the same block as #12 and #14 and is recorded below with
them, because all three concern the Tree-of-Thought sub-system. It is cross-listed under
[Models & infrastructure](#models--infrastructure).

### #16 · U6 · Aug 22, 2026 — rent growth needs a rent source

**Decision #16 detail (Aug 22, 2026) — rent growth needs a rent source.** §1 describes
the Scenario/Forecast agent as *"Tree-of-Thought reasoning over rent-growth/appreciation
scenarios, informed by metro-level housing trend data."* §2's Problem 2 had already
warned, on general housing-market reasoning, that price and rent dynamics diverge. Tested
against this project's own data before U6 was built, the relationship is not weak but
**negative**: pooled r = −0.309 across 24 metro-years, negative in all three metros
independently, with price outrunning rent by 8.9 points across 2021–22. Detail and
caveats in §2.

**Taken: forecast the two quantities separately.** Redfin measures sale prices and stays
the source for price appreciation. Rent growth comes from **HUD FMR's published history**
— ten fiscal years at county and ZIP resolution, served by the client this project
already caches, so it costs no new dependency. It is also the only candidate that is
*architecturally* consistent: the rent estimate is `ratio × FMR`, so projecting the anchor
forward while holding the structural ratio constant forecasts rent by the same mechanism
that produced the estimate, with no second normalization basis and no new vintage problem.

**Its weakness is that FMR is administrative, not market**, and the history shows
year-to-year jumps larger than any single market moved — Chicago +19.0% in FY2024, Los
Angeles +14.5%. A "base case" resting on one of those would be wrong in a way a reader
could not see, so U6 must screen for them and disclose what it screened. **Zillow ZORI is
adopted as the independent
check** rather than the primary series: market-observed, monthly, ZIP-level, free, and it
doubles as the only available test of the rent model's largest unverified assumption —
that rent-to-FMR structure is stable over the ~7 years between the corpus and today.

**Corrected when U6 measured it (Aug 22, 2026), and the paragraph above is the second
version.** It originally read *"methodology jumps … that almost certainly reflect HUD
changing how it derives the figure rather than a market event."* That is an attribution,
and FMR cannot support it. Built into a panel of the ten distinct HUD FMR areas behind
this project's training metros, **FY2024 moved every one of them** — cohort median
11.65%, minimum 6.5%. Chicago's headline +19.0% is 11.7 points of cohort and 7.4 of
local, so 61% of the move it was named for is shared with every other market in the
panel; Los Angeles's +14.5% is mostly cohort. A cohort-wide move is equally consistent
with a methodology change and with the 2021–22 rent surge reaching an administrative
series two years late, and no test inside FMR separates them. So `tools/fmr_history.py`
screens for **co-movement**, which is observable, and says nothing about cause. This is
the same error class §8's evidence standard exists for: the original claim was plausible,
was never measured, and would have been printed in a report as fact.

**And the screen could not have reused the price-side window.** The rent series' shifted
years are **FY2023–24**; the calendar 2020–2022 window `config.ANOMALOUS_PERIOD` defines
for Redfin runs at 2.73% / 5.22% / 3.09% against a 4.17% baseline — three ordinary years.
Sharing one constant across the two series would have excluded the ordinary years and
kept both distorted ones. FMR lags because it is administrative: the FY2024 schedules
were published in Sept 2023 on 2021–22 data. Reproduce both findings with
`scripts/fmr_history_evidence.py`; the panel is committed at
`src/tools/data/fmr_cohort_panel.json`.

**Why forecast rent growth at all**, recorded because it was a fair question and the
answer is not obvious: with `value_estimate` deliberately null (decision #15), the price
side has no property-level base except the asking price, so **rent is the only quantity
this system can forecast from a figure it actually derived.** Dropping it would leave the
Scenario agent with nothing of its own to project, and decision #12 placed one of the
project's two Tree-of-Thought nodes here — a node with nothing to branch over cannot
satisfy Checkpoint 4.1's requirement that ToT be used where linear reasoning fails from
premature commitment.


### #17 · U6 · Aug 24, 2026 — enumerate the hypothesis space, do not sample it

**Decision #17 detail (Aug 24, 2026) — the ToT structure changed once the data was in
front of it.** Checkpoint 4.1 specified sampling *b*=5 hypotheses per expansion at
`TOT_TEMPERATURE = 0.7`. Building against the measured bands, that is the wrong
mechanism for this space, and three things follow.

**The space is enumerable, so it is enumerated.** Four framings — two rent treatments
(screen the FY2023–24 cohort shift or not) × two price treatments (exclude calendar
2020–22 or not) × one appreciation series — then nine band pairings under each. Asking a
model for five hypotheses over a four-point space makes it *invent growth rates*, and
every figure in this system must trace to a measured source. The Tree-of-Thought paper
distinguishes *sampling* thoughts i.i.d. (for rich spaces) from *proposing* them (for
constrained ones, where sampling returns duplicates); this is the constrained case.
Consequences: nothing is invented, the branching factor is a property of the evidence
rather than a knob, and **the pipeline stays deterministic end to end** —
`TOT_TEMPERATURE` is now unused, and `LLM_TEMPERATURE = 0.0`'s comment
*"deterministic by default; ToT overrides"* no longer has an exception to describe.

**Two search parameters had to become per-depth, and both were found by reading output
rather than by reasoning.**

- *Beam width.* At 3 everywhere, the three reported scenarios came from three different
  framings — so the Chicago report showed an optimistic rent of +19.03%/yr directly
  beneath a basis block stating FY2024 had been screened out, and 19.03% **is** Chicago's
  FY2024 figure. Scenarios resting on different treatments are not commensurable and
  cannot share one provenance statement. `TOT_FRAMING_BEAM_WIDTH = 1`.
- *Prune threshold.* At 0.40 everywhere, an evaluator applying ordinary skepticism scored
  all four Los Angeles framings below it and emptied the beam on a deal whose series were
  both fully available. A threshold asks *"did this survive contact with the data?"* —
  a real question about a pairing, a category error about a framing, since framings are
  enumerated from treatments the evidence supports and are all defensible by
  construction. `TOT_FRAMING_PRUNE_THRESHOLD = 0.0`; the level selects rather than
  filters.

**`AppreciationTier` was removed rather than trimmed.** It typed a fallback ladder with
one reachable rung: the ZIP tier is closed on sample size (median 2 homes sold per
ZIP-period) and no all-residential extract exists in this project — checked, including
`data/old/`. Keeping two unreachable members would advertise a fallback the build cannot
climb, which is a claim about the design rather than about the system. `src/enums.py`
existed solely to hold the type and went with it; `appreciation_source` now carries a
plain description of the series.

**What the search is worth, measured.** `scripts/forecast_evidence.py` compares the
search against a linear baseline — the first framing in enumeration order with the three
diagonal pairings, i.e. what a competent implementation without a search would emit.
Across all four subjects the search kept the first-enumerated framing **0 times** and
chose an all-diagonal pairing set **0 times**; on Cleveland the base case differs by
−22.0% on rent and +26.4% on price. The script states what it would have shown had the
search been decoration, and reports each of those outcomes whether or not it holds.


### #12, #13, #14 · U6/U7 · Aug 18, 2026 — ToT scope, MCP adoption, and branch-state persistence

**Decisions #12–#14 detail (Aug 18, 2026) — reasoning strategy, MCP, and branch state.**
Taken together while specifying U6 ahead of building it, and prompted by Checkpoint 4.1.
All three concern the same sub-system, so they are recorded as one block.

**#12 — ToT is adopted selectively, not globally.** The pipeline order
(Extractor → Comps → Valuation → Scenario → Critic) is fixed by data dependency: comps
cannot precede geocoding, valuation cannot precede comps. There are no alternative paths
to explore, so branching across the pipeline would multiply cost with nothing to select
between. Two nodes fail that test in the other direction:

- **Scenario/Forecast (U6)** faces genuine forks with no single correct answer, and a
  linear chain resolves them by whichever framing it reaches first, anchoring every
  downstream figure to it.

  > **Revised at build time (Aug 24, 2026).** This originally named two forks: the
  > 2020–2022 window and the `appreciation_source` tier ladder. **The tier ladder is not
  > a fork** — measured, it has one rung, and `AppreciationTier` was removed with it
  > (§5). What replaced it is better grounded: the window fork turns out to be *two*
  > independent windows, because the rent and price series are anomalous in different
  > years (FY2023–24 against calendar 2020–22), and beneath them sits the choice of which
  > rent band pairs with which price band. Since the two quantities are negatively
  > correlated here (r = −0.309), the diagonal pairing a chain emits is the one the data
  > argues against. Measured across four subjects in
  > `scripts/forecast_evidence.py`, the search kept the first-enumerated framing **0
  > times** and chose an all-diagonal pairing set **0 times**.
- **Critic consistency checks (U7)** — the four checks named in `_consistency_objections`'s
  `TODO(U7)` differ in cost and are not independent, so running all of them on every deal
  spends the expensive ones on deals that do not need them.

  > **Retired at build time (Aug 27, 2026, U7.7).** The premise held while the checks were
  > still the four named in U2's `TODO(U7)`. Q5 (`docs/tasks/task_list_u7.md`) found six
  > of eight candidate checks dead, already built elsewhere, or structurally impossible
  > to fail, and replaced them with interaction checks over the accumulated flag list
  > (U7.2) and a comp-attribute-drift check owned by `agents/comps_retrieval.py` (U7.3).
  > What shipped are pure functions of `state.flags` — no LLM call, no generated
  > candidates, and therefore nothing for a beam search to select between. The premise
  > this bullet argued from (differing cost, non-independence) no longer describes what
  > the Critic checks, so decision #12's Critic half is retired on evidence rather than
  > built: `agents/critic.py` never imports `tools/tot.py`. `TOT_TEMPERATURE`, the one
  > constant retained solely for this consumer, is removed; the rest of the ToT block in
  > `config.py` now documents Scenario/Forecast as its sole consumer.

Structure and parameters are specified in the Checkpoint 4.1 response. New `config.py`
constants (`TOT_BRANCHING_FACTOR`, `TOT_MAX_DEPTH`, `TOT_BEAM_WIDTH`,
`TOT_PRUNE_THRESHOLD`) are **provisional and tuned in U8**, where
synthetic cases have a known-correct branch. Search strategy is **beam search**: BFS at
*b*=5 over depth 3 is 125 leaf evaluations for a three-output forecast, and DFS commits
to a framing before comparing it — reintroducing the premature commitment ToT exists to
prevent. `config.LLM_TEMPERATURE = 0.0` already carried the comment
`# deterministic by default; ToT overrides`, so this decision closes a seam the config
anticipated.

**#13 — MCP is adopted, and the honest case for it is narrower than the rubric implies.**
The Module 4 material frames MCP as a connectivity protocol (client, servers, resources,
tools over JSON-RPC), and its own decision framework routes "connecting tools to multiple
models" there. This project's ToT evaluator pulls evidence per branch — appreciation
history for an aggressive-growth branch, an FMR record for a high-rent branch — and that
tool-call boundary is where MCP fits.

**What it does not buy: capability.** These are in-process Python functions, and
LangChain's `@tool` decorator would give the evaluator dynamic tool selection with no
protocol hop. The gain is *portability and a second consumer* — the same read-only tools
become callable from any MCP host during U8 evaluation and Week 7 demonstration, so the
data layer can be interrogated directly rather than through a one-off script each time.
That is a real benefit and a modest one, and recording it that way is the point: the
alternative was overstating a tool's necessity to satisfy a rubric.

**MCP is explicitly *not* the ToT state manager**, despite Checkpoint 4.1 suggesting it
for "shared state, context passing, branch tracking." It has no state primitive. Using it
that way would mean building a stateful server duplicating the LangGraph checkpointer and
losing the `operator.add` reducer semantics that make flag accumulation structurally
correct (§5).

**CrewAI is declined.** Its strength is modeling an organization of role-playing agents,
and the session's framework points to it for "modeling a human workflow." This pipeline's
shape comes from data dependency, not a team's division of labor, and the role separation
it offers already exists as typed nodes. Adopting a second orchestrator mid-project for
one sub-feature adds a second execution model, a second state representation, and a second
failure surface without adding capability. **The deciding factor is scope, not merit** —
a ten-agent system designed today with no existing graph would deserve a real evaluation.
Note this argument deliberately does *not* rest on §8's "agents communicate only
through shared state"
convention, which is a project convention rather than a constraint CrewAI violates.

**#14 — the branch tree is split between state and eval artifact.** A compact ledger
(`{id, parent, depth, score, prune_reason}`) per pruned branch reaches `DealState`, which
is what lets the Summarizer say four hypotheses were considered and two discarded, and
why. The full tree — every generated hypothesis, surviving and pruned — is written to
`EVAL_RESULTS_DIR` during eval runs only, behind a config flag.

The split exists because the two artifacts answer different questions. The ledger is
enough to *disclose*; only the full tree lets you reconstruct why the evaluator scored
what it did, which is what U8 needs when a forecast looks wrong and the evaluator rather
than the model is the suspect. Persisting the full tree in state instead would re-serialize
it into the SQLite checkpointer on every subsequent node transition, and would need a
nested model with parent pointers in §5. The eval-only dump also does not expire, which
matters because LangSmith traces on the free tier do, at 14 days.

**This extends Transparent Degradation to the reasoning process itself.** The risk being
mitigated is a silent one: an evaluator that systematically undervalues a correct-but-
unusual hypothesis produces confident, well-formed, wrong forecasts and looks identical to
one working properly. U2 already produced a defect of that exact shape — one critical flag
cost 0.40, landed confidence at exactly 0.60, and `0.60 < 0.60` is false, so a
zero-comparable deal reported as an ordinary result. Pruning that leaves no trace is the
same failure waiting to happen one layer up.


---

## Orchestration & control flow

Decision #1 (LangGraph from day one, rather than a staged migration) is argued in
[`../design/architecture.md`](../design/architecture.md) §3 and is not duplicated here.
Decision #6 (the 0.60 escalation threshold and the severity weights) is **still open** —
see [`../open_questions.md`](../open_questions.md).

### #9 · U2 · Aug 9, 2026 — Planner topology: pre-flight, not supervisor

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
  functions stay few and small — consistent with §3's "agents communicate only through
  shared state."

Recorded because the hand-drawn diagram in `lang_graph_onboarding.md` §4 showed B's shape (and
showed it incoherently — see the correction note there), which is how an unclosed decision
surfaced as a documentation defect rather than as a question. Per §8, decisions of this kind
get raised rather than resolved by assumption at implementation time; this one was.

Each weekly checkpoint publishes explicit completion criteria. Where those exist, the
corresponding unit is specified to produce each required element as a build artifact
rather than as a write-up authored afterward — see the U4 acceptance criteria under
[Retrieval](#retrieval) above for the pattern. Apply the same treatment to 4.1, 5.1, and 6.1 as their criteria are
published.


### U2 · Aug 10–16, 2026 — what the walking skeleton found

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

**Re-measured Aug 16, 2026, with the real Extractor (U3).** The stub is gone, coordinates
are geocoded from each listing's own address rather than supplied, and every run makes a
live model call:

| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | 1.00 | **0** | reports normally |
| `chicago` | 8 | 0.85 | 2 | reports normally |
| `staten-island` | 0 | 0.30 | 5 (incl. 1 critical) | pauses at `human_review` |
| `no-geography` | 0 | 0.20 | 3 (incl. 2 critical) | pauses at `human_review` |
| `coord-conflict` | 8 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |
| `chicago --no-retrieval` | 0 | 0.60 | 2 (incl. 1 critical) | pauses at `human_review` |

Three things in this table are worth more than the numbers.

**The clean Los Angeles run survived the transition**, which was not a given: U3 nearly
lost it. An invented street address resolves to no parcel, falls back to the city
centroid, and raises a warn flag — so every demo run would have carried a disclosure and
this row would have stopped being a baseline. Moving the demo listings onto real
addresses (invented deal terms, real streets) is what preserved it.

**Staten Island still finds zero comps**, for the reason it always did. That was the
other transition risk: the corpus centroid for Staten Island sits 7.55 mi from
Tottenville, in a denser part of the island, so a centroid fallback would have quietly
turned the thin-market case into a different market. The real address keeps the case
measuring what §2 says it measures.

**`coord-conflict` escalates at confidence 0.60 — exactly the boundary** where U2's
escalation defect lived. It escalates on the critical-flag rule rather than on the score,
which is the independent guarantee finding 1 established, now exercised by a case that
arrives at that number honestly instead of by construction. *(U3-era. It measures 0.05
today — see the U7.8 re-measurement below, where the boundary case has moved to the
ablation row.)*

**⚠️ Everything above this line is U3-era history. Superseded by the U7.8
re-measurement at the end of this section**, which is the current behaviour of the
system. The two tables are kept rather than overwritten because the *movement* between
them is the finding: every number that changed did so because the system learned to
disclose something it could not observe in U3.

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


### U7 · Aug 24–27, 2026 — what the Critic actually checks

**The four checks §1 named for the Critic did not survive contact with the built
system**, and that is the unit's central finding rather than an inconvenience discovered
along the way. Reviewed one at a time against the code, before writing any:

| Check named in U2's `TODO(U7)` | Verdict |
| --- | --- |
| Rent estimate vs. the comp set's distribution | **Already built, and not in the Critic.** `agents/valuation_rent.py` raises `RENT_DIVERGES_FROM_COMPS` as its own Observe step. The Critic consumes that flag |
| Value estimate vs. listing price | **Dead.** Decision #15 made `value_estimate` permanently `None`; the TODO predates it |
| Scenario bands vs. the base they branch from | **Retired on evidence.** `agents/scenario_forecast.py` assigns the projection base directly from `deal_terms.price` / `rent_estimate` — the check would compare a field to the variable it was assigned from, and cannot fail by construction |
| Comp-source concentration | **Retired on evidence.** Already rendered as a Summarizer disclosure; promoted to an objection it fires on both dense demo deals, including the clean `los-angeles` baseline — it would object to the system's healthy case |

**The placement rule that came out of it, stated so it does not have to be
re-derived: a check belongs to the agent that already holds both of its inputs.** Two
agents deriving one fact independently is two agents that can disagree about it in one
report. That rule is what moved comp-attribute drift out of the Critic and into
`agents/comps_retrieval.py`, which already holds the subject terms and the comps it
returned, and what keeps rent-vs-comps in Valuation.

**What is left for the Critic is the one thing no other agent can do: read the
*combination*.** Every other agent flags its own step; the Critic is the only node that
sees all of those flags at once, and a combination can say something a sum cannot.
`confidence_from_flags` is a sum, and a sum only ever says *more doubt* — an interaction
says **this measurement does not mean what it appears to mean.** Three shipped (U7.2), all
keyed on `RENT_DIVERGES_FROM_COMPS`, because the comp cross-check is the only independent
check on the rent estimate this system has and each interaction is about when its verdict
stops being readable: comps that drifted onto a different unit type (CRITICAL), comps
clustered at a single coordinate (CRITICAL), and comps retrieved around a city centroid
while the location-blind rent model did not move (WARN).

**Where the window for those checks is, arithmetically.** With the provisional weights
(info 0.00, warn 0.15, critical 0.40) against a 0.60 threshold: one warn reports at 0.85,
two report at 0.70, three escalate at 0.55 on their own, and any critical escalates on
its independent ground. **So an interaction check only ever changes an outcome in the
two-warn window** — which is precisely where a deal looks ordinary and is not.

**`critic_rejected` changed meaning, and that is the substance of U7.4.** It was
`bool(objections)` — *something is wrong*. It is now `any(o.retryable ...)` — *another
pass could fix this*. A rework re-runs the entire pipeline, so it is worth spending only
where a second pass can change the input: a thin market stays thin, an address with no
street number stays unresolvable, and a comp set relaxed onto a different unit type will
relax the same way again. Only an unreachable geocoder may answer next time.
Non-retryable objections still escalate, through their severity.

**Three defects surfaced only because the back edge started carrying traffic**, and each
had been latent since U2:

1. **Nothing the Critic raised could trigger the Critic's own escalation.** `has_critical`
   read `state.flags` and not the flags being returned, so a CRITICAL objection set no
   route and would have reported as a normal result.
2. **Confidence decayed across rework laps.** `state.flags` is append-only by design and a
   rework re-runs every upstream agent, so a deal scored 0.70, then 0.40, then 0.10
   without anything about it changing — escalating on collapsed confidence before
   `MAX_REWORKS` was reached, which made `REWORK_LIMIT_REACHED` unreachable through the
   graph. **The cycle was bounded by an arithmetic accident rather than by the explicit
   counter §3 requires, and the two agreeing on the outcome is what kept it hidden.**
   Fixed by de-duplicating on `(source_agent, kind, detail)` — not on kind alone, because
   one retrieval pass can raise `RELAXED_MATCH_CRITERIA` twice for two real concessions.
3. **The rework path re-ran everything except the step that could fix the problem.**
   `REQUIRED_DEAL_FIELDS` carries no coordinate, so a deal complete on pass one skipped
   the Extractor on every later lap — and the single objection marked `retryable`, whose
   justification was *re-running the Extractor re-attempts the Census call*, re-attempted
   nothing. That is exactly the failure the retryable distinction exists to prevent.

The three share a shape worth naming: **a guardrail that has never fired has not been
tested, however carefully it was written.** All three were correct-looking code, and all
three were found by making the cycle actually run.

**Decision #6 splits: the mechanism landed in U7, the numbers did not.** The weights and
threshold live in `config`, the critical-flag rule is independent of both, rework laps no
longer decay the score, and `scripts/confidence_evidence.py` measures the whole thing on
the real pipeline. What U7 deliberately did **not** do is tune the numbers: the demo deals
were calibrated to run clean and cannot exercise the range, so tuning against them would
be fitting the threshold to the fixtures — the same error rejected three times elsewhere
in this build. That work moves to U8's eval batch, and #6 stays part-open until it lands.

**Decision #12's Critic half is retired on evidence** (U7.7) — the checks that shipped are
pure functions over `state.flags`, so there is no search space for a beam search to
operate on. Reasoning under [#12](#12-13-14--u6u7--aug-18-2026--tot-scope-mcp-adoption-and-branch-state-persistence)
above. **Decision #8's Critic half is closed by the same fact**: the Critic makes no LLM
call in this design, so `config.MODEL_CRITIC` is untested by construction rather than by
omission, and only the Summarizer's model role stays open for U9.


### Re-measured Aug 27, 2026 (U7.8) — the demo baseline, re-established

**Re-derived rather than transcribed.** `scripts/confidence_evidence.py` now prints these
rows from the same live run that produces the confidence evidence — real LLM extraction,
geocoding, Chroma retrieval, HUD FMR, rent model and ToT forecast — and runs the U4
ablation as a seventh invocation. The U3 table went stale across two units' worth of new
flags (U5's FMR anchoring, U6's forecast) because refreshing it meant seven runs and a
hand-typed table; it is now one command.

**Disclosures counts every flag on the final state, including the ones the Critic itself
raises.** The U2 and U3 versions of this table never said which they counted, which is
part of why these rows cannot be read as a row-for-row diff against them.

| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |
| --- | --- | --- | --- | --- |
| `los-angeles` | 8 | 0.70 | 4 (2 info, 2 warn) | reports normally |
| `chicago` | 8 | 0.55 | 9 (5 info, 4 warn) | pauses at `human_review` |
| `staten-island` | 0 | 0.00 | 8 (2 info, 4 warn, 2 critical) | pauses at `human_review` |
| `no-geography` | 0 | 0.00 | 5 (1 warn, 4 critical) | pauses at `human_review` |
| `overpriced` | 8 | 0.70 | 4 (2 info, 2 warn) | reports normally |
| `coord-conflict` | 8 | 0.05 | 5 (1 info, 2 warn, 2 critical) | pauses at `human_review` |
| `chicago --no-retrieval` | 0 | 0.60 | 6 (4 info, 1 warn, 1 critical) | pauses at `human_review` |

**The baseline argument is re-based, not restored.** There is no longer a run that raises
zero flags, and there will not be one again: `los-angeles` pays
`fmr_anchor_county_level` because Los Angeles County publishes no Small Area FMR, and
that is a fact about HUD rather than about the deal. What the demo set still has — and
what the original argument actually needed — is **a case that reports normally, a case
that stops, and the difference between them being legible**. `los-angeles` and
`overpriced` report at 0.70 with no critical flag and a full comp set; `chicago` stops at
0.55; the three degraded cases stop at 0.05 and below with critical flags naming what
failed. The clean row is now *the clean reporting path* rather than *the flagless run*.

**`chicago` escalating was accepted deliberately, not tuned away** (Aug 26, 2026, by the
architect). It escalates on the score alone, on three deal-specific warns — a widened
search radius, comps that came back outside the size band, and a near-tied forecast — and
the comps genuinely did drift. Raising `COMP_MAX_OUTSIDE_MATCH_SHARE` until Chicago
passed was rejected on the grounds that tuning a production threshold to preserve a demo
outcome inverts what the threshold is for.

**The critical-flag rule is exercised live after all — by the ablation, not by a deal.**
U7.6 concluded from the six deals that no live run isolates it. Adding the seventh
invocation shows `chicago --no-retrieval` sitting at exactly **0.60 with one critical
flag**: `retrieval_disabled` costs 0.40, `0.60 < 0.60` is false, so the score does not
escalate it and the critical-flag rule does. That is the same arithmetic boundary the U2
defect sat on, now landing on the correct side of it. It is a live case for the rule
rather than a hermetic one — but it is not a *deal*: only the `--no-retrieval` flag can
raise that flag, so U8 still owes an eval case that reaches the boundary through a
property of the listing. The script checks this rather than asserting it, so the sentence
cannot outlive the fact.

**Two rows raise one kind twice, and both are correct.** `staten-island` carries
`relaxed_search_radius` twice (two separate widenings) and `forecast_unavailable` twice —
a WARN for the price side having no Redfin series, then a CRITICAL for the search ending
with no surviving hypothesis. The U7.4 de-duplication is on `(source_agent, kind, detail)`
precisely so distinct observations that share a kind are each charged. Worth naming for
U8 anyway: a reader seeing one kind listed twice has to read both details to learn they
are different events, and 0.55 of that deal's penalty comes from a pair that looks like
one condition reported twice.

**What has not moved:** Staten Island still finds zero comps, and `no-geography` still
resolves through neither geocoding tier. Both are the cases §2 selected them to be.


### Prerequisite reading — U2-era process note

Retained for the record; the ramp-up it describes was completed before U2 review. "That
document" is the LangGraph onboarding note kept outside the public tree.

Ramp up on LangGraph (roughly
3 hours). This sits on the critical path: the review standard applied to Weeks 4–6 is
only as good as the reviewer's fluency in the framework, and §6 of that document is the
checklist applied to every unit.

### Aug 8, 2026 — U4 resequenced ahead of U2 and U3

Carried over from §6, where it explained a unit order that has since simply happened. Kept because the reason it worked is a reusable one.

**Resequenced Aug 8, 2026 — U4 pulled ahead of U2/U3.** Checkpoint 3.1 fell due before
the original Week 5 slot for retrieval. U4 turned out not to depend on either the
walking skeleton or the Extractor: it needs `state.py` and `config.py` (both U1), a
subject property can be constructed directly as a `DealTerms` object rather than
extracted from listing text, and a node function is callable with or without a graph
around it. This is the payoff of freezing the interface contract in U1 — with schema and
node signatures fixed, units can land in any order. Note the distinction being relied on:
U1 is the *interface* risk and had to come first; U2 is *integration* risk, which is
safe to defer.

### Aug 8, 2026 — the major revision that reordered the build

Carried over from the plan's preamble. All three changes are now simply the design, stated in §6 (sequencing), [`../design/architecture.md`](../design/architecture.md) §3 (LangGraph), and [`../design/data_strategy.md`](../design/data_strategy.md) §2 (the metro hypothesis), so the note is recorded here rather than framing a document whose readers no longer need the before-picture.

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

## Models & infrastructure

Decision #13 (MCP adoption) is recorded under
[Forecasting & reasoning](#12-13-14--u6u7--aug-18-2026--tot-scope-mcp-adoption-and-branch-state-persistence),
with #12 and #14, because the three were taken together and concern one sub-system.

### #8 · U3 · Aug 9–16, 2026 — OpenRouter model selection

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

**Closed Aug 16, 2026 (U3) — `nvidia/nemotron-3-nano-30b-a3b`, on the paid variant.**
The route to that answer is worth more than the answer, because the first two passes
measured the wrong thing.

**Pass 3 and 4, paid variants — the comparison only became a comparison once it was paid
for.** Every candidate returned 3/3 schema-valid extractions, 23/23 hand-checked fields,
correct assumption verdicts on all three listings, and **zero 429s**, with no model ever
needing a schema retry. Correctness ties completely, so the remaining signals are latency
and price:

| model | pass 3 | pass 4 | $/extraction |
| --- | --- | --- | --- |
| `google/gemma-4-26b-a4b-it` | 8.2s | 6.5s | 0.00034 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 13.7s | 9.3s | 0.00216 |
| **`nvidia/nemotron-3-nano-30b-a3b`** | **18.0s** | **11.3s** | **0.00015** |
| `openai/gpt-oss-20b` | 24.6s | 19.2s | 0.00009 |
| `nvidia/nemotron-3-super-120b-a12b` | 35.0s | 19.9s | 0.00027 |
| `google/gemma-4-31b-it` | 35.7s | 12.4s | 0.00028 |
| `nvidia/nemotron-3.5-lightning` | 44.7s | 32.9s | 0.00020 |

Selected on balance rather than on any single column: perfect on all four passes, the
cheapest of its family, and second-fastest overall. Two alternatives are recorded so the
choice stays reviewable rather than looking inevitable — gemma-4-26b was fastest on both
passes at 2.3× the price, and gpt-oss-20b was cheapest but slower. At $0.00015 per
extraction, roughly 6,700 extractions to the dollar, price is not the deciding axis at
this project's volume; it is recorded because a cost table nobody wrote is a cost nobody
notices later.

**One finding that outlives this decision: a free variant and a paid variant of the same
model name are not necessarily the same deployment.** `gemma-4-26b` scored a spurious
assumption on *both* free passes and on *neither* paid pass, with an identical prompt.
Whatever the cause — quantization, a different serving provider — it means a free-tier
measurement is not automatically evidence about the paid variant of the same name, and
neither is the reverse.

**This is a documented departure from the project's "prefer free tools" constraint**,
taken because the constraint's own qualifier — *where their quality is good* — is what
failed. See open item 0 below for the accounting.

**Passes 1 and 2, free variants — kept because the failure is the evidence.**
`--tier free` still reproduces them. These passes are what established that the free
tier's `:free` variants are served from provider-shared pools, so what they measured was
availability, not capability: models lost whole listings to 429s and *which* models
failed moved between passes. `openai/gpt-oss-20b:free` scored 3/3 on the first pass and
1/3 on the second; `google/gemma-4-31b-it:free` scored 0/3 then 1/3. The four
`nvidia/nemotron-3*` variants completed both passes, which is the only signal that
survived into the paid comparison.

| model | pass 1 | pass 2 | fields | assumptions | secs |
| --- | --- | --- | --- | --- | --- |
| `nvidia/nemotron-3-nano-30b-a3b:free` | 3/3 | 3/3 | 23/23 | all correct | 29.6 |
| `nvidia/nemotron-3-super-120b-a12b:free` | 3/3 | 3/3 | 23/23 | all correct | 34.6 |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 3/3 | 3/3 | 23/23 | all correct | 66.0 |
| `nvidia/nemotron-3.5-lightning:free` | 3/3 | 3/3 | 23/23 | all correct | 69.8 |
| `openai/gpt-oss-20b:free` | 3/3 | **1/3 (429)** | 23/23 | all correct | 31.9 |
| `google/gemma-4-26b-a4b-it:free` | 3/3 | 3/3 | 23/23 | **1 wrong** | 54.1 |
| `google/gemma-4-31b-it:free` | **0/3 (429)** | **1/3 (429)** | — | — | — |

**Every model that completed a listing scored 23/23 on hand-checked field accuracy, at
one attempt per listing — the retry loop never fired.** So accuracy discriminates almost
nothing here, and saying so is the honest reading: per §8, a check where everything
passes is evidence about the check, not a verdict on the candidates. These listings
separate a working extractor from a broken one, not a good one from a better one. That
held on the paid passes too, which is why the decision came down to latency and price.

**Two method corrections came out of these passes**, and the bake-off carries both now.
The free-tier table confounded availability with capability — a 429 scored identically to
a malformed extraction, so `gemma-4-31b` looked incapable when it was merely queued.
`run_case` now backs off `(5, 15, 30)` seconds on rate limits only, and counts them in a
separate column, so the two are measured independently. And the bake-off runs with the
response cache **off**: it measures a provider's live behaviour, and a replayed response
would report the recording's latency as if it were today's.

The single assumption error is worth recording because of what it was. `gemma-4-26b`
flagged a *stated* unit count as an inference. The same failure appeared in the
configured model's first run and was fixed in the prompt rather than in the scoring: a
phrase carrying the number ("three-unit", "three-family", "2-flat") states it, while a
numberless type word ("duplex", "triplex") is an inference. Over-flagging is a real
defect rather than harmless caution — every assumption costs confidence and reaches the
reader as a caveat, so a system that flags everything is indistinguishable to them from
one that flags nothing, which is §2's always-on-signal argument applied to extraction.


### Free-tier request cap · U3 · Aug 16, 2026 — moving to paid inference

This is the accounting decision #8 refers to above.

~~**Free-tier request cap**~~ — ✅ **closed Aug 16, 2026. $10 of credits purchased;
the build now runs on paid model variants.** Kept in full because the reasoning is a
budget decision the project constraints speak to directly.

The free tier is 50 model requests per day, account-wide. Measured, not read off a
docs page: three bake-off passes plus development exhausted it, and the header
confirms it (`X-RateLimit-Limit: 50`, `limit_source: openrouter_free_tier_daily`).
OpenRouter raises this to 1,000/day for $10 in credits — 10% of the project's $100
ceiling.

It bites hardest on **U8**, whose whole design is a batch of 8–10 listings run
repeatedly until the flag coverage is right, and on the Week 7 demo, which must
produce output on demand.

**Resolved: move to paid inference, and build the cache anyway.** Two findings
settled it. First, the daily cap is only one of *two* rate limits — the errors
distinguish `openrouter_free_tier_daily` (the account's 50/day, which credits raise to
1,000) from `upstream_provider_shared_pool` (a provider-side pool shared across all
free users of a `:free` variant, which credits do not address). Only paid variants
clear both, which is what made the model bake-off a fair comparison rather than a
measurement of who was queued behind whom — **passes 3 and 4 recorded zero 429s across
all seven candidates, against repeated losses on the free tier.** Second, the cost is
not close to material: at $0.00015 per extraction on the selected model, the entire
remaining build — development, eval batches, demo runs — is measured in dimes.

**On the "prefer free tools" constraint**, which this departs from: the constraint's
qualifier is *where their quality is good*, and the free tier failed exactly there.
Not on model quality — the same models are available either way — but on the
reproducibility of any measurement taken through it. Two passes could not agree on
which models worked, and one model behaved differently on its free and paid variants
with an identical prompt. A tier that cannot support a repeatable measurement is not
a cheaper version of the same thing.

The cache landed regardless, because its justification was never really quota.
Measured: **0.06 ms for a cache hit against 9.9–23 s for a live call.** It is a
development-latency mechanism first and a reproducibility mechanism second — an
evaluation whose inputs are re-sampled from a stochastic endpoint on each run cannot
show that a change in results came from a change in this system. See
`src/eval/README.md` for the two-tier case design that follows from it.

Worth noting what already worked: the cap was hit accidentally, and the system
degraded correctly rather than crashing (critical flag, escalation, full report). That
was not free — it took the `LlmError` conversion in `tools/llm_client.py`, which the
accidental outage is what exposed.

---

## Evaluation & demo

Decision #3 (Streamlit, run locally, scheduled at U9) was taken early and has not been
revisited; the demo surface is on §6's cut list at position 4, with a terminal recording
plus LangSmith traces as the fallback.

### U8 · why the eval harness is protected from the cut list

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


---

## Appendix — build inventory as of U6

Carried over from §7's "Open items" when that section was split out. It overlaps
[`changelog.md`](changelog.md), which is the authoritative chronological record of code
changes; this snapshot is kept because it groups files by *whether and how they were
verified*, which the changelog does not.

Built and verified against real data, requiring no rework: `tools/hud_fmr.py`,
`scripts/pull_fmr_sample.py` (§9), `scripts/verify_metro_selection.py`,
`tools/kaggle_data.py`, `tools/county_crosswalk.py`, `tools/redfin_data.py`,
`tools/vector_store.py`, `agents/comps_retrieval.py`, `scripts/build_comps_index.py`,
`scripts/retrieval_evidence.py`, and `scripts/retrieval_ablation_llm.py` (the last also
being the first live exercise of `tools/llm_client.py` — `call_with_schema`'s retry loop
fired for real, one model needing two attempts to produce schema-valid output). Added and
verified in U2: `graph.py`, `main.py`, `agents/planner.py`, `agents/summarizer.py`,
`agents/human_review.py`, `tools/tracing.py`, `scripts/export_graph_diagram.py`, and
`tests/test_flag_propagation.py` (14 cases, all passing). Added and verified Aug 11,
2026 (decision #10): `tools/geocoding.py` and `scripts/pull_geocode_sample.py` — not yet
called from the pipeline; see decision #10's closing detail above. Rewritten and
verified Aug 15, 2026 (decision #10 follow-on): `tools/county_crosswalk.py` (now a
point-in-polygon join, replacing the hand-maintained table) and
`scripts/verify_county_geometry.py` — this one *is* called from the pipeline
(`agents/extractor.py`), unlike geocoding itself. Added and verified in U3:
`agents/extractor.py` (real, no longer a stub — `tools/geocoding.py` is now called from
the pipeline too), `scripts/extraction_evidence.py`, `verify_models_live()` in
`tools/llm_client.py`, and `tests/test_flag_propagation.py` at 24 cases. Verified against
live services throughout — including, unplanned, the whole pipeline under a real provider
outage. Added and verified in U5 (Aug 22, 2026): `tools/model/rent_model.py`,
`scripts/train_rent_model.py`, `agents/valuation_rent.py` (real, no longer a stub),
`scripts/valuation_evidence.py` and `scripts/metro_shortlist_ablation.py`, with
`tests/test_flag_propagation.py` at 35 cases. The rent path is exercised against live
HUD FMR, real county polygons and the real comp index by the evidence script; the test
suite stays hermetic against published FMR schedules pasted into a fake client.

