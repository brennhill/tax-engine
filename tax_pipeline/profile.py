"""Typed loader for ``years/<ws>/config/profile.json``.

F3 (W2.B / T2.3) — promoted in
`.review/2026-05-10-platform-flexibility-review.md` §91-97 after the
2026-05-09 Anlage SO incident: the brenn workspace profile carries
``kap_lines: ["17", "19", "20", "21", "23", "24", "41"]`` plus
``anlage_n_label`` / ``anlage_kap_label`` ELSTER strings *inside the
user-facing profile*. The Anlage SO incident was a wrong line label;
the profile is the most-edited human surface and currently has no
schema. F3's value just doubled.

This module is the structural defense:

  * :class:`TaxpayerProfile` is a frozen dataclass capturing every
    top-level profile field plus the nested sub-objects we exercise
    (elections, jurisdictions, household, taxpayer, spouse, german
    return person slots).
  * :meth:`TaxpayerProfile.from_json` parses ``config/profile.json``
    and raises ``ValueError`` on:
      - unknown top-level keys (typo defense);
      - unknown ``elections.<key>`` (closed set sourced from
        :data:`tax_pipeline.jurisdictions.JURISDICTION_REGISTRY` and
        :data:`tax_pipeline.treaties.TREATY_REGISTRY` enablement flags
        plus a small set of additional well-known electives);
      - ``person_slots[*].kap_lines`` entries that are not declared
        as ``line_id`` in ``tax_pipeline/forms/schemas/anlage_kap.toml``
        (this is the exact defect-class the 2026-05-10 review called
        out: a typo'd Zeile number in a hand-edited profile would
        survive year-over-year today);
      - missing required fields;
      - schema_version mismatch.

Stdlib-only (``dataclasses``, ``tomllib``, ``json``, ``typing``).

The loader is intentionally narrow: it validates structure on read and
exposes a typed surface for the orchestrator. Non-migrated readers
that still call ``json.loads(profile_path.read_text(...))`` continue
to work — :meth:`TaxpayerProfile.as_dict` reproduces the on-disk
shape verbatim for those sites.

The ``schema_version`` field is a code-level invariant: when ``1``
the layout below is canonical; future schema breaks increment the
version and add a migrator. The version is stored on the typed
object but is **not** propagated into derivative artifacts that
embed the profile (e.g. ``final-legal-output.json`` strips it before
the embed, see :func:`profile_dict_for_embedding`), so adding the
field to disk does not drift the workspace-output md5s pinned in
``tests/y_agnostic/test_money_type.py``.

Authority for the per-jurisdiction enablement keys lives in the
jurisdiction / treaty registries; this module imports those for the
closed-set check rather than maintaining a parallel list.
"""
from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


# Schema version of the layout below. Bump when a backward-incompatible
# layout change ships; the matching migrator lives in this module under
# a ``_migrate_v<N>_to_v<N+1>`` function (no migrators today).
PROFILE_SCHEMA_VERSION: int = 1


# Path to the Anlage KAP schema, used to validate ``kap_lines`` entries.
# Keeping the relative path centralised so a future schemas/ relocation
# is one edit.
_ANLAGE_KAP_SCHEMA_PATH = (
    Path(__file__).parent / "forms" / "schemas" / "anlage_kap.toml"
)


# Top-level keys allowed on the profile. Adding a new top-level field
# requires extending this set *and* the dataclass below — that paired
# edit is the structural typo defense.
_ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "profile",
        "description",
        "tax_year",
        "employment_country",
        "employment_city",
        "primary_tax_residence",
        "us_citizen_or_long_term_resident",
        "german_return",
        "us_return",
        "investment_defaults",
        "taxpayer",
        "spouse",
        "household",
        "jurisdictions",
        "elections",
        "raw_buckets",
    }
)


# Elections keys outside the registry-derived enablement flags. The
# closed set is built dynamically at validation time so that a new
# jurisdiction / treaty in the registries automatically widens the
# allowed set; the hand-maintained additions below cover everything
# else that today's three workspaces use.
_NON_ENABLEMENT_ELECTIONS: frozenset[str] = frozenset(
    {
        # Capital / income method elections.
        "us_ftc_method",  # "accrued" / "paid" — Form 1116 election under § 905.
        "elect_section_911_feie",  # 26 U.S.C. § 911 election.
        "elect_joint_return_with_nra_spouse",  # 26 U.S.C. § 6013(g) election.
        # German per-person elections.
        "germany_kirchensteuer_membership",  # § 51a EStG.
        # Treaty/totalization disclosures.
        "acknowledges_totalization_agreement_germany_us",
    }
)


