"""The eval harness's batch runner and its two outputs (U8.1).

Runs every case in `eval/cases.py` through the **real compiled graph** — the same
`build_graph()` `main.py` uses, not a rearrangement of it — and produces two artifacts in
`eval/results/`:

1. **The results table**, a row per case: comps, confidence, disclosures by severity,
   outcome, the recommendation, whether the flag the case targets actually fired, and
   whether the outcome matched the verdict declared before the run. **Outcome and
   recommendation are the two axes** (U9.4) and the table keeps them apart: the first says
   whether the system can stand behind its numbers, the second whether the property is
   worth buying, and a row can escalate while recommending that a buyer proceed.
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
    .venv/bin/python -m eval.runner                 # every case; replays, no live calls
    .venv/bin/python -m eval.runner --tier golden
    .venv/bin/python -m eval.runner --case chicago
    .venv/bin/python -m eval.runner --record        # re-record, deliberately
    .venv/bin/python -m eval.runner --case los-angeles --live   # what a fresh run does

**Every tier replays by default as of U9.5**, demo deals included. Reaching a model is now
something someone typed — `--record` to freeze a run into the committed store, `--live` to
see what an unfrozen one does without writing it. Before that the demo rows fell through
to a gitignored development cache, so the seven figures the report quoted from them could
not be re-derived from a clone; `_case_environment` carries what that cost.
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
from state import (
    RECOMMENDATION_LABEL,
    DealState,
    DealTerms,
    FlagKind,
    RecommendationDetail,
    Severity,
)
from tools.faults import injected
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
    recommendation: Optional[RecommendationDetail] = None

    @property
    def observed(self) -> Verdict:
        return Verdict.ESCALATES if self.needs_human_review else Verdict.REPORTS

    @property
    def recommendation_cell(self) -> str:
        """Axis 2 for the table — the verdict, and whether a second reading split from it.

        **Reported, never scored, and that is a deliberate limit on this column** (U9.5).
        A case's declared `verdict` is axis 1; nothing in `cases.py` declares an expected
        recommendation, so this column records what the rule produced rather than checking
        it against anything. Authoring 21 expected verdicts *after* the rule exists would
        score the rule against a reading of itself, which is the error `VerdictSource`
        exists one column over to prevent. What the column does buy is a regression
        surface: axis 2 is a pure function, so any movement here between two batches on
        the same recordings is a real change in the rule and nothing else.

        The disagreement marker earns its place for the same reason the `†`/`‡` markers
        do — it is the only visible evidence that the second reasoning locus (OQ-22) ran
        at all, and a batch where nothing ever disagrees would say the cross-check is
        inert.
        """
        if self.recommendation is None:
            return "—"
        label = RECOMMENDATION_LABEL[self.recommendation.verdict]
        return f"{label} ⚖" if self.recommendation.cross_check_disagrees else label

    @property
    def has_critical(self) -> bool:
        return any(f.severity == Severity.CRITICAL for f in self.flags)

    @property
    def budget_exhausted(self) -> bool:
        """True when the row escalated because the rework budget ran out unresolved,
        rather than as a consequence of the accumulated score.

        `agents/critic.critic_agent` raises `FlagKind.REWORK_LIMIT_REACHED` on exactly
        that ground, so the flag is the marker rather than re-deriving the condition
        from `rework_count` here — `state.plan`/`config.MAX_REWORKS` are the Critic's
        business, not the table's.
        """
        return any(f.kind == FlagKind.REWORK_LIMIT_REACHED for f in self.flags)

    @property
    def escalated_above_threshold(self) -> bool:
        """Escalated while the confidence score alone would have let it report.

        The one row shape worth calling out by name. `agents/critic.critic_agent`
        escalates on **three** independent grounds (U8.5/OQ-16 added the third) — an
        accumulated score below `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD`, a single
        critical-severity disclosure, or a retryable objection that survives
        `config.MAX_REWORKS` reworks unresolved — and on almost every deal all of them
        agree, which makes the other two indistinguishable from the first in a results
        table. A row where they *disagree* is the only direct evidence that a given rule
        does anything on its own, and U8.6 has to be able to see it before deciding
        whether any of them could be collapsed. `has_critical`/`budget_exhausted` say
        *which* ground fired; this says only that the score alone would not have.
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
def _case_environment(case: EvalCase, record: bool, live: bool = False) -> Iterator[None]:
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

    **2. The response cache (U8.2; every tier since U9.5).** All three tiers point at the
    *committed* recordings in `config.EVAL_RECORDINGS_DIR` and replay them. Passing
    `live=True` is the only way to reach a model, and it is a typed flag rather than a
    property of the tier.

    **This used to be true of `golden` and `replay` only, and the exception was a
    reproducibility hole rather than a feature.** `live` rows fell through to whatever the
    environment said — in practice `LLM_CACHE_MODE=read_write` against the *gitignored*
    development cache — so a demo row was served from a developer's working store when it
    happened to be warm and called the model when it was not. Two things followed, and
    both were found at U9.5 rather than designed:

    - **The seven demo rows could not be reproduced from a fresh clone**, by construction,
      against this harness's own standard that a figure a clone cannot re-derive is an
      assertion rather than evidence (`eval/README.md`). They are unscored baselines, so
      it was defensible; it was nowhere stated, which is the part that was not.
    - **The published `staten-island` row said 1 comp where the build produces 0** — a
      stale extraction in that development cache, surviving in the results table as a
      number nothing could re-derive.

    Pinning every tier retires the class rather than the instance. What is lost is that no
    row now exercises a live call by default, so the batch stops being an incidental check
    that the model is reachable; `--live` restores that deliberately, and
    `tools/diagnostics.verify_models_live()` was always the thing actually testing it.

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

    **3. Declared fault injection (U8.2, extended U8.3, extended U8.5/OQ-16) — the
    mechanism moved out at U9.7a and this is now a delegation.** `tools/faults.py` owns
    the three patches and the reasoning behind each; `Fault` moved there with them. What
    stays here is the *call*, because the harness is only one of three callers now: the
    demo surface and `main.py --fault` declare the same failures against a `DemoDeal`, and
    a fault that behaved differently in the demo than in the evaluation would invalidate
    both at once.

    The nesting is deliberate. Faults unwind inside this function's `finally`, so the
    cache and retrieval overrides are restored last — outermost set, outermost cleared —
    and an exception anywhere inside leaves nothing patched either way.
    """
    previous_retrieval = config.RETRIEVAL_ENABLED
    previous_cache_dir = config.LLM_CACHE_DIR
    previous_cache_mode = config.LLM_CACHE_MODE

    config.RETRIEVAL_ENABLED = case.retrieval_enabled
    if not live:
        config.LLM_CACHE_DIR = config.EVAL_RECORDINGS_DIR
        config.LLM_CACHE_MODE = CacheMode.READ_WRITE if record else CacheMode.REPLAY

    try:
        with injected(
            case.injects,
            declared_by=case.key,
            geocoder_fallback_override=case.geocoder_fallback_override,
        ):
            yield
    finally:
        config.RETRIEVAL_ENABLED = previous_retrieval
        config.LLM_CACHE_DIR = previous_cache_dir
        config.LLM_CACHE_MODE = previous_cache_mode


def run_case(case: EvalCase, record: bool = False, live: bool = False) -> CaseResult:
    """One case, end to end, through the real compiled graph.

    `build_graph()` defaults to an in-memory checkpointer, so nothing persists between
    cases or between runs — a batch where case 4 could inherit case 3's thread would not
    be measuring the cases.

    A case that escalates pauses at `human_review` and `invoke` returns the state
    accumulated to that point plus an `__interrupt__` key rather than a finished report.
    That is what this harness wants: the Critic has already run, and no resume is issued
    because nothing here needs a rendered report.

    **The recommendation survives that pause, which is why the table can carry it.** The
    Critic computes both axes before it decides routing, so an escalated row still has a
    verdict on the property — and `staten-island` is exactly the row where the two differ.
    Reading axis 2 only from rows that completed would have shown it only where it was
    least interesting.
    """
    terms = case.terms.model_copy(deep=True) if case.terms else DealTerms()
    if case.supplied_coords is not None:
        terms.latitude, terms.longitude = case.supplied_coords

    state = DealState(
        raw_listing_text=case.listing or f"[golden fixture: {case.key}]",
        deal_terms=terms,
    )

    try:
        with _case_environment(case, record, live):
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
        recommendation=result.get("recommendation"),
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
        "recommendation | target fired | verdict |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        # The provenance column the plan asks for, carrying the injection where there is
        # one: a reader must be able to see that a row exercised a *declared simulated*
        # failure rather than a naturally occurring one, without opening `cases.py`.
        tier = f"{r.case.tier}" + (f" + {r.case.injects}" if r.case.injects else "")
        if r.error:
            lines.append(f"| `{r.case.key}` | {tier} | — | — | — | — | "
                         f"**ERROR** | — | — | {r.error} |")
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
        marker = ""
        if r.escalated_above_threshold:
            # Both grounds are independent of the score; disambiguate rather than
            # collapsing them into one mark, since which one fired is exactly what a
            # reader checking this row wants to know. `has_critical` first because a
            # row could in principle carry both — a rework spent on a retryable
            # objection can still return with an unrelated critical flag standing.
            marker = " †" if r.has_critical else " ‡" if r.budget_exhausted else " †"
        outcome = f"{r.observed}" + marker
        lines.append(
            f"| `{r.case.key}` | {tier} | {r.comps} | {r.rework_count} | "
            f"{r.confidence:.2f} | {disclosures} | {outcome} | "
            f"{r.recommendation_cell} | {target} | {mark}{suffix} |"
        )

    if any(r.escalated_above_threshold and r.has_critical for r in results):
        lines += [
            "",
            f"† Escalated on a critical-severity disclosure while the confidence score "
            f"alone ({config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold) would "
            f"have let the deal report. Direct evidence that the critical-flag rule "
            f"does something the score alone would not.",
        ]
    if any(r.escalated_above_threshold and r.budget_exhausted for r in results):
        lines += [
            "",
            f"‡ Escalated because a retryable objection survived "
            f"{config.MAX_REWORKS} rework(s) unresolved, while the confidence score "
            f"alone ({config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold) would "
            f"have let the deal report. Direct evidence that the rework-budget rule "
            f"does something the score alone would not (U8.5/OQ-16).",
        ]
    if any(r.recommendation is not None for r in results):
        lines += [
            "",
            "**`outcome` and `recommendation` are different questions and are meant to "
            "be read apart.** `outcome` is axis 1 — whether the system can stand behind "
            "its own numbers. `recommendation` is axis 2 — whether the property is worth "
            "buying. A row can escalate and still recommend proceeding, and "
            "`staten-island` is that row: zero comparables, and an asking price well "
            "under its ZIP median. Only axis 1 is scored in the `verdict` column; axis 2 "
            "is reported, because no case declares an expected recommendation and "
            "writing 21 of them after the rule exists would score the rule against "
            "itself.",
        ]
    if any(r.recommendation is not None and r.recommendation.cross_check_disagrees
           for r in results):
        lines += [
            "",
            "⚖ An independent model reading of the same evidence reached a *different* "
            "verdict, which the report discloses rather than resolves (U9.4, OQ-22). The "
            "rule always decides; the cross-check can only annotate. The marker is the "
            "only place a batch shows that second reasoning locus ran at all.",
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
                        help="Run only this tier. No tier makes model calls without "
                             "--live or --record.")
    parser.add_argument("--case", action="append", dest="keys",
                        help="Run only this case key. Repeatable.")
    parser.add_argument("--out", type=Path, default=RESULTS_DIR / "results.md")
    # Deliberately a flag rather than the default. Recording writes to the *committed*
    # store, so it changes evidence a report quotes, and that should be something someone
    # typed rather than something that happened because a prompt drifted.
    parser.add_argument("--record", action="store_true",
                        help="Record model responses into the committed store instead "
                             "of replaying them. Makes live calls; commit the result "
                             "deliberately.")
    # Every tier replays by default since U9.5, so reaching a model is now something
    # someone typed. Kept separate from --record because the two want opposite things:
    # --record makes live calls in order to *freeze* them, this one makes them in order
    # to see what an unfrozen run does. Asking for both is a contradiction rather than a
    # combination, so it is rejected rather than silently resolved in some order.
    parser.add_argument("--live", action="store_true",
                        help="Call the model instead of replaying recordings, without "
                             "writing them. Use to check what a fresh run does; the "
                             "published table is the replayed one.")
    args = parser.parse_args()
    if args.live and args.record:
        raise SystemExit(
            "--live and --record are contradictory: --record exists to freeze a live "
            "run into the committed store, --live exists to run without touching it. "
            "Pick one."
        )

    cases = all_cases()
    if args.tier:
        cases = [c for c in cases if c.tier == args.tier]
    if args.keys:
        cases = [c for c in cases if c.key in set(args.keys)]
    if not cases:
        raise SystemExit("No cases matched.")

    results = []
    for index, case in enumerate(cases, start=1):
        mode = " live" if args.live else " recording" if args.record else ""
        print(f"[{index}/{len(cases)}] {case.key} ({case.tier}){mode}...", flush=True)
        results.append(run_case(case, record=args.record, live=args.live))

    report = _report(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    print(f"\n{report}")
    print(f"written -> {args.out}")


if __name__ == "__main__":
    main()
