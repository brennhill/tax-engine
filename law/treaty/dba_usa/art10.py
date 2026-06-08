"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 10 (Dividenden / Dividends)
url: https://www.irs.gov/pub/irs-trty/germany.pdf
contains:
  - DBA-USA Art. 10(2)(a): 5 % source-state cap on dividends paid to a
    company that holds ≥ 10 % of the voting stock of the paying company
    (direct-investment dividends) — cited only; the 2025 engine does not
    emit direct-investment positions and no numeric constant is declared
    here today (see scope note below).
  - DBA-USA Art. 10(2)(b): 15 % source-state cap on portfolio dividends
    paid to a resident of the other state
  - DBA-USA Art. 10(3)(b): 0 % source-state rate on dividends paid to a
    pension fund / certain qualified beneficial owners under the 2006
    Protocol's "zero-rate" rules — cited only (see scope note below).
numeric_constants:
  - DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE: 0.15         # canonical Art. 10(2)(b) constant
  - GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE: 0.15          # alias of the above (Germany-side caller convention)
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20)
audited_by: claude-opus-4-7
audited_on: 2026-05-11
audit_hash: sha256:ea4504565191ee83e02b3504f33b84e32f5dbdc393fb375275ba26b7e286f6ad
---
"""
# Shadow extraction of DBA-USA Art. 10 (Phase 5 treaty article). Mirrors
# ``tax_pipeline.y2025.treaty_law`` byte-for-byte. The 15 % rate is the
# canonical declaration; ``tax_pipeline.y2025.germany_law`` re-exports it
# under the alias ``GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE`` so all
# Germany-side callers dereference the same Decimal (invariant I1).
#
# Scope note (W1.A / T1.1, 2026-05-11): the Art. 10(2)(a) direct-
# investment 5 % rate and the Art. 10(3)(b) pension-fund 0 % rate were
# removed from the TOML and from this sidecar because the 2025 engine
# does not emit those position classes and the constants had no
# working-tree consumer (they appeared in the cite-only "audit
# surface" but in practice were orphans under the New-1 verifier
# report). When a future return adds a direct-investment or pension-
# fund dividend pathway, re-add the matching constant to art10.toml
# with its citation and wire it into the rule that applies the rate.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

D = Decimal

# DBA-USA Art. 10(2)(b) — 15 % source-state cap on portfolio dividends.
# This is the single canonical declaration of the rate. Every other
# module imports from here.
# https://www.irs.gov/pub/irs-trty/germany.pdf
# https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html?gtp=249348_list%253D2
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE = _CONSTANTS["DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE"]
GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE = DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE

# DBA-USA Art. 10(2)(b) authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_10_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"

# DBA-USA Technical Explanation (IRS).
DBA_USA_TECH_EXPLANATION_URL = "https://www.irs.gov/pub/irs-trty/germtech.pdf"
