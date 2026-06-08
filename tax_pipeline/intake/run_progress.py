"""Background-run progress tracking for the local intake wizard.

Why this module exists: the wizard's prior ``POST /api/run`` was synchronous —
the browser tab held a single in-flight request for the duration of a real
cross-border return (tens of pipeline modules, dozens of stages). The user
saw a frozen tab for minutes with no indication of progress.

This module provides:

* ``start_run(project_root, year, workspace_root)`` — allocates a new
  ``run_id``, persists the initial event to
  ``outputs/run_progress/<run_id>.jsonl`` (JSON-lines, one event per line),
  and kicks off the pipeline in a background thread.

* ``read_run_status(year_paths, run_id)`` — reads the JSONL trace, returns
  the ordered list of events and a ``status`` summary (``running`` /
  ``completed`` / ``failed``).

* ``ProgressEmitter`` — a callable handed to ``run_year`` so the engine can
  emit ``stage_started`` / ``stage_completed`` events as each pipeline module
  enters and exits.

Design notes:

* The on-disk JSONL append is the single source of truth. The wizard polls
  the file roughly every 500ms; we never hold progress only in memory.
* Each append is a single-line write; line-oriented append is atomic on
  POSIX up to PIPE_BUF (~4 KiB), which is more than enough for these
  events.
* Events carry monotonic ISO-8601 timestamps so the wizard can show elapsed
  time per stage.
* We deliberately do NOT use websockets / SSE / asyncio. Polling a small
  JSONL file from stdlib ``http.server`` is sufficient for a single-user
  local wizard, and avoids new dependencies (per CLAUDE.md / project spec).

H2 hand-off: the background thread captures ``StageFailure`` from the
pipeline boundary and persists a ``failed`` event carrying the structured
``(stage_id, rule_id, missing_input_key, authority_url, original_message)``
fields. The wizard's status endpoint surfaces those verbatim so the UI can
render a labeled error card.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from tax_pipeline.year_runtime import resolve_year_paths


# Public type for callbacks plumbed into ``run_year``. Stages call into
# this with a mutable mapping of event fields (``stage_id``, ``phase``,
# ``module`` etc.).
ProgressCallback = Callable[[dict[str, Any]], None]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _progress_root(year_paths) -> Path:
    return year_paths.outputs_root / "run_progress"


def _progress_path(year_paths, run_id: str) -> Path:
    return _progress_root(year_paths) / f"{run_id}.jsonl"


def _validate_run_id(run_id: str) -> str:
    """Permit only ``[A-Za-z0-9_-]+`` so the run_id can be safely joined to
    a filesystem path. Any other character is rejected."""
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    for ch in run_id:
        if not (ch.isalnum() or ch in {"_", "-"}):
            raise ValueError(
                f"run_id may only contain letters, digits, '-' or '_'; "
                f"got {ch!r} in {run_id!r}"
            )
    return run_id


def _append_event(progress_path: Path, event: dict[str, Any]) -> None:
    """Append a single JSON-encoded line. The parent directory is
    expected to exist already. ``open(path, "a")`` performs an O_APPEND
    write; on POSIX writes up to PIPE_BUF are atomic, which is far more
    than these short events need.
    """
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, sort_keys=True) + "\n"
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(line)


@dataclass
class ProgressEmitter:
    """Callable wrapper around the JSONL writer.

    Threaded into ``run_year(progress_callback=...)`` so each pipeline
    module / phase records its entry and exit. The emitter also tracks the
    most recent open ``stage_id`` so a top-level exception handler can
    attribute the failure to the correct stage even if the rule body
    raised before emitting an explicit completion event.
    """

    progress_path: Path
    started_at_monotonic: float = field(default_factory=time.monotonic)
    current_stage_id: str | None = None

    def emit(self, event: dict[str, Any]) -> None:
        payload = dict(event)
        payload.setdefault("ts", _now_iso())
        payload.setdefault(
            "elapsed_seconds",
            round(time.monotonic() - self.started_at_monotonic, 3),
        )
        if payload.get("event") == "stage_started":
            self.current_stage_id = str(payload.get("stage_id") or "") or None
        elif payload.get("event") == "stage_completed":
            self.current_stage_id = None
        _append_event(self.progress_path, payload)

    def __call__(self, event: dict[str, Any]) -> None:
        self.emit(event)


def _read_events(progress_path: Path) -> list[dict[str, Any]]:
    if not progress_path.exists():
        return []
    events: list[dict[str, Any]] = []
    text = progress_path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            # Tolerate partial writes during concurrent polling: skip
            # malformed lines rather than failing the status read.
            continue
    return events


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute a summary block for the status endpoint.

    The summary carries the status (``pending`` if no events yet,
    ``running`` while at least one stage is open, ``completed`` /
    ``failed`` once the terminal event arrives), plus the currently-open
    stage_id (if any) so the wizard can show a "running …" indicator.
    """
    if not events:
        return {"status": "pending", "current_stage_id": None}

    current_stage: str | None = None
    open_stage_started_at: str | None = None
    open_modules: list[tuple[str, str]] = []  # (module, started_at)
    completed = False
    failed: dict[str, Any] | None = None
    for event in events:
        kind = event.get("event")
        if kind == "stage_started":
            current_stage = str(event.get("stage_id") or "") or current_stage
            open_stage_started_at = event.get("ts")
        elif kind == "stage_completed":
            current_stage = None
            open_stage_started_at = None
        elif kind == "run_completed":
            completed = True
        elif kind == "run_failed":
            failed = {
                "stage_id": event.get("stage_id"),
                "rule_id": event.get("rule_id"),
                "missing_input_key": event.get("missing_input_key"),
                "authority_url": event.get("authority_url"),
                "original_message": event.get("original_message")
                or event.get("message"),
                "kind": event.get("kind") or "stage_failure",
            }

    if failed is not None:
        return {
            "status": "failed",
            "current_stage_id": None,
            "failure": failed,
        }
    if completed:
        return {"status": "completed", "current_stage_id": None}
    return {
        "status": "running",
        "current_stage_id": current_stage,
        "current_stage_started_at": open_stage_started_at,
    }


