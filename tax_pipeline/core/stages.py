from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.legal_value import LegalValue
from tax_pipeline.core.stage_id import StageId


class AuditWaypoint(Enum):
    """Closed enum classifying outputs that are deliberately not on a form
    line.

    Every ``OutputDeclaration`` must declare at least one form_line_ref OR
    at least one audit_waypoint. The closed-enum form prevents authors
    from leaving an output unaccounted for under a vague "this isn't on a
    form" comment: each non-line output picks a category from this set, so
    a reviewer can group, count, and audit them.

    Adding a value here is a deliberate code change that humans review. A
    typo in a stage declaration cannot silently introduce a new
    classification.
    """

    # A computed value that participates in the math but is never written
    # on a form (e.g. ``total_taxable_before_allowance``,
    # ``combined_current_capital``, intermediate QDCGTW lines).
    INTERMEDIATE_MATH = "intermediate_math"

    # A per-Posten value that aggregates upward to a form-line entry
    # (e.g. per-symbol foreign tax under § 32d Abs. 5 EStG).
    PER_POSTEN_AGGREGATION = "per_posten_aggregation"

    # A reconciliation invariant whose only purpose is forcing two
    # independently computed totals to agree (e.g. the foreign-tax total
    # cross-check between ``foreign_tax_1099_eur`` and the bank-certificate
    # totals).
    RECONCILIATION_INVARIANT = "reconciliation_invariant"

    # A diagnostic / cross-check value that does not affect the legal
    # outcome but is exported for audit transparency (e.g. the vanilla
    # checkpoint totals, with-vs-without Teilfreistellung comparisons).
    DIAGNOSTIC_CROSS_CHECK = "diagnostic_cross_check"

    # A SHA-256 fingerprint over inputs whose only purpose is audit-trail
    # integrity.
    AUDIT_FINGERPRINT = "audit_fingerprint"


@dataclass(frozen=True)
class FormLineRef:
    """A typed citation of a single form line.

    Replaces parallel ``form_line_refs`` / ``form_line_urls`` string
    tuples with an explicit ``(form, line, url)`` triple. The url is
    optional because a small number of forms have no canonical anchor
    URL (e.g. ELSTER eingabemasken without dedicated help pages).
    """

    form: str
    line: str
    url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "form", _require_text("FormLineRef.form", self.form))
        object.__setattr__(self, "line", _require_text("FormLineRef.line", self.line))
        # url is allowed to be the empty string (no canonical link) but
        # cannot be ``None`` — the schema is tuple[str, ...] downstream.
        object.__setattr__(self, "url", str(self.url))

    def render(self) -> str:
        """Render to the legacy ``"<form> <line>"`` string used by the
        derived ``LawStage.form_line_refs`` field. Concatenated with a
        single space; if the line text already begins with a separator
        (``—``, ``-``, ``:``) the legacy string preserves that prefix
        verbatim.
        """
        return f"{self.form} {self.line}"


