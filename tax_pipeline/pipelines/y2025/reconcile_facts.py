from __future__ import annotations

import csv
import json
from json import JSONDecodeError
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from tax_pipeline.core import (
    AssessmentPackage,
    CanonicalFact,
    CountryAssessment,
    FactProvenance,
    IgnoredFact,
    RenderProjection,
    StageDiagnostic,
    StageGraphValidation,
    StageResult,
    TreatyAssessment,
    UnsupportedFact,
)
from tax_pipeline.paths import RAW_BUCKETS, all_raw_bucket_names, YearPaths

D = Decimal
EXTRACTOR_ID = "reconcile_facts_2025"


@dataclass(frozen=True)
class ReconciledFacts2025:
    canonical_facts: tuple[CanonicalFact, ...]
    unsupported_facts: tuple[UnsupportedFact, ...] = ()
    ignored_facts: tuple[IgnoredFact, ...] = ()


def _relative_source_ref(paths: YearPaths, path: Path) -> str:
    try:
        return path.relative_to(paths.year_root).as_posix()
    except ValueError:
        return path.as_posix()


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip().lower())
    return "_".join(part for part in cleaned.split("_") if part)


def _required(row: Mapping[str, str], key: str, *, path: Path, line_number: int) -> str:
    value = str(row.get(key, "")).strip()
    if not value:
        raise ValueError(f"{path.name} row {line_number} {key} is required")
    return value


def _decimal(value: str, *, path: Path, line_number: int, field: str) -> Decimal:
    try:
        return D(str(value).strip())
    except InvalidOperation as exc:
        raise ValueError(f"{path.name} row {line_number} {field} must be a decimal") from exc


def _parse_scalar(value: object) -> object:
    if isinstance(value, str):
        cleaned = value.strip()
        lowered = cleaned.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        try:
            return D(cleaned)
        except InvalidOperation:
            return cleaned
    return value


def _unit_and_currency(key: str, value: object, explicit_currency: str | None = None) -> tuple[str, str | None]:
    if explicit_currency:
        return "money", explicit_currency.upper()
    lowered = key.lower()
    if lowered.endswith("_usd") or lowered.endswith(".usd"):
        return "money", "USD"
    if lowered.endswith("_eur") or lowered.endswith(".eur"):
        return "money", "EUR"
    if lowered.endswith("_rate") or lowered.endswith(".rate"):
        return "ratio", None
    if isinstance(value, bool):
        return "boolean", None
    if isinstance(value, int):
        return "integer", None
    if isinstance(value, Decimal):
        return "number", None
    return "text", None


def _provenance(
    paths: YearPaths,
    path: Path,
    *,
    source_field: str,
    source_line: int | None = None,
    notes: Iterable[str] = (),
) -> FactProvenance:
    return FactProvenance(
        source_document_ref=_relative_source_ref(paths, path),
        source_field=source_field,
        source_line=source_line,
        extracted_by=EXTRACTOR_ID,
        notes=tuple(notes),
    )


def _fact(
    paths: YearPaths,
    *,
    key: str,
    value: object,
    provenance: FactProvenance,
    taxpayer_scope: str = "household",
    currency: str | None = None,
    unit: str | None = None,
    confidence: Decimal = D("1.0"),
) -> CanonicalFact:
    inferred_unit, inferred_currency = _unit_and_currency(key, value, currency)
    return CanonicalFact(
        key=key,
        value=value,
        provenance=provenance,
        tax_year=paths.year,
        taxpayer_scope=taxpayer_scope,
        currency=inferred_currency,
        unit=unit or inferred_unit,
        confidence=confidence,
    )


def _csv_rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            (line_number, {key: (value or "") for key, value in row.items() if key is not None})
            for line_number, row in enumerate(csv.DictReader(handle), start=2)
        ]


def _profile_facts(paths: YearPaths) -> list[CanonicalFact]:
    payload = json.loads(paths.profile_path.read_text(encoding="utf-8"))
    facts: list[CanonicalFact] = []

    def walk(prefix: tuple[str, ...], value: object) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                walk((*prefix, str(key)), value[key])
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk((*prefix, str(index)), item)
            return
        field = ".".join(prefix)
        parsed = _parse_scalar(value)
        facts.append(
            _fact(
                paths,
                key=f"profile.{field}",
                value=parsed,
                provenance=_provenance(paths, paths.profile_path, source_field=field),
            )
        )

    walk((), payload)
    return facts


