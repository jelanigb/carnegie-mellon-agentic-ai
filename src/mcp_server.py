"""MCP server exposing this project's read-only reference data (decision #13).

**What this is for, and — just as importantly — what it is not for.**

Two consumers motivated this server, and neither of them is the pipeline itself:

1. **The U6 Tree-of-Thought evaluator.** Scoring a candidate forecast branch means
   pulling evidence that depends on the branch: a hypothesis claiming aggressive
   appreciation warrants the observed historical distribution, one implying rent well
   above market warrants the FMR record. Which checks are worth running is a property of
   the branch, not a fixed battery, so the evaluator selects its own evidence from the
   tool descriptions below. Those descriptions are load-bearing — they are what an LLM
   reads to decide whether a tool applies — and are written for that reader.
2. **A human, during U8 evaluation and the Week 7 demonstration.** Any MCP host can now
   interrogate the same reference layer the pipeline uses, which replaces writing a
   one-off script every time a number needs checking.

**The honest accounting, per §7 decision #13: the pipeline does not require this.**
`tools/hud_fmr.py` and `tools/redfin_data.py` are in-process Python functions, and
LangChain's `@tool` decorator would give the evaluator dynamic tool selection with no
protocol hop. What MCP adds is portability and that second consumer — a real benefit and
a modest one. Recording it that way is deliberate: the alternative was overstating a
tool's necessity to satisfy a rubric, which is the error Transparent Degradation exists
to prevent, one level up (§8).

**This server is strictly read-only.** Every tool is annotated `readOnlyHint=True`, and
nothing here writes to state, the Chroma index, or any cache the pipeline depends on for
correctness. That is a deliberate boundary rather than an accident of scope: an agent
surface that can mutate the evidence base is a different security proposition than one
that can only read it, and this project's evidence base is what its credibility rests on.

**Transparent Degradation applies to tool returns as much as to agent outputs.** No tool
here raises on a flag-worthy condition or silently substitutes a fallback. Each returns
the provenance a caller would need to disclose what it got — whether an FMR record fell
back to the MSA-level entry, whether a growth band rests partly on the 2020–2022 anomaly,
how many observations a band was computed from. A caller that wants to ignore that has to
ignore it explicitly.

Run it directly for stdio transport:

    .venv/bin/python mcp_server.py

**No `query_comps` tool.** A U6 TODO deferred one pending a Critic rent-vs-comp check
that might need it. That check was never built in the Critic — Q1 (U7) resolved that the
Critic consumes `RENT_DIVERGES_FROM_COMPS` from `agents/valuation_rent.py` rather than
re-deriving it, and U7.7 retired decision #12's Critic ToT half entirely on evidence: the
checks that shipped are pure functions over `state.flags`, with no LLM evaluator to call
a tool in the first place. `docs/history/decision_log.md` #12.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

import config
from tools import redfin_data
from tools.hud_fmr import HudFmrApiError, HudFmrClient
from tools.logging_setup import library_logging_unchanged

# **Constructing the server reconfigures logging for the whole process.**
# `MCPServer.__init__` calls the SDK's own `configure_logging()`, which runs
# `logging.basicConfig(level="INFO", handlers=[RichHandler(...)])` — so importing this
# module for its tool registry, which `agents/scenario_forecast.py` does on every run,
# would otherwise decide how every other library in the process reports. Roughly 190
# lines of `httpx` and `sentence-transformers` chatter print before the report as a
# result. Wrapped rather than worked around downstream, because the change is made here
# and an entrypoint undoing it later would be repairing a cause it cannot see.
# `LIBRARY_LOGS=true` keeps it — see `tools/logging_setup.py`.
with library_logging_unchanged():
    server = MCPServer(
        name=config.MCP_SERVER_NAME,
        instructions=(
            "Read-only reference data for US residential rent and multi-family sale-price "
            "analysis. Use get_fmr for HUD Fair Market Rent (a rent level a county's market "
            "supports), and get_growth_bands / get_appreciation_history for observed "
            "multi-family sale-price appreciation. Coverage is limited: appreciation data "
            "exists only for the metros returned by list_available_metros, while FMR covers "
            "any US county given its FIPS code."
        ),
    )

_READ_ONLY = ToolAnnotations(readOnlyHint=True)

# Loading the Redfin extract parses a multi-year CSV, so it is done once per process and
# reused. Safe to cache because the extract is a static file on disk, not a live feed —
# unlike the FMR client's cache, which fronts an API and is invalidated per fiscal year.
_redfin_frame: Optional[pd.DataFrame] = None
_fmr_client: Optional[HudFmrClient] = None


def _get_redfin_frame() -> pd.DataFrame:
    global _redfin_frame
    if _redfin_frame is None:
        _redfin_frame = redfin_data.load_redfin()
    return _redfin_frame


def _get_fmr_client() -> HudFmrClient:
    global _fmr_client
    if _fmr_client is None:
        _fmr_client = HudFmrClient()
    return _fmr_client


@server.tool(annotations=_READ_ONLY)
def list_available_metros() -> dict[str, Any]:
    """List the metros with multi-family appreciation data available.

    Call this before get_growth_bands or get_appreciation_history if you are unsure
    whether a metro is covered. Coverage is deliberately narrow — three metros selected
    for listing density and sales volume — so a metro absent from this list has no
    appreciation data at all rather than sparse data.
    """
    return {
        "metros": list(redfin_data.TARGET_METROS.keys()),
        "note": (
            "Appreciation coverage is limited to these metros. FMR (get_fmr) covers any "
            "US county and is not restricted to this list."
        ),
    }


@server.tool(annotations=_READ_ONLY)
def get_fmr(
    county_fips: str,
    year: Optional[int] = None,
    zip_code: Optional[str] = None,
) -> dict[str, Any]:
    """Get HUD Fair Market Rent for a county: the rent level its market supports, by
    bedroom count.

    Use this to check whether a rent figure is plausible for its market. FMR is the
    40th-percentile rent, **not** the median, so a subject rent moderately above FMR is
    normal rather than suspect — treat a large multiple as the signal, not any excess.

    Args:
        county_fips: HUD's 10-digit entity id for the county (not the 5-digit Census
            FIPS). Obtainable from the pipeline's county resolution.
        year: Fiscal year. Defaults to the most recent HUD publishes. Pass it explicitly
            when comparing against dated data — a corpus listing from 2019 should be
            checked against 2019 FMR, not today's.
        zip_code: Only meaningful in Small Area FMR (SAFMR) counties, which publish
            per-ZIP rents. Ignored elsewhere. Whether a county is SAFMR varies **by
            year**, not just by county, so do not assume it from a prior call.

    Returns rents by bedroom count plus provenance: `is_safmr`, and `used_msa_fallback`
    (true when a SAFMR county was queried without a matching ZIP, so the figure is
    metro-wide rather than ZIP-specific).
    """
    try:
        result = _get_fmr_client().get_fmr(
            entityid=county_fips, year=year, zip_code=zip_code
        )
    except HudFmrApiError as exc:
        return {
            "available": False,
            "reason": f"HUD FMR API error: {exc}",
            "county_fips": county_fips,
        }
    except (FileNotFoundError, RuntimeError) as exc:
        # Missing or unreadable credentials. Reported as data rather than raised, so a
        # caller sees an unavailable tool instead of a dead server.
        return {
            "available": False,
            "reason": f"HUD FMR client unavailable: {exc}",
            "county_fips": county_fips,
        }

    return {
        "available": True,
        "county_fips": result.entityid,
        "area_name": result.area_name,
        "year": result.year,
        "rents_by_bedroom": result.rents,
        "is_safmr": result.is_safmr,
        "zip_requested": result.zip_requested,
        "used_msa_fallback": result.used_msa_fallback,
    }


@server.tool(annotations=_READ_ONLY)
def get_growth_bands(
    metro: str,
    exclude_anomalous_period: bool = False,
) -> dict[str, Any]:
    """Get observed optimistic / base / pessimistic annual appreciation for a metro's
    2–4 unit multi-family sales.

    Use this to test whether a forecast growth rate is defensible. The bands are measured
    from actual sales, not modeled: base is long-run mean year-over-year growth,
    optimistic the best sustained 12-observation stretch actually observed, pessimistic
    the worst. **A projection outside these bands is a claim the market has never done
    this** — sometimes defensible, never unremarkable.

    Args:
        metro: One of list_available_metros().
        exclude_anomalous_period: Recompute with 2020–2022 removed. Call this tool both
            ways when the treatment of that window is itself in question; the two results
            are the evidence for choosing, and either choice is defensible as long as the
            result says which was made.

    Returns the three bands plus the provenance needed to disclose them:
    `includes_anomalous_period`, `anomalous_period_share`,
    `optimistic_stretch_in_anomalous_period` (true when the optimistic band rests on the
    2021 spike), `n_yoy_observations`, and `stdev_yoy_pct` for dispersion.
    """
    try:
        series = redfin_data.get_appreciation_series(_get_redfin_frame(), metro=metro)
    except KeyError:
        return {
            "available": False,
            "reason": f"No appreciation data for metro {metro!r}.",
            "available_metros": list(redfin_data.TARGET_METROS.keys()),
        }

    bands = redfin_data.compute_growth_bands(
        series, exclude_anomalous_period=exclude_anomalous_period
    )

    return {
        "available": True,
        "metro": bands.metro,
        "source": bands.source_description,
        "base_yoy_pct": bands.base_yoy_pct,
        "optimistic_yoy_pct": bands.optimistic_yoy_pct,
        "pessimistic_yoy_pct": bands.pessimistic_yoy_pct,
        "median_yoy_pct": bands.median_yoy_pct,
        "stdev_yoy_pct": bands.stdev_yoy_pct,
        "n_yoy_observations": bands.n_yoy_observations,
        "includes_anomalous_period": bands.includes_anomalous_period,
        "anomalous_period_share": bands.anomalous_period_share,
        "anomalous_period_excluded": bands.anomalous_period_excluded,
        "optimistic_stretch_in_anomalous_period": (
            bands.optimistic_stretch_in_anomalous_period
        ),
        "sustained_window_periods": bands.sustained_window_periods,
        "periods_dropped_below_floor": bands.periods_dropped_below_floor,
    }


@server.tool(annotations=_READ_ONLY)
def get_appreciation_history(
    metro: str,
    periods: int = config.MCP_APPRECIATION_HISTORY_PERIODS,
) -> dict[str, Any]:
    """Get the recent month-by-month appreciation series behind a metro's growth bands.

    Use this when the bands alone are not enough — to see whether recent movement is
    trending against the long-run average, or to check where in the series an unusual
    band came from. get_growth_bands is the summary; this is the underlying series.

    Args:
        metro: One of list_available_metros().
        periods: How many of the most recent months to return.

    Each row carries the period, the smoothed rolling median sale price, and
    year-over-year percent change. Early rows of any series have a null `yoy_pct` because
    a year-over-year figure needs twelve prior months to exist.
    """
    try:
        series = redfin_data.get_appreciation_series(_get_redfin_frame(), metro=metro)
    except KeyError:
        return {
            "available": False,
            "reason": f"No appreciation data for metro {metro!r}.",
            "available_metros": list(redfin_data.TARGET_METROS.keys()),
        }

    tail = series.frame.tail(periods)
    rows = [
        {
            "period": period.strftime("%Y-%m"),
            "rolling_median_sale_price": (
                None if pd.isna(row["rolling_median"]) else float(row["rolling_median"])
            ),
            "yoy_pct": (
                None if pd.isna(row["yoy_pct"]) else float(row["yoy_pct"])
            ),
        }
        for period, row in tail.iterrows()
    ]

    return {
        "available": True,
        "metro": series.metro,
        "source": series.source_description,
        "rows": rows,
        "n_periods_total": series.n_periods,
        "first_period": series.first_period.strftime("%Y-%m"),
        "last_period": series.last_period.strftime("%Y-%m"),
        "window_periods": series.window_periods,
        "periods_dropped_below_floor": series.periods_dropped_below_floor,
    }


if __name__ == "__main__":
    server.run()
