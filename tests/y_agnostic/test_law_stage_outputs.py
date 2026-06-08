"""Schema tests for the OutputDeclaration / AuditWaypoint / FormLineRef
types that replace the per-stage form_line_refs list with per-output
provenance.

The stated engine goal is: "the final output tells the user which form
lines each value flows through". The old ``LawStage.form_line_refs`` was
per-stage, so a stage with multiple outputs shared one form-line list
across all of them. The new ``OutputDeclaration`` carries form-line
provenance per output, and a closed ``AuditWaypoint`` enum classifies
outputs that are deliberately not on a form line (intermediate math,
per-Posten aggregations, reconciliation invariants, diagnostic
cross-checks, audit fingerprints) so authors cannot leave an output
unaccounted for.

The schema enforces: every OutputDeclaration must have at least one
form_line_ref OR at least one audit_waypoint. An empty/unclassified
output is rejected at LawStage construction time.

LawStage is dual-mode during the migration:
- legacy mode: output_keys + form_line_refs + form_line_urls
- new mode:    outputs = tuple[OutputDeclaration, ...]
Exactly one mode must be used per stage. The legacy mode is preserved
so the four rule graphs can migrate one at a time without breaking
existing tests.

Authority: the form_line provenance underpins § 32d Abs. 5 EStG audit
trail (https://www.gesetze-im-internet.de/estg/__32d.html) and the
IRS Pub. 514 worksheet self-documentation requirement
(https://www.irs.gov/publications/p514).
"""
from __future__ import annotations

import unittest

from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawStage,
    OutputDeclaration,
)


class AuditWaypointEnumTest(unittest.TestCase):
    """The closed enum: every non-form-line output must pick one of these."""

    def test_enum_has_expected_values(self) -> None:
        self.assertEqual(AuditWaypoint.INTERMEDIATE_MATH.value, "intermediate_math")
        self.assertEqual(AuditWaypoint.PER_POSTEN_AGGREGATION.value, "per_posten_aggregation")
        self.assertEqual(AuditWaypoint.RECONCILIATION_INVARIANT.value, "reconciliation_invariant")
        self.assertEqual(AuditWaypoint.DIAGNOSTIC_CROSS_CHECK.value, "diagnostic_cross_check")
        self.assertEqual(AuditWaypoint.AUDIT_FINGERPRINT.value, "audit_fingerprint")

    def test_enum_is_closed(self) -> None:
        # Locking the size prevents drift: adding a new waypoint must be a
        # deliberate code change reviewed by a human, not an accidental
        # string typo somewhere in a stage definition.
        self.assertEqual(len(AuditWaypoint), 5)


class FormLineRefTest(unittest.TestCase):
    """A typed ``(form, line, url)`` triple replacing parallel string tuples."""

    def test_form_and_line_are_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "form"):
            FormLineRef(form="", line="Zeile 19", url="")
        with self.assertRaisesRegex(ValueError, "line"):
            FormLineRef(form="Anlage KAP", line="", url="")

    def test_url_is_optional(self) -> None:
        ref = FormLineRef(form="Anlage KAP", line="Zeile 19")
        self.assertEqual(ref.url, "")

    def test_url_when_present_must_be_text(self) -> None:
        ref = FormLineRef(
            form="Anlage KAP",
            line="Zeile 19",
            url="https://www.gesetze-im-internet.de/estg/__20.html",
        )
        self.assertEqual(ref.url, "https://www.gesetze-im-internet.de/estg/__20.html")


