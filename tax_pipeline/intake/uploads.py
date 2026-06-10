from __future__ import annotations

import json
from pathlib import Path

from tax_pipeline.classify import classify_relative_path
from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.manifest import write_manifest
from tax_pipeline.paths import (
    ASSET_CLASS_BUCKETS,
    JURISDICTION_BUCKETS,
    JURISDICTION_LEGACY_NAMES,
    RAW_BUCKETS,
    YearPaths,
    all_raw_bucket_names,
    canonical_bucket_path,
    has_legacy_raw_layout,
)
from tax_pipeline.scaffold_year import ensure_year_scaffold

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def _upload_index_path(paths: YearPaths) -> Path:
    return paths.raw_root / ".intake-uploads.json"


def _load_upload_index(paths: YearPaths) -> list[dict[str, object]]:
    index_path = _upload_index_path(paths)
    if not index_path.exists():
        return []
    return json.loads(index_path.read_text(encoding="utf-8"))


def _write_upload_index(paths: YearPaths, entries: list[dict[str, object]]) -> None:
    # Atomic write (invariant I9 — unique temp filename + parent fsync)
    # so a concurrent upload or a crash mid-write cannot leave a torn
    # JSON index on disk for the next list_uploads call.
    index_path = _upload_index_path(paths)
    atomic_write_text(index_path, json.dumps(entries, indent=2) + "\n")


