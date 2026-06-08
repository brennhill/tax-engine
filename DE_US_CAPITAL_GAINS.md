# Germany / U.S. Capital Gains, Dividends, And Treaty Math

This note has two jobs:

1. explain the Germany/U.S. cross-border capital-income picture in plain English
2. explain how this repo's current `2025` engine models the math

It is aimed at the main repo use case:

- a taxpayer with Germany and U.S. filing obligations
- German residence-country treatment on the Germany side
- U.S. capital income from U.S. brokers
- dividends, stock sales, and fund / ETF income

It is **not** a full treatise on every treaty article or every capital-income edge case. It is a map of the legal terrain and of this engine's current implementation boundary.

## Plain-English Treaty Overview

For the repo's main cross-border case, the big picture is:

- Germany is the residence country for the modeled filing
- the U.S. still taxes the U.S. return because U.S. citizens and U.S. taxpayers remain inside the U.S. tax system
- the Germany/U.S. treaty helps coordinate who gets to tax certain items and how double taxation is relieved

The most important practical point for this engine is:

- the treaty is **not** modeled here as a blanket override for all capital gains
- the current treaty-sensitive math is primarily about **dividends**
- the current U.S. treaty re-sourcing path is a limited modeled path for certain U.S.-source dividends, not a universal rule for all stock gains

So if you are asking, "Does the treaty just solve all Germany/U.S. capital overlap?" the answer is **no**. The engine treats dividends and capital gains differently, and it also distinguishes between:

- baseline domestic-law tax math
- foreign tax credit math
- treaty re-sourcing math
- explicit treaty-position inputs that are not yet fully mechanical

## Country-By-Country Legal Overview

### U.S. Side

For the current engine, the U.S. side works like this:

- **Ordinary dividends** are taxable as dividend income.
- **Qualified dividends** still show up as dividends, but they can get the lower `§ 1(h)` rate schedule instead of ordinary-bracket treatment.
- **Short-term capital gains** are treated like ordinary income for tax-rate purposes.
- **Long-term capital gains** get the long-term capital-gain rate structure.
- **Stock and ETF / fund sale gains** usually both land in the capital-gain netting system, but the U.S. still cares about short-term versus long-term holding period.
- **Capital gain distributions** from funds are their own capital-income input on the U.S. side.

In other words, on the U.S. return the primary distinction is usually:

- short-term vs long-term

not:

- stock vs ETF

That said, the current treaty worksheet modeling in this repo **does** separately track some dividend categories for treaty-cap and residual-rate assumptions:

- direct-equity dividends
- equity-fund dividends
- non-equity-fund dividends

That category split is part of the repo's treaty-position modeling, not the baseline Schedule D capital-netting logic.

### Germany Side

For the current engine, the Germany side works differently:

- the engine does **not** use the U.S.-style short-term / long-term split for normal securities
- dividends, stock sales, and fund income generally live inside the capital-income regime
- Germany then applies its own capital-tax rules, including:
  - capital tax rate mechanics
  - solidarity surcharge
  - foreign-tax credit ordering
  - fund rules such as `Teilfreistellung`

The important Germany distinctions in this repo are closer to:

- stock-sale gains and stock-sale loss carryforwards
- equity funds versus other investment funds
- dividends versus sale gains

not:

- short-term vs long-term

So a U.S. taxpayer may naturally think in short-term / long-term terms, while the Germany side of this repo thinks more in:

- stock bucket
- fund bucket
- dividend bucket

## Loss Behavior By Bucket

The table below is intentionally practical rather than academic. It describes the main behavior that matters for this repo.

| Bucket | Plain-English treatment | Current engine behavior |
| --- | --- | --- |
| U.S. short-term gains / losses | Netted in the short-term capital bucket. Short-term net gain is effectively taxed at ordinary rates. | Mechanical in `capital_gain_netting` and then fed into the regular U.S. tax model. |
| U.S. long-term gains / losses | Netted in the long-term capital bucket and then taxed under the lower long-term / `§ 1(h)` structure. | Mechanical in `capital_gain_netting`. |
| U.S. overall capital loss | After short-term and long-term netting, an overall net loss is not always fully deductible in the current year. | Engine applies the annual capital-loss cap for the current filing posture, then carries the remainder conceptually as carryforward input. |
| U.S. stock vs ETF sale losses | Usually both are still capital losses; the U.S. mainly cares about short-term versus long-term. | Engine mostly cares about short-term vs long-term buckets, not a separate stock-versus-ETF loss cage. |
| U.S. dividends | Dividends are not a capital-loss bucket. You do not "net dividend losses" the same way as capital-sale losses. | Ordinary and qualified dividends are modeled separately; no dividend-loss bucket exists. |
| Germany stock-sale losses | Germany can restrict stock-sale losses more narrowly than general capital losses. | Engine treats stock-loss carryforwards as a special bucket that offsets stock-sale gains only. |
| Germany ETF / fund sale losses | Fund treatment depends on the German investment-fund rules, not the U.S. Schedule D structure. | Engine separates equity-fund and other-fund treatment, including `Teilfreistellung` where relevant. |
| Germany dividends | Dividends are capital income, but they do not create a parallel "dividend loss carryforward" concept like a capital-sale loss bucket. | Engine taxes them as part of the capital-income model; treaty-sensitive dividend credit remains partly manual-position-driven. |

