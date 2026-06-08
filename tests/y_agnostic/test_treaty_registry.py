"""Tests for the treaty registry — Proposal 3.

The registry is the single source of truth for "what bilateral treaties
does the engine know about?" and "what does each one need?". These
tests assert the registry shape so a future contributor adding a second
treaty (DBA-Vietnam, DBA-UK, ...) lands a single registry row plus the
per-treaty rule / stage / law modules — without rewriting the existing
DBA-USA modeling.

Authority:
  * Architecture review §5 Proposal 3.
  * DBA-USA bilingual treaty text:
    https://www.irs.gov/pub/irs-trty/germany.pdf
"""

from __future__ import annotations

import unittest

from tax_pipeline.treaties import (
    TREATY_REGISTRY,
    TreatyDefinition,
    find_treaty_for_parties,
    get_treaty,
    is_treaty_enabled,
    iter_enabled_treaties,
    iter_treaties,
    load_module,
    treaty_stages_for,
)


class TreatyRegistryShapeTest(unittest.TestCase):
    """The registry today contains exactly DBA_USA in the expected shape."""

    def test_registry_has_dba_usa_entry(self) -> None:
        self.assertIn("DBA_USA", TREATY_REGISTRY)

    def test_registry_keys_are_python_identifiers(self) -> None:
        # Keys are used as both registry keys and (post-Commit-6) JSON
        # keys; underscore-separated python identifiers are required.
        for key in TREATY_REGISTRY:
            self.assertTrue(
                key.replace("_", "a").isidentifier(),
                f"treaty_id {key!r} must be a python identifier",
            )

    def test_dba_usa_entry_fields(self) -> None:
        dba_usa = get_treaty("DBA_USA")
        self.assertEqual(dba_usa.treaty_id, "DBA_USA")
        self.assertIn("Germany", dba_usa.display_name)
        self.assertIn("United States", dba_usa.display_name)
        self.assertEqual(dba_usa.short_name, "U.S.-Germany Income Tax Convention")
        # parties are alphabetically sorted (DE before US)
        self.assertEqual(dba_usa.parties, ("DE", "US"))
        self.assertEqual(dba_usa.in_force_year, 1989)
        self.assertEqual(dba_usa.last_protocol_year, 2006)
        self.assertEqual(dba_usa.enablement_flag, "use_treaty_resourcing")
        self.assertTrue(dba_usa.enablement_default)
        self.assertEqual(dba_usa.rules_module, "tax_pipeline.y2025.treaty_rules")
        self.assertEqual(dba_usa.stages_module, "tax_pipeline.y2025.treaty_stages")
        self.assertEqual(dba_usa.law_module, "tax_pipeline.y2025.treaty_law")
        # IRS-hosted bilingual treaty text — official authority per
        # CLAUDE.md "prefer official sources".
        self.assertTrue(dba_usa.authority_url.startswith("https://www.irs.gov/"))

    def test_parties_are_alphabetically_sorted(self) -> None:
        for definition in TREATY_REGISTRY.values():
            a, b = definition.parties
            self.assertLessEqual(
                a, b, f"parties {definition.parties!r} not alphabetically sorted"
            )

    def test_party_codes_are_iso2_uppercase(self) -> None:
        for definition in TREATY_REGISTRY.values():
            for party in definition.parties:
                self.assertEqual(len(party), 2, f"party {party!r} must be ISO-2")
                self.assertEqual(party, party.upper(), f"party {party!r} must be uppercase")

    def test_get_treaty_unknown_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError) as ctx:
            get_treaty("DBA_NONEXISTENT")
        self.assertIn("DBA_NONEXISTENT", str(ctx.exception))
        self.assertIn("Known treaties", str(ctx.exception))

    def test_iter_treaties_is_stable_order(self) -> None:
        order_a = tuple(t.treaty_id for t in iter_treaties())
        order_b = tuple(t.treaty_id for t in iter_treaties())
        self.assertEqual(order_a, order_b)
        # Today only DBA_USA — protect against accidental P3-followup
        # registrations that should be standalone PRs.
        self.assertEqual(order_a, ("DBA_USA",))

    def test_definition_is_frozen(self) -> None:
        dba_usa = get_treaty("DBA_USA")
        with self.assertRaises(Exception):
            dba_usa.treaty_id = "DBA_OTHER"  # type: ignore[misc]

    def test_load_module_lazy_imports(self) -> None:
        # Each registry-referenced module must import cleanly.
        for definition in iter_treaties():
            load_module(definition.rules_module)
            load_module(definition.stages_module)
            load_module(definition.law_module)


class FindTreatyForPartiesTest(unittest.TestCase):
    """``find_treaty_for_parties`` is order-independent and case-insensitive."""

    def test_find_dba_usa_is_order_and_case_insensitive(self) -> None:
        # Case + party-order both must round-trip to the same registry row.
        # Using assertIs tests identity → the lookup returns the singleton
        # registered TreatyDefinition rather than constructing a new copy.
        canonical = find_treaty_for_parties("DE", "US")
        self.assertIsNotNone(canonical)
        assert canonical is not None  # for type narrowing
        self.assertEqual(canonical.treaty_id, "DBA_USA")
        self.assertIs(find_treaty_for_parties("US", "DE"), canonical)
        self.assertIs(find_treaty_for_parties("de", "us"), canonical)

    def test_find_unknown_pair_returns_none(self) -> None:
        # No DBA-Vietnam in the registry today.
        self.assertIsNone(find_treaty_for_parties("DE", "VN"))
        self.assertIsNone(find_treaty_for_parties("UK", "FR"))


