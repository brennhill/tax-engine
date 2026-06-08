from __future__ import annotations

import unittest


class YearRegistryTest(unittest.TestCase):
    def test_2025_year_definition_is_registered(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)

        self.assertEqual(year_def.year, 2025)
        self.assertIn("tax_pipeline.pipelines.y2025.germany_model", year_def.pipeline_modules)
        self.assertIn("tax_pipeline.pipelines.y2025.us_model", year_def.pipeline_modules)
        self.assertIn("married_joint", year_def.supported_postures["usa"])

    def test_unsupported_numeric_year_fails_loudly(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        with self.assertRaisesRegex(NotImplementedError, "Only 2025"):
            get_year_definition(2026)


class YearDefinitionJurisdictionShapeTest(unittest.TestCase):
    """Proposal 2: YearDefinition is jurisdiction-keyed.

    Migrating away from named ``germany_modules`` / ``usa_modules``
    slots requires both the dict-keyed source-of-truth AND the
    backward-compatible legacy accessors continuing to work.
    """

    def test_jurisdictions_are_iso2(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)
        self.assertEqual(year_def.jurisdictions, ("DE", "US"))

    def test_jurisdiction_modules_dict_keys_match_iso2(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)
        self.assertSetEqual(set(year_def.jurisdiction_modules.keys()), {"DE", "US"})

    def test_legacy_named_accessors_match_dict(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)
        self.assertEqual(year_def.germany_modules, year_def.jurisdiction_modules["DE"])
        self.assertEqual(year_def.usa_modules, year_def.jurisdiction_modules["US"])
        self.assertEqual(
            year_def.germany_optional_modules,
            year_def.jurisdiction_optional_modules.get("DE", {}),
        )

    def test_pipeline_modules_includes_all_layers(self) -> None:
        from tax_pipeline.year_registry import get_year_definition

        year_def = get_year_definition(2025)
        modules = year_def.pipeline_modules
        # Derivation, optional germany (crypto + equity_comp_capital),
        # main germany, main usa, then report. Verify the relative
        # ordering of representative entries.
        self.assertLess(
            modules.index("tax_pipeline.pipelines.y2025.run_derivation"),
            modules.index("tax_pipeline.pipelines.y2025.coinbase_private_sales"),
        )
        self.assertLess(
            modules.index("tax_pipeline.pipelines.y2025.coinbase_private_sales"),
            modules.index("tax_pipeline.pipelines.y2025.germany_model"),
        )
        self.assertLess(
            modules.index("tax_pipeline.pipelines.y2025.germany_model"),
            modules.index("tax_pipeline.pipelines.y2025.us_model"),
        )
        self.assertLess(
            modules.index("tax_pipeline.pipelines.y2025.us_model"),
            modules.index("tax_pipeline.pipelines.y2025.final_legal_output"),
        )


if __name__ == "__main__":
    unittest.main()