## The Most Important Cross-Border Difference

The single biggest source of confusion is:

- **U.S. capital math is mainly organized around short-term vs long-term**
- **Germany capital math in this repo is mainly organized around stock / fund / dividend bucket behavior**

That means the same real-world broker activity can look different in the two countries:

- a short-term stock gain matters a lot on the U.S. side because it affects rate treatment
- the Germany side may care more about whether it is a stock, an equity fund, another fund, or a dividend stream

## How The Engine Models The U.S. Math

### 1. Capital Gain Netting

The current U.S. workpaper builds:

- short-term buckets
- long-term buckets
- Section `1256` `40/60` split where relevant
- final net capital result for Form `1040` line `7a`

In the current repo, this is mechanical once basis and source facts are fixed.

Relevant rule doc:

- [tax_pipeline/law_spec/usa/2025/capital_gain_netting.md](tax_pipeline/law_spec/usa/2025/capital_gain_netting.md)

Relevant implementation:

- `tax_pipeline/us_2025_law.py:section_1256_split_2025`
- `tax_pipeline/us_2025_law.py:compute_capital_assessment_2025`

### 2. Qualified Dividends

The engine does **not** just tax all dividends the same way.

It distinguishes:

- ordinary dividends
- qualified dividends

Qualified dividends are then run through the reduced-rate ordering logic under `26 U.S.C. § 1(h)`.

Relevant rule doc:

- [tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md](tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md)

Relevant implementation:

- `tax_pipeline/us_2025_law.py:regular_tax_2025_mfs`

### 3. FTC Limitation

The U.S. side computes baseline FTCs before any treaty re-sourcing add-on.

That means the engine first determines:

- passive-basket limitation
- general-category limitation
- allowed FTC under the repo's explicit filing positions

This is important because treaty re-sourcing is layered on top of already-computed domestic tax and FTC results, not used as a shortcut around them.

### 4. Treaty Re-Sourcing

The current treaty-sensitive U.S. math is focused on certain **U.S.-source dividends**.

The implemented logic is:

1. isolate the U.S.-source dividend stack
2. compute the regular U.S. tax attributable to that stack
3. compute the treaty's allowed source-country floor
4. compute the excess U.S. tax above that floor
5. cap the additional credit using the residence-country residual-tax worksheet logic

This is one of the key points where the engine is partly:

- **mechanical in arithmetic**
- **manual in tax-position inputs**

because the engine still depends on explicit assumptions for:

- U.S.-source dividend splits by category
- Germany residual tax rates on those categories
- the residence-country credit cap posture

Relevant rule doc:

- [tax_pipeline/law_spec/usa/2025/treaty_resourcing.md](tax_pipeline/law_spec/usa/2025/treaty_resourcing.md)

Relevant implementation:

- `tax_pipeline/us_2025_law.py:validate_treaty_resourcing_dividend_split_2025`
- `tax_pipeline/us_2025_law.py:validate_treaty_resourcing_inputs_2025`
- `tax_pipeline/us_2025_law.py:compute_treaty_resourcing_assessment_2025`

## How The Engine Models The Germany Math

### 1. Capital Buckets

The Germany side starts from capital-income buckets and fund treatment rather than the U.S. short-term / long-term structure.

The current engine distinguishes:

- stock sales
- equity funds
- other funds
- dividends
- explicit foreign tax
- treaty-position credit

### 2. Stock-Loss Carryforwards

The current engine treats Germany stock-loss carryforwards as a special, narrower bucket.

Practically, that means:

- prior stock-sale losses do **not** behave like a universal offset against every type of positive capital income
- the repo applies them against positive stock-sale gains only

