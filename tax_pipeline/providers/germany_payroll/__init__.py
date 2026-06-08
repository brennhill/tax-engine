from __future__ import annotations

from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.germany_payroll.social_insurance_notice_pdf import (
    extract_german_social_insurance_notice_pdf,
)
from tax_pipeline.providers.registry import ProviderRegistry


def register_handlers(registry: ProviderRegistry) -> None:
    registry.register(
        "germany_payroll",
        "social_insurance_notice",
        "pdf",
        CallableDocumentHandler(extract_german_social_insurance_notice_pdf),
    )
