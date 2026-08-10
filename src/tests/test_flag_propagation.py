"""The one test that must never fail (§8).

Transparent Degradation is this system's central design principle: a flag raised
anywhere must survive every downstream node and appear in the rendered report. A silent
flag loss would invalidate every output the system produces *while leaving it looking
correct*, which is the worst failure shape available — a wrong answer that discloses
nothing about being wrong. §6's cut list protects this file explicitly.

The suite is deliberately structured around the specific ways that guarantee could
break, rather than around the modules that implement it:

  1. A flag raised at the *first* node reaches the *last* one (`operator.add` is doing
     its job across the full pipeline, not just between adjacent nodes).
  2. Flags from *different* agents coexist rather than overwriting each other — the
     precise failure the reducer exists to prevent, and one that only appears once two
     nodes both raise.
  3. The reducer annotation is still on the field. This one guards against a future
     edit rather than against current behaviour, because removing it breaks nothing
     visible until two agents happen to flag on the same run.
  4. The Summarizer renders every flag's full detail text, not a count. §1 requires
     flags be surfaced "prominently, not just bottom-line numbers", and a report saying
     "3 warnings" satisfies propagation while defeating its purpose.
  5. The rework cycle terminates and discloses that it did. An unbounded cycle would
     hang; a bounded one that escalated silently would lose the reason.

**Why these tests avoid the Chroma corpus.** The must-never-fail suite should fail only
when flag propagation is broken. Depending on a built index and a downloadable
embedding model would let it fail for reasons that have nothing to do with what it
tests, and a test that cries wolf stops being consulted. The `no coordinates` path
traverses all eight nodes without touching the vector store, so it exercises the whole
graph on ordinary Python. The grounded path is covered separately below and skips
cleanly when the index is absent.
"""

from __future__ import annotations

import operator
from typing import get_args, get_origin
from uuid import uuid4

import pytest
from langgraph.types import Command

import config
import graph as graph_module
import nodes
from agents import critic as critic_module
from agents.critic import critic_agent
from agents.planner import route_after_critic
from graph import build_graph
from state import DealState, DealTerms, Flag, FlagKind, Severity

# Complete on address and units, missing a price — so the Extractor raises a real
# `unresolved_field` flag rather than one manufactured for the test. Coordinates are
# withheld, so Comps raises a second flag from a second agent without a corpus lookup.
LISTING_MISSING_PRICE = (
    "For sale: 1234 Sunset Ridge Ave, Los Angeles, CA 90026. Charming 2-unit duplex "
    "in Echo Park, 2 bed / 1 bath, approx 950 sq ft. Price on application."
)


def run_deal(listing: str = LISTING_MISSING_PRICE, terms: DealTerms | None = None) -> dict:
    """Invoke the compiled graph once and return its final state."""
    graph = build_graph()
    initial = DealState(raw_listing_text=listing, deal_terms=terms or DealTerms())
    invoke_config = {"configurable": {"thread_id": uuid4().hex}}
    result = graph.invoke(initial, invoke_config)

    # A deal this degraded escalates; resume so the assertions below run against a
    # finished report rather than a paused one.
    if "__interrupt__" in result:
        result = graph.invoke(Command(resume="[test] released"), invoke_config)
    return result


# --------------------------------------------------------------------------
# 1-2. Propagation and accumulation
# --------------------------------------------------------------------------


def test_extractor_flag_reaches_the_rendered_report():
    """A flag raised at the first node appears in the last node's output."""
    result = run_deal()

    extractor_flags = [
        f for f in result["flags"]
        if f.source_agent == nodes.EXTRACTOR and f.kind == FlagKind.UNRESOLVED_FIELD
    ]
    assert extractor_flags, "The Extractor should have flagged the missing price."

    report = result["report_markdown"]
    for f in extractor_flags:
        assert f.detail in report, (
            f"Flag {f.kind} was raised but its detail never reached the report. "
            f"This is the flag-loss failure the whole design guards against."
        )


def test_flags_from_different_agents_accumulate():
    """Two agents flagging on one run must both survive — the reducer's actual job."""
    result = run_deal()
    sources = {f.source_agent for f in result["flags"]}

    assert nodes.EXTRACTOR in sources, "Missing the Extractor's flag."
    assert nodes.COMPS_RETRIEVAL in sources, "Missing the Comps agent's flag."
    assert len(sources) >= 2, (
        f"Only {sources} raised surviving flags. If a later node's flags replaced an "
        f"earlier node's, the reducer on DealState.flags is not being applied."
    )


