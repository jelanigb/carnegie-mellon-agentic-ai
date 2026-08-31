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
  7. The Critic's *own* flags reach the report (U7). Every case above raises its flag
     upstream of the Critic, so all of them would still pass if nothing the Critic
     itself raised ever survived — and until U7.4 that was literally true of
     escalation, where `has_critical` read only the inherited list and a CRITICAL the
     Critic raised set no route. A flag raised by the last node before the Summarizer
     travels the shortest path in the system, which is exactly why it is the one nobody
     checks.

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
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pandas as pd
import pytest
from langgraph.types import Command
from openai import APIError

import config
import graph as graph_module
import nodes
from agents import critic as critic_module
from agents import extractor as extractor_module
from agents import scenario_forecast as scenario_module
from agents import valuation_rent as valuation_module
from agents.critic import Objection, critic_agent
from agents.extractor import FieldAssumption, ListingExtraction
from agents.planner import planner_agent, route_after_critic
from agents.summarizer import summarizer_agent
from graph import build_graph
from state import (
    DealState,
    DealStatus,
    DealTerms,
    Flag,
    FlagKind,
    LocationPrecision,
    RentEstimateSource,
    Severity,
    ValuationDetail,
    flag,
)
from tools import hud_fmr, zcta_crosswalk, zori
from tools.geocoding import GeocodeResult, GeocodeSource
from tools.llm_client import LlmError
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted
from tools.model import rent_model

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
# Logan Square, the Chicago demo subject's neighborhood. Its own constant for the same
# reason CLEVELAND has one: it is the market where the corpus is dense enough to return
# a full comp set but not dense enough to return a *similar* one, which is the case the
# comp-drift disclosure exists for. Same coordinates as subject B in
# `scripts/retrieval_evidence.py`, so the hermetic case and the live evidence run are
# measuring the same point.
CHICAGO = (41.9227, -87.6982)
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


@pytest.fixture(autouse=True)
def offline_scenario_evaluator(monkeypatch):
    """Keep U6's Tree-of-Thought evaluator off the network, for every test here.

    Same reasoning as `offline_extractor` above, and the same autouse posture so a case
    added later cannot reach out by forgetting to opt in. The Scenario agent scores each
    level with a model call; left live, this suite would make several per test, take
    minutes, and go red whenever OpenRouter did — which is exactly the failure mode that
    teaches a reader to stop trusting a must-never-fail suite.

    Forcing the constructor to raise routes the agent down its documented fallback: a
    deterministic scorer over the measured negative correlation between rent and price
    growth. That path is worth exercising on its own account, since it is what a real run
    degrades to when the model is unreachable. The evaluator's live behaviour belongs to
    `scripts/forecast_evidence.py`, which runs it against real services.
    """

    def _refuse(*args, **kwargs):
        raise LlmError("LLM disabled for the hermetic suite")

    monkeypatch.setattr(scenario_module, "LlmClient", _refuse)


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


def priced_cleanly(monkeypatch) -> None:
    """Make the Extractor raise nothing at all, so the case owns its own flag list.

    The autouse fixture withholds the price on purpose — most cases here want a real
    upstream flag to follow through the pipeline. The U7 interaction cases want the
    opposite: their whole subject is the confidence score, and an extra warn from the
    Extractor moves a deliberately-two-warn deal to three and escalates it on the score
    before the rule under test is reached. Found by measuring, not by reading: the case
    below first ran at 0.55 rather than 0.70.
    """
    priced = EXTRACTION_MISSING_PRICE.model_copy(deep=True, update={"price": 1_150_000.0})
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (priced, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))


# LA County: state FIPS 06 + county FIPS 037 + HUD's "99999" county placeholder. The
# real entityid rather than a made-up one, so a fixture that leaks into a log or an
# error message names a county that actually exists.
LOS_ANGELES_COUNTY = "0603799999"

# The market-rent level the stubbed ZORI panel reports for the current month. Set equal
# to the fake county 2BR schedule so the composed anchor — market level times the
# schedule's bedroom step — comes out at exactly that figure for a two-bedroom subject,
# which is what the pre-U11.3 anchor was. Cases that assert on the anchor's magnitude
# therefore keep asserting the same number, and the ones that care about the *tier* still
# exercise the ZIP-versus-county branch.
FAKE_ZORI_LEVEL = 2_903.0

# The same index at the corpus's 2018-19 vintage — the fake 2019 county 2BR schedule
# times the 1.186 ZORI-to-FMR ratio U8.0 measured for that year, so the synthetic market
# read sits above the 40th-percentile schedule the way a real one does. A comp listed
# then normalizes against this; the subject's estimate is anchored to the current level
# above. Today's level cancels out of `divergence_pct`, so this constant alone decides
# how far the cross-check sees the model and the comps apart.
FAKE_ZORI_VINTAGE = 1_791.0 * 1.186


