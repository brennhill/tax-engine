"""§ 51a EStG numeric tests, anchored to gesetze-im-internet.de.

Authority: § 51a EStG (https://www.gesetze-im-internet.de/estg/__51a.html).
The shadow only carries the "no membership" sentinel set; the actual
Kirchensteuer math is not modeled.
"""
from __future__ import annotations

import unittest

from law.germany.year_2025.estg.p51a import KIRCHENSTEUER_NONE_VALUES
from tax_pipeline.y2025.germany_inputs import (
    KIRCHENSTEUER_NONE_VALUES as PROD_NONE,
)


class P51aEstgIdentityTest(unittest.TestCase):
    def test_none_values_match_production(self) -> None:
        self.assertEqual(KIRCHENSTEUER_NONE_VALUES, PROD_NONE)


class P51aEstgStatuteTest(unittest.TestCase):
    def test_none_values_includes_canonical_strings(self) -> None:
        # The intake loader uses these to recognize "not a Kirchensteuer
        # member" so it can fail closed when any other value is asserted.
        self.assertIn("none", KIRCHENSTEUER_NONE_VALUES)
        self.assertIn("no", KIRCHENSTEUER_NONE_VALUES)
        self.assertIn("keine", KIRCHENSTEUER_NONE_VALUES)
        self.assertIn("nicht_mitglied", KIRCHENSTEUER_NONE_VALUES)


if __name__ == "__main__":
    unittest.main()
