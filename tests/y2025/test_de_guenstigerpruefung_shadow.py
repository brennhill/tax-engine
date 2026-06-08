"""Tests for the audit-only § 32d Abs. 6 EStG Günstigerprüfung shadow
comparison (F-DE-2 / DE25-GUENSTIGERPRUEFUNG-SHADOW).

§ 32d Abs. 6 EStG (Antragsveranlagung) lets the taxpayer elect to apply
the ordinary § 32a tariff to capital income when it produces a lower
total tax than the § 32d Abs. 1 flat 25 %. The 2025 engine fails closed
when ``capital_guenstigerpruefung_requested=1`` (the election is not yet
implemented). F-DE-2 adds an audit-only shadow stage that runs
unconditionally and surfaces a recommendation when the election would
benefit the taxpayer.

Authority:

- § 32d Abs. 6 EStG (the election):
  https://www.gesetze-im-internet.de/estg/__32d.html
- § 32d Abs. 1 EStG (the 25 % flat tax this election competes against):
  https://www.gesetze-im-internet.de/estg/__32d.html
- § 32a Abs. 1 EStG (basic ordinary tariff):
  https://www.gesetze-im-internet.de/estg/__32a.html
- § 32a Abs. 5 EStG (joint splitting tariff): same URL.
- § 32d Abs. 5 EStG (foreign-tax credit; carries through under the
  election): https://www.gesetze-im-internet.de/estg/__32d.html
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.y2025.germany_law import (
    GUENSTIGERPRUEFUNG_MATERIALITY_EUR,
    german_income_tax_split_2025,
)
from tax_pipeline.y2025.germany_stages import (
    germany_guenstigerpruefung_law_stages_2025,
)
from tax_pipeline.y2025.germany_guenstigerpruefung_rules import (
    DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID,
    de25_guenstigerpruefung_shadow,
    execute_germany_guenstigerpruefung_rule_graph,
    germany_guenstigerpruefung_initial_facts_2025,
    germany_guenstigerpruefung_initial_fingerprints_2025,
    germany_guenstigerpruefung_law_rules_2025,
)


D = Decimal


class GuenstigerpruefungLowBracketTest(unittest.TestCase):
    """§ 32d Abs. 6 EStG: low-bracket joint household.

    A household with €15,000 joint zvE and €5,000 capital income (no
    foreign tax) is in the Grundfreibetrag (§ 32a Abs. 1 EStG, splitting
    grants €24,192 = 2 × €12,096). Adding €5,000 of capital still keeps
    the combined zvE under the bracket where § 32a tax materially
    exceeds 25 %. The election should be recommended because the
    taxpayer pays €1,250 (25 % of €5,000) under § 32d Abs. 1 but
    essentially €0 under § 32a.
    """

    def test_low_bracket_election_is_recommended(self) -> None:
        # § 32a Abs. 5 EStG splitting tariff: zvE 15000 joint, capital
        # 5000 → combined 20000 split base 10000 → still under
        # Grundfreibetrag (12096) → tariff = 0. Status quo is 25 % flat
        # = 1250. Diff = 1250 → election recommended.
        # https://www.gesetze-im-internet.de/estg/__32d.html
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("15000.00"),
            capital_taxable_after_teilfreistellung_eur=D("5000.00"),
            status_quo_total_tax_eur=D("1250.00"),
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        result = de25_guenstigerpruefung_shadow(facts)
        diff = result["de.audit.guenstigerpruefung_shadow_diff_eur"]
        recommended = result["de.audit.guenstigerpruefung_election_recommended"]
        # § 32d Abs. 6 EStG: the diff must be positive (election would
        # save tax) and at least €100 to satisfy the spec's low-bracket
        # acceptance criterion.
        self.assertGreaterEqual(diff, D("100.00"))
        # Election recommended (boolean-flag Decimal).
        self.assertEqual(recommended, D("1"))

    def test_low_bracket_diff_equals_status_quo_when_combined_under_grundfreibetrag(
        self,
    ) -> None:
        # § 32a Abs. 1 / Abs. 5 EStG: when the combined zvE + capital
        # base is fully inside the Grundfreibetrag, the shadow ordinary
        # tariff is 0, so the entire status-quo capital tax is the diff.
        # This is the pure low-bracket case.
        zve = D("10000.00")
        capital = D("3000.00")
        status_quo = D("750.00")  # 25 % of capital
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=zve,
            capital_taxable_after_teilfreistellung_eur=capital,
            status_quo_total_tax_eur=status_quo,
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        result = de25_guenstigerpruefung_shadow(facts)
        self.assertEqual(
            result["de.audit.guenstigerpruefung_shadow_diff_eur"],
            status_quo,
        )
        self.assertEqual(
            result["de.audit.guenstigerpruefung_election_recommended"],
            D("1"),
        )


class GuenstigerpruefungHighBracketTest(unittest.TestCase):
    """§ 32d Abs. 6 EStG: high-bracket joint household — election worse.

    A household with €100,000 joint zvE is in § 32a Abs. 1 zone 2
    (progressive). Adding €10,000 of capital pushes the marginal rate
    well above 25 %, so the § 32a tariff path collects more capital tax
    than § 32d Abs. 1's flat 25 %. The shadow must NOT recommend the
    election (diff is negative or near-zero).
    """

    def test_high_bracket_election_is_not_recommended(self) -> None:
        # § 32a Abs. 5 EStG splitting: zvE 100000, capital 10000 →
        # combined 110000, marginal rate well above 25 %. Status quo
        # 2500 (25 % flat) is clearly lower than § 32a path.
        # https://www.gesetze-im-internet.de/estg/__32d.html
        # https://www.gesetze-im-internet.de/estg/__32a.html
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("100000.00"),
            capital_taxable_after_teilfreistellung_eur=D("10000.00"),
            status_quo_total_tax_eur=D("2500.00"),
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        result = de25_guenstigerpruefung_shadow(facts)
        diff = result["de.audit.guenstigerpruefung_shadow_diff_eur"]
        recommended = result["de.audit.guenstigerpruefung_election_recommended"]
        # § 32a path collects more tax than § 32d Abs. 1 → diff is
        # negative (election would COST the taxpayer).
        self.assertLess(diff, D("0.00"))
        # Election not recommended.
        self.assertEqual(recommended, D("0"))


class GuenstigerpruefungThresholdTest(unittest.TestCase):
    """§ 32d Abs. 6 EStG / project materiality: near-tie scenarios must
    NOT cross the recommendation threshold.

    Materiality is project-internal at €10 (see
    ``GUENSTIGERPRUEFUNG_MATERIALITY_EUR``) — diffs below this are
    rounding artifacts and do not constitute an actionable filing
    recommendation under § 32d Abs. 6 EStG.
    """

    def test_diff_at_threshold_is_not_recommended(self) -> None:
        # § 32d Abs. 6 EStG threshold: a diff exactly equal to €10
        # must NOT be recommended (strict > comparison).
        # We construct a synthetic scenario where the diff lands at
        # exactly €10 by computing what status-quo would equal the
        # shadow path + €10. This stresses the strict-inequality
        # boundary in the rule body.
        zve = D("60000.00")
        capital = D("4000.00")
        # § 32a Abs. 5 EStG splitting tariff at the configured zvE.
        ordinary_only = german_income_tax_split_2025(zve)
        combined = german_income_tax_split_2025(zve + capital)
        shadow_increment = combined - ordinary_only  # no FTC
        # Set status_quo so diff = exactly €10.
        status_quo = shadow_increment + GUENSTIGERPRUEFUNG_MATERIALITY_EUR
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=zve,
            capital_taxable_after_teilfreistellung_eur=capital,
            status_quo_total_tax_eur=status_quo,
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        result = de25_guenstigerpruefung_shadow(facts)
        diff = result["de.audit.guenstigerpruefung_shadow_diff_eur"]
        recommended = result["de.audit.guenstigerpruefung_election_recommended"]
        # diff == GUENSTIGERPRUEFUNG_MATERIALITY_EUR (€10), strict > test
        # ⇒ NOT recommended.
        self.assertEqual(diff, GUENSTIGERPRUEFUNG_MATERIALITY_EUR)
        self.assertEqual(recommended, D("0"))

    def test_diff_just_above_threshold_is_recommended(self) -> None:
        # § 32d Abs. 6 EStG threshold: a diff just above €10 must be
        # recommended.
        zve = D("60000.00")
        capital = D("4000.00")
        ordinary_only = german_income_tax_split_2025(zve)
        combined = german_income_tax_split_2025(zve + capital)
        shadow_increment = combined - ordinary_only
        status_quo = shadow_increment + GUENSTIGERPRUEFUNG_MATERIALITY_EUR + D("0.01")
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=zve,
            capital_taxable_after_teilfreistellung_eur=capital,
            status_quo_total_tax_eur=status_quo,
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        result = de25_guenstigerpruefung_shadow(facts)
        diff = result["de.audit.guenstigerpruefung_shadow_diff_eur"]
        recommended = result["de.audit.guenstigerpruefung_election_recommended"]
        self.assertEqual(diff, GUENSTIGERPRUEFUNG_MATERIALITY_EUR + D("0.01"))
        self.assertEqual(recommended, D("1"))


class GuenstigerpruefungStageDeclarationTest(unittest.TestCase):
    """The shadow stage's input/output declarations must satisfy the
    structural invariants I7 (rules read only declared input_fact_keys)
    and I8 (rules write only declared output_keys).
    """

    def test_declared_input_keys_match_rule_facts_consumed(self) -> None:
        # I7: the rule body only reads keys that appear in the stage's
        # ``input_fact_keys``. Verified at runtime by execute_rule_graph;
        # this test pins the contract by direct inspection.
        stages = germany_guenstigerpruefung_law_stages_2025()
        self.assertEqual(len(stages), 1)
        stage = stages[0]
        self.assertEqual(stage.stage_id, DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID)
        # Every declared input must be a key the rule reads.
        expected_inputs = {
            "de.audit.guenstiger.zve_ordinary_eur",
            "de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur",
            "de.audit.guenstiger.status_quo_total_tax_eur",
            "de.audit.guenstiger.foreign_tax_credit_applied_eur",
            "de.audit.guenstiger.filing_posture",
        }
        self.assertEqual(set(stage.input_fact_keys), expected_inputs)

    def test_declared_output_keys_match_rule_emitted(self) -> None:
        # I8: the rule body returns exactly the declared output keys.
        # validate_result enforces this at runtime; this test pins the
        # contract by direct inspection.
        stages = germany_guenstigerpruefung_law_stages_2025()
        stage = stages[0]
        expected_outputs = {
            "de.audit.guenstigerpruefung_shadow_diff_eur",
            "de.audit.guenstigerpruefung_election_recommended",
        }
        self.assertEqual(set(stage.output_keys), expected_outputs)

    def test_full_rule_graph_execution_matches_declarations(self) -> None:
        # Drive the full executor path: this exercises the I7/I8
        # tracking guards in execute_rule_graph end-to-end.
        # Authority: § 32d Abs. 6 EStG.
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("15000.00"),
            capital_taxable_after_teilfreistellung_eur=D("5000.00"),
            status_quo_total_tax_eur=D("1250.00"),
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        execution = execute_germany_guenstigerpruefung_rule_graph(
            facts,
            input_fingerprints=germany_guenstigerpruefung_initial_fingerprints_2025(
                facts
            ),
        )
        # Final facts contain only the declared outputs (plus the
        # initial facts that were threaded through).
        for key in (
            "de.audit.guenstigerpruefung_shadow_diff_eur",
            "de.audit.guenstigerpruefung_election_recommended",
        ):
            self.assertIn(key, execution.final_facts)

    def test_output_keys_use_audit_namespace(self) -> None:
        # The outputs must live under ``de.audit.*`` so they cannot be
        # mistaken for ``de.final.*`` values that feed the refund. The
        # boundary requirement from F-DE-2 spec.
        stages = germany_guenstigerpruefung_law_stages_2025()
        stage = stages[0]
        for key in stage.output_keys:
            self.assertTrue(
                key.startswith("de.audit."),
                f"Audit-only output {key} must live under de.audit.* namespace",
            )

    def test_law_rules_factory_returns_one_rule_for_one_stage(self) -> None:
        # Sanity check: the rule factory pairs the stage with a
        # calculate function.
        rules = germany_guenstigerpruefung_law_rules_2025()
        self.assertEqual(len(rules), 1)
        rule = rules[0]
        self.assertEqual(rule.stage.stage_id, DE25_GUENSTIGERPRUEFUNG_SHADOW_STAGE_ID)


class GuenstigerpruefungForeignTaxCreditTest(unittest.TestCase):
    """§ 32d Abs. 5 EStG: the foreign-tax credit reads through under the
    § 32d Abs. 6 election. The shadow path must subtract the already-
    applied FTC from the shadow ordinary-tariff increase, otherwise it
    would double-tax the foreign-source dividends.
    """

    def test_foreign_tax_credit_reduces_shadow_capital_increment(self) -> None:
        # § 32d Abs. 5 EStG: with €500 of FTC applied under the status
        # quo, the shadow path's incremental ordinary tax on capital
        # must be reduced by €500. This makes the election more
        # favorable than it would appear without the credit read-through.
        # Authority: https://www.gesetze-im-internet.de/estg/__32d.html
        facts_no_ftc = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("60000.00"),
            capital_taxable_after_teilfreistellung_eur=D("4000.00"),
            status_quo_total_tax_eur=D("1000.00"),
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="married_joint",
        )
        facts_with_ftc = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("60000.00"),
            capital_taxable_after_teilfreistellung_eur=D("4000.00"),
            status_quo_total_tax_eur=D("1000.00"),
            foreign_tax_credit_applied_eur=D("500.00"),
            filing_posture="married_joint",
        )
        diff_no_ftc = de25_guenstigerpruefung_shadow(facts_no_ftc)[
            "de.audit.guenstigerpruefung_shadow_diff_eur"
        ]
        diff_with_ftc = de25_guenstigerpruefung_shadow(facts_with_ftc)[
            "de.audit.guenstigerpruefung_shadow_diff_eur"
        ]
        # The FTC reduces the shadow ordinary-tariff increase, so the
        # diff is LARGER (more favorable to the election) when the FTC
        # is present.
        self.assertGreater(diff_with_ftc, diff_no_ftc)


class GuenstigerpruefungUnsupportedPostureTest(unittest.TestCase):
    """§ 32a EStG only models single / married_joint / married_separate
    postures in 2025; an unknown filing posture must fail closed rather
    than silently picking a tariff variant.
    """

    def test_unsupported_filing_posture_fails_closed(self) -> None:
        # § 32a Abs. 1 / Abs. 5 EStG: only documented postures are
        # supported; CLAUDE.md requires fail-closed on missing legal
        # configuration.
        facts = germany_guenstigerpruefung_initial_facts_2025(
            zve_ordinary_eur=D("15000.00"),
            capital_taxable_after_teilfreistellung_eur=D("5000.00"),
            status_quo_total_tax_eur=D("1250.00"),
            foreign_tax_credit_applied_eur=D("0.00"),
            filing_posture="some_unknown_posture",
        )
        with self.assertRaisesRegex(ValueError, r"§ 32d Abs\. 6 Günstigerprüfung"):
            de25_guenstigerpruefung_shadow(facts)


if __name__ == "__main__":
    unittest.main()
