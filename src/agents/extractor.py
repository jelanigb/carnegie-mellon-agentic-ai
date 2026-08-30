"""Extractor agent — Loop 1 from Checkpoint 2.1, built for real in U3.

This replaces the U2 stub's regex parse with a schema-validated LLM call. The regex is
**deleted rather than kept as a fallback**, and that is a decision rather than an
omission: a second parser that only runs when the first one fails is a second parser
nobody reviews, and it would quietly become the primary path the moment a free-tier
model went down. The system now either extracts with the model or discloses that it
could not — which is the same discipline `tools/geocoding.py` applies when it declines
to invent a coordinate. The offline path the old regex incidentally provided belongs to
the test suite, and `tests/test_flag_propagation.py` gets it by stubbing this module's
two outbound calls rather than by keeping a parser in production for its benefit.

Reason/Act/Observe/Decide:

- **Reason.** Decide which of the required deal terms the listing plausibly contains,
  which are absent, and which are stated ambiguously enough that a number read off them
  would be a guess wearing a fact's clothing.
- **Act.** Call the model for a `ListingExtraction`, then derive the two geography
  fields the listing never states: coordinates via `tools/geocoding.py`, and the county
  entityid via `tools/county_crosswalk.py` from those coordinates.
- **Observe.** Three things, each of which is an observation rather than an error: did
  the model produce schema-valid output within its retry budget; did the address resolve
  to a parcel, to a city-level approximation, or to nothing; and is every field in
  `config.REQUIRED_DEAL_FIELDS` populated.
- **Decide.** Emit a clarifying question and an `unresolved_field` flag per missing
  required field, an `assumed_field_value` flag per value the model inferred rather than
  read, and a geography flag matching whichever resolution tier actually fired. On retry
  exhaustion, write no deal terms at all and raise a critical flag — an empty extraction
  that says so is worth more than a half-parsed one that doesn't.

**Two outbound calls, and both are the test suite's seams.** `_extract_terms` wraps the
model call and `geocode` is imported by name, so `tests/test_flag_propagation.py`
monkeypatches those two names to run this node hermetically. The real versions are
exercised by `scripts/extraction_evidence.py` against live services, per §8's split
between hermetic tests and live verification scripts.

**On assumptions.** The model is asked to fill a field it inferred *and* to name the
inference in `assumptions`, rather than to choose between reporting and inferring. A
term of art like "2-flat" genuinely does mean two units, and refusing to read it would
throw away information the listing really carries; recording that it was read rather
than stated is what keeps the downstream estimate qualifiable. This is the mechanism
Checkpoint 2.1 describes as "proceed with a flagged assumption when it is not
[material and unrecoverable]".
"""

from __future__ import annotations

from typing import Literal, Optional, get_args

from pydantic import BaseModel, Field

import config
from state import DealState, DealTerms, Flag, FlagKind, Severity, flag
from tools import county_crosswalk, diagnostics
from tools.geocoding import GeocodeResult, GeocodeSource, geocode
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted

# Imported rather than reimplemented: a second haversine would be a second thing to keep
# correct, and this one is already the exact-distance filter behind every comp radius.
from tools.vector_store import haversine_miles

AGENT = "extractor"


# --------------------------------------------------------------------------
# The schema the model fills
# --------------------------------------------------------------------------

# Fields the model may name in an assumption. Written as a `Literal` rather than a
# runtime check so the permitted vocabulary appears *inside* the JSON schema the model
# receives — a model told which names are legal produces fewer illegal ones than a model
# corrected after the fact, and an illegal one still costs only a retry rather than
# reaching state.
AssumableField = Literal[
    "price",
    "unit_count",
    "unit_rents",
    "square_footage",
    "bedrooms",
    "bathrooms",
    "full_address",
    "street_address",
    "city",
    "state",
    "zip_code",
]

# Same reasoning as `graph._checked_mapping`: a name here that is not a real `DealTerms`
# field would produce a flag about a field that does not exist, and it would do so
# silently. Checked at import, when the traceback still names this line.
_UNKNOWN_ASSUMABLE = set(get_args(AssumableField)) - set(DealTerms.model_fields)
if _UNKNOWN_ASSUMABLE:
    raise ValueError(
        f"AssumableField names fields absent from DealTerms: {sorted(_UNKNOWN_ASSUMABLE)}"
    )


