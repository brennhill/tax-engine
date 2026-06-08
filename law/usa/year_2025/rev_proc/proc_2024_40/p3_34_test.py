"""Rev. Proc. 2024-40 § 3.34 FEIE ceiling tests, anchored to the IRS bulletin.

Authority:
- Rev. Proc. 2024-40 § 3.34 (https://www.irs.gov/pub/irs-drop/rp-24-40.pdf)
- 26 U.S.C. § 911(b)(2)(D)

Asserts the same numeric outcome as the production module via the shadow
copy in law/usa/year_2025/rev_proc/proc_2024_40/p3_34.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.rev_proc.proc_2024_40.p3_34 import (
    SECTION_911_FEIE_2025_USD,
)
from tax_pipeline.y2025.us_law import (
    SECTION_911_FEIE_2025_USD as ORIG_FEIE,
)


class RevProc2024_40_P3_34_IdentityTest(unittest.TestCase):
    """Shadow copy must equal the production module byte-for-byte."""

    def test_feie_ceiling_matches_production(self) -> None:
        self.assertEqual(SECTION_911_FEIE_2025_USD, ORIG_FEIE)

    def test_feie_ceiling_is_130000_usd(self) -> None:
        # Rev. Proc. 2024-40 § 3.34 sets the 2025 FEIE annual ceiling at
        # $130,000.
        self.assertEqual(SECTION_911_FEIE_2025_USD, Decimal("130000"))


if __name__ == "__main__":
    unittest.main()
