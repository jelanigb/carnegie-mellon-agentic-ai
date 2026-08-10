"""Planner agent — pre-flight planning, plus every routing decision in the graph.

Design notes: docs/implementation_plan.md §7 decision #9 (topology) and §3 rationale
item 4 ("conditional edges are the Planner").

**This agent is built, not stubbed.** Every other specialist in U2 is a placeholder
awaiting its own unit, but the Planner has no later unit assigned in §6 — and it needs
none. Decision #9 settled that the pipeline order is fixed by data dependency
(Valuation consumes `state.comps`, Scenario consumes the valuation outputs), so the
Planner never chooses an ordering. Its real degrees of freedom are which optional steps
to skip, rework routing, and escalation, and all three are deterministic functions of
state. There is nothing here for an LLM to decide, which is also why U2 can land while
decision #8 (model IDs) is still open.

Reason/Act/Observe/Decide:

- **Reason.** Inspect what is already known about the deal — are the required deal
  terms present, and is this a first pass or a re-entry from the Critic? — to determine
  which steps this run actually needs.
- **Act.** Write the execution plan into `state.plan` as an ordered list of node names.
  The plan is *data*, not control flow: a router later reads it rather than re-deriving
  the same decision, per §3's rule that routing must be state-encoded.
- **Observe.** Count the invocation. Decision #9 asserts the Planner runs at most
  `1 + rework_count` times per deal; recording the count makes that assertable in a
  test rather than only visible in a LangSmith trace.
- **Decide.** Hand off to the first node in the plan. On re-entry the same reasoning
  runs again against the Critic's updated state, so a rework pass can legally take a
  different route than the first pass did.

**Exactly one step is currently optional**, and that is a property of this pipeline
rather than a limitation of the mechanism. Extraction is skippable because a caller can
supply structured `DealTerms` directly (`scripts/retrieval_evidence.py` does exactly
this, and so does a rework pass that only needs comps re-run). Everything downstream is
a hard data dependency and skipping it would produce an estimate with nothing under it.
`plan` is a list rather than a boolean because adding a second optional step should mean
adding a router, not rewriting the representation.
"""

from __future__ import annotations

import config
import nodes
from state import DealState, DealTerms

AGENT = "planner"

# The fixed spine of the pipeline, in data-dependency order. Not a decision the Planner
# makes — decision #9 — so it is stated once here rather than reassembled per run.
_PIPELINE: tuple[str, ...] = (
    nodes.COMPS_RETRIEVAL,
    nodes.VALUATION_RENT,
    nodes.SCENARIO_FORECAST,
    nodes.CRITIC,
)


def deal_terms_are_complete(terms: DealTerms) -> bool:
    """True when every field in `config.REQUIRED_DEAL_FIELDS` is populated.

    The field list lives in config precisely so that "what counts as complete" is
    tunable without touching an agent (§8). Names are looked up by `getattr`, so a
    typo in the config tuple surfaces here as an `AttributeError` at the first run
    rather than as a silently-always-incomplete deal.
    """
    return all(
        getattr(terms, field_name) is not None
        for field_name in config.REQUIRED_DEAL_FIELDS
    )


def planner_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    steps: list[str] = []

    if not deal_terms_are_complete(state.deal_terms):
        steps.append(nodes.EXTRACTOR)

    steps.extend(_PIPELINE)

    # The rework counter is incremented here, on re-entry, rather than by the Critic on
    # rejection. The two are not equivalent: a rejection that escalates straight to a
    # human is not a rework, and counting it as one would silently shorten the budget.
    # Incrementing at the point of re-entry counts what the name says it counts, and
    # keeps decision #9's invariant exact — `planner_invocations == 1 + rework_count`.
    is_reentry = state.planner_invocations > 0

    return {
        "plan": steps,
        "planner_invocations": state.planner_invocations + 1,
        "rework_count": state.rework_count + 1 if is_reentry else state.rework_count,
    }


# --------------------------------------------------------------------------
# Routers — the conditional edges. No specialist calls another specialist (§3);
# these functions are the only place a next-node decision is made.
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
    never by LangGraph's `recursion_limit` (§3). Exhausting the budget routes to human
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
