"""Hand-authored recordings for the `extraction_retry_exhausted` eval case (U8.3).

Why this is not an ordinary `--record` run
--------------------------------------------
Every other recorded-extraction case (U8.3) is made the ordinary way: run the listing
against the live model once with `LLM_CACHE_MODE=read_write` and commit whatever comes
back. That does not work here. `agents.extractor.ListingExtraction` has no required
fields — every one is `Optional` with a default — so an empty or merely-odd response from
the model *validates*. Provoking three straight schema failures out of a live model on
demand is not a property this project can assert; it would either not reproduce, or it
would reproduce by accident and be unreviewable evidence of nothing.

`tools.llm_cache.ResponseCache` does not care whether a recording came from a live call —
each entry is keyed on `(model, system, prompt, temperature)` and served on a match. So
this script computes the three keys `agents.extractor._extract_terms` will actually look
up — using the real `_EXTRACTION_PROMPT`, `_EXTRACTION_SYSTEM`, `ListingExtraction`
schema and retry-prompt template, not a re-derivation of them — and writes a deliberately
invalid response under each one. No live model call happens; determinism comes from the
fact that Pydantic validation, unlike a model, is the same function every time.

Run once, deliberately, whenever the listing, the model, or the extraction schema
changes:

    .venv/bin/python scripts/record_retry_exhausted_fixture.py

The three responses are graded to look like plausible degrading behaviour rather than
three copies of noise: an outright refusal, then two structurally-valid JSON objects
that fail on type coercion. Each is verified against the real schema before being
written, so a response that would have validated (and therefore never traced the case's
intended path if it were the one played back) fails the script rather than getting
committed silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from agents.extractor import _EXTRACTION_PROMPT, _EXTRACTION_SYSTEM, ListingExtraction
from eval.cases import RETRY_EXHAUSTED_LISTING
from pydantic import ValidationError
from tools.llm_cache import CacheKey, CacheMode, ResponseCache
from tools.llm_client import _extract_json

import json

# Three attempts, each a distinct, plausible way a small model misbehaves under a
# schema-only instruction. None of them validate against `ListingExtraction` — checked
# below rather than assumed.
_RAW_RESPONSES = [
    "I'm sorry, I can't provide a structured summary of this listing without more "
    "context about the buyer's intent.",
    '{"price": "unspecified", "unit_count": "a few"}',
    '{"bedrooms": "two", "bathrooms": "one and a half"}',
]


def _base_system() -> str:
    """Reproduces `LlmClient.call_with_schema`'s system-prompt construction exactly."""
    schema_json = json.dumps(ListingExtraction.model_json_schema(), indent=2)
    return (
        _EXTRACTION_SYSTEM
        + "\n\nRespond with a single JSON object conforming to this schema. "
        "Emit no prose, no explanation, and no markdown fences.\n\n"
        + schema_json
    ).strip()


def main() -> None:
    original_prompt = _EXTRACTION_PROMPT.format(listing_text=RETRY_EXHAUSTED_LISTING)
    base_system = _base_system()
    cache = ResponseCache(config.EVAL_RECORDINGS_DIR, CacheMode.READ_WRITE)

    current_prompt = original_prompt
    for attempt, raw in enumerate(_RAW_RESPONSES, start=1):
        try:
            ListingExtraction.model_validate_json(_extract_json(raw))
        except (ValidationError, ValueError) as exc:
            last_error = str(exc)
        else:
            raise RuntimeError(
                f"attempt {attempt}'s response validates against ListingExtraction — "
                f"pick a response that genuinely fails schema validation."
            )

        key = CacheKey(
            model=config.MODEL_EXTRACTION,
            system=base_system,
            prompt=current_prompt,
            temperature=config.LLM_TEMPERATURE,
        )
        cache.put(key, raw)
        print(f"attempt {attempt}/3: recorded key {key.digest()[:12]}… "
              f"({len(current_prompt)} char prompt)")

        current_prompt = (
            f"{original_prompt}\n\n"
            f"Your previous response was rejected. It was:\n{raw}\n\n"
            f"The validation errors were:\n{last_error}\n\n"
            f"Return corrected JSON matching the schema exactly."
        )

    print("\nAll three attempts recorded. Replay this case with:")
    print("  .venv/bin/python -m eval.runner --case chicago-retry-exhausted")


if __name__ == "__main__":
    main()
