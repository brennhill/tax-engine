from __future__ import annotations

from tax_pipeline.providers.base import UnsupportedDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "germany_bank",
        "capital_certificate",
        "pdf",
        UnsupportedDocumentHandler(),
    )
