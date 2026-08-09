"""Thin OpenRouter client with schema-validated calls.

OpenRouter exposes an OpenAI-compatible API, so the official `openai` SDK is used
against a different base URL rather than pulling in a separate client library.

The important function here is `call_with_schema`. Free-tier models are unreliable at
producing strictly valid JSON, and the Extractor's clarification loop (Checkpoint 2.1,
Loop 1) depends on being able to *observe* a malformed parse and reformulate rather
than crashing or silently accepting garbage. `call_with_schema` closes that loop:
it validates against a Pydantic model and, on failure, re-prompts with the
ValidationError text so the model is told precisely what was wrong with its previous
attempt. Every agent that needs structured output goes through it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional, TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

import config

BASE_URL = "https://openrouter.ai/api/v1"

_REPO_ROOT = Path(__file__).resolve().parents[2]

# TODO(security): same open question as tools/hud_fmr.py — whether to drop this on-disk
# fallback and require OPENROUTER_API_KEY. Naming a credential path in a public source
# file advertises where a key is kept, even though the file is gitignored. Unlike the
# HUD token this one is billable if leaked, so it is the stronger candidate for
# env-var-only.
_TOKEN_FILE = _REPO_ROOT / "ignore" / "openrouter_key"

T = TypeVar("T", bound=BaseModel)


class LlmError(Exception):
    """Raised when the model cannot be reached, or auth is missing."""


class SchemaValidationExhausted(Exception):
    """Raised when a model failed to produce schema-valid output within the retry budget.

    Carries the final validation error and the raw text so the calling agent can decide
    whether to escalate, fall back, or raise a flag — the decision belongs to the agent,
    not to this client.
    """

    def __init__(self, attempts: int, last_error: str, last_raw: str):
        self.attempts = attempts
        self.last_error = last_error
        self.last_raw = last_raw
        super().__init__(
            f"No schema-valid response after {attempts} attempts. "
            f"Last validation error: {last_error}"
        )


def _load_token() -> str:
    """Token resolution mirrors tools/hud_fmr.py: env var wins, file is the fallback."""
    env_token = os.environ.get("OPENROUTER_API_KEY")
    if env_token:
        return env_token.strip()
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text().strip()
    raise LlmError(
        f"No OpenRouter token found. Set OPENROUTER_API_KEY or create {_TOKEN_FILE}."
    )


def _extract_json(text: str) -> str:
    """Pull a JSON object out of a model response.

    Smaller models routinely wrap JSON in prose or a ```json fence despite instructions
    not to. Stripping that here — rather than spending a retry on it — keeps the retry
    budget for genuine schema violations.
    """
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


class LlmClient:
    def __init__(self, token: Optional[str] = None):
        self._client = OpenAI(
            base_url=BASE_URL,
            api_key=token or _load_token(),
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Single completion returning raw text."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = self._client.chat.completions.create(
            model=model or config.MODEL_DEV,
            messages=messages,
            temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
        )
        return resp.choices[0].message.content or ""

    def call_with_schema(
        self,
        prompt: str,
        schema: type[T],
        model: Optional[str] = None,
        system: Optional[str] = None,
        max_attempts: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> tuple[T, int]:
        """Call the model and validate its output against `schema`.

        On a validation failure, re-prompts with the ValidationError text appended so
        the model is told exactly what was wrong rather than simply asked to try again.
        This is the Reason/Act/Observe/Decide loop applied to parsing: the malformed
        output is an *observation* that determines the next action, not an error state
        to be swallowed.

        Returns (validated_object, attempts_used) so the caller can flag how many
        retries a given extraction needed. Raises SchemaValidationExhausted when the
        budget runs out; the caller decides how to degrade.
        """
        attempts = max_attempts or config.MAX_EXTRACTION_RETRIES
        schema_json = json.dumps(schema.model_json_schema(), indent=2)

        base_system = (
            (system or "")
            + "\n\nRespond with a single JSON object conforming to this schema. "
            "Emit no prose, no explanation, and no markdown fences.\n\n"
            + schema_json
        ).strip()

        current_prompt = prompt
        last_error = ""
        last_raw = ""

        for attempt in range(1, attempts + 1):
            last_raw = self.complete(
                current_prompt,
                model=model,
                system=base_system,
                temperature=temperature,
            )
            try:
                return schema.model_validate_json(_extract_json(last_raw)), attempt
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                current_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous response was rejected. It was:\n{last_raw}\n\n"
                    f"The validation errors were:\n{last_error}\n\n"
                    f"Return corrected JSON matching the schema exactly."
                )

        raise SchemaValidationExhausted(attempts, last_error, last_raw)
