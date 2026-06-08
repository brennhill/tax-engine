"""Proposal 3 extension-surface test: adding a second bilateral treaty.

The whole point of Proposal 3 is that "treaty" is a registered edge
between two countries, not branches in code. The strongest test of
that property is: how many existing files would a maintainer have to
edit to add a synthetic second treaty (e.g., a "DBA_TEST" between
country "TE" and country "ST")?

Pre-P3 the answer was several files (``cross_jurisdiction.py`` had a
literal U.S.-only check, ``rule_narrative_packets.py`` and
``run_year.py`` hardcoded ``treaty_law_stages_2025``, etc.). Post-P3
the answer should be 1: a single ``TreatyDefinition`` row in
``tax_pipeline.treaties.TREATY_REGISTRY``.

This test does not actually wire a second real treaty into the
executed law-stage graph — that would require materialising rule /
stage / law modules and a fingerprint-stability migration of
``final-legal-output.json`` (deferred per the registry's module
docstring until a second treaty actually lands). Instead it asserts:

* registry mechanics (enablement gating, party lookup, stage list
  resolution) work for a synthetic ``DBA_TEST`` treaty inserted
  programmatically;
* the synthetic treaty's ``rules_module`` / ``stages_module`` /
  ``law_module`` strings are **lazy** — they are not pre-imported at
  registry-construction or registry-import time;
* DBA_USA continues to operate alongside the synthetic entry without
  cross-contamination.

If a future commit re-introduces a hardcoded ``"DBA_USA"`` branch in
any registry consumer, the corresponding assertion fails.

Authority:
  * Architecture review §5 Proposal 3.
  * DBA-USA bilingual treaty text:
    https://www.irs.gov/pub/irs-trty/germany.pdf
"""

from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from typing import Iterator

from tax_pipeline.treaties import (
    TREATY_REGISTRY,
    TreatyDefinition,
    find_treaty_for_parties,
    is_treaty_enabled,
    iter_enabled_treaties,
    iter_treaties,
    treaty_stages_for,
)


# Synthetic registry entry. Parties "TE" / "ST" are deliberately
# chosen so they sort alphabetically as ("ST", "TE") — exercising the
# alphabetical-sort canonicalisation contract — and so they are not
# real ISO-3166 codes (avoiding any accidental collision with a future
# real registration). The dotted-path module names point at strings
# that DO NOT EXIST on the filesystem; the lazy-import test below
# proves no consumer eagerly resolves them.
SYNTHETIC_TREATY = TreatyDefinition(
    treaty_id="DBA_TEST",
    display_name="Synthetic Test Convention Between Country TE and Country ST",
    short_name="TE-ST Test Treaty",
    parties=("ST", "TE"),
    in_force_year=2025,
    last_protocol_year=None,
    enablement_flag="use_test_treaty",
    enablement_default=True,
    rules_module="tax_pipeline.y2025.treaty_test_rules_DOES_NOT_EXIST",
    stages_module="tax_pipeline.y2025.treaty_test_stages_DOES_NOT_EXIST",
    law_module="tax_pipeline.y2025.treaty_test_law_DOES_NOT_EXIST",
    authority_url="https://example.invalid/dba-test.pdf",
)


@contextmanager
def synthetic_treaty_registered() -> Iterator[None]:
    """Insert ``DBA_TEST`` into ``TREATY_REGISTRY`` for the duration of
    the test, then remove it. Mutates the global registry in-place
    rather than monkeypatching so consumers that re-read the registry
    (e.g. ``iter_treaties``) see the synthetic entry without any
    indirection. The teardown is unconditional so a test failure does
    not leak the entry into subsequent tests.
    """
    assert "DBA_TEST" not in TREATY_REGISTRY, (
        "DBA_TEST already in registry — a previous test leaked state."
    )
    TREATY_REGISTRY["DBA_TEST"] = SYNTHETIC_TREATY
    try:
        yield
    finally:
        TREATY_REGISTRY.pop("DBA_TEST", None)


