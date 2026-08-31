"""ZIP-level sale-price benchmarks from county-assessor open data (U8.8, OQ-7, #11).

**Read side only.** `scripts/build_sale_benchmarks.py` builds the committed table and
carries the reasoning about sources, filters and why Los Angeles is absent; this module
is what the Valuation agent calls, and it makes no network request. That split is
deliberate for the same reason `tools/fmr_history.load_cohort_panel` reads a committed
panel: a report figure that depends on a live third-party request is a report that
renders differently depending on whether a municipal portal is up.

**What a lookup returns is a market reference, not a valuation.** The median describes
2-4 unit sales in the subject's ZIP over `config.SALE_BENCHMARK_WINDOW_START` onward,
with no adjustment for the subject's own size, unit count or condition — the same
caveat the metro figure carried, narrowed from a metro to a ZIP. Decision #15 leaves
`value_estimate` permanently `None` and this does not change that.

**Coverage is partial and the caller must handle a miss as an ordinary outcome**, not as
an error: two of the project's four indexed markets have a local tier (New York,
Chicago), Los Angeles has none because California publishes assessed value rather than
sale price, and Cleveland was never in scope for this pass. `lookup()` returns `None` in
all three cases and `unavailable_reason()` says which one applies, because "no data for
this ZIP", "no local tier in this market" and "this ZIP is too thin to trust" are
different facts and a reader can act on them differently.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

import config


@dataclass(frozen=True)
class ZipBenchmark:
    """One ZIP's median sale price, with everything needed to discount it.

    `n_sales` and `window_start` travel with the median rather than being looked up
    beside it, because the report states them in the same sentence — a median over 21
    sales and a median over 659 are different claims and the reader is told which.
    """

    zip_code: str
    median_sale_price: float
    n_sales: int
    market_label: str
    attribution: str
    definition: str
    window_start: str
    built_at: str


@dataclass(frozen=True)
class _Table:
    built_at: str
    window_start: str
    markets: dict[str, dict]
    zips: dict[str, dict]


@lru_cache(maxsize=1)
def _load(path: str) -> Optional[_Table]:
    """Read the committed table once per process, or None if it is not there.

    None rather than an exception, on `load_cohort_panel`'s precedent: a missing table
    degrades the benchmark to the metro tier, which the report already knows how to say,
    rather than failing a deal over a file that refines one figure.
    """
    file = Path(path)
    if not file.exists():
        return None
    raw = json.loads(file.read_text())
    return _Table(
        built_at=raw["built_at"],
        window_start=raw["window_start"],
        markets=raw["markets"],
        zips=raw["zips"],
    )


def lookup(zip_code: Optional[str]) -> Optional[ZipBenchmark]:
    """The ZIP's benchmark, or None when there is not a usable one.

    **`config.SALE_BENCHMARK_MIN_SALES` is applied here rather than at build time**, so
    the threshold can move without rebuilding the table from three municipal APIs — and
    so the artifact records what the data says while the judgment about how much data is
    enough stays in `config.py`, where §8 puts tunables.
    """
    table = _load(str(config.SALE_BENCHMARK_PATH))
    if table is None or not zip_code:
        return None

    record = table.zips.get(str(zip_code).strip())
    if record is None or record["n_sales"] < config.SALE_BENCHMARK_MIN_SALES:
        return None

    market = table.markets.get(record["market"], {})
    return ZipBenchmark(
        zip_code=str(zip_code).strip(),
        median_sale_price=float(record["median_sale_price"]),
        n_sales=int(record["n_sales"]),
        market_label=market.get("label", record["market"]),
        attribution=market.get("attribution", "county assessor records"),
        definition=market.get("definition", "multi-family sales"),
        window_start=table.window_start,
        built_at=table.built_at,
    )


def unavailable_reason(zip_code: Optional[str], city: Optional[str]) -> str:
    """Why this subject has no local benchmark — in the reader's terms, not the table's.

    Every branch names something the reader can act on or at least understand: a market
    where the records do not exist, a ZIP the records do not cover, or a ZIP whose sample
    is too thin to publish a median from. Written here rather than in the agent because
    the distinctions are properties of this table.
    """
    table = _load(str(config.SALE_BENCHMARK_PATH))
    where = f"around {city}" if city else "at this address"

    if table is None:
        return (
            "This build has no local sale-price records loaded, so the figure shown is "
            "the metro-wide one."
        )
    if not zip_code:
        return (
            f"No ZIP code resolved {where}, so no neighborhood sale-price record could "
            f"be looked up and the figure shown is the metro-wide one."
        )

    record = table.zips.get(str(zip_code).strip())
    if record is None:
        labels = sorted(m["label"] for m in table.markets.values())
        markets = (
            " and ".join([", ".join(labels[:-1]), labels[-1]])
            if len(labels) > 1
            else "".join(labels)
        )
        return (
            f"This build has neighborhood sale records for {markets} only, and ZIP "
            f"{zip_code} is not among them — so the figure shown is the metro-wide one. "
            f"Los Angeles County publishes assessed values rather than sale prices, "
            f"which are a different measure and are not substituted here."
        )
    return (
        f"Only {record['n_sales']} qualifying sales since {table.window_start} are on "
        f"record in ZIP {zip_code} — too few to publish a neighborhood median from, so "
        f"the figure shown is the metro-wide one."
    )
