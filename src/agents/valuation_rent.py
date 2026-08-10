"""Valuation & Rent agent — **U2 STUB**. The real implementation is U5.

**This stub deliberately produces no number at all**, and that is the interesting
decision in the file. The obvious placeholder — average the retrieved comps' rents and
call it an estimate — was rejected because §8 states a hard invariant: *never let
unanchored Kaggle dollar figures reach the Summarizer; every rent number passes through
FMR normalization first.* A comps mean is exactly such a figure. The corpus is a
2018–19 scrape, so its raw mean is a 2018 number that would appear in a 2026 report
wearing no date, which is the precise failure §2's rent-anchoring design exists to
prevent. A stub is not a license to violate an invariant that the rest of the system is
built around; it is a placeholder for work that will honor it.

The consequence is visible and intended: the walking skeleton's report says the rent
and value sections are unbuilt. That is a true statement about the build. A number with
an invisible eight-year vintage error would have been a false one.

What U5 builds here, per §2:

1. Train the regression on rent normalized by each row's own local HUD FMR
   (rent ÷ FMR-for-that-county-and-year), so the model learns a structural ratio rather
   than a dollar level that ages.
2. At prediction time, multiply the predicted ratio by *today's* FMR for the subject's
   county via `tools/hud_fmr.py`, producing a current-dollar figure anchored to a dated
   public reference.
3. Raise `rent_anchored_to_fmr` (info) on every estimate taking that path, plus
   `fmr_unavailable_for_county` (warn) when the crosswalk misses and a coarser fallback
   is used, and `fmr_bedroom_cap_exceeded` (info) for 5+ bedroom units, which HUD's
   schedule does not reach.
4. The LLM fallback path (`llm_rent_fallback_used`), which is item 2 on §6's cut list —
   documented as designed-but-unbuilt if the schedule slips.

Reason/Act/Observe/Decide (the loop U5 implements):

- **Reason.** Decide whether the retrieved comp set and the subject's own terms support
  a model-based estimate, or whether coverage gaps force the fallback path.
- **Act.** Predict the rent-to-FMR ratio from the subject's features, then anchor it
  against the current FMR for `deal_terms.county_fips`.
- **Observe.** Compare the anchored figure against the comp set's own distribution;
  a wide divergence is signal, not noise.
- **Decide.** Emit the estimate with the flags naming every approximation it rests on —
  the anchoring mechanism, any FMR fallback, any bedroom cap — so the report can
  disclose how the number was reached rather than only what it is.
"""

from __future__ import annotations

from state import DealState

AGENT = "valuation_rent"


def valuation_rent_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state.

    Returns only its stub marker. Writing `rent_estimate=None` explicitly would be
    redundant — it is already the default — and would violate §3's rule that a node
    returns only the keys it actually changed.
    """
    return {"stub_nodes": [AGENT]}
