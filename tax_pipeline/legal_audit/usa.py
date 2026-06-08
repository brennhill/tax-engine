from __future__ import annotations

from pathlib import Path

from tax_pipeline.forms.common import result_phrase
from tax_pipeline.legal_audit.common import (
    LegalAuditSpec,
    MatrixColumn,
    render_legal_audit_package,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import final_legal_output_path, load_final_legal_output_2025

SUPPORTED_YEAR = 2025


def _ensure_supported_year(paths: YearPaths) -> None:
    if paths.year != SUPPORTED_YEAR:
        raise NotImplementedError(
            f"U.S. legal-audit renderer currently supports {SUPPORTED_YEAR} only, got {paths.year}"
        )


def required_usa_legal_audit_paths(paths: YearPaths) -> list[Path]:
    return [final_legal_output_path(paths)]


def render_usa_legal_audit(paths: YearPaths) -> None:
    _ensure_supported_year(paths)

    final_output = load_final_legal_output_2025(paths)
    audit = final_output["usa"]["legal_audit"]
    results = audit["results"]
    overview_text = audit["overview_text"]
    trace_rows = audit["trace_rows"]
    assumption_rows = audit["assumption_rows"]
    spec = LegalAuditSpec(
        package_title=f"U.S. Legal Audit Package - {paths.year}",
        assumptions_title=f"U.S. {paths.year} Assumptions Register",
        assumptions_source_name="us-model-assumptions.csv",
        trace_index_title=f"U.S. {paths.year} Trace Index",
        law_matrix_title=f"U.S. {paths.year} Law Matrix",
        source_trace_name="us-tax-trace.csv",
        result_line_builder=lambda payload: (
            "Final modeled result: "
            f"**{result_phrase(payload['payments']['refund_if_positive_else_balance_due_with_treaty_resourcing_usd'], 'USD')}**."
        ),
        required_manual_positions_heading="Manual Positions Still Explicitly Configured",
        assumptions_required_columns=("section", "key", "value", "source", "note"),
        assumptions_required_nonblank_columns=("section", "key", "value", "source", "note"),
        trace_value_column="amount_usd",
        trace_value_header="Value",
        trace_note_column="note",
        trace_required_columns=(
            "step",
            "amount_usd",
            "legal_reference",
            "authority_url",
            "step_type",
            "note",
            "precision_note",
        ),
        trace_required_nonblank_columns=(
            "step",
            "amount_usd",
            "legal_reference",
            "authority_url",
            "step_type",
            "note",
            "precision_note",
        ),
        law_matrix_columns=(
            MatrixColumn("step", "step"),
            MatrixColumn("legal_reference", "legal_reference"),
            MatrixColumn("authority_url", "authority_url"),
            MatrixColumn("step_type", "step_type"),
            MatrixColumn("note", "note"),
            MatrixColumn("precision_note", "precision_note"),
        ),
        source_lines=(
            "`analysis-steps/final-legal-output.json`",
        ),
    )
    render_legal_audit_package(
        root=paths.usa_legal_audit_root,
        results=results,
        overview_text=overview_text,
        trace_rows=trace_rows,
        assumption_rows=assumption_rows,
        spec=spec,
    )
