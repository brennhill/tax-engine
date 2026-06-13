# Phase 2 Slice: US25-SCHEDULE-C — U.S. Schedule C Business Income + § 199A Gate

Status: **proposed — requires final legal review before merge** (see
§ 10 "Mandatory final review & legal audit"). Phase 2 of
[FREELANCER-SUPPORT-SPEC.md](FREELANCER-SUPPORT-SPEC.md); the U.S.
mirror of the German [FREELANCER-DE-EUER-SLICE-SPEC.md](FREELANCER-DE-EUER-SLICE-SPEC.md)
(income) + [FREELANCER-DE-VORSORGE-SLICE-SPEC.md](FREELANCER-DE-VORSORGE-SLICE-SPEC.md)
(deductions), now on `main`.

The German side computes a Freiberufler's profit (§ 18 / § 4 Abs. 3 EStG)
and feeds it into the tariff. This slice does the U.S. side: a U.S.
citizen abroad reports the **same** business on **Schedule C** (Form
1040), the net profit flows into AGI/taxable income and the
self-employment-tax base, and the § 199A QBI deduction is **adjudicated**
(see § 2 — for this engine's taxpayer it most likely does **not** apply).

The economic facts are **shared** across jurisdictions (CLAUDE.md
jurisdiction-boundary rule): the same receipts/expenses the German EÜR
nets are the Schedule C gross income less § 162 expenses, converted /
re-stated per U.S. rules.

---

## 1. Scope

**In scope (this slice):**
- **Schedule C net profit** = § 61 gross receipts − § 162 ordinary &
  necessary business expenses (verified 2026-06-10 against the IRS
  Schedule C page; constant-free, loss not floored on Schedule C itself
  but the income that reaches Form 1040 is the net).
- Wiring net profit into **two** existing U.S. paths:
  1. **Income / AGI** — as a component of `schedule_1_other_income_usd`
     (Schedule 1 line 3 → Form 1040) → `US25-07-AGI` → taxable income.
  2. **The SE-tax base** — `se_inputs.net_se_earnings_usd` (today read
     from `manual_overrides.se_net_earnings_usd`) becomes the **derived**
     Schedule C net profit, so § 1402(a)(12) (× 0.9235) and the existing
     § 1401 / Totalization logic (Phase 0) apply over the real profit.
- The loader change to read business receipts/expenses (the symmetric
  mirror of the German `_load_business_income_position`), gated on the
  shared `elections.worker_type` position, **failing closed** when
  self-employment is declared with no facts.
- The **§ 199A applicability gate** (§ 2) and the Schedule C / Form 8995
  form rendering.

**Explicitly OUT of scope (fail closed or not_applicable):**
- **§ 199A QBI for foreign-source business income** — see § 2; for a
  German-resident freelancer this engine targets, the deduction most
  likely does not apply. The slice does **not grant** a § 199A deduction
  for foreign business income; it surfaces `not_applicable` with the
  citation. (US-source self-employment QBI, with the W-2-wage / UBIA /
  SSTB above-threshold limits, is a separate, constant-dependent slice.)
- § 15 Gewerbe / Gewerbesteuer; the entire German side.
- Partnership / S-corp K-1 business income; multiple Schedule Cs;
  Schedule C losses interacting with the § 461(l) excess-business-loss
  limit and at-risk / passive rules — fail closed if declared.
- Self-employed health-insurance deduction (§ 162(l)), SEP/solo-401(k)
  (§ 404), QBI for any U.S.-source SE — follow-ons.

---

## 2. The § 199A QBI applicability finding (the #1 legal call — confirm in § 10)

**§ 199A(c)(3)(A)(i)** defines "qualified items of income" as those
**"effectively connected with the conduct of a trade or business within
the United States"** (§ 864(c)). A U.S. citizen who is **resident in
Germany** earning **German-source** freelance income is conducting a
trade or business **in Germany, not within the United States** — so that
income is **not QBI**, and **no § 199A deduction is allowed** on it.

Therefore, for this engine's modeled taxpayer (the cross-border
US-citizen-in-Germany freelancer), the correct § 199A posture is
**`not_applicable` — foreign-source business income is not QBI**, with
the § 199A(c)(3)(A)(i) / § 864(c) citation. The engine must **not** grant
a 20% deduction the taxpayer is not entitled to (that would be a
LEAK-class over-deduction — the inverse of the German Vorsorge
understatement, equally forbidden).

