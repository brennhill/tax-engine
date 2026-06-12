"""Posture and election registry for the intake UI.

This module is the single source of truth for the *capture surface* of every
user-facing tax posture/election. It deliberately does NOT contain legal math:
the engine continues to read profile.json / *.csv inputs and apply law.
Everything here is metadata that lets the local intake wizard:

  * render the right widget for each posture,
  * show the legal consequence (and what alternative paths a choice forecloses),
  * cite the controlling authority (§ EStG / 26 U.S.C. / DBA-USA Article),
  * validate cross-field preconditions and mutual-exclusion before we write
    posture state to disk.

CLAUDE.md tax-rule requirements: every posture cites its controlling authority
in ``legal_refs`` and an official URL in ``legal_urls``. These citations match
the citations used in the engine's input-validation modules (``germany_2025_inputs``,
``us_2025_inputs``) and the law-spec markdown.

The registry is intentionally append-only — concurrent waves (Wave 2D engine
DE work, Wave 3B engine US/treaty work, Wave 4 cross-jurisdiction) will land
engine-side support for postures that currently carry ``engine_supported=False``.
The UI greys out and labels those entries so users do not believe they can
elect a path the engine still fails closed on.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.paths import YearPaths
from tax_pipeline.scaffold_year import (
    ELECTIONS_COLUMNS,
    _display_germany_filing_posture,
    _display_usa_filing_posture,
    _normalize_germany_filing_posture,
    _normalize_usa_filing_posture,
    sync_profile_from_csv_inputs,
)


# ---------------------------------------------------------------------------
# Section identifiers used to group postures in the UI.
# ---------------------------------------------------------------------------
SECTION_FILING_STATUS = "filing_status"
SECTION_DE_ELECTIONS = "de_elections"
SECTION_US_ELECTIONS = "us_elections"
SECTION_TREATY = "treaty"
SECTION_CROSS_JURISDICTION = "cross_jurisdiction"


# ---------------------------------------------------------------------------
# Storage backend identifiers. Each posture is persisted to exactly one of:
#   - "profile_json": a path inside config/profile.json
#   - "elections_csv": a (jurisdiction, key) row in config/elections.csv
#   - "model_assumptions_csv": a (section, key) row in
#     outputs/tax-positions/de-model-assumptions.csv (Germany model
#     assumptions live here so they sit next to other tax-position rows that
#     the engine already consumes; see analysis_inputs.py).
# ---------------------------------------------------------------------------
STORAGE_PROFILE_JSON = "profile_json"
STORAGE_ELECTIONS_CSV = "elections_csv"
STORAGE_DE_MODEL_ASSUMPTIONS = "de_model_assumptions_csv"


@dataclass(frozen=True)
class PostureField:
    """Declarative description of one user-facing posture/election."""

    key: str
    """Dot-notation path. For ``profile_json`` storage this is the path inside
    profile.json (e.g. ``elections.elect_section_911_feie``). For CSV storage
    backends this is the canonical identifier the UI uses; the storage
    function maps it to (jurisdiction,key) or (section,key)."""

    label: str
    """Display name shown beside the widget."""

    widget: str
    """One of ``radio``, ``select``, ``checkbox``, ``text``, ``number``."""

    options: tuple[tuple[str, str], ...] = ()
    """``(value, display_label)`` pairs. Required for ``radio`` / ``select``."""

    tooltip: str = ""
    """One- to three-sentence explanation of the legal consequence and what
    alternative paths the choice forecloses. Must mention the controlling §
    or 26 U.S.C. citation (enforced by ``tests/y_agnostic/test_intake_postures.py``)."""

    required: bool = True
    default: Any = None

    legal_refs: tuple[str, ...] = ()
    """Statutory citations (e.g. ``§ 32a EStG``, ``26 U.S.C. § 911``)."""

    legal_urls: tuple[str, ...] = ()
    """Official source URLs for ``legal_refs``."""

    requires: tuple[tuple[str, Any], ...] = ()
    """``(other_key, must_equal_value)`` preconditions. Multiple entries are
    AND-combined."""

    mutually_exclusive_with: tuple[str, ...] = ()
    """Other posture keys that may not be true/non-empty at the same time."""

    section: str = "general"

    storage: str = STORAGE_PROFILE_JSON
    """Which on-disk surface this posture writes to."""

    storage_meta: tuple[tuple[str, str], ...] = ()
    """Backend-specific extras. For ``elections_csv`` storage this carries
    ``(("jurisdiction", "usa"), ("csv_key", "use_treaty_resourcing"))``. For
    ``de_model_assumptions_csv`` it carries ``(("section", "capital"),
    ("csv_key", "capital_guenstigerpruefung_requested"))``."""

    engine_supported: bool = True
    """When False, the UI marks the field as 'coming soon'. The engine still
    fails closed if the user picks the unsupported branch — this flag only
    drives UI affordances."""

    coming_soon_wave: str = ""
    """Free-text annotation pointing at the wave that will land engine-side
    support (e.g. ``"Wave 3B"``, ``"Wave 4"``)."""


# ---------------------------------------------------------------------------
# Registry of all user-facing postures.
#
# Order is significant for rendering: the UI iterates this tuple in order and
# groups consecutive entries by ``section``.
#
# Citations and URLs match those used in the engine input modules
# (``germany_2025_inputs.py``, ``us_2025_inputs.py``) and the law-spec
# markdown. CLAUDE.md "tax-law rule requirements" governs both.
# ---------------------------------------------------------------------------
POSTURE_REGISTRY: tuple[PostureField, ...] = (
    # ---- Filing status (per jurisdiction) ----------------------------------
    PostureField(
        key="jurisdictions.germany.filing_posture",
        label="Germany filing posture",
        widget="radio",
        options=(
            ("single", "Single"),
            ("married_joint", "Married joint (Splittingtarif)"),
            ("married_separate", "Married separate"),
        ),
        tooltip=(
            "Pick how Germany should treat you for the year: single, married "
            "filing together, or married filing on your own. Married filing "
            "together (Splittingtarif) usually saves money for couples with "
            "uneven incomes. Married filing separately rules that out but "
            "lets each spouse handle their investments on their own. Single "
            "gets you the smaller saver allowance. (Legal: § 26, § 26b, "
            "§ 32a EStG)"
        ),
        legal_refs=("§ 26 EStG", "§ 26b EStG", "§ 32a EStG"),
        legal_urls=(
            "https://www.gesetze-im-internet.de/estg/__26.html",
            "https://www.gesetze-im-internet.de/estg/__26b.html",
            "https://www.gesetze-im-internet.de/estg/__32a.html",
        ),
        section=SECTION_FILING_STATUS,
        storage=STORAGE_PROFILE_JSON,
        default="single",
    ),
    PostureField(
        key="jurisdictions.usa.filing_posture",
        label="U.S. filing posture",
        widget="radio",
        options=(
            ("single", "Single"),
            ("married_joint", "Married filing jointly"),
            ("mfs_nra_spouse", "MFS with NRA spouse"),
            ("married_separate", "Married filing separately"),
            ("head_of_household", "Head of household"),
        ),
        tooltip=(
            "Pick how the IRS should treat you: single, married filing "
            "jointly, married filing separately, married filing separately "
            "with a non-U.S.-citizen spouse, or head of household. Your pick "
            "decides which tax brackets, standard deduction, and "
            "investment-tax thresholds apply. Married filing separately "
            "cuts most of those numbers in half. Head of household needs "
            "you to have a qualifying child or relative living with you. "
            "(Legal: 26 U.S.C. §§ 1, 63, 1211(b), 1411, 2(b))"
        ),
        legal_refs=(
            "26 U.S.C. § 1",
            "26 U.S.C. § 63",
            "26 U.S.C. § 1211(b)",
            "26 U.S.C. § 1411",
            "26 U.S.C. § 2(b)",
        ),
        legal_urls=(
            "https://www.law.cornell.edu/uscode/text/26/1",
            "https://www.law.cornell.edu/uscode/text/26/63",
            "https://www.law.cornell.edu/uscode/text/26/1211",
            "https://www.law.cornell.edu/uscode/text/26/1411",
        ),
        section=SECTION_FILING_STATUS,
        storage=STORAGE_PROFILE_JSON,
        default="single",
    ),
    # ---- DE elections ------------------------------------------------------
    PostureField(
        key="elections.germany_kirchensteuer_membership",
        label="Kirchensteuer (church tax) membership",
        widget="select",
        options=(
            ("none", "None — not a member"),
            ("EVK", "Evangelisch (EVK)"),
            ("RKK", "Roman Catholic (RKK)"),
            ("FREIKIRCHE", "Freikirche / other"),
        ),
        tooltip=(
            "Germany collects church tax for members of recognized churches: "
            "8% of your income tax in Bavaria and Baden-Wuerttemberg, 9% "
            "everywhere else. Pick 'none' if you are not a member. We have "
            "not built the church-tax math yet, so picking any membership "
            "other than 'none' will stop the calculator. (Legal: § 51a EStG)"
        ),
        legal_refs=("§ 51a EStG",),
        legal_urls=("https://www.gesetze-im-internet.de/estg/__51a.html",),
        section=SECTION_DE_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default="none",
    ),
    PostureField(
        key="elections.germany_disability_pauschbetrag_transfer",
        label="§ 33b Abs. 5 EStG: claim a child's Behinderten-Pauschbetrag",
        widget="checkbox",
        tooltip=(
            "Germany gives a flat allowance to people with a recognized "
            "disability (Grad der Behinderung). § 33b Abs. 5 EStG lets "
            "parents claim a qualifying child's flat allowance on their "
            "own return — but only if they explicitly elect to. If you do "
            "not check this, the child's allowance is forfeit. The engine "
            "refuses to compute a return with disabled children unless "
            "this is set explicitly. (Legal: § 33b Abs. 5 EStG)"
        ),
        legal_refs=("§ 33b Abs. 5 EStG",),
        legal_urls=("https://www.gesetze-im-internet.de/estg/__33b.html",),
        section=SECTION_DE_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default=False,
    ),
    PostureField(
        key="capital_guenstigerpruefung_requested",
        label="§ 32d Abs. 6 Günstigerprüfung",
        widget="radio",
        options=(
            ("0", "Do not elect (use 25 % flat rate)"),
            ("1", "Elect § 32a tariff if it produces lower tax"),
        ),
        tooltip=(
            "Normally Germany taxes your investment income at a flat 25%. "
            "If your other income is low enough, you can ask Germany to use "
            "the regular income-tax brackets on it instead, which is "
            "sometimes cheaper. We will show you whether the swap would "
            "have saved you money, but the calculator does not yet apply "
            "the swap automatically. (Legal: § 32d Abs. 6 EStG)"
        ),
        legal_refs=("§ 32d Abs. 6 EStG",),
        legal_urls=("https://www.gesetze-im-internet.de/estg/__32d.html",),
        section=SECTION_DE_ELECTIONS,
        storage=STORAGE_DE_MODEL_ASSUMPTIONS,
        storage_meta=(("section", "capital"), ("csv_key", "capital_guenstigerpruefung_requested")),
        default="0",
    ),
    # ---- Self-employment (Phase 1 freelancer support) ----------------------
    PostureField(
        key="elections.worker_type",
        label="Worker type",
        widget="select",
        options=(
            ("employee", "Employee (wages only)"),
            ("self_employed", "Self-employed / freelancer"),
            ("both", "Both employee and self-employed"),
        ),
        tooltip=(
            "Pick how you earn money. 'Employee' means you only have wages "
            "from an employer. 'Self-employed' means you run your own "
            "freelance business (Freiberufler) and report its profit. "
            "'Both' means you have wages and freelance income. Choosing a "
            "self-employed option asks you for your business receipts and "
            "expenses, and the profit is taxed under § 18 / § 4 Abs. 3 EStG. "
            "(Legal: § 2 Abs. 1 EStG; § 18 EStG)"
        ),
        legal_refs=("§ 2 Abs. 1 EStG", "§ 18 EStG"),
        legal_urls=(
            "https://www.gesetze-im-internet.de/estg/__2.html",
            "https://www.gesetze-im-internet.de/estg/__18.html",
        ),
        section=SECTION_DE_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default="employee",
    ),
    PostureField(
        key="elections.de_self_employment_class",
        label="Self-employment class (§ 18 vs § 15)",
        widget="select",
        options=(
            ("freiberuflich_18", "Freiberufler — selbständige Arbeit (§ 18)"),
            ("gewerbe_15", "Gewerbe — trade business (§ 15) — coming soon"),
        ),
        tooltip=(
            "If you are self-employed, pick whether your work is a liberal "
            "profession (Freiberufler — e.g. consultant, developer, writer, "
            "doctor) or a trade business (Gewerbe — e.g. a shop). Freiberufler "
            "(§ 18) is supported. Gewerbe (§ 15) is not yet handled because it "
            "also triggers trade tax (Gewerbesteuer); selecting it stops the "
            "calculator rather than guessing. (Legal: § 18 EStG; § 15 EStG)"
        ),
        legal_refs=("§ 18 EStG", "§ 15 EStG"),
        legal_urls=(
            "https://www.gesetze-im-internet.de/estg/__18.html",
            "https://www.gesetze-im-internet.de/estg/__15.html",
        ),
        section=SECTION_DE_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default="freiberuflich_18",
    ),
    # ---- US elections ------------------------------------------------------
    PostureField(
        key="elections.elect_joint_return_with_nra_spouse",
        label="§ 6013(g) joint election with NRA spouse",
        widget="checkbox",
        tooltip=(
            "Check this if your spouse is not a U.S. citizen or green-card "
            "holder, but you want to file a joint U.S. tax return with them. "
            "Doing this means your spouse's worldwide income gets added to "
            "your U.S. return. Once you turn it on, it stays on every year "
            "until you formally take it back. You cannot pick this and also "
            "file 'married filing separately'. (Legal: 26 U.S.C. § 6013(g))"
        ),
        legal_refs=("26 U.S.C. § 6013(g)",),
        legal_urls=("https://www.law.cornell.edu/uscode/text/26/6013",),
        requires=(("jurisdictions.usa.filing_posture", "married_joint"),),
        mutually_exclusive_with=("jurisdictions.usa.filing_posture",),
        section=SECTION_US_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default=False,
    ),
    PostureField(
        key="elections.elect_joint_return_with_nra_spouse_for_niit",
        label="Joint NIIT election with NRA spouse",
        widget="checkbox",
        section=SECTION_US_ELECTIONS,
        required=True,
        default=False,
        requires=(("elections.elect_joint_return_with_nra_spouse", True),),
        engine_supported=True,
        legal_refs=("§ 1411(b)",),
        legal_urls=("https://www.law.cornell.edu/uscode/text/26/1411",),
        storage=STORAGE_PROFILE_JSON,
        tooltip=(
            "Even after you elect to treat a non-citizen spouse as a U.S. "
            "resident for income tax, the IRS keeps the investment-income "
            "tax (NIIT) separate. Check this to also count your spouse "
            "toward the joint $250,000 NIIT threshold. If you skip this, "
            "your threshold falls to $125,000 and your spouse's investment "
            "income stays outside the NIIT base. (Legal: 26 U.S.C. § 1411(b))"
        ),
    ),
    PostureField(
        key="elections.use_treaty_resourcing",
        label="Treaty re-sourcing election (Form 1116 § 904(d))",
        widget="checkbox",
        tooltip=(
            "Use the U.S.-Germany tax treaty to move some of your income "
            "from being 'U.S.-source' to being 'German-source' on your "
            "U.S. return. That makes more of your German taxes count as a "
            "credit against U.S. tax, so you usually pay less double tax. "
            "It does add a Form 1116 column and some paperwork. Most "
            "Americans living in Germany want this on. (Legal: 26 U.S.C. "
            "§ 904(d), DBA-USA 1989 Art. 23)"
        ),
        legal_refs=("26 U.S.C. § 904(d)", "DBA-USA 1989 Art. 23"),
        legal_urls=(
            "https://www.law.cornell.edu/uscode/text/26/904",
            "https://www.bgbl.de/xaver/bgbl/start.xav?startbk=Bundesanzeiger_BGBl",
        ),
        section=SECTION_US_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default=True,
    ),
    PostureField(
        key="elections.us_ftc_method",
        label="FTC accounting basis (§ 905(a))",
        widget="radio",
        options=(
            ("accrued", "Accrued — credit foreign tax accrued for the year"),
            ("paid", "Paid — credit foreign tax actually paid (cash basis)"),
        ),
        tooltip=(
            "Pick how you want to count foreign tax for the U.S. credit: "
            "in the year it was charged ('accrued') or in the year you "
            "actually paid it ('paid'). 'Accrued' usually matches your "
            "German tax assessment for the same year and is what most "
            "filers pick. 'Paid' is cash-basis: only counts what hit your "
            "bank that year. Once you pick, the IRS makes you stick with "
            "it every year. We currently support 'accrued' only; picking "
            "'paid' will stop the calculator. (Legal: 26 U.S.C. § 905)"
        ),
        legal_refs=("26 U.S.C. § 905(a)", "26 U.S.C. § 905(c)"),
        legal_urls=("https://www.law.cornell.edu/uscode/text/26/905",),
        section=SECTION_US_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default="accrued",
        engine_supported=True,  # accrued is supported; "paid" branch fails closed
        coming_soon_wave="",
    ),
    PostureField(
        key="elections.elect_section_911_feie",
        label="§ 911 Foreign Earned Income Exclusion",
        widget="checkbox",
        tooltip=(
            "If you live and work abroad, the IRS lets you leave up to "
            "$130,000 of your foreign wages off your U.S. return for 2025. "
            "To qualify you must either be a 'bona fide resident' of the "
            "foreign country for a full tax year, or be physically there "
            "at least 330 days in 12 months. You cannot also use the "
            "foreign tax credit on the same wages you exclude. Once you "
            "turn this on, it stays on every year unless you formally "
            "revoke it. For Americans in Germany, the foreign tax credit "
            "is usually a better deal because German tax is high. (Legal: "
            "26 U.S.C. § 911)"
        ),
        legal_refs=(
            "26 U.S.C. § 911(a)",
            "26 U.S.C. § 911(d)(6)",
            "26 U.S.C. § 911(e)",
        ),
        legal_urls=("https://www.law.cornell.edu/uscode/text/26/911",),
        section=SECTION_US_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default=False,
        engine_supported=True,
        coming_soon_wave="",
    ),
    PostureField(
        key="elections.acknowledges_totalization_agreement_germany_us",
        label="U.S.-Germany Totalization Agreement acknowledgment",
        widget="checkbox",
        tooltip=(
            "Wages from a German employer normally do not pay U.S. Social "
            "Security or Medicare tax, thanks to a 1976 agreement between "
            "the two countries. Check this box to confirm your wages are "
            "from a German employer and so they skip U.S. Social Security "
            "and Medicare. If you uncheck it, the calculator will stop "
            "because it does not yet handle the U.S. Additional Medicare "
            "Tax on wages. (Legal: 26 U.S.C. § 3101(b)(2); 1976 "
            "U.S.-Germany Totalization Agreement)"
        ),
        legal_refs=("26 U.S.C. § 3101(b)(2)",),
        legal_urls=(
            "https://www.law.cornell.edu/uscode/text/26/3101",
            "https://www.ssa.gov/international/Agreement_Pamphlets/germany.html",
        ),
        section=SECTION_US_ELECTIONS,
        storage=STORAGE_PROFILE_JSON,
        default=True,
    ),
    # ---- Treaty -----------------------------------------------------------
    PostureField(
        key="us.treaty.lob_qualification_category",
        label="DBA-USA Art. 28 LOB qualification",
        widget="select",
        options=(
            ("publicly_traded", "Publicly traded company"),
            ("qualified_resident", "Qualified resident (individual / pension fund)"),
            ("active_business", "Active trade or business"),
            ("derivative_benefits", "Derivative benefits"),
            ("competent_authority", "Competent-authority discretionary grant"),
            ("not_qualified", "Not qualified — no treaty benefits"),
        ),
        tooltip=(
            "The U.S.-Germany tax treaty has a 'who qualifies' rule that "
            "stops people from shopping the treaty just to lower taxes. "
            "Pick which category fits you. Almost every regular person who "
            "lives in Germany is a 'qualified resident'. Picking 'not "
            "qualified' turns off all treaty benefits, including the "
            "treaty re-sourcing election above, so you usually get more "
            "double-taxed. (Legal: DBA-USA 1989 Art. 28, 2006 Protocol)"
        ),
        legal_refs=("DBA-USA 1989 Art. 28 (2006 Protocol)",),
        legal_urls=(
            "https://www.bundesfinanzministerium.de/Content/DE/Standardartikel/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Laender_A_Z/Vereinigte_Staaten/2008-08-04-USA-Abkommen-DBA-Gesetz.pdf",
        ),
        section=SECTION_TREATY,
        storage=STORAGE_PROFILE_JSON,
        default="qualified_resident",
        engine_supported=True,
        coming_soon_wave="",
    ),
    # ---- Cross-jurisdiction (Wave 4) ---------------------------------------
    PostureField(
        key="elections.us_filing_required",
        label="U.S. filing required",
        widget="checkbox",
        tooltip=(
            "Turn off everything U.S.-related. Uncheck this only if nobody "
            "in your household is a U.S. citizen or green-card holder, you "
            "have no U.S.-source income, and you have no other reason to "
            "file with the IRS. With it off, we skip every U.S. form "
            "(1040, 1116, 2555, etc.) and only run the German return. The "
            "audit log records that you chose to skip the U.S. side. "
            "(Legal: 26 U.S.C. § 6012)"
        ),
        legal_refs=("26 U.S.C. § 6012",),
        legal_urls=("https://www.law.cornell.edu/uscode/text/26/6012",),
        section=SECTION_CROSS_JURISDICTION,
        storage=STORAGE_PROFILE_JSON,
        default=True,
        engine_supported=True,
        coming_soon_wave="",
    ),
)


def _registry_index() -> dict[str, PostureField]:
    return {field.key: field for field in POSTURE_REGISTRY}


# ---------------------------------------------------------------------------
# Serialization for the HTTP API.
# ---------------------------------------------------------------------------
def serialize_registry() -> list[dict[str, Any]]:
    """Return the registry in JSON-friendly form for the frontend.

    Tuples become lists; ``options`` and ``requires`` become lists of dicts
    so the JS side can read them without tuple-index acrobatics.
    """

    serialized: list[dict[str, Any]] = []
    for field_def in POSTURE_REGISTRY:
        record = asdict(field_def)
        record["options"] = [
            {"value": value, "label": label} for value, label in field_def.options
        ]
        record["requires"] = [
            {"key": key, "equals": value} for key, value in field_def.requires
        ]
        record["mutually_exclusive_with"] = list(field_def.mutually_exclusive_with)
        record["legal_refs"] = list(field_def.legal_refs)
        record["legal_urls"] = list(field_def.legal_urls)
        record["storage_meta"] = {key: value for key, value in field_def.storage_meta}
        serialized.append(record)
    return serialized


# ---------------------------------------------------------------------------
# Reading current values off disk (profile.json + CSV inputs).
# ---------------------------------------------------------------------------
def _read_profile(paths: YearPaths) -> dict[str, Any]:
    if not paths.profile_path.exists():
        return {}
    return json.loads(paths.profile_path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]


def _profile_get(profile: dict[str, Any], dotted_key: str) -> Any:
    """Walk ``profile`` along a dotted path, returning ``None`` if any segment
    is missing."""

    cursor: Any = profile
    for segment in dotted_key.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def _profile_set(profile: dict[str, Any], dotted_key: str, value: Any) -> None:
    cursor: dict[str, Any] = profile
    segments = dotted_key.split(".")
    for segment in segments[:-1]:
        next_cursor = cursor.get(segment)
        if not isinstance(next_cursor, dict):
            next_cursor = {}
            cursor[segment] = next_cursor
        cursor = next_cursor
    cursor[segments[-1]] = value


def read_posture_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current value for every registered posture field."""

    profile = _read_profile(paths)
    elections_rows = _read_csv_rows(paths.elections_path)
    elections_by_pair = {
        (row.get("jurisdiction", ""), row.get("key", "")): row.get("value", "")
        for row in elections_rows
    }

    de_assumptions_path = paths.tax_positions_root / "de-model-assumptions.csv"
    de_assumptions_rows = _read_csv_rows(de_assumptions_path)
    de_assumptions_by_pair = {
        (row.get("section", ""), row.get("key", "")): row.get("value", "")
        for row in de_assumptions_rows
    }

    state: dict[str, Any] = {}
    for field_def in POSTURE_REGISTRY:
        state[field_def.key] = _read_field_value(
            field_def,
            profile=profile,
            elections_by_pair=elections_by_pair,
            de_assumptions_by_pair=de_assumptions_by_pair,
        )
    return state


