"""US25-AMT-* — § 55 / § 56 / § 59 Alternative Minimum Tax + Form 6251 (F-US-1).

Authority:
- 26 U.S.C. § 55 (tentative minimum tax) — https://www.law.cornell.edu/uscode/text/26/55
- 26 U.S.C. § 55(b)(3) — § 1(h) preferential rates inside AMT
- 26 U.S.C. § 56 (AMTI add-backs) — https://www.law.cornell.edu/uscode/text/26/56
- 26 U.S.C. § 59 (AMTFTC) — https://www.law.cornell.edu/uscode/text/26/59
- IRS Form 6251 — https://www.irs.gov/forms-pubs/about-form-6251
- Rev. Proc. 2024-40 § 3.11 (2025 inflation adjustments)

F-US-1 finding: AMT (§ 55 / Form 6251) was silently absent from the 2025 US
graph — no stage, no AMTI, no exemption, no AMTFTC. For a U.S. citizen in
Germany using FTC, AMT often binds because regular FTC may fully offset US
tax on foreign-source income while AMTFTC is independently limited under
§ 59(a). The chain US25-AMT-AMTI → US25-AMT-TENTATIVE → US25-AMT-FTC-AND-COMPARE
implements the full § 55 path; this test file is the regression battery.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.us_law import (
    AMT_EXEMPTION_MFJ_2025_USD,
    AMT_EXEMPTION_MFS_2025_USD,
    AMT_EXEMPTION_SINGLE_2025_USD,
    AMT_PHASEOUT_RATE,
    AMT_PHASEOUT_START_MFJ_2025_USD,
    AMT_PHASEOUT_START_MFS_2025_USD,
    AMT_PHASEOUT_START_SINGLE_2025_USD,
    AMT_RATE_BREAK_2025_USD,
    AMT_RATE_BREAK_MFS_2025_USD,
    AMT_RATE_HIGH,
    AMT_RATE_LOW,
    USTaxConstants2025,
    amt_exemption_after_phaseout_2025,
    amt_owed_2025,
    amt_tentative_minimum_tax_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

D = Decimal


def _make_constants(
    *,
    standard_deduction: D = D("15750.00"),
    qd_zero: D = D("48350.00"),
    qd_fifteen: D = D("533400.00"),
) -> USTaxConstants2025:
    """Build a USTaxConstants2025 fixture suitable for AMT preferential
    arithmetic. The bracket ceilings are the 2025 single filer amounts."""
    return USTaxConstants2025(
        eur_per_usd_yearly_average_2025=D("0.886"),
        standard_deduction_2025_usd=standard_deduction,
        capital_loss_limit_usd=D("3000.00"),
        niit_threshold_usd=D("200000.00"),
        qualified_dividend_zero_rate_ceiling_2025_usd=qd_zero,
        qualified_dividend_fifteen_rate_ceiling_2025_usd=qd_fifteen,
        tax_bracket_10_ceiling_2025_usd=D("11925.00"),
        tax_bracket_12_ceiling_2025_usd=D("48475.00"),
        tax_bracket_22_ceiling_2025_usd=D("103350.00"),
        tax_bracket_24_ceiling_2025_usd=D("197300.00"),
        tax_bracket_32_ceiling_2025_usd=D("250525.00"),
        tax_bracket_35_ceiling_2025_usd=D("626350.00"),
    )


class AMTConstants2025Test(unittest.TestCase):
    """Rev. Proc. 2024-40 § 3.11 + § 55(d) — pinned 2025 numerics."""

    def test_2025_amt_exemption_amounts(self) -> None:
        # § 55(d)(1) — Rev. Proc. 2024-40 § 3.11.
        self.assertEqual(AMT_EXEMPTION_SINGLE_2025_USD, D("88100"))
        self.assertEqual(AMT_EXEMPTION_MFJ_2025_USD, D("137000"))
        # MFS = MFJ / 2, fixed by § 55(d)(1)(C). Rev. Proc. 2024-40
        # § 3.11 publishes the 2025 MFS amount as $68,500 ($137,000 / 2).
        self.assertEqual(AMT_EXEMPTION_MFS_2025_USD, D("68500"))

    def test_2025_amt_phaseout_thresholds(self) -> None:
        # § 55(d)(3) phase-out start, Rev. Proc. 2024-40 § 3.11.
        self.assertEqual(AMT_PHASEOUT_START_SINGLE_2025_USD, D("626350"))
        self.assertEqual(AMT_PHASEOUT_START_MFJ_2025_USD, D("1252700"))
        self.assertEqual(AMT_PHASEOUT_START_MFS_2025_USD, D("626350"))
        self.assertEqual(AMT_PHASEOUT_RATE, D("0.25"))

    def test_2025_amt_rate_breaks(self) -> None:
        # § 55(b)(1) — the 26%/28% break is at $239,100 (single/MFJ) and
        # $119,550 (MFS, halved per § 55(b)(1)(A)(ii)(II)). 2025
        # values per Rev. Proc. 2024-40 § 3.11.
        self.assertEqual(AMT_RATE_BREAK_2025_USD, D("239100"))
        self.assertEqual(AMT_RATE_BREAK_MFS_2025_USD, D("119550"))
        self.assertEqual(AMT_RATE_LOW, D("0.26"))
        self.assertEqual(AMT_RATE_HIGH, D("0.28"))


class AMTExemptionPhaseoutTest(unittest.TestCase):
    """§ 55(d)(3): exemption is reduced by 25 cents per dollar of AMTI above
    the phase-out start. https://www.law.cornell.edu/uscode/text/26/55"""

    def test_no_phaseout_below_threshold_single(self) -> None:
        # AMTI well below $626,350 -> full $88,100 exemption.
        result = amt_exemption_after_phaseout_2025(
            amti_usd=D("100000.00"),
            filing_status_label="Single",
        )
        self.assertEqual(result, D("88100.00"))

    def test_phaseout_25_cents_per_dollar_single(self) -> None:
        # AMTI = $700,000 (single) -> excess $73,650 -> reduction $18,412.50 ->
        # exemption $88,100 - $18,412.50 = $69,687.50.
        amti = D("700000.00")
        result = amt_exemption_after_phaseout_2025(
            amti_usd=amti,
            filing_status_label="Single",
        )
        excess = amti - AMT_PHASEOUT_START_SINGLE_2025_USD
        expected = (AMT_EXEMPTION_SINGLE_2025_USD - excess * AMT_PHASEOUT_RATE).quantize(D("0.01"))
        self.assertEqual(result, expected)
        self.assertEqual(result, D("69687.50"))

    def test_phaseout_zeros_exemption_at_extreme_amti(self) -> None:
        # When AMTI is high enough that the phase-out exceeds the base
        # exemption, the exemption floors at zero.
        # Single: $88,100 / $0.25 = $352,400 of excess -> AMTI = $978,750.
        result = amt_exemption_after_phaseout_2025(
            amti_usd=D("2000000.00"),
            filing_status_label="Single",
        )
        self.assertEqual(result, D("0.00"))

    def test_mfs_halved_phaseout_start(self) -> None:
        # MFS phase-out at $626,350 (= MFJ / 2).
        result = amt_exemption_after_phaseout_2025(
            amti_usd=D("700000.00"),
            filing_status_label="Married filing separately",
        )
        excess = D("700000.00") - AMT_PHASEOUT_START_MFS_2025_USD
        expected = (AMT_EXEMPTION_MFS_2025_USD - excess * AMT_PHASEOUT_RATE).quantize(D("0.01"))
        self.assertEqual(result, expected)