The slice therefore models § 199A as a **gate**, not a granted
deduction:
- If the business income is **foreign-source** (the default for this
  taxpayer; tie it to the German § 18 posture / a `business_income_source
  ∈ {us_effectively_connected, foreign}` position defaulting to
  `foreign`), the QBI deduction is **`not_applicable`** with the
  citation, and taxable income is **unchanged** by § 199A.
- If **US-effectively-connected** business income is declared, the
  below-threshold simple case (20% of QBI, capped at 20% of taxable
  income before QBI) MAY be modeled in a **follow-on** with VERIFIED 2025
  thresholds; the above-threshold W-2-wage / UBIA / SSTB limits **fail
  closed** until modeled. This slice ships the gate + the foreign-source
  `not_applicable`; it does **not** ship a granted QBI number.

**This is the highest-stakes legal call in the slice — get § 2 confirmed
by a qualified professional in § 10 before merge.**

---

## 3. Reference laws (verify each in § 10)

| Provision | Role | URL |
|---|---|---|
| 26 U.S.C. § 61 | gross income (Schedule C gross receipts) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61 |
| 26 U.S.C. § 162 | ordinary & necessary business expenses | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section162 |
| IRS Schedule C (Form 1040) | Profit or Loss From Business; net = receipts − expenses | https://www.irs.gov/forms-pubs/about-schedule-c-form-1040 |
| Schedule 1 (Form 1040) line 3 | business income flows to Form 1040 | https://www.irs.gov/forms-pubs/about-schedule-1-form-1040 |
| 26 U.S.C. § 1401 / § 1402(a)(12) | SE tax on net SE earnings × 0.9235 (already modeled) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1402 |
| § 164(f) | one-half SE-tax deduction reduces AGI (already modeled) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section164 |
| **26 U.S.C. § 199A(c)(3)(A)(i) + § 864(c)** | **QBI requires US-effectively-connected income → foreign business income is NOT QBI** | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section199A |
| § 911 (FEIE) × SE / QBI | FEIE excludes income tax not SE tax; FEIE-excluded income is not QBI (moot if § 199A N/A) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911 |
| U.S.-Germany Totalization Agreement (1979) | German Certificate of Coverage exempts the SE earnings from § 1401 (Phase 0) | https://www.ssa.gov/international/Agreement_Pamphlets/germany.html |

**Statutory constants:** the Schedule C netting is **constant-free**.
The SE constants (0.9235, 12.4%, 2.9%, $176,100 wage base) already live
signed in `law/usa/year_2025/usc26/p1401.toml`. **No new constant** is
introduced by the in-scope work. (Any future US-source QBI follow-on
needs the VERIFIED 2025 § 199A taxable-income thresholds + SSTB phaseout
range from the Rev. Proc. — flagged, not in this slice.)

---

## 4. Facts / Positions / Operations

**Facts** (`normalized/` — shared economic reality, provenance-carrying):
- `business_gross_receipts_usd` — § 61 gross business income.
- `business_expenses_usd` — § 162 total business expenses.
- Source: `config/us-business-income.csv` (`key,amount_usd,source,note`,
  keys `gross_receipts_usd` / `business_expenses_usd`), OR — preferred —
  **derive from the same economic facts** the German `business-income.csv`
  carries, converted at the 2025 IRS yearly-average rate
  (`eur_per_usd_yearly_average_2025`, already a constant). The jurisdiction
  boundary rule: one economic fact, two legal classifications. **File-
  presence null/zero/missing** semantics, returning `(value, file_declared)`
  (mirror `_load_business_income_facts`, germany_inputs.py:82).

**Positions** (declared, cited):
- `worker_type ∈ {employee, self_employed, both}` — **already exists**
  (`profile.py`, `postures.py`); **reused** on the U.S. side (a US-citizen
  freelancer in Germany is self-employed on both sides).
