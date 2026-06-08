from __future__ import annotations

import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_localized_amount
from tax_pipeline.providers.shared.dates import iso_named_date
from tax_pipeline.providers.shared.provenance import fact, snippet
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_order_details(relative_path: Path, page_text: str) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    order = re.search(r"Order placed\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})\s+Order No\.\s+([0-9\-]+)", page_text)
    total = re.search(r"Grand Total:\s*€([0-9\.,]+)", page_text)
    seller = re.search(r"Sold by:\s*([^\n]+)", page_text)
    description = re.search(r"Grand Total:\s*€[0-9\.,]+\s+(.+?)\s+Sold by:", page_text, re.DOTALL)

    if order:
        facts.extend(
            [
                fact(
                    key="document_variant",
                    value="amazon_order_details",
                    value_type="text",
                    unit="",
                    page=1,
                    section="Amazon order details variant",
                    snippet_text="Order Summary",
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key="order_date",
                    value=iso_named_date(order.group(1)),
                    value_type="date",
                    unit="",
                    page=1,
                    section="Amazon order placed date",
                    snippet_text=order.group(0),
                    relative_path=relative_path.as_posix(),
                ),
                fact(
                    key="order_number",
                    value=order.group(2),
                    value_type="text",
                    unit="",
                    page=1,
                    section="Amazon order number",
                    snippet_text=order.group(0),
                    relative_path=relative_path.as_posix(),
                ),
            ]
        )
    if total:
        facts.append(
            fact(
                key="total_amount_eur",
                value=fmt_money(parse_localized_amount(total.group(1))),
                value_type="decimal",
                unit="EUR",
                page=1,
                section="Amazon order total",
                snippet_text=total.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if seller:
        facts.append(
            fact(
                key="seller_name",
                value=seller.group(1).strip(),
                value_type="text",
                unit="",
                page=1,
                section="Amazon seller",
                snippet_text=seller.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if description:
        facts.append(
            fact(
                key="item_description",
                value=_clean_text(description.group(1)),
                value_type="text",
                unit="",
                page=1,
                section="Amazon item description",
                snippet_text=snippet(page_text, description.start(), description.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "expense_invoice", "deterministic.expense_invoice_pdf.v1", status, facts, warnings)


def _extract_rechnung(relative_path: Path, page_text: str) -> DocumentFacts:
    facts: list[FactRecord] = []
    warnings: list[str] = []

    invoice_date = re.search(r"/Lieferdatum\s+([0-9]{1,2}\s+[A-Za-zäöüÄÖÜ]+\s+[0-9]{4})", page_text)
    invoice_number = re.search(r"Rechnungsnummer\s+([A-Z0-9\-]+)", page_text)
    total = re.search(r"Zahlbetrag\s+([0-9\.,]+)\s+€", page_text)
    seller = re.search(r"Verkauft von\s+([^\n]+)", page_text)
    order_number = re.search(r"Bestellnummer\s+([0-9\-]+)", page_text)
    description = re.search(r"Rechnungsdetails\s+(.+?)\s+ASIN:", page_text, re.DOTALL)

    facts.append(
        fact(
            key="document_variant",
            value="amazon_rechnung",
            value_type="text",
            unit="",
            page=1,
            section="Amazon invoice variant",
            snippet_text="Rechnung",
            relative_path=relative_path.as_posix(),
        )
    )
    if invoice_date:
        facts.append(
            fact(
                key="invoice_date",
                value=iso_named_date(invoice_date.group(1)),
                value_type="date",
                unit="",
                page=1,
                section="Amazon invoice date",
                snippet_text=invoice_date.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if invoice_number:
        facts.append(
            fact(
                key="invoice_number",
                value=invoice_number.group(1),
                value_type="text",
                unit="",
                page=1,
                section="Amazon invoice number",
                snippet_text=invoice_number.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if total:
        facts.append(
            fact(
                key="total_amount_eur",
                value=fmt_money(parse_localized_amount(total.group(1))),
                value_type="decimal",
                unit="EUR",
                page=1,
                section="Amazon invoice total",
                snippet_text=total.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if seller:
        facts.append(
            fact(
                key="seller_name",
                value=seller.group(1).strip(),
                value_type="text",
                unit="",
                page=1,
                section="Amazon seller",
                snippet_text=seller.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if order_number:
        facts.append(
            fact(
                key="order_number",
                value=order_number.group(1),
                value_type="text",
                unit="",
                page=1,
                section="Amazon order number",
                snippet_text=order_number.group(0),
                relative_path=relative_path.as_posix(),
            )
        )
    if description:
        facts.append(
            fact(
                key="item_description",
                value=_clean_text(description.group(1)),
                value_type="text",
                unit="",
                page=1,
                section="Amazon invoice item description",
                snippet_text=snippet(page_text, description.start(), description.end()),
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(relative_path.as_posix(), "expense_invoice", "deterministic.expense_invoice_pdf.v1", status, facts, warnings)


def extract_merchant_invoice_pdf(relative_path: Path, pages: list[str]) -> DocumentFacts:
    page_text = pages[0] if pages else ""
    if "Order placed" in page_text and "Order No." in page_text:
        return _extract_order_details(relative_path, page_text)
    if "Rechnungsnummer" in page_text and "Zahlbetrag" in page_text:
        return _extract_rechnung(relative_path, page_text)
    return DocumentFacts(
        relative_path.as_posix(),
        "expense_invoice",
        "deterministic.expense_invoice_pdf.v1",
        "no_facts_extracted",
        [],
        ["Unsupported invoice layout"],
    )
