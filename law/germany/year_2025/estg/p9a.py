"""
---
jurisdiction: DE
tax_year: 2025
statute: § 9a EStG (Pauschbeträge für Werbungskosten)
url: https://www.gesetze-im-internet.de/estg/__9a.html
contains:
  - § 9a Satz 1 Nr. 1 lit. a EStG: Arbeitnehmer-Pauschbetrag €1,230
numeric_constants:
  - WORKER_ALLOWANCE_PER_PERSON_EUR: 1230.00  # § 9a Satz 1 Nr. 1 lit. a EStG
amended_by:
  - Steuerentlastungsgesetz 2022 (BGBl. I 2022 S. 749) — increase to €1,200
  - Inflationsausgleichsgesetz 2022 (BGBl. I 2022 S. 2230) — increase to €1,230 from 2023
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:26ff31dccaac8e153e40a273bbf3bbdd69ad84aa130964b3c0a3f8d45799bdd0
---
"""
# Shadow extraction of § 9a EStG Arbeitnehmer-Pauschbetrag (Phase 2 leaf §).
# Mirrors ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants

D = Decimal

# § 9a Satz 1 Nr. 1 lit. a EStG: Arbeitnehmer-Pauschbetrag €1,230 per
# person, applied to § 19 wage income whenever the actual Werbungskosten
# under § 9 EStG do not exceed it. Carries forward unchanged from 2023
# (Inflationsausgleichsgesetz, BGBl. I 2022 S. 2230) into 2025.
# https://www.gesetze-im-internet.de/estg/__9a.html
# Statutory constants live in the sibling .toml data file (F1, see
# .review/2026-05-08-platform-flexibility-review.md): year-on-year roll-
# forward edits the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
WORKER_ALLOWANCE_PER_PERSON_EUR = _CONSTANTS["WORKER_ALLOWANCE_PER_PERSON_EUR"]
