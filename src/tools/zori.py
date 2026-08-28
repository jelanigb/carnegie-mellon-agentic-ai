"""Zillow ZORI — the independent, market-observed rent series (decision #16, OQ-6).

Why this module exists
------------------------
Every rent figure this system produces is a ratio to HUD's Fair Market Rent, learned from
a 2018-19 corpus and applied to today's FMR schedule. That design (§2) rests on one
assumption it has never been able to test: **that rent-to-FMR structure is stable across
the ~7 years between the corpus and now.** If the ratio has drifted, every rent estimate
is wrong by the drift and nothing in the pipeline would say so.

FMR cannot test it — the ratio's denominator cannot also be its check. The corpus cannot
test it either; it is one snapshot, and a snapshot cannot measure its own staleness. The
test needs a *market-observed* series covering both ends of the gap, which is what #16
adopted ZORI for and what stayed unbuilt through U6 and U7.

What ZORI is, and what it is not
----------------------------------
ZORI is Zillow's Observed Rent Index: a smoothed, repeat-listing measure of typical asked
rent, published monthly per ZIP from 2015-01. Two properties matter here and both cut
against a naive comparison:

1. **It is not bedroom-specific.** One number per ZIP per month, across unit types. FMR is
   published per bedroom count, and the rent model anchors each row at its own bedroom
   count. So a ZORI/FMR ratio needs a bedroom baseline chosen deliberately — see
   `scripts/zori_evidence.py`, which weights FMR by the corpus's own bedroom mix so the
   denominator describes the same mixture the numerator does.
2. **Its unit mix is not the corpus's.** ZORI covers single-family, condo and multifamily;
   the Kaggle corpus is professionally-marketed apartment listings. The two populations
   overlap without matching, and no weighting available here fixes that.

**The consequence is worth stating precisely, because it decides what this data can
settle.** The *level* comparison — is the corpus's ~1.40x FMR the market's ratio? — is
exposed to both mismatches and can only ever be indicative. The *stability* comparison —
has the ratio moved between the corpus vintage and today? — applies the identical
construction at both ends, so a constant mix bias cancels out of the difference. **The
question #16 actually asked is the stability one, and it is the one this data answers
cleanly.** Reported that way rather than blended into a single headline number.

Source and licensing
----------------------
Public research CSVs published by Zillow at files.zillowstatic.com, free to use with
attribution. Downloaded to `data/` (gitignored) rather than committed: it is ~10 MB, it is
re-fetchable from a stable URL, and §8's committed-inputs rule is about *derived* evidence
being reproducible, which the evidence script's output satisfies on its own.
"""

from __future__ import annotations

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
