"""§ 56 AMTI adjustments citation tests.

Authority:
- 26 U.S.C. § 56 (https://www.law.cornell.edu/uscode/text/26/56)
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p56 import USC_56_URL
from tax_pipeline.y2025.us_law import USC_56_URL as ORIG_URL


class P56IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_56_URL, ORIG_URL)


if __name__ == "__main__":
    unittest.main()