def _read_field_value(
    field_def: PostureField,
    *,
    profile: dict[str, Any],
    elections_by_pair: dict[tuple[str, str], str],
    de_assumptions_by_pair: dict[tuple[str, str], str],
) -> Any:
    if field_def.storage == STORAGE_PROFILE_JSON:
        value = _profile_get(profile, field_def.key)
        if value is None:
            return field_def.default
        return value

    if field_def.storage == STORAGE_ELECTIONS_CSV:
        meta = dict(field_def.storage_meta)
        jurisdiction = meta.get("jurisdiction", "")
        csv_key = meta.get("csv_key", field_def.key.split(".")[-1])
        raw = elections_by_pair.get((jurisdiction, csv_key), "")
        return raw or field_def.default

    if field_def.storage == STORAGE_DE_MODEL_ASSUMPTIONS:
        meta = dict(field_def.storage_meta)
        section = meta.get("section", "")
        csv_key = meta.get("csv_key", field_def.key)
        raw = de_assumptions_by_pair.get((section, csv_key), "")
        return raw or field_def.default

    raise ValueError(
        f"Unknown storage backend for posture {field_def.key!r}: "
        f"{field_def.storage!r}. The registry must use one of "
        "'profile_json', 'elections_csv', or 'de_model_assumptions_csv'."
    )


