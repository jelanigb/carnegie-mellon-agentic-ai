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

import nodes
from agents.critic import Objection, _interaction_objections, _kinds
from state import DealState, FlagKind, Severity, ValuationDetail, flag


def _state(*kinds: FlagKind, cross_checked: bool = True) -> DealState:
    """A DealState carrying exactly the named flags, and a comp cross-check verdict.

    `cross_checked` mirrors what `valuation_rent._cross_check` writes: a
    `comp_implied_rent_median` exists only once
    `config.RENT_COMP_CROSSCHECK_MIN_COMPS` comps survive normalization, and I1/I3 are
    statements about that median. The default is True because that is the ordinary case
    — a deal with enough comps to compare against — and the False path has its own test.
    """
    detail = ValuationDetail()
    if cross_checked:
        detail.comp_implied_rent_median = 2_000.0
    return DealState(
        raw_listing_text="irrelevant to an interaction check",
        valuation_detail=detail,
        flags=[flag("test", kind, f"synthetic {kind}", Severity.WARN, 1) for kind in kinds],
    )


def _messages(objections: list[Objection]) -> str:
    return " ".join(o.message for o in objections)


# ---------------------------------------------------------------------------
# What each check requires (revised U8.6, Aug 30 2026)
#
# I1 and I3 need the comp cross-check to have produced a median; I2 additionally needs
# that median to have disagreed with the estimate. See `_interaction_objections`'
# docstring for why the three do not share one rule.
# ---------------------------------------------------------------------------


def test_a_degraded_comp_set_objects_even_where_the_numbers_agreed():
    """The U8.6 change, asserted directly.

    Agreement between an estimate and a median built on the wrong units, or around the
    wrong location, is a coincidence rather than a confirmation. The divergence gate used
    to read exactly that coincidence as "nothing to report".
    """
    assert len(_interaction_objections(_state(FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA))) == 1
    assert len(_interaction_objections(_state(FlagKind.COORDINATES_FROM_CITY_CENTROID))) == 1


def test_spatial_concentration_alone_still_raises_nothing():
    """I2 keeps the gate. Imprecision is a reason to discount a disagreement, not a
    finding on its own — and every Cleveland and Brooklyn comp set in this corpus is
    single-coordinate, so ungating it would object to a market rather than to a deal."""
    assert _interaction_objections(_state(FlagKind.COMPS_SPATIALLY_CONCENTRATED)) == []


def test_nothing_raised_when_no_flags_at_all():
    assert _interaction_objections(_state()) == []


def test_a_divergence_on_its_own_raises_nothing():
    """The single-flag case must stay quiet, or the check is just a second copy of the
    divergence flag with a louder severity."""
    assert _interaction_objections(_state(FlagKind.RENT_DIVERGES_FROM_COMPS)) == []


def test_no_objection_about_a_comparison_that_never_happened():
    """What replaces the gate for I1 and I3.

    Below `config.RENT_COMP_CROSSCHECK_MIN_COMPS` surviving comps the cross-check returns
    without a median, and the report carries the comp counts instead of a comparison. An
    objection here would describe a median the reader cannot see — the thin-market deals
    are exactly the ones that would collect it.
    """
    assert _interaction_objections(
        _state(FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA, cross_checked=False)
    ) == []
    assert _interaction_objections(
        _state(FlagKind.GEOCODER_SERVICE_UNAVAILABLE, cross_checked=False)
    ) == []


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
    """Deliberately weaker than I1 and I2.

    A centroid fallback moves both halves of the comparison — the comp set and, since the
    hybrid anchor, the rent level the estimate is anchored to. That degrades the
    comparison without voiding it, and the severity says so.
    """
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


# ---------------------------------------------------------------------------
# Pass-scoped flags (U8.5/OQ-15)
#
# The eval batch contains no rework lap (OQ-16), so this is the only place the
# guarantee `critic._kinds` exists for can be asserted right now. Each case builds
# `state.plan`/`planner_invocations` directly rather than driving the graph, for the
# same reason every other test in this file does: `_interaction_objections` is a pure
# function over accumulated state, and these three cases are about how it reads a
# multi-pass flag list, not about reproducing one.
# ---------------------------------------------------------------------------


def test_a_resolved_geocode_clears_the_stale_centroid_objection():
    """The scenario `_kinds`' docstring names: a rework that succeeds must not keep
    tripping I3 off the pass it fixed.

    Pass 1 fell back to a centroid on an outage; pass 2 re-ran the Extractor and it
    resolved cleanly, raising nothing. The Extractor ran this pass (`nodes.EXTRACTOR` is
    in `state.plan`), so it is judged on this pass alone — its pass-1 flag is superseded,
    not carried forward.
    """
    state = DealState(
        raw_listing_text="irrelevant to an interaction check",
        planner_invocations=2,
        plan=[nodes.EXTRACTOR, nodes.COMPS_RETRIEVAL, nodes.VALUATION_RENT],
        valuation_detail=ValuationDetail(comp_implied_rent_median=2_000.0),
        flags=[
            flag(
                nodes.EXTRACTOR,
                FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
                "pass 1: outage",
                Severity.WARN,
                1,
            ),
            flag(
                nodes.VALUATION_RENT,
                FlagKind.RENT_DIVERGES_FROM_COMPS,
                "pass 2: still diverges",
                Severity.WARN,
                2,
            ),
        ],
    )
    assert _interaction_objections(state) == []


def test_an_agent_skipped_this_pass_is_not_read_as_cleared():
    """The wrinkle `_kinds` exists to handle: absence because an agent did not run this
    pass must not read the same as absence because it looked and found nothing.

    The Extractor is missing from `state.plan` — it was not re-run this pass — so its
    pass-1 centroid finding carries forward rather than being dropped.
    """
    state = DealState(
        raw_listing_text="irrelevant to an interaction check",
        planner_invocations=2,
        plan=[nodes.COMPS_RETRIEVAL, nodes.VALUATION_RENT],
        valuation_detail=ValuationDetail(comp_implied_rent_median=2_000.0),
        flags=[
            flag(
                nodes.EXTRACTOR,
                FlagKind.COORDINATES_FROM_CITY_CENTROID,
                "pass 1: centroid, unresolvable address",
                Severity.WARN,
                1,
            ),
            flag(
                nodes.VALUATION_RENT,
                FlagKind.RENT_DIVERGES_FROM_COMPS,
                "pass 2: still diverges",
                Severity.WARN,
                2,
            ),
        ],
    )
    objections = _interaction_objections(state)
    assert len(objections) == 1
    assert objections[0].severity == Severity.WARN
    assert not objections[0].retryable


def test_an_agent_that_ran_this_pass_is_judged_on_this_pass_alone():
    """The positive case behind the fix, without which the two above prove nothing
    about which rule actually fired.

    Same shape as the "resolved" case, but the Extractor's pass-1 flag differs from its
    (empty) pass-2 contribution only in whether it ran — confirming supersession, not
    just an absent kind.
    """
    state = DealState(
        raw_listing_text="irrelevant to an interaction check",
        planner_invocations=2,
        plan=[nodes.EXTRACTOR, nodes.COMPS_RETRIEVAL, nodes.VALUATION_RENT],
        flags=[
            flag(
                nodes.EXTRACTOR,
                FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
                "pass 1: outage",
                Severity.WARN,
                1,
            ),
        ],
    )
    # No RENT_DIVERGES_FROM_COMPS this pass either, so the gate alone would already
    # return [] — the assertion that matters is on `_kinds` directly.
    assert FlagKind.GEOCODER_SERVICE_UNAVAILABLE not in _kinds(state)


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
