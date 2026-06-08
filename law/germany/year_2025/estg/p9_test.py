"""§ 9 EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 9 EStG (https://www.gesetze-im-internet.de/estg/__9.html).
Tagespauschale rate + cap come from § 4 Abs. 5 Satz 1 Nr. 6c EStG and apply
by § 9 Abs. 5 EStG cross-reference. Tests assert identity with the
production module ``tax_pipeline.y2025.germany_law`` so the shadow copy
stays byte-for-byte equivalent.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p9 import (
    HOME_OFFICE_DAILY_RATE_EUR,
    HOME_OFFICE_MAX_EUR,
    home_office_tagespauschale_2025,
)
from tax_pipeline.y2025.germany_law import (
    HOME_OFFICE_DAILY_RATE_EUR as TP_RATE,
    HOME_OFFICE_MAX_EUR as TP_MAX,
    home_office_tagespauschale_2025 as tp_fn,
)


class P9EstgIdentityTest(unittest.TestCase):
    """Shadow copy must equal the production module byte-for-byte."""

    def test_daily_rate_matches_production(self) -> None:
        self.assertEqual(HOME_OFFICE_DAILY_RATE_EUR, TP_RATE)

    def test_max_matches_production(self) -> None:
        self.assertEqual(HOME_OFFICE_MAX_EUR, TP_MAX)

    def test_function_matches_production_under_cap(self) -> None:
        # 100 days × €6 = €600 (well under €1,260 cap)
        shadow = home_office_tagespauschale_2025(100, 0)
        prod = tp_fn(100, 0)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("600.00"))

    def test_function_matches_production_at_cap(self) -> None:
        # 250 days × €6 = €1,500 → capped at €1,260
        shadow = home_office_tagespauschale_2025(250, 0)
        prod = tp_fn(250, 0)
        self.assertEqual(shadow, prod)
        self.assertEqual(shadow, Decimal("1260.00"))


class P9EstgStatuteTest(unittest.TestCase):
    """Numeric assertions against § 4 Abs. 5 Satz 1 Nr. 6c EStG."""

    def test_daily_rate_is_six_euros(self) -> None:
        # § 4 Abs. 5 Satz 1 Nr. 6c EStG (Jahressteuergesetz 2022).
        self.assertEqual(HOME_OFFICE_DAILY_RATE_EUR, Decimal("6.00"))

    def test_annual_cap_is_1260_eur(self) -> None:
        # § 4 Abs. 5 Satz 1 Nr. 6c EStG: 210 days × €6 = €1,260.
        self.assertEqual(HOME_OFFICE_MAX_EUR, Decimal("1260.00"))

    def test_zero_days_returns_zero(self) -> None:
        self.assertEqual(home_office_tagespauschale_2025(0, 0), Decimal("0.00"))

    def test_visit_days_require_no_other_workplace(self) -> None:
        with self.assertRaises(ValueError):
            home_office_tagespauschale_2025(0, 5)

    def test_visit_days_allowed_with_no_other_workplace(self) -> None:
        result = home_office_tagespauschale_2025(
            0, 5, visit_days_no_other_workplace=True
        )
        self.assertEqual(result, Decimal("30.00"))

    def test_negative_days_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            home_office_tagespauschale_2025(-1, 0)


if __name__ == "__main__":
    unittest.main()
