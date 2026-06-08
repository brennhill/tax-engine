"""Pure tax assessment core contracts."""

from tax_pipeline.core.assessment import (
    AssessmentPackage,
    CountryAssessment,
    RenderProjection,
    TreatyAssessment,
)
from tax_pipeline.core.facts import (
    CanonicalFact,
    FactKey,
    FactProvenance,
    IgnoredFact,
    UnsupportedFact,
    assert_facts_ready_for_legal_stages,
)
from tax_pipeline.core.legal_value import (
    LegalValue,
    require_legal_value,
)
from tax_pipeline.core.stages import (
    LawRule,
    LawStage,
    RuleGraphExecution,
    StageAuditRow,
    StageDiagnostic,
    StageGraphValidation,
    StageResult,
    execute_rule_graph,
    stage_audit_rows,
    validate_law_stage_graph,
)

__all__ = [
    "AssessmentPackage",
    "CanonicalFact",
    "CountryAssessment",
    "FactKey",
    "FactProvenance",
    "IgnoredFact",
    "LawRule",
    "LawStage",
    "LegalValue",
    "RenderProjection",
    "RuleGraphExecution",
    "StageAuditRow",
    "StageDiagnostic",
    "StageGraphValidation",
    "StageResult",
    "TreatyAssessment",
    "UnsupportedFact",
    "assert_facts_ready_for_legal_stages",
    "execute_rule_graph",
    "require_legal_value",
    "stage_audit_rows",
    "validate_law_stage_graph",
]
