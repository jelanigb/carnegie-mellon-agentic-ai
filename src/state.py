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
from typing import Annotated, Optional

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
    # Comps came back unlike the subject on an attribute the rent model prices on,
    # because the retrieval loop relaxed the band that would have excluded them.
    # Distinct from RELAXED_MATCH_CRITERIA, which records the *concession*: relaxing a
    # filter permits dissimilar comps without guaranteeing them, and a set that relaxed
    # but came back similar anyway is not degraded. This flag is the measured
    # consequence, which is what the Critic's interaction check keys on.
    COMPS_OUTSIDE_MATCH_CRITERIA = "comps_outside_match_criteria"

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
    # Same centroid fallback as above, but reached because the Census *request* failed
    # rather than because the address had nothing to resolve to. A distinct kind rather
    # than a detail inside the message, because the Critic has to branch on it: this is
    # the one degradation in the system that a rework pass can actually fix, since
    # re-running the Extractor re-attempts the call. Parsing prose to decide routing is
    # how a message edit silently becomes a behaviour change.
    GEOCODER_SERVICE_UNAVAILABLE = "geocoder_service_unavailable"
    GEOCODING_UNAVAILABLE = "geocoding_unavailable"
    # A caller supplied coordinates that disagree with the geocode of the listing's own
    # address. Raised rather than resolved: the system cannot tell whether the caller
    # meant the address (and mistyped the coordinates) or the coordinates (and mistyped
    # the address), and those are different properties. See the Extractor for which of
    # the two the pipeline carries while a human decides.
    SUPPLIED_COORDINATES_CONFLICT = "supplied_coordinates_conflict"

    # Valuation
    #
    # **These three were named for FMR until Aug 30, 2026 (U11.3), and the rename is the
    # point rather than tidiness.** The anchor stopped being a Fair Market Rent: it is
    # now Zillow's market rent index at the subject's own ZIP for the *level*, and the
    # HUD schedule only for the *bedroom step*. Members called `FMR_*` would have gone on
    # naming a source that no longer supplies the number, which is the class of quiet
    # staleness §2 exists to prevent — and enum names are what a future reader trusts
    # when the message and the member disagree. `FMR_BEDROOM_CAP_EXCEEDED` keeps its
    # name deliberately: the four-bedroom ceiling really is a property of the federal
    # schedule, which the hybrid anchor still uses.
    #
    # Disclosed on every estimate that is produced: the figure is a modelled ratio times
    # a local market reference, not an observed rent for this property. INFO rather than
    # WARN — it describes how the system works, not a degradation of this run.
    RENT_ANCHORED_TO_MARKET_INDEX = "rent_anchored_to_market_index"
    # No local reference figure could be resolved, so there is no estimate at all.
    RENT_ANCHOR_UNAVAILABLE = "rent_anchor_unavailable"
    FMR_BEDROOM_CAP_EXCEEDED = "fmr_bedroom_cap_exceeded"
    # The anchor fell back to the county's median across its covered ZIPs, because the
    # market rent index does not cover the subject's own ZIP for the month the estimate
    # reads from. Distinct from RENT_ANCHOR_UNAVAILABLE, which means no anchor at all:
    # this one means the estimate exists but cannot see below the county line.
    RENT_ANCHOR_COUNTY_LEVEL = "rent_anchor_county_level"
    # LLM_RENT_FALLBACK_USED lived here until Aug 28, 2026 (U8.1b). Removed on the same
    # rule that retired COUNTY_FROM_PRINCIPAL_COUNTY above, and found by the mechanism
    # that rule was written for: U8.1's coverage census reported it as the one kind no
    # case can raise, because §6's cut list item 3 was taken and the fallback estimator
    # was never built. A member nothing can raise corrupts the census in the pessimistic
    # direction — it reads as a degradation path the harness failed to exercise, when it
    # is a path the build does not have.
    #
    # `RentEstimateSource.LLM_FALLBACK` deliberately stays: that seam is typed-and-unused
    # on purpose (see agents/valuation_rent.py), and it is a different enum, read for
    # provenance rather than compared against a coverage claim. Re-add this member with
    # the estimator if item 3 is ever un-taken.
    # The rent estimate could not be produced at all, for a reason that is not the
    # county lookup. One kind rather than three (no trained model / features the
    # Extractor never resolved / a predicted ratio outside the plausible band) because
    # the reader's response to all three is identical — there is no rent figure and the
    # message says why. RENT_ANCHOR_UNAVAILABLE stays separate because §2 specifies
    # it by name and because it points at a fixable data gap rather than at this run.
    RENT_ESTIMATE_UNAVAILABLE = "rent_estimate_unavailable"
    # The modelled rent and the comp set disagree. Raised by the Valuation agent about
    # its own two inputs, which is what makes it distinct from CRITIC_INCONSISTENCY:
    # that one is the Critic comparing *different agents'* conclusions (U7). This is an
    # agent observing that the evidence it was handed does not support the number it
    # just produced, which is the Observe step of its own loop.
    RENT_DIVERGES_FROM_COMPS = "rent_diverges_from_comps"
    # The rent model's own historical error is measurably worse in the subject's market
    # than the batch it is normally scored against (U8.4, OQ-3). Distinct from every
    # other rent flag: RENT_ANCHORED_TO_MARKET_INDEX discloses the mechanism on every estimate,
    # RENT_DIVERGES_FROM_COMPS is two of this run's own inputs disagreeing, and
    # RENT_ANCHOR_COUNTY_LEVEL is about spatial resolution. This one says the estimate is
    # the system's ordinary output, produced the ordinary way, and this particular
    # market's holdout residual has historically run well above the figure quoted
    # elsewhere in the report as "the" error band. New York is the standing case: it is
    # in the training set (so this is not a transfer question — see OQ-12), just
    # measurably harder to price.
    RENT_ESTIMATE_MARKET_ERROR_ELEVATED = "rent_estimate_market_error_elevated"
    # The estimate (and the comp-implied figures compared against it — both carry the
    # same construction, so both carry the same drift) was multiplied by the subject
    # ZIP's measured market-vs-schedule drift factor (U8.4b, from U8.0's finding that
    # The market-rent index this estimate is anchored to has not been observed recently
    # enough for the figure to be called current. Zillow publishes ZORI on a lag and a
    # thin ZIP's series can end earlier still, so this is measured per subject against
    # `config.RENT_ANCHOR_MAX_STALENESS_MONTHS` rather than per file.
    #
    # **Replaces `RENT_DRIFT_CORRECTION_UNAVAILABLE`, and the kind it replaced is gone
    # (U11.3).** That flag disclosed that a measured FMR-versus-market bias could not be
    # removed from this estimate. The anchor is now a market index read at the same month
    # on both ends, so the bias is divided out where it arises and there is nothing left
    # for a correction to fail at. What survives is the narrower and still-true statement:
    # an estimate is only as current as the market read behind it.
    RENT_ANCHOR_INDEX_STALE = "rent_anchor_index_stale"

    # Forecast
    APPRECIATION_SOURCE = "appreciation_source"
    ANOMALOUS_PERIOD_INCLUDED = "anomalous_period_included"
    # No forecast at all on at least one side. Both halves fail independently and for
    # unrelated reasons — a Staten Island subject has a full FMR history and no Redfin
    # metro; a subject with no resolvable county has the reverse — so the message names
    # which side is missing rather than reporting a blanket absence.
    FORECAST_UNAVAILABLE = "forecast_unavailable"
    # Fiscal years in which every area in the FMR cohort panel moved together were held
    # out of the rent bands. The rent-side counterpart to ANOMALOUS_PERIOD_INCLUDED,
    # and deliberately a separate kind: the two series' anomalous windows do not
    # overlap. Redfin's is calendar 2020-2022; FMR's is FY2023-2024, because an
    # administrative series lags the market it measures. One kind covering both would
    # let a report imply the same years were treated the same way on both sides.
    RENT_GROWTH_COHORT_SHIFT_SCREENED = "rent_growth_cohort_shift_screened"
    # The top two branches scored within `config.TOT_TIE_EPSILON` of each other while
    # implying materially different outcomes, so the winner was near-arbitrary. Raised
    # rather than resolved silently: an evaluator that cannot separate two hypotheses
    # has not chosen between them, and a report that presents the survivor as the
    # conclusion would be overstating what the search established.
    FORECAST_BRANCHES_NEAR_TIED = "forecast_branches_near_tied"

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


