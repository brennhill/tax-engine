from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.datev.lohnsteuerbescheinigung_pdf import extract_datev_lohnsteuerbescheinigung_pdf
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "datev",
        "lohnsteuerbescheinigung",
        "pdf",
        CallableDocumentHandler(extract_datev_lohnsteuerbescheinigung_pdf),
    )