- **NEW** `business_income_source ∈ {foreign, us_effectively_connected}`
  — the cited § 199A(c)(3)(A)(i) / § 864(c) position, **default
  `foreign`** for this engine's taxpayer. Drives the § 199A gate (§ 2).
  Lives in `elections`.
- `totalization_certificate_present` — **already exists** (Phase 0);
  exempts the derived SE base from § 1401.

**Operations** (deterministic, cited, registered to a rule-graph stage):
- `schedule_c_net_profit_2025(*, inputs)` — § 61 − § 162 netting
  (constant-free; the production+shadow `p162.py` from the earlier
  attempt is the model — re-add it AND register it to the stage this time,
  per the LegalArchitectureEnforcement lesson).
- `qbi_deduction_gate_2025(...)` — returns `not_applicable` for foreign
  business income with the § 199A citation; a granted number only for the
  US-effectively-connected below-threshold case (deferred). Registered to
  its stage.

---

## 5. Function & file change-list (exhaustive, grounded in the rule-graph map)

### 5.1 Law layer — `tax_pipeline/y2025/us_law.py`
- **RE-ADD** `USScheduleCInputs2025` / `USScheduleCResult2025` /
  `schedule_c_net_profit_2025` (the verified § 61/§ 162 netting; same code
  as the backed-out attempt) AND **register** it:
  `REGISTERED_LAW_FUNCTIONS_2025["schedule_c_net_profit_2025"] =
  ("US25-02A-SCHEDULE-C",)` (us_law.py:390) and add it to the
  `compute_us_assessment_2025` stage tuple. (Registration is what the
  earlier standalone build was missing — LegalArchitectureEnforcement.)
- **ADD** `USC_199A_URL` + a `qbi_gate_2025` operation returning the
  `not_applicable` posture for foreign source (no granted deduction).

### 5.2 Inputs — `tax_pipeline/y2025/us_inputs.py`
- **ADD** `_load_us_business_income_facts(paths) -> (receipts, expenses,
  file_declared)` (mirror germany_inputs.py:82) and
  `_load_us_business_income_position(paths, profile)` resolving
  `worker_type` + `business_income_source`, **failing closed** when
  self-employment is declared with no facts (§ 61/§ 162 citation), and
  failing closed on `us_effectively_connected` (QBI-granting path not yet
  modeled).
- **MODIFY** `load_us_assessment_inputs_2025` (us_inputs.py:652-1026): set
  `se_inputs.net_se_earnings_usd` = **derived Schedule C net profit**
  (replacing the `manual_overrides.se_net_earnings_usd` read at
  us_inputs.py:905) when self-employment is declared; keep the manual
  override as the value only when worker_type=employee (back-compat), or
  deprecate it with a fail-closed if both are set inconsistently. Carry
  the Schedule C net profit into the income side too (see 5.4).

### 5.3 Input container — `us_law.py` `USAssessmentInputs2025`
- The net profit reaches the graph via the existing `se_inputs`
  (already on the dataclass) AND a new income field; add a
  `schedule_c_net_profit_usd: Decimal = ZERO_USD` (or a
  `USScheduleCResult2025`) so the income-side stage can read it. Default
  zero → wage earner unchanged.

### 5.4 Rule graph — `tax_pipeline/y2025/us_stages.py` + `us_rules.py`
- **ADD** stage **US25-02A-SCHEDULE-C** between US25-02-INCOME-SIDE-INPUTS
  and US25-03-CAPITAL-BUCKETS; output `us.stage.schedule_c` ({net_profit,
  gross, expenses}); calculate calls `schedule_c_net_profit_2025`.
- **MODIFY US25-02-INCOME-SIDE-INPUTS** (us_rules.py:168-180): add the
  Schedule C net profit into `schedule_1_other_income_usd` (currently
  `substitute_payments + staking`). This is the single wiring that makes
  it reach AGI → taxable income. (The SE base is already wired via
  se_inputs from the loader; no AGI change needed beyond Schedule 1.)
