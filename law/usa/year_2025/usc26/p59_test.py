"""§ 59 AMTFTC citation tests.

Authority:
- 26 U.S.C. § 59 (https://www.law.cornell.edu/uscode/text/26/59)
"""
from __future__ import annotations

import unittest

from law.usa.year_2025.usc26.p59 import USC_59_URL
from tax_pipeline.y2025.us_law import USC_59_URL as ORIG_URL


class P59IdentityTest(unittest.TestCase):
    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_59_URL, ORIG_URL)


if __name__ == "__main__":
    unittest.main()
