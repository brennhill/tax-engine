from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="germany",
    filing_posture="married_joint",
    module_path=__name__,
    required_household_shape="married",
    output_support=OutputSurfaceSupport(ordinary_law=True, forms=True, entry_sheet=True),
    legal_rule_keys=(
        "estg_26_joint_assessment_election",
        "estg_26b_joint_aggregation",
        "estg_32a_splitting_tariff",
        "estg_20_32d_joint_capital_assessment",
        "estg_36_credit_and_refund_order",
    ),
    implemented=True,
)
