"""How unusual is a given premium over the local sale benchmark? (U9.4)

**Written because U9.4 puts a threshold at the center of the report's headline claim, and
nothing in this repository said what a premium is worth.** The recommendation rule reads
the asking price against `ValuationDetail.benchmark_median_sale_price` and has to decide
where "priced materially above comparable sales" begins. The committed table
(`tools/data/zip_sale_benchmarks.json`) holds one median per ZIP and no dispersion at
all, so a threshold picked from it would be picked from nothing — the same defect #21 was
adopted to fix on the rent side, where a correlation was asserted once and never
re-measured.

This script re-pulls the individual sales behind those medians and asks the only question
that can place a threshold on evidence: **among sales that actually happened in a ZIP,
what fraction cleared their own ZIP's median by X%?** A premium at the 55th percentile of
real transactions is an ordinary sale and the report should not call it material. One at
the 95th is rare, and saying so is a claim the data supports.

What this measures, and what it does not
----------------------------------------
The spread of closed sale prices around their ZIP median, over the same window, filters
and publisher arm's-length screens `scripts/build_sale_benchmarks.py` uses — imported
from it rather than restated, so "a qualifying sale" has one definition.

That spread is driven mostly by **what was sold**, not by what anyone overpaid: the
benchmark carries no adjustment for square footage, unit count, condition or block, which
is the caveat `agents/summarizer._benchmark_section` prints in bold beneath every figure.
So a premium's percentile here answers *"how rare is a price this far above the local
median"* and never *"how far above fair value is this property"*. That is the weaker of
the two claims and it is the one the recommendation should make.

**Two references, because the report has two tiers.** Sales are measured against their
own ZIP's median and, separately, against their whole market's median — the second being
what a metro-tier benchmark actually is. Los Angeles has no local tier at all (California
publishes assessed value under Proposition 13, see the build script), so its demo deals
are read against a metro figure and the second table is the one that governs them.

The leave-one-out question is not asked: each ZIP kept here has at least
`config.SALE_BENCHMARK_MIN_SALES` sales, so a single record moves its own median by less
than the rounding in the output.

Run: .venv/bin/python scripts/sale_premium_distribution.py
     .venv/bin/python scripts/sale_premium_distribution.py --refresh   # re-pull
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from scripts.build_sale_benchmarks import _MARKET_FETCHERS

# The pulled sales, so re-reading the distribution does not re-pull two portals. Under
# `data/`, which is gitignored — this is a cache of a public source, not an artifact.
_CACHE_PATH = config.DATA_DIR / "processed" / "sale_premium_sales.json"

# Premiums the report might plausibly draw a line at, plus the three demo deals' own
# positions so they land inside the table rather than being compared to it afterwards.
_PREMIUM_GRID = (
    -0.20, -0.17, -0.10, 0.00, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40,
    0.50, 0.55, 0.60, 0.75, 1.00, 1.50,
)

# Read off in the other direction: where does a stated percentile fall in dollars-over-
# median terms? This is the column a threshold gets set from.
_PERCENTILE_GRID = (0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 0.99)


def _load_sales(refresh: bool) -> dict[str, dict[str, list[float]]]:
    """Per-market, per-ZIP sale prices — from cache unless asked to re-pull.

    The cache is keyed by nothing but its own existence on purpose. It holds a pull from
    two public portals under a fixed window; if the filters in `config` change, the
    honest move is `--refresh`, and a staleness heuristic here would only be a second
    place to get that wrong.
    """
    if not refresh and _CACHE_PATH.exists():
        cached = json.loads(_CACHE_PATH.read_text())
        counts = {m: sum(len(v) for v in z.values()) for m, z in cached.items()}
        print(f"Cached pull: {counts} (--refresh to re-pull)")
        return cached

    print(f"Window: sales on or after {config.SALE_BENCHMARK_WINDOW_START}")
    sales = {key: fetcher() for key, fetcher in _MARKET_FETCHERS.items()}
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(json.dumps(sales))
    return sales


def _percentile_of(sorted_values: list[float], target: float) -> float:
    """Share of `sorted_values` at or below `target`. Linear scan; the lists are small."""
    if not sorted_values:
        return float("nan")
    below = sum(1 for v in sorted_values if v <= target)
    return below / len(sorted_values)


def _quantile(sorted_values: list[float], q: float) -> float:
    """The value at quantile `q`, nearest-rank.

    Nearest-rank rather than interpolated because the output is read as "a real sale sat
    here", and an interpolated quantile is a price nobody paid.
    """
    if not sorted_values:
        return float("nan")
    index = min(len(sorted_values) - 1, int(q * len(sorted_values)))
    return sorted_values[index]


def _zip_tier_premiums(by_zip: dict[str, list[float]]) -> tuple[list[float], int, int]:
    """Every qualifying sale's price as a ratio to its own ZIP's median.

    ZIPs below `config.SALE_BENCHMARK_MIN_SALES` are dropped, because those are exactly
    the ZIPs the Valuation agent already refuses to read a benchmark from — measuring
    dispersion on medians the system would never publish would describe a code path that
    does not exist.
    """
    ratios: list[float] = []
    kept = dropped = 0
    for prices in by_zip.values():
        if len(prices) < config.SALE_BENCHMARK_MIN_SALES:
            dropped += 1
            continue
        kept += 1
        median = statistics.median(prices)
        if median <= 0:
            continue
        ratios.extend(price / median for price in prices)
    return sorted(ratios), kept, dropped


def _market_tier_premiums(by_zip: dict[str, list[float]]) -> list[float]:
    """Every sale as a ratio to the whole market's median — what a metro tier is.

    No ZIP floor here: the metro median is taken over every qualifying sale in the
    market, thin ZIPs included, which is what `redfin_data`'s metro figure does too.
    """
    prices = [p for values in by_zip.values() for p in values]
    if not prices:
        return []
    median = statistics.median(prices)
    return sorted(price / median for price in prices) if median > 0 else []


def _per_zip_percentiles(by_zip: dict[str, list[float]], premium: float) -> list[float]:
    """One percentile per ZIP, so a few dense ZIPs cannot speak for the market.

    The pooled figure weights a ZIP by how many sales it had; Brooklyn's busiest ZIP
    carries many times the weight of Tottenville's. Reported alongside as a robustness
    check — if the two disagree materially, the pooled number is describing a
    neighborhood rather than a market.
    """
    out: list[float] = []
    for prices in by_zip.values():
        if len(prices) < config.SALE_BENCHMARK_MIN_SALES:
            continue
        median = statistics.median(prices)
        if median <= 0:
            continue
        ratios = sorted(price / median for price in prices)
        out.append(_percentile_of(ratios, 1.0 + premium))
    return out


def _premium_table(label: str, ratios: list[float], by_zip: Optional[dict] = None) -> None:
    print(f"\n### {label} — {len(ratios):,} sales")
    if not ratios:
        print("  (no qualifying sales)")
        return
    header = "  premium | percentile of sales at or below"
    if by_zip is not None:
        header += " | median across ZIPs"
    print(header)
    for premium in _PREMIUM_GRID:
        pooled = _percentile_of(ratios, 1.0 + premium)
        row = f"  {premium:+6.0%} | {pooled:29.1%}"
        if by_zip is not None:
            per_zip = _per_zip_percentiles(by_zip, premium)
            row += f" | {statistics.median(per_zip):18.1%}" if per_zip else " | —"
        print(row)

    print("\n  percentile | premium over the median at that percentile")
    for q in _PERCENTILE_GRID:
        print(f"  {q:10.0%} | {_quantile(ratios, q) - 1.0:+43.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-pull both portals instead of reading the cached sales.",
    )
    args = parser.parse_args()

    sales = _load_sales(args.refresh)

    print("\n" + "=" * 78)
    print("ZIP tier — each sale against its own ZIP's median")
    print("=" * 78)
    pooled_zip: list[float] = []
    for market, by_zip in sales.items():
        ratios, kept, dropped = _zip_tier_premiums(by_zip)
        definition = config.SALE_BENCHMARK_SOURCES[market]["definition"]
        print(
            f"\n{config.SALE_BENCHMARK_SOURCES[market]['label']}: {kept} ZIPs kept, "
            f"{dropped} below the {config.SALE_BENCHMARK_MIN_SALES}-sale floor · "
            f"{definition}"
        )
        _premium_table(config.SALE_BENCHMARK_SOURCES[market]["label"], ratios, by_zip)
        pooled_zip.extend(ratios)
    _premium_table("Both markets pooled", sorted(pooled_zip))

    print("\n" + "=" * 78)
    print("Metro tier — each sale against its whole market's median")
    print("=" * 78)
    print(
        "This is the reference Los Angeles reads, and the one every deal reads where no\n"
        "local tier exists. Wider by construction: it describes properties an hour apart\n"
        "with one number."
    )
    for market, by_zip in sales.items():
        _premium_table(
            f"{config.SALE_BENCHMARK_SOURCES[market]['label']} (metro tier)",
            _market_tier_premiums(by_zip),
        )


if __name__ == "__main__":
    main()