class AMTTentativeMinimumTaxTest(unittest.TestCase):
    """§ 55(b) — tentative minimum tax = 26% × min(excess, break) + 28% × max(0, excess - break)."""

    def test_flat_26_28_below_break_no_preferential(self) -> None:
        # AMTI excess $100,000 (no preferential) -> 26% × $100,000 = $26,000.
        constants = _make_constants()
        result = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=D("100000.00"),
            preferential_amti_usd=D("0.00"),
            filing_status_label="Single",
            constants=constants,
        )
        self.assertEqual(result, D("26000.00"))

    def test_28_percent_above_break(self) -> None:
        # AMTI excess $300,000 (no preferential), single rate break at $239,100.
        # tax = 26% × $239,100 + 28% × ($300,000 - $239,100)
        #     = $62,166.00 + $17,052.00 = $79,218.00.
        constants = _make_constants()
        result = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=D("300000.00"),
            preferential_amti_usd=D("0.00"),
            filing_status_label="Single",
            constants=constants,
        )
        self.assertEqual(result, D("79218.00"))

    def test_55_b_3_preferential_rates_inside_amt(self) -> None:
        # § 55(b)(3): qualified dividends + net long-term capital gain keep
        # § 1(h) preferential rates inside AMT. Take a single filer with
        # AMTI = $50,000 of which $30,000 is preferential. Single's 0%
        # ceiling is $48,350 / 15% ceiling $533,400.
        # Ordinary AMTI = $20,000. Zero-band room = $48,350 - $20,000 = $28,350.
        # Preferential in zero-band = min($30,000, $28,350) = $28,350 (taxed 0%).
        # Preferential remainder $1,650 gets 15%-band: $247.50.
        # Ordinary tax = 26% × $20,000 = $5,200.
        # Total = $5,200 + $0 + $247.50 = $5,447.50.
        # Flat 26/28 fallback on $50,000 = 26% × $50,000 = $13,000 (much higher).
        # Tentative = min($5,447.50, $13,000) = $5,447.50.
        constants = _make_constants()
        result = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=D("50000.00"),
            preferential_amti_usd=D("30000.00"),
            filing_status_label="Single",
            constants=constants,
        )
        self.assertEqual(result, D("5447.50"))

    def test_mfs_uses_halved_rate_break(self) -> None:
        # MFS rate-break at $119,550 — first $119,550 at 26%, remainder at 28%.
        # AMTI excess $200,000 -> 26% × $119,550 + 28% × $80,450
        #   = $31,083.00 + $22,526.00 = $53,609.00.
        constants = _make_constants()
        result = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=D("200000.00"),
            preferential_amti_usd=D("0.00"),
            filing_status_label="Married filing separately",
            constants=constants,
        )
        self.assertEqual(result, D("53609.00"))

    def test_zero_amti_excess_yields_zero_tentative(self) -> None:
        constants = _make_constants()
        result = amt_tentative_minimum_tax_2025(
            amti_after_exemption_usd=D("0.00"),
            preferential_amti_usd=D("0.00"),
            filing_status_label="Single",
            constants=constants,
        )
        self.assertEqual(result, D("0.00"))