@dataclass(frozen=True)
class OutputDeclaration:
    """Per-output classification of where the value appears.

    Every output must declare at least one form_line_ref OR at least one
    audit_waypoint. An empty/unclassified output is rejected at LawStage
    construction time so authors cannot accidentally leave a value
    unaccounted for.
    """

    key: str
    form_line_refs: tuple[FormLineRef, ...] = ()
    audit_waypoints: frozenset[AuditWaypoint] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _require_text("OutputDeclaration.key", self.key))
        form_line_refs = tuple(self.form_line_refs)
        for ref in form_line_refs:
            if not isinstance(ref, FormLineRef):
                raise ValueError(
                    f"OutputDeclaration.form_line_refs[{self.key}] entries must be FormLineRef instances"
                )
        object.__setattr__(self, "form_line_refs", form_line_refs)
        # Coerce iterable input to frozenset and validate every member is
        # an AuditWaypoint enum value (not a bare string).
        try:
            audit_waypoints = frozenset(self.audit_waypoints)
        except TypeError as exc:
            raise ValueError(
                f"OutputDeclaration.audit_waypoints[{self.key}] must be iterable of AuditWaypoint"
            ) from exc
        for member in audit_waypoints:
            if not isinstance(member, AuditWaypoint):
                raise ValueError(
                    f"OutputDeclaration.audit_waypoints[{self.key}] entries must be AuditWaypoint members; got {member!r}"
                )
        object.__setattr__(self, "audit_waypoints", audit_waypoints)
        if not form_line_refs and not audit_waypoints:
            raise ValueError(
                f"OutputDeclaration[{self.key}] must declare at least one form_line_refs entry "
                "or at least one audit_waypoints entry; outputs cannot be unclassified."
            )


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _require_tuple(name: str, values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(_require_text(f"{name}[]", value) for value in values)
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _require_mapping(name: str, value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} is required")
    result: dict[str, Any] = {}
    for key, item in value.items():
        result[_require_text(f"{name}.key", key)] = item
    return result


@dataclass(frozen=True)
class StageDiagnostic:
    severity: str
    code: str
    message: str
    related_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", _require_text("StageDiagnostic.severity", self.severity))
        object.__setattr__(self, "code", _require_text("StageDiagnostic.code", self.code))
        object.__setattr__(self, "message", _require_text("StageDiagnostic.message", self.message))
        if self.related_key is not None:
            object.__setattr__(
                self,
                "related_key",
                _require_text("StageDiagnostic.related_key", self.related_key),
            )


@dataclass(frozen=True)
class StageResult:
    # P9: ``stage_id`` carries the legacy literal string form
    # (``"DE25-13F-VORABPAUSCHALE"``) so JSON renderers, fingerprint
    # payloads, and the 200+ call sites that read ``result.stage_id``
    # as a string keep working. The constructor accepts either a
    # :class:`StageId` typed triple or the legacy string and validates
    # via ``StageId.coerce`` so a malformed stage_id fails closed at
    # construction. The typed view is available via
    # :attr:`stage_id_typed` for code that wants to introspect the
    # ``(country, year_short, sequence)`` triple.
    stage_id: str
    outputs: Mapping[str, Any]
    input_values: Mapping[str, Any]
    input_fingerprints: Mapping[str, str]
    output_fingerprints: Mapping[str, str]
    diagnostics: Sequence[StageDiagnostic]
    precision_notes: Mapping[str, str]
    fingerprint: str = field(init=False)

    @property
    def stage_id_typed(self) -> StageId:
        """Typed view of :attr:`stage_id` as a ``(country, year_short,
        sequence)`` :class:`StageId` triple. The parse is cheap (regex
        match on a known-good string); call sites that need the typed
        view should prefer this over re-parsing the string themselves.
        """
        return StageId.parse(self.stage_id)

    def __post_init__(self) -> None:
        # Validate via StageId.coerce — accepts either a typed StageId
        # or a literal string, parses, then stores the canonical string
        # form. A malformed stage_id raises here.
        coerced = StageId.coerce(self.stage_id)
        object.__setattr__(self, "stage_id", str(coerced))
        outputs = _require_mapping("StageResult.outputs", self.outputs)
        input_values = _require_mapping("StageResult.input_values", self.input_values)
        input_fingerprints = _require_mapping("StageResult.input_fingerprints", self.input_fingerprints)
        output_fingerprints = _require_mapping("StageResult.output_fingerprints", self.output_fingerprints)
        precision_notes = _require_mapping("StageResult.precision_notes", self.precision_notes)
        for key, value in input_fingerprints.items():
            input_fingerprints[key] = _require_text(f"StageResult.input_fingerprints[{key}]", value)
        for key, value in output_fingerprints.items():
            output_fingerprints[key] = _require_text(f"StageResult.output_fingerprints[{key}]", value)
        for key, value in precision_notes.items():
            precision_notes[key] = _require_text(f"StageResult.precision_notes[{key}]", value)
        output_keys = set(outputs)
        if set(input_values) != set(input_fingerprints):
            raise ValueError("StageResult.input_values must match input_fingerprints")
        if set(output_fingerprints) != output_keys:
            raise ValueError("StageResult.output_fingerprints must match outputs")
        missing_precision_notes = output_keys - set(precision_notes)
        if missing_precision_notes:
            raise ValueError(f"StageResult.precision_notes missing: {sorted(missing_precision_notes)}")
        diagnostics = tuple(self.diagnostics)
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, StageDiagnostic):
                raise ValueError("StageResult.diagnostics must contain StageDiagnostic instances")
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "input_values", input_values)
        object.__setattr__(self, "input_fingerprints", input_fingerprints)
        object.__setattr__(self, "output_fingerprints", output_fingerprints)
        object.__setattr__(self, "precision_notes", precision_notes)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    # ``stage_id`` is the literal string form (P9
                    # validates via StageId.coerce in __post_init__);
                    # the SHA-256 payload remains byte-identical to the
                    # pre-P9 fingerprint (invariant I6).
                    "stage_id": self.stage_id,
                    "outputs": self.outputs,
                    "input_values": self.input_values,
                    "input_fingerprints": self.input_fingerprints,
                    "output_fingerprints": self.output_fingerprints,
                    "diagnostics": self.diagnostics,
                    "precision_notes": self.precision_notes,
                }
            ),
        )


