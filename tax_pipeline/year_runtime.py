from __future__ import annotations

import json
import os
from pathlib import Path

from tax_pipeline.paths import YearPaths


def _resolve_project_root(script_path: Path) -> Path:
    configured = os.environ.get("TAX_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()

    resolved = script_path.resolve()
    current = resolved if resolved.is_dir() else resolved.parent
    for candidate in [current, *current.parents]:
        if (candidate / "tax_pipeline").is_dir() and (candidate / "years").is_dir():
            return candidate
    return current


def _resolve_year(default_year: int) -> int:
    configured = os.environ.get("TAX_YEAR")
    return int(configured) if configured else default_year


def resolve_workspace_root(
    project_root: Path,
    year_token: str,
    *,
    explicit_workspace: Path | None = None,
) -> Path:
    if explicit_workspace is not None:
        return explicit_workspace.resolve()

    if year_token == "demo-2025":
        return (project_root / "years" / year_token).resolve()

    if year_token.isdigit():
        return (Path.home() / "taxes" / year_token).resolve()

    raise ValueError(f"Unsupported workspace target: {year_token}")


def resolve_numeric_year(year_token: str) -> int:
    if year_token == "demo-2025":
        return 2025
    if year_token.isdigit():
        return int(year_token)
    raise ValueError(f"Unsupported workspace target: {year_token}")


def resolve_year_paths(
    project_root: Path,
    year_token: str,
    *,
    workspace_root: Path | None = None,
) -> YearPaths:
    year = resolve_numeric_year(year_token)
    resolved_workspace = resolve_workspace_root(
        project_root,
        year_token,
        explicit_workspace=workspace_root,
    )
    return YearPaths.for_workspace(project_root, resolved_workspace, year)


def active_year_paths(script_path: Path, default_year: int = 2025) -> YearPaths:
    project_root = _resolve_project_root(script_path)
    year = _resolve_year(default_year)
    configured_workspace = os.environ.get("TAX_WORKSPACE_ROOT")
    if configured_workspace:
        return YearPaths.for_workspace(project_root, Path(configured_workspace).resolve(), year)
    return resolve_year_paths(project_root, str(year))


def analysis_root(script_path: Path, default_year: int = 2025) -> Path:
    configured = os.environ.get("TAX_ANALYSIS_DIR")
    if configured:
        return Path(configured).resolve()
    # Fix: the canonical pipeline always reads and writes through the year tree.
    # Falling back to a root-level `analysis-steps/` directory kept the old
    # compatibility shape alive and made the repo layout harder to reason about.
    return active_year_paths(script_path, default_year=default_year).analysis_root


def manifest_path(script_path: Path, default_year: int = 2025) -> Path:
    configured = os.environ.get("TAX_MANIFEST_PATH")
    if configured:
        return Path(configured).resolve()
    return active_year_paths(script_path, default_year=default_year).manifest_path


def load_manifest(paths: YearPaths) -> list[dict[str, object]]:
    if not paths.manifest_path.exists():
        return []
    return json.loads(paths.manifest_path.read_text(encoding="utf-8"))


def find_documents(
    paths: YearPaths,
    *,
    doc_type: str,
    tax_year: int | None = None,
    owner: str | None = None,
) -> list[Path]:
    matches: list[Path] = []
    for entry in load_manifest(paths):
        if entry.get("doc_type") != doc_type:
            continue
        if tax_year is not None and entry.get("tax_year") != tax_year:
            continue
        if owner is not None and entry.get("owner") != owner:
            continue
        matches.append(paths.raw_root / str(entry["relative_path"]))
    return sorted(matches)
