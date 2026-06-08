"""
---
jurisdiction: DE
tax_year: 2025
statute: § 31 EStG (Familienleistungsausgleich)
url: https://www.gesetze-im-internet.de/estg/__31.html
contains:
  - § 31 Satz 1 EStG: Familienleistungsausgleich purpose
  - § 31 Satz 4 EStG: Kindergeld add-back when Freibetrag elected (Günstigerprüfung)
  - Citation surface only — Günstigerprüfung composition lives in
    compositions/DE25-CHILDREN-CREDITS.py for now.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:9498de9ad64941d472a3be3abbf22cd6d6e3f4d360e54810b2e612cde0ab449a
---
"""
# Shadow extraction of § 31 EStG (Phase 3 composing §). This file is
# CITE-ONLY: the Günstigerprüfung (Kindergeld vs. Kinderfreibetrag
# preference test) is implemented in
# ``tax_pipeline/y2025/germany_children_rules.py`` as a Pipeline 2 stage
# composition and will move under ``law/germany/year_2025/compositions/``
# in MIGRATION.md Phase 4. The role of this file is to surface the
# canonical statute URL and citation strings under the per-§ audit unit.
#
# Authority: § 31 EStG (Familienleistungsausgleich, Günstigerprüfung).
# Satz 4: when the Freibetrag deduction's tax savings exceed Kindergeld
# received, the Freibetrag is applied and Kindergeld is added back to
# assessed tax-due (treated as advance payment).
# https://www.gesetze-im-internet.de/estg/__31.html
from __future__ import annotations

# § 31 EStG canonical URL (re-exported for narrative templates and audit
# packets that look up the URL by §-label).
ESTG_31_URL = "https://www.gesetze-im-internet.de/estg/__31.html"

# § 31 EStG citation string used by trace metadata.
ESTG_31_CITATION = "§ 31 EStG (Familienleistungsausgleich, Günstigerprüfung)"

# § 31 Satz 4 EStG citation — used by DE25-22-FINAL-REFUND when Kindergeld
# is added back to assessed tax-due after a Freibetrag election.
ESTG_31_SATZ_4_CITATION = "§ 31 Satz 4 EStG (Kindergeld-Hinzurechnung bei Freibetrag-Wahl)"

__all__ = ("ESTG_31_URL", "ESTG_31_CITATION", "ESTG_31_SATZ_4_CITATION")
