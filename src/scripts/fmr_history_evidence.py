"""Evidence for U6 — what HUD's published FMR history can and cannot support.

Built **before** the Scenario/Forecast agent, deliberately. §1 specified a rent forecast
driven by Redfin's price series and that premise was measured and disproved (decision
#16); the replacement series deserved the same treatment before code depended on it.
Three of this script's findings changed the design rather than confirming it, and the
config constants they set (`FMR_COHORT_SHIFT_EXCESS_PP`, `FMR_LOCAL_DEVIATION_PP`,
`FMR_IQR_*_PERCENTILE`) are reproduced here rather than asserted in a comment.

**What this check could have returned had the design been right as written** — the §8
standard, and the reason this script exists in this form:

  * Section 1 could have shown the five bedroom fields moving together within 0.2pp, in
    which case a fixed Two-Bedroom series would have been the simpler correct choice.
  * Section 3 could have shown the FY2020-22 calendar window lining up with the FMR
    surge, in which case `config.ANOMALOUS_PERIOD` would have covered both series and no
    second screen would have been needed.
  * Section 4 could have shown FY2024 confined to Chicago, which would have made
    "methodology jump" a defensible label for it.
  * Section 5 could have shown a natural threshold absent — a smooth gradient of cohort
    excesses with no gap — in which case the screen would have rested on a chosen number
    and should have been reported as such.

None of those came back that way, which is what makes the four findings load-bearing
rather than decorative. Section 6 is where the script rejected two of its own candidate
constructions on their output: a percentile band around an arithmetic mean, which put
Chicago's base case outside its own band in both treatments, and a sustained window,
the closest analogue to the price side. Section 9 tests whether the surviving choice
holds up as the series lengthens.

Two caveats stated up front, because the panel looks more authoritative than it is:

  1. The cohort is the ten HUD areas behind this project's training metros — not a
     national sample, and skewed large and coastal/midwest. The FY2023-24 shift appears
     in all ten independently, which is what makes the direction trustworthy; the
     baseline level is a property of this panel.
  2. Cook County crosses a SAFMR regime boundary at FY2018, and that is the weakest
     observation in Chicago's series. Philadelphia and Pittsburgh adopted Small Area FMRs
     the same year without a comparable dip, so no systematic regime effect is visible —
     but "not visible in three cases" is not "absent," and Chicago's FY2018 -4.2% should
     be read with that in mind.

Run:  .venv/bin/python scripts/fmr_history_evidence.py
      .venv/bin/python scripts/fmr_history_evidence.py --build-panel
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from tools import fmr_history, hud_fmr

# The HUD FMR areas behind this project's eight training metros (§7 decision #4 (training metro shortlist)), as
# resolved from listing coordinates by `tools/county_crosswalk.py` during U5. Listed
# explicitly rather than re-derived from the corpus so the panel is reproducible on a
# fresh clone without loading 100MB of Kaggle rows.
#
# **Sixteen counties, ten distinct areas.** HUD prices by FMR *area*, not by county:
# five New York counties share one schedule, and Cincinnati and Philadelphia contribute
# two counties each. Deduplicating matters — a cohort median over the raw sixteen would
# weight New York five times and drag the baseline toward one market.
PANEL_COUNTIES = {
    "0603799999": "Los Angeles, CA",
    "1703199999": "Cook, IL (Chicago)",
    "2502507000": "Boston, MA (town regime)",
    "3401399999": "Essex, NJ (Newark)",
    "3401799999": "Hudson, NJ (Jersey City)",
    "3600599999": "Bronx, NY",
    "3604799999": "Kings, NY",
    "3606199999": "New York, NY",
    "3608199999": "Queens, NY",
    "3608599999": "Richmond, NY (Staten Island)",
    "3902599999": "Hamilton, OH (Cincinnati)",
    "3903599999": "Cuyahoga, OH (Cleveland)",
    "3906199999": "Hamilton/Clermont, OH",
    "4200399999": "Allegheny, PA (Pittsburgh)",
    "4209199999": "Montgomery, PA",
    "4210199999": "Philadelphia, PA",
}

# The three metros the pipeline actually prices (`config.INFERENCE_METROS`).
TRIO = {
    "0603799999": "Los Angeles",
    "1703199999": "Chicago",
    "3903599999": "Cleveland",
}

BEDROOM_FIELDS = ["Efficiency", "One-Bedroom", "Two-Bedroom", "Three-Bedroom", "Four-Bedroom"]
REPORT_FIELD = "Two-Bedroom"


def build_panel(path: Path) -> fmr_history.CohortPanel:
    """Pull every panel county-year from HUD and write the committed artifact.

    Roughly 160 calls on a cold cache at HUD's 1/second rate limit, then free forever:
    `tools/hud_fmr.py` caches to disk. This is why the panel is committed rather than
    derived at runtime inside a per-deal node.
    """
    client = hud_fmr.HudFmrClient()
    latest = int(client.get_fmr(next(iter(PANEL_COUNTIES))).year)
    years = range(config.FMR_HISTORY_FIRST_YEAR, latest + 1)

    # Pull per *entityid*, never per area name. **HUD renames FMR areas between fiscal
    # years** — Cuyahoga is served as "Cleveland-Elyria, OH MSA" through FY2025 and
    # "Cleveland, OH HUD Metro FMR Area" from FY2026 — so keying the panel on the name
    # each year returns splits one county's history into two partial series, which then
    # drops a real year-over-year observation out of the cohort. Caught by section 7 of
    # this script printing eleven areas where the panel holds ten counties' worth.
    #
    # Whether that rename is cosmetic or an area *redefinition* is not determinable from
    # the API. Cleveland's FY2026 change is +5.9%, unremarkable against its own history,
    # so no discontinuity is visible — but that is the same "not visible in one case"
    # standard as the SAFMR caveat above, and is recorded as such rather than dismissed.
    per_entity: dict[str, dict[str, dict[int, float]]] = {}
    canonical: dict[str, str] = {}
    print(f"Building panel: {len(PANEL_COUNTIES)} counties x FY{years.start}-{latest}")
    for entityid, label in PANEL_COUNTIES.items():
        for year in years:
            try:
                result = client.get_fmr(entityid, year=year)
            except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError) as exc:
                print(f"  {label} FY{year}: {type(exc).__name__}")
                continue
            # Latest year wins, so the panel speaks HUD's current vocabulary.
            canonical[entityid] = result.area_name
            for bedroom_field in BEDROOM_FIELDS:
                rent = result.rents.get(bedroom_field)
                if rent is not None:
                    per_entity.setdefault(entityid, {}).setdefault(bedroom_field, {})[year] = float(rent)

    # Collapse entityids that share one schedule: five New York counties, and two each
    # for Cincinnati and Philadelphia. A cohort median over the raw sixteen would weight
    # New York five times.
    rents: dict[str, dict[str, dict[int, float]]] = {}
    entityids: dict[str, str] = {}
    for entityid, by_field in per_entity.items():
        area = canonical[entityid]
        if area in rents:
            continue
        rents[area] = by_field
        entityids[area] = entityid
    dropped = len(per_entity) - len(rents)
    print(f"  {len(per_entity)} counties -> {len(rents)} distinct HUD areas ({dropped} shared a schedule)")

    payload = {
        "built_at": datetime.now().isoformat(timespec="seconds"),
        "source": "HUD USER Fair Market Rents API (public record), via tools/hud_fmr.py",
        "note": (
            "Cohort baseline for the U6 rent-growth screen. Ten distinct HUD FMR areas "
            "behind this project's training metros; not a national sample. Rebuild with "
            "scripts/fmr_history_evidence.py --build-panel."
        ),
        "first_year": config.FMR_HISTORY_FIRST_YEAR,
        "last_year": latest,
        "entityids": entityids,
        "rents": rents,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True))
    print(f"\nWrote {path} — {len(rents)} distinct HUD areas, {path.stat().st_size:,} bytes")
    return fmr_history.load_cohort_panel(path)


def section_1_bedroom_spread(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 1. Is the growth rate bedroom-specific, or can one field stand in? ===")
    spreads = []
    for area in panel.area_names:
        per_field = {f: panel.yoy(area, f) for f in BEDROOM_FIELDS}
        years = set.intersection(*(set(v) for v in per_field.values())) if per_field else set()
        for year in years:
            values = [per_field[f][year] for f in BEDROOM_FIELDS]
            spreads.append(max(values) - min(values))
    spreads.sort()
    levels = sorted(abs(v) for a in panel.area_names for v in panel.yoy(a, REPORT_FIELD).values())
    print(f"  spread across the 5 bedroom fields within one area-year (n={len(spreads)}):")
    print(f"    median {statistics.median(spreads):.2f}pp | p90 {spreads[int(.9*len(spreads))]:.2f}pp | max {spreads[-1]:.2f}pp")
    print(f"  for scale, the median |YoY| level itself is {statistics.median(levels):.2f}pp")
    print("  -> too large to treat as noise. tools/fmr_history uses the subject's own bedroom count.")


def section_2_cohort(panel: fmr_history.CohortPanel) -> None:
    print(f"\n=== 2. The year cohort ({panel.n_areas} distinct HUD areas, {REPORT_FIELD}) ===")
    cohort = panel.cohort_medians(REPORT_FIELD)
    baseline = panel.baseline_pct(REPORT_FIELD)
    for year, median in cohort.items():
        values = sorted(
            v for a in panel.area_names if (v := panel.yoy(a, REPORT_FIELD).get(year)) is not None
        )
        print(f"  FY{year}  n={len(values):2d}  cohort median {median:6.2f}%   range [{values[0]:6.1f}, {values[-1]:6.1f}]")
    print(f"\n  baseline (median of the yearly cohort medians): {baseline:.2f}%")


def section_3_window_mismatch(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 3. Does config.ANOMALOUS_PERIOD (calendar 2020-2022) fit the rent series? ===")
    cohort = panel.cohort_medians(REPORT_FIELD)
    baseline = panel.baseline_pct(REPORT_FIELD)
    for year, median in cohort.items():
        in_price_window = year in (2020, 2021, 2022)
        excess = median - baseline
        tag = ""
        if in_price_window:
            tag = "  <- inside the PRICE anomaly window"
        if excess >= config.FMR_COHORT_SHIFT_EXCESS_PP:
            tag += "  <- RENT cohort shift"
        print(f"  FY{year}  {median:6.2f}%  ({excess:+5.2f}pp vs baseline){tag}")
    print("\n  The two sets do not overlap. FMR is administrative and lags: the FY2024")
    print("  schedules were published Sept 2023 on 2021-22 data. Applying the price")
    print("  window here would drop three ordinary years and keep both distorted ones.")


def section_4_attribution(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 4. Is FY2024 a Chicago event? (the 'methodology jump' claim) ===")
    cohort = panel.cohort_medians(REPORT_FIELD)
    shift_years = panel.cohort_shift_years(REPORT_FIELD)
    if not shift_years:
        print("  no cohort shift detected; nothing to decompose")
        return
    for year in shift_years:
        values = [(a, v) for a in panel.area_names if (v := panel.yoy(a, REPORT_FIELD).get(year)) is not None]
        print(f"\n  FY{year}: cohort median {cohort[year]:.2f}%, all {len(values)} areas moved "
              f"(min {min(v for _, v in values):.1f}%)")
        for area, value in sorted(values, key=lambda kv: -kv[1])[:4]:
            print(f"    {area[:44]:46s} {value:6.2f}%  = cohort {cohort[year]:5.2f} {value-cohort[year]:+6.2f} local"
                  f"   ({cohort[year]/value*100:3.0f}% shared)")
    print("\n  A cohort-wide move is equally consistent with a HUD methodology change and")
    print("  with the 2021-22 market surge reaching an administrative series two years")
    print("  late. FMR alone cannot separate them, so the screen measures co-movement and")
    print("  the report claims nothing about cause. Zillow ZORI is what could attribute it.")


def section_5_threshold(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 5. Is the cohort-shift threshold natural or chosen? ===")
    cohort = panel.cohort_medians(REPORT_FIELD)
    baseline = panel.baseline_pct(REPORT_FIELD)
    ranked = sorted((m - baseline, y) for y, m in cohort.items())
    for excess, year in ranked:
        print(f"    FY{year}  {excess:+6.2f}pp")
    shifted = [e for e, _ in ranked if e >= config.FMR_COHORT_SHIFT_EXCESS_PP]
    ordinary = [e for e, _ in ranked if e < config.FMR_COHORT_SHIFT_EXCESS_PP]
    if shifted and ordinary:
        gap = min(shifted) - max(ordinary)
        print(f"\n  gap between the largest ordinary year ({max(ordinary):+.2f}pp) and the")
        print(f"  smallest shifted one ({min(shifted):+.2f}pp): {gap:.2f}pp.")
        print(f"  Any threshold in ({max(ordinary):.2f}, {min(shifted):.2f}) selects the same years;")
        print(f"  config.FMR_COHORT_SHIFT_EXCESS_PP = {config.FMR_COHORT_SHIFT_EXCESS_PP} sits inside that band.")


def section_6_band_construction(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 6. Band construction on 9 annual points (Redfin has 88 monthly) ===")
    client = hud_fmr.HudFmrClient()
    shift_years = panel.cohort_shift_years(REPORT_FIELD)
    print(f"  cohort shift years excluded in the right-hand case: {list(shift_years)}\n")
    for entityid, label in TRIO.items():
        series = fmr_history.get_rent_growth_series(entityid, bedrooms=2, client=client)
        kept = {y: v for y, v in series.yoy_by_year.items() if y not in shift_years}
        values = sorted(kept.values())
        runs = _sustained_runs(kept, 3)
        geo = fmr_history._geometric_mean_pct(values)
        ordered = lambda lo, mid, hi: "ordered" if lo <= mid <= hi else "** BASE OUTSIDE ITS OWN BAND **"
        print(f"  {label}  (n={len(values)} after screening)")
        print(f"    min / geo-mean / max   {values[0]:6.2f} /{geo:6.2f} /{values[-1]:6.2f}   <- adopted, {ordered(values[0], geo, values[-1])}")
        print(f"    p25 / arith-mean / p75 {fmr_history._percentile(values,25):6.2f} /{statistics.mean(values):6.2f} /{fmr_history._percentile(values,75):6.2f}   "
              f"{ordered(fmr_history._percentile(values,25), statistics.mean(values), fmr_history._percentile(values,75))}")
        print(f"    p25 / median / p75     {fmr_history._percentile(values,25):6.2f} /{statistics.median(values):6.2f} /{fmr_history._percentile(values,75):6.2f}   "
              f"{ordered(fmr_history._percentile(values,25), statistics.median(values), fmr_history._percentile(values,75))}")
        if runs:
            covered = "" if max(kept) in runs else f"; FY{max(kept)} in no qualifying run"
            print(f"    sustained-3yr          {min(runs.values()):6.2f} /{geo:6.2f} /{max(runs.values()):6.2f}   "
                  f"({len(runs)} of {len(values)} years usable{covered})")
        else:
            print("    sustained-3yr          UNAVAILABLE - no three consecutive kept years")
    print("\n  Two rejections, both on this output rather than on preference:")
    print("    * p25/arithmetic-mean/p75 does not order. Mixing a mean with percentiles")
    print("      puts Chicago's base case outside its own band in BOTH treatments -")
    print("      above the optimistic figure unscreened, below the pessimistic screened.")
    print("    * Sustained windows are the closest analogue to the price-side method, but")
    print("      screening FY2023-24 breaks the run of consecutive years, so the two most")
    print("      recent observations fall out of every qualifying window.")
    print("  The geometric mean is used rather than the arithmetic one because the")
    print("  projection compounds; see section 9 for what that is worth.")


def _sustained_runs(series: dict[int, float], width: int) -> dict[int, float]:
    """Rolling mean over *consecutive* fiscal years only.

    Mirrors `redfin_data._sustained_means`, which segments on month adjacency for the
    same reason: a plain rolling mean would splice FY2022 onto FY2025 and report the
    result as a three-year stretch the market never had.
    """
    years = sorted(series)
    out: dict[int, float] = {}
    for i in range(len(years) - width + 1):
        run = years[i : i + width]
        if run[-1] - run[0] == width - 1:
            out[run[-1]] = statistics.mean(series[y] for y in run)
    return out


def section_7_resolution(panel: fmr_history.CohortPanel) -> None:
    print("\n=== 7. Could the growth rate be differenced at ZIP resolution? ===")
    client = hud_fmr.HudFmrClient()
    for area, entityid in sorted(panel.entityids.items()):
        depth = []
        for year in range(panel.first_year, panel.last_year + 1):
            try:
                if client.get_fmr(entityid, year=year).is_safmr:
                    depth.append(year)
            except (hud_fmr.HudFmrApiError, KeyError, StopIteration, RuntimeError):
                continue
        span = f"FY{min(depth)}-{max(depth)}" if depth else "none"
        print(f"  {area[:44]:46s} {len(depth):2d} yrs of ZIP schedules  ({span})")
    print("\n  Two years is one YoY observation. The growth rate is county-level for every")
    print("  metro; the Valuation agent's ZIP anchor pairs with it, and the report says so.")


def section_8_what_the_fork_costs(panel: fmr_history.CohortPanel) -> None:
    print(f"\n=== 8. What the fork is worth at the {config.FORECAST_HORIZON_YEARS}-year horizon ===")
    client = hud_fmr.HudFmrClient()
    for entityid, label in TRIO.items():
        series = fmr_history.get_rent_growth_series(entityid, bedrooms=2, client=client)
        both = {}
        for exclude in (False, True):
            bands = fmr_history.compute_rent_growth_bands(series, panel, exclude_cohort_shift_years=exclude)
            both[exclude] = bands
        if not (both[False].available and both[True].available):
            print(f"  {label}: bands unavailable")
            continue
        a, b = both[False], both[True]
        ma = a.projected_multiple(a.base_yoy_pct, config.FORECAST_HORIZON_YEARS)
        mb = b.projected_multiple(b.base_yoy_pct, config.FORECAST_HORIZON_YEARS)
        print(f"  {label:12s} base {a.base_yoy_pct:5.2f}%/yr (all years, n={a.n_yoy_observations}) -> {(ma-1)*100:5.1f}% cumulative")
        print(f"  {'':12s} base {b.base_yoy_pct:5.2f}%/yr (screened, n={b.n_yoy_observations}) -> {(mb-1)*100:5.1f}% cumulative")
        print(f"  {'':12s} on a $2,000 rent: ${2000*ma:,.0f} vs ${2000*mb:,.0f} in year {config.FORECAST_HORIZON_YEARS}\n")
    print("  Neither column is wrong, which is the point: FY2023-24 were increases a")
    print("  landlord could actually charge against, and they were also a national")
    print("  step-change unlikely to repeat annually. A linear chain picks one silently.")


def section_9_estimator_durability(panel: fmr_history.CohortPanel) -> None:
    """Does the adopted construction hold up as the series lengthens?

    Asked because min and max are *extreme order statistics*: they can only move
    outward as observations accumulate, never inward, unlike percentiles or a mean.
    That is a structural property, so the question is not whether it is true but
    whether it bites at this sample size and growth rate (one observation per October).
    """
    print("\n=== 9. Estimator durability ===")
    client = hud_fmr.HudFmrClient()
    shift_years = panel.cohort_shift_years(REPORT_FIELD)

    print("\n  (a) Arithmetic vs geometric mean - does the base case overstate compounding?")
    for entityid, label in TRIO.items():
        series = fmr_history.get_rent_growth_series(entityid, bedrooms=2, client=client)
        values = sorted(series.yoy_by_year.values())
        arithmetic = statistics.mean(values)
        geometric = fmr_history._geometric_mean_pct(values)
        horizon = config.FORECAST_HORIZON_YEARS
        print(f"    {label:13s} arithmetic {arithmetic:5.2f}%  geometric {geometric:5.2f}%  "
              f"(+{arithmetic-geometric:.2f}pp/yr)  -> {((1+arithmetic/100)**horizon-1)*100:5.1f}% vs "
              f"{((1+geometric/100)**horizon-1)*100:5.1f}% over {horizon}yr")

    print("\n  (b) Drift: what each statistic would have reported at n=5, 6, 7")
    print("      (oldest-first windows of the screened series; total movement across the sequence)")
    print(f"      {'metro':13s} {'min':>8s} {'p25':>8s} {'geo':>8s} {'p75':>8s} {'max':>8s}")
    for entityid, label in TRIO.items():
        series = fmr_history.get_rent_growth_series(entityid, bedrooms=2, client=client)
        years = sorted(y for y in series.yoy_by_year if y not in shift_years)
        windows = [
            sorted(series.yoy_by_year[y] for y in years[:k])
            for k in range(5, len(years) + 1)
        ]
        if len(windows) < 2:
            print(f"      {label:13s} too few observations to test drift")
            continue

        def movement(fn) -> float:
            seen = [fn(w) for w in windows]
            return max(seen) - min(seen)

        print(f"      {label:13s} "
              f"{movement(lambda w: w[0]):8.2f} "
              f"{movement(lambda w: fmr_history._percentile(w, 25)):8.2f} "
              f"{movement(fmr_history._geometric_mean_pct):8.2f} "
              f"{movement(lambda w: fmr_history._percentile(w, 75)):8.2f} "
              f"{movement(lambda w: w[-1]):8.2f}")
    print("\n      The minimum has not moved at all in any metro, and the maximum moved less")
    print("      than p75 did in Cleveland. The outward-drift property of extremes is real")
    print("      but not yet observable at this sample size, and the series grows by one")
    print("      observation per year. The IQR is carried in RentGrowthBands so the")
    print("      comparison stays available if that changes.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-panel", action="store_true",
                        help="re-pull every panel county-year from HUD and rewrite the committed artifact")
    args = parser.parse_args()

    if args.build_panel:
        panel = build_panel(config.FMR_COHORT_PANEL_PATH)
    else:
        panel = fmr_history.load_cohort_panel()
        if panel is None:
            print(f"No panel at {config.FMR_COHORT_PANEL_PATH}. Run with --build-panel first.")
            return

    print(f"\nPanel built {panel.built_at} — {panel.n_areas} distinct HUD FMR areas, "
          f"FY{panel.first_year}-{panel.last_year}")

    section_1_bedroom_spread(panel)
    section_2_cohort(panel)
    section_3_window_mismatch(panel)
    section_4_attribution(panel)
    section_5_threshold(panel)
    section_6_band_construction(panel)
    section_7_resolution(panel)
    section_8_what_the_fork_costs(panel)
    section_9_estimator_durability(panel)


if __name__ == "__main__":
    main()
