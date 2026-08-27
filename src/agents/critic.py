"""Critic/Reviewer agent — **PARTIAL in U2**. Cross-agent checks are U7.

Split deliberately, because the two halves of this agent have different dependencies:

- **Built now: flag aggregation into a confidence score, and the human-review
  escalation decision.** These depend only on `state.flags` and on weights that already
  live in `config.FLAG_SEVERITY_PENALTY`. Building them in U2 is what makes the
  `human_review` interrupt reachable at runtime rather than only in a test, and the
  escalation path is the whole point of wiring that node into the skeleton.
- **Stubbed for U7: cross-agent consistency checking**, the part that sets
  `critic_rejected` and drives the rework cycle. In U2 it could not be written in any
  honest form, because the checks worth making needed Valuation and Scenario output and
  neither agent produced any. A consistency check with only one populated input is a
  check that always passes, which §2's own argument rules out — a signal that cannot
  fire conveys nothing.

  **That precondition is now met.** U5 populates `rent_estimate` and `ValuationDetail`;
  U6 populates `scenarios` and `ForecastDetail`. See `_consistency_objections()` below
  for what U7 actually checks, which is not the list U2 anticipated.

`_consistency_objections()` is left as a real function returning an empty list rather
than being omitted, so the rework branch below is present, reachable, and testable by
substituting that one function. The cycle is proven bounded in
`tests/test_flag_propagation.py` that way, which is the U2 obligation; U7 supplies the
objections that make it fire on its own.

Reason/Act/Observe/Decide:

- **Reason.** Determine which upstream outputs are mutually checkable given what
  actually ran, and how much each accumulated flag should cost the deal's confidence.
- **Act.** Run the available consistency checks and aggregate flag severities into a
  single score.
- **Observe.** Compare the score against `config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD`,
  and note whether the rework budget still has room.
- **Decide.** Proceed to the report, send the deal back for one more pass, or escalate
  to a human. The decision is written to state; the routing that acts on it lives in
  `agents/planner.route_after_critic`, never here (§3 — agents communicate only through
  shared state; routing is an edge's job, not a specialist's).
"""

from __future__ import annotations

from typing import NamedTuple

import config
from state import DealState, FlagKind, Severity, flag

AGENT = "critic"


# Flags this agent raises as *consequences* of the score. They are excluded from the
# score's own inputs: a rework pass re-runs the Critic, the reducer appends its previous
# flags to the accumulated list, and counting them would let the score drive itself down
# on each lap of a cycle that exists to improve the deal. Confidence must be a function
# of what the pipeline observed, not of what the Critic previously concluded about it.
_DERIVED_KINDS = frozenset({
    FlagKind.LOW_CONFIDENCE_ESTIMATE,
    FlagKind.REWORK_LIMIT_REACHED,
    # Added U7.4, and it belongs here for both of the reasons above at once. An
    # objection is a conclusion *about* other flags, so counting it charges the same
    # observation twice — the divergence and the relaxation behind it have already been
    # paid for. And a rework lap re-raises it, so it would compound on a cycle whose
    # whole purpose is to improve the deal. Objections escalate through the critical
    # rule instead, which is a decision rather than an arithmetic contribution.
    FlagKind.CRITIC_INCONSISTENCY,
})


