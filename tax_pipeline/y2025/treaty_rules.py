"""Per-stage rule functions for the U.S.-Germany treaty re-sourcing graph.

This module is the single execution path for the four declared treaty
LawStages (TREATY25-15 through TREATY25-18). Bodies are lifted from the
historical ``treaty_resourcing_assessment_2025`` monolith in
``tax_pipeline/y2025/us_law.py``, split on stage boundaries so that every
legal value tracked by ``USTreatyResourcingAssessment2025`` is produced by
a ``LawRule.calculate`` invocation.

Authority:

- IRS Publication 514 "Foreign Tax Credit for Individuals"
  (https://www.irs.gov/publications/p514) — additional foreign tax credit
  worksheet for U.S.-source income re-sourced under a treaty.
- Germany treaty technical explanation
  (https://www.irs.gov/pub/irs-trty/germtech.pdf) — Article 23 residence-
  country relief mechanics that bound the additional credit.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import LawRule, LawStage, RuleGraphExecution, execute_rule_graph
from tax_pipeline.pipeline_context import set_pipeline_context_value
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.treaty_law import LOB_QUALIFICATION_CATEGORIES
from tax_pipeline.y2025.us_law import (
    TREATY_DIVIDEND_RATE,
    USTreatyInputs2025,
    USTreatyResourcingAssessment2025,
    round_cents,
    validate_germany_treaty_dividend_coverage_2025,
    validate_treaty_resourcing_dividend_split_2025,
    validate_treaty_resourcing_inputs_2025,
)

ZERO_USD = Decimal("0.00")
TREATY_EXECUTION_CONTEXT_KEY = "us25.treaty_rule_graph_execution"
"""Pipeline-context key under which ``execute_treaty_rule_graph`` stashes the
executed ``RuleGraphExecution``.

