"""§ 26 EStG citation tests, anchored to gesetze-im-internet.de."""
from __future__ import annotations

import unittest

from law.germany.year_2025.estg.p26 import ESTG_26_URL
from tax_pipeline.y2025.germany_law import ESTG_26_URL as PROD_URL


class P26EstgIdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(ESTG_26_URL, PROD_URL)


class P26EstgStatuteTest(unittest.TestCase):
    def test_url_is_canonical(self) -> None:
        self.assertEqual(ESTG_26_URL, "https://www.gesetze-im-internet.de/estg/__26.html")


if __name__ == "__main__":
    unittest.main()