def _election_facts(paths: YearPaths) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = []
    for line_number, row in _csv_rows(paths.elections_path):
        jurisdiction = _required(row, "jurisdiction", path=paths.elections_path, line_number=line_number).lower()
        key = _required(row, "key", path=paths.elections_path, line_number=line_number)
        raw_value = _required(row, "value", path=paths.elections_path, line_number=line_number)
        value = _parse_scalar(raw_value)
        facts.append(
            _fact(
                paths,
                key=f"election.{jurisdiction}.{key}",
                value=value,
                provenance=_provenance(
                    paths,
                    paths.elections_path,
                    source_field=key,
                    source_line=line_number,
                    notes=(row.get("source", ""), row.get("note", "")),
                ),
            )
        )
    return facts


def _people_facts(paths: YearPaths) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = []
    for line_number, row in _csv_rows(paths.people_path):
        person_id = _required(row, "person_id", path=paths.people_path, line_number=line_number)
        for field, raw_value in sorted(row.items()):
            value = str(raw_value).strip()
            if not value:
                continue
            parsed = _parse_scalar(value)
            facts.append(
                _fact(
                    paths,
                    key=f"person.{person_id}.{field}",
                    value=parsed,
                    taxpayer_scope=person_id,
                    provenance=_provenance(
                        paths,
                        paths.people_path,
                        source_field=field,
                        source_line=line_number,
                    ),
                )
            )
    return facts


def _payment_facts(paths: YearPaths) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = []
    for line_number, row in _csv_rows(paths.payments_path):
        jurisdiction = _required(row, "jurisdiction", path=paths.payments_path, line_number=line_number).lower()
        person_id = _required(row, "person_id", path=paths.payments_path, line_number=line_number)
        payment_type = _required(row, "payment_type", path=paths.payments_path, line_number=line_number)
        amount = _decimal(
            _required(row, "amount", path=paths.payments_path, line_number=line_number),
            path=paths.payments_path,
            line_number=line_number,
            field="amount",
        )
        currency = _required(row, "currency", path=paths.payments_path, line_number=line_number).upper()
        facts.append(
            _fact(
                paths,
                key=f"payment.{jurisdiction}.{person_id}.{payment_type}.{currency.lower()}",
                value=amount,
                taxpayer_scope=person_id,
                currency=currency,
                unit="money",
                provenance=_provenance(
                    paths,
                    paths.payments_path,
                    source_field=payment_type,
                    source_line=line_number,
                    notes=(row.get("source", ""), row.get("note", "")),
                ),
            )
        )
    return facts


def _reference_row_facts(paths: YearPaths, path: Path) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = []
    file_slug = _slug(path.stem)
    for line_number, row in _csv_rows(path):
        if {"section", "key", "value"}.issubset(row):
            section = _required(row, "section", path=path, line_number=line_number)
            key = _required(row, "key", path=path, line_number=line_number)
            value = _parse_scalar(_required(row, "value", path=path, line_number=line_number))
            facts.append(
                _fact(
                    paths,
                    key=f"reference.{file_slug}.{section}.{key}",
                    value=value,
                    provenance=_provenance(
                        paths,
                        path,
                        source_field=f"{section}.{key}",
                        source_line=line_number,
                        notes=(row.get("source", ""), row.get("note", "")),
                    ),
                )
            )
            continue

        if {"date", "usd_per_eur", "eur_per_usd"}.issubset(row):
            date = _required(row, "date", path=path, line_number=line_number)
            for field in ("usd_per_eur", "eur_per_usd"):
                facts.append(
                    _fact(
                        paths,
                        key=f"reference.{file_slug}.{date}.{field}",
                        value=_decimal(row[field], path=path, line_number=line_number, field=field),
                        unit="rate",
                        provenance=_provenance(
                            paths,
                            path,
                            source_field=f"{date}.{field}",
                            source_line=line_number,
                            notes=(row.get("source", ""), row.get("note", "")),
                        ),
                    )
                )
            continue

        raise ValueError(f"{path.name} row {line_number} uses an unsupported reference-data schema")
    return facts


