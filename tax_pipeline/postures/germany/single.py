from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="germany",
    filing_posture="single",
    module_path=__name__,
    required_household_shape="single",
    output_support=OutputSurfaceSupport(ordinary_law=True, forms=True, entry_sheet=True),
    legal_rule_keys=(
        "estg_2_taxable_income_order",
        "estg_32a_basic_tariff",
        "estg_20_32d_capital_assessment",
        "estg_36_credit_and_refund_order",
    ),
    implemented=True,
)