# ---------------------------------------------------------------------------
# Validation.
# ---------------------------------------------------------------------------
class PostureValidationError(ValueError):
    """Raised when a posture update violates the registry constraints."""


def _coerce_for_widget(field_def: PostureField, raw: Any) -> Any:
    """Normalize an incoming value to the type the widget implies. Strings
    pass through for radio/select/text; numbers come as Decimal-friendly
    strings; checkboxes coerce to bool."""

    if field_def.widget == "checkbox":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            text = raw.strip().lower()
            if text in {"true", "1", "yes", "y"}:
                return True
            if text in {"false", "0", "no", "n", ""}:
                return False
        if raw is None:
            return False
        if isinstance(raw, (int, float)):
            return bool(raw)
        raise PostureValidationError(
            f"{field_def.label}: must be a yes/no value (true or false). "
            f"You sent {raw!r}. Please use the checkbox to set it."
        )
    if field_def.widget in {"radio", "select"}:
        if raw is None:
            return ""
        return str(raw)
    if field_def.widget == "number":
        if raw is None or raw == "":
            return ""
        return str(raw)
    if raw is None:
        return ""
    return str(raw)


def validate_state(submitted: dict[str, Any]) -> dict[str, Any]:
    """Validate a full posture-state dict and return a normalized copy.

    Raises ``PostureValidationError`` on the first violation.
    """

    index = _registry_index()
    normalized: dict[str, Any] = {}

    # First pass: type/option validation per-field.
    for key, raw in submitted.items():
        if key not in index:
            raise PostureValidationError(
                f"Unknown posture key: {key!r}. Please use one of the "
                "documented posture keys; the registry is the source of "
                "truth and the form should not be sending anything new."
            )
        field_def = index[key]
        value = _coerce_for_widget(field_def, raw)
        if field_def.widget in {"radio", "select"} and value != "":
            allowed = {option_value for option_value, _ in field_def.options}
            if value not in allowed:
                raise PostureValidationError(
                    f"{field_def.label}: '{value}' is not one of the "
                    f"available options. Please pick one of: "
                    f"{sorted(allowed)}."
                )
        normalized[key] = value

    # Fill defaults for any registered field the caller omitted, so we can
    # evaluate ``requires`` against a complete view.
    for field_def in POSTURE_REGISTRY:
        if field_def.key not in normalized:
            normalized[field_def.key] = field_def.default

    # Required fields: must not be missing/empty (after coercion).
    for field_def in POSTURE_REGISTRY:
        if not field_def.required:
            continue
        value = normalized[field_def.key]
        if field_def.widget in {"radio", "select"} and (value is None or value == ""):
            raise PostureValidationError(
                f"{field_def.label}: this choice is required. Please pick "
                "one of the listed options before saving."
            )

    # ``requires`` preconditions must hold.
    for field_def in POSTURE_REGISTRY:
        if not field_def.requires:
            continue
        value = normalized[field_def.key]
        # Only enforce when the dependent field is "active" — i.e. the user
        # has elected the boolean true, or selected a non-default radio. For
        # checkboxes only enforce when value is True.
        active = bool(value) if field_def.widget == "checkbox" else (value not in (None, ""))
        if not active:
            continue
        for required_key, required_value in field_def.requires:
            actual = normalized.get(required_key)
            if actual != required_value:
                raise PostureValidationError(
                    f"{field_def.label}: this option requires "
                    f"{required_key} to equal {required_value!r}, but it "
                    f"is currently {actual!r}. Please change "
                    f"{required_key} first, or turn off this option."
                )

    return normalized


