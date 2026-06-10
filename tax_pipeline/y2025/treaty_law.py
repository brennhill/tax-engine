"""
Single source of truth for the U.S.–Germany income-tax treaty (DBA-USA)
2025 portfolio-dividend constants.

Authority
- DBA-USA (Germany–United States Convention for the Avoidance of Double
  Taxation, Income and Capital, signed 1989, amended 2006 Protocol),
  Art. 10(2)(b): the source state's tax on portfolio dividends paid to a
  resident of the other state may not exceed 15 % of the gross dividend.
  Bilingual treaty text: https://www.irs.gov/pub/irs-trty/germany.pdf
  Tech explanation:    https://www.irs.gov/pub/irs-trty/germtech.pdf
- DBA-USA Art. 23 governs elimination of double taxation. For a U.S.
  citizen resident in Germany, the operative sub-paragraphs are
  Art. 23(5)(c) (the re-sourcing rule — U.S.-source items are "deemed to
  arise" in Germany for U.S. FTC-limitation purposes), Art. 23(5)(b)
  (the U.S. credit for the German tax on those items) and Art. 23(5)(a)
  (Germany credits only the treaty-permitted U.S. tax). See the canonical
  citation constants below.

Why a separate module
- The 15 % rate is a single legal fact that belongs to one statute. Both
  jurisdictional law modules (germany_2025_law.py, us_2025_law.py) and
  the cross-border derivation/bridge code consume it. Centralizing here
  forces every callsite to dereference the same Decimal, eliminating the
  fail-closed risk that one literal drifts.

This module is statute-only. It does NOT do tax math. Computations that
apply the rate live in:
- tax_pipeline/y2025/derive_treaty_dividend_items.py (Pub. 514 derivation)
- tax_pipeline/y2025/treaty_bridge.py (USD ceiling clip)
- tax_pipeline/y2025/us_law.py (Pub. 514 worksheet line 18)
- tax_pipeline/y2025/germany_law.py (per-Posten residence credit cap)
"""
from __future__ import annotations

from decimal import Decimal

from tax_pipeline._law_data import LAW_DATA as _LAW_DATA

# DBA-USA Art. 10(2)(b) — 15 % source-state cap on portfolio dividends.
# This is the single canonical declaration of the rate. Every other
# module imports from here. Per New-1 (2026-05-10 platform-flexibility
# review) the value lives in law/treaty/dba_usa/art10.toml; updating
# the rate requires re-signing the TOML via
# ``python -m law.audit sign law/treaty/dba_usa/art10.toml``.
DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE = _LAW_DATA["DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE"]

# DBA-USA Art. 10(2)(b) authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_10_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"

# DBA-USA Technical Explanation (IRS).
DBA_USA_TECH_EXPLANATION_URL = "https://www.irs.gov/pub/irs-trty/germtech.pdf"

# DBA-USA Art. 23 — elimination of double taxation. Art. 23(5)(c) is the
# re-sourcing rule that underpins IRS Pub. 514's treaty re-sourcing
# worksheet (lines 16-19) for U.S. citizens resident in Germany.
DBA_USA_ART_23_URL = DBA_USA_ART_10_URL  # same treaty document

# --- Canonical DBA-USA Art. 23(5) / Art. 1 citation strings -----------------
# Single source of truth for the paragraph letters so they cannot drift
# between modules (the BLOCKER closed here was half the codebase citing
# "Art. 23(5)(b)" and half citing "Art. 23(3)" for the same re-sourcing
# rule — neither was correct). Per the 1989 treaty as amended by the 2006
# Protocol, Art. 23(5) is the special block for a U.S. citizen resident in
# Germany. New code should reference these constants rather than spelling
# the paragraph out inline. Authority: bilingual treaty text
# https://www.irs.gov/pub/irs-trty/germany.pdf and Technical Explanation
# https://www.irs.gov/pub/irs-trty/germtech.pdf.
#
#   Art. 23(5)(a) — Germany credits only the U.S. tax the treaty permits
#                   (not the U.S. citizenship-based tax)
#   Art. 23(5)(b) — the United States credits the German income tax paid
#                   on the re-sourced items (§§ 901-905, Pub. 514 limited)
#   Art. 23(5)(c) — the re-sourcing rule: those items are "deemed to
#                   arise" in Germany for U.S. FTC-limitation purposes
DBA_USA_ART_23_5_A_DE_CREDIT = "DBA-USA Art. 23(5)(a)"
DBA_USA_ART_23_5_B_US_CREDIT = "DBA-USA Art. 23(5)(b)"
DBA_USA_ART_23_5_C_RESOURCING = "DBA-USA Art. 23(5)(c)"
# Saving clause and the exception that preserves Art. 23(5) for citizens.
DBA_USA_ART_1_4_SAVING_CLAUSE = "DBA-USA Art. 1(4)"
DBA_USA_ART_1_5_A_SAVING_EXCEPTION = "DBA-USA Art. 1(5)(a)"

# DBA-USA Art. 28 (Limitation on Benefits, as amended by the 2006
# Protocol) — treaty benefits (including the Art. 23 / Pub. 514
# resourcing relief) require LOB qualification under one of the
# enumerated tests. For an individual U.S. citizen / long-term resident
# of Germany, Art. 28(2)(a) (qualified resident — individual) typically
# applies. The five paragraph categories are:
#   - Art. 28(2)(c) publicly traded company
#   - Art. 28(2)(a)/(f) qualified resident (incl. individuals)
#   - Art. 28(4) active business (active trade or business in residence
#     country)
#   - Art. 28(5)/(7) derivative benefits
#   - Art. 28(7) competent authority discretionary determination
# A treaty position must declare which paragraph qualifies the
# taxpayer; absent qualification, treaty benefits are disallowed and
# Form 8833 disclosure under § 6114 is the defensive posture.
DBA_USA_ART_28_URL = DBA_USA_ART_10_URL  # same treaty document

# Closed enum of supported LOB qualification categories. ``not_qualified``
# disables treaty re-sourcing; the engine fails closed if a treaty
# position is claimed without an Art. 28 qualification.
LOB_QUALIFICATION_CATEGORIES = (
    "publicly_traded",
    "qualified_resident",
    "active_business",
    "derivative_benefits",
    "competent_authority",
    "not_qualified",
)
