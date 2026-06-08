"""Decimal money helpers re-exported from the production law modules.

These helpers are NOT legal math (per LOCK.md § 1: helpers in ``law/_utils/``
do not get audit-locked). They are re-exported from
``tax_pipeline.y2025.germany_law`` and ``tax_pipeline.y2025.us_law`` so the
per-§ shadow files share a single canonical implementation of rounding and
validation primitives, keeping fingerprints byte-identical to the originals.

This file is part of MIGRATION.md Phase 2/3: per-§ shadow extraction.
"""
from __future__ import annotations

# DE rounding primitives. Each ``law/germany/year_2025/.../p<N>.py`` imports
# ``q2`` / ``floor_euro`` / ``floor_cent`` / ``ceil_euro`` from here.
from tax_pipeline.y2025.germany_law import (
    ceil_euro,
    floor_cent,
    floor_euro,
    q2,
)

# US rounding + validation primitives. Each ``law/usa/year_2025/.../p<N>.py``
# (and the Rev. Proc. files) imports these from here.
from tax_pipeline.y2025.us_law import (
    USD_CENT,
    ZERO_USD,
    _require_non_negative,
    _require_positive,
    _require_unit_interval,
    form_1040_whole_dollar_2025,
    round_cents,
)

__all__ = (
    # DE
    "q2",
    "floor_cent",
    "floor_euro",
    "ceil_euro",
    # US
    "USD_CENT",
    "ZERO_USD",
    "round_cents",
    "form_1040_whole_dollar_2025",
    "_require_non_negative",
    "_require_positive",
    "_require_unit_interval",
)
