from __future__ import annotations

import base64
import binascii
import json
import os
import secrets
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from tax_pipeline.intake.outputs import (
    build_output_manifest,
    build_output_preview,
    read_generated_output,
)
from tax_pipeline.intake.postures import (
    PostureValidationError,
    read_posture_state,
    serialize_registry,
    write_posture_state,
)
from tax_pipeline.intake.screens import (
    SCREEN_HANDLERS,
    ScreenValidationError,
    read_progress,
    save_all_progress,
    serialize_screen_metadata,
)
from tax_pipeline.intake.workspace import (
    create_workspace,
    materialize_demo_into_workspace,
    open_workspace,
    read_household,
    read_payments,
    resolve_workspace_paths,
    roll_forward_workspace,
    write_household,
    write_payments,
)
from tax_pipeline.intake.uploads import classify_upload_batch, list_uploads, store_upload
from tax_pipeline.intake.commands import (
    get_readiness,
    run_pipeline,
    start_run,
    status_run,
)
from tax_pipeline.run_year import StageFailure

CSRF_HEADER = "X-Tax-Intake-CSRF"
MAX_JSON_BODY_BYTES = 2 * 1024 * 1024
# Larger body cap for /api/uploads only: a 25 MB file (the advertised
# per-file ceiling, enforced post-decode by MAX_UPLOAD_BYTES) is ~33 MB
# of base64 plus JSON envelope. 36 MB gives comfortable headroom.
UPLOAD_JSON_BODY_BYTES = 36 * 1024 * 1024

# Loopback host names always allowed. A request whose Host header is not in
# the allowlist is rejected before any handling — this is the defense
# against DNS-rebinding, where a malicious page rebinds its own domain to
# 127.0.0.1 to become "same origin" and then reads the CSRF token / hits
# the destructive endpoints. The browser sends the *attacker's* domain in
# the Host header, so an allowlist of loopback names closes the hole even
# though the socket itself is loopback. Operators can widen the list with
# TAX_INTAKE_ALLOWED_HOSTS (comma-separated) for non-default binds.
_DEFAULT_ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


def _allowed_hosts(bind_host: str) -> frozenset[str]:
    hosts = set(_DEFAULT_ALLOWED_HOSTS)
    if bind_host:
        hosts.add(bind_host)
    extra = os.environ.get("TAX_INTAKE_ALLOWED_HOSTS", "")
    for token in extra.split(","):
        token = token.strip()
        if token:
            hosts.add(token)
    return frozenset(hosts)


def _host_header_allowed(host_header: str | None, allowed: frozenset[str]) -> bool:
    if not host_header:
        # No Host header at all (HTTP/1.0 without one). Reject — a normal
        # browser always sends Host; absence is anomalous.
        return False
    # Strip the optional :port. IPv6 literals arrive bracketed ("[::1]:8765").
    hostname = host_header
    if hostname.startswith("["):
        # [::1]:port  ->  [::1]
        closing = hostname.find("]")
        if closing != -1:
            hostname = hostname[: closing + 1]
    elif ":" in hostname:
        hostname = hostname.rsplit(":", 1)[0]
    return hostname in allowed


class IntakeHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, *, project_root: Path) -> None:
        super().__init__(server_address, request_handler_class)
        self.project_root = project_root.resolve()
        self.csrf_token = secrets.token_urlsafe(32)
        bind_host = server_address[0] if server_address else ""
        self.allowed_hosts = _allowed_hosts(bind_host)


