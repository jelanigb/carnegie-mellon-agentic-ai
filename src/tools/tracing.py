"""LangSmith tracing setup — opt-in, env-driven, never required to run.

§3 adopts LangSmith on the argument that multi-step agent loops are impractical to
debug from logs alone and that traces double as documentation of actual system
behaviour. Both hold. Neither is a reason to make the pipeline refuse to run without
an account.

So tracing is **enabled by the environment, not by the code**. LangSmith activates
itself when `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` are set — the LangChain
runtime reads those directly, and no call in this repo turns it on. What this module
adds is the two things that would otherwise be silent:

1. It sets the project name from `config.LANGSMITH_PROJECT`, so traces land in one
   named project instead of "default", which matters once several units' runs are
   interleaved and screenshots need to be found again weeks later.
2. It reports, once, whether tracing is on. A trace you believed was being captured and
   was not is worse than no trace, and that is exactly the failure that surfaces at the
   end of a run rather than the start.

> ⚠️ Free-tier traces expire after **14 days** (§3). Capture screenshots as you go;
> Week 4 traces will not be viewable in Week 7.
"""

from __future__ import annotations

import os

import config


def configure_tracing(verbose: bool = True) -> bool:
    """Point LangSmith at this project's trace bucket. Returns whether tracing is on.

    Called for its side effect at the start of a run. Safe to call when tracing is
    disabled, and safe to call more than once.
    """
    enabled = os.environ.get("LANGSMITH_TRACING", "").lower() == "true"

    if enabled:
        os.environ.setdefault("LANGSMITH_PROJECT", config.LANGSMITH_PROJECT)
        if not os.environ.get("LANGSMITH_API_KEY"):
            if verbose:
                print(
                    "  tracing: LANGSMITH_TRACING=true but LANGSMITH_API_KEY is unset. "
                    "The run will proceed and no trace will be recorded."
                )
            return False
        if verbose:
            print(f"  tracing: on -> LangSmith project '{os.environ['LANGSMITH_PROJECT']}'")
        return True

    if verbose:
        print(
            "  tracing: off. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to record "
            "this run."
        )
    return False
