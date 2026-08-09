"""Node name constants for the LangGraph state graph.

LangGraph addresses nodes by string. A typo in `add_edge("extracter", ...)` compiles
cleanly and fails at invoke time with an error that points at the graph rather than at
the typo, so the names are centralized here and referenced symbolically everywhere else.
"""

from __future__ import annotations

from typing import Final

PLANNER: Final = "planner"
EXTRACTOR: Final = "extractor"
COMPS_RETRIEVAL: Final = "comps_retrieval"
VALUATION_RENT: Final = "valuation_rent"
SCENARIO_FORECAST: Final = "scenario_forecast"
CRITIC: Final = "critic"
SUMMARIZER: Final = "summarizer"
HUMAN_REVIEW: Final = "human_review"

# Every node in the graph. Used to validate that conditional-edge mappings only ever
# target nodes that actually exist.
ALL_NODES: Final = (
    PLANNER,
    EXTRACTOR,
    COMPS_RETRIEVAL,
    VALUATION_RENT,
    SCENARIO_FORECAST,
    CRITIC,
    SUMMARIZER,
    HUMAN_REVIEW,
)
