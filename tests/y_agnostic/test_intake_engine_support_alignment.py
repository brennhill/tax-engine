"""F-A7 — Intake registry / engine wiring alignment.

For every posture in ``POSTURE_REGISTRY`` that advertises
``engine_supported=True``, the engine must actually consume the key.
Otherwise the intake UI is lying to the user: they make a choice that
travels nowhere and the engine quietly ignores it.

The alignment is intentionally one-directional and broad:

  * For ``elections.<suffix>`` keys we require either a tuple-form
    profile read ``("elections", "<suffix>")`` in
    ``germany_2025_inputs.py`` / ``us_2025_inputs.py`` (the canonical
    profile loaders), OR a textual ``elections.<suffix>`` reference
    elsewhere in the engine (``treaty_2025_rules.py``,
    ``cross_jurisdiction_2025.py``, ``run_year.py``,
    ``analysis_inputs.py``).
  * For ``us.treaty.<suffix>`` keys we require the suffix to appear as
    a typed-input attribute (``treaty_inputs.<suffix>``) anywhere in
    the engine — that is the fact channel through which the rule
    graph reads the posture.
  * For ``jurisdictions.<country>.<suffix>`` and other dotted-path
    keys we require a textual reference to the dotted suffix or its
    leaf token in the engine inputs.

If a registry entry claims engine support but no rule reads the key,
this test fails — the posture is either a UI ghost (engine ignores
the user's choice) or the engine wiring was lost.

This is the F-A7 alignment guard rail from the 2026-05-01 architecture
findings; sister to F-A2 (FEIE / LOB engine_supported flag updates).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tax_pipeline.intake.postures import POSTURE_REGISTRY


PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Files we treat as the legitimate set of "engine consumers" of profile
# postures. Inputs modules are the canonical profile loaders; the
# treaty rules, cross-jurisdiction gate, and run-year orchestrator are
# the other places where elected postures are read from profile or
# from the typed input dataclasses produced by the loaders.
_ENGINE_FILES = (
    "tax_pipeline/y2025/germany_inputs.py",
    "tax_pipeline/y2025/us_inputs.py",
    "tax_pipeline/y2025/treaty_rules.py",
    "tax_pipeline/y2025/cross_jurisdiction.py",
    "tax_pipeline/run_year.py",
    "tax_pipeline/analysis_inputs.py",
    # The Germany pipeline reads de-model-assumptions.csv via
    # ``ensure_capital_guenstigerpruefung_position_2025`` rather than
    # the inputs module, so we include it in the consumer corpus too.
    "tax_pipeline/pipelines/y2025/germany_model.py",
)


def _engine_text() -> str:
    parts: list[str] = []
    for relative in _ENGINE_FILES:
        path = PROJECT_ROOT / relative
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _references_key(blob: str, key: str) -> bool:
    """Return True iff the engine corpus references this posture key.

    The match is deliberately tolerant of how the engine spells the
    key:

      * Dotted-path literal (``elections.elect_section_911_feie``) —
        used in docstrings and comments adjacent to the loader.
      * Tuple-form profile read (``("elections", "elect_section_911_feie")``)
        — the canonical ``_required_profile_*(profile, ("a", "b"))``
        signature used by the inputs modules.
      * Typed-attribute access on a dataclass instance
        (``treaty_inputs.lob_qualification_category``) — the channel
        the rule graph uses for treaty postures.
    """
    if key in blob:
        return True
    segments = key.split(".")
    if len(segments) >= 2:
        # Tuple form: ("a", "b", ...)
        tuple_pattern = re.compile(
            r"\(\s*"
            + r"\s*,\s*".join(rf"[\"']{re.escape(part)}[\"']" for part in segments)
            + r"\s*[,)]"
        )
        if tuple_pattern.search(blob):
            return True
    # Last-segment attribute access (e.g. ".lob_qualification_category"
    # on a dataclass instance, ".us_filing_required" on a profile dict).
    leaf = segments[-1]
    if re.search(rf"\b{re.escape(leaf)}\b", blob):
        return True
    return False


# Postures that are not user election keys but instead identifiers in
# the user-facing UI for things the engine consumes through other
# named channels. These are explicitly enumerated — adding to this set
# requires a maintainer's review.
_UI_ONLY_KEYS: frozenset[str] = frozenset()


class EngineSupportAlignmentTest(unittest.TestCase):
    """Every engine_supported=True posture has at least one engine consumer."""

    def test_supported_postures_are_consumed_by_engine(self) -> None:
        blob = _engine_text()
        unsupported: list[str] = []
        for field in POSTURE_REGISTRY:
            if not field.engine_supported:
                continue
            if field.key in _UI_ONLY_KEYS:
                continue
            if not _references_key(blob, field.key):
                unsupported.append(field.key)
        self.assertFalse(
            unsupported,
            "Postures advertise engine_supported=True but no engine "
            "consumer was found. Either wire the key into the loader or "
            "set engine_supported=False:\n  - "
            + "\n  - ".join(sorted(unsupported)),
        )

    def test_feie_election_is_engine_supported(self) -> None:
        # F-A2: Wave 3B (a085717) wired US25-FEIE; the registry must
        # report that.
        for field in POSTURE_REGISTRY:
            if field.key == "elections.elect_section_911_feie":
                self.assertTrue(
                    field.engine_supported,
                    "elections.elect_section_911_feie should advertise "
                    "engine_supported=True after Wave 3B (a085717).",
                )
                return
        self.fail("elections.elect_section_911_feie missing from POSTURE_REGISTRY.")

    def test_lob_qualification_is_engine_supported(self) -> None:
        # F-A2: Wave 3B (564ae1f) wired TREATY25-LOB-QUALIFICATION; the
        # registry must report that.
        for field in POSTURE_REGISTRY:
            if field.key == "us.treaty.lob_qualification_category":
                self.assertTrue(
                    field.engine_supported,
                    "us.treaty.lob_qualification_category should advertise "
                    "engine_supported=True after Wave 3B (564ae1f).",
                )
                return
        self.fail("us.treaty.lob_qualification_category missing from POSTURE_REGISTRY.")


if __name__ == "__main__":
    unittest.main()
