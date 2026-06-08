"""Tests for the Wave 6 partial-save intake screens.

These tests cover the five new screens added in commit 2bc5f4a (Identity,
Bank accounts, DE deductions, Vorabpauschale, Carryovers) plus the
``/api/save-all`` aggregator and the ``/api/progress`` summary.

CLAUDE.md tax-rule requirements: every screen field whose value enters
the engine must reach the engine through a declared field, and the
backend tooltips must cite the controlling authority. The metadata
shape and the round-trip persistence are the structural guard rails
for that contract.
"""

from __future__ import annotations

import csv
import json
import re
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.intake.screens import (
    BANK_ACCOUNTS_COLUMNS,
    CITIZENSHIP_OPTIONS,
    FUND_CLASSIFICATIONS,
    SCREEN_HANDLERS,
    SCREEN_NAMES,
    SCREEN_TOOLTIPS,
    SUPPORT_RELATIONSHIPS,
    VORABPAUSCHALE_COLUMNS,
    read_progress,
    serialize_screen_metadata,
)
from tax_pipeline.intake.server import dispatch_request, dispatch_response
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITATION_PATTERN = re.compile(r"§|26 U\.S\.C\.|31 U\.S\.C\.|InvStG|DBA")
OFFICIAL_HOSTS = (
    "gesetze-im-internet.de",
    "law.cornell.edu",
    "irs.gov",
    "bundesfinanzministerium.de",
)


def _new_workspace(tmp: str, year: str = "2026"):
    workspace_root = Path(tmp) / year
    paths = resolve_year_paths(PROJECT_ROOT, year, workspace_root=workspace_root)
    ensure_year_scaffold(paths)
    return paths, workspace_root


def _post(path: str, body: dict[str, object]):
    return dispatch_request(PROJECT_ROOT, "POST", path, body=body)


def _get(path: str):
    return dispatch_request(PROJECT_ROOT, "GET", path)


# ---------------------------------------------------------------------------
# Metadata + tooltip shape
# ---------------------------------------------------------------------------


class ScreenMetadataShapeTest(unittest.TestCase):
    def test_metadata_endpoint_returns_five_screens(self) -> None:
        status, payload = _get("/api/screens/metadata")
        self.assertEqual(status, 200)
        self.assertIn("screens", payload)
        self.assertEqual(set(payload["screens"].keys()), set(SCREEN_NAMES))

    def test_every_field_has_tooltip_with_citation(self) -> None:
        # CLAUDE.md: every tax-rule implementation must cite the controlling
        # authority. Tooltips are the user-facing surface; without them the
        # field would render with no § reference at all.
        for screen, fields in SCREEN_TOOLTIPS.items():
            for key, meta in fields.items():
                self.assertGreaterEqual(
                    len(meta.get("tooltip", "")),
                    20,
                    f"{screen}.{key} tooltip too short ({meta.get('tooltip', '')!r}).",
                )
                refs = meta.get("legal_refs") or ()
                self.assertGreater(
                    len(refs),
                    0,
                    f"{screen}.{key} must declare at least one legal_refs entry.",
                )
                self.assertRegex(
                    " · ".join(refs),
                    CITATION_PATTERN,
                    f"{screen}.{key} legal_refs must cite a § or 26/31 U.S.C. or InvStG.",
                )

    def test_legal_urls_use_official_sources(self) -> None:
        for screen, fields in SCREEN_TOOLTIPS.items():
            for key, meta in fields.items():
                for url in meta.get("legal_urls", ()):
                    self.assertTrue(
                        any(host in url for host in OFFICIAL_HOSTS),
                        f"{screen}.{key} legal_url {url!r} is not from an official source.",
                    )

    def test_serialized_metadata_is_json_safe(self) -> None:
        encoded = json.dumps(serialize_screen_metadata())
        decoded = json.loads(encoded)
        self.assertIn("identity", decoded)
        self.assertIn("legal_refs", decoded["identity"]["full_legal_name"])


