"""
---
jurisdiction: DE
tax_year: 2025
statute: § 25 EStG (Veranlagungszeitraum, Steuererklärungspflicht)
url: https://www.gesetze-im-internet.de/estg/__25.html
contains:
  - § 25 Abs. 1 EStG: assessment period = calendar year
  - Citation surface only — assessment-period gating lives in
    tax_pipeline.y2025.germany_inputs (loader-side validation).
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:5d6b09efb0b4002d043bfa5af26b918401ca2cd06baac084762033e4c5b857f4
---
"""
# Shadow extraction of § 25 EStG (filing-posture authority). Cite-only.
from __future__ import annotations

ESTG_25_URL = "https://www.gesetze-im-internet.de/estg/__25.html"

ESTG_25_ABS_1_CITATION = "§ 25 Abs. 1 EStG (Veranlagungszeitraum: Kalenderjahr)"

__all__ = ("ESTG_25_URL", "ESTG_25_ABS_1_CITATION")
