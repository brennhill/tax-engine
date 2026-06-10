from __future__ import annotations

import json
import http.client
import threading
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

from tax_pipeline.intake.server import build_server, dispatch_request, dispatch_response
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class _TagIndex(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {key: value or "" for key, value in attrs}))

    def has(self, tag: str, **attrs: str) -> bool:
        return any(
            candidate_tag == tag and all(candidate_attrs.get(key) == value for key, value in attrs.items())
            for candidate_tag, candidate_attrs in self.tags
        )


class IntakeServerTest(unittest.TestCase):
    def test_root_serves_the_wizard_shell(self) -> None:
        status, content_type, body = dispatch_response(PROJECT_ROOT, "GET", "/")

        text = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html; charset=utf-8")
        self.assertIn("data-screen=\"workspace\"", text)
        self.assertIn("data-screen=\"household\"", text)
        self.assertIn("data-screen=\"payments\"", text)
        self.assertIn("data-screen=\"documents\"", text)
        # Readiness migrated from a stand-alone screen to a sticky
        # right-rail panel that re-runs the validator after each save.
        self.assertIn('id="readiness-rail"', text)
        self.assertIn("data-screen=\"run\"", text)

    def test_static_assets_are_served(self) -> None:
        js_status, js_type, js_body = dispatch_response(PROJECT_ROOT, "GET", "/static/app.js")
        css_status, css_type, css_body = dispatch_response(PROJECT_ROOT, "GET", "/static/styles.css")

        self.assertEqual(js_status, 200)
        self.assertEqual(js_type, "application/javascript; charset=utf-8")
        self.assertIn("async function createWorkspace", js_body.decode("utf-8"))

        self.assertEqual(css_status, 200)
        self.assertEqual(css_type, "text/css; charset=utf-8")
        self.assertIn(".wizard-shell", css_body.decode("utf-8"))

    def test_browser_shell_exposes_ui_controls_for_all_api_flows(self) -> None:
        _, _, html_body = dispatch_response(PROJECT_ROOT, "GET", "/")
        _, _, js_body = dispatch_response(PROJECT_ROOT, "GET", "/static/app.js")

        html = html_body.decode("utf-8")
        js = js_body.decode("utf-8")
        dom = _TagIndex()
        dom.feed(html)

        self.assertTrue(dom.has("form", id="household-form"))
        self.assertTrue(dom.has("form", id="payments-form"))
        self.assertTrue(dom.has("form", id="document-upload-form"))
        # Readiness button retired in favour of the live readiness rail.
        self.assertTrue(dom.has("aside", id="readiness-rail"))
        self.assertTrue(dom.has("button", id="run-button"))
        self.assertTrue(dom.has("button", id="outputs-button"))
        self.assertTrue(dom.has("div", id="outputs-list"))

        self.assertIn("function bindHouseholdForm", js)
        self.assertIn("function bindPaymentsForm", js)
        self.assertIn("function bindUploadForm", js)
        self.assertIn("function renderOutputDownloads", js)
        self.assertIn('us_ftc_method: "accrued"', js)
        self.assertNotIn('|| "0.00"', js)
        self.assertIn("/api/intake/household", js)
        self.assertIn("/api/intake/payments", js)
        self.assertIn("/api/uploads", js)
        self.assertIn("/api/readiness", js)
        self.assertIn("/api/run", js)
        self.assertIn("/api/outputs", js)

    def test_browser_shell_defaults_tax_year_to_prior_calendar_year(self) -> None:
        _, _, html_body = dispatch_response(PROJECT_ROOT, "GET", "/")
        _, _, js_body = dispatch_response(PROJECT_ROOT, "GET", "/static/app.js")

        html = html_body.decode("utf-8")
        js = js_body.decode("utf-8")

        self.assertIn('name="year"', html)
        self.assertNotIn('name="year" value="2026"', html)
        self.assertIn("new Date().getFullYear() - 1", js)
        self.assertIn("workspaceYearInput.value = state.year", js)

    def test_health_endpoint_returns_ok(self) -> None:
        status, payload = dispatch_request(PROJECT_ROOT, "GET", "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

    def test_outputs_endpoint_lists_downloadable_run_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            (paths.analysis_root / "final-legal-output.json").write_text("{}")
            (paths.analysis_root / "DE-de-narrative.md").write_text("# German narrative")
            (paths.analysis_root / "DE-en-narrative.md").write_text("# Germany narrative")
            (paths.analysis_root / "US-en-narrative.md").write_text("# U.S. narrative")
            (paths.germany_forms_root / "index.md").write_text("# Germany forms")

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/outputs?year=2025&workspace={workspace_root}",
            )

        self.assertEqual(status, 200)
        files = payload["files"]
        by_relative_path = {item["relative_path"]: item for item in files}
        self.assertIn("outputs/analysis-steps/final-legal-output.json", by_relative_path)
        self.assertIn("outputs/analysis-steps/DE-de-narrative.md", by_relative_path)
        self.assertIn("outputs/analysis-steps/DE-en-narrative.md", by_relative_path)
        self.assertIn("outputs/analysis-steps/US-en-narrative.md", by_relative_path)
        self.assertIn("outputs/forms/germany/index.md", by_relative_path)
        self.assertNotIn("absolute_path", by_relative_path["outputs/forms/germany/index.md"])
        self.assertNotIn(str(workspace_root), json.dumps(payload))
        self.assertEqual(by_relative_path["outputs/analysis-steps/DE-en-narrative.md"]["category"], "Narratives")
        self.assertIn("/api/output-download?", by_relative_path["outputs/analysis-steps/DE-en-narrative.md"]["download_url"])

    def test_static_assets_use_path_containment_not_string_prefix(self) -> None:
        status, content_type, body = dispatch_response(PROJECT_ROOT, "GET", "/static/../server.py")

        self.assertEqual(status, 404)
        self.assertEqual(content_type, "application/json; charset=utf-8")
        self.assertIn("Unknown route", body.decode("utf-8"))

    def test_output_download_serves_only_workspace_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2025"
            paths = resolve_year_paths(PROJECT_ROOT, "2025", workspace_root=workspace_root)
            paths.ensure_directories()
            narrative_path = paths.analysis_root / "DE-en-narrative.md"
            narrative_path.write_text("# Germany narrative")

            safe_relative = quote("outputs/analysis-steps/DE-en-narrative.md")
            status, content_type, body = dispatch_response(
                PROJECT_ROOT,
                "GET",
                f"/api/output-download?year=2025&workspace={workspace_root}&path={safe_relative}",
            )
            blocked_status, _, blocked_body = dispatch_response(
                PROJECT_ROOT,
                "GET",
                f"/api/output-download?year=2025&workspace={workspace_root}&path=../config/profile.json",
            )

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/markdown; charset=utf-8")
        self.assertEqual(body.decode("utf-8"), "# Germany narrative")
        self.assertEqual(blocked_status, 403)
        self.assertIn("generated outputs", blocked_body.decode("utf-8"))

    def test_get_workspace_returns_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/workspace?year=2026&workspace={workspace_root}",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["year"], 2026)
            self.assertEqual(payload["workspace_root"], str(workspace_root.resolve()))
            self.assertEqual(payload["people_count"], 1)
            self.assertEqual(payload["germany_filing_posture"], "single")

    def test_post_workspace_create_creates_the_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/workspace/create",
                body={"year": "2026", "workspace": str(workspace_root)},
            )

            self.assertEqual(status, 201)
            self.assertEqual(payload["year"], 2026)
            self.assertEqual(payload["workspace_root"], str(workspace_root.resolve()))
            self.assertTrue((workspace_root / "config" / "profile.json").exists())

    def test_post_workspace_create_rejects_unsafe_workspace_roots(self) -> None:
        status, payload = dispatch_request(
            PROJECT_ROOT,
            "POST",
            "/api/workspace/create",
            body={"year": "2026", "workspace": str(PROJECT_ROOT)},
        )

        self.assertEqual(status, 400)
        self.assertIn("Unsafe workspace root", payload["error"])

    def test_http_post_requires_csrf_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            server = build_server("127.0.0.1", 0, project_root=PROJECT_ROOT)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                body = json.dumps({"year": "2026", "workspace": str(workspace_root)})
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(
                    "POST",
                    "/api/workspace/create",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                blocked = conn.getresponse()
                blocked_body = blocked.read().decode("utf-8")
                conn.close()

                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(
                    "POST",
                    "/api/workspace/create",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Tax-Intake-CSRF": server.csrf_token,
                    },
                )
                allowed = conn.getresponse()
                conn.close()
            finally:
                server.shutdown()
                server.server_close()

            self.assertEqual(blocked.status, 403, blocked_body)
            self.assertEqual(allowed.status, 201)

    def test_get_and_post_household_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/intake/household?year=2026&workspace={workspace_root}",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["household"]["marital_status_on_dec_31"], "")
            self.assertEqual(len(payload["people"]), 1)

            update = {
                "year": "2026",
                "workspace": str(workspace_root),
                "household": {
                    "marital_status_on_dec_31": "married",
                    "germany_filing_posture": "married_joint",
                    "usa_filing_posture": "mfs_nra_spouse",
                },
                "people": [
                    {
                        "person_id": "person_1",
                        "display_name": "Alex Example",
                        "relationship_role": "taxpayer",
                        "elster_order": "1",
                        "us_filer": True,
                        "is_taxpayer": True,
                        "is_spouse": False,
                        "citizenship": "US",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": False,
                    },
                    {
                        "person_id": "person_2",
                        "display_name": "Sam Example",
                        "relationship_role": "spouse",
                        "elster_order": "2",
                        "us_filer": False,
                        "is_taxpayer": False,
                        "is_spouse": True,
                        "citizenship": "DE",
                        "country_of_tax_residence": "DE",
                        "nra_for_us_return": True,
                    },
                ],
                "jurisdictions": {
                    "germany": {"enabled": True},
                    "usa": {
                        "enabled": True,
                        "us_ftc_method": "paid",
                        "use_treaty_resourcing": True,
                        "elect_joint_return_with_nra_spouse": False,
                    },
                },
            }

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/intake/household",
                body=update,
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["people_count"], 2)

            people_rows = _read_csv_rows(paths.people_path)
            self.assertEqual([row["display_name"] for row in people_rows], ["Alex Example", "Sam Example"])
            elections_rows = _read_csv_rows(paths.elections_path)
            by_pair = {(row["jurisdiction"], row["key"]): row["value"] for row in elections_rows}
            self.assertEqual(by_pair[("germany", "filing_posture")], "joint")
            self.assertEqual(by_pair[("usa", "filing_posture")], "mfs")

    def test_post_household_rejects_malformed_payload_shapes_as_400(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/intake/household",
                body={
                    "year": "2026",
                    "workspace": str(workspace_root),
                    "household": "not an object",
                    "people": "not a list",
                },
            )

            self.assertEqual(status, 400)
            self.assertIn("household must be an object", payload["error"])

    def test_get_and_post_payments_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/intake/payments?year=2026&workspace={workspace_root}",
            )

            self.assertEqual(status, 200)
            self.assertEqual(payload["payments"], [])

            update = {
                "year": "2026",
                "workspace": str(workspace_root),
                "payments": [
                    {
                        "jurisdiction": "germany",
                        "person_id": "",
                        "payment_type": "income_tax_prepayment",
                        "amount": "500.00",
                        "currency": "EUR",
                        "source": "manual",
                        "note": "Quarterly prepayment",
                    },
                    {
                        "jurisdiction": "usa",
                        "person_id": "person_1",
                        "payment_type": "estimated_tax_payment",
                        "amount": "250.00",
                        "currency": "USD",
                        "source": "manual",
                        "note": "IRS estimate",
                    },
                ],
            }

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/intake/payments",
                body=update,
            )

            self.assertEqual(status, 200)
            self.assertEqual(len(payload["payments"]), 2)
            self.assertEqual(_read_csv_rows(paths.payments_path)[0]["payment_type"], "income_tax_prepayment")

    def test_post_payments_rejects_malformed_payload_shapes_as_400(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
            ensure_year_scaffold(paths)

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/intake/payments",
                body={"year": "2026", "workspace": str(workspace_root), "payments": ["bad"]},
            )

            self.assertEqual(status, 400)
            self.assertIn("payments[1] must be an object", payload["error"])


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


if __name__ == "__main__":
    unittest.main()
