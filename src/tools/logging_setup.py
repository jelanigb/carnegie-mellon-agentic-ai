"""Keep one library's constructor from configuring logging for the whole process.

Why this module exists
----------------------
A run prints roughly 190 lines of HTTP and model-loading chatter before the report —
HEAD requests to huggingface.co, redirect codes, `Loading SentenceTransformer model`.
None of it comes from this project, which reports with `print` rather than `logging`
throughout (`tools/diagnostics.py` records that choice and its cost). It is also not
the libraries' own default: Python's root logger starts at WARNING with no handler, so
an INFO record from `httpx` goes nowhere unless something asks for it.

**Something does, and it is decision #13's reference server.** `MCPServer.__init__`
calls the SDK's own `configure_logging()`, which calls
`logging.basicConfig(level="INFO", handlers=[RichHandler(...)])` — a process-wide
change made as a side effect of constructing an object.
`agents/scenario_forecast.py` imports `mcp_server` to build its evidence menu from the
live tool registry, so every run of this pipeline inherits it, and from that import
onward every third-party INFO record in the process becomes terminal output.

Measured at the embedder's first load, which is where the bulk of it lands: 32 records
from `httpx`, one from `sentence_transformers`, one WARNING from `huggingface_hub`.
The 320 records from `httpcore` sit at DEBUG and stay below the line either way.

What this does
--------------
Restores the root logger to whatever it was before the server was constructed, unless
`LIBRARY_LOGS=true` asks for the chatter back.

**Restoring rather than silencing by name is the decision here.** Setting `httpx` and
`sentence_transformers` to WARNING would work today and would be wrong the first time
either renames a logger or a third noisy dependency arrives — the list would go quietly
stale, which is the failure `graph.state_serde()`'s allowlist has now hit twice. The
root logger's prior state is a fact this process can read; a list of noisy logger names
is a guess that decays. Nothing here filters a record or lowers a level at its source,
so a library that starts logging something worth reading is unaffected: the process
simply stops carrying a logging configuration no entrypoint asked for.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

import config


@contextmanager
def library_logging_unchanged() -> Iterator[None]:
    """Undo any process-wide logging configuration made inside the block.

    Level and handler list are captured by value and put back, so a library that
    installs a handler, sets a level, or does both leaves the process as it found it.
    Only handlers the block *added* are removed, so a caller that installed its own
    handler first keeps it.

    A no-op when `config.LIBRARY_LOGS_ENABLED` — that switch exists so the chatter is
    one environment variable away when debugging a retrieval or an HTTP failure, rather
    than deleted from the build.
    """
    root = logging.getLogger()
    before_level, before_handlers = root.level, list(root.handlers)
    try:
        yield
    finally:
        if not config.LIBRARY_LOGS_ENABLED:
            for handler in list(root.handlers):
                if handler not in before_handlers:
                    root.removeHandler(handler)
            root.setLevel(before_level)