@dataclass(frozen=True)
class LawStage:
    # P9: ``stage_id`` carries the legacy literal string form
    # (``"DE25-13F-VORABPAUSCHALE"``) so fingerprint payloads
    # (invariant I6), JSON renderers, narrative-template lookups, and
    # the 200+ call sites that read ``stage.stage_id`` as a string keep
    # working byte-identical to the pre-P9 contract. The constructor
    # accepts either a :class:`StageId` typed triple or the legacy
    # string and validates via ``StageId.coerce`` so a malformed
    # stage_id fails closed at construction. The typed view is
    # available via :attr:`stage_id_typed` for code that wants to
    # introspect the ``(country, year_short, sequence)`` triple.
    stage_id: str
    country_or_scope: str
    legal_refs: Sequence[str]
    authority_urls: Sequence[str]
    input_fact_keys: Sequence[str]
    rounding_policy: str
    law_order_note: str
    legal_formula: str
    narrative_templates: Mapping[str, str]
    # Stages declare their outputs via per-output ``OutputDeclaration`` —
    # each declaration carries its own ``FormLineRef`` provenance and a
    # closed ``AuditWaypoint`` enum classification for non-form-line
    # outputs. ``__post_init__`` derives the read-only convenience
    # attributes ``output_keys`` / ``form_line_refs`` / ``form_line_urls``
    # so the rest of the engine (graph builder, narrative builder,
    # fingerprint) keeps reading a flat surface; those are not constructor
    # parameters.
    outputs: tuple[OutputDeclaration, ...] = ()
    output_keys: tuple[str, ...] = field(init=False)
    form_line_refs: tuple[str, ...] = field(init=False)
    form_line_urls: tuple[str, ...] = field(init=False)
    fingerprint: str = field(init=False)

    @property
    def stage_id_typed(self) -> StageId:
        """Typed view of :attr:`stage_id` as a ``(country, year_short,
        sequence)`` :class:`StageId` triple. Useful for code that needs
        to dispatch on the country (e.g. ``"DE"`` vs. ``"US"``) without
        re-parsing the literal string.
        """
        return StageId.parse(self.stage_id)

    def __post_init__(self) -> None:
        # Validate the stage_id via the typed StageId parser so a
        # malformed identifier raises here. We store the canonical
        # string form (``str(StageId(...))``) so fingerprint payloads
        # and the 200+ ``stage.stage_id``-as-string readers see a
        # byte-identical value to the pre-P9 contract.
        coerced = StageId.coerce(self.stage_id)
        object.__setattr__(self, "stage_id", str(coerced))
        object.__setattr__(
            self,
            "country_or_scope",
            _require_text("LawStage.country_or_scope", self.country_or_scope),
        )
        object.__setattr__(self, "legal_refs", _require_tuple("LawStage.legal_refs", self.legal_refs))
        object.__setattr__(
            self,
            "authority_urls",
            _require_tuple("LawStage.authority_urls", self.authority_urls),
        )
        object.__setattr__(
            self,
            "input_fact_keys",
            _require_tuple("LawStage.input_fact_keys", self.input_fact_keys),
        )
        if len(set(self.input_fact_keys)) != len(self.input_fact_keys):
            raise ValueError("LawStage.input_fact_keys contains duplicates")
        outputs_tuple = tuple(self.outputs)
        if not outputs_tuple:
            raise ValueError(
                "LawStage.outputs is required; declare each output with "
                "OutputDeclaration(key=..., form_line_refs=..., audit_waypoints=...)."
            )
        for decl in outputs_tuple:
            if not isinstance(decl, OutputDeclaration):
                raise ValueError(
                    "LawStage.outputs entries must be OutputDeclaration instances"
                )
        keys = tuple(decl.key for decl in outputs_tuple)
        if len(set(keys)) != len(keys):
            raise ValueError("LawStage.outputs declares duplicate keys")
        # Derived convenience fields. Form-line refs follow declaration
        # order across outputs; URLs are parallel. Downstream code that
        # iterates form_line_refs continues to work unchanged.
        derived_refs: list[str] = []
        derived_urls: list[str] = []
        for decl in outputs_tuple:
            for ref in decl.form_line_refs:
                derived_refs.append(ref.render())
                derived_urls.append(ref.url)
        object.__setattr__(self, "outputs", outputs_tuple)
        object.__setattr__(self, "output_keys", keys)
        object.__setattr__(self, "form_line_refs", tuple(derived_refs))
        object.__setattr__(self, "form_line_urls", tuple(derived_urls))
        object.__setattr__(
            self,
            "rounding_policy",
            _require_text("LawStage.rounding_policy", self.rounding_policy),
        )
        object.__setattr__(
            self,
            "law_order_note",
            _require_text("LawStage.law_order_note", self.law_order_note),
        )
        # legal_formula must describe the actual legal formula or decision applied
        # (ENGINE-SPEC.md: "Math Steps"). The auto-generated input-key concatenation
        # used historically by the renderer is rejected at the schema level so the
        # math-step formula in the audit packet cannot drift back into key noise.
        formula = _require_text("LawStage.legal_formula", self.legal_formula)
        auto_generated = (
            " + ".join(self.input_fact_keys) + " -> " + " + ".join(self.output_keys)
        )
        if formula == auto_generated:
            raise ValueError(
                "LawStage.legal_formula must describe the actual legal formula, "
                "not the auto-generated input-key concatenation"
            )
        object.__setattr__(self, "legal_formula", formula)
        narrative_templates = _require_mapping("LawStage.narrative_templates", self.narrative_templates)
        for key, value in narrative_templates.items():
            narrative_templates[key] = _require_text(f"LawStage.narrative_templates[{key}]", str(value))
            if narrative_templates[key] != self.stage_id:
                raise ValueError("LawStage.narrative_templates must map every language to stage_id")
        object.__setattr__(self, "narrative_templates", narrative_templates)
        # form_line_refs / form_line_urls were already set above in the mode
        # branch. The fingerprint reads them from self regardless of mode so
        # a stage migrated to the new shape produces the same fingerprint as
        # the equivalent legacy stage (audit packets stay stable across the
        # rule-graph migration).
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    # ``stage_id`` is the literal string form (P9
                    # validates via StageId.coerce in __post_init__);
                    # the SHA-256 payload remains byte-identical to the
                    # pre-P9 fingerprint (invariant I6).
                    "stage_id": self.stage_id,
                    "country_or_scope": self.country_or_scope,
                    "legal_refs": self.legal_refs,
                    "authority_urls": self.authority_urls,
                    "input_fact_keys": self.input_fact_keys,
                    "output_keys": self.output_keys,
                    "rounding_policy": self.rounding_policy,
                    "law_order_note": self.law_order_note,
                    "legal_formula": self.legal_formula,
                    "narrative_templates": self.narrative_templates,
                    "form_line_refs": self.form_line_refs,
                    "form_line_urls": self.form_line_urls,
                }
            ),
        )

    def validate_result(self, result: StageResult) -> None:
        if result.stage_id != self.stage_id:
            raise ValueError(f"StageResult {result.stage_id} does not belong to {self.stage_id}")
        declared_outputs = set(self.output_keys)
        actual_outputs = set(result.outputs)
        extra_outputs = actual_outputs - declared_outputs
        if extra_outputs:
            raise ValueError(f"{self.stage_id} produced untracked output: {sorted(extra_outputs)}")
        missing_outputs = declared_outputs - actual_outputs
        if missing_outputs:
            raise ValueError(f"{self.stage_id} missing declared output: {sorted(missing_outputs)}")
        missing_input_fingerprints = set(self.input_fact_keys) - set(result.input_fingerprints)
        if missing_input_fingerprints:
            raise ValueError(f"{self.stage_id} missing input fingerprint: {sorted(missing_input_fingerprints)}")
        missing_input_values = set(self.input_fact_keys) - set(result.input_values)
        if missing_input_values:
            raise ValueError(f"{self.stage_id} missing input values: {sorted(missing_input_values)}")
        if set(result.input_values) != set(result.input_fingerprints):
            raise ValueError(f"{self.stage_id} input values must match input fingerprints")
        if set(result.output_fingerprints) != declared_outputs:
            raise ValueError(f"{self.stage_id} output fingerprints must match declared outputs")
        missing_precision_notes = declared_outputs - set(result.precision_notes)
        if missing_precision_notes:
            raise ValueError(f"{self.stage_id} missing precision notes: {sorted(missing_precision_notes)}")


