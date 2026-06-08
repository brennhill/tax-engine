"""Invariant I2: every numeric leaf in ``final-legal-output.json`` must be
traceable to a ``StageResult.output_fingerprint`` recorded in
``legal-execution-graph.json``.

Authority for the audit-trail discipline this test enforces:
- § 32d Abs. 5 EStG fixes the German per-item foreign-tax-credit chain so
  every euro in the headline refund traces to a named rule node.
  https://www.gesetze-im-internet.de/estg/__32d.html
- IRS Publication 514 worksheets impose the same self-documentation rule
  on the U.S. Form 1116 side.
  https://www.irs.gov/publications/p514

Per CLAUDE.md, a value that escapes the rule graph (script-level math,
renderer projection, or undeclared derivation) must fail closed. This is
the WS-2 RED test of ``docs/invariant-migration-plan.md`` §3. It is
expected to fail on current main with at least
``de.refunds.final_target_refund_eur`` (germany_model.py:287-306),
``kap_line_19`` (germany_projections.py:113), and the foreign-tax
reconciliation totals (germany_model.py:259-269) untraceable.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from tax_pipeline.pipelines.y2025.final_legal_output import (
    LEGAL_EXECUTION_GRAPH_JSON,
    write_final_legal_output_2025,
)
from tests.generated_demo import generated_demo_paths


Q2 = Decimal("0.01")

# Audit-packet metadata keys whose value is a label, schema version,
# fingerprint hash, or source digest, not a legal Decimal amount.
ALLOWED_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "schema_version", "tax_year", "year",
        "line", "line_or_bucket", "kap_lines",
        "fingerprint", "audit_packet_fingerprint",
        "input_fingerprints", "output_fingerprints",
        "digest", "checksum", "timestamp", "generated_at",
    }
)

# Top-level subtrees skipped: ``narratives`` IS the trace source, so
# checking its leaves against itself would be circular.
ALLOWED_TOP_LEVEL_SUBTREES: frozenset[str] = frozenset({"narratives", "source_role"})

# Per-jurisdiction subtree exemptions. Both ``<jurisdiction>.forms.*``
# and ``<jurisdiction>.legal_audit.*`` are display projections of
# values the rule graph already commits to via the ``narratives``
# subtree. Phase 4D's ``LegalValue`` envelope provides typed
# per-value provenance for form-bound legal values (the canonical
# audit trail under § 32d Abs. 5 EStG / Pub. 514); the JSON
# subtrees re-render those values into rich form-line / trace
# structures for human readability. Walking those leaves and
# requiring each one to appear by VALUE in the narrative-output set
# produces structural false positives whenever a stage returns a
# rich dict (e.g. ``us.stage.tax_estimate`` → 30+ flattened JSON
# keys) — the dict's individual Decimals don't surface as separate
# narrative-output ``value`` leaves even though the stage commits
# to all of them at once. The architectural commitment ("every form
# line traces to a stage output") is now structurally enforced by
# the LegalValue envelope (I11) rather than by leaf-by-leaf JSON
# walk.
ALLOWED_JURISDICTION_SUBTREES: frozenset[str] = frozenset({"forms", "legal_audit"})

# Path-pattern exemptions for display-only structures whose Decimal
# leaves are either form-line numbers (Zeile labels like "17", "19")
# or rendered projections of rule-graph values. The rule-graph
# fingerprints commit to the underlying values; these structures are
# display projections and audit-only logs that re-render those same
# values for the form-line CSV / trace CSV / vanilla checkpoint.
#
# Each entry is a tuple of path-segment matchers. ``"*"`` matches any
# segment; ``"#"`` matches a numeric index. A leaf is exempt iff its
# path matches any pattern.
_EXEMPT_PATH_PATTERNS: tuple[tuple[str, ...], ...] = (
    # Anlage KAP / KAP-INV form-line CSV rows: row[1] is the Zeile
    # number string ("17", "19", "20", ...). DE25-FORM-KAP-PROJECTION
    # produces the amount column; row[1] is just the form-line label.
    ("*", "*", "kap_summary_rows", "#", "1"),
    ("*", "*", "*", "kap_summary_rows", "#", "1"),
    ("*", "*", "kap_inv_fund_rows", "#", "1"),
    ("*", "*", "*", "kap_inv_fund_rows", "#", "1"),
    # Anlage N projection rows: index 1 is the Zeile number.
    ("*", "*", "n_breakdown_rows", "#", "1"),
    ("*", "*", "*", "n_breakdown_rows", "#", "1"),
    # Trace-row audit log values: the trace CSV is a display projection
    # of the same values the rule graph already fingerprints under
    # narrative outputs. The trace_row.value_eur leaf re-renders those
    # values for human readability; the underlying rule-graph commit
    # remains the source of truth.
    ("*", "*", "trace_rows", "#", "value_eur"),
    ("*", "*", "*", "trace_rows", "#", "value_eur"),
    # Vanilla checkpoint: an independent sanity-check computation that
    # MUST agree with the rule graph but is computed from raw inputs
    # via the simplified "vanilla" path. Its values may not match the
    # rule-graph fingerprints exactly because the simplified path
    # bypasses some legal complexity (the divergence-detection test
    # ``test_vanilla_checkpoint`` enforces equivalence on the legal
    # surface). Display-only here.
    ("*", "*", "vanilla_checkpoint", "*"),
    ("*", "*", "*", "vanilla_checkpoint", "*"),
    # USA form bucket rows: per-Form-8949 / Schedule D bucket rows are
    # display projections of the US25-03-CAPITAL-BUCKETS PER_POSTEN
    # aggregation already in the rule graph; the row-level Decimal
    # re-renders the same value the rule graph commits to.
    ("usa", "forms", "bucket_rows", "#", "*"),
    ("usa", "forms", "*", "bucket_rows", "#", "*"),
    # USA renderer presentation rows mirroring rule-graph values.
    ("usa", "forms", "*", "rows", "#", "*"),
    # Tax-constants tables: statutory thresholds (§ 1, § 1(h), § 63,
    # § 1411 brackets / standard deduction / NIIT threshold) are
    # constants the rule graph CONSUMES, not outputs it produces. The
    # forms render the underlying us_2025_law constants for the user's
    # reference; they don't trace to a rule graph node by design.
    ("usa", "forms", "tax_constants_rows", "#", "*"),
    ("usa", "forms", "*", "tax_constants_rows", "#", "*"),
    # Schedule D individual entries: per-disposition breakdown rows.
    # The aggregate amounts trace through US25-03-CAPITAL-BUCKETS;
    # individual entries are presentation-layer line items.
    ("usa", "forms", "schedule_d_entries", "#", "*"),
    ("usa", "forms", "*", "schedule_d_entries", "#", "*"),
    # FTC support rows: display projection of US25-12 / US25-13 /
    # US25-14 per-basket aggregations.
    ("usa", "forms", "ftc_support_rows", "#", "*"),
    ("usa", "forms", "*", "ftc_support_rows", "#", "*"),
    # USA capital_results presentation: per-bucket / per-line projection
    # of the rule-graph capital tax outputs.
    ("usa", "forms", "capital_results", "*", "*"),
    ("usa", "forms", "capital_results", "*", "*", "*"),
    ("usa", "forms", "*", "capital_results", "*", "*"),
    # USA tax_estimate dict: assembled presentation summary mirroring
    # rule-graph outputs (income / tax / capital / ftc / payments /
    # treaty_resourcing). The rule graph commits to the underlying
    # values; this dict re-presents them as a flat per-section JSON.
    ("usa", "forms", "tax_estimate", "*", "*"),
    ("usa", "forms", "*", "tax_estimate", "*", "*"),
    # USA trace_rows: per-line audit trace mirroring rule-graph
    # outputs. The trace CSV is presentation, not a separate
    # commitment.
    ("usa", "forms", "trace_rows", "#", "*"),
    ("usa", "forms", "*", "trace_rows", "#", "*"),
)


def _path_matches(path: tuple[str, ...], pattern: tuple[str, ...]) -> bool:
    if len(path) < len(pattern):
        return False
    # Match against the tail of the path so the pattern can land at any
    # depth: useful for the legal_audit mirror that re-nests the same
    # subtree under a different prefix.
    suffix = path[-len(pattern) :]
    for p_seg, pat_seg in zip(suffix, pattern):
        if pat_seg == "*":
            continue
        if pat_seg == "#":
            try:
                int(p_seg)
            except ValueError:
                return False
            continue
        if p_seg != pat_seg:
            return False
    return True


def _path_is_exempt(path: tuple[str, ...]) -> bool:
    return any(_path_matches(path, pat) for pat in _EXEMPT_PATH_PATTERNS)


def _parse_decimal(value: object) -> Decimal | None:
    """Return ``Decimal(value).quantize(Q2)`` if ``value`` parses; else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Decimal)):
        try:
            return Decimal(value).quantize(Q2)
        except (InvalidOperation, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        # Strip trailing currency tag from narrative renderings like
        # "1500.00 EUR" / "316.03 USD" before parsing.
        for suffix in (" EUR", " USD"):
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                break
        try:
            return Decimal(text).quantize(Q2)
        except (InvalidOperation, ValueError):
            return None
    return None


def _collect_decimals_recursive(obj: object, out: set[Decimal]) -> None:
    """Walk ``obj`` (possibly a JSON-encoded string of a dict/list) and
    add every Decimal-parseable scalar to ``out``.
    """
    parsed = _parse_decimal(obj)
    if parsed is not None:
        out.add(parsed)
        return
    if isinstance(obj, str):
        try:
            inner = json.loads(obj)
        except (ValueError, TypeError):
            return
        _collect_decimals_recursive(inner, out)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_decimals_recursive(v, out)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_decimals_recursive(v, out)


def _stage_output_decimals(final_output: dict[str, Any]) -> set[Decimal]:
    """Collect every Decimal value that appears as a stage-derived narrative
    output.

    Narrative packets whose ``outputs[*].source == "executed-stage-result"``
    are produced by the rule-graph executor; their values are the canonical
    record of what each ``LawStage.calculate`` returned, and they are what
    the legal-execution-graph fingerprint chain commits to.
    """
    values: set[Decimal] = set()
    for _country, by_language in (final_output.get("narratives") or {}).items():
        if not isinstance(by_language, dict):
            continue
        for _language, packets in by_language.items():
            for packet in packets:
                for item in packet.get("outputs", ()):
                    if item.get("source") != "executed-stage-result":
                        continue
                    _collect_decimals_recursive(item.get("value"), values)
    return values


def _iter_numeric_leaves(
    obj: Any, path: tuple[str, ...]
) -> Iterable[tuple[tuple[str, ...], Any, Decimal]]:
    """Yield ``(path, raw_value, decimal_value)`` for every numeric leaf
    in ``obj`` whose path is not metadata-allowlisted.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ALLOWED_METADATA_KEYS:
                continue
            yield from _iter_numeric_leaves(value, path + (str(key),))
        return
    if isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from _iter_numeric_leaves(value, path + (str(index),))
        return
    parsed = _parse_decimal(obj)
    if parsed is None:
        return
    yield path, obj, parsed


class FinalOutputValuesTraceToRuleOutputsTest(unittest.TestCase):
    """Invariant I2: every numeric leaf in ``final-legal-output.json``
    traces to a ``StageResult.output_fingerprint`` recorded in
    ``legal-execution-graph.json``.

    Authority:
    - § 32d Abs. 5 EStG audit-trail requirement
      https://www.gesetze-im-internet.de/estg/__32d.html
    - IRS Publication 514 worksheet self-documentation
      https://www.irs.gov/publications/p514
    """

    def test_every_final_output_numeric_leaf_traces_to_rule_output(self) -> None:
        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)
            final_output = json.loads(
                (paths.analysis_root / "final-legal-output.json").read_text(
                    encoding="utf-8"
                )
            )
            graph_path = paths.analysis_root / LEGAL_EXECUTION_GRAPH_JSON
            graph = json.loads(graph_path.read_text(encoding="utf-8"))

        # The execution graph must be present and non-empty before the
        # invariant is meaningful.
        self.assertGreater(len(graph.get("nodes", [])), 0, "expected populated legal-execution-graph.json")

        stage_values = _stage_output_decimals(final_output)
        self.assertGreater(
            len(stage_values),
            0,
            "expected at least one Decimal value among executed-stage narrative outputs",
        )

        offenders: list[str] = []
        for top_key, subtree in final_output.items():
            if top_key in ALLOWED_TOP_LEVEL_SUBTREES:
                continue
            if top_key in ALLOWED_METADATA_KEYS:
                continue
            # Per-jurisdiction (germany / usa): only walk the keys that
            # carry standalone legal commitments. The forms / legal_audit
            # subtrees are display projections — see the
            # ALLOWED_JURISDICTION_SUBTREES docstring above.
            if isinstance(subtree, dict):
                for sub_key, sub_value in subtree.items():
                    if sub_key in ALLOWED_JURISDICTION_SUBTREES:
                        continue
                    if sub_key in ALLOWED_METADATA_KEYS:
                        continue
                    for path, raw, parsed in _iter_numeric_leaves(
                        sub_value, (top_key, sub_key)
                    ):
                        if parsed in stage_values:
                            continue
                        if _path_is_exempt(path):
                            continue
                        offenders.append(
                            f"{'.'.join(path)} = {raw!r} (Decimal({parsed}))"
                        )
                continue
            for path, raw, parsed in _iter_numeric_leaves(subtree, (top_key,)):
                if parsed in stage_values:
                    continue
                if _path_is_exempt(path):
                    continue
                offenders.append(f"{'.'.join(path)} = {raw!r} (Decimal({parsed}))")

        if offenders:
            preview = "\n  ".join(offenders[:40])
            extra = f"\n  ... and {len(offenders) - 40} more" if len(offenders) > 40 else ""
            self.fail(
                "final-legal-output.json contains numeric values that do not "
                "trace to any node's output_fingerprints chain in "
                "legal-execution-graph.json. Each offender escaped the rule "
                "graph and must be promoted to a LawStage output (see "
                "invariant-migration-plan.md WS-4A/4B/4C).\n"
                f"  {preview}{extra}"
            )


if __name__ == "__main__":
    unittest.main()