class FieldAssumption(BaseModel):
    """One value the model inferred rather than read, with the basis for the inference.

    `basis` is required and free-text on purpose. It is rendered verbatim into the
    report, so an assumption a reader cannot evaluate ("assumed 2 units") is worth
    materially less than one they can ("'2-flat' is a Chicago term for a two-unit
    building"), and requiring the field is what makes the difference non-optional.
    """

    field: AssumableField
    basis: str


class ListingExtraction(BaseModel):
    """What the model returns. Deliberately *not* `DealTerms`.

    Two reasons for the separate schema rather than reusing the state model directly:

    1. `DealTerms` carries derived geography — `latitude`, `longitude`, `county_fips` —
       that this system resolves by lookup and must never accept from a model. Handing
       the model a schema containing those fields is an invitation to fill them, and a
       hallucinated coordinate is indistinguishable from a real one downstream.
    2. The assumption and clarifying-question lists are extraction *process* output, not
       deal terms. They belong to this call, not to the property.
    """

    price: Optional[float] = None
    unit_count: Optional[int] = None
    unit_rents: list[float] = Field(default_factory=list)
    square_footage: Optional[float] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None

    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None

    assumptions: list[FieldAssumption] = Field(default_factory=list)
    clarifying_questions: list[str] = Field(default_factory=list)


_EXTRACTION_SYSTEM = """You extract structured deal terms from listings for small \
multi-family residential properties (2-4 units) on behalf of an investment analyst.

Rules, in priority order:

1. Report what the listing states. Use null for anything it does not state. A missing \
field is a normal, expected outcome and is handled downstream; an invented one is not \
recoverable, because nothing later in the pipeline can tell it apart from a real value.
2. Never invent an address, a price, or a rent. If the listing gives a partial address, \
report the parts it gives and leave the rest null.
3. You may resolve a term of art into a value — "duplex" means two units, "triplex" \
means three. When you do, fill the field AND add an entry to `assumptions` naming the \
field and the basis.
3a. An assumption is ONLY for a value you worked out, never for one the listing states. \
The test is whether the number itself appears in the phrase. Any phrase of the form \
"N-unit", "N-family", "N-flat" or "N units" — where N is a digit OR a spelled-out \
number such as two, three, or four — STATES the count. "Three-unit building", \
"three-family home", "3-family", and "2-flat" are all stated: record the value and add \
NO assumption. Only a building-type word carrying no number at all — "duplex", \
"triplex", "fourplex" — is an inference, and only those get an assumption. Flagging a stated value is a real error, not a harmless \
excess of caution: every assumption lowers the confidence score attached to this deal \
and is shown to the reader as a caveat, so flagging everything may artificially lower \
confidence in the deal.
4. `bedrooms` and `bathrooms` are PER UNIT, not totals for the building. "3-unit \
building, 2 bed / 1 bath units" means bedrooms=2, bathrooms=1. If the listing gives a \
building total and no per-unit figure, leave them null and ask a clarifying question.
5. `square_footage` is also per unit, on the same reasoning.
6. `unit_rents` is the list of per-unit monthly rents the listing states, in dollars. \
Empty list if it states none. Do not estimate them.
7. `price` is the asking or list price in dollars, as a number without formatting.
8. Raise a clarifying question only where a field is material to valuing the property \
AND the listing is genuinely ambiguous rather than merely silent. Silence is already \
detected without your help.
9. `full_address` is the address exactly as the listing writes it. `street_address`, \
`city`, `state`, and `zip_code` are that same address decomposed. `state` is the \
two-letter postal abbreviation."""


_EXTRACTION_PROMPT = """Extract the deal terms from this property listing.

--- LISTING ---
{listing_text}
--- END LISTING ---"""


def _extract_terms(listing_text: str) -> tuple[ListingExtraction, int]:
    """The model call, isolated so tests can substitute it (see the module docstring).

    Returns the validated extraction and the number of attempts it consumed. The retry
    loop itself lives in `llm_client.call_with_schema`, which re-prompts with the
    Pydantic `ValidationError` text so the model is told precisely what was wrong —
    Checkpoint 2.1's "malformed tool output is itself an observation" applied to
    parsing.
    """
    client = LlmClient()
    return client.call_with_schema(
        prompt=_EXTRACTION_PROMPT.format(listing_text=listing_text),
        schema=ListingExtraction,
        model=config.MODEL_EXTRACTION,
        system=_EXTRACTION_SYSTEM,
    )


# --------------------------------------------------------------------------
# Geography resolution
# --------------------------------------------------------------------------


