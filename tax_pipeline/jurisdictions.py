"""Jurisdiction registry — Proposal 2 (architecture review 2026-05-04).

Today, the orchestration layer hardcodes the names "germany" and "us"
in many places: ``postures/__init__.py`` keys its registry on the
literal strings, ``year_registry.YearDefinition`` has named slots
``germany_modules`` / ``usa_modules``, ``cross_jurisdiction.py`` reads
``elections.us_filing_required`` directly, ``paths.YearPaths`` carries
named ``germany_forms_root`` / ``usa_forms_root`` fields, and the
form renderers tag their LegalValue boundaries with module-level
``GERMANY_COUNTRY = "DE"`` constants.

Adding a third country (UK, FR, ...) is therefore a multi-file edit
across orchestration, paths, posture, renderer, audit modules. P2
re-shapes "country" into a data dimension on a single registry, so
the orchestration code iterates jurisdictions instead of branching
on names.

This module is **year-agnostic** by deliberate design: the registry
maps an ISO country code to its renderer, audit, posture, and
enablement metadata, none of which is year-specific. Year-specific
module dotted paths (rule modules, stage modules) live on
``YearDefinition.jurisdiction_modules`` keyed by the same code.

Invariants this module preserves:
  * I13 (disabled-jurisdiction explicit absence): the per-jurisdiction
    ``enablement_flag`` field replaces the literal
    ``elections.us_filing_required`` read so the disabled-jurisdiction
    posture is registry-driven and extensible to UK/CH/VN/IN.
  * I1 (no legal constants outside law modules): nothing here is a
    legal constant. Currency mapping points to the
    ``tax_pipeline.core.money.Currency`` enum where the canonical list
    lives.

References:
  * Architecture review §5 Proposal 2.
  * Architecture review §4 P5 (closed posture registry).
  * 26 U.S.C. § 6012 — gives the U.S. enablement flag its legal
    posture authority. Other jurisdictions will document their own
    filing-obligation gates (UK SA1, DE § 25 Abs. 3 EStG, etc.) when
    their ``JurisdictionDefinition`` rows land.
    https://www.law.cornell.edu/uscode/text/26/6012
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from types import ModuleType

from tax_pipeline.core.money import Currency


@dataclass(frozen=True)
class JurisdictionDefinition:
    """Static metadata describing one filing jurisdiction.

    Attributes:
      code: ISO 3166-1 alpha-2 uppercase code ("DE", "US"). Stable
          identifier used as the registry key and as the country tag
          in ``LegalValue`` provenance / ``_provenance.form_lines``.
      display_name: Human-readable English name used in narrative and
          renderer copy ("Germany", "United States").
      iso_alpha2: Lowercase ISO code ("de", "us"). Same as ``code``
          but lowercase, used to construct the ISO-coded raw bucket
          path under ``raw/jurisdictions/<iso>/`` (Proposal 8).
      raw_bucket: Canonical bucket name (post-P8) for jurisdiction-
          bound documents. Equal to ``iso_alpha2`` in the new layout.
      raw_bucket_legacy: Pre-P8 flat bucket name ("germany", "us")
          retained for backward-compatible reads of unmigrated
          workspaces; see ``paths.JURISDICTION_LEGACY_NAMES``.
      primary_currency: The Currency in which form lines and final
          tax / refund amounts are denominated.
      enablement_flag: Profile-level boolean key gating this
          jurisdiction's pathway. ``elections.<flag>`` is read by the
          orchestrator (e.g. "us_filing_required" for the U.S.
          pathway under 26 U.S.C. § 6012).
      enablement_default: Default value when the flag is absent from
          the profile. Preserves backward compatibility with workspaces
          materialized before the flag existed.
      posture_module: Dotted path to the posture submodule
          ("tax_pipeline.postures.germany"). Lazy-imported.
      forms_module: Dotted path to the form renderer module.
      legal_audit_module: Dotted path to the legal-audit package
          builder module.
      rules_year_namespace: Dotted path to the per-year rule package
          ("tax_pipeline.y2025"). Year-specific consumers join this
          with the year code to address rule modules.
      posture_registry_key: The legacy registry key used in
          ``postures/__init__.py`` and in ``profile.jurisdiction``.
          Often equal to lowercased ``display_name`` ("germany",
          "usa"). Preserved as data so the registry rewrite does not
          require renaming the on-disk profile fields.
    """

    code: str
    display_name: str
    iso_alpha2: str
    raw_bucket: str
    raw_bucket_legacy: str
    primary_currency: Currency
    enablement_flag: str
    enablement_default: bool
    posture_module: str
    forms_module: str
    legal_audit_module: str
    rules_year_namespace: str
    posture_registry_key: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
# Keyed by ISO-2 uppercase code. Order is significant for callers that
# iterate the registry to produce stable output (germany_model first,
# us_model second, mirroring ``YearDefinition.pipeline_modules``).
JURISDICTION_REGISTRY: dict[str, JurisdictionDefinition] = {
    "DE": JurisdictionDefinition(
        code="DE",
        display_name="Germany",
        iso_alpha2="de",
        raw_bucket="de",
        raw_bucket_legacy="germany",
        primary_currency=Currency.EUR,
        # § 25 Abs. 3 EStG keeps Germany on a default-enabled posture
        # so unmigrated workspaces continue to compute the German
        # return; the engine has no per-jurisdiction "Germany filing
        # not required" surface today, so the flag is a placeholder
        # that always evaluates to its default. Adding such a surface
        # later is a one-line registry edit.
        # https://www.gesetze-im-internet.de/estg/__25.html
        enablement_flag="germany_filing_required",
        enablement_default=True,
        posture_module="tax_pipeline.postures.germany",
        forms_module="tax_pipeline.forms.germany",
        legal_audit_module="tax_pipeline.legal_audit.germany",
        rules_year_namespace="tax_pipeline.y2025",
        posture_registry_key="germany",
    ),
    "US": JurisdictionDefinition(
        code="US",
        display_name="United States",
        iso_alpha2="us",
        raw_bucket="us",
        raw_bucket_legacy="us",
        primary_currency=Currency.USD,
        # 26 U.S.C. § 6012 — Persons required to make returns of income.
        # The user-facing posture flag is ``elections.us_filing_required``;
        # I13 (disabled-jurisdiction explicit absence) requires the
        # engine to skip every US25-* / TREATY25-* / BRIDGE25-* stage
        # when this flag is false.
        # https://www.law.cornell.edu/uscode/text/26/6012
        enablement_flag="us_filing_required",
        enablement_default=True,
        posture_module="tax_pipeline.postures.usa",
        forms_module="tax_pipeline.forms.usa",
        legal_audit_module="tax_pipeline.legal_audit.usa",
        rules_year_namespace="tax_pipeline.y2025",
        posture_registry_key="usa",
    ),
}


def get_jurisdiction(code: str) -> JurisdictionDefinition:
    """Return the registry entry for an ISO-2 country code.

    The code is normalised to uppercase before lookup. Unknown codes
    raise ``KeyError`` so callers fail closed rather than silently
    producing a default jurisdiction (CLAUDE.md "fail closed" rule).
    """
    normalized = code.strip().upper()
    if normalized not in JURISDICTION_REGISTRY:
        raise KeyError(
            f"Unknown jurisdiction code {code!r}. "
            f"Known codes: {sorted(JURISDICTION_REGISTRY)}"
        )
    return JURISDICTION_REGISTRY[normalized]


def get_jurisdiction_by_posture_key(posture_key: str) -> JurisdictionDefinition:
    """Return the registry entry whose ``posture_registry_key`` matches.

    Used by the posture registry and the orchestrator's
    ``profile.jurisdictions.<key>.enabled`` reader, which both still
    use the legacy lowercase-display-name keys ("germany", "usa").
    """
    normalized = posture_key.strip().lower()
    for definition in JURISDICTION_REGISTRY.values():
        if definition.posture_registry_key == normalized:
            return definition
    raise KeyError(
        f"No jurisdiction registered with posture_registry_key={posture_key!r}. "
        f"Known keys: {sorted(d.posture_registry_key for d in JURISDICTION_REGISTRY.values())}"
    )


def iter_jurisdictions() -> tuple[JurisdictionDefinition, ...]:
    """Return all registered jurisdictions in registration order."""
    return tuple(JURISDICTION_REGISTRY.values())


def load_module(dotted_path: str) -> ModuleType:
    """Lazy-import a registry-referenced module.

    Centralised so tests can monkeypatch the loader if needed and so
    every dotted-path string in the registry uses the same import
    contract. Module-load errors propagate verbatim — fail closed.
    """
    return importlib.import_module(dotted_path)


__all__ = [
    "JurisdictionDefinition",
    "JURISDICTION_REGISTRY",
    "get_jurisdiction",
    "get_jurisdiction_by_posture_key",
    "iter_jurisdictions",
    "load_module",
]
