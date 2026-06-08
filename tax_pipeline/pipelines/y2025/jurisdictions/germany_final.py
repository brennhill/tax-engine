"""Germany final-legal-output validators.

Architecture review 2026-05-04 §5 Proposal 7 — extracts the Germany
validation block from the 944-line ``final_legal_output.py``. The
collectors here gate the projection-side artifacts (CSV row sets,
ELSTER entry-sheet text) against the typed legal core output that
``germany_model.py`` persists into ``germany-model-results.json``.

Authority
---------
- § 26a EStG (separate assessment) — controls the posture gate
  ``_validate_germany_final_output_supported``.
  https://www.gesetze-im-internet.de/estg/__26a.html
- § 20 EStG / § 32d EStG (Abgeltungsteuer / capital ordering) — the
  KAP projection consistency gate ``_validate_germany_render_projection``
  exists so that a stale or hand-edited Anlage KAP sidecar cannot
  override the typed legal core ordering computed in
  ``germany_2025_law.py``.
  https://www.gesetze-im-internet.de/estg/__20.html
  https://www.gesetze-im-internet.de/estg/__32d.html
- § 33b Abs. 5 EStG (transferred Behinderten-Pauschbetrag) — drives
  the Anlage Kind summary row that
  ``_validate_germany_render_projection`` cross-checks.
  https://www.gesetze-im-internet.de/estg/__33b.html
"""

from __future__ import annotations

from typing import Any

from tax_pipeline.pipelines.y2025.final_legal_output_helpers import (
    _projection_dict_rows,
    _require_projected_rows_equal,
)


def _validate_germany_final_output_supported(germany_results: dict[str, Any]) -> None:
    posture = str(germany_results.get("ordinary", {}).get("filing_posture", "")).strip().lower()
    if posture == "married_separate":
        # § 26a EStG separate assessment is not a renderer variant of the joint model:
        # it needs spouse-separated income/deduction/tax outputs before public final
        # legal output can be trusted.
        raise NotImplementedError("Germany married_separate not supported in final output under § 26a EStG.")


def _validate_germany_render_projection(
    germany_results: dict[str, Any],
    *,
    kap_summary_rows: list[dict[str, str]],
    kap_inv_fund_rows: list[dict[str, str]],
    n_work_expense_rows: list[dict[str, str]],
    kind_summary_rows: list[dict[str, str]],
) -> None:
    # Germany form/audit rendering is allowed to consume CSV-shaped rows, but those
    # rows must be exact projections of the typed legal core output. This prevents
    # a stale or hand-edited Anlage KAP sidecar from overriding the § 20 / § 32d
    # capital ordering computed in germany_2025_law.py.
    elster_projection = germany_results.get("render_projection", {}).get("elster", {})
    expected_kap = _projection_dict_rows(
        elster_projection.get("kap_summary_rows"),
        ("form", "line", "amount_eur", "note"),
        label="render_projection.elster.kap_summary_rows",
    )
    expected_kap_inv = _projection_dict_rows(
        elster_projection.get("kap_inv_fund_rows"),
        ("symbol", "fund_type", "income_eur", "sale_result_eur", "combined_eur"),
        label="render_projection.elster.kap_inv_fund_rows",
    )
    expected_n = _projection_dict_rows(
        elster_projection.get("n_breakdown_rows"),
        ("form", "line", "description", "amount_eur", "note"),
        label="render_projection.elster.n_breakdown_rows",
    )
    expected_kind = _projection_dict_rows(
        elster_projection.get("kind_summary_rows"),
        ("form", "line", "amount_eur", "note"),
        label="render_projection.elster.kind_summary_rows",
    )
    _require_projected_rows_equal(
        kap_summary_rows,
        expected_kap,
        path_name="germany-kap-summary.csv",
    )
    _require_projected_rows_equal(
        kap_inv_fund_rows,
        expected_kap_inv,
        path_name="germany-kap-inv-fund-summary.csv",
    )
    _require_projected_rows_equal(
        n_work_expense_rows,
        expected_n,
        path_name="germany-n-work-expenses.csv",
    )
    _require_projected_rows_equal(
        kind_summary_rows,
        expected_kind,
        path_name="germany-kind-summary.csv",
    )


def _required_core_anlage_n_projection(germany_results: dict[str, Any]) -> dict[str, Any]:
    projection = germany_results.get("render_projection", {}).get("elster", {}).get("anlage_n_entries_by_slot")
    if not isinstance(projection, dict):
        raise FileNotFoundError(
            "Missing Germany core render projection: render_projection.elster.anlage_n_entries_by_slot"
        )
    return projection
