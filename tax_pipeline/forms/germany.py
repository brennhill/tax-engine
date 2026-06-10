from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from tax_pipeline.core.money import Currency
from tax_pipeline.forms._schema import load_form_schema
from tax_pipeline.forms.common import (
    clear_markdown_outputs,
    FormEntry,
    format_currency,
    legal_value_entry,
    legal_value_from_decimal,
    legal_value_from_dict,
    markdown_link,
    result_phrase,
    write_form,
)
from tax_pipeline.y2025.germany_law import (
    ELSTER_ANLAGE_AUS_2025_URL,
    ESTG_32D_URL,
    ESTG_34C_URL,
    ESTR_R_34C_URL,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import final_legal_output_path, load_final_legal_output_2025
from tax_pipeline.postures import get_posture_definition
from tax_pipeline.y2025.treaty_law import DBA_USA_ART_10_URL

SUPPORTED_YEAR = 2025
# Proposal 2 (architecture review 2026-05-04): the country tag used
# at the LegalValue boundary now sources from the jurisdiction
# registry rather than a module-level literal. Lookup happens at
# import time (the registry is static and cheap to read), but the
# tag stays a local constant so the call sites below are unchanged.
from tax_pipeline.jurisdictions import get_jurisdiction as _get_jurisdiction

GERMANY_COUNTRY = _get_jurisdiction("DE").code
MARRIED_SEPARATE_UNSUPPORTED = (
    "Germany filing posture 'married_separate' is not supported for the 2025 filing surface yet."
)


def _ensure_supported_year(paths: YearPaths) -> None:
    if paths.year != SUPPORTED_YEAR:
        raise NotImplementedError(f"Germany forms renderer currently supports {SUPPORTED_YEAR} only, got {paths.year}")


def required_germany_form_paths(paths: YearPaths) -> list[Path]:
    return [final_legal_output_path(paths)]


def _required_form_line(rows: list[dict[str, str]], form: str, line: str, path_name: str) -> dict[str, str]:
    matches = [row for row in rows if row["form"] == form and row["line"] == line]
    if not matches:
        raise FileNotFoundError(f"Missing required row {form} / {line} in {path_name}")
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one row for {form} / {line} in {path_name}")
    return matches[0]


def _required_anlage_n_entries(forms: dict, slot: str) -> list[FormEntry]:
    field_name = f"anlage_n_entries_by_slot.{slot}"
    entries_by_slot = forms.get("anlage_n_entries_by_slot")
    if not isinstance(entries_by_slot, dict):
        raise FileNotFoundError("Missing Germany final legal output field: anlage_n_entries_by_slot")
    projected_entries = entries_by_slot.get(slot)
    if not isinstance(projected_entries, list):
        raise FileNotFoundError(f"Missing Germany final legal output field: {field_name}")

    entries: list[FormEntry] = []
    for index, entry in enumerate(projected_entries, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid Germany final legal output field: {field_name}[{index}]")
        missing = [key for key in ("label", "value", "source", "notes") if key not in entry]
        if missing:
            missing_fields = ", ".join(f"{field_name}[{index}].{key}" for key in missing)
            raise FileNotFoundError(f"Missing Germany final legal output field: {missing_fields}")
        entries.append(FormEntry(entry["label"], entry["value"], source=entry["source"], notes=entry["notes"]))
    return entries


def _write_index(paths: YearPaths, results: dict, profile: dict, filing_posture: str) -> None:
    person_slots = _german_person_slots(profile)
    domestic_capital_withholding_credit = (
        results.get("capital", {}).get("domestic_capital_withholding_credit_eur", "0.00")
    )
    dher_stock_gain = results["capital"]["dher_stock_gain_eur"]
    lines = [
        f"# Germany Forms Package - {paths.year}",
        "",
        f"Final modeled result: **{result_phrase(results['refunds']['final_target_refund_eur'])}**.",
        "",
        # Filing-guide pointer (rendered after the per-Anlage files so
        # the walkthrough can reflect actual rendered Anlage contents).
        # The link is a stable filename: ``FILING-GUIDE.md`` lives next
        # to the per-Anlage Markdown in this directory.
        f"**Start here:** {markdown_link('FILING-GUIDE.md', 'FILING-GUIDE.md')} — Schritt-für-Schritt-Walkthrough für die Eingabe in ELSTER. Die Anlagen-Dateien unten sind die zugrundeliegenden Referenzen.",
        "",
        "## Filing posture",
        f"- Filing posture: `{filing_posture}`",
        "",
        "## Locked result snapshot",
        f"- Capital tax with favorable equity-fund treatment after treaty credit: `{format_currency(results['capital']['capital_tax_with_teilfreistellung_after_treaty_eur'])}`",
        f"- Other income included under § 22 Nr. 3: `{format_currency(results['refunds']['other_income_22nr3_eur'])}`",
        "",
        "## Form Files",
        f"- {markdown_link(f'{paths.year}_hauptvordruck.md', f'{paths.year}_hauptvordruck.md')}",
        *(
            f"- {markdown_link(f'{paths.year}_anlage_n_{slot['slot']}.md', f'{paths.year}_anlage_n_{slot['slot']}.md')}"
            for slot in person_slots
        ),
        *(
            f"- {markdown_link(f'{paths.year}_anlage_kap_{slot['slot']}.md', f'{paths.year}_anlage_kap_{slot['slot']}.md')}"
            for slot in person_slots
        ),
        f"- {markdown_link(f'{paths.year}_anlage_kap_inv.md', f'{paths.year}_anlage_kap_inv.md')}",
        f"- {markdown_link(f'{paths.year}_anlage_kind.md', f'{paths.year}_anlage_kind.md')}",
        f"- {markdown_link(f'{paths.year}_anlage_vorsorgeaufwand.md', f'{paths.year}_anlage_vorsorgeaufwand.md')}",
        f"- {markdown_link(f'{paths.year}_anlage_sonderausgaben.md', f'{paths.year}_anlage_sonderausgaben.md')}",
        f"- {markdown_link(f'{paths.year}_anlage_aus.md', f'{paths.year}_anlage_aus.md')}",
        f"- {markdown_link(f'{paths.year}_anlage_so.md', f'{paths.year}_anlage_so.md')}",
        "",
        "## Source Files",
        "- `final-legal-output.json`",
    ]
    if Decimal(dher_stock_gain) != Decimal("0.00"):
        lines.insert(7, f"- Equity-comp capital sidecar included: `{format_currency(dher_stock_gain)}`")
    if Decimal(domestic_capital_withholding_credit) != Decimal("0.00"):
        lines.insert(8, f"- Domestic capital withholding credited under §36: `{format_currency(domestic_capital_withholding_credit)}`")
    # Renderer boundary rule: summaries are narrative sidecars, not authority.
    # Keep the index highlights sourced from final-legal-output.json structured
    # core fields so stale markdown cannot override the Germany legal result.
    lines.extend(
        [
            "",
            "## Summary Highlights",
            f"- Chosen filing target refund: {format_currency(results['refunds']['final_target_refund_eur'])}",
            f"- Work-equipment share included: {format_currency(results['refunds']['equipment_work_share_total_eur'])}",
            f"- Other income included under § 22 Nr. 3: {format_currency(results['refunds']['other_income_22nr3_eur'])}",
        ]
    )
    (paths.germany_forms_root / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _normalize_germany_filing_posture(text: str) -> str:
    lowered = text.strip().lower()
    return {
        "single": "single",
        "joint": "married_joint",
        "married_joint": "married_joint",
        "separate": "married_separate",
        "married_separate": "married_separate",
    }.get(lowered, lowered)


def _germany_filing_posture(profile: dict) -> str:
    explicit = _normalize_germany_filing_posture(
        str(profile.get("jurisdictions", {}).get("germany", {}).get("filing_posture", ""))
    )
    if explicit:
        return explicit
    household_value = _normalize_germany_filing_posture(
        str(profile.get("household", {}).get("germany_filing_status", ""))
    )
    if household_value:
        return household_value
    spouse_name = str(profile.get("spouse", {}).get("name", "")).strip()
    if spouse_name and profile.get("german_return", {}).get("assume_joint_assessment_if_married", False):
        return "married_joint"
    return "single"


def _ensure_supported_filing_posture(posture: str) -> None:
    posture_definition = get_posture_definition("germany", posture)
    if not posture_definition.output_support.forms:
        raise NotImplementedError(MARRIED_SEPARATE_UNSUPPORTED)


def _germany_filing_posture_from_results(results: dict) -> str:
    posture = str(results.get("ordinary", {}).get("filing_posture", "")).strip()
    if not posture:
        raise FileNotFoundError("Missing Germany final legal output field: results.ordinary.filing_posture")
    return _normalize_germany_filing_posture(posture)


def _german_person_slots(profile: dict) -> list[dict]:
    configured = profile.get("german_return", {}).get("person_slots")
    if configured:
        return configured
    taxpayer_name = profile.get("taxpayer", {}).get("name", "").strip()
    spouse_name = profile.get("spouse", {}).get("name", "").strip()
    return [
        {
            "slot": "person_1",
            "order_label": "Person 1",
            "display_name": taxpayer_name,
            "owner": None,
            "anlage_n_label": "Anlage N (Person 1)",
            "anlage_kap_label": "Anlage KAP - Person 1",
            # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze
            # 5 und 6 EStG; former 2024 KAP per-bucket lines for
            # Termingeschäfte (positives, losses) and Uneinbringlichkeit
            # are removed for VZ 2025. BMF-VERIFIED 2026-05-13.
            "kap_lines": ["4", "17", "19", "20", "23", "41"],
            "kap_raw_lines": [],
            "kap_posture": "Use person 1's foreign-capital package.",
            "kap_notes": ["Use the audited foreign-capital line summary for this person."],
        },
        {
            "slot": "person_2",
            "order_label": "Person 2",
            "display_name": spouse_name,
            "owner": None,
            "anlage_n_label": "Anlage N (Person 2)",
            "anlage_kap_label": "Anlage KAP - Person 2",
            "kap_lines": ["4", "5", "7", "8", "17", "37", "38", "40"],
            "kap_raw_lines": ["5"],
            "kap_posture": "Use person 2's separate bank-certificate capital schedule.",
            "kap_notes": ["The Upvest certificate remains separate from the Schwab reconstruction."],
        },
    ]


def _person_heading(person: dict) -> str:
    display_name = (person.get("display_name") or "").strip()
    if display_name:
        return f"{person['order_label']} ({display_name})"
    return person["order_label"]


def _read_people_rows_for_identity(paths: YearPaths) -> list[dict[str, str]]:
    """Read people.csv as ordered identity records for Hauptvordruck Z7-9.

    Returns a list of {german_tax_id, display_name, first_name, last_name,
    relationship_role, elster_order} dicts. Missing file → empty list
    (renderer falls back to "(missing — complete from workspace people.csv)"
    placeholders, the fail-closed posture).
    """
    if not paths.people_path.exists():
        return []
    import csv as _csv
    with paths.people_path.open(newline="", encoding="utf-8") as handle:
        rows = list(_csv.DictReader(handle))
    rows.sort(
        key=lambda r: (
            int(r.get("elster_order") or "999")
            if (r.get("elster_order") or "").isdigit()
            else 999
        )
    )
    return rows


def _read_banking_for_hauptvordruck(paths: YearPaths) -> dict[str, str]:
    """Read banking config for Hauptvordruck Zeilen 75-78 (refund IBAN/BIC).

    The 2025 BMF Hauptvordruck Zeilen 75-78 are the Erstattungs-Kontoangaben:
    Zeile 75 IBAN, Zeile 76 BIC, Zeile 77 contoinhaber:in (account holder),
    Zeile 78 banking institution. The engine does NOT model banking
    workspace facts today (no derived/extracted banking fact); the
    renderer reads optional ``profile.banking`` fields directly. When
    absent, every row renders the placeholder
    "(missing — complete from workspace banking config)" — the
    fail-closed auditable-absence pattern from CLAUDE.md.
    """
    profile_dict: dict = {}
    if paths.profile_path.exists():
        try:
            import json as _json
            profile_dict = _json.loads(paths.profile_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - missing/malformed profile is non-fatal
            profile_dict = {}
    banking = profile_dict.get("banking") or {}
    if not isinstance(banking, dict):
        banking = {}
    return {
        "iban": str(banking.get("iban") or "").strip(),
        "bic": str(banking.get("bic") or "").strip(),
        "account_holder": str(banking.get("account_holder") or "").strip(),
        "institution": str(banking.get("institution") or "").strip(),
    }


_HAUPTVORDRUCK_MISSING_PLACEHOLDER = "(missing — complete from workspace config)"


def _identity_value(value: str) -> str:
    """Render an identity field value or the fail-closed placeholder."""
    return value.strip() if value and value.strip() else _HAUPTVORDRUCK_MISSING_PLACEHOLDER


def _write_hauptvordruck(paths: YearPaths, results: dict, profile: dict, filing_posture: str) -> None:
    """Render Mantelbogen / Hauptvordruck 2025 with identity + banking rows.

    C6 (FORM-MAPPING-FOLLOWUP, 2026-05-03). Adds non-currency identity
    rows from ``people.csv`` (Steuer-IdNr Z7-9), Veranlagungswahl
    (Z23-25, derived from filing posture + profile.spouse.name), and
    refund banking (Z75-78) read from ``profile.banking``. When any
    field is empty / missing, the renderer emits the explicit
    placeholder ``(missing — complete from workspace config)`` rather
    than fabricating values — fail-closed posture per CLAUDE.md.

    Identity strings are NOT legal values (no monetary amount); they
    travel as plain ``FormEntry(value=str)`` rows and do not transit
    the I11 ``legal_value_entry`` boundary. The bottom-line refund
    estimation row remains an audit-only summary of
    ``results["refunds"]["final_target_refund_eur"]`` (already
    fingerprinted by DE25-22-FINAL-REFUND).

    Authority:
    - Hauptvordruck (ESt 1A 2025), BMF Steuerformular (PDF download
      from https://www.formulare-bfinv.de/) — non-currency identity and
      Erstattungskonto fields.
    - § 25 EStG, § 26 EStG, § 26b EStG (Veranlagungswahl):
      https://www.gesetze-im-internet.de/estg/__26.html
    - § 36 Abs. 4 EStG (Erstattung — refund disposition):
      https://www.gesetze-im-internet.de/estg/__36.html
    """
    if filing_posture == "single":
        filing_value = "Einzelveranlagung (single)"
        veranlagung_kind = "Einzelveranlagung nach § 25 EStG"
    elif filing_posture == "married_separate":
        filing_value = "Einzelveranlagung verheirateter Personen (married separate, § 26a EStG)"
        veranlagung_kind = "Einzelveranlagung Ehegatten/Lebenspartner § 26a EStG"
    elif filing_posture == "married_joint":
        filing_value = "Zusammenveranlagung (joint, § 26b EStG)"
        veranlagung_kind = "Zusammenveranlagung Ehegatten/Lebenspartner § 26b EStG"
    else:
        filing_value = "Review profile"
        veranlagung_kind = _HAUPTVORDRUCK_MISSING_PLACEHOLDER

    people_rows = _read_people_rows_for_identity(paths)
    taxpayer_row: dict[str, str] = {}
    spouse_row: dict[str, str] = {}
    for row in people_rows:
        role = str(row.get("relationship_role") or "").strip().lower()
        if not taxpayer_row and (role == "taxpayer" or row.get("is_taxpayer", "").strip().lower() in {"true", "1", "yes"}):
            taxpayer_row = row
        elif not spouse_row and (role == "spouse" or row.get("is_spouse", "").strip().lower() in {"true", "1", "yes"}):
            spouse_row = row
    # Fallback ordering for workspaces lacking explicit role flags.
    if not taxpayer_row and people_rows:
        taxpayer_row = people_rows[0]
    if not spouse_row and len(people_rows) > 1:
        spouse_row = people_rows[1]

    banking = _read_banking_for_hauptvordruck(paths)

    spouse_name = str((profile.get("spouse") or {}).get("name") or "").strip()
    is_joint = filing_posture == "married_joint"
    schema = load_form_schema("hauptvordruck")

    identity_entries: list[FormEntry] = [
        FormEntry(
            schema.label("identifikation"),
            filing_value,
            source="config/profile.json",
        ),
        # Z7-9 — Steuer-Identifikationsnummer of the taxpayer (Z7) and
        # spouse (Z8/Z9 carry name + IdNr of the joint-assessed
        # partner). § 139b AO governs the Steuer-IdNr; ELSTER assigns
        # one unique 11-digit number per natural person for life.
        FormEntry(
            schema.label("zeile_7_steuer_idnr_taxpayer"),
            _identity_value(taxpayer_row.get("german_tax_id", "")),
            source="config/people.csv",
            notes=(
                f"Taxpayer name: {_identity_value(taxpayer_row.get('display_name', ''))}. "
                "§ 139b AO Steuer-Identifikationsnummer."
            ),
        ),
        FormEntry(
            schema.label("zeile_8_name_spouse"),
            _identity_value(spouse_row.get("display_name", spouse_name)),
            source="config/people.csv / config/profile.json",
            notes=(
                "Filled only on joint assessment (§ 26b EStG); empty rows "
                "OK for single posture."
                if not is_joint
                else "Joint assessment per § 26b EStG."
            ),
        ),
        FormEntry(
            schema.label("zeile_9_steuer_idnr_spouse"),
            _identity_value(spouse_row.get("german_tax_id", "")),
            source="config/people.csv",
            notes=(
                "Filled only on joint assessment (§ 26b EStG)."
                if not is_joint
                else "§ 139b AO Steuer-Identifikationsnummer of the joint-assessed partner."
            ),
        ),
        # Z23-25 — Veranlagungswahl. § 26 EStG offers four postures
        # (Einzel / Zusammen / Sondersituation Trennungsjahr). Z23
        # confirms the chosen posture; Z24-25 are the Wahl-of-each-
        # spouse rows that the joint return shares.
        FormEntry(
            schema.label("zeile_23_veranlagungsart"),
            veranlagung_kind,
            source="config/profile.json (jurisdictions.germany.filing_posture)",
            notes="§ 25 / § 26 / § 26a / § 26b EStG — chosen Veranlagungsart.",
        ),
        FormEntry(
            schema.label("zeile_24_wahl_taxpayer"),
            _identity_value(taxpayer_row.get("display_name", "")),
            source="config/people.csv",
            notes="Confirms the taxpayer's election of the chosen Veranlagungsart.",
        ),
        FormEntry(
            schema.label("zeile_25_wahl_spouse"),
            _identity_value(spouse_row.get("display_name", spouse_name)) if is_joint else "(n/a — single posture)",
            source="config/people.csv / config/profile.json",
            notes=(
                "Confirms the spouse/partner's election of the chosen Veranlagungsart "
                "(§ 26 Abs. 1, Abs. 2 EStG joint election)."
                if is_joint
                else "Joint-assessment-only field; left blank under single posture."
            ),
        ),
        # Z75-78 — Erstattungs-Kontoangaben. § 36 Abs. 4 EStG governs
        # the refund disposition. The renderer does not own banking
        # workspace facts today; user completes from a banking config
        # block (profile.banking.{iban, bic, account_holder, institution}).
        FormEntry(
            schema.label("zeile_75_iban"),
            _identity_value(banking["iban"]),
            source="config/profile.json (banking.iban)",
            notes="§ 36 Abs. 4 EStG — refund disposition account.",
        ),
        FormEntry(
            schema.label("zeile_76_bic"),
            _identity_value(banking["bic"]),
            source="config/profile.json (banking.bic)",
            notes="§ 36 Abs. 4 EStG — BIC of the refund-disposition bank.",
        ),
        FormEntry(
            schema.label("zeile_77_account_holder"),
            _identity_value(banking["account_holder"]),
            source="config/profile.json (banking.account_holder)",
            notes="§ 36 Abs. 4 EStG — account holder name (must match Steuerpflichtige:r unless joint).",
        ),
        FormEntry(
            schema.label("zeile_78_institution"),
            _identity_value(banking["institution"]),
            source="config/profile.json (banking.institution)",
            notes="§ 36 Abs. 4 EStG — banking institution name.",
        ),
        FormEntry(
            schema.label("estimation"),
            result_phrase(results["refunds"]["final_target_refund_eur"]),
            source="germany-model-results.json",
            notes=(
                "Audit summary of de.final.target_refund_eur produced by "
                "DE25-22-FINAL-REFUND; the Mantelbogen does not carry an "
                "input row for the refund — the value is computed by the "
                "Finanzamt from § 36 / § 31 / treaty rows on Anlagen."
            ),
        ),
        FormEntry(
            schema.label("prepayment_note"),
            "See audit note",
            source="germany-elster-entry-sheet.md",
            notes="The prepayment is not transmitted as a filing line.",
        ),
    ]

    write_form(
        paths.germany_forms_root / f"{paths.year}_hauptvordruck.md",
        f"{paths.year} {schema.display_name}",
        [
            "Reflect the audited entry sheet and saved model outputs.",
            "Identity rows (Z7-9) come from ``config/people.csv``; "
            "Veranlagungswahl rows (Z23-25) derive from "
            "``profile.jurisdictions.germany.filing_posture``; "
            "Erstattungs-Kontoangaben (Z75-78) come from "
            "``profile.banking`` when configured.",
            "Missing identity / banking values render as the explicit "
            "placeholder ``" + _HAUPTVORDRUCK_MISSING_PLACEHOLDER + "`` — "
            "the fail-closed posture from CLAUDE.md (no silent default).",
            "Keep prepayment handling source-aligned and audit-only.",
        ],
        identity_entries,
        [
            "Summary source: `germany-summary.md`.",
            "Entry sheet source: `germany-elster-entry-sheet.md`.",
            "Authority for Steuer-Identifikationsnummer fields (Z7-9): "
            "§ 139b AO (https://www.gesetze-im-internet.de/ao_1977/__139b.html).",
            "Authority for Veranlagungswahl (Z23-25): § 25 / § 26 / § 26a / § 26b EStG "
            "(https://www.gesetze-im-internet.de/estg/__26.html).",
            "Authority for Erstattungs-Kontoangaben (Z75-78): § 36 Abs. 4 EStG "
            "(https://www.gesetze-im-internet.de/estg/__36.html).",
        ],
    )


def _write_anlage_n_for_person(
    paths: YearPaths,
    person: dict,
    entries: list[FormEntry],
) -> None:
    schema = load_form_schema("anlage_n")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_n_{person['slot']}.md",
        f"{paths.year} {schema.display_name} - {_person_heading(person)}",
        [
            "Keep the filing aligned with the audited outputs.",
            "No extra employee-expense deductions are introduced by the renderer.",
        ],
        entries,
        [
            "Source note: `germany-elster-entry-sheet.md`.",
        ],
    )


def _write_anlage_kap_for_person(
    paths: YearPaths,
    person: dict,
    rows: list[dict[str, str]],
    provenance: Mapping[str, Any] | None,
) -> None:
    schema = load_form_schema("anlage_kap")

    def kap_entry(line: str) -> FormEntry:
        row = _required_form_line(rows, person["anlage_kap_label"], line, "germany-kap-summary.csv")
        # ``kap_raw_lines`` are non-currency fields (account counts, etc.) — they
        # render as raw strings, not legal values. Currency lines transit
        # ``legal_value_entry`` so the I11 boundary is load-bearing.
        if line in person.get("kap_raw_lines", []):
            return FormEntry(
                schema.label(line),
                row["amount_eur"],
                source="germany-kap-summary.csv",
                notes=row["note"],
            )
        # A4 (FORM-MAPPING-FOLLOWUP): Anlage KAP Zeile 4 is the only KAP
        # line that maps 1:1 onto a single declared rule output
        # (``de.capital.sparer_pauschbetrag_claimed_eur`` from
        # DE25-16-SECTION-20-9-SAVER). Bind its provenance lookup key
        # to that output_key so the renderer reads the executor's
        # StageResult fingerprint from
        # ``_provenance.form_lines.DE`` rather than synthesizing a
        # ``renderer:DE:anlage_kap...`` triple. Every other KAP Zeile
        # is a renderer-side projection of multiple rule outputs
        # (e.g., Z19 aggregates multiple per-symbol values), so they
        # rightfully take the synthesized fingerprint via the
        # default ``provenance_output_key=None`` path.
        # § 20 Abs. 9 Satz 1/2 EStG — https://www.gesetze-im-internet.de/estg/__20.html
        provenance_output_key = (
            "de.capital.sparer_pauschbetrag_claimed_eur" if line == "4" else None
        )
        return legal_value_entry(
            schema.label(line),
            legal_value_from_dict(
                row,
                "amount_eur",
                country=GERMANY_COUNTRY,
                section=f"anlage_kap.{person['slot']}.zeile_{line}",
                provenance=provenance,
                provenance_output_key=provenance_output_key,
            ),
            currency=Currency.EUR,
            source="germany-kap-summary.csv",
            notes=row["note"],
        )

    # A4 (FORM-MAPPING-FOLLOWUP): Anlage KAP Zeile 4
    # (Sparer-Pauschbetrag claim line) is mandatory on every Anlage
    # KAP regardless of profile.json ``kap_lines``. Prepend it
    # unconditionally so older workspaces that omit "4" from the
    # configured list still get the statutory €1,000 / €2,000 claim
    # rendered. The kap_summary_rows projection emits the row
    # ``[anlage_kap_label, "4", saver_allowance_eur, …]`` for each
    # person from ``de.capital.sparer_pauschbetrag_claimed_eur``
    # (DE25-16 rule output).
    # § 20 Abs. 9 Satz 1/2 EStG — https://www.gesetze-im-internet.de/estg/__20.html
    configured_lines = list(person["kap_lines"])
    kap_lines = ["4", *configured_lines] if "4" not in configured_lines else configured_lines
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_kap_{person['slot']}.md",
        f"{paths.year} {schema.display_name} - {_person_heading(person)}",
        [
            person["kap_posture"],
            "This file reproduces the already-audited line summary.",
        ],
        [kap_entry(line) for line in kap_lines],
        ["The current file is source-oriented and does not recalculate any tax.", *person["kap_notes"]],
    )


def _write_anlage_kap_inv(
    paths: YearPaths,
    rows: list[dict[str, str]],
    fund_rows: list[dict[str, str]],
    provenance: Mapping[str, Any] | None,
) -> None:
    top_funds = sorted(fund_rows, key=lambda row: abs(float(row["combined_eur"])), reverse=True)[:5]
    schema = load_form_schema("anlage_kap_inv")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_kap_inv.md",
        f"{paths.year} {schema.display_name}",
        [
            "Use the audited fund summary and per-fund support file.",
            "The renderer only reformats existing output artifacts.",
        ],
        [
            legal_value_entry(
                schema.label("zeile_4"),
                legal_value_from_dict(
                    _required_form_line(rows, "Anlage KAP-INV", "4", "germany-kap-summary.csv"),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kap_inv.zeile_4",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kap-summary.csv",
                notes=_required_form_line(rows, "Anlage KAP-INV", "4", "germany-kap-summary.csv")["note"],
            ),
            legal_value_entry(
                schema.label("zeile_8"),
                legal_value_from_dict(
                    _required_form_line(rows, "Anlage KAP-INV", "8", "germany-kap-summary.csv"),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kap_inv.zeile_8",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kap-summary.csv",
                notes=_required_form_line(rows, "Anlage KAP-INV", "8", "germany-kap-summary.csv")["note"],
            ),
            legal_value_entry(
                schema.label("zeilen_9_13"),
                legal_value_from_dict(
                    _required_form_line(rows, "Anlage KAP-INV", "9-13", "germany-kap-summary.csv"),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kap_inv.zeile_9_13",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kap-summary.csv",
                notes=_required_form_line(rows, "Anlage KAP-INV", "9-13", "germany-kap-summary.csv")["note"],
            ),
            legal_value_entry(
                schema.label("zeile_14"),
                legal_value_from_dict(
                    _required_form_line(rows, "Anlage KAP-INV", "14", "germany-kap-summary.csv"),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kap_inv.zeile_14",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kap-summary.csv",
                notes=_required_form_line(rows, "Anlage KAP-INV", "14", "germany-kap-summary.csv")["note"],
            ),
            legal_value_entry(
                schema.label("zeile_26"),
                legal_value_from_dict(
                    _required_form_line(rows, "Anlage KAP-INV", "26", "germany-kap-summary.csv"),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kap_inv.zeile_26",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kap-summary.csv",
                notes=_required_form_line(rows, "Anlage KAP-INV", "26", "germany-kap-summary.csv")["note"],
            ),
        ],
        [
            "Top per-fund rows are preserved below for cross-checking.",
            *(
                f"{row['symbol']}: {row['combined_eur']} EUR ({row['fund_type']})"
                for row in top_funds
            ),
        ],
    )


def _write_anlage_kind(
    paths: YearPaths,
    rows: list[dict[str, str]],
    results: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Anlage Kind 2025 — Z6-15 Kinderfreibetrag/BEA + Z65 § 33b transferral.

    Anlage Kind 2025 carries two distinct legal-relief surfaces:

    **Z6-15 — Kinderfreibetrag + BEA-Freibetrag per § 32 Abs. 6 EStG.**
    Per-child identifier rows (Z6-15 contain Steuer-IdNr, Name,
    Geburtsdatum, Verwandtschaftsverhältnis, Kindschaftsverhältnis as
    non-currency attestation fields) plus the per-child € 6,672 / parent
    Kinderfreibetrag share + €2,928 / parent BEA-Freibetrag share. The
    household total surfaced here is the aggregated value
    (``de.children.kinderfreibetrag_total_eur``) feeding the
    § 31 EStG Satz 1 Günstigerprüfung in DE25-CHILDREN-CREDITS. When
    ``qualifying_children_count == 0`` the renderer emits an explicit
    0.00 row + posture note "no qualifying children present" — the
    fail-closed auditable-absence posture per CLAUDE.md.

    **Z64-66 — § 33b Abs. 5 EStG transferred Pauschbetrag.**
    The Zeile-64 / Zeile-65 / Zeile-66 form-surface assignment is the
    legal-transferral subset of § 33b Abs. 5 EStG per
    https://www.gesetze-im-internet.de/estg/__33b.html.
    Zeile 64: attestation / qualifying conditions (the child does not
    claim the Pauschbetrag in their own assessment, per § 33b Abs. 5
    BMF-VERIFIED 2026-05-11 — § 33b Abs. 5 EStG Satz 1.
    Satz 1 EStG).
    Zeile 65: per-child Pauschbetrag EUR amount, transferred to the
    BMF-VERIFIED 2026-05-11 — § 33b Abs. 5 EStG Satz 2 hälftige Übertragung.
    parents' assessment per § 33b Abs. 5 Satz 1/2 EStG.
    Zeile 66: optional anderweitige prozentuale Aufteilung between the
    BMF-VERIFIED 2026-05-11 — § 33b Abs. 5 EStG Satz 3 Aufteilungswahl.
    parents per § 33b Abs. 5 Satz 3 EStG (the joint-election clause;
    default 50/50 if Zeile 66 is left blank).

    The legally-effective EUR amounts come from
    ``DE25-CHILDREN-CREDITS`` and
    ``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG``; the renderer threads
    each through the I11 LegalValue envelope.

    Authority:
    - § 32 Abs. 6 EStG: https://www.gesetze-im-internet.de/estg/__32.html
    - § 31 EStG: https://www.gesetze-im-internet.de/estg/__31.html
    - § 33b Abs. 3 EStG: https://www.gesetze-im-internet.de/estg/__33b.html
    - § 33b Abs. 5 EStG: https://www.gesetze-im-internet.de/estg/__33b.html
    - § 33b Abs. 5 Satz 3 EStG: https://www.gesetze-im-internet.de/estg/__33b.html
    - BMF Anlage Kind 2025: BMF Steuerformular id 034025_25
      (Helfer in Steuersachen 2.9.0 Zeilen 64-66 confirms the line range).
    F-DE-VERIFIED-AGAINST-BMF-2025: 2026-05-02
    """
    children = results.get("children", {})
    qualifying_children_count = int(children.get("qualifying_children_count", 0))
    posture_lines = [
        "Z6-15 (per § 32 Abs. 6 EStG): per-child Kinderfreibetrag + "
        "BEA-Freibetrag aggregate. Identity rows (Steuer-IdNr, Name, "
        "Geburtsdatum, Verwandtschaftsverhältnis) are non-currency "
        "attestation fields completed from the workspace ``children.csv``.",
        "Reflect the audited § 33b Abs. 5 EStG transferral on Zeile 65; "
        "complete Zeile 64 (attestation) and Zeile 66 (split override) "
        "from the workspace profile.",
        "No legal math is introduced by the renderer — every EUR amount "
        "is a declared rule output (DE25-CHILDREN-CREDITS / "
        "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG) re-emitted through the "
        "I11 LegalValue boundary.",
    ]
    if qualifying_children_count == 0:
        posture_lines.append(
            "Posture: NO qualifying children present in this workspace "
            "(``de.children.qualifying_children_count`` == 0). Per "
            "CLAUDE.md fail-closed posture, every EUR row renders as "
            "an explicit 0.00 to make the auditable absence "
            "structurally visible — never silently default to zero."
        )
    schema = load_form_schema("anlage_kind")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_kind.md",
        f"{paths.year} {schema.display_name}",
        posture_lines,
        [
            # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): label format
            # is ``Anlage Kind Zeilen 6-15`` so the I3 scanner can
            # extract the destination Zeile range (the parenthetical
            # description moved to ``notes``).
            legal_value_entry(
                schema.label("zeilen_6_15"),
                legal_value_from_dict(
                    children,
                    "kinderfreibetrag_total_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kind.zeilen_6_15",
                    provenance=provenance,
                    provenance_output_key="de.children.kinderfreibetrag_total_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "Kinderfreibetrag + BEA, household total. § 32 Abs. 6 "
                    "EStG household-aggregate Kinderfreibetrag + BEA-"
                    "Freibetrag. Per-child identity rows (Steuer-IdNr, "
                    "Name, Geburtsdatum) come from the workspace "
                    "children.csv; this row is the household € total "
                    "produced by DE25-CHILDREN-CREDITS for the "
                    "§ 31 EStG Günstigerprüfung."
                ),
            ),
            legal_value_entry(
                schema.label("kindergeld_audit"),
                legal_value_from_dict(
                    children,
                    "kindergeld_total_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kind.kindergeld_total",
                    provenance=provenance,
                    provenance_output_key="de.children.kindergeld_total_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "BKGG § 6 Abs. 2 — total Kindergeld received in the "
                    "household across the year. Cross-check input for "
                    "the § 31 EStG Satz 1 Günstigerprüfung; the chosen "
                    "relief on the return is one of (a) Kinderfreibetrag, "
                    "(b) Kindergeld, never both."
                ),
            ),
            legal_value_entry(
                schema.label("guenstigerpruefung_audit"),
                legal_value_from_dict(
                    children,
                    "kinderfreibetrag_tax_saving_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kind.guenstigerpruefung_saving",
                    provenance=provenance,
                    provenance_output_key="de.children.kinderfreibetrag_tax_saving_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "§ 31 EStG Satz 1 counterfactual: tariff at zvE minus "
                    "tariff at zvE − Kinderfreibetrag_total_eur. When this "
                    "exceeds Kindergeld received, Kinderfreibetrag wins; "
                    "otherwise Kindergeld wins (§ 31 Satz 4 EStG netting)."
                ),
            ),
            legal_value_entry(
                schema.label("zeile_65"),
                legal_value_from_dict(
                    _required_form_line(
                        rows, "Anlage Kind", "65", "germany-kind-summary.csv"
                    ),
                    "amount_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_kind.zeile_65",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-kind-summary.csv",
                notes=_required_form_line(
                    rows, "Anlage Kind", "65", "germany-kind-summary.csv"
                )["note"],
            ),
        ],
        [
            # BMF-VERIFIED 2026-05-11 — Anlage Kind 2025 (BMF Steuerformular
            # id 034025_25) line-surface assignment per the inline statute
            # citations: § 32 Abs. 6 EStG governs the Kinderfreibetrag +
            # BEA-Freibetrag aggregate filed on Anlage Kind Z6-15;
            # § 33b Abs. 3 Satz 2/3 EStG the per-child Pauschbetrag schedule
            # filed on Z65; § 33b Abs. 5 Satz 1/2/3 EStG the parents'
            # transferral filed on Z64/Z65/Z66; all per
            # https://www.gesetze-im-internet.de/estg/__32.html,
            # https://www.gesetze-im-internet.de/estg/__33b.html.
            "Authority for the per-child Kinderfreibetrag + BEA-Freibetrag (Zeilen 6-15 amount): "
            "§ 32 Abs. 6 EStG (https://www.gesetze-im-internet.de/estg/__32.html).",
            "Authority for the § 31 EStG Günstigerprüfung (Kindergeld vs. Kinderfreibetrag): "
            "§ 31 EStG Satz 1, Satz 4 (https://www.gesetze-im-internet.de/estg/__31.html).",
            "Authority for the per-child Pauschbetrag schedule (Zeile 65 amount): "
            "§ 33b Abs. 3 Satz 2/3 EStG (https://www.gesetze-im-internet.de/estg/__33b.html).",
            "Authority for the parents' transferral (Zeilen 64-65 attestation + amount): "
            "§ 33b Abs. 5 Satz 1/2 EStG (https://www.gesetze-im-internet.de/estg/__33b.html).",
            "Authority for the 50/50 split default + Zeile 66 joint-election override: "
            "§ 33b Abs. 5 Satz 3 EStG (https://www.gesetze-im-internet.de/estg/__33b.html).",
        ],
    )


def _write_anlage_vorsorgeaufwand(
    paths: YearPaths,
    results: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Anlage Vorsorgeaufwand 2025 with per-Zeile bucket scalars.

    C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03). Anlage Vorsorgeaufwand 2025
    decomposes into three statutory buckets, each backed by a declared
    DE25-05 / DE25-06 scalar output flowing through the I11 LegalValue
    envelope:

    BMF-VERIFIED 2026-05-11 — three Zeile groupings on Anlage
    Vorsorgeaufwand 2025 bound to § 10 Abs. 1 Nr. 2 / Nr. 3 / Nr. 3a
    EStG and the § 10 Abs. 4 cap per
    https://www.gesetze-im-internet.de/estg/__10.html.

    - **Zeilen 4-9** — Beiträge zur gesetzlichen Rentenversicherung /
      berufsständischen Versorgungswerken, § 10 Abs. 1 Nr. 2 / Abs. 3
      EStG. Source: ``de.ordinary.retirement_special_expenses_total_eur``
      (DE25-05-RETIREMENT-SA).
    - **Zeilen 11-14** — Beiträge zur Kranken-/Pflegeversicherung,
      § 10 Abs. 1 Nr. 3 EStG. Source:
      ``de.ordinary.health_vorsorge_basic_health_eur``
      (DE25-06-HEALTH-VORSORGE-SA).
    BMF-VERIFIED 2026-05-11 — sonstige-Vorsorge cluster authority below.
    - **Zeilen 31-37** — sonstige Vorsorgeaufwendungen (Arbeitslosen-,
      Berufsunfähigkeits-, Haftpflicht-, Risikolebens-, Unfallversicherung),
      § 10 Abs. 1 Nr. 3a EStG, within the § 10 Abs. 4 cap. Source:
      ``de.ordinary.health_vorsorge_other_allowed_eur``
      (DE25-06-HEALTH-VORSORGE-SA).

    No legal math runs in the renderer — the three scalars are produced
    by the rule graph, fingerprinted by the executor, and re-emitted
    here under the I11 LegalValue boundary.

    Authority:
    - § 10 Abs. 1 Nr. 2, Nr. 3, Nr. 3a, Abs. 3, Abs. 4 EStG:
      https://www.gesetze-im-internet.de/estg/__10.html
    - BMF Anlage Vorsorgeaufwand 2025:
      https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Lohnsteuer-und-Einkommensteuer/Anlage-Vorsorgeaufwand/anlage-vorsorgeaufwand.html
    """
    ordinary = results["ordinary"]
    schema = load_form_schema("anlage_vorsorgeaufwand")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_vorsorgeaufwand.md",
        f"{paths.year} {schema.display_name}",
        [
            # BMF-VERIFIED 2026-05-11 — Anlage Vorsorgeaufwand 2025 Zeile
            # groupings (Z4-9 retirement, Z11-14 health, Z31-37 sonstige)
            # bound to § 10 Abs. 1 Nr. 2/3/3a EStG + § 10 Abs. 4 EStG cap
            # per https://www.gesetze-im-internet.de/estg/__10.html.
            "Beiträge zur Altersvorsorge nach § 10 Abs. 1 Nr. 2 / Abs. 3 EStG "
            "(Zeilen 4-9), Krankenversicherung/Pflegeversicherung nach "
            "§ 10 Abs. 1 Nr. 3 EStG (Zeilen 11-14) und sonstige "
            "Vorsorgeaufwendungen nach § 10 Abs. 1 Nr. 3a EStG, gedeckelt "
            "durch § 10 Abs. 4 EStG (Zeilen 31-37).",
            "No legal math is introduced by the renderer — every Zeile "
            "scalar is a declared rule output (DE25-05 / DE25-06) "
            "re-emitted through the I11 LegalValue boundary.",
        ],
        [
            legal_value_entry(
                schema.label("zeilen_4_9"),
                legal_value_from_dict(
                    ordinary,
                    "vorsorge_retirement_total_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_vorsorgeaufwand.zeilen_4_9",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.retirement_special_expenses_total_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes="§ 10 Abs. 1 Nr. 2 / Abs. 3 EStG — Beiträge zur gesetzlichen Rentenversicherung / berufsständischen Versorgungswerken.",
            ),
            legal_value_entry(
                schema.label("zeilen_11_14"),
                legal_value_from_dict(
                    ordinary,
                    "vorsorge_basic_health_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_vorsorgeaufwand.zeilen_11_14",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.health_vorsorge_basic_health_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes="§ 10 Abs. 1 Nr. 3 EStG — Beiträge zur Kranken- und Pflegeversicherung (Basisabsicherung).",
            ),
            legal_value_entry(
                schema.label("zeilen_31_37"),
                legal_value_from_dict(
                    ordinary,
                    "vorsorge_other_allowed_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_vorsorgeaufwand.zeilen_31_37",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.health_vorsorge_other_allowed_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes="§ 10 Abs. 1 Nr. 3a EStG — sonstige Vorsorgeaufwendungen (Arbeitslosen-, Berufsunfähigkeits-, Haftpflicht-, Risikolebens-, Unfallversicherung) innerhalb des § 10 Abs. 4 EStG-Höchstbetrags.",
            ),
        ],
        [
            # BMF-VERIFIED 2026-05-11 — Anlage Vorsorgeaufwand 2025 form
            # surface; the three Zeile-range groupings (4-9 retirement,
            # 11-14 Kranken/Pflege, 31-37 sonstige) match § 10 Abs. 1
            # Nr. 2/3/3a EStG and the § 10 Abs. 4 EStG cap per
            # https://www.gesetze-im-internet.de/estg/__10.html.
            "Authority for retirement Vorsorgeaufwendungen (Zeilen 4-9): "
            "§ 10 Abs. 1 Nr. 2 EStG, § 10 Abs. 3 EStG "
            "(https://www.gesetze-im-internet.de/estg/__10.html).",
            "Authority for Krankenversicherung/Pflegeversicherung (Zeilen 11-14): "
            "§ 10 Abs. 1 Nr. 3 EStG "
            "(https://www.gesetze-im-internet.de/estg/__10.html).",
            "Authority for sonstige Vorsorgeaufwendungen (Zeilen 31-37): "
            "§ 10 Abs. 1 Nr. 3a EStG within the § 10 Abs. 4 EStG cap "
            "(https://www.gesetze-im-internet.de/estg/__10.html).",
        ],
    )


def _write_anlage_sonderausgaben(
    paths: YearPaths,
    results: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Anlage Sonderausgaben 2025 with per-Zeile bucket scalars.

    C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03). Anlage Sonderausgaben 2025
    decomposes into three statutory buckets, each backed by a declared
    rule output flowing through the I11 LegalValue envelope:

    - **§ 10b EStG Spendenabzug** — charitable donations within the
      20 % GdE cap. Source: ``de.ordinary.spendenabzug_deductible_eur``
      (DE25-SPENDENABZUG).
    - **§ 33a Abs. 1 EStG Unterhaltsleistungen** — support payments
      within the Grundfreibetrag cap minus Eigenbezüge reduction.
      Source: ``de.ordinary.unterhaltsleistungen_deductible_eur``
      (DE25-UNTERHALTSLEISTUNGEN). Note: § 33a is technically
      außergewöhnliche Belastungen in besonderen Fällen, but the
      form-mapping plan groups it with the Sonderausgaben renderer
      because the deductible flows through the same § 2 Abs. 5 EStG
      assembly path.
    - **§ 10c EStG Sonderausgaben-Pauschbetrag** — statutory minimum
      lump sum (€72 joint / €36 single per-person). Source:
      ``de.ordinary.sonderausgaben_pauschbetrag_applied_eur``
      (DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG). Audit-only — the
      Finanzamt applies the Pauschbetrag automatically; the row
      surfaces the value the engine assumed for the § 2 Abs. 5
      assembly.

    No legal math runs in the renderer; the three scalars are produced
    by the rule graph, fingerprinted by the executor, and re-emitted
    here under the I11 LegalValue boundary. For workspaces with no
    Spenden / Unterhalt facts (the brenn-2025 default posture), the
    deductible rows render as 0.00 — the fail-closed auditable-absence
    pattern from CLAUDE.md.

    Authority:
    - § 10b Abs. 1 EStG (Spendenabzug):
      https://www.gesetze-im-internet.de/estg/__10b.html
    - § 33a Abs. 1 EStG (Unterhaltsleistungen):
      https://www.gesetze-im-internet.de/estg/__33a.html
    - § 10c EStG (Sonderausgaben-Pauschbetrag):
      https://www.gesetze-im-internet.de/estg/__10c.html
    """
    ordinary = results["ordinary"]
    schema = load_form_schema("anlage_sonderausgaben")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_sonderausgaben.md",
        f"{paths.year} {schema.display_name}",
        [
            "§ 10b Abs. 1 EStG Spendenabzug (Spenden / Mitgliedsbeiträge "
            "an steuerbegünstigte Körperschaften, gedeckelt auf 20 % der "
            "Gesamtbetrag der Einkünfte).",
            "§ 33a Abs. 1 EStG Unterhaltsleistungen (Unterhaltszahlungen "
            "an gesetzlich Unterhaltsberechtigte, gedeckelt durch den "
            "Grundfreibetrag minus Eigenbezüge-Reduktion).",
            "§ 10c EStG Sonderausgaben-Pauschbetrag — audit-only row; "
            "the Finanzamt applies the Pauschbetrag automatically.",
            "No legal math is introduced by the renderer — every Zeile "
            "scalar is a declared rule output (DE25-SPENDENABZUG / "
            "DE25-UNTERHALTSLEISTUNGEN / DE25-06B-SONDERAUSGABEN-"
            "PAUSCHBETRAG) re-emitted through the I11 LegalValue boundary.",
        ],
        [
            # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): label format is
            # ``Anlage <Form> Zeile N`` / ``Anlage <Form> Zeilen N-M`` so
            # the I3 scanner's German label regex can extract the
            # destination Zeile and match against the FormLineRef
            # declarations on the rule outputs (DE25-SPENDENABZUG /
            # DE25-UNTERHALTSLEISTUNGEN / DE25-06B-SONDERAUSGABEN-
            # PAUSCHBETRAG). The descriptive § citation moves to ``notes``
            # so it stays auditable without breaking the scanner regex.
            legal_value_entry(
                schema.label("spenden_zeilen_5_7"),
                legal_value_from_dict(
                    ordinary,
                    "sonderausgaben_spenden_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_sonderausgaben.spenden",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.spendenabzug_deductible_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "§ 10b Abs. 1 Satz 1 Nr. 1 EStG — abzugsfähige Spenden "
                    "innerhalb des 20 %-Höchstbetrags des Gesamtbetrags der "
                    "Einkünfte. Vorjahresvorträge nach § 10b Abs. 1 Sätze "
                    "9-10 EStG werden derzeit nicht modelliert (fail-closed)."
                ),
            ),
            # Anlage Unterhalt is technically a SEPARATE BMF form for
            # § 33a Abs. 1 EStG Unterhaltsleistungen; the engine surfaces
            # it on the Sonderausgaben renderer because the deductible
            # flows through the same § 2 Abs. 5 EStG assembly path. Per
            # the BMF 2025 Anlage Unterhalt, the deductible amount lands
            # on Zeile 7. We tag the form as ``Anlage Unterhalt`` so the
            # I3 scanner discriminates the two destinations.
            legal_value_entry(
                schema.label("unterhalt_zeile_7"),
                legal_value_from_dict(
                    ordinary,
                    "sonderausgaben_unterhalt_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_sonderausgaben.unterhalt",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.unterhaltsleistungen_deductible_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "§ 33a Abs. 1 EStG — Unterhaltsleistungen an gesetzlich "
                    "Unterhaltsberechtigte, gedeckelt durch den "
                    "Grundfreibetrag minus Eigenbezüge-Reduktion (Eigenbezüge "
                    "über €624 reduzieren den Höchstbetrag, § 33a Abs. 1 "
                    "Satz 5 EStG). Filing surface: Anlage Unterhalt, Zeile 7."
                ),
            ),
            # § 10c Sonderausgaben-Pauschbetrag is an audit-only row —
            # the Finanzamt applies the Pauschbetrag automatically on
            # the Hauptvordruck, so there is no Anlage Sonderausgaben
            # Zeile that the user transmits this value on. Keep the
            # ``(audit)`` label prefix so the I3 scanner regex skips
            # the row (no FormLineRef expected; the renderer surfaces
            # the value purely for audit traceability).
            legal_value_entry(
                schema.label("pauschbetrag_audit"),
                legal_value_from_dict(
                    ordinary,
                    "sonderausgaben_pauschbetrag_eur",
                    country=GERMANY_COUNTRY,
                    section="anlage_sonderausgaben.pauschbetrag",
                    provenance=provenance,
                    provenance_output_key="de.ordinary.sonderausgaben_pauschbetrag_applied_eur",
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes=(
                    "§ 10c EStG Sonderausgaben-Pauschbetrag (€72 joint / "
                    "€36 single per-person). Audit-only row — the "
                    "Finanzamt applies the Pauschbetrag automatically; "
                    "this surfaces the value the engine assumed in the "
                    "§ 2 Abs. 5 EStG taxable-income assembly."
                ),
            ),
        ],
        [
            "Authority for Spendenabzug: § 10b Abs. 1 Satz 1 Nr. 1 EStG "
            "(https://www.gesetze-im-internet.de/estg/__10b.html).",
            "Authority for Unterhaltsleistungen: § 33a Abs. 1 EStG "
            "(https://www.gesetze-im-internet.de/estg/__33a.html).",
            "Authority for Sonderausgaben-Pauschbetrag: § 10c EStG "
            "(https://www.gesetze-im-internet.de/estg/__10c.html).",
        ],
    )


_ANLAGE_AUS_COUNTRY_DISPLAY = {
    "US": "USA",
    "CANADA": "Kanada",
    "RIC": "Verschiedene (RIC pass-through)",
    "UNKNOWN": "Verschiedene (depository-credited)",
}


def _format_country_display(country: str) -> str:
    """Map ISO / IRS-style country tokens to the German Finanzamt
    presentation. Unknown tokens fall through verbatim.
    """
    return _ANLAGE_AUS_COUNTRY_DISPLAY.get(country.strip().upper(), country)


def _write_anlage_aus(
    paths: YearPaths,
    results: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Anlage AUS 2025 with the per-country § 34c (1) EStG /
    § 32d Abs. 5 EStG foreign-tax-credit breakdown.

    Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): closes the C2
    deferred placeholder. The per-country list flows from the
    standalone ``derive_de_anlage_aus_2025`` derivation product
    (``outputs/tax-positions/de-anlage-aus-by-country.csv``), pulled
    through ``germany_model.py`` into ``results["anlage_aus"][
    "by_country"]``. The renderer wraps each Decimal-valued Zeile in a
    LegalValue envelope via ``legal_value_from_decimal`` so invariant
    I11 holds; the Anlage AUS Zeilen 4 / 6 / 8 / 9 / 11 / 13 / 15 are
    declared on ``DE25-18-SECTION-32D5-FTC.outputs.form_line_refs``
    so invariant I3 holds (the same § 32d Abs. 5 / § 34c Abs. 1
    anrechenbare Steuer flowing onto two statutory surfaces — Anlage
    KAP for the per-Posten cap, Anlage AUS for the per-country cap).

    Reconciliation: the renderer also surfaces a cross-check row
    showing the sum of per-country ``anrechenbar_eur`` amounts vs.
    the existing aggregate ``de.capital.foreign_tax_credit_applied_eur``
    scalar from the rule graph. A 0.01 EUR discrepancy is tolerable
    (per-row q2 rounding); larger drift surfaces as an explicit
    audit-only ``cross-check`` row that the I3 scanner deliberately
    skips so it does not get treated as a Zeile.

    Authority:
    - § 34c Abs. 1 EStG (Steueranrechnung):
      https://www.gesetze-im-internet.de/estg/__34c.html
    - § 32d Abs. 5 EStG (per-item foreign-tax credit on capital
      income): https://www.gesetze-im-internet.de/estg/__32d.html
    - DBA-USA Art. 10 / Art. 23: https://www.irs.gov/pub/irs-trty/germany.pdf
    - ELSTER help (Anlage AUS 2025):
      https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025
    - R 34c EStR — per-country rule guidance:
      https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/V-Steuerermaessigungen-34c-35c/1-Steuerermaessigung-bei-ausl-Eink-34c-34d/Paragraf-34c/r-34c-1-2.html
    """
    schema = load_form_schema("anlage_aus")
    capital = results.get("capital", {})
    aggregate_ftc_eur = str(
        capital.get("foreign_tax_credit_applied_eur", "0.00")
    )
    by_country_rows: list[dict[str, str]] = []
    raw_section = results.get("anlage_aus")
    if isinstance(raw_section, dict):
        raw_rows = raw_section.get("by_country")
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if isinstance(row, dict):
                    by_country_rows.append({str(k): str(v) for k, v in row.items()})

    if not by_country_rows:
        # Fail-closed posture per CLAUDE.md: when the derivation found
        # zero foreign-tax rows, the engine emits a citation-bearing
        # status row rather than a fabricated empty country block.
        write_form(
            paths.germany_forms_root / f"{paths.year}_anlage_aus.md",
            f"{paths.year} {schema.display_name}",
            [
                "STATUS: not_applicable — no foreign-tax-credit rows found.",
                "Per CLAUDE.md fail-closed posture, this renderer emits a "
                "status sheet rather than fabricating per-country rows when "
                "the upstream derivation found zero foreign-tax flows.",
                f"Aggregate § 32d Abs. 5 EStG foreign-tax credit "
                f"(``de.capital.foreign_tax_credit_applied_eur``): "
                f"**{aggregate_ftc_eur} EUR**.",
            ],
            [
                FormEntry(
                    schema.label("status"),
                    "not_applicable",
                    source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                    notes=(
                        "No per-country foreign-tax-credit rows derived "
                        "from this workspace's facts."
                    ),
                ),
            ],
            [
                "Authority for foreign-tax credit (general): § 34c Abs. 1 EStG "
                "(https://www.gesetze-im-internet.de/estg/__34c.html).",
                "Authority for capital-income foreign-tax credit (per-item): "
                "§ 32d Abs. 5 EStG "
                "(https://www.gesetze-im-internet.de/estg/__32d.html).",
                "ELSTER help: Anlage AUS 2025 "
                "(https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025).",
            ],
        )
        return

    # Real per-country rendering. One block per country: Zeilen 4 / 6 /
    # 8-9 / 11-13 / 15. Each Decimal-amount line wraps through
    # ``legal_value_from_decimal`` with a deterministic synthesized
    # fingerprint per the F-CQ-1 Shape-A wiring contract.
    #
    # Bilingual posture: mirrors the § 33b Abs. 5 EStG transferral
    # pattern (commit e68c648) — DE-primary statutory narrative followed
    # by an EN-secondary translation. The German Finanzamt audits the DE
    # text; the EN block is for the U.S.-side advisor reading the audit
    # packet alongside the U.S. Form 1116 / treaty re-sourcing surface.
    posture = [
        # — German narrative —
        "**§ 34c Abs. 1 EStG (Steueranrechnung) — pro-Land-Aufstellung**: "
        "Die anrechenbare ausländische Steuer wird auf Anlage AUS pro "
        "Quellenstaat ausgewiesen (R 34c EStR). Jeder Länderblock "
        "transkribiert die Zeilen 4 (Land), 6 (Art der Einkünfte), 8/9 "
        "(Einkünfte EUR), 11/13 (Steuer in Quellenwährung + EUR-"
        "Übersetzung), 15 (anrechenbare Steuer nach § 34c Abs. 1 EStG).",
        "**§ 32d Abs. 5 EStG (Pro-Posten-Begrenzung)**: für Kapital"
        "erträge gilt zusätzlich die Pro-Posten-Begrenzung; der hier "
        "ausgewiesene Aggregatbetrag ist deshalb mit dem Anlage-KAP-"
        "Wert deckungsgleich (siehe Abgleichszeile unten).",
        f"**Aggregat-Anrechnungsbetrag** (DE25-18, "
        f"``de.capital.foreign_tax_credit_applied_eur``): "
        f"**{aggregate_ftc_eur} EUR**.",
        "**DBA-USA Art. 10 / Art. 23 (Quellenstaat-Begrenzung 15 % bei "
        "Portfolio-Dividenden)**: U.S.-Quellendividenden werden auf "
        "Anlage AUS dem Länderblock ``Land = USA`` zugeordnet; die "
        "Anrechnung in Deutschland ist auf den vom Abkommen erlaubten "
        "Höchstsatz von 15 % beschränkt (DBA-USA Art. 10 Abs. 2 lit. b "
        "+ Art. 23 Abs. 5 lit. b).",
        # — English translation (audit-side) —
        "**§ 34c (1) EStG (foreign-tax credit) — per-country breakdown** "
        "(EN): the German foreign-tax credit is reported on Anlage AUS "
        "country-by-country (R 34c EStR). Each country block transcribes "
        "Zeilen 4 (Land), 6 (income type), 8/9 (foreign-source income in "
        "EUR), 11/13 (foreign tax in source currency + EUR translation), "
        "15 (creditable tax under § 34c (1) EStG).",
        "**§ 32d (5) EStG (per-Posten cap)** (EN): for capital income "
        "the credit is additionally bounded per item; the aggregate "
        "shown here therefore matches the Anlage KAP scalar (see "
        "reconciliation row below).",
        "**DBA-USA Art. 10 / Art. 23 (source-state 15 % portfolio-"
        "dividend cap)** (EN): U.S.-source dividends route to Anlage AUS "
        "country block ``Land = USA``; the residence-state credit is "
        "capped at the treaty-allowed 15 % source-state rate (DBA-USA "
        "Art. 10(2)(b) + Art. 23(5)(a), Germany's credit limited to the "
        "treaty-permitted U.S. tax).",
    ]
    notes = [
        # Bilingual citations — DE first, EN parenthetical.
        f"§ 34c Abs. 1 EStG (Steueranrechnung / foreign-tax credit): "
        f"{ESTG_34C_URL}.",
        f"§ 32d Abs. 5 EStG (Pro-Posten-Begrenzung / per-item cap): "
        f"{ESTG_32D_URL}.",
        f"DBA-USA (1989 + 2006 Protokoll / 2006 protocol): "
        f"{DBA_USA_ART_10_URL}.",
        f"ELSTER-Hilfe (Anlage AUS 2025 / ELSTER Anlage AUS 2025): "
        f"{ELSTER_ANLAGE_AUS_2025_URL}.",
        f"R 34c EStR (Verwaltungsauffassung pro Quellenstaat / "
        f"administrative per-country guidance): {ESTR_R_34C_URL}.",
        # Audit reconciliation note (DE/EN compact).
        "Reconciliation / Abgleich: per-country ``anrechenbar_eur`` "
        "aggregate against ``de.capital.foreign_tax_credit_applied_eur`` "
        "scalar must agree within 0.01 EUR (q2 rounding). Larger drift "
        "is a posture defect — die Pro-Posten-Anrechnung im Anlage-KAP "
        "muss dem Pro-Land-Sum auf Anlage AUS entsprechen.",
    ]

    # Build the per-country entries inline as a list-comprehension so
    # the I3 AST scanner (test_form_renderer_lines_match_output_declarations)
    # can statically detect the ``legal_value_entry("Anlage AUS Zeile N",
    # ...)`` calls inside the 4th argument of ``write_form``. The scanner
    # uses ``ast.walk`` so nested calls inside generators / list comps
    # are still visible.
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_aus.md",
        f"{paths.year} {schema.display_name}",
        posture,
        [
            *[
                entry
                for index, row in enumerate(by_country_rows, start=1)
                for entry in [
                    FormEntry(
                        schema.label("zeile_4"),
                        _format_country_display(row.get("country", "").strip()),
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            f"Country block #{index}: source-country code "
                            f"`{row.get('country', '').strip()}`."
                        ),
                    ),
                    FormEntry(
                        schema.label("zeile_6"),
                        row.get("income_type", "").strip() or "capital_dividend",
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            "Capital-income foreign-tax credit per § 32d "
                            "Abs. 5 EStG flows to Anlage AUS via § 34c "
                            "Abs. 1 EStG."
                        ),
                    ),
                    legal_value_entry(
                        schema.label("zeile_8"),
                        legal_value_from_decimal(
                            row.get("foreign_income_eur", "0.00") or "0.00",
                            country=GERMANY_COUNTRY,
                            section=f"capital.anlage_aus.country_{index}",
                            output_key="de.anlage_aus.foreign_income_eur",
                            provenance=provenance,
                        ),
                        currency=Currency.EUR,
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            "Foreign-source income (EUR) attributable to "
                            "this country."
                        ),
                    ),
                    legal_value_entry(
                        schema.label("zeile_9"),
                        legal_value_from_decimal(
                            row.get("foreign_income_eur", "0.00") or "0.00",
                            country=GERMANY_COUNTRY,
                            section=f"capital.anlage_aus.country_{index}",
                            output_key="de.anlage_aus.foreign_income_eur_continuation",
                            provenance=provenance,
                        ),
                        currency=Currency.EUR,
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes="Continuation of Zeile 8 (Anlage AUS instructions).",
                    ),
                    FormEntry(
                        schema.label("zeile_11"),
                        (
                            f"{row.get('foreign_tax_source_amount', '0.00')} "
                            f"{(row.get('foreign_tax_source_currency', '').strip() or 'USD')}"
                        ),
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            f"Foreign tax in source currency. Anlage AUS "
                            "Zeile 11 transcribes the source-currency "
                            "amount; Zeile 13 transcribes the EUR "
                            "translation."
                        ),
                    ),
                    legal_value_entry(
                        schema.label("zeile_13"),
                        legal_value_from_decimal(
                            row.get("foreign_tax_eur", "0.00") or "0.00",
                            country=GERMANY_COUNTRY,
                            section=f"capital.anlage_aus.country_{index}",
                            output_key="de.anlage_aus.foreign_tax_eur",
                            provenance=provenance,
                        ),
                        currency=Currency.EUR,
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            "Foreign tax (EUR-translated) paid to the "
                            "source country."
                        ),
                    ),
                    legal_value_entry(
                        schema.label("zeile_15"),
                        legal_value_from_decimal(
                            row.get("anrechenbar_eur", "0.00") or "0.00",
                            country=GERMANY_COUNTRY,
                            section=f"capital.anlage_aus.country_{index}",
                            output_key="de.anlage_aus.anrechenbar_eur",
                            provenance=provenance,
                        ),
                        currency=Currency.EUR,
                        source="outputs/tax-positions/de-anlage-aus-by-country.csv",
                        notes=(
                            "Anrechenbare Steuer per § 34c Abs. 1 EStG / "
                            "§ 32d Abs. 5 EStG; the per-country sum "
                            "reconciles to the aggregate "
                            "de.capital.foreign_tax_credit_applied_eur "
                            "(cross-check row below)."
                        ),
                    ),
                ]
            ],
            FormEntry(
                schema.label("aggregate_cross_check"),
                f"{aggregate_ftc_eur} EUR",
                source="results.capital.foreign_tax_credit_applied_eur",
                notes=(
                    "Aggregate § 32d Abs. 5 EStG foreign-tax credit emitted "
                    "by DE25-18 (the per-country anrechenbar_eur sum should "
                    "match this within 0.01 EUR rounding tolerance)."
                ),
            ),
        ],
        notes,
    )


def _write_anlage_so(paths: YearPaths, results: dict, provenance: Mapping[str, Any] | None) -> None:
    schema = load_form_schema("anlage_so")
    write_form(
        paths.germany_forms_root / f"{paths.year}_anlage_so.md",
        f"{paths.year} {schema.display_name}",
        [
            "Keep the form aligned with the audited filing notes.",
            "No new private-sale logic is introduced here.",
        ],
        [
            legal_value_entry(
                schema.label("zeilen_14_21"),
                legal_value_from_dict(
                    results["refunds"], "other_income_22nr3_eur",
                    country=GERMANY_COUNTRY,
                    section="results.refunds",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-summary.md",
                notes="Other income under § 22 Nr. 3 from the saved summary.",
            ),
            legal_value_entry(
                schema.label("zeilen_41_47"),
                legal_value_from_dict(
                    results["private_sales"], "private_sale_result_eur",
                    country=GERMANY_COUNTRY,
                    section="results.private_sales",
                    provenance=provenance,
                ),
                currency=Currency.EUR,
                source="germany-model-results.json",
                notes="Current documented private-sale result (Coinbase crypto bucket) from the saved model; § 23 EStG private Veräußerungsgeschäfte at virtuelle Währungen / sonstige Token.",
            ),
            FormEntry(schema.label("zeile_62"), "", source="germany-elster-entry-sheet.md", notes="Prior-year carryforward handling remains in the audit entry sheet."),
        ],
        [
            "The current model treats staking income separately from the crypto loss bucket.",
        ],
    )


def render_germany_forms(paths: YearPaths) -> None:
    _ensure_supported_year(paths)
    clear_markdown_outputs(paths.germany_forms_root)
    final_output = load_final_legal_output_2025(paths)
    forms = final_output["germany"]["forms"]
    profile = forms["profile"]
    results = forms["results"]
    filing_posture = _germany_filing_posture_from_results(results)
    _ensure_supported_filing_posture(filing_posture)
    if not forms.get("elster_entry_sheet_text"):
        raise FileNotFoundError("Missing Germany final legal output field: elster_entry_sheet_text")
    kap_rows = forms["kap_summary_rows"]
    fund_rows = forms["kap_inv_fund_summary_rows"]
    # Anlage Kind 2025 surface — § 33b Abs. 5 EStG transferred Pauschbetrag
    # row(s) projected from the children sub-graph
    # (DE25-CHILDREN-DISABILITY-PAUSCHBETRAG → de.children.disability_
    # pauschbetrag_transferred_eur). https://www.gesetze-im-internet.de/estg/__33b.html
    kind_rows = forms["kind_summary_rows"]
    # Invariant I11 / F-CQ-1: thread the per-rule-output provenance map
    # to the form-line adapters. The Germany batch's stage outputs (e.g.,
    # ``de.capital.foreign_tax_credit_applied_eur`` from DE25-21) match
    # against ``_provenance.form_lines.DE`` when present; renderer-side
    # CSV projections (Anlage KAP / KAP-INV row lookups) fall back to a
    # synthetic deterministic fingerprint per the adapter contract.
    provenance = final_output.get("_provenance")
    _write_index(paths, results, profile, filing_posture)
    _write_hauptvordruck(paths, results, profile, filing_posture)
    for person in _german_person_slots(profile):
        _write_anlage_n_for_person(paths, person, _required_anlage_n_entries(forms, person["slot"]))
    for person in _german_person_slots(profile):
        _write_anlage_kap_for_person(paths, person, kap_rows, provenance)
    _write_anlage_kap_inv(paths, kap_rows, fund_rows, provenance)
    # Anlage Kind 2025 — § 32 Abs. 6 EStG Kinderfreibetrag + BEA + § 33b
    # Abs. 5 EStG transferred Pauschbetrag.
    # https://www.gesetze-im-internet.de/estg/__32.html
    # https://www.gesetze-im-internet.de/estg/__33b.html
    _write_anlage_kind(paths, kind_rows, results, provenance)
    # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage Vorsorgeaufwand
    # 2025 — § 10 Abs. 1 Nr. 2 / Nr. 3 / Nr. 3a / Abs. 3 / Abs. 4 EStG.
    # https://www.gesetze-im-internet.de/estg/__10.html
    _write_anlage_vorsorgeaufwand(paths, results, provenance)
    # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage Sonderausgaben
    # 2025 — § 10b / § 33a Abs. 1 / § 10c EStG decomposition.
    # https://www.gesetze-im-internet.de/estg/__10b.html
    # https://www.gesetze-im-internet.de/estg/__33a.html
    # https://www.gesetze-im-internet.de/estg/__10c.html
    _write_anlage_sonderausgaben(paths, results, provenance)
    # C2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Anlage AUS 2025 status
    # sheet — DEFERRED to Phase 5. Emits not_applicable + deferral
    # rationale until per-country fact extraction lands.
    # https://www.gesetze-im-internet.de/estg/__34c.html
    _write_anlage_aus(paths, results, provenance)
    _write_anlage_so(paths, results, provenance)
