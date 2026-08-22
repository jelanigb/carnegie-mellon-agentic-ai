"""Shared state for the deal-evaluation graph.

Design notes: docs/implementation_plan.md §5.

Two decisions here are load-bearing and worth stating at the point of implementation
rather than only in the design document:

1. **Pydantic, not dataclasses.** The Extractor's clarification loop (Checkpoint 2.1,
   Loop 1) must observe *how* a parse was malformed and reformulate its next attempt.
   A Pydantic ValidationError is structured, human-readable text that can be fed
   directly back into a retry prompt. A dataclass raises TypeError or silently accepts
   malformed input, giving the loop nothing to reason about.

2. **`flags` carries an `operator.add` reducer.** Without it, any node returning
   {"flags": [...]} would *overwrite* the accumulated list, and Transparent Degradation
   — the design principle this whole system exists to demonstrate — would fail silently
   the first time two agents both raised flags. With the reducer, each node returns only
   the flags it personally raised and accumulation is guaranteed by the framework rather
   than by developer discipline.

Note which fields do NOT get reducers. `comps` is written by a single node, and each
relaxation pass *replaces* the working set rather than appending to it; a reducer there
would accumulate stale candidates from earlier, narrower passes alongside the final set.
"""

from __future__ import annotations

import operator
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field


