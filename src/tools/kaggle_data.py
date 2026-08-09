"""Loading and cleaning for the Kaggle rental corpus.

Every consumer of this dataset — the comp index (U4), the rent regression (U5), and the
metro verification script — needs the same cleaning applied identically. Centralizing it
here means a data-quality decision is made once and cannot drift between consumers.

Data-quality issues found in the raw extract and handled here:

1. **Encoding.** The file is cp1252, not utf-8; free-text fields carry Windows-encoded
   bytes that fail a naive read.
2. **84 duplicate `id` values.** Verified as exact duplicate rows — identical on price,
   bedrooms, square_feet, cityname, and latitude — so they are dropped rather than
   reconciled. Left in place they would double-count listings in the comp index and
   silently overweight those rows in regression training.
3. **Implausible rents.** A small number of rows fall outside a defensible long-term
   rent range (79 nationally). Bounds live in config.py.
4. **City name matching.** Metro rollup requires matching "Cleveland" to "Cleveland
   Heights" while *not* matching "Queens" to "Queensbury" or "Bronx" to "Bronxville" —
   both real false positives in this data, and both outside the metro they appear to
   name. Naive substring matching gets this wrong; word-boundary matching gets it right.
"""

from __future__ import annotations

import re

import pandas as pd

import config

KAGGLE_PATH = config.DATA_DIR / "apartments_for_rent_classified_100K.csv"

# Fields without which a row is useless to either the comp index or the regression.
CORE_FIELDS = [
    "price", "bedrooms", "bathrooms", "square_feet",
    "latitude", "longitude", "cityname", "state",
]

NUMERIC_FIELDS = ["price", "bedrooms", "bathrooms", "square_feet", "latitude", "longitude"]


def city_matches(cityname: str, patterns: list[str]) -> bool:
    """Word-boundary match of a city name against candidate patterns.

    Word boundaries rather than plain substring containment: "Cleveland" should match
    "Cleveland Heights" (genuinely the Cleveland metro) but "Queens" must not match
    "Queensbury" (upstate New York, ~200 miles from the borough). Both cases occur in
    this dataset.
    """
    name = str(cityname or "")
    return any(re.search(rf"\b{re.escape(p)}\b", name, re.IGNORECASE) for p in patterns)


def load_clean(apply_rent_bounds: bool = True) -> pd.DataFrame:
    """Load the corpus with all cleaning applied. This is the only supported entry point."""
    df = pd.read_csv(KAGGLE_PATH, sep=";", encoding="cp1252", low_memory=False)

    before = len(df)
    df = df.drop_duplicates(subset="id", keep="first")
    deduped = before - len(df)

    df = df.dropna(subset=CORE_FIELDS)
    for col in NUMERIC_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=NUMERIC_FIELDS)

    if apply_rent_bounds:
        df = df[
            (df["price"] >= config.KAGGLE_MIN_RENT)
            & (df["price"] <= config.KAGGLE_MAX_RENT)
        ]

    df.attrs["rows_deduped"] = deduped
    df.attrs["rows_dropped"] = before - len(df)
    return df.reset_index(drop=True)


def filter_markets(df: pd.DataFrame, markets: dict[str, list[str]]) -> pd.DataFrame:
    """Restrict to the given markets, keyed by state code -> city name patterns."""
    frames = []
    for state, patterns in markets.items():
        in_state = df[df["state"] == state]
        mask = in_state["cityname"].apply(lambda c: city_matches(c, patterns))
        frames.append(in_state[mask])
    if not frames:
        return df.iloc[0:0]
    return pd.concat(frames, ignore_index=True)


def vintage(df: pd.DataFrame) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Min/max listing timestamps. The `time` column is a Unix timestamp."""
    t = pd.to_datetime(pd.to_numeric(df["time"], errors="coerce"), unit="s")
    return t.min(), t.max()
