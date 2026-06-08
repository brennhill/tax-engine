from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.tax_preparer.packet_1040_pdf import extract_tax_preparer_1040_packet_pdf
from tax_pipeline.providers.tax_preparer.packet_8879_pdf import extract_tax_preparer_8879_pdf


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "tax_preparer",
        "1040_packet",
        "pdf",
        CallableDocumentHandler(extract_tax_preparer_1040_packet_pdf),
    )
    registry.register(
        "tax_preparer",
        "8879",
        "pdf",
        CallableDocumentHandler(extract_tax_preparer_8879_pdf),
    )