def confidence_from_flags(state: DealState) -> float:
    """Aggregate accumulated flags into a single confidence score in [0, 1].

    Starts at full confidence and subtracts a per-severity penalty for every flag
    raised anywhere upstream. Info-severity flags cost nothing by design: they disclose
    a mechanism (rent was FMR-anchored; a metro-level appreciation tier was used)
    rather than a weakness, and charging them would make the score fall on runs where
    nothing went wrong.

    The weights are PROVISIONAL and tuned in U8 — they live in `config` for exactly
    that reason (§8). The shape of the function is the U2 commitment; the numbers are
    not.

    **Identical observations are counted once (U7.4).** `state.flags` is append-only
    across rework laps, deliberately, so the raw run history stays inspectable — the same
    reason the Summarizer de-duplicates `stub_nodes` at render time rather than in the
    reducer. But a rework re-runs every upstream agent, and each re-raises the flags it
    raised before, so a summed score would fall on every lap without anything about the
    deal having changed. A deal does not get worse because the pipeline looked at it
    twice.

    Measured before this was added: a deal carrying two warn flags scored 0.70, then 0.40
    on the first rework lap and 0.10 on the second. It escalated on collapsed confidence
    before `MAX_REWORKS` was ever reached, which made `REWORK_LIMIT_REACHED` unreachable
    and left the cycle bounded by an arithmetic accident rather than by the explicit
    counter §3 requires. That the two happened to agree is exactly what makes this the
    kind of defect worth finding deliberately.

    De-duplication is on `(source_agent, kind, detail)`. Not on `kind` alone: one
    retrieval pass can legitimately raise `RELAXED_MATCH_CRITERIA` twice for two
    different relaxations, and those are two real observations that should both be
    charged. Identical text from the same agent is the same observation reported again.
    """
    # TODO(U8): the budget this function has to spend may already be committed before a
    # deal is read. Measured across three demo deals, Aug 26, 2026: each carried **exactly
    # two warn flags** before anything deal-specific was observed, so each started from
    # 0.70 rather than 1.00. The pair is not fixed — `los-angeles` and `chicago` raised
    # `fmr_anchor_county_level` and `forecast_branches_near_tied`; `overpriced` raised
    # `fmr_anchor_county_level` and `comps_spatially_concentrated` and no near-tie at all.
    # **Which makes the floor the finding rather than the pair.** Three deals is not proof
    # of a floor, but if one holds, 0.30 of the 0.40 separating a clean run from
    # `HUMAN_REVIEW_CONFIDENCE_THRESHOLD` is spent before the deal is read, the effective
    # threshold is 0.90 while `config` says 0.60, and exactly one further warn of any kind
    # can land before escalation. That is what took `chicago` from 0.70 to 0.55 and into
    # human review when U7.3 added one ordinary disclosure (accepted, not a regression:
    # the comps did drift). All three flags arrived in U5/U6, after the §6 demo table was
    # last measured.
    #
    # Deferred to U8 rather than fixed here because the fix depends on which reading is
    # true and only the eval batch exercises the range — the five demo deals were
    # calibrated to run clean. Re-pricing warn downward treats a symptom and moves every
    # deal at once. If instead a disclosure is genuinely unconditional, it is reporting a
    # *mechanism* rather than a weakness, which is the definition this docstring already
    # gives for info severity — it would cost nothing and still print. What it takes: run
    # the eval batch, count each FlagKind's incidence across it, and demote or re-price on
    # that evidence. A penalty that every deal pays is not discriminating between deals.
    seen: set[tuple[str, FlagKind, str]] = set()
    penalty = 0.0
    for f in state.flags:
        if f.kind in _DERIVED_KINDS:
            continue
        signature = (f.source_agent, f.kind, f.detail)
        if signature in seen:
            continue
        seen.add(signature)
        penalty += config.FLAG_SEVERITY_PENALTY.get(f.severity, 0.0)
    return max(0.0, min(1.0, 1.0 - penalty))


def _consistency_objections(state: DealState) -> list[Objection]:
    """Cross-agent contradictions found in this run. **U7 populates this.**

    Returns an empty list today, so `critic_rejected` is never set and the rework cycle
    never fires on its own in this build.

    The four checks §1 originally named were reviewed against the built system while
    planning U7, and **the list did not survive contact with it.** Recorded here rather
    than silently replaced, because a TODO that names work the build has since made
    impossible is worse than no TODO:

    1. *Rent estimate against the comp set's distribution* — **already built, and not
       here.** `agents/valuation_rent.py` raises `RENT_DIVERGES_FROM_COMPS` as its own
       Observe step, using `ValuationDetail.comp_implied_rent_p25/median/p75`. The
       Critic **consumes that flag** rather than recomputing it. Two agents deriving one
       fact independently is two agents that can disagree about it.
    2. *Value estimate against the listing price* — **dead.** Decision #15 made
       `DealState.value_estimate` permanently `None`; nothing in this build writes it.
       This TODO predates that decision.
    3. *Scenario bands against the base they branch from* — **live, TODO(U7).** Both
       `ForecastDetail.projection_base_price`/`_rent` and the `Scenario` bands are
       populated by U6.
    4. *Comp-source concentration* — **live, TODO(U7).** The corpus is 91%
       RentDigs.com, so eight comps from one feed are not eight independent
       observations; `Comp.listing_source` exists to make that detectable. Must not
       double-count with `COMPS_SPATIALLY_CONCENTRATED`, which is a different
       concentration and already fires.

    TODO(U7): implement 3 and 4, plus two checks U2 did not anticipate because the state
    they read did not exist yet — the forecast's projection base against the figures it
    claims to project from, and comp attribute drift against the subject after
    relaxation.

    Two further comparisons — the listing's *stated* rents against `rent_estimate`, and
    its asking price against `ValuationDetail.benchmark_median_sale_price` — are
    deliberately **not** objections in U7. They ship as Summarizer disclosures instead,
    because the rent one currently reports ~-29% on every demo deal: FMR is a
    40th-percentile rent while the model predicts ~1.40x FMR, so the gap measures a
    percentile mismatch rather than the deal. TODO(U8): promote both once Zillow ZORI
    settles which baseline is right.

    This stays the single seam the Critic calls and the tests substitute, even though it
    currently delegates to one family of checks. TODO(U7.3) adds comp attribute drift
    alongside `_interaction_objections`, and each family stays independently testable.
    """
    return _interaction_objections(state)


