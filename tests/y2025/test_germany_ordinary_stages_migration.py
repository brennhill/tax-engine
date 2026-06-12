"""Migration regression test for the Germany ordinary rule graph
(DE25-00 through DE25-10) from the legacy ``output_keys`` /
``form_line_refs`` / ``form_line_urls`` shape to the new
``outputs: tuple[OutputDeclaration, ...]`` shape introduced in
``tax_pipeline.core.stages``.

The migration must preserve the legacy fingerprint surface byte-for-byte
(see ``LawStage.__post_init__`` derivation rule), so any audit packet
produced before the migration matches the one produced after.

Authority for the underlying calculations is unchanged (see
``tax_pipeline/y2025/germany_ordinary_rules.py`` and the per-stage
``legal_refs`` tuples). The migration is purely a schema change.
"""
from __future__ import annotations

import unittest

from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.y2025.germany_stages import germany_ordinary_law_stages_2025


EXPECTED_ORDINARY_STAGE_IDS = (
    "DE25-00-FILING-POSTURE-GATE",
    "DE25-01-WAGE-INCOME",
    "DE25-02-WERBUNGSKOSTEN",
    "DE25-03-NET-EMPLOYMENT",
    "DE25-04-OTHER-22NR3",
    "DE25-EUER",
    "DE25-ALTERSENTLASTUNGSBETRAG",
    "DE25-ARBEITSZIMMER",
    "DE25-05-RETIREMENT-SA",
    "DE25-06-HEALTH-VORSORGE-SA",
    "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
    "DE25-SPENDENABZUG",
    "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
    "DE25-UNTERHALTSLEISTUNGEN",
    "DE25-BEHINDERUNG-PAUSCHBETRAG",
    "DE25-07-TAXABLE-INCOME",
    "DE25-08-INCOME-TAX-TARIFF",
    "DE25-09-ORDINARY-SOLI",
    "DE25-10-ORDINARY-CREDITS",
)


