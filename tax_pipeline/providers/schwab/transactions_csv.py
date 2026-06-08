from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tax_pipeline.providers.shared.csv_utils import csv_dict_rows
from tax_pipeline.providers.shared.dates import iso_us_date, primary_us_date
from tax_pipeline.providers.shared.provenance import fact
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_schwab_transactions_csv(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = pages[0]
    facts: list[FactRecord] = []
    warnings: list[str] = []
    fieldnames, rows = csv_dict_rows(text)
    if not rows:
        return DocumentFacts(
            relative_path.as_posix(),
            "schwab_transactions_csv",
            "deterministic.schwab_transactions_csv.v1",
            "no_facts_extracted",
            [],
            ["No transaction rows found"],
        )

    dates = [primary_us_date(row["Date"]) for row in rows if row.get("Date")]
    actions = sorted({row["Action"] for row in rows if row.get("Action")})
    min_date = min(dates, key=lambda value: datetime.strptime(value, "%m/%d/%Y"))
    max_date = max(dates, key=lambda value: datetime.strptime(value, "%m/%d/%Y"))
    summary_snippet = "\n".join(text.splitlines()[:5])
    first_date_row = next(row for row in rows if primary_us_date(row.get("Date", "")) == min_date)
    last_date_row = next(row for row in rows if primary_us_date(row.get("Date", "")) == max_date)

    facts.extend(
        [
            fact(
                key="transaction_row_count",
                value=str(len(rows)),
                value_type="integer",
                unit="rows",
                page=1,
                section="Schwab transactions CSV summary",
                snippet_text=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=f"Columns: {', '.join(fieldnames)}",
            ),
            fact(
                key="first_transaction_date",
                value=iso_us_date(min_date),
                value_type="date",
                unit="",
                page=1,
                section="Schwab transactions CSV earliest date",
                snippet_text=",".join(first_date_row.get(name, "") for name in fieldnames),
                relative_path=relative_path.as_posix(),
            ),
            fact(
                key="last_transaction_date",
                value=iso_us_date(max_date),
                value_type="date",
                unit="",
                page=1,
                section="Schwab transactions CSV latest date",
                snippet_text=",".join(last_date_row.get(name, "") for name in fieldnames),
                relative_path=relative_path.as_posix(),
            ),
            fact(
                key="distinct_action_count",
                value=str(len(actions)),
                value_type="integer",
                unit="actions",
                page=1,
                section="Schwab transactions CSV distinct actions",
                snippet_text=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=", ".join(actions),
            ),
        ]
    )

    return DocumentFacts(
        relative_path.as_posix(),
        "schwab_transactions_csv",
        "deterministic.schwab_transactions_csv.v1",
        "ok",
        facts,
        warnings,
    )
