"""Scenario/Forecast agent — **U2 STUB**. The real implementation is U6.

Stubbed rather than partially built for a structural reason, not just a scheduling one:
this agent's inputs do not exist yet. §5 has Scenario consuming `rent_estimate` and
`value_estimate`, both of which the U2 Valuation stub deliberately declines to produce
(see `valuation_rent.py`). Projecting growth bands onto a missing base value would
produce three scenarios about nothing.

Note that the *data* half is already built and verified: `tools/redfin_data.py` loads
the metro extract, applies the $10,000 floor, computes the rolling-3 window, and
derives optimistic/base/pessimistic growth bands with the anomalous-period segmentation
fix from §2. U6 is the reasoning layer over it, not the data layer.

**⚠️ The original premise for the rent half of this agent was disproved on Aug 22, 2026,
before it was built.** §1 and §2 specified Tree-of-Thought branching over rent-growth and
appreciation scenarios *"informed by metro-level housing trend data"* — that is, inferring
rent growth from Redfin's sale-price series. Measured, rent growth and price growth are
**negatively** correlated across the inference trio (pooled r = −0.309; −0.135 Chicago,
−0.226 Los Angeles, −0.530 Cleveland over FY2019–2026), with price outrunning rent by 8.9
points in the 2021–22 window §2 already flagged. A rent forecast driven by that series
would point the wrong way. Do not build the original spec.

**The two quantities are forecast separately, from sources that match each.** Redfin
remains correct for *price* appreciation, which is what it measures. Rent growth comes
from HUD FMR's published history — ten fiscal years, county and ZIP resolution, served by
the client this project already caches, and consistent with the anchoring design by
construction: the rent estimate is `ratio × FMR`, so projecting the FMR anchor forward
while holding the structural ratio constant forecasts rent by the same mechanism that
produced the estimate. Zillow ZORI is the independent check on whether those bands match
market-observed rent growth; FMR is administrative and shows methodology jumps (Chicago
+19.0% in FY2024, Los Angeles +14.5%) that a base case must screen for and disclose.

What U6 builds here, per §2 and §6:

1. Tree-of-Thought branching over optimistic / base / pessimistic paths for **rent growth
   and price appreciation as separate quantities**, each grounded in measured bands from
   its own source rather than invented spreads or a blended series.
2. `appreciation_source` recorded on state — `metro_multifamily` for the tier-1 default,
   `metro_all_residential` for the tier-3 fallback. (`zip_multifamily` is tier 2,
   deferred in §2 and not produced by this build; it stays in the Literal so the
   deferral is legible in the type.)
3. `anomalous_period_included` (info) wherever the 2020–2022 window feeds an average or
   a band, so a "base case" resting partly on a near-zero-rate stretch says so.

Reason/Act/Observe/Decide (the loop U6 implements):

- **Reason.** Determine which appreciation tier the subject's metro can actually
  support at adequate sample size, and which historical window is representative.
- **Act.** Branch into three scenarios, each carrying its own growth assumption drawn
  from the measured series rather than from a rule of thumb.
- **Observe.** Check each branch's implied outcome against the observed historical
  range — a projection outside anything the market has ever done is a defect in the
  reasoning, not a bold forecast.
- **Decide.** Emit the three branches with the source tier and any anomalous-period
  contamination flagged, so a reader can see which years the base case rests on.
"""

from __future__ import annotations

from state import DealState

AGENT = "scenario_forecast"


def scenario_forecast_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    return {"stub_nodes": [AGENT]}
