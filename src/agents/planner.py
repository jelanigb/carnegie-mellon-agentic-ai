"""Planner agent — pre-flight planning, plus every routing decision in the graph.

**Nothing here is an LLM call.** The pipeline order is fixed by data dependency
(Valuation consumes `state.comps`, Scenario consumes the valuation outputs), so the
Planner never chooses an ordering. Its real degrees of freedom are which optional steps
to skip, rework routing, and escalation, and all three are deterministic functions of
state.

Reason/Act/Observe — **three stages, not the usual four:**

- **Reason.** Inspect what is already known about the deal — are the required deal
  terms present, and is this a first pass or a re-entry from the Critic? — to determine
  which steps this run actually needs. On a rework the same inspection runs again against
  the Critic's updated state, so a second pass can legitimately plan a different route
  than the first one did.
- **Act.** Write the execution plan into `state.plan` as an ordered list of node names.
  The plan is *data*, not control flow: a router later reads it rather than re-deriving
  the same decision. Routing is state-encoded throughout this graph.
- **Observe.** Count the invocation. The Planner runs at most `1 + rework_count` times
  per deal; recording the count makes that assertable in a test rather than only visible
  in a trace.

**There is no Decide stage, and its absence is the design rather than a gap.** In the
other specialists Decide is a step of its own — the Critic weighs a finished score against
a threshold and picks report, rework or escalate; the Valuation agent settles which
approximations the estimate it just produced has to carry. Here there is nothing left to
settle after Act, because **the plan is the decision**: writing it and choosing it are one
step, and a fourth stage would name that step twice. What remains — actually going to the
next node — is not this function's to do. `planner_agent` returns a partial state update
and stops; the jump is made by `route_after_planner`, a conditional edge at the foot of
this module.

Both live in this file, which is why the module is described as holding every routing
decision in the graph, but they sit on opposite sides of the node boundary and the
separation is the point: a route is a fact recorded on `state` before it is a jump anyone
takes. `docs/diagrams/agent_logic_flow.md`'s Planner panel draws the node the same way,
ending at EXIT rather than at a decision.

**Exactly one step is currently optional**, and that is a property of this pipeline
rather than a limitation of the mechanism. Extraction is skippable because a caller can
supply structured `DealTerms` directly (`scripts/retrieval_evidence.py` does exactly
this). Everything downstream is a hard data dependency and skipping it would produce an
estimate with nothing under it. `plan` is a list rather than a boolean because adding a
second optional step should mean adding a router, not rewriting the representation.

**A rework pass is not automatically a comps-only pass.** Extraction is re-planned when
the accumulated flags say the geocoder was *unreachable* rather than the address
unresolvable — see `_geocode_is_worth_retrying`. Without that distinction a rework
re-runs everything except the one step that could change the answer, burns its budget,
and escalates with the objection it started with.
"""

from __future__ import annotations

import config
import nodes
from state import DealState, DealTerms, FlagKind

AGENT = "planner"

# The fixed spine of the pipeline, in data-dependency order. Not a decision the Planner
# makes, so it is stated once here rather than reassembled per run.
_PIPELINE: tuple[str, ...] = (
    nodes.COMPS_RETRIEVAL,
    nodes.VALUATION_RENT,
    nodes.SCENARIO_FORECAST,
    nodes.CRITIC,
)


def deal_terms_are_complete(terms: DealTerms) -> bool:
    """True when every field in `config.REQUIRED_DEAL_FIELDS` is populated.

    Kept as a named function here, delegating to `DealTerms.is_complete()`, because the
    routing decision it expresses is the Planner's and reads better at the call site as a
    sentence about the deal. The predicate itself lives on `state.DealTerms` because the
    Extractor needs it too.
    """
    return terms.is_complete()


def _geocode_is_worth_retrying(state: DealState) -> bool:
    """True when a previous pass fell back to a city centroid because the Census
    geocoder could not be reached.

    Two flags describe two different failures, and only one is worth retrying:
    `GEOCODER_SERVICE_UNAVAILABLE` means the call failed and the address was never
    tested, while `COORDINATES_FROM_CITY_CENTROID` means it was tested and had nothing to
    resolve to. An address with no street number resolves no better on the fifth attempt
    than on the first.

    **Reads only the pass that just completed**, not the accumulated flags. Read
    cumulatively this stays true on later laps even after a retry succeeded, and
    extraction gets re-planned for a geocode that has already resolved. Called from
    `planner_agent` before re-entry increments `planner_invocations`, so
    `state.planner_invocations` here still names the pass that just finished; filtering to
    it is what makes a resolved geocode stop re-triggering extraction.
    """
    return any(
        f.kind is FlagKind.GEOCODER_SERVICE_UNAVAILABLE
        and f.planner_invocations == state.planner_invocations
        for f in state.flags
    )


