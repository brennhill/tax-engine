# DE_US_CAPITAL_GAINS Design

## Goal

Add a public-facing explainer file named `DE_US_CAPITAL_GAINS.md` that does two things in one place:

1. gives a plain-English legal overview of Germany/U.S. cross-border capital-income treatment for the repo's main use case
2. explains how this engine currently models that law and computes the math

The focus is:

- treaty treatment of dividends
- short-term and long-term gains
- differences between stocks, ETFs / funds, and dividends
- loss behavior by bucket
- what is mechanical in the engine versus what still depends on explicit manual tax positions

## File To Add

- `DE_US_CAPITAL_GAINS.md`

## Audience

- human users trying to understand the cross-border capital logic
- contributors trying to understand the repo's current treaty and loss-bucket modeling
- future reviewers comparing engine math to the repo's stated interpretation

## Required Sections

### 1. Purpose And Scope

State clearly that the note is:

- a Germany/U.S. cross-border capital-income explainer
- focused on the current `2025` engine
- not a generic all-cases treaty treatise

### 2. Plain-English Treaty Overview

Explain in plain English:

- why the U.S. still taxes U.S. citizens / taxpayers even when Germany is the residence country in the modeled case
- why treaty relief in this repo is primarily relevant to certain dividend interactions rather than all capital gains
- that the repo's treaty re-sourcing path is a limited modeled path, not a universal capital-gain override

### 3. Country-By-Country Legal Overview

Split into:

- U.S. side
- Germany side

Cover:

- dividends
- short-term gains
- long-term gains
- stocks
- ETFs / investment funds

### 4. Loss Behavior By Bucket

Include a comparison table covering at least:

- U.S. short-term losses
- U.S. long-term losses
- U.S. stocks
- U.S. ETFs / funds
- U.S. dividends
- Germany stock-sale losses
- Germany ETF / fund treatment
- Germany dividends

The table should emphasize:

- what can offset what
- annual limits where relevant
- where losses are bucket-restricted
- where dividends do not create a parallel "loss bucket" concept

### 5. How The Engine Models The Math

Describe the current repo implementation for:

- U.S. capital netting
- qualified-dividend treatment
- FTC limitation
- treaty re-sourcing worksheet logic
- Germany capital buckets
- Germany stock-loss carryforward treatment
- equity-fund versus other-fund treatment
- Germany treaty dividend credit

This section must distinguish:

- mechanical calculations
- manual tax-position inputs

### 6. What The Engine Does Not Claim

State boundaries explicitly:

- not all treaty outcomes are fully mechanical
- not every possible capital-gain scenario is modeled
- this is a `2025` engine
- the file describes this repo's interpretation and implementation boundary, not legal advice

### 7. Repo Pointers

Link to the relevant law-spec files and key engine files.

Minimum intended links:

- `tax_pipeline/law_spec/usa/2025/treaty_resourcing.md`
- `tax_pipeline/law_spec/usa/2025/capital_gain_netting.md`
- `tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md`
- `tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md`
- `tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md`

## Source Expectations

Prefer primary or official sources where possible:

- treaty technical explanation
- IRS publications/instructions where the repo already relies on them
- U.S. Code / official IRS materials
- German statutory sources / official BMF materials already used in the repo

The document should avoid overstating certainty where the engine still uses explicit assumptions.

## Tone

The note should be:

- plain English first
- technically precise
- explicit about where the repo's math is a model of the law rather than an oracle of absolute truth

## Non-Goals

Do not:

- try to document every IRS or German tax edge case
- claim universal treaty treatment for all capital gains
- blur the line between legal overview and engine-specific modeling
