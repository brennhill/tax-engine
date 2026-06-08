from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Proposal 8 (raw-bucket redesign, 2026-05-04 architecture review):
# the original ``RAW_BUCKETS`` tuple conflated two different dimensions
# under a single flat namespace -- jurisdiction-bound documents
# (``germany``, ``us``) and asset-class documents
# (``brokers``/``crypto``/``equity_comp``/``receipts``/``real_estate``).
# Adding a third country (UK, FR, ...) forces a confusing bucket
# decision (does UK brokerage go under ``raw/uk/`` or ``raw/brokers/``?).
# The new layout splits the two dimensions:
#
#   raw/jurisdictions/<iso2>/    -- jurisdiction-bound documents
#   raw/asset_classes/<class>/   -- cross-jurisdiction asset documents
#
# JURISDICTION_BUCKETS uses ISO 3166-1 alpha-2 country codes (``de``,
# ``us``); the legacy directory names (``germany``, ``us``) are mapped
# via JURISDICTION_LEGACY_NAMES so existing workspaces continue to work
# until they are migrated. The runtime resolver checks the new layout
# first and falls back to the old, printing a one-time migration hint.
JURISDICTION_BUCKETS: tuple[str, ...] = ("de", "us")
ASSET_CLASS_BUCKETS: tuple[str, ...] = (
    "brokers",
    "crypto",
    "equity_comp",
    "receipts",
    "real_estate",
)

# Mapping from the legacy flat-bucket name (``germany``, ``us``) to the
# canonical ISO-coded jurisdiction bucket (``de``, ``us``). Kept as a
# data dict so the migration helper, the dual-read resolver, and the
# uploads classifier all share one source of truth.
JURISDICTION_LEGACY_NAMES: dict[str, str] = {
    "germany": "de",
    "us": "us",
}

# Backward-compatible alias preserving the original flat-bucket tuple
# shape. Kept so legacy call sites (``profile.raw_buckets`` validation,
# evidence-only uploads) keep accepting the historical names. New code
# should prefer JURISDICTION_BUCKETS / ASSET_CLASS_BUCKETS or
# ``all_raw_bucket_names()`` below.
RAW_BUCKETS: tuple[str, ...] = (
    *JURISDICTION_LEGACY_NAMES.keys(),
    *ASSET_CLASS_BUCKETS,
)


def all_raw_bucket_names() -> tuple[str, ...]:
    """Names accepted as a top-level raw bucket on either layout.

    Includes the canonical ISO codes (``de``, ``us``), the legacy flat
    names (``germany``, ``us``), and every asset class. The tuple is
    deduplicated and order-stable so it can be used by callers that
    iterate buckets for upload classification or migration scanning.
    """

    seen: list[str] = []
    for name in (
        *JURISDICTION_BUCKETS,
        *JURISDICTION_LEGACY_NAMES.keys(),
        *ASSET_CLASS_BUCKETS,
    ):
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def canonical_bucket_path(raw_root: Path, bucket: str) -> Path:
    """Return the canonical (post-redesign) on-disk path for ``bucket``.

    Jurisdiction names (legacy ``germany``/``us``, canonical ``de``/
    ``us``) resolve under ``raw/jurisdictions/<iso2>/``. Asset-class
    names resolve under ``raw/asset_classes/<class>/``. Unknown names
    fall back to ``raw_root / bucket`` so callers retain the original
    behavior on names they do not recognise (``profile.raw_buckets``
    validation surfaces them via the unsupported-fact path instead).
    """

    iso = JURISDICTION_LEGACY_NAMES.get(bucket, bucket)
    if iso in JURISDICTION_BUCKETS:
        return raw_root / "jurisdictions" / iso
    if bucket in ASSET_CLASS_BUCKETS:
        return raw_root / "asset_classes" / bucket
    return raw_root / bucket


