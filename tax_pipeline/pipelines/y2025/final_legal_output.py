"""Final-legal-output assembly for the 2025 pipeline.

This module collects every per-jurisdiction sidecar artifact (Germany
analysis-step JSON, U.S. analysis-step JSON, treaty packet, narratives,
rule_outputs / form_lines / final_outputs provenance blocks) into the
single ``final-legal-output.json`` boundary that downstream renderers
consume.

Proposal 7 (architecture review 2026-05-04, §5) — IN PROGRESS:
the bespoke per-jurisdiction validation paths (``_validate_germany_*``,
``_validate_us_*``, ``_validate_treaty_*``) are still hardcoded by
country name. Germany validators have been extracted to
``jurisdictions/germany_final.py`` and USA validators (including
``_us_schedule_d_entries``) to ``jurisdictions/usa_final.py``;
both are re-exported here for the existing call sites. Treaty
validators remain inline pending P3 (registry-driven treaty stages)
landing — coordinating the cut now would conflict with that parallel
work. Once treaty surfaces also move out, the orchestrator dispatch
loop in ``build_final_legal_output_2025`` can become registry-driven
(architecture review §5 Proposal 7 Commit 5) along with the
schema_version field. Until then, adding a new per-jurisdiction
field still requires editing this file in multiple places — that
friction is documented as P2 (architecture review §4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.y2025.cross_jurisdiction import read_us_filing_required
from tax_pipeline.paths import YearPaths
from tax_pipeline.profile import TaxpayerProfile, profile_dict_for_embedding
from tax_pipeline.pipelines.y2025.final_legal_output_helpers import (
    _missing_artifact_error,
    _projection_dict_rows,
    _read_csv_rows,
    _read_json,
    _read_required_csv_rows,
    _read_required_json,
    _read_required_text,
    _read_text,
    _require_final_trace_authorities,
    _require_projected_rows_equal,
    _require_projected_text_equal,
)
from tax_pipeline.pipelines.y2025.jurisdictions.germany_final import (
    _required_core_anlage_n_projection,
    _validate_germany_final_output_supported,
    _validate_germany_render_projection,
)
from tax_pipeline.pipelines.y2025.jurisdictions.usa_final import (
    _us_schedule_d_entries,
    _validate_us_bucket_rows_projection,
    _validate_us_capital_results_projection,
    _validate_us_final_output_consistency,
)
from tax_pipeline.pipelines.y2025.rule_narrative_packets import build_rule_narratives_2025
from tax_pipeline.year_runtime import active_year_paths

FINAL_LEGAL_OUTPUT_NAME = "final-legal-output.json"
DISABLED_REASON = "disabled in config/profile.json"
US_FILING_NOT_REQUIRED_REASON = (
    "elections.us_filing_required=false in config/profile.json "
    "(26 U.S.C. § 6012 — household has no U.S. filing obligation)"
)
LEGAL_EXECUTION_GRAPH_JSON = "legal-execution-graph.json"
LEGAL_EXECUTION_GRAPH_MERMAID = "legal-execution-graph.mmd"


def final_legal_output_path(paths: YearPaths) -> Path:
    return paths.analysis_root / FINAL_LEGAL_OUTPUT_NAME


def _enabled_jurisdictions(profile: TaxpayerProfile) -> dict[str, bool]:
    """Return ``{germany, usa}`` enablement flags for the final-output writer.

    Mirrors ``run_year._enabled_jurisdictions_from_profile`` so the
    final-legal-output writer agrees with the orchestrator on which
    jurisdictions actually ran. Authority: 26 U.S.C. § 6012 —
    ``elections.us_filing_required=false`` is the canonical opt-out
    for the U.S. pathway.
    https://www.law.cornell.edu/uscode/text/26/6012

    T2.3 / F3: takes a typed :class:`TaxpayerProfile`. The
    :func:`read_us_filing_required` widening still consumes either
    typed or dict shape.
    """
    germany_enabled = (
        profile.jurisdictions["germany"].enabled
        if "germany" in profile.jurisdictions
        else True
    )
    usa_enabled = (
        profile.jurisdictions["usa"].enabled
        if "usa" in profile.jurisdictions
        else True
    )
    if not read_us_filing_required(profile):
        usa_enabled = False
    return {"germany": germany_enabled, "usa": usa_enabled}


def build_final_legal_output_2025(paths: YearPaths) -> dict[str, Any]:
    # T2.3 / F3 — typed profile load. Validates structure (unknown
    # keys, unknown elections, invalid kap_lines) at writer entry so
    # the final-legal-output writer never observes a typo-shaped
    # profile. The dict view used for the embedded
    # ``germany.forms.profile`` field strips ``schema_version`` so
    # adding that field to disk does not drift the workspace-output
    # md5s (see profile_dict_for_embedding).
    profile = TaxpayerProfile.from_json(paths.profile_path)
    profile_dict = profile_dict_for_embedding(profile)
    # Verify the legacy file shape parses too — defense in depth for
    # readers that bypass the typed loader (none in this writer, but
    # the dict-equivalence is the audit guarantee).
    _read_required_json(paths.profile_path)
    enabled = _enabled_jurisdictions(profile)
    us_filing_required = read_us_filing_required(profile)

    output: dict[str, Any] = {
        "schema_version": 1,
        "tax_year": paths.year,
        "source_role": "final legal output consumed by renderers",
        # 26 U.S.C. § 6012 (Persons required to make returns of income):
        # surface the user-facing posture so audit consumers can tell
        # an opt-out run apart from a workspace-config disable, without
        # parsing the per-jurisdiction "reason" string.
        # https://www.law.cornell.edu/uscode/text/26/6012
        "us_filing_required": us_filing_required,
    }

    if enabled["germany"]:
        germany_results = _read_required_json(paths.analysis_root / "germany-model-results.json")
        _validate_germany_final_output_supported(germany_results)
        # Employee-expense detail can be empty; renderers then emit an explicit
        # "No deduction rows present" note from this traceable artifact.
        germany_work_expense_rows = _read_required_csv_rows(
            paths.analysis_root / "germany-n-work-expenses.csv",
            allow_empty=True,
        )
        germany_anlage_n_entries_by_slot = _required_core_anlage_n_projection(germany_results)
        germany_trace_path = paths.analysis_root / "germany-model-trace.csv"
        germany_trace_rows = _read_required_csv_rows(germany_trace_path)
        _require_final_trace_authorities(germany_trace_rows, germany_trace_path)
        germany_overview = _read_required_text(paths.analysis_root / "germany-audit-note.md")
        germany_assumptions = _read_required_csv_rows(
            paths.tax_positions_root / "de-model-assumptions.csv",
            allow_empty=True,
        )
        kap_summary_rows = _read_required_csv_rows(paths.analysis_root / "germany-kap-summary.csv")
        kap_inv_fund_summary_rows = _read_required_csv_rows(
            paths.analysis_root / "germany-kap-inv-fund-summary.csv",
            allow_empty=True,
        )
        # Anlage Kind summary — § 33b Abs. 5 EStG transferred Pauschbetrag.
        # Always materialized (the row exists with a 0.00 amount when no
        # qualifying child has a §-33b Pauschbetrag) so the form-line
        # surface is auditable on every workspace per invariant I3 +
        # CLAUDE.md "fail closed; never silently default to zero" — the
        # explicit 0.00 row is the auditable absence.
        # https://www.gesetze-im-internet.de/estg/__33b.html
        kind_summary_rows = _read_required_csv_rows(
            paths.analysis_root / "germany-kind-summary.csv",
        )
        germany_elster_entry_sheet = _read_required_text(paths.analysis_root / "germany-elster-entry-sheet.md")
        _validate_germany_render_projection(
            germany_results,
            kap_summary_rows=kap_summary_rows,
            kap_inv_fund_rows=kap_inv_fund_summary_rows,
            n_work_expense_rows=germany_work_expense_rows,
            kind_summary_rows=kind_summary_rows,
        )
        _require_projected_text_equal(
            germany_elster_entry_sheet,
            germany_results.get("render_projection", {}).get("elster", {}).get("entry_sheet_markdown"),
            path_name="germany-elster-entry-sheet.md",
        )
        output["germany"] = {
            "forms": {
                # T2.3 / F3: embed the dict view of the typed profile.
                # ``profile_dict_for_embedding`` strips ``schema_version``
                # so the embedded shape stays byte-stable across the F3
                # landing — preserves the workspace-output md5s pinned
                # in ``tests/y_agnostic/test_money_type.py``.
                "profile": profile_dict,
                "results": germany_results,
                "summary_text": _read_required_text(paths.analysis_root / "germany-summary.md"),
                "elster_entry_sheet_text": germany_elster_entry_sheet,
                "kap_summary_rows": kap_summary_rows,
                "n_work_expense_rows": germany_work_expense_rows,
                "anlage_n_entries_by_slot": germany_anlage_n_entries_by_slot,
                # Empty per-fund rows are valid when no investment funds were found;
                # requiring the file still makes that empty state auditable.
                "kap_inv_fund_summary_rows": kap_inv_fund_summary_rows,
                # Anlage Kind 2025 Zeile 65 surface for § 33b Abs. 5 EStG
                # transferred Pauschbetrag. https://www.gesetze-im-internet.de/estg/__33b.html
                "kind_summary_rows": kind_summary_rows,
            },
            "legal_audit": {
                "results": germany_results,
                "overview_text": germany_overview,
                "trace_rows": germany_trace_rows,
                "assumption_rows": germany_assumptions,
            },
        }
    else:
        output["germany"] = {
            "forms": {"profile": profile_dict, "status": "not_applicable", "reason": DISABLED_REASON},
            "legal_audit": {"status": "not_applicable", "reason": DISABLED_REASON},
        }

    if enabled["usa"]:
        us_tax_estimate = _read_required_json(paths.analysis_root / "us-tax-estimate.json")
        us_treaty_package = _read_required_json(paths.analysis_root / "us-treaty-package.json")
        _validate_us_final_output_consistency(us_tax_estimate, us_treaty_package)
        us_capital_results = _read_required_json(paths.analysis_root / "us-capital-results.json")
        _validate_us_capital_results_projection(us_tax_estimate, us_capital_results)
        us_bucket_rows = _read_required_csv_rows(
            paths.analysis_root / "us-form-8949-income-buckets.csv",
            allow_empty=True,
        )
        _validate_us_bucket_rows_projection(us_tax_estimate, us_bucket_rows)
        us_trace_path = paths.analysis_root / "us-tax-trace.csv"
        us_trace_rows = _read_required_csv_rows(us_trace_path)
        _require_final_trace_authorities(us_trace_rows, us_trace_path)
        us_overview = _read_required_text(paths.analysis_root / "us-audit-note.md")
        us_assumptions = _read_required_csv_rows(
            paths.tax_positions_root / "us-model-assumptions.csv",
            allow_empty=True,
        )
        output["usa"] = {
            "forms": {
                "treaty_package": us_treaty_package,
                "tax_estimate": us_tax_estimate,
                "capital_results": us_capital_results,
                "schedule_d_entries": _us_schedule_d_entries(us_capital_results),
                # Form 8949 buckets can be empty for taxpayers with no reportable
                # disposition buckets, but the CSV must exist to trace that fact.
                "bucket_rows": us_bucket_rows,
                "trace_rows": us_trace_rows,
                "ftc_support_rows": _read_required_csv_rows(paths.derived_facts_root / "usa" / "ftc-support.csv"),
                "tax_constants_rows": _read_required_csv_rows(paths.reference_data_root / "us-tax-constants.csv"),
                "supporting_statements_text": _read_required_text(paths.analysis_root / "us-supporting-statements.md"),
                "treaty_entry_sheet_text": _read_required_text(paths.analysis_root / "us-treaty-entry-sheet.md"),
            },
            "legal_audit": {
                "results": us_tax_estimate,
                "overview_text": us_overview,
                "trace_rows": us_trace_rows,
                "assumption_rows": us_assumptions,
            },
        }
    else:
        # When ``us_filing_required=false`` (26 U.S.C. § 6012 opt-out),
        # the U.S. pathway intentionally produced no artifacts. Use a
        # citation-bearing reason string so the audit packet can tell
        # an opt-out apart from a workspace-config disable.
        usa_reason = (
            US_FILING_NOT_REQUIRED_REASON
            if not us_filing_required
            else DISABLED_REASON
        )
        output["usa"] = {
            "forms": {"status": "not_applicable", "reason": usa_reason},
            "legal_audit": {"status": "not_applicable", "reason": usa_reason},
        }

    output["narratives"] = build_rule_narratives_2025(output)

    # WS-4D / invariant I11: persist the (stage_id, output_key, fingerprint)
    # triple alongside the rendered values so the audit packet carries
    # per-rule-output provenance. Reviewers / auditors can map each
    # form-line value back to its producing stage without re-running the
    # rule graph. The triples are harvested from the narrative packets'
    # ``stage_output_fingerprints`` (which the executor threads through
    # the StageResult chain — no parallel third-domain re-hash).
    output["_provenance"] = _build_legal_value_provenance(output)

    return output


def _build_legal_value_provenance(output: dict[str, Any]) -> dict[str, Any]:
    """Build the per-rule-output ``(stage_id, output_key, fingerprint)``
    provenance map for invariant I11.

    Walks the narrative packets in ``output["narratives"]``, picks the
    stage-backed packets (those with ``stage_output_fingerprints``), and
    emits ``rule_outputs[country][rule_id][output_key] = {stage_id,
    output_key, fingerprint}`` plus a flat
    ``form_lines[country][output_key]`` view keyed by the form-line refs
    each output landed on. Non-stage narrative packets (hand-crafted
    summary nodes) are skipped because they have no executor-side
    fingerprint chain — the legal-execution-graph already documents them
    via ``audit_packet_fingerprint``.

    The schema is intentionally additive: existing readers of
    ``final-legal-output.json`` ignore the ``_provenance`` key; new
    readers (auditors, the make-check invariant battery) consult it
    directly.

    See ``docs/invariant-migration-plan.md`` §6 / WS-4D and CLAUDE.md
    invariant I11.
    """
    rule_outputs: dict[str, dict[str, dict[str, dict[str, str]]]] = {}
    form_lines: dict[str, dict[str, dict[str, str]]] = {}
    for country, by_language in (output.get("narratives") or {}).items():
        if not isinstance(by_language, dict):
            continue
        # Pick a deterministic language for the per-output triple. The
        # stage_output_fingerprints are language-invariant (the executor
        # produced one StageResult per stage), so any language with a
        # populated map yields the same triples. We prefer "en" for the
        # public audit trail; fall back to "de" if "en" is absent.
        rules = by_language.get("en") or by_language.get("de") or []
        if not isinstance(rules, list):
            continue
        rule_outputs.setdefault(country, {})
        form_lines.setdefault(country, {})
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            stage_output_fingerprints = rule.get("stage_output_fingerprints") or {}
            if not isinstance(stage_output_fingerprints, dict):
                continue
            rule_id = str(rule.get("rule_id", "")).strip()
            if not rule_id or not stage_output_fingerprints:
                # Non-stage summary packet — covered by the legal-
                # execution-graph's audit_packet_fingerprint; no per-key
                # executor fingerprint exists.
                continue
            per_output: dict[str, dict[str, str]] = {}
            for output_key, fingerprint in stage_output_fingerprints.items():
                triple = {
                    "stage_id": rule_id,
                    "output_key": str(output_key),
                    "fingerprint": str(fingerprint),
                }
                per_output[str(output_key)] = triple
                form_lines[country][str(output_key)] = triple
            rule_outputs[country][rule_id] = per_output
    return {
        "schema_version": 1,
        "rule_outputs": rule_outputs,
        "form_lines": form_lines,
    }


def _iter_narrative_packets(output: dict[str, Any]) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for country, by_language in output.get("narratives", {}).items():
        if not isinstance(by_language, dict):
            continue
        for language, rules in by_language.items():
            for rule in rules:
                packet = dict(rule)
                packet["_graph_country"] = country
                packet["_graph_language"] = language
                packets.append(packet)
    return packets


def build_legal_execution_graph_2025(output: dict[str, Any]) -> dict[str, Any]:
    """Build the legal-execution-graph from narrative packets.

    The graph's per-key ``input_fingerprints`` / ``output_fingerprints`` are
    the *same* values the executor produced on its ``StageResult`` records:
    they are threaded through the narrative packet via
    ``stage_input_fingerprints`` / ``stage_output_fingerprints`` (see
    ``rule_narrative_packets._stage_rule``). Re-hashing the narrative dict
    here would produce a parallel third-domain chain that is unrelated to
    the executor's commitments — exactly the bug WS-5C of
    ``docs/invariant-migration-plan.md`` removes.

    For non-stage narrative packets (hand-crafted summaries that do not
    correspond to any executed ``LawStage``), there is no per-key
    ``StageResult`` fingerprint to reference; the per-key fingerprints
    fall back to the packet-level audit fingerprint (which IS the
    canonical commitment for those summary nodes — they are a single
    audit object with no executor-side per-key chain).
    """
    packets = _iter_narrative_packets(output)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    producer_by_scope_output_key: dict[tuple[str, str, str], str] = {}
    output_fingerprint_by_scope_key: dict[tuple[str, str, str], str] = {}
    for packet in packets:
        if packet["template_id"] != packet["rule_id"]:
            raise ValueError(
                "legal execution graph requires narrative template_id to equal rule_id "
                f"for {packet['rule_id']}"
            )
        packet_fingerprint = packet.get("fingerprint")
        if not packet_fingerprint:
            raise ValueError(f"legal execution graph requires narrative packet fingerprint for {packet['rule_id']}")
        country = packet["_graph_country"]
        language = packet["_graph_language"]
        node_id = f"{country}-{language}-{packet['rule_id']}"
        # Stage-backed packets carry the executor's StageResult fingerprints
        # threaded through ``stage_input_fingerprints`` / ``stage_output_fingerprints``.
        # Non-stage summary packets do not, so the per-key fingerprint
        # collapses to the packet-level audit fingerprint.
        stage_output_fingerprints: dict[str, str] = dict(packet.get("stage_output_fingerprints", {}) or {})
        stage_input_fingerprints: dict[str, str] = dict(packet.get("stage_input_fingerprints", {}) or {})
        output_fingerprints: dict[str, str] = {}
        for item in packet["outputs"]:
            key = item["key"]
            output_fingerprints[key] = stage_output_fingerprints.get(key, packet_fingerprint)
        input_fingerprints: dict[str, str] = {}
        for item in packet["inputs"]:
            input_key = item["key"]
            scoped_key = (country, language, input_key)
            producer = producer_by_scope_output_key.get(scoped_key)
            if producer:
                edges.append(
                    {
                        "from_node_id": producer,
                        "from_output_key": input_key,
                        "to_node_id": node_id,
                        "to_input_key": input_key,
                    }
                )
                input_fingerprints[input_key] = output_fingerprint_by_scope_key[scoped_key]
            else:
                input_fingerprints[input_key] = stage_input_fingerprints.get(
                    input_key, packet_fingerprint
                )
        nodes.append(
            {
                "node_id": node_id,
                "rule_id": packet["rule_id"],
                "country": country,
                "language": language,
                "template_id": packet["template_id"],
                "audit_packet_fingerprint": packet_fingerprint,
                "legal_refs": packet["legal_refs"],
                "authority_urls": packet["authority_urls"],
                "input_keys": list(input_fingerprints),
                "output_keys": list(output_fingerprints),
                "input_fingerprints": input_fingerprints,
                "output_fingerprints": output_fingerprints,
                "form_lines": packet["form_lines"],
            }
        )
        for output_key in output_fingerprints:
            scoped_key = (country, language, output_key)
            producer_by_scope_output_key[scoped_key] = node_id
            output_fingerprint_by_scope_key[scoped_key] = output_fingerprints[output_key]
    return {
        "schema_version": 1,
        "source": FINAL_LEGAL_OUTPUT_NAME,
        "nodes": nodes,
        "edges": edges,
    }


def render_legal_execution_graph_mermaid_2025(graph: dict[str, Any]) -> str:
    lines = ["flowchart TD"]
    for node in graph["nodes"]:
        safe_id = str(node["node_id"]).replace("-", "_")
        lines.append(f'  {safe_id}["{node["rule_id"]}"]')
    for edge in graph["edges"]:
        lines.append(
            "  "
            f"{str(edge['from_node_id']).replace('-', '_')} "
            f"-->|{edge['from_output_key']}| "
            f"{str(edge['to_node_id']).replace('-', '_')}"
        )
    return "\n".join(lines) + "\n"


def write_final_legal_output_2025(paths: YearPaths) -> Path:
    """Single-writer entry for the final-legal-output triple.

    Three artifacts must remain consistent with each other:
    - ``final-legal-output.json`` — the merged legal output payload
    - ``legal-execution-graph.json`` — the audit-trail graph derived from it
    - ``legal-execution-graph.mmd`` — the Mermaid rendering of that graph

    Form renderers (``forms/germany.py``, ``forms/usa.py``) and the
    narrative / verbose-report pipelines read whichever of these files
    they need. A partial failure mid-write would leave a stale
    ``final-legal-output.json`` paired with the previous run's graph
    files (or vice versa), which is hard to detect downstream.

    Build the full triple in memory first, then commit each file via
    ``atomic_write_text`` (temp + fsync + os.replace). Any exception
    while building leaves the prior triple intact; the final commit
    block is the only mutation point for these paths.
    """
    output_path = final_legal_output_path(paths)
    output = build_final_legal_output_2025(paths)
    graph = build_legal_execution_graph_2025(output)
    graph_json_path = paths.analysis_root / LEGAL_EXECUTION_GRAPH_JSON
    graph_mermaid_path = paths.analysis_root / LEGAL_EXECUTION_GRAPH_MERMAID

    output_text = json.dumps(output, indent=2, sort_keys=True) + "\n"
    graph_text = json.dumps(graph, indent=2, sort_keys=True) + "\n"
    mermaid_text = render_legal_execution_graph_mermaid_2025(graph)

    atomic_write_text(output_path, output_text)
    atomic_write_text(graph_json_path, graph_text)
    atomic_write_text(graph_mermaid_path, mermaid_text)
    return output_path


def load_final_legal_output_2025(paths: YearPaths) -> dict[str, Any]:
    path = final_legal_output_path(paths)
    if not path.exists():
        raise FileNotFoundError(f"Missing final legal output: {path}")
    try:
        output = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid final legal output JSON: {path}") from exc
    if not isinstance(output, dict):
        raise ValueError(f"Invalid final legal output JSON: expected object at {path}")
    return output


def main() -> None:
    write_final_legal_output_2025(active_year_paths(Path(__file__), default_year=2025))


if __name__ == "__main__":
    main()
