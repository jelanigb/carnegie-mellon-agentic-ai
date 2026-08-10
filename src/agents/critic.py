"""Critic/Reviewer agent — **PARTIAL in U2**. Cross-agent checks are U7.

Split deliberately, because the two halves of this agent have different dependencies:

- **Built now: flag aggregation into a confidence score, and the human-review
  escalation decision.** These depend only on `state.flags` and on weights that already
  live in `config.FLAG_SEVERITY_PENALTY`. Building them in U2 is what makes the
  `human_review` interrupt reachable at runtime rather than only in a test, and the
  escalation path is the whole point of wiring that node into the skeleton.
- **Stubbed for U7: cross-agent consistency checking**, the part that sets
  `critic_rejected` and drives the rework cycle. It cannot be written yet in any honest
  form: the checks worth making compare a rent estimate against its comp set and a
  scenario band against its base value, and neither the Valuation nor the Scenario
  agent produces anything in this build. A consistency check with only one populated
  input is a check that always passes, which §2's own argument rules out — a signal
  that cannot fire conveys nothing.

`_consistency_objections()` is left as a real function returning an empty list rather
than being omitted, so the rework branch below is present, reachable, and testable by
substituting that one function. The cycle is proven bounded in
`tests/test_flag_propagation.py` that way, which is the U2 obligation; U7 supplies the
objections that make it fire on its own.

Reason/Act/Observe/Decide:

- **Reason.** Determine which upstream outputs are mutually checkable given what
  actually ran, and how much each accumulated flag should cost the deal's confidence.
- **Act.** Run the available consistency checks and aggregate flag severities into a
  single score.
- **Observe.** Compare the score against `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD`,
  and note whether the rework budget still has room.
- **Decide.** Proceed to the report, send the deal back for one more pass, or escalate
  to a human. The decision is written to state; the routing that acts on it lives in
  `agents/planner.route_after_critic`, never here (§3 — no agent calls another agent).
"""

from __future__ import annotations

import config
from state import DealState, FlagKind, Severity, flag

AGENT = "critic"


# Flags this agent raises as *consequences* of the score. They are excluded from the
# score's own inputs: a rework pass re-runs the Critic, the reducer appends its previous
# flags to the accumulated list, and counting them would let the score drive itself down
# on each lap of a cycle that exists to improve the deal. Confidence must be a function
# of what the pipeline observed, not of what the Critic previously concluded about it.
_DERIVED_KINDS = frozenset({FlagKind.LOW_CONFIDENCE_ESTIMATE, FlagKind.REWORK_LIMIT_REACHED})


def confidence_from_flags(state: DealState) -> float:
    """Aggregate accumulated flags into a single confidence score in [0, 1].

    Starts at full confidence and subtracts a per-severity penalty for every flag
    raised anywhere upstream. Info-severity flags cost nothing by design: they disclose
    a mechanism (rent was FMR-anchored; a metro-level appreciation tier was used)
    rather than a weakness, and charging them would make the score fall on runs where
    nothing went wrong.

    The weights are PROVISIONAL and tuned in U7 — they live in `config` for exactly
    that reason (§8). The shape of the function is the U2 commitment; the numbers are
    not.
    """
    penalty = sum(
        config.FLAG_SEVERITY_PENALTY.get(f.severity, 0.0)
        for f in state.flags
        if f.kind not in _DERIVED_KINDS
    )
    return max(0.0, min(1.0, 1.0 - penalty))


def _consistency_objections(state: DealState) -> list[str]:
    """Cross-agent contradictions found in this run. **U7 populates this.**

    Returns an empty list today, so `critic_rejected` is never set and the rework cycle
    never fires on its own in this build. That is accurate rather than convenient:
    there is nothing yet to be inconsistent with.

    TODO(U7): implement the checks named in §1 — the rent estimate against the comp
    set's own distribution, the scenario bands against the base value they branch from,
    the value estimate against the listing price, and comp-source concentration (the
    corpus is 91% RentDigs.com, so eight comps from one feed are not eight independent
    observations — `Comp.listing_source` exists to make that detectable).
    """
    return []


def critic_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    objections = _consistency_objections(state)
    confidence = confidence_from_flags(state)

    flags = []
    for objection in objections:
        flags.append(
            flag(AGENT, FlagKind.CRITIC_INCONSISTENCY, objection, Severity.WARN)
        )

    # Escalate on either of two independent grounds. A critical flag is sufficient on
    # its own, and not only as a contributor to the score:
    #
    # Severity.CRITICAL is defined in the report as "the estimate should not be relied
    # on without addressing this". A deal carrying one that still reaches a report as a
    # normal result contradicts what the system says about its own flag. That is not
    # hypothetical arithmetic — the U2 demo produced it. One critical flag costs 0.40,
    # landing confidence at exactly 0.60, and `0.60 < 0.60` is false, so the
    # zero-comps Chicago and no-coordinates runs both reported without escalating. The
    # threshold is a judgment about *accumulated* uncertainty and is the right tool for
    # a pile of warnings; it is the wrong tool for a single disqualifying observation.
    #
    # TODO(U7): decision #6 sets both the 0.60 threshold and the severity weights as
    # PROVISIONAL. Confirm this rule when they are tuned — if the weights were retuned
    # so that one critical flag falls clearly below the threshold, the two conditions
    # would coincide and this one could fold back into the score. Keeping them separate
    # is deliberate even then: it makes the guarantee independent of the weights.
    low_confidence = confidence < config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD
    has_critical = any(f.severity == Severity.CRITICAL for f in state.flags)

    if low_confidence or has_critical:
        reason = (
            f"Confidence {confidence:.2f} is below the "
            f"{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold"
            if low_confidence
            else f"Confidence {confidence:.2f} clears the threshold, but a "
                 f"critical-severity disclosure was raised"
        )
        flags.append(
            flag(
                AGENT,
                FlagKind.LOW_CONFIDENCE_ESTIMATE,
                f"{reason}; routing to human review rather than reporting as a "
                f"normal result.",
                Severity.WARN,
            )
        )

    rejected = bool(objections)
    budget_exhausted = rejected and state.rework_count >= config.MAX_REWORKS
    if budget_exhausted:
        flags.append(
            flag(
                AGENT,
                FlagKind.REWORK_LIMIT_REACHED,
                f"Objections remain after {state.rework_count} rework pass(es), the "
                f"configured maximum. Escalating rather than looping further.",
                Severity.WARN,
            )
        )

    return {
        "confidence_score": confidence,
        "critic_rejected": rejected,
        "needs_human_review": low_confidence or has_critical or budget_exhausted,
        "flags": flags,
        "stub_nodes": [AGENT],
    }