class FakeFmrClient:
    """A HUD client that answers from fixed schedules instead of over the network.

    U5 gave this suite its first agent that *must* reach an external API to do its job at
    all, which is a new problem for a file whose whole premise is that it fails only when
    flag propagation is broken. Stubbed for the same reason as the Extractor's three
    boundaries: a HUD outage turning the must-never-fail suite red would teach a reader
    to stop trusting it. `scripts/pull_fmr_sample.py` exercises the real client, and
    `scripts/valuation_evidence.py` runs the whole agent against it.

    **The numbers are real Los Angeles County schedules, not invented ones**, pulled from
    HUD for entityid 0603799999 and pasted here. That matters more than it looks: the
    gap between the 2019 and 2026 columns *is* the vintage correction the Observe step
    exists to apply, so a flat synthetic schedule would let every comp normalize to
    itself and the cross-check would test nothing. With these, a hermetic run reproduces
    the live evidence run's figures to the dollar.

    What is deliberately *not* faked is `hud_fmr.bedroom_field`. The four-bedroom cap is
    the thing under test in one case below, so the real implementation is called.
    """

    # ZIP 90026 (Echo Park) as published for FY2026, alongside the county-wide figures.
    # One ZIP is enough: the point is that the pipeline resolves a ZIP and anchors on it,
    # not that a fake reproduces all 474 of them. `zip_table_enabled=False` turns this off
    # to exercise the non-SAFMR county path, which is a real case — Richmond County
    # (Staten Island) has no Small Area FMR.
    ZIP_SCHEDULES = {
        "90026": {"Efficiency": 2064, "One-Bedroom": 2309, "Two-Bedroom": 2880,
                  "Three-Bedroom": 3652, "Four-Bedroom": 4066},
    }

    # HUD FMR, Los Angeles County (entityid 0603799999), fiscal years as published.
    SCHEDULES = {
        2019: {"Efficiency": 1158, "One-Bedroom": 1384, "Two-Bedroom": 1791,
               "Three-Bedroom": 2401, "Four-Bedroom": 2641},
        2020: {"Efficiency": 1279, "One-Bedroom": 1517, "Two-Bedroom": 1956,
               "Three-Bedroom": 2614, "Four-Bedroom": 2857},
        2026: {"Efficiency": 2079, "One-Bedroom": 2328, "Two-Bedroom": 2903,
               "Three-Bedroom": 3681, "Four-Bedroom": 4098},
    }
    CURRENT_YEAR = 2026

    def __init__(self, scale: float = 1.0, zip_table_enabled: bool = True):
        # `scale` multiplies every figure, so a case that needs the estimate pushed away
        # from the comps can move the anchor without inventing a second schedule.
        self.scale = scale
        self.zip_table_enabled = zip_table_enabled

    def get_fmr_zip_table(self, entityid, year=None):
        if not self.zip_table_enabled:
            return {}
        return {
            z: {k: v * self.scale for k, v in rents.items()}
            for z, rents in self.ZIP_SCHEDULES.items()
        }

    def _schedule(self, year) -> dict:
        table = self.SCHEDULES.get(year or self.CURRENT_YEAR, self.SCHEDULES[self.CURRENT_YEAR])
        return {k: v * self.scale for k, v in table.items()}

    def get_fmr(self, entityid, year=None, zip_code=None):
        return SimpleNamespace(
            entityid=entityid,
            year=year or self.CURRENT_YEAR,
            # `area_name` is read by tools/fmr_history when it builds the rent-growth
            # series; the real client always returns one.
            area_name="Los Angeles-Long Beach-Glendale, CA HUD Metro FMR Area",
            is_safmr=self.zip_table_enabled,
            rents=self._schedule(year),
        )

    def get_fmr_for_bedroom(self, entityid, bedrooms, year=None, zip_code=None):
        field_name, capped = hud_fmr.bedroom_field(bedrooms)
        zip_rents = self.get_fmr_zip_table(entityid, year=year).get(zip_code or "")
        used_msa_fallback = zip_rents is None
        rents = zip_rents or self._schedule(year)
        return {
            "rent": rents[field_name],
            "bedrooms_requested": bedrooms,
            "bedrooms_used": min(max(bedrooms, 0), 4),
            "bedroom_cap_exceeded": capped,
            "year": year or self.CURRENT_YEAR,
            "is_safmr": self.zip_table_enabled,
            "used_msa_fallback": used_msa_fallback,
        }


def offline_valuation(
    monkeypatch,
    county: str = LOS_ANGELES_COUNTY,
    scale: float = 1.0,
    zip_table_enabled: bool = True,
    zcta: str | None = "90026",
    zip_trained: bool = True,
    zori_covers_zip: bool = True,
):
    """Give the Valuation agent a county and an FMR schedule without leaving the process.

    Overrides the autouse fixture's `lookup_county_fips` stub, which returns `None` — the
    default this file wants, since most cases here are about degradation, but the one
    thing that makes a rent estimate impossible. Patching the module attribute covers
    both callers at once: `agents/extractor.py` resolves the *subject's* county and
    `tools/model/rent_model.py` resolves each *comp's*, and both hold a reference to the
    same `tools.county_crosswalk` module object. Same for `hud_fmr`.
    """
    client = FakeFmrClient(scale=scale, zip_table_enabled=zip_table_enabled)
    monkeypatch.setattr(
        extractor_module.county_crosswalk, "lookup_county_fips", lambda lat, lon: county
    )
    monkeypatch.setattr(hud_fmr, "HudFmrClient", lambda *a, **k: client)
    # The ZCTA join reads a 67 MB Census boundary file. Stubbed for the same reason as
    # the county one: it is an integration point, and this suite tests flag propagation.
    monkeypatch.setattr(zcta_crosswalk, "lookup_zcta", lambda lat, lon: zcta)
    monkeypatch.setattr(
        zcta_crosswalk, "zctas_for_points",
        lambda lats, lons: [zcta] * len(lats),
    )

    # Pin the ZIP-anchor gate rather than inheriting it from whichever counties the
    # artifact on disk happened to train at ZIP resolution. The agent only anchors at ZIP
    # for a county the model was *fit* on at ZIP resolution — a real and load-bearing
    # contract, since SAFMR coverage expanded after 2020 — but which counties those are
    # is a property of a retrain, and a test that moved with it would be asserting on
    # something other than the behaviour it names.
    bundle = rent_model.load()
    if bundle is not None:
        gated = dict(bundle)
        report = dict(gated.get("report") or {})
        report["zip_anchored_counties"] = [county] if zip_trained else []
        gated["report"] = report
        monkeypatch.setattr(valuation_module.rent_model, "load", lambda: gated)

    # **The anchor reads the ZORI panel on every estimate since U11.3**, which is a
    # re-fetchable ~10 MB data file rather than a service. Stubbed here for the same
    # reason the FMR client is: left live, a machine without the file would flip outcomes
    # in tests that never mention the anchor, and `tests/` is meant to be hermetic.
    # `scripts/anchor_probe.py` and the evidence scripts exercise the real series.
    #
    # `zori_covers_zip=False` drives the county-tier path, which is the fallback a ZIP
    # whose series has not begun takes.
    months = [
        str(m.date()) for m in pd.date_range("2018-01-31", "2026-07-31", freq="ME")
    ]
    # Flat across the vintage, then a step to today's level. A flat *history* is what
    # makes the fixture readable: every comp normalizes against the same 2018-19 figure
    # whatever month it was listed in, so the cross-check below measures the model
    # against the comps rather than against calendar noise the fake invented.
    levels = {m: (FAKE_ZORI_VINTAGE if m < "2026-01-01" else FAKE_ZORI_LEVEL) * scale
              for m in months}
    covered_zip = (zcta or "90026") if zori_covers_zip else "99999"
    panel = pd.DataFrame([{
        "RegionName": covered_zip, "State": "CA",
        "CountyName": "Los Angeles County", "zip": covered_zip,
        **levels,
    }])
    medians = pd.DataFrame([levels], index=pd.Index([county[:5]], name="geoid"))
    counts = pd.DataFrame([{m: 12 for m in months}],
                          index=pd.Index([county[:5]], name="geoid"))
    monkeypatch.setattr(zori, "panel", lambda: panel)
    monkeypatch.setattr(zori, "county_median_tables", lambda: (medians, counts))
    return client


