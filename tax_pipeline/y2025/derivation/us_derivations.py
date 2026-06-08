"""U.S. Pipeline 1 (Derivation) stages for the 2025 tax year.

Pipeline 1 contract per ``docs/invariant-migration-plan.md`` §1.5:
deterministic, typed transformations of raw 1099 / broker /
treaty-package inputs into canonical derived facts. NO legal
interpretation lives here — that stays in the existing US25-* stages
(Pipeline 2). Stage IDs are prefixed ``DERIVE-US25-``.

WS-5H lands this module empty. Future workstreams (the U.S. analog of
WS-5A / WS-5B) will register concrete derivation stages such as
``DERIVE-US25-CAPITAL-FACT-ASSEMBLY``. This module's factory below
returns ``()`` until those workstreams land.

Authority context: 1099 reporting taxonomy per 26 U.S.C. §§ 6042 /
6045 / 6049, IRS Pub. 550 capital-gain assembly conventions, IRS
Pub. 514 treaty resourcing per-line aggregation.
- https://www.irs.gov/publications/p550
- https://www.irs.gov/publications/p514
"""
from __future__ import annotations

from tax_pipeline.core.stages import LawRule


def usa_derivation_law_rules_2025() -> tuple[LawRule, ...]:
    """Return the U.S. Pipeline 1 rule set for tax year 2025.

    Empty in the WS-5H framework landing. Populated by future
    workstreams that promote U.S.-side derivations out of
    ``us_model.py`` / ``us_capital_workpaper.py`` orchestrator code.
    """
    return ()


__all__ = ["usa_derivation_law_rules_2025"]
