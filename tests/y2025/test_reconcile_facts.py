from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from tax_pipeline.core.assessment import AssessmentPackage, RenderProjection
from tax_pipeline.core.stages import StageGraphValidation, StageResult
from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.pipelines.y2025.reconcile_facts import (
    build_assessment_package_2025,
    reconcile_facts_2025,
)


class ReconcileFacts2025Test(unittest.TestCase):
    def test_reconcile_facts_loads_config_and_reference_data_with_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)

            reconciled = reconcile_facts_2025(paths)

        by_key = {fact.key: fact for fact in reconciled.canonical_facts}
        self.assertEqual(by_key["profile.tax_year"].value, 2025)
        self.assertEqual(by_key["person.person_1.display_name"].value, "Alex North")
        self.assertEqual(by_key["payment.usa.person_1.estimated_tax_payment.usd"].value, Decimal("1000.00"))
        self.assertEqual(
            by_key["reference.us_tax_constants.irs.eur_per_usd_yearly_average_2025"].provenance.source_field,
            "irs.eur_per_usd_yearly_average_2025",
        )
        self.assertTrue(all(fact.provenance.source_document_ref for fact in reconciled.canonical_facts))
        self.assertFalse(
            [fact for fact in reconciled.unsupported_facts if fact.fact.key.startswith("profile.raw_bucket.")]
        )
        ignored_sources = {fact.fact.provenance.source_document_ref for fact in reconciled.ignored_facts}
        self.assertIn("normalized/facts/README.md", ignored_sources)
        self.assertIn("normalized/facts/index.json", ignored_sources)

    def test_unknown_profile_raw_bucket_is_explicit_unsupported_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            profile = json.loads(paths.profile_path.read_text())
            profile["raw_buckets"].append("mystery_bank")
            paths.profile_path.write_text(json.dumps(profile))

            reconciled = reconcile_facts_2025(paths)

        raw_bucket_facts = [
            fact for fact in reconciled.unsupported_facts if fact.fact.key == "profile.raw_bucket.mystery_bank"
        ]
        self.assertEqual(len(raw_bucket_facts), 1)
        unsupported = raw_bucket_facts[0]
        self.assertEqual(unsupported.fact.key, "profile.raw_bucket.mystery_bank")
        self.assertIn("raw bucket", unsupported.reason)

    def test_unrecognized_normalized_fact_file_is_explicit_unsupported_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            unsupported_path = paths.facts_root / "new-broker-form.facts.json"
            unsupported_path.write_text('{"gross_wages_eur": "100000.00"}')

            reconciled = reconcile_facts_2025(paths)

        unsupported = [
            fact
            for fact in reconciled.unsupported_facts
            if fact.fact.provenance.source_document_ref == "normalized/facts/new-broker-form.facts.json"
        ]
        self.assertEqual(len(unsupported), 1)
        self.assertIn("unsupported fact file", unsupported[0].reason)

    def test_assessment_package_fails_closed_with_unsupported_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            profile = json.loads(paths.profile_path.read_text())
            profile["raw_buckets"].append("mystery_bank")
            paths.profile_path.write_text(json.dumps(profile))
            reconciled = reconcile_facts_2025(paths)

        with self.assertRaisesRegex(ValueError, "unsupported facts"):
            build_assessment_package_2025(reconciled)

    def test_render_projection_fields_must_come_from_legal_stage_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            reconciled = reconcile_facts_2025(paths)

        with self.assertRaisesRegex(ValueError, "render fields must come from legal stage outputs"):
            build_assessment_package_2025(
                reconciled.canonical_facts,
                render_fields={"profile.tax_year": 2025},
            )

        result = StageResult(
            stage_id="DE25-TEST-STAGE",
            outputs={"de.final.balance": Decimal("1.00")},
            input_values={"profile.tax_year": 2025},
            input_fingerprints={"profile.tax_year": "sha256:profile.tax_year"},
            output_fingerprints={"de.final.balance": "sha256:de.final.balance"},
            diagnostics=(),
            precision_notes={"de.final.balance": "Test output precision."},
        )
        package = build_assessment_package_2025(
            reconciled.canonical_facts,
            germany_stage_results=(result,),
            render_fields={"de.final.balance": Decimal("1.00")},
        )

        self.assertEqual(package.render_projection.fields["de.final.balance"], Decimal("1.00"))

    def test_build_assessment_package_uses_core_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(Path(tmp), demo_name="demo-2025", year=2025)
            reconciled = reconcile_facts_2025(paths)

        package = build_assessment_package_2025(
            reconciled.canonical_facts,
            audit_graph=StageGraphValidation(
                stage_ids=(),
                initial_fact_keys=tuple(sorted(fact.key for fact in reconciled.canonical_facts)),
                output_keys=(),
                final_available_keys=tuple(sorted(fact.key for fact in reconciled.canonical_facts)),
            ),
            render_projection=RenderProjection(
                fields={},
                source_output_fingerprints={},
            ),
        )

        self.assertIsInstance(package, AssessmentPackage)
        self.assertEqual(package.tax_year, 2025)
        self.assertGreater(len(package.canonical_facts), 0)


if __name__ == "__main__":
    unittest.main()
