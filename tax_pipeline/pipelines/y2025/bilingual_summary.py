"""Bilingual high-level summary renderer for the 2025 tax year.

This module produces ``analysis-steps/2025-bilingual-summary.md`` — a
companion document that aggregates already-computed values from the
upstream rule-graph outputs (``germany-model-results.json``,
``us-tax-estimate.json``, ``crypto-private-sales-results.json``) and
the normalized facts (Lohnsteuerbescheinigung, Schwab 1099 composite)
into one bilingual readout.

Authoritative narrative authority continues to live in the per-rule
files ``DE-de-narrative.md`` / ``DE-en-narrative.md`` /
``US-en-narrative.md`` rendered by ``rule_narratives.py``. This module
intentionally performs no legal math (CLAUDE.md invariant I5 — no
``Decimal`` arithmetic on rule outputs in pipeline orchestrators) —
every numeric value is read as a string from the upstream JSON and
formatted for display only. Cross-document links in the rendered
output use bare filenames so a zipped ``analysis-steps/`` directory
remains self-contained.

Output is written atomically via ``atomic_write_text`` (invariant I9).
"""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.paths import YearPaths
from tax_pipeline.year_runtime import active_year_paths


YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)

TEMPLATE_ROOT = Path(__file__).resolve().parents[2] / "narrative" / "templates"
TEMPLATE_NAME = "SUMMARY-BILINGUAL.jinja"
OUTPUT_FILENAME = "2025-bilingual-summary.md"


def _fmt(value: object, *, default: str = "—") -> str:
    """Format a Decimal-like value with thousands separators and two decimals.

    Strings, ints, floats, and Decimals all pass through. Empty / None
    values render as ``default``. Non-numeric strings pass through
    unchanged (so callers can pre-stuff a string like "yes" or "01.01.-31.12.").
    """
    if value is None or value == "":
        return default
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    quantized = amount.quantize(Decimal("0.01"))
    integer_part, _, fractional_part = format(quantized, "f").partition(".")
    sign = ""
    if integer_part.startswith("-"):
        sign = "-"
        integer_part = integer_part[1:]
    grouped = "{:,}".format(int(integer_part))
    return f"{sign}{grouped}.{fractional_part}" if fractional_part else f"{sign}{grouped}"


