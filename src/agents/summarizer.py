"""Summarizer agent — produces the investor-facing report. Real in U2; polished in U9.

Built for real in the walking skeleton rather than stubbed, and §6 gives the reason
directly: the previous plan built the Summarizer last, which would have left the
component producing the system's actual output as the least-exercised and most
schedule-exposed piece in the build. Inverting that is the point of a walking skeleton.
U9 polishes wording and layout; the structure and the disclosure rules are settled here.

**The disclosure rules are the design, not the formatting.** §1 requires this agent to
"surface all upstream flags prominently, not just bottom-line numbers," so three
properties of the rendering are load-bearing rather than stylistic:

1. **Flags appear before the numbers.** A caveat printed underneath a figure is a
   caveat most readers never reach. Critical and warn flags are rendered above the
   estimates they qualify.
2. **Every flag is rendered, never counted.** "3 warnings" tells a reader that
   something is wrong and denies them the ability to judge whether it matters. Each
   flag prints its source agent, kind, and full detail text.
3. **Absence is stated, not omitted.** A section with no data says the section is
   unbuilt or the input was missing. Silently dropping it would let a report about a
   deal with no valuation look like a report about a deal that needed none.

Reason/Act/Observe/Decide:

- **Reason.** Determine what this run actually established and what it did not — which
  estimates exist, which flags qualify them, and whether a human reviewed the deal.
- **Act.** Render the report in disclosure-first order: escalation status, then flags by
  severity, then findings, then the comp evidence they rest on.
- **Observe.** Nothing here re-derives an upstream figure. The Summarizer reports; if it
  computed, two components could disagree about the same number and the report would be
  the one lying.
- **Decide.** Mark the run complete — unless a human reviewed it, in which case that
  status stands, since "reviewed" and "cleared automatically" are different outcomes and
  the record should not conflate them.
"""

from __future__ import annotations

from collections import Counter
from typing import Optional

import config
from tools.llm_client import LlmClient, LlmError
from state import (
    RECOMMENDATION_LABEL,
    Comp,
    ConfidenceBreakdown,
    DealState,
    DealStatus,
    Flag,
    FlagScope,
    ForecastDetail,
    Recommendation,
    Scenario,
    Severity,
    count_area_positioned,
    scope_of,
)

AGENT = "summarizer"

# What the verdict line says when the rule reached a verdict with nothing to list under
# it. Only `PROCEED` reaches this in practice — it is the absence of every finding rather
# than a finding of its own — but the others carry a line so a missing reason can never
# render as an empty sentence.
_DEFAULT_VERDICT_LINE = {
    Recommendation.PROCEED: (
        "Nothing in the asking price or the rent evidence argues against this deal."
    ),
    Recommendation.PROCEED_WITH_CAUTION: (
        "Something about the pricing or the rent evidence warrants a closer look."
    ),
    Recommendation.DO_NOT_PROCEED: (
        "The asking price is not supported by the rent evidence available for it."
    ),
    Recommendation.NO_RECOMMENDATION: (
        "There was not enough evidence to judge whether this is a good deal."
    ),
}

_SEVERITY_ORDER = (Severity.CRITICAL, Severity.WARN, Severity.INFO)

# Counted nouns for the heading's severity mix. Separate from `_SEVERITY_LABEL` below,
# which names the *group heading* a reader sees above a block — "Disclosure (5)" reads
# correctly as a heading and wrongly as a count ("5 disclosure").
_SEVERITY_MIX_NOUN = {
    Severity.CRITICAL: "critical",
    Severity.WARN: "warning",
    Severity.INFO: "informational",
}

_SEVERITY_LABEL = {
    Severity.CRITICAL: "Critical",
    Severity.WARN: "Warning",
    Severity.INFO: "Disclosure",
}

# What each severity means for a reader deciding how much weight to put on the numbers
# below it. Stated in the report itself so the labels are not left to interpretation.
_SEVERITY_GUIDANCE = {
    Severity.CRITICAL: "the estimate below should not be relied on without addressing this",
    Severity.WARN: "materially widens the uncertainty on the estimate below",
    Severity.INFO: "a mechanism used, disclosed for transparency; not a weakness",
}


def _money(value: float | None) -> str:
    return f"${value:,.0f}" if value is not None else "—"


