"""Schedule B render-precondition (Workstream 5).

Authority:
- IRS Form 1040 Instructions — https://www.irs.gov/instructions/i1040gi
- IRS Schedule B Instructions — https://www.irs.gov/forms-pubs/about-schedule-b-form-1040

Schedule B is required when interest > $1,500 OR ordinary dividends >
$1,500 OR a foreign account exists. The foreign-account trigger
(Schedule B Part III) is independent of the $1,500 dollar thresholds:
Schedule B Part III is ALWAYS required when the taxpayer has a foreign
account, regardless of the interest / dividend amounts.

Workstream 5 of the 2026-05-01 USA legal-flow review fills the
unconditional-render gap in ``tax_pipeline/forms/usa.py``. The
``schedule_b_required_2025`` and ``schedule_b_parts_required_2025``
helpers in ``tax_pipeline/y2025/us_law.py`` express the IRS predicate;
the renderer consumes them.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    SCHEDULE_B_THRESHOLD_USD,
    schedule_b_parts_required_2025,
    schedule_b_required_2025,
)

D = Decimal


class ScheduleBThresholdConstantTest(unittest.TestCase):
    """Pin the $1,500 IRS instruction threshold."""

    def test_threshold_is_1500_usd(self) -> None:
        self.assertEqual(SCHEDULE_B_THRESHOLD_USD, D("1500.00"))


class ScheduleBRequiredPredicateTest(unittest.TestCase):
    """Direct truth table for the Schedule B precondition."""

    def test_truth_table(self) -> None:
        # ``(interest, dividends, has_account, expected_required, note)``
        # covering every branch of ``schedule_b_required_2025``.
        cases = (
            (D("100"), D("100"), False, False, "below threshold, no foreign account"),
            (D("1500"), D("1500"), False, False, "exact $1,500 is NOT > $1,500"),
            (D("1500.01"), D("0"), False, True, "interest > $1,500 triggers"),
            (D("0"), D("1500.01"), False, True, "dividends > $1,500 trigger"),
            (D("0"), D("0"), True, True, "foreign account triggers regardless"),
        )
        for interest, dividends, has_account, expected, note in cases:
            with self.subTest(note=note):
                self.assertEqual(
                    schedule_b_required_2025(
                        interest_income_usd=interest,
                        ordinary_dividends_usd=dividends,
                        has_foreign_account=has_account,
                    ),
                    expected,
                )

    def test_negative_amounts_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "interest_income_usd"):
            schedule_b_required_2025(
                interest_income_usd=D("-1"),
                ordinary_dividends_usd=D("0"),
                has_foreign_account=False,
            )


class ScheduleBPartsRequiredTest(unittest.TestCase):
    """Per-Part precondition matrix.

    - Part I (Interest): required when interest > $1,500 OR a foreign
      account is present (so the foreign-account checkbox is on a Part I
      line in the IRS form).
    - Part II (Dividends): required when dividends > $1,500.
    - Part III (Foreign Accounts): required iff has_foreign_account.
    """

    def test_parts_required_truth_table(self) -> None:
        # ``(interest, dividends, has_account) -> (part_i, part_ii, part_iii)``.
        # The asymmetry — foreign-account flips Part I as well as Part III —
        # is the load-bearing case (the foreign-account checkbox lives in
        # Part I per the IRS form).
        cases = (
            (D("100"), D("100"), False, (False, False, False), "below thresholds, no account"),
            (D("2000"), D("100"), False, (True, False, False), "only interest above"),
            (D("100"), D("2000"), False, (False, True, False), "only dividends above"),
            (D("0"), D("0"), True, (True, False, True), "foreign account triggers parts I + III"),
            (D("2000"), D("2000"), True, (True, True, True), "all three parts required"),
        )
        for interest, dividends, has_account, expected, note in cases:
            with self.subTest(note=note):
                self.assertEqual(
                    schedule_b_parts_required_2025(
                        interest_income_usd=interest,
                        ordinary_dividends_usd=dividends,
                        has_foreign_account=has_account,
                    ),
                    expected,
                )


class ScheduleBDemoWorkspacePostureTest(unittest.TestCase):
    """The U.S.-citizen-in-Germany demo posture has a German bank
    account, so Schedule B Part III is always required.
    """

    def test_us_in_germany_posture_always_renders_part_iii(self) -> None:
        # Sparkasse / Comdirect / etc. account is the modeled posture.
        # Even at $0 interest and $0 dividends, Part III triggers.
        part_i, part_ii, part_iii = schedule_b_parts_required_2025(
            interest_income_usd=D("0"),
            ordinary_dividends_usd=D("0"),
            has_foreign_account=True,
        )
        self.assertTrue(part_iii)
        self.assertTrue(part_i)  # foreign-account checkbox lives in Part I


if __name__ == "__main__":
    unittest.main()
