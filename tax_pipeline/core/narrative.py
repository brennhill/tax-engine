from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _require_sequence(name: str, values: Iterable[Any]) -> tuple[Any, ...]:
    result = tuple(values)
    if not result:
        raise ValueError(f"{name} is required")
    return result


@dataclass(frozen=True)
class NarrativeValue:
    label: str
    value: str
    key: str
    source: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _require_text("NarrativeValue.label", self.label))
        object.__setattr__(self, "value", _require_text("NarrativeValue.value", self.value))
        object.__setattr__(self, "key", _require_text("NarrativeValue.key", self.key))
        if self.source:
            object.__setattr__(self, "source", _require_text("NarrativeValue.source", self.source))
        if self.note:
            object.__setattr__(self, "note", _require_text("NarrativeValue.note", self.note))

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "value": self.value,
            "key": self.key,
            "source": self.source,
            "note": self.note,
        }


@dataclass(frozen=True)
class NarrativeMathStep:
    statement: str
    formula: str
    result: str
    rounding_note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "statement", _require_text("NarrativeMathStep.statement", self.statement))
        object.__setattr__(self, "formula", _require_text("NarrativeMathStep.formula", self.formula))
        object.__setattr__(self, "result", _require_text("NarrativeMathStep.result", self.result))
        if self.rounding_note:
            object.__setattr__(self, "rounding_note", _require_text("NarrativeMathStep.rounding_note", self.rounding_note))

    def to_dict(self) -> dict[str, str]:
        return {
            "statement": self.statement,
            "formula": self.formula,
            "result": self.result,
            "rounding_note": self.rounding_note,
        }


@dataclass(frozen=True)
class NarrativeFormLine:
    form: str
    line: str
    value: str
    note: str = ""
    url: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "form", _require_text("NarrativeFormLine.form", self.form))
        object.__setattr__(self, "line", _require_text("NarrativeFormLine.line", self.line))
        object.__setattr__(self, "value", _require_text("NarrativeFormLine.value", self.value))
        if self.note:
            object.__setattr__(self, "note", _require_text("NarrativeFormLine.note", self.note))
        if self.url:
            object.__setattr__(self, "url", _require_text("NarrativeFormLine.url", self.url))

    def to_dict(self) -> dict[str, str]:
        return {
            "form": self.form,
            "line": self.line,
            "value": self.value,
            "note": self.note,
            "url": self.url,
        }


