"""US25-SE-TAX + US25-ADDITIONAL-MEDICARE — § 1401 / § 3101 (Workstream 2).

Authority:
- 26 U.S.C. § 1401 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
- 26 U.S.C. § 1402 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402
- 26 U.S.C. § 3101 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
- IRS Schedule SE — https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
- IRS Form 8959 — https://www.irs.gov/forms-pubs/about-form-8959
- SSA U.S.-Germany Totalization Agreement (1979) —
  https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
- 2025 SSA wage base ($176,100): https://www.ssa.gov/oact/cola/cbb.html

Workstream 2 fills the SE-tax + Additional Medicare gap that was a
NotImplementedError in ``tax_pipeline/y2025/us_inputs.py``. § 1401(a)
imposes 12.4 % OASDI on net SE earnings up to the SS wage base;
§ 1401(b)(1) imposes 2.9 % Medicare on all net SE earnings; § 1402(a)(12)
reduces the base to 92.35 %. § 1401(b)(2) and § 3101(b)(2) impose an
additional 0.9 % Medicare on the COMBINED wage + SE base above the
filing-status threshold ($200k/$250k/$125k, statutory non-indexed).
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    ADDITIONAL_MEDICARE_RATE,
    ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD,
    ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD,
    ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD,
    MEDICARE_RATE,
    OASDI_RATE,
    SECA_NET_EARNINGS_FACTOR,
    SS_WAGE_BASE_2025_USD,
    USC_1401_URL,
    USC_3101_URL,
    USSelfEmploymentInputs2025,
    additional_medicare_assessment_2025,
    se_tax_assessment_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

D = Decimal


class SEMedicareConstants2025Test(unittest.TestCase):
    """Pin SSA / IRS / statutory numerics for 2025."""

    def test_ss_wage_base_2025(self) -> None:
        # SSA 2025 wage base.
        self.assertEqual(SS_WAGE_BASE_2025_USD, D("176100"))

    def test_seca_net_earnings_factor(self) -> None:
        # § 1402(a)(12) — 92.35 %.
        self.assertEqual(SECA_NET_EARNINGS_FACTOR, D("0.9235"))

    def test_se_rates(self) -> None:
        # § 1401(a) — 12.4 % OASDI; § 1401(b)(1) — 2.9 % Medicare.
        self.assertEqual(OASDI_RATE, D("0.124"))
        self.assertEqual(MEDICARE_RATE, D("0.029"))

    def test_additional_medicare_thresholds(self) -> None:
        # § 3101(b)(2)(A)-(C) — statutory non-indexed thresholds.
        self.assertEqual(ADDITIONAL_MEDICARE_THRESHOLD_SINGLE_2025_USD, D("200000"))
        self.assertEqual(ADDITIONAL_MEDICARE_THRESHOLD_MFJ_2025_USD, D("250000"))
        self.assertEqual(ADDITIONAL_MEDICARE_THRESHOLD_MFS_2025_USD, D("125000"))
        self.assertEqual(ADDITIONAL_MEDICARE_RATE, D("0.009"))


class SETaxNoSEEarningsTest(unittest.TestCase):
    """Demo posture has no SE earnings — verify the helper short-
    circuits to zero outputs."""

    def test_zero_net_se_earnings(self) -> None:
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("0"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertEqual(result.se_tax_usd, D("0.00"))
        self.assertEqual(result.oasdi_tax_usd, D("0.00"))
        self.assertEqual(result.medicare_tax_usd, D("0.00"))


class SETaxNonZeroEarningsTest(unittest.TestCase):
    """§ 1401 SE-tax math on positive net SE earnings."""

    def test_se_tax_under_wage_base(self) -> None:
        # Net SE = $100,000 → SE-taxable = $92,350 (× 0.9235).
        # OASDI tax: $92,350 × 0.124 = $11,451.40
        # Medicare tax: $92,350 × 0.029 = $2,678.15
        # Total SE tax: $14,129.55
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("100000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertEqual(result.se_taxable_earnings_usd, D("92350.00"))
        self.assertEqual(result.oasdi_taxable_earnings_usd, D("92350.00"))
        self.assertEqual(result.oasdi_tax_usd, D("11451.40"))
        self.assertEqual(result.medicare_tax_usd, D("2678.15"))
        self.assertEqual(result.se_tax_usd, D("14129.55"))

    def test_oasdi_capped_at_ss_wage_base(self) -> None:
        # Net SE = $200,000 → SE-taxable = $184,700 (× 0.9235).
        # OASDI base capped at $176,100 (SS wage base).
        # OASDI: $176,100 × 0.124 = $21,836.40
        # Medicare: $184,700 × 0.029 = $5,356.30
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("200000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertEqual(result.se_taxable_earnings_usd, D("184700.00"))
        self.assertEqual(result.oasdi_taxable_earnings_usd, D("176100.00"))
        self.assertEqual(result.oasdi_tax_usd, D("21836.40"))
        self.assertEqual(result.medicare_tax_usd, D("5356.30"))


class SETaxTotalizationCertificateTest(unittest.TestCase):
    """U.S.-Germany Totalization Agreement (1979) — Phase 0.

    A self-employed U.S. citizen resident in Germany who holds a German
    Certificate of Coverage is covered by the German social-insurance
    system and is EXEMPT from § 1401. The assessment is returned as an
    explicit Totalization exemption (zero tax, exempt marker, citation),
    not a silent zero and not a fail-closed error.
    Authority: SSA U.S.-Germany Totalization Agreement (1979),
    https://www.ssa.gov/international/Agreement_Pamphlets/germany.html.
    """

    def test_certificate_present_is_exempt_zero_se_tax(self) -> None:
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("50000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=True,
            )
        )
        # Exempt → every § 1401 tax component is zero.
        self.assertEqual(result.se_tax_usd, D("0.00"))
        self.assertEqual(result.oasdi_tax_usd, D("0.00"))
        self.assertEqual(result.medicare_tax_usd, D("0.00"))
        self.assertEqual(result.se_taxable_earnings_usd, D("0.00"))
        self.assertEqual(result.oasdi_taxable_earnings_usd, D("0.00"))
        # But the earnings are still reported (disclosure), and the
        # exemption is explicitly marked and cited — not a silent zero.
        self.assertEqual(result.net_se_earnings_usd, D("50000.00"))
        self.assertTrue(result.exempt_under_totalization)
        self.assertIn("Totalization", result.coverage_basis)

    def test_exempt_zero_is_distinguishable_from_no_earnings_zero(self) -> None:
        # I13 / null-zero-missing: both produce $0 SE tax, but the basis
        # and the exemption marker differ so the audit trail can tell
        # "exempt under a treaty" apart from "had no SE income".
        exempt = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("50000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=True,
            )
        )
        no_earnings = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("0"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertEqual(exempt.se_tax_usd, no_earnings.se_tax_usd)  # both 0
        self.assertTrue(exempt.exempt_under_totalization)
        self.assertFalse(no_earnings.exempt_under_totalization)
        self.assertNotEqual(exempt.coverage_basis, no_earnings.coverage_basis)

    def test_computed_branch_reports_section_1401_basis(self) -> None:
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("100000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertFalse(result.exempt_under_totalization)
        self.assertIn("§ 1401", result.coverage_basis)


class AdditionalMedicareTest(unittest.TestCase):
    """§ 3101(b)(2) + § 1401(b)(2) Additional Medicare Tax."""

    def test_below_threshold_zero_tax(self) -> None:
        # Combined base $150,000 < $200,000 single threshold.
        result = additional_medicare_assessment_2025(
            filing_status_label="Single",
            medicare_taxable_wages_usd=D("100000"),
            se_taxable_earnings_usd=D("50000"),
        )
        self.assertEqual(result.threshold_usd, D("200000"))
        self.assertEqual(result.combined_base_usd, D("150000.00"))
        self.assertEqual(result.excess_over_threshold_usd, D("0.00"))
        self.assertEqual(result.additional_medicare_tax_usd, D("0.00"))

    def test_above_threshold_single(self) -> None:
        # Combined base $250,000 → excess $50,000 → 0.9 % = $450.
        result = additional_medicare_assessment_2025(
            filing_status_label="Single",
            medicare_taxable_wages_usd=D("200000"),
            se_taxable_earnings_usd=D("50000"),
        )
        self.assertEqual(result.excess_over_threshold_usd, D("50000.00"))
        self.assertEqual(result.additional_medicare_tax_usd, D("450.00"))

    def test_mfj_threshold_higher(self) -> None:
        # Combined base $260k MFJ → excess $10k → 0.9 % = $90.
        result = additional_medicare_assessment_2025(
            filing_status_label="Married filing jointly",
            medicare_taxable_wages_usd=D("260000"),
            se_taxable_earnings_usd=D("0"),
        )
        self.assertEqual(result.threshold_usd, D("250000"))
        self.assertEqual(result.additional_medicare_tax_usd, D("90.00"))

    def test_mfs_threshold_lower(self) -> None:
        # MFS threshold = $125,000.
        result = additional_medicare_assessment_2025(
            filing_status_label="Married filing separately",
            medicare_taxable_wages_usd=D("125000"),
            se_taxable_earnings_usd=D("10000"),
        )
        self.assertEqual(result.threshold_usd, D("125000"))
        self.assertEqual(result.excess_over_threshold_usd, D("10000.00"))
        self.assertEqual(result.additional_medicare_tax_usd, D("90.00"))


class SETaxStageDeclarationTest(unittest.TestCase):
    """US25-SE-TAX and US25-ADDITIONAL-MEDICARE stages are declared and
    cite the controlling sections per CLAUDE.md.
    """

    def test_se_and_additional_medicare_stages_declared(self) -> None:
        stage_ids = [s.stage_id for s in usa_law_stages_2025()]
        self.assertIn("US25-SE-TAX", stage_ids)
        self.assertIn("US25-ADDITIONAL-MEDICARE", stage_ids)

    def test_us25_se_tax_cites_section_1401(self) -> None:
        se = next(s for s in usa_law_stages_2025() if s.stage_id == "US25-SE-TAX")
        self.assertTrue(any("§ 1401" in ref for ref in se.legal_refs))
        self.assertIn(USC_1401_URL, se.authority_urls)

    def test_additional_medicare_cites_section_3101(self) -> None:
        am = next(
            s for s in usa_law_stages_2025() if s.stage_id == "US25-ADDITIONAL-MEDICARE"
        )
        self.assertTrue(any("§ 3101" in ref for ref in am.legal_refs))
        self.assertIn(USC_3101_URL, am.authority_urls)


class SETaxDemoWorkspaceTest(unittest.TestCase):
    """Demo workspace has no SE earnings — loader produces zero SE
    inputs and the helpers short-circuit to zero.
    """

    def test_demo_workspace_has_zero_se_inputs(self) -> None:
        import tempfile
        from pathlib import Path

        from tax_pipeline.demo_workspace import materialize_demo_workspace
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertEqual(inputs.se_inputs.net_se_earnings_usd, D("0.00"))
            self.assertEqual(
                inputs.se_inputs.us_w2_medicare_taxable_wages_usd, D("0.00")
            )
            self.assertFalse(inputs.se_inputs.totalization_certificate_present)


class Section164fOneHalfSETaxAGIDeductionTest(unittest.TestCase):
    """F-C1 — 26 U.S.C. § 164(f)(1) one-half SE-tax above-the-line
    deduction must reduce AGI in US25-07-AGI.

    Authority:
      - 26 U.S.C. § 164(f)(1):
        https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
      - Schedule 1 (Form 1040), line 15 — "Deductible part of
        self-employment tax".
        https://www.irs.gov/forms-pubs/about-schedule-1-form-1040

    The deduction is one-half of § 1401 SE tax (§ 1401(a) OASDI +
    § 1401(b)(1) Medicare). § 1401(b)(2) Additional Medicare is NOT
    deductible under § 164(f) and is computed in
    ``US25-ADDITIONAL-MEDICARE``.
    """

    def test_us25_07_agi_declares_se_tax_input(self) -> None:
        # I7: AGI's input declarations must list us.stage.se_tax so the
        # § 164(f) one-half-SE-tax deduction has a fingerprinted upstream.
        agi_stage = next(
            s for s in usa_law_stages_2025() if s.stage_id == "US25-07-AGI"
        )
        self.assertIn("us.stage.se_tax", agi_stage.input_fact_keys)

    def test_us25_07_cites_section_164f(self) -> None:
        agi_stage = next(
            s for s in usa_law_stages_2025() if s.stage_id == "US25-07-AGI"
        )
        joined = " ".join(agi_stage.legal_refs)
        self.assertIn("§ 164(f)", joined)

    def test_se_tax_stage_runs_before_agi(self) -> None:
        ids = [s.stage_id for s in usa_law_stages_2025()]
        self.assertIn("US25-SE-TAX", ids)
        self.assertIn("US25-07-AGI", ids)
        self.assertLess(ids.index("US25-SE-TAX"), ids.index("US25-07-AGI"))

    def test_50k_se_earnings_reduces_agi_by_half_se_tax(self) -> None:
        # § 1401 SE tax on $50,000 net SE earnings:
        #   SE-taxable = 50,000 * 0.9235 = 46,175.00
        #   OASDI = 46,175.00 * 0.124 = 5,725.70
        #   Medicare = 46,175.00 * 0.029 = 1,339.0775 → 1,339.08
        #   SE tax = 5,725.70 + 1,339.08 = 7,064.78
        # § 164(f)(1) deduction = 7,064.78 / 2 = 3,532.39
        result = se_tax_assessment_2025(
            se_inputs=USSelfEmploymentInputs2025(
                net_se_earnings_usd=D("50000"),
                us_w2_medicare_taxable_wages_usd=D("0"),
                totalization_certificate_present=False,
            )
        )
        self.assertEqual(result.se_tax_usd, D("7064.78"))
        # AGI helper: simulate calling adjusted_gross_income_2025 with the
        # one-half SE-tax deduction. Confirm AGI is reduced by exactly the
        # deduction amount when all other AGI inputs are held constant.
        from tax_pipeline.y2025.us_law import (
            adjusted_gross_income_2025,
            round_cents,
        )

        baseline_agi = adjusted_gross_income_2025(
            wages_usd=D("100000.00"),
            ordinary_dividends_usd=D("0.00"),
            interest_income_usd=D("0.00"),
            schedule_1_other_income_usd=D("0.00"),
            form_1040_line_7a_usd=D("0.00"),
        )
        one_half_se = round_cents(result.se_tax_usd / D("2"))
        self.assertEqual(one_half_se, D("3532.39"))
        agi_with_deduction = adjusted_gross_income_2025(
            wages_usd=D("100000.00"),
            ordinary_dividends_usd=D("0.00"),
            interest_income_usd=D("0.00"),
            schedule_1_other_income_usd=D("0.00"),
            form_1040_line_7a_usd=D("0.00"),
            one_half_se_tax_deduction_usd=one_half_se,
        )
        self.assertEqual(baseline_agi - agi_with_deduction, one_half_se)
        self.assertEqual(agi_with_deduction, D("96467.61"))

    def test_zero_se_tax_leaves_agi_unchanged(self) -> None:
        # Demo posture has no SE earnings → SE tax = 0 → AGI unaffected.
        from tax_pipeline.y2025.us_law import adjusted_gross_income_2025

        agi = adjusted_gross_income_2025(
            wages_usd=D("100000.00"),
            ordinary_dividends_usd=D("0.00"),
            interest_income_usd=D("0.00"),
            schedule_1_other_income_usd=D("0.00"),
            form_1040_line_7a_usd=D("0.00"),
            one_half_se_tax_deduction_usd=D("0.00"),
        )
        self.assertEqual(agi, D("100000.00"))

    def test_negative_se_tax_deduction_fails_closed(self) -> None:
        from tax_pipeline.y2025.us_law import adjusted_gross_income_2025

        with self.assertRaisesRegex(ValueError, "one_half_se_tax_deduction_usd"):
            adjusted_gross_income_2025(
                wages_usd=D("100000.00"),
                ordinary_dividends_usd=D("0.00"),
                interest_income_usd=D("0.00"),
                schedule_1_other_income_usd=D("0.00"),
                form_1040_line_7a_usd=D("0.00"),
                one_half_se_tax_deduction_usd=D("-1.00"),
            )


if __name__ == "__main__":
    unittest.main()
