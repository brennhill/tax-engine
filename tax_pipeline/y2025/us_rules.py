"""Per-stage rule functions for the U.S. 2025 income-tax graph.

This module is the single execution path for the twenty-two declared
``US25-00`` through ``US25-21`` LawStages. Each ``calculate`` function
slices a piece of the historical ``compute_us_assessment_2025`` monolith
in ``tax_pipeline/y2025/us_law.py``; every legal value tracked by
``USOverallAssessment2025`` is produced by a ``LawRule.calculate``
invocation through ``execute_rule_graph``.

Treaty stages ``US25-15`` through ``US25-18`` mirror the values produced
by the dedicated treaty rule graph (``TREATY25-15`` - ``TREATY25-18``,
Phase 1) but expose them under the ``us.stage.treaty_*`` namespace that
downstream U.S. stages consume; the legal arithmetic is the same.

Authority: see the per-stage docstrings inside
``tax_pipeline/y2025/us_stages.py``.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import LawRule, LawStage, RuleGraphExecution, execute_rule_graph
from tax_pipeline.pipeline_context import (
    get_pipeline_context_value,
    set_pipeline_context_value,
)
from tax_pipeline.y2025.us_law import (
    ADDITIONAL_MEDICARE_RATE,
    BUSINESS_INCOME_SOURCE_FOREIGN,
    IRS_GERMANY_TECH,
    IRS_I1040,
    IRS_I1040SD,
    IRS_I1116,
    IRS_I8960,
    IRS_P514,
    IRS_P550,
    IRS_SCHEDULE_C_URL,
    IRS_YEARLY_AVG_RATES,
    NIIT_RATE,
    USAssessmentInputs2025,
    USAMTAssessment2025,
    USC_1_URL,
    USC_24_URL,
    USC_55_URL,
    USC_56_URL,
    USC_59_URL,
    USC_61_URL,
    USC_63_URL,
    USC_152_URL,
    USC_162_URL,
    USC_199A_URL,
    USC_864_URL,
    USC_901_URL,
    USC_904_URL,
    USC_1211_URL,
    USC_1212_URL,
    USC_1256_URL,
    USC_1411_URL,
    USCapitalAssessment2025,
    USChildTaxCreditAssessment2025,
    USFTCAssessment2025,
    USLawStage2025,
    USNIITAssessment2025,
    USOverallAssessment2025,
    USQBIGateAssessment2025,
    USRegularTaxAssessment2025,
    USScheduleCInputs2025,
    USScheduleCResult2025,
    USTreatyResourcingAssessment2025,
    adjusted_gross_income_2025,
    additional_medicare_assessment_2025,
    allowed_ftc_2025,
    amt_exemption_after_phaseout_2025,
    amt_owed_2025,
    amt_tentative_minimum_tax_2025,
    ctc_and_odc_assessment_2025,
    current_year_general_foreign_tax_usd_2025,
    fatca_fbar_assessment_2025,
    feie_assessment_2025,
    ftc_limitation_2025,
    net_capital_gain_for_preferential_tax_2025,
    qbi_gate_2025,
    regular_tax_2025,
    round_cents,
    schedule_c_net_profit_2025,
    se_tax_assessment_2025,
    section_1256_split_2025,
    standard_deduction_allocation_2025,
    taxable_income_2025,
    total_gross_income_for_ftc_2025,
    treaty_resourcing_assessment_2025,
    validate_form_1116_preferential_adjustment_support_2025,
    validate_supported_us_filing_positions_2025,
    validate_us_assessment_source_amounts_2025,
    validate_us_source_split_inputs_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

ZERO_USD = Decimal("0.00")
US_EXECUTION_CONTEXT_KEY = "us25.rule_graph_execution"
"""Pipeline-context key under which ``execute_us_rule_graph`` stashes the
executed ``RuleGraphExecution`` for in-memory hand-off to the narrative
packet builder.
"""

US_TREATY_ASSESSMENT_CONTEXT_KEY = "us25.treaty_assessment"
# Per-execution cache key. The treaty assessment is the result of running the
# TREATY25-* rule graph and is reused across US25-15..US25-18 (which all
# project from the same Pub. 514 worksheet) without re-executing it. The
# cache lives in pipeline_context so it does not leak into rule-graph facts
# and is reset at the start of every ``execute_us_rule_graph`` call.


def _inputs(facts: Mapping[str, Any]) -> USAssessmentInputs2025:
    inputs = facts["us.assessment.inputs"]
    if not isinstance(inputs, USAssessmentInputs2025):
        raise TypeError("us.assessment.inputs must be a USAssessmentInputs2025 instance")
    return inputs


# ---------------------------------------------------------------------------
# US25-00 through US25-08 (income / AGI / taxable income)
# ---------------------------------------------------------------------------


def us25_00_filing_position(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1, § 63, § 1211(b), § 1411: filing-status / election checks
    # plus posture-sensitive constants. Validation gates run here before any
    # income or credit computation.
    inputs = _inputs(facts)
    validate_supported_us_filing_positions_2025(inputs)
    validate_us_assessment_source_amounts_2025(inputs)
    validate_us_source_split_inputs_2025(
        ordinary_dividends_usd=inputs.capital_facts.ordinary_dividends_usd,
        qualified_dividends_usd=inputs.capital_facts.qualified_dividends_usd,
        foreign_source_passive_dividends_usd=inputs.ftc_inputs.foreign_source_passive_dividends_usd,
        foreign_source_qualified_dividends_usd=inputs.ftc_inputs.foreign_source_qualified_dividends_usd,
    )
    is_joint_return = inputs.profile.filing_status_label.strip().lower() == "married filing jointly"
    return {
        "us.stage.filing_position": {
            "filing_status_label": inputs.profile.filing_status_label,
            "is_joint_return": is_joint_return,
            "include_staking_in_niit": inputs.profile.include_staking_in_niit,
            "joint_return_with_nra_spouse_election": inputs.profile.joint_return_with_nra_spouse_election,
            "use_treaty_resourcing": inputs.treaty_inputs.use_treaty_resourcing,
            "capital_loss_limit_usd": inputs.constants.capital_loss_limit_usd,
            "standard_deduction_2025_usd": inputs.constants.standard_deduction_2025_usd,
            "niit_threshold_usd": inputs.constants.niit_threshold_usd,
            "eur_per_usd_yearly_average_2025": inputs.constants.eur_per_usd_yearly_average_2025,
        }
    }


def us25_01_wage_translation(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # IRS yearly-average FX guidance translates EUR wages to USD. Joint returns
    # combine taxpayer + spouse gross wages before translation.
    inputs = _inputs(facts)
    filing_position = facts["us.stage.filing_position"]
    is_joint = bool(filing_position["is_joint_return"])
    eur = inputs.ftc_inputs.taxpayer_gross_wages_eur + (
        inputs.ftc_inputs.spouse_gross_wages_eur if is_joint else ZERO_USD
    )
    if eur < ZERO_USD:
        raise ValueError("gross_wages_eur must be non-negative")
    fx = inputs.constants.eur_per_usd_yearly_average_2025
    if fx <= ZERO_USD:
        raise ValueError("eur_per_usd_yearly_average_2025 must be positive")
    return {"us.stage.wages_usd": round_cents(eur / fx)}


def _schedule_c_net_profit(inputs: USAssessmentInputs2025) -> Decimal:
    # 26 U.S.C. § 61 / § 162 Schedule C net profit. ``None`` (pure wage earner)
    # is zero profit; otherwise the constant-free netting in
    # ``schedule_c_net_profit_2025``. Deterministic: US25-02 and US25-02A both
    # call this on the same inputs and obtain the same value (the amount is
    # counted once — in schedule_1_other_income_usd — never double-counted).
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
    if inputs.schedule_c_inputs is None:
        return ZERO_USD
    return schedule_c_net_profit_2025(inputs=inputs.schedule_c_inputs).net_profit_usd


def us25_02_income_side_inputs(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 61 / § 162 / Pub. 525 / Pub. 550 income-side classification:
    # dividends, interest, Schedule 1 other (substitute payments + staking +
    # Schedule C net profit), qualified dividends, capital gain distributions.
    # IRS-VERIFIED 2026-06-13 (2025 Schedule C / Schedule 1 PDFs): the § 61 /
    # § 162 Schedule C net profit (Schedule C line 31) lands on Schedule 1
    # line 3, which the engine aggregates into schedule_1_other_income_usd →
    # AGI. For a wage earner (no Schedule C facts) the net profit is zero, so
    # this value is identical to the wage-only baseline.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
    inputs = _inputs(facts)
    capital_facts = inputs.capital_facts
    schedule_c_net_profit = _schedule_c_net_profit(inputs)
    schedule_1_other = round_cents(
        capital_facts.substitute_payments_usd
        + capital_facts.staking_income_usd
        + schedule_c_net_profit
    )
    return {
        "us.stage.income_side_inputs": {
            "ordinary_dividends_usd": round_cents(capital_facts.ordinary_dividends_usd),
            "qualified_dividends_usd": round_cents(capital_facts.qualified_dividends_usd),
            "interest_income_usd": round_cents(capital_facts.interest_income_usd),
            "schedule_1_other_income_usd": schedule_1_other,
            "substitute_payments_usd": round_cents(capital_facts.substitute_payments_usd),
            "staking_income_usd": round_cents(capital_facts.staking_income_usd),
            "schedule_c_net_profit_usd": round_cents(schedule_c_net_profit),
            "capital_gain_distributions_usd": round_cents(capital_facts.capital_gain_distributions_usd),
        }
    }


def us25_02a_schedule_c(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 61 / § 162 Schedule C net profit = gross receipts − ordinary
    # & necessary business expenses. IRS-VERIFIED 2026-06-13 against the 2025
    # Schedule C PDF (line 31 = line 7 gross income − line 28 total expenses, in
    # the no-home-office posture). The single net-profit amount feeds the income
    # side (Schedule 1 line 3, via US25-02-INCOME-SIDE-INPUTS) and the SE-tax
    # base (derived by the loader); these are the SAME profit, not double-
    # counted. For a wage earner the Schedule C facts are absent and every
    # output is zero (invariant I13).
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
    # https://www.irs.gov/forms-pubs/about-schedule-c-form-1040
    inputs = _inputs(facts)
    if inputs.schedule_c_inputs is None:
        gross_receipts = ZERO_USD
        business_expenses = ZERO_USD
        net_profit = ZERO_USD
        source = BUSINESS_INCOME_SOURCE_FOREIGN
        declared = False
        law_basis = "26 U.S.C. §§ 61, 162; IRS Schedule C (Form 1040)"
    else:
        result = schedule_c_net_profit_2025(inputs=inputs.schedule_c_inputs)
        gross_receipts = result.gross_receipts_usd
        business_expenses = result.business_expenses_usd
        net_profit = result.net_profit_usd
        source = result.business_income_source
        declared = True
        law_basis = result.law_basis
    return {
        "us.stage.schedule_c": {
            "gross_receipts_usd": gross_receipts,
            "business_expenses_usd": business_expenses,
            "net_profit_usd": net_profit,
            "business_income_source": source,
            "declared": declared,
            "law_basis": law_basis,
        },
        # Schedule C line-level decomposition (1:1 mirror of the bundle;
        # invariants I2 / I3 / I11). Line 7 = gross income, line 28 = total
        # expenses, line 31 = net profit (IRS-VERIFIED 2026-06-13).
        "us.tax.schedule_c_line_7_gross_income_usd": gross_receipts,
        "us.tax.schedule_c_line_28_total_expenses_usd": business_expenses,
        "us.tax.schedule_c_line_31_net_profit_usd": net_profit,
    }


def us25_03_capital_buckets(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. §§ 1211, 1212, Form 8949/Schedule D bucket assembly. Box A/B/H
    # short-term and Box D/K long-term are accumulated from broker- and
    # digital-asset-derived facts.
    inputs = _inputs(facts)
    f = inputs.capital_facts
    short_box_a = round_cents(f.schwab_short_box_a_gain_usd + f.jpm_short_type_a_gain_usd)
    short_box_b = round_cents(f.schwab_short_box_b_gain_usd)
    short_box_h = round_cents(
        f.coinbase_short_with_basis_proceeds_usd
        - f.coinbase_short_with_basis_basis_usd
        + f.coinbase_short_unknown_proceeds_usd
        - f.coinbase_short_unknown_basis_reconstructed_usd
    )
    long_box_d = round_cents(f.schwab_long_box_d_gain_usd)
    long_box_k = round_cents(f.coinbase_long_with_basis_proceeds_usd - f.coinbase_long_with_basis_basis_usd)
    short_term_total = round_cents(short_box_a + short_box_b + short_box_h)
    long_term_total_with_cgd = round_cents(long_box_d + long_box_k + f.capital_gain_distributions_usd)
    net_capital_before_1256 = round_cents(short_term_total + long_term_total_with_cgd)
    digital_asset_transaction_present = any(
        value != ZERO_USD
        for value in (
            f.coinbase_short_with_basis_proceeds_usd,
            f.coinbase_short_with_basis_basis_usd,
            f.coinbase_short_unknown_proceeds_usd,
            f.coinbase_short_unknown_basis_reconstructed_usd,
            f.coinbase_long_with_basis_proceeds_usd,
            f.coinbase_long_with_basis_basis_usd,
        )
    )
    return {
        "us.stage.capital_buckets": {
            "short_box_a_usd": short_box_a,
            "short_box_b_usd": short_box_b,
            "short_box_h_usd": short_box_h,
            "long_box_d_usd": long_box_d,
            "long_box_k_usd": long_box_k,
            "short_term_total_usd": short_term_total,
            "long_term_total_with_cgd_usd": long_term_total_with_cgd,
            "net_capital_before_1256_usd": net_capital_before_1256,
            "capital_gain_distributions_usd": round_cents(f.capital_gain_distributions_usd),
            "digital_asset_transaction_present": digital_asset_transaction_present,
        }
    }


def us25_04_section_1256(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1256(a)(3) statutory 40/60 short/long character split.
    inputs = _inputs(facts)
    section_1256_total = round_cents(inputs.capital_facts.schwab_section_1256_total_usd)
    short_term, long_term = section_1256_split_2025(section_1256_total)
    return {
        "us.stage.section_1256_split": {
            "total_usd": section_1256_total,
            "short_term_usd": short_term,
            "long_term_usd": long_term,
        }
    }


def us25_05_capital_loss_line_7a(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1211(b) annual capital-loss limit and § 1212 carryforward.
    # Form 1040 line 7a is the post-§ 1211 capital result.
    inputs = _inputs(facts)
    capital_buckets = facts["us.stage.capital_buckets"]
    section_1256 = facts["us.stage.section_1256_split"]
    capital_loss_limit_usd = inputs.constants.capital_loss_limit_usd
    if capital_loss_limit_usd < ZERO_USD:
        raise ValueError("capital_loss_limit_usd must be non-negative")
    net_capital_after_1256 = round_cents(
        capital_buckets["net_capital_before_1256_usd"] + section_1256["total_usd"]
    )
    if net_capital_after_1256 < 0:
        capital_loss_deduction = round_cents(min(capital_loss_limit_usd, -net_capital_after_1256))
        capital_loss_carryforward = round_cents(-net_capital_after_1256 - capital_loss_deduction)
        form_1040_line_7a = round_cents(-capital_loss_deduction)
    else:
        capital_loss_deduction = ZERO_USD
        capital_loss_carryforward = ZERO_USD
        form_1040_line_7a = round_cents(net_capital_after_1256)
    return {
        "us.stage.capital_loss_result": {
            "net_capital_after_1256_usd": net_capital_after_1256,
            "form_1040_line_7a_usd": form_1040_line_7a,
            "capital_loss_deduction_2025_usd": capital_loss_deduction,
            "tentative_capital_loss_carryforward_2026_usd": capital_loss_carryforward,
        }
    }


def us25_06_preferential_capital_base(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1(h) preferential net-capital-gain base for the Form 1040
    # line-16 Qualified Dividends and Capital Gain Tax Worksheet.
    capital_buckets = facts["us.stage.capital_buckets"]
    section_1256 = facts["us.stage.section_1256_split"]
    capital_loss = facts["us.stage.capital_loss_result"]
    capital_view = USCapitalAssessment2025(
        short_box_a_usd=capital_buckets["short_box_a_usd"],
        short_box_b_usd=capital_buckets["short_box_b_usd"],
        short_box_h_usd=capital_buckets["short_box_h_usd"],
        short_term_total_usd=capital_buckets["short_term_total_usd"],
        long_box_d_usd=capital_buckets["long_box_d_usd"],
        long_box_k_usd=capital_buckets["long_box_k_usd"],
        capital_gain_distributions_usd=capital_buckets["capital_gain_distributions_usd"],
        long_term_total_with_cgd_usd=capital_buckets["long_term_total_with_cgd_usd"],
        section_1256_total_usd=section_1256["total_usd"],
        section_1256_short_term_usd=section_1256["short_term_usd"],
        section_1256_long_term_usd=section_1256["long_term_usd"],
        net_capital_before_1256_usd=capital_buckets["net_capital_before_1256_usd"],
        net_capital_after_1256_usd=capital_loss["net_capital_after_1256_usd"],
        capital_loss_deduction_2025_usd=capital_loss["capital_loss_deduction_2025_usd"],
        tentative_capital_loss_carryforward_2026_usd=capital_loss["tentative_capital_loss_carryforward_2026_usd"],
        form_1040_line_7a_usd=capital_loss["form_1040_line_7a_usd"],
        digital_asset_transaction_present=capital_buckets["digital_asset_transaction_present"],
    )
    return {
        "us.stage.preferential_capital_base": net_capital_gain_for_preferential_tax_2025(capital_view)
    }


def us25_07_agi(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 61: gross income / Form 1040 line 11 AGI assembly.
    # F-C1 — 26 U.S.C. § 164(f)(1) one-half SE-tax deduction is an
    # above-the-line adjustment on Schedule 1 line 15 that reduces AGI.
    # Only § 1401(a) OASDI + § 1401(b)(1) Medicare (the combined
    # ``se_tax_usd``) is § 164(f) deductible; § 1401(b)(2) Additional
    # Medicare is NOT and is computed in US25-ADDITIONAL-MEDICARE.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
    income_side = facts["us.stage.income_side_inputs"]
    wages_usd = facts["us.stage.wages_usd"]
    capital_loss = facts["us.stage.capital_loss_result"]
    se_tax_view = facts["us.stage.se_tax"]
    one_half_se_tax_deduction = round_cents(
        se_tax_view["se_tax_usd"] / Decimal("2")
    )
    return {
        "us.stage.adjusted_gross_income": adjusted_gross_income_2025(
            wages_usd=wages_usd,
            ordinary_dividends_usd=income_side["ordinary_dividends_usd"],
            interest_income_usd=income_side["interest_income_usd"],
            schedule_1_other_income_usd=income_side["schedule_1_other_income_usd"],
            form_1040_line_7a_usd=capital_loss["form_1040_line_7a_usd"],
            one_half_se_tax_deduction_usd=one_half_se_tax_deduction,
        )
    }


def us25_feie(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 911 Foreign Earned Income Exclusion + § 911(c) housing
    # exclusion / deduction. The stage delegates to ``feie_assessment_2025``
    # in ``us_2025_law``; when the election is not made every output is
    # zero, so the demo workspace flows through unchanged. § 911(d)(6)
    # produces the disallowed-FTC amount and § 1411(d)(1)(A) produces the
    # NIIT MAGI add-back, both keyed under us.stage.feie for downstream
    # stages (US25-08, US25-11, US25-20).
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
    # https://www.irs.gov/publications/p54
    inputs = _inputs(facts)
    # Touch the AGI input so the executor records us.stage.adjusted_gross_income
    # in the input value/fingerprint maps for invariant I7.
    _ = facts["us.stage.adjusted_gross_income"]
    assessment = feie_assessment_2025(feie_inputs=inputs.feie_inputs)
    # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Form-2555-line scalar
    # outputs decomposing the existing ``us.stage.feie`` bundle so the
    # Form 2555 renderer can read fingerprinted Decimals through the
    # I11 LegalValue envelope.
    # - Line 36 (annual FEIE): excluded_amount_usd, 26 U.S.C. § 911(b)(2)(D).
    # - Line 45 (housing exclusion): housing_exclusion_usd, § 911(c)(4).
    # - Line 50 (housing deduction): housing_deduction_usd, § 911(c)(5).
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
    # https://www.irs.gov/forms-pubs/about-form-2555
    return {
        "us.stage.feie": {
            "elected": assessment.elected,
            "excluded_amount_usd": assessment.excluded_amount_usd,
            "housing_exclusion_usd": assessment.housing_exclusion_usd,
            "housing_deduction_usd": assessment.housing_deduction_usd,
            "deduction_total_usd": assessment.deduction_total_usd,
            "disallowed_ftc_usd": assessment.disallowed_ftc_usd,
            "niit_magi_addback_usd": assessment.niit_magi_addback_usd,
        },
        "us.feie.line_36_excluded_amount_usd": assessment.excluded_amount_usd,
        "us.feie.line_45_housing_exclusion_usd": assessment.housing_exclusion_usd,
        "us.feie.line_50_housing_deduction_usd": assessment.housing_deduction_usd,
    }


def us25_08_taxable_income(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 63 + 26 U.S.C. § 911: taxable income after standard
    # deduction and § 911 deduction-total (excluded wages + housing
    # exclusion + housing deduction).
    inputs = _inputs(facts)
    feie = facts["us.stage.feie"]
    feie_deduction = feie["deduction_total_usd"]
    base = facts["us.stage.adjusted_gross_income"] - feie_deduction
    return {
        "us.stage.taxable_income": taxable_income_2025(
            base,
            inputs.constants.standard_deduction_2025_usd,
        )
    }


def us25_08a_qbi_gate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c) QBI applicability GATE. For
    # foreign-source business income (the engine's taxpayer: U.S. citizen
    # resident in Germany, German-source freelance income) the deduction is
    # not_applicable and ZERO — German-source income is NOT effectively
    # connected with a U.S. trade or business, so it is NOT QBI. Taxable income
    # is UNCHANGED by § 199A in this posture (the gate subtracts nothing). This
    # is an explicit cited not_applicable status (invariant I13), never a Form
    # 8995 zero line; granting any 20 % deduction would be a LEAK-class
    # over-deduction. ``us_effectively_connected`` fails closed in qbi_gate_2025.
    # ``us.stage.taxable_income`` is read so US25-08A records a real input edge
    # (invariant I7); § 199A does not change it for foreign source.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section864
    inputs = _inputs(facts)
    taxable_income = facts["us.stage.taxable_income"]
    assessment = qbi_gate_2025(schedule_c_inputs=inputs.schedule_c_inputs)
    return {
        "us.stage.qbi_gate": {
            "status": assessment.status,
            "applicable": assessment.applicable,
            "business_income_source": assessment.business_income_source,
            "qbi_deduction_usd": assessment.qbi_deduction_usd,
            "taxable_income_before_qbi_usd": round_cents(taxable_income),
            # Taxable income is unchanged by § 199A for foreign-source income;
            # carry the post-gate value so downstream readers see the gate left
            # it untouched (no Form 8995 line; not_applicable per I13).
            "taxable_income_after_qbi_usd": round_cents(taxable_income),
            "basis": assessment.basis,
        }
    }


# ---------------------------------------------------------------------------
# US25-09 through US25-14 (regular tax / FTC chain)
# ---------------------------------------------------------------------------


def us25_09_regular_tax(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1 / § 1(h) / Pub. 550: regular tax with qualified-dividend
    # and capital-gain preferential rate ordering (Form 1040 line 16
    # Qualified Dividends and Capital Gain Tax Worksheet).
    inputs = _inputs(facts)
    income_side = facts["us.stage.income_side_inputs"]
    taxable_income = facts["us.stage.taxable_income"]
    preferential_base = facts["us.stage.preferential_capital_base"]
    regular = regular_tax_2025(
        taxable_income,
        income_side["qualified_dividends_usd"],
        inputs.constants,
        net_capital_gain_usd=preferential_base,
    )
    return {
        "us.stage.regular_tax_before_credits": {
            "taxable_ordinary_income_usd": regular.taxable_ordinary_income_usd,
            "ordinary_tax_component_usd": regular.ordinary_tax_component_usd,
            "qualified_dividend_tax_component_usd": regular.qualified_dividend_tax_component_usd,
            "regular_tax_before_credits_usd": regular.regular_tax_before_credits_usd,
        }
    }


def us25_10_form_1116_preferential_gate(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 904 / Form 1116 Worksheet for Line 18: foreign qualified-
    # dividend / capital-gain preferential adjustment is checked here. Cases
    # outside the IRS exception fail closed.
    inputs = _inputs(facts)
    wages_usd = facts["us.stage.wages_usd"]
    income_side = facts["us.stage.income_side_inputs"]
    regular_tax = facts["us.stage.regular_tax_before_credits"]
    regular_tax_view = USRegularTaxAssessment2025(
        wages_usd=wages_usd,
        schedule_1_other_income_usd=income_side["schedule_1_other_income_usd"],
        adjusted_gross_income_usd=facts["us.stage.adjusted_gross_income"],
        taxable_income_usd=facts["us.stage.taxable_income"],
        taxable_ordinary_income_usd=regular_tax["taxable_ordinary_income_usd"],
        ordinary_tax_component_usd=regular_tax["ordinary_tax_component_usd"],
        qualified_dividend_tax_component_usd=regular_tax["qualified_dividend_tax_component_usd"],
        regular_tax_before_credits_usd=regular_tax["regular_tax_before_credits_usd"],
    )
    validate_form_1116_preferential_adjustment_support_2025(
        regular_tax=regular_tax_view,
        ftc_inputs=inputs.ftc_inputs,
        constants=inputs.constants,
    )
    return {"us.stage.form_1116_preferential_gate": "supported"}


def us25_11_ftc_denominator(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 904 / Pub. 514: Form 1116 category gross-income denominator
    # plus standard-deduction allocation per category (general / passive).
    # 26 U.S.C. § 911(d)(6): foreign earned income excluded under § 911 is
    # removed from the FTC denominator (it would otherwise inflate the
    # category fraction and over-credit foreign tax that § 911(d)(6) has
    # already disallowed). The general-basket wages (which carry the
    # excluded foreign earned income for the modeled posture) drop by the
    # excluded amount.
    inputs = _inputs(facts)
    wages_usd = facts["us.stage.wages_usd"]
    income_side = facts["us.stage.income_side_inputs"]
    feie = facts["us.stage.feie"]
    capital_facts = inputs.capital_facts
    ftc_inputs = inputs.ftc_inputs
    passive_category_gross_income = round_cents(
        ftc_inputs.foreign_source_passive_dividends_usd + ftc_inputs.foreign_source_net_capital_gain_usd
    )
    # § 911(d)(6) — exclude § 911 amount from general-basket wages so the
    # FTC denominator never credits foreign tax allocable to excluded
    # income.
    feie_excluded = feie["excluded_amount_usd"] + feie["housing_exclusion_usd"]
    general_basket_wages = max(ZERO_USD, round_cents(wages_usd - feie_excluded))
    total_gross_income = total_gross_income_for_ftc_2025(
        wages_usd=general_basket_wages,
        ordinary_dividends_usd=capital_facts.ordinary_dividends_usd,
        interest_income_usd=capital_facts.interest_income_usd,
        schedule_1_other_income_usd=income_side["schedule_1_other_income_usd"],
        capital_gain_distributions_usd=capital_facts.capital_gain_distributions_usd,
        known_positive_short_capital_gain_usd=ftc_inputs.known_positive_short_capital_gain_usd,
        known_positive_long_capital_gain_usd=ftc_inputs.known_positive_long_capital_gain_usd,
    )
    standard_deduction = inputs.constants.standard_deduction_2025_usd
    general_alloc = standard_deduction_allocation_2025(
        standard_deduction_usd=standard_deduction,
        category_gross_income_usd=general_basket_wages,
        total_gross_income_for_ftc_usd=total_gross_income,
    )
    passive_alloc = standard_deduction_allocation_2025(
        standard_deduction_usd=standard_deduction,
        category_gross_income_usd=passive_category_gross_income,
        total_gross_income_for_ftc_usd=total_gross_income,
    )
    general_taxable_income = max(ZERO_USD, general_basket_wages - general_alloc)
    passive_taxable_income = max(ZERO_USD, passive_category_gross_income - passive_alloc)
    return {
        "us.stage.ftc_denominator": {
            "total_gross_income_for_ftc_usd": round_cents(total_gross_income),
            "general_standard_deduction_alloc_usd": round_cents(general_alloc),
            "passive_standard_deduction_alloc_usd": round_cents(passive_alloc),
            "general_taxable_income_for_ftc_usd": round_cents(general_taxable_income),
            "passive_taxable_income_for_ftc_usd": round_cents(passive_taxable_income),
            "passive_category_gross_income_usd": passive_category_gross_income,
        }
    }


def us25_12_ftc_limitations(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 904 limitation: regular_tax * category_taxable_income /
    # taxable_income, applied per category (general / passive).
    denom = facts["us.stage.ftc_denominator"]
    taxable_income = facts["us.stage.taxable_income"]
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    return {
        "us.stage.ftc_limitations": {
            "general_ftc_limitation_usd": round_cents(
                ftc_limitation_2025(
                    regular_tax_before_credits_usd=regular_tax,
                    category_taxable_income_usd=denom["general_taxable_income_for_ftc_usd"],
                    taxable_income_usd=taxable_income,
                )
            ),
            "passive_ftc_limitation_usd": round_cents(
                ftc_limitation_2025(
                    regular_tax_before_credits_usd=regular_tax,
                    category_taxable_income_usd=denom["passive_taxable_income_for_ftc_usd"],
                    taxable_income_usd=taxable_income,
                )
            ),
        }
    }


def us25_13_foreign_tax_available(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 901, § 905 / Pub. 514: current-year foreign tax + carryovers
    # per category. Wage-share allocation per Pub. 514 is the supported posture.
    # F-C3 — 26 U.S.C. § 911(d)(6): no foreign tax credit is allowed for
    # foreign tax paid on income that is excluded under § 911. The FEIE
    # stage (US25-FEIE) emits the disallowed amount via
    # ``us.stage.feie.disallowed_ftc_usd`` (already pro-rated by the law
    # helper for the excluded portion of foreign earned income). Wages
    # ride in the general basket per Pub. 514, so the disallowance lands
    # against ``current_year_general_foreign_tax_usd``. The post-denial
    # current-year general foreign tax is floored at zero — § 911(d)(6)
    # cannot create a refundable / negative bucket.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
    inputs = _inputs(facts)
    capital_facts = inputs.capital_facts
    ftc_inputs = inputs.ftc_inputs
    feie = facts["us.stage.feie"]
    current_general = current_year_general_foreign_tax_usd_2025(
        taxpayer_gross_wages_eur=ftc_inputs.taxpayer_gross_wages_eur,
        spouse_gross_wages_eur=ftc_inputs.spouse_gross_wages_eur,
        joint_wage_side_tax_eur=ftc_inputs.joint_wage_side_tax_eur,
        eur_per_usd_yearly_average_2025=inputs.constants.eur_per_usd_yearly_average_2025,
        use_full_joint_tax=False,
    )
    # § 911(d)(6) — strip the FTC allocable to the § 911 excluded amount
    # from the general basket. ``disallowed_ftc_usd`` is zero whenever
    # § 911 is not elected, so the demo posture is unchanged.
    disallowed_ftc_general = feie["disallowed_ftc_usd"]
    current_general_after_911d6 = max(
        ZERO_USD, round_cents(current_general - disallowed_ftc_general)
    )
    return {
        "us.stage.foreign_tax_available": {
            "current_year_general_foreign_tax_usd": current_general_after_911d6,
            "current_year_general_foreign_tax_before_911d6_usd": round_cents(current_general),
            "section_911_d_6_disallowed_ftc_general_usd": round_cents(disallowed_ftc_general),
            "current_year_passive_foreign_tax_usd": round_cents(capital_facts.foreign_tax_paid_usd),
            "general_ftc_carryover_2024_usd": round_cents(capital_facts.general_ftc_carryover_2024_usd),
            "passive_ftc_carryover_2024_usd": round_cents(capital_facts.passive_ftc_carryover_2024_usd),
        }
    }


def us25_14_baseline_allowed_ftc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. §§ 901 and 904: allowed credit per category is the lesser of
    # available foreign tax (current + carryover) and the § 904 limitation.
    limitations = facts["us.stage.ftc_limitations"]
    available = facts["us.stage.foreign_tax_available"]
    allowed_general, general_available_total = allowed_ftc_2025(
        limitation_usd=limitations["general_ftc_limitation_usd"],
        current_year_foreign_tax_usd=available["current_year_general_foreign_tax_usd"],
        carryover_usd=available["general_ftc_carryover_2024_usd"],
    )
    allowed_passive, passive_available_total = allowed_ftc_2025(
        limitation_usd=limitations["passive_ftc_limitation_usd"],
        current_year_foreign_tax_usd=available["current_year_passive_foreign_tax_usd"],
        carryover_usd=available["passive_ftc_carryover_2024_usd"],
    )
    total_allowed = round_cents(allowed_general + allowed_passive)
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    return {
        "us.stage.baseline_allowed_ftc": {
            "allowed_general_ftc_usd": round_cents(allowed_general),
            "allowed_passive_ftc_usd": round_cents(allowed_passive),
            "general_available_foreign_tax_usd": round_cents(general_available_total),
            "passive_available_foreign_tax_usd": round_cents(passive_available_total),
            "total_allowed_ftc_usd": total_allowed,
            "regular_tax_after_ftc_usd": round_cents(regular_tax - total_allowed),
            "remaining_form_1116_line_33_cap_usd": round_cents(max(ZERO_USD, regular_tax - total_allowed)),
        }
    }


# ---------------------------------------------------------------------------
# US25-15 through US25-18 (treaty re-sourcing)
# ---------------------------------------------------------------------------
#
# These four stages mirror the Pub. 514 treaty worksheet that Phase 1 already
# expressed as TREATY25-15 through TREATY25-18. Here they re-emit the same
# values into the ``us.stage.treaty_*`` namespace so downstream U.S. stages
# (US25-19 onwards) can consume them without crossing the treaty graph
# boundary. The legacy ``treaty_resourcing_assessment_2025`` wrapper is
# called once inside US25-15 to capture the full assessment, which is then
# decomposed across stages 15-18.


def _treaty_assessment(facts: Mapping[str, Any]) -> USTreatyResourcingAssessment2025:
    cached = get_pipeline_context_value(US_TREATY_ASSESSMENT_CONTEXT_KEY)
    if cached is not None:
        return cached
    inputs = _inputs(facts)
    capital_facts = inputs.capital_facts
    ftc_inputs = inputs.ftc_inputs
    baseline = facts["us.stage.baseline_allowed_ftc"]
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    treaty = treaty_resourcing_assessment_2025(
        ordinary_dividends_usd=capital_facts.ordinary_dividends_usd,
        qualified_dividends_usd=capital_facts.qualified_dividends_usd,
        foreign_source_passive_dividends_usd=ftc_inputs.foreign_source_passive_dividends_usd,
        foreign_source_qualified_dividends_usd=ftc_inputs.foreign_source_qualified_dividends_usd,
        # F-FN-2: Pub. 514 worksheet line 16 uses taxable income (Form 1040
        # line 15), not AGI. The cache-priming call inside US25-15 now reads
        # us.stage.taxable_income; the parent stage US25-15 declares this key
        # and ensures the dependency is materialized in the audit graph.
        taxable_income_usd=facts["us.stage.taxable_income"],
        standard_deduction_2025_usd=inputs.constants.standard_deduction_2025_usd,
        regular_tax_before_credits_usd=regular_tax,
        regular_tax_after_ftc_usd=baseline["regular_tax_after_ftc_usd"],
        remaining_form_1116_line_33_cap_usd=baseline["remaining_form_1116_line_33_cap_usd"],
        constants=inputs.constants,
        treaty_inputs=inputs.treaty_inputs,
    )
    set_pipeline_context_value(US_TREATY_ASSESSMENT_CONTEXT_KEY, treaty)
    return treaty


def us25_15_treaty_us_source_dividends(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 15: U.S.-source ordinary and qualified dividends.
    # Computed once by the treaty wrapper (which delegates to the TREATY25-*
    # rule graph in Phase 1) and surfaced into us.stage.treaty_* for the rest
    # of the U.S. graph. The TREATY25-* graph remains the canonical execution
    # of these values; US25-15-18 expose the same numbers under a U.S.-side
    # fact-key namespace.
    treaty = _treaty_assessment(facts)
    return {
        "us.stage.treaty_us_source_dividends": {
            "us_source_dividends_usd": treaty.us_source_dividends_usd,
            "us_source_qualified_dividends_usd": treaty.us_source_qualified_dividends_usd,
        },
    }


def us25_16_treaty_average_tax_floor(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet lines 16-18: U.S. tax on the U.S.-source dividend
    # stack (line 16) versus treaty 15 % source-country tax (line 17), with
    # line 18 = max(0, line 16 - line 17).
    treaty = _treaty_assessment(facts)
    return {
        "us.stage.treaty_us_limitation": {
            "us_tax_on_us_source_dividends_usd": treaty.us_tax_on_us_source_dividends_usd,
            "treaty_minimum_us_tax_on_us_source_dividends_usd": treaty.treaty_minimum_us_tax_on_us_source_dividends_usd,
            "treaty_resourcing_us_limitation_usd": treaty.treaty_resourcing_us_limitation_usd,
        }
    }


def us25_17_treaty_german_residual_cap(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet lines 19-20c: U.S. tax above the greater of the
    # treaty floor and the German residence credit (line 19) plus residual
    # German residence-country tax on the same dividends (line 20c).
    treaty = _treaty_assessment(facts)
    return {
        "us.stage.treaty_german_residual_cap": {
            "german_precredit_tax_on_us_source_dividends_usd": treaty.german_precredit_tax_on_us_source_dividends_usd,
            "german_residence_credit_for_us_tax_usd": treaty.german_residence_credit_for_us_tax_usd,
            "worksheet_line_19_maximum_credit_usd": treaty.worksheet_line_19_maximum_credit_usd,
            "worksheet_line_20c_residual_residence_country_tax_usd": treaty.worksheet_line_20c_residual_residence_country_tax_usd,
            "german_residual_tax_on_us_source_dividends_usd": treaty.german_residual_tax_on_us_source_dividends_usd,
        }
    }


def us25_18_treaty_additional_ftc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 21 = min(line 19, line 20c); the additional FTC
    # is line 21 further capped by remaining Form 1116 line-33 room.
    treaty = _treaty_assessment(facts)
    return {
        "us.stage.treaty_additional_ftc": {
            "worksheet_line_21_additional_credit_usd": treaty.worksheet_line_21_additional_credit_usd,
            "treaty_resourcing_additional_ftc_usd": treaty.treaty_resourcing_additional_ftc_usd,
            "regular_tax_after_ftc_and_treaty_resourcing_usd": treaty.regular_tax_after_ftc_and_treaty_resourcing_usd,
        }
    }


# ---------------------------------------------------------------------------
# US25-19 through US25-21 (allowed FTC / NIIT / payments)
# ---------------------------------------------------------------------------


def us25_19_allowed_ftc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. §§ 901 and 904 / Pub. 514 / Form 1116: final allowed FTC =
    # baseline + treaty add-on (subject to Form 1116 line-33 cap, applied
    # already in US25-18).
    baseline = facts["us.stage.baseline_allowed_ftc"]
    treaty_additional = facts["us.stage.treaty_additional_ftc"]
    total_allowed_ftc_after_treaty = round_cents(
        baseline["total_allowed_ftc_usd"] + treaty_additional["treaty_resourcing_additional_ftc_usd"]
    )
    return {
        "us.stage.allowed_ftc": {
            "total_allowed_ftc_after_treaty_resourcing_usd": total_allowed_ftc_after_treaty,
        }
    }


def us25_19a_allowed_ftc_after_resourcing(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. §§ 901 and 904 + IRS Publication 514 worksheet line 21 +
    # DBA-USA Art. 23: the total allowed Foreign Tax Credit after the
    # Publication 514 treaty re-sourcing add-on is the value that lands on
    # Form 1116 line 33 and Schedule 3 line 1. Promoted into its own
    # LawStage so the orchestrator (``us_model.main``) can read this
    # fingerprinted output instead of recomputing the sum from legacy
    # assessment dataclass fields (closes LEAK-4 / I5).
    #
    # Authority URLs:
    #   - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
    #   - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
    #   - https://www.irs.gov/publications/p514
    #   - https://www.irs.gov/instructions/i1116
    #   - https://www.irs.gov/pub/irs-trty/germtech.pdf
    baseline = facts["us.stage.baseline_allowed_ftc"]
    treaty_additional = facts["us.stage.treaty_additional_ftc"]
    allowed = facts["us.stage.allowed_ftc"]
    total_after_resourcing = round_cents(
        baseline["total_allowed_ftc_usd"]
        + treaty_additional["treaty_resourcing_additional_ftc_usd"]
    )
    # Reconciliation invariant: the dedicated post-treaty stage and the
    # US25-19 dict-output value must agree to the cent. If they ever drift
    # (e.g. a future contributor adjusts only one), fail closed instead of
    # silently shipping inconsistent legal numbers.
    legacy_post_treaty = allowed["total_allowed_ftc_after_treaty_resourcing_usd"]
    if total_after_resourcing != legacy_post_treaty:
        raise ValueError(
            "US25-19A reconciliation invariant violated: "
            f"baseline+treaty_additional={total_after_resourcing} "
            f"!= US25-19 us.stage.allowed_ftc.total_allowed_ftc_after_treaty_resourcing_usd"
            f"={legacy_post_treaty}. See 26 U.S.C. §§ 901, 904 and Pub. 514 worksheet line 21."
        )
    return {
        "us.stage.total_allowed_ftc_after_treaty_resourcing_usd": {
            "total_allowed_ftc_after_treaty_resourcing_usd": total_after_resourcing,
        },
        # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line 1 = post-treaty
        # allowed Foreign Tax Credit (Form 1116 line 33). 1:1 mirror of
        # the post-treaty sum above. Surfaced under
        # ``us.tax.schedule_3_line_1_ftc_total_usd`` so the Schedule 3
        # renderer reads a fingerprinted value through
        # ``legal_value_entry`` (invariants I2 / I11) and the prior
        # projection-side ``ftc[allowed_general] + ftc[allowed_passive]
        # + treaty[treaty_resourcing_additional_ftc]`` arithmetic at
        # ``us_treaty_packet.py:147`` is removed (invariant I5).
        "us.tax.schedule_3_line_1_ftc_total_usd": total_after_resourcing,
    }


# ---------------------------------------------------------------------------
# US25-AMT-* (Alternative Minimum Tax under §§ 55, 56, 59 — F-US-1)
# ---------------------------------------------------------------------------


def us25_amt_amti(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 56 — AMTI = regular taxable income plus § 56 add-backs
    # (state/local tax itemized deduction, depreciation timing differences,
    # ISO bargain element, NOL adjustments). For the only supported 2025
    # posture (standard-deduction filer, no itemized SALT, no ISO, no
    # depreciation prefs), AMTI ≈ taxable income; the upstream gates in
    # ``us_2025_inputs.py`` (under F-US-1) reject any fact pattern that
    # introduces real § 56 prefs so this stage cannot silently zero-default.
    # § 55(b)(3) preferential portion = qualified dividends + § 1(h) net
    # capital gain (kept at § 1(h) rates inside AMT). Authority:
    # https://www.law.cornell.edu/uscode/text/26/56
    # https://www.law.cornell.edu/uscode/text/26/55  (§ 55(b)(3))
    inputs = _inputs(facts)
    taxable_income = facts["us.stage.taxable_income"]
    preferential_capital_base = facts["us.stage.preferential_capital_base"]
    qualified_dividends = facts["us.capital.qualified_dividends"]
    # Posture gate already executed in ``us_2025_inputs.py`` confirms there
    # are no § 56 add-backs in the supported posture; AMTI add-back is zero.
    # Standard deduction is NOT a § 56 prefs item under TCJA (suspended
    # § 56(b)(1)(E) addback for 2018-2025). The 2025 AMTI base is therefore
    # simply taxable income for this posture.
    amti_addbacks_usd = ZERO_USD
    amti_usd = round_cents(taxable_income + amti_addbacks_usd)
    # § 55(b)(3) preferential portion: must be capped by AMTI itself (cannot
    # exceed the post-add-back base) per Form 6251 instructions.
    preferential_amti_usd = round_cents(
        min(amti_usd, preferential_capital_base + qualified_dividends)
    )
    if preferential_amti_usd < ZERO_USD:
        preferential_amti_usd = ZERO_USD
    return {
        "us.stage.amt_amti": {
            "amti_usd": amti_usd,
            "preferential_amti_usd": preferential_amti_usd,
            "amti_addbacks_usd": amti_addbacks_usd,
            "filing_status_label": inputs.profile.filing_status_label,
        }
    }


def us25_amt_tentative(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 55(d) exemption (with § 55(d)(3) phase-out), then § 55(b)
    # tentative minimum tax. § 55(b)(3) preserves § 1(h) preferential rates
    # on long-term capital gain and qualified dividends inside AMT — the
    # tentative minimum is the smaller of the flat 26/28 schedule and the
    # § 1(h)-style decomposition of preferential AMTI.
    # https://www.law.cornell.edu/uscode/text/26/55
    inputs = _inputs(facts)
    amt_amti = facts["us.stage.amt_amti"]
    amti_usd: Decimal = amt_amti["amti_usd"]
    preferential_amti_usd: Decimal = amt_amti["preferential_amti_usd"]
    filing_status = inputs.profile.filing_status_label
    exemption_usd = amt_exemption_after_phaseout_2025(
        amti_usd=amti_usd,
        filing_status_label=filing_status,
    )
    amti_after_exemption = amti_usd - exemption_usd
    if amti_after_exemption < ZERO_USD:
        amti_after_exemption = ZERO_USD
    amti_after_exemption = round_cents(amti_after_exemption)
    # § 55(b)(3) preferential portion is bounded by post-exemption AMTI.
    preferential_for_tentative = min(preferential_amti_usd, amti_after_exemption)
    tentative_min_tax = amt_tentative_minimum_tax_2025(
        amti_after_exemption_usd=amti_after_exemption,
        preferential_amti_usd=preferential_for_tentative,
        filing_status_label=filing_status,
        constants=inputs.constants,
    )
    return {
        "us.stage.amt_tentative": {
            "exemption_usd": exemption_usd,
            "amti_after_exemption_usd": amti_after_exemption,
            "preferential_amti_after_exemption_usd": round_cents(preferential_for_tentative),
            "tentative_min_tax_usd": tentative_min_tax,
        }
    }


def us25_amt_ftc_and_compare(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 59(a) AMTFTC limitation per category =
    #     tentative_min_tax × (foreign_source_amti_per_basket / total_amti)
    # AMTFTC per basket = min(available_foreign_tax_per_basket, limitation).
    # AMTFTC total = sum across baskets, capped at tentative_min_tax.
    # Final AMT under § 55(a) is then max(0, tentative_min_tax − AMTFTC −
    # regular_tax_after_FTC).
    #
    # F-C4 — the previous implementation scaled per-basket available
    # foreign tax by ``tentative_min / regular_tax``. That is dimensionally
    # wrong: it converts a foreign-tax dollar into a foreign-tax dollar
    # multiplied by a (tax/tax) ratio, which is not the § 59(a) ratio.
    # The correct ratio is foreign_source_AMTI / total_AMTI (parallel to
    # § 904(d), but on the AMTI base). For the supported posture
    # (standard-deduction filer, no § 56 prefs), AMTI ≈ regular taxable
    # income, so the per-basket AMTI numerator is numerically identical to
    # the § 904 numerator — but the denominator is AMTI, not regular
    # taxable income, so the limitation does NOT collapse to the regular
    # § 904 limitation. The bug only mattered when regular_tax differs
    # from tentative_min (the AMT-binding case), which is precisely when
    # § 59(a) is load-bearing.
    # https://www.law.cornell.edu/uscode/text/26/59
    # https://www.law.cornell.edu/uscode/text/26/55
    amt_amti = facts["us.stage.amt_amti"]
    amt_tentative = facts["us.stage.amt_tentative"]
    baseline = facts["us.stage.baseline_allowed_ftc"]
    allowed_ftc = facts["us.stage.allowed_ftc"]
    ftc_denominator = facts["us.stage.ftc_denominator"]
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    inputs = _inputs(facts)  # noqa: F841 — declared input touched at this seam.

    amti_usd = amt_amti["amti_usd"]
    tentative_min = amt_tentative["tentative_min_tax_usd"]
    # § 59(a): per-basket AMTI taxable income for the supported posture
    # (no § 56 add-backs) equals the § 904 per-basket numerator
    # (general_taxable_income_for_ftc_usd / passive_taxable_income_for_ftc_usd).
    # The AMTI denominator is total AMTI, not regular taxable income.
    general_amti_numerator = ftc_denominator["general_taxable_income_for_ftc_usd"]
    passive_amti_numerator = ftc_denominator["passive_taxable_income_for_ftc_usd"]
    if amti_usd == ZERO_USD or tentative_min == ZERO_USD:
        amtftc_usd = ZERO_USD
        per_category_amtftc_general = ZERO_USD
        per_category_amtftc_passive = ZERO_USD
        general_amtftc_limitation_usd = ZERO_USD
        passive_amtftc_limitation_usd = ZERO_USD
    else:
        general_available = baseline["general_available_foreign_tax_usd"]
        passive_available = baseline["passive_available_foreign_tax_usd"]
        # § 59(a) limitation per basket = tentative_min × (basket_amti / amti).
        # Each ratio is bounded at 1 because per-basket AMTI cannot exceed
        # total AMTI (this also matches the IRS Form 6251 / Form 1116 AMT
        # instructions, which floor the per-basket fraction at 1).
        general_ratio = min(Decimal("1"), general_amti_numerator / amti_usd)
        passive_ratio = min(Decimal("1"), passive_amti_numerator / amti_usd)
        general_amtftc_limitation_usd = round_cents(tentative_min * general_ratio)
        passive_amtftc_limitation_usd = round_cents(tentative_min * passive_ratio)
        per_category_amtftc_general = min(
            general_available, general_amtftc_limitation_usd
        )
        per_category_amtftc_passive = min(
            passive_available, passive_amtftc_limitation_usd
        )
        amtftc_usd = round_cents(
            per_category_amtftc_general + per_category_amtftc_passive
        )
        # § 59(a) total AMTFTC cannot exceed tentative minimum tax (it
        # offsets only the AMT it parallels).
        if amtftc_usd > tentative_min:
            amtftc_usd = tentative_min

    # Regular-tax-after-FTC baseline. The post-treaty allowed FTC is the
    # value that lands on Schedule 3 line 1 (Form 1040 line 20), so the
    # § 55(a) comparison uses regular_tax − total_allowed_ftc_after_treaty.
    total_allowed_ftc_after_treaty = allowed_ftc[
        "total_allowed_ftc_after_treaty_resourcing_usd"
    ]
    regular_tax_after_ftc = regular_tax - total_allowed_ftc_after_treaty
    if regular_tax_after_ftc < ZERO_USD:
        regular_tax_after_ftc = ZERO_USD
    regular_tax_after_ftc = round_cents(regular_tax_after_ftc)

    # Baseline (no-treaty) AMT comparison: regular_tax − baseline_allowed_ftc.
    # IRS-VERIFIED 2026-05-10 — this is the AMT that lands on Schedule 2
    # line 2 (2025 revision; was line 1 on 2024 revision) when treaty
    # re-sourcing is NOT claimed; the output key name retains 2024 line
    # numbering for fingerprint stability — see the declaration below.
    # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    # Compute both so US25-21 can wire each total_tax stream.
    baseline_total_allowed = baseline["total_allowed_ftc_usd"]
    baseline_regular_after_ftc = regular_tax - baseline_total_allowed
    if baseline_regular_after_ftc < ZERO_USD:
        baseline_regular_after_ftc = ZERO_USD
    baseline_regular_after_ftc = round_cents(baseline_regular_after_ftc)

    amt_owed_treaty = amt_owed_2025(
        tentative_min_tax_usd=tentative_min,
        amtftc_usd=amtftc_usd,
        regular_tax_after_ftc_usd=regular_tax_after_ftc,
    )
    amt_owed_baseline = amt_owed_2025(
        tentative_min_tax_usd=tentative_min,
        amtftc_usd=amtftc_usd,
        regular_tax_after_ftc_usd=baseline_regular_after_ftc,
    )

    return {
        "us.stage.amt_owed": {
            "amtftc_usd": amtftc_usd,
            "amtftc_general_usd": round_cents(per_category_amtftc_general),
            "amtftc_passive_usd": round_cents(per_category_amtftc_passive),
            "amtftc_general_limitation_usd": round_cents(general_amtftc_limitation_usd),
            "amtftc_passive_limitation_usd": round_cents(passive_amtftc_limitation_usd),
            "regular_tax_after_ftc_usd": regular_tax_after_ftc,
            "baseline_regular_tax_after_ftc_usd": baseline_regular_after_ftc,
            "amt_owed_usd": amt_owed_treaty,
            "amt_owed_without_treaty_resourcing_usd": amt_owed_baseline,
        },
        # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 2 = AMT (Form 6251
        # line 11) for the chosen treaty-resourcing posture. 1:1 surface of
        # the post-treaty AMT scalar; no new arithmetic.
        # IRS-VERIFIED 2026-05-10 — AMT moved from Schedule 2 line 1 (2024
        # revision) to line 2 (2025 revision) per
        # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf. The output key name
        # ``us.tax.schedule_2_line_1_amt_usd`` retains 2024 line numbering
        # for fingerprint stability across the audit graph; renaming would
        # rotate every workspace's md5 with no semantic change. The 2025
        # IRS line number for AMT is 2, surfaced through the form schema /
        # renderer (tax_pipeline/forms/schemas/schedule_2.toml + ``_write_
        # schedule_2``).
        "us.tax.schedule_2_line_1_amt_usd": amt_owed_treaty,
    }


def us25_20_niit(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1411 / Form 8960: NIIT = 3.8 % × min(NII, max(0, MAGI -
    # threshold)). Staking inclusion is a posture-controlled manual position.
    # F-C2 — 26 U.S.C. § 1411(d)(1)(A): MAGI for § 1411 is AGI plus the
    # § 911(a)(1) excluded foreign earned income (and the § 911(c) housing
    # exclusion), so the FEIE election cannot strip the NIIT base. The
    # § 911 stage (US25-FEIE) emits the per-§ 1411(d) add-back via
    # ``us.stage.feie.niit_magi_addback_usd``; reading it here closes the
    # F-C2 leak where the wired add-back was never applied.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411
    inputs = _inputs(facts)
    income_side = facts["us.stage.income_side_inputs"]
    capital_loss = facts["us.stage.capital_loss_result"]
    feie = facts["us.stage.feie"]
    # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 Part I line decomposition.
    # Authority: Form 8960 instructions (2024 revision; 2025 retains
    # the line numbers at publication time):
    #   https://www.irs.gov/forms-pubs/about-form-8960
    # Line 1 = taxable interest. Line 2 = ordinary dividends. Line 5a =
    # net capital gain/loss from Form 1040 line 7a. Lines 5b/5c = 0
    # (no § 1411 trade/business or CFC/PFIC adjustments modelled). Line
    # 5d = 5a + 5b + 5c. Substitute payments and (when elected) staking
    # income flow into line 7 ("Other modifications to investment
    # income"). Line 8 = sum of lines 1, 2, 5d, 7 (other Part I lines
    # are zero in the supported posture).
    line_1_interest = income_side["interest_income_usd"]
    line_2_ordinary_dividends = income_side["ordinary_dividends_usd"]
    line_5a_capital_gain_loss = capital_loss["form_1040_line_7a_usd"]
    line_5b_non_section_1411_adj = ZERO_USD
    line_5c_cfc_pfic_adj = ZERO_USD
    line_5d_combined_capital = round_cents(
        line_5a_capital_gain_loss + line_5b_non_section_1411_adj + line_5c_cfc_pfic_adj
    )
    line_7_other_modifications = income_side["substitute_payments_usd"]
    if inputs.profile.include_staking_in_niit:
        line_7_other_modifications = (
            line_7_other_modifications + income_side["staking_income_usd"]
        )
    line_7_other_modifications = round_cents(line_7_other_modifications)
    # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — Form 8960 line 11
    # (total deductions and modifications). No Part II investment-
    # expense deductions are modeled in the supported posture, so
    # line 11 = 0; surfaced for renderer reconciliation (line 12 =
    # line 8 − line 11).
    line_11_total_deductions = ZERO_USD
    # Pre-floor line 8: sum of declared Part I lines.
    line_8_total_investment_income_signed = (
        line_1_interest
        + line_2_ordinary_dividends
        + line_5d_combined_capital
        + line_7_other_modifications
    )
    # Existing convention (and Form 8960 line 16 floor): negative NII
    # cannot generate NIIT, so the line-8 surface follows max(0, signed)
    # so the audit value matches the input to the line-12 step. The pre-
    # floor signed total is preserved as ``line_5d_combined_capital``
    # remains signed (a negative line 5a flows through to line 5d).
    line_8_total_investment_income = round_cents(
        max(ZERO_USD, line_8_total_investment_income_signed)
    )
    # Form 8960 line 12 = line 8 − line 11. No Part II deductions
    # modeled, so line_11_total_deductions = 0 and line 12 = line 8.
    line_12_net_investment_income = round_cents(
        line_8_total_investment_income - line_11_total_deductions
    )
    net_investment_income = line_12_net_investment_income
    # § 1411(d)(1)(A) modified AGI = AGI + § 911 excluded amount + § 911(c)
    # housing exclusion. ``niit_magi_addback_usd`` is zero whenever the
    # § 911 election is not made, so the demo posture flows through
    # unchanged.
    modified_agi_usd = round_cents(
        facts["us.stage.adjusted_gross_income"] + feie["niit_magi_addback_usd"]
    )
    modified_agi_excess = round_cents(
        max(ZERO_USD, modified_agi_usd - inputs.constants.niit_threshold_usd)
    )
    niit_base = round_cents(min(net_investment_income, modified_agi_excess))
    niit = round_cents(niit_base * NIIT_RATE)
    return {
        "us.stage.niit": {
            "net_investment_income_usd": net_investment_income,
            "modified_agi_usd": modified_agi_usd,
            "modified_agi_excess_usd": modified_agi_excess,
            "niit_base_usd": niit_base,
            "niit_usd": niit,
        },
        # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 12 = § 1411 NIIT
        # (Form 8960 line 17). 1:1 surface of the NIIT scalar; no new
        # arithmetic.
        "us.tax.schedule_2_line_12_niit_usd": niit,
        # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 line-level decomposition.
        "us.tax.form_8960_line_1_interest_usd": round_cents(line_1_interest),
        "us.tax.form_8960_line_2_ordinary_dividends_usd": round_cents(
            line_2_ordinary_dividends
        ),
        "us.tax.form_8960_line_5a_capital_gain_loss_usd": round_cents(
            line_5a_capital_gain_loss
        ),
        "us.tax.form_8960_line_5b_non_section_1411_adj_usd": line_5b_non_section_1411_adj,
        "us.tax.form_8960_line_5c_cfc_pfic_adj_usd": line_5c_cfc_pfic_adj,
        "us.tax.form_8960_line_5d_combined_capital_usd": line_5d_combined_capital,
        # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — line 7 (other
        # modifications, including substitute payments + optional
        # staking) and line 11 (total deductions, zero in supported
        # posture) so the rendered Part I lines foot to line 8 and
        # line 12 = line 8 − line 11 reconciles from visible
        # components.
        "us.tax.form_8960_line_7_other_modifications_usd": line_7_other_modifications,
        "us.tax.form_8960_line_8_total_investment_income_usd": line_8_total_investment_income,
        "us.tax.form_8960_line_11_total_deductions_usd": line_11_total_deductions,
        "us.tax.form_8960_line_12_net_investment_income_usd": line_12_net_investment_income,
    }


def us25_se_tax(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 1401 / § 1402 — SE tax = 12.4 % OASDI on net SE
    # earnings up to the SS wage base + 2.9 % Medicare on all net SE
    # earnings (§ 1402(a)(12) reduces the base to 92.35 %). When SE
    # earnings are zero the helper short-circuits to zero outputs.
    # Phase 0 (Totalization): ``totalization_certificate_present`` returns
    # an explicit § 1401 exemption (zero tax, exempt marker, citation)
    # under the U.S.-Germany Totalization Agreement — the German system
    # covers the SE earner — rather than failing closed.
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
    # https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
    inputs = _inputs(facts)
    assessment = se_tax_assessment_2025(se_inputs=inputs.se_inputs)
    # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level decomposition.
    # Authority: Schedule SE (2024 revision; 2025 retains the line
    # numbering at publication time):
    #   https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
    # Schedule SE Part I — Self-Employment Tax:
    #   Line 2  = Net profit/loss from Schedule C (= net SE earnings).
    #   Line 3  = Combine lines 1a, 1b, 2 (= line 2 in supported posture).
    #   Line 4a = Line 3 × 92.35 % per § 1402(a)(12).
    #   Line 4c = 4a + 4b (= 4a; no optional method modelled).
    #   Line 6  = Line 4c + 5b (= 4c; no church wages modelled).
    #   Line 8a = W-2 box 3 social security wages (proxy: Medicare-taxable
    #             wages = SS wages for the supported posture).
    #   Line 10 = OASDI tax = 12.4 % × min(line 6, line 9 = max(0, SS base
    #             − line 8a)).
    #   Line 11 = Medicare tax = 2.9 % × line 6.
    #   Line 12 = Line 10 + Line 11 → Schedule 2 line 4.
    line_2_net_se_earnings = assessment.net_se_earnings_usd
    line_3_total_se_earnings = line_2_net_se_earnings
    line_4a_se_taxable = assessment.se_taxable_earnings_usd
    line_4c_se_taxable = line_4a_se_taxable
    line_6_combined_se_base = line_4c_se_taxable
    line_8a_w2_ss_wages = round_cents(
        inputs.se_inputs.us_w2_medicare_taxable_wages_usd
    )
    line_10_oasdi_tax = assessment.oasdi_tax_usd
    line_11_medicare_tax = assessment.medicare_tax_usd
    line_12_total_se_tax = assessment.se_tax_usd
    return {
        "us.stage.se_tax": {
            "net_se_earnings_usd": assessment.net_se_earnings_usd,
            "se_taxable_earnings_usd": assessment.se_taxable_earnings_usd,
            "oasdi_taxable_earnings_usd": assessment.oasdi_taxable_earnings_usd,
            "oasdi_tax_usd": assessment.oasdi_tax_usd,
            "medicare_tax_usd": assessment.medicare_tax_usd,
            "se_tax_usd": assessment.se_tax_usd,
            # Phase 0 (Totalization): the exemption is carried into the
            # audit trail so a Totalization-exempt $0 is distinguishable
            # from a no-earnings $0 (CLAUDE.md null/zero/missing, I13).
            # ``coverage_basis`` names the controlling authority for the
            # branch taken so this stage cross-audits in isolation.
            "exempt_under_totalization": assessment.exempt_under_totalization,
            "coverage_basis": assessment.coverage_basis,
        },
        # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 4 = § 1401 SE tax.
        # 1:1 surface of the SE-tax scalar; no new arithmetic.
        "us.tax.schedule_2_line_4_se_tax_usd": assessment.se_tax_usd,
        # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level decomposition.
        "us.tax.schedule_se_line_2_net_se_earnings_usd": line_2_net_se_earnings,
        "us.tax.schedule_se_line_3_total_se_earnings_usd": line_3_total_se_earnings,
        "us.tax.schedule_se_line_4a_se_taxable_usd": line_4a_se_taxable,
        "us.tax.schedule_se_line_4c_se_taxable_usd": line_4c_se_taxable,
        "us.tax.schedule_se_line_6_combined_se_base_usd": line_6_combined_se_base,
        "us.tax.schedule_se_line_8a_w2_ss_wages_usd": line_8a_w2_ss_wages,
        "us.tax.schedule_se_line_10_oasdi_tax_usd": line_10_oasdi_tax,
        "us.tax.schedule_se_line_11_medicare_tax_usd": line_11_medicare_tax,
        "us.tax.schedule_se_line_12_total_se_tax_usd": line_12_total_se_tax,
    }


def us25_additional_medicare(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 3101(b)(2) + § 1401(b)(2) — 0.9 % Additional Medicare
    # tax on COMBINED Medicare-taxable wages + SE taxable earnings
    # exceeding the filing-status threshold ($200k single / $250k MFJ /
    # $125k MFS, statutory non-indexed).
    inputs = _inputs(facts)
    se = facts["us.stage.se_tax"]
    assessment = additional_medicare_assessment_2025(
        filing_status_label=inputs.profile.filing_status_label,
        medicare_taxable_wages_usd=inputs.se_inputs.us_w2_medicare_taxable_wages_usd,
        se_taxable_earnings_usd=se["se_taxable_earnings_usd"],
    )
    # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level decomposition.
    # Form 8959 splits the combined excess into a wages portion (Part I,
    # lines 1-7) and an SE portion (Part II, lines 8-13), with a single
    # shared threshold consumed wages-first then SE. Part III (RRTA,
    # lines 14-17) is not modeled (zero) for the supported posture.
    # Authority:
    #   - 26 U.S.C. § 3101(b)(2) — 0.9 % on Medicare wages above threshold.
    #   - 26 U.S.C. § 1401(b)(2) — 0.9 % on SE earnings sharing the same
    #     threshold per Form 8959 Part II.
    #   - Form 8959 instructions: https://www.irs.gov/forms-pubs/about-form-8959
    # Form 8959 line numbering used here (2024 revision; 2025 retains
    # the line numbers at publication time):
    #   Part I (Medicare wages):
    #     Line 1: Medicare-taxable wages (W-2 box 5).
    #     Line 4: Sum of lines 1-3 (line 1 only in supported posture).
    #     Line 5: filing-status threshold.
    #     Line 6: max(0, line 4 - line 5).
    #     Line 7: line 6 × 0.009.
    #   Part II (Self-employment income):
    #     Line 8: Net SE taxable earnings (Schedule SE Section A line 4).
    #     Line 9: filing-status threshold (same as line 5).
    #     Line 10: amount from line 4 (Medicare wages).
    #     Line 11: max(0, line 9 - line 10).
    #     Line 12: max(0, line 8 - line 11).
    #     Line 13: line 12 × 0.009.
    #   Part III (RRTA): lines 14-17 = 0 (not modeled).
    #   Line 18: Total Additional Medicare Tax (line 7 + line 13 + line
    #   17). Carries to Schedule 2 line 11.
    medicare_wages = assessment.medicare_wages_usd
    se_taxable = assessment.se_taxable_earnings_usd
    threshold = assessment.threshold_usd
    line_4_total_medicare_wages = medicare_wages
    line_5_threshold = threshold
    line_6_wages_excess = round_cents(
        max(ZERO_USD, line_4_total_medicare_wages - line_5_threshold)
    )
    line_7_addtl_medicare_on_wages = round_cents(
        line_6_wages_excess * ADDITIONAL_MEDICARE_RATE
    )
    line_8_se_taxable = se_taxable
    line_9_threshold = threshold
    line_10_wages_for_se_step = line_4_total_medicare_wages
    line_11_residual_threshold = round_cents(
        max(ZERO_USD, line_9_threshold - line_10_wages_for_se_step)
    )
    line_12_se_excess = round_cents(
        max(ZERO_USD, line_8_se_taxable - line_11_residual_threshold)
    )
    line_13_addtl_medicare_on_se = round_cents(
        line_12_se_excess * ADDITIONAL_MEDICARE_RATE
    )
    line_18_total_addtl_medicare = round_cents(
        line_7_addtl_medicare_on_wages + line_13_addtl_medicare_on_se
    )
    # Reconciliation: line 18 must agree with the assessment scalar
    # (combined-base computation) to the cent.
    if line_18_total_addtl_medicare != assessment.additional_medicare_tax_usd:
        raise ValueError(
            "Form 8959 line 18 reconciliation invariant violated: "
            f"line_7 ({line_7_addtl_medicare_on_wages}) + line_13 "
            f"({line_13_addtl_medicare_on_se}) != assessment.additional_"
            f"medicare_tax_usd ({assessment.additional_medicare_tax_usd}). "
            "See 26 U.S.C. §§ 3101(b)(2), 1401(b)(2) and Form 8959."
        )
    return {
        "us.stage.additional_medicare": {
            "threshold_usd": assessment.threshold_usd,
            "medicare_wages_usd": assessment.medicare_wages_usd,
            "se_taxable_earnings_usd": assessment.se_taxable_earnings_usd,
            "combined_base_usd": assessment.combined_base_usd,
            "excess_over_threshold_usd": assessment.excess_over_threshold_usd,
            "additional_medicare_tax_usd": assessment.additional_medicare_tax_usd,
        },
        # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 11 = § 3101(b)(2) +
        # § 1401(b)(2) Additional Medicare (Form 8959 line 18). 1:1
        # surface of the additional-Medicare scalar; no new arithmetic.
        "us.tax.schedule_2_line_11_additional_medicare_usd": assessment.additional_medicare_tax_usd,
        # B3 — Form 8959 line-level decomposition.
        "us.tax.form_8959_line_1_medicare_wages_usd": line_4_total_medicare_wages,
        "us.tax.form_8959_line_4_total_medicare_wages_usd": line_4_total_medicare_wages,
        "us.tax.form_8959_line_5_threshold_usd": line_5_threshold,
        "us.tax.form_8959_line_6_wages_excess_usd": line_6_wages_excess,
        "us.tax.form_8959_line_7_addtl_medicare_on_wages_usd": line_7_addtl_medicare_on_wages,
        "us.tax.form_8959_line_8_se_taxable_usd": line_8_se_taxable,
        "us.tax.form_8959_line_11_residual_threshold_usd": line_11_residual_threshold,
        "us.tax.form_8959_line_13_addtl_medicare_on_se_usd": line_13_addtl_medicare_on_se,
        "us.tax.form_8959_line_18_total_addtl_medicare_usd": line_18_total_addtl_medicare,
    }


def us25_ctc_and_odc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # 26 U.S.C. § 24 — Child Tax Credit + Credit for Other Dependents.
    # Qualifying-child counts (§ 24(c)(1) under-17 + § 24(h)(7) SSN) and
    # ODC counts (§ 24(h)(4) for 17+ qualifying children or § 152(d)
    # qualifying relatives with TIN) are pre-classified by the loader
    # at ``tax_pipeline/y2025/us_inputs.py:_classify_child_2025`` so this
    # rule consumes the typed counts and runs the § 24(b) phase-out
    # plus § 24(d) refundable ACTC ceiling.
    #
    # MAGI for § 24(b) follows the Schedule 8812 (2025) instructions:
    # AGI plus § 911 / § 911(c) excluded amounts (same add-back as the
    # § 1411 NIIT MAGI under § 1411(d)(1)(A)) plus § 933 / Form 2555
    # exclusions. This rule reads the executor's
    # ``us.stage.feie.niit_magi_addback_usd`` (which already implements
    # the § 911 add-back) and adds it to AGI.
    #
    # Earned income for the § 24(d)(1)(B) phase-in includes wages
    # (§ 32(c)(2)(A)) and net SE earnings (§ 32(c)(2)(B)), reduced by
    # the § 911 excluded portion under § 24(d)(1)(B)(i).
    #
    # Authority:
    #   - https://www.law.cornell.edu/uscode/text/26/24
    #   - https://www.law.cornell.edu/uscode/text/26/152
    #   - https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
    inputs = _inputs(facts)
    wages_usd = facts["us.stage.wages_usd"]
    se_taxable_earnings = facts["us.stage.se_tax"]["se_taxable_earnings_usd"]
    feie = facts["us.stage.feie"]
    agi = facts["us.stage.adjusted_gross_income"]
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    baseline_allowed_ftc = facts["us.stage.baseline_allowed_ftc"]
    # § 24(b)(2) MAGI: AGI plus § 911 excluded foreign earned income (and
    # § 911(c) housing exclusion); the FEIE stage already exposes this
    # add-back via niit_magi_addback_usd to keep the § 1411 and § 24
    # phase-outs symmetric.
    magi = round_cents(agi + feie["niit_magi_addback_usd"])
    # § 24(d)(1)(B) earned income = wages + net SE earnings; § 24(d)(1)(B)(i)
    # excludes amounts excluded under § 911. Demo posture has zero § 911
    # election so the add-back is zero by default.
    earned_income = round_cents(wages_usd + se_taxable_earnings)
    # § 24 nonrefundable credits offset regular tax after FTC; use the
    # baseline (no-treaty) post-FTC tax as the cap. The treaty path
    # produces a different post-FTC tax via US25-19A; for the supported
    # postures both are the same when no treaty resourcing is claimed.
    regular_tax_after_ftc = baseline_allowed_ftc["regular_tax_after_ftc_usd"]
    assessment = ctc_and_odc_assessment_2025(
        children_count_qualifying_for_ctc=inputs.children_facts.children_count_qualifying_for_ctc,
        children_count_qualifying_for_odc=inputs.children_facts.children_count_qualifying_for_odc,
        earned_income_usd=earned_income,
        modified_agi_usd=magi,
        regular_tax_after_ftc_usd=regular_tax_after_ftc,
        filing_status_label=inputs.profile.filing_status_label,
    )
    # Surface every Schedule 8812 (2025) form-line value as a declared
    # rule output so the renderer can pull each line through a real
    # ``StageResult.output_fingerprint`` (invariants I2 / I11). Lines 4 / 6
    # (counts), 9 / 10 / 13 (worksheet inputs), 16a / 16b (refundable-ACTC
    # caps), 18a / 19 / 20 / 21 (refundable phase-in arithmetic) all flow
    # through here. The rule body computed each value already; we just
    # promote them to declared output_keys under invariant I8.
    # Authority: 26 U.S.C. § 24; Schedule 8812 (2025) instructions.
    # https://www.law.cornell.edu/uscode/text/26/24
    # https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
    return {
        # § 24(c)(1) / § 24(h)(7) qualifying-children count (Schedule 8812
        # Line 4) and § 24(h)(4) qualifying-relatives / non-SSN children
        # count (Line 6).
        "us.ctc.qualifying_ctc_count": assessment.qualifying_ctc_count,
        "us.ctc.qualifying_odc_count": assessment.qualifying_odc_count,
        "us.ctc.gross_ctc_usd": assessment.gross_ctc_usd,
        "us.ctc.gross_odc_usd": assessment.gross_odc_usd,
        "us.ctc.combined_pre_phaseout_usd": assessment.combined_pre_phaseout_usd,
        # § 24(b)(2) phase-out threshold (Line 9) and Modified AGI
        # (Line 10 — already folded the § 911 / § 933 add-back upstream).
        "us.ctc.phaseout_threshold_usd": assessment.phaseout_threshold_usd,
        "us.ctc.modified_agi_usd": assessment.modified_agi_usd,
        "us.ctc.phaseout_reduction_usd": assessment.phaseout_reduction_usd,
        "us.ctc.combined_post_phaseout_usd": assessment.combined_post_phaseout_usd,
        # Schedule 8812 Line 13 — regular tax after FTC ordering cap from
        # the Credit Limit Worksheet A. § 24(b)(3): nonrefundable credits
        # cannot reduce tax below zero.
        "us.ctc.regular_tax_after_ftc_usd": assessment.regular_tax_after_ftc_usd,
        "us.ctc.nonrefundable_portion_usd": assessment.nonrefundable_portion_usd,
        # Schedule 8812 Line 16a — remaining-CTC ceiling for the § 24(d)
        # refundable allocation. Line 16b — § 24(d)(1)(A) per-child cap
        # ($1,700 for 2025; Rev. Proc. 2024-40 § 3.05).
        "us.ctc.remaining_ctc_for_refundable_usd": assessment.remaining_ctc_for_refundable_usd,
        "us.ctc.refundable_actc_cap_usd": assessment.refundable_actc_cap_usd,
        # Schedule 8812 Line 18a — earned income input. Line 19 — the
        # statutory $2,500 floor from CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD
        # (kept in the law module per invariant I1; surfaced as a real
        # output here so the form-line write traces to a fingerprint).
        # Line 20 — max(0, earned_income − $2,500). Line 21 — 15 %
        # phase-in.
        "us.ctc.earned_income_usd": assessment.earned_income_usd,
        "us.ctc.earned_income_floor_usd": assessment.earned_income_floor_usd,
        "us.ctc.earned_income_excess_usd": assessment.earned_income_excess_usd,
        "us.ctc.refundable_actc_earned_income_phase_in_usd": assessment.refundable_actc_earned_income_phase_in_usd,
        # Post-phaseout CTC share (split of combined_post by gross_ctc /
        # combined_pre) — the working value Line 16a is derived from.
        "us.ctc.post_phaseout_ctc_share_usd": assessment.post_phaseout_ctc_share_usd,
        "us.ctc.refundable_actc_usd": assessment.refundable_actc_usd,
        "us.ctc.total_credit_usd": assessment.total_credit_usd,
    }


def us25_21_payments(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Form 1040 instructions: refund (line 35a) / amount owed (line 37) split
    # of the signed (payments - total tax) result, with treaty re-sourcing
    # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) line numbering per
    # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf; chain Form 6251
    # line 11 → Schedule 2 line 2 → line 3 → Form 1040 line 17.
    # applied if claimed. F-US-1: total_tax now includes AMT (Schedule 2
    # line 2 on the 2025 IRS revision; was Schedule 2 line 1 on the 2024
    # revision) under 26 U.S.C. § 55. Without it the no-AMT path silently
    # understated total_tax for AMT-binding postures. Workstream 2:
    # total_tax now also includes § 1401 SE tax (Schedule 2 line 4) and
    # § 3101(b)(2) Additional Medicare (Schedule 2 line 11). For the
    # demo posture (no SE earnings) the additions are zero.
    inputs = _inputs(facts)
    regular_tax = facts["us.stage.regular_tax_before_credits"]["regular_tax_before_credits_usd"]
    baseline = facts["us.stage.baseline_allowed_ftc"]
    treaty_additional = facts["us.stage.treaty_additional_ftc"]
    amt_owed = facts["us.stage.amt_owed"]
    niit = facts["us.stage.niit"]
    se_tax = facts["us.stage.se_tax"]["se_tax_usd"]
    addtl_medicare = facts["us.stage.additional_medicare"]["additional_medicare_tax_usd"]
    # 26 U.S.C. § 24 — § 24 nonrefundable credit (Form 1040 line 19) reduces
    # regular tax after FTC. § 24(d) refundable ACTC (Form 1040 line 28) is
    # added to payments. Both are zero when ``config/children.csv`` is empty.
    ctc_nonrefundable = facts["us.ctc.nonrefundable_portion_usd"]
    ctc_refundable = facts["us.ctc.refundable_actc_usd"]
    estimated_payment = round_cents(inputs.capital_facts.estimated_payment_2025_usd)
    # § 24(b)(3) ordering: subtract § 24 nonrefundable credit from regular
    # tax after FTC BEFORE adding the additional taxes (AMT/NIIT/SE/Addtl
    # Medicare). The credit cannot reduce the additional taxes.
    regular_after_ftc_baseline = baseline["regular_tax_after_ftc_usd"]
    regular_after_ftc_treaty = treaty_additional[
        "regular_tax_after_ftc_and_treaty_resourcing_usd"
    ]
    baseline_after_ctc = round_cents(
        max(ZERO_USD, regular_after_ftc_baseline - ctc_nonrefundable)
    )
    treaty_after_ctc = round_cents(
        max(ZERO_USD, regular_after_ftc_treaty - ctc_nonrefundable)
    )
    total_tax = round_cents(
        baseline_after_ctc
        + amt_owed["amt_owed_without_treaty_resourcing_usd"]
        + niit["niit_usd"]
        + se_tax
        + addtl_medicare
    )
    total_tax_with_treaty = round_cents(
        treaty_after_ctc
        + amt_owed["amt_owed_usd"]
        + niit["niit_usd"]
        + se_tax
        + addtl_medicare
    )
    payments_total = round_cents(estimated_payment + ctc_refundable)
    refund_or_balance = round_cents(payments_total - total_tax)
    refund_or_balance_with_treaty = round_cents(payments_total - total_tax_with_treaty)
    # A2 (FORM-MAPPING-FOLLOWUP): Form 1040 line 22 = line 18 minus line 21.
    # line_18 is the tax-side subtotal "regular tax + AMT" (line 16 + line 17);
    # line_21 is the credit-side subtotal "CTC nonrefundable + Schedule 3"
    # (line 19 + line 20). Schedule 3 line 1 is the FTC, which is the
    # ``baseline_allowed_ftc`` plus ``treaty_additional_ftc`` for the
    # treaty-resourced posture, or ``baseline_allowed_ftc`` alone for the
    # no-treaty baseline. Both versions are surfaced as declared rule
    # outputs so the renderer can show the chosen-treaty-posture value
    # while the audit trail still carries the no-treaty value.
    # Authority: Form 1040 instructions (line 22):
    #   https://www.irs.gov/instructions/i1040gi
    #   26 U.S.C. § 24(b)(3) ordering (CTC nonrefundable subtracted from
    #   regular tax after FTC and BEFORE additional taxes).
    line_18 = round_cents(
        regular_tax + amt_owed["amt_owed_without_treaty_resourcing_usd"]
    )
    line_18_with_treaty = round_cents(
        regular_tax + amt_owed["amt_owed_usd"]
    )
    baseline_ftc_total = baseline["total_allowed_ftc_usd"]
    treaty_ftc_total = round_cents(
        baseline_ftc_total + treaty_additional["treaty_resourcing_additional_ftc_usd"]
    )
    line_21_baseline = round_cents(ctc_nonrefundable + baseline_ftc_total)
    line_21_treaty = round_cents(ctc_nonrefundable + treaty_ftc_total)
    line_22 = round_cents(max(ZERO_USD, line_18 - line_21_baseline))
    line_22_with_treaty = round_cents(
        max(ZERO_USD, line_18_with_treaty - line_21_treaty)
    )
    # IRS-VERIFIED 2026-05-11 against the 2025 Schedule 2 PDF at
    # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf — AMT moved from
    # Schedule 2 line 1 (2024 revision) to line 2 (2025 revision);
    # the prior comment block said "2025 retains line numbering"
    # which was incorrect for Part I.
    # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 3 = sum of Part I
    # (line 1z additions to tax + line 2 AMT) per the 2025 revision.
    # IRS-VERIFIED 2026-05-11 — Part I line 1 expands to 1a-1y (APTC
    # repayment, clean-vehicle credit repayments, Form 4255 EPE
    # recapture, other) and 1z is the subtotal of 1a..1y. Line 2 is
    # IRS-VERIFIED 2026-05-11 against f1040s2.pdf — the AMT carried
    # from Form 6251 line 11. Line 3 = line 1z + line 2 → Form 1040
    # line 17. The supported posture has no line-1z additions to tax
    # IRS-VERIFIED 2026-05-11 (1z = $0), so line 3 = line 2 =
    # treaty-resourced AMT for the chosen filing posture. Form 1040
    # line 17 reads from this value (Authority below).
    # Authority IRS-VERIFIED 2026-05-11:
    #   - Schedule 2 (2025 revision):
    #     https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    #     https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    #   - 26 U.S.C. § 55 (AMT): https://www.law.cornell.edu/uscode/text/26/55
    schedule_2_line_3_total_amt = round_cents(amt_owed["amt_owed_usd"])
    # B1 — Schedule 2 line 21 = total of Part II "Other Taxes" (lines
    # 4-18 plus § 1411 NIIT). For the supported posture line 21 = line 4
    # (SE) + line 11 (Additional Medicare) + line 12 (NIIT). Form 1040
    # line 23 reads from this value.
    # Authority:
    #   - Schedule 2 (2024 revision):
    #     https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    #   - 26 U.S.C. § 1401 (SE tax)
    #   - 26 U.S.C. § 3101(b)(2) / § 1401(b)(2) (Additional Medicare)
    #   - 26 U.S.C. § 1411 (NIIT)
    schedule_2_line_21_total_other_taxes = round_cents(
        se_tax + addtl_medicare + niit["niit_usd"]
    )
    # B2-AUDIT (FORM-MAPPING-FOLLOWUP, 2026-05-03) — the historical B2
    # declarations for ``schedule_3_line_6c_other_refundable_credits_usd``
    # and ``schedule_3_line_11_treaty_resourcing_additional_ftc_usd``
    # were REMOVED. Per the IRS Schedule 3 (2024 / 2025) line numbering,
    # line 6c is the Adoption credit (Form 8839) and line 11 is "Excess
    # Social Security and Tier 1 RRTA tax withheld" — neither is the
    # treaty FTC add-on. The Pub. 514 worksheet line 21 value remains
    # available on ``us.stage.treaty_additional_ftc`` (US25-18) and
    # flows into Schedule 3 via line 1 (post-cap allowed FTC) only.
    return {
        "us.stage.refund_or_balance": {
            "estimated_payment_2025_usd": estimated_payment,
            "total_tax_usd": total_tax,
            "total_tax_with_treaty_resourcing_usd": total_tax_with_treaty,
            "refund_if_positive_else_balance_due_usd": refund_or_balance,
            "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": refund_or_balance_with_treaty,
        },
        "us.tax.line_22_after_credits_usd": line_22,
        "us.tax.line_22_after_credits_with_treaty_resourcing_usd": line_22_with_treaty,
        "us.tax.schedule_2_line_3_total_amt_usd": schedule_2_line_3_total_amt,
        "us.tax.schedule_2_line_21_total_other_taxes_usd": schedule_2_line_21_total_other_taxes,
    }


def us25_fatca_fbar_determination(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03) — Form 8938 (§ 6038D)
    + FBAR (31 CFR § 1010.350) filing-determination rule.

    Determination-only — does NOT change tax owed. The rule pulls the
    pre-loaded ``fatca_fbar_inputs`` from ``us.assessment.inputs`` and
    delegates to ``fatca_fbar_assessment_2025``. When the workspace's
    ``foreign-financial-accounts.csv`` is missing or
    ``data_complete=False``, the helper returns
    ``status="not_applicable"`` with a citation-bearing reason — the
    renderer surfaces a manual-determination status sheet rather than
    a silent "not required" verdict.

    Authority:
      - 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
      - 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
      - IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
      - 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
      - 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
      - FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/
    """
    inputs = _inputs(facts)
    assessment = fatca_fbar_assessment_2025(inputs=inputs.fatca_fbar_inputs)
    return {
        "us.fatca.form_8938_threshold_eoy_usd": assessment.form_8938_threshold_eoy_usd,
        "us.fatca.form_8938_threshold_anytime_usd": assessment.form_8938_threshold_anytime_usd,
        "us.fatca.foreign_specified_assets_max_usd": assessment.foreign_specified_assets_max_usd,
        "us.fatca.foreign_specified_assets_eoy_usd": assessment.foreign_specified_assets_eoy_usd,
        "us.fatca.form_8938_required": assessment.form_8938_required,
        "us.fbar.aggregate_max_balance_usd": assessment.fbar_aggregate_max_balance_usd,
        "us.fbar.fincen_114_required": assessment.fincen_114_required,
        "us.fatca.determination_status": assessment.status,
        "us.fatca.determination_reason": assessment.reason,
    }


