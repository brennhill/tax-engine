from __future__ import annotations

import email
import html
import re
from pathlib import Path

from tax_pipeline.providers.shared.amounts import fmt_money, parse_us_amount
from tax_pipeline.providers.shared.provenance import fact
from tax_pipeline.providers.shared.schema import DocumentFacts, FactRecord


def _body_text(raw_message: str) -> tuple[str, str, str]:
    msg = email.message_from_string(raw_message)
    subject = msg.get("Subject", "")
    sender = msg.get("From", "")
    payload = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() in {"text/plain", "text/html"}:
                chunk = part.get_payload(decode=True)
                if chunk is not None:
                    payload = chunk.decode(part.get_content_charset() or "utf-8", errors="replace")
                    if payload:
                        break
    else:
        raw_payload = msg.get_payload(decode=True)
        if raw_payload is not None:
            payload = raw_payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        else:
            payload = msg.get_payload() or ""
    return subject, sender, payload


def _extract_field(body: str, label: str) -> str | None:
    match = re.search(rf"{re.escape(label)}:\s*(?:<b>)?([^<\n]+)", body, re.IGNORECASE)
    return html.unescape(match.group(1).strip()) if match else None


def extract_donation_receipt_eml(relative_path: Path, pages: list[str]) -> DocumentFacts:
    raw_message = pages[0] if pages else ""
    subject, sender, body = _body_text(raw_message)
    facts: list[FactRecord] = []
    warnings: list[str] = []

    if subject:
        facts.append(
            fact(
                key="email_subject",
                value=subject,
                value_type="text",
                unit="",
                page=1,
                section="Email subject",
                snippet_text=subject,
                relative_path=relative_path.as_posix(),
            )
        )
    if sender:
        facts.append(
            fact(
                key="email_sender",
                value=sender,
                value_type="text",
                unit="",
                page=1,
                section="Email sender",
                snippet_text=sender,
                relative_path=relative_path.as_posix(),
            )
        )

    field_map = [
        ("organization_name", "Organization", "text", ""),
        ("campaign_name", "Campaign", "text", ""),
        ("donor_name", "Donor Name", "text", ""),
        ("receipt_number", "Receipt #", "text", ""),
        ("donated_at", "Donated At", "text", ""),
        ("payment_method", "Payment Method", "text", ""),
        ("donation_interval", "Donation Interval", "text", ""),
    ]
    for key, label, value_type, unit in field_map:
        value = _extract_field(body, label)
        if value is None:
            continue
        facts.append(
            fact(
                key=key,
                value=value,
                value_type=value_type,
                unit=unit,
                page=1,
                section=f"Donation receipt {label}",
                snippet_text=f"{label}: {value}",
                relative_path=relative_path.as_posix(),
            )
        )

    amount = _extract_field(body, "Amount")
    if amount is not None:
        facts.append(
            fact(
                key="donation_amount_usd",
                value=fmt_money(parse_us_amount(amount)),
                value_type="decimal",
                unit="USD",
                page=1,
                section="Donation receipt Amount",
                snippet_text=f"Amount: {amount}",
                relative_path=relative_path.as_posix(),
            )
        )

    status = "ok" if facts else "no_facts_extracted"
    return DocumentFacts(
        relative_path.as_posix(),
        "donation_receipt_eml",
        "deterministic.donation_receipt_eml.v1",
        status,
        facts,
        warnings,
    )
