"""Cross-jurisdiction gating helpers for the 2025 engine.

This module is the single source of truth for whether the U.S. /
treaty / cross-jurisdiction-bridge pathways execute on a given run.
It exists so that the U.S.-only stages (``US25-*``), the treaty
re-sourcing stages (``TREATY25-*``), and the cross-jurisdiction
reconciliation stage (``BRIDGE25-FOREIGN-TAX-RECONCILIATION``) can be
short-circuited cleanly when the household has no U.S. filing
obligation under 26 U.S.C. § 6012 (e.g. a German resident with no
U.S. citizenship, no green card, and no U.S.-source items).

CLAUDE.md "tax-rule requirements": the posture flag is captured at the
intake-wizard layer (``tax_pipeline/intake/postures.py`` field
``elections.us_filing_required``) and persisted to ``config/profile.json``
under ``elections.us_filing_required``. Authority for the gate itself
is 26 U.S.C. § 6012 (general filing requirement) — when the user
opts out, none of the U.S. legal pathways apply, so running them
would either fabricate a tax position or fail closed mid-pipeline.

Proposal 2 (architecture review 2026-05-04): the U.S.-shaped helpers
(``read_us_filing_required`` / ``should_include_us_2025_stages`` etc.)
now generalise via the jurisdiction registry. Each
:class:`JurisdictionDefinition` carries an ``enablement_flag``
(profile-level boolean key) and ``enablement_default``; the
:func:`is_jurisdiction_enabled` helper reads either field by ISO-2
code. The legacy U.S.-named helpers stay (Proposal 9-style
"function names stay, internals generalize") so call sites in
``run_year.py`` / ``analysis_inputs.py`` / ``germany_model.py`` /
``final_legal_output.py`` / ``validate_workspace.py`` keep working.

Authority links:

- 26 U.S.C. § 6012 — Persons required to make returns of income.
  https://www.law.cornell.edu/uscode/text/26/6012
- DBA-USA 1989 — When the U.S. side does not run, treaty re-sourcing
  has no U.S.-side computation to feed and is therefore ``not_applicable``.
  https://www.irs.gov/pub/irs-trty/germany.pdf
- § 32d Abs. 5 EStG — The cross-jurisdiction reconciliation invariant
  asserts the foreign-tax components reconcile across the U.S. and
  German chains; with no U.S. side, the assertion has no
  cross-jurisdiction surface to enforce.
  https://www.gesetze-im-internet.de/estg/__32d.html
"""

from __future__ import annotations

from typing import Any, Mapping, Union

from tax_pipeline.jurisdictions import get_jurisdiction


# T2.3 / F3 — typed TaxpayerProfile is the migration-forward shape for
# profile data. The cross-jurisdiction helpers historically accepted a
# raw ``Mapping`` because every call site loaded ``profile.json``
# directly; they now also accept a :class:`TaxpayerProfile` so the
# orchestrator (``run_year.py``) and the final-output writer
# (``pipelines.y2025.final_legal_output.py``) can build the typed
# object once and thread it through without re-parsing. Non-migrated
# call sites (forms, germany_inputs, intake) keep passing dicts; the
# coercion path through :func:`is_jurisdiction_enabled` is identical
# for both shapes.
def _to_profile_mapping(profile: "ProfileLike") -> Mapping[str, Any]:
    """Normalise a profile-like argument to a Mapping.

    Local import to avoid a top-level cycle: ``tax_pipeline.profile``
    does not import from this module today (its
    ``TaxpayerProfile.is_jurisdiction_enabled`` is the inverse
    delegation), but keeping the import lazy preserves the boot-order
    invariant the registry-driven modules already maintain.
    """
    from tax_pipeline.profile import TaxpayerProfile

    if isinstance(profile, TaxpayerProfile):
        return profile.as_dict()
    return profile


# Public type alias for "anything the cross-jurisdiction helpers
# accept". Callers may pass a raw dict, a Mapping subclass, or a
# typed :class:`tax_pipeline.profile.TaxpayerProfile`.
ProfileLike = Union[Mapping[str, Any], "TaxpayerProfileProxy"]
# Forward reference; the real class is in tax_pipeline.profile and we
# avoid importing it at module top level to keep the boot graph clean.
TaxpayerProfileProxy = Any


# Retained for backward compatibility with existing call sites and
# tests. Equivalent to ``get_jurisdiction("US").enablement_default``;
# kept as a module-level constant so `from ... import
# US_FILING_REQUIRED_DEFAULT` continues to work.
US_FILING_REQUIRED_DEFAULT = get_jurisdiction("US").enablement_default
"""Default for ``elections.us_filing_required`` when the profile omits
it. ``True`` preserves backward compatibility with the existing
U.S.-citizen-in-Germany demo workspace and with every test fixture
materialized before the posture was wired into the engine.
"""


