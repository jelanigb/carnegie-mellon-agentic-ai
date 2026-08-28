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
this). Everything downstream is a hard data dependency and skipping it would produce an
estimate with nothing under it. `plan` is a list rather than a boolean because adding a
second optional step should mean adding a router, not rewriting the representation.

**A rework pass is not automatically a comps-only pass** (corrected U7.4b). This
docstring previously said a rework "only needs comps re-run", and U7.4 built a rework
path on the opposite assumption — that re-entry re-attempts a geocode that failed on a
transient outage. Both could not be true, and the code agreed with the docstring:
`REQUIRED_DEAL_FIELDS` holds no coordinate, so a deal whose address, price and unit count
were extracted on pass one skipped extraction on every later pass and re-attempted
nothing. The rework burned its budget and escalated with the same objection it started
with. Extraction is now re-planned when the accumulated flags say the geocoder was
unreachable rather than the address unresolvable — see `_geocode_is_worth_retrying`.
"""

from __future__ import annotations

import config
import nodes
from state import DealState, DealTerms, FlagKind

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

    Kept as a named function here, delegating to `DealTerms.is_complete()`, because the
    routing decision it expresses is the Planner's and reads better at the call site as a
    sentence about the deal. The predicate itself moved to `state.DealTerms` in U8.1b,
    once the Extractor needed it too — see that method for why.
    """
    return terms.is_complete()


def _geocode_is_worth_retrying(state: DealState) -> bool:
    """True when a previous pass fell back to a city centroid because the Census
    geocoder could not be reached.

    The distinction this reads was built in U7.1b precisely so a routing decision could
    be made on it: `GEOCODER_SERVICE_UNAVAILABLE` means the call failed and the address
    was never tested, while `COORDINATES_FROM_CITY_CENTROID` means it was tested and had
    nothing to resolve to. Only the first is worth another pass — an address with no
    street number resolves no better on the fifth attempt than on the first.

    TODO(U8): this reads the *accumulated* flags, so it stays true on later laps even
    after a retry succeeds — extraction is then re-planned once more for a geocode that
    already resolved. Harmless and bounded here: one cached model call and one geocode
    per lap, capped by `config.MAX_REWORKS`. The same staleness has a sharper consequence
    in `critic._interaction_objections`, where it puts a sentence in the report that is no
    longer true; both are fixed by stamping each flag with the `planner_invocations` that
    produced it. Scheduled at U8, §6 cut list 2a.
    """
    return any(f.kind is FlagKind.GEOCODER_SERVICE_UNAVAILABLE for f in state.flags)


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
    # **Reason 3 was a real gap, found by the eval harness and fixed Aug 28, 2026
    # (U8.1b).** `config.REQUIRED_DEAL_FIELDS` does not include coordinates, and
    # reasonably so — a listing that reaches the Extractor has them derived from its
    # address as an ordinary step (#10). But a caller supplying complete structured terms
    # skipped this node entirely, so nothing ever derived them, and the deal arrived at
    # comp retrieval with nowhere to search. The run then degraded on *geography* while
    # looking like an ordinary result, which is precisely the silent failure Transparent
    # Degradation exists to refuse.
    #
    # Latent rather than active until now — `main.py` always supplies raw text — which is
    # why it survived to U8. The Extractor makes no model call on this path; see
    # `extractor_agent`.
    # **First pass only**, and the qualifier is load-bearing. Without it this reads
    # "geography is incomplete", which stays true forever for an address that was tried
    # and could not be resolved — so every rework lap would re-plan extraction for a
    # geocode that already failed on its merits. That is precisely the distinction U7.1b
    # drew and `_geocode_is_worth_retrying` exists to police: a *service outage* is worth
    # another attempt, an address with nothing to resolve to is not. This clause is about
    # geography never having been *attempted*; later laps are that function's business.
    #
    # Caught by `test_an_unresolvable_address_does_not_re_plan_extraction`, which is the
    # test that exists for exactly this mistake.
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
