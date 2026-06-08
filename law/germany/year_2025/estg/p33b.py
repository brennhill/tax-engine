"""
---
jurisdiction: DE
tax_year: 2025
statute: § 33b EStG (Pauschbeträge wegen Behinderung)
url: https://www.gesetze-im-internet.de/estg/__33b.html
contains:
  - § 33b Abs. 3 Satz 2 EStG: Pauschbetrag schedule by Grad der Behinderung
  - § 33b Abs. 3 Satz 3 EStG: erhöhter Pauschbetrag €7,400 (hilflos / blind)
  - § 33b Abs. 5 EStG: per-child Pauschbetrag transferral
  - § 33b Abs. 6 EStG: Pflegegrad 4/5 → routes to Satz 3 amount
numeric_constants:
  - BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR (GdB 20-100)
  - BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR: 7400.00
amended_by:
  - Behinderten-Pauschbetragsgesetz, BGBl. I 2020 S. 2770 (2021 doubling carried into 2025)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:63b96cf6beef46ed82de3112f2ada0a20ac4fd5b7085f7f8c5f1b3d1e50b728b
---
"""
# Shadow extraction of § 33b EStG (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.germany_law`` byte-for-byte.
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from law._utils.constants import load_constants, load_tables

D = Decimal

# § 33b Abs. 3 EStG Pauschbeträge by Grad der Behinderung (GdB). The 2021
# Behinderten-Pauschbetragsgesetz (BGBl. I 2020 S. 2770) doubled the
# rates effective 2021; the 2025 statute carries those rates unchanged.
# https://www.gesetze-im-internet.de/estg/__33b.html
# Statutory constants live in the sibling .toml data file: the scalar
# § 33b Abs. 3 Satz 3 EStG €7,400 erhöhter Pauschbetrag (F1, atomic
# constant) and the GdB-keyed Pauschbetrag schedule (W2.A / T1.2,
# table-shape="dict_int_decimal"). Year-on-year roll-forward edits
# the TOML, not this Python module.
_CONSTANTS = load_constants(Path(__file__).with_suffix(".toml"))
_TABLES = load_tables(Path(__file__).with_suffix(".toml"))
# § 33b Abs. 3 Satz 3 EStG erhöhter Pauschbetrag (€7,400) for hilflose
# (Merkzeichen H), blinde (Merkzeichen Bl), or Pflegegrad 4/5
# (§ 33b Abs. 6 EStG) taxpayers. Mutually exclusive with the GdB
# schedule under § 33b Abs. 3 Satz 2 EStG: the special amount supersedes
# the schedule when claimed.
BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR = _CONSTANTS["BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR"]
# § 33b Abs. 3 Satz 2 EStG: monotonically-increasing Pauschbetrag by
# Grad der Behinderung step (GdB 20 … 100 in increments of 10).
BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR: dict[int, Decimal] = dict(
    _TABLES["BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR"]
)
# Algebraic invariant: the Pauschbetrag schedule is monotonically
# increasing in GdB. A future amendment that breaks this monotone is
# almost certainly a typo (or a half-rolled re-keying), so fail closed
# at import time instead of letting a non-monotone Pauschbetrag escape
# into a return.
_GDB_KEYS = sorted(BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR)
for _prev, _next in zip(_GDB_KEYS, _GDB_KEYS[1:]):
    assert (
        BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[_next]
        > BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[_prev]
    ), (
        f"§ 33b Abs. 3 Satz 2 EStG: Pauschbetrag(GdB {_next}) must "
        f"strictly exceed Pauschbetrag(GdB {_prev})."
    )


def disability_pauschbetrag_2025(
    gdb_grade: int,
    *,
    helpless_or_blind: bool = False,
) -> Decimal:
    """§ 33b Abs. 3 EStG schedule lookup for a single GdB grade.

    Schedule (per § 33b Abs. 3 Satz 2 EStG):
        GdB < 20  → €0
        GdB 20    → €384
        GdB 30    → €620
        GdB 40    → €860
        GdB 50    → €1,140
        GdB 60    → €1,440
        GdB 70    → €1,780
        GdB 80    → €2,120
        GdB 90    → €2,460
        GdB 100   → €2,840

    Special branch (§ 33b Abs. 3 Satz 3 EStG, also § 33b Abs. 6 EStG):
    Merkzeichen H / Bl / Pflegegrad 4 oder 5 → €7,400.

    Non-decadic GdB grades round DOWN to the nearest valid step (so
    GdB 35 → €620, GdB 87 → €2,120). This mirrors the BMF EStH
    treatment.

    Authority: § 33b Abs. 3 Satz 2/3 EStG, § 33b Abs. 6 EStG,
    BGBl. I 2020 S. 2770.
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    if helpless_or_blind:
        return BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR
    if gdb_grade < 0 or gdb_grade > 100:
        raise ValueError(
            f"§ 33b Abs. 3 EStG: gdb_grade must be in [0, 100]; got {gdb_grade!r}."
        )
    if gdb_grade < 20:
        # § 33b Abs. 3 Satz 2 EStG attaches no Pauschbetrag below GdB
        # 20; the loader still accepts the value so a child's grade can
        # round-trip through intake without forcing a transfer claim.
        return D("0.00")
    # Round DOWN to the nearest decadic GdB step. BMF EStH treats a
    # higher attestation as attaching to the next-lower decadic slot
    # (e.g. GdB 35 attests to GdB 30) for the §-33b-Abs.-3-EStG amount.
    rounded_step = (gdb_grade // 10) * 10
    return BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[rounded_step]


def behinderung_pauschbetrag_2025(
    *,
    gdb: int,
    hilflos_or_blind: bool,
) -> Decimal:
    """§ 33b Abs. 3 EStG canonical taxpayer-side Pauschbetrag.

    Stricter than ``disability_pauschbetrag_2025``: only accepts
    multiples of 10 in [20, 100] (or hilflos/blind). Used by the
    DE25-BEHINDERUNG-PAUSCHBETRAG legal stage at the taxpayer boundary.

    Authority: § 33b Abs. 3 EStG.
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    # § 33b Abs. 3 EStG flat allowance by GdB tier; § 33b Abs. 3 Satz 3
    # EStG gives the special €7,400 amount for hilflose / blinde
    # Menschen. The two paths are mutually exclusive; the special amount
    # supersedes the GdB schedule when claimed.
    if hilflos_or_blind:
        return BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR
    if gdb <= 0:
        return D("0.00")
    if gdb % 10 != 0 or gdb < 20 or gdb > 100:
        raise ValueError(
            f"Unsupported Grad der Behinderung {gdb!r}; § 33b Abs. 3 EStG "
            "requires a multiple of 10 in [20, 100] or hilflos/blind status."
        )
    return BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[gdb]


def child_disability_pauschbetrag_for_transferral_2025(
    *,
    child: object,
    transfer_election_active: bool,
) -> Decimal:
    """§ 33b Abs. 5 EStG per-child Pauschbetrag transferral amount.

    Returns the per-child §-33b-Abs.-3 EStG Pauschbetrag that flows to
    the parents when the profile-level transferral election is active,
    and zero otherwise.

    Authority: § 33b Abs. 5 EStG (transferral); § 33b Abs. 3 EStG
    (per-grade schedule).
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    if not transfer_election_active:
        return D("0.00")
    return disability_pauschbetrag_2025(
        int(child.disability_gdb),
        helpless_or_blind=bool(child.disability_helpless_or_blind),
    )