class GermanyOrdinaryStagesMigratedToOutputsShape(unittest.TestCase):
    """Every ordinary stage must declare its outputs via the new
    ``outputs=tuple[OutputDeclaration, ...]`` field. The legacy
    ``output_keys`` / ``form_line_refs`` / ``form_line_urls`` arguments
    must no longer be passed at construction time. The dual-mode
    LawStage validator derives the legacy fields from ``outputs`` so
    fingerprints stay stable.
    """

    def test_every_ordinary_stage_declares_outputs(self) -> None:
        stages = germany_ordinary_law_stages_2025()
        self.assertEqual(
            tuple(stage.stage_id for stage in stages),
            EXPECTED_ORDINARY_STAGE_IDS,
        )
        for stage in stages:
            with self.subTest(stage_id=stage.stage_id):
                self.assertGreater(
                    len(stage.outputs),
                    0,
                    f"{stage.stage_id} must declare outputs via the new "
                    "OutputDeclaration shape; legacy output_keys-only "
                    "stages are no longer accepted in this rule graph.",
                )
                for decl in stage.outputs:
                    self.assertIsInstance(decl, OutputDeclaration)

    def test_every_ordinary_output_is_classified(self) -> None:
        stages = germany_ordinary_law_stages_2025()
        for stage in stages:
            for decl in stage.outputs:
                with self.subTest(stage_id=stage.stage_id, key=decl.key):
                    has_form_line = bool(decl.form_line_refs)
                    has_audit = bool(decl.audit_waypoints)
                    self.assertTrue(
                        has_form_line or has_audit,
                        f"{stage.stage_id}/{decl.key} must declare a "
                        "form_line_ref or an audit_waypoint.",
                    )
                    for ref in decl.form_line_refs:
                        self.assertIsInstance(ref, FormLineRef)
                    for waypoint in decl.audit_waypoints:
                        self.assertIsInstance(waypoint, AuditWaypoint)

    def test_output_keys_match_legacy_set(self) -> None:
        """The migrated stages must declare exactly the same output_keys
        the legacy graph declared (so downstream rule wiring continues to
        match input_fact_keys)."""
        stages = germany_ordinary_law_stages_2025()
        observed = {stage.stage_id: tuple(stage.output_keys) for stage in stages}
        expected = {
            "DE25-00-FILING-POSTURE-GATE": ("de.ordinary.filing_posture",),
            "DE25-01-WAGE-INCOME": ("de.ordinary.gross_wages",),
            "DE25-02-WERBUNGSKOSTEN": ("de.ordinary.work_expenses",),
            "DE25-03-NET-EMPLOYMENT": ("de.ordinary.net_employment_income",),
            "DE25-04-OTHER-22NR3": ("de.ordinary.other_income_22nr3_taxable",),
            "DE25-EUER": ("de.ordinary.business_profit_eur",),
            "DE25-ALTERSENTLASTUNGSBETRAG": ("de.ordinary.altersentlastungsbetrag",),
            "DE25-ARBEITSZIMMER": ("de.ordinary.arbeitszimmer",),
            "DE25-05-RETIREMENT-SA": (
                "de.ordinary.retirement_special_expenses",
                "de.ordinary.retirement_special_expenses_total_eur",
            ),
            "DE25-06-HEALTH-VORSORGE-SA": (
                "de.ordinary.health_vorsorge_special_expenses",
                "de.ordinary.health_vorsorge_total_eur",
                "de.ordinary.health_vorsorge_basic_health_eur",
                "de.ordinary.health_vorsorge_other_allowed_eur",
            ),
            "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG": (
                "de.ordinary.total_special_expenses",
                "de.ordinary.sonderausgaben_pauschbetrag_applied_eur",
            ),
            "DE25-SPENDENABZUG": (
                "de.ordinary.spendenabzug",
                "de.ordinary.spendenabzug_deductible_eur",
            ),
            "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN": ("de.ordinary.aussergewoehnliche_belastungen",),
            "DE25-UNTERHALTSLEISTUNGEN": (
                "de.ordinary.unterhaltsleistungen",
                "de.ordinary.unterhaltsleistungen_deductible_eur",
            ),
            "DE25-BEHINDERUNG-PAUSCHBETRAG": ("de.ordinary.behinderung_pauschbetrag",),
            "DE25-07-TAXABLE-INCOME": ("de.ordinary.taxable_income",),
            "DE25-08-INCOME-TAX-TARIFF": ("de.ordinary.income_tax",),
            "DE25-09-ORDINARY-SOLI": ("de.ordinary.solidarity_surcharge",),
            "DE25-10-ORDINARY-CREDITS": ("de.ordinary.refund_before_capital",),
        }
        self.assertEqual(observed, expected)

    def test_form_line_refs_render_byte_for_byte_to_legacy_strings(self) -> None:
        """Stage classification re-pin (post-WS-2B).

        The German ordinary stages previously declared descriptive
        ``form_line_refs`` strings ("Hauptvordruck (ESt 1A) —
        Veranlagungswahl", "Anlage N — Bruttoarbeitslohn (Zeile 6)",
        ...). Per invariant I3
        (``tests/test_form_renderer_lines_match_output_declarations.py``)
        the renderer ↔ OutputDeclaration form-line contract requires
        each FormLineRef to match a ``_required_form_line(rows, form,
        line, ...)`` renderer read; the German renderer
        (``tax_pipeline/forms/germany.py``) only consumes the Anlage
        KAP / KAP-INV CSV via that helper. Hauptvordruck / Anlage N /
        Anlage SO / Anlage Vorsorgeaufwand / Steuerberechnung values
        flow through ``FormEntry`` projections in
        ``_write_hauptvordruck`` / ``_write_anlage_n_for_person`` /
        ``_write_anlage_so`` instead, so the descriptive labels were
        renderer-orphans.

        WS-2B re-anchors every ordinary stage on closed-enum
        AuditWaypoint classifications. Stage fingerprints change as a
        result — that is expected per
        ``docs/invariant-migration-plan.md`` §10 item 4 ("the prior
        classification was wrong"). The legal authority on each output
        continues to ride on ``legal_refs`` / ``authority_urls`` /
        ``legal_formula``.
        """
        stages = {stage.stage_id: stage for stage in germany_ordinary_law_stages_2025()}
        # Every ordinary stage in this list still declares an empty
        # ``form_line_refs`` tuple at the LawStage surface; the per-
        # output classification lives in
        # ``OutputDeclaration.audit_waypoints``.
        #
        # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04) re-introduces
        # FormLineRef declarations on a subset of these stages
        # (DE25-05 / DE25-06 / DE25-SPENDENABZUG /
        # DE25-UNTERHALTSLEISTUNGEN) so the bidirectional I3 contract
        # enforces the new C3 / C4 renderer writes (Anlage
        # Vorsorgeaufwand / Sonderausgaben / Unterhalt). Those stages
        # are intentionally excluded from this empty-refs list — the
        # paired ``test_form_renderer_lines_match_output_declarations``
        # test enforces that every newly declared FormLineRef is
        # consumed by a renderer and vice versa.
        for stage_id in (
            "DE25-00-FILING-POSTURE-GATE",
            "DE25-01-WAGE-INCOME",
            "DE25-02-WERBUNGSKOSTEN",
            "DE25-03-NET-EMPLOYMENT",
            "DE25-04-OTHER-22NR3",
            "DE25-ALTERSENTLASTUNGSBETRAG",
            "DE25-ARBEITSZIMMER",
            "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
            "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
            "DE25-BEHINDERUNG-PAUSCHBETRAG",
            "DE25-07-TAXABLE-INCOME",
            "DE25-08-INCOME-TAX-TARIFF",
            "DE25-09-ORDINARY-SOLI",
            "DE25-10-ORDINARY-CREDITS",
        ):
            with self.subTest(stage_id=stage_id):
                stage = stages[stage_id]
                self.assertEqual(stage.form_line_refs, ())
                self.assertEqual(stage.form_line_urls, ())
                # Each stage's single output is now classified via at
                # least one AuditWaypoint, satisfying the
                # OutputDeclaration "form_line_refs OR audit_waypoints"
                # invariant from ``tax_pipeline/core/stages.py``.
                for decl in stage.outputs:
                    self.assertTrue(
                        decl.audit_waypoints,
                        f"{stage_id}::{decl.key} must classify via AuditWaypoint",
                    )

        # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): the four C3 /
        # C4 stages now carry FormLineRefs binding the bidirectional
        # I3 contract on the new German Anlage renderers. Assert each
        # expected ``(form, line)`` ref renders verbatim so a future
        # refactor cannot silently drop the binding.
        c_audit_expected: dict[str, tuple[tuple[str, str], ...]] = {
            "DE25-05-RETIREMENT-SA": (
                ("Anlage Vorsorgeaufwand", "4-9"),
            ),
            "DE25-06-HEALTH-VORSORGE-SA": (
                ("Anlage Vorsorgeaufwand", "11-14"),
                ("Anlage Vorsorgeaufwand", "31-37"),
            ),
            "DE25-SPENDENABZUG": (
                ("Anlage Sonderausgaben", "5-7"),
            ),
            "DE25-UNTERHALTSLEISTUNGEN": (
                ("Anlage Unterhalt", "7"),
            ),
        }
        for stage_id, expected_refs in c_audit_expected.items():
            with self.subTest(stage_id=stage_id):
                stage = stages[stage_id]
                rendered = tuple(
                    f"{form} {line}" for form, line in expected_refs
                )
                self.assertEqual(stage.form_line_refs, rendered)
                # Authority URL is required for every C-audit
                # FormLineRef.
                for url in stage.form_line_urls:
                    self.assertTrue(url, f"{stage_id} FormLineRef must carry an authority URL")


if __name__ == "__main__":
    unittest.main()
