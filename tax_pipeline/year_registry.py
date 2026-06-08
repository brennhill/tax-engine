from __future__ import annotations

from dataclasses import dataclass, field

from tax_pipeline.jurisdictions import (
    JURISDICTION_REGISTRY,
    get_jurisdiction_by_posture_key,
)
from tax_pipeline.postures import get_posture_definition, known_postures


@dataclass(frozen=True)
class YearDefinition:
    """Per-year orchestration manifest — Proposal 2 jurisdiction-keyed shape.

    Pre-P2 the manifest carried named slots ``germany_modules`` /
    ``usa_modules`` / ``germany_optional_modules`` / ``supported_postures``
    keyed on the literal strings ``"germany"`` / ``"usa"``. P2 collapses
    those into ``jurisdiction_modules`` and ``jurisdiction_optional_modules``
    keyed by ISO-2 jurisdiction code (matching
    :data:`tax_pipeline.jurisdictions.JURISDICTION_REGISTRY`). The legacy
    named-slot accessors remain as ``@property`` views over the dict so
    historic call sites continue to function while the migration completes.

    Pipeline 1 (Derivation) modules run BEFORE every Pipeline 2 (Legal)
    module so derived facts are persisted to ``derived-facts.json`` before
    any legal interpretation runs (WS-5H invariant migration plan §1.5).
    Stage IDs in derivation modules are prefixed ``DERIVE-``.
    """

    year: int
    derivation_modules: tuple[str, ...]
    # Per-jurisdiction main rule-graph orchestrator modules, keyed by
    # ISO-2 code ("DE", "US"). Order within each tuple is significant
    # for ``pipeline_modules``.
    jurisdiction_modules: dict[str, tuple[str, ...]]
    # Per-jurisdiction optional modules, keyed by ISO-2 code, then by
    # capability key ("crypto", "equity_comp_capital"). Optional modules
    # gate on workspace-config knobs in
    # ``run_year._pipeline_modules_for_enabled``.
    jurisdiction_optional_modules: dict[str, dict[str, str]]
    report_modules: tuple[str, ...]
    forms_supported: bool
    legal_audit_supported: bool
    supported_postures: dict[str, tuple[str, ...]]

    @property
    def jurisdictions(self) -> tuple[str, ...]:
        """ISO-2 codes for which this year carries rule modules.

        Stable order matches ``jurisdiction_modules.keys()`` insertion
        order (mirrors :func:`jurisdictions.iter_jurisdictions`).
        """
        return tuple(self.jurisdiction_modules.keys())

    # ---- Backward-compatible named-slot accessors --------------------
    # These properties let pre-P2 callers (run_year.py, tests) continue
    # to address modules by jurisdiction name while the registry rewrite
    # propagates outward. Once every consumer reads from
    # ``jurisdiction_modules`` directly these can be removed.

    @property
    def germany_modules(self) -> tuple[str, ...]:
        return self.jurisdiction_modules.get("DE", ())

    @property
    def usa_modules(self) -> tuple[str, ...]:
        return self.jurisdiction_modules.get("US", ())

    @property
    def germany_optional_modules(self) -> dict[str, str]:
        return self.jurisdiction_optional_modules.get("DE", {})

    @property
    def pipeline_modules(self) -> tuple[str, ...]:
        # Optional Germany modules retain their pre-P2 ordering: crypto
        # then equity_comp_capital, prepended before the main DE pipeline.
        de_optional = self.jurisdiction_optional_modules.get("DE", {})
        ordered_optional = tuple(
            de_optional[key] for key in ("crypto", "equity_comp_capital") if key in de_optional
        )
        return (
            self.derivation_modules
            + ordered_optional
            + self.jurisdiction_modules.get("DE", ())
            + self.jurisdiction_modules.get("US", ())
            + self.report_modules
        )


def _supported_postures_from_registry() -> dict[str, tuple[str, ...]]:
    """Build the ``supported_postures`` mapping from the jurisdiction registry.

    For each jurisdiction, list the posture filing keys whose posture
    definition reports ``output_support.forms`` (Germany) or every
    known posture (U.S. — historic shape; the U.S. side has no
    forms-gate today).
    """
    result: dict[str, tuple[str, ...]] = {}
    for definition in JURISDICTION_REGISTRY.values():
        registry_key = definition.posture_registry_key
        postures = known_postures(registry_key)
        # Match the pre-P2 shape: Germany filters to forms=True, U.S.
        # exposes every known posture.
        if definition.code == "DE":
            filtered = tuple(
                posture
                for posture in postures
                if get_posture_definition(registry_key, posture).output_support.forms
            )
        else:
            filtered = tuple(postures)
        result[registry_key] = filtered
    return result


YEAR_2025 = YearDefinition(
    year=2025,
    derivation_modules=(
        "tax_pipeline.pipelines.y2025.run_derivation",
    ),
    jurisdiction_modules={
        "DE": (
            "tax_pipeline.pipelines.y2025.germany_model",
            "tax_pipeline.pipelines.y2025.germany_elster_entry_sheet",
        ),
        "US": (
            "tax_pipeline.pipelines.y2025.us_capital_workpaper",
            "tax_pipeline.pipelines.y2025.us_model",
            "tax_pipeline.pipelines.y2025.us_treaty_packet",
        ),
    },
    jurisdiction_optional_modules={
        "DE": {
            "crypto": "tax_pipeline.pipelines.y2025.coinbase_private_sales",
            "equity_comp_capital": "tax_pipeline.pipelines.y2025.dher_german",
        },
    },
    report_modules=(
        "tax_pipeline.pipelines.y2025.final_legal_output",
        "tax_pipeline.pipelines.y2025.rule_narratives",
        "tax_pipeline.pipelines.y2025.bilingual_summary",
        "tax_pipeline.pipelines.y2025.verbose_report",
    ),
    forms_supported=True,
    legal_audit_supported=True,
    supported_postures=_supported_postures_from_registry(),
)


def get_year_definition(year: int) -> YearDefinition:
    if year == 2025:
        return YEAR_2025
    raise NotImplementedError("Only 2025 has an implemented tax engine at the moment.")