class RentEstimateSource(StrEnum):
    """Which estimator produced `DealState.rent_estimate`.

    The report cites this so a reader can weigh a regression output differently from an
    LLM fallback. Closed set for the same reason as `LocationPrecision`: it's compared
    (`agents/summarizer.py`) rather than only displayed.
    """

    REGRESSION_MODEL = "regression_model"
    LLM_FALLBACK = "llm_fallback"


class DealStatus(StrEnum):
    """Where a deal's run stands. Terminal values are `COMPLETE` and `FAILED`;
    `NEEDS_REVIEW` is a durable state a deal can still be resumed from (see
    `agents/human_review.py`), not a terminal one.
    """

    IN_PROGRESS = "in_progress"
    NEEDS_REVIEW = "needs_review"
    COMPLETE = "complete"
    FAILED = "failed"


class Flag(BaseModel):
    """A disclosed deviation from the ideal path.

    Raised at the moment the deviation occurs, not reconstructed later, so that every
    downstream estimate built on it can be qualified accordingly.
    """

    source_agent: str
    kind: FlagKind
    detail: str
    severity: Severity
    # Which pass raised this (`DealState.planner_invocations` at the moment it was
    # constructed) — U8.5/OQ-15. `DealState.flags` is append-only across rework laps so
    # the raw run history stays inspectable, which means nothing else on a Flag says
    # whether it still describes the deal or only described it on an earlier lap. The
    # default of 0 is a sentinel for flags built outside the pass mechanism (a
    # hand-constructed test fixture) rather than a real pass number: `planner_agent`
    # advances `planner_invocations` to 1 before any other node can raise anything, so a
    # real flag is never stamped 0.
    planner_invocations: int = 0


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
      (`FlagKind.RENT_ANCHOR_UNAVAILABLE`) for a New England point or a subject with
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

    def is_complete(self) -> bool:
        """True when every field in `config.REQUIRED_DEAL_FIELDS` is populated.

        Lives on the type rather than in an agent because two agents now ask it — the
        Planner, to decide whether extraction is needed at all, and the Extractor, to
        decide whether it needs the *model* or only the geocoder (U8.1b). Putting it in
        one of them would have made the other import an agent, inverting the dependency
        the graph's topology sets up.

        The field list stays in `config` precisely so "what counts as complete" is
        tunable without touching an agent (§8). Names are looked up by `getattr`, so a
        typo in the config tuple surfaces here at the first run rather than as a
        silently-always-incomplete deal.

        **`config` is imported inside the method, not at module scope, and that is
        deliberate.** This module imports nothing from the project — it is the schema
        every other module depends on, and a schema that reaches back into configuration
        at import time makes the dependency run both ways. Keeping the import local means
        `state.py` still loads on its own, while the one method that genuinely needs a
        tunable can read it.
        """
        import config

        return all(
            getattr(self, field_name) is not None
            for field_name in config.REQUIRED_DEAL_FIELDS
        )

    def geography_is_incomplete(self) -> bool:
        """True when a deal still needs a geography step, whatever else it has.

        Two distinct gaps, reached by different callers. **No coordinates** is a caller
        who supplied structured terms and left placement to the system. **Coordinates but
        no county** is a caller who knows where the property is but not which HUD entity
        prices it — a lookup key rather than a location.

        Both were silent until U8.1b: `config.REQUIRED_DEAL_FIELDS` covers neither, so a
        complete-looking deal skipped extraction and reached the Valuation agent with no
        FMR anchor — disclosing `RENT_ANCHOR_UNAVAILABLE` as though HUD published no
        schedule for the county, rather than as though nobody had looked one up. Those
        read the same in a report and mean entirely different things.

        Here rather than in either agent for the same reason as `is_complete()` above:
        the Planner asks it to route, the Extractor asks it to decide which geography
        step to run, and whichever agent owned it the other would have had to import an
        agent.
        """
        return (
            self.latitude is None
            or self.longitude is None
            or self.county_fips is None
        )


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