# ---------------------------------------------------------------------------
# Identity & Employment
# ---------------------------------------------------------------------------


class IdentityScreenTest(unittest.TestCase):
    def test_round_trip_persists_taxpayer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "taxpayer": {
                            "full_legal_name": "Alex Sample",
                            "address_country": "de",
                            "us_ssn_or_itin": "123-45-6789",
                            "german_tax_id": "12345678901",
                            "date_of_birth": "1980-04-15",
                            "citizenship_status": "us_citizen",
                        }
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            taxpayer = payload["state"]["taxpayer"]
            self.assertEqual(taxpayer["full_legal_name"], "Alex Sample")
            # ISO normalized to upper-case; dashes stripped from SSN.
            self.assertEqual(taxpayer["address_country"], "DE")
            self.assertEqual(taxpayer["us_ssn_or_itin"], "123456789")
            self.assertEqual(taxpayer["german_tax_id"], "12345678901")
            self.assertEqual(taxpayer["citizenship_status"], "us_citizen")

    def test_partial_save_preserves_unrelated_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"full_legal_name": "Alex Sample"}},
                },
            )
            _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"address_city": "Berlin"}},
                },
            )
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            taxpayer = payload["state"]["taxpayer"]
            # Both fields must be present after sequential partial saves.
            self.assertEqual(taxpayer["full_legal_name"], "Alex Sample")
            self.assertEqual(taxpayer["address_city"], "Berlin")

    def test_invalid_ssn_rejected_and_disk_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            before = paths.profile_path.read_text(encoding="utf-8") if paths.profile_path.exists() else ""
            status, payload = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"us_ssn_or_itin": "abc"}},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("error", payload)
            after = paths.profile_path.read_text(encoding="utf-8") if paths.profile_path.exists() else ""
            self.assertEqual(before, after)

    def test_invalid_citizenship_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"citizenship_status": "martian"}},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("citizenship_status", payload["error"])

    def test_restore_after_fresh_paths_resolution(self) -> None:
        # Mimics restart-server: write, then re-resolve paths and read.
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"full_legal_name": "Alex Sample", "german_tax_id": "12345678901"}},
                },
            )
            # Pretend the server restarted: re-resolve paths, no in-memory state.
            paths2 = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=ws)
            ensure_year_scaffold(paths2)
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            self.assertEqual(payload["state"]["taxpayer"]["full_legal_name"], "Alex Sample")
            self.assertEqual(payload["state"]["taxpayer"]["german_tax_id"], "12345678901")


# ---------------------------------------------------------------------------
# Bank accounts
# ---------------------------------------------------------------------------


