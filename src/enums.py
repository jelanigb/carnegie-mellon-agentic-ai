"""Closed-vocabulary enums shared across modules that must not depend on each other.

Exists solely to hold `AppreciationTier`. `state.py` is the natural home for a shared
type, but `tools/redfin_data.py` deliberately does not import `state.py` — see that
module's docstring: keeping Redfin's flag-worthy findings as returned data rather than
constructed `Flag` objects is what lets it avoid the dependency. `state.py` does not
depend on `tools/redfin_data.py` either, since that module pulls in pandas and does
Redfin-specific I/O setup at import time that `state.py` (imported by lightweight tests
and scripts) shouldn't have to pay for. This module has zero internal dependencies, so
either side can import it without the other.

If a second shared enum ever needs this treatment, it belongs here too rather than
picking one side to depend on the other.
"""

from __future__ import annotations

from enum import StrEnum


class AppreciationTier(StrEnum):
    """Which appreciation series backs a forecast's growth assumption.

    Mirrored by `DealState.appreciation_source` in `state.py` (docs/state_schema.md
    §5) and produced by `tools/redfin_data.py`'s `AppreciationSeries.tier` /
    `GrowthBands.tier`. Both import this one definition rather than each declaring
    their own, which is what stops the two from drifting apart the way two
    independently-typed `Literal`s could.

    `zip_multifamily` is documented future work (§2) and is not produced by the
    current build; kept as a member rather than omitted so the type already has a
    place for it.
    """

    METRO_MULTIFAMILY = "metro_multifamily"
    ZIP_MULTIFAMILY = "zip_multifamily"
    METRO_ALL_RESIDENTIAL = "metro_all_residential"