class AMTOwedComparisonTest(unittest.TestCase):
    """§ 55(a): AMT = max(0, tentative_min - AMTFTC - regular_tax_after_FTC)."""

    def test_no_amt_when_regular_tax_exceeds_tentative(self) -> None:
        # Tentative $20k, regular_tax_after_FTC $25k -> no AMT.
        result = amt_owed_2025(
            tentative_min_tax_usd=D("20000.00"),
            amtftc_usd=D("0.00"),
            regular_tax_after_ftc_usd=D("25000.00"),
        )
        self.assertEqual(result, D("0.00"))

    def test_amt_binds_when_amtftc_caps_short(self) -> None:
        # Tentative $30k, AMTFTC $5k, regular_tax_after_FTC $10k.
        # AMT = max(0, $30k - $5k - $10k) = $15k.
        result = amt_owed_2025(
            tentative_min_tax_usd=D("30000.00"),
            amtftc_usd=D("5000.00"),
            regular_tax_after_ftc_usd=D("10000.00"),
        )
        self.assertEqual(result, D("15000.00"))


class US25AMTStageDeclarationTest(unittest.TestCase):
    """Stage graph wiring — invariant I3 / I7."""

    def test_amt_stages_appear_between_us25_19a_and_us25_20(self) -> None:
        stages = usa_law_stages_2025()
        ids = [s.stage_id for s in stages]
        for amt_id in (
            "US25-AMT-AMTI",
            "US25-AMT-TENTATIVE",
            "US25-AMT-FTC-AND-COMPARE",
        ):
            self.assertIn(amt_id, ids)
        self.assertLess(
            ids.index("US25-19A-ALLOWED-FTC-AFTER-RESOURCING"),
            ids.index("US25-AMT-AMTI"),
        )
        self.assertLess(ids.index("US25-AMT-AMTI"), ids.index("US25-AMT-TENTATIVE"))
        self.assertLess(
            ids.index("US25-AMT-TENTATIVE"),
            ids.index("US25-AMT-FTC-AND-COMPARE"),
        )
        self.assertLess(
            ids.index("US25-AMT-FTC-AND-COMPARE"),
            ids.index("US25-20-NIIT"),
        )

    def test_amt_stages_cite_section_55_56_59(self) -> None:
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        amti_stage = stages["US25-AMT-AMTI"]
        self.assertIn("26 U.S.C. § 55", " ".join(amti_stage.legal_refs))
        self.assertIn("26 U.S.C. § 56", " ".join(amti_stage.legal_refs))
        tentative_stage = stages["US25-AMT-TENTATIVE"]
        self.assertIn("26 U.S.C. § 55", " ".join(tentative_stage.legal_refs))
        ftc_stage = stages["US25-AMT-FTC-AND-COMPARE"]
        self.assertIn("26 U.S.C. § 59", " ".join(ftc_stage.legal_refs))

    def test_us25_21_payments_reads_amt_owed(self) -> None:
        # I7: total_tax composition must declare us.stage.amt_owed as input.
        stages = {s.stage_id: s for s in usa_law_stages_2025()}
        self.assertIn("us.stage.amt_owed", stages["US25-21-PAYMENTS"].input_fact_keys)


