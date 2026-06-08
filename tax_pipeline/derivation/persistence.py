"""Persistence helpers for Pipeline 1 (Derivation) artifacts.

Two artifacts land per derivation run:

- ``derived-facts.json`` — the final-facts dict (initial facts plus
  every derivation stage's outputs), serialized with the same
  Decimal/dataclass/set canonicalization the legal-output triple
  uses. This is the typed boundary that Pipeline 2 reads.
- ``derivation-graph.json`` — the audit graph (same shape as
  ``legal-execution-graph.json``) describing which derivation stage
  produced which fact and the fingerprint chain.

Both files are committed via the shared
:func:`tax_pipeline.core.io.atomic_write_text` helper (unique tempfile
+ parent-directory fsync, see WS-2E / finding H9). Re-using the helper
keeps the atomicity / durability contract identical for Pipeline 1 and
Pipeline 2 outputs.

Authority context: derived facts feed § 32d Abs. 5 EStG per-Posten
foreign-tax credits (https://www.gesetze-im-internet.de/estg/__32d.html)
and InvStG § 2 Abs. 6 fund classifications
(https://www.gesetze-im-internet.de/invstg_2018/__2.html), so the
audit-trail rigor for these intermediate facts must match the
legal-output rigor downstream.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from tax_pipeline.core.io import AuditEncoder, atomic_write_text
from tax_pipeline.derivation.runtime import DerivationPipelineResult
from tax_pipeline.paths import YearPaths

DERIVATION_FACTS_NAME = "derived-facts.json"
DERIVATION_GRAPH_NAME = "derivation-graph.json"


def derivation_facts_path(paths: YearPaths) -> Path:
    """Resolve the workspace path for ``derived-facts.json``."""
    return paths.derivation_root / DERIVATION_FACTS_NAME


def derivation_graph_path(paths: YearPaths) -> Path:
    """Resolve the workspace path for ``derivation-graph.json``."""
    return paths.derivation_root / DERIVATION_GRAPH_NAME


def _facts_payload(final_facts: dict[str, Any]) -> dict[str, Any]:
    """Build the JSON-serializable form of the derived-facts dict.

    Re-encodes through :class:`AuditEncoder` so Decimals, dataclasses,
    and sets canonicalize identically to the legal-execution-graph
    serialization. Callers that round-trip the file get a
    Decimal-as-string surface (per the encoder contract) which is
    then parsed back into Decimals by Pipeline 2's input loader.
    """
    return {
        "schema_version": 1,
        "fact_keys": sorted(final_facts.keys()),
        # Round-trip through the audit encoder so the in-memory shape
        # collapses to JSON-native primitives. ``json.loads`` on the
        # encoded text yields the canonical form Pipeline 2 will read.
        "facts": json.loads(json.dumps(final_facts, cls=AuditEncoder)),
    }


def write_derivation_artifacts(
    paths: YearPaths,
    result: DerivationPipelineResult,
) -> tuple[Path, Path]:
    """Atomically write ``derived-facts.json`` and ``derivation-graph.json``.

    Returns the ``(facts_path, graph_path)`` pair. The two files form
    a consistent set: the facts dict is the bag of derived values
    produced by the stages described in the graph. A failure between
    the two writes leaves at most one file at the new content (each
    individual write is itself atomic per WS-2E).
    """
    paths.derivation_root.mkdir(parents=True, exist_ok=True)
    facts_path = derivation_facts_path(paths)
    graph_path = derivation_graph_path(paths)

    facts_payload = _facts_payload(result.final_facts)
    facts_text = (
        json.dumps(facts_payload, indent=2, sort_keys=True, cls=AuditEncoder) + "\n"
    )
    graph_text = (
        json.dumps(result.graph_dict, indent=2, sort_keys=True, cls=AuditEncoder) + "\n"
    )

    atomic_write_text(facts_path, facts_text)
    atomic_write_text(graph_path, graph_text)
    return facts_path, graph_path


def load_derivation_facts(paths: YearPaths) -> dict[str, Any]:
    """Load ``derived-facts.json`` for Pipeline 2 consumption.

    Pipeline 2 stages will eventually source their initial facts from
    this artifact instead of in-memory orchestrator state — see the
    invariant catalog entry in ``docs/invariant-migration-plan.md``
    §1.5. WS-5H exposes the loader so the reproducibility test in
    ``tests/y2025/test_derivation_to_legal_pipeline_reproducibility.py`` can
    verify Pipeline 2 is deterministic when re-fed the persisted facts.
    """
    facts_path = derivation_facts_path(paths)
    if not facts_path.exists():
        raise FileNotFoundError(
            f"Missing derived-facts artifact: {facts_path}. "
            "Run the derivation pipeline before Pipeline 2."
        )
    payload = json.loads(facts_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"derived-facts.json must contain a JSON object: {facts_path}")
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise ValueError(
            f"derived-facts.json missing required 'facts' object: {facts_path}"
        )
    return facts


# ---------------------------------------------------------------------------
# Pipeline 2 rehydration helpers
# ---------------------------------------------------------------------------
# ``derived-facts.json`` is the canonical Pipeline 1 → Pipeline 2 boundary
# (``docs/invariant-migration-plan.md`` §1.5). Persisting through
# :class:`AuditEncoder` is lossy for Python types Pipeline 2 stages still
# consume directly — Decimals serialize as fixed-point strings, frozensets as
# sorted lists, tuples as lists. The rehydrator below restores the canonical
# typed shape for the German-capital derivation outputs (DERIVE-DE25-13A
# through 13E plus DERIVE-DE25-FUND-CLASSIFICATION) so that DE25-13's
# ``calculate`` body sees the same value graph whether facts came from an
# in-memory ``execute_derivation_pipeline`` call or a disk round-trip.
#
# Authority: § 32d Abs. 5 EStG per-Posten audit-trail rigor
# (https://www.gesetze-im-internet.de/estg/__32d.html) requires that the
# derived-facts boundary is byte-stable; the typed-rehydration contract is
# what lets us keep that guarantee while routing through JSON.

_DECIMAL_KEYS_PER_SYMBOL_SALE_AGGREGATION = (
    "stock_gain",
    "fund_gain",
    "option_gain",
    "dher_stock_gain",
)
_DICT_OF_DECIMAL_KEYS_PER_SYMBOL_SALE_AGGREGATION = (
    "stock_symbol_gain",
    "fund_symbol_gain",
    "option_symbol_gain",
)

_DECIMAL_KEYS_BOX_1A = (
    "positive_income_total",
    "non_fund_positive_income_total",
    "explicit_foreign_tax_total",
)
_DICT_OF_DECIMAL_KEYS_BOX_1A = (
    "foreign_tax_by_item",
    "foreign_tax_refund_by_item",
    "fund_symbol_income",
)

_DECIMAL_KEYS_BANK_CERT_BUCKETS = (
    "domestic_capital_tax_withheld",
    "domestic_capital_soli_withheld",
)
_DICT_OF_DECIMAL_KEYS_BANK_CERT_BUCKETS = (
    "bank_certificate_non_stock_by_symbol",
    "bank_certificate_foreign_taxable_by_item",
    "stock_subset_by_certificate",
    "foreign_tax_by_certificate",
)
_DECIMAL_KEYS_BANK_CERT_SUMMARY = (
    "income",
    "stock_gain",
    "non_stock_income",
    "saver_allowance_used",
    "foreign_tax_credited",
    "foreign_tax_not_credited",
)

_DECIMAL_KEYS_SOURCE_COUNTRY = (
    "equity_fund_total",
    "non_equity_fund_total",
)

_DECIMAL_KEYS_FOREIGN_TAX_INDEXING = (
    "explicit_foreign_tax_total",
)
_DICT_OF_DECIMAL_KEYS_FOREIGN_TAX_INDEXING = (
    "foreign_tax_by_item",
    "foreign_tax_refund_by_item",
    "bank_certificate_foreign_taxable_by_item",
)


def _to_decimal(value: Any) -> Decimal:
    """Restore a Decimal from its :class:`AuditEncoder` string form."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _dict_of_decimal(value: Any) -> dict[str, Decimal]:
    if not isinstance(value, dict):
        raise ValueError(f"expected dict, got {type(value).__name__}")
    return {str(k): _to_decimal(v) for k, v in value.items()}


