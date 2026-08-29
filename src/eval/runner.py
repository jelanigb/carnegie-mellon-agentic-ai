"""The eval harness's batch runner and its two outputs (U8.1).

Runs every case in `eval/cases.py` through the **real compiled graph** — the same
`build_graph()` `main.py` uses, not a rearrangement of it — and produces two artifacts in
`eval/results/`:

1. **The results table**, a row per case: comps, confidence, disclosures by severity,
   outcome, whether the flag the case targets actually fired, and whether the outcome
   matched the verdict declared before the run.
2. **The coverage census**, `set(FlagKind)` minus the union of every case's raised kinds.
   This is the comparison `state.FlagKind`'s docstring names as the reason it is an enum
   rather than a set of string constants, and it is what upgrades the report's claim from
   "flags fire" to "every degradation path this system defines is exercised".

**What the census could return, stated because a census that cannot fail proves nothing**
(§8). It could report full coverage; it could report gaps that are real and fixable by a
new case; or it could report gaps that *no* case can close, which is a different finding
and is why `UNREACHABLE_BY_ANY_CASE` below exists. Counting a kind nothing can raise as an
uncovered gap would misstate the harness's own reach in the pessimistic direction, exactly
as omitting it would in the optimistic one.

Run:
    .venv/bin/python -m eval.runner                 # every case
    .venv/bin/python -m eval.runner --tier golden   # replays recordings; no live calls
    .venv/bin/python -m eval.runner --case chicago
    .venv/bin/python -m eval.runner --tier golden --record   # re-record, deliberately
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterator, Optional
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from eval.cases import EvalCase, Fault, Tier, Verdict, VerdictSource, all_cases
from graph import build_graph
from state import DealState, DealTerms, FlagKind, Severity
from tools import geocoding
from tools.llm_cache import CacheMode

RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Flag kinds no case can raise, with the reason each one cannot. Subtracted from the
# census's "uncovered" set and reported separately, because they are a statement about
# the build rather than a gap in the case set.
#
# Kept as a table with reasons rather than a bare set: a kind listed here is being
# excluded from a coverage claim the report makes, and an exclusion without a reason is
# indistinguishable from a case nobody got round to writing.
# **Empty, and that is the correct end state rather than an unused mechanism.** Its first
# run held one entry — `LLM_RENT_FALLBACK_USED`, unraisable because §6's cut list item 3
# was taken and the estimator was never built. Rather than caveat the census permanently,
# the member was deleted (U8.1b), on the rule `state.FlagKind` already wrote down when it
# retired `COUNTY_FROM_PRINCIPAL_COUNTY`: a kind nothing can raise corrupts the coverage
# comparison, so it should leave the enum rather than be excused in the report.
#
# The table stays because the *next* such member will be found the same way, and because
# an empty exclusion list is itself a claim worth printing: every kind this system defines
# is one some case could reach.
UNREACHABLE_BY_ANY_CASE: dict[FlagKind, str] = {}


@dataclass
class CaseResult:
    case: EvalCase
    comps: int
    confidence: Optional[float]
    flags: list = field(default_factory=list)
    needs_human_review: bool = False
    rework_count: int = 0
    error: Optional[str] = None

    @property
    def observed(self) -> Verdict:
        return Verdict.ESCALATES if self.needs_human_review else Verdict.REPORTS

    @property
    def escalated_above_threshold(self) -> bool:
        """Escalated while the confidence score alone would have let it report.

        The one row shape worth calling out by name. `agents/critic.critic_agent`
        escalates on two independent grounds — an accumulated score below
        `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD`, or a single critical-severity
        disclosure — and on almost every deal the two agree, which makes the second
        indistinguishable from the first in a results table. A row where they *disagree*
        is the only direct evidence that the critical rule does anything, and U8.6 has to
        be able to see it before deciding whether the two conditions could be collapsed.
        """
        return (
            self.needs_human_review
            and self.confidence is not None
            and self.confidence >= config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD
        )

    @property
    def verdict_agrees(self) -> bool:
        return self.observed is self.case.verdict

    @property
    def targets_fired(self) -> bool:
        """True when every kind the case was engineered to trip actually fired.

        All of them, not any: a case naming two targets is claiming both paths run, and
        scoring it on the easier one would let a half-working case read as a pass.
        """
        raised = {f.kind for f in self.flags}
        return all(target in raised for target in self.case.targets)

    def severity_counts(self) -> dict[Severity, int]:
        return {
            severity: sum(1 for f in self.flags if f.severity == severity)
            for severity in (Severity.INFO, Severity.WARN, Severity.CRITICAL)
        }


@contextlib.contextmanager
def _case_environment(case: EvalCase, record: bool) -> Iterator[None]:
    """Every module-level override a case needs, applied and unwound as one unit.

    Three separate things live here, and they are together because they share one
    property: each is process-global state that a case sets and every *later* case would
    silently inherit. Unwinding in `finally` rather than after the invoke is the point —
    an exception mid-batch would otherwise leave the remaining rows running under some
    earlier case's conditions, and they would not say so, because the rows would look
    perfectly ordinary.

    **1. The retrieval ablation.** `config.RETRIEVAL_ENABLED` is a per-case property here
    rather than the command-line switch it is in `main.py`, so the ungrounded run is a row
    in the same table as every grounded one.

    **2. The response cache (U8.2).** Tiers `golden` and `replay` point at the *committed*
    recordings in `config.EVAL_RECORDINGS_DIR` and replay them; `live` is left on whatever
    the environment says, which is what makes it live.

    This wiring is what makes the tier property in `eval/README.md` true rather than
    aspirational, and it was **not** true before U8.2 — a fact worth recording, because the
    claim read as settled and was not. `agents/scenario_forecast._make_scorer` builds an
    `LlmClient` and calls it twice per Tree-of-Thought level on *every* run, tier
    regardless: a golden fixture skips the Extractor's model call, not the pipeline's. So
    every golden row was a live, quota-dependent, ~30-second call that a fresh clone could
    not reproduce — and `config.EVAL_RECORDINGS_DIR` had been defined since U3 with nothing
    in the repository reading it. Measured while writing U8.2's cases: two Los Angeles
    subjects differing only in bed/bath/floor-area returned an ordinary appreciation
    disclosure on one run and a **critical** `forecast_unavailable` on the other, decided
    inside the branch scorer. A verdict declared in advance cannot sit on top of that.

    `--record` flips the mode to `read_write` so the recordings can be made deliberately.
    Nothing writes to the committed store by accident: without the flag a missing
    recording raises `CacheMiss`, which is the honest failure — it means a prompt drifted
    since the batch was recorded, and re-recording is a decision rather than a fallback.

    **3. Declared fault injection (U8.2).** See `cases.Fault` for why this exists and why
    it is a named, declared field rather than a fixture that quietly patches something.
    """
    previous_retrieval = config.RETRIEVAL_ENABLED
    previous_cache_dir = config.LLM_CACHE_DIR
    previous_cache_mode = config.LLM_CACHE_MODE
    previous_geocode_census = geocoding.geocode_census

    config.RETRIEVAL_ENABLED = case.retrieval_enabled
    if case.tier is not Tier.LIVE:
        config.LLM_CACHE_DIR = config.EVAL_RECORDINGS_DIR
        config.LLM_CACHE_MODE = CacheMode.READ_WRITE if record else CacheMode.REPLAY

    if case.injects is Fault.GEOCODER_OUTAGE:
        def _unreachable(*args, **kwargs):
            raise geocoding.GeocodingError(
                f"[eval fault injection, case {case.key!r}] simulated Census Geocoder "
                f"outage. Declared by the case, not a real network failure."
            )

        # Patched at `tools.geocoding`, which is where `geocode()` looks the name up, so
        # the failure enters through the same door a real outage would: `geocode()`
        # catches `GeocodingError`, sets `primary_unavailable`, and the Extractor raises
        # `GEOCODER_SERVICE_UNAVAILABLE` rather than `COORDINATES_FROM_CITY_CENTROID`.
        # Patching the flag in directly would have skipped the distinction the case exists
        # to exercise.
        geocoding.geocode_census = _unreachable

    try:
        yield
    finally:
        config.RETRIEVAL_ENABLED = previous_retrieval
        config.LLM_CACHE_DIR = previous_cache_dir
        config.LLM_CACHE_MODE = previous_cache_mode
        geocoding.geocode_census = previous_geocode_census


def run_case(case: EvalCase, record: bool = False) -> CaseResult:
    """One case, end to end, through the real compiled graph.

    `build_graph()` defaults to an in-memory checkpointer, so nothing persists between
    cases or between runs — a batch where case 4 could inherit case 3's thread would not
    be measuring the cases.

    A case that escalates pauses at `human_review` and `invoke` returns the state
    accumulated to that point plus an `__interrupt__` key rather than a finished report.
    That is what this harness wants: the Critic has already run, and no resume is issued
    because nothing here needs a rendered report.
    """
    terms = case.terms.model_copy(deep=True) if case.terms else DealTerms()
    if case.supplied_coords is not None:
        terms.latitude, terms.longitude = case.supplied_coords

    state = DealState(
        raw_listing_text=case.listing or f"[golden fixture: {case.key}]",
        deal_terms=terms,
    )

    try:
        with _case_environment(case, record):
            result = build_graph().invoke(
                state,
                {"configurable": {"thread_id": f"eval-{case.key}-{uuid4().hex[:8]}"}},
            )
    except Exception as exc:  # noqa: BLE001 - a failing case is a result, not a crash
        # One case failing must not cost the other rows. The error becomes the row's
        # content, which is more useful than a traceback that ends the batch: a harness
        # that dies on case 3 of 12 tells you less than one that reports case 3 failed.
        return CaseResult(case=case, comps=0, confidence=None, error=f"{type(exc).__name__}: {exc}")

    return CaseResult(
        case=case,
        comps=len(result.get("comps", [])),
        confidence=result.get("confidence_score"),
        flags=result.get("flags", []),
        needs_human_review=bool(result.get("needs_human_review")),
        rework_count=int(result.get("rework_count") or 0),
    )


def census(results: list[CaseResult]) -> tuple[set[FlagKind], set[FlagKind], set[FlagKind]]:
    """`(covered, uncovered, unreachable)` over the whole batch."""
    covered = {f.kind for r in results for f in r.flags}
    unreachable = set(UNREACHABLE_BY_ANY_CASE)
    uncovered = set(FlagKind) - covered - unreachable
    return covered, uncovered, unreachable


def _results_table(results: list[CaseResult]) -> str:
    lines = [
        "| case | tier | comps | reworks | confidence | disclosures | outcome | "
        "target fired | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        # The provenance column the plan asks for, carrying the injection where there is
        # one: a reader must be able to see that a row exercised a *declared simulated*
        # failure rather than a naturally occurring one, without opening `cases.py`.
        tier = f"{r.case.tier}" + (f" + {r.case.injects}" if r.case.injects else "")
        if r.error:
            lines.append(f"| `{r.case.key}` | {tier} | — | — | — | — | "
                         f"**ERROR** | — | {r.error} |")
            continue
        counts = r.severity_counts()
        disclosures = f"{len(r.flags)} (" + ", ".join(
            f"{n} {s}" for s, n in counts.items() if n
        ) + ")" if r.flags else "0"
        target = "—" if not r.case.targets else ("yes" if r.targets_fired else "**NO**")
        # A BASELINE verdict is a regression check, and marking it "ok" beside a
        # PREDICTED one would invite the two to be counted together — see cases.py.
        mark = "ok" if r.verdict_agrees else "**MISMATCH**"
        suffix = "" if r.case.verdict_source is VerdictSource.PREDICTED else " (baseline)"
        outcome = f"{r.observed}" + (" †" if r.escalated_above_threshold else "")
        lines.append(
            f"| `{r.case.key}` | {tier} | {r.comps} | {r.rework_count} | "
            f"{r.confidence:.2f} | {disclosures} | {outcome} | {target} | "
            f"{mark}{suffix} |"
        )

    if any(r.escalated_above_threshold for r in results):
        lines += [
            "",
            f"† Escalated on a critical-severity disclosure while the confidence score "
            f"alone ({config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold) would "
            f"have let the deal report. These rows are the only direct evidence that the "
            f"two escalation grounds are independent.",
        ]
    return "\n".join(lines)


def _census_section(results: list[CaseResult]) -> str:
    covered, uncovered, unreachable = census(results)
    total = len(set(FlagKind))
    lines = [
        f"Of {total} defined flag kinds, **{len(covered)} were raised** by this batch, "
        f"{len(uncovered)} were not, and {len(unreachable)} cannot be raised by any case.",
        "",
        "**Uncovered — a case could close each of these:**",
        "",
    ]
    lines += [f"- `{kind}`" for kind in sorted(uncovered)] or ["- (none)"]
    lines += ["", "**Unreachable by any case — a statement about the build, not a gap:**", ""]
    lines += [f"- `{kind}` — {reason}" for kind, reason in
              sorted(UNREACHABLE_BY_ANY_CASE.items())] or [
        "- (none) — every kind this system defines is one some case could reach."]
    return "\n".join(lines)


def _scoring_summary(results: list[CaseResult]) -> str:
    """Verdict agreement over PREDICTED cases only — U8.6's actual instrument."""
    scored = [r for r in results
              if r.case.verdict_source is VerdictSource.PREDICTED and not r.error]
    baseline = [r for r in results
                if r.case.verdict_source is VerdictSource.BASELINE and not r.error]
    lines = []
    if scored:
        agree = sum(1 for r in scored if r.verdict_agrees)
        lines.append(f"**Verdict agreement (predicted cases only): {agree}/{len(scored)}.** "
                     f"This is the figure U8.6 tunes against.")
    else:
        lines.append("**No predicted cases yet** — U8.2 supplies them. Until then this "
                     "batch measures coverage and regression, not threshold placement.")
    if baseline:
        agree = sum(1 for r in baseline if r.verdict_agrees)
        lines.append("")
        lines.append(f"Regression against published baselines: {agree}/{len(baseline)} "
                     f"match the U7.8 table. A mismatch means either this build changed "
                     f"behaviour or that table has gone stale.")
    return "\n".join(lines)


