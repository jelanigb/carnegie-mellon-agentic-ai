"""The one field the full-detail diagnostic channel is not allowed to print.

`tools/diagnostics.py` exists to print an exception *unabridged*, which is the opposite
of what `llm_client._transport_failure` does for the report. The account identifier is
the single exception to that, and it is here rather than in `test_flag_propagation.py`
because nothing on this path raises a flag or reaches a report — it reaches a terminal,
and the Week 7 deliverable records one.

**Tested rather than trusted, because the failure is silent.** A redaction that stops
matching prints an identifier into a capture that cannot be edited afterwards, and
nothing in a passing run says so. The two near-miss cases matter as much as the two
positives: an over-matching pattern destroys the detail this module exists to preserve,
just as quietly.

Each case redirects `_STREAM` rather than using pytest's capture fixtures. `_STREAM`
binds `sys.stdout` at import, so it holds the real stream and neither `capsys` nor
`capfd` sees the writes — pytest's own global capture does, which is why a failure
prints the text it claims it cannot read. Substituting the stream tests the same bytes
without depending on which capture layer wins.

No LLM, no network, no state.
"""

from __future__ import annotations

import io

import pytest

from tools import diagnostics

# The shape OpenRouter renders an error body in — the useful half is the provider's
# message and status; the envelope carries the identifier `_transport_failure` strips.
_ERROR_BODY = (
    '{"error":{"message":"Rate limit exceeded: free-models-per-day. Add 10 credits '
    'to unlock 1000 free model requests per day","code":429},'
    '"user_id":"user_2xK9mQvT4bLpNaZw"}'
)


class _Printed:
    """What reached the stream, as a string, for the duration of one test."""

    def __init__(self, buffer: io.StringIO) -> None:
        self._buffer = buffer

    def __contains__(self, needle: str) -> bool:
        return needle in self._buffer.getvalue()

    def __str__(self) -> str:  # pragma: no cover - only reached on a failure
        return self._buffer.getvalue()


@pytest.fixture
def printed(monkeypatch):
    buffer = io.StringIO()
    monkeypatch.setattr(diagnostics, "_STREAM", buffer)
    return _Printed(buffer)


def test_the_account_identifier_does_not_reach_the_terminal(printed):
    diagnostics.log_exception("OpenRouter call failed", RuntimeError(_ERROR_BODY))
    assert "user_2xK9mQvT4bLpNaZw" not in printed
    assert "[account id redacted]" in printed


def test_everything_a_person_debugging_wants_survives_the_redaction(printed):
    """The reason this channel exists is the detail the report throws away. Redacting
    one field must not cost the status code, the provider's own explanation, or its
    remedy hint — those are what turn a failed run into a diagnosed one."""
    diagnostics.log_exception("OpenRouter call failed", RuntimeError(_ERROR_BODY))
    assert "429" in printed
    assert "Rate limit exceeded: free-models-per-day" in printed
    assert "Add 10 credits" in printed


def test_the_identifier_is_caught_outside_a_json_envelope_too(printed):
    """`agents/extractor.py` passes a raw model response as a note detail, and what a
    model echoes back is not this project's to predict. The bare-token pattern is what
    covers it, and a body the provider reformats one day."""
    diagnostics.log_note("last raw response was:", "…quoting user_2xK9mQvT4bLpNaZw inline")
    assert "user_2xK9mQvT4bLpNaZw" not in printed
    assert "[account id redacted]" in printed


def test_the_redaction_does_not_over_match(printed):
    """An over-broad pattern fails as silently as an under-broad one, and costs more:
    it eats the detail the channel exists for. The field *name*, a short token that only
    looks like an id, and an ordinary provider note must all come through untouched."""
    diagnostics.log_note(
        "nvidia/nemotron-3-nano-30b-a3b answered by Novita",
        "system_fingerprint=abc123; the user_id field was absent; user_short",
    )
    assert "[account id redacted]" not in printed
    assert "the user_id field was absent" in printed
    assert "user_short" in printed
    assert "system_fingerprint=abc123" in printed
