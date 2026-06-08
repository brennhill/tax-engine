"""§ 6 BKGG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 6 Abs. 2 BKGG (https://www.gesetze-im-internet.de/bkgg_1996/__6.html)
+ § 31 Satz 4 EStG (https://www.gesetze-im-internet.de/estg/__31.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.bkgg.p6 import (
    KINDERGELD_2025_ANNUAL_EUR,
    KINDERGELD_2025_MONTHLY_EUR,
    KINDERGELD_2025_RECIPIENT_VALUES,
    KINDERGELD_2025_THIS_FILER_RECIPIENTS,
    kindergeld_for_child_2025,
)
from tax_pipeline.y2025.germany_law import (
    KINDERGELD_2025_ANNUAL_EUR as PROD_ANNUAL,
    KINDERGELD_2025_MONTHLY_EUR as PROD_MONTHLY,
    KINDERGELD_2025_RECIPIENT_VALUES as PROD_RECIPIENT_VALUES,
    KINDERGELD_2025_THIS_FILER_RECIPIENTS as PROD_THIS_FILER,
    kindergeld_for_child_2025 as prod_fn,
)


class P6BkggIdentityTest(unittest.TestCase):
    def test_monthly_amount_matches_production(self) -> None:
        self.assertEqual(KINDERGELD_2025_MONTHLY_EUR, PROD_MONTHLY)

    def test_annual_amount_matches_production(self) -> None:
        self.assertEqual(KINDERGELD_2025_ANNUAL_EUR, PROD_ANNUAL)

    def test_recipient_values_match_production(self) -> None:
        self.assertEqual(KINDERGELD_2025_RECIPIENT_VALUES, PROD_RECIPIENT_VALUES)

    def test_this_filer_recipients_match_production(self) -> None:
        self.assertEqual(KINDERGELD_2025_THIS_FILER_RECIPIENTS, PROD_THIS_FILER)

    def test_kindergeld_for_taxpayer_full_year_matches_production(self) -> None:
        s = kindergeld_for_child_2025(12, "taxpayer")
        p = prod_fn(12, "taxpayer")
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("3060.00"))

    def test_kindergeld_for_spouse_partial_year_matches_production(self) -> None:
        s = kindergeld_for_child_2025(7, "spouse")
        p = prod_fn(7, "spouse")
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("1785.00"))

    def test_kindergeld_for_other_parent_returns_zero_matches_production(self) -> None:
        s = kindergeld_for_child_2025(12, "other_parent")
        p = prod_fn(12, "other_parent")
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("0.00"))

    def test_kindergeld_for_none_recipient_returns_zero_matches_production(self) -> None:
        s = kindergeld_for_child_2025(12, "none")
        p = prod_fn(12, "none")
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("0.00"))


class P6BkggStatuteTest(unittest.TestCase):
    def test_monthly_amount_is_255_eur(self) -> None:
        # § 6 Abs. 2 BKGG: €255/month from 01.01.2025
        # (Steuerfortentwicklungsgesetz 2024, BGBl. 2024 I; previously
        # €250/month since 01.01.2023 under Inflationsausgleichsgesetz 2022).
        self.assertEqual(KINDERGELD_2025_MONTHLY_EUR, Decimal("255"))

    def test_annual_amount_is_3060_eur(self) -> None:
        self.assertEqual(KINDERGELD_2025_ANNUAL_EUR, Decimal("3060"))

    def test_unsupported_recipient_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            kindergeld_for_child_2025(12, "uncle")

    def test_negative_months_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            kindergeld_for_child_2025(-1, "taxpayer")

    def test_more_than_12_months_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            kindergeld_for_child_2025(13, "taxpayer")


if __name__ == "__main__":
    unittest.main()
