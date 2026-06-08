from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from tax_pipeline.paths import YearPaths
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


@dataclass(frozen=True)
class ValidationIssue:
    relative_path: str
    severity: str
    rule: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "relative_path": self.relative_path,
            "severity": self.severity,
            "rule": self.rule,
            "message": self.message,
        }


REQUIRED_FIELDS: dict[str, set[str]] = {
    "schwab_1099_pdf": {
        "ordinary_dividends_box_1a_usd",
        "qualified_dividends_box_1b_usd",
        "capital_gain_distributions_box_2a_usd",
        "nondividend_distributions_box_3_usd",
        "foreign_tax_paid_box_7_usd",
        "interest_income_box_1_usd",
        "substitute_payments_box_8_usd",
    },
    "schwab_1099_csv": {
        "ordinary_dividends_box_1a_usd",
        "qualified_dividends_box_1b_usd",
        "capital_gain_distributions_box_2a_usd",
        "nondividend_distributions_box_3_usd",
        "foreign_tax_paid_box_7_usd",
        "interest_income_box_1_usd",
        "substitute_payments_box_8_usd",
        "form_1099_b_row_count",
    },
    "schwab_transactions_csv": {
        "transaction_row_count",
        "first_transaction_date",
        "last_transaction_date",
        "distinct_action_count",
    },
    "coinbase_transactions_csv": {
        "transaction_row_count",
        "first_transaction_timestamp",
        "last_transaction_timestamp",
        "distinct_transaction_type_count",
    },
    "coinbase_1099_da_pdf": {
        "short_term_proceeds_usd",
        "short_term_cost_basis_usd",
        "short_term_gain_or_loss_usd",
        "long_term_proceeds_usd",
        "long_term_cost_basis_usd",
        "long_term_gain_or_loss_usd",
        "total_proceeds_usd",
        "total_cost_basis_usd",
        "total_gain_or_loss_usd",
    },
    "schwab_limitation_image": {
        "historical_data_window_years",
        "earliest_available_start_date",
    },
    "jpm_1099_pdf": {
        "account_number",
        "statement_date",
        "short_term_type_a_proceeds_usd",
        "short_term_type_a_cost_basis_usd",
        "short_term_type_a_market_discount_usd",
        "short_term_type_a_wash_sale_loss_disallowed_usd",
        "short_term_type_a_net_gain_usd",
    },
    "german_lohnsteuer_pdf": {
        "period_certification",
        "gross_wage_eur",
        "withheld_wage_tax_eur",
        "withheld_solidarity_surcharge_eur",
        "multiannual_wage_eur",
        "employer_pension_contribution_eur",
        "employee_pension_contribution_eur",
        "employee_health_insurance_eur",
        "employee_nursing_care_insurance_eur",
        "employee_unemployment_insurance_eur",
    },
    "german_verlustvortrag_pdf": {
        "loss_carryforward_as_of",
        "loss_carryforward_stock_sales_eur",
        "loss_carryforward_private_sales_eur",
    },
    "german_steuerbescheid_pdf": {
        "assessment_date",
        "assessed_income_tax_eur",
        "assessed_solidarity_surcharge_eur",
        "withheld_income_tax_credit_eur",
        "withheld_solidarity_credit_eur",
        "residual_income_tax_eur",
        "residual_solidarity_surcharge_eur",
        "payment_due_date",
        "amount_due_total_eur",
    },
    "german_prepayment_pdf": {"payment_amount_eur", "value_date", "booking_date", "reference_text"},
    "german_capital_certificate_pdf": {
        "capital_income_line_7_eur",
        "stock_sale_gain_line_8_eur",
        "saver_allowance_used_line_17_eur",
        "capital_gains_tax_line_37_eur",
        "solidarity_surcharge_line_38_eur",
        "foreign_tax_credit_line_40_eur",
    },
    "n26_transfer_confirmation_pdf": {
        "transfer_type",
        "amount_eur",
        "value_date",
        "booking_date",
        "transaction_id",
        "fee_eur",
        "reference_text",
        "sender_name",
        "recipient_name",
        "issued_on",
    },
    "german_social_insurance_notice_pdf": {
        "notice_date",
        "created_or_transmitted_at",
        "personnel_number",
        "insurance_number",
        "employee_name",
        "employer_name",
        "submission_reason_code",
        "submission_reason_text",
        "health_insurer_name",
        "employer_number",
        "nationality",
    },
    "us_1040_packet_pdf": {
        "prepared_for",
        "cover_income_tax_payable_usd",
        "cover_filing_deadline",
        "mfs_spouse_name",
        "form_1040_line_1h_other_earned_income_usd",
        "form_1040_line_1z_total_income_usd",
        "form_1040_line_2b_taxable_interest_usd",
        "form_1040_line_3a_qualified_dividends_usd",
        "form_1040_line_3b_ordinary_dividends_usd",
    },
    "us_8879_pdf": {
        "prepared_for",
        "signed_by",
        "cover_income_tax_payable_usd",
        "late_payment_penalty_interest_usd",
        "cover_total_due_usd",
        "cover_filing_deadline",
        "tax_year",
        "agi_usd",
        "total_tax_usd",
        "amount_owed_usd",
    },
}


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value)


