"""Comps/Retrieval agent — adaptive relaxation loop.

Implements Loop 2 from Checkpoint 2.1:

    "You are an experienced real-estate agent who has been given listing details for a
    property for sale. Retrieve comparable listings from the datastore within {X} miles
    of the subject property. Stop when you have at least {Y} listings meeting the match
    criteria. If you cannot find enough, broaden the search area incrementally. Do not
    exceed {Z} iterations."

X, Y, Z live in config.py as INITIAL_SEARCH_RADIUS_MILES, MIN_QUALIFYING_COMPS, and
MAX_RETRIEVAL_ITERATIONS.

Reason/Act/Observe/Decide:

- **Reason.** Translate the subject property's characteristics — bedroom count, square
  footage, coordinates — into retrieval criteria at the current strictness level.
- **Act.** Query the vector store: metadata filters for the hard constraints, semantic
  similarity over description text for ranking.
- **Observe.** Count the comps that survive both the metadata filter and the exact
  geographic radius check. A shortfall is an observation, not an error — it is the
  input to the next decision.
- **Decide.** If the count meets the threshold, exit and pass the set downstream. If
  not, relax exactly one criterion, record a flag naming what was relaxed, and repeat.
  On reaching the iteration cap, exit with a sparse-comps flag and whatever was found
  rather than returning a silently weak result presented as a strong one.

Relaxation concedes the square-footage band first, then widens the search radius, then
loosens bedroom-count tolerance.

**That order is inherited from U4, and the rationale it was written with does not
survive measurement — corrected Sept 2, 2026 (maintenance item M6).** It read "ordered by
how much accuracy each concession costs", calling square footage the weakest signal and
bedroom count the strongest. The shipped rent model measures the opposite:
`square_feet` 0.502, `bedrooms` 0.300, `bathrooms` 0.198 — floor area is the strongest
feature at 1.7x bedrooms, and it is the first thing this ladder gives up. **The cause is
sequencing, not a bad judgment**: the ladder was written in U4 and the rent model did not
exist until U5, so "weakest signal" was an assumption made before there was anything to
ask, and nothing revisited it when the answer arrived.

**Two cautions against over-reading that, which are why the order is not simply
reversed.** Feature importance in the rent *model* is not the same quantity as comp
*comparability* — comps feed a cross-check, not the model — and importances are
unreliable under correlated features, which floor area and bedroom count certainly are.
There is also a second argument pointing the same way that has **not** been checked: a
bedroom mismatch has a correction available through #19's FMR bedroom step, while a
square-footage mismatch has none, which would mean the ladder concedes the uncorrectable
attribute first. Reproduce the importances by loading `config.RENT_MODEL_PATH` and
reading `bundle["model"].feature_importances_` against `config.RENT_MODEL_FEATURES`.

**Not reordered here, deliberately.** Changing the ladder changes which comps every deal
retrieves, which moves comp counts, the drift flag, confidence and verdicts across all 30
eval rows — a re-derivation of the published table, against a finding that is real but
whose fix is not established. What is corrected is the *claim*, so the next reader is not
misled by a rationale the evidence contradicts. U4's ablation harness is the instrument
that would settle it.

A single prompt has no way to inspect the result of its own retrieval and adjust; this
loop is why that matters.
"""

from __future__ import annotations

import config
from state import DealState, FlagKind, Severity, count_area_positioned
from tools import vector_store

AGENT = "comps_retrieval"


def _distinct_locations(comps: "list") -> int:
    """Count the distinct places a comp set actually represents.

    Counted on the comps' own coordinates, which is what makes this an actual location
    count rather than an approximation of one.

    It was briefly keyed on rounded distance instead, when `Comp` carried no coordinate.
    That proxy was wrong in a specific way worth recording: two buildings equidistant
    from the subject in opposite directions counted as one place, so it *understated*
    variety, and it moved whenever `config.COMP_DISTANCE_DECIMALS` changed — a
    disclosure threshold silently coupled to a display setting. Both problems are gone
    now that `Comp.latitude`/`longitude` exist.

    A comp without coordinates is not counted as a place. Every comp from
    `vector_store.query_comps` has them (the corpus requires them at load), so this
    guards against directly-constructed comps in tests and fixtures rather than against
    the retrieval path.
    """
    return len({
        (c.latitude, c.longitude)
        for c in comps
        if c.latitude is not None and c.longitude is not None
    })


