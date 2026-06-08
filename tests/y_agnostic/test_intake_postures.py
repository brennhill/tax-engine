"""Tests for the intake posture/election registry (Wave 5).

CLAUDE.md tax-rule requirements: every posture must cite the controlling
authority. These tests are the structural guard rails for the registry
itself — registry shape, citation formatting, validation semantics, and
HTTP round-trip — so a future contributor cannot silently land a posture
without a § citation, an option label, or a tooltip.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.intake.postures import (
    POSTURE_REGISTRY,
    PostureValidationError,
    SECTION_DE_ELECTIONS,
    SECTION_FILING_STATUS,
    SECTION_TREATY,
    SECTION_US_ELECTIONS,
    STORAGE_DE_MODEL_ASSUMPTIONS,
    STORAGE_PROFILE_JSON,
    read_posture_state,
    serialize_registry,
    validate_state,
    write_posture_state,
)
from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOT_PATTERN = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")
CITATION_PATTERN = re.compile(r"§|26 U\.S\.C\.|DBA-USA")


class PostureRegistryShapeTest(unittest.TestCase):
    """Sanity checks on every entry of POSTURE_REGISTRY."""

    def test_registry_is_non_empty(self) -> None:
        self.assertGreaterEqual(len(POSTURE_REGISTRY), 10, "Registry must cover at least the documented postures.")

    def test_keys_use_dot_notation(self) -> None:
        for field in POSTURE_REGISTRY:
            self.assertRegex(
                field.key,
                DOT_PATTERN,
                f"Posture key {field.key!r} must use lowercase dot notation.",
            )

    def test_keys_are_unique(self) -> None:
        keys = [field.key for field in POSTURE_REGISTRY]
        self.assertEqual(len(keys), len(set(keys)), "Posture keys must be unique.")

    def test_widgets_are_supported(self) -> None:
        supported = {"radio", "select", "checkbox", "text", "number"}
        for field in POSTURE_REGISTRY:
            self.assertIn(field.widget, supported, f"Posture {field.key!r} uses unsupported widget {field.widget!r}.")

    def test_radio_and_select_have_options_with_labels(self) -> None:
        for field in POSTURE_REGISTRY:
            if field.widget in {"radio", "select"}:
                self.assertGreater(len(field.options), 1, f"Posture {field.key!r} ({field.widget}) needs options.")
                for option_value, option_label in field.options:
                    self.assertTrue(option_value, f"Posture {field.key!r} has empty option value.")
                    self.assertTrue(option_label, f"Posture {field.key!r} option {option_value!r} has empty label.")

    def test_tooltips_cite_authority(self) -> None:
        # CLAUDE.md: every tax-rule implementation must cite the controlling
        # legal authority. Tooltips are the user-facing surface — they must
        # mention the § or 26 U.S.C. citation.
        for field in POSTURE_REGISTRY:
            self.assertGreaterEqual(
                len(field.tooltip),
                30,
                f"Posture {field.key!r} tooltip is too short.",
            )
            self.assertRegex(
                field.tooltip,
                CITATION_PATTERN,
                f"Posture {field.key!r} tooltip must cite a § or 26 U.S.C. authority.",
            )

    def test_legal_refs_present(self) -> None:
        for field in POSTURE_REGISTRY:
            self.assertGreater(
                len(field.legal_refs),
                0,
                f"Posture {field.key!r} must declare at least one legal_refs entry.",
            )

    def test_legal_urls_use_official_sources(self) -> None:
        # CLAUDE.md: prefer official sources (IRS, Treasury, BMF,
        # Gesetze-im-Internet, ELSTER/BMF instructions, Cornell/Cornell-LII
        # for U.S. Code).
        official_hosts = (
            "gesetze-im-internet.de",
            "law.cornell.edu",
            "uscode.house.gov",
            "irs.gov",
            "ssa.gov",
            "bundesfinanzministerium.de",
            "bgbl.de",
            "bmf.gv.at",
        )
        for field in POSTURE_REGISTRY:
            for url in field.legal_urls:
                self.assertTrue(
                    any(host in url for host in official_hosts),
                    f"Posture {field.key!r} legal_url {url!r} is not from an official source.",
                )

    def test_storage_backends_are_known(self) -> None:
        known = {"profile_json", "elections_csv", "de_model_assumptions_csv"}
        for field in POSTURE_REGISTRY:
            self.assertIn(field.storage, known)

    def test_serialize_registry_is_json_safe(self) -> None:
        serialized = serialize_registry()
        # Should round-trip through json.dumps without TypeError.
        encoded = json.dumps(serialized)
        decoded = json.loads(encoded)
        self.assertEqual(len(decoded), len(POSTURE_REGISTRY))
        self.assertIn("options", decoded[0])
        self.assertIn("requires", decoded[0])
        self.assertIn("section", decoded[0])

    def test_each_section_is_populated(self) -> None:
        sections = {field.section for field in POSTURE_REGISTRY}
        self.assertIn(SECTION_FILING_STATUS, sections)
        self.assertIn(SECTION_DE_ELECTIONS, sections)
        self.assertIn(SECTION_US_ELECTIONS, sections)
        self.assertIn(SECTION_TREATY, sections)


class PostureValidationTest(unittest.TestCase):
    """Validation semantics: requires, mutual-exclusion, value-in-options."""

    def _baseline(self) -> dict[str, object]:
        # A self-consistent baseline that satisfies every required field with
        # its default value.
        return {field.key: field.default for field in POSTURE_REGISTRY}

    def test_validate_state_accepts_baseline(self) -> None:
        normalized = validate_state(self._baseline())
        self.assertEqual(normalized["jurisdictions.germany.filing_posture"], "single")
        self.assertEqual(normalized["jurisdictions.usa.filing_posture"], "single")

    def test_validate_state_rejects_unknown_keys(self) -> None:
        baseline = self._baseline()
        baseline["bogus.key"] = "value"
        with self.assertRaises(PostureValidationError):
            validate_state(baseline)

    def test_validate_state_rejects_value_not_in_options(self) -> None:
        baseline = self._baseline()
        baseline["jurisdictions.germany.filing_posture"] = "married_split_brain"
        with self.assertRaises(PostureValidationError):
            validate_state(baseline)

    def test_validate_state_enforces_requires_precondition(self) -> None:
        # § 6013(g) joint election requires usa.filing_posture=married_joint;
        # if filing posture is single but the election is True, validation
        # must fail.
        baseline = self._baseline()
        baseline["jurisdictions.usa.filing_posture"] = "single"
        baseline["elections.elect_joint_return_with_nra_spouse"] = True
        with self.assertRaises(PostureValidationError) as cm:
            validate_state(baseline)
        self.assertIn("requires", str(cm.exception))

    def test_validate_state_passes_when_requires_is_satisfied(self) -> None:
        baseline = self._baseline()
        baseline["jurisdictions.usa.filing_posture"] = "married_joint"
        baseline["elections.elect_joint_return_with_nra_spouse"] = True
        normalized = validate_state(baseline)
        self.assertTrue(normalized["elections.elect_joint_return_with_nra_spouse"])

    def test_validate_state_coerces_checkbox_strings(self) -> None:
        baseline = self._baseline()
        baseline["elections.use_treaty_resourcing"] = "true"
        normalized = validate_state(baseline)
        self.assertIs(normalized["elections.use_treaty_resourcing"], True)


class PostureCoverageTest(unittest.TestCase):
    """Every election the engine inputs check must appear in the registry."""

    def test_engine_election_keys_are_in_registry(self) -> None:
        # CLAUDE.md "every position captured" assertion — scan the engine
        # input modules for ``elections.<key>`` lookups and require each one
        # to be represented in POSTURE_REGISTRY (or in the de-model-
        # assumptions CSV branch).
        engine_inputs = (
            PROJECT_ROOT / "tax_pipeline" / "y2025" / "germany_inputs.py",
            PROJECT_ROOT / "tax_pipeline" / "y2025" / "us_inputs.py",
        )
        # Match "elections.<key>" where <key> is identifier chars including
        # digits (e.g. ``elect_section_911_feie``). Anchor on a non-identifier
        # boundary so trailing digits are captured.
        election_pattern = re.compile(r'elections\.([a-z][a-z0-9_]+)')
        # ``elections.get(...)`` is a Python attribute access, not a posture
        # lookup; ``elections.<key>`` inside docstrings is also fine but we
        # filter ``get`` explicitly because it never names an election.
        ignored_keys = {"get", "setdefault", "pop", "items", "keys", "values"}
        engine_keys: set[str] = set()
        for path in engine_inputs:
            text = path.read_text(encoding="utf-8")
            for match in election_pattern.finditer(text):
                key = match.group(1)
                if key in ignored_keys:
                    continue
                engine_keys.add(key)

        registry_keys = {
            field.key.split(".", 1)[1]
            for field in POSTURE_REGISTRY
            if field.key.startswith("elections.")
        }

        # Engine inputs reference elections by short key; the registry uses
        # the full ``elections.<key>`` dotted path. Every engine election
        # must appear in the registry; the registry may legitimately add
        # forward-looking entries (engine_supported=False).
        missing = engine_keys - registry_keys
        self.assertFalse(
            missing,
            f"Engine input modules reference elections.{{{', '.join(sorted(missing))}}} "
            "but they are not declared in POSTURE_REGISTRY.",
        )

    def test_capital_guenstigerpruefung_is_registered(self) -> None:
        # Special case: capital_guenstigerpruefung_requested is not under
        # ``elections.`` — it lives in the de-model-assumptions CSV.
        keys = {field.key for field in POSTURE_REGISTRY}
        self.assertIn("capital_guenstigerpruefung_requested", keys)


class PostureEndpointTest(unittest.TestCase):
    """HTTP API round-trip via the existing dispatch_request pattern."""

    def test_get_postures_returns_registry(self) -> None:
        status, payload = dispatch_request(PROJECT_ROOT, "GET", "/api/postures")
        self.assertEqual(status, 200)
        self.assertIn("fields", payload)
        self.assertGreater(len(payload["fields"]), 0)
        first = payload["fields"][0]
        self.assertIn("key", first)
        self.assertIn("tooltip", first)
        self.assertIn("legal_refs", first)
        self.assertIn("section", first)

    def test_get_postures_state_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/postures/state?year=2026&workspace={workspace_root}",
            )
            self.assertEqual(status, 200)
            self.assertIn("state", payload)
            state = payload["state"]
            # Defaults from scaffold are "single" for both jurisdictions.
            self.assertEqual(state["jurisdictions.germany.filing_posture"], "single")
            self.assertEqual(state["jurisdictions.usa.filing_posture"], "single")

    def test_post_postures_state_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            updated_state: dict[str, object] = {
                field.key: field.default for field in POSTURE_REGISTRY
            }
            updated_state["elections.germany_kirchensteuer_membership"] = "none"
            updated_state["elections.use_treaty_resourcing"] = True
            updated_state["elections.us_ftc_method"] = "accrued"
            updated_state["capital_guenstigerpruefung_requested"] = "0"

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/postures/state",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "state": updated_state,
                },
            )

            self.assertEqual(status, 200, payload)
            self.assertIn("state", payload)
            persisted = payload["state"]
            self.assertEqual(persisted["elections.us_ftc_method"], "accrued")
            self.assertEqual(persisted["capital_guenstigerpruefung_requested"], "0")

            # The de-model-assumptions.csv must now contain the
            # capital_guenstigerpruefung_requested row even if scaffolding
            # did not create the file before.
            de_assumptions = paths.tax_positions_root / "de-model-assumptions.csv"
            self.assertTrue(de_assumptions.exists())
            with de_assumptions.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            keys = {(row["section"], row["key"]) for row in rows}
            self.assertIn(("capital", "capital_guenstigerpruefung_requested"), keys)

    def test_post_postures_state_rejects_invalid_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            bad_state = {field.key: field.default for field in POSTURE_REGISTRY}
            bad_state["jurisdictions.usa.filing_posture"] = "totally_made_up_status"

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/postures/state",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "state": bad_state,
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("error", payload)

    def test_post_postures_state_rejects_violating_requires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            bad_state = {field.key: field.default for field in POSTURE_REGISTRY}
            bad_state["jurisdictions.usa.filing_posture"] = "single"
            bad_state["elections.elect_joint_return_with_nra_spouse"] = True

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/postures/state",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "state": bad_state,
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("requires", payload["error"])


class PostureStorageTest(unittest.TestCase):
    """Direct tests against read_posture_state / write_posture_state."""

    def test_write_persists_to_profile_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            updated = {field.key: field.default for field in POSTURE_REGISTRY}
            updated["elections.use_treaty_resourcing"] = True
            updated["elections.acknowledges_totalization_agreement_germany_us"] = True

            write_posture_state(paths, updated)

            on_disk = json.loads(paths.profile_path.read_text(encoding="utf-8"))
            self.assertIs(on_disk["elections"]["use_treaty_resourcing"], True)
            self.assertIs(on_disk["elections"]["acknowledges_totalization_agreement_germany_us"], True)

    def test_read_after_write_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            updated = {field.key: field.default for field in POSTURE_REGISTRY}
            updated["jurisdictions.germany.filing_posture"] = "married_joint"
            updated["jurisdictions.usa.filing_posture"] = "married_joint"
            updated["elections.elect_joint_return_with_nra_spouse"] = True

            write_posture_state(paths, updated)
            state = read_posture_state(paths)

            self.assertEqual(state["jurisdictions.germany.filing_posture"], "married_joint")
            self.assertEqual(state["jurisdictions.usa.filing_posture"], "married_joint")
            self.assertIs(state["elections.elect_joint_return_with_nra_spouse"], True)

    def test_niit_joint_election_round_trip(self) -> None:
        # F-A3: elections.elect_joint_return_with_nra_spouse_for_niit is
        # the separate NIIT-only joint election under § 1411(b). It is a
        # distinct posture from the § 6013(g) joint election (only
        # meaningful when § 6013(g) is also elected) and the engine
        # consumes it via us_2025_inputs._optional_profile_bool. Confirm
        # that POSTing it to /api/postures/state and GETing back returns
        # the same value.
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            updated = {field.key: field.default for field in POSTURE_REGISTRY}
            updated["jurisdictions.usa.filing_posture"] = "married_joint"
            updated["elections.elect_joint_return_with_nra_spouse"] = True
            updated["elections.elect_joint_return_with_nra_spouse_for_niit"] = True

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/postures/state",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "state": updated,
                },
            )
            self.assertEqual(status, 200, payload)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/postures/state?year=2026&workspace={workspace_root}",
            )
            self.assertEqual(status, 200, payload)
            persisted = payload["state"]
            self.assertIs(
                persisted["elections.elect_joint_return_with_nra_spouse_for_niit"],
                True,
            )

            on_disk = json.loads(paths.profile_path.read_text(encoding="utf-8"))
            self.assertIs(
                on_disk["elections"]["elect_joint_return_with_nra_spouse_for_niit"],
                True,
            )


if __name__ == "__main__":
    unittest.main()
