"""§ 26a EStG citation tests, anchored to gesetze-im-internet.de."""
from __future__ import annotations

import unittest

from law.germany.year_2025.estg.p26a import ESTG_26A_URL


class P26aEstgStatuteTest(unittest.TestCase):
    def test_url_is_canonical(self) -> None:
        self.assertEqual(ESTG_26A_URL, "https://www.gesetze-im-internet.de/estg/__26a.html")


if __name__ == "__main__":
    unittest.main()
