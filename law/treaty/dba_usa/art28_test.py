"""DBA-USA Art. 28 numeric tests, anchored to the IRS-hosted treaty text.

Authority: DBA-USA Art. 28 (https://www.irs.gov/pub/irs-trty/germany.pdf).
"""
from __future__ import annotations

import unittest

from law.treaty.dba_usa.art28 import (
    DBA_USA_ART_28_URL,
    LOB_QUALIFICATION_CATEGORIES,
)
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_28_URL as PROD_URL,
    LOB_QUALIFICATION_CATEGORIES as PROD_CATEGORIES,
)


class Art28IdentityTest(unittest.TestCase):
    def test_treaty_url_matches_production(self) -> None:
        self.assertEqual(DBA_USA_ART_28_URL, PROD_URL)

    def test_lob_categories_match_production(self) -> None:
        self.assertEqual(LOB_QUALIFICATION_CATEGORIES, PROD_CATEGORIES)


class Art28StatuteTest(unittest.TestCase):
    def test_lob_categories_is_closed_six_member_enum(self) -> None:
        # Five qualifying categories + one "not_qualified" sentinel.
        self.assertEqual(len(LOB_QUALIFICATION_CATEGORIES), 6)
        self.assertIn("publicly_traded", LOB_QUALIFICATION_CATEGORIES)
        self.assertIn("qualified_resident", LOB_QUALIFICATION_CATEGORIES)
        self.assertIn("active_business", LOB_QUALIFICATION_CATEGORIES)
        self.assertIn("derivative_benefits", LOB_QUALIFICATION_CATEGORIES)
        self.assertIn("competent_authority", LOB_QUALIFICATION_CATEGORIES)
        self.assertIn("not_qualified", LOB_QUALIFICATION_CATEGORIES)


if __name__ == "__main__":
    unittest.main()