def _hydrate_per_symbol_sale_aggregation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.per_symbol_sale_aggregation must be a dict")
    out: dict[str, Any] = {}
    for key in _DECIMAL_KEYS_PER_SYMBOL_SALE_AGGREGATION:
        out[key] = _to_decimal(value[key])
    for key in _DICT_OF_DECIMAL_KEYS_PER_SYMBOL_SALE_AGGREGATION:
        out[key] = _dict_of_decimal(value[key])
    return out


def _hydrate_box_1a_filtered_dividends(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.box_1a_filtered_dividends must be a dict")
    out: dict[str, Any] = {}
    for key in _DECIMAL_KEYS_BOX_1A:
        out[key] = _to_decimal(value[key])
    for key in _DICT_OF_DECIMAL_KEYS_BOX_1A:
        out[key] = _dict_of_decimal(value[key])
    # ``income_items`` is a tuple of tuples ``(credit_item_id, symbol,
    # bucket, amount)``; JSON degrades both layers to lists. Restore the
    # tuple shape so DE25-13's downstream consumers (which iterate /
    # destructure with positional unpacking) see a stable type.
    raw_items = value["income_items"]
    income_items = tuple(
        (str(item[0]), str(item[1]), str(item[2]), _to_decimal(item[3]))
        for item in raw_items
    )
    out["income_items"] = income_items
    # Fallback ambiguity counts are dict[str, int] — JSON preserves ints.
    out["fallback_income_count_by_symbol"] = {
        str(k): int(v) for k, v in value["fallback_income_count_by_symbol"].items()
    }
    out["fallback_tax_count_by_symbol"] = {
        str(k): int(v) for k, v in value["fallback_tax_count_by_symbol"].items()
    }
    return out


def _hydrate_per_symbol_bank_certificate_buckets(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.per_symbol_bank_certificate_buckets must be a dict")
    summary = value["bank_certificate_summary"]
    if not isinstance(summary, dict):
        raise ValueError("bank_certificate_summary must be a dict")
    out: dict[str, Any] = {
        "bank_certificate_summary": {
            key: _to_decimal(summary[key]) for key in _DECIMAL_KEYS_BANK_CERT_SUMMARY
        }
    }
    for key in _DECIMAL_KEYS_BANK_CERT_BUCKETS:
        out[key] = _to_decimal(value[key])
    for key in _DICT_OF_DECIMAL_KEYS_BANK_CERT_BUCKETS:
        out[key] = _dict_of_decimal(value[key])
    return out


def _hydrate_source_country_classification(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.source_country_classification must be a dict")
    raw_symbols = value["fund_symbols"]
    if not isinstance(raw_symbols, (list, tuple, frozenset, set)):
        raise ValueError("fund_symbols must be a sequence in JSON form")
    fund_types = value["fund_types"]
    if not isinstance(fund_types, dict):
        raise ValueError("fund_types must be a dict")
    out: dict[str, Any] = {
        "fund_symbols": frozenset(str(s) for s in raw_symbols),
        "fund_types": {str(k): str(v) for k, v in fund_types.items()},
    }
    for key in _DECIMAL_KEYS_SOURCE_COUNTRY:
        out[key] = _to_decimal(value[key])
    return out


def _hydrate_foreign_tax_indexing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.foreign_tax_indexing must be a dict")
    out: dict[str, Any] = {}
    for key in _DECIMAL_KEYS_FOREIGN_TAX_INDEXING:
        out[key] = _to_decimal(value[key])
    for key in _DICT_OF_DECIMAL_KEYS_FOREIGN_TAX_INDEXING:
        out[key] = _dict_of_decimal(value[key])
    return out


def _hydrate_fund_classification(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("de.derived.fund_classification must be a dict")
    return {str(k): str(v) for k, v in value.items()}


def _hydrate_vorabpauschale_inputs(value: Any) -> dict[str, dict[str, Any]]:
    """Restore Decimal / int shapes for the per-fund Vorabpauschale index.

    InvStG § 18 / § 19 per-fund inputs are persisted as a sorted dict
    keyed by symbol with ``nav_start_eur`` / ``nav_end_eur`` /
    ``ausschuettung_eur`` (Decimal-as-string) and ``months_held`` (int).
    https://www.gesetze-im-internet.de/invstg_2018/__18.html
    https://www.gesetze-im-internet.de/invstg_2018/__19.html
    """
    if not isinstance(value, dict):
        raise ValueError("de.derived.vorabpauschale_inputs must be a dict")
    out: dict[str, dict[str, Any]] = {}
    for symbol, row in value.items():
        if not isinstance(row, dict):
            raise ValueError(
                "de.derived.vorabpauschale_inputs rows must be dicts"
            )
        out[str(symbol)] = {
            "nav_start_eur": _to_decimal(row["nav_start_eur"]),
            "nav_end_eur": _to_decimal(row["nav_end_eur"]),
            "ausschuettung_eur": _to_decimal(row["ausschuettung_eur"]),
            "months_held": int(row["months_held"]),
        }
    return out


_GERMANY_CAPITAL_DERIVED_FACT_HYDRATORS = {
    "de.derived.per_symbol_sale_aggregation": _hydrate_per_symbol_sale_aggregation,
    "de.derived.box_1a_filtered_dividends": _hydrate_box_1a_filtered_dividends,
    "de.derived.per_symbol_bank_certificate_buckets": (
        _hydrate_per_symbol_bank_certificate_buckets
    ),
    "de.derived.source_country_classification": _hydrate_source_country_classification,
    "de.derived.foreign_tax_indexing": _hydrate_foreign_tax_indexing,
    "de.derived.fund_classification": _hydrate_fund_classification,
    "de.derived.vorabpauschale_inputs": _hydrate_vorabpauschale_inputs,
}


def hydrate_germany_capital_derived_facts(
    raw_facts: dict[str, Any],
) -> dict[str, Any]:
    """Restore canonical Python types for Germany-capital ``de.derived.*`` keys.

    Pipeline 2 (DE25-13 through DE25-21) reads the ``de.derived.*`` facts
    persisted by Pipeline 1. The :class:`AuditEncoder` JSON form is lossy
    (Decimal → str, frozenset → list, tuple → list), so a direct
    ``json.loads`` would feed Pipeline 2 strings where it expects
    Decimals. This rehydrator restores the typed shape for every
    ``de.derived.*`` key DE25-13 declares as an input fact.

    Callers receive the same mapping shape ``execute_derivation_pipeline``
    would have returned in memory. Unknown keys (e.g., future Pipeline 1
    outputs not yet consumed by Germany capital) are passed through
    unchanged so adding a new derivation stage doesn't break this call
    site.
    """
    out: dict[str, Any] = {}
    for key, value in raw_facts.items():
        hydrator = _GERMANY_CAPITAL_DERIVED_FACT_HYDRATORS.get(key)
        if hydrator is None:
            out[key] = value
            continue
        out[key] = hydrator(value)
    return out


def load_germany_capital_derived_facts(paths: YearPaths) -> dict[str, Any]:
    """Load + rehydrate the Germany-capital ``de.derived.*`` facts from disk.

    Convenience wrapper around :func:`load_derivation_facts` +
    :func:`hydrate_germany_capital_derived_facts`. Used by
    ``germany_capital_initial_facts_2025`` to splice the persisted
    Pipeline 1 boundary state into DE25-13's initial facts so a Pipeline
    1 bug surfaces as a stale ``derived-facts.json`` artifact rather than
    as a silent mismatch in Pipeline 2's downstream legal output.
    """
    return hydrate_germany_capital_derived_facts(load_derivation_facts(paths))


__all__ = [
    "DERIVATION_FACTS_NAME",
    "DERIVATION_GRAPH_NAME",
    "derivation_facts_path",
    "derivation_graph_path",
    "hydrate_germany_capital_derived_facts",
    "load_derivation_facts",
    "load_germany_capital_derived_facts",
    "write_derivation_artifacts",
]
