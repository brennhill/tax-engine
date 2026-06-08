"""Rev. Proc. 2024-40 § 3.05 numeric tests, anchored to the IRS bulletin.

Authority:
- Rev. Proc. 2024-40 § 3.05 (https://www.irs.gov/pub/irs-drop/rp-24-40.pdf)
- 26 U.S.C. § 24(d)(1)(A) / § 24(h)(2)
- IRS Schedule 8812 (2025) instructions

Asserts the same numeric outcome as the production module via the shadow
copy in law/usa/year_2025/rev_proc/proc_2024_40/p3_05.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.rev_proc.proc_2024_40.p3_05 import (
    CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD,
)
from tax_pipeline.y2025.us_law import (
    CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD as ORIG_CAP,
)


class RevProc2024_40_P3_05_IdentityTest(unittest.TestCase):
    """Shadow copy must equal the production module byte-for-byte."""

    def test_refundable_cap_matches_production(self) -> None:
        self.assertEqual(CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD, ORIG_CAP)

    def test_refundable_cap_is_1700_usd(self) -> None:
        # Rev. Proc. 2024-40 § 3.05 sets the 2025 ACTC refundable cap at
        # $1,700 per qualifying child.
        self.assertEqual(
            CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD, Decimal("1700")
        )


if __name__ == "__main__":
    unittest.main()
