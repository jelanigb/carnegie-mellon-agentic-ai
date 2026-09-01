"""Build the committed ZIP-level sale-price benchmark table (U8.8, OQ-7, #11).

**What this replaces, and what it does not.** `ValuationDetail.benchmark_median_sale_price`
has been a Redfin *metro* median since U6 — one number for every 2-4 unit property in
Chicago, and §2's "location-blind below the county" limitation showing up on the price
side exactly as it did on the rent side before ZIP-resolution anchoring landed. This
script builds the sub-metro replacement from county-assessor open data. It does **not**
produce a value estimate for a property: #15 leaves `value_estimate` permanently `None`,
and a ZIP median is still a market reference, just a local one.

**Why an aggregate rather than a parcel match, which is what makes this affordable.**
U8's Q3 priced this item as an address-to-parcel join — "the same class of work that
produced U3's geocoding tier fallbacks, and bounded only if the join works first try" —
and scheduled it behind the harness core with a drop-dead date for that reason. That
priced the *original* specification, scoring a value estimate that no longer exists. The
respecified deliverable is a benchmark, which needs a median over the subject's ZIP and
never needs to identify the subject's parcel. No fuzzy address matching happens anywhere
in this file.

**Sources, and their admissibility under §8.** Both are public records published by the
assessing authority itself; neither dataset carries a license field in its Socrata
metadata, so admissibility rests on §8's "public record" clause rather than on an open
licence, and each record here keeps the issuing office's attribution.

| Market | Portal | Dataset | Route |
| --- | --- | --- | --- |
| New York | NYC Open Data | `w2pb-icbu` (Citywide Annualized Calendar Sales) | direct — carries `zip_code`, `residential_units` and `sale_price` in one table |
| Chicago | Cook County Open Data | `wvhk-k5uv` (Assessor Parcel Sales) + `nj4t-kc8j` (Parcel Universe) | joined on an exact `pin`; sales carry no ZIP, the universe carries no sale |

**Los Angeles is absent by measurement, not by omission.** California assessor rolls
publish *assessed value* (`Roll_LandValue` / `Roll_ImpValue`), not transaction price,
because Proposition 13 fixes a base-year value that is systematically stale for a
long-held parcel. That is a different instrument and substituting it silently would put
two incomparable quantities behind one field name. Los Angeles keeps the Redfin metro
median and the report says which tier it is reading, per §8's Transparent Degradation.

**The two markets do not define "multi-family" identically, and the table says so per
market rather than averaging the difference away.** New York publishes a unit count, so
its rows are filtered to 2-4 residential units with no commercial unit — Redfin's own
"Multi-Family (2-4 unit)" definition. Cook County publishes a property *class*, and the
closest class is 211, "apartment building with two to six units". There is no unit count
in either Cook dataset to narrow it with, so Chicago's benchmark covers 2-6 units and
every record carries the definition it was built under.

**Cook's own non-arm's-length screens are used rather than a price floor alone.** The
sales dataset publishes `is_multisale`, `sale_filter_deed_type`,
`sale_filter_same_sale_within_365` and `sale_filter_less_than_10k` — the assessor's
judgment about which transfers are not market sales. Measured on class 211 since 2023:
20,369 sales, of which 18,335 pass all four. Using the publisher's screen rather than
inventing one is the same reasoning `tools/redfin_data.py` applies to its price floor,
one level better sourced.

Run: `.venv/bin/python scripts/build_sale_benchmarks.py`
     `.venv/bin/python scripts/build_sale_benchmarks.py --dry-run`  (measure, write nothing)

Writes `config.SALE_BENCHMARK_PATH`, which is committed: the pipeline must not make a
network call to render a benchmark, for the same reason `EVAL_RECORDINGS_DIR` is
committed — a fresh clone has to reproduce the report's figures.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterator, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config

_PAGE = 50_000
_TIMEOUT_SECONDS = 180


def _get(base: str, dataset: str, **params: str) -> list[dict]:
    """One Socrata request, with the query echoed on failure.

    No app token: this runs a handful of times in the life of the project, well inside
    the anonymous throttle, and a token would be a fourth secret to manage for no gain
    (§8's secrets boundary — every key this project holds has a reason).
    """
    url = f"{base}/resource/{dataset}.json?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:  # pragma: no cover - network path
        raise SystemExit(f"{dataset}: HTTP {error.code} for {url}\n{error.read()[:400]}")


def _paged(base: str, dataset: str, **params: str) -> Iterator[dict]:
    """Every row of a query, page by page.

    Ordered by a stable key, because Socrata does not guarantee a paging order without
    one and an unordered `$offset` walk can repeat and skip rows.
    """
    offset = 0
    while True:
        page = _get(base, dataset, **params, **{"$limit": str(_PAGE), "$offset": str(offset)})
        yield from page
        if len(page) < _PAGE:
            return
        offset += _PAGE


def _clean_zip(value: Any) -> Optional[str]:
    """Five digits, or nothing.

    Both portals emit placeholder ZIPs (`0`, empty, occasionally a nine-digit ZIP+4),
    and a benchmark keyed on a placeholder would be a median over unrelated properties
    that looks exactly like a real one.
    """
    text = str(value or "").strip()
    if len(text) > 5 and text[:5].isdigit():
        text = text[:5]
    return text if len(text) == 5 and text.isdigit() else None


def _median(prices: list[float]) -> float:
    return float(statistics.median(prices))


# ---------------------------------------------------------------------------
# New York
# ---------------------------------------------------------------------------


def new_york_sales_by_zip() -> dict[str, list[float]]:
    """Qualifying 2-4 unit residential sale prices in the five boroughs, grouped by ZIP.

    Aggregated client-side rather than with Socrata's `median()` so the sale count, the
    median and the price floor are all computed by the same code that does it for Cook —
    two markets whose numbers are compared in one report should not be produced by two
    different aggregations.

    **Returns the individual prices rather than the median** (U9.4). `main()` reduces
    them through `_summarize`, exactly as this function used to, and
    `scripts/sale_premium_distribution.py` needs the prices themselves — how far a single
    sale sits from its ZIP's median is a question a table of medians cannot answer. The
    filters are the load-bearing part and they now have one home: a second script
    restating this `$where` clause is two definitions of "a qualifying sale" that drift
    apart without either one looking wrong.
    """
    categories = ", ".join(f"'{c}'" for c in config.SALE_BENCHMARK_NYC_CATEGORIES)
    where = (
        f"sale_date >= '{config.SALE_BENCHMARK_WINDOW_START}' "
        f"AND sale_price >= {config.SALE_BENCHMARK_MIN_SALE_PRICE} "
        f"AND residential_units >= {config.SALE_BENCHMARK_MIN_UNITS} "
        f"AND residential_units <= {config.SALE_BENCHMARK_MAX_UNITS} "
        f"AND commercial_units = 0 "
        f"AND building_class_category in ({categories})"
    )
    by_zip: dict[str, list[float]] = defaultdict(list)
    rows = 0
    for row in _paged(
        config.SALE_BENCHMARK_SOURCES["new_york"]["portal"],
        config.SALE_BENCHMARK_SOURCES["new_york"]["sales_dataset"],
        **{"$select": "zip_code, sale_price", "$where": where, "$order": "sale_price"},
    ):
        rows += 1
        zip_code = _clean_zip(row.get("zip_code"))
        if zip_code:
            by_zip[zip_code].append(float(row["sale_price"]))

    print(f"  New York: {rows:,} qualifying sales across {len(by_zip)} ZIPs")
    return dict(by_zip)


# ---------------------------------------------------------------------------
# Chicago (Cook County)
# ---------------------------------------------------------------------------


def chicago_sales_by_zip() -> dict[str, list[float]]:
    """Qualifying class-211 sale prices grouped by ZIP, joined to the parcel universe.

    The join is on an exact `pin` — the assessor's own primary key, present in both
    datasets — so it either matches or it does not. Unmatched sales are reported rather
    than dropped silently, because a systematic join failure and a genuinely rare parcel
    look identical in the output otherwise.
    """
    source = config.SALE_BENCHMARK_SOURCES["chicago"]
    where = (
        f"class = '{config.SALE_BENCHMARK_COOK_CLASS}' "
        f"AND sale_date >= '{config.SALE_BENCHMARK_WINDOW_START}' "
        f"AND sale_price >= {config.SALE_BENCHMARK_MIN_SALE_PRICE} "
        f"AND is_multisale = false "
        f"AND sale_filter_deed_type = false "
        f"AND sale_filter_same_sale_within_365 = false "
        f"AND sale_filter_less_than_10k = false"
    )
    sales = [
        (str(row["pin"]), float(row["sale_price"]))
        for row in _paged(
            source["portal"],
            source["sales_dataset"],
            **{"$select": "pin, sale_price", "$where": where, "$order": "pin"},
        )
        if row.get("pin") and row.get("sale_price")
    ]

    zip_of_pin: dict[str, str] = {}
    for row in _paged(
        source["portal"],
        source["parcel_dataset"],
        **{
            "$select": "pin, zip_code",
            "$where": (
                f"class = '{config.SALE_BENCHMARK_COOK_CLASS}' "
                f"AND year = '{config.SALE_BENCHMARK_COOK_PARCEL_YEAR}'"
            ),
            "$order": "pin",
        },
    ):
        zip_code = _clean_zip(row.get("zip_code"))
        if zip_code and row.get("pin"):
            zip_of_pin[str(row["pin"])] = zip_code

    by_zip: dict[str, list[float]] = defaultdict(list)
    unmatched = 0
    for pin, price in sales:
        zip_code = zip_of_pin.get(pin)
        if zip_code is None:
            unmatched += 1
            continue
        by_zip[zip_code].append(price)

    matched = len(sales) - unmatched
    share = matched / len(sales) if sales else 0.0
    print(
        f"  Chicago: {len(sales):,} qualifying sales, {len(zip_of_pin):,} parcels in the "
        f"universe, {matched:,} joined ({share:.1%}), {unmatched:,} unmatched, "
        f"{len(by_zip)} ZIPs"
    )
    return dict(by_zip)


# ---------------------------------------------------------------------------


def _summarize(by_zip: dict[str, list[float]], market_key: str) -> dict[str, dict]:
    """One record per ZIP: the median, the count behind it, and which market it is.

    **Every ZIP is kept, including the thin ones**, and the count travels with the
    median so the consumer applies `config.SALE_BENCHMARK_MIN_SALES` rather than this
    script baking a floor into the artifact. A floor changed later would otherwise mean
    rebuilding the table from the network to find out what it would have done.
    """
    return {
        zip_code: {
            "median_sale_price": round(_median(prices), 2),
            "n_sales": len(prices),
            "market": market_key,
        }
        for zip_code, prices in sorted(by_zip.items())
    }


def _distribution(records: dict[str, dict]) -> str:
    """What the sample sizes look like, so `SALE_BENCHMARK_MIN_SALES` is set on evidence.

    Printed rather than stored: it is an input to a threshold decision, and the decision
    itself belongs in `config.py` with its reasoning.
    """
    counts = sorted(r["n_sales"] for r in records.values())
    if not counts:
        return "  (no ZIPs)"
    quantiles = [
        f"min {counts[0]}",
        f"p10 {counts[len(counts) // 10]}",
        f"median {counts[len(counts) // 2]}",
        f"max {counts[-1]}",
    ]
    for floor in (10, 20, 30, 50):
        kept = sum(1 for c in counts if c >= floor)
        quantiles.append(f"≥{floor}: {kept}/{len(counts)}")
    return "  " + " · ".join(quantiles)


# The one place a market key is bound to the fetcher that pulls it. Read by
# `scripts/sale_premium_distribution.py` too, so a market added here reaches both the
# committed table and the dispersion measurement without a second registration.
_MARKET_FETCHERS = {
    "new_york": new_york_sales_by_zip,
    "chicago": chicago_sales_by_zip,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pull and measure, write nothing. Use when checking whether the sources moved.",
    )
    args = parser.parse_args()

    print(f"Window: sales on or after {config.SALE_BENCHMARK_WINDOW_START}")
    records: dict[str, dict] = {}
    for market_key, builder in _MARKET_FETCHERS.items():
        built = _summarize(builder(), market_key)
        print(_distribution(built))
        overlap = set(built) & set(records)
        if overlap:
            # Two markets claiming one ZIP would mean a filter is wrong; ZIPs do not
            # span Cook County and New York City.
            raise SystemExit(f"ZIP claimed by two markets: {sorted(overlap)[:5]}")
        records.update(built)

    payload = {
        "built_at": date.today().isoformat(),
        "window_start": config.SALE_BENCHMARK_WINDOW_START,
        "markets": {
            key: {
                "label": source["label"],
                "attribution": source["attribution"],
                "definition": source["definition"],
            }
            for key, source in config.SALE_BENCHMARK_SOURCES.items()
        },
        "zips": records,
    }

    if args.dry_run:
        print(f"\n--dry-run: {len(records)} ZIPs built, nothing written")
        return

    config.SALE_BENCHMARK_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.SALE_BENCHMARK_PATH.write_text(json.dumps(payload, indent=1, sort_keys=True))
    size_kb = config.SALE_BENCHMARK_PATH.stat().st_size / 1024
    print(f"\nwrote {len(records)} ZIPs -> {config.SALE_BENCHMARK_PATH} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
