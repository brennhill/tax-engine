from __future__ import annotations

import argparse
import json
import os
import runpy
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from tax_pipeline.analysis_inputs import missing_structured_inputs
from tax_pipeline.y2025.cross_jurisdiction import read_us_filing_required
from tax_pipeline.fact_extraction import extract_all_facts
from tax_pipeline.profile import TaxpayerProfile
from tax_pipeline.forms import (
    ensure_required_paths,
    render_germany_filing_guide,
    render_germany_forms,
    render_usa_filing_guide,
    render_usa_forms,
    required_germany_form_paths,
    required_usa_form_paths,
)
from tax_pipeline.legal_audit import (
    render_germany_legal_audit,
    render_usa_legal_audit,
    required_germany_legal_audit_paths,
    required_usa_legal_audit_paths,
)
from tax_pipeline.pipelines.y2025.final_legal_output import load_final_legal_output_2025
from tax_pipeline.pipeline_context import clear_pipeline_context
from tax_pipeline.y2025.carryforward_export import export_carryforwards_2025
from tax_pipeline.year_runtime import resolve_year_paths
from tax_pipeline.manifest import write_manifest
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_registry import get_year_definition


def pipeline_modules(year: int = 2025) -> list[str]:
    return list(get_year_definition(year).pipeline_modules)


def _enabled_jurisdictions_from_profile(
    profile: TaxpayerProfile | dict,
) -> dict[str, bool]:
    """Return ``{germany, usa}`` enablement flags for the orchestrator.

    Accepts either a typed :class:`TaxpayerProfile` (the F3 migration
    target) or a raw dict (for the legacy
    :func:`print_headline_summary` path that re-reads the embedded
    profile out of ``final-legal-output.json``). The
    :func:`read_us_filing_required` widening handles both shapes.

    Authority: 26 U.S.C. § 6012 — the user-facing
    ``elections.us_filing_required`` posture is the canonical opt-out
    for the U.S. pathway. The engine still respects the legacy
    ``jurisdictions.usa.enabled`` flag, but the posture flag overrides
    it when set to false.
    https://www.law.cornell.edu/uscode/text/26/6012
    """
    if isinstance(profile, TaxpayerProfile):
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
    else:
        jurisdictions = profile.get("jurisdictions", {})
        germany = jurisdictions.get("germany", {})
        usa = jurisdictions.get("usa", {})
        germany_enabled = bool(germany.get("enabled", True))
        usa_enabled = bool(usa.get("enabled", True))
    if not read_us_filing_required(profile):
        usa_enabled = False
    return {"germany": germany_enabled, "usa": usa_enabled}


