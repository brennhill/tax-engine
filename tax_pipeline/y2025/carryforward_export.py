"""Carryforward auto-export at the year boundary.

Year-boundary state survival is the only legal-graph output that *must*
cross a tax year. Capital-loss carryforwards (26 U.S.C. § 1212 /
§ 20 Abs. 6 EStG / § 23 Abs. 3 Sätze 7-9 EStG) and FTC carryovers
(26 U.S.C. § 904(c)) are computed by the 2025 rule graph and persisted
under ``years/<ws>/outputs/analysis-steps/final-legal-output.json``.
Without an auto-export the next year's loader has to hand-extract those
numbers from the 2025 Bescheid PDF / 1040 — exactly the failure mode the
F4 proposal in ``.review/2026-05-08-platform-flexibility-review.md`` §F4
calls out (and ``.review/2026-05-10-platform-flexibility-review.md`` §6
promotes to "first-tier" work).

This module emits ``outputs/carryforward-out-<juri>.csv`` files whose
schema matches the loader-side normalized-facts CSVs:

- ``carryforward-out-de.csv`` — same ``section,key,value,source,note``
  shape as ``years/<next>/normalized/facts/de-loss-carryforwards.csv``.
- ``carryforward-out-us.csv`` — same shape as
  ``years/<next>/normalized/facts/us-carryovers-and-payments.csv``.

Authorities cited per exported row:

- Germany stock-loss carryforward: § 20 Abs. 6 EStG.
  https://www.gesetze-im-internet.de/estg/__20.html
- Germany private-sale-loss carryforward: § 23 Abs. 3 Sätze 7-9 EStG.
  https://www.gesetze-im-internet.de/estg/__23.html
- U.S. capital-loss carryover: 26 U.S.C. §§ 1211-1212.
  https://www.law.cornell.edu/uscode/text/26/1212

Invariant posture (CLAUDE.md):

- This module performs NO legal arithmetic (I5). Every exported value
  comes verbatim from a declared rule output already persisted in
  ``final-legal-output.json``.
- The export is additive to the ``outputs/`` tree: it does not modify
  ``final-legal-output.json`` itself, so the pinned workspace md5s
  (``test_money_type.py``) remain byte-identical.
- File writes use ``atomic_write_text`` per I9.

Known gap (flagged 2026-05-11 by W1.B implementer): the 2025 U.S. rule
graph does not currently track an *ending* per-basket FTC carryover
(only the 2024 *starting* carryover that the user provided as input
and the year's allowed FTC). 26 U.S.C. § 904(c) unused-foreign-tax
carryover into 2026 is therefore NOT yet exportable. The capital-loss
carryforward (§ 1212) is the only U.S. value that is. When the FTC
carryover-to-2026 outputs land, add their rows here without touching
the loader schema.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from tax_pipeline.analysis_inputs import CSV_FIELDS
from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.paths import YearPaths

# Re-export the loader CSV header field list. Keeping the import here
# (rather than redeclaring the literal) means the export header rotates
# in lockstep with the loader header if it ever changes.
__all__ = [
    "DE_CARRYFORWARD_OUT_FILENAME",
    "US_CARRYFORWARD_OUT_FILENAME",
    "build_de_carryforward_rows",
    "build_us_carryforward_rows",
    "export_carryforwards_2025",
    "render_carryforward_csv",
]

DE_CARRYFORWARD_OUT_FILENAME = "carryforward-out-de.csv"
US_CARRYFORWARD_OUT_FILENAME = "carryforward-out-us.csv"

# Citation URLs used in the exported ``note`` fields. Each row carries
# the controlling §-authority so the audit packet of the *next* year
# can trace the imported number back to the legal basis under which it
# was computed in the prior year.
_ESTG_20_URL = "https://www.gesetze-im-internet.de/estg/__20.html"
_ESTG_23_URL = "https://www.gesetze-im-internet.de/estg/__23.html"
_USC_1212_URL = "https://www.law.cornell.edu/uscode/text/26/1212"

_SOURCE_FINAL_LEGAL_OUTPUT = "outputs/analysis-steps/final-legal-output.json"


def _read_string(node: Any, *path: str) -> str:
    """Walk ``node`` along the dotted ``path`` and return a string.

    Fails closed if any segment is missing or the leaf is not a string.
    The exported CSV must carry verbatim Decimal-as-string values from
    the rule-graph outputs; silently defaulting to ``"0"`` would
    fabricate prior-year state.
    """
    cursor: Any = node
    walked: list[str] = []
    for segment in path:
        walked.append(segment)
        if not isinstance(cursor, dict) or segment not in cursor:
            raise KeyError(
                "Missing carryforward value in final-legal-output.json: "
                f"{'.'.join(walked)}"
            )
        cursor = cursor[segment]
    if not isinstance(cursor, str):
        raise TypeError(
            "Carryforward value must be a Decimal-as-string in "
            f"final-legal-output.json at {'.'.join(walked)}: got {type(cursor).__name__}"
        )
    # Round-trip through Decimal as a sanity check; a malformed string
    # ("N/A", "") would silently corrupt the next year's loader.
    Decimal(cursor)
    return cursor


def build_de_carryforward_rows(final_output: dict[str, Any]) -> list[dict[str, str]]:
    """Build the Germany carryforward-out rows from ``final_output``.

    Two outputs roll forward from the 2025 DE rule graph:

    1. § 20 Abs. 6 EStG stock-loss carryforward remaining at year-end
       (``de.capital.stock_loss_carryforward_remaining_eur``). The next
       year's ``de-loss-carryforwards.csv`` consumes this as
       ``stock_loss_carryforward_2025_eur`` (the year stamp on the key
       advances; the §-authority is unchanged).
    2. § 23 Abs. 3 Sätze 7-9 EStG updated private-sale-loss
       carryforward at year-end
       (``de.private_sales.updated_private_sale_carryforward_eur``).
       The next year's loader consumes this as
       ``private_sale_loss_carryforward_2025_eur``.

    Both source values are produced by Pipeline 2 rule outputs and
    persisted in ``final-legal-output.json`` already — this function
    rearranges them into the loader's row shape.
    """
    forms = final_output.get("germany", {}).get("forms", {})
    if forms.get("status") == "not_applicable":
        return []
    results = forms.get("results", {})
    if not isinstance(results, dict):
        raise ValueError(
            "Germany carryforward export requires germany.forms.results in "
            "final-legal-output.json"
        )

    stock_remaining = _read_string(
        results, "capital", "stock_loss_carryforward_remaining_eur"
    )
    private_remaining = _read_string(
        results, "private_sales", "updated_private_sale_carryforward_eur"
    )

    return [
        {
            "section": "carryforward",
            "key": "stock_loss_carryforward_2025_eur",
            "value": stock_remaining,
            "source": _SOURCE_FINAL_LEGAL_OUTPUT,
            "note": (
                "§ 20 Abs. 6 EStG stock-loss carryforward remaining at end of 2025 "
                f"(auto-exported from DE25 capital rule graph). {_ESTG_20_URL}"
            ),
        },
        {
            "section": "carryforward",
            "key": "private_sale_loss_carryforward_2025_eur",
            "value": private_remaining,
            "source": _SOURCE_FINAL_LEGAL_OUTPUT,
            "note": (
                "§ 23 Abs. 3 Sätze 7-9 EStG updated private-sale-loss carryforward at "
                f"end of 2025 (auto-exported). {_ESTG_23_URL}"
            ),
        },
    ]


def build_us_carryforward_rows(final_output: dict[str, Any]) -> list[dict[str, str]]:
    """Build the U.S. carryforward-out rows from ``final_output``.

    One output rolls forward from the 2025 U.S. rule graph today:

    - 26 U.S.C. §§ 1211-1212 tentative capital-loss carryforward into
      2026 (``usa.forms.capital_results.capital.tentative_capital_loss_carryforward_2026_usd``).
      The engine's existing output key already names 2026 explicitly,
      so the next year's loader reads the same key verbatim.

    NOT yet exported (rule-graph gap flagged 2026-05-11): the
    26 U.S.C. § 904(c) per-basket unused-foreign-tax carryover INTO
    2026 is not currently a declared rule output. The DE25/US25 graphs
    track only the 2024 *starting* carryover (an input fact). Closing
    that gap is a follow-up F4 increment; until then the user must
    hand-extract those numbers from the 2025 Form 1116 (Part III line
    10 "Excess foreign taxes from prior years" on the 2026 return).
    """
    forms = final_output.get("usa", {}).get("forms", {})
    if forms.get("status") == "not_applicable":
        return []

    capital_results = forms.get("capital_results", {})
    if not isinstance(capital_results, dict):
        raise ValueError(
            "U.S. carryforward export requires usa.forms.capital_results in "
            "final-legal-output.json"
        )

    capital_loss_into_2026 = _read_string(
        capital_results, "capital", "tentative_capital_loss_carryforward_2026_usd"
    )

    return [
        {
            "section": "carryover",
            "key": "capital_loss_carryforward_into_2026_usd",
            "value": capital_loss_into_2026,
            "source": _SOURCE_FINAL_LEGAL_OUTPUT,
            "note": (
                "26 U.S.C. §§ 1211-1212 tentative capital-loss carryforward into 2026 "
                f"(auto-exported from US25 capital rule graph). {_USC_1212_URL}"
            ),
        },
    ]


def render_carryforward_csv(rows: Iterable[dict[str, str]]) -> str:
    """Render ``rows`` as a CSV string in the loader's wire format.

    The loaders consume the ``section,key,value,source,note`` header
    declared in ``analysis_inputs.CSV_FIELDS``. Using ``csv.DictWriter``
    via an in-memory buffer keeps the encoding (utf-8) and the line
    terminator ("\\n") deterministic, so byte-identical workspaces
    produce byte-identical carryforward exports.
    """
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_FIELDS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def export_carryforwards_2025(
    paths: YearPaths, final_output: dict[str, Any]
) -> dict[str, Any]:
    """Write the per-jurisdiction carryforward-out CSVs for the year.

    The CSVs land at ``paths.outputs_root / carryforward-out-{de,us}.csv``
    (sibling to ``analysis-steps/``, ``forms/``, ``legal-audit/`` — at
    the top of the workspace's ``outputs/`` tree so a downstream
    year-bootstrapping tool can locate them by a simple
    ``<workspace>/outputs/carryforward-out-*.csv`` glob without crawling
    sub-folders).

    A disabled jurisdiction (per CLAUDE.md invariant I13 — either
    ``elections.us_filing_required=false`` for U.S., or
    ``jurisdictions.<code>.enabled=false``) contributes no rows and
    produces no file: the absence of the CSV is the auditable opt-out
    posture, mirroring how ``final-legal-output.json`` records
    ``status: not_applicable`` for the disabled side.

    Returns a small report dict (``{country: {"path": Path|None,
    "rows": int}}``) so the caller can log what was written without
    re-reading the files.
    """
    paths.outputs_root.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {}

    de_rows = build_de_carryforward_rows(final_output)
    if de_rows:
        de_path = paths.outputs_root / DE_CARRYFORWARD_OUT_FILENAME
        atomic_write_text(de_path, render_carryforward_csv(de_rows))
        report["germany"] = {"path": de_path, "rows": len(de_rows)}
    else:
        report["germany"] = {"path": None, "rows": 0}

    us_rows = build_us_carryforward_rows(final_output)
    if us_rows:
        us_path = paths.outputs_root / US_CARRYFORWARD_OUT_FILENAME
        atomic_write_text(us_path, render_carryforward_csv(us_rows))
        report["usa"] = {"path": us_path, "rows": len(us_rows)}
    else:
        report["usa"] = {"path": None, "rows": 0}

    return report
