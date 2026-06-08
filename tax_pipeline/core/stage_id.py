"""Typed identifier for legal-rule stages.

Historically every ``LawStage`` carried a free-text ``stage_id`` such as
``"DE25-13F-VORABPAUSCHALE"``. The string format encodes a triple
``(country_or_scope, year, sequence)`` but the encoding is implicit —
nothing parses it, nothing validates it, and a typo or year drift is
invisible to the executor. P9 introduces a typed ``StageId`` triple
whose ``__str__`` PRESERVES the historical string form byte-for-byte so
fingerprint payloads (invariant I6) remain identical.

The serialized form is the contract. ``str(StageId("DE", "25",
"13F-VORABPAUSCHALE"))`` MUST equal ``"DE25-13F-VORABPAUSCHALE"``.
``stable_fingerprint(...)`` payloads include this string verbatim, and
the byte-stable ``final-legal-output.json`` from the P1 audit is keyed
off the same digest. Any change to ``__str__`` is a fingerprint break.

Country-or-scope prefixes encountered in the 2025 rule graph:

- ``DE`` — Germany law stages (``DE25-*``).
- ``US`` — United States law stages (``US25-*``).
- ``TREATY`` — bilateral treaty stages (``TREATY25-*``); the only
  treaty modeled today is the DBA-USA, but the prefix is
  treaty-agnostic to leave room for a future ``TREATY-DBA-VN-*``.
- ``BRIDGE`` — cross-jurisdiction reconciliation stages
  (``BRIDGE25-FOREIGN-TAX-RECONCILIATION``).
- ``DERIVE-DE`` / ``DERIVE-USA`` — Pipeline-1 derivation stages
  (``DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION``,
  ``DERIVE-USA25-…``). The ``DERIVE-`` prefix denotes the derivation
  pipeline; the second segment names the underlying jurisdiction.

The parser handles all five prefix shapes. The ``year_short`` is held
as a two-character string (``"25"``) rather than an int so a short
year that begins with ``0`` (hypothetically) survives the round-trip
without numeric coercion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Recognized country-or-scope prefixes, ordered with longer/more specific
# prefixes first so the regex alternation prefers ``DERIVE-DE`` over a
# spurious ``DE`` match against ``DERIVE-DE25-…``.
_KNOWN_COUNTRIES: tuple[str, ...] = (
    "DERIVE-USA",
    "DERIVE-DE",
    "TREATY",
    "BRIDGE",
    "US",
    "DE",
)


# A valid stage ID matches ``<country><year_short>-<sequence>`` where:
# - ``<country>`` is one of the recognized prefixes above;
# - ``<year_short>`` is a 2-digit numeric year (``"25"`` for 2025);
# - ``<sequence>`` is a non-empty, uppercase, hyphen-separated tail
#   (the per-statute / per-section identifier, e.g.
#   ``"13F-VORABPAUSCHALE"``).
_STAGE_ID_RE = re.compile(
    r"^(?P<country>" + "|".join(_KNOWN_COUNTRIES) + r")"
    r"(?P<year_short>\d{2})"
    r"-(?P<sequence>[A-Z0-9][A-Z0-9-]*)$"
)


@dataclass(frozen=True)
class StageId:
    """Typed legal-rule stage identifier.

    The triple ``(country, year_short, sequence)`` deserializes from and
    serializes to the historical string form (e.g.
    ``"DE25-13F-VORABPAUSCHALE"``). The serialized form is the only
    representation that crosses fingerprint / JSON / form-line
    boundaries, so structural changes to the string format are
    fingerprint-breaking under invariant I6.
    """

    country: str
    year_short: str
    sequence: str

    def __post_init__(self) -> None:
        if not isinstance(self.country, str) or self.country not in _KNOWN_COUNTRIES:
            raise ValueError(
                f"StageId.country must be one of {_KNOWN_COUNTRIES}; got {self.country!r}"
            )
        if (
            not isinstance(self.year_short, str)
            or len(self.year_short) != 2
            or not self.year_short.isdigit()
        ):
            raise ValueError(
                f"StageId.year_short must be a 2-digit string (e.g. '25'); got {self.year_short!r}"
            )
        if not isinstance(self.sequence, str) or not self.sequence:
            raise ValueError(
                f"StageId.sequence must be a non-empty string; got {self.sequence!r}"
            )
        # Validate the sequence is the same uppercase / hyphen-only shape
        # the regex matches so accidental lowercase / whitespace input
        # does not silently round-trip.
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]*", self.sequence):
            raise ValueError(
                f"StageId.sequence must be uppercase A-Z/0-9/'-', starting with an "
                f"alphanumeric; got {self.sequence!r}"
            )

    def __str__(self) -> str:
        return f"{self.country}{self.year_short}-{self.sequence}"

    @classmethod
    def parse(cls, raw: str) -> StageId:
        """Parse a literal stage-id string into a typed :class:`StageId`.

        Accepts every shape produced by ``__str__``. Raises
        ``ValueError`` on malformed input — there is no silent default.
        """
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(f"StageId.parse requires a non-empty string; got {raw!r}")
        match = _STAGE_ID_RE.match(raw)
        if not match:
            raise ValueError(
                f"StageId.parse: {raw!r} does not match a known stage-id shape "
                f"(<country><year_short>-<sequence>; country in {_KNOWN_COUNTRIES})."
            )
        return cls(
            country=match.group("country"),
            year_short=match.group("year_short"),
            sequence=match.group("sequence"),
        )

    @classmethod
    def coerce(cls, value: StageId | str) -> StageId:
        """Accept either a typed :class:`StageId` or its string form.

        The :class:`LawStage` and :class:`LegalValue` constructors call
        this so existing call sites that pass ``stage_id="DE25-…"``
        continue to work without code churn — the string is parsed at
        the boundary.
        """
        if isinstance(value, StageId):
            return value
        return cls.parse(value)


__all__ = ["StageId"]
