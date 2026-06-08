"""
---
jurisdiction: DE
tax_year: 2025
statute: § 3 SolzG 1995 (Bemessungsgrundlage und zeitliche Anwendung)
url: https://www.gesetze-im-internet.de/solzg_1995/__3.html
contains:
  - § 3 SolzG 1995: Soli is assessed on the festgesetzte Einkommensteuer /
    Lohnsteuer / Kapitalertragsteuer base; the percentage rate appears in
    § 4 SolzG. The 5,5 % rate is conventionally referenced as a § 3/§ 4
    pair (the assessment base is § 3, the percentage is § 4). The rate
    constant lives here so callers can address "the SolzG rate" with one
    URL even though the percentage itself is set by § 4 SolzG.
numeric_constants:
  - SOLI_RATE: 0.055  # § 4 Satz 1 SolzG 1995, paired with § 3 base
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:5707a51a6bd3b1fbcae4d0c44a176fff52e399677a88aeee3a8538aa2a2341c5
---
"""
# Shadow extraction of § 3 SolzG 1995 base (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte. The rate value is the
# § 4 Satz 1 SolzG 1995 percentage that applies to the § 3 base; the §
# 4 Freigrenze + Milderungszone live in ``solzg/p4.py``.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

D = Decimal

# § 4 Satz 1 SolzG 1995: 5,5 % solidarity-surcharge rate applied to the
# § 3 SolzG 1995 assessment base (festgesetzte Einkommensteuer /
# Lohnsteuer / Kapitalertragsteuer).
# https://www.gesetze-im-internet.de/solzg_1995/__3.html
# https://www.gesetze-im-internet.de/solzg_1995/__4.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
SOLI_RATE = _CONSTANTS["SOLI_RATE"]
