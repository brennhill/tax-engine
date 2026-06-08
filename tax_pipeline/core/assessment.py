from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tax_pipeline.core.facts import (
    CanonicalFact,
    IgnoredFact,
    UnsupportedFact,
    assert_facts_ready_for_legal_stages,
    stable_fingerprint,
)
from tax_pipeline.core.stages import StageDiagnostic, StageGraphValidation, StageResult


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _require_mapping(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return {_require_text(f"{name}.key", key): item for key, item in value.items()}


@dataclass(frozen=True)
class CountryAssessment:
    country_or_scope: str
    stage_results: Sequence[StageResult]
    totals: Mapping[str, Any]
    diagnostics: Sequence[StageDiagnostic] = ()
    precision_notes: Mapping[str, str] = field(default_factory=dict)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "country_or_scope",
            _require_text("CountryAssessment.country_or_scope", self.country_or_scope),
        )
        stage_results = tuple(self.stage_results)
        for result in stage_results:
            if not isinstance(result, StageResult):
                raise ValueError("CountryAssessment.stage_results must contain StageResult instances")
        diagnostics = tuple(self.diagnostics)
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, StageDiagnostic):
                raise ValueError("CountryAssessment.diagnostics must contain StageDiagnostic instances")
        precision_notes = _require_mapping("CountryAssessment.precision_notes", self.precision_notes)
        for key, value in precision_notes.items():
            precision_notes[key] = _require_text(f"CountryAssessment.precision_notes[{key}]", value)
        object.__setattr__(self, "stage_results", stage_results)
        object.__setattr__(self, "totals", _require_mapping("CountryAssessment.totals", self.totals))
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "precision_notes", precision_notes)
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    "country_or_scope": self.country_or_scope,
                    "stage_results": tuple(result.fingerprint for result in self.stage_results),
                    "totals": self.totals,
                    "diagnostics": self.diagnostics,
                    "precision_notes": self.precision_notes,
                }
            ),
        )


@dataclass(frozen=True)
class TreatyAssessment:
    treaty_id: str
    stage_results: Sequence[StageResult]
    outputs: Mapping[str, Any]
    diagnostics: Sequence[StageDiagnostic] = ()
    precision_notes: Mapping[str, str] = field(default_factory=dict)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "treaty_id", _require_text("TreatyAssessment.treaty_id", self.treaty_id))
        stage_results = tuple(self.stage_results)
        for result in stage_results:
            if not isinstance(result, StageResult):
                raise ValueError("TreatyAssessment.stage_results must contain StageResult instances")
        diagnostics = tuple(self.diagnostics)
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, StageDiagnostic):
                raise ValueError("TreatyAssessment.diagnostics must contain StageDiagnostic instances")
        precision_notes = _require_mapping("TreatyAssessment.precision_notes", self.precision_notes)
        for key, value in precision_notes.items():
            precision_notes[key] = _require_text(f"TreatyAssessment.precision_notes[{key}]", value)
        object.__setattr__(self, "stage_results", stage_results)
        object.__setattr__(self, "outputs", _require_mapping("TreatyAssessment.outputs", self.outputs))
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "precision_notes", precision_notes)
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    "treaty_id": self.treaty_id,
                    "stage_results": tuple(result.fingerprint for result in self.stage_results),
                    "outputs": self.outputs,
                    "diagnostics": self.diagnostics,
                    "precision_notes": self.precision_notes,
                }
            ),
        )


@dataclass(frozen=True)
class RenderProjection:
    fields: Mapping[str, Any]
    source_output_fingerprints: Mapping[str, str]
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        fields = _require_mapping("RenderProjection.fields", self.fields)
        source_output_fingerprints = _require_mapping(
            "RenderProjection.source_output_fingerprints",
            self.source_output_fingerprints,
        )
        for key, value in source_output_fingerprints.items():
            source_output_fingerprints[key] = _require_text(
                f"RenderProjection.source_output_fingerprints[{key}]",
                value,
            )
        object.__setattr__(self, "fields", fields)
        missing_source_fingerprints = set(fields) - set(source_output_fingerprints)
        if missing_source_fingerprints:
            raise ValueError(
                f"RenderProjection.source_output_fingerprints missing: {sorted(missing_source_fingerprints)}"
            )
        object.__setattr__(self, "source_output_fingerprints", source_output_fingerprints)
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    "fields": self.fields,
                    "source_output_fingerprints": self.source_output_fingerprints,
                }
            ),
        )


