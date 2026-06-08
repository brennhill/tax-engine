"""Precision and determinism tests for Germany capital rule graph.

Covers four code-correctness bugs:
  - C1: saver-allowance allocation precision mismatch in
    ``de25_16_section_20_9_saver`` / ``_taxable_capital_item_after_saver_allowance_2025``
    (§ 20 Abs. 9 EStG, https://www.gesetze-im-internet.de/estg/__20.html;
    § 32d Abs. 5 EStG, https://www.gesetze-im-internet.de/estg/__32d.html).
  - C18: per-item allowance share precision pinning at sub-cent boundaries
    (§ 20 Abs. 9 EStG; § 32d Abs. 5 EStG).
  - C16: ``frozenset`` iteration order leaking into dict insertion order in
    ``de25_14_fund_teilfreistellung`` (InvStG § 20,
    https://www.gesetze-im-internet.de/invstg_2018/__20.html).
  - C7: ``repr(dict)`` fingerprint nondeterminism for Mapping facts in
    ``germany_capital_initial_fingerprints_2025`` and ``us_initial_fingerprints_2025``.
"""

from __future__ import annotations

import os
import sys
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.y2025.germany_law import (
    GermanyCapitalAssessmentInputs2025,
    _taxable_capital_item_after_saver_allowance_2025,
    q2,
)
from tax_pipeline.y2025.germany_capital_rules import (
    de25_14_fund_teilfreistellung,
    de25_16_section_20_9_saver,
    germany_capital_initial_facts_2025,
    germany_capital_initial_fingerprints_2025,
)
from tax_pipeline.y2025.us_rules import us_initial_fingerprints_2025


D = Decimal