class BankAccountsScreenTest(unittest.TestCase):
    def test_round_trip_writes_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/bank_accounts/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "accounts": [
                            {
                                "label": "Sparkasse Berlin",
                                "country": "de",
                                "account_number": "DE89370400440532013000",
                                "year_end_balance_usd": "12500.50",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            accounts = payload["state"]["accounts"]
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0]["country"], "DE")
            csv_path = paths.config_root / "bank_accounts.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["label"], "Sparkasse Berlin")
            for column in BANK_ACCOUNTS_COLUMNS:
                self.assertIn(column, rows[0])

    def test_invalid_balance_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/bank_accounts/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "accounts": [{"label": "x", "year_end_balance_usd": "not-a-number"}]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("year_end_balance_usd", payload["error"])

    def test_partial_save_without_accounts_key_leaves_csv_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            # First write one account.
            _post(
                "/api/bank_accounts/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"accounts": [{"label": "First", "country": "DE"}]},
                },
            )
            # Now POST with no `accounts` key — partial save should leave
            # the existing CSV alone.
            status, _ = _post(
                "/api/bank_accounts/state",
                body={"year": "2026", "workspace": str(ws), "state": {}},
            )
            self.assertEqual(status, 200)
            status, payload = _get(f"/api/bank_accounts/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["accounts"][0]["label"], "First")


# ---------------------------------------------------------------------------
# DE deductions (Wave 3A)
# ---------------------------------------------------------------------------


class DeDeductionsScreenTest(unittest.TestCase):
    def test_round_trip_persists_into_manual_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "medical_expenses_eur": "850.00",
                        "charitable_donations_eur": "200",
                        "gdb": 50,
                        "arbeitszimmer_claimed": True,
                        "arbeitszimmer_qualifies_as_mittelpunkt": "true",
                        "support_recipient_relationship": "parent",
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            ret = payload["state"]
            self.assertEqual(ret["medical_expenses_eur"], "850.00")
            self.assertEqual(ret["gdb"], 50)
            self.assertIs(ret["arbeitszimmer_claimed"], True)
            self.assertIs(ret["arbeitszimmer_qualifies_as_mittelpunkt"], True)
            self.assertEqual(ret["support_recipient_relationship"], "parent")
            on_disk = json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["deductions"]["wave3a"]["medical_expenses_eur"], "850.00")

    def test_invalid_gdb_value_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"gdb": 35},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("gdb", payload["error"])

    def test_invalid_relationship_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"support_recipient_relationship": "neighbor"},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("support_recipient_relationship", payload["error"])

    def test_partial_save_only_writes_present_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"medical_expenses_eur": "100.00"},
                },
            )
            _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"charitable_donations_eur": "50.00"},
                },
            )
            status, payload = _get(f"/api/de_deductions/state?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            ret = payload["state"]
            self.assertEqual(ret["medical_expenses_eur"], "100.00")
            self.assertEqual(ret["charitable_donations_eur"], "50.00")


# ---------------------------------------------------------------------------
# Vorabpauschale per-fund
# ---------------------------------------------------------------------------


class VorabpauschaleScreenTest(unittest.TestCase):
    def test_round_trip_writes_reference_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/vorabpauschale/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "funds": [
                            {
                                "symbol": "IE00B4L5Y983",
                                "fund_name": "iShares Core MSCI World",
                                "nav_start_eur": "100.00",
                                "nav_end_eur": "112.00",
                                "ausschuettung_eur": "0.50",
                                "months_held": 12,
                                "fund_classification": "aktienfonds",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            funds = payload["state"]["funds"]
            self.assertEqual(funds[0]["symbol"], "IE00B4L5Y983")
            self.assertEqual(funds[0]["fund_classification"], "aktienfonds")
            csv_path = paths.reference_data_root / "de-vorabpauschale-inputs-2025.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            for column in VORABPAUSCHALE_COLUMNS:
                self.assertIn(column, rows[0])

    def test_invalid_fund_classification_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/vorabpauschale/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "funds": [
                            {
                                "symbol": "IE00B4L5Y983",
                                "fund_classification": "totally_invented",
                            }
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("fund_classification", payload["error"])

    def test_months_held_out_of_range_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/vorabpauschale/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "funds": [
                            {"symbol": "X", "months_held": 25},
                        ]
                    },
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("months_held", payload["error"])

    def test_replacing_funds_list_replaces_csv(self) -> None:
        # Vorabpauschale is a list-editor screen: rebuilds the CSV.
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _post(
                "/api/vorabpauschale/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"funds": [{"symbol": "AAA", "fund_classification": "aktienfonds"}]},
                },
            )
            _post(
                "/api/vorabpauschale/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"funds": [{"symbol": "BBB", "fund_classification": "mischfonds"}]},
                },
            )
            status, payload = _get(f"/api/vorabpauschale/state?year=2026&workspace={ws}")
            funds = payload["state"]["funds"]
            self.assertEqual(len(funds), 1)
            self.assertEqual(funds[0]["symbol"], "BBB")


# ---------------------------------------------------------------------------
# Carryovers
# ---------------------------------------------------------------------------


class CarryoversScreenTest(unittest.TestCase):
    def test_round_trip_us_and_de(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/carryovers/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {
                        "us_passive_ftc_carryover_2024_usd": "200.00",
                        "us_general_ftc_carryover_2024_usd": "50.00",
                        "us_short_term_capital_loss_carryover_2024_usd": "0.00",
                        "us_long_term_capital_loss_carryover_2024_usd": "1500.00",
                        "de_stock_loss_carryforward_2024_eur": "300.00",
                        "de_non_stock_loss_carryforward_2024_eur": "100.00",
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            ret = payload["state"]
            self.assertEqual(ret["us_passive_ftc_carryover_2024_usd"], "200.00")
            self.assertEqual(ret["de_stock_loss_carryforward_2024_eur"], "300.00")
            on_disk = json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))
            self.assertEqual(
                on_disk["carryovers"]["us_ftc"]["us_passive_ftc_carryover_2024_usd"],
                "200.00",
            )
            de_loss_path = paths.facts_root / "de-loss-carryforwards.csv"
            self.assertTrue(de_loss_path.exists())
            with de_loss_path.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            keys_to_values = {row["key"]: row["value"] for row in rows}
            self.assertEqual(keys_to_values.get("stock_loss_carryforward_2024_eur"), "300.00")
            self.assertEqual(keys_to_values.get("private_sale_loss_carryforward_2024_eur"), "100.00")

    def test_invalid_money_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/carryovers/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"us_passive_ftc_carryover_2024_usd": "definitely-not-a-number"},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("us_passive_ftc_carryover_2024_usd", payload["error"])

    def test_partial_save_does_not_clobber_us_when_only_de_submitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths, ws = _new_workspace(tmp)
            _post(
                "/api/carryovers/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"us_passive_ftc_carryover_2024_usd": "100.00"},
                },
            )
            _post(
                "/api/carryovers/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"de_stock_loss_carryforward_2024_eur": "75.00"},
                },
            )
            status, payload = _get(f"/api/carryovers/state?year=2026&workspace={ws}")
            ret = payload["state"]
            self.assertEqual(ret["us_passive_ftc_carryover_2024_usd"], "100.00")
            self.assertEqual(ret["de_stock_loss_carryforward_2024_eur"], "75.00")


