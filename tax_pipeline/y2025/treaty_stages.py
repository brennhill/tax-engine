"""Declared LawStages for the U.S.-Germany treaty re-sourcing graph.

This module is the static contract: legal references, authority URLs, input
and output fact keys, formulas, narrative templates. The per-stage rule
functions that actually execute live in
``tax_pipeline.y2025.treaty_rules``.

Phase B migration: every stage now declares its outputs via the new
``outputs=tuple[OutputDeclaration, ...]`` shape so each output carries its
own form-line provenance or audit-waypoint classification. The dual-mode
``LawStage`` derives the legacy ``output_keys`` / ``form_line_refs`` /
``form_line_urls`` fields from ``outputs`` so downstream graph builders,
fingerprint computations, and narrative templates keep operating against
the same surface — and per the fingerprint-stability invariant tested by
``tests/y_agnostic/test_law_stage_outputs.py::LawStageFingerprintStabilityTest`` the
derived form-line strings reproduce the legacy strings byte-for-byte so
audit packets do not churn during the migration.
"""

from __future__ import annotations

from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.y2025.treaty_law import DBA_USA_ART_28_URL
from tax_pipeline.y2025.us_law import IRS_GERMANY_TECH, IRS_P514


def _stage_template_id(stage_id: str) -> str:
    return stage_id


# Cited form titles — kept as named constants so the form/line split used to
# reproduce the legacy form_line_refs strings is readable and identical
# everywhere it appears. The line text intentionally retains the leading
# em-dash separator so ``FormLineRef.render()`` (``f"{form} {line}"``)
# reconstructs the legacy string verbatim, preserving the LawStage
# fingerprint across the migration.
_PUB_514_WORKSHEET = "Pub. 514 treaty re-sourcing worksheet"
_FORM_1116 = "Form 1116"
# C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): Per Form 1116 instructions and
# IRS Publication 514, treaty re-sourced U.S.-source income is placed in
# a SEPARATE Form 1116 with the basket header "Certain Income Resourced
# by Treaty" (the § 904(d)(6) basket). The renderer
# (``_write_form_1116_resourced``) emits a ``2025_form_1116_resourced.md``
# file; the canonical form name on its FormLineRef declarations is
# "Form 1116 Resourced" — distinct from "Form 1116 Passive" /
# "Form 1116 General".
_FORM_1116_RESOURCED = "Form 1116 Resourced"
_IRS_FORM_1116_INSTR_URL = "https://www.irs.gov/instructions/i1116"
_IRS_ABOUT_FORM_1116_URL = "https://www.irs.gov/forms-pubs/about-form-1116"