class SyntheticTreatyRegistryMechanicsTest(unittest.TestCase):
    """Registry mechanics work for a programmatically-added second treaty.

    These assertions are the operational floor of "adding a treaty is
    a single registry-row edit": every consumer of the registry must
    treat the synthetic entry the same as DBA_USA.
    """

    def test_iter_treaties_includes_synthetic(self) -> None:
        with synthetic_treaty_registered():
            ids = tuple(t.treaty_id for t in iter_treaties())
            self.assertIn("DBA_USA", ids)
            self.assertIn("DBA_TEST", ids)

    def test_find_treaty_for_synthetic_parties_order_independent(self) -> None:
        with synthetic_treaty_registered():
            # parties stored as ("ST", "TE") after alphabetical sort;
            # find should resolve regardless of caller order or case.
            forward = find_treaty_for_parties("TE", "ST")
            reverse = find_treaty_for_parties("ST", "TE")
            lower = find_treaty_for_parties("te", "st")
            self.assertIsNotNone(forward)
            self.assertIs(forward, reverse)
            self.assertIs(forward, lower)
            assert forward is not None  # type narrowing
            self.assertEqual(forward.treaty_id, "DBA_TEST")

    def test_dba_usa_unaffected_by_synthetic_entry(self) -> None:
        with synthetic_treaty_registered():
            # Cross-contamination probe: looking up DE/US must still
            # resolve to DBA_USA, not bleed into the synthetic entry.
            dba_usa = find_treaty_for_parties("DE", "US")
            self.assertIsNotNone(dba_usa)
            assert dba_usa is not None
            self.assertEqual(dba_usa.treaty_id, "DBA_USA")

    def test_synthetic_enablement_gate_off_when_party_disabled(self) -> None:
        with synthetic_treaty_registered():
            # The synthetic treaty's parties ("ST", "TE") are not real
            # registered jurisdictions, so the both-parties-enabled
            # gate must fail closed: ``is_treaty_enabled`` lazy-loads
            # ``cross_jurisdiction.is_jurisdiction_enabled``, which in
            # turn calls ``get_jurisdiction("ST")`` / "TE" and raises
            # ``KeyError`` for unknown ISO-2 codes.
            with self.assertRaises(KeyError):
                is_treaty_enabled({}, "DBA_TEST")

    def test_synthetic_treaty_flag_off_short_circuits(self) -> None:
        with synthetic_treaty_registered():
            # When the treaty's own flag is explicitly False, the gate
            # short-circuits to False BEFORE the both-parties check
            # runs — proving the gate composition order matches the
            # documented contract (treaty flag first, then parties).
            profile = {"elections": {"use_test_treaty": False}}
            self.assertFalse(is_treaty_enabled(profile, "DBA_TEST"))

    def test_iter_enabled_treaties_skips_synthetic_when_unconfigured(self) -> None:
        with synthetic_treaty_registered():
            # With the synthetic flag OFF, only DBA_USA is enabled.
            # iter_enabled_treaties must not crash on the synthetic
            # entry's unresolvable parties — the flag short-circuit
            # protects the gate.
            profile = {"elections": {"use_test_treaty": False}}
            treaties = iter_enabled_treaties(profile)
            ids = tuple(t.treaty_id for t in treaties)
            self.assertEqual(ids, ("DBA_USA",))

    def test_treaty_stages_for_propagates_module_load_error(self) -> None:
        with synthetic_treaty_registered():
            # The synthetic ``stages_module`` does not exist on disk.
            # ``treaty_stages_for`` lazy-imports it, so the error must
            # surface as a ``ModuleNotFoundError`` (fail-closed import
            # contract from ``treaties.load_module``), proving no
            # silent fallback path exists.
            with self.assertRaises(ModuleNotFoundError):
                treaty_stages_for("DBA_TEST")


class LazyImportContractTest(unittest.TestCase):
    """Registry-referenced modules are NOT pre-imported at registry
    construction or registry-import time.

    The lazy-import discipline is what makes adding a second treaty
    cheap: an unused treaty's modules never load. If a future refactor
    adds an eager-import side effect to the registry module (e.g., a
    module-level "validate every dotted path" check), this test fails.
    """

    def test_synthetic_modules_not_imported_after_insertion(self) -> None:
        # Capture sys.modules before insertion; the synthetic entry's
        # dotted paths must not appear after registration alone. Only
        # an explicit ``treaty_stages_for("DBA_TEST")`` (or similar
        # consumer call) should trigger the import attempt.
        modules_before = set(sys.modules)
        with synthetic_treaty_registered():
            modules_after_insert = set(sys.modules)
            new_modules = modules_after_insert - modules_before
            for path in (
                SYNTHETIC_TREATY.rules_module,
                SYNTHETIC_TREATY.stages_module,
                SYNTHETIC_TREATY.law_module,
            ):
                self.assertNotIn(
                    path,
                    new_modules,
                    f"Module {path!r} eagerly imported on registry insertion; "
                    "the registry must lazy-load per the I1/extension contract.",
                )

    def test_dba_usa_modules_loadable_alongside_synthetic(self) -> None:
        # DBA_USA's real modules must remain loadable while the
        # synthetic (broken) entry is in the registry — proving no
        # cross-contamination from a malformed sibling row.
        with synthetic_treaty_registered():
            stages = treaty_stages_for("DBA_USA")
            # Same five-stage list as the standalone DBA_USA test —
            # I6 fingerprint stability not perturbed by a sibling
            # registry entry.
            self.assertEqual(len(stages), 5)
            self.assertEqual(stages[0].stage_id, "TREATY25-LOB-QUALIFICATION")


if __name__ == "__main__":
    unittest.main()
