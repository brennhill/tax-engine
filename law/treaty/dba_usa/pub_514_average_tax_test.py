"""IRS Pub. 514 average-tax-rate worksheet tests.

Authority:
- DBA-USA Art. 10(2)(b), Art. 23(5)(b) (https://www.irs.gov/pub/irs-trty/germany.pdf)
- IRS Publication 514 (https://www.irs.gov/publications/p514)
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.treaty.dba_usa.pub_514_average_tax import (
    treaty25_16_average_tax_floor,
    treaty25_17_german_residual_cap,
)
from tax_pipeline.y2025.treaty_rules import (
    treaty25_16_average_tax_floor as prod_line_16,
    treaty25_17_german_residual_cap as prod_line_17,
)
from tax_pipeline.y2025.us_law import USTreatyInputs2025

D = Decimal


def _treaty_inputs_resourcing_on() -> USTreatyInputs2025:
    # Use zero-dollar dividend posture so
    # ``validate_germany_treaty_dividend_coverage_2025`` early-returns; the
    # purpose of the identity test is the math symmetry between the two
    # implementations of the rule body, not the cross-jurisdictional
    # coverage validator that lives in us_2025_law.
    return USTreatyInputs2025(
        use_treaty_resourcing=True,
        us_source_direct_equity_dividends_usd=D("0"),
        us_source_equity_fund_dividends_usd=D("0"),
        us_source_non_equity_fund_dividends_usd=D("0"),
        lob_qualification_category="qualified_resident",
    )


def _treaty_inputs_resourcing_off() -> USTreatyInputs2025:
    return USTreatyInputs2025(
        use_treaty_resourcing=False,
        us_source_direct_equity_dividends_usd=D("0"),
        us_source_equity_fund_dividends_usd=D("0"),
        us_source_non_equity_fund_dividends_usd=D("0"),
        lob_qualification_category="not_qualified",
    )


class Pub514Line16IdentityTest(unittest.TestCase):
    def test_resourcing_off_yields_zeros_matching_production(self) -> None:
        facts = {"us.treaty.inputs": _treaty_inputs_resourcing_off()}
        s = treaty25_16_average_tax_floor(dict(facts))
        p = prod_line_16(dict(facts))
        self.assertEqual(dict(s), dict(p))

    def test_zero_us_source_dividends_with_resourcing_on_matches_production(self) -> None:
        treaty_inputs = _treaty_inputs_resourcing_on()
        facts = {
            "us.treaty.inputs": treaty_inputs,
            "treaty.us_source_dividends": D("0.00"),
            "us.stage.regular_tax_before_credits": D("20000.00"),
            "us.stage.taxable_income": D("100000.00"),
            "us.constants.treaty_dividend_rate": D("0.15"),
        }
        s = treaty25_16_average_tax_floor(dict(facts))
        p = prod_line_16(dict(facts))
        self.assertEqual(dict(s), dict(p))

    def test_zero_taxable_income_fails_closed_matching_production(self) -> None:
        treaty_inputs = _treaty_inputs_resourcing_on()
        facts = {
            "us.treaty.inputs": treaty_inputs,
            "treaty.us_source_dividends": D("0.00"),
            "us.stage.regular_tax_before_credits": D("10.00"),
            "us.stage.taxable_income": D("0.00"),
            "us.constants.treaty_dividend_rate": D("0.15"),
        }
        with self.assertRaises(ValueError):
            treaty25_16_average_tax_floor(dict(facts))
        with self.assertRaises(ValueError):
            prod_line_16(dict(facts))


class Pub514Line17IdentityTest(unittest.TestCase):
    def test_resourcing_off_yields_zeros_matching_production(self) -> None:
        facts = {"us.treaty.inputs": _treaty_inputs_resourcing_off()}
        s = treaty25_17_german_residual_cap(dict(facts))
        p = prod_line_17(dict(facts))
        self.assertEqual(dict(s), dict(p))

    def test_residence_credit_below_floor_matches_production(self) -> None:
        treaty_inputs = _treaty_inputs_resourcing_on()
        facts = {
            "us.treaty.inputs": treaty_inputs,
            "treaty.us_tax_on_us_source_dividends": D("200.00"),
            "treaty.treaty_minimum_us_tax_at_source": D("150.00"),
            "de.treaty.us_source_dividend_tax_and_credit": {
                "german_precredit_tax_on_us_source_dividends_usd": D("180.00"),
                "german_residence_credit_for_us_tax_usd": D("50.00"),
            },
        }
        s = treaty25_17_german_residual_cap(dict(facts))
        p = prod_line_17(dict(facts))
        self.assertEqual(dict(s), dict(p))

    def test_residence_credit_exceeds_floor_matches_production(self) -> None:
        # Worksheet line 19 < line 18 when residence credit > 15 % floor.
        treaty_inputs = _treaty_inputs_resourcing_on()
        facts = {
            "us.treaty.inputs": treaty_inputs,
            "treaty.us_tax_on_us_source_dividends": D("250.00"),
            "treaty.treaty_minimum_us_tax_at_source": D("150.00"),
            "de.treaty.us_source_dividend_tax_and_credit": {
                "german_precredit_tax_on_us_source_dividends_usd": D("220.00"),
                "german_residence_credit_for_us_tax_usd": D("200.00"),
            },
        }
        s = treaty25_17_german_residual_cap(dict(facts))
        p = prod_line_17(dict(facts))
        self.assertEqual(dict(s), dict(p))


if __name__ == "__main__":
    unittest.main()
