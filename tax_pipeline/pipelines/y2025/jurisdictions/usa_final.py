"""USA final-legal-output validators and projection helpers.

Architecture review 2026-05-04 §5 Proposal 7 — extracts the U.S.
validation block from ``final_legal_output.py``. The collectors here
gate the projection-side artifacts (``us-capital-results.json``,
``us-form-8949-income-buckets.csv``, ``us-treaty-package.json``,
Form 1040 projection) against the typed legal core output that
``us_model.py`` persists into ``us-tax-estimate.json``.

Authority
---------
- 26 U.S.C. §§ 1211, 1212, 1256 — capital-loss / Section 1256 ordering
  guarded by ``_validate_us_capital_results_projection`` and
  ``_validate_us_bucket_rows_projection``. The U.S. capital sidecar
  (``us-capital-results.json``) and the Form 8949 bucket projection
  must be exact projections of those statutory results.
  https://www.law.cornell.edu/uscode/text/26/1211
  https://www.law.cornell.edu/uscode/text/26/1212
  https://www.law.cornell.edu/uscode/text/26/1256
- 26 U.S.C. § 55 (AMT, Form 6251 / Form 1040 line 17) and Form 1040
  instructions Schedule 2 line 21 (Other Taxes total → Form 1040
  line 23) — gated by ``_validate_us_final_output_consistency``.
  https://www.law.cornell.edu/uscode/text/26/55
  https://www.irs.gov/instructions/i1040gi
- DBA-USA Art. 23 (treaty resourcing) and Pub. 514 line 21 — gated
  by ``_validate_us_treaty_package_projection`` so a stale treaty
  packet cannot diverge from the resourcing FTC computed in the rule
  graph.
  https://www.irs.gov/forms-pubs/about-publication-514
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from tax_pipeline.pipelines.y2025.final_legal_output_helpers import (
    _format_decimal,
    _require_equal_string,
    _require_us_sidecar_equal,
)


def _validate_us_capital_results_projection(
    us_tax_estimate: dict[str, Any],
    capital_results: dict[str, Any],
) -> None:
    # U.S. form rendering may expose CSV/JSON sidecars, but those sidecars are
    # only valid as projections of the pure 2025 legal core. This gate prevents a
    # stale us-capital-results.json from disagreeing with the 26 U.S.C. §§ 1211,
    # 1212, and 1256 capital result already frozen in us-tax-estimate.json.
    for section, keys in (
        ("capital", tuple(capital_results.get("capital", {}).keys())),
        (
            "income",
            (
                "ordinary_dividends_usd",
                "qualified_dividends_usd",
                "interest_income_usd",
                "capital_gain_distributions_usd",
                "substitute_payments_usd",
                "staking_income_usd",
                "nondividend_distributions_usd",
                "foreign_tax_paid_usd",
            ),
        ),
    ):
        expected_section = us_tax_estimate.get(section, {})
        actual_section = capital_results.get(section, {})
        for key in keys:
            if key not in actual_section or key not in expected_section:
                continue
            _require_us_sidecar_equal(
                actual_section[key],
                expected_section[key],
                artifact="us-capital-results.json",
                label=f"{section}.{key}",
            )
    income = capital_results.get("income", {})
    _require_us_sidecar_equal(
        income.get("schedule_1_other_income_total_usd"),
        us_tax_estimate.get("income", {}).get("schedule_1_other_income_usd"),
        artifact="us-capital-results.json",
        label="income.schedule_1_other_income_total_usd",
    )
    ftc_start = capital_results.get("ftc_starting_point", {})
    ftc = us_tax_estimate.get("ftc", {})
    for key in (
        "passive_ftc_carryover_2024_usd",
        "general_ftc_carryover_2024_usd",
        "german_2024_redetermination_paid_2025_eur",
    ):
        _require_us_sidecar_equal(
            ftc_start.get(key),
            ftc.get(key),
            artifact="us-capital-results.json",
            label=f"ftc_starting_point.{key}",
        )


def _required_bucket_projection_row(
    bucket_rows: list[dict[str, str]],
    *,
    form: str,
    line_or_bucket: str,
) -> dict[str, str]:
    matches = [row for row in bucket_rows if row.get("form") == form and row.get("line_or_bucket") == line_or_bucket]
    if not matches:
        raise FileNotFoundError(f"Missing required row {form} / {line_or_bucket} in us-form-8949-income-buckets.csv")
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one row for {form} / {line_or_bucket} in us-form-8949-income-buckets.csv")
    return matches[0]


def _validate_us_bucket_rows_projection(
    us_tax_estimate: dict[str, Any],
    bucket_rows: list[dict[str, str]],
) -> None:
    capital = us_tax_estimate.get("capital", {})
    income = us_tax_estimate.get("income", {})
    checks = (
        ("Schedule B", "Line 5", income.get("ordinary_dividends_usd")),
        ("Form 1040", "Line 3a", income.get("qualified_dividends_usd")),
        ("Form 1040", "Line 3b", income.get("ordinary_dividends_usd")),
        ("Schedule B", "Line 2", income.get("interest_income_usd")),
        ("Schedule D", "Line 13", capital.get("capital_gain_distributions_usd")),
        ("Form 8949", "Part I Box A", capital.get("short_box_a_usd")),
        ("Form 8949", "Part I Box B", capital.get("short_box_b_usd")),
        ("Form 8949", "Part I Box H", capital.get("short_box_h_usd")),
        ("Form 8949 / Schedule D", "Part II Box D", capital.get("long_box_d_usd")),
        ("Form 8949", "Part II Box K", capital.get("long_box_k_usd")),
        ("Form 6781", "Net section 1256", capital.get("section_1256_total_usd")),
        ("Schedule D", "Net capital before 1256", capital.get("net_capital_before_1256_usd")),
        ("Schedule D", "Net capital after 1256", capital.get("net_capital_after_1256_usd")),
        ("Schedule D", "Capital loss deduction 2025", capital.get("capital_loss_deduction_2025_usd")),
        ("Carryforward", "Capital loss carryforward to 2026", capital.get("tentative_capital_loss_carryforward_2026_usd")),
    )
    if not bucket_rows:
        nonzero_required_rows = [
            (form, line_or_bucket)
            for form, line_or_bucket, expected in checks
            if Decimal(str(expected or "0.00")) != Decimal("0.00")
        ]
        if nonzero_required_rows:
            form, line_or_bucket = nonzero_required_rows[0]
            raise FileNotFoundError(
                f"Missing required row {form} / {line_or_bucket} in us-form-8949-income-buckets.csv"
            )
        return
    for form, line_or_bucket, expected in checks:
        row = _required_bucket_projection_row(bucket_rows, form=form, line_or_bucket=line_or_bucket)
        _require_us_sidecar_equal(
            row.get("amount_usd"),
            expected,
            artifact="us-form-8949-income-buckets.csv",
            label=f"{form} {line_or_bucket}",
        )


def _validate_us_treaty_package_projection(us_tax_estimate: dict[str, Any], treaty_package: dict[str, Any]) -> None:
    treaty = us_tax_estimate.get("treaty_resourcing", {})
    manual = us_tax_estimate.get("manual_positions", {})
    worksheet = treaty_package.get("treaty_resourcing_worksheet", {})
    claimed = str(manual.get("use_treaty_resourcing", "")).strip().lower() == "yes"
    expected_status = "computed" if claimed else "not_applicable"
    _require_us_sidecar_equal(
        worksheet.get("status"),
        expected_status,
        artifact="us-treaty-package.json",
        label="treaty_resourcing_worksheet.status",
    )
    expected_line_21 = (
        "0.00"
        if not claimed
        else treaty.get(
            "worksheet_line_21_additional_credit_usd",
            treaty.get("treaty_resourcing_additional_ftc_usd"),
        )
    )
    _require_us_sidecar_equal(
        worksheet.get("line_21_additional_credit_usd"),
        expected_line_21,
        artifact="us-treaty-package.json",
        label="treaty_resourcing_worksheet.line_21_additional_credit_usd",
    )


def _validate_us_final_output_consistency(us_tax_estimate: dict[str, Any], treaty_package: dict[str, Any]) -> None:
    income = us_tax_estimate.get("income", {})
    capital = us_tax_estimate.get("capital", {})
    tax = us_tax_estimate.get("tax", {})
    ftc = us_tax_estimate.get("ftc", {})
    payments = us_tax_estimate.get("payments", {})
    form_1040 = treaty_package.get("form_1040", {})
    # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) Part I composition per
    # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
    # F-US-1: line_17 = Form 1040 line 17 = Schedule 2 line 3 (AMT under
    # 26 U.S.C. § 55, Form 6251 line 11). Pre-B1 the validator computed
    # this as ``amt_owed_usd``; B1 (FORM-MAPPING-FOLLOWUP) declares the
    # IRS-VERIFIED 2026-05-11 value via the rule output
    # ``us.tax.schedule_2_line_3_total_amt_usd`` (Schedule 2 Part I total
    # = line 1z additions to tax + line 2 AMT; the 2025 IRS revision
    # moved AMT from line 1 to line 2 and expanded the additions-to-tax
    # row to 1a..1y with subtotal 1z). For the supported posture (no
    # line-1z additions to tax) line 3 = line 2 = AMT, so the consistency
    # check still holds against ``amt_owed_usd``.
    #
    # B1 — line_23 = Schedule 2 line 21 (Part II Other Taxes total =
    # SE tax + Additional Medicare + NIIT in the supported posture).
    # The pre-B1 validator incorrectly summed AMT + NIIT into line 23,
    # which conflated Schedule 2 Part I (AMT, Form 1040 line 17) with
    # Part II (Other Taxes, Form 1040 line 23). The correct semantic per
    # Form 1040 instructions is line 23 = Schedule 2 line 21 = sum of
    # lines 4-18 (i.e., Part II only). The new declared rule output
    # ``us.tax.schedule_2_line_21_total_other_taxes_usd`` is surfaced on
    # ``us-tax-estimate.json:tax`` and projected to
    # ``form_1040.line_23_schedule_2_usd`` directly.
    # Authority: Form 1040 instructions (2025): https://www.irs.gov/instructions/i1040gi
    expected_line_23 = tax.get("schedule_2_line_21_total_other_taxes_usd")
    projection_checks = {
        "line_1h_other_earned_income_usd": income.get("wages_usd"),
        "line_1z_total_wages_usd": income.get("wages_usd"),
        "line_2b_taxable_interest_usd": income.get("interest_income_usd"),
        "line_3a_qualified_dividends_usd": income.get("qualified_dividends_usd"),
        "line_3b_ordinary_dividends_usd": income.get("ordinary_dividends_usd"),
        "line_7a_capital_gain_or_loss_usd": capital.get("form_1040_line_7a_usd"),
        "line_8_schedule_1_usd": income.get("schedule_1_other_income_usd"),
        "line_11_agi_usd": income.get("adjusted_gross_income_usd"),
        # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03): the validator
        # reconstructs the standard-deduction value (Form 1040 line 12)
        # by subtracting the projected taxable income from the projected
        # AGI to confirm the projection is internally consistent. This
        # is a consistency-check arithmetic only — the value is not
        # written to a form line; it is compared against
        # ``form_1040["line_12e_standard_deduction_usd"]`` which is the
        # projection-side value built by ``us_treaty_packet.py``. Both
        # sides ultimately trace to the same rule outputs (us.stage.agi
        # and us.stage.taxable_income) so equality is structural.
        # # pragma: legal-math-ok validator consistency-check; both
        # sides trace to us.stage.agi / us.stage.taxable_income.
        "line_12e_standard_deduction_usd": _format_decimal(
            Decimal(str(income.get("adjusted_gross_income_usd", "0.00")))  # pragma: legal-math-ok validator consistency check; both AGI and taxable_income are declared rule outputs
            - Decimal(str(income.get("taxable_income_usd", "0.00")))
        ),
        "line_15_taxable_income_usd": income.get("taxable_income_usd"),
        "line_16_tax_usd": tax.get("regular_tax_before_credits_usd"),
        "line_17_amt_usd": tax.get("amt_owed_usd"),
        "line_20_schedule_3_usd": ftc.get("total_allowed_ftc_after_treaty_resourcing_usd"),
        "line_23_schedule_2_usd": expected_line_23,
        "line_26_estimated_payments_usd": payments.get("estimated_payment_usd"),
    }
    for label, expected in projection_checks.items():
        _require_equal_string(form_1040.get(label), expected, label=label)

    _validate_us_treaty_package_projection(us_tax_estimate, treaty_package)

    signed_result = Decimal(str(payments["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"]))
    expected_refund = _format_decimal(max(Decimal("0.00"), signed_result))
    expected_amount_owed = _format_decimal(max(Decimal("0.00"), -signed_result))
    if "refund_with_treaty_resourcing_usd" in payments:
        _require_equal_string(
            payments.get("refund_with_treaty_resourcing_usd"),
            expected_refund,
            label="refund_with_treaty_resourcing_usd",
        )
    if "amount_owed_with_treaty_resourcing_usd" in payments:
        _require_equal_string(
            payments.get("amount_owed_with_treaty_resourcing_usd"),
            expected_amount_owed,
            label="amount_owed_with_treaty_resourcing_usd",
        )
    _require_equal_string(form_1040.get("line_35a_refund_usd"), expected_refund, label="line_35a_refund_usd")
    if "line_37_amount_owed_usd" in form_1040:
        _require_equal_string(form_1040.get("line_37_amount_owed_usd"), expected_amount_owed, label="line_37_amount_owed_usd")


def _us_schedule_d_entries(us_capital_results: dict[str, Any]) -> list[dict[str, str]]:
    capital = us_capital_results["capital"]

    def usd(value: object) -> str:
        return f"{_format_decimal(value)} USD"

    short_attached = Decimal(str(capital["short_box_b_usd"])) + Decimal(str(capital["short_box_h_usd"]))
    return [
        {
            "line": "Short covered / no-adjustment total",
            "value": usd(capital["short_box_a_usd"]),
            "source": "us-capital-results.json",
            "notes": "Direct broker short covered total.",
        },
        {
            "line": "Short attached 8949 total",
            "value": usd(short_attached),
            "source": "us-capital-results.json",
            "notes": "Short noncovered broker rows plus short digital-asset rows.",
        },
        {
            "line": "Short 1256 portion",
            "value": usd(capital["section_1256_short_term_usd"]),
            "source": "us-capital-results.json",
            "notes": "Forty percent of the net section 1256 result.",
        },
        {
            "line": "Short total before Form 6781",
            "value": usd(capital["short_term_total_usd"]),
            "source": "us-capital-results.json",
            "notes": "",
        },
        {
            "line": "Long covered / no-adjustment total",
            "value": usd(capital["long_box_d_usd"]),
            "source": "us-capital-results.json",
            "notes": "Direct broker long covered total.",
        },
        {
            "line": "Long attached 8949 total",
            "value": usd(capital["long_box_k_usd"]),
            "source": "us-capital-results.json",
            "notes": "Long digital-asset attached-detail rows.",
        },
        {
            "line": "Line 13",
            "value": usd(capital["capital_gain_distributions_usd"]),
            "source": "us-capital-results.json",
            "notes": "Capital gain distributions.",
        },
        {
            "line": "Long 1256 portion",
            "value": usd(capital["section_1256_long_term_usd"]),
            "source": "us-capital-results.json",
            "notes": "Sixty percent of the net section 1256 result.",
        },
        {
            "line": "Long total before Form 6781",
            "value": usd(capital["long_term_total_with_cgd_usd"]),
            "source": "us-capital-results.json",
            "notes": "",
        },
        {
            "line": "Net capital result",
            "value": usd(capital["net_capital_after_1256_usd"]),
            "source": "us-capital-results.json",
            "notes": "Net capital result before the annual deduction cap.",
        },
        {
            "line": "Capital loss deduction carried to Form 1040 line 7a",
            "value": usd(f"-{capital['capital_loss_deduction_2025_usd']}"),
            "source": "us-capital-results.json",
            "notes": "Current filing posture annual capital-loss limit.",
        },
        {
            "line": "Capital loss carryforward to 2026",
            "value": usd(capital["tentative_capital_loss_carryforward_2026_usd"]),
            "source": "us-capital-results.json",
            "notes": "",
        },
    ]
