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
  6. Each of U3's extraction and geography degradation paths reaches the report — added
     when the Extractor became real, since every one of them is a *new* way for a flag
     to be raised and therefore a new way for one to be lost.

**Why these tests make no network calls, and how (U3).** A must-never-fail test should
fail only when the thing it tests is broken. The real Extractor has three outbound
dependencies — an OpenRouter call, the Census geocoder, and a 12 MB county boundary file
— and the real Comps agent needs a built Chroma index and a downloadable embedding
model. Any of those could make this suite red for reasons having nothing to do with flag
propagation, and a test that cries wolf stops being consulted.

So `offline_extractor` below stubs the Extractor's three boundaries for *every* test in
this file, and individual cases override the stubs to force the specific degradation
they are about. This is the §8 split between hermetic tests and live verification: the
real extraction path is exercised against live services by
`scripts/extraction_evidence.py`, where a failure means the service is down and that is
the finding. Note what is *not* stubbed — `extractor_agent` itself, every flag it
constructs, the graph, the reducers, the routers, and the Summarizer. Only the edges
leaving the process are faked.

The one exception is a grounded Los Angeles run that uses the real Chroma corpus and
skips cleanly when the index is absent. Its role is the same one §2 gives the LA row in
the retrieval evidence: a suite where every case is degraded cannot show that the
degradation signals mean anything.
"""

from __future__ import annotations

import operator
from uuid import uuid4

import httpx
import pytest
from langgraph.types import Command
from openai import APIError

import config
import graph as graph_module
import nodes
from agents import critic as critic_module
from agents import extractor as extractor_module
from agents.critic import critic_agent
from agents.extractor import FieldAssumption, ListingExtraction
from agents.planner import route_after_critic
from graph import build_graph
from state import (
    DealState,
    DealStatus,
    DealTerms,
    Flag,
    FlagKind,
    LocationPrecision,
    Severity,
)
from tools.geocoding import GeocodeResult, GeocodeSource
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted

# The listing text is now inert — the stubbed model call decides what comes back, so the
# text is here for readability rather than for parsing. That is a deliberate improvement
# over the U2 fixture, where the tested behaviour depended on a regex happening to miss
# the price and on coordinates happening to be withheld: each flag below is now forced
# on purpose rather than obtained as a side effect.
LISTING_MISSING_PRICE = (
    "For sale: 1234 Sunset Ridge Ave, Los Angeles, CA 90026. Charming 2-unit duplex "
    "in Echo Park, 2 bed / 1 bath, approx 950 sq ft. Price on application."
)

# Complete on address and units, missing a price — so the Extractor raises a real
# `unresolved_field` flag rather than one manufactured for the test.
EXTRACTION_MISSING_PRICE = ListingExtraction(
    unit_count=2,
    bedrooms=2,
    bathrooms=1.0,
    square_footage=950.0,
    full_address="1234 Sunset Ridge Ave, Los Angeles, CA 90026",
    street_address="1234 Sunset Ridge Ave",
    city="Los Angeles",
    state="CA",
    zip_code="90026",
)

LOS_ANGELES = (34.0522, -118.2437)
# Cleveland's demo subject. Retained as its own constant because it is the corpus's
# worst-positioned market — 2% of its rows carry a street address — so it is the point
# that exercises the spatial-concentration disclosure. See Comp.location_precision.
CLEVELAND = (41.4670, -81.7001)


def parcel_at(
    latitude: float,
    longitude: float,
    matched_address: str = "1234 SUNSET RIDGE AVE, LOS ANGELES, CA, 90026",
) -> GeocodeResult:
    """A Census-tier geocode result — the tier that outranks supplied coordinates.

    `matched_address` is parameterised so a non-Los Angeles case does not carry an LA
    address string. It is inert for routing, but a fixture that says one city while
    testing another is the kind of detail that misleads whoever reads a failure next.
    """
    return GeocodeResult(
        latitude=latitude,
        longitude=longitude,
        matched_address=matched_address,
        source=GeocodeSource.CENSUS_GEOCODER,
    )


@pytest.fixture(autouse=True)
def offline_extractor(monkeypatch):
    """Stub the Extractor's three outbound calls for every test in this file.

    Autouse rather than opt-in, so a case added later cannot reach the network by
    forgetting to ask not to. The defaults produce the U2 fixture's shape — a listing
    missing its price, and no resolvable coordinates — which keeps the propagation and
    accumulation tests below testing exactly what they always did: a flag from the first
    node, plus a flag from Comps short-circuiting on missing coordinates, with no Chroma
    query in between.
    """
    monkeypatch.setattr(
        extractor_module,
        "_extract_terms",
        lambda text: (EXTRACTION_MISSING_PRICE.model_copy(deep=True), 1),
    )
    monkeypatch.setattr(extractor_module, "geocode", lambda *args, **kwargs: None)
    # The county lookup reads a 12 MB Census boundary file, downloading it on a cache
    # miss. Stubbed for the same reason as the other two: it is an integration point,
    # and this suite tests flag propagation.
    monkeypatch.setattr(
        extractor_module.county_crosswalk, "lookup_county_fips", lambda lat, lon: None
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


def flags_of_kind(result: dict, kind: FlagKind) -> list[Flag]:
    return [f for f in result["flags"] if f.kind == kind]


def assert_reaches_report(result: dict, kind: FlagKind) -> Flag:
    """The claim this whole file exists to defend, as a reusable assertion."""
    raised = flags_of_kind(result, kind)
    assert raised, f"Expected a {kind} flag; got {sorted({f.kind for f in result['flags']})}."
    for f in raised:
        assert f.detail in result["report_markdown"], (
            f"Flag {kind} was raised but its detail never reached the report. "
            f"This is the flag-loss failure the whole design guards against."
        )
    return raised[0]


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


def test_the_extractor_no_longer_reports_itself_as_a_stub():
    """U3's completion, asserted rather than assumed.

    The build-status disclosure is only informative while it is accurate. An agent that
    kept announcing itself as a stub after being built would erode the one signal a
    reader has for telling an unbuilt section from an empty one.
    """
    result = run_deal()
    assert nodes.EXTRACTOR not in result["stub_nodes"]


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

    Every escalation route is disabled for the duration so none can pre-empt the rework
    path, which is the only thing under test here — each has its own test above. The
    threshold goes to zero, the retrieval node is swapped for a no-op, and the geocode
    resolves cleanly so the Extractor raises no critical flag of its own. Substituting a
    node is what `graph.NODE_FUNCTIONS` exists as a mapping for; `build_graph` reads it
    at call time.
    """
    monkeypatch.setattr(
        critic_module, "_consistency_objections", lambda state: ["injected objection"]
    )
    monkeypatch.setattr(config, "HUMAN_REVIEW_CONFIDENCE_THRESHOLD", 0.0)
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
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
    assert result["status"] == DealStatus.NEEDS_REVIEW
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
    assert resumed["status"] == DealStatus.NEEDS_REVIEW, (
        "A reviewed deal must not be recorded as having cleared on its own."
    )