def _report(results: list[CaseResult]) -> str:
    return "\n\n".join([
        f"# Eval harness results — {date.today().isoformat()}",
        "Generated by `eval/runner.py`. Every row is one invocation of the compiled "
        "graph in `graph.py` — the same one `main.py` runs.",
        "## Results",
        _results_table(results),
        "## Verdicts",
        _scoring_summary(results),
        "## Flag coverage",
        _census_section(results),
    ]) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=[t.value for t in Tier],
                        help="Run only this tier. `golden` makes no model calls.")
    parser.add_argument("--case", action="append", dest="keys",
                        help="Run only this case key. Repeatable.")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "results.md")
    # Deliberately a flag rather than the default. Recording writes to the *committed*
    # store, so it changes evidence a report quotes, and that should be something someone
    # typed rather than something that happened because a prompt drifted.
    parser.add_argument("--record", action="store_true",
                        help="Record model responses for golden/replay cases into the "
                             "committed store instead of replaying them. Makes live "
                             "calls; commit the result deliberately.")
    args = parser.parse_args()

    cases = all_cases()
    if args.tier:
        cases = [c for c in cases if c.tier == args.tier]
    if args.keys:
        cases = [c for c in cases if c.key in set(args.keys)]
    if not cases:
        raise SystemExit("No cases matched.")

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.key} ({case.tier})...", flush=True)
        results.append(run_case(case, record=args.record))

    report = _report(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"\n{report}")
    print(f"written -> {args.out}")


if __name__ == "__main__":
    main()
