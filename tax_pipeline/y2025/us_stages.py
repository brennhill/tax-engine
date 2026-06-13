from __future__ import annotations

from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.y2025.us_law import (
    CFR_1_6038D_2_URL,
    CFR_31_1010_350_URL,
    FINCEN_BSA_EFILING_URL,
    FORM_6251_INSTRUCTIONS_URL,
    IRS_ABOUT_FORM_1040_URL,
    IRS_ABOUT_FORM_1116_URL,
    IRS_ABOUT_FORM_6781_URL,
    IRS_ABOUT_FORM_8949_URL,
    IRS_ABOUT_FORM_8960_URL,
    IRS_ABOUT_SCHEDULE_1_URL,
    IRS_ABOUT_SCHEDULE_2_URL,
    IRS_ABOUT_SCHEDULE_3_URL,
    IRS_ABOUT_SCHEDULE_D_URL,
    IRS_FORM_2555_URL,
    IRS_FORM_8938_URL,
    IRS_FORM_8938_VS_FBAR_URL,
    IRS_FORM_8959_URL,
    IRS_GERMANY_TECH,
    IRS_I1040,
    IRS_I1040SD,
    IRS_I1116,
    IRS_I8949,
    IRS_I8960,
    IRS_NOTICE_2024_77_URL,
    IRS_P514,
    IRS_P525,
    IRS_P54_URL,
    IRS_P550,
    IRS_SCHEDULE_C_URL,
    IRS_SCHEDULE_SE_URL,
    IRS_YEARLY_AVG_RATES,
    REV_PROC_2024_40_URL,
    SCH_8812_INSTRUCTIONS_URL,
    USC_1_URL,
    USC_24_URL,
    USC_31_5314_URL,
    USC_55_URL,
    USC_56_URL,
    USC_59_URL,
    USC_61_URL,
    USC_63_URL,
    USC_152_URL,
    USC_162_URL,
    USC_164_URL,
    USC_199A_URL,
    USC_864_URL,
    USC_901_URL,
    USC_904_URL,
    USC_911_URL,
    USC_1211_URL,
    USC_1212_URL,
    USC_1256_URL,
    USC_1411_URL,
    USC_6038D_URL,
)

# B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03): the IRS_ABOUT_* form
# landing-page constants previously declared here in parallel with the
# ``_URL``-suffixed siblings in ``us_2025_law.py`` are now single-
# sourced in the law module. Local aliases below are kept (without
# the ``_URL`` suffix) so existing FormLineRef call sites in this
# module continue to read naturally; callers should prefer the
# canonical ``us_2025_law`` names in new code.
IRS_ABOUT_FORM_1040 = IRS_ABOUT_FORM_1040_URL
IRS_ABOUT_FORM_1116 = IRS_ABOUT_FORM_1116_URL
IRS_ABOUT_FORM_6781 = IRS_ABOUT_FORM_6781_URL
IRS_ABOUT_FORM_8949 = IRS_ABOUT_FORM_8949_URL
IRS_ABOUT_FORM_8960 = IRS_ABOUT_FORM_8960_URL
IRS_ABOUT_SCHEDULE_1 = IRS_ABOUT_SCHEDULE_1_URL
IRS_ABOUT_SCHEDULE_2 = IRS_ABOUT_SCHEDULE_2_URL
IRS_ABOUT_SCHEDULE_3 = IRS_ABOUT_SCHEDULE_3_URL
IRS_ABOUT_SCHEDULE_D = IRS_ABOUT_SCHEDULE_D_URL


def _stage_template_id(stage_id: str) -> str:
    return stage_id


def _stage_with_outputs(
    stage_id: str,
    legal_refs: tuple[str, ...],
    authority_urls: tuple[str, ...],
    input_fact_keys: tuple[str, ...],
    rounding_policy: str,
    law_order_note: str,
    legal_formula: str,
    outputs: tuple[OutputDeclaration, ...],
) -> LawStage:
    """Construct a US LawStage in the new ``outputs=`` shape.

    Per-output form-line provenance and audit-waypoint classification
    are encoded in ``outputs``. The engine derives the legacy
    ``output_keys`` / ``form_line_refs`` / ``form_line_urls`` fields
    from each ``OutputDeclaration`` so renderers, narrative builders,
    and audit fingerprints keep operating against the same surface
    during the migration.
    """
    return LawStage(
        stage_id=stage_id,
        country_or_scope="US-2025",
        legal_refs=legal_refs,
        authority_urls=authority_urls,
        input_fact_keys=input_fact_keys,
        rounding_policy=rounding_policy,
        law_order_note=law_order_note,
        legal_formula=legal_formula,
        narrative_templates={"en": _stage_template_id(stage_id)},
        outputs=outputs,
    )


