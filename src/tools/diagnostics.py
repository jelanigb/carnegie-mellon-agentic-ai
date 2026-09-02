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

**The account identifier is the one thing this channel does not print** — resolved
Sept 2, 2026 (U9.M), closing the `security`-scoped deferral that stood here. The full
text used to include the `user_id` that `_transport_failure` strips, which is right for
a terminal someone is watching and wrong for one being recorded: the Week 7 deliverable
includes a terminal capture, and a raw 429 arriving during it would put the account id
on screen. (Stated without the deferral marker on purpose, so `grep -rn "TODO(" src/`
stops counting a closed item — the inventory in §8 is only worth what that grep is.)

**Redaction was taken over the alternative — an env-gated verbosity switch defaulting to
quiet during recording — because the alternative's failure mode is unrecoverable.** A
switch has to be *remembered*, once, before a capture that cannot be edited afterwards;
and the run that exposes the identifier is by definition a run where something already
went wrong, which is the worst moment to be relying on having set a variable. Redaction
holds whether or not anyone was thinking about it. It also costs nothing a person
debugging actually wants: the status, the provider, the remedy hint and the traceback all
survive untouched, and the identifier is the one field that tells a reader nothing about
the failure. See `_redact` below for what is matched and why both forms are.
"""

from __future__ import annotations

import re
import sys
import traceback
from typing import TextIO

# Flip to `sys.stderr` to keep diagnostics out of piped stdout. See the module docstring.
_STREAM: TextIO = sys.stdout

_PREFIX = "[diagnostic]"

_REDACTED = "[account id redacted]"

# Two patterns for one identifier, because the envelope around it is the provider's to
# change and the identifier itself is not. The first matches it as a JSON field, which is
# how OpenRouter renders an error body today; the second matches the bare token anywhere,
# which covers a body formatted some other way, a message that quotes the id inline, and
# a traceback rendering an exception's repr.
#
# **Deliberately narrow.** These match an account identifier and nothing else — not
# addresses, not model ids, not the provider's remedy hint — because a redaction that
# over-matches destroys the detail this module exists to preserve, and it does so
# silently. The length floor keeps `user_id`-adjacent prose from being caught.
_ACCOUNT_ID_PATTERNS = (
    re.compile(r'("user_id"\s*:\s*")[^"]*(")'),
    re.compile(r"\buser_[A-Za-z0-9]{8,}\b"),
)


def _redact(text: str) -> str:
    """Remove the calling account's identifier from anything about to be printed.

    Applied to every line this module emits rather than only to exception text, because
    the raw model response reaches it too — `agents/extractor.py` passes `exc.last_raw`
    as a note detail, and what a model echoes back is not this project's to predict.
    """
    text = _ACCOUNT_ID_PATTERNS[0].sub(rf"\g<1>{_REDACTED}\g<2>", text)
    return _ACCOUNT_ID_PATTERNS[1].sub(_REDACTED, text)


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
    print(f"{_PREFIX} {_redact(context)}", file=_STREAM)
    print(f"{_PREFIX}   {_redact(f'{type(exc).__name__}: {exc}')}", file=_STREAM)
    if include_traceback:
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            for subline in line.rstrip().splitlines():
                print(f"{_PREFIX}   {_redact(subline)}", file=_STREAM)
    _STREAM.flush()


def log_note(context: str, detail: str) -> None:
    """Same channel, for a diagnostic that has no exception object behind it.

    Used where the interesting event is a *decision* rather than a failure — a schema
    retry being spent, say, which is a normal outcome of a loop working correctly and
    still worth being able to see.
    """
    print(f"{_PREFIX} {_redact(context)}", file=_STREAM)
    print(f"{_PREFIX}   {_redact(detail)}", file=_STREAM)
    _STREAM.flush()
