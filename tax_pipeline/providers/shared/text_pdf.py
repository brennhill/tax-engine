from __future__ import annotations

import subprocess
from pathlib import Path


def load_pdf_pages(path: Path) -> list[str]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    pages = [page for page in result.stdout.split("\f")]
    while pages and not pages[-1].strip():
        pages.pop()
    return pages
