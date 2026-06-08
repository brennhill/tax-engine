from __future__ import annotations

import unittest


class PostureRegistryTest(unittest.TestCase):
    def test_known_postures_are_registered(self) -> None:
        from tax_pipeline.postures import get_posture_definition

        germany = get_posture_definition("germany", "married_joint")
        usa = get_posture_definition("usa", "mfs_nra_spouse")

        self.assertEqual(germany.jurisdiction, "germany")
        self.assertEqual(germany.filing_posture, "married_joint")
        self.assertEqual(usa.jurisdiction, "usa")
        self.assertEqual(usa.filing_posture, "mfs_nra_spouse")

    def test_invalid_posture_fails_loudly(self) -> None:
        from tax_pipeline.postures import get_posture_definition

        with self.assertRaisesRegex(ValueError, "Unsupported filing posture"):
            get_posture_definition("germany", "head_of_household")

    def test_posture_definition_exposes_output_surface_support(self) -> None:
        from tax_pipeline.postures import get_posture_definition

        separate = get_posture_definition("germany", "married_separate")

        self.assertEqual(separate.required_household_shape, "married")
        self.assertEqual(
            separate.module_path,
            "tax_pipeline.postures.germany.married_separate",
        )
        self.assertFalse(separate.output_support.forms)
        self.assertFalse(separate.output_support.entry_sheet)
        # § 26a Abs. 2 EStG separate-assessment allocation elections are not modeled yet, so
        # the registry must not advertise complete ordinary-law support for married_separate.
        self.assertFalse(separate.output_support.ordinary_law)

    def test_postures_expose_legal_rule_keys_not_just_output_support(self) -> None:
        from tax_pipeline.postures import get_posture_definition

        germany_joint = get_posture_definition("germany", "married_joint")
        germany_separate = get_posture_definition("germany", "married_separate")
        usa_mfs = get_posture_definition("usa", "mfs_nra_spouse")
        usa_joint = get_posture_definition("usa", "married_joint")

        self.assertTrue(hasattr(germany_joint, "legal_rule_keys"))
        self.assertIn("estg_26b_joint_aggregation", germany_joint.legal_rule_keys)
        self.assertIn("estg_26a_separate_assessment", germany_separate.legal_rule_keys)
        self.assertIn("irc_1211b_mfs_capital_loss_limit", usa_mfs.legal_rule_keys)
        self.assertIn("irc_6013g_nra_spouse_joint_election", usa_joint.legal_rule_keys)

    def test_usa_married_joint_is_registered_as_supported_runtime_posture(self) -> None:
        from tax_pipeline.postures import get_posture_definition

        joint = get_posture_definition("usa", "married_joint")

        self.assertEqual(joint.required_household_shape, "married")
        self.assertEqual(joint.module_path, "tax_pipeline.postures.usa.married_joint")
        self.assertTrue(joint.implemented)

    def test_all_supported_postures_resolve_to_dedicated_modules(self) -> None:
        from tax_pipeline.postures import known_postures

        self.assertEqual(
            known_postures("germany"),
            {
                "single": "tax_pipeline.postures.germany.single",
                "married_joint": "tax_pipeline.postures.germany.married_joint",
                "married_separate": "tax_pipeline.postures.germany.married_separate",
            },
        )
        self.assertEqual(
            known_postures("usa"),
            {
                "single": "tax_pipeline.postures.usa.single",
                "mfs_nra_spouse": "tax_pipeline.postures.usa.mfs_nra_spouse",
                "married_joint": "tax_pipeline.postures.usa.married_joint",
            },
        )


if __name__ == "__main__":
    unittest.main()
