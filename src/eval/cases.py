"""The eval harness's case type, and the case set (U8.1).

A case is a listing plus **a claim about what the system should do with it**, written
before the system is run on it. That second half is what separates this from a fixture
directory, and it is the whole reason the harness can be used to tune anything.

Why the declared verdict exists, and why it is written first
--------------------------------------------------------------
U8.6 tunes decision #6's confidence threshold and severity weights, and the instrument
problem it faces is the one that disqualified the demo deals: **they were calibrated to
run clean, so fitting a threshold to them would measure this repository's own fixtures.**
An engineered eval batch has the same defect with the sign reversed — it is calibrated to
*fail*, and a threshold fitted to it is fitted to fixtures just the same.

The way out is to score the threshold against what each case was *supposed* to do rather
than against the flags it produced. So every case declares `verdict` — `REPORTS` or
`ESCALATES` — as part of its definition, and disagreement is triaged by a rule fixed in
advance rather than after seeing which way it went:

  * the target flag fired as designed and the verdict still disagrees → a **tuning signal**;
  * the target flag did not fire → **the case is wrong**, not the threshold.

Reading the system's output and recording it as the intended verdict would produce perfect
agreement and prove nothing. Hence `VerdictSource` below.

Two kinds of verdict, which must not be pooled
------------------------------------------------
The six demo deals and the U4 ablation join this batch (U8.1) so the demo evidence is a row
set in the evaluation rather than a separate pass. But their outcomes are already *measured*
and published — `history/decision_log.md` carries the U7.8 table. Declaring those as
"intended verdicts" would hand U8.6 seven free agreements that were transcribed from the
answer key, quietly inflating any threshold's score.

So a verdict carries its provenance. `PREDICTED` is a claim made before any run and is the
only kind that counts toward U8.6's agreement score. `BASELINE` is a previously measured
outcome, which makes the case a **regression check** — valuable, and evidence of a
different thing. `scoring_cases()` returns the first kind only.

Tiers, and why most cases make no model call
----------------------------------------------
Most flag kinds are raised downstream of extraction, so routing those cases through a live
model would make them slower, non-reproducible and no more truthful (`eval/README.md`).

  * `GOLDEN` — a complete `DealTerms` is supplied and the Extractor is skipped. This needs
    no new mechanism: the pre-flight Planner (#9) already routes past extraction when
    `deal_terms_are_complete()` holds, so a fixture is a deal that arrives already
    extracted.
  * `REPLAY` — extraction actually runs, against recorded responses (`LLM_CACHE_MODE=replay`).
    For the handful of kinds that genuinely originate in the Extractor.
  * `LIVE` — a real model call. The demo deals, and the end-to-end evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from demo_deals import DEMO_DEALS
from state import DealTerms, FlagKind


class Verdict(StrEnum):
    """What the system should do with a case. Declared, not observed."""

    REPORTS = "reports"
    ESCALATES = "escalates"


class VerdictSource(StrEnum):
    """Where a verdict came from — see the module docstring on why this is not cosmetic."""

    # A claim written before the case was ever run. Counts toward U8.6's agreement score.
    PREDICTED = "predicted"
    # A previously measured outcome, making the case a regression check. Excluded from
    # the agreement score, because agreeing with a transcribed answer is not evidence.
    BASELINE = "baseline"


class Tier(StrEnum):
    GOLDEN = "golden"
    REPLAY = "replay"
    LIVE = "live"


@dataclass(frozen=True)
class EvalCase:
    """One listing, one claim about it, and the flag it was built to trip."""

    key: str
    tier: Tier
    verdict: Verdict
    verdict_source: VerdictSource
    # What this case is for, in a sentence. Read by a human reviewing the results table,
    # so it says why the case exists rather than restating its fields.
    note: str

    # The degradation paths this case is engineered to exercise. Empty is legitimate for
    # a demo deal, which exists to be representative rather than to trip anything.
    targets: tuple[FlagKind, ...] = ()

    # Exactly one of these. `listing` runs extraction; `terms` skips it.
    listing: Optional[str] = None
    terms: Optional[DealTerms] = None

    supplied_coords: Optional[tuple[float, float]] = None
    # The U4 ablation switch. A case rather than a command-line flag, so the ungrounded
    # run is a row in the same table as every grounded one.
    retrieval_enabled: bool = True

    def __post_init__(self) -> None:
        if (self.listing is None) == (self.terms is None):
            raise ValueError(
                f"Case {self.key!r}: supply exactly one of `listing` or `terms`. "
                f"`listing` runs the Extractor; `terms` skips it."
            )
        if self.terms is not None:
            self._check_golden_fixture()

    def _check_golden_fixture(self) -> None:
        """A skipped Extractor is also a skipped geocoder, and that trap is silent.

        `config.REQUIRED_DEAL_FIELDS` decides whether the Planner skips extraction, and
        it does **not** include coordinates — reasonably, since a listing that reaches
        the Extractor gets them from `tools/geocoding.py` as an ordinary step (U3). But a
        golden fixture never reaches the Extractor, so nothing derives them. A fixture
        supplying the three required fields and no coordinates therefore skips extraction
        *and* arrives at retrieval with nowhere to search, and the run degrades on
        geography rather than on whatever the case was built to test.

        Caught here rather than left to be diagnosed from a confusing results row: the
        case would still produce output, and the output would look like a finding.
        """
        # Imported here rather than at module scope: `agents.planner` imports `config`
        # and `nodes`, and a case file is also read by tooling that should not need the
        # graph in memory to list what cases exist.
        from agents.planner import deal_terms_are_complete

        if not deal_terms_are_complete(self.terms):
            raise ValueError(
                f"Case {self.key!r}: a `golden` fixture must satisfy "
                f"`deal_terms_are_complete()`, or the Planner will route it through the "
                f"Extractor and the case will not test what it says it tests."
            )
        if self.terms.latitude is None or self.terms.longitude is None:
            raise ValueError(
                f"Case {self.key!r}: a golden fixture must supply latitude and "
                f"longitude. Skipping the Extractor also skips geocoding, so without "
                f"them this case degrades on geography rather than on its target."
            )


# --------------------------------------------------------------------------
# The demo deals, as cases (the U10 absorption)
# --------------------------------------------------------------------------
#
# §6 folded U10 into U8 so the demo evidence and the evaluation evidence come from one
# code path and cannot disagree. This is where that happens: the same six listings
# `main.py --deal` runs, plus the ablation, entering the batch as rows.
#
# **Their verdicts are BASELINE, not PREDICTED**, and every one is transcribed from the
# U7.8 re-measurement in `history/decision_log.md` rather than guessed. That makes them
# regression checks on a published table — if a row moves, either this build changed
# behaviour or that table is stale, and both are worth knowing. What they are not is
# evidence that a confidence threshold is well placed.

_DEMO_BASELINES: dict[str, tuple[Verdict, str]] = {
    "los-angeles": (Verdict.REPORTS, "Dense market, full comp set. U7.8: 0.70, reports."),
    "chicago": (Verdict.ESCALATES, "U7.8: 0.55 on three deal-specific warns — escalates "
                                   "on the score alone, accepted rather than tuned away."),
    "staten-island": (Verdict.ESCALATES, "§2's real-thinness case: zero comps. U7.8: 0.00."),
    "no-geography": (Verdict.ESCALATES, "Address neither geocoder nor centroid can place. "
                                        "U7.8: 0.00."),
    "overpriced": (Verdict.REPORTS, "Deliberate premium to the benchmark, so the "
                                    "asking-price disclosure says something. U7.8: 0.70."),
    "coord-conflict": (Verdict.ESCALATES, "Supplied coords disagree with the address's "
                                          "geocode. U7.8: 0.05."),
}


def demo_cases() -> list[EvalCase]:
    """The six demo deals plus the U4 ablation, as LIVE cases."""
    cases = [
        EvalCase(
            key=key,
            tier=Tier.LIVE,
            verdict=verdict,
            verdict_source=VerdictSource.BASELINE,
            note=note,
            listing=DEMO_DEALS[key].listing,
            supplied_coords=DEMO_DEALS[key].supplied_coords,
        )
        for key, (verdict, note) in _DEMO_BASELINES.items()
    ]
    cases.append(
        EvalCase(
            key="chicago--no-retrieval",
            tier=Tier.LIVE,
            verdict=Verdict.ESCALATES,
            verdict_source=VerdictSource.BASELINE,
            note=(
                "The U4 ablation. U7.8: lands at exactly 0.60 with one critical flag — "
                "the score does not escalate it and the critical-flag rule does, which "
                "is the only live case for that rule. Not reachable by any listing."
            ),
            targets=(FlagKind.RETRIEVAL_DISABLED,),
            listing=DEMO_DEALS["chicago"].listing,
            retrieval_enabled=False,
        )
    )
    return cases


# --------------------------------------------------------------------------
# The engineered cases (U8.2)
# --------------------------------------------------------------------------
#
# Deliberately empty until U8.2. U8.1's coverage census runs against the demo set alone
# first, so U8.2's fixtures are designed against a *measured* gap rather than an assumed
# one — the same ordering the metro-selection work used, and for the same reason.
ENGINEERED_CASES: list[EvalCase] = []


def all_cases() -> list[EvalCase]:
    return demo_cases() + ENGINEERED_CASES


def scoring_cases(cases: Optional[list[EvalCase]] = None) -> list[EvalCase]:
    """The cases whose verdicts U8.6 may legitimately score a threshold against.

    `BASELINE` verdicts are excluded by construction — see the module docstring. This
    function exists so that exclusion is applied in one place and cannot be forgotten at
    the point where it would matter most.
    """
    return [c for c in (cases or all_cases())
            if c.verdict_source is VerdictSource.PREDICTED]
