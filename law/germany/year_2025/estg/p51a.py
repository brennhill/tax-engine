"""
---
jurisdiction: DE
tax_year: 2025
statute: § 51a EStG (Festsetzung und Erhebung von Zuschlagsteuern)
url: https://www.gesetze-im-internet.de/estg/__51a.html
contains:
  - § 51a Abs. 1-2 EStG: Kirchensteuer attached as 8 % / 9 % of assessed
    Einkommensteuer for taxpayers who belong to a recognized
    Religionsgemeinschaft. The 2025 engine does NOT model Kirchensteuer —
    the only role of this file is to carry the canonical "no membership"
    sentinel set so the loader can fail closed when membership is asserted.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:7ad893eba9309c222ee51744965b1ee36668d76d21bb089b20bcd99fb29a953a
---
"""
# Shadow extraction of § 51a EStG (Phase 2 leaf §). The Kirchensteuer
# rate (8 % / 9 %) is NOT modeled by this engine; the only piece bound to
# § 51a EStG that lives in code is the "no membership" sentinel set.
#
# Authority: § 51a EStG.
# https://www.gesetze-im-internet.de/estg/__51a.html
from __future__ import annotations

# § 51a EStG attaches Kirchensteuer at 8 % or 9 % of assessed
# Einkommensteuer for taxpayers belonging to a recognized
# Religionsgemeinschaft. The 2025 model does not yet implement
# Kirchensteuer, so it must fail closed if a taxpayer asserts
# membership.
# https://www.gesetze-im-internet.de/estg/__51a.html
KIRCHENSTEUER_NONE_VALUES = {"none", "no", "keine", "nicht_mitglied"}
