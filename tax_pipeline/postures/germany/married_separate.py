from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="germany",
    filing_posture="married_separate",
    module_path=__name__,
    required_household_shape="married",
    # § 26a Abs. 2 EStG separate-assessment allocation elections are not modeled yet.
    # Keep every public surface marked unsupported instead of advertising partial ordinary-law support.
    output_support=OutputSurfaceSupport(ordinary_law=False, forms=False, entry_sheet=False),
    legal_rule_keys=(
        "estg_26a_separate_assessment",
        "estg_26a_expense_and_credit_allocation_elections_unimplemented",
        "estg_32a_basic_tariff_per_spouse",
    ),
    implemented=True,
)
