# Phase 1 Slice: DE25-EUER — German Self-Employment Income Integration

Status: **proposed — requires final legal review before merge** (see
§ 9 "Mandatory final review & legal audit"). Implementation slice of
[FREELANCER-SUPPORT-SPEC.md](FREELANCER-SUPPORT-SPEC.md) Phase 1.

This slice makes a German **Freiberufler**'s return actually compute:
it wires the verified § 4 Abs. 3 EStG EÜR net-profit rule (built and
verified 2026-06-10) into the executed German rule graph so freelance
profit flows into the § 2 EStG income summation and the § 32a tariff,
and renders Anlage S.

## 1. Scope

**In scope (this slice):**
- Self-employment income from **selbständige Arbeit** (§ 18 EStG,
  Freiberufler) computed by EÜR (§ 4 Abs. 3 EStG).
- A new executed stage **DE25-EUER** producing the household business
  profit, summed into **DE25-07-TAXABLE-INCOME** so it reaches
  **DE25-08-INCOME-TAX-TARIFF** (§ 32a).
- The `worker_type` position and the § 18/§ 15 sub-position.
- Anlage S rendering of the net profit.
- Loss handling: a § 4 Abs. 3 Verlust (negative profit) reduces the
  Summe der Einkünfte (§ 2 Abs. 3 Verlustausgleich within the year).

**Explicitly OUT of scope (separate slices, each gated on VERIFY):**
- § 15 EStG Gewerbe income, Gewerbesteuer, the § 35 EStG credit (Phase 3).
- Umsatzsteuer / § 19 UStG Kleinunternehmer (Phase 3).
- Self-employed **Vorsorge contribution inputs** — a freelancer with no
  wages has no Lohnsteuer-derived KV/PV; their actual § 10 contributions
  need a new input path. This slice integrates the *profit*; the
  self-employed Vorsorge input path is a **follow-on slice** and is
  flagged at every touch point. Until then the engine fails closed if a
  self-employed worker_type is declared with no Vorsorge source.
- U.S. side (Schedule C / § 199A) — Phase 2.
- Asset depreciation (AfA, § 7 EStG) and per-item EÜR line categories —
  this slice consumes aggregated receipts/expenses totals; line-item
  AfA is a follow-on.

## 2. Reference laws (verify each in § 9 before merge)

| Provision | Role | URL |
|---|---|---|
| § 2 Abs. 1 Nr. 3 EStG | selbständige Arbeit is a taxable income category | https://www.gesetze-im-internet.de/estg/__2.html |
| § 2 Abs. 2 Satz 1 Nr. 1 EStG | for § 13/§ 15/§ 18, "Einkünfte" = Gewinn | https://www.gesetze-im-internet.de/estg/__2.html |
| § 2 Abs. 3 EStG | Summe der Einkünfte = sum of all categories (Verlustausgleich) | https://www.gesetze-im-internet.de/estg/__2.html |
| § 18 EStG | Einkünfte aus selbständiger Arbeit (Freiberufler) | https://www.gesetze-im-internet.de/estg/__18.html |
| § 4 Abs. 3 EStG | EÜR: Gewinn = Betriebseinnahmen − Betriebsausgaben (cash-basis) | https://www.gesetze-im-internet.de/estg/__4.html |
| § 15 EStG | Gewerbebetrieb (OUT — fail closed this slice) | https://www.gesetze-im-internet.de/estg/__15.html |
| Anlage S (2025) | form for selbständige Arbeit income | ELSTER 2025 Anlage S (VERIFY line numbers) |
| Anlage EÜR (2025) | EÜR form | ELSTER 2025 Anlage EÜR (VERIFY line numbers) |

The § 4 Abs. 3 netting itself carries **no statutory constant** and was
verified 2026-06-10 against gesetze-im-internet. The Anlage S / EÜR
**line numbers** are the only new label surface and MUST be verified
against the 2025 ELSTER forms (New-2 label-inventory ratchet).

