from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Any

from tax_pipeline._law_data import LAW_DATA as _LAW_DATA, LAW_TABLES as _LAW_TABLES

D = Decimal

# Law-spec references:
# - tax_pipeline/law_spec/germany/2025/split_tariff.md
# - tax_pipeline/law_spec/germany/2025/ordinary_soli.md
# - tax_pipeline/law_spec/germany/2025/other_income_22nr3.md
# - tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md
# - tax_pipeline/law_spec/germany/2025/payments_and_crediting.md

ESTG_2_URL = "https://www.gesetze-im-internet.de/estg/__2.html"
ESTG_3_URL = "https://www.gesetze-im-internet.de/estg/__3.html"
ESTG_4_5_6C_URL = "https://www.gesetze-im-internet.de/estg/__4.html"
# § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer (annual €1,260 Pauschale, or
# actual costs when the home office is the Mittelpunkt der gesamten
# betrieblichen und beruflichen Betätigung). Distinct from the
# § 4 Abs. 5 Satz 1 Nr. 6c Tagespauschale modeled by
# ``home_office_tagespauschale_2025``; § 4 Abs. 5 Satz 1 Nr. 6c Satz 3
# EStG forbids combining the two for the same period.
# https://www.gesetze-im-internet.de/estg/__4.html
ESTG_4_5_6B_URL = "https://www.gesetze-im-internet.de/estg/__4.html"
ESTG_9_URL = "https://www.gesetze-im-internet.de/estg/__9.html"
ESTG_9A_URL = "https://www.gesetze-im-internet.de/estg/__9a.html"
ESTG_10_URL = "https://www.gesetze-im-internet.de/estg/__10.html"
# § 10b Abs. 1 EStG Spendenabzug — charitable donations as Sonderausgaben
# capped at 20 % of Gesamtbetrag der Einkünfte. Out-of-scope here:
# § 10b Abs. 1 Satz 1 Nr. 2 EStG entrepreneur 4 ‰ alternative cap;
# § 10b Abs. 1 Sätze 9-10 EStG carryforwards (Großspendenrest).
# https://www.gesetze-im-internet.de/estg/__10b.html
ESTG_10B_URL = "https://www.gesetze-im-internet.de/estg/__10b.html"
ESTG_10C_URL = "https://www.gesetze-im-internet.de/estg/__10c.html"
ESTG_18_URL = "https://www.gesetze-im-internet.de/estg/__18.html"
ESTG_19_URL = "https://www.gesetze-im-internet.de/estg/__19.html"
ESTG_20_URL = "https://www.gesetze-im-internet.de/estg/__20.html"
ESTG_22_URL = "https://www.gesetze-im-internet.de/estg/__22.html"
ESTG_23_URL = "https://www.gesetze-im-internet.de/estg/__23.html"
# § 24a EStG Altersentlastungsbetrag (age-relief allowance) — sliding scale by
# the calendar year the taxpayer first turned 64 (Vollendung des 64.
# Lebensjahres BEFORE the start of the assessment year).
# https://www.gesetze-im-internet.de/estg/__24a.html
ESTG_24A_URL = "https://www.gesetze-im-internet.de/estg/__24a.html"
ESTG_25_URL = "https://www.gesetze-im-internet.de/estg/__25.html"
ESTG_26_URL = "https://www.gesetze-im-internet.de/estg/__26.html"
ESTG_26B_URL = "https://www.gesetze-im-internet.de/estg/__26b.html"
ESTG_32A_URL = "https://www.gesetze-im-internet.de/estg/__32a.html"
ESTG_32D_URL = "https://www.gesetze-im-internet.de/estg/__32d.html"
# § 33 EStG außergewöhnliche Belastungen (extraordinary burdens), with
# § 33 Abs. 3 EStG zumutbare Belastung (reasonable burden) sliding scale.
# BFH VI R 75/14 (19.01.2017) confirms slab progression on the brackets.
# https://www.gesetze-im-internet.de/estg/__33.html
ESTG_33_URL = "https://www.gesetze-im-internet.de/estg/__33.html"
# § 33a EStG Außergewöhnliche Belastungen in besonderen Fällen — support
# payments to legally entitled persons (estranged or divorced spouses,
# parents, children without Kindergeld, etc.).
# https://www.gesetze-im-internet.de/estg/__33a.html
ESTG_33A_URL = "https://www.gesetze-im-internet.de/estg/__33a.html"
# § 33b EStG Pauschbeträge wegen Behinderung — disability flat allowances
# by Grad der Behinderung (GdB), plus the special amount for hilflose /
# blinde Menschen.
# https://www.gesetze-im-internet.de/estg/__33b.html
ESTG_33B_URL = "https://www.gesetze-im-internet.de/estg/__33b.html"
# § 31 EStG Familienleistungsausgleich — Finanzamt automatically picks the
# better of (a) Kindergeld retained vs. (b) Kinderfreibetrag deduction
# (Günstigerprüfung). When the Freibetrag deduction's tax savings exceed
# Kindergeld received, the Freibetrag is applied and Kindergeld is added
# back to assessed tax-due (treated as advance payment).
# https://www.gesetze-im-internet.de/estg/__31.html
ESTG_31_URL = "https://www.gesetze-im-internet.de/estg/__31.html"
# § 32 EStG (insbes. Abs. 6) — Kinderfreibetrag + BEA-Freibetrag
# (Betreuung, Erziehung, Ausbildung). Combined €9,600 per child for
# single parent / MFJ, halved (€4,800) per spouse in MFS.
# https://www.gesetze-im-internet.de/estg/__32.html
ESTG_32_URL = "https://www.gesetze-im-internet.de/estg/__32.html"
# Bundeskindergeldgesetz (BKGG) — Kindergeld for VZ 2025:
# €255/month per child (raised from €250 by the
# Steuerfortentwicklungsgesetz 2024, effective 01.01.2025), statutory
# uniform rate (no longer escalating with child count).
# https://www.gesetze-im-internet.de/bkgg_1996/
BKGG_URL = "https://www.gesetze-im-internet.de/bkgg_1996/"
ESTG_36_URL = "https://www.gesetze-im-internet.de/estg/__36.html"
SOLZG_3_URL = "https://www.gesetze-im-internet.de/solzg_1995/__3.html"
SOLZG_4_URL = "https://www.gesetze-im-internet.de/solzg_1995/__4.html"
SOLZG_5_URL = "https://www.gesetze-im-internet.de/solzg_1995/__5.html"
INVSTG_2_URL = "https://www.gesetze-im-internet.de/invstg_2018/__2.html"
INVSTG_16_URL = "https://www.gesetze-im-internet.de/invstg_2018/__16.html"
INVSTG_18_URL = "https://www.gesetze-im-internet.de/invstg_2018/__18.html"
INVSTG_19_URL = "https://www.gesetze-im-internet.de/invstg_2018/__19.html"
INVSTG_20_URL = "https://www.gesetze-im-internet.de/invstg_2018/__20.html"
INVSTG_21_URL = "https://www.gesetze-im-internet.de/invstg_2018/__21.html"
# BMF-Schreiben 16.01.2025 - IV C 1 - S 1980-1/19/10005:008 — published the
# 2025 Basiszinssatz (2.53 %) used by InvStG § 18 to compute the
# Vorabpauschale Basisertrag. Source: BMF Investmentfonds page (annual
# Basiszinssatz announcements).
# https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuergesetz/2025-01-16-basiszins-zur-berechnung-der-vorabpauschale.pdf?__blob=publicationFile&v=2
BMF_BASISZINS_2025_URL = "https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuergesetz/2025-01-16-basiszins-zur-berechnung-der-vorabpauschale.pdf?__blob=publicationFile&v=2"
TAX_ADVICE_BMF_URL = "https://ao.bundesfinanzministerium.de/esth/2025/B-Anhaenge/Anhang-16/XIII/inhalt.html"
BMF_ABGELTUNGSTEUER_URL = "https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=6"
BMF_PAP_2025_URL = "https://www.bundesfinanzministerium.de/Datenportal/Daten/frei-nutzbare-produkte/Anwendungen/Programmablaufplan-2025/Programmablaufplan-2025.html"
BMF_USA_PAGE_URL = "https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html?gtp=249348_list%253D2"
# § 19a EStG (employee equity grant deferral) — Einkommensteuer-Hinweise (EStH) 2025
ESTH_PARAGRAF_19A_URL = "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/II-Einkommen-2-24b/8-Die-einzelnen-Einkunftsarten-13-24b/d-Nichtselbstaendige-Arbeit-19-19a/Paragraf-19a/inhalt.html"
# R 34c EStR — foreign-tax credit / per-country rule guidance
ESTR_R_34C_URL = "https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/V-Steuerermaessigungen-34c-35c/1-Steuerermaessigung-bei-ausl-Eink-34c-34d/Paragraf-34c/r-34c-1-2.html"
# BMF-Schreiben 06.03.2025 — Einzelfragen zu Kryptowerten (private Veräußerungsgeschäfte)
BMF_KRYPTOWERTE_2025_URL = "https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2025-03-06-einzelfragen-kryptowerte-bmf-schreiben.pdf?__blob=publicationFile&v=2"
# ELSTER help page for the 2025 Anlage AUS / Anlage N entries used by Germany returns
ELSTER_ANLAGE_AUS_2025_URL = "https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025"
# Top-level ELSTER portal entry — the URL the per-jurisdiction filing
# guide tells the user to file the assembled return through. The
# ``helpGlobal`` page is the entry point for ELSTER help (referenced
# generically by the filing guide).
# https://www.elster.de/
ELSTER_PORTAL_URL = "https://www.elster.de/"
ELSTER_HELP_GLOBAL_URL = "https://www.elster.de/eportal/helpGlobal"
# § 34c EStG — Steueranrechnung bei beschränkter / unbeschränkter Steuerpflicht
# (per-country foreign-tax credit). Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03)
# pins this URL for the Anlage AUS FormLineRef declarations on DE25-18.
ESTG_34C_URL = "https://www.gesetze-im-internet.de/estg/__34c.html"

WORKER_ALLOWANCE_PER_PERSON_EUR = _LAW_DATA["WORKER_ALLOWANCE_PER_PERSON_EUR"]
HOME_OFFICE_DAILY_RATE_EUR = _LAW_DATA["HOME_OFFICE_DAILY_RATE_EUR"]
HOME_OFFICE_MAX_EUR = _LAW_DATA["HOME_OFFICE_MAX_EUR"]
OTHER_VORSORGE_CAP_EMPLOYEE_EUR = _LAW_DATA["OTHER_VORSORGE_CAP_EMPLOYEE_EUR"]
OTHER_VORSORGE_CAP_GENERAL_EUR = _LAW_DATA["OTHER_VORSORGE_CAP_GENERAL_EUR"]
SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR = _LAW_DATA["SONDERAUSGABEN_PAUSCHBETRAG_SINGLE_EUR"]
SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR = _LAW_DATA["SONDERAUSGABEN_PAUSCHBETRAG_JOINT_EUR"]
# § 10 Abs. 3 Satz 1 EStG: the Höchstbetrag for retirement Vorsorgeaufwendungen
# equals the maximum (employer + employee) annual contribution to the
# knappschaftliche Rentenversicherung for the assessment year. The BMAS
# Sozialversicherungs-Rechengrößenverordnung 2025 abolished the West/Ost
# split — for 2025 there is a single bundeseinheitliche BBG of €118,800
# in the knappschaftliche RV. The legacy "_RV_WEST_" suffix on the
# constant name is retained for fingerprint stability under invariants
# I1 / I2; the value is correct for the unified 2025 BBG.
# 2025: BBG knappschaftliche RV (unified) = €118,800 × Beitragssatz
# 24.7 % = €29,343.60, rounded by BMF to €29,344 in the assessment
# guidance.
# https://www.gesetze-im-internet.de/estg/__10.html
# https://www.bmas.de/DE/Service/Gesetze-und-Gesetzesvorhaben/sozialversicherungs-rechengroessen-2025.html
RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR = _LAW_DATA["RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR"]
RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR = _LAW_DATA["RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR"]
RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025 = _LAW_DATA["RETIREMENT_SPECIAL_EXPENSE_CAP_KNAPPSCHAFT_BEITRAGSSATZ_2025"]
SOLI_SINGLE_THRESHOLD_EUR = _LAW_DATA["SOLI_SINGLE_THRESHOLD_EUR"]
SOLI_JOINT_THRESHOLD_EUR = _LAW_DATA["SOLI_JOINT_THRESHOLD_EUR"]
# § 4 Satz 1 SolzG 1995: 5,5% solidarity-surcharge rate on the assessment base.
# https://www.gesetze-im-internet.de/solzg_1995/__4.html
SOLI_RATE = _LAW_DATA["SOLI_RATE"]
SOLI_MITIGATION_RATE = _LAW_DATA["SOLI_MITIGATION_RATE"]
# § 32d Abs. 1 Satz 1 EStG: 25% flat capital-income tax (Abgeltungsteuer).
# https://www.gesetze-im-internet.de/estg/__32d.html
CAPITAL_TAX_RATE_2025 = _LAW_DATA["CAPITAL_TAX_RATE_2025"]
# F-DE-2 (audit-only): § 32d Abs. 6 EStG Günstigerprüfung shadow comparison
# threshold. The shadow stage DE25-GUENSTIGERPRUEFUNG-SHADOW recommends the
# election only when the diff between § 32d Abs. 1 path and § 32a path
# exceeds this materiality. €10 is the project threshold:
# - It is well above q2/floor_euro rounding artifacts (worst case ~€2 across
#   the multi-stage path), so a positive diff above €10 is signal not noise.
# - It matches the granularity at which an ELSTER preview is meaningfully
#   different from the modeled result.
# - It is conservative: at €10 the shadow is silent on micro-bracket
#   crossings that would not change the user's filing decision.
# This is a project-internal materiality, not a statutory amount, so it
# does not pass through ``assert_germany_csv_statutory_constants_2025``.
# Authority context: § 32d Abs. 6 EStG (Antragsveranlagung):
# https://www.gesetze-im-internet.de/estg/__32d.html
GUENSTIGERPRUEFUNG_MATERIALITY_EUR = _LAW_DATA["GUENSTIGERPRUEFUNG_MATERIALITY_EUR"]
# § 20 Abs. 9 Satz 1 EStG: Sparer-Pauschbetrag — €1,000 per single filer,
# €2,000 for jointly assessed spouses (§ 20 Abs. 9 Satz 2 EStG).
# https://www.gesetze-im-internet.de/estg/__20.html
SAVER_ALLOWANCE_JOINT_2025_EUR = _LAW_DATA["SAVER_ALLOWANCE_JOINT_2025_EUR"]
SAVER_ALLOWANCE_SINGLE_2025_EUR = _LAW_DATA["SAVER_ALLOWANCE_SINGLE_2025_EUR"]
# § 22 Nr. 3 Satz 2 EStG: €256 Freigrenze for sonstige Einkünfte from
# Leistungen, including modeled staking-style receipts.
# https://www.gesetze-im-internet.de/estg/__22.html
OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR = _LAW_DATA["OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR"]
STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE = _LAW_DATA["STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE"]
# § 24a EStG Altersentlastungsbetrag — sliding scale keyed by the calendar
# year the taxpayer first turned 64 (i.e., the year *after* the assessment
# year in which they turned 64 for those born during the year). Once
# established, that birth-year cohort's (rate, cap) is fixed for life
# under § 24a Satz 5 EStG. The 2024-anchored rate of 11.2 % / €532 carries
# forward to 2025 because the legislative phase-out reached the 0 % terminal
# value-pair only at the 2058 cohort; the schedule below is the official
# Anlage to § 24a EStG with the 2005-2024 rate-pairs that may still apply
# in 2025 to taxpayers whose 64th birthday fell in those earlier years.
# Source schedule: § 24a Satz 5 EStG Anlage.
# https://www.gesetze-im-internet.de/estg/__24a.html
# Sourced from the W2.A / T1.2 shadow TOML
# (law/germany/year_2025/estg/p24a.toml). The frozen LAW_TABLES view
# is wrapped in a plain dict so the existing module-level type
# signature (``dict[int, tuple[Decimal, Decimal]]``) is preserved.
# F-C6: the 2023 cap is €665 (NOT €684) — the Wachstumschancengesetz
# (28.03.2024, BGBl. I 2024 Nr. 108) re-keyed the per-cohort rate-step
# from 0.4 to 0.2 percentage points starting cohort 2023.
ALTERSENTLASTUNGSBETRAG_2025_TABLE: dict[int, tuple[Decimal, Decimal]] = dict(
    _LAW_TABLES["ALTERSENTLASTUNGSBETRAG_2025_TABLE"]
)
ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS = 64
# § 33 Abs. 3 EStG zumutbare Belastung sliding scale, applied progressively
# (slab method per BFH VI R 75/14, 19.01.2017): each income tier's rate
# applies only to the income band within that tier.
# https://www.gesetze-im-internet.de/estg/__33.html
# Family categories per § 33 Abs. 3 Satz 1 EStG:
# - "single_no_children": single (or married-separate) without children,
# - "joint_or_few_children": married/joint without children OR single with
#   1-2 dependent children,
# - "many_children": three or more dependent children regardless of posture.
# Sourced from the W2.A / T1.2 shadow TOML
# (law/germany/year_2025/estg/p33.toml) — one ``bracket_list`` table
# carries both thresholds and per-category rates; the legacy split-tuple
# / dict shapes are reconstructed below so call sites keep their imports.
_ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS = _LAW_TABLES[
    "ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR"
]
_ZUMUTBARE_BELASTUNG_2025_CATEGORIES = (
    "single_no_children",
    "joint_or_few_children",
    "many_children",
)
ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR: tuple[Decimal, Decimal] = tuple(
    row["upper_threshold"]
    for row in _ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS
    if row["upper_threshold"].is_finite()
)
ZUMUTBARE_BELASTUNG_2025_RATES: dict[str, tuple[Decimal, Decimal, Decimal]] = {
    category: tuple(
        row[category] for row in _ZUMUTBARE_BELASTUNG_2025_BRACKET_ROWS
    )
    for category in _ZUMUTBARE_BELASTUNG_2025_CATEGORIES
}
# § 33a Abs. 1 Satz 1 EStG: maximum deductible Unterhaltsleistungen tracks
# the Grundfreibetrag (= TARIFF_2025_GROUND_ALLOWANCE_EUR for 2025).
# § 33a Abs. 1 Satz 5 EStG: recipient's own income/maintenance above
# €624 ("Eigenbezüge") reduces the cap euro for euro.
# https://www.gesetze-im-internet.de/estg/__33a.html
UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR = _LAW_DATA["UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR"]
UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS = frozenset({
    "estranged_spouse",
    "divorced_spouse",
    "parent",
    "child_no_kindergeld",
})
# § 33b Abs. 3 EStG Pauschbeträge by Grad der Behinderung (GdB). The 2021
# Behinderten-Pauschbetragsgesetz (BGBl. I 2020 S. 2770) doubled the
# rates effective 2021; the 2025 statute carries those rates unchanged.
# https://www.gesetze-im-internet.de/estg/__33b.html
# Sourced from the W2.A / T1.2 shadow TOML
# (law/germany/year_2025/estg/p33b.toml). Algebraic invariant: the
# Pauschbetrag schedule is monotonically increasing in GdB; the
# import-time assertion below catches a half-rolled re-keying that
# would otherwise let a non-monotone Pauschbetrag escape into a return.
BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR: dict[int, Decimal] = dict(
    _LAW_TABLES["BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR"]
)
_BEHINDERUNG_GDB_KEYS = sorted(BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR)
for _prev, _next in zip(_BEHINDERUNG_GDB_KEYS, _BEHINDERUNG_GDB_KEYS[1:]):
    assert (
        BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[_next]
        > BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[_prev]
    ), (
        f"§ 33b Abs. 3 Satz 2 EStG: Pauschbetrag(GdB {_next}) must "
        f"strictly exceed Pauschbetrag(GdB {_prev})."
    )
BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR = _LAW_DATA["BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR"]
# § 32 Abs. 6 EStG — Kinderfreibetrag (€6,672 total per child) plus
# BEA-Freibetrag (€2,928 total per child) for the assessment year 2025.
# Each parent claims half by default (€3,336 + €1,464 = €4,800 per
# spouse in married_separate); single parents and married_joint claim
# the full €9,600 combined deduction. Authority:
# § 32 Abs. 6 Satz 1 EStG (Kinderfreibetrag €3,336 / Elternteil),
# § 32 Abs. 6 Satz 2 EStG (BEA €1,464 / Elternteil),
# § 32 Abs. 6 Satz 3 EStG (full transfer to one parent / single parent).
# Effective from BGBl. I 2024 (Steuerfortentwicklungsgesetz).
# https://www.gesetze-im-internet.de/estg/__32.html
KINDERFREIBETRAG_2025_EUR = _LAW_DATA["KINDERFREIBETRAG_2025_EUR"]
BEA_FREIBETRAG_2025_EUR = _LAW_DATA["BEA_FREIBETRAG_2025_EUR"]
COMBINED_KINDERFREIBETRAG_2025_EUR = _LAW_DATA["COMBINED_KINDERFREIBETRAG_2025_EUR"]
# § 32 Abs. 6 Satz 1 EStG — per-parent halves. These are the legally
# controlling Halbteilung amounts: each parent claims €3,336 +
# €1,464 = €4,800; in married_joint / single the engine consolidates
# them into the COMBINED €9,600 figure used by
# ``kinderfreibetrag_for_child_2025``. Wired here so the per-parent /
# combined relationship is auditable from a single edit point and the
# constants are not orphaned in the F1 shadow tree.
# Authority: § 32 Abs. 6 Satz 1 EStG (Kinderfreibetrag),
# § 32 Abs. 6 Satz 2 EStG (BEA-Freibetrag); per-parent values
# established by the Steuerfortentwicklungsgesetz 2024 (BGBl. 2024 I).
# https://www.gesetze-im-internet.de/estg/__32.html
KINDERFREIBETRAG_PER_PARENT_2025_EUR = _LAW_DATA["KINDERFREIBETRAG_PER_PARENT_2025_EUR"]
BEA_FREIBETRAG_PER_PARENT_2025_EUR = _LAW_DATA["BEA_FREIBETRAG_PER_PARENT_2025_EUR"]
# Algebraic invariant under § 32 Abs. 6 Satz 1 EStG: the combined
# Kinderfreibetrag (€6,672) is exactly two parents' shares, and the
# combined BEA-Freibetrag (€2,928) is exactly two parents' shares.
# Likewise the joint €9,600 deduction is the sum of all four halves.
# Asserting at import time catches a half-roll-forward (e.g. the
# per-parent KFB is updated in the TOML but the combined sum is not).
assert (
    D("2") * KINDERFREIBETRAG_PER_PARENT_2025_EUR == KINDERFREIBETRAG_2025_EUR
), (
    "§ 32 Abs. 6 Satz 1 EStG: combined Kinderfreibetrag must equal "
    "2 × per-parent share."
)
assert (
    D("2") * BEA_FREIBETRAG_PER_PARENT_2025_EUR == BEA_FREIBETRAG_2025_EUR
), (
    "§ 32 Abs. 6 Satz 2 EStG: combined BEA-Freibetrag must equal "
    "2 × per-parent share."
)
assert (
    D("2") * (KINDERFREIBETRAG_PER_PARENT_2025_EUR + BEA_FREIBETRAG_PER_PARENT_2025_EUR)
    == COMBINED_KINDERFREIBETRAG_2025_EUR
), (
    "§ 32 Abs. 6 EStG: combined €9,600 deduction must equal 2 × "
    "(KFB per parent + BEA per parent)."
)
# Bundeskindergeldgesetz (BKGG) § 6 Abs. 2: €250/month from 01.01.2023
# (Inflationsausgleichsgesetz 2022) raised to €255/month from 01.01.2025
# by the Steuerfortentwicklungsgesetz 2024 (BGBl. 2024 I). Uniform per
# child — no longer increasing with child count. Annual = €3,060 for a
# child eligible all twelve months.
# https://www.gesetze-im-internet.de/bkgg_1996/__6.html
# Per New-1 (2026-05-10 platform-flexibility review) the monthly /
# annual amounts live in law/germany/year_2025/bkgg/p6.toml — the
# F1 shadow data file. _LAW_DATA is the single edit point; updating
# the value requires re-signing the TOML via
# ``python -m law.audit sign law/germany/year_2025/bkgg/p6.toml``.
KINDERGELD_2025_MONTHLY_EUR = _LAW_DATA["KINDERGELD_2025_MONTHLY_EUR"]
KINDERGELD_2025_ANNUAL_EUR = _LAW_DATA["KINDERGELD_2025_ANNUAL_EUR"]
KINDERGELD_2025_RECIPIENT_VALUES = frozenset(
    {"taxpayer", "spouse", "other_parent", "none"}
)
KINDERGELD_2025_THIS_FILER_RECIPIENTS = frozenset({"taxpayer", "spouse"})
# § 10b Abs. 1 Satz 1 Nr. 1 EStG: Spendenabzug capped at 20 % of
# Gesamtbetrag der Einkünfte; the alternative 4 ‰ "Umsatz + Lohnsumme"
# entrepreneur cap (§ 10b Abs. 1 Satz 1 Nr. 2 EStG) is out of scope.
# https://www.gesetze-im-internet.de/estg/__10b.html
SPENDENABZUG_2025_GDE_FRACTION_CAP = _LAW_DATA["SPENDENABZUG_2025_GDE_FRACTION_CAP"]
# § 4 Abs. 5 Satz 1 Nr. 6b Satz 4 EStG: Jahrespauschale (annual lump sum)
# for an Arbeitszimmer when the home office is NOT the Mittelpunkt der
# gesamten betrieblichen und beruflichen Betätigung. Mutually exclusive
# with § 4 Abs. 5 Satz 1 Nr. 6c Tagespauschale (HOME_OFFICE_MAX_EUR)
# under § 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG.
# https://www.gesetze-im-internet.de/estg/__4.html
ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR = D("1260.00")
# § 20 InvStG 2018 Teilfreistellung schedule by fund type — sourced
# from the W2.A / T1.2 shadow TOML (law/germany/year_2025/invstg/p20.toml)
# so the working-tree rule graph and the citation surface share a single
# edit point. The frozen LAW_TABLES view is wrapped in a plain dict so
# the existing module-level type signature (``dict[str, Decimal]``) is
# preserved. The English aliases (equity / mixed / property /
# foreign_property / other) live alongside the German labels in the
# TOML entries.
# Authority: § 20 Abs. 1 Nr. 1, Abs. 1 Nr. 2, Abs. 3 Nr. 1, Abs. 3 Nr. 2
# InvStG 2018.
# https://www.gesetze-im-internet.de/invstg_2018/__20.html
FUND_TEILFREISTELLUNG_RATES_2025: dict[str, Decimal] = dict(
    _LAW_TABLES["FUND_TEILFREISTELLUNG_RATES_2025"]
)
# InvStG § 18 Abs. 1: Basisertrag = NAV_start × 0.7 × Basiszinssatz × (months_held / 12).
# The 0.7 factor is the statutory shortfall (70 % of the risk-free rate) that
# § 18 InvStG applies to the prior-year NAV. The Basiszinssatz for 2025 is
# 2.53 %, published by the BMF on 16 January 2025 (Az. IV C 1 -
# S 1980-1/19/10005:008) per BMF Investmentfonds page.
# https://www.gesetze-im-internet.de/invstg_2018/__18.html
# https://www.gesetze-im-internet.de/invstg_2018/__19.html
VORABPAUSCHALE_BASISERTRAG_FACTOR = _LAW_DATA["VORABPAUSCHALE_BASISERTRAG_FACTOR"]
BASISZINS_2025 = _LAW_DATA["BASISZINS_2025"]
GERMANY_CAPITAL_SALE_BUCKETS_2025 = {"stock", "fund_like", "option"}
GERMANY_CAPITAL_INCOME_BUCKETS_2025 = {"stock", "fund_like", "option", "cash"}
GERMANY_CAPITAL_INCOME_KINDS_2025 = {"dividend", "interest", "substitute_payment", "foreign_tax"}
GERMANY_US_TREATY_DIVIDEND_CLASSES_2025 = {
    "portfolio_dividend",
    "equity_fund_dividend",
    "non_equity_fund_dividend",
}
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE as _DBA_ART_10_2_B_RATE,
)

GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE = _DBA_ART_10_2_B_RATE

NON_RULE_PUBLIC_HELPERS_2025 = {
    "q2",
    "floor_cent",
    "ceil_euro",
    "floor_euro",
    # F-DE-1: loader-side validation that the workspace de-tax-constants.csv
    # rows agree with the centralized 2025 statutory constants. Not a rule
    # calculation — it runs once per pipeline invocation at the inputs boundary.
    "assert_germany_csv_statutory_constants_2025",
    # § 31 EStG / § 32 Abs. 6 EStG / BKGG — children aggregation helpers.
    # The per-child Kinderfreibetrag and Kindergeld functions plus the
    # aggregate are called from Pipeline 1's DERIVE-DE25-CHILDREN stage
    # (a derivation, not a Pipeline 2 legal stage) and from Pipeline 2's
    # DE25-CHILDREN-CREDITS. The aggregator's
    # role is to produce typed Pipeline 1 derived facts; the legal
    # § 31 EStG Günstigerprüfung lives in the DE25-CHILDREN-CREDITS rule body.
    "kinderfreibetrag_for_child_2025",
    "kindergeld_for_child_2025",
    "aggregate_germany_children_facts_2025",
    # § 33b Abs. 3 / Abs. 5 EStG — disability Pauschbetrag schedule and
    # per-child transferral amount (Gap 2). The lookup
    # ``disability_pauschbetrag_2025`` is a canonical schedule reader;
    # the per-child transferral helper is consumed by the children
    # aggregator that already lives on this list. Both are non-rule
    # helpers because the legal interpretation lives in the registered
    # ``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` /
    # ``DE25-BEHINDERUNG-PAUSCHBETRAG`` calculate bodies.
    "disability_pauschbetrag_2025",
    "child_disability_pauschbetrag_for_transferral_2025",
}

