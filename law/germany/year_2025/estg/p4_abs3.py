"""
---
jurisdiction: DE
tax_year: 2025
statute: § 4 Abs. 3 EStG (Einnahmenüberschussrechnung / cash-basis profit) with § 18 EStG (selbständige Arbeit)
url: https://www.gesetze-im-internet.de/estg/__4.html
contains:
  - § 4 Abs. 3 Satz 1 EStG: a self-employed person not required to keep
    books may compute profit as the excess of operating receipts
    (Betriebseinnahmen) over operating expenses (Betriebsausgaben) —
    the cash-basis Einnahmenüberschussrechnung (Zufluss-Abfluss-Prinzip).
    The net may be negative (a Verlust that offsets other income under
    § 2 Abs. 3 EStG); it is not floored at zero.
  - § 18 EStG: this Gewinn is the Einkünfte aus selbständiger Arbeit
    (§ 2 Abs. 2 Satz 1 Nr. 1 EStG) joining the Summe der Einkünfte.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-8
audited_on: 2026-06-12
audit_hash: sha256:b2195e6d278e6c1e2748611221c15ed18298e2084c7c036179ca5c279431141f
---
"""
# Shadow extraction of § 4 Abs. 3 EStG Einnahmenüberschussrechnung
# (Phase 1 freelancer support, FREELANCER-DE-EUER-SLICE-SPEC.md). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. Pure arithmetic — no
# statutory constant; the legal content is the netting rule itself
# (Gewinn = Betriebseinnahmen − Betriebsausgaben) and its cash-basis
# recognition. Registered to the DE25-EUER stage. Verified 2026-06-10
# against gesetze-im-internet.
# https://www.gesetze-im-internet.de/estg/__4.html
from __future__ import annotations

# Money primitive (not legal math; LOCK.md § 1) shared with production.
from law._utils.money import q2

# Re-use production dataclasses + the controlling-authority string + the
# validation primitive so shadow output instances compare equal to
# production output under unittest.assertEqual.
from tax_pipeline.y2025.germany_law import (
    EUER_LEGAL_BASIS,
    GermanyEuerInputs2025,
    GermanyEuerResult2025,
    _require_non_negative_decimal,
)

ESTG_4_ABS3_URL = "https://www.gesetze-im-internet.de/estg/__4.html"
ESTG_18_URL = "https://www.gesetze-im-internet.de/estg/__18.html"


def euer_net_profit_2025(*, inputs: GermanyEuerInputs2025) -> GermanyEuerResult2025:
    """Compute the § 4 Abs. 3 EStG EÜR net profit (cash-basis).

    Pure function of its declared inputs. Receipts and expenses must each
    be non-negative; the net (receipts − expenses) may be negative — a
    Verlust that offsets other income under § 2 Abs. 3 EStG, so it is NOT
    floored at zero.

    Authority: § 4 Abs. 3 Satz 1 EStG; § 18 EStG.
    https://www.gesetze-im-internet.de/estg/__4.html
    """
    _require_non_negative_decimal(
        inputs.operating_receipts_eur, label="operating_receipts_eur"
    )
    _require_non_negative_decimal(
        inputs.operating_expenses_eur, label="operating_expenses_eur"
    )
    receipts = q2(inputs.operating_receipts_eur)
    expenses = q2(inputs.operating_expenses_eur)
    return GermanyEuerResult2025(
        operating_receipts_eur=receipts,
        operating_expenses_eur=expenses,
        net_profit_eur=q2(receipts - expenses),
        legal_basis=EUER_LEGAL_BASIS,
    )


__all__ = (
    "ESTG_4_ABS3_URL",
    "ESTG_18_URL",
    "euer_net_profit_2025",
)
