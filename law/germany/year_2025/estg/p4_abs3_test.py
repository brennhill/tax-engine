"""§ 4 Abs. 3 EStG Einnahmenüberschussrechnung — shadow tests.

Authority:
- § 4 Abs. 3 EStG — https://www.gesetze-im-internet.de/estg/__4.html
- § 18 EStG — https://www.gesetze-im-internet.de/estg/__18.html

The shadow mirrors ``tax_pipeline.y2025.germany_law`` byte-for-byte;
these tests assert concrete numeric EÜR outcomes.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p4_abs3 import euer_net_profit_2025
from tax_pipeline.y2025.germany_law import (
    GermanyEuerInputs2025,
    euer_net_profit_2025 as production_euer_net_profit_2025,
)

D = Decimal


class P4Abs3EuerTest(unittest.TestCase):
    def test_shadow_matches_production(self) -> None:
        inputs = GermanyEuerInputs2025(
            operating_receipts_eur=D("80000.00"),
            operating_expenses_eur=D("18250.00"),
        )
        self.assertEqual(
            euer_net_profit_2025(inputs=inputs),
            production_euer_net_profit_2025(inputs=inputs),
        )

    def test_net_profit_is_receipts_minus_expenses(self) -> None:
        # § 4 Abs. 3 Satz 1: Gewinn = Überschuss der Betriebseinnahmen über
        # die Betriebsausgaben. 80,000 − 18,250 = 61,750.
        result = euer_net_profit_2025(
            inputs=GermanyEuerInputs2025(
                operating_receipts_eur=D("80000.00"),
                operating_expenses_eur=D("18250.00"),
            )
        )
        self.assertEqual(result.operating_receipts_eur, D("80000.00"))
        self.assertEqual(result.operating_expenses_eur, D("18250.00"))
        self.assertEqual(result.net_profit_eur, D("61750.00"))
        self.assertIn("§ 4 Abs. 3 EStG", result.legal_basis)

    def test_loss_is_not_floored_at_zero(self) -> None:
        # A § 4 Abs. 3 Verlust (expenses > receipts) is a real negative
        # result that offsets other income under § 2 Abs. 3 EStG — never
        # floored.
        result = euer_net_profit_2025(
            inputs=GermanyEuerInputs2025(
                operating_receipts_eur=D("10000.00"),
                operating_expenses_eur=D("14500.00"),
            )
        )
        self.assertEqual(result.net_profit_eur, D("-4500.00"))

    def test_zero_activity_yields_zero_profit(self) -> None:
        result = euer_net_profit_2025(
            inputs=GermanyEuerInputs2025(
                operating_receipts_eur=D("0.00"),
                operating_expenses_eur=D("0.00"),
            )
        )
        self.assertEqual(result.net_profit_eur, D("0.00"))

    def test_negative_receipts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "operating_receipts_eur"):
            euer_net_profit_2025(
                inputs=GermanyEuerInputs2025(
                    operating_receipts_eur=D("-1.00"),
                    operating_expenses_eur=D("0.00"),
                )
            )

    def test_negative_expenses_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "operating_expenses_eur"):
            euer_net_profit_2025(
                inputs=GermanyEuerInputs2025(
                    operating_receipts_eur=D("0.00"),
                    operating_expenses_eur=D("-1.00"),
                )
            )


if __name__ == "__main__":
    unittest.main()