# ---------------------------------------------------------------------------
# Interaction checks (U7)
# ---------------------------------------------------------------------------
#
# Every other agent checks what it has the data to check and flags its own step. The
# Critic is the only node that sees all of those flags at once, and that is the whole of
# what it can contribute that nothing upstream can: **whether a combination of
# disclosures changes what the result means.**
#
# This is not extra penalty. `confidence_from_flags` is a sum, and a sum can only ever
# say *more doubt*. These say something a sum cannot express — *this measurement does not
# mean what it appears to mean* — which is a different claim and needs a different
# mechanism.
#
# Where the gap is, with the weights as they stand (info 0.00, warn 0.15, critical 0.40,
# threshold 0.60): one warn lands at 0.85 and reports, two warns land at 0.70 and report,
# three warns land at 0.55 and already escalate, and any critical escalates on its own
# independent ground. **So the window these exist for is exactly two warns** — plus any
# number of INFO flags, which cost nothing by design.
#
# Each is a pure function of accumulated state. No LLM call, no network, no corpus, no
# model — which is why they are hermetically testable in a way the checks U7 originally
# planned were not.


class Objection(NamedTuple):
    """One cross-agent contradiction, with what the Critic should do about it.

    `severity` rather than a bare string because these need CRITICAL to escalate, and
    `retryable` because a rework pass re-runs the pipeline and most of these cannot be
    fixed by re-running anything — re-reading the same listing will not densify a thin
    market or add a street number to an address that lacks one. Carrying the distinction
    here keeps `agents/planner.route_after_critic` from having to infer it.
    """

    message: str
    severity: Severity
    retryable: bool = False


def _kinds(state: DealState) -> frozenset[FlagKind]:
    return frozenset(f.kind for f in state.flags)


