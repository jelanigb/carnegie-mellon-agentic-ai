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
from eval.data import golden_fixtures
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


class Fault(StrEnum):
    """An external failure a case asks the harness to simulate. **Declared, never hidden.**

    Added U8.2, for one kind the batch could not otherwise reach at all.
    `FlagKind.REWORK_LIMIT_REACHED` needs an objection the Critic marks `retryable`, and
    exactly one objection is ever marked so: the I3 branch in
    `agents/critic._interaction_objections`, gated on `GEOCODER_SERVICE_UNAVAILABLE`. That
    flag is raised only when the Census *request itself fails*
    (`tools/geocoding.geocode`) — not when it runs and finds no match, which is the
    distinction U7.1b built precisely so the rework cycle could be spent on an outage and
    not on an address that will never resolve.

    Neither tier can produce that. A golden fixture supplies coordinates, so U8.1b's
    geography path takes the county-only branch and never calls the geocoder; a replay case
    calls it and it succeeds, because `LLM_CACHE_MODE=replay` covers *model* calls and the
    Census lookup is an ordinary HTTP request. So the outage can be injected or it can go
    unexercised, and leaving the system's only bounded-retry path untested through the unit
    that tunes `MAX_REWORKS` is the worse of the two.

    **A field on the case rather than a fixture that quietly patches something**, and that
    is the whole design. The injection appears in the case definition, in the results
    table, and in the report, so a reader can see that the row exercised a *simulated*
    outage rather than a real one. A harness that patches a module inside a fixture would
    produce the identical row and let it read as a naturally-occurring failure — which is
    the same class of overstatement `verdict_source` exists to prevent one row over.

    The patch enters through the same door a real outage does: `geocode_census` raises
    `GeocodingError`, `geocode()` catches it and sets `primary_unavailable`. Nothing forces
    the flag directly, so the case still tests the branch that chooses between
    `GEOCODER_SERVICE_UNAVAILABLE` and `COORDINATES_FROM_CITY_CENTROID` rather than
    asserting the outcome of it.

    **`LLM_UNAVAILABLE`, added U8.3, for the same class of reason.**
    `FlagKind.EXTRACTION_UNAVAILABLE` is raised when `agents.extractor._extract_terms`
    never receives a response at all — `tools.llm_client.LlmClient.complete` raises
    `LlmError` before there is anything to validate, let alone record. A recording is a
    replay of a *response*; there is no response here to replay, so the two mechanisms
    that cover every other extraction flag (a real listing, a recorded call) both come up
    empty for this one, which is exactly `Fault`'s admission criterion.

    Patched one layer above the raw transport call, same as `GEOCODER_OUTAGE`:
    `LlmClient.complete` is the primary call (`geocode_census`'s analogue), so the
    Extractor's own `except LlmError` branch still does the deciding. The patch is
    class-level rather than per-instance because `_extract_terms` builds a fresh
    `LlmClient()` per call and there is no instance to reach beforehand.

    Left unrestricted rather than expired after one call: `agents.scenario_forecast` also
    builds an `LlmClient` and would hit the same patched method later in the same run.
    That is not a leak to guard against — it is the honest consequence of the model
    actually being down. `scenario_forecast` already catches `LlmError` and raises its own
    `FORECAST_UNAVAILABLE`, so the row shows a real, gracefully-degraded multi-flag outage
    rather than a run that dies partway through.
    """

    GEOCODER_OUTAGE = "geocoder_outage"
    LLM_UNAVAILABLE = "llm_unavailable"


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
    # An external failure the harness simulates for this case, or None. See `Fault`.
    injects: Optional[Fault] = None
    # OQ-16, meaningful only alongside `injects=Fault.GEOCODER_OUTAGE`: where the centroid
    # fallback lands, overriding the real corpus-wide (city, state) average `geocode()`
    # would otherwise compute. U8.2's search over 9 markets x 16 configurations found the
    # real city-wide centroid never both diverges from the rent estimate *and* stays clear
    # of a critical or a third warn — divergence and comp dispersion trade off directly,
    # since both are driven by how thin the matching supply is at whatever point the
    # centroid lands on. This lets a case place the fallback at a specific, already-known
    # point instead — see `runner._case_environment`, which patches
    # `tools.geocoding.city_centroid` to return it.
    geocoder_fallback_override: Optional[tuple[float, float]] = None

    def __post_init__(self) -> None:
        if (self.listing is None) == (self.terms is None):
            raise ValueError(
                f"Case {self.key!r}: supply exactly one of `listing` or `terms`. "
                f"`listing` runs the Extractor; `terms` skips it."
            )
        if self.terms is not None:
            self._check_golden_fixture()
        if self.injects is not None and self.terms is not None:
            # A fixture supplies its terms directly, so U8.1b's geography path takes the
            # county-only branch and the Extractor never calls the model or the geocoder
            # at all — either injection would be a silent no-op and the case would report
            # a clean pass for a failure that never happened. Rejected at import for the
            # same reason `_check_golden_fixture` is: the run would still produce a
            # plausible row.
            raise ValueError(
                f"Case {self.key!r}: a declared fault needs the seam it patches to "
                f"actually be reached, so this case must supply `listing` rather than "
                f"`terms`. A fixture skips the Extractor entirely."
            )
        if self.geocoder_fallback_override is not None and self.injects is not Fault.GEOCODER_OUTAGE:
            raise ValueError(
                f"Case {self.key!r}: `geocoder_fallback_override` only means something "
                f"when the geocoder is faulted (`injects=Fault.GEOCODER_OUTAGE`) — "
                f"otherwise the real Census geocoder runs and this is never consulted."
            )

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
    "los-angeles": (Verdict.REPORTS, "Dense market, full comp set. U7.8: 0.70, reports. "
                                     "0.85 since U8.6c demoted the pairing near-tie to "
                                     "info; verdict unchanged."),
    # **Re-baselined Aug 29, 2026 (U8.6c), and the reason is a deliberate severity change
    # rather than drift.** U7.8 measured 0.55 / escalates on three deal-specific warns,
    # one of which was `forecast_branches_near_tied` at the *pairing* level. U8.6c demoted
    # that variant to INFO on the finding that both tied pairings appear in the reported
    # scenario set regardless, so nothing a reader sees turned on it. Chicago now carries
    # two warns and reports at 0.70. Recorded here rather than left as a standing
    # mismatch, because the old row is no longer the behaviour this build has — but note
    # what it cost: this was the demo set's one "escalates on accumulated warns alone,
    # nothing broken" case, and the set no longer has one.
    "chicago": (Verdict.REPORTS, "U7.8: 0.55, escalated on three warns. Re-baselined at "
                                 "U8.6c: 0.70, reports — the third warn was the pairing "
                                 "near-tie, now info-severity."),
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
# Written against U8.1's *measured* coverage gap rather than an assumed one, which is why
# the harness was built before the cases. The list the plan first carried was written from
# assumption and was wrong in both directions — it named a kind the demo set already
# covers and missed six it does not.
#
# **How each verdict was derived, and why that is not the same as having run the case.**
# Q1 requires the verdict to be a claim made in advance, because reading the system's
# output and recording it as the intention produces a perfect score and proves nothing.
# The fixtures below *were* run while they were being designed — that is what it takes to
# confirm a case trips the kind it targets at all — so "written before the run" needs to
# mean something more precise than a promise.
#
# It means this: **every verdict below is derived from the target flag's severity and the
# shipped escalation rule, and from nothing else.** A CRITICAL target escalates, because
# `agents/critic.critic_agent` escalates on a critical flag independently of the score. A
# lone WARN target costs 0.15 against a 0.60 threshold, so it reports. An INFO target costs
# nothing, so it reports. That derivation is mechanical, it can be checked by a reader
# against `config.FLAG_SEVERITY_PENALTY`, and it does not consult what the case actually
# did.
#
# The two are allowed to disagree, and one of them does before this file is ever run —
# `chicago-five-bedroom`, whose target is INFO and which escalates anyway. That is the
# instrument working. The triage rule was fixed in advance and applies unchanged: the
# target fired, so the disagreement is a **tuning signal**, not a broken case. Recording
# the observed outcome as the intended one would have hidden exactly the finding the batch
# exists to produce.
#
# **Two cases predict `reports`, and that is deliberate.** A batch of nothing but
# escalating cases can be scored 100% by a threshold of 1.0, so agreement would measure
# nothing. `la-ordinary-duplex` and `chicago-uptown-duplex` are what make the agreement
# figure two-sided.

