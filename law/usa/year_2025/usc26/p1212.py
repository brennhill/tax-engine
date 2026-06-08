"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 1212 (Capital loss carrybacks and carryovers)
url: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212&num=0&edition=prelim
contains:
  - § 1212(b): individual capital-loss carryforward into subsequent
    tax years (no carryback for individuals; the unused loss carries
    forward indefinitely until exhausted).
  - The arithmetic that consumes § 1212 lives in
    ``compute_capital_assessment_2025`` (capital-buckets composition):
    after § 1211(b) limits the deduction, the residual flows to
    ``tentative_capital_loss_carryforward_2026_usd``. This file is
    therefore a citation anchor at the law layer.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:c831a5bfb93fd4a8c66015c7709847df1690e44b1d23cf9b20747ec2b1dd2b04
---
"""
# Shadow extraction of § 1212 carryover citation surface (Phase 2 leaf §).
# Mirrors ``tax_pipeline.y2025.us_law``: § 1212 has no standalone math
# helper at the law layer (the carryforward residual is computed in
# ``compute_capital_assessment_2025``).
#
# Authority: 26 U.S.C. § 1212(b) — individual capital-loss carryover.
# https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212
from __future__ import annotations

USC_1212_URL = (
    "https://uscode.house.gov/view.xhtml?req=granuleid:"
    "USC-prelim-title26-section1212&num=0&edition=prelim"
)

__all__ = ("USC_1212_URL",)
