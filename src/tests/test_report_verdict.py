"""Axis 2 — the recommendation, its cross-check, and the report's two verdict lines (U9.4).

Unit tests over a pure function plus a rendering pass, kept out of
`test_flag_propagation.py` for the reason `test_critic_interactions.py` gives: that suite
proves a flag survives every node and reaches the report, and these prove a *judgment* is
reached correctly in the first place. Different guarantee, different failure mode.

The first three cases are the ones worth protecting. **The rule must not read axis 1** —
the whole design is two questions answered separately, and the failure mode is subtle
enough that the first draft of `recommend()` had it: an uncorroborated rent, which is
largely a fact about data coverage in a market, reached a verdict about the property.
`staten-island` is the deal where that shows, and the regression for it is
`test_an_uncorroborated_rent_alone_does_not_reach_caution`.

`conftest.offline_report_calls` disables the two model calls for every test here as it
does everywhere; the two that exercise them re-enable one and substitute a client, which
is also what makes the point that neither can move a figure.
"""

from __future__ import annotations

import re

import pytest

import config
from agents import summarizer as summarizer_module
from agents.critic import cross_check, recommend
from agents.summarizer import summarizer_agent
from state import (
    DealState,
    DealTerms,
    Recommendation,
    RecommendationDetail,
    Severity,
    ValuationDetail,
    flag,
    FlagKind,
)
from tools.llm_client import LlmError


def _state(
    price: float | None = 1_000_000.0,
    benchmark: float | None = 1_000_000.0,
    tier: str | None = "zip",
    rent: float | None = 2_500.0,
    comp_median: float | None = 2_500.0,
    diverged: bool = False,
    **deal_state_kwargs,
) -> DealState:
    """A DealState carrying exactly the inputs the recommendation rule reads.

    `comp_median=None` mirrors what `valuation_rent._cross_check` does below
    `config.RENT_COMP_CROSSCHECK_MIN_COMPS` surviving comps: it returns before computing
    a median, so the estimate has no independent check. That and `diverged` are the two
    ways the rent claim fails to be corroborated, and the rule treats them alike.
    """
    detail = ValuationDetail(
        benchmark_median_sale_price=benchmark,
        benchmark_tier=tier,
        comp_implied_rent_median=comp_median,
    )
    if tier == "zip":
        # A ZIP-tier benchmark never arrives without the figures the report prints beside
        # it — `sale_benchmarks.ZipBenchmark` carries the count, window and attribution in
        # the same object as the median, deliberately, so a reader can discount a thin one.
        # Populated here so the fixture describes a state the pipeline can actually reach.
        detail.benchmark_zip = "60640"
        detail.benchmark_zip_n_sales = 148
        detail.benchmark_zip_window_start = "2023-01-01"
        detail.benchmark_zip_attribution = "synthetic"
        detail.benchmark_zip_definition = "2-6 unit apartment buildings"
    if comp_median is not None:
        # `valuation_rent._cross_check` writes the median, its quartiles, the two comp
        # counts and the divergence in one pass or writes none of them, so a fixture that
        # sets only the median describes a state the pipeline cannot produce.
        detail.comp_implied_rent_p25 = comp_median * 0.9
        detail.comp_implied_rent_p75 = comp_median * 1.1
        detail.comps_cross_checked = 8
        detail.comps_available = 8
        detail.divergence_pct = (rent - comp_median) / comp_median if rent else 0.0
    flags = (
        [flag("valuation_rent", FlagKind.RENT_DIVERGES_FROM_COMPS, "synthetic", Severity.WARN, 1)]
        if diverged
        else []
    )
    return DealState(
        raw_listing_text="irrelevant to a verdict",
        deal_terms=DealTerms(price=price),
        rent_estimate=rent,
        valuation_detail=detail,
        flags=flags,
        **deal_state_kwargs,
    )


# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------


def test_a_price_inside_the_ordinary_range_proceeds():
    assert recommend(_state(price=1_000_000)).verdict is Recommendation.PROCEED


def test_a_premium_past_the_caution_threshold_warns():
    price = 1_000_000 * (1 + config.RECOMMENDATION_ZIP_CAUTION_PREMIUM + 0.01)
    assert recommend(_state(price=price)).verdict is Recommendation.PROCEED_WITH_CAUTION


def test_an_uncorroborated_rent_alone_does_not_reach_caution():
    """**The regression for U9.4's own defect, and the reason it is the third test here.**

    Whether the comp cross-check could run is largely a statement about data coverage in
    a market — `state.scope_of` classifies the sparse-comp disclosure as market-scoped for
    exactly that reason — so it belongs to axis 1. The first draft let it reach a verdict
    on its own, which made `staten-island` read *proceed with caution* about a deal whose
    only measured fact is that it is **17% below its ZIP median**: the misreading the
    escalation banner already produced, reintroduced one line lower.
    """
    detail = recommend(_state(price=830_000, comp_median=None))
    assert detail.rent_corroborated is False
    assert detail.verdict is Recommendation.PROCEED


