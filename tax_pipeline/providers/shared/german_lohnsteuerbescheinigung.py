from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_german_compact_cents
from tax_pipeline.providers.shared.provenance import fact, find_first_match
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def _find_numbered_line_block(pages: list[str], line_no: int) -> tuple[int, str] | None:
    line_pattern = re.compile(rf"(?:^|\s){line_no}\.\s")
    next_line_pattern = re.compile(r"(?:^|\s)[0-9]{1,2}(?:a)?\.\s")
    for page_number, page_text in enumerate(pages, start=1):
        lines = page_text.splitlines()
        for index, line in enumerate(lines):
            if not line_pattern.search(line):
                continue
            block_lines = [line]
            next_index = index + 1
            while next_index < len(lines) and not next_line_pattern.search(lines[next_index]):
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


def extract_german_lohnsteuerbescheinigung(relative_path: Path, pages: list[str]) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []
    zero_if_blank_lines = {5, 10}

    def capture_line_block(line_no: int, section: str) -> tuple[int, str] | None:
        found = _find_numbered_line_block(pages, line_no)
        if found is None:
            warnings.append(f"Missing pattern for {section}")
        return found

    period_match_found = find_first_match(
        pages,
        r"1\.\s+(?:Period of certification|Bescheinigungszeitraum).*?([0-9]{2}\.[0-9]{2}\.-[0-9]{2}\.[0-9]{2}\.)",
    )
    if period_match_found:
        page, match = period_match_found
        facts.append(
            fact(
                key="period_certification",
                value=match.group(1),
                value_type="text",
                unit="",
                page=page,
                section="Lohnsteuerbescheinigung line 1",
                snippet_text=match.group(0),
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
            if line_no in zero_if_blank_lines:
                facts.append(
                    fact(
                        key=key,
                        value="0.00",
                        value_type="decimal",
                        unit="EUR",
                        page=page,
                        section=section,
                        snippet_text=block_text,
                        relative_path=relative_path.as_posix(),
                        notes="Blank amount interpreted as zero",
                    )
                )
                continue
            warnings.append(f"Missing amount in {section}")
            continue
        facts.append(
            fact(
                key=key,
                value=fmt_money(parse_german_compact_cents(amount_raw)),
                value_type="decimal",
                unit="EUR",
                page=page,
                section=section,
                snippet_text=block_text,
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "german_lohnsteuer_pdf",
        "deterministic.german_lohnsteuer_pdf.v1",
        status,
        facts,
        warnings,
    )
