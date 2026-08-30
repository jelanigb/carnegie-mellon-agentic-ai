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
from state import (
    Comp,
    ConfidenceBreakdown,
    DealState,
    DealStatus,
    Flag,
    FlagScope,
    ForecastDetail,
    Severity,
    count_area_positioned,
    scope_of,
)

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

    lines = ["## Disclosures", ""]
    lines.append(
        f"{len(flags)} disclosure(s) were raised during this evaluation. Each is "
        "listed in full below, grouped by whether it describes this property or the "
        "data available for its market, and ordered most severe first within each."
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
        + ". Sections fed by them are unbuilt, not empty — each is "
        "scheduled for a later stage of this build.",
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

        # Rendered whenever the subject's market resolves to one of the four this
        # breakdown covers, whether or not the gap crossed the flag's threshold (Q2(a)):
        # a reader in a market that is not elevated should still see what "not elevated"
        # looks like next to the one that is.
        if (detail.subject_metro and detail.subject_metro_mae_dollars is not None
                and detail.subject_metro_mae_n is not None):
            lines.append(
                f"That figure is the model's error averaged across every market it was "
                f"trained on. In **{detail.subject_metro}** specifically, the same "
                f"held-out measurement missed by "
                f"**{_money(detail.subject_metro_mae_dollars)}/mo** "
                f"(n={detail.subject_metro_mae_n} held-out listings) — "
                + (
                    "materially worse than the figure above, see the disclosure below."
                    if detail.subject_metro_mae_dollars
                    > config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD
                    * detail.model_holdout_mae_dollars
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
    not a check (Q4). The reason is measured rather than cautious: the gap is ~-29% on all
    three demo listings, and it is structural. `rent_estimate` is anchored to FMR, a
    40th-percentile administrative rent, while the corpus the model learned from rents at
    roughly 1.40x that anchor — so the model predicts market-typical rent, and #11
    calibrated these listings to the anchor itself. Raising an objection from that would
    charge the deal for a property of the fixtures. Whether the offset belongs to the
    market or to the corpus is genuinely unsettled and needs an independently observed
    market-rent series to answer (OQ-6, #16), which is why
    `config.RENT_CLAIM_DIVERGENCE_DISCLOSURE_THRESHOLD` ships as `None`.

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

    # The caveat is direction-dependent, and getting that wrong would be worse than
    # omitting it. The estimate is anchored to a benchmark that sits below typical market
    # rents while the corpus behind the model sits above it, so the estimate leans high:
    # stated rents *below* it are the expected shape and say little, and stated rents
    # *above* it run against that lean and say more.
    if gap < 0:
        lines.extend([
            "",
            "> **A gap in this direction is expected and is not on its own evidence "
            "that the property is under-rented.** The estimate is anchored to a federal "
            "affordability benchmark that sits below typical market rents by design, "
            "while the listings the model learned from rent well above that benchmark — "
            "so the estimate leans toward market-typical rent, and these figures sit "
            "nearer the benchmark. An independently observed market-rent series "
            "(Zillow's rent index) now informs the estimate where its coverage allows — "
            "see the rent disclosures above — which narrows, but does not settle, which "
            "of the two better describes this local market.",
            "",
        ])
    else:
        lines.extend([
            "",
            "> **Stated rents above the estimate run against the direction this system "
            "tends to err.** The estimate is anchored to a federal affordability "
            "benchmark that sits below typical market rents, while the listings the "
            "model learned from rent well above it, so the estimate already leans "
            "toward the higher of the two. Rents stated above it are therefore worth "
            "verifying against leases rather than taken from the listing — the usual "
            "explanations are short-term or furnished tenancies, rents including "
            "utilities or parking, or figures that are asking rather than collected.",
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
        if detail and detail.model_holdout_mae_dollars is not None:
            value += f" ± {_money(detail.model_holdout_mae_dollars)} overall"
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

    lines.extend(_scenario_section(state))

    return lines


def _money_or_dash(value: Optional[float]) -> str:
    return _money(value) if value is not None else "—"


def _scenario_section(state: DealState) -> list[str]:
    """The forecast, its basis, and what the search discarded on the way.

    Three blocks rather than one table, and the split is the disclosure. The scenarios
    say what the forecast is; the basis says which treatment of which series produced
    it, including the fiscal years held out and the interquartile range the bands sit
    inside; the ledger says what else was considered. A reader who only reads the first
    block gets a forecast; one who reads all three can tell whether to believe it.
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

    base_rent = detail.projection_base_rent if detail else None
    base_price = detail.projection_base_price if detail else None
    basis_parts = []
    if base_rent is not None:
        basis_parts.append(f"modelled rent {_money(base_rent)}/mo")
    if base_price is not None:
        basis_parts.append(f"the **asking price** {_money(base_price)}")
    if basis_parts:
        lines.append(
            f"Projected from {' and '.join(basis_parts)}. The price side compounds the "
            f"asking price rather than an estimated value — this system does not produce "
            f"one, and says so above."
        )
        lines.append("")
        lines.append(
            "Scenarios are named for their **combined** outcome across both quantities. "
            "Because rent growth and price growth are negatively correlated in this "
            "project's data, a single column need not fall in label order — the "
            "pessimistic case can carry the higher projected price and still be the worse "
            "outcome overall. Each row states which band it drew from on each side."
        )
        lines.append("")

    lines.append(
        "| Scenario | Rent growth | Price growth | "
        f"Rent in yr {horizon} | Price in yr {horizon} |"
    )
    lines.append("| --- | --- | --- | --- | --- |")
    for scenario in state.scenarios:
        rent_growth = (
            f"{scenario.rent_growth_pct_per_year:+.2f}%/yr ({scenario.rent_band})"
            if scenario.rent_growth_pct_per_year is not None
            else "—"
        )
        price_growth = (
            f"{scenario.price_growth_pct_per_year:+.2f}%/yr ({scenario.price_band})"
            if scenario.price_growth_pct_per_year is not None
            else "—"
        )
        lines.append(
            f"| **{scenario.name.title()}** | {rent_growth} | {price_growth} | "
            f"{_money_or_dash(scenario.projected_monthly_rent)} | "
            f"{_money_or_dash(scenario.projected_price)} |"
        )
    lines.append("")

    for scenario in state.scenarios:
        if scenario.rationale:
            lines.append(f"- **{scenario.name.title()}** — {scenario.rationale}")
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
            f"FY{detail.rent_growth_first_year}–{detail.rent_growth_last_year}"
            if detail.rent_growth_first_year
            else "the published history"
        )
        lines.append(
            f"**Rent** — HUD Fair Market Rent history for "
            f"{detail.rent_growth_area_name or 'the subject county'}, "
            f"{detail.rent_growth_bedrooms}-bedroom, at "
            f"{detail.rent_growth_resolution} resolution over {span} "
            f"({detail.rent_growth_n_observations} year-over-year observations). "
            f"The bands are the worst and best fiscal years observed "
            f"(FY{detail.rent_growth_pessimistic_year} and "
            f"FY{detail.rent_growth_optimistic_year}); the base case is their compound "
            f"average."
        )
        if detail.rent_growth_iqr_lower_pct is not None:
            lines.append(
                f"  Interquartile range of those annual changes: "
                f"{detail.rent_growth_iqr_lower_pct:.2f}% to "
                f"{detail.rent_growth_iqr_upper_pct:.2f}% — shown so an extreme band "
                f"that rests on an isolated year is visible as one."
            )
        if detail.cohort_shift_years_excluded:
            years = ", ".join(f"FY{y}" for y in detail.cohort_shift_years_excluded)
            lines.append(
                f"  {years} were held out: every one of the {detail.cohort_n_areas} HUD "
                f"areas in this project's panel moved together in those years, against a "
                f"{detail.cohort_baseline_pct:.2f}% baseline. Whether that was a HUD "
                f"methodology change or a delayed market signal is not determinable from "
                f"this series, so it is disclosed rather than attributed."
            )
        if detail.local_deviation_years:
            years = ", ".join(f"FY{y}" for y in detail.local_deviation_years)
            lines.append(
                f"  {years} saw this area depart sharply from the national cohort — a "
                f"local move, kept in the bands because that is market signal."
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
        "#### What the forecast search considered",
        "",
        f"{len(entries)} hypotheses were evaluated and {len(pruned)} discarded. "
        f"Pruning is recorded rather than silent: an evaluator that quietly drops a "
        f"correct-but-unusual branch looks identical to one working properly.",
        "",
    ]
    for entry in pruned:
        score = f"{entry.score:.2f}" if entry.score is not None else "not scored"
        lines.append(f"- `{entry.id}` ({score}) — {entry.summary} **Discarded:** {entry.prune_reason}")
    lines.append("")
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
