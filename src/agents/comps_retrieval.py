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

Relaxation is ordered by how much accuracy each concession costs: the square-footage
band goes first (weakest signal), then the search radius widens, then bedroom-count
tolerance loosens (strongest signal, conceded last). A single prompt has no way to
inspect the result of its own retrieval and adjust; this loop is why that matters.
"""

from __future__ import annotations

import config
from state import DealState, FlagKind, Severity, count_area_positioned, flag
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
                flag(
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
                flag(
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

        # Relax exactly one criterion per pass, weakest signal conceded first.
        if sqft_tolerance is not None:
            sqft_tolerance = None
            flags.append(
                flag(
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
                flag(
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
                flag(
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
            flag(
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
                flag(
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

    return {
        "comps": comps,
        "search_radius_miles": radius,
        "retrieval_iterations": iterations,
        "flags": flags,
    }
