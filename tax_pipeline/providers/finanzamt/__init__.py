from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.finanzamt.prepayment_pdf import extract_finanzamt_prepayment_pdf
from tax_pipeline.providers.finanzamt.steuerbescheid_pdf import extract_finanzamt_steuerbescheid_pdf
from tax_pipeline.providers.finanzamt.verlustvortrag_pdf import extract_finanzamt_verlustvortrag_pdf
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "finanzamt",
        "steuerbescheid",
        "pdf",
        CallableDocumentHandler(extract_finanzamt_steuerbescheid_pdf),
    )
    registry.register(
        "finanzamt",
        "verlustvortrag",
        "pdf",
        CallableDocumentHandler(extract_finanzamt_verlustvortrag_pdf),
    )
    registry.register(
        "finanzamt",
        "prepayment",
        "pdf",
        CallableDocumentHandler(extract_finanzamt_prepayment_pdf),
    )
