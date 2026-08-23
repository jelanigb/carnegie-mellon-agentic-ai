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

import config
from state import Comp, DealState, DealStatus, Flag, Severity, count_area_positioned

AGENT = "summarizer"

_SEVERITY_ORDER = (Severity.CRITICAL, Severity.WARN, Severity.INFO)

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


def _flag_section(flags: list[Flag]) -> list[str]:
    """Every flag, grouped by severity, most severe first."""
    if not flags:
        return [
            "## Disclosures",
            "",
            "**None.** This run completed without relaxing any criterion, falling back "
            "to any coarser data source, or leaving any required field unresolved.",
            "",
        ]

    lines = ["## Disclosures", ""]
    lines.append(
        f"{len(flags)} disclosure(s) were raised during this evaluation. Each is "
        "listed in full below, most severe first."
    )
    lines.append("")

    for severity in _SEVERITY_ORDER:
        matching = [f for f in flags if f.severity == severity]
        if not matching:
            continue
        lines.append(
            f"### {_SEVERITY_LABEL[severity]} ({len(matching)}) — "
            f"{_SEVERITY_GUIDANCE[severity]}"
        )
        lines.append("")
        for f in matching:
            lines.append(f"- **`{f.kind}`** — {f.detail}  ")
            lines.append(f"  *raised by:* `{f.source_agent}`")
        lines.append("")

    return lines


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
        + ". Sections fed by them are unbuilt, not empty. See "
        "`docs/implementation_plan.md` §6 for the unit that implements each.",
        "",
    ]


def _benchmark_section(state: DealState, detail) -> list[str]:
    """Redfin's metro sale-price median, framed as a reference rather than an estimate.

    **The framing is the whole point of this section, not its wording.** The figure is a
    median over one metro-month series with no individual sales behind it, so it says
    what a typical 2-4 unit property in this metro sold for — and nothing whatsoever
    about *this* property's square footage, unit count, or condition. Printed in the
    findings table it would read as a value estimate; printed here, next to the asking
    price it is meant to be read against, it reads as what it is.
    """
    lines = ["### Market benchmark", ""]

    if detail is None or detail.benchmark_median_sale_price is None:
        reason = (detail.benchmark_unavailable_reason if detail else None) or (
            "The valuation step did not run."
        )
        lines.extend([f"**Not available.** {reason}", ""])
        return lines

    lines.append(
        f"Typical **Multi-Family (2-4 unit)** sale in the {detail.benchmark_metro} "
        f"metro: **{_money(detail.benchmark_median_sale_price)}**, the median over the "
        f"last {detail.benchmark_periods_averaged} monthly periods "
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
    lines.extend([
        "",
        "> **This is not an estimate of this property's value.** The source is "
        "pre-aggregated to one median per metro per month and exposes no individual "
        "sales, so it carries no square footage, unit count, or condition — the same "
        "figure describes every 2-4 unit property in the metro. It is a market "
        "reference for reading the asking price against, and nothing more.",
        "",
    ])
    return lines


def _rent_basis_section(state: DealState, detail) -> list[str]:
    """How the rent figure was reached, and whether the comps agreed with it.

    Rendered even when the cross-check did not run. A report that silently omits the
    check whenever it fails would show its working only on the runs where the working
    looked good, which is the opposite of what disclosure is for.
    """
    if detail is None or state.rent_estimate is None:
        return []

    lines = ["### How the rent figure was reached", ""]

    if detail.model_holdout_mae_dollars is not None:
        trained = (
            f", trained {detail.model_trained_at:%b %d, %Y}"
            if detail.model_trained_at else ""
        )
        lines.append(
            f"A linear regression on bedrooms, bathrooms and square footage, fit to "
            f"{detail.model_training_rows:,} listings{trained}. On a held-out slice it "
            f"missed by **{_money(detail.model_holdout_mae_dollars)}/mo on average** "
            f"({detail.model_holdout_mae_ratio:.3f} in ratio terms). That is the error "
            f"band on the figure above, and it is wide."
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
        if detail and detail.model_holdout_mae_dollars is not None:
            value += f" ± {_money(detail.model_holdout_mae_dollars)}"
        basis = str(state.rent_estimate_source or "unspecified")
        if state.rent_estimate_ratio_to_fmr is not None and state.fmr_anchor_used is not None:
            year = f"FY{detail.fmr_year} " if detail and detail.fmr_year else ""
            # Name the spatial resolution, not just the figure. ZIP schedules span
            # roughly 2x within a single county, so "FMR $2,220" means something very
            # different depending on which of the two it is.
            where = ""
            if detail and detail.fmr_resolution == "zip":
                where = f" (ZIP {detail.fmr_zip})" if detail.fmr_zip else " (ZIP)"
            elif detail and detail.fmr_resolution == "county":
                where = " (county-wide)"
            basis += (
                f", ratio {state.rent_estimate_ratio_to_fmr:.2f} × {year}FMR "
                f"{_money(state.fmr_anchor_used)}{where}"
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

    if state.scenarios:
        lines.append("### Scenarios")
        lines.append("")
        source = state.appreciation_source or "unspecified"
        lines.append(f"Appreciation series: `{source}`.")
        lines.append("")
        for name, detail in state.scenarios.items():
            lines.append(f"- **{name.title()}** — {detail}")
        lines.append("")
    else:
        lines.append(
            "### Scenarios\n\nNot produced — the forecast agent is unbuilt (U6). The "
            "rent estimate it will project from now exists; what U6 still has to settle "
            "is what a *value* forecast is anchored to, since this project has no "
            "property-level sale data to estimate one from.\n"
        )

    return lines


def summarizer_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state."""
    terms = state.deal_terms
    heading = terms.full_address or "Unidentified property"

    lines: list[str] = [f"# Deal Evaluation — {heading}", ""]

    lines.extend(_build_status_section(state.stub_nodes))

    if state.status == DealStatus.NEEDS_REVIEW or state.needs_human_review:
        # Deliberately does not name the confidence threshold as the cause. A critical
        # disclosure escalates on its own, above the threshold — see agents/critic.py —
        # so a banner that always blamed the score would misreport that case.
        lines.append(
            "> 🚩 **Escalated to human review.** This deal did not clear the system's "
            "automated checks on its own. See the disclosures below for why."
        )
        if state.human_review_note:
            lines.append(">")
            lines.append(f"> **Reviewer note:** {state.human_review_note}")
        lines.append("")

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