REGISTERED_LAW_FUNCTIONS_2025 = {
    "euer_net_profit_2025": ("DE25-EUER",),
    "german_income_tax_single_2025": ("DE25-08-INCOME-TAX-TARIFF",),
    "german_income_tax_split_2025": ("DE25-08-INCOME-TAX-TARIFF",),
    "german_soli_assessment_2025": ("DE25-09-ORDINARY-SOLI", "DE25-19-CAPITAL-SOLI"),
    "home_office_tagespauschale_2025": ("DE25-02-WERBUNGSKOSTEN",),
    "retirement_special_expense_deduction_2025": ("DE25-05-RETIREMENT-SA",),
    "joint_retirement_special_expense_deductions_2025": ("DE25-05-RETIREMENT-SA",),
    "deductible_basic_health_contribution_2025": ("DE25-06-HEALTH-VORSORGE-SA",),
    "other_vorsorge_allowed_employee_2025": ("DE25-06-HEALTH-VORSORGE-SA",),
    "joint_other_vorsorge_allowed_employee_2025": ("DE25-06-HEALTH-VORSORGE-SA",),
    "other_income_22nr3_taxable_2025": ("DE25-04-OTHER-22NR3",),
    "altersentlastungsbetrag_2025": ("DE25-ALTERSENTLASTUNGSBETRAG",),
    "zumutbare_belastung_2025": ("DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",),
    "aussergewoehnliche_belastungen_deductible_2025": ("DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",),
    "unterhaltsleistungen_deductible_2025": ("DE25-UNTERHALTSLEISTUNGEN",),
    "behinderung_pauschbetrag_2025": ("DE25-BEHINDERUNG-PAUSCHBETRAG",),
    "spendenabzug_2025": ("DE25-SPENDENABZUG",),
    "arbeitszimmer_deductible_2025": ("DE25-ARBEITSZIMMER",),
    "foreign_tax_credit_32d5_cap_2025": ("DE25-18-SECTION-32D5-FTC",),
    "capital_tax_after_foreign_tax_credit_2025": (
        "DE25-17-SECTION-32D1-GROSS-TAX",
        "DE25-18-SECTION-32D5-FTC",
        "DE25-19-CAPITAL-SOLI",
    ),
    "treaty_relieved_capital_tax_2025": ("DE25-20-TREATY-CHECK",),
    "normalized_fund_type_2025": ("DE25-14-FUND-TEILFREISTELLUNG",),
    "fund_type_for_symbol_2025": ("DE25-14-FUND-TEILFREISTELLUNG",),
    "saver_allowance_for_spouse_20_9_2025": ("DE25-16-SECTION-20-9-SAVER",),
    "compute_germany_capital_assessment_2025": (
        "DE25-13-CAPITAL-RAW-BUCKETS",
        "DE25-13F-VORABPAUSCHALE",
        "DE25-14-FUND-TEILFREISTELLUNG",
        "DE25-15-SECTION-20-6-NETTING",
        "DE25-16-SECTION-20-9-SAVER",
        "DE25-17-SECTION-32D1-GROSS-TAX",
        "DE25-18-SECTION-32D5-FTC",
        "DE25-19-CAPITAL-SOLI",
        "DE25-20-TREATY-CHECK",
        "DE25-21-FINAL-CAPITAL-TAX",
    ),
    "compute_germany_children_assessment_2025": (
        "DE25-CHILDREN-CREDITS",
        "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
    ),
    "compute_joint_ordinary_assessment_2025": (
        "DE25-00-FILING-POSTURE-GATE",
        "DE25-01-WAGE-INCOME",
        "DE25-02-WERBUNGSKOSTEN",
        "DE25-03-NET-EMPLOYMENT",
        "DE25-04-OTHER-22NR3",
        "DE25-ALTERSENTLASTUNGSBETRAG",
        "DE25-ARBEITSZIMMER",
        "DE25-05-RETIREMENT-SA",
        "DE25-06-HEALTH-VORSORGE-SA",
        "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
        "DE25-SPENDENABZUG",
        "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
        "DE25-UNTERHALTSLEISTUNGEN",
        "DE25-BEHINDERUNG-PAUSCHBETRAG",
        "DE25-07-TAXABLE-INCOME",
        "DE25-08-INCOME-TAX-TARIFF",
        "DE25-09-ORDINARY-SOLI",
        "DE25-10-ORDINARY-CREDITS",
    ),
}

# Official 2025 tariff constants from the dated BMF Programmablaufplan 2025 and
# § 32a Abs. 1 EStG; live statute URLs can roll forward to later-year constants.
TARIFF_2025_GROUND_ALLOWANCE_EUR = _LAW_DATA["TARIFF_2025_GROUND_ALLOWANCE_EUR"]
TARIFF_2025_PROGRESS_ZONE_1_END_EUR = _LAW_DATA["TARIFF_2025_PROGRESS_ZONE_1_END_EUR"]
TARIFF_2025_PROGRESS_ZONE_2_END_EUR = _LAW_DATA["TARIFF_2025_PROGRESS_ZONE_2_END_EUR"]
# § 32a Abs. 1 Nr. 5 EStG: the 45 % Reichensteuer applies "ab €277.826".
# This constant is the inclusive UPPER BOUND of the 42 % zone (one euro
# below the start of the 45 % zone) — the rule body uses ``x <=
# TARIFF_2025_TOP_RATE_START_EUR`` so the comparison stays correct, but
# the name is a legacy artifact: the value is *not* the first euro of the
# 45 % bracket. A future schema bump can rename to
# ``TARIFF_2025_FORTYTWO_ZONE_END_EUR`` once we accept the fingerprint
# churn under invariants I1 / I2.
TARIFF_2025_TOP_RATE_START_EUR = _LAW_DATA["TARIFF_2025_TOP_RATE_START_EUR"]


def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def floor_cent(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_FLOOR)


def ceil_euro(value: Decimal) -> Decimal:
    return value.quantize(D("1"), rounding=ROUND_CEILING)


def floor_euro(value: Decimal) -> Decimal:
    return value.quantize(D("1"), rounding=ROUND_FLOOR)


def _require_non_negative_int(value: int, *, label: str) -> int:
    if value < 0:
        raise ValueError(f"{label} must be non-negative.")
    return value


def _require_non_negative_decimal(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00"):
        raise ValueError(f"{label} must be non-negative.")
    return value


def _require_unit_interval(value: Decimal, *, label: str) -> Decimal:
    if value < D("0.00") or value > D("1.00"):
        raise ValueError(f"{label} must be between 0 and 1 inclusive.")
    return value


# ---------------------------------------------------------------------------
# § 4 Abs. 3 EStG — Einnahmenüberschussrechnung (EÜR); § 18 EStG income
#
# Phase 1 (freelancer support, FREELANCER-SUPPORT-SPEC.md /
# FREELANCER-DE-EUER-SLICE-SPEC.md). The cash-basis profit of a
# self-employed person not required to keep books is the excess of
# operating receipts over operating expenses ("… können als Gewinn den
# Überschuss der Betriebseinnahmen über die Betriebsausgaben ansetzen",
# § 4 Abs. 3 Satz 1 EStG; verified 2026-06-10 against gesetze-im-internet).
# For selbständige Arbeit (§ 18 EStG) this Gewinn is the Einkünfte
# (§ 2 Abs. 2 Satz 1 Nr. 1 EStG) that join the Summe der Einkünfte. Pure
# arithmetic — no statutory constant. The net may be negative (a Verlust
# that offsets other income under § 2 Abs. 3 EStG); it is not floored.
# https://www.gesetze-im-internet.de/estg/__4.html
# https://www.gesetze-im-internet.de/estg/__18.html
# ---------------------------------------------------------------------------
ESTG_4_ABS3_URL = "https://www.gesetze-im-internet.de/estg/__4.html"

EUER_LEGAL_BASIS = (
    "§ 4 Abs. 3 EStG — Einnahmenüberschussrechnung: Gewinn = Überschuss der "
    "Betriebseinnahmen über die Betriebsausgaben (Zufluss-Abfluss-Prinzip); "
    "§ 18 EStG selbständige Arbeit"
)


@dataclass(frozen=True)
class GermanyEuerInputs2025:
    """§ 4 Abs. 3 EStG Einnahmenüberschussrechnung inputs (cash-basis).

    ``operating_receipts_eur`` (Betriebseinnahmen) and
    ``operating_expenses_eur`` (Betriebsausgaben) are the aggregated, already
    cash-recognized totals for the trade/profession. Both are non-negative;
    the netting may still yield a loss.
    """

    operating_receipts_eur: Decimal
    operating_expenses_eur: Decimal


@dataclass(frozen=True)
class GermanyEuerResult2025:
    """§ 4 Abs. 3 EStG net profit (Gewinn / Verlust) breakdown.

    ``net_profit_eur`` may be negative (a § 4 Abs. 3 Verlust). ``legal_basis``
    names the controlling authority for this result so a single EÜR result
    cross-audits against the law in isolation.
    """

    operating_receipts_eur: Decimal
    operating_expenses_eur: Decimal
    net_profit_eur: Decimal
    legal_basis: str = EUER_LEGAL_BASIS


@dataclass(frozen=True)
class BusinessIncomeInputs2025:
    """Declared self-employment business-income inputs for one household.

    ``self_employment_class`` is the cited § 18/§ 15 position:
    ``"freiberuflich_18"`` (selbständige Arbeit, supported) or
    ``"gewerbe_15"`` (Gewerbebetrieb — out of scope this slice; the loader
    fails closed because Gewerbesteuer is not yet modeled).
    """

    operating_receipts_eur: Decimal
    operating_expenses_eur: Decimal
    self_employment_class: str = "freiberuflich_18"


def euer_net_profit_2025(*, inputs: GermanyEuerInputs2025) -> GermanyEuerResult2025:
    """Compute the § 4 Abs. 3 EStG EÜR net profit (cash-basis).

    Pure function of its declared inputs. Receipts and expenses must each be
    non-negative; the net (receipts − expenses) may be negative — a Verlust
    that offsets other income under § 2 Abs. 3 EStG, so it is NOT floored at
    zero. Registered to the DE25-EUER stage (REGISTERED_LAW_FUNCTIONS_2025).

    Authority: § 4 Abs. 3 Satz 1 EStG (Überschuss der Betriebseinnahmen über
    die Betriebsausgaben), § 18 EStG (selbständige Arbeit).
    https://www.gesetze-im-internet.de/estg/__4.html
    """
    _require_non_negative_decimal(
        inputs.operating_receipts_eur, label="operating_receipts_eur"
    )
    _require_non_negative_decimal(
        inputs.operating_expenses_eur, label="operating_expenses_eur"
    )
    receipts = q2(inputs.operating_receipts_eur)
    expenses = q2(inputs.operating_expenses_eur)
    return GermanyEuerResult2025(
        operating_receipts_eur=receipts,
        operating_expenses_eur=expenses,
        net_profit_eur=q2(receipts - expenses),
        legal_basis=EUER_LEGAL_BASIS,
    )


# Map of CSV row keys (in years/<workspace>/normalized/reference-data/de-tax-constants.csv)
# to the canonical statutory law-module constants they must equal. The CSV row
# stays as a redundant declaration so workspaces that already shipped the file
# do not break, but any drift fails closed at load time per invariant I1.
_CSV_STATUTORY_CONSTANT_BINDINGS_2025: tuple[tuple[str, Decimal, str, str], ...] = (
    (
        "capital_tax_rate",
        CAPITAL_TAX_RATE_2025,
        "§ 32d Abs. 1 Satz 1 EStG",
        ESTG_32D_URL,
    ),
    (
        "saver_allowance_eur",
        SAVER_ALLOWANCE_JOINT_2025_EUR,
        "§ 20 Abs. 9 Satz 1 und 2 EStG",
        ESTG_20_URL,
    ),
    (
        "soli_rate",
        SOLI_RATE,
        "§ 4 Satz 1 SolzG 1995",
        SOLZG_4_URL,
    ),
    (
        "other_income_22nr3_freigrenze_eur",
        OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
        "§ 22 Nr. 3 Satz 2 EStG",
        ESTG_22_URL,
    ),
)


def assert_germany_csv_statutory_constants_2025(values: dict[str, Decimal]) -> None:
    """Fail closed if the workspace de-tax-constants.csv drifts from the
    centralized 2025 statutory constants in this module.

    Invariant I1 keeps statutory rates and named thresholds in the law
    modules. The Germany workspace CSV historically carried these four
    rows so existing year workspaces do not need to be edited; it now
    serves as a redundant declaration that must equal the law-module
    constant. Any other value fails closed before the rule graph runs,
    so a workspace edit cannot silently override Bundesrecht.

    Authority for the four bindings is documented per row in
    ``_CSV_STATUTORY_CONSTANT_BINDINGS_2025``.
    """
    for csv_key, statutory_value, citation, url in _CSV_STATUTORY_CONSTANT_BINDINGS_2025:
        if csv_key not in values:
            continue
        observed = values[csv_key]
        if Decimal(observed) != Decimal(statutory_value):
            raise ValueError(
                f"de-tax-constants.csv {csv_key}={observed} disagrees with the "
                f"centralized 2025 statutory constant {statutory_value} "
                f"({citation}, {url}). Update the workspace CSV row or the law "
                "module under invariant I1 — never let them drift."
            )


@dataclass(frozen=True)
class WageFacts2025:
    owner: str | None
    source_files: tuple[str, ...]
    gross_wage_eur: Decimal
    withheld_wage_tax_eur: Decimal
    withheld_solidarity_surcharge_eur: Decimal
    multiannual_wage_eur: Decimal
    employer_pension_contribution_eur: Decimal
    employee_pension_contribution_eur: Decimal
    employee_health_insurance_eur: Decimal
    employee_nursing_care_insurance_eur: Decimal
    employee_unemployment_insurance_eur: Decimal


@dataclass(frozen=True)
class WorkEquipmentItem2025:
    key: str
    gross_amount_eur: Decimal
    work_use_share: Decimal
    deductible_amount_eur: Decimal


@dataclass(frozen=True)
class PersonOrdinaryInputs2025:
    slot: str
    order_label: str
    display_name: str
    owner: str | None
    wage: WageFacts2025
    work_equipment_items: tuple[WorkEquipmentItem2025, ...]
    home_office_days_without_visit: int
    home_office_days_with_visit: int
    manual_work_equipment_deduction_eur: Decimal
    telecom_deduction_eur: Decimal
    employment_legal_insurance_deduction_eur: Decimal
    cross_border_tax_help_deduction_eur: Decimal
    health_insurance_sick_pay_reduction_rate: Decimal
    other_vorsorge_cap_eur: Decimal = OTHER_VORSORGE_CAP_EMPLOYEE_EUR
    home_office_visit_days_no_other_workplace: bool = False
    # § 24a EStG Altersentlastungsbetrag — birth year drives the lifetime
    # rate/cap (year_turned_64 keys ALTERSENTLASTUNGSBETRAG_2025_TABLE).
    # 0 means "not declared"; the rule then yields 0 EUR for this person.
    # https://www.gesetze-im-internet.de/estg/__24a.html
    birth_year: int = 0
    # § 33b Abs. 3 EStG Pauschbetrag wegen Behinderung. ``gdb`` is the
    # Grad der Behinderung as a multiple of 10 in [20, 100], or 0 if no
    # disability is declared. ``hilflos_or_blind`` triggers the §-33b-
    # Abs.-3 special €7,400 Pauschbetrag instead of the GdB schedule.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    gdb: int = 0
    hilflos_or_blind: bool = False


@dataclass(frozen=True)
class JointOrdinaryInputs2025:
    people: tuple[PersonOrdinaryInputs2025, ...]
    other_income_22nr3_eur: Decimal
    other_income_22nr3_threshold_eur: Decimal
    prepayments_eur: Decimal
    filing_posture: str = ""
    joint_assessment_prerequisites_validated: bool = False
    other_income_22nr3_by_person_eur: tuple[Decimal, ...] = ()
    prepayments_by_person_eur: tuple[Decimal, ...] = ()
    # § 33 EStG außergewöhnliche Belastungen (medical) — joint household
    # total. Subject to § 33 Abs. 3 zumutbare Belastung deduction.
    # https://www.gesetze-im-internet.de/estg/__33.html
    medical_expenses_eur: Decimal = D("0.00")
    # § 33 Abs. 3 EStG zumutbare Belastung family category. One of
    # ``ZUMUTBARE_BELASTUNG_2025_RATES`` keys.
    zumutbare_belastung_family_category: str = "single_no_children"
    # § 33a EStG Unterhaltsleistungen.
    # https://www.gesetze-im-internet.de/estg/__33a.html
    support_payments_eur: Decimal = D("0.00")
    support_recipient_income_eur: Decimal = D("0.00")
    support_recipient_relationship: str = ""
    # § 10b EStG Spendenabzug.
    # https://www.gesetze-im-internet.de/estg/__10b.html
    charitable_donations_eur: Decimal = D("0.00")
    # § 10b Abs. 1 Sätze 9-10 EStG previous-year carryforward
    # (Großspendenrest). Non-zero amounts are not modeled — fail closed.
    charitable_donations_carryforward_eur: Decimal = D("0.00")
    # § 4 Abs. 5 Satz 1 Nr. 6b EStG Arbeitszimmer.
    # https://www.gesetze-im-internet.de/estg/__4.html
    arbeitszimmer_claimed: bool = False
    arbeitszimmer_qualifies_as_mittelpunkt: bool = False
    arbeitszimmer_actual_costs_eur: Decimal = D("0.00")
    # § 18 / § 4 Abs. 3 EStG self-employment income. None = the household
    # has no self-employment (wage earner); the DE25-EUER stage then sees
    # zero receipts/expenses and emits a zero § 18 profit. Populated only
    # when worker_type includes self-employment (loader fail-closes if the
    # business-income facts are missing under an active posture).
    business_income: BusinessIncomeInputs2025 | None = None


@dataclass(frozen=True)
class PersonOrdinaryAssessment2025:
    slot: str
    order_label: str
    display_name: str
    owner: str | None
    wage: WageFacts2025
    work_equipment_items: tuple[WorkEquipmentItem2025, ...]
    manual_work_equipment_deduction_eur: Decimal
    work_equipment_eur: Decimal
    home_office_days_without_visit: int
    home_office_days_with_visit: int
    home_office_deduction_eur: Decimal
    telecom_deduction_eur: Decimal
    employment_legal_insurance_deduction_eur: Decimal
    cross_border_tax_help_deduction_eur: Decimal
    actual_werbungskosten_eur: Decimal
    allowed_werbungskosten_eur: Decimal
    income_after_werbungskosten_eur: Decimal
    retirement_contributions_eur: Decimal
    health_and_nursing_contributions_eur: Decimal
    other_vorsorge_contributions_eur: Decimal
    other_vorsorge_allowed_eur: Decimal
    total_special_expenses_eur: Decimal


@dataclass(frozen=True)
class JointOrdinaryAssessment2025:
    filing_posture: str
    people: tuple[PersonOrdinaryAssessment2025, ...]
    other_income_22nr3_eur: Decimal
    other_income_22nr3_taxable_eur: Decimal
    other_income_22nr3_by_person_taxable_eur: tuple[Decimal, ...]
    sum_income_after_werbungskosten_eur: Decimal
    retirement_contributions_eur: Decimal
    health_and_nursing_contributions_eur: Decimal
    other_vorsorge_contributions_eur: Decimal
    other_vorsorge_allowed_eur: Decimal
    # C3-prereq (FORM-MAPPING-FOLLOWUP, 2026-05-03): the § 10 Abs. 1 Nr. 3
    # + Nr. 3a + Abs. 4 EStG total Vorsorgeaufwendungen, taken from the
    # declared DE25-06-HEALTH-VORSORGE-SA scalar output
    # ``de.ordinary.health_vorsorge_total_eur``. Replaces the
    # projection-side sum at germany_model.py (formerly under a
    # ``# pragma: legal-math-ok`` bypass) so the form-line scalar that
    # lands on Anlage Vorsorgeaufwand Zeilen 11-14 carries the executor's
    # StageResult fingerprint via I11.
    health_vorsorge_total_eur: Decimal
    # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket scalars
    # for Anlage Vorsorgeaufwand. ``health_vorsorge_basic_health_eur`` =
    # § 10 Abs. 1 Nr. 3 EStG (Zeilen 11-14). ``health_vorsorge_other_allowed_eur``
    # = § 10 Abs. 1 Nr. 3a EStG within the § 10 Abs. 4 cap (Zeilen 31 ff.).
    # ``retirement_special_expenses_total_eur`` = § 10 Abs. 1 Nr. 2 / Abs. 3
    # EStG (Zeilen 4-9).
    health_vorsorge_basic_health_eur: Decimal
    health_vorsorge_other_allowed_eur: Decimal
    retirement_special_expenses_total_eur: Decimal
    total_special_expenses_eur: Decimal
    # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket scalars
    # for Anlage Sonderausgaben. ``spendenabzug_deductible_eur`` =
    # § 10b Abs. 1 EStG (Spenden, capped at 20 % GdE).
    # ``unterhaltsleistungen_deductible_eur`` = § 33a Abs. 1 EStG support
    # payments (within Grundfreibetrag cap minus Eigenbezüge reduction).
    # ``sonderausgaben_pauschbetrag_applied_eur`` = § 10c EStG statutory
    # minimum Pauschbetrag (joint amount on married_joint, per-person
    # single amount otherwise).
    spendenabzug_deductible_eur: Decimal
    unterhaltsleistungen_deductible_eur: Decimal
    sonderausgaben_pauschbetrag_applied_eur: Decimal
    joint_taxable_income_eur: Decimal
    joint_income_tax_eur: Decimal
    joint_solidarity_surcharge_eur: Decimal
    withheld_wage_tax_eur: Decimal
    withheld_wage_solidarity_surcharge_eur: Decimal
    prepayments_eur: Decimal
    ordinary_refund_before_capital_eur: Decimal


@dataclass(frozen=True)
class GermanyCapitalSaleFact2025:
    asset_bucket: str
    symbol: str
    gain_eur_matched: Decimal


@dataclass(frozen=True)
class GermanyCapitalIncomeFact2025:
    kind: str
    asset_bucket: str
    symbol: str
    eur_amount: Decimal
    refund_entitlement_eur: Decimal | None = None
    foreign_tax_item_id: str = ""


@dataclass(frozen=True)
class GermanyBankCapitalCertificate2025:
    owner_slot: str
    certificate_id: str
    source_file: str
    kap_line_7_income_eur: Decimal
    kap_line_8_stock_gains_eur: Decimal = D("0.00")
    kap_line_17_saver_allowance_used_eur: Decimal = D("0.00")
    kap_line_37_kest_withheld_eur: Decimal = D("0.00")
    kap_line_38_soli_withheld_eur: Decimal = D("0.00")
    kap_line_40_foreign_tax_credited_eur: Decimal = D("0.00")
    kap_line_41_foreign_tax_not_credited_eur: Decimal = D("0.00")


@dataclass(frozen=True)
class GermanyTreatyDividendItem2025:
    item_id: str
    owner_slot: str
    gross_dividend_eur: Decimal
    german_taxable_dividend_eur: Decimal
    allocated_us_tax_paid_eur: Decimal
    treaty_rate: Decimal = GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE
    dividend_class: str = "portfolio_dividend"


@dataclass(frozen=True)
class GermanyVorabpauschaleInput2025:
    """Per-fund Vorabpauschale (deemed-distribution) raw input.

    InvStG § 18 / § 19 govern the deemed-distribution mechanism that taxes
    accumulating funds annually on a Basisertrag floor even when no actual
    distribution occurred. The per-fund inputs are:

    - ``symbol``  — ticker / ISIN identifier (must match the fund_classification
      taxonomy so the Teilfreistellung rate routes correctly).
    - ``nav_start_eur`` — the NAV at the first valuation date of the calendar
      year (InvStG § 18 Abs. 1 Satz 1: ``Wert des Investmentanteils zu Beginn
      des Kalenderjahres``).
    - ``nav_end_eur`` — the NAV at the last valuation date of the calendar
      year. Used by the InvStG § 16 Abs. 1 Nr. 2 cap: the Vorabpauschale
      cannot exceed the actual market gain ``max(0, NAV_end − NAV_start)``.
    - ``ausschuettung_eur`` — actual distributions paid during the year
      (InvStG § 18 Abs. 1 Satz 3: the Basisertrag is reduced by the year's
      Ausschuettungen before becoming the Vorabpauschale).
    - ``months_held`` — the number of full months the unit was held during
      the calendar year (InvStG § 18 Abs. 2: pro-ration by 1/12 per month).

    Authority:
    - InvStG § 18: https://www.gesetze-im-internet.de/invstg_2018/__18.html
    - InvStG § 19: https://www.gesetze-im-internet.de/invstg_2018/__19.html
    - InvStG § 16: https://www.gesetze-im-internet.de/invstg_2018/__16.html
    """

    symbol: str
    nav_start_eur: Decimal
    nav_end_eur: Decimal
    ausschuettung_eur: Decimal
    months_held: int


@dataclass(frozen=True)
class GermanyUSTreatyDividendPacketItem2025:
    item_id: str
    owner_slot: str
    dividend_class: str
    gross_dividend_eur: Decimal
    german_taxable_dividend_eur: Decimal
    article_10_source_tax_ceiling_eur: Decimal
    germany_precredit_tax_eur: Decimal
    germany_residence_credit_eur: Decimal


@dataclass(frozen=True)
class GermanyCapitalAssessmentInputs2025:
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...]
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...]
    dher_stock_gain_eur: Decimal
    stock_loss_carryforward_2024_eur: Decimal
    saver_allowance_eur: Decimal
    capital_tax_rate: Decimal
    soli_rate: Decimal
    treaty_dividend_credit_eur: Decimal
    fund_classification: dict[str, str]
    bank_certificates: tuple[GermanyBankCapitalCertificate2025, ...] = ()
    treaty_dividend_items: tuple[GermanyTreatyDividendItem2025, ...] = ()
    other_spouse_capital_before_allowance_eur: Decimal | None = None
    # InvStG § 19 Vorabpauschale (deemed-distribution) per-fund inputs.
    # Empty tuple is the supported zero-Vorabpauschale path: workspaces
    # with no accumulating funds in scope keep producing 0.00 EUR and the
    # legal stage DE25-13F-VORABPAUSCHALE emits an empty per-symbol dict.
    vorabpauschale_inputs: tuple[GermanyVorabpauschaleInput2025, ...] = ()