# Shared with `scripts/record_retry_exhausted_fixture.py`, which hand-authors that
# case's recordings against this exact text — see `chicago-retry-exhausted` below and
# that script's module docstring for why a live `--record` run cannot make them. A
# module constant rather than two copies is what keeps the case and its recordings from
# being able to drift apart: the recorded cache keys are hashes of this string, so an
# edit here without a re-run of that script turns every committed recording into a
# `CacheMiss`.
RETRY_EXHAUSTED_LISTING = (
    "For sale: 3310 W Belmont Ave, Chicago, IL 60618. Well-maintained 2-unit building, "
    "2 bed / 1 bath per unit, approx 1,000 sq ft each. Asking $475,000."
)

ENGINEERED_CASES: list[EvalCase] = [
    # --- The control -------------------------------------------------------
    EvalCase(
        key="la-ordinary-duplex",
        tier=Tier.GOLDEN,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        note=(
            "The control. An ordinary two-bedroom duplex in the densest indexed market, "
            "targeting nothing. Without at least one case that should not escalate, a "
            "threshold of 1.0 would score perfectly and the agreement figure would be "
            "measuring only how many cases were built to fail."
        ),
        terms=golden_fixtures.LA_ORDINARY.terms,
    ),

    # --- Valuation ---------------------------------------------------------
    EvalCase(
        key="la-oversized-loft",
        tier=Tier.GOLDEN,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.RENT_ESTIMATE_UNAVAILABLE,),
        note=(
            "Two bedrooms across 5,000 sq ft drives the predicted rent-to-FMR ratio "
            "outside the band the model's own training set was bounded to, so the "
            "estimate is refused rather than reported. Escalates because the refusal is "
            "critical-severity: there is no rent figure, and a report without one is not "
            "an ordinary result."
        ),
        terms=golden_fixtures.LA_OVERSIZED_LOFT.terms,
    ),
    EvalCase(
        key="chicago-five-bedroom",
        tier=Tier.GOLDEN,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.FMR_BEDROOM_CAP_EXCEEDED,),
        note=(
            "Five bedrooms per unit, past the top of HUD's published schedule, so the "
            "anchor is substituted and disclosed. Predicted to **report**: that "
            "disclosure is info-severity and costs the confidence score nothing by "
            "design. Sited in Cook County, which publishes Small Area FMRs, so the "
            "county-level anchoring warning that three of the six demo deals share is "
            "absent here and cannot account for the outcome either way."
        ),
        terms=golden_fixtures.CHI_FIVE_BEDROOM.terms,
    ),
    EvalCase(
        key="chicago-uptown-duplex",
        tier=Tier.GOLDEN,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.RENT_DIVERGES_FROM_COMPS,),
        note=(
            "**Closes the open question about whether anything still trips the rent-comp "
            "divergence check** — it moved from firing on two of five subjects to none "
            "when ZIP-resolution anchoring landed, and a flag nothing can raise would "
            "corrupt the coverage claim. Nothing about this property is engineered: an "
            "ordinary two-bedroom duplex whose comps match it on bedrooms and floor area, "
            "in a market whose ZIP-level Fair Market Rent is high. The disagreement is "
            "between the model and the comps alone, which is the only form in which this "
            "flag says anything. Predicted to report: one warn-severity disclosure sits "
            "well above the threshold."
        ),
        terms=golden_fixtures.CHI_UPTOWN_ORDINARY.terms,
    ),

    # --- Critic interaction checks (U7.2's I1 and I3) ----------------------
    #
    # Two cases rather than one, because the Critic's interaction checks are three
    # separate judgments and a single case would exercise whichever fired first. These
    # reach the same flag kind by different routes, which is what makes a failure in
    # either of them localizable.
    EvalCase(
        key="la-three-bedroom-comp-drift",
        tier=Tier.GOLDEN,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA, FlagKind.CRITIC_INCONSISTENCY),
        note=(
            "The comp set is widened to find eight three-bedroom units and comes back "
            "unlike the subject on an attribute the rent estimate prices on, so the "
            "comparable-implied median describes a different kind of unit than the one "
            "being priced. Escalates because that objection is critical-severity: the "
            "rent figure has no usable independent check on this deal."
        ),
        terms=golden_fixtures.LA_THREE_BEDROOM.terms,
    ),

    # --- The critical-flag escalation rule, isolated -----------------------
    EvalCase(
        key="chicago-uptown-oversized",
        tier=Tier.GOLDEN,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.CRITIC_INCONSISTENCY,),
        note=(
            "**Built to isolate the critical-disclosure rule from the confidence score, "
            "and it no longer does — recorded rather than quietly re-purposed.** A "
            "critical disclosure sends a deal to a human on its own ground, not only by "
            "dragging the score down. This listing was engineered so the deal cleared "
            "the threshold comfortably (measured 0.70 at design, 0.55 once recorded) and "
            "escalated on the critical alone.\n\n"
            "Since U8.4b/U8.4c it measures **0.30**: the drift-corrected rent changed the "
            "scoring prompt and the Tree-of-Thought search now empties its beam at depth "
            "2, adding a second, *critical* `forecast_unavailable` — so the score is far "
            "below threshold and the two escalation grounds agree again. The case still "
            "passes (its target fires, verdict `escalates`), but it is no longer evidence "
            "for the rule's independence. **`chicago--no-retrieval` still carries that "
            "evidence** — it is the row the results table marks with †, landing at exactly "
            "0.60 with one critical — so the batch has not lost the property, only this "
            "listing-reachable demonstration of it. U7.8's request for a *deal* that "
            "isolates the rule is therefore open again, and is U8.6's to re-site."
        ),
        terms=golden_fixtures.CHI_UPTOWN_OVERSIZED.terms,
    ),
    EvalCase(
        key="cleveland-triplex",
        tier=Tier.GOLDEN,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.COMPS_SPATIALLY_CONCENTRATED, FlagKind.CRITIC_INCONSISTENCY),
        note=(
            "The same objection reached the other way. Nothing about this triplex is "
            "unusual; the market is. Cleveland is the one indexed metro where the comp "
            "set collapses onto a single coordinate, so the median that disagrees with "
            "the estimate is a point sample rather than a market summary. Escalates on "
            "the objection's severity, not on the score."
        ),
        terms=golden_fixtures.CLE_ORDINARY.terms,
    ),
    EvalCase(
        key="ny-bedstuy-triplex",
        tier=Tier.GOLDEN,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED,
                 FlagKind.COMPS_SPATIALLY_CONCENTRATED),
        note=(
            "The market-error disclosure (OQ-3), tripped by a listing with a real comp "
            "set rather than by the `staten-island` demo's zero-comp accident, where the "
            "flag is invisible against a report already escalating for an unrelated "
            "reason. Both targets are warn-severity, so the mechanical rule declares "
            "`reports`; New York's other standing warn (county-level FMR anchoring) "
            "stacks with them, which is itself the sort of thing U8.6's tuning run "
            "should see rather than a case defect to fix."
        ),
        terms=golden_fixtures.NY_BEDSTUY_ORDINARY.terms,
    ),

    # --- The rework cycle, under a declared outage -------------------------
    #
    # The one case in this set that is not a golden fixture, and the reason is structural
    # rather than a preference: see `Fault`. A rework needs a *retryable* objection, the
    # only retryable objection is gated on the geocoder having been unreachable, and a
    # fixture that carries its own coordinates never calls the geocoder at all. So this
    # case supplies a listing, lets extraction and geography actually run, and declares
    # the outage it simulates.
    EvalCase(
        key="chicago-geocoder-outage",
        tier=Tier.REPLAY,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.GEOCODER_SERVICE_UNAVAILABLE, FlagKind.REWORK_LIMIT_REACHED),
        injects=Fault.GEOCODER_OUTAGE,
        geocoder_fallback_override=(41.975320, -87.656463),
        note=(
            "**A simulated address-lookup outage, declared by the case rather than "
            "waiting for a real one.** The address is never tested, so comparables are "
            "drawn around the fallback coordinates instead. The override lands the "
            "fallback at the address's own real Census geocode (verified live, U8.2) "
            "rather than Chicago's corpus-wide average, so this case isolates the "
            "*outage* — only the ability to verify the address is removed, not the "
            "geography a working geocoder would have found anyway.\n\n"
            "**Closes `rework_limit_reached`, the one kind U8.2 and U8.3 left uncovered "
            "(U8.5/OQ-16).** That subsection found the real corpus-wide centroid never "
            "both diverges and stays clear of a critical or a third warn, and this case "
            "was originally recorded against it — landing exactly there, and the second "
            "target was withdrawn. `geocoder_fallback_override` was built to place the "
            "fallback somewhere already known to diverge instead of leaving it to the "
            "corpus average.\n\n"
            "**Building it surfaced a second, real defect, fixed alongside it: "
            "`extractor._supplied_coordinates` was reading a *previous pass's* "
            "centroid fallback as if a caller had deliberately supplied it.** On the "
            "first rework, that reclassified `GEOCODER_SERVICE_UNAVAILABLE` as "
            "`GEOCODING_UNAVAILABLE` — a different kind, non-retryable, and dishonest "
            "about provenance (the report would say the coordinates were 'used as "
            "given' when the system had derived them itself). It also broke "
            "`_geocode_is_worth_retrying`'s read of the just-completed pass, so a third "
            "attempt was never planned. Restricted to the deal's first pass, since a "
            "second pass is only ever reached through this one retryable objection, "
            "which itself requires no caller-supplied coordinates to have existed — see "
            "that function's docstring for the full argument.\n\n"
            "**Verdict derivation departs from the mechanical severity rule the other "
            "cases use, and says so rather than pretending otherwise.** Confidence "
            "clears the threshold at 0.70 (two unique warns; `rework_limit_reached` "
            "itself is excluded from the score as a Critic-derived flag, same as "
            "`critic_inconsistency`) and no critical fires. Escalation here comes from "
            "a *third* ground `critic_agent` sets independently of both — "
            "`budget_exhausted`, once the retryable objection survives `MAX_REWORKS` "
            "reworks unresolved. `chicago--no-retrieval` is the only other row this "
            "batch has where confidence and escalation disagree, and there the reason is "
            "the critical-flag rule; this is the third independent escalation ground, "
            "not a repeat of that one.\n\n"
            "**The listing price ($640,000) is not part of what this case is "
            "engineered to show, and is picked empirically rather than derived.** "
            "`scenario_forecast`'s Tree-of-Thought scorer is not perfectly "
            "deterministic even at temperature 0 — an earlier call in the chain "
            "(which evidence to pull) varies enough between live attempts to change "
            "the downstream scoring prompt — so some price points land a mirror-image "
            "pairing (rent-up/price-down vs. rent-down/price-up) close enough to tie, "
            "raising `forecast_branches_near_tied` as an unrelated third warn that "
            "front-loads escalation before the rework budget is spent. This price was "
            "found clean across three replay runs; it carries no significance beyond "
            "that. Once recorded, replay is exact — the non-determinism only affects a "
            "fresh live call, never a committed recording."
        ),
        listing=(
            "For sale: 5100 N Kenmore Ave, Chicago, IL 60640. Uptown two-flat, 2 bed / "
            "1 bath per unit, approx 950 sq ft each. Vintage details, rear porches, "
            "shared laundry in the basement. Current tenants pay $1,800 and $1,850 per "
            "month. Asking $640,000."
        ),
    ),

    # --- Recorded extractions (U8.3): the kinds that genuinely originate in the ------
    # --- Extractor or in geography resolution, so the model or the geocoder has to ---
    # --- actually run rather than being skipped by a golden fixture. -----------------
    #
    # Five of the six kinds U8.2's census routed here; the sixth, geocoder_service_
    # unavailable, closed in U8.2 itself via Fault.GEOCODER_OUTAGE and needed no further
    # case. See eval/README.md's "Recording and replaying" section for the mechanics.
    EvalCase(
        key="la-unpriced-triplex",
        tier=Tier.REPLAY,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.UNRESOLVED_FIELD,),
        note=(
            "The listing states the address, unit count and every physical attribute, "
            "but never states a price — 'contact listing agent' is the only thing said "
            "about it. Predicted to report: `unit_count` is given as '3-unit', which "
            "the extraction system prompt's rule 3a treats as stated rather than "
            "inferred, so this case does not also trip `assumed_field_value`.\n\n"
            "**Measured `escalates` since U8.4b, and kept as a declared mismatch rather "
            "than re-sited.** The prediction stands on the mechanical rule — a lone WARN "
            "target reports — but ZIP 90089 is a USC campus ZIP that Zillow's rent index "
            "does not cover, so the deal also pays `rent_drift_correction_unavailable`, "
            "which with `fmr_anchor_county_level` makes three warns and 0.55. The target "
            "fired, so the triage rule fixed in advance classes this a **tuning signal**. "
            "Re-siting to a covered ZIP was considered and rejected: it would make the "
            "batch systematically avoid the ZIPs where the system degrades, which is the "
            "same 'calibrated to run clean' failure the demo deals are criticized for. "
            "See U8.6's finding on market-structural warns stacking on deal-specific "
            "targets. **Sited in Los Angeles rather "
            "than Cleveland deliberately** — a first attempt at Cleveland reproduced "
            "(across three re-runs, so structural rather than a network flake) the same "
            "comp-concentration critical objection `cleveland-triplex` already "
            "evidences, which would have buried this flag's own cost under a confound "
            "this case was not built to measure."
        ),
        listing=(
            "For sale: 3400 S Vermont Ave, Los Angeles, CA 90089. 3-unit building, 2 "
            "bed / 1 bath per unit, approx 900 sq ft each. New roof in 2023, updated "
            "electrical panel. Current tenants pay $1,450/month per unit. Contact "
            "listing agent for price."
        ),
    ),
    EvalCase(
        key="la-duplex-near-usc",
        tier=Tier.REPLAY,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.ASSUMED_FIELD_VALUE,),
        note=(
            "'Duplex' names a building type but no number, so the extraction system "
            "prompt's rule 3 requires the model to infer unit_count=2 and record the "
            "basis rather than read it. Predicted to report on the mechanical rule: a "
            "lone WARN target costs 0.15.\n\n"
            "**Measured `escalates` since U8.4b, and kept as a declared mismatch** for "
            "the same reason as `la-unpriced-triplex` a few blocks over: ZIP 90007's "
            "rent-index coverage begins 31 months after the training vintage — too late "
            "to anchor a before/after comparison — so `rent_drift_correction_unavailable` "
            "joins `fmr_anchor_county_level` and the target for three warns at 0.55. "
            "Target fired, so this is a tuning signal, not a broken case."
        ),
        listing=(
            "For sale: 1425 W Adams Blvd, Los Angeles, CA 90007. Charming duplex near "
            "USC, each unit 2 bed / 1 bath, approx 850 sq ft. Long-term tenants, rent "
            "roll available on request. Asking $780,000."
        ),
    ),
    EvalCase(
        key="chicago-retry-exhausted",
        tier=Tier.REPLAY,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.EXTRACTION_RETRY_EXHAUSTED,),
        note=(
            "**Recordings for this case are hand-authored, not live-recorded** — see "
            "`scripts/record_retry_exhausted_fixture.py` for why: `ListingExtraction` "
            "has no required fields, so an ordinary model response validates and "
            "provoking three organic failures on demand is not reproducible. The three "
            "committed responses are real cache entries under the real prompts "
            "`call_with_schema`'s retry loop generates; nothing about replay is "
            "special-cased for this case. Predicted to escalate: retry exhaustion is "
            "critical-severity, independent of the score, and no deal terms survive it."
        ),
        listing=RETRY_EXHAUSTED_LISTING,
    ),
    EvalCase(
        key="cleveland-model-outage",
        tier=Tier.REPLAY,
        verdict=Verdict.ESCALATES,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.EXTRACTION_UNAVAILABLE,),
        injects=Fault.LLM_UNAVAILABLE,
        note=(
            "**A simulated model outage, declared by the case** — see "
            "`Fault.LLM_UNAVAILABLE`. Nothing about this listing is engineered; the "
            "content is unreachable in this run regardless of what it says. Predicted "
            "to escalate: an unreachable model is critical-severity and no deal terms "
            "are extracted. The same patched outage also reaches "
            "`scenario_forecast`'s later calls, so this row is expected to carry a "
            "second critical disclosure (`forecast_unavailable`) — the honest "
            "consequence of the model actually being down for the whole run, not a "
            "second target this case claims to isolate."
        ),
        listing=(
            "For sale: 1840 Coventry Rd, Cleveland, OH 44118. 2-unit building, 2 bed / "
            "1 bath per unit, approx 950 sq ft each. Asking $310,000."
        ),
    ),
    EvalCase(
        key="chicago-unmatched-street",
        tier=Tier.REPLAY,
        verdict=Verdict.REPORTS,
        verdict_source=VerdictSource.PREDICTED,
        targets=(FlagKind.COORDINATES_FROM_CITY_CENTROID,),
        note=(
            "**The one U8.3 case that keeps a real network dependency on every run.** "
            "`coordinates_from_city_centroid` fires when the Census geocoder runs and "
            "cleanly finds no match — a naturally-reachable path, unlike the outage "
            "cases above, so `Fault` (reserved for paths nothing else can reach) does "
            "not apply. Verified live before this case was written: "
            "`geocode_census('99999 Nonexistent Fantasy Ln', 'Chicago', 'IL', None)` "
            "returns `None` (no match, not an error), and Chicago is well represented "
            "in the corpus so the centroid fallback resolves. Predicted to report: two "
            "warns measured (`coordinates_from_city_centroid` plus "
            "`comps_spatially_concentrated` — even Chicago's density collapses somewhat "
            "when comps are drawn from one fixed centroid rather than the property "
            "itself), both well under threshold."
        ),
        listing=(
            "For sale: 99999 Nonexistent Fantasy Ln, Chicago, IL. 2-unit building, 2 "
            "bed / 1 bath per unit, approx 1,050 sq ft each. Asking $410,000."
        ),
    ),
]


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