def _coerce_enablement_value(raw: Any, default: bool) -> bool:
    """Coerce a profile-loaded enablement value to a bool.

    Profile values may arrive as native bool (intake wizard, JSON),
    string (``"true"`` / ``"false"`` from the legacy CSV-sync path),
    or ``None`` (omitted). Centralised here so every per-jurisdiction
    enablement read uses the same coercion contract.
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


def is_jurisdiction_enabled(profile: ProfileLike, code: str) -> bool:
    """Return whether jurisdiction ``code`` is enabled by the profile.

    Reads ``elections.<enablement_flag>`` from ``profile`` where the
    flag name comes from
    :class:`tax_pipeline.jurisdictions.JurisdictionDefinition`. Falls
    back to ``enablement_default`` when the value is absent or not a
    coercible bool. Coerces string forms (``"true"``/``"false"``)
    that survive the legacy CSV-sync path.

    T2.3 / F3: ``profile`` may now also be a typed
    :class:`tax_pipeline.profile.TaxpayerProfile`; it is normalised to
    a dict view before the lookup so the legacy coercion contract
    remains identical for both shapes.
    """
    definition = get_jurisdiction(code)
    mapping = _to_profile_mapping(profile)
    elections = mapping.get("elections", {})
    if not isinstance(elections, Mapping):
        return definition.enablement_default
    raw = elections.get(definition.enablement_flag, definition.enablement_default)
    return _coerce_enablement_value(raw, definition.enablement_default)


def read_us_filing_required(profile: ProfileLike) -> bool:
    """Return ``elections.us_filing_required`` from ``profile`` (default True).

    Coerces non-bool values (e.g. CSV-derived strings ``"true"`` /
    ``"false"`` that survive the legacy CSV-sync path) so the gate
    behaves identically whether the value was set through the intake
    wizard's posture endpoint, the legacy ``config/profile.json``, or
    the ``config/elections.csv`` round-trip.

    P2 internals: delegates to :func:`is_jurisdiction_enabled` keyed
    on the U.S. registry entry.

    Authority: 26 U.S.C. § 6012 — when the user attests they have no
    U.S. filing obligation, the engine treats the U.S. pathway as
    inapplicable rather than producing a partial U.S. return.
    """
    return is_jurisdiction_enabled(profile, "US")


def should_include_bridge_2025_stages(profile: ProfileLike) -> bool:
    """Return whether ``BRIDGE25-FOREIGN-TAX-RECONCILIATION`` runs.

    The bridge stage asserts that four independently sourced
    foreign-tax components (1099 input, German bank certificate
    credited bucket, German bank certificate not-yet-credited bucket,
    treaty re-sourcing add-on) reconcile to ``capital.explicit_foreign_tax_total``.
    The treaty add-on component is only meaningful when the U.S.
    pathway runs; without it the bridge has no cross-jurisdiction
    surface. Per § 32d Abs. 5 EStG the per-Posten cap still applies
    inside the German capital rule graph — the bridge is the
    cross-jurisdiction tie, which is moot when only one jurisdiction
    files.
    """
    return is_jurisdiction_enabled(profile, "US")


def should_include_treaty_2025_stages(profile: ProfileLike) -> bool:
    """Return whether the ``TREATY25-*`` stages run.

    Treaty re-sourcing under DBA-USA Art. 23 / 26 U.S.C. § 904(d) is a
    U.S.-side computation: it allocates German source tax against U.S.
    Form 1116 limitations. With no U.S. return, the treaty stages have
    no consumer.

    P3 (architecture review §5 Proposal 3): the function name stays for
    backward compatibility with call sites in ``run_year.py`` /
    ``rule_narrative_packets.py``, but the body now delegates to
    :func:`tax_pipeline.treaties.is_treaty_enabled` keyed on the
    DBA-USA registry entry. ``is_treaty_enabled("DBA_USA")`` already
    requires both parties (DE, US) to be enabled, so the U.S.-opt-out
    case (I13) is still short-circuited correctly. The treaty's own
    ``enablement_flag = "use_treaty_resourcing"`` is now also
    consulted as a hard gate — pre-P3 the U.S. rule graph soft-gated
    on this flag inside individual rule bodies (see e.g.
    ``treaty_rules.treaty25_15_us_source_dividends`` returning
    ``not_applicable``); the stages still run and emit
    ``not_applicable`` outputs when the flag is false. We preserve
    that behaviour here by gating the stage-list inclusion on the
    union (US enabled) rather than the strict AND that
    ``is_treaty_enabled`` enforces — the treaty rule bodies are the
    canonical place to interpret ``use_treaty_resourcing`` per
    fingerprint stability.
    """
    # Backwards-compatible behaviour: the stage list is included
    # whenever the U.S. side runs. The treaty's own resourcing-
    # election flag is consulted *inside* the treaty rule bodies (which
    # emit ``not_applicable`` outputs when it is false), preserving
    # fingerprint stability of the executed-stages list across pre-P3
    # and post-P3 runs.
    from tax_pipeline.treaties import get_treaty

    treaty = get_treaty("DBA_USA")
    # Both parties must be enabled — equivalent to "U.S. enabled" today
    # since DE is default-enabled and has no opt-out surface, but
    # registry-driven so a future DE opt-out would also short-circuit.
    for party in treaty.parties:
        if not is_jurisdiction_enabled(profile, party):
            return False
    return True


def should_include_us_2025_stages(profile: ProfileLike) -> bool:
    """Return whether the ``US25-*`` stages run.

    Mirror of :func:`should_include_treaty_2025_stages` for the
    main U.S. assessment graph. Profile-level ``jurisdictions.usa.enabled``
    can also disable the U.S. side; when ``us_filing_required`` is
    false we treat that as the canonical opt-out signal because it is
    the user-facing posture (whereas ``jurisdictions.usa.enabled`` is
    a workspace-config knob).
    """
    return is_jurisdiction_enabled(profile, "US")


__all__ = [
    "US_FILING_REQUIRED_DEFAULT",
    "is_jurisdiction_enabled",
    "read_us_filing_required",
    "should_include_bridge_2025_stages",
    "should_include_treaty_2025_stages",
    "should_include_us_2025_stages",
]