- **ADD** stage **US25-08A-QBI-GATE** after US25-08-TAXABLE-INCOME:
  outputs the § 199A status (`not_applicable` for foreign source) and a
  zero deduction; taxable income is unchanged for the foreign-source
  taxpayer. (When a future slice grants US-source QBI, this stage
  subtracts it before US25-09-REGULAR-TAX.) Declared + registered.

### 5.5 SE-tax interaction (already built — confirm)
- US25-SE-TAX already reads `se_inputs.net_se_earnings_usd` and applies
  § 1402(a)(12) × 0.9235 + the Phase 0 Totalization exemption. Once the
  loader derives net SE earnings from Schedule C, a covered freelancer's
  SE tax stays `exempt_under_totalization` (Phase 0) while the **income**
  still flows to AGI — the correct cross-border result. **No SE-stage
  change**; add a test asserting both behaviors together.

### 5.6 Forms — `tax_pipeline/forms/schemas/` + `forms/usa.py`
- **ADD** `schedule_c.toml` (the net-profit line; VERIFY 2025 Schedule C
  line numbers) + `_write_schedule_c` renderer via `legal_value_entry`
  (I3/I11), reading `us.stage.schedule_c.net_profit`.
- **ADD** `form_8995.toml` only if a granted QBI number is ever rendered;
  for the foreign-source `not_applicable` posture, the U.S. narrative /
  filing package states the § 199A non-applicability with the citation —
  **no Form 8995 line is rendered** (I13: explicitly absent, not a zero
  line). Confirm in § 10.

### 5.7 Position / posture — `postures.py`, `profile.py`
- Reuse `worker_type`. **ADD** `elections.business_income_source` to the
  allowed set (`profile.py`) + a posture-registry entry with the
  plain-English tooltip + `(Legal: § 199A(c)(3)(A)(i); § 864(c))`.

### 5.8 Narrative — `tax_pipeline/narrative/templates/`
- **ADD** `US25-02A-SCHEDULE-C.jinja` (income) and **US25-08A-QBI-GATE.jinja**
  (the § 199A non-applicability explanation), inputs addressed by key
  (I12), citations matching the rule law refs.

---

## 6. Cross-border interactions to get right

- **Totalization (Phase 0):** deriving the SE base from Schedule C must
  not break the Totalization exemption — a covered freelancer's SE tax
  stays `not_applicable`, the income still flows. Test both together.
- **FEIE × SE / QBI:** § 911 FEIE excludes the income from **income tax**
  but not from **SE tax** (moot under Totalization). FEIE-excluded income
  is **not QBI** anyway — but since § 199A is `not_applicable` for foreign
  source regardless (§ 2), there is no QBI×FEIE arithmetic to model in
  this slice. Confirm in § 10.
- **Treaty (Art. 7 business profits):** independent personal services
  fold into Art. 7 under the 2006 protocol; for a Germany-resident with
  no U.S. permanent establishment, business profits are taxable only in
  Germany, with the saving clause letting the U.S. tax its citizen
  (FEIE/FTC relief). This reuses the existing treaty machinery; confirm
  no new treaty stage is needed.

---

## 7. Demo / fingerprint impact

- The demo is a wage earner: `worker_type=employee` → Schedule C net
  profit 0 → `schedule_1_other_income_usd` unchanged in value, SE base
  unchanged → AGI / taxable income / tax **value-identical**.
- Adding US25-02A-SCHEDULE-C and US25-08A-QBI-GATE changes the executed
  stage list/count and the income-side / taxable-income stage
  fingerprints. Update the U.S. structural pins (the stage-count and
  stage-id-list tests, the `available` initial-key set in
  test_law_stage_graph) the same way the DE slices did; assert the
  wage-earner demo's AGI / taxable income / total tax **values** are
  byte-identical.

---

## 8. Invariant compliance

- **I1 / A4** — constant-free; SE constants already signed in `p1401.toml`.
- **LegalArchitectureEnforcement** — `schedule_c_net_profit_2025` and the
  QBI gate are **registered** to declared stages (the fix for what blocked
  the earlier standalone Schedule C attempt).
