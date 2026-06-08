from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.jpm.form_1099_b_pdf import extract_jpm_1099_b_pdf
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "jpm",
        "1099_b",
        "pdf",
        CallableDocumentHandler(extract_jpm_1099_b_pdf),
    )