# Allowed nested keys, surfaced for typo defense. Nested unstructured
# bags (``raw_buckets`` list, ``person_slots`` per-slot extra notes)
# don't go through this check — see the dataclass below for the
# precise structure.
_ALLOWED_JURISDICTION_KEYS: frozenset[str] = frozenset({"enabled", "filing_posture"})
_ALLOWED_HOUSEHOLD_KEYS: frozenset[str] = frozenset(
    {"marital_status_on_dec_31", "germany_filing_status", "us_filing_status"}
)
_ALLOWED_TAXPAYER_KEYS: frozenset[str] = frozenset(
    {"name", "citizenship", "germany_tax_resident"}
)
_ALLOWED_SPOUSE_KEYS: frozenset[str] = frozenset({"name", "us_tax_status"})
_ALLOWED_INVESTMENT_DEFAULTS_KEYS: frozenset[str] = frozenset(
    {
        "primary_broker_country",
        "other_stock_countries_allowed",
        "crypto_supported",
        "real_estate_supported",
    }
)
_ALLOWED_US_RETURN_KEYS: frozenset[str] = frozenset(
    {
        "required",
        "default_filing_status_if_spouse_is_nonresident_alien",
        "treaty_resourcing_common",
    }
)
_ALLOWED_GERMAN_RETURN_KEYS: frozenset[str] = frozenset(
    {
        "required",
        "joint_assessment_prerequisites",
        "person_slots",
        "assume_joint_assessment_if_married",
    }
)
_ALLOWED_JOINT_PREREQ_KEYS: frozenset[str] = frozenset(
    {
        "married_or_registered_partners",
        "not_permanently_separated",
        "unrestricted_tax_liability",
        "joint_election",
        "eligibility_existed_at_start_or_arose_during_year",
    }
)
_ALLOWED_PERSON_SLOT_KEYS: frozenset[str] = frozenset(
    {
        "slot",
        "order_label",
        "display_name",
        "owner",
        "anlage_n_label",
        "anlage_kap_label",
        "kap_lines",
        "kap_raw_lines",
        "kap_posture",
        "kap_notes",
    }
)


def _load_anlage_kap_line_ids(schema_path: Path = _ANLAGE_KAP_SCHEMA_PATH) -> frozenset[str]:
    """Return the set of declared ``line_id`` values in the Anlage KAP TOML.

    Loaded once at validation time (no module-level cache so test
    monkeypatching of the schema path remains effective). Stdlib-only:
    ``tomllib`` is the parser.
    """
    if not schema_path.exists():
        raise FileNotFoundError(
            f"Anlage KAP schema not found at {schema_path}; cannot validate "
            "person_slots[*].kap_lines without it."
        )
    with schema_path.open("rb") as fh:
        data = tomllib.load(fh)
    lines = data.get("lines", [])
    if not isinstance(lines, list):
        raise ValueError(
            f"Anlage KAP schema at {schema_path} has malformed 'lines' array."
        )
    return frozenset(
        str(entry["line_id"])
        for entry in lines
        if isinstance(entry, dict) and "line_id" in entry
    )


def _allowed_elections_keys() -> frozenset[str]:
    """Return the closed set of allowed ``elections.<key>`` names.

    Sourced from:
      * :data:`tax_pipeline.jurisdictions.JURISDICTION_REGISTRY` —
        every jurisdiction's ``enablement_flag``.
      * :data:`tax_pipeline.treaties.TREATY_REGISTRY` — every treaty's
        ``enablement_flag``.
      * :data:`_NON_ENABLEMENT_ELECTIONS` — hand-maintained other electives.

    Imports are local so this module stays importable from very early
    boot paths (the registries import this module's siblings).
    """
    from tax_pipeline.jurisdictions import JURISDICTION_REGISTRY
    from tax_pipeline.treaties import TREATY_REGISTRY

    keys: set[str] = set(_NON_ENABLEMENT_ELECTIONS)
    for definition in JURISDICTION_REGISTRY.values():
        keys.add(definition.enablement_flag)
    for definition in TREATY_REGISTRY.values():
        keys.add(definition.enablement_flag)
    return frozenset(keys)


def _require_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}: expected JSON object, got {type(value).__name__}")
    return value


def _require_str(value: Any, *, context: str, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context}: expected string, got {type(value).__name__}")
    if not allow_empty and not value.strip():
        raise ValueError(f"{context}: must be a non-empty string")
    return value