def _load_json(path: Path) -> Mapping[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_facts(facts_json_path: Path) -> dict[str, str]:
    """Flatten a normalized facts JSON file into a ``{key: value}`` dict.

    The facts JSON shape is ``{"facts": [{"key": "...", "value": "..."}, ...]}``
    plus a few document-level metadata fields. We only care about the
    typed key/value pairs.
    """
    payload = _load_json(facts_json_path)
    facts = payload.get("facts", [])
    return {fact["key"]: fact["value"] for fact in facts if "key" in fact}


def _find_one(directory: Path, glob_pattern: str) -> Path | None:
    matches = sorted(directory.glob(glob_pattern))
    return matches[0] if matches else None


def _load_kap_rows(csv_path: Path, *, form_filter: str) -> list[dict[str, str]]:
    """Pick out ``germany-kap-summary.csv`` rows for one of the form sections.

    The CSV is in shape ``form, line, amount_eur, note``. ``form_filter``
    selects the form section (e.g., ``"Anlage KAP - Brenn"``); rows
    matching are returned in source order. Numeric amounts are
    re-formatted with thousands separators; the literal "yes" value
    used for tick-box rows passes through.
    """
    if not csv_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("form") != form_filter:
                continue
            line_value = row.get("line", "")
            note_value = row.get("note", "")
            amount_value = row.get("amount_eur", "")
            rows.append(
                {
                    "label": f"Z{line_value}" if line_value else "—",
                    "amount_eur": _fmt(amount_value),
                    "note": note_value,
                }
            )
    return rows


def _load_kap_inv_rows(csv_path: Path) -> list[dict[str, str]]:
    """Pick out the Anlage KAP-INV rows from ``germany-kap-summary.csv``."""
    if not csv_path.exists():
        return []
    rows: list[dict[str, str]] = []
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("form") != "Anlage KAP-INV":
                continue
            line_value = row.get("line", "")
            note_value = row.get("note", "")
            amount_value = row.get("amount_eur", "")
            rows.append(
                {
                    "label": f"Z{line_value}" if line_value else "—",
                    "amount_eur": _fmt(amount_value),
                    "note": note_value,
                }
            )
    return rows


def _load_fund_summary(csv_path: Path) -> dict[str, Any]:
    """Read ``germany-kap-inv-fund-summary.csv`` into structured context.

    Returns ``{"aktienfonds_symbols": [...], "sonstige_symbols": [...],
    "top_results": [...]}``. ``top_results`` is the per-fund table
    sorted by absolute combined result, capped to 12 rows — picks out
    the high-impact funds for the readout without dumping all 30+.
    """
    if not csv_path.exists():
        return {"aktienfonds_symbols": [], "sonstige_symbols": [], "top_results": []}
    aktienfonds_symbols: list[str] = []
    sonstige_symbols: list[str] = []
    combined_rows: list[tuple[Decimal, dict[str, str]]] = []
    fund_labels = {
        "IBIT": "BTC ETF",
        "FBTC": "Fidelity BTC",
        "FETH": "ETH ETF",
    }
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            symbol = row.get("symbol", "")
            fund_type = row.get("fund_type", "")
            combined_raw = row.get("combined_eur", "0")
            if fund_type == "aktienfonds":
                aktienfonds_symbols.append(symbol)
            elif fund_type == "sonstige":
                sonstige_symbols.append(symbol)
            try:
                combined_decimal = Decimal(combined_raw)
            except (InvalidOperation, ValueError):
                continue
            combined_rows.append(
                (
                    combined_decimal,
                    {
                        "symbol": symbol,
                        "label": fund_labels.get(symbol, ""),
                        "fund_type": fund_type,
                        "combined_eur": _fmt(combined_raw),
                    },
                )
            )
    # Sort by absolute magnitude descending, take top 12. Sorting is
    # display-only (not legal math) — the per-fund values themselves
    # are not modified.
    combined_rows.sort(key=lambda pair: abs(pair[0]), reverse=True)
    top_results = [row for _, row in combined_rows[:12]]
    return {
        "aktienfonds_symbols": aktienfonds_symbols,
        "sonstige_symbols": sonstige_symbols,
        "top_results": top_results,
    }


def _build_de_context(
    germany_results: Mapping[str, Any],
    person_1_facts: Mapping[str, str],
    person_2_facts: Mapping[str, str],
) -> dict[str, str]:
    """Assemble the ``de.*`` namespace passed to the template."""
    ordinary = germany_results.get("ordinary", {})
    capital = germany_results.get("capital", {})
    refunds = germany_results.get("refunds", {})
    filing_posture = ordinary.get("filing_posture", "")
    filing_posture_de = "Zusammenveranlagung" if filing_posture == "married_joint" else filing_posture
    return {
        "filing_posture": filing_posture,
        "filing_posture_de": filing_posture_de,
        "refund_eur": _fmt(refunds.get("final_target_refund_eur")),
        "gross_wages_eur": _fmt(ordinary.get("gross_wages_eur")),
        "work_expenses_eur": _fmt(ordinary.get("work_expenses_eur")),
        "total_special_expenses_eur": _fmt(ordinary.get("total_special_expenses_eur")),
        "other_income_22nr3_taxable_eur": _fmt(ordinary.get("other_income_22nr3_taxable_eur")),
        "joint_taxable_income_eur": _fmt(ordinary.get("joint_taxable_income_eur")),
        "joint_income_tax_eur": _fmt(ordinary.get("joint_income_tax_eur")),
        "joint_solidarity_surcharge_eur": _fmt(ordinary.get("joint_solidarity_surcharge_eur")),
        "withheld_wage_tax_eur": _fmt(ordinary.get("withheld_wage_tax_eur")),
        "withheld_wage_solidarity_surcharge_eur": _fmt(ordinary.get("withheld_wage_solidarity_surcharge_eur")),
        "prepayments_eur": _fmt(ordinary.get("prepayments_eur")),
        "capital_tax_with_teilfreistellung_before_treaty_eur": _fmt(
            capital.get("capital_tax_with_teilfreistellung_before_treaty_eur")
        ),
        "domestic_capital_withholding_credit_eur": _fmt(capital.get("domestic_capital_withholding_credit_eur")),
        "stock_loss_carryforward_used_eur": _fmt(capital.get("stock_loss_carryforward_used_eur")),
        "dher_stock_gain_eur": _fmt(capital.get("dher_stock_gain_eur")),
        "saver_allowance_used_eur": _fmt(capital.get("saver_allowance_used_eur")),
        # Per-person wage detail — pulled from the normalized
        # Lohnsteuerbescheinigung facts so the source-anchor is visible
        # in the readout. Use ``_fmt(default="—")`` so missing facts
        # render as a dash, not an empty cell (I4: never silently zero).
        "person_1_period": person_1_facts.get("period_certification", "—"),
        "person_1_gross_wage_eur": _fmt(person_1_facts.get("gross_wage_eur")),
        "person_1_withheld_wage_tax_eur": _fmt(person_1_facts.get("withheld_wage_tax_eur")),
        "person_1_withheld_soli_eur": _fmt(person_1_facts.get("withheld_solidarity_surcharge_eur")),
        "person_1_multiannual_wage_eur": _fmt(person_1_facts.get("multiannual_wage_eur")),
        "person_1_employer_pension_eur": _fmt(person_1_facts.get("employer_pension_contribution_eur")),
        "person_1_employee_pension_eur": _fmt(person_1_facts.get("employee_pension_contribution_eur")),
        "person_1_employee_health_eur": _fmt(person_1_facts.get("employee_health_insurance_eur")),
        "person_1_employee_nursing_eur": _fmt(person_1_facts.get("employee_nursing_care_insurance_eur")),
        "person_1_employee_unemployment_eur": _fmt(person_1_facts.get("employee_unemployment_insurance_eur")),
        "person_2_period": person_2_facts.get("period_certification", "—"),
        "person_2_gross_wage_eur": _fmt(person_2_facts.get("gross_wage_eur")),
        "person_2_withheld_wage_tax_eur": _fmt(person_2_facts.get("withheld_wage_tax_eur")),
        "person_2_withheld_soli_eur": _fmt(person_2_facts.get("withheld_solidarity_surcharge_eur")),
        "person_2_multiannual_wage_eur": _fmt(person_2_facts.get("multiannual_wage_eur")),
        "person_2_employer_pension_eur": _fmt(person_2_facts.get("employer_pension_contribution_eur")),
        "person_2_employee_pension_eur": _fmt(person_2_facts.get("employee_pension_contribution_eur")),
        "person_2_employee_health_eur": _fmt(person_2_facts.get("employee_health_insurance_eur")),
        "person_2_employee_nursing_eur": _fmt(person_2_facts.get("employee_nursing_care_insurance_eur")),
        "person_2_employee_unemployment_eur": _fmt(person_2_facts.get("employee_unemployment_insurance_eur")),
    }


def _build_us_context(us_results: Mapping[str, Any]) -> dict[str, str]:
    """Assemble the ``us.*`` namespace passed to the template."""
    income = us_results.get("income", {})
    capital = us_results.get("capital", {})
    tax = us_results.get("tax", {})
    ftc = us_results.get("ftc", {})
    treaty = us_results.get("treaty_resourcing", {})
    payments = us_results.get("payments", {})
    filing = us_results.get("filing_assumptions", {})
    return {
        "irs_rate": filing.get("irs_yearly_average_eur_per_usd", "0.886"),
        "wages_usd": _fmt(income.get("wages_usd")),
        "ordinary_dividends_usd": _fmt(income.get("ordinary_dividends_usd")),
        "qualified_dividends_usd": _fmt(income.get("qualified_dividends_usd")),
        "interest_income_usd": _fmt(income.get("interest_income_usd")),
        "capital_gain_distributions_usd": _fmt(income.get("capital_gain_distributions_usd")),
        "substitute_payments_usd": _fmt(income.get("substitute_payments_usd")),
        "staking_income_usd": _fmt(income.get("staking_income_usd")),
        "nondividend_distributions_usd": _fmt(income.get("nondividend_distributions_usd")),
        "foreign_tax_paid_usd": _fmt(income.get("foreign_tax_paid_usd")),
        "schedule_1_other_income_usd": _fmt(income.get("schedule_1_other_income_usd")),
        "adjusted_gross_income_usd": _fmt(income.get("adjusted_gross_income_usd")),
        "taxable_income_usd": _fmt(income.get("taxable_income_usd")),
        "short_box_a_usd": _fmt(capital.get("short_box_a_usd")),
        "short_box_b_usd": _fmt(capital.get("short_box_b_usd")),
        "short_box_h_usd": _fmt(capital.get("short_box_h_usd")),
        "long_box_d_usd": _fmt(capital.get("long_box_d_usd")),
        "long_box_k_usd": _fmt(capital.get("long_box_k_usd")),
        "section_1256_total_usd": _fmt(capital.get("section_1256_total_usd")),
        "net_capital_before_1256_usd": _fmt(capital.get("net_capital_before_1256_usd")),
        "net_capital_after_1256_usd": _fmt(capital.get("net_capital_after_1256_usd")),
        "capital_loss_deduction_2025_usd": _fmt(capital.get("capital_loss_deduction_2025_usd")),
        "capital_loss_carryforward_2026_usd": _fmt(capital.get("tentative_capital_loss_carryforward_2026_usd")),
        "regular_tax_usd": _fmt(tax.get("regular_tax_before_credits_usd")),
        "niit_usd": _fmt(tax.get("niit_usd")),
        "total_tax_usd": _fmt(tax.get("total_tax_usd")),
        "total_tax_with_treaty_resourcing_usd": _fmt(tax.get("total_tax_with_treaty_resourcing_usd")),
        "general_ftc_carryover_2024_usd": _fmt(ftc.get("general_ftc_carryover_2024_usd")),
        "passive_ftc_carryover_2024_usd": _fmt(ftc.get("passive_ftc_carryover_2024_usd")),
        "total_allowed_ftc_usd": _fmt(ftc.get("total_allowed_ftc_usd")),
        "us_source_dividends_usd": _fmt(treaty.get("us_source_dividends_usd")),
        "treaty_resourcing_us_limitation_usd": _fmt(treaty.get("treaty_resourcing_us_limitation_usd")),
        "german_residual_tax_on_us_source_dividends_usd": _fmt(
            treaty.get("german_residual_tax_on_us_source_dividends_usd")
        ),
        "treaty_resourcing_additional_ftc_usd": _fmt(treaty.get("treaty_resourcing_additional_ftc_usd")),
        "estimated_payment_usd": _fmt(payments.get("estimated_payment_usd")),
        "refund_base_usd": _fmt(payments.get("refund_without_treaty_resourcing_usd")),
        "refund_treaty_usd": _fmt(payments.get("refund_with_treaty_resourcing_usd")),
    }


def _build_schwab_context(facts: Mapping[str, str]) -> dict[str, str]:
    """Schwab 1099-composite normalized facts → ``schwab.*`` template ns."""
    return {
        "ordinary_dividends_usd": _fmt(facts.get("ordinary_dividends_box_1a_usd")),
        "qualified_dividends_usd": _fmt(facts.get("qualified_dividends_box_1b_usd")),
        "capital_gain_distributions_usd": _fmt(facts.get("capital_gain_distributions_box_2a_usd")),
        "nondividend_distributions_usd": _fmt(facts.get("nondividend_distributions_box_3_usd")),
        "foreign_tax_paid_usd": _fmt(facts.get("foreign_tax_paid_box_7_usd")),
        "interest_income_usd": _fmt(facts.get("interest_income_box_1_usd")),
        "substitute_payments_usd": _fmt(facts.get("substitute_payments_box_8_usd")),
        "foreign_source_income_usd": _fmt(facts.get("foreign_source_income_summary_usd")),
    }


def _build_private_sales_context(results: Mapping[str, Any]) -> dict[str, str]:
    """Private-sales (Coinbase § 23 EStG) JSON → ``private_sales.*``."""
    return {
        "result_eur": _fmt(results.get("private_sale_result_eur")),
        "prior_carryforward_eur": _fmt(results.get("prior_private_sale_carryforward_eur")),
        "updated_carryforward_eur": _fmt(results.get("updated_private_sale_carryforward_eur")),
    }


def render_bilingual_summary(paths: YearPaths = YEAR_PATHS) -> Path:
    """Render the bilingual summary into ``analysis-steps/`` and return the path.

    Reads (all already-computed by upstream stages):

    - ``analysis-steps/germany-model-results.json``
    - ``analysis-steps/us-tax-estimate.json``
    - ``analysis-steps/crypto-private-sales-results.json`` (optional)
    - ``analysis-steps/germany-kap-summary.csv``
    - ``analysis-steps/germany-kap-inv-fund-summary.csv``
    - ``normalized/facts/germany_person_1_*_Lohnsteuerbescheinigung_*.facts.json``
    - ``normalized/facts/germany_person_2_*_Lohnsteuerbescheinigung_*.facts.json``
    - ``normalized/facts/brokers_1099_Composite*.facts.json``

    Writes ``analysis-steps/2025-bilingual-summary.md`` atomically.
    """
    analysis = paths.analysis_root
    normalized_facts = paths.workspace_root / "normalized" / "facts"

    germany_results_path = analysis / "germany-model-results.json"
    us_results_path = analysis / "us-tax-estimate.json"
    private_sales_path = analysis / "crypto-private-sales-results.json"
    kap_summary_csv = analysis / "germany-kap-summary.csv"
    kap_inv_fund_csv = analysis / "germany-kap-inv-fund-summary.csv"

    germany_results = _load_json(germany_results_path) if germany_results_path.exists() else {}
    us_results = _load_json(us_results_path) if us_results_path.exists() else {}
    private_sales = _load_json(private_sales_path) if private_sales_path.exists() else {}

    person_1_path = _find_one(
        normalized_facts, "germany_person_1_*_Lohnsteuerbescheinigung_*_pdf.facts.json"
    )
    person_2_path = _find_one(
        normalized_facts, "germany_person_2_*_Lohnsteuerbescheinigung_*_pdf.facts.json"
    )
    person_1_facts = _load_facts(person_1_path) if person_1_path else {}
    person_2_facts = _load_facts(person_2_path) if person_2_path else {}

    schwab_path = _find_one(normalized_facts, "brokers_1099_Composite*.facts.json")
    schwab_facts = _load_facts(schwab_path) if schwab_path else {}

    workspace_label = paths.workspace_root.name + " (VZ " + str(paths.year) + ")"

    context: dict[str, Any] = {
        "workspace_label": workspace_label,
        "de": _build_de_context(germany_results, person_1_facts, person_2_facts),
        "us": _build_us_context(us_results),
        "schwab": _build_schwab_context(schwab_facts),
        "private_sales": _build_private_sales_context(private_sales),
        "kap_brenn_rows": _load_kap_rows(kap_summary_csv, form_filter="Anlage KAP - Brenn"),
        "kap_lien_rows": _load_kap_rows(kap_summary_csv, form_filter="Anlage KAP - Lien"),
        "kap_inv_rows": _load_kap_inv_rows(kap_summary_csv),
        "funds": _load_fund_summary(kap_inv_fund_csv),
    }

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_ROOT)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    try:
        rendered = env.get_template(TEMPLATE_NAME).render(**context)
    except TemplateError as exc:
        raise RuntimeError(f"Failed to render {TEMPLATE_NAME}: {exc}") from exc

    output_path = analysis / OUTPUT_FILENAME
    atomic_write_text(output_path, rendered.rstrip() + "\n")
    return output_path


def main() -> None:
    output_path = render_bilingual_summary(YEAR_PATHS)
    print(f"Bilingual summary → {output_path.relative_to(YEAR_PATHS.workspace_root)}")


__all__: Iterable[str] = ("main", "render_bilingual_summary")


if __name__ == "__main__":
    main()
