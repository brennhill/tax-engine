"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 59 (Alternative Minimum Tax Foreign Tax Credit)
url: https://www.law.cornell.edu/uscode/text/26/59
contains:
  - § 59(a): AMTFTC parallels § 904(d) per-category limitation but uses
    the AMTI base. The AMTFTC computation itself lives in the rule-
    graph composition (US25-AMT-FTC-AND-COMPARE); this file is the
    law-layer citation anchor.
numeric_constants: []
imports_from:
  - law/usa/year_2025/usc26/p55.py: § 55 dependency (AMTFTC plugs into
    amt_owed_2025 via the regular-tax-after-FTC baseline)
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:b03fc2555394a0befefe408029dea1036ffbdb863e57b64c2655aa19326bb5a8
---
"""
# Shadow extraction of § 59 citation surface (Phase 3 composing §).
# The production module references § 59 via URL constant only; the
# AMTFTC computation lives in the rule-graph composition (Phase 4)
# where ``allowed_ftc_2025`` is re-run on the AMTI base and routed
# into ``amt_owed_2025`` (which lives in ``p55.py``).
#
# Authority: 26 U.S.C. § 59 — alternative minimum tax foreign tax
# credit (AMTFTC).
# https://www.law.cornell.edu/uscode/text/26/59
from __future__ import annotations

USC_59_URL = "https://www.law.cornell.edu/uscode/text/26/59"

__all__ = ("USC_59_URL",)
