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
from tools import hud_fmr, kaggle_data, redfin_data, rent_drift, zcta_crosswalk
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
    subject_fmr: float,
    drift_factor: float = 1.0,
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
    `config.RENT_MODEL_FEATURES` excludes any market identifier by design, so the
    county-level FMR anchor is the only channel through which location enters an estimate
    at all — and nothing in the pipeline can represent variation below the county. This
    check therefore currently fires on a known blind spot rather than on an anomaly, which
    is a limitation of the check worth stating plainly. The flag still declines to name a
    culprit, but now for the accurate reason: the disagreement is real and the comps are
    the better-informed of the two inputs about location.

        `scripts/valuation_evidence.py --diagnose-divergence`.

    **The drift correction applies to both sides, symmetrically (U8.4b).** Comp-implied
    rents are built the same way the estimate is — a vintage ratio times the subject's
    *today* FMR — so they carry exactly the same schedule-vs-market drift U8.0 measured.
    `drift_factor` therefore scales the comp-implied figures here just as it scaled the
    estimate before it arrived, which keeps every reported dollar in the same corrected
    terms while cancelling out of `divergence_pct` entirely: the check goes on measuring
    structure against structure. Correcting only the estimate would have injected a
    systematic ~−12% gap and reported it as a model-vs-comps disagreement.
    """
    anchoring = rent_model.anchor_comp_rents(state.comps, subject_fmr)
    detail.comps_available = anchoring.comps_available
    detail.comps_cross_checked = anchoring.comps_used
    detail.comps_zip_anchored = anchoring.zip_anchored

    if anchoring.comps_used < config.RENT_COMP_CROSSCHECK_MIN_COMPS:
        return []

    median = anchoring.median * drift_factor
    detail.comp_implied_rent_median = median
    detail.comp_implied_rent_p25 = anchoring.percentile(25) * drift_factor
    detail.comp_implied_rent_p75 = anchoring.percentile(75) * drift_factor
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
                FlagKind.FMR_UNAVAILABLE_FOR_COUNTY,
                "The subject property resolved to no county, so there is no HUD Fair "
                "Market Rent to anchor against and no rent estimate was produced. "
                "Every rent figure in this system is a modelled ratio times a local "
                "FMR; without the second term there is no number to report. Causes: no "
                "resolvable coordinates, or a New England address, which HUD prices by "
                "town rather than by county.",
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
    trained_zip_counties = set(
        (bundle.get("report") or {}).get("zip_anchored_counties") or []
    )
    subject_zip = None
    if terms.county_fips in trained_zip_counties:
        subject_zip = terms.zip_code or zcta_crosswalk.lookup_zcta(
            terms.latitude, terms.longitude
        )

    try:
        client = hud_fmr.HudFmrClient()
        anchor = client.get_fmr_for_bedroom(
            terms.county_fips, int(terms.bedrooms), zip_code=subject_zip
        )
    except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError) as exc:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FMR_UNAVAILABLE_FOR_COUNTY,
                f"County {terms.county_fips} resolved, but its HUD Fair Market Rent "
                f"schedule could not be retrieved ({type(exc).__name__}). No rent "
                f"estimate was produced. This is a lookup failure rather than a "
                f"property that cannot be priced — a re-run may succeed.",
                Severity.CRITICAL,
            )
        )
        return {"valuation_detail": detail, "flags": flags}

    subject_fmr = float(anchor["rent"])
    detail.fmr_year = anchor["year"]
    # **An anchor is ZIP-resolution only if HUD published a Small Area schedule for this
    # county *and* a ZIP in it matched.** Both halves are needed, and reading only the
    # second was a defect (fixed U8.2b, found by U8.2's case work).
    #
    # `used_msa_fallback` answers two different questions depending on what HUD returned,
    # and `tools/hud_fmr.get_fmr` is where the two shapes are normalized. For a county
    # *with* Small Area FMRs it means "a ZIP was asked for and none matched, so the
    # MSA-level row was used" — a genuine fallback. For a county with **no** Small Area
    # schedule at all, HUD returns a single flat record, there is no fallback to record,
    # and the field is `False`.
    #
    # Reading it alone therefore inverted the disclosure in exactly the counties that
    # most need it. **Measured Aug 28, 2026: all five New York counties** — New York,
    # Kings, Queens, Bronx and Richmond — return the flat shape, so every New York
    # subject recorded `fmr_resolution = "zip"` against a county-wide figure with
    # `fmr_zip` unset. `agents/summarizer.py` then printed a bare "(ZIP)" beside the
    # anchor, claiming sub-county precision the estimate does not have, and the
    # county-level disclosure below was suppressed — worth 0.15 of confidence on every
    # New York deal, including the `staten-island` demo. §2 designates New York as the
    # market grounded in real thinness; this made it the one market that did not say so.
    #
    # `is_safmr` is the half that was missing: it reports which response shape HUD sent,
    # which is precisely "does this county have ZIP-level schedules at all".
    zip_anchored = anchor["is_safmr"] and not anchor["used_msa_fallback"]
    detail.fmr_resolution = "zip" if zip_anchored else "county"
    detail.fmr_zip = subject_zip if zip_anchored else None

    if not zip_anchored:
        # **The consequence is identical; the cause is not, and the message says which
        # (U8.2b).** One flag kind rather than two, on the rule this file already applies
        # elsewhere: a reader's response to both is the same — treat the figure as
        # describing the county, not the address. But the sentence naming the cause has
        # to be true of the deal in front of them, and a single fixed sentence was not.
        # It asserted that HUD publishes no ZIP-level schedule, which is right for a New
        # York subject and wrong for a Los Angeles one: Los Angeles County has 474 ZIP
        # schedules for FY2026 and is county-anchored anyway, because the model's
        # training rows there were county-anchored and mixing the two would multiply a
        # county-relative ratio by a ZIP-level figure.
        cause = (
            "HUD publishes no ZIP-level rent schedule for this county, so the "
            "county-wide figure is the only one available"
            if not anchor["is_safmr"]
            else "the rent model's own training data for this county was measured "
                 "against county-wide rents, so a ZIP-level figure could not be "
                 "combined with it without mixing two different baselines"
        )
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FMR_ANCHOR_COUNTY_LEVEL,
                f"This estimate is anchored to the county-wide Fair Market Rent for "
                f"{terms.county_fips}, because {cause}. Where ZIP-level schedules are "
                f"used, they span roughly 2x within a single county, so a county anchor "
                f"cannot distinguish an expensive neighborhood from a cheap one — the "
                f"estimate describes the county's rent level, not this address's.",
                Severity.WARN,
            )
        )

    if anchor["bedroom_cap_exceeded"]:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.FMR_BEDROOM_CAP_EXCEEDED,
                f"The subject has {terms.bedrooms} bedrooms; HUD publishes no Fair "
                f"Market Rent beyond four, so this estimate is anchored to the "
                f"{anchor['bedrooms_used']}-bedroom figure. Larger units rent above "
                f"their four-bedroom anchor, so the estimate is likely conservative.",
                Severity.INFO,
            )
        )

    ratio = rent_model.predict_ratio(
        bundle, terms.bedrooms, terms.bathrooms, terms.square_footage
    )

    # `predict_ratio` deliberately returns the raw model output so an implausible
    # prediction stays visible instead of being clipped into looking reasonable. This is
    # where that decision is paid off: the same bounds the training set applied to drop
    # data defects are applied to the model's own output, and a ratio outside them means
    # the features fell outside anything the model saw. Refusing beats reporting it.
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

    estimate = ratio * subject_fmr

    # --- Drift correction (U8.4b, from U8.0's finding) -------------------------
    # The model learned its ratio against the vintage FMR schedule and multiplies it by
    # today's, but the schedule outran the market by ~18.5 points over that interval, so
    # the raw product reads high by the subject ZIP's own drift. The ZIP for the market
    # read is resolved independently of the anchor's grain: ZORI is ZIP-level even where
    # the FMR anchor is county-level, and the market the subject rents in is its ZIP
    # either way.
    zori_zip = terms.zip_code or (
        zcta_crosswalk.lookup_zcta(terms.latitude, terms.longitude)
        if terms.latitude is not None and terms.longitude is not None
        else None
    )
    drift = rent_drift.compute_drift(
        zori_zip, terms.county_fips, int(terms.bedrooms), subject_zip, client=client
    )
    if drift.applied:
        estimate *= drift.factor
        detail.rent_drift_factor = drift.factor
        detail.rent_drift_market_growth_pct = drift.market_growth_pct
        detail.rent_drift_schedule_growth_pct = drift.schedule_growth_pct
        detail.rent_drift_zori_vintage_month = drift.zori_vintage_month_used
        detail.rent_drift_zori_latest_month = drift.zori_latest_month
        direction = "down" if drift.factor < 1.0 else "up"
        stale = (
            drift.zori_staleness_months is not None
            and drift.zori_staleness_months > config.RENT_DRIFT_MAX_ZORI_STALENESS_MONTHS
        )
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_DRIFT_CORRECTION_APPLIED,
                f"The rent estimate was adjusted {direction} by a factor of "
                f"{drift.factor:.2f} to correct for measured drift between market rents "
                f"and the federal rent schedule it is anchored to. Since the training "
                f"data's 2018-19 vintage, the schedule for this area rose "
                f"{drift.schedule_growth_pct:+.0f}% while observed market rents in ZIP "
                f"{drift.zip_code} (Zillow's rent index) rose "
                f"{drift.market_growth_pct:+.0f}%; an unadjusted figure would carry that "
                f"gap. The comparable-implied rents shown alongside are adjusted "
                f"identically, since they are built the same way and carry the same "
                f"drift."
                + (
                    f" Note the market index's last observation "
                    f"({drift.zori_latest_month}) is {drift.zori_staleness_months} "
                    f"months old — the correction is only as current as that series."
                    if stale
                    else ""
                ),
                Severity.INFO,
            )
        )
    else:
        flags.append(
            state.flag(
                AGENT,
                FlagKind.RENT_DRIFT_CORRECTION_UNAVAILABLE,
                f"A drift correction normally applied to every rent estimate could not "
                f"be computed for this property, because {drift.unavailable_reason}. "
                f"The federal rent schedule this estimate is anchored to has risen "
                f"measurably faster than market rents since the model's 2018-19 "
                f"training data — where the correction could be computed in this "
                f"project's markets, it reduced estimates by between roughly 7% and "
                f"26% — so this estimate, and the comparable-implied rents beside it, "
                f"likely read high by that kind of margin.",
                Severity.WARN,
            )
        )

    flags.extend(_cross_check(detail, state, estimate, subject_fmr, drift.factor or 1.0))

    # Raised on every estimate that took this path, without exception. INFO rather than
    # WARN because it describes a mechanism working as designed, not a degradation —
    # the severity guidance in the report says exactly that. It is here so that no
    # reader can mistake a modelled ratio times a government reference figure for an
    # observed market rent.
    #
    # The closing sentence branches on the drift correction (U8.4b). Its previous fixed
    # form claimed the stability assumption was "one nothing in this project verifies" —
    # true when written, false since U8.0 measured the assumption and found it does not
    # hold. A disclosure that misstates what the project has checked is the same defect
    # class U8.2b fixed, one layer up.
    flags.append(
        state.flag(
            AGENT,
            FlagKind.RENT_ANCHORED_TO_FMR,
            f"Estimated rent of ${estimate:,.0f}/mo is a modelled rent-to-FMR ratio of "
            f"{ratio:.2f} applied to the FY{detail.fmr_year} HUD Fair Market Rent of "
            f"${subject_fmr:,.0f} for "
            + (f"ZIP {detail.fmr_zip}" if detail.fmr_resolution == "zip"
               else f"county {terms.county_fips}")
            + (
                f", then adjusted by a factor of {drift.factor:.2f} for measured "
                f"market-versus-schedule drift (see the drift disclosure)"
                if drift.applied
                else ""
            )
            + f". It is not an observed "
            f"market rent. The ratio comes from a regression trained on 2018-19 listings "
            f"normalized the same way, which assumes rent-to-FMR structure is stable "
            f"over that interval — an assumption this project has measured and found "
            + (
                f"to have drifted, which is what the adjustment above corrects for."
                if drift.applied
                else f"to have drifted; the correction for it could not be applied to "
                     f"this property, so see the drift disclosure for the likely "
                     f"direction and size of the error."
            ),
            Severity.INFO,
        )
    )

    return {
        "rent_estimate": estimate,
        "rent_estimate_ratio_to_fmr": ratio,
        "fmr_anchor_used": subject_fmr,
        "rent_estimate_source": RentEstimateSource.REGRESSION_MODEL,
        "valuation_detail": detail,
        "flags": flags,
    }