def _rent_model_available() -> bool:
    """Whether a trained model is on disk. Same posture as `_corpus_available`: a
    machine that has never run `scripts/train_rent_model.py` should skip these cases
    rather than fail them, since the absence is a setup state and not a defect.
    """
    return rent_model.load() is not None


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


def test_the_build_status_banner_still_renders_when_a_node_is_stubbed():
    """A reader must be able to tell 'unbuilt' from 'nothing to report'.

    **Rewritten Aug 30, 2026 (U8.6d), and the rewrite is the interesting part.** This
    asserted `"Provisional build" in report` on an ordinary run, which passed for four
    units because `agents/critic.py` had never stopped declaring itself a stub — so the
    test was asserting a defect. Its companion assertion, `nodes.VALUATION_RENT in
    report`, was satisfied by the string appearing in a flag's `raised by:` line rather
    than in the banner at all.

    Every agent is built now, so the mechanism has nothing to report on an ordinary run.
    It is still load-bearing for anything stubbed later, so it is exercised directly
    against a state that declares one, rather than being deleted along with the defect
    that was keeping it green.
    """
    state = DealState(raw_listing_text="[stub banner]", stub_nodes=["some_future_agent"])
    report = summarizer_agent(state)["report_markdown"]

    assert "Provisional build" in report
    assert "some_future_agent" in report


def test_no_agent_still_reports_itself_as_a_stub():
    """The other half, and the reason the test above could sit wrong for four units.

    `test_the_extractor_no_longer_reports_itself_as_a_stub` below checks one agent by
    name, which is why the Critic's stale declaration survived U7's completion of it.
    This checks the set, so the next agent to finish cannot leave the claim behind.
    """
    result = run_deal()
    assert result["stub_nodes"] == [], (
        f"{result['stub_nodes']} still declare themselves unbuilt. Every agent is "
        f"built; a stale declaration tells every reader the report is provisional."
    )


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


def test_confidence_does_not_decay_across_rework_laps():
    """The cycle must be bounded by its counter, not by the score collapsing.

    `state.flags` is append-only across laps on purpose, and a rework re-runs every
    upstream agent, so each re-raises what it raised before. Summed naively, a deal
    carrying two warn flags scored 0.70, then 0.40 on the first lap and 0.10 on the
    second — escalating on collapsed confidence before `MAX_REWORKS` was reached, which
    made `REWORK_LIMIT_REACHED` unreachable. The cycle was still bounded, but by an
    arithmetic accident rather than by the explicit counter §3 requires, and the two
    agreeing is what would have kept it hidden.

    A deal does not get worse because the pipeline looked at it twice.
    """
    accumulated = []
    scores = []
    for _ in range(3):
        accumulated += [
            flag("upstream", FlagKind.RENT_DIVERGES_FROM_COMPS, "same text", Severity.WARN, 1),
            flag("upstream", FlagKind.GEOCODER_SERVICE_UNAVAILABLE, "same text", Severity.WARN, 1),
        ]
        scores.append(
            critic_agent(DealState(raw_listing_text="x", flags=list(accumulated)))[
                "confidence_score"
            ]
        )
    assert scores == [0.70, 0.70, 0.70], scores


def test_distinct_observations_of_one_kind_are_each_charged():
    """The de-duplication must not over-reach.

    One retrieval pass can raise `RELAXED_MATCH_CRITERIA` twice — it drops the
    square-footage band first and loosens bedroom tolerance later — and those are two
    real concessions, not one reported twice. De-duplicating on kind alone would charge
    for one and silently forgive the other.
    """
    two_relaxations = [
        flag("comps_retrieval", FlagKind.RELAXED_MATCH_CRITERIA, "dropped sqft band", Severity.WARN, 1),
        flag("comps_retrieval", FlagKind.RELAXED_MATCH_CRITERIA, "loosened bedrooms", Severity.WARN, 1),
    ]
    result = critic_agent(DealState(raw_listing_text="x", flags=two_relaxations))
    assert result["confidence_score"] == 0.70