The narrative packet builder reads this so audit packets are built from real
executed StageResults rather than replayed pre-computed values. Same in-memory
hand-off pattern that the treaty dividend bridge uses
(``treaty_bridge_2025.GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY``).
"""


def _treaty_inputs(facts: Mapping[str, Any]) -> USTreatyInputs2025:
    treaty_inputs = facts["us.treaty.inputs"]
    if not isinstance(treaty_inputs, USTreatyInputs2025):
        raise TypeError("us.treaty.inputs must be a USTreatyInputs2025 instance")
    return treaty_inputs


def _zero_outputs_for(stage: LawStage) -> dict[str, Decimal]:
    return {key: ZERO_USD for key in stage.output_keys}


def treaty25_lob_qualification(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # DBA-USA Art. 28 (Limitation on Benefits, as amended by the 2006
    # Protocol) — treaty benefits require qualification under one of
    # the five enumerated tests. The category is read off the typed
    # ``USTreatyInputs2025.lob_qualification_category`` (Workstream 4
    # of the 2026-05-01 USA legal-flow review). Form 8833 disclosure
    # under § 6114 is required whenever the taxpayer claims treaty
    # re-sourcing AND qualifies under Art. 28; without qualification,
    # treaty re-sourcing is disabled (treaty.lob_qualified = False).
    # https://www.irs.gov/pub/irs-trty/germany.pdf (Art. 28)
    treaty_inputs = _treaty_inputs(facts)
    raw_category = (treaty_inputs.lob_qualification_category or "").strip().lower()
    if raw_category not in LOB_QUALIFICATION_CATEGORIES:
        # Fail-closed: an unrecognized category is not a legal posture.
        # Per CLAUDE.md, missing legal posture must fail closed instead
        # of silently denying or granting treaty benefits.
        raise ValueError(
            f"Unsupported DBA-USA Art. 28 LOB qualification category "
            f"{treaty_inputs.lob_qualification_category!r}; expected one of "
            + ", ".join(sorted(LOB_QUALIFICATION_CATEGORIES))
        )
    qualified = raw_category != "not_qualified"
    if treaty_inputs.use_treaty_resourcing and not qualified:
        # Art. 28 + Pub. 514: a taxpayer who cannot qualify under any
        # of the five paragraphs cannot claim treaty re-sourcing.
        raise ValueError(
            "Treaty re-sourcing requires DBA-USA Art. 28 LOB qualification; "
            "lob_qualification_category='not_qualified' disables re-sourcing. "
            "Either select a qualifying category (publicly_traded, "
            "qualified_resident, active_business, derivative_benefits, "
            "competent_authority) or set use_treaty_resourcing=false."
        )
    # Form 8833 disclosure under § 6114 is required when treaty
    # benefits are claimed (with limited de-minimis exceptions for
    # treaty rates that simply implement statutory withholding limits).
    form_8833_required = bool(treaty_inputs.use_treaty_resourcing and qualified)
    return {
        "treaty.lob_qualified": qualified,
        "treaty.lob_category": raw_category,
        "treaty.form_8833_required": form_8833_required,
    }


def treaty25_15_us_source_dividends(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 15: U.S.-source ordinary and qualified dividends
    # equal the dividend totals less the foreign-source split. The validation
    # gates here run only when the taxpayer claims treaty re-sourcing; without
    # that election, the stage produces zeros and the downstream stages cascade
    # zeros through the worksheet.
    treaty_inputs = _treaty_inputs(facts)
    # DBA-USA Art. 28 LOB gate (Workstream 4): the upstream
    # TREATY25-LOB-QUALIFICATION stage already raised when the taxpayer
    # claimed re-sourcing without qualifying. Touch the input here so
    # the executor records the dependency for invariant I7.
    _ = facts["treaty.lob_qualified"]
    split = facts["treaty.dividend_split"]
    ordinary = Decimal(str(split["ordinary_dividends_usd"]))
    qualified = Decimal(str(split["qualified_dividends_usd"]))
    foreign_passive = Decimal(str(split["foreign_source_passive_dividends_usd"]))
    foreign_qualified = Decimal(str(split["foreign_source_qualified_dividends_usd"]))

    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.us_source_dividends": ZERO_USD,
            "treaty.us_source_qualified_dividends": ZERO_USD,
        }

    validate_treaty_resourcing_inputs_2025(
        ordinary_dividends_usd=ordinary,
        qualified_dividends_usd=qualified,
        foreign_source_passive_dividends_usd=foreign_passive,
        foreign_source_qualified_dividends_usd=foreign_qualified,
        treaty_inputs=treaty_inputs,
    )
    us_source_dividends = round_cents(ordinary - foreign_passive)
    us_source_qualified_dividends = round_cents(qualified - foreign_qualified)
    validate_treaty_resourcing_dividend_split_2025(
        computed_us_source_dividends_usd=us_source_dividends,
        treaty_inputs=treaty_inputs,
    )
    return {
        "treaty.us_source_dividends": us_source_dividends,
        "treaty.us_source_qualified_dividends": us_source_qualified_dividends,
    }


def treaty25_16_average_tax_floor(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 16: U.S. tax on the U.S.-source dividend stack
    # measured at the average regular-tax rate. Per IRS Publication 514,
    # the "Average rate" is regular tax divided by **taxable income**
    # (Form 1040 line 15), NOT adjusted gross income; AGI as the divisor
    # systematically understates the rate because AGI > taxable income
    # whenever a deduction (standard or itemized) applies. F-FN-2 in the
    # 2026-05-01 per-function review documents the prior AGI denominator
    # as a low-bias drift; this implementation uses taxable income to
    # conform to the worksheet.
    # Pub. 514 worksheet line 17: treaty-allowed source-country tax (15 % rate
    # under DBA-USA Art. 10 paragraph 2(b)).
    # Pub. 514 worksheet line 18: U.S. tax above the treaty floor (max of
    # 0 and line 16 minus line 17). Line 19 (computed in TREATY25-17) further
    # clips this by the German residence credit when that credit exceeds the
    # 15 % floor.
    # https://www.irs.gov/publications/p514
    treaty_inputs = _treaty_inputs(facts)
    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.us_tax_on_us_source_dividends": ZERO_USD,
            "treaty.treaty_minimum_us_tax_at_source": ZERO_USD,
            "treaty.us_limitation_above_15_percent_floor": ZERO_USD,
        }

    us_source_dividends = Decimal(str(facts["treaty.us_source_dividends"]))
    regular_tax_before_credits = Decimal(str(facts["us.stage.regular_tax_before_credits"]))
    taxable_income = Decimal(str(facts["us.stage.taxable_income"]))
    treaty_dividend_rate = Decimal(str(facts["us.constants.treaty_dividend_rate"]))

    if taxable_income <= ZERO_USD:
        raise ValueError("us.stage.taxable_income must be positive for the Pub. 514 average-rate worksheet")

    us_tax_average_rate = regular_tax_before_credits / taxable_income
    us_tax_on_us_source_dividends = round_cents(us_tax_average_rate * us_source_dividends)
    treaty_minimum_us_tax_at_source = round_cents(us_source_dividends * treaty_dividend_rate)
    validate_germany_treaty_dividend_coverage_2025(
        us_source_dividends_usd=us_source_dividends,
        treaty_allowed_us_tax_at_source_usd=treaty_minimum_us_tax_at_source,
        treaty_inputs=treaty_inputs,
    )
    us_limitation_above_15_percent_floor = round_cents(
        max(ZERO_USD, us_tax_on_us_source_dividends - treaty_minimum_us_tax_at_source)
    )
    return {
        "treaty.us_tax_on_us_source_dividends": us_tax_on_us_source_dividends,
        "treaty.treaty_minimum_us_tax_at_source": treaty_minimum_us_tax_at_source,
        "treaty.us_limitation_above_15_percent_floor": us_limitation_above_15_percent_floor,
    }


def treaty25_17_german_residual_cap(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 19 (re-derived): max of 0 and line 16 minus the
    # greater of (line 17 treaty floor, the German residence credit on the same
    # U.S.-source dividend stack). When the residence credit exceeds the 15 %
    # floor, line 19 < line 18; line 21 (TREATY25-18) uses line 19, not line 18.
    # Pub. 514 worksheet line 20c: max of 0 and Germany's pre-credit residence
    # tax on the same dividends minus the same greater-of clamp. Caps the
    # additional credit by residual residence-country tax under DBA-USA Art. 23.
    treaty_inputs = _treaty_inputs(facts)
    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.worksheet_line_19_maximum_credit": ZERO_USD,
            "treaty.german_residual_cap": ZERO_USD,
            "treaty.german_precredit_tax_on_us_source_dividends": ZERO_USD,
            "treaty.german_residence_credit_for_us_tax": ZERO_USD,
        }

    us_tax_on_us_source_dividends = Decimal(str(facts["treaty.us_tax_on_us_source_dividends"]))
    treaty_minimum_us_tax_at_source = Decimal(str(facts["treaty.treaty_minimum_us_tax_at_source"]))
    germany = facts["de.treaty.us_source_dividend_tax_and_credit"]
    # Per CLAUDE.md "never silently default to zero": when treaty re-sourcing is
    # enabled (gated above), the upstream U.S. core validator
    # (``us_2025_law._validate_treaty_dividend_coverage``) already raises
    # ValueError if either German precredit tax or residence credit is None,
    # and the producer in ``treaty_initial_facts_2025`` always populates both
    # sub-dict keys. Subscripting (rather than ``.get(..., ZERO_USD)``) ensures
    # any future producer-contract violation surfaces as a KeyError under
    # invariant I4 instead of silently denying the additional FTC (review H5).
    german_precredit = round_cents(
        Decimal(str(germany["german_precredit_tax_on_us_source_dividends_usd"]))
    )
    residence_credit = round_cents(
        Decimal(str(germany["german_residence_credit_for_us_tax_usd"]))
    )
    floor_or_residence = max(treaty_minimum_us_tax_at_source, residence_credit)
    worksheet_line_19 = round_cents(
        max(ZERO_USD, us_tax_on_us_source_dividends - floor_or_residence)
    )
    worksheet_line_20c = round_cents(
        max(ZERO_USD, german_precredit - floor_or_residence)
    )
    return {
        "treaty.worksheet_line_19_maximum_credit": worksheet_line_19,
        "treaty.german_residual_cap": worksheet_line_20c,
        "treaty.german_precredit_tax_on_us_source_dividends": german_precredit,
        "treaty.german_residence_credit_for_us_tax": residence_credit,
    }


def treaty25_18_additional_ftc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Pub. 514 worksheet line 21: lesser of line 19 (U.S.-tax-above-clamp) and
    # line 20c (residual German residence-country tax). The additional credit
    # carried to Form 1116 line 12 / Part IV line 32 is line 21 further capped
    # by the remaining Form 1116 line-33 nonrefundable-credit ceiling, so the
    # treaty add-on never exceeds U.S. regular tax after the baseline FTC.
    treaty_inputs = _treaty_inputs(facts)
    regular_tax_after_ftc = round_cents(
        Decimal(str(facts["us.stage.regular_tax_after_ftc"]))
    )
    if not treaty_inputs.use_treaty_resourcing:
        return {
            "treaty.worksheet_line_21_additional_credit": ZERO_USD,
            "treaty.additional_foreign_tax_credit": ZERO_USD,
            "treaty.regular_tax_after_ftc_and_treaty_resourcing": regular_tax_after_ftc,
            # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): the
            # § 904(d)(6) treaty-resourced basket has no prior-year
            # carryover (the basket is created annually by treaty
            # election; § 904(c) carryovers do not cross treaty-basket
            # boundaries). Surface as a declared rule output bound to
            # Form 1116 Resourced Line 10 so the renderer write
            # transits the I3 contract instead of a literal Decimal in
            # the form module.
            "treaty.resourced_basket_carryover": ZERO_USD,
        }

    line_19 = Decimal(str(facts["treaty.worksheet_line_19_maximum_credit"]))
    line_20c = Decimal(str(facts["treaty.german_residual_cap"]))
    remaining_line_33_cap = round_cents(
        Decimal(str(facts["us.stage.remaining_form_1116_line_33_cap"]))
    )
    if remaining_line_33_cap < ZERO_USD:
        raise ValueError("us.stage.remaining_form_1116_line_33_cap must be non-negative")
    worksheet_line_21 = round_cents(min(line_19, line_20c))
    additional_credit = round_cents(min(worksheet_line_21, remaining_line_33_cap))
    return {
        "treaty.worksheet_line_21_additional_credit": worksheet_line_21,
        "treaty.additional_foreign_tax_credit": additional_credit,
        "treaty.regular_tax_after_ftc_and_treaty_resourcing": round_cents(
            regular_tax_after_ftc - additional_credit
        ),
        # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): see comment
        # above. Constant 0.00 by treaty design — the § 904(d)(6)
        # basket is created annually and has no carryover.
        "treaty.resourced_basket_carryover": ZERO_USD,
    }


_RULE_FUNCTIONS = {
    "TREATY25-LOB-QUALIFICATION": treaty25_lob_qualification,
    "TREATY25-15-US-SOURCE-DIVIDENDS": treaty25_15_us_source_dividends,
    "TREATY25-16-AVERAGE-TAX-FLOOR": treaty25_16_average_tax_floor,
    "TREATY25-17-GERMAN-RESIDUAL-CAP": treaty25_17_german_residual_cap,
    "TREATY25-18-ADDITIONAL-FTC": treaty25_18_additional_ftc,
}


def treaty_law_rules_2025() -> tuple[LawRule, ...]:
    stages = treaty_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(f"No treaty calculate function registered for {stage.stage_id}")
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def treaty_initial_facts_2025(
    *,
    treaty_inputs: USTreatyInputs2025,
    ordinary_dividends_usd: Decimal,
    qualified_dividends_usd: Decimal,
    foreign_source_passive_dividends_usd: Decimal,
    foreign_source_qualified_dividends_usd: Decimal,
    regular_tax_before_credits_usd: Decimal,
    taxable_income_usd: Decimal,
    regular_tax_after_ftc_usd: Decimal,
    remaining_form_1116_line_33_cap_usd: Decimal,
) -> dict[str, Any]:
    # F-FN-2: the Pub. 514 worksheet line 16 average-rate denominator is
    # taxable income (Form 1040 line 15), not AGI. The initial-fact key carrying
    # this value into TREATY25-16 is ``us.stage.taxable_income``.
    return {
        "us.treaty.inputs": treaty_inputs,
        "treaty.dividend_split": {
            "ordinary_dividends_usd": ordinary_dividends_usd,
            "qualified_dividends_usd": qualified_dividends_usd,
            "foreign_source_passive_dividends_usd": foreign_source_passive_dividends_usd,
            "foreign_source_qualified_dividends_usd": foreign_source_qualified_dividends_usd,
        },
        "us.stage.regular_tax_before_credits": regular_tax_before_credits_usd,
        "us.stage.taxable_income": taxable_income_usd,
        "us.stage.regular_tax_after_ftc": regular_tax_after_ftc_usd,
        "us.stage.remaining_form_1116_line_33_cap": remaining_form_1116_line_33_cap_usd,
        "us.constants.treaty_dividend_rate": TREATY_DIVIDEND_RATE,
        "de.treaty.us_source_dividend_tax_and_credit": {
            "german_precredit_tax_on_us_source_dividends_usd": (
                treaty_inputs.german_precredit_tax_on_us_source_dividends_usd or ZERO_USD
            ),
            "german_residence_credit_for_us_tax_usd": (
                treaty_inputs.german_residence_credit_for_us_tax_usd or ZERO_USD
            ),
        },
    }


def execute_treaty_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        treaty_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    # Stash for in-memory hand-off to the narrative packet builder. The
    # narrative graph nodes must reference the *same* StageResult tuple that
    # produced the legal values; without this, the packet builder would either
    # replay (the C1 anti-pattern) or re-run the graph and risk drift if any
    # input fact were derived rather than stashed. ``run_year`` clears this
    # context at the start of each pipeline run.
    set_pipeline_context_value(TREATY_EXECUTION_CONTEXT_KEY, execution)
    return execution


def treaty_assessment_from_final_facts(
    final_facts: Mapping[str, Any],
    *,
    regular_tax_after_ftc_usd: Decimal,
) -> USTreatyResourcingAssessment2025:
    """Project the executed final_facts into the legacy view dataclass.

    Phase 1 of the engine restructure preserves
    ``USTreatyResourcingAssessment2025`` as a typed view so that existing
    form renderers, trace writers, and golden tests continue to work
    unchanged. The dataclass is no longer *produced* by a monolithic
    compute path; it is *projected* here from the rule graph's outputs.
    """
    def fact(key: str) -> Decimal:
        return Decimal(str(final_facts[key]))

    additional = fact("treaty.additional_foreign_tax_credit")
    return USTreatyResourcingAssessment2025(
        us_source_dividends_usd=fact("treaty.us_source_dividends"),
        us_source_qualified_dividends_usd=fact("treaty.us_source_qualified_dividends"),
        us_tax_on_us_source_dividends_usd=fact("treaty.us_tax_on_us_source_dividends"),
        treaty_minimum_us_tax_on_us_source_dividends_usd=fact("treaty.treaty_minimum_us_tax_at_source"),
        treaty_resourcing_us_limitation_usd=fact("treaty.us_limitation_above_15_percent_floor"),
        german_precredit_tax_on_us_source_dividends_usd=fact("treaty.german_precredit_tax_on_us_source_dividends"),
        german_residence_credit_for_us_tax_usd=fact("treaty.german_residence_credit_for_us_tax"),
        worksheet_line_19_maximum_credit_usd=fact("treaty.worksheet_line_19_maximum_credit"),
        worksheet_line_20c_residual_residence_country_tax_usd=fact("treaty.german_residual_cap"),
        worksheet_line_21_additional_credit_usd=fact("treaty.worksheet_line_21_additional_credit"),
        treaty_resourcing_additional_ftc_usd=additional,
        # Pub. 514 documents line 20c as the residual residence-country tax;
        # the legacy dataclass exposes the same value under a second name for
        # backward compatibility with downstream renderers.
        german_residual_tax_on_us_source_dividends_usd=fact("treaty.german_residual_cap"),
        regular_tax_after_ftc_and_treaty_resourcing_usd=fact("treaty.regular_tax_after_ftc_and_treaty_resourcing"),
        # C7-audit (FORM-MAPPING-FOLLOWUP, 2026-05-04): always 0.00 by
        # treaty design — surface as a declared rule output for I3.
        resourced_basket_carryover_usd=fact("treaty.resourced_basket_carryover"),
    )


def treaty_initial_fingerprints_2025(initial_facts: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


__all__ = [
    "TREATY_EXECUTION_CONTEXT_KEY",
    "execute_treaty_rule_graph",
    "treaty_assessment_from_final_facts",
    "treaty_initial_facts_2025",
    "treaty_initial_fingerprints_2025",
    "treaty_law_rules_2025",
    "treaty25_15_us_source_dividends",
    "treaty25_16_average_tax_floor",
    "treaty25_17_german_residual_cap",
    "treaty25_18_additional_ftc",
]