def test_a_divergent_cross_check_counts_the_same_as_one_that_never_ran():
    assert recommend(_state(diverged=True)).rent_corroborated is False


def test_reject_needs_the_premium_and_the_rent_failure_together():
    """Neither instrument rejects alone; the benchmark is not a valuation and says so."""
    price = 1_000_000 * (1 + config.RECOMMENDATION_ZIP_REJECT_PREMIUM + 0.01)
    assert recommend(_state(price=price)).verdict is Recommendation.PROCEED_WITH_CAUTION
    assert recommend(_state(price=price, comp_median=None)).verdict is (
        Recommendation.DO_NOT_PROCEED
    )


def test_the_metro_tier_is_held_to_a_higher_bar_than_the_zip_tier():
    """A metro median describes properties an hour apart, and the measurement says so.

    +55% is around the 90th percentile of sales in a ZIP and roughly the 78th against a
    metro-wide median. The same listing therefore reads differently against the two
    references, which is why the tier travels with the premium rather than the premium
    travelling alone.
    """
    price = 1_000_000 * 1.55
    assert recommend(_state(price=price, tier="zip")).verdict is (
        Recommendation.PROCEED_WITH_CAUTION
    )
    assert recommend(_state(price=price, tier="metro")).verdict is Recommendation.PROCEED


def test_an_unknown_tier_falls_to_the_harder_threshold():
    """The safe direction: an unrecognized tier should say less about a deal, not more."""
    price = 1_000_000 * 1.55
    assert recommend(_state(price=price, tier=None)).verdict is Recommendation.PROCEED


@pytest.mark.parametrize(
    "kwargs", [dict(price=None), dict(benchmark=None, tier=None)], ids=["no-price", "no-benchmark"]
)
def test_a_missing_input_yields_no_recommendation_rather_than_a_verdict(kwargs):
    detail = recommend(_state(**kwargs))
    assert detail.verdict is Recommendation.NO_RECOMMENDATION
    assert detail.reasons, "the absent input should be named, not left silent"


def test_the_rule_ignores_the_escalation_decision_entirely():
    """Axis 1 must not reach axis 2. Same evidence, both routing outcomes, one verdict."""
    reported = recommend(_state(needs_human_review=False))
    escalated = recommend(_state(needs_human_review=True, confidence_score=0.0))
    assert reported.verdict is escalated.verdict


def test_verdict_text_carries_no_internal_vocabulary():
    """Every reason reaches the investor-facing report, so each has to stand alone."""
    banned = re.compile(
        r"§\d|(?<![\w$])#\d+|\bU\d+(\.\d+)?\b|\bconfig\.[A-Z_]+|\bFlagKind\.|\bp\d{2}\b"
    )
    for kwargs in (
        dict(price=1_000_000),
        dict(price=1_600_000),
        dict(price=1_600_000, comp_median=None),
        dict(price=700_000),
        dict(price=None),
        dict(benchmark=None, tier=None),
    ):
        for reason in recommend(_state(**kwargs)).reasons:
            assert not banned.search(reason), reason


# ---------------------------------------------------------------------------
# The cross-check — it annotates, and it can never decide
# ---------------------------------------------------------------------------


class _FixedClient:
    """An LlmClient whose one call returns a chosen verdict."""

    def __init__(self, verdict: Recommendation):
        self._verdict = verdict

    def call_with_schema(self, prompt, schema, **kwargs):
        return schema(verdict=self._verdict, reasoning="synthetic second opinion"), 1


def test_a_disagreeing_model_annotates_the_verdict_without_moving_it(monkeypatch):
    monkeypatch.setattr(config, "RECOMMENDATION_CROSS_CHECK_ENABLED", True)
    monkeypatch.setattr(
        "agents.critic.LlmClient", lambda *a, **k: _FixedClient(Recommendation.DO_NOT_PROCEED)
    )
    state = _state(price=1_000_000)
    detail = cross_check(state, recommend(state))

    assert detail.verdict is Recommendation.PROCEED, "the rule decides, always"
    assert detail.model_verdict is Recommendation.DO_NOT_PROCEED
    assert detail.cross_check_disagrees


def test_an_unreachable_model_leaves_no_annotation_rather_than_a_disagreement(monkeypatch):
    """A missing second opinion is not a disagreement, and must not render as one."""
    monkeypatch.setattr(config, "RECOMMENDATION_CROSS_CHECK_ENABLED", True)

    def _refuse(*args, **kwargs):
        raise LlmError("offline")

    monkeypatch.setattr("agents.critic.LlmClient", _refuse)
    state = _state(price=1_000_000)
    detail = cross_check(state, recommend(state))

    assert detail.model_verdict is None
    assert not detail.cross_check_disagrees