def test_rework_cycle_terminates_and_discloses_that_it_did(monkeypatch):
    """Drive the cycle to exhaustion through the real graph.

    The Critic's consistency checks are U7 work and return nothing today, so the
    objection is injected at that one seam — which is why `_consistency_objections`
    exists as a real function rather than being omitted until U7.

    Every escalation route is disabled for the duration so none can pre-empt the rework
    path, which is the only thing under test here — each has its own test above. The
    threshold goes to zero, the geocode resolves cleanly so the Extractor raises no
    critical flag of its own, and the retrieval and valuation nodes are swapped for
    no-ops. Substituting a node is what `graph.NODE_FUNCTIONS` exists as a mapping for;
    `build_graph` reads it at call time.

    **Valuation joined that list in U5, and the reason is worth recording.** Under this
    file's autouse stubs the subject resolves to no county, so the real agent raises a
    critical `rent_anchor_unavailable` — which escalates immediately and leaves this
    test measuring zero rework passes instead of two. That is the agent behaving
    correctly and the test asking about something else. Stubbing it out is the same move
    already made for retrieval, for the same reason, rather than a symptom worked around.

    **Scenario joined in U6 for exactly the same reason, which is what makes the pattern
    worth naming.** With no county there is no FMR history to difference, and with
    Valuation stubbed there is no resolved metro, so the forecast has neither side and
    raises a critical `forecast_unavailable`. Three agents have now pre-empted this test
    by correctly reporting a degradation, so the rule is general: a test that isolates
    one route has to silence every *other* route that can escalate, and the list grows as
    the pipeline learns to disclose more.

    **The injected objection gained `retryable=True` in U7.4**, and the change is
    deliberate rather than mechanical. `critic_rejected` stopped meaning "an objection
    exists" and started meaning "another pass could fix this", because a rework re-runs
    the whole pipeline and most objections a second pass cannot change — a thin market
    stays thin. A non-retryable objection now escalates instead of looping, so injecting
    one here would test the escalation route this test exists to exclude. The guarantee
    under test is unchanged: the cycle is bounded and says so when it ends.
    """
    monkeypatch.setattr(
        critic_module,
        "_consistency_objections",
        lambda state: [
            Objection("injected objection", Severity.WARN, retryable=True)
        ],
    )
    monkeypatch.setattr(config, "HUMAN_REVIEW_CONFIDENCE_THRESHOLD", 0.0)
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.VALUATION_RENT, lambda state: {}
    )
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.SCENARIO_FORECAST, lambda state: {}
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

    # Through `assert_reaches_report` rather than a substring check on the kind (U7.8):
    # the kind is a label the Summarizer prints from the enum, while the *detail* is the
    # only place the reader learns how many passes were spent and that the loop stopped
    # deliberately. A report that names the kind and drops the sentence would satisfy
    # propagation while losing the reason, which is the failure this case is about.
    raised = assert_reaches_report(result, FlagKind.REWORK_LIMIT_REACHED)
    assert raised.severity == Severity.WARN
    assert str(config.MAX_REWORKS) in raised.detail, (
        "The disclosure should say how much budget was spent, not merely that some was."
    )
    assert result["status"] == DealStatus.NEEDS_REVIEW
    assert "rework_limit_reached" in result["report_markdown"]


def test_a_downed_geocoder_makes_a_rework_re_plan_extraction():
    """The rework path only means something if the step that could change the answer runs.

    `REQUIRED_DEAL_FIELDS` holds no coordinate, so a deal whose address, price and unit
    count were extracted on pass one is "complete" forever after. Before U7.4b that
    skipped extraction on every rework lap — so the one objection the Critic marks
    retryable, justified as re-attempting a Census call, re-attempted nothing and burned
    the budget arriving back with the same objection.
    """
    settled = DealTerms(
        full_address="123 Real St, Los Angeles, CA",
        price=1_049_000,
        unit_count=2,
        latitude=LOS_ANGELES[0],
        longitude=LOS_ANGELES[1],
    )
    state = DealState(
        raw_listing_text="x",
        deal_terms=settled,
        planner_invocations=1,
        flags=[flag("extractor", FlagKind.GEOCODER_SERVICE_UNAVAILABLE, "down", Severity.WARN, 1)],
    )
    assert nodes.EXTRACTOR in planner_agent(state)["plan"]


def test_an_unresolvable_address_does_not_re_plan_extraction():
    """The other half of the U7.1b split, and the reason it was worth splitting.

    An address with no street number resolves no better on the fifth attempt than on the
    first, so re-planning extraction for it would spend the rework budget on a certainty.
    """
    settled = DealTerms(
        full_address="Echo Park, Los Angeles, CA",
        price=1_049_000,
        unit_count=2,
        latitude=LOS_ANGELES[0],
        longitude=LOS_ANGELES[1],
    )
    state = DealState(
        raw_listing_text="x",
        deal_terms=settled,
        planner_invocations=1,
        flags=[flag("extractor", FlagKind.COORDINATES_FROM_CITY_CENTROID, "centroid", Severity.WARN, 1)],
    )
    assert nodes.EXTRACTOR not in planner_agent(state)["plan"]


def test_a_geocoder_outage_two_laps_ago_no_longer_re_plans_extraction():
    """U8.5/OQ-15's fix to `_geocode_is_worth_retrying`, asserted directly.

    Before U8.5 this read the *accumulated* flags, so a `GEOCODER_SERVICE_UNAVAILABLE`
    from a pass that already retried and moved on would still trigger another re-plan on
    every later lap. Pass 1's outage is stale by the time pass 2 has already completed —
    the flag is stamped `planner_invocations=1` while `state.planner_invocations=2`,
    i.e. two passes have run since — so this must not re-plan extraction a third time.
    """
    settled = DealTerms(
        full_address="123 Real St, Los Angeles, CA",
        price=1_049_000,
        unit_count=2,
        latitude=LOS_ANGELES[0],
        longitude=LOS_ANGELES[1],
    )
    state = DealState(
        raw_listing_text="x",
        deal_terms=settled,
        planner_invocations=2,
        flags=[
            flag(
                "extractor", FlagKind.GEOCODER_SERVICE_UNAVAILABLE, "stale outage", Severity.WARN, 1
            )
        ],
    )
    assert nodes.EXTRACTOR not in planner_agent(state)["plan"]


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