def _supplied_coordinates(state: DealState) -> Optional[tuple[float, float]]:
    """Coordinates an external caller put in state before the pipeline ever ran, if any.

    The U2 stub merged *every* pre-existing field over its own parse, as an affordance
    for callers supplying coordinates the pipeline had no way to derive. That merge is
    gone — a real extractor's output should not depend on what happened to be in state
    beforehand — but coordinates remain readable here for one narrow purpose: checking
    them against the address, not deferring to them.

    **Meaningful only on the deal's first pass (U8.5/OQ-16).** Found while building a
    fault-injection case to close `FlagKind.REWORK_LIMIT_REACHED`: on a rework,
    `state.deal_terms.latitude/longitude` already holds whatever the *previous* pass
    resolved to, and this function cannot tell that apart from a caller's own input — a
    prior pass's centroid fallback was being read back as if a caller had chosen it,
    disclosed as "used as given" with no way to verify it, rather than as the system's
    own fallback. That silently swapped `GEOCODER_SERVICE_UNAVAILABLE` for
    `GEOCODING_UNAVAILABLE` on the second pass, which both stopped
    `_geocode_is_worth_retrying` from planning a third attempt and added a new unique
    flag to the confidence tally — short-circuiting a retry a persistent outage should
    still have been worth spending.

    Safe to restrict this way **given the system's one retry path today**: a rework only
    ever happens because of I3's `GEOCODER_SERVICE_UNAVAILABLE` objection, the only
    retryable one that exists, and that flag is only ever raised when no caller supplied
    coordinates in the first place — the caller-supplied branch in `_resolve_geography`
    takes priority and raises a different, non-retryable flag instead. So a deal can only
    ever reach a second pass when pass one's coordinates were pipeline-derived, never
    caller-supplied. Re-check this reasoning if a second retryable objection is ever
    added — it would no longer hold by construction.
    """
    if state.planner_invocations != 1:
        return None
    terms = state.deal_terms
    if terms.latitude is None or terms.longitude is None:
        return None
    return terms.latitude, terms.longitude