@dataclass(frozen=True)
class AssessmentPackage:
    tax_year: int
    canonical_facts: Sequence[CanonicalFact]
    germany_assessment: CountryAssessment | None
    us_assessment: CountryAssessment | None
    treaty_assessment: TreatyAssessment | None
    diagnostics: Sequence[StageDiagnostic]
    audit_graph: StageGraphValidation
    render_projection: RenderProjection
    ignored_facts: Sequence[IgnoredFact] = ()
    unsupported_facts: Sequence[UnsupportedFact] = ()
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.tax_year, int) or self.tax_year < 1900:
            raise ValueError("AssessmentPackage.tax_year must be a valid year")
        canonical_facts = tuple(self.canonical_facts)
        ignored_facts = tuple(self.ignored_facts)
        unsupported_facts = tuple(self.unsupported_facts)
        if unsupported_facts:
            raise ValueError("AssessmentPackage cannot be built with unsupported facts")
        assert_facts_ready_for_legal_stages((*canonical_facts, *ignored_facts, *unsupported_facts))
        for fact in canonical_facts:
            if not isinstance(fact, CanonicalFact):
                raise ValueError("AssessmentPackage.canonical_facts must contain CanonicalFact instances")
        for fact in ignored_facts:
            if not isinstance(fact, IgnoredFact):
                raise ValueError("AssessmentPackage.ignored_facts must contain IgnoredFact instances")
        for fact in unsupported_facts:
            if not isinstance(fact, UnsupportedFact):
                raise ValueError("AssessmentPackage.unsupported_facts must contain UnsupportedFact instances")
        diagnostics = tuple(self.diagnostics)
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, StageDiagnostic):
                raise ValueError("AssessmentPackage.diagnostics must contain StageDiagnostic instances")
        if not isinstance(self.audit_graph, StageGraphValidation):
            raise ValueError("AssessmentPackage.audit_graph must be a StageGraphValidation")
        if not isinstance(self.render_projection, RenderProjection):
            raise ValueError("AssessmentPackage.render_projection must be a RenderProjection")
        untracked_render_fields = set(self.render_projection.fields) - set(self.audit_graph.output_keys)
        if untracked_render_fields:
            raise ValueError(
                f"render fields must come from legal stage outputs: {sorted(untracked_render_fields)}"
            )
        object.__setattr__(self, "canonical_facts", canonical_facts)
        object.__setattr__(self, "ignored_facts", ignored_facts)
        object.__setattr__(self, "unsupported_facts", unsupported_facts)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    "tax_year": self.tax_year,
                    "canonical_facts": tuple(fact.fingerprint for fact in self.canonical_facts),
                    "germany_assessment": self.germany_assessment.fingerprint
                    if self.germany_assessment
                    else None,
                    "us_assessment": self.us_assessment.fingerprint if self.us_assessment else None,
                    "treaty_assessment": self.treaty_assessment.fingerprint
                    if self.treaty_assessment
                    else None,
                    "diagnostics": self.diagnostics,
                    "audit_graph": self.audit_graph,
                    "render_projection": self.render_projection.fingerprint,
                    "ignored_facts": tuple(fact.fingerprint for fact in self.ignored_facts),
                    "unsupported_facts": tuple(fact.fingerprint for fact in self.unsupported_facts),
                }
            ),
        )


__all__ = [
    "AssessmentPackage",
    "CountryAssessment",
    "RenderProjection",
    "TreatyAssessment",
]
