from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_DIR = REPO_ROOT / "tax_pipeline"

# Statute / agency URL hosts that must only appear in law modules. Renderers
# (tax_pipeline/forms/**) and pipeline composition (tax_pipeline/pipelines/**)
# must import URL constants from law modules so a single edit propagates
# everywhere.
STATUTE_URL_HOSTS = (
    "gesetze-im-internet.de",
    "irs.gov",
    "uscode.house.gov",
    "bzst.de",
    "bundesfinanzministerium.de",
    "elster.de",
)

# Directories that must be free of statute URL string literals.
SCAN_DIRS = (
    TAX_PIPELINE_DIR / "pipelines",
    TAX_PIPELINE_DIR / "forms",
)


class StatuteURLCentralizationTest(unittest.TestCase):
    """Per CLAUDE.md, every tax-rule citation must dereference a single
    canonical URL constant. Renderer-side or pipeline-side string literals
    drift silently from the audit graph when the underlying statute page is
    rolled forward. Concentrating URLs in `tax_pipeline/y2025/germany_law.py`,
    `tax_pipeline/y2025/us_law.py`, and `tax_pipeline/y2025/treaty_law.py` makes
    the citation surface auditable and one-edit upgradable.
    """

    def test_no_statute_url_string_literals_in_pipelines_or_forms(self) -> None:
        offenders: list[str] = []
        host_pattern = re.compile(
            r'"https?://[^"]*?(' + "|".join(re.escape(h) for h in STATUTE_URL_HOSTS) + r')[^"]*"'
        )
        for scan_dir in SCAN_DIRS:
            if not scan_dir.exists():
                continue
            for py_file in scan_dir.rglob("*.py"):
                text = py_file.read_text(encoding="utf-8")
                for match in host_pattern.finditer(text):
                    line_no = text[: match.start()].count("\n") + 1
                    offenders.append(f"{py_file.relative_to(REPO_ROOT)}:{line_no}: {match.group(0)}")
        self.assertEqual(
            offenders,
            [],
            "Found statute/agency URL string literals in pipelines/forms; "
            "import the URL from tax_pipeline.y2025.germany_law / "
            "tax_pipeline.y2025.us_law / tax_pipeline.y2025.treaty_law instead.",
        )


if __name__ == "__main__":
    unittest.main()
