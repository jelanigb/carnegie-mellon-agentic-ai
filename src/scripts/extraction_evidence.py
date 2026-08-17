"""U3 evidence — the Extractor against live models, on listings built to stress it.

    .venv/bin/python scripts/extraction_evidence.py                     # configured model
    .venv/bin/python scripts/extraction_evidence.py --bakeoff           # every candidate
    .venv/bin/python scripts/extraction_evidence.py --bakeoff --tier free

Two artifacts from one set of inputs, because they need the same runs:

1. **Loop 1 behaviour (Checkpoint 2.1).** Three synthetic listings, each engineered so a
   different branch of the extraction loop is the one that fires: a complete listing that
   should raise nothing, one that states its unit count only as a term of art (the
   assumption branch), and one missing a required field outright (the clarifying-question
   branch). Printed per listing: what was extracted, what was assumed and on what basis,
   which questions were raised, and how many model attempts it cost.

2. **Decision #8 (§7), which this script closed.** `--bakeoff` runs the same three
   listings across every candidate in the live catalogue that this project would
   consider, and reports schema-validity, attempts consumed, rate-limited calls,
   wall-clock time, and per-field agreement against hand-checked expected values. §7
   deferred the model choice to U3 on the grounds that "choosing well needs real
   extraction output to judge against"; this is that output.

   **`--tier` defaults to paid, and that is a finding rather than a convenience.** The
   first two passes ran against `:free` variants and measured the wrong thing: those are
   served from provider-shared pools, so models lost whole listings to 429s and *which*
   ones failed moved between passes. `--tier free` is kept so that result stays
   reproducible. Two mechanisms now stop availability contaminating capability — 429s are
   backed off and counted separately (see `RATE_LIMIT_BACKOFF_SECONDS`), and this section
   runs with the response cache **off**, since replaying a recording would report its
   latency and success as though they were today's.

**What these checks could have returned had the system been behaving well** (§8). The
accuracy column compares against expected values written *before* any model was run, and
they are values a careful human reads straight off the listing text — so a model scoring
poorly here is failing at transcription, not at judgement. The assumption check is the
one that can fail in both directions and is reported that way: a model that flags nothing
scores no assumption credit, and so does a model that flags a value the listing stated
outright. A run where every model scored 100% on every column would be evidence the
listings are too easy to discriminate between models, not evidence that all models are
equally good — listing C exists partly to make that unlikely.

**Geography is deliberately out of scope here.** These listings are checked for
extraction quality only; `scripts/pull_geocode_sample.py` and
`scripts/verify_county_geometry.py` already verify the geocoding and county tiers
against live services, and re-verifying them here would spend API calls to re-answer a
settled question.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents import extractor
from tools import diagnostics
from tools.llm_cache import ResponseCache
from tools.llm_client import LlmClient, LlmError, SchemaValidationExhausted, available_models

# Candidates are resolved against the live catalogue at run time rather than pinned here,
# which is the same staleness lesson decision #8 recorded: a list of model IDs written
# into a file is a list that goes wrong quietly. These prefixes select the families worth
# considering for structured extraction; anything free matching one and present in the
# catalogue gets run.
BAKEOFF_PREFIXES = ("openai/", "google/gemma", "nvidia/nemotron-3", "cohere/")

# Models excluded on capability grounds rather than performance: these are built for
# tasks other than instruction-following extraction, so including them would pad the
# table with predictable failures and spend budget doing it.
BAKEOFF_EXCLUDE = ("content-safety", "-vl", "-omni", "-code", "note-preview")

# Backoff between rate-limited retries, in seconds. Longer than the OpenAI SDK's own
# retry (which `config.LLM_MAX_RETRIES` already sets to 3 and which fires first), because
# the failures this is for were not momentary: a provider's shared pool stayed busy
# across a whole bake-off pass. Applied only to 429s — see `run_case`.
RATE_LIMIT_BACKOFF_SECONDS = (5, 15, 30)


@dataclass
class Case:
    """A listing plus what a careful human reads off it.

    `expected` holds only fields the listing states or clearly implies. A field the
    listing genuinely omits is absent from this dict rather than mapped to `None`, so
    the accuracy score never rewards a model for leaving something blank that it had no
    way to fill — that is measured separately, by the required-field questions.
    """

    key: str
    what_it_tests: str
    listing: str
    expected: dict[str, Any]
    expects_assumption_on: Optional[str] = None
    expects_questions_about: list[str] = field(default_factory=list)


CASES: list[Case] = [
    Case(
        key="A — complete",
        what_it_tests=(
            "The clean path. Everything required is stated plainly, so a correct "
            "extraction raises no flags at all. This is the case that gives the other "
            "two their meaning: without it, a system that flagged everything would "
            "score identically to one that flagged the right things."
        ),
        listing=(
            "For sale: 2500 N Kedzie Blvd, Chicago, IL 60647. Three-unit building in "
            "Logan Square. Each unit is 2 bedrooms, 1 bathroom, approximately 950 "
            "square feet. Current tenants pay $1,850, $1,795, and $1,900 per month. "
            "Original woodwork, full basement, two-car garage. Asking $525,000."
        ),
        expected={
            "price": 525_000.0,
            "unit_count": 3,
            "bedrooms": 2,
            "bathrooms": 1.0,
            "square_footage": 950.0,
            "city": "Chicago",
            "state": "IL",
            "zip_code": "60647",
            "unit_rents": [1850.0, 1795.0, 1900.0],
        },
    ),
    Case(
        key="B — term of art",
        what_it_tests=(
            "The assumption branch. The unit count is never stated as a number — "
            "'duplex' names a building type that means two units. A model that leaves "
            "unit_count null discards information the listing really carries; one that "
            "fills it without flagging presents an inference as an observation. Only "
            "filling it AND recording the basis is correct. Contrast case A, which "
            "writes its count out as 'three-unit': that is stated, and flagging it "
            "would be the opposite error."
        ),
        listing=(
            "For sale: 1425 W Sunset Blvd, Los Angeles, CA 90026. Classic Echo Park "
            "duplex, fully renovated. Each unit offers 2 bedrooms and 1 bathroom across "
            "roughly 900 square feet. In-unit laundry, off-street parking for two cars. "
            "Asking $1,150,000."
        ),
        expected={
            "price": 1_150_000.0,
            "unit_count": 2,
            "bedrooms": 2,
            "bathrooms": 1.0,
            "square_footage": 900.0,
            "city": "Los Angeles",
            "state": "CA",
            "zip_code": "90026",
        },
        expects_assumption_on="unit_count",
    ),
    Case(
        key="C — missing and ambiguous",
        what_it_tests=(
            "The clarifying-question branch, plus the per-unit trap. No price is given, "
            "so a required field is unresolvable. The bedroom count is stated as a "
            "building total ('7 bedrooms across the building') with no per-unit "
            "breakdown, so a model that reports bedrooms=7 has silently changed the "
            "unit of measure the comp search runs on — the failure this case exists to "
            "detect. Correct behaviour is null plus a question."
        ),
        listing=(
            "For sale: 7001 Amboy Rd, Staten Island, NY 10307. Tottenville three-family "
            "home on a deep lot, 7 bedrooms across the building and 3 full bathrooms. "
            "Approximately 2,700 square feet in total. Needs updating throughout. "
            "Price on application — contact listing agent."
        ),
        expected={
            "unit_count": 3,
            "city": "Staten Island",
            "state": "NY",
            "zip_code": "10307",
            "price": None,
            "bedrooms": None,
        },
        expects_questions_about=["price"],
    ),
]


def _field_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        return sorted(actual or []) == sorted(expected)
    if isinstance(expected, float) and isinstance(actual, (int, float)):
        return abs(float(actual) - expected) < 0.01
    if isinstance(expected, str) and isinstance(actual, str):
        return actual.strip().lower() == expected.strip().lower()
    return actual == expected


def score(case: Case, result: extractor.ListingExtraction) -> tuple[int, int, list[str]]:
    """Fields correct, fields checked, and the names of the ones that were wrong."""
    wrong = []
    for name, expected in case.expected.items():
        if not _field_matches(expected, getattr(result, name)):
            wrong.append(f"{name}={getattr(result, name)!r} (want {expected!r})")
    return len(case.expected) - len(wrong), len(case.expected), wrong


def assumption_verdict(case: Case, result: extractor.ListingExtraction) -> str:
    """Scored in both directions — see the module docstring."""
    named = {a.field for a in result.assumptions}
    if case.expects_assumption_on:
        if case.expects_assumption_on in named:
            return "correct"
        return f"MISSED ({case.expects_assumption_on})"
    return "correct" if not named else f"SPURIOUS ({sorted(named)})"


@dataclass
class Attempt:
    """One model's outcome on one listing.

    `status` distinguishes the two ways a model can produce nothing, and the distinction
    is the point: "returned unusable JSON three times" is a capability finding about the
    model, while "429" is an availability finding about the tier it was served from.
    Reporting both as FAIL hid that `google/gemma-4-31b-it:free` scored zero on the free
    tier for a reason that says nothing about how well it extracts.

    `rate_limit_hits` keeps that separation quantitative rather than merely categorical.
    A model that succeeded only after backing off twice is not equivalent to one that
    answered immediately, even though both end up in the `ok` column.
    """

    extraction: Optional[extractor.ListingExtraction]
    attempts: int
    status: str
    seconds: float
    rate_limit_hits: int = 0


def run_case(case: Case, model: str, cache_mode: Optional[str] = None) -> Attempt:
    """Run one listing against one model.

    `cache_mode` defaults to whatever `config.LLM_CACHE_MODE` says, which is what the
    loop-behaviour section wants: those runs are evidence of *this system's* extraction
    behaviour, they benefit from being fast to re-run, and recording them is how the
    replayable fixtures in `src/eval/data/` get made.

    The bake-off passes `"off"` explicitly, because it is measuring something different —
    a provider's live latency and availability. A replayed response there would report
    the recording's properties as though they were today's, which is the one thing that
    comparison must not do.
    """
    client = LlmClient(
        cache=ResponseCache(config.LLM_CACHE_DIR, cache_mode or config.LLM_CACHE_MODE)
    )
    started = time.monotonic()
    rate_limit_hits = 0

    for attempt_number in range(len(RATE_LIMIT_BACKOFF_SECONDS) + 1):
        elapsed = lambda: time.monotonic() - started  # noqa: E731 — read at each return
        try:
            result, attempts = client.call_with_schema(
                prompt=extractor._EXTRACTION_PROMPT.format(listing_text=case.listing),
                schema=extractor.ListingExtraction,
                model=model,
                system=extractor._EXTRACTION_SYSTEM,
            )
            return Attempt(result, attempts, "ok", elapsed(), rate_limit_hits)

        except SchemaValidationExhausted as exc:
            # Not retried. The model answered; it just answered badly, and asking the
            # same question again is exactly what `call_with_schema` already did.
            diagnostics.log_exception(
                f"bakeoff[{model}] {case.key}: schema never validated", exc
            )
            return Attempt(None, exc.attempts, "schema-invalid", elapsed(), rate_limit_hits)

        except LlmError as exc:
            # Backoff applies to rate limits only. A 429 is the provider saying "later",
            # which is not information about whether this model can extract — scoring it
            # as a capability failure is what made the free-tier table unreadable. Any
            # other transport error is reported as-is, since retrying an auth failure or
            # a dead model just spends money slower.
            is_rate_limit = "429" in str(exc)
            retries_left = attempt_number < len(RATE_LIMIT_BACKOFF_SECONDS)
            if is_rate_limit and retries_left:
                delay = RATE_LIMIT_BACKOFF_SECONDS[attempt_number]
                rate_limit_hits += 1
                diagnostics.log_note(
                    f"bakeoff[{model}] {case.key}: rate limited",
                    f"backing off {delay}s (retry {attempt_number + 1} of "
                    f"{len(RATE_LIMIT_BACKOFF_SECONDS)})",
                )
                time.sleep(delay)
                continue

            diagnostics.log_exception(f"bakeoff[{model}] {case.key}: call failed", exc)
            if is_rate_limit:
                rate_limit_hits += 1
            # The table reduces this to a short code, which is right for a comparison
            # grid and useless for working out *which* 429 was hit — an account daily cap
            # and an upstream provider pool are different problems with different
            # remedies, and only the logged body distinguishes them.
            status = "429" if is_rate_limit else "unreachable"
            return Attempt(None, 0, status, elapsed(), rate_limit_hits)

        except Exception as exc:  # noqa: BLE001 — an unclassified provider fault is a result
            diagnostics.log_exception(
                f"bakeoff[{model}] {case.key}: unclassified failure", exc,
                include_traceback=True,
            )
            return Attempt(None, 0, type(exc).__name__, elapsed(), rate_limit_hits)

    # Unreachable: every branch above returns or continues, and the loop is bounded.
    raise AssertionError("bake-off retry loop exited without a result")


def report_loop_behaviour(model: str) -> None:
    """Artifact 1: what the extraction loop actually did, per listing."""
    print("=" * 78)
    print(f"LOOP 1 BEHAVIOUR — model: {model}")
    print("=" * 78)

    for case in CASES:
        print(f"\n--- {case.key} ---")
        print(f"Tests: {case.what_it_tests}\n")
        print(f"Listing:\n  {case.listing}\n")

        attempt = run_case(case, model)
        result = attempt.extraction
        if result is None:
            print(f"  EXTRACTION FAILED ({attempt.status}) — the pipeline would raise a "
                  f"critical flag and escalate.")
            continue

        correct, checked, wrong = score(case, result)
        print(f"  attempts: {attempt.attempts}   {attempt.seconds:.1f}s   "
              f"fields correct: {correct}/{checked}"
              f"   assumptions: {assumption_verdict(case, result)}")
        if wrong:
            for item in wrong:
                print(f"    WRONG: {item}")

        print(f"  extracted: price={result.price} units={result.unit_count} "
              f"beds={result.bedrooms} baths={result.bathrooms} "
              f"sqft={result.square_footage} rents={result.unit_rents}")
        print(f"             address={result.full_address!r}")
        for assumption in result.assumptions:
            print(f"  ASSUMED  {assumption.field}: {assumption.basis}")
        for question in result.clarifying_questions:
            print(f"  ASKS     {question}")
        if not result.assumptions and not result.clarifying_questions:
            print("  (no assumptions, no questions — the clean path)")


def bakeoff_models(tier: str) -> list[str]:
    """Candidates for the comparison, resolved against the live catalogue.

    The paid tier is derived from the free shortlist by dropping the `:free` suffix and
    keeping whatever the catalogue actually lists, rather than by selecting "everything
    not free" — that would sweep in hundreds of models and, more importantly, would stop
    the two tiers comparing the same families. The question being asked is whether a
    given model extracts well, not which vendor has the largest catalogue.
    """
    catalogue = available_models()
    if tier == "free":
        candidates = sorted(m for m in catalogue if m.endswith(":free"))
    else:
        paid_names = {m.removesuffix(":free") for m in catalogue if m.endswith(":free")}
        candidates = sorted(paid_names & catalogue)

    return [
        m
        for m in candidates
        if m.startswith(BAKEOFF_PREFIXES) and not any(x in m for x in BAKEOFF_EXCLUDE)
    ]


def report_bakeoff(tier: str) -> None:
    """Artifact 2: the comparison decision #8 needs."""
    models = bakeoff_models(tier)
    print("=" * 78)
    print(f"DECISION #8 BAKE-OFF — {tier} tier")
    print("=" * 78)
    print(f"Catalogue models matching {BAKEOFF_PREFIXES}, excluding {BAKEOFF_EXCLUDE}:")
    for model in models:
        print(f"  {model}")
    print(f"\nCache is off for this section (live measurement). Rate-limited calls back "
          f"off {RATE_LIMIT_BACKOFF_SECONDS} and are counted separately, so availability "
          f"and capability are not confounded.\n")

    header = (
        f"{'model':<40} {'valid':>6} {'tries':>6} {'429s':>5} {'secs':>7} "
        f"{'fields':>8} {'assumptions':>16}"
    )
    print(header)
    print("-" * len(header))

    for model in models:
        valid = 0
        total_attempts = 0
        total_seconds = 0.0
        total_429s = 0
        correct_total = 0
        checked_total = 0
        verdicts = []

        for case in CASES:
            attempt = run_case(case, model, cache_mode="off")
            total_attempts += attempt.attempts
            total_seconds += attempt.seconds
            total_429s += attempt.rate_limit_hits
            label = case.key.split()[0]
            if attempt.extraction is None:
                verdicts.append(f"{label}:{attempt.status}")
                continue
            valid += 1
            correct, checked, _ = score(case, attempt.extraction)
            correct_total += correct
            checked_total += checked
            verdict = assumption_verdict(case, attempt.extraction)
            verdicts.append(f"{label}:{'ok' if verdict == 'correct' else 'X'}")

        fields = f"{correct_total}/{checked_total}" if checked_total else "—"
        print(f"{model:<40} {valid:>3}/{len(CASES):<2} {total_attempts:>6} "
              f"{total_429s:>5} {total_seconds:>6.1f}s {fields:>8} "
              f"{' '.join(verdicts):>16}")

    print()
    print("Columns: `valid` = listings yielding schema-valid output; `tries` = model")
    print("calls consumed across all three (3 is the floor — higher means the schema")
    print("retry loop fired); `429s` = rate-limited calls that were backed off and")
    print("retried, an availability measure that no longer contaminates the others;")
    print("`secs` = wall-clock including backoff; `fields` = hand-checked field values")
    print("correct; `assumptions` = per listing, whether the assumption verdict was")
    print("right (a spurious flag scores X, same as a missed one).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--bakeoff",
        action="store_true",
        help="run every candidate model, not just the configured one (decision #8)",
    )
    parser.add_argument(
        "--tier",
        choices=("paid", "free"),
        default="paid",
        help=(
            "which variants the bake-off compares. Defaults to paid: the free tier's "
            "shared upstream pools make availability, not capability, the thing being "
            "measured. Keep `free` available so that finding stays reproducible."
        ),
    )
    parser.add_argument(
        "--model",
        default=config.MODEL_EXTRACTION,
        help=f"model for the loop-behaviour section (default: {config.MODEL_EXTRACTION})",
    )
    args = parser.parse_args()

    report_loop_behaviour(args.model)
    if args.bakeoff:
        print("\n")
        report_bakeoff(args.tier)


if __name__ == "__main__":
    main()