def _parse_integer(value: str) -> int:
    return int(value)


def _parse_date(value: str) -> None:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d-%b-%Y"):
        try:
            datetime.strptime(value, fmt)
            return
        except ValueError:
            continue
    raise ValueError(value)


def _parse_datetime(value: str) -> None:
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%d.%m.%Y / %H:%M"):
        try:
            datetime.strptime(value, fmt)
            return
        except ValueError:
            continue
    raise ValueError(value)


def _fact_map(doc: DocumentFacts) -> dict[str, str]:
    return {fact.key: fact.value for fact in doc.facts}


def document_facts_from_dict(payload: dict[str, object]) -> DocumentFacts:
    return DocumentFacts(
        relative_path=str(payload["relative_path"]),
        doc_type=str(payload["doc_type"]),
        parser=str(payload["parser"]),
        status=str(payload["status"]),
        facts=[FactRecord(**fact) for fact in payload.get("facts", [])],
        warnings=[str(warning) for warning in payload.get("warnings", [])],
        provider=payload.get("provider"),
        document_family=payload.get("document_family"),
        country_of_origin=payload.get("country_of_origin"),
        owner=payload.get("owner"),
        tax_year=payload.get("tax_year"),
        parser_name=payload.get("parser_name"),
        parser_version=payload.get("parser_version"),
    )


