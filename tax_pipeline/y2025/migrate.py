from __future__ import annotations

from pathlib import Path

from tax_pipeline.manifest import write_manifest
from tax_pipeline.paths import YearPaths
from tax_pipeline.scaffold_year import ensure_year_scaffold


def migrate_2025(project_root: Path) -> YearPaths:
    """Prepare the canonical 2025 year tree.

    This function keeps the existing public entry point, but it no longer tries
    to reconstruct 2025 from root-level documents or older numbered workpapers.
    The `years/2025/` tree is now the single source of truth.
    """

    paths = YearPaths.for_year(project_root, 2025)
    paths.ensure_directories()
    ensure_year_scaffold(paths)
    write_manifest(paths.raw_root, paths.manifest_path, year=2025)
    return paths


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    migrate_2025(project_root)


if __name__ == "__main__":
    main()
