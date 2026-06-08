from __future__ import annotations

import unittest
from decimal import Decimal


# Note: a broader "no Decimal('0.15') literal in the engine" check used to
# live here. That coverage is now provided by invariant I1
# (``tests/test_no_legal_constant_literal_bypass.py``), which scans every
# law module for any literal whose numeric value matches a named law
# constant. The four identity checks below remain because they catch a
# different bug class — the canonical constant exists but a downstream
# module re-declares its own copy and stops being ``is`` to it.
class TreatyLawCanonicalConstantTest(unittest.TestCase):
    """Pin DBA-USA Art. 10(2)(b) 15% portfolio-dividend rate to a single
    canonical module so that all jurisdictional code dereferences the same
    Decimal value.

    Authority:
    - DBA-USA Art. 10(2)(b)
      https://www.irs.gov/pub/irs-trty/germany.pdf
    - DBA-USA Technical Explanation
      https://www.irs.gov/pub/irs-trty/germtech.pdf
    """

    def test_canonical_module_exposes_rate(self) -> None:
        from tax_pipeline.y2025.treaty_law import (
            DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
        )
        self.assertEqual(
            DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, Decimal("0.15")
        )

    def test_germany_law_imports_from_canonical_module(self) -> None:
        from tax_pipeline.y2025 import germany_law as germany_2025_law, treaty_law as treaty_2025_law

        self.assertIs(
            germany_2025_law.GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE,
            treaty_2025_law.DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
        )

    def test_us_law_imports_from_canonical_module(self) -> None:
        from tax_pipeline.y2025 import us_law as us_2025_law, treaty_law as treaty_2025_law

        self.assertIs(
            us_2025_law.TREATY_DIVIDEND_RATE,
            treaty_2025_law.DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
        )

    def test_derive_module_imports_from_canonical_module(self) -> None:
        from tax_pipeline.y2025 import (
            derive_treaty_dividend_items as derive_treaty_dividend_items_2025,
            treaty_law as treaty_2025_law,
        )

        self.assertIs(
            derive_treaty_dividend_items_2025.TREATY_RATE,
            treaty_2025_law.DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
        )

if __name__ == "__main__":
    unittest.main()
