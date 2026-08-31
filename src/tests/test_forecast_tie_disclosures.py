"""What the forecast search's scores say, and where its cut line fell (U8.6c).

Kept out of `test_flag_propagation.py` for the same reason
`test_stated_rent_disclosure.py` is: nothing here decides anything. The cut-boundary
disclosure is INFO, so it costs no confidence and moves no verdict, and the evaluator's
per-scenario score is a rendering. A failure here means the report withholds or misstates
something a reader was promised, never that the pipeline routed a deal wrongly.

Two of these assert a *measurement* rather than a message, which is the point of the
subsection: the depth-2 cut line — which pairings reach the report at all — was the one
rank comparison in the search that nothing measured.

Every case runs the real `tot.beam_search` over a hand-scored candidate set, or renders
directly from a constructed `DealState`. No LLM, no network, no corpus.
"""

from __future__ import annotations

from typing import Sequence

import pytest

import config
from agents.scenario_forecast import _disclosure_flags
from agents.summarizer import _scenario_section
from state import DealState, DealTerms, FlagKind, ForecastDetail, Scenario, Severity
from tools import tot


def _search(scores: list[float], *, width: int, conservatism=None) -> tot.SearchResult:
    """One level of beam search over candidates whose scores are dictated by the case.

    The scorer is a lookup rather than a model call, so a case states the exact rank
    structure it is about and the search does the cutting.
    """

    def expand(depth: int, parents: Sequence[tot.Candidate]) -> list[tot.Candidate]:
        if depth != 1:
            return []
        return [
            tot.Candidate(id=f"c{i}", depth=1, payload={"i": i}, summary=f"candidate {i}")
            for i in range(len(scores))
        ]

    def score(depth: int, candidates: Sequence[tot.Candidate]):
        return [(scores[c.payload["i"]], c.summary) for c in candidates]

    return tot.beam_search(
        expand,
        lambda candidate: None,
        score,
        beam_width=width,
        max_depth=1,
        prune_threshold=0.0,
        conservatism_key=conservatism,
    )


def test_the_cut_line_is_measured_not_only_the_ordering_above_it():
    """`score_gap_by_depth` compares #1 against #2; this compares #3 against #4.

    They answer different questions and the second is the one that decides which
    hypotheses are reported at all.
    """
    result = _search([0.90, 0.80, 0.70, 0.40], width=3)

    assert result.score_gap_by_depth[1] == pytest.approx(0.10)      # #1 vs #2
    assert result.cut_boundary_gap_by_depth[1] == pytest.approx(0.30)  # #3 vs #4


def test_a_cut_taken_inside_a_tie_group_records_a_non_positive_margin():
    """The tie-break can move a higher-scoring candidate below the line.

    That is the sharpest version of the finding — the reported set was chosen by this
    project's conservatism preference rather than by the evaluator — so the margin has to
    be able to come out negative rather than being reported as an absolute distance.
    """
    # #3 and #4 are within TOT_TIE_EPSILON, so `_rank` sorts that pair by conservatism;
    # the key below prefers the *lower*-scoring one, which puts it above the cut.
    result = _search(
        [0.90, 0.80, 0.70, 0.69],
        width=3,
        conservatism=lambda candidate: candidate.score or 0.0,
    )

    assert result.cut_boundary_gap_by_depth[1] < 0


def test_a_cut_line_inside_the_tie_threshold_is_disclosed():
    detail = ForecastDetail()
    result = tot.SearchResult(cut_boundary_gap_by_depth={2: 0.01})

    flags = _disclosure_flags(detail, result, {}, [], planner_invocations=1)

    assert len(flags) == 1
    assert flags[0].kind is FlagKind.FORECAST_BRANCHES_NEAR_TIED
    assert flags[0].severity is Severity.INFO
    # The reader is told what is at stake at this line specifically, which is what
    # separates it from a tie between two scenarios that both appear in the report.
    assert "which pairings are shown at all" in flags[0].detail


def test_a_cut_the_tie_break_decided_says_so_rather_than_claiming_a_margin():
    """The common case on this batch, and the stronger finding of the two.

    A non-positive margin means the discarded pairing outscored the one that reached the
    report and lost on the conservatism preference. Describing that as "separated by
    0.050, inside the 0.05 threshold" would be self-contradictory *and* would understate
    what happened.
    """
    result = tot.SearchResult(cut_boundary_gap_by_depth={2: -0.05})

    detail = _disclosure_flags(ForecastDetail(), result, {}, [], planner_invocations=1)[0]

    assert "not separated on score at all" in detail.detail
    assert "0.050 *above* the one kept" in detail.detail
    assert "more conservative reading" in detail.detail


def test_a_decisive_cut_line_says_nothing():
    """A margin the evaluator could resolve is not a disclosure. Asserted because the
    opposite failure — a flag that fires on every run — is how a disclosure stops being
    read."""
    result = tot.SearchResult(cut_boundary_gap_by_depth={2: config.TOT_TIE_EPSILON * 4})

    assert _disclosure_flags(ForecastDetail(), result, {}, [], planner_invocations=1) == []


def test_each_scenario_reports_the_score_it_was_judged_on():
    """The field was populated and carried on state since U6 and rendered nowhere, so the
    search's own judgment of each surviving hypothesis was invisible to the reader."""
    state = DealState(
        raw_listing_text="irrelevant to a rendering test",
        deal_terms=DealTerms(),
        scenarios=[
            Scenario(
                name="pessimistic",
                rent_growth_pct_per_year=1.0,
                price_growth_pct_per_year=1.0,
                rationale="Rents lag the schedule.",
                evaluator_score=0.45,
            ),
            Scenario(
                name="optimistic",
                rent_growth_pct_per_year=4.0,
                price_growth_pct_per_year=3.0,
                rationale="Supply stays tight.",
                evaluator_score=0.85,
            ),
        ],
    )

    text = "\n".join(_scenario_section(state))

    assert "scored 0.45" in text and "scored 0.85" in text
    # Both cautions the score is useless without: the labels are not a score ranking, and
    # one draw of a noisy judge is not a rank (OQ-17).
    assert "not from these scores" in text
    assert "repeat runs measurably vary" in text


def test_a_scenario_with_no_score_renders_without_one():
    """The heuristic fallback path scores candidates too, but a scenario reconstructed
    from partial state may not carry one, and a report is not allowed to invent it."""
    state = DealState(
        raw_listing_text="irrelevant to a rendering test",
        deal_terms=DealTerms(),
        scenarios=[Scenario(name="base", rationale="The only hypothesis that survived.")],
    )

    text = "\n".join(_scenario_section(state))

    assert "The only hypothesis that survived." in text
    assert "scored" not in text
