from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path
from typing import Callable

from tax_pipeline.classify import classify_relative_path, format_for_path, provider_fields_for_doc_type
from tax_pipeline.fact_validation import validate_all_facts
from tax_pipeline.year_runtime import load_manifest
from tax_pipeline.paths import YearPaths, has_legacy_raw_layout
from tax_pipeline.providers import coinbase as coinbase_provider
from tax_pipeline.providers import datev as datev_provider
from tax_pipeline.providers import donation_platform as donation_platform_provider
from tax_pipeline.providers import finanzamt as finanzamt_provider
from tax_pipeline.providers import germany_bank as germany_bank_provider
from tax_pipeline.providers import germany_payroll as germany_payroll_provider
from tax_pipeline.providers import jpm as jpm_provider
from tax_pipeline.providers import merchant as merchant_provider
from tax_pipeline.providers import n26 as n26_provider
from tax_pipeline.providers import shareworks as shareworks_provider
from tax_pipeline.providers import schwab as schwab_provider
from tax_pipeline.providers import tax_preparer as tax_preparer_provider
from tax_pipeline.providers.base import CallableDocumentHandler, UnsupportedDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.shared.document import DocumentDescriptor
from tax_pipeline.providers.shared.document import descriptor_from_classification
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord
from tax_pipeline.providers.shared.text_pdf import load_pdf_pages


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _fmt_money(value: Decimal) -> str:
    return format(_q2(value), "f")


def _fmt_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return format(value.quantize(Decimal("1")), "f")
    return _fmt_money(value)


