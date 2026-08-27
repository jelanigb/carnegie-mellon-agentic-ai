"""Interaction checks — the Critic's one contribution nothing upstream can make.

These are unit tests over a pure function, deliberately kept out of
`test_flag_propagation.py`. That suite proves a flag raised in one agent survives every
downstream node and reaches the report; these prove a *combination* of flags is read
correctly in the first place. Different guarantee, different failure mode, and mixing
them would make the propagation suite fail for reasons that have nothing to do with
propagation. The propagation cases for these arrive in U7.4, once the checks are wired.

Each test constructs the flag set directly rather than driving the pipeline to produce
it. That is the point of the design: an interaction check reads accumulated state and
nothing else, so it needs no LLM, no network, no corpus and no trained model to exercise
— which is precisely what the checks U7 originally planned could not offer.
"""

from __future__ import annotations

from agents.critic import Objection, _interaction_objections
from state import DealState, FlagKind, Severity, flag


def _state(*kinds: FlagKind) -> DealState:
    """A DealState carrying exactly the named flags and nothing else."""
    return DealState(
        raw_listing_text="irrelevant to an interaction check",
        flags=[flag("test", kind, f"synthetic {kind}", Severity.WARN) for kind in kinds],
    )


def _messages(objections: list[Objection]) -> str:
    return " ".join(o.message for o in objections)


# ---------------------------------------------------------------------------
# The gate: no divergence, no interaction
# ---------------------------------------------------------------------------


def test_no_objections_when_the_cross_check_did_not_diverge():
    """Every interaction here is about how to read a divergence. Without one there is
    nothing to misread, however degraded the comp set was."""
    assert _interaction_objections(_state()) == []
    assert _interaction_objections(_state(FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA)) == []
    assert _interaction_objections(_state(FlagKind.COMPS_SPATIALLY_CONCENTRATED)) == []
    assert _interaction_objections(_state(FlagKind.COORDINATES_FROM_CITY_CENTROID)) == []


def test_a_divergence_on_its_own_raises_nothing():
    """The single-flag case must stay quiet, or the check is just a second copy of the
    divergence flag with a louder severity."""
    assert _interaction_objections(_state(FlagKind.RENT_DIVERGES_FROM_COMPS)) == []


# ---------------------------------------------------------------------------
# I1 — relaxation on a priced attribute
# ---------------------------------------------------------------------------


def test_comps_outside_match_criteria_with_divergence_is_critical():
    objections = _interaction_objections(
        _state(FlagKind.RENT_DIVERGES_FROM_COMPS, FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA)
    )
    assert len(objections) == 1
    assert objections[0].severity == Severity.CRITICAL
    assert not objections[0].retryable
    # Named in the words a reader has, not by the constant that holds them.
    assert "bedrooms" in objections[0].message


def test_a_relaxed_radius_alone_is_not_a_relaxed_attribute():
    """Widening the radius keeps the attribute filters intact, so the comp set still
    describes the same kind of unit. Conflating the two would fire I1 on ordinary
    thin-market deals."""
    objections = _interaction_objections(
        _state(FlagKind.RENT_DIVERGES_FROM_COMPS, FlagKind.RELAXED_SEARCH_RADIUS)
    )
    assert objections == []


def test_relaxation_without_measured_drift_is_not_an_objection():
    """The repointing in U7.3, asserted.

    `RELAXED_MATCH_CRITERIA` says the retrieval loop dropped a filter. It does not say
    the comps that came back were unlike the subject — dropping a band permits that
    without producing it. Only the measured consequence is an objection.
    """
    objections = _interaction_objections(
        _state(FlagKind.RENT_DIVERGES_FROM_COMPS, FlagKind.RELAXED_MATCH_CRITERIA)
    )
    assert objections == []


# ---------------------------------------------------------------------------
# I2 — the comp median is a point sample
# ---------------------------------------------------------------------------