@dataclass(frozen=True)
class Child2025:
    """Per-child raw fact block read from ``config/children.csv``.

    The CSV is the shared schema between the German (this module),
    U.S., and intake adapters; only a subset of columns matters for
    the German Familienleistungsausgleich calculation. Columns not
    used here (``ssn``, ``itin``, ``annual_gross_income_usd``,
    ``months_in_us_household``) are preserved on the dataclass so the
    same ``Child2025`` instance can be threaded into the U.S. side.

    Authority context:
    - § 31 EStG Familienleistungsausgleich
      (https://www.gesetze-im-internet.de/estg/__31.html)
    - § 32 EStG Kinder
      (https://www.gesetze-im-internet.de/estg/__32.html)
    - BKGG (Bundeskindergeldgesetz)
      (https://www.gesetze-im-internet.de/bkgg_1996/)
    """

    child_id: str
    name: str
    date_of_birth: str
    ssn: str
    itin: str
    steuer_id: str
    relationship: str
    months_in_household: int
    months_in_us_household: int
    annual_gross_income_eur: Decimal
    annual_gross_income_usd: Decimal
    kindergeld_received_eur: Decimal
    kindergeld_recipient: str
    # § 33b Abs. 5 EStG entitles parents to transfer a qualifying
    # child's Behinderten-Pauschbetrag to themselves. The intake CSV
    # validates the GdB grade ([0, 100]); the transferral is wired
    # through ``DERIVE-DE25-CHILDREN`` and ``DE25-CHILDREN-DISABILITY-
    # PAUSCHBETRAG`` (Gap 2) when the profile-level election
    # ``elections.germany_disability_pauschbetrag_transfer`` is true.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    disability_gdb: int
    # § 33b Abs. 3 Satz 3 EStG erhöhter Pauschbetrag (€7,400) for
    # ``hilflos`` (Merkzeichen H), ``blind`` (Merkzeichen Bl), or
    # Pflegegrad 4/5 (§ 33b Abs. 6 EStG). Mutually exclusive with the
    # GdB schedule under § 33b Abs. 3 Satz 2 EStG: the special amount
    # supersedes the GdB tier when claimed. Optional column on the
    # intake CSV; defaults to False so existing fixtures keep working.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    disability_helpless_or_blind: bool = False


@dataclass(frozen=True)
class GermanyChildrenFacts2025:
    """Aggregated children facts for the German Familienleistungsausgleich.

    The aggregator materializes per-child eligibility once at the
    Pipeline 1 boundary so the Pipeline 2 legal stage
    ``DE25-CHILDREN-CREDITS`` consumes a
    single typed object. ``children_present`` is ``False`` when the
    workspace ships only the CSV header (zero qualifying rows); the
    legal stage short-circuits to pass-through behaviour in that case
    so demo workspaces without children produce identical numerics.

    Authority:
    - § 31 EStG: https://www.gesetze-im-internet.de/estg/__31.html
    - § 32 Abs. 6 EStG: https://www.gesetze-im-internet.de/estg/__32.html
    - BKGG: https://www.gesetze-im-internet.de/bkgg_1996/
    """

    children: tuple[Child2025, ...]
    children_present: bool
    children_count: int
    kinderfreibetrag_total_eur: Decimal
    kindergeld_received_total_eur: Decimal
    # § 33b Abs. 5 EStG transferral total — sum of per-child §-33b-Abs.-3
    # Pauschbeträge that flow to the parents when the profile election
    # ``elections.germany_disability_pauschbetrag_transfer`` is true. Zero
    # when the election is false, when no qualifying child has
    # ``disability_gdb > 0`` / ``disability_helpless_or_blind`` set, or
    # when ``children_present == False``. The aggregator is the single
    # numeric source for both the Pipeline 1 derivation
    # (``DERIVE-DE25-CHILDREN`` → ``de.derived.children_disability_
    # pauschbetrag_total_eur``) and the Pipeline 2 audit stage
    # (``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` →
    # ``de.children.disability_pauschbetrag_transferred_eur``); both
    # values are guaranteed equal because they read the same aggregator.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    disability_pauschbetrag_total_transferred_eur: Decimal


def kinderfreibetrag_for_child_2025(
    months_in_household: int,
    *,
    filing_posture: str,
) -> Decimal:
    """Per-child Kinderfreibetrag + BEA-Freibetrag (§ 32 Abs. 6 EStG).

    Returns the deduction available against zvE for one qualifying child
    given the months the child was in the household. Partial-year
    proration is by full months (the law treats the child's birth month
    as a full month). MFS halves the per-child amount because the
    Freibetrag is split between parents.

    Authority:
    - § 32 Abs. 6 Satz 1 EStG (€3,336 Kinderfreibetrag per parent → €6,672 combined)
    - § 32 Abs. 6 Satz 2 EStG (€1,464 BEA per parent → €2,928 combined)
    - § 32 Abs. 6 Satz 3 EStG (full transfer to one parent / single parent)
    https://www.gesetze-im-internet.de/estg/__32.html
    """
    if months_in_household < 0 or months_in_household > 12:
        raise ValueError(
            "months_in_household must be in [0, 12] under § 32 Abs. 6 EStG."
        )
    if filing_posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(
            f"Unsupported Germany filing posture for Kinderfreibetrag: {filing_posture}"
        )
    full_amount = COMBINED_KINDERFREIBETRAG_2025_EUR
    if filing_posture == "married_separate":
        # § 32 Abs. 6 Satz 1/2 EStG halves to €4,800 per spouse when
        # parents are jointly entitled but file separately (default
        # split; explicit § 32 Abs. 6 Satz 6 EStG transfer to one parent
        # is not modeled in 2025).
        full_amount = full_amount / D("2")
    proration = D(months_in_household) / D("12")
    return q2(full_amount * proration)


