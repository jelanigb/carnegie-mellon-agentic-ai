"""LangSmith tracing setup — opt-in, env-driven, never required to run.

§3 adopts LangSmith on the argument that multi-step agent loops are impractical to
debug from logs alone and that traces double as documentation of actual system
behaviour. Both hold. Neither is a reason to make the pipeline refuse to run without
an account.

So tracing is **switched on by the environment, not by the code**. LangSmith activates
itself when `LANGSMITH_TRACING=true` and a key are set — the LangChain runtime reads
`LANGSMITH_API_KEY` directly, and no call in this repo turns tracing on. What this
module adds is the three things that would otherwise be silent:

1. It sets the project name from `config.LANGSMITH_PROJECT`, so traces land in one
   named project instead of "default", which matters once several units' runs are
   interleaved and screenshots need to be found again weeks later.
2. It supplies the key from the same on-disk fallback the other two credentials use
   (`_load_key` below), because the switch and the credential are different questions
   and only the switch should have to be typed.
3. It reports, once, whether tracing is on. A trace you believed was being captured and
   was not is worse than no trace, and that is exactly the failure that surfaces at the
   end of a run rather than the start.

**The switch is deliberately not given a file fallback.** A key on disk means *this
machine can trace*; `LANGSMITH_TRACING=true` means *this run should be traced*. Folding
the second into the first would start recording every local run to a hosted service the
moment a key was dropped into place, which is the opposite of opt-in.

> ⚠️ Free-tier traces expire after **14 days** (§3). Capture screenshots as you go;
> Week 4 traces will not be viewable in Week 7.
"""

from __future__ import annotations

import os
from pathlib import Path

import config

_REPO_ROOT = Path(__file__).resolve().parents[2]

# TODO(security): the third instance of the on-disk credential fallback, and it inherits
# the question OQ-10 settled for the other two on Aug 31, 2026 — keep the fallback,
# because the directory is gitignored and requiring an env var only makes a fresh clone
# harder to run. Same trade as `tools/llm_client.py` and `tools/hud_fmr.py`; unlike the
# OpenRouter key this one is not billable if leaked, so it is the weakest candidate of
# the three for env-var-only.
_KEY_FILE = _REPO_ROOT / "ignore" / "langsmith_key.txt"


def _load_key() -> str | None:
    """Key resolution mirrors `tools/llm_client.py`: env var wins, file is the fallback.

    Returns `None` rather than raising, and that is the one way it differs from the
    other two loaders: the pipeline cannot run without a model or an FMR schedule, and
    it can run perfectly well without a record of having run. A missing trace key is a
    reported condition, not an error.
    """
    env_key = os.environ.get("LANGSMITH_API_KEY")
    if env_key:
        return env_key.strip()
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text().strip() or None
    return None


def configure_tracing(verbose: bool = True) -> bool:
    """Point LangSmith at this project's trace bucket. Returns whether tracing is on.

    Called for its side effect at the start of a run. Safe to call when tracing is
    disabled, and safe to call more than once.
    """
    enabled = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"

    if enabled:
        os.environ.setdefault("LANGSMITH_PROJECT", config.LANGSMITH_PROJECT)
        key = _load_key()
        if not key:
            if verbose:
                print(
                    "  tracing: LANGSMITH_TRACING=true but no LangSmith key was found. "
                    "The run will proceed and no trace will be recorded."
                )
            return False
        # Written back to the environment because the LangChain runtime reads the
        # variable itself — nothing in this repo hands the key to a client. A key
        # already in the environment is left exactly as it was found.
        os.environ["LANGSMITH_API_KEY"] = key
        if verbose:
            print(f"  tracing: on -> LangSmith project '{os.environ['LANGSMITH_PROJECT']}'")
        return True

    if verbose:
        print("  tracing: off. Set LANGSMITH_TRACING=true to record this run.")
    return False