def _require_bool(value: Any, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{context}: expected boolean, got {type(value).__name__}")
    return value


def _reject_unknown(
    mapping: Mapping[str, Any],
    allowed: frozenset[str],
    *,
    context: str,
) -> None:
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        raise ValueError(
            f"{context}: unknown key(s) {unknown!r}; allowed keys: {sorted(allowed)!r}"
        )


@dataclass(frozen=True, slots=True)
class PersonSlot:
    """One entry under ``german_return.person_slots``.

    Models the per-person Anlage configuration that the renderer
    consumes. ``kap_lines`` is validated against the Anlage KAP TOML
    schema's declared ``line_id`` set at load time.
    """

    slot: str
    order_label: str
    display_name: str
    # ``owner`` may be ``None`` in the freshly-scaffolded state
    # (``DEFAULT_PROFILE`` in scaffold_year ships ``None`` placeholders;
    # the wizard fills it in before the engine runs the legal core).
    owner: str | None
    anlage_n_label: str
    anlage_kap_label: str
    kap_lines: tuple[str, ...]
    kap_raw_lines: tuple[str, ...]
    kap_posture: str
    kap_notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        """Return the on-disk dict shape for this slot."""
        return {
            "slot": self.slot,
            "order_label": self.order_label,
            "display_name": self.display_name,
            "owner": self.owner,
            "anlage_n_label": self.anlage_n_label,
            "anlage_kap_label": self.anlage_kap_label,
            "kap_lines": list(self.kap_lines),
            "kap_raw_lines": list(self.kap_raw_lines),
            "kap_posture": self.kap_posture,
            "kap_notes": list(self.kap_notes),
        }


@dataclass(frozen=True, slots=True)
class GermanReturn:
    """The ``german_return`` block."""

    required: bool
    person_slots: tuple[PersonSlot, ...]
    assume_joint_assessment_if_married: bool
    joint_assessment_prerequisites: Mapping[str, bool]

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "required": self.required,
            "assume_joint_assessment_if_married": self.assume_joint_assessment_if_married,
            "person_slots": [slot.as_dict() for slot in self.person_slots],
        }
        if self.joint_assessment_prerequisites:
            out["joint_assessment_prerequisites"] = dict(
                self.joint_assessment_prerequisites
            )
        return out


@dataclass(frozen=True, slots=True)
class USReturn:
    """The ``us_return`` block."""

    required: bool
    default_filing_status_if_spouse_is_nonresident_alien: str
    treaty_resourcing_common: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "default_filing_status_if_spouse_is_nonresident_alien": (
                self.default_filing_status_if_spouse_is_nonresident_alien
            ),
            "treaty_resourcing_common": self.treaty_resourcing_common,
        }


@dataclass(frozen=True, slots=True)
class JurisdictionConfig:
    """One entry under ``jurisdictions.<name>``."""

    enabled: bool
    filing_posture: str

    def as_dict(self) -> dict[str, Any]:
        return {"enabled": self.enabled, "filing_posture": self.filing_posture}


@dataclass(frozen=True, slots=True)
class InvestmentDefaults:
    primary_broker_country: str
    other_stock_countries_allowed: bool
    crypto_supported: bool
    real_estate_supported: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_broker_country": self.primary_broker_country,
            "other_stock_countries_allowed": self.other_stock_countries_allowed,
            "crypto_supported": self.crypto_supported,
            "real_estate_supported": self.real_estate_supported,
        }


@dataclass(frozen=True, slots=True)
class Taxpayer:
    name: str
    citizenship: tuple[str, ...]
    germany_tax_resident: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "citizenship": list(self.citizenship),
            "germany_tax_resident": self.germany_tax_resident,
        }


@dataclass(frozen=True, slots=True)
class Spouse:
    name: str
    us_tax_status: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "us_tax_status": self.us_tax_status}


@dataclass(frozen=True, slots=True)
class Household:
    marital_status_on_dec_31: str
    germany_filing_status: str
    us_filing_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "marital_status_on_dec_31": self.marital_status_on_dec_31,
            "germany_filing_status": self.germany_filing_status,
            "us_filing_status": self.us_filing_status,
        }


