from __future__ import annotations

import json
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
                "preview_eligible": is_preview_eligible(relative_path),
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


# Cap preview body sizes so a single render call cannot blow the JSON
# response. Real narratives are ~50-200 KB; 256 KB headroom covers them
# while still bounding pathological cases.
PREVIEW_MAX_BODY_BYTES = 256 * 1024

# JSON-preview highlight keys. The final-legal-output.json package
# carries the refund/tax stories under per-jurisdiction subtrees. We
# pull the highest-value figures so the user sees the bottom line
# without opening the raw file. Keep in lockstep with the rule outputs
# in tax_pipeline/pipelines/y2025/{germany_model,us_model}.py — the
# bilingual-summary template fills the same fields, so adding a field
# here usually means adding it there too.
_HIGHLIGHT_SPECS: tuple[dict[str, str], ...] = (
    {
        "label": "Germany — final refund / due",
        "jsonpath": "germany.refunds.final_target_refund_eur",
        "currency": "EUR",
        "detail": "§ 36 EStG; final refund or balance due after prepayments and withholding.",
    },
    {
        "label": "Germany — total income tax",
        "jsonpath": "germany.refunds.total_income_tax_eur",
        "currency": "EUR",
        "detail": "§ 32a EStG; income tax before payments are credited.",
    },
    {
        "label": "U.S. — refund without treaty re-sourcing",
        "jsonpath": "usa.payments.refund_without_treaty_resourcing_usd",
        "currency": "USD",
        "detail": "26 U.S.C. § 6402; refund position absent the DBA-USA Art. 23 claim.",
    },
    {
        "label": "U.S. — refund with treaty re-sourcing",
        "jsonpath": "usa.payments.refund_with_treaty_resourcing_usd",
        "currency": "USD",
        "detail": "DBA-USA Art. 23 + IRS Pub. 514; refund after Article 23(5)(c) re-sourcing.",
    },
    {
        "label": "U.S. — total tax (treaty resourced)",
        "jsonpath": "usa.tax.total_tax_with_treaty_resourcing_usd",
        "currency": "USD",
        "detail": "26 U.S.C. § 1 + § 904; total federal income tax after treaty FTC.",
    },
)


def _follow_jsonpath(payload: object, jsonpath: str) -> object:
    cur: object = payload
    for piece in jsonpath.split("."):
        if not isinstance(cur, dict):
            return None
        if piece not in cur:
            return None
        cur = cur[piece]
    return cur


def _format_amount(value: object, currency: str) -> str:
    if value is None:
        return ""
    try:
        amount = float(str(value))
    except (TypeError, ValueError):
        return str(value)
    symbol = {"USD": "$", "EUR": "€"}.get(currency, "")
    formatted = f"{amount:,.2f}"
    return f"{symbol}{formatted}" if symbol else f"{formatted} {currency}"


def build_output_preview(paths: YearPaths, relative_path: str) -> dict[str, object]:
    """Produce a structured preview of a generated output file.

    Powers the in-app "Preview" buttons on the Outputs screen — the user
    sees the highest-value numbers and the narrative text without having
    to download anything. Three preview shapes:

    * **json** — parsed JSON plus a highlights list of cited refund / tax
      figures (final-legal-output.json).
    * **markdown** — raw markdown body for in-pane rendering (the
      DE / U.S. narratives, the verbose report).
    * **raw** — first N bytes of any other allowed text file.

    The same allowlist as ``read_generated_output`` governs access, so a
    preview cannot leak files outside the workspace's outputs surface.
    """
    path = read_generated_output(paths, relative_path)
    suffix = path.suffix.lower()
    raw_bytes = path.read_bytes()[:PREVIEW_MAX_BODY_BYTES]
    truncated = path.stat().st_size > PREVIEW_MAX_BODY_BYTES

    if suffix == ".json":
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return {
                "kind": "json",
                "relative_path": relative_path,
                "error": f"Failed to parse JSON: {exc}",
                "body_text": raw_bytes.decode("utf-8", errors="replace"),
                "truncated": truncated,
            }
        highlights: list[dict[str, str]] = []
        for spec in _HIGHLIGHT_SPECS:
            value = _follow_jsonpath(payload, spec["jsonpath"])
            if value is None:
                continue
            highlights.append(
                {
                    "label": spec["label"],
                    "amount": _format_amount(value, spec["currency"]),
                    "detail": spec["detail"],
                }
            )
        provenance = payload.get("_provenance") if isinstance(payload, dict) else None
        provenance_count = 0
        if isinstance(provenance, dict):
            rule_outputs = provenance.get("rule_outputs", {})
            if isinstance(rule_outputs, dict):
                for jurisdiction_outputs in rule_outputs.values():
                    if isinstance(jurisdiction_outputs, dict):
                        provenance_count += len(jurisdiction_outputs)
        return {
            "kind": "json",
            "relative_path": relative_path,
            "highlights": highlights,
            "provenance_count": provenance_count,
            "body_text": raw_bytes.decode("utf-8", errors="replace"),
            "truncated": truncated,
        }

    if suffix == ".md":
        return {
            "kind": "markdown",
            "relative_path": relative_path,
            "body_text": raw_bytes.decode("utf-8", errors="replace"),
            "truncated": truncated,
        }

    return {
        "kind": "raw",
        "relative_path": relative_path,
        "body_text": raw_bytes.decode("utf-8", errors="replace"),
        "truncated": truncated,
    }


# File paths whose Preview button gets surfaced on the Outputs screen.
# Adding a relative path here turns on the preview affordance in the UI
# without changing the JS — the renderer reads PREVIEWABLE_RELATIVE_PATHS
# via /api/outputs's "preview_eligible" boolean per file (see
# build_output_manifest below).
PREVIEW_ELIGIBLE_SUFFIXES: tuple[str, ...] = (
    "analysis-steps/final-legal-output.json",
    "analysis-steps/DE-de-narrative.md",
    "analysis-steps/DE-en-narrative.md",
    "analysis-steps/US-en-narrative.md",
    "analysis-steps/verbose-report.md",
)


def is_preview_eligible(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(normalized.endswith(suffix) for suffix in PREVIEW_ELIGIBLE_SUFFIXES)


__all__ = [
    "build_output_manifest",
    "build_output_preview",
    "is_preview_eligible",
    "read_generated_output",
]
