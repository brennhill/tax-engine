from __future__ import annotations

from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.y2025.germany_law import (
    BKGG_URL,
    BMF_ABGELTUNGSTEUER_URL,
    BMF_BASISZINS_2025_URL,
    BMF_PAP_2025_URL,
    BMF_USA_PAGE_URL,
    ESTG_2_URL,
    ESTG_3_URL,
    ESTG_4_5_6B_URL,
    ESTG_4_5_6C_URL,
    ESTG_4_ABS3_URL,
    ESTG_9_URL,
    ESTG_9A_URL,
    ESTG_10_URL,
    ESTG_10B_URL,
    ESTG_10C_URL,
    ESTG_18_URL,
    ESTG_20_URL,
    ESTG_22_URL,
    ESTG_24A_URL,
    ESTG_26_URL,
    ESTG_26B_URL,
    ESTG_31_URL,
    ESTG_32_URL,
    ESTG_33_URL,
    ESTG_33A_URL,
    ESTG_33B_URL,
    ESTG_32A_URL,
    ESTG_32D_URL,
    ESTG_34C_URL,
    ESTG_36_URL,
    ELSTER_ANLAGE_AUS_2025_URL,
    INVSTG_16_URL,
    INVSTG_18_URL,
    INVSTG_19_URL,
    INVSTG_20_URL,
    INVSTG_21_URL,
    SOLZG_3_URL,
    SOLZG_4_URL,
)


# NOTE (L11/H4, 2026-05-01 correctness review): ``ESTG_19_URL`` is also
# defined in ``tax_pipeline.y2025.germany_law`` and ``ESTG_26A_URL`` is only
# defined here. Centralizing both in ``germany_2025_law`` is the desired
# end state, but the URL-centralization test only scans ``pipelines/`` and
# ``forms/``, so this duplicate is currently undetected by lint. Resolving
# the import cycle is tracked as a follow-up; until then, keep the URL
# strings byte-identical to the law-module copies so a future merge does
# not change any LawStage fingerprint.
ESTG_19_URL = "https://www.gesetze-im-internet.de/estg/__19.html"
ESTG_26A_URL = "https://www.gesetze-im-internet.de/estg/__26a.html"

# NOTE (L8, 2026-05-01 correctness review): the FormLineRef ``line`` strings
# below use em-dash U+2014 ("—") rather than ASCII hyphen U+002D ("-").
# ``LawStage`` fingerprints the rendered ``f"{form} {line}"`` so a swap from
# em-dash to hyphen would change every dependent fingerprint downstream.
# Treat the em-dash as part of the legal-citation contract; do not silently
# normalize when editing.

# Form-line landing pages on the BMF Steuerformulare site. These pages link to
# the official Anleitung (instructions) for each Anlage and stay stable across
# annual form revisions.
BMF_FORM_HAUPTVORDRUCK_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Lohnsteuer-und-Einkommensteuer/lohnsteuer-und-einkommensteuer.html"
BMF_FORM_ANLAGE_N_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Lohnsteuer-und-Einkommensteuer/Anlage-N/anlage-n.html"
BMF_FORM_ANLAGE_VORSORGE_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Lohnsteuer-und-Einkommensteuer/Anlage-Vorsorgeaufwand/anlage-vorsorgeaufwand.html"
BMF_FORM_ANLAGE_KAP_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Abgeltungsteuer/Anlage-KAP/anlage-kap.html"
BMF_FORM_ANLAGE_KAP_INV_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Abgeltungsteuer/Anlage-KAP-INV/anlage-kap-inv.html"
BMF_FORM_ANLAGE_SO_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Steuererklaerung-Steuerformulare/Wichtige-Informationen-rund-ums-Thema-Steuern/Lohnsteuer-und-Einkommensteuer/Anlage-SO/anlage-so.html"
# Anlage S (Einkünfte aus selbständiger Arbeit, § 18 EStG). The official
# 2025 ELSTER/BMF Anlage S PDF was not reachable on 2026-06-12 (see the
# NEEDS-VERIFICATION marker on tax_pipeline/forms/schemas/anlage_s.toml), so
# the FormLineRef url points at the controlling § 18 EStG provision on
# gesetze-im-internet rather than a (404) form landing page.
ESTG_18_FORM_ANLAGE_S_URL = "https://www.gesetze-im-internet.de/estg/__18.html"