def _workspace_root_from_text(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def _static_root(project_root: Path) -> Path:
    return project_root / "tax_pipeline" / "intake" / "static"


def _content_type_for_path(path: Path) -> str:
    if path.suffix == ".html":
        return "text/html; charset=utf-8"
    if path.suffix == ".css":
        return "text/css; charset=utf-8"
    if path.suffix == ".js":
        return "application/javascript; charset=utf-8"
    if path.suffix == ".md":
        return "text/markdown; charset=utf-8"
    if path.suffix == ".json":
        return "application/json; charset=utf-8"
    if path.suffix == ".csv":
        return "text/csv; charset=utf-8"
    if path.suffix == ".txt":
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def dispatch_request(
    project_root: Path,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    parsed = urlparse(path)

    if method == "GET" and parsed.path == "/api/health":
        return HTTPStatus.OK, {"ok": True}

    if method == "GET" and parsed.path == "/api/workspace":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        return HTTPStatus.OK, open_workspace(project_root, year, workspace_root=workspace_root)

    if method == "GET" and parsed.path == "/api/intake/household":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, read_household(paths)

    if method == "GET" and parsed.path == "/api/intake/payments":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, read_payments(paths)

    if method == "GET" and parsed.path == "/api/uploads":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, list_uploads(paths)

    if method == "GET" and parsed.path == "/api/readiness":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        return HTTPStatus.OK, get_readiness(project_root, year, workspace_root=workspace_root)

    if method == "GET" and parsed.path == "/api/output-preview":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        rel_path = query.get("path", [""])[0]
        if not year or not rel_path:
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing 'year' and/or 'path'. Provide both — e.g. /api/output-preview?year=2025&path=outputs/analysis-steps/final-legal-output.json.",
            }
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, build_output_preview(paths, rel_path)
        except PermissionError as exc:
            return HTTPStatus.FORBIDDEN, {"error": str(exc)}
        except FileNotFoundError as exc:
            return HTTPStatus.NOT_FOUND, {"error": f"Output not found: {exc}"}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "GET" and parsed.path == "/api/outputs":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, build_output_manifest(paths)

    if method == "GET" and parsed.path == "/api/postures":
        return HTTPStatus.OK, {"fields": serialize_registry()}

    if method == "GET" and parsed.path == "/api/postures/state":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, {"state": read_posture_state(paths)}

    if method == "POST" and parsed.path == "/api/postures/state":
        payload = dict(body or {})
        year = str(payload.pop("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
        submitted = payload.get("state")
        if not isinstance(submitted, dict):
            return HTTPStatus.BAD_REQUEST, {"error": "The request is missing the 'state' object, or it is not an object. Please include a JSON object with the screen's field values."}
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, {"state": write_posture_state(paths, submitted)}
        except PostureValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    # --- Wave 6 partial-save / restore screens -----------------------------
    if method == "GET" and parsed.path == "/api/screens/metadata":
        return HTTPStatus.OK, {"screens": serialize_screen_metadata()}

    if method == "GET" and parsed.path == "/api/progress":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        return HTTPStatus.OK, read_progress(paths)

    if method == "POST" and parsed.path == "/api/save-all":
        payload = dict(body or {})
        year = str(payload.pop("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
        screens_payload = payload.get("screens")
        if screens_payload is None:
            screens_payload = {key: payload.get(key) for key in payload if key in SCREEN_HANDLERS}
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, save_all_progress(paths, screens_payload)
        except ScreenValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    for _screen_name, (_reader, _writer) in SCREEN_HANDLERS.items():
        if method == "GET" and parsed.path == f"/api/{_screen_name}/state":
            query = parse_qs(parsed.query)
            year = query.get("year", [""])[0]
            if not year:
                return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}
            workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, {"state": _reader(paths)}
        if method == "POST" and parsed.path == f"/api/{_screen_name}/state":
            payload = dict(body or {})
            year = str(payload.pop("year", "")).strip()
            if not year:
                return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
            workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
            submitted = payload.get("state")
            if submitted is None:
                # Allow callers to put the screen body at top-level when the
                # 'state' wrapper is omitted; this mirrors the postures
                # convention but is more forgiving for partial submissions.
                submitted = {k: v for k, v in payload.items() if k not in ("year", "workspace")}
            if not isinstance(submitted, dict):
                return HTTPStatus.BAD_REQUEST, {"error": "The request is missing the 'state' object, or it is not an object. Please include a JSON object with the screen's field values."}
            try:
                paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
                return HTTPStatus.OK, {"state": _writer(paths, submitted)}
            except ScreenValidationError as exc:
                return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
            except ValueError as exc:
                return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/workspace/create":
        payload = body or {}
        year = str(payload.get("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.get("workspace", "")).strip())
        try:
            return HTTPStatus.CREATED, create_workspace(project_root, year, workspace_root=workspace_root)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/workspace/demo":
        # The demo target is fixed (~/taxes/demo-2025) inside
        # materialize_demo_into_workspace. We deliberately ignore any
        # client-supplied 'year'/'workspace' so a forged request cannot
        # redirect the destructive reset at an arbitrary directory.
        try:
            return HTTPStatus.CREATED, materialize_demo_into_workspace(project_root)
        except FileNotFoundError:
            return HTTPStatus.NOT_FOUND, {"error": "The synthetic demo workspace is missing from this install."}
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/workspace/roll-forward":
        payload = body or {}
        year = str(payload.get("year", "")).strip()
        source_year = str(payload.get("source_year", "")).strip()
        if not year or not source_year:
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing 'year' and/or 'source_year'. Provide both — e.g. {\"source_year\": \"2024\", \"year\": \"2025\"}.",
            }
        workspace_root = _workspace_root_from_text(str(payload.get("workspace", "")).strip())
        try:
            return HTTPStatus.CREATED, roll_forward_workspace(
                project_root,
                source_year=source_year,
                target_year=year,
                workspace_root=workspace_root,
            )
        except FileNotFoundError:
            # Redact the absolute source path (repo convention: path_redacted).
            return HTTPStatus.NOT_FOUND, {
                "error": f"No existing workspace found for {source_year} to roll forward from.",
            }
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/intake/household":
        payload = dict(body or {})
        year = str(payload.pop("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, write_household(paths, payload)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/intake/payments":
        payload = dict(body or {})
        year = str(payload.pop("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            return HTTPStatus.OK, write_payments(paths, payload)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    if method == "POST" and parsed.path == "/api/uploads/classify-batch":
        payload = dict(body or {})
        filenames = payload.get("filenames")
        if not isinstance(filenames, list):
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing 'filenames' array. Provide a list of names to classify, e.g. {\"filenames\": [\"foo.pdf\", \"bar.csv\"]}.",
            }
        return HTTPStatus.OK, {"predictions": classify_upload_batch([str(n) for n in filenames])}

    if method == "POST" and parsed.path == "/api/uploads":
        payload = dict(body or {})
        year = str(payload.pop("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.pop("workspace", "")).strip())
        filename = str(payload.get("filename", "")).strip()
        if not filename:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the file name. Please include 'filename' in the request body so we know what to call the upload."}
        encoded = str(payload.get("content_base64", "")).strip()
        if not encoded:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the file contents. Please include 'content_base64' in the request body with the file encoded as base64."}
        try:
            paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
            content = base64.b64decode(encoded.encode("ascii"), validate=True)
            result = store_upload(
                paths,
                filename,
                content,
                manual_bucket=str(payload.get("manual_bucket", "")).strip() or None,
                evidence_only=bool(payload.get("evidence_only", False)),
            )
        except (binascii.Error, UnicodeEncodeError) as exc:
            return HTTPStatus.BAD_REQUEST, {
                "error": (
                    f"The file contents are not valid base64. Please "
                    f"re-encode the file using standard base64 and try "
                    f"again. (Detail: {exc})"
                )
            }
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        status = HTTPStatus.CREATED if result.get("stored") else HTTPStatus.OK
        return status, result

    if method == "POST" and parsed.path == "/api/run":
        payload = dict(body or {})
        year = str(payload.get("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {"error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."}
        workspace_root = _workspace_root_from_text(str(payload.get("workspace", "")).strip())
        try:
            return HTTPStatus.ACCEPTED, run_pipeline(project_root, year, workspace_root=workspace_root)
        except StageFailure as exc:
            # H2: structured pipeline failure with statute citation +
            # URL. The wizard renders this as a labeled error card
            # showing each field instead of a single opaque error
            # string, so the user (or a reviewer) can click through to
            # the cited authority directly from the UI.
            return HTTPStatus.UNPROCESSABLE_ENTITY, {
                "error": exc.original_message,
                "stage_failure": exc.as_dict(),
            }
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}

    # H1: streaming-progress flow. Start kicks off ``run_year`` on a
    # background thread and returns immediately with a ``run_id``; status
    # is polled every ~500ms by the wizard so the user sees per-stage
    # progress instead of a frozen tab while the pipeline runs.
    if method == "POST" and parsed.path == "/api/run/start":
        payload = dict(body or {})
        year = str(payload.get("year", "")).strip()
        if not year:
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing the tax year. Please include 'year' in the request body, like {\"year\": \"2025\"}."
            }
        workspace_root = _workspace_root_from_text(
            str(payload.get("workspace", "")).strip()
        )
        try:
            result = start_run(project_root, year, workspace_root=workspace_root)
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        return HTTPStatus.ACCEPTED, result

    if method == "GET" and parsed.path == "/api/run/status":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        if not year:
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."
            }
        run_id = query.get("run_id", [""])[0]
        if not run_id:
            return HTTPStatus.BAD_REQUEST, {
                "error": "Missing the run identifier. Please add ?run_id=... to the URL — the value is returned by /api/run/start."
            }
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        try:
            result = status_run(
                project_root, year, run_id, workspace_root=workspace_root
            )
        except ValueError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        return HTTPStatus.OK, result

    return HTTPStatus.NOT_FOUND, {"error": f"Unknown route: {parsed.path}"}


def dispatch_response(
    project_root: Path,
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
) -> tuple[int, str, bytes]:
    parsed = urlparse(path)
    static_root = _static_root(project_root)

    if method == "GET" and parsed.path == "/":
        asset_path = static_root / "index.html"
        return HTTPStatus.OK, _content_type_for_path(asset_path), asset_path.read_bytes()

    if method == "GET" and parsed.path.startswith("/static/"):
        asset_name = parsed.path.removeprefix("/static/")
        asset_path = (static_root / asset_name).resolve()
        try:
            asset_path.relative_to(static_root.resolve())
        except ValueError:
            payload = json.dumps({"error": f"Unknown route: {parsed.path}"}).encode("utf-8")
            return HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", payload
        if not asset_path.exists() or not asset_path.is_file():
            payload = json.dumps({"error": f"Unknown route: {parsed.path}"}).encode("utf-8")
            return HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", payload
        return HTTPStatus.OK, _content_type_for_path(asset_path), asset_path.read_bytes()

    if method == "GET" and parsed.path == "/api/output-download":
        query = parse_qs(parsed.query)
        year = query.get("year", [""])[0]
        relative_path = query.get("path", [""])[0]
        if not year:
            payload = json.dumps({"error": "Missing the tax year. Please add ?year=YYYY to the URL, like ?year=2025."}).encode("utf-8")
            return HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", payload
        if not relative_path:
            payload = json.dumps({"error": "Missing required query parameter: path"}).encode("utf-8")
            return HTTPStatus.BAD_REQUEST, "application/json; charset=utf-8", payload
        workspace_root = _workspace_root_from_text(query.get("workspace", [""])[0])
        paths = resolve_workspace_paths(project_root, year, workspace_root=workspace_root)
        try:
            output_path = read_generated_output(paths, relative_path)
        except PermissionError as exc:
            payload = json.dumps({"error": str(exc)}).encode("utf-8")
            return HTTPStatus.FORBIDDEN, "application/json; charset=utf-8", payload
        except FileNotFoundError as exc:
            payload = json.dumps({"error": f"Generated output not found: {exc}"}).encode("utf-8")
            return HTTPStatus.NOT_FOUND, "application/json; charset=utf-8", payload
        return HTTPStatus.OK, _content_type_for_path(output_path), output_path.read_bytes()

    status, payload = dispatch_request(project_root, method, path, body=body)
    encoded = json.dumps(payload).encode("utf-8")
    return int(status), "application/json; charset=utf-8", encoded


def _build_handler():
    class IntakeHandler(BaseHTTPRequestHandler):
        server: IntakeHTTPServer

        def log_message(self, format: str, *args) -> None:
            return

        def _send_response(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json_body(self, max_bytes: int = MAX_JSON_BODY_BYTES) -> dict[str, object]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("Invalid Content-Length") from exc
            if length > max_bytes:
                raise ValueError("Request body exceeds maximum size")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def _reject_bad_host(self) -> bool:
            """Reject requests whose Host header is not allow-listed.

            Closes the DNS-rebinding bypass: the CSRF token is handed out
            on GET /api/session, so without a Host check a rebound
            attacker domain could read it and then drive the destructive
            POST endpoints. Returns True (and sends 403) when the request
            must be rejected.
            """
            host = self.headers.get("Host")
            if not _host_header_allowed(host, self.server.allowed_hosts):
                self._send_json(
                    {"error": "Forbidden host. This server only accepts local (loopback) requests."},
                    HTTPStatus.FORBIDDEN,
                )
                return True
            return False

        def do_GET(self) -> None:
            if self._reject_bad_host():
                return
            if urlparse(self.path).path == "/api/session":
                self._send_json({"csrf_token": self.server.csrf_token})
                return
            status, content_type, payload = dispatch_response(self.server.project_root, "GET", self.path)
            self._send_response(status, content_type, payload)

        def do_POST(self) -> None:
            if self._reject_bad_host():
                return
            if self.headers.get(CSRF_HEADER) != self.server.csrf_token:
                self._send_json({"error": "Missing or invalid CSRF token"}, HTTPStatus.FORBIDDEN)
                return
            content_type = self.headers.get("Content-Type", "")
            if content_type and not content_type.lower().startswith("application/json"):
                self._send_json({"error": "POST requests require application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
                return
            # File uploads carry base64-encoded bytes, which inflate ~4/3
            # and must fit the 25 MB decoded cap (MAX_UPLOAD_BYTES). The
            # default 2 MB JSON cap would throttle uploads to ~1.5 MB, so
            # the uploads route gets a larger body cap. Every other route
            # keeps the small cap.
            max_body = (
                UPLOAD_JSON_BODY_BYTES
                if urlparse(self.path).path == "/api/uploads"
                else MAX_JSON_BODY_BYTES
            )
            try:
                body = self._read_json_body(max_body)
            except json.JSONDecodeError as exc:
                self._send_json({"error": f"Invalid JSON request body: {exc}"}, HTTPStatus.BAD_REQUEST)
                return
            except ValueError as exc:
                status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE if "maximum size" in str(exc) else HTTPStatus.BAD_REQUEST
                self._send_json({"error": str(exc)}, status)
                return
            status, content_type, payload = dispatch_response(
                self.server.project_root,
                "POST",
                self.path,
                body=body,
            )
            self._send_response(status, content_type, payload)

    return IntakeHandler


def build_server(host: str, port: int, *, project_root: Path) -> IntakeHTTPServer:
    return IntakeHTTPServer((host, port), _build_handler(), project_root=project_root)
