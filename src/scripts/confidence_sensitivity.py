"""How much would decision #6's numbers have to move before any verdict changed? (U8.6)

    .venv/bin/python scripts/confidence_sensitivity.py

**The instrument problem this exists to solve.** U8.6 is asked to tune
`HUMAN_REVIEW_CONFIDENCE_THRESHOLD` and `FLAG_SEVERITY_PENALTY` against the eval batch.
The obvious method — score how often the shipped values agree with each case's declared
verdict — cannot work here, and the reason is stated in `eval/cases.py`: the cases were
written knowing the shipped values, so agreement measures the fixtures. The demo deals
have the same defect with the sign reversed, which is why they were disqualified from this
in the first place.

So the question asked instead is a **robustness** one: hold the batch fixed, sweep the
parameters, and report the region over which nothing the system decides changes. That is
answerable from fixtures without being contaminated by them — a fixture cannot tell you
whether 0.60 is the right threshold, but it can tell you that 0.45 and 0.65 produce the
identical set of verdicts, which is a fact about the *parameter* rather than about the
fixture. The close is therefore a claim about stability, not about optimality, and the
artifact this writes says so in those words.

**Three things it reports, and one it settles.**

1. **The stable region.** Every (threshold, warn weight) pair over a grid, marked with how
   many verdicts differ from the shipped configuration's. The scores are quantized to
   multiples of the warn weight — every deal's confidence is `1 − (k × warn + m ×
   critical)` for small integers k and m — so the surface is expected to be flat in
   plateaus rather than smooth, and the plateau containing the shipped values is the
   answer.
2. **Whether the critical weight does anything.** Any critical flag escalates through an
   independent rule in `critic.critic_agent`, so `FLAG_SEVERITY_PENALTY["critical"]`
   should be behaviorally inert — it can move a *score* but never a *verdict*. Swept
   across its whole plausible range to confirm that, because "inert by argument" and
   "inert on this batch" are different claims.
3. **OQ-1's causal pair.** `rent_anchor_county_level` is part of *why*
   `rent_estimate_market_error_elevated` fires — a county-grain anchor is one reason a
   market's holdout error runs high — so charging 0.15 for each charges cause and effect
   separately. The other market-scoped flags are independent axes. Whether de-duplicating
   that one pair moves any verdict is measured here rather than argued.

**Re-scoring reuses `critic.confidence_from_flags` rather than reimplementing it**, with
`config` patched around each grid point. A second copy of the arithmetic in a tuning
script is how a tuning script comes to be measuring something the system does not do.

Runs the batch once in replay mode to collect flag sets (no live model calls), then sweeps
in memory. Writes its artifact to `eval/results/sensitivity.md`.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents.critic import confidence_from_flags
from eval import runner
from eval.cases import Tier, Verdict, VerdictSource, scoring_cases
from state import DealState, FlagKind, Severity

ARTIFACT = config.SRC_DIR / "eval" / "results" / "sensitivity.md"

# The grid. Both axes are swept well past anything defensible so the plateau's *edges* are
# visible — a sweep that only covers the region someone already believes in cannot show
# that the region is wide.
#
# **Extended downward Aug 30, 2026, because the first version reported its own floor as a
# finding.** The threshold axis started at 0.30, the plateau ran to the bottom of it, and
# the artifact said "every threshold from 0.30 to 0.70" — which reads as a measured edge
# and was actually the edge of the search. The lowest-scoring escalating cases sit at 0.25,
# so the real boundary was below the grid the whole time. Both axes now run to values
# nothing could defend (a 0.05 threshold escalates almost nothing; a 0.45 warn weight
# escalates on two), which is the point: an edge is only evidence if the sweep could have
# found it somewhere else. `_edge_note` below says so explicitly whenever a reported bound
# still lands on the grid boundary.
THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.45, 0.50,
              0.55, 0.60, 0.65, 0.70, 0.75, 0.85, 0.95]
WARN_WEIGHTS = [0.05, 0.10, 0.125, 0.15, 0.175, 0.20, 0.25, 0.30, 0.40, 0.45]
CRITICAL_WEIGHTS = [0.0, 0.10, 0.25, 0.40, 0.60, 1.00]

# The causal pair OQ-1 asks about: the second is partly *caused* by the first, so charging
# both charges one observation twice. Scored as an alternative, never adopted here.
_CAUSAL_PAIR = (FlagKind.RENT_ANCHOR_COUNTY_LEVEL,
                FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED)


def _edge_note(run: list[float], axis: list[float], name: str) -> str:
    """Say so when a reported bound is the edge of the search rather than a real edge.

    **This exists because the first version of this artifact got it wrong.** The threshold
    grid started at 0.30, the plateau ran all the way to it, and the summary reported
    "every threshold from 0.30 to 0.70" — which a reader takes as a measured boundary. It
    was the bottom of the grid. A plateau that touches the edge of the search has an
    *unknown* extent in that direction, and saying so costs one sentence.
    """
    if not run:
        return ""
    touches = []
    if run[0] == axis[0]:
        touches.append("below")
    if run[-1] == axis[-1]:
        touches.append("above")
    if not touches:
        return ""
    return (
        f" **The {name} run reaches the {' and '.join(touches)} edge of the swept grid, "
        f"so its true extent in that direction is unmeasured rather than bounded here.**"
    )


@contextlib.contextmanager
def _weights(warn: float, critical: float):
    """Patch the severity table for one grid point and put it back."""
    previous = config.FLAG_SEVERITY_PENALTY
    config.FLAG_SEVERITY_PENALTY = {"info": 0.0, "warn": warn, "critical": critical}
    try:
        yield
    finally:
        config.FLAG_SEVERITY_PENALTY = previous


def _verdict(result, threshold: float, dedupe_causal_pair: bool = False) -> Verdict:
    """Re-derive one case's verdict under the currently-patched weights.

    Mirrors `critic.critic_agent`'s three escalation grounds deliberately rather than
    calling it: the Critic needs a live `DealState` mid-run, and what is being swept is the
    *decision*, which is three lines of it. The one piece that is genuinely arithmetic —
    the score — is delegated to the real function so it cannot drift.
    """
    flags = list(result.flags)
    if dedupe_causal_pair:
        kinds = {f.kind for f in flags}
        if all(k in kinds for k in _CAUSAL_PAIR):
            flags = [f for f in flags if f.kind is not _CAUSAL_PAIR[0]]

    confidence = confidence_from_flags(
        DealState(raw_listing_text="[sensitivity sweep]", flags=flags)
    )
    has_critical = any(f.severity == Severity.CRITICAL for f in result.flags)
    budget_exhausted = any(
        f.kind is FlagKind.REWORK_LIMIT_REACHED for f in result.flags
    )
    escalates = confidence < threshold or has_critical or budget_exhausted
    return Verdict.ESCALATES if escalates else Verdict.REPORTS


def _baseline(results) -> dict[str, Verdict]:
    with _weights(config.FLAG_SEVERITY_PENALTY["warn"],
                  config.FLAG_SEVERITY_PENALTY["critical"]):
        return {
            r.case.key: _verdict(r, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD)
            for r in results
        }


def _sweep_grid(results, baseline: dict[str, Verdict]) -> list[str]:
    shipped_warn = config.FLAG_SEVERITY_PENALTY["warn"]
    shipped_critical = config.FLAG_SEVERITY_PENALTY["critical"]
    lines = [
        "## 1. The stable region",
        "",
        "Verdicts that differ from the shipped configuration, over "
        f"{len(results)} predicted cases. `0` means this configuration decides every "
        "case exactly as the shipped one does; **`·` marks the shipped values**.",
        "",
        "| warn \\ threshold | " + " | ".join(f"{t:.2f}" for t in THRESHOLDS) + " |",
        "| --- |" + " --- |" * len(THRESHOLDS),
    ]
    plateau: list[tuple[float, float]] = []
    for warn in WARN_WEIGHTS:
        cells = []
        for threshold in THRESHOLDS:
            with _weights(warn, shipped_critical):
                changed = sum(
                    1 for r in results if _verdict(r, threshold) is not baseline[r.case.key]
                )
            if changed == 0:
                plateau.append((warn, threshold))
            shipped = (warn == shipped_warn
                       and threshold == config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD)
            cells.append(f"**{changed}**·" if shipped else str(changed))
        lines.append(f"| **{warn:.3f}** | " + " | ".join(cells) + " |")

    if plateau:
        # **The contiguous run through the shipped point, not the union of both axes.**
        # Reporting "warn weights 0.05-0.30 and thresholds 0.30-0.85 appear somewhere in
        # the region" is true and misleading: those extremes do not hold *together*, and a
        # reader would take it as a rectangle. What a person actually wants to know is how
        # far each dial can be turned from where it sits with the other left alone.
        flat = set(plateau)
        row = [t for t in THRESHOLDS
               if (shipped_warn, t) in flat
               and all((shipped_warn, u) in flat for u in THRESHOLDS
                       if min(t, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD)
                       <= u <= max(t, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD))]
        column = [w for w in WARN_WEIGHTS
                  if (w, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD) in flat
                  and all((v, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD) in flat
                          for v in WARN_WEIGHTS
                          if min(w, shipped_warn) <= v <= max(w, shipped_warn))]
        lines += [
            "",
            f"**{len(plateau)} of {len(WARN_WEIGHTS) * len(THRESHOLDS)} grid points "
            f"decide this batch identically to the shipped configuration.**",
            "",
            "**Nothing here changes the shipped threshold — it is 0.60 and stays 0.60.** "
            "This asks what *would* happen at other values, so the question is how much "
            "room the shipped choice has, not what it should become.",
            "",
            f"Through the shipped point specifically: holding the warn weight at "
            f"{shipped_warn:.3f}, **every threshold from {row[0]:.2f} to {row[-1]:.2f}** "
            f"decides all {len(results)} cases the same way; holding the threshold at "
            f"{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f}, **every warn weight from "
            f"{column[0]:.3f} to {column[-1]:.3f}** does. Those are contiguous runs, not "
            f"the union of the table's extremes — the corners do not hold together."
            + _edge_note(row, THRESHOLDS, "threshold")
            + _edge_note(column, WARN_WEIGHTS, "warn weight"),
            "",
            "**Read this as a limit on the instrument, not as a licence.** A batch that "
            "cannot distinguish two settings is not saying they are equally good; it is "
            "saying it has no evidence either way. The shipped values are held because "
            "nothing here argues against them, and that is a weaker claim than tuning "
            "would have been — which is why it is stated in these words rather than as "
            "an optimum.",
        ]
    return lines + [""]


def _sweep_critical(results, baseline: dict[str, Verdict]) -> list[str]:
    shipped_warn = config.FLAG_SEVERITY_PENALTY["warn"]
    lines = [
        "## 2. Is the critical weight behaviorally inert?",
        "",
        "A critical disclosure escalates through an independent rule, so its *weight* "
        "should never decide a verdict. Swept across its whole plausible range at the "
        "shipped threshold and warn weight.",
        "",
        "| critical weight | verdicts changed |",
        "| --- | --- |",
    ]
    changes = []
    for critical in CRITICAL_WEIGHTS:
        with _weights(shipped_warn, critical):
            changed = sum(
                1 for r in results
                if _verdict(r, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD)
                is not baseline[r.case.key]
            )
        changes.append(changed)
        lines.append(f"| {critical:.2f} | {changed} |")

    verdict = (
        "**Inert, as argued.** Setting it to 0.00 — charging a critical disclosure "
        "nothing at all — changes no verdict, because every deal carrying one escalates "
        "on the independent rule regardless. This is also the confirmation "
        "`critic.py`'s escalation rule was left open for: the rule does work the score "
        "does not."
        if not any(changes) else
        "**Not inert on this batch** — the weight moves verdicts, which means the "
        "independent critical rule is not covering every case that carries a critical "
        "flag. Investigate before treating the two grounds as redundant."
    )
    return lines + ["", verdict, ""]


def _causal_pair(results, baseline: dict[str, Verdict]) -> list[str]:
    both = [r for r in results
            if all(k in {f.kind for f in r.flags} for k in _CAUSAL_PAIR)]
    lines = [
        "## 3. OQ-1 — does de-duplicating the causal pair move anything?",
        "",
        f"`{_CAUSAL_PAIR[0].value}` is part of *why* `{_CAUSAL_PAIR[1].value}` fires, so "
        "charging both charges cause and effect separately. "
        f"**{len(both)} of {len(results)} cases carry both.**",
        "",
    ]
    if not both:
        return lines + [
            "Nothing to measure on this batch: no case carries both. Under the hybrid "
            "anchor the county-tier fallback fires far less often than it did under FMR, "
            "so the pair that motivated this question has largely stopped co-occurring. "
            "**The question is closed by the anchor change rather than by a re-pricing** "
            "— re-open it if county-tier anchoring becomes common again.",
            "",
        ]

    with _weights(config.FLAG_SEVERITY_PENALTY["warn"],
                  config.FLAG_SEVERITY_PENALTY["critical"]):
        moved = [
            r.case.key for r in results
            if _verdict(r, config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
                        dedupe_causal_pair=True) is not baseline[r.case.key]
        ]
    lines.append(", ".join(f"`{r.case.key}`" for r in both))
    lines.append("")
    lines.append(
        f"**{len(moved)} verdict(s) move if the pair is de-duplicated**"
        + (f": {', '.join(f'`{k}`' for k in moved)}." if moved else
           " — so the double-charge is real arithmetic but costs nothing in behavior, "
           "and de-duplicating it would be a change to the score's meaning made on no "
           "evidence. Held as-is, with the double-charge documented.")
    )
    return lines + [""]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ARTIFACT)
    args = parser.parse_args()

    cases = [c for c in scoring_cases() if c.tier is not Tier.LIVE]
    print(f"Running {len(cases)} predicted, non-live cases in replay mode...", flush=True)
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"  [{index}/{len(cases)}] {case.key}", flush=True)
        result = runner.run_case(case)
        if result.error:
            print(f"      ERROR: {result.error}")
            continue
        results.append(result)

    baseline = _baseline(results)
    escalating = sum(1 for v in baseline.values() if v is Verdict.ESCALATES)

    lines = [
        "# Confidence sensitivity — decision #6 against the eval batch (U8.6)",
        "",
        f"Generated by `scripts/confidence_sensitivity.py` over {len(results)} cases "
        f"with a verdict declared before the run "
        f"(`{VerdictSource.PREDICTED.value}`), of which {escalating} escalate under the "
        "shipped configuration.",
        "",
        "**This measures robustness, not optimality**, and the distinction is the whole "
        "reason the artifact exists. The cases were written knowing the shipped values, "
        "so scoring agreement against them would measure the fixtures rather than the "
        "parameters. Sweeping the parameters over a fixed batch asks a question the "
        "fixtures cannot bias: how far can these numbers move before the system decides "
        "anything differently?",
        "",
        f"Shipped: threshold **{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f}**, "
        f"warn **{config.FLAG_SEVERITY_PENALTY['warn']:.3f}**, "
        f"critical **{config.FLAG_SEVERITY_PENALTY['critical']:.2f}**.",
        "",
    ]
    lines += _sweep_grid(results, baseline)
    lines += _sweep_critical(results, baseline)
    lines += _causal_pair(results, baseline)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nwritten -> {args.out}")


if __name__ == "__main__":
    main()
