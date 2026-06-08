from __future__ import annotations

import json
from pathlib import Path

from tax_pipeline.classify import classify_relative_path


def build_manifest(raw_root: Path, year: int) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for path in sorted(p for p in raw_root.rglob("*") if p.is_file()):
        if any(part.startswith(".") for part in path.relative_to(raw_root).parts):
            continue
        relative_path = path.relative_to(raw_root)
        entry = classify_relative_path(relative_path)
        if entry["tax_year"] is None:
            entry["tax_year"] = year
        entries.append(entry)
    return entries


def write_manifest(raw_root: Path, manifest_path: Path, year: int) -> list[dict[str, object]]:
    manifest = build_manifest(raw_root, year=year)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest
