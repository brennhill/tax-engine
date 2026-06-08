from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.coinbase.form_1099_da_pdf import extract_coinbase_1099_da_pdf
from tax_pipeline.providers.coinbase.transactions_csv import extract_coinbase_transactions_csv
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "coinbase",
        "transactions",
        "csv",
        CallableDocumentHandler(extract_coinbase_transactions_csv),
    )
    registry.register(
        "coinbase",
        "1099_da",
        "pdf",
        CallableDocumentHandler(extract_coinbase_1099_da_pdf),
    )
