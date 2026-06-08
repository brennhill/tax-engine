from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Mapping

from tax_pipeline.y2025.germany_inputs import load_german_person_slots
from tax_pipeline.y2025.germany_law import (
    GermanyBankCapitalCertificate2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
)
from tax_pipeline.y2025.germany_capital_rules import (
    GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY,
)
from tax_pipeline.y2025.germany_kap_projection_rules import (
    execute_germany_kap_projection_rule_graph,
    germany_kap_projection_initial_facts_2025,
    germany_kap_projection_initial_fingerprints_2025,
)
from tax_pipeline.pipeline_context import get_pipeline_context_value
from tax_pipeline.pipelines.y2025 import germany_loaders as _germany_loaders

getcontext().prec = 28
D = Decimal


def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    return format(q2(value), "f")


def capital_form_projection_2025(
    *,
    inputs: dict[str, Decimal],
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...],
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...],
    bank_certificates: tuple[GermanyBankCapitalCertificate2025, ...],
    fund_classification: dict[str, str],
    person_slots: list[dict[str, str]],
    dher_stock_gain_eur: Decimal,
    vorabpauschale_taxable_after_teilfreistellung_eur: Decimal,
) -> dict:
    """Shape the Anlage KAP / KAP-INV CSV rows from the executed rule graph.

    WS-4C (``docs/invariant-migration-plan.md``): the legal arithmetic for
    Anlage KAP / KAP-INV form-line projection now lives in
    ``DE25-FORM-KAP-PROJECTION``. This helper is a thin shim that runs the
    rule graph and shapes the per-Zeile EUR scalars into the CSV row
    tuples the renderer expects. Per CLAUDE.md the renderer must not
    perform legal math; this body now reads rule-output values and
    formats them — there is no remaining ``+ - * /`` over rule outputs.
    """
    person_1 = next(slot for slot in person_slots if slot["slot"] == "person_1")
    person_slots_by_slot = {slot["slot"]: slot for slot in person_slots}
    # A4 (FORM-MAPPING-FOLLOWUP) — single-sourced from the
    # DE25-16-SECTION-20-9-SAVER rule output
    # ``de.capital.sparer_pauschbetrag_claimed_eur``. The renderer
    # boundary then carries the statutory cap (€1,000 single / €2,000
    # jointly assessed spouses; § 20 Abs. 9 Satz 1/2 EStG) onto
    # Anlage KAP Zeile 4 of each spouse's form. Reading from the
    # executor's final facts keeps the I2/I11 fingerprint chain
    # single-sourced and avoids re-deriving from ``inputs`` (which
    # would silently default to "0.00" if the key were missing). Both
    # spouses' Anlage KAP Z4 carries the same amount under the
    # joint-assessment convention; the *used* allocation appears
    # separately on Z17.
    # https://www.gesetze-im-internet.de/estg/__20.html
    capital_execution = get_pipeline_context_value(
        GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY
    )
    if capital_execution is None:
        raise RuntimeError(
            "Germany capital rule-graph execution missing from pipeline "
            "context; ``compute_germany_capital_assessment_2025`` must "
            "run before ``capital_form_projection_2025`` so the "
            "Anlage KAP Zeile 4 Sparer-Pauschbetrag value is sourced "
            "from the executor's ``de.capital.sparer_pauschbetrag_claimed_eur`` "
            "output rather than re-derived from inputs."
        )
    sparer_pauschbetrag_claimed_eur = q2(
        Decimal(
            str(capital_execution.final_facts["de.capital.sparer_pauschbetrag_claimed_eur"])
        )
    )

    # Promote the projection arithmetic into the rule graph. The four
    # per-Zeile EUR scalars (Zeilen 19/20/21/23/24/41), the four KAP-INV
    # Zeilen (4/8/14/26), and the per-fund row breakdown are produced
    # inside DE25-FORM-KAP-PROJECTION's calculate body and arrive here
    # as fingerprinted final facts.
    initial_facts = germany_kap_projection_initial_facts_2025(
        foreign_tax_1099_eur=inputs["foreign_tax_1099_eur"],
        sale_facts=sale_facts,
        income_facts=income_facts,
        fund_classification=dict(fund_classification),
        dher_stock_gain_eur=dher_stock_gain_eur,
        vorabpauschale_taxable_after_teilfreistellung_eur=(
            vorabpauschale_taxable_after_teilfreistellung_eur
        ),
    )
    kap_execution = execute_germany_kap_projection_rule_graph(
        initial_facts,
        input_fingerprints=germany_kap_projection_initial_fingerprints_2025(
            initial_facts
        ),
    )
    final_facts: Mapping[str, Any] = kap_execution.final_facts

    # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5 und 6
    # EStG; the former 2024 Anlage KAP per-bucket Zeilen for
    # Termingeschäfte positives and Termingeschäfte losses are dropped
    # for VZ 2025. option_pos / option_neg still flow into the surviving
    # Zeile 19 inside the projection rule. BMF-VERIFIED 2026-05-13
    # against BMF 16.05.2025 Steuerbescheinigung-Schreiben —
    # https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
    line_19_eur = final_facts["de.kap.line_19_eur"]
    line_20_eur = final_facts["de.kap.line_20_eur"]
    line_23_eur = final_facts["de.kap.line_23_eur"]
    line_41_eur = final_facts["de.kap.line_41_eur"]
    inv_line_4_eur = final_facts["de.kap_inv.line_4_eur"]
    inv_line_8_eur = final_facts["de.kap_inv.line_8_eur"]
    # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung) lands here
    # for Anlage KAP-INV Zeilen 9-13. The legal calculation happened in
    # DE25-13F-VORABPAUSCHALE; the KAP projection re-emits the value.
    # https://www.gesetze-im-internet.de/invstg_2018/__19.html
    inv_line_9_13_eur = final_facts["de.kap_inv.line_9_13_eur"]
    inv_line_14_eur = final_facts["de.kap_inv.line_14_eur"]
    inv_line_26_eur = final_facts["de.kap_inv.line_26_eur"]
    fund_rows = final_facts["de.kap_inv.fund_rows"]

    kap_summary_rows: list[list[str]] = [
        # A4: Anlage KAP Z4 — § 20 Abs. 9 Satz 1/2 EStG
        # Sparer-Pauschbetrag claim line (statutory cap before
        # § 20 Abs. 9 Satz 3 spouse-allocation).
        [
            person_1["anlage_kap_label"],
            "4",
            fmt(sparer_pauschbetrag_claimed_eur),
            f"Sparer-Pauschbetrag claimed by {person_1['order_label'].lower()} (§ 20 Abs. 9 Satz 1/2 EStG; the §-20-Abs.-9-Satz-3 spouse-allocation appears on Z17).",
        ],
        [person_1["anlage_kap_label"], "17", "0.00", f"Already-used Sparer-Pauschbetrag at German banks for {person_1['order_label'].lower()}."],
        [person_1["anlage_kap_label"], "19", fmt(line_19_eur), "Net foreign non-fund capital income, including ordinary income plus stock/option results."],
        [person_1["anlage_kap_label"], "20", fmt(line_20_eur), "Gross gains from stock sales."],
        [person_1["anlage_kap_label"], "23", fmt(line_23_eur), "Gross losses from stock sales."],
        [person_1["anlage_kap_label"], "41", fmt(line_41_eur), "Foreign tax from the Schwab 1099 package converted to EUR."],
        ["Anlage KAP-INV", "4", fmt(inv_line_4_eur), "Distributions / income from Aktienfonds."],
        ["Anlage KAP-INV", "8", fmt(inv_line_8_eur), "Distributions / income from sonstige Investmentfonds."],
        ["Anlage KAP-INV", "9-13", fmt(inv_line_9_13_eur), "InvStG § 19 Vorabpauschale (deemed-distribution amount, post-§ 20 Teilfreistellung) computed by DE25-13F-VORABPAUSCHALE."],
        ["Anlage KAP-INV", "14", fmt(inv_line_14_eur), "Gains/losses from sales of Aktienfonds."],
        ["Anlage KAP-INV", "26", fmt(inv_line_26_eur), "Gains/losses from sales of sonstige Investmentfonds."],
    ]
    for certificate in bank_certificates:
        owner = person_slots_by_slot.get(certificate.owner_slot)
        if owner is None:
            raise ValueError(f"Germany bank certificate owner_slot not found in person slots: {certificate.owner_slot}")
        # These are direct projections of typed certificate facts already included in the
        # joint § 20/§ 32d/§ 36 core. The renderer must not calculate these rows from
        # raw certificate sidecars.
        kap_summary_rows.extend(
            [
                # A4: Anlage KAP Z4 — § 20 Abs. 9 Satz 1/2 EStG
                # Sparer-Pauschbetrag claim line, mirrored on the
                # bank-certificate owner's Anlage KAP under the
                # joint-assessment convention.
                [
                    owner["anlage_kap_label"],
                    "4",
                    fmt(sparer_pauschbetrag_claimed_eur),
                    f"Sparer-Pauschbetrag claimed by {owner['order_label'].lower()} (§ 20 Abs. 9 Satz 1/2 EStG; the §-20-Abs.-9-Satz-3 spouse-allocation appears on Z17).",
                ],
                [owner["anlage_kap_label"], "5", "yes", "Tick the review field so the bank withholding and foreign-tax credit are taken into account."],
                [owner["anlage_kap_label"], "7", fmt(certificate.kap_line_7_income_eur), "Capital income from the bank annual tax certificate."],
                [owner["anlage_kap_label"], "8", fmt(certificate.kap_line_8_stock_gains_eur), "Stock-sale gains included in certificate line 7."],
                [owner["anlage_kap_label"], "17", fmt(certificate.kap_line_17_saver_allowance_used_eur), "Already-used Sparer-Pauschbetrag at the bank per the certificate."],
                [owner["anlage_kap_label"], "37", fmt(certificate.kap_line_37_kest_withheld_eur), "Kapitalertragsteuer withheld per the certificate."],
                [owner["anlage_kap_label"], "38", fmt(certificate.kap_line_38_soli_withheld_eur), "Solidarity surcharge withheld per the certificate."],
                [owner["anlage_kap_label"], "40", fmt(certificate.kap_line_40_foreign_tax_credited_eur), "Credited foreign tax per the certificate."],
                [owner["anlage_kap_label"], "41", fmt(certificate.kap_line_41_foreign_tax_not_credited_eur), "Foreign tax not yet credited per the certificate."],
            ]
        )

    kap_inv_fund_rows: list[list[str]] = []
    for row in fund_rows:
        sym = str(row["symbol"])
        fund_type = str(row["fund_type"])
        income_eur = row["income_eur"]
        sale_result_eur = row["sale_result_eur"]
        combined_eur = row["combined_eur"]
        kap_inv_fund_rows.append([sym, fund_type, fmt(income_eur), fmt(sale_result_eur), fmt(combined_eur)])

    return {
        "kap_summary_rows": kap_summary_rows,
        "kap_inv_fund_rows": kap_inv_fund_rows,
        # JStG 2024 dropped the per-bucket option_pos / option_neg
        # surfaces; both still net into kap_line_19 inside the rule.
        "capital_audit": {
            "kap_line_19": fmt(line_19_eur),
            "stock_pos": fmt(line_20_eur),
            "stock_neg": fmt(line_23_eur),
            "fund_income_akt": fmt(inv_line_4_eur),
            "fund_income_sonst": fmt(inv_line_8_eur),
            "fund_sales_akt": fmt(inv_line_14_eur),
            "fund_sales_sonst": fmt(inv_line_26_eur),
            "foreign_tax_full": fmt(line_41_eur),
        },
    }


