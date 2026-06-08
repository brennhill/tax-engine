"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 23 (Vermeidung der Doppelbesteuerung / Elimination of Double Taxation)
url: https://www.irs.gov/pub/irs-trty/germany.pdf
contains:
  - DBA-USA Art. 23(2): Germany's residence-country relief mechanism
    (Anrechnungsmethode for U.S.-source items not exempted under another
    Article; Freistellungsmethode for items expressly exempted)
  - DBA-USA Art. 23(3): U.S. residence-country credit for German source
    tax under §§ 901-905 (subject to Pub. 514 limitation)
  - DBA-USA Art. 23(5)(b): treaty re-sourcing rule that treats
    U.S.-source income as foreign source for purposes of the U.S. FTC
    when paid to a U.S. citizen resident in Germany — underpins IRS
    Pub. 514's average-tax-rate worksheet (lines 16-21)
numeric_constants: []
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:a6a750e4fb93bc5f1e5ac63f742cc0866920d4b3a4ee7f743543c403a2046f89
---
"""
# Shadow extraction of DBA-USA Art. 23 (Phase 5 treaty article). The
# numeric resourcing logic — Pub. 514 worksheet lines 16/17/18/19/20c/21 —
# lives in ``pub_514_average_tax.py`` because it crosses jurisdictions
# (it consumes both U.S. taxable income and Germany's residence-country
# precredit / residence-credit on the same U.S.-source dividend stack).
# This file carries the Article's citation surface for audit packets.
from __future__ import annotations

# DBA-USA Art. 23 authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_23_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"