def _join(items: list[str]) -> str:
    """Render a list the way a sentence reads it: "a", "a and b", "a, b and c"."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


# The two halves of the disclosure list, and what each one asks of a reader (U8.6d). The
# split is by *subject*, not by severity — severity still orders within each half — because
# "the listing never stated a price" and "no rent index covers this county" call for
# different responses even at identical weight. One is a gap someone can close; the other
# is a standing property of the data, the same for every listing in that market.
_SCOPE_HEADING = {
    FlagScope.DEAL: "About this property",
    FlagScope.MARKET: "About our coverage of this market",
}

_SCOPE_GUIDANCE = {
    FlagScope.DEAL: (
        "specific to this listing or this run — some of these may be resolvable"
    ),
    FlagScope.MARKET: (
        "true of every listing in this market, not of this property in particular; "
        "they still widen the uncertainty on the numbers below"
    ),
}


def _confidence_arithmetic(breakdown: Optional[ConfidenceBreakdown]) -> list[str]:
    """Show what the deduction was made of, not just what it totalled (U8.6d).

    A reader could always see the flags and the score; what was missing was the sum
    connecting them, so "confidence 0.55" arrived as a verdict rather than as a result.
    One line, immediately under the score, splitting the deduction the same way the
    disclosure list below is split — so the two halves of the report agree about what this
    deal's doubt is made of.

    Silent when nothing was deducted: "0.00 deducted, 0.00 from each of two things" is
    noise on a clean run, and the score of 1.00 already says it.
    """
    if breakdown is None or breakdown.total_deducted <= 0:
        return []
    return [
        f"*{breakdown.total_deducted:.2f} deducted from a starting 1.00: "
        f"{breakdown.deducted_deal:.2f} from this property, "
        f"{breakdown.deducted_market:.2f} from how much is known about this market. "
        f"Both halves are itemized under Disclosures below.*",
        "",
    ]


def _verdict_lines(state: DealState) -> list[str]:
    """The two axes, as two lines that never merge. **The largest readability change in U9.**

    The report has always stated axis 1 — whether the system can stand behind its own
    numbers — and readers have always taken it for axis 2, whether the property is worth
    buying. `staten-island` is where that misreading is most costly: it escalates because
    no comparables were found, while asking **17% below its ZIP median**, so a reader who
    saw "🚩 Escalated to human review" and concluded the deal was bad had it exactly
    backwards.

    Rendered as one quote block with two labelled lines rather than as two separate
    banners, because adjacency is what teaches the distinction — a reader sees the same
    deal answered two ways in two sentences and learns that the questions differ. Kept
    above everything else, including the model-written summary beneath it, so the
    reproducible statement is the first thing on the page and the prose supports it rather
    than the other way round.

    **"System check" was replaced Sept 2, 2026, because it named the instrument rather
    than the consequence.** A reader meeting *"System check — escalated to human review"*
    has to work out what a system check is and what escalating one implies for them; the
    line now says who has to do what before this report goes anywhere — *"Flagged by
    system — needs human review before sharing with investors"*. That is also exactly
    what the escalation means operationally, under either routing rule in
    `design/personas.md`: a deal-substance flag waits on the agent (persona b) before it
    reaches the investor (persona c), and an infrastructure flag waits on IT (persona a),
    and in neither case should the report be forwarded first. The cleared branch is
    worded to match, so the two read as one question answered two ways rather than as two
    unrelated banners.

    Reader-facing throughout (§8): no flag names, no thresholds, no field names.
    """
    lines: list[str] = []
    rec = state.recommendation
    escalated = state.status == DealStatus.NEEDS_REVIEW or state.needs_human_review

    if rec is not None:
        headline = rec.reasons[0] if rec.reasons else _DEFAULT_VERDICT_LINE[rec.verdict]
        lines.append(f"> **Recommendation — {RECOMMENDATION_LABEL[rec.verdict]}.** {headline}")
        lines.append(">")

    if escalated:
        # Deliberately does not name the confidence threshold as the cause. A critical
        # disclosure escalates on its own, above the threshold — see agents/critic.py —
        # so a banner that always blamed the score would misreport that case.
        lines.append(
            "> 🚩 **Flagged by system — needs human review before sharing with "
            "investors.** This deal did not clear the system's automated checks on its "
            "own; the disclosures below say why. **This is a statement about the "
            "evaluation, not about the property.**"
        )
    else:
        lines.append(
            "> ✅ **Cleared by system — no human review needed before sharing.** The "
            "figures below passed the system's own checks without a human having to "
            "release them."
        )

    if state.human_review_note:
        lines.append(">")
        lines.append(f"> **Reviewer note:** {state.human_review_note}")
    lines.append("")

    # The cross-check, and only where a second opinion exists *and* differs. Printed
    # outside the quote block so it reads as a footnote to the verdict rather than as a
    # third axis. **Disclosed rather than resolved** — the rule decides, always, and
    # saying which reading the reader is holding is the product here.
    if rec is not None and rec.cross_check_disagrees:
        rationale = f" Its reasoning: {rec.model_rationale}" if rec.model_rationale else ""
        lines.append(
            f"*An independent review of the same evidence reached a different "
            f"conclusion — **{RECOMMENDATION_LABEL[rec.model_verdict]}**.{rationale} The "
            f"recommendation above follows this system's stated rule, which is the one "
            f"that decides; the disagreement is disclosed here rather than resolved. A "
            f"deal the two readings agree on is a more comfortable one to hold than a "
            f"deal they split over.*"
        )
        lines.append("")

    return lines


_LEDE_SYSTEM = (
    "You write the opening paragraph of an investment report on a residential "
    "multi-family property. You are given the conclusions the report has already "
    "reached. Restate them for a reader who has not yet scrolled — you do not reach "
    "conclusions of your own, add figures that are not given to you, or soften or "
    "strengthen anything you are handed. Three or four sentences, plain words, no "
    "headings, no bullet points, no markdown.\n\n"
    # Added after a live run described 'limited comparable sales' on a deal with eight
    # comparables and no such disclosure. It had generalised from a retrieval note rather
    # than inventing a figure, which the rule above did not cover — a summary that
    # characterises the evidence is reaching a conclusion, which is the one thing this
    # role does not do.
    "Describe only what is listed below. Do not characterise the evidence as limited, "
    "thin, strong or weak unless a line below says so in those terms, and do not name a "
    "disclosure that is not listed.\n\n"
    # Second correction from the same live run. This report carries two different
    # comparable sets — rental listings, which produce the rent estimate, and recorded
    # sales, which produce the price benchmark — and the summary described the first as
    # the second. That is not a style problem: an investor reading "seven comparable
    # sales" would believe the price figure rested on seven transactions when it rests on
    # 148.
    "This report uses two different kinds of comparable. Comparable rentals are rental "
    "listings and produce the rent estimate; recorded sales produce the price benchmark. "
    "Never call one the other."
)


def _lede_prompt(state: DealState) -> str:
    """The report's own conclusions, in the rounded figures the report prints.

    **Rounded reader-facing numbers only, never a raw float.** OQ-18 records a replay row
    that missed its recordings for reasons never established, and a full-precision float
    in a prompt is a cache key that moves whenever an upstream computation shifts in its
    last decimal place. Everything here is a rounded percentage, a whole dollar figure or
    a short string, so this adds no second instance of that fragility.

    Everything quoted is already printed somewhere below, which is what makes the
    constraint in `_LEDE_SYSTEM` checkable: the summary is additive, and a reader who
    skips it loses nothing.
    """
    terms = state.deal_terms
    rec = state.recommendation
    escalated = state.status == DealStatus.NEEDS_REVIEW or state.needs_human_review

    parts = [f"Property: {terms.full_address or 'address not resolved'}."]
    if terms.price:
        parts.append(f"Asking price: {_money(terms.price)}.")
    if terms.unit_count:
        parts.append(f"Units: {terms.unit_count}.")
    if state.rent_estimate is not None:
        parts.append(f"Estimated rent: {_money(state.rent_estimate)} per month per unit.")

    if rec is not None:
        parts.append(f"The recommendation is: {RECOMMENDATION_LABEL[rec.verdict]}.")
        for reason in rec.reasons:
            parts.append(f"Reason given: {reason}")
        if rec.cross_check_disagrees:
            parts.append(
                "An independent review of the same evidence reached a different "
                f"conclusion, {RECOMMENDATION_LABEL[rec.model_verdict]}, and the report "
                "discloses that disagreement without resolving it."
            )

    parts.append(
        "The evaluation was escalated to a human reviewer because it did not clear the "
        "system's automated checks."
        if escalated
        else "The evaluation cleared the system's automated checks without human review."
    )

    counts = Counter(f.severity for f in state.flags)
    if state.flags:
        parts.append(
            f"{len(state.flags)} disclosures were raised: "
            f"{counts[Severity.CRITICAL]} critical, {counts[Severity.WARN]} warning, "
            f"{counts[Severity.INFO]} informational."
        )
        # **No disclosure text is quoted, and removing it closed a whole failure class.**
        # Two live runs mis-relayed excerpts in ways the instructions did not stop:
        # "limited comparable data" on a run whose comp set was full and whose
        # disclosures were all mechanism notes, and "zero comparable sales within two
        # miles" for a *rental* comp count — a report that carries both rental
        # comparables and recorded sales cannot afford that word swapped, since it moves
        # the price benchmark from 148 transactions to none.
        #
        # The excerpts were never in this section's brief: it says what the property is,
        # what the report recommends and why, and whether a human reviewed it. Counts
        # carry the shape of the disclosures, and every one of them is rendered in full
        # immediately below the summary — so nothing is hidden by leaving the prose to
        # what it was asked for. Prompt wording was tried twice first; this is the fix
        # that does not depend on a draw (OQ-17).

    parts.append(f"Comparable rentals found: {len(state.comps)}.")
    parts.append("")
    parts.append(
        "Write the opening paragraph. Say what the property is, what the report "
        "recommends and why, and whether a human reviewer was involved. Do not invent "
        "any figure that is not above, and do not describe the individual disclosures — "
        "they are listed in full directly beneath what you write."
    )
    return "\n".join(parts)


def _lede_section(state: DealState) -> list[str]:
    """A short written summary above the report. **Additive, and it decides nothing.**

    **It renders the verdict the rule computed; it does not reach one.** The recommendation
    is a pure function in `agents/critic.recommend` for the reason OQ-17 measured — this
    model scores an identical prompt 0.05 on one call and 0.95 on the next — and a summary
    that could restate the verdict differently would put that variance back into the one
    line a reader takes away. The prompt is handed the conclusion and asked to relay it.

    Sits *below* the verdict lines rather than above them, so the reproducible statement
    is the first thing on the page and the prose supports it.

    **On failure it renders a sentence, not a flag.** A 31st `FlagKind` would break U8's
    30-of-30 coverage census unless some declared fault could reach it, and more
    fundamentally every other flag in this system *propagates* — it is raised in one node
    and consumed downstream. A flag raised in the terminal node has no consumer but the
    report already printing it, so the flag mechanism would be doing nothing the sentence
    does not already do.
    """
    if not config.SUMMARY_NARRATIVE_ENABLED:
        return []

    try:
        text = LlmClient().complete(
            _lede_prompt(state),
            model=config.MODEL_SUMMARIZER,
            system=_LEDE_SYSTEM,
        )
    except (LlmError, RuntimeError, OSError):
        text = None

    if not text or not text.strip():
        return [
            "## Summary",
            "",
            "*A written summary could not be generated for this run; the disclosures "
            "and figures below are unaffected.*",
            "",
        ]
    return ["## Summary", "", text.strip(), ""]


def _verdict_reasons_block(state: DealState) -> list[str]:
    """The rest of the reasoning behind the verdict, under the model's summary.

    The first reason is already on the verdict line; this carries any others. Silent when
    there is nothing left to say, which is the ordinary case for `Proceed` — that verdict
    is the absence of findings rather than a finding of its own, and inventing a sentence
    to fill the space would tell a reader something the rule did not conclude.
    """
    rec = state.recommendation
    if rec is None or len(rec.reasons) < 2:
        return []
    return ["**Also behind this recommendation:**", ""] + [
        f"- {reason}" for reason in rec.reasons[1:]
    ] + [""]


def _flag_section(flags: list[Flag]) -> list[str]:
    """Every flag, grouped by what it is *about*, then by severity within that.

    **Grouped by subject rather than only by severity as of U8.6d.** The previous ordering
    was severity alone, which put a warning about the county's rent index next to a warning
    about this building's comp set and left a reader to work out that only one of them
    describes the deal in front of them. It never dropped anything — rule 2 of the module
    docstring stands, every flag is rendered in full — but it made the list harder to act
    on the longer it got.

    Property-scoped disclosures print first, deliberately: they are the ones a reader might
    do something about, and the report's job is to put what matters where it is read.
    """
    if not flags:
        return [
            "## Disclosures",
            "",
            "**None.** This run completed without relaxing any criterion, falling back "
            "to any coarser data source, or leaving any required field unresolved.",
            "",
        ]

    counts = Counter(f.severity for f in flags)
    mix = ", ".join(
        f"{counts[sev]} {_SEVERITY_MIX_NOUN[sev]}"
        for sev in _SEVERITY_ORDER
        if counts[sev]
    )
    lines = [f"## Disclosures — {len(flags)} ({mix})", ""]
    lines.append(
        f"{len(flags)} disclosure(s) were raised during this evaluation. Each is "
        "listed in full below, grouped by whether it describes this property or the "
        "data available for its market, and ordered most severe first within each. "
        "Entries that describe a mechanism rather than a weakness are collapsed; "
        "anything that qualifies a number below is open."
    )
    lines.append("")

    for scope in (FlagScope.DEAL, FlagScope.MARKET):
        in_scope = [f for f in flags if scope_of(f.kind) is scope]
        if not in_scope:
            continue
        lines.append(f"### {_SCOPE_HEADING[scope]} ({len(in_scope)})")
        lines.append("")
        lines.append(f"*{_SCOPE_GUIDANCE[scope].capitalize()}.*")
        lines.append("")
        for severity in _SEVERITY_ORDER:
            matching = [f for f in in_scope if f.severity == severity]
            if not matching:
                continue
            lines.append(
                f"**{_SEVERITY_LABEL[severity]} ({len(matching)})** — "
                f"{_SEVERITY_GUIDANCE[severity]}"
            )
            lines.append("")
            for f in matching:
                lines.extend(_disclosure_entry(f, severity))
            lines.append("")

    return lines


def _first_sentence(text: str) -> str:
    """The disclosure's opening clause, for the collapsed line a reader scans."""
    head = text.split(". ")[0].rstrip(".").strip()
    return head if head else text.strip()


