from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.postures import get_posture_definition
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
)
from tax_pipeline.y2025.us_law import (
    IRS_GERMANY_TECH,
    IRS_I1040 as IRS_I1040,
    IRS_I1116,
    IRS_I8960,
    IRS_P514,
    IRS_YEARLY_AVG_RATES,
)
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28

YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STEPS = analysis_root(Path(__file__), default_year=2025)
TAX_RESULTS = STEPS / "us-tax-estimate.json"

PACKET_JSON = STEPS / "us-treaty-package.json"
WORKSHEET_CSV = STEPS / "us-treaty-resourcing-worksheet.csv"
ENTRY_MD = STEPS / "us-treaty-entry-sheet.md"
STATEMENTS_MD = STEPS / "us-supporting-statements.md"



def round_cents(amount_usd: Decimal) -> Decimal:
    return amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(amount_usd: Decimal) -> str:
    return format(round_cents(amount_usd), "f")


def _usa_posture_from_assessment_inputs(assessment_inputs) -> str:
    filing_status = assessment_inputs.profile.filing_status_label.strip().lower()
    if filing_status == "single":
        return "single"
    if filing_status == "married filing separately":
        return "mfs_nra_spouse" if assessment_inputs.profile.spouse_name_for_mfs_line else "married_separate"
    if filing_status == "married filing jointly":
        return "married_joint"
    raise NotImplementedError(
        f"Unsupported U.S. filing status label {assessment_inputs.profile.filing_status_label!r}."
    )


def _usa_posture_from_tax_results(filing_assumptions: dict) -> str:
    filing_status = str(filing_assumptions.get("filing_status", "")).strip().lower()
    if filing_status == "single":
        return "single"
    if filing_status == "married filing separately":
        return "mfs_nra_spouse" if filing_assumptions.get("nra_spouse_name") else "married_separate"
    if filing_status == "married filing jointly":
        return "married_joint"
    raise NotImplementedError(f"Unsupported U.S. filing status label {filing_assumptions.get('filing_status')!r}.")


def load_json_decimals(path: Path) -> dict:
    def convert(value):
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [convert(v) for v in value]
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception:
                return value
        return value

    return convert(json.loads(path.read_text(encoding="utf-8")))


