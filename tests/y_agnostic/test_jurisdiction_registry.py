"""Tests for the jurisdiction registry — Proposal 2.

The registry is the single source of truth for "what jurisdictions
does the engine know about?" and "what does each one need?". These
tests assert the registry shape so a future contributor adding a
third jurisdiction (UK, FR, ...) lands a single registry row plus
the per-jurisdiction module set, not a multi-file edit across
``year_registry.py`` / ``postures/__init__.py`` / ``paths.py`` /
``cross_jurisdiction.py``.

Authority: architecture review §5 Proposal 2.
"""

from __future__ import annotations

import unittest

from tax_pipeline.core.money import Currency
from tax_pipeline.jurisdictions import (
    JURISDICTION_REGISTRY,
    JurisdictionDefinition,
    get_jurisdiction,
    get_jurisdiction_by_posture_key,
    iter_jurisdictions,
    load_module,
)


class JurisdictionRegistryShapeTest(unittest.TestCase):
    def test_registry_has_germany_and_us_entries(self) -> None:
        self.assertIn("DE", JURISDICTION_REGISTRY)
        self.assertIn("US", JURISDICTION_REGISTRY)

    def test_registry_keys_are_iso_alpha2_uppercase(self) -> None:
        for key, definition in JURISDICTION_REGISTRY.items():
            self.assertEqual(key, definition.code, f"key/code mismatch for {key!r}")
            self.assertEqual(key, key.upper(), f"key {key!r} must be uppercase")
            self.assertEqual(len(key), 2, f"key {key!r} must be ISO-2")

    def test_germany_and_us_entries_pin_their_full_field_surfaces(self) -> None:
        # Pin every field on both registry rows in a single test —
        # field-by-field assertions on each entry separately just fan
        # out the same shape check.
        de = get_jurisdiction("DE")
        self.assertEqual(de.code, "DE")
        self.assertEqual(de.display_name, "Germany")
        self.assertEqual(de.iso_alpha2, "de")
        self.assertEqual(de.raw_bucket, "de")
        self.assertEqual(de.raw_bucket_legacy, "germany")
        self.assertIs(de.primary_currency, Currency.EUR)
        self.assertEqual(de.posture_registry_key, "germany")
        self.assertEqual(de.posture_module, "tax_pipeline.postures.germany")
        self.assertEqual(de.forms_module, "tax_pipeline.forms.germany")
        self.assertEqual(de.legal_audit_module, "tax_pipeline.legal_audit.germany")

        us = get_jurisdiction("US")
        self.assertEqual(us.code, "US")
        self.assertEqual(us.display_name, "United States")
        self.assertEqual(us.iso_alpha2, "us")
        self.assertEqual(us.raw_bucket, "us")
        self.assertEqual(us.raw_bucket_legacy, "us")
        self.assertIs(us.primary_currency, Currency.USD)
        # 26 U.S.C. § 6012 — the user-facing posture flag.
        self.assertEqual(us.enablement_flag, "us_filing_required")
        self.assertTrue(us.enablement_default)
        self.assertEqual(us.posture_registry_key, "usa")
        self.assertEqual(us.posture_module, "tax_pipeline.postures.usa")
        self.assertEqual(us.forms_module, "tax_pipeline.forms.usa")
        self.assertEqual(us.legal_audit_module, "tax_pipeline.legal_audit.usa")

    def test_get_jurisdiction_normalises_case(self) -> None:
        self.assertIs(get_jurisdiction("de"), get_jurisdiction("DE"))
        self.assertIs(get_jurisdiction("Us"), get_jurisdiction("US"))

    def test_get_jurisdiction_unknown_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_jurisdiction("XX")
        self.assertIn("XX", str(ctx.exception))
        self.assertIn("Known codes", str(ctx.exception))

    def test_get_jurisdiction_by_posture_key_resolves(self) -> None:
        self.assertEqual(get_jurisdiction_by_posture_key("germany").code, "DE")
        self.assertEqual(get_jurisdiction_by_posture_key("usa").code, "US")

    def test_get_jurisdiction_by_posture_key_unknown_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_jurisdiction_by_posture_key("uk")

    def test_iter_jurisdictions_is_stable_order(self) -> None:
        order_a = tuple(d.code for d in iter_jurisdictions())
        order_b = tuple(d.code for d in iter_jurisdictions())
        self.assertEqual(order_a, order_b)
        # Germany before U.S. mirrors YearDefinition.pipeline_modules.
        self.assertEqual(order_a, ("DE", "US"))

    def test_load_module_lazy_imports(self) -> None:
        # Each registry-referenced module must import cleanly.
        for definition in iter_jurisdictions():
            load_module(definition.posture_module)
            load_module(definition.forms_module)
            load_module(definition.legal_audit_module)

    def test_definitions_are_frozen(self) -> None:
        de = get_jurisdiction("DE")
        with self.assertRaises(Exception):  # FrozenInstanceError subclass of AttributeError
            de.code = "XX"  # type: ignore[misc]

    def test_jurisdictiondefinition_dataclass_kind(self) -> None:
        de = get_jurisdiction("DE")
        self.assertIsInstance(de, JurisdictionDefinition)


class YearPathsJurisdictionAccessorsTest(unittest.TestCase):
    """Proposal 2: paths.YearPaths exposes per-jurisdiction accessors.

    The named ``germany_forms_root`` / ``usa_forms_root`` slots stay
    for backward compatibility with the AST-driven I3 invariant
    test, but new orchestration code reads via
    :meth:`YearPaths.forms_root_for` / :meth:`legal_audit_root_for`
    keyed by ISO-2 code.
    """

    def test_forms_root_for_matches_named_slot(self) -> None:
        from pathlib import Path

        from tax_pipeline.paths import YearPaths

        paths = YearPaths.for_year(Path("/tmp/example"), 2025)
        self.assertEqual(paths.forms_root_for("DE"), paths.germany_forms_root)
        self.assertEqual(paths.forms_root_for("US"), paths.usa_forms_root)

    def test_legal_audit_root_for_matches_named_slot(self) -> None:
        from pathlib import Path

        from tax_pipeline.paths import YearPaths

        paths = YearPaths.for_year(Path("/tmp/example"), 2025)
        self.assertEqual(paths.legal_audit_root_for("DE"), paths.germany_legal_audit_root)
        self.assertEqual(paths.legal_audit_root_for("US"), paths.usa_legal_audit_root)

    def test_forms_root_for_normalises_case(self) -> None:
        from pathlib import Path

        from tax_pipeline.paths import YearPaths

        paths = YearPaths.for_year(Path("/tmp/example"), 2025)
        self.assertEqual(paths.forms_root_for("de"), paths.forms_root_for("DE"))

    def test_unknown_code_fails_closed(self) -> None:
        from pathlib import Path

        from tax_pipeline.paths import YearPaths

        paths = YearPaths.for_year(Path("/tmp/example"), 2025)
        with self.assertRaises(KeyError):
            paths.forms_root_for("XX")
        with self.assertRaises(KeyError):
            paths.legal_audit_root_for("XX")


if __name__ == "__main__":
    unittest.main()
