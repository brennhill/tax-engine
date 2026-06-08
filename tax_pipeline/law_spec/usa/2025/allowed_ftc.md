# U.S. 2025 Allowed Foreign Tax Credit

## Authority

- `26 U.S.C. § 901`
- `26 U.S.C. § 904`
- Instructions for Form `1116`
- IRS Publication `514`
- Official URLs:
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
  - https://www.irs.gov/instructions/i1116
  - https://www.irs.gov/publications/p514

## What This Rule Governs

The allowed FTC in each basket after applying the basket limitation.

For the treaty-resourcing scenario, the final nonrefundable FTC also includes the Publication 514 additional-credit worksheet amount after the base Form 1116 basket credits.

## Inputs

- basket limitation
- current-year foreign tax
- carryover

## Formula

`allowed credit = min(limitation, current-year foreign tax + carryover)`

## Ordering

This applies after the basket limitations are computed.

The `total_allowed_ftc_after_treaty_resourcing` trace step applies after the base allowed general/passive credits and after the treaty-resourcing worksheet has computed its additional credit.

## Rounding

- cents are preserved

## Edge Cases

- zero limitation
- zero foreign tax
- carryover larger than the limitation

## Ambiguities / Filing Positions

The allowed-credit formula is mechanical.

The current model's general-basket current-year foreign tax still depends on a separate wage-share allocation position.

## Implemented By

- `tax_pipeline/y2025/us_law.py:allowed_ftc_2025`
- `tax_pipeline/y2025/us_law.py:compute_ftc_assessment_2025`

## Test Coverage

- `tests/test_us_2025_law.py`

## Outputs Affected

- `allowed_general_ftc`
- `allowed_passive_ftc`
- `total_allowed_ftc_after_treaty_resourcing`