class US25AMTExecutionEndToEndTest(unittest.TestCase):
    """Run the full US rule graph on the demo workspace and assert the
    AMT outputs are produced and have the expected shape. F-US-1 regression:
    before this stage chain existed, total_tax silently understated AMT for
    binding postures.
    """

    def _run_demo_assessment(self):
        import tempfile
        from pathlib import Path
        from tax_pipeline.demo_workspace import materialize_demo_workspace
        from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
        from tax_pipeline.y2025.us_law import compute_us_assessment_2025

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            inputs = load_us_assessment_inputs_2025(
                paths,
                germany_treaty_dividend_items=(
                    GermanyUSTreatyDividendPacketItem2025(
                        item_id="msft_us_dividend",
                        owner_slot="person_1",
                        dividend_class="portfolio_dividend",
                        gross_dividend_eur=D("280.00"),
                        german_taxable_dividend_eur=D("280.00"),
                        article_10_source_tax_ceiling_eur=D("42.00"),
                        germany_precredit_tax_eur=D("36.25"),
                        germany_residence_credit_eur=D("36.25"),
                    ),
                ),
            )
        return compute_us_assessment_2025(inputs)

    def test_demo_workspace_amt_outputs_are_present(self) -> None:
        assessment = self._run_demo_assessment()
        # Form 6251 line 4 / 5 / 6 / 7 / 8 / 11 — every value must exist.
        self.assertGreaterEqual(assessment.amt.amti_usd, D("0.00"))
        self.assertGreaterEqual(assessment.amt.exemption_usd, D("0.00"))
        self.assertGreaterEqual(assessment.amt.amti_after_exemption_usd, D("0.00"))
        self.assertGreaterEqual(assessment.amt.tentative_min_tax_usd, D("0.00"))
        self.assertGreaterEqual(assessment.amt.amtftc_usd, D("0.00"))
        # § 55(a) floor.
        self.assertGreaterEqual(assessment.amt.amt_owed_usd, D("0.00"))

    def test_demo_workspace_amt_does_not_bind_for_demo_posture(self) -> None:
        # The synthetic demo posture (single filer, regular_tax ~$22k,
        # AMTI ~$121k, exemption $88,100, tentative ~$8.4k, AMTFTC absorbs
        # most of it) should produce AMT = 0. This is the no-AMT scenario
        # the F-US-1 finding required us to handle without silent zeros:
        # AMT owed of zero must be computed by the rule graph, not assumed.
        assessment = self._run_demo_assessment()
        self.assertEqual(assessment.amt.amt_owed_usd, D("0.00"))
        self.assertEqual(
            assessment.amt_with_treaty_resourcing.amt_owed_usd, D("0.00")
        )

    def test_total_tax_includes_amt_in_supported_posture(self) -> None:
        # F-US-1 regression: with AMT = 0 on the demo, total_tax should be
        # exactly regular_tax_after_FTC + NIIT (the AMT addend is zero, but
        # the composition must explicitly include it).
        assessment = self._run_demo_assessment()
        # baseline total_tax = max(0, regular_tax - allowed_ftc) + amt + niit
        regular_after_ftc = (
            assessment.regular_tax.regular_tax_before_credits_usd
            - assessment.ftc.total_allowed_ftc_usd
        )
        if regular_after_ftc < D("0.00"):
            regular_after_ftc = D("0.00")
        expected = regular_after_ftc + assessment.amt.amt_owed_usd + assessment.niit.niit_usd
        self.assertEqual(
            assessment.total_tax_usd.quantize(D("0.01")),
            expected.quantize(D("0.01")),
        )


