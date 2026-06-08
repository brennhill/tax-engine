from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.shareworks.statement_pdf import extract_shareworks_statement_pdf


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "shareworks",
        "statement",
        "pdf",
        CallableDocumentHandler(extract_shareworks_statement_pdf),
    )