def test_spatially_concentrated_comps_with_divergence_are_critical():
    objections = _interaction_objections(
        _state(FlagKind.RENT_DIVERGES_FROM_COMPS, FlagKind.COMPS_SPATIALLY_CONCENTRATED)
    )
    assert len(objections) == 1
    assert objections[0].severity == Severity.CRITICAL
    assert not objections[0].retryable


# ---------------------------------------------------------------------------
# I3 — the comps moved and the model did not
# ---------------------------------------------------------------------------


def test_centroid_fallback_with_divergence_is_warn_not_critical():
    """Deliberately weaker than I1 and I2. The rent model is location-blind below the
    county, so a centroid fallback moves the comps without moving the estimate — that
    degrades the comparison and points at which side to doubt, rather than voiding it."""
    objections = _interaction_objections(
        _state(
            FlagKind.RENT_DIVERGES_FROM_COMPS,
            FlagKind.COORDINATES_FROM_CITY_CENTROID,
        )
    )
    assert len(objections) == 1
    assert objections[0].severity == Severity.WARN
    assert not objections[0].retryable


def test_an_unreachable_geocoder_makes_the_same_objection_retryable():
    """The U7.1b split earning its keep: same consequence, different cause, and only
    this cause is worth spending a rework pass on."""
    objections = _interaction_objections(
        _state(
            FlagKind.RENT_DIVERGES_FROM_COMPS,
            FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
        )
    )
    assert len(objections) == 1
    assert objections[0].severity == Severity.WARN
    assert objections[0].retryable
    assert "re-run" in objections[0].message


# ---------------------------------------------------------------------------
# Co-occurrence
# ---------------------------------------------------------------------------


def test_independent_reasons_accumulate_rather_than_collapsing():
    """A thin-market deal can trip all three. They are separate reasons the same verdict
    is unreadable, and reporting one would hide the others from the reviewer."""
    objections = _interaction_objections(
        _state(
            FlagKind.RENT_DIVERGES_FROM_COMPS,
            FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA,
            FlagKind.COMPS_SPATIALLY_CONCENTRATED,
            FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
        )
    )
    assert len(objections) == 3
    assert [o.severity for o in objections] == [
        Severity.CRITICAL,
        Severity.CRITICAL,
        Severity.WARN,
    ]
    assert sum(o.retryable for o in objections) == 1


# ---------------------------------------------------------------------------
# Reader-facing language
# ---------------------------------------------------------------------------


def test_objection_text_carries_no_internal_vocabulary():
    """Objection text reaches the investor-facing report, so it has to stand on its own.

    Section numbers, decision numbers, unit numbers and `config` constant names are the
    vocabulary of this repository, not of the person reading the output. They are welcome
    in docstrings and comments — which evolve alongside the code and are read by people
    who have the repo open — and nowhere that a reader or a demo audience will see.

    Enforced here rather than left as a convention because it is the kind of rule that
    holds until someone pastes a sentence from a docstring into a message.
    """
    import itertools
    import re

    every_kind = [
        FlagKind.RENT_DIVERGES_FROM_COMPS,
        FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA,
        FlagKind.COMPS_SPATIALLY_CONCENTRATED,
        FlagKind.COORDINATES_FROM_CITY_CENTROID,
        FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
    ]
    banned = re.compile(
        r"§\d"                     # section reference
        r"|(?<![\w$])#\d+"          # decision reference
        r"|\bU\d+(\.\d+)?\b"        # unit reference
        r"|\bconfig\.[A-Z_]+"       # config constant
        r"|\bFlagKind\.",           # enum member
    )

    # Every reachable combination, so a message added later cannot slip through on a
    # branch this test happens not to construct.
    for size in range(1, len(every_kind) + 1):
        for combo in itertools.combinations(every_kind, size):
            for objection in _interaction_objections(_state(*combo)):
                found = banned.search(objection.message)
                assert found is None, (
                    f"objection text leaks internal vocabulary "
                    f"{found.group(0)!r}: {objection.message}"
                )
