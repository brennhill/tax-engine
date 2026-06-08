"""
---
jurisdiction: DE
tax_year: 2025
statute: § 26a EStG (Einzelveranlagung von Ehegatten)
url: https://www.gesetze-im-internet.de/estg/__26a.html
contains:
  - § 26a Abs. 1 EStG: each spouse's own income, no household aggregation
  - § 26a Abs. 2 EStG: Sonderausgaben split helper (§§ 10/10a/10b/33/33a/33b)
  - Citation surface only — Einzelveranlagung wiring lives in
    tax_pipeline.y2025.germany_inputs and the per-stage rule bodies.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:243c54b29a766449f40ce4e2c2f93cfe6e62ddc0901cd9e944eb75f6b2f95a69
---
"""
# Shadow extraction of § 26a EStG (filing-posture authority). Cite-only.
# (No URL constant exists in production for § 26a — the canonical URL
# string is asserted in the statute test below.)
from __future__ import annotations

ESTG_26A_URL = "https://www.gesetze-im-internet.de/estg/__26a.html"

ESTG_26A_ABS_1_CITATION = "§ 26a Abs. 1 EStG (Einzelveranlagung — eigene Einkünfte)"
ESTG_26A_ABS_2_CITATION = "§ 26a Abs. 2 EStG (Sonderausgaben-Aufteilung Einzelveranlagung)"

__all__ = (
    "ESTG_26A_URL",
    "ESTG_26A_ABS_1_CITATION",
    "ESTG_26A_ABS_2_CITATION",
)
