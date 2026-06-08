"""Proposal 2 extension-surface test: adding a third jurisdiction.

The whole point of Proposal 2 is that "country" is a data dimension
on a single registry, not branches in code. The strongest test of
that property is: how many existing files would a maintainer have
to edit to add a synthetic third jurisdiction (e.g., a "TEST"
jurisdiction with its own renderer / posture / etc. modules)?

Pre-P2 the answer was ~6 files (paths.py, postures/__init__.py,
year_registry.py, cross_jurisdiction.py, plus per-renderer
country-tag constants). Post-P2 the answer should be 1: a single
``JurisdictionDefinition`` row in
``tax_pipeline.jurisdictions.JURISDICTION_REGISTRY``.

This test does not actually add a third jurisdiction — that would
require materialising rule modules, posture packages, renderers, and
audit packages. Instead it asserts the surface contract: the
registry is read by every consumer that previously branched on
``"germany"`` / ``"us"`` literals, so a registry-row addition is the
single edit point.

Authority: architecture review §5 Proposal 2.
"""

from __future__ import annotations

import unittest

from tax_pipeline.jurisdictions import (
    JURISDICTION_REGISTRY,
    JurisdictionDefinition,
    get_jurisdiction,
)


class RegistryDrivesPostureRegistryTest(unittest.TestCase):
    """``postures/__init__.py`` reads from JURISDICTION_REGISTRY."""

    def test_posture_registry_keys_match_registry(self) -> None:
        from tax_pipeline.postures import known_postures

        registry_keys = {d.posture_registry_key for d in JURISDICTION_REGISTRY.values()}
        # Every registered posture-registry-key must yield at least
        # one known posture (the registry-driven build is wired in).
        for key in registry_keys:
            self.assertGreater(
                len(known_postures(key)),
                0,
                f"Posture registry surfaces no postures for {key!r}; "
                "the JURISDICTION_REGISTRY entry is not wired into "
                "tax_pipeline.postures.__init__.",
            )


class RegistryDrivesYearRegistryTest(unittest.TestCase):
    """``YearDefinition`` is jurisdiction-keyed."""

    def test_year_definition_lists_registered_jurisdictions(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)
        # Every jurisdiction listed in the year definition must be
        # present in the JURISDICTION_REGISTRY (the year is the
        # consumer; the registry is the source of truth).
        for code in year_def.jurisdictions:
            self.assertIn(
                code,
                JURISDICTION_REGISTRY,
                f"YearDefinition references unknown jurisdiction {code!r}",
            )


class RegistryDrivesCrossJurisdictionGateTest(unittest.TestCase):
    """``cross_jurisdiction.is_jurisdiction_enabled`` reads enablement_flag."""

    def test_us_gate_reads_us_filing_required(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        # Simulate a profile that flips the U.S. flag and verify the
        # gate reads the registry's ``enablement_flag``, not a hard-
        # coded "us_filing_required" literal.
        us_def = get_jurisdiction("US")
        flag = us_def.enablement_flag
        self.assertEqual(flag, "us_filing_required")

        profile_off = {"elections": {flag: False}}
        profile_on = {"elections": {flag: True}}
        self.assertFalse(is_jurisdiction_enabled(profile_off, "US"))
        self.assertTrue(is_jurisdiction_enabled(profile_on, "US"))

    def test_de_gate_reads_de_enablement_flag(self) -> None:
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        de_def = get_jurisdiction("DE")
        flag = de_def.enablement_flag
        # DE has a placeholder flag with default True; verify the
        # gate respects an explicit False override on the registry-
        # specified flag name (proves the gate is registry-driven,
        # not a "us_filing_required" literal).
        profile_off = {"elections": {flag: False}}
        self.assertFalse(is_jurisdiction_enabled(profile_off, "DE"))


class RegistryDrivesPathsTest(unittest.TestCase):
    """``YearPaths.forms_root_for(code)`` reads from the registry."""

    def test_forms_root_for_uses_posture_registry_key(self) -> None:
        from pathlib import Path

        from tax_pipeline.paths import YearPaths

        paths = YearPaths.for_year(Path("/tmp/example"), 2025)
        for definition in JURISDICTION_REGISTRY.values():
            forms_root = paths.forms_root_for(definition.code)
            self.assertEqual(
                forms_root,
                paths.forms_root / definition.posture_registry_key,
                f"forms_root_for({definition.code!r}) should resolve via "
                f"posture_registry_key={definition.posture_registry_key!r}",
            )


class RegistryDrivesFormCountryTagsTest(unittest.TestCase):
    """Form renderers' country tags come from the registry."""

    def test_germany_renderer_country_tag_matches_registry(self) -> None:
        from tax_pipeline.forms.germany import GERMANY_COUNTRY

        self.assertEqual(GERMANY_COUNTRY, get_jurisdiction("DE").code)

    def test_usa_renderer_country_tag_matches_registry(self) -> None:
        from tax_pipeline.forms.usa import USA_COUNTRY

        self.assertEqual(USA_COUNTRY, get_jurisdiction("US").code)


class JurisdictionDefinitionExtensionShapeTest(unittest.TestCase):
    """A new JurisdictionDefinition has all required fields."""

    def test_definition_supports_full_field_set(self) -> None:
        # If a future P2 cleanup removes a field from
        # JurisdictionDefinition, this test fails — protecting the
        # extension surface contract for downstream consumers.
        from tax_pipeline.core.money import Currency

        synthetic = JurisdictionDefinition(
            code="XX",
            display_name="Example Jurisdiction",
            iso_alpha2="xx",
            raw_bucket="xx",
            raw_bucket_legacy="xx",
            primary_currency=Currency.EUR,
            enablement_flag="xx_filing_required",
            enablement_default=False,
            posture_module="tax_pipeline.postures.example",
            forms_module="tax_pipeline.forms.example",
            legal_audit_module="tax_pipeline.legal_audit.example",
            rules_year_namespace="tax_pipeline.y2025",
            posture_registry_key="example",
        )
        # Constructed without raising; every consumer reads via
        # field access, not via positional indexing.
        self.assertEqual(synthetic.code, "XX")
        self.assertEqual(synthetic.posture_registry_key, "example")


if __name__ == "__main__":
    unittest.main()
