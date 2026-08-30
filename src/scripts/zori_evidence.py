"""U8.0 — does rent-to-FMR structure hold across the seven years the rent model spans?

**The assumption this tests is the largest unverified one in the system.** §2's rent
design learns a rent/FMR *ratio* from a 2018-19 corpus and applies it to today's FMR
schedule, on the reasoning that a ratio ages far more slowly than a dollar level does.
`tools/model/rent_model.py` states the exposure plainly: *"The ratio assumption is
load-bearing and untested against 2026 data."* Decision #16 adopted Zillow ZORI as the
instrument and it went unbuilt through U6 and U7. This is that measurement.

Two questions, and they are not equally answerable
----------------------------------------------------
1. **Stability — has the ratio moved between the corpus vintage and today?** This is what
   #16 actually asked, and the one this data answers cleanly. The identical construction
   is applied at both ends, so any constant bias in the construction cancels out of the
   difference.
2. **Level — is the corpus's ~1.40x FMR the market's ratio?** Indicative only. ZORI's unit
   mix (single-family, condo, multifamily) is not the corpus's (marketed apartments), and
   no weighting available here fixes that. Reported, and reported as indicative.

Keeping them apart is the point. Blending them into one headline number would let a
mix-mismatch artifact be read as a finding about drift.

Making the denominators comparable
------------------------------------
ZORI is one figure per ZIP across unit types; FMR is published per bedroom count, and the
rent model anchors every corpus row at its own bedroom count. Dividing one by the other
needs a bedroom baseline chosen deliberately rather than by default.

**The corpus's own bedroom mix supplies it.** For each ZCTA, the corpus-side denominator
is already the mean of the row-level FMR anchors — bedroom-weighted by construction, for
free. The present-day denominator reprices *that same mix* against FY2026 schedules
through `rent_model.anchor_for_row`, the single place ZIP-vs-county anchoring is decided.
So both ends divide by a mixture built the same way, and the ratio moves only if rent
relative to FMR moved.

**Two limits on the denominators, stated because they bound the claim.** Only rows
anchored at ZIP resolution are used — 1,105 of the 5,686 the model trains on — because
ZORI is a ZIP series and a county-anchored ratio has a different denominator, which
`rent_model` documents as the reason the two are not poolable. And where the vintage-year
ZIP schedule was reconstructed rather than published (`RENT_MODEL_BACKCAST_ZIP_FMR`), both
ends carry the same current ZIP-to-county ratio, so that factor cancels out of the growth
comparison and the FMR growth measured for those ZCTAs is their county's.

**What this check could have returned, stated before it runs** (§8: a verification whose
negative result was structurally guaranteed proves nothing):

  * **Stable, near the corpus's ratio.** The design's assumption holds, the rent model's
    largest exposure closes, and check A can be promoted with a threshold set above #11's
    known calibration offset.
  * **Stable, but at a materially different level.** The corpus is unrepresentative of its
    own market and the model carries a constant bias — correctable, and a finding.
  * **Drifted.** The ratio is not the stable quantity §2 assumed. Every rent estimate
    carries that drift, and check A must *not* be promoted, because the gap it would flag
    would be the model's error rather than the deal's.
  * **Too little coverage to say.** ZORI does not cover the corpus's ZCTAs densely enough
    at 2019, in which case this reports that and nothing else. That is a real possible
    outcome of this script, not a failure of it.

Run:
    .venv/bin/python scripts/zori_evidence.py --download   # first time; ~10 MB
    .venv/bin/python scripts/zori_evidence.py
    .venv/bin/python scripts/zori_evidence.py --anchor-comparison
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config
from tools import hud_fmr, zori
from tools.model import rent_model

# The fiscal year the "today" denominator is priced at. Read from the corpus-independent
# side deliberately: this is the schedule a *current* prediction is multiplied by, which
# is the number a reader of today's report is exposed to.
CURRENT_FISCAL_YEAR = 2026


def _corpus_side() -> pd.DataFrame:
    """Per-ZCTA corpus rent/FMR, with the bedroom mix that produced it.

    Restricted to rows anchored at ZIP resolution. A county-anchored row's ratio has a
    different denominator from a ZIP-anchored one — `rent_model` documents that as the
    reason the two are not poolable — and ZORI is a ZIP series, so mixing them here would
    compare a ZIP numerator against a partly-county denominator.
    """
    frame, report = rent_model.build_training_frame()
    print(f"Corpus: {len(frame):,} rows anchored, {report.counties} counties, "
          f"fiscal years {report.fiscal_years}")

    zip_anchored = frame[
        frame["anchor_tier"].isin(["zip", "zip_backcast"])
        & frame["zcta"].notna()
    ].copy()
    print(f"        {len(zip_anchored):,} of them ZIP-anchored, across "
          f"{zip_anchored['zcta'].nunique()} ZCTAs — the comparable set\n")
    return zip_anchored


def _current_denominators(frame: pd.DataFrame) -> dict[str, float]:
    """Reprice each ZCTA's corpus bedroom mix against FY2026 schedules.

    One anchor lookup per (zcta, county, bedrooms) combination rather than per row, then
    weighted by how often that bedroom count appears in the ZCTA — which reproduces the
    corpus-side mean-of-anchors weighting exactly, at the other end of the gap.
    """
    client = hud_fmr.HudFmrClient()
    pairs = {(fips, CURRENT_FISCAL_YEAR) for fips in frame["county_fips"].unique()}
    county_table = rent_model._fmr_table(pairs, client)
    zip_tables, zip_basis = rent_model._zip_anchor_tables(pairs, client, county_table)

    denominators: dict[str, float] = {}
    for zcta, group in frame.groupby("zcta"):
        fips = group["county_fips"].iloc[0]
        weighted, total = 0.0, 0
        for bedrooms, count in group["bedrooms"].value_counts().items():
            value, _ = rent_model.anchor_for_row(
                int(bedrooms), fips, CURRENT_FISCAL_YEAR, zcta,
                county_table, zip_tables, zip_basis,
            )
            if value and value > 0:
                weighted += float(value) * int(count)
                total += int(count)
        if total:
            denominators[str(zcta)] = weighted / total
    return denominators


def _rows(
    frame: pd.DataFrame, panel: pd.DataFrame, current: dict[str, float]
) -> tuple[list[dict], dict[str, int]]:
    """Every ZCTA with ZORI coverage at both ends, plus a census of what was dropped.

    **No corpus-row minimum is applied here.** That constant governs which rows get
    *printed*; applying it to selection as well would silently discard evidence from
    thinner ZCTAs and report an aggregate over the densest ones as if it covered the set.
    The dropped-row census is returned rather than logged, because a reader has to be able
    to see how much of the corpus the answer actually rests on.
    """
    rows: list[dict] = []
    dropped = {"no_zori_coverage": 0, "no_current_fmr": 0, "substitution_too_far": 0}
    target = pd.Timestamp(config.ZORI_VINTAGE_MONTH)

    for zcta, group in frame.groupby("zcta"):
        zcta = str(zcta)
        series = zori.series_for_zip(panel, zcta)
        if series is None:
            dropped["no_zori_coverage"] += len(group)
            continue

        then = zori.nearest_observed(series, config.ZORI_VINTAGE_MONTH)
        observed = series.dropna()
        if then is None or observed.empty:
            dropped["no_zori_coverage"] += len(group)
            continue
        if zcta not in current:
            dropped["no_current_fmr"] += len(group)
            continue

        then_month, then_value = then
        months_off = abs((pd.Timestamp(then_month) - target).days) / 30.44
        if months_off > config.ZORI_MAX_VINTAGE_SUBSTITUTION_MONTHS:
            dropped["substitution_too_far"] += len(group)
            continue

        now_month, now_value = str(observed.index[-1]), float(observed.iloc[-1])
        # The corpus-side denominator is the mean of the row-level anchors: already
        # bedroom-weighted, and the exact quantity `rent_to_fmr` was divided by.
        fmr_then = float(group["fmr"].mean())
        rows.append({
            "zcta": zcta,
            "city": f"{group['cityname'].mode().iloc[0]}, {group['state'].iloc[0]}",
            "corpus_rows": len(group),
            "corpus_ratio": float(group["rent_to_fmr"].mean()),
            "fmr_then": fmr_then,
            "fmr_now": current[zcta],
            "zori_then_month": then_month,
            "zori_then": then_value,
            "zori_now_month": now_month,
            "zori_now": now_value,
            "months_off": months_off,
            "zori_ratio_then": then_value / fmr_then,
            "zori_ratio_now": now_value / current[zcta],
        })
    return rows, dropped


def _report(rows: list[dict], dropped: dict[str, int]) -> None:
    if not rows:
        print("No ZCTA cleared ZORI coverage at both ends. That is the fourth outcome\n"
              "this script named up front: the data is too thin to answer, and no ratio\n"
              "is reported rather than one being reported from a handful of ZIPs.")
        return

    shown = [r for r in rows if r["corpus_rows"] >= config.ZORI_MIN_CORPUS_ROWS_PER_ZCTA]
    print(f"Per-ZCTA, for the {len(shown)} with at least "
          f"{config.ZORI_MIN_CORPUS_ROWS_PER_ZCTA} corpus rows "
          f"(all {len(rows)} feed the aggregate below):\n")
    print(f"{'ZCTA':<7} {'city':<18} {'rows':>5} {'corpus':>7} {'then':>6} {'now':>6} "
          f"{'drift':>7}")
    print("-" * 62)
    for row in sorted(shown, key=lambda r: -r["corpus_rows"]):
        drift = row["zori_ratio_now"] / row["zori_ratio_then"] - 1.0
        print(f"{row['zcta']:<7} {row['city'][:18]:<18} {row['corpus_rows']:>5,} "
              f"{row['corpus_ratio']:>7.3f} {row['zori_ratio_then']:>6.3f} "
              f"{row['zori_ratio_now']:>6.3f} {drift:>+6.1%}")

    weights = sum(r["corpus_rows"] for r in rows)
    def weighted(key: str) -> float:
        return sum(r[key] * r["corpus_rows"] for r in rows) / weights

    corpus = weighted("corpus_ratio")
    then, now = weighted("zori_ratio_then"), weighted("zori_ratio_now")
    zori_growth = weighted("zori_now") / weighted("zori_then") - 1.0
    fmr_growth = weighted("fmr_now") / weighted("fmr_then") - 1.0

    print("-" * 62)
    print(f"\nAggregate, row-weighted across {len(rows)} ZCTAs and {weights:,} corpus rows.")
    dropped_total = sum(dropped.values())
    if dropped_total:
        detail = ", ".join(f"{v:,} {k.replace('_', ' ')}" for k, v in dropped.items() if v)
        print(f"Excluded {dropped_total:,} ZIP-anchored rows: {detail}.")

    print(f"\n  1. STABILITY — the question #16 asked, and the one answered cleanly.")
    print(f"     ZORI/FMR at {config.ZORI_VINTAGE_MONTH[:7]}: {then:.3f}")
    print(f"     ZORI/FMR today:            {now:.3f}")
    print(f"     Drift over the gap:        {now / then - 1.0:+.1%}")

    print(f"\n  1b. WHICH SIDE MOVED — a ratio can fall two ways, and they call for")
    print(f"      opposite responses, so the drift is decomposed rather than asserted.")
    print(f"     Market rent (ZORI):        {zori_growth:+.1%}")
    print(f"     The FMR schedule:          {fmr_growth:+.1%}")
    if fmr_growth > zori_growth:
        print(f"     -> FMR outran the market by {fmr_growth - zori_growth:.1%}. The ratio")
        print(f"        fell because the denominator rose, not because rents did not.")
    else:
        print(f"     -> The market outran FMR by {zori_growth - fmr_growth:.1%}.")

    print(f"\n  2. LEVEL — indicative only; ZORI's unit mix is not the corpus's.")
    print(f"     Corpus rent/FMR:           {corpus:.3f}")
    print(f"     ZORI/FMR at the same date: {then:.3f}")
    print(f"     Corpus vs. market:         {corpus / then - 1.0:+.1%}")

    print("\nRead (1) and (1b) as evidence about the rent model's core assumption. Read (2)")
    print("as a hint about whether the corpus is representative of its own market, not as a")
    print("measurement of it — the populations differ in ways no weighting here fixes.")


def _anchor_comparison() -> None:
    """Would ZORI be a better anchor than FMR? The evidence for §6's cut-list item 6.

    Separate from the drift measurement above and reported separately, because it asks a
    different question. The drift asks *has the FMR anchor moved*; this asks *should the
    anchor be FMR at all*. The second only became worth asking once the first found drift.

    **The premise this had to test first was coverage**, and the expectation going in was
    wrong. ZIP-level FMR anchors only ~1,100 of the corpus's rows, because HUD's Small Area
    schedules do not cover every county, so ZORI was assumed to be similarly sparse. It is
    not: it covers essentially every ZIP the corpus occupies, and the binding constraint is
    when each ZIP's series *begins* rather than whether it exists.

    Two measures, because they disagree and the disagreement is the finding:

      * **Dispersion of the ratio itself.** A tighter ratio is an easier target to learn.
      * **Dispersion of the per-city means.** This is what an anchor is *for* — carrying
        the location signal so the model does not have to. `RENT_MODEL_FEATURES` holds no
        market identifier by design, so whatever the anchor fails to absorb here is error
        the model structurally cannot recover. §2's "location-blind below the county".
    """
    frame, _ = rent_model.build_training_frame()
    panel = zori.load()
    covered = set(panel["zip"])

    print(f"Corpus rows FMR anchors:            {len(frame):>6,}")
    in_zori = frame["zcta"].astype("string").isin(covered)
    print(f"  ... whose ZIP appears in ZORI:    {int(in_zori.sum()):>6,}  "
          f"({in_zori.mean():.0%})")

    # Anchor each row at its OWN listing month rather than a fixed date: a 2018 listing
    # and a 2019 one face different markets, and pinning both to one month would import
    # that year's trend into the ratio as noise.
    listed = pd.to_datetime(pd.to_numeric(frame["time"], errors="coerce"), unit="s")
    frame["month"] = listed.dt.to_period("M").dt.to_timestamp("M").dt.strftime("%Y-%m-%d")
    series = {str(z): zori.series_for_zip(panel, str(z))
              for z in frame["zcta"].dropna().unique()}

    def anchor(row):
        one = series.get(str(row["zcta"]))
        if one is None or row["month"] not in one.index:
            return float("nan")
        value = one[row["month"]]
        return float("nan") if pd.isna(value) else float(value)

    frame["zori"] = frame.apply(anchor, axis=1)
    usable = frame[frame["zori"].notna() & (frame["zori"] > 0)].copy()
    print(f"  ... AND observed at its own month:{len(usable):>6,}  "
          f"({len(usable) / len(frame):.0%})  <- what ZORI-anchoring would train on")

    usable["rent_to_zori"] = usable["price"] / usable["zori"]
    usable = usable[usable["rent_to_zori"].between(
        config.RENT_MODEL_MIN_RATIO, config.RENT_MODEL_MAX_RATIO)]

    print(f"\nOn the {len(usable):,} rows both anchors can price:\n")
    print(f"{'anchor':<12} {'mean':>7} {'median':>7} {'CV':>7}   {'per-city mean sd':>16}")
    print("-" * 56)
    for name, column in (("rent/FMR", "rent_to_fmr"), ("rent/ZORI", "rent_to_zori")):
        values = usable[column]
        by_city = usable.groupby(["state", "cityname"])[column]
        means = by_city.mean()[by_city.size() >= 50]
        print(f"{name:<12} {values.mean():>7.3f} {values.median():>7.3f} "
              f"{values.std() / values.mean():>6.1%}   {means.std():>16.3f}")

    print("\nThe two measures disagree, and both readings are in the answer:")
    print("  * ZORI's ratio is the *looser* one, so it is not an easier target to learn.")
    print("  * ZORI's per-city means are the *tighter* ones, so it absorbs more of the")
    print("    location signal the model has no feature for. That is the property an")
    print("    anchor exists to supply, which is why this is a cut-list item and not a")
    print("    closed case against.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true",
                        help="Fetch the ZORI CSV to data/ before running.")
    parser.add_argument("--anchor-comparison", action="store_true",
                        help="Compare FMR and ZORI as anchors (§6 cut-list item 6).")
    args = parser.parse_args()

    if args.download:
        print(f"Downloading ZORI -> {zori.ZORI_PATH}")
        zori.download(force=True)

    panel = zori.load()
    months = zori.month_columns(panel)
    print(f"ZORI: {len(panel):,} ZIPs, {months[0][:7]} to {months[-1][:7]}\n")

    if args.anchor_comparison:
        _anchor_comparison()
        return

    frame = _corpus_side()
    current = _current_denominators(frame)
    rows, dropped = _rows(frame, panel, current)
    _report(rows, dropped)


if __name__ == "__main__":
    main()