@dataclass(frozen=True, slots=True)
class TaxpayerProfile:
    """Typed view of ``years/<ws>/config/profile.json``.

    Built by :meth:`from_json`. All fields are required except for the
    ones explicitly noted as optional. The dataclass is frozen and
    uses ``slots=True`` so a typo in a field name fails at attribute
    access time rather than silently creating a new attribute.

    Use :meth:`as_dict` to round-trip back to the on-disk JSON shape
    for non-migrated readers (forms/germany.py, scaffold_year.py,
    intake/workspace.py — they still consume raw dicts; the typed
    object can re-materialise the same shape they expect).
    """

    # Plumbing metadata. ``schema_version`` is a code-level invariant
    # validated at load and stripped from the on-disk-equivalent dict
    # returned by :meth:`as_dict` so derivative artifacts (the
    # ``germany.forms.profile`` block embedded in
    # ``final-legal-output.json``) preserve their byte shape across
    # this module landing.
    schema_version: int = PROFILE_SCHEMA_VERSION

    # Identity / description.
    profile: str = ""
    description: str = ""
    tax_year: int | None = None

    # Core taxpayer geography.
    employment_country: str = ""
    employment_city: str = ""
    primary_tax_residence: str = ""
    us_citizen_or_long_term_resident: bool = False

    # Per-return sections.
    german_return: GermanReturn | None = None
    us_return: USReturn | None = None

    # Investment context.
    investment_defaults: InvestmentDefaults | None = None

    # Filer + spouse identity.
    taxpayer: Taxpayer | None = None
    spouse: Spouse | None = None

    # Household + jurisdiction posture.
    household: Household | None = None
    jurisdictions: Mapping[str, JurisdictionConfig] = field(default_factory=dict)

    # Election bag. Closed set validated at load time; the dict
    # preserves the on-disk values so the existing
    # ``read_us_filing_required`` coercion path keeps working
    # bit-for-bit.
    elections: Mapping[str, Any] = field(default_factory=dict)

    # Raw bucket list — unstructured by design (it's a list of free-
    # form bucket names that the workspace lays out under raw/).
    raw_buckets: tuple[str, ...] = ()

    # ---- public methods --------------------------------------------------

    @classmethod
    def from_json(cls, path: Path) -> "TaxpayerProfile":
        """Load and validate a profile from ``path``.

        Raises ``ValueError`` on any structural defect: unknown key,
        wrong type, invalid kap_lines, schema version mismatch.
        """
        if not isinstance(path, Path):
            path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Profile JSON not found at {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in profile at {path}: {exc}") from exc
        return cls.from_dict(raw, source=str(path))

    @classmethod
    def from_dict(
        cls,
        raw: Any,
        *,
        source: str = "<dict>",
    ) -> "TaxpayerProfile":
        """Validate a raw dict and return a :class:`TaxpayerProfile`.

        Separated from :meth:`from_json` so tests can drive the
        validation contract without writing JSON to disk.
        """
        mapping = _require_mapping(raw, context=f"profile {source}")
        _reject_unknown(
            mapping, _ALLOWED_TOP_LEVEL_KEYS, context=f"profile {source}"
        )

        schema_version = mapping.get("schema_version", PROFILE_SCHEMA_VERSION)
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise ValueError(
                f"profile {source}: schema_version must be an int, "
                f"got {type(schema_version).__name__}"
            )
        if schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(
                f"profile {source}: schema_version={schema_version} not supported; "
                f"this build only loads schema_version={PROFILE_SCHEMA_VERSION}"
            )

        # ---- top-level scalars --------------------------------------------
        profile_name = _require_str(
            mapping.get("profile", ""), context=f"profile {source} .profile"
        )
        description = _require_str(
            mapping.get("description", ""), context=f"profile {source} .description"
        )
        tax_year_raw = mapping.get("tax_year")
        if tax_year_raw is not None and (
            not isinstance(tax_year_raw, int) or isinstance(tax_year_raw, bool)
        ):
            raise ValueError(
                f"profile {source} .tax_year: must be an int, "
                f"got {type(tax_year_raw).__name__}"
            )
        employment_country = _require_str(
            mapping.get("employment_country", ""),
            context=f"profile {source} .employment_country",
        )
        employment_city = _require_str(
            mapping.get("employment_city", ""),
            context=f"profile {source} .employment_city",
        )
        primary_tax_residence = _require_str(
            mapping.get("primary_tax_residence", ""),
            context=f"profile {source} .primary_tax_residence",
        )
        us_citizen = _require_bool(
            mapping.get("us_citizen_or_long_term_resident", False),
            context=f"profile {source} .us_citizen_or_long_term_resident",
        )

        # ---- nested sections ---------------------------------------------
        german_return = _parse_german_return(
            mapping.get("german_return"), source=source
        )
        us_return = _parse_us_return(mapping.get("us_return"), source=source)
        investment_defaults = _parse_investment_defaults(
            mapping.get("investment_defaults"), source=source
        )
        taxpayer = _parse_taxpayer(mapping.get("taxpayer"), source=source)
        spouse = _parse_spouse(mapping.get("spouse"), source=source)
        household = _parse_household(mapping.get("household"), source=source)
        jurisdictions = _parse_jurisdictions(
            mapping.get("jurisdictions"), source=source
        )
        elections = _parse_elections(mapping.get("elections"), source=source)

        raw_buckets_raw = mapping.get("raw_buckets", [])
        if not isinstance(raw_buckets_raw, list) or any(
            not isinstance(entry, str) for entry in raw_buckets_raw
        ):
            raise ValueError(
                f"profile {source} .raw_buckets: must be a list of strings"
            )

        return cls(
            schema_version=schema_version,
            profile=profile_name,
            description=description,
            tax_year=tax_year_raw,
            employment_country=employment_country,
            employment_city=employment_city,
            primary_tax_residence=primary_tax_residence,
            us_citizen_or_long_term_resident=us_citizen,
            german_return=german_return,
            us_return=us_return,
            investment_defaults=investment_defaults,
            taxpayer=taxpayer,
            spouse=spouse,
            household=household,
            jurisdictions=jurisdictions,
            elections=elections,
            raw_buckets=tuple(raw_buckets_raw),
        )

    def as_dict(self, *, include_schema_version: bool = False) -> dict[str, Any]:
        """Return the on-disk JSON shape for this profile.

        ``include_schema_version=False`` (default) omits the
        ``schema_version`` key so derivative artifacts that embed the
        profile (e.g. ``final-legal-output.json``) preserve their
        pre-F3 byte shape — i.e. the workspace-output md5s pinned in
        ``tests/y_agnostic/test_money_type.py``. Pass ``include_schema_version=True``
        when re-writing ``config/profile.json`` so the on-disk file
        keeps the schema marker.
        """
        out: dict[str, Any] = {}
        if include_schema_version:
            out["schema_version"] = self.schema_version
        # Maintain the same key order as the on-disk files so that
        # ``json.dumps(profile.as_dict(), indent=2)`` is diff-stable
        # with the canonical workspace layout.
        if self.profile:
            out["profile"] = self.profile
        if self.description:
            out["description"] = self.description
        if self.tax_year is not None:
            out["tax_year"] = self.tax_year
        out["employment_country"] = self.employment_country
        out["employment_city"] = self.employment_city
        out["primary_tax_residence"] = self.primary_tax_residence
        out["us_citizen_or_long_term_resident"] = self.us_citizen_or_long_term_resident
        if self.german_return is not None:
            out["german_return"] = self.german_return.as_dict()
        if self.us_return is not None:
            out["us_return"] = self.us_return.as_dict()
        if self.investment_defaults is not None:
            out["investment_defaults"] = self.investment_defaults.as_dict()
        if self.taxpayer is not None:
            out["taxpayer"] = self.taxpayer.as_dict()
        if self.spouse is not None:
            out["spouse"] = self.spouse.as_dict()
        if self.household is not None:
            out["household"] = self.household.as_dict()
        if self.jurisdictions:
            out["jurisdictions"] = {
                key: cfg.as_dict() for key, cfg in self.jurisdictions.items()
            }
        if self.elections:
            out["elections"] = dict(self.elections)
        if self.raw_buckets:
            out["raw_buckets"] = list(self.raw_buckets)
        return out

    # ---- convenience accessors -------------------------------------------

    def is_jurisdiction_enabled(self, code: str) -> bool:
        """Return whether jurisdiction ``code`` is enabled.

        Delegates to :func:`tax_pipeline.y2025.cross_jurisdiction.is_jurisdiction_enabled`
        so the typed object and the dict-based reader resolve identically
        (including the string-coercion path for legacy CSV-synced
        ``"true"`` / ``"false"`` values).
        """
        from tax_pipeline.y2025.cross_jurisdiction import is_jurisdiction_enabled

        return is_jurisdiction_enabled(self.as_dict(), code)

    def kap_lines_for(self, slot: str) -> tuple[str, ...]:
        """Return the configured Anlage KAP line_ids for a person slot.

        Raises ``KeyError`` if no slot with that name is configured.
        """
        if self.german_return is None:
            raise KeyError(f"No german_return configured; cannot resolve slot {slot!r}")
        for entry in self.german_return.person_slots:
            if entry.slot == slot:
                return entry.kap_lines
        raise KeyError(
            f"No person_slot {slot!r} configured; known slots: "
            f"{[p.slot for p in self.german_return.person_slots]}"
        )

    def get_election(self, key: str, default: Any = None) -> Any:
        """Return ``elections[key]`` or ``default``."""
        return self.elections.get(key, default)


# ---------------------------------------------------------------------------
# Section parsers — kept module-level so they can be unit-tested in isolation
# and so ``TaxpayerProfile.from_dict`` stays focused on the top-level layout.
# ---------------------------------------------------------------------------


def _parse_german_return(raw: Any, *, source: str) -> GermanReturn | None:
    if raw is None:
        return None
    mapping = _require_mapping(raw, context=f"profile {source} .german_return")
    _reject_unknown(
        mapping,
        _ALLOWED_GERMAN_RETURN_KEYS,
        context=f"profile {source} .german_return",
    )
    required = _require_bool(
        mapping.get("required", True),
        context=f"profile {source} .german_return.required",
    )
    assume_joint = _require_bool(
        mapping.get("assume_joint_assessment_if_married", False),
        context=(
            f"profile {source} .german_return.assume_joint_assessment_if_married"
        ),
    )
    prereq_raw = mapping.get("joint_assessment_prerequisites", {})
    prereq_mapping = _require_mapping(
        prereq_raw,
        context=f"profile {source} .german_return.joint_assessment_prerequisites",
    )
    _reject_unknown(
        prereq_mapping,
        _ALLOWED_JOINT_PREREQ_KEYS,
        context=f"profile {source} .german_return.joint_assessment_prerequisites",
    )
    joint_prereq: dict[str, bool] = {}
    for key in prereq_mapping:
        joint_prereq[key] = _require_bool(
            prereq_mapping[key],
            context=(
                f"profile {source} .german_return.joint_assessment_prerequisites"
                f".{key}"
            ),
        )

    slots_raw = mapping.get("person_slots", [])
    if not isinstance(slots_raw, list):
        raise ValueError(
            f"profile {source} .german_return.person_slots: must be a list"
        )
    kap_line_ids = _load_anlage_kap_line_ids()
    slots: list[PersonSlot] = []
    for index, entry in enumerate(slots_raw):
        slot_context = f"profile {source} .german_return.person_slots[{index}]"
        slot_mapping = _require_mapping(entry, context=slot_context)
        _reject_unknown(
            slot_mapping, _ALLOWED_PERSON_SLOT_KEYS, context=slot_context
        )
        slot_id = _require_str(
            slot_mapping.get("slot", ""),
            context=f"{slot_context}.slot",
            allow_empty=False,
        )
        order_label = _require_str(
            slot_mapping.get("order_label", ""),
            context=f"{slot_context}.order_label",
            allow_empty=False,
        )
        display_name = _require_str(
            slot_mapping.get("display_name", ""),
            context=f"{slot_context}.display_name",
        )
        # ``owner`` is allowed to be ``None`` in the freshly-scaffolded
        # state (``DEFAULT_PROFILE`` in scaffold_year ships ``None``
        # placeholders; the wizard fills them in before the engine runs
        # the legal core). We preserve ``None`` so :meth:`as_dict`
        # round-trips byte-stably for unmigrated scaffold tests.
        owner_raw = slot_mapping.get("owner", "")
        owner: str | None
        if owner_raw is None:
            owner = None
        else:
            owner = _require_str(
                owner_raw,
                context=f"{slot_context}.owner",
            )
        anlage_n_label = _require_str(
            slot_mapping.get("anlage_n_label", ""),
            context=f"{slot_context}.anlage_n_label",
        )
        anlage_kap_label = _require_str(
            slot_mapping.get("anlage_kap_label", ""),
            context=f"{slot_context}.anlage_kap_label",
        )
        kap_lines_raw = slot_mapping.get("kap_lines", [])
        kap_lines = _parse_kap_lines(
            kap_lines_raw,
            allowed_line_ids=kap_line_ids,
            context=f"{slot_context}.kap_lines",
        )
        kap_raw_lines_raw = slot_mapping.get("kap_raw_lines", [])
        kap_raw_lines = _parse_kap_lines(
            kap_raw_lines_raw,
            allowed_line_ids=kap_line_ids,
            context=f"{slot_context}.kap_raw_lines",
        )
        kap_posture = _require_str(
            slot_mapping.get("kap_posture", ""),
            context=f"{slot_context}.kap_posture",
        )
        kap_notes_raw = slot_mapping.get("kap_notes", [])
        if not isinstance(kap_notes_raw, list) or any(
            not isinstance(entry, str) for entry in kap_notes_raw
        ):
            raise ValueError(
                f"{slot_context}.kap_notes: must be a list of strings"
            )
        slots.append(
            PersonSlot(
                slot=slot_id,
                order_label=order_label,
                display_name=display_name,
                owner=owner,
                anlage_n_label=anlage_n_label,
                anlage_kap_label=anlage_kap_label,
                kap_lines=kap_lines,
                kap_raw_lines=kap_raw_lines,
                kap_posture=kap_posture,
                kap_notes=tuple(kap_notes_raw),
            )
        )
    return GermanReturn(
        required=required,
        person_slots=tuple(slots),
        assume_joint_assessment_if_married=assume_joint,
        joint_assessment_prerequisites=joint_prereq,
    )


def _parse_kap_lines(
    raw: Any,
    *,
    allowed_line_ids: frozenset[str],
    context: str,
) -> tuple[str, ...]:
    """Validate a ``kap_lines`` / ``kap_raw_lines`` array.

    This is the **Anlage KAP defect class** the 2026-05-10 review
    called out: every entry must be a string equal to a declared
    ``line_id`` in ``anlage_kap.toml``. A typo like ``"99"`` or
    ``"17a"`` (when only ``"17"`` is declared) fails closed with a
    pointer to the schema file.
    """
    if not isinstance(raw, list):
        raise ValueError(f"{context}: must be a list of Anlage KAP line_id strings")
    out: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str):
            raise ValueError(
                f"{context}[{index}]: must be a string Anlage KAP line_id, "
                f"got {type(entry).__name__}"
            )
        if entry not in allowed_line_ids:
            raise ValueError(
                f"{context}[{index}] = {entry!r} is not a declared Anlage KAP "
                f"line_id; declared line_ids in "
                f"{_ANLAGE_KAP_SCHEMA_PATH.relative_to(Path(__file__).parent.parent)} "
                f"are: {sorted(allowed_line_ids)!r}"
            )
        out.append(entry)
    return tuple(out)


