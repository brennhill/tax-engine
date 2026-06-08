from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from decimal import Decimal
import hashlib
import json
from typing import Any


def _require_text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _require_tuple(name: str, values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(_require_text(f"{name}[]", value) for value in values)
    if not result:
        raise ValueError(f"{name} is required")
    return result


def _fingerprintable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"type": "Decimal", "value": str(value)}
    # NOTE (L10, 2026-05-01 correctness review): ``is_dataclass(value)`` is
    # True for both dataclass instances AND dataclass classes themselves.
    # Hashing a class object would explode at ``getattr(value, field.name)``
    # below (instance attributes don't exist on the class), so the current
    # contract is gated by usage rather than an explicit
    # ``not isinstance(value, type)`` guard. ``core.io.AuditEncoder.default``
    # tightens this with the explicit ``not isinstance(o, type)`` check;
    # mirror that here if the call surface ever broadens.
    if is_dataclass(value):
        return {
            field.name: _fingerprintable(getattr(value, field.name))
            for field in fields(value)
            if field.init
        }
    if isinstance(value, Mapping):
        # NOTE (L9, 2026-05-01 correctness review): mapping keys are coerced
        # to ``str`` for both the sort and the emitted JSON object keys.
        # Two distinct keys that share a string representation (e.g.,
        # ``int(1)`` and ``str("1")``) would collide in the emitted dict
        # and produce a non-unique sort key. Current rule-graph payloads
        # use only string keys so this is a robustness gap rather than a
        # live bug; document so a future caller mixing key types is
        # forced to revisit this canonicalization.
        return {str(key): _fingerprintable(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, frozenset | set):
        # Sets are unordered; sort by string for stability so two equal sets
        # always produce the same fingerprint.
        return [_fingerprintable(item) for item in sorted(value, key=str)]
    if isinstance(value, tuple | list):
        return [_fingerprintable(item) for item in value]
    return value


def stable_fingerprint(payload: Mapping[str, Any]) -> str:
    # Invariant I6 (§ 32d Abs. 5 EStG audit-trail): fingerprint payloads must
    # carry the *canonical* value (Decimal, dataclass, Mapping, etc.) so the
    # _fingerprintable canonicalizer produces deterministic output across
    # interpreter sessions. Stringifying via repr() defeats canonicalization
    # because Decimal('1.00') and Decimal('1.0') repr-differ but are legally
    # identical. Reject keys that look like repr-stringified shadows.
    if isinstance(payload, Mapping):
        for key in payload:
            key_str = str(key)
            if key_str.endswith("_repr") or key_str.startswith("repr_"):
                raise ValueError(
                    "fingerprint payload must use canonical 'value' field, "
                    "not repr-stringified"
                )
    serialized = json.dumps(_fingerprintable(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FactKey:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _require_text("FactKey.value", self.value))


@dataclass(frozen=True)
class FactProvenance:
    source_document_ref: str
    source_field: str
    extracted_by: str
    source_line: int | None = None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_document_ref",
            _require_text("FactProvenance.source_document_ref", self.source_document_ref),
        )
        object.__setattr__(
            self,
            "source_field",
            _require_text("FactProvenance.source_field", self.source_field),
        )
        object.__setattr__(
            self,
            "extracted_by",
            _require_text("FactProvenance.extracted_by", self.extracted_by),
        )
        if self.source_line is not None and self.source_line < 1:
            raise ValueError("FactProvenance.source_line must be positive")
        object.__setattr__(
            self,
            "notes",
            tuple(note.strip() for note in self.notes if isinstance(note, str) and note.strip()),
        )


@dataclass(frozen=True)
class CanonicalFact:
    key: str
    value: Any
    provenance: FactProvenance
    tax_year: int
    taxpayer_scope: str
    unit: str
    confidence: Decimal
    currency: str | None = None
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _require_text("CanonicalFact.key", self.key))
        if self.value is None:
            raise ValueError("CanonicalFact.value is required")
        if not isinstance(self.provenance, FactProvenance):
            raise ValueError("CanonicalFact.provenance is required")
        if not isinstance(self.tax_year, int) or self.tax_year < 1900:
            raise ValueError("CanonicalFact.tax_year must be a valid year")
        object.__setattr__(
            self,
            "taxpayer_scope",
            _require_text("CanonicalFact.taxpayer_scope", self.taxpayer_scope),
        )
        object.__setattr__(self, "unit", _require_text("CanonicalFact.unit", self.unit))
        if not isinstance(self.confidence, Decimal):
            raise ValueError("CanonicalFact.confidence must be a Decimal")
        if self.confidence < Decimal("0") or self.confidence > Decimal("1"):
            raise ValueError("CanonicalFact.confidence must be between 0 and 1")
        if self.currency is not None:
            object.__setattr__(self, "currency", _require_text("CanonicalFact.currency", self.currency))
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint(
                {
                    "key": self.key,
                    "value_type": type(self.value).__qualname__,
                    "value": self.value,
                    "provenance": self.provenance,
                    "tax_year": self.tax_year,
                    "taxpayer_scope": self.taxpayer_scope,
                    "currency": self.currency,
                    "unit": self.unit,
                    "confidence": self.confidence,
                }
            ),
        )


@dataclass(frozen=True)
class UnsupportedFact:
    fact: CanonicalFact
    reason: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.fact, CanonicalFact):
            raise ValueError("UnsupportedFact.fact must be a CanonicalFact")
        object.__setattr__(self, "reason", _require_text("UnsupportedFact.reason", self.reason))
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint({"kind": "unsupported", "fact": self.fact.fingerprint, "reason": self.reason}),
        )


@dataclass(frozen=True)
class IgnoredFact:
    fact: CanonicalFact
    reason: str
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.fact, CanonicalFact):
            raise ValueError("IgnoredFact.fact must be a CanonicalFact")
        object.__setattr__(self, "reason", _require_text("IgnoredFact.reason", self.reason))
        object.__setattr__(
            self,
            "fingerprint",
            stable_fingerprint({"kind": "ignored", "fact": self.fact.fingerprint, "reason": self.reason}),
        )


def assert_facts_ready_for_legal_stages(
    facts: Iterable[CanonicalFact | IgnoredFact | UnsupportedFact],
) -> None:
    for fact in facts:
        canonical = fact.fact if isinstance(fact, IgnoredFact | UnsupportedFact) else fact
        if not isinstance(canonical, CanonicalFact):
            raise ValueError("facts must be CanonicalFact, IgnoredFact, or UnsupportedFact instances")
        if not isinstance(canonical.provenance, FactProvenance):
            raise ValueError(f"{canonical.key} is missing provenance")
        if not canonical.provenance.source_document_ref or not canonical.provenance.source_field:
            raise ValueError(f"{canonical.key} is missing provenance")


__all__ = [
    "CanonicalFact",
    "FactKey",
    "FactProvenance",
    "IgnoredFact",
    "UnsupportedFact",
    "assert_facts_ready_for_legal_stages",
    "stable_fingerprint",
]
