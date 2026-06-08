"""§ 61 citation surface tests, anchored to uscode.house.gov.

Authority:
- 26 U.S.C. § 61 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61)

Asserts the citation URL constant equals the production module value.
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p61 import USC_61_URL
from tax_pipeline.y2025.us_law import USC_61_URL as ORIG_URL


class P61IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_61_URL, ORIG_URL)

    def test_url_points_to_section_61(self) -> None:
        self.assertIn("section61", USC_61_URL)


if __name__ == "__main__":
    unittest.main()
