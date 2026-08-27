"""Entrypoint — run the full pipeline on one listing.

    .venv/bin/python main.py                       # dense market, clean run
    .venv/bin/python main.py --deal chicago        # moderate: retrieval relaxes once
    .venv/bin/python main.py --deal staten-island  # thin: escalates to human review
    .venv/bin/python main.py --deal no-geography   # unresolvable address, end to end
    .venv/bin/python main.py --deal coord-conflict # supplied coords vs. the address
    .venv/bin/python main.py --deal overpriced     # asking price 55% over the benchmark
    .venv/bin/python main.py --file listing.txt --coords 34.0522,-118.2437
    .venv/bin/python main.py --deal chicago --no-retrieval   # the U4 ablation

The three market deals are the same density cases `scripts/retrieval_evidence.py`
measures, reused here so end-to-end behaviour can be compared against the retrieval
evidence directly rather than against a separate set of inputs.

**Coordinates are derived from the listing, not supplied alongside it (U3).** The
Extractor calls `tools/geocoding.py` as an ordinary step, so a listing arriving as text
now reaches comp retrieval on its own — which was the point of closing decision #10.
Two consequences visible here:

- The demo listings carry **real street addresses**, because an invented one resolves to
  no parcel and falls back to the city centroid, raising a geography flag on every run.
  Deal terms — price, rents, unit mix — remain entirely invented, as does the premise
  that any of these properties is for sale. Only the address is real, and only so that
  the geocoder has something to resolve.
- `--deal no-coords` is retired and replaced by `--deal no-geography`, which reaches the
  same degraded state through a real failure rather than a withheld input: an address
  neither the Census geocoder nor the corpus centroid can place. Verified to resolve to
  nothing through both tiers. That is a stronger demonstration than withholding
  coordinates was, because nothing about it depends on the caller cooperating.

`--coords` still exists, and now means something different: supplied coordinates are
checked against the geocode of the listing's own address rather than trusted. `--deal
coord-conflict` demonstrates that path — see `agents/extractor.py._resolve_geography`
for why the disagreement escalates instead of being resolved.

**Interrupt handling.** A deal that escalates pauses at `human_review` and `invoke`
returns an `__interrupt__` payload instead of a finished state. This script prints what
was surfaced to the reviewer and then resumes with a canned note so the demo produces a
complete report in one command. A real caller would wait for an actual human between
those two steps; the pause is genuine either way, and the second `invoke` resumes from
the checkpoint rather than re-running the pipeline.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

import config
from demo_deals import DEMO_DEALS
from graph import build_graph, state_serde
from state import DealState, DealTerms
from tools.llm_client import LlmError, verify_models_live
from tools.tracing import configure_tracing

CHECKPOINT_DB = config.DATA_DIR / "processed" / "checkpoints.sqlite"

# The synthetic listings, their supplied coordinates, and the provenance of every figure
# in them, all live in `demo_deals.py` — see that module for what is real (addresses, and
# the market data each price and rent is anchored to) and what is invented (everything
# else, including the premise that any of these properties is for sale).
# `scripts/verify_demo_calibration.py` re-derives each figure from its live source.


def _initial_state(listing_text: str, coords: tuple[float, float] | None) -> DealState:
    terms = DealTerms()
    if coords is not None:
        terms.latitude, terms.longitude = coords
    return DealState(raw_listing_text=listing_text, deal_terms=terms)


def _parse_coords(raw: str | None) -> tuple[float, float] | None:
    if not raw:
        return None
    try:
        lat, lon = (float(part) for part in raw.split(","))
    except ValueError:
        raise SystemExit(f"--coords expects 'LAT,LON', got {raw!r}")
    return lat, lon


def _print_interrupt(payload) -> None:
    print("\n" + "=" * 78)
    print("PAUSED — escalated to human review")
    print("=" * 78)
    print(json.dumps(payload, indent=2, default=str))
    print("=" * 78)


def _check_models() -> None:
    """Fail at launch on a dead model ID rather than partway through a run.

    Decision #8's durable lesson: the previous four model IDs were valid when written and
    dead six days later. Discovering that after a geocode and a Chroma query have already
    run wastes the work and reports the failure at the wrong layer. Raised as `SystemExit`
    rather than a traceback because the message is the whole point — it names the missing
    model and lists the free ones currently available.
    """
    try:
        verified = verify_models_live()
    except LlmError as exc:
        # `available_models` has already logged the underlying cause in full; this keeps
        # the exit message short and actionable rather than making it carry both jobs.
        raise SystemExit(f"Model check failed: {exc}")
    print(f"Model check OK — {', '.join(sorted(verified))}")


def run(listing_text: str, coords: tuple[float, float] | None, thread_id: str) -> str:
    """Run one deal end to end and return the rendered report."""
    configure_tracing()
    _check_models()

    invoke_config = {"configurable": {"thread_id": thread_id}}

    CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
    # `closing`, because sqlite3's own context manager commits on exit but does not
    # close the connection.
    with closing(sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)) as connection:
        # Constructed directly rather than via `SqliteSaver.from_conn_string` because
        # that helper takes no serializer, and this run needs the state-type allowlist
        # from `graph.state_serde()` — see its docstring.
        checkpointer = SqliteSaver(connection, serde=state_serde())
        graph = build_graph(checkpointer=checkpointer)
        result = graph.invoke(_initial_state(listing_text, coords), invoke_config)

        if "__interrupt__" in result:
            _print_interrupt(result["__interrupt__"][0].value)
            result = graph.invoke(
                Command(
                    resume=(
                        "[demo] Reviewed and released for reporting. A real reviewer "
                        "would resolve the disclosures above before proceeding."
                    )
                ),
                invoke_config,
            )

    return result["report_markdown"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--deal",
        choices=sorted(DEMO_DEALS),
        default="los-angeles",
        help="which built-in synthetic deal to run (default: los-angeles)",
    )
    parser.add_argument("--file", type=Path, help="run a listing from a text file instead")
    parser.add_argument(
        "--coords",
        help=(
            "'LAT,LON' to supply coordinates for --file. Checked against the geocode of "
            "the listing's own address rather than trusted; a disagreement beyond "
            "config.COORDINATE_CONFLICT_THRESHOLD_MILES escalates to human review."
        ),
    )
    parser.add_argument(
        "--no-retrieval",
        action="store_true",
        help="the U4 ablation: run with RETRIEVAL_ENABLED off, ungrounded",
    )
    parser.add_argument(
        "--thread-id",
        help=(
            "checkpointer thread id. Defaults to a fresh random id per run, because "
            "reusing one resumes that thread from wherever it stopped rather than "
            "starting the deal over. Pass an explicit id to resume a paused run."
        ),
    )
    args = parser.parse_args()

    if args.no_retrieval:
        # Mutated here rather than read from an env var so the ablation stays a single
        # documented switch (§6) rather than two ways of expressing the same thing.
        config.RETRIEVAL_ENABLED = False

    if args.file:
        listing_text = args.file.read_text()
        coords = _parse_coords(args.coords)
        label = args.file.name
    else:
        deal = DEMO_DEALS[args.deal]
        listing_text, coords = deal.listing, deal.supplied_coords
        label = args.deal

    thread_id = args.thread_id or f"{label}-{uuid4().hex[:8]}"

    print(f"Running deal '{label}' (retrieval "
          f"{'ON' if config.RETRIEVAL_ENABLED else 'OFF'}, thread '{thread_id}')")
    report = run(listing_text, coords, thread_id=thread_id)
    print("\n" + report)


if __name__ == "__main__":
    main()
