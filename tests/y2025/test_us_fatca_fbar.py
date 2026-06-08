"""US25-FATCA-FBAR-DETERMINATION — 26 U.S.C. § 6038D Form 8938 + 31 CFR
§ 1010.350 FBAR (Group D, FORM-MAPPING-FOLLOWUP, 2026-05-03).

Authority:
- 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
- 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
- IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
- 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
- 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
- FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/

Determination-only stage. Does not affect tax owed. The rule fails
closed (status="not_applicable") when the workspace lacks foreign-
account data; otherwise computes REQUIRED / NOT REQUIRED for both
regimes.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    FATCA_8938_THRESHOLD_ABROAD_MFJ_ANYTIME_USD,
    FATCA_8938_THRESHOLD_ABROAD_MFJ_EOY_USD,
    FATCA_8938_THRESHOLD_ABROAD_SINGLE_ANYTIME_USD,
    FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD,
    FATCA_8938_THRESHOLD_DOMESTIC_MFJ_ANYTIME_USD,
    FATCA_8938_THRESHOLD_DOMESTIC_MFJ_EOY_USD,
    FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_ANYTIME_USD,
    FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_EOY_USD,
    FBAR_AGGREGATE_THRESHOLD_USD,
    USFATCAFBARInputs2025,
    USForeignFinancialAccount2025,
    fatca_fbar_assessment_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

D = Decimal


class FATCAFBARThresholdConstants2025Test(unittest.TestCase):
    """Pin Reg. § 1.6038D-2(b) thresholds + 31 CFR § 1010.350 threshold.

    The 2025 IRS Form 8938 instructions hold these unchanged from the
    2024 figures (the thresholds are not inflation-indexed). FBAR is
    fixed at $10,000 statutorily and never inflation-indexed.
    """

    def test_threshold_constants_match_regulations(self) -> None:
        # Reg. § 1.6038D-2(b)(2) domestic + (b)(3) abroad + 31 CFR
        # § 1010.350(a) FBAR. A regression that flips one constant is
        # caught with the citation in the subTest label.
        cases = (
            (FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_EOY_USD, D("50000"),
             "§ 1.6038D-2(b)(2) domestic single EOY"),
            (FATCA_8938_THRESHOLD_DOMESTIC_SINGLE_ANYTIME_USD, D("75000"),
             "§ 1.6038D-2(b)(2) domestic single anytime"),
            (FATCA_8938_THRESHOLD_DOMESTIC_MFJ_EOY_USD, D("100000"),
             "§ 1.6038D-2(b)(2) domestic MFJ EOY"),
            (FATCA_8938_THRESHOLD_DOMESTIC_MFJ_ANYTIME_USD, D("150000"),
             "§ 1.6038D-2(b)(2) domestic MFJ anytime"),
            (FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD, D("200000"),
             "§ 1.6038D-2(b)(3) abroad single EOY"),
            (FATCA_8938_THRESHOLD_ABROAD_SINGLE_ANYTIME_USD, D("300000"),
             "§ 1.6038D-2(b)(3) abroad single anytime"),
            (FATCA_8938_THRESHOLD_ABROAD_MFJ_EOY_USD, D("400000"),
             "§ 1.6038D-2(b)(3) abroad MFJ EOY"),
            (FATCA_8938_THRESHOLD_ABROAD_MFJ_ANYTIME_USD, D("600000"),
             "§ 1.6038D-2(b)(3) abroad MFJ anytime"),
            (FBAR_AGGREGATE_THRESHOLD_USD, D("10000"),
             "31 CFR § 1010.350(a) FBAR aggregate"),
        )
        for actual, expected, citation in cases:
            with self.subTest(citation=citation):
                self.assertEqual(actual, expected)


class FATCAFBARDataCompleteFalseTest(unittest.TestCase):
    """Per CLAUDE.md fail-closed posture, ``data_complete=False`` must
    surface ``status="not_applicable"`` with a citation. A silent zero
    would be indistinguishable from "below threshold" and is
    unacceptable for filings carrying significant non-filing penalties.
    """

    def test_data_incomplete_returns_not_applicable_with_citation(self) -> None:
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(),
                data_complete=False,
            )
        )
        self.assertEqual(result.status, "not_applicable")
        self.assertIn("§ 6038D", result.reason)
        self.assertIn("§ 1010.350", result.reason)
        self.assertFalse(result.form_8938_required)
        self.assertFalse(result.fincen_114_required)
        # Threshold scalars still surface for the renderer.
        self.assertEqual(
            result.form_8938_threshold_eoy_usd,
            FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD,
        )

    def test_empty_filing_status_returns_not_applicable(self) -> None:
        # Default-constructed fatca_fbar_inputs with empty filing status
        # must fail closed (this branch is hit by ad-hoc test fixtures
        # constructing USAssessmentInputs2025 without the loader).
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="",
                residency_basis="domestic",
                accounts=(),
                data_complete=False,
            )
        )
        self.assertEqual(result.status, "not_applicable")
        self.assertFalse(result.form_8938_required)
        self.assertFalse(result.fincen_114_required)


class FATCAFBARDomesticUnderThresholdTest(unittest.TestCase):
    """U.S.-resident, under threshold — neither form attaches."""

    def test_under_threshold_no_form_8938_no_fbar(self) -> None:
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Single",
                residency_basis="domestic",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="dr-cd-001",
                        country="DE",
                        institution="Sparkasse",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("8000"),
                        usd_eoy_balance=D("7500"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.status, "determined")
        self.assertFalse(result.form_8938_required)
        # 31 CFR § 1010.350: $8,000 aggregate is below $10,000 threshold.
        self.assertFalse(result.fincen_114_required)


class FATCAFBARDomesticOverThresholdTest(unittest.TestCase):
    """U.S.-resident, over threshold — both forms attach."""

    def test_domestic_single_over_threshold_both_required(self) -> None:
        # Single domestic: EOY > $50,000 OR max-anytime > $75,000.
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Single",
                residency_basis="domestic",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="acct-1",
                        country="DE",
                        institution="Sparkasse",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("80000"),
                        usd_eoy_balance=D("60000"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.status, "determined")
        # 26 U.S.C. § 6038D / Reg. § 1.6038D-2(b)(2): single domestic
        # filer with EOY $60,000 > $50,000 OR max $80,000 > $75,000.
        self.assertTrue(result.form_8938_required)
        # 31 CFR § 1010.350: $80,000 max > $10,000.
        self.assertTrue(result.fincen_114_required)


class FATCAFBARAbroadMFSTest(unittest.TestCase):
    """The brenn-2025 posture — MFS, U.S. citizen abroad — uses the
    abroad-tier $200K EOY / $300K anytime thresholds (Reg.
    § 1.6038D-2(b)(3) read with § 911(d)(1)(A))."""

    def test_mfs_abroad_just_under_threshold_form_8938_not_required(self) -> None:
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="schwab",
                        country="US",
                        institution="Schwab",
                        account_type="brokerage",
                        currency="USD",
                        usd_max_balance_during_year=D("250000"),
                        usd_eoy_balance=D("180000"),
                        # Schwab is US-domiciled; not § 6038D-scope SFFA.
                        is_specified_foreign_financial_asset=False,
                    ),
                    USForeignFinancialAccount2025(
                        account_id="comdirect",
                        country="DE",
                        institution="Comdirect",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("50000"),
                        usd_eoy_balance=D("45000"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.status, "determined")
        # SFFA aggregate is just $50,000 max / $45,000 EOY — below the
        # $200K EOY / $300K anytime abroad-MFS thresholds.
        self.assertFalse(result.form_8938_required)
        self.assertEqual(result.foreign_specified_assets_max_usd, D("50000.00"))
        self.assertEqual(result.foreign_specified_assets_eoy_usd, D("45000.00"))
        # FBAR scope is broader: $250K + $50K = $300K aggregate max,
        # well over the $10K FBAR threshold.
        self.assertEqual(result.fbar_aggregate_max_balance_usd, D("300000.00"))
        self.assertTrue(result.fincen_114_required)

    def test_mfs_abroad_over_threshold_form_8938_required(self) -> None:
        # SFFA EOY $250K > $200K threshold → Form 8938 attaches.
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="bank-1",
                        country="DE",
                        institution="Sparkasse",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("280000"),
                        usd_eoy_balance=D("250000"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.status, "determined")
        self.assertTrue(result.form_8938_required)
        self.assertTrue(result.fincen_114_required)
        # Reg. § 1.6038D-2(b)(3): MFS abroad uses the $200K EOY tier.
        self.assertEqual(
            result.form_8938_threshold_eoy_usd,
            FATCA_8938_THRESHOLD_ABROAD_SINGLE_EOY_USD,
        )


class FATCAFBARFBARScopeBroaderTest(unittest.TestCase):
    """31 CFR § 1010.350 scope is BROADER than § 6038D — the engine
    must aggregate ALL foreign accounts (not just SFFA-tagged)."""

    def test_fbar_aggregates_non_sffa_accounts(self) -> None:
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="non-sffa-acct",
                        country="DE",
                        institution="Some pension custodian",
                        account_type="pension",
                        currency="EUR",
                        usd_max_balance_during_year=D("12000"),
                        usd_eoy_balance=D("11000"),
                        is_specified_foreign_financial_asset=False,
                    ),
                ),
                data_complete=True,
            )
        )
        # SFFA aggregates are zero (the only account is not SFFA), so
        # Form 8938 does not attach.
        self.assertFalse(result.form_8938_required)
        # But FBAR aggregate is $12K > $10K — FBAR attaches.
        self.assertEqual(result.fbar_aggregate_max_balance_usd, D("12000.00"))
        self.assertTrue(result.fincen_114_required)


class FATCAFBARFBARBoundaryTest(unittest.TestCase):
    """31 CFR § 1010.350(a) uses the verb "exceed" — strict greater-than.
    $10,000.00 aggregate does NOT trigger; $10,000.01 does.

    Group D audit (2026-05-03): the prior 12 unit tests asserted
    above-threshold and well-below-threshold but did not pin the exact
    boundary. The boundary is the legally-load-bearing case — a future
    refactor that flipped ``>`` to ``>=`` would change the determination
    for the boundary cohort by exactly one cent and silently alter who
    is told to file FBAR. These two tests guard that flip.
    """

    def test_fbar_exactly_threshold_not_required(self) -> None:
        # 31 CFR § 1010.350(a) — "exceed $10,000" excludes $10,000 itself.
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Single",
                residency_basis="domestic",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="exact-10k",
                        country="DE",
                        institution="Sparkasse",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("10000.00"),
                        usd_eoy_balance=D("9000.00"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.fbar_aggregate_max_balance_usd, D("10000.00"))
        self.assertFalse(result.fincen_114_required)

    def test_fbar_one_cent_over_threshold_required(self) -> None:
        # $10,000.01 triggers (the legally-required boundary case).
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Single",
                residency_basis="domestic",
                accounts=(
                    USForeignFinancialAccount2025(
                        account_id="one-cent-over",
                        country="DE",
                        institution="Sparkasse",
                        account_type="bank",
                        currency="EUR",
                        usd_max_balance_during_year=D("10000.01"),
                        usd_eoy_balance=D("9000.00"),
                        is_specified_foreign_financial_asset=True,
                    ),
                ),
                data_complete=True,
            )
        )
        self.assertEqual(result.fbar_aggregate_max_balance_usd, D("10000.01"))
        self.assertTrue(result.fincen_114_required)


class FATCAFBARStageDeclarationTest(unittest.TestCase):
    """The US25-FATCA-FBAR-DETERMINATION stage carries the right
    citations and declared outputs (invariant I8 ensures the rule writes
    only declared keys)."""

    def test_stage_present_with_authority_citations(self) -> None:
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        self.assertIn("US25-FATCA-FBAR-DETERMINATION", stages)
        stage = stages["US25-FATCA-FBAR-DETERMINATION"]
        legal_refs = " | ".join(stage.legal_refs)
        self.assertIn("§ 6038D", legal_refs)
        self.assertIn("§ 5314", legal_refs)
        self.assertIn("§ 1010.350", legal_refs)
        urls = " | ".join(stage.authority_urls)
        self.assertIn("uscode/text/26/6038D", urls)
        self.assertIn("uscode/text/31/5314", urls)
        self.assertIn("cfr/text/31/1010.350", urls)
        self.assertIn("about-form-8938", urls)
        self.assertIn("bsaefiling.fincen.treas.gov", urls)

    def test_stage_declares_all_nine_outputs(self) -> None:
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        stage = stages["US25-FATCA-FBAR-DETERMINATION"]
        keys = {output.key for output in stage.outputs}
        self.assertEqual(
            keys,
            {
                "us.fatca.form_8938_threshold_eoy_usd",
                "us.fatca.form_8938_threshold_anytime_usd",
                "us.fatca.foreign_specified_assets_max_usd",
                "us.fatca.foreign_specified_assets_eoy_usd",
                "us.fatca.form_8938_required",
                "us.fbar.aggregate_max_balance_usd",
                "us.fbar.fincen_114_required",
                "us.fatca.determination_status",
                "us.fatca.determination_reason",
            },
        )


class FATCAFBARDiscoveredAccountsReasonTest(unittest.TestCase):
    """Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): when the loader
    populates ``inputs.accounts`` from the auto-derived stub CSV (with
    zero placeholder balances) but ``data_complete`` stays False, the
    rule must enumerate the discovered accounts in its reason text so
    the manual-determination renderer can list them.
    """

    def _stub_account(
        self, account_id: str, *, institution: str = "N26"
    ) -> USForeignFinancialAccount2025:
        return USForeignFinancialAccount2025(
            account_id=account_id,
            country="DE",
            institution=institution,
            account_type="bank",
            currency="EUR",
            usd_max_balance_during_year=D("0"),
            usd_eoy_balance=D("0"),
            is_specified_foreign_financial_asset=True,
        )

    def test_data_incomplete_with_accounts_lists_them_in_reason(self) -> None:
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(
                    self._stub_account("n26_brenn"),
                    self._stub_account("upvest_lien", institution="Upvest"),
                ),
                data_complete=False,
            )
        )
        self.assertEqual(result.status, "not_applicable")
        # Each discovered account must surface in the reason text so
        # the renderer's per-account row list lines up with the rule.
        self.assertIn("n26_brenn", result.reason)
        self.assertIn("upvest_lien", result.reason)
        # The reason must still cite the controlling regulations.
        self.assertIn("§ 6038D", result.reason)
        self.assertIn("§ 1010.350", result.reason)
        # form_8938_required and fincen_114_required stay False because
        # the engine cannot affirmatively determine threshold breach
        # without verified balances.
        self.assertFalse(result.form_8938_required)
        self.assertFalse(result.fincen_114_required)

    def test_data_incomplete_without_accounts_uses_legacy_reason(self) -> None:
        # The pre-Phase-5.2 reason text still applies when the loader
        # supplied no accounts at all (no derivation, empty workspace).
        result = fatca_fbar_assessment_2025(
            inputs=USFATCAFBARInputs2025(
                filing_status_label="Married filing separately",
                residency_basis="abroad_section_911_d_1_a",
                accounts=(),
                data_complete=False,
            )
        )
        self.assertEqual(result.status, "not_applicable")
        self.assertIn(
            "Foreign-financial-account fact source not yet populated",
            result.reason,
        )


class ProfileResidencyBasisForFatcaTest(unittest.TestCase):
    """Phase 5.1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): cover all four
    branches of ``_profile_residency_basis_for_fatca``.

    Authority: 26 U.S.C. § 911(d)(1)(A) and (B); Reg. § 1.6038D-2(b)(1)
    cross-references both prongs to set the Form 8938 thresholds.
    """

    def test_bona_fide_resident_us_citizen_returns_911_d_1_a(self) -> None:
        # § 911(d)(1)(A) — primary residence in a foreign country plus
        # U.S. citizenship is the load-bearing branch for brenn-2025.
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {
                "primary_tax_residence": "DE",
                "us_citizen_or_long_term_resident": True,
            }
        )
        self.assertEqual(result, "abroad_section_911_d_1_a")

    def test_330_day_physical_presence_branch(self) -> None:
        # § 911(d)(1)(B) — 330 full days abroad. Requires a U.S.
        # citizen / long-term resident with a non-bona-fide residency
        # posture (no foreign primary_tax_residence) but a populated
        # day-count fact >= 330.
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {
                "primary_tax_residence": "",
                "us_citizen_or_long_term_resident": True,
                "days_outside_us_during_year": 330,
            }
        )
        self.assertEqual(result, "abroad_330_day_physical_presence")

    def test_330_day_branch_under_threshold_falls_back_to_domestic(self) -> None:
        # 329 days is one short of the § 911(d)(1)(B) statutory floor;
        # without bona-fide residence the result is "domestic".
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {
                "primary_tax_residence": "",
                "us_citizen_or_long_term_resident": True,
                "days_outside_us_during_year": 329,
            }
        )
        self.assertEqual(result, "domestic")

    def test_missing_day_count_falls_back_to_domestic_when_no_bona_fide(self) -> None:
        # No primary_tax_residence and no day-count fact → domestic.
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {"us_citizen_or_long_term_resident": True}
        )
        self.assertEqual(result, "domestic")

    def test_non_us_citizen_never_qualifies_for_abroad_tier(self) -> None:
        # Reg. § 1.6038D applies only to U.S. persons; a non-citizen
        # with no primary_tax_residence and 365 days outside the U.S.
        # still maps to "domestic" because Form 8938's abroad tier
        # under § 911(d)(1) requires U.S. citizenship / long-term
        # residency.
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {
                "primary_tax_residence": "",
                "us_citizen_or_long_term_resident": False,
                "days_outside_us_during_year": 365,
            }
        )
        self.assertEqual(result, "domestic")

    def test_taxpayer_nested_day_count_is_recognized(self) -> None:
        # The fact may live under taxpayer.days_outside_us_during_year
        # (matching the existing taxpayer.* nesting in profile.json).
        from tax_pipeline.y2025.us_inputs import _profile_residency_basis_for_fatca

        result = _profile_residency_basis_for_fatca(
            {
                "us_citizen_or_long_term_resident": True,
                "taxpayer": {"days_outside_us_during_year": 365},
            }
        )
        self.assertEqual(result, "abroad_330_day_physical_presence")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