def _parse_us_return(raw: Any, *, source: str) -> USReturn | None:
    if raw is None:
        return None
    mapping = _require_mapping(raw, context=f"profile {source} .us_return")
    _reject_unknown(
        mapping, _ALLOWED_US_RETURN_KEYS, context=f"profile {source} .us_return"
    )
    return USReturn(
        required=_require_bool(
            mapping.get("required", False),
            context=f"profile {source} .us_return.required",
        ),
        default_filing_status_if_spouse_is_nonresident_alien=_require_str(
            mapping.get("default_filing_status_if_spouse_is_nonresident_alien", ""),
            context=(
                f"profile {source} "
                ".us_return.default_filing_status_if_spouse_is_nonresident_alien"
            ),
        ),
        treaty_resourcing_common=_require_bool(
            mapping.get("treaty_resourcing_common", False),
            context=f"profile {source} .us_return.treaty_resourcing_common",
        ),
    )


def _parse_investment_defaults(
    raw: Any, *, source: str
) -> InvestmentDefaults | None:
    if raw is None:
        return None
    mapping = _require_mapping(
        raw, context=f"profile {source} .investment_defaults"
    )
    _reject_unknown(
        mapping,
        _ALLOWED_INVESTMENT_DEFAULTS_KEYS,
        context=f"profile {source} .investment_defaults",
    )
    return InvestmentDefaults(
        primary_broker_country=_require_str(
            mapping.get("primary_broker_country", ""),
            context=f"profile {source} .investment_defaults.primary_broker_country",
        ),
        other_stock_countries_allowed=_require_bool(
            mapping.get("other_stock_countries_allowed", False),
            context=(
                f"profile {source} "
                ".investment_defaults.other_stock_countries_allowed"
            ),
        ),
        crypto_supported=_require_bool(
            mapping.get("crypto_supported", False),
            context=f"profile {source} .investment_defaults.crypto_supported",
        ),
        real_estate_supported=_require_bool(
            mapping.get("real_estate_supported", False),
            context=(
                f"profile {source} .investment_defaults.real_estate_supported"
            ),
        ),
    )


