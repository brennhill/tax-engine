"""§ 9a EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 9a EStG (https://www.gesetze-im-internet.de/estg/__9a.html).
Identity tests assert the shadow constant equals the production module.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.germany.year_2025.estg.p9a import WORKER_ALLOWANCE_PER_PERSON_EUR
from tax_pipeline.y2025.germany_law import (
    WORKER_ALLOWANCE_PER_PERSON_EUR as PROD_WORKER_ALLOWANCE,
)


class P9aEstgIdentityTest(unittest.TestCase):
    def test_worker_allowance_matches_production(self) -> None:
        self.assertEqual(WORKER_ALLOWANCE_PER_PERSON_EUR, PROD_WORKER_ALLOWANCE)


class P9aEstgStatuteTest(unittest.TestCase):
    def test_worker_allowance_is_1230_eur(self) -> None:
        # § 9a Satz 1 Nr. 1 lit. a EStG (Inflationsausgleichsgesetz 2022).
        self.assertEqual(WORKER_ALLOWANCE_PER_PERSON_EUR, Decimal("1230.00"))


if __name__ == "__main__":
    unittest.main()