_RULE_FUNCTIONS = {
    "US25-00-FILING-POSITION": us25_00_filing_position,
    "US25-01-WAGE-TRANSLATION": us25_01_wage_translation,
    "US25-02-INCOME-SIDE-INPUTS": us25_02_income_side_inputs,
    "US25-02A-SCHEDULE-C": us25_02a_schedule_c,
    "US25-03-CAPITAL-BUCKETS": us25_03_capital_buckets,
    "US25-04-SECTION-1256": us25_04_section_1256,
    "US25-05-CAPITAL-LOSS-LINE-7A": us25_05_capital_loss_line_7a,
    "US25-06-PREFERENTIAL-CAPITAL-BASE": us25_06_preferential_capital_base,
    "US25-07-AGI": us25_07_agi,
    "US25-FEIE": us25_feie,
    "US25-08-TAXABLE-INCOME": us25_08_taxable_income,
    "US25-08A-QBI-GATE": us25_08a_qbi_gate,
    "US25-09-REGULAR-TAX": us25_09_regular_tax,
    "US25-10-FORM-1116-PREFERENTIAL-GATE": us25_10_form_1116_preferential_gate,
    "US25-11-FTC-DENOMINATOR": us25_11_ftc_denominator,
    "US25-12-FTC-LIMITATIONS": us25_12_ftc_limitations,
    "US25-13-FOREIGN-TAX-AVAILABLE": us25_13_foreign_tax_available,
    "US25-14-BASELINE-ALLOWED-FTC": us25_14_baseline_allowed_ftc,
    "US25-15-TREATY-US-SOURCE-DIVIDENDS": us25_15_treaty_us_source_dividends,
    "US25-16-TREATY-AVERAGE-TAX-FLOOR": us25_16_treaty_average_tax_floor,
    "US25-17-TREATY-GERMAN-RESIDUAL-CAP": us25_17_treaty_german_residual_cap,
    "US25-18-TREATY-ADDITIONAL-FTC": us25_18_treaty_additional_ftc,
    "US25-19-ALLOWED-FTC": us25_19_allowed_ftc,
    "US25-19A-ALLOWED-FTC-AFTER-RESOURCING": us25_19a_allowed_ftc_after_resourcing,
    "US25-AMT-AMTI": us25_amt_amti,
    "US25-AMT-TENTATIVE": us25_amt_tentative,
    "US25-AMT-FTC-AND-COMPARE": us25_amt_ftc_and_compare,
    "US25-SE-TAX": us25_se_tax,
    "US25-ADDITIONAL-MEDICARE": us25_additional_medicare,
    "US25-CTC-AND-ODC": us25_ctc_and_odc,
    "US25-20-NIIT": us25_20_niit,
    "US25-21-PAYMENTS": us25_21_payments,
    # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 8938 / FBAR
    # determination — runs after every tax-affecting stage so it
    # reflects the same posture / balance set, but is independent
    # (does not affect tax owed).
    "US25-FATCA-FBAR-DETERMINATION": us25_fatca_fbar_determination,
}