def _disclosure_entry(flag: Flag, severity: Severity) -> list[str]:
    """One disclosure, collapsed or open according to whether a reader may skip it.

    **Progressive detail, and the split is by severity rather than by length** (U9.4). The
    architect's finding was that a reader seeing many of these reports meets the same
    boilerplate every time and the substance is buried in it — on the Los Angeles deal all
    three disclosures are info-severity mechanism notes, and they are identical on every
    run in that market.

    Info-severity entries collapse to their opening clause; **critical and warn stay
    open**. That keeps both of the module docstring's load-bearing rules intact rather
    than trading one away: nothing moves below the numbers it qualifies (rule 1), and
    nothing is reduced to a count (rule 2) — the full text is present in every case, and
    what changes is only whether a reader has to scroll past text that says the same thing
    on every report in this market.

    `<details>` renders as a disclosure widget wherever this report is actually read by
    its audience — on GitHub, where the committed sample reports live, and in the
    Streamlit surface, which passes it to `st.markdown`. A terminal shows the tags, and
    that is the developer's surface rather than the investor's.
    """
    if severity is not Severity.INFO:
        return [
            f"- **`{flag.kind}`** — {flag.detail}  ",
            f"  *raised by:* `{flag.source_agent}`",
        ]
    head = _first_sentence(flag.detail)
    # A disclosure whose whole text is one sentence would otherwise print itself twice —
    # once as the collapsed line and again as the body underneath it.
    body = [f"{flag.detail}", ""] if flag.detail.rstrip(". ") != head else []
    return [
        "<details>",
        f"<summary><b><code>{flag.kind}</code></b> — {head}</summary>",
        "",
        *body,
        f"*raised by:* `{flag.source_agent}`",
        "</details>",
        "",
    ]


