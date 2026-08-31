"""U8.M — is `config.MAX_REWORKS = 2` the right budget, or just the first one written?

**Why this exists.** `MAX_REWORKS` shipped from U1 carrying `PROVISIONAL — tune in U8`,
and U8 closed without tuning it: the unit built the case that *exercises* the bound
(`chicago-geocoder-outage`, which spends both laps and escalates on the budget) but never
asked whether a different budget would decide anything differently. A constant whose
marker names a closed unit reads as scheduled work and is really unowned work, which is
the failure mode `engineering_standards.md` records this sweep against.

**Why the replay tier alone is the right scope, and this is a measurement rather than a
convenience.** The budget can only matter to a case that reworks at all, a rework happens
only when the Critic raises a **retryable** objection, and exactly one objection in this
system is retryable — I3 on a geocoder outage, where re-running the Extractor may reach
the Census service on a later pass. Every other objection describes something a second
pass cannot change: a thin market stays thin, an address with no street number stays
unresolvable. No golden case raises the retryable one — every golden row in
`eval/results/results.md` records **0 reworks** — so the golden tier is provably inert
under this parameter, and running it would spend fifteen replays confirming arithmetic.

**What this can return, stated before it runs so the finding is falsifiable** (§8):

  * **The budget is load-bearing.** At 1 the case escalates on a *different* ground, or
    at 3 a lap resolves what two could not, and a verdict moves. Then 2 is a choice and
    this sweep is what chose it.
  * **The budget is inert across the range.** Nothing moves at 1, 2 or 3. That is the
    likely answer and it is a real one: the injected outage is permanent for the run, so
    more laps cannot reach a geocoder that is not coming back. It would say the shipped
    value is unfalsified rather than optimal — the same shape as #6's close, and it
    should be reported in those words rather than as "2 is correct".
  * **A budget above 2 is not replayable.** A third lap would need prompts the committed
    store may not contain. That is a fact about the recordings, **not** a result about the
    budget, and it is reported as its own outcome rather than folded into either of the
    above.

Run:
    .venv/bin/python scripts/rework_budget_sweep.py
    .venv/bin/python scripts/rework_budget_sweep.py --budgets 1 2 3 4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from eval.cases import Tier, all_cases
from eval.runner import CaseResult, run_case
from state import FlagKind

# The budget is only observable through a case that reworks, and only the replay tier
# contains one. Named here rather than filtered by key so that a future retryable
# objection reaching a different tier is picked up without editing this script.
SWEPT_TIER = Tier.REPLAY

DEFAULT_BUDGETS = (1, 2, 3)


def _row(result: CaseResult) -> str:
    if result.error:
        return f"{result.case.key:<28} ERROR {result.error}"
    verdict = "escalates" if result.needs_human_review else "reports  "
    budget = "budget" if result.budget_exhausted else "      "
    conf = "  n/a" if result.confidence is None else f"{result.confidence:5.2f}"
    return (f"{result.case.key:<28} {result.rework_count} reworks  conf {conf}  "
            f"{verdict}  {budget}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets", type=int, nargs="+", default=list(DEFAULT_BUDGETS))
    args = parser.parse_args()

    cases = [c for c in all_cases() if c.tier == SWEPT_TIER]
    shipped = config.MAX_REWORKS
    print(f"Sweeping MAX_REWORKS over {args.budgets}; shipped value is {shipped}.")
    print(f"{len(cases)} {SWEPT_TIER.value}-tier cases. The golden tier is inert under "
          f"this parameter — no golden case raises a retryable objection — so it is not "
          f"run; see this script's docstring.\n")

    # Keyed by budget so the comparison below reads rows against rows rather than
    # against a remembered table.
    by_budget: dict[int, list[CaseResult]] = {}
    for budget in args.budgets:
        config.MAX_REWORKS = budget
        print(f"--- MAX_REWORKS = {budget} " + "-" * 40)
        results = [run_case(case) for case in cases]
        by_budget[budget] = results
        for result in results:
            print("  " + _row(result))
        print()
    config.MAX_REWORKS = shipped

    baseline = by_budget.get(shipped)
    if baseline is None:
        print("Shipped value not in the swept range; no comparison made.")
        return

    print("=" * 60)
    print(f"Against the shipped budget of {shipped}:\n")
    for budget, results in by_budget.items():
        if budget == shipped:
            continue
        errors = [r for r in results if r.error]
        if errors:
            # A missing recording is a statement about the store, not about the budget,
            # and conflating the two would report an untested configuration as an inert
            # one — the more dangerous of the two mistakes.
            print(f"  MAX_REWORKS = {budget}: NOT REPLAYABLE — "
                  f"{len(errors)} case(s) could not run "
                  f"({errors[0].error.split(':')[0]}). A budget above the recorded lap "
                  f"count needs prompts the committed store does not hold, so this is "
                  f"a gap in the evidence rather than a result about the budget.")
            continue
        moved = [
            (b.case.key, b.observed.value, r.observed.value)
            for b, r in zip(baseline, results)
            if b.observed != r.observed
        ]
        reworks = [
            (b.case.key, b.rework_count, r.rework_count)
            for b, r in zip(baseline, results)
            if b.rework_count != r.rework_count
        ]
        print(f"  MAX_REWORKS = {budget}: {len(moved)} verdict(s) changed, "
              f"{len(reworks)} case(s) spent a different number of laps.")
        for key, was, now in moved:
            print(f"      verdict  {key}: {was} -> {now}")
        for key, was, now in reworks:
            print(f"      laps     {key}: {was} -> {now}")

    exercised = [
        r.case.key for r in baseline
        if any(f.kind == FlagKind.REWORK_LIMIT_REACHED for f in r.flags)
    ]
    print(f"\n  Cases escalating on the budget at the shipped value: "
          f"{', '.join(exercised) or 'none'}.")


if __name__ == "__main__":
    main()