def _reference_facts(paths: YearPaths) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = []
    for path in sorted(paths.reference_data_root.glob("*.csv")):
        facts.extend(_reference_row_facts(paths, path))
    return facts


def _unsupported_raw_bucket_facts(paths: YearPaths) -> list[UnsupportedFact]:
    payload = json.loads(paths.profile_path.read_text(encoding="utf-8"))
    raw_buckets = payload.get("raw_buckets", [])
    if not isinstance(raw_buckets, list):
        raise ValueError("profile.raw_buckets must be a list when present")
    unsupported: list[UnsupportedFact] = []
    # Proposal 8 (raw-bucket redesign): accept either the legacy flat
    # bucket names (``germany``, ``us``) or the new canonical ISO codes
    # (``de``, ``us``) plus every asset-class label, so a workspace
    # whose ``profile.raw_buckets`` has been migrated to the new layout
    # is not flagged as carrying "unknown" buckets.
    supported = set(all_raw_bucket_names())
    for index, raw_bucket in enumerate(raw_buckets):
        bucket = str(raw_bucket).strip()
        if not bucket or bucket in supported:
            continue
        unsupported.append(
            UnsupportedFact(
                fact=_fact(
                    paths,
                    key=f"profile.raw_bucket.{_slug(bucket)}",
                    value=bucket,
                    provenance=_provenance(
                        paths,
                        paths.profile_path,
                        source_field=f"raw_buckets.{index}",
                    ),
                ),
                reason=f"Unknown raw bucket {bucket!r} is not wired to the 2025 reconciliation shell.",
            )
        )
    return unsupported


def _unsupported_csv_facts(paths: YearPaths, root: Path, bucket_name: str) -> list[UnsupportedFact]:
    unsupported: list[UnsupportedFact] = []
    for path in sorted(root.glob("*.csv")):
        file_slug = _slug(path.stem)
        for line_number, row in _csv_rows(path):
            section = _required(row, "section", path=path, line_number=line_number)
            key = _required(row, "key", path=path, line_number=line_number)
            value = _parse_scalar(_required(row, "value", path=path, line_number=line_number))
            unsupported.append(
                UnsupportedFact(
                    fact=_fact(
                        paths,
                        key=f"unsupported.{bucket_name}.{file_slug}.{section}.{key}",
                        value=value,
                        provenance=_provenance(
                            paths,
                            path,
                            source_field=f"{section}.{key}",
                            source_line=line_number,
                            notes=(row.get("source", ""), row.get("note", "")),
                        ),
                    ),
                    reason=f"{bucket_name} is an unsupported fact bucket for the 2025 reconciliation shell.",
                )
            )
    return unsupported


def _ignored_file_fact(paths: YearPaths, path: Path, bucket_name: str, reason: str) -> IgnoredFact:
    return IgnoredFact(
        fact=_fact(
            paths,
            key=f"ignored.{bucket_name}.{_slug(path.relative_to(path.parents[0]).as_posix())}.file",
            value=_relative_source_ref(paths, path),
            provenance=_provenance(paths, path, source_field=path.name),
        ),
        reason=reason,
    )


def _unsupported_file_fact(paths: YearPaths, path: Path, bucket_name: str) -> UnsupportedFact:
    relative_ref = _relative_source_ref(paths, path)
    return UnsupportedFact(
        fact=_fact(
            paths,
            key=f"unsupported.{bucket_name}.{_slug(path.name)}.file",
            value=relative_ref,
            provenance=_provenance(
                paths,
                path,
                source_field=path.name,
            ),
        ),
        reason=(
            f"{bucket_name} contains unsupported fact file {relative_ref!r}; "
            "add a parser/reconciler before legal stages can consume it."
        ),
    )


