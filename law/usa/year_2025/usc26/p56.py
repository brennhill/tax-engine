"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 56 (Alternative Minimum Tax — adjustments)
url: https://www.law.cornell.edu/uscode/text/26/56
contains:
  - § 56(a)/(b): AMTI add-backs (state/local-tax itemized deduction,
    depreciation timing differences, ISO bargain element, NOL
    adjustments). The AMTI assembly itself lives in the
    composition-layer rule (US25-AMT-AMTI) which consumes regular-tax
    taxable income and adds the § 56 items; this file is the law-layer
    citation anchor for that assembly.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:a6d5638c31e474d2614ae269ac5a54cb20c2a4ce47808f1f9377683a7f778be9
---
"""
# Shadow extraction of § 56 citation surface (Phase 3 composing §).
# The production module references § 56 via URL constant only; the
# AMTI add-back assembly lives in the rule-graph composition (Phase 4).
#
# Authority: 26 U.S.C. § 56 — adjustments in computing AMTI.
# https://www.law.cornell.edu/uscode/text/26/56
from __future__ import annotations

USC_56_URL = "https://www.law.cornell.edu/uscode/text/26/56"

__all__ = ("USC_56_URL",)