def us_law_rules_2025() -> tuple[LawRule, ...]:
    stages = usa_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(f"No US calculate function registered for {stage.stage_id}")
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def us_initial_facts_2025(inputs: USAssessmentInputs2025) -> dict[str, Any]:
    # The granular fact keys declared in usa_law_stages_2025 are populated by
    # the per-stage calculate functions; here we provide the initial facts that
    # those declarations reference plus the full typed inputs for any stage
    # that needs to read fields that aren't decomposed into individual keys.
    return {
        "us.assessment.inputs": inputs,
        "us.profile.filing_posture": inputs.profile.filing_status_label,
        "us.profile.elections": {
            "joint_return_with_nra_spouse_election": inputs.profile.joint_return_with_nra_spouse_election,
            "include_staking_in_niit": inputs.profile.include_staking_in_niit,
            "use_treaty_resourcing": inputs.treaty_inputs.use_treaty_resourcing,
        },
        "us.reference.constants": {
            "standard_deduction_2025_usd": inputs.constants.standard_deduction_2025_usd,
            "capital_loss_limit_usd": inputs.constants.capital_loss_limit_usd,
            "niit_threshold_usd": inputs.constants.niit_threshold_usd,
            "eur_per_usd_yearly_average_2025": inputs.constants.eur_per_usd_yearly_average_2025,
        },
        "us.fx.eur_per_usd": inputs.constants.eur_per_usd_yearly_average_2025,
        "us.wages.eur": inputs.ftc_inputs.taxpayer_gross_wages_eur,
        "us.capital.income_facts": {
            "ordinary_dividends_usd": inputs.capital_facts.ordinary_dividends_usd,
            "qualified_dividends_usd": inputs.capital_facts.qualified_dividends_usd,
            "interest_income_usd": inputs.capital_facts.interest_income_usd,
            "substitute_payments_usd": inputs.capital_facts.substitute_payments_usd,
            "staking_income_usd": inputs.capital_facts.staking_income_usd,
            "capital_gain_distributions_usd": inputs.capital_facts.capital_gain_distributions_usd,
        },
        "us.capital.sale_facts": inputs.capital_facts,
        "us.capital.section_1256_facts": {
            "schwab_section_1256_total_usd": inputs.capital_facts.schwab_section_1256_total_usd,
        },
        "us.constants.capital_loss_limit": inputs.constants.capital_loss_limit_usd,
        "us.constants.standard_deduction": inputs.constants.standard_deduction_2025_usd,
        "us.capital.qualified_dividends": inputs.capital_facts.qualified_dividends_usd,
        "us.ftc.foreign_preferential_income": {
            "foreign_source_qualified_dividends_usd": inputs.ftc_inputs.foreign_source_qualified_dividends_usd,
            "foreign_source_net_capital_gain_usd": inputs.ftc_inputs.foreign_source_net_capital_gain_usd,
        },
        "us.ftc.category_gross_income": {
            "wages_eur": inputs.ftc_inputs.taxpayer_gross_wages_eur,
            "spouse_wages_eur": inputs.ftc_inputs.spouse_gross_wages_eur,
            "foreign_source_passive_dividends_usd": inputs.ftc_inputs.foreign_source_passive_dividends_usd,
            "foreign_source_net_capital_gain_usd": inputs.ftc_inputs.foreign_source_net_capital_gain_usd,
        },
        "us.ftc.current_foreign_tax": {
            "joint_wage_side_tax_eur": inputs.ftc_inputs.joint_wage_side_tax_eur,
            "foreign_tax_paid_usd": inputs.capital_facts.foreign_tax_paid_usd,
        },
        "us.ftc.carryovers": {
            "general_ftc_carryover_2024_usd": inputs.capital_facts.general_ftc_carryover_2024_usd,
            "passive_ftc_carryover_2024_usd": inputs.capital_facts.passive_ftc_carryover_2024_usd,
        },
        "us.treaty.dividend_source_split": {
            "ordinary_dividends_usd": inputs.capital_facts.ordinary_dividends_usd,
            "qualified_dividends_usd": inputs.capital_facts.qualified_dividends_usd,
            "foreign_source_passive_dividends_usd": inputs.ftc_inputs.foreign_source_passive_dividends_usd,
            "foreign_source_qualified_dividends_usd": inputs.ftc_inputs.foreign_source_qualified_dividends_usd,
        },
        "de.stage.us_source_dividend_tax_and_credit": {
            "german_precredit_tax_on_us_source_dividends_usd": (
                inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd or ZERO_USD
            ),
            "german_residence_credit_for_us_tax_usd": (
                inputs.treaty_inputs.german_residence_credit_for_us_tax_usd or ZERO_USD
            ),
        },
        "us.payments.estimated": inputs.capital_facts.estimated_payment_2025_usd,
    }


