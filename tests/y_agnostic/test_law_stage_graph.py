from __future__ import annotations

from dataclasses import is_dataclass
from decimal import Decimal
import inspect
import unittest

from tax_pipeline.core import facts as core_facts
from tax_pipeline.core import stages as core_stages
from tax_pipeline.core.stages import (
    FormLineRef,
    LawRule,
    LawStage,
    OutputDeclaration,
    RuleGraphExecution,
    StageDiagnostic,
    StageResult,
    execute_rule_graph,
    validate_law_stage_graph,
)


def _stage(
    *,
    stage_id: str = "DE25-TEST-TAXABLE-INCOME",
    inputs: tuple[str, ...] = ("de.wages.gross.eur",),
    outputs: tuple[str, ...] = ("de.taxable_income.eur",),
    legal_formula: str = "test fixture: outputs derived from inputs per § 2 Abs. 5 EStG",
) -> LawStage:
        return LawStage(
            stage_id=stage_id,
            country_or_scope="DE",
            legal_refs=("§ 2 Abs. 5 EStG",),
            authority_urls=("https://www.gesetze-im-internet.de/estg/__2.html",),
            input_fact_keys=inputs,
            outputs=tuple(
                OutputDeclaration(
                    key=key,
                    form_line_refs=(FormLineRef(form="ELSTER", line="internal audit stage"),),
                )
                for key in outputs
            ),
            rounding_policy="Cent amounts remain Decimal; final euro rounding happens only in declared tariff stages.",
            law_order_note="Taxable income must be determined before applying the tariff.",
            legal_formula=legal_formula,
            narrative_templates={"en": stage_id},
        )


