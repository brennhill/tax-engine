from __future__ import annotations

from pathlib import Path
from typing import Iterable

from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import load_final_legal_output_2025
from tax_pipeline.year_runtime import active_year_paths, analysis_root


YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STEPS = analysis_root(Path(__file__), default_year=2025)
VERBOSE_MD = STEPS / "verbose-report.md"


def _enabled_jurisdictions(profile: dict) -> dict[str, bool]:
    jurisdictions = profile.get("jurisdictions", {})
    germany = jurisdictions.get("germany", {})
    usa = jurisdictions.get("usa", {})
    return {
        "germany": bool(germany.get("enabled", True)),
        "usa": bool(usa.get("enabled", True)),
    }


def _validate_trace(rows: list[dict[str, str]], *, value_column: str, label: str) -> list[dict[str, str]]:
    required_columns = {"step", value_column, "note", "legal_reference", "authority_url"}
    present = set(rows[0].keys()) if rows else set()
    missing = sorted(required_columns - present)
    if missing:
        raise ValueError(f"Missing required columns for {label}: {', '.join(missing)}")

    for index, row in enumerate(rows, start=1):
        missing_values = [
            column
            for column in ("step", value_column, "legal_reference", "authority_url")
            if not row.get(column, "").strip()
        ]
        if missing_values:
            raise ValueError(
                f"Missing required values for {label}: row {index}:{','.join(missing_values)}"
            )
    return rows


def _money(results: dict, *path: str) -> str:
    current = results
    for part in path:
        current = current[part]
    return str(current)