@dataclass(frozen=True)
class LawRule:
    stage: LawStage
    implementation_ref: str
    calculate: Callable[[Mapping[str, Any]], Mapping[str, Any]]

    def __post_init__(self) -> None:
        if not isinstance(self.stage, LawStage):
            raise ValueError("LawRule.stage must be a LawStage")
        object.__setattr__(
            self,
            "implementation_ref",
            _require_text("LawRule.implementation_ref", self.implementation_ref),
        )
        if not callable(self.calculate):
            raise ValueError("LawRule.calculate must be callable")

    @property
    def rule_id(self) -> str:
        return self.stage.stage_id


@dataclass(frozen=True)
class StageGraphValidation:
    stage_ids: tuple[str, ...]
    initial_fact_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    final_available_keys: tuple[str, ...]


@dataclass(frozen=True)
class StageAuditRow:
    stage_id: str
    country_or_scope: str
    legal_refs: tuple[str, ...]
    authority_urls: tuple[str, ...]
    input_fact_keys: tuple[str, ...]
    output_keys: tuple[str, ...]
    rounding_policy: str
    law_order_note: str
    narrative_templates: Mapping[str, str]
    form_line_refs: tuple[str, ...]
    form_line_urls: tuple[str, ...] = ()
    result_fingerprint: str | None = None
    precision_notes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RuleGraphExecution:
    rules: Sequence[LawRule]
    initial_facts: Mapping[str, Any]
    final_facts: Mapping[str, Any]
    stage_results: Sequence[StageResult]
    validation: StageGraphValidation

    def __post_init__(self) -> None:
        rules = tuple(self.rules)
        if not rules:
            raise ValueError("RuleGraphExecution.rules is required")
        for rule in rules:
            if not isinstance(rule, LawRule):
                raise ValueError("RuleGraphExecution.rules must contain LawRule instances")
        stage_results = tuple(self.stage_results)
        for result in stage_results:
            if not isinstance(result, StageResult):
                raise ValueError("RuleGraphExecution.stage_results must contain StageResult instances")
        if not isinstance(self.validation, StageGraphValidation):
            raise ValueError("RuleGraphExecution.validation must be a StageGraphValidation")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(self, "initial_facts", dict(self.initial_facts))
        object.__setattr__(self, "final_facts", dict(self.final_facts))
        object.__setattr__(self, "stage_results", stage_results)

    @property
    def legal_outputs(self) -> Mapping[str, LegalValue]:
        """Form-bound rule outputs wrapped in :class:`LegalValue` envelopes
        (invariant I11).

        For every executed ``StageResult`` whose output value is a
        ``Decimal``, expose a ``LegalValue(amount, stage_id, output_key,
        fingerprint)`` carrying the stage_id, the declared output_key,
        and the executor's existing
        ``StageResult.output_fingerprints[output_key]`` digest. Non-Decimal
        outputs (dataclass aggregates, lists, mapping rows used for
        per-Posten projections) are intentionally excluded — only the
        scalar legal values that land on a form line are gated by the
        envelope. Form renderers / audit-packet builders that need
        provenance for those scalars call
        ``RuleGraphExecution.legal_outputs[output_key]`` and pass the
        result through ``require_legal_value`` at the boundary.

        The wrap happens AFTER ``calculate(...)`` returns; rule
        ``calculate`` bodies still emit ``Mapping[str, Any]`` of bare
        Decimals (no rule-API change). Back-compat: ``final_facts``
        continues to expose bare values so downstream rule chains keep
        running unchanged.
        """
        wrapped: dict[str, LegalValue] = {}
        for result in self.stage_results:
            for output_key, value in result.outputs.items():
                if not isinstance(value, Decimal):
                    continue
                fingerprint = result.output_fingerprints[output_key]
                wrapped[output_key] = LegalValue(
                    amount=value,
                    stage_id=result.stage_id,
                    output_key=output_key,
                    fingerprint=fingerprint,
                )
        return wrapped

    def to_graph_dict(self) -> dict[str, Any]:
        results_by_stage_id = {result.stage_id: result for result in self.stage_results}
        producer_by_output_key: dict[str, str] = {}
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, str]] = []
        for rule in self.rules:
            stage = rule.stage
            result = results_by_stage_id.get(stage.stage_id)
            if result is None:
                raise ValueError(f"Missing StageResult for {stage.stage_id}")
            for input_key in stage.input_fact_keys:
                producer = producer_by_output_key.get(input_key)
                if producer:
                    edges.append(
                        {
                            "from_rule_id": producer,
                            "from_output_key": input_key,
                            "to_rule_id": stage.stage_id,
                            "to_input_key": input_key,
                        }
                    )
            nodes.append(
                {
                    "rule_id": stage.stage_id,
                    "country_or_scope": stage.country_or_scope,
                    "implementation_ref": rule.implementation_ref,
                    "legal_refs": list(stage.legal_refs),
                    "authority_urls": list(stage.authority_urls),
                    "input_fact_keys": list(stage.input_fact_keys),
                    "output_keys": list(stage.output_keys),
                    "rounding_policy": stage.rounding_policy,
                    "law_order_note": stage.law_order_note,
                    "narrative_templates": dict(stage.narrative_templates),
                    "form_line_refs": list(stage.form_line_refs),
                    "form_line_urls": list(stage.form_line_urls),
                    "result_fingerprint": result.fingerprint,
                    "input_values": dict(result.input_values),
                    "input_fingerprints": dict(result.input_fingerprints),
                    "output_fingerprints": dict(result.output_fingerprints),
                    "precision_notes": dict(result.precision_notes),
                }
            )
            for output_key in stage.output_keys:
                producer_by_output_key[output_key] = stage.stage_id
        return {
            "schema_version": 1,
            "stage_ids": list(self.validation.stage_ids),
            "initial_fact_keys": list(self.validation.initial_fact_keys),
            "output_keys": list(self.validation.output_keys),
            "nodes": nodes,
            "edges": edges,
        }

    def to_mermaid(self) -> str:
        lines = ["flowchart TD"]
        graph = self.to_graph_dict()
        for node in graph["nodes"]:
            rule_id = node["rule_id"]
            lines.append(f'  {rule_id.replace("-", "_")}["{rule_id}"]')
        for edge in graph["edges"]:
            lines.append(
                "  "
                f"{edge['from_rule_id'].replace('-', '_')} "
                f"-->|{edge['from_output_key']}| "
                f"{edge['to_rule_id'].replace('-', '_')}"
            )
        return "\n".join(lines) + "\n"