def _parse_taxpayer(raw: Any, *, source: str) -> Taxpayer | None:
    if raw is None:
        return None
    mapping = _require_mapping(raw, context=f"profile {source} .taxpayer")
    _reject_unknown(
        mapping, _ALLOWED_TAXPAYER_KEYS, context=f"profile {source} .taxpayer"
    )
    citizenship_raw = mapping.get("citizenship", [])
    if not isinstance(citizenship_raw, list) or any(
        not isinstance(c, str) for c in citizenship_raw
    ):
        raise ValueError(
            f"profile {source} .taxpayer.citizenship: must be a list of strings"
        )
    return Taxpayer(
        name=_require_str(
            mapping.get("name", ""), context=f"profile {source} .taxpayer.name"
        ),
        citizenship=tuple(citizenship_raw),
        germany_tax_resident=_require_bool(
            mapping.get("germany_tax_resident", False),
            context=f"profile {source} .taxpayer.germany_tax_resident",
        ),
    )


def _parse_spouse(raw: Any, *, source: str) -> Spouse | None:
    if raw is None:
        return None
    mapping = _require_mapping(raw, context=f"profile {source} .spouse")
    _reject_unknown(
        mapping, _ALLOWED_SPOUSE_KEYS, context=f"profile {source} .spouse"
    )
    return Spouse(
        name=_require_str(
            mapping.get("name", ""), context=f"profile {source} .spouse.name"
        ),
        us_tax_status=_require_str(
            mapping.get("us_tax_status", ""),
            context=f"profile {source} .spouse.us_tax_status",
        ),
    )