def _trace_table(rows: Iterable[dict[str, str]], *, value_column: str, currency: str) -> list[str]:
    lines = [
        "| Step | Amount | Legal Reference | Official Authority | Calculation Note |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for row in rows:
        amount = f"{row[value_column]} {currency}".strip()
        note = row.get("note", "")
        precision = row.get("precision_note", "")
        if precision:
            note = f"{note} Precision: {precision}"
        # Trace authority cells often contain multiple official URLs separated by "|".
        # Escape table metacharacters so the legal-reference table remains auditable Markdown.
        def cell(value: str) -> str:
            return str(value).replace("|", "\\|")

        lines.append(
            f"| {cell(row['step'])} | {cell(amount)} | {cell(row['legal_reference'])} | {cell(row['authority_url'])} | {cell(note)} |"
        )
    return lines


def _germany_sections(final_output: dict) -> list[str]:
    forms = final_output["germany"]["forms"]
    audit = final_output["germany"]["legal_audit"]
    results = forms["results"]
    trace_rows = _validate_trace(audit["trace_rows"], value_column="value_eur", label="final-legal-output Germany trace")

    capital = results["capital"]
    ordinary = results["ordinary"]
    refunds = results["refunds"]
    vanilla = results["vanilla_checkpoint"]

    lines = [
        "### Germany Investment Facts",
        f"- Stock gains: `{capital['stock_gain_eur']} EUR`",
        f"- Stock loss carryforward used: `{capital['stock_loss_carryforward_used_eur']} EUR`",
        f"- Stock loss carryforward remaining: `{capital['stock_loss_carryforward_remaining_eur']} EUR`",
        f"- Fund gains: `{capital['fund_gain_eur']} EUR`",
        f"- Equity-fund income/gains before Teilfreistellung: `{capital['equity_fund_total_eur']} EUR`",
        f"- Non-equity fund income/gains: `{capital['non_equity_fund_total_eur']} EUR`",
        f"- Option gains: `{capital['option_gain_eur']} EUR`",
        f"- Positive dividend/interest cashflows: `{capital['positive_income_total_eur']} EUR`",
        f"- Explicit foreign tax paid: `{capital['explicit_foreign_tax_total_eur']} EUR`",
        f"- Private-sale result: `{results['private_sales']['private_sale_result_eur']} EUR`",
        "",
        "### Germany Ordinary And Final Results",
        f"- Filing posture: `{ordinary['filing_posture']}`",
        f"- Taxable income: `{ordinary['joint_taxable_income_eur']} EUR`",
        f"- Income tax: `{ordinary['joint_income_tax_eur']} EUR`",
        f"- Solidarity surcharge: `{ordinary['joint_solidarity_surcharge_eur']} EUR`",
        f"- Ordinary refund before capital: `{ordinary['ordinary_refund_before_capital_eur']} EUR`",
        f"- Capital tax after Teilfreistellung and treaty-credit check: `{capital['capital_tax_with_teilfreistellung_after_treaty_eur']} EUR`",
        f"- Final refund if positive / balance due if negative: `{refunds['final_target_refund_eur']} EUR`",
        f"- Vanilla checkpoint refund if positive / balance due if negative: `{vanilla['refund_or_balance_due_eur']} EUR`",
        "",
        "## Germany Full Calculation Trace",
        "Every row below comes from `final-legal-output.json`, which carries the Germany legal trace with a legal reference for each calculation step.",
        "",
        *_trace_table(trace_rows, value_column="value_eur", currency="EUR"),
        "",
    ]
    return lines


def _usa_sections(final_output: dict) -> list[str]:
    forms = final_output["usa"]["forms"]
    audit = final_output["usa"]["legal_audit"]
    tax = forms["tax_estimate"]
    capital_results = forms["capital_results"]
    trace_rows = _validate_trace(audit["trace_rows"], value_column="amount_usd", label="final-legal-output U.S. trace")

    capital = capital_results["capital"]
    income = capital_results["income"]
    payments = tax["payments"]
    vanilla = tax["vanilla_checkpoint"]

    lines = [
        "### U.S. Investment Facts",
        f"- Ordinary dividends: `{income['ordinary_dividends_usd']} USD`",
        f"- Qualified dividends: `{income['qualified_dividends_usd']} USD`",
        f"- Interest income: `{income['interest_income_usd']} USD`",
        f"- Capital-gain distributions: `{income['capital_gain_distributions_usd']} USD`",
        f"- Short-term total: `{capital['short_term_total_usd']} USD`",
        f"- Long-term total including capital-gain distributions: `{capital['long_term_total_with_cgd_usd']} USD`",
        f"- Section 1256 total: `{capital['section_1256_total_usd']} USD`",
        f"- Section 1256 short-term share: `{capital['section_1256_short_term_usd']} USD`",
        f"- Section 1256 long-term share: `{capital['section_1256_long_term_usd']} USD`",
        f"- Net capital after Section 1256: `{capital['net_capital_after_1256_usd']} USD`",
        f"- Capital loss deduction: `{capital['capital_loss_deduction_2025_usd']} USD`",
        f"- Capital loss carryforward: `{capital['tentative_capital_loss_carryforward_2026_usd']} USD`",
        f"- Foreign tax paid on passive income: `{income['foreign_tax_paid_usd']} USD`",
        "",
        "### U.S. Ordinary, FTC, Treaty, And Final Results",
        f"- Filing status: `{tax['filing_assumptions']['filing_status']}`",
        f"- Wages: `{tax['income']['wages_usd']} USD`",
        f"- Adjusted gross income: `{tax['income']['adjusted_gross_income_usd']} USD`",
        f"- Taxable income: `{tax['income']['taxable_income_usd']} USD`",
        f"- Regular tax before credits: `{tax['tax']['regular_tax_before_credits_usd']} USD`",
        f"- Total allowed FTC: `{tax['ftc']['total_allowed_ftc_usd']} USD`",
        f"- NIIT: `{tax['tax']['niit_usd']} USD`",
        f"- Total tax after base FTCs: `{tax['tax']['total_tax_usd']} USD`",
        f"- Total tax with treaty re-sourcing: `{tax['tax']['total_tax_with_treaty_resourcing_usd']} USD`",
        f"- Refund if positive / balance due if negative: `{payments['refund_if_positive_else_balance_due_usd']} USD`",
        f"- Treaty refund if positive / balance due if negative: `{payments['refund_if_positive_else_balance_due_with_treaty_resourcing_usd']} USD`",
        f"- Vanilla checkpoint refund if positive / balance due if negative: `{vanilla['refund_or_balance_due_usd']} USD`",
        "",
        "## U.S. Full Calculation Trace",
        "Every row below comes from `final-legal-output.json`, which carries the U.S. legal trace with a legal reference for each calculation step.",
        "",
        *_trace_table(trace_rows, value_column="amount_usd", currency="USD"),
        "",
    ]
    return lines


def render_verbose_report(paths: YearPaths = YEAR_PATHS) -> Path:
    final_output = load_final_legal_output_2025(paths)
    enabled = _enabled_jurisdictions(final_output.get("germany", {}).get("forms", {}).get("profile", {}))
    lines = [
        "# Verbose 2025 Tax Calculation Report",
        "",
        "This report is derived from `final-legal-output.json`; it does not recompute tax.",
        "Its job is to make the calculation auditable: first the high-level income/gain facts, then the law-referenced calculation rows used by each country model.",
        "",
        "## High-Level Facts",
        "",
    ]

    if enabled["germany"]:
        lines.extend(_germany_sections(final_output))
    if enabled["usa"]:
        lines.extend(_usa_sections(final_output))
    if not enabled["germany"] and not enabled["usa"]:
        lines.append("No jurisdictions are enabled in `config/profile.json`.")

    paths.analysis_root.mkdir(parents=True, exist_ok=True)
    output_path = paths.analysis_root / VERBOSE_MD.name
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    render_verbose_report(YEAR_PATHS)


if __name__ == "__main__":
    main()
