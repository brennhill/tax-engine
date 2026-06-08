from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from tax_pipeline.forms.common import result_phrase
from tax_pipeline.legal_audit.common import (
    LegalAuditSpec,
    MatrixColumn,
    render_legal_audit_package,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import final_legal_output_path, load_final_legal_output_2025
from tax_pipeline.postures import get_posture_definition

SUPPORTED_YEAR = 2025
LAW_SPEC_ROOT = Path(__file__).resolve().parents[1] / "law_spec" / "germany" / "2025"


def _ensure_supported_year(paths: YearPaths) -> None:
    if paths.year != SUPPORTED_YEAR:
        raise NotImplementedError(
            f"Germany legal-audit renderer currently supports {SUPPORTED_YEAR} only, got {paths.year}"
        )


def required_germany_legal_audit_paths(paths: YearPaths) -> list[Path]:
    return [final_legal_output_path(paths)]


def _coverage_patterns() -> list[tuple[str, str, str]]:
    coverage_path = LAW_SPEC_ROOT / "coverage.md"
    rows: list[tuple[str, str, str]] = []
    for line in coverage_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        pattern = cells[0].strip("`")
        match = re.search(r"\(([^)]+\.md)\)", cells[1])
        if not match:
            continue
        spec_name = match.group(1)
        spec_path = LAW_SPEC_ROOT / spec_name
        test_coverage = _test_coverage_for_spec(spec_path)
        rows.append((pattern, spec_name, test_coverage))
    return rows


def _test_coverage_for_spec(spec_path: Path) -> str:
    lines = spec_path.read_text(encoding="utf-8").splitlines()
    capture = False
    bullets: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "## Test Coverage":
            capture = True
            continue
        if capture and stripped.startswith("## "):
            break
        if capture and stripped.startswith("- "):
            bullets.append(stripped[2:])
    return "; ".join(bullets) if bullets else "No explicit test coverage listed"


def _enrich_trace_rows_with_law_spec(trace_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    coverage = _coverage_patterns()
    enriched: list[dict[str, str]] = []
    missing: list[str] = []
    for row in trace_rows:
        step = row["step"]
        match = next((entry for entry in coverage if fnmatch.fnmatch(step, entry[0])), None)
        if match is None:
            missing.append(step)
            continue
        _, spec_name, test_coverage = match
        if step == "joint_income_tax":
            # The trace step name is historical. § 32a Abs. 1 basic-tariff rows and
            # § 26b/§ 32a Abs. 5 splitting rows must map to different law specs so the
            # audit matrix cannot silently claim married law coverage for a single return.
            legal_reference = row.get("legal_reference", "")
            note = row.get("note", "")
            married_split_trace = "§ 26b" in legal_reference or "splitting" in note.lower()
            split_tariff_cited = re.search(
                r"§\s*32a\s+Abs\.\s*(?:5|1\s+und\s+5)\b",
                legal_reference,
            )
            if married_split_trace and not split_tariff_cited:
                # § 26b EStG makes married joint income tax use the § 32a Abs. 5
                # splitting method. A married/splitting audit trace that omits Abs. 5
                # must fail closed instead of being mapped to basic_tariff.md.
                raise ValueError("Germany married joint_income_tax trace must cite § 32a Abs. 5 EStG.")
            if split_tariff_cited:
                if "§ 26b" not in legal_reference:
                    raise ValueError("Germany married joint_income_tax trace must cite § 26b and § 32a Abs. 5 EStG.")
                spec_name = "split_tariff.md"
                test_coverage = _test_coverage_for_spec(LAW_SPEC_ROOT / spec_name)
            else:
                spec_name = "basic_tariff.md"
                test_coverage = _test_coverage_for_spec(LAW_SPEC_ROOT / spec_name)
        enriched_row = dict(row)
        enriched_row["law_spec"] = f"tax_pipeline/law_spec/germany/2025/{spec_name}"
        enriched_row["test_coverage"] = test_coverage
        enriched.append(enriched_row)
    if missing:
        raise ValueError("Missing Germany law-spec coverage for trace steps: " + ", ".join(missing))
    return enriched


def render_germany_legal_audit(paths: YearPaths) -> None:
    _ensure_supported_year(paths)

    final_output = load_final_legal_output_2025(paths)
    audit = final_output["germany"]["legal_audit"]
    results = audit["results"]
    filing_posture = str(results.get("ordinary", {}).get("filing_posture", "")).strip()
    if filing_posture:
        posture = get_posture_definition("germany", filing_posture)
        if not posture.output_support.ordinary_law:
            # § 26a EStG separate assessment has allocation elections that are not modeled in
            # the 2025 Germany engine. Legal-audit output must not render unsupported posture math.
            raise NotImplementedError(
                f"Germany legal-audit output is not supported for filing posture '{filing_posture}'."
            )
    overview_text = audit["overview_text"]
    trace_rows = _enrich_trace_rows_with_law_spec(audit["trace_rows"])
    assumption_rows = audit["assumption_rows"]
    spec = LegalAuditSpec(
        package_title=f"Germany Legal Audit Package - {paths.year}",
        assumptions_title=f"Germany {paths.year} Assumptions Register",
        assumptions_source_name="de-model-assumptions.csv",
        trace_index_title=f"Germany {paths.year} Trace Index",
        law_matrix_title=f"Germany {paths.year} Law Matrix",
        source_trace_name="germany-model-trace.csv",
        result_line_builder=lambda payload: (
            f"Final modeled result: **{result_phrase(payload['refunds']['final_target_refund_eur'])}**."
        ),
        required_manual_positions_heading="Manual Factual Positions Still Explicitly Configured",
        assumptions_required_columns=("section", "key", "value", "source", "note"),
        assumptions_required_nonblank_columns=("section", "key", "value", "source", "note"),
        trace_value_column="value_eur",
        trace_value_header="Value",
        trace_note_column="note",
        trace_required_columns=("step", "value_eur", "legal_reference", "authority_url", "note", "precision_note"),
        trace_required_nonblank_columns=("step", "value_eur", "legal_reference", "authority_url", "note"),
        law_matrix_columns=(
            MatrixColumn("step", "step"),
            MatrixColumn("legal_reference", "legal_reference"),
            MatrixColumn("authority_url", "authority_url"),
            MatrixColumn("Law Spec", "law_spec"),
            MatrixColumn("Test Coverage", "test_coverage"),
            MatrixColumn("note", "note"),
            MatrixColumn("precision_note", "precision_note"),
        ),
        source_lines=(
            "`analysis-steps/final-legal-output.json`",
        ),
    )
    render_legal_audit_package(
        root=paths.germany_legal_audit_root,
        results=results,
        overview_text=overview_text,
        trace_rows=trace_rows,
        assumption_rows=assumption_rows,
        spec=spec,
    )