class IsTreatyEnabledTest(unittest.TestCase):
    """The enablement gate combines the treaty flag with both parties' status."""

    def test_dba_usa_enabled_by_default(self) -> None:
        # A profile with no elections at all yields the registry default
        # (True) AND both jurisdictions default-enabled — so DBA_USA on.
        self.assertTrue(is_treaty_enabled({}, "DBA_USA"))
        self.assertTrue(is_treaty_enabled({"elections": {}}, "DBA_USA"))

    def test_dba_usa_disabled_when_treaty_flag_false(self) -> None:
        profile = {"elections": {"use_treaty_resourcing": False}}
        self.assertFalse(is_treaty_enabled(profile, "DBA_USA"))

    def test_dba_usa_disabled_when_us_party_disabled(self) -> None:
        # I13: when the U.S. side is opted out under 26 U.S.C. § 6012,
        # DBA-USA must be inapplicable regardless of the treaty flag.
        profile = {
            "elections": {
                "us_filing_required": False,
                "use_treaty_resourcing": True,
            }
        }
        self.assertFalse(is_treaty_enabled(profile, "DBA_USA"))

    def test_dba_usa_disabled_when_de_party_disabled(self) -> None:
        # Symmetric — if Germany were opted out, the treaty between
        # DE-US has no German-side surface either.
        profile = {
            "elections": {
                "germany_filing_required": False,
                "use_treaty_resourcing": True,
            }
        }
        self.assertFalse(is_treaty_enabled(profile, "DBA_USA"))

    def test_dba_usa_coerces_string_flag(self) -> None:
        # Legacy CSV-sync path serializes booleans as strings; the
        # treaty gate must coerce identically to the jurisdiction gate.
        self.assertFalse(
            is_treaty_enabled(
                {"elections": {"use_treaty_resourcing": "false"}}, "DBA_USA"
            )
        )
        self.assertTrue(
            is_treaty_enabled(
                {"elections": {"use_treaty_resourcing": "true"}}, "DBA_USA"
            )
        )

    def test_unknown_treaty_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            is_treaty_enabled({}, "DBA_NONEXISTENT")


class IterEnabledTreatiesTest(unittest.TestCase):
    """``iter_enabled_treaties`` fans the gate over the registry."""

    def test_default_profile_yields_dba_usa(self) -> None:
        treaties = iter_enabled_treaties({})
        self.assertEqual(tuple(t.treaty_id for t in treaties), ("DBA_USA",))

    def test_us_opted_out_yields_empty(self) -> None:
        # I13 is enforced through the per-treaty parties check.
        treaties = iter_enabled_treaties({"elections": {"us_filing_required": False}})
        self.assertEqual(treaties, ())

    def test_treaty_flag_off_yields_empty(self) -> None:
        treaties = iter_enabled_treaties(
            {"elections": {"use_treaty_resourcing": False}}
        )
        self.assertEqual(treaties, ())


class TreatyStagesForTest(unittest.TestCase):
    """``treaty_stages_for`` resolves the per-treaty stages module."""

    def test_dba_usa_returns_lob_first_then_treaty25_15_to_18(self) -> None:
        # Five stages today: LOB + 15..18; LOB qualification heads the
        # graph (I6: stage IDs fingerprint identically). The TREATY25-
        # prefix is the namespacing contract for I6.
        stages = treaty_stages_for("DBA_USA")
        self.assertEqual(len(stages), 5)
        self.assertEqual(stages[0].stage_id, "TREATY25-LOB-QUALIFICATION")
        for stage in stages:
            self.assertTrue(
                stage.stage_id.startswith("TREATY25-"),
                f"Stage id {stage.stage_id!r} does not start with 'TREATY25-'.",
            )

    def test_unknown_treaty_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            treaty_stages_for("DBA_NONEXISTENT")


class TreatyDefinitionExtensionShapeTest(unittest.TestCase):
    """A new TreatyDefinition has all required fields for a future treaty."""

    def test_definition_supports_full_field_set(self) -> None:
        # If a future P3 cleanup removes a field from
        # TreatyDefinition, this test fails — protecting the extension
        # surface contract for downstream consumers (a registered
        # DBA-Vietnam, etc.).
        synthetic = TreatyDefinition(
            treaty_id="DBA_TEST",
            display_name="Test Convention Between Country A and Country B",
            short_name="A-B Test Treaty",
            parties=("AA", "BB"),
            in_force_year=2025,
            last_protocol_year=None,
            enablement_flag="use_test_treaty",
            enablement_default=False,
            rules_module="tax_pipeline.y2025.treaty_test_rules",
            stages_module="tax_pipeline.y2025.treaty_test_stages",
            law_module="tax_pipeline.y2025.treaty_test_law",
            authority_url="https://example.invalid/treaty.pdf",
        )
        self.assertEqual(synthetic.treaty_id, "DBA_TEST")
        self.assertEqual(synthetic.parties, ("AA", "BB"))
        self.assertIsNone(synthetic.last_protocol_year)


if __name__ == "__main__":
    unittest.main()
