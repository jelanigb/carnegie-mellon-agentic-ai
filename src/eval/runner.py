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
from tools import geocoding, zori

# The month `Fault.STALE_RENT_INDEX` pins the market index to. Chosen to sit well past
# `config.RENT_ANCHOR_MAX_STALENESS_MONTHS` so refreshing the committed panel cannot
# quietly stop the case from firing.
_STALE_INDEX_MONTH = "2023-01-31"
from tools.llm_cache import CacheMode
from tools.llm_client import LlmClient, LlmError

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

    **3. Declared fault injection (U8.2, extended U8.3, extended U8.5/OQ-16).** See
    `cases.Fault` for why this exists and why it is a named, declared field rather than a
    fixture that quietly patches something. `GEOCODER_OUTAGE` patches
    `geocoding.geocode_census`; `LLM_UNAVAILABLE` patches `LlmClient.complete` at the
    class, since `_extract_terms` builds a fresh instance per call and there is no
    instance to reach beforehand. A case declaring `geocoder_fallback_override` also
    patches `geocoding.city_centroid`, so the outage's fallback lands at a chosen point
    instead of the real corpus-wide city average — OQ-16's answer, since the real average
    never both diverges from the rent estimate and stays clear of a third warn or a
    critical (U8.2's grid search). All patches are unwound in the same `finally` as
    everything else here.
    """
    previous_retrieval = config.RETRIEVAL_ENABLED
    previous_cache_dir = config.LLM_CACHE_DIR
    previous_cache_mode = config.LLM_CACHE_MODE
    previous_geocode_census = geocoding.geocode_census
    previous_city_centroid = geocoding.city_centroid
    previous_llm_complete = LlmClient.complete

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

        if case.geocoder_fallback_override is not None:
            lat, lon = case.geocoder_fallback_override

            def _forced_centroid(city, state, primary_unavailable=False):
                return geocoding.GeocodeResult(
                    latitude=lat,
                    longitude=lon,
                    matched_address=(
                        f"[eval fault injection, case {case.key!r}] forced centroid "
                        f"fallback at ({lat:.5f}, {lon:.5f})"
                    ),
                    source=geocoding.GeocodeSource.CITY_CENTROID,
                    primary_unavailable=primary_unavailable,
                )

            # Same shape as the real function — a `GeocodeResult` with
            # `source=CITY_CENTROID` — so the Extractor's own branch on `.source` and
            # `.primary_unavailable` still makes the outage-vs-unresolvable decision.
            # Only *where* the fallback lands is forced; the mechanism that decides
            # whether it is worth retrying is untouched.
            geocoding.city_centroid = _forced_centroid

    if case.injects is Fault.STALE_RENT_INDEX:
        # Far enough back that the staleness threshold is crossed by a wide margin, so
        # the case does not silently stop firing when the committed panel is refreshed.
        previous_latest_month = zori.latest_month
        zori.latest_month = lambda panel: _STALE_INDEX_MONTH

    if case.injects is Fault.LLM_UNAVAILABLE:
        def _unreachable_complete(*args, **kwargs):
            raise LlmError(
                f"[eval fault injection, case {case.key!r}] simulated model outage. "
                f"Declared by the case, not a real network failure."
            )

        # Patched at the class, not an instance: `_extract_terms` (and
        # `scenario_forecast._make_scorer`) each build their own `LlmClient()`, so there
        # is no shared instance to patch. `self.complete(...)` resolves through the class
        # either way, so every instance created for the rest of this case sees the fault
        # — including scenario_forecast's later calls, which is the honest behaviour of a
        # model that is actually down (see `Fault.LLM_UNAVAILABLE`'s docstring).
        LlmClient.complete = _unreachable_complete

    try:
        yield
    finally:
        config.RETRIEVAL_ENABLED = previous_retrieval
        config.LLM_CACHE_DIR = previous_cache_dir
        config.LLM_CACHE_MODE = previous_cache_mode
        geocoding.geocode_census = previous_geocode_census
        if case.injects is Fault.STALE_RENT_INDEX:
            zori.latest_month = previous_latest_month
        geocoding.city_centroid = previous_city_centroid
        LlmClient.complete = previous_llm_complete


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
            f"{r.confidence:.2f} | {disclosures} | {outcome} | {target} | "
            f"{mark}{suffix} |"
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