class OutputDeclarationValidationTest(unittest.TestCase):
    """The classification invariant: every output must be a form line OR an
    audit waypoint. Neither alone OR both is acceptable; nothing isn't."""

    def test_form_line_only_is_valid(self) -> None:
        decl = OutputDeclaration(
            key="de.capital.taxable_capital_eur",
            form_line_refs=(FormLineRef("Anlage KAP", "Zeile 19"),),
        )
        self.assertEqual(decl.key, "de.capital.taxable_capital_eur")
        self.assertEqual(len(decl.form_line_refs), 1)
        self.assertEqual(decl.audit_waypoints, frozenset())

    def test_audit_waypoint_only_is_valid(self) -> None:
        decl = OutputDeclaration(
            key="de.capital.total_taxable_before_allowance",
            audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
        )
        self.assertEqual(decl.form_line_refs, ())
        self.assertEqual(decl.audit_waypoints, frozenset({AuditWaypoint.INTERMEDIATE_MATH}))

    def test_form_line_and_audit_waypoint_together_is_valid(self) -> None:
        decl = OutputDeclaration(
            key="de.capital.foreign_tax_credit",
            form_line_refs=(FormLineRef("Anlage KAP", "Zeile 41"),),
            audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
        )
        self.assertEqual(len(decl.form_line_refs), 1)
        self.assertEqual(decl.audit_waypoints, frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}))

    def test_neither_form_line_nor_audit_waypoint_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "form_line_refs.*audit_waypoints|audit_waypoints.*form_line_refs"):
            OutputDeclaration(key="de.capital.unknown")

    def test_key_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "key"):
            OutputDeclaration(
                key="",
                form_line_refs=(FormLineRef("Anlage KAP", "Zeile 19"),),
            )

    def test_audit_waypoint_set_must_contain_enum_members(self) -> None:
        # frozenset({"intermediate_math"}) (a string) must not silently pass.
        # Every entry must be an AuditWaypoint instance so a typo in a stage
        # declaration is caught at construction time, not at audit time.
        with self.assertRaises((ValueError, TypeError)):
            OutputDeclaration(
                key="de.capital.intermediate",
                audit_waypoints=frozenset({"intermediate_math"}),  # type: ignore[arg-type]
            )