# ---------------------------------------------------------------------------
# Save-all + progress
# ---------------------------------------------------------------------------


class SaveAllProgressTest(unittest.TestCase):
    def test_progress_endpoint_returns_completeness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _get(f"/api/progress?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            self.assertIn("completeness", payload)
            completeness = payload["completeness"]
            self.assertIn("filled", completeness)
            self.assertIn("total", completeness)
            self.assertEqual(completeness["total"], len(SCREEN_NAMES))

    def test_save_all_writes_every_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/save-all",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "screens": {
                        "identity": {"taxpayer": {"full_legal_name": "Alex"}},
                        "bank_accounts": {"accounts": [{"label": "Spk", "country": "DE"}]},
                        "de_deductions": {"medical_expenses_eur": "100.00"},
                        "vorabpauschale": {
                            "funds": [{"symbol": "X", "fund_classification": "aktienfonds"}]
                        },
                        "carryovers": {"us_passive_ftc_carryover_2024_usd": "10.00"},
                        "children": {
                            "children": [
                                {
                                    "name": "Kid Sample",
                                    "date_of_birth": "2018-09-12",
                                    "relationship": "qualifying_child",
                                    "ssn": "123-45-6789",
                                }
                            ]
                        },
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(set(payload["saved"].keys()), set(SCREEN_NAMES))
            # Every screen now reads back populated state.
            for screen in SCREEN_NAMES:
                _, sub = _get(f"/api/{screen}/state?year=2026&workspace={ws}")
                self.assertIn("state", sub)

    def test_save_all_progress_marks_screens_as_filled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            _post(
                "/api/save-all",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "screens": {
                        "bank_accounts": {"accounts": [{"label": "Spk", "country": "DE"}]},
                        "de_deductions": {"medical_expenses_eur": "100.00"},
                    },
                },
            )
            _, payload = _get(f"/api/progress?year=2026&workspace={ws}")
            by_screen = payload["completeness"]["by_screen"]
            self.assertTrue(by_screen["bank_accounts"]["filled"])
            self.assertTrue(by_screen["de_deductions"]["filled"])

    def test_save_all_rejects_unknown_screen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            status, payload = _post(
                "/api/save-all",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "screens": {"made_up_screen": {}},
                },
            )
            self.assertEqual(status, 400, payload)
            self.assertIn("error", payload)


