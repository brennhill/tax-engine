from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from tax_pipeline.paths import YearPaths


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def demo_source_root(*, demo_name: str = "demo-2025") -> Path:
    source = _project_root() / "years" / demo_name
    if not source.exists():
        raise FileNotFoundError(f"Missing synthetic demo workspace: {source}")
    return source


def materialize_demo_workspace(
    project_root: Path,
    *,
    demo_name: str = "demo-2025",
    year: int = 2025,
) -> YearPaths:
    source = demo_source_root(demo_name=demo_name)
    target = YearPaths.for_year(project_root, year)
    if target.year_root.exists():
        shutil.rmtree(target.year_root)
    target.year_root.mkdir(parents=True, exist_ok=True)

    for child in source.iterdir():
        destination = target.year_root / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)

    target.ensure_directories()
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Materialize the checked-in synthetic demo workspace into a numeric year tree.",
    )
    parser.add_argument("--demo-name", default="demo-2025")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Target project root where years/<year>/ will be created.",
    )
    args = parser.parse_args(argv)

    materialized = materialize_demo_workspace(
        args.project_root.resolve(),
        demo_name=args.demo_name,
        year=args.year,
    )
    print(materialized.year_root)


if __name__ == "__main__":
    main()
