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
- DBA-USA Art. 23 governs elimination of double taxation; Art. 23(5)(b)
  allows the residence state to re-source income for FTC purposes.

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

# DBA-USA Art. 23 — elimination of double taxation; Art. 23(5)(b) is the
# re-sourcing rule that underpins IRS Pub. 514's treaty re-sourcing
# worksheet (lines 16-19) for U.S. citizens resident in Germany.
DBA_USA_ART_23_URL = DBA_USA_ART_10_URL  # same treaty document

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