class ValuationDetail(BaseModel):
    """Everything the Valuation agent established beyond the headline rent figure.

    Separate from the five top-level valuation fields on `DealState` rather than merged
    into them, and the split is by **consumer**, not by tidiness. `rent_estimate`,
    `rent_anchor_used` and their siblings are the *result*: what a downstream agent reads
    and computes with — U6's forecast projects from `rent_estimate`. Everything here is
    *provenance*: what the report has to disclose so a reader can weigh that result, and
    nothing downstream calculates from it. Keeping the two apart means U6 depends on a
    stable five-field contract while this object stays free to grow as the disclosure
    surface does.

    Every field is Optional because every one of them describes a step that can fail
    independently. A run can produce a rent estimate with no comp cross-check (the comps
    resolved to no county), a cross-check with no estimate (the model artifact is
    missing), or a market benchmark with neither (an uncovered metro is a fact about
    Redfin's extract, not about this deal). Collapsing those into one presence check
    would make the report say "unavailable" about three different things at once.
    """

    # --- Rent-model provenance -------------------------------------------------
    # Carried so the report can print an error band beside the estimate. A point
    # estimate with no spread is the shape §1 objects to: it reads as more precise than
    # the thing that produced it. Read from the persisted model bundle rather than
    # recomputed, so the figure quoted is the one the shipped model actually scored.
    model_holdout_mae_dollars: Optional[float] = None
    model_holdout_mae_ratio: Optional[float] = None
    model_trained_at: Optional[datetime] = None
    model_training_rows: Optional[int] = None

    # Per-metro holdout error for the subject's own market (U8.4, OQ-3), from
    # `TrainingReport.mae_dollars_by_metro`. Separate from `model_holdout_mae_dollars`
    # above rather than replacing it: the report states both, always — "±$518 overall,
    # ±$1,065 in New York" — so a reader in a good market can see what good looks like.
    # `subject_metro` is `None` when the subject's market is not one of the four this
    # breakdown covers, which is a fact about coverage, not a degradation to disclose.
    subject_metro: Optional[str] = None
    subject_metro_mae_dollars: Optional[float] = None
    subject_metro_mae_n: Optional[int] = None

    # --- Drift correction provenance (U8.4b) -------------------------------------
    # How old the market index's newest observation was when this estimate was built,
    # and which month it came from. Carried whether or not the staleness flag fired, so
    # the report can state the anchor's vintage rather than only complain about it.
    anchor_index_month: Optional[str] = None
    anchor_index_staleness_months: Optional[int] = None

    # Which HUD fiscal-year schedule supplied the *bedroom step* — how much a
    # three-bedroom is worth relative to a two-bedroom in this county. Since U11.3 the
    # schedule no longer sets the rent level (the market index does), and its own level
    # divides out of the shape, so this dates the shape and nothing else. Still carried:
    # §2's whole design is that the number is dated, and a shape read from a stale
    # schedule is a disclosure even when the level beside it is current.
    fmr_shape_year: Optional[int] = None

    # Which spatial resolution the anchor's *level* came from: "zip" where the market
    # rent index covers the subject's own ZIP at the month read, "county" where it fell
    # back to the county's median across covered ZIPs. Carried because the difference is
    # large — rents span roughly 2x within a single county — and because the model is
    # trained against ZIP resolution wherever it exists, so a county-anchored estimate is
    # the degraded case rather than the normal one. `anchor_zip` is the ZIP the level was
    # read at, and is None on the county tier.
    anchor_tier: Optional[str] = None
    anchor_zip: Optional[str] = None

    # --- Comp cross-check (the agent's Observe step) ----------------------------
    # Each comp's own rent, divided by the FMR for *its* county and *its* fiscal year,
    # then re-anchored at the subject's current FMR. That last step is what makes the
    # comparison fair: it re-expresses "what this comp rented for, where it is, in 2019"
    # as "what a unit like it would rent for, here, today," which is the same question
    # the model answered. A raw comp mean would compare a 2019 dollar to a 2026 one —
    # the exact vintage error §2 exists to prevent.
    comp_implied_rent_median: Optional[float] = None
    comp_implied_rent_p25: Optional[float] = None
    comp_implied_rent_p75: Optional[float] = None
    # Two counts, not one, because their difference is the disclosure. A cross-check
    # that ran on 3 of 8 comps is much weaker than one that ran on 8, and a single
    # "comps used" number cannot tell those apart.
    comps_cross_checked: int = 0
    comps_available: int = 0
    # How many of the cross-checked comps were anchored at ZIP rather than county
    # resolution. A comp set spanning a SAFMR county and a non-SAFMR one is normalized
    # on two different bases, and the report should not imply otherwise.
    comps_zip_anchored: int = 0
    # Signed: positive means the model came in above the comps. Direction matters to a
    # reader deciding which way the estimate might be wrong, and an absolute value
    # would throw it away.
    divergence_pct: Optional[float] = None

    # --- Market benchmark (not a value estimate; see the Summarizer) ------------
    # Redfin's median sale price for Multi-Family (2-4 unit) in the subject's metro,
    # smoothed over `config.REDFIN_ROLLING_WINDOW_PERIODS`. Deliberately *not* written
    # to `DealState.value_estimate`: the extract is pre-aggregated to one median per
    # metro-period and exposes no individual sales, so it carries no property-level
    # signal at all — the same figure describes a 2-unit duplex and a 4-unit building
    # in the same metro. It is a market reference the asking price can be read against,
    # and the report labels it as one.
    benchmark_metro: Optional[str] = None
    benchmark_median_sale_price: Optional[float] = None
    benchmark_periods_averaged: Optional[int] = None
    benchmark_homes_sold_per_period: Optional[float] = None
    # Why there is no benchmark, in words, for the metros Redfin's extract never
    # reached — New York is the standing case (§2). Absence stated rather than omitted.
    benchmark_unavailable_reason: Optional[str] = None


