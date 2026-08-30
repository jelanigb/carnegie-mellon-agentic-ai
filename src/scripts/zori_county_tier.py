"""Does a county tier close ZORI's coverage gap? (U11.3, §6 cut-list item 6)

    .venv/bin/python scripts/zori_county_tier.py

**Written to re-price a cut-list item rather than to justify one.** §6 item 6 prices
re-anchoring the rent model on ZORI at "a U5 rewrite, plus 27% of the training rows",
and the second half is the number that made the item look unaffordable. That figure is
real — `scripts/zori_evidence.py --anchor-comparison` measures 4,147 of 5,686 rows
priceable at ZIP grain — but it was never decomposed, and the decomposition changes what
it means.

**The gap is a series-start effect, not a coverage gap.** ZORI covers essentially every
ZIP the corpus occupies (5,662 of 5,686); what it does not always have is an observation
back at a given row's own 2018-19 listing month, because a thin ZIP's series begins when
Zillow has enough listings there. A county aggregate is continuous where any one of its
ZIPs is not, so the question this script asks is whether a **county tier** — the same
`zip → county` fallback `tools.model.rent_model.anchor_for_row` already applies to FMR —
recovers those rows.

**It states what it could have returned, per §8.** If the gap were absent ZIPs, a county
tier would recover close to nothing and item 6's price would stand as written. If it is
the series-start effect, recovery should be near total and the row-loss half of that
price is not a real cost. Either answer is publishable; the one that was not available
before this ran is *neither*, which is why the item sat unpriced.

**What this measures and what it does not.** It measures whether the *target* can be
computed — feasibility, not quality. Whether a ZORI-anchored ratio is a better thing to
learn is a separate question that `--anchor-comparison` already answers as genuinely
mixed: a looser ratio (CV 36.3% against FMR's 33.1%) but tighter per-city means (0.172
against 0.257), which is what an anchor exists to supply given `RENT_MODEL_FEATURES`
carries no market identifier. This script removes a feasibility objection. It does not
remove that one.

**Two limitations, stated rather than discovered later.**

1. **The county tier is a different denominator from the ZIP tier**, exactly as
   county-anchored and ZIP-anchored FMR rows are — `rent_model` documents that mixed
   basis as a real limitation of the current target, and `TrainingReport` records the
   split for it. A ZORI re-anchor inherits that same limitation rather than a new one,
   and it would need the same disclosure.
2. **ZORI ZIPs are joined to counties by name here** (`CountyName` against the Census
   `NAMELSAD`), which resolves 96.6% of the file and leaves independent cities and
   similar edge cases unmatched. That is adequate for a feasibility count and is *not*
   adequate for an implementation, which should resolve a ZIP to its county by the same
   polygon join `tools/county_crosswalk.py` already performs for points. The four
   markets in `config.INDEXED_MARKETS` are unaffected.

Reads the corpus, the ZORI panel and the Census county boundaries. No network calls
beyond what those loaders already cache, no model calls, and nothing is written.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

import config
from tools import kaggle_data, zori
from tools.model import rent_model


def _listing_month(frame: pd.DataFrame) -> pd.Series:
    """Each row's own listing month, keyed as ZORI's month columns are.

    Anchored at the row's own month rather than a fixed date, matching
    `scripts/zori_evidence.py`'s `--anchor-comparison`: a 2018 listing and a 2019 one
    face different markets, and pinning both to one month would import that year's trend
    into the ratio as noise. Keyed `%Y-%m-%d` at month end because that is the literal
    column name in Zillow's file, and a `%Y-%m` key silently matches nothing.
    """
    listed = pd.to_datetime(pd.to_numeric(frame["time"], errors="coerce"), unit="s")
    return listed.dt.to_period("M").dt.to_timestamp("M").dt.strftime("%Y-%m-%d")


def _zip_tier(frame: pd.DataFrame, panel: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """`(zip_is_in_zori, priceable_at_own_month)` — the baseline this script re-prices.

    Two masks rather than one, because they answer different questions and the
    difference between them *is* the finding: the first is coverage, the second is
    coverage that is usable at the corpus's vintage.
    """
    series = {z: zori.series_for_zip(panel, z) for z in frame["zcta"].dropna().unique()}
    in_zori = frame["zcta"].map(lambda z: series.get(z) is not None).fillna(False)

    def value(row):
        one = series.get(row["zcta"])
        if one is None or row["month"] not in one.index:
            return np.nan
        observed = one[row["month"]]
        return np.nan if pd.isna(observed) else float(observed)

    priced = frame.apply(value, axis=1)
    return in_zori, priced.notna() & (priced > 0)


def main() -> None:
    frame, _ = rent_model.build_training_frame()
    panel = zori.load()

    frame["month"] = _listing_month(frame)
    frame["zcta"] = frame["zcta"].astype("string")
    # The corpus carries HUD's 10-character entityid (state+county FIPS + a "99999"
    # placeholder — see `county_crosswalk._entityid_from_geoid`); the Census boundary
    # file is keyed on the bare 5-digit GEOID.
    frame["geoid"] = frame["county_fips"].astype(str).str[:5]

    in_zori, zip_ok = _zip_tier(frame, panel)
    gap = ~zip_ok

    print(f"Corpus rows FMR anchors:              {len(frame):>6,}")
    print(f"  ZIP appears in ZORI:                {int(in_zori.sum()):>6,}  ({in_zori.mean():.1%})")
    print(f"  AND observed at its own month:      {int(zip_ok.sum()):>6,}  ({zip_ok.mean():.1%})"
          f"   <- cut list's comparable set")
    print(f"  UNPRICED by the ZIP tier:           {int(gap.sum()):>6,}  ({gap.mean():.1%})"
          f"   <- the '27%'")
    absent = int((~in_zori).sum())
    print(f"     ZIP absent from ZORI:            {absent:>6,}")
    print(f"     present but no observation:      {int(gap.sum()) - absent:>6,}"
          f"   <- series-start effect")

    median_by_county, n_by_county = zori.county_medians(panel)
    print(f"ZORI ZIPs joined to a Census county:   "
          f"{int(n_by_county.max(axis=1).sum()):>6,} of {len(panel):,}")

    def county_value(row) -> tuple[float, int]:
        geoid, month = row["geoid"], row["month"]
        if geoid not in median_by_county.index or month not in median_by_county.columns:
            return float("nan"), 0
        return (
            float(median_by_county.at[geoid, month]),
            int(n_by_county.at[geoid, month]),
        )

    resolved = frame.apply(county_value, axis=1)
    frame["zori_county"] = [value for value, _ in resolved]
    frame["zori_county_zips"] = [n for _, n in resolved]
    county_ok = frame["zori_county"].notna() & (frame["zori_county"] > 0)

    recovered = gap & county_ok
    combined = zip_ok | county_ok

    print("\n=== County tier ===")
    print(f"  Rows the county tier can price:     {int(county_ok.sum()):>6,}  ({county_ok.mean():.1%})")
    print(f"  RECOVERED from the gap:             {int(recovered.sum()):>6,}"
          f"   = {recovered.sum() / max(int(gap.sum()), 1):.1%} of it")
    print(f"  Combined ZIP-or-county coverage:    {int(combined.sum()):>6,}  ({combined.mean():.1%})")
    print(f"  Residual, still unpriced:           {int((~combined).sum()):>6,}  ({(~combined).mean():.1%})")

    behind = frame.loc[recovered, "zori_county_zips"]
    if len(behind):
        print(f"  ZIPs behind each recovered median:  median {behind.median():.0f},"
              f" p10 {behind.quantile(0.10):.0f}, min {behind.min():.0f}"
              f"   <- a one-ZIP county median needs a floor and a disclosure")

    print("\n=== By indexed market ===")
    print(f"  {'market':<14} {'rows':>7} {'ZIP tier':>10} {'recovered':>11} {'combined':>10}")
    for state, patterns in config.INDEXED_MARKETS.items():
        mask = (frame["state"] == state) & frame["cityname"].apply(
            lambda c, p=patterns: kaggle_data.city_matches(c, p)
        )
        if not int(mask.sum()):
            continue
        print(f"  {patterns[0]:<14} {int(mask.sum()):>7,} {zip_ok[mask].mean():>9.1%} "
              f"{int(recovered[mask].sum()):>11,} {combined[mask].mean():>9.1%}")


if __name__ == "__main__":
    main()