def _confidence_rank(value: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(value, 0)


def _preferred_bucket_for_doc_type(doc_type: str) -> str | None:
    return {
        "schwab_1099_pdf": "brokers",
        "schwab_1099_csv": "brokers",
        "schwab_transactions_csv": "brokers",
        "schwab_limitation_image": "brokers",
        "jpm_1099_pdf": "brokers",
        "coinbase_transactions_csv": "crypto",
        "coinbase_1099_da_pdf": "crypto",
        "shareworks_statement_pdf": "equity_comp",
        "german_lohnsteuer_pdf": "germany",
        "german_verlustvortrag_pdf": "germany",
        "german_steuerbescheid_pdf": "germany",
        "german_prepayment_pdf": "germany",
        "german_capital_certificate_pdf": "germany",
        "german_social_insurance_notice_pdf": "germany",
        "us_1040_packet_pdf": "us",
        "us_8879_pdf": "us",
        "n26_transfer_confirmation_pdf": "us",
        "donation_receipt_eml": "receipts",
        "expense_invoice": "receipts",
    }.get(doc_type)


def _layout_for_workspace(paths: YearPaths) -> str:
    """Pick the layout to use for new uploads in this workspace.

    Returns ``"legacy"`` if any pre-Proposal-8 flat bucket directory
    already holds a file (the workspace has not been migrated);
    otherwise returns ``"canonical"`` so new scaffolds and freshly
    migrated workspaces use ``raw/jurisdictions/<iso>/`` and
    ``raw/asset_classes/<class>/``.

    Sticking to one layout per workspace keeps the on-disk shape
    coherent: a half-migrated workspace where new uploads land under
    the new layout and old files remain under the legacy layout would
    be the worst of both worlds. The migration helper (Commit 4)
    promotes a workspace from legacy to canonical atomically.
    """

    return "legacy" if has_legacy_raw_layout(paths.raw_root) else "canonical"


def _bucket_destination(paths: YearPaths, bucket: str, layout: str) -> Path:
    """Return ``raw_root/<sub>/<bucket>`` (or legacy flat) for storing.

    ``bucket`` is the legacy flat label (``brokers``, ``germany``,
    ``receipts`` ...). The legacy flat path is used on un-migrated
    workspaces; canonical workspaces resolve to
    ``raw/jurisdictions/<iso>/`` for jurisdiction labels and
    ``raw/asset_classes/<class>/`` for asset-class labels.
    """

    if layout == "legacy":
        return paths.raw_root / bucket
    return canonical_bucket_path(paths.raw_root, bucket)


def _candidate_is_supported(candidate: dict[str, object], filename: str) -> bool:
    doc_type = str(candidate["doc_type"])
    if doc_type == "unknown":
        return False
    lowered_name = filename.lower()
    if doc_type == "expense_invoice" and "invoice" not in lowered_name and "order details" not in lowered_name:
        return False
    return True


def _classify_upload_name(filename: str) -> dict[str, object]:
    # Proposal 8: probe both layouts so a filename that classifies via
    # its top-level bucket (``receipts/`` triggers the
    # ``expense_invoice`` heuristic) keeps classifying when the upload
    # is rooted at either ``raw/<bucket>/`` (legacy) or
    # ``raw/{jurisdictions,asset_classes}/<bucket>/`` (canonical).
    candidates = [
        classify_relative_path(Path(bucket) / filename)
        for bucket in all_raw_bucket_names()
    ]
    supported = [candidate for candidate in candidates if _candidate_is_supported(candidate, filename)]
    if not supported:
        return {
            "status": "unsupported",
            "stored": False,
            "bucket": None,
            "doc_type": "unknown",
            "provider": None,
            "document_family": None,
            "format": Path(filename).suffix.lower().lstrip(".") or "unknown",
            "tax_year": None,
            "owner": None,
            "country_of_origin": None,
            "confidence": "low",
            "relative_path": None,
            "filename": filename,
        }
    chosen = max(supported, key=lambda candidate: _confidence_rank(str(candidate["confidence"])))
    bucket = _preferred_bucket_for_doc_type(str(chosen["doc_type"])) or str(chosen["bucket"])
    return {
        "status": "supported",
        "stored": False,
        "bucket": bucket,
        "doc_type": chosen["doc_type"],
        "provider": chosen["provider"],
        "document_family": chosen["document_family"],
        "format": chosen["format"],
        "tax_year": chosen["tax_year"],
        "owner": chosen["owner"],
        "country_of_origin": chosen["country_of_origin"],
        "confidence": chosen["confidence"],
        "relative_path": f"{bucket}/{filename}",
        "filename": filename,
    }


def _upsert_upload_entry(paths: YearPaths, entry: dict[str, object]) -> None:
    entries = [existing for existing in _load_upload_index(paths) if existing.get("relative_path") != entry.get("relative_path")]
    entries.append(entry)
    _write_upload_index(paths, entries)


def _safe_upload_filename(filename: str) -> str:
    """Reject path-traversal and absolute-path uploads.

    Allows German umlauts and other non-ASCII Unicode in the basename so
    that filenames like ``Lohnsteuerbescheinigung-Ä.pdf`` survive intake.

    The explicit ``"/"``/``"\\"`` checks reject path separators on POSIX
    and Windows respectively. ``Path(safe).is_absolute()`` rejects roots
    like ``"/etc/passwd"`` or ``"C:\\Windows"``. The ``"."``/``".."`` and
    ``Path(safe).name != safe`` checks reject parent-directory traversal.

    NOTE (L7, 2026-05-01 correctness review): once the separator and
    absolute-path branches have rejected names with ``/`` or ``\\``,
    ``Path(safe).name != safe`` is a redundant safety net rather than a
    primary check. Kept as defense-in-depth so a future Python ``Path``
    normalization quirk (e.g., a trailing ``"/"`` collapsing) cannot
    smuggle a traversal through the earlier branches.
    """
    safe = filename.strip()
    if (
        not safe
        or safe in {".", ".."}
        or "/" in safe
        or "\\" in safe
        or Path(safe).is_absolute()
        or Path(safe).name != safe
        or any(ord(char) < 32 for char in safe)
    ):
        raise ValueError("Unsafe upload filename")
    return safe


def _contained_destination(root: Path, relative_path: Path) -> Path:
    root_resolved = root.resolve()
    destination = (root / relative_path).resolve()
    try:
        destination.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("Unsafe upload destination") from exc
    return destination


def store_upload(
    paths: YearPaths,
    filename: str,
    content: bytes,
    *,
    manual_bucket: str | None = None,
    evidence_only: bool = False,
) -> dict[str, object]:
    ensure_year_scaffold(paths)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Upload exceeds maximum size")
    filename = _safe_upload_filename(filename)
    preview = _classify_upload_name(filename)

    layout = _layout_for_workspace(paths)

    if preview["status"] == "supported":
        bucket = str(preview["bucket"])
        # Proposal 8: legacy workspaces keep storing under
        # ``raw/<bucket>/<filename>``; canonical workspaces store under
        # ``raw/jurisdictions/<iso>/<filename>`` or
        # ``raw/asset_classes/<class>/<filename>``. Both layouts remain
        # readable so the dual-read path keeps working until the
        # workspace is migrated.
        bucket_dir = _bucket_destination(paths, bucket, layout)
        relative_path = bucket_dir.relative_to(paths.raw_root) / filename
        destination = _contained_destination(paths.raw_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        write_manifest(paths.raw_root, paths.manifest_path, year=paths.year)
        entry = {
            **preview,
            "stored": True,
            "relative_path": relative_path.as_posix(),
        }
        _upsert_upload_entry(paths, entry)
        return entry

    if evidence_only:
        # Accept either the legacy flat names or the canonical ISO /
        # asset-class names so the wizard's bucket selector can be
        # rolled forward without breaking older clients.
        if manual_bucket not in set(all_raw_bucket_names()):
            raise ValueError(f"Evidence-only uploads require a supported manual bucket: {manual_bucket!r}")
        bucket_dir = _bucket_destination(paths, str(manual_bucket), layout)
        relative_path = bucket_dir.relative_to(paths.raw_root) / ".evidence-only" / filename
        destination = _contained_destination(paths.raw_root, relative_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        entry = {
            **preview,
            "status": "evidence_only",
            "stored": True,
            "bucket": manual_bucket,
            "relative_path": relative_path.as_posix(),
        }
        _upsert_upload_entry(paths, entry)
        return entry

    return preview


def classify_upload_batch(filenames: list[str]) -> list[dict[str, object]]:
    """Classify a batch of upload candidates without storing them.

    Powers the drag-and-drop uploader's per-file preview row: the client
    drops N files, the server returns N classifier predictions (bucket,
    doc_type, provider, confidence, country), and the user confirms or
    overrides bucket before any bytes are written to disk. The classifier
    only needs the filename/relative-path to predict — file content is
    not read at this stage, so the preview is cheap.
    """
    predictions: list[dict[str, object]] = []
    for raw_name in filenames:
        name = str(raw_name or "").strip()
        if not name:
            predictions.append(
                {
                    "filename": "",
                    "error": "Empty filename.",
                }
            )
            continue
        prediction = classify_relative_path(Path(name))
        prediction["filename"] = name
        predictions.append(prediction)
    return predictions


def list_uploads(paths: YearPaths) -> dict[str, object]:
    ensure_year_scaffold(paths)
    return {"uploads": _load_upload_index(paths)}
