"""Entrypoint — run the full pipeline on one listing.

    .venv/bin/python main.py                      # dense market, clean run
    .venv/bin/python main.py --deal chicago       # moderate: retrieval relaxes once
    .venv/bin/python main.py --deal staten-island # thin: escalates to human review
    .venv/bin/python main.py --deal no-coords     # the geocoding gap, end to end
    .venv/bin/python main.py --file listing.txt --coords 34.0522,-118.2437
    .venv/bin/python main.py --deal chicago --no-retrieval   # the U4 ablation

The four built-in deals are the same density cases `scripts/retrieval_evidence.py`
measures, reused here so the skeleton's end-to-end behaviour can be compared against
the retrieval evidence directly rather than against a separate set of inputs.

**Coordinates are supplied alongside the listing text, not extracted from it.** Nothing
in this system geocodes an address yet — see the `TODO(U3)` in `agents/extractor.py`
and decision #10 in §7. `--deal no-coords` runs the same Los Angeles deal with them
withheld, which is the honest demonstration of what that gap costs: retrieval cannot
run at all, a critical flag is raised, confidence collapses, and the deal escalates.
That path is worth having in the demo set rather than hidden behind a fixture.

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
from graph import build_graph, state_serde
from state import DealState, DealTerms
from tools.tracing import configure_tracing

CHECKPOINT_DB = config.DATA_DIR / "processed" / "checkpoints.sqlite"

# Synthetic listings, per the program's requirement that no real listing data enter this
# repository. The coordinates are real locations; the deals are invented.
DEMO_DEALS: dict[str, tuple[str, tuple[float, float] | None]] = {
    "los-angeles": (
        "For sale: 1234 Sunset Ridge Ave, Los Angeles, CA 90026. Charming 2-unit "
        "duplex in Echo Park, each unit 2 bed / 1 bath, approx 950 sq ft per unit. "
        "Renovated kitchens, in-unit laundry, off-street parking. Asking $1,150,000.",
        (34.0522, -118.2437),
    ),
    "chicago": (
        "For sale: 2500 N Kedzie Blvd, Chicago, IL 60647. Classic Logan Square 2-flat, "
        "2 bed / 1 bath per unit, approx 950 sq ft each. Original woodwork, full "
        "basement, two-car garage. Asking $525,000.",
        (41.9227, -87.6982),
    ),
    "staten-island": (
        "For sale: 100 Amboy Rd, Staten Island, NY 10307. Tottenville 3-unit building, "
        "2 bed / 1 bath units, approx 900 sq ft each. Deep lot, needs updating. "
        "Asking $875,000.",
        (40.5083, -74.2500),
    ),
    # Same deal as los-angeles, coordinates withheld — see the module docstring.
    "no-coords": (
        "For sale: 1234 Sunset Ridge Ave, Los Angeles, CA 90026. Charming 2-unit "
        "duplex in Echo Park, each unit 2 bed / 1 bath, approx 950 sq ft per unit. "
        "Asking $1,150,000.",
        None,
    ),
}


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


def run(listing_text: str, coords: tuple[float, float] | None, thread_id: str) -> str:
    """Run one deal end to end and return the rendered report."""
    configure_tracing()

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
    parser.add_argument("--coords", help="'LAT,LON' for --file; see the geocoding note")
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
        listing_text, coords = DEMO_DEALS[args.deal]
        label = args.deal

    thread_id = args.thread_id or f"{label}-{uuid4().hex[:8]}"

    print(f"Running deal '{label}' (retrieval "
          f"{'ON' if config.RETRIEVAL_ENABLED else 'OFF'}, thread '{thread_id}')")
    report = run(listing_text, coords, thread_id=thread_id)
    print("\n" + report)


if __name__ == "__main__":
    main()
