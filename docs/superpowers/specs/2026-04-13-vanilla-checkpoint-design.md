# Vanilla Checkpoint Design

## Goal

Add one low-blast-radius "vanilla checkpoint" output for Germany and one for the U.S. so commercial tax software can be used to validate the core wage-only tax math independently from treaty, capital, crypto, and discretionary-deduction logic.

## Why

The current final results combine:

- wage income
- capital income
- treaty positions
- FTC logic
- crypto logic
- discretionary deductions

That makes it hard to isolate whether the basic wage-side tax engine is correct. A checkpoint that keeps only wage income and default deductions lets the user compare the result against mainstream software with minimal interpretation risk.

## Non-goals

- Do not replace the full filing outputs.
- Do not create a second full tax engine.
- Do not create multiple checkpoint variants yet.
- Do not add treaty logic to the checkpoint.
- Do not include discretionary deductions such as home office or work equipment.

## Checkpoint definition

The checkpoint means:

- include wage income only
- include normal default deductions and filing-status defaults for the jurisdiction
- include actual wage withholding and prepayments / estimated payments
- exclude all non-wage income
- exclude all discretionary or judgment-based deductions
- exclude treaty effects
- exclude FTC effects
- exclude investment, crypto, and equity-comp effects except to the extent they are already embedded in wage documents

## Germany checkpoint

The Germany checkpoint should include:

- employment income from the wage certificates
- statutory/default wage-side deductions and contribution treatment already required by law
- joint filing posture and ordinary tariff
- wage tax and wage solidarity surcharge withheld
- the documented `5,000 EUR` prepayment

The Germany checkpoint should exclude:

- all `Anlage KAP` and `KAP-INV` effects
- treaty dividend credit
- `§ 22 Nr. 3` staking income
- `§ 23` private-sale effects
- home office
- work equipment
- any other manual deduction positions

## U.S. checkpoint

The U.S. checkpoint should include:

- wage income only
- the existing filing posture (`MFS` with NRA spouse not included on the return)
- the 2025 standard deduction
- the documented `2,000 USD` estimated payment

The U.S. checkpoint should exclude:

- dividends
- interest
- capital gains and losses
- Schedule 1 other income
- NIIT
- FTC
- treaty re-sourcing
- any non-wage manual filing positions

## Data shape

Each country should expose one structured `vanilla_checkpoint` block in the canonical result JSON.

Germany fields:

- `taxable_income_eur`
- `income_tax_eur`
- `soli_eur`
- `total_tax_eur`
- `refund_or_balance_due_eur`

U.S. fields:

- `adjusted_gross_income_usd`
- `taxable_income_usd`
- `regular_tax_usd`
- `total_tax_usd`
- `refund_or_balance_due_usd`

## Output surfaces

The checkpoint should appear in:

- the canonical results JSON for each country
- the summary Markdown for each country
- the `run_year` stdout headline summary

The summary Markdown should add a clearly labeled section:

- `Vanilla checkpoint for commercial software comparison`

## Architecture

The checkpoint must be computed from the same law-core inputs and pure functions as the main model.

That means:

- no ad hoc arithmetic in the summary renderer
- no duplicate shadow logic in `run_year`
- no separate manual worksheet outside the legal engine

The country model should derive the checkpoint as a narrow alternate scenario from the same structured inputs and then render it into the existing output surfaces.

## Testing

Add tests that verify:

- the new JSON fields exist
- the summary Markdown renders the checkpoint section
- the stdout summary includes the checkpoint values
- the checkpoint excludes treaty-sensitive and discretionary items
- the checkpoint remains stable across reruns

## Success criteria

The user should be able to:

1. run `python3 -m tax_pipeline.run_year 2025`
2. read one vanilla checkpoint number for Germany and one for the U.S.
3. reproduce those same simplified results in commercial software using wage-only assumptions
4. use any mismatch to narrow the problem to the core wage-side logic instead of the treaty/capital layers
