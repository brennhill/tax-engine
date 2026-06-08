from __future__ import annotations

import contextvars
import csv
import json
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.paths import YearPaths
from tax_pipeline.pipeline_context import get_pipeline_context_value
from tax_pipeline.y2025.treaty_bridge import GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY
from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.treaty_rules import TREATY_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.us_rules import US_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.us_law import (
    IRS_GERMANY_TECH,
    IRS_I1040,
    IRS_I1116,
    IRS_I8960,
    IRS_P514,
    IRS_P550,
    IRS_YEARLY_AVG_RATES,
    USC_1_URL,
    USC_61_URL,
    USC_63_URL,
    USC_904_URL,
    USC_1411_URL,
    compute_us_assessment_2025,
)
from tax_pipeline.pipelines.y2025.vanilla_checkpoint import (
    compute_usa_vanilla_checkpoint_2025,
)
from tax_pipeline.postures import get_posture_definition
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28


# WS-5D (invariant migration plan §7): workspace resolution is lazy. The
# previous module-level ``YEAR_PATHS = active_year_paths(...)`` fired
# filesystem ``stat`` calls at import time and froze the resolved paths,
# which broke the Phase-1/Phase-2/Phase-3 separation the audit graph
# depends on. The cache is held in a ``ContextVar`` so parallel pipeline
# runs in the same process each see their own resolved paths.
_YEAR_PATHS_VAR: contextvars.ContextVar[YearPaths | None] = contextvars.ContextVar(
    "us_model_year_paths",
    default=None,
)
_STEPS_VAR: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "us_model_steps",
    default=None,
)


def _year_paths() -> YearPaths:
    cached = _YEAR_PATHS_VAR.get()
    if cached is not None:
        return cached
    resolved = active_year_paths(Path(__file__), default_year=2025)
    _YEAR_PATHS_VAR.set(resolved)
    return resolved


def _steps() -> Path:
    cached = _STEPS_VAR.get()
    if cached is not None:
        return cached
    resolved = analysis_root(Path(__file__), default_year=2025)
    _STEPS_VAR.set(resolved)
    return resolved


def reset_year_paths() -> None:
    _YEAR_PATHS_VAR.set(None)
    _STEPS_VAR.set(None)


def _results_json() -> Path:
    return _steps() / "us-tax-estimate.json"


def _summary_md() -> Path:
    return _steps() / "us-tax-estimate.md"


def _trace_csv() -> Path:
    return _steps() / "us-tax-trace.csv"


def _audit_note_md() -> Path:
    return _steps() / "us-audit-note.md"


def __getattr__(name: str):
    """Compatibility shim for legacy module-attribute access.

    Tests in ``tests/y2025/test_year_pipeline.py`` read ``us_model.RESULTS_JSON``
    and similar names directly. Each access triggers the lazy resolver.
    ``mock.patch.object`` still works because it sets a real module
    attribute that shadows ``__getattr__``.
    """
    if name == "YEAR_PATHS":
        return _year_paths()
    if name == "STEPS":
        return _steps()
    if name == "RESULTS_JSON":
        return _results_json()
    if name == "SUMMARY_MD":
        return _summary_md()
    if name == "TRACE_CSV":
        return _trace_csv()
    if name == "AUDIT_NOTE_MD":
        return _audit_note_md()
    raise AttributeError(f"module 'us_model' has no attribute {name!r}")


def round_cents(amount_usd: Decimal) -> Decimal:
    return amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(amount_usd: Decimal) -> str:
    return format(round_cents(amount_usd), "f")


def fmt_stage_amount(stage) -> str:
    if stage.step == "eur_per_usd_yearly_average_2025":
        return format(stage.amount, "f")
    return fmt(stage.amount)


def _bool_label(value: bool) -> str:
    return "yes" if value else "no"


def _filing_status_summary(profile) -> str:
    if profile.spouse_name_for_mfs_line:
        return f"{profile.filing_status_label.lower()} with NRA spouse not included on the U.S. return"
    if profile.joint_return_with_nra_spouse_election:
        return f"{profile.filing_status_label.lower()} with explicit NRA-spouse joint-return election"
    return profile.filing_status_label.lower()


def _usa_posture_from_profile(profile) -> str:
    filing_status = profile.filing_status_label.strip().lower()
    if filing_status == "single":
        return "single"
    if filing_status == "married filing separately":
        return "mfs_nra_spouse" if profile.spouse_name_for_mfs_line else "married_separate"
    if filing_status == "married filing jointly":
        return "married_joint"
    raise NotImplementedError(f"Unsupported U.S. filing status label {profile.filing_status_label!r}.")