# ---------------------------------------------------------------------------
# The report's two lines
# ---------------------------------------------------------------------------


def _report(state: DealState) -> str:
    return summarizer_agent(state)["report_markdown"]


def test_the_two_axes_render_as_separate_lines_that_do_not_merge():
    """`staten-island`'s shape: escalated on axis 1, and a fine deal on axis 2.

    The single most-cited readability defect this unit exists to fix — a reader who saw
    the escalation banner and concluded the property was bad had it exactly backwards.
    """
    state = _state(price=830_000, comp_median=None, needs_human_review=True)
    state.recommendation = recommend(state)
    report = _report(state)

    assert "Recommendation — Proceed." in report
    # **The label changed Sept 2, 2026 and the assertion follows the meaning, not the
    # wording.** "System check" named the instrument; the line now names the consequence
    # — who has to do what before this report goes anywhere — which is the readability
    # fix this test exists to protect, applied one level deeper than it was.
    assert "Flagged by system — needs human review before sharing with investors" in report
    assert "not about the property" in report


def test_a_clean_run_says_so_on_the_system_line_rather_than_staying_silent():
    state = _state(price=1_000_000)
    state.recommendation = recommend(state)
    report = _report(state)

    assert "Cleared by system — no human review needed before sharing" in report
    # Worded to mirror the escalated branch, so the two read as one question answered two
    # ways. A pair that drifts apart is how the axis distinction stops being legible.
    assert "System check" not in report
    assert "escalated" not in report.lower()


def test_the_disagreement_is_disclosed_in_the_report_rather_than_resolved():
    state = _state(price=1_000_000)
    state.recommendation = RecommendationDetail(
        verdict=Recommendation.PROCEED,
        reasons=["synthetic"],
        model_verdict=Recommendation.DO_NOT_PROCEED,
        model_rationale="synthetic second opinion",
    )
    report = _report(state)

    assert "independent review of the same evidence" in report
    assert "disclosed here rather than resolved" in report
    assert "Recommendation — Proceed." in report


def test_agreement_adds_no_line_at_all():
    state = _state(price=1_000_000)
    state.recommendation = RecommendationDetail(
        verdict=Recommendation.PROCEED,
        reasons=["synthetic"],
        model_verdict=Recommendation.PROCEED,
    )
    assert "independent review" not in _report(state)


# ---------------------------------------------------------------------------
# The written summary — additive, and it decides nothing
# ---------------------------------------------------------------------------


def test_the_summary_is_absent_when_the_switch_is_off():
    state = _state(price=1_000_000)
    state.recommendation = recommend(state)
    assert "## Summary" not in _report(state)


def test_a_failed_summary_renders_a_sentence_and_never_a_flag(monkeypatch):
    """**Q1, answered Aug 31.** A 31st `FlagKind` would break U8's 30-of-30 coverage
    census unless some declared fault could reach it, and every other flag in this system
    propagates — one raised in the terminal node has no consumer but the report already
    printing it.
    """
    monkeypatch.setattr(config, "SUMMARY_NARRATIVE_ENABLED", True)

    def _refuse(*args, **kwargs):
        raise LlmError("offline")

    monkeypatch.setattr(summarizer_module, "LlmClient", _refuse)
    state = _state(price=1_000_000)
    state.recommendation = recommend(state)
    before = len(state.flags)
    report = _report(state)

    assert "A written summary could not be generated for this run" in report
    assert "the disclosures and figures below are unaffected" in report
    assert len(state.flags) == before, "the failure must not raise a flag"


def test_a_summary_that_returns_nothing_is_treated_as_a_failure(monkeypatch):
    """An empty string is a failed call that did not raise, and renders the same sentence."""
    monkeypatch.setattr(config, "SUMMARY_NARRATIVE_ENABLED", True)

    class _Empty:
        def complete(self, *args, **kwargs):
            return "   "

    monkeypatch.setattr(summarizer_module, "LlmClient", lambda *a, **k: _Empty())
    state = _state(price=1_000_000)
    state.recommendation = recommend(state)
    assert "could not be generated" in _report(state)


def test_the_summary_prompt_quotes_no_raw_float(monkeypatch):
    """OQ-18's fragility, kept out rather than added to a second time.

    A full-precision float in a prompt is a cache key that moves whenever an upstream
    computation shifts in its last decimal place. Everything the prompt carries is a
    rounded percentage, a whole dollar figure or a short string.
    """
    state = _state(price=1_049_123.4567, rent=2861.339)
    state.recommendation = recommend(state)
    prompt = summarizer_module._lede_prompt(state)
    assert not re.search(r"\d\.\d{3,}", prompt), prompt
