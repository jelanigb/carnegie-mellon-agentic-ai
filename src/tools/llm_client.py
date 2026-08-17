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

import requests
from openai import APIError, OpenAI
from pydantic import BaseModel, ValidationError

import config
from tools import diagnostics
from tools.llm_cache import CacheKey, ResponseCache

BASE_URL = "https://openrouter.ai/api/v1"
MODELS_URL = f"{BASE_URL}/models"

# The catalogue endpoint is public, so the liveness check below deliberately does not
# authenticate: "this model no longer exists" and "your key is missing" are different
# operator problems, and a check that needed a key could not tell them apart.
_CATALOGUE_TIMEOUT_SECONDS = 20

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


def _transport_failure(model: str, exc: APIError) -> str:
    """Summarize an SDK exception into text that is safe to publish.

    `str(exc)` on an OpenRouter error is the entire JSON body, which carries the calling
    account's `user_id` alongside the useful part. That text does not stay in a log: the
    Extractor puts it in a flag, the flag is rendered verbatim into the report (§1
    requires flags be shown in full, not summarized), and the reports are portfolio
    artifacts. So the account identifier would have been published.

    Reading the provider's own `message` keeps what a reader needs — which model, which
    status, and the explanation including its remedy hint — and drops the envelope
    carrying the identifier. Note `exc.message` is *not* that: it is the whole rendered
    body, identifier included, which is the trap this function exists to avoid.

    Both nestings are handled because the SDK unwraps one level for some error classes
    and not others (a 429 arrives already unwrapped), and guessing wrong costs the
    message. Length-capped as a backstop, since the body shape is the provider's to
    change and this text reaches a published document either way.
    """
    provider_message = None
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict):
            provider_message = inner.get("message")
        elif isinstance(body.get("message"), str):
            provider_message = body["message"]

    status = getattr(exc, "status_code", None)
    where = f"OpenRouter call to {model} failed"
    if status is not None:
        where += f" (HTTP {status})"
    return f"{where}: {(provider_message or type(exc).__name__)[:400]}"


def available_models() -> set[str]:
    """Every model ID OpenRouter's catalogue currently lists.

    Raises `LlmError` when the catalogue itself cannot be read. That is deliberately
    not treated as "the models are fine" — an unverifiable configuration and a verified
    one are different states, and silently conflating them would reintroduce exactly the
    failure this function exists to prevent.
    """
    try:
        response = requests.get(MODELS_URL, timeout=_CATALOGUE_TIMEOUT_SECONDS)
        response.raise_for_status()
        return {entry["id"] for entry in response.json()["data"]}
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        diagnostics.log_exception(
            f"llm_client.available_models: could not read the catalogue at {MODELS_URL}",
            exc,
        )
        raise LlmError(
            f"Could not read the OpenRouter model catalogue at {MODELS_URL}: {exc}. "
            f"The configured models are unverified rather than known-good."
        ) from exc


