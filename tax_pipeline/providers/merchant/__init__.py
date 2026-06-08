from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.merchant.invoice_pdf import extract_merchant_invoice_pdf
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "merchant",
        "invoice",
        "pdf",
        CallableDocumentHandler(extract_merchant_invoice_pdf),
    )