class SaverAllowanceAllocationPrecisionTest(unittest.TestCase):
    """C1 + C18: Allocation must use a q2-quantized total taxable before allowance.

    Authority: § 20 Abs. 9 EStG (Sparer-Pauschbetrag) and § 32d Abs. 5 EStG
    (per-item foreign-tax credit cap), Gesetze im Internet:
    https://www.gesetze-im-internet.de/estg/__20.html and
    https://www.gesetze-im-internet.de/estg/__32d.html.
    """

    def test_de25_16_emits_quantized_total_taxable_before_allowance(self) -> None:
        # Mirror the data shapes the rule expects, using values whose unrounded
        # sum produces sub-cent residue. Each symbol's pre-allowance amount is
        # itself q2-quantized at later call sites (y2025/germany_capital_rules.py
        # lines 603, 712-715), so the total must also be q2 to keep the
        # downstream ratio item / total in a single precision domain.
        # Choose three symbols with un-q2 components that sum to a value with
        # >2 fractional digits, so the q2 path differs from raw sum.
        netting = {
            "taxable_by_symbol_before_allowance": {
                "A": D("100.001"),
                "B": D("100.002"),
                "C": D("100.003"),
            },
            "stock_gain_after_carryforward": D("0.00"),
            "foreign_tax_by_item": {},
            "foreign_tax_refund_by_item": {},
            "foreign_taxable_item_by_key_before_allowance": {},
        }
        raw_buckets = {
            "fund_gain": D("0.00"),
            "option_gain": D("0.00"),
            "positive_income_total": D("300.006"),
            "non_fund_positive_income_total": D("300.006"),
        }
        fund_after = {
            "fund_taxable_after_teilfreistellung": D("0.00"),
        }
        facts = {
            "de.capital.after_section_20_6_netting": netting,
            "de.capital.raw_buckets": raw_buckets,
            "de.capital.fund_after_teilfreistellung": fund_after,
            "de.capital.saver_allowance": D("1000.00"),
            "de.capital.other_spouse_capital_before_allowance": None,
            # InvStG § 19 Vorabpauschale is a declared input of DE25-16; the
            # saver-allowance precision pin uses no Vorabpauschale so the
            # allocation maths exercises only the per-symbol totals.
            # https://www.gesetze-im-internet.de/invstg_2018/__19.html
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": D("0.00"),
        }
        result = de25_16_section_20_9_saver(facts)
        total = result["de.capital.taxable_after_allowance"]["total_taxable_before_allowance"]
        # The sum of the three symbol values is 300.006; q2 must give 300.01.
        self.assertEqual(total, D("300.01"))
        # And the value is q2-shaped (exactly two fractional digits).
        self.assertEqual(total, q2(total))

    def test_de25_16_total_drives_allocation_consistent_with_q2_path(self) -> None:
        # End-to-end pin: with three pre-allowance values whose un-q2 sum is
        # 300.006 (q2 -> 300.01) and a partial saver allowance of 100.00 EUR,
        # the per-item allocation must match what the q2-quantized total
        # produces. Before C1 is fixed the rule emits the unquantized 300.006
        # in ``total_taxable_before_allowance``; after the fix it emits 300.01.
        netting = {
            "taxable_by_symbol_before_allowance": {
                "A": D("100.001"),
                "B": D("100.002"),
                "C": D("100.003"),
            },
            "stock_gain_after_carryforward": D("0.00"),
            "foreign_tax_by_item": {},
            "foreign_tax_refund_by_item": {},
            "foreign_taxable_item_by_key_before_allowance": {},
        }
        raw_buckets = {
            "fund_gain": D("0.00"),
            "option_gain": D("0.00"),
            "positive_income_total": D("300.006"),
            "non_fund_positive_income_total": D("300.006"),
        }
        fund_after = {"fund_taxable_after_teilfreistellung": D("0.00")}
        facts = {
            "de.capital.after_section_20_6_netting": netting,
            "de.capital.raw_buckets": raw_buckets,
            "de.capital.fund_after_teilfreistellung": fund_after,
            "de.capital.saver_allowance": D("100.00"),
            "de.capital.other_spouse_capital_before_allowance": None,
            # InvStG § 19 Vorabpauschale is a declared input of DE25-16; the
            # end-to-end allocation pin runs without Vorabpauschale.
            # https://www.gesetze-im-internet.de/invstg_2018/__19.html
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": D("0.00"),
        }
        result = de25_16_section_20_9_saver(facts)["de.capital.taxable_after_allowance"]
        emitted_total = result["total_taxable_before_allowance"]
        # After the fix the total is q2 (300.01) so downstream item / total
        # ratios divide by 300.01 rather than 300.006.
        self.assertEqual(emitted_total, D("300.01"))
        # Cross-check the helper produces the q2-consistent value when fed the
        # emitted total alongside a q2-quantized item.
        item_q2 = q2(D("100.001"))  # 100.00
        helper_value = _taxable_capital_item_after_saver_allowance_2025(
            item_q2,
            total_taxable_before_allowance_eur=emitted_total,
            saver_allowance_eur=D("100.00"),
        )
        # share = 100.00 * 100.00 / 300.01 = 33.32888... → 100.00 - share = 66.6711... → q2 = 66.67
        self.assertEqual(helper_value, D("66.67"))

    def test_helper_subcent_boundary_pinning(self) -> None:
        # C18: pin allocation behavior at a sub-cent boundary.
        # With three equal-cent items totaling 300.00 EUR and a 1.00 EUR
        # allowance, each item's allowance share is exactly 1/3 EUR. The helper
        # uses round-once-at-end (q2 ROUND_HALF_UP after subtraction), so each
        # item receives 100.00 - 0.3333... = 99.6666... → 99.67.
        item = D("100.00")
        total = D("300.00")
        allowance = D("1.00")
        result = _taxable_capital_item_after_saver_allowance_2025(
            item,
            total_taxable_before_allowance_eur=total,
            saver_allowance_eur=allowance,
        )
        self.assertEqual(result, D("99.67"))

    def test_de25_16_emits_sparer_pauschbetrag_claimed_eur_for_joint_assessment(
        self,
    ) -> None:
        # A4 (FORM-MAPPING-FOLLOWUP): § 20 Abs. 9 Satz 2 EStG — €2,000
        # statutory cap for jointly assessed spouses (§ 26b EStG). The
        # rule must surface this on the new declared output
        # ``de.capital.sparer_pauschbetrag_claimed_eur`` so the renderer
        # writes Anlage KAP Zeile 4 from a fingerprinted rule output, not
        # from a re-derivation in the projection. The *used* allocation
        # (Zeile 17) remains on the existing
        # ``taxable_after_allowance`` block.
        # https://www.gesetze-im-internet.de/estg/__20.html
        netting = {
            "taxable_by_symbol_before_allowance": {
                "A": D("500.00"),
                "B": D("500.00"),
            },
            "stock_gain_after_carryforward": D("0.00"),
            "foreign_tax_by_item": {},
            "foreign_tax_refund_by_item": {},
            "foreign_taxable_item_by_key_before_allowance": {},
        }
        raw_buckets = {
            "fund_gain": D("0.00"),
            "option_gain": D("0.00"),
            "positive_income_total": D("1000.00"),
            "non_fund_positive_income_total": D("1000.00"),
        }
        fund_after = {"fund_taxable_after_teilfreistellung": D("0.00")}
        facts = {
            "de.capital.after_section_20_6_netting": netting,
            "de.capital.raw_buckets": raw_buckets,
            "de.capital.fund_after_teilfreistellung": fund_after,
            # § 20 Abs. 9 Satz 2 EStG: jointly assessed spouses get a
            # €2,000 cap (the canonical SAVER_ALLOWANCE_JOINT_2025_EUR
            # constant; see germany_2025_law.py).
            "de.capital.saver_allowance": D("2000.00"),
            "de.capital.other_spouse_capital_before_allowance": None,
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": D("0.00"),
        }
        result = de25_16_section_20_9_saver(facts)
        # The new declared output must equal the statutory cap exactly,
        # regardless of how much of the allowance the spouse actually uses.
        # Here total income (1000.00 EUR) is below the cap (2000.00 EUR), so
        # the *used* allowance is only 1000.00 EUR — but the *claimed* line
        # 4 amount remains the full €2,000 jointly assessed cap.
        self.assertEqual(
            result["de.capital.sparer_pauschbetrag_claimed_eur"], D("2000.00")
        )
        self.assertEqual(
            result["de.capital.taxable_after_allowance"]["saver_allowance_used"],
            D("1000.00"),
        )

    def test_de25_16_emits_sparer_pauschbetrag_claimed_eur_for_single_filer(
        self,
    ) -> None:
        # A4 (FORM-MAPPING-FOLLOWUP): § 20 Abs. 9 Satz 1 EStG — €1,000
        # statutory cap for a single filer (or a married-separate posture
        # before the spouse-allocation; § 20 Abs. 9 Satz 3 EStG handles
        # the spouse case via ``other_spouse_capital_before_allowance``).
        # https://www.gesetze-im-internet.de/estg/__20.html
        netting = {
            "taxable_by_symbol_before_allowance": {"A": D("500.00")},
            "stock_gain_after_carryforward": D("0.00"),
            "foreign_tax_by_item": {},
            "foreign_tax_refund_by_item": {},
            "foreign_taxable_item_by_key_before_allowance": {},
        }
        raw_buckets = {
            "fund_gain": D("0.00"),
            "option_gain": D("0.00"),
            "positive_income_total": D("500.00"),
            "non_fund_positive_income_total": D("500.00"),
        }
        fund_after = {"fund_taxable_after_teilfreistellung": D("0.00")}
        facts = {
            "de.capital.after_section_20_6_netting": netting,
            "de.capital.raw_buckets": raw_buckets,
            "de.capital.fund_after_teilfreistellung": fund_after,
            # § 20 Abs. 9 Satz 1 EStG: €1,000 cap for a single filer.
            "de.capital.saver_allowance": D("1000.00"),
            "de.capital.other_spouse_capital_before_allowance": None,
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": D("0.00"),
        }
        result = de25_16_section_20_9_saver(facts)
        self.assertEqual(
            result["de.capital.sparer_pauschbetrag_claimed_eur"], D("1000.00")
        )