def _read_json_config(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {label}: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return payload


def _load_profile_if_exists(paths) -> TaxpayerProfile | None:
    """Build a typed :class:`TaxpayerProfile` from the workspace.

    Returns ``None`` when the profile file is absent (the
    intake-wizard pre-config state). F3 (T2.3) — every profile read in
    this module funnels through this helper so the typed-validation
    contract runs exactly once per run.
    """
    if not paths.profile_path.exists():
        return None
    return TaxpayerProfile.from_json(paths.profile_path)


def _enabled_jurisdictions(paths) -> dict[str, bool]:
    profile = _load_profile_if_exists(paths)
    if profile is None:
        return {"germany": True, "usa": True}
    return _enabled_jurisdictions_from_profile(profile)


def _pipeline_modules_for_enabled(paths, year_definition) -> list[str]:
    profile = _load_profile_if_exists(paths)
    if profile is None:
        enabled = {"germany": True, "usa": True}
        crypto_supported = True
    else:
        enabled = _enabled_jurisdictions_from_profile(profile)
        crypto_supported = (
            profile.investment_defaults.crypto_supported
            if profile.investment_defaults is not None
            else True
        )
    manual_overrides = {}
    if paths.manual_overrides_path.exists():
        manual_overrides = _read_json_config(paths.manual_overrides_path, label="config/manual_overrides.json")
    equity_comp_capital_supported = bool(
        manual_overrides.get("equity_comp", {}).get("include_capital_sales", True)
    )
    modules: list[str] = []
    # WS-5H (invariant migration plan §1.5): Pipeline 1 (Derivation)
    # runs unconditionally before any Pipeline 2 (Legal) jurisdiction
    # module. The empty Pipeline 1 still writes ``derived-facts.json``
    # / ``derivation-graph.json`` so the boundary contract is
    # observable from the very first commit, and so WS-5A / WS-5B can
    # register stages without further plumbing.
    modules.extend(year_definition.derivation_modules)
    if enabled["germany"]:
        if crypto_supported:
            modules.append(year_definition.germany_optional_modules["crypto"])
        if equity_comp_capital_supported:
            modules.append(year_definition.germany_optional_modules["equity_comp_capital"])
        modules.extend(year_definition.germany_modules)
    if enabled["usa"]:
        modules.extend(year_definition.usa_modules)
    modules.extend(year_definition.report_modules)
    return modules


OBSOLETE_ANALYSIS_OUTPUTS = [
    "067-ecb-usd-eur-daily-2022-2025.csv",
    "070-capital-sales-detail.csv",
    "072-2025-income-cashflows.csv",
    "090-model-inputs.csv",
    "091-model-results.json",
    "092-model-trace.csv",
    "093-final-results-summary.md",
    "098-coinbase-private-sales-lot-detail.csv",
    "099-coinbase-private-sales-dispositions.csv",
    "100-coinbase-private-sales-summary.md",
    "101-coinbase-private-sales-results.json",
    "111-dher-german-capital-detail.csv",
    "112-dher-german-results.json",
    "113-dher-german-summary.md",
    "114-elster-entry-sheet.md",
    "115-kap-inv-fund-summary.csv",
    "116-n-werbungskosten-breakdown.csv",
    "117-elster-kap-summary.csv",
    "120-us-2025-capital-inputs.csv",
    "121-us-2025-capital-results.json",
    "122-us-2025-capital-summary.md",
    "123-us-2025-8949-and-income-buckets.csv",
    "124-us-2025-tax-model-inputs.csv",
    "125-us-2025-tax-estimate.json",
    "126-us-2025-tax-estimate.md",
    "127-us-2025-tax-trace.csv",
    "130-spouse-bank-capital-certificate-summary.md",
    "131-us-2025-chosen-treaty-package.json",
    "132-us-2025-treaty-resourcing-worksheet.csv",
    "133-us-2025-treaty-entry-sheet.md",
    "134-us-2025-supporting-statements.md",
    "de-us-treaty-dividend-packet.json",
    # Renamed 2026-05-04 to disambiguate from the legal-audit/<country>/
    # directory artifact. The new files are germany-audit-note.md and
    # us-audit-note.md; clean up stale copies from prior runs.
    "germany-legal-audit.md",
    "us-legal-audit.md",
]


def analysis_inputs_directory(
    project_root: Path,
    year: int | str,
    *,
    workspace_root: Path | None = None,
) -> Path:
    paths = resolve_year_paths(project_root, str(year), workspace_root=workspace_root)
    get_year_definition(paths.year)
    ensure_year_scaffold(paths)
    missing = missing_structured_inputs(paths)
    if missing:
        missing_names = ", ".join(path.as_posix() for path in missing)
        raise FileNotFoundError(
            f"Missing structured inputs for {paths.year}: {missing_names}. "
            "Populate years/<year>/normalized/reference-data, years/<year>/normalized/derived-facts, "
            "the extracted facts directories, and years/<year>/outputs/tax-positions before running the full pipeline. "
            f"For a grouped checklist, run: python3 -m tax_pipeline.validate_workspace {paths.year_root.name}"
        )
    return paths.analysis_root.resolve()


def remove_obsolete_analysis_outputs(analysis_root: Path) -> None:
    for name in OBSOLETE_ANALYSIS_OUTPUTS:
        path = analysis_root / name
        if path.exists():
            path.unlink()


def _run_pipeline_module(module_name: str, *, env: dict[str, str], cwd: Path) -> None:
    # Pipeline modules are ordinary Python modules. Running them in-process keeps
    # the year runtime auditable and avoids a shell/process boundary between data
    # gathering and the legal core execution.
    previous_env = os.environ.copy()
    previous_cwd = Path.cwd()
    try:
        os.environ.clear()
        os.environ.update(env)
        os.chdir(cwd)
        runpy.run_module(module_name, run_name="__main__", alter_sys=True)
    finally:
        os.chdir(previous_cwd)
        os.environ.clear()
        os.environ.update(previous_env)


# Type alias for the progress hook plumbed by the intake wizard. Each call
# records one structured event (``event``, ``stage_id``, ...). The hook is
# optional — CLI runs and unit tests pass ``None`` and the engine takes the
# normal silent path.
ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception:  # noqa: BLE001 - progress is observability, never load-bearing
        # A broken progress hook must not abort the pipeline. The wizard
        # falls back to "no events visible yet" rather than failing the
        # run for a logging error.
        pass


def _stage_id_for_module(module_name: str) -> str:
    """Map a pipeline-module dotted path to a wizard-facing stage_id.

    The full dotted path is unwieldy for a UI list; the trailing
    component is sufficient to identify the stage and matches the
    convention used in CLAUDE.md (e.g. ``DE25-00`` is a rule stage_id,
    ``germany_model`` is a pipeline-module stage_id).
    """
    return module_name.rsplit(".", 1)[-1]


# H2: official-source URL hosts we lift out of fail-closed rule
# messages. CLAUDE.md's tax-rule requirements mandate that every
# fail-closed ``raise ValueError(...)`` inside the rule modules embeds
# the gesetze-im-internet.de / law.cornell.edu / irs.gov URL in the
# message string. The wizard turns that URL into a hyperlink, so we
# detect it with a startswith check against the curated host list (no
# regex dependency, no false positives).
_AUTHORITY_URL_HOSTS = (
    "https://www.gesetze-im-internet.de",
    "https://www.law.cornell.edu",
    "https://www.irs.gov",
    "https://www.bmf",
    "https://www.bundesfinanzministerium.de",
)


def _extract_authority_url(message: str) -> str | None:
    """Return the first authority URL embedded in ``message``, or ``None``.

    The rule modules emit URLs as bare whitespace-bounded tokens; we
    tokenize on whitespace and accept the first token whose prefix
    matches a known official-source host. Trailing punctuation
    (``.``, ``)``, ``,``) is stripped so the link is clickable.
    """
    if not isinstance(message, str) or not message:
        return None
    for token in message.split():
        cleaned = token.strip().rstrip(".,;:)\"'")
        for host in _AUTHORITY_URL_HOSTS:
            if cleaned.startswith(host):
                return cleaned
    return None


def _extract_missing_input_key(message: str) -> str | None:
    """Best-effort lift of a missing-input-key from the executor's
    fail-closed ``"<stage_id> missing input facts: [...]"`` raise.

    Parse failure leaves the structured field ``None``; the caller still
    surfaces the original message so no statute context is hidden.
    """
    if not isinstance(message, str):
        return None
    marker = "missing input facts: "
    if marker not in message:
        return None
    tail = message.split(marker, 1)[1].lstrip()
    if not tail.startswith("["):
        return None
    # Walk to the matching closing bracket so a trailing URL / sentence
    # ("...]. https://...") does not get pulled into the key value.
    depth = 0
    for i, ch in enumerate(tail):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return tail[: i + 1]
    return None


class StageFailure(Exception):
    """Structured failure raised at the wizard's run boundary.

    The wizard's old ``/api/run`` returned a single opaque error string
    when a stage raised. H2 replaces that with a labeled error card
    showing the ``(stage_id, rule_id, missing_input_key, authority_url,
    original_message)`` triple — fail-closed rule errors already embed
    every field; we just stop dropping them on the floor.

    Attributes:

    * ``stage_id`` — pipeline-module / rule stage_id that raised, when
      known. ``None`` for failures outside any stage.
    * ``rule_id`` — same value as ``stage_id`` today (the executor uses
      a single id), but kept distinct so a future refactor that
      separates the two doesn't break the wizard contract.
    * ``missing_input_key`` — declared-input key list (as the executor
      formats it) when the underlying error is the executor's missing-
      inputs fail-closed raise.
    * ``authority_url`` — gesetze-im-internet.de / law.cornell.edu /
      irs.gov URL embedded in the rule-level error message, lifted to
      the structured field so the wizard renders it as a hyperlink.
    * ``original_message`` — verbatim error message; always shown in
      the wizard's failure card so no statute context is hidden when a
      structured field cannot be parsed.
    """

    def __init__(
        self,
        *,
        stage_id: str | None,
        rule_id: str | None,
        missing_input_key: str | None,
        authority_url: str | None,
        original_message: str,
    ) -> None:
        super().__init__(original_message)
        self.stage_id = stage_id
        self.rule_id = rule_id
        self.missing_input_key = missing_input_key
        self.authority_url = authority_url
        self.original_message = original_message

    @classmethod
    def from_exception(
        cls,
        exc: BaseException,
        *,
        stage_id: str | None = None,
        rule_id: str | None = None,
    ) -> "StageFailure":
        message = str(exc)
        return cls(
            stage_id=stage_id,
            rule_id=rule_id,
            missing_input_key=_extract_missing_input_key(message),
            authority_url=_extract_authority_url(message),
            original_message=message,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_id": self.stage_id,
            "rule_id": self.rule_id,
            "missing_input_key": self.missing_input_key,
            "authority_url": self.authority_url,
            "original_message": self.original_message,
        }


def _refund_or_balance_due(amount: object) -> tuple[str, str]:
    value = Decimal(str(amount))
    label = "refund" if value >= 0 else "balance due"
    return label, f"{abs(value):.2f}"
def print_headline_summary(paths) -> None:
    final_output = load_final_legal_output_2025(paths)
    enabled = _enabled_jurisdictions_from_profile(final_output.get("germany", {}).get("forms", {}).get("profile", {}))
    try:
        outputs_display = paths.analysis_root.relative_to(paths.project_root).as_posix()
    except ValueError:
        outputs_display = str(paths.analysis_root)

    print(f"Year {paths.year} complete")
    if enabled["germany"]:
        germany_results = final_output["germany"]["forms"]["results"]
        germany_label, germany_amount = _refund_or_balance_due(germany_results["refunds"]["final_target_refund_eur"])
        germany_vanilla_label, germany_vanilla_amount = _refund_or_balance_due(
            germany_results["vanilla_checkpoint"]["refund_or_balance_due_eur"]
        )
        print(f"  Germany {germany_label}: {germany_amount} EUR")
        print(f"  Germany vanilla checkpoint {germany_vanilla_label}: {germany_vanilla_amount} EUR")
    if enabled["usa"]:
        us_results = final_output["usa"]["forms"]["tax_estimate"]
        us_base_label, us_base_amount = _refund_or_balance_due(
            us_results["payments"]["refund_if_positive_else_balance_due_usd"]
        )
        us_treaty_label, us_treaty_amount = _refund_or_balance_due(
            us_results["payments"]["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"]
        )
        us_vanilla_label, us_vanilla_amount = _refund_or_balance_due(
            us_results["vanilla_checkpoint"]["refund_or_balance_due_usd"]
        )
        print(f"  U.S. base {us_base_label}: {us_base_amount} USD")
        print(f"  U.S. treaty {us_treaty_label}: {us_treaty_amount} USD")
        print(f"  U.S. vanilla checkpoint {us_vanilla_label}: {us_vanilla_amount} USD")
    print(f"  Outputs: {outputs_display}")


def run_year(
    project_root: Path,
    year: int | str,
    *,
    workspace_root: Path | None = None,
    prompt_if_config_missing: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> None:
    paths = resolve_year_paths(project_root, str(year), workspace_root=workspace_root)
    year_definition = get_year_definition(paths.year)
    ensure_year_scaffold(paths, prompt_if_config_missing=prompt_if_config_missing)

    # H1: surface the early high-level phases (manifest write, fact
    # extraction, structured-input verification) as their own stages so
    # the wizard's progress list shows progress before any rule module
    # starts executing. Pipelines/y2025/* modules emit their own stage
    # events further down.
    _emit_progress(
        progress_callback,
        {"event": "stage_started", "stage_id": "scaffold", "phase": "scaffold"},
    )
    write_manifest(paths.raw_root, paths.manifest_path, year=paths.year)
    _emit_progress(
        progress_callback,
        {"event": "stage_completed", "stage_id": "scaffold", "phase": "scaffold"},
    )

    _emit_progress(
        progress_callback,
        {"event": "stage_started", "stage_id": "extract_facts", "phase": "facts"},
    )
    extract_all_facts(paths)
    _emit_progress(
        progress_callback,
        {"event": "stage_completed", "stage_id": "extract_facts", "phase": "facts"},
    )

    _emit_progress(
        progress_callback,
        {
            "event": "stage_started",
            "stage_id": "analysis_inputs",
            "phase": "structured_inputs",
        },
    )
    analysis_inputs_directory(project_root, year, workspace_root=workspace_root)
    _emit_progress(
        progress_callback,
        {
            "event": "stage_completed",
            "stage_id": "analysis_inputs",
            "phase": "structured_inputs",
        },
    )
    enabled = _enabled_jurisdictions(paths)
    # Auto-derive Pub. 514 treaty dividend items from the per-row
    # income-cashflows facts so the user does not have to author the per-Posten
    # CSVs by hand. Idempotent — overwrites both files on each run from the
    # current facts. Authority: DBA-USA Art. 10/23 + IRS Pub. 514.
    # https://www.irs.gov/pub/irs-trty/germtech.pdf
    # https://www.irs.gov/publications/p514
    #
    # 26 U.S.C. § 6012 gate: when ``elections.us_filing_required`` is
    # false the household has no U.S. return to apply Pub. 514 against,
    # so deriving the per-Posten treaty dividend items would produce
    # outputs no rule will consume. Skip the derivation cleanly.
    # https://www.law.cornell.edu/uscode/text/26/6012
    if enabled["usa"]:
        from tax_pipeline.y2025.derive_treaty_dividend_items import (
            write_treaty_dividend_items_2025,
        )
        _emit_progress(
            progress_callback,
            {
                "event": "stage_started",
                "stage_id": "derive_treaty_dividend_items",
                "phase": "structured_inputs",
            },
        )
        de_path, us_path, item_count = write_treaty_dividend_items_2025(paths)
        print(f"Auto-derived {item_count} treaty dividend items → {de_path.name} + {us_path.name}")
        _emit_progress(
            progress_callback,
            {
                "event": "stage_completed",
                "stage_id": "derive_treaty_dividend_items",
                "phase": "structured_inputs",
            },
        )
    else:
        print("Skipping Pub. 514 treaty dividend item derivation (us_filing_required=false)")
    # Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): auto-derive a
    # foreign-financial-accounts stub CSV by scanning the extracted
    # facts index. Best-effort with documented gaps — balances stay
    # zero-placeholders until the user fills them in. Only meaningful
    # when the household has a U.S. filing obligation; the determination
    # rule is U.S.-side under § 6038D / 31 CFR § 1010.350.
    # https://www.law.cornell.edu/uscode/text/26/6038D
    # https://www.law.cornell.edu/cfr/text/31/1010.350
    if enabled["usa"]:
        from tax_pipeline.y2025.derive_foreign_financial_accounts import (
            write_foreign_financial_accounts_2025,
        )
        _emit_progress(
            progress_callback,
            {
                "event": "stage_started",
                "stage_id": "derive_foreign_financial_accounts",
                "phase": "structured_inputs",
            },
        )
        ffa_path, ffa_count = write_foreign_financial_accounts_2025(paths)
        print(f"Auto-derived {ffa_count} foreign-financial-account stub(s) → {ffa_path.name}")
        _emit_progress(
            progress_callback,
            {
                "event": "stage_completed",
                "stage_id": "derive_foreign_financial_accounts",
                "phase": "structured_inputs",
            },
        )
    # Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-country § 34c
    # / § 32d Abs. 5 EStG foreign-tax-credit breakdown for Anlage AUS.
    # Reads the already-derived treaty-dividend-items CSV plus the
    # 1099-div-detail.csv country attribution; aggregates by (country,
    # income_type) into a renderer-ready CSV. Only meaningful when the
    # household has a German return; the rendering happens in the
    # Germany pipeline and reconciles against the rule-graph aggregate.
    # https://www.gesetze-im-internet.de/estg/__34c.html
    # https://www.gesetze-im-internet.de/estg/__32d.html
    if enabled["germany"]:
        from tax_pipeline.y2025.derive_de_anlage_aus import (
            write_anlage_aus_by_country_2025,
        )
        _emit_progress(
            progress_callback,
            {
                "event": "stage_started",
                "stage_id": "derive_de_anlage_aus",
                "phase": "structured_inputs",
            },
        )
        aus_path, aus_count = write_anlage_aus_by_country_2025(paths)
        print(f"Auto-derived {aus_count} Anlage AUS country row(s) → {aus_path.name}")
        _emit_progress(
            progress_callback,
            {
                "event": "stage_completed",
                "stage_id": "derive_de_anlage_aus",
                "phase": "structured_inputs",
            },
        )
    clear_pipeline_context()

    env = os.environ.copy()
    env.update(
        {
            "TAX_PROJECT_ROOT": str(project_root),
            "TAX_YEAR": str(paths.year),
            "TAX_WORKSPACE_ROOT": str(paths.workspace_root),
            "TAX_USE_YEAR_LAYOUT": "1",
            "TAX_ANALYSIS_DIR": str(paths.analysis_root),
            "TAX_MANIFEST_PATH": str(paths.manifest_path),
        }
    )

    for module_name in _pipeline_modules_for_enabled(paths, year_definition):
        stage_id = _stage_id_for_module(module_name)
        _emit_progress(
            progress_callback,
            {
                "event": "stage_started",
                "stage_id": stage_id,
                "module": module_name,
                "phase": "rule_graph",
            },
        )
        _run_pipeline_module(module_name, env=env, cwd=project_root)
        _emit_progress(
            progress_callback,
            {
                "event": "stage_completed",
                "stage_id": stage_id,
                "module": module_name,
                "phase": "rule_graph",
            },
        )

    if year_definition.forms_supported:
        _emit_progress(
            progress_callback,
            {"event": "stage_started", "stage_id": "render_forms", "phase": "forms"},
        )
        try:
            if enabled["germany"]:
                ensure_required_paths(required_germany_form_paths(paths), label="Germany form inputs for 2025")
                ensure_required_paths(required_germany_legal_audit_paths(paths), label="Germany legal-audit inputs for 2025")
            if enabled["usa"]:
                ensure_required_paths(required_usa_form_paths(paths), label="U.S. form inputs for 2025")
                ensure_required_paths(required_usa_legal_audit_paths(paths), label="U.S. legal-audit inputs for 2025")
            if enabled["germany"]:
                render_germany_forms(paths)
                render_germany_legal_audit(paths)
                # Per-jurisdiction end-user filing walkthrough. Re-presents
                # the per-form Markdown in dependency order with explicit
                # cross-form transfer notes (Anlage → Mantelbogen). Pure
                # re-presentation: no Decimal arithmetic, no new
                # form_line_refs (CLAUDE.md invariants I3 / I5).
                render_germany_filing_guide(paths)
            if enabled["usa"]:
                render_usa_forms(paths)
                render_usa_legal_audit(paths)
                # 26 U.S.C. § 6012 (CLAUDE.md invariant I13): the U.S.
                # filing guide is gated on the U.S. pathway being
                # enabled. When ``elections.us_filing_required=false``
                # the orchestrator already skips the U.S. branch and
                # the guide is correctly absent.
                render_usa_filing_guide(paths)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"{exc} For a grouped checklist, run: python3 -m tax_pipeline.validate_workspace {paths.year}"
            ) from exc
        _emit_progress(
            progress_callback,
            {"event": "stage_completed", "stage_id": "render_forms", "phase": "forms"},
        )

    # F4 (W1.B / T2.1) — year-boundary carryforward export. The capital-
    # loss carryforward (26 U.S.C. § 1212 / § 20 Abs. 6 EStG) and the
    # private-sale-loss carryforward (§ 23 Abs. 3 Sätze 7-9 EStG) are the
    # only legal-graph outputs that MUST survive to the next year. Surface
    # them in the loader-side CSV shape under ``outputs/`` so the next
    # year's normalized/facts/*.csv can be auto-seeded instead of hand-
    # extracted from the prior-year Bescheid PDF / 1040. See
    # ``tax_pipeline/y2025/carryforward_export.py`` for the per-row
    # authority citations.
    # https://www.gesetze-im-internet.de/estg/__20.html
    # https://www.gesetze-im-internet.de/estg/__23.html
    # https://www.law.cornell.edu/uscode/text/26/1212
    _emit_progress(
        progress_callback,
        {"event": "stage_started", "stage_id": "export_carryforwards", "phase": "carryforward_export"},
    )
    # F4 (W1.B / T2.1) — robust to incomplete/mocked pipeline output:
    # when the legal-output JSON is missing or malformed (e.g., a test
    # harness stubbed the upstream scripts so the file was never
    # produced), skip the carryforward export rather than failing the
    # whole run. The export is a downstream convenience, not a legal
    # requirement; the rule graph has already finished.
    try:
        final_output_for_export = load_final_legal_output_2025(paths)
    except (FileNotFoundError, ValueError) as exc:
        print(
            f"Skipping carryforward export — final-legal-output JSON "
            f"unavailable ({exc.__class__.__name__})."
        )
    else:
        carryforward_report = export_carryforwards_2025(paths, final_output_for_export)
        for country, info in carryforward_report.items():
            if info["path"] is not None:
                print(
                    f"Auto-exported {info['rows']} {country} carryforward row(s) → "
                    f"{info['path'].name}"
                )
    _emit_progress(
        progress_callback,
        {"event": "stage_completed", "stage_id": "export_carryforwards", "phase": "carryforward_export"},
    )

    print_headline_summary(paths)
    # Keep the current analysis surface intact unless the full pipeline succeeded.
    remove_obsolete_analysis_outputs(paths.analysis_root)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("year", nargs="?", default="2025")
    parser.add_argument("--workspace")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    project_root = Path(__file__).resolve().parent.parent
    workspace_root = Path(args.workspace) if args.workspace else None
    run_year(project_root, args.year, workspace_root=workspace_root, prompt_if_config_missing=True)


if __name__ == "__main__":
    main()
