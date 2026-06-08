from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from tax_pipeline.paths import YearPaths


_CATEGORY_ORDER = {
    "Narratives": 0,
    "Final Legal Output": 1,
    "Filing Packages": 2,
    "Legal Audits": 3,
    "Analysis Workpapers": 4,
    "Tax Positions": 5,
    "Facts Review": 6,
    "Other Outputs": 7,
}

_SPECIAL_LABELS = {
    "outputs/analysis-steps/final-legal-output.json": "Final legal output JSON",
    "outputs/analysis-steps/DE-de-narrative.md": "Germany legal narrative, German",
    "outputs/analysis-steps/DE-en-narrative.md": "Germany legal narrative, English",
    "outputs/analysis-steps/US-en-narrative.md": "U.S. legal narrative, English",
    "outputs/analysis-steps/verbose-report.md": "Verbose legal calculation report",
    "outputs/analysis-steps/germany-elster-entry-sheet.md": "Germany ELSTER entry sheet",
    "outputs/analysis-steps/us-treaty-entry-sheet.md": "U.S. treaty entry sheet",
    "outputs/forms/germany/index.md": "Germany filing package index",
    "outputs/forms/usa/index.md": "U.S. filing package index",
    "outputs/legal-audit/germany/index.md": "Germany legal audit index",
    "outputs/legal-audit/usa/index.md": "U.S. legal audit index",
    "normalized/facts/REVIEW.md": "Extracted facts review index",
}


def _is_relative_safe(relative_path: str) -> bool:
    path = Path(relative_path)
    return not path.is_absolute() and ".." not in path.parts


def _is_allowed_download_path(relative_path: str) -> bool:
    if not _is_relative_safe(relative_path):
        return False
    path = Path(relative_path)
    if not path.parts:
        return False
    if path.parts[0] == "outputs":
        return True
    return relative_path == "normalized/facts/REVIEW.md"


def _category_for(relative_path: str) -> str:
    if relative_path.endswith("-narrative.md"):
        return "Narratives"
    if relative_path == "outputs/analysis-steps/final-legal-output.json":
        return "Final Legal Output"
    if relative_path.startswith("outputs/forms/"):
        return "Filing Packages"
    if relative_path.startswith("outputs/legal-audit/"):
        return "Legal Audits"
    if relative_path.startswith("outputs/tax-positions/"):
        return "Tax Positions"
    if relative_path == "normalized/facts/REVIEW.md":
        return "Facts Review"
    if relative_path.startswith("outputs/analysis-steps/"):
        return "Analysis Workpapers"
    return "Other Outputs"


def _label_for(relative_path: str) -> str:
    if relative_path in _SPECIAL_LABELS:
        return _SPECIAL_LABELS[relative_path]
    name = Path(relative_path).name
    return name.replace("_", " ").replace("-", " ").removesuffix(".md").removesuffix(".json").title()


def _iter_generated_files(paths: YearPaths) -> list[Path]:
    files: list[Path] = []
    if paths.outputs_root.exists():
        files.extend(path for path in paths.outputs_root.rglob("*") if path.is_file() and not path.name.startswith("."))
    if paths.facts_root.exists():
        review_path = paths.facts_root / "REVIEW.md"
        if review_path.exists():
            files.append(review_path)
    return files


def build_output_manifest(paths: YearPaths) -> dict[str, object]:
    workspace_root = paths.year_root.resolve()
    files: list[dict[str, object]] = []
    for path in _iter_generated_files(paths):
        try:
            relative_path = path.resolve().relative_to(workspace_root).as_posix()
        except ValueError:
            continue
        if not _is_allowed_download_path(relative_path):
            continue
        category = _category_for(relative_path)
        download_url = "/api/output-download?" + urlencode(
            {
                "year": str(paths.year),
                "path": relative_path,
            }
        )
        files.append(
            {
                "label": _label_for(relative_path),
                "category": category,
                "relative_path": relative_path,
                "download_url": download_url,
                "size_bytes": path.stat().st_size,
            }
        )
    files.sort(key=lambda item: (_CATEGORY_ORDER.get(str(item["category"]), 99), str(item["relative_path"])))
    return {
        "workspace": {"year": str(paths.year), "path_redacted": True},
        "locations": {
            "outputs": "outputs/",
            "facts_review": "normalized/facts/REVIEW.md",
            "analysis": "outputs/analysis-steps/",
            "forms": "outputs/forms/",
            "legal_audit": "outputs/legal-audit/",
            "tax_positions": "outputs/tax-positions/",
        },
        "files": files,
    }


def read_generated_output(paths: YearPaths, relative_path: str) -> Path:
    if not _is_allowed_download_path(relative_path):
        raise PermissionError("Downloads are limited to generated outputs for this workspace.")
    path = (paths.year_root / relative_path).resolve()
    workspace_root = paths.year_root.resolve()
    if workspace_root != path and workspace_root not in path.parents:
        raise PermissionError("Downloads are limited to generated outputs for this workspace.")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(relative_path)
    return path


__all__ = ["build_output_manifest", "read_generated_output"]