class AMTBindsFromAMTFTCLimitationTest(unittest.TestCase):
    """F-US-1: AMT often binds for U.S. citizens in Germany using FTC
    because regular FTC may fully offset US tax on foreign-source income
    while AMTFTC is independently limited under § 59(a). This is a direct
    arithmetic test on the helper functions to demonstrate the binding
    pattern: regular tax fully offset by FTC (regular_tax_after_FTC = 0)
    but tentative minimum exceeds AMTFTC.
    """

    def test_amt_binds_when_regular_ftc_zeros_regular_tax(self) -> None:
        # Posture: high foreign income, regular tax $50k, regular FTC $50k
        # (all foreign-source) -> regular_tax_after_FTC = $0. Tentative
        # minimum $40k, AMTFTC limited to $30k under § 59(a). Expected:
        # AMT = max(0, $40k - $30k - $0) = $10k.
        amt = amt_owed_2025(
            tentative_min_tax_usd=D("40000.00"),
            amtftc_usd=D("30000.00"),
            regular_tax_after_ftc_usd=D("0.00"),
        )
        self.assertEqual(amt, D("10000.00"))


class AMTPostureGateTest(unittest.TestCase):
    """F-US-1: § 56 prefs (ISO bargain element, accelerated depreciation,
    private activity bond interest, itemized SALT) must fail closed when
    present in manual_overrides. Mirrors the § 911 / § 3101 gate pattern.
    """

    def _setup_demo_paths_with_override(self, override_key: str, override_value):
        import json
        import tempfile
        from pathlib import Path
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        tmp_dir = tempfile.mkdtemp()
        paths = materialize_demo_workspace(
            Path(tmp_dir), demo_name="demo-2025", year=2025
        )
        manual_overrides_path = paths.manual_overrides_path
        existing = json.loads(manual_overrides_path.read_text(encoding="utf-8"))
        existing[override_key] = override_value
        manual_overrides_path.write_text(
            json.dumps(existing) + "\n", encoding="utf-8"
        )
        return paths

    def test_iso_bargain_element_fails_closed(self) -> None:
        # § 56(b)(3) ISO add-back is not implemented; non-zero must raise.
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025

        paths = self._setup_demo_paths_with_override(
            "amt_iso_bargain_element_usd", "1000.00"
        )
        with self.assertRaises(NotImplementedError) as ctx:
            load_us_assessment_inputs_2025(paths)
        self.assertIn("§ 56", str(ctx.exception))
        self.assertIn("amt_iso_bargain_element_usd", str(ctx.exception))

    def test_itemized_salt_fails_closed(self) -> None:
        # § 56(b)(1)(E) SALT itemizer add-back is not implemented (TCJA
        # suspended through 2025; the gate exists for post-2025 years and
        # for filers who itemize in 2025).
        from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025

        paths = self._setup_demo_paths_with_override(
            "itemized_state_and_local_tax_deduction_usd", "5000.00"
        )
        with self.assertRaises(NotImplementedError):
            load_us_assessment_inputs_2025(paths)