@dataclass(frozen=True)
class RuleNarrative:
    rule_id: str
    country: str
    language: str
    template_id: str
    title: str
    legal_refs: Sequence[str]
    authority_urls: Sequence[str]
    inputs: Sequence[NarrativeValue]
    math_steps: Sequence[NarrativeMathStep]
    outputs: Sequence[NarrativeValue]
    # ``form_lines`` may be empty for stages whose every output is
    # classified via ``OutputDeclaration.audit_waypoints`` rather than a
    # ``FormLineRef`` (e.g. RECONCILIATION_INVARIANT or INTERMEDIATE_MATH
    # outputs that participate in the calculation but never land on a
    # specific form line). Per WS-2B the renderer ↔ OutputDeclaration
    # bidirectional contract (invariant I3) requires each FormLineRef to
    # match a ``_required_form_line(rows, form, line, ...)`` read on the
    # German KAP / KAP-INV CSV path; non-matching descriptive labels
    # were correctly removed and replaced with audit waypoints, so the
    # narrative form_lines tuple can now be empty for those stages
    # without violating any invariant.
    form_lines: Sequence[NarrativeFormLine]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _require_text("RuleNarrative.rule_id", self.rule_id))
        object.__setattr__(self, "country", _require_text("RuleNarrative.country", self.country))
        object.__setattr__(self, "language", _require_text("RuleNarrative.language", self.language))
        object.__setattr__(self, "template_id", _require_text("RuleNarrative.template_id", self.template_id))
        if self.template_id != self.rule_id:
            raise ValueError("RuleNarrative.template_id must equal rule_id")
        object.__setattr__(self, "title", _require_text("RuleNarrative.title", self.title))
        object.__setattr__(self, "legal_refs", tuple(_require_text("RuleNarrative.legal_refs[]", ref) for ref in _require_sequence("RuleNarrative.legal_refs", self.legal_refs)))
        object.__setattr__(self, "authority_urls", tuple(_require_text("RuleNarrative.authority_urls[]", url) for url in _require_sequence("RuleNarrative.authority_urls", self.authority_urls)))
        inputs = _require_sequence("RuleNarrative.inputs", self.inputs)
        math_steps = _require_sequence("RuleNarrative.math_steps", self.math_steps)
        outputs = _require_sequence("RuleNarrative.outputs", self.outputs)
        # form_lines may be empty when the stage's outputs are all
        # audit-waypoint classified; coerce to tuple without enforcing
        # non-empty.
        form_lines = tuple(self.form_lines)
        for value in (*inputs, *outputs):
            if not isinstance(value, NarrativeValue):
                raise ValueError("RuleNarrative inputs and outputs must contain NarrativeValue instances")
        for step in math_steps:
            if not isinstance(step, NarrativeMathStep):
                raise ValueError("RuleNarrative.math_steps must contain NarrativeMathStep instances")
        for line in form_lines:
            if not isinstance(line, NarrativeFormLine):
                raise ValueError("RuleNarrative.form_lines must contain NarrativeFormLine instances")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "math_steps", math_steps)
        object.__setattr__(self, "outputs", outputs)
        object.__setattr__(self, "form_lines", form_lines)

    def to_dict(self) -> dict[str, Any]:
        # WS-5G / invariant I12: templates address inputs by declared key
        # (``rule.inputs_by_key["<key>"].value``) rather than by positional
        # index. Adding a new entry to a stage's ``input_fact_keys`` tuple
        # used to silently shift the ``rule.inputs[N]`` indices and corrupt
        # template output (the WS-3A redo hit a JSONDecodeError when a new
        # declared input was prepended to DE25-07-TAXABLE-INCOME). The
        # ``inputs`` list keeps its original shape so existing fingerprints
        # remain stable; ``inputs_by_key`` is a derived projection added
        # AFTER the fingerprint is computed, so the audit-packet fingerprint
        # consumed by ``final_legal_output`` and the legal-execution-graph
        # nodes does not change.
        # Authority for the fail-closed discipline on duplicate declared
        # inputs: ``LawStage.input_fact_keys`` is a tuple of distinct fact
        # keys by construction (see ``tax_pipeline/core/stages.py``). If a
        # caller violates that invariant, the by-key projection collapses
        # entries silently — raise instead per CLAUDE.md fail-closed rule.
        input_dicts = [value.to_dict() for value in self.inputs]
        payload = {
            "rule_id": self.rule_id,
            "country": self.country,
            "language": self.language,
            "template_id": self.template_id,
            "title": self.title,
            "legal_refs": list(self.legal_refs),
            "authority_urls": list(self.authority_urls),
            "inputs": input_dicts,
            "math_steps": [step.to_dict() for step in self.math_steps],
            "outputs": [value.to_dict() for value in self.outputs],
            "form_lines": [line.to_dict() for line in self.form_lines],
        }
        payload["fingerprint"] = stable_fingerprint(payload)
        inputs_by_key: dict[str, dict[str, str]] = {}
        for item in input_dicts:
            key = item["key"]
            if key in inputs_by_key:
                raise ValueError(
                    f"RuleNarrative.inputs contains duplicate key {key!r}; cannot build inputs_by_key view"
                )
            inputs_by_key[key] = item
        payload["inputs_by_key"] = inputs_by_key
        return payload


def rule_narrative_from_mapping(payload: Mapping[str, Any]) -> RuleNarrative:
    return RuleNarrative(
        rule_id=str(payload["rule_id"]),
        country=str(payload["country"]),
        language=str(payload["language"]),
        template_id=str(payload["template_id"]),
        title=str(payload["title"]),
        legal_refs=tuple(str(value) for value in payload["legal_refs"]),
        authority_urls=tuple(str(value) for value in payload["authority_urls"]),
        inputs=tuple(
            NarrativeValue(
                str(value["label"]),
                str(value["value"]),
                str(value["key"]),
                str(value.get("source", "")),
                str(value.get("note", "")),
            )
            for value in payload["inputs"]
        ),
        math_steps=tuple(
            NarrativeMathStep(
                str(step["statement"]),
                str(step["formula"]),
                str(step["result"]),
                str(step.get("rounding_note", "")),
            )
            for step in payload["math_steps"]
        ),
        outputs=tuple(
            NarrativeValue(
                str(value["label"]),
                str(value["value"]),
                str(value["key"]),
                str(value.get("source", "")),
                str(value.get("note", "")),
            )
            for value in payload["outputs"]
        ),
        form_lines=tuple(
            NarrativeFormLine(
                str(line["form"]),
                str(line["line"]),
                str(line["value"]),
                str(line.get("note", "")),
                str(line.get("url", "")),
            )
            for line in payload["form_lines"]
        ),
    )


__all__ = [
    "NarrativeFormLine",
    "NarrativeMathStep",
    "NarrativeValue",
    "RuleNarrative",
    "rule_narrative_from_mapping",
]
