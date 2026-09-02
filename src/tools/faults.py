"""Declared fault injection — one implementation, every consumer.

Three simulated external failures, each existing because **no real input can reach the
path it covers.** A model outage, a geocoder outage and a stale market index are all
conditions this system is built to disclose rather than absorb, and none of them can be
produced on demand: the services are up, and the committed rent panel is current.

**Why this is its own module (U9.7a).** The injection logic lived inside
`eval/runner._case_environment`, keyed off an `EvalCase`. U9.7's demo surface needs the
same three faults against a `DemoDeal`, and `main.py` needs them to *record* the
combinations that surface replays. Reimplementing them for the second caller is the
defect `tools/hud_fmr.bedroom_field` already names in its own docstring — a rule applied
at a second call site becomes "a training set capped differently from the inference
path", silent in both directions. A fault that behaved differently in the demo than in
the evaluation would invalidate both at once, and neither would say so.

So the enum and the mechanism live together here, in `tools/`, below both consumers.
`eval/cases.py` imports `Fault` from this module; nothing in `tools/` imports from
`eval/`, which is the layering that made the move worth doing rather than merely tidy.

**Declared, never hidden — and that is the whole design.** The injection appears in the
case definition or the CLI flag, in the results table, and in the text of the flag it
produces. A reader can see the row exercised a *simulated* outage. A harness that patched
a module inside a fixture would produce the identical row and let it read as a
naturally-occurring failure, which is the same class of overstatement `eval.cases.
VerdictSource` exists to prevent one column over.

**Every patch enters through the same door a real failure would.** `geocode_census`
raises, and `geocoding.geocode()` catches it and sets `primary_unavailable` — so the
Extractor still *decides* between `GEOCODER_SERVICE_UNAVAILABLE` and
`COORDINATES_FROM_CITY_CENTROID` rather than having the outcome asserted for it. Nothing
here forces a flag directly. That is the difference between testing a branch and
asserting its result.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import StrEnum
from typing import Iterator, Optional

from tools import geocoding, zori
from tools.llm_client import LlmClient, LlmError


class Fault(StrEnum):
    """An external failure a run asks the system to simulate. **Declared, never hidden.**

    Added U8.2, for one kind the batch could not otherwise reach at all.
    `FlagKind.REWORK_LIMIT_REACHED` needs an objection the Critic marks `retryable`, and
    exactly one objection is ever marked so: the I3 branch in
    `agents/critic._interaction_objections`, gated on `GEOCODER_SERVICE_UNAVAILABLE`. That
    flag is raised only when the Census *request itself fails*
    (`tools/geocoding.geocode`) — not when it runs and finds no match, which is the
    distinction U7.1b built precisely so the rework cycle could be spent on an outage and
    not on an address that will never resolve.

    Neither tier can produce that. A golden fixture supplies coordinates, so U8.1b's
    geography path takes the county-only branch and never calls the geocoder; a replay case
    calls it and it succeeds, because `LLM_CACHE_MODE=replay` covers *model* calls and the
    Census lookup is an ordinary HTTP request. So the outage can be injected or it can go
    unexercised, and leaving the system's only bounded-retry path untested through the unit
    that tunes `MAX_REWORKS` is the worse of the two.

    **`LLM_UNAVAILABLE`, added U8.3, for the same class of reason.**
    `FlagKind.EXTRACTION_UNAVAILABLE` is raised when `agents.extractor._extract_terms`
    never receives a response at all — `tools.llm_client.LlmClient.complete` raises
    `LlmError` before there is anything to validate, let alone record. A recording is a
    replay of a *response*; there is no response here to replay, so the two mechanisms
    that cover every other extraction flag (a real listing, a recorded call) both come up
    empty for this one, which is exactly this enum's admission criterion.

    Patched one layer above the raw transport call, same as `GEOCODER_OUTAGE`:
    `LlmClient.complete` is the primary call (`geocode_census`'s analogue), so the
    Extractor's own `except LlmError` branch still does the deciding. The patch is
    class-level rather than per-instance because `_extract_terms` builds a fresh
    `LlmClient()` per call and there is no instance to reach beforehand.

    Left unrestricted rather than expired after one call: `agents.scenario_forecast` also
    builds an `LlmClient` and would hit the same patched method later in the same run.
    That is not a leak to guard against — it is the honest consequence of the model
    actually being down. `scenario_forecast` already catches `LlmError` and raises its own
    `FORECAST_UNAVAILABLE`, so the run shows a real, gracefully-degraded multi-flag outage
    rather than a run that dies partway through.

    **One property `LLM_UNAVAILABLE` has that the other two do not, measured at U9.7a and
    load-bearing for the demo surface:** it patches `LlmClient.complete`, which is where
    the response cache is consulted, so the patch sits *above* the cache and no lookup
    ever happens. It therefore behaves identically under `replay` and live, and needs no
    recording of its own. The other two change state that reaches the forecast prompt, so
    a replayed run under either of them raises `CacheMiss` unless that exact combination
    was recorded.
    """

    GEOCODER_OUTAGE = "geocoder_outage"
    LLM_UNAVAILABLE = "llm_unavailable"
    # **`STALE_RENT_INDEX`, added U11.3, for the same reason as the two above: no listing
    # can reach this path.** `RENT_ANCHOR_INDEX_STALE` fires when the market-rent index
    # the estimate is anchored to has not been observed for
    # `config.RENT_ANCHOR_MAX_STALENESS_MONTHS`, which is a property of the *data file* on
    # the machine, not of any property. Today's panel is one month old, so no fixture and
    # no recording can raise it — and a kind nothing can raise corrupts the coverage
    # census, which is the rule `state.FlagKind` already set when it retired
    # `LLM_RENT_FALLBACK_USED`. Patched at `zori.latest_month`, one layer above the file,
    # so the pipeline's own staleness arithmetic does the deciding rather than a directly
    # forced flag.
    STALE_RENT_INDEX = "stale_rent_index"


# The month `Fault.STALE_RENT_INDEX` pins the market index to. Chosen to sit well past
# `config.RENT_ANCHOR_MAX_STALENESS_MONTHS` so refreshing the committed panel cannot
# quietly stop the fault from firing.
STALE_INDEX_MONTH = "2023-01-31"


def _marker(declared_by: str) -> str:
    """The prefix every simulated failure carries into the text it produces.

    **Reader-facing, and deliberately so.** This string reaches a `Flag.detail` and is
    rendered verbatim in the report (`agents/extractor.py`'s `EXTRACTION_UNAVAILABLE`
    embeds the exception text), so a person reading a degraded report can tell a
    demonstration from an incident. §8 forbids internal vocabulary in exactly this
    position, which is why it no longer says "eval fault injection, case" — the demo
    surface runs these against a listing, not a case, and there is no evaluation involved.

    **It reaches no model prompt, which was checked rather than assumed** (U9.7a).
    `scenario_forecast._context_block` quotes flag *kinds* only, and
    `summarizer._lede_prompt` quotes severity *counts* only — no disclosure text reaches
    either. Verified empirically by re-deriving the full batch after this wording changed:
    no `CacheMiss`, and `results.md` byte-identical. Had it reached a prompt, the wording
    would have been frozen and this docstring would say so instead.
    """
    return f"[simulated failure, declared by {declared_by!r} — not a real outage]"


@contextmanager
def injected(
    fault: Optional[Fault],
    *,
    declared_by: str,
    geocoder_fallback_override: Optional[tuple[float, float]] = None,
) -> Iterator[None]:
    """Apply one declared fault for the duration of the block, then unwind it.

    `declared_by` names whoever asked for the simulation — an eval case key, or a demo
    deal key from `main.py --fault`. It appears in the text the fault produces, so the
    report says *who* declared it rather than only that something was declared.

    **Unwinding in `finally` rather than after the call is the point.** Every patch here
    is process-global, so an exception mid-run would otherwise leave everything after it
    executing under some earlier run's conditions — and those runs would not say so,
    because they would look perfectly ordinary. That mattered for a batch of eval rows
    first; it matters more for a long-lived Streamlit process, where "everything after it"
    is the rest of the session rather than the rest of the batch.

    `geocoder_fallback_override` is meaningful only alongside `GEOCODER_OUTAGE` and is
    OQ-16's answer: it forces the centroid fallback to land at a chosen point instead of
    the real corpus-wide city average, because that average never both diverges from the
    rent estimate and stays clear of a third warn or a critical (U8.2's grid search). Only
    *where* the fallback lands is forced — the mechanism deciding whether the fallback is
    worth retrying is untouched.
    """
    previous_geocode_census = geocoding.geocode_census
    previous_city_centroid = geocoding.city_centroid
    previous_llm_complete = LlmClient.complete
    previous_latest_month = zori.latest_month

    if fault is Fault.GEOCODER_OUTAGE:
        def _unreachable(*args, **kwargs):
            raise geocoding.GeocodingError(
                f"{_marker(declared_by)} the Census Geocoder was made unreachable for "
                f"this run."
            )

        # Patched at `tools.geocoding`, which is where `geocode()` looks the name up, so
        # the failure enters through the same door a real outage would: `geocode()`
        # catches `GeocodingError`, sets `primary_unavailable`, and the Extractor raises
        # `GEOCODER_SERVICE_UNAVAILABLE` rather than `COORDINATES_FROM_CITY_CENTROID`.
        # Patching the flag in directly would have skipped the distinction this exists
        # to exercise.
        geocoding.geocode_census = _unreachable

        if geocoder_fallback_override is not None:
            lat, lon = geocoder_fallback_override

            def _forced_centroid(city, state, primary_unavailable=False):
                return geocoding.GeocodeResult(
                    latitude=lat,
                    longitude=lon,
                    matched_address=(
                        f"{_marker(declared_by)} centroid fallback forced to "
                        f"({lat:.5f}, {lon:.5f})"
                    ),
                    source=geocoding.GeocodeSource.CITY_CENTROID,
                    primary_unavailable=primary_unavailable,
                )

            # Same shape as the real function — a `GeocodeResult` with
            # `source=CITY_CENTROID` — so the Extractor's own branch on `.source` and
            # `.primary_unavailable` still makes the outage-vs-unresolvable decision.
            geocoding.city_centroid = _forced_centroid

    if fault is Fault.STALE_RENT_INDEX:
        zori.latest_month = lambda panel: STALE_INDEX_MONTH

    if fault is Fault.LLM_UNAVAILABLE:
        def _unreachable_complete(*args, **kwargs):
            raise LlmError(
                f"{_marker(declared_by)} the model was made unreachable for this run."
            )

        # Patched at the class, not an instance: `_extract_terms` and
        # `scenario_forecast._make_scorer` each build their own `LlmClient`, so there is
        # no shared instance to patch. `self.complete(...)` resolves through the class
        # either way, so every instance created for the rest of this run sees the fault —
        # including scenario_forecast's later calls, which is the honest behaviour of a
        # model that is actually down (see `Fault.LLM_UNAVAILABLE`).
        LlmClient.complete = _unreachable_complete

    try:
        yield
    finally:
        geocoding.geocode_census = previous_geocode_census
        geocoding.city_centroid = previous_city_centroid
        LlmClient.complete = previous_llm_complete
        zori.latest_month = previous_latest_month