def test_an_unreachable_geocoder_is_disclosed_as_distinct_from_a_bad_address(monkeypatch):
    """Same centroid coordinate as the test above, different cause, different flag.

    The distinction is load-bearing rather than cosmetic: this is the one degradation in
    the system a rework pass can actually fix, because re-running the Extractor
    re-attempts the call. An address with no street number will never resolve no matter
    how often it is retried. The Critic routes on the flag kind, so the two cannot be
    allowed to arrive as one.
    """
    centroid = GeocodeResult(
        latitude=LOS_ANGELES[0],
        longitude=LOS_ANGELES[1],
        matched_address="Los Angeles, CA (corpus centroid — city-level approximation)",
        source=GeocodeSource.CITY_CENTROID,
        primary_unavailable=True,
    )
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: centroid)
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS, nodes.COMPS_RETRIEVAL, lambda state: {"comps": []}
    )

    result = run_deal()
    raised = assert_reaches_report(result, FlagKind.GEOCODER_SERVICE_UNAVAILABLE)
    assert raised.severity == Severity.WARN
    assert result["deal_terms"].latitude == LOS_ANGELES[0]
    # The address-side flag must NOT also fire — one cause, one disclosure.
    assert not any(
        f.kind == FlagKind.COORDINATES_FROM_CITY_CENTROID for f in result["flags"]
    )


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

    **Extended in U5 to keep meaning what it says.** Without a county the real Valuation
    agent raises a critical flag, so this case would have quietly become another degraded
    one — still passing its own assertions while no longer demonstrating the thing it
    exists to demonstrate. `offline_valuation` gives it a county and an FMR schedule, so
    the run now produces an actual rent figure and the "clean" claim is true end to end.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 1_150_000.0}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    assert result["comps"], "Expected comps in a market measured as dense in §2."
    assert not flags_of_kind(result, FlagKind.SPARSE_COMPS)
    assert not flags_of_kind(result, FlagKind.GEOCODING_UNAVAILABLE)
    assert not flags_of_kind(result, FlagKind.RENT_ANCHOR_UNAVAILABLE)
    assert not flags_of_kind(result, FlagKind.RENT_ESTIMATE_UNAVAILABLE)
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
def test_comps_admitted_by_a_relaxed_search_are_disclosed(monkeypatch):
    """A comp set that came back *unlike* the subject must say so (U7.3).

    Chicago is the case, and it is a real one rather than a constructed one: the corpus
    is dense enough there to return a full eight comps but not dense enough to return
    eight similar ones, so the retrieval loop drops the square-footage band and the set
    that comes back spans 510 to 2,000 sq ft against a 950 sq ft subject.

    Distinct from `RELAXED_MATCH_CRITERIA`, which is also raised on this run and records
    only the *concession*. Relaxing a filter permits dissimilar comps without producing
    them; this flag is the measured consequence, and it is the one the Critic's I1
    interaction keys on. Asserting both here pins that distinction end to end — if the
    drift check were ever collapsed back into the relaxation flag, this case goes red.

    No county is stubbed, so no rent figure is produced and the deal escalates on that
    ground. That is deliberate: this case is about a retrieval flag surviving to the
    report, and giving it Los Angeles FMR schedules to reach a rent estimate would put a
    fixture from one county on a subject in another.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True,
        update={
            "price": 499_000.0,
            "full_address": "2500 N Kedzie Blvd, Chicago, IL 60647",
            "street_address": "2500 N Kedzie Blvd",
            "city": "Chicago",
            "state": "IL",
            "zip_code": "60647",
        },
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(
        extractor_module,
        "geocode",
        lambda *a, **k: parcel_at(*CHICAGO, matched_address="2500 N KEDZIE BLVD, CHICAGO, IL, 60647"),
    )

    result = run_deal()

    assert not flags_of_kind(result, FlagKind.SPARSE_COMPS), (
        "This case is only meaningful while the comp count itself is adequate — "
        "a thin set is already covered by the sparsity disclosure."
    )
    raised = assert_reaches_report(result, FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA)
    assert raised.severity == Severity.WARN
    assert flags_of_kind(result, FlagKind.RELAXED_MATCH_CRITERIA), (
        "The concession and its consequence are separate observations, and this case "
        "exists partly to hold them apart."
    )


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


# --------------------------------------------------------------------------
# 7. Valuation (U5) — every path that produces a rent figure, and every one that
#    refuses to. Added when the Valuation agent became real: each is a new way for a
#    flag to be raised and therefore a new way for one to be lost.
# --------------------------------------------------------------------------


def test_no_county_means_no_rent_figure_at_all():
    """The invariant §2 exists to protect, asserted at the place it could break.

    A subject with no county has no FMR to anchor against. The tempting behaviour is to
    average the retrieved comps instead and report that — a plausible-looking figure in
    one line. It would also be a 2019 dollar amount printed in a 2026 report with
    nothing marking it as one, which is the exact failure the whole rent-anchoring
    design exists to prevent. So the assertion is two-sided: the flag must reach the
    report *and* no rent figure may appear beside it.
    """
    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_ANCHOR_UNAVAILABLE)
    assert raised.severity == Severity.CRITICAL, (
        "This flag means there is no rent estimate at all, not that one is imprecise. "
        "A warn here would understate a missing headline number to the Critic as much "
        "as to a reader."
    )
    assert result.get("rent_estimate") is None
    assert result.get("rent_estimate_ratio_to_anchor") is None
    assert result.get("rent_anchor_used") is None
    assert "not produced" in result["report_markdown"]


def test_the_valuation_agent_no_longer_reports_itself_as_a_stub():
    """U5's completion, expressed as a property of the output rather than of the diff.

    The report's provisional-build banner names every node that ran as a placeholder.
    While the Valuation agent was a stub it appeared there, and a reader was told the
    rent section was unbuilt rather than empty. That claim is now false, and a test that
    pins it is what stops the banner from outliving the stub.
    """
    result = run_deal()
    assert nodes.VALUATION_RENT not in result["stub_nodes"]


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_a_rent_estimate_discloses_the_anchor_it_was_built_from(monkeypatch):
    """An estimate on the model path must show its working, not just its result.

    `rent_anchored_to_market_index` is `INFO` and fires on every single estimate, which usually
    makes a signal worthless — §2's own argument against always-on flags. It earns its
    place by carrying content rather than existing as a marker: the ratio, the FMR, and
    the fiscal year are all in the detail text, so a reader can multiply the two numbers
    themselves and see that this is a modelled figure rather than an observed rent.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    assert result.get("rent_estimate") is not None
    assert result.get("rent_estimate_source") == RentEstimateSource.REGRESSION_MODEL
    # The anchoring arithmetic itself, asserted rather than assumed: since U11.3 the
    # estimate is the ratio times the composed anchor and nothing else, so a correction
    # applied on the way out without being disclosed would show up here.
    assert result["valuation_detail"].anchor_index_month is not None, (
        "The anchor's own vintage is carried whether or not it is stale enough to flag."
    )
    assert result.get("rent_estimate") == pytest.approx(
        result.get("rent_estimate_ratio_to_anchor") * result.get("rent_anchor_used")
    )
    # The ZIP's own market level, not the county median — the two are different
    # denominators, and a subject whose ZIP the index covers must be anchored to it.
    # The bedroom step is 1.0 here because the subject is a two-bedroom and two bedrooms
    # is the reference the shape divides by, so the composed anchor is the level itself.
    assert result.get("rent_anchor_used") == pytest.approx(FAKE_ZORI_LEVEL)
    assert result["valuation_detail"].anchor_tier == "zip"
    assert result["valuation_detail"].anchor_zip == "90026"
    assert not flags_of_kind(result, FlagKind.RENT_ANCHOR_COUNTY_LEVEL)

    raised = assert_reaches_report(result, FlagKind.RENT_ANCHORED_TO_MARKET_INDEX)
    assert raised.severity == Severity.INFO
    # The disclosure names the month the market index was read at, not a fiscal
    # year: since U11.3 the level comes from a monthly series, and "FY2026" would
    # describe only the bedroom step.
    assert "2026-07-31" in raised.detail
    assert "90026" in raised.detail

    detail = result.get("valuation_detail")
    assert detail.model_mae_dollars > 0, (
        "The report prints an error band beside the estimate; without the persisted "
        "training metrics it would print a point estimate reading as exact."
    )
    assert f"{detail.model_mae_dollars:,.0f}" in result["report_markdown"]


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_a_five_bedroom_subject_discloses_the_hud_bedroom_cap(monkeypatch):
    """HUD publishes nothing above four bedrooms, and the report has to say so.

    The approximation is small and entirely invisible in the output — a five-bedroom
    unit priced off the four-bedroom schedule produces a perfectly ordinary-looking
    number. That is exactly the kind of silent degradation the flag vocabulary exists
    for, which is why `hud_fmr.bedroom_field` returns the cap alongside the field
    instead of applying it quietly.
    """
    # Sized like a real five-bedroom unit rather than by bumping the bedroom count on a
    # 950 sqft duplex. That shortcut was tried first and the agent refused the estimate,
    # correctly — see the out-of-bounds case below, which now pins that behaviour.
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True,
        update={
            "price": 1_150_000.0,
            "bedrooms": 5,
            "bathrooms": 2.0,
            "square_footage": 2_200.0,
        },
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.FMR_BEDROOM_CAP_EXCEEDED)
    assert raised.severity == Severity.INFO
    assert result.get("rent_anchor_used") == pytest.approx(
        FAKE_ZORI_LEVEL
        * FakeFmrClient.SCHEDULES[2026]["Four-Bedroom"]
        / FakeFmrClient.SCHEDULES[2026]["Two-Bedroom"]
    )
    assert result.get("rent_estimate") is not None, (
        "The cap is an approximation to disclose, not a reason to refuse an estimate."
    )


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_a_feature_the_listing_never_stated_blocks_the_estimate(monkeypatch):
    """No substituted default may stand in for a field the listing did not contain.

    A corpus mean for the missing square footage would produce a rent figure describing
    a property nobody listed, and it would carry no marker distinguishing it from one
    built on real inputs. Refusing is the only option that leaves the report honest,
    and the flag names which field was missing so the refusal is actionable.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True, update={"price": 1_150_000.0, "square_footage": None}
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_ESTIMATE_UNAVAILABLE)
    assert "square_footage" in raised.detail
    assert result.get("rent_estimate") is None


@pytest.mark.skipif(not _corpus_available(), reason="Chroma index not built")
@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_the_comp_cross_check_stays_silent_when_the_model_and_comps_agree(monkeypatch):
    """The negative case, and §8 requires it: a flag that fired always would say nothing.

    Los Angeles is the market this must hold on, and not by luck. Measured Aug 22, 2026,
    its retrieved comps sit +7.9% against the metro's own 2-bedroom population, while
    Chicago's and Cleveland's sit +70.4% and +73.1% — LA is the one inference market
    whose comp set is genuinely representative, so it is the one where agreement is the
    correct outcome rather than a threshold set generously enough to hide a disagreement.

    The check must be shown to have actually *run*, not merely to have raised nothing.
    Those are different states with the same flag output, and conflating them would let
    this test keep passing if the cross-check silently stopped executing.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    detail = result.get("valuation_detail")
    assert detail.comps_cross_checked >= config.RENT_COMP_CROSSCHECK_MIN_COMPS, (
        "The cross-check did not run, so its silence proves nothing."
    )
    assert detail.divergence_pct is not None
    assert abs(detail.divergence_pct) <= config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT
    assert not flags_of_kind(result, FlagKind.RENT_DIVERGES_FROM_COMPS)
    assert "Cross-check against the comps:" in result["report_markdown"]