## 3. Facts / Positions / Operations (this slice)

**Facts** (`normalized/` — economic reality, provenance-carrying):
- `business_operating_receipts_eur` (Betriebseinnahmen total).
- `business_operating_expenses_eur` (Betriebsausgaben total).
- Source: a new `normalized/derived-facts/germany/business-income.csv`
  (or `config/business-income.csv` for direct user entry), header
  `key,amount_eur,source,note`. **File-presence semantics** per CLAUDE.md
  null/zero/missing: absent file = not declared; header-only = explicit
  zero; rows = populated.

**Positions** (declared, cited):
- `worker_type ∈ {employee, self_employed, both}` — profile/elections,
  authority § 2 Abs. 1 EStG (which income categories exist). Default
  `employee`. Drives whether business facts are required.
- `de_self_employment_class ∈ {freiberuflich_18, gewerbe_15}` — required
  iff worker_type includes self-employment; authority § 18 vs § 15 EStG.
  This slice supports `freiberuflich_18` only; `gewerbe_15` **fails
  closed** with the § 15/GewStG citation (Phase 3).

**Operations** (deterministic, cited, in the rule graph):
- `euer_net_profit_2025` (already built/signed, `germany_law.py` +
  `law/germany/year_2025/estg/p4_abs3.py`) → DE25-EUER.

## 4. Function & file change-list (exhaustive)

### 4.1 Law layer — `tax_pipeline/y2025/germany_law.py`
- **(exists)** `euer_net_profit_2025`, `GermanyEuerInputs2025`,
  `GermanyEuerResult2025`, `EUER_LEGAL_BASIS`, `ESTG_4_ABS3_URL`.
- **ADD** `ESTG_18_URL = "https://www.gesetze-im-internet.de/estg/__18.html"`.
- **REGISTER** in `REGISTERED_LAW_FUNCTIONS_2025` (germany_law.py:420):
  `"euer_net_profit_2025": ("DE25-EUER",)`. This is what satisfies the
  `LegalArchitectureEnforcement` invariant that blocked the standalone
  build — the function must map to a declared, executed stage.

### 4.2 Inputs — `tax_pipeline/y2025/germany_inputs.py`
- **ADD** `_load_business_income_facts(paths) -> (receipts_eur,
  expenses_eur, file_declared: bool)` mirroring `_load_wage_totals`
  (germany_inputs.py:191). Returns the `(value, file_declared)` pair so
  missing-vs-empty is preserved (CLAUDE.md).
- **MODIFY** `load_joint_ordinary_inputs_2025` (germany_inputs.py:724):
  read `worker_type` + `de_self_employment_class`; if self-employment is
  active, require the business-income file (fail closed with § 4 Abs. 3
  citation if missing); if `gewerbe_15`, fail closed (§ 15 out of scope).
  Pass receipts/expenses into the inputs container.

### 4.3 Input container — `germany_law.py` dataclasses
- **ADD** `BusinessIncomeInputs2025(operating_receipts_eur,
  operating_expenses_eur, self_employment_class)` frozen dataclass.
- **MODIFY** `JointOrdinaryInputs2025` (germany_law.py:649): add field
  `business_income: BusinessIncomeInputs2025 | None = None` (None =
  worker has no self-employment; keeps existing wage-only constructions
  valid — back-compat).