def treaty_law_stages_2025() -> tuple[LawStage, ...]:
    # Per invariant I3 (renderer ↔ OutputDeclaration form-line
    # bidirectional contract), the U.S. renderer
    # (``tax_pipeline/forms/usa.py``) consumes treaty packet values via
    # ``FormEntry`` projections from the saved ``us-treaty-package.json``
    # rather than via ``_required_form_line``. Treaty stages therefore
    # classify their outputs with closed-enum ``AuditWaypoint`` values
    # describing each value's role in the Pub. 514 worksheet flow; the
    # Pub. 514 worksheet line numbers and DBA-USA Article 23 mechanics
    # continue to ride on ``legal_refs``, ``authority_urls``, and the
    # per-output ``legal_formula``. WS-2B re-anchors the form-line
    # declarations off the renderer-orphan path.
    return (
        # TREATY25-LOB-QUALIFICATION: DBA-USA Art. 28 (Limitation on
        # Benefits, as amended by the 2006 Protocol) gates every other
        # treaty benefit. A treaty resourcing claim under Art. 23 / Pub.
        # 514 requires LOB qualification under one of:
        #   - Art. 28(2)(c) publicly traded company
        #   - Art. 28(2)(a)/(f) qualified resident (incl. individuals)
        #   - Art. 28(4) active business
        #   - Art. 28(5)/(7) derivative benefits
        #   - Art. 28(7) competent authority discretionary determination
        # ``not_qualified`` disables resourcing and triggers Form 8833
        # disclosure (§ 6114). Workstream 4 of the 2026-05-01 USA
        # legal-flow review.
        # https://www.irs.gov/pub/irs-trty/germany.pdf (Art. 28)
        LawStage(
            stage_id="TREATY25-LOB-QUALIFICATION",
            country_or_scope="US-DE-TREATY-2025",
            legal_refs=("DBA-USA Art. 28 (Limitation on Benefits, 2006 Protocol)",),
            authority_urls=(DBA_USA_ART_28_URL,),
            input_fact_keys=("us.treaty.inputs",),
            rounding_policy="No currency rounding; LOB qualification is a categorical gate.",
            law_order_note="Art. 28 LOB qualification gates the rest of the treaty graph; if a taxpayer cannot qualify under one of the five paragraphs, treaty re-sourcing is disabled.",
            legal_formula="treaty.lob_qualified = lob_category != 'not_qualified'; treaty.form_8833_required = use_treaty_resourcing AND treaty.lob_qualified per DBA-USA Art. 28 + § 6114",
            narrative_templates={"en": _stage_template_id("TREATY25-LOB-QUALIFICATION")},
            outputs=(
                OutputDeclaration(
                    key="treaty.lob_qualified",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="treaty.lob_category",
                    audit_waypoints=frozenset({AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}),
                ),
                OutputDeclaration(
                    key="treaty.form_8833_required",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
        # TREATY25-15: Pub. 514 worksheet line 15. Two outputs split the
        # dividend stack into U.S.-source ordinary and U.S.-source
        # qualified portions. Both are PER_POSTEN_AGGREGATION values
        # feeding the average-rate worksheet line 16-21 calculation
        # downstream; neither independently appears on a U.S. or German
        # form line the renderer reads via ``_required_form_line``.
        LawStage(
            stage_id="TREATY25-15-US-SOURCE-DIVIDENDS",
            country_or_scope="US-DE-TREATY-2025",
            legal_refs=("IRS Publication 514", "Germany treaty technical explanation"),
            authority_urls=(IRS_P514, IRS_GERMANY_TECH),
            input_fact_keys=("us.treaty.inputs", "treaty.dividend_split", "treaty.lob_qualified"),
            rounding_policy="Treaty worksheet values are rounded to cents at each Pub. 514 worksheet line.",
            law_order_note="The treaty worksheet starts from the U.S.-source dividend split before the average-rate worksheet runs.",
            legal_formula="treaty.us_source_dividends = ordinary_dividends - foreign_source_passive_dividends; treaty.us_source_qualified_dividends = qualified_dividends - foreign_source_qualified_dividends (Pub. 514 worksheet line 15)",
            narrative_templates={"en": _stage_template_id("TREATY25-15-US-SOURCE-DIVIDENDS")},
            outputs=(
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the U.S.-source
                # dividend stack lands on Form 1116 Resourced Line 1a
                # (re-sourced gross income) per § 904(d)(6) and the
                # ``Certain Income Resourced by Treaty`` basket header.
                # The C-audit (2026-05-04) anchors the renderer write
                # to this declared rule output via the bidirectional
                # I3 contract.
                OutputDeclaration(
                    key="treaty.us_source_dividends",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="1a",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
                ),
                OutputDeclaration(
                    key="treaty.us_source_qualified_dividends",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # TREATY25-16: Pub. 514 worksheet lines 16-18.
        # Three outputs: line 16 (avg-rate U.S. tax on US-source dividends),
        # line 17 (15 % treaty floor), line 18 (residual above the floor).
        # The legacy stage shared a single "lines 16-18" ref across all three.
        # To preserve fingerprint stability the line-18 output (the residual
        # above the 15 % floor) owns that single ref — it is the value the
        # downstream stages actually consume — and the upstream worksheet
        # sub-components are classified INTERMEDIATE_MATH. Note: line 16 and
        # line 17 ARE Pub. 514 worksheet lines in the legal sense; the
        # INTERMEDIATE_MATH label here reflects the per-stage flat-list
        # constraint of the legacy form_line_refs tuple, not their absence
        # from the worksheet. The "lines 16-18" string already cites all
        # three lines collectively, so audit transparency is preserved.
        LawStage(
            stage_id="TREATY25-16-AVERAGE-TAX-FLOOR",
            country_or_scope="US-DE-TREATY-2025",
            legal_refs=("IRS Publication 514", "Germany treaty technical explanation"),
            authority_urls=(IRS_P514, IRS_GERMANY_TECH),
            input_fact_keys=(
                "us.treaty.inputs",
                "treaty.us_source_dividends",
                "us.stage.regular_tax_before_credits",
                # F-FN-2: Pub. 514 worksheet line 16 uses **taxable income**
                # (Form 1040 line 15), not AGI, as the average-rate denominator.
                "us.stage.taxable_income",
                # ``us.constants.treaty_dividend_rate`` is sourced from the
                # centralized DBA-USA Art. 10(2)(b) constant
                # (``us_2025_law.TREATY_DIVIDEND_RATE`` ->
                # ``treaty_2025_law.DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE``)
                # via ``treaty_initial_facts_2025`` in
                # ``treaty_2025_rules.py``. Single source of truth.
                "us.constants.treaty_dividend_rate",
            ),
            rounding_policy="Treaty worksheet values are rounded to cents at each Pub. 514 worksheet line.",
            law_order_note="Publication 514 applies an average-tax-rate method and compares it to the treaty source-country floor.",
            legal_formula="line_16 = regular_tax_before_credits * us_source_dividends / taxable_income; line_17 = treaty_dividend_rate * us_source_dividends; line_18 = max(0, line_16 - line_17)",
            narrative_templates={"en": _stage_template_id("TREATY25-16-AVERAGE-TAX-FLOOR")},
            outputs=(
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``treaty.us_tax_on_us_source_dividends`` is the smaller-
                # of cap (Pub. 514 worksheet line 16, the average-rate
                # U.S. tax on the re-sourced dividends) that binds the
                # nonrefundable resourced credit on Form 1116 Resourced
                # Line 33. The C-audit (2026-05-04) anchors the renderer
                # write via the bidirectional I3 contract.
                OutputDeclaration(
                    key="treaty.us_tax_on_us_source_dividends",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="33",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="treaty.treaty_minimum_us_tax_at_source",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                OutputDeclaration(
                    key="treaty.us_limitation_above_15_percent_floor",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # TREATY25-17: Pub. 514 worksheet lines 19 and 20c (dual cap).
        # Four outputs: line 19 (residual U.S. tax above max(floor, residence
        # credit)), line 20c (residual German tax above the same clamp), plus
        # two passthrough values (German pre-credit tax, German residence
        # credit) that are inputs to the dual cap. The legacy stage shared a
        # single "lines 19 / 20c" ref. To preserve fingerprint stability the
        # line 19 output owns the ref; line 20c is classified
        # RECONCILIATION_INVARIANT because line 21 (TREATY25-18) reconciles
        # the two by ``min(line_19, line_20c)`` — the dual-cap reconciliation
        # is the central treaty-credit invariant under DBA-USA Art. 23. The
        # German precredit and residence-credit passthroughs are
        # INTERMEDIATE_MATH (clamp inputs, never on a U.S. form line).
        LawStage(
            stage_id="TREATY25-17-GERMAN-RESIDUAL-CAP",
            country_or_scope="US-DE-TREATY-2025",
            legal_refs=("IRS Publication 514", "Germany treaty technical explanation"),
            authority_urls=(IRS_P514, IRS_GERMANY_TECH),
            input_fact_keys=(
                "us.treaty.inputs",
                "treaty.us_tax_on_us_source_dividends",
                "treaty.treaty_minimum_us_tax_at_source",
                "de.treaty.us_source_dividend_tax_and_credit",
            ),
            rounding_policy="Treaty worksheet values are rounded to cents at each Pub. 514 worksheet line.",
            law_order_note="Pub. 514 lines 19-20c clamp by the greater of the 15 % floor and the German residence credit on the same dividends.",
            legal_formula="line_19 = max(0, line_16 - max(line_17, residence_credit)); line_20c = max(0, german_precredit - max(line_17, residence_credit))",
            narrative_templates={"en": _stage_template_id("TREATY25-17-GERMAN-RESIDUAL-CAP")},
            outputs=(
                OutputDeclaration(
                    key="treaty.worksheet_line_19_maximum_credit",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="treaty.german_residual_cap",
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="treaty.german_precredit_tax_on_us_source_dividends",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03):
                # ``treaty.german_residence_credit_for_us_tax`` is the
                # foreign tax paid on the re-sourced income — the
                # German residence-state credit allocable to U.S.-source
                # dividends after the DBA-USA Art. 10(2)(b) ceiling.
                # Lands on Form 1116 Resourced Line 8.
                OutputDeclaration(
                    key="treaty.german_residence_credit_for_us_tax",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="8",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
            ),
        ),
        # TREATY25-18: Pub. 514 worksheet line 21 + Form 1116 line 12.
        # Three outputs: line 21 (the dual-cap min), the additional FTC carried
        # to Form 1116 line 12, and the regular tax after the treaty add-on.
        # The legacy stage carried two refs in this order:
        #   1. "Pub. 514 ... — line 21 (additional credit)"
        #   2. "Form 1116 line 12 (treaty re-sourcing add-on)"
        # The line 21 output owns the first ref AND is tagged
        # RECONCILIATION_INVARIANT because line 21 = min(line 19, line 20c)
        # is the final dual-cap reconciliation. The additional_foreign_tax_credit
        # output owns the Form 1116 line 12 ref. The post-treaty regular tax
        # is classified INTERMEDIATE_MATH — it's the running tax-after-credits
        # value the downstream U.S. stages consume; it does not independently
        # appear on a Form 1116 line at this point in the worksheet.
        LawStage(
            stage_id="TREATY25-18-ADDITIONAL-FTC",
            country_or_scope="US-DE-TREATY-2025",
            legal_refs=("IRS Publication 514", "Germany treaty technical explanation"),
            authority_urls=(IRS_P514, IRS_GERMANY_TECH),
            input_fact_keys=(
                "us.treaty.inputs",
                "treaty.worksheet_line_19_maximum_credit",
                "treaty.german_residual_cap",
                "us.stage.regular_tax_after_ftc",
                "us.stage.remaining_form_1116_line_33_cap",
            ),
            rounding_policy="Treaty worksheet values are rounded to cents at each Pub. 514 worksheet line.",
            law_order_note="Pub. 514 worksheet line 21 is the lesser of line 19 and line 20c; Form 1116 line 33 then caps the nonrefundable credit.",
            legal_formula="line_21 = min(line_19, line_20c); additional_ftc = min(line_21, remaining_form_1116_line_33_cap); regular_tax_after_ftc_and_treaty = regular_tax_after_ftc - additional_ftc",
            narrative_templates={"en": _stage_template_id("TREATY25-18-ADDITIONAL-FTC")},
            outputs=(
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the dual-cap
                # min lands on Form 1116 Resourced Line 21 (resourced
                # limitation) on the separate § 904(d)(6) Form 1116.
                OutputDeclaration(
                    key="treaty.worksheet_line_21_additional_credit",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="21",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                # C7 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the allowed
                # credit (smaller of foreign tax / limitation) lands on
                # Form 1116 Resourced Line 22.
                OutputDeclaration(
                    key="treaty.additional_foreign_tax_credit",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="22",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
                OutputDeclaration(
                    key="treaty.regular_tax_after_ftc_and_treaty_resourcing",
                    audit_waypoints=frozenset({AuditWaypoint.INTERMEDIATE_MATH}),
                ),
                # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): the
                # § 904(d)(6) treaty-resourced basket has no prior-year
                # carryover by treaty design — the basket is created
                # annually by treaty election and § 904(c) carryovers
                # do not cross treaty-basket boundaries. Surfacing the
                # 0.00 value as a declared rule output (rather than a
                # renderer-side literal) anchors Form 1116 Resourced
                # Line 10 to the I3 bidirectional contract.
                OutputDeclaration(
                    key="treaty.resourced_basket_carryover",
                    form_line_refs=(
                        FormLineRef(
                            form=_FORM_1116_RESOURCED,
                            line="10",
                            url=_IRS_ABOUT_FORM_1116_URL,
                        ),
                    ),
                    audit_waypoints=frozenset({AuditWaypoint.RECONCILIATION_INVARIANT}),
                ),
            ),
        ),
    )


__all__ = [
    "treaty_law_stages_2025",
]