- **I4 / I7 / I8** — new stages read only declared inputs, write only
  declared outputs; the loader fails closed on missing business facts
  under self-employment, and on `us_effectively_connected` (QBI-granting
  path not modeled) — no silent over-deduction.
- **I13** — § 199A `not_applicable` for foreign source is an explicit
  cited status, never a zero Form 8995 line; wage-earner Schedule C
  artifacts are absent, not zeroed.
- **I3 / I11** — Schedule C line via `legal_value_entry` with a real
  stage fingerprint; bidirectional with the schema.
- **I12** — new narratives address inputs by key.
- **New-2** — VERIFY the 2025 Schedule C line number(s); marker.

---

## 9. Build order (sub-slices, each green before the next)

1. **Schedule C net profit core** — re-add + **register**
   `schedule_c_net_profit_2025` (p162 shadow + production), the loader +
   `business_income_source` position (fail-closed wiring), the
   US25-02A-SCHEDULE-C stage, and the Schedule 1 / SE-base wiring. Green
   the value; wage-earner demo unchanged. **This is the high-value,
   constant-free, correct core.**
2. **§ 199A gate** — US25-08A-QBI-GATE returning `not_applicable` for
   foreign source (no taxable-income change), fail-closed on
   us_effectively_connected; narrative.
3. **Forms** — Schedule C schema + renderer (verified line numbers); the
   § 199A non-applicability narration (no Form 8995 line).
4. **End-to-end + cross-border tests** — Schedule C profit → AGI → tax;
   Totalization-exempt SE + taxed income together; § 199A not_applicable;
   fail-closed cases; demo invariance.

---

## 10. Mandatory final review & legal audit (gating — do NOT merge until all checked)

- [ ] **§ 199A foreign-source non-applicability (THE call)** — confirm,
  with a qualified professional, that a U.S. citizen resident in Germany
  earning German-source freelance income has **no § 199A QBI deduction**
  (§ 199A(c)(3)(A)(i) / § 864(c) — not US-effectively-connected), and that
  the engine therefore correctly grants **zero** § 199A and surfaces
  `not_applicable` with the citation. If any edge (e.g. a U.S.-situs
  client, U.S. PE) makes some income US-ECI, confirm the gate fails closed
  rather than guessing.
- [ ] **Schedule C net profit → both paths** — confirm the net profit
  correctly (a) flows to Schedule 1 line 3 → Form 1040 income → AGI, and
  (b) is the SE-tax base (× 0.9235), and that these are the **same**
  profit, not double-counted; § 61 / § 162 / Schedule SE.
- [ ] **Totalization + income together** — confirm a German-Certificate-
  of-Coverage freelancer's SE tax stays `exempt_under_totalization`
  (Phase 0) while the Schedule C income still flows to U.S. income tax.
- [ ] **FEIE interaction** — confirm § 911 FEIE excludes the business
  income from income tax (if elected) but not SE tax, and that the
  ordering vs the SE-tax base and § 164(f) deduction is correct.
- [ ] **Currency** — if the profit is derived from the German EÜR facts,
  confirm the 2025 IRS yearly-average rate conversion and that it matches
  the Schedule C "U.S. dollars" instruction (vs spot-rate per receipt).
- [ ] **Schedule C 2025 line numbers** — verify the net-profit line
  against the official 2025 Schedule C PDF (New-2 marker).
- [ ] **Demo invariance** — wage-earner AGI / taxable income / total tax
  byte-identical (value) to the pre-slice baseline; demo runs exit 0.
- [ ] **Independent recompute** — hand-recompute a freelancer fixture:
  receipts/expenses → net profit → Schedule 1 → AGI → taxable income →
  regular tax, and the SE-tax (or its Totalization exemption), and confirm
  § 199A subtracts nothing.
- [ ] **Full suite + invariants + A4 + label-inventory green.**

> This slice changes how U.S. taxable income and the SE-tax base are
> computed for a real filer class and makes a high-stakes call that a
> deduction (§ 199A) does **not** apply. Per the project's posture it is
> not done until every box is checked against authoritative sources,
> ideally with a qualified professional confirming the § 199A
> foreign-source non-applicability.