### 4.4 Rule graph — `tax_pipeline/y2025/germany_stages.py`
- **ADD** stage **DE25-EUER**, inserted **after `DE25-04-OTHER-22NR3`
  (line 255) and before `DE25-ALTERSENTLASTUNGSBETRAG` (line 256)**:
  ```
  LawStage(
    stage_id="DE25-EUER",
    country_or_scope="DE-2025",
    legal_refs=("§ 18 EStG", "§ 4 Abs. 3 EStG", "§ 2 Abs. 2 Satz 1 Nr. 1 EStG"),
    authority_urls=(ESTG_18_URL, ESTG_4_ABS3_URL, ESTG_2_URL),
    input_fact_keys=("de.ordinary.business_receipts_eur",
                     "de.ordinary.business_expenses_eur"),
    rounding_policy="EÜR receipts/expenses rounded to cents (q2); net not floored.",
    law_order_note="§ 4 Abs. 3 EÜR profit is an Einkunftsart under § 2 Abs. 1 Nr. 3; computed before the Gesamtbetrag der Einkünfte deductions so it joins net_employment_income + other_income in DE25-07.",
    legal_formula="de.ordinary.business_profit_eur = business_receipts_eur − business_expenses_eur per § 4 Abs. 3 EStG (may be negative)",
    narrative_templates={"de": "DE25-EUER", "en": "DE25-EUER"},
    outputs=(OutputDeclaration(
        key="de.ordinary.business_profit_eur",
        form_line_refs=(FormLineRef(form="Anlage S", line="<VERIFY>", url="<ELSTER 2025 Anlage S>"),),
        audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
    ),),
  )
  ```
- **MODIFY `DE25-07-TAXABLE-INCOME` (germany_stages.py:760)**:
  add `"de.ordinary.business_profit_eur"` to `input_fact_keys` and to the
  `legal_formula` sum (currently `net_employment_income +
  other_income_22nr3_taxable − deductions`).

### 4.5 Rule calculate bodies — `tax_pipeline/y2025/germany_ordinary_rules.py`
- **ADD** `de25_euer(facts) -> {"de.ordinary.business_profit_eur": ...}`:
  reads the two declared input keys, calls `euer_net_profit_2025`,
  returns the declared output (I7/I8 exact key contract).
- **ADD** the two input facts to `germany_ordinary_initial_facts_2025`
  (germany_ordinary_rules.py:943): `de.ordinary.business_receipts_eur` /
  `business_expenses_eur`, sourced from `BusinessIncomeInputs2025` or
  **0.00 when `business_income is None`** (wage earner → legitimate zero,
  demo unchanged in value).
- **MODIFY** the DE25-07 calculate to add `business_profit_eur` into the
  taxable-income sum.
- Register the new calculate in the rules→stage dispatch table the
  executor uses (same place the other `de25_*` calculates are wired).

### 4.6 Forms — Anlage S
- **ADD** `tax_pipeline/forms/schemas/anlage_s.toml` (model on
  `anlage_so.toml`): `form_id="anlage_s"`, `authority_url=<§ 18 EStG>`,
  one `[[lines]]` for the net-profit line (**line_id + label VERIFIED
  against 2025 Anlage S**).
- **ADD** renderer in `tax_pipeline/forms/germany.py` writing the line via
  `legal_value_entry(...)` + `legal_value_from_dict(...)` (the I11
  boundary; germany.py:554 pattern) so the value carries its
  `(stage_id, output_key, fingerprint)` provenance from DE25-EUER.

### 4.7 Position / posture — `profile.py`, `postures.py`, `scaffold_year.py`
- **ADD** `worker_type` + `de_self_employment_class` to
  `_ALLOWED_TOP_LEVEL_KEYS` / `TaxpayerProfile` (profile.py:80) and a
  `SECTION_SELF_EMPLOYMENT` entry in `postures.py` with plain-English
  tooltips + `(Legal: § 18 EStG)` (usability ratchet).
- **ADD** the columns to `ELECTIONS_COLUMNS` (scaffold_year.py) so a real
  workspace can declare them.

### 4.8 Narrative — `tax_pipeline/narrative/templates/`
- **ADD** `DE25-EUER.de.jinja` / `DE25-EUER.en.jinja` addressing inputs
  by key (`rule.inputs_by_key[...]`, invariant I12), citing § 18 / § 4
  Abs. 3 EStG and matching the rule's law refs (CLAUDE.md narrative
  naming rule).

## 5. Demo / fingerprint impact

