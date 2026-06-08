"""Rev. Proc. 2024-40 § 3.11 AMT inflation tests, anchored to the IRS bulletin.

Authority:
- Rev. Proc. 2024-40 (https://www.irs.gov/pub/irs-drop/rp-24-40.pdf)
- 26 U.S.C. § 55(d) (exemption + phase-out)
- 26 U.S.C. § 55(b)(1) (26%/28% rate break)

Asserts the same numeric outcomes as the production module via the
shadow copy in law/usa/year_2025/rev_proc/proc_2024_40/p3_11.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.rev_proc.proc_2024_40.p3_11 import (
    AMT_EXEMPTION_MFJ_2025_USD,
    AMT_EXEMPTION_MFS_2025_USD,
    AMT_EXEMPTION_SINGLE_2025_USD,
    AMT_PHASEOUT_START_MFJ_2025_USD,
    AMT_PHASEOUT_START_MFS_2025_USD,
    AMT_PHASEOUT_START_SINGLE_2025_USD,
    AMT_RATE_BREAK_2025_USD,
    AMT_RATE_BREAK_MFS_2025_USD,
)
from tax_pipeline.y2025.us_law import (
    AMT_EXEMPTION_MFJ_2025_USD as ORIG_EXEMPTION_MFJ,
    AMT_EXEMPTION_MFS_2025_USD as ORIG_EXEMPTION_MFS,
    AMT_EXEMPTION_SINGLE_2025_USD as ORIG_EXEMPTION_SINGLE,
    AMT_PHASEOUT_START_MFJ_2025_USD as ORIG_PHASEOUT_MFJ,
    AMT_PHASEOUT_START_MFS_2025_USD as ORIG_PHASEOUT_MFS,
    AMT_PHASEOUT_START_SINGLE_2025_USD as ORIG_PHASEOUT_SINGLE,
    AMT_RATE_BREAK_2025_USD as ORIG_RATE_BREAK,
    AMT_RATE_BREAK_MFS_2025_USD as ORIG_RATE_BREAK_MFS,
)


class RevProc2024_40_P3_11_IdentityTest(unittest.TestCase):
    """Shadow copy must equal the production module byte-for-byte."""

    def test_exemption_single_matches_production(self) -> None:
        self.assertEqual(AMT_EXEMPTION_SINGLE_2025_USD, ORIG_EXEMPTION_SINGLE)

    def test_exemption_mfj_matches_production(self) -> None:
        self.assertEqual(AMT_EXEMPTION_MFJ_2025_USD, ORIG_EXEMPTION_MFJ)

    def test_exemption_mfs_matches_production(self) -> None:
        self.assertEqual(AMT_EXEMPTION_MFS_2025_USD, ORIG_EXEMPTION_MFS)

    def test_phaseout_single_matches_production(self) -> None:
        self.assertEqual(
            AMT_PHASEOUT_START_SINGLE_2025_USD, ORIG_PHASEOUT_SINGLE
        )

    def test_phaseout_mfj_matches_production(self) -> None:
        self.assertEqual(AMT_PHASEOUT_START_MFJ_2025_USD, ORIG_PHASEOUT_MFJ)

    def test_phaseout_mfs_matches_production(self) -> None:
        self.assertEqual(AMT_PHASEOUT_START_MFS_2025_USD, ORIG_PHASEOUT_MFS)

    def test_rate_break_matches_production(self) -> None:
        self.assertEqual(AMT_RATE_BREAK_2025_USD, ORIG_RATE_BREAK)

    def test_rate_break_mfs_matches_production(self) -> None:
        self.assertEqual(AMT_RATE_BREAK_MFS_2025_USD, ORIG_RATE_BREAK_MFS)


class RevProc2024_40_P3_11_StatuteTest(unittest.TestCase):
    """Numeric assertions against Rev. Proc. 2024-40 published amounts."""

    def test_exemption_amounts_2025(self) -> None:
        self.assertEqual(AMT_EXEMPTION_SINGLE_2025_USD, Decimal("88100"))
        self.assertEqual(AMT_EXEMPTION_MFJ_2025_USD, Decimal("137000"))
        # MFS = MFJ / 2 per § 55(d)(1)(C).
        self.assertEqual(AMT_EXEMPTION_MFS_2025_USD, Decimal("68500"))

    def test_phaseout_amounts_2025(self) -> None:
        self.assertEqual(
            AMT_PHASEOUT_START_SINGLE_2025_USD, Decimal("626350")
        )
        self.assertEqual(
            AMT_PHASEOUT_START_MFJ_2025_USD, Decimal("1252700")
        )
        self.assertEqual(
            AMT_PHASEOUT_START_MFS_2025_USD, Decimal("626350")
        )

    def test_mfs_phaseout_is_half_of_mfj(self) -> None:
        self.assertEqual(
            AMT_PHASEOUT_START_MFS_2025_USD * Decimal(2),
            AMT_PHASEOUT_START_MFJ_2025_USD,
        )

    def test_rate_break_amounts_2025(self) -> None:
        # 2025 26%/28% rate break, Rev. Proc. 2024-40 § 3.11.
        self.assertEqual(AMT_RATE_BREAK_2025_USD, Decimal("239100"))
        self.assertEqual(AMT_RATE_BREAK_MFS_2025_USD, Decimal("119550"))

    def test_mfs_rate_break_is_half_of_standard(self) -> None:
        # § 55(b)(1)(A)(ii)(II) — MFS rate break is half.
        self.assertEqual(
            AMT_RATE_BREAK_MFS_2025_USD * Decimal(2),
            AMT_RATE_BREAK_2025_USD,
        )


if __name__ == "__main__":
    unittest.main()