# --------------------------------------------------------------------------
# 6. U3 — the Extractor's own degradation paths
#
# Each case forces one path and asserts the flag survives to the report. Together they
# are also the coverage U8 will assert against `set(FlagKind)` for this agent, built
# here rather than there because these are propagation claims first.
# --------------------------------------------------------------------------


def test_an_inferred_field_is_disclosed_as_an_assumption(monkeypatch):
    """A value read from a term of art rather than stated must say so.

    This is the flag Checkpoint 2.1 calls "proceed with a flagged assumption": the
    extraction is *better* for resolving "2-flat" into two units, and the report is only
    trustworthy if it distinguishes that from a listing that said "2 units" outright.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True,
        update={
            "price": 525_000.0,
            "assumptions": [
                FieldAssumption(
                    field="unit_count",
                    basis="The listing calls the property a '2-flat', a Chicago term "
                    "for a two-unit building.",
                )
            ],
        },
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))

    result = run_deal()
    raised = assert_reaches_report(result, FlagKind.ASSUMED_FIELD_VALUE)
    assert "2-flat" in raised.detail, (
        "The basis for the inference must reach the reader. An assumption they cannot "
        "evaluate is worth little more than an unflagged one."
    )


def test_retry_exhaustion_escalates_and_writes_no_deal_terms(monkeypatch):
    """The bounded-retry branch of Loop 1.

    Two claims, and the second is the one worth protecting: the failure is disclosed at
    critical severity, and no partial or invented deal terms are written. A schema the
    model never satisfied must not leave a half-built `DealTerms` behind for the
    Valuation agent to price.
    """
    def exhausted(text):
        raise SchemaValidationExhausted(
            attempts=config.MAX_EXTRACTION_RETRIES,
            last_error="price: Input should be a valid number",
            last_raw='{"price": "on application"}',
        )

    monkeypatch.setattr(extractor_module, "_extract_terms", exhausted)

    result = run_deal()
    assert_reaches_report(result, FlagKind.EXTRACTION_RETRY_EXHAUSTED)
    assert result["status"] == DealStatus.NEEDS_REVIEW, (
        "A failed extraction must not report as normal."
    )
    assert result["deal_terms"].price is None
    assert result["deal_terms"].full_address is None
    assert result["extraction_attempts"] == config.MAX_EXTRACTION_RETRIES


def test_an_unreachable_model_is_disclosed_distinctly(monkeypatch):
    """'No model was reached' is a different finding from 'the model kept failing'.

    Asserted as a distinct kind rather than folded into retry exhaustion because the two
    call for different responses from whoever reads the report — one is a service
    outage, the other is a model that cannot handle the listing.
    """
    def unreachable(text):
        raise LlmError("No OpenRouter token found.")

    monkeypatch.setattr(extractor_module, "_extract_terms", unreachable)

    result = run_deal()
    assert_reaches_report(result, FlagKind.EXTRACTION_UNAVAILABLE)
    assert not flags_of_kind(result, FlagKind.EXTRACTION_RETRY_EXHAUSTED)
    assert result["extraction_attempts"] == 0, (
        "No attempt was made against the retry budget, so none should be recorded."
    )


def test_a_transport_failure_becomes_an_error_the_agent_can_flag(monkeypatch):
    """Closes the chain the test above starts from its other end.

    That test asserts the Extractor turns an `LlmError` into a flag. This one asserts
    the client actually *produces* an `LlmError` when the transport fails, rather than
    letting an SDK exception escape — because between them lies the real failure mode:
    a `RateLimitError` is not an `LlmError`, so before this it would have propagated out
    of the node and crashed the graph instead of degrading. Not hypothetical. The free
    tier's daily cap (50 requests, account-wide) was hit during the U3 bake-off, which
    is how the gap was found.
    """
    def rate_limited(**kwargs):
        raise APIError(
            "Rate limit exceeded: free-models-per-day",
            request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
            body=None,
        )

    client = LlmClient(token="not-a-real-key")
    monkeypatch.setattr(client._client.chat.completions, "create", rate_limited)

    with pytest.raises(LlmError):
        client.complete("anything")


def test_missing_coordinates_are_disclosed_as_critical():
    """The default stub's path: nothing resolved, so retrieval cannot run at all."""
    result = run_deal()
    raised = assert_reaches_report(result, FlagKind.GEOCODING_UNAVAILABLE)
    assert raised.severity == Severity.CRITICAL
    assert result["deal_terms"].latitude is None


