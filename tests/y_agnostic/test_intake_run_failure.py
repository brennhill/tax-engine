"""H2 tests for the structured ``StageFailure`` boundary.

Background: the wizard's old ``/api/run`` returned a single error string
("ValueError: ..."). Real fail-closed messages from the rule modules
embed a statute citation and a ``gesetze-im-internet.de`` /
``law.cornell.edu`` / ``irs.gov`` URL right in the message body — H2
lifts those into structured fields so the wizard renders a labeled
error card instead of a single opaque string.

These tests cover:

* ``StageFailure.from_exception`` lifts the authority URL and the
  ``missing input facts: [...]`` fragment out of typical fail-closed
  messages.
* The synchronous ``/api/run`` route returns HTTP 422 with the
  ``stage_failure`` payload when ``run_pipeline`` raises a
  ``StageFailure``.
* The streaming ``/api/run/status`` flow persists the same structured
  fields in the JSONL trace via ``ProgressEmitter`` + ``start_run`` so
  the wizard can render the error card from polling state alone.
"""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tax_pipeline.intake.run_progress import (
    ProgressEmitter,
    read_run_status,
    start_run,
)
from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.run_year import (
    StageFailure,
    _extract_authority_url,
    _extract_missing_input_key,
)
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ExtractAuthorityUrlTest(unittest.TestCase):
    def test_extract_authority_url_recognizes_official_hosts(self) -> None:
        # ``(message, expected, note)`` covering the two official-host
        # families the engine cites + trailing-punctuation stripping +
        # the "no url" branches.
        cases = (
            (
                "elections.germany_disability_pauschbetrag_transfer_split must "
                "have exactly 2 share(s) per § 33b Abs. 5 Satz 3 EStG. "
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                "https://www.gesetze-im-internet.de/estg/__33b.html",
                "gesetze-im-internet.de host",
            ),
            (
                "26 U.S.C. § 6012 cross-jurisdiction gate failed: "
                "https://www.law.cornell.edu/uscode/text/26/6012",
                "https://www.law.cornell.edu/uscode/text/26/6012",
                "law.cornell.edu host",
            ),
            (
                "see https://www.irs.gov/publications/p514.",
                "https://www.irs.gov/publications/p514",
                "trailing period stripped",
            ),
            ("plain message", None, "no URL → None"),
            ("", None, "empty → None"),
        )
        for message, expected, note in cases:
            with self.subTest(note=note):
                self.assertEqual(_extract_authority_url(message), expected)


class ExtractMissingInputKeyTest(unittest.TestCase):
    def test_lifts_missing_input_facts_fragment(self) -> None:
        message = "DE25-13 missing input facts: ['de.ordinary.gross_wages']"
        self.assertEqual(
            _extract_missing_input_key(message),
            "['de.ordinary.gross_wages']",
        )

    def test_returns_none_when_marker_absent(self) -> None:
        self.assertIsNone(_extract_missing_input_key("unrelated message"))


class StageFailureFromExceptionTest(unittest.TestCase):
    def test_constructs_with_lifted_url_and_missing_input(self) -> None:
        exc = ValueError(
            "DE25-13 missing input facts: ['de.ordinary.gross_wages']. "
            "https://www.gesetze-im-internet.de/estg/__19.html"
        )
        failure = StageFailure.from_exception(
            exc, stage_id="DE25-13", rule_id="DE25-13"
        )
        self.assertEqual(failure.stage_id, "DE25-13")
        self.assertEqual(
            failure.authority_url,
            "https://www.gesetze-im-internet.de/estg/__19.html",
        )
        self.assertEqual(
            failure.missing_input_key, "['de.ordinary.gross_wages']"
        )

    def test_as_dict_round_trips_all_fields(self) -> None:
        failure = StageFailure(
            stage_id="X",
            rule_id="X",
            missing_input_key="['k']",
            authority_url="https://example.invalid",
            original_message="X failed",
        )
        # Use a known-bad URL only as a structural-test value; the
        # real authority hosts are exercised in ExtractAuthorityUrlTest.
        self.assertEqual(
            failure.as_dict(),
            {
                "stage_id": "X",
                "rule_id": "X",
                "missing_input_key": "['k']",
                "authority_url": "https://example.invalid",
                "original_message": "X failed",
            },
        )


class HttpRunReturns422OnStageFailureTest(unittest.TestCase):
    def test_post_run_returns_422_with_structured_payload(self) -> None:
        def boom(*_args, **_kwargs):
            raise ValueError(
                "DE25-13 missing input facts: ['de.ordinary.gross_wages']. "
                "https://www.gesetze-im-internet.de/estg/__19.html"
            )

        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            ensure_year_scaffold(paths)

            with mock.patch("tax_pipeline.intake.commands.run_year", side_effect=boom):
                status, payload = dispatch_request(
                    PROJECT_ROOT,
                    "POST",
                    "/api/run",
                    body={"year": "2026", "workspace": str(workspace_root)},
                )

            self.assertEqual(status, 422)
            self.assertIn("stage_failure", payload)
            failure = payload["stage_failure"]
            self.assertEqual(
                failure["authority_url"],
                "https://www.gesetze-im-internet.de/estg/__19.html",
            )
            self.assertEqual(
                failure["missing_input_key"], "['de.ordinary.gross_wages']"
            )


class StreamingFlowPersistsStageFailureFieldsTest(unittest.TestCase):
    def test_run_failed_event_carries_authority_url_and_missing_key(self) -> None:
        def boom(project_root, year, *, workspace_root=None, progress_callback=None):
            progress_callback(
                {"event": "stage_started", "stage_id": "germany_model"}
            )
            raise ValueError(
                "germany_model missing input facts: ['de.ordinary.gross_wages']. "
                "https://www.gesetze-im-internet.de/estg/__19.html"
            )

        with tempfile.TemporaryDirectory() as tmp:
            workspace_root = Path(tmp) / "2026"
            paths = resolve_year_paths(
                PROJECT_ROOT, "2026", workspace_root=workspace_root
            )
            paths.ensure_directories()

            payload = start_run(
                PROJECT_ROOT,
                "2026",
                workspace_root=workspace_root,
                run_year_callable=boom,
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
            self.assertEqual(
                failure["authority_url"],
                "https://www.gesetze-im-internet.de/estg/__19.html",
            )
            self.assertEqual(
                failure["missing_input_key"], "['de.ordinary.gross_wages']"
            )

    def test_emitter_jsonl_lines_can_be_independently_replayed(self) -> None:
        # The on-disk JSONL trace is the single source of truth — a
        # second reader should see the same structured fields without
        # the in-memory ``ProgressEmitter``.
        with tempfile.TemporaryDirectory() as tmp:
            progress_path = Path(tmp) / "events.jsonl"
            emitter = ProgressEmitter(progress_path=progress_path)
            failure = StageFailure(
                stage_id="DE25-13",
                rule_id="DE25-13",
                missing_input_key="['de.ordinary.gross_wages']",
                authority_url="https://www.gesetze-im-internet.de/estg/__19.html",
                original_message="boom",
            )
            emitter.emit({"event": "run_started", "run_id": "x"})
            emitter.emit(
                {
                    "event": "run_failed",
                    "run_id": "x",
                    "kind": "ValueError",
                    **failure.as_dict(),
                }
            )

            lines = progress_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            import json as _json

            replayed = _json.loads(lines[1])
            self.assertEqual(replayed["stage_id"], "DE25-13")
            self.assertEqual(
                replayed["authority_url"],
                "https://www.gesetze-im-internet.de/estg/__19.html",
            )


if __name__ == "__main__":
    unittest.main()
