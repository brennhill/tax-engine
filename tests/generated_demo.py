from __future__ import annotations

import io
import tempfile
from contextlib import redirect_stdout
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Iterator
from pathlib import Path

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.paths import YearPaths
from tax_pipeline.run_year import run_year


@dataclass
class GeneratedDemoWorkspace:
    tempdir: tempfile.TemporaryDirectory
    paths: YearPaths
    stdout: str

    def cleanup(self) -> None:
        self.tempdir.cleanup()


def generate_demo_workspace() -> GeneratedDemoWorkspace:
    tempdir = tempfile.TemporaryDirectory()
    root = Path(tempdir.name)
    stdout = io.StringIO()
    paths = populate_demo_workspace(root, stdout=stdout)
    return GeneratedDemoWorkspace(tempdir=tempdir, paths=paths, stdout=stdout.getvalue())


def populate_demo_workspace(
    project_root: Path,
    *,
    year: int = 2025,
    stdout: io.StringIO | None = None,
) -> YearPaths:
    paths = materialize_demo_workspace(project_root, demo_name="demo-2025", year=year)
    buffer = stdout if stdout is not None else io.StringIO()
    with redirect_stdout(buffer):
        run_year(project_root, str(year), workspace_root=paths.year_root)
    return paths


@contextmanager
def generated_demo_paths() -> Iterator[YearPaths]:
    demo = generate_demo_workspace()
    try:
        yield demo.paths
    finally:
        demo.cleanup()
