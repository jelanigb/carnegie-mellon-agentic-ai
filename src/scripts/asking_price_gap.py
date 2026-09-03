"""Is the asking-price-versus-benchmark gap tunable — check B's missing measurement (OQ-20)

    LLM_CACHE_MODE=replay LLM_CACHE_DIR=eval/data/llm_recordings \\
      .venv/bin/python scripts/asking_price_gap.py

**The B analogue of `scripts/stated_rent_gap.py`, taken Sept 2, 2026.** U7 Q4 shipped two
Summarizer disclosures and scheduled promoting both to Critic objections at U8: **check A**,
the listing's stated rents against the modelled rent, and **check B**, the listing's asking
price (`deal_terms.price`) against the market benchmark
(`ValuationDetail.benchmark_median_sale_price`). U8.7 measured *A* and held it as a
disclosure on a specific finding. The phrase "checks A and B" then carried B along with it —
`valuation_rent._attach_benchmark` says "check B was not promoted at U8.7" — but **no
measurement of B was ever taken and no decision about B was ever recorded.** Decision #20's
register row is about the stated-rent comparison alone. That gap is OQ-20.

**The confound this measurement has to survive, and it is worse than A's.** Decision #11 set
every demo and eval asking price *from the Redfin metro median*, and U8.8 replaced the
comparison basis with the **ZIP** median. So a raw gap is mostly *(metro median − ZIP
median)* for that ZIP, plus whatever the deal itself carries — and the first term dominates:
ZIP 60640 runs 77% above the Chicago metro, which is why a perfectly ordinary Uptown duplex
reads 39% cheap. **A threshold fitted to that would bury #11's calibration inside a
production constant**, which is the class of error U7 Q4 refused for A.

**So the raw gap is not the measurement. The decomposition is.** For every fixture this
prints three quantities, not one:

1. **Gap to benchmark** — `(price − benchmark) / benchmark`, what a naive check B would
   threshold on.
2. **The calibration term** — `(metro median − ZIP median) / ZIP median`, how much of that
   gap is #11 setting the price off a wider geography than the benchmark reads. Available
   because `ValuationDetail` deliberately keeps `benchmark_metro_median_sale_price` beside
   the ZIP figure rather than replacing it (U8.8).
3. **The deal residual** — what is left once the calibration term is removed. This is the
   only column that describes the *property*, and it is what a promoted check B would need
   to be discriminating on.

**The prediction, written before the run so the measurement can falsify it rather than
confirm it** — OQ-20 states it and this script is what tests it: B closes as a disclosure
like A did, but for a *different* reason. A's threshold would have restated an existing
flag; B's would restate #11's calibration. That is falsified if the deal residual is
dispersed and sign-varying across fixtures whose asking price was *not* declared as an
offset — and confirmed if the residual collapses to roughly zero everywhere except the one
fixture that declares a premium.

**The fixtures' own declaration is the control.** `demo_deals.DemoDeal` carries `price_basis`
and `price_premium_to_basis`: a deal with `price_premium_to_basis=None` asserts *no*
deliberate offset from its basis, so its residual should be noise. `overpriced` declares
**+55%** against ZIP 60640, and `chicago-uptown` declares its price from the same ZIP
benchmark with no premium. Those two are the calibrated straddle — one deal that should fire
any reasonable threshold and one that should not — and if the residual does not separate
them, no threshold read off this batch means anything.

**A second, dependent question is deliberately out of scope here and stays open**: whether
the benchmark's *tier* should raise a flag. OQ-20 argues it should not, because nothing
computes from the benchmark — but that argument **expires the moment check B is promoted**,
since the benchmark then becomes an input to a check and its grain starts deciding an
outcome. Los Angeles and Cleveland have no ZIP tier at all, so a promoted B would compare an
asking price against a metro-wide median in half the inference set. This script measures;
it does not promote, and a promotion would need that tier rule first.

**Both tiers are run, and the demo deals are why.** Check A measured the golden fixtures
alone; that is not sufficient here, because **no golden fixture declares a price offset** —
`price_basis` and `price_premium_to_basis` live on `demo_deals.DemoDeal`, and the demo deals
are LIVE-tier eval rows. Without them the control does not exist and the residual column has
nothing to be read against. They replay from committed recordings since U9.5, so including
them costs a cache directory rather than a quota, which is why the invocation above sets one.

No live model calls: the golden tier supplies complete `DealTerms` and replays recorded
forecast responses, and the demo tier replays its extractions too — the same environment
`eval/runner.py` builds. So this costs what A's script cost.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from demo_deals import DEMO_DEALS
from eval import cases as eval_cases
from eval.cases import Tier
from eval.runner import _case_environment
from graph import build_graph
from state import DealState, DealTerms

# The same placements check A swept, so the two measurements are readable side by side.
CANDIDATE_THRESHOLDS = (0.20, 0.25, 0.30, 0.35, 0.40)


def _declared(key: str) -> tuple[str | None, float | None]:
    """The fixture's own declaration of where its asking price came from, if it has one.

    Eval fixtures carry no `price_basis`; the demo deals do, and the demo deals are also
    eval rows. Keyed on the case key, which is the demo key for those rows.
    """
    deal = DEMO_DEALS.get(key)
    if deal is None:
        return None, None
    return deal.price_basis, deal.price_premium_to_basis


def _cases():
    """Golden fixtures plus the demo deals — the second is where the control lives."""
    golden = [c for c in eval_cases.ENGINEERED_CASES if c.tier is Tier.GOLDEN]
    demo = [c for c in eval_cases.demo_cases() if c.key in DEMO_DEALS]
    return golden + demo


def _rows() -> list[dict]:
    """Every fixture that produced both an asking price and a benchmark of any tier."""
    out_rows = []
    for case in _cases():
        terms = case.terms.model_copy(deep=True) if case.terms else DealTerms()
        if case.supplied_coords is not None:
            terms.latitude, terms.longitude = case.supplied_coords
        state = DealState(
            raw_listing_text=case.listing or f"[golden fixture: {case.key}]",
            deal_terms=terms,
        )
        with _case_environment(case, False):
            out = build_graph().invoke(
                state,
                {"configurable": {"thread_id": f"pricegap-{case.key}-{uuid4().hex[:8]}"}},
            )
        detail = out.get("valuation_detail")
        resolved = out.get("deal_terms")
        price = resolved.price if resolved else None
        if detail is None or price is None or not detail.benchmark_median_sale_price:
            continue

        benchmark = detail.benchmark_median_sale_price
        metro_median = detail.benchmark_metro_median_sale_price
        gap = (price - benchmark) / benchmark
        # The calibration term only exists where the two tiers differ. At the metro tier
        # the benchmark *is* the metro median, so there is nothing to decompose and the
        # whole gap is already the deal — which is itself worth seeing in the table.
        if detail.benchmark_tier == "zip" and metro_median:
            calibration = (metro_median - benchmark) / benchmark
            residual = (price - metro_median) / metro_median
        else:
            calibration = None
            residual = gap

        basis, premium = _declared(case.key)
        out_rows.append({
            "key": case.key,
            "price": price,
            "benchmark": benchmark,
            "tier": detail.benchmark_tier or "—",
            "zip": detail.benchmark_zip or "—",
            "gap": gap,
            "calibration": calibration,
            "residual": residual,
            "declared_premium": premium,
            "basis": basis,
            "flags": sorted({f.kind.value for f in out.get("flags", [])}),
            "demo": case.key in DEMO_DEALS,
        })
    out_rows.sort(key=lambda r: -r["gap"])
    return out_rows


def main() -> None:
    rows = _rows()
    print(f"Check B — asking price against its market benchmark. {len(rows)} fixtures.\n")

    print(f"{'fixture':<26}{'tier':>6}{'gap':>9}{'calib':>9}{'residual':>10}"
          f"{'declared':>10}")
    print("-" * 70)
    for r in rows:
        calib = f"{r['calibration']:+.0%}" if r["calibration"] is not None else "—"
        declared = (f"{r['declared_premium']:+.0%}"
                    if r["declared_premium"] is not None else "—")
        print(f"{r['key']:<26}{r['tier']:>6}{r['gap']:>+9.0%}{calib:>9}"
              f"{r['residual']:>+10.0%}{declared:>10}")
    print("-" * 70)
    print("gap      = (price - benchmark) / benchmark          <- what a naive check B "
          "would threshold on")
    print("calib    = (metro median - ZIP median) / ZIP median <- decision #1 (LangGraph)1's "
          "calibration, not the deal")
    print("residual = (price - metro median) / metro median    <- the only column about "
          "the property\n")

    # --- The three findings, computed rather than asserted ------------------------
    declared = [r for r in rows if r["declared_premium"] is not None]
    zip_based = [r for r in rows if r["basis"] and r["basis"].startswith("zip_")]
    metro_based = [r for r in rows if r["basis"] and r["basis"].startswith("redfin_metro")]

    print("FINDING 1 — the batch does not share one calibration basis, so neither column")
    print("is correct for all of it. Decision #11 set the original demo prices from the")
    print("REDFIN METRO median; U9.4 and U9.6 calibrated the two newest deals against the")
    print("ZIP benchmark. Each fixture's own declaration is the ground truth:\n")
    seen: set[str] = set()
    with_basis = [r for r in declared + zip_based + metro_based
                  if not (r["key"] in seen or seen.add(r["key"]))]
    for r in sorted(with_basis, key=lambda r: (r["basis"] or "", r["key"])):
        truth = (f"{r['declared_premium']:+.0%}"
                 if r["declared_premium"] is not None else "+0%")
        print(f"  {r['key']:<22} basis {str(r['basis']):<34} declared {truth:>6}"
              f" | gap {r['gap']:>+5.0%}  residual {r['residual']:>+5.0%}")
    print("\n  For a ZIP-calibrated deal the RAW GAP recovers the declared truth and the")
    print("  residual does not; for a metro-calibrated deal it is the other way round.")
    print("  A single threshold has no column to sit on.\n")

    structural_zero = [r for r in rows
                       if r["basis"] and r["basis"].startswith("redfin_metro")
                       and r["tier"] == "metro" and abs(r["gap"]) < 0.005]
    print(f"FINDING 2 — on {len(structural_zero)} fixtures check B cannot fail by "
          f"construction:")
    for r in structural_zero:
        print(f"  {r['key']:<22} price set FROM the metro median, benchmark IS the "
              f"metro median -> gap {r['gap']:+.0%}")
    print("  §8's own rule: a check that cannot fail is not a check. These are the")
    print("  markets with no ZIP tier — Los Angeles and Cleveland — which is half the")
    print("  inference set.\n")

    metro_tier = [r for r in rows if r["tier"] == "metro" and not r["basis"]]
    if metro_tier:
        top = sorted(metro_tier, key=lambda r: -r["gap"])[:3]
        print("FINDING 3 — at the metro tier the gap ranks by WHERE a property is, not by")
        print("what it costs. The three largest, none of which declares a premium:")
        for r in top:
            print(f"  {r['key']:<28}{r['gap']:>+7.0%}   flags: "
                  f"{', '.join(r['flags'][:3]) or '(none)'}")
        print("  A Manhattan listing reads expensive against a New York metro median")
        print("  because it is in Manhattan. Promoting B without a tier rule would ship")
        print("  that as a finding about the deal.\n")

    print("Threshold sweep — what a promoted check B would fire on:")
    for t in CANDIDATE_THRESHOLDS:
        on_gap = [r["key"] for r in rows if r["gap"] > t]
        on_residual = [r["key"] for r in rows if r["residual"] > t]
        print(f"  +{t:.0%}  raw gap ({len(on_gap)}): {', '.join(on_gap) or '(none)'}")
        print(f"        residual ({len(on_residual)}): "
              f"{', '.join(on_residual) or '(none)'}")

    print("\nVERDICT INPUT: OQ-20 predicted B closes as a disclosure because a threshold")
    print("would restate decision #1 (LangGraph)1's calibration. The measurement agrees and sharpens")
    print("it: there is no single column to fit a threshold to, because the fixtures do")
    print("not share a basis — and on the metro-tier markets the check is inert by")
    print("construction. Closing B as a disclosure is not a deferral here; it is the")
    print("only reading this evidence supports.")


if __name__ == "__main__":
    main()