This is one of the major legal differences from the broad U.S. short-term / long-term netting picture.

### 3. Equity Funds And Other Funds

The engine treats German equity-fund and non-equity-fund results differently where the investment-fund rules matter.

In the current model, this is where `Teilfreistellung` enters the capital-income ordering.

So when users ask, "Why does ETF behavior differ from stock behavior?" the Germany answer is often:

- because funds are living under the investment-fund rules, not just the direct stock-sale rule

### 4. Treaty Dividend Credit On The Germany Side

The Germany side has an important treaty-sensitive surface too, but it is more fragile than the domestic capital ordering.

The current engine:

- computes the domestic capital ordering mechanically
- then applies a separate treaty-position credit
- uses that credit against capital soli first and then remaining capital tax

The **ordering** is mechanical.

The **credit amount itself** is still an explicit tax-position input in the current repo rather than a fully generated treaty worksheet result.

Relevant rule docs:

- [tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md](tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md)
- [tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md](tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md)

Relevant implementation:

- `tax_pipeline/germany_2025_law.py:capital_tax_after_foreign_tax_credit_2025`
- `tax_pipeline/germany_2025_law.py:treaty_relieved_capital_tax_2025`
- `tax_pipeline/pipelines/y2025/germany_model.py`

## Mechanical Versus Manual In This Engine

This distinction matters more than any single formula.

### Mostly Mechanical In The Current Repo

- U.S. short-term / long-term capital netting once facts are fixed
- U.S. qualified-dividend rate ordering
- U.S. annual capital-loss cap application
- Germany capital ordering around:
  - `Teilfreistellung`
  - statutory foreign-tax credit
  - capital solidarity surcharge
  - treaty-credit sequencing

### Still Manual-Position-Driven In The Current Repo

- exact U.S. treaty re-sourcing dividend split assumptions
- Germany residual-tax assumptions feeding the U.S. treaty worksheet
- Germany treaty dividend credit amount itself
- any underlying factual basis or source reconstruction issues that are not purely parser-derived

So the honest summary is:

- the engine's arithmetic is strong once the facts and filing positions are fixed
- the most fragile areas are still treaty-sensitive dividend positions, not ordinary bucket math

## What The Engine Does Not Claim

This repo does **not** claim:

- that every Germany/U.S. capital issue is fully automated
- that treaty treatment for all capital gains is modeled end-to-end
- that short-term gains are treaty-re-sourced here the same way the dividend worksheet is
- that every stock / ETF / dividend edge case across both countries is already covered

And it definitely does not claim:

- that this note is legal advice

This file describes:

- the broad legal picture relevant to the repo
- and the current engine's `2025` implementation choices

## Official / Primary Sources Worth Reading

- U.S.-Germany treaty technical explanation
  - https://www.irs.gov/pub/irs-trty/germtech.pdf
- IRS Publication `514`
  - https://www.irs.gov/publications/p514
- `26 U.S.C. § 1`
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1&num=0&edition=prelim
- `26 U.S.C. § 1211`
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211&num=0&edition=prelim
- `26 U.S.C. § 1212`
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212&num=0&edition=prelim
- `26 U.S.C. § 1256`
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256&num=0&edition=prelim
- `26 U.S.C. § 904`
  - https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904&num=0&edition=prelim
- Germany treaty materials from BMF
  - https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html?gtp=249348_list%253D2
- `§ 32d EStG`
  - https://www.gesetze-im-internet.de/estg/__32d.html
- `InvStG § 20`
  - https://www.gesetze-im-internet.de/invstg_2018/__20.html
- `§ 4 SolzG 1995`
  - https://www.gesetze-im-internet.de/solzg_1995/__4.html
- `§ 5 SolzG 1995`
  - https://www.gesetze-im-internet.de/solzg_1995/__5.html

## Repo Pointers

- [tax_pipeline/law_spec/usa/2025/index.md](tax_pipeline/law_spec/usa/2025/index.md)
- [tax_pipeline/law_spec/usa/2025/capital_gain_netting.md](tax_pipeline/law_spec/usa/2025/capital_gain_netting.md)
- [tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md](tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md)
- [tax_pipeline/law_spec/usa/2025/treaty_resourcing.md](tax_pipeline/law_spec/usa/2025/treaty_resourcing.md)
- [tax_pipeline/law_spec/germany/2025/index.md](tax_pipeline/law_spec/germany/2025/index.md)
- [tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md](tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md)
- [tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md](tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md)