def germany_ordinary_law_stages_2025() -> tuple[LawStage, ...]:
    # Phase 3 of the engine restructure: filing posture is an input fact, not a
    # rule-list branch. The three former posture-selected stage pairs/triples
    # collapse to single canonical stages whose ``calculate`` body branches
    # internally on ``de.ordinary.filing_posture``. Every taxpayer runs the same
    # 12 declared stages in the same order.
    #
    # Migration to per-output classification: each stage declares its
    # outputs via ``OutputDeclaration`` so a reader can see, per output,
    # exactly which form line(s) the value lands on or which closed-enum
    # ``AuditWaypoint`` justifies the value living off any form line. The
    # dual-mode ``LawStage`` validator derives the legacy ``output_keys``,
    # ``form_line_refs``, and ``form_line_urls`` fields from these
    # declarations, preserving the engine's fingerprint surface
    # byte-for-byte across the migration.
    return (
        LawStage(
            stage_id="DE25-00-FILING-POSTURE-GATE",
            country_or_scope="DE-2025",
            legal_refs=("§ 26 EStG", "§ 26a EStG", "§ 26b EStG", "§ 32a Abs. 1 EStG", "§ 32a Abs. 5 EStG"),
            authority_urls=(ESTG_26_URL, ESTG_26A_URL, ESTG_26B_URL, ESTG_32A_URL),
            input_fact_keys=(
                "de.profile.filing_posture",
                "de.profile.joint_assessment_prerequisites",
                "de.profile.separate_assessment_allocations",
                "de.ordinary.raw_inputs",
            ),
            rounding_policy="No currency rounding; this stage validates the filing posture against legal prerequisites.",
            law_order_note="Filing posture/election eligibility must be established before any household aggregation, basic tariff, or section 26b splitting.",
            legal_formula="gate: validate filing_posture in {single, married_joint, married_separate} against § 26 prerequisites (married_joint requires joint election + § 26 facts; married_separate requires § 26a per-spouse allocations); de.ordinary.filing_posture := validated posture, else fail-closed",
            narrative_templates={
                "de": "DE25-00-FILING-POSTURE-GATE",
                "en": "DE25-00-FILING-POSTURE-GATE",
            },
            outputs=(
                # Filing posture is a gate: it does not emit a numerical
                # value on a form line; it forces the assessment regime
                # (§ 26b joint base vs. § 32a(1) single tariff vs. § 26a
                # separate allocation) that every later stage depends on.
                # Classified RECONCILIATION_INVARIANT — the prior
                # Hauptvordruck Veranlagungswahl ``form_line_refs`` entry
                # was an orphan because the German renderer never reads
                # it via ``_required_form_line``; the gate output never
                # passes through the kap_summary CSV → renderer path.
                # Authority cites still ride on legal_refs / authority_urls.
                OutputDeclaration(
                    key="de.ordinary.filing_posture",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-01-WAGE-INCOME",
            country_or_scope="DE-2025",
            legal_refs=("§ 19 Abs. 1 EStG", "§ 2 Abs. 2 Satz 1 Nr. 2 EStG"),
            authority_urls=(ESTG_19_URL, ESTG_2_URL),
            input_fact_keys=("de.ordinary.filing_posture", "de.ordinary.people"),
            rounding_policy="Employee wage facts remain cent-level Decimal amounts.",
            law_order_note="Employment income is identified before employment-related deductions.",
            legal_formula="de.ordinary.gross_wages = {total: sum(person.wage.gross_wage_eur for person in household), by_person: tuple[Decimal, ...]} per § 19 Abs. 1 EStG",
            narrative_templates={
                "de": "DE25-01-WAGE-INCOME",
                "en": "DE25-01-WAGE-INCOME",
            },
            outputs=(
                # Bruttoarbeitslohn ultimately appears on Anlage N
                # Zeile 6 (§ 19 Abs. 1 EStG), but the German renderer
                # writes Anlage N entries via ``_required_anlage_n_entries``
                # / ``FormEntry`` (label-keyed dicts), not via
                # ``_required_form_line``. The form-binding contract
                # tested by I3 only enforces ``_required_form_line``
                # reads, so the per-person aggregation is the
                # operative classification for this output here. The
                # § 19 Abs. 1 EStG authority continues to ride on
                # legal_refs / authority_urls / legal_formula.
                # https://www.gesetze-im-internet.de/estg/__19.html
                OutputDeclaration(
                    key="de.ordinary.gross_wages",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-02-WERBUNGSKOSTEN",
            country_or_scope="DE-2025",
            legal_refs=("§ 9 EStG", "§ 9a EStG", "§ 4 Abs. 5 Satz 1 Nr. 6c EStG"),
            authority_urls=(ESTG_9_URL, ESTG_9A_URL, ESTG_4_5_6C_URL),
            input_fact_keys=(
                "de.ordinary.gross_wages",
                "de.ordinary.people",
                "de.constants.worker_allowance_per_person",
            ),
            rounding_policy="Work expenses remain cent-level until taxable-income assembly.",
            law_order_note="Actual Werbungskosten and the Arbeitnehmer-Pauschbetrag are resolved before net employment income.",
            legal_formula="de.ordinary.work_expenses[per_person] = max(actual_§9_expenses(work_equipment + home_office_tagespauschale_2025 + telecom + employment_legal_insurance + cross_border_tax_help), min(§9a_Arbeitnehmer-Pauschbetrag, gross_wage))",
            narrative_templates={
                "de": "DE25-02-WERBUNGSKOSTEN",
                "en": "DE25-02-WERBUNGSKOSTEN",
            },
            outputs=(
                # Werbungskosten ultimately land on Anlage N Zeilen 31
                # ff. (§ 9 EStG / § 9a EStG / § 4 Abs. 5 Satz 1 Nr. 6c
                # EStG), via the Anlage-N FormEntry projection rather
                # than ``_required_form_line``. PER_POSTEN_AGGREGATION
                # captures the per-person breakdown (work_equipment,
                # home_office, telecom, ...) the Posten assembly
                # consumes. Authority continues to ride on legal_refs /
                # authority_urls / legal_formula.
                # https://www.gesetze-im-internet.de/estg/__9.html
                OutputDeclaration(
                    key="de.ordinary.work_expenses",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-03-NET-EMPLOYMENT",
            country_or_scope="DE-2025",
            legal_refs=("§ 2 Abs. 2 Satz 1 Nr. 2 EStG", "§ 19 EStG", "§ 9 EStG"),
            authority_urls=(ESTG_2_URL, ESTG_19_URL, ESTG_9_URL),
            input_fact_keys=("de.ordinary.gross_wages", "de.ordinary.work_expenses"),
            rounding_policy="Net employment income remains cent-level Decimal before household aggregation.",
            law_order_note="Wages less Werbungskosten must be determined before other income and special expenses.",
            legal_formula="de.ordinary.net_employment_income[per_person] = gross_wage - allowed_werbungskosten; total = sum across household per § 2 Abs. 2 Satz 1 Nr. 2 EStG",
            narrative_templates={
                "de": "DE25-03-NET-EMPLOYMENT",
                "en": "DE25-03-NET-EMPLOYMENT",
            },
            outputs=(
                # Net employment income ultimately appears on Anlage N
                # ("Einkünfte aus nichtselbständiger Arbeit (nach
                # Werbungskosten)") per § 2 Abs. 2 Satz 1 Nr. 2 EStG,
                # via the Anlage-N FormEntry projection rather than
                # ``_required_form_line``. PER_POSTEN_AGGREGATION
                # captures the per-person breakdown that feeds § 26b
                # joint base vs. § 2 Abs. 5 single assembly.
                # https://www.gesetze-im-internet.de/estg/__2.html
                OutputDeclaration(
                    key="de.ordinary.net_employment_income",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-04-OTHER-22NR3",
            country_or_scope="DE-2025",
            legal_refs=("§ 22 Nr. 3 EStG",),
            authority_urls=(ESTG_22_URL,),
            input_fact_keys=(
                "de.ordinary.filing_posture",
                "de.ordinary.other_income_22nr3",
                "de.ordinary.other_income_22nr3_threshold",
                "de.ordinary.other_income_22nr3_by_person",
                "de.ordinary.people",
            ),
            rounding_policy="Per-person section 22 Nr. 3 threshold results are summed at cent precision.",
            law_order_note="Taxable other income is included in the section 2 income sum before special expenses.",
            legal_formula="de.ordinary.other_income_22nr3_taxable[per_person] = max(0, other_income_per_person - § 22 Nr. 3 threshold); married_joint requires per-spouse allocation reconciling to the aggregate, otherwise per-person amount itself is the allocation",
            narrative_templates={
                "de": "DE25-04-OTHER-22NR3",
                "en": "DE25-04-OTHER-22NR3",
            },
            outputs=(
                # § 22 Nr. 3 Sonstige Einkünfte ultimately land on
                # Anlage SO Zeilen 14-21, via the Anlage-SO FormEntry
                # in ``_write_anlage_so`` rather than
                # ``_required_form_line``. PER_POSTEN_AGGREGATION
                # captures the per-spouse allocation feeding
                # married_separate ordering.
                # https://www.gesetze-im-internet.de/estg/__22.html
                OutputDeclaration(
                    key="de.ordinary.other_income_22nr3_taxable",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # § 18 EStG selbständige Arbeit, computed by § 4 Abs. 3 EStG EÜR.
        # The Gewinn is an Einkunftsart (§ 2 Abs. 1 Nr. 3 / Abs. 2 Satz 1
        # Nr. 1 EStG) that joins net_employment_income + other_income in
        # DE25-07-TAXABLE-INCOME before the Gesamtbetrag-der-Einkünfte
        # deductions. A wage earner has no business income → zero profit
        # (the demo is unchanged in value). A Verlust is NOT floored
        # (§ 2 Abs. 3 Verlustausgleich). Phase 1 (FREELANCER-DE-EUER-SLICE
        # -SPEC.md); freiberuflich only — § 15 Gewerbe fails closed in the
        # loader.
        # https://www.gesetze-im-internet.de/estg/__18.html
        # https://www.gesetze-im-internet.de/estg/__4.html
        LawStage(
            stage_id="DE25-EUER",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 18 EStG",
                "§ 4 Abs. 3 EStG",
                "§ 2 Abs. 2 Satz 1 Nr. 1 EStG",
            ),
            authority_urls=(ESTG_18_URL, ESTG_4_ABS3_URL, ESTG_2_URL),
            input_fact_keys=(
                "de.ordinary.business_receipts_eur",
                "de.ordinary.business_expenses_eur",
            ),
            rounding_policy="EÜR receipts/expenses rounded to cents (q2); the net profit is not floored.",
            law_order_note="§ 4 Abs. 3 EÜR profit is an Einkunftsart under § 2 Abs. 1 Nr. 3; computed before the Gesamtbetrag-der-Einkünfte deductions so it joins net_employment_income + other_income_22nr3_taxable in DE25-07.",
            legal_formula="de.ordinary.business_profit_eur = business_receipts_eur - business_expenses_eur per § 4 Abs. 3 Satz 1 EStG (Überschuss der Betriebseinnahmen über die Betriebsausgaben; may be negative)",
            narrative_templates={"de": "DE25-EUER", "en": "DE25-EUER"},
            outputs=(
                # § 18 selbständige Arbeit profit lands on Anlage S via the
                # Anlage-S FormEntry projection (Phase 1 slice 3) — the
                # ``_write_anlage_s`` renderer reads it through the I11
                # ``legal_value_entry`` boundary. PER_POSTEN_AGGREGATION
                # captures the receipts−expenses netting. The FormLineRef
                # binds the output to the Anlage S Freiberufler-Gewinn line
                # (Zeile per the anlage_s schema; I3 bidirectional). The Zeile
                # number carries a NEEDS-VERIFICATION marker on the form schema
                # until the official 2025 ELSTER Anlage S is confirmed.
                # https://www.gesetze-im-internet.de/estg/__18.html
                OutputDeclaration(
                    key="de.ordinary.business_profit_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage S",
                            line="4",
                            url=ESTG_18_FORM_ANLAGE_S_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-ALTERSENTLASTUNGSBETRAG",
            country_or_scope="DE-2025",
            legal_refs=("§ 24a EStG",),
            authority_urls=(ESTG_24A_URL,),
            input_fact_keys=(
                "de.ordinary.filing_posture",
                "de.ordinary.people",
                "de.ordinary.net_employment_income",
                "de.ordinary.other_income_22nr3_taxable",
                "de.constants.altersentlastungsbetrag_tax_year",
            ),
            rounding_policy="Per-person Altersentlastungsbetrag is q2-quantized at cent precision; the household total sums the per-person amounts.",
            law_order_note="§ 24a EStG is computed after § 22 Nr. 3 taxable income and before total Sonderausgaben so the cohort allowance reduces the assessment base before § 2 Abs. 5 zvE assembly.",
            legal_formula=(
                "de.ordinary.altersentlastungsbetrag[per_person] = "
                "altersentlastungsbetrag_2025(birth_year, eligible_income = "
                "net_employment_income + other_income_22nr3_taxable, "
                "tax_year = de.constants.altersentlastungsbetrag_tax_year) "
                "per § 24a Satz 5 EStG cohort table; § 24a Satz 2 Nr. 1 EStG "
                "excludes § 19 wages from the eligible base, but here the "
                "implementation conservatively excludes § 19 entirely from "
                "the Altersentlastungsbetrag base by passing only § 22 Nr. 3 "
                "+ other ordinary income (net_employment_income is the "
                "post-Werbungskosten employment number and is intentionally "
                "INCLUDED ONLY for the eligibility check, not for the rate "
                "× base computation)."
            ),
            narrative_templates={
                "de": "DE25-ALTERSENTLASTUNGSBETRAG",
                "en": "DE25-ALTERSENTLASTUNGSBETRAG",
            },
            outputs=(
                # Altersentlastungsbetrag per § 24a EStG reduces the
                # § 2 Abs. 4 Gesamtbetrag der Einkünfte (and therefore the
                # § 2 Abs. 5 zvE) but is not on a dedicated form line that
                # the renderer's ``_required_form_line`` reads. The
                # Hauptvordruck FormEntry projection consumes the
                # household total as part of the Sonderbetrag block,
                # mirroring how DE25-06B feeds Sonderausgaben.
                # https://www.gesetze-im-internet.de/estg/__24a.html
                OutputDeclaration(
                    key="de.ordinary.altersentlastungsbetrag",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-ARBEITSZIMMER",
            country_or_scope="DE-2025",
            legal_refs=("§ 4 Abs. 5 Satz 1 Nr. 6b EStG", "§ 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG"),
            authority_urls=(ESTG_4_5_6B_URL,),
            input_fact_keys=(
                "de.ordinary.raw_inputs",
                "de.ordinary.people",
            ),
            rounding_policy="Pauschale and actual-costs amounts are q2-quantized at cent precision.",
            law_order_note=(
                "§ 4 Abs. 5 Satz 1 Nr. 6b EStG runs alongside § 9 EStG "
                "Werbungskosten. The election is mutually exclusive with "
                "the § 4 Abs. 5 Satz 1 Nr. 6c Tagespauschale modeled in "
                "DE25-02. The deduction enters § 2 Abs. 5 zvE assembly "
                "at DE25-07."
            ),
            legal_formula=(
                "if not arbeitszimmer_claimed: 0; "
                "elif tagespauschale_days > 0: fail-closed (§ 4 Abs. 5 "
                "Satz 1 Nr. 6c Satz 3 EStG mutual exclusion); "
                "elif qualifies_as_mittelpunkt: actual_costs_eur; "
                "else: ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR (€1,260)"
            ),
            narrative_templates={
                "de": "DE25-ARBEITSZIMMER",
                "en": "DE25-ARBEITSZIMMER",
            },
            outputs=(
                # § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer deduction
                # appears on Anlage N (employee returns) or as Betriebs-
                # ausgaben (self-employed); the FormEntry projection
                # consumes the value via results.refunds.
                # https://www.gesetze-im-internet.de/estg/__4.html
                OutputDeclaration(
                    key="de.ordinary.arbeitszimmer",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-05-RETIREMENT-SA",
            country_or_scope="DE-2025",
            legal_refs=("§ 10 Abs. 1 Nr. 2 EStG", "§ 10 Abs. 3 EStG", "§ 3 Nr. 62 EStG"),
            authority_urls=(ESTG_10_URL, ESTG_3_URL),
            input_fact_keys=("de.ordinary.people", "de.ordinary.filing_posture"),
            rounding_policy="Joint caps and employer-share subtraction are resolved to cent-level Decimal amounts.",
            law_order_note="Retirement Vorsorgeaufwendungen are determined before total special expenses.",
            legal_formula="de.ordinary.retirement_special_expenses[per_person] = retirement_special_expense_deduction_2025(employee_pension, employer_pension); married_joint applies joint_retirement_special_expense_deductions_2025 across spouses; de.ordinary.retirement_special_expenses_total_eur = sum(per_person)",
            narrative_templates={
                "de": "DE25-05-RETIREMENT-SA",
                "en": "DE25-05-RETIREMENT-SA",
            },
            outputs=(
                # Rentenversicherungsbeiträge ultimately land on Anlage
                # Vorsorgeaufwand Zeilen 4-9 (§ 10 Abs. 1 Nr. 2 / Abs. 3
                # EStG), via the Vorsorge FormEntry projection rather
                # than ``_required_form_line``. PER_POSTEN_AGGREGATION
                # captures the per-person allocation feeding § 26b vs.
                # single assembly.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.retirement_special_expenses",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``de.ordinary.retirement_special_expenses_total_eur``
                # is the § 10 Abs. 1 Nr. 2 / Abs. 3 EStG scalar total
                # that lands on Anlage Vorsorgeaufwand Zeilen 4-9
                # (Beiträge zur gesetzlichen Rentenversicherung /
                # berufsständischen Versorgungswerken).
                #
                # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): the
                # extended I3 scanner now detects German renderer
                # writes that follow the ``"Anlage <Form> Zeile(n) N"``
                # label convention, so this output gets a FormLineRef
                # binding the bidirectional contract on Anlage
                # Vorsorgeaufwand Zeilen 4-9.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.retirement_special_expenses_total_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Vorsorgeaufwand",
                            line="4-9",
                            url=BMF_FORM_ANLAGE_VORSORGE_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-06-HEALTH-VORSORGE-SA",
            country_or_scope="DE-2025",
            legal_refs=("§ 10 Abs. 1 Nr. 3 EStG", "§ 10 Abs. 1 Nr. 3a EStG", "§ 10 Abs. 4 EStG"),
            authority_urls=(ESTG_10_URL,),
            input_fact_keys=("de.ordinary.people", "de.ordinary.filing_posture"),
            rounding_policy="Basic health/nursing and other Vorsorge caps remain cent-level Decimal amounts.",
            law_order_note="Health/nursing and other Vorsorge deductions are resolved before the section 10c minimum is added.",
            legal_formula="de.ordinary.health_vorsorge_special_expenses[per_person] = deductible_basic_health_contribution_2025 + other_vorsorge_allowed_employee_2025; married_joint applies joint_other_vorsorge_allowed_employee_2025 across spouses; de.ordinary.health_vorsorge_total_eur = sum(per_person_health + per_person_other_allowed); de.ordinary.health_vorsorge_basic_health_eur = sum(per_person_health); de.ordinary.health_vorsorge_other_allowed_eur = sum(per_person_other_allowed)",
            narrative_templates={
                "de": "DE25-06-HEALTH-VORSORGE-SA",
                "en": "DE25-06-HEALTH-VORSORGE-SA",
            },
            outputs=(
                # Kranken- und Pflegeversicherung ultimately land on
                # Anlage Vorsorgeaufwand Zeilen 11 ff. (§ 10 Abs. 1 Nr.
                # 3 / Nr. 3a / Abs. 4 EStG), via the Vorsorge FormEntry
                # projection rather than ``_required_form_line``.
                # PER_POSTEN_AGGREGATION captures the per-person
                # allocation that the § 10c lump-sum stage consumes,
                # plus the joint other-Vorsorge cap (when married_joint)
                # carried inside the output as intermediate math.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.health_vorsorge_special_expenses",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                # C3-prereq (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``de.ordinary.health_vorsorge_total_eur`` is the
                # § 10 Abs. 1 Nr. 3 / Nr. 3a + § 10 Abs. 4 EStG total
                # over both spouses (or single filer). Audit-only —
                # the per-Zeile FormLineRefs are carried by the two
                # bucket scalars below (basic_health → 11-14, other
                # allowed → 31 ff.); the rolled-up scalar feeds the
                # § 10c Pauschbetrag computation downstream.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.health_vorsorge_total_eur",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``de.ordinary.health_vorsorge_basic_health_eur`` =
                # § 10 Abs. 1 Nr. 3 EStG basic Krankenversicherung +
                # Pflegeversicherung total. Lands on Anlage
                # Vorsorgeaufwand Zeilen 11-14. C-audit
                # (FORM-MAPPING-FOLLOWUP, 2026-05-04): FormLineRef
                # added so the extended I3 scanner enforces the
                # bidirectional contract on this Anlage.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.health_vorsorge_basic_health_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Vorsorgeaufwand",
                            line="11-14",
                            url=BMF_FORM_ANLAGE_VORSORGE_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``de.ordinary.health_vorsorge_other_allowed_eur`` =
                # § 10 Abs. 1 Nr. 3a EStG sonstige Vorsorgeaufwendungen
                # (subject to the § 10 Abs. 4 cap). Lands on Anlage
                # Vorsorgeaufwand Zeilen 31-37.
                # https://www.gesetze-im-internet.de/estg/__10.html
                OutputDeclaration(
                    key="de.ordinary.health_vorsorge_other_allowed_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Vorsorgeaufwand",
                            line="31-37",
                            url=BMF_FORM_ANLAGE_VORSORGE_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
            country_or_scope="DE-2025",
            legal_refs=("§ 10 EStG", "§ 10c EStG"),
            authority_urls=(ESTG_10_URL, ESTG_10C_URL),
            input_fact_keys=(
                "de.ordinary.retirement_special_expenses",
                "de.ordinary.health_vorsorge_special_expenses",
                "de.ordinary.filing_posture",
                "de.constants.sonderausgaben_pauschbetrag_joint",
                "de.constants.sonderausgaben_pauschbetrag_single",
            ),
            rounding_policy="The § 10c lump sum is added at cent precision before taxable-income assembly.",
            law_order_note="Total special expenses, including the § 10c minimum, must be fixed before § 2 Abs. 5 taxable income.",
            legal_formula="de.ordinary.total_special_expenses = sum(retirement + health_vorsorge per person) + § 10c Sonderausgaben-Pauschbetrag (joint amount when married_joint, per-person single amount otherwise)",
            narrative_templates={
                "de": "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
                "en": "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
            },
            outputs=(
                # Total special expenses (with the § 10c Sonderausgaben-
                # Pauschbetrag added) feeds the Hauptvordruck
                # Sonderausgaben block before § 2 Abs. 5 zvE assembly.
                # The Hauptvordruck FormEntry projection in
                # ``_write_hauptvordruck`` consumes this value; the
                # German renderer does not read it via
                # ``_required_form_line``. INTERMEDIATE_MATH classifies
                # it as the § 2 Abs. 5 EStG taxable-income input.
                # https://www.gesetze-im-internet.de/estg/__10c.html
                OutputDeclaration(
                    key="de.ordinary.total_special_expenses",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar
                # § 10c EStG Sonderausgaben-Pauschbetrag (joint amount
                # for married_joint, per-person single amount otherwise),
                # for the Anlage Sonderausgaben renderer. The Pauschbetrag
                # is the floor — Anlage Sonderausgaben writers do not
                # transmit it explicitly (the Finanzamt applies it
                # automatically), but the audit packet exposes it.
                # https://www.gesetze-im-internet.de/estg/__10c.html
                OutputDeclaration(
                    key="de.ordinary.sonderausgaben_pauschbetrag_applied_eur",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-SPENDENABZUG",
            country_or_scope="DE-2025",
            legal_refs=("§ 10b Abs. 1 EStG",),
            authority_urls=(ESTG_10B_URL,),
            input_fact_keys=(
                "de.ordinary.raw_inputs",
                "de.ordinary.net_employment_income",
                "de.ordinary.other_income_22nr3_taxable",
                "de.ordinary.altersentlastungsbetrag",
            ),
            rounding_policy="Cap and deductible amounts are q2-quantized at cent precision.",
            law_order_note=(
                "§ 10b is a Sonderausgabe; the cap = 20 % of Gesamtbetrag "
                "der Einkünfte after § 24a Altersentlastungsbetrag (§ 2 "
                "Abs. 4 EStG ordering). Carryforwards (§ 10b Abs. 1 "
                "Sätze 9-10 EStG) are not modeled — fail closed."
            ),
            legal_formula=(
                "GdE = sum(net_employment_income) + other_income_22nr3_taxable "
                "- altersentlastungsbetrag; "
                "de.ordinary.spendenabzug_eur = min(charitable_donations_eur, "
                "0.20 * GdE) per § 10b Abs. 1 Satz 1 Nr. 1 EStG"
            ),
            narrative_templates={
                "de": "DE25-SPENDENABZUG",
                "en": "DE25-SPENDENABZUG",
            },
            outputs=(
                # § 10b Spendenabzug appears in the Sonderausgaben block
                # of the Hauptvordruck; the FormEntry projection consumes
                # the value via results.refunds.
                # https://www.gesetze-im-internet.de/estg/__10b.html
                OutputDeclaration(
                    key="de.ordinary.spendenabzug",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar
                # § 10b Abs. 1 Satz 1 Nr. 1 EStG deductible amount
                # (capped at 20 % of GdE) for the Anlage Sonderausgaben
                # renderer.
                # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): the
                # extended I3 scanner now detects the German renderer's
                # ``"Anlage Sonderausgaben Zeilen 5-7"`` write site, so
                # this output anchors the bidirectional contract via a
                # FormLineRef per BMF Anlage Sonderausgaben 2025
                # (Spenden / Mitgliedsbeiträge an steuerbegünstigte
                # Körperschaften — Zeilen 5-7).
                # https://www.gesetze-im-internet.de/estg/__10b.html
                OutputDeclaration(
                    key="de.ordinary.spendenabzug_deductible_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Sonderausgaben",
                            line="5-7",
                            url=ESTG_10B_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
            country_or_scope="DE-2025",
            legal_refs=("§ 33 EStG", "§ 33 Abs. 3 EStG"),
            authority_urls=(ESTG_33_URL,),
            input_fact_keys=(
                "de.ordinary.raw_inputs",
                "de.ordinary.net_employment_income",
                "de.ordinary.other_income_22nr3_taxable",
                "de.ordinary.altersentlastungsbetrag",
            ),
            rounding_policy=(
                "Zumutbare Belastung is q2-quantized after the slab "
                "progression; the deductible delta is q2-quantized."
            ),
            law_order_note=(
                "§ 33 Abs. 3 EStG zumutbare Belastung is computed against "
                "Gesamtbetrag der Einkünfte, which is fixed once § 24a "
                "Altersentlastungsbetrag is subtracted from the income "
                "sum. The deductible außergewöhnliche Belastung enters "
                "the § 2 Abs. 5 zvE assembly at DE25-07."
            ),
            legal_formula=(
                "GdE = sum(net_employment_income) + other_income_22nr3_taxable "
                "- altersentlastungsbetrag; "
                "zumutbare_belastung = slab(GdE, family_category, brackets="
                "(15340, 51130), rates=ZUMUTBARE_BELASTUNG_2025_RATES); "
                "de.ordinary.aussergewoehnliche_belastungen_deductible_eur "
                "= max(0, medical_expenses_eur - zumutbare_belastung)"
            ),
            narrative_templates={
                "de": "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
                "en": "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
            },
            outputs=(
                # § 33 EStG outflow lands on the Hauptvordruck Außerge-
                # wöhnliche Belastungen block; the Hauptvordruck FormEntry
                # projection (forms/germany.py) consumes the value
                # via ``results.refunds`` rather than _required_form_line.
                # https://www.gesetze-im-internet.de/estg/__33.html
                OutputDeclaration(
                    key="de.ordinary.aussergewoehnliche_belastungen",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-UNTERHALTSLEISTUNGEN",
            country_or_scope="DE-2025",
            legal_refs=("§ 33a Abs. 1 EStG",),
            authority_urls=(ESTG_33A_URL,),
            input_fact_keys=(
                "de.ordinary.raw_inputs",
                "de.constants.unterhaltsleistungen_grundfreibetrag",
            ),
            rounding_policy="The deductible amount is q2-quantized after the cap arithmetic.",
            law_order_note=(
                "§ 33a Abs. 1 EStG is an außergewöhnliche-Belastung in "
                "besonderen Fällen, applied in parallel with § 33 (the "
                "claimant cannot stack the same expense in both stages "
                "under § 33a Abs. 4 EStG). The deduction enters § 2 Abs. 5 "
                "zvE assembly at DE25-07."
            ),
            legal_formula=(
                "eigenbezuege_reduction = max(0, recipient_income_eur - 624); "
                "cap = max(0, grundfreibetrag_eur - eigenbezuege_reduction); "
                "de.ordinary.unterhaltsleistungen_deductible_eur = "
                "min(support_payments_eur, cap) per § 33a Abs. 1 Satz 1 / "
                "Satz 5 EStG"
            ),
            narrative_templates={
                "de": "DE25-UNTERHALTSLEISTUNGEN",
                "en": "DE25-UNTERHALTSLEISTUNGEN",
            },
            outputs=(
                # § 33a Abs. 1 EStG support deduction lands on the
                # Hauptvordruck Außergewöhnliche Belastungen in besonderen
                # Fällen block; consumed by the FormEntry projection
                # (forms/germany.py) rather than _required_form_line.
                # https://www.gesetze-im-internet.de/estg/__33a.html
                OutputDeclaration(
                    key="de.ordinary.unterhaltsleistungen",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): scalar
                # § 33a Abs. 1 EStG deductible amount for the Anlage
                # Unterhalt renderer (Unterhaltsleistungen
                # innerhalb des Grundfreibetrag-Caps minus
                # Eigenbezüge-Reduktion).
                # C-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): per
                # BMF 2025, § 33a Abs. 1 EStG support payments are
                # transmitted on a SEPARATE Anlage Unterhalt (not the
                # Anlage Sonderausgaben). The C4 renderer surfaces the
                # value under the Anlage Unterhalt label
                # (``"Anlage Unterhalt Zeile 7"``), and this FormLineRef
                # anchors the bidirectional I3 contract there.
                # https://www.gesetze-im-internet.de/estg/__33a.html
                OutputDeclaration(
                    key="de.ordinary.unterhaltsleistungen_deductible_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Unterhalt",
                            line="7",
                            url=ESTG_33A_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-BEHINDERUNG-PAUSCHBETRAG",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 33b Abs. 3 EStG",
                "§ 33b Abs. 5 EStG",
                "§ 33b Abs. 7 EStG",
            ),
            authority_urls=(ESTG_33B_URL,),
            input_fact_keys=(
                "de.ordinary.people",
                # Gap 2 — § 33b Abs. 5 EStG transferral. Pipeline 1
                # derived total summed across qualifying children when
                # the parents claim the transferral; zero when the
                # election is false or no qualifying child carries a
                # §-33b-Abs.-3-EStG Pauschbetrag.
                "de.derived.children_disability_pauschbetrag_total_eur",
                # § 33b Abs. 5 Satz 3 EStG split override. ``None`` when
                # the parents accept the statutory 50/50 default (the
                # canonical posture under "zu gleichen Teilen
                # aufgeteilt"); a tuple of Decimal shares summing to 1
                # when they jointly elect another allocation via Anlage
                # Kind 2025 Zeile 66 ("anderweitige prozentuale
                # Aufteilung"). Validated inside the rule body — an
                # invalid override fails closed rather than silently
                # reverting to 50/50.
                "de.profile.disability_pauschbetrag_transfer_split",
            ),
            rounding_policy="Per-person Pauschbetrag is a fixed cent-precision EUR amount; the household total sums per-person amounts plus the § 33b Abs. 5 EStG child transferral total. Per-person allocations of the transferral apply the § 33b Abs. 5 Satz 3 EStG share, q2-quantized, with the last person absorbing rounding so the per-person sum equals the household total exactly.",
            law_order_note=(
                "§ 33b Pauschbetrag is a Sonderausgaben-adjacent flat "
                "deduction; it enters § 2 Abs. 5 zvE assembly at DE25-07 "
                "in parallel with § 33 / § 33a. § 33b Abs. 7 EStG forbids "
                "stacking the same disability-related expense in § 33 — "
                "the cross-stage gate is a future enhancement; for now "
                "the workspace must elect one path. § 33b Abs. 5 EStG "
                "transferral of a qualifying child's Pauschbetrag is "
                "summed into the household total via the Pipeline 1 "
                "derived fact; the legally-effective application of "
                "the transferral happens here, while the children "
                "sub-graph stage DE25-CHILDREN-DISABILITY-PAUSCHBETRAG "
                "re-emits the same scalar for audit."
            ),
            legal_formula=(
                "de.ordinary.behinderung_pauschbetrag[per_person] = "
                "BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[gdb] if not "
                "hilflos_or_blind else BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR; "
                "household total = sum across spouses (each carries their own GdB) "
                "+ de.derived.children_disability_pauschbetrag_total_eur "
                "(per § 33b Abs. 5 EStG transferral when the profile "
                "election is true; zero otherwise)"
            ),
            narrative_templates={
                "de": "DE25-BEHINDERUNG-PAUSCHBETRAG",
                "en": "DE25-BEHINDERUNG-PAUSCHBETRAG",
            },
            outputs=(
                # § 33b Pauschbetrag lands on the Hauptvordruck
                # Außergewöhnliche Belastungen block via FormEntry
                # projection rather than _required_form_line.
                # https://www.gesetze-im-internet.de/estg/__33b.html
                OutputDeclaration(
                    key="de.ordinary.behinderung_pauschbetrag",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-07-TAXABLE-INCOME",
            country_or_scope="DE-2025",
            legal_refs=("§ 2 Abs. 3 EStG", "§ 2 Abs. 4 EStG", "§ 2 Abs. 5 EStG", "§ 18 EStG", "§ 26b EStG", "§ 24a EStG", "§ 33 EStG", "§ 33a EStG", "§ 33b EStG", "§ 10b EStG", "§ 4 Abs. 5 EStG"),
            authority_urls=(ESTG_2_URL, ESTG_18_URL, ESTG_26B_URL, ESTG_24A_URL, ESTG_33_URL, ESTG_33A_URL, ESTG_33B_URL, ESTG_10B_URL, ESTG_4_5_6B_URL),
            input_fact_keys=(
                "de.ordinary.net_employment_income",
                "de.ordinary.other_income_22nr3_taxable",
                "de.ordinary.business_profit_eur",
                "de.ordinary.altersentlastungsbetrag",
                "de.ordinary.arbeitszimmer",
                "de.ordinary.total_special_expenses",
                "de.ordinary.spendenabzug",
                "de.ordinary.aussergewoehnliche_belastungen",
                "de.ordinary.unterhaltsleistungen",
                "de.ordinary.behinderung_pauschbetrag",
                "de.ordinary.filing_posture",
                "de.constants.sonderausgaben_pauschbetrag_single",
            ),
            rounding_policy="Taxable income remains cent-level; tariff functions apply statutory euro rounding.",
            law_order_note="The income sum (incl. § 18 selbständige Arbeit profit) and special expenses (incl. § 4 Abs. 5 Satz 1 Nr. 6b Arbeitszimmer, § 24a, § 10b, § 33, § 33a, § 33b) must be resolved before the tariff base.",
            legal_formula="de.ordinary.taxable_income = household-level sum(net_employment_income) + other_income_22nr3_taxable + § 18 business_profit_eur - § 24a altersentlastungsbetrag - § 4 Abs. 5 Satz 1 Nr. 6b arbeitszimmer - total_special_expenses - § 10b spendenabzug - § 33 aussergewoehnliche_belastungen_deductible - § 33a unterhaltsleistungen_deductible - § 33b behinderung_pauschbetrag if married_joint (per § 26b aggregation); otherwise sum per-person taxable bases (per § 2 Abs. 5 single assessment, with each person's GdB allowance subtracted from their own base)",
            narrative_templates={
                "de": "DE25-07-TAXABLE-INCOME",
                "en": "DE25-07-TAXABLE-INCOME",
            },
            outputs=(
                # zvE (zu versteuerndes Einkommen) is the Hauptvordruck
                # tariff base per § 2 Abs. 3 / Abs. 5 EStG / § 26b EStG;
                # § 26b joint aggregation vs. § 2 Abs. 5 single assembly
                # is selected by filing posture inside the rule body.
                # The Hauptvordruck FormEntry projection consumes this
                # value; the renderer does not read it via
                # ``_required_form_line``. INTERMEDIATE_MATH classifies
                # it as the input to the § 32a EStG tariff stage.
                # https://www.gesetze-im-internet.de/estg/__2.html
                OutputDeclaration(
                    key="de.ordinary.taxable_income",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-08-INCOME-TAX-TARIFF",
            country_or_scope="DE-2025",
            legal_refs=("§ 26b EStG", "§ 32a Abs. 1 EStG", "§ 32a Abs. 5 EStG"),
            authority_urls=(ESTG_26B_URL, ESTG_32A_URL, BMF_PAP_2025_URL),
            input_fact_keys=("de.ordinary.taxable_income", "de.ordinary.filing_posture"),
            rounding_policy="The 2025 BMF Programmablaufplan applies statutory euro rounding inside the tariff.",
            law_order_note="Tariff selection is law-driven by filing posture: § 32a(5) splitting only after § 26b aggregation; § 32a(1) basic tariff otherwise.",
            legal_formula="de.ordinary.income_tax = 2 * basic_tariff_2025(taxable_income / 2) per § 32a Abs. 5 EStG if filing_posture == 'married_joint'; else basic_tariff_2025(per_person_taxable_income) summed across household per § 32a Abs. 1 EStG",
            narrative_templates={
                "de": "DE25-08-INCOME-TAX-TARIFF",
                "en": "DE25-08-INCOME-TAX-TARIFF",
            },
            outputs=(
                # Tarifliche Einkommensteuer is the Steuerberechnung
                # value driven by § 32a EStG and the BMF
                # Programmablaufplan 2025. The Steuerberechnung is a
                # logical output of the tariff function consumed by
                # downstream stages (§ 36 EStG credit, § 4 SolzG soli);
                # there is no ``_required_form_line`` read on a
                # "Steuerberechnung" form because Steuerberechnung
                # itself is a calculation block rather than a BMF
                # Anlage. INTERMEDIATE_MATH captures that role.
                # https://www.gesetze-im-internet.de/estg/__32a.html
                OutputDeclaration(
                    key="de.ordinary.income_tax",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-09-ORDINARY-SOLI",
            country_or_scope="DE-2025",
            legal_refs=("§ 3 SolzG 1995", "§ 4 SolzG 1995"),
            authority_urls=(SOLZG_3_URL, SOLZG_4_URL, BMF_PAP_2025_URL),
            input_fact_keys=("de.ordinary.income_tax", "de.ordinary.filing_posture"),
            rounding_policy="Soli is floored to cent precision after the statutory threshold/milderungszone comparison.",
            law_order_note="Ordinary solidarity surcharge is computed from assessed ordinary income tax.",
            legal_formula="de.ordinary.solidarity_surcharge = SolzG 1995 § 3/§ 4 threshold and Milderungszone applied to de.ordinary.income_tax (joint amount when married_joint, summed per-person otherwise)",
            narrative_templates={
                "de": "DE25-09-ORDINARY-SOLI",
                "en": "DE25-09-ORDINARY-SOLI",
            },
            outputs=(
                # Ordinary Solidaritätszuschlag per § 3 / § 4 SolzG
                # 1995 is consumed by the § 36 EStG credit/refund stage
                # downstream; the Steuerberechnung block is a
                # calculation surface, not a BMF Anlage the renderer
                # reads via ``_required_form_line``. INTERMEDIATE_MATH
                # captures that role.
                # https://www.gesetze-im-internet.de/solzg_1995/__4.html
                OutputDeclaration(
                    key="de.ordinary.solidarity_surcharge",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        LawStage(
            stage_id="DE25-10-ORDINARY-CREDITS",
            country_or_scope="DE-2025",
            legal_refs=("§ 36 Abs. 2 EStG", "§ 36 Abs. 3 EStG"),
            authority_urls=(ESTG_36_URL,),
            input_fact_keys=(
                "de.ordinary.income_tax",
                "de.ordinary.solidarity_surcharge",
                "de.ordinary.people",
                "de.ordinary.filing_posture",
                "de.ordinary.prepayments",
                "de.ordinary.prepayments_by_person",
            ),
            rounding_policy="§ 36 Abs. 3 EStG rounds withholding-credit sums up to full euros by credit type; prepayments remain exact cent amounts.",
            law_order_note="Section 36 payment/refund arithmetic follows the ordinary tax and surcharge calculation.",
            legal_formula="de.ordinary.refund_before_capital = ceil_euro(sum(withheld_wage_tax)) + ceil_euro(sum(withheld_solidarity_surcharge)) + prepayments - income_tax - solidarity_surcharge per § 36 Abs. 2/3 EStG",
            narrative_templates={
                "de": "DE25-10-ORDINARY-CREDITS",
                "en": "DE25-10-ORDINARY-CREDITS",
            },
            outputs=(
                # Anrechnung Lohnsteuer / Vorauszahlungen per § 36
                # Abs. 2 / Abs. 3 EStG. The headline refund-before-
                # capital number is consumed by the Hauptvordruck
                # FormEntry projection in ``_write_hauptvordruck`` and
                # by the Phase-4 DE25-22 final-refund stage; the
                # German renderer does not read it via
                # ``_required_form_line``. RECONCILIATION_INVARIANT
                # captures the cross-check role between withholding
                # totals (Anlage N), prepayments (profile), and the
                # ordinary tariff result.
                # https://www.gesetze-im-internet.de/estg/__36.html
                OutputDeclaration(
                    key="de.ordinary.refund_before_capital",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
    )


def germany_capital_law_stages_2025() -> tuple[LawStage, ...]:
    # Capital stages declare outputs via the new ``outputs`` shape:
    # each output's form-line provenance is per-output (one OutputDeclaration
    # per stage_output_key) and audit_waypoints classify the value-shape
    # facets that are not on a form line (per-Posten aggregations,
    # intermediate math, reconciliation invariants, diagnostic
    # cross-checks).
    #
    # Form-line refs anchor each output to the concrete (form, Zeile)
    # pair the renderer reads from ``germany-kap-summary.csv`` (produced
    # by ``germany_projections.capital_form_projection_2025``). Per
    # invariant I3 (``tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py``),
    # every renderer ``_required_form_line(rows, form, line, ...)`` read
    # must be declared by some ``OutputDeclaration``, and conversely
    # every ``OutputDeclaration.form_line_refs`` entry must be consumed
    # by the renderer. The legacy descriptive labels (e.g. "Anlage KAP —
    # Abgeltungsteuer 25 %") are replaced by concrete person-specific
    # labels ("Anlage KAP - Person 1" / "Anlage KAP - Person 2") and the
    # numeric Zeile that the BMF Anlage KAP / KAP-INV physical form
    # carries. This is a deliberate stage-fingerprint churn (WS-2B):
    # the prior classification was wrong because none of the descriptive
    # labels appeared on a real BMF form line.
    return (
        # DE25-13 — § 20 EStG bucket classification + InvStG fund symbol
        # classification + bank-certificate Zeile 7/8 split + per-item
        # foreign-tax index. The raw_buckets dict produces the gross
        # values that flow into Anlage KAP (Person 1 lines 20/21/23/24
        # for stock and option pos/neg, Person 2 lines 5/7/8 for the
        # bank-certificate review checkbox + KAP Zeile 7 capital income
        # + KAP Zeile 8 stock-sale gains) and Anlage KAP-INV (lines 4/8
        # for fund distributions and Zeilen 9-13 for Vorabpauschalen).
        # Authority: § 20 Abs. 1 / Abs. 2 EStG and InvStG §§ 16-20.
        # https://www.gesetze-im-internet.de/estg/__20.html
        # https://www.gesetze-im-internet.de/invstg_2018/__20.html
        LawStage(
            stage_id="DE25-13-CAPITAL-RAW-BUCKETS",
            country_or_scope="DE-2025",
            legal_refs=("§ 20 EStG", "InvStG § 16", "InvStG § 19", "InvStG § 20"),
            authority_urls=(ESTG_20_URL, INVSTG_20_URL),
            input_fact_keys=(
                # WS-5A (invariant migration plan §7): the five raw-input
                # derivations DE25-13 historically performed inline now
                # live as Pipeline 1 stages. DE25-13's calculate body
                # consumes the typed derived facts and applies only § 20
                # EStG bucket assembly (the legal interpretation that
                # belongs in Pipeline 2).
                "de.derived.per_symbol_sale_aggregation",
                "de.derived.box_1a_filtered_dividends",
                "de.derived.per_symbol_bank_certificate_buckets",
                "de.derived.source_country_classification",
                "de.derived.foreign_tax_indexing",
            ),
            rounding_policy="Raw capital buckets remain cent-level Decimal amounts before legal netting.",
            law_order_note="Capital facts must be classified into stock, fund, option, and income buckets before special rules apply.",
            legal_formula="de.capital.raw_buckets = classify(sale_facts, income_facts, bank_certificates) into {stock, fund, option, income} buckets with per-symbol indices and per-item foreign-tax tracking per § 20 EStG and InvStG §§ 16-20",
            narrative_templates={
                "de": "DE25-13-CAPITAL-RAW-BUCKETS",
                "en": "DE25-13-CAPITAL-RAW-BUCKETS",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.raw_buckets",
                    form_line_refs=(
                        # Anlage KAP - Person 1 stock buckets
                        # (§ 20 Abs. 2 Satz 1 Nr. 1 EStG). JStG 2024
                        # (in Kraft 06.12.2024) deleted § 20 Abs. 6
                        # Sätze 5 und 6 EStG; the former 2024
                        # per-bucket FormLineRef entries for
                        # Termingeschäfte positives and
                        # Termingeschäfte losses are removed for
                        # VZ 2025. option_pos / option_neg components
                        # still net into Anlage KAP Person 1 via the
                        # surviving Zeile-19 sum inside DE25-FORM-KAP-
                        # PROJECTION. BMF 16.05.2025 Steuerbescheinigung-
                        # Schreiben. BMF-VERIFIED 2026-05-13.
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="20",
                            url=ESTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="23",
                            url=ESTG_20_URL,
                        ),
                        # Anlage KAP - Person 2 bank-certificate review +
                        # raw capital income + included stock gains
                        # (§ 20 Abs. 1 / Abs. 2 EStG via Steuerbescheinigung).
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="5",
                            url=ESTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="7",
                            url=ESTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="8",
                            url=ESTG_20_URL,
                        ),
                        # Anlage KAP-INV gross fund distributions and
                        # Vorabpauschalen per InvStG § 16 / § 18.
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="4",
                            url=INVSTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="8",
                            url=INVSTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="9-13",
                            url=INVSTG_20_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # DE25-13F — InvStG § 19 Vorabpauschale (deemed-distribution for
        # accumulating funds). § 18 fixes the Basisertrag formula:
        # ``Basisertrag = NAV_start * 0.7 * Basiszinssatz * months_held / 12``.
        # § 19 then nets actual Ausschuettungen against the Basisertrag and
        # caps the result at the year's NAV gain (§ 16 Abs. 1 Nr. 2):
        # ``Vorabpauschale = max(0, min(NAV_end - NAV_start,
        #     max(0, Basisertrag - Ausschuettung)))``.
        # The Teilfreistellung rate that already routes Ausschuettungen
        # (DE25-14) applies to the Vorabpauschale identically (InvStG § 20).
        # The Basiszinssatz for 2025 is 2.53 %, BMF-Schreiben 16.01.2025
        # (IV C 1 - S 1980-1/19/10005:008).
        # https://www.gesetze-im-internet.de/invstg_2018/__18.html
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        # https://www.gesetze-im-internet.de/invstg_2018/__16.html
        # https://www.gesetze-im-internet.de/invstg_2018/__20.html
        LawStage(
            stage_id="DE25-13F-VORABPAUSCHALE",
            country_or_scope="DE-2025",
            legal_refs=(
                "InvStG § 16 Abs. 1 Nr. 2",
                "InvStG § 18",
                "InvStG § 19",
                "InvStG § 20",
                "BMF Schreiben 16.01.2025",
            ),
            authority_urls=(
                INVSTG_16_URL,
                INVSTG_18_URL,
                INVSTG_19_URL,
                INVSTG_20_URL,
                BMF_BASISZINS_2025_URL,
            ),
            input_fact_keys=(
                "de.derived.vorabpauschale_inputs",
                "de.capital.fund_classification",
                "de.capital.fund_teilfreistellung_rates",
                "de.capital.basiszins",
                "de.capital.vorabpauschale_basisertrag_factor",
            ),
            rounding_policy=(
                "Per-fund Vorabpauschale amounts are q2-quantized at cent "
                "precision after the § 16 Abs. 1 Nr. 2 NAV-gain cap and "
                "before the InvStG § 20 Teilfreistellung is applied."
            ),
            law_order_note=(
                "Vorabpauschale is laufender Ertrag under InvStG § 19; it "
                "feeds into § 20 Abs. 6 EStG as non-stock-gain income "
                "(NOT a Veräusserungsgewinn — § 20 Abs. 6 Satz 4 prohibits "
                "offsetting against stock losses)."
            ),
            legal_formula=(
                "for each fund: "
                "basisertrag = max(0, NAV_start * 0.7 * Basiszins * months_held / 12); "
                "gross_vorab = max(0, basisertrag - Ausschuettung); "
                "nav_gain = max(0, NAV_end - NAV_start); "
                "vorabpauschale = min(gross_vorab, nav_gain); "
                "taxable_after_teilfreistellung = vorabpauschale * "
                "(1 - teilfreistellung_rate(fund_type)) "
                "per InvStG § 18 / § 19 / § 16 Abs. 1 Nr. 2 / § 20"
            ),
            narrative_templates={
                "de": "DE25-13F-VORABPAUSCHALE",
                "en": "DE25-13F-VORABPAUSCHALE",
            },
            outputs=(
                # Per-symbol Vorabpauschale before Teilfreistellung — per-Posten
                # breakdown for audit / Anlage KAP-INV per-fund support.
                OutputDeclaration(
                    key="de.capital.vorabpauschale_per_symbol_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
                # Total Vorabpauschale (gross) — pre-Teilfreistellung.
                OutputDeclaration(
                    key="de.capital.vorabpauschale_total_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
                # Total Vorabpauschale after InvStG § 20 Teilfreistellung —
                # the laufender-Ertrag amount that lands on Anlage KAP-INV
                # Zeilen 9-13 and feeds § 20 Abs. 6 EStG netting (DE25-15).
                OutputDeclaration(
                    key="de.capital.vorabpauschale_taxable_after_teilfreistellung_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="9-13",
                            url=INVSTG_19_URL,
                        ),
                    ),
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
            ),
        ),
        # DE25-14 — InvStG § 20 Teilfreistellung. The fund-sale gains
        # after Teilfreistellung land on Anlage KAP-INV Zeile 14
        # (Aktienfonds) and Zeile 26 (sonstige Investmentfonds).
        # https://www.gesetze-im-internet.de/invstg_2018/__20.html
        LawStage(
            stage_id="DE25-14-FUND-TEILFREISTELLUNG",
            country_or_scope="DE-2025",
            legal_refs=("InvStG § 20", "InvStG § 21"),
            authority_urls=(INVSTG_20_URL, INVSTG_21_URL),
            input_fact_keys=(
                "de.capital.raw_buckets",
                "de.capital.fund_classification",
                "de.capital.fund_teilfreistellung_rates",
            ),
            rounding_policy="Teilfreistellung percentages are applied before section 20 netting and allowance.",
            law_order_note="InvStG partial exemption/loss disallowance must precede section 20 loss ordering.",
            legal_formula="de.capital.fund_after_teilfreistellung = fund_gain * (1 - teilfreistellung_rate(fund_type)) per InvStG § 20; per-symbol fund taxable amounts after rate also retained",
            narrative_templates={
                "de": "DE25-14-FUND-TEILFREISTELLUNG",
                "en": "DE25-14-FUND-TEILFREISTELLUNG",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.fund_after_teilfreistellung",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="14",
                            url=INVSTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="26",
                            url=INVSTG_20_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # DE25-15 — § 20 Abs. 6 EStG loss-class ordering. The netted
        # non-fund capital income lands on Anlage KAP - Person 1 Zeile
        # 19 (kap_line_19 = ordinary + stock_pos − stock_neg + option_pos
        # − option_neg, after § 20 Abs. 6 EStG ordering and BMF
        # Abgeltungsteuer Rn. 120/122/228-230).
        # https://www.gesetze-im-internet.de/estg/__20.html
        LawStage(
            stage_id="DE25-15-SECTION-20-6-NETTING",
            country_or_scope="DE-2025",
            legal_refs=("§ 20 Abs. 6 EStG", "BMF Abgeltungsteuer Rn. 120, 122, 228-230"),
            authority_urls=(ESTG_20_URL, BMF_ABGELTUNGSTEUER_URL),
            input_fact_keys=(
                "de.capital.raw_buckets",
                "de.capital.fund_after_teilfreistellung",
                "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur",
                "de.capital.stock_loss_carryforward_2024",
                "de.capital.treaty_dividend_items",
                "de.capital.fund_classification",
                "de.capital.fund_teilfreistellung_rates",
            ),
            rounding_policy="Loss buckets are netted at cent precision before the saver allowance.",
            law_order_note="Section 20(6) loss restrictions apply before the section 20(9) allowance.",
            legal_formula="current_year_non_stock_net = option_gain + fund_taxable_after_teilfreistellung + non_fund_positive_income; stock_gain_after_carryforward = max(0, stock_gain - stock_loss_carryforward_used) after § 20 Abs. 6 EStG ordering; treaty dividend items integrated into the per-item foreign-tax index",
            narrative_templates={
                "de": "DE25-15-SECTION-20-6-NETTING",
                "en": "DE25-15-SECTION-20-6-NETTING",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.after_section_20_6_netting",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="19",
                            url=ESTG_20_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # DE25-16 — § 20 Abs. 9 EStG Sparer-Pauschbetrag. The
        # already-used saver allowance lands on Anlage KAP Zeile 17 for
        # each person who has a Steuerbescheinigung carrying the bank's
        # already-applied allowance share. Person 1 (Schwab) carries a
        # zero already-used allowance; Person 2 (bank certificate)
        # carries the certificate's kap_line_17_saver_allowance_used_eur.
        # https://www.gesetze-im-internet.de/estg/__20.html
        LawStage(
            stage_id="DE25-16-SECTION-20-9-SAVER",
            country_or_scope="DE-2025",
            legal_refs=("§ 20 Abs. 9 Satz 3 EStG",),
            authority_urls=(ESTG_20_URL,),
            input_fact_keys=(
                "de.capital.after_section_20_6_netting",
                "de.capital.fund_after_teilfreistellung",
                "de.capital.raw_buckets",
                "de.capital.saver_allowance",
                "de.capital.other_spouse_capital_before_allowance",
                "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur",
            ),
            rounding_policy="Saver allowance is capped to the positive net capital base and statutory allowance.",
            law_order_note="The saver allowance reduces net capital income before section 32d tax.",
            legal_formula="saver_allowance_used = min(saver_allowance_eur, total_taxable_before_allowance) (with spouse-allocation per § 20 Abs. 9 Satz 3 EStG when other_spouse_capital_before_allowance is set); taxable_after_teilfreistellung = max(0, primary_taxable_after_teilfreistellung_before_allowance - saver_allowance_used)",
            narrative_templates={
                "de": "DE25-16-SECTION-20-9-SAVER",
                "en": "DE25-16-SECTION-20-9-SAVER",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.taxable_after_allowance",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="17",
                            url=ESTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="17",
                            url=ESTG_20_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # A4 (FORM-MAPPING-FOLLOWUP): § 20 Abs. 9 Satz 1/2 EStG
                # Sparer-Pauschbetrag claim line on Anlage KAP Zeile 4.
                # The value is the statutory cap (€1,000 single / €2,000
                # jointly assessed spouses) the user enters before any
                # § 20 Abs. 9 Satz 3 spouse-allocation. Both spouses'
                # Anlage KAP Z4 carries the same statutory amount under
                # the joint-assessment convention; the *used* allocation
                # is the existing Z17 output above.
                # https://www.gesetze-im-internet.de/estg/__20.html
                OutputDeclaration(
                    key="de.capital.sparer_pauschbetrag_claimed_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="4",
                            url=ESTG_20_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="4",
                            url=ESTG_20_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # DE25-17 — § 32d Abs. 1 EStG 25 % flat capital tax. On the BMF
        # Anlage KAP this materialises as the bank-certificate Zeile 37
        # (Kapitalertragsteuer einbehalten / KESt withheld), which is
        # the per-bank realisation of the § 32d Abs. 1 EStG flat rate
        # for the certificate-bearing person. Person 2's bank
        # certificate carries the line; Person 1's Schwab package has
        # no German bank certificate to populate. WS-2B re-anchors this
        # output from the prior descriptive Anlage-KAP label (which the
        # renderer never read) onto the actual Zeile 37 the renderer
        # consumes via ``_required_form_line``.
        # https://www.gesetze-im-internet.de/estg/__32d.html
        LawStage(
            stage_id="DE25-17-SECTION-32D1-GROSS-TAX",
            country_or_scope="DE-2025",
            legal_refs=("§ 32d Abs. 1 EStG",),
            authority_urls=(ESTG_32D_URL,),
            input_fact_keys=(
                "de.capital.taxable_after_allowance",
                "de.capital.capital_tax_rate",
            ),
            rounding_policy="Gross capital tax is computed at cent precision before foreign-tax credits.",
            law_order_note="Section 32d(1) imposes the flat tax before section 32d(5) foreign-tax credit reduction.",
            legal_formula="de.capital.section_32d1_gross_tax.gross_income_tax_with_teilfreistellung = capital_tax_rate * taxable_after_teilfreistellung; gross_income_tax_no_teilfreistellung = capital_tax_rate * taxable_before_teilfreistellung (per § 32d Abs. 1 EStG)",
            narrative_templates={
                "de": "DE25-17-SECTION-32D1-GROSS-TAX",
                "en": "DE25-17-SECTION-32D1-GROSS-TAX",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.section_32d1_gross_tax",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="37",
                            url=ESTG_32D_URL,
                        ),
                    ),
                ),
            ),
        ),
        # DE25-18 — § 32d Abs. 5 EStG per-item foreign-tax credit. The
        # creditable foreign tax lands on Anlage KAP - Person 1 Zeile 41
        # (Schwab 1099 foreign tax) and Anlage KAP - Person 2 Zeile 40
        # (foreign tax already credited per the bank certificate).
        # https://www.gesetze-im-internet.de/estg/__32d.html
        LawStage(
            stage_id="DE25-18-SECTION-32D5-FTC",
            country_or_scope="DE-2025",
            legal_refs=("§ 32d Abs. 5 EStG",),
            authority_urls=(ESTG_32D_URL,),
            input_fact_keys=(
                "de.capital.section_32d1_gross_tax",
                "de.capital.after_section_20_6_netting",
                "de.capital.taxable_after_allowance",
                "de.capital.capital_tax_rate",
            ),
            rounding_policy="Foreign-tax credit caps are computed per item/source before aggregate credit application.",
            law_order_note="Section 32d(5) credit reduces the section 32d(1) tax before capital solidarity surcharge.",
            legal_formula="foreign_tax_credit_cap = sum_per_item(min(net_foreign_tax_after_refund, taxable_item * capital_tax_rate)); applied_credit = min(foreign_tax_credit_cap, gross_income_tax) per § 32d Abs. 5 EStG; per-item credit caps after § 20 Abs. 9 allowance allocation also retained",
            narrative_templates={
                "de": "DE25-18-SECTION-32D5-FTC",
                "en": "DE25-18-SECTION-32D5-FTC",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.section_32d5_foreign_tax_credit",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="41",
                            url=ESTG_32D_URL,
                        ),
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="40",
                            url=ESTG_32D_URL,
                        ),
                        # Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                        # Anlage AUS Zeilen 8 / 9 / 13 / 15 — the four
                        # EUR-Decimal lines that transcribe the per-
                        # country § 34c (1) EStG foreign-tax-credit
                        # breakdown of the same
                        # de.capital.section_32d5_foreign_tax_credit
                        # money flow that lands on Anlage KAP Zeilen
                        # 40 / 41. Anlage AUS Zeile 4 (Land /
                        # text), Zeile 6 (Art der Einkünfte / text), and
                        # Zeile 11 (Steuer in Quellenwährung — non-EUR,
                        # informational) are NOT declared here because
                        # they are not EUR-Decimal values flowing
                        # through the I11 LegalValue envelope. The
                        # I3 scanner only looks at ``legal_value_entry``
                        # call sites (LegalValue boundary writes), so
                        # adding text-only Zeilen as FormLineRefs would
                        # produce orphan declarations. The
                        # per-country split is computed by the
                        # standalone derivation
                        # ``derive_de_anlage_aus_2025`` (no rule-graph
                        # arithmetic; no new output_key).
                        # https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025
                        # https://www.gesetze-im-internet.de/estg/__34c.html
                        FormLineRef(
                            form="Anlage AUS",
                            line="8",
                            url=ELSTER_ANLAGE_AUS_2025_URL,
                        ),
                        FormLineRef(
                            form="Anlage AUS",
                            line="9",
                            url=ELSTER_ANLAGE_AUS_2025_URL,
                        ),
                        FormLineRef(
                            form="Anlage AUS",
                            line="13",
                            url=ELSTER_ANLAGE_AUS_2025_URL,
                        ),
                        FormLineRef(
                            form="Anlage AUS",
                            line="15",
                            url=ESTG_34C_URL,
                        ),
                    ),
                    audit_waypoints=frozenset(
                        {
                            AuditWaypoint.PER_POSTEN_AGGREGATION,
                            AuditWaypoint.RECONCILIATION_INVARIANT,
                        }
                    ),
                ),
            ),
        ),
        # DE25-19 — § 4 SolzG 1995 capital solidarity surcharge. On the
        # BMF Anlage KAP this is the bank-certificate Zeile 38
        # (Solidaritätszuschlag einbehalten on KESt) — the per-bank
        # realisation of the § 4 SolzG capital soli for the
        # certificate-bearing person. Person 2's bank certificate
        # carries the line; Person 1's Schwab package has no German
        # bank certificate. WS-2B re-anchors this output from the prior
        # descriptive Anlage-KAP label onto Zeile 38.
        # https://www.gesetze-im-internet.de/solzg_1995/__4.html
        LawStage(
            stage_id="DE25-19-CAPITAL-SOLI",
            country_or_scope="DE-2025",
            legal_refs=("§ 3 SolzG 1995", "§ 4 SolzG 1995"),
            authority_urls=(SOLZG_3_URL, SOLZG_4_URL),
            input_fact_keys=(
                "de.capital.section_32d1_gross_tax",
                "de.capital.section_32d5_foreign_tax_credit",
                "de.capital.soli_rate",
            ),
            rounding_policy="Capital solidarity surcharge is kept at cent precision after credit ordering.",
            law_order_note="SolzG applies to the remaining capital income tax after the section 32d(5) credit.",
            legal_formula="income_tax_after_foreign_credit = max(0, gross_income_tax - foreign_tax_credit_applied); de.capital.solidarity_surcharge = floor_cent(soli_rate * income_tax_after_foreign_credit) per § 4 SolzG 1995",
            narrative_templates={
                "de": "DE25-19-CAPITAL-SOLI",
                "en": "DE25-19-CAPITAL-SOLI",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.solidarity_surcharge",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 2",
                            line="38",
                            url=SOLZG_4_URL,
                        ),
                    ),
                ),
            ),
        ),
        # DE25-20 — DBA-USA Art. 10/Art. 23 cross-check via § 32d Abs.
        # 5. The treaty cross-check fails closed when the manual treaty
        # credit pool would bypass § 32d(5) per-item ordering; it does
        # not write a bespoke Anlage-KAP form line of its own.
        # Classified RECONCILIATION_INVARIANT (treaty packet vs. § 32d
        # caps reconciliation) plus PER_POSTEN_AGGREGATION (per-item
        # U.S.-source dividend exports).
        LawStage(
            stage_id="DE25-20-TREATY-CHECK",
            country_or_scope="DE-2025",
            legal_refs=("DBA-USA Art. 10", "DBA-USA Art. 23", "§ 32d Abs. 5 EStG"),
            authority_urls=(BMF_USA_PAGE_URL, ESTG_32D_URL),
            input_fact_keys=(
                "de.capital.solidarity_surcharge",
                "de.capital.section_32d5_foreign_tax_credit",
                "de.capital.after_section_20_6_netting",
                "de.capital.taxable_after_allowance",
                "de.capital.treaty_dividend_credit",
                "de.capital.capital_tax_rate",
            ),
            rounding_policy="Separate treaty credits are rejected unless explicitly modeled through the section 32d(5) sequence.",
            law_order_note="Treaty relief cannot be added after domestic credit ordering unless the specific legal path is modeled.",
            legal_formula="de.capital.treaty_credit_check fails closed if treaty_dividend_credit > 0; otherwise allocates per-item credit to U.S.-source dividends per DBA-USA Art. 10 and Art. 23 routed through § 32d Abs. 5 EStG",
            narrative_templates={
                "de": "DE25-20-TREATY-CHECK",
                "en": "DE25-20-TREATY-CHECK",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.treaty_credit_check",
                    audit_waypoints=frozenset(
                        {
                            AuditWaypoint.PER_POSTEN_AGGREGATION,
                            AuditWaypoint.RECONCILIATION_INVARIANT,
                        }
                    ),
                ),
            ),
        ),
        # DE25-21 — Final modeled capital tax = post-treaty income tax +
        # post-treaty soli. The headline scalar is consumed by
        # downstream § 36 EStG refund arithmetic (DE25-22-FINAL-REFUND
        # in Phase 4); it does not directly write a single bank
        # certificate Zeile, so we classify it as RECONCILIATION_INVARIANT
        # (final cross-check between § 32d(1) gross tax, § 32d(5)
        # credit, § 4 SolzG soli, and the DBA-USA cross-check).
        LawStage(
            stage_id="DE25-21-FINAL-CAPITAL-TAX",
            country_or_scope="DE-2025",
            legal_refs=("§ 32d Abs. 1 EStG", "§ 32d Abs. 5 EStG", "§ 4 SolzG 1995"),
            authority_urls=(ESTG_32D_URL, SOLZG_4_URL),
            input_fact_keys=(
                "de.capital.solidarity_surcharge",
                "de.capital.treaty_credit_check",
                "de.capital.section_32d5_foreign_tax_credit",
            ),
            rounding_policy="Capital tax and capital soli are kept at cent precision after credit ordering.",
            law_order_note="Final capital liability follows domestic section 32d and SolzG ordering plus the treaty fail-closed check.",
            legal_formula="de.capital.final_tax = treaty_credit_check.income_tax_after_treaty + treaty_credit_check.solidarity_surcharge_after_treaty (after § 5 SolzG 1995 ordering and DBA-USA Art. 23 fail-closed check)",
            narrative_templates={
                "de": "DE25-21-FINAL-CAPITAL-TAX",
                "en": "DE25-21-FINAL-CAPITAL-TAX",
            },
            outputs=(
                OutputDeclaration(
                    key="de.capital.final_tax",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
    )


def germany_children_law_stages_2025() -> tuple[LawStage, ...]:
    """§ 31 EStG Familienleistungsausgleich Günstigerprüfung sub-graph stages.

    DE25-CHILDREN-CREDITS performs the comparison between Kindergeld
    retention and Kinderfreibetrag deduction (§ 31 EStG Satz 1) using
    the per-child aggregates produced by Pipeline 1's
    ``DERIVE-DE25-CHILDREN``. The stage:

    - Computes ordinary tariff at the as-modeled zvE (already the value
      that reaches DE25-08 and the final-refund chain).
    - Computes the counterfactual ordinary tariff at zvE minus the
      § 32 Abs. 6 EStG Kinderfreibetrag + BEA-Freibetrag total.
    - Picks ``"kinderfreibetrag"`` when that tariff differential exceeds
      Kindergeld received (§ 31 Satz 4 EStG) and ``"kindergeld"``
      otherwise.

    No mutation of DE25-07 zvE or DE25-08 tariff happens here — the
    chosen relief value is consumed by the final-settlement stage which
    applies the § 31 Satz 4 EStG netting. This mirrors how DBA-USA
    Article 23 routing is applied at the final stage rather than inside
    the per-rule capital chain.

    Authority:
    - § 31 EStG (Familienleistungsausgleich, Günstigerprüfung):
      https://www.gesetze-im-internet.de/estg/__31.html
    - § 32 Abs. 6 EStG (Kinderfreibetrag + BEA-Freibetrag):
      https://www.gesetze-im-internet.de/estg/__32.html
    - BKGG § 6 Abs. 2 (Kindergeld monthly amount):
      https://www.gesetze-im-internet.de/bkgg_1996/
    - § 32a Abs. 1 / Abs. 5 EStG (income tariff used for the
      counterfactual): https://www.gesetze-im-internet.de/estg/__32a.html
    """
    return (
        # DE25-CHILDREN-CREDITS — § 31 EStG Günstigerprüfung. Reads the
        # per-child aggregates produced by Pipeline 1 (DERIVE-DE25-CHILDREN)
        # plus the as-modeled ordinary zvE / income tax / filing posture
        # from the executed ordinary sub-graph. Emits the chosen relief
        # value plus the comparison metadata. The final-settlement stage
        # consumes ``de.children.applied_relief_eur`` and
        # ``de.children.guenstigerpruefung_choice``; renderer touch-points
        # do not consume these values directly (they read the projected
        # ``germany-model-results.json`` block instead).
        # https://www.gesetze-im-internet.de/estg/__31.html
        # https://www.gesetze-im-internet.de/estg/__32.html
        LawStage(
            stage_id="DE25-CHILDREN-CREDITS",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 31 EStG",
                "§ 32 Abs. 6 EStG",
                "§ 32a Abs. 1 EStG",
                "§ 32a Abs. 5 EStG",
                "BKGG § 6 Abs. 2",
            ),
            authority_urls=(ESTG_31_URL, ESTG_32_URL, ESTG_32A_URL, BKGG_URL),
            input_fact_keys=(
                # Pipeline 1 derived aggregates (read from derived-facts.json).
                "de.derived.children_present",
                "de.derived.children_count",
                "de.derived.kinderfreibetrag_total_eur",
                "de.derived.kindergeld_received_total_eur",
                # Pipeline 2 ordinary outputs threaded in by the executor.
                "de.ordinary.taxable_income_eur",
                "de.ordinary.income_tax_eur",
                "de.ordinary.filing_posture",
            ),
            rounding_policy=(
                "Counterfactual tariff computed via the same § 32a Abs. 1 / "
                "Abs. 5 EStG floor_euro path used by DE25-08; the relief "
                "delta is q2 cent precision."
            ),
            law_order_note=(
                "Children Günstigerprüfung runs after DE25-08 produces the "
                "as-modeled ordinary income tax, and before DE25-22 "
                "applies the § 31 Satz 4 EStG netting."
            ),
            legal_formula=(
                "tariff_at_zve = (filing_posture == married_joint) "
                "? german_income_tax_split_2025(zvE) "
                ": german_income_tax_single_2025(zvE); "
                "tariff_at_zve_minus_kinderfreibetrag = "
                "tariff(max(0, zvE - kinderfreibetrag_total_eur)); "
                "kinderfreibetrag_tax_saving_eur = "
                "tariff_at_zve - tariff_at_zve_minus_kinderfreibetrag; "
                "if kinderfreibetrag_tax_saving_eur > "
                "kindergeld_received_total_eur "
                "(per § 31 EStG Satz 1 Günstigerprüfung): "
                "guenstigerpruefung_choice = 'kinderfreibetrag', "
                "applied_relief_eur = kinderfreibetrag_tax_saving_eur; "
                "else: guenstigerpruefung_choice = 'kindergeld', "
                "applied_relief_eur = 0.00 "
                "(per § 31 EStG Satz 4: Kindergeld retained, "
                "no Freibetrag deduction)."
            ),
            narrative_templates={
                "de": "DE25-CHILDREN-CREDITS",
                "en": "DE25-CHILDREN-CREDITS",
            },
            outputs=(
                # The chosen relief value (positive when Kinderfreibetrag
                # wins, zero when Kindergeld wins). DIAGNOSTIC_CROSS_CHECK
                # because no form line consumes it directly — DE25-22
                # consumes it as an input fact. The audit graph still
                # carries the fingerprint via the StageResult.
                OutputDeclaration(
                    key="de.children.applied_relief_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.RECONCILIATION_INVARIANT}
                    ),
                ),
                OutputDeclaration(
                    key="de.children.guenstigerpruefung_choice",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}
                    ),
                ),
                # Surfaced totals for projection into
                # ``germany-model-results.json``. The renderer reads these
                # via the JSON projection path. C-audit
                # (FORM-MAPPING-FOLLOWUP, 2026-05-04) anchors the
                # household Kinderfreibetrag + BEA total to Anlage Kind
                # Zeilen 6-15 via FormLineRef so the renderer's
                # ``legal_value_entry("Anlage Kind Zeilen 6-15", …)``
                # write transits the I3 bidirectional contract.
                OutputDeclaration(
                    key="de.children.kinderfreibetrag_total_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Kind",
                            line="6-15",
                            url=ESTG_32_URL,
                        ),
                    ),
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
                OutputDeclaration(
                    key="de.children.kindergeld_total_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
                OutputDeclaration(
                    key="de.children.kinderfreibetrag_tax_saving_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.INTERMEDIATE_MATH}
                    ),
                ),
                OutputDeclaration(
                    key="de.children.qualifying_children_count",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
            ),
        ),
        # DE25-CHILDREN-DISABILITY-PAUSCHBETRAG (Gap 2) — § 33b Abs. 5
        # EStG transferral. Sibling stage to DE25-CHILDREN-CREDITS in
        # the same children sub-graph. Re-emits the per-child Pauschbetrag
        # transferral total computed by Pipeline 1's
        # DERIVE-DE25-CHILDREN, gated on the profile election. The total
        # itself is consumed by the ordinary stage
        # DE25-BEHINDERUNG-PAUSCHBETRAG (which adds it to the parents'
        # household total via the same Pipeline 1 derived fact); this
        # Pipeline 2 stage exists so the children sub-graph carries an
        # auditable StageResult fingerprint for the same value, and so
        # ``compute_germany_children_assessment_2025`` can surface the
        # transferred amount alongside the §-31-Günstigerprüfung outputs.
        # Two stages produce the same number — Pipeline 1 for the
        # ordinary graph to consume, Pipeline 2 for audit + form
        # rendering surface.
        # Authority:
        #   § 33b Abs. 3 EStG (Pauschbetrag schedule)
        #   § 33b Abs. 5 EStG (transferral to parents)
        # https://www.gesetze-im-internet.de/estg/__33b.html
        LawStage(
            stage_id="DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 33b Abs. 3 EStG",
                "§ 33b Abs. 5 EStG",
            ),
            authority_urls=(ESTG_33B_URL,),
            input_fact_keys=(
                # Pipeline 1 derived total (same key the ordinary stage
                # DE25-BEHINDERUNG-PAUSCHBETRAG reads).
                "de.derived.children_disability_pauschbetrag_total_eur",
                "de.derived.children_present",
                # Election surfaced as a derived fact so this stage's
                # input_fact_keys list carries the audit context for the
                # § 33b Abs. 5 EStG gate without re-reading the profile.
                "de.derived.children_disability_pauschbetrag_transfer_election",
            ),
            rounding_policy=(
                "§ 33b Abs. 3 EStG schedule is fixed-cent EUR; "
                "the transferred total is q2-quantized."
            ),
            law_order_note=(
                "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG is the audit + "
                "form-rendering surface for the § 33b Abs. 5 EStG "
                "transferred Pauschbetrag. It re-emits the Pipeline 1 "
                "derived total. The same value flows into "
                "DE25-BEHINDERUNG-PAUSCHBETRAG (ordinary graph) via the "
                "same de.derived.* key so the parents' assessment "
                "ordering (DE25-07 zvE → DE25-08 tariff) is unchanged. "
                "Two stages produce the same scalar — by construction, "
                "since both read the aggregator output. The form line "
                "(Anlage Kind 2025 Zeile 65) is bound here so the "
                "renderer's read into the children sub-graph output is "
                "the audit anchor for the per-child Pauschbetrag amount."
            ),
            legal_formula=(
                "transferred = sum(per-child Pauschbetrag(gdb, hilflos)) "
                "when election=true and children_present, else 0 "
                "(per § 33b Abs. 5 Satz 1 EStG forfeit branch); the "
                "value is written to Anlage Kind 2025 Zeile 65 "
                "(per-child Pauschbetrag amount, BMF Steuerformular)"
            ),
            narrative_templates={
                "de": "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
                "en": "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
            },
            outputs=(
                # Anlage Kind 2025 Zeilen 64-66 carry "Übertragung des
                # Pauschbetrags für Kinder mit Behinderung":
                #   Zeile 64: attestation/qualifying conditions
                #   Zeile 65: certificate data + per-child Pauschbetrag
                #             EUR amount (the legally-effective transferral)
                #   Zeile 66: optional anderweitige prozentuale Aufteilung
                #             override (§ 33b Abs. 5 Satz 3 EStG joint
                #             election; default 50/50 if Zeile 66 blank)
                # The transferred EUR amount lands on Zeile 65; the split
                # ratio between Zeilen 64-66 is the procedural Anlage Kind
                # context. Source: Helfer in Steuersachen 2.9.0 Zeilen
                # 64-66 (2025); BMF Steuerformular per
                # https://www.formulare-bfinv.de/ form id 034025_25.
                # F-DE-VERIFIED-AGAINST-BMF-2025: 2026-05-02
                # https://www.gesetze-im-internet.de/estg/__33b.html
                OutputDeclaration(
                    key="de.children.disability_pauschbetrag_transferred_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.INTERMEDIATE_MATH}
                    ),
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage Kind",
                            line="65",
                            url=ESTG_33B_URL,
                        ),
                    ),
                ),
            ),
        ),
    )


def germany_final_law_stages_2025() -> tuple[LawStage, ...]:
    """Final-refund stages that consume both ordinary and capital outputs.

    DE25-22-FINAL-REFUND is the headline § 36 Abs. 2 EStG refund:
    ordinary refund net of the post-treaty capital tax, plus the domestic
    capital-withholding credit. The computation used to live in
    ``tax_pipeline/pipelines/y2025/germany_model.py:317-335`` as
    script-level Decimal arithmetic on rule-output values, which invariant
    I5 flagged as legal math escaping the audit graph and invariant I2
    flagged because the resulting ``final_target_refund_eur`` had no
    ``StageResult.output_fingerprint``. WS-4B of
    ``docs/invariant-migration-plan.md`` promotes the computation into
    this stage so the headline number is fingerprinted and cited.

    Wave 11A (children): DE25-22 also consumes the § 31 EStG
    Familienleistungsausgleich children outputs and applies the chosen
    relief per § 31 Satz 4 EStG. When the Kinderfreibetrag path wins
    (tariff differential > Kindergeld received) the tariff differential
    is subtracted from total income tax AND the Kindergeld is added back
    as an advance-payment offset (Hinzurechnung) per § 31 Satz 4 EStG.
    When Kindergeld wins, total tax is unchanged (Kindergeld retained
    outside the assessment).

    Authority:
    - § 36 Abs. 2 EStG (Anrechnung der Steuer / Erstattungsbetrag) — the
      controlling refund rule.
      https://www.gesetze-im-internet.de/estg/__36.html
    - § 31 Satz 4 EStG (Familienleistungsausgleich Hinzurechnung):
      https://www.gesetze-im-internet.de/estg/__31.html
    - § 32d Abs. 1 EStG — the capital tax component being netted into
      the final refund.
      https://www.gesetze-im-internet.de/estg/__32d.html
    - InvStG § 20 — the Teilfreistellung-aware capital tax that the
      § 32d(1) component already incorporates.
      https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    return (
        # DE25-22-FINAL-REFUND — § 36 Abs. 2 EStG headline refund.
        # The Hauptvordruck Erstattung line is the form-bound output;
        # the two intermediate values (refund_before_treaty,
        # chosen_refund_before_domestic_certificate) are
        # INTERMEDIATE_MATH waypoints because they participate in the
        # § 36 Abs. 2 calculation but are not on a separate form line.
        # https://www.gesetze-im-internet.de/estg/__36.html
        LawStage(
            stage_id="DE25-22-FINAL-REFUND",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 36 Abs. 2 EStG",
                "§ 31 Satz 4 EStG",
                "§ 32d Abs. 1 EStG",
                "InvStG § 20",
            ),
            authority_urls=(ESTG_36_URL, ESTG_31_URL, ESTG_32D_URL, INVSTG_20_URL),
            input_fact_keys=(
                "de.final.ordinary_refund_before_capital_eur",
                "de.final.capital_tax_with_teilfreistellung_before_treaty_eur",
                "de.final.capital_tax_with_teilfreistellung_after_treaty_eur",
                "de.final.domestic_capital_withholding_credit_eur",
                # Wave 11A — § 31 Satz 4 EStG Familienleistungsausgleich
                # netting. When the children sub-graph picks
                # Kinderfreibetrag, the tariff differential reduces tax
                # and the Kindergeld total is hinzugerechnet (added back
                # as advance payment). When it picks Kindergeld, both
                # values are zero / "kindergeld" and final tax is
                # unchanged. Reading the keys here keeps the children
                # effect inside the audit graph and out of DE25-07 zvE
                # / DE25-08 tariff.
                "de.children.applied_relief_eur",
                "de.children.guenstigerpruefung_choice",
                "de.children.kindergeld_total_eur",
            ),
            rounding_policy="Final refund kept at cent precision; § 36 Abs. 2 EStG netting follows the capital and ordinary stages' rounding.",
            law_order_note="Final refund netting per § 36 Abs. 2 EStG follows the § 32d Abs. 1 capital tax and the DBA-USA Art. 23 / § 32d Abs. 5 treaty step. § 31 Satz 4 EStG Familienleistungsausgleich routing is applied here, after the children sub-graph picks Kinderfreibetrag vs. Kindergeld.",
            legal_formula=(
                "if guenstigerpruefung_choice == 'kinderfreibetrag': "
                "ordinary_refund_after_children_eur = "
                "ordinary_refund_before_capital_eur "
                "+ applied_relief_eur "
                "- kindergeld_total_eur "
                "(per § 31 Satz 4 EStG: tariff differential reduces tax, "
                "Kindergeld hinzugerechnet als Vorauszahlung); "
                "else: ordinary_refund_after_children_eur = "
                "ordinary_refund_before_capital_eur "
                "(Kindergeld retained outside the assessment); "
                "de.final.refund_before_treaty_eur = "
                "ordinary_refund_after_children_eur "
                "- capital_tax_with_teilfreistellung_before_treaty_eur; "
                "de.final.chosen_refund_before_domestic_certificate_eur = "
                "ordinary_refund_after_children_eur "
                "- capital_tax_with_teilfreistellung_after_treaty_eur; "
                "de.final.target_refund_eur = "
                "chosen_refund_before_domestic_certificate_eur "
                "+ domestic_capital_withholding_credit_eur "
                "(per § 36 Abs. 2 EStG)"
            ),
            narrative_templates={
                "de": "DE25-22-FINAL-REFUND",
                "en": "DE25-22-FINAL-REFUND",
            },
            outputs=(
                # Headline refund — § 36 Abs. 2 EStG Erstattungsbetrag.
                # The Hauptvordruck "Estimation" entry consumes this
                # value via the FormEntry path (forms/germany.py reads
                # ``results["refunds"]["final_target_refund_eur"]``),
                # NOT via ``_required_form_line``. The German renderer's
                # _required_form_line consumers are CSV-row reads on
                # Anlage KAP / KAP-INV / Anlage N; the Hauptvordruck
                # FormEntry path is JSON-keyed. Per invariant I3
                # (renderer↔OutputDeclaration bidirectional contract),
                # an OutputDeclaration form_line_refs entry that no
                # _required_form_line consumes is an orphan; classify
                # the value as RECONCILIATION_INVARIANT so DE25-22
                # mirrors DE25-21-FINAL-CAPITAL-TAX which carries the
                # same pattern (the § 32d-final number is read by the
                # FormEntry path on Anlage KAP, not by
                # _required_form_line).
                # Authority: § 36 Abs. 2 EStG.
                # https://www.gesetze-im-internet.de/estg/__36.html
                OutputDeclaration(
                    key="de.final.target_refund_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.RECONCILIATION_INVARIANT}
                    ),
                ),
                # Intermediate: refund net of pre-treaty capital tax.
                # Used as audit cross-check between the with- vs.
                # without-treaty paths; not on its own form line.
                OutputDeclaration(
                    key="de.final.refund_before_treaty_eur",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Intermediate: refund net of post-treaty capital tax,
                # before the domestic certificate credit. Same role.
                OutputDeclaration(
                    key="de.final.chosen_refund_before_domestic_certificate_eur",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # § 31 Satz 4 EStG: ordinary refund after the
                # Familienleistungsausgleich routing (before capital
                # netting). Captured as INTERMEDIATE_MATH so the audit
                # graph shows the routing leg explicitly even though no
                # form line consumes it directly.
                # https://www.gesetze-im-internet.de/estg/__31.html
                OutputDeclaration(
                    key="de.final.ordinary_refund_after_children_eur",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
    )


def germany_kap_projection_law_stages_2025() -> tuple[LawStage, ...]:
    """Anlage KAP / KAP-INV form-line projection stages.

    DE25-FORM-KAP-PROJECTION promotes the Anlage KAP / KAP-INV form-line
    arithmetic out of ``tax_pipeline/pipelines/y2025/germany_projections.py``
    (specifically the ``kap_line_19 = ordinary + stock_pos - stock_neg +
    option_pos - option_neg`` computation at line 113, plus the per-line
    bucket roll-ups feeding KAP Zeilen 20/21/23/24/41 and KAP-INV Zeilen
    4/8/14/26) into a ``LawRule.calculate`` body. Promoting the
    arithmetic into a stage brings every rendered EUR amount inside the
    audit graph: the executed ``StageResult`` carries fingerprints for
    each form-line output, and ``OutputDeclaration.form_line_refs``
    declares the bidirectional contract with the renderer's
    ``_required_form_line`` reads.

    WS-4C of ``docs/invariant-migration-plan.md`` replaces the
    script-level Decimal arithmetic flagged by invariants I2 (no
    fingerprint) and I5 (legal math outside the rule graph).

    Authority:
    - § 20 Abs. 1 / Abs. 2 EStG fixes the capital-income classification
      feeding Anlage KAP Zeilen 19-24.
      https://www.gesetze-im-internet.de/estg/__20.html
    - § 32d Abs. 1 EStG governs the flat capital-tax surface that
      Anlage KAP collects on Zeile 41 (foreign tax).
      https://www.gesetze-im-internet.de/estg/__32d.html
    - InvStG § 20 governs the fund-related Teilfreistellung and
      fund-type taxonomy feeding Anlage KAP-INV Zeilen 4 / 8 / 14 / 26.
      https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    return (
        # DE25-FORM-KAP-PROJECTION — Anlage KAP / KAP-INV form-line
        # projection. Inputs are the per-fact tuples (sale facts, income
        # facts) plus the fund classification and the 1099 foreign-tax
        # input. The rule emits per-Zeile EUR scalars carrying
        # FormLineRef bindings the renderer's _required_form_line consumer
        # reads against the rendered CSV rows.
        # Authority: § 20 Abs. 1 / Abs. 2 EStG; § 32d Abs. 1 EStG;
        # InvStG § 20.
        # https://www.gesetze-im-internet.de/estg/__20.html
        # https://www.gesetze-im-internet.de/estg/__32d.html
        # https://www.gesetze-im-internet.de/invstg_2018/__20.html
        LawStage(
            stage_id="DE25-FORM-KAP-PROJECTION",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 20 Abs. 1 EStG",
                "§ 20 Abs. 2 EStG",
                "§ 32d Abs. 1 EStG",
                "InvStG § 20",
            ),
            authority_urls=(ESTG_20_URL, ESTG_32D_URL, INVSTG_20_URL),
            input_fact_keys=(
                "de.kap.foreign_tax_1099_eur",
                "de.capital.sale_facts",
                "de.capital.income_facts",
                "de.capital.fund_classification",
                "de.capital.dher_stock_gain",
                # InvStG § 19 Vorabpauschale (laufender Ertrag, post-§ 20
                # Teilfreistellung) lands on Anlage KAP-INV Zeilen 9-13.
                # The amount is computed inside DE25-13F-VORABPAUSCHALE
                # and threaded into this projection so the renderer
                # consumes a fingerprinted Zeile value, not a hard-zero.
                # https://www.gesetze-im-internet.de/invstg_2018/__19.html
                "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur",
            ),
            rounding_policy=(
                "Each Zeile output is q2-quantized at cent precision. "
                "Sale-fact and income-fact amounts arrive q2-quantized "
                "from the loaders; the per-Zeile sums stay at cent "
                "precision through the projection."
            ),
            law_order_note=(
                "The Anlage KAP form-line projection runs after the "
                "DE25-13/14/15 § 20 EStG bucket assembly so the "
                "per-fact amounts are already classified into stock / "
                "fund_like / option / income buckets. The renderer "
                "reads the projected Zeile values directly."
            ),
            # BMF-VERIFIED 2026-05-13 against BMF 16.05.2025
            # Steuerbescheinigung-Schreiben (URL in legal_formula).
            legal_formula=(
                "ordinary = sum(income_facts where bucket != fund_like and kind != foreign_tax); "
                "stock_pos / stock_neg = sign-split sum(sale_facts where bucket == stock) "
                "(with dher_stock_gain folded into the matching sign bucket per § 19a EStG); "
                "option_pos / option_neg = sign-split sum(sale_facts where bucket == option); "
                "de.kap.line_19_eur = ordinary + stock_pos - stock_neg + option_pos - option_neg "
                "(per § 20 Abs. 1 / Abs. 2 EStG net non-fund foreign capital income on the "
                "surviving Anlage KAP Person 1 Zeile 19; post-JStG-2024 the option_pos / option_neg "
                "components fold into that sum without surfacing on their own per-bucket form line); "
                # BMF-VERIFIED 2026-05-13 against BMF 16.05.2025 Steuerbescheinigung-Schreiben.
                "de.kap.line_20_eur = stock_pos; "
                "de.kap.line_23_eur = stock_neg; "
                "de.kap.line_41_eur = foreign_tax_1099_eur (Schwab 1099 EUR converted, "
                "before § 32d Abs. 5 per-Posten cap); "
                "Anlage KAP-INV Zeilen 4 / 8 / 14 / 26 split by InvStG § 20 "
                "Aktienfonds / sonstige Investmentfonds taxonomy. "
                "JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5 und 6 EStG "
                "without replacement; former 2024 Anlage KAP per-bucket Zeilen for "
                "Termingeschäfte positives, Termingeschäfte losses, and Uneinbringlichkeit "
                "are removed. Authority: BMF 16.05.2025 Steuerbescheinigung-Schreiben."
            ),
            narrative_templates={
                "de": "DE25-FORM-KAP-PROJECTION",
                "en": "DE25-FORM-KAP-PROJECTION",
            },
            outputs=(
                # Anlage KAP - Person 1 Zeile 19: net non-fund foreign
                # capital income (ordinary + signed stock/option).
                # § 20 Abs. 1 / Abs. 2 EStG.
                OutputDeclaration(
                    key="de.kap.line_19_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="19",
                            url=ESTG_20_URL,
                        ),
                    ),
                ),
                # Anlage KAP - Person 1 Zeile 20: gross stock-sale gains.
                OutputDeclaration(
                    key="de.kap.line_20_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="20",
                            url=ESTG_20_URL,
                        ),
                    ),
                ),
                # Anlage KAP - Person 1 Zeile 23: stock losses.
                # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6
                # Sätze 5 und 6 EStG; the former 2024 per-bucket
                # OutputDeclarations for de.kap.line_21_eur
                # (Termingeschäfte positives) and de.kap.line_24_eur
                # (Termingeschäfte losses) are removed. option_pos /
                # option_neg still net into de.kap.line_19_eur. BMF
                # 16.05.2025 Steuerbescheinigung-Schreiben confirms.
                OutputDeclaration(
                    key="de.kap.line_23_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="23",
                            url=ESTG_20_URL,
                        ),
                    ),
                ),
                # Anlage KAP - Person 1 Zeile 41: 1099 foreign tax (EUR).
                # § 32d Abs. 5 EStG enforces per-Posten cap downstream;
                # this Zeile carries the gross 1099 amount as filed.
                OutputDeclaration(
                    key="de.kap.line_41_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP - Person 1",
                            line="41",
                            url=ESTG_32D_URL,
                        ),
                    ),
                ),
                # Anlage KAP-INV Zeilen 4 / 8 / 14 / 26 — fund splits.
                # InvStG § 20 fund taxonomy:
                #  - Zeile 4: Aktienfonds distributions/income.
                #  - Zeile 8: sonstige Investmentfonds distributions.
                #  - Zeile 14: Aktienfonds sale gains/losses.
                #  - Zeile 26: sonstige Investmentfonds sale gains/losses.
                OutputDeclaration(
                    key="de.kap_inv.line_4_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="4",
                            url=INVSTG_20_URL,
                        ),
                    ),
                ),
                OutputDeclaration(
                    key="de.kap_inv.line_8_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="8",
                            url=INVSTG_20_URL,
                        ),
                    ),
                ),
                # Anlage KAP-INV Zeilen 9-13: InvStG § 19 Vorabpauschale
                # (deemed-distribution amount, post-§ 20 Teilfreistellung).
                # The amount comes from DE25-13F-VORABPAUSCHALE; this
                # projection re-emits it under a `de.kap_inv.*` key so the
                # renderer's _required_form_line consumer reads it the
                # same way it reads the other KAP-INV Zeilen.
                # https://www.gesetze-im-internet.de/invstg_2018/__19.html
                OutputDeclaration(
                    key="de.kap_inv.line_9_13_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="9-13",
                            url=INVSTG_19_URL,
                        ),
                    ),
                ),
                OutputDeclaration(
                    key="de.kap_inv.line_14_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="14",
                            url=INVSTG_20_URL,
                        ),
                    ),
                ),
                OutputDeclaration(
                    key="de.kap_inv.line_26_eur",
                    form_line_refs=(
                        FormLineRef(
                            form="Anlage KAP-INV",
                            line="26",
                            url=INVSTG_20_URL,
                        ),
                    ),
                ),
                # Per-fund summary feeds the KAP-INV per-fund supporting
                # CSV (germany-kap-inv-fund-summary.csv). Classified
                # PER_POSTEN_AGGREGATION because the value is a per-symbol
                # roll-up rather than a single Zeile.
                OutputDeclaration(
                    key="de.kap_inv.fund_rows",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.PER_POSTEN_AGGREGATION}
                    ),
                ),
            ),
        ),
    )


def germany_guenstigerpruefung_law_stages_2025() -> tuple[LawStage, ...]:
    """Audit-only Günstigerprüfung shadow-comparison stage (F-DE-2).

    § 32d Abs. 6 EStG (Antragsveranlagung) lets the taxpayer elect to apply
    the ordinary § 32a tariff to capital income if it produces a lower
    total tax than the § 32d Abs. 1 flat 25%. Today the engine fails
    closed when ``capital_guenstigerpruefung_requested=1`` (see
    ``ensure_capital_guenstigerpruefung_position_2025`` in
    ``tax_pipeline/pipelines/y2025/germany_model.py``) — correct posture
    for an unimplemented branch, but it leaves taxpayers in low brackets
    with no signal that the election would help them.

    This stage runs unconditionally and computes both paths:

    1. Status-quo (§ 32d Abs. 1 path): the actual modeled total tax from
       the ordinary + capital + final rule graphs that have already
       executed upstream.
    2. Shadow (§ 32a path): the ordinary § 32a tariff applied to
       (zvE_ordinary + capital_income_after_teilfreistellung), plus the
       unchanged ordinary solidarity surcharge component, less foreign
       tax credits that would carry through under § 32d Abs. 5 EStG (the
       § 32a path does not lose them).

    The output is two audit-only values, not form-bound:

    - ``de.audit.guenstigerpruefung_shadow_diff_eur`` — Decimal, status_quo
      total tax minus shadow total tax. Positive ⇒ the election would
      reduce tax; negative ⇒ the election would raise tax.
    - ``de.audit.guenstigerpruefung_election_recommended`` — Decimal-as-flag
      (``D("1")`` if the diff exceeds ``GUENSTIGERPRUEFUNG_MATERIALITY_EUR``
      = €10, else ``D("0")``).

    No form line is written from these outputs (DIAGNOSTIC_CROSS_CHECK).
    The renderer does not consume them; the warning surfaces in
    ``germany-model-results.json`` and ``germany-model-trace.csv`` only.

    Authority:

    - § 32d Abs. 6 EStG (Antragsveranlagung — election to apply § 32a):
      https://www.gesetze-im-internet.de/estg/__32d.html
    - § 32d Abs. 1 EStG (the 25 % flat tax that the election competes
      against): https://www.gesetze-im-internet.de/estg/__32d.html
    - § 32a Abs. 1 EStG (the ordinary tariff applied under the election):
      https://www.gesetze-im-internet.de/estg/__32a.html
    - § 32a Abs. 5 EStG (joint splitting tariff): same URL.
    - § 32d Abs. 5 EStG (foreign-tax credit; carries through under the
      election): https://www.gesetze-im-internet.de/estg/__32d.html
    - BMF-Schreiben Abgeltungsteuer 14.05.2025 (mechanics of the
      Günstigerprüfung): the 2025 BMF Einzelfragen-Schreiben to
      Abgeltungsteuer.

    Materiality: ``GUENSTIGERPRUEFUNG_MATERIALITY_EUR = €10`` was chosen
    because at the cent-precision of the German rule graph any positive
    diff is mathematically real, but a delta below €10 is dominated by
    rounding artifacts (q2 / floor_euro at multiple stages) and is not a
    practically actionable recommendation. €10 also matches the
    granularity at which an ELSTER preview is meaningfully different
    from the modeled result.
    """
    return (
        # DE25-GUENSTIGERPRUEFUNG-SHADOW — § 32d Abs. 6 EStG audit-only
        # comparison. Pure diagnostic: the two outputs do NOT change
        # final.target_refund_eur. Reviewers see whether the taxpayer
        # would benefit from electing the ordinary tariff.
        # https://www.gesetze-im-internet.de/estg/__32d.html
        LawStage(
            stage_id="DE25-GUENSTIGERPRUEFUNG-SHADOW",
            country_or_scope="DE-2025",
            legal_refs=(
                "§ 32d Abs. 6 EStG",
                "§ 32d Abs. 1 EStG",
                "§ 32a Abs. 1 EStG",
                "§ 32a Abs. 5 EStG",
                "§ 32d Abs. 5 EStG",
            ),
            authority_urls=(ESTG_32D_URL, ESTG_32A_URL, BMF_ABGELTUNGSTEUER_URL),
            input_fact_keys=(
                "de.audit.guenstiger.zve_ordinary_eur",
                "de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur",
                "de.audit.guenstiger.status_quo_total_tax_eur",
                "de.audit.guenstiger.foreign_tax_credit_applied_eur",
                "de.audit.guenstiger.filing_posture",
            ),
            rounding_policy="Shadow tariff uses the same § 32a tariff floor_euro path; the diff is q2.",
            law_order_note="Audit-only shadow runs after the § 32d Abs. 1 / Abs. 5 / SolzG capital path so the status-quo total tax is final and comparable.",
            legal_formula=(
                "shadow_zve = zve_ordinary + capital_taxable_after_teilfreistellung; "
                "shadow_ordinary_tax = (filing_posture == married_joint) "
                "? german_income_tax_split_2025(shadow_zve) "
                ": german_income_tax_single_2025(shadow_zve); "
                "shadow_total_tax = max(0, shadow_ordinary_tax - foreign_tax_credit_applied) "
                "  - german_income_tax_(split|single)_2025(zve_ordinary); "
                "// the second term subtracts the ordinary-only tariff already counted "
                "// in status_quo_total_tax so we compare like-for-like; "
                "diff = status_quo_total_tax - shadow_total_tax_delta; "
                "election_recommended = (diff > GUENSTIGERPRUEFUNG_MATERIALITY_EUR) "
                "(per § 32d Abs. 6 EStG)"
            ),
            narrative_templates={
                "de": "DE25-GUENSTIGERPRUEFUNG-SHADOW",
                "en": "DE25-GUENSTIGERPRUEFUNG-SHADOW",
            },
            outputs=(
                # Audit-only: no form-line ref. The German renderer
                # never reads these values. Classified
                # DIAGNOSTIC_CROSS_CHECK because the stage is purely a
                # cross-check between the § 32d Abs. 1 path the engine
                # actually uses and the § 32d Abs. 6 / § 32a path the
                # engine has not implemented.
                OutputDeclaration(
                    key="de.audit.guenstigerpruefung_shadow_diff_eur",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}
                    ),
                ),
                OutputDeclaration(
                    key="de.audit.guenstigerpruefung_election_recommended",
                    audit_waypoints=frozenset(
                        {AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}
                    ),
                ),
            ),
        ),
    )


def germany_law_stages_2025() -> tuple[LawStage, ...]:
    return (
        germany_ordinary_law_stages_2025()
        + germany_capital_law_stages_2025()
        + germany_children_law_stages_2025()
        + germany_final_law_stages_2025()
        + germany_kap_projection_law_stages_2025()
        + germany_guenstigerpruefung_law_stages_2025()
    )


__all__ = [
    "germany_capital_law_stages_2025",
    "germany_children_law_stages_2025",
    "germany_final_law_stages_2025",
    "germany_guenstigerpruefung_law_stages_2025",
    "germany_kap_projection_law_stages_2025",
    "germany_law_stages_2025",
    "germany_ordinary_law_stages_2025",
]