def main() -> None:
    tax_results = load_json_decimals(TAX_RESULTS)
    filing_assumptions = tax_results["filing_assumptions"]
    get_posture_definition("usa", _usa_posture_from_tax_results(filing_assumptions))

    income = tax_results["income"]
    tax = tax_results["tax"]
    ftc = tax_results["ftc"]
    treaty = tax_results["treaty_resourcing"]
    manual = tax_results["manual_positions"]
    payments = tax_results["payments"]
    # 26 U.S.C. § 24 — Child Tax Credit + § 24(h)(4) ODC values surfaced by
    # ``us_model.py`` from the US25-CTC-AND-ODC rule graph stage. The CTC
    # block is always present in ``us-tax-estimate.json``; for an empty
    # ``config/children.csv`` every value is zero so the demo numerics are
    # unchanged. Authority: https://www.law.cornell.edu/uscode/text/26/24
    ctc = tax_results.get("ctc", {
        # Defensive default for a workspace with no children.csv — every
        # Schedule 8812 line surfaces as zero. The default block must
        # populate every key the renderer reads, including the new
        # line 9/10/13/16a/16b/18a/19/20/21 worksheet steps surfaced as
        # declared rule outputs.
        "qualifying_ctc_count": 0,
        "qualifying_odc_count": 0,
        "gross_ctc_usd": Decimal("0.00"),
        "gross_odc_usd": Decimal("0.00"),
        "combined_pre_phaseout_usd": Decimal("0.00"),
        "phaseout_threshold_usd": Decimal("0.00"),
        "modified_agi_usd": Decimal("0.00"),
        "regular_tax_after_ftc_usd": Decimal("0.00"),
        "phaseout_reduction_usd": Decimal("0.00"),
        "combined_post_phaseout_usd": Decimal("0.00"),
        "nonrefundable_portion_usd": Decimal("0.00"),
        "remaining_ctc_for_refundable_usd": Decimal("0.00"),
        "refundable_actc_cap_usd": Decimal("0.00"),
        "earned_income_usd": Decimal("0.00"),
        "earned_income_floor_usd": Decimal("0.00"),
        "earned_income_excess_usd": Decimal("0.00"),
        "refundable_actc_earned_income_phase_in_usd": Decimal("0.00"),
        "refundable_actc_usd": Decimal("0.00"),
        "total_credit_usd": Decimal("0.00"),
    })
    capital_income = income
    capital_tax = tax_results["capital"]
    capital_ftc = ftc
    has_digital_assets = capital_tax.get("digital_asset_transaction_present") == "yes" or any(
        capital_tax[key] != Decimal("0.00")
        for key in [
            "short_box_h_usd",
            "long_box_k_usd",
        ]
    ) or capital_income["staking_income_usd"] != Decimal("0.00")
    treaty_resourcing_claimed = manual["use_treaty_resourcing"] == "yes"
    filing_status = filing_assumptions["filing_status"]
    spouse_name = filing_assumptions["nra_spouse_name"]
    joint_return_spouse_name = filing_assumptions["joint_return_spouse_name"]
    elected_joint_with_nra_spouse = filing_assumptions["joint_return_with_nra_spouse_election"] == "yes"
    # 26 U.S.C. §§ 901 and 905 make the FTC timing/election posture part of the
    # Form 1116 support package. Report the profile-selected method instead of
    # hard-coding accrued.
    ftc_method_label = "Accrued" if filing_assumptions["accrued_basis_ftc"] == "yes" else "Paid"
    standard_deduction_label = filing_status.lower()

    line_16_tax = tax["regular_tax_before_credits_usd"]
    # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line 1 (Foreign Tax Credit)
    # is now a declared rule output produced by US25-19A
    # (``us.tax.schedule_3_line_1_ftc_total_usd``). Reading it directly
    # closes the long-standing I5 smell at this line where the
    # projection summed three rule outputs (allowed_general + allowed_
    # passive + treaty_resourcing_additional) into a "schedule3_line1"
    # local — Decimal arithmetic on legal output keys outside the rule
    # graph that the I5 detector did not catch because the receiver
    # ``ftc`` is a dict-typed local (not the tainted ``assessment`` /
    # ``treaty`` receiver names) and the LHS name does not start with
    # the ``tax_`` / ``legal_`` / ``refund_`` prefixes the LHS-by-name
    # heuristic flags. Authority: 26 U.S.C. §§ 901/904 + Pub. 514
    # worksheet line 21; Schedule 3:
    #   https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
    schedule3_line1 = tax["schedule_3_line_1_ftc_total_usd"]
    worksheet_line_21 = treaty.get(
        "worksheet_line_21_additional_credit_usd",
        treaty["treaty_resourcing_additional_ftc_usd"],
    )
    schedule3_line8 = schedule3_line1
    # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line-level decomposition.
    # All values are 1:1 reads of declared rule outputs surfaced by
    # ``us_model.py`` (US25-AMT-FTC-AND-COMPARE / US25-SE-TAX /
    # US25-ADDITIONAL-MEDICARE / US25-20-NIIT / US25-21-PAYMENTS). No
    # Decimal arithmetic on legal output keys outside the rule graph
    # (invariant I5). The Form 1040 line-17 / line-23 wires read from
    # these rule-graph values rather than re-summing them here.
    # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) AMT row is on line 2
    # (was line 1 on the 2024 revision) per
    # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf. The packet key
    # ``schedule_2_line_1_amt_usd`` retains the 2024 line-1 name for
    # fingerprint stability across the audit graph; the rendered IRS
    # line label comes from the schema TOML.
    # Authority: 26 U.S.C. § 55 / Form 6251; Schedule 2:
    #   https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
    schedule2_line1_amt = tax["schedule_2_line_1_amt_usd"]
    schedule2_line3_total_amt = tax["schedule_2_line_3_total_amt_usd"]
    schedule2_line4_se_tax = tax["schedule_2_line_4_se_tax_usd"]
    schedule2_line11_additional_medicare = tax["schedule_2_line_11_additional_medicare_usd"]
    schedule2_line12 = tax["schedule_2_line_12_niit_usd"]
    schedule2_line21 = tax["schedule_2_line_21_total_other_taxes_usd"]
    form1040_line17 = schedule2_line3_total_amt
    form1040_line23 = schedule2_line21
    form1040_line26 = payments["estimated_payment_usd"]
    refund_amount = payments.get(
        "refund_with_treaty_resourcing_usd",
        fmt(max(Decimal("0.00"), payments["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"])),
    )
    amount_owed = payments.get(
        "amount_owed_with_treaty_resourcing_usd",
        fmt(max(Decimal("0.00"), -payments["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"])),
    )
    baseline_refund = payments.get(
        "refund_without_treaty_resourcing_usd",
        fmt(max(Decimal("0.00"), payments["refund_if_positive_else_balance_due_usd"])),
    )
    baseline_amount_owed = payments.get(
        "amount_owed_without_treaty_resourcing_usd",
        fmt(max(Decimal("0.00"), -payments["refund_if_positive_else_balance_due_usd"])),
    )

    packet = {
        "chosen_position": {
            "filing_status": filing_status,
            "nra_spouse_name": spouse_name,
            "joint_return_spouse_name": joint_return_spouse_name,
            "joint_return_with_nra_spouse_election": "yes" if elected_joint_with_nra_spouse else "no",
            "digital_assets_checkbox": "Yes" if has_digital_assets else "No",
            "ftc_method": ftc_method_label,
            "treaty_resourcing_claimed": manual["use_treaty_resourcing"],
            # DBA-USA Art. 28 LOB qualification + 26 U.S.C. § 6114 /
            # Reg. § 301.6114-1: Form 8833 disclosure is required when
            # the taxpayer claims treaty re-sourcing AND qualifies under
            # one of the five LOB paragraphs. Sourced from the executed
            # ``TREATY25-LOB-QUALIFICATION`` rule output
            # ``treaty.form_8833_required`` (plumbed through
            # ``us_model.py`` into ``treaty_resourcing.form_8833_required``).
            # https://www.law.cornell.edu/uscode/text/26/6114
            # https://www.law.cornell.edu/cfr/text/26/301.6114-1
            "form_8833_required": treaty.get("form_8833_required", "no"),
            "lob_qualified": treaty.get("lob_qualified", "no"),
            "lob_category": treaty.get("lob_category", ""),
        },
        "headline": {
            "refund_usd": fmt(refund_amount),
            "total_tax_usd": fmt(tax["total_tax_with_treaty_resourcing_usd"]),
            "schedule3_total_foreign_tax_credit_usd": fmt(schedule3_line8),
            "schedule2_total_additional_tax_usd": fmt(schedule2_line21),
        },
        "form_1040": {
            "line_1h_other_earned_income_usd": fmt(income["wages_usd"]),
            "line_1z_total_wages_usd": fmt(income["wages_usd"]),
            "line_2b_taxable_interest_usd": fmt(capital_income["interest_income_usd"]),
            "line_3a_qualified_dividends_usd": fmt(capital_income["qualified_dividends_usd"]),
            "line_3b_ordinary_dividends_usd": fmt(capital_income["ordinary_dividends_usd"]),
            "line_7a_capital_gain_or_loss_usd": fmt(capital_tax["form_1040_line_7a_usd"]),
            "line_8_schedule_1_usd": fmt(income["schedule_1_other_income_usd"]),
            "line_11_agi_usd": fmt(income["adjusted_gross_income_usd"]),
            "line_12e_standard_deduction_usd": fmt(income["adjusted_gross_income_usd"] - income["taxable_income_usd"]),
            "line_15_taxable_income_usd": fmt(income["taxable_income_usd"]),
            "line_16_tax_usd": fmt(line_16_tax),
            "line_17_amt_usd": fmt(form1040_line17),
            # 26 U.S.C. § 24(b) — nonrefundable Child Tax Credit + § 24(h)(4)
            # ODC. Schedule 8812 line 14 carries to Form 1040 line 19 and
            # offsets line 16 (regular tax) BEFORE the additional taxes on
            # Schedule 2 (AMT, NIIT, SE, Additional Medicare).
            # https://www.law.cornell.edu/uscode/text/26/24
            "line_19_ctc_odc_usd": fmt(ctc["nonrefundable_portion_usd"]),
            "line_20_schedule_3_usd": fmt(schedule3_line8),
            # A2: Form 1040 line 22 = line 18 minus line 21 (tax after
            # nonrefundable credits, before Schedule 2 additional taxes).
            # Sourced from the executed ``us.tax.line_22_after_credits_*``
            # rule outputs surfaced by ``us_model.py`` under
            # ``tax.line_22_after_credits_*``. The treaty-resourced
            # version is used in the chosen filing posture (Schedule 3
            # line 1 includes the Pub. 514 additional credit). Authority:
            #   - Form 1040 instructions (2025): https://www.irs.gov/instructions/i1040gi
            "line_22_after_credits_usd": fmt(
                tax["line_22_after_credits_with_treaty_resourcing_usd"]
            ),
            "line_23_schedule_2_usd": fmt(form1040_line23),
            "line_26_estimated_payments_usd": fmt(form1040_line26),
            # 26 U.S.C. § 24(d) — refundable Additional Child Tax Credit.
            # Schedule 8812 line 27 carries to Form 1040 line 28 and is added
            # to payments. Capped at $1,700 per qualifying child for 2025
            # (Rev. Proc. 2024-40 § 3.05, OBBBA-preserved cap) and at the
            # § 24(d)(1)(B) earned-income phase-in (15% × (earned − $2,500)).
            # https://www.law.cornell.edu/uscode/text/26/24
            "line_28_refundable_actc_usd": fmt(ctc["refundable_actc_usd"]),
            "line_35a_refund_usd": fmt(refund_amount),
            "line_37_amount_owed_usd": fmt(amount_owed),
        },
        "schedule_3": {
            # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line-level
            # decomposition (lines 1, 6c, 8, 11). Each numeric field is a
            # 1:1 projection of a declared rule output (US25-19A for
            # line 1; US25-21-PAYMENTS for lines 6c and 11). No Decimal
            # arithmetic on legal output keys outside the rule graph
            # (invariant I5) — the prior projection-side
            # ``schedule3_line1 = ftc[allowed_general] + ftc[allowed_
            # passive] + treaty[treaty_resourcing_additional]`` smell is
            # closed by the new ``us.tax.schedule_3_line_1_ftc_total_usd``
            # rule output.
            # Authority:
            #   - 26 U.S.C. § 901 / § 904 (Foreign Tax Credit)
            #   - 26 U.S.C. § 904(d)(6) (treaty re-sourcing basket)
            #   - IRS Pub. 514 worksheet line 21 (treaty resourcing)
            #   - Schedule 3 (2024 revision):
            #     https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
            "line_1_foreign_tax_credit_usd": fmt(schedule3_line1),
            "line_8_total_nonrefundable_credits_usd": fmt(schedule3_line8),
        },
        "schedule_2": {
            # B1 (FORM-MAPPING-FOLLOWUP) — full Schedule 2 line-level
            # decomposition. Each field is a 1:1 projection of a declared
            # rule output produced by US25-AMT-FTC-AND-COMPARE /
            # US25-SE-TAX / US25-ADDITIONAL-MEDICARE / US25-20-NIIT /
            # US25-21-PAYMENTS so the Schedule 2 renderer transits
            # ``legal_value_entry`` with a real
            # ``StageResult.output_fingerprint`` (invariants I2 / I11). No
            # Decimal arithmetic on legal output keys outside the rule
            # graph (invariant I5).
            # Authority:
            #   - 26 U.S.C. § 55 (AMT) / Form 6251
            #   - 26 U.S.C. § 1401 / § 1402 (SE tax) / Schedule SE
            #   - 26 U.S.C. § 3101(b)(2) / § 1401(b)(2) (Additional
            #     Medicare) / Form 8959
            #   - 26 U.S.C. § 1411 (NIIT) / Form 8960
            #   - Schedule 2 (IRS-VERIFIED 2026-05-10 against the 2025
            #     revision — https://www.irs.gov/pub/irs-pdf/f1040s2.pdf):
            #     Part I lines 1a-1f / 1y / 1z = additions to tax;
            #     line 2 = AMT (Form 6251 line 11); line 3 = line 1z + line 2.
            #     The packet key ``line_1_amt_from_form_6251_usd`` retains
            #     2024 line-1 numbering for fingerprint stability.
            #     https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
            "line_1_amt_from_form_6251_usd": fmt(schedule2_line1_amt),
            "line_3_total_amt_usd": fmt(schedule2_line3_total_amt),
            "line_4_se_tax_from_schedule_se_usd": fmt(schedule2_line4_se_tax),
            "line_11_additional_medicare_from_form_8959_usd": fmt(
                schedule2_line11_additional_medicare
            ),
            "line_12_niit_from_form_8960_usd": fmt(schedule2_line12),
            "line_21_total_other_taxes_usd": fmt(schedule2_line21),
        },
        "schedule_8812": {
            # 26 U.S.C. § 24 — Child Tax Credit + Credit for Other Dependents
            # + Additional (refundable) Child Tax Credit. Schedule 8812 (2025)
            # walks lines 1-14 (CTC computation) and lines 15-27 (refundable
            # ACTC). Every value here is a pure 1:1 projection of declared
            # ``us.ctc.*`` rule outputs; no Decimal arithmetic on legal
            # output keys (invariant I5). Each form-line key is paired with
            # the executor's ``us.ctc.*`` key (used by the renderer's
            # ``legal_value_from_dict`` provenance lookup) so every Schedule
            # 8812 line traces to a real ``StageResult.output_fingerprint``
            # (invariant I2 / I11; no synthesized fingerprints).
            # https://www.law.cornell.edu/uscode/text/26/24
            # https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
            "qualifying_ctc_count": ctc["qualifying_ctc_count"],
            "qualifying_odc_count": ctc["qualifying_odc_count"],
            "gross_ctc_usd": fmt(ctc["gross_ctc_usd"]),
            "gross_odc_usd": fmt(ctc["gross_odc_usd"]),
            "combined_pre_phaseout_usd": fmt(ctc["combined_pre_phaseout_usd"]),
            "phaseout_reduction_usd": fmt(ctc["phaseout_reduction_usd"]),
            "combined_post_phaseout_usd": fmt(ctc["combined_post_phaseout_usd"]),
            # Line 9 — § 24(b)(2) phase-out threshold ($200k single /
            # $400k MFJ).
            "line_9_phaseout_threshold_usd": fmt(ctc["phaseout_threshold_usd"]),
            # Line 10 — § 24(b)(2) Modified AGI (AGI plus § 911 / § 933
            # add-backs, mirroring the § 1411(d)(1)(A) NIIT MAGI base).
            "line_10_modified_agi_usd": fmt(ctc["modified_agi_usd"]),
            # Line 13 — regular tax after FTC ordering cap from the
            # Credit Limit Worksheet A; § 24(b)(3) ordering.
            "line_13_credit_limit_from_worksheet_usd": fmt(ctc["regular_tax_after_ftc_usd"]),
            # Line 14 (nonrefundable CTC + ODC carried to Form 1040 line 19).
            "line_14_nonrefundable_ctc_odc_usd": fmt(ctc["nonrefundable_portion_usd"]),
            # Line 16a — remaining-CTC ceiling for the § 24(d) refundable
            # allocation; Line 16b — § 24(d)(1)(A) per-child cap ($1,700
            # for 2025; Rev. Proc. 2024-40 § 3.05).
            "line_16a_remaining_ctc_for_actc_usd": fmt(ctc["remaining_ctc_for_refundable_usd"]),
            "line_16b_per_child_refundable_cap_usd": fmt(ctc["refundable_actc_cap_usd"]),
            # Line 18a — earned-income input to § 24(d)(1)(B); Line 19 —
            # statutory $2,500 floor (sourced from
            # CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD per invariant I1);
            # Line 20 — max(0, earned_income − $2,500); Line 21 — 15 %
            # phase-in.
            "line_18a_earned_income_usd": fmt(ctc["earned_income_usd"]),
            "line_19_earned_income_floor_usd": fmt(ctc["earned_income_floor_usd"]),
            "line_20_earned_income_excess_usd": fmt(ctc["earned_income_excess_usd"]),
            "line_21_earned_income_phase_in_usd": fmt(
                ctc["refundable_actc_earned_income_phase_in_usd"]
            ),
            # Line 27 (refundable ACTC carried to Form 1040 line 28).
            "line_27_refundable_actc_usd": fmt(ctc["refundable_actc_usd"]),
            "total_credit_usd": fmt(ctc["total_credit_usd"]),
        },
        "form_6251": {
            "line_4_amti_usd": fmt(tax.get("amti_usd", Decimal("0.00"))),
            "line_5_exemption_usd": fmt(tax.get("amt_exemption_usd", Decimal("0.00"))),
            "line_6_amti_after_exemption_usd": fmt(tax.get("amti_after_exemption_usd", Decimal("0.00"))),
            "line_7_tentative_min_tax_usd": fmt(tax.get("amt_tentative_min_tax_usd", Decimal("0.00"))),
            "line_8_amtftc_usd": fmt(tax.get("amtftc_usd", Decimal("0.00"))),
            "line_11_amt_owed_usd": fmt(schedule2_line1_amt),
            "preferential_amti_usd": fmt(tax.get("amt_preferential_amti_usd", Decimal("0.00"))),
        },
        # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level decomposition
        # under 26 U.S.C. §§ 3101(b)(2) (Medicare-wage portion) and
        # 1401(b)(2) (SE-earnings portion). Each numeric field is a 1:1
        # projection of a declared rule output (US25-ADDITIONAL-MEDICARE)
        # so every form-line write transits ``legal_value_entry`` with a
        # real ``StageResult.output_fingerprint`` (invariants I2 / I11).
        # No Decimal arithmetic on legal output keys outside the rule
        # graph (invariant I5).
        # Authority:
        #   - Form 8959 instructions:
        #     https://www.irs.gov/forms-pubs/about-form-8959
        "form_8959": {
            "line_1_medicare_wages_usd": fmt(tax["form_8959_line_1_medicare_wages_usd"]),
            "line_4_total_medicare_wages_usd": fmt(
                tax["form_8959_line_4_total_medicare_wages_usd"]
            ),
            "line_5_threshold_usd": fmt(tax["form_8959_line_5_threshold_usd"]),
            "line_6_wages_excess_usd": fmt(tax["form_8959_line_6_wages_excess_usd"]),
            "line_7_addtl_medicare_on_wages_usd": fmt(
                tax["form_8959_line_7_addtl_medicare_on_wages_usd"]
            ),
            "line_8_se_taxable_usd": fmt(tax["form_8959_line_8_se_taxable_usd"]),
            "line_11_residual_threshold_usd": fmt(
                tax["form_8959_line_11_residual_threshold_usd"]
            ),
            "line_13_addtl_medicare_on_se_usd": fmt(
                tax["form_8959_line_13_addtl_medicare_on_se_usd"]
            ),
            "line_18_total_addtl_medicare_usd": fmt(
                tax["form_8959_line_18_total_addtl_medicare_usd"]
            ),
        },
        # Phase 2 (FREELANCER-US-SCHEDULE-C) — Schedule C line-level
        # decomposition under 26 U.S.C. § 61 / § 162. Each numeric field is a
        # 1:1 projection of a declared rule output (US25-02A-SCHEDULE-C). No
        # Decimal arithmetic on legal output keys outside the rule graph
        # (invariant I5). IRS-VERIFIED 2026-06-13: line 7 gross income, line 28
        # total expenses, line 31 net profit.
        # Authority: https://www.irs.gov/forms-pubs/about-schedule-c-form-1040
        "schedule_c": {
            "line_7_gross_income_usd": fmt(
                tax["schedule_c_line_7_gross_income_usd"]
            ),
            "line_28_total_expenses_usd": fmt(
                tax["schedule_c_line_28_total_expenses_usd"]
            ),
            "line_31_net_profit_usd": fmt(
                tax["schedule_c_line_31_net_profit_usd"]
            ),
        },
        # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level decomposition
        # under 26 U.S.C. §§ 1401, 1402(a)(12). Each numeric field is a
        # 1:1 projection of a declared rule output (US25-SE-TAX). No
        # Decimal arithmetic on legal output keys outside the rule graph
        # (invariant I5).
        # Authority: Schedule SE instructions:
        #   https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
        "schedule_se": {
            "line_2_net_se_earnings_usd": fmt(
                tax["schedule_se_line_2_net_se_earnings_usd"]
            ),
            "line_3_total_se_earnings_usd": fmt(
                tax["schedule_se_line_3_total_se_earnings_usd"]
            ),
            "line_4a_se_taxable_usd": fmt(tax["schedule_se_line_4a_se_taxable_usd"]),
            "line_4c_se_taxable_usd": fmt(tax["schedule_se_line_4c_se_taxable_usd"]),
            "line_6_combined_se_base_usd": fmt(
                tax["schedule_se_line_6_combined_se_base_usd"]
            ),
            "line_8a_w2_ss_wages_usd": fmt(tax["schedule_se_line_8a_w2_ss_wages_usd"]),
            "line_10_oasdi_tax_usd": fmt(tax["schedule_se_line_10_oasdi_tax_usd"]),
            "line_11_medicare_tax_usd": fmt(tax["schedule_se_line_11_medicare_tax_usd"]),
            "line_12_total_se_tax_usd": fmt(tax["schedule_se_line_12_total_se_tax_usd"]),
        },
        # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 Part I line-level
        # decomposition under 26 U.S.C. § 1411. Each numeric field is a
        # 1:1 projection of a declared rule output (US25-20-NIIT). No
        # Decimal arithmetic on legal output keys outside the rule
        # graph (invariant I5).
        # Authority: Form 8960 instructions:
        #   https://www.irs.gov/forms-pubs/about-form-8960
        "form_8960": {
            "line_1_interest_usd": fmt(tax["form_8960_line_1_interest_usd"]),
            "line_2_ordinary_dividends_usd": fmt(
                tax["form_8960_line_2_ordinary_dividends_usd"]
            ),
            "line_5a_capital_gain_loss_usd": fmt(
                tax["form_8960_line_5a_capital_gain_loss_usd"]
            ),
            "line_5b_non_section_1411_adj_usd": fmt(
                tax["form_8960_line_5b_non_section_1411_adj_usd"]
            ),
            "line_5c_cfc_pfic_adj_usd": fmt(
                tax["form_8960_line_5c_cfc_pfic_adj_usd"]
            ),
            "line_5d_combined_capital_usd": fmt(
                tax["form_8960_line_5d_combined_capital_usd"]
            ),
            # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — line 7
            # ("Other modifications to investment income") and line 11
            # ("Total deductions and modifications") so the rendered
            # Part I lines foot to line 8 and line 12 reconciles from
            # visible components. Line 7 carries substitute-payment +
            # optional staking income; line 11 = 0 in the supported
            # posture (no Part II investment-expense deductions).
            "line_7_other_modifications_usd": fmt(
                tax["form_8960_line_7_other_modifications_usd"]
            ),
            "line_8_total_investment_income_usd": fmt(
                tax["form_8960_line_8_total_investment_income_usd"]
            ),
            "line_11_total_deductions_usd": fmt(
                tax["form_8960_line_11_total_deductions_usd"]
            ),
            "line_12_net_investment_income_usd": fmt(
                tax["form_8960_line_12_net_investment_income_usd"]
            ),
            # Existing "line 17" wire — the NIIT scalar — kept for
            # backward compatibility with the renderer's existing read of
            # the rolled-up base; sourced from Schedule 2 line 12 (= NIIT
            # scalar) per B1's declared rule output.
            "line_17_niit_usd": fmt(tax["schedule_2_line_12_niit_usd"]),
        },
        "treaty_resourcing_worksheet": {
            "status": "computed" if treaty_resourcing_claimed else "not_applicable",
            "line_12_estimated_us_tax_usd": fmt(treaty["us_tax_on_us_source_dividends_usd"]),
            "line_16_treaty_allowed_us_tax_at_source_usd": fmt(
                treaty["treaty_minimum_us_tax_on_us_source_dividends_usd"]
            ),
            "line_17_residence_country_tax_before_credit_usd": fmt(
                treaty["german_precredit_tax_on_us_source_dividends_usd"]
            ),
            "line_18_residence_country_credit_for_us_tax_usd": fmt(
                treaty["german_residence_credit_for_us_tax_usd"]
            ),
            "line_19_maximum_credit_usd": fmt(treaty["worksheet_line_19_maximum_credit_usd"]),
            "line_20c_residual_residence_country_tax_usd": fmt(
                treaty["worksheet_line_20c_residual_residence_country_tax_usd"]
            ),
            "line_21_additional_credit_usd": fmt(worksheet_line_21),
        },
    }
    if not treaty_resourcing_claimed:
        packet["treaty_resourcing_worksheet"]["reason"] = "Treaty re-sourcing is disabled in the selected filing posture."
    PACKET_JSON.write_text(json.dumps(packet, indent=2) + "\n", encoding="utf-8")

    worksheet_rows = [
        ("I", "1", "Dividends, gross U.S.-source amount", treaty["us_source_dividends_usd"], IRS_P514, "Uses the documented U.S.-source dividend stack from the saved source split."),
        ("I", "8B", "Net U.S.-source income in the separate category", treaty["us_source_dividends_usd"], IRS_P514, "No direct expenses were allocated to this dividend-only worksheet build."),
        ("I", "9", "Tax from Form 1040 line 16 before credits", line_16_tax, IRS_P514, "Publication 514 line 9 uses Form 1040 line 16 in the saved posture; no Schedule 2 line 1z or Form 8978 adjustment is modeled."),
        ("I", "12", "Estimated U.S. tax on U.S.-source income", treaty["us_tax_on_us_source_dividends_usd"], IRS_P514, "Publication 514 average-tax-rate method: line 9 divided by taxable income (Form 1040 line 15), multiplied by line 8 column B."),
        ("II", "14a", "U.S.-source dividends subject to treaty rate", treaty["us_source_dividends_usd"], IRS_P514, ""),
        ("II", "14b", "Treaty rate", DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, IRS_GERMANY_TECH, "Germany treaty dividend ceiling used in the saved model."),
        ("II", "14c", "Allowable U.S. tax at source under treaty", treaty["treaty_minimum_us_tax_on_us_source_dividends_usd"], IRS_P514, ""),
        ("II", "16", "Total allowable U.S. tax at source", treaty["treaty_minimum_us_tax_on_us_source_dividends_usd"], IRS_P514, ""),
        ("III", "17", "Residence-country tax before foreign tax credit", treaty["german_precredit_tax_on_us_source_dividends_usd"], IRS_P514, "Uses Germany treaty-dividend stage outputs for the same U.S.-source dividend stack."),
        ("III", "18", "Residence-country credit allowed for U.S. tax paid", treaty["german_residence_credit_for_us_tax_usd"], IRS_P514, "Uses Germany's computed Article 23 dividend credit for the same U.S.-source dividend stack."),
        ("III", "19", "Maximum additional credit", treaty["worksheet_line_19_maximum_credit_usd"], IRS_P514, "Line 12 less the greater of line 16 or line 18."),
        ("III", "20a", "Residence-country tax before credit", treaty["german_precredit_tax_on_us_source_dividends_usd"], IRS_P514, ""),
        ("III", "20b", "Greater of line 16 or line 18", max(treaty["treaty_minimum_us_tax_on_us_source_dividends_usd"], treaty["german_residence_credit_for_us_tax_usd"]), IRS_P514, ""),
        ("III", "20c", "Residual residence-country tax after source-country credit", treaty["worksheet_line_20c_residual_residence_country_tax_usd"], IRS_P514, ""),
        ("III", "21", "Additional foreign tax credit", worksheet_line_21, IRS_P514, "Add to Form 1116 Part III line 12 and Part IV line 32 under Publication 514; Form 1116 line 33 still limits the allowed nonrefundable credit."),
    ]
    with WORKSHEET_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["section", "line", "description", "amount_usd", "authority_url", "precision_note"])
        for section, line, desc, amount, url, note in worksheet_rows:
            writer.writerow([section, line, desc, fmt(amount), url, note])

    entry_lines = [
        "# U.S. Audit Summary - 2025",
        "",
        f"Current modeled filing result under the chosen treaty re-sourcing posture: **{fmt(refund_amount)} USD refund**.",
        "",
        "This file is the U.S. audit surface for the saved 2025 model.",
        "Use `outputs/forms/usa/` for the filing package. Do not use this audit summary as the primary form-entry surface.",
        "",
        "## Form 1040",
        f"- Filing status: `{filing_status}`",
    ]
    if spouse_name:
        entry_lines.append(f"- Spouse entry below filing-status box: `{spouse_name}`")
    elif elected_joint_with_nra_spouse:
        entry_lines.append(
            f"- Joint-return spouse: `{joint_return_spouse_name}` (explicit NRA-spouse joint-return election)"
        )
    entry_lines.extend([
        f"- Digital asset checkbox: `{'Yes' if has_digital_assets else 'No'}`",
        f"- `Line 1h` other earned income: `{fmt(income['wages_usd'])} USD`",
        f"- `Line 1z` total wages: `{fmt(income['wages_usd'])} USD`",
        f"- `Line 2b` taxable interest: `{fmt(capital_income['interest_income_usd'])} USD`",
        f"- `Line 3a` qualified dividends: `{fmt(capital_income['qualified_dividends_usd'])} USD`",
        f"- `Line 3b` ordinary dividends: `{fmt(capital_income['ordinary_dividends_usd'])} USD`",
        f"- `Line 7a` capital gain or (loss): `{fmt(capital_tax['form_1040_line_7a_usd'])} USD`",
        f"- `Line 8` from Schedule 1: `{fmt(income['schedule_1_other_income_usd'])} USD`",
        f"- `Line 11` adjusted gross income: `{fmt(income['adjusted_gross_income_usd'])} USD`",
        f"- `Line 12e` standard deduction: `{fmt(income['adjusted_gross_income_usd'] - income['taxable_income_usd'])} USD`",
        f"- `Line 15` taxable income: `{fmt(income['taxable_income_usd'])} USD`",
        f"- `Line 16` tax: `{fmt(line_16_tax)} USD`",
        f"- `Line 20` from Schedule 3: `{fmt(schedule3_line8)} USD`",
        f"- `Line 23` from Schedule 2: `{fmt(form1040_line23)} USD`",
        f"- `Line 26` estimated tax payments: `{fmt(form1040_line26)} USD`",
        f"- `Line 35a` refund: `{fmt(refund_amount)} USD`",
        "",
        "## Schedule B",
        f"- `Line 2` taxable interest: `{fmt(capital_income['interest_income_usd'])} USD`",
        f"- `Line 5` ordinary dividends: `{fmt(capital_income['ordinary_dividends_usd'])} USD`",
        "",
        "## Schedule 1",
        f"- `Line 8z` total: `{fmt(income['schedule_1_other_income_usd'])} USD`",
        "  Split by attached statement:",
        f"  substitute payments `{fmt(capital_income['substitute_payments_usd'])} USD`; staking income `{fmt(capital_income['staking_income_usd'])} USD`",
        "",
        "## Schedule D / Form 8949 / Form 6781",
        f"- `Form 8949 Part I Box A`: `{fmt(capital_tax['short_box_a_usd'])} USD`",
        f"- `Form 8949 Part I Box B`: `{fmt(capital_tax['short_box_b_usd'])} USD`",
        f"- `Form 8949 Part I Box H`: `{fmt(capital_tax['short_box_h_usd'])} USD`",
        f"- `Form 8949 Part II Box D`: `{fmt(capital_tax['long_box_d_usd'])} USD`",
        f"- `Form 8949 Part II Box K`: `{fmt(capital_tax['long_box_k_usd'])} USD`",
        f"- `Form 6781` net section 1256: `{fmt(capital_tax['section_1256_total_usd'])} USD`",
        f"- `Schedule D` capital loss deduction used on Form 1040 line 7a: `{fmt(capital_tax['form_1040_line_7a_usd'])} USD`",
        f"- Tentative 2026 capital loss carryforward: `{fmt(capital_tax['tentative_capital_loss_carryforward_2026_usd'])} USD`",
        "",
        "## Form 8960 / Schedule 2",
        f"- `Form 8960` NIIT: `{fmt(schedule2_line12)} USD`",
        f"- `Schedule 2 line 12`: `{fmt(schedule2_line12)} USD`",
        f"- `Schedule 2 line 21`: `{fmt(schedule2_line21)} USD`",
        "",
        "## Form 1116 / Schedule 3",
        f"- General-category allowed FTC: `{fmt(ftc['allowed_general_ftc_usd'])} USD`",
        f"- Passive-category allowed FTC: `{fmt(ftc['allowed_passive_ftc_usd'])} USD`",
        f"- Additional treaty re-sourcing credit: `{fmt(treaty['treaty_resourcing_additional_ftc_usd'])} USD`",
        f"- `Schedule 3 line 1` foreign tax credit: `{fmt(schedule3_line1)} USD`",
        f"- `Schedule 3 line 8` total nonrefundable credits: `{fmt(schedule3_line8)} USD`",
        "- `Form 8833`: not required for this additional foreign tax credit posture under Publication 514.",
        "- No separate treaty-only Form 1116 basket is used in this packet; it follows the limited re-sourcing worksheet route for U.S. citizens resident in Germany.",
        "",
        "## Required Attachments",
        "- `Schedule B`",
        "- `Schedule 1`",
        "- `Schedule D`",
        "- `Form 8949`",
        "- `Form 6781`",
        "- `Form 8960`",
        "- `Form 1116` passive category",
        "- `Form 1116` general category",
        "- `Schedule B (Form 1116)` carryover support",
        "- `Schedule C (Form 1116)` for the 2024 German redetermination if the preparer carries it through that way",
        (
            "- Publication 514 `Additional Foreign Tax Credit on U.S. Income` worksheet as an attachment to Form 1116"
            if treaty_resourcing_claimed
            else "- Treaty re-sourcing is not claimed; no Publication 514 additional-credit worksheet is attached."
        ),
        "",
        "## Pre-Submit Checklist",
    ])
    if spouse_name:
        entry_lines.append(
            f"- Filing posture: confirm the return is `{filing_status}` with spouse entry `{spouse_name}` below the filing-status box."
        )
    elif elected_joint_with_nra_spouse:
        entry_lines.append(
            f"- Filing posture: confirm the return is `{filing_status}` with spouse `{joint_return_spouse_name}` included under the explicit NRA-spouse joint-return election."
        )
    else:
        entry_lines.append(f"- Filing posture: confirm the return is `{filing_status}` with no spouse entry populated.")
    entry_lines.extend([
        f"- Wage and base return amounts: confirm Form 1040 lines `1z`, `11`, `12e`, `15`, `16`, `23`, and `26` match this sheet. The base-return anchor without treaty re-sourcing is `{fmt(baseline_refund)} USD refund` / `{fmt(baseline_amount_owed)} USD amount owed`.",
        f"- Vanilla checkpoint: if you strip the return down to wages only, standard deduction, no capital, no treaty, and no FTC, the checkpoint is `{fmt(-tax_results['vanilla_checkpoint']['refund_or_balance_due_usd'])} USD balance due`. Use that as the low-blast-radius commercial-software comparison point.",
        "- Schedule B / Schedule 1 / Schedule D: confirm taxable interest, dividends, substitute payments, staking income, capital-loss deduction, Form 8949 buckets, and Form 6781 total match this sheet before you trust the 1040 result.",
        f"- Estimated payment: confirm the `{fmt(form1040_line26)} USD` estimated payment is actually present on Form 1040 line `26`. If it is missing, the refund will be understated by exactly that amount.",
        "- Form 1116 base credits: confirm the passive-category and general-category FTC amounts match this sheet before layering on treaty re-sourcing.",
        "- Treaty re-sourcing: only use the treaty-version anchor if the Publication 514 additional-credit worksheet is attached and the treaty worksheet lines match this sheet.",
        f"- Final anchors: the non-treaty base-return target is `{fmt(baseline_refund)} USD refund` / `{fmt(baseline_amount_owed)} USD amount owed`; the treaty-version target is `{fmt(refund_amount)} USD refund` / `{fmt(amount_owed)} USD amount owed`. A materially different preview means a required bucket is still missing or mis-entered.",
        "",
        "## Authorities",
        f"- Form 1040 instructions (2025): {IRS_I1040}",
        f"- Form 1116 instructions (2025): {IRS_I1116}",
        f"- Publication 514 (2025): {IRS_P514}",
        f"- Form 8960 instructions (2025): {IRS_I8960}",
        f"- Germany treaty technical explanation: {IRS_GERMANY_TECH}",
        f"- IRS yearly average FX rates: {IRS_YEARLY_AVG_RATES}",
        "",
    ])
    ENTRY_MD.write_text("\n".join(entry_lines), encoding="utf-8")

    statements_lines = [
        "# U.S. 2025 Supporting Statements",
        "",
        "## Statement 1 - Schedule 1 line 8z",
        "",
        "Other income reported on `Schedule 1, line 8z`:",
        f"- Substitute payments in lieu of dividends / interest: `{fmt(capital_income['substitute_payments_usd'])} USD`",
        f"- Digital-asset staking income: `{fmt(capital_income['staking_income_usd'])} USD`",
        f"- Total: `{fmt(income['schedule_1_other_income_usd'])} USD`",
        "",
        "## Statement 2 - Form 1116 treaty re-sourcing attachment",
        "",
        (
            "Attach the Publication 514 `Additional Foreign Tax Credit on U.S. Income` worksheet."
            if treaty_resourcing_claimed
            else "Treaty re-sourcing is not claimed for this packet, so no Publication 514 additional-credit worksheet is attached."
        ),
        f"- Worksheet line 12 estimated U.S. tax on U.S.-source dividend income: `{fmt(treaty['us_tax_on_us_source_dividends_usd'])} USD`",
        f"- Worksheet line 16 treaty-allowed U.S. source-country tax: `{fmt(treaty['treaty_minimum_us_tax_on_us_source_dividends_usd'])} USD`",
        f"- Worksheet line 17 Germany tax on the same U.S.-source dividend stack before foreign tax credit: `{fmt(treaty['german_precredit_tax_on_us_source_dividends_usd'])} USD`",
        f"- Worksheet line 18 Germany credit for U.S. tax paid: `{fmt(treaty['german_residence_credit_for_us_tax_usd'])} USD`",
        f"- Worksheet line 21 additional foreign tax credit claimed: `{fmt(worksheet_line_21)} USD`",
        "- No separate treaty-only Form 1116 category is used in this packet; the current filing posture follows the limited re-sourcing worksheet route.",
        "- `Form 8833` is not included because Publication 514 says it is not required for this additional credit claim.",
        "",
        (
            "Publication 514 says to file this worksheet with Form 1040 or 1040-SR as an attachment to Form 1116 and to add the line-21 amount to Form 1116 Part III line 12 and Part IV line 32."
            if treaty_resourcing_claimed
            else "Because treaty re-sourcing is not claimed, the Publication 514 line-21 add-on is not attached or added to Form 1116."
        ),
        "",
        "## Statement 3 - 2024 German redetermination",
        "",
        f"- Extra 2024 German assessment paid in 2025: `{fmt(capital_ftc['german_2024_redetermination_paid_2025_eur'])} EUR`",
        f"- Current working posture: {ftc_method_label.lower()}-basis foreign tax method tracked through `Schedule C (Form 1116)` / carryover support as applicable.",
        "- Current model assumption: no 2024 amendment is needed if the redetermination only increases FTC carryovers and does not change U.S. tax due for an already-filed year.",
        "",
        "## Residual assumptions to keep visible",
        "",
        *(
            [
                f"- Current filing posture uses an explicit NRA-spouse joint-return election for `{joint_return_spouse_name}`."
            ]
            if elected_joint_with_nra_spouse
            else []
        ),
        f"- Foreign wages are still presented on `Form 1040 line 1h / 1z` for the current `{filing_status}` posture; if software or the preparer uses a different statement-backed presentation, the total income should remain the same.",
        "- The treaty worksheet line 17/18 uses the Germany treaty-dividend stage and fails closed if the matched dividend gross/tax/credit projection is missing.",
        "",
    ]
    STATEMENTS_MD.write_text("\n".join(statements_lines), encoding="utf-8")


if __name__ == "__main__":
    main()