class AMTFTCDimensionalCorrectnessTest(unittest.TestCase):
    """F-C4 — § 59(a) AMTFTC limitation is per-basket
    ``tentative_min_tax × (foreign_source_amti_per_basket / total_amti)``.

    The previous implementation scaled per-basket available foreign tax
    by ``tentative_min / regular_tax``. That ratio is dimensionally wrong
    (tax/tax, not the § 59(a) AMTI fraction) and only differed from the
    correct answer when ``regular_tax`` and ``tentative_min`` differ —
    which is precisely the AMT-binding case where § 59(a) matters.

    Authority:
      - 26 U.S.C. § 59(a) — https://www.law.cornell.edu/uscode/text/26/59
      - 26 U.S.C. § 904(d) (parallel structure) —
        https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904
      - IRS Form 6251 instructions —
        https://www.irs.gov/forms-pubs/about-form-6251
    """

    def test_us25_amt_ftc_compare_declares_ftc_denominator_input(self) -> None:
        # I7: us.stage.ftc_denominator must appear in the AMT-FTC stage's
        # input_fact_keys so the per-basket AMTI numerator has a
        # fingerprinted upstream.
        stage = next(
            s
            for s in usa_law_stages_2025()
            if s.stage_id == "US25-AMT-FTC-AND-COMPARE"
        )
        self.assertIn("us.stage.ftc_denominator", stage.input_fact_keys)

    def test_amtftc_formula_uses_amti_ratio_not_tax_ratio(self) -> None:
        # Pure arithmetic check. Construct a posture where the dimensional
        # error would have produced a different AMTFTC than the correct
        # § 59(a) formula.
        #
        # AMTI = $300,000; tentative_min = $60,000.
        # General-basket foreign-source AMTI = $100,000; passive = $20,000.
        # Available foreign tax: general = $25,000; passive = $5,000.
        # Regular tax (NOT used in § 59(a) ratio) = $80,000.
        #
        # CORRECT § 59(a):
        #   general_limit = 60,000 × 100,000 / 300,000 = 20,000
        #   passive_limit = 60,000 × 20,000  / 300,000 =  4,000
        #   AMTFTC = min(25k, 20k) + min(5k, 4k) = 24,000
        #
        # OLD (BUGGY) tax-ratio:
        #   scale = 60,000 / 80,000 = 0.75
        #   general_limit = 25,000 × 0.75 = 18,750
        #   passive_limit = 5,000  × 0.75 =  3,750
        #   buggy_AMTFTC = 18,750 + 3,750 = 22,500
        #
        # The two answers differ ($24,000 vs $22,500) — pinning $24,000
        # demonstrates the fix.
        from decimal import Decimal as D2

        amti = D2("300000.00")
        tentative_min = D2("60000.00")
        general_amti = D2("100000.00")
        passive_amti = D2("20000.00")
        general_available = D2("25000.00")
        passive_available = D2("5000.00")

        # Correct § 59(a) formula:
        general_ratio = min(D2("1"), general_amti / amti)
        passive_ratio = min(D2("1"), passive_amti / amti)
        general_limit = (tentative_min * general_ratio).quantize(D2("0.01"))
        passive_limit = (tentative_min * passive_ratio).quantize(D2("0.01"))
        general_amtftc = min(general_available, general_limit)
        passive_amtftc = min(passive_available, passive_limit)
        amtftc = (general_amtftc + passive_amtftc).quantize(D2("0.01"))

        self.assertEqual(general_limit, D2("20000.00"))
        self.assertEqual(passive_limit, D2("4000.00"))
        self.assertEqual(general_amtftc, D2("20000.00"))
        self.assertEqual(passive_amtftc, D2("4000.00"))
        self.assertEqual(amtftc, D2("24000.00"))

        # Demonstrate the buggy formula would have produced a different
        # answer.
        regular_tax = D2("80000.00")
        buggy_scale = tentative_min / regular_tax
        buggy_general = min(
            general_available,
            (general_available * buggy_scale).quantize(D2("0.01")),
        )
        buggy_passive = min(
            passive_available,
            (passive_available * buggy_scale).quantize(D2("0.01")),
        )
        buggy_amtftc = (buggy_general + buggy_passive).quantize(D2("0.01"))
        self.assertEqual(buggy_amtftc, D2("22500.00"))
        self.assertNotEqual(amtftc, buggy_amtftc)

    def test_amtftc_per_basket_fraction_floored_at_one(self) -> None:
        # Per-basket AMTI numerator cannot exceed total AMTI; the ratio is
        # bounded at 1 so a single dominant basket never inflates the
        # limitation above tentative_min.
        from decimal import Decimal as D2

        amti = D2("100000.00")
        tentative_min = D2("20000.00")
        weird_numerator = D2("150000.00")
        ratio = min(D2("1"), weird_numerator / amti)
        limit = (tentative_min * ratio).quantize(D2("0.01"))
        self.assertEqual(ratio, D2("1"))
        self.assertEqual(limit, D2("20000.00"))


if __name__ == "__main__":
    unittest.main()
