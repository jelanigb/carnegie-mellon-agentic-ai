"""StateGraph assembly — nodes, edges, routing, compile.

This module is *only* wiring. Every decision it expresses was made elsewhere: the
topology in §7 decision #9 (Planner topology), the state schema in §5, the node names in `nodes.py`. If a
piece of reasoning shows up here, it is in the wrong file — a specialist's logic
belongs in `agents/`, and a routing rule belongs in a `route_*` function beside the
Planner (§3, "agents communicate only through shared state").

**The topology** (decision #9 — pre-flight Planner, not a supervisor):

    START → Planner → [Extractor] → Comps → Valuation → Scenario → Critic
                                                                     ├→ Summarizer → END
                                                                     ├→ human_review → Summarizer
                                                                     └→ Planner   (the one cycle)

Three properties of this graph are review criteria rather than implementation details,
and each is checkable against the diagram `scripts/export_graph_diagram.py` generates
from the compiled object:

1. **`Critic → Planner` is the only cycle.** A second cycle means the design drifted
   back toward the rejected supervisor topology, and is a defect rather than a
   variation.
2. **Exactly two conditional edges exist** — the Planner's entry skip and the Critic's
   three-way split. Everything else is static, because the pipeline order is forced by
   data dependency and is not the Planner's to choose.
3. **The cycle is bounded by `rework_count` in state**, never by `recursion_limit`.
   Hitting the framework's limit raises an opaque exception; the counter escalates to
   human review instead, which is the behaviour Checkpoint 2.1 specified.

**Why a checkpointer is always present.** `interrupt()` has nowhere to persist a paused
run without one, so `human_review` would fail rather than pause. The default is
in-memory, which is enough for a single process and for tests; `main.py` supplies the
SQLite saver for runs that should survive the process. Either way a `thread_id` is
required at invoke time — omitting it is an error, not a default.
"""

from __future__ import annotations

from typing import Optional

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

import nodes
from agents.comps_retrieval import comps_retrieval_agent
from agents.critic import critic_agent
from agents.extractor import extractor_agent
from agents.human_review import human_review_node
from agents.planner import planner_agent, route_after_critic, route_after_planner
from agents.scenario_forecast import scenario_forecast_agent
from agents.summarizer import summarizer_agent
from agents.valuation_rent import valuation_rent_agent
from state import (
    BranchLedgerEntry,
    Comp,
    ConfidenceBreakdown,
    DealState,
    DealStatus,
    DealTerms,
    Flag,
    FlagKind,
    FlagScope,
    LocationPrecision,
    ForecastDetail,
    Recommendation,
    RecommendationDetail,
    RentEstimateSource,
    Scenario,
    Severity,
    ValuationDetail,
)


def state_serde() -> JsonPlusSerializer:
    """Serializer that knows this project's state types by name.

    A checkpointer round-trips state through msgpack, and LangGraph 1.x warns on every
    custom type it deserializes without an explicit allowlist entry — *"this will be
    blocked in a future version."* Six of this project's types cross that boundary on
    any run that pauses, so without this the paused-and-resumed path (the entire point
    of `human_review`) is on a deprecation clock, and the warnings bury the interrupt
    payload the demo is meant to show.

    Listing the types is also the safer posture rather than merely the quieter one: the
    permissive default deserializes *any* type a checkpoint file names. Passing an
    explicit allowlist switches that to deny-by-default, and these are everything the
    graph actually persists.

    **Four names were missing from it until Aug 22, 2026, and how that surfaced is the
    reason to record it.** `DealStatus`, `LocationPrecision`, `RentEstimateSource` and
    `AppreciationTier` (removed in U6) are all `StrEnum`, and a `StrEnum` member *is* a
    `str`, so a
    blocked deserialization degraded to the bare string, which Pydantic then coerced
    straight back to the enum on the next validation. Nothing broke and no output was
    ever wrong. The gap was visible only as a log line, and it took a U5 test asserting
    on a resumed run to put that line somewhere anyone would read it. A deny-by-default
    list whose omissions are silent is a list that drifts, which is what happened here
    across three units.

    So the rule this docstring is really stating: **every type reachable from
    `DealState` belongs here, enums included, whether or not omitting it currently
    appears to matter.** `ValuationDetail` joined in U5 as a genuinely new type; the
    four enums joined because they should have been here all along.

    **It drifted again across three more units, and was caught Sept 1, 2026 the same
    way — by reading a log line nobody was reading.** `ConfidenceBreakdown` (U7),
    `FlagScope` (U8.5), `Recommendation` and `RecommendationDetail` (U9.4) were all
    reachable from `DealState` and all absent. **The recurrence is the finding, not the
    omission:** the rule above was already written, in this docstring, by the pass that
    learned it — and stating a rule next to the list does not keep the list current,
    because the person adding a state field is not reading the serializer.

    **This time the degradation is one level worse than the enum case, which is why it
    matters more than it looks.** `ConfidenceBreakdown` and `RecommendationDetail` are
    `BaseModel`, not `StrEnum`, so a blocked deserialization yields a plain **`dict`**,
    not a string. Measured on a resumed `staten-island` run: every field value survived
    and Pydantic re-validated the dict back into the model at the node boundary, so the
    rendered report was never wrong — but `graph.invoke`'s **return value** carries the
    raw dict, and any caller that reaches into it gets an `AttributeError` rather than a
    verdict.

    **Nothing had that caller until U9.7.** `main.py` reads only `report_markdown`, a
    `str`, and the eval runner reads `recommendation` off a *non*-resumed invoke — the
    round trip happens on resume, and the harness never resumes. The Streamlit surface is
    the first consumer to read a typed field out of a resumed run, which is precisely the
    escalated-deal path it exists to demonstrate. A defect that is invisible until the
    one path a demo is built around is the argument for the rule, restated.

    Note the constructor argument rather than the more obvious
    `JsonPlusSerializer().with_msgpack_allowlist(...)`: that method returns `self`
    unchanged when the base allowlist is the permissive default, so the fluent form
    silently does nothing. Verified against the installed version rather than assumed —
    the warnings are what made it visible.
    """
    return JsonPlusSerializer(
        allowed_msgpack_modules=[
            DealState,
            DealTerms,
            Comp,
            ValuationDetail,
            Flag,
            FlagKind,
            Severity,
            FlagScope,
            DealStatus,
            LocationPrecision,
            RentEstimateSource,
            Scenario,
            BranchLedgerEntry,
            ForecastDetail,
            ConfidenceBreakdown,
            Recommendation,
            RecommendationDetail,
        ]
    )