def planner_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    steps: list[str] = []

    # Three independent reasons to route through the Extractor node:
    #
    #   1. The terms are not all there yet — the ordinary case.
    #   2. They are, but the coordinates behind them came from a geocoder that was down.
    #      This is the whole justification for the Critic's rework path, which without it
    #      re-runs everything *except* the step that could change the answer.
    #   3. They are, and the geography behind them is incomplete — no coordinates, or
    #      coordinates with no county resolved. Both leave the FMR anchor unreachable.
    #
    # **Reason 3 is easy to miss.** `config.REQUIRED_DEAL_FIELDS` does not include
    # coordinates, and reasonably so — a listing that reaches the Extractor has them
    # derived from its address as an ordinary step. But a caller supplying complete
    # structured terms would skip this node entirely, so nothing would derive them, and
    # the deal would arrive at comp retrieval with nowhere to search. The run then
    # degrades on *geography* while looking like an ordinary result, which is the silent
    # failure Transparent Degradation exists to refuse. The Extractor makes no model call
    # on this path; see `extractor_agent`.
    #
    # **First pass only**, and the qualifier is load-bearing. Without it this reads
    # "geography is incomplete", which stays true forever for an address that was tried
    # and could not be resolved — so every rework lap would re-plan extraction for a
    # geocode that already failed on its merits. A *service outage* is worth another
    # attempt, an address with nothing to resolve to is not; this clause is about
    # geography never having been *attempted*, and later laps are
    # `_geocode_is_worth_retrying`'s business.
    #
    # Caught by `test_an_unresolvable_address_does_not_re_plan_extraction`.
    needs_geocode = (
        state.planner_invocations == 0 and state.deal_terms.geography_is_incomplete()
    )
    if (
        not deal_terms_are_complete(state.deal_terms)
        or _geocode_is_worth_retrying(state)
        or needs_geocode
    ):
        steps.append(nodes.EXTRACTOR)

    steps.extend(_PIPELINE)

    # The rework counter is incremented here, on re-entry, rather than by the Critic on
    # rejection. The two are not equivalent: a rejection that escalates straight to a
    # human is not a rework, and counting it as one would silently shorten the budget.
    # Incrementing at the point of re-entry counts what the name says it counts, and
    # keeps the invariant exact — `planner_invocations == 1 + rework_count`.
    is_reentry = state.planner_invocations > 0

    return {
        "plan": steps,
        "planner_invocations": state.planner_invocations + 1,
        "rework_count": state.rework_count + 1 if is_reentry else state.rework_count,
    }


# --------------------------------------------------------------------------
# Routers — the conditional edges. No specialist calls another specialist; these
# functions are the only place a next-node decision is made.
# --------------------------------------------------------------------------


def route_after_planner(state: DealState) -> str:
    """Enter the plan at its first step.

    Reads `state.plan` rather than re-running `deal_terms_are_complete`. Duplicating
    that predicate here would create two places where the skip decision lives and one
    place for them to disagree — the plan in state would then describe a route the
    graph did not actually take, which is worse than having no plan at all.
    """
    if state.plan:
        return state.plan[0]
    # A plan is always written by planner_agent immediately upstream, so an empty plan
    # means state was constructed by hand (a test, or a caller invoking a router
    # directly). Fall through to the pipeline spine rather than raising.
    return _PIPELINE[0]


def route_after_critic(state: DealState) -> str:
    """The graph's only branching decision with more than two outcomes.

    Order matters. Escalation is checked before rework because a deal the Critic wants
    a human to look at should reach a human, not be quietly re-run first — and because
    a rework pass that raised the same concerns again would arrive back here anyway,
    one full pipeline later.

    The rework cycle is bounded by `config.MAX_REWORKS` against `state.rework_count`,
    never by LangGraph's `recursion_limit`. Exhausting the budget routes to human
    review — a graceful escalation — rather than raising an opaque framework exception.
    """
    if state.needs_human_review:
        return nodes.HUMAN_REVIEW

    if state.critic_rejected:
        if state.rework_count < config.MAX_REWORKS:
            return nodes.PLANNER
        # Budget exhausted with the Critic still unsatisfied. The deal does not proceed
        # to a report as though the objection had been resolved.
        return nodes.HUMAN_REVIEW

    return nodes.SUMMARIZER