class FundTeilfreistellungDeterministicOrderTest(unittest.TestCase):
    """C16: ``frozenset`` iteration order must not leak into dict insertion order.

    Authority: InvStG § 20 (partial exemption for fund income),
    https://www.gesetze-im-internet.de/invstg_2018/__20.html.
    """

    def _build_facts(self, fund_symbols_order: tuple[str, ...]) -> dict:
        # ``frozenset`` hash ordering is process-stable for short ASCII strings
        # but not order-of-insertion preserving; we exercise determinism by
        # building two semantically equal frozensets and verifying the rule
        # emits a stable, sorted dict either way.
        symbols = frozenset(fund_symbols_order)
        fund_types = {sym: "equity_fund" for sym in symbols}
        fund_symbol_gain = {sym: D("100.00") for sym in symbols}
        fund_symbol_income = {sym: D("0.00") for sym in symbols}
        return {
            "de.capital.raw_buckets": {
                "fund_symbols": symbols,
                "fund_types": fund_types,
                "fund_symbol_gain": fund_symbol_gain,
                "fund_symbol_income": fund_symbol_income,
            },
            "de.capital.fund_teilfreistellung_rates": {"equity_fund": D("0.30")},
        }

    def test_taxable_by_symbol_after_teilfreistellung_keys_are_sorted(self) -> None:
        symbols = ("ZETA", "ALPHA", "MIKE", "BETA", "GAMMA")
        out = de25_14_fund_teilfreistellung(self._build_facts(symbols))
        keys = list(
            out["de.capital.fund_after_teilfreistellung"][
                "taxable_by_symbol_after_fund_teilfreistellung"
            ].keys()
        )
        self.assertEqual(keys, sorted(symbols))

    def test_taxable_by_symbol_after_teilfreistellung_order_invariant_across_inputs(
        self,
    ) -> None:
        first = de25_14_fund_teilfreistellung(self._build_facts(("ZETA", "ALPHA", "MIKE")))
        second = de25_14_fund_teilfreistellung(self._build_facts(("ALPHA", "MIKE", "ZETA")))
        first_keys = list(
            first["de.capital.fund_after_teilfreistellung"][
                "taxable_by_symbol_after_fund_teilfreistellung"
            ].keys()
        )
        second_keys = list(
            second["de.capital.fund_after_teilfreistellung"][
                "taxable_by_symbol_after_fund_teilfreistellung"
            ].keys()
        )
        self.assertEqual(first_keys, second_keys)


