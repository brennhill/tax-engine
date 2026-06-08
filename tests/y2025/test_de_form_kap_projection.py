"""TDD test for ``DE25-FORM-KAP-PROJECTION`` (WS-4C).

The DE25-FORM-KAP-PROJECTION stage replaces the script-level Anlage KAP
form-line projection in
``tax_pipeline/pipelines/y2025/germany_projections.py`` (the headline
offender being ``kap_line_19 = ordinary + stock_pos - stock_neg +
option_pos - option_neg`` at line 113 — flagged by I2 / I5 in
``docs/invariant-migration-plan.md``).

Promoting the projection arithmetic into a ``LawRule.calculate`` body
brings every Zeile-bound EUR amount inside the audit graph: the
executed ``StageResult`` carries fingerprints for the line outputs and
``OutputDeclaration.form_line_refs`` declares the bidirectional
contract with the renderer's ``_required_form_line`` reads.

Authority:
- § 20 Abs. 1 / Abs. 2 EStG fixes the capital-income classification
  feeding Anlage KAP Zeilen 19-24.
  https://www.gesetze-im-internet.de/estg/__20.html
- § 32d Abs. 1 EStG governs the flat capital-tax surface that Anlage
  KAP collects on Zeile 41 (foreign tax) and the bank-certificate
  Zeilen 37/38/40 the same form binds.
  https://www.gesetze-im-internet.de/estg/__32d.html
- InvStG § 20 governs the fund-related Teilfreistellung / fund-type
  taxonomy feeding Anlage KAP-INV Zeilen 4 / 8 / 14 / 26.
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.core.stages import AuditWaypoint, FormLineRef
from tax_pipeline.y2025.germany_law import GermanyCapitalIncomeFact2025, GermanyCapitalSaleFact2025
from tax_pipeline.y2025.germany_stages import germany_law_stages_2025
from tax_pipeline.y2025.germany_kap_projection_rules import (
    DE25_FORM_KAP_PROJECTION_STAGE_ID,
    de25_form_kap_projection,
    execute_germany_kap_projection_rule_graph,
    germany_kap_projection_initial_facts_2025,
    germany_kap_projection_initial_fingerprints_2025,
)


D = Decimal


def _facts(
    *,
    foreign_tax_1099_eur: Decimal = D("0.00"),
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...] = (),
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...] = (),
    fund_classification: dict[str, str] | None = None,
    dher_stock_gain_eur: Decimal = D("0.00"),
    vorabpauschale_taxable_after_teilfreistellung_eur: Decimal = D("0.00"),
) -> dict:
    # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung) is a declared
    # input of DE25-FORM-KAP-PROJECTION; default to zero for tests that
    # exercise the non-Vorabpauschale projection lines.
    # https://www.gesetze-im-internet.de/invstg_2018/__19.html
    return germany_kap_projection_initial_facts_2025(
        foreign_tax_1099_eur=foreign_tax_1099_eur,
        sale_facts=sale_facts,
        income_facts=income_facts,
        fund_classification=fund_classification or {},
        dher_stock_gain_eur=dher_stock_gain_eur,
        vorabpauschale_taxable_after_teilfreistellung_eur=(
            vorabpauschale_taxable_after_teilfreistellung_eur
        ),
    )


class De25FormKapProjectionTest(unittest.TestCase):
    """Per CLAUDE.md, every tax-rule cites legal authority + URL.
    DE25-FORM-KAP-PROJECTION cites § 20 EStG, § 32d Abs. 1 EStG, InvStG § 20.
    """

    def test_stage_declared_in_germany_law_stages(self) -> None:
        # The stage must land in germany_law_stages_2025() so the rule-graph
        # narrative-packet builder and legal-execution-graph emit it.
        stages = germany_law_stages_2025()
        kap_stage = next(
            (s for s in stages if s.stage_id == DE25_FORM_KAP_PROJECTION_STAGE_ID),
            None,
        )
        self.assertIsNotNone(
            kap_stage,
            f"{DE25_FORM_KAP_PROJECTION_STAGE_ID} must appear in germany_law_stages_2025()",
        )
        assert kap_stage is not None
        self.assertEqual(kap_stage.country_or_scope, "DE-2025")
        # Citations: § 20 Abs. 1/2 EStG, § 32d Abs. 1 EStG, InvStG § 20.
        joined_refs = " | ".join(kap_stage.legal_refs)
        self.assertIn("§ 20 Abs. 1 EStG", joined_refs)
        self.assertIn("§ 20 Abs. 2 EStG", joined_refs)
        self.assertIn("§ 32d Abs. 1 EStG", kap_stage.legal_refs)
        self.assertIn("InvStG § 20", kap_stage.legal_refs)
        self.assertIn(
            "https://www.gesetze-im-internet.de/estg/__20.html",
            kap_stage.authority_urls,
        )
        self.assertIn(
            "https://www.gesetze-im-internet.de/estg/__32d.html",
            kap_stage.authority_urls,
        )
        self.assertIn(
            "https://www.gesetze-im-internet.de/invstg_2018/__20.html",
            kap_stage.authority_urls,
        )

    def test_form_line_refs_align_with_renderer_reads(self) -> None:
        # The renderer reads the surviving ``Anlage KAP - Person 1``
        # lines 19/20/23/41 via
        # ``_required_form_line(rows, person["anlage_kap_label"], line, …)``
        # and ``Anlage KAP-INV`` lines 4/8/14/26. Per invariant I3, every
        # read must match an OutputDeclaration form_line_ref pair.
        # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5 und
        # 6 EStG; the former 2024 per-bucket Anlage KAP lines for
        # Termingeschäfte positives and Termingeschäfte losses are NOT
        # declared and MUST NOT appear in the renderer reads. Authority —
        # BMF 16.05.2025 Steuerbescheinigung-Schreiben:
        # https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
        stages = germany_law_stages_2025()
        kap_stage = next(s for s in stages if s.stage_id == DE25_FORM_KAP_PROJECTION_STAGE_ID)
        declared_pairs: set[tuple[str, str]] = set()
        for decl in kap_stage.outputs:
            for ref in decl.form_line_refs:
                declared_pairs.add((ref.form, ref.line))
        # The Person 1 KAP form lines this stage materialises (post-JStG-2024).
        for line in ("19", "20", "23", "41"):
            self.assertIn(
                ("Anlage KAP - Person 1", line),
                declared_pairs,
                f"Anlage KAP - Person 1 line {line} must be declared by {DE25_FORM_KAP_PROJECTION_STAGE_ID}",
            )
        # Former 2024 Anlage KAP per-bucket lines for Termingeschäfte
        # positives and Termingeschäfte losses are dropped post-JStG-2024.
        for dropped_line in ("21", "24"):
            self.assertNotIn(
                ("Anlage KAP - Person 1", dropped_line),
                declared_pairs,
                f"Anlage KAP - Person 1 line {dropped_line} MUST NOT be declared post-JStG-2024 "
                f"(§ 20 Abs. 6 Sätze 5/6 EStG deletion, in Kraft 06.12.2024)",
            )
        # KAP-INV lines.
        for line in ("4", "8", "14", "26"):
            self.assertIn(
                ("Anlage KAP-INV", line),
                declared_pairs,
                f"Anlage KAP-INV line {line} must be declared by {DE25_FORM_KAP_PROJECTION_STAGE_ID}",
            )

    def test_calculate_matches_projection_helper_kap_line_19(self) -> None:
        # Pin the formula germany_projections.py:113 used to compute:
        # kap_line_19 = ordinary + stock_pos - stock_neg + option_pos - option_neg.
        # ordinary = sum of non-fund_like income (excluding foreign_tax)
        # stock_pos / stock_neg = signed split of stock-bucket sale gains
        # option_pos / option_neg net into Zeile 19 but are NOT emitted
        # as their own output_keys post-JStG-2024. § 20 Abs. 6 Sätze 5/6
        # EStG were deleted by JStG 2024 (in Kraft 06.12.2024), so the
        # former 2024 per-bucket Termingeschäfte Zeilen do not exist on
        # the VZ 2025 Anlage KAP. BMF 16.05.2025 Steuerbescheinigung-
        # Schreiben confirms.
        sale_facts = (
            GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="ABC", gain_eur_matched=D("100.00")),
            GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="DEF", gain_eur_matched=D("-30.00")),
            GermanyCapitalSaleFact2025(asset_bucket="option", symbol="OPT1", gain_eur_matched=D("50.00")),
            GermanyCapitalSaleFact2025(asset_bucket="option", symbol="OPT2", gain_eur_matched=D("-20.00")),
        )
        income_facts = (
            GermanyCapitalIncomeFact2025(
                kind="qualified_dividend",
                asset_bucket="stock",
                symbol="ABC",
                eur_amount=D("40.00"),
            ),
            GermanyCapitalIncomeFact2025(
                kind="interest",
                asset_bucket="bond",
                symbol="BOND",
                eur_amount=D("60.00"),
            ),
            GermanyCapitalIncomeFact2025(
                kind="foreign_tax",
                asset_bucket="stock",
                symbol="ABC",
                eur_amount=D("5.00"),
            ),
        )
        facts = _facts(
            foreign_tax_1099_eur=D("12.34"),
            sale_facts=sale_facts,
            income_facts=income_facts,
            dher_stock_gain_eur=D("0.00"),
            fund_classification={},
        )
        outputs = de25_form_kap_projection(facts)
        # ordinary = 40 + 60 (foreign_tax row excluded) = 100
        # stock_pos = 100, stock_neg = 30
        # option_pos = 50, option_neg = 20 (net into Zeile 19, not surfaced)
        # kap_line_19 = 100 + 100 - 30 + 50 - 20 = 200
        self.assertEqual(outputs["de.kap.line_19_eur"], D("200.00"))
        self.assertEqual(outputs["de.kap.line_20_eur"], D("100.00"))
        self.assertEqual(outputs["de.kap.line_23_eur"], D("30.00"))
        self.assertEqual(outputs["de.kap.line_41_eur"], D("12.34"))
        # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5
        # und 6 EStG. The two former 2024 per-bucket Termingeschäfte
        # output_keys MUST be absent from the rule output dict; the
        # economic content is folded into de.kap.line_19_eur above.
        self.assertNotIn("de.kap.line_21_eur", outputs)
        self.assertNotIn("de.kap.line_24_eur", outputs)

    def test_termingeschaefte_loss_over_20k_fully_offsets_capital_income(self) -> None:
        # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5 und
        # 6 EStG. Before this change, a Termingeschäfte loss could only
        # offset Termingeschäfte gains up to €20,000 per year (the rest
        # was caged in a Verlustverrechnungskreis carryforward). Post-
        # JStG-2024, a € 25,000 Termingeschäfte loss fully nets against
        # ordinary § 20 Kapitalerträge inside the surviving § 20 Abs. 6
        # Sätze 1-4 pot — there is no €20k cap.
        #
        # Worked example: ordinary § 20 dividends = €50,000;
        # Termingeschäfte loss = €25,000. Pre-JStG-2024 the cap would
        # have allowed only €20,000 of the loss to offset gains;
        # post-JStG-2024 the full €25,000 nets into Zeile 19.
        # Expected: kap_line_19 = 50,000 + 0 (stock) - 0 (stock) +
        # 0 (option_pos) - 25,000 (option_neg) = €25,000.
        #
        # Authority — § 20 Abs. 6 EStG post-JStG-2024:
        # https://www.gesetze-im-internet.de/estg/__20.html
        # BMF 16.05.2025 Steuerbescheinigung-Schreiben:
        # https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
        sale_facts = (
            GermanyCapitalSaleFact2025(
                asset_bucket="option",
                symbol="ESVT",
                gain_eur_matched=D("-25000.00"),
            ),
        )
        income_facts = (
            GermanyCapitalIncomeFact2025(
                kind="qualified_dividend",
                asset_bucket="stock",
                symbol="ABC",
                eur_amount=D("50000.00"),
            ),
        )
        facts = _facts(
            foreign_tax_1099_eur=D("0.00"),
            sale_facts=sale_facts,
            income_facts=income_facts,
            dher_stock_gain_eur=D("0.00"),
            fund_classification={},
        )
        outputs = de25_form_kap_projection(facts)
        # Zeile 19 = ordinary (50,000) + stock_pos (0) - stock_neg (0) +
        # option_pos (0) - option_neg (25,000) = 25,000. Pre-JStG-2024
        # the cap would have produced a different value because only
        # the first €20,000 of option_neg could offset gains.
        self.assertEqual(outputs["de.kap.line_19_eur"], D("25000.00"))
        # The full €25k loss nets — it is not capped at €20k anywhere.
        # We verify the assertion holds by sanity-checking the inputs
        # against the post-JStG-2024 absence of the cap: the resulting
        # Zeile 19 is exactly (50,000 - 25,000) = 25,000, NOT the
        # pre-JStG-2024 capped value of (50,000 - 20,000) = 30,000.
        self.assertNotEqual(
            outputs["de.kap.line_19_eur"],
            D("30000.00"),
            "Post-JStG-2024 there is no €20,000 cap on Termingeschäfte "
            "loss offsetting; Zeile 19 should reflect the FULL €25,000 "
            "loss netting, producing €25,000 not the pre-JStG €30,000."
        )

    def test_executor_records_outputs_in_rule_graph(self) -> None:
        # End-to-end: ``execute_germany_kap_projection_rule_graph`` produces a
        # ``RuleGraphExecution`` whose final facts include the form-line
        # values (the I2 progress condition — the values live inside the rule
        # graph rather than in script-level arithmetic).
        facts = _facts(
            foreign_tax_1099_eur=D("100.00"),
            sale_facts=(
                GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="X", gain_eur_matched=D("500.00")),
            ),
            income_facts=(
                GermanyCapitalIncomeFact2025(kind="interest", asset_bucket="bond", symbol="B", eur_amount=D("200.00")),
            ),
            dher_stock_gain_eur=D("0.00"),
            fund_classification={},
        )
        execution = execute_germany_kap_projection_rule_graph(
            facts,
            input_fingerprints=germany_kap_projection_initial_fingerprints_2025(facts),
        )
        # kap_line_19 = ordinary(200) + stock_pos(500) - 0 + 0 - 0 = 700
        self.assertEqual(execution.final_facts["de.kap.line_19_eur"], D("700.00"))
        self.assertEqual(execution.final_facts["de.kap.line_41_eur"], D("100.00"))
        # StageResult fingerprints exist for each declared output.
        self.assertEqual(len(execution.stage_results), 1)
        result = execution.stage_results[0]
        self.assertEqual(result.stage_id, DE25_FORM_KAP_PROJECTION_STAGE_ID)
        # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5 und
        # 6 EStG. The former 2024 per-bucket Termingeschäfte output keys
        # (de.kap.line_21_eur, de.kap.line_24_eur) are NOT in this set
        # and MUST NOT have fingerprints; their economic content folds
        # into de.kap.line_19_eur.
        for key in (
            "de.kap.line_19_eur",
            "de.kap.line_20_eur",
            "de.kap.line_23_eur",
            "de.kap.line_41_eur",
            "de.kap_inv.line_4_eur",
            "de.kap_inv.line_8_eur",
            "de.kap_inv.line_14_eur",
            "de.kap_inv.line_26_eur",
            "de.kap_inv.fund_rows",
        ):
            self.assertIn(key, result.output_fingerprints, f"missing fingerprint for {key}")
        for dropped_key in ("de.kap.line_21_eur", "de.kap.line_24_eur"):
            self.assertNotIn(
                dropped_key,
                result.output_fingerprints,
                f"{dropped_key} fingerprint MUST be absent post-JStG-2024 "
                "(§ 20 Abs. 6 Sätze 5/6 EStG deletion, in Kraft 06.12.2024)",
            )


if __name__ == "__main__":
    unittest.main()