@pytest.mark.skipif(not _corpus_available(), reason="Chroma index not built")
@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_a_model_that_disagrees_with_its_comps_says_so(monkeypatch):
    """Force the disagreement at the model, which is the honest seam to force it at.

    The alternative — distorting the FMR schedule until the numbers separate — would
    move the comps and the estimate together, since both are normalized through it, and
    would therefore test the arithmetic rather than the disagreement. Overriding the
    predicted ratio moves exactly one of the two inputs, which is the situation the flag
    is about. Same reasoning as the `_consistency_objections` injection above.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)
    monkeypatch.setattr(
        valuation_module.rent_model, "predict_ratio", lambda *a, **k: 3.5
    )

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_DIVERGES_FROM_COMPS)
    assert raised.severity == Severity.WARN
    assert result.get("valuation_detail").divergence_pct > 0, (
        "An over-prediction should be reported as sitting above the comps; a flag that "
        "dropped the direction would tell a reader the estimate is suspect without "
        "telling them which way."
    )
    assert "above" in raised.detail


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_an_implausible_prediction_is_refused_rather_than_reported(monkeypatch):
    """A subject unlike anything the model trained on is refused, not priced.

    **This case exists because a fixture was written by accident and turned out to be
    load-bearing.** An earlier draft of the bedroom-cap test raised a 950 sqft duplex to
    five bedrooms without resizing it, and the agent declined to produce an estimate —
    which looked like a bug and was not.

    **What it asserts changed at U11.1, and the reason is the point.** Until then the
    refusal came from the *output* side: the shipped LinearRegression's `bedrooms`
    coefficient was negative (HUD's schedule climbs with bedroom count faster than real
    rents do), so a high bedroom count on a small footprint drove the predicted ratio
    below the plausible band and the agent refused. That made this test hostage to a
    fitted coefficient — the inputs had to be re-chosen once already, when ZIP-resolution
    anchoring shrank the coefficient from -0.44 to -0.33 and the original 5bd/950sqft
    fixture started predicting a low-but-legal 0.34.

    Gradient boosting has no such coefficient and, more to the point, **cannot produce an
    implausible ratio at all** — its prediction is an average of training targets already
    inside the band, so it clamps rather than extrapolating. The old mechanism would have
    gone quiet without failing, which is why the check moved to
    `rent_model.subject_is_out_of_domain` and why this test now asserts on the *input*
    being outside the training data rather than on the output being absurd. It is no
    longer pinned to anything a retrain can move: 6 bedrooms across 500 sqft is 83 square
    feet per bedroom against a measured p0.1 of 150, and that stays true whatever is
    fitted on top of it.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True,
        update={"price": 1_150_000.0, "bedrooms": 6, "square_footage": 500.0},
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_ESTIMATE_UNAVAILABLE)
    assert raised.severity == Severity.CRITICAL
    assert "square feet per bedroom" in raised.detail
    assert result.get("rent_estimate") is None


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_an_oversized_footprint_is_refused_at_the_other_tail(monkeypatch):
    """The same guard from above, at the end a per-feature range cannot reach.

    Added with U11.1 because the domain check has two tails and the case above only
    exercises one. This end is the one a naive guard misses: **5,000 sqft is comfortably
    inside the corpus's own 130-9,175 range**, so a per-feature min/max check waves this
    subject through. What is abnormal is the combination — two bedrooms across 5,000 sqft
    is 2,500 square feet per bedroom against a corpus median of 574.

    It is the shape of `eval/`'s `la-oversized-loft` fixture, which is the case the batch
    uses to cover this flag kind, so a regression here would show up there as a silently
    priced estimate rather than as a failure.
    """
    extraction = EXTRACTION_MISSING_PRICE.model_copy(
        deep=True,
        update={"price": 2_400_000.0, "bedrooms": 2, "square_footage": 5_000.0},
    )
    monkeypatch.setattr(extractor_module, "_extract_terms", lambda text: (extraction, 1))
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch)

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_ESTIMATE_UNAVAILABLE)
    assert raised.severity == Severity.CRITICAL
    assert result.get("rent_estimate") is None