def legacy_bucket_path(raw_root: Path, bucket: str) -> Path:
    """Return the pre-redesign (flat) on-disk path for ``bucket``.

    The legacy layout is ``raw_root / <bucket>``. Jurisdiction buckets
    use the historical flat names (``germany``, ``us``) -- the ISO
    codes are mapped back to those names so an ISO-coded resolver call
    still finds files in legacy workspaces.
    """

    legacy_name = bucket
    if bucket in JURISDICTION_BUCKETS:
        for legacy, iso in JURISDICTION_LEGACY_NAMES.items():
            if iso == bucket:
                legacy_name = legacy
                break
    return raw_root / legacy_name


def resolve_bucket_path(raw_root: Path, bucket: str) -> Path:
    """Pick the right on-disk path for ``bucket`` across both layouts.

    The new layout is preferred when its directory exists; otherwise we
    fall back to the legacy flat path. This is the read-side of the
    Proposal 8 dual-layout contract: workspaces that have not been
    migrated keep working until the migration helper is run.
    """

    new_path = canonical_bucket_path(raw_root, bucket)
    if new_path.exists():
        return new_path
    legacy = legacy_bucket_path(raw_root, bucket)
    if legacy.exists():
        return legacy
    return new_path


def has_legacy_raw_layout(raw_root: Path) -> bool:
    """True when the workspace still uses the pre-redesign flat layout.

    Used by the runtime to print a one-time migration hint without
    failing closed -- legacy workspaces continue to function but the
    user is nudged to run the migration helper.
    """

    if not raw_root.exists():
        return False
    for bucket in (*JURISDICTION_LEGACY_NAMES.keys(), *ASSET_CLASS_BUCKETS):
        if (raw_root / bucket).is_dir():
            children = [p for p in (raw_root / bucket).iterdir() if not p.name.startswith(".")]
            if children:
                return True
    return False


def canonicalize_relative_path(relative_path: str) -> str:
    """Map a manifest-relative path to the canonical (new-layout) form.

    Used when emitting derived metadata so downstream artifacts always
    refer to canonical paths regardless of which layout the workspace
    is on. The path content (filename, sub-folders) is preserved
    verbatim; only the top-level bucket prefix is rewritten when it is
    a recognised legacy or canonical bucket.
    """

    if not relative_path:
        return relative_path
    parts = relative_path.replace("\\", "/").split("/")
    head, tail = parts[0], parts[1:]
    if head in JURISDICTION_LEGACY_NAMES:
        iso = JURISDICTION_LEGACY_NAMES[head]
        return "/".join(["jurisdictions", iso, *tail])
    if head in JURISDICTION_BUCKETS:
        return "/".join(["jurisdictions", head, *tail])
    if head in ASSET_CLASS_BUCKETS:
        return "/".join(["asset_classes", head, *tail])
    return relative_path


