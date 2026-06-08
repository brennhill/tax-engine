"""DBA-USA Art. 11 citation tests.

Authority: DBA-USA Art. 11(1) (https://www.irs.gov/pub/irs-trty/germany.pdf).

Scope note (W1.A / T1.1, 2026-05-11): the Art. 11(1) 0 % source-state
interest-rate constant (``DBA_USA_ART_11_INTEREST_RATE``) was removed
from the shadow tree because the 2025 engine does not emit treaty-
eligible interest positions and the constant had no working-tree
consumer. Once a treaty-interest pathway is wired, re-add the
numeric-rate assertion here alongside the existing URL anchor.
"""
from __future__ import annotations

import unittest

from law.treaty.dba_usa.art11 import (
    DBA_USA_ART_11_URL,
)


class Art11StatuteTest(unittest.TestCase):
    def test_treaty_url_is_irs_hosted_germany_pdf(self) -> None:
        self.assertEqual(
            DBA_USA_ART_11_URL,
            "https://www.irs.gov/pub/irs-trty/germany.pdf",
        )


if __name__ == "__main__":
    unittest.main()