def main() -> None:
    inputs = load_us_assessment_inputs_2025(
        _year_paths(),
        germany_treaty_dividend_items=get_pipeline_context_value(
            GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY,
            None,
        ),
    )
    get_posture_definition("usa", _usa_posture_from_profile(inputs.profile))
    assessment = compute_us_assessment_2025(inputs)
    # I5 / LEAK-4 fix: capture the post-treaty allowed-FTC sum produced
    # by ``US25-19A-ALLOWED-FTC-AFTER-RESOURCING`` BEFORE the vanilla
    # checkpoint re-runs the U.S. rule graph (which would overwrite the
    # ``US_EXECUTION_CONTEXT_KEY`` with the no-treaty execution).
    # Authority: 26 U.S.C. §§ 901, 904 + IRS Pub. 514 worksheet line 21
    # (Form 1116 line 33). The value lives at
    # ``us.stage.total_allowed_ftc_after_treaty_resourcing_usd`` in the
    # rule graph's final facts.
    us_execution = get_pipeline_context_value(US_EXECUTION_CONTEXT_KEY)
    if us_execution is None:
        raise RuntimeError(
            "U.S. rule-graph execution missing from pipeline context; "
            "compute_us_assessment_2025 must run before us_model.main reads "
            "us.stage.total_allowed_ftc_after_treaty_resourcing_usd."
        )
    total_allowed_ftc_after_treaty = us_execution.final_facts[
        "us.stage.total_allowed_ftc_after_treaty_resourcing_usd"
    ]["total_allowed_ftc_after_treaty_resourcing_usd"]
    # A2 (FORM-MAPPING-FOLLOWUP): Form 1040 line 22 = line 18 minus line
    # 21 (tax after nonrefundable credits, before additional taxes on
    # Schedule 2). Surfaced as a declared rule output by the
    # US25-21-PAYMENTS stage so the rendered 1040 walks 16 / 17 / 19 /
    # 20 / 22 / 23 instead of jumping from 21 to 23. Both versions
    # (no-treaty baseline + treaty-resourced) are surfaced; the
    # renderer reads the treaty-resourced version under the chosen
    # filing posture. Authority:
    #   - Form 1040 instructions (2025): https://www.irs.gov/instructions/i1040gi
    line_22_after_credits = us_execution.final_facts[
        "us.tax.line_22_after_credits_usd"
    ]
    line_22_after_credits_with_treaty = us_execution.final_facts[
        "us.tax.line_22_after_credits_with_treaty_resourcing_usd"
    ]
    # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line-level decomposition.
    # Each scalar is a declared rule output produced by US25-AMT-FTC-AND-
    # COMPARE / US25-SE-TAX / US25-ADDITIONAL-MEDICARE / US25-20-NIIT /
    # US25-21-PAYMENTS. The projection here is a pure 1:1 read-out so the
    # Schedule 2 renderer transits ``legal_value_entry`` with the
    # executor's StageResult fingerprint at the form-line boundary
    # (invariants I2 / I11). No Decimal arithmetic on legal output keys
    # outside the rule graph (invariant I5).
    # Authority: Schedule 2 (IRS-VERIFIED 2026-05-10 against the 2025
    # revision — https://www.irs.gov/pub/irs-pdf/f1040s2.pdf): AMT moved
    # from Schedule 2 line 1 (2024 revision) to line 2 (2025 revision).
    # The fact key ``us.tax.schedule_2_line_1_amt_usd`` retains 2024 line-1
    # numbering for fingerprint stability across the audit graph; the
    # rendered IRS line label comes from the schema TOML.
    #   https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    schedule_2_line_1_amt = us_execution.final_facts["us.tax.schedule_2_line_1_amt_usd"]
    schedule_2_line_3_total_amt = us_execution.final_facts[
        "us.tax.schedule_2_line_3_total_amt_usd"
    ]
    schedule_2_line_4_se_tax = us_execution.final_facts[
        "us.tax.schedule_2_line_4_se_tax_usd"
    ]
    schedule_2_line_11_additional_medicare = us_execution.final_facts[
        "us.tax.schedule_2_line_11_additional_medicare_usd"
    ]
    schedule_2_line_12_niit = us_execution.final_facts[
        "us.tax.schedule_2_line_12_niit_usd"
    ]
    schedule_2_line_21_total_other_taxes = us_execution.final_facts[
        "us.tax.schedule_2_line_21_total_other_taxes_usd"
    ]
    # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line-level decomposition.
    # Each value is a 1:1 read of a declared rule output (US25-19A for
    # line 1). No Decimal arithmetic on legal output keys outside the
    # rule graph (invariant I5). The pre-B2 ``us_treaty_packet.py:147``
    # Decimal addition (allowed_general + allowed_passive +
    # treaty_resourcing_additional) is replaced by a single read of
    # ``us.tax.schedule_3_line_1_ftc_total_usd``.
    #
    # The Pub. 514 worksheet line 21 add-on for treaty re-sourcing is
    # surfaced separately from any Schedule 3 line because Schedule 3
    # line 11 is "Excess Social Security / Tier 1 RRTA tax withheld" per
    # IRS Schedule 3 line numbering — NOT an FTC line. The add-on
    # actually flows into Form 1116 Part III line 12 / Part IV line 32
    # (and into Schedule 3 line 1 only via the post-cap allowed FTC).
    # Authority: Schedule 3 (2024 revision):
    #   https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
    schedule_3_line_1_ftc_total = us_execution.final_facts[
        "us.tax.schedule_3_line_1_ftc_total_usd"
    ]
    # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level decomposition
    # (Additional Medicare Tax). Each value is a 1:1 read of a declared
    # rule output produced by US25-ADDITIONAL-MEDICARE. No Decimal
    # arithmetic on legal output keys outside the rule graph (I5).
    # Authority: Form 8959 instructions:
    #   https://www.irs.gov/forms-pubs/about-form-8959
    form_8959_lines = {
        key: us_execution.final_facts[key]
        for key in (
            "us.tax.form_8959_line_1_medicare_wages_usd",
            "us.tax.form_8959_line_4_total_medicare_wages_usd",
            "us.tax.form_8959_line_5_threshold_usd",
            "us.tax.form_8959_line_6_wages_excess_usd",
            "us.tax.form_8959_line_7_addtl_medicare_on_wages_usd",
            "us.tax.form_8959_line_8_se_taxable_usd",
            "us.tax.form_8959_line_11_residual_threshold_usd",
            "us.tax.form_8959_line_13_addtl_medicare_on_se_usd",
            "us.tax.form_8959_line_18_total_addtl_medicare_usd",
        )
    }
    # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level decomposition
    # (US25-SE-TAX). Each value is a 1:1 read of a declared rule output.
    # No Decimal arithmetic on legal output keys (I5).
    # Authority: Schedule SE instructions:
    #   https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
    schedule_se_lines = {
        key: us_execution.final_facts[key]
        for key in (
            "us.tax.schedule_se_line_2_net_se_earnings_usd",
            "us.tax.schedule_se_line_3_total_se_earnings_usd",
            "us.tax.schedule_se_line_4a_se_taxable_usd",
            "us.tax.schedule_se_line_4c_se_taxable_usd",
            "us.tax.schedule_se_line_6_combined_se_base_usd",
            "us.tax.schedule_se_line_8a_w2_ss_wages_usd",
            "us.tax.schedule_se_line_10_oasdi_tax_usd",
            "us.tax.schedule_se_line_11_medicare_tax_usd",
            "us.tax.schedule_se_line_12_total_se_tax_usd",
        )
    }
    # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 line-level decomposition
    # (US25-20-NIIT). Each value is a 1:1 read of a declared rule output
    # (Part I lines 1, 2, 5a-5d; line 8 total investment income; line
    # 12 net investment income). No Decimal arithmetic on legal output
    # keys outside the rule graph (I5).
    # Authority: Form 8960 instructions:
    #   https://www.irs.gov/forms-pubs/about-form-8960
    form_8960_lines = {
        key: us_execution.final_facts[key]
        for key in (
            "us.tax.form_8960_line_1_interest_usd",
            "us.tax.form_8960_line_2_ordinary_dividends_usd",
            "us.tax.form_8960_line_5a_capital_gain_loss_usd",
            "us.tax.form_8960_line_5b_non_section_1411_adj_usd",
            "us.tax.form_8960_line_7_other_modifications_usd",
            "us.tax.form_8960_line_11_total_deductions_usd",
            "us.tax.form_8960_line_5c_cfc_pfic_adj_usd",
            "us.tax.form_8960_line_5d_combined_capital_usd",
            "us.tax.form_8960_line_8_total_investment_income_usd",
            "us.tax.form_8960_line_12_net_investment_income_usd",
        )
    }
    # 26 U.S.C. § 24 — pull the executed CTC + ODC outputs from the rule
    # graph so ``us-tax-estimate.json`` carries the Schedule 8812 line
    # values. The eight keys below match the US25-CTC-AND-ODC stage's
    # declared ``output_keys`` exactly so this block stays a pure
    # projection (no Decimal arithmetic on legal output keys, per
    # invariant I5). Authority:
    #   - 26 U.S.C. § 24 — https://www.law.cornell.edu/uscode/text/26/24
    #   - IRS Schedule 8812 (2025) instructions
    #     https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
    ctc_facts = {
        key: us_execution.final_facts[key]
        for key in (
            # Schedule 8812 (2025) qualifying-children counts (Lines 4 / 6).
            "us.ctc.qualifying_ctc_count",
            "us.ctc.qualifying_odc_count",
            "us.ctc.gross_ctc_usd",
            "us.ctc.gross_odc_usd",
            "us.ctc.combined_pre_phaseout_usd",
            # § 24(b)(2) phase-out threshold (Line 9), Modified AGI
            # (Line 10), and the regular-tax-after-FTC ordering cap from
            # Credit Limit Worksheet A (Line 13).
            "us.ctc.phaseout_threshold_usd",
            "us.ctc.modified_agi_usd",
            "us.ctc.regular_tax_after_ftc_usd",
            "us.ctc.phaseout_reduction_usd",
            "us.ctc.combined_post_phaseout_usd",
            "us.ctc.nonrefundable_portion_usd",
            # § 24(d)(1) refundable-ACTC sub-steps: remaining-CTC ceiling
            # (Line 16a), per-child cap (Line 16b), earned-income input
            # (Line 18a), $2,500 floor (Line 19), excess (Line 20), and
            # 15 % phase-in (Line 21).
            "us.ctc.remaining_ctc_for_refundable_usd",
            "us.ctc.refundable_actc_cap_usd",
            "us.ctc.earned_income_usd",
            "us.ctc.earned_income_floor_usd",
            "us.ctc.earned_income_excess_usd",
            "us.ctc.refundable_actc_earned_income_phase_in_usd",
            "us.ctc.refundable_actc_usd",
            "us.ctc.total_credit_usd",
        )
    }
    # DBA-USA Art. 28 LOB qualification + 26 U.S.C. § 6114 / Reg.
    # § 301.6114-1 Form 8833 disclosure flag. Captured BEFORE the
    # ``compute_usa_vanilla_checkpoint_2025`` call below — that helper
    # re-runs the U.S. rule graph with ``use_treaty_resourcing=False``
    # and would overwrite the ``TREATY_EXECUTION_CONTEXT_KEY`` execution
    # with a no-treaty replay where ``treaty.form_8833_required`` is
    # always ``False`` (mirrors the LEAK-4 capture pattern for
    # ``total_allowed_ftc_after_treaty_resourcing_usd`` above). The
    # value is the literal rule output produced by the
    # ``TREATY25-LOB-QUALIFICATION`` stage; no Decimal arithmetic on
    # legal output keys here (invariant I5).
    # https://www.law.cornell.edu/uscode/text/26/6114
    # https://www.law.cornell.edu/cfr/text/26/301.6114-1
    treaty_execution = get_pipeline_context_value(TREATY_EXECUTION_CONTEXT_KEY)
    if treaty_execution is None:
        raise RuntimeError(
            "Treaty rule-graph execution missing from pipeline context; "
            "compute_us_assessment_2025 must run before us_model.main reads "
            "treaty.form_8833_required."
        )
    lob_form_8833_required = bool(treaty_execution.final_facts["treaty.form_8833_required"])
    lob_qualified = bool(treaty_execution.final_facts["treaty.lob_qualified"])
    lob_category = str(treaty_execution.final_facts["treaty.lob_category"])
    vanilla_checkpoint = compute_usa_vanilla_checkpoint_2025(inputs)
    filing_status_summary = _filing_status_summary(inputs.profile)
    filing_status_label_lower = inputs.profile.filing_status_label.lower()
    estimated_payment_text = f"{fmt(inputs.capital_facts.estimated_payment_2025_usd)} USD"
    refund_without_treaty = max(Decimal("0.00"), assessment.refund_if_positive_else_balance_due_usd)
    amount_owed_without_treaty = max(Decimal("0.00"), -assessment.refund_if_positive_else_balance_due_usd)
    refund_with_treaty = max(Decimal("0.00"), assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd)
    amount_owed_with_treaty = max(Decimal("0.00"), -assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd)

    results = {
        "filing_assumptions": {
            "filing_status": inputs.profile.filing_status_label,
            "nra_spouse_name": inputs.profile.spouse_name_for_mfs_line,
            "joint_return_spouse_name": inputs.profile.joint_return_spouse_name,
            "joint_return_with_nra_spouse_election": _bool_label(inputs.profile.joint_return_with_nra_spouse_election),
            "niit_threshold_usd": fmt(inputs.constants.niit_threshold_usd),
            "accrued_basis_ftc": _bool_label(inputs.profile.accrued_basis_ftc),
            "treaty_resourcing_credit_included": "scenario only",
        },
        "manual_positions": {
            "include_staking_in_niit": _bool_label(inputs.profile.include_staking_in_niit),
            "use_treaty_resourcing": _bool_label(inputs.treaty_inputs.use_treaty_resourcing),
            "ftc_denominator_positive_income_only": _bool_label(inputs.ftc_inputs.conservative_positive_income_only),
            "allocate_joint_german_tax_by_wage_share": _bool_label(inputs.ftc_inputs.allocate_joint_german_tax_by_wage_share),
            "germany_treaty_dividend_packet_used": _bool_label(
                inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd is not None
                or inputs.treaty_inputs.german_residence_credit_for_us_tax_usd is not None
            ),
        },
        "income": {
            "wages_usd": fmt(assessment.regular_tax.wages_usd),
            "ordinary_dividends_usd": fmt(inputs.capital_facts.ordinary_dividends_usd),
            "qualified_dividends_usd": fmt(inputs.capital_facts.qualified_dividends_usd),
            "interest_income_usd": fmt(inputs.capital_facts.interest_income_usd),
            "capital_gain_distributions_usd": fmt(inputs.capital_facts.capital_gain_distributions_usd),
            "substitute_payments_usd": fmt(inputs.capital_facts.substitute_payments_usd),
            "staking_income_usd": fmt(inputs.capital_facts.staking_income_usd),
            "nondividend_distributions_usd": fmt(inputs.capital_facts.nondividend_distributions_usd),
            "foreign_tax_paid_usd": fmt(inputs.capital_facts.foreign_tax_paid_usd),
            "schedule_1_other_income_usd": fmt(assessment.regular_tax.schedule_1_other_income_usd),
            "adjusted_gross_income_usd": fmt(assessment.regular_tax.adjusted_gross_income_usd),
            "taxable_income_usd": fmt(assessment.regular_tax.taxable_income_usd),
        },
        "capital": {
            "short_box_a_usd": fmt(assessment.capital.short_box_a_usd),
            "short_box_b_usd": fmt(assessment.capital.short_box_b_usd),
            "short_box_h_usd": fmt(assessment.capital.short_box_h_usd),
            "short_term_total_usd": fmt(assessment.capital.short_term_total_usd),
            "long_box_d_usd": fmt(assessment.capital.long_box_d_usd),
            "long_box_k_usd": fmt(assessment.capital.long_box_k_usd),
            "capital_gain_distributions_usd": fmt(assessment.capital.capital_gain_distributions_usd),
            "long_term_total_with_cgd_usd": fmt(assessment.capital.long_term_total_with_cgd_usd),
            "section_1256_total_usd": fmt(assessment.capital.section_1256_total_usd),
            "section_1256_short_term_usd": fmt(assessment.capital.section_1256_short_term_usd),
            "section_1256_long_term_usd": fmt(assessment.capital.section_1256_long_term_usd),
            "net_capital_before_1256_usd": fmt(assessment.capital.net_capital_before_1256_usd),
            "net_capital_after_1256_usd": fmt(assessment.capital.net_capital_after_1256_usd),
            "capital_loss_deduction_2025_usd": fmt(assessment.capital.capital_loss_deduction_2025_usd),
            "tentative_capital_loss_carryforward_2026_usd": fmt(assessment.capital.tentative_capital_loss_carryforward_2026_usd),
            "form_1040_line_7a_usd": fmt(assessment.capital.form_1040_line_7a_usd),
            "digital_asset_transaction_present": _bool_label(assessment.capital.digital_asset_transaction_present),
        },
        "tax": {
            "regular_tax_before_credits_usd": fmt(assessment.regular_tax.regular_tax_before_credits_usd),
            "ordinary_tax_component_usd": fmt(assessment.regular_tax.ordinary_tax_component_usd),
            "qualified_dividend_tax_component_usd": fmt(assessment.regular_tax.qualified_dividend_tax_component_usd),
            "niit_usd": fmt(assessment.niit.niit_usd),
            # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 2 / Form 1040
            # line 17. https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
            # F-US-1: § 55 AMT projection. ``amt_owed_usd`` carries the
            # treaty-resourced AMT (Schedule 2 line 2 / Form 1040 line 17 in
            # the chosen treaty packet — 2025 revision; was Schedule 2 line 1
            # on 2024 revision); ``amt_owed_without_treaty_resourcing_usd``
            # is the no-treaty AMT used by the baseline-no-treaty total_tax.
            "amt_owed_usd": fmt(assessment.amt_with_treaty_resourcing.amt_owed_usd),
            "amt_owed_without_treaty_resourcing_usd": fmt(assessment.amt.amt_owed_usd),
            "amti_usd": fmt(assessment.amt.amti_usd),
            "amt_exemption_usd": fmt(assessment.amt.exemption_usd),
            "amti_after_exemption_usd": fmt(assessment.amt.amti_after_exemption_usd),
            "amt_tentative_min_tax_usd": fmt(assessment.amt.tentative_min_tax_usd),
            "amtftc_usd": fmt(assessment.amt.amtftc_usd),
            "amt_preferential_amti_usd": fmt(assessment.amt.preferential_amti_usd),
            "total_tax_usd": fmt(assessment.total_tax_usd),
            "total_tax_with_treaty_resourcing_usd": fmt(assessment.total_tax_with_treaty_resourcing_usd),
            # A2 (FORM-MAPPING-FOLLOWUP): Form 1040 line 22 (tax after
            # nonrefundable credits, before additional taxes on
            # Schedule 2). Sourced from declared rule outputs
            # ``us.tax.line_22_after_credits_usd`` /
            # ``us.tax.line_22_after_credits_with_treaty_resourcing_usd``
            # produced by US25-21-PAYMENTS — pure 1:1 projection, no
            # Decimal arithmetic on legal output keys (invariant I5).
            "line_22_after_credits_usd": fmt(line_22_after_credits),
            "line_22_after_credits_with_treaty_resourcing_usd": fmt(
                line_22_after_credits_with_treaty
            ),
            # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line-level
            # decomposition (lines 1, 3, 4, 11, 12, 21). 1:1 projection of
            # declared rule outputs; no Decimal arithmetic on legal output
            # keys outside the rule graph (invariant I5).
            # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
            "schedule_2_line_1_amt_usd": fmt(schedule_2_line_1_amt),
            "schedule_2_line_3_total_amt_usd": fmt(schedule_2_line_3_total_amt),
            "schedule_2_line_4_se_tax_usd": fmt(schedule_2_line_4_se_tax),
            "schedule_2_line_11_additional_medicare_usd": fmt(
                schedule_2_line_11_additional_medicare
            ),
            "schedule_2_line_12_niit_usd": fmt(schedule_2_line_12_niit),
            "schedule_2_line_21_total_other_taxes_usd": fmt(
                schedule_2_line_21_total_other_taxes
            ),
            # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line 1 (Foreign
            # Tax Credit, post-treaty). Pure 1:1 projection of the
            # declared rule output (invariant I5). Per IRS Schedule 3
            # (2024 / 2025) line numbering, line 6c is the Adoption
            # credit (Part I) and line 11 is "Excess Social Security
            # and Tier 1 RRTA tax withheld" (Part II) — neither is the
            # treaty FTC add-on, so the engine surfaces only line 1.
            # https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
            "schedule_3_line_1_ftc_total_usd": fmt(schedule_3_line_1_ftc_total),
            # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level
            # decomposition (Additional Medicare Tax). 1:1 projection of
            # declared rule outputs (invariant I5).
            # https://www.irs.gov/forms-pubs/about-form-8959
            "form_8959_line_1_medicare_wages_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_1_medicare_wages_usd"]
            ),
            "form_8959_line_4_total_medicare_wages_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_4_total_medicare_wages_usd"]
            ),
            "form_8959_line_5_threshold_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_5_threshold_usd"]
            ),
            "form_8959_line_6_wages_excess_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_6_wages_excess_usd"]
            ),
            "form_8959_line_7_addtl_medicare_on_wages_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_7_addtl_medicare_on_wages_usd"]
            ),
            "form_8959_line_8_se_taxable_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_8_se_taxable_usd"]
            ),
            "form_8959_line_11_residual_threshold_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_11_residual_threshold_usd"]
            ),
            "form_8959_line_13_addtl_medicare_on_se_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_13_addtl_medicare_on_se_usd"]
            ),
            "form_8959_line_18_total_addtl_medicare_usd": fmt(
                form_8959_lines["us.tax.form_8959_line_18_total_addtl_medicare_usd"]
            ),
            # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level
            # decomposition. Pure 1:1 projection of declared rule outputs.
            # https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
            "schedule_se_line_2_net_se_earnings_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_2_net_se_earnings_usd"]
            ),
            "schedule_se_line_3_total_se_earnings_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_3_total_se_earnings_usd"]
            ),
            "schedule_se_line_4a_se_taxable_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_4a_se_taxable_usd"]
            ),
            "schedule_se_line_4c_se_taxable_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_4c_se_taxable_usd"]
            ),
            "schedule_se_line_6_combined_se_base_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_6_combined_se_base_usd"]
            ),
            "schedule_se_line_8a_w2_ss_wages_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_8a_w2_ss_wages_usd"]
            ),
            "schedule_se_line_10_oasdi_tax_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_10_oasdi_tax_usd"]
            ),
            "schedule_se_line_11_medicare_tax_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_11_medicare_tax_usd"]
            ),
            "schedule_se_line_12_total_se_tax_usd": fmt(
                schedule_se_lines["us.tax.schedule_se_line_12_total_se_tax_usd"]
            ),
            # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 line-level
            # decomposition. Pure 1:1 projection of declared rule
            # outputs. https://www.irs.gov/forms-pubs/about-form-8960
            "form_8960_line_1_interest_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_1_interest_usd"]
            ),
            "form_8960_line_2_ordinary_dividends_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_2_ordinary_dividends_usd"]
            ),
            "form_8960_line_5a_capital_gain_loss_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_5a_capital_gain_loss_usd"]
            ),
            "form_8960_line_5b_non_section_1411_adj_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_5b_non_section_1411_adj_usd"]
            ),
            "form_8960_line_5c_cfc_pfic_adj_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_5c_cfc_pfic_adj_usd"]
            ),
            "form_8960_line_5d_combined_capital_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_5d_combined_capital_usd"]
            ),
            "form_8960_line_7_other_modifications_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_7_other_modifications_usd"]
            ),
            "form_8960_line_8_total_investment_income_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_8_total_investment_income_usd"]
            ),
            "form_8960_line_11_total_deductions_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_11_total_deductions_usd"]
            ),
            "form_8960_line_12_net_investment_income_usd": fmt(
                form_8960_lines["us.tax.form_8960_line_12_net_investment_income_usd"]
            ),
        },
        "ftc": {
            "general_taxable_income_for_ftc_usd": fmt(assessment.ftc.general_taxable_income_for_ftc_usd),
            "passive_taxable_income_for_ftc_usd": fmt(assessment.ftc.passive_taxable_income_for_ftc_usd),
            "general_ftc_limitation_usd": fmt(assessment.ftc.general_ftc_limitation_usd),
            "passive_ftc_limitation_usd": fmt(assessment.ftc.passive_ftc_limitation_usd),
            "current_year_general_foreign_tax_usd": fmt(assessment.ftc.current_year_general_foreign_tax_usd),
            "current_year_passive_foreign_tax_usd": fmt(assessment.ftc.current_year_passive_foreign_tax_usd),
            "allowed_general_ftc_usd": fmt(assessment.ftc.allowed_general_ftc_usd),
            "allowed_passive_ftc_usd": fmt(assessment.ftc.allowed_passive_ftc_usd),
            "total_allowed_ftc_usd": fmt(assessment.ftc.total_allowed_ftc_usd),
            "total_allowed_ftc_after_treaty_resourcing_usd": fmt(total_allowed_ftc_after_treaty),
            "passive_ftc_carryover_2024_usd": fmt(inputs.capital_facts.passive_ftc_carryover_2024_usd),
            "general_ftc_carryover_2024_usd": fmt(inputs.capital_facts.general_ftc_carryover_2024_usd),
            "german_2024_redetermination_paid_2025_eur": fmt(inputs.capital_facts.german_2024_redetermination_paid_2025_eur),
        },
        "treaty_resourcing": {
            "us_source_dividends_usd": fmt(assessment.treaty_resourcing.us_source_dividends_usd),
            "us_source_qualified_dividends_usd": fmt(assessment.treaty_resourcing.us_source_qualified_dividends_usd),
            "us_tax_on_us_source_dividends_usd": fmt(assessment.treaty_resourcing.us_tax_on_us_source_dividends_usd),
            "treaty_minimum_us_tax_on_us_source_dividends_usd": fmt(
                assessment.treaty_resourcing.treaty_minimum_us_tax_on_us_source_dividends_usd
            ),
            "treaty_resourcing_us_limitation_usd": fmt(
                assessment.treaty_resourcing.treaty_resourcing_us_limitation_usd
            ),
            "german_precredit_tax_on_us_source_dividends_usd": fmt(
                assessment.treaty_resourcing.german_precredit_tax_on_us_source_dividends_usd
            ),
            "german_residence_credit_for_us_tax_usd": fmt(
                assessment.treaty_resourcing.german_residence_credit_for_us_tax_usd
            ),
            "worksheet_line_19_maximum_credit_usd": fmt(
                assessment.treaty_resourcing.worksheet_line_19_maximum_credit_usd
            ),
            "worksheet_line_20c_residual_residence_country_tax_usd": fmt(
                assessment.treaty_resourcing.worksheet_line_20c_residual_residence_country_tax_usd
            ),
            "worksheet_line_21_additional_credit_usd": fmt(
                assessment.treaty_resourcing.worksheet_line_21_additional_credit_usd
            ),
            "german_residual_tax_on_us_source_dividends_usd": fmt(
                assessment.treaty_resourcing.german_residual_tax_on_us_source_dividends_usd
            ),
            "treaty_resourcing_additional_ftc_usd": fmt(
                assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd
            ),
            # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): always 0.00
            # by treaty design — surfaced as a declared rule output
            # (TREATY25-18 / treaty.resourced_basket_carryover) so the
            # Form 1116 Resourced Line 10 renderer write transits the
            # I3 contract instead of a literal Decimal.
            "resourced_basket_carryover_usd": fmt(
                assessment.treaty_resourcing.resourced_basket_carryover_usd
            ),
            # DBA-USA Art. 28 LOB qualification + 26 U.S.C. § 6114 /
            # Reg. § 301.6114-1 Form 8833 disclosure flag. Plumbed from
            # the executed ``TREATY25-LOB-QUALIFICATION`` rule output
            # ``treaty.form_8833_required`` so the U.S. treaty packet
            # renderer no longer hard-codes "no" and the user actually
            # sees a Form 8833 placeholder when treaty re-sourcing is
            # claimed. Authority:
            #   - 26 U.S.C. § 6114 — https://www.law.cornell.edu/uscode/text/26/6114
            #   - 26 C.F.R. § 301.6114-1 — https://www.law.cornell.edu/cfr/text/26/301.6114-1
            "lob_qualified": "yes" if lob_qualified else "no",
            "lob_category": lob_category,
            "form_8833_required": "yes" if lob_form_8833_required else "no",
        },
        "ctc": {
            # 26 U.S.C. § 24 — Child Tax Credit + § 24(h)(4) ODC. Schedule 8812
            # walks lines 1-14 (CTC computation) and lines 15-27 (ACTC); the
            # nonrefundable portion lands on Form 1040 line 19, the refundable
            # ACTC on Form 1040 line 28. For an empty ``config/children.csv``
            # every value is zero so the demo numerics are unchanged. Each
            # value here is a 1:1 projection of a declared ``us.ctc.*`` rule
            # output (no Decimal arithmetic; invariant I5).
            # https://www.law.cornell.edu/uscode/text/26/24
            # https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
            "qualifying_ctc_count": ctc_facts["us.ctc.qualifying_ctc_count"],
            "qualifying_odc_count": ctc_facts["us.ctc.qualifying_odc_count"],
            "gross_ctc_usd": fmt(ctc_facts["us.ctc.gross_ctc_usd"]),
            "gross_odc_usd": fmt(ctc_facts["us.ctc.gross_odc_usd"]),
            "combined_pre_phaseout_usd": fmt(ctc_facts["us.ctc.combined_pre_phaseout_usd"]),
            # Schedule 8812 Line 9 / 10 / 13 — phase-out threshold, MAGI,
            # and the regular-tax-after-FTC ordering cap from the Credit
            # Limit Worksheet A. § 24(b)(2) / § 24(b)(3).
            "phaseout_threshold_usd": fmt(ctc_facts["us.ctc.phaseout_threshold_usd"]),
            "modified_agi_usd": fmt(ctc_facts["us.ctc.modified_agi_usd"]),
            "regular_tax_after_ftc_usd": fmt(ctc_facts["us.ctc.regular_tax_after_ftc_usd"]),
            "phaseout_reduction_usd": fmt(ctc_facts["us.ctc.phaseout_reduction_usd"]),
            "combined_post_phaseout_usd": fmt(ctc_facts["us.ctc.combined_post_phaseout_usd"]),
            "nonrefundable_portion_usd": fmt(ctc_facts["us.ctc.nonrefundable_portion_usd"]),
            # Schedule 8812 Line 16a / 16b / 18a / 19 / 20 / 21 — the
            # § 24(d) refundable-ACTC sub-steps surfaced as declared rule
            # outputs so each form-line write traces to a fingerprint.
            "remaining_ctc_for_refundable_usd": fmt(ctc_facts["us.ctc.remaining_ctc_for_refundable_usd"]),
            "refundable_actc_cap_usd": fmt(ctc_facts["us.ctc.refundable_actc_cap_usd"]),
            "earned_income_usd": fmt(ctc_facts["us.ctc.earned_income_usd"]),
            "earned_income_floor_usd": fmt(ctc_facts["us.ctc.earned_income_floor_usd"]),
            "earned_income_excess_usd": fmt(ctc_facts["us.ctc.earned_income_excess_usd"]),
            "refundable_actc_earned_income_phase_in_usd": fmt(
                ctc_facts["us.ctc.refundable_actc_earned_income_phase_in_usd"]
            ),
            "refundable_actc_usd": fmt(ctc_facts["us.ctc.refundable_actc_usd"]),
            "total_credit_usd": fmt(ctc_facts["us.ctc.total_credit_usd"]),
        },
        "payments": {
            "estimated_payment_usd": fmt(inputs.capital_facts.estimated_payment_2025_usd),
            "refund_if_positive_else_balance_due_usd": fmt(
                assessment.refund_if_positive_else_balance_due_usd
            ),
            "refund_without_treaty_resourcing_usd": fmt(refund_without_treaty),
            "amount_owed_without_treaty_resourcing_usd": fmt(amount_owed_without_treaty),
            "refund_if_positive_else_balance_due_with_treaty_resourcing_usd": fmt(
                assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd
            ),
            "refund_with_treaty_resourcing_usd": fmt(refund_with_treaty),
            "amount_owed_with_treaty_resourcing_usd": fmt(amount_owed_with_treaty),
        },
        "vanilla_checkpoint": {
            "adjusted_gross_income_usd": fmt(vanilla_checkpoint.adjusted_gross_income_usd),
            "taxable_income_usd": fmt(vanilla_checkpoint.taxable_income_usd),
            "regular_tax_usd": fmt(vanilla_checkpoint.regular_tax_usd),
            "total_tax_usd": fmt(vanilla_checkpoint.total_tax_usd),
            "refund_or_balance_due_usd": fmt(vanilla_checkpoint.refund_or_balance_due_usd),
        },
        # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 2555 (Foreign
        # Earned Income Exclusion) per-line scalars from US25-FEIE. The
        # ``elected`` flag gates the renderer; per-line scalars carry
        # the I11 fingerprint so each Form 2555 line traces to a
        # declared rule output. When ``elected=False`` the scalars are
        # zero (assessment.elected branch in feie_assessment_2025) —
        # the renderer emits an explicit zero packet on the rare gated
        # demo posture.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
        # https://www.irs.gov/forms-pubs/about-form-2555
        "feie": {
            "elected": bool(us_execution.final_facts["us.stage.feie"]["elected"]),
            "line_36_excluded_amount_usd": fmt(
                us_execution.final_facts["us.feie.line_36_excluded_amount_usd"]
            ),
            "line_45_housing_exclusion_usd": fmt(
                us_execution.final_facts["us.feie.line_45_housing_exclusion_usd"]
            ),
            "line_50_housing_deduction_usd": fmt(
                us_execution.final_facts["us.feie.line_50_housing_deduction_usd"]
            ),
        },
        # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 8938 (§ 6038D)
        # / FBAR (31 CFR § 1010.350) determination block. Booleans + USD
        # aggregates emitted by US25-FATCA-FBAR-DETERMINATION; the
        # renderer reads ``status`` and emits a manual-determination
        # status sheet (rather than REQUIRED / NOT REQUIRED) when the
        # workspace's foreign-financial-accounts.csv is incomplete.
        # https://www.law.cornell.edu/uscode/text/26/6038D
        # https://www.law.cornell.edu/cfr/text/31/1010.350
        # https://www.irs.gov/forms-pubs/about-form-8938
        "fatca_fbar": {
            "status": str(
                us_execution.final_facts["us.fatca.determination_status"]
            ),
            "reason": str(
                us_execution.final_facts["us.fatca.determination_reason"]
            ),
            "filing_status_label": inputs.profile.filing_status_label,
            "residency_basis": inputs.fatca_fbar_inputs.residency_basis,
            "form_8938_threshold_eoy_usd": fmt(
                us_execution.final_facts["us.fatca.form_8938_threshold_eoy_usd"]
            ),
            "form_8938_threshold_anytime_usd": fmt(
                us_execution.final_facts["us.fatca.form_8938_threshold_anytime_usd"]
            ),
            "foreign_specified_assets_max_usd": fmt(
                us_execution.final_facts["us.fatca.foreign_specified_assets_max_usd"]
            ),
            "foreign_specified_assets_eoy_usd": fmt(
                us_execution.final_facts["us.fatca.foreign_specified_assets_eoy_usd"]
            ),
            "form_8938_required": bool(
                us_execution.final_facts["us.fatca.form_8938_required"]
            ),
            "fbar_aggregate_max_balance_usd": fmt(
                us_execution.final_facts["us.fbar.aggregate_max_balance_usd"]
            ),
            "fincen_114_required": bool(
                us_execution.final_facts["us.fbar.fincen_114_required"]
            ),
            "account_count": len(inputs.fatca_fbar_inputs.accounts),
            # Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-account
            # summary surface for the manual-determination renderer. The
            # rule-output booleans / aggregates are still authoritative;
            # this list exists so the status sheet can enumerate "fill
            # in balances for these accounts" rather than emitting an
            # empty-schema placeholder. Identity rows only — no Decimal
            # legal math is performed here, and the renderer only writes
            # these out as text descriptions, not via legal_value_entry.
            "discovered_accounts": [
                {
                    "account_id": account.account_id,
                    "country": account.country,
                    "institution": account.institution,
                    "account_type": account.account_type,
                    "currency": account.currency,
                    "is_specified_foreign_financial_asset": (
                        account.is_specified_foreign_financial_asset
                    ),
                }
                for account in sorted(
                    inputs.fatca_fbar_inputs.accounts,
                    key=lambda a: a.account_id,
                )
            ],
        },
    }
    _results_json().write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    trace_rows = [
        (
            stage.step,
            fmt_stage_amount(stage),
            stage.note,
            stage.legal_reference,
            stage.authority_url,
            stage.step_type,
            stage.precision_note,
        )
        for stage in assessment.law_order_stages
    ]
    with _trace_csv().open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["step", "amount_usd", "note", "legal_reference", "authority_url", "step_type", "precision_note"])
        writer.writerows(trace_rows)

    baseline_line = (
        f"Estimated refund after the {estimated_payment_text} payment: **{fmt(assessment.refund_if_positive_else_balance_due_usd)} USD**"
        if assessment.refund_if_positive_else_balance_due_usd >= 0
        else f"Estimated balance still due after the {estimated_payment_text} payment: **{fmt(-assessment.refund_if_positive_else_balance_due_usd)} USD**"
    )
    treaty_line = (
        f"Estimated refund after the {estimated_payment_text} payment with treaty re-sourcing: **{fmt(assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd)} USD**"
        if assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd >= 0
        else f"Estimated balance still due after the {estimated_payment_text} payment with treaty re-sourcing: **{fmt(-assessment.refund_if_positive_else_balance_due_with_treaty_resourcing_usd)} USD**"
    )

    _summary_md().write_text(
        "\n".join(
            [
                "# U.S. 2025 Baseline Tax Estimate",
                "",
                "This file is generated by `python3 -m tax_pipeline.pipelines.y2025.us_model` from structured year inputs and the pure law helpers in `tax_pipeline/y2025/us_law.py`.",
                "",
                "## Locked baseline assumptions",
                f"- Filing status: {filing_status_summary}.",
                f"- FTC method: {'accrued basis' if inputs.profile.accrued_basis_ftc else 'paid basis'}.",
                f"- Passive foreign-source income currently documented: `{fmt(inputs.ftc_inputs.foreign_source_passive_dividends_usd)} USD` of dividends and `{fmt(inputs.ftc_inputs.foreign_source_net_capital_gain_usd)} USD` of net capital gain with `{fmt(inputs.capital_facts.foreign_tax_paid_usd)} USD` foreign tax.",
                f"- NIIT includes staking income: `{_bool_label(inputs.profile.include_staking_in_niit)}`.",
                "",
                "## Income and tax",
                f"- IRS 2025 yearly-average EUR/USD rate used: `{format(inputs.constants.eur_per_usd_yearly_average_2025, 'f')}`",
                f"- wages translated at that IRS yearly-average rate: **{fmt(assessment.regular_tax.wages_usd)} USD**",
                f"- adjusted gross income: {fmt(assessment.regular_tax.adjusted_gross_income_usd)} USD",
                f"- taxable income after the 2025 {filing_status_label_lower} standard deduction: {fmt(assessment.regular_tax.taxable_income_usd)} USD",
                f"- regular tax before credits: {fmt(assessment.regular_tax.regular_tax_before_credits_usd)} USD",
                f"- NIIT estimate: {fmt(assessment.niit.niit_usd)} USD",
                "",
                "## Vanilla checkpoint for commercial software comparison",
                f"- Wage income only, with the 2025 {filing_status_label_lower} standard deduction and the documented {estimated_payment_text} estimated payment kept in place.",
                "- No dividends, interest, capital gains/losses, Schedule 1 other income, NIIT, FTC, or treaty re-sourcing.",
                f"- adjusted gross income in the checkpoint: {fmt(vanilla_checkpoint.adjusted_gross_income_usd)} USD",
                f"- taxable income in the checkpoint: {fmt(vanilla_checkpoint.taxable_income_usd)} USD",
                f"- regular tax in the checkpoint: {fmt(vanilla_checkpoint.regular_tax_usd)} USD",
                f"- total tax in the checkpoint: {fmt(vanilla_checkpoint.total_tax_usd)} USD",
                f"- refund or balance due in the checkpoint after the {estimated_payment_text} payment: {fmt(vanilla_checkpoint.refund_or_balance_due_usd)} USD",
                "",
                "## FTC baseline",
                f"- general FTC limitation: {fmt(assessment.ftc.general_ftc_limitation_usd)} USD",
                f"- passive FTC limitation: {fmt(assessment.ftc.passive_ftc_limitation_usd)} USD",
                f"- allowed general FTC: {fmt(assessment.ftc.allowed_general_ftc_usd)} USD",
                f"- allowed passive FTC: {fmt(assessment.ftc.allowed_passive_ftc_usd)} USD",
                f"- total allowed FTC: {fmt(assessment.ftc.total_allowed_ftc_usd)} USD",
                "",
                "## Treaty re-sourcing scenario",
                f"- U.S.-source dividends used for the treaty analysis: {fmt(assessment.treaty_resourcing.us_source_dividends_usd)} USD",
                f"- extra U.S. tax on that dividend stack above the treaty's 15 percent floor: {fmt(assessment.treaty_resourcing.treaty_resourcing_us_limitation_usd)} USD",
                f"- German residual tax on that same dividend stack: {fmt(assessment.treaty_resourcing.german_residual_tax_on_us_source_dividends_usd)} USD",
                f"- additional treaty re-sourcing FTC modeled: {fmt(assessment.treaty_resourcing.treaty_resourcing_additional_ftc_usd)} USD",
                "",
                "## Payment position",
                baseline_line,
                treaty_line,
                f"- total tax in this baseline: {fmt(assessment.total_tax_usd)} USD",
                f"- total tax with treaty re-sourcing: {fmt(assessment.total_tax_with_treaty_resourcing_usd)} USD",
                "",
                "## Manual positions kept explicit",
                f"- FTC denominator uses documented positive-income components only: `{_bool_label(inputs.ftc_inputs.conservative_positive_income_only)}`",
                f"- Joint German wage-side tax allocated by wage share: `{_bool_label(inputs.ftc_inputs.allocate_joint_german_tax_by_wage_share)}`",
                f"- Germany treaty-dividend core outputs used for Publication 514 lines 17/18: `{_bool_label(inputs.treaty_inputs.german_precredit_tax_on_us_source_dividends_usd is not None and inputs.treaty_inputs.german_residence_credit_for_us_tax_usd is not None)}`",
                "- Treaty dividend re-sourcing fails closed unless Germany outputs the matched U.S.-source dividend gross, treaty-allowed U.S. tax, pre-credit German tax, and German credit.",
                f"- Treaty re-sourcing selected in the current filing posture: `{_bool_label(inputs.treaty_inputs.use_treaty_resourcing)}`",
                "",
                "## Official sources",
                f"- 26 U.S.C. § 61: {USC_61_URL}",
                f"- 26 U.S.C. § 63: {USC_63_URL}",
                f"- 26 U.S.C. § 1: {USC_1_URL}",
                f"- 26 U.S.C. § 904: {USC_904_URL}",
                f"- 26 U.S.C. § 1411: {USC_1411_URL}",
                f"- IRS yearly average currency exchange rates: {IRS_YEARLY_AVG_RATES}",
                f"- IRS Instructions for Form 1040: {IRS_I1040}",
                f"- IRS Instructions for Form 1116: {IRS_I1116}",
                f"- IRS Instructions for Form 8960: {IRS_I8960}",
                f"- IRS Publication 514: {IRS_P514}",
                f"- IRS Publication 550: {IRS_P550}",
                f"- U.S.-Germany treaty technical explanation: {IRS_GERMANY_TECH}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    _audit_note_md().write_text(
        "\n".join(
            [
                "# U.S. 2025 Legal Audit Note",
                "",
                "This file is generated to let a non-tax professional audit the U.S. model against the legal order and the concrete code entry points.",
                "",
                "## Statutory Order Used",
                "1. Capital buckets and the annual capital-loss limitation are computed under 26 U.S.C. §§ 1211, 1212, and 1256.",
                "2. Gross income / AGI are assembled under 26 U.S.C. § 61 with the actual Form 1040 line 7a capital result included.",
                f"3. Taxable income is computed under 26 U.S.C. § 63 using the 2025 {filing_status_label_lower} standard deduction.",
                f"4. Regular tax is computed under 26 U.S.C. § 1 using the 2025 {filing_status_label_lower} schedule and the qualified-dividend / capital-gain ordering from § 1(h).",
                "5. Foreign tax credit limitations are computed under 26 U.S.C. § 904 and the Form 1116 / Publication 514 allocation rules.",
                "6. Allowed passive and general FTCs are applied under 26 U.S.C. § 901 and § 904.",
                "7. Treaty re-sourcing worksheet values are computed under the Germany treaty technical explanation and Publication 514.",
                "8. NIIT is computed under 26 U.S.C. § 1411 and the Form 8960 instructions.",
                "9. Payments are applied on Form 1040 to determine refund or balance due.",
                "",
                "## Code Entry Points",
                "- Pure U.S. 2025 law helpers: `tax_pipeline/y2025/us_law.py`",
                "- Structured-input loader for those pure functions: `tax_pipeline/y2025/us_inputs.py`",
                "- Capital workpaper generator: `python3 -m tax_pipeline.pipelines.y2025.us_capital_workpaper`",
                "- Top-level U.S. 2025 model: `python3 -m tax_pipeline.pipelines.y2025.us_model`",
                "- Treaty packet renderer: `python3 -m tax_pipeline.pipelines.y2025.us_treaty_packet`",
                "",
                "## Manual Positions Still Explicitly Configured",
                "- Include staking income in NIIT",
                "- Use treaty re-sourcing in the chosen posture",
                "- Use documented positive-income components only in the FTC denominator",
                "- Allocate joint German wage-side tax by wage share",
                "- Set Germany's residence-country credit equal to treaty-allowed U.S. source tax in the Publication 514 worksheet",
                "- Use the documented U.S.-source dividend split and German residual-rate assumptions from `outputs/tax-positions/us-model-assumptions.csv`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
