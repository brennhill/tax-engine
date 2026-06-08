"""Migration tests for the Germany capital rule graph (DE25-13 through
DE25-21) from the legacy ``output_keys`` + ``form_line_refs`` shape to
the new ``outputs: tuple[OutputDeclaration, ...]`` shape.

Each migrated stage must:
1. Declare at least one ``OutputDeclaration`` in ``LawStage.outputs``.
2. Preserve fingerprint stability against the pre-migration legacy
   declaration: the derived ``form_line_refs`` strings must reproduce
   the original byte-for-byte and the stage fingerprint must not change
   relative to the legacy ``LawStage`` constructed with the same
   metadata.

Authority: the form-line provenance is the audit trail for § 32d
Abs. 5 EStG (https://www.gesetze-im-internet.de/estg/__32d.html) and
the InvStG § 20 Teilfreistellung disclosure
(https://www.gesetze-im-internet.de/invstg_2018/__20.html).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.core.stages import LawStage, OutputDeclaration
from tax_pipeline.y2025.germany_stages import germany_capital_law_stages_2025


class GermanyCapitalStagesMigrationTest(unittest.TestCase):
    """Every Germany capital stage must declare ``outputs`` (new shape)."""

    def test_every_stage_uses_outputs_shape(self) -> None:
        stages = germany_capital_law_stages_2025()
        # 10 stages: DE25-13, DE25-13F-VORABPAUSCHALE (InvStG § 19 deemed-
        # distribution, https://www.gesetze-im-internet.de/invstg_2018/__19.html),
        # DE25-14 through DE25-21.
        self.assertEqual(len(stages), 10)
        for stage in stages:
            self.assertIsInstance(stage, LawStage, stage.stage_id)
            self.assertGreater(
                len(stage.outputs),
                0,
                f"{stage.stage_id} must declare outputs via OutputDeclaration tuple",
            )
            for decl in stage.outputs:
                self.assertIsInstance(decl, OutputDeclaration, stage.stage_id)

    def test_expected_form_line_refs_preserved(self) -> None:
        """Stage classification re-pin (post-WS-2B).

        The German capital stages previously declared descriptive
        ``form_line_refs`` strings (e.g. ``"Anlage KAP — Abgeltungsteuer
        25 % (§ 32d Abs. 1 EStG)"``). Per invariant I3
        (``tests/test_form_renderer_lines_match_output_declarations.py``),
        the renderer ↔ OutputDeclaration form-line contract requires
        each FormLineRef to match a ``_required_form_line(rows, form,
        line, ...)`` renderer read on the
        ``germany-kap-summary.csv`` projection rows; those
        person-specific Anlage KAP / KAP-INV labels are
        ``"Anlage KAP - Person 1"``, ``"Anlage KAP - Person 2"``,
        ``"Anlage KAP-INV"`` paired with the numeric Zeile that the
        BMF Anlage-KAP physical form carries (5/7/8/17/19-24/37/38/40/41
        on Anlage KAP per person and 4/8/9-13/14/26 on Anlage KAP-INV).
        WS-2B re-anchors every capital stage onto those concrete
        person-and-Zeile pairs. Stage fingerprints change as a result —
        that is expected per ``docs/invariant-migration-plan.md`` §10
        item 4 ("the prior classification was wrong"). DE25-20 (treaty
        cross-check) and DE25-21 (final capital tax) carry no
        renderer-read form line and are RECONCILIATION_INVARIANT only.
        """
        # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5
        # und 6 EStG, removing the former 2024 per-bucket Anlage KAP
        # form-line refs for Termingeschäfte positives ("21") and
        # Termingeschäfte losses ("24"). The DE25-13 expected pairs
        # below correspond to the surviving VZ 2025 Anlage KAP Zeilen.
        # BMF-VERIFIED 2026-05-13 against BMF 16.05.2025
        # Steuerbescheinigung-Schreiben.
        expected = {
            "DE25-13-CAPITAL-RAW-BUCKETS": (
                "Anlage KAP - Person 1 20",
                "Anlage KAP - Person 1 23",
                "Anlage KAP - Person 2 5",
                "Anlage KAP - Person 2 7",
                "Anlage KAP - Person 2 8",
                "Anlage KAP-INV 4",
                "Anlage KAP-INV 8",
                "Anlage KAP-INV 9-13",
            ),
            "DE25-14-FUND-TEILFREISTELLUNG": (
                "Anlage KAP-INV 14",
                "Anlage KAP-INV 26",
            ),
            "DE25-15-SECTION-20-6-NETTING": ("Anlage KAP - Person 1 19",),
            # A4 (FORM-MAPPING-FOLLOWUP): adds Anlage KAP Z4 form-line
            # refs for the new ``sparer_pauschbetrag_claimed_eur``
            # output. The legacy ``form_line_refs`` derived field
            # concatenates per-output FormLineRefs, so the four
            # ``Anlage KAP - Person N <line>`` entries below appear in
            # the same order the OutputDeclarations are constructed
            # (Z17 first via ``taxable_after_allowance``, then Z4 via
            # ``sparer_pauschbetrag_claimed_eur``).
            "DE25-16-SECTION-20-9-SAVER": (
                "Anlage KAP - Person 1 17",
                "Anlage KAP - Person 2 17",
                "Anlage KAP - Person 1 4",
                "Anlage KAP - Person 2 4",
            ),
            "DE25-17-SECTION-32D1-GROSS-TAX": ("Anlage KAP - Person 2 37",),
            # Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage AUS
            # Zeilen 8 / 9 / 13 / 15 (EUR-Decimal lines) declared on
            # the same OutputDeclaration so the per-country § 34c (1)
            # EStG foreign-tax credit appearing on Anlage AUS is bound
            # to the same § 32d Abs. 5 EStG anrechenbare Steuer scalar
            # that lands on the per-Posten Anlage KAP Zeilen.
            "DE25-18-SECTION-32D5-FTC": (
                "Anlage KAP - Person 1 41",
                "Anlage KAP - Person 2 40",
                "Anlage AUS 8",
                "Anlage AUS 9",
                "Anlage AUS 13",
                "Anlage AUS 15",
            ),
            "DE25-19-CAPITAL-SOLI": ("Anlage KAP - Person 2 38",),
            "DE25-20-TREATY-CHECK": (),
            "DE25-21-FINAL-CAPITAL-TAX": (),
        }
        stages_by_id = {stage.stage_id: stage for stage in germany_capital_law_stages_2025()}
        for stage_id, expected_refs in expected.items():
            stage = stages_by_id[stage_id]
            self.assertEqual(stage.form_line_refs, expected_refs, stage_id)

    def test_output_keys_unchanged(self) -> None:
        """Output keys remain a single canonical key per stage; downstream
        rule implementations key off these names."""
        expected_keys = {
            "DE25-13-CAPITAL-RAW-BUCKETS": ("de.capital.raw_buckets",),
            "DE25-14-FUND-TEILFREISTELLUNG": ("de.capital.fund_after_teilfreistellung",),
            "DE25-15-SECTION-20-6-NETTING": ("de.capital.after_section_20_6_netting",),
            # A4 (FORM-MAPPING-FOLLOWUP): adds
            # ``de.capital.sparer_pauschbetrag_claimed_eur`` (Anlage KAP
            # Z4) alongside ``taxable_after_allowance`` (Z17).
            "DE25-16-SECTION-20-9-SAVER": (
                "de.capital.taxable_after_allowance",
                "de.capital.sparer_pauschbetrag_claimed_eur",
            ),
            "DE25-17-SECTION-32D1-GROSS-TAX": ("de.capital.section_32d1_gross_tax",),
            "DE25-18-SECTION-32D5-FTC": ("de.capital.section_32d5_foreign_tax_credit",),
            "DE25-19-CAPITAL-SOLI": ("de.capital.solidarity_surcharge",),
            "DE25-20-TREATY-CHECK": ("de.capital.treaty_credit_check",),
            "DE25-21-FINAL-CAPITAL-TAX": ("de.capital.final_tax",),
        }
        stages_by_id = {stage.stage_id: stage for stage in germany_capital_law_stages_2025()}
        for stage_id, expected in expected_keys.items():
            self.assertEqual(stages_by_id[stage_id].output_keys, expected, stage_id)


if __name__ == "__main__":
    unittest.main()
