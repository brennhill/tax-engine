# Intake Wizard / Workspace UI Coverage TODO

A real-return setup with the current engine surfaced ~15 manual configuration
steps that the user must perform by hand (editing JSON / CSV files, renaming
PDFs, classifying funds, populating treaty packets, etc.). This document
catalogs every step encountered so they can be folded into the local intake
wizard or a follow-up automation layer.

Each item lists:
- the engine-side error or fail-closed gate that surfaces today
- the file the user has to edit
- what the wizard should do instead

Authority for every "fail closed" gate is documented in
[docs/law-coverage.md](law-coverage.md).

---

## A. Profile-level elections (currently: edit `config/profile.json` by hand)

### A1. § 51a EStG Kirchensteuer membership
- Engine error: `Missing required elections.germany_kirchensteuer_membership in profile.json (§ 51a EStG)`
- Wizard should: present a dropdown — None / EVK / RKK / Freikirche / Other — with help text linking to https://www.gesetze-im-internet.de/estg/__51a.html. Selecting anything other than "None" warns that Kirchensteuer is not yet modeled and will fail closed.

### A2. 26 U.S.C. § 911 Foreign Earned Income Exclusion
- Engine error: `Missing required U.S. § 911 Foreign Earned Income Exclusion election`
- Wizard should: present a checkbox "Elect § 911 Foreign Earned Income Exclusion?" with help text and a clear warning that election currently fails closed.

### A3. U.S.-Germany Totalization Agreement acknowledgment for § 3101
- Engine error: `Missing required ... acknowledges_totalization_agreement_germany_us`
- Wizard should: render a single yes/no question — "Are all your wages from a German employer (covered by the U.S.-Germany Totalization Agreement)?" — with help text. False or unset fails closed.

### A4. § 32d Abs. 6 Günstigerprüfung
- Engine error: `Germany § 32d Abs. 6 Günstigerprüfung posture is required for capital income`
- Wizard should: when user has capital income, present a "Compute § 32d Abs. 6 comparison?" toggle. Default off. Setting on currently fails closed (not yet implemented).

### A5. § 6013(g)/(h) NRA spouse joint election
- Engine path: when spouse `us_tax_status="nra"` and US filing posture is `married_joint`, election must be true.
- Wizard should: detect NRA spouse + married_joint US posture and require explicit election with explanation of consequences (worldwide income, retroactive ineffectiveness on revocation).

### A6. `jurisdictions` block & `joint_assessment_prerequisites`
- Engine error: `Germany two-person returns require an explicit jurisdictions.germany.filing_posture` and `Germany married_joint requires german_return.joint_assessment_prerequisites`.
- Wizard should: derive `jurisdictions.{germany,usa}.filing_posture` from the household marital-status + posture answers. For married_joint, present the four § 26 prerequisites as a four-checkbox group with a single "All apply" shortcut.

---

## B. Owner tagging for source documents (currently: rename PDFs by hand)

### B1. Wage certificate owner inference is filename-marker-only
- Engine error: `Missing german_lohnsteuer_pdf facts for owner='person_1'`
- Cause: `tax_pipeline/classify.py:_guess_owner` only recognizes `person_1`, `person-1`, `person 1`, `taxpayer`, `person_2`, `person-2`, `person 2`, `spouse`, `partner` as filename markers. Names ("Brenn", "Lien") are not matched.
- Wizard should: at upload time, ask "which person does this document belong to?" with the household roster as options. Stash the answer in a sidecar metadata file (e.g. `raw/<bucket>/<filename>.owner.txt`) that the classifier reads, OR rename the file with the slot marker prepended — whichever fits the existing parser layer better.

### B2. Re-extraction does not respect manual edits to `*.facts.json`
- Cause: `extract_all_facts` clobbers fact files when the source PDF or the descriptor changes; manual `owner` edits in `*.facts.json` are lost on the next run.
- Wizard should: store overrides in a separate sidecar that the extractor reads and respects, OR provide a "lock this fact file from re-extraction" toggle.

---

## C. Fund classification (currently: edit `manual_overrides.json` by hand)