def children_form_projection_2025(
    *,
    children_disability_pauschbetrag_transferred_eur: Decimal,
) -> dict[str, list[list[str]]]:
    """Shape the Anlage Kind CSV rows from the executed children sub-graph.

    The 2025 BMF Anlage Kind Steuerformular places the per-child
    Behinderten-Pauschbetrag transferral in Zeilen 64-66:

    - Zeile 64: attestation / qualifying conditions (§ 33b Abs. 5 EStG
      requires the child not to claim the Pauschbetrag in their own
      assessment — non-currency attestation field).
    - Zeile 65: per-child Pauschbetrag EUR amount (§ 33b Abs. 3 EStG
      schedule by GdB or hilflos/blind erhöhter Pauschbetrag), cleanly
      transferred to the parents' assessment per § 33b Abs. 5 Satz 1/2
      EStG.
    - Zeile 66: optional anderweitige prozentuale Aufteilung between
      the parents (§ 33b Abs. 5 Satz 3 EStG joint election; default
      50/50 if Zeile 66 is left blank).

    This projection emits the Zeile 65 EUR amount for the renderer; the
    Zeilen 64 / 66 procedural fields are non-currency attestation / split
    metadata that travel through the narrative footer rather than the
    CSV row surface.

    Authority:
    - § 33b Abs. 5 EStG (transferral):
      https://www.gesetze-im-internet.de/estg/__33b.html
    - Helfer in Steuersachen 2.9.0 Zeilen 64-66 "Übertragung des
      Pauschbetrags für Kinder mit Behinderung" (2025).
    - BMF Steuerformular id 034025_25 (Anlage Kind 2025).
    """
    transferred = q2(children_disability_pauschbetrag_transferred_eur)
    return {
        "kind_summary_rows": [
            [
                "Anlage Kind",
                "65",
                fmt(transferred),
                "§ 33b Abs. 5 EStG transferred Behinderten-Pauschbetrag for "
                "the qualifying child(ren); the per-child §-33b-Abs.-3 "
                "Pauschbetrag attaches to the parents' assessment when "
                "claimed (forfeit otherwise per § 33b Abs. 5 Satz 1).",
            ],
        ],
    }