class InitialFingerprintsStableMappingOrderTest(unittest.TestCase):
    """C7: Fingerprints over Mapping fact values must be order-independent.

    Authority context: audit-trail integrity for § 32d Abs. 5 EStG capital
    assessments (https://www.gesetze-im-internet.de/estg/__32d.html); two
    semantically identical workspaces must yield identical fingerprints.
    """

    def test_germany_capital_fingerprints_invariant_under_dict_order(self) -> None:
        # The same dict[str, str] inserted in two different orders must produce
        # the same fingerprint, otherwise audit-packet hashes drift.
        order_one = {"AAA": "equity_fund", "BBB": "non_equity_fund"}
        order_two = {"BBB": "non_equity_fund", "AAA": "equity_fund"}
        first = germany_capital_initial_fingerprints_2025(
            {"de.capital.fund_classification": order_one}
        )
        second = germany_capital_initial_fingerprints_2025(
            {"de.capital.fund_classification": order_two}
        )
        self.assertEqual(first, second)

    def test_us_initial_fingerprints_invariant_under_dict_order(self) -> None:
        order_one = {"AAA": "equity_fund", "BBB": "non_equity_fund"}
        order_two = {"BBB": "non_equity_fund", "AAA": "equity_fund"}
        first = us_initial_fingerprints_2025({"de.capital.fund_classification": order_one})
        second = us_initial_fingerprints_2025({"de.capital.fund_classification": order_two})
        self.assertEqual(first, second)


class PipelineBoundaryFailClosedTest(unittest.TestCase):
    """F-A4: ``germany_capital_initial_facts_2025`` must fail closed when
    ``derived-facts.json`` is absent and no ``derived_facts`` injection is
    supplied.

    Pre-F-A4 the function silently re-derived in memory, which let
    Pipeline 1 staleness escape detection: a stale on-disk artifact from
    a prior run was masked by the in-memory recomputation. The
    two-pipeline architecture (``docs/invariant-migration-plan.md`` §1.5)
    requires Pipeline 1 (``run_derivation``) to commit
    ``derived-facts.json`` before Pipeline 2 (germany_model) reads it;
    when neither path is available, the rule must surface the missing
    artifact rather than re-derive.

    Authority: § 32d Abs. 5 EStG per-Posten audit trail
    (https://www.gesetze-im-internet.de/estg/__32d.html); a stale or
    absent boundary state must not be silently recomputed.
    """

    def test_germany_capital_initial_facts_fail_closed_when_artifact_absent(self) -> None:
        # No ``derived_facts=`` injected, no ``TAX_*`` env vars in scope —
        # the loader returns ``None`` and the rule must raise
        # FileNotFoundError pointing operators at run_derivation.
        env_keys = ("TAX_PROJECT_ROOT", "TAX_WORKSPACE_ROOT", "TAX_YEAR")
        saved = {k: os.environ.pop(k, None) for k in env_keys}
        try:
            inputs = GermanyCapitalAssessmentInputs2025(
                sale_facts=(),
                income_facts=(),
                dher_stock_gain_eur=Decimal("0.00"),
                stock_loss_carryforward_2024_eur=Decimal("0.00"),
                saver_allowance_eur=Decimal("2000.00"),
                capital_tax_rate=Decimal("0.25"),
                soli_rate=Decimal("0.055"),
                treaty_dividend_credit_eur=Decimal("0.00"),
                fund_classification={},
            )
            with self.assertRaises(FileNotFoundError) as ctx:
                germany_capital_initial_facts_2025(inputs)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

        message = str(ctx.exception)
        self.assertIn("derived-facts.json not found", message)
        self.assertIn("Pipeline 1 (Derivation)", message)
        self.assertIn("run_derivation", message)


if __name__ == "__main__":
    unittest.main()