def usa_law_stages_2025() -> tuple[LawStage, ...]:
    # Per invariant I3
    # (``tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py``),
    # an ``OutputDeclaration.form_line_refs`` entry must be matched by a
    # renderer ``_required_form_line(rows, form, line, ...)`` read. The
    # U.S. renderer (``tax_pipeline/forms/usa.py``) consumes the
    # treaty / 1040 / 1116 / 6781 / 8949 / 8960 / Schedule outputs via
    # ``FormEntry`` (label-keyed dict reads from the saved
    # ``us-treaty-package.json`` / ``us-tax-trace.csv`` /
    # ``us-tax-estimate.json`` artifacts) rather than via
    # ``_required_form_line``. The U.S. stages therefore classify their
    # outputs with closed-enum ``AuditWaypoint`` values describing the
    # value's role in the calculation; the controlling legal authority
    # (26 U.S.C. § 1, § 61, § 63, § 901, § 904, § 1211, § 1212, § 1256,
    # § 1411 plus IRS Pub. 514 / Pub. 525 / Pub. 550 / Form 1116 / Form
    # 1040 instructions) continues to ride on ``legal_refs``,
    # ``authority_urls``, and ``legal_formula``. WS-2B re-anchors the
    # form-line declarations off the renderer-orphan path; the
    # ``DE25-FORM-USA-PROJECTION`` Phase-4 stage will eventually hold
    # the form-line bindings the U.S. renderer reads via
    # ``_required_form_line``.
    return (
        # US25-00: filing posture validation gates which constants
        # apply downstream. The Form 1040 filing-status checkbox is
        # populated by the renderer's ``_write_1040`` from the saved
        # treaty packet's ``chosen_position.filing_status``; the gate
        # itself is RECONCILIATION_INVARIANT (validates posture vs.
        # § 1 / § 63 / § 1211(b) / § 1411 thresholds).
        _stage_with_outputs(
            "US25-00-FILING-POSITION",
            ("26 U.S.C. § 1", "26 U.S.C. § 63", "26 U.S.C. § 1211(b)", "26 U.S.C. § 1411"),
            (USC_1_URL, USC_63_URL, USC_1211_URL, USC_1411_URL),
            ("us.profile.filing_posture", "us.profile.elections", "us.reference.constants", "us.assessment.inputs"),
            "No currency rounding; this stage validates posture-sensitive constants.",
            "Filing posture/elections select thresholds before any income or credit computation.",
            "us.stage.filing_position = {filing_status, niit_threshold, capital_loss_limit, standard_deduction} selected by us.profile.filing_posture",
            (
                OutputDeclaration(
                    key="us.stage.filing_position",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-01: foreign wage translation per the IRS yearly average
        # currency exchange rate. Translated wages flow into the
        # § 61 AGI assembly downstream and ultimately appear on Form
        # 1040 line 1a via the renderer's ``_write_1040`` FormEntry.
        _stage_with_outputs(
            "US25-01-WAGE-TRANSLATION",
            ("IRS yearly average currency exchange rates",),
            (IRS_YEARLY_AVG_RATES,),
            ("us.stage.filing_position", "us.fx.eur_per_usd", "us.wages.eur", "us.assessment.inputs"),
            "Foreign wages are rounded to cents after annual average-rate translation.",
            "Foreign wages must be translated before section 61 AGI assembly.",
            "us.stage.wages_usd = us.wages.eur / us.fx.eur_per_usd (IRS yearly average rate, rounded to cents)",
            (
                OutputDeclaration(
                    key="us.stage.wages_usd",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-02: dividend / interest / substitute / staking inputs
        # per § 61. Values feed Form 1040 lines 2b/3a/3b and
        # Schedule 1 line 8/9 via the renderer's ``_write_1040`` /
        # ``_write_schedule_1`` FormEntry projections.
        _stage_with_outputs(
            "US25-02-INCOME-SIDE-INPUTS",
            ("26 U.S.C. § 61", "IRS Publication 525", "IRS Publication 550"),
            (USC_61_URL, IRS_P525, IRS_P550),
            ("us.stage.wages_usd", "us.capital.income_facts", "us.assessment.inputs"),
            "Income side components remain cent-level before AGI assembly.",
            "Dividend, interest, substitute-payment, and staking income facts feed section 61 gross income.",
            "us.stage.income_side_inputs = {dividends, interest, schedule_1_other, staking, substitute_payments} per 26 U.S.C. § 61",
            (
                OutputDeclaration(
                    key="us.stage.income_side_inputs",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-02A: 26 U.S.C. § 61 / § 162 Schedule C net profit. Net profit =
        # § 61(a)(2) gross receipts − § 162(a) ordinary & necessary expenses.
        # IRS-VERIFIED 2026-06-13 against the 2025 Schedule C PDF
        # (https://www.irs.gov/pub/irs-pdf/f1040sc.pdf): line 31 = line 7 (gross
        # income) − line 28 (total expenses) in the no-home-office posture. The
        # single net-profit amount feeds TWO downstream paths: (a) the income
        # side — folded into ``schedule_1_other_income_usd`` at
        # US25-02-INCOME-SIDE-INPUTS so it reaches Schedule 1 line 3 → Form 1040
        # → AGI; and (b) the SE-tax base — the loader derives
        # ``se_inputs.net_se_earnings_usd`` from this same profit so
        # § 1402(a)(12) (× 0.9235) and the Phase 0 Totalization logic apply over
        # the real profit. These are the SAME profit (income once; SE tax is a
        # separate tax on the same earnings; ½ SE tax is § 164(f) deductible) —
        # standard treatment, not double-counting. For a wage earner (no
        # Schedule C facts) the net profit is zero, so AGI / taxable income are
        # value-identical to the wage-only baseline (invariant I13: the
        # wage-earner Schedule C artifact is absent, not a zeroed form).
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162
        # https://www.irs.gov/forms-pubs/about-schedule-c-form-1040
        _stage_with_outputs(
            "US25-02A-SCHEDULE-C",
            ("26 U.S.C. § 61", "26 U.S.C. § 162", "IRS Schedule C (Form 1040)"),
            (USC_61_URL, USC_162_URL, IRS_SCHEDULE_C_URL),
            ("us.assessment.inputs",),
            # IRS-VERIFIED 2026-06-13 — Schedule C line 31 (net profit) carries
            # to Schedule 1 line 3; the line numbers are from the official 2025
            # Schedule C PDF (https://www.irs.gov/pub/irs-pdf/f1040sc.pdf).
            "Schedule C net profit is rounded to cents to match the Schedule C line-31 entry.",
            "Schedule C net profit is computed before US25-03 capital buckets so it can feed the income side (Schedule 1 line 3) and the self-employment-tax base.",
            "us.stage.schedule_c.net_profit_usd = round(gross_receipts_usd - business_expenses_usd) per 26 U.S.C. §§ 61, 162 (IRS Schedule C line 31)",
            (
                OutputDeclaration(
                    key="us.stage.schedule_c",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule C line-level decomposition. Each line is a declared
                # rule output so the Schedule C renderer transits
                # ``legal_value_entry`` with a real
                # ``StageResult.output_fingerprint`` (invariants I2 / I3 / I11).
                # IRS-VERIFIED 2026-06-13 against the 2025 Schedule C PDF
                # (https://www.irs.gov/pub/irs-pdf/f1040sc.pdf): line 7 gross
                # income, line 28 total expenses, line 31 net profit.
                OutputDeclaration(
                    key="us.tax.schedule_c_line_7_gross_income_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule C", line="7", url=IRS_SCHEDULE_C_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_c_line_28_total_expenses_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule C", line="28", url=IRS_SCHEDULE_C_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_c_line_31_net_profit_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule C", line="31", url=IRS_SCHEDULE_C_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-03: Form 8949 / Schedule D bucket assembly per § 1211 /
        # § 1212 + Schedule D / Form 8949 instructions. Per-bucket
        # short/long split is a per-Posten aggregation; the Form 8949
        # / Schedule D bucket totals appear in the renderer via
        # ``_write_form_8949`` and ``_write_schedule_d`` FormEntry
        # projections.
        _stage_with_outputs(
            "US25-03-CAPITAL-BUCKETS",
            ("26 U.S.C. § 1211", "26 U.S.C. § 1212", "Instructions for Schedule D and Form 8949"),
            (USC_1211_URL, USC_1212_URL, IRS_I1040SD),
            ("us.capital.sale_facts", "us.assessment.inputs"),
            "Capital buckets remain cent-level before annual loss-limit application.",
            "Form 8949/Schedule D buckets must be assembled before line 7a and preferential tax.",
            "us.stage.capital_buckets = bucket(us.capital.sale_facts by short/long term and Form 8949 box A/B/D/H/K)",
            (
                OutputDeclaration(
                    key="us.stage.capital_buckets",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-04: § 1256(a)(3) statutory 40/60 character split.
        # Reported on Form 6781 via the renderer's ``_write_form_6781``
        # FormEntry projection. Per-bucket character split is per-Posten
        # aggregation.
        _stage_with_outputs(
            "US25-04-SECTION-1256",
            ("26 U.S.C. § 1256",),
            (USC_1256_URL,),
            ("us.stage.capital_buckets", "us.capital.section_1256_facts", "us.assessment.inputs"),
            "Section 1256 amounts are split at cent precision into 40/60 character.",
            "Section 1256 character split feeds the Schedule D capital result.",
            "us.stage.section_1256_split = {short: 0.40 * total, long: 0.60 * total} per 26 U.S.C. § 1256(a)(3)",
            (
                OutputDeclaration(
                    key="us.stage.section_1256_split",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-05: § 1211(b) annual cap + § 1212 carryforward. The
        # post-cap result enters Form 1040 line 7a via the renderer's
        # ``_write_1040`` FormEntry; INTERMEDIATE_MATH captures its role
        # as the AGI / NIIT input.
        _stage_with_outputs(
            "US25-05-CAPITAL-LOSS-LINE-7A",
            ("26 U.S.C. § 1211(b)", "26 U.S.C. § 1212"),
            (USC_1211_URL, USC_1212_URL),
            ("us.stage.capital_buckets", "us.stage.section_1256_split", "us.constants.capital_loss_limit", "us.assessment.inputs"),
            "Annual capital-loss deduction and carryforward are rounded to cents.",
            "The Schedule D result enters Form 1040 line 7a before AGI and NIIT.",
            "us.stage.capital_loss_result.form_1040_line_7a = max(net_capital_after_1256, -capital_loss_limit) per § 1211(b); carryforward = excess loss per § 1212",
            (
                OutputDeclaration(
                    key="us.stage.capital_loss_result",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-06: § 1(h) preferential net-capital-gain base feeds the
        # QDCGTW (line 16 worksheet) downstream; INTERMEDIATE_MATH
        # captures that role.
        _stage_with_outputs(
            "US25-06-PREFERENTIAL-CAPITAL-BASE",
            ("26 U.S.C. § 1(h)", "Instructions for Schedule D"),
            (USC_1_URL, IRS_I1040SD),
            ("us.stage.capital_buckets", "us.stage.section_1256_split", "us.stage.capital_loss_result"),
            "Preferential net-capital-gain base remains cent-level for the line 16 worksheet.",
            "The section 1(h) preferential base is identified before regular tax.",
            "us.stage.preferential_capital_base = net_capital_gain (long-term gain - short-term loss, floored at 0) per 26 U.S.C. § 1(h)",
            (
                OutputDeclaration(
                    key="us.stage.preferential_capital_base",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-SE-TAX: 26 U.S.C. § 1401 Self-Employment Contributions
        # Act tax. Promoted ahead of US25-07-AGI so the § 164(f) one-half
        # SE-tax deduction (F-C1) can flow into Form 1040 line 11 via
        # ``us.stage.se_tax`` consumed by US25-07-AGI. The downstream
        # consumers (US25-ADDITIONAL-MEDICARE, US25-21-PAYMENTS) read
        # ``us.stage.se_tax`` from the same fingerprinted output.
        # 12.4 % OASDI on net SE earnings up to the 2025 SSA wage base
        # ($176,100), plus 2.9 % Medicare on all net SE earnings
        # (§ 1402(a)(12) reduces the base to 92.35 %). The U.S.-Germany
        # Totalization Agreement (1979) keeps SE earnings out of § 1401 if
        # a German Certificate of Coverage is presented; that path fails
        # closed in ``se_tax_assessment_2025`` because the
        # certificate-driven SSA-coverage flow is not yet modeled.
        # Schedule SE is the filed form when SE earnings exist.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402
        # https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
        # https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
        _stage_with_outputs(
            "US25-SE-TAX",
            ("26 U.S.C. § 1401", "26 U.S.C. § 1402", "U.S.-Germany Totalization Agreement", "IRS Schedule SE"),
            (
                "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401&num=0&edition=prelim",
                "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402&num=0&edition=prelim",
                "https://www.ssa.gov/international/Agreement_Pamphlets/germany.html",
                "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040",
            ),
            ("us.assessment.inputs",),
            "SE tax components are rounded to cents to match Schedule SE.",
            "Section 1401 SE tax is computed before US25-07-AGI so the § 164(f) one-half SE-tax deduction reduces AGI; the same SE-tax value flows to Schedule 2 line 4 alongside § 1411 NIIT and § 55 AMT.",
            "us.stage.se_tax = 0.124 * min(net_se_earnings * 0.9235, SS_wage_base_2025) + 0.029 * (net_se_earnings * 0.9235) per 26 U.S.C. §§ 1401, 1402",
            (
                OutputDeclaration(
                    key="us.stage.se_tax",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 4 = § 1401
                # SE tax (Schedule SE line 12 carries to Schedule 2 line 4).
                # 1:1 mirror of ``us.stage.se_tax.se_tax_usd`` — no new
                # arithmetic (invariant I5).
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                OutputDeclaration(
                    key="us.tax.schedule_2_line_4_se_tax_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="4", url=IRS_ABOUT_SCHEDULE_2),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B4 (FORM-MAPPING-FOLLOWUP) — Schedule SE line-level
                # decomposition. Each line is a declared rule output so
                # the Schedule SE renderer transits ``legal_value_entry``
                # with a real ``StageResult.output_fingerprint``
                # (invariants I2 / I11). Authority:
                #   - 26 U.S.C. § 1401 (SECA tax).
                #   - 26 U.S.C. § 1402(a)(12) (92.35 % factor).
                #   - Schedule SE instructions:
                #     https://www.irs.gov/forms-pubs/about-schedule-se-form-1040
                OutputDeclaration(
                    key="us.tax.schedule_se_line_2_net_se_earnings_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="2", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_3_total_se_earnings_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="3", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_4a_se_taxable_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="4a", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_4c_se_taxable_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="4c", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_6_combined_se_base_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="6", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_8a_w2_ss_wages_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="8a", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_10_oasdi_tax_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="10", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_11_medicare_tax_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="11", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.tax.schedule_se_line_12_total_se_tax_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule SE", line="12", url=IRS_SCHEDULE_SE_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-07: § 61 AGI lands on Form 1040 line 11 via the
        # renderer's ``_write_1040`` FormEntry projection. F-C1 — § 164(f)
        # one-half of § 1401 SE tax (OASDI + Medicare, NOT § 1401(b)(2)
        # additional Medicare) is an above-the-line AGI adjustment per
        # 26 U.S.C. § 164(f)(1) and Schedule 1 line 15.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164
        _stage_with_outputs(
            "US25-07-AGI",
            ("26 U.S.C. § 61", "26 U.S.C. § 164(f)"),
            (USC_61_URL, USC_164_URL),
            (
                "us.stage.wages_usd",
                "us.stage.income_side_inputs",
                "us.stage.capital_loss_result",
                "us.stage.se_tax",
            ),
            "AGI components are summed at cent precision; § 164(f) one-half SE tax is rounded to cents before subtraction.",
            "Section 61 gross income/AGI is assembled (after § 164(f) one-half SE-tax deduction) before section 63 taxable income.",
            "us.stage.adjusted_gross_income = wages_usd + income_side_inputs + capital_loss_result.form_1040_line_7a - 0.5 * us.stage.se_tax.se_tax_usd per 26 U.S.C. §§ 61, 164(f)",
            (
                OutputDeclaration(
                    key="us.stage.adjusted_gross_income",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-FEIE: 26 U.S.C. § 911 Foreign Earned Income Exclusion +
        # § 911(c) housing exclusion / deduction (Workstream 1, US
        # coverage gap). The stage emits the typed ``us.stage.feie`` view
        # carrying the excluded amount, the housing-exclusion / housing-
        # deduction split, the § 911(d)(6) FTC denial, and the
        # § 1411(d)(1)(A) NIIT MAGI add-back. When the election is not
        # made every output is zero, so the demo workspace flows through
        # unchanged. Form 2555 is the filed form when § 911 is elected.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
        # https://www.irs.gov/publications/p54
        # https://www.irs.gov/forms-pubs/about-form-2555
        # https://www.irs.gov/pub/irs-drop/n-24-77.pdf
        _stage_with_outputs(
            "US25-FEIE",
            ("26 U.S.C. § 911", "IRS Publication 54", "IRS Form 2555", "IRS Notice 2024-77"),
            (USC_911_URL, IRS_P54_URL, IRS_FORM_2555_URL, IRS_NOTICE_2024_77_URL),
            (
                "us.assessment.inputs",
                "us.stage.adjusted_gross_income",
            ),
            "FEIE values are rounded to cents to match Form 2555 line outputs.",
            "Section 911 exclusion runs after AGI assembly so the excluded amount removes from FTC denominator (§ 904) and § 63 taxable income; § 1411(d)(1)(A) MAGI add-back lands in NIIT.",
            "us.stage.feie = {excluded_amount, housing_exclusion, housing_deduction, deduction_total, disallowed_ftc, niit_magi_addback} per 26 U.S.C. §§ 911(b), 911(c), 911(d)(6), 1411(d)(1)(A); us.feie.line_36 = excluded_amount; us.feie.line_45 = housing_exclusion; us.feie.line_50 = housing_deduction (per Form 2555 line layout)",
            (
                OutputDeclaration(
                    key="us.stage.feie",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # C1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Form-2555-
                # line scalar outputs decomposing the bundle so the Form
                # 2555 renderer can read fingerprinted Decimals through
                # the I11 LegalValue envelope. Lines 36 / 45 / 50 are the
                # three legally-meaningful scalars on Form 2555 (annual
                # exclusion, housing exclusion, housing deduction); the
                # § 911(d)(6) FTC denial and § 1411(d)(1)(A) NIIT add-
                # back stay on the bundle as RECONCILIATION_INVARIANT
                # because they feed downstream stages (US25-11 FTC,
                # US25-20 NIIT) rather than transmit on Form 2555.
                # https://www.irs.gov/forms-pubs/about-form-2555
                #
                # C-audit (2026-05-04): each per-line scalar carries a
                # FormLineRef for invariant I3, so the bidirectional
                # renderer↔OutputDeclaration contract enforces the
                # ``_write_form_2555`` writes are anchored to declared
                # rule outputs (no orphan declarations, no orphan
                # renderer rows).
                OutputDeclaration(
                    key="us.feie.line_36_excluded_amount_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 2555", line="36", url=IRS_FORM_2555_URL),
                    ),
                ),
                OutputDeclaration(
                    key="us.feie.line_45_housing_exclusion_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 2555", line="45", url=IRS_FORM_2555_URL),
                    ),
                ),
                OutputDeclaration(
                    key="us.feie.line_50_housing_deduction_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 2555", line="50", url=IRS_FORM_2555_URL),
                    ),
                ),
            ),
        ),
        # US25-08: § 63 taxable income lands on Form 1040 line 15 via
        # the renderer's ``_write_1040`` FormEntry projection. After
        # US25-FEIE, taxable income is reduced by the § 911 deduction
        # total in addition to the standard deduction.
        _stage_with_outputs(
            "US25-08-TAXABLE-INCOME",
            ("26 U.S.C. § 63", "26 U.S.C. § 911"),
            (USC_63_URL, USC_911_URL),
            ("us.stage.adjusted_gross_income", "us.stage.feie", "us.constants.standard_deduction", "us.assessment.inputs"),
            "Taxable income remains cent-level before tax-table or bracket rounding.",
            "Section 63 taxable income is the base for section 1 tax and section 904 limitations.",
            "us.stage.taxable_income = max(0, us.stage.adjusted_gross_income - us.stage.feie.deduction_total - us.constants.standard_deduction) per 26 U.S.C. §§ 63, 911",
            (
                OutputDeclaration(
                    key="us.stage.taxable_income",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-08A: 26 U.S.C. § 199A QBI applicability GATE. For this engine's
        # taxpayer (U.S. citizen resident in Germany, German-source freelance
        # income, business_income_source='foreign'), § 199A(c)(3)(A)(i) / § 864(c)
        # require income effectively connected with a trade or business WITHIN
        # the United States. German-source business income is conducted within
        # Germany, NOT within the U.S. → it is NOT QBI → the § 199A deduction is
        # not_applicable and ZERO. Taxable income is UNCHANGED by § 199A in this
        # posture (the gate subtracts nothing before US25-09-REGULAR-TAX). This
        # is an explicit cited not_applicable status (invariant I13), NEVER a
        # Form 8995 zero line — granting any 20 % deduction here would be a
        # LEAK-class over-deduction. The us_effectively_connected QBI-granting
        # path is NOT modeled and fails closed at the loader (the W-2-wage /
        # UBIA / SSTB limits need verified 2025 § 199A thresholds, out of scope).
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section864
        _stage_with_outputs(
            "US25-08A-QBI-GATE",
            ("26 U.S.C. § 199A(c)(3)(A)(i)", "26 U.S.C. § 864(c)"),
            (USC_199A_URL, USC_864_URL),
            ("us.stage.taxable_income", "us.assessment.inputs"),
            "No currency rounding; the foreign-source § 199A deduction is a fixed zero (not_applicable).",
            "§ 199A applicability is adjudicated after § 63 taxable income and before § 1 regular tax; for foreign-source business income the deduction is not_applicable (zero) and taxable income is unchanged.",
            "gate: business_income_source='foreign' (§ 864(c): not US-effectively-connected) => § 199A not_applicable, qbi_deduction_usd = 0, taxable income unchanged; 'us_effectively_connected' fails closed (QBI-granting path not modeled)",
            (
                OutputDeclaration(
                    key="us.stage.qbi_gate",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-09: § 1 / § 1(h) regular tax via QDCGTW lands on Form
        # 1040 line 16 via the renderer's ``_write_1040`` FormEntry.
        _stage_with_outputs(
            "US25-09-REGULAR-TAX",
            ("26 U.S.C. § 1", "26 U.S.C. § 1(h)", "IRS Publication 550"),
            (USC_1_URL, IRS_P550),
            ("us.stage.taxable_income", "us.stage.preferential_capital_base", "us.capital.qualified_dividends", "us.stage.income_side_inputs", "us.assessment.inputs"),
            "Tax table/worksheet rounding follows Form 1040 line 16 instructions.",
            "Regular tax is computed before foreign tax credits and before NIIT.",
            "us.stage.regular_tax_before_credits = section_1_tax(taxable_income) with § 1(h) preferential rates on net_capital_gain + qualified_dividends",
            (
                OutputDeclaration(
                    key="us.stage.regular_tax_before_credits",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-10: Form 1116 line-18 adjustment-exception gate. Binary
        # gate that controls whether downstream FTC stages apply the
        # rate-differential adjustment; classified
        # RECONCILIATION_INVARIANT (validates the supported preferential-
        # income posture per Form 1116 instructions).
        _stage_with_outputs(
            "US25-10-FORM-1116-PREFERENTIAL-GATE",
            ("26 U.S.C. § 904", "Instructions for Form 1116"),
            (USC_904_URL, IRS_I1116),
            ("us.stage.regular_tax_before_credits", "us.ftc.foreign_preferential_income", "us.stage.adjusted_gross_income", "us.stage.taxable_income", "us.stage.wages_usd", "us.stage.income_side_inputs", "us.assessment.inputs"),
            "No currency rounding; unsupported Form 1116 preferential adjustments fail closed.",
            "Form 1116 preferential-income adjustment support is checked before FTC limitations.",
            "gate: foreign preferential income (qualified dividends, capital gain distributions) supported per Form 1116 instructions => proceed; else fail-closed",
            (
                OutputDeclaration(
                    key="us.stage.form_1116_preferential_gate",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-11: Form 1116 lines 1-7 (FTC denominator + std-deduction
        # apportionment per basket). Classified PER_POSTEN_AGGREGATION:
        # per-basket apportionment of category gross income and
        # allocated deductions.
        _stage_with_outputs(
            "US25-11-FTC-DENOMINATOR",
            ("26 U.S.C. § 904", "IRS Publication 514", "26 U.S.C. § 911"),
            (USC_904_URL, IRS_P514, USC_911_URL),
            (
                "us.stage.form_1116_preferential_gate",
                "us.ftc.category_gross_income",
                "us.constants.standard_deduction",
                "us.stage.wages_usd",
                "us.stage.income_side_inputs",
                "us.stage.feie",
                "us.assessment.inputs",
            ),
            "Standard-deduction allocations are retained at cent precision.",
            "Form 1116 category income and deductions are apportioned before basket limitations; § 911(d)(6) excludes § 911 amounts from the general-basket numerator.",
            "us.stage.ftc_denominator[category] = (category_gross_income - § 911 excluded amount when general basket) - allocated_deductions per § 904, Pub. 514, and § 911(d)(6)",
            (
                OutputDeclaration(
                    key="us.stage.ftc_denominator",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-12: § 904 per-basket limitation. PER_POSTEN_AGGREGATION
        # captures the per-basket limitation surface that feeds the
        # downstream allowed-FTC selection.
        _stage_with_outputs(
            "US25-12-FTC-LIMITATIONS",
            ("26 U.S.C. § 904", "Instructions for Form 1116"),
            (USC_904_URL, IRS_I1116),
            ("us.stage.ftc_denominator", "us.stage.taxable_income", "us.stage.regular_tax_before_credits"),
            "FTC limitations are rounded to cents for workpaper audit.",
            "Section 904 limits must be computed before allowed credit selection.",
            "us.stage.ftc_limitations[category] = regular_tax_before_credits * ftc_denominator[category] / taxable_income per 26 U.S.C. § 904(a)",
            (
                OutputDeclaration(
                    key="us.stage.ftc_limitations",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-13: foreign tax available = current-year + § 904(c)
        # carryover, with § 911(d)(6) FTC denial applied (F-C3) before
        # the lesser-of limitation downstream. PER_POSTEN_AGGREGATION
        # captures the per-basket carryover bookkeeping; the aggregate
        # amount feeds the baseline-allowed-FTC stage. § 911(d)(6) strips
        # the FTC allocable to the § 911 excluded amount from the general
        # basket (excluded foreign earned income is wage income → general
        # basket per Pub. 514).
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
        _stage_with_outputs(
            "US25-13-FOREIGN-TAX-AVAILABLE",
            ("26 U.S.C. § 901", "26 U.S.C. § 905", "26 U.S.C. § 911(d)(6)", "IRS Publication 514"),
            (USC_901_URL, USC_911_URL, IRS_P514),
            (
                "us.stage.ftc_limitations",
                "us.ftc.current_foreign_tax",
                "us.ftc.carryovers",
                "us.stage.feie",
                "us.assessment.inputs",
            ),
            "Current foreign tax and carryovers are retained at cent precision; § 911(d)(6) denial is rounded to cents and floored at zero.",
            "Available foreign tax and carryovers are identified after § 911(d)(6) FTC denial and before the lesser-of limitation.",
            "us.stage.foreign_tax_available[category] = max(0, current_year_foreign_tax_paid[category] - § 911(d)(6) disallowed_ftc[category]) + carryover_2024[category] per 26 U.S.C. §§ 901, 911(d)(6)",
            (
                OutputDeclaration(
                    key="us.stage.foreign_tax_available",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        # US25-14: baseline allowed FTC = lesser of available foreign
        # tax and § 904 limit, summed across baskets. INTERMEDIATE_MATH
        # captures its role as the input to the final-allowed-FTC
        # presentation stage.
        _stage_with_outputs(
            "US25-14-BASELINE-ALLOWED-FTC",
            ("26 U.S.C. §§ 901 and 904",),
            (USC_901_URL, USC_904_URL),
            ("us.stage.ftc_limitations", "us.stage.foreign_tax_available", "us.stage.regular_tax_before_credits", "us.assessment.inputs"),
            "Baseline credits are rounded to cents after applying each basket limitation.",
            "Baseline FTC is the lesser of available foreign tax and the section 904 limitation before treaty line-12 adjustment.",
            "us.stage.baseline_allowed_ftc = sum_categories(min(foreign_tax_available[category], ftc_limitations[category])) per 26 U.S.C. §§ 901 and 904",
            (
                OutputDeclaration(
                    key="us.stage.baseline_allowed_ftc",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        _stage_with_outputs(
            "US25-15-TREATY-US-SOURCE-DIVIDENDS",
            ("Germany treaty technical explanation", "IRS Publication 514"),
            (IRS_GERMANY_TECH, IRS_P514),
            # F-FN-2: ``_treaty_assessment`` (the cache-priming helper called
            # from this stage's calculate body) now reads us.stage.taxable_income
            # for the Pub. 514 worksheet line 16 average-rate denominator.
            ("us.stage.baseline_allowed_ftc", "us.treaty.dividend_source_split", "us.stage.taxable_income", "us.stage.regular_tax_before_credits", "us.assessment.inputs"),
            "Treaty dividend source amounts remain cent-level before average-rate worksheet math.",
            "U.S.-source treaty income must be identified before the Publication 514 additional-credit worksheet.",
            "us.stage.treaty_us_source_dividends = sum of U.S.-sourced dividend items per DBA-USA Art. 10 and Pub. 514 worksheet line 15",
            (
                OutputDeclaration(
                    key="us.stage.treaty_us_source_dividends",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
            ),
        ),
        _stage_with_outputs(
            "US25-16-TREATY-AVERAGE-TAX-FLOOR",
            ("IRS Publication 514", "Germany treaty technical explanation"),
            (IRS_P514, IRS_GERMANY_TECH),
            # F-FN-2: Pub. 514 worksheet line 16 uses **taxable income** (Form
            # 1040 line 15), not AGI, as the average-rate denominator.
            ("us.stage.treaty_us_source_dividends", "us.stage.regular_tax_before_credits", "us.stage.taxable_income"),
            "Publication 514 average-rate worksheet values are rounded to cents.",
            "The U.S. tax on treaty-resourced income is compared to the treaty 15 percent source-country floor.",
            "us.stage.treaty_us_limitation = max(0, regular_tax * us_source_dividends / taxable_income - 0.15 * us_source_dividends) per Pub. 514 worksheet line 18 (line 19 is produced downstream by US25-17 after the German residual-tax cap is applied).",
            (
                OutputDeclaration(
                    key="us.stage.treaty_us_limitation",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        _stage_with_outputs(
            "US25-17-TREATY-GERMAN-RESIDUAL-CAP",
            ("IRS Publication 514", "Germany treaty technical explanation"),
            (IRS_P514, IRS_GERMANY_TECH),
            # F-FN-1: ``de.stage.us_source_dividend_tax_and_credit`` was previously
            # declared here, but ``us25_17_treaty_german_residual_cap`` delegates to
            # ``_treaty_assessment(facts)`` (cached after US25-15) and never reads
            # the de.stage key directly. Per the per-function review, dropping the
            # declaration eliminates the false-positive dependency edge in the
            # audit graph; the actual upstream German values reach this stage via
            # the typed ``us.assessment.inputs`` consumed during the cache-priming
            # call inside US25-15. The remaining ``us.stage.treaty_us_limitation``
            # entry preserves the legitimate ordering edge from US25-16.
            ("us.stage.treaty_us_limitation",),
            "German residual tax cap values are retained at cent precision.",
            "Publication 514 uses Germany's tax and credit on the same U.S.-source dividend stack when available, then caps the additional credit by residual residence-country tax.",
            "us.stage.treaty_german_residual_cap = german_precredit_tax_on_us_source_dividends - german_residence_credit_for_us_tax per Pub. 514 worksheet line 20c",
            (
                OutputDeclaration(
                    key="us.stage.treaty_german_residual_cap",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        _stage_with_outputs(
            "US25-18-TREATY-ADDITIONAL-FTC",
            ("IRS Publication 514", "Germany treaty technical explanation"),
            (IRS_P514, IRS_GERMANY_TECH),
            ("us.stage.treaty_us_limitation", "us.stage.treaty_german_residual_cap"),
            "Additional treaty FTC is the cent-level lesser of worksheet line 19 and line 20c.",
            "Publication 514 worksheet line 21 is carried to Form 1116 line 12 before final allowed FTC/payment presentation.",
            "us.stage.treaty_additional_ftc = min(treaty_us_limitation, treaty_german_residual_cap) per Pub. 514 worksheet line 21",
            (
                OutputDeclaration(
                    key="us.stage.treaty_additional_ftc",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-19: final allowed FTC = baseline + treaty add-on. Lands
        # on Form 1116 line 33 / Schedule 3 line 1 via the renderer's
        # ``_write_form_1116_*`` FormEntry projections.
        _stage_with_outputs(
            "US25-19-ALLOWED-FTC",
            ("26 U.S.C. §§ 901 and 904", "IRS Publication 514", "Instructions for Form 1116"),
            (USC_901_URL, USC_904_URL, IRS_P514, IRS_I1116),
            ("us.stage.baseline_allowed_ftc", "us.stage.treaty_additional_ftc"),
            "Final allowed credits are rounded to cents after adding the treaty re-sourcing line-12 adjustment.",
            "Final FTC presentation follows Form 1116 after the Publication 514 treaty additional credit is included.",
            "us.stage.allowed_ftc = baseline_allowed_ftc + treaty_additional_ftc (subject to Form 1116 line 33 nonrefundable-credit cap)",
            (
                OutputDeclaration(
                    key="us.stage.allowed_ftc",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-19A: promote the post-treaty allowed-FTC sum to a top-level
        # rule-graph fact so the orchestrator (``us_model.main``) can read
        # it instead of recomputing ``ftc.total_allowed_ftc_usd +
        # treaty_resourcing.treaty_resourcing_additional_ftc_usd`` at the
        # script boundary. Authority: 26 U.S.C. §§ 901 (FTC) and 904
        # (limitation), IRS Publication 514 worksheet line 21 carried to
        # Form 1116 line 12, and DBA-USA Art. 23 (residence-country credit
        # reconciliation). Closes LEAK-4 / I5 by making the sum a
        # fingerprinted ``StageResult`` with a Form 1116 line 33 binding.
        _stage_with_outputs(
            "US25-19A-ALLOWED-FTC-AFTER-RESOURCING",
            (
                "26 U.S.C. § 901",
                "26 U.S.C. § 904",
                "DBA-USA Art. 23",
                "IRS Publication 514",
                "Instructions for Form 1116",
            ),
            (USC_901_URL, USC_904_URL, IRS_GERMANY_TECH, IRS_P514, IRS_I1116),
            ("us.stage.baseline_allowed_ftc", "us.stage.treaty_additional_ftc", "us.stage.allowed_ftc"),
            "Post-treaty allowed FTC remains cent-level for Schedule 3 line 1 / Form 1116 line 33.",
            "After the Publication 514 worksheet line 21 add-on is folded into Form 1116, the post-treaty allowed credit is the value Schedule 3 line 1 carries to Form 1040.",
            "us.stage.total_allowed_ftc_after_treaty_resourcing_usd = baseline_allowed_ftc.total_allowed_ftc_usd + treaty_additional_ftc.treaty_resourcing_additional_ftc_usd per 26 U.S.C. §§ 901/904 and Pub. 514 worksheet line 21",
            (
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the post-
                # treaty allowed-FTC total lands on Form 1116 Resourced
                # Line 32 (total credit across all baskets — Passive +
                # General + Resourced) on the separate § 904(d)(6)
                # Form 1116. The C-audit (2026-05-04) anchors the
                # ``_write_form_1116_resourced`` Line 32 write to this
                # declared rule output via the bidirectional I3
                # contract; Schedule 3 line 1 uses a separate
                # FormLineRef on ``us.tax.schedule_3_line_1_ftc_total_usd``
                # below.
                OutputDeclaration(
                    key="us.stage.total_allowed_ftc_after_treaty_resourcing_usd",
                    form_line_refs=(
                        FormLineRef(
                            form="Form 1116 Resourced",
                            line="32",
                            url=IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B2 (FORM-MAPPING-FOLLOWUP) — Schedule 3 line 1 = post-
                # treaty allowed Foreign Tax Credit (Form 1116 line 33).
                # 1:1 mirror of the post-treaty allowed FTC sum surfaced
                # above; carries the FormLineRef so the Schedule 3
                # renderer can transit ``legal_value_entry`` with a real
                # ``StageResult.output_fingerprint`` (invariants I2 / I11).
                # This output is what ``us_treaty_packet.py`` reads
                # instead of summing ftc[allowed_general] + ftc[allowed_
                # passive] + treaty[treaty_resourcing_additional_ftc] at
                # the projection boundary (closes the I5 smell at
                # us_treaty_packet.py:147).
                # https://www.irs.gov/pub/irs-pdf/f1040s3.pdf
                OutputDeclaration(
                    key="us.tax.schedule_3_line_1_ftc_total_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 3", line="1", url=IRS_ABOUT_SCHEDULE_3),
                        # Schedule 3 line 8 = Part I total nonrefundable
                        # credits = sum of lines 1-7. For the supported
                        # posture (no other Part I credits modeled) line
                        # 8 numerically equals line 1; the same rule
                        # output backs both lines so each form-line write
                        # transits the same fingerprint.
                        FormLineRef(form="Schedule 3", line="8", url=IRS_ABOUT_SCHEDULE_3),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # F-US-1 — Alternative Minimum Tax stages under 26 U.S.C. §§ 55, 56,
        # 59 + Form 6251. Inserted between US25-19A (post-treaty allowed FTC)
        # and US25-20 (NIIT) so the AMT comparison uses the same regular-tax-
        # after-FTC baseline that lands on Schedule 3 line 1, with the
        # treaty-resourced allowed-FTC sum kept separate as a parallel run
        # consumed by the treaty packet renderer. The fail-closed posture is
        # mandatory: § 55 was previously absent from the U.S. graph (the F-US-1
        # finding), so total_tax silently understated AMT-binding postures.
        # Authority:
        #   - https://www.law.cornell.edu/uscode/text/26/55  (tentative min. tax)
        #   - https://www.law.cornell.edu/uscode/text/26/56  (AMTI add-backs)
        #   - https://www.law.cornell.edu/uscode/text/26/59  (AMTFTC § 59(a))
        #   - https://www.irs.gov/forms-pubs/about-form-6251 (Form 6251)
        #   - https://www.irs.gov/pub/irs-drop/rp-24-40.pdf  (2025 Rev. Proc.)
        _stage_with_outputs(
            "US25-AMT-AMTI",
            ("26 U.S.C. § 55", "26 U.S.C. § 56", "Instructions for Form 6251"),
            (USC_55_URL, USC_56_URL, FORM_6251_INSTRUCTIONS_URL),
            (
                "us.stage.taxable_income",
                "us.stage.preferential_capital_base",
                "us.capital.qualified_dividends",
                "us.assessment.inputs",
            ),
            "AMTI is rounded to cents before the § 55(d) exemption phase-out.",
            "AMTI assembly under § 56 must precede the § 55 exemption and tentative minimum tax.",
            "us.stage.amt_amti.amti_usd = taxable_income + § 56 add-backs (state/local SALT itemized, ISO bargain, depreciation timing, NOL adj.); preferential portion = qualified_dividends + net long-term capital gain (§ 55(b)(3))",
            (
                OutputDeclaration(
                    key="us.stage.amt_amti",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        _stage_with_outputs(
            "US25-AMT-TENTATIVE",
            ("26 U.S.C. § 55", "Instructions for Form 6251", "Rev. Proc. 2024-40"),
            (USC_55_URL, FORM_6251_INSTRUCTIONS_URL, REV_PROC_2024_40_URL),
            ("us.stage.amt_amti", "us.assessment.inputs"),
            "Exemption and tentative minimum tax are rounded to cents before the AMTFTC subtraction.",
            "§ 55(d) exemption (with § 55(d)(3) phase-out) and § 55(b) tentative minimum tax precede the § 59(a) AMTFTC.",
            "us.stage.amt_tentative.tentative_min_tax_usd = 26%/28% on (AMTI − exemption); § 55(b)(3) preserves § 1(h) preferential rates on long-term capital gain + qualified dividends inside AMT",
            (
                OutputDeclaration(
                    key="us.stage.amt_tentative",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # US25-AMT-FTC-AND-COMPARE: F-C4 — § 59(a) AMTFTC limitation per
        # basket = tentative_min × (foreign_source_amti_per_basket /
        # total_amti). Per-basket AMTI numerator equals the § 904(d)
        # numerator under the supported posture (no § 56 prefs); read it
        # from us.stage.ftc_denominator instead of scaling by tentative_min /
        # regular_tax (the dimensionally-incorrect previous formula).
        _stage_with_outputs(
            "US25-AMT-FTC-AND-COMPARE",
            ("26 U.S.C. § 59", "26 U.S.C. § 55", "Instructions for Form 6251"),
            (USC_59_URL, USC_55_URL, FORM_6251_INSTRUCTIONS_URL),
            (
                "us.stage.amt_amti",
                "us.stage.amt_tentative",
                "us.stage.baseline_allowed_ftc",
                "us.stage.allowed_ftc",
                "us.stage.regular_tax_before_credits",
                "us.stage.ftc_denominator",
                "us.assessment.inputs",
            ),
            # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 2 = AMT
            # (was line 1 on 2024 revision); https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
            "AMT owed is rounded to cents and floored at zero before Schedule 2 line 2 (2025 revision; was line 1 on 2024 revision); per-basket AMTFTC limitation is rounded to cents.",
            "§ 59(a) AMTFTC parallels § 904(d) per-category limitation but on the AMTI base; § 55(a) compares tentative minimum to regular tax after FTC.",
            "us.stage.amt_owed.amt_owed_usd = max(0, tentative_min_tax − AMTFTC − regular_tax_after_FTC) per § 55(a); AMTFTC = sum of per-category min(available_foreign_tax, tentative_min × category_amti_numerator / total_amti) per § 59(a)",
            (
                OutputDeclaration(
                    key="us.stage.amt_owed",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 2 = AMT
                # per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf and Form
                # 6251 line 11 instructions ("Enter here and on Schedule 2
                # (Form 1040), line 2"). Was Schedule 2 line 1 on 2024
                # revision. B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 2
                # = AMT under 26 U.S.C. § 55 / Form 6251 line 11. The
                # output key name retains the historical
                # ``schedule_2_line_1_amt_usd`` form for fingerprint
                # stability; FormLineRef.line below carries the 2025 IRS
                # line number. Pure 1:1 mirror of
                # ``us.stage.amt_owed.amt_owed_usd`` — no new arithmetic
                # (invariants I2 / I5 / I11).
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                OutputDeclaration(
                    key="us.tax.schedule_2_line_1_amt_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="2", url=IRS_ABOUT_SCHEDULE_2),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-ADDITIONAL-MEDICARE: 26 U.S.C. § 3101(b)(2) and
        # § 1401(b)(2) Additional Medicare Tax (Workstream 2). 0.9 %
        # additional tax on the COMBINED wage + SE base above the
        # filing-status threshold ($200,000 single / $250,000 MFJ /
        # $125,000 MFS). Form 8959 implements the combined wage/SE
        # arithmetic; the threshold is shared (single threshold across
        # both bases per § 3101(b)(2)(A)-(C)).
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
        # https://www.irs.gov/forms-pubs/about-form-8959
        _stage_with_outputs(
            "US25-ADDITIONAL-MEDICARE",
            ("26 U.S.C. § 3101(b)(2)", "26 U.S.C. § 1401(b)(2)", "IRS Form 8959"),
            (
                "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101&num=0&edition=prelim",
                "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401&num=0&edition=prelim",
                IRS_FORM_8959_URL,
            ),
            ("us.assessment.inputs", "us.stage.se_tax"),
            "Additional Medicare tax is rounded to cents to match Form 8959.",
            "§ 3101(b)(2) attaches when combined Medicare-taxable wages + SE earnings exceed the filing-status threshold; flows to Schedule 2 line 11.",
            "us.stage.additional_medicare = 0.009 * max(0, medicare_wages + se_taxable_earnings - threshold) per § 3101(b)(2) and § 1401(b)(2)",
            (
                OutputDeclaration(
                    key="us.stage.additional_medicare",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 11 =
                # Additional Medicare Tax (Form 8959 line 18). 1:1 mirror of
                # ``us.stage.additional_medicare.additional_medicare_tax_usd``
                # — no new arithmetic (invariant I5).
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                OutputDeclaration(
                    key="us.tax.schedule_2_line_11_additional_medicare_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="11", url=IRS_ABOUT_SCHEDULE_2),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B3 (FORM-MAPPING-FOLLOWUP) — Form 8959 line-level
                # decomposition. Each line is a declared rule output so
                # the Form 8959 renderer transits ``legal_value_entry``
                # with a real ``StageResult.output_fingerprint``
                # (invariants I2 / I11). Authority:
                #   - 26 U.S.C. § 3101(b)(2) (Medicare-wage portion).
                #   - 26 U.S.C. § 1401(b)(2) (SE portion).
                #   - Form 8959 instructions:
                #     https://www.irs.gov/forms-pubs/about-form-8959
                OutputDeclaration(
                    key="us.tax.form_8959_line_1_medicare_wages_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="1", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_4_total_medicare_wages_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="4", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_5_threshold_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="5", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_6_wages_excess_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="6", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_7_addtl_medicare_on_wages_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="7", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_8_se_taxable_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="8", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_11_residual_threshold_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="11", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_13_addtl_medicare_on_se_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="13", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8959_line_18_total_addtl_medicare_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8959", line="18", url=IRS_FORM_8959_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-CTC-AND-ODC: 26 U.S.C. § 24 — Child Tax Credit (§ 24(a))
        # and Credit for Other Dependents (§ 24(h)(4)) under the post-OBBBA
        # 2025 numerics. The stage runs after the regular-tax-after-FTC
        # baseline is fixed (US25-19A) so the nonrefundable portion can be
        # capped at it under § 24 ordering, and BEFORE US25-20-NIIT because
        # NIIT (Form 1040 line 22) is a separate additional tax that the
        # § 24 nonrefundable credit cannot offset. Form 1040 line 19 reads
        # the nonrefundable portion; Form 1040 line 28 reads the refundable
        # ACTC. Authority:
        #   - 26 U.S.C. § 24(a) (as substituted by § 24(h)(2) post-OBBBA
        #     for 2025) — $2,200 per qualifying child (§ 152(c))
        #   - 26 U.S.C. § 24(b) — phase-out at $200k single / $400k MFJ
        #   - 26 U.S.C. § 24(d)(1)(B) — refundable ACTC = 15% × (earned −
        #     $2,500), capped at $1,700 per qualifying child under
        #     § 24(d)(1)(A) (Rev. Proc. 2024-40 § 3.05)
        #   - 26 U.S.C. § 24(h)(4) — $500 ODC, NON-refundable
        #   - 26 U.S.C. § 24(h)(7) — CTC requires a valid SSN
        #   - 26 U.S.C. § 152(c) — qualifying child definition
        #   - Schedule 8812 / Rev. Proc. 2024-40 § 3.05 — refundable cap
        # https://www.law.cornell.edu/uscode/text/26/24
        # https://www.law.cornell.edu/uscode/text/26/152
        # https://www.irs.gov/forms-pubs/about-schedule-8812-form-1040
        # https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
        _stage_with_outputs(
            "US25-CTC-AND-ODC",
            (
                "26 U.S.C. § 24(a)",
                "26 U.S.C. § 24(b)",
                "26 U.S.C. § 24(d)",
                "26 U.S.C. § 24(h)(4)",
                "26 U.S.C. § 24(h)(7)",
                "26 U.S.C. § 152",
                "Schedule 8812 (2025) instructions",
                "Rev. Proc. 2024-40",
            ),
            (
                USC_24_URL,
                USC_152_URL,
                SCH_8812_INSTRUCTIONS_URL,
                REV_PROC_2024_40_URL,
            ),
            (
                "us.assessment.inputs",
                "us.stage.wages_usd",
                "us.stage.se_tax",
                "us.stage.adjusted_gross_income",
                "us.stage.feie",
                "us.stage.regular_tax_before_credits",
                "us.stage.baseline_allowed_ftc",
            ),
            "Cents-rounded throughout; the § 24(b)(3) phase-out rounds the MAGI excess up to the next $1,000 before applying the $50/$1,000 (5 %) reduction.",
            "§ 24 nonrefundable credit offsets regular tax after FTC and BEFORE the § 1411 NIIT additional tax. The refundable ACTC is computed AFTER the nonrefundable allocation under § 24(d).",
            "us.ctc.total_credit_usd = nonrefundable_portion + refundable_actc; nonrefundable_portion = min(combined_post_phaseout, regular_tax_after_ftc); refundable_actc = min(remaining_ctc, $1,700 × ctc_children, 15% × max(0, earned_income − $2,500)); combined_post_phaseout = max(0, $2,200 × ctc_children + $500 × odc_children − $50 × ceil(max(0, MAGI − threshold) / $1,000))",
            (
                # Schedule 8812 (2025) Line 4 — qualifying-children count
                # (§ 24(c)(1) / § 24(h)(7) SSN). Line 6 — qualifying
                # other-dependent count (§ 24(h)(4)). Surfaced as legal
                # outputs so the loader's child classification traces to
                # a real fingerprint at the form-line boundary.
                OutputDeclaration(
                    key="us.ctc.qualifying_ctc_count",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="4", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.gross_ctc_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="5", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.qualifying_odc_count",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="6", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.gross_odc_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="7", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.combined_pre_phaseout_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="8", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 9 — § 24(b)(2) phase-out threshold
                # ($200k single / $400k MFJ).
                OutputDeclaration(
                    key="us.ctc.phaseout_threshold_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="9", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 10 — Modified AGI under § 24(b)(2)
                # (AGI plus § 911 / § 933 add-backs, mirroring the
                # § 1411(d)(1)(A) NIIT MAGI base).
                OutputDeclaration(
                    key="us.ctc.modified_agi_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="10", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.phaseout_reduction_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="11", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.combined_post_phaseout_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="12", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 13 — regular tax after FTC ordering
                # cap from the Credit Limit Worksheet A. Per § 24(b)(3),
                # nonrefundable credits cannot reduce tax below zero.
                OutputDeclaration(
                    key="us.ctc.regular_tax_after_ftc_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="13", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.nonrefundable_portion_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="14", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # Schedule 8812 Line 16a — remaining-CTC ceiling that the
                # § 24(d)(1) refundable allocation chooses against.
                OutputDeclaration(
                    key="us.ctc.remaining_ctc_for_refundable_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="16a", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 16b — § 24(d)(1)(A) per-child
                # refundable cap ($1,700 for 2025; Rev. Proc. 2024-40
                # § 3.05).
                OutputDeclaration(
                    key="us.ctc.refundable_actc_cap_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="16b", url=REV_PROC_2024_40_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 18a — earned-income input to the
                # § 24(d)(1)(B) phase-in (wages + net SE earnings, less
                # § 911 excluded amounts under § 24(d)(1)(B)(i)).
                OutputDeclaration(
                    key="us.ctc.earned_income_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="18a", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 19 — statutory $2,500 earned-income
                # floor under § 24(d)(1)(B). Constant value (sourced from
                # CTC_REFUNDABLE_EARNED_INCOME_FLOOR_USD in the law module
                # per invariant I1) but surfaced as an output so the
                # audit graph records where the floor was sourced.
                OutputDeclaration(
                    key="us.ctc.earned_income_floor_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="19", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 20 — max(0, earned_income − $2,500).
                OutputDeclaration(
                    key="us.ctc.earned_income_excess_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="20", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Schedule 8812 Line 21 — 15 % × (earned_income − $2,500).
                OutputDeclaration(
                    key="us.ctc.refundable_actc_earned_income_phase_in_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="21", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # Post-phaseout CTC share (combined_post × gross_ctc /
                # combined_pre) — internal split used to compute Line 16a;
                # not a Schedule 8812 line itself but on the audit graph.
                OutputDeclaration(
                    key="us.ctc.post_phaseout_ctc_share_usd",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.ctc.refundable_actc_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 8812", line="27", url=USC_24_URL),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.ctc.total_credit_usd",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-20: § 1411 NIIT = 3.8 % * min(NII, MAGI excess).
        # Lands on Form 8960 line 17 / Schedule 2 line 12 via the
        # renderer's ``_write_form_8960`` FormEntry projection. F-C2 —
        # § 1411(d)(1)(A) modifies AGI for NIIT by adding back the § 911
        # excluded foreign earned income (and § 911(c) housing exclusion).
        # ``us.stage.feie`` carries the add-back via
        # ``niit_magi_addback_usd``; the rule reads it directly so the
        # FEIE election can never strip the NIIT base.
        # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411
        _stage_with_outputs(
            "US25-20-NIIT",
            ("26 U.S.C. § 1411", "26 U.S.C. § 1411(d)(1)(A)", "26 U.S.C. § 911", "Instructions for Form 8960"),
            (USC_1411_URL, USC_911_URL, IRS_I8960),
            (
                "us.stage.adjusted_gross_income",
                "us.stage.income_side_inputs",
                "us.stage.capital_loss_result",
                "us.stage.feie",
                "us.assessment.inputs",
            ),
            "NIIT is rounded to cents after applying the 3.8 percent rate.",
            "NIIT is a separate additional tax and is not offset by FTC or treaty credits; § 1411(d)(1)(A) requires AGI plus § 911 excluded amount as the MAGI base before the § 1411 threshold is applied.",
            "us.stage.niit = 0.038 * min(net_investment_income, max(0, (AGI + § 911 excluded amount + § 911(c) housing exclusion) - § 1411 threshold)) per 26 U.S.C. §§ 1411, 1411(d)(1)(A)",
            (
                OutputDeclaration(
                    key="us.stage.niit",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 12 = § 1411
                # NIIT (Form 8960 line 17). 1:1 mirror of
                # ``us.stage.niit.niit_usd`` — no new arithmetic (I5).
                # B5 — same scalar also lands on Form 8960 line 17, so
                # the renderer reads the same fingerprint for both
                # form-line writes.
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                # https://www.irs.gov/forms-pubs/about-form-8960
                OutputDeclaration(
                    key="us.tax.schedule_2_line_12_niit_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="12", url=IRS_ABOUT_SCHEDULE_2),
                        FormLineRef(form="Form 8960", line="17", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B5 (FORM-MAPPING-FOLLOWUP) — Form 8960 Part I (line 1
                # interest, line 2 dividends, lines 5a-5d capital
                # gain/loss subgroup) and Part III (line 8 total
                # investment income, line 12 net investment income).
                # Authority: 26 U.S.C. § 1411 + Form 8960 instructions:
                #   https://www.irs.gov/forms-pubs/about-form-8960
                OutputDeclaration(
                    key="us.tax.form_8960_line_1_interest_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="1", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_2_ordinary_dividends_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="2", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_5a_capital_gain_loss_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="5a", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_5b_non_section_1411_adj_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="5b", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_5c_cfc_pfic_adj_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="5c", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_5d_combined_capital_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="5d", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # B-audit (FORM-MAPPING-FOLLOWUP, 2026-05-03) — Form 8960
                # line 7 ("Other modifications to investment income")
                # carries substitute-payment income and (when elected)
                # staking income into the line-8 sum. Without surfacing
                # line 7 the rendered Part I lines do NOT foot to line 8
                # whenever line 7 is non-zero (brenn-2025 has $423.24 of
                # substitute payments, so line 1+2+5d alone undershoots
                # line 8 by exactly that amount). Authority: Form 8960
                # instructions, Part I line 7:
                #   https://www.irs.gov/forms-pubs/about-form-8960
                OutputDeclaration(
                    key="us.tax.form_8960_line_7_other_modifications_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="7", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_8_total_investment_income_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="8", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B-audit — Form 8960 line 11 ("Total deductions and
                # modifications") = sum of Part II lines 9a-9c + 10. Zero
                # in the supported posture (no investment-expense
                # deductions modeled), but surfaced so the rendered line
                # 12 = line 8 − line 11 reconciles from visible
                # components rather than relying on an unrendered zero.
                OutputDeclaration(
                    key="us.tax.form_8960_line_11_total_deductions_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="11", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.form_8960_line_12_net_investment_income_usd",
                    form_line_refs=(
                        FormLineRef(form="Form 8960", line="12", url=IRS_ABOUT_FORM_8960),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # US25-21: refund/balance arithmetic lands on Form 1040 line
        # 35a / 37 via the renderer's ``_write_1040`` FormEntry. The
        # rule's net result is a reconciliation invariant (refund vs.
        # amount-owed sign).
        # IRS-VERIFIED 2026-05-10 — Schedule 2 (2025) line 2 / Form 1040
        # line 17 per https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
        # F-US-1: total_tax composition now includes us.stage.amt_owed
        # (Schedule 2 line 2 / Form 1040 line 17 — 2025 revision; was line 1
        # on 2024 revision). Without it, AMT-binding filers had a silently
        # understated total_tax.
        # A2 (FORM-MAPPING-FOLLOWUP): add ``us.tax.line_22_after_credits_usd``
        # — Form 1040 line 22 (line 18 minus line 21) — as an explicit
        # declared rule output so the rendered 1040 walks 16 / 17 / 19 /
        # 20 / 22 / 23 instead of jumping from 21 to 23. The subtraction
        # lives inside ``us25_21_payments.calculate(...)`` per invariant
        # I5 (no Decimal arithmetic on legal output keys outside the
        # rule graph). The output uses ``INTERMEDIATE_MATH`` + no
        # ``FormLineRef`` to match every other 1040 line in the renderer:
        # Form 1040 has no opted-in ``FormLineRef`` declarations today,
        # so adding one would flip the bidirectional I3 gate ON for the
        # entire Form 1040 surface and cascade-break every other 1040
        # renderer read. Authority:
        #   - Form 1040 instructions (line 22 = line 18 − line 21)
        #     https://www.irs.gov/instructions/i1040gi
        #   - 26 U.S.C. § 24(b)(3) ordering (CTC nonrefundable subtracted
        #     before additional taxes) — already cited above.
        #   - 26 U.S.C. § 901 / § 904 (FTC nonrefundable, on Schedule 3
        #     line 1 / Form 1040 line 20).
        _stage_with_outputs(
            "US25-21-PAYMENTS",
            ("Instructions for Form 1040", "26 U.S.C. § 24"),
            (IRS_I1040, USC_24_URL),
            (
                "us.stage.regular_tax_before_credits",
                "us.stage.allowed_ftc",
                "us.stage.niit",
                "us.stage.amt_owed",
                "us.stage.se_tax",
                "us.stage.additional_medicare",
                "us.ctc.nonrefundable_portion_usd",
                "us.ctc.refundable_actc_usd",
                "us.payments.estimated",
                "us.stage.baseline_allowed_ftc",
                "us.stage.treaty_additional_ftc",
                "us.assessment.inputs",
            ),
            "Final payment/refund arithmetic remains cent-level in the support package.",
            "Payments are applied after tax, final credits including treaty re-sourcing and the § 24 nonrefundable CTC/ODC (Form 1040 line 19), and additional taxes (AMT + NIIT + SE tax + Additional Medicare). The § 24(d) refundable ACTC (Form 1040 line 28) is then added to payments.",
            "us.stage.refund_or_balance = us.payments.estimated + ctc.refundable_actc - (regular_tax_before_credits - allowed_ftc - ctc.nonrefundable + amt_owed + niit + se_tax + additional_medicare); positive => refund (line 35a), negative => amount owed (line 37). us.tax.line_22_after_credits_usd = max(0, line_18 - line_21) where line_18 = regular_tax + amt_owed and line_21 = ctc.nonrefundable + (baseline_allowed_ftc + treaty_additional_ftc).",
            (
                OutputDeclaration(
                    key="us.stage.refund_or_balance",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # A2: Form 1040 line 22 = line 18 minus line 21. The
                # treaty-resourced version (line 20 includes the Pub. 514
                # additional credit) is what the renderer ultimately
                # writes; we surface both for symmetry with the existing
                # ``total_tax_*`` pair on ``us.stage.refund_or_balance``.
                OutputDeclaration(
                    key="us.tax.line_22_after_credits_usd",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="us.tax.line_22_after_credits_with_treaty_resourcing_usd",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # IRS-VERIFIED 2026-05-11 — Schedule 2 (2025) Part I per
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf.
                # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 3 = sum
                # of Part I (line 1z additions to tax + line 2 AMT).
                # IRS-VERIFIED 2026-05-11 — In the 2025 revision,
                # lines 1a-1y are additions to tax (APTC repayment,
                # clean-vehicle credit repayments, Form 4255 EPE
                # recapture, other); 1z is the subtotal of 1a..1y; and
                # line 2 is the AMT (Form 6251 line 11) per
                # IRS-VERIFIED 2026-05-11 f1040s2.pdf. The supported
                # posture has no line-1z additions (1z = $0), so
                # line 3 = line 2 = AMT for the chosen treaty posture.
                # Surfaced as a declared rule output so the Schedule 2
                # renderer reads a fingerprinted value (invariants
                # I2 / I11). The sum lives inside this rule's calculate
                # body per invariant I5 (no Decimal arithmetic on legal
                # IRS-VERIFIED 2026-05-11 — Form 1040 line 17 reads
                # from this value per the 2025 chain.
                # output keys outside the rule graph).
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                # https://www.irs.gov/instructions/i1040gi
                OutputDeclaration(
                    key="us.tax.schedule_2_line_3_total_amt_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="3", url=IRS_ABOUT_SCHEDULE_2),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # B1 (FORM-MAPPING-FOLLOWUP) — Schedule 2 line 21 = total
                # Part II "Other Taxes" (sum of lines 4-18 plus § 1411 NIIT
                # and § 1401(b)(2) Additional Medicare in 2025). For the
                # supported posture line 21 = line 4 (SE) + line 11
                # (Additional Medicare) + line 12 (NIIT). Lives inside this
                # rule's calculate body per invariant I5. Form 1040 line 23
                # reads from this value.
                # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf
                # https://www.irs.gov/instructions/i1040gi
                OutputDeclaration(
                    key="us.tax.schedule_2_line_21_total_other_taxes_usd",
                    form_line_refs=(
                        FormLineRef(form="Schedule 2", line="21", url=IRS_ABOUT_SCHEDULE_2),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # NOTE — historical B2 declarations for
                # ``us.tax.schedule_3_line_6c_other_refundable_credits_usd``
                # and ``us.tax.schedule_3_line_11_treaty_resourcing_additional_ftc_usd``
                # were REMOVED in the B-audit pass (2026-05-03). Per the
                # IRS Schedule 3 (2024 / 2025) form line numbering:
                #   - line 6c is the Adoption credit (Form 8839),
                #   - line 11 is "Excess Social Security and Tier 1
                #     RRTA tax withheld",
                # neither of which is the treaty FTC add-on. The Pub.
                # 514 worksheet line 21 value is already captured inside
                # ``us.stage.treaty_additional_ftc`` (US25-18) and
                # implicitly carried into Schedule 3 via
                # ``us.tax.schedule_3_line_1_ftc_total_usd`` (post-cap
                # allowed FTC). No parallel Schedule 3 line surface.
            ),
        ),
        # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03):
        # US25-FATCA-FBAR-DETERMINATION — 26 U.S.C. § 6038D / Reg.
        # § 1.6038D-2 Form 8938 ("Statement of Specified Foreign
        # Financial Assets") and 31 U.S.C. § 5314 / 31 CFR § 1010.350
        # FinCEN Form 114 ("FBAR") filing-determination stage.
        #
        # Determination-only — does NOT change tax owed. The rule reads
        # ``us.assessment.inputs.fatca_fbar_inputs`` (filing status,
        # residency basis, per-account balances) and emits booleans +
        # threshold scalars consumed by the renderer to produce two
        # status sheets:
        #   - ``2025_form_8938_status.md`` — REQUIRED / NOT REQUIRED for
        #     Form 8938 attachment under § 6038D.
        #   - ``2025_fincen_114_status.md`` — REQUIRED / NOT REQUIRED for
        #     the FinCEN 114 (FBAR) filing under 31 CFR § 1010.350.
        #
        # The rule fails closed (``status="not_applicable"``) when the
        # workspace has not enumerated foreign accounts, per CLAUDE.md
        # fail-closed posture. A silent zero would be indistinguishable
        # from "below threshold" and is unacceptable for filings that
        # carry significant non-filing penalties.
        #
        # Authority:
        #   - 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
        #   - 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
        #   - IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
        #   - 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
        #   - 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
        #   - FinCEN BSA E-Filing — https://bsaefiling.fincen.treas.gov/
        _stage_with_outputs(
            "US25-FATCA-FBAR-DETERMINATION",
            (
                "26 U.S.C. § 6038D",
                "26 CFR § 1.6038D-2",
                "31 U.S.C. § 5314",
                "31 CFR § 1010.350",
                "IRS Form 8938 instructions",
            ),
            (
                USC_6038D_URL,
                CFR_1_6038D_2_URL,
                USC_31_5314_URL,
                CFR_31_1010_350_URL,
                IRS_FORM_8938_URL,
                FINCEN_BSA_EFILING_URL,
                IRS_FORM_8938_VS_FBAR_URL,
            ),
            ("us.assessment.inputs",),
            "Threshold and aggregate balances are USD-translated by the loader; rounded to cents inside the rule.",
            "FATCA / FBAR determinations are independent of tax owed and run after every tax-affecting stage so they reflect the same posture and balance set.",
            "us.fatca.form_8938_required = (foreign_specified_assets_eoy > threshold_eoy) OR (foreign_specified_assets_max > threshold_anytime); us.fbar.fincen_114_required = (aggregate_max_balance > $10,000) per § 6038D / 31 CFR § 1010.350.",
            (
                OutputDeclaration(
                    key="us.fatca.form_8938_threshold_eoy_usd",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.fatca.form_8938_threshold_anytime_usd",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.fatca.foreign_specified_assets_max_usd",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                OutputDeclaration(
                    key="us.fatca.foreign_specified_assets_eoy_usd",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                OutputDeclaration(
                    key="us.fatca.form_8938_required",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.fbar.aggregate_max_balance_usd",
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                OutputDeclaration(
                    key="us.fbar.fincen_114_required",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="us.fatca.determination_status",
                    audit_waypoints=frozenset({AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}),
                ),
                OutputDeclaration(
                    key="us.fatca.determination_reason",
                    audit_waypoints=frozenset({AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}),
                ),
            ),
        ),
    )



__all__ = [
    "usa_law_stages_2025",
]
