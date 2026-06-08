"""Treaty registry — Proposal 3 (architecture review 2026-05-04).

Today the only modeled treaty is DBA-USA (the 1989 U.S.–Germany Income
and Capital Tax Convention as amended by the 2006 Protocol). The
treaty namespace (``tax_pipeline.y2025.treaty_law`` /
``tax_pipeline.y2025.treaty_stages`` /
``tax_pipeline.y2025.treaty_rules`` plus
``BRIDGE25-FOREIGN-TAX-RECONCILIATION`` plus
``final-legal-output.json::treaty: {...}``) is shaped as if exactly one
treaty exists per run. P3 abstracts the treaty into a registered edge
between two countries so a future second treaty (DE-VN, US-VN, UK-DE,
...) lands as a single registry row plus its own per-treaty rule /
stage / law modules — without rewriting the existing DBA-USA modeling.

This module is **year-agnostic by design**: the registry maps a
``treaty_id`` to its parties, enablement metadata, and the dotted
paths of its (currently year-2025-only) rule / stage / law modules.
The lazy-import discipline (mirrors
:mod:`tax_pipeline.jurisdictions`) means no treaty module is loaded
until something calls into it, so adding a second treaty does not
slow boot for runs that do not use it.

Invariants this module preserves:

* I1 (no legal constants outside law modules): nothing here is a
  legal constant. The 15 % DBA-USA Art. 10(2)(b) rate continues to
  live in ``tax_pipeline/y2025/treaty_law.py``; this registry only
  declares the dotted-path of that law module.
* I13 (disabled-jurisdiction explicit absence): a treaty is enabled
  only when (a) the treaty's own ``enablement_flag`` is true on the
  profile **and** (b) both parties' jurisdictions are enabled
  per :func:`tax_pipeline.y2025.cross_jurisdiction.is_jurisdiction_enabled`.
  When the U.S. side is opted out under 26 U.S.C. § 6012, the
  DBA-USA treaty is automatically inapplicable and
  :func:`is_treaty_enabled` returns ``False``.
* I6 (canonical fingerprints): stage IDs continue to fingerprint as
  the existing ``TREATY25-...`` strings. This registry does not
  rename stages.

Deferred (Commit 6, P3):
  ``final-legal-output.json`` carries a single ``treaty: {...}``
  block today. For a multi-treaty future the schema becomes
  ``treaties: {"DBA_USA": {...}, "DBA_VN": {...}, ...}``. Migrating
  the schema is a fingerprint-stability event (renderer goldens,
  audit packets, downstream consumers); we defer the migration
  until a second treaty actually lands. Until then, the registry
  exposes the abstraction without forcing a schema change. See
  :mod:`tax_pipeline.pipelines.y2025.final_legal_output` for the
  current single-block writer.

References:

* Architecture review §5 Proposal 3.
* DBA-USA bilingual treaty text:
  https://www.irs.gov/pub/irs-trty/germany.pdf
* DBA-USA Technical Explanation:
  https://www.irs.gov/pub/irs-trty/germtech.pdf
* 26 U.S.C. § 6012 — gives the U.S. enablement flag its legal posture
  authority; the treaty's enablement transitively depends on it.
  https://www.law.cornell.edu/uscode/text/26/6012
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# Schema-deferral marker — P3 Commit 6 (deferred per architecture review).
# ---------------------------------------------------------------------------
# The current ``final-legal-output.json`` schema has a single ``treaty:
# {...}`` block. When a second treaty is modeled, this should migrate to
# ``treaties: {"DBA_USA": {...}, ...}``. Deferred until then because schema
# migration is a fingerprint-stability event affecting renderer goldens
# and downstream consumers.
#
# Why this marker lives here, not just in the module docstring:
# the migration is a multi-touchpoint event (renderer code under
# ``tax_pipeline/pipelines/y2025/final_legal_output.py``, golden test
# fixtures, the ``_provenance.treaty.*`` audit block, and any external
# consumers reading the JSON). A grep for
# ``FINAL_LEGAL_OUTPUT_TREATY_SCHEMA_DEFERRED`` surfaces every site that
# the migration must coordinate when it lands. The flag itself is
# ``True`` today; flipping it to ``False`` is the first edit of the
# Commit-6 schema-migration patch series.
FINAL_LEGAL_OUTPUT_TREATY_SCHEMA_DEFERRED: bool = True
"""Whether ``final-legal-output.json`` still uses the single-treaty
``treaty: {...}`` schema (``True``) instead of the multi-treaty
``treaties: {"DBA_USA": {...}, ...}`` schema. Stays ``True`` until a
second treaty is modeled — see this module's "Deferred (Commit 6, P3)"
section."""


@dataclass(frozen=True)
class TreatyDefinition:
    """Static metadata describing one bilateral income-tax treaty.

    Attributes:
      treaty_id: Canonical Python-identifier-shaped key
          (``"DBA_USA"``). Stable across years; used as the registry
          key. Underscore-separated so it is a valid Python identifier
          (suitable for use as a JSON key or attribute slot).
      display_name: Full official treaty title in English. Used in
          narrative copy and audit packet headers.
      short_name: Compact human-readable label
          (``"U.S.-Germany Income Tax Convention"``).
      parties: Tuple of two ISO-3166-1 alpha-2 uppercase country codes,
          stored in **alphabetical order**. Alphabetical sorting makes
          ``(country_a, country_b)`` lookups order-independent so the
          DBA-USA edge resolves the same whether queried as ``("DE",
          "US")`` or ``("US", "DE")``.
      in_force_year: Calendar year the treaty entered into force
          (1989 for DBA-USA).
      last_protocol_year: Calendar year of the most recent amending
          protocol (2006 for DBA-USA), or ``None`` if no protocol has
          amended the original treaty. Used in narrative copy and as a
          documentation anchor.
      enablement_flag: Profile-level boolean key gating this treaty's
          pathway. Read from ``elections.<flag>`` on the profile.
          Defaults to :attr:`enablement_default` when absent.
      enablement_default: Default value when the flag is absent from
          the profile. ``True`` for DBA-USA preserves backward
          compatibility with workspaces materialized before the flag
          existed.
      rules_module: Dotted path to the per-year rules module
          (``"tax_pipeline.y2025.treaty_rules"``). Lazy-imported.
      stages_module: Dotted path to the per-year stages module.
      law_module: Dotted path to the per-year law-constants module.
      authority_url: Canonical authority URL for the treaty text
          (IRS-hosted PDF for DBA-USA).
    """

    treaty_id: str
    display_name: str
    short_name: str
    parties: tuple[str, str]
    in_force_year: int
    last_protocol_year: int | None
    enablement_flag: str
    enablement_default: bool
    rules_module: str
    stages_module: str
    law_module: str
    authority_url: str


def _normalize_parties(parties: tuple[str, str]) -> tuple[str, str]:
    """Return ``parties`` as an alphabetically-sorted ISO-2 uppercase tuple.

    Centralised so registry construction and lookup share the same
    canonicalization. Fail closed on malformed input (length, casing).
    """
    if len(parties) != 2:
        raise ValueError(
            f"TreatyDefinition.parties must be a 2-tuple, got {parties!r}"
        )
    a, b = parties
    if not isinstance(a, str) or not isinstance(b, str):
        raise TypeError(f"TreatyDefinition.parties members must be str, got {parties!r}")
    a_norm = a.strip().upper()
    b_norm = b.strip().upper()
    if len(a_norm) != 2 or len(b_norm) != 2:
        raise ValueError(
            f"TreatyDefinition.parties must be ISO-2 codes, got {parties!r}"
        )
    return tuple(sorted((a_norm, b_norm)))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Keyed by ``treaty_id``. Today only DBA-USA. The order in this dict
# dictates iteration order for callers that need stable output across
# treaties (e.g. final-legal-output ``treaties`` block when the
# Commit-6 schema migration lands).
TREATY_REGISTRY: dict[str, TreatyDefinition] = {
    "DBA_USA": TreatyDefinition(
        treaty_id="DBA_USA",
        display_name=(
            "Convention Between the United States of America and the "
            "Federal Republic of Germany for the Avoidance of Double "
            "Taxation and the Prevention of Fiscal Evasion with respect "
            "to Taxes on Income and Capital and to Certain Other Taxes "
            "(1989, as amended by the 2006 Protocol)"
        ),
        short_name="U.S.-Germany Income Tax Convention",
        parties=_normalize_parties(("DE", "US")),
        in_force_year=1989,
        last_protocol_year=2006,
        # ``elections.use_treaty_resourcing`` is the profile-level
        # election that drives DBA-USA Art. 23 / IRS Pub. 514 treaty
        # re-sourcing (``TREATY25-*`` stages). Distinct from
        # ``elections.us_filing_required`` which gates the entire U.S.
        # side; treaty enablement transitively depends on the U.S.
        # jurisdiction being enabled, enforced by
        # :func:`is_treaty_enabled`.
        enablement_flag="use_treaty_resourcing",
        enablement_default=True,
        rules_module="tax_pipeline.y2025.treaty_rules",
        stages_module="tax_pipeline.y2025.treaty_stages",
        law_module="tax_pipeline.y2025.treaty_law",
        # IRS-hosted bilingual treaty PDF (mirror of
        # ``DBA_USA_ART_10_URL`` in
        # ``tax_pipeline.y2025.treaty_law``; centralized at the law
        # module per I1).
        authority_url="https://www.irs.gov/pub/irs-trty/germany.pdf",
    ),
}


def get_treaty(treaty_id: str) -> TreatyDefinition:
    """Return the registry entry for a treaty_id.

    Unknown ids raise ``KeyError`` (fail closed per CLAUDE.md).
    """
    if treaty_id not in TREATY_REGISTRY:
        raise KeyError(
            f"Unknown treaty_id {treaty_id!r}. "
            f"Known treaties: {sorted(TREATY_REGISTRY)}"
        )
    return TREATY_REGISTRY[treaty_id]


def find_treaty_for_parties(party_a: str, party_b: str) -> TreatyDefinition | None:
    """Return the treaty (if any) covering the country pair.

    The lookup is order-independent: ``find_treaty_for_parties("DE",
    "US")`` and ``find_treaty_for_parties("us", "de")`` both resolve
    to the DBA-USA entry. Returns ``None`` when no treaty in the
    registry covers the pair, so callers can fail-soft when probing
    whether a treaty applies.
    """
    needle = _normalize_parties((party_a, party_b))
    for definition in TREATY_REGISTRY.values():
        if definition.parties == needle:
            return definition
    return None


def iter_treaties() -> tuple[TreatyDefinition, ...]:
    """Return all registered treaties in registration order."""
    return tuple(TREATY_REGISTRY.values())


def load_module(dotted_path: str) -> ModuleType:
    """Lazy-import a registry-referenced module.

    Centralised so tests can monkeypatch the loader if needed and so
    every dotted-path string in the registry uses the same import
    contract. Module-load errors propagate verbatim — fail closed.
    """
    return importlib.import_module(dotted_path)


def iter_enabled_treaties(profile: Mapping[str, Any]) -> tuple[TreatyDefinition, ...]:
    """Return registered treaties enabled by ``profile`` in registry order.

    Used by orchestration code that needs to drive the rule-graph
    executor across every enabled treaty without hardcoding
    ``"DBA_USA"``. Today the registry contains only DBA-USA so the
    return is either ``()`` (when the U.S. side is opted out) or
    ``(DBA_USA,)``. When a second treaty lands the iteration
    naturally fans out without changing call sites.

    The :func:`is_treaty_enabled` semantics (treaty flag AND both
    parties enabled) apply to every entry — so the U.S.-opt-out case
    (I13) is structurally short-circuited.
    """
    return tuple(
        definition
        for definition in TREATY_REGISTRY.values()
        if is_treaty_enabled(profile, definition.treaty_id)
    )


def treaty_stages_for(treaty_id: str) -> tuple[Any, ...]:
    """Return the declared LawStage tuple for ``treaty_id``.

    Lazy-loads the treaty's ``stages_module`` and calls its
    ``treaty_law_stages_<year>`` builder. Today only DBA-USA exposes
    a ``treaty_law_stages_2025`` factory; the helper is the
    registry-driven hand-off point for a future second treaty whose
    factory function will be discovered by name from its
    ``stages_module``.

    Discovery contract: the stages module must expose a public
    callable named ``treaty_law_stages_2025`` returning
    ``tuple[LawStage, ...]``. The 2025 year is the only year modeled
    today; when 2026 lands, the registry will need a per-year
    discovery field rather than a hardcoded function name.
    """
    definition = get_treaty(treaty_id)
    module = load_module(definition.stages_module)
    factory = getattr(module, "treaty_law_stages_2025", None)
    if factory is None:
        raise AttributeError(
            f"Treaty stages module {definition.stages_module!r} does not "
            "expose a 'treaty_law_stages_2025' factory."
        )
    return factory()


def is_treaty_enabled(profile: Mapping[str, Any], treaty_id: str) -> bool:
    """Return whether ``treaty_id`` is enabled by the profile.

    A treaty is enabled when:

    1. The profile's ``elections.<treaty.enablement_flag>`` is true
       (or absent and the treaty's ``enablement_default`` is true).
    2. **Both** parties' jurisdictions are enabled per
       :func:`tax_pipeline.y2025.cross_jurisdiction.is_jurisdiction_enabled`.

    Condition (2) preserves I13 (disabled-jurisdiction explicit
    absence): when the U.S. side is opted out under 26 U.S.C. § 6012,
    the DBA-USA treaty is structurally inapplicable — a treaty between
    US and X has no U.S.-side computation to feed when the U.S.
    pathway is off.

    The lazy import of :mod:`tax_pipeline.y2025.cross_jurisdiction`
    avoids a top-level circular import (cross_jurisdiction imports
    from tax_pipeline.jurisdictions; this module is consumed by
    cross_jurisdiction's siblings).
    """
    definition = get_treaty(treaty_id)
    elections = profile.get("elections", {}) if isinstance(profile, Mapping) else {}
    if not isinstance(elections, Mapping):
        flag_value: Any = definition.enablement_default
    else:
        flag_value = elections.get(definition.enablement_flag, definition.enablement_default)
    flag_enabled = _coerce_bool(flag_value, definition.enablement_default)
    if not flag_enabled:
        return False
    # Both parties must be enabled. Lazy import avoids cycles.
    from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

    for party in definition.parties:
        if not is_jurisdiction_enabled(profile, party):
            return False
    return True


def _coerce_bool(raw: Any, default: bool) -> bool:
    """Coerce a profile-loaded value to bool with the same contract as
    :func:`tax_pipeline.y2025.cross_jurisdiction._coerce_enablement_value`.

    Profile values may be native bool, the strings ``"true"``/``"false"``,
    or ``None``. Centralised here so the treaty enablement gate uses
    identical coercion to the jurisdiction enablement gate.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text in {"true", "1", "yes", "y"}:
            return True
        if text in {"false", "0", "no", "n", ""}:
            return False
    if raw is None:
        return default
    return bool(raw)


__all__ = [
    "TREATY_REGISTRY",
    "TreatyDefinition",
    "find_treaty_for_parties",
    "get_treaty",
    "is_treaty_enabled",
    "iter_enabled_treaties",
    "iter_treaties",
    "load_module",
    "treaty_stages_for",
]