def us_initial_fingerprints_2025(initial_facts: Mapping[str, Any]) -> dict[str, str]:
    # Pass the raw value through ``stable_fingerprint`` so Mapping/Set/Decimal/
    # dataclass values get canonicalized before hashing. Using ``repr(value)``
    # would leak Python dict insertion order into the audit-trail hash.
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_us_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    set_pipeline_context_value(US_TREATY_ASSESSMENT_CONTEXT_KEY, None)
    execution = execute_rule_graph(
        dict(initial_facts),
        us_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(US_EXECUTION_CONTEXT_KEY, execution)
    return execution


def us_assessment_from_final_facts(
    final_facts: Mapping[str, Any],
    *,
    inputs: USAssessmentInputs2025,
) -> USOverallAssessment2025:
    """Project executed final_facts back into the legacy view dataclass."""
    capital_buckets = final_facts["us.stage.capital_buckets"]
    section_1256 = final_facts["us.stage.section_1256_split"]
    capital_loss = final_facts["us.stage.capital_loss_result"]
    income_side = final_facts["us.stage.income_side_inputs"]
    regular_tax = final_facts["us.stage.regular_tax_before_credits"]
    denom = final_facts["us.stage.ftc_denominator"]
    limitations = final_facts["us.stage.ftc_limitations"]
    available = final_facts["us.stage.foreign_tax_available"]
    baseline = final_facts["us.stage.baseline_allowed_ftc"]
    treaty_assessment = get_pipeline_context_value(US_TREATY_ASSESSMENT_CONTEXT_KEY)
    if treaty_assessment is None:
        raise RuntimeError(
            "Treaty assessment missing from pipeline context; US25-15 must populate it via _treaty_assessment."
        )
    niit = final_facts["us.stage.niit"]
    payments = final_facts["us.stage.refund_or_balance"]

    capital_view = USCapitalAssessment2025(
        short_box_a_usd=capital_buckets["short_box_a_usd"],
        short_box_b_usd=capital_buckets["short_box_b_usd"],
        short_box_h_usd=capital_buckets["short_box_h_usd"],
        short_term_total_usd=capital_buckets["short_term_total_usd"],
        long_box_d_usd=capital_buckets["long_box_d_usd"],
        long_box_k_usd=capital_buckets["long_box_k_usd"],
        capital_gain_distributions_usd=capital_buckets["capital_gain_distributions_usd"],
        long_term_total_with_cgd_usd=capital_buckets["long_term_total_with_cgd_usd"],
        section_1256_total_usd=section_1256["total_usd"],
        section_1256_short_term_usd=section_1256["short_term_usd"],
        section_1256_long_term_usd=section_1256["long_term_usd"],
        net_capital_before_1256_usd=capital_buckets["net_capital_before_1256_usd"],
        net_capital_after_1256_usd=capital_loss["net_capital_after_1256_usd"],
        capital_loss_deduction_2025_usd=capital_loss["capital_loss_deduction_2025_usd"],
        tentative_capital_loss_carryforward_2026_usd=capital_loss["tentative_capital_loss_carryforward_2026_usd"],
        form_1040_line_7a_usd=capital_loss["form_1040_line_7a_usd"],
        digital_asset_transaction_present=capital_buckets["digital_asset_transaction_present"],
    )
    regular_view = USRegularTaxAssessment2025(
        wages_usd=final_facts["us.stage.wages_usd"],
        schedule_1_other_income_usd=income_side["schedule_1_other_income_usd"],
        adjusted_gross_income_usd=final_facts["us.stage.adjusted_gross_income"],
        taxable_income_usd=final_facts["us.stage.taxable_income"],
        taxable_ordinary_income_usd=regular_tax["taxable_ordinary_income_usd"],
        ordinary_tax_component_usd=regular_tax["ordinary_tax_component_usd"],
        qualified_dividend_tax_component_usd=regular_tax["qualified_dividend_tax_component_usd"],
        regular_tax_before_credits_usd=regular_tax["regular_tax_before_credits_usd"],
    )
    ftc_view = USFTCAssessment2025(
        total_gross_income_for_ftc_usd=denom["total_gross_income_for_ftc_usd"],
        general_standard_deduction_alloc_usd=denom["general_standard_deduction_alloc_usd"],
        passive_standard_deduction_alloc_usd=denom["passive_standard_deduction_alloc_usd"],
        general_taxable_income_for_ftc_usd=denom["general_taxable_income_for_ftc_usd"],
        passive_taxable_income_for_ftc_usd=denom["passive_taxable_income_for_ftc_usd"],
        general_ftc_limitation_usd=limitations["general_ftc_limitation_usd"],
        passive_ftc_limitation_usd=limitations["passive_ftc_limitation_usd"],
        current_year_general_foreign_tax_usd=available["current_year_general_foreign_tax_usd"],
        current_year_passive_foreign_tax_usd=available["current_year_passive_foreign_tax_usd"],
        passive_available_foreign_tax_usd=baseline["passive_available_foreign_tax_usd"],
        general_available_foreign_tax_usd=baseline["general_available_foreign_tax_usd"],
        allowed_general_ftc_usd=baseline["allowed_general_ftc_usd"],
        allowed_passive_ftc_usd=baseline["allowed_passive_ftc_usd"],
        total_allowed_ftc_usd=baseline["total_allowed_ftc_usd"],
        regular_tax_after_ftc_usd=baseline["regular_tax_after_ftc_usd"],
    )
    niit_view = USNIITAssessment2025(
        net_investment_income_usd=niit["net_investment_income_usd"],
        modified_agi_excess_usd=niit["modified_agi_excess_usd"],
        niit_base_usd=niit["niit_base_usd"],
        niit_usd=niit["niit_usd"],
    )
    # F-US-1: AMT projection views. Two parallel runs of § 55(a):
    #   - amt_view: § 55(a) compared against regular_tax − total_allowed_ftc
    #     (no treaty re-sourcing applied to the regular-tax-after-FTC side).
    #   - amt_view_treaty: § 55(a) compared against regular_tax −
    #     post-Pub-514 allowed FTC. Used by the treaty packet renderer.
    amt_amti = final_facts["us.stage.amt_amti"]
    amt_tentative = final_facts["us.stage.amt_tentative"]
    amt_owed = final_facts["us.stage.amt_owed"]
    amt_view = USAMTAssessment2025(
        amti_usd=amt_amti["amti_usd"],
        preferential_amti_usd=amt_amti["preferential_amti_usd"],
        exemption_usd=amt_tentative["exemption_usd"],
        amti_after_exemption_usd=amt_tentative["amti_after_exemption_usd"],
        tentative_min_tax_usd=amt_tentative["tentative_min_tax_usd"],
        amtftc_usd=amt_owed["amtftc_usd"],
        amt_owed_usd=amt_owed["amt_owed_without_treaty_resourcing_usd"],
    )
    amt_view_treaty = USAMTAssessment2025(
        amti_usd=amt_amti["amti_usd"],
        preferential_amti_usd=amt_amti["preferential_amti_usd"],
        exemption_usd=amt_tentative["exemption_usd"],
        amti_after_exemption_usd=amt_tentative["amti_after_exemption_usd"],
        tentative_min_tax_usd=amt_tentative["tentative_min_tax_usd"],
        amtftc_usd=amt_owed["amtftc_usd"],
        amt_owed_usd=amt_owed["amt_owed_usd"],
    )
    law_order_stages = _law_order_stages_from_views(
        inputs=inputs,
        capital=capital_view,
        regular=regular_view,
        ftc=ftc_view,
        treaty=treaty_assessment,
        niit=niit_view,
        amt=amt_view,
        amt_treaty=amt_view_treaty,
        refund_or_balance=payments["refund_if_positive_else_balance_due_usd"],
        refund_or_balance_with_treaty=payments[
            "refund_if_positive_else_balance_due_with_treaty_resourcing_usd"
        ],
    )
    return USOverallAssessment2025(
        capital=capital_view,
        regular_tax=regular_view,
        ftc=ftc_view,
        treaty_resourcing=treaty_assessment,
        niit=niit_view,
        amt=amt_view,
        amt_with_treaty_resourcing=amt_view_treaty,
        total_tax_usd=payments["total_tax_usd"],
        total_tax_with_treaty_resourcing_usd=payments["total_tax_with_treaty_resourcing_usd"],
        refund_if_positive_else_balance_due_usd=payments["refund_if_positive_else_balance_due_usd"],
        refund_if_positive_else_balance_due_with_treaty_resourcing_usd=payments[
            "refund_if_positive_else_balance_due_with_treaty_resourcing_usd"
        ],
        law_order_stages=law_order_stages,
    )


def _law_order_stages_from_views(
    *,
    inputs: USAssessmentInputs2025,
    capital: USCapitalAssessment2025,
    regular: USRegularTaxAssessment2025,
    ftc: USFTCAssessment2025,
    treaty: USTreatyResourcingAssessment2025,
    niit: USNIITAssessment2025,
    amt: USAMTAssessment2025,
    amt_treaty: USAMTAssessment2025,
    refund_or_balance: Decimal,
    refund_or_balance_with_treaty: Decimal,
) -> tuple[USLawStage2025, ...]:
    # Flat audit-trace projection of the executed rule graph. The rule graph
    # itself is the canonical execution; this projection preserves the legacy
    # ``law_order_stages`` shape consumed by the U.S. model trace CSV and
    # legal-trace renderers.
    return (
        USLawStage2025(
            "eur_per_usd_yearly_average_2025",
            inputs.constants.eur_per_usd_yearly_average_2025,
            "IRS yearly average Euro Zone exchange rate for 2025.",
            "IRS yearly average currency exchange rates",
            IRS_YEARLY_AVG_RATES,
            precision_note="Direct source value from the structured reference-data layer.",
        ),
        USLawStage2025(
            "wages_usd",
            regular.wages_usd,
            "Foreign wages translated at the IRS yearly average rate for the current filing posture.",
            "IRS yearly average currency exchange rates",
            IRS_YEARLY_AVG_RATES,
            precision_note="Uses the filing-posture wage facts selected by the U.S. input loader.",
        ),
        USLawStage2025(
            "capital_gain_or_loss_line_7a",
            capital.form_1040_line_7a_usd,
            "Form 1040 line 7a amount from Schedule D / Form 6781 capital ordering.",
            "26 U.S.C. §§ 1211, 1212, and 1256; Instructions for Schedule D",
            f"{USC_1211_URL} | {USC_1212_URL} | {USC_1256_URL} | {IRS_I1040SD}",
            precision_note="Carries the Schedule D / Form 6781 result after the 26 U.S.C. § 1211(b) capital-loss limit.",
        ),
        USLawStage2025(
            "adjusted_gross_income",
            regular.adjusted_gross_income_usd,
            "Gross income assembled for Form 1040 line 11, including the line 7a capital result.",
            "26 U.S.C. § 61",
            USC_61_URL,
            precision_note="Adds wage, dividend, interest, Schedule 1, and line 7a components before Form 1040 line 11.",
        ),
        USLawStage2025(
            "taxable_income",
            regular.taxable_income_usd,
            "Adjusted gross income less the selected 2025 filing-status standard deduction.",
            "26 U.S.C. § 63",
            USC_63_URL,
            precision_note="Subtracts the selected 2025 26 U.S.C. § 63 standard deduction from AGI.",
        ),
        USLawStage2025(
            "regular_tax_before_credits",
            regular.regular_tax_before_credits_usd,
            "Regular income tax before FTCs, including the qualified-dividend and capital-gain rate ordering.",
            "26 U.S.C. § 1; IRS Publication 550",
            f"{USC_1_URL} | {IRS_P550}",
            precision_note="Uses the selected 26 U.S.C. § 1 schedule plus Publication 550 qualified-dividend ordering.",
        ),
        USLawStage2025(
            "total_gross_income_for_ftc",
            ftc.total_gross_income_for_ftc_usd,
            "Gross-income denominator used to apportion the standard deduction for Form 1116.",
            "26 U.S.C. § 904; IRS Publication 514",
            f"{USC_904_URL} | {IRS_P514}",
            step_type="manual_position",
            precision_note="Current model supports the documented positive-income denominator posture only.",
        ),
        USLawStage2025(
            "general_ftc_limitation",
            ftc.general_ftc_limitation_usd,
            "General-category FTC limitation.",
            "26 U.S.C. § 904; Instructions for Form 1116",
            f"{USC_904_URL} | {IRS_I1116}",
            precision_note="Applies the Form 1116 limitation fraction under 26 U.S.C. § 904 to the general basket.",
        ),
        USLawStage2025(
            "passive_ftc_limitation",
            ftc.passive_ftc_limitation_usd,
            "Passive-category FTC limitation.",
            "26 U.S.C. § 904; Instructions for Form 1116",
            f"{USC_904_URL} | {IRS_I1116}",
            precision_note="Applies the Form 1116 limitation fraction under 26 U.S.C. § 904 to the passive basket.",
        ),
        USLawStage2025(
            "current_year_general_foreign_tax_usd",
            ftc.current_year_general_foreign_tax_usd,
            "Current-year general-category foreign tax used by the supported wage-tax allocation posture.",
            "IRS Publication 514",
            IRS_P514,
            step_type="manual_position",
            precision_note="Allocated by wage share as an explicit Publication 514 manual position.",
        ),
        USLawStage2025(
            "allowed_general_ftc",
            ftc.allowed_general_ftc_usd,
            "Allowed general-category foreign tax credit.",
            "26 U.S.C. §§ 901 and 904",
            f"{USC_901_URL} | {USC_904_URL}",
            precision_note="Allowed credit is the lesser of available general-category foreign tax and the 26 U.S.C. § 904 limitation.",
        ),
        USLawStage2025(
            "allowed_passive_ftc",
            ftc.allowed_passive_ftc_usd,
            "Allowed passive-category foreign tax credit.",
            "26 U.S.C. §§ 901 and 904",
            f"{USC_901_URL} | {USC_904_URL}",
            precision_note="Allowed credit is the lesser of available passive-category foreign tax and the 26 U.S.C. § 904 limitation.",
        ),
        USLawStage2025(
            "us_source_dividends",
            treaty.us_source_dividends_usd,
            "U.S.-source dividends potentially eligible for treaty re-sourcing.",
            "Germany treaty technical explanation; IRS Publication 514",
            f"{IRS_GERMANY_TECH} | {IRS_P514}",
            precision_note="Uses the documented foreign-source split before the Publication 514 treaty-resourcing worksheet.",
        ),
        USLawStage2025(
            "treaty_resourcing_us_limitation",
            treaty.treaty_resourcing_us_limitation_usd,
            "Extra U.S. tax on the U.S.-source dividend stack above the treaty 15 percent floor.",
            "Germany treaty technical explanation; IRS Publication 514",
            f"{IRS_GERMANY_TECH} | {IRS_P514}",
            precision_note="Computed with the Publication 514 average-tax-rate method.",
        ),
        USLawStage2025(
            "german_residual_tax_on_us_source_dividends",
            treaty.german_residual_tax_on_us_source_dividends_usd,
            "Residual German tax on the same U.S.-source dividends for the Publication 514 cap.",
            "IRS Publication 514; Germany treaty technical explanation",
            f"{IRS_P514} | {IRS_GERMANY_TECH}",
            step_type="manual_position",
            precision_note="Manual residual-rate input used only for the Publication 514 line 20c cap.",
        ),
        USLawStage2025(
            "treaty_resourcing_additional_ftc",
            treaty.treaty_resourcing_additional_ftc_usd,
            "Additional FTC allowed in the treaty re-sourcing scenario.",
            "IRS Publication 514; Germany treaty technical explanation",
            f"{IRS_P514} | {IRS_GERMANY_TECH}",
            precision_note="Publication 514 worksheet line 21 is min(line 19, line 20c); the final allowed add-on is then capped by the remaining Form 1116 line-33 room.",
        ),
        USLawStage2025(
            "total_allowed_ftc_after_treaty_resourcing",
            round_cents(ftc.total_allowed_ftc_usd + treaty.treaty_resourcing_additional_ftc_usd),
            "Total allowed FTC after adding the Publication 514 treaty-resourcing worksheet amount to the base Form 1116 credits.",
            "26 U.S.C. §§ 901 and 904; IRS Publication 514; Instructions for Form 1116",
            f"{USC_901_URL} | {USC_904_URL} | {IRS_P514} | {IRS_I1116}",
            precision_note="Final nonrefundable FTC used before Form 1040 payment/refund arithmetic in the treaty-resourcing scenario.",
        ),
        # F-US-1: Form 6251 AMT trace entries (lines 4 / 5 / 6 / 7 / 8 / 11).
        USLawStage2025(
            "amt_amti",
            amt.amti_usd,
            "Form 6251 line 4 alternative minimum taxable income, including § 56 add-backs.",
            "26 U.S.C. §§ 55, 56; Instructions for Form 6251",
            f"{USC_55_URL} | {USC_56_URL} | https://www.irs.gov/forms-pubs/about-form-6251",
            precision_note="AMTI for the supported posture equals taxable income (no § 56 prefs in scope); the gate in us_2025_inputs.py rejects ISO / SALT / depreciation prefs.",
        ),
        USLawStage2025(
            "amt_exemption",
            amt.exemption_usd,
            "Form 6251 line 5 § 55(d) exemption after § 55(d)(3) phase-out (25 cents per dollar over the threshold).",
            "26 U.S.C. § 55(d); Rev. Proc. 2024-40 § 3.11",
            f"{USC_55_URL} | https://www.irs.gov/pub/irs-drop/rp-24-40.pdf",
            precision_note="2025 exemption: $88,100 single / $137,000 MFJ / $68,650 MFS; phase-out starts at $626,350 / $1,252,700 / $626,350.",
        ),
        USLawStage2025(
            "amt_tentative_min_tax",
            amt.tentative_min_tax_usd,
            "Form 6251 line 7 tentative minimum tax. § 55(b)(3) preserves § 1(h) preferential rates on long-term capital gain and qualified dividends inside AMT.",
            "26 U.S.C. § 55(b); Instructions for Form 6251",
            f"{USC_55_URL} | https://www.irs.gov/forms-pubs/about-form-6251",
            precision_note="26%/28% break at $232,600 (or $116,300 MFS); preferential AMTI uses the § 1(h) zero/15/20 ceilings under § 55(b)(3).",
        ),
        USLawStage2025(
            "amt_amtftc",
            amt.amtftc_usd,
            "Form 6251 line 8 § 59(a) AMTFTC; per-category limitation parallel to § 904(d) but on the AMTI base.",
            "26 U.S.C. § 59(a); Instructions for Form 6251",
            f"{USC_59_URL} | https://www.irs.gov/forms-pubs/about-form-6251",
            precision_note="Per-category lesser-of (available foreign tax, AMTI-based § 59(a) limit), capped at tentative minimum tax.",
        ),
        USLawStage2025(
            "amt_owed",
            amt.amt_owed_usd,
            # IRS-VERIFIED 2026-05-10 — Form 6251 line 11 → Schedule 2 line 2
            # → Form 1040 line 17 (was line 1 on 2024 revision) per
            # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf, https://www.irs.gov/pub/irs-pdf/f6251.pdf.
            "Form 6251 line 11 AMT owed (no treaty re-sourcing applied to regular tax baseline). Carried to Schedule 2 line 2 / Form 1040 line 17.",
            "26 U.S.C. § 55(a); Instructions for Form 6251",
            f"{USC_55_URL} | https://www.irs.gov/forms-pubs/about-form-6251",
            precision_note="max(0, tentative minimum − AMTFTC − regular tax after FTC), floored at zero.",
        ),
        USLawStage2025(
            "amt_owed_with_treaty_resourcing",
            amt_treaty.amt_owed_usd,
            "Form 6251 line 11 AMT owed in the treaty re-sourcing scenario (regular_tax − post-Pub-514 allowed FTC as the comparison baseline).",
            "26 U.S.C. § 55(a); IRS Publication 514; Instructions for Form 6251",
            f"{USC_55_URL} | {IRS_P514} | https://www.irs.gov/forms-pubs/about-form-6251",
            precision_note="Same § 55(a) formula as amt_owed but using the treaty-resourced regular-tax-after-FTC baseline.",
        ),
        USLawStage2025(
            "net_investment_income",
            niit.net_investment_income_usd,
            "Net investment income base before applying the modified-AGI threshold.",
            "26 U.S.C. § 1411",
            USC_1411_URL,
            precision_note="Includes 26 U.S.C. § 1411 and Form 8960 NII inputs plus the explicit staking-income posture.",
        ),
        USLawStage2025(
            "niit",
            niit.niit_usd,
            "Net investment income tax.",
            "26 U.S.C. § 1411; Instructions for Form 8960",
            f"{USC_1411_URL} | {IRS_I8960}",
            precision_note="Computed as 3.8 percent of the lesser of NII and MAGI excess under 26 U.S.C. § 1411 and Form 8960.",
        ),
        USLawStage2025(
            "refund_if_positive_else_balance_due",
            refund_or_balance,
            "Estimated result after payments without treaty re-sourcing.",
            "Instructions for Form 1040",
            IRS_I1040,
            precision_note="Applies Form 1040 payment/refund arithmetic after regular tax and NIIT.",
        ),
        USLawStage2025(
            "refund_if_positive_else_balance_due_with_treaty_resourcing",
            refund_or_balance_with_treaty,
            "Estimated result after payments if the treaty re-sourcing credit is claimed and allowed as modeled.",
            "IRS Publication 514; Germany treaty technical explanation",
            f"{IRS_P514} | {IRS_GERMANY_TECH}",
            precision_note="Applies the Publication 514 treaty credit before the Form 1040 refund/balance presentation.",
        ),
    )


__all__ = [
    "US_EXECUTION_CONTEXT_KEY",
    "execute_us_rule_graph",
    "us_assessment_from_final_facts",
    "us_initial_facts_2025",
    "us_initial_fingerprints_2025",
    "us_law_rules_2025",
    "us25_00_filing_position",
    "us25_01_wage_translation",
    "us25_02_income_side_inputs",
    "us25_02a_schedule_c",
    "us25_03_capital_buckets",
    "us25_04_section_1256",
    "us25_05_capital_loss_line_7a",
    "us25_06_preferential_capital_base",
    "us25_07_agi",
    "us25_feie",
    "us25_08_taxable_income",
    "us25_08a_qbi_gate",
    "us25_09_regular_tax",
    "us25_10_form_1116_preferential_gate",
    "us25_11_ftc_denominator",
    "us25_12_ftc_limitations",
    "us25_13_foreign_tax_available",
    "us25_14_baseline_allowed_ftc",
    "us25_15_treaty_us_source_dividends",
    "us25_16_treaty_average_tax_floor",
    "us25_17_treaty_german_residual_cap",
    "us25_18_treaty_additional_ftc",
    "us25_19_allowed_ftc",
    "us25_amt_amti",
    "us25_amt_tentative",
    "us25_amt_ftc_and_compare",
    "us25_se_tax",
    "us25_additional_medicare",
    "us25_20_niit",
    "us25_21_payments",
    "us25_fatca_fbar_determination",
]
