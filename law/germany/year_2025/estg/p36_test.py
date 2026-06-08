"""§ 36 EStG citation tests, anchored to gesetze-im-internet.de.

Authority: § 36 EStG (https://www.gesetze-im-internet.de/estg/__36.html).
This file is cite-only — the refund-balance composition still lives in
tax_pipeline/y2025/germany_final_rules.py per MIGRATION.md Phase 4.
"""
from __future__ import annotations

import unittest

from law.germany.year_2025.estg.p36 import (
    ESTG_36_ABS_2_CITATION,
    ESTG_36_URL,
)
from tax_pipeline.y2025.germany_law import ESTG_36_URL as PROD_URL


class P36EstgIdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(ESTG_36_URL, PROD_URL)


class P36EstgStatuteTest(unittest.TestCase):
    def test_url_is_canonical_gesetze_im_internet(self) -> None:
        self.assertEqual(ESTG_36_URL, "https://www.gesetze-im-internet.de/estg/__36.html")

    def test_citation_string_includes_abs_2(self) -> None:
        self.assertIn("Abs. 2", ESTG_36_ABS_2_CITATION)


if __name__ == "__main__":
    unittest.main()