class Scenario(BaseModel):
    """One reported forecast path: a rent band paired with a price band, projected out.

    **The pairing is the reasoning, not a formatting choice.** Three rent bands and
    three price bands give nine combinations, and the obvious three — optimistic with
    optimistic, base with base, pessimistic with pessimistic — are the ones this
    project's own data argues against. Rent growth and price growth are *negatively*
    correlated across the inference trio (pooled r = -0.309, §2), so the diagonal
    pairings describe a market behaving in a way it has usually not. Which pairing
    deserves to be called "optimistic" for a given deal is a judgement over measured
    inputs, and it is the judgement the Scenario agent's search exists to make.

    Every rate here is an observed figure from `tools/fmr_history.py` or
    `tools/redfin_data.py` - never a model's invention. The search selects among
    measured values; it does not produce new ones.
    """

    # "optimistic" | "base" | "pessimistic" - the label this path is reported under,
    # assigned after the search by ordering the survivors, not chosen by the evaluator.
    name: str

    # Which band each side contributes. Carried separately from `name` because they can
    # legitimately differ: a "base" scenario may pair an optimistic rent band with a
    # pessimistic price band, and hiding that would make the label look like a
    # measurement rather than a composition.
    rent_band: Optional[str] = None
    price_band: Optional[str] = None

    rent_growth_pct_per_year: Optional[float] = None
    price_growth_pct_per_year: Optional[float] = None

    # Projected levels at `ForecastDetail.horizon_years`. Rent projects from
    # `DealState.rent_estimate`; price projects from the **asking price**, which is an
    # observed fact about this property rather than an estimate - decision #15 leaves
    # `value_estimate` null, and §7 assigned this choice to U6.
    projected_monthly_rent: Optional[float] = None
    projected_price: Optional[float] = None

    # Why this pairing, in the evaluator's words. Rendered verbatim: a scenario a reader
    # cannot interrogate is a number with a label on it.
    rationale: Optional[str] = None
    evaluator_score: Optional[float] = None


