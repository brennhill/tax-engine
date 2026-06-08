"""§ 1212 carryover citation tests.

Authority:
- 26 U.S.C. § 1212 (https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212)
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p1212 import USC_1212_URL
from tax_pipeline.y2025.us_law import USC_1212_URL as ORIG_URL


class P1212IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_1212_URL, ORIG_URL)


if __name__ == "__main__":
    unittest.main()