def kindergeld_for_child_2025(
    months_in_household: int,
    kindergeld_recipient: str,
) -> Decimal:
    """Per-child Kindergeld received during the year (BKGG since 2023).

    Only Kindergeld actually paid out to *this* filer (taxpayer or
    spouse) counts for the § 31 EStG Günstigerprüfung; payments to the
    other parent fall outside this filer's claim per § 31 Satz 4 EStG.

    Authority:
    - BKGG (€255/month uniform for VZ 2025, raised from €250 by the
      Steuerfortentwicklungsgesetz 2024 effective 01.01.2025):
      https://www.gesetze-im-internet.de/bkgg_1996/
    - § 31 Satz 4 EStG (Kindergeld counted only to the entitled parent):
      https://www.gesetze-im-internet.de/estg/__31.html
    """
    if months_in_household < 0 or months_in_household > 12:
        raise ValueError(
            "months_in_household must be in [0, 12] for Kindergeld."
        )
    if kindergeld_recipient not in KINDERGELD_2025_RECIPIENT_VALUES:
        raise ValueError(
            f"Unsupported kindergeld_recipient: {kindergeld_recipient!r} "
            "(allowed: taxpayer, spouse, other_parent, none)."
        )
    if kindergeld_recipient not in KINDERGELD_2025_THIS_FILER_RECIPIENTS:
        return D("0.00")
    return q2(KINDERGELD_2025_MONTHLY_EUR * D(months_in_household))


def disability_pauschbetrag_2025(
    gdb_grade: int,
    *,
    helpless_or_blind: bool = False,
) -> Decimal:
    """§ 33b Abs. 3 EStG Pauschbetrag lookup for a single GdB grade.

    Returns the §-33b-Abs.-3 EStG flat allowance for a given Grad der
    Behinderung. The 2021 Behinderten-Pauschbetragsgesetz
    (BGBl. I 2020 S. 2770) doubled the rates effective 2021 and the
    2025 statute carries them unchanged. EStH 2025 publishes the
    same tabellarisch.

    Schedule (per § 33b Abs. 3 Satz 2 EStG, see
    ``BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR``):
        GdB < 20  → €0      (no Pauschbetrag attaches)
        GdB 20    → €384
        GdB 30    → €620
        GdB 40    → €860
        GdB 50    → €1,140
        GdB 60    → €1,440
        GdB 70    → €1,780
        GdB 80    → €2,120
        GdB 90    → €2,460
        GdB 100   → €2,840

    Special branch (§ 33b Abs. 3 Satz 3 EStG, also § 33b Abs. 6 EStG):
    Merkzeichen H (hilflos) / Bl (blind) / Pflegegrad 4 oder 5 →
    erhöhter Pauschbetrag of €7,400. Mutually exclusive with the GdB
    schedule under § 33b Abs. 3 Satz 2 EStG: the special amount
    supersedes the schedule when claimed.

    Non-decadic GdB grades are rounded DOWN to the nearest valid step
    (so GdB 35 → €620, GdB 87 → €2,120). This mirrors the BMF EStH
    treatment: an attestation issued at GdB 35 still attaches to the
    §-33b-Abs.-3 EStG slot for GdB 30. The fail-closed boundary on
    ``gdb_grade < 0`` and ``gdb_grade > 100`` matches the loader's
    intake validation.

    Authority:
    - § 33b Abs. 3 Satz 2 EStG (Pauschbetrag schedule by GdB).
    - § 33b Abs. 3 Satz 3 EStG (erhöhter Pauschbetrag €7,400).
    - § 33b Abs. 6 EStG (Pflegegrad 4/5 routing into Satz 3 EStG).
    - BGBl. I 2020 S. 2770 (Behinderten-Pauschbetragsgesetz, 2021
      doubling carried into 2025).
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    if helpless_or_blind:
        return BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR
    if gdb_grade < 0 or gdb_grade > 100:
        raise ValueError(
            f"§ 33b Abs. 3 EStG: gdb_grade must be in [0, 100]; got {gdb_grade!r}."
        )
    if gdb_grade < 20:
        # § 33b Abs. 3 Satz 2 EStG attaches no Pauschbetrag below GdB
        # 20; the loader still accepts the value so a child's grade can
        # round-trip through intake without forcing a transfer claim.
        return D("0.00")
    # Round DOWN to the nearest decadic GdB step. BMF EStH treats a
    # higher attestation as attaching to the next-lower decadic slot
    # (e.g. GdB 35 attests to GdB 30) for the §-33b-Abs.-3-EStG amount.
    rounded_step = (gdb_grade // 10) * 10
    return BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[rounded_step]


def child_disability_pauschbetrag_for_transferral_2025(
    *,
    child: "Child2025",
    transfer_election_active: bool,
) -> Decimal:
    """Per-child § 33b Abs. 5 EStG Pauschbetrag transferral amount.

    Returns the per-child §-33b-Abs.-3 EStG Pauschbetrag that flows to
    the parents when the profile-level transferral election is active,
    and zero otherwise. The election is a profile field (see
    ``elections.germany_disability_pauschbetrag_transfer``); the loader
    enforces fail-closed validation that the election must be declared
    whenever any child has ``disability_gdb > 0``.

    The lookup uses :func:`disability_pauschbetrag_2025` so the GdB
    schedule lives in a single canonical edit point per invariant I1.

    Authority:
    - § 33b Abs. 5 EStG (transferral of a qualifying child's
      Pauschbetrag to the parents when the parents claim it).
    - § 33b Abs. 3 EStG (per-grade schedule used for the transferral
      amount).
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    if not transfer_election_active:
        return D("0.00")
    return disability_pauschbetrag_2025(
        int(child.disability_gdb),
        helpless_or_blind=bool(child.disability_helpless_or_blind),
    )


def aggregate_germany_children_facts_2025(
    children: tuple[Child2025, ...],
    *,
    filing_posture: str,
    disability_pauschbetrag_transfer_election: bool = False,
) -> GermanyChildrenFacts2025:
    """Sum per-child Kinderfreibetrag and Kindergeld for the household.

    Filters out non-qualifying children (``relationship`` other than
    ``qualifying_child``); ``qualifying_relative`` rows are tracked on
    the U.S. side via the same ``Child2025`` schema but never count
    toward the German Kinderfreibetrag.

    The optional ``disability_pauschbetrag_transfer_election`` activates
    the § 33b Abs. 5 EStG transferral path: when ``True`` and any
    qualifying child has a non-zero § 33b Abs. 3 EStG Pauschbetrag
    (GdB ≥ 20 or hilflos/blind), the per-child amounts are summed into
    ``disability_pauschbetrag_total_transferred_eur``. When ``False``
    (or when no child has a Pauschbetrag), the transferral total is
    zero and the parents' assessment is unchanged. Loader-side
    validation enforces the fail-closed contract that the election
    must be present whenever any child has ``disability_gdb > 0``.

    Authority context: § 31 EStG / § 32 Abs. 6 EStG / BKGG /
    § 33b Abs. 3 EStG / § 33b Abs. 5 EStG. See
    https://www.gesetze-im-internet.de/estg/__31.html and
    https://www.gesetze-im-internet.de/estg/__33b.html .
    """
    if filing_posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(
            f"Unsupported Germany filing posture for children aggregation: {filing_posture}"
        )
    qualifying = tuple(c for c in children if c.relationship == "qualifying_child")
    children_count = len(qualifying)
    kinderfreibetrag_total = D("0.00")
    kindergeld_total = D("0.00")
    disability_transferred_total = D("0.00")
    for child in qualifying:
        kinderfreibetrag_total += kinderfreibetrag_for_child_2025(
            int(child.months_in_household),
            filing_posture=filing_posture,
        )
        kindergeld_total += kindergeld_for_child_2025(
            int(child.months_in_household),
            child.kindergeld_recipient,
        )
        # § 33b Abs. 5 EStG transferral — only summed when the election
        # is active. Without the election the per-child amount is forfeit
        # under § 33b Abs. 5 Satz 1 EStG (the parents must claim it for
        # the child's allowance to attach to the assessment).
        disability_transferred_total += child_disability_pauschbetrag_for_transferral_2025(
            child=child,
            transfer_election_active=disability_pauschbetrag_transfer_election,
        )
    return GermanyChildrenFacts2025(
        children=tuple(children),
        children_present=children_count > 0,
        children_count=children_count,
        kinderfreibetrag_total_eur=q2(kinderfreibetrag_total),
        kindergeld_received_total_eur=q2(kindergeld_total),
        disability_pauschbetrag_total_transferred_eur=q2(
            disability_transferred_total
        ),
    )


def _normalized_germany_filing_posture_2025(inputs: JointOrdinaryInputs2025) -> str:
    posture = (inputs.filing_posture or "").strip().lower()
    if not posture:
        if len(inputs.people) == 1:
            posture = "single"
        else:
            # § 26 Abs. 2 EStG makes the spouse assessment form an election on the
            # return. Do not infer Zusammenveranlagung merely from a two-person dataset.
            raise ValueError(
                "Two-person Germany ordinary assessment requires explicit Germany filing_posture under § 26 EStG."
            )
    if posture not in {"single", "married_joint", "married_separate"}:
        raise ValueError(f"Unsupported Germany filing posture: {posture}")
    if posture == "single" and len(inputs.people) != 1:
        raise ValueError("Germany filing posture 'single' requires exactly one person.")
    if posture in {"married_joint", "married_separate"} and len(inputs.people) != 2:
        raise ValueError(f"Germany filing posture '{posture}' requires exactly two people.")
    if posture == "married_joint" and not inputs.joint_assessment_prerequisites_validated:
        # § 26 Abs. 1-3 EStG is the legal gate for Ehegatten-/Lebenspartner splitting.
        # The core law function must carry proof that those facts were checked before it can
        # aggregate under § 26b EStG and apply § 32a Abs. 5 EStG.
        raise ValueError("Germany married_joint requires validated § 26 EStG prerequisites.")
    return posture


def _allocations_or_default(
    explicit: tuple[Decimal, ...],
    *,
    people_count: int,
    aggregate_amount: Decimal,
    filing_posture: str,
    label: str,
) -> tuple[Decimal, ...]:
    if explicit:
        if len(explicit) != people_count:
            raise ValueError(f"{label} allocations must match the people count.")
        allocations = tuple(q2(_require_non_negative_decimal(value, label=label)) for value in explicit)
        if q2(sum(allocations, D("0.00"))) != q2(aggregate_amount):
            raise ValueError(f"{label} allocations must reconcile to the aggregate amount.")
        return allocations
    if filing_posture == "married_separate" and aggregate_amount != D("0.00"):
        raise ValueError(
            f"Germany filing posture 'married_separate' requires explicit {label} allocations."
        )
    allocations = [D("0.00")] * people_count
    if people_count:
        allocations[0] = q2(aggregate_amount)
    return tuple(allocations)


def _validate_joint_ordinary_inputs_2025(inputs: JointOrdinaryInputs2025) -> None:
    # § 2 Abs. 2 EStG starts from real positive receipts and deductible expenses,
    # while § 36 Abs. 2 EStG credits only actual non-negative withholdings and
    # prepayments. Reject impossible source facts before allowances or splitting.
    _require_non_negative_decimal(inputs.other_income_22nr3_eur, label="other_income_22nr3_eur")
    _require_non_negative_decimal(inputs.other_income_22nr3_threshold_eur, label="other_income_22nr3_threshold_eur")
    _require_non_negative_decimal(inputs.prepayments_eur, label="prepayments_eur")
    for value in inputs.other_income_22nr3_by_person_eur:
        _require_non_negative_decimal(value, label="other_income_22nr3_by_person_eur")
    for value in inputs.prepayments_by_person_eur:
        _require_non_negative_decimal(value, label="prepayments_by_person_eur")
    for person in inputs.people:
        wage = person.wage
        for label, value in (
            ("gross_wage_eur", wage.gross_wage_eur),
            ("withheld_wage_tax_eur", wage.withheld_wage_tax_eur),
            ("withheld_solidarity_surcharge_eur", wage.withheld_solidarity_surcharge_eur),
            ("multiannual_wage_eur", wage.multiannual_wage_eur),
            ("employer_pension_contribution_eur", wage.employer_pension_contribution_eur),
            ("employee_pension_contribution_eur", wage.employee_pension_contribution_eur),
            ("employee_health_insurance_eur", wage.employee_health_insurance_eur),
            ("employee_nursing_care_insurance_eur", wage.employee_nursing_care_insurance_eur),
            ("employee_unemployment_insurance_eur", wage.employee_unemployment_insurance_eur),
            ("manual_work_equipment_deduction_eur", person.manual_work_equipment_deduction_eur),
            ("telecom_deduction_eur", person.telecom_deduction_eur),
            ("employment_legal_insurance_deduction_eur", person.employment_legal_insurance_deduction_eur),
            ("cross_border_tax_help_deduction_eur", person.cross_border_tax_help_deduction_eur),
            ("other_vorsorge_cap_eur", person.other_vorsorge_cap_eur),
        ):
            _require_non_negative_decimal(value, label=label)
        _require_unit_interval(
            person.health_insurance_sick_pay_reduction_rate,
            label="health_insurance_sick_pay_reduction_rate",
        )
        _require_non_negative_int(
            person.home_office_days_without_visit,
            label="home_office_days_without_visit",
        )
        _require_non_negative_int(
            person.home_office_days_with_visit,
            label="home_office_days_with_visit",
        )
        for item in person.work_equipment_items:
            _require_non_negative_decimal(item.gross_amount_eur, label="work_equipment.gross_amount_eur")
            _require_unit_interval(item.work_use_share, label="work_equipment.work_use_share")
            _require_non_negative_decimal(item.deductible_amount_eur, label="work_equipment.deductible_amount_eur")


@dataclass(frozen=True)
class CapitalTaxAssessment2025:
    taxable_capital_eur: Decimal
    gross_income_tax_eur: Decimal
    foreign_tax_credit_eur: Decimal
    income_tax_after_foreign_credit_eur: Decimal
    solidarity_surcharge_eur: Decimal
    total_tax_eur: Decimal


@dataclass(frozen=True)
class TreatyRelievedCapitalTax2025:
    treaty_credit_eur: Decimal
    solidarity_surcharge_before_treaty_eur: Decimal
    solidarity_surcharge_after_treaty_eur: Decimal
    income_tax_before_treaty_eur: Decimal
    income_tax_after_treaty_eur: Decimal
    total_tax_after_treaty_eur: Decimal


@dataclass(frozen=True)
class GermanyCapitalLawStage2025:
    step: str
    value_eur: Decimal
    legal_reference: str
    authority_url: str
    note: str
    precision_note: str = ""