def _parse_us_amount(raw: str) -> Decimal:
    cleaned = raw.replace(",", "").replace("$", "").replace(" ", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    return Decimal(cleaned)


def _parse_german_standard_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def _parse_german_decimal_comma_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(".", "").replace(",", ".").replace("€", "")
    return Decimal(cleaned)


def _parse_german_compact_cents(raw: str) -> Decimal:
    digits = re.sub(r"\D", "", raw)
    return Decimal(digits) / Decimal("100")


def _safe_slug(relative_path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", relative_path).strip("_")


def _load_image_text(path: Path) -> str:
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "--psm", "6"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _manual_override_path(paths: YearPaths, relative_path: str) -> Path:
    return paths.manual_facts_root / f"{_safe_slug(relative_path)}.json"


def _load_manual_override(
    paths: YearPaths,
    descriptor: DocumentDescriptor,
    relative_path: str,
    doc_type: str,
) -> DocumentFacts | None:
    override_path = _manual_override_path(paths, relative_path)
    if not override_path.exists():
        return None
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    doc = DocumentFacts(
        relative_path=relative_path,
        doc_type=str(payload.get("doc_type") or doc_type),
        parser=str(payload.get("parser") or "manual.reviewed.v1"),
        status=str(payload.get("status") or "ok"),
        facts=[FactRecord(**fact) for fact in payload.get("facts", [])],
        warnings=[str(warning) for warning in payload.get("warnings", [])],
    )
    return _annotate_document(doc, descriptor)


def _snippet(page_text: str, start: int, end: int, radius: int = 120) -> str:
    snippet = page_text[max(0, start - radius) : min(len(page_text), end + radius)].strip()
    return "\n".join(line.rstrip() for line in snippet.splitlines() if line.strip())


def _find_first_match(
    pages: list[str], pattern: str, flags: int = re.MULTILINE | re.DOTALL
) -> tuple[int, re.Match[str]] | None:
    regex = re.compile(pattern, flags)
    for index, page_text in enumerate(pages, start=1):
        match = regex.search(page_text)
        if match:
            return index, match
    return None


def _normalize_date(raw: str) -> str:
    return re.sub(r"\s+", "", raw)


def _iso_us_date(raw: str) -> str:
    return datetime.strptime(raw, "%m/%d/%Y").date().isoformat()


def _primary_us_date(raw: str) -> str:
    match = re.search(r"([0-9]{2}/[0-9]{2}/[0-9]{4})", raw)
    if not match:
        raise ValueError(f"No MM/DD/YYYY date found in {raw!r}")
    return match.group(1)


def _find_numbered_line_block(pages: list[str], line_no: int) -> tuple[int, str] | None:
    line_pattern = re.compile(rf"^\s*{line_no}\.\s")
    next_line_pattern = re.compile(r"^\s*[0-9]{1,2}(?:a)?\.\s")
    for page_number, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        for index, line in enumerate(lines):
            if not line_pattern.match(line):
                continue
            block_lines = [line]
            next_index = index + 1
            while next_index < len(lines) and not next_line_pattern.match(lines[next_index]):
                block_lines.append(lines[next_index])
                next_index += 1
            return page_number, "\n".join(block_lines)
    return None


def _extract_last_compact_amount(block: str) -> str | None:
    for line in reversed(block.splitlines()):
        if not line.strip():
            continue
        match = re.search(r"([0-9][0-9\.]*)\s*$", line)
        if not match:
            continue
        digits = re.sub(r"\D", "", match.group(1))
        if len(digits) < 4:
            continue
        prefix = line[: match.start(1)]
        if not prefix.strip() or re.search(r"\s{5,}$", prefix):
            return match.group(1)
    return None


def _fact(
    *,
    key: str,
    value: str,
    value_type: str,
    unit: str,
    page: int,
    section: str,
    snippet: str,
    relative_path: str,
    confidence: str = "high",
    notes: str = "",
) -> FactRecord:
    return FactRecord(
        key=key,
        value=value,
        value_type=value_type,
        unit=unit,
        confidence=confidence,
        source={
            "file": relative_path,
            "page": page,
            "section": section,
            "snippet": snippet,
        },
        notes=notes,
    )


def _csv_dict_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
    rows = [row for row in rows if any(value for value in row.values())]
    return fieldnames, rows


def _extract_lohnsteuer(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    def capture_line_block(line_no: int, section: str) -> tuple[int, str] | None:
        found = _find_numbered_line_block(pages, line_no)
        if found is None:
            warnings.append(f"Missing pattern for {section}")
        return found

    period_match_found = _find_first_match(
        pages,
        r"1\.\s+(?:Period of certification|Bescheinigungszeitraum).*?([0-9]{2}\.[0-9]{2}\.-[0-9]{2}\.[0-9]{2}\.)",
    )
    if period_match_found:
        page, match = period_match_found
        facts.append(
            _fact(
                key="period_certification",
                value=match.group(1),
                value_type="text",
                unit="",
                page=page,
                section="Lohnsteuerbescheinigung line 1",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for period")

    amount_specs = [
        ("gross_wage_eur", 3, "Lohnsteuerbescheinigung line 3"),
        ("withheld_wage_tax_eur", 4, "Lohnsteuerbescheinigung line 4"),
        ("withheld_solidarity_surcharge_eur", 5, "Lohnsteuerbescheinigung line 5"),
        ("multiannual_wage_eur", 10, "Lohnsteuerbescheinigung line 10"),
        ("employer_pension_contribution_eur", 22, "Lohnsteuerbescheinigung line 22"),
        ("employee_pension_contribution_eur", 23, "Lohnsteuerbescheinigung line 23"),
        ("employee_health_insurance_eur", 25, "Lohnsteuerbescheinigung line 25"),
        ("employee_nursing_care_insurance_eur", 26, "Lohnsteuerbescheinigung line 26"),
        ("employee_unemployment_insurance_eur", 27, "Lohnsteuerbescheinigung line 27"),
    ]
    for key, line_no, section in amount_specs:
        found = capture_line_block(line_no, section)
        if not found:
            continue
        page, block_text = found
        amount_raw = _extract_last_compact_amount(block_text)
        if amount_raw is None:
            warnings.append(f"Missing amount in {section}")
            continue
        facts.append(
            _fact(
                key=key,
                value=_fmt_money(_parse_german_compact_cents(amount_raw)),
                value_type="decimal",
                unit="EUR",
                page=page,
                section=section,
                snippet=block_text,
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "german_lohnsteuer_pdf", "deterministic.german_lohnsteuer_pdf.v1", status, facts, warnings)


def _extract_verlustvortrag(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    as_of = _find_first_match(pages, r"auf\s+den\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})")
    if as_of:
        page, match = as_of
        facts.append(
            _fact(
                key="loss_carryforward_as_of",
                value=match.group(1),
                value_type="date",
                unit="",
                page=page,
                section="Bescheid heading",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    specs = [
        (
            "loss_carryforward_stock_sales_eur",
            r"Kapitalvermögen \(Veräußerung von Aktien\) auf\s+([0-9\.]+)",
            "§ 10d carryforward stock sales",
        ),
        (
            "loss_carryforward_private_sales_eur",
            r"privaten Veräußerungsgeschäften auf\s+([0-9\.]+)",
            "§ 23 carryforward private sales",
        ),
    ]
    for key, pattern, section in specs:
        found = _find_first_match(pages, pattern)
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        facts.append(
            _fact(
                key=key,
                value=_fmt_decimal(_parse_german_standard_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section=section,
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "german_verlustvortrag_pdf", "deterministic.german_verlustvortrag_pdf.v1", status, facts, warnings)


def _extract_steuerbescheid(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    date_match = _find_first_match(pages, r"([0-9]{2}\.[0-9]{2}\.[0-9]{4})")
    if date_match:
        page, match = date_match
        facts.append(
            _fact(
                key="assessment_date",
                value=_normalize_date(match.group(1)),
                value_type="date",
                unit="",
                page=page,
                section="Steuerbescheid heading date",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    dual_specs = [
        (
            "Festgesetzt werden",
            "assessed_income_tax_eur",
            "assessed_solidarity_surcharge_eur",
            "Steuerbescheid assessed tax",
        ),
        (
            "ab Steuerabzug vom Lohn",
            "withheld_income_tax_credit_eur",
            "withheld_solidarity_credit_eur",
            "Steuerbescheid wage tax credits",
        ),
        (
            "verbleibende Steuer",
            "residual_income_tax_eur",
            "residual_solidarity_surcharge_eur",
            "Steuerbescheid residual tax",
        ),
    ]
    for label, left_key, right_key, section in dual_specs:
        found = _find_first_match(pages, rf"{re.escape(label)}\s+([0-9\.\,]+)\s+([0-9\.\,]+)")
        if not found:
            warnings.append(f"Missing pattern for {section}")
            continue
        page, match = found
        shared_snippet = _snippet(pages[page - 1], match.start(), match.end())
        left_value, right_value = match.groups()
        facts.extend(
            [
                _fact(
                    key=left_key,
                    value=_fmt_money(_parse_german_decimal_comma_amount(left_value)),
                    value_type="decimal",
                    unit="EUR",
                    page=page,
                    section=f"{section} income tax",
                    snippet=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
                _fact(
                    key=right_key,
                    value=_fmt_money(_parse_german_decimal_comma_amount(right_value)),
                    value_type="decimal",
                    unit="EUR",
                    page=page,
                    section=f"{section} solidarity surcharge",
                    snippet=shared_snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )

    due_date = _find_first_match(pages, r"spätestens am\s+([0-9]{2}\s*\.[0-9]{2}\.[0-9]{4})")
    if due_date:
        page, match = due_date
        facts.append(
            _fact(
                key="payment_due_date",
                value=_normalize_date(match.group(1)),
                value_type="date",
                unit="",
                page=page,
                section="Steuerbescheid payment due date",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Steuerbescheid payment due date")

    amount_due = _find_first_match(pages, r"Den Gesamtbetrag von\s+([0-9\.\,]+)\s+€")
    if amount_due:
        page, match = amount_due
        facts.append(
            _fact(
                key="amount_due_total_eur",
                value=_fmt_money(_parse_german_decimal_comma_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section="Steuerbescheid total amount due",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for Steuerbescheid total amount due")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_steuerbescheid_pdf",
        "deterministic.german_steuerbescheid_pdf.v1",
        status,
        facts,
        warnings,
    )


def _extract_german_prepayment(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    amount = _find_first_match(pages, r"Instant bank transfer\s+([0-9\.\,]+)\s+EUR")
    if amount:
        page, match = amount
        facts.append(
            _fact(
                key="payment_amount_eur",
                value=_fmt_money(_parse_german_decimal_comma_amount(match.group(1))),
                value_type="decimal",
                unit="EUR",
                page=page,
                section="Transfer amount",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for transfer amount")

    value_booking = _find_first_match(
        pages,
        r"Value Date\s+Booking Date\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})\s+([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
    )
    if value_booking:
        page, match = value_booking
        snippet = _snippet(pages[page - 1], match.start(), match.end())
        facts.extend(
            [
                _fact(
                    key="value_date",
                    value=match.group(1),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Transfer value date",
                    snippet=snippet,
                    relative_path=relative_path.as_posix(),
                ),
                _fact(
                    key="booking_date",
                    value=match.group(2),
                    value_type="date",
                    unit="",
                    page=page,
                    section="Transfer booking date",
                    snippet=snippet,
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )
    else:
        warnings.append("Missing pattern for transfer dates")

    reference = _find_first_match(pages, r"Reference text\s+([^\n]+)")
    if reference:
        page, match = reference
        facts.append(
            _fact(
                key="reference_text",
                value=match.group(1).strip(),
                value_type="text",
                unit="",
                page=page,
                section="Transfer reference text",
                snippet=_snippet(pages[page - 1], match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing pattern for transfer reference text")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_prepayment_pdf",
        "deterministic.german_prepayment_pdf.v1",
        status,
        facts,
        warnings,
    )


def _extract_schwab_transactions_csv(relative_path: Path, pages: list[str]) -> DocumentFacts:
    text = pages[0]
    facts: list[FactRecord] = []
    warnings: list[str] = []
    fieldnames, rows = _csv_dict_rows(text)
    if not rows:
        return DocumentFacts(
            relative_path.as_posix(),
            "schwab_transactions_csv",
            "deterministic.schwab_transactions_csv.v1",
            "no_facts_extracted",
            [],
            ["No transaction rows found"],
        )

    dates = [_primary_us_date(row["Date"]) for row in rows if row.get("Date")]
    actions = sorted({row["Action"] for row in rows if row.get("Action")})
    min_date = min(dates, key=lambda value: datetime.strptime(value, "%m/%d/%Y"))
    max_date = max(dates, key=lambda value: datetime.strptime(value, "%m/%d/%Y"))
    summary_snippet = "\n".join(text.splitlines()[:5])
    first_date_row = next(row for row in rows if _primary_us_date(row.get("Date", "")) == min_date)
    last_date_row = next(row for row in rows if _primary_us_date(row.get("Date", "")) == max_date)

    facts.extend(
        [
            _fact(
                key="transaction_row_count",
                value=str(len(rows)),
                value_type="integer",
                unit="rows",
                page=1,
                section="Schwab transactions CSV summary",
                snippet=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=f"Columns: {', '.join(fieldnames)}",
            ),
            _fact(
                key="first_transaction_date",
                value=_iso_us_date(min_date),
                value_type="date",
                unit="",
                page=1,
                section="Schwab transactions CSV earliest date",
                snippet=",".join(first_date_row.get(name, "") for name in fieldnames),
                relative_path=relative_path.as_posix(),
            ),
            _fact(
                key="last_transaction_date",
                value=_iso_us_date(max_date),
                value_type="date",
                unit="",
                page=1,
                section="Schwab transactions CSV latest date",
                snippet=",".join(last_date_row.get(name, "") for name in fieldnames),
                relative_path=relative_path.as_posix(),
            ),
            _fact(
                key="distinct_action_count",
                value=str(len(actions)),
                value_type="integer",
                unit="actions",
                page=1,
                section="Schwab transactions CSV distinct actions",
                snippet=summary_snippet,
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


def _extract_coinbase_transactions_csv(relative_path: Path, pages: list[str]) -> DocumentFacts:
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
            _fact(
                key="user_name",
                value=user_row[1].strip(),
                value_type="text",
                unit="",
                page=1,
                section="Coinbase transactions user row",
                snippet=",".join(user_row),
                relative_path=relative_path.as_posix(),
            )
        )
    else:
        warnings.append("Missing Coinbase user row")

    facts.extend(
        [
            _fact(
                key="transaction_row_count",
                value=str(len(data_rows)),
                value_type="integer",
                unit="rows",
                page=1,
                section="Coinbase transactions CSV summary",
                snippet=summary_snippet,
                relative_path=relative_path.as_posix(),
                notes=f"Columns: {', '.join(header)}",
            ),
            _fact(
                key="first_transaction_timestamp",
                value=min_timestamp,
                value_type="datetime",
                unit="UTC",
                page=1,
                section="Coinbase transactions earliest timestamp",
                snippet=next(",".join(row.get(col, "") for col in header) for row in data_rows if row.get("Timestamp", "").strip() == min_timestamp),
                relative_path=relative_path.as_posix(),
            ),
            _fact(
                key="last_transaction_timestamp",
                value=max_timestamp,
                value_type="datetime",
                unit="UTC",
                page=1,
                section="Coinbase transactions latest timestamp",
                snippet=next(",".join(row.get(col, "") for col in header) for row in data_rows if row.get("Timestamp", "").strip() == max_timestamp),
                relative_path=relative_path.as_posix(),
            ),
            _fact(
                key="distinct_transaction_type_count",
                value=str(len(transaction_types)),
                value_type="integer",
                unit="transaction_types",
                page=1,
                section="Coinbase transactions distinct transaction types",
                snippet=summary_snippet,
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


def _extract_coinbase_1099_da(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        (
            r"Coinbase\s+Short\s+\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("short_term_proceeds_usd", 1, "Coinbase 1099-DA summary short proceeds"),
                ("short_term_cost_basis_usd", 2, "Coinbase 1099-DA summary short cost basis"),
                ("short_term_gain_or_loss_usd", 3, "Coinbase 1099-DA summary short gain or loss"),
            ],
        ),
        (
            r"Coinbase\s+Long\s+\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("long_term_proceeds_usd", 1, "Coinbase 1099-DA summary long proceeds"),
                ("long_term_cost_basis_usd", 2, "Coinbase 1099-DA summary long cost basis"),
                ("long_term_gain_or_loss_usd", 3, "Coinbase 1099-DA summary long gain or loss"),
            ],
        ),
        (
            r"Total[^\n]*\$\s*([0-9,]+\.\d{2})\s+\$\s*([0-9,]+\.\d{2})\s+(-?\$\s*[0-9,]+\.\d{2})",
            [
                ("total_proceeds_usd", 1, "Coinbase 1099-DA summary total proceeds"),
                ("total_cost_basis_usd", 2, "Coinbase 1099-DA summary total cost basis"),
                ("total_gain_or_loss_usd", 3, "Coinbase 1099-DA summary total gain or loss"),
            ],
        ),
    ]
    for pattern, fields in specs:
        found = _find_first_match(pages, pattern)
        if not found:
            warnings.append(f"Missing pattern for {fields[0][2]}")
            continue
        page, match = found
        shared_snippet = _snippet(pages[page - 1], match.start(), match.end())
        for key, group_index, section in fields:
            facts.append(
                _fact(
                    key=key,
                    value=_fmt_money(_parse_us_amount(match.group(group_index))),
                    value_type="decimal",
                    unit="USD",
                    page=page,
                    section=section,
                    snippet=shared_snippet,
                    relative_path=relative_path.as_posix(),
                )
            )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "coinbase_1099_da_pdf",
        "deterministic.coinbase_1099_da_pdf.v1",
        status,
        facts,
        warnings,
    )


def _extract_schwab_1099(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    specs = [
        ("ordinary_dividends_box_1a_usd", 3, r"1a\s+Total Ordinary Dividends.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 1a"),
        ("qualified_dividends_box_1b_usd", 3, r"1b\s+Qualified Dividends.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 1b"),
        ("capital_gain_distributions_box_2a_usd", 3, r"2a\s+Total Capital Gain Distributions.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 2a"),
        ("nondividend_distributions_box_3_usd", 3, r"3\s+Nondividend Distributions.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 3"),
        ("foreign_tax_paid_box_7_usd", 3, r"7\s+Foreign Tax Paid.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-DIV box 7"),
        ("interest_income_box_1_usd", 5, r"1\s+Interest Income.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-INT box 1"),
        ("substitute_payments_box_8_usd", 7, r"8\s+Substitute Payments in Lieu of Dividends or Interest.*?\$\s*([0-9,]+\.\d{2})", "Form 1099-MISC box 8"),
        ("foreign_source_income_summary_usd", 90, r"Total Foreign Tax Paid and Income.*?\(?[0-9,]+\.\d{2}\)?\s*\$?\s*([0-9,]+\.\d{2})", "Foreign Tax Paid and Income Summary"),
    ]
    for key, page_number, pattern, section in specs:
        if len(pages) < page_number:
            warnings.append(f"Missing page {page_number} for {section}")
            continue
        page_text = pages[page_number - 1]
        match = re.search(pattern, page_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        facts.append(
            _fact(
                key=key,
                value=_fmt_money(_parse_us_amount(match.group(1))),
                value_type="decimal",
                unit="USD",
                page=page_number,
                section=section,
                snippet=_snippet(page_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "schwab_1099_pdf", "deterministic.schwab_1099_pdf.v1", status, facts, warnings)


def _extract_jpm_1099(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []
    if not pages:
        return DocumentFacts(relative_path.as_posix(), "jpm_1099_pdf", "deterministic.jpm_1099_pdf.v1", "no_text_extracted", [], ["No pages available"])

    page_text = pages[0]

    text_specs = [
        ("account_number", r"Tax Information for Account\s+([A-Z0-9\-]+)", "JPM 1099 heading", "text", ""),
        ("statement_date", r"Statement Date\s+([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", "JPM statement date", "date", ""),
    ]
    for key, pattern, section, value_type, unit in text_specs:
        match = re.search(pattern, page_text, re.MULTILINE | re.DOTALL)
        if not match:
            warnings.append(f"Missing pattern for {section}")
            continue
        facts.append(
            _fact(
                key=key,
                value=match.group(1),
                value_type=value_type,
                unit=unit,
                page=1,
                section=section,
                snippet=_snippet(page_text, match.start(), match.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    summary_row = re.search(
        r"Short\s+A \(basis reported to the IRS\).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2}).*?([0-9,]+\.\d{2})",
        page_text,
        re.MULTILINE | re.DOTALL,
    )
    if summary_row:
        shared_snippet = _snippet(page_text, summary_row.start(), summary_row.end())
        proceeds, basis, market_discount, wash_sale, net_gain = summary_row.groups()
        specs = [
            ("short_term_type_a_proceeds_usd", proceeds, "JPM 1099-B short-term proceeds"),
            ("short_term_type_a_cost_basis_usd", basis, "JPM 1099-B short-term cost basis"),
            ("short_term_type_a_market_discount_usd", market_discount, "JPM 1099-B short-term market discount"),
            ("short_term_type_a_wash_sale_loss_disallowed_usd", wash_sale, "JPM 1099-B short-term wash sale disallowed"),
            ("short_term_type_a_net_gain_usd", net_gain, "JPM 1099-B short-term net gain"),
        ]
        for key, raw_amount, section in specs:
            facts.append(
                _fact(
                    key=key,
                    value=_fmt_money(_parse_us_amount(raw_amount)),
                    value_type="decimal",
                    unit="USD",
                    page=1,
                    section=section,
                    snippet=shared_snippet,
                    relative_path=relative_path.as_posix(),
                )
            )
    else:
        base_start = re.search(r"Short\s+A \(basis reported to the IRS\)", page_text, re.MULTILINE | re.DOTALL)
        if base_start:
            section_text = page_text[base_start.start() :]
            label_specs = [
                ("short_term_type_a_proceeds_usd", r"Proceeds\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term proceeds"),
                ("short_term_type_a_cost_basis_usd", r"Cost basis\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term cost basis"),
                ("short_term_type_a_net_gain_usd", r"Net gain or loss\(-\)\s+([0-9,]+\.\d{2})", "JPM 1099-B short-term net gain"),
            ]
            for key, pattern, section in label_specs:
                match = re.search(pattern, section_text, re.MULTILINE | re.DOTALL)
                if not match:
                    warnings.append(f"Missing pattern for {section}")
                    continue
                facts.append(
                    _fact(
                        key=key,
                        value=_fmt_money(_parse_us_amount(match.group(1))),
                        value_type="decimal",
                        unit="USD",
                        page=1,
                        section=section,
                        snippet=_snippet(section_text, match.start(), match.end()),
                        relative_path=relative_path.as_posix(),
                    )
                )
        else:
            warnings.append("Missing short-term Type A summary row")

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "jpm_1099_pdf", "deterministic.jpm_1099_pdf.v1", status, facts, warnings)


FALLBACK_EXTRACTORS: dict[str, Callable[[Path, list[str]], DocumentFacts]] = {}


def _format_for_doc_type(doc_type: str) -> str:
    if doc_type.endswith("_pdf"):
        return "pdf"
    if doc_type.endswith("_csv"):
        return "csv"
    if doc_type.endswith("_eml"):
        return "eml"
    return "unknown"


def _descriptor_for(relative_path: Path, doc_type: str) -> DocumentDescriptor:
    meta = classify_relative_path(relative_path)
    if str(meta["doc_type"]) != doc_type:
        provider, document_family, country_of_origin = provider_fields_for_doc_type(doc_type)
        meta = {
            **meta,
            "doc_type": doc_type,
            "provider": provider,
            "document_family": document_family,
            "format": format_for_path(relative_path) if relative_path.suffix else _format_for_doc_type(doc_type),
            "country_of_origin": country_of_origin,
        }
    return descriptor_from_classification(meta)


def _build_default_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    schwab_provider.register_handlers(registry)
    coinbase_provider.register_handlers(registry)
    datev_provider.register_handlers(registry)
    jpm_provider.register_handlers(registry)
    finanzamt_provider.register_handlers(registry)
    shareworks_provider.register_handlers(registry)
    germany_bank_provider.register_handlers(registry)
    germany_payroll_provider.register_handlers(registry)
    merchant_provider.register_handlers(registry)
    n26_provider.register_handlers(registry)
    donation_platform_provider.register_handlers(registry)
    tax_preparer_provider.register_handlers(registry)
    for doc_type, extractor in FALLBACK_EXTRACTORS.items():
        provider, document_family, _country = provider_fields_for_doc_type(doc_type)
        if provider is None or document_family is None:
            continue
        registry.register(
            provider,
            document_family,
            _format_for_doc_type(doc_type),
            CallableDocumentHandler(extractor),
        )
    return registry


DEFAULT_PROVIDER_REGISTRY = _build_default_registry()


def _split_parser(parser: str) -> tuple[str, str | None]:
    if ".v" not in parser:
        return parser, None
    parser_name, parser_version = parser.rsplit(".v", 1)
    return parser_name, f"v{parser_version}"


def _annotate_document(doc: DocumentFacts, descriptor: DocumentDescriptor) -> DocumentFacts:
    parser_name, parser_version = _split_parser(doc.parser)
    return replace(
        doc,
        provider=descriptor.provider,
        document_family=descriptor.document_family,
        country_of_origin=descriptor.country_of_origin,
        owner=descriptor.owner,
        tax_year=descriptor.tax_year,
        parser_name=parser_name,
        parser_version=parser_version,
    )


def extract_document_facts_from_pages(
    relative_path: Path,
    doc_type: str,
    pages: list[str],
    *,
    descriptor: DocumentDescriptor | None = None,
    registry: ProviderRegistry | None = None,
) -> DocumentFacts:
    registry = registry or DEFAULT_PROVIDER_REGISTRY
    descriptor = descriptor or _descriptor_for(relative_path, doc_type)
    if descriptor.format in {"pdf", "image"} and not any(page.strip() for page in pages):
        return _annotate_document(
            DocumentFacts(
                relative_path.as_posix(),
                doc_type,
                f"deterministic.{doc_type}.v1",
                "needs_ocr",
                [],
                ["No extractable text found; OCR or manual review required"],
            ),
            descriptor,
        )
    handler = registry.resolve(descriptor)
    if isinstance(handler, UnsupportedDocumentHandler):
        return _annotate_document(handler.extract(relative_path, pages, descriptor), descriptor)
    return _annotate_document(handler.extract(relative_path, pages, descriptor), descriptor)


def write_document_facts(paths: YearPaths, doc: DocumentFacts) -> tuple[Path, Path]:
    slug = _safe_slug(doc.relative_path)
    json_path = paths.facts_root / f"{slug}.facts.json"
    md_path = paths.facts_root / f"{slug}.facts.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(doc.to_dict(), indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Facts For {doc.relative_path}",
        "",
        f"- doc type: `{doc.doc_type}`",
        f"- parser: `{doc.parser}`",
        f"- provider: `{doc.provider}`",
        f"- document family: `{doc.document_family}`",
        f"- country of origin: `{doc.country_of_origin}`",
        f"- owner: `{doc.owner}`",
        f"- tax year: `{doc.tax_year}`",
        f"- status: `{doc.status}`",
        f"- facts: `{len(doc.facts)}`",
    ]
    if doc.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in doc.warnings)
    if doc.facts:
        lines.extend(["", "## Facts"])
        for fact in doc.facts:
            lines.extend(
                [
                    f"### {fact.key}",
                    f"- value: `{fact.value}` {fact.unit}".rstrip(),
                    f"- type: `{fact.value_type}`",
                    f"- confidence: `{fact.confidence}`",
                    f"- source file: `{fact.source['file']}`",
                    f"- source page: `{fact.source['page']}`",
                    f"- source section: `{fact.source['section']}`",
                    "- source snippet:",
                    "```text",
                    str(fact.source["snippet"]),
                    "```",
                ]
            )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def extract_all_facts(paths: YearPaths) -> list[dict[str, object]]:
    paths.ensure_directories()
    # Proposal 8: nudge un-migrated workspaces toward the new layout.
    # The runtime keeps reading legacy buckets (the manifest walker
    # globs the entire ``raw_root`` tree, and ``classify_relative_path``
    # normalises both layouts), so this is informational only.
    if has_legacy_raw_layout(paths.raw_root):
        print(
            "[paths] note: raw/ is on the legacy flat layout (germany/, us/, "
            "brokers/, ...). Run `tax-pipeline-migrate-buckets <workspace> "
            "--apply` to migrate to raw/jurisdictions/<iso>/ + "
            "raw/asset_classes/<class>/."
        )
    index_rows: list[dict[str, object]] = []
    review_lines = [
        f"# Facts Review - {paths.year}",
        "",
        "Each facts file is deterministic-first and links every extracted fact back to a source file, page, section, and snippet.",
        "",
        "| Document | Type | Status | Facts | JSON | Markdown |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]
    for entry in load_manifest(paths):
        relative_path = str(entry["relative_path"])
        raw_path = paths.raw_root / relative_path
        doc_type = str(entry["doc_type"])
        descriptor = descriptor_from_classification(entry)

        manual_doc = _load_manual_override(paths, descriptor, relative_path, doc_type)
        if manual_doc is not None:
            doc = manual_doc
        elif raw_path.suffix.lower() == ".pdf":
            try:
                pages = load_pdf_pages(raw_path)
            except Exception as exc:
                doc = _annotate_document(
                    DocumentFacts(relative_path, doc_type, "deterministic.pdf_text.v1", "text_extraction_failed", [], [str(exc)]),
                    descriptor,
                )
            else:
                doc = extract_document_facts_from_pages(
                    Path(relative_path),
                    doc_type,
                    pages,
                    descriptor=descriptor,
                )
        elif raw_path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
            try:
                text = _load_image_text(raw_path)
            except Exception as exc:
                doc = _annotate_document(
                    DocumentFacts(relative_path, doc_type, "deterministic.image_ocr.v1", "text_extraction_failed", [], [str(exc)]),
                    descriptor,
                )
            else:
                doc = extract_document_facts_from_pages(
                    Path(relative_path),
                    doc_type,
                    [text],
                    descriptor=descriptor,
                )
        elif raw_path.suffix.lower() in {".csv", ".eml", ".txt"}:
            text = raw_path.read_text(encoding="utf-8-sig", errors="replace")
            doc = extract_document_facts_from_pages(
                Path(relative_path),
                doc_type,
                [text],
                descriptor=descriptor,
            )
        else:
            doc = extract_document_facts_from_pages(
                Path(relative_path),
                doc_type,
                [],
                descriptor=descriptor,
            )
        json_path, md_path = write_document_facts(paths, doc)
        index_entry = {
            "relative_path": relative_path,
            "doc_type": doc_type,
            "status": doc.status,
            "facts_count": len(doc.facts),
            "json_path": json_path.relative_to(paths.year_root).as_posix(),
            "markdown_path": md_path.relative_to(paths.year_root).as_posix(),
        }
        index_rows.append(index_entry)
        review_lines.append(
            f"| `{relative_path}` | `{doc_type}` | `{doc.status}` | {len(doc.facts)} | `{index_entry['json_path']}` | `{index_entry['markdown_path']}` |"
        )

    (paths.facts_root / "index.json").write_text(json.dumps(index_rows, indent=2) + "\n", encoding="utf-8")
    (paths.facts_root / "REVIEW.md").write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    issues = validate_all_facts(paths, index_rows)
    error_issues = [issue for issue in issues if issue.severity == "error"]
    if error_issues:
        raise ValueError(
            "Fact validation failed; refusing to run tax-law calculations with invalid source facts. "
            f"See {paths.facts_root / 'VALIDATION.md'}."
        )
    return index_rows
