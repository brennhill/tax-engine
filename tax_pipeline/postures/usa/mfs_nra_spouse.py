from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="usa",
    filing_posture="mfs_nra_spouse",
    module_path=__name__,
    required_household_shape="married",
    output_support=OutputSurfaceSupport(ordinary_law=True, forms=True, entry_sheet=True),
    legal_rule_keys=(
        "irc_1_mfs_rate_schedule",
        "irc_63_mfs_standard_deduction",
        "irc_1211b_mfs_capital_loss_limit",
        "irc_1411_mfs_niit_threshold",
        "nra_spouse_not_on_return",
        "irc_901_904_ftc_limitation",
    ),
    implemented=True,
)
