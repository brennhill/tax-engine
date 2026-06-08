from __future__ import annotations

import csv
import io
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.provenance import fact
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


BOX_FACTS = {
    ("Form 1099DIV", "1a"): "ordinary_dividends_box_1a_usd",
    ("Form 1099DIV", "1b"): "qualified_dividends_box_1b_usd",
    ("Form 1099DIV", "2a"): "capital_gain_distributions_box_2a_usd",
    ("Form 1099DIV", "3"): "nondividend_distributions_box_3_usd",
    ("Form 1099DIV", "7"): "foreign_tax_paid_box_7_usd",
    ("Form 1099INT", "1"): "interest_income_box_1_usd",
    ("Form 1099MISC", "8"): "substitute_payments_box_8_usd",
}


def extract_schwab_1099_csv(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = pages[0]
    rows = list(csv.reader(io.StringIO(text)))
    facts: list[FactRecord] = []
    warnings: list[str] = []

    current_form: str | None = None
    in_1099b = False
    disposition_rows = 0

    for raw_row in rows:
        row = [cell.strip() for cell in raw_row]
        if not any(row):
            continue
        first = row[0]
        if first.startswith("Form 1099"):
            current_form = first
            in_1099b = first == "Form 1099 B"
            continue

        if current_form == "Form 1099 B":
            if row[0] == "Description of property (Example 100 sh. XYZ Co.)":
                continue
            if row[0] and row[0] != "1a":
                disposition_rows += 1
            continue

        if len(row) < 5 or row[0] in {"Box", "Corrected", "Account", "Tax Year"}:
            continue

        fact_key = BOX_FACTS.get((current_form or "", row[0]))
        if fact_key is None:
            continue
        amount_raw = row[2] or row[3]
        if not amount_raw:
            continue
        facts.append(
            fact(
                key=fact_key,
                value=fmt_money(parse_us_amount(amount_raw)),
                value_type="decimal",
                unit="USD",
                page=1,
                section=f"{current_form} box {row[0]}",
                snippet_text=",".join(raw_row),
                relative_path=relative_path.as_posix(),
            )
        )

    if disposition_rows:
        facts.append(
            fact(
                key="form_1099_b_row_count",
                value=str(disposition_rows),
                value_type="integer",
                unit="rows",
                page=1,
                section="Form 1099 B disposition rows",
                snippet_text="Form 1099 B",
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "schwab_1099_csv",
        "deterministic.schwab_1099_csv.v1",
        status,
        facts,
        warnings,
    )
