from __future__ import annotations

from pathlib import Path
from typing import Any

from tax_pipeline.intake.outputs import build_output_manifest
from tax_pipeline.intake.run_progress import (
    read_run_status,
    start_run as start_background_run,
)
from tax_pipeline.run_year import StageFailure, run_year
from tax_pipeline.validate_workspace import validate_workspace, validation_report_payload
from tax_pipeline.year_runtime import resolve_year_paths


def get_readiness(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    report = validate_workspace(project_root, year_token, workspace_root=workspace_root)
    return validation_report_payload(report)


def run_pipeline(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
) -> dict[str, object]:
    """Synchronous run, retained for tests / scripted callers.

    The wizard's primary path now uses ``start_run`` + ``status_run`` so
    the browser can poll for stage progress (H1). This synchronous
    helper still runs the full pipeline in-process and is kept for the
    legacy ``/api/run`` route and unit tests that invoke it directly.

    H2: any non-``StageFailure`` exception escaping ``run_year`` is
    wrapped at this boundary so the caller (HTTP server / unit test)
    sees a uniform structured error with statute citation + URL,
    instead of a raw ``ValueError`` whose message is truncated by the
    server's ``except ValueError`` branch.
    """
    paths = resolve_year_paths(project_root, year_token, workspace_root=workspace_root)
    try:
        run_year(project_root, year_token, workspace_root=workspace_root)
    except StageFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize at boundary
        raise StageFailure.from_exception(exc) from exc
    return {
        "status": "completed",
        "outputs": build_output_manifest(paths),
    }


def start_run(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """H1: kick off ``run_year`` in a background thread, return ``run_id``."""
    return start_background_run(
        project_root, year_token, workspace_root=workspace_root
    )


def status_run(
    project_root: Path,
    year_token: str,
    run_id: str,
    *,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """H1: poll status by ``run_id``. Returns the streaming progress
    events plus a status summary (``running`` / ``completed`` / ``failed``)
    and, on completion, the output manifest the wizard's Outputs screen
    consumes.
    """
    paths = resolve_year_paths(project_root, year_token, workspace_root=workspace_root)
    payload = read_run_status(paths, run_id)
    if payload.get("status") == "completed":
        payload["outputs"] = build_output_manifest(paths)
    return payload