@dataclass(frozen=True)
class GermanyCapitalAssessment2025:
    stock_gain: Decimal = D("0.00")
    dher_stock_gain: Decimal = D("0.00")
    stock_gain_after_carryforward: Decimal = D("0.00")
    stock_loss_carryforward_used: Decimal = D("0.00")
    stock_loss_carryforward_remaining: Decimal = D("0.00")
    fund_gain: Decimal = D("0.00")
    option_gain: Decimal = D("0.00")
    positive_income_total: Decimal = D("0.00")
    explicit_foreign_tax_total: Decimal = D("0.00")
    net_creditable_foreign_tax_total: Decimal = D("0.00")
    foreign_tax_credit_cap_eur: Decimal = D("0.00")
    equity_fund_total: Decimal = D("0.00")
    non_equity_fund_total: Decimal = D("0.00")
    non_fund_positive_income_total: Decimal = D("0.00")
    fund_taxable_after_teilfreistellung_eur: Decimal = D("0.00")
    saver_allowance_used_eur: Decimal = D("0.00")
    fund_teilfreistellung_reduction_eur: Decimal = D("0.00")
    combined_current_capital_eur: Decimal = D("0.00")
    taxable_before_teilfreistellung_eur: Decimal = D("0.00")
    taxable_after_teilfreistellung_eur: Decimal = D("0.00")
    capital_no_teilfreistellung: CapitalTaxAssessment2025 | None = None
    capital_with_teilfreistellung: CapitalTaxAssessment2025 | None = None
    treaty_relieved_capital: TreatyRelievedCapitalTax2025 | None = None
    bank_certificate_income_eur: Decimal = D("0.00")
    bank_certificate_stock_gain_eur: Decimal = D("0.00")
    bank_certificate_non_stock_income_eur: Decimal = D("0.00")
    bank_certificate_saver_allowance_used_eur: Decimal = D("0.00")
    bank_certificate_foreign_tax_credited_eur: Decimal = D("0.00")
    bank_certificate_foreign_tax_not_credited_eur: Decimal = D("0.00")
    domestic_capital_tax_withheld_eur: Decimal = D("0.00")
    domestic_capital_soli_withheld_eur: Decimal = D("0.00")
    domestic_capital_withholding_credit_eur: Decimal = D("0.00")
    treaty_us_source_dividend_gross_eur: Decimal = D("0.00")
    treaty_us_source_dividend_precredit_tax_eur: Decimal = D("0.00")
    treaty_us_source_dividend_allowed_us_tax_eur: Decimal = D("0.00")
    treaty_us_source_dividend_credit_eur: Decimal = D("0.00")
    treaty_dividend_packet_items: tuple[GermanyUSTreatyDividendPacketItem2025, ...] = ()
    capital_tax_no_teilfreistellung_eur: Decimal = D("0.00")
    capital_tax_with_teilfreistellung_before_treaty_eur: Decimal = D("0.00")
    capital_tax_with_teilfreistellung_after_treaty_eur: Decimal = D("0.00")
    # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung), the
    # laufender-Ertrag amount that lands on Anlage KAP-INV Zeilen 9-13.
    # Computed by DE25-13F-VORABPAUSCHALE; surfaced here so the KAP-form
    # projection can re-emit it under ``de.kap_inv.line_9_13_eur``.
    # https://www.gesetze-im-internet.de/invstg_2018/__19.html
    vorabpauschale_taxable_after_teilfreistellung_eur: Decimal = D("0.00")
    law_order_stages: tuple[GermanyCapitalLawStage2025, ...] = ()


def german_income_tax_single_2025(zve_eur: Decimal) -> Decimal:
    # Official tariff formula and rounding order from § 32a Abs. 1 EStG.
    x = floor_euro(zve_eur)
    if x <= TARIFF_2025_GROUND_ALLOWANCE_EUR:
        tax = D("0")
    elif x <= TARIFF_2025_PROGRESS_ZONE_1_END_EUR:
        y = (x - TARIFF_2025_GROUND_ALLOWANCE_EUR) / D("10000")
        tax = (D("932.30") * y + D("1400")) * y
    elif x <= TARIFF_2025_PROGRESS_ZONE_2_END_EUR:
        z = (x - TARIFF_2025_PROGRESS_ZONE_1_END_EUR) / D("10000")
        tax = (D("176.64") * z + D("2397")) * z + D("1015.13")
    elif x <= TARIFF_2025_TOP_RATE_START_EUR:
        tax = D("0.42") * x - D("10911.92")
    else:
        tax = D("0.45") * x - D("19246.67")
    return floor_euro(tax)


def german_income_tax_split_2025(zve_eur: Decimal) -> Decimal:
    # Joint splitting under § 26b and § 32a Abs. 5 EStG.
    return floor_euro(german_income_tax_single_2025(zve_eur / D("2")) * D("2"))


def german_soli_assessment_2025(
    ordinary_income_tax_eur: Decimal,
    *,
    filing_posture: str = "married_joint",
) -> Decimal:
    # 2025 solidarity-surcharge free limits from SolzG § 3 and § 4 are posture-specific:
    # single/separate assessments use 19,950 EUR; splitting assessments use 39,900 EUR.
    posture = filing_posture.strip().lower()
    if posture in {"single", "married_separate"}:
        threshold = SOLI_SINGLE_THRESHOLD_EUR
    elif posture == "married_joint":
        threshold = SOLI_JOINT_THRESHOLD_EUR
    else:
        raise ValueError(f"Unsupported Germany solidarity-surcharge filing posture: {filing_posture}")
    if ordinary_income_tax_eur <= threshold:
        return D("0.00")
    raw = floor_cent(ordinary_income_tax_eur * SOLI_RATE)
    mitigation = floor_cent((ordinary_income_tax_eur - threshold) * SOLI_MITIGATION_RATE)
    return min(raw, mitigation)


def home_office_tagespauschale_2025(
    days_without_first_workplace_visit: int,
    days_with_first_workplace_visit: int,
    *,
    visit_days_no_other_workplace: bool = False,
) -> Decimal:
    # Fix: keep the home-office cap in one helper so every caller uses the same § 4 Abs. 5
    # Satz 1 Nr. 6c EStG / § 9 Abs. 5 EStG daily-rate and annual-cap rule.
    _require_non_negative_int(days_without_first_workplace_visit, label="days_without_first_workplace_visit")
    _require_non_negative_int(days_with_first_workplace_visit, label="days_with_first_workplace_visit")
    if days_with_first_workplace_visit and not visit_days_no_other_workplace:
        raise ValueError(
            "Home-office days with a first-workplace visit require an explicit no other workplace position."
        )
    eligible_days = days_without_first_workplace_visit + days_with_first_workplace_visit
    return q2(min(D(eligible_days) * HOME_OFFICE_DAILY_RATE_EUR, HOME_OFFICE_MAX_EUR))


def retirement_special_expense_deduction_2025(
    employee_pension_contribution_eur: Decimal,
    employer_pension_contribution_eur: Decimal,
) -> Decimal:
    # Fix: do not double-count the tax-free employer pension share.
    # Under § 10 Abs. 1 Nr. 2 Satz 6 and Abs. 3 Sätze 5-6 EStG, the employer share is added
    # to the base and then subtracted again. From 2023 onward the rate is 100%, so the
    # deductible amount for employees is effectively the employee share.
    gross_retirement_base = min(
        employee_pension_contribution_eur + employer_pension_contribution_eur,
        RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR,
    )
    deductible_amount = gross_retirement_base - employer_pension_contribution_eur
    return q2(max(deductible_amount, D("0.00")))


def joint_retirement_special_expense_deductions_2025(
    people: tuple[PersonOrdinaryInputs2025, ...],
) -> tuple[Decimal, ...]:
    # § 10 Abs. 3 Sätze 1, 2, 5 und 6 EStG doubles the cap for jointly assessed
    # spouses, applies that cap to the combined retirement base, then subtracts
    # all tax-free § 3 Nr. 62 employer shares. Per-spouse allocation is audit output only.
    joint_cap = RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR * D("2")
    employee_shares = tuple(
        _require_non_negative_decimal(
            person.wage.employee_pension_contribution_eur,
            label="employee_pension_contribution_eur",
        )
        for person in people
    )
    employer_shares = tuple(
        _require_non_negative_decimal(
            person.wage.employer_pension_contribution_eur,
            label="employer_pension_contribution_eur",
        )
        for person in people
    )
    gross_bases = tuple(employee + employer for employee, employer in zip(employee_shares, employer_shares, strict=True))
    total_gross_base = sum(gross_bases, D("0.00"))
    if total_gross_base == D("0.00"):
        return tuple(D("0.00") for _ in people)
    capped_total_base = min(total_gross_base, joint_cap)
    household_deduction = q2(max(D("0.00"), capped_total_base - sum(employer_shares, D("0.00"))))
    return _allocate_total_by_weights(household_deduction, employee_shares)


def deductible_basic_health_contribution_2025(
    employee_health_insurance_eur: Decimal,
    employee_nursing_care_insurance_eur: Decimal,
    *,
    statutory_health_sick_pay_reduction_rate: Decimal,
) -> Decimal:
    # Fix: statutory health-insurance contributions with Krankengeld entitlement are not
    # fully deductible as basic health coverage. § 10 Abs. 1 Nr. 3 Satz 4 EStG requires
    # reducing the health-insurance portion by 4% for the sick-pay component unless facts
    # show a different non-deductible share.
    _require_non_negative_decimal(employee_health_insurance_eur, label="employee_health_insurance_eur")
    _require_non_negative_decimal(employee_nursing_care_insurance_eur, label="employee_nursing_care_insurance_eur")
    _require_unit_interval(
        statutory_health_sick_pay_reduction_rate,
        label="statutory_health_sick_pay_reduction_rate",
    )
    reduced_health = employee_health_insurance_eur * (D("1.00") - statutory_health_sick_pay_reduction_rate)
    return q2(max(reduced_health, D("0.00")) + employee_nursing_care_insurance_eur)


def other_vorsorge_allowed_employee_2025(
    health_and_nursing_contributions_eur: Decimal,
    other_vorsorge_contributions_eur: Decimal,
    *,
    cap_eur: Decimal = OTHER_VORSORGE_CAP_EMPLOYEE_EUR,
) -> Decimal:
    # § 10 Abs. 4 Sätze 1-2 EStG uses either the 2,800 EUR general cap or the
    # 1,900 EUR employee/covered-health-cost cap. Basic health and nursing
    # contributions use that cap first; only unused room remains for § 10 Abs. 1 Nr. 3a.
    _require_non_negative_decimal(cap_eur, label="other_vorsorge_cap_eur")
    remaining_cap = cap_eur - min(
        health_and_nursing_contributions_eur,
        cap_eur,
    )
    return q2(max(D("0.00"), min(other_vorsorge_contributions_eur, remaining_cap)))


def joint_other_vorsorge_allowed_employee_2025(
    health_and_nursing_contributions: tuple[Decimal, ...],
    other_vorsorge_contributions: tuple[Decimal, ...],
    other_vorsorge_caps: tuple[Decimal, ...] | None = None,
) -> tuple[Decimal, ...]:
    # § 10 Abs. 4 Sätze 1-4 EStG determines each spouse's 1,900/2,800 EUR cap first,
    # then uses the sum as the joint cap. Basic health/nursing contributions consume
    # the common cap before unemployment-insurance or other § 10 Abs. 1 Nr. 3a amounts.
    caps = other_vorsorge_caps or tuple(
        OTHER_VORSORGE_CAP_EMPLOYEE_EUR for _ in health_and_nursing_contributions
    )
    if len(caps) != len(health_and_nursing_contributions):
        raise ValueError("other_vorsorge_caps must match the people count.")
    joint_cap = q2(sum((_require_non_negative_decimal(cap, label="other_vorsorge_cap_eur") for cap in caps), D("0.00")))
    total_health_and_nursing = q2(sum(health_and_nursing_contributions, D("0.00")))
    total_other = q2(sum(other_vorsorge_contributions, D("0.00")))
    remaining_cap = joint_cap - min(total_health_and_nursing, joint_cap)
    total_allowed = q2(max(D("0.00"), min(total_other, remaining_cap)))
    if total_allowed == D("0.00") or total_other == D("0.00"):
        return tuple(D("0.00") for _ in other_vorsorge_contributions)
    return _allocate_total_by_weights(total_allowed, other_vorsorge_contributions)


