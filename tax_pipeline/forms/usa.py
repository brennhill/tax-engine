from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from tax_pipeline.core.legal_value import LegalValue
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
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import final_legal_output_path, load_final_legal_output_2025
from tax_pipeline.postures import get_posture_definition
from tax_pipeline.y2025.us_law import (
    CFR_1_6038D_2_URL,
    CFR_31_1010_350_URL,
    FBAR_AGGREGATE_THRESHOLD_USD,
    FINCEN_BSA_EFILING_URL,
    IRS_ABOUT_FORM_1116_URL,
    IRS_ABOUT_FORM_8960_URL,
    IRS_ABOUT_SCHEDULE_2_URL,
    IRS_ABOUT_SCHEDULE_3_URL,
    IRS_FORM_2555_URL,
    IRS_FORM_8833_URL,
    IRS_FORM_8938_URL,
    IRS_FORM_8938_VS_FBAR_URL,
    IRS_FORM_8959_URL,
    IRS_P514,
    IRS_SCHEDULE_C_URL,
    IRS_SCHEDULE_SE_URL,
    SCH_8812_INSTRUCTIONS_URL,
    USC_24_URL,
    USC_31_5314_URL,
    USC_911_URL,
    USC_6038D_URL,
)

D = Decimal
SUPPORTED_YEAR = 2025
# Proposal 2 (architecture review 2026-05-04): country tag sourced
# from the jurisdiction registry. See forms/germany.py for the
# rationale; same lazy-but-import-time pattern applies here.
from tax_pipeline.jurisdictions import get_jurisdiction as _get_jurisdiction

USA_COUNTRY = _get_jurisdiction("US").code


def _ensure_supported_year(paths: YearPaths) -> None:
    if paths.year != SUPPORTED_YEAR:
        raise NotImplementedError(f"U.S. forms renderer currently supports {SUPPORTED_YEAR} only, got {paths.year}")


def required_usa_form_paths(paths: YearPaths) -> list[Path]:
    return [final_legal_output_path(paths)]


def _row_decimal(row: dict[str, str], key: str) -> Decimal:
    return D(row[key])


def _required_trace_step(rows: list[dict[str, str]], step: str) -> dict[str, str]:
    matches = [row for row in rows if row["step"] == step]
    if not matches:
        raise FileNotFoundError(f"Missing required row {step} in us-tax-trace.csv")
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one row for {step} in us-tax-trace.csv")
    return matches[0]


def _required_key_row(rows: list[dict[str, str]], key: str, source_name: str) -> dict[str, str]:
    matches = [row for row in rows if row.get("key") == key]
    if not matches:
        raise FileNotFoundError(f"Missing required row {key} in {source_name}")
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one row for {key} in {source_name}")
    return matches[0]


def _usa_posture_from_treaty_packet(treaty: dict) -> str:
    filing_status = str(treaty["chosen_position"]["filing_status"]).strip().lower()
    spouse_name = str(treaty["chosen_position"].get("nra_spouse_name", "")).strip()
    if filing_status == "single":
        return "single"
    if filing_status == "married filing separately":
        return "mfs_nra_spouse" if spouse_name else "married_separate"
    if filing_status == "married filing jointly":
        return "married_joint"
    raise NotImplementedError(f"Unsupported U.S. filing status label {treaty['chosen_position']['filing_status']!r}.")


