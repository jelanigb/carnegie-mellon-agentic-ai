"""The report's one comparison between what the seller claims and what the system derived.

Kept out of `test_flag_propagation.py` because nothing here raises a flag — this is a
Summarizer disclosure, not a check (U7 Q4). Nothing about it reaches confidence, routing
or the rework cycle, so a failure here means the report says something wrong, never that
the pipeline decided something wrong.

Every case renders the section directly from a constructed `DealState`. No LLM, no
network, no corpus, no trained model.
"""

from __future__ import annotations

import re

import config
from agents.summarizer import _stated_rent_section
from state import DealState, DealTerms


def _render(*, estimate: float | None, rents: list[float], **terms) -> str:
    state = DealState(
        raw_listing_text="irrelevant to a rendering test",
        deal_terms=DealTerms(unit_rents=rents, **terms),
        rent_estimate=estimate,
    )
    return "\n".join(_stated_rent_section(state, None))


def test_the_stated_rents_and_the_estimate_both_reach_the_reader():
    """The gap this section exists for was invisible before it: the report rendered
    `rent_estimate` and never `deal_terms.unit_rents`, so a reader could not see that the
    two disagreed by roughly a third."""
    text = _render(estimate=4_075.0, rents=[2_850.0, 2_950.0], unit_count=2, bedrooms=2)

    assert "$2,850" in text and "$2,950" in text   # what the listing claims
    assert "$4,075" in text                        # what the system derived
    assert "29% below" in text                     # and the distance between them
    assert "$5,800" in text and "$8,150" in text   # both totalled across the units


def test_the_caveat_follows_the_direction_of_the_gap():
    """The structural offset only explains stated rents that fall *below* the estimate.
    Printing that explanation over a listing whose rents sit above it would excuse the
    one case worth questioning."""
    below = _render(estimate=4_075.0, rents=[2_850.0], unit_count=1, bedrooms=2)
    above = _render(estimate=1_700.0, rents=[2_400.0], unit_count=1, bedrooms=1)

    assert "is expected" in below
    assert "worth verifying against leases" not in below

    assert "worth verifying against leases" in above
    assert "is expected" not in above


def test_a_listing_that_states_no_rents_says_so():
    """The same rule `_rent_basis_section` follows: a comparison rendered only where it
    is available shows its working only on the runs where the working looked good."""
    text = _render(estimate=3_000.0, rents=[], unit_count=3, bedrooms=2)

    assert "states no per-unit rents" in text
    assert "$3,000" not in text  # nothing to compare it against, so no false comparison


def test_fewer_stated_rents_than_units_is_disclosed():
    """Otherwise the total silently describes part of the property while reading as the
    whole rent roll."""
    text = _render(estimate=1_700.0, rents=[1_800.0, 1_850.0], unit_count=4, bedrooms=1)

    assert "4 units but rents for 2" in text
    assert "understates the property's rent roll" in text


def test_the_divergence_threshold_gates_the_emphasis(monkeypatch):
    """`RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD` ships as `None`, so this branch is
    unreachable in the shipped configuration. Exercised here rather than left to U8 to
    discover: a branch nothing can enter is not a branch, and the whole reason the
    constant is `None` is that the number needs evidence this project does not yet have.
    """
    emphasis = "larger than this report treats as ordinary"

    assert config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD is None
    assert emphasis not in _render(
        estimate=4_075.0, rents=[2_850.0], unit_count=1, bedrooms=2
    )

    monkeypatch.setattr(config, "RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD", 0.25)
    assert emphasis in _render(
        estimate=4_075.0, rents=[2_850.0], unit_count=1, bedrooms=2
    )
    # 3% gap, well inside the same threshold — the line is a threshold, not a constant.
    assert emphasis not in _render(
        estimate=2_900.0, rents=[2_820.0], unit_count=1, bedrooms=2
    )


def test_the_disclosure_carries_no_internal_vocabulary():
    """Same rule the Critic's objections are held to: a section number, a decision
    number, a unit label or a `config` constant name is this repository's vocabulary and
    not the reader's."""
    banned = re.compile(
        r"§\d"
        r"|(?<![\w$])#\d+"
        r"|\bU\d+(\.\d+)?\b"
        r"|\bconfig\.[A-Z_]+"
        r"|\bFlagKind\."
        r"|\bFMR\b"          # the anchor is named in plain words, not by its acronym
        r"|\bZORI\b",
    )
    cases = [
        _render(estimate=4_075.0, rents=[2_850.0, 2_950.0], unit_count=2, bedrooms=2),
        _render(estimate=1_700.0, rents=[2_400.0], unit_count=1, bedrooms=1),
        _render(estimate=3_000.0, rents=[], unit_count=3, bedrooms=2),
        _render(estimate=1_700.0, rents=[1_800.0, 1_850.0], unit_count=4, bedrooms=1),
        _render(estimate=2_500.0, rents=[2_400.0], unit_count=1),  # bedroom count unknown
    ]
    for text in cases:
        found = banned.search(text)
        assert found is None, f"disclosure leaks internal vocabulary {found.group(0)!r}"
