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


def _findings_section(state: DealState) -> list[str]:
    terms = state.deal_terms
    lines = ["## Findings", ""]

    lines.append("| Metric | Value | Basis |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| Asking price | {_money(terms.price)} | listing |")
    lines.append(
        f"| Units | {terms.unit_count if terms.unit_count is not None else '—'} | listing |"
    )

    if state.rent_estimate is not None:
        basis = state.rent_estimate_source or "unspecified"
        if state.fmr_anchor_used is not None:
            basis += f", anchored to FMR {_money(state.fmr_anchor_used)}"
        lines.append(f"| Estimated rent | {_money(state.rent_estimate)}/mo | {basis} |")
    else:
        lines.append("| Estimated rent | not produced | valuation agent unbuilt (U5) |")

    if state.value_estimate is not None:
        lines.append(f"| Estimated value | {_money(state.value_estimate)} | comps-based |")
    else:
        lines.append("| Estimated value | not produced | valuation agent unbuilt (U5) |")

    lines.append("")

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
            "### Scenarios\n\nNot produced — the forecast agent is unbuilt (U6), and "
            "it has no base value to project from until U5 lands.\n"
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
