"""§ 164 citation surface tests.

Authority:
- 26 U.S.C. § 164 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164)
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p164 import USC_164_URL
from tax_pipeline.y2025.us_law import USC_164_URL as ORIG_URL


class P164IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_164_URL, ORIG_URL)

    def test_url_points_to_section_164(self) -> None:
        self.assertIn("section164", USC_164_URL)


if __name__ == "__main__":
    unittest.main()
