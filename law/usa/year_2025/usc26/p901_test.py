"""§ 901 FTC mechanism tests.

Authority:
- 26 U.S.C. § 901 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901)
- 26 U.S.C. § 905 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905)

Asserts identity with ``tax_pipeline.y2025.us_law.allowed_ftc_2025``.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p901 import (
    USC_901_URL,
    USC_905_URL,
    allowed_ftc_2025,
)
from tax_pipeline.y2025.us_law import (
    USC_901_URL as ORIG_901,
    USC_905_URL as ORIG_905,
    allowed_ftc_2025 as orig_fn,
)


class P901IdentityTest(unittest.TestCase):
    def test_urls_match_production(self) -> None:
        self.assertEqual(USC_901_URL, ORIG_901)
        self.assertEqual(USC_905_URL, ORIG_905)

    def test_limitation_binds_when_available_exceeds(self) -> None:
        kwargs = dict(
            limitation_usd=Decimal("10000.00"),
            current_year_foreign_tax_usd=Decimal("8000.00"),
            carryover_usd=Decimal("5000.00"),
        )
        shadow = allowed_ftc_2025(**kwargs)
        prod = orig_fn(**kwargs)
        self.assertEqual(shadow, prod)
        # available = $13,000; limitation $10,000 binds.
        self.assertEqual(shadow, (Decimal("10000.00"), Decimal("13000.00")))

    def test_available_binds_when_limitation_exceeds(self) -> None:
        kwargs = dict(
            limitation_usd=Decimal("20000.00"),
            current_year_foreign_tax_usd=Decimal("8000.00"),
            carryover_usd=Decimal("5000.00"),
        )
        shadow = allowed_ftc_2025(**kwargs)
        prod = orig_fn(**kwargs)
        self.assertEqual(shadow, prod)
        # available = $13,000 binds.
        self.assertEqual(shadow, (Decimal("13000.00"), Decimal("13000.00")))

    def test_negative_inputs_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            allowed_ftc_2025(
                limitation_usd=Decimal("-1.00"),
                current_year_foreign_tax_usd=Decimal("0.00"),
                carryover_usd=Decimal("0.00"),
            )


if __name__ == "__main__":
    unittest.main()
