"""Critic/Reviewer agent — **PARTIAL in U2**. Cross-agent checks are U7.

Split deliberately, because the two halves of this agent have different dependencies:

- **Built now: flag aggregation into a confidence score, and the human-review
  escalation decision.** These depend only on `state.flags` and on weights that already
  live in `config.FLAG_SEVERITY_PENALTY`. Building them in U2 is what makes the
  `human_review` interrupt reachable at runtime rather than only in a test, and the
  escalation path is the whole point of wiring that node into the skeleton.
- **Stubbed for U7: cross-agent consistency checking**, the part that sets
  `critic_rejected` and drives the rework cycle. In U2 it could not be written in any
  honest form, because the checks worth making needed Valuation and Scenario output and
  neither agent produced any. A consistency check with only one populated input is a
  check that always passes, which §2's own argument rules out — a signal that cannot
  fire conveys nothing.

  **That precondition is now met.** U5 populates `rent_estimate` and `ValuationDetail`;
  U6 populates `scenarios` and `ForecastDetail`. See `_consistency_objections()` below
  for what U7 actually checks, which is not the list U2 anticipated.

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
  `agents/planner.route_after_critic`, never here (§3 — agents communicate only through
  shared state; routing is an edge's job, not a specialist's).
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
    never fires on its own in this build.

    The four checks §1 originally named were reviewed against the built system while
    planning U7, and **the list did not survive contact with it.** Recorded here rather
    than silently replaced, because a TODO that names work the build has since made
    impossible is worse than no TODO:

    1. *Rent estimate against the comp set's distribution* — **already built, and not
       here.** `agents/valuation_rent.py` raises `RENT_DIVERGES_FROM_COMPS` as its own
       Observe step, using `ValuationDetail.comp_implied_rent_p25/median/p75`. The
       Critic **consumes that flag** rather than recomputing it. Two agents deriving one
       fact independently is two agents that can disagree about it.
    2. *Value estimate against the listing price* — **dead.** Decision #15 made
       `DealState.value_estimate` permanently `None`; nothing in this build writes it.
       This TODO predates that decision.
    3. *Scenario bands against the base they branch from* — **live, TODO(U7).** Both
       `ForecastDetail.projection_base_price`/`_rent` and the `Scenario` bands are
       populated by U6.
    4. *Comp-source concentration* — **live, TODO(U7).** The corpus is 91%
       RentDigs.com, so eight comps from one feed are not eight independent
       observations; `Comp.listing_source` exists to make that detectable. Must not
       double-count with `COMPS_SPATIALLY_CONCENTRATED`, which is a different
       concentration and already fires.

    TODO(U7): implement 3 and 4, plus two checks U2 did not anticipate because the state
    they read did not exist yet — the forecast's projection base against the figures it
    claims to project from, and comp attribute drift against the subject after
    relaxation.

    Two further comparisons — the listing's *stated* rents against `rent_estimate`, and
    its asking price against `ValuationDetail.benchmark_median_sale_price` — are
    deliberately **not** objections in U7. They ship as Summarizer disclosures instead,
    because the rent one currently reports ~-29% on every demo deal: FMR is a
    40th-percentile rent while the model predicts ~1.40x FMR, so the gap measures a
    percentile mismatch rather than the deal. TODO(U8): promote both once Zillow ZORI
    settles which baseline is right.
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
    # TODO(U8): decision #6 sets both the 0.60 threshold and the severity weights as
    # PROVISIONAL, and **U8 is where they get tuned, not U7** — the eval batch is what
    # exercises the range, and the five demo deals were calibrated to run clean, so they
    # cannot. U7 lands the mechanism; U8 supplies the numbers.
    #
    # Confirm this rule when they are tuned — if the weights were retuned so that one
    # critical flag falls clearly below the threshold, the two conditions would coincide
    # and this one could fold back into the score. Keeping them separate is deliberate
    # even then: it makes the guarantee independent of the weights.
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