class BranchLedgerEntry(BaseModel):
    """One hypothesis the search considered, surviving or discarded (decision #14).

    **Pruning that leaves no trace is the failure mode this project has already had
    once.** In U2 a single critical flag cost 0.40, landed confidence at exactly 0.60,
    and `0.60 < 0.60` is false, so a zero-comparable deal reported as ordinary. An
    evaluator that systematically undervalues a correct-but-unusual branch produces
    confident, well-formed, wrong forecasts and looks identical to one working properly.
    So every branch writes a row here whether it survived or not, and the Summarizer can
    state how many hypotheses were considered and why each was dropped.

    This is the compact ledger, which is what disclosure needs. The full tree - every
    generated hypothesis with its evidence - goes to `EVAL_RESULTS_DIR` during eval runs
    only, behind `config.TOT_PERSIST_FULL_TREE`, because only that lets U8 reconstruct
    why the evaluator scored what it did.
    """

    id: str
    parent: Optional[str] = None
    depth: int = 0
    # Which node produced it. Present so the Critic's own search (U7, decision #12) can
    # append to the same ledger rather than needing a second one.
    agent: str = ""
    summary: str = ""
    score: Optional[float] = None
    # None when the branch survived. A sentence, not a code: the report prints it.
    prune_reason: Optional[str] = None