def validate_law_stage_graph(
    stages: Sequence[LawStage],
    *,
    available_fact_keys: Iterable[str],
    stage_results: Sequence[StageResult] | None = None,
) -> StageGraphValidation:
    stage_list = tuple(stages)
    initial_keys = tuple(_require_text("available_fact_keys[]", key) for key in available_fact_keys)
    available = set(initial_keys)
    produced_outputs: set[str] = set()
    seen_stage_ids: set[str] = set()
    for stage in stage_list:
        if not isinstance(stage, LawStage):
            raise ValueError("stages must contain LawStage instances")
        if stage.stage_id in seen_stage_ids:
            raise ValueError(f"duplicate stage_id: {stage.stage_id}")
        seen_stage_ids.add(stage.stage_id)
        missing_inputs = set(stage.input_fact_keys) - available
        if missing_inputs:
            raise ValueError(f"{stage.stage_id} missing input: {sorted(missing_inputs)}")
        duplicate_outputs = set(stage.output_keys) & produced_outputs
        if duplicate_outputs:
            raise ValueError(f"{stage.stage_id} duplicate output: {sorted(duplicate_outputs)}")
        produced_outputs.update(stage.output_keys)
        available.update(stage.output_keys)

    if stage_results is not None:
        results_by_stage_id: dict[str, StageResult] = {}
        for result in stage_results:
            if not isinstance(result, StageResult):
                raise ValueError("stage_results must contain StageResult instances")
            if result.stage_id in results_by_stage_id:
                raise ValueError(f"duplicate StageResult: {result.stage_id}")
            results_by_stage_id[result.stage_id] = result
        unknown_results = set(results_by_stage_id) - seen_stage_ids
        if unknown_results:
            raise ValueError(f"StageResult for unknown stage: {sorted(unknown_results)}")
        for stage in stage_list:
            result = results_by_stage_id.get(stage.stage_id)
            if result is not None:
                stage.validate_result(result)

    return StageGraphValidation(
        stage_ids=tuple(stage.stage_id for stage in stage_list),
        initial_fact_keys=tuple(sorted(initial_keys)),
        output_keys=tuple(sorted(produced_outputs)),
        final_available_keys=tuple(sorted(available)),
    )


