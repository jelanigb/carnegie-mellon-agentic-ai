"""Put `src/` on the import path.

Application modules import as `import config`, `from state import ...` — flat, with
`src/` as the project root — and the scripts do the same via an explicit `sys.path`
insert. Tests follow the same convention rather than introducing a package layout that
only the test suite uses.

Run: .venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