def _allocate_total_by_weights(total: Decimal, weights: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    total = q2(total)
    if total == D("0.00") or not weights:
        return tuple(D("0.00") for _ in weights)
    total_weight = sum((max(weight, D("0.00")) for weight in weights), D("0.00"))
    if total_weight == D("0.00"):
        return tuple(D("0.00") for _ in weights)
    allocations: list[Decimal] = []
    remaining = total
    positive_indexes = [index for index, weight in enumerate(weights) if weight > D("0.00")]
    last_positive = positive_indexes[-1]
    for index, weight in enumerate(weights):
        if weight <= D("0.00"):
            allocations.append(D("0.00"))
            continue
        if index == last_positive:
            allocations.append(q2(remaining))
        else:
            share = q2(total * weight / total_weight)
            allocations.append(share)
            remaining -= share
    return tuple(allocations)


def other_income_22nr3_taxable_2025(
    other_income_eur: Decimal,
    threshold_eur: Decimal,
) -> Decimal:
    # § 22 Nr. 3 EStG uses a Freigrenze. Once crossed, the full amount is taxable.
    _require_non_negative_decimal(other_income_eur, label="other_income_eur")
    _require_non_negative_decimal(threshold_eur, label="threshold_eur")
    return q2(other_income_eur if other_income_eur >= threshold_eur else D("0.00"))


def altersentlastungsbetrag_2025(
    *,
    birth_year: int,
    eligible_income_eur: Decimal,
    tax_year: int = 2025,
) -> Decimal:
    # § 24a Satz 1, 3, 5 EStG: an Altersentlastungsbetrag of (rate × eligible
    # income) capped at the cohort cap is granted to taxpayers who turned
    # 64 BEFORE the start of the assessment year. Rate and cap are fixed for
    # life by the calendar year in which the taxpayer first met the age
    # threshold (Vollendung des 64. Lebensjahres) per § 24a Satz 5 EStG.
    # Eligible income excludes § 19 wages and Beamtenversorgung pensions
    # (§ 24a Satz 2 Nr. 1 EStG); capital income is excluded unless the
    # taxpayer elects Günstigerprüfung under § 32d Abs. 6 EStG.
    # https://www.gesetze-im-internet.de/estg/__24a.html
    if birth_year <= 0:
        return D("0.00")
    _require_non_negative_decimal(eligible_income_eur, label="eligible_income_eur")
    year_turned_64 = birth_year + ALTERSENTLASTUNGSBETRAG_AGE_THRESHOLD_YEARS
    if year_turned_64 >= tax_year:
        # § 24a Satz 3 EStG: the allowance applies starting the assessment
        # year following the year the taxpayer turned 64. A taxpayer who
        # turns 64 during 2025 first qualifies in 2026.
        return D("0.00")
    if year_turned_64 not in ALTERSENTLASTUNGSBETRAG_2025_TABLE:
        # Use the closest cohort year covered by the official Anlage; for
        # taxpayers who turned 64 before 2005 the rate-pair is the 2005 row.
        cohort_year = max(min(year_turned_64, max(ALTERSENTLASTUNGSBETRAG_2025_TABLE)), min(ALTERSENTLASTUNGSBETRAG_2025_TABLE))
    else:
        cohort_year = year_turned_64
    rate, cap = ALTERSENTLASTUNGSBETRAG_2025_TABLE[cohort_year]
    return q2(min(cap, q2(eligible_income_eur * rate)))


def zumutbare_belastung_2025(
    *,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    family_category: str,
) -> Decimal:
    # § 33 Abs. 3 EStG progressive (slab) computation per BFH VI R 75/14
    # (19.01.2017): each tier rate applies only to the band within that
    # tier. The thresholds are 15 340 EUR and 51 130 EUR; the bracket
    # rates depend on family category.
    # https://www.gesetze-im-internet.de/estg/__33.html
    _require_non_negative_decimal(
        gesamtbetrag_der_einkuenfte_eur, label="gesamtbetrag_der_einkuenfte_eur"
    )
    if family_category not in ZUMUTBARE_BELASTUNG_2025_RATES:
        raise ValueError(
            "Unsupported zumutbare_belastung_family_category "
            f"{family_category!r}; expected one of "
            f"{sorted(ZUMUTBARE_BELASTUNG_2025_RATES)}."
        )
    bracket_a, bracket_b = ZUMUTBARE_BELASTUNG_2025_BRACKETS_EUR
    rate_a, rate_b, rate_c = ZUMUTBARE_BELASTUNG_2025_RATES[family_category]
    income = gesamtbetrag_der_einkuenfte_eur
    band_a = min(income, bracket_a)
    band_b = max(D("0.00"), min(income, bracket_b) - bracket_a)
    band_c = max(D("0.00"), income - bracket_b)
    burden = band_a * rate_a + band_b * rate_b + band_c * rate_c
    return q2(burden)


def aussergewoehnliche_belastungen_deductible_2025(
    *,
    medical_expenses_eur: Decimal,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    family_category: str,
) -> tuple[Decimal, Decimal]:
    # § 33 Abs. 1 / Abs. 3 EStG: deductible außergewöhnliche Belastungen =
    # max(0, claimed expenses − zumutbare Belastung). Returns
    # (deductible, zumutbare_belastung) so the per-stage trace can show
    # both legs.
    # https://www.gesetze-im-internet.de/estg/__33.html
    _require_non_negative_decimal(medical_expenses_eur, label="medical_expenses_eur")
    burden = zumutbare_belastung_2025(
        gesamtbetrag_der_einkuenfte_eur=gesamtbetrag_der_einkuenfte_eur,
        family_category=family_category,
    )
    deductible = q2(max(D("0.00"), medical_expenses_eur - burden))
    return deductible, burden


def unterhaltsleistungen_deductible_2025(
    *,
    support_payments_eur: Decimal,
    recipient_income_eur: Decimal,
    relationship: str,
    grundfreibetrag_eur: Decimal,
) -> Decimal:
    # § 33a Abs. 1 Satz 1 EStG: deductible support payments capped at the
    # Grundfreibetrag (§ 32a Abs. 1 EStG). § 33a Abs. 1 Satz 5 EStG reduces
    # the cap by the recipient's own income exceeding €624 ("Eigenbezüge
    # und Bezüge"). Relationship gates eligibility per § 33a Abs. 1 Satz 1
    # EStG (legal duty of support).
    # https://www.gesetze-im-internet.de/estg/__33a.html
    _require_non_negative_decimal(support_payments_eur, label="support_payments_eur")
    _require_non_negative_decimal(recipient_income_eur, label="recipient_income_eur")
    _require_non_negative_decimal(grundfreibetrag_eur, label="grundfreibetrag_eur")
    cleaned_relationship = (relationship or "").strip().lower()
    if support_payments_eur == D("0.00") and not cleaned_relationship:
        return D("0.00")
    if cleaned_relationship not in UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS:
        raise ValueError(
            "Unsupported support_recipient_relationship "
            f"{relationship!r}; expected one of "
            f"{sorted(UNTERHALTSLEISTUNGEN_2025_RECIPIENT_RELATIONSHIPS)} per § 33a Abs. 1 EStG."
        )
    eigenbezuege_reduction = max(
        D("0.00"),
        recipient_income_eur - UNTERHALTSLEISTUNGEN_2025_RECIPIENT_INCOME_FREIBETRAG_EUR,
    )
    cap = max(D("0.00"), grundfreibetrag_eur - eigenbezuege_reduction)
    return q2(min(support_payments_eur, cap))


def behinderung_pauschbetrag_2025(
    *,
    gdb: int,
    hilflos_or_blind: bool,
) -> Decimal:
    # § 33b Abs. 3 EStG flat allowance by GdB tier; § 33b Abs. 3 Satz 3
    # EStG gives the special €7,400 amount for hilflose / blinde
    # Menschen. The two paths are mutually exclusive; the special amount
    # supersedes the GdB schedule when claimed.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    if hilflos_or_blind:
        return BEHINDERUNG_PAUSCHBETRAG_HILFLOS_BLIND_2025_EUR
    if gdb <= 0:
        return D("0.00")
    if gdb % 10 != 0 or gdb < 20 or gdb > 100:
        raise ValueError(
            f"Unsupported Grad der Behinderung {gdb!r}; § 33b Abs. 3 EStG "
            "requires a multiple of 10 in [20, 100] or hilflos/blind status."
        )
    return BEHINDERUNG_PAUSCHBETRAG_2025_TABLE_EUR[gdb]


def spendenabzug_2025(
    *,
    donations_eur: Decimal,
    gesamtbetrag_der_einkuenfte_eur: Decimal,
    carryforward_eur: Decimal,
) -> Decimal:
    # § 10b Abs. 1 Satz 1 Nr. 1 EStG: deductible Sonderausgabe = min(
    # donations, 20 % of GdE). § 10b Abs. 1 Sätze 9-10 EStG carryforwards
    # are not modeled — fail closed if any carryforward is asserted.
    # https://www.gesetze-im-internet.de/estg/__10b.html
    _require_non_negative_decimal(donations_eur, label="donations_eur")
    _require_non_negative_decimal(
        gesamtbetrag_der_einkuenfte_eur, label="gesamtbetrag_der_einkuenfte_eur"
    )
    _require_non_negative_decimal(carryforward_eur, label="carryforward_eur")
    if carryforward_eur > D("0.00"):
        raise NotImplementedError(
            "§ 10b Abs. 1 Sätze 9-10 EStG donation carryforwards "
            "(Großspendenrest) are not modeled for 2025; the workspace "
            "asserts a non-zero charitable_donations_carryforward_eur. "
            "Resolve manually before running the pipeline."
        )
    cap = q2(gesamtbetrag_der_einkuenfte_eur * SPENDENABZUG_2025_GDE_FRACTION_CAP)
    return q2(min(donations_eur, cap))


def arbeitszimmer_deductible_2025(
    *,
    arbeitszimmer_claimed: bool,
    qualifies_as_mittelpunkt: bool,
    actual_costs_eur: Decimal,
    tagespauschale_days_total: int,
) -> Decimal:
    # § 4 Abs. 5 Satz 1 Nr. 6b EStG: full deduction of actual costs IF the
    # home office is the Mittelpunkt der gesamten betrieblichen und
    # beruflichen Betätigung; otherwise a Jahrespauschale of €1,260
    # (§ 4 Abs. 5 Satz 1 Nr. 6b Satz 4 EStG). § 4 Abs. 5 Satz 1 Nr. 6c
    # Satz 3 EStG forbids combining the Jahrespauschale with the
    # Tagespauschale (Nr. 6c) for the same period — ``tagespauschale_days_total``
    # is the post-cap number of days already claimed; non-zero forbids
    # the Arbeitszimmer election.
    # https://www.gesetze-im-internet.de/estg/__4.html
    _require_non_negative_decimal(actual_costs_eur, label="actual_costs_eur")
    if not arbeitszimmer_claimed:
        return D("0.00")
    if tagespauschale_days_total > 0:
        raise ValueError(
            "§ 4 Abs. 5 Satz 1 Nr. 6c Satz 3 EStG forbids combining the "
            "Arbeitszimmer-Pauschale (Nr. 6b) with the Tagespauschale (Nr. 6c) "
            "for the same period. Choose one election; the workspace currently "
            f"claims both ({tagespauschale_days_total} Tagespauschale days)."
        )
    if qualifies_as_mittelpunkt:
        return q2(actual_costs_eur)
    return ARBEITSZIMMER_JAHRESPAUSCHALE_2025_EUR


def foreign_tax_credit_32d5_cap_2025(
    foreign_tax_items: tuple[tuple[Decimal, Decimal, Decimal], ...],
    *,
    capital_tax_rate: Decimal,
) -> Decimal:
    # § 32d Abs. 5 EStG caps creditable foreign tax per individual taxable capital item
    # and reduces paid foreign tax by any refund/reduction entitlement before applying the cap.
    _require_unit_interval(capital_tax_rate, label="capital_tax_rate")
    total_credit = D("0.00")
    for taxable_income_eur, foreign_tax_paid_eur, refund_entitlement_eur in foreign_tax_items:
        _require_non_negative_decimal(taxable_income_eur, label="foreign taxable capital income")
        _require_non_negative_decimal(foreign_tax_paid_eur, label="foreign tax paid")
        _require_non_negative_decimal(refund_entitlement_eur, label="foreign tax refund entitlement")
        net_foreign_tax = max(D("0.00"), foreign_tax_paid_eur - refund_entitlement_eur)
        item_cap = taxable_income_eur * capital_tax_rate
        total_credit += min(net_foreign_tax, item_cap)
    return q2(total_credit)


def _taxable_capital_item_after_saver_allowance_2025(
    item_taxable_before_allowance_eur: Decimal,
    *,
    total_taxable_before_allowance_eur: Decimal,
    saver_allowance_eur: Decimal,
) -> Decimal:
    # § 20 Abs. 9 EStG applies the Sparer-Pauschbetrag before § 32d Abs. 1/5 EStG
    # taxes and credits capital income. For treaty worksheet exports, allocate that
    # allowance proportionally so the exported residence-country tax on a U.S.-source
    # dividend cannot exceed the German tax actually left on that dividend stack.
    _require_non_negative_decimal(item_taxable_before_allowance_eur, label="item_taxable_before_allowance_eur")
    _require_non_negative_decimal(total_taxable_before_allowance_eur, label="total_taxable_before_allowance_eur")
    _require_non_negative_decimal(saver_allowance_eur, label="saver_allowance_eur")
    if item_taxable_before_allowance_eur == D("0.00") or total_taxable_before_allowance_eur == D("0.00"):
        return D("0.00")
    allowance_used = min(saver_allowance_eur, total_taxable_before_allowance_eur)
    allowance_share = allowance_used * item_taxable_before_allowance_eur / total_taxable_before_allowance_eur
    return q2(max(D("0.00"), item_taxable_before_allowance_eur - allowance_share))


def _allocated_applied_credit_2025(
    item_credit_cap_eur: Decimal,
    *,
    total_credit_cap_eur: Decimal,
    actual_applied_credit_eur: Decimal,
) -> Decimal:
    _require_non_negative_decimal(item_credit_cap_eur, label="item_credit_cap_eur")
    _require_non_negative_decimal(total_credit_cap_eur, label="total_credit_cap_eur")
    _require_non_negative_decimal(actual_applied_credit_eur, label="actual_applied_credit_eur")
    if item_credit_cap_eur == D("0.00") or total_credit_cap_eur == D("0.00"):
        return D("0.00")
    allocated = actual_applied_credit_eur * item_credit_cap_eur / total_credit_cap_eur
    return q2(min(item_credit_cap_eur, allocated))


def capital_tax_after_foreign_tax_credit_2025(
    taxable_capital_eur: Decimal,
    foreign_tax_credit_eur: Decimal,
    *,
    capital_tax_rate: Decimal,
    soli_rate: Decimal,
) -> CapitalTaxAssessment2025:
    # Fix: model the statutory order explicitly.
    # § 32d Abs. 1 EStG applies the 25% capital-income tax first, § 32d Abs. 5 EStG credits
    # qualifying foreign tax next, and only the remaining income-tax assessment base is
    # subject to SolzG § 4.
    _require_non_negative_decimal(taxable_capital_eur, label="taxable_capital_eur")
    _require_non_negative_decimal(foreign_tax_credit_eur, label="foreign_tax_credit_eur")
    gross_income_tax = q2(taxable_capital_eur * capital_tax_rate)
    foreign_tax_credit = q2(min(foreign_tax_credit_eur, gross_income_tax))
    income_tax_after_foreign_credit = q2(max(D("0.00"), gross_income_tax - foreign_tax_credit))
    solidarity_surcharge = floor_cent(income_tax_after_foreign_credit * soli_rate)
    total_tax = q2(income_tax_after_foreign_credit + solidarity_surcharge)
    return CapitalTaxAssessment2025(
        taxable_capital_eur=q2(taxable_capital_eur),
        gross_income_tax_eur=gross_income_tax,
        foreign_tax_credit_eur=foreign_tax_credit,
        income_tax_after_foreign_credit_eur=income_tax_after_foreign_credit,
        solidarity_surcharge_eur=solidarity_surcharge,
        total_tax_eur=total_tax,
    )


def treaty_relieved_capital_tax_2025(
    income_tax_after_foreign_credit_eur: Decimal,
    solidarity_surcharge_before_treaty_eur: Decimal,
    treaty_credit_eur: Decimal,
) -> TreatyRelievedCapitalTax2025:
    # Fix: make the treaty-credit ordering auditable.
    # § 5 SolzG 1995 applies the relief against soli first and only then against the
    # remaining income tax.
    _require_non_negative_decimal(income_tax_after_foreign_credit_eur, label="income_tax_after_foreign_credit_eur")
    _require_non_negative_decimal(solidarity_surcharge_before_treaty_eur, label="solidarity_surcharge_before_treaty_eur")
    _require_non_negative_decimal(treaty_credit_eur, label="treaty_credit_eur")
    treaty_credit = q2(max(treaty_credit_eur, D("0.00")))
    if treaty_credit != D("0.00"):
        raise NotImplementedError(
            "Manual Germany treaty dividend credits are not supported as a separate second capital credit. "
            "Credit foreign tax through the § 32d(5) per-item cap instead."
        )
    solidarity_after_treaty = q2(max(D("0.00"), solidarity_surcharge_before_treaty_eur - treaty_credit))
    remaining_credit = q2(max(D("0.00"), treaty_credit - solidarity_surcharge_before_treaty_eur))
    income_tax_after_treaty = q2(max(D("0.00"), income_tax_after_foreign_credit_eur - remaining_credit))
    return TreatyRelievedCapitalTax2025(
        treaty_credit_eur=treaty_credit,
        solidarity_surcharge_before_treaty_eur=q2(solidarity_surcharge_before_treaty_eur),
        solidarity_surcharge_after_treaty_eur=solidarity_after_treaty,
        income_tax_before_treaty_eur=q2(income_tax_after_foreign_credit_eur),
        income_tax_after_treaty_eur=income_tax_after_treaty,
        total_tax_after_treaty_eur=q2(income_tax_after_treaty + solidarity_after_treaty),
    )


def normalized_fund_type_2025(raw: object, *, symbol: str) -> str:
    fund_type = str(raw).strip().lower()
    if fund_type not in FUND_TEILFREISTELLUNG_RATES_2025:
        raise ValueError(
            f"Fund classification for {symbol} must be one of: "
            + ", ".join(sorted(FUND_TEILFREISTELLUNG_RATES_2025))
        )
    return fund_type


def fund_type_for_symbol_2025(symbol: str, fund_classification: dict[str, str]) -> str:
    cleaned = symbol.strip().upper()
    if cleaned not in fund_classification:
        # InvStG § 20 has materially different Teilfreistellung rates by fund type.
        # Missing classification must fail closed instead of defaulting to Aktienfonds.
        raise ValueError(f"Fund classification missing for fund_like symbol {cleaned}.")
    return normalized_fund_type_2025(fund_classification[cleaned], symbol=cleaned)


def saver_allowance_for_spouse_20_9_2025(
    own_capital_before_allowance: Decimal,
    other_spouse_capital_before_allowance: Decimal,
    joint_saver_allowance_eur: Decimal,
) -> Decimal:
    # § 20 Abs. 9 Satz 3 EStG allocates half the joint Sparer-Pauschbetrag to each
    # spouse first; only unused excess from one spouse transfers to the other. A
    # negative other-spouse bucket cannot create more than the statutory joint
    # allowance.
    per_spouse_allowance = q2(joint_saver_allowance_eur / D("2"))
    own_positive_capital = max(D("0.00"), own_capital_before_allowance)
    other_positive_capital = max(D("0.00"), other_spouse_capital_before_allowance)
    transferable_excess = max(D("0.00"), per_spouse_allowance - min(other_positive_capital, per_spouse_allowance))
    return q2(min(own_positive_capital, joint_saver_allowance_eur, per_spouse_allowance + transferable_excess))


def _validated_capital_sale_bucket_2025(fact: GermanyCapitalSaleFact2025) -> str:
    bucket = str(fact.asset_bucket).strip()
    if bucket not in GERMANY_CAPITAL_SALE_BUCKETS_2025:
        # § 20 EStG, InvStG § 20/§ 21, and § 20 Abs. 6 EStG have bucket-specific
        # treatment. Unknown buckets must fail closed instead of disappearing from
        # the capital assessment.
        raise ValueError(
            "Unsupported Germany capital sale asset_bucket "
            f"{fact.asset_bucket!r} for symbol {fact.symbol!r}; classify under § 20 EStG/InvStG first."
        )
    return bucket


def _validated_capital_income_classification_2025(fact: GermanyCapitalIncomeFact2025) -> tuple[str, str]:
    kind = str(fact.kind).strip()
    bucket = str(fact.asset_bucket).strip()
    if kind not in GERMANY_CAPITAL_INCOME_KINDS_2025:
        # § 20 EStG defines the modeled income kinds; unsupported kinds must not be
        # treated as generic positive income because § 32d(5) credits are item-based.
        raise ValueError(
            "Unsupported Germany capital income kind "
            f"{fact.kind!r} for symbol {fact.symbol!r}; classify under § 20 EStG first."
        )
    if bucket not in GERMANY_CAPITAL_INCOME_BUCKETS_2025:
        # InvStG § 20/§ 21 and § 32d Abs. 5 EStG depend on the taxable item/source
        # bucket, so unknown buckets fail closed before tax-base assembly.
        raise ValueError(
            "Unsupported Germany capital income asset_bucket "
            f"{fact.asset_bucket!r} for symbol {fact.symbol!r}; classify under § 20 EStG/InvStG first."
        )
    return kind, bucket


def _validate_germany_capital_inputs_2025(inputs: GermanyCapitalAssessmentInputs2025) -> None:
    # § 20 Abs. 6 EStG loss carryforwards, § 20 Abs. 9 EStG saver allowance,
    # § 32d Abs. 1/5 tax-credit rates, and § 4 SolzG percentage rates are
    # non-negative legal parameters. Validate them before the ordered capital
    # sequence so impossible inputs cannot silently invert the statutory math.
    _require_non_negative_decimal(
        inputs.stock_loss_carryforward_2024_eur,
        label="stock_loss_carryforward_2024_eur",
    )
    _require_non_negative_decimal(inputs.saver_allowance_eur, label="saver_allowance_eur")
    _require_unit_interval(inputs.capital_tax_rate, label="capital_tax_rate")
    _require_unit_interval(inputs.soli_rate, label="soli_rate")
    _require_non_negative_decimal(inputs.treaty_dividend_credit_eur, label="treaty_dividend_credit_eur")
    seen_certificate_ids: set[str] = set()
    for certificate in inputs.bank_certificates:
        # § 20 EStG certificate line 8 is only the stock-sale subset of line 7.
        # The typed certificate is validated before the ordered capital sequence so a
        # malformed bank certificate cannot double-count capital income.
        if not str(certificate.owner_slot).strip():
            raise ValueError("Germany bank certificate owner_slot is required.")
        certificate_id = str(certificate.certificate_id).strip()
        if not certificate_id:
            raise ValueError("Germany bank certificate certificate_id is required.")
        if certificate_id in seen_certificate_ids:
            raise ValueError(f"Duplicate Germany bank certificate certificate_id: {certificate_id}")
        seen_certificate_ids.add(certificate_id)
        for label, value in (
            ("kap_line_7_income_eur", certificate.kap_line_7_income_eur),
            ("kap_line_8_stock_gains_eur", certificate.kap_line_8_stock_gains_eur),
            ("kap_line_17_saver_allowance_used_eur", certificate.kap_line_17_saver_allowance_used_eur),
            ("kap_line_37_kest_withheld_eur", certificate.kap_line_37_kest_withheld_eur),
            ("kap_line_38_soli_withheld_eur", certificate.kap_line_38_soli_withheld_eur),
            ("kap_line_40_foreign_tax_credited_eur", certificate.kap_line_40_foreign_tax_credited_eur),
            ("kap_line_41_foreign_tax_not_credited_eur", certificate.kap_line_41_foreign_tax_not_credited_eur),
        ):
            _require_non_negative_decimal(value, label=label)
        if q2(certificate.kap_line_8_stock_gains_eur) > q2(certificate.kap_line_7_income_eur):
            raise ValueError("kap_line_8_stock_gains_eur cannot exceed kap_line_7_income_eur.")
    seen_treaty_item_ids: set[str] = set()
    for item in inputs.treaty_dividend_items:
        # DBA-USA Art. 10 is dividend-only relief. DBA-USA Art. 23(5)(a) then routes
        # the treaty-limited U.S. source tax through Germany's § 32d Abs. 5 EStG
        # credit cap (Germany credits only the treaty-permitted U.S. tax for a
        # U.S. citizen resident in Germany). Reject ambiguous or non-dividend items before the capital
        # sequence so stock-sale gains cannot receive dividend treaty treatment.
        item_id = str(item.item_id).strip()
        if not item_id:
            raise ValueError("Germany U.S.-source treaty dividend item_id is required.")
        if item_id in seen_treaty_item_ids:
            raise ValueError(f"Duplicate Germany U.S.-source treaty dividend item_id: {item_id}")
        seen_treaty_item_ids.add(item_id)
        if not str(item.owner_slot).strip():
            raise ValueError("Germany U.S.-source treaty dividend owner_slot is required.")
        dividend_class = str(item.dividend_class).strip().lower()
        if dividend_class not in GERMANY_US_TREATY_DIVIDEND_CLASSES_2025:
            raise ValueError(f"Unsupported U.S.-source treaty dividend class: {item.dividend_class!r}")
        for label, value in (
            ("gross_dividend_eur", item.gross_dividend_eur),
            ("german_taxable_dividend_eur", item.german_taxable_dividend_eur),
            ("allocated_us_tax_paid_eur", item.allocated_us_tax_paid_eur),
        ):
            _require_non_negative_decimal(value, label=label)
        _require_unit_interval(item.treaty_rate, label="treaty_rate")
        if q2(item.treaty_rate) != GERMANY_US_TREATY_PORTFOLIO_DIVIDEND_RATE:
            raise NotImplementedError(
                "Only the 15% Germany-U.S. treaty portfolio-dividend rate is implemented."
            )
        if q2(item.german_taxable_dividend_eur) > q2(item.gross_dividend_eur):
            raise ValueError("german_taxable_dividend_eur cannot exceed gross_dividend_eur.")
        if q2(item.allocated_us_tax_paid_eur) > q2(item.gross_dividend_eur):
            raise ValueError("allocated_us_tax_paid_eur cannot exceed gross_dividend_eur.")


def compute_germany_capital_assessment_2025(
    inputs: GermanyCapitalAssessmentInputs2025,
    *,
    derived_facts: Mapping[str, Any] | None = None,
) -> GermanyCapitalAssessment2025:
    # Phase 2 of the engine restructure: this function is now a thin wrapper
    # around the Germany capital rule graph. The legal arithmetic lives in
    # tax_pipeline/y2025/germany_capital_rules.py per-stage calculate functions
    # for DE25-13 through DE25-21. The dataclass is preserved as a typed view
    # (option (i) per ENGINE-RESTRUCTURE-PLAN.md) so existing form renderers
    # and tests continue to work unchanged.
    #
    # ``derived_facts`` is the Pipeline 1 → Pipeline 2 boundary state that
    # ``germany_capital_initial_facts_2025`` would otherwise read from disk
    # (``derived-facts.json``). Production callers (``run_year`` →
    # ``germany_model.py``) leave it ``None`` and rely on the on-disk
    # artifact. Test callers that bypass ``run_year`` synthesize the
    # boundary via ``tests/_germany_derived_facts.py:
    # germany_derived_facts_for_inputs`` and pass the result through. F-A4
    # (architecture review, ``.review/2026-05-01-final/architecture.md``)
    # removed the in-memory Pipeline 1 fallback that previously hid this
    # boundary inside production code.
    from tax_pipeline.y2025.germany_capital_rules import (
        execute_germany_capital_rule_graph,
        germany_capital_assessment_from_final_facts,
        germany_capital_initial_facts_2025,
        germany_capital_initial_fingerprints_2025,
    )

    _validate_germany_capital_inputs_2025(inputs)
    initial_facts = germany_capital_initial_facts_2025(
        inputs, derived_facts=derived_facts
    )
    execution = execute_germany_capital_rule_graph(
        initial_facts,
        input_fingerprints=germany_capital_initial_fingerprints_2025(initial_facts),
    )
    return germany_capital_assessment_from_final_facts(execution.final_facts, inputs=inputs)



def compute_joint_ordinary_assessment_2025(
    inputs: JointOrdinaryInputs2025,
    *,
    children_disability_pauschbetrag_total_eur: Decimal = D("0.00"),
    disability_pauschbetrag_transfer_split: tuple[Decimal, ...] | None = None,
) -> JointOrdinaryAssessment2025:
    # Phase 3 of the engine restructure: this function is now a thin wrapper
    # around the Germany ordinary rule graph. The legal arithmetic lives in
    # tax_pipeline/y2025/germany_ordinary_rules.py per-stage calculate functions
    # for DE25-00 through DE25-10. The dataclass is preserved as a typed view
    # (option (i)) so existing form renderers, ELSTER projections, and tests
    # continue to work unchanged. Filing posture is an input fact; every
    # taxpayer runs the same 12 declared stages in the same order.
    #
    # Gap 2 — § 33b Abs. 5 EStG transferral: callers thread the Pipeline 1
    # derived ``de.derived.children_disability_pauschbetrag_total_eur``
    # through this thin wrapper into the ordinary graph; the default zero
    # keeps legacy test fixtures (no children) byte-identical.
    from tax_pipeline.y2025.germany_ordinary_rules import (
        execute_germany_ordinary_rule_graph,
        germany_ordinary_assessment_from_final_facts,
        germany_ordinary_initial_facts_2025,
        germany_ordinary_initial_fingerprints_2025,
    )

    initial_facts = germany_ordinary_initial_facts_2025(
        inputs,
        children_disability_pauschbetrag_total_eur=(
            children_disability_pauschbetrag_total_eur
        ),
        disability_pauschbetrag_transfer_split=(
            disability_pauschbetrag_transfer_split
        ),
    )
    execution = execute_germany_ordinary_rule_graph(
        initial_facts,
        input_fingerprints=germany_ordinary_initial_fingerprints_2025(initial_facts),
    )
    return germany_ordinary_assessment_from_final_facts(execution.final_facts, inputs=inputs)


@dataclass(frozen=True)
class GermanyChildrenAssessment2025:
    """Typed view of the executed § 31 EStG Familienleistungsausgleich sub-graph.

    Surfaced as the result of ``compute_germany_children_assessment_2025``
    so the call site in ``germany_model.main()`` (and the analogous test
    wrappers) can pass three deterministic scalars into
    ``germany_final_initial_facts_2025`` without poking inside the
    children sub-graph's ``RuleGraphExecution.final_facts`` mapping.

    Authority: § 31 EStG (Familienleistungsausgleich, Günstigerprüfung) /
    § 32 Abs. 6 EStG (Kinderfreibetrag + BEA-Freibetrag) / BKGG § 6
    Abs. 2 (Kindergeld monthly amount). The chosen relief value is
    consumed by DE25-22-FINAL-REFUND under § 31 Satz 4 EStG netting.
    https://www.gesetze-im-internet.de/estg/__31.html
    """

    applied_relief_eur: Decimal
    guenstigerpruefung_choice: str
    kindergeld_total_eur: Decimal
    qualifying_children_count: int
    # C5 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the § 32 Abs. 6 EStG total
    # Kinderfreibetrag + BEA-Freibetrag for the household (sum across
    # all qualifying children). Surfaced from the
    # ``DE25-CHILDREN-CREDITS`` rule output
    # ``de.children.kinderfreibetrag_total_eur``. Lands on Anlage Kind
    # 2025 — the per-child Kinderfreibetrag/BEA Zeilen render via this
    # household total when ``qualifying_children_count >= 1``; for the
    # zero-children posture the value is 0.00 and the renderer emits an
    # explicit zero row + posture note (CLAUDE.md fail-closed posture).
    # https://www.gesetze-im-internet.de/estg/__32.html
    kinderfreibetrag_total_eur: Decimal
    # § 31 EStG Satz 1 Günstigerprüfung counterfactual tariff saving —
    # ``tariff_at_zve - tariff_at_zve_minus_kinderfreibetrag`` from
    # DE25-CHILDREN-CREDITS. Audit cross-check; not directly rendered
    # on a single Anlage Kind line, but surfaces in the package index
    # so reviewers can see why Kindergeld vs. Kinderfreibetrag was
    # chosen.
    kinderfreibetrag_tax_saving_eur: Decimal
    # § 33b Abs. 5 EStG transferred Pauschbetrag (Gap 2). Surfaced from
    # the ``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` audit stage. Equals
    # the Pipeline 1 derivation (consumed by DE25-BEHINDERUNG-
    # PAUSCHBETRAG) by construction — both stages read the same
    # aggregator. https://www.gesetze-im-internet.de/estg/__33b.html
    disability_pauschbetrag_transferred_eur: Decimal


def compute_germany_children_assessment_2025(
    *,
    ordinary_taxable_income_eur: Decimal,
    ordinary_income_tax_eur: Decimal,
    filing_posture: str,
    derived_facts: Mapping[str, Any] | None = None,
) -> GermanyChildrenAssessment2025:
    """Wave 11A: thin wrapper around the children sub-graph rule graph.

    Mirrors ``compute_germany_capital_assessment_2025`` — production
    callers (``run_year`` → ``germany_model.py``) leave ``derived_facts``
    None and rely on the on-disk ``derived-facts.json`` artifact; test
    callers that bypass ``run_year`` synthesize the boundary in-memory
    and forward it through. F-A4 (architecture review,
    ``.review/2026-05-01-final/architecture.md``) requires the
    Pipeline 1 → Pipeline 2 boundary state to travel either through
    ``derived_facts`` or ``derived-facts.json`` — never via an
    in-memory fallback inside production code.

    The returned ``GermanyChildrenAssessment2025`` carries exactly the
    three scalars DE25-22-FINAL-REFUND consumes under § 31 Satz 4 EStG
    plus the qualifying-children count for audit cross-check.
    """
    from tax_pipeline.y2025.germany_children_rules import (
        execute_germany_children_rule_graph,
        germany_children_initial_facts_2025,
        germany_children_initial_fingerprints_2025,
    )

    initial_facts = germany_children_initial_facts_2025(
        derived_facts=derived_facts,
        ordinary_taxable_income_eur=ordinary_taxable_income_eur,
        ordinary_income_tax_eur=ordinary_income_tax_eur,
        filing_posture=filing_posture,
    )
    execution = execute_germany_children_rule_graph(
        initial_facts,
        input_fingerprints=germany_children_initial_fingerprints_2025(
            initial_facts
        ),
    )
    final_facts = execution.final_facts
    return GermanyChildrenAssessment2025(
        applied_relief_eur=Decimal(
            str(final_facts["de.children.applied_relief_eur"])
        ),
        guenstigerpruefung_choice=str(
            final_facts["de.children.guenstigerpruefung_choice"]
        ),
        kindergeld_total_eur=Decimal(
            str(final_facts["de.children.kindergeld_total_eur"])
        ),
        qualifying_children_count=int(
            final_facts["de.children.qualifying_children_count"]
        ),
        kinderfreibetrag_total_eur=Decimal(
            str(final_facts["de.children.kinderfreibetrag_total_eur"])
        ),
        kinderfreibetrag_tax_saving_eur=Decimal(
            str(final_facts["de.children.kinderfreibetrag_tax_saving_eur"])
        ),
        disability_pauschbetrag_transferred_eur=Decimal(
            str(
                final_facts["de.children.disability_pauschbetrag_transferred_eur"]
            )
        ),
    )


