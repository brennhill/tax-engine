from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.generated_demo import generated_demo_paths
from tax_pipeline.y2025.germany_stages import (
    germany_capital_law_stages_2025,
    germany_children_law_stages_2025,
    germany_final_law_stages_2025,
    germany_kap_projection_law_stages_2025,
    germany_law_stages_2025,
    germany_ordinary_law_stages_2025,
)
from tax_pipeline.narrative.render import DEFAULT_TEMPLATE_ROOT
from tax_pipeline.pipelines.y2025.final_legal_output import write_final_legal_output_2025
from tax_pipeline.pipelines.y2025.rule_narrative_packets import _with_missing_stage_rules
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


def _germany_stages_for_posture(filing_posture: str) -> tuple:
    # Phase 3: filing posture is an input fact, not a rule-list branch. The
    # canonical stage list is the same for every posture; the kept argument
    # name preserves call-site readability for tests that compare per-posture
    # outputs from the same rule list.
    del filing_posture
    return (
        germany_ordinary_law_stages_2025()
        + germany_capital_law_stages_2025()
        + germany_final_law_stages_2025()
        + germany_kap_projection_law_stages_2025()
    )


def _all_declared_stage_variants() -> tuple:
    return (
        *germany_ordinary_law_stages_2025(),
        *germany_capital_law_stages_2025(),
        *germany_final_law_stages_2025(),
        *germany_kap_projection_law_stages_2025(),
        *usa_law_stages_2025(),
        *treaty_law_stages_2025(),
    )