# --------------------------------------------------------------------------
# 3. The reducer itself
# --------------------------------------------------------------------------


def test_flags_field_still_carries_the_add_reducer():
    """Guards a future edit, not current behaviour.

    Removing `Annotated[..., operator.add]` breaks nothing observable until two agents
    flag on the same run, so the annotation is asserted directly rather than only
    through its effects.
    """
    annotation = DealState.model_fields["flags"].metadata
    assert operator.add in annotation, (
        "DealState.flags lost its operator.add reducer. Without it, any node returning "
        "{'flags': [...]} overwrites everything raised upstream."
    )


def test_clarifying_questions_also_accumulate():
    """The other multi-writer list field. Same failure mode, same guard."""
    annotation = DealState.model_fields["clarifying_questions"].metadata
    assert operator.add in annotation


def test_comps_deliberately_has_no_reducer():
    """`comps` must NOT accumulate — each relaxation pass replaces the working set.

    Asserted because the mistake here is the opposite of the one above: adding a
    reducer to `comps` would pile stale candidates from narrower passes onto the final
    set, and the resulting comp list would look richer than the retrieval actually was.
    """
    assert operator.add not in DealState.model_fields["comps"].metadata


# --------------------------------------------------------------------------
# 4. Rendering
# --------------------------------------------------------------------------


def test_every_flag_is_rendered_in_full_not_counted():
    result = run_deal()
    report = result["report_markdown"]

    assert result["flags"], "Expected this deal to raise flags."
    for f in result["flags"]:
        assert f.detail in report, f"Flag {f.kind} was summarized away, not rendered."
        assert str(f.kind) in report, f"Flag kind {f.kind} is missing from the report."


def test_report_discloses_stubbed_agents():
    """A reader must be able to tell 'unbuilt' from 'nothing to report'."""
    result = run_deal()
    report = result["report_markdown"]

    assert "Provisional build" in report
    assert nodes.VALUATION_RENT in report
    assert result["stub_nodes"], "Stubbed nodes should record themselves in state."


def test_critical_flags_appear_before_the_findings():
    """Disclosure-first ordering (§1: flags surfaced prominently, not as a footnote)."""
    report = run_deal()["report_markdown"]
    assert report.index("## Disclosures") < report.index("## Findings")


# --------------------------------------------------------------------------
# 5. The bounded rework cycle
# --------------------------------------------------------------------------


def test_route_after_critic_escalates_rather_than_looping_forever():
    """The router in isolation: once the budget is spent, rework is no longer offered."""
    base = DealState(raw_listing_text="x", critic_rejected=True)

    assert route_after_critic(base.model_copy(update={"rework_count": 0})) == nodes.PLANNER
    exhausted = base.model_copy(update={"rework_count": config.MAX_REWORKS})
    assert route_after_critic(exhausted) == nodes.HUMAN_REVIEW

    assert route_after_critic(DealState(raw_listing_text="x")) == nodes.SUMMARIZER
    escalate = DealState(raw_listing_text="x", needs_human_review=True)
    assert route_after_critic(escalate) == nodes.HUMAN_REVIEW


def test_rework_cycle_terminates_and_discloses_that_it_did(monkeypatch):
    """Drive the cycle to exhaustion through the real graph.

    The Critic's consistency checks are U7 work and return nothing today, so the
    objection is injected at that one seam — which is why `_consistency_objections`
    exists as a real function rather than being omitted until U7.

    Two escalation routes are disabled for the duration so they cannot pre-empt the
    rework path, which is the only thing under test here — each has its own test above.
    The threshold goes to zero, and the retrieval node is swapped for a no-op so the
    run raises no critical flag. Substituting a node is what `graph.NODE_FUNCTIONS`
    exists as a mapping for; `build_graph` reads it at call time.
    """
    monkeypatch.setattr(
        critic_module, "_consistency_objections", lambda state: ["injected objection"]
    )
    monkeypatch.setattr(config, "HUMAN_REVIEW_CONFIDENCE_THRESHOLD", 0.0)
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    graph = build_graph()
    invoke_config = {"configurable": {"thread_id": uuid4().hex}}
    result = graph.invoke(
        DealState(raw_listing_text=LISTING_MISSING_PRICE), invoke_config
    )

    assert "__interrupt__" in result, (
        "An unresolvable objection should exhaust the rework budget and escalate."
    )
    result = graph.invoke(Command(resume="[test] released"), invoke_config)

    assert result["rework_count"] == config.MAX_REWORKS, (
        f"Expected exactly {config.MAX_REWORKS} rework passes, got "
        f"{result['rework_count']}."
    )
    # Decision #9's stated invariant, asserted rather than read off a trace.
    assert result["planner_invocations"] == 1 + result["rework_count"]

    kinds = {f.kind for f in result["flags"]}
    assert FlagKind.REWORK_LIMIT_REACHED in kinds, (
        "The cycle terminated but did not disclose why. A bound that escalates "
        "silently loses the reason, which is the same failure as dropping a flag."
    )
    assert result["status"] == "needs_review"
    assert "rework_limit_reached" in result["report_markdown"]