class LawStageGraphContractsTest(unittest.TestCase):
    def test_law_rule_executes_only_declared_outputs_and_records_graph_fingerprints(self) -> None:
        # A legal calculation must be executable only through a declared LawRule:
        # the rule binds the law metadata, implementation function, dependencies,
        # output fingerprints, and audit graph together.
        taxable_stage = _stage(
            stage_id="DE25-07-TAXABLE-INCOME",
            inputs=("de.wages.gross.eur",),
            outputs=("de.ordinary.taxable_income",),
        )
        tariff_stage = _stage(
            stage_id="DE25-08-BASIC-TARIFF",
            inputs=("de.ordinary.taxable_income",),
            outputs=("de.ordinary.income_tax",),
        )

        execution = execute_rule_graph(
            {"de.wages.gross.eur": Decimal("50000.00")},
            (
                LawRule(
                    stage=taxable_stage,
                    implementation_ref="tests.taxable_income_rule",
                    calculate=lambda facts: {"de.ordinary.taxable_income": facts["de.wages.gross.eur"]},
                ),
                LawRule(
                    stage=tariff_stage,
                    implementation_ref="tests.tariff_rule",
                    calculate=lambda facts: {
                        "de.ordinary.income_tax": facts["de.ordinary.taxable_income"] * Decimal("0.20")
                    },
                ),
            ),
        )

        self.assertIsInstance(execution, RuleGraphExecution)
        self.assertEqual(execution.final_facts["de.ordinary.income_tax"], Decimal("10000.0000"))
        self.assertEqual([result.stage_id for result in execution.stage_results], [
            "DE25-07-TAXABLE-INCOME",
            "DE25-08-BASIC-TARIFF",
        ])
        self.assertEqual(
            execution.stage_results[1].input_values["de.ordinary.taxable_income"],
            Decimal("50000.00"),
        )
        self.assertIn("de.ordinary.taxable_income", execution.stage_results[1].input_fingerprints)

        graph = execution.to_graph_dict()
        self.assertEqual(graph["nodes"][0]["rule_id"], "DE25-07-TAXABLE-INCOME")
        self.assertEqual(graph["nodes"][1]["implementation_ref"], "tests.tariff_rule")
        self.assertEqual(
            graph["nodes"][1]["input_values"]["de.ordinary.taxable_income"],
            Decimal("50000.00"),
        )
        self.assertEqual(graph["edges"][0]["from_output_key"], "de.ordinary.taxable_income")
        self.assertEqual(graph["edges"][0]["to_rule_id"], "DE25-08-BASIC-TARIFF")
        self.assertTrue(graph["nodes"][0]["output_fingerprints"]["de.ordinary.taxable_income"])

        with self.assertRaisesRegex(ValueError, "untracked output"):
            execute_rule_graph(
                {"de.wages.gross.eur": Decimal("50000.00")},
                (
                    LawRule(
                        stage=taxable_stage,
                        implementation_ref="tests.bad_rule",
                        calculate=lambda facts: {
                            "de.ordinary.taxable_income": facts["de.wages.gross.eur"],
                            "de.extra": Decimal("1.00"),
                        },
                    ),
                ),
            )

    def test_law_stage_requires_audit_metadata(self) -> None:
        stage = _stage()

        self.assertTrue(is_dataclass(stage))
        self.assertEqual(stage.stage_id, "DE25-TEST-TAXABLE-INCOME")
        self.assertEqual(stage.country_or_scope, "DE")
        self.assertEqual(stage.legal_refs, ("§ 2 Abs. 5 EStG",))
        self.assertEqual(stage.authority_urls, ("https://www.gesetze-im-internet.de/estg/__2.html",))
        self.assertEqual(stage.input_fact_keys, ("de.wages.gross.eur",))
        self.assertEqual(stage.output_keys, ("de.taxable_income.eur",))
        self.assertIn("Cent", stage.rounding_policy)
        self.assertIn("before", stage.law_order_note)
        self.assertEqual(stage.narrative_templates, {"en": "DE25-TEST-TAXABLE-INCOME"})
        self.assertEqual(stage.form_line_refs, ("ELSTER internal audit stage",))
        self.assertIn("§ 2 Abs. 5 EStG", stage.legal_formula)

        # The Phase C schema replaces the legacy ``output_keys`` /
        # ``form_line_refs`` constructor fields with a single ``outputs``
        # tuple. The construction-time validators reject blanks for every
        # remaining required field.
        required_fields = {
            "stage_id",
            "country_or_scope",
            "legal_refs",
            "authority_urls",
            "input_fact_keys",
            "outputs",
            "rounding_policy",
            "law_order_note",
            "legal_formula",
            "narrative_templates",
        }
        for field_name in required_fields:
            kwargs = {
                "stage_id": "DE25-TEST-TAXABLE-INCOME",
                "country_or_scope": "DE",
                "legal_refs": ("§ 2 Abs. 5 EStG",),
                "authority_urls": ("https://www.gesetze-im-internet.de/estg/__2.html",),
                "input_fact_keys": ("de.wages.gross.eur",),
                "outputs": (
                    OutputDeclaration(
                        key="de.taxable_income.eur",
                        form_line_refs=(FormLineRef(form="ELSTER", line="internal audit stage"),),
                    ),
                ),
                "rounding_policy": "Round only at declared boundaries.",
                "law_order_note": "Taxable income precedes tariff tax.",
                "legal_formula": "de.taxable_income.eur = de.wages.gross.eur per § 2 Abs. 5 EStG",
                "narrative_templates": {"en": "DE25-TEST-TAXABLE-INCOME"},
            }
            if field_name == "narrative_templates":
                kwargs[field_name] = {}
            elif field_name == "outputs":
                kwargs[field_name] = ()
            elif field_name.endswith("s") or field_name.endswith("keys"):
                kwargs[field_name] = ()
            else:
                kwargs[field_name] = " "
            with self.assertRaises(ValueError):
                LawStage(**kwargs)

    def test_stage_graph_validation_rejects_missing_inputs_duplicate_outputs_and_untracked_outputs(self) -> None:
        validate_law_stage_graph(
            [
                _stage(),
                _stage(
                    stage_id="DE25-TEST-TARIFF-TAX",
                    inputs=("de.taxable_income.eur",),
                    outputs=("de.tariff_tax.eur",),
                ),
            ],
            available_fact_keys={"de.wages.gross.eur"},
        )

        with self.assertRaisesRegex(ValueError, "missing input"):
            validate_law_stage_graph([_stage(inputs=("de.missing.eur",))], available_fact_keys={"de.wages.gross.eur"})

        with self.assertRaisesRegex(ValueError, "duplicate output"):
            validate_law_stage_graph(
                [
                    _stage(stage_id="DE25-TEST-FIRST", outputs=("de.taxable_income.eur",)),
                    _stage(stage_id="DE25-TEST-SECOND", outputs=("de.taxable_income.eur",)),
                ],
                available_fact_keys={"de.wages.gross.eur"},
            )

        result_with_extra_output = StageResult(
            stage_id="DE25-TEST-TAXABLE-INCOME",
            outputs={
                "de.taxable_income.eur": Decimal("40000.00"),
                "de.untracked.eur": Decimal("1.00"),
            },
            input_values={"de.wages.gross.eur": Decimal("50000.00")},
            input_fingerprints={"de.wages.gross.eur": "input-sha"},
            output_fingerprints={
                "de.taxable_income.eur": "output-sha",
                "de.untracked.eur": "extra-sha",
            },
            diagnostics=(),
            precision_notes={
                "de.taxable_income.eur": "Kept as cents for later tariff stage.",
                "de.untracked.eur": "This fixture should be rejected by graph validation.",
            },
        )
        with self.assertRaisesRegex(ValueError, "untracked output"):
            validate_law_stage_graph(
                [_stage()],
                available_fact_keys={"de.wages.gross.eur"},
                stage_results=[result_with_extra_output],
            )

    def test_stage_result_records_fingerprints_diagnostics_and_precision_notes(self) -> None:
        diagnostic = StageDiagnostic(
            severity="info",
            code="rounded-later",
            message="No rounding applied in this stage.",
        )
        result = StageResult(
            stage_id="DE25-TEST-TAXABLE-INCOME",
            outputs={"de.taxable_income.eur": Decimal("40000.00")},
            input_values={"de.wages.gross.eur": Decimal("50000.00")},
            input_fingerprints={"de.wages.gross.eur": "input-sha"},
            output_fingerprints={"de.taxable_income.eur": "output-sha"},
            diagnostics=(diagnostic,),
            precision_notes={"de.taxable_income.eur": "Kept as cents for later tariff stage."},
        )

        self.assertTrue(is_dataclass(result))
        self.assertEqual(result.outputs["de.taxable_income.eur"], Decimal("40000.00"))
        self.assertEqual(result.input_fingerprints["de.wages.gross.eur"], "input-sha")
        self.assertEqual(result.output_fingerprints["de.taxable_income.eur"], "output-sha")
        self.assertEqual(result.diagnostics[0].code, "rounded-later")
        self.assertIn("cents", result.precision_notes["de.taxable_income.eur"])

        with self.assertRaisesRegex(ValueError, "precision_notes"):
            StageResult(
                stage_id="DE25-TEST-TAXABLE-INCOME",
                outputs={"de.taxable_income.eur": Decimal("40000.00")},
                input_values={"de.wages.gross.eur": Decimal("50000.00")},
                input_fingerprints={"de.wages.gross.eur": "input-sha"},
                output_fingerprints={"de.taxable_income.eur": "output-sha"},
                diagnostics=(),
                precision_notes={},
            )

        with self.assertRaisesRegex(ValueError, "input_values"):
            StageResult(
                stage_id="DE25-TEST-TAXABLE-INCOME",
                outputs={"de.taxable_income.eur": Decimal("40000.00")},
                input_values={},
                input_fingerprints={"de.wages.gross.eur": "input-sha"},
                output_fingerprints={"de.taxable_income.eur": "output-sha"},
                diagnostics=(),
                precision_notes={"de.taxable_income.eur": "Kept as cents for later tariff stage."},
            )

    def test_pure_core_modules_do_not_use_file_io(self) -> None:
        forbidden = ("Path(", "open(", "read_text(", "write_text(", "read_bytes(", "write_bytes(")
        for module in (core_facts, core_stages):
            source = inspect.getsource(module)
            for token in forbidden:
                self.assertNotIn(token, source, module.__name__)

    def test_law_stage_legal_formula_rejects_auto_generated_input_key_concat(self) -> None:
        # ENGINE-SPEC.md "Math Steps": each rule must describe the legal formula
        # actually applied. The historical renderer auto-generated formulas as
        # `" + ".join(input_keys) + " -> " + " + ".join(output_keys)`, which
        # mis-stated the law (e.g. tariff splitting as addition). LawStage must
        # reject that exact shape at the schema level so it cannot return.
        with self.assertRaisesRegex(ValueError, "auto-generated"):
            LawStage(
                stage_id="DE25-TEST-AUTO-FORMULA",
                country_or_scope="DE",
                legal_refs=("§ 2 Abs. 5 EStG",),
                authority_urls=("https://www.gesetze-im-internet.de/estg/__2.html",),
                input_fact_keys=("de.wages.gross.eur",),
                outputs=(
                    OutputDeclaration(
                        key="de.taxable_income.eur",
                        form_line_refs=(FormLineRef(form="ELSTER", line="internal audit stage"),),
                    ),
                ),
                rounding_policy="Cent precision.",
                law_order_note="Taxable income precedes tariff tax.",
                legal_formula="de.wages.gross.eur -> de.taxable_income.eur",
                narrative_templates={"en": "DE25-TEST-AUTO-FORMULA"},
            )

    def test_executor_fails_closed_when_a_law_rule_calculate_raises(self) -> None:
        # The legal-execution graph is only auditable if every node is produced
        # by an actual ``LawRule.calculate`` invocation. Monkey-patching a
        # registered ``LawRule.calculate`` to raise must propagate the failure
        # rather than silently emitting a partial graph or stand-in zeros for
        # the failing stage's outputs.
        sabotage_msg = "sabotaged calculate must fail closed"

        def _raise(_facts):
            raise RuntimeError(sabotage_msg)

        good_stage = _stage(stage_id="DE25-07-TAXABLE-INCOME")
        bad_rule = LawRule(
            stage=good_stage,
            implementation_ref="tests.sabotaged_calculate",
            calculate=_raise,
        )
        with self.assertRaisesRegex(RuntimeError, sabotage_msg):
            execute_rule_graph(
                {"de.wages.gross.eur": Decimal("50000.00")},
                (bad_rule,),
            )

    def test_union_law_stage_graph_validates_with_documented_bridge_keys(self) -> None:
        # Cross-jurisdiction integrity: when DE25 + US25 + TREATY25 stages run
        # in the same pipeline, every stage's input_fact_keys must be either
        # produced by an upstream stage OR declared as a "bridge" fact stitched
        # in by the orchestrator (treaty_bridge_2025.py + per-scope
        # initial_facts_* helpers). The bridge keys listed below are the
        # current cross-border seam — when item 4 of the review punch list
        # promotes the bridge to a first-class LawStage, this test should
        # shrink (the bridge keys move from `bridge_initial_keys` to declared
        # outputs of a `BRIDGE25-*` stage).
        #
        # Authority for the seam: docs/law-coverage.md "Cross-jurisdiction
        # bridge keys" section.
        from tax_pipeline.y2025.germany_stages import (
            germany_capital_law_stages_2025,
            germany_ordinary_law_stages_2025,
        )
        from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
        from tax_pipeline.y2025.us_stages import usa_law_stages_2025

        union_stages = (
            *germany_ordinary_law_stages_2025(),
            *germany_capital_law_stages_2025(),
            *usa_law_stages_2025(),
            *treaty_law_stages_2025(),
        )

        # Initial-fact keys produced by each scope's loader (NOT by stages).
        de_ordinary_initial_keys = {
            "de.ordinary.raw_inputs",
            "de.profile.filing_posture",
            "de.profile.joint_assessment_prerequisites",
            "de.profile.separate_assessment_allocations",
            "de.ordinary.people",
            # § 18 / § 4 Abs. 3 EStG self-employment receipts/expenses —
            # initial facts assembled by germany_ordinary_initial_facts_2025
            # (zero for a wage earner), consumed by DE25-EUER.
            "de.ordinary.business_receipts_eur",
            "de.ordinary.business_expenses_eur",
            # § 10 Abs. 1 Nr. 2/3/3a EStG self-employed Vorsorge by slot —
            # initial fact (empty mapping for a wage earner), consumed by
            # DE25-05-RETIREMENT-SA / DE25-06-HEALTH-VORSORGE-SA.
            "de.ordinary.se_vorsorge_by_slot",
            "de.ordinary.other_income_22nr3",
            "de.ordinary.other_income_22nr3_threshold",
            "de.ordinary.other_income_22nr3_by_person",
            "de.ordinary.prepayments",
            "de.ordinary.prepayments_by_person",
            "de.constants.worker_allowance_per_person",
            "de.constants.sonderausgaben_pauschbetrag_joint",
            "de.constants.sonderausgaben_pauschbetrag_single",
            "de.constants.altersentlastungsbetrag_tax_year",
            "de.constants.unterhaltsleistungen_grundfreibetrag",
            # Gap 2 — § 33b Abs. 5 EStG transferral total. Pipeline 1
            # derivation (DERIVE-DE25-CHILDREN) supplies the value;
            # ``germany_ordinary_initial_facts_2025`` threads it onto the
            # ordinary initial facts so DE25-BEHINDERUNG-PAUSCHBETRAG can
            # add it to the parents' household total. Treated as an
            # initial key for the union-graph validation because it is
            # produced by Pipeline 1, not by a Pipeline 2 stage.
            # https://www.gesetze-im-internet.de/estg/__33b.html
            "de.derived.children_disability_pauschbetrag_total_eur",
            # Gap 2 deferred — § 33b Abs. 5 Satz 3 EStG joint-election
            # split override. Sourced from
            # ``elections.germany_disability_pauschbetrag_transfer_split``
            # in profile.json (Anlage Kind 2025 Zeile 66). ``None`` selects
            # the statutory 50/50 default. Threaded onto the ordinary
            # initial facts by ``germany_ordinary_initial_facts_2025``;
            # consumed by DE25-BEHINDERUNG-PAUSCHBETRAG.
            # https://www.gesetze-im-internet.de/estg/__33b.html
            "de.profile.disability_pauschbetrag_transfer_split",
        }
        de_capital_initial_keys = {
            "de.capital.sale_facts",
            "de.capital.income_facts",
            "de.capital.bank_certificates",
            "de.capital.treaty_dividend_items",
            "de.capital.fund_classification",
            "de.capital.fund_teilfreistellung_rates",
            "de.capital.dher_stock_gain",
            "de.capital.stock_loss_carryforward_2024",
            "de.capital.saver_allowance",
            "de.capital.other_spouse_capital_before_allowance",
            "de.capital.capital_tax_rate",
            "de.capital.soli_rate",
            "de.capital.treaty_dividend_credit",
            # WS-5A (invariant migration plan §7): the five DE25-13
            # derivations now live as Pipeline 1 stages
            # (DERIVE-DE25-13A through 13E). Their outputs land in the
            # capital initial facts via the Pipeline 1 splice in
            # ``germany_capital_initial_facts_2025`` — so the union-graph
            # validation must treat them as "available initial keys".
            "de.derived.per_symbol_sale_aggregation",
            "de.derived.box_1a_filtered_dividends",
            "de.derived.per_symbol_bank_certificate_buckets",
            "de.derived.source_country_classification",
            "de.derived.foreign_tax_indexing",
            # InvStG § 19 Vorabpauschale per-fund inputs land here from
            # the Pipeline 1 derivation DERIVE-DE25-13F. The Basiszinssatz
            # (2.53 % for 2025) and the 0.7 statutory factor live in
            # germany_2025_law.py and arrive on the capital initial facts.
            # https://www.gesetze-im-internet.de/invstg_2018/__19.html
            "de.derived.vorabpauschale_inputs",
            "de.capital.basiszins",
            "de.capital.vorabpauschale_basisertrag_factor",
        }
        us_initial_keys = {
            "us.assessment.inputs",
            "us.profile.filing_posture",
            "us.profile.elections",
            "us.reference.constants",
            "us.fx.eur_per_usd",
            "us.wages.eur",
            "us.capital.income_facts",
            "us.capital.sale_facts",
            "us.capital.section_1256_facts",
            "us.constants.capital_loss_limit",
            "us.constants.standard_deduction",
            "us.capital.qualified_dividends",
            "us.ftc.foreign_preferential_income",
            "us.ftc.category_gross_income",
            "us.ftc.current_foreign_tax",
            "us.ftc.carryovers",
            "us.treaty.dividend_source_split",
            "us.payments.estimated",
        }
        # Bridge keys: produced by treaty_bridge_2025.py and the per-scope
        # initial_facts helpers, NOT by any LawStage. Item 4 of the review
        # punch list promotes the bridge to a stage; until that lands, these
        # are the documented seam.
        bridge_initial_keys = {
            "de.stage.us_source_dividend_tax_and_credit",
            "de.treaty.us_source_dividend_tax_and_credit",
            "us.treaty.inputs",
            "treaty.dividend_split",
            "us.constants.treaty_dividend_rate",
            "us.stage.regular_tax_after_ftc",
            "us.stage.remaining_form_1116_line_33_cap",
        }

        available = (
            de_ordinary_initial_keys
            | de_capital_initial_keys
            | us_initial_keys
            | bridge_initial_keys
        )

        # validate_law_stage_graph raises ValueError on missing inputs;
        # passing means every cross-border key is accounted for.
        validation = validate_law_stage_graph(
            union_stages,
            available_fact_keys=available,
        )
        # 12 + 10 + 29 + 5 = 56 stages. DE25-13F-VORABPAUSCHALE covers
        # InvStG § 19 deemed-distribution (gap #9 in
        # ``.review/2026-05-01-legal-flow/germany-legal-flow.md``); the
        # 29 US stages add US25-FEIE (§ 911 Form 2555, a085717),
        # US25-AMT-AMTI / US25-AMT-TENTATIVE / US25-AMT-FTC-AND-COMPARE
        # (§ 55 Form 6251, 2f99526), and US25-SE-TAX / US25-ADDITIONAL-MEDICARE
        # (§ 1401 / § 3101 Form 8959, 3434872) atop the prior 23-stage US
        # graph; the 5 treaty stages add TREATY25-LOB-QUALIFICATION (DBA-USA
        # Art. 28 LOB gate, 564ae1f) atop the 4 Pub. 514 worksheet stages.
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        # https://www.law.cornell.edu/uscode/text/26/55
        # https://www.law.cornell.edu/uscode/text/26/911
        # https://www.law.cornell.edu/uscode/text/26/1401
        # https://www.irs.gov/pub/irs-trty/germany.pdf
        # +6 stages: DE25-ALTERSENTLASTUNGSBETRAG (§ 24a EStG),
        # DE25-ARBEITSZIMMER (§ 4 Abs. 5 Satz 1 Nr. 6b EStG),
        # DE25-SPENDENABZUG (§ 10b EStG),
        # DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN (§ 33 EStG),
        # DE25-UNTERHALTSLEISTUNGEN (§ 33a EStG),
        # DE25-BEHINDERUNG-PAUSCHBETRAG (§ 33b EStG) (gaps from
        # .review/2026-05-01-legal-flow/germany-legal-flow.md).
        # https://www.gesetze-im-internet.de/estg/__24a.html
        # https://www.gesetze-im-internet.de/estg/__4.html
        # https://www.gesetze-im-internet.de/estg/__10b.html
        # https://www.gesetze-im-internet.de/estg/__33.html
        # https://www.gesetze-im-internet.de/estg/__33a.html
        # https://www.gesetze-im-internet.de/estg/__33b.html
        # 63 = 62 prior stages + US25-CTC-AND-ODC (26 U.S.C. § 24 + § 152).
        # https://www.law.cornell.edu/uscode/text/26/24
        # https://www.law.cornell.edu/uscode/text/26/152
        # 64 = 63 + US25-FATCA-FBAR-DETERMINATION (26 U.S.C. § 6038D /
        # 31 CFR § 1010.350) added by Group D (FORM-MAPPING-FOLLOWUP,
        # 2026-05-03). Determination-only — does not feed any
        # downstream tax stage.
        # https://www.law.cornell.edu/uscode/text/26/6038D
        # https://www.law.cornell.edu/cfr/text/31/1010.350
        # 65 = 64 + DE25-EUER (§ 18 / § 4 Abs. 3 EStG selbständige Arbeit
        # EÜR profit) added by Phase 1 freelancer support
        # (FREELANCER-DE-EUER-SLICE-SPEC.md). Feeds DE25-07 taxable income.
        # https://www.gesetze-im-internet.de/estg/__18.html
        # https://www.gesetze-im-internet.de/estg/__4.html
        # 67 = 65 + US25-02A-SCHEDULE-C (26 U.S.C. § 61 / § 162 Schedule C
        # net profit) + US25-08A-QBI-GATE (26 U.S.C. § 199A(c)(3)(A)(i) /
        # § 864(c) QBI applicability gate — not_applicable for foreign-source
        # business income) added by Phase 2 freelancer support
        # (FREELANCER-US-SCHEDULE-C-SLICE-SPEC.md). US25-02A feeds the income
        # side (Schedule 1 line 3 → AGI) and the SE-tax base; US25-08A
        # adjudicates § 199A (grants zero for foreign source).
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A
        self.assertEqual(len(validation.stage_ids), 67)

    def test_union_law_stage_graph_fails_when_bridge_keys_are_omitted(self) -> None:
        # Counterpart: removing the bridge keys MUST surface as a missing-input
        # error during validation. This pins the bridge as a real cross-border
        # contract — accidentally removing the orchestrator stitching would
        # break the union graph at startup, not silently at runtime.
        from tax_pipeline.y2025.germany_stages import (
            germany_capital_law_stages_2025,
            germany_ordinary_law_stages_2025,
        )
        from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
        from tax_pipeline.y2025.us_stages import usa_law_stages_2025

        union_stages = (
            *germany_ordinary_law_stages_2025(),
            *germany_capital_law_stages_2025(),
            *usa_law_stages_2025(),
            *treaty_law_stages_2025(),
        )
        # Provide all initial keys EXCEPT the bridge keys. Validation must
        # raise on the first stage that depends on a missing bridge key.
        de_ordinary_initial_keys = {
            "de.ordinary.raw_inputs",
            "de.profile.filing_posture",
            "de.profile.joint_assessment_prerequisites",
            "de.profile.separate_assessment_allocations",
            "de.ordinary.people",
            # § 18 / § 4 Abs. 3 EStG self-employment receipts/expenses —
            # initial facts assembled by germany_ordinary_initial_facts_2025
            # (zero for a wage earner), consumed by DE25-EUER.
            "de.ordinary.business_receipts_eur",
            "de.ordinary.business_expenses_eur",
            # § 10 Abs. 1 Nr. 2/3/3a EStG self-employed Vorsorge by slot —
            # initial fact (empty mapping for a wage earner), consumed by
            # DE25-05-RETIREMENT-SA / DE25-06-HEALTH-VORSORGE-SA.
            "de.ordinary.se_vorsorge_by_slot",
            "de.ordinary.other_income_22nr3",
            "de.ordinary.other_income_22nr3_threshold",
            "de.ordinary.other_income_22nr3_by_person",
            "de.ordinary.prepayments",
            "de.ordinary.prepayments_by_person",
            "de.constants.worker_allowance_per_person",
            "de.constants.sonderausgaben_pauschbetrag_joint",
            "de.constants.sonderausgaben_pauschbetrag_single",
            "de.constants.altersentlastungsbetrag_tax_year",
            "de.constants.unterhaltsleistungen_grundfreibetrag",
            # Gap 2 — § 33b Abs. 5 EStG transferral total. Pipeline 1
            # derivation (DERIVE-DE25-CHILDREN) supplies the value;
            # ``germany_ordinary_initial_facts_2025`` threads it onto the
            # ordinary initial facts so DE25-BEHINDERUNG-PAUSCHBETRAG can
            # add it to the parents' household total. Treated as an
            # initial key for the union-graph validation because it is
            # produced by Pipeline 1, not by a Pipeline 2 stage.
            # https://www.gesetze-im-internet.de/estg/__33b.html
            "de.derived.children_disability_pauschbetrag_total_eur",
            # Gap 2 deferred — § 33b Abs. 5 Satz 3 EStG joint-election
            # split override. Sourced from
            # ``elections.germany_disability_pauschbetrag_transfer_split``
            # in profile.json (Anlage Kind 2025 Zeile 66). ``None`` selects
            # the statutory 50/50 default. Threaded onto the ordinary
            # initial facts by ``germany_ordinary_initial_facts_2025``;
            # consumed by DE25-BEHINDERUNG-PAUSCHBETRAG.
            # https://www.gesetze-im-internet.de/estg/__33b.html
            "de.profile.disability_pauschbetrag_transfer_split",
        }
        de_capital_initial_keys = {
            "de.capital.sale_facts",
            "de.capital.income_facts",
            "de.capital.bank_certificates",
            "de.capital.treaty_dividend_items",
            "de.capital.fund_classification",
            "de.capital.fund_teilfreistellung_rates",
            "de.capital.dher_stock_gain",
            "de.capital.stock_loss_carryforward_2024",
            "de.capital.saver_allowance",
            "de.capital.other_spouse_capital_before_allowance",
            "de.capital.capital_tax_rate",
            "de.capital.soli_rate",
            "de.capital.treaty_dividend_credit",
            # WS-5A (invariant migration plan §7): the five DE25-13
            # derivations now live as Pipeline 1 stages
            # (DERIVE-DE25-13A through 13E). Their outputs land in the
            # capital initial facts via the Pipeline 1 splice in
            # ``germany_capital_initial_facts_2025`` — so the union-graph
            # validation must treat them as "available initial keys".
            "de.derived.per_symbol_sale_aggregation",
            "de.derived.box_1a_filtered_dividends",
            "de.derived.per_symbol_bank_certificate_buckets",
            "de.derived.source_country_classification",
            "de.derived.foreign_tax_indexing",
            # InvStG § 19 Vorabpauschale per-fund inputs land here from
            # the Pipeline 1 derivation DERIVE-DE25-13F. The Basiszinssatz
            # (2.53 % for 2025) and the 0.7 statutory factor live in
            # germany_2025_law.py and arrive on the capital initial facts.
            # https://www.gesetze-im-internet.de/invstg_2018/__19.html
            "de.derived.vorabpauschale_inputs",
            "de.capital.basiszins",
            "de.capital.vorabpauschale_basisertrag_factor",
        }
        us_initial_keys = {
            "us.assessment.inputs",
            "us.profile.filing_posture",
            "us.profile.elections",
            "us.reference.constants",
            "us.fx.eur_per_usd",
            "us.wages.eur",
            "us.capital.income_facts",
            "us.capital.sale_facts",
            "us.capital.section_1256_facts",
            "us.constants.capital_loss_limit",
            "us.constants.standard_deduction",
            "us.capital.qualified_dividends",
            "us.ftc.foreign_preferential_income",
            "us.ftc.category_gross_income",
            "us.ftc.current_foreign_tax",
            "us.ftc.carryovers",
            "us.treaty.dividend_source_split",
            "us.payments.estimated",
        }
        with self.assertRaisesRegex(ValueError, "missing input"):
            validate_law_stage_graph(
                union_stages,
                available_fact_keys=(
                    de_ordinary_initial_keys
                    | de_capital_initial_keys
                    | us_initial_keys
                ),
            )

    def test_every_declared_law_stage_has_a_real_legal_formula(self) -> None:
        # Every stage in every jurisdiction/posture variant must carry a
        # legal_formula that is not the auto-generated input-key concatenation.
        # This is the scope check that complements the LawStage __post_init__
        # rejection above.
        from tax_pipeline.y2025.germany_stages import (
            germany_capital_law_stages_2025,
            germany_ordinary_law_stages_2025,
        )
        from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
        from tax_pipeline.y2025.us_stages import usa_law_stages_2025

        all_stages = (
            *germany_ordinary_law_stages_2025(),
            *germany_capital_law_stages_2025(),
            *usa_law_stages_2025(),
            *treaty_law_stages_2025(),
        )
        for stage in all_stages:
            with self.subTest(stage_id=stage.stage_id):
                auto = " + ".join(stage.input_fact_keys) + " -> " + " + ".join(stage.output_keys)
                self.assertNotEqual(stage.legal_formula, auto)
                self.assertTrue(stage.legal_formula.strip())


if __name__ == "__main__":
    unittest.main()
