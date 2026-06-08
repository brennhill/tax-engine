"""§ 31 EStG citation tests, anchored to gesetze-im-internet.de.

Authority: § 31 EStG (https://www.gesetze-im-internet.de/estg/__31.html).
This file is cite-only — the Günstigerprüfung composition still lives in
tax_pipeline/y2025/germany_children_rules.py per MIGRATION.md Phase 4.
"""
from __future__ import annotations

import unittest

from law.germany.year_2025.estg.p31 import (
    ESTG_31_CITATION,
    ESTG_31_SATZ_4_CITATION,
    ESTG_31_URL,
)
from tax_pipeline.y2025.germany_law import ESTG_31_URL as PROD_URL


class P31EstgIdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(ESTG_31_URL, PROD_URL)


class P31EstgStatuteTest(unittest.TestCase):
    def test_url_is_canonical_gesetze_im_internet(self) -> None:
        self.assertEqual(ESTG_31_URL, "https://www.gesetze-im-internet.de/estg/__31.html")

    def test_citation_strings_present(self) -> None:
        self.assertIn("§ 31 EStG", ESTG_31_CITATION)
        self.assertIn("Satz 4", ESTG_31_SATZ_4_CITATION)


if __name__ == "__main__":
    unittest.main()