def ordinary_form_projection_rows_2025(ordinary_assessment, person_slots: list[dict[str, str]]) -> list[list[str]]:
    rows: list[list[str]] = []
    slot_labels = {slot["slot"]: slot["anlage_n_label"] for slot in person_slots}
    for person in ordinary_assessment.people:
        form_name = slot_labels[person.slot]
        if person.work_equipment_eur > 0:
            if person.work_equipment_items and person.manual_work_equipment_deduction_eur > 0:
                note = "Equipment invoices multiplied by the configured work-use shares, plus explicit manual work-equipment deduction positions from config/manual_overrides.json."
            elif person.manual_work_equipment_deduction_eur > 0:
                note = "Explicit manual work-equipment deduction position from config/manual_overrides.json."
            else:
                note = "Equipment invoices multiplied by the configured work-use shares."
            rows.append([form_name, "54-56", "Arbeitsmittel total", fmt(person.work_equipment_eur), note])
        rows.append([form_name, "58", "Homeoffice days without first workplace visit", str(person.home_office_days_without_visit), "Tagespauschale days from config/manual_overrides.json."])
        rows.append([form_name, "59", "Homeoffice days with first workplace visit", str(person.home_office_days_with_visit), "Current model assumption from config/manual_overrides.json."])
        if person.telecom_deduction_eur > 0:
            rows.append([form_name, "61-64", "Telefon / Internet", fmt(person.telecom_deduction_eur), "Explicit manual deduction position from config/manual_overrides.json."])
        if person.employment_legal_insurance_deduction_eur > 0:
            rows.append([form_name, "61-64", "Beruflicher Anteil Rechtsschutzversicherung", fmt(person.employment_legal_insurance_deduction_eur), "Explicit manual deduction position from config/manual_overrides.json."])
        if person.cross_border_tax_help_deduction_eur > 0:
            rows.append([form_name, "61-64", "Grenzüberschreitende Steuerberatung", fmt(person.cross_border_tax_help_deduction_eur), "Explicit manual deduction position from config/manual_overrides.json."])
    return rows


