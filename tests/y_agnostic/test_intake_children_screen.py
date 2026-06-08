"""Tests for the Children & Dependents intake screen (Wave 11C).

The "children" screen captures per-child facts the engine needs for the
U.S. Child Tax Credit / Credit for Other Dependents (26 U.S.C. §§ 24,
152) and the German Kinderfreibetrag / Kindergeld Günstigerprüfung
(§§ 31, 32 EStG; BKGG § 6). One row per child in
``config/children.csv``; an empty CSV (header only) means no children,
which the engine reads as zero credits / zero Freibeträge.

CLAUDE.md tax-rule requirements: every screen field whose value enters
the engine must reach the engine through a declared field, and the
backend tooltips must cite the controlling authority. The metadata
shape, validation messages, and round-trip persistence are the
structural guard rails for that contract.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tax_pipeline.intake.screens import (
    CHILDREN_COLUMNS,
    CHILD_RELATIONSHIPS,
    KINDERGELD_RECIPIENTS,
    SCREEN_HANDLERS,
    SCREEN_TOOLTIPS,
    serialize_screen_metadata,
    write_children_state,
)
from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITATION_PATTERN = re.compile(r"§|26 U\.S\.C\.|31 U\.S\.C\.|InvStG|BKGG|DBA")


def _new_workspace(tmp: str, year: str = "2026"):
    workspace_root = Path(tmp) / year
    paths = resolve_year_paths(PROJECT_ROOT, year, workspace_root=workspace_root)
    ensure_year_scaffold(paths)
    return paths, workspace_root


def _post(path: str, body: dict[str, object]):
    return dispatch_request(PROJECT_ROOT, "POST", path, body=body)


def _get(path: str):
    return dispatch_request(PROJECT_ROOT, "GET", path)


def _disable_us_filing(paths) -> None:
    """Helper: drop the U.S. filing posture from profile.json so the
    SSN/ITIN-required validation is OFF for the rest of the test. Used
    when a test wants to assert the screen accepts a qualifying child
    without a U.S. ID (Germany-only household)."""

    text = paths.profile_path.read_text(encoding="utf-8")
    profile = json.loads(text)
    profile.setdefault("jurisdictions", {}).setdefault("usa", {})
    profile["jurisdictions"]["usa"]["enabled"] = False
    profile["jurisdictions"]["usa"]["filing_posture"] = ""
    paths.profile_path.write_text(json.dumps(profile, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Round-trip persistence
# ---------------------------------------------------------------------------


class ChildrenScreenRoundTripTest(unittest.TestCase):
    def test_post_two_children_then_get_returns_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira North",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "steuer_id": "12345678901",
                                "relationship": "qualifying_child",
                                "months_in_household": "12",
                                "kindergeld_received_eur": "3000.00",
                                "kindergeld_recipient": "taxpayer",
                            },
                            {
                                "name": "Theo North",
                                "date_of_birth": "2020-03-04",
                                "ssn": "444-55-6666",
                                "relationship": "qualifying_child",
                                "months_in_household": "12",
                                "kindergeld_received_eur": "3000.00",
                                "kindergeld_recipient": "taxpayer",
                            },
                        ]
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            kids = payload["state"]["children"]
            self.assertEqual(len(kids), 2)
            self.assertEqual(kids[0]["name"], "Mira North")
            # Hyphens stripped from SSN, like the identity screen does.
            self.assertEqual(kids[0]["ssn"], "111223333")
            self.assertEqual(kids[1]["ssn"], "444556666")
            csv_path = paths.config_root / "children.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            for column in CHILDREN_COLUMNS:
                self.assertIn(column, rows[0])

    def test_replace_full_list_drops_removed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            },
                            {
                                "name": "Theo",
                                "date_of_birth": "2020-03-04",
                                "ssn": "444-55-6666",
                                "relationship": "qualifying_child",
                            },
                        ]
                    },
                },
            )
            # Replace with a single child — the second one must disappear.
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(len(payload["state"]["children"]), 1)
            status, payload = _get(f"/api/children/state?year=2026&workspace={ws}")
            self.assertEqual(len(payload["state"]["children"]), 1)
            self.assertEqual(payload["state"]["children"][0]["name"], "Mira")

    def test_partial_save_without_children_key_leaves_csv_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            # POST with no `children` key — partial save should leave the
            # existing CSV alone (matches bank_accounts and vorabpauschale).
            status, _ = _post(
                "/api/children/state",
                body={"year": "2026", "workspace": str(ws), "state": {}},
            )
            self.assertEqual(status, 200)
            status, payload = _get(f"/api/children/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["children"][0]["name"], "Mira")

    def test_empty_list_writes_header_only_csv(self) -> None:
        # An empty CSV (header only) is what the engine reads as
        # "no children". Posting children=[] must produce that.
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"children": []},
                },
            )
            self.assertEqual(status, 200, payload)
            csv_path = paths.config_root / "children.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class ChildrenScreenValidationTest(unittest.TestCase):
    def test_bad_ssn_format_rejected_with_plain_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "12345",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            # Wave 9 plain-English standard: error must spell out the
            # actual rule (9 digits) instead of opaque "invalid".
            self.assertIn("9 digits", payload["error"])

    def test_kindergeld_recipient_none_with_nonzero_amount_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                                "kindergeld_received_eur": "3000.00",
                                "kindergeld_recipient": "none",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("kindergeld_received_eur", payload["error"])
            self.assertIn("none", payload["error"])

    def test_us_household_with_qualifying_child_requires_ssn_or_itin(self) -> None:
        # The default scaffold has the U.S. side enabled, so a
        # qualifying child without an SSN AND without an ITIN must
        # fail closed.
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("SSN", payload["error"])
            self.assertIn("ITIN", payload["error"])

    def test_germany_only_household_accepts_qualifying_child_without_us_id(self) -> None:
        # Disabling the U.S. side in profile.json must turn the
        # SSN/ITIN requirement off so a Germany-only household can
        # save a row with only the Steuer-ID.
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _disable_us_filing(paths)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "steuer_id": "12345678901",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["state"]["children"][0]["steuer_id"], "12345678901")

    def test_invalid_relationship_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "godparent",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("relationship", payload["error"])

    def test_months_in_household_out_of_range_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                                "months_in_household": "13",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("0", payload["error"])
            self.assertIn("12", payload["error"])

    def test_negative_income_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                                "annual_gross_income_eur": "-100",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("0 or greater", payload["error"])

    def test_missing_name_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("name", payload["error"].lower())

    def test_disability_gdb_out_of_range_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                                "disability_gdb": "150",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("disability_gdb", payload["error"])
            self.assertIn("100", payload["error"])

    def test_validation_failure_leaves_existing_csv_intact(self) -> None:
        # A failed write must not corrupt the on-disk CSV. We seed one
        # valid row, then submit a batch where the second row is bad;
        # the existing row must still be there afterwards.
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            csv_path = paths.config_root / "children.csv"
            prior = csv_path.read_text(encoding="utf-8")
            status, payload = _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            },
                            {
                                "name": "Bad",
                                "date_of_birth": "2018-09-12",
                                "ssn": "abc",
                                "relationship": "qualifying_child",
                            },
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertEqual(csv_path.read_text(encoding="utf-8"), prior)


# ---------------------------------------------------------------------------
# Metadata + tooltip presence (Wave 9 standard)
# ---------------------------------------------------------------------------


class ChildrenScreenMetadataTest(unittest.TestCase):
    def test_metadata_endpoint_includes_children(self) -> None:
        status, payload = _get("/api/screens/metadata")
        self.assertEqual(status, 200)
        self.assertIn("children", payload["screens"])

    def test_currency_markers_present(self) -> None:
        # Currency hints let the frontend render € / $ prefixes and
        # EUR / USD pills automatically. _eur fields → EUR; _usd → USD.
        meta = serialize_screen_metadata()["children"]
        self.assertEqual(meta["kindergeld_received_eur"]["currency"], "EUR")
        self.assertEqual(meta["annual_gross_income_eur"]["currency"], "EUR")
        self.assertEqual(meta["annual_gross_income_usd"]["currency"], "USD")
        # Non-money fields carry an empty currency so consumers can
        # detect them uniformly.
        self.assertEqual(meta["name"]["currency"], "")
        self.assertEqual(meta["ssn"]["currency"], "")
        self.assertEqual(meta["steuer_id"]["currency"], "")

    def test_every_field_has_plain_english_tooltip_with_citation(self) -> None:
        # Wave 9 standard: every field gets a tooltip ≥ 50 chars
        # leading with plain English, ending with a parenthesized
        # legal citation.
        for key, meta in SCREEN_TOOLTIPS["children"].items():
            tooltip = meta.get("tooltip", "")
            self.assertGreaterEqual(
                len(tooltip),
                50,
                f"children.{key} tooltip is too short ({len(tooltip)} chars).",
            )
            refs = meta.get("legal_refs") or ()
            self.assertGreater(
                len(refs),
                0,
                f"children.{key} must declare at least one legal_refs entry.",
            )
            self.assertRegex(
                " · ".join(refs),
                CITATION_PATTERN,
                f"children.{key} legal_refs must cite a § / 26 U.S.C. / BKGG.",
            )

    def test_screen_handler_registered(self) -> None:
        self.assertIn("children", SCREEN_HANDLERS)
        reader, writer = SCREEN_HANDLERS["children"]
        self.assertTrue(callable(reader))
        self.assertTrue(callable(writer))

    def test_relationship_and_recipient_enums_match_validation(self) -> None:
        self.assertEqual(
            CHILD_RELATIONSHIPS,
            ("qualifying_child", "qualifying_relative"),
        )
        self.assertEqual(
            KINDERGELD_RECIPIENTS,
            ("taxpayer", "spouse", "other_parent", "none"),
        )


# ---------------------------------------------------------------------------
# Atomic write: forced os.replace failure → no torn CSV
# ---------------------------------------------------------------------------


class ChildrenScreenAtomicWriteTest(unittest.TestCase):
    def test_forced_atomic_write_failure_preserves_prior_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _post(
                "/api/children/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "children": [
                            {
                                "name": "Mira",
                                "date_of_birth": "2018-09-12",
                                "ssn": "111-22-3333",
                                "relationship": "qualifying_child",
                            }
                        ]
                    },
                },
            )
            csv_path = paths.config_root / "children.csv"
            prior = csv_path.read_text(encoding="utf-8")

            with mock.patch(
                "tax_pipeline.intake.screens.atomic_write_text",
                side_effect=RuntimeError("simulated mid-write failure"),
            ):
                with self.assertRaises(RuntimeError):
                    write_children_state(
                        paths,
                        {
                            "children": [
                                {
                                    "name": "Mira",
                                    "date_of_birth": "2018-09-12",
                                    "ssn": "111-22-3333",
                                    "relationship": "qualifying_child",
                                },
                                {
                                    "name": "Theo",
                                    "date_of_birth": "2020-03-04",
                                    "ssn": "444-55-6666",
                                    "relationship": "qualifying_child",
                                },
                            ]
                        },
                    )

            # The prior CSV must be byte-for-byte intact.
            self.assertEqual(csv_path.read_text(encoding="utf-8"), prior)


if __name__ == "__main__":
    unittest.main()
