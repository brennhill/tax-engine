from __future__ import annotations

from dataclasses import is_dataclass
from decimal import Decimal
import unittest

from tax_pipeline.core.facts import (
    CanonicalFact,
    FactProvenance,
    IgnoredFact,
    UnsupportedFact,
    assert_facts_ready_for_legal_stages,
)


class CanonicalFactContractsTest(unittest.TestCase):
    def test_canonical_fact_records_auditable_typed_value_and_stable_fingerprint(self) -> None:
        provenance = FactProvenance(
            source_document_ref="years/demo-2025/facts/jpm-1099.json",
            source_field="1099-DIV:1a",
            extracted_by="jpm_1099_parser",
        )
        fact = CanonicalFact(
            key="us.dividends.total.usd",
            value=Decimal("125.40"),
            provenance=provenance,
            tax_year=2025,
            taxpayer_scope="primary",
            currency="USD",
            unit="money",
            confidence=Decimal("0.99"),
        )
        same_fact = CanonicalFact(
            key="us.dividends.total.usd",
            value=Decimal("125.40"),
            provenance=provenance,
            tax_year=2025,
            taxpayer_scope="primary",
            currency="USD",
            unit="money",
            confidence=Decimal("0.99"),
        )

        self.assertTrue(is_dataclass(fact))
        self.assertEqual(fact.key, "us.dividends.total.usd")
        self.assertIsInstance(fact.value, Decimal)
        self.assertEqual(fact.provenance.source_document_ref, "years/demo-2025/facts/jpm-1099.json")
        self.assertEqual(fact.provenance.source_field, "1099-DIV:1a")
        self.assertEqual(fact.tax_year, 2025)
        self.assertEqual(fact.taxpayer_scope, "primary")
        self.assertEqual(fact.currency, "USD")
        self.assertEqual(fact.unit, "money")
        self.assertEqual(fact.confidence, Decimal("0.99"))
        self.assertEqual(fact.fingerprint, same_fact.fingerprint)
        self.assertNotEqual(fact.fingerprint, "")

    def test_unsupported_and_ignored_facts_require_human_readable_reasons(self) -> None:
        fact = CanonicalFact(
            key="broker.raw.memo",
            value="memo only",
            provenance=FactProvenance(
                source_document_ref="normalized/broker.json",
                source_field="memo",
                extracted_by="broker_parser",
            ),
            tax_year=2025,
            taxpayer_scope="joint",
            unit="text",
            confidence=Decimal("0.80"),
        )

        with self.assertRaisesRegex(ValueError, "UnsupportedFact.reason"):
            UnsupportedFact(fact=fact, reason=" ")
        with self.assertRaisesRegex(ValueError, "IgnoredFact.reason"):
            IgnoredFact(fact=fact, reason="")

        unsupported = UnsupportedFact(fact=fact, reason="No 2025 law stage consumes broker memo fields.")
        ignored = IgnoredFact(fact=fact, reason="Duplicate of the manually reviewed broker total.")

        self.assertIn("law stage", unsupported.reason)
        self.assertIn("Duplicate", ignored.reason)
        self.assertTrue(is_dataclass(unsupported))
        self.assertTrue(is_dataclass(ignored))

    def test_missing_provenance_fails_before_legal_stage_execution(self) -> None:
        with self.assertRaisesRegex(ValueError, "provenance"):
            CanonicalFact(
                key="de.wages.gross.eur",
                value=Decimal("50000.00"),
                provenance=None,
                tax_year=2025,
                taxpayer_scope="primary",
                currency="EUR",
                unit="money",
                confidence=Decimal("1.0"),
            )

        good_fact = CanonicalFact(
            key="de.wages.gross.eur",
            value=Decimal("50000.00"),
            provenance=FactProvenance(
                source_document_ref="lohnsteuerbescheinigung.pdf",
                source_field="Bruttoarbeitslohn",
                extracted_by="germany_payroll_parser",
            ),
            tax_year=2025,
            taxpayer_scope="primary",
            currency="EUR",
            unit="money",
            confidence=Decimal("1.0"),
        )
        assert_facts_ready_for_legal_stages([good_fact])


if __name__ == "__main__":
    unittest.main()