def test_a_city_centroid_fallback_is_disclosed_as_an_approximation(monkeypatch):
    """The middle geography tier: coordinates exist, but not for this property."""
    centroid = GeocodeResult(
        latitude=LOS_ANGELES[0],
        longitude=LOS_ANGELES[1],
        matched_address="Los Angeles, CA (corpus centroid — city-level approximation)",
        source=GeocodeSource.CITY_CENTROID,
    )
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: centroid)
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    result = run_deal()
    raised = assert_reaches_report(result, FlagKind.COORDINATES_FROM_CITY_CENTROID)
    assert raised.severity == Severity.WARN
    assert result["deal_terms"].latitude == LOS_ANGELES[0]


def test_supplied_coordinates_conflicting_with_the_address_escalate(monkeypatch):
    """The U3 conflict path.

    The system cannot tell whether the caller meant this address or those coordinates,
    so it escalates instead of choosing silently. The address wins for the purpose of
    continuing the run — the report names the address, so retrieval is anchored to the
    same property the reader is being shown — and the discarded coordinates are recorded
    in the flag so a reviewer can see both.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    # Santa Monica: ~13 mi from the geocoded address, well beyond the tolerance.
    supplied = DealTerms(latitude=34.0195, longitude=-118.4912)
    result = run_deal(terms=supplied)

    raised = assert_reaches_report(result, FlagKind.SUPPLIED_COORDINATES_CONFLICT)
    assert raised.severity == Severity.CRITICAL
    assert result["status"] == DealStatus.NEEDS_REVIEW
    assert result["deal_terms"].latitude == LOS_ANGELES[0], (
        "The geocoded address should be what the pipeline carries."
    )
    assert "34.01950" in raised.detail, (
        "The discarded coordinates must be in the flag; a reviewer resolving the "
        "conflict needs both values, not just the one that won."
    )


def test_supplied_coordinates_close_to_the_address_raise_nothing(monkeypatch):
    """The negative case, and the reason the one above means anything.

    A tolerance that fired on every supplied coordinate would be indistinguishable from
    a tolerance of zero — the §2 argument about a signal that is always on, applied to a
    threshold rather than to a search radius.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    # ~0.1 mi away — a parcel-level disagreement, not a different property.
    nearby = DealTerms(latitude=LOS_ANGELES[0] + 0.0015, longitude=LOS_ANGELES[1])
    result = run_deal(terms=nearby)

    assert not flags_of_kind(result, FlagKind.SUPPLIED_COORDINATES_CONFLICT)
    assert not flags_of_kind(result, FlagKind.GEOCODING_UNAVAILABLE)