class RuleInputDeclarationError(ValueError):
    """A ``LawRule.calculate`` body read a key that wasn't in
    ``LawStage.input_fact_keys``. Per § 32d Abs. 5 EStG audit-trail rigor
    every rule input must be a declared edge in the rule graph; an
    undeclared read means the audit graph is missing a real data
    dependency. The runtime tracker in ``execute_rule_graph`` surfaces
    these violations at the seam where they are introduced.
    """

    def __init__(self, stage_id: StageId | str, undeclared_keys: frozenset[str]) -> None:
        # P9: accept either the typed StageId (for forward-compat with
        # call sites that pass ``stage.stage_id_typed``) or the legacy
        # string form. Normalize to the literal string for the error
        # message and the public ``self.stage_id`` attribute so existing
        # ``except RuleInputDeclarationError as e: e.stage_id == "DE25-…"``
        # call sites continue to work.
        stage_id_str = str(stage_id) if isinstance(stage_id, StageId) else stage_id
        self.stage_id = stage_id_str
        self.undeclared_keys = undeclared_keys
        super().__init__(
            f"{stage_id_str} read undeclared facts {sorted(undeclared_keys)} — "
            f"add them to LawStage.input_fact_keys or stop reading them"
        )


class LegalInvariantViolation(ValueError):
    """A ``LawRule.calculate`` body detected that a legal reconciliation
    invariant does not hold for the supplied facts.

    Reconciliation invariants are stage-level cross-checks that two
    independently computed totals agree (e.g., the foreign-tax-paid total
    asserted by ``BRIDGE25-FOREIGN-TAX-RECONCILIATION`` against
    ``capital.explicit_foreign_tax_total``). Per CLAUDE.md the engine
    must fail closed when a legal invariant is violated rather than
    silently default to zero or paper over the discrepancy. The executor
    surfaces this exception as a stage failure with the offending
    ``stage_id`` so the pipeline run aborts at the seam where the
    invariant was introduced.

    Authority for the fail-closed discipline:
    - § 32d Abs. 5 EStG (per-Posten foreign-tax credit) requires the
      foreign-tax basis to be reconciled before the credit cap applies.
      https://www.gesetze-im-internet.de/estg/__32d.html
    - 26 U.S.C. § 901 (foreign tax credit) requires a verifiable
      foreign-tax-paid figure as the credit basis.
      https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
    """

    def __init__(self, stage_id: StageId | str, message: str) -> None:
        # P9: accept either the typed StageId (forward-compat) or the
        # legacy string; the error message + public attribute use the
        # literal string form so existing call sites that read
        # ``e.stage_id`` as a string keep working.
        stage_id_str = str(stage_id) if isinstance(stage_id, StageId) else stage_id
        self.stage_id = stage_id_str
        super().__init__(f"{stage_id_str}: {message}")