### C1. InvStG § 2 Abs. 6 fund-type classification per ETF/fund symbol
- Engine error: `Fund classification missing for fund_like symbol IJR.`
- Cause: every `asset_bucket=fund_like` symbol in `income-cashflows.csv` and `capital-sales-detail.csv` must appear in `manual_overrides.json` `fund_classification.aktienfonds` or `non_aktienfonds`. ~25 symbols for an active U.S. brokerage portfolio.
- Wizard should:
  - auto-discover all fund_like symbols across the workspace.
  - propose a default classification for each (most equity ETFs → aktienfonds; bond/precious-metal/preferred → non_aktienfonds).
  - present a per-symbol confirmation table with the proposed classification and a link to the fund's fact sheet.
  - persist user overrides.
- Bonus: integrate a deterministic classification database keyed by ISIN / ticker that the wizard ships with for common ETFs (~200 tickers covers most cases). The user only confirms / overrides edge cases.

---

## D. Per-person income allocations (currently: edit `derived-facts/common/other-income-facts.csv`)

### D1. § 22 Nr. 3 EStG per-person staking allocation for married_joint
- Engine error: `Germany married_joint requires per-spouse § 22 Nr. 3 allocations for nonzero amounts.`
- Wizard should: when other-income (staking, royalties, etc.) is detected, ask "whose account/wallet did this come from?" and write the per-person rows automatically.

---

## E. § 32d Abs. 5 EStG per-Posten foreign-tax tracking (currently: edit `income-cashflows.csv`)

### E1. `kind` value normalization
- Engine error: `Unsupported Germany capital income kind 'dividend_cash' for symbol 'AMZA'`
- Cause: engine only accepts `{dividend, interest, substitute_payment, foreign_tax}`; some upstream extractions use `dividend_cash` / `dividend_reinvested` subtypes.
- Wizard should: normalize at extraction time, OR extend the engine's accepted set to include common subtypes that map 1:1 to `dividend`.

### E2. `refund_entitlement_eur` column on foreign_tax rows
- Engine error: `Germany foreign_tax rows in income-cashflows.csv must include refund_entitlement_eur.`
- Wizard should: ask "did your broker withhold at the treaty rate (typical) or above the treaty rate?" once per foreign-tax row group, and populate the column accordingly. Default = 0 (treaty rate withheld, no NR7 reclaim possible).

### E3. `foreign_tax_item_id` pairing for per-Posten cap
- Engine error: `Germany foreign_tax rows require foreign_tax_item_id when symbol fallback is ambiguous`
- Cause: when the same symbol has multiple foreign_tax rows + multiple dividend rows in a year (e.g. quarterly ENB), § 32d(5) needs explicit pairing.
- Wizard should: auto-pair by date (foreign_tax row + dividend row on the same date) and assign deterministic IDs like `<symbol>_<YYYY_MM_DD>`. Flag unpaired tax rows for user review.

### E5. `income-cashflows.csv` reconciliation to 1099 box 1a
- Engine effect: auto-derivation of treaty packet items reveals when income-cashflows totals more (or less) than Schwab 1099 box 1a, which the engine then rejects via `validate_treaty_resourcing_dividend_split_2025` (us_2025_law.py:489-498).
- Real-return finding (2025-04-30 walk): income-cashflows non-ENB dividend total = USD 12,076.66 vs. 1099 box 1a = USD 9,596.58 (gap USD 2,480). Likely causes:
  - `dividend_reinvested` rows double-count amounts the broker reports as a single net.
  - Box 3 nondividend distributions (USD 475.51) are wrongly classified as `kind=dividend` in some rows.
- Wizard / extraction should: at extraction time, validate the per-row sum reconciles to the 1099 box totals and surface unreconciled items for review (the user picks "this is a reinvestment double-count", "this is Box 3", etc.) instead of letting the discrepancy hide until the treaty cross-check fails three layers downstream.

### E4. Fund-pass-through foreign tax (1099 box 7 vs. itemized rows)
- Engine error: `foreign_tax_1099_eur must reconcile to ... income-cashflows.csv foreign_tax rows + bank-certificate rows`
- Cause: `foreign_tax_1099_eur` is the aggregate from the 1099 (e.g. €44.35); income-cashflows itemizes only direct withholdings (e.g. ENB). The gap is foreign tax paid by international funds (VXUS, VT, etc.) inside the fund and passed through on the 1099 — not directly visible per-dividend.
- Wizard should: auto-extract per-fund foreign-tax detail from the Schwab supplementary statement (`1099 Year-End Tax Summary` lists "foreign source amount" and "foreign tax paid" per fund). Generate one foreign_tax row per fund per year with `foreign_tax_item_id=<symbol>_fund_passthrough_<year>` and pair with the corresponding fund's aggregate dividend row.
- Until this is automated: add a manual-override file `outputs/tax-positions/fund-passthrough-foreign-tax.csv` so the user doesn't have to edit `income-cashflows.csv` directly.