class ForecastDetail(BaseModel):
    """Provenance for the forecast, split from the scenarios for the same reason
    `ValuationDetail` is split from `rent_estimate` - by consumer.

    `DealState.scenarios` is the *result*: what the report leads with and what the
    Critic checks against the base value. Everything here is what a reader needs in
    order to weigh that result, and nothing downstream calculates from it.

    Every field is Optional because the two sides fail independently. A Staten Island
    subject has an FMR history and no Redfin metro at all; a subject with no resolvable
    county has the reverse. Collapsing those into one "forecast unavailable" would tell
    a reader nothing about which half is missing.
    """

    horizon_years: Optional[int] = None

    # --- What the projection is anchored to ------------------------------------
    # The asking price, and the fact that it is the asking price. Decision #15 declined
    # to produce a property-level `value_estimate`, so the alternative was projecting
    # from a metro median that this repo's demo prices were themselves calibrated to -
    # an agreement that would measure nothing. The asking price is at least an observed
    # fact about this property, and the report says that is what it is.
    projection_base_price: Optional[float] = None
    projection_base_source: Optional[str] = None
    projection_base_rent: Optional[float] = None

    # --- Rent side (HUD FMR history) -------------------------------------------
    rent_growth_area_name: Optional[str] = None
    rent_growth_resolution: Optional[str] = None
    rent_growth_bedrooms: Optional[int] = None
    rent_growth_n_observations: Optional[int] = None
    rent_growth_first_year: Optional[int] = None
    rent_growth_last_year: Optional[int] = None
    rent_growth_pessimistic_pct: Optional[float] = None
    rent_growth_base_pct: Optional[float] = None
    rent_growth_optimistic_pct: Optional[float] = None
    rent_growth_pessimistic_year: Optional[int] = None
    rent_growth_optimistic_year: Optional[int] = None
    # Disclosed beside the bands, never as the bands - it distinguishes an isolated
    # spike from a cluster. See config.FMR_IQR_*_PERCENTILE.
    rent_growth_iqr_lower_pct: Optional[float] = None
    rent_growth_iqr_upper_pct: Optional[float] = None
    # Fiscal years in which every area in the cohort panel moved together. Named rather
    # than counted, because "FY2023 and FY2024 were screened" is checkable and "two
    # years were screened" is not.
    cohort_shift_years_detected: list[int] = Field(default_factory=list)
    cohort_shift_years_excluded: list[int] = Field(default_factory=list)
    cohort_baseline_pct: Optional[float] = None
    cohort_n_areas: Optional[int] = None
    local_deviation_years: list[int] = Field(default_factory=list)
    rent_growth_unavailable_reason: Optional[str] = None

    # --- Price side (Redfin metro multi-family) --------------------------------
    price_growth_metro: Optional[str] = None
    price_growth_n_observations: Optional[int] = None
    price_growth_pessimistic_pct: Optional[float] = None
    price_growth_base_pct: Optional[float] = None
    price_growth_optimistic_pct: Optional[float] = None
    anomalous_period_excluded: Optional[bool] = None
    anomalous_period_share: Optional[float] = None
    optimistic_stretch_in_anomalous_period: Optional[bool] = None
    price_growth_unavailable_reason: Optional[str] = None

    # --- The search itself ------------------------------------------------------
    # Counts rather than the tree, which lives in the ledger. Enough for the report to
    # say what was considered without re-serializing the search on every state write.
    framings_considered: Optional[int] = None
    branches_generated: Optional[int] = None
    branches_pruned: Optional[int] = None
    # Gap between the top two scores at the final level. Below config.TOT_TIE_EPSILON
    # the selection was near-arbitrary, and the system says so rather than presenting a
    # coin flip as a conclusion.
    top_two_score_gap: Optional[float] = None
    evidence_tools_called: list[str] = Field(default_factory=list)
    # Why the search produced nothing, when it produced nothing. Distinct from the two
    # `*_unavailable_reason` fields above: those say a *series* was missing, this says
    # the series were present and no hypothesis over them survived. A report that
    # confused the two would tell a reader to go find data they already have.
    search_exhausted_reason: Optional[str] = None


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
    rent_estimate_ratio_to_anchor: Optional[float] = None
    rent_anchor_used: Optional[float] = None
    # Never populated by this build, and that is a design decision rather than an
    # unfinished one — see `agents/valuation_rent.py`. The only sale-price source in
    # this project is Redfin's pre-aggregated extract: one median per metro-period,
    # zero individual sales, no property attributes to adjust by. Writing that median
    # here would have state assert a property-level value it does not have. The figure
    # is carried instead as `ValuationDetail.benchmark_median_sale_price` and rendered
    # as a market reference. Kept as a field because U6 may yet choose a projection
    # base for it; that decision belongs to U6, where the appreciation evidence is.
    value_estimate: Optional[float] = None
    rent_estimate_source: Optional[RentEstimateSource] = None

    # Provenance for everything above, for the report to disclose. See ValuationDetail
    # for why this is a separate object rather than more top-level fields.
    valuation_detail: Optional[ValuationDetail] = None

    # forecast
    # Which series the appreciation figures came from, in the words the report uses -
    # `tools/redfin_data.SERIES_DESCRIPTION`. A plain string rather than the
    # `AppreciationTier` enum this held until U6: the tier ladder it belonged to was
    # measured down to a single rung (`zip_multifamily` closed on sample size,
    # `metro_all_residential` closed by decision - see §7), and a three-member type
    # advertising fallbacks the build cannot reach describes a design rather than a
    # system. A description also tells a reader more than a tier label does.
    appreciation_source: Optional[str] = None

    # The reported forecast paths, and the provenance behind them. `scenarios` was an
    # untyped dict through U5 because nothing wrote it; U6 gives it the same
    # result/provenance split `ValuationDetail` uses - see `Scenario` and
    # `ForecastDetail` above for why the pairing of bands is the reasoning rather than a
    # presentation choice.
    scenarios: list[Scenario] = Field(default_factory=list)
    forecast_detail: Optional[ForecastDetail] = None

    # Every hypothesis the Tree-of-Thought search considered, surviving or pruned
    # (decision #14). Carries a reducer because the Critic's own search appends to it in
    # U7, and because a rework pass re-runs the Scenario node - the raw history stays
    # inspectable and the Summarizer de-duplicates at render time, matching `stub_nodes`.
    branch_ledger: Annotated[list[BranchLedgerEntry], operator.add] = Field(
        default_factory=list
    )

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
    status: DealStatus = DealStatus.IN_PROGRESS
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

    def flag(self, source_agent: str, kind: FlagKind, detail: str, severity: Severity = Severity.INFO) -> Flag:
        """Bound convenience constructor for the common case: a node raising a flag
        against its own already-in-scope `state` (U8.5/OQ-15).

        Every node function, and most of the helpers they call, already hold `state` —
        this stamps `planner_invocations` from it automatically rather than making
        every one of the ~37 call sites pass it explicitly. The free `flag()` function
        below still exists for the handful of helpers that build a `Flag` without a
        `DealState` in scope; they take the pass number as an explicit argument instead.
        """
        return flag(source_agent, kind, detail, severity, self.planner_invocations)


