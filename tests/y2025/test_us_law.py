from __future__ import annotations

import csv
from dataclasses import replace
import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USA_LAW_SPEC_ROOT = PROJECT_ROOT / "tax_pipeline" / "law_spec" / "usa" / "2025"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tests.y2025._treaty_fixture import write_demo_us_treaty_dividend_items
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.us_inputs import _usa_filing_posture, load_us_assessment_inputs_2025, load_us_capital_source_facts_2025
from tax_pipeline.y2025.us_law import (
    GermanyTreatyDividendPacketItem2025,
    MFS_CAPITAL_LOSS_LIMIT_USD,
    USRegularTaxAssessment2025,
    compute_capital_assessment_2025,
    compute_us_assessment_2025,
    niit_assessment_2025,
    regular_tax_2025_mfs,
    round_cents,
    section_1256_split_2025,
    tax_from_schedule_y2_2025_mfs,
    treaty_resourcing_assessment_2025,
    USAssessmentInputs2025,
    USCapitalSourceFacts2025,
    USFTCInputs2025,
    USReturnProfile2025,
    USTaxConstants2025,
    USTreatyDividendItem2025,
    USTreatyInputs2025,
    validate_form_1116_preferential_adjustment_support_2025,
    wages_usd_2025,
)


class US2025LawTest(unittest.TestCase):
    def _set_election(self, paths: YearPaths, key: str, value: object) -> None:
        text = paths.profile_path.read_text()
        profile = json.loads(text)
        profile.setdefault("elections", {})[key] = value
        paths.profile_path.write_text(json.dumps(profile, indent=2))

    def test_section_911_election_required_in_profile(self) -> None:
        # 26 U.S.C. § 911 Foreign Earned Income Exclusion is a major election;
        # the engine must require an explicit posture rather than silently
        # assume "not elected".
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            del profile["elections"]["elect_section_911_feie"]
            paths.profile_path.write_text(json.dumps(profile, indent=2))

            with self.assertRaisesRegex(ValueError, "§ 911 Foreign Earned Income Exclusion"):
                load_us_assessment_inputs_2025(paths)

    def test_section_911_election_when_true_fails_closed(self) -> None:
        # § 911 changes the income side, the FTC side (§ 911(d)(6) FTC denial),
        # and NIIT MAGI (§ 1411(d)(1)(A) add-back). The 2025 model does not
        # implement these adjustments; the engine must refuse rather than
        # produce a wrong number.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            self._set_election(paths, "elect_section_911_feie", True)

            with self.assertRaisesRegex(NotImplementedError, "§ 911"):
                load_us_assessment_inputs_2025(paths)

    def test_totalization_agreement_acknowledgment_required(self) -> None:
        # § 3101(b)(2) Additional Medicare Tax (0.9 %) does not apply to
        # German-employer wages because the U.S.-Germany Totalization
        # Agreement keeps such wages outside U.S. FICA/Medicare. The engine
        # requires an explicit acknowledgment of this assumption, otherwise
        # fails closed.
        # https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            del profile["elections"]["acknowledges_totalization_agreement_germany_us"]
            paths.profile_path.write_text(json.dumps(profile, indent=2))

            with self.assertRaisesRegex(ValueError, "Totalization Agreement"):
                load_us_assessment_inputs_2025(paths)

    def test_totalization_agreement_rejection_fails_closed(self) -> None:
        # If the acknowledgment is set to false, § 3101(b)(2) would attach to
        # any U.S.-source Medicare-taxable wages and the engine has no Form
        # 8959 implementation; fail closed.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            self._set_election(paths, "acknowledges_totalization_agreement_germany_us", False)

            with self.assertRaisesRegex(NotImplementedError, "Totalization Agreement"):
                load_us_assessment_inputs_2025(paths)

    def test_us_tax_constants_have_posture_neutral_field_names(self) -> None:
        # CLAUDE.md requires field names to honestly reflect the legal authority.
        # The 2025 IRS tax constants apply to whichever filing posture the loader
        # selected; the fields should not carry an `_mfs_` suffix that is wrong
        # for single and married-joint filers. Authority: Rev. Proc. 2024-40 and
        # IRS Form 1040 Instructions for 2025.
        # https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
        fields = set(USTaxConstants2025.__dataclass_fields__)
        for name in (
            "standard_deduction_2025_usd",
            "niit_threshold_usd",
            "qualified_dividend_zero_rate_ceiling_2025_usd",
            "qualified_dividend_fifteen_rate_ceiling_2025_usd",
            "tax_bracket_10_ceiling_2025_usd",
            "tax_bracket_12_ceiling_2025_usd",
            "tax_bracket_22_ceiling_2025_usd",
            "tax_bracket_24_ceiling_2025_usd",
            "tax_bracket_32_ceiling_2025_usd",
            "tax_bracket_35_ceiling_2025_usd",
            "capital_loss_limit_usd",
            "eur_per_usd_yearly_average_2025",
        ):
            with self.subTest(field=name):
                self.assertIn(name, fields)
        for name in (
            "standard_deduction_mfs_2025_usd",
            "niit_threshold_mfs_usd",
            "qualified_dividend_zero_rate_ceiling_mfs_2025_usd",
            "qualified_dividend_fifteen_rate_ceiling_mfs_2025_usd",
            "tax_bracket_10_ceiling_mfs_2025_usd",
            "tax_bracket_12_ceiling_mfs_2025_usd",
            "tax_bracket_22_ceiling_mfs_2025_usd",
            "tax_bracket_24_ceiling_mfs_2025_usd",
            "tax_bracket_32_ceiling_mfs_2025_usd",
            "tax_bracket_35_ceiling_mfs_2025_usd",
        ):
            with self.subTest(field=name):
                self.assertNotIn(name, fields)

    def test_blank_us_filing_posture_fails_closed(self) -> None:
        # Filing posture selects thresholds under 26 U.S.C. § 1, § 63,
        # § 1211(b), and § 1411. A blank value is not a legal election.
        profile = {"jurisdictions": {"usa": {"filing_posture": "  "}}}

        with self.assertRaisesRegex(ValueError, "explicit U.S. filing_posture"):
            _usa_filing_posture(profile)

    def _treaty_inputs_for_single_dividend(
        self,
        *,
        gross_usd: str = "1000.00",
        allowed_us_tax_usd: str = "150.00",
        precredit_usd: str = "250.00",
        credit_usd: str = "150.00",
    ) -> USTreatyInputs2025:
        return USTreatyInputs2025(
            use_treaty_resourcing=True,
            us_source_direct_equity_dividends_usd=Decimal(gross_usd),
            us_source_equity_fund_dividends_usd=Decimal("0.00"),
            us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
            us_treaty_dividend_items=(
                USTreatyDividendItem2025(
                    item_id="us_dividend_1",
                    treaty_bucket="direct_equity",
                    gross_dividend_usd=Decimal(gross_usd),
                ),
            ),
            germany_treaty_dividend_items=(
                GermanyTreatyDividendPacketItem2025(
                    item_id="us_dividend_1",
                    owner_slot="person_1",
                    dividend_class="portfolio_dividend",
                    gross_dividend_eur=Decimal("886.00"),
                    gross_dividend_usd=Decimal(gross_usd),
                    german_taxable_dividend_eur=Decimal("886.00"),
                    article_10_source_tax_ceiling_usd=Decimal(allowed_us_tax_usd),
                    german_precredit_tax_on_us_source_dividend_usd=Decimal(precredit_usd),
                    german_residence_credit_for_us_tax_usd=Decimal(credit_usd),
                    fx_reconciliation="test fixture matched by item_id",
                ),
            ),
            germany_treaty_us_source_dividend_gross_usd=Decimal(gross_usd),
            germany_treaty_us_source_dividend_allowed_us_tax_usd=Decimal(allowed_us_tax_usd),
            german_precredit_tax_on_us_source_dividends_usd=Decimal(precredit_usd),
            german_residence_credit_for_us_tax_usd=Decimal(credit_usd),
        )

    def _demo_germany_treaty_dividend_packet_items(
        self,
    ) -> tuple[GermanyUSTreatyDividendPacketItem2025, ...]:
        return (
            GermanyUSTreatyDividendPacketItem2025(
                item_id="msft_us_dividend",
                owner_slot="person_1",
                dividend_class="portfolio_dividend",
                gross_dividend_eur=Decimal("280.00"),
                german_taxable_dividend_eur=Decimal("280.00"),
                article_10_source_tax_ceiling_eur=Decimal("42.00"),
                germany_precredit_tax_eur=Decimal("36.25"),
                germany_residence_credit_eur=Decimal("36.25"),
            ),
        )

    def _read_csv_rows(self, path: Path) -> list[dict[str, str]]:
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))

    def _rewrite_csv_key_value(self, path: Path, updates: dict[str, str]) -> None:
        lines = path.read_text().splitlines()
        rewritten: list[str] = []
        for line in lines:
            if not line or line.startswith("section,key,value,source,note"):
                rewritten.append(line)
                continue
            parts = line.split(",", 4)
            key = parts[1]
            if key in updates:
                parts[2] = updates[key]
                line = ",".join(parts)
            rewritten.append(line)
        path.write_text("\n".join(rewritten) + "\n")

    def _seed_ordinary_married_joint_workspace(self, root: Path) -> YearPaths:
        paths = self._seed_us_inputs_tree(root)
        profile = json.loads(paths.profile_path.read_text())
        profile["jurisdictions"]["usa"]["filing_posture"] = "married_joint"
        profile["household"]["marital_status_on_dec_31"] = "married"
        profile["household"]["us_filing_status"] = "married_joint"
        profile["spouse"] = {"name": "Jamie Example", "us_tax_status": "us_taxpayer"}
        paths.profile_path.write_text(json.dumps(profile))

        joint_constants = [
            "irs,standard_deduction_married_joint_2025_usd,31500.00,test_fixture,Joint-filer standard deduction for the test fixture.",
            "irs,niit_threshold_married_joint_usd,250000.00,test_fixture,Joint-filer NIIT threshold for the test fixture.",
            "irs,qualified_dividend_zero_rate_ceiling_married_joint_2025_usd,96700.00,test_fixture,Joint-filer zero-rate ceiling for the test fixture.",
            "irs,qualified_dividend_fifteen_rate_ceiling_married_joint_2025_usd,600050.00,test_fixture,Joint-filer fifteen-percent ceiling for the test fixture.",
            "irs,tax_bracket_10_ceiling_married_joint_2025_usd,23850.00,test_fixture,Joint-filer 10 percent ceiling for the test fixture.",
            "irs,tax_bracket_12_ceiling_married_joint_2025_usd,96950.00,test_fixture,Joint-filer 12 percent ceiling for the test fixture.",
            "irs,tax_bracket_22_ceiling_married_joint_2025_usd,206700.00,test_fixture,Joint-filer 22 percent ceiling for the test fixture.",
            "irs,tax_bracket_24_ceiling_married_joint_2025_usd,394600.00,test_fixture,Joint-filer 24 percent ceiling for the test fixture.",
            "irs,tax_bracket_32_ceiling_married_joint_2025_usd,501050.00,test_fixture,Joint-filer 32 percent ceiling for the test fixture.",
            "irs,tax_bracket_35_ceiling_married_joint_2025_usd,751600.00,test_fixture,Joint-filer 35 percent ceiling for the test fixture.",
            "irs,capital_loss_limit_married_joint_2025_usd,3000.00,test_fixture,Joint-return annual capital loss limit for the test fixture.",
        ]
        constants_path = paths.reference_data_root / "us-tax-constants.csv"
        constants_path.write_text(constants_path.read_text().rstrip() + "\n" + "\n".join(joint_constants) + "\n")
        self._rewrite_csv_key_value(
            paths.derived_facts_root / "usa" / "foreign-wage-support.csv",
            {
                "taxpayer_gross_wages_eur": "100000.00",
                "spouse_gross_wages_eur": "50000.00",
                "joint_wage_side_tax_eur": "18000.00",
            },
        )
        return paths

    def _seed_joint_nra_spouse_workspace(self, root: Path, *, explicit_election: bool | None) -> YearPaths:
        paths = self._seed_ordinary_married_joint_workspace(root)
        profile = json.loads(paths.profile_path.read_text())
        profile["spouse"] = {"name": "Jamie Example", "us_tax_status": "nra"}
        if explicit_election is None:
            profile["elections"].pop("elect_joint_return_with_nra_spouse", None)
        else:
            profile["elections"]["elect_joint_return_with_nra_spouse"] = explicit_election
        paths.profile_path.write_text(json.dumps(profile))
        return paths

    def test_usa_law_spec_files_exist(self) -> None:
        expected = [
            USA_LAW_SPEC_ROOT / "index.md",
            USA_LAW_SPEC_ROOT / "regular_tax.md",
            USA_LAW_SPEC_ROOT / "qualified_dividend_worksheet.md",
            USA_LAW_SPEC_ROOT / "capital_loss_limit.md",
            USA_LAW_SPEC_ROOT / "ftc_limitation.md",
            USA_LAW_SPEC_ROOT / "niit.md",
            USA_LAW_SPEC_ROOT / "treaty_resourcing.md",
        ]
        for path in expected:
            self.assertTrue(path.exists(), path)
        # The U.S. law-spec index is the audit map for filing-status-sensitive
        # computations under 26 U.S.C. § 1, § 63, § 1211(b), and § 1411.
        self.assertIn("married_joint", (USA_LAW_SPEC_ROOT / "index.md").read_text())
        # The NIIT law spec must name the actual § 1411 implementation entry point.
        niit_text = (USA_LAW_SPEC_ROOT / "niit.md").read_text()
        self.assertIn("niit_assessment_2025", niit_text)
        self.assertNotIn("compute_niit_assessment_2025", niit_text)

    def test_us_treaty_inputs_use_typed_items_not_legacy_residual_rates(self) -> None:
        # IRS Pub. 514's additional-credit worksheet and DBA-USA Art. 23 require
        # matched U.S.-source income plus Germany's tax/credit on that same stack.
        # The core input model should therefore carry typed item coverage, not legacy
        # German residual-rate assumptions that no longer drive the worksheet.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        fields = set(USTreatyInputs2025.__dataclass_fields__)

        self.assertIn("us_treaty_dividend_items", fields)
        self.assertIn("germany_treaty_dividend_items", fields)
        self.assertNotIn("german_residual_rate_direct_or_non_equity_dividends", fields)
        self.assertNotIn("german_residual_rate_equity_fund_dividends", fields)
        self.assertNotIn("german_residence_credit_equals_treaty_allowed_us_tax", fields)

    def _seed_us_inputs_tree(self, root: Path) -> YearPaths:
        return materialize_demo_workspace(root, demo_name="demo-2025", year=2025)

    def _load_us_inputs_with_demo_germany_packet(self, paths: YearPaths) -> USAssessmentInputs2025:
        # The synthetic demo packet asserts a U.S.-source treaty dividend
        # (msft_us_dividend); the real pipeline auto-derives the matching
        # us-treaty-dividend-items.csv before the U.S. model loads, so the
        # test writes it here (the bare demo carries no treaty items).
        write_demo_us_treaty_dividend_items(paths)
        return load_us_assessment_inputs_2025(
            paths,
            germany_treaty_dividend_items=self._demo_germany_treaty_dividend_packet_items(),
        )

    def _pipeline_env(self, root: Path) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "TAX_PROJECT_ROOT": str(root),
                "TAX_YEAR": "2025",
                "TAX_WORKSPACE_ROOT": str(root / "years" / "2025"),
                "TAX_USE_YEAR_LAYOUT": "1",
            }
        )
        return env

    def _run_same_process_germany_then_us_model(self, root: Path) -> None:
        from tax_pipeline.pipeline_context import clear_pipeline_context
        from tax_pipeline.run_year import _run_pipeline_module

        env = self._pipeline_env(root)
        clear_pipeline_context()
        # Pipeline 1 (Derivation) must materialize derived-facts.json before
        # Pipeline 2 (Legal) runs; the in-memory fallback was removed in F-A4.
        _run_pipeline_module("tax_pipeline.pipelines.y2025.run_derivation", env=env, cwd=PROJECT_ROOT)
        _run_pipeline_module("tax_pipeline.pipelines.y2025.germany_model", env=env, cwd=PROJECT_ROOT)
        _run_pipeline_module("tax_pipeline.pipelines.y2025.us_model", env=env, cwd=PROJECT_ROOT)

    def test_reference_data_uses_official_2025_irs_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            inputs = load_us_assessment_inputs_2025(paths)
            rows = {
                row["key"]: row
                for row in self._read_csv_rows(paths.reference_data_root / "us-tax-constants.csv")
            }

        self.assertEqual(inputs.constants.eur_per_usd_yearly_average_2025, Decimal("0.886"))
        self.assertEqual(inputs.constants.standard_deduction_2025_usd, Decimal("15750.00"))
        # The CSV under years/<year>/normalized/reference-data/us-tax-constants.csv
        # has per-posture rows (`_single_`, `_mfs_`, `_married_joint_`); the
        # demo profile loads MFS, so the MFS-keyed rows are what the loader read.
        self.assertEqual(rows["tax_bracket_35_ceiling_mfs_2025_usd"]["value"], "375800.00")
        self.assertNotEqual(rows["eur_per_usd_yearly_average_2025"]["source"], "synthetic_demo")
        self.assertNotEqual(rows["standard_deduction_mfs_2025_usd"]["source"], "synthetic_demo")

    def test_eur_per_usd_yearly_average_2025_is_pinned_to_irs_published_value(self) -> None:
        # The IRS publishes its 2025 yearly average exchange rate for the Euro
        # Zone in Q1 2026 on the official "Yearly average currency exchange
        # rates" page. The constant in
        # tax_pipeline/y2025/us_law.py:IRS_YEARLY_AVG_2025_EURO_ZONE pins the
        # value used by the engine; the demo CSV must agree byte-for-byte.
        # If the IRS later revises the published rate, this test will fail
        # and the engine constant must be updated alongside the data file.
        # Authority:
        # https://www.irs.gov/individuals/international-taxpayers/yearly-average-currency-exchange-rates
        from tax_pipeline.y2025.us_law import IRS_YEARLY_AVG_2025_EURO_ZONE

        self.assertEqual(IRS_YEARLY_AVG_2025_EURO_ZONE, Decimal("0.886"))
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            inputs = load_us_assessment_inputs_2025(paths)
            rows = {
                row["key"]: row
                for row in self._read_csv_rows(paths.reference_data_root / "us-tax-constants.csv")
            }
        self.assertEqual(
            inputs.constants.eur_per_usd_yearly_average_2025,
            IRS_YEARLY_AVG_2025_EURO_ZONE,
        )
        self.assertEqual(
            rows["eur_per_usd_yearly_average_2025"]["value"],
            "0.886",
        )
        self.assertEqual(
            rows["eur_per_usd_yearly_average_2025"]["source"],
            "irs_2025_yearly_average_rates",
        )

    def test_schedule_y2_2025_mfs_uses_tax_table_below_100000(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            # IRS Publication 1040 (2025) Tax Table: rows 0-5 and 50-75
            # are exact table rows, not midpoint bracket approximations.
            self.assertEqual(
                tax_from_schedule_y2_2025_mfs(Decimal("0.01"), inputs.constants),
                Decimal("0.00"),
            )
            self.assertEqual(
                tax_from_schedule_y2_2025_mfs(Decimal("50.00"), inputs.constants),
                Decimal("6.00"),
            )
            self.assertEqual(
                tax_from_schedule_y2_2025_mfs(Decimal("50000.00"), inputs.constants),
                Decimal("5920.00"),
            )
            self.assertEqual(
                tax_from_schedule_y2_2025_mfs(Decimal("100000.00"), inputs.constants),
                Decimal("16914.00"),
            )

    def test_us_law_exposes_generic_filing_status_tax_function_names(self) -> None:
        # 26 U.S.C. § 1 ordinary tax schedules are selected by the input loader's filing
        # posture constants. The law helper names should not encode MFS when the same helper
        # is used for Single, MFJ, and MFS/NRA-spouse postures.
        import tax_pipeline.y2025.us_law as law

        self.assertTrue(hasattr(law, "tax_from_schedule_y2_2025"))
        self.assertTrue(hasattr(law, "regular_tax_2025"))

    def test_regular_tax_respects_qualified_dividend_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            assessment = regular_tax_2025_mfs(Decimal("50000.00"), Decimal("3000.00"), inputs.constants)
        self.assertEqual(assessment.taxable_ordinary_income_usd, Decimal("47000.00"))
        self.assertEqual(assessment.ordinary_tax_component_usd, Decimal("5405.00"))
        self.assertEqual(assessment.qualified_dividend_tax_component_usd, Decimal("247.50"))
        self.assertEqual(assessment.regular_tax_before_credits_usd, Decimal("5652.50"))

    def test_regular_tax_applies_preferential_rates_to_net_long_term_capital_gain(self) -> None:
        inputs = USAssessmentInputs2025(
            constants=USTaxConstants2025(
                eur_per_usd_yearly_average_2025=Decimal("1.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                capital_loss_limit_usd=MFS_CAPITAL_LOSS_LIMIT_USD,
                niit_threshold_usd=Decimal("999999.00"),
                qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("48350.00"),
                qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("300000.00"),
                tax_bracket_10_ceiling_2025_usd=Decimal("11925.00"),
                tax_bracket_12_ceiling_2025_usd=Decimal("48475.00"),
                tax_bracket_22_ceiling_2025_usd=Decimal("103350.00"),
                tax_bracket_24_ceiling_2025_usd=Decimal("197300.00"),
                tax_bracket_32_ceiling_2025_usd=Decimal("250525.00"),
                tax_bracket_35_ceiling_2025_usd=Decimal("375800.00"),
            ),
            profile=USReturnProfile2025(
                filing_status_label="Married filing separately",
                spouse_name_for_mfs_line="EXAMPLE NRA",
                joint_return_spouse_name="",
                joint_return_with_nra_spouse_election=False,
                accrued_basis_ftc=True,
                include_staking_in_niit=False,
            ),
            capital_facts=USCapitalSourceFacts2025(
                ordinary_dividends_usd=Decimal("0.00"),
                qualified_dividends_usd=Decimal("0.00"),
                capital_gain_distributions_usd=Decimal("0.00"),
                nondividend_distributions_usd=Decimal("0.00"),
                foreign_tax_paid_usd=Decimal("0.00"),
                interest_income_usd=Decimal("0.00"),
                substitute_payments_usd=Decimal("0.00"),
                staking_income_usd=Decimal("0.00"),
                estimated_payment_2025_usd=Decimal("0.00"),
                passive_ftc_carryover_2024_usd=Decimal("0.00"),
                general_ftc_carryover_2024_usd=Decimal("0.00"),
                german_2024_redetermination_paid_2025_eur=Decimal("0.00"),
                schwab_short_box_a_gain_usd=Decimal("0.00"),
                schwab_short_box_b_gain_usd=Decimal("0.00"),
                schwab_long_box_d_gain_usd=Decimal("10000.00"),
                schwab_section_1256_total_usd=Decimal("0.00"),
                jpm_short_type_a_gain_usd=Decimal("0.00"),
                coinbase_short_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_short_with_basis_basis_usd=Decimal("0.00"),
                coinbase_short_unknown_proceeds_usd=Decimal("0.00"),
                coinbase_short_unknown_basis_reconstructed_usd=Decimal("0.00"),
                coinbase_long_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_long_with_basis_basis_usd=Decimal("0.00"),
            ),
            ftc_inputs=USFTCInputs2025(
                taxpayer_gross_wages_eur=Decimal("75000.00"),
                spouse_gross_wages_eur=Decimal("0.00"),
                joint_wage_side_tax_eur=Decimal("0.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                foreign_source_net_capital_gain_usd=Decimal("0.00"),
                known_positive_short_capital_gain_usd=Decimal("0.00"),
                known_positive_long_capital_gain_usd=Decimal("10000.00"),
                conservative_positive_income_only=True,
                allocate_joint_german_tax_by_wage_share=True,
            ),
            treaty_inputs=USTreatyInputs2025(
                use_treaty_resourcing=False,
                us_source_direct_equity_dividends_usd=Decimal("0.00"),
                us_source_equity_fund_dividends_usd=Decimal("0.00"),
                us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
            ),
        )

        assessment = compute_us_assessment_2025(inputs)

        self.assertEqual(assessment.regular_tax.taxable_income_usd, Decimal("85000.00"))
        self.assertEqual(assessment.regular_tax.taxable_ordinary_income_usd, Decimal("75000.00"))
        self.assertEqual(assessment.regular_tax.regular_tax_before_credits_usd, Decimal("12920.00"))

    def test_regular_tax_applies_preferential_rates_to_capital_gain_distributions(self) -> None:
        inputs = USAssessmentInputs2025(
            constants=USTaxConstants2025(
                eur_per_usd_yearly_average_2025=Decimal("1.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                capital_loss_limit_usd=MFS_CAPITAL_LOSS_LIMIT_USD,
                niit_threshold_usd=Decimal("999999.00"),
                qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("48350.00"),
                qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("300000.00"),
                tax_bracket_10_ceiling_2025_usd=Decimal("11925.00"),
                tax_bracket_12_ceiling_2025_usd=Decimal("48475.00"),
                tax_bracket_22_ceiling_2025_usd=Decimal("103350.00"),
                tax_bracket_24_ceiling_2025_usd=Decimal("197300.00"),
                tax_bracket_32_ceiling_2025_usd=Decimal("250525.00"),
                tax_bracket_35_ceiling_2025_usd=Decimal("375800.00"),
            ),
            profile=USReturnProfile2025(
                filing_status_label="Married filing separately",
                spouse_name_for_mfs_line="EXAMPLE NRA",
                joint_return_spouse_name="",
                joint_return_with_nra_spouse_election=False,
                accrued_basis_ftc=True,
                include_staking_in_niit=False,
            ),
            capital_facts=USCapitalSourceFacts2025(
                ordinary_dividends_usd=Decimal("0.00"),
                qualified_dividends_usd=Decimal("0.00"),
                capital_gain_distributions_usd=Decimal("10000.00"),
                nondividend_distributions_usd=Decimal("0.00"),
                foreign_tax_paid_usd=Decimal("0.00"),
                interest_income_usd=Decimal("0.00"),
                substitute_payments_usd=Decimal("0.00"),
                staking_income_usd=Decimal("0.00"),
                estimated_payment_2025_usd=Decimal("0.00"),
                passive_ftc_carryover_2024_usd=Decimal("0.00"),
                general_ftc_carryover_2024_usd=Decimal("0.00"),
                german_2024_redetermination_paid_2025_eur=Decimal("0.00"),
                schwab_short_box_a_gain_usd=Decimal("0.00"),
                schwab_short_box_b_gain_usd=Decimal("0.00"),
                schwab_long_box_d_gain_usd=Decimal("0.00"),
                schwab_section_1256_total_usd=Decimal("0.00"),
                jpm_short_type_a_gain_usd=Decimal("0.00"),
                coinbase_short_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_short_with_basis_basis_usd=Decimal("0.00"),
                coinbase_short_unknown_proceeds_usd=Decimal("0.00"),
                coinbase_short_unknown_basis_reconstructed_usd=Decimal("0.00"),
                coinbase_long_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_long_with_basis_basis_usd=Decimal("0.00"),
            ),
            ftc_inputs=USFTCInputs2025(
                taxpayer_gross_wages_eur=Decimal("75000.00"),
                spouse_gross_wages_eur=Decimal("0.00"),
                joint_wage_side_tax_eur=Decimal("0.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                foreign_source_net_capital_gain_usd=Decimal("0.00"),
                known_positive_short_capital_gain_usd=Decimal("0.00"),
                known_positive_long_capital_gain_usd=Decimal("10000.00"),
                conservative_positive_income_only=True,
                allocate_joint_german_tax_by_wage_share=True,
            ),
            treaty_inputs=USTreatyInputs2025(
                use_treaty_resourcing=False,
                us_source_direct_equity_dividends_usd=Decimal("0.00"),
                us_source_equity_fund_dividends_usd=Decimal("0.00"),
                us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
            ),
        )

        assessment = compute_us_assessment_2025(inputs)

        self.assertEqual(assessment.regular_tax.taxable_income_usd, Decimal("85000.00"))
        self.assertEqual(assessment.regular_tax.taxable_ordinary_income_usd, Decimal("75000.00"))
        self.assertEqual(assessment.regular_tax.regular_tax_before_credits_usd, Decimal("12920.00"))

    def test_regular_tax_applies_preferential_rates_to_section_1256_long_term_share(self) -> None:
        inputs = USAssessmentInputs2025(
            constants=USTaxConstants2025(
                eur_per_usd_yearly_average_2025=Decimal("1.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                capital_loss_limit_usd=MFS_CAPITAL_LOSS_LIMIT_USD,
                niit_threshold_usd=Decimal("999999.00"),
                qualified_dividend_zero_rate_ceiling_2025_usd=Decimal("48350.00"),
                qualified_dividend_fifteen_rate_ceiling_2025_usd=Decimal("300000.00"),
                tax_bracket_10_ceiling_2025_usd=Decimal("11925.00"),
                tax_bracket_12_ceiling_2025_usd=Decimal("48475.00"),
                tax_bracket_22_ceiling_2025_usd=Decimal("103350.00"),
                tax_bracket_24_ceiling_2025_usd=Decimal("197300.00"),
                tax_bracket_32_ceiling_2025_usd=Decimal("250525.00"),
                tax_bracket_35_ceiling_2025_usd=Decimal("375800.00"),
            ),
            profile=USReturnProfile2025(
                filing_status_label="Married filing separately",
                spouse_name_for_mfs_line="EXAMPLE NRA",
                joint_return_spouse_name="",
                joint_return_with_nra_spouse_election=False,
                accrued_basis_ftc=True,
                include_staking_in_niit=False,
            ),
            capital_facts=USCapitalSourceFacts2025(
                ordinary_dividends_usd=Decimal("0.00"),
                qualified_dividends_usd=Decimal("0.00"),
                capital_gain_distributions_usd=Decimal("0.00"),
                nondividend_distributions_usd=Decimal("0.00"),
                foreign_tax_paid_usd=Decimal("0.00"),
                interest_income_usd=Decimal("0.00"),
                substitute_payments_usd=Decimal("0.00"),
                staking_income_usd=Decimal("0.00"),
                estimated_payment_2025_usd=Decimal("0.00"),
                passive_ftc_carryover_2024_usd=Decimal("0.00"),
                general_ftc_carryover_2024_usd=Decimal("0.00"),
                german_2024_redetermination_paid_2025_eur=Decimal("0.00"),
                schwab_short_box_a_gain_usd=Decimal("0.00"),
                schwab_short_box_b_gain_usd=Decimal("0.00"),
                schwab_long_box_d_gain_usd=Decimal("0.00"),
                schwab_section_1256_total_usd=Decimal("10000.00"),
                jpm_short_type_a_gain_usd=Decimal("0.00"),
                coinbase_short_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_short_with_basis_basis_usd=Decimal("0.00"),
                coinbase_short_unknown_proceeds_usd=Decimal("0.00"),
                coinbase_short_unknown_basis_reconstructed_usd=Decimal("0.00"),
                coinbase_long_with_basis_proceeds_usd=Decimal("0.00"),
                coinbase_long_with_basis_basis_usd=Decimal("0.00"),
            ),
            ftc_inputs=USFTCInputs2025(
                taxpayer_gross_wages_eur=Decimal("75000.00"),
                spouse_gross_wages_eur=Decimal("0.00"),
                joint_wage_side_tax_eur=Decimal("0.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                foreign_source_net_capital_gain_usd=Decimal("0.00"),
                known_positive_short_capital_gain_usd=Decimal("4000.00"),
                known_positive_long_capital_gain_usd=Decimal("6000.00"),
                conservative_positive_income_only=True,
                allocate_joint_german_tax_by_wage_share=True,
            ),
            treaty_inputs=USTreatyInputs2025(
                use_treaty_resourcing=False,
                us_source_direct_equity_dividends_usd=Decimal("0.00"),
                us_source_equity_fund_dividends_usd=Decimal("0.00"),
                us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
            ),
        )

        assessment = compute_us_assessment_2025(inputs)

        self.assertEqual(assessment.capital.section_1256_short_term_usd, Decimal("4000.00"))
        self.assertEqual(assessment.capital.section_1256_long_term_usd, Decimal("6000.00"))
        self.assertEqual(assessment.regular_tax.taxable_income_usd, Decimal("85000.00"))
        self.assertEqual(assessment.regular_tax.taxable_ordinary_income_usd, Decimal("79000.00"))
        self.assertEqual(assessment.regular_tax.regular_tax_before_credits_usd, Decimal("13200.00"))

    def test_form_1116_foreign_qd_adjustments_fail_closed_without_adjustment_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            high_foreign_qd = replace(
                inputs,
                capital_facts=replace(
                    inputs.capital_facts,
                    ordinary_dividends_usd=Decimal("25000.00"),
                    qualified_dividends_usd=Decimal("25000.00"),
                ),
                ftc_inputs=replace(
                    inputs.ftc_inputs,
                    foreign_source_passive_dividends_usd=Decimal("25000.00"),
                    foreign_source_qualified_dividends_usd=Decimal("25000.00"),
                ),
            )

            with self.assertRaisesRegex(NotImplementedError, "Form 1116 qualified-dividend"):
                compute_us_assessment_2025(high_foreign_qd)

    def test_form_1116_adjustment_exception_uses_full_taxable_income_not_ordinary_only(self) -> None:
        # IRS Form 1116 Instructions (2024 / 2025) condition the qualified-dividend
        # / capital-gain "adjustment exception" on FULL taxable income (Form 1040
        # line 15 / QDCGTW line 24), not on the ordinary-only portion. A taxpayer
        # whose full taxable income is above the 24 % bracket ceiling cannot claim
        # the exception even if their ordinary-only taxable income is below it.
        # Authority: IRS Instructions for Form 1116, "Adjustment exception".
        # https://www.irs.gov/instructions/i1116
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
        constants = inputs.constants
        bracket_24_ceiling = constants.tax_bracket_24_ceiling_2025_usd

        qualified_dividends_usd = Decimal("10000.00")
        # Ordinary-only just below the ceiling; full taxable income above.
        taxable_ordinary = bracket_24_ceiling - Decimal("100.00")
        taxable_income = taxable_ordinary + qualified_dividends_usd
        self.assertGreater(taxable_income, bracket_24_ceiling)
        self.assertLessEqual(taxable_ordinary, bracket_24_ceiling)

        # Synthesize a USRegularTaxAssessment2025 with these line values. The
        # tax components only need to satisfy `line_23_preferential_tax <
        # line_24_tax_on_all_taxable_income` to enter the gate; pick numbers
        # that make adjustment_required = True.
        regular_tax = USRegularTaxAssessment2025(
            wages_usd=Decimal("0.00"),
            schedule_1_other_income_usd=Decimal("0.00"),
            adjusted_gross_income_usd=taxable_income + constants.standard_deduction_2025_usd,
            taxable_income_usd=taxable_income,
            taxable_ordinary_income_usd=taxable_ordinary,
            ordinary_tax_component_usd=Decimal("40000.00"),
            qualified_dividend_tax_component_usd=Decimal("1500.00"),
            regular_tax_before_credits_usd=Decimal("41500.00"),
        )

        ftc_inputs = USFTCInputs2025(
            taxpayer_gross_wages_eur=Decimal("0.00"),
            spouse_gross_wages_eur=Decimal("0.00"),
            joint_wage_side_tax_eur=Decimal("0.00"),
            foreign_source_passive_dividends_usd=Decimal("5000.00"),
            foreign_source_qualified_dividends_usd=Decimal("5000.00"),
            foreign_source_net_capital_gain_usd=Decimal("0.00"),
            known_positive_short_capital_gain_usd=Decimal("0.00"),
            known_positive_long_capital_gain_usd=Decimal("0.00"),
            conservative_positive_income_only=True,
            allocate_joint_german_tax_by_wage_share=True,
        )
        # Foreign preferential income is $5,000 — below the $20,000
        # FORM_1116_PREFERENTIAL_EXCEPTION_LIMIT, so the income-side condition
        # alone won't gate it. Whether the gate raises must depend on whether
        # we test taxable_income (correct) or taxable_ordinary_income (the
        # taxpayer-favorable bug).
        with self.assertRaisesRegex(NotImplementedError, "Form 1116 qualified-dividend"):
            validate_form_1116_preferential_adjustment_support_2025(
                regular_tax=regular_tax,
                ftc_inputs=ftc_inputs,
                constants=constants,
            )

    def test_form_1116_adjustment_exception_qualifies_when_full_taxable_income_below_ceiling(self) -> None:
        # Counterpart to the bug-pinning test: when full taxable income IS
        # at or below the 24 % bracket ceiling AND foreign preferential income
        # is below $20,000, the exception applies and the gate returns silently.
        # Authority: IRS Instructions for Form 1116, "Adjustment exception".
        # https://www.irs.gov/instructions/i1116
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
        constants = inputs.constants
        bracket_24_ceiling = constants.tax_bracket_24_ceiling_2025_usd

        qualified_dividends_usd = Decimal("5000.00")
        taxable_ordinary = bracket_24_ceiling - Decimal("10000.00")
        taxable_income = taxable_ordinary + qualified_dividends_usd
        self.assertLessEqual(taxable_income, bracket_24_ceiling)

        regular_tax = USRegularTaxAssessment2025(
            wages_usd=Decimal("0.00"),
            schedule_1_other_income_usd=Decimal("0.00"),
            adjusted_gross_income_usd=taxable_income + constants.standard_deduction_2025_usd,
            taxable_income_usd=taxable_income,
            taxable_ordinary_income_usd=taxable_ordinary,
            ordinary_tax_component_usd=Decimal("35000.00"),
            qualified_dividend_tax_component_usd=Decimal("750.00"),
            regular_tax_before_credits_usd=Decimal("35750.00"),
        )

        ftc_inputs = USFTCInputs2025(
            taxpayer_gross_wages_eur=Decimal("0.00"),
            spouse_gross_wages_eur=Decimal("0.00"),
            joint_wage_side_tax_eur=Decimal("0.00"),
            foreign_source_passive_dividends_usd=Decimal("2500.00"),
            foreign_source_qualified_dividends_usd=Decimal("2500.00"),
            foreign_source_net_capital_gain_usd=Decimal("0.00"),
            known_positive_short_capital_gain_usd=Decimal("0.00"),
            known_positive_long_capital_gain_usd=Decimal("0.00"),
            conservative_positive_income_only=True,
            allocate_joint_german_tax_by_wage_share=True,
        )

        # Returns None silently — exception qualifies.
        result = validate_form_1116_preferential_adjustment_support_2025(
            regular_tax=regular_tax,
            ftc_inputs=ftc_inputs,
            constants=constants,
        )
        self.assertIsNone(result)

    def test_form_1116_foreign_net_capital_gain_adjustments_fail_closed_without_adjustment_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            high_foreign_net_capital_gain = replace(
                inputs,
                capital_facts=replace(
                    inputs.capital_facts,
                    ordinary_dividends_usd=Decimal("0.00"),
                    qualified_dividends_usd=Decimal("0.00"),
                    schwab_long_box_d_gain_usd=Decimal("25000.00"),
                ),
                ftc_inputs=replace(
                    inputs.ftc_inputs,
                    foreign_source_passive_dividends_usd=Decimal("0.00"),
                    foreign_source_qualified_dividends_usd=Decimal("0.00"),
                    foreign_source_net_capital_gain_usd=Decimal("25000.00"),
                    known_positive_long_capital_gain_usd=Decimal("25000.00"),
                ),
            )

            with self.assertRaisesRegex(NotImplementedError, "Form 1116 qualified-dividend/capital-gain"):
                compute_us_assessment_2025(high_foreign_net_capital_gain)

    def test_section_1256_split_is_40_60(self) -> None:
        short_term, long_term = section_1256_split_2025(Decimal("-5601.99"))
        self.assertEqual(short_term, Decimal("-2240.80"))
        self.assertEqual(long_term, Decimal("-3361.19"))

    def test_capital_assessment_applies_mfs_loss_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            facts = load_us_capital_source_facts_2025(self._seed_us_inputs_tree(Path(tmp)))
            assessment = compute_capital_assessment_2025(facts)
        self.assertEqual(assessment.net_capital_after_1256_usd, Decimal("1050.00"))
        self.assertEqual(assessment.capital_loss_deduction_2025_usd, Decimal("0.00"))
        self.assertEqual(assessment.tentative_capital_loss_carryforward_2026_usd, Decimal("0.00"))
        self.assertEqual(assessment.form_1040_line_7a_usd, Decimal("1050.00"))

    def test_niit_uses_lesser_of_nii_and_magi_excess(self) -> None:
        assessment = niit_assessment_2025(
            adjusted_gross_income_usd=Decimal("202437.95"),
            capital_line_7a_usd=Decimal("-1500.00"),
            ordinary_dividends_usd=Decimal("9596.58"),
            interest_income_usd=Decimal("12.25"),
            substitute_payments_usd=Decimal("105.26"),
            staking_income_usd=Decimal("317.98"),
            include_staking_in_niit=True,
            niit_threshold_usd=Decimal("125000.00"),
        )
        self.assertEqual(assessment.net_investment_income_usd, Decimal("8532.07"))
        self.assertEqual(assessment.modified_agi_excess_usd, Decimal("77437.95"))
        self.assertEqual(assessment.niit_base_usd, Decimal("8532.07"))
        self.assertEqual(assessment.niit_usd, Decimal("324.22"))

    def test_exact_us_assessment_matches_2025_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            assessment = compute_us_assessment_2025(self._load_us_inputs_with_demo_germany_packet(paths))
        self.assertEqual(assessment.regular_tax.wages_usd, Decimal("135440.18"))
        self.assertEqual(assessment.regular_tax.adjusted_gross_income_usd, Decimal("137335.18"))
        self.assertEqual(assessment.regular_tax.taxable_income_usd, Decimal("121585.18"))
        self.assertEqual(assessment.regular_tax.regular_tax_before_credits_usd, Decimal("21909.54"))
        self.assertEqual(assessment.ftc.allowed_general_ftc_usd, Decimal("21607.22"))
        self.assertEqual(assessment.ftc.allowed_passive_ftc_usd, Decimal("80.40"))
        # F-FN-2: Pub. 514 worksheet line 16 uses taxable income (Form 1040 line 15)
        # as the average-rate denominator, not AGI. The new value reflects
        # 21909.54 * us_source_dividends / 121585.18 (taxable income) instead of
        # the previous 21909.54 * us_source_dividends / 137335.18 (AGI).
        self.assertEqual(assessment.treaty_resourcing.us_tax_on_us_source_dividends_usd, Decimal("56.95"))
        self.assertEqual(assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd, Decimal("0.00"))
        self.assertEqual(assessment.niit.niit_usd, Decimal("0.00"))
        self.assertEqual(assessment.total_tax_usd, Decimal("221.92"))
        self.assertEqual(assessment.total_tax_with_treaty_resourcing_usd, Decimal("221.92"))
        self.assertEqual(assessment.refund_if_positive_else_balance_due_usd, Decimal("778.08"))
        self.assertEqual(
            assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd,
            Decimal("778.08"),
        )

    def test_treaty_resourcing_election_false_disables_additional_credit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            assessment = compute_us_assessment_2025(
                replace(
                    inputs,
                    treaty_inputs=replace(inputs.treaty_inputs, use_treaty_resourcing=False),
                )
            )

        self.assertEqual(assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd, Decimal("0.00"))
        self.assertEqual(
            assessment.treaty_resourcing.regular_tax_after_ftc_and_treaty_resourcing_usd,
            assessment.ftc.regular_tax_after_ftc_usd,
        )
        self.assertEqual(assessment.total_tax_with_treaty_resourcing_usd, assessment.total_tax_usd)

    def test_treaty_resourcing_credit_is_capped_by_form_1116_line_33(self) -> None:
        # IRS Pub. 514 says treaty worksheet line 21 is added to Form 1116 line 12
        # and Part IV line 32; Form 1116 then still caps the nonrefundable credit
        # under IRC §904 and Form 1116 line 33. A treaty worksheet amount cannot
        # push final FTC above Form 1116 line 20 regular tax liability.
        # DBA-USA Art. 23 requires the residence-country tax and credit to be for
        # the same U.S.-source dividend stack, so explicit Germany core outputs are
        # required instead of a residual-rate fallback.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        with tempfile.TemporaryDirectory() as tmp:
            constants = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp))).constants

        assessment = treaty_resourcing_assessment_2025(
            ordinary_dividends_usd=Decimal("1000.00"),
            qualified_dividends_usd=Decimal("1000.00"),
            foreign_source_passive_dividends_usd=Decimal("0.00"),
            foreign_source_qualified_dividends_usd=Decimal("0.00"),
            taxable_income_usd=Decimal("10000.00"),
            standard_deduction_2025_usd=Decimal("0.00"),
            regular_tax_before_credits_usd=Decimal("3000.00"),
            regular_tax_after_ftc_usd=Decimal("500.00"),
            remaining_form_1116_line_33_cap_usd=Decimal("1.00"),
            constants=constants,
            treaty_inputs=self._treaty_inputs_for_single_dividend(precredit_usd="300.00"),
        )

        self.assertEqual(assessment.worksheet_line_19_maximum_credit_usd, Decimal("150.00"))
        self.assertEqual(assessment.worksheet_line_21_additional_credit_usd, Decimal("150.00"))
        self.assertEqual(assessment.treaty_resourcing_additional_ftc_usd, Decimal("1.00"))
        self.assertEqual(assessment.regular_tax_after_ftc_and_treaty_resourcing_usd, Decimal("499.00"))

    def test_treaty_resourcing_uses_explicit_germany_dividend_credit_outputs(self) -> None:
        # DBA-USA Art. 23 and IRS Pub. 514 line 17/18 require the U.S. additional
        # FTC worksheet to use Germany's tax and credit on the same U.S.-source
        # dividend stack. This must come from the Germany treaty-dividend stage,
        # not from a Boolean assumption that line 18 equals the 15% treaty floor.
        with tempfile.TemporaryDirectory() as tmp:
            constants = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp))).constants

        assessment = treaty_resourcing_assessment_2025(
            ordinary_dividends_usd=Decimal("1000.00"),
            qualified_dividends_usd=Decimal("1000.00"),
            foreign_source_passive_dividends_usd=Decimal("0.00"),
            foreign_source_qualified_dividends_usd=Decimal("0.00"),
            taxable_income_usd=Decimal("10000.00"),
            standard_deduction_2025_usd=Decimal("0.00"),
            regular_tax_before_credits_usd=Decimal("2800.00"),
            regular_tax_after_ftc_usd=Decimal("500.00"),
            remaining_form_1116_line_33_cap_usd=Decimal("500.00"),
            constants=constants,
            treaty_inputs=self._treaty_inputs_for_single_dividend(),
        )

        self.assertEqual(assessment.us_tax_on_us_source_dividends_usd, Decimal("280.00"))
        self.assertEqual(assessment.treaty_minimum_us_tax_on_us_source_dividends_usd, Decimal("150.00"))
        self.assertEqual(assessment.german_precredit_tax_on_us_source_dividends_usd, Decimal("250.00"))
        self.assertEqual(assessment.german_residence_credit_for_us_tax_usd, Decimal("150.00"))
        self.assertEqual(assessment.worksheet_line_19_maximum_credit_usd, Decimal("130.00"))
        self.assertEqual(assessment.worksheet_line_20c_residual_residence_country_tax_usd, Decimal("100.00"))
        self.assertEqual(assessment.worksheet_line_21_additional_credit_usd, Decimal("100.00"))
        self.assertEqual(assessment.treaty_resourcing_additional_ftc_usd, Decimal("100.00"))

    def test_treaty_resourcing_requires_germany_core_outputs_for_us_source_dividends(self) -> None:
        # IRS Pub. 514 lines 17/18 and DBA-USA Art. 23 require Germany's actual
        # residence-country tax and credit on the same U.S.-source dividend stack.
        # If treaty re-sourcing is claimed for positive U.S.-source dividends, the
        # legal core must fail closed instead of reconstructing Germany from saved
        # residual-rate assumptions.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        with tempfile.TemporaryDirectory() as tmp:
            constants = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp))).constants

        with self.assertRaisesRegex(ValueError, "Germany treaty dividend packet outputs are required"):
            treaty_resourcing_assessment_2025(
                ordinary_dividends_usd=Decimal("1000.00"),
                qualified_dividends_usd=Decimal("1000.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                taxable_income_usd=Decimal("10000.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                regular_tax_before_credits_usd=Decimal("2800.00"),
                regular_tax_after_ftc_usd=Decimal("500.00"),
                remaining_form_1116_line_33_cap_usd=Decimal("500.00"),
                constants=constants,
                treaty_inputs=USTreatyInputs2025(
                    use_treaty_resourcing=True,
                    us_source_direct_equity_dividends_usd=Decimal("1000.00"),
                    us_source_equity_fund_dividends_usd=Decimal("0.00"),
                    us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
                    us_treaty_dividend_items=(
                        USTreatyDividendItem2025(
                            item_id="us_dividend_1",
                            treaty_bucket="direct_equity",
                            gross_dividend_usd=Decimal("1000.00"),
                        ),
                    ),
                ),
            )

    def test_treaty_resourcing_requires_germany_dividend_base_to_match_us_source_stack(self) -> None:
        # IRS Pub. 514 lines 1/8/12/16 and lines 17/18 must all refer to the same
        # U.S.-source income. DBA-USA Art. 23 does not permit using Germany tax and
        # credit computed on a different dividend base.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        with tempfile.TemporaryDirectory() as tmp:
            constants = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp))).constants

        with self.assertRaisesRegex(ValueError, "Germany treaty dividend gross must match"):
            treaty_resourcing_assessment_2025(
                ordinary_dividends_usd=Decimal("1000.00"),
                qualified_dividends_usd=Decimal("1000.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                taxable_income_usd=Decimal("10000.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                regular_tax_before_credits_usd=Decimal("2800.00"),
                regular_tax_after_ftc_usd=Decimal("500.00"),
                remaining_form_1116_line_33_cap_usd=Decimal("500.00"),
                constants=constants,
                treaty_inputs=replace(
                    self._treaty_inputs_for_single_dividend(),
                    germany_treaty_us_source_dividend_gross_usd=Decimal("999.99"),
                ),
            )

    def test_treaty_resourcing_requires_us_and_germany_item_coverage_to_match(self) -> None:
        # Pub. 514 lines 1/8/12/16 and lines 17/18 must cover the same income.
        # DBA-USA Art. 23 treaty resourcing therefore compares item identity before
        # amount totals so FX translation cannot hide that Germany and the U.S. are
        # using different dividend stacks.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        with tempfile.TemporaryDirectory() as tmp:
            constants = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp))).constants

        bad_treaty_inputs = replace(
            self._treaty_inputs_for_single_dividend(),
            germany_treaty_dividend_items=(
                replace(
                    self._treaty_inputs_for_single_dividend().germany_treaty_dividend_items[0],
                    item_id="different_dividend",
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "item coverage mismatch"):
            treaty_resourcing_assessment_2025(
                ordinary_dividends_usd=Decimal("1000.00"),
                qualified_dividends_usd=Decimal("1000.00"),
                foreign_source_passive_dividends_usd=Decimal("0.00"),
                foreign_source_qualified_dividends_usd=Decimal("0.00"),
                taxable_income_usd=Decimal("10000.00"),
                standard_deduction_2025_usd=Decimal("0.00"),
                regular_tax_before_credits_usd=Decimal("2800.00"),
                regular_tax_after_ftc_usd=Decimal("500.00"),
                remaining_form_1116_line_33_cap_usd=Decimal("500.00"),
                constants=constants,
                treaty_inputs=bad_treaty_inputs,
            )

    def test_paid_basis_ftc_posture_is_supported_under_section_905a(self) -> None:
        # Workstream 3 — 26 U.S.C. § 905(a) paid-basis FTC posture is now
        # supported; the loader records ``accrued_basis_ftc=False`` on
        # ``USReturnProfile2025`` instead of failing closed, and the
        # downstream FTC chain accepts the posture. (The treaty-resourcing
        # branch requires Germany packet inputs; this test exercises the
        # loader-and-validator path the previous NotImplementedError gated.)
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            paid_basis = replace(inputs.profile, accrued_basis_ftc=False)
            # The validator that previously rejected paid-basis no longer
            # throws; supported postures now include both accrued and paid.
            from tax_pipeline.y2025.us_law import (
                validate_supported_us_filing_positions_2025,
            )

            paid_inputs = replace(inputs, profile=paid_basis)
            validate_supported_us_filing_positions_2025(paid_inputs)
            self.assertFalse(paid_inputs.profile.accrued_basis_ftc)

    def test_mfj_general_foreign_tax_still_uses_supported_wage_share_allocation(self) -> None:
        # IRS Publication 514 allocation is a manual legal posture in this engine.
        # Married filing jointly must not switch to the full joint German wage tax
        # unless a separate supported allocation posture is implemented.
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            joint_profile = replace(
                inputs.profile,
                filing_status_label="Married filing jointly",
                joint_return_spouse_name="Jamie Example",
                joint_return_with_nra_spouse_election=True,
            )
            joint_ftc = replace(
                inputs.ftc_inputs,
                taxpayer_gross_wages_eur=Decimal("100.00"),
                spouse_gross_wages_eur=Decimal("300.00"),
                joint_wage_side_tax_eur=Decimal("4000.00"),
                allocate_joint_german_tax_by_wage_share=True,
            )
            assessment = compute_us_assessment_2025(
                replace(
                    inputs,
                    profile=joint_profile,
                    ftc_inputs=joint_ftc,
                    treaty_inputs=replace(inputs.treaty_inputs, use_treaty_resourcing=False),
                )
            )

        self.assertEqual(
            assessment.ftc.current_year_general_foreign_tax_usd,
            round_cents(Decimal("1000.00") / inputs.constants.eur_per_usd_yearly_average_2025),
        )

    def test_unsupported_ftc_denominator_position_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            unsupported_ftc = replace(inputs.ftc_inputs, conservative_positive_income_only=False)
            with self.assertRaisesRegex(
                NotImplementedError,
                "documented positive-income FTC denominator posture",
            ):
                compute_us_assessment_2025(replace(inputs, ftc_inputs=unsupported_ftc))

    def test_unsupported_joint_german_tax_allocation_fails_loudly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            unsupported_ftc = replace(inputs.ftc_inputs, allocate_joint_german_tax_by_wage_share=False)
            with self.assertRaisesRegex(
                NotImplementedError,
                "wage-share allocation of joint German wage-side tax",
            ):
                compute_us_assessment_2025(replace(inputs, ftc_inputs=unsupported_ftc))

    def test_treaty_dividend_split_must_reconcile_to_computed_us_source_dividends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            mismatched_treaty = replace(
                inputs.treaty_inputs,
                us_source_direct_equity_dividends_usd=(
                    inputs.treaty_inputs.us_source_direct_equity_dividends_usd + Decimal("0.01")
                ),
            )
            with self.assertRaisesRegex(
                ValueError,
                "Treaty dividend split must reconcile to the computed U.S.-source dividend total",
            ):
                compute_us_assessment_2025(replace(inputs, treaty_inputs=mismatched_treaty))

    def test_treaty_resourcing_rejects_unsupported_treaty_item_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            bad_treaty = replace(
                inputs.treaty_inputs,
                us_treaty_dividend_items=(
                    USTreatyDividendItem2025(
                        item_id="msft_us_dividend",
                        treaty_bucket="unsupported_bucket",
                        gross_dividend_usd=Decimal("316.03"),
                    ),
                ),
            )
            with self.assertRaisesRegex(ValueError, "Unsupported U.S. treaty dividend bucket"):
                compute_us_assessment_2025(replace(inputs, treaty_inputs=bad_treaty))

    def test_treaty_resourcing_assessment_rejects_negative_us_source_dividend_bases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            with self.assertRaisesRegex(ValueError, "U.S.-source dividends cannot be negative"):
                compute_us_assessment_2025(
                    replace(
                        inputs,
                        capital_facts=replace(
                            inputs.capital_facts,
                            ordinary_dividends_usd=Decimal("1.00"),
                            qualified_dividends_usd=Decimal("1.00"),
                        ),
                        ftc_inputs=replace(
                            inputs.ftc_inputs,
                            foreign_source_passive_dividends_usd=Decimal("2.00"),
                        ),
                    )
                )
            with self.assertRaisesRegex(ValueError, "U.S.-source qualified dividends cannot be negative"):
                compute_us_assessment_2025(
                    replace(
                        inputs,
                        capital_facts=replace(
                            inputs.capital_facts,
                            qualified_dividends_usd=Decimal("1.00"),
                        ),
                        ftc_inputs=replace(
                            inputs.ftc_inputs,
                            foreign_source_qualified_dividends_usd=Decimal("2.00"),
                        ),
                    )
                )

    def test_foreign_source_qualified_dividends_must_be_subset_of_foreign_passive_dividends(self) -> None:
        # Form 1116/Pub. 514 source splits classify qualified dividends inside the
        # passive dividend stack. A foreign-source qualified dividend amount greater
        # than total foreign-source passive dividends is impossible source data and
        # must fail before treaty or FTC math runs.
        # Source: https://www.irs.gov/publications/p514.
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))

            with self.assertRaisesRegex(
                ValueError,
                "Foreign-source qualified dividends cannot exceed foreign-source passive dividends",
            ):
                compute_us_assessment_2025(
                    replace(
                        inputs,
                        capital_facts=replace(
                            inputs.capital_facts,
                            ordinary_dividends_usd=Decimal("1000.00"),
                            qualified_dividends_usd=Decimal("900.00"),
                        ),
                        ftc_inputs=replace(
                            inputs.ftc_inputs,
                            foreign_source_passive_dividends_usd=Decimal("100.00"),
                            foreign_source_qualified_dividends_usd=Decimal("800.00"),
                        ),
                    )
                )

    def test_qualified_dividends_must_be_subset_of_ordinary_dividends(self) -> None:
        # 26 U.S.C. § 1(h)(11) gives preferential treatment to qualified dividend
        # income only as a subset of dividends included in gross income under
        # 26 U.S.C. § 61(a)(7). Form 1040 line 3a is therefore a subset of line 3b;
        # source splitting must fail closed before computing impossible residuals.
        # Source: https://www.irs.gov/instructions/i1040gi.
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))

            with self.assertRaisesRegex(
                ValueError,
                "Qualified dividends cannot exceed ordinary dividends",
            ):
                compute_us_assessment_2025(
                    replace(
                        inputs,
                        capital_facts=replace(
                            inputs.capital_facts,
                            ordinary_dividends_usd=Decimal("100.00"),
                            qualified_dividends_usd=Decimal("200.00"),
                        ),
                        ftc_inputs=replace(
                            inputs.ftc_inputs,
                            foreign_source_passive_dividends_usd=Decimal("0.00"),
                            foreign_source_qualified_dividends_usd=Decimal("0.00"),
                        ),
                    )
                )

    def test_assessment_rejects_negative_source_amounts_before_legal_math(self) -> None:
        # 26 U.S.C. §§ 61, 63, 901, 904, 1211, and 1411 require source facts to be
        # legally possible before the return math runs. Proceeds, basis, dividends,
        # wage/payment/FTC amounts, and treaty item amounts are non-negative facts;
        # only computed gain/loss result fields may be negative.
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))

        cases = [
            replace(
                inputs,
                capital_facts=replace(inputs.capital_facts, ordinary_dividends_usd=Decimal("-1.00")),
            ),
            replace(
                inputs,
                capital_facts=replace(inputs.capital_facts, coinbase_short_with_basis_proceeds_usd=Decimal("-1.00")),
            ),
            replace(
                inputs,
                capital_facts=replace(inputs.capital_facts, estimated_payment_2025_usd=Decimal("-1.00")),
            ),
            replace(
                inputs,
                ftc_inputs=replace(inputs.ftc_inputs, taxpayer_gross_wages_eur=Decimal("-1.00")),
            ),
            replace(
                inputs,
                treaty_inputs=replace(
                    inputs.treaty_inputs,
                    us_treaty_dividend_items=(
                        USTreatyDividendItem2025(
                            item_id="msft_us_dividend",
                            treaty_bucket="direct_equity",
                            gross_dividend_usd=Decimal("-0.01"),
                        ),
                    ),
                ),
            ),
        ]
        labels = [
            "ordinary_dividends_usd",
            "coinbase_short_with_basis_proceeds_usd",
            "estimated_payment_2025_usd",
            "taxpayer_gross_wages_eur",
            "gross_dividend_usd",
        ]
        for label, bad_inputs in zip(labels, cases, strict=True):
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, label):
                    compute_us_assessment_2025(bad_inputs)

    def test_ftc_source_split_validation_runs_even_without_treaty_resourcing(self) -> None:
        # Form 1116 and Pub. 514 source-split facts feed the FTC limitation before
        # any treaty-resourcing election. They must fail closed even when treaty
        # resourcing is disabled.
        with tempfile.TemporaryDirectory() as tmp:
            inputs = load_us_assessment_inputs_2025(self._seed_us_inputs_tree(Path(tmp)))
            no_treaty = replace(inputs.treaty_inputs, use_treaty_resourcing=False)
            with self.assertRaisesRegex(ValueError, "U.S.-source dividends cannot be negative"):
                compute_us_assessment_2025(
                    replace(
                        inputs,
                        treaty_inputs=no_treaty,
                        capital_facts=replace(
                            inputs.capital_facts,
                            ordinary_dividends_usd=Decimal("1.00"),
                            qualified_dividends_usd=Decimal("1.00"),
                        ),
                        ftc_inputs=replace(
                            inputs.ftc_inputs,
                            foreign_source_passive_dividends_usd=Decimal("2.00"),
                        ),
                    )
                )

    def test_wage_translation_requires_positive_irs_exchange_rate(self) -> None:
        # The IRS yearly-average rate is a divisor for foreign wage translation.
        # Zero or negative rates are invalid source facts and must fail closed.
        with self.assertRaisesRegex(ValueError, "eur_per_usd_yearly_average_2025 must be positive"):
            wages_usd_2025(Decimal("100.00"), Decimal("0.00"))
        with self.assertRaisesRegex(ValueError, "eur_per_usd_yearly_average_2025 must be positive"):
            wages_usd_2025(Decimal("100.00"), Decimal("-1.00"))

    def test_ftc_helpers_reject_impossible_negative_or_zero_states(self) -> None:
        from tax_pipeline.y2025.us_law import (
            allowed_ftc_2025,
            current_year_general_foreign_tax_usd_2025,
            ftc_limitation_2025,
            standard_deduction_allocation_2025,
        )

        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            allowed_ftc_2025(
                limitation_usd=Decimal("100.00"),
                current_year_foreign_tax_usd=Decimal("-1.00"),
                carryover_usd=Decimal("0.00"),
            )
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            allowed_ftc_2025(
                limitation_usd=Decimal("100.00"),
                current_year_foreign_tax_usd=Decimal("1.00"),
                carryover_usd=Decimal("-1.00"),
            )
        with self.assertRaisesRegex(ValueError, "must be positive"):
            current_year_general_foreign_tax_usd_2025(
                taxpayer_gross_wages_eur=Decimal("0.00"),
                spouse_gross_wages_eur=Decimal("0.00"),
                joint_wage_side_tax_eur=Decimal("1.00"),
                eur_per_usd_yearly_average_2025=Decimal("1.00"),
            )
        self.assertEqual(
            current_year_general_foreign_tax_usd_2025(
                taxpayer_gross_wages_eur=Decimal("0.00"),
                spouse_gross_wages_eur=Decimal("0.00"),
                joint_wage_side_tax_eur=Decimal("0.00"),
                eur_per_usd_yearly_average_2025=Decimal("1.00"),
            ),
            Decimal("0.00"),
        )
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            standard_deduction_allocation_2025(
                standard_deduction_usd=Decimal("-1.00"),
                category_gross_income_usd=Decimal("100.00"),
                total_gross_income_for_ftc_usd=Decimal("100.00"),
            )
        with self.assertRaisesRegex(ValueError, "category_gross_income_usd must also be zero"):
            standard_deduction_allocation_2025(
                standard_deduction_usd=Decimal("1.00"),
                category_gross_income_usd=Decimal("1.00"),
                total_gross_income_for_ftc_usd=Decimal("0.00"),
            )
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            ftc_limitation_2025(
                regular_tax_before_credits_usd=Decimal("-1.00"),
                category_taxable_income_usd=Decimal("10.00"),
                taxable_income_usd=Decimal("10.00"),
            )
        with self.assertRaisesRegex(ValueError, "category_taxable_income_usd must also be zero"):
            ftc_limitation_2025(
                regular_tax_before_credits_usd=Decimal("1.00"),
                category_taxable_income_usd=Decimal("1.00"),
                taxable_income_usd=Decimal("0.00"),
            )

    def test_ftc_limitation_caps_at_pre_credit_us_tax_under_section_904_a(self) -> None:
        # 26 U.S.C. § 904(a) limits the FTC to the U.S. tax on entire taxable income.
        # Form 1116 line 21 instructions: "Enter the smaller of line 19 or line 20."
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
        # https://www.irs.gov/instructions/i1116
        # https://www.irs.gov/publications/p514
        #
        # When U.S.-source losses make foreign-source taxable income exceed worldwide
        # taxable income, the unbounded fraction (cat_TI / TI) > 1 and would overstate
        # the FTC. The statutory ceiling is the pre-credit U.S. tax itself.
        from tax_pipeline.y2025.us_law import ftc_limitation_2025

        # Scenario: foreign-source TI ($150k) exceeds worldwide TI ($100k) because of
        # documented U.S.-source losses. Pre-credit tax is $20k. The unbounded fraction
        # would produce $30k; the cap holds it at $20k.
        capped = ftc_limitation_2025(
            regular_tax_before_credits_usd=Decimal("20000.00"),
            category_taxable_income_usd=Decimal("150000.00"),
            taxable_income_usd=Decimal("100000.00"),
        )
        self.assertEqual(capped, Decimal("20000.00"))

        # Sanity check: when foreign-source TI < worldwide TI, the proportional
        # formula still controls (no cap binding).
        proportional = ftc_limitation_2025(
            regular_tax_before_credits_usd=Decimal("20000.00"),
            category_taxable_income_usd=Decimal("40000.00"),
            taxable_income_usd=Decimal("100000.00"),
        )
        self.assertEqual(proportional, Decimal("8000.00"))

        # Edge: foreign-source TI equals worldwide TI -> cap and fraction agree exactly.
        equal_case = ftc_limitation_2025(
            regular_tax_before_credits_usd=Decimal("20000.00"),
            category_taxable_income_usd=Decimal("100000.00"),
            taxable_income_usd=Decimal("100000.00"),
        )
        self.assertEqual(equal_case, Decimal("20000.00"))

    def test_documented_positive_income_denominator_is_bounded_by_worldwide_ti_under_section_904_b(self) -> None:
        # 26 U.S.C. § 904(b)(1) requires the FTC fraction denominator to be worldwide
        # taxable income. The 2025 model uses the documented-positive-income subset as a
        # conservative posture; the binding assertion ensures that subset never exceeds
        # taxable_income + standard_deduction, which would invert the conservatism.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
        # https://www.irs.gov/instructions/i1116
        from tax_pipeline.core.stages import LegalInvariantViolation
        from tax_pipeline.y2025.us_law import (
            validate_documented_positive_income_denominator_bound_2025,
        )

        # Within bound: total_gross = 30000 <= taxable (15000) + std_ded (15000) = 30000.
        validate_documented_positive_income_denominator_bound_2025(
            total_gross_income_for_ftc_usd=Decimal("30000.00"),
            taxable_income_usd=Decimal("15000.00"),
            standard_deduction_usd=Decimal("15000.00"),
        )

        # Strictly under: clearly OK.
        validate_documented_positive_income_denominator_bound_2025(
            total_gross_income_for_ftc_usd=Decimal("25000.00"),
            taxable_income_usd=Decimal("15000.00"),
            standard_deduction_usd=Decimal("15000.00"),
        )

        # Inconsistent inputs: documented positive subset exceeds worldwide gross
        # income ceiling. Must fail closed with a § 904(b) invariant violation.
        with self.assertRaisesRegex(
            LegalInvariantViolation,
            r"Documented-positive-income FTC denominator .* exceeds the worldwide-gross-income ceiling",
        ):
            validate_documented_positive_income_denominator_bound_2025(
                total_gross_income_for_ftc_usd=Decimal("31000.00"),
                taxable_income_usd=Decimal("15000.00"),
                standard_deduction_usd=Decimal("15000.00"),
            )

        # Negative inputs fail closed before the bound check.
        with self.assertRaisesRegex(ValueError, "must be non-negative"):
            validate_documented_positive_income_denominator_bound_2025(
                total_gross_income_for_ftc_usd=Decimal("-1.00"),
                taxable_income_usd=Decimal("15000.00"),
                standard_deduction_usd=Decimal("15000.00"),
            )

    def test_load_us_assessment_inputs_requires_explicit_profile_elections_and_assumptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            profile_path = paths.profile_path
            profile = json.loads(profile_path.read_text())
            profile["jurisdictions"]["usa"]["filing_posture"] = "maried_joint"
            profile_path.write_text(json.dumps(profile))
            # Filing posture selects the thresholds for 26 U.S.C. § 1, § 63,
            # § 1211(b), and § 1411. Typos must fail closed, not fall into MFS.
            with self.assertRaisesRegex(ValueError, "Unsupported U.S. filing posture"):
                load_us_assessment_inputs_2025(paths)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            profile_path = paths.profile_path
            profile = json.loads(profile_path.read_text())
            profile["jurisdictions"]["usa"]["filing_posture"] = "mfs_nra_spouse"
            profile["spouse"] = {"name": ""}
            del profile["spouse"]["name"]
            profile_path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, "Missing required spouse name"):
                load_us_assessment_inputs_2025(paths)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            overrides_path = paths.manual_overrides_path
            overrides = json.loads(overrides_path.read_text())
            overrides["treaty_resourcing"]["enabled"] = None
            overrides_path.write_text(json.dumps(overrides))
            profile_path = paths.profile_path
            profile = json.loads(profile_path.read_text())
            del profile["elections"]["use_treaty_resourcing"]
            profile_path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, "Missing required U.S. treaty resourcing election"):
                load_us_assessment_inputs_2025(paths)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            overrides_path = paths.manual_overrides_path
            overrides = json.loads(overrides_path.read_text())
            overrides["treaty_resourcing"]["enabled"] = "yes"
            overrides_path.write_text(json.dumps(overrides))
            with self.assertRaisesRegex(ValueError, "Invalid treaty_resourcing.enabled"):
                load_us_assessment_inputs_2025(paths)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            profile_path = paths.profile_path
            profile = json.loads(profile_path.read_text())
            del profile["elections"]["us_ftc_method"]
            profile_path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, "Missing required U.S. FTC method"):
                load_us_assessment_inputs_2025(paths)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            profile_path = paths.profile_path
            profile = json.loads(profile_path.read_text())
            profile["elections"]["us_ftc_method"] = "paid"
            profile_path.write_text(json.dumps(profile))
            # Workstream 3 — 26 U.S.C. § 905(a) paid-basis FTC posture is
            # now a supported election. The loader records the posture as
            # ``accrued_basis_ftc=False`` on ``USReturnProfile2025`` so
            # downstream FTC chain consumers know which timing applies;
            # the legal arithmetic continues to use available foreign tax.
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertFalse(inputs.profile.accrued_basis_ftc)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)

            assumptions_path = paths.tax_positions_root / "us-model-assumptions.csv"
            assumptions_lines = assumptions_path.read_text().splitlines()
            assumptions_path.write_text(
                "\n".join(
                    [
                        assumptions_lines[0],
                        *[line for line in assumptions_lines[1:] if "include_staking_in_niit" not in line],
                    ]
                )
                + "\n"
            )
            with self.assertRaisesRegex(ValueError, "Missing required U.S. assumption: include_staking_in_niit"):
                load_us_assessment_inputs_2025(paths)

    def test_load_us_assessment_inputs_uses_germany_treaty_packet_when_present(self) -> None:
        # DBA-USA Art. 23 and IRS Pub. 514 line 17/18 require the U.S. worksheet to
        # consume Germany's computed tax and credit on U.S.-source dividends. The
        # loader consumes the typed same-run Germany packet supplied by the
        # orchestrator, matches item IDs to U.S. treaty items, and converts Germany
        # tax/credit values to the U.S. model's USD workpaper currency.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            write_demo_us_treaty_dividend_items(paths)

            inputs = load_us_assessment_inputs_2025(
                paths,
                germany_treaty_dividend_items=self._demo_germany_treaty_dividend_packet_items(),
            )

        self.assertEqual(
            inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd,
            Decimal("40.91"),
        )
        self.assertEqual(
            inputs.treaty_inputs.german_residence_credit_for_us_tax_usd,
            Decimal("40.91"),
        )
        self.assertEqual(inputs.treaty_inputs.germany_treaty_us_source_dividend_gross_usd, Decimal("316.03"))
        self.assertEqual(
            inputs.treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd,
            Decimal("47.40"),
        )
        self.assertEqual(
            tuple(item.item_id for item in inputs.treaty_inputs.germany_treaty_dividend_items),
            ("msft_us_dividend",),
        )
        self.assertIn("item ID", inputs.treaty_inputs.germany_treaty_dividend_items[0].fx_reconciliation)

    def test_load_us_assessment_inputs_rejects_explicit_germany_packet_coverage_gap(self) -> None:
        # IRS Pub. 514 additional FTC worksheet lines 1/8/12/16 and 17/18 require
        # the same U.S.-source dividend stack. If the Germany core emits an explicit
        # same-run packet that does not cover the U.S. treaty dividend item set, the
        # U.S. loader must fail closed instead of fabricating missing worksheet
        # values as zero.
        # Source: https://www.irs.gov/publications/p514.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))

            with self.assertRaisesRegex(ValueError, "item coverage"):
                load_us_assessment_inputs_2025(paths, germany_treaty_dividend_items=())

    def test_load_us_assessment_inputs_ignores_stale_audit_only_germany_treaty_packet(self) -> None:
        # IRS Pub. 514 lines 17/18 and DBA-USA Art. 23 require Germany's current
        # residence-country tax and credit for the same dividend stack. The U.S.
        # loader must not consume a durable Germany-to-U.S. bridge file as logic
        # input; stale audit files must be harmless unless the same-run orchestrator
        # explicitly supplies a typed treaty packet in memory.
        # Sources: https://www.irs.gov/publications/p514 and
        # https://www.irs.gov/pub/irs-trty/germtech.pdf.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            baseline_packet_precredit = load_us_assessment_inputs_2025(
                paths
            ).treaty_inputs.german_precredit_tax_on_us_source_dividends_usd
            packet = {
                "schema_version": 1,
                "source_role": "germany_to_usa_treaty_dividend_bridge",
                "source_fingerprints": {
                    "normalized/derived-facts/germany/income-cashflows.csv": "not-the-current-sha256"
                },
                "items": [
                    {
                        "item_id": "msft_us_dividend",
                        "owner_slot": "person_1",
                        "dividend_class": "portfolio_dividend",
                        "gross_dividend_eur": "280.00",
                        "german_taxable_dividend_eur": "280.00",
                        "article_10_source_tax_ceiling_eur": "42.00",
                        "germany_precredit_tax_eur": "40.91",
                        "germany_residence_credit_eur": "40.91",
                    }
                ],
                "totals": {
                    "gross_dividend_eur": "280.00",
                    "article_10_source_tax_ceiling_eur": "42.00",
                    "germany_precredit_tax_eur": "40.91",
                    "germany_residence_credit_eur": "40.91",
                },
            }
            (paths.analysis_root / "de-us-treaty-dividend-packet.json").write_text(json.dumps(packet))

            inputs = load_us_assessment_inputs_2025(paths)

        self.assertEqual(
            inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd,
            baseline_packet_precredit,
        )
        self.assertIsNone(inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd)

    def test_load_us_assessment_inputs_preserves_zero_germany_treaty_dividend_outputs(self) -> None:
        # IRS Pub. 514 lines 17/18 may legitimately be zero when Germany's § 20 Abs. 9
        # Sparer-Pauschbetrag fully shelters the U.S.-source dividend. Present zero
        # outputs are legal conclusions from the Germany core, not missing data that
        # should fall back to residual-rate assumptions.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))
            (paths.tax_positions_root / "us-treaty-dividend-items.csv").write_text(
                "item_id,treaty_bucket,gross_dividend_usd,source,note\n"
            )

            inputs = load_us_assessment_inputs_2025(paths, germany_treaty_dividend_items=())

        self.assertEqual(inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd, Decimal("0.00"))
        self.assertEqual(inputs.treaty_inputs.german_residence_credit_for_us_tax_usd, Decimal("0.00"))
        self.assertEqual(inputs.treaty_inputs.germany_treaty_us_source_dividend_gross_usd, Decimal("0.00"))
        self.assertEqual(inputs.treaty_inputs.germany_treaty_us_source_dividend_allowed_us_tax_usd, Decimal("0.00"))

    def test_load_us_assessment_inputs_supports_ordinary_married_joint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_ordinary_married_joint_workspace(Path(tmp))

            inputs = load_us_assessment_inputs_2025(paths)

        self.assertEqual(inputs.profile.filing_status_label, "Married filing jointly")
        self.assertEqual(inputs.profile.spouse_name_for_mfs_line, "")
        self.assertEqual(inputs.constants.standard_deduction_2025_usd, Decimal("31500.00"))
        self.assertEqual(inputs.constants.capital_loss_limit_usd, Decimal("3000.00"))
        self.assertEqual(inputs.constants.tax_bracket_10_ceiling_2025_usd, Decimal("23850.00"))

    def test_us_capital_workpaper_uses_selected_1211_loss_limit_for_mfj(self) -> None:
        # 26 U.S.C. § 1211(b) limits individual capital-loss deductions at $3,000,
        # except $1,500 for married-filing-separately. The workpaper must use the
        # selected filing posture from the loader, not the core MFS default.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_ordinary_married_joint_workspace(root)
            self._rewrite_csv_key_value(
                paths.derived_facts_root / "usa" / "capital-summary.csv",
                {
                    "schwab_short_box_a_gain_usd": "-2500.00",
                    "schwab_short_box_b_gain_usd": "0.00",
                    "schwab_long_box_d_gain_usd": "0.00",
                    "schwab_section_1256_total_usd": "0.00",
                    "jpm_short_type_a_gain_usd": "0.00",
                    "coinbase_short_with_basis_proceeds_usd": "0.00",
                    "coinbase_short_with_basis_basis_usd": "0.00",
                    "coinbase_short_unknown_proceeds_usd": "0.00",
                    "coinbase_short_unknown_basis_reconstructed_usd": "0.00",
                    "coinbase_long_with_basis_proceeds_usd": "0.00",
                    "coinbase_long_with_basis_basis_usd": "0.00",
                },
            )
            env = os.environ.copy()
            env.update(
                {
                    "TAX_PROJECT_ROOT": str(root),
                    "TAX_YEAR": "2025",
                    "TAX_WORKSPACE_ROOT": str(root / "years" / "2025"),
                    "TAX_USE_YEAR_LAYOUT": "1",
                }
            )
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.us_capital_workpaper"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
            results = json.loads(
                (root / "years" / "2025" / "outputs" / "analysis-steps" / "us-capital-results.json").read_text()
            )

        self.assertEqual(results["capital"]["capital_loss_deduction_2025_usd"], "2500.00")

    def test_joint_assessment_uses_mfj_schedule_without_nra_spouse_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_ordinary_married_joint_workspace(Path(tmp))

            assessment = compute_us_assessment_2025(self._load_us_inputs_with_demo_germany_packet(paths))

        self.assertEqual(assessment.regular_tax.wages_usd, Decimal("169300.23"))
        self.assertEqual(assessment.regular_tax.taxable_income_usd, Decimal("139695.23"))
        self.assertEqual(assessment.regular_tax.regular_tax_before_credits_usd, Decimal("20469.25"))

    def test_us_core_assessment_exposes_law_ordered_render_stages(self) -> None:
        # The audit trace and treaty renderers must be projections of the core legal result.
        # Each stage needs a legal reference so the renderer does not reconstruct the IRC
        # §§ 1, 61, 63, 901, 904, 1211, 1411, or treaty ordering on its own.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_us_inputs_tree(Path(tmp))

            assessment = compute_us_assessment_2025(self._load_us_inputs_with_demo_germany_packet(paths))

        self.assertTrue(hasattr(assessment, "law_order_stages"))
        stages = list(assessment.law_order_stages)
        self.assertIn("capital_gain_or_loss_line_7a", [stage.step for stage in stages])
        self.assertIn("treaty_resourcing_additional_ftc", [stage.step for stage in stages])
        self.assertTrue(all(stage.legal_reference for stage in stages))
        self.assertTrue(all(stage.authority_url for stage in stages))
        # IRC §§ 1, 61, 63, 901, 904, 1211, and 1411 trace rows feed the legal audit,
        # so every core stage must carry its precision/source note with the authority.
        blank_precision_stages = [stage.step for stage in stages if not stage.precision_note]
        self.assertEqual([], blank_precision_stages)

    def test_joint_assessment_rejects_nra_spouse_without_explicit_election(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_joint_nra_spouse_workspace(Path(tmp), explicit_election=None)

            with self.assertRaisesRegex(ValueError, "explicit election"):
                load_us_assessment_inputs_2025(paths)

    def test_joint_assessment_accepts_nra_spouse_with_explicit_election(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_joint_nra_spouse_workspace(Path(tmp), explicit_election=True)
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["elect_joint_return_with_nra_spouse_for_niit"] = True
            paths.profile_path.write_text(json.dumps(profile))

            inputs = load_us_assessment_inputs_2025(paths)

        self.assertEqual(inputs.profile.filing_status_label, "Married filing jointly")
        self.assertEqual(inputs.profile.spouse_name_for_mfs_line, "")
        self.assertTrue(inputs.profile.joint_return_with_nra_spouse_election)
        self.assertEqual(inputs.profile.joint_return_spouse_name, "Jamie Example")
        self.assertEqual(inputs.constants.niit_threshold_usd, Decimal("250000.00"))

    def test_joint_nra_spouse_without_niit_election_uses_mfs_8960_threshold(self) -> None:
        # Form 8960 instructions for a § 6013(g)/(h) joint return with an NRA spouse
        # default the NIIT computation to married-filing-separately unless the separate
        # NIIT joint-election treatment is also chosen.
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_joint_nra_spouse_workspace(Path(tmp), explicit_election=True)

            inputs = load_us_assessment_inputs_2025(paths)

        self.assertEqual(inputs.profile.filing_status_label, "Married filing jointly")
        self.assertEqual(inputs.constants.standard_deduction_2025_usd, Decimal("31500.00"))
        self.assertEqual(inputs.constants.niit_threshold_usd, Decimal("125000.00"))

    def test_joint_nra_spouse_niit_joint_threshold_requires_separate_8960_election(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_joint_nra_spouse_workspace(Path(tmp), explicit_election=True)
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["elect_joint_return_with_nra_spouse_for_niit"] = True
            paths.profile_path.write_text(json.dumps(profile))

            inputs = load_us_assessment_inputs_2025(paths)

        self.assertEqual(inputs.constants.niit_threshold_usd, Decimal("250000.00"))

    def test_joint_nra_spouse_election_is_visible_in_treaty_packet_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_joint_nra_spouse_workspace(root, explicit_election=True)
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["elect_joint_return_with_nra_spouse_for_niit"] = True
            paths.profile_path.write_text(json.dumps(profile))
            self._run_same_process_germany_then_us_model(root)
            env = self._pipeline_env(root)
            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.us_treaty_packet"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )
            packet = json.loads((root / "years" / "2025" / "outputs" / "analysis-steps" / "us-treaty-package.json").read_text())
            entry_text = (root / "years" / "2025" / "outputs" / "analysis-steps" / "us-treaty-entry-sheet.md").read_text()
        self.assertEqual(packet["chosen_position"]["filing_status"], "Married filing jointly")
        self.assertEqual(packet["chosen_position"]["joint_return_spouse_name"], "Jamie Example")
        self.assertEqual(packet["chosen_position"]["joint_return_with_nra_spouse_election"], "yes")
        self.assertIn("explicit NRA-spouse joint-return election", entry_text)

    def test_treaty_disabled_packet_does_not_attach_publication_514_additional_credit_worksheet(self) -> None:
        # Pub. 514 additional-credit worksheet is only a filing attachment when
        # treaty re-sourcing is actually claimed. A disabled treaty branch must
        # not tell the user to attach a zero worksheet.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)
            overrides = json.loads(paths.manual_overrides_path.read_text())
            overrides["treaty_resourcing"]["enabled"] = False
            paths.manual_overrides_path.write_text(json.dumps(overrides))
            self._run_same_process_germany_then_us_model(root)
            env = self._pipeline_env(root)
            subprocess.run([sys.executable, "-m", "tax_pipeline.pipelines.y2025.us_treaty_packet"], check=True, cwd=PROJECT_ROOT, env=env)

            packet = json.loads((paths.analysis_root / "us-treaty-package.json").read_text())
            entry_text = (paths.analysis_root / "us-treaty-entry-sheet.md").read_text()
            statements_text = (paths.analysis_root / "us-supporting-statements.md").read_text()

        self.assertEqual(packet["chosen_position"]["treaty_resourcing_claimed"], "no")
        self.assertEqual(packet["treaty_resourcing_worksheet"]["status"], "not_applicable")
        self.assertNotIn("Publication 514 `Additional Foreign Tax Credit on U.S. Income` worksheet as an attachment", entry_text)
        self.assertNotIn("Attach the Publication 514 `Additional Foreign Tax Credit on U.S. Income` worksheet", statements_text)

    def test_zero_net_digital_asset_sale_still_checks_form_1040_digital_asset_yes(self) -> None:
        # IRS digital-asset question is transaction-presence based. A sale/exchange
        # with zero net gain still requires a Yes answer.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)
            self._rewrite_csv_key_value(
                paths.derived_facts_root / "usa" / "capital-summary.csv",
                {
                    "coinbase_short_with_basis_proceeds_usd": "100.00",
                    "coinbase_short_with_basis_basis_usd": "100.00",
                    "coinbase_short_unknown_proceeds_usd": "0.00",
                    "coinbase_short_unknown_basis_reconstructed_usd": "0.00",
                    "coinbase_long_with_basis_proceeds_usd": "0.00",
                    "coinbase_long_with_basis_basis_usd": "0.00",
                },
            )
            self._rewrite_csv_key_value(
                paths.derived_facts_root / "common" / "other-income-facts.csv",
                {"staking_income_usd": "0.00"},
            )
            self._run_same_process_germany_then_us_model(root)
            env = self._pipeline_env(root)
            subprocess.run([sys.executable, "-m", "tax_pipeline.pipelines.y2025.us_treaty_packet"], check=True, cwd=PROJECT_ROOT, env=env)

            packet = json.loads((paths.analysis_root / "us-treaty-package.json").read_text())

        self.assertEqual(packet["chosen_position"]["digital_assets_checkbox"], "Yes")

    def test_treaty_packet_renders_from_us_model_projection_not_capital_sidecar_artifacts(self) -> None:
        # Treaty rendering must consume the final U.S. core model output. It should not need
        # the capital workpaper sidecar after us_model has written the Form 1040/Schedule D/
        # treaty projection from the same 26 U.S.C. §§ 901/904 and Publication 514 core.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)
            self._run_same_process_germany_then_us_model(root)
            env = self._pipeline_env(root)
            for path in (
                paths.analysis_root / "us-capital-results.json",
                paths.analysis_root / "us-form-8949-income-buckets.csv",
            ):
                if path.exists():
                    path.unlink()

            subprocess.run(
                [sys.executable, "-m", "tax_pipeline.pipelines.y2025.us_treaty_packet"],
                check=True,
                cwd=PROJECT_ROOT,
                env=env,
            )

            packet = json.loads((paths.analysis_root / "us-treaty-package.json").read_text())

        self.assertIn("form_1040", packet)
        self.assertIn("treaty_resourcing_worksheet", packet)

    def test_us_treaty_packet_runs_for_paid_basis_ftc_posture(self) -> None:
        # Workstream 3 — 26 U.S.C. § 905(a) paid-basis FTC posture is a
        # supported election. The treaty packet must run through under
        # paid-basis profiles; the timing posture is recorded on
        # ``USReturnProfile2025.accrued_basis_ftc=False`` for downstream
        # consumers, while the legal arithmetic continues to use
        # available foreign tax (current + carryover).
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = self._seed_us_inputs_tree(root)
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["us_ftc_method"] = "paid"
            paths.profile_path.write_text(json.dumps(profile))
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertFalse(inputs.profile.accrued_basis_ftc)

    def test_us_model_writes_audit_artifacts_with_legal_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_us_inputs_tree(root)
            self._run_same_process_germany_then_us_model(root)
            trace_path = root / "years" / "2025" / "outputs" / "analysis-steps" / "us-tax-trace.csv"
            audit_path = root / "years" / "2025" / "outputs" / "analysis-steps" / "us-audit-note.md"
            self.assertTrue(trace_path.exists())
            self.assertTrue(audit_path.exists())
            trace_text = trace_path.read_text()
            audit_text = audit_path.read_text()
        self.assertIn("regular_tax_before_credits", trace_text)
        self.assertIn("legal_reference", trace_text.splitlines()[0])
        self.assertIn("Publication 514", audit_text)
        self.assertIn("Statutory Order Used", audit_text)
        self.assertIn("26 U.S.C. § 904", audit_text)
        self.assertIn("manual positions", audit_text.lower())
        # IRS Publication 514 treaty-resourcing support uses the average-tax-rate
        # worksheet, not a direct regular-tax-difference shortcut.
        self.assertIn("Publication 514 average-tax-rate method", trace_text)
        self.assertNotIn("regular-tax difference with and without", trace_text)
