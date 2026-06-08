"""DBA-USA Art. 10 numeric tests, anchored to the IRS-hosted treaty text.

Authority:
- DBA-USA Art. 10(2)(b) (https://www.irs.gov/pub/irs-trty/germany.pdf)
- DBA-USA Technical Explanation (https://www.irs.gov/pub/irs-trty/germtech.pdf)

Scope note (W1.A / T1.1, 2026-05-11): the Art. 10(2)(a) direct-
investment 5 % rate and the Art. 10(3)(b) pension-fund 0 % rate were
removed from the shadow tree because the 2025 engine does not emit
those position classes and the constants had no working-tree consumer.
Once those pathways are wired, re-add the assertions here.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.treaty.dba_usa.art10 import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
    DBA_USA_ART_10_URL,
    DBA_USA_TECH_EXPLANATION_URL,
    GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE,
)
from tax_pipeline.y2025.germany_law import (
    GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE as PROD_GERMANY_PORTFOLIO,
)
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE as PROD_RATE,
    DBA_USA_ART_10_URL as PROD_URL,
    DBA_USA_TECH_EXPLANATION_URL as PROD_TECH_URL,
)


class Art10IdentityTest(unittest.TestCase):
    def test_portfolio_dividend_rate_matches_production(self) -> None:
        self.assertEqual(DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, PROD_RATE)

    def test_germany_alias_matches_production(self) -> None:
        # ``GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE`` is re-exported from
        # the Germany law module via the same Decimal object.
        self.assertEqual(GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE, PROD_GERMANY_PORTFOLIO)
        self.assertEqual(
            GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE,
            DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
        )

    def test_treaty_url_matches_production(self) -> None:
        self.assertEqual(DBA_USA_ART_10_URL, PROD_URL)

    def test_tech_explanation_url_matches_production(self) -> None:
        self.assertEqual(DBA_USA_TECH_EXPLANATION_URL, PROD_TECH_URL)


class Art10StatuteTest(unittest.TestCase):
    def test_portfolio_dividend_rate_is_15_percent(self) -> None:
        # Art. 10(2)(b) DBA-USA.
        self.assertEqual(DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, Decimal("0.15"))

    def test_treaty_url_is_irs_hosted_germany_pdf(self) -> None:
        self.assertEqual(
            DBA_USA_ART_10_URL,
            "https://www.irs.gov/pub/irs-trty/germany.pdf",
        )


if __name__ == "__main__":
    unittest.main()