def _comps_section(comps: list[Comp], radius_miles: float, iterations: int) -> list[str]:
    if not comps:
        return [
            "## Comparable Rentals",
            "",
            "**No qualifying comparables were retrieved.** Any rent figure in this "
            "report is therefore ungrounded in local market evidence. See the "
            "disclosures above for what the retrieval loop attempted.",
            "",
        ]

    lines = [
        "## Comparable Rentals",
        "",
        f"{len(comps)} comparable listing(s) retrieved within {radius_miles:.1f} miles "
        f"after {iterations} retrieval pass(es).",
        "",
        "| Listing ID | Rent | Beds | Baths | Sq Ft | Distance | Similarity | Source |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in comps:
        lines.append(
            f"| `{c.listing_id}` | {_money(c.rent)} | {c.beds} | {c.baths:g} | "
            f"{c.square_feet:,.0f} | "
            f"{c.distance_miles:.{config.COMP_DISTANCE_DECIMALS}f} mi | "
            f"{c.similarity_score:.3f} | {c.listing_source or '—'} |"
        )
    lines.append("")

    # Source concentration. §5 records that the corpus is 91% RentDigs.com, so a comp
    # count overstates independence whenever one aggregator supplies most of the set.
    # Disclosed here rather than left for a reader to notice by scanning the column.
    sources = Counter(c.listing_source or "unknown" for c in comps)
    top_source, top_count = sources.most_common(1)[0]
    if len(sources) == 1:
        lines.append(
            f"**Source concentration:** all {len(comps)} comparables come from a single "
            f"feed (`{top_source}`). They are less independent than the count suggests."
        )
    elif top_count / len(comps) >= 0.75:
        lines.append(
            f"**Source concentration:** {top_count} of {len(comps)} comparables come "
            f"from one feed (`{top_source}`) across {len(sources)} sources total."
        )
    else:
        lines.append(
            f"**Source concentration:** drawn from {len(sources)} distinct sources."
        )
    lines.append("")

    # Location precision — the spatial counterpart to source concentration above, and
    # disclosed for the same reason. 92% of the corpus carries no street address, and
    # those rows sit on a city-area placeholder coordinate rather than a parcel, so a
    # distance column can imply a precision the underlying data does not have. Stated
    # here so a reader sees it beside the numbers rather than having to infer it from
    # repeated distances.
    area_positioned = count_area_positioned(comps)
    if area_positioned == len(comps):
        lines.append(
            f"**Location precision:** none of these {len(comps)} comparables carries a "
            f"street address in the source data; each is positioned at a city-area "
            f"coordinate. Distances are approximate and should be read as "
            f"*within this market*, not as measured separations."
        )
    elif area_positioned:
        lines.append(
            f"**Location precision:** {area_positioned} of {len(comps)} comparables "
            f"are positioned at a city-area coordinate rather than a street address; "
            f"their distances are approximate."
        )
    else:
        lines.append(
            f"**Location precision:** all {len(comps)} comparables carry a street "
            f"address in the source data."
        )
    lines.append("")

    return lines


def _build_status_section(stub_nodes: list[str]) -> list[str]:
    """Discloses which nodes ran as placeholders.

    Printed at the top, at the same prominence as a critical flag, because a reader who
    does not know the valuation is unbuilt will read its absence as "no value could be
    determined for this property" — a statement about the deal rather than about the
    software. Kept out of the flag stream on purpose; see `DealState.stub_nodes`.
    """
    if not stub_nodes:
        return []
    # De-duplicated here rather than in the reducer, so a node re-run by the rework
    # cycle still appears once in the report while the raw history stays in state.
    unique = sorted(set(stub_nodes))
    return [
        "> ⚠️ **Provisional build.** These agents ran as stubs or partial "
        "implementations and did not produce their full output: "
        + ", ".join(f"`{name}`" for name in unique)
        + ". Sections fed by them are unbuilt, not empty — each is "
        "scheduled for a later stage of this build.",
        "",
    ]


def _benchmark_section(state: DealState, detail) -> list[str]:
    """The sale-price benchmark, framed as a reference rather than an estimate.

    **The framing is the whole point of this section, not its wording.** Whichever tier
    supplies it, the figure is a median over *other* properties' transactions and says
    nothing about this property's square footage, unit count or condition. Printed in the
    findings table it would read as a value estimate; printed here, next to the asking
    price it is meant to be read against, it reads as what it is.

    **Two tiers since U8.8, and the section says which one it is reading**, because the
    reader's response differs: a neighborhood median is a comparison they can act on,
    and a metro-wide one describes a 2-unit duplex and a 4-unit building forty miles
    apart identically. When the local figure exists the metro figure is printed beneath
    it as contrast rather than dropped — the gap between them is information, and on this
    project's own demo listings it is the visible consequence of #11 having set their
    asking prices *from* the metro median.
    """
    lines = ["### Market benchmark", ""]

    if detail is None or detail.benchmark_median_sale_price is None:
        reason = (detail.benchmark_unavailable_reason if detail else None) or (
            "The valuation step did not run."
        )
        lines.extend([f"**Not available.** {reason}", ""])
        return lines

    local = detail.benchmark_tier == "zip"
    if local:
        lines.append(
            f"Typical **{detail.benchmark_zip_definition}** sale in **ZIP "
            f"{detail.benchmark_zip}**: "
            f"**{_money(detail.benchmark_median_sale_price)}**, the median of "
            f"{detail.benchmark_zip_n_sales:,} recorded sales since "
            f"{detail.benchmark_zip_window_start} "
            f"({detail.benchmark_zip_attribution})."
        )
    else:
        lines.append(
            f"Typical **Multi-Family (2-4 unit)** sale in the {detail.benchmark_metro} "
            f"metro: **{_money(detail.benchmark_median_sale_price)}**, the median over "
            f"the last {detail.benchmark_periods_averaged} monthly periods "
            f"(~{detail.benchmark_homes_sold_per_period:,.0f} sales per period, Redfin)."
        )

    if state.deal_terms.price:
        drift = (state.deal_terms.price - detail.benchmark_median_sale_price) / (
            detail.benchmark_median_sale_price
        )
        side = "above" if drift >= 0 else "below"
        lines.append(
            f"This listing asks {_money(state.deal_terms.price)} — "
            f"**{abs(drift):.0%} {side}** that benchmark."
        )

    lines.append("")
    if local and detail.benchmark_metro_median_sale_price:
        wide = detail.benchmark_metro_median_sale_price
        spread = (detail.benchmark_median_sale_price - wide) / wide
        lines.append(
            f"For contrast, the median across the whole {detail.benchmark_metro} metro is "
            f"{_money(wide)} (Redfin, 2-4 unit) — this neighborhood runs "
            f"**{abs(spread):.0%} {'above' if spread >= 0 else 'below'}** it. The "
            f"neighborhood figure is the one used above, because a metro-wide median "
            f"describes properties an hour apart identically."
        )
        lines.append("")
    elif detail.benchmark_local_unavailable_reason:
        lines.append(f"*{detail.benchmark_local_unavailable_reason}*")
        lines.append("")

    caveat = (
        "The records behind it are other properties' sales in this ZIP over the period "
        "named, with no adjustment for size, unit count or condition — and the local "
        "definition of a multi-family sale is the one quoted above, which differs "
        "between markets because the counties publishing the records define it "
        "differently."
        if local
        else "The source is pre-aggregated to one median per metro per month and "
        "exposes no individual sales, so it carries no square footage, unit count or "
        "condition — the same figure describes every 2-4 unit property in the metro."
    )
    lines.extend([
        f"> **This is not an estimate of this property's value.** {caveat} It is a "
        f"market reference for reading the asking price against, and nothing more.",
        "",
    ])
    return lines


def _rent_basis_section(state: DealState, detail) -> list[str]:
    """How the rent figure was reached, and whether the comps agreed with it.

    Rendered even when the cross-check did not run. A report that silently omits the
    check whenever it fails would show its working only on the runs where the working
    looked good, which is the opposite of what disclosure is for.

    **Two false claims corrected here Aug 30, 2026 (U11.5 item 1), and they are the only
    ones on that list a reader could see.** This paragraph said "A linear regression" —
    the estimator has been gradient boosting since #18 — and "on a held-out slice", which
    described the single 20% split #18 replaced with k-fold cross-validation plus a
    full-data refit. The second is the subtler error: under the new protocol every row is
    scored exactly once by a fold that never saw it, so the figure is stronger evidence
    than "a held-out slice" implies, and the per-metro n is the market's full row count
    rather than a fifth of it. Both are stated in plain words rather than named, on this
    file's rule that reader-facing text carries no vocabulary the reader cannot resolve.

    **Their identifiers were renamed at U8.10 (U11.5 item 2), a pass behind this one.**
    `ValuationDetail.model_mae_dollars` and `TrainingReport.mae_dollars` had carried
    FMR-and-holdout names describing an anchor #19 retired and a protocol #18 replaced.
    The second is serialized into the persisted bundle and read back by string key, so it
    took a retrain rather than an edit; the architect took the retrain over a both-keys
    read, since the shim would have protected an artifact that is not in the repository.
    """
    if detail is None or state.rent_estimate is None:
        return []

    lines = ["### How the rent figure was reached", ""]

    if detail.model_mae_dollars is not None:
        trained = (
            f", trained {detail.model_trained_at:%b %d, %Y}"
            if detail.model_trained_at else ""
        )
        lines.append(
            f"A gradient-boosted tree model over bedrooms, bathrooms and square "
            f"footage, fit to {detail.model_training_rows:,} listings{trained}. Every "
            f"listing was scored by a version of the model that had not been shown it, "
            f"and on that basis it missed by "
            f"**{_money(detail.model_mae_dollars)}/mo on average** "
            f"({detail.model_mae_ratio:.3f} in ratio terms). That is the error "
            f"band on the figure above, and it is wide."
        )
        lines.append("")

        # Rendered whenever the subject's market resolves to one of the four this
        # breakdown covers, whether or not the gap crossed the flag's threshold (Q2(a)):
        # a reader in a market that is not elevated should still see what "not elevated"
        # looks like next to the one that is.
        if (detail.subject_metro and detail.subject_metro_mae_dollars is not None
                and detail.subject_metro_mae_n is not None):
            lines.append(
                f"That figure is the model's error averaged across every market it was "
                f"trained on. In **{detail.subject_metro}** specifically, the same "
                f"measurement missed by "
                f"**{_money(detail.subject_metro_mae_dollars)}/mo** "
                f"(n={detail.subject_metro_mae_n} listings) — "
                + (
                    "materially worse than the figure above, see the disclosure below."
                    if detail.subject_metro_mae_dollars
                    > config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD
                    * detail.model_mae_dollars
                    else "in line with the figure above."
                )
            )
            lines.append("")

    if detail.comp_implied_rent_median is not None:
        direction = "above" if (detail.divergence_pct or 0) >= 0 else "below"
        at_zip = (
            f", {detail.comps_zip_anchored} of them at ZIP resolution"
            if detail.comps_zip_anchored else ""
        )
        lines.append(
            f"**Cross-check against the comps:** {detail.comps_cross_checked} of "
            f"{detail.comps_available} retrieved comps normalized cleanly to their own "
            f"area and fiscal year{at_zip}, implying "
            f"**{_money(detail.comp_implied_rent_median)}/mo** "
            f"(middle half {_money(detail.comp_implied_rent_p25)}–"
            f"{_money(detail.comp_implied_rent_p75)}). The model sits "
            f"{abs(detail.divergence_pct):.0%} {direction} that."
        )
    else:
        shortfall = (
            f"only {detail.comps_cross_checked} of {detail.comps_available} retrieved "
            f"comps could be normalized to this county and fiscal year"
            if detail.comps_available
            else "no comps were retrieved"
        )
        lines.append(
            f"**Cross-check against the comps: not run** — {shortfall}, below the "
            f"{config.RENT_COMP_CROSSCHECK_MIN_COMPS} needed for a median to describe a "
            f"distribution rather than a single listing. The estimate above rests on "
            f"the model alone, with no local evidence corroborating it."
        )
    lines.append("")
    return lines


def _stated_rent_section(state: DealState, detail) -> list[str]:
    """The listing's own rent claim, set against the rent this system derived.

    **The only place in the report where what the seller asserts meets what the system
    worked out independently.** Every other comparison in this section sets one derived
    figure against another — the model against the comps, the asking price against a metro
    median. Until this section existed the report rendered `rent_estimate` and never
    `deal_terms.unit_rents`, so a reader could not see that the two disagreed by roughly
    a third. That is a Transparent Degradation gap: the system held both numbers and
    showed one.

    Rendered whenever a rent estimate exists, **including when the listing stated no rents
    at all**, for the same reason `_rent_basis_section` renders its cross-check when the
    cross-check did not run. A report that shows a comparison only where it is favourable
    shows its working only on the runs where the working looked good.

    **No flag, no objection, no effect on confidence or routing** — this is a disclosure,
    not a check (Q4). The reason was measured rather than cautious: the gap was ~-29% on
    all three demo listings and it was *structural*. `rent_estimate` was anchored to FMR,
    a 40th-percentile administrative rent, while the corpus the model learned from rented
    at roughly 1.40x that anchor — so the model predicted market-typical rent while #11
    calibrated these listings to the anchor itself. Raising an objection from that would
    have charged the deal for a property of the fixtures.

    **That premise expired at U11.3 and the measurement was re-run rather than assumed.**
    The anchor is a market rent index now, not a 40th-percentile benchmark, so the
    structural offset is gone. Across the 13 fixtures carrying independently-set rents:
    **mean -11.4%, median -9.7%, range -39.4% to +66.6%** — dispersed and sign-varying,
    which is a property of each deal rather than of the anchor. The reason this stayed a
    disclosure has therefore been removed, and **whether to promote it to a Critic
    objection is an open decision rather than a settled one** (U8.7, OQ-1). It ships as a
    disclosure until that is taken, which is the same behavior for a different and now
    honestly-stated reason.

    The demo deals cannot be used to answer it: their `rent_basis` is `hud_fmr:2`, so #11
    set their stated rents *from* the old anchor. Any gap they show measures the
    FMR-versus-market spread, not the deal — which is a live finding about the demo set,
    not about this check.

    Reason/Act/Observe/Decide is the Summarizer's, not this helper's: it renders, and
    decides only how much to say.
    """
    if state.rent_estimate is None:
        return []

    terms = state.deal_terms
    lines = ["### The listing's stated rents", ""]

    if not terms.unit_rents:
        lines.extend([
            "**The listing states no per-unit rents.** The estimate above therefore "
            "stands on the model and the comps alone, with nothing from the seller to "
            "read it against — no claim to corroborate it, and none to contradict it.",
            "",
        ])
        return lines

    rents = list(terms.unit_rents)
    stated_avg = sum(rents) / len(rents)
    stated_total = sum(rents)
    rendered = _join(list(_money(r) for r in rents))

    # The unit basis is stated rather than assumed. `rent_estimate` is one figure for one
    # bedroom count; `unit_rents` is a list that may describe units of different sizes,
    # and averaging across a mixed set compares two different things. Naming the basis
    # lets a reader see when it does not hold instead of discovering it later.
    per_unit_basis = (
        f"a {terms.bedrooms}-bedroom unit" if terms.bedrooms is not None
        else "the subject's unit type"
    )
    lines.append(
        f"The listing states {rendered} per month across "
        f"{len(rents)} unit{'s' if len(rents) != 1 else ''} — an average of "
        f"**{_money(stated_avg)}** per unit, **{_money(stated_total)}/mo** in total."
    )

    gap = (stated_avg - state.rent_estimate) / state.rent_estimate
    side = "above" if gap >= 0 else "below"
    # Multiply the figure the reader is shown, not the one behind it. `rent_estimate`
    # carries cents; rendering the per-unit figure from the raw value and the total from
    # the raw value produces $4,075 and $8,151, and a reader who checks the arithmetic
    # finds it off by a dollar. The precision lost is below the resolution of a number
    # printed to the dollar and carrying a $524 error band.
    per_unit = round(state.rent_estimate)
    estimate_total = (
        f", or **{_money(per_unit * len(rents))}/mo** across {len(rents)} units"
    )
    lines.append("")
    lines.append(
        f"This system estimates **{_money(per_unit)}/mo** for "
        f"{per_unit_basis}{estimate_total}. The stated rents sit "
        f"**{abs(gap):.0%} {side}** that estimate."
    )

    # A stated-rent count that disagrees with the stated unit count means the average
    # above describes only part of the property. Said here rather than left for a reader
    # to notice by comparing two numbers in different sections.
    if terms.unit_count is not None and terms.unit_count != len(rents):
        lines.append("")
        lines.append(
            f"**The listing gives {terms.unit_count} units but rents for "
            f"{len(rents)}.** The average and total above cover only the units with a "
            f"stated rent, so the total understates the property's rent roll."
        )

    threshold = config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD
    if threshold is not None and abs(gap) >= threshold:
        lines.append("")
        lines.append(
            f"**This gap is larger than this report treats as ordinary.** Read the "
            f"estimate and the stated rents as two claims in disagreement rather than "
            f"as one figure with a margin around it."
        )

    # **This caveat was direction-dependent for a reason that stopped being true on
    # Aug 30, 2026 (U11.3), and the correction is a narrowing rather than a rewrite.**
    #
    # It used to say a negative gap was *expected*: the estimate was anchored to a
    # 40th-percentile federal affordability benchmark while the corpus behind the model
    # rented well above it, so every estimate leaned high by a structural offset and
    # stated rents below it said nothing. Measured then, the gap was ~-29% on all three
    # demo listings — a constant, which is what a structural offset looks like.
    #
    # The anchor is a market rent index now, so that offset is gone. Re-measured across
    # the 13 fixtures that carry independently-set rents: **mean -11.4%, median -9.7%,
    # range -39.4% to +66.6%.** Dispersed and sign-varying, which is what a property of
    # the *deal* looks like. So a negative gap is no longer "expected" in the sense of
    # being predicted by the anchor — but it is still the common direction, and the two
    # remaining reasons for it are real and worth stating. The text below says the
    # narrower, true thing.
    if gap < 0:
        lines.extend([
            "",
            "> **A gap in this direction is common and is not on its own evidence that "
            "the property is under-rented.** The estimate describes what a unit of this "
            "size and configuration rents for in this ZIP code today; a stated rent is "
            "what sitting tenants are actually paying, which lags the market wherever "
            "leases were signed earlier or renewed below market. It is also an estimate "
            "with a stated error band — see the rent disclosures above — and a gap "
            "inside that band is not a disagreement.",
            "",
        ])
    else:
        lines.extend([
            "",
            "> **Stated rents above the estimate are worth verifying against leases "
            "rather than taken from the listing.** The estimate describes a unit of this "
            "size and configuration in this ZIP code; rents materially above it usually "
            "have an explanation the listing has not given — short-term or furnished "
            "tenancies, rents including utilities or parking, or figures that are asking "
            "rather than collected.",
            "",
        ])
    return lines

def _findings_section(state: DealState) -> list[str]:
    terms = state.deal_terms
    lines = ["## Findings", ""]

    lines.append("| Metric | Value | Basis |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Asking price | {_money(terms.price)} | listing |")
    lines.append(
        f"| Units | {terms.unit_count if terms.unit_count is not None else '—'} | listing |"
    )

    detail = state.valuation_detail

    if state.rent_estimate is not None:
        # The error band is printed inside the value cell rather than in a footnote,
        # because a reader who takes one number away from this table should take the
        # spread with it. $2,431 and "$2,431 give or take $519" support different
        # decisions, and the second one is what this model actually supports.
        value = f"{_money(state.rent_estimate)}/mo per unit"
        if detail and detail.model_mae_dollars is not None:
            value += f" ± {_money(detail.model_mae_dollars)} overall"
            # Rendered whenever the subject's market resolves, elevated or not — Q2(a):
            # the point is a reader in a good market can see what good looks like too.
            if (detail.subject_metro and detail.subject_metro_mae_dollars is not None):
                value += (
                    f", ± {_money(detail.subject_metro_mae_dollars)} in "
                    f"{detail.subject_metro}"
                )
        basis = str(state.rent_estimate_source or "unspecified")
        if state.rent_estimate_ratio_to_anchor is not None and state.rent_anchor_used is not None:
            # **Names the market index, not Fair Market Rent (U11.3).** Until then the
            # anchor was a HUD schedule and this line said so; it is now a Zillow rent
            # index read at a month, stepped to the subject's bedroom count by the
            # schedule's own ratio between unit sizes. The old sentence survived the
            # anchor change for one commit and was false for that whole time, which is
            # the defect class U8.2b and U8.4c both fixed — a disclosure describing a
            # mechanism the system has stopped using.
            #
            # Name the spatial resolution, not just the figure. Rents span roughly 2x
            # within a single county, so the same dollar amount means something very
            # different depending on which of the two produced it.
            where = ""
            if detail and detail.anchor_tier == "zip":
                where = f" (ZIP {detail.anchor_zip})" if detail.anchor_zip else " (ZIP)"
            elif detail and detail.anchor_tier == "county":
                where = " (county-wide)"
            asof = (
                f" as of {detail.anchor_index_month[:7]}"
                if detail and detail.anchor_index_month
                else ""
            )
            basis += (
                f", ratio {state.rent_estimate_ratio_to_anchor:.2f} × market rent "
                f"{_money(state.rent_anchor_used)}{where}{asof}"
            )
        lines.append(f"| Estimated rent | {value} | {basis} |")
    else:
        # No reason text here on purpose: whichever path declined to produce a figure
        # raised a flag saying which one, and those are rendered *above* this table.
        # Restating it would give the report two authorities on the same fact.
        lines.append(
            "| Estimated rent | not produced | see the disclosures above for which "
            "input was missing |"
        )

    # `value_estimate` is never populated by this build; see agents/valuation_rent.py
    # for the evidence behind that. The row stays, and says so — dropping it would let
    # a reader conclude the property has no determinable value, which is a claim about
    # the deal rather than about this system's inputs.
    lines.append(
        "| Estimated value | not produced | no property-level sale data exists in this "
        "project's sources; see the market benchmark below |"
    )

    lines.append("")
    lines.extend(_benchmark_section(state, detail))
    lines.extend(_rent_basis_section(state, detail))
    # After the basis, deliberately: the gap is only interpretable once the reader knows
    # the estimate's error band and whether the comps corroborated it.
    lines.extend(_stated_rent_section(state, detail))
    # Last of the price/rent blocks, because it is the only one that combines them and
    # it should be read after both of its inputs have been qualified.
    lines.extend(_gross_rent_multiplier_section(state, detail))

    lines.extend(_scenario_section(state))

    return lines


def _money_or_dash(value: Optional[float]) -> str:
    return _money(value) if value is not None else "—"


def _projection_rent_error(state: DealState, base_rent: Optional[float]) -> Optional[str]:
    """The sentence that stops the outlook reading as more precise than it is.

    Every scenario row compounds one modelled rent figure, and that figure has a measured
    error band the outlook never widens for. So the spread *between* rows is a statement
    about how the market might move, not about how far the starting point itself could
    be off — and on `staten-island` the band is 32% of the estimate against a five-year
    spread of 43%, meaning the rows differ by less than the error bar under all of them.
    A reader not told that reads three rows as three measurements.

    Prefers the subject's own metro over the pooled figure — the same order, and for the
    same reason, as the Findings table one section above: the pooled number averages
    across markets this deal is not in. Returns `None` rather than a hedge when no band
    is on state, because a sentence about an error it cannot quantify gives a reader
    nothing to act on.
    """
    detail = state.valuation_detail
    if detail is None or base_rent is None or base_rent <= 0:
        return None
    band = detail.subject_metro_mae_dollars or detail.model_mae_dollars
    if band is None:
        return None
    where = (
        f"in {detail.subject_metro}"
        if detail.subject_metro and detail.subject_metro_mae_dollars is not None
        else "across the markets this model was trained on"
    )
    return (
        f"**Every row compounds the same modelled rent, and that rent carries an error "
        f"of ± {_money(band)}/mo {where} — about {band / base_rent:.0%} of it.** The "
        f"rows differ from each other in how the market moves; not one of them widens "
        f"for how far the starting rent could be off. Read the spread between rows as "
        f"the range of markets this deal could meet, not as the range this system's "
        f"own rent figure could take."
    )


def _scenario_section(state: DealState) -> list[str]:
    """The forecast, its basis, and how the search reasoned its way to it.

    Four blocks rather than one table, and the split is the disclosure. **The measured
    ranges lead**, one per quantity, because that is the part whose labels are true
    without qualification — the combined scenarios below them are pairings, and a row
    labelled "Optimistic" can carry the pessimistic price band. Then the scenarios
    themselves; then the basis, which says which treatment of which series produced the
    numbers; then the search, rendered as the two questions it actually asked with the
    winner of each shown. A reader who stops after the first block has a defensible
    forecast; one who reads all four can tell whether to believe it and can see what the
    system rejected on the way.
    """
    detail = state.forecast_detail
    if not state.scenarios:
        reason = "The forecast agent produced no scenarios for this deal."
        if detail is not None:
            halves = [
                text
                for text in (
                    detail.rent_growth_unavailable_reason,
                    detail.price_growth_unavailable_reason,
                    detail.search_exhausted_reason,
                )
                if text
            ]
            if halves:
                reason = " ".join(halves)
        return ["### Scenarios", "", reason, ""]

    horizon = detail.horizon_years if detail else config.FORECAST_HORIZON_YEARS
    lines = [f"### Scenarios — {horizon}-year outlook", ""]
    lines.extend(_band_tables(detail))

    base_rent = detail.projection_base_rent if detail else None
    base_price = detail.projection_base_price if detail else None
    basis_parts = []
    if base_rent is not None:
        basis_parts.append(f"modelled rent {_money(base_rent)}/mo")
    if base_price is not None:
        basis_parts.append(f"the **asking price** {_money(base_price)}")
    if basis_parts:
        # **The rent side compounds an estimate, and that estimate has an error band
        # (maintenance item M8, Sept 2, 2026).** Every scenario row starts from
        # `projection_base_rent` — which is `state.rent_estimate` — and compounds it as
        # though it were exact. On `staten-island` the figure carries a metro holdout
        # error of +/-$855, 32% of the estimate, against a five-year band spread of 43%:
        # the three rows differ from each other by *less* than the error bar on the
        # number all three start from, and the section did not say so.
        #
        # **Language, not calculation.** Nothing about which scenarios are selected or
        # what they project changes. Raised by the U9 spike on OQ-22's starting-point
        # treatment (`design/forecast_starting_point_spike.md`), which proposed
        # *projecting* from the band; that mechanism was not adopted — the evaluator
        # held its choice on only 5 of 8 repeat runs — and stating the band is the half
        # that survives that finding, standing whichever way OQ-22 was decided.
        lines.append(
            f"Projected from {' and '.join(basis_parts)}. The price side compounds the "
            f"asking price rather than an estimated value — this system does not produce "
            f"one, and says so above."
        )
        rent_error_sentence = _projection_rent_error(state, base_rent)
        if rent_error_sentence:
            lines.append("")
            lines.append(rent_error_sentence)
        lines.append("")
        lines.append(
            "Each row is named for the combination it describes, and the bands beside "
            "each figure are the same ones in the table above. **Rows are ordered worst "
            "to best by combined outcome**, so the central case is not necessarily in "
            "the middle. Rent and price are paired here rather than forecast "
            "independently, and this project has measured how the two move together: "
            "weakly, and not in a consistent direction. Read each row as one internally "
            "consistent story about this market, not as evidence that rent and price "
            "tend to move that way."
        )
        lines.append("")

    # **Each quantity's rate sits beside its own projected level (Sept 2, 2026).** The
    # previous order put both rates together and both levels together, so reading what
    # rent does meant crossing the price column and back — and the two columns a reader
    # most often compares, a rate and the level it compounds to, were the furthest apart.
    lines.append(
        "| Scenario | Rent growth | "
        f"Rent in year {horizon} | Price growth | Price in year {horizon} | "
        "Why this row is shown |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for scenario in state.scenarios:
        rent_growth = (
            f"{scenario.rent_growth_pct_per_year:+.2f}%/yr ({_band_word(scenario.rent_band)})"
            if scenario.rent_growth_pct_per_year is not None
            else "—"
        )
        price_growth = (
            f"{scenario.price_growth_pct_per_year:+.2f}%/yr ({_band_word(scenario.price_band)})"
            if scenario.price_growth_pct_per_year is not None
            else "—"
        )
        lines.append(
            f"| **{scenario.name}** | {rent_growth} | "
            f"{_money_or_dash(scenario.projected_monthly_rent)} | {price_growth} | "
            f"{_money_or_dash(scenario.projected_price)} | "
            f"{_why_shown(scenario)} |"
        )
    lines.append("")
    lines.extend(_band_coverage_note(state.scenarios, detail))

    # **The score moved into the table at U9.7T and this carries the rationale alone.**
    # It sat here because the branch ledger renders every discarded hypothesis as
    # `id (score) — summary`, and a survivor read the same way was the matching statement
    # (U8.6c). What that missed is that a score alone does not say how the row got in —
    # the tie-break decides half the pairing levels — so the number now sits beside the
    # mechanism in the "Why this row is shown" column, where the two are read together.
    scored = any(s.evaluator_score is not None for s in state.scenarios)
    for scenario in state.scenarios:
        if scenario.rationale:
            lines.append(f"- **{scenario.name}** — {scenario.rationale}")
    if scored:
        lines.append("")
        lines.append(
            "The score in the last column is how well the forecast search judged that "
            "combination to be supported by the evidence it was given, from 0 to 1 — "
            "shown because a scenario the system itself rated weakly should be read as "
            "one. Two cautions: a score says how well evidenced a combination is, not "
            "how likely it is, so a higher-scoring row is not a more probable outcome; "
            "and the scores come from a single model call whose repeat runs measurably "
            "vary, so small differences between them are not reliable — which is why a "
            "row kept on the tie-break says so rather than reporting the gap."
        )
    lines.append("")

    if detail is not None:
        lines.extend(_forecast_basis_block(detail))
        lines.extend(_branch_ledger_block(state))

    return lines


def _forecast_basis_block(detail: ForecastDetail) -> list[str]:
    """How the bands were built — the part that lets a reader discount the forecast."""
    lines = ["#### How these bands were built", ""]

    if detail.rent_growth_base_pct is not None:
        span = (
            f"{detail.rent_growth_first_observation} to "
            f"{detail.rent_growth_last_observation}"
            if detail.rent_growth_first_observation
            else "the published history"
        )
        where = detail.rent_growth_area_name or "the subject county"
        breadth = (
            f", a median across the {detail.rent_growth_zips_in_county} postal codes "
            f"within it"
            if detail.rent_growth_zips_in_county
            else ""
        )
        if detail.rent_growth_pessimistic_year is None:
            # The market index: monthly, so the outer bands are sustained stretches.
            lines.append(
                f"**Rent** — {detail.rent_growth_source_description} for {where}"
                f"{breadth}, covering {span} "
                f"({detail.rent_growth_n_observations} year-over-year observations). The "
                f"outer bands are the worst and best twelve-month stretches the index "
                f"actually held, not its worst and best single months; the base case is "
                f"the average across every month kept."
            )
            lines.append(
                f"  This is measured across the county, while the rent estimate above is "
                f"anchored to this property's own postal code. A single postal code's "
                f"rent index generally does not reach back far enough to measure a "
                f"five-year trend, so the trend is read at the wider geography and the "
                f"estimate is not."
            )
        else:
            # The published schedule: annual, so the bands name a year.
            lines.append(
                f"**Rent** — {detail.rent_growth_source_description} for {where}, "
                f"{detail.rent_growth_bedrooms}-bedroom, covering {span} "
                f"({detail.rent_growth_n_observations} year-over-year observations). No "
                f"market rent index reaches this county with enough history to measure a "
                f"trend, so this published schedule serves instead. Its bands are the "
                f"worst and best single years on record "
                f"({detail.rent_growth_pessimistic_year} and "
                f"{detail.rent_growth_optimistic_year}), and the base case compounds "
                f"every year kept — a single year is a blunter extreme than the "
                f"twelve-month stretches the sale-price bands use, so this range reads "
                f"wider for that reason alone."
            )
        if detail.rent_anomalous_period_excluded is not None:
            lines.append(
                f"  2020–2022 "
                f"{'excluded' if detail.rent_anomalous_period_excluded else 'included'} "
                f"— the same treatment question asked of the sale-price series below, so "
                f"the two describe the same span of history."
            )
        lines.append("")
    elif detail.rent_growth_unavailable_reason:
        lines.append(f"**Rent** — {detail.rent_growth_unavailable_reason}")
        lines.append("")

    if detail.price_growth_base_pct is not None:
        lines.append(
            f"**Price** — Redfin metro-level Multi-Family (2–4 unit) median sale price "
            f"for {detail.price_growth_metro}, "
            f"{detail.price_growth_n_observations} year-over-year observations, "
            f"2020–2022 "
            f"{'excluded' if detail.anomalous_period_excluded else 'included'}."
        )
        lines.append("")
    elif detail.price_growth_unavailable_reason:
        lines.append(f"**Price** — {detail.price_growth_unavailable_reason}")
        lines.append("")

    return lines


def _band_tables(detail: Optional[ForecastDetail]) -> list[str]:
    """The two measured ranges, each on its own terms, before anything is combined.

    **This leads the forecast because it is the part that is true without qualification,
    and the combined table below it is not.** A scenario row is a *pairing*: its label
    comes from the two sides' projected outcome together, so a row labelled "Optimistic"
    can and does carry the pessimistic price band. The report has always explained that
    honestly in a paragraph, and explaining a confusing thing clearly does not stop it
    being confusing.

    Split into one table per series, every label describes the band directly under it.
    Nothing is lost from the reasoning — all nine pairings and the full search ledger are
    still below — and the reader who wants one number per quantity gets it without having
    to decompose a combined outcome first.
    """
    if detail is None:
        return []
    rows: list[tuple[str, Optional[float], Optional[float], Optional[float], str]] = []
    if detail.rent_growth_base_pct is not None:
        rows.append((
            "Monthly rent",
            detail.rent_growth_pessimistic_pct,
            detail.rent_growth_base_pct,
            detail.rent_growth_optimistic_pct,
            f"{detail.rent_growth_n_observations} year-over-year observations",
        ))
    if detail.price_growth_base_pct is not None:
        note = f"{detail.price_growth_n_observations} year-over-year observations"
        if detail.optimistic_stretch_in_anomalous_period:
            # The one caveat that cannot wait for the disclosure list: an optimistic band
            # resting on the 2020-2022 rate window is a real observed stretch and a bad
            # thing to compound five years forward without saying so beside the number.
            note += "; strongest stretch falls in 2020–2022"
        rows.append((
            "Sale price",
            detail.price_growth_pessimistic_pct,
            detail.price_growth_base_pct,
            detail.price_growth_optimistic_pct,
            note,
        ))
    if not rows:
        return []

    # Read from *both* fields, never from the price side alone. The two are separate
    # forks and the search is free to answer them differently — the Staten Island run
    # does, keeping 2020-2022 in the rent bands and holding it out of the price bands —
    # so a sentence generalising one to both contradicts the basis block below it.
    rent_out = detail.rent_anomalous_period_excluded
    price_out = detail.anomalous_period_excluded
    if rent_out is None and price_out is None:
        window = None
    elif rent_out == price_out:
        window = (
            "2020–2022 held out of both"
            if rent_out
            else "2020–2022 kept in both"
        )
    else:
        held, kept = (
            ("rent", "sale price") if rent_out else ("sale price", "rent")
        )
        window = f"2020–2022 held out of {held} and kept in {kept}"
    lines = [
        "#### What each series has done",
        "",
        "Measured ranges, one per quantity, each labelled for its own band rather than "
        "for a combined outcome. Given a stretch of history these figures are arithmetic "
        "and do not move between runs — but *which* stretch of history is a judgment, "
        + (f"and this run made it one way ({window}); " if window else "")
        + "the reasoning behind it is shown under **Step 1** below.",
        "",
        "| | Weakest sustained stretch | Long-run average | Strongest sustained stretch | Measured over |",
        "| --- | --- | --- | --- | --- |",
    ]
    for label, low, mid, high, note in rows:
        lines.append(
            f"| **{label}** | {_pct_or_dash(low)} | {_pct_or_dash(mid)} | "
            f"{_pct_or_dash(high)} | {note} |"
        )
    lines.append("")
    return lines


def _pct_or_dash(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:+.2f}%/yr"


# The short form of `_band_tables`' column headings, for use inside a table cell. One
# vocabulary across both forecast tables is the whole of U9.7T's first finding: the
# report used to print plain words for the bands in one table and the internal names
# `pessimistic` / `base` / `optimistic` for the same bands in the next, where those three
# words *also* named the combined outcome in the row label beside them.
_BAND_WORDS = {
    "pessimistic": "weakest stretch",
    "base": "long-run average",
    "optimistic": "strongest stretch",
}


def _gross_rent_multiplier_section(state: DealState, detail) -> list[str]:
    """Price against rent, as the one investor ratio this project's data supports.

    **Why this ratio and not cap rate.** Cap rate is what an investor would rather see
    and it needs net operating income, which needs operating expenses — taxes,
    insurance, vacancy, maintenance, management — that this system does not model.
    Assuming an expense ratio would put an invented number at the centre of the
    recommendation. The report says that plainly rather than omitting the subject,
    because a reader who came for cap rate should learn why it is absent.

    **The two multiples are not independent, and the text says so.** They share a
    denominator, so their ratio is exactly the price premium stated above — the same
    comparison in a different unit. Presenting them as two agreeing measurements would
    be double-counting one fact, which is the failure the whole report is built against.
    What the second one buys is the unit itself: an investor who thinks in multiples can
    read the market without converting anything.
    """
    if detail is None:
        return []
    if detail.gross_rent_multiplier is None:
        if not detail.grm_unavailable_reason:
            return []
        return [
            "### Price against rent",
            "",
            f"No gross rent multiple was formed for this listing, because "
            f"{detail.grm_unavailable_reason}.",
            "",
        ]

    units = state.deal_terms.unit_count
    lines = [
        "### Price against rent",
        "",
        f"At the modelled rent, this property's gross rent is "
        f"**{_money(detail.grm_annual_gross_rent)} a year** across {units} unit"
        f"{'s' if units != 1 else ''}, so the asking price is "
        f"**{detail.gross_rent_multiplier:.1f}×** annual gross rent.",
        "",
    ]

    if detail.benchmark_gross_rent_multiplier is not None:
        tier = "this ZIP code" if detail.benchmark_tier == "zip" else "this metro area"
        lines.append(
            f"The typical recorded sale in {tier} would buy the same rent at "
            f"**{detail.benchmark_gross_rent_multiplier:.1f}×**. That is the *same* "
            f"comparison as the price-versus-benchmark figure above rather than a "
            f"second one — both multiples divide by the same rent, so the gap between "
            f"them is the price gap restated. It is shown because the multiple is the "
            f"unit this comparison is usually made in."
        )
        lines.append("")

    lines.append(
        "> **This is a gross multiple, not a yield, and the difference is the "
        "expenses.** It divides the price by rent before taxes, insurance, vacancy, "
        "maintenance or management — none of which this system models, and all of "
        "which a buyer pays. A capitalization rate would account for them; producing "
        "one here would mean assuming an expense ratio and presenting the assumption "
        "as a finding, so this report stops at the ratio its data can support and "
        "says where the line is."
    )
    lines.append("")
    return lines


def _band_coverage_note(
    scenarios: list[Scenario], detail: Optional[ForecastDetail]
) -> list[str]:
    """Name any measured band that reached none of the reported rows.

    **The reader's default assumption is that three scenarios span the range, and on
    this project's own demo deal they do not.** On `los-angeles` the beam kept base
    rent with base price, base rent with pessimistic price, and pessimistic rent with
    base price — so neither series' strongest stretch appears in any row, while both are
    printed in the table above. A reader taking the last row as the upside case is
    reading a figure the search never claimed was one.

    Stated as an absence rather than fixed by widening the beam, which would be
    overriding the evaluation to satisfy a layout: the bands that reached no row are the
    ones the search did not judge well enough evidenced to report, and that is the
    finding. Silent when the rows cover every band, so the line means something when it
    does appear.
    """
    if detail is None or not scenarios:
        return []

    missing: list[str] = []
    sides = (
        ("rent", detail.rent_growth_base_pct, [s.rent_band for s in scenarios]),
        ("sale price", detail.price_growth_base_pct, [s.price_band for s in scenarios]),
    )
    for label, series_present, used in sides:
        if series_present is None:
            # No series at all on this side — already disclosed as an unavailability,
            # and calling its bands "not shown" would imply bands that were never built.
            continue
        for band in ("pessimistic", "base", "optimistic"):
            if band not in used:
                missing.append(f"the {_BAND_WORDS[band]} for {label}")
    if not missing:
        return []

    return [
        f"**Not represented above:** {_join(missing)}. Every band is measured and "
        "printed in the table at the top of this section; what the rows show is which "
        "*combinations* the search judged worth reporting, and a band reaching no row "
        "means it did not survive that judgment in any pairing. The bottom row is "
        "therefore the best case among those reported, not the best case measured.",
        "",
    ]


def _why_shown(scenario: Scenario) -> str:
    """The row's own account of how it got into the report.

    **This column exists because the report had the losers' side of the story and not
    the winners'.** The branch ledger below says why each discarded hypothesis was
    dropped; nothing said whether a row a reader is looking at had outscored the field,
    been kept by this system's preference for the more cautious reading, or been held
    open as the neutral case. Measured across the committed recordings, the tie-break
    decides **51%** of the pairing levels — so "it scored highest" was the wrong thing
    to leave a reader inferring about roughly half the rows in front of them.

    It also brings the near-tie disclosure to the row it is about. The flag still fires
    and is still listed in full, but a caution sixty lines above the table, inside a
    collapsed block, is not where a reader meets the number it qualifies.
    """
    score = (
        f"**{scenario.evaluator_score:.2f}**"
        if scenario.evaluator_score is not None
        else None
    )
    basis = scenario.selection_basis or ""

    if basis == "reserved":
        detail = "the neutral case, always shown"
    elif basis.startswith("tie:"):
        # The stored figure is the tie group's size; the reader is being told how many
        # *others* it was level with.
        others = max(int(basis.split(":", 1)[1]) - 1, 1)
        detail = (
            f"level with {others} other pairing{'s' if others != 1 else ''}, "
            "kept as the more cautious"
        )
    elif basis == "outright":
        detail = "outscored the pairings left out"
    else:
        # No basis recorded — a scenario reconstructed from partial state, or the linear
        # baseline in `scripts/forecast_evidence.py`, which no search selected. Saying
        # nothing is right; inventing a mechanism would be worse than an empty cell.
        return score or "—"

    return f"{score} — {detail}" if score else detail


def _band_word(band: Optional[str]) -> str:
    """The reader-facing name for a band. Falls back to whatever it was given.

    A band this map does not know is a defect rather than a case to design for, and
    printing it is how it gets noticed — silently rendering "unknown" would hide which
    value arrived.
    """
    return _BAND_WORDS.get(band or "", band or "—")


def _branch_ledger_block(state: DealState) -> list[str]:
    """What the search considered and discarded.

    Present even when nothing was pruned, because "four hypotheses considered, none
    discarded" and "no search ran" are different facts about a forecast and a reader
    should be able to tell them apart.
    """
    entries = [e for e in state.branch_ledger if e.agent == "scenario_forecast"]
    if not entries:
        return []

    # A rework pass re-runs the node and appends a second set of rows; the raw history
    # stays in state and the de-duplication happens here, matching how `stub_nodes` is
    # handled.
    seen: dict[str, object] = {}
    for entry in entries:
        seen[entry.id] = entry
    entries = list(seen.values())

    pruned = [e for e in entries if e.prune_reason]
    lines = [
        "#### How the forecast search reasoned",
        "",
        f"{len(entries)} hypotheses were evaluated and {len(pruned)} discarded, across "
        f"two questions asked in order. Pruning is recorded rather than silent: an "
        f"evaluator that quietly drops a correct-but-unusual branch looks identical to "
        f"one working properly.",
        "",
    ]

    # Rendered as two steps rather than one list of thirteen, and the winner is shown.
    # The previous rendering flattened both levels together and printed only *discarded*
    # branches, so a reader saw three losers and never learned what beat them — the one
    # place in this system where a model exercises judgment, and it was the one place the
    # report showed no verdict.
    for depth, heading in (
        (1, "Step 1 — which reading of the history should every band be built from?"),
        (2, "Step 2 — which combinations of those bands are worth showing?"),
    ):
        at_depth = [e for e in entries if e.depth == depth]
        if not at_depth:
            continue
        kept = [e for e in at_depth if not e.prune_reason]
        lines.append(
            f"**{heading}**  \n*{len(at_depth)} considered, {len(kept)} kept.*"
        )
        lines.append("")
        # Best score first, so the chosen reading leads rather than being hunted for.
        for entry in sorted(at_depth, key=lambda e: -(e.score or 0.0)):
            score = f"{entry.score:.2f}" if entry.score is not None else "not scored"
            if entry.prune_reason:
                lines.append(
                    f"- `{entry.id}` ({score}) — {entry.summary} "
                    f"**Discarded:** {entry.prune_reason}"
                )
            else:
                lines.append(f"- **`{entry.id}` ({score}) — {entry.summary} ← carried forward**")
        lines.append("")

    lines.append(
        "*The scores and the wording above come from one model call, and repeat calls on "
        "identical input have been measured moving materially. Read this as a sample of "
        "the reasoning rather than a stable ranking — small differences between scores "
        "are not reliable. The bands themselves are arithmetic and do not move.*"
    )
    lines.append("")
    return lines


def summarizer_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    terms = state.deal_terms
    heading = terms.full_address or "Unidentified property"

    lines: list[str] = [f"# Deal Evaluation — {heading}", ""]

    lines.extend(_build_status_section(state.stub_nodes))

    # **The two axes open the report** (U9.4). Above the status strip and above the
    # model's summary, so the first thing a reader meets is the reproducible verdict
    # rather than a number they cannot place or prose that varies between runs.
    lines.extend(_verdict_lines(state))
    lines.extend(_verdict_reasons_block(state))
    lines.extend(_lede_section(state))

    confidence = (
        f"{state.confidence_score:.2f}" if state.confidence_score is not None else "—"
    )
    lines.append(
        f"**Confidence:** {confidence} "
        f"(escalation threshold {config.HUMAN_REVIEW_CONFIDENCE_THRESHOLD:.2f}) · "
        f"**Disclosures:** {len(state.flags)} · "
        f"**Comparables:** {len(state.comps)}"
    )
    lines.append("")
    lines.extend(_confidence_arithmetic(state.confidence_detail))

    # Disclosures precede findings deliberately — see the module docstring.
    lines.extend(_flag_section(state.flags))

    if state.clarifying_questions:
        lines.append("## Unanswered Questions")
        lines.append("")
        lines.append(
            "The evaluation proceeded without answers to the following. Each "
            "corresponds to an `unresolved_field` disclosure above."
        )
        lines.append("")
        for question in state.clarifying_questions:
            lines.append(f"- {question}")
        lines.append("")

    lines.extend(_findings_section(state))
    lines.extend(
        _comps_section(state.comps, state.search_radius_miles, state.retrieval_iterations)
    )

    lines.append("---")
    lines.append("")
    lines.append(
        f"*Generated by the multi-family deal evaluator · run started "
        f"{state.created_at:%Y-%m-%d %H:%M} · planner invocations "
        f"{state.planner_invocations} · rework passes {state.rework_count}*"
    )

    return {
        "report_markdown": "\n".join(lines),
        # A reviewed deal keeps its needs_review status; see the module docstring.
        "status": (
            DealStatus.NEEDS_REVIEW
            if state.status == DealStatus.NEEDS_REVIEW
            else DealStatus.COMPLETE
        ),
    }
