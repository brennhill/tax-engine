"""
---
jurisdiction: DE
tax_year: 2025
statute: § 36 EStG (Entstehung und Tilgung der Einkommensteuer)
url: https://www.gesetze-im-internet.de/estg/__36.html
contains:
  - § 36 Abs. 2 EStG: refund balance + advance-payment netting (cite-only)
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:c29450c7fd8f9718e73a0c35f51dfab5207725d4849712a897b3273ab9aeb4c3
---
"""
# Shadow extraction of § 36 EStG (Phase 3 composing §). This file is
# CITE-ONLY: the actual refund netting (assessed tax due vs. withheld
# wage tax + Vorauszahlungen + Kindergeld add-back) lives in
# ``tax_pipeline/y2025/germany_final_rules.py`` as the
# DE25-22-FINAL-REFUND composition. It will move under
# ``law/germany/year_2025/compositions/`` in MIGRATION.md Phase 4.
#
# Authority: § 36 Abs. 2 EStG (refund balance crediting only actual
# non-negative withholdings and prepayments).
# https://www.gesetze-im-internet.de/estg/__36.html
from __future__ import annotations

# § 36 EStG canonical URL (re-exported for narrative templates / audit
# packets).
ESTG_36_URL = "https://www.gesetze-im-internet.de/estg/__36.html"

# § 36 Abs. 2 EStG citation string.
ESTG_36_ABS_2_CITATION = "§ 36 Abs. 2 EStG (Anrechnung der Vorauszahlungen und Steuerabzugsbeträge)"

__all__ = ("ESTG_36_URL", "ESTG_36_ABS_2_CITATION")
