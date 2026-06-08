"""Tests for the H1 streaming-progress flow.

The wizard's old ``/api/run`` POST blocked the browser tab for the whole
pipeline run. H1 replaces that with a background-thread runner plus
``/api/run/start`` and ``/api/run/status`` endpoints so the wizard can poll
stage progress every ~500ms and render a list of stages as they complete.

These tests cover:

* ``ProgressEmitter`` writes one JSON line per event and tracks the
  current open stage so failures attach to the right stage_id.
* ``read_run_status`` returns the ordered events and the right status
  summary for ``running`` / ``completed`` / ``failed`` runs.
* The HTTP boundary returns a 202 with a ``run_id`` from
  ``/api/run/start`` and an OK with events from ``/api/run/status``.
* The H2 ``StageFailure`` triple (``stage_id``, ``missing_input_key``,
  ``authority_url``, ``original_message``) survives the JSONL persistence
  and surfaces verbatim through ``/api/run/status``.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from tax_pipeline.intake.commands import status_run
from tax_pipeline.intake.run_progress import (
    ProgressEmitter,
    read_run_status,
    start_run,
)
from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ProgressEmitterTest(unittest.TestCase):
    def test_emit_appends_one_jsonl_line_per_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "events.jsonl"
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": "abc"})
            emitter.emit(
                {"event": "stage_started", "stage_id": "extract_facts"}
            )
            emitter.emit(
                {"event": "stage_completed", "stage_id": "extract_facts"}
            )
            emitter.emit({"event": "run_completed", "run_id": "abc"})

            lines = progress_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 4)
            for line in lines:
                payload = json.loads(line)
                self.assertIn("event", payload)
                self.assertIn("ts", payload)
                self.assertIn("elapsed_seconds", payload)

    def test_emit_tracks_current_stage_id_for_failure_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "events.jsonl"
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "stage_started", "stage_id": "germany_model"})
            self.assertEqual(emitter.current_stage_id, "germany_model")
            emitter.emit({"event": "stage_completed", "stage_id": "germany_model"})
            self.assertIsNone(emitter.current_stage_id)


class ReadRunStatusTest(unittest.TestCase):
    def test_pending_when_no_events_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            payload = read_run_status(paths, "missing-run")
            self.assertEqual(payload["status"], "pending")
            self.assertEqual(payload["events"], [])

    def test_running_when_stage_open(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()
            run_id = "test-run"
            progress_path = paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": run_id})
            emitter.emit({"event": "stage_started", "stage_id": "germany_model"})

            payload = read_run_status(paths, run_id)
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["current_stage_id"], "germany_model")

    def test_completed_status_after_run_completed_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()
            run_id = "done"
            progress_path = paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": run_id})
            emitter.emit({"event": "stage_started", "stage_id": "scaffold"})
            emitter.emit({"event": "stage_completed", "stage_id": "scaffold"})
            emitter.emit({"event": "run_completed", "run_id": run_id})

            payload = read_run_status(paths, run_id)
            self.assertEqual(payload["status"], "completed")

    def test_failed_status_carries_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()
            run_id = "boom"
            progress_path = paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": run_id})
            emitter.emit(
                {
                    "event": "run_failed",
                    "run_id": run_id,
                    "stage_id": "DE25-13",
                    "rule_id": "DE25-13",
                    "missing_input_key": "de.ordinary.gross_wages",
                    "authority_url": "https://www.gesetze-im-internet.de/estg/__19.html",
                    "original_message": "DE25-13 missing input facts: ['de.ordinary.gross_wages']",
                }
            )

            payload = read_run_status(paths, run_id)
            self.assertEqual(payload["status"], "failed")
            failure = payload["failure"]
            self.assertEqual(failure["stage_id"], "DE25-13")
            self.assertEqual(
                failure["authority_url"],
                "https://www.gesetze-im-internet.de/estg/__19.html",
            )
            self.assertEqual(
                failure["missing_input_key"], "de.ordinary.gross_wages"
            )

    def test_run_id_must_be_path_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()
            with self.assertRaises(ValueError):
                read_run_status(paths, "../escape")
            with self.assertRaises(ValueError):
                read_run_status(paths, "")


class StartRunBackgroundTest(unittest.TestCase):
    def test_start_run_kicks_off_thread_and_emits_events(self) -> None:
        events_seen: list[dict] = []
        done = threading.Event()

        def fake_run(project_root, year, *, workspace_root=None, progress_callback=None):
            progress_callback({"event": "stage_started", "stage_id": "scaffold"})
            progress_callback({"event": "stage_completed", "stage_id": "scaffold"})
            events_seen.append({"ran": True})
            done.set()

        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            from tax_pipeline.intake.run_progress import start_run as direct_start
            payload = direct_start(
                PROJECT_ROOT,
                "2026",
                workspace_root=workspace_root,
                run_year_callable=fake_run,
            )
            self.assertEqual(payload["status"], "running")
            self.assertTrue(payload["run_id"])

            self.assertTrue(done.wait(5.0), "background runner did not finish")
            # Give the thread a moment to write the run_completed event.
            for _ in range(20):
                status = read_run_status(paths, payload["run_id"])
                if status["status"] == "completed":
                    break
                time.sleep(0.05)

            self.assertEqual(status["status"], "completed")
            kinds = [event["event"] for event in status["events"]]
            self.assertIn("run_started", kinds)
            self.assertIn("stage_started", kinds)
            self.assertIn("stage_completed", kinds)
            self.assertIn("run_completed", kinds)

    def test_start_run_persists_run_failed_with_open_stage_id(self) -> None:
        # Plain exceptions raised from inside a stage attribute the
        # failure to the most recent open ``stage_id`` recorded by the
        # emitter, so the wizard's polling endpoint can show "germany_model
        # failed" instead of just dumping the message.
        def fake_run(project_root, year, *, workspace_root=None, progress_callback=None):
            progress_callback({"event": "stage_started", "stage_id": "germany_model"})
            raise RuntimeError("synthetic boom inside germany_model")

        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            from tax_pipeline.intake.run_progress import start_run as direct_start
            payload = direct_start(
                PROJECT_ROOT,
                "2026",
                workspace_root=workspace_root,
                run_year_callable=fake_run,
            )

            run_id = payload["run_id"]
            for _ in range(40):
                status = read_run_status(paths, run_id)
                if status["status"] in {"failed", "completed"}:
                    break
                time.sleep(0.05)

            self.assertEqual(status["status"], "failed")
            failure = status["failure"]
            self.assertEqual(failure["stage_id"], "germany_model")
            self.assertIn("synthetic boom", failure["original_message"])


class HttpBoundaryTest(unittest.TestCase):
    def test_post_run_start_returns_202_with_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            ensure_year_scaffold(paths)

            # The HTTP-boundary contract under test is "start_run kicks
            # off a background thread and returns immediately with a
            # run_id". The real ``run_year`` will fail in the worker
            # thread because the demo workspace is not fully populated,
            # but that fails into the JSONL trace as a ``run_failed``
            # event — the foreground HTTP response stays 202 with the
            # ``run_id``.
            status, payload = dispatch_request(
                PROJECT_ROOT,
                "POST",
                "/api/run/start",
                body={"year": "2026", "workspace": str(workspace_root)},
            )

            self.assertEqual(status, 202)
            self.assertEqual(payload["status"], "running")
            self.assertTrue(payload["run_id"])

            run_id = payload["run_id"]
            progress_path = (
                paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            )
            for _ in range(50):
                if progress_path.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(progress_path.exists())

    def test_get_run_status_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            run_id = "reuse"
            progress_path = paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": run_id})
            emitter.emit({"event": "stage_started", "stage_id": "extract_facts"})
            emitter.emit({"event": "stage_completed", "stage_id": "extract_facts"})

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                (
                    f"/api/run/status?year=2026&workspace={workspace_root}"
                    f"&run_id={run_id}"
                ),
            )
            self.assertEqual(status, 200)
            self.assertEqual(payload["status"], "running")
            kinds = [event["event"] for event in payload["events"]]
            self.assertIn("stage_started", kinds)

    def test_get_run_status_rejects_missing_run_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            status, payload = dispatch_request(
                PROJECT_ROOT,
                "GET",
                f"/api/run/status?year=2026&workspace={workspace_root}",
            )
            self.assertEqual(status, 400)
            self.assertIn("run_id", payload["error"])

    def test_status_run_command_returns_outputs_when_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()
            run_id = "done"
            progress_path = paths.outputs_root / "run_progress" / f"{run_id}.jsonl"
            progress_path.parent.mkdir(parents=True, exist_ok=True)
            emitter = ProgressEmitter(progress_path=progress_path)
            emitter.emit({"event": "run_started", "run_id": run_id})
            emitter.emit({"event": "run_completed", "run_id": run_id})

            payload = status_run(
                PROJECT_ROOT, "2026", run_id, workspace_root=workspace_root
            )
            self.assertEqual(payload["status"], "completed")
            self.assertIn("outputs", payload)


if __name__ == "__main__":
    unittest.main()
