"""Reproduces the metro-selection evidence in docs/implementation_plan.md §2.

§2 originally hypothesized New York / Chicago / Philadelphia as the inference trio,
reasoned from housing-stock patterns rather than from these datasets. This script is
the check that overturned it, and it exists so the resulting table is reproducible
rather than a set of numbers asserted once in a document.

It answers two questions:

  1. Kaggle rent-listing density per candidate metro — does a credible comp corpus
     exist there? (Also confirms the dataset's vintage from the `time` column.)
  2. Redfin 2-4 unit sales volume per candidate metro — is there enough transaction
     volume for a stable appreciation series?

A metro must clear both bars. Chicago, Los Angeles, and Cleveland do; New York fails
the first and Philadelphia fails both.

Also produces the ranked Kaggle density list backing decision #4 in §7 (the ~5-8 metro
training shortlist, which is a superset of the inference trio).

Run: .venv/bin/python scripts/verify_metro_selection.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
KAGGLE_PATH = REPO_ROOT / "data" / "apartments_for_rent_classified_100K.csv"
REDFIN_PATH = (
    REPO_ROOT
    / "data"
    / "redfin_property_types_monthly_all_metros_multi_family_2_4_units_2018_Jan_to_2026_Jun.csv"
)

# Kaggle has no county/ZIP column (see §2, "Two data gaps"), so metros are assembled
# from cityname substrings scoped to a state. Substring matching is intentional:
# "New York" must roll up its boroughs, which appear as separate cityname values.
CANDIDATE_METROS: dict[tuple[str, str], list[str]] = {
    ("IL", "Chicago"): ["Chicago"],
    ("CA", "Los Angeles"): ["Los Angeles"],
    ("OH", "Cleveland"): ["Cleveland"],
    ("NY", "New York City (all boroughs)"): [
        "New York", "Brooklyn", "Queens", "Bronx", "Staten Island", "Manhattan"
    ],
    ("PA", "Philadelphia"): ["Philadelphia"],
    ("MA", "Boston"): ["Boston"],
    ("OH", "Cincinnati"): ["Cincinnati"],
    ("NJ", "Newark/Jersey City"): ["Newark", "Jersey City"],
    ("WI", "Milwaukee"): ["Milwaukee"],
    ("NY", "Buffalo"): ["Buffalo"],
    ("MI", "Detroit"): ["Detroit"],
    ("PA", "Pittsburgh"): ["Pittsburgh"],
}

# REGION NAME substring in the Redfin extract, per candidate metro label above.
REDFIN_REGION = {
    "Chicago": "Chicago, IL metro area",
    "Los Angeles": "Los Angeles, CA metro area",
    "Cleveland": "Cleveland, OH metro area",
    "New York City (all boroughs)": "New York, NY metro area",
    "Philadelphia": "Philadelphia, PA metro area",
    "Boston": "Boston, MA metro area",
    "Cincinnati": "Cincinnati, OH metro area",
    "Newark/Jersey City": "New York, NY metro area",  # same CBSA
    "Milwaukee": "Milwaukee, WI metro area",
    "Buffalo": "Buffalo, NY metro area",
    "Detroit": "Detroit, MI metro area",
    "Pittsburgh": "Pittsburgh, PA metro area",
}

# Minimum bars a metro must clear to be viable as an inference metro. Provisional and
# deliberately loose — they exist to make the pass/fail judgment explicit rather than
# to be precise. Tune alongside decision #4 in §7.
MIN_KAGGLE_LISTINGS = 500
MIN_REDFIN_SALES = 100


def load_kaggle() -> pd.DataFrame:
    # cp1252, not utf-8: the export contains Windows-encoded bytes in free-text fields.
    return pd.read_csv(KAGGLE_PATH, sep=";", encoding="cp1252")


def kaggle_metro_counts(df: pd.DataFrame) -> dict[str, int]:
    counts: dict[str, int] = {}
    for (state, label), substrings in CANDIDATE_METROS.items():
        in_state = df[df["state"] == state]
        mask = in_state["cityname"].fillna("").apply(
            lambda c: any(sub.lower() in c.lower() for sub in substrings)
        )
        counts[label] = int(mask.sum())
    return counts


def redfin_median_sales(df: pd.DataFrame) -> dict[str, float]:
    medians: dict[str, float] = {}
    for label, region in REDFIN_REGION.items():
        rows = df[df["REGION NAME"] == region]
        sold = pd.to_numeric(rows["HOMES SOLD"], errors="coerce").dropna()
        medians[label] = float(sold.median()) if len(sold) else float("nan")
    return medians


def main() -> None:
    # ---------- Kaggle ----------
    kaggle = load_kaggle()
    print(f"Kaggle: loaded {len(kaggle):,} rows from {KAGGLE_PATH.name}\n")

    print("=== Missing values in fields the pipeline depends on ===")
    print(kaggle[["cityname", "state", "price", "bedrooms", "square_feet", "time"]]
          .isna().sum().to_string())

    # Vintage: §2 claims Dec 2018 - Dec 2019. Confirm rather than restate.
    times = pd.to_datetime(pd.to_numeric(kaggle["time"], errors="coerce"), unit="s")
    print(f"\n=== Vintage (from `time`) ===\n{times.min()}  ->  {times.max()}")

    print("\n=== Top 25 (state, cityname) by listing count — backs §7 decision #4 ===")
    top = kaggle.groupby(["state", "cityname"]).size().sort_values(ascending=False).head(25)
    print(top.to_string())

    # ---------- Redfin ----------
    redfin = pd.read_csv(REDFIN_PATH)
    print(f"\n\nRedfin: loaded {len(redfin):,} rows from {REDFIN_PATH.name}")
    print(f"  FREQUENCY:   {sorted(redfin['FREQUENCY'].unique())}")
    print(f"  REGION TYPE: {sorted(redfin['REGION TYPE'].unique())}")
    print(f"  distinct metros: {redfin['REGION NAME'].nunique():,}")
    print("  NOTE: extract is Monthly, not Rolling 3 Months — §2 specifies computing")
    print("        the rolling window in tools/redfin_data.py rather than re-downloading.")

    # ---------- Combined verdict (reproduces the §2 table) ----------
    counts = kaggle_metro_counts(kaggle)
    medians = redfin_median_sales(redfin)

    print("\n\n=== §2 metro selection table ===")
    print(f"(bars: Kaggle >= {MIN_KAGGLE_LISTINGS} listings, "
          f"Redfin >= {MIN_REDFIN_SALES} median sales/period)\n")
    header = f"{'metro':<32} {'kaggle':>8} {'redfin':>8}  verdict"
    print(header)
    print("-" * len(header))

    ranked = sorted(counts, key=lambda m: -(counts[m] + medians.get(m, 0)))
    for label in ranked:
        k = counts[label]
        r = medians.get(label, float("nan"))
        k_ok = k >= MIN_KAGGLE_LISTINGS
        r_ok = r >= MIN_REDFIN_SALES
        if k_ok and r_ok:
            verdict = "PASS  — viable on both"
        elif not k_ok and not r_ok:
            verdict = "FAIL  — weak on both"
        elif not k_ok:
            verdict = "FAIL  — comps too thin"
        else:
            verdict = "FAIL  — sales volume too thin"
        print(f"{label:<32} {k:>8,} {r:>8,.0f}  {verdict}")

    print("\nSelected inference trio (§2): Chicago, Los Angeles, Cleveland.")
    print("Boston passes both bars but is excluded — HUD defines FMR areas by town")
    print("rather than county in the six New England states, which would require a")
    print("regional branch in tools/hud_fmr.py for no analytical gain.")


if __name__ == "__main__":
    main()
