from __future__ import annotations

import csv
import json

from tax_pipeline.paths import YearPaths


def _read_csv_rows(path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: value or "" for key, value in row.items() if key is not None} for row in csv.DictReader(handle)]


def workspace_metadata(paths: YearPaths) -> dict[str, object]:
    profile: dict[str, object] = {}
    if paths.profile_path.exists():
        profile = json.loads(paths.profile_path.read_text(encoding="utf-8"))

    jurisdictions = profile.get("jurisdictions", {}) if isinstance(profile, dict) else {}
    germany = jurisdictions.get("germany", {}) if isinstance(jurisdictions, dict) else {}
    usa = jurisdictions.get("usa", {}) if isinstance(jurisdictions, dict) else {}
    people_rows = _read_csv_rows(paths.people_path)

    return {
        "workspace_root": str(paths.workspace_root.resolve()),
        "year": paths.year,
        "exists": paths.workspace_root.exists(),
        "people_count": len(people_rows),
        "germany_enabled": bool(germany.get("enabled", False)),
        "germany_filing_posture": str(germany.get("filing_posture", "")),
        "usa_enabled": bool(usa.get("enabled", False)),
        "usa_filing_posture": str(usa.get("filing_posture", "")),
    }