def _resolve_geography(
    terms: DealTerms,
    supplied_lat_long: Optional[tuple[float, float]],
    planner_invocations: int,
) -> list[Flag]:
    """Fill `terms.latitude/longitude/county_fips` in place; return what to disclose.

    Four outcomes, ordered by how much the resulting coordinate can be trusted:

    1. **The address resolved to a parcel.** Census's point wins, including over
       caller-supplied coordinates — the report prints the address, so anchoring comp
       retrieval anywhere else would make the output internally inconsistent about which
       property it describes. If supplied coordinates disagree by more than
       `config.COORDINATE_CONFLICT_THRESHOLD_MILES`, that disagreement escalates rather
       than being resolved here: the system cannot tell whether the caller meant this
       address or those coordinates, and guessing would silently pick a property.
    2. **The address did not resolve, but the caller supplied coordinates.** Those are
       used, and disclosed as unverified — a city centroid would be strictly worse than
       a point someone chose deliberately. Note this is the one branch where no conflict
       check is possible, because there is nothing to check against.
    3. **The address resolved only to a city centroid.** Used and disclosed as the
       city-level approximation it is. The conflict check deliberately does *not* run
       against a centroid: a centroid is an admission that the address could not be
       placed, not a competing claim about where it is, so comparing one to the
       caller's coordinates would manufacture conflicts out of ordinary metro-scale
       distance.
    4. **Nothing resolved.** No coordinates, critical flag, and comp retrieval
       short-circuits downstream.
    """
    flags: list[Flag] = []
    resolved: Optional[GeocodeResult] = geocode(
        terms.street_address, terms.city, terms.state, terms.zip_code
    )
    parcel = (
        resolved
        if resolved is not None and resolved.source == GeocodeSource.CENSUS_GEOCODER
        else None
    )

    if parcel is not None:
        terms.latitude, terms.longitude = parcel.latitude, parcel.longitude
        if supplied_lat_long is not None:
            miles = haversine_miles(
                supplied_lat_long[0], supplied_lat_long[1],
                parcel.latitude, parcel.longitude,
            )
            if miles > config.COORDINATE_CONFLICT_THRESHOLD_MILES:
                flags.append(
                    flag(
                        AGENT,
                        FlagKind.SUPPLIED_COORDINATES_CONFLICT,
                        f"Caller-supplied coordinates "
                        f"({supplied_lat_long[0]:.5f}, {supplied_lat_long[1]:.5f}) "
                        f"sit {miles:.2f} mi from the geocode of the listing's own "
                        f"address, {parcel.matched_address} "
                        f"({parcel.latitude:.5f}, {parcel.longitude:.5f}) — beyond the "
                        f"{config.COORDINATE_CONFLICT_THRESHOLD_MILES:.2f} mi tolerance. "
                        f"These describe different locations, and which one was intended "
                        f"cannot be determined from the inputs. The address was used, so "
                        f"comparables below are drawn from around it; if the coordinates "
                        f"were the intended location, this analysis is of the wrong "
                        f"property.",
                        Severity.CRITICAL,
                        planner_invocations,
                    )
                )
    elif supplied_lat_long is not None:
        terms.latitude, terms.longitude = supplied_lat_long
        flags.append(
            flag(
                AGENT,
                FlagKind.GEOCODING_UNAVAILABLE,
                "The listing's address could not be resolved to a parcel, so the "
                "caller-supplied coordinates were used as given and could not be "
                "checked against it. If the address is wrong, nothing here would "
                "detect that.",
                Severity.WARN,
                planner_invocations,
            )
        )
    elif resolved is not None:
        terms.latitude, terms.longitude = resolved.latitude, resolved.longitude
        # Same coordinate, same accuracy cost, different cause — and the cause decides
        # whether retrying is worth anything. See GeocodeResult.primary_unavailable.
        consequence = (
            f"Comparables are drawn from a radius around the city's centre of listing "
            f"density rather than around this property, which costs the most accuracy "
            f"in large metros."
        )
        if resolved.primary_unavailable:
            flags.append(
                flag(
                    AGENT,
                    FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
                    f"The Census geocoder could not be reached, so the address was "
                    f"never tested against it; coordinates fall back to "
                    f"{resolved.matched_address}. {consequence} This is a service "
                    f"outage rather than a problem with the address — the same listing "
                    f"may resolve to a parcel on a later run.",
                    Severity.WARN,
                    planner_invocations,
                )
            )
        else:
            flags.append(
                flag(
                    AGENT,
                    FlagKind.COORDINATES_FROM_CITY_CENTROID,
                    f"The address could not be resolved to a parcel; coordinates fall "
                    f"back to {resolved.matched_address}. {consequence}",
                    Severity.WARN,
                    planner_invocations,
                )
            )
    else:
        flags.append(
            flag(
                AGENT,
                FlagKind.GEOCODING_UNAVAILABLE,
                "The listing's address could not be resolved to coordinates by either "
                "the Census geocoder or the corpus city centroid, and none were "
                "supplied. Comparable retrieval requires coordinates and cannot run.",
                Severity.CRITICAL,
                planner_invocations,
            )
        )

    # Geometric county lookup, keyed on whichever coordinate survived above. `None` here
    # is not flagged at this node: the Valuation agent raises
    # RENT_ANCHOR_UNAVAILABLE where the gap actually bites, and flagging it twice
    # would double-count the same problem against the confidence score.
    terms.county_fips = county_crosswalk.lookup_county_fips(terms.latitude, terms.longitude)
    return flags


# --------------------------------------------------------------------------
# The node
# --------------------------------------------------------------------------


def _extraction_failed(
    state: DealState, kind: FlagKind, detail: str, attempts: int
) -> dict:
    """Partial update for a run that produced no usable extraction.

    `deal_terms` is deliberately absent from the returned dict rather than set to an
    empty object: omitting the key leaves whatever state already held, which is the
    correct behaviour for a rework pass re-running extraction after a partial success.
    Overwriting it with a blank would destroy a previous pass's work to record a
    failure, which is a worse outcome than the failure itself.
    """
    return {
        "extraction_attempts": state.extraction_attempts + attempts,
        "flags": [state.flag(AGENT, kind, detail, Severity.CRITICAL)],
    }