def _canonical_json_facts(paths: YearPaths, path: Path) -> list[CanonicalFact] | None:
    if not path.name.endswith(".facts.json"):
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise ValueError(f"{path.name} must be valid JSON") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("facts"), list):
        return None
    owner = str(payload.get("owner", "household")).strip() or "household"
    doc_type = str(payload.get("doc_type", path.stem)).strip() or path.stem
    facts: list[CanonicalFact] = []
    for index, item in enumerate(payload["facts"]):
        if not isinstance(item, Mapping):
            raise ValueError(f"{path.name} facts[{index}] must be an object")
        raw_key = str(item.get("key", "")).strip()
        if not raw_key:
            raise ValueError(f"{path.name} facts[{index}].key is required")
        if item.get("value") is None:
            raise ValueError(f"{path.name} facts[{index}].value is required")
        notes = [f"doc_type={doc_type}"]
        source = item.get("source")
        if isinstance(source, Mapping) and source.get("file"):
            notes.append(f"source_file={source['file']}")
        if item.get("notes"):
            notes.append(str(item["notes"]))
        facts.append(
            _fact(
                paths,
                key=f"fact.{_slug(owner)}.{_slug(raw_key)}",
                value=_parse_scalar(item["value"]),
                taxpayer_scope=owner,
                provenance=_provenance(
                    paths,
                    path,
                    source_field=f"facts.{index}.{raw_key}",
                    notes=notes,
                ),
            )
        )
    return facts


def _non_csv_fact_files(
    paths: YearPaths,
    root: Path,
    bucket_name: str,
) -> tuple[list[CanonicalFact], list[IgnoredFact], list[UnsupportedFact]]:
    canonical: list[CanonicalFact] = []
    ignored: list[IgnoredFact] = []
    unsupported: list[UnsupportedFact] = []
    if not root.exists():
        return canonical, ignored, unsupported
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        if path.suffix.lower() == ".csv":
            continue
        if path.suffix.lower() == ".md" or path.name in {"index.json", "validation.json"}:
            ignored.append(
                _ignored_file_fact(
                    paths,
                    path,
                    bucket_name,
                    f"{bucket_name} metadata/documentation file is not a legal fact input.",
                )
            )
            continue
        json_facts = _canonical_json_facts(paths, path)
        if json_facts is not None:
            canonical.extend(json_facts)
            continue
        unsupported.append(_unsupported_file_fact(paths, path, bucket_name))
    return canonical, ignored, unsupported


def reconcile_facts_2025(paths: YearPaths) -> ReconciledFacts2025:
    facts_canonical, facts_ignored, facts_unsupported = _non_csv_fact_files(
        paths,
        paths.facts_root,
        "facts",
    )
    manual_canonical, manual_ignored, manual_unsupported = _non_csv_fact_files(
        paths,
        paths.manual_facts_root,
        "manual_facts",
    )
    canonical_facts = [
        *_profile_facts(paths),
        *_people_facts(paths),
        *_election_facts(paths),
        *_payment_facts(paths),
        *_reference_facts(paths),
        *facts_canonical,
        *manual_canonical,
    ]
    unsupported_facts = [
        *_unsupported_raw_bucket_facts(paths),
        *facts_unsupported,
        *_unsupported_csv_facts(paths, paths.facts_root, "facts"),
        *manual_unsupported,
        *_unsupported_csv_facts(paths, paths.manual_facts_root, "manual_facts"),
    ]
    return ReconciledFacts2025(
        canonical_facts=tuple(canonical_facts),
        unsupported_facts=tuple(unsupported_facts),
        ignored_facts=tuple((*facts_ignored, *manual_ignored)),
    )


def _split_facts(
    reconciled: ReconciledFacts2025 | Iterable[CanonicalFact | IgnoredFact | UnsupportedFact],
) -> tuple[tuple[CanonicalFact, ...], tuple[IgnoredFact, ...], tuple[UnsupportedFact, ...]]:
    if isinstance(reconciled, ReconciledFacts2025):
        return reconciled.canonical_facts, reconciled.ignored_facts, reconciled.unsupported_facts

    canonical: list[CanonicalFact] = []
    ignored: list[IgnoredFact] = []
    unsupported: list[UnsupportedFact] = []
    for fact in reconciled:
        if isinstance(fact, CanonicalFact):
            canonical.append(fact)
        elif isinstance(fact, IgnoredFact):
            ignored.append(fact)
        elif isinstance(fact, UnsupportedFact):
            unsupported.append(fact)
        else:
            raise ValueError("facts must be CanonicalFact, IgnoredFact, or UnsupportedFact instances")
    return tuple(canonical), tuple(ignored), tuple(unsupported)


