"""Invariant: ``StageId.__str__`` must produce the literal pre-P9
string for every stage in the rule graph.

Per CLAUDE.md invariant I6, ``stable_fingerprint`` payloads must use
canonical values; any change to the serialized form of ``stage_id``
breaks fingerprint stability for the entire ``final-legal-output.json``
audit boundary. The P9 typed-StageId migration preserves the literal
string form of every stage ID. This test asserts that contract by
walking every ``LawStage`` declared by the rule-graph factories and
checking that its ``stage_id`` (the string-stored value) round-trips
through ``StageId.parse → str`` to the same byte sequence.

The frozen list of expected pre-P9 stage IDs lives in
``tests.test_stage_id.PRE_P9_STAGE_IDS``. Any new stage ID added to
the rule graph must be appended there explicitly.
"""

from __future__ import annotations

import unittest

from tax_pipeline.core.stage_id import StageId
from tax_pipeline.y2025.bridge_stages import bridge_law_stages_2025
from tax_pipeline.y2025.derivation.germany_derivations import (
    germany_derivation_law_rules_2025,
)
from tax_pipeline.y2025.derivation.us_derivations import (
    usa_derivation_law_rules_2025,
)
from tax_pipeline.y2025.germany_stages import germany_law_stages_2025
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.us_stages import usa_law_stages_2025

from tests.y_agnostic.test_stage_id import PRE_P9_STAGE_IDS


def _all_law_stages():
    """Walk every LawStage emitted by the 2025 rule-graph factories.

    Pipeline 1 derivation factories return ``LawRule``; we extract the
    ``.stage`` attribute. Pipeline 2 / treaty / bridge factories return
    ``LawStage`` directly.
    """
    pipeline2 = (
        *germany_law_stages_2025(),
        *usa_law_stages_2025(),
        *treaty_law_stages_2025(),
        *bridge_law_stages_2025(),
    )
    pipeline1 = tuple(
        rule.stage
        for rule in (
            *germany_derivation_law_rules_2025(),
            *usa_derivation_law_rules_2025(),
        )
    )
    return (*pipeline2, *pipeline1)


class StageIdFingerprintStabilityTest(unittest.TestCase):
    def test_every_law_stage_has_a_typed_round_trippable_stage_id(self) -> None:
        """Every ``LawStage.stage_id`` parses as a typed
        :class:`StageId` and serializes back to its byte-identical
        literal form. This is the contract that protects fingerprint
        stability under invariant I6 across the P9 migration."""

        all_stages = _all_law_stages()
        self.assertGreater(
            len(all_stages),
            0,
            "no law stages discovered — the rule graph is empty?",
        )
        for stage in all_stages:
            stage_id_str = stage.stage_id
            with self.subTest(stage_id=stage_id_str):
                self.assertIsInstance(stage_id_str, str)
                # Round-trip: parse the literal string into a typed
                # StageId, then serialize back to a string. The result
                # must be byte-identical to the stored string.
                parsed = StageId.parse(stage_id_str)
                self.assertEqual(str(parsed), stage_id_str)

    def test_every_executed_stage_id_appears_in_pre_p9_frozen_list(self) -> None:
        """Every ``LawStage.stage_id`` in the executable rule graph
        must appear in ``PRE_P9_STAGE_IDS`` (the frozen list pinned
        from a 2026-05-04 grep). A new stage ID requires updating the
        frozen list explicitly so the byte-identical-fingerprint
        contract is documented at the audit boundary, not silently
        absorbed.
        """
        actual_ids = {stage.stage_id for stage in _all_law_stages()}
        frozen = set(PRE_P9_STAGE_IDS)

        new_stage_ids = actual_ids - frozen
        self.assertFalse(
            new_stage_ids,
            (
                "rule graph emits stage IDs not pinned in the pre-P9 "
                "frozen list — append to PRE_P9_STAGE_IDS in "
                "tests/test_stage_id.py and document the byte-identical "
                f"fingerprint contract:\n  {sorted(new_stage_ids)}"
            ),
        )

    def test_law_stage_stage_id_is_stored_as_string(self) -> None:
        """``LawStage.__post_init__`` validates the typed StageId
        triple but stores ``stage_id`` as the literal string form so
        fingerprint payloads (``"stage_id": self.stage_id``) and the
        200+ string-reading call sites stay byte-identical.
        """
        stages = germany_law_stages_2025()
        self.assertGreater(len(stages), 0)
        for stage in stages:
            with self.subTest(stage_id=stage.stage_id):
                self.assertIsInstance(stage.stage_id, str)
                # Typed view exists but does not replace the string field.
                self.assertIsInstance(stage.stage_id_typed, StageId)
                self.assertEqual(str(stage.stage_id_typed), stage.stage_id)


if __name__ == "__main__":
    unittest.main()
