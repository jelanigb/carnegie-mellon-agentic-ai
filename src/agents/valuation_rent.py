"""Valuation & Rent agent — U5. Produces the deal's rent estimate, or says why it can't.

**The number this agent emits is a modelled ratio times a dated government reference,
and the design turns on that being true rather than convenient.** §2's rent-anchoring
argument in one line: the Kaggle corpus is a Dec 2018 - Dec 2019 scrape, so a regression
fit on its rent column predicts 2019 dollars, and a 2019 dollar figure printed in a 2026
report is wrong while looking entirely ordinary — no error bar, no missing value,
nothing a reader could catch. `tools/model/rent_model.py` therefore learns
rent ÷ local-FMR-at-the-time, and this agent multiplies that ratio by *today's* FMR for
the subject's own county.

**The obvious shortcut is the one thing this file must never do.** Averaging the
retrieved comps' rents would produce a plausible figure in one line, and §8 forbids it:
never let an unanchored Kaggle dollar figure reach the Summarizer. The U2 stub refused
that shortcut and emitted nothing at all rather than take it; the real implementation
keeps that discipline and adds an anchor instead of relaxing it. Every path below that
cannot anchor produces *no rent figure*, never a fallback one.

**What is deliberately not built here.**

- **The LLM fallback path** — §6's cut list item 3,
  descoped Aug 21, 2026 in advance rather than abandoned mid-build. `RentEstimateSource`
  still carries `LLM_FALLBACK` as a member, so the seam is typed and unused rather than
  absent. See `TODO(cut-list)` below for what taking it would cost.
- **A property-level value estimate.** `DealState.value_estimate` stays `None` on every
  run of this build, and that is a decision with evidence behind it rather than an
  unfinished section. The only sale-price source in this project is Redfin's extract,
  which is pre-aggregated to one median per metro-period: 306 rows total, zero
  individual sales, no square footage or unit count to adjust by. A "value estimate"
  built from it would return the same dollar figure for a 2-unit duplex and a 4-unit
  building in the same metro, because there is nothing in the inputs that could
  distinguish them. Worse, this repo's demo asking prices were *calibrated to that same
  median* (`demo_deals.price_basis`), so emitting it as an estimate would produce
  reports where the estimated value matches the asking price to within $140 — an
  agreement that measures nothing except that both numbers came from one source. The
  median is still genuinely useful, so it is carried as
  `ValuationDetail.benchmark_median_sale_price` and rendered as a labelled market
  reference the asking price is read *against*, not as this property's value.

Reason/Act/Observe/Decide:

- **Reason.** Establish what this deal can actually support. Four things have to hold
  before a rent figure is defensible — a trained model on disk, the subject's own
  bed/bath/sqft, a resolvable county, and an FMR schedule for it — and each failure is
  disclosed by name rather than collapsed into "unavailable."
- **Act.** Predict the rent-to-FMR ratio from the subject's features, then anchor it
  against the current FMR for `deal_terms.county_fips`.
- **Observe.** Re-express every retrieved comp's rent in the subject's current dollars
  and compare the estimate against their median. This is the step that makes the agent
  a loop rather than a call: the comps were retrieved by a different agent for a
  different purpose, and asking whether they agree is the only check available on a
  number with no ground truth. A wide divergence is signal, not noise.
- **Decide.** Emit the estimate with a flag naming every approximation it rests on — the
  anchoring mechanism itself, any FMR bedroom cap, any disagreement with the comps — so
  the report discloses how the number was reached rather than only what it is.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

import pandas as pd

import config
from state import (
    DealState,
    DealTerms,
    FlagKind,
    RentEstimateSource,
    Severity,
    ValuationDetail,
    flag,
)
from tools import hud_fmr, kaggle_data, redfin_data, zcta_crosswalk, zori
from tools.model import rent_model

AGENT = "valuation_rent"

# TODO(cut-list): the LLM fallback estimator (§6 cut list, item 3) is descoped, not
# designed away. It would sit here, after the ratio path has failed to anchor: prompt a
# model for a rent figure with the comp set as context, write it with
# `RentEstimateSource.LLM_FALLBACK`, and raise a flag kind that would have to be re-added
# to `FlagKind` — it was removed Aug 28, 2026 once U8.1's coverage census showed it was the
# one member nothing in the build could raise (see `state.FlagKind`). What
# it costs is not the call — `tools/llm_client.call_with_schema` already does the hard
# part — but the evaluation: an unanchored LLM figure is exactly the failure mode §2
# exists to prevent, so shipping one needs the ungrounded-vs-grounded comparison
# `scripts/retrieval_ablation_llm.py` did for comps, repeated for rents. That is a unit
# of work, not a loose end, which is why it was cut in advance rather than half-built.


@lru_cache(maxsize=None)
def _metro_benchmark(metro: str) -> Optional[tuple[float, int, float]]:
    """Redfin's smoothed median sale price for 2-4 unit properties in one metro.

    Returns `(median, periods_averaged, homes_sold_per_period)`, or `None` when the
    extract does not reach this metro — New York is the standing case (§2), which is
    why the Staten Island demo deal exists.

    **Smoothed over `config.REDFIN_ROLLING_WINDOW_PERIODS` rather than read off the
    latest period, on measurement.** Across the last 12 periods the month-over-month
    swing in this series runs a median 1.5% in Chicago and 2.4% in Los Angeles, but
    **6.9% in Cleveland with a 14.4% maximum** — a single-month median there is noise a
    reader would mistake for a market move. The same three-period window the
    appreciation series uses, reused rather than re-tuned, so the report and the
    forecast are not smoothing the same source differently.

    Sub-floor periods are dropped first, for the reason `config.MIN_SALE_PRICE_USD`
    exists: a non-arm's-length transfer in the window would drag the mean.

    Cached because `load_redfin` reads a 19 MB CSV, and the pipeline would otherwise pay
    that on every deal. Keyed on the metro name, which is the only input.
    """
    try:
        frame = redfin_data.load_redfin()
    except (FileNotFoundError, OSError):
        return None

    rows = frame[(frame["metro"] == metro) & (~frame["below_price_floor"])]
    rows = rows.sort_values("period").tail(config.REDFIN_ROLLING_WINDOW_PERIODS)
    if rows.empty:
        return None
    return (
        float(rows["median_sale_price"].mean()),
        int(len(rows)),
        float(rows["homes_sold"].median()),
    )


def _index_staleness_months(month: Optional[str]) -> Optional[int]:
    """How many months old the market index's newest observation is, or `None`.

    Read against today rather than against the file's own newest column, because the
    question a reader has is how current the estimate is, not how current the file is.
    """
    if not month:
        return None
    observed, now = pd.Timestamp(month), pd.Timestamp.now()
    return max(0, (now.year - observed.year) * 12 + (now.month - observed.month))


def _resolve_market_label(terms: DealTerms) -> Optional[str]:
    """The subject's market label ("Chicago", "New York", ...), or None.

    One resolver for every per-market lookup in this agent — the Redfin benchmark, the
    per-metro error figure — matched the way `config.INDEXED_MARKETS` defines a market:
    the state key plus word-boundary city matching over the market's own city patterns
    (`kaggle_data.city_matches`, the rule that folds "Cleveland Heights" into Cleveland
    while keeping "Queensbury" out of Queens), with `patterns[0]` as the label.

    Until U8.4c the benchmark had its own weaker matcher — the city against the metro
    *label* alone, no state check — which no borough name ever matched, so a Brooklyn
    subject read as outside the New York market. That was one half of the "Redfin
    doesn't cover New York" misdiagnosis (the other was the trio-only region filter,
    fixed in `config.REDFIN_TARGET_METROS`). Two notions of "is this city in that
    market" is one of the ways a system quietly starts disagreeing with itself.
    """
    if not terms.city or not terms.state:
        return None
    return next(
        (
            patterns[0]
            for state, patterns in config.INDEXED_MARKETS.items()
            if terms.state == state and kaggle_data.city_matches(terms.city, patterns)
        ),
        None,
    )


def _attach_benchmark(detail: ValuationDetail, terms: DealTerms) -> None:
    """Resolve the subject to a Redfin metro and record the benchmark, or why not.

    Runs regardless of whether a rent estimate turns out to be possible, because the two
    fail for unrelated reasons: a subject with no county has no FMR anchor but is still
    in a metro the price series covers, and a reader comparing the asking price to the
    market should not lose that because the rent path stopped earlier.
    """
    if not terms.city:
        detail.benchmark_unavailable_reason = (
            "The listing resolved to no city, so no metro sale-price series applies."
        )
        return

    metro = _resolve_market_label(terms)
    if metro is None or metro not in redfin_data.TARGET_METROS:
        # "This build's series" rather than "Redfin's extract": the second claims a
        # coverage fact about the source that this code never checks, and shipping that
        # claim unchecked is how a stale trio-only filter got reported as a Redfin
        # limitation for months (U8.4c).
        detail.benchmark_unavailable_reason = (
            f"This build's metro sale-price series does not reach {terms.city}. It is "
            f"scoped to the {', '.join(sorted(redfin_data.TARGET_METROS))} markets."
        )
        return

    benchmark = _metro_benchmark(metro)
    if benchmark is None:
        detail.benchmark_unavailable_reason = (
            f"No usable sale-price periods for the {metro} metro in the Redfin extract."
        )
        return

    median, periods, homes_sold = benchmark
    detail.benchmark_metro = metro
    detail.benchmark_median_sale_price = median
    detail.benchmark_periods_averaged = periods
    detail.benchmark_homes_sold_per_period = homes_sold


def _attach_model_provenance(detail: ValuationDetail, bundle: dict) -> None:
    """Copy the persisted training run's numbers onto the detail object.

    Read from the bundle rather than from `config.py` or a docstring, so the error band
    the report prints is the one the artifact on disk actually scored. A retrain that
    moves the MAE moves the reported figure with it; a hardcoded one would keep quoting
    a model that is no longer there.
    """
    report = bundle.get("report") or {}
    detail.model_holdout_mae_dollars = report.get("mae_dollars_at_holdout_fmr")
    detail.model_holdout_mae_ratio = report.get("mae_ratio")
    detail.model_training_rows = report.get("rows_trained")
    detail.model_trained_at = bundle.get("trained_at")


def _attach_metro_error(
    detail: ValuationDetail, terms: DealTerms, bundle: dict, planner_invocations: int
) -> list:
    """Resolve the subject to one of the four markets `mae_dollars_by_metro` covers, and
    flag when that market's historical error runs materially worse than the model's
    headline figure (U8.4, OQ-3).

    Matched by `_resolve_market_label` — since U8.4c literally the same function
    `_attach_benchmark` uses, over the same `config.INDEXED_MARKETS` grouping
    `tools.model.rent_model._mae_dollars_by_metro` used to produce these figures, so the
    three cannot drift apart.

    Sets `detail.subject_metro*` whenever the market resolves, independent of whether the
    ratio crosses the flag's threshold: per Q2(a), the report prints this market's error
    on every run, not only a flagged one, so a reader in a good market can see what good
    looks like. A subject outside these four markets gets `None` — a fact about this
    breakdown's coverage, not a degradation to disclose.
    """
    by_metro = (bundle.get("report") or {}).get("mae_dollars_by_metro") or {}
    label = _resolve_market_label(terms)
    if label is None or label not in by_metro:
        return []

    stats = by_metro[label]
    detail.subject_metro = label
    detail.subject_metro_mae_dollars = stats["mae_dollars"]
    detail.subject_metro_mae_n = stats["n"]

    overall = detail.model_holdout_mae_dollars
    threshold = config.RENT_MODEL_METRO_ERROR_RATIO_THRESHOLD
    if not overall or stats["mae_dollars"] <= threshold * overall:
        return []

    ratio = stats["mae_dollars"] / overall
    return [
        flag(
            AGENT,
            FlagKind.RENT_ESTIMATE_MARKET_ERROR_ELEVATED,
            f"The rent model's historical error in {label} is ${stats['mae_dollars']:,.0f}, "
            f"{ratio:.1f}x the ${overall:,.0f} error quoted elsewhere in this report as "
            f"the model's typical accuracy, measured on {stats['n']} held-out {label} "
            f"listings. This is a known weakness of the model in this particular market, "
            f"not a property of this deal or a sign the model has never seen a market like "
            f"it — {label} listings are part of what the model trained on; they are just "
            f"harder to price accurately than most. Treat this estimate as less reliable "
            f"than the headline error band on its own would suggest.",
            Severity.WARN,
            planner_invocations,
        )
    ]


def _cross_check(
    detail: ValuationDetail,
    state: DealState,
    estimate: float,
    subject_anchor: float,
) -> list:
    """Compare the estimate against the comp set, normalized to the same dollars.

    Returns the flags this observation warrants — at most one, and often none. The
    normalization itself lives in `rent_model.anchor_comp_rents`, next to the identical
    operation the training set performs, so the two cannot drift into normalizing the
    same quantity differently.

    Silent when too few comps survive normalization: `config.RENT_COMP_CROSSCHECK_MIN_COMPS`
    is the floor, and below it the counts on `detail` carry the disclosure instead. A
    divergence measured against one comp would report on that comp, not on the estimate.

    **What this check caught on its first live run was not what it was expecting, and
    the first explanation for it was wrong.** Across five subjects the estimate came in
    *below* the comp median every time — 13.0% and 21.6% in Los Angeles, 29.7% and 30.4%
    in Chicago, 40.0% in Cleveland. Comparing each comp set against its metro's whole
    2-bedroom population made retrieval look like the culprit, and that reading was
    recorded here before it was checked properly. It does not hold: a comp set is drawn
    from a 2-4 mile radius, so comparing it to a metro measures the neighborhood.

    Against the candidate pool at the same radius, semantic ranking moves the comp median
    only +2.7% / +21.6% / +4.2%, while the neighborhood moves it +5.1% / +40.1% / +66.2%.
    The comps are reporting genuine neighborhood premiums correctly.

    **The divergence is the model's, and it is structural rather than a fitting error.**
    `config.RENT_MODEL_FEATURES` excludes any market identifier by design, so the anchor
    is the only channel through which location enters an estimate at all, and whatever the
    anchor fails to absorb is error the model structurally cannot recover. This check
    therefore fires on a known blind spot rather than on an anomaly, which is a limitation
    of the check worth stating plainly. The flag still declines to name a culprit, but now
    for the accurate reason: the disagreement is real and the comps are the better-informed
    of the two inputs about location.

    **U11.3 narrowed that blind spot without closing it, and the distinction matters to
    how this paragraph should be read.** Until then the anchor was county-grain wherever
    HUD published no Small Area schedule — all of Los Angeles, all of New York — so
    "nothing in the pipeline can represent variation below the county" was literally true
    there. The hybrid anchor reads the market index at the subject's own ZIP, so sub-county
    variation now does reach the estimate in every market the index covers. What is left is
    variation below the ZIP, plus the county-tier rows the index does not cover. Expect this
    check to fire less often and to mean something narrower when it does.

        `scripts/valuation_evidence.py --diagnose-divergence`.

    **No drift correction on either side since U11.3, and that is the anchor change
    paying off here.** Until then both the estimate and the comp-implied figures were a
    vintage ratio times *today's* FMR, so both carried the schedule-vs-market drift U8.0
    measured and `tools/rent_drift.py` scaled both symmetrically to cancel it out of
    `divergence_pct`. The anchor is now a market series read at each row's own month, so
    the vintage divides out where it arises and there is no residual level error left for
    a correction to remove.
    """
    anchoring = rent_model.anchor_comp_rents(state.comps, subject_anchor)
    detail.comps_available = anchoring.comps_available
    detail.comps_cross_checked = anchoring.comps_used
    detail.comps_zip_anchored = anchoring.zip_anchored

    if anchoring.comps_used < config.RENT_COMP_CROSSCHECK_MIN_COMPS:
        return []

    median = anchoring.median
    detail.comp_implied_rent_median = median
    detail.comp_implied_rent_p25 = anchoring.percentile(25)
    detail.comp_implied_rent_p75 = anchoring.percentile(75)
    # Signed, so the report can say which way the estimate leans. An absolute value
    # would tell a reader the estimate is suspect without telling them how.
    detail.divergence_pct = (estimate - median) / median

    if abs(detail.divergence_pct) <= config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:
        return []

    direction = "above" if detail.divergence_pct > 0 else "below"
    return [
        state.flag(
            AGENT,
            FlagKind.RENT_DIVERGES_FROM_COMPS,
            f"The modelled rent of ${estimate:,.0f}/mo sits "
            f"{abs(detail.divergence_pct):.0%} {direction} the ${median:,.0f}/mo implied "
            f"by {anchoring.comps_used} of {anchoring.comps_available} retrieved comps, "
            f"each normalized to this county and this fiscal year before comparing. "
            f"The threshold is {config.RENT_COMP_DIVERGENCE_THRESHOLD_PCT:.0%}. "
            f"Neither figure is ground truth and this flag does not say which is wrong: "
            f"a gap this size means either the model is off for this property or the "
            f"retrieved comps are not representative of the market. Check the comp "
            f"disclosures above — a set concentrated in one location or drawn from one "
            f"aggregator can sit well away from its own metro. Treat the rent figure as "
            f"the wider of the two ranges.",
            Severity.WARN,
        )
    ]


def valuation_rent_agent(state: DealState) -> dict:
    """Node function: returns a partial state update, never the whole state.

    Every early return below carries `valuation_detail`, so a run that produces no rent
    figure still tells the report what it *did* establish — the market benchmark, the
    model's training provenance — instead of returning an empty section that reads as
    "nothing was determined about this property."
    """
    terms = state.deal_terms
    detail = ValuationDetail()
    flags: list = []

    # Independent of the rent path and computed first for that reason; see
    # `_attach_benchmark`.
    _attach_benchmark(detail, terms)

    bundle = rent_model.load()
    if bundle is None:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ESTIMATE_UNAVAILABLE,
                "No trained rent model is present on this machine "
                f"({config.RENT_MODEL_PATH.name} is absent), so no rent figure was "
                "produced. Run scripts/train_rent_model.py. The pipeline completed and "
                "every other section is real; only the rent estimate is missing.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    _attach_model_provenance(detail, bundle)
    # Independent of everything below: it only needs city/state and the persisted
    # report, not a resolved county or a successful estimate. See `_attach_benchmark`
    # for why that independence matters — a subject that fails later still gets this
    # disclosure.
    flags.extend(_attach_metro_error(detail, terms, bundle, state.planner_invocations))

    # The model takes exactly these three, and a missing one cannot be defaulted: a zero
    # or a corpus mean silently substituted here would produce a rent figure describing
    # a property the listing never described. The Extractor has already raised
    # UNRESOLVED_FIELD for each of them, so this flag names the consequence rather than
    # repeating the cause.
    missing = [
        name
        for name, value in (
            ("bedrooms", terms.bedrooms),
            ("bathrooms", terms.bathrooms),
            ("square_footage", terms.square_footage),
        )
        if value is None
    ]
    if missing:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ESTIMATE_UNAVAILABLE,
                f"The rent model requires {', '.join(config.RENT_MODEL_FEATURES)}, and "
                f"the listing did not resolve {', '.join(missing)}. No rent figure was "
                f"produced; substituting a default for a field the listing never stated "
                f"would describe a different property.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    # No county, no FMR, no anchor, no estimate — see the module docstring on why there
    # is no fallback here. Severity is CRITICAL rather than the WARN §2 originally
    # specified, and the change is deliberate: that severity was written when the design
    # still had a coarser state/national fallback behind it, so the flag meant "this
    # figure is less precise." With the fallback removed there is no figure at all, and
    # a warn-level flag on a missing headline number would understate it to the Critic's
    # confidence scoring as much as to a reader.
    if terms.county_fips is None:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ANCHOR_UNAVAILABLE,
                "The subject property resolved to no county, so there is no local rent "
                "reference to anchor against and no rent estimate was produced. Every "
                "rent figure in this system is a modelled ratio times a local market "
                "reference; without the second term there is no number to report. "
                "Causes: no resolvable coordinates, or a New England address, which the "
                "federal rent schedule prices by town rather than by county.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    # Resolve the subject's ZIP before the lookup. The Extractor's parsed `zip_code` is
    # preferred over a polygon join because it came from the listing itself; the ZCTA
    # join is the fallback for a listing that stated no ZIP. Both are needed: the model
    # is trained against ZIP-resolution FMR wherever HUD publishes it, so anchoring the
    # subject at county resolution would multiply a ZIP-relative ratio by a county-level
    # figure — two different denominators, wrong by the spread between them.
    #
    # **Gated on what the model was actually trained with, not on what HUD publishes
    # today.** SAFMR coverage expanded after 2020: Los Angeles has 474 ZIP schedules for
    # FY2026 and none for the corpus's FY2019 vintage, so its training rows are
    # county-anchored. Asking for a ZIP anchor there would apply a ZIP-level figure to a
    # county-relative ratio. The persisted training report carries the counties that were
    # ZIP-anchored, and only those get ZIP resolution here.
    subject_zip = terms.zip_code or zcta_crosswalk.lookup_zcta(
        terms.latitude, terms.longitude
    )

    # **The anchor is ZORI for the level and FMR only for the bedroom step (U11.3).** The
    # subject is read at the market index's newest observation rather than at a fiscal
    # year, because ZORI is a monthly market series and the estimate is meant to be in
    # today's dollars; the FMR half is read at the current fiscal year and its level
    # divides out, so the schedule's own drift against the market never reaches the
    # figure. `rent_model.anchor_for_row` is the same function training used, which is
    # what keeps the two from drifting apart.
    try:
        client = hud_fmr.HudFmrClient()
        fiscal_year = rent_model.fmr_fiscal_year(pd.Timestamp.now())
        tables = rent_model.build_anchor_tables(
            {(terms.county_fips, fiscal_year)}, client
        )
        month = zori.latest_month(tables.zori_panel) if tables.available else None
        subject_anchor, anchor_tier = (
            rent_model.anchor_for_row(
                int(terms.bedrooms), terms.county_fips, fiscal_year,
                month, subject_zip, tables,
            )
            if month
            else (float("nan"), "none")
        )
    except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError) as exc:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ANCHOR_UNAVAILABLE,
                f"County {terms.county_fips} resolved, but the reference rent figures "
                f"this estimate is built from could not be retrieved "
                f"({type(exc).__name__}). No rent estimate was produced. This is a "
                f"lookup failure rather than a property that cannot be priced — a re-run "
                f"may succeed.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    if anchor_tier == "none" or subject_anchor != subject_anchor:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ANCHOR_UNAVAILABLE,
                "No reference rent figure could be resolved for this property, so no "
                "rent estimate was produced. Every rent figure in this system is a "
                "modelled ratio times a local market reference; without the second term "
                "there is no number to report. Causes: the market rent index covers "
                "neither this ZIP nor its county, or no federal rent schedule exists for "
                "the county — which is the case throughout New England, where the "
                "schedule is published by town.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    detail.fmr_shape_year = fiscal_year
    detail.anchor_tier = anchor_tier
    detail.anchor_zip = subject_zip if anchor_tier == "zip" else None

    if anchor_tier == "county":
        # **The consequence is identical; the cause is not, and the message says which
        # (U8.2b's rule, applied to the new anchor).** One flag kind rather than two: a
        # reader's response is the same either way — treat the figure as describing the
        # county, not the address.
        #
        # Under the FMR anchor this meant "HUD publishes no ZIP-level schedule here".
        # Under the market-index anchor it means the ZIP's own series has not begun, or
        # covers this month with a gap, so the county's median across its covered ZIPs
        # stood in. That is a different cause with the same consequence, and it is far
        # more common at the corpus's vintage than at today's — which is why 1,528 of the
        # model's own training rows carry it too (U11.3).
        behind = rent_model.county_zip_count(tables, terms.county_fips, month)
        thin = (
            f" That median rests on only {behind} ZIP codes, so it carries little more "
            f"local detail than a metro average would."
            if behind and behind < config.RENT_ANCHOR_MIN_COUNTY_ZIPS
            else ""
        )
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ANCHOR_COUNTY_LEVEL,
                f"This estimate is anchored to a county-wide market rent figure rather "
                f"than to this ZIP code's own, because the rent index Zillow publishes "
                f"for ZIP {subject_zip or 'this address'} does not cover the period this "
                f"estimate reads from. Rents span roughly 2x within a single county, so a "
                f"county anchor cannot distinguish an expensive neighborhood from a cheap "
                f"one — the estimate describes the county's rent level, not this "
                f"address's.{thin}",
                Severity.WARN,
            )
        )

    _, bedroom_cap_exceeded = rent_model.bedroom_shape(
        int(terms.bedrooms), terms.county_fips, fiscal_year, tables.fmr_county
    )
    if bedroom_cap_exceeded:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FMR_BEDROOM_CAP_EXCEEDED,
                f"The subject has {terms.bedrooms} bedrooms; the federal rent schedule "
                f"this estimate uses to step between unit sizes stops at four, so the "
                f"four-bedroom step was applied. Larger units rent above it, so the "
                f"estimate is likely conservative.",
                Severity.INFO,
            )
        )

    # The market index is only as current as its newest observation, and Zillow publishes
    # on a lag. Disclosed rather than corrected: there is nothing to correct *to*, and a
    # reader weighing a rent figure should know how old the market read behind it is.
    staleness = _index_staleness_months(month)
    detail.anchor_index_month = month
    detail.anchor_index_staleness_months = staleness
    if staleness is not None and staleness > config.RENT_ANCHOR_MAX_STALENESS_MONTHS:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ANCHOR_INDEX_STALE,
                f"The market rent index this estimate is anchored to was last observed "
                f"{staleness} months ago ({month}). The estimate is only as current as "
                f"that reading, and rents may have moved since.",
                Severity.WARN,
            )
        )

    # **Competence before prediction (U11.1).** Asked of the inputs, and asked first,
    # because the answer must not depend on which estimator is fitted. Until U11.1 this
    # was answered downstream by the output-side band below: the LinearRegression that
    # shipped then extrapolated an implausible *ratio* for a subject unlike anything it
    # trained on, and the band caught it. A tree-based estimator cannot do that — its
    # prediction is an average of training targets already inside that band — so it
    # returns a confident number instead, and the disclosure would have disappeared as a
    # side effect of a model swap rather than by any decision. See
    # `rent_model.subject_is_out_of_domain` for the measurement.
    #
    # Same `FlagKind` as the band below, with the cause branching, on this file's own rule
    # (U8.2b): a reader's response is identical — there is no rent figure and none should
    # be inferred — while the sentence explaining why has to be true of the deal in front
    # of them.
    out_of_domain = rent_model.subject_is_out_of_domain(
        bundle, terms.bedrooms, terms.bathrooms, terms.square_footage
    )
    if out_of_domain is not None:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ESTIMATE_UNAVAILABLE,
                f"No rent estimate was produced for this property, because "
                f"{out_of_domain}. The model can only speak to properties resembling the "
                f"ones it learned from, and this subject's {terms.bedrooms}bd / "
                f"{terms.bathrooms}ba / {terms.square_footage:,.0f} sqft falls outside "
                f"that. A figure produced here would look like every other estimate in "
                f"this report while resting on nothing comparable, so none is given.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    ratio = rent_model.predict_ratio(
        bundle, terms.bedrooms, terms.bathrooms, terms.square_footage
    )

    # `predict_ratio` deliberately returns the raw model output so an implausible
    # prediction stays visible instead of being clipped into looking reasonable. This is
    # where that decision is paid off: the same bounds the training set applied to drop
    # data defects are applied to the model's own output.
    #
    # **Kept as a second line of defense after U11.1 moved the competence check upstream,
    # not made redundant by it.** The two ask different questions: the domain check above
    # asks whether the *subject* resembles the training data, this asks whether the
    # *model* produced something coherent. Under the current gradient-boosting form this
    # branch is unreachable by construction — every prediction is an average of training
    # targets already inside the band — and that is a reason to keep it rather than
    # delete it, since it is the form, not the requirement, that made it quiet.
    if not config.RENT_MODEL_MIN_RATIO <= ratio <= config.RENT_MODEL_MAX_RATIO:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_ESTIMATE_UNAVAILABLE,
                f"The model predicted a rent-to-FMR ratio of {ratio:.2f}, outside the "
                f"plausible band {config.RENT_MODEL_MIN_RATIO}-"
                f"{config.RENT_MODEL_MAX_RATIO} that its own training set was bounded "
                f"to. The subject's {terms.bedrooms}bd / {terms.bathrooms}ba / "
                f"{terms.square_footage:,.0f} sqft falls outside the range this model "
                f"can speak to, so no rent figure was produced.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    estimate = ratio * subject_anchor

    flags.extend(_cross_check(detail, state, estimate, subject_anchor))

    # Raised on every estimate that took this path, without exception. INFO rather than
    # WARN because it describes a mechanism working as designed, not a degradation —
    # the severity guidance in the report says exactly that. It is here so that no
    # reader can mistake a modelled ratio times a reference figure for an observed
    # market rent.
    #
    # **Rewritten at U11.3 with the anchor.** Its previous form named HUD Fair Market
    # Rent as the reference and closed by saying the rent-to-FMR stability assumption had
    # been measured and found to have drifted. Both halves stopped being true: the level
    # now comes from a market index read at the same month on both ends, so there is no
    # schedule-versus-market gap left to disclose.
    flags.append(
        state.flag(
            AGENT,
            FlagKind.RENT_ANCHORED_TO_MARKET_INDEX,
            f"Estimated rent of ${estimate:,.0f}/mo is a modelled ratio of {ratio:.2f} "
            f"applied to a reference rent of ${subject_anchor:,.0f} for "
            + (f"ZIP {detail.anchor_zip}" if detail.anchor_tier == "zip"
               else f"county {terms.county_fips}")
            + f", read from Zillow's published rent index for {month} and stepped to "
            f"{terms.bedrooms} bedrooms using the federal rent schedule's own ratio "
            f"between unit sizes. It is not an observed rent for this building. The "
            f"ratio comes from a model trained on 2018-19 listings normalized against "
            f"the same index at their own listing months, so what it carries forward is "
            f"how this property compares to its neighbors rather than what anything "
            f"cost in 2019.",
            Severity.INFO,
        )
    )

    return {
        "rent_estimate": estimate,
        "rent_estimate_ratio_to_anchor": ratio,
        "rent_anchor_used": subject_anchor,
        "rent_estimate_source": RentEstimateSource.REGRESSION_MODEL,
        "valuation_detail": detail,
        "flags": flags,
    }
