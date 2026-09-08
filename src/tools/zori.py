"""Zillow Observed Rent Index (ZORI) — the market-observed rent series this system anchors to.

Why this module exists
------------------------
Two consumers, and both are load-bearing:

1. **The rent anchor.** `tools/model/rent_model.py` learns rent as a ratio to the local
   rent *level*, and this series supplies that level — at the row's own ZIP and its own
   listing month during training, and at the subject's ZIP and the newest published month
   at inference.
2. **The forecast's rent growth.** `tools/rent_growth.py` differences the same series to
   band rent growth, so the projection moves by the same mechanism that produced the
   estimate.

Using a market series for both is what keeps the corpus's 2018-19 vintage out of the
output: the numerator and the denominator are read at the same month, so the vintage
divides out where it arises rather than being corrected afterwards.

What ZORI is, and what it is not
----------------------------------
ZORI is Zillow's Observed Rent Index: a smoothed, repeat-listing measure of typical asked
rent, published monthly per ZIP from 2015-01. Two properties matter here:

1. **It is not bedroom-specific.** One number per ZIP per month, across unit types. This is
   why the anchor is a hybrid — the federal rent schedule supplies the step between bedroom
   counts, with its own level divided out. See `rent_model.bedroom_shape`.
2. **Its unit mix is not the corpus's.** ZORI covers single-family, condo and multifamily;
   the listing corpus is professionally-marketed apartment listings. The two populations
   overlap without matching, and no weighting available here fixes that.

**That second point decides what comparisons against this series can settle.** A *level*
comparison — is the corpus's rent-to-schedule ratio the market's ratio? — is exposed to the
mix mismatch and can only ever be indicative. A *stability* comparison — has the ratio moved
between the corpus vintage and today? — applies the identical construction at both ends, so
a constant mix bias cancels out of the difference. `scripts/zori_evidence.py` reports the
two separately rather than blending them into one headline number.

Source and licensing
----------------------
Public research CSVs published by Zillow at files.zillowstatic.com, free to use with
attribution. Downloaded to `data/` (gitignored) rather than committed: it is ~10 MB and
re-fetchable from a stable URL, and what this project commits is *derived* evidence, which
the evidence scripts' outputs already carry.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

import config

# The ZIP-level, smoothed, all-home-types series. "uc" is Zillow's unadjusted-cutoff
# variant and "sm" the smoothed one; the seasonally-adjusted twin (`_sa_`) is deliberately
# not used, because both ends of the vintage comparison are read at the same calendar
# month and seasonal adjustment would only add a transformation to reason about.
ZORI_URL = (
    "https://files.zillowstatic.com/research/public_csvs/zori/"
    "Zip_zori_uc_sfrcondomfr_sm_month.csv"
)
ZORI_PATH = config.DATA_DIR / "Zip_zori_uc_sfrcondomfr_sm_month.csv"

# Zillow's layout is a block of identity columns followed by one column per month. Which
# columns are months is decided by **whether the name parses as a date**, not by naming a
# fixed identity set — that first version was wrong within an hour of being written, and
# instructively so: it defined months as "not one of these nine names", so the `zip`
# column this module derives in `load()` was silently classified as a month, and the
# panel reported its own range as "2015-01 to zip". A negative definition breaks whenever
# anyone adds a column, including us. Asking the column what it is cannot.


def download(force: bool = False) -> Path:
    """Fetch the CSV to `data/` if it is not already there.

    Kept as an explicit step rather than an implicit one inside `load()`: a script that
    silently reaches the network on import is a script whose failures are hard to read,
    and this one is meant to be run deliberately.
    """
    if ZORI_PATH.exists() and not force:
        return ZORI_PATH

    import urllib.request

    ZORI_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Download to a sibling temp file and rename, so an interrupted fetch cannot leave a
    # truncated CSV that later loads as a smaller, silently wrong dataset.
    staging = ZORI_PATH.with_suffix(".partial")
    urllib.request.urlretrieve(ZORI_URL, staging)
    staging.replace(ZORI_PATH)
    return ZORI_PATH


def month_columns(df: pd.DataFrame) -> list[str]:
    """The monthly value columns, in order, as they appear in the file.

    A column counts as a month if its name parses as a date — see the note above for the
    defect the earlier negative definition produced.
    """
    months = []
    for column in df.columns:
        try:
            pd.Timestamp(str(column))
        except (ValueError, TypeError):
            continue
        months.append(column)
    return months


def load() -> pd.DataFrame:
    """The ZORI panel, indexed by five-digit ZIP.

    `RegionName` arrives as an integer for most ZIPs, which drops the leading zero on
    every New England and New Jersey code. Zero-padded here rather than at each call
    site, because a silent join failure on exactly the ZIPs that start with 0 is the kind
    of defect that looks like sparse coverage.
    """
    if not ZORI_PATH.exists():
        raise FileNotFoundError(
            f"ZORI data not found at {ZORI_PATH}. Run `zori.download()` or "
            f"`scripts/zori_evidence.py --download` first."
        )
    df = pd.read_csv(ZORI_PATH, low_memory=False)
    # Copied before the column is added, not after: the file is ~140 columns wide, and
    # appending to the frame pandas returns from read_csv warns about fragmentation at the
    # point of assignment, which a later copy does not suppress.
    df = df.copy()
    df["zip"] = df["RegionName"].astype(str).str.strip().str.zfill(5)
    return df


def series_for_zip(df: pd.DataFrame, zip_code: str) -> Optional[pd.Series]:
    """One ZIP's monthly series as a float Series indexed by month string, or None.

    Returns None rather than an empty Series when the ZIP is absent, so a caller has to
    distinguish "not covered" from "covered but all-NaN" — they mean different things
    about ZORI's coverage and would otherwise silently merge.
    """
    match = df[df["zip"] == zip_code]
    if match.empty:
        return None
    row = match.iloc[0]
    months = month_columns(df)
    return pd.to_numeric(row[months], errors="coerce")


def county_medians(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Per-county monthly median ZORI, and the ZIP count behind each median.

    **Why a county tier exists at all.** ZORI covers essentially every ZIP the corpus
    occupies, but an individual ZIP's series begins only when Zillow has enough listings
    there, so a 2018-19 read lands before many of them start — measured at 1,515 of the
    corpus's 5,686 rows. A county aggregate is continuous where any one of its ZIPs is
    not, and it recovers 99.0% of that gap (`scripts/zori_county_tier.py`). This is the
    same `zip -> county` fallback `tools.model.rent_model.anchor_for_row` already applies
    to FMR, and it carries the same caveat: a county figure is a different denominator
    from a ZIP one, and a caller mixing them owes its reader a disclosure.

    The count travels with the median for the reason `CompAnchoring.comps_used` does — a
    median over one ZIP is a county median in name only, and nothing else distinguishes
    it from a median over thirty.

    Returns `(medians, zip_counts)`, both indexed by 5-digit county GEOID and columned by
    ZORI's own month strings.

    **ZIPs are matched to counties by name here** (`CountyName` against the Census
    `NAMELSAD`), which resolves ~96.6% of the file and misses independent cities and
    similar edge cases. Adequate because the alternative — a polygon join per ZIP — needs
    ZIP boundaries this project does not otherwise load, and every market in
    `config.INDEXED_MARKETS` resolves. Stated because it is a real limitation of the
    figure and not visible in the output.
    """
    from tools import county_crosswalk

    counties = county_crosswalk._counties()
    geoid_by_name = counties.assign(
        key=counties["STUSPS"].str.upper() + "|" + counties["NAMELSAD"].str.lower()
    ).set_index("key")["GEOID"].to_dict()

    keyed = df.assign(
        key=df["State"].astype(str).str.upper()
        + "|"
        + df["CountyName"].astype(str).str.lower()
    )
    keyed["geoid"] = keyed["key"].map(geoid_by_name)
    matched = keyed[keyed["geoid"].notna()]
    months = month_columns(df)
    return (
        matched.groupby("geoid")[months].median(),
        matched.groupby("geoid")[months].count(),
    )


