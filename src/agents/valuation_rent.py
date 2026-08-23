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

- **The LLM fallback path** (`FlagKind.LLM_RENT_FALLBACK_USED`) — §6's cut list item 3,
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
from tools import hud_fmr, kaggle_data, redfin_data, zcta_crosswalk
from tools.model import rent_model

AGENT = "valuation_rent"

# TODO(cut-list): the LLM fallback estimator (§6 cut list, item 3) is descoped, not
# designed away. It would sit here, after the ratio path has failed to anchor: prompt a
# model for a rent figure with the comp set as context, write it with
# `RentEstimateSource.LLM_FALLBACK`, and raise `FlagKind.LLM_RENT_FALLBACK_USED`. What
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


def _attach_benchmark(detail: ValuationDetail, terms: DealTerms) -> None:
    """Resolve the subject to a Redfin metro and record the benchmark, or why not.

    Runs regardless of whether a rent estimate turns out to be possible, because the two
    fail for unrelated reasons: a subject with no county has no FMR anchor but is still
    in a metro Redfin covers, and a reader comparing the asking price to the market
    should not lose that because the rent path stopped earlier.

    Matched with `kaggle_data.city_matches` rather than an equality test, so the metro
    a subject belongs to is decided by the same word-boundary rule that decides corpus
    membership — the rule that folds "Cleveland Heights" into Cleveland while keeping
    "Queensbury" out of Queens. Two different notions of "is this city in that metro"
    is one of the ways a system quietly starts disagreeing with itself.
    """
    if not terms.city:
        detail.benchmark_unavailable_reason = (
            "The listing resolved to no city, so no metro sale-price series applies."
        )
        return

    metro = next(
        (m for m in redfin_data.TARGET_METROS if kaggle_data.city_matches(terms.city, [m])),
        None,
    )
    if metro is None:
        detail.benchmark_unavailable_reason = (
            f"Redfin's Multi-Family (2-4 unit) extract does not cover {terms.city}. "
            f"It reaches {', '.join(sorted(redfin_data.TARGET_METROS))} only."
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


def _cross_check(
    detail: ValuationDetail, state: DealState, estimate: float, subject_fmr: float
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
    """
    anchoring = rent_model.anchor_comp_rents(state.comps, subject_fmr)
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
        flag(
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
            flag(
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
            flag(
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
            flag(
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
            flag(
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
    # `used_msa_fallback` is True when HUD had no Small Area FMR for this ZIP and the
    # county-wide figure was used instead.
    detail.fmr_resolution = "county" if anchor["used_msa_fallback"] else "zip"
    detail.fmr_zip = None if anchor["used_msa_fallback"] else subject_zip

    if detail.fmr_resolution == "county":
        flags.append(
            flag(
                AGENT,
                FlagKind.FMR_ANCHOR_COUNTY_LEVEL,
                f"This estimate is anchored to the county-wide Fair Market Rent for "
                f"{terms.county_fips}, because HUD publishes no Small Area (ZIP-level) "
                f"FMR there. Within counties that do have them, ZIP schedules span "
                f"roughly 2x, so a county anchor cannot distinguish an expensive "
                f"neighborhood from a cheap one — the estimate describes the county's "
                f"rent level, not this address's.",
                Severity.WARN,
            )
        )

    if anchor["bedroom_cap_exceeded"]:
        flags.append(
            flag(
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
            flag(
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

    flags.extend(_cross_check(detail, state, estimate, subject_fmr))

    # Raised on every estimate that took this path, without exception. INFO rather than
    # WARN because it describes a mechanism working as designed, not a degradation —
    # the severity guidance in the report says exactly that. It is here so that no
    # reader can mistake a modelled ratio times a government reference figure for an
    # observed market rent.
    flags.append(
        flag(
            AGENT,
            FlagKind.RENT_ANCHORED_TO_FMR,
            f"Estimated rent of ${estimate:,.0f}/mo is a modelled rent-to-FMR ratio of "
            f"{ratio:.2f} applied to the FY{detail.fmr_year} HUD Fair Market Rent of "
            f"${subject_fmr:,.0f} for "
            + (f"ZIP {detail.fmr_zip}" if detail.fmr_resolution == "zip"
               else f"county {terms.county_fips}")
            + f". It is not an observed "
            f"market rent. The ratio comes from a regression trained on 2018-19 listings "
            f"normalized the same way, which assumes rent-to-FMR structure is stable "
            f"over that interval — the largest single source of error in this figure, "
            f"and one nothing in this project verifies.",
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