def test_supplied_coordinates_survive_an_unresolvable_address(monkeypatch):
    """The one branch where no conflict check is possible.

    With the address unresolvable, the supplied point is the best available location and
    is used — but it could not be checked against the address, and the report says so
    rather than presenting it as verified. Uses the autouse stub's `geocode -> None`.
    """
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    supplied = DealTerms(latitude=LOS_ANGELES[0], longitude=LOS_ANGELES[1])
    result = run_deal(terms=supplied)

    raised = assert_reaches_report(result, FlagKind.GEOCODING_UNAVAILABLE)
    assert raised.severity == Severity.WARN, (
        "Coordinates exist, so retrieval can run; this is not the critical no-location "
        "case and should not score as one."
    )
    assert result["deal_terms"].latitude == LOS_ANGELES[0]


# --------------------------------------------------------------------------
# Grounded path — skipped when the Chroma index is absent
# --------------------------------------------------------------------------


def _corpus_available() -> bool:
    try:
        from tools import vector_store

        return vector_store.get_collection().count() > 0
    except Exception as exc:  # noqa: BLE001 - absence of the index is the only thing tested
        # The skip message below asserts one cause ("index not built"), but this catch
        # accepts any — a failed embedding-model download, a Chroma version mismatch.
        # Logging the real reason keeps the skip from quietly misattributing itself.
        from tools import diagnostics

        diagnostics.log_exception(
            "test_flag_propagation: corpus unavailable, skipping the grounded case",
            exc,
        )
        return False