def _form_bound_children_stage_ids() -> set[str]:
    """Children sub-graph stages that have a Pipeline 2 form-line surface.

    The children sub-graph (``germany_children_law_stages_2025``) is
    excluded from ``_all_declared_stage_variants`` because not every
    children stage emits an audit-narrative packet through the executor
    yet (DE25-CHILDREN-CREDITS still narrates via
    DE25-22-FINAL-REFUND's § 31 Satz 4 EStG netting). The stages on this
    list have a form-bound output (Anlage Kind 2025 Zeile 65 for
    DE25-CHILDREN-DISABILITY-PAUSCHBETRAG per § 33b Abs. 5 EStG) and
    therefore must ship a matching narrative template under the
    canonical template root.

    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    form_bound: set[str] = set()
    for stage in germany_children_law_stages_2025():
        if any(decl.form_line_refs for decl in stage.outputs):
            form_bound.update(stage.narrative_templates.values())
    return form_bound


SUPPLEMENTAL_RULE_IDS = {
    "DE25-FACTS",
    "DE25-NARRATIVE-CAPITAL-FTC",
    "DE25-NARRATIVE-TARIFF",
    "US25-FACTS",
    "US25-NARRATIVE-NIIT",
    "US25-NARRATIVE-PAYMENTS",
    "US25-NARRATIVE-TREATY-FTC",
    # SUMMARY-BILINGUAL is not a per-rule narrative template — it is a
    # standalone bilingual summary document rendered by
    # ``tax_pipeline/pipelines/y2025/bilingual_summary.py`` against
    # already-computed ``germany-model-results.json`` /
    # ``us-tax-estimate.json`` outputs. It lives alongside the per-rule
    # templates so the existing ``narrative/templates/`` Jinja
    # environment can load it, but it has no upstream rule stage.
    "SUMMARY-BILINGUAL",
}


def _allowed_template_rule_ids() -> set[str]:
    return (
        {stage.stage_id for stage in _all_declared_stage_variants()}
        | SUPPLEMENTAL_RULE_IDS
        # Children sub-graph stages that have a Pipeline 2 form-line
        # surface ship their own narrative template per CLAUDE.md
        # naming rule (e.g. DE25-CHILDREN-DISABILITY-PAUSCHBETRAG.jinja
        # for the § 33b Abs. 5 EStG transferral on Anlage Kind 2025
        # Zeile 65). Stages without a form_line_ref still narrate
        # through the parent stage they net into and do not need a
        # standalone template.
        # https://www.gesetze-im-internet.de/estg/__33b.html
        | _form_bound_children_stage_ids()
    )


class RuleNarrativeModelTest(unittest.TestCase):
    def test_rule_narrative_requires_structured_fields_and_serializes_to_json(self) -> None:
        from tax_pipeline.core.narrative import (
            NarrativeFormLine,
            NarrativeMathStep,
            NarrativeValue,
            RuleNarrative,
        )

        packet = RuleNarrative(
            rule_id="DE25-08-SPLIT-TARIFF",
            country="DE",
            language="en",
            template_id="DE25-08-SPLIT-TARIFF",
            title="Splitting tariff",
            legal_refs=("§ 26b EStG", "§ 32a Abs. 5 EStG"),
            authority_urls=("https://www.gesetze-im-internet.de/estg/__32a.html",),
            inputs=(
                NarrativeValue("Taxable income", "100000.00 EUR", "de.ordinary.taxable_income"),
            ),
            math_steps=(
                NarrativeMathStep("Apply splitting tariff", "2 * basic_tax(zve / 2)", "20000.00 EUR"),
            ),
            outputs=(
                NarrativeValue("Income tax", "20000.00 EUR", "de.ordinary.income_tax"),
            ),
            form_lines=(
                NarrativeFormLine("ELSTER Einkommensteuer", "tax calculation", "20000.00 EUR"),
            ),
        )

        self.assertEqual(packet.to_dict()["template_id"], "DE25-08-SPLIT-TARIFF")
        self.assertEqual(json.loads(json.dumps(packet.to_dict()))["outputs"][0]["value"], "20000.00 EUR")

        with self.assertRaisesRegex(ValueError, "RuleNarrative.template_id must equal rule_id"):
            RuleNarrative(
                rule_id="DE25-08-SPLIT-TARIFF",
                country="DE",
                language="en",
                template_id="DE_ordinary_EStG-32a-5-splitting_en",
                title="Splitting tariff",
                legal_refs=("§ 26b EStG",),
                authority_urls=("https://www.gesetze-im-internet.de/estg/__26b.html",),
                inputs=(NarrativeValue("Taxable income", "100000.00 EUR", "de.ordinary.taxable_income"),),
                math_steps=(NarrativeMathStep("Apply splitting tariff", "2 * basic_tax(zve / 2)", "20000.00 EUR"),),
                outputs=(NarrativeValue("Income tax", "20000.00 EUR", "de.ordinary.income_tax"),),
                form_lines=(NarrativeFormLine("ELSTER", "tax", "20000.00 EUR"),),
            )

        with self.assertRaisesRegex(ValueError, "RuleNarrative.math_steps is required"):
            RuleNarrative(
                rule_id="DE25-08-SPLIT-TARIFF",
                country="DE",
                language="en",
                template_id="DE25-08-SPLIT-TARIFF",
                title="Splitting tariff",
                legal_refs=("§ 26b EStG",),
                authority_urls=("https://www.gesetze-im-internet.de/estg/__26b.html",),
                inputs=(NarrativeValue("Taxable income", "100000.00 EUR", "de.ordinary.taxable_income"),),
                math_steps=(),
                outputs=(NarrativeValue("Income tax", "20000.00 EUR", "de.ordinary.income_tax"),),
                form_lines=(NarrativeFormLine("ELSTER", "tax", "20000.00 EUR"),),
            )


class RuleNarrativeRendererTest(unittest.TestCase):
    def test_renderer_uses_rule_named_jinja_templates_and_fails_on_missing_variables(self) -> None:
        from tax_pipeline.core.narrative import (
            NarrativeFormLine,
            NarrativeMathStep,
            NarrativeValue,
            RuleNarrative,
        )
        from tax_pipeline.narrative.render import render_narrative_markdown

        with tempfile.TemporaryDirectory() as tmp:
            template_root = Path(tmp)
            (template_root / "DE_ordinary_EStG-32a-5-splitting_en.jinja").write_text(
                "Rule {{ rule.rule_id }} uses {{ rule.inputs[0].value }} and {{ missing_value }}.\n"
            )
            (template_root / "DE25-08-SPLIT-TARIFF.jinja").write_text(
                "Rule {{ rule.rule_id }} uses {{ rule.inputs[0].value }} and {{ missing_value }}.\n"
            )
            packet = RuleNarrative(
                rule_id="DE25-08-SPLIT-TARIFF",
                country="DE",
                language="en",
                template_id="DE25-08-SPLIT-TARIFF",
                title="Splitting tariff",
                legal_refs=("§ 26b EStG",),
                authority_urls=("https://www.gesetze-im-internet.de/estg/__26b.html",),
                inputs=(NarrativeValue("Taxable income", "100000.00 EUR", "de.ordinary.taxable_income"),),
                math_steps=(NarrativeMathStep("Apply splitting tariff", "2 * basic_tax(zve / 2)", "20000.00 EUR"),),
                outputs=(NarrativeValue("Income tax", "20000.00 EUR", "de.ordinary.income_tax"),),
                form_lines=(NarrativeFormLine("ELSTER", "tax", "20000.00 EUR"),),
            )

            with self.assertRaisesRegex(ValueError, "DE25-08-SPLIT-TARIFF.jinja"):
                render_narrative_markdown((packet,), template_root=template_root, title="Germany")

            (template_root / "DE25-08-SPLIT-TARIFF.jinja").write_text(
                "Rule {{ rule.rule_id }} uses {{ rule.inputs[0].value }}.\n"
            )
            rendered = render_narrative_markdown((packet,), template_root=template_root, title="Germany")

        self.assertIn("# Germany", rendered)
        self.assertIn("Rule DE25-08-SPLIT-TARIFF uses 100000.00 EUR.", rendered)


class RuleNarrativePipelineTest(unittest.TestCase):
    def test_final_output_contains_named_rule_narratives(self) -> None:
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        self.assertIn("narratives", output)
        self.assertEqual(output["narratives"]["DE"]["de"][0]["template_id"], output["narratives"]["DE"]["de"][0]["rule_id"])
        template_ids = {row["template_id"] for row in output["narratives"]["US"]["en"]}
        self.assertIn("US25-NARRATIVE-TREATY-FTC", template_ids)
        self.assertIn("US25-NARRATIVE-NIIT", template_ids)

    def test_germany_single_filer_narrative_uses_basic_tariff_branch_of_collapsed_stage(self) -> None:
        # Phase 3: DE25-08-INCOME-TAX-TARIFF is one canonical stage whose
        # legal_refs cite both § 32a Abs. 1 (basic) and § 32a Abs. 5 (splitting).
        # The branch taken at runtime is observable in the executed packet's
        # input_values["de.ordinary.filing_posture"] - "single" here selects
        # the § 32a(1) basic tariff body inside the calculate function.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        de_stage_rule_ids = {rule["rule_id"] for rule in output["narratives"]["DE"]["en"]}
        de_tax_rule = next(rule for rule in output["narratives"]["DE"]["en"] if rule["rule_id"] == "DE25-08-INCOME-TAX-TARIFF")

        # Old posture-conditional rule_ids must not reappear.
        self.assertNotIn("DE25-08-SPLIT-TARIFF", de_stage_rule_ids)
        self.assertNotIn("DE25-08-BASIC-TARIFF", de_stage_rule_ids)
        self.assertEqual(de_tax_rule["template_id"], "DE25-08-INCOME-TAX-TARIFF")
        # Consolidated stage cites both branches' authorities.
        self.assertIn("§ 32a Abs. 1 EStG", de_tax_rule["legal_refs"])
        self.assertIn("§ 32a Abs. 5 EStG", de_tax_rule["legal_refs"])
        self.assertIn("§ 26b EStG", de_tax_rule["legal_refs"])
        # The branch is recorded in the input values - single posture takes the
        # basic tariff path; the formula text shows the conditional.
        input_keys = {item["key"]: item["value"] for item in de_tax_rule["inputs"]}
        self.assertEqual(input_keys["de.ordinary.filing_posture"], "single")
        formula = de_tax_rule["math_steps"][0]["formula"]
        self.assertIn("married_joint", formula)
        self.assertIn("basic_tariff_2025", formula)

    def test_germany_section_32d5_narrative_separates_credit_from_final_tax(self) -> None:
        # § 32d Abs. 5 EStG determines the foreign-tax credit. The final capital
        # liability is a later result after § 32d Abs. 1 tax, the § 32d Abs. 5
        # credit, SolzG, and the fail-closed treaty check.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        rule = next(rule for rule in output["narratives"]["DE"]["en"] if rule["rule_id"] == "DE25-NARRATIVE-CAPITAL-FTC")
        output_keys = {value["key"]: value["value"] for value in rule["outputs"]}
        math_results = {step["statement"]: step["result"] for step in rule["math_steps"]}

        self.assertEqual(output_keys["de.capital.foreign_tax_credit_applied_eur"], "42.00 EUR")
        self.assertEqual(output_keys["de.capital.capital_tax_with_teilfreistellung_after_treaty_eur"], "238.95 EUR")
        self.assertIn("Apply § 32d(5) foreign-tax credit", math_results)
        self.assertIn("Compute final capital tax after SolzG and treaty check", math_results)
        formulas = " ".join(step["formula"] for step in rule["math_steps"])
        self.assertIn("net foreign tax after refund entitlement", formulas)
        self.assertIn("per-item/source cap", formulas)
        self.assertIn("§ 4 SolzG 1995", rule["legal_refs"])
        self.assertIn("https://www.gesetze-im-internet.de/solzg_1995/__4.html", rule["authority_urls"])
        self.assertNotEqual(
            output_keys["de.capital.foreign_tax_credit_applied_eur"],
            output_keys["de.capital.capital_tax_with_teilfreistellung_after_treaty_eur"],
        )

    def test_germany_tariff_narrative_carries_dated_bmf_pap_authority_url(self) -> None:
        # 2025 § 32a tariff constants are pinned to the dated BMF PAP, because the
        # live statute page can roll forward to later years.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        rule = next(
            rule for rule in output["narratives"]["DE"]["en"]
            if rule["rule_id"] == "DE25-NARRATIVE-TARIFF"
        )

        self.assertIn("BMF Programmablaufplan 2025", rule["legal_refs"])
        self.assertTrue(any("Programmablaufplan-2025" in url for url in rule["authority_urls"]))

    def test_usa_niit_narrative_points_to_form_8960_line_17_and_schedule_2_line_12(self) -> None:
        # Instructions for Form 8960 put the computed NIIT on Form 8960 line 17,
        # then Schedule 2 line 12 carries that amount to Form 1040.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        rule = next(rule for rule in output["narratives"]["US"]["en"] if rule["rule_id"] == "US25-NARRATIVE-NIIT")
        form_lines = {(line["form"], line["line"]): line["value"] for line in rule["form_lines"]}

        self.assertEqual(form_lines[("Form 8960", "line 17")], "0.00 USD")
        self.assertEqual(form_lines[("Schedule 2", "line 12")], "0.00 USD")

    def test_rule_narrative_rendered_markdown_includes_authority_urls(self) -> None:
        # The narrative is the human/LLM audit surface. It must render not only
        # legal labels but also the canonical authority URLs used to verify them.
        from tax_pipeline.pipelines.y2025.rule_narratives import render_rule_narratives

        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)
            render_rule_narratives(paths)

            de_en = (paths.analysis_root / "DE-en-narrative.md").read_text()
            us_en = (paths.analysis_root / "US-en-narrative.md").read_text()

        self.assertIn("https://www.gesetze-im-internet.de/estg/__32d.html", de_en)
        self.assertIn("https://www.irs.gov/publications/p514", us_en)

    def test_each_rule_narrative_packet_carries_law_inputs_math_outputs_and_form_lines(self) -> None:
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        packets = [
            *output["narratives"]["DE"]["de"],
            *output["narratives"]["DE"]["en"],
            *output["narratives"]["US"]["en"],
        ]
        self.assertGreaterEqual(len(packets), 8)
        # Per WS-2B + invariant I3
        # (``tests/test_form_renderer_lines_match_output_declarations.py``),
        # OutputDeclarations whose form_line_refs do not match any
        # ``_required_form_line(rows, form, line, ...)`` renderer read
        # were re-classified to closed-enum AuditWaypoint values; their
        # narrative packets therefore legitimately have empty
        # form_lines. The bidirectional renderer ↔ OutputDeclaration
        # contract still guarantees that every renderer read on a
        # German Anlage KAP / KAP-INV form line maps to a declared
        # FormLineRef somewhere — the form-line surface as a whole is
        # protected by I3, not by per-stage narrative form_lines.
        for packet in packets:
            with self.subTest(rule_id=packet["rule_id"], template_id=packet["template_id"]):
                self.assertTrue(packet["legal_refs"])
                self.assertTrue(packet["authority_urls"])
                self.assertTrue(packet["inputs"])
                self.assertTrue(packet["math_steps"])
                self.assertTrue(packet["outputs"])
                self.assertTrue(all(step["formula"] for step in packet["math_steps"]))
        # At least one packet across the whole audit graph still binds
        # to a form line (the DE25 capital stages on Anlage KAP /
        # KAP-INV); a totally form-line-less audit packet would
        # indicate the bidirectional invariant collapsed.
        self.assertTrue(any(packet["form_lines"] for packet in packets))

    def test_stage_rule_narratives_use_rule_specific_templates_and_real_values(self) -> None:
        # The audit narrative is not allowed to paper over missing rule coverage with
        # metadata-only stage prose or fact-key echoes. Every declared stage must render
        # through a rule-specific Jinja template and carry computed or traceable values.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        packets = [
            *output["narratives"]["DE"]["de"],
            *output["narratives"]["DE"]["en"],
            *output["narratives"]["US"]["en"],
        ]
        stage_ids = {
            *(stage.stage_id for stage in germany_law_stages_2025()),
            *(stage.stage_id for stage in usa_law_stages_2025()),
            *(stage.stage_id for stage in treaty_law_stages_2025()),
        }
        for packet in packets:
            if packet["rule_id"] not in stage_ids:
                continue
            with self.subTest(rule_id=packet["rule_id"], template_id=packet["template_id"]):
                self.assertNotIn("stage_generic", packet["template_id"])
                self.assertEqual(packet["template_id"], packet["rule_id"])
                self.assertTrue((DEFAULT_TEMPLATE_ROOT / f"{packet['template_id']}.jinja").exists())
                packet_text = json.dumps(packet, sort_keys=True)
                self.assertNotIn("available before", packet_text)
                self.assertNotIn("produced by", packet_text)
                for value in (*packet["inputs"], *packet["outputs"]):
                    self.assertNotEqual(value["value"], value["key"])

        ordinary = output["germany"]["forms"]["results"]["ordinary"]
        tariff = next(
            packet for packet in output["narratives"]["DE"]["en"]
            if packet["rule_id"] == "DE25-08-INCOME-TAX-TARIFF"
        )
        tariff_inputs = {item["key"]: item["value"] for item in tariff["inputs"]}
        tariff_outputs = {item["key"]: item["value"] for item in tariff["outputs"]}
        # Under Phase 3 the rich-dict outputs carry the joint-level value;
        # the scalar number we want is inside the JSON-serialized dict.
        taxable_input = json.loads(tariff_inputs["de.ordinary.taxable_income"])
        income_tax_output = json.loads(tariff_outputs["de.ordinary.income_tax"])
        self.assertEqual(taxable_input["joint_taxable_income_eur"], ordinary["joint_taxable_income_eur"])
        self.assertEqual(income_tax_output["joint_income_tax_eur"], ordinary["joint_income_tax_eur"])

    def test_stage_narratives_fail_closed_without_executed_stage_result(self) -> None:
        # A declared legal stage without a same-run StageResult is missing audit
        # evidence, not a harmless narrative gap.
        stages = germany_law_stages_2025()

        with self.assertRaisesRegex(ValueError, "missing executed StageResult"):
            _with_missing_stage_rules(
                (),
                stages,
                country="DE",
                language="en",
                stage_results=(),
            )

    def test_supplemental_narratives_cannot_reuse_declared_law_stage_rule_ids(self) -> None:
        # A LawStage rule_id is a legal execution node ID. Supplemental narrative
        # packets may explain values, but they must not preempt or shadow a stage
        # by reusing that LawStage ID.
        stages = germany_law_stages_2025()

        with self.assertRaisesRegex(ValueError, "reuses declared LawStage rule_id"):
            _with_missing_stage_rules(
                ({"rule_id": stages[0].stage_id},),
                stages,
                country="DE",
                language="en",
            )

    def test_rule_narratives_have_unique_rule_ids_and_no_supplemental_stage_id_reuse(self) -> None:
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        declared_stage_ids = {stage.stage_id for stage in _all_declared_stage_variants()}
        for country, languages in output["narratives"].items():
            for language, packets in languages.items():
                with self.subTest(country=country, language=language):
                    rule_ids = [packet["rule_id"] for packet in packets]
                    self.assertEqual(len(rule_ids), len(set(rule_ids)))
                    for packet in packets:
                        self.assertEqual(packet["template_id"], packet["rule_id"])
                        if packet["rule_id"] in SUPPLEMENTAL_RULE_IDS:
                            self.assertNotIn(packet["rule_id"], declared_stage_ids)

    def test_template_directory_contains_only_rule_id_named_templates(self) -> None:
        allowed = _allowed_template_rule_ids()
        actual = {path.stem for path in DEFAULT_TEMPLATE_ROOT.glob("*.jinja")}

        self.assertEqual(actual - allowed, set())
        self.assertEqual(allowed - actual, set())
        for path in DEFAULT_TEMPLATE_ROOT.glob("*.jinja"):
            text = path.read_text()
            self.assertNotIn("generic", path.name.lower())
            self.assertNotIn("generic", text.lower())
            self.assertNotIn("{% include", text)

    def test_final_narratives_cover_every_declared_legal_stage(self) -> None:
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        filing_posture = output["germany"]["forms"]["results"]["ordinary"]["filing_posture"]
        germany_stage_ids = {stage.stage_id for stage in _germany_stages_for_posture(filing_posture)}
        us_stage_ids = {stage.stage_id for stage in usa_law_stages_2025()}
        treaty_stage_ids = {stage.stage_id for stage in treaty_law_stages_2025()}

        self.assertTrue(germany_stage_ids.issubset({packet["rule_id"] for packet in output["narratives"]["DE"]["de"]}))
        self.assertTrue(germany_stage_ids.issubset({packet["rule_id"] for packet in output["narratives"]["DE"]["en"]}))
        self.assertTrue((us_stage_ids | treaty_stage_ids).issubset({packet["rule_id"] for packet in output["narratives"]["US"]["en"]}))

        for stage in (*_germany_stages_for_posture(filing_posture), *usa_law_stages_2025(), *treaty_law_stages_2025()):
            for template_id in stage.narrative_templates.values():
                with self.subTest(stage_id=stage.stage_id, template_id=template_id):
                    self.assertTrue((DEFAULT_TEMPLATE_ROOT / f"{template_id}.jinja").exists())

    def test_usa_payment_narrative_uses_form_1040_refund_and_amount_owed_branches(self) -> None:
        # Instructions for Form 1040 present overpayment/refund on line 35a and
        # amount owed on line 37. The narrative must not use one signed number for
        # both form lines.
        with generated_demo_paths() as paths:
            output_path = write_final_legal_output_2025(paths)
            output = json.loads(output_path.read_text())

        rule = next(rule for rule in output["narratives"]["US"]["en"] if rule["rule_id"] == "US25-NARRATIVE-PAYMENTS")
        outputs = {value["key"]: value["value"] for value in rule["outputs"]}
        form_lines = {(line["form"], line["line"]): line["value"] for line in rule["form_lines"]}

        self.assertEqual(outputs["us.payments.refund_with_treaty_resourcing_usd"], "778.08 USD")
        self.assertEqual(outputs["us.payments.amount_owed_with_treaty_resourcing_usd"], "0.00 USD")
        self.assertEqual(form_lines[("Form 1040", "line 35a")], "778.08 USD")
        self.assertEqual(form_lines[("Form 1040", "line 37")], "0.00 USD")

    def test_rule_narrative_pipeline_writes_country_language_files(self) -> None:
        from tax_pipeline.pipelines.y2025.rule_narratives import render_rule_narratives

        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)

            outputs = render_rule_narratives(paths)

            de_de = (paths.analysis_root / "DE-de-narrative.md").read_text()
            de_en = (paths.analysis_root / "DE-en-narrative.md").read_text()
            us_en = (paths.analysis_root / "US-en-narrative.md").read_text()

        self.assertEqual(
            outputs,
            {
                "DE-de": paths.analysis_root / "DE-de-narrative.md",
                "DE-en": paths.analysis_root / "DE-en-narrative.md",
                "US-en": paths.analysis_root / "US-en-narrative.md",
            },
        )
        self.assertIn("Grunddaten", de_de)
        self.assertIn("Germany basic facts", de_en)
        self.assertIn(
            "[Form 1116](https://www.irs.gov/forms-pubs/about-form-1116), line 12",
            us_en,
        )
        self.assertIn("Form 8960", us_en)
