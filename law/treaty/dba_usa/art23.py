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
  - DBA-USA Art. 23(5): special block for a U.S. citizen who is a
    resident of the Federal Republic of Germany, with three operative
    sub-paragraphs the engine relies on:
      * Art. 23(5)(a): Germany credits only the U.S. tax the treaty
        permits (not the U.S. citizenship-based tax)
      * Art. 23(5)(b): the United States allows a credit against U.S.
        tax for the German income tax paid on the re-sourced items
        (the §§ 901-905 credit, subject to the Pub. 514 limitation)
      * Art. 23(5)(c): the re-sourcing rule — those items are "deemed
        to arise" in the Federal Republic of Germany for purposes of
        the U.S. FTC limitation; this underpins IRS Pub. 514's
        average-tax-rate worksheet (lines 16-21)
  - DBA-USA Art. 1(4): saving clause (the United States may tax its
    citizens as if the Convention had not entered into force), and
    Art. 1(5)(a): the exception that preserves the Art. 23(5) benefits
    for U.S. citizens notwithstanding the saving clause
numeric_constants: []
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:20fc9f3b15e924f1e12350552973f736ea0d61d4e29988c32628bb2e0da9373c
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
