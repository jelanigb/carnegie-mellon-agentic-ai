"""The one investor ratio this project's data supports, and the line it stops at.

Kept out of `test_flag_propagation.py` because nothing here raises a flag: the multiple
is a disclosure, nothing computes from it, and no check reads it — the same standing
`ValuationDetail.benchmark_median_sale_price` has. A failure here means the report states
a wrong ratio, never that the pipeline decided something wrong.

The arithmetic is one division and is tested anyway, because the *inputs* are the part
that can go wrong quietly: a multiple built on the stated rents instead of the modelled
one, or on a per-unit rent that was never multiplied out, is wrong by a factor nobody
would notice in a plausible-looking number.

No LLM, no network, no corpus, no trained model.
"""

from __future__ import annotations

import pytest

from agents.summarizer import _gross_rent_multiplier_section
from agents.valuation_rent import _attach_gross_rent_multiplier
from state import DealState, DealTerms, ValuationDetail


def _detail(*, price, units, rent, benchmark=None, tier=None) -> ValuationDetail:
    detail = ValuationDetail(
        benchmark_median_sale_price=benchmark, benchmark_tier=tier
    )
    _attach_gross_rent_multiplier(
        detail, DealTerms(price=price, unit_count=units), rent
    )
    return detail


def _render(detail: ValuationDetail, *, units: int | None = 2) -> str:
    state = DealState(
        raw_listing_text="irrelevant to a rendering test",
        deal_terms=DealTerms(unit_count=units),
    )
    return "\n".join(_gross_rent_multiplier_section(state, detail))


def test_the_multiple_is_price_over_annual_rent_across_every_unit():
    """The `los-angeles` figures. A per-unit rent left un-multiplied would give 30.6 —
    a number that still looks like a plausible multiple, which is why this is asserted
    rather than eyeballed."""
    detail = _detail(price=1_049_000.0, units=2, rent=2_861.0)

    assert detail.grm_annual_gross_rent == pytest.approx(2_861.0 * 2 * 12)
    assert detail.gross_rent_multiplier == pytest.approx(15.28, abs=0.01)


def test_the_benchmark_multiple_shares_the_deal_multiple_s_denominator():
    """Which is what makes their ratio exactly the price premium — and why the report
    says they are one comparison in two units rather than two measurements."""
    detail = _detail(
        price=1_049_000.0, units=2, rent=2_861.0,
        benchmark=1_047_955.0, tier="metro",
    )

    ratio_of_multiples = (
        detail.gross_rent_multiplier / detail.benchmark_gross_rent_multiplier
    )
    assert ratio_of_multiples == pytest.approx(1_049_000.0 / 1_047_955.0)


def test_a_listing_with_no_price_says_why_rather_than_going_silent():
    """`la-unpriced-triplex` reaches this path. An empty section would read as a report
    that forgot the ratio rather than one that could not form it."""
    detail = _detail(price=None, units=2, rent=2_861.0)

    assert detail.gross_rent_multiplier is None
    text = _render(detail)
    assert "no asking price" in text
    assert "No gross rent multiple was formed" in text


def test_an_unresolved_unit_count_does_not_default_to_one():
    """Defaulting would produce a multiple describing a property the listing never
    described — the same error `RENT_ESTIMATE_UNAVAILABLE` exists to refuse one field
    over."""
    detail = _detail(price=1_049_000.0, units=None, rent=2_861.0)

    assert detail.gross_rent_multiplier is None
    assert "unit count" in (detail.grm_unavailable_reason or "")


def test_the_report_says_the_multiple_is_gross_and_why_there_is_no_cap_rate():
    """The boundary is the point of the section. A gross multiple presented without it
    reads as a yield, and a reader who came for cap rate should learn why it is absent
    rather than assume the system forgot."""
    text = _render(_detail(price=1_049_000.0, units=2, rent=2_861.0))

    assert "gross multiple, not a yield" in text
    assert "vacancy" in text and "expense ratio" in text