class _TrackingMapping(Mapping):
    """A read-only mapping wrapper that records every key read.

    The wrapper is used inside ``execute_rule_graph`` to instrument
    ``LawRule.calculate`` calls so the executor can surface undeclared-key
    reads (invariant I7). Authoring rules against this wrapper does not
    change semantics — every method delegates to the underlying mapping.
    """

    def __init__(self, source: Mapping[str, Any]) -> None:
        self._source = source
        self._read_keys: set[str] = set()

    def __getitem__(self, key: str) -> Any:
        self._read_keys.add(key)
        return self._source[key]

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            self._read_keys.add(key)
        return key in self._source

    def __iter__(self):
        # Iterating yields all keys, so flag every key as read. Authors who
        # need to enumerate inputs must declare them all in input_fact_keys.
        self._read_keys.update(self._source.keys())
        return iter(self._source)

    def __len__(self) -> int:
        return len(self._source)

    def get(self, key, default=None):  # noqa: D401 - Mapping API
        if isinstance(key, str):
            self._read_keys.add(key)
        return self._source.get(key, default)

    def keys(self):  # noqa: D401 - Mapping API
        self._read_keys.update(self._source.keys())
        return self._source.keys()

    def items(self):  # noqa: D401 - Mapping API
        self._read_keys.update(self._source.keys())
        return self._source.items()

    def values(self):  # noqa: D401 - Mapping API
        self._read_keys.update(self._source.keys())
        return self._source.values()

    @property
    def read_keys(self) -> frozenset[str]:
        return frozenset(self._read_keys)


