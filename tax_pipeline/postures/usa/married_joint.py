from __future__ import annotations

from tax_pipeline.postures.base import OutputSurfaceSupport, PostureDefinition


DEFINITION = PostureDefinition(
    jurisdiction="usa",
    filing_posture="married_joint",
    module_path=__name__,
    required_household_shape="married",
    output_support=OutputSurfaceSupport(ordinary_law=True, forms=True, entry_sheet=True),
    legal_rule_keys=(
        "irc_1_mfj_rate_schedule",
        "irc_63_mfj_standard_deduction",
        "irc_1211b_standard_capital_loss_limit",
        "irc_1411_mfj_or_nra_election_niit_threshold",
        "irc_6013g_nra_spouse_joint_election",
        "irc_901_904_ftc_limitation",
    ),
    implemented=True,
)