# ---------------------------------------------------------------------------
# Frontend wiring (HTML + JS structure)
# ---------------------------------------------------------------------------


class FrontendWiringTest(unittest.TestCase):
    def test_index_html_includes_every_screen_section(self) -> None:
        _, _, html_body = dispatch_response(PROJECT_ROOT, "GET", "/")
        html = html_body.decode("utf-8")
        for screen in SCREEN_NAMES:
            self.assertIn(f'data-screen="{screen}"', html, f"Screen {screen} missing in index.html")
            self.assertIn(f'data-nav-target="{screen}"', html, f"Nav target for {screen} missing in index.html")
        self.assertIn('id="save-all-button"', html)
        self.assertIn('id="progress-summary"', html)

    def test_app_js_wires_save_all_and_screen_loaders(self) -> None:
        _, _, js_body = dispatch_response(PROJECT_ROOT, "GET", "/static/app.js")
        js = js_body.decode("utf-8")
        self.assertIn("function saveAllProgress", js)
        self.assertIn("function bindAllScreenForms", js)
        self.assertIn("/api/save-all", js)
        self.assertIn("/api/screens/metadata", js)
        self.assertIn("/api/progress", js)
        # The JS uses a template literal `/api/${screen}/state`; assert it
        # appears once and that every screen name is in the screens list.
        self.assertIn("/api/${screen}/state", js)
        for screen in SCREEN_NAMES:
            self.assertIn(f'"{screen}"', js, f"Screen {screen} missing in SCREEN_NAMES JS array")


# ---------------------------------------------------------------------------
# Coverage assertion: every engine elections.<key> is reachable somewhere
# ---------------------------------------------------------------------------


class EngineCoverageTest(unittest.TestCase):
    def test_engine_required_input_fields_are_reachable(self) -> None:
        # The Wave 6 screens add Wave-3A deduction inputs and Vorabpauschale
        # per-fund inputs, both of which the engine reads. The engine's
        # ``elections.<key>`` lookups are already covered by the Wave 5
        # posture registry; this test guards against future drift by
        # asserting the universe of (posture-registry ∪ wave-6-screen)
        # inputs covers the union of the engine's lookup keys.
        engine_inputs = (
            PROJECT_ROOT / "tax_pipeline" / "y2025" / "germany_inputs.py",
            PROJECT_ROOT / "tax_pipeline" / "y2025" / "us_inputs.py",
        )
        election_pattern = re.compile(r"elections\.([a-z][a-z0-9_]+)")
        ignored_keys = {"get", "setdefault", "pop", "items", "keys", "values"}
        engine_keys: set[str] = set()
        for path in engine_inputs:
            text = path.read_text(encoding="utf-8")
            for match in election_pattern.finditer(text):
                key = match.group(1)
                if key in ignored_keys:
                    continue
                engine_keys.add(key)

        from tax_pipeline.intake.postures import POSTURE_REGISTRY

        registry_keys = {
            field.key.split(".", 1)[1]
            for field in POSTURE_REGISTRY
            if field.key.startswith("elections.")
        }

        missing = engine_keys - registry_keys
        self.assertFalse(
            missing,
            "Engine elections lookups not covered by registry/screens: "
            + ", ".join(sorted(missing)),
        )

    def test_screen_handlers_match_screen_names(self) -> None:
        self.assertEqual(set(SCREEN_HANDLERS.keys()), set(SCREEN_NAMES))


if __name__ == "__main__":
    unittest.main()
