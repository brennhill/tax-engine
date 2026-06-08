from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.n26.transfer_confirmation_pdf import extract_n26_transfer_confirmation_pdf
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "n26",
        "transfer_confirmation",
        "pdf",
        CallableDocumentHandler(extract_n26_transfer_confirmation_pdf),
    )