@pytest.mark.skipif(
    not _corpus_available(),
    reason="Chroma index not built; run scripts/build_comps_index.py",
)
def test_grounded_run_reaches_the_report_with_real_comps(monkeypatch):
    """The dense Los Angeles case: retrieval succeeds and the comps reach the report.

    The counterpart to everything above. Those tests prove flags survive; this one
    proves a *clean* run stays clean — no relaxation flag, no geography flag, and real
    comps rendered with their citable source. §2 makes this argument about the evidence
    scripts and it applies here too: a suite where every case is degraded cannot show
    that the degradation signals mean anything.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 1_150_000.0}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))

    result = run_deal()

    assert result["comps"], "Expected comps in a market measured as dense in §2."
    assert not flags_of_kind(result, FlagKind.SPARSE_COMPS)
    assert not flags_of_kind(result, FlagKind.GEOCODING_UNAVAILABLE)
    assert "## Comparable Rentals" in result["report_markdown"]
    assert result["comps"][0].listing_id in result["report_markdown"]

@pytest.mark.skipif(
    not _corpus_available(),
    reason="Chroma index not built; run scripts/build_comps_index.py",
)
def test_a_comp_set_drawn_from_one_place_is_disclosed(monkeypatch):
    """A *full* comp set describing a single location must say so.

    The failure this guards against was live in the build until Aug 22, 2026. 92% of
    the corpus carries no street address and sits on a city-area placeholder
    coordinate, so a comp set can satisfy MIN_QUALIFYING_COMPS while describing one
    point. Cleveland is the case: 8 comps, 8 of them city-area positioned, all at the
    same distance. The count check passes and the concentration check is what fires,
    which is exactly why this is a separate flag from SPARSE_COMPS rather than a
    stricter version of it.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 385_000.0}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(
        extractor_module,
        "geocode",
        lambda *a, **k: parcel_at(*CLEVELAND, matched_address="3200 W 25TH ST, CLEVELAND, OH, 44109"),
    )

    result = run_deal()

    assert not flags_of_kind(result, FlagKind.SPARSE_COMPS), (
        "This case is only meaningful while the comp count itself is adequate — "
        "otherwise it is testing sparsity, which is already covered."
    )
    assert_reaches_report(result, FlagKind.COMPS_SPATIALLY_CONCENTRATED)


@pytest.mark.skipif(
    not _corpus_available(),
    reason="Chroma index not built; run scripts/build_comps_index.py",
)
def test_an_adequately_spread_comp_set_raises_nothing(monkeypatch):
    """The negative case, and the suite does not accept the flag without it.

    §8's standard applied to a threshold: a check that fired on every comp set would be
    indistinguishable from a check with no threshold at all, and would tell a reader
    nothing when it appeared. The Los Angeles subject clears
    COMP_MIN_DISTINCT_LOCATIONS exactly, so this case also pins the boundary — if the
    threshold is ever raised, this test fails rather than the disclosure quietly
    becoming universal.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 1_150_000.0}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))

    result = run_deal()

    assert result["comps"], "Expected comps in a market measured as dense in §2."
    assert not flags_of_kind(result, FlagKind.COMPS_SPATIALLY_CONCENTRATED)


@pytest.mark.skipif(
    not _corpus_available(),
    reason="Chroma index not built; run scripts/build_comps_index.py",
)
def test_comps_carry_their_location_precision_and_vintage(monkeypatch):
    """Every retrieved comp reports how well it is located and when it was listed.

    Both fields landed in the Aug 22, 2026 re-index. `location_precision` is what lets
    the report distinguish eight located comparables from eight city-area points;
    `listed_date` is what lets each comp be normalized against the FMR for its own
    fiscal year rather than one assumed vintage (§2). Asserted on the comps themselves
    rather than through the report, because rendering them is the Summarizer's concern
    while this is the retrieval contract.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 1_150_000.0}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))

    result = run_deal()
    comps = result["comps"]
    assert comps, "Expected comps in a market measured as dense in §2."

    for c in comps:
        assert c.location_precision in {LocationPrecision.ADDRESS, LocationPrecision.AREA}, (
            f"Comp {c.listing_id} carries location_precision={c.location_precision!r}; "
            "an unset value would let a city-area point pass as a located comparable."
        )
        assert c.listed_date is not None, (
            f"Comp {c.listing_id} has no listed_date, so it cannot be normalized "
            "against the FMR for its own fiscal year (§2)."
        )
        assert c.listed_date.year in (2018, 2019), (
            f"Comp {c.listing_id} is dated {c.listed_date.year}; the corpus spans "
            "Dec 2018 - Dec 2019, so anything else means the epoch decode is wrong."
        )
