"""On-disk cache for model responses — a latency and reproducibility mechanism.

Why this exists, and why the reason changed
--------------------------------------------
This was first proposed as a quota workaround: the OpenRouter free tier allows 50 model
requests per day account-wide, and U3's bake-off exhausted it. Moving to paid inference
removed that pressure, and the cache is worth building anyway for two reasons that
outlast it:

1. **Latency.** A live call measured 9.9-23s per listing during the U3 bake-off. A hit
   here is a local JSON read — milliseconds. Re-running an evidence script against
   unchanged prompts stops being a coffee break.
2. **Reproducibility.** An evaluation whose inputs are re-sampled from a stochastic
   endpoint on every run cannot show that a change in results came from a change in the
   system. Replaying recorded responses makes the eval harness a measurement of *this
   repo* rather than of the provider's mood that afternoon. That matters directly for
   U8, whose output is the evaluation section of the report.

Cost avoidance still happens; it is now the least interesting of the three.

Three modes, and the third is the point
-----------------------------------------
- `off` — every call goes live. Nothing is read, nothing is written.
- `read_write` — the development default. A miss calls the model and records the result.
- `replay` — a miss **raises** rather than calling the model. This is what makes an
  evaluation run honest: a cache miss means a prompt changed since the recordings were
  made, and the right response to that is a deliberate re-record, not a silent live call
  that quietly re-samples half the suite and reports the mixture as one result.

Caching at the transport layer, deliberately
----------------------------------------------
The cache sits under `LlmClient.complete`, not under `call_with_schema`. That is what
makes a replayed run reproduce the *retry loop* faithfully rather than skipping it: each
attempt in `call_with_schema` sends a different prompt (the previous failure's
`ValidationError` is appended), so each attempt has its own key and its own recording. A
recorded sequence where the model failed validation twice and succeeded on the third
attempt replays as exactly that — three entries, two rejections, one success. Caching the
validated object instead would have erased the loop this project's Checkpoint 2.1 design
is built around.

What is not cached
-------------------
Nothing decides here whether a response *should* be reused — the key covers every input
that changes the output (model, system prompt, user prompt, temperature), so a hit is a
hit on identical inputs by construction. Temperature is included even though it is 0.0
almost everywhere, because the one place it will not be is U6's Tree-of-Thought
branching, and a cache that silently served a temperature-0 response to a temperature-0.8
request would make those branches identical without saying so.

Storage
--------
One file per entry, not a single accumulating JSON. Recordings meant for `replay` are
committed to the repo (`src/eval/data/`), so a fresh clone can reproduce an evaluation —
and one-file-per-entry means each recording is an independently reviewable diff rather
than a churning blob. It also sidesteps the read-modify-write races that
`tools/hud_fmr.py`'s single-file cache documents as an accepted limitation.

Each file carries its prompt alongside its response. That is redundant — the key is a
hash of exactly those inputs — and it is kept anyway, because a recording nobody can read
is a recording nobody will audit, and these are checked into a public repository as
evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

CacheMode = Literal["off", "read_write", "replay"]


class CacheMiss(Exception):
    """Raised in `replay` mode when a request has no recording.

    Deliberately fatal rather than a fall-through to a live call. A miss during replay
    means the prompt has drifted from what was recorded, and the two honest responses to
    that are re-recording or fixing the prompt — not silently mixing fresh samples into a
    result set presented as reproducible.
    """

    def __init__(self, key: str, model: str, directory: Path):
        self.key = key
        super().__init__(
            f"No recorded response for {model} (key {key[:12]}…) in {directory}. "
            f"Cache mode is 'replay', so no live call was made. Re-record with "
            f"LLM_CACHE_MODE=read_write if the prompt changed on purpose."
        )


@dataclass(frozen=True)
class CacheKey:
    """Everything that can change a response. Hashed, in a fixed field order."""

    model: str
    system: Optional[str]
    prompt: str
    temperature: float

    def digest(self) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "system": self.system,
                "prompt": self.prompt,
                "temperature": self.temperature,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, directory: Path, mode: CacheMode = "read_write"):
        self._dir = Path(directory)
        self._mode = mode

    @property
    def mode(self) -> CacheMode:
        return self._mode

    def _path(self, key: str) -> Path:
        return self._dir / f"{key}.json"

    def get(self, key: CacheKey) -> Optional[str]:
        """Return a recorded response, or `None` on a miss in a mode that allows one.

        Raises `CacheMiss` in `replay` mode — see that exception's docstring.
        """
        if self._mode == "off":
            return None

        digest = key.digest()
        path = self._path(digest)
        if path.exists():
            try:
                return json.loads(path.read_text())["response"]
            except (json.JSONDecodeError, KeyError, OSError) as exc:
                # A corrupt recording is a miss, not a crash — but never a silent one,
                # since the alternative reading ("this prompt was never recorded") would
                # send someone re-recording a file that already exists.
                from tools import diagnostics

                diagnostics.log_exception(
                    f"llm_cache: recording at {path} is unreadable; treating as a miss",
                    exc,
                )

        if self._mode == "replay":
            raise CacheMiss(digest, key.model, self._dir)
        return None

    def put(self, key: CacheKey, response: str) -> None:
        """Record a response. No-op in `off`; in `replay` nothing new is ever recorded."""
        if self._mode != "read_write":
            return

        self._dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "model": key.model,
            "temperature": key.temperature,
            # Kept for auditability rather than for lookup — see the module docstring.
            "system": key.system,
            "prompt": key.prompt,
            "response": response,
        }

        # Same atomicity discipline as tools/hud_fmr.py's cache: write to a temporary
        # file in the destination directory, then rename, so an interrupted write cannot
        # leave a half-written recording that later reads as corrupt.
        fd, tmp_name = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_name, self._path(key.digest()))
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
