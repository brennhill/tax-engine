"""26 U.S.C. § 24 — Child Tax Credit + Additional Child Tax Credit + ODC.

Authority:
- 26 U.S.C. § 24 — Child Tax Credit / ACTC / ODC.
  https://www.law.cornell.edu/uscode/text/26/24
- 26 U.S.C. § 152 — qualifying-child / qualifying-relative definitions.
  https://www.law.cornell.edu/uscode/text/26/152
- IRS Schedule 8812 (Form 1040) — Credits for Qualifying Children and
  Other Dependents (2025 instructions).
  https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
- Rev. Proc. 2024-40 § 3.05 — 2025 inflation-adjusted refundable ACTC
  cap of $1,700 per qualifying child (§ 24(d)(1)(A)).
  https://www.irs.gov/pub/irs-drop/rp-24-40.pdf

These tests pin the numeric outcomes of
``ctc_and_odc_assessment_2025`` against concrete fact patterns. The
2025 numerics under the post-OBBBA regime are:

  - $2,200 per qualifying child (§ 24(a) as substituted by § 24(h)(2)
    post-OBBBA for 2025; confirmed against IRS Schedule 8812 (2025)
    instructions and the IRS Child Tax Credit landing page)
  - $500 per Other Dependent (§ 24(h)(4)), NON-refundable
  - $200,000 phase-out start for non-MFJ; $400,000 for MFJ (§ 24(b)(2))
  - $50 per $1,000 of MAGI excess; excess rounded UP to next $1,000
    under § 24(b)(3)
  - Refundable ACTC = min(remaining_ctc, $1,700 × ctc_children,
    15 % × max(0, earned_income − $2,500)) under § 24(d)(1)(B), capped
    by § 24(d)(1)(A) inflation-indexed cap (Rev. Proc. 2024-40 § 3.05)

All expectations were hand-verified against the math in
``tax_pipeline/y2025/us_law.py::ctc_and_odc_assessment_2025`` before
being written; the law-core function is the source of truth.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD,
    USChildTaxCreditAssessment2025,
    ctc_and_odc_assessment_2025,
)


def _assess(
    *,
    ctc_count: int = 0,
    odc_count: int = 0,
    earned_income: str = "0",
    magi: str = "0",
    tax_after_ftc: str = "0",
    filing_status: str = "Single",
) -> USChildTaxCreditAssessment2025:
    return ctc_and_odc_assessment_2025(
        children_count_qualifying_for_ctc=ctc_count,
        children_count_qualifying_for_odc=odc_count,
        earned_income_usd=Decimal(earned_income),
        modified_agi_usd=Decimal(magi),
        regular_tax_after_ftc_usd=Decimal(tax_after_ftc),
        filing_status_label=filing_status,
    )


class CTCAndODCAssessment2025Test(unittest.TestCase):
    """Concrete numeric fact patterns for § 24 CTC + ACTC + ODC."""

    def test_zero_children_yields_zero_credit(self) -> None:
        """§ 24(a) / § 24(h)(4): no qualifying children and no other
        dependents produce zero gross CTC, zero gross ODC, and zero
        total credit even with positive tax liability and earned income.

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=0,
            odc_count=0,
            earned_income="50000",
            magi="50000",
            tax_after_ftc="5000",
        )
        self.assertEqual(result.gross_ctc_usd, Decimal("0.00"))
        self.assertEqual(result.gross_odc_usd, Decimal("0.00"))
        self.assertEqual(result.combined_pre_phaseout_usd, Decimal("0.00"))
        self.assertEqual(result.phaseout_reduction_usd, Decimal("0.00"))
        self.assertEqual(result.combined_post_phaseout_usd, Decimal("0.00"))
        self.assertEqual(result.nonrefundable_portion_usd, Decimal("0.00"))
        self.assertEqual(result.refundable_actc_usd, Decimal("0.00"))
        self.assertEqual(result.total_credit_usd, Decimal("0.00"))
        # Schedule 8812 (2025) Lines 4 / 6 — qualifying-children counts.
        self.assertEqual(result.qualifying_ctc_count, 0)
        self.assertEqual(result.qualifying_odc_count, 0)
        # Schedule 8812 Lines 9 / 10 / 13 — phase-out threshold ($200k
        # single), Modified AGI, and the regular-tax-after-FTC ordering
        # cap echoed from the caller.
        self.assertEqual(result.phaseout_threshold_usd, Decimal("200000"))
        self.assertEqual(result.modified_agi_usd, Decimal("50000.00"))
        self.assertEqual(result.regular_tax_after_ftc_usd, Decimal("5000.00"))
        # Schedule 8812 Line 16a / 16b / 18a / 19 / 20 / 21 — refundable
        # ACTC sub-steps. With zero qualifying children every ceiling /
        # phase-in component is zero except Line 19 (statutory floor)
        # and Line 20 (max(0, 50000 − 2500) = 47500). § 24(d)(1)(B).
        self.assertEqual(result.remaining_ctc_for_refundable_usd, Decimal("0.00"))
        self.assertEqual(result.refundable_actc_cap_usd, Decimal("0.00"))
        self.assertEqual(result.earned_income_usd, Decimal("50000.00"))
        self.assertEqual(result.earned_income_floor_usd, Decimal("2500.00"))
        self.assertEqual(result.earned_income_excess_usd, Decimal("47500.00"))
        self.assertEqual(
            result.refundable_actc_earned_income_phase_in_usd, Decimal("7125.00")
        )
        self.assertEqual(result.post_phaseout_ctc_share_usd, Decimal("0.00"))

    def test_two_children_below_threshold_full_nonrefundable(self) -> None:
        """§ 24(a) + § 24(b)(2): two qualifying children at $150,000
        single MAGI is below the $200,000 phase-out start, so the full
        $4,400 CTC stands ($2,200 × 2). Regular tax after FTC of
        $20,000 fully absorbs the credit as nonrefundable, leaving zero
        refundable ACTC under § 24(d)(1).

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=2,
            earned_income="150000",
            magi="150000",
            tax_after_ftc="20000",
        )
        self.assertEqual(result.gross_ctc_usd, Decimal("4400.00"))
        self.assertEqual(result.phaseout_reduction_usd, Decimal("0.00"))
        self.assertEqual(result.combined_post_phaseout_usd, Decimal("4400.00"))
        self.assertEqual(result.nonrefundable_portion_usd, Decimal("4400.00"))
        self.assertEqual(result.refundable_actc_usd, Decimal("0.00"))

    def test_two_children_single_phaseout_at_250k(self) -> None:
        """§ 24(b)(2)/(3): single filer with $250,000 MAGI has $50,000
        of excess over the $200,000 threshold. § 24(b)(3) rounds the
        excess up to the next $1,000 (already $50,000 exactly), so the
        phase-out is $50 × 50 = $2,500. Combined post-phaseout credit
        falls from $4,400 ($2,200 × 2) to $1,900.

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=2,
            earned_income="250000",
            magi="250000",
            tax_after_ftc="50000",
        )
        self.assertEqual(result.phaseout_reduction_usd, Decimal("2500.00"))
        self.assertEqual(result.combined_post_phaseout_usd, Decimal("1900.00"))
        self.assertEqual(result.nonrefundable_portion_usd, Decimal("1900.00"))

    def test_one_child_mfj_phaseout_rounds_excess_up(self) -> None:
        """§ 24(b)(3): MFJ filer at $410,500 MAGI has $10,500 of excess
        over the $400,000 MFJ threshold. § 24(b)(3) rounds the excess
        UP to the next $1,000, so the reduction quotient is 11 (not 10
        or 10.5), giving a phase-out of $550. The single qualifying
        child's $2,200 gross CTC drops to $1,650 post-phaseout.

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=1,
            earned_income="400000",
            magi="410500",
            tax_after_ftc="80000",
            filing_status="Married Filing Jointly",
        )
        self.assertEqual(result.gross_ctc_usd, Decimal("2200.00"))
        self.assertEqual(result.phaseout_reduction_usd, Decimal("550.00"))
        self.assertEqual(result.combined_post_phaseout_usd, Decimal("1650.00"))

    def test_zero_tax_yields_refundable_actc_capped_at_1700(self) -> None:
        """§ 24(d)(1)(B): with zero regular tax to absorb the
        nonrefundable portion, the refundable ACTC ceiling is the
        minimum of the post-phaseout CTC ($2,200), the per-child cap of
        $1,700 (§ 24(d)(1)(A); Rev. Proc. 2024-40 § 3.05), and 15 %
        of (earned income − $2,500). For one child with $20,000 earned
        income that's min($2,200, $1,700, $2,625) = $1,700.

        https://www.law.cornell.edu/uscode/text/26/24
        https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
        """
        result = _assess(
            ctc_count=1,
            earned_income="20000",
            magi="20000",
            tax_after_ftc="0",
        )
        self.assertEqual(result.nonrefundable_portion_usd, Decimal("0.00"))
        self.assertEqual(result.refundable_actc_usd, Decimal("1700.00"))

    def test_odc_only_is_nonrefundable(self) -> None:
        """§ 24(h)(4): the $500 Credit for Other Dependents is
        explicitly NON-refundable. With one ODC and zero qualifying
        CTC children, the entire credit is nonrefundable and the
        refundable ACTC is zero regardless of earned income.

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=0,
            odc_count=1,
            earned_income="50000",
            magi="50000",
            tax_after_ftc="5000",
        )
        self.assertEqual(result.gross_ctc_usd, Decimal("0.00"))
        self.assertEqual(result.gross_odc_usd, Decimal("500.00"))
        self.assertEqual(result.nonrefundable_portion_usd, Decimal("500.00"))
        self.assertEqual(result.refundable_actc_usd, Decimal("0.00"))

    def test_mfs_uses_200k_threshold_not_400k(self) -> None:
        """§ 24(b)(2): the $400,000 threshold applies only to a joint
        return. Married Filing Separately uses the $200,000 threshold,
        so an MFS filer at $250,000 MAGI is in phase-out (not below
        the MFJ threshold). Same numerics as the single $250k case.

        https://www.law.cornell.edu/uscode/text/26/24
        """
        result = _assess(
            ctc_count=2,
            earned_income="250000",
            magi="250000",
            tax_after_ftc="50000",
            filing_status="Married Filing Separately",
        )
        self.assertEqual(result.phaseout_threshold_usd, Decimal("200000"))
        self.assertEqual(result.phaseout_reduction_usd, Decimal("2500.00"))
        self.assertEqual(result.combined_post_phaseout_usd, Decimal("1900.00"))


if __name__ == "__main__":
    unittest.main()
