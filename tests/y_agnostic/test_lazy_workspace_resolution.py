"""Regression tests for invariant migration plan WS-5D.

Background — the migration plan §7 / WS-5D requires that pipeline modules
which are tightly coupled to the runtime workspace (germany_loaders,
germany_projections, us_model) defer all workspace-path resolution to
function call time, not module import time. The previous shape resolved
``YEAR_PATHS = active_year_paths(...)`` at module top level, which fires
filesystem ``stat`` / ``is_dir`` calls before any explicit pipeline call
and freezes those values for the lifetime of the import — breaking the
Phase-1/Phase-2/Phase-3 separation the audit graph depends on.

These tests assert that importing the pipeline module performs zero
filesystem I/O. Pipeline runs that legitimately need the paths must call
the lazy ``_year_paths()`` accessor (or a public function that does so).

References:
- ``docs/invariant-migration-plan.md`` §7 / WS-5D — "Move module-level
  workspace resolution to function-scope" (Medium, M4).
- ``tax_pipeline.year_runtime.active_year_paths`` (the resolver).
- The corresponding fix lives in
  ``tax_pipeline/pipelines/y2025/germany_loaders.py`` and
  ``tax_pipeline/pipelines/y2025/germany_projections.py``.
"""

from __future__ import annotations

import builtins
import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock


PIPELINE_MODULES = (
    "tax_pipeline.pipelines.y2025.germany_loaders",
    "tax_pipeline.pipelines.y2025.germany_projections",
    "tax_pipeline.pipelines.y2025.us_model",
)


def _drop_module_cache(*module_names: str) -> None:
    """Remove the named modules and their submodules from ``sys.modules``.

    Required so that ``importlib.import_module`` actually re-executes the
    module body under our patched I/O guards. A normal ``import`` after the
    test process has already imported the module is a no-op.
    """
    drop = set(module_names)
    for name in list(sys.modules):
        for target in module_names:
            if name == target or name.startswith(target + "."):
                drop.add(name)
    for name in drop:
        sys.modules.pop(name, None)


class LazyWorkspaceResolutionTest(unittest.TestCase):
    """Importing the pipeline modules must not touch the filesystem.

    Workspace resolution is a Phase-1 input to a pipeline run; module import
    is supposed to be a pure code-loading step. Mixing the two means import
    order silently encodes which workspace the pipeline will see, and a
    test that wants to swap workspaces has to monkeypatch module globals.
    """

    def _assert_zero_io_on_import(self, module_name: str) -> None:
        # Drop both the target module and any pipeline siblings that may have
        # been imported by an earlier test in the same process. Without this
        # the module body never re-runs and the I/O guards see nothing.
        _drop_module_cache(*PIPELINE_MODULES)

        observed_calls: list[tuple[str, str]] = []

        def _record(method_name: str):
            def _capture(self, *_a, **_kw):  # pragma: no cover - guard helper
                observed_calls.append((method_name, str(self)))
                raise AssertionError(
                    f"Path.{method_name} called during import of {module_name} "
                    f"on {self!s}; workspace resolution must be lazy."
                )
            return _capture

        def _record_open(*args, **_kwargs):  # pragma: no cover - guard helper
            target = args[0] if args else "<unknown>"
            observed_calls.append(("open", str(target)))
            raise AssertionError(
                f"builtins.open called during import of {module_name} on "
                f"{target!s}; workspace resolution must be lazy."
            )

        with mock.patch.object(Path, "is_dir", _record("is_dir")), \
             mock.patch.object(Path, "exists", _record("exists")), \
             mock.patch.object(Path, "stat", _record("stat")), \
             mock.patch.object(Path, "read_text", _record("read_text")), \
             mock.patch.object(Path, "read_bytes", _record("read_bytes")), \
             mock.patch.object(builtins, "open", _record_open):
            try:
                importlib.import_module(module_name)
            except AssertionError:
                # The recorder raises AssertionError to surface the offending
                # call site; record_calls already contains the offender.
                self.fail(
                    f"{module_name} performs filesystem I/O at import time: "
                    f"{observed_calls}"
                )

        self.assertEqual(
            observed_calls,
            [],
            f"Unexpected I/O during import of {module_name}: {observed_calls}",
        )

    def test_pipeline_modules_import_is_io_free(self) -> None:
        # All three workspace-coupled pipeline modules must defer I/O to
        # function-call time (WS-5D). One subTest per module so a regression
        # still points at the offending module by name.
        for module_name in PIPELINE_MODULES:
            with self.subTest(module=module_name):
                self._assert_zero_io_on_import(module_name)

    def test_germany_loaders_exposes_lazy_year_paths_helper(self) -> None:
        """The fix-shape requires a public lazy accessor.

        Other modules (e.g. germany_model.main) need a callable they can
        invoke after they've configured the workspace. The plan names this
        ``_year_paths()`` (private by Python convention but exposed as the
        canonical accessor for in-package consumers).
        """
        _drop_module_cache(*PIPELINE_MODULES)
        module = importlib.import_module(
            "tax_pipeline.pipelines.y2025.germany_loaders"
        )
        self.assertTrue(
            callable(getattr(module, "_year_paths", None)),
            "germany_loaders must expose a lazy _year_paths() accessor.",
        )


if __name__ == "__main__":  # pragma: no cover - manual harness
    unittest.main()