def _parse_household(raw: Any, *, source: str) -> Household | None:
    if raw is None:
        return None
    mapping = _require_mapping(raw, context=f"profile {source} .household")
    _reject_unknown(
        mapping, _ALLOWED_HOUSEHOLD_KEYS, context=f"profile {source} .household"
    )
    return Household(
        marital_status_on_dec_31=_require_str(
            mapping.get("marital_status_on_dec_31", ""),
            context=f"profile {source} .household.marital_status_on_dec_31",
        ),
        germany_filing_status=_require_str(
            mapping.get("germany_filing_status", ""),
            context=f"profile {source} .household.germany_filing_status",
        ),
        us_filing_status=_require_str(
            mapping.get("us_filing_status", ""),
            context=f"profile {source} .household.us_filing_status",
        ),
    )


def _parse_jurisdictions(
    raw: Any, *, source: str
) -> Mapping[str, JurisdictionConfig]:
    if raw is None:
        return {}
    mapping = _require_mapping(raw, context=f"profile {source} .jurisdictions")
    out: dict[str, JurisdictionConfig] = {}
    for jurisdiction_key in mapping:
        sub = mapping[jurisdiction_key]
        sub_context = (
            f"profile {source} .jurisdictions.{jurisdiction_key}"
        )
        sub_mapping = _require_mapping(sub, context=sub_context)
        _reject_unknown(
            sub_mapping, _ALLOWED_JURISDICTION_KEYS, context=sub_context
        )
        out[jurisdiction_key] = JurisdictionConfig(
            enabled=_require_bool(
                sub_mapping.get("enabled", True),
                context=f"{sub_context}.enabled",
            ),
            filing_posture=_require_str(
                sub_mapping.get("filing_posture", ""),
                context=f"{sub_context}.filing_posture",
            ),
        )
    return out


