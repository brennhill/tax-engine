"""Tests for :mod:`tax_pipeline.profile` (F3 / W2.B / T2.3).

Covers the strict-validation contract of :class:`TaxpayerProfile`:

- the 3 actual workspace profiles load successfully (regression net
  for the migration);
- structural defects fail closed at load time:
    * unknown top-level key;
    * unknown ``elections.<key>`` (the ``us_filing_requried`` (sic)
      defect class);
    * ``person_slots[*].kap_lines`` entry not declared in the Anlage
      KAP TOML schema (the 2026-05-10 review §91-97 defect class);
    * missing required field type;
    * schema_version mismatch;
- ``profile_dict_for_embedding`` strips ``schema_version`` so the
  embedded ``germany.forms.profile`` block in
  ``final-legal-output.json`` is byte-identical to today's on-disk
  profile.json (preserves the workspace md5s pinned in
  ``tests/test_money_type.py``).

Stdlib-only.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tax_pipeline.profile import (
    PROFILE_SCHEMA_VERSION,
    TaxpayerProfile,
    profile_dict_for_embedding,
)


# Canonical workspace profile fixture — mirrors the demo-2025 shape
# closely so each defect-class test starts from a known-good baseline.
_VALID_PROFILE: dict = {
    "schema_version": 1,
    "profile": "synthetic_demo",
    "description": "fixture for test_profile_schema",
    "tax_year": 2025,
    "employment_country": "DE",
    "employment_city": "Berlin",
    "primary_tax_residence": "DE",
    "us_citizen_or_long_term_resident": True,
    "german_return": {
        "required": True,
        "assume_joint_assessment_if_married": False,
        "person_slots": [
            {
                "slot": "person_1",
                "order_label": "Person 1",
                "display_name": "Alex North",
                "owner": "person_1",
                "anlage_n_label": "Anlage N (Person 1)",
                "anlage_kap_label": "Anlage KAP - Person 1",
                "kap_lines": ["17", "19", "20"],
                "kap_raw_lines": [],
                "kap_posture": "single",
                "kap_notes": [],
            }
        ],
    },
    "us_return": {
        "required": True,
        "default_filing_status_if_spouse_is_nonresident_alien": "",
        "treaty_resourcing_common": True,
    },
    "jurisdictions": {
        "germany": {"enabled": True, "filing_posture": "single"},
        "usa": {"enabled": True, "filing_posture": "single"},
    },
    "investment_defaults": {
        "primary_broker_country": "US",
        "other_stock_countries_allowed": True,
        "crypto_supported": False,
        "real_estate_supported": False,
    },
    "taxpayer": {
        "name": "Alex North",
        "citizenship": ["US", "DE"],
        "germany_tax_resident": True,
    },
    "spouse": {"name": "", "us_tax_status": ""},
    "household": {
        "marital_status_on_dec_31": "single",
        "germany_filing_status": "single",
        "us_filing_status": "single",
    },
    "elections": {
        "us_ftc_method": "accrued",
        "use_treaty_resourcing": True,
        "germany_kirchensteuer_membership": "none",
        "elect_section_911_feie": False,
        "acknowledges_totalization_agreement_germany_us": True,
    },
    "raw_buckets": ["germany", "brokers"],
}


class ValidProfileTest(unittest.TestCase):
    """Happy path — the fixture loads to the expected dataclass."""

    def test_valid_dict_loads(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        self.assertEqual(profile.schema_version, PROFILE_SCHEMA_VERSION)
        self.assertEqual(profile.profile, "synthetic_demo")
        self.assertEqual(profile.tax_year, 2025)
        self.assertEqual(profile.primary_tax_residence, "DE")
        self.assertTrue(profile.us_citizen_or_long_term_resident)
        self.assertIsNotNone(profile.german_return)
        self.assertEqual(len(profile.german_return.person_slots), 1)
        slot = profile.german_return.person_slots[0]
        self.assertEqual(slot.slot, "person_1")
        self.assertEqual(slot.kap_lines, ("17", "19", "20"))
        self.assertEqual(profile.get_election("us_ftc_method"), "accrued")

    def test_from_json_round_trips_via_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(
                json.dumps(_VALID_PROFILE, indent=2), encoding="utf-8"
            )
            profile = TaxpayerProfile.from_json(path)
            self.assertEqual(profile.profile, "synthetic_demo")

    def test_workspace_profiles_load_successfully(self) -> None:
        """Regression net: all 3 actual workspace profiles must load.

        This is the F3 promotion guarantee — adding the typed loader
        does not change the legal semantics of the existing
        workspaces. The brenn-2025 path is gitignored on the public
        tree; this test skips it cleanly when the file is absent.
        """
        repo_root = Path(__file__).resolve().parents[2]
        for ws in ("brenn-2025", "demo-2025", "de-only-demo-2025"):
            profile_path = repo_root / "years" / ws / "config" / "profile.json"
            if not profile_path.exists():
                # brenn-2025 is gitignored on the public tree.
                continue
            with self.subTest(workspace=ws):
                profile = TaxpayerProfile.from_json(profile_path)
                self.assertEqual(profile.schema_version, 1)
                # Every workspace has a German return today.
                self.assertIsNotNone(profile.german_return)


class TypoDefenseTest(unittest.TestCase):
    """Structural defects must fail closed at load time."""

    def _profile(self) -> dict:
        return deepcopy(_VALID_PROFILE)

    def test_unknown_top_level_key_fails(self) -> None:
        profile = self._profile()
        profile["extra_top_level_key"] = "oops"
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("unknown key", str(ctx.exception).lower())
        self.assertIn("extra_top_level_key", str(ctx.exception))

    def test_unknown_elections_key_fails(self) -> None:
        """The us_filing_requried (sic) defect class.

        A typo'd election name slips through dict-based access today;
        the typed loader rejects it with the closed set.
        """
        profile = self._profile()
        profile["elections"]["us_filing_requried"] = True  # noqa: typo
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("us_filing_requried", str(ctx.exception))
        # The closed set is surfaced for the user.
        self.assertIn("us_filing_required", str(ctx.exception))

    def test_invalid_kap_lines_entry_fails(self) -> None:
        """The 2026-05-10 review §91-97 defect class.

        A typo'd Anlage KAP Zeile (e.g. "99" or "17a") in a
        hand-edited profile would survive year-over-year today; the
        typed loader rejects it with a pointer to the schema file.
        """
        profile = self._profile()
        profile["german_return"]["person_slots"][0]["kap_lines"] = ["99"]
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        msg = str(ctx.exception)
        self.assertIn("99", msg)
        self.assertIn("anlage_kap", msg.lower())
        # The valid set is surfaced for the user.
        self.assertIn("17", msg)

    def test_kap_lines_must_be_list_of_strings(self) -> None:
        profile = self._profile()
        profile["german_return"]["person_slots"][0]["kap_lines"] = [17]
        with self.assertRaises(ValueError):
            TaxpayerProfile.from_dict(profile)

    def test_missing_required_field_fails_when_wrong_type(self) -> None:
        """Wrong type on a required field fails closed."""
        profile = self._profile()
        profile["us_citizen_or_long_term_resident"] = "yes"  # must be bool
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("us_citizen_or_long_term_resident", str(ctx.exception))

    def test_unknown_nested_key_in_jurisdictions_fails(self) -> None:
        profile = self._profile()
        profile["jurisdictions"]["germany"]["typo_field"] = "x"
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("typo_field", str(ctx.exception))

    def test_unknown_person_slot_key_fails(self) -> None:
        profile = self._profile()
        profile["german_return"]["person_slots"][0]["mystery_field"] = "x"
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("mystery_field", str(ctx.exception))

    def test_schema_version_mismatch_fails(self) -> None:
        profile = self._profile()
        profile["schema_version"] = 99
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("schema_version", str(ctx.exception))

    def test_top_level_must_be_object(self) -> None:
        with self.assertRaises(ValueError):
            TaxpayerProfile.from_dict([1, 2, 3])

    def test_unknown_joint_prereq_key_fails(self) -> None:
        profile = self._profile()
        profile["german_return"]["joint_assessment_prerequisites"] = {
            "married_or_registered_partners": True,
            "typo_field": True,
        }
        with self.assertRaises(ValueError) as ctx:
            TaxpayerProfile.from_dict(profile)
        self.assertIn("typo_field", str(ctx.exception))


class EmbeddingTest(unittest.TestCase):
    """The dict-for-embedding view must preserve the on-disk shape.

    This is the md5-stability guarantee: adding ``schema_version: 1``
    to profile.json does NOT change the byte shape of the embedded
    ``germany.forms.profile`` field in ``final-legal-output.json``.
    """

    def test_embedding_strips_schema_version(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        embedded = profile_dict_for_embedding(profile)
        self.assertNotIn("schema_version", embedded)

    def test_embedding_round_trips_under_canonical_json(self) -> None:
        """The dict view must equal the on-disk JSON shape (minus schema_version).

        Compared via canonical-JSON (sort_keys + indent), which is the
        form ``write_final_legal_output_2025`` uses to serialise
        ``final-legal-output.json``.
        """
        on_disk = deepcopy(_VALID_PROFILE)
        on_disk_no_schema = {
            k: v for k, v in on_disk.items() if k != "schema_version"
        }
        profile = TaxpayerProfile.from_dict(on_disk)
        embedded = profile_dict_for_embedding(profile)
        self.assertEqual(
            json.dumps(on_disk_no_schema, indent=2, sort_keys=True),
            json.dumps(embedded, indent=2, sort_keys=True),
        )

    def test_workspace_profiles_round_trip_canonical(self) -> None:
        """Each actual workspace profile.json must canonical-JSON
        match its typed embedding (minus schema_version).

        This is the contract preserving the workspace md5s:
        ``final-legal-output.json`` embeds ``germany.forms.profile``
        as ``profile_dict_for_embedding(typed_profile)``, which is
        canonical-JSON identical to the on-disk profile.json minus
        the ``schema_version`` field.
        """
        repo_root = Path(__file__).resolve().parents[2]
        for ws in ("brenn-2025", "demo-2025", "de-only-demo-2025"):
            profile_path = repo_root / "years" / ws / "config" / "profile.json"
            if not profile_path.exists():
                continue
            with self.subTest(workspace=ws):
                on_disk = json.loads(profile_path.read_text(encoding="utf-8"))
                on_disk_no_schema = {
                    k: v for k, v in on_disk.items() if k != "schema_version"
                }
                profile = TaxpayerProfile.from_json(profile_path)
                embedded = profile_dict_for_embedding(profile)
                self.assertEqual(
                    json.dumps(on_disk_no_schema, indent=2, sort_keys=True),
                    json.dumps(embedded, indent=2, sort_keys=True),
                )


class ConvenienceAccessorsTest(unittest.TestCase):
    """The dataclass exposes the convenience accessors the brief
    listed (``is_jurisdiction_enabled``, ``kap_lines_for``,
    ``get_election``)."""

    def test_is_jurisdiction_enabled(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        self.assertTrue(profile.is_jurisdiction_enabled("US"))
        self.assertTrue(profile.is_jurisdiction_enabled("DE"))

    def test_is_jurisdiction_enabled_respects_opt_out(self) -> None:
        # 26 U.S.C. § 6012 — opt-out posture; the typed object resolves
        # the same way as the dict-based reader.
        profile_dict = deepcopy(_VALID_PROFILE)
        profile_dict["elections"]["us_filing_required"] = False
        profile = TaxpayerProfile.from_dict(profile_dict)
        self.assertFalse(profile.is_jurisdiction_enabled("US"))
        self.assertTrue(profile.is_jurisdiction_enabled("DE"))

    def test_kap_lines_for_known_slot(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        self.assertEqual(profile.kap_lines_for("person_1"), ("17", "19", "20"))

    def test_kap_lines_for_unknown_slot_fails(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        with self.assertRaises(KeyError):
            profile.kap_lines_for("person_99")

    def test_get_election_default(self) -> None:
        profile = TaxpayerProfile.from_dict(deepcopy(_VALID_PROFILE))
        self.assertEqual(
            profile.get_election("not_a_real_key", "fallback"),
            "fallback",
        )


class NullableFieldsTest(unittest.TestCase):
    """Round-trip null values from the DEFAULT_PROFILE shape.

    The ``DEFAULT_PROFILE`` in ``tax_pipeline.scaffold_year`` ships
    placeholder ``null`` values for unfilled electives and
    ``owner: null`` in person_slots. The typed loader must accept
    them without modification so byte-stability survives.
    """

    def test_null_election_values_preserved(self) -> None:
        profile_dict = deepcopy(_VALID_PROFILE)
        profile_dict["elections"]["use_treaty_resourcing"] = None
        profile = TaxpayerProfile.from_dict(profile_dict)
        self.assertIsNone(profile.get_election("use_treaty_resourcing"))

    def test_null_owner_in_person_slot_preserved(self) -> None:
        profile_dict = deepcopy(_VALID_PROFILE)
        profile_dict["german_return"]["person_slots"][0]["owner"] = None
        profile = TaxpayerProfile.from_dict(profile_dict)
        slot = profile.german_return.person_slots[0]
        self.assertIsNone(slot.owner)


if __name__ == "__main__":
    unittest.main()