@dataclass(frozen=True)
class YearPaths:
    project_root: Path
    year: int
    workspace_root: Path
    year_root: Path
    raw_root: Path
    config_root: Path
    normalized_root: Path
    outputs_root: Path
    analysis_root: Path
    derivation_root: Path
    forms_root: Path
    # Proposal 2 (architecture review 2026-05-04): per-jurisdiction
    # form / legal-audit roots are kept as named slots for backward
    # compatibility with the existing AST-driven invariant tests
    # (``test_form_renderer_lines_match_output_declarations.py``) that
    # match ``germany_forms_root`` / ``usa_forms_root`` literals. The
    # registry-driven dict-keyed accessors live below as helper
    # methods (``forms_root_for(code)`` / ``legal_audit_root_for(code)``)
    # which let new orchestration code iterate jurisdictions without
    # reading the named slots. A future P2 cleanup pass can replace
    # the named slots with a dict once the AST tests are migrated.
    germany_forms_root: Path
    usa_forms_root: Path
    legal_audit_root: Path
    germany_legal_audit_root: Path
    usa_legal_audit_root: Path
    manifest_path: Path
    facts_root: Path
    manual_facts_root: Path
    reference_data_root: Path
    derived_facts_root: Path
    tax_positions_root: Path
    profile_path: Path
    manual_overrides_path: Path
    people_path: Path
    payments_path: Path
    elections_path: Path
    children_path: Path

    def forms_root_for(self, code: str) -> Path:
        """Return the per-jurisdiction forms root by ISO-2 code.

        Proposal 2 jurisdiction-keyed accessor. Generalises the
        ``germany_forms_root`` / ``usa_forms_root`` named slots so
        new orchestration code can iterate jurisdictions without
        reading the named slots. Unknown codes raise ``KeyError``
        (fail closed).
        """
        from tax_pipeline.jurisdictions import get_jurisdiction

        definition = get_jurisdiction(code)
        return self.forms_root / definition.posture_registry_key

    def legal_audit_root_for(self, code: str) -> Path:
        """Return the per-jurisdiction legal-audit root by ISO-2 code.

        Mirror of :func:`forms_root_for` for the legal-audit packages.
        """
        from tax_pipeline.jurisdictions import get_jurisdiction

        definition = get_jurisdiction(code)
        return self.legal_audit_root / definition.posture_registry_key

    @classmethod
    def for_year(cls, project_root: Path, year: int) -> "YearPaths":
        year_root = project_root / "years" / str(year)
        return cls.for_workspace(project_root, year_root, year)

    @classmethod
    def for_workspace(cls, project_root: Path, workspace_root: Path, year: int) -> "YearPaths":
        year_root = workspace_root
        raw_root = year_root / "raw"
        config_root = year_root / "config"
        normalized_root = year_root / "normalized"
        outputs_root = year_root / "outputs"
        analysis_root = outputs_root / "analysis-steps"
        # WS-5H (invariant migration plan §1.5): Pipeline 1 (Derivation)
        # writes ``derived-facts.json`` and ``derivation-graph.json`` here.
        # Pipeline 2 (Legal) reads ``derived-facts.json`` as the typed,
        # persisted boundary between raw-input derivation and legal
        # interpretation. Co-locating with ``analysis-steps`` keeps audit
        # artifacts grouped under ``outputs/`` for downstream tooling.
        derivation_root = outputs_root / "derivation"
        forms_root = outputs_root / "forms"
        germany_forms_root = forms_root / "germany"
        usa_forms_root = forms_root / "usa"
        legal_audit_root = outputs_root / "legal-audit"
        germany_legal_audit_root = legal_audit_root / "germany"
        usa_legal_audit_root = legal_audit_root / "usa"
        manifest_path = normalized_root / "documents.json"
        facts_root = normalized_root / "facts"
        manual_facts_root = normalized_root / "manual-facts"
        reference_data_root = normalized_root / "reference-data"
        derived_facts_root = normalized_root / "derived-facts"
        tax_positions_root = outputs_root / "tax-positions"
        profile_path = config_root / "profile.json"
        manual_overrides_path = config_root / "manual_overrides.json"
        people_path = config_root / "people.csv"
        payments_path = config_root / "payments.csv"
        elections_path = config_root / "elections.csv"
        # § 31 EStG / § 32 Abs. 6 EStG / BKGG — per-child facts (one row
        # per child) feeding the German Familienleistungsausgleich and
        # the U.S. CTC / dependents calculation. Optional file: a
        # missing path means "no children declared" and produces zero
        # children-related changes.
        # https://www.gesetze-im-internet.de/estg/__31.html
        children_path = config_root / "children.csv"
        return cls(
            project_root=project_root,
            year=year,
            workspace_root=workspace_root,
            year_root=year_root,
            raw_root=raw_root,
            config_root=config_root,
            normalized_root=normalized_root,
            outputs_root=outputs_root,
            analysis_root=analysis_root,
            derivation_root=derivation_root,
            forms_root=forms_root,
            germany_forms_root=germany_forms_root,
            usa_forms_root=usa_forms_root,
            legal_audit_root=legal_audit_root,
            germany_legal_audit_root=germany_legal_audit_root,
            usa_legal_audit_root=usa_legal_audit_root,
            manifest_path=manifest_path,
            facts_root=facts_root,
            manual_facts_root=manual_facts_root,
            reference_data_root=reference_data_root,
            derived_facts_root=derived_facts_root,
            tax_positions_root=tax_positions_root,
            profile_path=profile_path,
            manual_overrides_path=manual_overrides_path,
            people_path=people_path,
            payments_path=payments_path,
            elections_path=elections_path,
            children_path=children_path,
        )

    def ensure_directories(self) -> None:
        self.raw_root.mkdir(parents=True, exist_ok=True)
        # Proposal 8: scaffold the new dual-dimension layout.
        # ``raw/jurisdictions/<iso>/`` for country-bound docs,
        # ``raw/asset_classes/<class>/`` for asset-class docs.
        (self.raw_root / "jurisdictions").mkdir(parents=True, exist_ok=True)
        (self.raw_root / "asset_classes").mkdir(parents=True, exist_ok=True)
        for iso in JURISDICTION_BUCKETS:
            (self.raw_root / "jurisdictions" / iso).mkdir(parents=True, exist_ok=True)
        for asset_class in ASSET_CLASS_BUCKETS:
            (self.raw_root / "asset_classes" / asset_class).mkdir(parents=True, exist_ok=True)
        # Backward-compatible scaffold: the legacy flat names continue
        # to be created so existing workspaces, tests, and the upload
        # ``manual_bucket=...`` evidence-only path keep working until
        # the workspace is migrated. The migration helper (Commit 4)
        # converts a legacy workspace to the new layout in-place.
        #
        # Audit Wave 2a (2026-05-04) deferred the removal of these
        # legacy stubs: ``test_year_pipeline.py:88,1631`` assert
        # ``raw/real_estate`` is a directory after ``ensure_directories``,
        # ``test_year_pipeline.py:217-218`` and ``:347`` create files
        # under ``raw/germany/`` directly, and ``has_legacy_raw_layout``
        # only flags non-empty legacy buckets so the empty stubs are
        # harmless on disk. Migrating the assertions to the canonical
        # layout is straightforward but touches ~6 tests; deferring
        # until Proposal 2 (jurisdiction registry) when the asserted
        # directory shape is being redesigned anyway.
        for bucket in RAW_BUCKETS:
            (self.raw_root / bucket).mkdir(parents=True, exist_ok=True)
        self.config_root.mkdir(parents=True, exist_ok=True)
        self.normalized_root.mkdir(parents=True, exist_ok=True)
        self.facts_root.mkdir(parents=True, exist_ok=True)
        self.manual_facts_root.mkdir(parents=True, exist_ok=True)
        self.reference_data_root.mkdir(parents=True, exist_ok=True)
        self.derived_facts_root.mkdir(parents=True, exist_ok=True)
        (self.derived_facts_root / "common").mkdir(parents=True, exist_ok=True)
        (self.derived_facts_root / "germany").mkdir(parents=True, exist_ok=True)
        (self.derived_facts_root / "usa").mkdir(parents=True, exist_ok=True)
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        self.analysis_root.mkdir(parents=True, exist_ok=True)
        self.derivation_root.mkdir(parents=True, exist_ok=True)
        self.forms_root.mkdir(parents=True, exist_ok=True)
        self.germany_forms_root.mkdir(parents=True, exist_ok=True)
        self.usa_forms_root.mkdir(parents=True, exist_ok=True)
        self.legal_audit_root.mkdir(parents=True, exist_ok=True)
        self.germany_legal_audit_root.mkdir(parents=True, exist_ok=True)
        self.usa_legal_audit_root.mkdir(parents=True, exist_ok=True)
        self.tax_positions_root.mkdir(parents=True, exist_ok=True)