---

## F. Treaty packet items (currently: empty files in `outputs/tax-positions/`)

### F1. `de-us-treaty-dividend-items.csv` and `us-treaty-dividend-items.csv`
- Engine effect: empty files mean no Pub. 514 treaty re-sourcing — the user loses access to the additional FTC for U.S.-source dividends taxed by Germany.
- Wizard should:
  - auto-derive U.S.-source dividend items from `income-cashflows.csv` (filter by `country_of_origin=US` or by symbol → US-domiciled lookup).
  - generate matching pairs with item_ids that align byte-for-byte across the DE and US sides.
  - present the candidate items for user confirmation before writing.

---

## G. Bank-certificate capital schedules (currently: parser is explicitly unsupported)

### G1. `germany_bank capital_certificate` parser support
- Status: `docs/provider-support.md` lists this as **Explicitly unsupported parser**. Common provider examples: Upvest, Comdirect, ING, DKB, Trade Republic, Scalable Capital — all routinely issue Steuerbescheinigungen for German residents.
- Engine effect: any user with a German bank/broker capital certificate must manually populate `derived-facts/germany/bank-capital-certificates.csv` row-by-row.
- Action item:
  1. Author a deterministic parser for Upvest Steuerbescheinigung first (Brenn / Lien have Upvest).
  2. Then add Comdirect, ING, DKB, Trade Republic, Scalable Capital using a shared helper for the standard German Steuerbescheinigung layout (Anlage KAP line numbers are the same; only header/branding differs per bank).
  3. Provider matrix in `tax_pipeline/providers/germany_bank/` mirroring `tax_pipeline/providers/datev/` shape.
  4. Update `docs/provider-support.md` to mark each one supported.

This is the single most-requested missing parser per real-return testing.
**This is the highest-priority follow-up identified by the 2025-04-29 real-return walk.**

---

## H. Tax-position manual-overrides (currently: edit `outputs/tax-positions/de-model-assumptions.csv` by hand)

### H1. `treaty_dividend_credit_eur` legacy field
- Cause: pre-engine-restructure workspaces have a nonzero value here. Engine now fails closed (treaty crediting flows through § 32d(5) per-Posten).
- Wizard should: detect legacy nonzero `treaty_dividend_credit_eur` and offer to zero it out with a one-click migration, citing the engine-restructure commit and the new path.

### H2. `capital_guenstigerpruefung_requested` toggle
- Same as A4 above — the wizard should write this row automatically based on the user's profile-level answer.

---

## I. People / payments / elections CSVs (currently: scaffold-only, hand-edited)

### I1. `config/people.csv`
- Engine error if missing: validate refuses to proceed.
- Wizard should: build the row-set from the wizard's household questions. Already partially done by `tax-pipeline-intake`'s "household basics" step — verify it covers all required columns including `german_health_insurer`, `german_statutory_health_with_sick_pay`, `german_other_vorsorge_cap_eur`, `church_tax_applicable`.

### I2. `config/payments.csv`
- Wizard should: provide an explicit step "what prepayments did you make?" with line items per jurisdiction, year, and quarter.

### I3. `config/elections.csv`
- Wizard should: derive 100 % from the profile-level elections (overlap with A1-A6). The CSV is duplicative and the wizard should generate it automatically.

---

## Priority for the wizard / parser roadmap

Highest leverage to add to the local intake wizard, in order:

1. **G1 — `germany_bank` capital-certificate parser.** Direct user-time win; the most common missing parser.
2. **C1 — Fund classification UI.** Currently 23+ manual edits per real-return setup; wizard can suggest defaults.
3. **F1 — Treaty packet auto-generation.** Without it the user silently loses meaningful FTC.
4. **E4 — Fund-pass-through foreign tax extraction.** Currently a €30+ FTC-gap risk per real return.
5. **B1, B2 — Owner tagging at upload + override stickiness.** Eliminates a confusing failure mode.
6. **A1-A6, H1, H2 — Election form fields.** Mostly mechanical once the wizard exists for it.

Items in this list are **wizard / parser features**, not legal-engine changes. The
legal engine is correct in failing closed for each of them; the gap is the
ergonomic layer above the engine.
