"""Full-detail error logging, kept separate from what reaches a report.

Why this exists
---------------
U3 introduced a deliberate asymmetry: `llm_client._transport_failure` strips a provider
error down to its useful message before it becomes a flag, because flags are rendered
verbatim into reports and the raw body carries the calling account's `user_id`. That is
right for the report and wrong for debugging — the discarded detail (status metadata,
rate-limit headers, provider name, remedy hints) is exactly what a person diagnosing a
failure wants.

So the two audiences get different text from the same failure, on purpose:

- **The report** gets the sanitized summary. It is a published artifact.
- **stdout** gets everything, unabridged, through this module.

Nothing here decides *whether* to degrade — that stays with the agent, per §8. This only
makes sure that a caught exception is never the last anyone hears of it, which is the one
failure mode a `try/except` introduces for free.

Two properties worth stating
----------------------------
**Swallowed exceptions are the real target.** Sites that re-raise or embed `{exc}` in a
message already preserve their detail. The ones this module changes are those that
catch-and-continue: `geocoding.geocode` falling through to the centroid, the schema retry
loop absorbing a `ValidationError` before re-prompting, index teardown ignoring a missing
collection. Each of those was previously silent, and silence is what makes a degraded run
hard to explain after the fact.

**stdout, not stderr, and that is a choice with a cost.** Requested explicitly, and it
matches how the rest of this project reports (`print`, not `logging`). The cost is that
`main.py` also prints the finished report to stdout, so `python main.py > report.md`
captures diagnostics into the report file. Switching to stderr is the one-line change
below if that becomes the annoying half of the trade — the call sites do not change.

TODO(security): the full text intentionally includes the account identifier that
`_transport_failure` strips. That is correct for a terminal and wrong for anything
recorded: the Week 7 deliverable includes a terminal capture, and a raw 429 printed
during it would put the account id on screen. Options are a redaction of that one field,
or an env-gated verbosity switch defaulting to quiet during recording. Not resolved here
because the request was explicitly for the full message, and narrowing it silently would
be the same class of error as publishing it.
"""

from __future__ import annotations

import sys
import traceback
from typing import TextIO

# Flip to `sys.stderr` to keep diagnostics out of piped stdout. See the module docstring.
_STREAM: TextIO = sys.stdout

_PREFIX = "[diagnostic]"


def log_exception(
    context: str,
    exc: BaseException,
    *,
    include_traceback: bool = False,
) -> None:
    """Print the complete, unsanitized exception under a line saying where it happened.

    `context` should name the operation and what the code did next, because "what
    happened" and "what it cost" are different questions and the second is the one a
    reader is usually asking — "Census geocode failed; falling through to the city
    centroid" is worth more than the exception alone.

    `include_traceback` is for the genuinely unexpected. A caught `RequestException` from
    a known network call needs no stack; a bare `except Exception` catching something
    unclassified does.
    """
    print(f"{_PREFIX} {context}", file=_STREAM)
    print(f"{_PREFIX}   {type(exc).__name__}: {exc}", file=_STREAM)
    if include_traceback:
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            for subline in line.rstrip().splitlines():
                print(f"{_PREFIX}   {subline}", file=_STREAM)
    _STREAM.flush()


def log_note(context: str, detail: str) -> None:
    """Same channel, for a diagnostic that has no exception object behind it.

    Used where the interesting event is a *decision* rather than a failure — a schema
    retry being spent, say, which is a normal outcome of a loop working correctly and
    still worth being able to see.
    """
    print(f"{_PREFIX} {context}", file=_STREAM)
    print(f"{_PREFIX}   {detail}", file=_STREAM)
    _STREAM.flush()
