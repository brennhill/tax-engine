"""DBA-USA Art. 17 cite-only test, anchored to the IRS-hosted treaty text.

Authority: DBA-USA Art. 17(1)/(2)/(3) (https://www.irs.gov/pub/irs-trty/germany.pdf).
"""
from __future__ import annotations

import unittest

from law.treaty.dba_usa.art17 import DBA_USA_ART_17_URL


class Art17StatuteTest(unittest.TestCase):
    def test_treaty_url_is_irs_hosted_germany_pdf(self) -> None:
        self.assertEqual(
            DBA_USA_ART_17_URL,
            "https://www.irs.gov/pub/irs-trty/germany.pdf",
        )


if __name__ == "__main__":
    unittest.main()