class Severity(StrEnum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


class FlagKind(StrEnum):
    """The closed set of degradation kinds this system can disclose.

    A `StrEnum` rather than a class of string constants, for three reasons specific to
    this project:

    1. **It makes §8's review rule structural.** The engineering standards require that
       flag kinds be "drawn from a defined set, not ad-hoc strings." As bare constants
       that was a rule a reviewer had to remember; typing `Flag.kind` as this enum makes
       Pydantic reject an unknown kind at construction instead. This is the same
       reasoning that justified an `operator.add` reducer on `DealState.flags` — an
       invariant the design depends on should be enforced by the type, not by vigilance.
    2. **It makes the set enumerable, which U8 depends on.** The eval harness can
       iterate every member and assert that some test case triggers it. That upgrades
       the claim from "flags fire" to "every degradation path this system defines is
       exercised" — which is what the evaluation section of the report needs.
    3. **It costs nothing at the boundary.** `StrEnum` members *are* `str`, so JSON
       serialization, dictionary keys, and comparison against raw strings all behave
       exactly as before.

    The usual objection to a strict enum — that an unknown value from an external source
    would raise — does not apply here: every flag originates in this system's own agents.
    """

    # Extraction
    UNRESOLVED_FIELD = "unresolved_field"
    ASSUMED_FIELD_VALUE = "assumed_field_value"
    EXTRACTION_RETRY_EXHAUSTED = "extraction_retry_exhausted"
    # Distinct from EXTRACTION_RETRY_EXHAUSTED, and the distinction is the reader's,
    # not the implementation's: "the model answered three times and never produced
    # usable output" and "no model was reached at all" call for different responses
    # from whoever reads the report. Collapsing them into one kind would save an enum
    # member and cost the reader the only thing they needed from it.
    EXTRACTION_UNAVAILABLE = "extraction_unavailable"

    # Retrieval
    RELAXED_SEARCH_RADIUS = "relaxed_search_radius"
    RELAXED_MATCH_CRITERIA = "relaxed_match_criteria"
    SPARSE_COMPS = "sparse_comps"
    RETRIEVAL_DISABLED = "retrieval_disabled"  # U4 ablation path
    # A comp set can satisfy MIN_QUALIFYING_COMPS while representing far fewer
    # *places* than listings — see Comp.location_precision. Measured Aug 22, 2026:
    # the Cleveland demo returns 8 comps from a single coordinate. Distinct from
    # SPARSE_COMPS, which counts listings; this one counts locations.
    COMPS_SPATIALLY_CONCENTRATED = "comps_spatially_concentrated"

    # Geography resolution
    #
    # COUNTY_FROM_PRINCIPAL_COUNTY existed here through Aug 15, 2026, for the old
    # county_crosswalk.py's "principal county" approximation for multi-county cities.
    # Retired along with that table: the crosswalk's replacement resolves the exact
    # county for a subject's actual coordinates rather than approximating one from its
    # city name, so there is no longer an approximation on this path to disclose. Not
    # kept as a permanently-unraisable member — U8's coverage check compares raised
    # kinds against the full enum, and a kind nothing can ever raise would corrupt that
    # comparison rather than merely go unexercised.
    COORDINATES_FROM_CITY_CENTROID = "coordinates_from_city_centroid"
    GEOCODING_UNAVAILABLE = "geocoding_unavailable"
    # A caller supplied coordinates that disagree with the geocode of the listing's own
    # address. Raised rather than resolved: the system cannot tell whether the caller
    # meant the address (and mistyped the coordinates) or the coordinates (and mistyped
    # the address), and those are different properties. See the Extractor for which of
    # the two the pipeline carries while a human decides.
    SUPPLIED_COORDINATES_CONFLICT = "supplied_coordinates_conflict"

    # Valuation
    RENT_ANCHORED_TO_FMR = "rent_anchored_to_fmr"
    FMR_UNAVAILABLE_FOR_COUNTY = "fmr_unavailable_for_county"
    FMR_BEDROOM_CAP_EXCEEDED = "fmr_bedroom_cap_exceeded"
    LLM_RENT_FALLBACK_USED = "llm_rent_fallback_used"

    # Forecast
    APPRECIATION_SOURCE = "appreciation_source"
    ANOMALOUS_PERIOD_INCLUDED = "anomalous_period_included"

    # Review
    LOW_CONFIDENCE_ESTIMATE = "low_confidence_estimate"
    CRITIC_INCONSISTENCY = "critic_inconsistency"
    REWORK_LIMIT_REACHED = "rework_limit_reached"


class LocationPrecision(StrEnum):
    """How well a comp's coordinate identifies an actual place.

    See `Comp.location_precision` for what the two values mean and the measured
    coverage behind them. `StrEnum` for the same reason as `FlagKind` above: the value
    is compared and filtered on (`count_area_positioned`, the eval harness), so a closed
    type catches a typo at construction rather than producing a silent non-match.
    """

    ADDRESS = "address"
    AREA = "area"


class Flag(BaseModel):
    """A disclosed deviation from the ideal path.

    Raised at the moment the deviation occurs, not reconstructed later, so that every
    downstream estimate built on it can be qualified accordingly.
    """

    source_agent: str
    kind: FlagKind
    detail: str
    severity: Severity


class DealTerms(BaseModel):
    """Structured terms extracted from a listing.

    Geography fields are grouped by **provenance**, because how a value was obtained
    determines how much it can be trusted and whether its failure needs disclosing:

    - **Observed** — copied verbatim from the listing. Cannot be wrong, only absent.
    - **Parsed** — decomposed from the observed text by the Extractor. Can be wrong;
      a misparse is a silent error unless the observed original is retained to check
      against, which is why `full_address` is kept rather than reconstructed.
    - **Derived** — produced by a lookup rather than read from the listing at all.
      `latitude`/`longitude` (decision #10, `tools/geocoding.py`) carry known
      approximation error and raise a flag when it's material: a parcel-accurate geocode
      raises nothing, but the city-centroid fallback is a coarser approximation and is
      disclosed as one. `county_fips` (`tools/county_crosswalk.py`, rewritten Aug 15,
      2026 to a point-in-polygon join against the subject's own coordinates rather than
      a hand-maintained city-name table) is now exact rather than approximate — it no
      longer picks a "principal" county for a multi-county city, it resolves the one the
      point actually falls in — so it raises nothing on success; it only fails outright
      (`FlagKind.FMR_UNAVAILABLE_FOR_COUNTY`) for a New England point or a subject with
      no coordinates to begin with.

    Keeping `full_address` alongside the parsed components is deliberate redundancy, not
    an oversight. It preserves the audit trail — if a report cites Cook County for a
    property, the chain from raw string to parsed city to derived FIPS stays inspectable.
    """

    # --- Deal economics ---
    price: Optional[float] = None
    unit_count: Optional[int] = None
    unit_rents: list[float] = Field(default_factory=list)
    square_footage: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None

    # --- Geography: observed ---
    # The address exactly as it appeared in the listing. Also the human-readable
    # identifier the Summarizer uses, since that is what an investor recognizes.
    full_address: Optional[str] = None

    # --- Geography: parsed from full_address by the Extractor ---
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    # --- Geography: derived by lookup, never read from the listing ---
    # county_fips comes from tools/county_crosswalk.py keyed on (city, state); the
    # source data carries no county or ZIP column at all (§2, "Two data gaps").
    county_fips: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class Comp(BaseModel):
    """A retrieved comparable listing.

    Checkpoint 2.1 justifies retrieval on the grounds that it "constrains the comp set
    to records that demonstrably exist and allows the report to cite which ones were
    used." `listing_source` is what makes that citation complete — an id alone says a
    record exists somewhere, while an id plus its originating site says where a reader
    could go to check it.

    It also carries a second signal the design cares about. This corpus is 91%
    RentDigs.com, so a comp set drawn entirely from one aggregator is less independent
    than its count suggests. Surfacing the source lets the Critic notice that
    concentration and the report disclose it, rather than presenting eight comps from a
    single feed as eight independent observations.

    Optional because a source is not guaranteed for every retrieval path — the LLM
    fallback estimator, if it is ever used, produces no citable origin at all, and that
    absence should be representable rather than papered over with a placeholder.
    """

    listing_id: str
    similarity_score: float
    rent: float
    beds: int
    baths: float
    square_feet: float
    distance_miles: float
    listing_source: Optional[str] = None

    # The comp's own coordinate, carried from the corpus rather than geocoded — this
    # dataset ships latitude/longitude columns, and `kaggle_data.CORE_FIELDS` requires
    # them, so every indexed comp has one. Read `location_precision` below for how much
    # any given one is worth.
    #
    # Added Aug 22, 2026. The original schema omitted these because `distance_miles` is
    # the spatial fact a *report* needs, which was true as far as it went — but two
    # things downstream need the coordinate itself, and neither can be served by a
    # distance. Counting how many distinct places a comp set represents requires the
    # points, not their distances from a subject (two buildings equidistant in opposite
    # directions are two places). And §2's invariant that every rent figure passes
    # through FMR normalization means any comp-derived rent must be normalized by *that
    # comp's* county FMR, which `county_crosswalk` resolves from coordinates.
    #
    # `vector_store.query_comps` already read both from Chroma metadata to compute the
    # haversine distance and then discarded them, so this costs no re-index.
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Populated from the corpus `time` column (Unix timestamp, Dec 2018 - Dec 2019).
    # Per-comp vintage matters for valuation: §2's FMR anchoring normalizes by the FMR
    # for *the year a row was recorded*, and this corpus straddles a federal fiscal-year
    # boundary, so a comp set spanning both needs per-row dates rather than a single
    # assumed vintage. Closed the U5 TODO on Aug 22, 2026 in the same re-index that
    # added `location_precision`.
    listed_date: Optional[datetime] = None

    # How well this comp's coordinate identifies an actual place.
    #
    # "address" — the source row carried a street address; its coordinate is very
    #   likely parcel-level (measured: median 1 listing per coordinate).
    # "area"    — the source row had no address and carries what is effectively a
    #   city-area placeholder (measured: median 5 listings per coordinate, one point
    #   in Jersey City standing in for 497 listings spanning $1,200-$5,240).
    #
    # **The signal is strong but not clean, and overstating it would be the exact error
    # this field exists to prevent.** 74 coordinates in the training shortlist carry
    # both kinds at once (2,390 rows), so an "address" tag makes a coordinate probable,
    # not certain. It is recorded per comp so the report can disclose the composition of
    # a comp set rather than presenting eight city-area points as eight located
    # comparables. Coverage varies enormously by metro — Chicago 42%, LA 5%,
    # Cleveland 2% — which is why this is disclosed rather than used to rank or filter:
    # preferring "address" comps would empty the Cleveland comp set entirely.
    location_precision: Optional[LocationPrecision] = None


class DealState(BaseModel):
    """The single typed object threaded through every node.

    Nodes return *partial* updates (a dict of only the keys they changed), not this
    object. Returning the whole mutated state is the most common LangGraph error and
    defeats the reducers.
    """

    # inputs
    raw_listing_text: str

    # planning (written by the Planner; see decision #9 in §7)
    # The Planner runs pre-flight rather than as a supervisor, so its decision about
    # which optional steps run is recorded here rather than recomputed inside a router.
    # §3 requires routing to be state-encoded: a conditional edge reads this list, it
    # does not re-derive it. No reducer — exactly one node writes it, and a rework
    # re-entry *replaces* the plan rather than extending it.
    plan: list[str] = Field(default_factory=list)

    # Makes decision #9's stated invariant — "the Planner runs at most 1 + rework_count
    # times per deal" — assertable from state rather than only observable in a trace.
    planner_invocations: int = 0

    # extraction
    deal_terms: DealTerms = Field(default_factory=DealTerms)
    clarifying_questions: Annotated[list[str], operator.add] = Field(default_factory=list)
    extraction_attempts: int = 0

    # retrieval
    comps: list[Comp] = Field(default_factory=list)
    search_radius_miles: float = 1.0
    retrieval_iterations: int = 0

    # valuation
    rent_estimate: Optional[float] = None
    rent_estimate_ratio_to_fmr: Optional[float] = None
    fmr_anchor_used: Optional[float] = None
    value_estimate: Optional[float] = None
    rent_estimate_source: Optional[Literal["regression_model", "llm_fallback"]] = None

    # forecast
    # "zip_multifamily" is documented future work (§2) and is not produced by this build.
    appreciation_source: Optional[
        Literal["metro_multifamily", "zip_multifamily", "metro_all_residential"]
    ] = None
    scenarios: dict = Field(default_factory=dict)

    # review
    confidence_score: Optional[float] = None
    needs_human_review: bool = False
    critic_rejected: bool = False
    rework_count: int = 0

    # Whatever the reviewer supplied when resuming from the human_review interrupt.
    # Rendered verbatim in the report: a deal that required human judgement should say
    # so in the record, alongside the judgement itself.
    human_review_note: Optional[str] = None

    # output
    report_markdown: Optional[str] = None

    # build provenance (walking skeleton, U2)
    #
    # Names of nodes that ran as stubs during this run, so the report can disclose that
    # a section is unbuilt rather than merely empty. Deliberately *not* a Flag, for two
    # reasons that both matter:
    #
    #   1. A flag describes a degradation of the system as designed — something the
    #      deal or the data did. A stub describes the state of the build. Routing the
    #      second through FlagKind would corrupt what U8's coverage check means, since
    #      it compares raised kinds against `set(FlagKind)` to claim every *designed*
    #      degradation path is exercised.
    #   2. A stub flag would fire on every run of this build, and §2 already establishes
    #      the principle: a signal that is always on conveys nothing. That argument
    #      drove the X=2.0 tuning; it applies here unchanged.
    #
    # Carries a reducer because several nodes contribute. A node re-run by the rework
    # cycle appends its name again; the Summarizer de-duplicates at render time rather
    # than the reducer suppressing it, so the raw run history stays inspectable.
    stub_nodes: Annotated[list[str], operator.add] = Field(default_factory=list)

    # cross-cutting
    flags: Annotated[list[Flag], operator.add] = Field(default_factory=list)
    status: Literal["in_progress", "needs_review", "complete", "failed"] = "in_progress"
    created_at: datetime = Field(default_factory=datetime.now)

    def flags_by_severity(self, severity: Severity) -> list[Flag]:
        return [f for f in self.flags if f.severity == severity]

    def has_flag(self, kind: FlagKind) -> bool:
        """Used by the eval harness to assert that a given degradation path fired."""
        return any(f.kind == kind for f in self.flags)

    def flag_kinds(self) -> set[FlagKind]:
        """Distinct flag kinds raised during this run.

        The eval harness unions this across every case and compares it against
        `set(FlagKind)` to report which degradation paths are covered and which are
        defined but never exercised. That comparison is only possible because FlagKind
        is an enum.
        """
        return {f.kind for f in self.flags}


def flag(
    source_agent: str,
    kind: FlagKind,
    detail: str,
    severity: Severity = Severity.INFO,
) -> Flag:
    """Convenience constructor, so raising a flag inside a node stays a one-liner.

    Nodes return flags as a list in their partial update — e.g.
    `return {"flags": [flag(AGENT, FlagKind.SPARSE_COMPS, "...", Severity.WARN)]}`
    — and the reducer on DealState.flags accumulates them.
    """
    return Flag(source_agent=source_agent, kind=kind, detail=detail, severity=severity)


def count_area_positioned(comps: list[Comp]) -> int:
    """How many comps carry a city-area placeholder coordinate rather than a street
    address. See `Comp.location_precision` for what the two values mean and why the
    distinction matters.

    Shared by `comps_retrieval` (spatial-concentration flag) and `summarizer`
    (location-precision disclosure) so the two stay in agreement by construction.
    """
    return sum(1 for c in comps if c.location_precision == LocationPrecision.AREA)