# ---------------------------------------------------------------------------
# Writing posture state back to disk.
# ---------------------------------------------------------------------------
def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    # Build CSV text in memory and atomic_write_text it (invariant I9 —
    # unique temp filename + parent fsync) so a concurrent writer or a
    # crash mid-write cannot leave a torn or empty CSV on disk.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    atomic_write_text(path, buffer.getvalue())


def _bool_to_csv_text(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def write_posture_state(paths: YearPaths, submitted: dict[str, Any]) -> dict[str, Any]:
    """Persist a validated posture-state dict back to profile.json + CSVs.

    Returns the post-write state dict as ``read_posture_state`` would report
    it, so the API caller can confirm the round-trip.
    """

    normalized = validate_state(submitted)
    profile = _read_profile(paths)

    # First pass: profile.json updates.
    for field_def in POSTURE_REGISTRY:
        if field_def.storage != STORAGE_PROFILE_JSON:
            continue
        if field_def.key not in normalized:
            continue
        value = normalized[field_def.key]
        # Filing posture fields normalize through the existing helpers so we
        # store the canonical "married_joint" / "mfs_nra_spouse" tokens that
        # the rest of the engine expects.
        if field_def.key == "jurisdictions.germany.filing_posture":
            value = _normalize_germany_filing_posture(str(value))
        elif field_def.key == "jurisdictions.usa.filing_posture":
            value = _normalize_usa_filing_posture(str(value))
        _profile_set(profile, field_def.key, value)

    atomic_write_text(
        paths.profile_path, json.dumps(profile, indent=2) + "\n"
    )

    # Second pass: elections.csv updates. We currently write filing-posture
    # rows so the CSV-driven sync step can pick them up the next time anyone
    # edits the wizard's household form. We do NOT clobber the legacy CSV
    # rows for fields not represented in the registry.
    elections_rows = _read_csv_rows(paths.elections_path)
    elections_by_pair: dict[tuple[str, str], dict[str, str]] = {
        (row.get("jurisdiction", ""), row.get("key", "")): dict(row) for row in elections_rows
    }

    def _upsert_csv(jurisdiction: str, key: str, value: str, note: str) -> None:
        pair = (jurisdiction, key)
        existing = elections_by_pair.get(pair, {
            "jurisdiction": jurisdiction,
            "key": key,
            "value": "",
            "source": "intake_wizard",
            "note": note,
        })
        existing["value"] = value
        existing["source"] = existing.get("source") or "intake_wizard"
        existing["note"] = existing.get("note") or note
        elections_by_pair[pair] = existing

    germany_posture = normalized.get("jurisdictions.germany.filing_posture")
    if germany_posture:
        _upsert_csv(
            "germany",
            "filing_posture",
            _display_germany_filing_posture(str(germany_posture)),
            "Germany filing posture (posture registry).",
        )
    usa_posture = normalized.get("jurisdictions.usa.filing_posture")
    if usa_posture:
        _upsert_csv(
            "usa",
            "filing_posture",
            _display_usa_filing_posture(str(usa_posture)),
            "U.S. filing posture (posture registry).",
        )
    elect_joint = normalized.get("elections.elect_joint_return_with_nra_spouse")
    if elect_joint is not None:
        _upsert_csv(
            "usa",
            "elect_joint_return_with_nra_spouse",
            _bool_to_csv_text(elect_joint),
            "§ 6013(g) joint election with NRA spouse (posture registry).",
        )
    use_treaty = normalized.get("elections.use_treaty_resourcing")
    if use_treaty is not None:
        _upsert_csv(
            "usa",
            "use_treaty_resourcing",
            _bool_to_csv_text(use_treaty),
            "U.S. treaty re-sourcing election (posture registry).",
        )
    ftc_method = normalized.get("elections.us_ftc_method")
    if ftc_method:
        _upsert_csv(
            "usa",
            "us_ftc_method",
            str(ftc_method),
            "U.S. FTC accounting basis (posture registry).",
        )

    _write_csv(paths.elections_path, ELECTIONS_COLUMNS, list(elections_by_pair.values()))

    # Third pass: de-model-assumptions.csv updates.
    de_assumptions_path = paths.tax_positions_root / "de-model-assumptions.csv"
    de_rows = _read_csv_rows(de_assumptions_path)
    de_by_pair: dict[tuple[str, str], dict[str, str]] = {
        (row.get("section", ""), row.get("key", "")): dict(row) for row in de_rows
    }
    de_columns = ["section", "key", "value", "source", "note"]

    for field_def in POSTURE_REGISTRY:
        if field_def.storage != STORAGE_DE_MODEL_ASSUMPTIONS:
            continue
        if field_def.key not in normalized:
            continue
        meta = dict(field_def.storage_meta)
        section = meta.get("section", "")
        csv_key = meta.get("csv_key", field_def.key)
        pair = (section, csv_key)
        existing = de_by_pair.get(
            pair,
            {
                "section": section,
                "key": csv_key,
                "value": "",
                "source": "intake_wizard",
                "note": "; ".join(field_def.legal_refs) or "Posture registry update.",
            },
        )
        existing["value"] = str(normalized[field_def.key])
        existing["source"] = existing.get("source") or "intake_wizard"
        existing["note"] = existing.get("note") or (
            "; ".join(field_def.legal_refs) or "Posture registry update."
        )
        de_by_pair[pair] = existing

    if de_by_pair:
        de_assumptions_path.parent.mkdir(parents=True, exist_ok=True)
        _write_csv(de_assumptions_path, de_columns, list(de_by_pair.values()))

    # Re-sync profile.json from the CSVs so the canonical view stays
    # consistent with the legacy household form path.
    if paths.profile_path.exists():
        try:
            sync_profile_from_csv_inputs(paths)
        except FileNotFoundError:
            pass

    return read_posture_state(paths)


__all__ = [
    "POSTURE_REGISTRY",
    "PostureField",
    "PostureValidationError",
    "SECTION_CROSS_JURISDICTION",
    "SECTION_DE_ELECTIONS",
    "SECTION_FILING_STATUS",
    "SECTION_TREATY",
    "SECTION_US_ELECTIONS",
    "STORAGE_DE_MODEL_ASSUMPTIONS",
    "STORAGE_ELECTIONS_CSV",
    "STORAGE_PROFILE_JSON",
    "read_posture_state",
    "serialize_registry",
    "validate_state",
    "write_posture_state",
]
