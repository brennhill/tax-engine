"""
---
jurisdiction: DE
tax_year: 2025
statute: § 26 EStG (Veranlagung von Ehegatten)
url: https://www.gesetze-im-internet.de/estg/__26.html
contains:
  - § 26 Abs. 1 EStG: spouses with valid Ehe and unbeschränkte Steuerpflicht
  - § 26 Abs. 2 EStG: Wahlrecht — Zusammenveranlagung vs. Einzelveranlagung
  - § 26 Abs. 3 EStG: default Zusammenveranlagung when no election declared
  - Citation surface only — posture validation lives in
    tax_pipeline.y2025.germany_inputs (loader-side fail-closed gating).
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:8efcdb219bdcfcafc7b1ef7d9ed203f653ce61e404d3ff18a5e3c903979c0be4
---
"""
# Shadow extraction of § 26 EStG (filing-posture authority). Cite-only.
from __future__ import annotations

ESTG_26_URL = "https://www.gesetze-im-internet.de/estg/__26.html"

ESTG_26_ABS_1_CITATION = "§ 26 Abs. 1 EStG (Voraussetzungen Ehegattenveranlagung)"
ESTG_26_ABS_2_CITATION = "§ 26 Abs. 2 EStG (Wahlrecht Zusammen- vs. Einzelveranlagung)"
ESTG_26_ABS_3_CITATION = "§ 26 Abs. 3 EStG (Default Zusammenveranlagung)"

__all__ = (
    "ESTG_26_URL",
    "ESTG_26_ABS_1_CITATION",
    "ESTG_26_ABS_2_CITATION",
    "ESTG_26_ABS_3_CITATION",
)
