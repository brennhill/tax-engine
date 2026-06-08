"""§ 10b EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 10b EStG (https://www.gesetze-im-internet.de/estg/__10b.html).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p10b import (
    SPENDENABZUG_2025_GDE_FRACTION_CAP,
    spendenabzug_2025,
)
from tax_pipeline.y2025.germany_law import (
    SPENDENABZUG_2025_GDE_FRACTION_CAP as PROD_CAP,
    spendenabzug_2025 as prod_spendenabzug,
)


class P10bEstgIdentityTest(unittest.TestCase):
    def test_cap_constant_matches_production(self) -> None:
        self.assertEqual(SPENDENABZUG_2025_GDE_FRACTION_CAP, PROD_CAP)

    def test_function_below_cap_matches_production(self) -> None:
        # €100 donation, GdE €100,000 → cap is €20,000 → deductible = €100.
        s = spendenabzug_2025(
            donations_eur=Decimal("100.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("100000.00"),
            carryforward_eur=Decimal("0.00"),
        )
        p = prod_spendenabzug(
            donations_eur=Decimal("100.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("100000.00"),
            carryforward_eur=Decimal("0.00"),
        )
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("100.00"))

    def test_function_above_cap_matches_production(self) -> None:
        # €30,000 donation, GdE €100,000 → cap = €20,000 → deductible = €20,000.
        s = spendenabzug_2025(
            donations_eur=Decimal("30000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("100000.00"),
            carryforward_eur=Decimal("0.00"),
        )
        p = prod_spendenabzug(
            donations_eur=Decimal("30000.00"),
            gesamtbetrag_der_einkuenfte_eur=Decimal("100000.00"),
            carryforward_eur=Decimal("0.00"),
        )
        self.assertEqual(s, p)
        self.assertEqual(s, Decimal("20000.00"))


class P10bEstgStatuteTest(unittest.TestCase):
    def test_cap_is_20_percent(self) -> None:
        # § 10b Abs. 1 Satz 1 Nr. 1 EStG.
        self.assertEqual(SPENDENABZUG_2025_GDE_FRACTION_CAP, Decimal("0.20"))

    def test_carryforward_fails_closed(self) -> None:
        # § 10b Abs. 1 Sätze 9-10 EStG Großspendenrest is not modeled.
        with self.assertRaises(NotImplementedError):
            spendenabzug_2025(
                donations_eur=Decimal("100.00"),
                gesamtbetrag_der_einkuenfte_eur=Decimal("100000.00"),
                carryforward_eur=Decimal("50.00"),
            )


if __name__ == "__main__":
    unittest.main()
