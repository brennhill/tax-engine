from __future__ import annotations

import re
from pathlib import Path


def _normalize_parts(path: Path) -> list[str]:
    return [part.lower() for part in path.parts]


def _guess_owner(path: Path) -> str | None:
    lowered = path.as_posix().lower()
    if any(marker in lowered for marker in ("person_1", "person-1", "person 1", "taxpayer")):
        return "person_1"
    if any(marker in lowered for marker in ("person_2", "person-2", "person 2", "spouse", "partner")):
        return "person_2"
    return None


def _extract_year(name: str) -> int | None:
    match = re.search(r"(20\d{2})", name)
    return int(match.group(1)) if match else None


def _format_for_name(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".eml":
        return "eml"
    if suffix in {".png", ".jpg", ".jpeg"}:
        return "image"
    return "unknown"


def format_for_path(path: Path) -> str:
    return _format_for_name(path.name)


def _provider_fields(doc_type: str) -> tuple[str | None, str | None, str | None]:
    mapping = {
        "schwab_1099_pdf": ("schwab", "1099_composite", "US"),
        "schwab_1099_csv": ("schwab", "1099", "US"),
        "schwab_transactions_csv": ("schwab", "transactions", "US"),
        "schwab_limitation_image": ("schwab", "limitation_notice", "US"),
        "coinbase_transactions_csv": ("coinbase", "transactions", "US"),
        "coinbase_1099_da_pdf": ("coinbase", "1099_da", "US"),
        "jpm_1099_pdf": ("jpm", "1099_b", "US"),
        "shareworks_statement_pdf": ("shareworks", "statement", "US"),
        "german_lohnsteuer_pdf": ("datev", "lohnsteuerbescheinigung", "DE"),
        "german_verlustvortrag_pdf": ("finanzamt", "verlustvortrag", "DE"),
        "german_steuerbescheid_pdf": ("finanzamt", "steuerbescheid", "DE"),
        "german_prepayment_pdf": ("finanzamt", "prepayment", "DE"),
        "german_capital_certificate_pdf": ("germany_bank", "capital_certificate", "DE"),
        "n26_transfer_confirmation_pdf": ("n26", "transfer_confirmation", "DE"),
        "german_social_insurance_notice_pdf": ("germany_payroll", "social_insurance_notice", "DE"),
        "us_1040_packet_pdf": ("tax_preparer", "1040_packet", "US"),
        "us_8879_pdf": ("tax_preparer", "8879", "US"),
        "expense_invoice": ("merchant", "invoice", None),
        "donation_receipt_eml": ("donation_platform", "donation_receipt", None),
        "unknown": (None, None, None),
    }
    return mapping.get(doc_type, (None, None, None))


def provider_fields_for_doc_type(doc_type: str) -> tuple[str | None, str | None, str | None]:
    return _provider_fields(doc_type)


def _bucket_for_parts(parts: list[str]) -> str:
    """Return the logical bucket for a manifest-relative path.

    The pre-Proposal-8 layout was flat (``germany/...``, ``us/...``,
    ``brokers/...`` etc.) so ``parts[0]`` was the bucket. The new
    layout splits jurisdiction documents under
    ``jurisdictions/<iso>/...`` and asset documents under
    ``asset_classes/<class>/...``. Translate both back to the legacy
    bucket label so downstream classification (the
    ``bucket == "receipts"`` heuristic, the ``UnsupportedFact`` ledger,
    etc.) keeps working unchanged on either layout.
    """

    if not parts:
        return "raw"
    head = parts[0]
    if head == "jurisdictions" and len(parts) >= 2:
        iso = parts[1]
        # Normalise back to the historical flat name so existing
        # consumers that compare bucket == "germany" / "us" stay valid.
        legacy = {"de": "germany", "us": "us"}.get(iso, iso)
        return legacy
    if head == "asset_classes" and len(parts) >= 2:
        return parts[1]
    return head


def classify_relative_path(relative_path: Path) -> dict[str, object]:
    rel = relative_path.as_posix()
    name = relative_path.name
    lowered_name = name.lower()
    parts = _normalize_parts(relative_path)
    bucket = _bucket_for_parts(parts)

    doc_type = "unknown"
    confidence = "low"

    if "1099 composite" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "schwab_1099_pdf"
        confidence = "high"
    elif re.search(r"1099-\d{4}.*\.csv$", lowered_name):
        doc_type = "schwab_1099_csv"
        confidence = "high"
    elif "individual_" in lowered_name and "transactions" in lowered_name and lowered_name.endswith(".csv"):
        doc_type = "schwab_transactions_csv"
        confidence = "high"
    elif lowered_name.startswith("coinbase-transactions-") and lowered_name.endswith(".csv"):
        doc_type = "coinbase_transactions_csv"
        confidence = "high"
    elif "1099-da" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "coinbase_1099_da_pdf"
        confidence = "high"
    elif lowered_name == "jpm-1099statement.pdf":
        doc_type = "jpm_1099_pdf"
        confidence = "high"
    elif "shareworks" in rel.lower() and lowered_name.endswith(".pdf"):
        doc_type = "shareworks_statement_pdf"
        confidence = "medium"
    elif ("lohnsteuer" in lowered_name or "wage tax deduction" in lowered_name) and lowered_name.endswith(".pdf"):
        doc_type = "german_lohnsteuer_pdf"
        confidence = "high"
    elif "verlustvortrag" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "german_verlustvortrag_pdf"
        confidence = "high"
    elif "est-bescheid" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "german_steuerbescheid_pdf"
        confidence = "high"
    elif "prepay" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "german_prepayment_pdf"
        confidence = "medium"
    elif "capital-annual_income_statement" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "german_capital_certificate_pdf"
        confidence = "medium"
    elif lowered_name.startswith("1040-") and lowered_name.endswith(".pdf"):
        doc_type = "us_1040_packet_pdf"
        confidence = "high"
    elif lowered_name.startswith("8879-") and lowered_name.endswith(".pdf"):
        doc_type = "us_8879_pdf"
        confidence = "high"
    elif "additional-" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "n26_transfer_confirmation_pdf"
        confidence = "medium"
    elif "social" in lowered_name and lowered_name.endswith(".pdf"):
        doc_type = "german_social_insurance_notice_pdf"
        confidence = "medium"
    elif "schwab-limitations" in lowered_name and _format_for_name(name) == "image":
        doc_type = "schwab_limitation_image"
        confidence = "high"
    elif lowered_name.endswith(".eml"):
        doc_type = "donation_receipt_eml"
        confidence = "medium"
    elif bucket == "receipts" or "invoice" in lowered_name or "order details" in lowered_name:
        doc_type = "expense_invoice"
        confidence = "medium"

    provider, document_family, country_of_origin = _provider_fields(doc_type)

    return {
        "relative_path": rel,
        "bucket": bucket,
        "doc_type": doc_type,
        "provider": provider,
        "document_family": document_family,
        "format": format_for_path(relative_path),
        "tax_year": _extract_year(name),
        "owner": _guess_owner(relative_path),
        "country_of_origin": country_of_origin,
        "confidence": confidence,
    }
