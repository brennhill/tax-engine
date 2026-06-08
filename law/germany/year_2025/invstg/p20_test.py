"""§ 20 InvStG 2018 numeric tests, anchored to gesetze-im-internet.de.

Authority: § 20 InvStG 2018 (https://www.gesetze-im-internet.de/invstg_2018/__20.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.invstg.p20 import (
    FUND_TEILFREISTELLUNG_RATES_2025,
    fund_type_for_symbol_2025,
    normalized_fund_type_2025,
)
from tax_pipeline.y2025.germany_law import (
    FUND_TEILFREISTELLUNG_RATES_2025 as PROD_TABLE,
    fund_type_for_symbol_2025 as prod_fund_type_for_symbol,
    normalized_fund_type_2025 as prod_normalized,
)


class P20InvStGIdentityTest(unittest.TestCase):
    def test_table_matches_production(self) -> None:
        self.assertEqual(FUND_TEILFREISTELLUNG_RATES_2025, PROD_TABLE)

    def test_normalized_aktienfonds_matches_production(self) -> None:
        s = normalized_fund_type_2025("Aktienfonds", symbol="DE000ABC")
        p = prod_normalized("Aktienfonds", symbol="DE000ABC")
        self.assertEqual(s, p)
        self.assertEqual(s, "aktienfonds")

    def test_normalized_english_alias_matches_production(self) -> None:
        s = normalized_fund_type_2025("equity", symbol="VWRL")
        p = prod_normalized("equity", symbol="VWRL")
        self.assertEqual(s, p)

    def test_fund_type_for_symbol_matches_production(self) -> None:
        classification = {"VWRL": "equity", "REIT": "property"}
        self.assertEqual(
            fund_type_for_symbol_2025("vwrl", classification),
            prod_fund_type_for_symbol("vwrl", classification),
        )
        self.assertEqual(
            fund_type_for_symbol_2025("reit", classification),
            prod_fund_type_for_symbol("reit", classification),
        )

    def test_unknown_classification_fails_closed_matches_production(self) -> None:
        with self.assertRaises(ValueError):
            normalized_fund_type_2025("crypto", symbol="BTC")
        with self.assertRaises(ValueError):
            prod_normalized("crypto", symbol="BTC")

    def test_missing_symbol_fails_closed_matches_production(self) -> None:
        with self.assertRaises(ValueError):
            fund_type_for_symbol_2025("MISSING", {"VWRL": "equity"})
        with self.assertRaises(ValueError):
            prod_fund_type_for_symbol("MISSING", {"VWRL": "equity"})


class P20InvStGStatuteTest(unittest.TestCase):
    def test_aktienfonds_rate_is_30_percent(self) -> None:
        # § 20 Abs. 1 Nr. 1 InvStG.
        self.assertEqual(FUND_TEILFREISTELLUNG_RATES_2025["aktienfonds"], Decimal("0.30"))

    def test_mischfonds_rate_is_15_percent(self) -> None:
        # § 20 Abs. 1 Nr. 2 InvStG.
        self.assertEqual(FUND_TEILFREISTELLUNG_RATES_2025["mischfonds"], Decimal("0.15"))

    def test_immobilienfonds_inland_rate_is_60_percent(self) -> None:
        # § 20 Abs. 3 Nr. 1 InvStG.
        self.assertEqual(FUND_TEILFREISTELLUNG_RATES_2025["immobilienfonds"], Decimal("0.60"))

    def test_immobilienfonds_foreign_rate_is_80_percent(self) -> None:
        # § 20 Abs. 3 Nr. 2 InvStG.
        self.assertEqual(
            FUND_TEILFREISTELLUNG_RATES_2025["auslands_immobilienfonds"],
            Decimal("0.80"),
        )

    def test_sonstige_rate_is_zero(self) -> None:
        # Auffangkategorie: § 20 InvStG sonstige Investmentfonds.
        self.assertEqual(FUND_TEILFREISTELLUNG_RATES_2025["sonstige"], Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