- The demo is a wage earner: `business_income is None` →
  `business_receipts/expenses = 0.00` → `business_profit_eur = 0.00` →
  `taxable_income` **value unchanged**.
- BUT adding an `input_fact_key` to **DE25-07-TAXABLE-INCOME** changes
  that stage's declared inputs and its `output_fingerprint`. Expect:
  - DE25-07 fingerprint changes (new input in the chain) — update any
    golden fingerprint, but **assert the taxable_income value is
    identical** to pre-change for the demo.
  - A new `de.ordinary.business_profit_eur` key appears in
    `final-legal-output` `_provenance.rule_outputs[germany]` (value 0.00
    for the demo).
- Tests that assert DE25-07's exact `input_fact_keys` set or its
  fingerprint must be updated; tests asserting taxable-income / tariff
  **values** must stay green unchanged.

## 6. Tests to add (cite authority, assert numbers)

- `law/germany/year_2025/estg/p4_abs3_test.py` (exists) — netting.
- DE25-EUER stage: declared, registered, cites § 18 / § 4 Abs. 3; the
  registry maps `euer_net_profit_2025 → DE25-EUER` (architecture test).
- End-to-end: a self_employed fixture (receipts 80,000, expenses 18,250
  → profit 61,750) flows into `taxable_income` and changes the § 32a
  tariff by the correct amount; a Verlust (expenses > receipts) reduces
  Summe der Einkünfte.
- Demo: `business_profit_eur == 0.00` and `taxable_income` value
  unchanged vs the pre-slice baseline.
- `gewerbe_15` declared → fail closed with § 15 citation.
- self_employed declared with no business-income file → fail closed with
  § 4 Abs. 3 citation.

## 7. Invariant compliance (must hold)

- **I1** — no new statutory constant (EÜR is constant-free); nothing to
  centralize.
- **LegalArchitectureEnforcement** — `euer_net_profit_2025` registered to
  DE25-EUER (the fix for the boundary that blocked the standalone build).
- **I4/I7/I8** — DE25-EUER reads only its two declared inputs, writes
  only `business_profit_eur`; fail closed on missing business facts under
  an active self-employment posture.
- **I3/I11** — Anlage S line declared in schema and written via
  `legal_value_entry`; bidirectional with `OutputDeclaration.form_line_refs`.
- **I2** — `business_profit_eur` traces to DE25-EUER's
  `output_fingerprint`; it reaches a form line only through the graph.
- **I12** — narrative addresses inputs by key.
- **I13** — when `worker_type=employee`, no self-employment artifacts are
  fabricated; the zero is a legitimate "no business" value, not a
  disabled-jurisdiction marker (distinct from I13's opt-out case).
- **New-2 label inventory** — the Anlage S line number is VERIFIED against
  the 2025 form or carried in the baseline with a marker.
- **A4** — `p4_abs3.py` already signed; no new signed file in this slice
  unless a new shadow is added (then sign + register).

## 7a. Implementation status (2026-06-12)

Landed on `main`, full suite green (1372 tests, 0/0), A4 lock 125/125:

- **Sub-slice 1 — DONE.** `euer_net_profit_2025` (§ 4 Abs. 3) + signed
  shadow `p4_abs3.py`; `BusinessIncomeInputs2025`; `worker_type` /
  `de_self_employment_class` positions (profile + posture registry);
  loader `_load_business_income_position` with fail-closed wiring.
- **Sub-slice 2 — DONE.** `DE25-EUER` stage declared + registered
  (`euer_net_profit_2025 → DE25-EUER`); `de25_euer` calculate; business
  receipts/expenses initial facts; `DE25-07` sums § 18 profit; structural
  pins updated.
- **Sub-slice 4 — DONE.** End-to-end tests through the full graph
  (`tests/y2025/test_germany_euer.py`): profit-on-wages, zero-wage
  freelancer, Verlust (not floored), and all loader fail-closed cases —
  hand-derived euro outcomes confirmed.
- **Narrative — DONE.** `DE25-EUER.jinja` (de/en, inputs by key, I12).
- **Sub-slice 3 — REMAINING.** Anlage S schema + renderer + the
  `form_line_refs` on `DE25-EUER`'s output (I3 bidirectional + I11
  boundary). **Verified line number:** the Freiberufler net profit goes
  on **Anlage S 2025 Zeile 4** (Gewinn aus freiberuflicher Tätigkeit =
  Betriebseinnahmen − Betriebsausgaben; Zeile 5 for a second activity) —
  corroborated by multiple tax-help sources (steuern.de, accountable.de,
  sevdesk); **must be confirmed against the official ELSTER 2025 Anlage S
  PDF before merge** (the official ELSTER form URL 404'd on fetch; the
  § 9 gate requires this confirmation, and the New-2 label-inventory
  ratchet requires an ELSTER-VERIFIED marker on the Zeile-4 label).

