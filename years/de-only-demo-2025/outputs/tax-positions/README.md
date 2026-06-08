# tax-positions

This folder holds year-specific tax-layer results and intermediate tax positions.

Tax-position names may be jurisdiction-specific and law-loaded.

Examples:
- Germany `Anlage KAP` lines
- U.S. `Form 1116` positions
- treaty re-sourcing allocations

Do not move these names up into shared facts or shared derived facts.

Examples:
- prior-year carryovers consumed as current-year tax inputs
- treaty-supporting allocation outputs
- line-mapped filing positions
- model-level assumptions that belong in the tax layer rather than raw or derived facts