def execute_rule_graph(
    initial_facts: Mapping[str, Any],
    rules: Sequence[LawRule],
    *,
    initial_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    rule_tuple = tuple(rules)
    if not rule_tuple:
        raise ValueError("rules is required")
    for rule in rule_tuple:
        if not isinstance(rule, LawRule):
            raise ValueError("rules must contain LawRule instances")
    facts = _require_mapping("initial_facts", initial_facts)
    fingerprints = {
        key: _require_text(f"initial_fingerprints[{key}]", initial_fingerprints[key])
        if initial_fingerprints is not None and key in initial_fingerprints
        else stable_fingerprint({"fact_key": key, "value": value})
        for key, value in facts.items()
    }
    stages = tuple(rule.stage for rule in rule_tuple)
    validation = validate_law_stage_graph(stages, available_fact_keys=facts.keys())
    results: list[StageResult] = []
    for rule in rule_tuple:
        stage = rule.stage
        missing = [key for key in stage.input_fact_keys if key not in facts]
        if missing:
            raise ValueError(f"{stage.stage_id} missing input facts: {missing}")
        # Wrap facts so undeclared-key reads inside calculate(...) are
        # surfaced as RuleInputDeclarationError (invariant I7). Each
        # calculate gets its own tracker instance so the read set is
        # scoped to that one rule invocation.
        tracker = _TrackingMapping(dict(facts))
        raw_outputs = rule.calculate(tracker)
        declared = set(stage.input_fact_keys)
        undeclared = tracker.read_keys - declared
        if undeclared:
            raise RuleInputDeclarationError(
                stage.stage_id,
                frozenset(undeclared),
            )
        outputs = _require_mapping(f"{stage.stage_id}.outputs", raw_outputs)
        input_values = {key: facts[key] for key in stage.input_fact_keys}
        output_fingerprints = {
            key: stable_fingerprint({"stage_id": stage.stage_id, "output_key": key, "value": value})
            for key, value in outputs.items()
        }
        result = StageResult(
            stage_id=stage.stage_id,
            outputs=outputs,
            input_values=input_values,
            input_fingerprints={key: fingerprints[key] for key in stage.input_fact_keys},
            output_fingerprints=output_fingerprints,
            diagnostics=(),
            precision_notes={key: stage.rounding_policy for key in outputs},
        )
        stage.validate_result(result)
        results.append(result)
        facts.update(outputs)
        fingerprints.update(output_fingerprints)
    validation = validate_law_stage_graph(
        stages,
        available_fact_keys=initial_facts.keys(),
        stage_results=results,
    )
    return RuleGraphExecution(
        rules=rule_tuple,
        initial_facts=dict(initial_facts),
        final_facts=facts,
        stage_results=tuple(results),
        validation=validation,
    )


def stage_audit_rows(
    stages: Sequence[LawStage],
    stage_results: Sequence[StageResult] = (),
) -> tuple[StageAuditRow, ...]:
    results_by_stage_id = {result.stage_id: result for result in stage_results}
    rows: list[StageAuditRow] = []
    for stage in stages:
        result = results_by_stage_id.get(stage.stage_id)
        rows.append(
            StageAuditRow(
                stage_id=stage.stage_id,
                country_or_scope=stage.country_or_scope,
                legal_refs=tuple(stage.legal_refs),
                authority_urls=tuple(stage.authority_urls),
                input_fact_keys=tuple(stage.input_fact_keys),
                output_keys=tuple(stage.output_keys),
                rounding_policy=stage.rounding_policy,
                law_order_note=stage.law_order_note,
                narrative_templates=dict(stage.narrative_templates),
                form_line_refs=tuple(stage.form_line_refs),
                form_line_urls=tuple(stage.form_line_urls),
                result_fingerprint=result.fingerprint if result else None,
                # StageAuditRow is metadata-oriented; input values stay in StageResult
                # and the durable execution graph so renderers cannot invent them.
                precision_notes=result.precision_notes if result else {},
            )
        )
    return tuple(rows)


__all__ = [
    "LawRule",
    "LawStage",
    "LegalInvariantViolation",
    "RuleGraphExecution",
    "RuleInputDeclarationError",
    "StageAuditRow",
    "StageDiagnostic",
    "StageGraphValidation",
    "StageResult",
    "execute_rule_graph",
    "stage_audit_rows",
    "validate_law_stage_graph",
]
