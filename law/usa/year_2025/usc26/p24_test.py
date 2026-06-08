"""§ 24 CTC + ODC + ACTC numeric tests, anchored to Cornell uscode.

Authority:
- 26 U.S.C. § 24 (https://www.law.cornell.edu/uscode/text/26/24)
- 26 U.S.C. § 152 (https://www.law.cornell.edu/uscode/text/26/152)
- IRS Schedule 8812 (2025) instructions
- Rev. Proc. 2024-40 § 3.05

Asserts the same numeric outcomes as the production rule via the
shadow copy in law/usa/year_2025/usc26/p24.py.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.usc26.p24 import (
    CTC_PER_CHILD_2025_USD,
    CTC_PHASEOUT_RATE,
    CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD,
    CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD,
    CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD,
    CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD,
    CTC_REFUNDABLE_PHASE_IN_RATE,
    ODC_PER_DEPENDENT_2025_USD,
    USC_24_URL,
    _ctc_phaseout_threshold_2025,
    ctc_and_odc_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    CTC_PER_CHILD_2025_USD as ORIG_CTC,
    CTC_PHASEOUT_RATE as ORIG_PHASEOUT,
    CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD as ORIG_MFJ_THR,
    CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD as ORIG_SINGLE_THR,
    CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD as ORIG_REF_CAP,
    CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD as ORIG_FLOOR,
    CTC_REFUNDABLE_PHASE_IN_RATE as ORIG_PHASE_IN,
    ODC_PER_DEPENDENT_2025_USD as ORIG_ODC,
    USC_24_URL as ORIG_URL,
    ctc_and_odc_assessment_2025 as orig_assess,
)


class P24CTCIdentityTest(unittest.TestCase):
    """Shadow copy must equal the production module byte-for-byte."""

    def test_url_matches_production(self) -> None:
        self.assertEqual(USC_24_URL, ORIG_URL)

    def test_constants_match_production(self) -> None:
        self.assertEqual(CTC_PER_CHILD_2025_USD, ORIG_CTC)
        self.assertEqual(ODC_PER_DEPENDENT_2025_USD, ORIG_ODC)
        self.assertEqual(
            CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD, ORIG_SINGLE_THR
        )
        self.assertEqual(CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD, ORIG_MFJ_THR)
        self.assertEqual(CTC_PHASEOUT_RATE, ORIG_PHASEOUT)
        self.assertEqual(CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD, ORIG_FLOOR)
        self.assertEqual(CTC_REFUNDABLE_PHASE_IN_RATE, ORIG_PHASE_IN)
        self.assertEqual(CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD, ORIG_REF_CAP)

    def test_assess_matches_orig_2_children_below_threshold(self) -> None:
        kwargs = dict(
            children_count_qualifying_for_ctc=2,
            children_count_qualifying_for_odc=0,
            earned_income_usd=Decimal("150000"),
            modified_agi_usd=Decimal("150000"),
            regular_tax_after_ftc_usd=Decimal("20000"),
            filing_status_label="Single",
        )
        self.assertEqual(
            ctc_and_odc_assessment_2025(**kwargs),
            orig_assess(**kwargs),
        )

    def test_assess_matches_orig_phased_out_mfj(self) -> None:
        kwargs = dict(
            children_count_qualifying_for_ctc=2,
            children_count_qualifying_for_odc=1,
            earned_income_usd=Decimal("420000"),
            modified_agi_usd=Decimal("420000"),
            regular_tax_after_ftc_usd=Decimal("100000"),
            filing_status_label="Married filing jointly",
        )
        self.assertEqual(
            ctc_and_odc_assessment_2025(**kwargs),
            orig_assess(**kwargs),
        )

    def test_assess_matches_orig_low_earned_income(self) -> None:
        # Earned income just above the $2,500 floor — refundable
        # phase-in caps at 15 % × ($3,000 − $2,500) = $75.
        kwargs = dict(
            children_count_qualifying_for_ctc=1,
            children_count_qualifying_for_odc=0,
            earned_income_usd=Decimal("3000"),
            modified_agi_usd=Decimal("3000"),
            regular_tax_after_ftc_usd=Decimal("0"),
            filing_status_label="Single",
        )
        result = ctc_and_odc_assessment_2025(**kwargs)
        self.assertEqual(result, orig_assess(**kwargs))
        self.assertEqual(result.refundable_actc_usd, Decimal("75.00"))

    def test_assess_matches_orig_zero_children(self) -> None:
        kwargs = dict(
            children_count_qualifying_for_ctc=0,
            children_count_qualifying_for_odc=0,
            earned_income_usd=Decimal("100000"),
            modified_agi_usd=Decimal("100000"),
            regular_tax_after_ftc_usd=Decimal("15000"),
            filing_status_label="Single",
        )
        result = ctc_and_odc_assessment_2025(**kwargs)
        self.assertEqual(result, orig_assess(**kwargs))
        self.assertEqual(result.total_credit_usd, Decimal("0.00"))


class P24CTCStatuteTest(unittest.TestCase):
    """Numeric assertions against 26 U.S.C. § 24."""

    def test_ctc_per_child_2200_usd(self) -> None:
        # § 24(a) (as substituted by § 24(h)(2) post-OBBBA for 2025) —
        # $2,200 per qualifying child. IRS Schedule 8812 (2025)
        # instructions and IRS CTC landing page confirm.
        self.assertEqual(CTC_PER_CHILD_2025_USD, Decimal("2200"))

    def test_odc_per_dependent_500_usd(self) -> None:
        # § 24(h)(4) — $500 per ODC dependent.
        self.assertEqual(ODC_PER_DEPENDENT_2025_USD, Decimal("500"))

    def test_phaseout_threshold_mfj_400k(self) -> None:
        # § 24(b)(2)(B) — $400,000 MFJ.
        self.assertEqual(
            CTC_PHASEOUT_THRESHOLD_MFJ_2025_USD, Decimal("400000")
        )

    def test_phaseout_threshold_single_200k(self) -> None:
        # § 24(b)(2)(A) — $200,000 single/HoH/MFS.
        self.assertEqual(
            CTC_PHASEOUT_THRESHOLD_SINGLE_2025_USD, Decimal("200000")
        )

    def test_phaseout_rate_5_percent(self) -> None:
        # § 24(b)(2) — $50 per $1,000 = 5 percentage points per $1,000.
        self.assertEqual(CTC_PHASEOUT_RATE, Decimal("0.05"))

    def test_refundable_floor_2500_usd(self) -> None:
        # § 24(d)(1)(B) — $2,500 earned-income floor.
        self.assertEqual(
            CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD, Decimal("2500")
        )

    def test_refundable_phase_in_rate_15_percent(self) -> None:
        # § 24(d)(1)(B) — 15 % phase-in rate.
        self.assertEqual(CTC_REFUNDABLE_PHASE_IN_RATE, Decimal("0.15"))

    def test_refundable_cap_1700_usd(self) -> None:
        # § 24(d)(1)(A) — $1,700 refundable cap (Rev. Proc. 2024-40 § 3.05).
        self.assertEqual(
            CTC_REFUNDABLE_CAP_PER_CHILD_2025_USD, Decimal("1700")
        )

    def test_phaseout_threshold_picker_mfj(self) -> None:
        self.assertEqual(
            _ctc_phaseout_threshold_2025(filing_status_label="Married filing jointly"),
            Decimal("400000"),
        )

    def test_phaseout_threshold_picker_other(self) -> None:
        for label in ("Single", "Married filing separately"):
            self.assertEqual(
                _ctc_phaseout_threshold_2025(filing_status_label=label),
                Decimal("200000"),
            )

    def test_negative_count_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            ctc_and_odc_assessment_2025(
                children_count_qualifying_for_ctc=-1,
                children_count_qualifying_for_odc=0,
                earned_income_usd=Decimal("100000"),
                modified_agi_usd=Decimal("100000"),
                regular_tax_after_ftc_usd=Decimal("10000"),
                filing_status_label="Single",
            )


if __name__ == "__main__":
    unittest.main()