def verify_models_live(*model_ids: str) -> set[str]:
    """Fail loudly at launch if a configured model has left the catalogue (decision #8).

    This exists because of a specific, recorded failure: the four model IDs in
    `config.py` were valid when written and dead six days later — the free Llama variant
    they all pointed at became paid-only. Nothing before U3 made an LLM call, so the
    breakage would have surfaced as an opaque error partway through an extraction, in a
    run that had already spent a geocode and a Chroma query. Free-tier catalogues churn;
    treating these constants as set-once is what made a routine deprecation into a
    latent runtime failure.

    Defaults to the four `config.MODEL_*` roles, deduplicated — they currently hold the
    same value, and reporting one dead model four times would be noise.

    Returns the set it checked, so a caller can log what was verified rather than
    assuming. Raises `LlmError` naming every missing ID.
    """
    wanted = set(model_ids) or {
        config.MODEL_DEV,
        config.MODEL_EXTRACTION,
        config.MODEL_CRITIC,
        config.MODEL_SUMMARIZER,
    }
    catalogue = available_models()

    missing = sorted(wanted - catalogue)
    if missing:
        # Suggest same-vendor models rather than "everything free". The project runs on
        # paid variants (decision #8), so a free-model list is the wrong remedy — and a
        # dead model is usually replaced by its sibling, not by whatever is cheapest.
        vendors = {model.split("/")[0] for model in missing}
        alternatives = sorted(m for m in catalogue if m.split("/")[0] in vendors)
        raise LlmError(
            f"Configured model(s) absent from the OpenRouter catalogue: {missing}. "
            f"Update config.py — see decision #8 in docs/implementation_plan.md §7. "
            f"Still listed from the same vendor(s): {alternatives or 'none'}"
        )
    return wanted


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
    def __init__(
        self,
        token: Optional[str] = None,
        cache: Optional[ResponseCache] = None,
    ):
        self._client = OpenAI(
            base_url=BASE_URL,
            api_key=token or _load_token(),
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )
        # Injectable so an evaluation run can point at the committed recordings in
        # `src/eval/data/` while ordinary runs use the gitignored development cache,
        # without either needing to mutate config.
        self._cache = cache or ResponseCache(config.LLM_CACHE_DIR, config.LLM_CACHE_MODE)

    def complete(
        self,
        prompt: str,
        model: Optional[str] = None,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Single completion returning raw text, served from cache when recorded."""
        resolved_model = model or config.MODEL_DEV
        resolved_temperature = (
            config.LLM_TEMPERATURE if temperature is None else temperature
        )
        # Built from the resolved values, not the arguments: `complete(model=None)` and
        # `complete(model=config.MODEL_DEV)` are the same request and must share a key,
        # or half the recordings would be unreachable depending on how the caller wrote
        # the call.
        key = CacheKey(
            model=resolved_model,
            system=system,
            prompt=prompt,
            temperature=resolved_temperature,
        )

        cached = self._cache.get(key)
        if cached is not None:
            return cached

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        # Every SDK failure is funnelled into LlmError so callers have one exception
        # type to degrade on. This is not tidiness — it is the Transparent Degradation
        # guarantee at the transport layer. A rate limit arrives as
        # `openai.RateLimitError`, which is not an `LlmError`, so before this the free
        # tier's daily cap would propagate out of the Extractor and crash the graph
        # instead of raising a flag. Found the honest way: by exhausting
        # `free-models-per-day` (50 requests, account-wide) during the U3 bake-off.
        #
        # The SDK has already retried transient failures `config.LLM_MAX_RETRIES` times
        # with backoff by the time this fires, so reaching here means it did not clear.
        try:
            resp = self._client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                temperature=resolved_temperature,
            )
        except APIError as exc:
            # The full body goes to stdout; only the sanitized summary continues into
            # the flag and therefore into the report. See tools/diagnostics.py for why
            # the two audiences get different text.
            diagnostics.log_exception(
                f"llm_client.complete: call to {resolved_model} failed; "
                f"raising LlmError for the caller to degrade on",
                exc,
            )
            raise LlmError(_transport_failure(resolved_model, exc)) from exc

        content = resp.choices[0].message.content or ""
        # Recorded after a successful call only. A failed call has nothing worth
        # replaying, and recording one would make a transient outage permanent for
        # every future run keyed on the same prompt.
        self._cache.put(key, content)
        return content

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
                # Previously invisible: a retry that eventually succeeded left no trace,
                # so "this model needed three attempts" was unknowable after the fact.
                # The raw response is included because the validation error alone rarely
                # explains *why* the model produced it.
                diagnostics.log_exception(
                    f"llm_client.call_with_schema: attempt {attempt}/{attempts} against "
                    f"{model or config.MODEL_DEV} failed validation for "
                    f"{schema.__name__}; re-prompting with the error text",
                    exc,
                )
                diagnostics.log_note(
                    "  rejected response was:", last_raw.strip()[:1000] or "(empty)"
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    f"Your previous response was rejected. It was:\n{last_raw}\n\n"
                    f"The validation errors were:\n{last_error}\n\n"
                    f"Return corrected JSON matching the schema exactly."
                )

        raise SchemaValidationExhausted(attempts, last_error, last_raw)
