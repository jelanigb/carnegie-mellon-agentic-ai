"""Evidence for U7.6 — the confidence-weight mechanism, on the real pipeline.

A script rather than a test, per §8's split. Two hermetic tests already prove the
mechanism's arithmetic in isolation, with a fake flag schedule built to exercise the
exact case each is named for:

  * `tests/test_flag_propagation.py::test_a_single_critical_flag_escalates_regardless_of_score`
    — a lone critical flag, nothing else, confidence lands exactly at the threshold and
    escalates anyway.
  * `tests/test_flag_propagation.py::test_confidence_does_not_decay_across_rework_laps`
    — a duplicated flag from a rework lap is charged once, not twice.

What neither test can show is **how today's actual system distributes across that
mechanism** — real LLM extraction, real geocoding, real Chroma retrieval, real HUD FMR,
real rent model, real ToT forecast, run on the six demo deals `main.py` ships. That is
what this script measures, and it is not decoration: `critic.confidence_from_flags` then
claimed a "two-warn floor" — every deal checked so far (three, as of Aug 26, 2026) paid
0.30 of the 0.40 separating a clean run from
`config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD` before anything deal-specific was observed.
Whether that holds, and whether the critical-flag rule is currently exercised by any real
deal independent of a low score, are both empirical questions this script answers rather
than assumes. Per U7.6: mechanism is not touched here — only measured.

**Both questions are now answered and this script is what answered the first.** The floor
does not generalize (see the finding printed below), and the critical-flag rule is isolated
by five golden eval rows rather than by any demo deal. The weights and threshold stopped
being provisional on Aug 30, 2026: #6 **held** them on
`scripts/confidence_sensitivity.py`'s sweep of the eval batch.

**What this check could have returned, stated up front so the finding is falsifiable:**

  * The floor could hold across all six deals, strengthening the case that two of the
    three severity levels are already committed before a deal is read.
  * It could fail to hold, in which case the three-deal measurement was reading a
    property of *which* deals were sampled rather than a property of the mechanism.
  * Every deal carrying a critical flag could also already sit below threshold on the
    score alone, in which case the critical-independent-of-score rule — real, and the
    fix for the U2 boundary defect `critic.py` documents — is not currently exercised by
    any live demo run, only by the hermetic test built for it.

**It also re-derives the demo table (U7.8).** `history/decision_log.md` carries a
`main.py --deal` table — comps, confidence, disclosures, outcome — that U2 measured, U3
re-measured, and that went stale when U5 and U6 added flags nothing re-ran against it.
A table transcribed by hand goes stale the same way a second time, so the rows are
printed here, from the same live run that produces everything above, and the ablation
row (`chicago --no-retrieval`) with it. Re-measuring is then one command rather than
seven, which is the difference between a table that gets refreshed and one that does not.

Run: .venv/bin/python scripts/confidence_evidence.py
     .venv/bin/python scripts/confidence_evidence.py --deal chicago
     .venv/bin/python scripts/confidence_evidence.py --no-table   # skip the ablation run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents.critic import _DERIVED_KINDS, confidence_from_flags
from demo_deals import DEMO_DEALS, DemoDeal
from graph import build_graph
from state import DealState, DealTerms, Severity
from tools.llm_client import LlmError, verify_models_live


def _check_models() -> None:
    """Fail before the first (real, billed) call rather than partway into six deals."""
    try:
        verified = verify_models_live()
    except LlmError as exc:
        raise SystemExit(f"Model check failed: {exc}")
    print(f"Model check OK — {', '.join(sorted(verified))}\n")


def _run_deal(deal: DemoDeal) -> dict:
    """One deal, end to end, through the real compiled graph.

    `build_graph()` defaults to an in-memory checkpointer, so no state persists between
    deals or between runs of this script — appropriate here, where every run is meant to
    start clean, unlike `main.py`'s SQLite checkpointer, which exists so a paused thread
    can be resumed.

    A deal that escalates pauses at `human_review` and `invoke` returns the state
    accumulated up to that point plus an `__interrupt__` key, not a finished report —
    exactly what this script needs, since the Critic already ran. No resume is issued;
    this script never needs a rendered report, only what the Critic wrote to state.
    """
    terms = DealTerms()
    if deal.supplied_coords is not None:
        terms.latitude, terms.longitude = deal.supplied_coords
    state = DealState(raw_listing_text=deal.listing, deal_terms=terms)
    graph = build_graph()
    thread_id = f"confidence-evidence-{deal.key}-{uuid4().hex[:8]}"
    return graph.invoke(state, {"configurable": {"thread_id": thread_id}})


def _contributing_flags(flags: list) -> list[tuple]:
    """The flags that actually fed the score: derived kinds excluded, duplicates folded.

    Mirrors `confidence_from_flags`'s own filter exactly (imported, not re-typed) so this
    table can never silently drift from what the function it is reporting on actually
    does.
    """
    seen: set[tuple[str, str, str]] = set()
    rows = []
    for f in flags:
        if f.kind in _DERIVED_KINDS:
            continue
        signature = (f.source_agent, f.kind, f.detail)
        if signature in seen:
            continue
        seen.add(signature)
        penalty = config.FLAG_SEVERITY_PENALTY.get(f.severity, 0.0)
        rows.append((f.severity, f.source_agent, f.kind, penalty))
    return rows


def _disclosure_summary(flags: list) -> str:
    """`4 (2 info, 2 warn)` — every flag on the final state, by severity.

    **Every** flag, including the ones the Critic itself raises. The U2/U3 versions of
    this table never said which it counted, which is part of why a re-measurement cannot
    just be compared against them row for row. Stated here so the next re-measurement is
    comparing the same quantity.
    """
    order = (Severity.INFO, Severity.WARN, Severity.CRITICAL)
    counts = {s: sum(1 for f in flags if f.severity == s) for s in order}
    parts = [f"{n} {s}" for s, n in counts.items() if n]
    return f"{len(flags)}" + (f" ({', '.join(parts)})" if parts else "")


def _outcome(result: dict) -> str:
    return "pauses at `human_review`" if result["needs_human_review"] else "reports normally"


def _print_demo_table(rows: list[tuple[str, dict]]) -> None:
    """The demo table, as markdown, ready to paste into `history/decision_log.md`."""
    print("=" * 78)
    print("Demo table (U7.8 re-measurement)")
    print("=" * 78)
    print()
    print("| `main.py --deal` | Comps | Confidence | Disclosures | Outcome |")
    print("| --- | --- | --- | --- | --- |")
    for label, result in rows:
        print(
            f"| `{label}` | {len(result['comps'])} | {result['confidence_score']:.2f} | "
            f"{_disclosure_summary(result['flags'])} | {_outcome(result)} |"
        )
    print()


def _print_deal(key: str, result: dict) -> None:
    print("=" * 78)
    print(key)
    print("=" * 78)

    flags = result["flags"]
    contributing = _contributing_flags(flags)
    confidence = result["confidence_score"]
    print(f"  comps: {len(result['comps'])}   disclosures: {_disclosure_summary(flags)}")

    # Independent recomputation, on the full post-Critic flag list. If this ever
    # disagrees with what `critic_agent` actually returned, the derived-kind exclusion
    # has stopped doing its job — a rework lap would compound rather than hold steady,
    # which is exactly the U7.4 defect the exclusion exists to prevent.
    recomputed = confidence_from_flags(SimpleNamespace(flags=flags))
    if abs(recomputed - confidence) > 1e-9:
        print(
            f"  ** MISMATCH ** critic reported {confidence:.4f}, recomputed from the "
            f"final flag list gives {recomputed:.4f} — the derived-kind exclusion did "
            f"not hold on this deal."
        )

    if not contributing:
        print("  no flags fed the score")
    for severity, source_agent, kind, penalty in contributing:
        print(f"  {severity:9s} {source_agent:18s} {kind:32s} -{penalty:.2f}")

    penalty_total = sum(p for *_rest, p in contributing)
    print(f"  confidence: 1.00 - {penalty_total:.2f} = {confidence:.2f}  "
          f"(threshold {config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f})")

    low_confidence = confidence < config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD
    has_critical = any(f.severity == Severity.CRITICAL for f in flags)
    if not result["needs_human_review"]:
        print("  -> reports normally")
    elif low_confidence and has_critical:
        print(
            "  -> escalates: BOTH grounds present (score below threshold, and a "
            "critical flag) — this deal cannot isolate which rule is doing the work"
        )
    elif has_critical:
        print(
            "  -> escalates on the CRITICAL-FLAG rule alone — confidence clears the "
            "threshold, demonstrating the rule is independent of the score"
        )
    else:
        print("  -> escalates on the SCORE alone")

    if result["critic_rejected"]:
        print(
            f"  critic_rejected=True — rework requested "
            f"(rework_count={result['rework_count']})"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deal", choices=sorted(DEMO_DEALS), help="run one demo deal")
    parser.add_argument(
        "--no-table",
        action="store_true",
        help="skip the demo table, and with it the extra ungrounded ablation run",
    )
    args = parser.parse_args()

    _check_models()

    keys = [args.deal] if args.deal else list(DEMO_DEALS)
    results = {}
    for key in keys:
        results[key] = _run_deal(DEMO_DEALS[key])
        _print_deal(key, results[key])

    if len(results) < 2:
        return

    # The ablation row, run last and deliberately: it mutates the module-level
    # `RETRIEVAL_ENABLED` the way `main.py --no-retrieval` does, and every grounded deal
    # above has already finished by the time it does. Restored afterwards regardless, so
    # an import of this module cannot leave retrieval off for whatever runs next.
    ablation = None
    if not args.no_table:
        grounded = config.RETRIEVAL_ENABLED
        try:
            config.RETRIEVAL_ENABLED = False
            ablation = _run_deal(DEMO_DEALS["chicago"])
        finally:
            config.RETRIEVAL_ENABLED = grounded
        _print_deal("chicago --no-retrieval (U4 ablation)", ablation)
        _print_demo_table(
            [*results.items(), ("chicago --no-retrieval", ablation)]
        )

    print("=" * 78)
    print("Across all six demo deals")
    print("=" * 78)

    warn_kind_sets = []
    isolates_critical_rule = 0
    for key, result in results.items():
        flags = result["flags"]
        warn_kinds = {
            f.kind for f in flags
            if f.severity == Severity.WARN and f.kind not in _DERIVED_KINDS
        }
        warn_kind_sets.append(warn_kinds)
        confidence = result["confidence_score"]
        has_critical = any(f.severity == Severity.CRITICAL for f in flags)
        if has_critical and confidence >= config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
            isolates_critical_rule += 1

    common_warns = set.intersection(*warn_kind_sets) if warn_kind_sets else set()
    if common_warns:
        print(
            f"  Warn-severity flags common to every deal: "
            f"{', '.join(sorted(common_warns))}"
        )
        print("  The 'floor' claim holds on this six-deal set.")
    else:
        print(
            "  No warn-severity flag is common to all six deals — the 'floor' claim "
            "measured on three deals does not generalize to six. The FMR "
            "county-anchor warn, for example, fires on the three Los Angeles-county "
            "deals (los-angeles, overpriced, coord-conflict) because that county has "
            "no HUD Small Area FMR, and not on chicago, which has one; it is a "
            "per-county HUD-coverage fact, not a property every deal shares."
        )

    if isolates_critical_rule:
        print(
            f"  {isolates_critical_rule} of 6 deals escalate on the critical-flag rule "
            f"alone (confidence at or above threshold with a critical flag present)."
        )
    else:
        print(
            "  0 of 6 deals isolate the critical-flag rule: every deal carrying a "
            "critical flag already sits below threshold on the score alone. The rule "
            "is real (`agents/critic.py`, decision #6) and proven by "
            "`test_a_single_critical_flag_escalates_regardless_of_score`."
        )

    # The ablation is a `main.py` invocation rather than a seventh deal, so it is kept
    # out of the six-deal statistics above — but it is a live run, and U7.6 concluded
    # from the six alone that *nothing* live exercised the critical-flag rule. It does.
    # Checked rather than asserted, so the sentence cannot outlive the fact.
    if ablation is not None:
        ablation_isolates = (
            any(f.severity == Severity.CRITICAL for f in ablation["flags"])
            and ablation["confidence_score"] >= config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD
        )
        if ablation_isolates:
            print(
                f"  The `chicago --no-retrieval` ablation DOES isolate the rule: one "
                f"critical flag and nothing else, confidence "
                f"{ablation['confidence_score']:.2f} against a "
                f"{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold — the same "
                f"boundary the U2 defect sat on, now escalating because the rule is "
                f"independent of the score. It is a live case for the rule, though not "
                f"a *deal*: the critical flag is `retrieval_disabled`, which only the "
                f"ablation flag can raise."
            )
        else:
            print(
                "  The `chicago --no-retrieval` ablation does not isolate the rule "
                "either — its score now falls below the threshold on its own."
            )


if __name__ == "__main__":
    main()
