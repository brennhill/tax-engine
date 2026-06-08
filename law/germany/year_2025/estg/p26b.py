"""
---
jurisdiction: DE
tax_year: 2025
statute: § 26b EStG (Zusammenveranlagung von Ehegatten)
url: https://www.gesetze-im-internet.de/estg/__26b.html
contains:
  - § 26b EStG: spouses' incomes are aggregated, treated jointly as one
    Steuerpflichtiger; Splittingverfahren applies via § 32a Abs. 5 EStG.
  - Citation surface only — Zusammenveranlagung wiring lives in
    tax_pipeline.y2025.germany_inputs and the per-stage rule bodies; the
    actual Splitting math lives in p32a.py.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:87faf61bff91b1cbcf4214ab5681443f6d63b02f791d530728093b2f66e4cd76
---
"""
# Shadow extraction of § 26b EStG (filing-posture authority). Cite-only.
from __future__ import annotations

ESTG_26B_URL = "https://www.gesetze-im-internet.de/estg/__26b.html"

ESTG_26B_CITATION = (
    "§ 26b EStG (Zusammenveranlagung — Ehegatten gelten gemeinsam als ein"
    " Steuerpflichtiger; Splitting nach § 32a Abs. 5 EStG)"
)

__all__ = ("ESTG_26B_URL", "ESTG_26B_CITATION")
