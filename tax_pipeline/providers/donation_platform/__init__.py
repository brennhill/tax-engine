from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.donation_platform.donation_receipt_eml import extract_donation_receipt_eml
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "donation_platform",
        "donation_receipt",
        "eml",
        CallableDocumentHandler(extract_donation_receipt_eml),
    )
