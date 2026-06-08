from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.schwab.form_1099_composite_pdf import extract_schwab_1099_composite_pdf
from tax_pipeline.providers.schwab.form_1099_csv import extract_schwab_1099_csv
from tax_pipeline.providers.schwab.limitation_image import extract_schwab_limitation_image
from tax_pipeline.providers.schwab.transactions_csv import extract_schwab_transactions_csv


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "schwab",
        "1099_composite",
        "pdf",
        CallableDocumentHandler(extract_schwab_1099_composite_pdf),
    )
    registry.register(
        "schwab",
        "1099",
        "csv",
        CallableDocumentHandler(extract_schwab_1099_csv),
    )
    registry.register(
        "schwab",
        "transactions",
        "csv",
        CallableDocumentHandler(extract_schwab_transactions_csv),
    )
    registry.register(
        "schwab",
        "limitation_notice",
        "image",
        CallableDocumentHandler(extract_schwab_limitation_image),
    )