def _optional_n_projection_row(rows: list[list[str]], form_name: str, line: str) -> list[str] | None:
    matches = [row for row in rows if row[0] == form_name and row[1] == line]
    return matches[0] if matches else None


def _n_projection_rows_exist(rows: list[list[str]], form_name: str, line: str) -> bool:
    return any(row[0] == form_name and row[1] == line for row in rows)


def _sum_n_projection_amount(rows: list[list[str]], form_name: str, line: str) -> str:
    return f"{sum((D(row[3]) for row in rows if row[0] == form_name and row[1] == line), D('0.00')):.2f} EUR"


def anlage_n_entries_projection_2025(
    ordinary_assessment,
    person_slots: list[dict[str, str]],
    n_breakdown_rows: list[list[str]],
) -> dict[str, list[dict[str, str]]]:
    slot_labels = {slot["slot"]: slot for slot in person_slots}
    entries_by_slot: dict[str, list[dict[str, str]]] = {}
    for person in ordinary_assessment.people:
        meta = slot_labels[person.slot]
        form_name = meta["anlage_n_label"]
        source = "; ".join(person.wage.source_files) or "germany-model-results.json"
        # A3 (FORM-MAPPING-FOLLOWUP): row labels now name the
        # *destination* Anlage N Zeile (the line on the 2025 BMF Anlage
        # N form the user transcribes onto), not the *source*
        # Lohnsteuerbescheinigung eDaten Zeile. The source-side eDaten
        # Zeile remains in the row notes for traceability so the audit
        # trail still names the wage-certificate line that produced the
        # value. 2025 BMF Anlage N mapping per the ELSTER help page
        # (ELSTER_ANLAGE_AUS_2025_URL is the wider 2025 Anlage AUS / N
        # help anchor):
        #   - Z6 Bruttoarbeitslohn  ← Lohnsteuerbescheinigung Z3
        #   - Z7 Einbehaltene Lohnsteuer ← Lohnsteuerbescheinigung Z4
        #   - Z8 Einbehaltener Solidaritätszuschlag
        #     ← Lohnsteuerbescheinigung Z5
        #   - Z16 Mehrjährige Bezüge / Entschädigungen
        #     ← Lohnsteuerbescheinigung Z10
        # Authority: § 19 Abs. 1 EStG (employment income) — the same
        # § 19 / § 9 / § 9a chain DE25-01-WAGE-INCOME ff. cite.
        # https://www.gesetze-im-internet.de/estg/__19.html
        entries = [
            {
                "label": "Anlage N Zeile 6 (Bruttoarbeitslohn)",
                "value": f"{fmt(person.wage.gross_wage_eur)} EUR",
                "source": source,
                "notes": "Source: Lohnsteuerbescheinigung Zeile 3. Gross wage carried from the Germany ordinary-income core onto Anlage N Zeile 6 (§ 19 Abs. 1 EStG).",
            },
            {
                "label": "Anlage N Zeile 7 (Einbehaltene Lohnsteuer)",
                "value": f"{fmt(person.wage.withheld_wage_tax_eur)} EUR",
                "source": source,
                "notes": "Source: Lohnsteuerbescheinigung Zeile 4. Withheld wage tax carried onto Anlage N Zeile 7 — credited against the assessed Einkommensteuer per § 36 Abs. 2 Nr. 2 EStG.",
            },
            {
                "label": "Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag)",
                "value": f"{fmt(person.wage.withheld_solidarity_surcharge_eur)} EUR",
                "source": source,
                "notes": "Source: Lohnsteuerbescheinigung Zeile 5. Withheld solidarity surcharge carried onto Anlage N Zeile 8 — credited against the assessed Soli per SolzG 1995.",
            },
            {
                "label": "Anlage N Zeile 16 (Mehrjährige Bezüge)",
                "value": f"{fmt(person.wage.multiannual_wage_eur)} EUR",
                "source": source,
                "notes": "Source: Lohnsteuerbescheinigung Zeile 10. Mehrjährige Bezüge / Entschädigungen reach Anlage N Zeile 16 (already included in the Zeile 6 Bruttoarbeitslohn when present; § 34 EStG five-fifths method handles the spread).",
            },
        ]
        person_rows = [row for row in n_breakdown_rows if row[0] == form_name]
        if person_rows:
            work_materials = _optional_n_projection_row(n_breakdown_rows, form_name, "54-56")
            if work_materials is not None:
                entries.append(
                    {
                        "label": "Anlage N Zeilen 54-56",
                        "value": f"{D(work_materials[3]):.2f} EUR",
                        "source": "germany-n-work-expenses.csv",
                        "notes": work_materials[4],
                    }
                )
            homeoffice_days_without_visit = _optional_n_projection_row(n_breakdown_rows, form_name, "58")
            if homeoffice_days_without_visit is not None:
                entries.append(
                    {
                        "label": "Anlage N Zeile 58",
                        "value": f"{homeoffice_days_without_visit[3]} days",
                        "source": "germany-n-work-expenses.csv",
                        "notes": homeoffice_days_without_visit[4],
                    }
                )
            homeoffice_days_with_visit = _optional_n_projection_row(n_breakdown_rows, form_name, "59")
            if homeoffice_days_with_visit is not None:
                entries.append(
                    {
                        "label": "Anlage N Zeile 59",
                        "value": f"{homeoffice_days_with_visit[3]} days",
                        "source": "germany-n-work-expenses.csv",
                        "notes": homeoffice_days_with_visit[4],
                    }
                )
            if _n_projection_rows_exist(n_breakdown_rows, form_name, "61-64"):
                entries.append(
                    {
                        "label": "Anlage N Zeilen 61-64",
                        "value": _sum_n_projection_amount(n_breakdown_rows, form_name, "61-64"),
                        "source": "germany-n-work-expenses.csv",
                        "notes": "Aggregated from the structured 61-64 rows in `germany-n-work-expenses.csv`.",
                    }
                )
        else:
            entries.append(
                {
                    "label": f"Anlage N {person.order_label}",
                    "value": "No deduction rows present",
                    "source": "germany-n-work-expenses.csv",
                    "notes": f"No separate {person.order_label.lower()} deduction rows are present in the structured export.",
                }
            )
        entries_by_slot[person.slot] = entries
    return entries_by_slot