def _write_index(paths: YearPaths, treaty: dict, tax_estimate: dict) -> None:
    baseline = tax_estimate["payments"]["refund_if_positive_else_balance_due_usd"]
    treaty_refund = tax_estimate["payments"]["refund_if_positive_else_balance_due_with_treaty_resourcing_usd"]
    form_8833_required = str(treaty["chosen_position"].get("form_8833_required", "no")).strip().lower() == "yes"
    # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): list the FATCA /
    # FBAR status sheets in the index when the rule graph emitted a
    # ``fatca_fbar`` block (always present after Group D landed). The
    # sheets always render — either with a determination or a
    # MANUAL DETERMINATION REQUIRED posture — so the index always
    # links them when the block exists.
    fatca_fbar_listed = bool(tax_estimate.get("fatca_fbar"))
    # B3 — Form 8959 is gated on Schedule 2 line 11 > 0 (Additional
    # Medicare Tax attaches). When zero, the form file is not written
    # and the index does not list it.
    form_8959_attaches = D(
        str(
            treaty.get("form_8959", {}).get("line_18_total_addtl_medicare_usd", "0.00")
        )
    ) > D("0.00")
    # B4 — Schedule SE is gated on net SE earnings > 0. When the
    # supported posture has no SE income, the form is not written.
    schedule_se_renders = D(
        str(treaty.get("schedule_se", {}).get("line_2_net_se_earnings_usd", "0.00"))
    ) > D("0.00")
    lines = [
        f"# U.S. Forms Package - {paths.year}",
        "",
        f"Final modeled result: **{result_phrase(treaty_refund, 'USD')}**.",
        "",
        # Filing-guide pointer (rendered after the per-form files so the
        # walkthrough can reflect actual rendered form contents). The
        # link is a stable filename: ``FILING-GUIDE.md`` lives next to
        # the per-form Markdown in this directory.
        f"**Start here:** {markdown_link('FILING-GUIDE.md', 'FILING-GUIDE.md')} — step-by-step walkthrough for typing this return into IRS Free File / preparer software. The per-form files below are the underlying references.",
        "",
        "## Filing posture",
        f"- Filing status: `{treaty['chosen_position']['filing_status']}`",
        f"- Joint-return spouse: `{treaty['chosen_position'].get('joint_return_spouse_name', '')}`",
        f"- Explicit NRA-spouse joint-return election: `{treaty['chosen_position'].get('joint_return_with_nra_spouse_election', 'no')}`",
        f"- FTC method: `{treaty['chosen_position']['ftc_method']}`",
        f"- Treaty re-sourcing claimed: `{treaty['chosen_position']['treaty_resourcing_claimed']}`",
        f"- Form 8833 required: `{treaty['chosen_position']['form_8833_required']}`",
        "",
        "## Locked result snapshot",
        f"- Baseline result without treaty re-sourcing: `{result_phrase(baseline, 'USD')}`",
        f"- Chosen treaty re-sourcing result: `{result_phrase(treaty_refund, 'USD')}`",
        f"- Schedule 3 foreign tax credit in the chosen posture: `{format_currency(treaty['headline']['schedule3_total_foreign_tax_credit_usd'], 'USD')}`",
        f"- Schedule 2 additional tax in the chosen posture: `{format_currency(treaty['headline']['schedule2_total_additional_tax_usd'], 'USD')}`",
        "",
        "## Form Files",
        f"- {markdown_link(f'{paths.year}_1040.md', f'{paths.year}_1040.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_1.md', f'{paths.year}_schedule_1.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_b.md', f'{paths.year}_schedule_b.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_d.md', f'{paths.year}_schedule_d.md')}",
        f"- {markdown_link(f'{paths.year}_form_8949.md', f'{paths.year}_form_8949.md')}",
        f"- {markdown_link(f'{paths.year}_form_6781.md', f'{paths.year}_form_6781.md')}",
        f"- {markdown_link(f'{paths.year}_form_6251.md', f'{paths.year}_form_6251.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_2.md', f'{paths.year}_schedule_2.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_3.md', f'{paths.year}_schedule_3.md')}",
        f"- {markdown_link(f'{paths.year}_schedule_8812.md', f'{paths.year}_schedule_8812.md')}",
        # B4 — Schedule SE listing gated on net SE earnings > 0.
        *(
            [f"- {markdown_link(f'{paths.year}_schedule_se.md', f'{paths.year}_schedule_se.md')}"]
            if schedule_se_renders
            else []
        ),
        # B3 — Form 8959 listing is gated on Additional Medicare > 0.
        *(
            [f"- {markdown_link(f'{paths.year}_form_8959.md', f'{paths.year}_form_8959.md')}"]
            if form_8959_attaches
            else []
        ),
        f"- {markdown_link(f'{paths.year}_form_8960.md', f'{paths.year}_form_8960.md')}",
        f"- {markdown_link(f'{paths.year}_form_1116_passive.md', f'{paths.year}_form_1116_passive.md')}",
        f"- {markdown_link(f'{paths.year}_form_1116_general.md', f'{paths.year}_form_1116_general.md')}",
        # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): separate Form 1116 for
        # § 904(d)(6) treaty-resourced basket. The renderer always
        # writes ``2025_form_1116_resourced.md`` (the underlying Pub.
        # 514 worksheet runs on every workspace), so the index always
        # links it.
        f"- {markdown_link(f'{paths.year}_form_1116_resourced.md', f'{paths.year}_form_1116_resourced.md')}",
        # 26 U.S.C. § 6114 / Reg. § 301.6114-1 — Form 8833 listing is
        # gated on the executed TREATY25-LOB-QUALIFICATION rule output;
        # the file is only rendered (and only listed here) when the
        # taxpayer claims treaty re-sourcing AND qualifies under one of
        # the five DBA-USA Art. 28 LOB paragraphs.
        *(
            [f"- {markdown_link(f'{paths.year}_form_8833.md', f'{paths.year}_form_8833.md')}"]
            if form_8833_required
            else []
        ),
        # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): FATCA Form 8938 /
        # FBAR FinCEN 114 filing-determination status sheets — listed
        # whenever the rule emitted a ``fatca_fbar`` block (always true
        # after Group D landed; the sheets surface either a
        # determination or a MANUAL DETERMINATION REQUIRED posture).
        # https://www.law.cornell.edu/uscode/text/26/6038D
        # https://www.law.cornell.edu/cfr/text/31/1010.350
        *(
            [
                f"- {markdown_link(f'{paths.year}_form_8938_status.md', f'{paths.year}_form_8938_status.md')}",
                f"- {markdown_link(f'{paths.year}_fincen_114_status.md', f'{paths.year}_fincen_114_status.md')}",
            ]
            if fatca_fbar_listed
            else []
        ),
        "",
        "## Source Files",
        "- `final-legal-output.json`",
    ]
    (paths.usa_forms_root / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_1040(paths: YearPaths, treaty: dict, provenance: Mapping[str, Any] | None) -> None:
    form = treaty["form_1040"]
    filing_status = treaty["chosen_position"]["filing_status"]
    spouse_name = treaty["chosen_position"].get("nra_spouse_name", "")
    joint_return_spouse_name = treaty["chosen_position"].get("joint_return_spouse_name", "")
    elected_joint_with_nra_spouse = treaty["chosen_position"].get("joint_return_with_nra_spouse_election", "no") == "yes"
    digital_assets_checkbox = treaty["chosen_position"].get("digital_assets_checkbox", "Yes")
    line_37_amount_owed = D(str(form.get("line_37_amount_owed_usd", "0.00")))
    posture_line = (
        "Chosen filing posture is married filing separately with the NRA spouse listed by name."
        if spouse_name
        else (
            f"Chosen filing posture is married filing jointly under an explicit NRA-spouse joint-return election for {joint_return_spouse_name}."
            if elected_joint_with_nra_spouse
            else f"Chosen filing posture is {filing_status.lower()}."
        )
    )

    def lv_form(line_key: str) -> FormEntry:  # closure over form / provenance
        # Ensure form-line keys are in the JSON before adapter access; missing
        # keys here are projection drift, which the adapter surfaces as KeyError.
        return legal_value_from_dict(
            form,
            line_key,
            country=USA_COUNTRY,
            section="form_1040",
            provenance=provenance,
        )

    schema = load_form_schema("form_1040")
    write_form(
        paths.usa_forms_root / f"{paths.year}_1040.md",
        f"{paths.year} {schema.display_name}",
        [
            posture_line,
            "This file reflects the treaty re-sourcing scenario selected for the saved 2025 package.",
        ],
        [
            FormEntry(schema.label("filing_status_label"), filing_status, source="us-treaty-package.json"),
            *(
                [FormEntry(schema.label("spouse_name_mfs_label"), spouse_name, source="us-treaty-package.json")]
                if spouse_name
                else []
            ),
            *(
                [
                    FormEntry(
                        schema.label("joint_return_spouse_label"),
                        joint_return_spouse_name,
                        source="us-treaty-package.json",
                        notes="Included on the return under the explicit NRA-spouse joint-return election.",
                    )
                ]
                if elected_joint_with_nra_spouse
                else []
            ),
            FormEntry(
                schema.label("digital_assets_checkbox_label"),
                digital_assets_checkbox,
                source="us-treaty-package.json",
                notes="Reflects whether digital-asset sales or staking were present in the current year workspace.",
            ),
            legal_value_entry(schema.label("1h"), lv_form("line_1h_other_earned_income_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Foreign wages shown in the current filing posture."),
            legal_value_entry(schema.label("1z"), lv_form("line_1z_total_wages_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Total wages under the current filing posture."),
            legal_value_entry(schema.label("2b"), lv_form("line_2b_taxable_interest_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("3a"), lv_form("line_3a_qualified_dividends_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("3b"), lv_form("line_3b_ordinary_dividends_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("7"), lv_form("line_7a_capital_gain_or_loss_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Capital result carried from Schedule D after the current filing posture's annual capital-loss limit."),
            legal_value_entry(schema.label("8"), lv_form("line_8_schedule_1_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("11"), lv_form("line_11_agi_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("12"), lv_form("line_12e_standard_deduction_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("15"), lv_form("line_15_taxable_income_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            legal_value_entry(schema.label("16"), lv_form("line_16_tax_usd"), currency=Currency.USD, source="us-treaty-package.json"),
            # F-US-1 / IRS-VERIFIED 2026-05-10 — Form 1040 line 17 ← Schedule 2
            # line 3 per https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
            # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) Part I per
            # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf: lines 1a-1f/1y/1z =
            # additions to tax; line 2 = AMT (Form 6251 line 11);
            # line 3 = line 1z + line 2. AMT moved from Schedule 2 line 1
            # (2024) to line 2 (2025) per https://www.irs.gov/instructions/i6251.
            # https://www.law.cornell.edu/uscode/text/26/55
            legal_value_entry(schema.label("17"), lv_form("line_17_amt_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Amount from Schedule 2 line 3 (Part I total = line 1z additions to tax: APTC, clean-vehicle credit repayments, Form 4255 EPE recapture + line 2 AMT under 26 U.S.C. § 55, Form 6251 line 11; supported posture has zero line-1z additions)."),
            # 26 U.S.C. § 24(b) — nonrefundable Child Tax Credit + § 24(h)(4)
            # ODC. Schedule 8812 line 14 carries to Form 1040 line 19. Sourced
            # from ``us.ctc.nonrefundable_portion_usd`` via the treaty packet's
            # form_1040 projection. https://www.law.cornell.edu/uscode/text/26/24
            # IRS-VERIFIED 2026-05-10 — Schedule 8812 line 14 → Form 1040 line 19
            # per https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
            legal_value_entry(schema.label("19"), lv_form("line_19_ctc_odc_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Nonrefundable § 24 CTC + § 24(h)(4) ODC from Schedule 8812 line 14."),
            legal_value_entry(schema.label("20"), lv_form("line_20_schedule_3_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Schedule 3 total in the treaty re-sourcing posture."),
            # A2 (FORM-MAPPING-FOLLOWUP): Form 1040 line 22 — tax after
            # nonrefundable credits = line 18 minus line 21. Sourced from the
            # executed ``us.tax.line_22_after_credits_with_treaty_resourcing_usd``
            # rule output. Authority: Form 1040 instructions (2025) line 22.
            # https://www.irs.gov/instructions/i1040gi
            # IRS-VERIFIED 2026-05-10 — Form 1040 line 22 = line 18 minus line 21
            # per https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
            legal_value_entry(schema.label("22"), lv_form("line_22_after_credits_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Tax after nonrefundable credits (line 18 minus line 21); 26 U.S.C. § 24(b)(3) ordering."),
            # IRS-VERIFIED 2026-05-10 — Schedule 2 line 21 → Form 1040 line 23 per
            # https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
            # and https://www.irs.gov/forms-pubs/correction-to-2024-schedule-2-form-1040-line-21
            legal_value_entry(schema.label("23"), lv_form("line_23_schedule_2_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Schedule 2 line 21 (Part II — Other Taxes: SE + Additional Medicare + NIIT). Per Form 1040 instructions, line 23 carries Schedule 2 Part II only; the Part I AMT total is on line 17."),
            legal_value_entry(schema.label("26"), lv_form("line_26_estimated_payments_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="User-confirmed payment already sent."),
            # 26 U.S.C. § 24(d) — refundable Additional Child Tax Credit.
            # Schedule 8812 line 27 carries to Form 1040 line 28; capped at
            # $1,700 per qualifying child for 2025 (Rev. Proc. 2024-40 § 3.05;
            # OBBBA-preserved cap) and the § 24(d)(1)(B) earned-income phase-in.
            # https://www.law.cornell.edu/uscode/text/26/24
            # IRS-VERIFIED 2026-05-10 — Schedule 8812 line 27 → Form 1040 line 28
            # per https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
            legal_value_entry(schema.label("28"), lv_form("line_28_refundable_actc_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Refundable ACTC from Schedule 8812 line 27 (§ 24(d))."),
            legal_value_entry(schema.label("35a"), lv_form("line_35a_refund_usd"), currency=Currency.USD, source="us-treaty-package.json", notes="Refund amount; zero when the chosen treaty posture has a balance due."),
            *(
                [
                    legal_value_entry(
                        schema.label("37"),
                        legal_value_from_decimal(
                            line_37_amount_owed,
                            country=USA_COUNTRY,
                            section="form_1040",
                            output_key="line_37_amount_owed_usd",
                            provenance=provenance,
                        ),
                        currency=Currency.USD,
                        source="us-treaty-package.json",
                        notes="Amount owed in the chosen treaty re-sourcing posture.",
                    )
                ]
                if line_37_amount_owed > D("0.00")
                else []
            ),
        ],
        [
            # IRS-VERIFIED 2026-05-11 — Form 1040 (2025) line 1h = "Other
            # earned income (see instructions). Enter type and amount" per
            # https://www.irs.gov/pub/irs-pdf/f1040.pdf.
            "If software presents foreign wages through a statement-backed foreign-employer-compensation flow instead of literal line 1h, keep the total wages unchanged.",
        ],
    )


def _write_schedule_1(paths: YearPaths, capital_results: dict, provenance: Mapping[str, Any] | None) -> None:
    income = capital_results["income"]
    schema = load_form_schema("schedule_1")

    def lv_income(key: str) -> LegalValue:
        return legal_value_from_dict(
            income, key, country=USA_COUNTRY, section="capital_results.income", provenance=provenance,
        )

    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_1.md",
        f"{paths.year} {schema.display_name}",
        [
            "Only the populated other-income line and its supporting statement items are shown.",
        ],
        [
            legal_value_entry(schema.label("8z_total"), lv_income("schedule_1_other_income_total_usd"), currency=Currency.USD, source="us-capital-results.json"),
            legal_value_entry(schema.label("8z_substitute_payments"), lv_income("substitute_payments_usd"), currency=Currency.USD, source="us-capital-results.json", notes="Payments in lieu of dividends / interest."),
            legal_value_entry(schema.label("8z_staking_income"), lv_income("staking_income_usd"), currency=Currency.USD, source="us-capital-results.json", notes="Digital-asset staking income."),
        ],
        [
            "Supporting split also appears in `us-supporting-statements.md`.",
        ],
    )


def _write_schedule_b(paths: YearPaths, capital_results: dict, provenance: Mapping[str, Any] | None) -> None:
    # IRS Form 1040 Instructions / Schedule B Instructions (Workstream 5):
    # Schedule B is required when interest > $1,500 OR ordinary dividends
    # > $1,500 OR a foreign account exists. The foreign-account trigger
    # (Schedule B Part III) is always set for the U.S.-citizen-in-Germany
    # posture (Sparkasse / Comdirect / etc.). The render is therefore
    # conditional on the predicate; for the demo posture the German bank
    # account always triggers Part III, so Schedule B is always rendered.
    # https://www.irs.gov/instructions/i1040gi
    # https://www.irs.gov/forms-pubs/about-schedule-b-form-1040
    from tax_pipeline.y2025.us_law import (
        schedule_b_parts_required_2025,
        schedule_b_required_2025,
    )

    income = capital_results["income"]
    interest = D(str(income.get("interest_income_usd", "0")))
    dividends = D(str(income.get("ordinary_dividends_usd", "0")))
    # The German-employer wage / Sparkasse / Comdirect posture in the
    # demo workspace ALWAYS has a foreign account; the bank-certificate
    # facts are loaded into capital_results as such. Detect via the
    # presence of any non-zero foreign-account-related income or rely on
    # the explicit ``has_foreign_account`` flag if present in the
    # capital_results income block (default True for the cross-border
    # filing posture, which is the only modeled posture here).
    has_foreign_account = bool(
        income.get("has_foreign_account", True)
    )
    if not schedule_b_required_2025(
        interest_income_usd=interest,
        ordinary_dividends_usd=dividends,
        has_foreign_account=has_foreign_account,
    ):
        # Below the $1,500 thresholds with no foreign account — Schedule
        # B is not required. Skip rendering entirely.
        return

    def lv_income(key: str) -> LegalValue:
        return legal_value_from_dict(
            income, key, country=USA_COUNTRY, section="capital_results.income", provenance=provenance,
        )

    part_i, part_ii, part_iii = schedule_b_parts_required_2025(
        interest_income_usd=interest,
        ordinary_dividends_usd=dividends,
        has_foreign_account=has_foreign_account,
    )
    schema = load_form_schema("schedule_b")
    entries: list[FormEntry] = []
    posture_lines: list[str] = []
    if part_i:
        posture_lines.append("Part I (Interest) is required: interest exceeds $1,500 or a foreign account exists.")
        entries.append(
            legal_value_entry(
                schema.label("2"),
                lv_income("interest_income_usd"),
                currency=Currency.USD,
                source="us-capital-results.json",
                notes="Taxable interest (Schedule B Part I).",
            )
        )
    if part_ii:
        posture_lines.append("Part II (Dividends) is required: ordinary dividends exceed $1,500.")
        entries.append(
            legal_value_entry(
                schema.label("5"),
                lv_income("ordinary_dividends_usd"),
                currency=Currency.USD,
                source="us-capital-results.json",
                notes="Ordinary dividends (Schedule B Part II).",
            )
        )
    if part_iii:
        posture_lines.append(
            "Part III (Foreign Accounts) is required: a German bank account "
            "(Sparkasse / Comdirect / etc.) is present. The separate FATCA "
            "Form 8938 (§ 6038D) and FBAR / FinCEN 114 (31 CFR § 1010.350) "
            "filing determinations are surfaced in "
            f"`{paths.year}_form_8938_status.md` and "
            f"`{paths.year}_fincen_114_status.md`."
        )
        entries.append(
            FormEntry(
                schema.label("7a_foreign_account_checkbox"),
                "Yes",
                source="us-capital-results.json",
                notes="Foreign account is present; Schedule B Part III always required.",
            )
        )
    if not posture_lines:
        posture_lines.append("Use the Schwab 1099 totals already carried into the treaty package.")
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_b.md",
        f"{paths.year} {schema.display_name}",
        posture_lines,
        entries,
        [
            # IRS-VERIFIED 2026-05-11 — Form 1040 (2025) line 3a = "Qualified
            # dividends" and Schedule B (2025) Part II line 5 = "List name of
            # payer" for ordinary dividends; line 6 carries to Form 1040 line
            # 3b. https://www.irs.gov/pub/irs-pdf/f1040.pdf
            # https://www.irs.gov/pub/irs-pdf/f1040sb.pdf
            "Qualified dividends remain on Form 1040 line 3a, not Schedule B line 5.",
        ],
    )


def _required_schedule_d_entries(forms: dict) -> list[FormEntry]:
    projected = forms.get("schedule_d_entries")
    if not isinstance(projected, list):
        raise FileNotFoundError("Missing U.S. final legal output field: schedule_d_entries")
    entries: list[FormEntry] = []
    for index, entry in enumerate(projected, start=1):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid U.S. final legal output field: schedule_d_entries[{index}]")
        missing = [key for key in ("line", "value", "source", "notes") if key not in entry]
        if missing:
            raise FileNotFoundError(
                "Missing U.S. final legal output field: "
                + ", ".join(f"schedule_d_entries[{index}].{key}" for key in missing)
            )
        entries.append(FormEntry(entry["line"], entry["value"], source=entry["source"], notes=entry["notes"]))
    return entries


def _write_schedule_d(paths: YearPaths, schedule_d_entries: list[FormEntry]) -> None:
    schema = load_form_schema("schedule_d")
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_d.md",
        f"{paths.year} {schema.display_name}",
        [
            "This schedule aggregates the direct broker rows, attached Form 8949 rows, capital gain distributions, and the Form 6781 section 1256 split.",
        ],
        schedule_d_entries,
        [
            "The detailed lot buckets remain in `us-form-8949-income-buckets.csv` and `us-capital-results.json`.",
        ],
    )


def _write_form_8949(paths: YearPaths, bucket_rows: list[dict[str, str]], provenance: Mapping[str, Any] | None) -> None:
    relevant = [
        row for row in bucket_rows
        if row["form"] in {"Form 8949", "Form 8949 / Schedule D"}
    ]
    order = {
        "Part I Box A": 0,
        "Part I Box B": 1,
        "Part I Box H": 2,
        "Part II Box D": 3,
        "Part II Box K": 4,
    }
    relevant.sort(key=lambda row: order.get(row["line_or_bucket"], 99))
    schema = load_form_schema("form_8949")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_8949.md",
        f"{paths.year} {schema.display_name}",
        [
            "Use the saved bucket totals and attach detail only for the rows that require it.",
        ],
        [
            legal_value_entry(
                row["line_or_bucket"],
                legal_value_from_dict(
                    row, "amount_usd",
                    country=USA_COUNTRY,
                    section=f"form_8949.{row['line_or_bucket']}",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-form-8949-income-buckets.csv",
                notes=row["note"],
            )
            for row in relevant
        ],
        [
            "Attach detailed broker / exchange support for any rows that were not reported with basis to the IRS.",
        ],
    )


def _write_form_6781(paths: YearPaths, capital_results: dict, provenance: Mapping[str, Any] | None) -> None:
    capital = capital_results["capital"]

    def lv_capital(key: str) -> LegalValue:
        return legal_value_from_dict(
            capital, key,
            country=USA_COUNTRY,
            section="capital_results.capital",
            provenance=provenance,
        )

    schema = load_form_schema("form_6781")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_6781.md",
        f"{paths.year} {schema.display_name}",
        [
            "This form carries the Schwab section 1256 result into Schedule D using the 40/60 split.",
        ],
        [
            legal_value_entry(schema.label("net_section_1256_result"), lv_capital("section_1256_total_usd"), currency=Currency.USD, source="us-capital-results.json"),
            legal_value_entry(schema.label("short_term_40_pct"), lv_capital("section_1256_short_term_usd"), currency=Currency.USD, source="us-capital-results.json"),
            legal_value_entry(schema.label("long_term_60_pct"), lv_capital("section_1256_long_term_usd"), currency=Currency.USD, source="us-capital-results.json"),
        ],
        [
            "The split is imported from the saved capital model output.",
        ],
    )


def _write_form_6251(
    paths: YearPaths,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Form 6251 (Alternative Minimum Tax — Individuals) for F-US-1.

    Authority:
      - 26 U.S.C. § 55 (tentative minimum tax)
        https://www.law.cornell.edu/uscode/text/26/55
      - 26 U.S.C. § 56 (AMTI add-backs)
        https://www.law.cornell.edu/uscode/text/26/56
      - 26 U.S.C. § 59 (AMTFTC)
        https://www.law.cornell.edu/uscode/text/26/59
      - IRS Form 6251 (about + instructions)
        https://www.irs.gov/forms-pubs/about-form-6251
      - Rev. Proc. 2024-40 § 3.11 (2025 inflation adjustments)
        https://www.irs.gov/pub/irs-drop/rp-24-40.pdf

    The line numbers track the 2024-revision Form 6251 (the 2025 form
    retains the same line numbering as of this writing — see the IRS form
    page for any post-publication line renumbering). The renderer reads the
    executed values from the treaty packet's ``form_6251`` projection block,
    which is itself a projection of ``us.stage.amt_amti``,
    ``us.stage.amt_tentative``, and ``us.stage.amt_owed`` produced by the
    US25-AMT-* rule chain.
    """
    form_6251 = treaty.get("form_6251")
    if not isinstance(form_6251, dict):
        # Defensive: the treaty packet must carry the AMT projection. If it
        # does not, fail closed rather than silently writing an empty Form 6251.
        raise FileNotFoundError(
            "Missing required Form 6251 projection in treaty package: "
            "treaty['form_6251'] (carries lines 4 / 5 / 6 / 7 / 8 / 11)."
        )

    def lv_form_6251(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            form_6251,
            line_key,
            country=USA_COUNTRY,
            section="form_6251",
            provenance=provenance,
        )

    schema = load_form_schema("form_6251")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_6251.md",
        f"{paths.year} {schema.display_name}",
        [
            "Form 6251 implements 26 U.S.C. § 55 (tentative minimum tax), § 56 (AMTI add-backs), and § 59 (AMTFTC).",
            "Authority: https://www.law.cornell.edu/uscode/text/26/55 — https://www.irs.gov/forms-pubs/about-form-6251",
            "2025 numerics from Rev. Proc. 2024-40 § 3.11: $88,100 single / $137,000 MFJ / $68,500 MFS exemption; phase-out at $626,350 / $1,252,700 / $626,350; 26%/28% break at $239,100 (or $119,550 MFS).",
        ],
        [
            legal_value_entry(
                schema.label("4"),
                lv_form_6251("line_4_amti_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Alternative minimum taxable income (taxable income + § 56 add-backs).",
            ),
            legal_value_entry(
                schema.label("preferential_amti"),
                lv_form_6251("preferential_amti_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Long-term capital gain + qualified dividends inside AMTI (kept at § 1(h) preferential rates).",
            ),
            legal_value_entry(
                schema.label("5"),
                lv_form_6251("line_5_exemption_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 55(d) exemption after § 55(d)(3) phase-out (25 cents per dollar of AMTI above the threshold).",
            ),
            legal_value_entry(
                schema.label("6"),
                lv_form_6251("line_6_amti_after_exemption_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="AMTI less exemption (line 4 − line 5), floored at zero.",
            ),
            legal_value_entry(
                schema.label("7"),
                lv_form_6251("line_7_tentative_min_tax_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Tentative minimum tax — § 55(b) 26%/28% schedule with § 55(b)(3) preferential ordering.",
            ),
            legal_value_entry(
                schema.label("8"),
                lv_form_6251("line_8_amtftc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 59(a) AMTFTC — per-category limitation parallel to § 904(d) on the AMTI base.",
            ),
            # IRS-VERIFIED 2026-05-10 — Form 6251 (2025) line 11 reads
            # "AMT. Subtract line 10 from line 9. If zero or less, enter
            # -0-. Enter here and on Schedule 2 (Form 1040), line 2"
            # per https://www.irs.gov/pub/irs-pdf/f6251.pdf. The Schedule 2
            # destination moved from line 1 (2024 revision) to line 2
            # (2025 revision); the Form 1040 destination (line 17) is
            # unchanged.
            legal_value_entry(
                schema.label("11"),
                lv_form_6251("line_11_amt_owed_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="AMT owed = max(0, tentative minimum − AMTFTC − regular tax after FTC). Carried to Schedule 2 line 2 / Form 1040 line 17.",
            ),
        ],
        [
            # IRS-VERIFIED 2026-05-10 — line numbering verified against the
            # 2025 Form 6251 PDF at https://www.irs.gov/pub/irs-pdf/f6251.pdf.
            # The 2025 Form 6251 retains line 11 as the AMT-result line; only
            # the Schedule 2 destination changed (line 1 → line 2).
            "Line numbering verified against the 2025 Form 6251 PDF: https://www.irs.gov/pub/irs-pdf/f6251.pdf",
            "Confirm against the official IRS PDF before filing: https://www.irs.gov/forms-pubs/about-form-6251",
        ],
    )


def _write_schedule_8812(
    paths: YearPaths,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Schedule 8812 (Credits for Qualifying Children and Other Dependents).

    Authority:
      - 26 U.S.C. § 24(a) (as substituted by § 24(h)(2) post-OBBBA for
        2025) — $2,200 CTC per qualifying child (§ 152(c)).
        https://www.law.cornell.edu/uscode/text/26/24
      - 26 U.S.C. § 24(b)(2)/(3) — phase-out at $200k single / $400k MFJ;
        $50 per $1,000 of MAGI excess (excess rounded up to next $1,000).
      - 26 U.S.C. § 24(d)(1)(A) — refundable Additional Child Tax Credit
        (ACTC) cap of $1,700 per qualifying child for 2025 (inflation-
        indexed via § 24(h)(5); Rev. Proc. 2024-40 § 3.05).
        § 24(d)(1)(B) phase-in: 15% × (earned income − $2,500).
      - 26 U.S.C. § 24(h)(4) — $500 Credit for Other Dependents (NON-
        refundable).
      - 26 U.S.C. § 152(c) — qualifying child definition.
        https://www.law.cornell.edu/uscode/text/26/152
      - IRS Schedule 8812 (2025) instructions.
        https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040

    The renderer reads the executed values from the treaty packet's
    ``schedule_8812`` projection block, which is itself a projection of
    ``us.ctc.*`` produced by the ``US25-CTC-AND-ODC`` rule. Lines 1-14
    cover the CTC computation (gross CTC + ODC, MAGI phase-out,
    nonrefundable portion). Lines 15-27 cover the ACTC (refundable
    portion).

    F-CQ-1: every numeric line transits ``legal_value_entry`` with a
    ``LegalValue`` envelope (invariant I11). The Form 1040 line 19
    nonrefundable portion and Form 1040 line 28 refundable ACTC carry
    their own (stage_id, output_key, fingerprint) triple inside the
    ``_provenance`` block of ``final-legal-output.json``.
    """
    schedule = treaty.get("schedule_8812")
    if not isinstance(schedule, dict):
        # Defensive: the treaty packet must carry the Schedule 8812
        # projection. Failing closed prevents a silent zero-credit
        # rendering when the rule graph stage never executed.
        raise FileNotFoundError(
            "Missing required Schedule 8812 projection in treaty package: "
            "treaty['schedule_8812'] (carries lines 1-14 / 15-27)."
        )

    # Map each Schedule 8812 projection key to its declared
    # ``us.ctc.*`` executor output_key. The renderer's
    # ``legal_value_from_dict`` lookup then resolves a real
    # ``StageResult.output_fingerprint`` from
    # ``_provenance.form_lines["US"]`` — never a synthesized one
    # (invariants I2 / I11). Adding a Schedule 8812 line requires
    # adding a row here AND a matching ``OutputDeclaration.form_line_refs``
    # on the US25-CTC-AND-ODC stage (invariant I3 bidirectional).
    SCHEDULE_8812_PROVENANCE: dict[str, str] = {
        "qualifying_ctc_count": "us.ctc.qualifying_ctc_count",
        "qualifying_odc_count": "us.ctc.qualifying_odc_count",
        "gross_ctc_usd": "us.ctc.gross_ctc_usd",
        "gross_odc_usd": "us.ctc.gross_odc_usd",
        "combined_pre_phaseout_usd": "us.ctc.combined_pre_phaseout_usd",
        "phaseout_reduction_usd": "us.ctc.phaseout_reduction_usd",
        "combined_post_phaseout_usd": "us.ctc.combined_post_phaseout_usd",
        "line_9_phaseout_threshold_usd": "us.ctc.phaseout_threshold_usd",
        "line_10_modified_agi_usd": "us.ctc.modified_agi_usd",
        "line_13_credit_limit_from_worksheet_usd": "us.ctc.regular_tax_after_ftc_usd",
        "line_14_nonrefundable_ctc_odc_usd": "us.ctc.nonrefundable_portion_usd",
        "line_16a_remaining_ctc_for_actc_usd": "us.ctc.remaining_ctc_for_refundable_usd",
        "line_16b_per_child_refundable_cap_usd": "us.ctc.refundable_actc_cap_usd",
        "line_18a_earned_income_usd": "us.ctc.earned_income_usd",
        "line_19_earned_income_floor_usd": "us.ctc.earned_income_floor_usd",
        "line_20_earned_income_excess_usd": "us.ctc.earned_income_excess_usd",
        "line_21_earned_income_phase_in_usd": "us.ctc.refundable_actc_earned_income_phase_in_usd",
        "line_27_refundable_actc_usd": "us.ctc.refundable_actc_usd",
        "total_credit_usd": "us.ctc.total_credit_usd",
    }

    def lv_8812(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            schedule,
            line_key,
            country=USA_COUNTRY,
            section="schedule_8812",
            provenance=provenance,
            provenance_output_key=SCHEDULE_8812_PROVENANCE[line_key],
        )

    # Every Schedule 8812 line surfaced here is a 1:1 projection of a
    # declared ``us.ctc.*`` rule output (Schedule 8812 Lines 4 / 5 / 6 /
    # 7 / 8 / 9 / 10 / 11 / 12 / 13 / 14 / 16a / 16b / 18a / 19 / 20 /
    # 21 / 27). Adding a new line requires (1) adding the value as a
    # ``us.ctc.*`` output of US25-CTC-AND-ODC, (2) adding a
    # ``form_line_refs`` entry on the corresponding ``OutputDeclaration``,
    # and (3) projecting the value into ``us-treaty-package.json``'s
    # ``schedule_8812`` block. The I3 invariant scanner enforces the
    # bidirectional renderer↔declaration match.
    schema = load_form_schema("schedule_8812")
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_8812.md",
        f"{paths.year} {schema.display_name}",
        [
            "Schedule 8812 implements 26 U.S.C. § 24 — Child Tax Credit (§ 24(a)), "
            "Credit for Other Dependents (§ 24(h)(4)), and the refundable Additional "
            "Child Tax Credit (§ 24(d)).",
            f"Authority: {USC_24_URL} — {SCH_8812_INSTRUCTIONS_URL}",
            "2025 numerics: $2,200 per qualifying child (§ 24(a) as substituted by "
            "§ 24(h)(2) post-OBBBA); $500 ODC per other dependent (§ 24(h)(4)); "
            "$1,700 refundable cap per qualifying child (§ 24(d)(1)(A); "
            "Rev. Proc. 2024-40 § 3.05); phase-out at $200,000 single / $400,000 "
            "MFJ at $50 per $1,000 of MAGI excess.",
        ],
        [
            # Part I — Child Tax Credit and Credit for Other Dependents
            legal_value_entry(
                schema.label("4"),
                lv_8812("qualifying_ctc_count"),
                unit="count",
                source="us-treaty-package.json",
                notes="Number of qualifying children under § 152(c) with a § 24(h)(7) SSN.",
            ),
            legal_value_entry(
                schema.label("5"),
                lv_8812("gross_ctc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Line 4 × $2,200 — gross CTC before phase-out (§ 24(a) as substituted by § 24(h)(2)).",
            ),
            legal_value_entry(
                schema.label("6"),
                lv_8812("qualifying_odc_count"),
                unit="count",
                source="us-treaty-package.json",
                notes="Number of other dependents (§ 24(h)(4) qualifying relatives + non-SSN children).",
            ),
            legal_value_entry(
                schema.label("7"),
                lv_8812("gross_odc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Line 6 × $500 — gross ODC before phase-out (§ 24(h)(4)).",
            ),
            legal_value_entry(
                schema.label("8"),
                lv_8812("combined_pre_phaseout_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Line 5 + Line 7 — combined CTC + ODC before MAGI phase-out.",
            ),
            # Schedule 8812 (2025) Line 9 — § 24(b)(2) phase-out threshold.
            legal_value_entry(
                schema.label("9"),
                lv_8812("line_9_phaseout_threshold_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 24(b)(2) phase-out threshold ($200,000 single / $400,000 MFJ).",
            ),
            # Schedule 8812 Line 10 — § 24(b)(2) Modified AGI. AGI plus
            # § 911 / § 933 add-backs (parallel to § 1411(d)(1)(A) NIIT
            # MAGI). Sourced from ``us.ctc.modified_agi_usd``.
            legal_value_entry(
                schema.label("10"),
                lv_8812("line_10_modified_agi_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 24(b)(2) Modified AGI = AGI + § 911 / § 933 excluded foreign earned income.",
            ),
            legal_value_entry(
                schema.label("11"),
                lv_8812("phaseout_reduction_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 24(b)(3) — $50 × ceil(max(0, MAGI − threshold)/$1,000); capped at line 8.",
            ),
            legal_value_entry(
                schema.label("12"),
                lv_8812("combined_post_phaseout_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Line 8 − Line 11 — combined CTC + ODC after phase-out.",
            ),
            # Schedule 8812 Line 13 — Credit Limit Worksheet A regular-tax
            # ordering cap (§ 24(b)(3)).
            legal_value_entry(
                schema.label("13"),
                lv_8812("line_13_credit_limit_from_worksheet_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Credit Limit Worksheet A — regular tax after FTC; "
                    "§ 24(b)(3) caps the nonrefundable portion at this value."
                ),
            ),
            legal_value_entry(
                schema.label("14"),
                lv_8812("line_14_nonrefundable_ctc_odc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "min(combined_post_phaseout, regular_tax_after_FTC) — "
                    "nonrefundable CTC + ODC carried to Form 1040 line 19 "
                    "(§ 24(b)(3) ordering: cannot reduce tax below zero)."
                ),
            ),
            # Part II-A — Additional Child Tax Credit (refundable). The
            # Schedule 8812 (2025) instructions walk Lines 16a / 16b
            # (remaining-CTC ceiling and per-child cap), 18a / 19 / 20 /
            # 21 (earned-income phase-in), then Line 27 (final refundable
            # ACTC). § 24(d)(1)(A) — $1,700/child cap (Rev. Proc. 2024-40
            # § 3.05). § 24(d)(1)(B) — 15 % × (earned − $2,500) phase-in.
            legal_value_entry(
                schema.label("16a"),
                lv_8812("line_16a_remaining_ctc_for_actc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Remaining post-phaseout CTC after the nonrefundable "
                    "allocation absorbed regular tax — § 24(d) refundable "
                    "ceiling input."
                ),
            ),
            legal_value_entry(
                schema.label("16b"),
                lv_8812("line_16b_per_child_refundable_cap_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "$1,700 × qualifying_ctc_count — § 24(d)(1)(A) per-child "
                    "refundable cap for 2025 (Rev. Proc. 2024-40 § 3.05)."
                ),
            ),
            legal_value_entry(
                schema.label("18a"),
                lv_8812("line_18a_earned_income_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Earned income for § 24(d)(1)(B) — wages "
                    "(§ 32(c)(2)(A)) + net SE earnings (§ 32(c)(2)(B)), "
                    "less § 911 excluded amounts under § 24(d)(1)(B)(i)."
                ),
            ),
            # Schedule 8812 Line 19 — statutory $2,500 floor under
            # § 24(d)(1)(B). Constant value (CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD
            # in the law module) but surfaced as a rule output so the
            # form-line write traces to a fingerprint (invariant I2).
            legal_value_entry(
                schema.label("19"),
                lv_8812("line_19_earned_income_floor_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 24(d)(1)(B) statutory $2,500 earned-income floor.",
            ),
            legal_value_entry(
                schema.label("20"),
                lv_8812("line_20_earned_income_excess_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="max(0, line 18a − line 19) — earned income above the $2,500 floor.",
            ),
            legal_value_entry(
                schema.label("21"),
                lv_8812("line_21_earned_income_phase_in_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="15 % × line 20 — § 24(d)(1)(B) phase-in amount.",
            ),
            legal_value_entry(
                schema.label("27"),
                lv_8812("line_27_refundable_actc_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "min(line 16a, line 16b, line 21) — refundable ACTC "
                    "carried to Form 1040 line 28 (§ 24(d)(1)(B); Rev. "
                    "Proc. 2024-40 § 3.05 OBBBA-preserved cap)."
                ),
            ),
            legal_value_entry(
                schema.label("total_credit"),
                lv_8812("total_credit_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Line 14 + Line 27 — total § 24 credit "
                    "(nonrefundable + refundable ACTC)."
                ),
            ),
        ],
        [
            "The 2025 form retains the line-numbering scheme from the 2024 revision; "
            f"confirm against the official IRS PDF before filing: {SCH_8812_INSTRUCTIONS_URL}",
            "ODC is non-refundable; only the § 24(d) ACTC can flow to line 28.",
            "Every numeric line above traces to a declared ``us.ctc.*`` rule "
            "output via the executor's ``StageResult.output_fingerprint`` "
            "chain — no synthesized fingerprints (invariants I2 / I11).",
        ],
    )


def _write_schedule_2(
    paths: YearPaths,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Schedule 2 (Additional Taxes) for B1 (FORM-MAPPING-FOLLOWUP).

    Authority:
      - 26 U.S.C. § 55 (Alternative Minimum Tax) / Form 6251.
        https://www.law.cornell.edu/uscode/text/26/55
      - 26 U.S.C. § 1401 / § 1402 (Self-Employment Tax) / Schedule SE.
      - 26 U.S.C. § 3101(b)(2) / § 1401(b)(2) (Additional Medicare) /
        Form 8959.
      - 26 U.S.C. § 1411 (NIIT) / Form 8960.
      - Schedule 2 (2025 revision): https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
        https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
      - Form 1040 instructions (line 17 reads Schedule 2 Part I total;
        line 23 reads Schedule 2 Part II total):
        https://www.irs.gov/instructions/i1040gi

    IRS-VERIFIED 2026-05-11 — chain is Form 6251 line 11 (AMT) →
    Schedule 2 line 2 → Schedule 2 line 3 (Part I total = line 1z
    additions to tax + line 2 AMT) → Form 1040 line 17. The 2025 IRS
    revision moved AMT from line 1 (2024) to line 2.
    https://www.irs.gov/pub/irs-pdf/f1040s2.pdf

    Each line on this form is a 1:1 projection of a declared rule output
    (US25-AMT-FTC-AND-COMPARE / US25-SE-TAX / US25-ADDITIONAL-MEDICARE /
    US25-20-NIIT / US25-21-PAYMENTS) so every form-line write transits
    ``legal_value_entry`` with the executor's
    ``StageResult.output_fingerprint`` (invariants I2 / I11) — no
    synthesized fingerprints. Adding a new Schedule 2 line requires (1)
    declaring the value as a rule output, (2) adding a
    ``form_line_refs`` entry on the corresponding ``OutputDeclaration``,
    and (3) projecting the value into ``us-treaty-package.json``'s
    ``schedule_2`` block; the bidirectional I3 invariant scanner enforces
    the renderer↔declaration match.
    """
    schedule = treaty.get("schedule_2")
    if not isinstance(schedule, dict):
        # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) Part I: line 2 = AMT,
        # line 3 = line 1z + line 2 → Form 1040 line 17.
        # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
        raise FileNotFoundError(
            "Missing required Schedule 2 projection in treaty package: "
            "treaty['schedule_2'] (carries lines 2 / 3 / 4 / 11 / 12 / 21)."
        )

    # Map each Schedule 2 projection key to its declared executor
    # ``us.tax.schedule_2_*`` output_key. The renderer's
    # ``legal_value_from_dict`` lookup then resolves the real
    # ``StageResult.output_fingerprint`` from
    # ``_provenance.form_lines["US"]`` — never a synthesized one.
    SCHEDULE_2_PROVENANCE: dict[str, str] = {
        "line_1_amt_from_form_6251_usd": "us.tax.schedule_2_line_1_amt_usd",
        "line_3_total_amt_usd": "us.tax.schedule_2_line_3_total_amt_usd",
        "line_4_se_tax_from_schedule_se_usd": "us.tax.schedule_2_line_4_se_tax_usd",
        "line_11_additional_medicare_from_form_8959_usd": "us.tax.schedule_2_line_11_additional_medicare_usd",
        "line_12_niit_from_form_8960_usd": "us.tax.schedule_2_line_12_niit_usd",
        "line_21_total_other_taxes_usd": "us.tax.schedule_2_line_21_total_other_taxes_usd",
    }

    def lv_sched2(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            schedule,
            line_key,
            country=USA_COUNTRY,
            section="schedule_2",
            provenance=provenance,
            provenance_output_key=SCHEDULE_2_PROVENANCE[line_key],
        )

    schema = load_form_schema("schedule_2")
    # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) Part I line 3 carries to
    # Form 1040 line 17; Part II line 21 carries to Form 1040 line 23
    # per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_2.md",
        f"{paths.year} {schema.display_name}",
        [
            "Schedule 2 carries Part I (Alternative Minimum Tax) to Form 1040 line 17 and "
            "Part II (Other Taxes — SE tax, Additional Medicare, NIIT) to Form 1040 line 23.",
            "Authority: 26 U.S.C. §§ 55, 1401, 3101(b)(2), 1411.",
            f"Form: {IRS_ABOUT_SCHEDULE_2_URL}",
        ],
        [
            # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) Part I line layout per
            # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf: lines 1a-1f/1y/1z =
            # additions to tax; line 2 = AMT (Form 6251 line 11); line 3 =
            # line 1z + line 2 → Form 1040 line 17. AMT moved from Schedule
            # 2 line 1 (2024) to line 2 (2025); corrected here.
            # IRS-VERIFIED 2026-05-10 — Form 6251 (2025) line 11 instructs
            # filer to "Enter here and on Schedule 2 (Form 1040), line 2"
            # (was line 1 on 2024 revision). https://www.irs.gov/pub/irs-pdf/f6251.pdf
            legal_value_entry(
                schema.label("2"),
                lv_sched2("line_1_amt_from_form_6251_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                # IRS-VERIFIED 2026-05-10 — Form 6251 line 11 = AMT, lands on
                # Schedule 2 line 2 (2025) per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
                notes="Alternative minimum tax (Form 6251 line 11) under 26 U.S.C. § 55. (The internal projection key retains the historical ``line_1_amt`` name for fingerprint stability — the 2025 IRS line number is 2.)",
            ),
            legal_value_entry(
                schema.label("3"),
                lv_sched2("line_3_total_amt_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 3 = line 1z + line 2
                # → Form 1040 line 17 per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
                notes="Part I total (line 1z additions to tax + line 2 AMT). Carries to Form 1040 line 17.",
            ),
            # Part II — additional taxes flowing to Form 1040 line 23.
            # IRS-VERIFIED 2026-05-11 — Schedule SE (2025) line 12 instructs
            # "Enter here and on Schedule 2 (Form 1040), line 4"
            # per https://www.irs.gov/pub/irs-pdf/f1040sse.pdf.
            legal_value_entry(
                schema.label("4"),
                lv_sched2("line_4_se_tax_from_schedule_se_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 1401 self-employment tax from Schedule SE line 12.",
            ),
            # IRS-VERIFIED 2026-05-11 — Form 8959 (2025) line 18 instructs
            # "Also include this amount on Schedule 2 (Form 1040), line 11"
            # per https://www.irs.gov/pub/irs-pdf/f8959.pdf.
            legal_value_entry(
                schema.label("11"),
                lv_sched2("line_11_additional_medicare_from_form_8959_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 3101(b)(2) / § 1401(b)(2) Additional Medicare from Form 8959 line 18.",
            ),
            # IRS-VERIFIED 2026-05-11 — Form 8960 (2025) line 17 = "Net
            # investment income tax for individuals" per
            # https://www.irs.gov/pub/irs-pdf/f8960.pdf; carries to
            # Schedule 2 (2025) line 12 per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
            legal_value_entry(
                schema.label("12"),
                lv_sched2("line_12_niit_from_form_8960_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="§ 1411 net investment income tax from Form 8960 line 17.",
            ),
            # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) line 21 = total of
            # Part II "other taxes" rows; "Enter here and on Form 1040 ...
            # line 23" per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
            legal_value_entry(
                schema.label("21"),
                lv_sched2("line_21_total_other_taxes_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Part II total (lines 4-18). Carries to Form 1040 line 23.",
            ),
        ],
        [
            # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line numbering per
            # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
            "Line numbering verified 2026-05-10 against https://www.irs.gov/pub/irs-pdf/f1040s2.pdf "
            "(2025 revision): Part I lines 1a-1f / 1y / 1z = additions to tax (APTC repayment, "
            "clean-vehicle credit repayments, Form 4255 EPE recapture, other), line 2 = AMT "
            "(Form 6251 line 11), line 3 = line 1z + line 2 → Form 1040 line 17.",
            "Every numeric line above traces to a declared "
            "``us.tax.schedule_2_*`` rule output via the executor's "
            "``StageResult.output_fingerprint`` chain (invariants I2 / I11).",
        ],
    )


def _write_schedule_3(
    paths: YearPaths,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Schedule 3 (Additional Credits and Payments) for B2.

    Authority:
      - 26 U.S.C. §§ 901, 904 — Foreign Tax Credit (Schedule 3 line 1).
      - 26 U.S.C. § 904(d)(6) — treaty re-sourcing basket.
      - IRS Publication 514 worksheet line 21 (treaty resourcing add-on
        carried to Form 1116 line 12 / Part IV line 32).
        https://www.irs.gov/publications/p514
      - Schedule 3 (2024 revision; 2025 retains line numbering):
        https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
      - Form 1040 line 20 reads from Schedule 3 line 8 (= Part I total
        nonrefundable credits): https://www.irs.gov/instructions/i1040gi

    Each line on this form is a 1:1 projection of a declared rule output
    (US25-19A for line 1 post-treaty FTC; US25-21-PAYMENTS for lines 6c
    and 11) so every form-line write transits ``legal_value_entry`` with
    the executor's ``StageResult.output_fingerprint`` (invariants I2 /
    I11).

    The renderer closes the long-standing I5 smell at
    ``tax_pipeline/pipelines/y2025/us_treaty_packet.py:147`` where the
    projection summed three rule outputs (allowed_general +
    allowed_passive + treaty_resourcing_additional) into a local — that
    arithmetic now lives inside the rule graph as
    ``us.tax.schedule_3_line_1_ftc_total_usd``.
    """
    schedule = treaty.get("schedule_3")
    if not isinstance(schedule, dict):
        raise FileNotFoundError(
            "Missing required Schedule 3 projection in treaty package: "
            "treaty['schedule_3'] (carries lines 1 / 8)."
        )

    SCHEDULE_3_PROVENANCE: dict[str, str] = {
        "line_1_foreign_tax_credit_usd": "us.tax.schedule_3_line_1_ftc_total_usd",
    }

    def lv_sched3(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            schedule,
            line_key,
            country=USA_COUNTRY,
            section="schedule_3",
            provenance=provenance,
            provenance_output_key=SCHEDULE_3_PROVENANCE.get(line_key),
        )

    schema = load_form_schema("schedule_3")
    # IRS-VERIFIED 2026-05-11 — Schedule 3 (2025) line 8 ("Add lines 1
    # through 4, 5a, 5b, and 7") carries to Form 1040 line 20; line 15
    # ("Add lines 9 through 12 and 14") carries to Form 1040 line 31
    # per https://www.irs.gov/pub/irs-pdf/f1040s3.pdf.
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_3.md",
        f"{paths.year} {schema.display_name}",
        [
            "Schedule 3 carries Part I nonrefundable credits to Form 1040 line 20 and "
            "Part II refundable credits / payments to Form 1040 line 31.",
            "Authority: 26 U.S.C. §§ 901, 904; § 904(d)(6) treaty re-sourcing basket; "
            "IRS Pub. 514 worksheet line 21.",
            f"Form: {IRS_ABOUT_SCHEDULE_3_URL}",
        ],
        [
            # Part I — line 1 (FTC) and line 8 (Part I total). Only the
            # FTC line is non-zero in the supported posture; other Part I
            # credits (CDCC, education, retirement, residential energy,
            # general business, etc.) are not modeled.
            # IRS-NEEDS-VERIFICATION 2026-05-11 — the notes string references
            # "Form 1116 line 33" but the 2025 Form 1116 PDF
            # (https://www.irs.gov/pub/irs-pdf/f1116.pdf) routes the FTC
            # subtotal-after-boycott-reduction to Schedule 3 (Form 1040)
            # line 1 from a different Part IV row than the cited number.
            # Flagged for a separate atomic line-numbering commit (defer;
            # do not silently rotate).
            legal_value_entry(
                schema.label("1"),
                lv_sched3("line_1_foreign_tax_credit_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Foreign tax credit (Form 1116 line 33), post-treaty "
                    "re-sourcing. § 901 / § 904 + Pub. 514 worksheet line 21."
                ),
            ),
            # Line 8 mirrors line 1 here (the only Part I credit modeled).
            # It is rendered from the same ftc_total rule output via the
            # ``Schedule 3, line 8`` FormLineRef declared on
            # ``us.tax.schedule_3_line_1_ftc_total_usd``; both reads
            # transit the same StageResult fingerprint.
            # IRS-VERIFIED 2026-05-11 — Schedule 3 (2025) line 8 = "Add
            # lines 1 through 4, 5a, 5b, and 7" — total Part I non-
            # refundable credits per https://www.irs.gov/pub/irs-pdf/f1040s3.pdf.
            legal_value_entry(
                schema.label("8"),
                lv_sched3("line_1_foreign_tax_credit_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Total nonrefundable credits (Schedule 3 Part I). For "
                    "the supported posture this equals line 1 (FTC) — no "
                    "other Part I credits are claimed."
                ),
            ),
        ],
        [
            "The 2025 form retains the line-numbering scheme from the 2024 revision; "
            f"confirm against the official IRS PDF before filing: {IRS_ABOUT_SCHEDULE_3_URL}",
            "Schedule 3 surfaces only the actual Schedule 3 lines (line 1, "
            "line 8) for the supported posture. The treaty re-sourcing "
            "additional credit (IRS Pub. 514 worksheet line 21) is NOT a "
            "Schedule 3 line — per the IRS form numbering, Schedule 3 "
            "line 6c is the Adoption credit (Form 8839) and Schedule 3 "
            "line 11 is excess Social Security / Tier 1 RRTA tax withheld; "
            "neither maps to the FTC. The Pub. 514 add-on flows into Form "
            "1116 Part III line 12 / Part IV line 32 and reaches Schedule "
            "3 only via line 1 (the post-cap allowed FTC).",
            "Every numeric line above traces to a declared ``us.tax.*`` "
            "rule output via the executor's ``StageResult.output_fingerprint`` "
            "chain (invariants I2 / I11).",
        ],
    )


def _write_schedule_se(
    paths: YearPaths,
    treaty: dict,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Schedule SE (Self-Employment Tax) for B4.

    Authority:
      - 26 U.S.C. § 1401 — SE tax = 12.4 % OASDI on net SE earnings up
        to the SSA wage base + 2.9 % Medicare on all net SE earnings.
      - 26 U.S.C. § 1402(a)(12) — net SE earnings × 92.35 %.
      - Schedule SE instructions:
        https://www.irs.gov/forms-pubs/about-schedule-se-form-1040

    The renderer is gated on net SE earnings > 0; when the supported
    posture has no SE income (the brenn-2025 / demo postures) the form
    file is not written.
    """
    schedule = treaty.get("schedule_se")
    if not isinstance(schedule, dict):
        raise FileNotFoundError(
            "Missing required Schedule SE projection in treaty package: "
            "treaty['schedule_se']."
        )
    line_2_value = D(str(schedule.get("line_2_net_se_earnings_usd", "0.00")))
    if line_2_value <= D("0.00"):
        return

    SCHEDULE_SE_PROVENANCE: dict[str, str] = {
        "line_2_net_se_earnings_usd": "us.tax.schedule_se_line_2_net_se_earnings_usd",
        "line_3_total_se_earnings_usd": "us.tax.schedule_se_line_3_total_se_earnings_usd",
        "line_4a_se_taxable_usd": "us.tax.schedule_se_line_4a_se_taxable_usd",
        "line_4c_se_taxable_usd": "us.tax.schedule_se_line_4c_se_taxable_usd",
        "line_6_combined_se_base_usd": "us.tax.schedule_se_line_6_combined_se_base_usd",
        "line_8a_w2_ss_wages_usd": "us.tax.schedule_se_line_8a_w2_ss_wages_usd",
        "line_10_oasdi_tax_usd": "us.tax.schedule_se_line_10_oasdi_tax_usd",
        "line_11_medicare_tax_usd": "us.tax.schedule_se_line_11_medicare_tax_usd",
        "line_12_total_se_tax_usd": "us.tax.schedule_se_line_12_total_se_tax_usd",
    }

    def lv_se(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            schedule,
            line_key,
            country=USA_COUNTRY,
            section="schedule_se",
            provenance=provenance,
            provenance_output_key=SCHEDULE_SE_PROVENANCE[line_key],
        )

    schema = load_form_schema("schedule_se")
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_se.md",
        f"{paths.year} {schema.display_name}",
        [
            "Schedule SE implements 26 U.S.C. § 1401 (12.4 % OASDI / 2.9 % Medicare on "
            "net SE earnings, with the § 1402(a)(12) 92.35 % factor). Line 12 carries "
            "to Schedule 2 line 4.",
            f"Authority: {IRS_SCHEDULE_SE_URL}",
        ],
        [
            legal_value_entry(
                schema.label("2"),
                lv_se("line_2_net_se_earnings_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Net profit/loss from Schedule C (or partnership Schedule K-1).",
            ),
            legal_value_entry(
                schema.label("3"),
                lv_se("line_3_total_se_earnings_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Combine lines 1a, 1b, 2 (= line 2 in the supported posture).",
            ),
            legal_value_entry(
                schema.label("4a"),
                lv_se("line_4a_se_taxable_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="line 3 × 92.35 % — § 1402(a)(12) net SE earnings factor.",
            ),
            legal_value_entry(
                schema.label("4c"),
                lv_se("line_4c_se_taxable_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Combine lines 4a + 4b (= 4a; no optional method modelled).",
            ),
            legal_value_entry(
                schema.label("6"),
                lv_se("line_6_combined_se_base_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Add lines 4c + 5b (= 4c; no church-employee income modelled).",
            ),
            legal_value_entry(
                schema.label("8a"),
                lv_se("line_8a_w2_ss_wages_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "W-2 box 3 social-security wages — used to reduce the SS wage-"
                    "base ceiling on line 9 (= max(0, $176,100 − line 8a))."
                ),
            ),
            legal_value_entry(
                schema.label("10"),
                lv_se("line_10_oasdi_tax_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "OASDI tax = 12.4 % × min(line 6, line 9) per 26 U.S.C. § 1401(a)."
                ),
            ),
            legal_value_entry(
                schema.label("11"),
                lv_se("line_11_medicare_tax_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Medicare tax = 2.9 % × line 6 per 26 U.S.C. § 1401(b)(1). "
                    "§ 1401(b)(2) Additional Medicare is on Form 8959, not here."
                ),
            ),
            legal_value_entry(
                schema.label("12"),
                lv_se("line_12_total_se_tax_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Total SE tax (line 10 + line 11). Carries to Schedule 2 line 4."
                ),
            ),
        ],
        [
            "The 2025 form retains the line-numbering scheme from the 2024 revision; "
            f"confirm against the official IRS PDF before filing: {IRS_SCHEDULE_SE_URL}",
            "Every numeric line above traces to a declared "
            "``us.tax.schedule_se_*`` rule output via the executor's "
            "``StageResult.output_fingerprint`` chain (invariants I2 / I11).",
        ],
    )


def _write_schedule_c(
    paths: YearPaths,
    treaty: dict,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Schedule C (Profit or Loss From Business).

    Authority (IRS-VERIFIED 2026-06-13 against the official 2025 Schedule C
    PDF, https://www.irs.gov/pub/irs-pdf/f1040sc.pdf):
      - 26 U.S.C. § 61(a)(2) — gross income from business (line 7).
      - 26 U.S.C. § 162(a) — ordinary & necessary business expenses (line 28).
      - Schedule C line 31 net profit = line 7 − line 28 (no-home-office
        posture); carries to Schedule 1 line 3 and Schedule SE line 2.

    The renderer is gated on a declared Schedule C position (net profit ≠ 0 or
    gross receipts > 0); a pure wage earner has no Schedule C facts and the
    form file is not written (invariant I13: the artifact is explicitly absent,
    not a zeroed form). No Form 8995 is rendered — for foreign-source business
    income the § 199A QBI deduction is not_applicable (see US25-08A-QBI-GATE),
    so the § 199A non-applicability is narrated rather than shown as a zero
    Form 8995 line.
    """
    schedule = treaty.get("schedule_c")
    if not isinstance(schedule, dict):
        raise FileNotFoundError(
            "Missing required Schedule C projection in treaty package: "
            "treaty['schedule_c']."
        )
    net_profit = D(str(schedule.get("line_31_net_profit_usd", "0.00")))
    gross_income = D(str(schedule.get("line_7_gross_income_usd", "0.00")))
    # Gate: skip rendering when there is no Schedule C business at all (the
    # wage-earner posture). A loss (net_profit < 0) is still a real Schedule C
    # and IS rendered.
    if net_profit == D("0.00") and gross_income == D("0.00"):
        return

    SCHEDULE_C_PROVENANCE: dict[str, str] = {
        "line_7_gross_income_usd": "us.tax.schedule_c_line_7_gross_income_usd",
        "line_28_total_expenses_usd": "us.tax.schedule_c_line_28_total_expenses_usd",
        "line_31_net_profit_usd": "us.tax.schedule_c_line_31_net_profit_usd",
    }

    def lv_sc(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            schedule,
            line_key,
            country=USA_COUNTRY,
            section="schedule_c",
            provenance=provenance,
            provenance_output_key=SCHEDULE_C_PROVENANCE[line_key],
        )

    schema = load_form_schema("schedule_c")
    write_form(
        paths.usa_forms_root / f"{paths.year}_schedule_c.md",
        f"{paths.year} {schema.display_name}",
        [
            # IRS-VERIFIED 2026-06-13 — 2025 Schedule C lines (7/28/31 → Sch 1 ln 3, Sch SE ln 2): https://www.irs.gov/pub/irs-pdf/f1040sc.pdf
            "Schedule C implements 26 U.S.C. § 61(a)(2) (gross income from "
            "business) less 26 U.S.C. § 162(a) (ordinary & necessary "
            "expenses). Line 31 net profit = line 7 − line 28; it carries to "
            "Schedule 1 line 3 (income → AGI) and to Schedule SE line 2 (the "
            "self-employment-tax base) — the same profit, counted once as "
            "income.",
            "The § 199A QBI deduction does NOT apply to this foreign-source "
            "business income (26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c): not "
            "effectively connected with a U.S. trade or business). No Form "
            "8995 is filed; the § 199A non-applicability is explained in the "
            "US25-08A-QBI-GATE narrative.",
            f"Authority: {IRS_SCHEDULE_C_URL}",
        ],
        [
            legal_value_entry(
                schema.label("7"),
                lv_sc("line_7_gross_income_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Gross income (§ 61(a)(2)); gross receipts less returns and cost of goods sold, plus other business income.",
            ),
            legal_value_entry(
                schema.label("28"),
                lv_sc("line_28_total_expenses_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Total ordinary & necessary business expenses (§ 162(a)).",
            ),
            legal_value_entry(
                schema.label("31"),
                lv_sc("line_31_net_profit_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Net profit (or loss) = line 7 − line 28. Carries to Schedule 1 line 3 and Schedule SE line 2.",
            ),
        ],
        [
            "IRS-VERIFIED 2026-06-13 against the official 2025 Schedule C PDF "
            f"(https://www.irs.gov/pub/irs-pdf/f1040sc.pdf): {IRS_SCHEDULE_C_URL}",
            "Every numeric line above traces to a declared "
            "``us.tax.schedule_c_*`` rule output (US25-02A-SCHEDULE-C) via the "
            "executor's ``StageResult.output_fingerprint`` chain (invariants "
            "I2 / I3 / I11).",
        ],
    )


def _write_form_8959(
    paths: YearPaths,
    treaty: dict,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Form 8959 (Additional Medicare Tax) for B3.

    Authority:
      - 26 U.S.C. § 3101(b)(2) — 0.9 % Additional Medicare Tax on
        Medicare-taxable wages above the filing-status threshold
        (Part I, lines 1-7).
      - 26 U.S.C. § 1401(b)(2) — same 0.9 % on net SE earnings; shares
        the threshold with § 3101(b)(2) (Part II, lines 8-13).
      - Form 8959 instructions:
        https://www.irs.gov/forms-pubs/about-form-8959

    The renderer is gated on Schedule 2 line 11 > 0; when no Additional
    Medicare attaches in the supported posture the form file is not
    written. Line numbering tracks the 2024 revision (2025 retains it
    at publication time).
    """
    form = treaty.get("form_8959")
    if not isinstance(form, dict):
        raise FileNotFoundError(
            "Missing required Form 8959 projection in treaty package: "
            "treaty['form_8959']."
        )
    # Gate: skip rendering when no Additional Medicare Tax attaches.
    line_18_value = D(str(form.get("line_18_total_addtl_medicare_usd", "0.00")))
    if line_18_value <= D("0.00"):
        return

    FORM_8959_PROVENANCE: dict[str, str] = {
        "line_1_medicare_wages_usd": "us.tax.form_8959_line_1_medicare_wages_usd",
        "line_4_total_medicare_wages_usd": "us.tax.form_8959_line_4_total_medicare_wages_usd",
        "line_5_threshold_usd": "us.tax.form_8959_line_5_threshold_usd",
        "line_6_wages_excess_usd": "us.tax.form_8959_line_6_wages_excess_usd",
        "line_7_addtl_medicare_on_wages_usd": "us.tax.form_8959_line_7_addtl_medicare_on_wages_usd",
        "line_8_se_taxable_usd": "us.tax.form_8959_line_8_se_taxable_usd",
        "line_11_residual_threshold_usd": "us.tax.form_8959_line_11_residual_threshold_usd",
        "line_13_addtl_medicare_on_se_usd": "us.tax.form_8959_line_13_addtl_medicare_on_se_usd",
        "line_18_total_addtl_medicare_usd": "us.tax.form_8959_line_18_total_addtl_medicare_usd",
    }

    def lv_8959(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            form,
            line_key,
            country=USA_COUNTRY,
            section="form_8959",
            provenance=provenance,
            provenance_output_key=FORM_8959_PROVENANCE[line_key],
        )

    schema = load_form_schema("form_8959")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_8959.md",
        f"{paths.year} {schema.display_name}",
        [
            "Form 8959 implements 26 U.S.C. § 3101(b)(2) (Part I, Medicare wages) "
            "and 26 U.S.C. § 1401(b)(2) (Part II, SE earnings). Both parts share "
            "a single filing-status threshold consumed wages-first.",
            f"Authority: {IRS_FORM_8959_URL}",
        ],
        [
            # Part I — Medicare wages.
            legal_value_entry(
                schema.label("1"),
                lv_8959("line_1_medicare_wages_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Medicare-taxable wages (W-2 box 5).",
            ),
            legal_value_entry(
                schema.label("4"),
                lv_8959("line_4_total_medicare_wages_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Sum of lines 1-3 (line 1 only in supported posture).",
            ),
            legal_value_entry(
                schema.label("5"),
                lv_8959("line_5_threshold_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Filing-status threshold ($200,000 single / $250,000 MFJ / "
                    "$125,000 MFS) per 26 U.S.C. § 3101(b)(2)(A)-(C)."
                ),
            ),
            legal_value_entry(
                schema.label("6"),
                lv_8959("line_6_wages_excess_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="max(0, line 4 − line 5) — Medicare wages above threshold.",
            ),
            legal_value_entry(
                schema.label("7"),
                lv_8959("line_7_addtl_medicare_on_wages_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="line 6 × 0.009 — Additional Medicare on wages (§ 3101(b)(2)).",
            ),
            # Part II — SE earnings.
            legal_value_entry(
                schema.label("8"),
                lv_8959("line_8_se_taxable_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Net SE taxable earnings (Schedule SE Section A line 4).",
            ),
            legal_value_entry(
                schema.label("11"),
                lv_8959("line_11_residual_threshold_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "max(0, line 9 (threshold) − line 10 (Medicare wages)) — "
                    "residual threshold absorbed by SE income."
                ),
            ),
            legal_value_entry(
                schema.label("13"),
                lv_8959("line_13_addtl_medicare_on_se_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "max(0, line 8 − line 11) × 0.009 — Additional Medicare "
                    "on SE earnings (§ 1401(b)(2))."
                ),
            ),
            # Total.
            legal_value_entry(
                schema.label("18"),
                lv_8959("line_18_total_addtl_medicare_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                # IRS-VERIFIED 2026-05-10: Form 8959 (2025) line 18 → Schedule 2
                # line 11 per IRS Form 8959 instructions, Part IV.
                # https://www.irs.gov/instructions/i8959
                notes=(
                    "Total Additional Medicare Tax (line 7 + line 13 + line 17). "
                    "Carries to Schedule 2 line 11. Part III RRTA (lines 14-17) "
                    "is not modeled (zero in supported posture)."
                ),
            ),
        ],
        [
            "The 2025 form retains the line-numbering scheme from the 2024 revision; "
            f"confirm against the official IRS PDF before filing: {IRS_FORM_8959_URL}",
            "Every numeric line above traces to a declared "
            "``us.tax.form_8959_*`` rule output via the executor's "
            "``StageResult.output_fingerprint`` chain (invariants I2 / I11).",
        ],
    )


def _write_form_8960(
    paths: YearPaths,
    trace_rows: list[dict[str, str]],
    tax_estimate: dict,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Form 8960 (Net Investment Income Tax) for B5.

    Authority:
      - 26 U.S.C. § 1411 — Net Investment Income Tax (3.8 % × min(NII,
        max(0, MAGI − threshold))).
      - IRS Form 8960 instructions:
        https://www.irs.gov/forms-pubs/about-form-8960

    B5 (FORM-MAPPING-FOLLOWUP) replaces the previous trace-row read with
    a full Part I / Part III line decomposition sourced from declared
    rule outputs (US25-20-NIIT). Lines surfaced: 1 (interest), 2
    (ordinary dividends), 5a-5d (capital gain/loss subgroup), 8 (total
    investment income), 12 (net investment income). Line 17 (= the
    rolled-up NIIT scalar) is preserved for backward compatibility.
    """
    form = treaty.get("form_8960")
    if not isinstance(form, dict):
        raise FileNotFoundError(
            "Missing required Form 8960 projection in treaty package: "
            "treaty['form_8960']."
        )
    try:
        threshold_usd = tax_estimate["filing_assumptions"]["niit_threshold_usd"]
    except KeyError as exc:
        raise ValueError(
            "Missing model-selected NIIT threshold in final output: "
            "usa.forms.tax_estimate.filing_assumptions.niit_threshold_usd"
        ) from exc

    FORM_8960_PROVENANCE: dict[str, str] = {
        "line_1_interest_usd": "us.tax.form_8960_line_1_interest_usd",
        "line_2_ordinary_dividends_usd": "us.tax.form_8960_line_2_ordinary_dividends_usd",
        "line_5a_capital_gain_loss_usd": "us.tax.form_8960_line_5a_capital_gain_loss_usd",
        "line_5b_non_section_1411_adj_usd": "us.tax.form_8960_line_5b_non_section_1411_adj_usd",
        "line_5c_cfc_pfic_adj_usd": "us.tax.form_8960_line_5c_cfc_pfic_adj_usd",
        "line_5d_combined_capital_usd": "us.tax.form_8960_line_5d_combined_capital_usd",
        "line_7_other_modifications_usd": "us.tax.form_8960_line_7_other_modifications_usd",
        "line_8_total_investment_income_usd": "us.tax.form_8960_line_8_total_investment_income_usd",
        "line_11_total_deductions_usd": "us.tax.form_8960_line_11_total_deductions_usd",
        "line_12_net_investment_income_usd": "us.tax.form_8960_line_12_net_investment_income_usd",
        # Line 17 = NIIT scalar (B1's Schedule 2 line 12 declaration).
        "line_17_niit_usd": "us.tax.schedule_2_line_12_niit_usd",
    }

    def lv_8960(line_key: str) -> LegalValue:
        return legal_value_from_dict(
            form,
            line_key,
            country=USA_COUNTRY,
            section="form_8960",
            provenance=provenance,
            provenance_output_key=FORM_8960_PROVENANCE.get(line_key),
        )

    schema = load_form_schema("form_8960")
    threshold_entry = legal_value_entry(
        schema.label("selected_niit_threshold"),
        legal_value_from_decimal(
            threshold_usd,
            country=USA_COUNTRY,
            section="tax_estimate.filing_assumptions",
            output_key="niit_threshold_usd",
            provenance=provenance,
        ),
        currency=Currency.USD,
        source="us-tax-estimate.json",
        notes="Model-selected threshold used for the 26 U.S.C. § 1411 NIIT calculation.",
    )
    # IRS-VERIFIED 2026-05-10 — Form 8960 (2025) line 17 → Schedule 2 line 12 per
    # https://www.irs.gov/e-file-providers/line-by-line-instructions-free-file-fillable-forms
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_8960.md",
        f"{paths.year} {schema.display_name}",
        [
            "Form 8960 implements 26 U.S.C. § 1411. NIIT = 3.8 % × min(line 12, "
            "max(0, MAGI − threshold)). Line 17 carries to Schedule 2 line 12.",
            f"Authority: {IRS_ABOUT_FORM_8960_URL}",
        ],
        [
            # Part I — Investment Income.
            legal_value_entry(
                schema.label("1"),
                lv_8960("line_1_interest_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Taxable interest (Form 1040 line 2b).",
            ),
            legal_value_entry(
                schema.label("2"),
                lv_8960("line_2_ordinary_dividends_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Ordinary dividends (Form 1040 line 3b).",
            ),
            legal_value_entry(
                schema.label("5a"),
                lv_8960("line_5a_capital_gain_loss_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Net gain/loss from disposition of property (Form 1040 line 7a)."
                ),
            ),
            legal_value_entry(
                schema.label("5b"),
                lv_8960("line_5b_non_section_1411_adj_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Adjustments for non-§ 1411 trade/business gain/loss "
                    "(zero in supported posture)."
                ),
            ),
            legal_value_entry(
                schema.label("5c"),
                lv_8960("line_5c_cfc_pfic_adj_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Adjustment from CFCs and PFICs (zero in supported posture)."
                ),
            ),
            legal_value_entry(
                schema.label("5d"),
                lv_8960("line_5d_combined_capital_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Combine lines 5a + 5b + 5c (= 5a in supported posture).",
            ),
            # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — line 7
            # carries substitute-payment income (and, when elected,
            # staking income) into the line-8 sum. Without surfacing
            # line 7 the rendered Part I lines do not foot to line 8.
            legal_value_entry(
                schema.label("7"),
                lv_8960("line_7_other_modifications_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Other modifications to investment income — "
                    "substitute-payment income (and staking, when the "
                    "§ 1411 staking election is made)."
                ),
            ),
            legal_value_entry(
                schema.label("8"),
                lv_8960("line_8_total_investment_income_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Total investment income — sum of Part I lines 1, 2, "
                    "5d, 7 (floored at zero per § 1411 / Form 8960 "
                    "instructions)."
                ),
            ),
            # Part II — Investment Expenses Allocable to Investment
            # Income. Lines 9a-9c + 10 → line 11 = 0 in the supported
            # posture (no investment-expense deductions modeled).
            legal_value_entry(
                schema.label("11"),
                lv_8960("line_11_total_deductions_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Total deductions and modifications (Part II) — zero "
                    "in the supported posture; surfaced so the rendered "
                    "line 12 = line 8 − line 11 reconciles from visible "
                    "components."
                ),
            ),
            # Part III — Tax Computation.
            legal_value_entry(
                schema.label("12"),
                lv_8960("line_12_net_investment_income_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Net investment income = line 8 − line 11."
                ),
            ),
            threshold_entry,
            legal_value_entry(
                schema.label("17"),
                lv_8960("line_17_niit_usd"),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes=(
                    "Net Investment Income Tax — 3.8 % × min(line 12, "
                    "max(0, MAGI − threshold)). Carries to Schedule 2 line 12."
                ),
            ),
        ],
        [
            "The 2025 form retains the line-numbering scheme from the 2024 revision; "
            f"confirm against the official IRS PDF before filing: {IRS_ABOUT_FORM_8960_URL}",
            "Every numeric line above traces to a declared "
            "``us.tax.form_8960_*`` rule output via the executor's "
            "``StageResult.output_fingerprint`` chain (invariants I2 / I11).",
        ],
    )


def _write_form_1116_passive(
    paths: YearPaths,
    tax_estimate: dict,
    ftc_support_rows: list[dict[str, str]],
    treaty: dict,
    capital_results: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    passive_dividends = _required_key_row(
        ftc_support_rows,
        "foreign_source_passive_dividends_usd",
        "usa/ftc-support.csv",
    )
    passive_net_capital_gain = _required_key_row(
        ftc_support_rows,
        "foreign_source_net_capital_gain_usd",
        "usa/ftc-support.csv",
    )
    worksheet = treaty["treaty_resourcing_worksheet"]
    treaty_claimed = worksheet.get("status") == "computed"
    posture_lines = [
        "Use the passive-category FTC posture from the chosen treaty-resourcing package.",
        (
            "The Publication 514 additional-credit worksheet attaches to this filing package."
            if treaty_claimed
            else "Treaty re-sourcing is not claimed in this filing package."
        ),
    ]
    # IRS Form 1116 (2024 revision; 2025 retains the same line numbering at
    # publication time — confirm against the official PDF before filing):
    # Part I: Line 1a — foreign-source gross income by category. Part II:
    # Line 8 — foreign taxes paid/accrued. Part III: Line 10 — carryover,
    # Line 21 — limitation, Line 22 — allowed credit (smaller of line 14 or
    # line 21), Line 32 — total of all categories, Line 33 — smaller-of cap.
    # https://www.irs.gov/forms-pubs/about-form-1116
    schema = load_form_schema("form_1116_passive")
    entries = [
        legal_value_entry(
            schema.label("1a_dividends"),
            legal_value_from_dict(passive_dividends, "value", country=USA_COUNTRY, section="ftc_support.foreign_source_passive_dividends_usd", provenance=provenance),
            currency=Currency.USD,
            source="usa/ftc-support.csv",
            notes="Schwab page 90 documented foreign-source passive dividends.",
        ),
        legal_value_entry(
            schema.label("1a_capital_gain"),
            legal_value_from_dict(passive_net_capital_gain, "value", country=USA_COUNTRY, section="ftc_support.foreign_source_net_capital_gain_usd", provenance=provenance),
            currency=Currency.USD,
            source="usa/ftc-support.csv",
            notes=passive_net_capital_gain["note"],
        ),
        legal_value_entry(
            schema.label("8"),
            legal_value_from_dict(tax_estimate["ftc"], "current_year_passive_foreign_tax_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
            currency=Currency.USD,
            source="us-tax-estimate.json",
        ),
        legal_value_entry(
            schema.label("10"),
            legal_value_from_dict(capital_results["ftc_starting_point"], "passive_ftc_carryover_2024_usd", country=USA_COUNTRY, section="capital_results.ftc_starting_point", provenance=provenance),
            currency=Currency.USD,
            source="us-capital-results.json",
            notes="2024 passive FTC carryover entering 2025.",
        ),
        legal_value_entry(
            schema.label("21"),
            legal_value_from_dict(tax_estimate["ftc"], "passive_ftc_limitation_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
            currency=Currency.USD,
            source="us-tax-estimate.json",
        ),
        legal_value_entry(
            schema.label("22"),
            legal_value_from_dict(tax_estimate["ftc"], "allowed_passive_ftc_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Smaller of line 14 (foreign tax) or line 21 (limitation).",
        ),
    ]
    if treaty_claimed:
        entries.append(
            legal_value_entry(
                schema.label("32_pub514_addon"),
                legal_value_from_dict(worksheet, "line_21_additional_credit_usd", country=USA_COUNTRY, section="treaty_resourcing_worksheet", provenance=provenance),
                currency=Currency.USD,
                source="us-treaty-package.json",
                notes="Publication 514 additional foreign tax credit on U.S. income (Certain Income Resourced by Treaty basket — see § 904(d)(6)).",
            )
        )
    else:
        entries.append(
            FormEntry(
                schema.label("treaty_resourcing_addon_na"),
                "Not applicable",
                source="us-treaty-package.json",
                notes="Treaty re-sourcing is not claimed in the selected posture.",
            )
        )
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_1116_passive.md",
        f"{paths.year} {schema.display_name}",
        posture_lines,
        entries,
        [
            "No separate treaty-only Form 1116 basket is used in the current packet.",
        ],
    )


def _write_form_1116_resourced(
    paths: YearPaths,
    tax_estimate: dict,
    treaty: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Form 1116 — Certain Income Resourced by Treaty (§ 904(d)(6) basket).

    C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03). Per Form 1116 instructions
    and IRS Publication 514, treaty re-sourced U.S.-source income is
    placed in a SEPARATE Form 1116 with the basket header "Certain
    Income Resourced by Treaty" (the § 904(d)(6) basket). Previously
    this was embedded as a single line-32 add-on inside the passive
    Form 1116; this renderer extracts it into its own Part I / Part II
    / Part III line set so the form is filing-ready.

    The renderer is gated on the executed Pub. 514 worksheet
    (``treaty_resourcing_worksheet.status == "computed"``) — when
    treaty re-sourcing is not claimed, the renderer no-ops. Per CLAUDE.md
    fail-closed posture, an explicit-zero resourced 1116 would be
    indistinguishable from a real return without re-sourcing.

    Per-line scalars (all from existing declared TREATY25-* / US25-*
    rule outputs):
    - **Part I Line 1a** — Re-sourced gross income (the U.S.-source
      dividends now treated as foreign-source per DBA-USA Art. 23(5)(c)).
      Source: ``treaty_resourcing.us_source_dividends_usd``.
    - **Part I Line 8** — Foreign tax paid on the re-sourced income
      (the German residence-state credit allocable to U.S.-source
      dividends after the treaty Art. 10(2)(b) ceiling).
      Source: ``treaty_resourcing.german_residence_credit_for_us_tax_usd``.
    - **Part III Line 10** — N/A (no carryover for the resourced
      basket; the basket is created annually by treaty election).
    - **Part III Line 21** — Resourced limitation (the dual-cap
      Pub. 514 worksheet line 21 = min(line 19, line 20c)).
      Source: ``treaty.worksheet_line_21_additional_credit_usd``.
    - **Part III Line 22** — Allowed credit (smaller of line 14 / 21).
      Source: ``treaty.treaty_resourcing_additional_ftc_usd``.
    - **Part III Line 32** — Total credit across all categories
      (sum carried to Form 1040 / Schedule 3 line 1).
      Source: ``tax_estimate.ftc.total_allowed_ftc_after_treaty_resourcing_usd``.
    - **Part III Line 33** — Smaller-of cap binding the nonrefundable
      credit. Source: ``treaty.us_tax_on_us_source_dividends_usd``
      (the regular U.S. tax on the re-sourced income).

    Authority:
    - 26 U.S.C. § 904(d)(6) (separate basket for treaty re-sourced
      income): https://www.law.cornell.edu/uscode/text/26/904
    - DBA-USA Art. 23(5)(c) (Relief from Double Taxation):
      https://www.irs.gov/pub/irs-trty/germany.pdf
    - IRS Publication 514 (Foreign Tax Credit for Individuals):
      https://www.irs.gov/publications/p514
    - IRS Form 1116 instructions:
      https://www.irs.gov/forms-pubs/about-form-1116
    """
    worksheet = treaty.get("treaty_resourcing_worksheet") or {}
    if str(worksheet.get("status", "")).strip().lower() != "computed":
        # Gated no-op: treaty re-sourcing is not claimed. The fail-
        # closed posture for "no re-sourcing election" is the absence
        # of the form file (an explicit-zero resourced 1116 would be
        # indistinguishable from a real return without re-sourcing).
        return
    treaty_resourcing = tax_estimate.get("treaty_resourcing") or {}
    ftc = tax_estimate.get("ftc") or {}
    schema = load_form_schema("form_1116_resourced")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_1116_resourced.md",
        f"{paths.year} {schema.display_name}",
        [
            "26 U.S.C. § 904(d)(6) creates a SEPARATE Form 1116 basket "
            "for income re-sourced by treaty. Per Form 1116 instructions, "
            'the basket header reads "Certain Income Resourced by Treaty" '
            "and Form 8833 disclosure is required (26 U.S.C. § 6114).",
            "DBA-USA Art. 23(5)(c) re-sources U.S.-source dividends to "
            "Germany so the Art. 10(2)(b) 15 % source-country ceiling "
            "is given effect through the foreign-tax credit; the dual "
            "cap (Pub. 514 worksheet line 19 / 20c → line 21) computes "
            "the additional U.S. credit allowed.",
            "No legal math is introduced by the renderer — every Line "
            "scalar is a declared rule output (TREATY25-* / US25-*) "
            "re-emitted through the I11 LegalValue boundary.",
        ],
        [
            legal_value_entry(
                schema.label("1a"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "us_source_dividends_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_1a",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.us_source_dividends_usd)",
                notes=(
                    "Re-sourced gross income: U.S.-source dividends "
                    "treated as foreign-source per DBA-USA Art. 23(5)(c)."
                ),
            ),
            legal_value_entry(
                schema.label("8"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "german_residence_credit_for_us_tax_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_8",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.german_residence_credit_for_us_tax_usd)",
                notes=(
                    "Foreign tax allocable to the re-sourced income — "
                    "German residence-state credit on U.S.-source "
                    "dividends after the Art. 10(2)(b) ceiling."
                ),
            ),
            legal_value_entry(
                schema.label("10"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "resourced_basket_carryover_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_10",
                    provenance=provenance,
                    provenance_output_key="treaty.resourced_basket_carryover",
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.resourced_basket_carryover_usd)",
                notes=(
                    "Form 1116 Line 10 (carryover from prior year) is "
                    "always zero for the § 904(d)(6) treaty-resourced "
                    "basket — the basket is created annually by treaty "
                    "election; carryovers under § 904(c) do not cross "
                    "treaty-basket boundaries. Surfaced as a declared "
                    "rule output (TREATY25-18 / "
                    "treaty.resourced_basket_carryover) for invariant I3."
                ),
            ),
            legal_value_entry(
                schema.label("21"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "worksheet_line_21_additional_credit_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_21",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.worksheet_line_21_additional_credit_usd)",
                notes=(
                    "Pub. 514 worksheet line 21 = min(line 19, line "
                    "20c) — the dual-cap on the re-sourced credit."
                ),
            ),
            legal_value_entry(
                schema.label("22"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "treaty_resourcing_additional_ftc_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_22",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.treaty_resourcing_additional_ftc_usd)",
                notes=(
                    "Smaller of foreign tax (Line 14) and limitation "
                    "(Line 21). For the treaty-resourced basket this "
                    "equals worksheet line 21 by construction."
                ),
            ),
            legal_value_entry(
                schema.label("32"),
                legal_value_from_dict(
                    ftc,
                    "total_allowed_ftc_after_treaty_resourcing_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_32",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (ftc.total_allowed_ftc_after_treaty_resourcing_usd)",
                notes=(
                    "Total Form 1116 credit across all baskets "
                    "(Passive + General + Resourced). Carries to "
                    "Schedule 3 line 1."
                ),
            ),
            legal_value_entry(
                schema.label("33"),
                legal_value_from_dict(
                    treaty_resourcing,
                    "us_tax_on_us_source_dividends_usd",
                    country=USA_COUNTRY,
                    section="form_1116_resourced.line_33",
                    provenance=provenance,
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json (treaty_resourcing.us_tax_on_us_source_dividends_usd)",
                notes=(
                    "Smaller-of cap (Line 33). Total nonrefundable "
                    "credit cannot exceed the U.S. regular tax on the "
                    "re-sourced income; Pub. 514 worksheet line 19 "
                    "implements this constraint."
                ),
            ),
        ],
        [
            "Authority for the separate basket: 26 U.S.C. § 904(d)(6) "
            "(https://www.law.cornell.edu/uscode/text/26/904).",
            "Authority for treaty re-sourcing: DBA-USA Art. 23(5)(c) "
            "(https://www.irs.gov/pub/irs-trty/germany.pdf).",
            f"IRS Publication 514 (worksheet authority): {IRS_P514}.",
            f"IRS Form 1116 instructions: {IRS_ABOUT_FORM_1116_URL}.",
            "Form 8833 disclosure requirement: 26 U.S.C. § 6114 / "
            "26 C.F.R. § 301.6114-1 (rendered separately in this "
            "package when LOB qualified).",
        ],
    )


def _write_form_1116_general(paths: YearPaths, tax_estimate: dict, capital_results: dict, provenance: Mapping[str, Any] | None) -> None:
    ftc = tax_estimate["ftc"]
    income = tax_estimate["income"]
    ftc_starting_point = capital_results["ftc_starting_point"]
    schema = load_form_schema("form_1116_general")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_1116_general.md",
        f"{paths.year} {schema.display_name}",
        [
            "General-category foreign tax credit is the Germany wage basket in the saved 2025 model.",
            "IRS Form 1116 line numbers match the 2024-revision; confirm against the 2025 PDF before filing: https://www.irs.gov/forms-pubs/about-form-1116",
        ],
        [
            legal_value_entry(
                schema.label("1a_germany_wages"),
                legal_value_from_dict(income, "wages_usd", country=USA_COUNTRY, section="tax_estimate.income", provenance=provenance),
                currency=Currency.USD,
                source="us-tax-estimate.json",
            ),
            legal_value_entry(
                schema.label("8"),
                legal_value_from_dict(ftc, "current_year_general_foreign_tax_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
                currency=Currency.USD,
                source="us-tax-estimate.json",
                notes="Allocated share of the joint 2025 German wage-side tax.",
            ),
            legal_value_entry(
                schema.label("10"),
                legal_value_from_dict(ftc_starting_point, "general_ftc_carryover_2024_usd", country=USA_COUNTRY, section="capital_results.ftc_starting_point", provenance=provenance),
                currency=Currency.USD,
                source="us-capital-results.json",
                notes="2024 general FTC carryover entering 2025.",
            ),
            legal_value_entry(
                schema.label("21"),
                legal_value_from_dict(ftc, "general_ftc_limitation_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
                currency=Currency.USD,
                source="us-tax-estimate.json",
            ),
            legal_value_entry(
                schema.label("22"),
                legal_value_from_dict(ftc, "allowed_general_ftc_usd", country=USA_COUNTRY, section="tax_estimate.ftc", provenance=provenance),
                currency=Currency.USD,
                source="us-tax-estimate.json",
                notes="Smaller of line 14 (foreign tax) or line 21 (limitation).",
            ),
        ],
        [
            "The 2024 German redetermination stays in accrued-basis carryover/redetermination support, not as a fresh 2025 cash-basis credit.",
        ],
    )


def _write_form_2555(
    paths: YearPaths,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> None:
    """Render Form 2555 — Foreign Earned Income Exclusion (gated on § 911 election).

    C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03). Form 2555 is the IRS form
    on which a U.S. citizen or resident elects 26 U.S.C. § 911(a) to
    exclude foreign earned income (and § 911(c) housing exclusion /
    deduction). The renderer is gated on
    ``tax_estimate['feie']['elected'] == True``; when the election is
    not made (the brenn-2025 default posture), this renderer no-ops
    and the form does not appear in the package.

    Per-line scalars:
    - **Line 36** — Annual FEIE (§ 911(b)(2)(D) cap-bound annual amount).
      Source: ``us.feie.line_36_excluded_amount_usd`` (US25-FEIE).
    - **Line 45** — Housing exclusion (§ 911(c)(4) employer-provided
      portion). Source: ``us.feie.line_45_housing_exclusion_usd``
      (US25-FEIE).
    - **Line 50** — Housing deduction (§ 911(c)(5) self-employed
      portion). Source: ``us.feie.line_50_housing_deduction_usd``
      (US25-FEIE).

    No legal math runs in the renderer; each scalar is a declared
    rule output flowing through the I11 LegalValue envelope.

    Authority:
    - 26 U.S.C. § 911 (Foreign Earned Income Exclusion):
      https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
    - IRS Form 2555: https://www.irs.gov/forms-pubs/about-form-2555
    - IRS Publication 54 (Tax Guide for U.S. Citizens / Residents
      Abroad): https://www.irs.gov/publications/p54
    - IRS Notice 2024-77 (2025 § 911 cap and housing-exclusion limits):
      https://www.irs.gov/pub/irs-drop/n-24-77.pdf
    """
    feie = tax_estimate.get("feie") or {}
    elected = bool(feie.get("elected", False))
    if not elected:
        # Gated no-op: § 911 election not made. The fail-closed posture
        # for "no FEIE election" is the absence of the form file (an
        # explicit zero-amount Form 2555 would be indistinguishable
        # from a real FEIE return with $0 of foreign earned income).
        return
    schema = load_form_schema("form_2555")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_2555.md",
        f"{paths.year} {schema.display_name}",
        [
            "26 U.S.C. § 911(a) elects to exclude foreign earned income; "
            "§ 911(c) elects the housing exclusion (employer-provided "
            "portion) and / or housing deduction (self-employed portion).",
            "§ 911(d)(6) denies a foreign-tax credit on the excluded "
            "income (the disallowance flows into US25-11 FTC); "
            "§ 1411(d)(1)(A) adds the excluded amount back to NIIT MAGI "
            "(the add-back flows into US25-20 NIIT).",
            "No legal math is introduced by the renderer — every Line "
            "scalar is a declared rule output (US25-FEIE) re-emitted "
            "through the I11 LegalValue boundary.",
            f"Authority: {IRS_FORM_2555_URL}",
        ],
        [
            legal_value_entry(
                schema.label("36"),
                legal_value_from_dict(
                    feie,
                    "line_36_excluded_amount_usd",
                    country=USA_COUNTRY,
                    section="form_2555.line_36",
                    provenance=provenance,
                    provenance_output_key="us.feie.line_36_excluded_amount_usd",
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json",
                notes=(
                    "26 U.S.C. § 911(b)(2)(D) — Foreign Earned Income "
                    "Exclusion (annual amount, capped by the § 911(b)(2)(D) "
                    "indexed limit; for 2025 the cap is $130,000 per IRS "
                    "Notice 2024-77, prorated by qualifying days when the "
                    "qualifying period spans <365 days)."
                ),
            ),
            legal_value_entry(
                schema.label("45"),
                legal_value_from_dict(
                    feie,
                    "line_45_housing_exclusion_usd",
                    country=USA_COUNTRY,
                    section="form_2555.line_45",
                    provenance=provenance,
                    provenance_output_key="us.feie.line_45_housing_exclusion_usd",
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json",
                notes=(
                    "26 U.S.C. § 911(c)(4) — Housing exclusion (employer-"
                    "provided portion). Excess over the § 911(c) base "
                    "housing amount, capped by the § 911(c)(2) location-"
                    "adjusted ceiling."
                ),
            ),
            legal_value_entry(
                schema.label("50"),
                legal_value_from_dict(
                    feie,
                    "line_50_housing_deduction_usd",
                    country=USA_COUNTRY,
                    section="form_2555.line_50",
                    provenance=provenance,
                    provenance_output_key="us.feie.line_50_housing_deduction_usd",
                ),
                currency=Currency.USD,
                source="us-tax-estimate.json",
                notes=(
                    "26 U.S.C. § 911(c)(5) — Housing deduction (self-"
                    "employed portion). Reduces self-employment income "
                    "for AGI purposes; the § 911(c)(2) ceiling still binds."
                ),
            ),
        ],
        [
            f"Authority for FEIE: 26 U.S.C. § 911 ({USC_911_URL}).",
            "Authority for the 2025 cap and housing-exclusion limits: IRS "
            "Notice 2024-77 (https://www.irs.gov/pub/irs-drop/n-24-77.pdf).",
            f"Confirm rendered values against the official IRS Form 2555 PDF: {IRS_FORM_2555_URL}.",
            "IRS Publication 54 (Tax Guide for U.S. Citizens / Residents "
            "Abroad): https://www.irs.gov/publications/p54",
        ],
    )


def _write_form_8833(paths: YearPaths, treaty: dict) -> None:
    """Render Form 8833 — Treaty-Based Return Position Disclosure.

    Authority:
      - 26 U.S.C. § 6114 (treaty-based return position disclosure)
        https://www.law.cornell.edu/uscode/text/26/6114
      - 26 C.F.R. § 301.6114-1 (regulations implementing § 6114)
        https://www.law.cornell.edu/cfr/text/26/301.6114-1
      - DBA-USA Art. 28 (Limitation on Benefits, 2006 Protocol)
        https://www.irs.gov/pub/irs-trty/germany.pdf
      - IRS Form 8833 landing page
        https://www.irs.gov/forms-pubs/about-form-8833

    The form is the disclosure that accompanies a treaty-based return
    position. For the saved 2025 posture (U.S. citizen resident in
    Germany claiming the DBA-USA Art. 23 / Pub. 514 re-sourcing of
    U.S.-source dividends to allow the Art. 23 source-country credit
    floor) the disclosed articles are 23 (relief from double taxation),
    28 (limitation on benefits), and 10 (dividend-rate ceiling). The
    renderer is gated on
    ``treaty['chosen_position']['form_8833_required'] == 'yes'``;
    when treaty re-sourcing is not claimed (or LOB qualification is
    ``not_qualified``) the rule output flips to ``no`` and this
    renderer no-ops, so the form does not appear in the package.

    Form 8833 carries no Decimal amounts (the only amount field, Line 6,
    is a dollar-figure aid we leave unfilled here because the disclosure
    is qualitative — the user verifies the underlying treaty-resourcing
    credit on Form 1116 / Pub. 514). Every row is therefore a plain
    identity / disclosure entry; invariant I3 / I11 do not apply because
    no ``legal_value_entry(...)`` calls are emitted.
    """
    chosen = treaty["chosen_position"]
    if str(chosen.get("form_8833_required", "no")).strip().lower() != "yes":
        return
    lob_category = str(chosen.get("lob_category", "")).strip()
    treaty_resourcing_claimed = str(chosen.get("treaty_resourcing_claimed", "no")).strip().lower() == "yes"
    schema = load_form_schema("form_8833")
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_8833.md",
        f"{paths.year} {schema.display_name}",
        [
            "26 U.S.C. § 6114 / 26 C.F.R. § 301.6114-1 require disclosure when a U.S. taxpayer claims a treaty-based return position.",
            (
                "The saved posture claims DBA-USA Art. 23 re-sourcing of U.S.-source dividends so the Art. 23 source-country credit floor allows additional Form 1116 credit (Pub. 514 worksheet)."
                if treaty_resourcing_claimed
                else "Treaty re-sourcing is not claimed in the chosen filing posture; this disclosure file is generated because the LOB stage flagged a Form 8833 obligation."
            ),
            f"Authority: {IRS_FORM_8833_URL}",
        ],
        [
            FormEntry(schema.label("1a_treaty_country"), "Germany", source="us-treaty-package.json"),
            FormEntry(
                schema.label("1b_treaty_articles"),
                "Article 23 (Relief from Double Taxation); Article 28 (Limitation on Benefits, 2006 Protocol); Article 10 (Dividends)",
                source="us-treaty-package.json",
                notes="Re-sourcing claim relies on Art. 23(5)(c) (U.S.-source items deemed to arise in Germany for U.S. citizens) read with Art. 23(5)(b) (U.S. credit for the German tax), the Art. 10(2)(b) 15 % portfolio-dividend ceiling and Art. 28 LOB qualification.",
            ),
            FormEntry(
                schema.label("2_irc_provisions"),
                "26 U.S.C. § 6114; 26 C.F.R. § 301.6114-1",
                source="us-treaty-package.json",
            ),
            FormEntry(
                schema.label("3_payer"),
                "Not applicable - individual income tax return; treaty re-sourcing is at the taxpayer level, not a withholding-agent payer claim.",
                source="us-treaty-package.json",
            ),
            FormEntry(
                schema.label("4_position_provided_by_reg"),
                "Yes - the position reduces U.S. tax under Reg. § 301.6114-1(b)(4)(ii) (re-sourcing of U.S.-source income to allow the Art. 23 foreign tax credit).",
                source="us-treaty-package.json",
            ),
            FormEntry(
                schema.label("5_subject_to_penalty"),
                "No - this disclosure is filed timely with Form 1040 to satisfy § 6114; the § 6712 penalty for failure-to-disclose does not apply when timely filed.",
                source="us-treaty-package.json",
            ),
            FormEntry(
                schema.label("6_explanation"),
                (
                    "The taxpayer is a U.S. citizen resident in Germany and qualifies under DBA-USA Art. 28 "
                    f"(LOB category: {lob_category or 'qualified_resident'}). "
                    "Pursuant to Art. 23(5)(c) of the 1989 U.S.-Germany income tax treaty (as amended by the 2006 Protocol), U.S.-source dividends "
                    "are re-sourced to Germany to the extent necessary so the Art. 10(2)(b) 15 % ceiling is given effect through the Art. 23 "
                    "foreign tax credit on the German return. The additional foreign tax credit on the U.S. side is computed via the "
                    "IRS Publication 514 'Additional Foreign Tax Credit on U.S. Income' worksheet attached to Form 1116."
                ),
                source="us-treaty-package.json",
                notes="Pub. 514 worksheet line 21 is added to Form 1116 Part III line 12 and Part IV line 32; the Form 1116 line 33 cap still binds the allowed credit.",
            ),
        ],
        [
            "26 U.S.C. § 6114: https://www.law.cornell.edu/uscode/text/26/6114",
            "26 C.F.R. § 301.6114-1: https://www.law.cornell.edu/cfr/text/26/301.6114-1",
            "DBA-USA (1989, as amended by the 2006 Protocol): https://www.irs.gov/pub/irs-trty/germany.pdf",
            "Confirm the rendered language against the official IRS Form 8833 PDF before filing: https://www.irs.gov/forms-pubs/about-form-8833",
        ],
    )


def _write_form_8938_status(
    paths: YearPaths,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> bool:
    """Render the Form 8938 (FATCA) filing-determination status sheet.

    Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03). The renderer surfaces
    the US25-FATCA-FBAR-DETERMINATION outputs as a determination-only
    status sheet. This is NOT a fillable Form 8938 — Form 8938 has
    Part V / Part VI per-account detail that requires per-account
    enumeration the engine does not yet model.

    Three render branches:
      1. ``status="not_applicable"`` — workspace lacks foreign-account
         data; surface manual-determination text + the column schema
         the user must populate. Per CLAUDE.md fail-closed posture.
      2. ``status="determined"`` AND ``form_8938_required=true`` —
         REQUIRED verdict with the threshold and SFFA aggregates.
      3. ``status="determined"`` AND ``form_8938_required=false`` —
         NOT REQUIRED verdict (still surfaces threshold + aggregate).

    Returns True iff the file was written, so the index can list it.

    I3 design choice (Group D audit, 2026-05-03) — STATUS SHEET, NOT A
    TRANSCRIPTION TARGET. The labels here ("Threshold - end of year",
    "Specified foreign financial assets - max during year", etc.) are
    DESCRIPTIVE rather than ``"Line N"`` form-line labels, so the I3
    scanner (``tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py``)
    deliberately skips them via the ``_LINE_LABEL_RE`` filter. The
    rationale: this file is a *determination* of whether the user must
    file Form 8938, not a transcription onto specific Form 8938 lines —
    the engine does not (yet) emit Part I / Part V / Part VI per-account
    rows. If a future workstream renders the actual Form 8938 form (with
    statutory line numbers), the new renderer MUST switch to ``"Line N"``
    labels and declare matching ``OutputDeclaration.form_line_refs`` so
    the bidirectional I3 invariant fires. Do not introduce ``"Line N"``
    labels here without paired ``form_line_refs`` declarations.

    Authority:
      - 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
      - 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
      - IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
      - IRS comparison Form 8938 vs FBAR —
        https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements
    """
    fatca = tax_estimate.get("fatca_fbar") or {}
    if not fatca:
        # Tax-estimate JSON missing the block — happens only if the
        # rule graph hasn't been re-run after Group D landed. Skip
        # silently rather than crash; the I3 / I11 audits do not
        # require this sheet to exist on every workspace.
        return False
    schema = load_form_schema("form_8938_status")
    status = str(fatca.get("status", "")).strip().lower()
    filing_status_label = str(fatca.get("filing_status_label", "")).strip()
    residency_basis = str(fatca.get("residency_basis", "")).strip()
    posture = [
        f"Filing status: `{filing_status_label or 'unknown'}`.",
        f"Residency basis (Reg. § 1.6038D-2(b)(1)): `{residency_basis or 'unknown'}`.",
        (
            "26 U.S.C. § 6038D requires Form 8938 attachment when specified "
            "foreign financial assets exceed filing-status- and residency-"
            "dependent thresholds (Reg. § 1.6038D-2(b))."
        ),
        (
            "Form 8938 is filed WITH Form 1040; the separate FBAR (FinCEN "
            "Form 114) is filed with FinCEN — the two regimes overlap but "
            "are distinct."
        ),
    ]
    notes = [
        f"26 U.S.C. § 6038D: {USC_6038D_URL}",
        f"26 CFR § 1.6038D-2: {CFR_1_6038D_2_URL}",
        f"IRS Form 8938: {IRS_FORM_8938_URL}",
        f"IRS Form 8938 vs FBAR: {IRS_FORM_8938_VS_FBAR_URL}",
        (
            "This is a determination-only status sheet, NOT the actual "
            "Form 8938. Confirm threshold, asset list, and Part V / VI "
            "per-account detail against the official IRS Form 8938 PDF "
            "before filing."
        ),
    ]
    if status == "not_applicable":
        # Manual-determination posture: data not yet structured.
        reason = str(fatca.get("reason", "")).strip()
        # Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-account
        # discovered list. Each entry is identity-only (no balances, no
        # Decimal math). The list is rendered as plain ``FormEntry``
        # rows below the determination row so the user sees "fill in
        # balances for THESE accounts" rather than "populate this CSV
        # from scratch".
        discovered = fatca.get("discovered_accounts") or []
        if not isinstance(discovered, list):
            discovered = []
        entries: list[FormEntry] = [
            FormEntry(
                schema.label("filing_status"),
                filing_status_label or "(missing)",
                source="config/profile.json",
            ),
            FormEntry(
                schema.label("residency_basis"),
                residency_basis or "(missing)",
                source="config/profile.json",
            ),
            FormEntry(
                schema.label("determination_status_manual"),
                "MANUAL DETERMINATION REQUIRED",
                source="us-tax-estimate.json",
                notes=(
                    "26 U.S.C. § 6038D thresholds cannot be evaluated "
                    "without a populated foreign-financial-accounts.csv "
                    "and the data_complete marker."
                ),
            ),
        ]
        if discovered:
            entries.append(
                FormEntry(
                    schema.label("auto_discovered_accounts"),
                    str(len(discovered)),
                    source="outputs/tax-positions/foreign-financial-accounts-derived.csv",
                    notes=(
                        "Identity-only stubs scanned from extracted facts. "
                        "Balances are placeholders pending manual entry."
                    ),
                )
            )
            for account in discovered:
                if not isinstance(account, dict):
                    continue
                account_id = str(account.get("account_id", "")).strip()
                country = str(account.get("country", "")).strip()
                institution = str(account.get("institution", "")).strip()
                account_type = str(account.get("account_type", "")).strip()
                currency = str(account.get("currency", "")).strip()
                is_sffa = bool(
                    account.get("is_specified_foreign_financial_asset", False)
                )
                entries.append(
                    FormEntry(
                        f"Discovered account: {account_id}",
                        f"{institution} ({country}, {account_type}, {currency})",
                        source="outputs/tax-positions/foreign-financial-accounts-derived.csv",
                        notes=(
                            f"SFFA scope: {'yes' if is_sffa else 'no'}. "
                            "Edit normalized/facts/foreign-financial-accounts.csv "
                            "to enter the verified usd_eoy_balance and "
                            "usd_max_balance_during_year for this account."
                        ),
                    )
                )
        write_form(
            paths.usa_forms_root / f"{paths.year}_form_8938_status.md",
            f"{paths.year} {schema.display_name} (Manual)",
            posture
            + [
                "**Determination: MANUAL DETERMINATION REQUIRED.**",
                f"Reason: {reason}",
                (
                    "Required input columns in "
                    "`years/<workspace>/normalized/facts/foreign-financial-accounts.csv`: "
                    "account_id, country, institution, account_type "
                    "(bank | brokerage | pension | insurance | other), "
                    "currency, usd_max_balance_during_year, usd_eoy_balance, "
                    "is_specified_foreign_financial_asset (true/false). "
                    "Mark the file complete by adding a sentinel row "
                    "`account_id=__data_complete__` OR creating a "
                    "`foreign-financial-accounts.complete` marker file alongside it."
                ),
            ],
            entries,
            notes,
        )
        return True
    # Determined branch — surface aggregates + threshold.
    determination_text = (
        "REQUIRED — attach Form 8938 to Form 1040."
        if bool(fatca.get("form_8938_required", False))
        else "NOT REQUIRED — specified foreign financial assets do not exceed the applicable thresholds."
    )
    entries = [
        FormEntry(
            schema.label("filing_status"),
            filing_status_label,
            source="config/profile.json",
        ),
        FormEntry(
            schema.label("residency_basis"),
            residency_basis,
            source="config/profile.json",
        ),
        legal_value_entry(
            schema.label("threshold_eoy"),
            legal_value_from_dict(
                fatca,
                "form_8938_threshold_eoy_usd",
                country=USA_COUNTRY,
                section="fatca_fbar.threshold_eoy",
                provenance=provenance,
                provenance_output_key="us.fatca.form_8938_threshold_eoy_usd",
            ),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Reg. § 1.6038D-2(b) end-of-year threshold for this filing-status / residency tier.",
        ),
        legal_value_entry(
            schema.label("threshold_anytime"),
            legal_value_from_dict(
                fatca,
                "form_8938_threshold_anytime_usd",
                country=USA_COUNTRY,
                section="fatca_fbar.threshold_anytime",
                provenance=provenance,
                provenance_output_key="us.fatca.form_8938_threshold_anytime_usd",
            ),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Reg. § 1.6038D-2(b) max-during-year threshold for this filing-status / residency tier.",
        ),
        legal_value_entry(
            schema.label("sffa_max"),
            legal_value_from_dict(
                fatca,
                "foreign_specified_assets_max_usd",
                country=USA_COUNTRY,
                section="fatca_fbar.sffa_max",
                provenance=provenance,
                provenance_output_key="us.fatca.foreign_specified_assets_max_usd",
            ),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Sum of per-account max balance during year for SFFA-tagged rows.",
        ),
        legal_value_entry(
            schema.label("sffa_eoy"),
            legal_value_from_dict(
                fatca,
                "foreign_specified_assets_eoy_usd",
                country=USA_COUNTRY,
                section="fatca_fbar.sffa_eoy",
                provenance=provenance,
                provenance_output_key="us.fatca.foreign_specified_assets_eoy_usd",
            ),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Sum of per-account EOY balance for SFFA-tagged rows.",
        ),
        FormEntry(
            schema.label("determination"),
            determination_text,
            source="us-tax-estimate.json",
            notes="Form 8938 attaches if EOY > EOY-threshold OR max-during-year > anytime-threshold (Reg. § 1.6038D-2(a)).",
        ),
        FormEntry(
            schema.label("account_count"),
            str(int(fatca.get("account_count", 0))),
            source="normalized/facts/foreign-financial-accounts.csv",
        ),
    ]
    write_form(
        paths.usa_forms_root / f"{paths.year}_form_8938_status.md",
        f"{paths.year} {schema.display_name}",
        posture,
        entries,
        notes,
    )
    return True


def _fbar_manual_entries(
    fatca: dict,
    provenance: Mapping[str, Any] | None,
) -> list[FormEntry]:
    """Build the manual-determination entries for the FBAR status sheet.

    Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): when the manual CSV
    is empty but the auto-derivation produced stub rows, surface each
    discovered foreign account as its own ``FormEntry`` so the user
    sees "fill in balances for THESE accounts" rather than a bare
    "populate this CSV from scratch" stub. Identity-only — balances are
    not legal values here, the FBAR threshold IS via legal_value_entry.
    """
    schema = load_form_schema("fincen_114_status")
    discovered = fatca.get("discovered_accounts") or []
    if not isinstance(discovered, list):
        discovered = []
    entries: list[FormEntry] = [
        FormEntry(
            schema.label("determination_status_manual"),
            "MANUAL DETERMINATION REQUIRED",
            source="us-tax-estimate.json",
            notes=(
                "Aggregate foreign-account balance cannot be "
                "evaluated without a populated "
                "foreign-financial-accounts.csv."
            ),
        ),
        legal_value_entry(
            schema.label("fbar_aggregate_threshold"),
            legal_value_from_decimal(
                FBAR_AGGREGATE_THRESHOLD_USD,
                country=USA_COUNTRY,
                section="fatca_fbar.fbar_threshold",
                output_key="us.fbar.aggregate_threshold_usd",
                provenance=provenance,
            ),
            currency=Currency.USD,
            source="y2025.us_law.FBAR_AGGREGATE_THRESHOLD_USD",
            notes="31 CFR § 1010.350(a) — fixed at $10,000 (not inflation-indexed).",
        ),
    ]
    if discovered:
        entries.append(
            FormEntry(
                schema.label("auto_discovered_accounts"),
                str(len(discovered)),
                source="outputs/tax-positions/foreign-financial-accounts-derived.csv",
                notes=(
                    "Identity-only stubs scanned from extracted facts. "
                    "Aggregate FBAR threshold check requires per-account "
                    "max-during-year balances — fill them in manually."
                ),
            )
        )
        for account in discovered:
            if not isinstance(account, dict):
                continue
            account_id = str(account.get("account_id", "")).strip()
            country = str(account.get("country", "")).strip()
            institution = str(account.get("institution", "")).strip()
            account_type = str(account.get("account_type", "")).strip()
            currency = str(account.get("currency", "")).strip()
            entries.append(
                FormEntry(
                    f"Discovered account: {account_id}",
                    f"{institution} ({country}, {account_type}, {currency})",
                    source="outputs/tax-positions/foreign-financial-accounts-derived.csv",
                    notes=(
                        "FBAR scope is broader than § 6038D — every foreign "
                        "financial account counts toward the $10,000 aggregate. "
                        "Confirm signature authority on shared / spousal "
                        "accounts before excluding them."
                    ),
                )
            )
    return entries


def _write_fincen_114_status(
    paths: YearPaths,
    tax_estimate: dict,
    provenance: Mapping[str, Any] | None,
) -> bool:
    """Render the FinCEN Form 114 (FBAR) filing-determination status sheet.

    Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03). FBAR is filed with
    FinCEN (the BSA E-Filing System), NOT with the IRS. The status
    sheet only reports the determination — the actual filing is the
    user's responsibility through the FinCEN web UI.

    Returns True iff the file was written.

    I3 design choice — see the parallel comment on
    ``_write_form_8938_status``. Labels are descriptive, not ``"Line N"``
    transcription targets; FinCEN Form 114 has its own line-numbered
    schema (Part II / Part III per-account rows) that the engine does
    not yet emit. If a future workstream renders the actual FinCEN 114
    PDF rows it MUST use ``"Line N"`` labels with paired
    ``OutputDeclaration.form_line_refs`` so the bidirectional I3
    invariant fires.

    Authority:
      - 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
      - 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
      - FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/
    """
    fatca = tax_estimate.get("fatca_fbar") or {}
    if not fatca:
        return False
    schema = load_form_schema("fincen_114_status")
    status = str(fatca.get("status", "")).strip().lower()
    posture = [
        (
            "31 U.S.C. § 5314 / 31 CFR § 1010.350(a) require U.S. persons "
            "with aggregate foreign financial accounts exceeding $10,000 at "
            "any point during the calendar year to file FinCEN Form 114 (FBAR)."
        ),
        (
            "FBAR is filed SEPARATELY with FinCEN through the BSA E-Filing "
            f"System ({FINCEN_BSA_EFILING_URL}); it is NOT attached to "
            "Form 1040. Due date is April 15 with an automatic extension to "
            "October 15."
        ),
        (
            "FBAR scope is broader than Form 8938: every foreign financial "
            "account counts toward the $10,000 aggregate, including "
            "signature-only authority on a non-owned account."
        ),
    ]
    notes = [
        f"31 U.S.C. § 5314: {USC_31_5314_URL}",
        f"31 CFR § 1010.350: {CFR_31_1010_350_URL}",
        f"FinCEN BSA E-Filing: {FINCEN_BSA_EFILING_URL}",
        f"IRS Form 8938 vs FBAR comparison: {IRS_FORM_8938_VS_FBAR_URL}",
        (
            "This is a determination-only status sheet, NOT the actual "
            "FinCEN Form 114. The filing happens through FinCEN's web UI."
        ),
    ]
    if status == "not_applicable":
        reason = str(fatca.get("reason", "")).strip()
        write_form(
            paths.usa_forms_root / f"{paths.year}_fincen_114_status.md",
            f"{paths.year} {schema.display_name} (Manual)",
            posture
            + [
                "**Determination: MANUAL DETERMINATION REQUIRED.**",
                f"Reason: {reason}",
                (
                    "Required input columns in "
                    "`years/<workspace>/normalized/facts/foreign-financial-accounts.csv`: "
                    "account_id, country, institution, account_type, "
                    "currency, usd_max_balance_during_year (used for FBAR "
                    "aggregate), usd_eoy_balance, "
                    "is_specified_foreign_financial_asset."
                ),
            ],
            _fbar_manual_entries(fatca, provenance),
            notes,
        )
        return True
    determination_text = (
        "REQUIRED — file FinCEN Form 114 separately via the BSA E-Filing System."
        if bool(fatca.get("fincen_114_required", False))
        else "NOT REQUIRED — aggregate foreign-account balance does not exceed $10,000 at any point during the year."
    )
    entries = [
        legal_value_entry(
            schema.label("fbar_threshold_31_cfr"),
            legal_value_from_decimal(
                FBAR_AGGREGATE_THRESHOLD_USD,
                country=USA_COUNTRY,
                section="fatca_fbar.fbar_threshold",
                output_key="us.fbar.aggregate_threshold_usd",
                provenance=provenance,
            ),
            currency=Currency.USD,
            source="y2025.us_law.FBAR_AGGREGATE_THRESHOLD_USD",
            notes="Fixed statutory threshold; not inflation-indexed.",
        ),
        legal_value_entry(
            schema.label("aggregate_max_balance"),
            legal_value_from_dict(
                fatca,
                "fbar_aggregate_max_balance_usd",
                country=USA_COUNTRY,
                section="fatca_fbar.fbar_aggregate_max",
                provenance=provenance,
                provenance_output_key="us.fbar.aggregate_max_balance_usd",
            ),
            currency=Currency.USD,
            source="us-tax-estimate.json",
            notes="Sum across all foreign financial accounts (FBAR scope is broader than § 6038D).",
        ),
        FormEntry(
            schema.label("determination"),
            determination_text,
            source="us-tax-estimate.json",
            notes="FBAR attaches if aggregate max balance during year exceeds $10,000 (31 CFR § 1010.350(a)).",
        ),
        FormEntry(
            schema.label("account_count"),
            str(int(fatca.get("account_count", 0))),
            source="normalized/facts/foreign-financial-accounts.csv",
        ),
        FormEntry(
            schema.label("filing_system"),
            FINCEN_BSA_EFILING_URL,
            source="31 CFR § 1010.350(g)",
            notes="Filed separately from Form 1040, online with FinCEN.",
        ),
    ]
    write_form(
        paths.usa_forms_root / f"{paths.year}_fincen_114_status.md",
        f"{paths.year} {schema.display_name}",
        posture,
        entries,
        notes,
    )
    return True


def render_usa_forms(paths: YearPaths) -> None:
    _ensure_supported_year(paths)
    clear_markdown_outputs(paths.usa_forms_root)
    final_output = load_final_legal_output_2025(paths)
    forms = final_output["usa"]["forms"]
    treaty = forms["treaty_package"]
    get_posture_definition("usa", _usa_posture_from_treaty_packet(treaty))
    tax_estimate = forms["tax_estimate"]
    capital_results = forms["capital_results"]
    bucket_rows = forms["bucket_rows"]
    trace_rows = forms["trace_rows"]
    ftc_support_rows = forms["ftc_support_rows"]
    schedule_d_entries = _required_schedule_d_entries(forms)
    # Invariant I11 / F-CQ-1: thread the per-rule-output provenance map
    # to the form-line adapters. When a rule output_key matches a form-
    # line key the adapter pulls the executor's StageResult fingerprint
    # from this block; otherwise it synthesizes a deterministic
    # (renderer:US:section, line_key, value) fingerprint.
    provenance = final_output.get("_provenance")

    _write_index(paths, treaty, tax_estimate)
    _write_1040(paths, treaty, provenance)
    _write_schedule_1(paths, capital_results, provenance)
    _write_schedule_b(paths, capital_results, provenance)
    _write_schedule_d(paths, schedule_d_entries)
    _write_form_8949(paths, bucket_rows, provenance)
    _write_form_6781(paths, capital_results, provenance)
    # F-US-1: render Form 6251 (Alternative Minimum Tax) before Form 8960 so
    # the AMT result is available alongside NIIT in the package index.
    _write_form_6251(paths, treaty, provenance)
    # 26 U.S.C. § 24 — Schedule 8812 carries CTC (line 14 → Form 1040 line 19)
    # and refundable ACTC (line 27 → Form 1040 line 28). For the demo posture
    # with header-only ``config/children.csv`` every line renders zero, which
    # leaves the existing demo numerics unchanged.
    _write_schedule_8812(paths, treaty, provenance)
    # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 (Additional Taxes) under
    # 26 U.S.C. §§ 55 / 1401 / 3101(b)(2) / 1411. Lines 1, 3 (Part I) and
    # 4, 11, 12, 21 (Part II) carry to Form 1040 lines 17 / 23 from the
    # declared ``us.tax.schedule_2_*`` rule outputs.
    _write_schedule_2(paths, treaty, provenance)
    # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 (Additional Credits and
    # Payments). Line 1 (post-treaty FTC), line 6c (other refundable),
    # line 8 (Part I total = line 1 in the supported posture), line 11
    # (treaty resourcing add-on per Pub. 514 worksheet line 21).
    _write_schedule_3(paths, treaty, provenance)
    # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE (Self-Employment Tax)
    # under 26 U.S.C. §§ 1401, 1402(a)(12). Gated on net SE earnings >
    # Phase 2 (FREELANCER-US-SCHEDULE-C) — Schedule C (Profit or Loss From
    # Business) under 26 U.S.C. § 61 / § 162. Gated on a declared Schedule C
    # position (net profit ≠ 0 or gross receipts > 0). IRS-VERIFIED 2026-06-13
    # against the 2025 Schedule C PDF: renders lines 7/28/31.
    _write_schedule_c(paths, treaty, tax_estimate, provenance)
    # 0; renders lines 2/3/4a/4c/6/8a/10/11/12.
    _write_schedule_se(paths, treaty, tax_estimate, provenance)
    # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 (Additional Medicare Tax)
    # under 26 U.S.C. §§ 3101(b)(2) / 1401(b)(2). Gated on Schedule 2
    # line 11 > 0; renders Part I (lines 1, 4-7) and Part II (lines 8,
    # 11-13) plus the line-18 total.
    _write_form_8959(paths, treaty, tax_estimate, provenance)
    # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 (NIIT) line-level
    # decomposition. Renders Part I (lines 1, 2, 5a-5d), Part III line
    # 8 (total investment income), line 12 (NII), and line 17 (NIIT
    # scalar) from declared ``us.tax.form_8960_*`` rule outputs.
    _write_form_8960(paths, trace_rows, tax_estimate, treaty, provenance)
    _write_form_1116_passive(paths, tax_estimate, ftc_support_rows, treaty, capital_results, provenance)
    _write_form_1116_general(paths, tax_estimate, capital_results, provenance)
    # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 1116 — Certain
    # Income Resourced by Treaty (§ 904(d)(6) basket). Renders as a
    # SEPARATE Form 1116 with its own Part I / Part III line set when
    # treaty re-sourcing is claimed. https://www.law.cornell.edu/uscode/text/26/904
    _write_form_1116_resourced(paths, tax_estimate, treaty, provenance)
    # 26 U.S.C. § 6114 / Reg. § 301.6114-1 — Form 8833 disclosure of the
    # treaty-based return position. Gated on the executed
    # ``TREATY25-LOB-QUALIFICATION`` rule output
    # ``treaty.form_8833_required`` (plumbed through ``us_model.py``
    # into the treaty packet's ``chosen_position`` block). Renders only
    # when treaty re-sourcing is claimed AND the taxpayer qualifies
    # under one of the five DBA-USA Art. 28 LOB paragraphs.
    _write_form_8833(paths, treaty)
    # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 2555 (Foreign
    # Earned Income Exclusion) under 26 U.S.C. § 911. Gated on the
    # § 911(a) election plumbed through ``us_model.py`` from the
    # US25-FEIE rule output ``us.stage.feie.elected``. When the
    # election is not made, the renderer no-ops and the form does not
    # appear in the package (per CLAUDE.md fail-closed posture: an
    # explicit-zero Form 2555 would be indistinguishable from a real
    # FEIE return with $0 of foreign earned income).
    _write_form_2555(paths, tax_estimate, provenance)
    # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): Form 8938 (FATCA,
    # § 6038D) and FinCEN Form 114 (FBAR, 31 CFR § 1010.350) filing-
    # determination status sheets. Both gate on the
    # US25-FATCA-FBAR-DETERMINATION rule output via
    # ``tax_estimate["fatca_fbar"]``. When the workspace's
    # foreign-financial-accounts.csv is incomplete, the sheets render
    # in MANUAL DETERMINATION REQUIRED form per CLAUDE.md fail-closed
    # posture. https://www.law.cornell.edu/uscode/text/26/6038D
    # https://www.law.cornell.edu/cfr/text/31/1010.350
    _write_form_8938_status(paths, tax_estimate, provenance)
    _write_fincen_114_status(paths, tax_estimate, provenance)