def _interaction_objections(state: DealState) -> list[Objection]:
    """Contradictions that exist only in the *combination* of upstream disclosures.

    **Not yet wired — `_consistency_objections()` is the seam, and U7.4 joins them.**
    Landed separately so this can be reviewed as arithmetic over flag sets, before the
    routing consequences of raising a CRITICAL from inside the Critic are taken on.

    Ordered strongest first. Each returns at most one objection, and they are allowed to
    co-occur: a deal that trips two of these has two independent reasons its rent
    cross-check is not saying what it appears to say.

    TODO(U8): **these read the accumulated flag list as if it described the current
    pass, and on a rework lap it does not.** `DealState.flags` carries an `operator.add`
    reducer so the raw run history stays inspectable, and nothing on a `Flag` says which
    pass raised it. Measured: a rework that *succeeds* — the geocoder answers, coordinates
    resolve to a parcel, the divergence clears, neither agent raises anything new — still
    trips I3 from pass one's flags, sets `critic_rejected`, and tells the reader the comps
    were drawn around a city centroid when they no longer were.

    Accepted for U7 rather than fixed, deliberately: the loop is bounded by
    `config.MAX_REWORKS`, and every path this can reach ends at human review, so the one
    audience guaranteed to see the stale sentence also sees the flag list beside it. The
    fix is to stamp each flag with the `planner_invocations` that produced it and evaluate
    only the current pass — a §5 change touching every agent that raises a flag, which is
    why it is scheduled at U8 and sits on §6's cut list at 2a rather than being taken here.
    Note the wrinkle it has to handle: an agent skipped on a rework raises nothing, so
    absence must not read as *cleared* when it means *not re-examined*. `state.plan`
    records which agents ran.
    """
    kinds = _kinds(state)
    objections: list[Objection] = []

    # The comp cross-check is the only independent check on the rent estimate in this
    # system, so every interaction below is about when its verdict stops being readable.
    if FlagKind.RENT_DIVERGES_FROM_COMPS not in kinds:
        return objections

    # I1 — the comp set came back unlike the subject on an attribute the model prices on.
    #
    # **Keys on the measured consequence, not on the concession** (repointed U7.3). This
    # read `RELAXED_MATCH_CRITERIA` until the drift was actually measured, and that flag
    # records only that the retrieval loop dropped a filter. Dropping one *permits*
    # dissimilar comps without producing them: a set that relaxed and came back similar
    # anyway is not degraded, and objecting to it would treat a concession as a result.
    # `COMPS_OUTSIDE_MATCH_CRITERIA` is raised by the retrieval agent only when comps
    # actually fell outside the bedroom or size band originally searched.
    #
    # Why it matters that the attribute is one the model prices on:
    # `config.RENT_MODEL_FEATURES` is ("bedrooms", "bathrooms", "square_feet"), so the
    # comp median then describes a different population than the model predicted for, and
    # a gap between them is the expected consequence of the widening rather than evidence
    # about the estimate.
    if FlagKind.COMPS_OUTSIDE_MATCH_CRITERIA in kinds:
        objections.append(
            Objection(
                "The comp set was widened on an attribute the rent estimate depends "
                "on — bedrooms, bathrooms or floor area — so the comparable-implied "
                "median describes a different kind of unit than the one being priced. "
                "The divergence "
                "between them is the expected consequence of that relaxation, not a "
                "finding about the estimate — the rent figure has no usable independent "
                "check on this deal.",
                Severity.CRITICAL,
            )
        )

    # I2 — the comp median is a point sample.
    #
    # Decision #15 measured Chicago's busiest coordinate carrying 150 listings whose
    # rents span $760-$6,995, CV 48.7% against 49.7% for the whole metro. A median over
    # comps clustered like that carries almost no locational information, so diverging
    # from it is weak evidence in either direction.
    if FlagKind.COMPS_SPATIALLY_CONCENTRATED in kinds:
        objections.append(
            Objection(
                "The comparables cluster at one location, so their median is a point "
                "sample rather than a market summary — a single coordinate in this "
                "data can carry 150 listings whose rents span $760 to $6,995. "
                "Divergence from a median that dispersed is weak evidence about the "
                "estimate in either direction.",
                Severity.CRITICAL,
            )
        )

    # I3 — the comps moved and the model did not.
    #
    # Weaker than the two above, and the reason is worth stating rather than leaving to
    # be rediscovered: the rent model is **location-blind below the county** (§2). Its
    # features carry no market identifier and its anchor is county-level FMR, so the
    # subject's coordinates do not affect the estimate at all — only which comps are
    # retrieved. A centroid fallback therefore moves the comp set to the city's centre of
    # listing density while leaving the estimate untouched. That degrades the comparison
    # and tells you which branch of the divergence flag's own either/or is the likely one;
    # it does not void it. WARN rather than CRITICAL for exactly that reason.
    geocode_fallbacks = {
        FlagKind.COORDINATES_FROM_CITY_CENTROID,
        FlagKind.GEOCODER_SERVICE_UNAVAILABLE,
    }
    if kinds & geocode_fallbacks:
        # Only the service-outage cause is worth a rework: re-running the Extractor
        # re-attempts the Census call, and the same listing may resolve to a parcel on a
        # later run. An address with no street number will not, however often it is
        # retried. U7.1b split the flag kinds so this branch reads the cause instead of
        # parsing the message.
        retryable = FlagKind.GEOCODER_SERVICE_UNAVAILABLE in kinds
        objections.append(
            Objection(
                "The comps were retrieved around the city's center of listing density "
                "rather than around this property, while the rent model — which is "
                "location-blind below the county — produced the same estimate it would "
                "have for any address in this county. The divergence is therefore more "
                "readable as the comps describing a different neighborhood than as the "
                "estimate being wrong for this property."
                + (
                    " The geocoder was unreachable rather than the address being "
                    "unresolvable, so a re-run may resolve it to a parcel."
                    if retryable
                    else ""
                ),
                Severity.WARN,
                retryable=retryable,
            )
        )

    return objections