@lru_cache(maxsize=1)
def panel() -> Optional[pd.DataFrame]:
    """The ZORI panel, loaded once per process, or `None` if the file is absent.

    ~10 MB, and **every rent estimate reads it** — the anchor the model learns a ratio to
    is built from this series. `None` rather than an exception for the
    reason `rent_model.load` returns `None` for a missing model: an absent data file is a
    condition the Valuation agent discloses through the flag mechanism, not a crash, and
    the pipeline must still produce a report on a machine that has not downloaded it.
    """
    try:
        return load()
    except (FileNotFoundError, OSError):
        return None


@lru_cache(maxsize=1)
def county_median_tables() -> Optional[tuple[pd.DataFrame, pd.DataFrame]]:
    """`county_medians` over the cached panel, computed once per process.

    Cached because it reads the Census county boundaries and groups ~8,500 ZIPs across
    ~140 month columns, which is far too expensive to repeat per subject — and the county
    tier is consulted for any subject whose own ZIP series has not started.
    """
    frame = panel()
    return None if frame is None else county_medians(frame)


def latest_month(df: pd.DataFrame) -> Optional[str]:
    """The most recent month column carrying any observation at all.

    Read from the file rather than from today's date: Zillow publishes on a lag, so the
    newest column is the newest *observation*, and an estimate anchored to it is only as
    current as that. `config.RENT_ANCHOR_MAX_STALENESS_MONTHS` decides when that gap is
    worth disclosing.
    """
    for column in reversed(month_columns(df)):
        if df[column].notna().any():
            return str(column)
    return None


def value_at(series: pd.Series, month: str) -> Optional[float]:
    """The value at an exact month column, or None if absent or unobserved."""
    if month not in series.index:
        return None
    value = series[month]
    return None if pd.isna(value) else float(value)


def nearest_observed(series: pd.Series, month: str) -> Optional[tuple[str, float]]:
    """The observed value nearest to `month`, and which month supplied it.

    ZORI's coverage of a given ZIP starts when Zillow has enough listings there, so an
    early-vintage read can land before a ZIP's series begins. Returning the month used
    alongside the value keeps that substitution visible in the output instead of letting
    a reader assume every row was read at the same date.
    """
    observed = series.dropna()
    if observed.empty:
        return None
    target = pd.Timestamp(month)
    distances = (pd.to_datetime(observed.index) - target).map(abs)
    position = int(distances.argmin())
    return str(observed.index[position]), float(observed.iloc[position])
