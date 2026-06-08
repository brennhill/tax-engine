from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="usa",
    filing_posture="single",
    module_path=__name__,
    required_household_shape="single",
    output_support=OutputSurfaceSupport(ordinary_law=True, forms=True, entry_sheet=True),
    legal_rule_keys=(
        "irc_1_single_rate_schedule",
        "irc_63_single_standard_deduction",
        "irc_1211b_standard_capital_loss_limit",
        "irc_1411_single_niit_threshold",
        "irc_901_904_ftc_limitation",
    ),
    implemented=True,
)