def person_projection_2025(ordinary_assessment, person_slots: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    slot_meta = {slot["slot"]: slot for slot in person_slots}
    projected: dict[str, dict[str, str]] = {}
    for person in ordinary_assessment.people:
        meta = slot_meta[person.slot]
        projected[person.slot] = {
            "display_label": meta.get("display_name") or meta["order_label"],
            "order_label": meta["order_label"],
            "anlage_kap_label": meta["anlage_kap_label"],
            "anlage_n_label": meta["anlage_n_label"],
            "gross_wage_eur": fmt(person.wage.gross_wage_eur),
            "withheld_wage_tax_eur": fmt(person.wage.withheld_wage_tax_eur),
            "withheld_solidarity_surcharge_eur": fmt(person.wage.withheld_solidarity_surcharge_eur),
            "multiannual_wage_eur": fmt(person.wage.multiannual_wage_eur),
            "work_equipment_eur": fmt(person.work_equipment_eur),
            "home_office_days_without_visit": str(person.home_office_days_without_visit),
            "home_office_days_with_visit": str(person.home_office_days_with_visit),
            "other_work_expenses_eur": fmt(
                person.telecom_deduction_eur  # pragma: legal-math-ok § 9 Abs. 1 EStG Anlage N "other Werbungskosten" display sum: the per-component values are validated upstream and DE25-02-WERBUNGSKOSTEN already aggregates them as the legal Werbungskosten total. This row presents the three-component split for the form-projection CSV.
                + person.employment_legal_insurance_deduction_eur
                + person.cross_border_tax_help_deduction_eur
            ),
            "telecom_deduction_eur": fmt(person.telecom_deduction_eur),
            "employment_legal_insurance_deduction_eur": fmt(person.employment_legal_insurance_deduction_eur),
            "cross_border_tax_help_deduction_eur": fmt(person.cross_border_tax_help_deduction_eur),
            "actual_werbungskosten_eur": fmt(person.actual_werbungskosten_eur),
        }
    return projected


def person_slots_for_projection_2025(ordinary_assessment) -> list[dict[str, str]]:
    # WS-5D (invariant migration plan §7): defer workspace resolution to
    # call time so each pipeline run picks up its own env-derived paths.
    # ``germany_loaders._year_paths()`` is the canonical lazy accessor;
    # an early ``from germany_loaders import YEAR_PATHS`` style import
    # would freeze the value at this module's first import.
    try:
        return load_german_person_slots(_germany_loaders._year_paths())
    except FileNotFoundError:
        # Unit tests can mock the ordinary assessment directly without materializing a
        # full config/profile.json. The legal calculation has already happened; this
        # fallback only supplies deterministic render labels for that mocked core result.
        return [
            {
                "slot": person.slot,
                "order_label": person.order_label,
                "display_name": getattr(person, "display_name", person.order_label),
                "anlage_n_label": f"Anlage N ({person.order_label})",
                "anlage_kap_label": f"Anlage KAP ({person.order_label})",
            }
            for person in ordinary_assessment.people
        ]
