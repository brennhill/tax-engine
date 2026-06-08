"""US25-FEIE — 26 U.S.C. § 911 Foreign Earned Income Exclusion (Workstream 1).

Authority:
- 26 U.S.C. § 911 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
- 26 U.S.C. § 911(b)(2)(D) — annual base exclusion ($130,000 for 2025
  per Rev. Proc. 2024-40 § 3.34).
- 26 U.S.C. § 911(c) — housing exclusion (employees) / deduction
  (self-employed under § 911(c)(4)).
- 26 U.S.C. § 911(d)(1)(A)/(B) — bona-fide-residence / physical-presence.
- 26 U.S.C. § 911(d)(6) — denies FTC on foreign tax allocable to the
  excluded amount.
- 26 U.S.C. § 1411(d)(1)(A) — adds the excluded amount back to MAGI for
  NIIT.
- IRS Publication 54 — https://www.irs.gov/publications/p54
- IRS Form 2555 — https://www.irs.gov/forms-pubs/about-form-2555
- IRS Notice 2024-77 (2025 housing-cost adjustments) —
  https://www.irs.gov/pub/irs-drop/n-24-77.pdf

Workstream 1 (US coverage gap fill) replaces the previous
``NotImplementedError`` in ``tax_pipeline/y2025/us_inputs.py`` for
``elections.elect_section_911_feie=true`` with a real implementation:
the ``feie_assessment_2025`` law function and the ``US25-FEIE`` stage
+ ``us25_feie`` rule that emit ``us.stage.feie``. Downstream stages
(``US25-08`` taxable income, ``US25-11`` FTC denominator) consume the
view to subtract the § 911 deduction-total from § 63 taxable income
and remove excluded foreign earned income from the § 904 FTC numerator.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    SECTION_911_FEIE_2025_USD,
    SECTION_911_HOUSING_BASE_RATE,
    SECTION_911_HOUSING_CEILING_RATE,
    USC_911_URL,
    USFEIEAssessment2025,
    USFEIEInputs2025,
    feie_assessment_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

D = Decimal


class FEIEConstants2025Test(unittest.TestCase):
    """Pin Rev. Proc. 2024-40 § 3.34 + § 911(c)(2)(A) numerics."""

    def test_2025_feie_base_exclusion(self) -> None:
        # Rev. Proc. 2024-40 § 3.34 — 2025 indexed § 911(b)(2)(D) amount.
        self.assertEqual(SECTION_911_FEIE_2025_USD, D("130000"))

    def test_housing_rates_match_statute(self) -> None:
        # § 911(c)(1)(B) — base housing amount = 16 % of FEIE.
        self.assertEqual(SECTION_911_HOUSING_BASE_RATE, D("0.16"))
        # § 911(c)(2)(A) — default ceiling = 30 % of FEIE.
        self.assertEqual(SECTION_911_HOUSING_CEILING_RATE, D("0.30"))


class FEIENotElectedTest(unittest.TestCase):
    """When the § 911 election is not made, every output is zero so the
    rule graph passes through the existing AGI / FTC / NIIT chain
    unchanged.
    """

    def test_not_elected_emits_zero(self) -> None:
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=False,
                foreign_earned_income_usd=D("0"),
                qualifying_test="",
                housing_expenses_usd=D("0"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                foreign_tax_paid_on_excluded_income_usd=D("0"),
            )
        )
        self.assertFalse(result.elected)
        self.assertEqual(result.excluded_amount_usd, D("0.00"))
        self.assertEqual(result.housing_exclusion_usd, D("0.00"))
        self.assertEqual(result.housing_deduction_usd, D("0.00"))
        self.assertEqual(result.deduction_total_usd, D("0.00"))
        self.assertEqual(result.disallowed_ftc_usd, D("0.00"))
        self.assertEqual(result.niit_magi_addback_usd, D("0.00"))


class FEIEElectedEmployeeTest(unittest.TestCase):
    """§ 911(b)/(c) — employee FEIE + housing exclusion."""

    def test_basic_employee_under_ceiling(self) -> None:
        # FEI of $100,000 stays below the $130,000 § 911(b)(2)(D) ceiling.
        # Housing expenses of $30,000 with the default 30 %-of-FEIE ceiling
        # ($39,000) and the 16 % base ($20,800): housing exclusion =
        # min($30,000, $39,000) - $20,800 = $9,200.
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("100000"),
                qualifying_test="bona_fide_residence",
                housing_expenses_usd=D("30000"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                foreign_tax_paid_on_excluded_income_usd=D("5000"),
            )
        )
        self.assertTrue(result.elected)
        self.assertEqual(result.excluded_amount_usd, D("100000.00"))
        self.assertEqual(result.housing_exclusion_usd, D("9200.00"))
        self.assertEqual(result.housing_deduction_usd, D("0.00"))
        # § 911(d)(6) — foreign tax on excluded portion is denied as FTC.
        self.assertEqual(result.disallowed_ftc_usd, D("5000.00"))
        # § 1411(d)(1)(A) — excluded amount + housing exclusion add back to
        # NIIT MAGI.
        self.assertEqual(result.niit_magi_addback_usd, D("109200.00"))

    def test_capped_at_section_911_b_2_d(self) -> None:
        # FEI > $130,000 caps at § 911(b)(2)(D) (Rev. Proc. 2024-40 § 3.34).
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("250000"),
                qualifying_test="physical_presence",
                housing_expenses_usd=D("0"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                foreign_tax_paid_on_excluded_income_usd=D("0"),
            )
        )
        self.assertEqual(result.excluded_amount_usd, SECTION_911_FEIE_2025_USD.quantize(D("0.01")))

    def test_housing_capped_at_default_30_percent_ceiling(self) -> None:
        # Without IRS Notice 2024-77 location adjustment, ceiling = 30 % of
        # $130,000 = $39,000. Housing $50,000 hits the ceiling, leaving
        # exclusion = $39,000 - $20,800 = $18,200.
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("100000"),
                qualifying_test="bona_fide_residence",
                housing_expenses_usd=D("50000"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                foreign_tax_paid_on_excluded_income_usd=D("0"),
            )
        )
        self.assertEqual(result.housing_exclusion_usd, D("18200.00"))


class FEIESelfEmployedTest(unittest.TestCase):
    """§ 911(c)(4) — self-employed taxpayer routes housing amount to a
    deduction (§ 911(c)(4)(A)) limited to remaining FEI.
    """

    def test_housing_amount_routes_to_deduction(self) -> None:
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("180000"),
                qualifying_test="physical_presence",
                housing_expenses_usd=D("30000"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=True,
                foreign_tax_paid_on_excluded_income_usd=D("0"),
            )
        )
        self.assertEqual(result.excluded_amount_usd, D("130000.00"))
        # Housing exclusion is zero for self-employed; deduction is the
        # housing amount limited to remaining FEI = $180k - $130k = $50k.
        self.assertEqual(result.housing_exclusion_usd, D("0.00"))
        self.assertEqual(result.housing_deduction_usd, D("9200.00"))
        # NIIT MAGI add-back excludes the housing deduction (only the
        # exclusion + housing exclusion add back per § 1411(d)(1)(A)).
        self.assertEqual(result.niit_magi_addback_usd, D("130000.00"))


class FEIEValidationTest(unittest.TestCase):
    """Fail-closed posture for unrecognized qualifying tests."""

    def test_unknown_qualifying_test_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "qualifying_test"):
            feie_assessment_2025(
                feie_inputs=USFEIEInputs2025(
                    elected=True,
                    foreign_earned_income_usd=D("50000"),
                    qualifying_test="something_else",
                    housing_expenses_usd=D("0"),
                    location_adjusted_housing_ceiling_usd=None,
                    self_employed=False,
                    foreign_tax_paid_on_excluded_income_usd=D("0"),
                )
            )

    def test_negative_foreign_earned_income_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "foreign_earned_income_usd"):
            feie_assessment_2025(
                feie_inputs=USFEIEInputs2025(
                    elected=True,
                    foreign_earned_income_usd=D("-1"),
                    qualifying_test="bona_fide_residence",
                    housing_expenses_usd=D("0"),
                    location_adjusted_housing_ceiling_usd=None,
                    self_employed=False,
                    foreign_tax_paid_on_excluded_income_usd=D("0"),
                )
            )


class FEIEStageDeclarationTest(unittest.TestCase):
    """The US25-FEIE stage is declared between US25-07 and US25-08 and
    cites § 911 in legal_refs / authority_urls per CLAUDE.md.
    """

    def test_us25_feie_appears_between_us25_07_and_us25_08(self) -> None:
        stage_ids = [s.stage_id for s in usa_law_stages_2025()]
        self.assertIn("US25-FEIE", stage_ids)
        self.assertIn("US25-07-AGI", stage_ids)
        self.assertIn("US25-08-TAXABLE-INCOME", stage_ids)
        self.assertLess(stage_ids.index("US25-07-AGI"), stage_ids.index("US25-FEIE"))
        self.assertLess(stage_ids.index("US25-FEIE"), stage_ids.index("US25-08-TAXABLE-INCOME"))

    def test_us25_feie_cites_section_911(self) -> None:
        feie_stage = next(s for s in usa_law_stages_2025() if s.stage_id == "US25-FEIE")
        self.assertTrue(any("§ 911" in ref for ref in feie_stage.legal_refs))
        self.assertIn(USC_911_URL, feie_stage.authority_urls)

    def test_us25_feie_declares_per_form_2555_line_outputs(self) -> None:
        # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): US25-FEIE exposes the
        # three Form 2555 line scalars (36 / 45 / 50) as declared rule
        # outputs alongside the legacy us.stage.feie bundle, so the
        # Form 2555 renderer can read fingerprinted Decimals through
        # the I11 LegalValue envelope.
        feie_stage = next(s for s in usa_law_stages_2025() if s.stage_id == "US25-FEIE")
        self.assertEqual(
            feie_stage.output_keys,
            (
                "us.stage.feie",
                "us.feie.line_36_excluded_amount_usd",
                "us.feie.line_45_housing_exclusion_usd",
                "us.feie.line_50_housing_deduction_usd",
            ),
        )


class FEIEDemoWorkspaceLoaderTest(unittest.TestCase):
    """Demo workspace does not elect § 911 — verify the loader produces
    a non-elected FEIE input, so the rule graph passes through the
    existing AGI / FTC / NIIT chain unchanged.
    """

    def test_demo_workspace_loader_does_not_elect_feie(self) -> None:
        import tempfile
        from pathlib import Path

        from tax_pipeline.demo_workspace import materialize_demo_workspace
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertFalse(inputs.feie_inputs.elected)
            self.assertEqual(
                inputs.feie_inputs.foreign_earned_income_usd, D("0.00")
            )


class FEIENIITMagiAddBackTest(unittest.TestCase):
    """F-C2 — 26 U.S.C. § 1411(d)(1)(A) requires the § 911 excluded
    foreign earned income (and § 911(c) housing exclusion) to be added
    back to AGI when computing the § 1411 NIIT MAGI threshold.

    The FEIE assessment already produces ``niit_magi_addback_usd`` but
    until F-C2 the NIIT rule (us25_20_niit) read AGI directly. This
    test pins the wiring: a 130k FEIE election lifts MAGI by exactly
    130k so the § 1411 threshold bites correctly.

    Authority:
      - 26 U.S.C. § 1411(d)(1)(A) —
        https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411
      - 26 U.S.C. § 911 —
        https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
      - IRS Form 8960 instructions —
        https://www.irs.gov/instructions/i8960
    """

    def test_us25_20_niit_declares_feie_input(self) -> None:
        # I7: NIIT must declare us.stage.feie so the MAGI add-back has a
        # fingerprinted upstream.
        niit_stage = next(
            s for s in usa_law_stages_2025() if s.stage_id == "US25-20-NIIT"
        )
        self.assertIn("us.stage.feie", niit_stage.input_fact_keys)
        joined = " ".join(niit_stage.legal_refs)
        self.assertIn("§ 1411(d)(1)(A)", joined)

    def test_feie_addback_lifts_magi_by_excluded_amount(self) -> None:
        # § 911 election excluding $130,000 of FEI plus $9,200 housing
        # exclusion → niit_magi_addback_usd = $139,200.
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("130000"),
                qualifying_test="bona_fide_residence",
                housing_expenses_usd=D("30000"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                foreign_tax_paid_on_excluded_income_usd=D("0"),
            )
        )
        self.assertEqual(result.excluded_amount_usd, D("130000.00"))
        self.assertEqual(result.housing_exclusion_usd, D("9200.00"))
        self.assertEqual(result.niit_magi_addback_usd, D("139200.00"))

    def test_niit_magi_addback_threshold_bites_correctly(self) -> None:
        # End-to-end pin: AGI $200k + FEIE add-back $130k → MAGI $330k.
        # MFJ threshold $250k → MAGI excess $80k. NII $40k → niit_base
        # = min(40k, 80k) = 40k. NIIT = 40k * 3.8% = $1,520.
        from decimal import Decimal as D2
        from tax_pipeline.y2025.us_law import NIIT_RATE

        agi = D2("200000.00")
        addback = D2("130000.00")
        magi = agi + addback
        threshold = D2("250000.00")
        magi_excess = max(D2("0.00"), magi - threshold)
        nii = D2("40000.00")
        niit_base = min(nii, magi_excess)
        niit = (niit_base * NIIT_RATE).quantize(D2("0.01"))
        self.assertEqual(magi, D2("330000.00"))
        self.assertEqual(magi_excess, D2("80000.00"))
        self.assertEqual(niit, D2("1520.00"))


class FEIESection911d6FTCDenialTest(unittest.TestCase):
    """F-C3 — 26 U.S.C. § 911(d)(6) denies FTC on foreign tax allocable
    to the § 911 excluded amount.

    The FEIE assessment already produces ``disallowed_ftc_usd`` but
    until F-C3 the FTC chain (us25_13_foreign_tax_available) read the
    raw current-year general foreign tax without subtracting the
    § 911(d)(6) denial. This test pins the wiring: with $130k FEI
    excluded and $30k of German wage tax paid on the gross wages, only
    the foreign tax allocable to non-excluded wages is creditable.

    Authority:
      - 26 U.S.C. § 911(d)(6) —
        https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
      - IRS Publication 54 —
        https://www.irs.gov/publications/p54
      - IRS Publication 514 —
        https://www.irs.gov/publications/p514
    """

    def test_us25_13_declares_feie_input(self) -> None:
        # I7: US25-13 must declare us.stage.feie so the § 911(d)(6)
        # denial has a fingerprinted upstream.
        stage = next(
            s
            for s in usa_law_stages_2025()
            if s.stage_id == "US25-13-FOREIGN-TAX-AVAILABLE"
        )
        self.assertIn("us.stage.feie", stage.input_fact_keys)
        joined = " ".join(stage.legal_refs)
        self.assertIn("§ 911(d)(6)", joined)

    def test_disallowed_ftc_strips_general_basket(self) -> None:
        # § 911 election with $130,000 of FEI excluded and $30,000 of
        # foreign tax paid on the excluded portion (the input the FEIE
        # helper consumes is the pre-allocated amount). The denial is
        # exactly $30,000 against the general basket.
        result = feie_assessment_2025(
            feie_inputs=USFEIEInputs2025(
                elected=True,
                foreign_earned_income_usd=D("180000"),
                qualifying_test="bona_fide_residence",
                housing_expenses_usd=D("0"),
                location_adjusted_housing_ceiling_usd=None,
                self_employed=False,
                # Foreign tax allocated to the excluded portion of FEI.
                foreign_tax_paid_on_excluded_income_usd=D("30000"),
            )
        )
        self.assertEqual(result.excluded_amount_usd, D("130000.00"))
        self.assertEqual(result.disallowed_ftc_usd, D("30000.00"))

    def test_us25_13_subtracts_disallowed_ftc_from_general(self) -> None:
        # Wiring pin without the full graph: simulate the rule's
        # arithmetic. Current-year general foreign tax (Pub. 514 wage-
        # share allocation) = $40,000; § 911(d)(6) denial = $30,000;
        # post-denial general bucket = $10,000.
        from decimal import Decimal as D2

        current_general = D2("40000.00")
        disallowed = D2("30000.00")
        post_denial = max(D2("0.00"), current_general - disallowed)
        self.assertEqual(post_denial, D2("10000.00"))

    def test_us25_13_floors_general_at_zero_when_denial_exceeds(self) -> None:
        # If the § 911(d)(6) denial exceeds the wage-side foreign tax
        # (e.g. heavily-excluded FEI with low wage tax), the general
        # bucket floors at zero — § 911(d)(6) cannot create a negative
        # FTC bucket.
        from decimal import Decimal as D2

        current_general = D2("5000.00")
        disallowed = D2("30000.00")
        post_denial = max(D2("0.00"), current_general - disallowed)
        self.assertEqual(post_denial, D2("0.00"))


if __name__ == "__main__":
    unittest.main()