def _outside_match_criteria(comps: list, subject) -> list:
    """Comps that would not have qualified under the *unrelaxed* match criteria.

    Measured against `config`'s original tolerances rather than whatever the loop
    relaxed them to, because the question is what the relaxation admitted. A comp is
    counted once however many attributes it misses on — the reader is being told the set
    drifted, not audited attribute by attribute.

    Silent on attributes the subject does not state: a listing with no square footage
    cannot have its comps judged against it, and guessing a subject size in order to
    have something to compare would invent the very thing the check exists to detect.
    """
    drifted = []
    for comp in comps:
        if subject.bedrooms is not None and comp.beds is not None:
            if abs(comp.beds - subject.bedrooms) > config.COMP_MATCH_BEDROOM_TOLERANCE:
                drifted.append(comp)
                continue
        if subject.square_footage and comp.square_feet:
            tolerance = config.COMP_MATCH_SQFT_TOLERANCE_PCT
            low = subject.square_footage * (1 - tolerance)
            high = subject.square_footage * (1 + tolerance)
            if not low <= comp.square_feet <= high:
                drifted.append(comp)
    return drifted


def comps_retrieval_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    subject = state.deal_terms

    # Ablation path (U4 acceptance criteria, §6). With retrieval disabled the pipeline
    # runs on identical inputs without grounding, producing the before/after comparison
    # Checkpoint 3.1 asks for. The flag makes the ungrounded run self-identifying, so a
    # report produced this way can never be mistaken for a grounded one.
    if not config.RETRIEVAL_ENABLED:
        return {
            "comps": [],
            "retrieval_iterations": 0,
            "flags": [
                state.flag(
                    AGENT,
                    FlagKind.RETRIEVAL_DISABLED,
                    "Comp retrieval was disabled; no comparable listings were used. "
                    "Any valuation downstream is ungrounded.",
                    Severity.CRITICAL,
                )
            ],
        }

    if subject.latitude is None or subject.longitude is None:
        return {
            "comps": [],
            "retrieval_iterations": 0,
            "flags": [
                state.flag(
                    AGENT,
                    FlagKind.SPARSE_COMPS,
                    "Subject property has no coordinates; comp retrieval could not run.",
                    Severity.CRITICAL,
                )
            ],
        }

    radius = config.INITIAL_SEARCH_RADIUS_MILES
    bedroom_tolerance = config.COMP_MATCH_BEDROOM_TOLERANCE
    sqft_tolerance = config.COMP_MATCH_SQFT_TOLERANCE_PCT

    flags = []
    comps = []
    iterations = 0

    for iteration in range(1, config.MAX_RETRIEVAL_ITERATIONS + 1):
        iterations = iteration

        comps = vector_store.query_comps(
            subject=subject,
            radius_miles=radius,
            bedroom_tolerance=bedroom_tolerance,
            sqft_tolerance_pct=sqft_tolerance,
            n_results=config.MIN_QUALIFYING_COMPS,
        )

        if len(comps) >= config.MIN_QUALIFYING_COMPS:
            break

        if iteration == config.MAX_RETRIEVAL_ITERATIONS:
            break

        # Relax exactly one criterion per pass, in the order the module docstring
        # states — and see it for why that order's original rationale was retired.
        #
        # TODO(retrieval): reorder this ladder on a measurement of comp comparability,
        # or record that the order is right for a reason other than the one it was
        # written with. **What is missing.** The order is inherited from U4 and the
        # rationale it was written with does not survive: it called floor area the
        # weakest signal, and the shipped rent model measures `square_feet` at 0.502
        # against `bedrooms` at 0.300 — so this ladder concedes the strongest measured
        # attribute first and the weakest last. M6 corrected the *claim* (module
        # docstring, with the two cautions against over-reading it); the *order* is
        # still the one the retired claim chose.
        #
        # **Why deferred (Sept 2, 2026, maintenance item M6).** Reordering changes which
        # comps every deal retrieves, and comp counts feed the drift flag, confidence and
        # the verdict — so it re-derives the published results table across all 30 eval
        # rows, inside a freeze week, against a finding that is real but whose fix is not
        # established.
        #
        # **What it would take.** Score the six orderings of these three concessions on
        # comp-set quality measured against held-out corpus rows, whose actual rents are
        # known — U4's ablation harness is the instrument and it needs no model call.
        # Then check the second argument, which points the same way and is **unverified**:
        # a bedroom mismatch has a correction available through #19's FMR bedroom step
        # while a floor-area mismatch has none, which would mean this ladder concedes the
        # uncorrectable attribute first. Note also that the order lives here as control
        # flow rather than in `config.py`; if it is ever measured, it should move there
        # under §8's single-home rule, because at that point it is a tuned parameter.
        #
        # Whether the choice should be a per-deal judgment rather than any fixed order is
        # a larger and separate question — OQ-24, which this measurement gates.
        if sqft_tolerance is not None:
            sqft_tolerance = None
            flags.append(
                state.flag(
                    AGENT,
                    FlagKind.RELAXED_MATCH_CRITERIA,
                    f"Only {len(comps)} comps within {radius:.1f} mi; dropped the "
                    f"square-footage band to widen the candidate set.",
                    Severity.INFO,
                )
            )
        elif radius < config.MAX_SEARCH_RADIUS_MILES:
            previous = radius
            radius = min(radius * config.RADIUS_EXPANSION_FACTOR,
                         config.MAX_SEARCH_RADIUS_MILES)
            flags.append(
                state.flag(
                    AGENT,
                    FlagKind.RELAXED_SEARCH_RADIUS,
                    f"Only {len(comps)} comps within {previous:.1f} mi "
                    f"(threshold {config.MIN_QUALIFYING_COMPS}); widened to "
                    f"{radius:.1f} mi. Comps are drawn from a broader area than ideal.",
                    Severity.WARN,
                )
            )
        else:
            previous_tolerance = bedroom_tolerance
            bedroom_tolerance += 1
            flags.append(
                state.flag(
                    AGENT,
                    FlagKind.RELAXED_MATCH_CRITERIA,
                    f"Radius already at the {config.MAX_SEARCH_RADIUS_MILES:.0f} mi "
                    f"ceiling with {len(comps)} comps; loosened bedroom tolerance from "
                    f"±{previous_tolerance} to ±{bedroom_tolerance}.",
                    Severity.WARN,
                )
            )

    if len(comps) < config.MIN_QUALIFYING_COMPS:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.SPARSE_COMPS,
                f"Found {len(comps)} qualifying comps after {iterations} "
                f"iteration(s); the threshold is {config.MIN_QUALIFYING_COMPS}. "
                f"Estimates derived from this set carry materially wider uncertainty "
                f"than a full comp set would imply.",
                Severity.CRITICAL if len(comps) == 0 else Severity.WARN,
            )
        )

    # Spatial concentration is a separate observation from sparsity, and a comp set can
    # fail this check while passing the count check — the Cleveland demo returns a full
    # 8 comps from one coordinate. Reported because eight listings at one point are not
    # eight independent observations of a neighborhood, however many rows they are.
    if comps:
        distinct = _distinct_locations(comps)
        if distinct < config.COMP_MIN_DISTINCT_LOCATIONS:
            area_positioned = count_area_positioned(comps)
            flags.append(
                state.flag(
                    AGENT,
                    FlagKind.COMPS_SPATIALLY_CONCENTRATED,
                    f"{len(comps)} comps resolve to only {distinct} distinct "
                    f"location(s) (threshold {config.COMP_MIN_DISTINCT_LOCATIONS}); "
                    f"{area_positioned} of them carry a city-area coordinate rather "
                    f"than a street address. They are fewer independent observations "
                    f"than the comp count suggests, and reported distances are "
                    f"correspondingly approximate.",
                    Severity.WARN,
                )
            )

    # What the relaxation actually admitted, as distinct from the fact that it happened.
    # Relaxing a filter permits dissimilar comps; it does not produce them. A set that
    # dropped the square-footage band and came back similar anyway is not degraded, and
    # flagging it would report a concession as though it were a consequence.
    if comps:
        drifted = _outside_match_criteria(comps, subject)
        share = len(drifted) / len(comps)
        if share > config.COMP_MAX_OUTSIDE_MATCH_SHARE:
            sizes = sorted(c.square_feet for c in comps if c.square_feet)
            spread = (
                f" Sizes range from {sizes[0]:,.0f} to {sizes[-1]:,.0f} sq ft against a "
                f"subject of {subject.square_footage:,.0f}."
                if sizes and subject.square_footage
                else ""
            )
            flags.append(
                state.flag(
                    AGENT,
                    FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA,
                    f"{len(drifted)} of {len(comps)} comparables fall outside the "
                    f"bedroom count or size range originally searched for; the search "
                    f"was widened to find enough of them.{spread} They are less "
                    f"comparable to this property than the count suggests, and a rent "
                    f"figure read against them inherits that.",
                    Severity.WARN,
                )
            )

    return {
        "comps": comps,
        "search_radius_miles": radius,
        "retrieval_iterations": iterations,
        "flags": flags,
    }
