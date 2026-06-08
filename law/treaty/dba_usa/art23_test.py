"""DBA-USA Art. 23 cite-only test, anchored to the IRS-hosted treaty text.

Authority: DBA-USA Art. 23(2)/(3)/(5)(b) (https://www.irs.gov/pub/irs-trty/germany.pdf).
"""
from __future__ import annotations

import unittest

from law.treaty.dba_usa.art23 import DBA_USA_ART_23_URL
from tax_pipeline.y2025.treaty_law import DBA_USA_ART_23_URL as PROD_URL


class Art23IdentityTest(unittest.TestCase):
    def test_treaty_url_matches_production(self) -> None:
        self.assertEqual(DBA_USA_ART_23_URL, PROD_URL)


class Art23StatuteTest(unittest.TestCase):
    def test_treaty_url_is_irs_hosted_germany_pdf(self) -> None:
        self.assertEqual(
            DBA_USA_ART_23_URL,
            "https://www.irs.gov/pub/irs-trty/germany.pdf",
        )


if __name__ == "__main__":
    unittest.main()