def read_run_status(year_paths, run_id: str) -> dict[str, Any]:
    """Read the on-disk JSONL trace for ``run_id`` and produce a wizard-
    friendly payload (``status``, ``events``, optional ``failure``)."""
    _validate_run_id(run_id)
    progress_path = _progress_path(year_paths, run_id)
    events = _read_events(progress_path)
    summary = _summarize(events)
    return {
        "run_id": run_id,
        "events": events,
        **summary,
    }


def list_recent_runs(year_paths, limit: int = 5) -> list[dict[str, Any]]:
    """Return the most recent ``limit`` run summaries (sorted by mtime
    descending). Useful for tests and a future "history" panel."""
    root = _progress_root(year_paths)
    if not root.exists():
        return []
    paths = sorted(root.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in paths[:limit]:
        run_id = path.stem
        out.append(read_run_status(year_paths, run_id))
    return out


def _allocate_run_id() -> str:
    return secrets.token_urlsafe(8).replace("=", "").replace("/", "_").replace("+", "-")


def start_run(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
    run_year_callable: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Allocate a ``run_id``, write an initial ``run_started`` event, and
    kick off the pipeline in a background thread.

    Returns ``{"run_id": ..., "status": "running"}`` immediately so the
    wizard can pivot to polling without holding the request open.

    The ``run_year_callable`` indirection exists for tests — production
    callers leave it ``None`` and the function is resolved lazily to
    ``tax_pipeline.run_year.run_year``.
    """
    paths = resolve_year_paths(project_root, str(year_token), workspace_root=workspace_root)
    paths.outputs_root.mkdir(parents=True, exist_ok=True)
    _progress_root(paths).mkdir(parents=True, exist_ok=True)

    run_id = _allocate_run_id()
    progress_path = _progress_path(paths, run_id)
    emitter = ProgressEmitter(progress_path=progress_path)
    emitter.emit(
        {
            "event": "run_started",
            "run_id": run_id,
            "year": str(paths.year),
            "workspace_root": str(paths.workspace_root),
        }
    )

    # Resolve the runner lazily so the import does not load the engine
    # graph until a run actually starts (and so tests can inject a stub).
    if run_year_callable is None:
        from tax_pipeline.run_year import run_year as _run_year  # local import

        run_year_callable = _run_year

    def _run() -> None:
        try:
            run_year_callable(
                project_root,
                str(year_token),
                workspace_root=workspace_root,
                progress_callback=emitter,
            )
        except BaseException as exc:  # noqa: BLE001 - we re-raise via JSONL
            # H2: wrap arbitrary exceptions into a ``StageFailure`` at this
            # wizard-boundary site so the JSONL trace carries the
            # structured ``(stage_id, rule_id, missing_input_key,
            # authority_url, original_message)`` triple. The most recent
            # open stage_id comes from the emitter — that is the stage
            # the user was watching turn yellow when the run died.
            from tax_pipeline.run_year import StageFailure

            if isinstance(exc, StageFailure):
                failure = exc
            else:
                failure = StageFailure.from_exception(
                    exc,
                    stage_id=emitter.current_stage_id,
                    rule_id=emitter.current_stage_id,
                )
            payload: dict[str, Any] = {
                "event": "run_failed",
                "run_id": run_id,
                "kind": exc.__class__.__name__,
                **failure.as_dict(),
            }
            try:
                emitter.emit(payload)
            except Exception:  # noqa: BLE001 - never let logging crash the thread
                pass
            return
        emitter.emit({"event": "run_completed", "run_id": run_id})

    thread = threading.Thread(target=_run, name=f"tax-run-{run_id}", daemon=True)
    thread.start()
    return {"run_id": run_id, "status": "running"}
