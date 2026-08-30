"""Per-subject rent-drift correction factor (U8.4b, from U8.0's finding).

Why this module exists
------------------------
The rent model learned rent ≈ 1.3–1.7x FMR from a 2018-19 corpus and multiplies that
ratio by *today's* FMR — a design (§2) that holds only while the FMR schedule tracks the
market it prices. U8.0 measured that it has not: since the corpus vintage, the FMR
schedule rose +51.9% against market rent's +33.5% (Zillow ZORI, the independent series
decision #16 adopted), so the ratio's denominator outran its market by ~18.5 points and
an uncorrected estimate reads high — ~13% on aggregate, and anywhere from −4% (reads
slightly low) to ~+25% depending on the ZIP, because the drift is not uniform.

This module computes the correction: the subject ZIP's own measured

    factor = (ZORI today / FMR today) ÷ (ZORI at corpus vintage / FMR at corpus vintage)
           = (ZORI today / ZORI vintage) × (FMR vintage / FMR today)

**Per-ZIP rather than one global scalar, because U8.0 measured the drift ranging from
+3.6% to −20% across ZCTAs** — a single factor would be right on average and wrong
nearly everywhere. Worth stating plainly (the task list already does): a per-ZIP factor
is re-anchoring on ZORI, expressed at prediction time instead of training time; the
structural version is §6 cut-list item 6, now U11's Q1.

The algebra is worth seeing once: corrected estimate = ratio × FMR_today × factor
= ratio × FMR_vintage × (ZORI_today / ZORI_vintage) — i.e. re-anchor the model at the
vintage schedule it was trained against, then grow by the *market's* observed growth
rather than the schedule's.

**Both FMR ends must resolve at the same spatial grain** (the subject's anchor grain:
ZIP where the model's training rows were ZIP-anchored, county otherwise), or the ratio
mixes two denominators — the defect class U8.2b and the anchor-resolution gate in
`agents/valuation_rent.py` both exist to prevent. A grain mismatch between the two
fiscal years returns unavailable rather than a silently mixed factor.

Flag-worthy conditions are **returned as data**, never raised here: `DriftResult`
carries the factor or the reason there is none, plus the provenance the disclosure
needs (which months were read, whether the vintage was substituted, how stale the
series is). Converting that into `Flag` objects is the Valuation agent's job — the same
split `tools/redfin_data.py` documents for `GrowthBands`.

The ZORI panel is an on-disk lookup (`data/`, re-fetchable from Zillow's stable URL via
`tools/zori.download()` — that is the refresh path), never a live fetch at inference
time. Staleness is measured against the series' own last observed month and disclosed
past `config.RENT_DRIFT_MAX_ZORI_STALENESS_MONTHS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import pandas as pd

import config
from tools import hud_fmr, zori
from tools.model.rent_model import fmr_fiscal_year


@dataclass(frozen=True)
class DriftResult:
    """The factor, or the reason there is none — plus everything a disclosure needs."""

    factor: Optional[float] = None
    unavailable_reason: Optional[str] = None

    zip_code: Optional[str] = None
    zori_vintage_month_used: Optional[str] = None
    zori_vintage_substituted: bool = False
    zori_latest_month: Optional[str] = None
    zori_staleness_months: Optional[int] = None
    market_growth_pct: Optional[float] = None      # ZORI, vintage -> latest
    schedule_growth_pct: Optional[float] = None    # FMR, vintage FY -> current FY
    fmr_vintage_year: Optional[int] = None
    fmr_current_year: Optional[int] = None

    @property
    def applied(self) -> bool:
        return self.factor is not None


def _months_between(a: str, b: str) -> int:
    first, second = pd.Timestamp(a), pd.Timestamp(b)
    return abs((first.year - second.year) * 12 + (first.month - second.month))


@lru_cache(maxsize=1)
def _zori_panel() -> Optional[pd.DataFrame]:
    """The ZORI panel, loaded once per process — ~10 MB and every estimate reads it."""
    try:
        return zori.load()
    except (FileNotFoundError, OSError):
        return None


def compute_drift(
    zip_code: Optional[str],
    county_fips: str,
    bedrooms: int,
    anchor_zip: Optional[str],
    client: Optional[hud_fmr.HudFmrClient] = None,
) -> DriftResult:
    """The subject's drift factor, or the reason it cannot be computed.

    `zip_code` locates the subject in the ZORI panel (its market); `anchor_zip` is the
    ZIP the FMR anchor actually used, or None for a county-grain anchor — passed
    separately because the two are different questions: ZORI is always ZIP-grain, while
    the FMR ratio must reproduce the anchor's own grain at both fiscal years.
    """
    if not zip_code:
        return DriftResult(unavailable_reason=(
            "the subject resolved to no ZIP code, and the market-rent index is "
            "published per ZIP"
        ))

    panel = _zori_panel()
    if panel is None:
        return DriftResult(unavailable_reason=(
            "the market-rent index file is not present on this machine"
        ), zip_code=zip_code)

    series = zori.series_for_zip(panel, zip_code)
    if series is None:
        return DriftResult(unavailable_reason=(
            f"the market-rent index does not cover ZIP {zip_code}"
        ), zip_code=zip_code)

    vintage = zori.nearest_observed(series, config.ZORI_VINTAGE_MONTH)
    if vintage is None:
        return DriftResult(unavailable_reason=(
            f"the market-rent index has no observed values for ZIP {zip_code}"
        ), zip_code=zip_code)
    vintage_month, zori_vintage = vintage
    substitution = _months_between(vintage_month, config.ZORI_VINTAGE_MONTH)
    if substitution > config.ZORI_MAX_VINTAGE_SUBSTITUTION_MONTHS:
        # The same limit the U8.0 evidence run applied, for the same reason: a read
        # substituted from the far side of the 2021-22 surge imports the surge into the
        # "before" figure and understates the very drift being corrected.
        return DriftResult(unavailable_reason=(
            f"the market-rent index's coverage of ZIP {zip_code} begins too long after "
            f"the training data's vintage for a before/after comparison"
        ), zip_code=zip_code)

    observed = series.dropna()
    latest_month = str(observed.index[-1])
    zori_latest = float(observed.iloc[-1])
    staleness = _months_between(latest_month, str(pd.Timestamp.now().date()))

    vintage_fy = fmr_fiscal_year(pd.Timestamp(config.ZORI_VINTAGE_MONTH))
    client = client or hud_fmr.HudFmrClient()
    try:
        current = client.get_fmr_for_bedroom(county_fips, bedrooms, zip_code=anchor_zip)
        past = client.get_fmr_for_bedroom(
            county_fips, bedrooms, year=vintage_fy, zip_code=anchor_zip
        )
    except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError) as exc:
        return DriftResult(unavailable_reason=(
            f"the FY{vintage_fy} rent schedule needed for the before/after comparison "
            f"could not be retrieved ({type(exc).__name__})"
        ), zip_code=zip_code)

    def _grain(anchor: dict) -> str:
        return "zip" if anchor["is_safmr"] and not anchor["used_msa_fallback"] else "county"

    if _grain(current) != _grain(past):
        # e.g. a ZIP schedule exists today but not at the vintage: the ratio would mix a
        # ZIP-level numerator year with a county-level denominator year.
        return DriftResult(unavailable_reason=(
            "the current and vintage rent schedules resolve at different spatial "
            "grains for this subject, so their ratio would mix two baselines"
        ), zip_code=zip_code)

    fmr_current, fmr_vintage = float(current["rent"]), float(past["rent"])
    if fmr_current <= 0 or fmr_vintage <= 0 or zori_vintage <= 0:
        return DriftResult(unavailable_reason=(
            "a non-positive rent figure in one of the four inputs"
        ), zip_code=zip_code)

    factor = (zori_latest / zori_vintage) * (fmr_vintage / fmr_current)
    if not config.RENT_DRIFT_FACTOR_MIN <= factor <= config.RENT_DRIFT_FACTOR_MAX:
        # The same philosophy as RENT_MODEL_MIN/MAX_RATIO: U8.0 measured per-ZCTA drift
        # spanning roughly +4% to −20%, so a factor far outside that neighborhood is a
        # join or data defect, and refusing beats silently shipping it.
        return DriftResult(unavailable_reason=(
            f"the computed factor ({factor:.2f}) falls outside the plausible band, "
            f"which indicates a data defect rather than real drift"
        ), zip_code=zip_code)

    return DriftResult(
        factor=factor,
        zip_code=zip_code,
        zori_vintage_month_used=vintage_month,
        zori_vintage_substituted=substitution > 0,
        zori_latest_month=latest_month,
        zori_staleness_months=staleness,
        market_growth_pct=(zori_latest / zori_vintage - 1.0) * 100.0,
        schedule_growth_pct=(fmr_current / fmr_vintage - 1.0) * 100.0,
        fmr_vintage_year=vintage_fy,
        fmr_current_year=int(current["year"]),
    )