def test_planner_invocation_invariant_holds_on_a_clean_run():
    result = run_deal()
    assert result["planner_invocations"] == 1 + result["rework_count"]


# --------------------------------------------------------------------------
# Human review
# --------------------------------------------------------------------------


def test_a_single_critical_flag_escalates_regardless_of_score():
    """Regression test for a defect the U2 demo runs exposed.

    One critical flag costs 0.40, putting confidence at exactly 0.60 — and
    `0.60 < 0.60` is false, so a deal with zero comparables reported as a normal
    result. A report is not entitled to present an estimate as ordinary when the
    system has itself said that estimate should not be relied on.

    Asserted at the boundary deliberately: the arithmetic that produced the defect is
    a property of the *provisional* U7 weights, so this test states the guarantee
    (a critical flag escalates) rather than the numbers that currently satisfy it.
    """
    state = DealState(
        raw_listing_text="x",
        flags=[
            Flag(
                source_agent=nodes.COMPS_RETRIEVAL,
                kind=FlagKind.SPARSE_COMPS,
                detail="no comparables",
                severity=Severity.CRITICAL,
            )
        ],
    )
    update = critic_agent(state)

    assert update["confidence_score"] >= config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD, (
        "This test is only meaningful while a lone critical flag still scores at or "
        "above the threshold. If the U7 weights changed, re-derive the case."
    )
    assert update["needs_human_review"] is True


def test_human_review_pauses_and_surfaces_the_grounds_for_escalation():
    graph = build_graph()
    invoke_config = {"configurable": {"thread_id": uuid4().hex}}
    result = graph.invoke(
        DealState(raw_listing_text=LISTING_MISSING_PRICE), invoke_config
    )

    assert "__interrupt__" in result, "A zero-comp deal should escalate, not report."
    payload = result["__interrupt__"][0].value
    assert payload["flags"], "The reviewer was shown no reason for the escalation."
    assert all(
        f["severity"] in (Severity.WARN, Severity.CRITICAL) for f in payload["flags"]
    )

    resumed = graph.invoke(Command(resume="[test] reviewer note"), invoke_config)
    assert resumed["human_review_note"] == "[test] reviewer note"
    assert "[test] reviewer note" in resumed["report_markdown"]
    assert resumed["status"] == "needs_review", (
        "A reviewed deal must not be recorded as having cleared on its own."
    )


# --------------------------------------------------------------------------
# Grounded path — skipped when the Chroma index is absent
# --------------------------------------------------------------------------


def _corpus_available() -> bool:
    try:
        from tools import vector_store

        return vector_store.get_collection().count() > 0
    except Exception:  # noqa: BLE001 - absence of the index is the only thing tested
        return False


@pytest.mark.skipif(
    not _corpus_available(),
    reason="Chroma index not built; run scripts/build_comps_index.py",
)
def test_grounded_run_reaches_the_report_with_real_comps():
    """The dense Los Angeles case: retrieval succeeds and the comps reach the report.

    The counterpart to everything above. Those tests prove flags survive; this one
    proves a *clean* run stays clean — no relaxation flag, and real comps rendered with
    their citable source. §2 makes this argument about the evidence scripts and it
    applies here too: a suite where every case is degraded cannot show that the
    degradation signals mean anything.
    """
    terms = DealTerms(latitude=34.0522, longitude=-118.2437)
    listing = (
        "For sale: 1234 Sunset Ridge Ave, Los Angeles, CA 90026. 2-unit duplex, "
        "2 bed / 1 bath, approx 950 sq ft. Asking $1,150,000."
    )
    result = run_deal(listing, terms)

    assert result["comps"], "Expected comps in a market measured as dense in §2."
    assert not [f for f in result["flags"] if f.kind == FlagKind.SPARSE_COMPS]
    assert "## Comparable Rentals" in result["report_markdown"]
    assert result["comps"][0].listing_id in result["report_markdown"]
