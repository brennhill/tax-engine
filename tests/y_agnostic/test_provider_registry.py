from __future__ import annotations

import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.classify import classify_relative_path
from tax_pipeline.fact_extraction import DEFAULT_PROVIDER_REGISTRY
from tax_pipeline.providers.base import DocumentDescriptor, UnsupportedDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.shared.document import descriptor_from_classification


class ProviderDescriptorTest(unittest.TestCase):
    def test_classification_exposes_provider_descriptor_fields(self) -> None:
        schwab = classify_relative_path(Path("brokers/2025-Individual_XXX273_Transactions_schwab.csv"))
        coinbase = classify_relative_path(Path("crypto/coinbase-1099-DA.pdf"))
        finanzamt = classify_relative_path(Path("germany/ESt-Bescheid inkl. VZ 2024.pdf"))

        self.assertEqual(schwab["provider"], "schwab")
        self.assertEqual(schwab["document_family"], "transactions")
        self.assertEqual(schwab["format"], "csv")
        self.assertEqual(schwab["country_of_origin"], "US")

        self.assertEqual(coinbase["provider"], "coinbase")
        self.assertEqual(coinbase["document_family"], "1099_da")
        self.assertEqual(coinbase["format"], "pdf")
        self.assertEqual(coinbase["country_of_origin"], "US")

        self.assertEqual(finanzamt["provider"], "finanzamt")
        self.assertEqual(finanzamt["document_family"], "steuerbescheid")
        self.assertEqual(finanzamt["format"], "pdf")
        self.assertEqual(finanzamt["country_of_origin"], "DE")


class ProviderRegistryTest(unittest.TestCase):
    def test_registry_resolves_registered_handler(self) -> None:
        registry = ProviderRegistry()
        handler = UnsupportedDocumentHandler()
        descriptor = DocumentDescriptor(
            provider="schwab",
            document_family="transactions",
            format="csv",
            doc_type="schwab_transactions_csv",
            owner="person_1",
            tax_year=2025,
            country_of_origin="US",
            confidence="high",
        )

        registry.register("schwab", "transactions", "csv", handler)

        self.assertIs(registry.resolve(descriptor), handler)

    def test_registry_falls_back_to_unsupported_handler(self) -> None:
        registry = ProviderRegistry()
        descriptor = DocumentDescriptor(
            provider="shareworks",
            document_family="statement",
            format="pdf",
            doc_type="shareworks_statement_pdf",
            owner="person_1",
            tax_year=2025,
            country_of_origin="US",
            confidence="medium",
        )

        handler = registry.resolve(descriptor)

        self.assertIsInstance(handler, UnsupportedDocumentHandler)

    def test_registry_exposes_registered_provider_triples(self) -> None:
        registry = ProviderRegistry()
        handler = UnsupportedDocumentHandler()

        registry.register("schwab", "transactions", "csv", handler)
        registry.register("coinbase", "1099_da", "pdf", handler)

        self.assertEqual(
            registry.registered_handler_keys(),
            {
                ("coinbase", "1099_da", "pdf"),
                ("schwab", "transactions", "csv"),
            },
        )

    def test_default_registry_resolves_supported_examples(self) -> None:
        descriptors = [
            descriptor_from_classification(classify_relative_path(Path("brokers/2025-Individual_XXX273_Transactions_schwab.csv"))),
            descriptor_from_classification(classify_relative_path(Path("crypto/coinbase-1099-DA.pdf"))),
            descriptor_from_classification(classify_relative_path(Path("germany/ESt-Bescheid inkl. VZ 2024.pdf"))),
        ]

        for descriptor in descriptors:
            handler = DEFAULT_PROVIDER_REGISTRY.resolve(descriptor)
            self.assertNotIsInstance(
                handler,
                UnsupportedDocumentHandler,
                f"Expected registered handler for {(descriptor.provider, descriptor.document_family, descriptor.format)}",
            )


if __name__ == "__main__":
    unittest.main()
