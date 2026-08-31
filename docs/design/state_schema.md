**§5 of the plan of record — [`implementation_plan.md`](../implementation_plan.md).**
Section numbers (§1–§9) and decision numbers (#1–#20) anywhere in this repository refer
to that file: §-numbers to its sections, #-numbers to the **decisions register in §7**,
which names every decision and links to its full reasoning in
[`decision_log.md`](../history/decision_log.md). A
[document map](../implementation_plan.md#document-map) there lists every document in this
project and when to read it.

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

**Every closed-vocabulary field is now a `StrEnum`, not just flag kinds** (extended Aug
22, 2026). `FlagKind`/`Severity` set the precedent above; `location_precision`,
`rent_estimate_source`, `appreciation_source`, and `status` used bare `Literal`s instead,
which was an inconsistency rather than a considered difference — they're compared and
filtered on the same way flags are (`count_area_positioned`, the eval harness,
`agents/summarizer.py`'s status branching), so the same typo-at-construction argument
applies. `GeocodeSource` (`census_geocoder` / `city_centroid`) got the
same treatment locally in `tools/geocoding.py`, and `tools/llm_cache.py`'s `CacheMode`
now coerces its env-driven string through the enum at construction, so a typo'd
`LLM_CACHE_MODE` raises at startup instead of silently matching no branch.

```python
import operator
from enum import StrEnum
from typing import Annotated, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class Severity(StrEnum):
    INFO = "info"; WARN = "warn"; CRITICAL = "critical"

class LocationPrecision(StrEnum):
    ADDRESS = "address"; AREA = "area"

class RentEstimateSource(StrEnum):
    REGRESSION_MODEL = "regression_model"; LLM_FALLBACK = "llm_fallback"

class DealStatus(StrEnum):
    IN_PROGRESS = "in_progress"; NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"; FAILED = "failed"

class FlagKind(StrEnum):
    UNRESOLVED_FIELD = "unresolved_field"
    RELAXED_SEARCH_RADIUS = "relaxed_search_radius"
    SPARSE_COMPS = "sparse_comps"
    RENT_ANCHORED_TO_MARKET_INDEX = "rent_anchored_to_market_index"
    RENT_ANCHOR_UNAVAILABLE = "rent_anchor_unavailable"
    COORDINATES_FROM_CITY_CENTROID = "coordinates_from_city_centroid"
    SUPPLIED_COORDINATES_CONFLICT = "supplied_coordinates_conflict"
    EXTRACTION_UNAVAILABLE = "extraction_unavailable"
    # ... 20 kinds total; see src/state.py for the full set. (COUNTY_FROM_PRINCIPAL_COUNTY
    # was here through Aug 15, 2026 — retired along with the crosswalk table it described;
    # see the "Geography fields are grouped by provenance" section below. The last two
    # above were added in U3: a caller-supplied coordinate that disagrees with the
    # geocode of the listing's own address, and a model that could not be reached at all
    # — the latter kept distinct from EXTRACTION_RETRY_EXHAUSTED because "never reached"
    # and "answered badly three times" ask different things of the reader.)

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
    distance_miles: float                  # 1 dp — see location_precision
    listing_source: Optional[str] = None   # originating site, for citation
    listed_date: Optional[datetime] = None # per-row vintage, for FMR normalization
    location_precision: Optional[LocationPrecision] = None
    latitude: Optional[float] = None       # from the corpus, never geocoded
    longitude: Optional[float] = None

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
    rent_estimate_ratio_to_anchor: Optional[float] = None  # model's raw structural output
    rent_anchor_used: Optional[float] = None              # today's local market rent
    value_estimate: Optional[float] = None               # never populated — see U5 below
    rent_estimate_source: Optional[RentEstimateSource] = None
    valuation_detail: Optional[ValuationDetail] = None   # provenance for the report

    # forecast (U6)
    appreciation_source: Optional[str] = None            # which series, in words
    scenarios: list[Scenario] = Field(default_factory=list)
    forecast_detail: Optional[ForecastDetail] = None     # provenance for the report
    branch_ledger: Annotated[list[BranchLedgerEntry], operator.add] = Field(
        default_factory=list
    )

    # review
    confidence_score: Optional[float] = None
    needs_human_review: bool = False
    critic_rejected: bool = False
    rework_count: int = 0               # bounds the Critic → Planner cycle (§3)

    # cross-cutting
    flags: Annotated[list[Flag], operator.add] = Field(default_factory=list)
    status: DealStatus = DealStatus.IN_PROGRESS
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

### Fields added in U5 (Aug 22, 2026)

**`ValuationDetail`, and why it is a nested object rather than more top-level fields.**
The split is by *consumer*, not by tidiness. The five valuation fields above are the
**result** — what a downstream agent reads and computes with; U6's forecast projects
from `rent_estimate`. `ValuationDetail` is **provenance** — the holdout error band, the
fiscal year of the FMR anchor, the comp cross-check, the market benchmark — read only by
the Summarizer and calculated from by nothing. Keeping them apart lets U6 depend on a
stable five-field contract while the disclosure surface grows freely behind it.

Every field on it is `Optional` because each describes a step that fails independently.
A run can produce a rent estimate with no comp cross-check (the comps resolved to no
county), a cross-check with no estimate, or a market benchmark with neither — an
uncovered metro is a fact about Redfin's extract, not about the deal. One presence flag
across all three would make the report say "unavailable" about three different things at
once.

**`value_estimate` is never populated by this build, and that is a decision.** The only
sale-price source in the project is Redfin's extract, pre-aggregated to one median per
metro-period: 306 rows, zero individual sales, no square footage or unit count to adjust
by. A value estimate built from it would return an identical figure for a 2-unit duplex
and a 4-unit building in the same metro. The median is carried as
`ValuationDetail.benchmark_median_sale_price` and rendered as a labelled market
reference instead. The field is kept because U6 may choose a projection base for it;
that decision belongs to U6, where the appreciation evidence is.

> **Closed at U6 (Aug 24, 2026): the projection base is the asking price**, and
> `value_estimate` stays `None` permanently rather than pending. Projecting from the
> Redfin median would have compounded a figure this repo's demo asking prices were
> themselves calibrated to. The asking price is an observed fact about the property, so
> the report's claim is *"pay this today, and here is what the measured trend implies"* —
> which needs no value estimate. Carried as `ForecastDetail.projection_base_price` with
> `projection_base_source` naming it in words.

### Fields added in U6 (Aug 24, 2026)

**Three new types, and one enum removed.** `Scenario` is the *result* — the reported
forecast paths — and `ForecastDetail` is the *provenance*, following exactly the split
`ValuationDetail` established above and for the same reason: the Critic checks scenario
bands against a base value, while nothing downstream calculates from the provenance.
`BranchLedgerEntry` is the third, and it is neither: it records what the reasoning
*considered*, which is a disclosure obligation rather than a result (decision #14).

**`scenarios` stops being an untyped `dict`.** It held one through U5 because nothing
wrote it. It is now `list[Scenario]`, ordered pessimistic → optimistic by combined
outcome across both projected quantities.

**A `Scenario` pairs a rent band with a price band, and the pairing is the reasoning.**
Three rent bands and three price bands give nine combinations. The diagonal — optimistic
with optimistic, and so on — is what a linear chain emits, and it is the combination
§2's measurement argues against, since rent and price growth are *negatively* correlated
across the inference trio (pooled r = −0.309). `rent_band` and `price_band` are carried
separately from `name` because they legitimately differ: a scenario labelled "base" may
pair an optimistic rent band with a pessimistic price one, and collapsing that would make
the label look like a measurement rather than a composition.

**`branch_ledger` carries an `operator.add` reducer**, for two reasons that both apply.
The Critic's own search appends to it in U7 (decision #12), and a rework pass re-runs the
Scenario node — so the raw history stays inspectable and the Summarizer de-duplicates at
render time, matching how `stub_nodes` is handled.

**`AppreciationTier` and `src/enums.py` were removed.** The enum described a fallback
ladder — `metro_multifamily | zip_multifamily | metro_all_residential` — and U6 measured
it down to a single rung: the ZIP tier is closed on sample size (median 2 homes sold per
ZIP-period) and no all-residential extract exists in this project. A three-member type
advertising fallbacks the build cannot reach describes a design rather than a system, so
`appreciation_source` now carries a plain description of the series
(`redfin_data.SERIES_DESCRIPTION`), which tells a report reader more than a tier label
did. `enums.py` existed solely to hold that type and went with it.

**Three new `FlagKind` members.** `FORECAST_UNAVAILABLE` covers a missing side — critical
when both fail, warn when one does, because the two halves fail for unrelated reasons and
a blanket absence would tell a reader nothing about which. `RENT_GROWTH_COHORT_SHIFT_SCREENED`
is the rent-side counterpart to `ANOMALOUS_PERIOD_INCLUDED`, and is deliberately separate
because **the two series' anomalous windows do not overlap**: Redfin's is calendar
2020–2022, FMR's is FY2023–2024, since an administrative series lags the market it
measures. One kind covering both would imply the same years were treated the same way on
both sides. `FORECAST_BRANCHES_NEAR_TIED` fires when the evaluator could not separate the
top two hypotheses, or when the surviving scenarios do not span distinct outcomes.

### Fields added in U5 (Aug 22, 2026), continued

**Two new `FlagKind` members.** `RENT_ESTIMATE_UNAVAILABLE` covers every way a rent
figure can fail to be produced *other than* the county lookup — no trained model, a
feature the listing never resolved, a predicted ratio outside the plausible band — as
one kind rather than three, because a reader's response to all three is identical and
the detail text names the cause. `RENT_DIVERGES_FROM_COMPS` is the Valuation agent
observing that its own two inputs disagree, which is what distinguishes it from
`CRITIC_INCONSISTENCY`: that one is the Critic comparing *different agents'* conclusions
(U7).

**Added Aug 22, 2026 with ZIP-resolution anchoring.** `ValuationDetail.anchor_tier`
(`"zip"` / `"county"`), `anchor_zip`, and `comps_zip_anchored`, plus
`FlagKind.RENT_ANCHOR_COUNTY_LEVEL` (warn) for a county with no Small Area FMR. The
distinction is carried because it is large — ZIP schedules span roughly 2x within a
single county — and because a reader cannot tell a ZIP-anchored figure from a
county-anchored one by looking at it. `RENT_ANCHOR_COUNTY_LEVEL` is deliberately distinct
from `RENT_ANCHOR_UNAVAILABLE`: that one means no estimate at all, this one means the
estimate exists but cannot see below the county line.

**Renamed Aug 30, 2026 (U11.3), because the anchor stopped being a Fair Market Rent.**
These fields and flags were named `fmr_*` when HUD's schedule supplied the rent *level*.
It now supplies only the bedroom *step*; the level comes from Zillow's market rent index
at the subject's own ZIP. Three flag kinds moved — `RENT_ANCHORED_TO_FMR` →
`RENT_ANCHORED_TO_MARKET_INDEX`, `FMR_UNAVAILABLE_FOR_COUNTY` → `RENT_ANCHOR_UNAVAILABLE`,
`FMR_ANCHOR_COUNTY_LEVEL` → `RENT_ANCHOR_COUNTY_LEVEL` — along with
`ValuationDetail.fmr_resolution`/`fmr_zip`/`fmr_year` → `anchor_tier`/`anchor_zip`/
`fmr_shape_year` and `DealState.rent_estimate_ratio_to_fmr`/`fmr_anchor_used` →
`rent_estimate_ratio_to_anchor`/`rent_anchor_used`.

**`FMR_BEDROOM_CAP_EXCEEDED` deliberately keeps its name.** The four-bedroom ceiling
really is a property of the federal schedule, which the hybrid anchor still reads. A
mechanical rename that swept it up would have made the vocabulary *less* accurate, which
is the point of doing this by hand rather than by pattern.

The meaning of `RENT_ANCHOR_COUNTY_LEVEL` shifted with the rename and the flag's own text
says so: it used to mean *HUD publishes no ZIP-level schedule here*, and now means *the
market index does not cover this ZIP for the month read, so the county's median across
its covered ZIPs stood in*. Same consequence for a reader, different cause — U8.2b's rule.

**Added Aug 30, 2026 (U8.6d): `FlagScope`, `scope_of()`, and `ConfidenceBreakdown`.**
Every flag kind is classified as describing this **deal** or this **market**; four kinds
are market-scoped (`RENT_ANCHOR_COUNTY_LEVEL`, `RENT_ESTIMATE_MARKET_ERROR_ELEVATED`,
`RENT_ANCHOR_INDEX_STALE`, `COMPS_SPATIALLY_CONCENTRATED`) and everything else defaults to
deal. `DealState.confidence_detail` carries the score's arithmetic split the same way, so
the report can state what the deduction was made of rather than only what it totalled.

**This is a reporting classification and must not become a scoring one.** Two scores with
independent floors were proposed, measured, and rejected — market coverage propagates into
the deal's own numbers, so scoring the deal side alone would have published high
confidence on a rent figure the report elsewhere calls unreliable. The full reasoning is
in `tasks/task_list_u8.md` U8.6d and is repeated in the `FlagScope` docstring, deliberately,
because the constraint has to be visible where the enum is read.

**One severity changed.** `RENT_ANCHOR_UNAVAILABLE` moved from `warn` to `critical`.
§2 specified `warn` when the design still had a coarser state/national fallback behind
it, so the flag meant "this figure is less precise." The fallback was removed — a raw
comp mean is exactly the unanchored 2019 figure the design forbids — so the flag now
means there is no rent figure at all. A warn-level flag on a missing headline number
would understate it to the Critic's confidence scoring as much as to a reader. The
same reasoning `SPARSE_COMPS` already uses, which is `critical` at zero comps and `warn`
otherwise: severity follows consequence.

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
  from the listing.

  **Superseded Aug 15, 2026.** This originally described the hand-maintained
  `county_crosswalk.py` table, which picked a *principal* county for the ten cities
  spanning several (Chicago, Dallas, Houston among them) — a defensible but genuine
  approximation, hence `FlagKind.COUNTY_FROM_PRINCIPAL_COUNTY`. That table is retired:
  `county_fips` now resolves via a point-in-polygon join against the subject's own
  coordinates (`tools/geocoding.py`, decision #10), which returns the *exact* county a
  point falls in rather than approximating one from a city name — verified to reproduce
  the old table's hand-checked entityids exactly, plus resolve cities the table never
  covered at all (e.g. Miami). `COUNTY_FROM_PRINCIPAL_COUNTY` is removed from the enum
  rather than kept unraisable — see `state.py`. `latitude`/`longitude` remain the tier
  that can raise a flag on approximation (the city-centroid fallback); `county_fips` no
  longer can on success, only on outright failure (`RENT_ANCHOR_UNAVAILABLE` — no
  coordinates, or a New England point, flagged as future work rather than solved).

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

### `Comp` location fields (added Aug 22, 2026)

`listed_date`, `location_precision`, `latitude`, and `longitude` were added together,
and the reason is the same finding in each case: §2 measured that **92% of the corpus
carries no street address**, and those rows sit on a city-area placeholder coordinate
rather than a parcel.

`location_precision` (`"address"` / `"area"`) is how a comp says which kind it is, so a
report can distinguish eight located comparables from eight points that are really one
city. `listed_date` carries the row's own vintage, because the corpus straddles the
FY2019/FY2020 boundary and §2's anchoring normalizes each rent against the FMR for *the
year it was recorded*.

**The coordinates are the correction of an omission rather than a new capability.** The
original schema above carried `distance_miles` and no coordinate, on the reasonable
grounds that a distance is the spatial fact a *report* needs. Two things downstream turn
out to need the point itself. Counting how many distinct places a comp set represents
cannot be done from distances — two buildings equidistant from the subject in opposite
directions are two places, and a distance-keyed count silently merges them, while also
coupling a disclosure threshold to the display setting `COMP_DISTANCE_DECIMALS`. And any
comp-derived rent figure must pass through FMR normalization per §2's invariant, which
needs each comp's county, which `county_crosswalk` resolves from coordinates.

Note what these are *not*: comps are never geocoded. The corpus ships
`latitude`/`longitude`, `kaggle_data.CORE_FIELDS` requires them, and
`vector_store.query_comps` was already reading both to compute the haversine distance
before discarding them — so carrying them costs no re-index and no lookup. Geocoding
(`tools/geocoding.py`, decision #10) applies to the *subject* property, which arrives as
address text. The two paths are easy to conflate and share no code.