## 8. Build order (sub-slices, each green before the next)

1. Loader + `BusinessIncomeInputs2025` + `worker_type`/class positions
   (fail-closed wiring; no graph change yet).
2. DE25-EUER stage + `de25_euer` calculate + registry entry +
   initial-facts (zero-default); update DE25-07 sum. Green the value,
   update DE25-07 fingerprint/key-set tests.
3. Anlage S schema + renderer (I3/I11) + narrative (I12).
4. End-to-end self_employed fixture tests + Verlust + fail-closed cases.

## 9. Mandatory final review & legal audit (gating — do NOT merge until all checked)

Every box must be checked by a reviewer auditing against the **actual
legal authority**, not against this spec:

- [ ] **§ 2 summation correctness** — confirm § 4 Abs. 3 profit belongs in
  the Summe der Einkünfte as § 2 Abs. 1 Nr. 3 (selbständige Arbeit) and
  is summed *before* the Sonderausgaben/außergewöhnliche-Belastungen
  deductions that produce zvE, verified against § 2 Abs. 2–5 EStG.
- [ ] **Loss offset** — confirm a Verlust correctly reduces Summe der
  Einkünfte (§ 2 Abs. 3 Verlustausgleich) and is not floored, and that
  this does not violate any § 10d / Mindestbesteuerung rule the engine
  should model (flag if it does).
- [ ] **§ 9a interaction** — confirm the § 19 Arbeitnehmer-Pauschbetrag is
  NOT applied to § 18 business income (it must remain wage-only).
- [ ] **§ 18 vs § 15 boundary** — confirm the `freiberuflich_18` posture
  is the right gate and that `gewerbe_15` correctly fails closed (no
  Gewerbesteuer silently skipped).
- [ ] **Anlage S 2025 line number(s)** — verified against the published
  2025 ELSTER Anlage S PDF; New-2 marker present; schema label matches.
- [ ] **Citations** — every `legal_refs` / `authority_url` / narrative
  citation resolves to the cited provision (URL-liveness); the narrative
  citation matches the rule's law refs (CLAUDE.md).
- [ ] **Vorsorge scope** — confirm this slice does NOT silently mis-handle
  a freelancer's KV/PV: a self_employed workspace with no Vorsorge source
  fails closed (the self-employed Vorsorge input path is a declared
  follow-on, not silently zero).
- [ ] **Demo invariance** — `de.ordinary.taxable_income` and the tariff
  are byte-identical to the pre-slice baseline for the wage-earner demo
  (value, not fingerprint).
- [ ] **Independent recompute** — a reviewer recomputes the
  receipts/expenses → profit → zvE → § 32a tariff by hand for the
  self_employed fixture and confirms the asserted numbers.
- [ ] **Full suite + invariants + A4 + label-inventory green**; demo runs
  end-to-end (exit 0).

> This slice changes how taxable income is computed for a real filer
> class. Per the project's posture it is not done until every box above
> is checked against authoritative sources, ideally with a qualified
> professional confirming the § 2 summation and the Anlage S mapping.
