"""Put `src/` on the import path, and keep the suite off the network.

Application modules import as `import config`, `from state import ...` — flat, with
`src/` as the project root — and the scripts do the same via an explicit `sys.path`
insert. Tests follow the same convention rather than introducing a package layout that
only the test suite uses.

Run: .venv/bin/python -m pytest tests -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402  — the path insert above has to run first


@pytest.fixture(autouse=True)
def offline_report_calls(monkeypatch):
    """Turn off the two model calls U9.4 added, for every test in every file.

    **In `conftest.py` rather than beside the tests that touch them, and autouse rather
    than opt-in**, for the reason `test_flag_propagation.offline_scenario_evaluator`
    gives about the forecast evaluator: a case added later must not be able to reach the
    network by forgetting to ask not to. That fixture guards one file because the
    Scenario agent is reached from one file's cases; these two are reached by **every
    test that renders a report**, which is most of the suite.

    The two calls are the Critic's recommendation cross-check and the Summarizer's
    written summary. Left live, this suite would make two calls per test across 76 tests,
    take minutes, and go red whenever OpenRouter did — the failure mode that teaches a
    reader to stop trusting a must-never-fail suite.

    **Neither switch changes a verdict or a figure**, which is what makes disabling them
    safe rather than a hole in the coverage. The recommendation is computed by a pure
    rule and the cross-check can only annotate it; the summary is additive prose above a
    report that is complete without it. A test wanting either path exercises it by
    setting the flag back on and substituting a client — see
    `test_report_verdict.py` for both.
    """
    monkeypatch.setattr(config, "RECOMMENDATION_CROSS_CHECK_ENABLED", False)
    monkeypatch.setattr(config, "SUMMARY_NARRATIVE_ENABLED", False)
