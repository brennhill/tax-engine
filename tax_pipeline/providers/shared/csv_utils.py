from __future__ import annotations

import csv
import io


def csv_dict_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    rows = [row for row in rows if any(value for value in row.values())]
    return fieldnames, rows
