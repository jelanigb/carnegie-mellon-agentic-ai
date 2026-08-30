"""**Superseded by U11.3 and kept only for the factor arithmetic.** The rent-drift
correction is no longer applied by the pipeline: the anchor is now a market index read
at each row's own month, so the schedule-versus-market gap this module corrected for is
divided out where it arises rather than removed afterwards. `tools/rent_drift.py` is
unused by `agents/valuation_rent.py` and is scheduled for retirement at U11.M; the
symmetry case that asserted the correction cancelled out of `divergence_pct` is deleted
here because the parameter it exercised no longer exists.

The drift correction's arithmetic, its refusal paths, and its symmetry (U8.4b).

Deliberately scoped, per §8's testing preference: the factor computation and the one
property that would corrupt a published check if it broke — that the correction cancels
out of the comp divergence because it applies to both sides. End-to-end behaviour
(which flags a corrected demo deal carries) is the eval batch's job, not this file's.

Every HUD and ZORI dependency is stubbed at the seam `tools/rent_drift.py` reads them
through, so this file runs with no network and no data files present.
"""

from __future__ import annotations

import pandas as pd
import pytest

import config
from agents import valuation_rent
from state import DealState, DealTerms
from tools import rent_drift
from tools.model.rent_model import CompAnchoring


VINTAGE = config.ZORI_VINTAGE_MONTH  # "2019-06-30"


class _StubHud:
    """Returns a fixed schedule per fiscal year, in the client's normalized shape."""

    def __init__(self, rents_by_year: dict, is_safmr: bool = False,
                 used_msa_fallback: bool = False, current_year: int = 2026,
                 shape_by_year: dict | None = None):
        self.rents_by_year = rents_by_year
        self.is_safmr = is_safmr
        self.used_msa_fallback = used_msa_fallback
        self.current_year = current_year
        self.shape_by_year = shape_by_year or {}

    def get_fmr_for_bedroom(self, entityid, bedrooms, year=None, zip_code=None):
        effective = year if year is not None else self.current_year
        shape = self.shape_by_year.get(effective, {})
        return {
            "rent": self.rents_by_year[effective],
            "year": effective,
            "is_safmr": shape.get("is_safmr", self.is_safmr),
            "used_msa_fallback": shape.get("used_msa_fallback", self.used_msa_fallback),
        }


def _panel(zip_code: str, months: dict) -> pd.DataFrame:
    """A one-ZIP ZORI panel in the real file's shape: identity column + month columns."""
    return pd.DataFrame([{"RegionName": zip_code, "zip": zip_code, **months}])


@pytest.fixture(autouse=True)
def _fresh_panel_cache():
    rent_drift._zori_panel.cache_clear()
    yield
    rent_drift._zori_panel.cache_clear()


def test_the_factor_is_market_growth_over_schedule_growth(monkeypatch):
    # Market rent rose 30% while the schedule rose 50%: the factor must be 1.30/1.50.
    monkeypatch.setattr(
        rent_drift, "_zori_panel",
        lambda: _panel("60618", {VINTAGE: 2000.0, "2026-06-30": 2600.0}),
    )
    result = rent_drift.compute_drift(
        "60618", "1703199999", 2, None,
        client=_StubHud({2026: 3000.0, 2019: 2000.0}),
    )
    assert result.applied
    assert result.factor == pytest.approx((2600 / 2000) * (2000 / 3000))
    assert result.market_growth_pct == pytest.approx(30.0)
    assert result.schedule_growth_pct == pytest.approx(50.0)
    assert result.zori_vintage_substituted is False


def test_no_zip_and_no_coverage_both_refuse_with_different_reasons(monkeypatch):
    monkeypatch.setattr(
        rent_drift, "_zori_panel",
        lambda: _panel("60618", {VINTAGE: 2000.0, "2026-06-30": 2600.0}),
    )
    no_zip = rent_drift.compute_drift(None, "1703199999", 2, None, client=_StubHud({}))
    uncovered = rent_drift.compute_drift(
        "99999", "1703199999", 2, None, client=_StubHud({})
    )
    assert not no_zip.applied and "no ZIP" in no_zip.unavailable_reason
    assert not uncovered.applied and "does not cover" in uncovered.unavailable_reason


def test_a_vintage_substituted_past_the_limit_refuses(monkeypatch):
    # Series begins 14 months after the vintage month: reading it as the "before" figure
    # would land on the far side of the 2021-22 surge, the exact error the limit exists
    # to stop. (14 > ZORI_MAX_VINTAGE_SUBSTITUTION_MONTHS = 12.)
    monkeypatch.setattr(
        rent_drift, "_zori_panel",
        lambda: _panel("60618", {"2020-08-31": 2200.0, "2026-06-30": 2600.0}),
    )
    result = rent_drift.compute_drift(
        "60618", "1703199999", 2, None,
        client=_StubHud({2026: 3000.0, 2019: 2000.0}),
    )
    assert not result.applied
    assert "begins too long after" in result.unavailable_reason


def test_mixed_anchor_grains_refuse_rather_than_mix_baselines(monkeypatch):
    # A ZIP schedule that exists today but not at the vintage (the Los Angeles shape):
    # the ratio would divide a ZIP-level numerator year by a county-level denominator
    # year.
    monkeypatch.setattr(
        rent_drift, "_zori_panel",
        lambda: _panel("90026", {VINTAGE: 2000.0, "2026-06-30": 2600.0}),
    )
    result = rent_drift.compute_drift(
        "90026", "0603799999", 2, "90026",
        client=_StubHud(
            {2026: 3000.0, 2019: 2000.0},
            shape_by_year={
                2026: {"is_safmr": True, "used_msa_fallback": False},
                2019: {"is_safmr": False, "used_msa_fallback": False},
            },
        ),
    )
    assert not result.applied
    assert "different spatial grains" in result.unavailable_reason


def test_an_implausible_factor_refuses_as_a_data_defect(monkeypatch):
    # A ZORI series that tripled against a flat schedule computes a factor of ~3 —
    # outside RENT_DRIFT_FACTOR_MAX, so it must be refused, not applied.
    monkeypatch.setattr(
        rent_drift, "_zori_panel",
        lambda: _panel("60618", {VINTAGE: 1000.0, "2026-06-30": 3000.0}),
    )
    result = rent_drift.compute_drift(
        "60618", "1703199999", 2, None,
        client=_StubHud({2026: 2000.0, 2019: 2000.0}),
    )
    assert not result.applied
    assert "plausible band" in result.unavailable_reason

# **`test_the_correction_cancels_out_of_the_divergence` was deleted at U11.3.** It
# asserted that the drift factor cancelled out of `divergence_pct` because it scaled the
# estimate and the comp-implied figures symmetrically. The anchor is now a market index
# read at each row's own listing month, so the schedule-versus-market gap is divided out
# where it arises rather than corrected afterwards, and `_cross_check` no longer takes a
# factor for the case to exercise. `tools/rent_drift.py` is unused by the pipeline as of
# that change and is scheduled for retirement at U11.M; the cases above still pass and
# still describe the module's arithmetic, so they stay until it goes.