def validate_document_facts(doc: DocumentFacts) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    facts = _fact_map(doc)

    if doc.status != "ok" and ".evidence-only" not in Path(doc.relative_path).parts:
        issues.append(
            ValidationIssue(
                doc.relative_path,
                "error",
                "document_extraction_status",
                f"Document extraction status is `{doc.status}`; non-evidence documents must extract cleanly before tax-law calculations.",
            )
        )

    if doc.status == "ok":
        missing = sorted(REQUIRED_FIELDS.get(doc.doc_type, set()) - set(facts))
        for key in missing:
            issues.append(
                ValidationIssue(doc.relative_path, "error", "missing_required_field", f"Missing required fact `{key}`")
            )
        if doc.warnings:
            for warning in doc.warnings:
                issues.append(ValidationIssue(doc.relative_path, "error", "parser_warning", warning))

    for fact in doc.facts:
        if fact.source.get("page", 0) <= 0:
            issues.append(ValidationIssue(doc.relative_path, "error", "invalid_source_page", f"{fact.key} has non-positive source page"))
        if not str(fact.source.get("section", "")).strip():
            issues.append(ValidationIssue(doc.relative_path, "error", "missing_source_section", f"{fact.key} is missing source section"))
        if not str(fact.source.get("snippet", "")).strip():
            issues.append(ValidationIssue(doc.relative_path, "error", "missing_source_snippet", f"{fact.key} is missing source snippet"))
        try:
            if fact.value_type == "decimal":
                _parse_decimal(fact.value)
            elif fact.value_type == "integer":
                _parse_integer(fact.value)
            elif fact.value_type == "date":
                _parse_date(fact.value)
            elif fact.value_type == "datetime":
                _parse_datetime(fact.value)
            elif fact.value_type == "text" and not fact.value.strip():
                raise ValueError("blank text")
        except (InvalidOperation, ValueError) as exc:
            issues.append(
                ValidationIssue(doc.relative_path, "error", "invalid_value_type", f"{fact.key} value `{fact.value}` invalid for type `{fact.value_type}`: {exc}")
            )

    def decimal(key: str) -> Decimal | None:
        value = facts.get(key)
        return Decimal(value) if value is not None else None

    if doc.doc_type == "german_lohnsteuer_pdf":
        gross = decimal("gross_wage_eur")
        wage_tax = decimal("withheld_wage_tax_eur")
        soli = decimal("withheld_solidarity_surcharge_eur")
        multi = decimal("multiannual_wage_eur")
        pension_employee = decimal("employee_pension_contribution_eur")
        health = decimal("employee_health_insurance_eur")
        nursing = decimal("employee_nursing_care_insurance_eur")
        unemployment = decimal("employee_unemployment_insurance_eur")
        if gross is not None and wage_tax is not None and wage_tax > gross:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Withheld wage tax exceeds gross wage"))
        if gross is not None and soli is not None and soli > gross:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Solidarity surcharge exceeds gross wage"))
        if wage_tax is not None and soli is not None and soli > wage_tax:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Solidarity surcharge exceeds wage tax"))
        if gross is not None and multi is not None and multi > gross:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Multiannual wage exceeds gross wage"))
        for label, value in {
            "employee_pension_contribution_eur": pension_employee,
            "employee_health_insurance_eur": health,
            "employee_nursing_care_insurance_eur": nursing,
            "employee_unemployment_insurance_eur": unemployment,
        }.items():
            if gross is not None and value is not None and value > gross:
                issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", f"{label} exceeds gross wage"))

    if doc.doc_type in {"schwab_1099_pdf", "schwab_1099_csv", "us_1040_packet_pdf"}:
        qualified = decimal("qualified_dividends_box_1b_usd") or decimal("form_1040_line_3a_qualified_dividends_usd")
        ordinary = decimal("ordinary_dividends_box_1a_usd") or decimal("form_1040_line_3b_ordinary_dividends_usd")
        if qualified is not None and ordinary is not None and qualified > ordinary:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Qualified dividends exceed ordinary dividends"))

    if doc.doc_type == "us_1040_packet_pdf":
        line_1h = decimal("form_1040_line_1h_other_earned_income_usd")
        line_1z = decimal("form_1040_line_1z_total_income_usd")
        if line_1h is not None and line_1z is not None and line_1h > line_1z:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Form 1040 line 1h exceeds line 1z"))

    if doc.doc_type == "us_8879_pdf":
        payable = decimal("cover_income_tax_payable_usd")
        penalty = decimal("late_payment_penalty_interest_usd")
        total = decimal("cover_total_due_usd")
        amount_owed = decimal("amount_owed_usd")
        total_tax = decimal("total_tax_usd")
        if payable is not None and penalty is not None and total is not None and payable + penalty != total:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Cover total due does not equal payable plus penalty"))
        if amount_owed is not None and total_tax is not None and amount_owed != total_tax:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Form 8879 amount owed does not equal total tax"))

    if doc.doc_type == "n26_transfer_confirmation_pdf":
        amount = decimal("amount_eur")
        fee = decimal("fee_eur")
        if amount is not None and fee is not None and fee > amount:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Transfer fee exceeds transfer amount"))

    if doc.doc_type == "jpm_1099_pdf":
        proceeds = decimal("short_term_type_a_proceeds_usd")
        basis = decimal("short_term_type_a_cost_basis_usd")
        market_discount = decimal("short_term_type_a_market_discount_usd")
        wash_sale = decimal("short_term_type_a_wash_sale_loss_disallowed_usd")
        net_gain = decimal("short_term_type_a_net_gain_usd")
        if None not in (proceeds, basis, market_discount, wash_sale, net_gain):
            expected = proceeds - basis + market_discount + wash_sale
            if expected != net_gain:
                issues.append(
                    ValidationIssue(doc.relative_path, "error", "relative_value", "JPM net gain does not match proceeds - basis + market discount + wash sale")
                )

    if doc.doc_type == "german_capital_certificate_pdf":
        capital_income = decimal("capital_income_line_7_eur")
        stock_sale_gain = decimal("stock_sale_gain_line_8_eur")
        saver_allowance = decimal("saver_allowance_used_line_17_eur")
        tax_withheld = decimal("capital_gains_tax_line_37_eur")
        foreign_tax_credit = decimal("foreign_tax_credit_line_40_eur")
        if capital_income is not None and stock_sale_gain is not None and stock_sale_gain > capital_income:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Stock-sale gain exceeds total capital income"))
        if capital_income is not None and saver_allowance is not None and saver_allowance > capital_income:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Saver allowance used exceeds total capital income"))
        if capital_income is not None and tax_withheld is not None and tax_withheld > capital_income:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Withheld tax exceeds total capital income"))
        if tax_withheld is not None and foreign_tax_credit is not None and foreign_tax_credit > tax_withheld:
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Foreign tax credit exceeds withheld tax"))

    if doc.doc_type == "shareworks_statement_pdf":
        has_statement_variant = {"published_date", "statement_period_start", "statement_period_end", "transaction_row_count"} <= set(facts)
        has_summary_variant = {"summary_period_start", "summary_period_end", "account_number", "company_name"} <= set(facts)
        has_no_records_variant = facts.get("report_result") == "no_records_found"
        if not has_no_records_variant and "account_number" not in facts:
            issues.append(ValidationIssue(doc.relative_path, "error", "missing_required_field", "Missing required fact `account_number`"))
        if not any((has_statement_variant, has_summary_variant, has_no_records_variant)):
            issues.append(ValidationIssue(doc.relative_path, "error", "relative_value", "Shareworks facts do not match any supported statement variant"))

    if doc.doc_type == "coinbase_1099_da_pdf":
        for prefix in ("short_term", "long_term"):
            proceeds = decimal(f"{prefix}_proceeds_usd")
            basis = decimal(f"{prefix}_cost_basis_usd")
            gain = decimal(f"{prefix}_gain_or_loss_usd")
            if None not in (proceeds, basis, gain) and proceeds - basis != gain:
                issues.append(
                    ValidationIssue(doc.relative_path, "error", "relative_value", f"{prefix} gain/loss does not equal proceeds - cost basis")
                )

    return issues


def validate_all_facts(paths: YearPaths, index_rows: list[dict[str, object]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for row in index_rows:
        doc = document_facts_from_dict(json.loads(_resolve_indexed_fact_path(paths, str(row["json_path"])).read_text(encoding="utf-8")))
        doc_issues = validate_document_facts(doc)
        issues.extend(doc_issues)

    payload = [issue.to_dict() for issue in issues]
    (paths.facts_root / "validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    lines = [
        f"# Facts Validation - {paths.year}",
        "",
        f"- issues: `{len(issues)}`",
    ]
    if not issues:
        lines.append("- result: `ok`")
    else:
        lines.extend(["", "## Issues"])
        for issue in issues:
            lines.append(f"- `{issue.severity}` `{issue.relative_path}` `{issue.rule}`: {issue.message}")
    (paths.facts_root / "VALIDATION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return issues


def _resolve_indexed_fact_path(paths: YearPaths, indexed_path: str) -> Path:
    path = Path(indexed_path)
    if path.is_absolute():
        return path
    workspace_relative = paths.year_root / path
    if workspace_relative.exists():
        return workspace_relative
    project_relative = paths.project_root / path
    if project_relative.exists():
        return project_relative
    return workspace_relative