def critic_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    objections = _consistency_objections(state)
    confidence = confidence_from_flags(state)

    # Each objection carries its own severity — an interaction that voids the rent
    # cross-check is not the same weight as one that merely degrades it, and flattening
    # them to WARN would discard the distinction U7.2 exists to draw.
    flags = [
        flag(AGENT, FlagKind.CRITIC_INCONSISTENCY, objection.message, objection.severity)
        for objection in objections
    ]

    # Escalate on either of two independent grounds. A critical flag is sufficient on
    # its own, and not only as a contributor to the score:
    #
    # Severity.CRITICAL is defined in the report as "the estimate should not be relied
    # on without addressing this". A deal carrying one that still reaches a report as a
    # normal result contradicts what the system says about its own flag. That is not
    # hypothetical arithmetic — the U2 demo produced it. One critical flag costs 0.40,
    # landing confidence at exactly 0.60, and `0.60 < 0.60` is false, so the
    # zero-comps Chicago and no-coordinates runs both reported without escalating. The
    # threshold is a judgment about *accumulated* uncertainty and is the right tool for
    # a pile of warnings; it is the wrong tool for a single disqualifying observation.
    #
    # TODO(U8): decision #6 sets both the 0.60 threshold and the severity weights as
    # PROVISIONAL, and **U8 is where they get tuned, not U7** — the eval batch is what
    # exercises the range, and the five demo deals were calibrated to run clean, so they
    # cannot. U7 lands the mechanism; U8 supplies the numbers.
    #
    # Confirm this rule when they are tuned — if the weights were retuned so that one
    # critical flag falls clearly below the threshold, the two conditions would coincide
    # and this one could fold back into the score. Keeping them separate is deliberate
    # even then: it makes the guarantee independent of the weights.
    low_confidence = confidence < config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD
    # Over the flags this pass *raises* as well as the ones it inherited. Reading only
    # `state.flags` was a latent defect until U7.4: nothing the Critic raised could
    # trigger the Critic's own escalation, so a CRITICAL objection would have set no
    # route and reported as a normal result — the same class of miss as the U2 boundary
    # case this rule was written for.
    has_critical = any(
        f.severity == Severity.CRITICAL for f in (*state.flags, *flags)
    )

    if low_confidence or has_critical:
        reason = (
            f"Confidence {confidence:.2f} is below the "
            f"{config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f} threshold"
            if low_confidence
            else f"Confidence {confidence:.2f} clears the threshold, but a "
                 f"critical-severity disclosure was raised"
        )
        flags.append(
            flag(
                AGENT,
                FlagKind.LOW_CONFIDENCE_ESTIMATE,
                f"{reason}; routing to human review rather than reporting as a "
                f"normal result.",
                Severity.WARN,
            )
        )

    # `critic_rejected` means "another pass could fix this", not "something is wrong".
    # The distinction is the whole reason `Objection.retryable` exists. A rework re-runs
    # the pipeline, so it is worth spending only where a second pass can change the
    # input: a geocoder that was unreachable may answer on the next call. It can do
    # nothing about a thin market, a comp set relaxed onto a different unit type, or an
    # address that has no street number — those are facts about the deal, and looping on
    # them burns the budget and arrives back here one full pipeline later with the same
    # objection. Non-retryable objections still escalate, through their severity.
    rejected = any(objection.retryable for objection in objections)
    budget_exhausted = rejected and state.rework_count >= config.MAX_REWORKS
    if budget_exhausted:
        flags.append(
            flag(
                AGENT,
                FlagKind.REWORK_LIMIT_REACHED,
                f"Objections remain after {state.rework_count} rework pass(es), the "
                f"configured maximum. Escalating rather than looping further.",
                Severity.WARN,
            )
        )

    return {
        "confidence_score": confidence,
        "critic_rejected": rejected,
        "needs_human_review": low_confidence or has_critical or budget_exhausted,
        "flags": flags,
        "stub_nodes": [AGENT],
    }
