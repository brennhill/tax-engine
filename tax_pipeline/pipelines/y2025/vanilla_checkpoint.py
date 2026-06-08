from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from tax_pipeline.y2025.germany_law import (
    JointOrdinaryInputs2025,
    PersonOrdinaryInputs2025,
    compute_joint_ordinary_assessment_2025,
)
from tax_pipeline.y2025.us_law import (
    USAssessmentInputs2025,
    USCapitalSourceFacts2025,
    USFTCInputs2025,
    USReturnProfile2025,
    USTreatyInputs2025,
    compute_us_assessment_2025,
)


ZERO = Decimal("0.00")


@dataclass(frozen=True)
class GermanyVanillaCheckpoint2025:
    assessment_inputs: JointOrdinaryInputs2025
    taxable_income_eur: Decimal
    income_tax_eur: Decimal
    soli_eur: Decimal
    total_tax_eur: Decimal
    refund_or_balance_due_eur: Decimal


@dataclass(frozen=True)
class USAVanillaCheckpoint2025:
    assessment_inputs: USAssessmentInputs2025
    adjusted_gross_income_usd: Decimal
    taxable_income_usd: Decimal
    regular_tax_usd: Decimal
    total_tax_usd: Decimal
    refund_or_balance_due_usd: Decimal


def derive_germany_vanilla_inputs_2025(
    inputs: JointOrdinaryInputs2025,
) -> JointOrdinaryInputs2025:
    # Keep wage facts, withholding, and prepayments, but remove all discretionary deductions
    # and non-wage income so this scenario can be checked in standard commercial software.
    people = tuple(
        replace(
            person,
            work_equipment_items=(),
            manual_work_equipment_deduction_eur=ZERO,
            home_office_days_without_visit=0,
            home_office_days_with_visit=0,
            telecom_deduction_eur=ZERO,
            employment_legal_insurance_deduction_eur=ZERO,
            cross_border_tax_help_deduction_eur=ZERO,
        )
        for person in inputs.people
    )
    return replace(
        inputs,
        people=people,
        other_income_22nr3_eur=ZERO,
        other_income_22nr3_by_person_eur=(),
    )


def compute_germany_vanilla_checkpoint_2025(
    inputs: JointOrdinaryInputs2025,
) -> GermanyVanillaCheckpoint2025:
    vanilla_inputs = derive_germany_vanilla_inputs_2025(inputs)
    assessment = compute_joint_ordinary_assessment_2025(vanilla_inputs)
    return GermanyVanillaCheckpoint2025(
        assessment_inputs=vanilla_inputs,
        taxable_income_eur=assessment.joint_taxable_income_eur,
        income_tax_eur=assessment.joint_income_tax_eur,
        soli_eur=assessment.joint_solidarity_surcharge_eur,
        total_tax_eur=assessment.joint_income_tax_eur + assessment.joint_solidarity_surcharge_eur,  # pragma: legal-math-ok § 32a EStG income tax + § 4 SolzG 1995 5.5% solidarity surcharge already produced by the rule graph (joint_income_tax_eur and joint_solidarity_surcharge_eur are declared rule outputs); this sum is a narrative-comparison total for the vanilla-checkpoint artifact, not a form-line value. Authority: https://www.gesetze-im-internet.de/estg/__32a.html and https://www.gesetze-im-internet.de/solzg_1995/__4.html
        refund_or_balance_due_eur=assessment.ordinary_refund_before_capital_eur,
    )


def derive_usa_vanilla_inputs_2025(
    inputs: USAssessmentInputs2025,
) -> USAssessmentInputs2025:
    # Keep wages, filing status, standard deduction, and the actual estimated payment, but
    # remove all non-wage income, FTC inputs, and treaty posture so this scenario isolates
    # the core wage-only Form 1040 math.
    capital_facts = USCapitalSourceFacts2025(
        ordinary_dividends_usd=ZERO,
        qualified_dividends_usd=ZERO,
        capital_gain_distributions_usd=ZERO,
        nondividend_distributions_usd=ZERO,
        foreign_tax_paid_usd=ZERO,
        interest_income_usd=ZERO,
        substitute_payments_usd=ZERO,
        staking_income_usd=ZERO,
        estimated_payment_2025_usd=inputs.capital_facts.estimated_payment_2025_usd,
        passive_ftc_carryover_2024_usd=ZERO,
        general_ftc_carryover_2024_usd=ZERO,
        german_2024_redetermination_paid_2025_eur=ZERO,
        schwab_short_box_a_gain_usd=ZERO,
        schwab_short_box_b_gain_usd=ZERO,
        schwab_long_box_d_gain_usd=ZERO,
        schwab_section_1256_total_usd=ZERO,
        jpm_short_type_a_gain_usd=ZERO,
        coinbase_short_with_basis_proceeds_usd=ZERO,
        coinbase_short_with_basis_basis_usd=ZERO,
        coinbase_short_unknown_proceeds_usd=ZERO,
        coinbase_short_unknown_basis_reconstructed_usd=ZERO,
        coinbase_long_with_basis_proceeds_usd=ZERO,
        coinbase_long_with_basis_basis_usd=ZERO,
    )
    ftc_inputs = USFTCInputs2025(
        taxpayer_gross_wages_eur=inputs.ftc_inputs.taxpayer_gross_wages_eur,
        spouse_gross_wages_eur=inputs.ftc_inputs.spouse_gross_wages_eur,
        joint_wage_side_tax_eur=ZERO,
        foreign_source_passive_dividends_usd=ZERO,
        foreign_source_qualified_dividends_usd=ZERO,
        foreign_source_net_capital_gain_usd=ZERO,
        known_positive_short_capital_gain_usd=ZERO,
        known_positive_long_capital_gain_usd=ZERO,
        conservative_positive_income_only=inputs.ftc_inputs.conservative_positive_income_only,
        allocate_joint_german_tax_by_wage_share=inputs.ftc_inputs.allocate_joint_german_tax_by_wage_share,
    )
    treaty_inputs = USTreatyInputs2025(
        use_treaty_resourcing=False,
        us_source_direct_equity_dividends_usd=ZERO,
        us_source_equity_fund_dividends_usd=ZERO,
        us_source_non_equity_fund_dividends_usd=ZERO,
    )
    profile = replace(inputs.profile, include_staking_in_niit=False)
    return replace(
        inputs,
        capital_facts=capital_facts,
        ftc_inputs=ftc_inputs,
        treaty_inputs=treaty_inputs,
        profile=profile,
    )


def compute_usa_vanilla_checkpoint_2025(
    inputs: USAssessmentInputs2025,
) -> USAVanillaCheckpoint2025:
    vanilla_inputs = derive_usa_vanilla_inputs_2025(inputs)
    assessment = compute_us_assessment_2025(vanilla_inputs)
    return USAVanillaCheckpoint2025(
        assessment_inputs=vanilla_inputs,
        adjusted_gross_income_usd=assessment.regular_tax.adjusted_gross_income_usd,
        taxable_income_usd=assessment.regular_tax.taxable_income_usd,
        regular_tax_usd=assessment.regular_tax.regular_tax_before_credits_usd,
        total_tax_usd=assessment.total_tax_usd,
        refund_or_balance_due_usd=assessment.refund_if_positive_else_balance_due_usd,
    )