def _parse_elections(raw: Any, *, source: str) -> Mapping[str, Any]:
    if raw is None:
        return {}
    mapping = _require_mapping(raw, context=f"profile {source} .elections")
    allowed = _allowed_elections_keys()
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        # Friendly fail-closed: surface the closed set so the user can
        # spot the typo. This is exactly the
        # ``us_filing_requried`` (sic) defect class the 2026-05-10
        # review called out.
        raise ValueError(
            f"profile {source} .elections: unknown election key(s) {unknown!r}; "
            f"allowed keys (sourced from JURISDICTION_REGISTRY + "
            f"TREATY_REGISTRY enablement flags plus the closed non-enablement "
            f"set): {sorted(allowed)!r}"
        )
    # Values are not strongly typed at the dataclass level — the
    # downstream coercion in cross_jurisdiction handles bool/str
    # variants. We do a lightweight scalar-or-null check so a stray
    # nested dict / list is rejected. ``None`` is allowed because
    # ``DEFAULT_PROFILE`` in :mod:`tax_pipeline.scaffold_year` ships
    # placeholder ``null`` values for electives the user has not yet
    # filled in (``use_treaty_resourcing``, ``elect_section_911_feie``,
    # ``acknowledges_totalization_agreement_germany_us``); the
    # downstream readers handle ``None`` via the coercion path.
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        if value is not None and not isinstance(value, (str, bool, int, float)):
            raise ValueError(
                f"profile {source} .elections.{key}: must be a scalar "
                f"(bool/string/number) or null, got {type(value).__name__}"
            )
        out[key] = value
    return out


def profile_dict_for_embedding(profile: TaxpayerProfile) -> dict[str, Any]:
    """Return the dict shape used when embedding the profile in a
    derivative artifact (e.g. ``final-legal-output.json``
    ``germany.forms.profile``).

    Strips ``schema_version`` so adding the field to the on-disk
    profile.json does not drift the workspace-output md5s pinned in
    ``tests/y_agnostic/test_money_type.py``.

    Centralised here (rather than at every embed site) so a future
    schema rev can update the strip rules in one place.
    """
    return profile.as_dict(include_schema_version=False)


__all__ = [
    "PROFILE_SCHEMA_VERSION",
    "GermanReturn",
    "Household",
    "InvestmentDefaults",
    "JurisdictionConfig",
    "PersonSlot",
    "Spouse",
    "Taxpayer",
    "TaxpayerProfile",
    "USReturn",
    "profile_dict_for_embedding",
]