# The node function behind each name. Kept as a mapping so that "every declared node is
# registered" is a property of one data structure rather than of eight call sites.
NODE_FUNCTIONS = {
    nodes.PLANNER: planner_agent,
    nodes.EXTRACTOR: extractor_agent,
    nodes.COMPS_RETRIEVAL: comps_retrieval_agent,
    nodes.VALUATION_RENT: valuation_rent_agent,
    nodes.SCENARIO_FORECAST: scenario_forecast_agent,
    nodes.CRITIC: critic_agent,
    nodes.HUMAN_REVIEW: human_review_node,
    nodes.SUMMARIZER: summarizer_agent,
}


def _checked_mapping(*targets: str) -> dict[str, str]:
    """Build a conditional-edge mapping, rejecting any target that is not a real node.

    This is the check `nodes.ALL_NODES` was defined for. A router returning a name with
    no matching node fails at invoke time with an error pointing at the graph rather
    than at the typo — trap 3 in the LangGraph onboarding notes — so the mapping is
    validated at import instead, when the traceback still names this line.
    """
    unknown = [t for t in targets if t not in nodes.ALL_NODES]
    if unknown:
        raise ValueError(
            f"Conditional edge targets are not registered nodes: {unknown}. "
            f"Known nodes: {list(nodes.ALL_NODES)}"
        )
    return {target: target for target in targets}


def build_graph(checkpointer: Optional[object] = None):
    """Assemble and compile the deal-evaluation graph.

    `checkpointer` defaults to an in-memory saver rather than to `None`: a graph
    compiled without one cannot pause at `human_review`, and a default that silently
    disables the system's escalation path is the wrong default.
    """
    builder = StateGraph(DealState)

    for name, function in NODE_FUNCTIONS.items():
        builder.add_node(name, function)

    builder.add_edge(START, nodes.PLANNER)

    # Conditional edge 1 — the Planner's pre-flight skip. Extraction is the only step a
    # caller can legally skip (see agents/planner.py); everything after it is a hard
    # data dependency.
    builder.add_conditional_edges(
        nodes.PLANNER,
        route_after_planner,
        _checked_mapping(nodes.EXTRACTOR, nodes.COMPS_RETRIEVAL),
    )

    # The pipeline spine. Static, because decision #9 (Planner topology) established that this ordering is
    # fixed by data dependency and is not something the Planner decides.
    builder.add_edge(nodes.EXTRACTOR, nodes.COMPS_RETRIEVAL)
    builder.add_edge(nodes.COMPS_RETRIEVAL, nodes.VALUATION_RENT)
    builder.add_edge(nodes.VALUATION_RENT, nodes.SCENARIO_FORECAST)
    builder.add_edge(nodes.SCENARIO_FORECAST, nodes.CRITIC)

    # Conditional edge 2 — rework, escalate, or report. The `nodes.PLANNER` target here
    # is the graph's only cycle.
    builder.add_conditional_edges(
        nodes.CRITIC,
        route_after_critic,
        _checked_mapping(nodes.HUMAN_REVIEW, nodes.PLANNER, nodes.SUMMARIZER),
    )

    # A reviewed deal still produces a report — see agents/human_review.py.
    builder.add_edge(nodes.HUMAN_REVIEW, nodes.SUMMARIZER)
    builder.add_edge(nodes.SUMMARIZER, END)

    return builder.compile(
        checkpointer=checkpointer or InMemorySaver(serde=state_serde())
    )