def extractor_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    # **Geography-only path (U8.1b).** The Planner routes here when the terms are already
    # complete but nothing has geocoded them — a caller supplying structured terms, or a
    # golden eval fixture. Parsing is not what that deal needs, and running the model over
    # a listing whose fields are already known would spend a call to re-derive them,
    # risk a *worse* parse than the caller supplied, and make the golden eval tier
    # depend on a model it is defined not to call.
    #
    # `_resolve_geography` is called on the caller's own terms rather than on a re-parse,
    # so what the caller supplied is what gets geocoded and what the report later cites.
    if state.deal_terms.is_complete() and state.deal_terms.geography_is_incomplete():
        terms = state.deal_terms.model_copy(deep=True)
        if terms.latitude is None or terms.longitude is None:
            # Nothing known: geocode the address, which also resolves the county.
            flags = _resolve_geography(
                terms, supplied_lat_long=None, planner_invocations=state.planner_invocations
            )
        else:
            # **Coordinates known, county not.** The caller placed the property; only the
            # FMR lookup key is missing. Geocoding here would be worse than useless — it
            # would re-derive a point the caller already gave, and any disagreement would
            # raise a coordinate conflict against coordinates nobody disputed.
            #
            # `county_fips_from_point` is a point-in-polygon join against local geometry,
            # so this path stays network-free, which is what lets the eval harness's
            # golden tier keep the property `eval/README.md` defines it by.
            #
            # No flag on failure, deliberately: an unresolved county surfaces as
            # `RENT_ANCHOR_UNAVAILABLE` in the Valuation agent, which is the agent that
            # knows what the absence costs. Raising one here too would disclose the same
            # gap twice in the same report.
            terms.county_fips = county_crosswalk.lookup_county_fips(
                terms.latitude, terms.longitude
            )
            flags = []
        return {"deal_terms": terms, "flags": flags}

    try:
        extraction, attempts = _extract_terms(state.raw_listing_text)
    except SchemaValidationExhausted as exc:
        # The flag below carries a truncated version, since it is rendered into the
        # report. The unabridged error and the model's last raw response go to stdout,
        # because "what did it actually return" is the first question anyone debugging
        # this asks. See tools/diagnostics.py.
        diagnostics.log_exception(
            f"extractor: {exc.attempts} attempts produced no schema-valid extraction; "
            f"raising a critical flag and writing no deal terms",
            exc,
        )
        diagnostics.log_note("  last raw response was:", exc.last_raw.strip() or "(empty)")
        return _extraction_failed(
            state,
            FlagKind.EXTRACTION_RETRY_EXHAUSTED,
            f"The extraction model returned output failing schema validation on all "
            f"{exc.attempts} attempts; the last error was: {exc.last_error} No deal "
            f"terms were extracted, so every estimate below is unsupported.",
            attempts=exc.attempts,
        )
    except LlmError as exc:
        # `llm_client.complete` has already logged the unsanitized provider body; this
        # records what the pipeline did about it, which that layer cannot know.
        diagnostics.log_exception(
            "extractor: the model was unreachable; raising a critical flag and "
            "continuing without deal terms",
            exc,
        )
        return _extraction_failed(
            state,
            FlagKind.EXTRACTION_UNAVAILABLE,
            f"The extraction model could not be reached, so the listing was never "
            f"parsed: {exc}",
            attempts=0,
        )

    terms = DealTerms(
        **extraction.model_dump(exclude={"assumptions", "clarifying_questions"})
    )

    flags = _resolve_geography(
        terms, _supplied_coordinates(state), state.planner_invocations
    )
    questions: list[str] = []

    for assumption in extraction.assumptions:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.ASSUMED_FIELD_VALUE,
                f"'{assumption.field}' was inferred rather than read from the listing: "
                f"{assumption.basis} Downstream estimates treat it as given.",
                Severity.WARN,
            )
        )

    for field_name in config.REQUIRED_DEAL_FIELDS:
        if getattr(terms, field_name) is not None:
            continue
        readable = field_name.replace("_", " ")
        questions.append(f"What is the {readable} for this property?")
        flags.append(
            state.flag(
                AGENT,
                FlagKind.UNRESOLVED_FIELD,
                f"Required field '{field_name}' could not be extracted from the "
                f"listing text. Downstream estimates proceed without it.",
                Severity.WARN,
            )
        )

    # The model's questions come second and are de-duplicated against the deterministic
    # ones above, which are the load-bearing set: a required field is missing or it is
    # not, and that determination should not vary run to run. The model contributes only
    # what a fixed check cannot see — ambiguity, as opposed to absence.
    seen = {q.strip().lower() for q in questions}
    for question in extraction.clarifying_questions:
        key = question.strip().lower()
        if key and key not in seen:
            seen.add(key)
            questions.append(question.strip())

    return {
        "deal_terms": terms,
        "clarifying_questions": questions,
        # Counts model attempts consumed, not node invocations — a rework pass that
        # needed three tries cost three, and the distinction matters for reading a
        # trace against the retry budget.
        "extraction_attempts": state.extraction_attempts + attempts,
        "flags": flags,
    }
