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

What U6 builds here, per §2 and §6:

1. Tree-of-Thought branching over optimistic / base / pessimistic rent-growth and
   appreciation paths, grounded in the measured bands rather than invented spreads.
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