def flag(
    source_agent: str,
    kind: FlagKind,
    detail: str,
    severity: Severity,
    planner_invocations: int,
) -> Flag:
    """Convenience constructor for a helper that has no `DealState` to call
    `state.flag()` on.

    `planner_invocations` has no default here, deliberately (U8.5/OQ-15): a helper that
    forgets to thread it through fails loudly at the call site instead of silently
    stamping every flag it raises with the sentinel 0, which would make the Critic treat
    a live pass's finding as if it belonged to no pass at all.

    Nodes return flags as a list in their partial update — e.g.
    `return {"flags": [state.flag(AGENT, FlagKind.SPARSE_COMPS, "...", Severity.WARN)]}`
    — and the reducer on DealState.flags accumulates them.
    """
    return Flag(
        source_agent=source_agent,
        kind=kind,
        detail=detail,
        severity=severity,
        planner_invocations=planner_invocations,
    )


def count_area_positioned(comps: list[Comp]) -> int:
    """How many comps carry a city-area placeholder coordinate rather than a street
    address. See `Comp.location_precision` for what the two values mean and why the
    distinction matters.

    Shared by `comps_retrieval` (spatial-concentration flag) and `summarizer`
    (location-precision disclosure) so the two stay in agreement by construction.
    """
    return sum(1 for c in comps if c.location_precision == LocationPrecision.AREA)