class LawStageOutputsModeTest(unittest.TestCase):
    """LawStage requires the ``outputs`` field. The convenience
    attributes ``output_keys`` / ``form_line_refs`` / ``form_line_urls``
    are derived from ``outputs`` in ``__post_init__`` and are not
    constructor parameters.
    """

    def _common_kwargs(self) -> dict:
        return {
            "stage_id": "DE25-TEST",
            "country_or_scope": "DE-2025",
            "legal_refs": ("§ 20 EStG",),
            "authority_urls": ("https://www.gesetze-im-internet.de/estg/__20.html",),
            "input_fact_keys": ("de.capital.fact_a",),
            "rounding_policy": "no rounding",
            "law_order_note": "Test stage for schema migration.",
            "legal_formula": "out_a := fact_a per § 20 EStG",
            "narrative_templates": {"de": "DE25-TEST", "en": "DE25-TEST"},
        }

    def test_new_outputs_shape_derives_legacy_fields(self) -> None:
        stage = LawStage(
            **self._common_kwargs(),
            outputs=(
                OutputDeclaration(
                    key="de.capital.out_a",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP",
                            line="Zeile 19",
                            url="https://www.gesetze-im-internet.de/estg/__20.html",
                        ),
                    ),
                ),
            ),
        )
        self.assertEqual(stage.output_keys, ("de.capital.out_a",))
        self.assertIn("Anlage KAP", stage.form_line_refs[0])
        self.assertIn("Zeile 19", stage.form_line_refs[0])
        self.assertEqual(
            stage.form_line_urls,
            ("https://www.gesetze-im-internet.de/estg/__20.html",),
        )
        self.assertEqual(len(stage.outputs), 1)

    def test_new_outputs_shape_with_audit_waypoint_only(self) -> None:
        # An output classified solely as INTERMEDIATE_MATH still produces a
        # valid stage; it just doesn't contribute any form_line_refs to the
        # derived legacy field. Stage-level form_line_refs would be empty
        # in that case, which the schema must allow because some stages
        # produce only audit values.
        stage = LawStage(
            **self._common_kwargs(),
            outputs=(
                OutputDeclaration(
                    key="de.capital.intermediate",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        )
        self.assertEqual(stage.output_keys, ("de.capital.intermediate",))
        self.assertEqual(stage.form_line_refs, ())
        self.assertEqual(stage.form_line_urls, ())

    def test_multi_output_derives_unioned_form_lines(self) -> None:
        # A stage with two outputs, each touching its own form line, must
        # derive a stage-level form_line_refs that contains both. Order
        # follows declaration order so the audit graph remains stable.
        stage = LawStage(
            **self._common_kwargs(),
            outputs=(
                OutputDeclaration(
                    key="de.capital.out_a",
                    form_line_refs=(FormLineRef("Anlage KAP", "Zeile 19"),),
                ),
                OutputDeclaration(
                    key="de.capital.out_b",
                    form_line_refs=(FormLineRef("Anlage KAP", "Zeile 41"),),
                ),
            ),
        )
        self.assertEqual(len(stage.output_keys), 2)
        self.assertEqual(len(stage.form_line_refs), 2)
        # First declaration's form_line first.
        self.assertIn("Zeile 19", stage.form_line_refs[0])
        self.assertIn("Zeile 41", stage.form_line_refs[1])

    def test_empty_outputs_rejected(self) -> None:
        # Stages must declare at least one output. Constructing without
        # ``outputs`` (or with an empty tuple) leaves the stage with no
        # declared outputs and must fail closed.
        with self.assertRaises(ValueError):
            LawStage(**self._common_kwargs())

    def test_legacy_constructor_fields_rejected(self) -> None:
        # Phase C removed ``output_keys`` / ``form_line_refs`` /
        # ``form_line_urls`` from the constructor signature; passing them
        # is a TypeError. This test pins that contract so a future PR
        # cannot accidentally re-introduce the dual-mode entry point.
        with self.assertRaises(TypeError):
            LawStage(
                **self._common_kwargs(),
                output_keys=("de.capital.out_a",),  # type: ignore[call-arg]
                form_line_refs=("Anlage KAP — Zeile 19",),  # type: ignore[call-arg]
            )


class LawStageDerivedFieldsTest(unittest.TestCase):
    """The convenience fields derived from ``outputs`` carry the
    same content the legacy parallel-tuple fields used to expose,
    so downstream code (graph builders, narrative builders, audit
    fingerprints) keeps reading a flat surface.
    """

    def _common_kwargs(self) -> dict:
        return {
            "stage_id": "DE25-TEST-DERIVED",
            "country_or_scope": "DE-2025",
            "legal_refs": ("§ 20 EStG",),
            "authority_urls": ("https://www.gesetze-im-internet.de/estg/__20.html",),
            "input_fact_keys": ("de.capital.fact_a",),
            "rounding_policy": "no rounding",
            "law_order_note": "Derived fields test.",
            "legal_formula": "out := fact_a per § 20 EStG",
            "narrative_templates": {"de": "DE25-TEST-DERIVED", "en": "DE25-TEST-DERIVED"},
        }

    def test_form_line_refs_render_to_form_plus_line(self) -> None:
        stage = LawStage(
            **self._common_kwargs(),
            outputs=(
                OutputDeclaration(
                    key="de.capital.out",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP",
                            line="— Zeile 19",
                            url="https://www.gesetze-im-internet.de/estg/__20.html",
                        ),
                    ),
                ),
            ),
        )
        # Derived form_line_refs is "form line" with a single space joining
        # them; downstream renderers use the legacy string format unchanged.
        self.assertEqual(stage.form_line_refs, ("Anlage KAP — Zeile 19",))
        self.assertEqual(
            stage.form_line_urls,
            ("https://www.gesetze-im-internet.de/estg/__20.html",),
        )
        self.assertEqual(stage.output_keys, ("de.capital.out",))


if __name__ == "__main__":
    unittest.main()
