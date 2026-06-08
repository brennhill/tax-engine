"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 28 (Schranken für die Inanspruchnahme der Vergünstigungen / Limitation on Benefits)
url: https://www.irs.gov/pub/irs-trty/germany.pdf
contains:
  - DBA-USA Art. 28(2)(c): publicly-traded company qualification
  - DBA-USA Art. 28(2)(a)/(f): qualified resident (incl. individuals)
  - DBA-USA Art. 28(4): active trade or business in the residence country
  - DBA-USA Art. 28(5)/(7): derivative-benefits qualification
  - DBA-USA Art. 28(7): competent-authority discretionary determination
  - LOB_QUALIFICATION_CATEGORIES: closed enum of supported qualification
    categories. ``not_qualified`` disables treaty re-sourcing and the
    engine fails closed if a treaty position is claimed without an Art. 28
    qualification.
numeric_constants: []
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20) — the
    LOB Article was substantively rewritten by the Protocol
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:29ab5eb88a45d4e3f0168017cbfe75fc93d546424978f640f64bcd105214eafd
---
"""
# Shadow extraction of DBA-USA Art. 28 (Phase 5 treaty article). Mirrors
# ``tax_pipeline.y2025.treaty_law`` byte-for-byte. The Article 28 LOB
# qualification gate is consumed by ``treaty25_lob_qualification`` in
# ``tax_pipeline.y2025.treaty_rules``; that rule fails closed when the
# taxpayer asserts treaty re-sourcing without an Art. 28 qualifying
# category.
from __future__ import annotations

# DBA-USA Art. 28 authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_28_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"

# Closed enum of supported LOB qualification categories. ``not_qualified``
# disables treaty re-sourcing; the engine fails closed if a treaty
# position is claimed without an Art. 28 qualification.
# https://www.irs.gov/pub/irs-trty/germany.pdf
LOB_QUALIFICATION_CATEGORIES = (
    "publicly_traded",
    "qualified_resident",
    "active_business",
    "derivative_benefits",
    "competent_authority",
    "not_qualified",
)
