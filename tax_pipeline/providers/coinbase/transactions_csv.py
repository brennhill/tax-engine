from __future__ import annotations

import csv
import io
from pathlib import Path

from tax_pipeline.providers.shared.provenance import fact
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def extract_coinbase_transactions_csv(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = pages[0]
    facts: list[FactRecord] = []
    warnings: list[str] = []
    raw_rows = list(csv.reader(io.StringIO(text)))
    rows = [row for row in raw_rows if any(cell.strip() for cell in row)]

    user_row = next((row for row in rows if row and row[0] == "User"), None)
    header_index = next((index for index, row in enumerate(rows) if row and row[0] == "ID"), None)
    if header_index is None:
        return DocumentFacts(
            relative_path.as_posix(),
            "coinbase_transactions_csv",
            "deterministic.coinbase_transactions_csv.v1",
            "no_facts_extracted",
            [],
            ["Missing Coinbase transactions header row"],
        )

    header = rows[header_index]
    data_rows = [dict(zip(header, row)) for row in rows[header_index + 1 :] if any(cell.strip() for cell in row)]
    if not data_rows:
        return DocumentFacts(
            relative_path.as_posix(),
            "coinbase_transactions_csv",
            "deterministic.coinbase_transactions_csv.v1",
            "no_facts_extracted",
            [],
            ["No Coinbase transaction rows found"],
        )

    timestamps = [row["Timestamp"].strip() for row in data_rows if row.get("Timestamp")]
    transaction_types = sorted({row["Transaction Type"].strip() for row in data_rows if row.get("Transaction Type")})
    min_timestamp = min(timestamps)
    max_timestamp = max(timestamps)
    summary_snippet = "\n".join(",".join(row) for row in rows[:5])

    if user_row and len(user_row) >= 2:
        facts.append(
            fact(
                key="user_name",
                value=user_row[1].strip(),
                value_type="text",
                unit="",
                page=1,
                section="Coinbase transactions user row",
                snippet_text=",".join(user_row),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing Coinbase user row")

    facts.extend(
        [
            fact(
                key="transaction_row_count",
                value=str(len(data_rows)),
                value_type="integer",
                unit="rows",
                page=1,
                section="Coinbase transactions CSV summary",
                snippet_text=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=f"Columns: {', '.join(header)}",
            ),
            fact(
                key="first_transaction_timestamp",
                value=min_timestamp,
                value_type="datetime",
                unit="UTC",
                page=1,
                section="Coinbase transactions earliest timestamp",
                snippet_text=next(",".join(row.get(col, "") for col in header) for row in data_rows if row.get("Timestamp", "").strip() == min_timestamp),
                relative_path=relative_path.as_posix(),
            ),
            fact(
                key="last_transaction_timestamp",
                value=max_timestamp,
                value_type="datetime",
                unit="UTC",
                page=1,
                section="Coinbase transactions latest timestamp",
                snippet_text=next(",".join(row.get(col, "") for col in header) for row in data_rows if row.get("Timestamp", "").strip() == max_timestamp),
                relative_path=relative_path.as_posix(),
            ),
            fact(
                key="distinct_transaction_type_count",
                value=str(len(transaction_types)),
                value_type="integer",
                unit="transaction_types",
                page=1,
                section="Coinbase transactions distinct transaction types",
                snippet_text=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=", ".join(transaction_types),
            ),
        ]
    )

    return DocumentFacts(
        relative_path.as_posix(),
        "coinbase_transactions_csv",
        "deterministic.coinbase_transactions_csv.v1",
        "ok",
        facts,
        warnings,
    )