@pytest.mark.skipif(not _rent_model_available(), reason="rent model not trained")
def test_a_county_without_small_area_fmr_says_the_anchor_is_coarse(monkeypatch):
    """A real case, not a hypothetical: Richmond County (Staten Island) has no SAFMR.

    The estimate is still produced — a county anchor is coarse, not absent — but a reader
    has no way to tell a ZIP-anchored figure from a county-anchored one by looking at it,
    and the difference is large: within counties that publish Small Area FMRs the ZIP
    schedules span roughly 2x. That is exactly the silent degradation the flag vocabulary
    exists for.
    """
    monkeypatch.setattr(extractor_module, "geocode", lambda *a, **k: parcel_at(*LOS_ANGELES))
    offline_valuation(monkeypatch, zori_covers_zip=False)

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.RENT_ANCHOR_COUNTY_LEVEL)
    assert raised.severity == Severity.WARN
    assert result["valuation_detail"].anchor_tier == "county"
    assert result.get("rent_anchor_used") == FakeFmrClient.SCHEDULES[2026]["Two-Bedroom"]
    assert result.get("rent_estimate") is not None, (
        "A coarse anchor is a disclosure, not a reason to refuse an estimate."
    )


# --------------------------------------------------------------------------
# 8. U7 — the Critic's own flags
#
# Everything above raises its flag upstream of the Critic and asks whether it survives.
# These ask the narrower question the U7 checks introduced: a flag raised by the *last*
# node before the Summarizer travels the shortest path in the system, and until U7.4
# nothing the Critic raised could even trigger the Critic's own escalation.
# --------------------------------------------------------------------------


