"""Typed envelope for values that cross the rule-graph → form-renderer
boundary (invariant I11).

Per CLAUDE.md, every value the engine writes onto a tax form line must
trace back to a declared rule's output and carry its (stage_id,
output_key, fingerprint) provenance. Bare ``Decimal`` arithmetic in
projections / orchestrator scripts is exactly how LEAK-1 (final refund)
and LEAK-3 (Anlage KAP line 19) escaped the rule graph and reached the
audit packet without an audit edge.

Authority for the audit-trail discipline:
- § 32d Abs. 5 EStG (per-Posten foreign tax credit) requires the
  foreign-tax basis to be reconciled before the credit cap applies.
  https://www.gesetze-im-internet.de/estg/__32d.html
- 26 U.S.C. § 901 (foreign tax credit) requires a verifiable
  foreign-tax-paid figure as the credit basis.
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim

The envelope is a frozen dataclass. ``require_legal_value`` is the
boundary helper that form renderers and audit-packet builders call; it
fails closed with a ``TypeError`` if a bare ``Decimal`` (or anything
else) reaches the boundary, making the LEAK-1 / LEAK-3 class of bug
unrepresentable.

See ``docs/invariant-migration-plan.md`` §6 / WS-4D.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from tax_pipeline.core.money import Currency
from tax_pipeline.core.stage_id import StageId


@dataclass(frozen=True)
class LegalValue:
    """A form-bound legal value with its full provenance.

    ``amount`` is the canonical Decimal value the rule produced.
    ``stage_id`` is the producing stage's identifier — the literal
    string form (e.g. ``"DE25-13F-VORABPAUSCHALE"``). The constructor
    accepts either a :class:`StageId` typed triple or the legacy string
    and serializes via ``str(...)`` so the persisted provenance
    triple under ``_provenance.form_lines[country][output_key]``
    remains byte-identical across the P9 migration.
    ``output_key`` is the declared ``OutputDeclaration.key`` under which
    the rule emitted this value.
    ``fingerprint`` is the SHA-256 hex digest produced by
    ``stable_fingerprint({"stage_id": ..., "output_key": ..., "value":
    ...})`` — the same fingerprint the executor records on the
    ``StageResult.output_fingerprints`` map (no parallel third-domain
    re-hash).
    ``currency`` (P4) is an optional :class:`Currency` tag that travels
    alongside the amount so the renderer no longer has to infer
    currency from a string ``unit=`` argument. It is OPTIONAL for
    backward compatibility — call sites that don't pass currency get
    ``None`` and the renderer falls back to the legacy ``unit=`` path.
    The currency tag is intentionally NOT part of the canonical
    fingerprint payload (invariant I6): currency travels alongside
    the value but does not enter ``stable_fingerprint`` or any
    persisted ``_provenance`` triple. This preserves the byte-stable
    md5s of ``final-legal-output.json`` across the P4 migration.
    """

    amount: Decimal
    stage_id: str
    output_key: str
    fingerprint: str
    currency: Currency | None = field(default=None)

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                "LegalValue.amount must be a Decimal; "
                f"got {type(self.amount).__qualname__}"
            )
        # P4: currency is optional, but if provided it must be a
        # Currency enum member — fail closed on a stray string label
        # (e.g. ``"USD"``) so the renderer can rely on the closed set.
        if self.currency is not None and not isinstance(self.currency, Currency):
            raise TypeError(
                "LegalValue.currency must be a Currency enum member or None; "
                f"got {type(self.currency).__qualname__}"
            )
        # P9: ``stage_id`` may arrive as a typed :class:`StageId` (from
        # ``RuleGraphExecution.legal_outputs``) or as a literal string
        # (from synthetic renderer-side provenance in
        # ``forms/common.py``). Coerce to ``str(stage_id)`` so the
        # serialized provenance triple is byte-identical regardless of
        # which path produced it.
        if isinstance(self.stage_id, StageId):
            object.__setattr__(self, "stage_id", str(self.stage_id))
        for field_name in ("stage_id", "output_key", "fingerprint"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"LegalValue.{field_name} is required (non-empty string)"
                )

    def provenance(self) -> dict[str, str]:
        """Return the provenance triple as a JSON-serializable dict.

        Used by ``final_legal_output.py`` to attach a ``_provenance``
        sub-field alongside each rendered Decimal-as-string so the audit
        packet carries per-value provenance at the form-line boundary.
        """
        return {
            "stage_id": self.stage_id,
            "output_key": self.output_key,
            "fingerprint": self.fingerprint,
        }


def require_legal_value(value: Any, *, context: str) -> LegalValue:
    """Boundary guard: assert ``value`` is a :class:`LegalValue`.

    Form-renderer call sites and audit-packet provenance builders call
    this when they need to extract ``value.amount`` for actual rendering.
    Passing a bare ``Decimal`` (or anything other than ``LegalValue``)
    fails closed with a ``TypeError`` whose message names the calling
    ``context`` so the offender is obvious in the traceback.

    The fail-closed posture is mandatory under CLAUDE.md: missing
    provenance for a form-line value is a legal-audit defect, not a
    formatting oddity.
    """
    if not isinstance(value, LegalValue):
        raise TypeError(
            f"{context}: form-bound legal value must be a LegalValue envelope; "
            f"got {type(value).__qualname__}. "
            "Wrap the rule output via RuleGraphExecution.legal_outputs."
        )
    return value


__all__ = [
    "LegalValue",
    "require_legal_value",
]