def _assessment(country_or_scope: str, stage_results: Sequence[StageResult]) -> CountryAssessment | None:
    results = tuple(stage_results)
    if not results:
        return None
    totals: dict[str, Any] = {}
    diagnostics: list[StageDiagnostic] = []
    precision_notes: dict[str, str] = {}
    for result in results:
        totals.update(result.outputs)
        diagnostics.extend(result.diagnostics)
        precision_notes.update(result.precision_notes)
    return CountryAssessment(
        country_or_scope=country_or_scope,
        stage_results=results,
        totals=totals,
        diagnostics=tuple(diagnostics),
        precision_notes=precision_notes,
    )


def _treaty_assessment(stage_results: Sequence[StageResult]) -> TreatyAssessment | None:
    results = tuple(stage_results)
    if not results:
        return None
    outputs: dict[str, Any] = {}
    diagnostics: list[StageDiagnostic] = []
    precision_notes: dict[str, str] = {}
    for result in results:
        outputs.update(result.outputs)
        diagnostics.extend(result.diagnostics)
        precision_notes.update(result.precision_notes)
    return TreatyAssessment(
        treaty_id="de-us-2025",
        stage_results=results,
        outputs=outputs,
        diagnostics=tuple(diagnostics),
        precision_notes=precision_notes,
    )


def build_assessment_package_2025(
    reconciled_facts: ReconciledFacts2025 | Iterable[CanonicalFact | IgnoredFact | UnsupportedFact],
    *,
    germany_stage_results: Sequence[StageResult] = (),
    us_stage_results: Sequence[StageResult] = (),
    treaty_stage_results: Sequence[StageResult] = (),
    render_fields: Mapping[str, Any] | None = None,
    audit_graph: StageGraphValidation | None = None,
    render_projection: RenderProjection | None = None,
) -> AssessmentPackage:
    canonical_facts, ignored_facts, unsupported_facts = _split_facts(reconciled_facts)
    if unsupported_facts:
        raise ValueError(
            "Cannot build 2025 assessment package with unsupported facts: "  # pragma: legal-math-ok string error-message concatenation (str + str), no Decimal arithmetic — the I5 taint tracker seeds ``unsupported_facts`` because the parameter name ends in ``_facts``
            + ", ".join(fact.fact.key for fact in unsupported_facts)
        )
    all_stage_results = (*germany_stage_results, *us_stage_results, *treaty_stage_results)
    output_keys = tuple(sorted({key for result in all_stage_results for key in result.outputs}))
    stage_ids = tuple(result.stage_id for result in all_stage_results)
    source_output_fingerprints = {
        key: fingerprint
        for result in all_stage_results
        for key, fingerprint in result.output_fingerprints.items()
    }
    diagnostics = tuple(diagnostic for result in all_stage_results for diagnostic in result.diagnostics)
    initial_fact_keys = tuple(sorted(fact.key for fact in canonical_facts))
    if render_projection is None and render_fields:
        untracked_render_fields = set(render_fields) - set(source_output_fingerprints)
        if untracked_render_fields:
            raise ValueError(
                f"render fields must come from legal stage outputs: {sorted(untracked_render_fields)}"
            )

    return AssessmentPackage(
        tax_year=2025,
        canonical_facts=canonical_facts,
        germany_assessment=_assessment("DE", germany_stage_results),
        us_assessment=_assessment("US", us_stage_results),
        treaty_assessment=_treaty_assessment(treaty_stage_results),
        diagnostics=diagnostics,
        audit_graph=audit_graph or StageGraphValidation(
            stage_ids=stage_ids,
            initial_fact_keys=initial_fact_keys,
            output_keys=output_keys,
            final_available_keys=tuple(sorted((*initial_fact_keys, *output_keys))),
        ),
        render_projection=render_projection or RenderProjection(
            fields=dict(render_fields or {}),
            source_output_fingerprints=source_output_fingerprints,
        ),
        ignored_facts=ignored_facts,
        unsupported_facts=unsupported_facts,
    )


__all__ = [
    "ReconciledFacts2025",
    "build_assessment_package_2025",
    "reconcile_facts_2025",
]
