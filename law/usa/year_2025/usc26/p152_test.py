"""§ 152 citation surface tests.

Authority:
- 26 U.S.C. § 152 (https://www.law.cornell.edu/uscode/text/26/152)
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p152 import USC_152_URL
from tax_pipeline.y2025.us_law import USC_152_URL as ORIG_URL


class P152IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_152_URL, ORIG_URL)

    def test_url_points_to_section_152(self) -> None:
        self.assertIn("/26/152", USC_152_URL)


if __name__ == "__main__":
    unittest.main()