def test_an_interaction_objection_reaches_the_report_and_escalates(monkeypatch):
    """The Critic's cross-agent objection is a flag like any other, and must survive.

    Two upstream disclosures that are individually ordinary — the comp set drifted onto
    a different kind of unit, and the modelled rent diverges from that set's median —
    combine into a statement neither agent could make on its own: the only independent
    check on the rent estimate is not readable on this deal. `_interaction_objections`
    proves that arithmetic hermetically in `test_critic_interactions.py`; this proves the
    conclusion reaches a reader.

    **The confidence score is what makes this case worth running through the graph.**
    Two warns land at 0.70, which *clears* the 0.60 threshold — so the deal escalates on
    the critical-flag rule alone, over a flag the Critic raised in the same pass. That
    path existed only on paper until U7.4: `has_critical` read `state.flags` and not the
    flags being returned, so a CRITICAL objection set no route and reported as a normal
    result.

    The two upstream flags are injected at the node boundary rather than obtained from
    the real agents, for this file's usual reason — the combination needs a corpus, a
    trained model and an FMR schedule to arise naturally, and this case is about what the
    Critic does with it, not about reproducing it. `test_critic_interactions.py` covers
    the check itself; the grounded runs above cover each input flag arising for real.
    """
    priced_cleanly(monkeypatch)
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS,
        nodes.COMPS_RETRIEVAL,
        lambda state: {
            "comps": [],
            "flags": [
                flag(
                    nodes.COMPS_RETRIEVAL,
                    FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA,
                    "[test] 3 of 8 comparables fall outside the size range searched for.",
                    Severity.WARN,
                    state.planner_invocations,
                )
            ],
        },
    )
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS,
        nodes.VALUATION_RENT,
        lambda state: {
            # The median as well as the flag: I1 and I3 are statements *about* the comp
            # cross-check, so since U8.6 they require it to have produced a verdict —
            # a stub that raised the divergence flag without one would describe a
            # comparison the real agent never wrote down.
            "valuation_detail": ValuationDetail(comp_implied_rent_median=2_000.0),
            "flags": [
                flag(
                    nodes.VALUATION_RENT,
                    FlagKind.RENT_DIVERGES_FROM_COMPS,
                    "[test] The modelled rent sits above the comparable-implied median.",
                    Severity.WARN,
                    state.planner_invocations,
                )
            ],
        },
    )
    # Silenced for the reason the rework case documents at length: an agent correctly
    # reporting a degradation of its own would escalate this deal on a different ground
    # and leave the case measuring nothing. With no rent estimate there is no forecast.
    monkeypatch.setitem(graph_module.NODE_FUNCTIONS, nodes.SCENARIO_FORECAST, lambda state: {})

    result = run_deal()

    raised = assert_reaches_report(result, FlagKind.CRITIC_INCONSISTENCY)
    assert raised.severity == Severity.CRITICAL
    assert raised.source_agent == nodes.CRITIC
    assert result["confidence_score"] == 0.70, (
        "Two warns and a derived objection: the objection must not be charged to the "
        "score as well, or the same observation is paid for twice."
    )
    assert result["confidence_score"] >= config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD, (
        "The point of this case is escalation *above* the threshold. If the weights "
        "move far enough that the score alone escalates, the case stops testing the "
        "critical-flag rule and needs re-pitching rather than re-baselining."
    )
    assert result["status"] == DealStatus.NEEDS_REVIEW
    assert result["rework_count"] == 0, (
        "A comp set relaxed onto a different unit type will relax the same way on a "
        "second pass, so this objection escalates rather than reworking."
    )


def test_a_report_carries_no_objection_when_the_disclosures_do_not_combine(monkeypatch):
    """The negative case, without which the flag above proves nothing.

    Same two-warn shape, same score of 0.70, one difference: the divergence flag is
    absent, so there is no cross-check whose readability could be in question. §8's
    standard for a threshold applies to an interaction as well — a check that fired on
    any two disclosures would be indistinguishable from no check, and would tell a reader
    nothing when it appeared.
    """
    priced_cleanly(monkeypatch)
    monkeypatch.setitem(
        graph_module.NODE_FUNCTIONS,
        nodes.COMPS_RETRIEVAL,
        lambda state: {
            "comps": [],
            "flags": [
                flag(
                    nodes.COMPS_RETRIEVAL,
                    FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA,
                    "[test] 3 of 8 comparables fall outside the size range searched for.",
                    Severity.WARN,
                    state.planner_invocations,
                ),
                flag(
                    nodes.COMPS_RETRIEVAL,
                    FlagKind.RELAXED_SEARCH_RADIUS,
                    "[test] Widened to 4.0 mi to find enough comparables.",
                    Severity.WARN,
                    state.planner_invocations,
                ),
            ],
        },
    )
    monkeypatch.setitem(graph_module.NODE_FUNCTIONS, nodes.VALUATION_RENT, lambda state: {})
    monkeypatch.setitem(graph_module.NODE_FUNCTIONS, nodes.SCENARIO_FORECAST, lambda state: {})

    result = run_deal()

    assert not flags_of_kind(result, FlagKind.CRITIC_INCONSISTENCY)
    assert result["confidence_score"] == 0.70
    assert result["status"] == DealStatus.COMPLETE, (
        "Two ordinary warns above the threshold report normally. If this deal "
        "escalates, the interaction check has started firing on the accumulation "
        "rather than on the combination."
    )
