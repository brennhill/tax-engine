# Phase 1 Slice: DE25-SE-VORSORGE — Self-Employed § 10 EStG Vorsorgeaufwendungen

Status: **proposed — requires final legal review before merge** (see
§ 11 "Mandatory final review & legal audit"). Follow-on slice of
[FREELANCER-DE-EUER-SLICE-SPEC.md](FREELANCER-DE-EUER-SLICE-SPEC.md),
itself Phase 1 of [FREELANCER-SUPPORT-SPEC.md](FREELANCER-SUPPORT-SPEC.md).

The EÜR slice (now on `main`) wired a Freiberufler's **profit** (§ 18 /
§ 4 Abs. 3 EStG) into the § 2 EStG income summation and the § 32a tariff.
This slice closes the matching **deduction** gap: a pure freelancer's
**Vorsorgeaufwendungen** (§ 10 EStG — Kranken-, Pflege-, and
Rentenversicherung paid out of pocket) are not captured, so the engine
computes a freelancer's taxable income with **zero § 10 Vorsorge
deductions** and **overstates their tax**. This is a silent
understatement of a deduction — exactly the fail-closed-violating class
the project forbids (CLAUDE.md "Operations fail closed on missing
inputs … Silent defaults to zero are the highest-severity bug class").

The fix routes a freelancer's actual contributions into the **existing**
§ 10 stages (`DE25-05-RETIREMENT-SA`, `DE25-06-HEALTH-VORSORGE-SA`) so
the § 10 Abs. 3 / Abs. 4 **caps apply correctly** — it does **not** build
a parallel deduction path that bypasses the caps.

---

## 1. Scope

**In scope (this slice):**
- A self-employed person's own **Altersvorsorge** (§ 10 Abs. 1 Nr. 2
  EStG — Basisrente / gesetzliche or freiwillige RV / berufsständisches
  Versorgungswerk), deductible at the 2025 rate (100% from 2023) up to
  the § 10 Abs. 3 Höchstbetrag.
- A self-employed person's own **Basiskranken- und Pflegeversicherung**
  (§ 10 Abs. 1 Nr. 3 EStG — base tier, fully deductible).
- A self-employed person's own **sonstige Vorsorgeaufwendungen** (§ 10
  Abs. 1 Nr. 3a EStG) within the § 10 Abs. 4 cap, where the
  self-employed person who funds their own health insurance gets the
  **higher €2,800** cap (§ 10 Abs. 4 Satz 2/3 EStG) rather than the
  €1,900 employee cap.
- A new **fact source** for these out-of-pocket contributions, and the
  loader/input-container/initial-facts plumbing to feed them into the
  existing § 10 stages **through the existing law functions and caps**.
- The interim **fail-closed** posture (§ 10) tightened to a real
  deduction path (this slice *is* the deduction path the EÜR slice
  deferred to).

**Explicitly OUT of scope (separate slices, each gated on VERIFY):**
- § 15 EStG Gewerbe income / Gewerbesteuer / the § 35 EStG credit
  (Phase 3) — already fails closed in the EÜR loader.
- The **entire U.S. side** — Schedule C, § 199A, SE-tax / Totalization
  interaction (Phases 0 / 2). This slice touches only German § 10.
- Anything that is not § 10 EStG Vorsorge: § 9 Werbungskosten, § 33/§ 33a
  außergewöhnliche Belastungen, § 10b Spenden, § 24a, the § 10c
  Pauschbetrag floor mechanics (consumed unchanged from `DE25-06B`).
- **Rürup/Riester top-ups, voluntary/private add-on KV tiers beyond the
  base tier, Krankentagegeld** — the slice models the base statutory /
  basis-tier contributions a freelancer must pay; richer Vorsorge product
  modeling is a follow-on and **fails closed** if declared.
- **Splitting** a contribution across spouses where only one is
  self-employed beyond what the existing per-person allocation already
  does — the existing joint aggregators are reused verbatim; no new
  spousal-allocation legal logic is introduced.

---

## 2. The gap, precisely (current-behavior evidence)

The two § 10 Vorsorge stages read contributions **only** from each
person's `WageFacts2025` (the Lohnsteuerbescheinigung-derived
employee/employer split):

- `tax_pipeline/y2025/germany_law.py:694-706` — `WageFacts2025` carries
  `employer_pension_contribution_eur`, `employee_pension_contribution_eur`,
  `employee_health_insurance_eur`, `employee_nursing_care_insurance_eur`,
  `employee_unemployment_insurance_eur`. These are the **only** Vorsorge
  amount fields in the input model.
- `tax_pipeline/y2025/germany_ordinary_rules.py:292-323` — `de25_05_retirement_sa`
  reads `person.wage.employee_pension_contribution_eur` /
  `employer_pension_contribution_eur` for **every** person and runs them
  through `retirement_special_expense_deduction_2025`.
- `tax_pipeline/y2025/germany_ordinary_rules.py:326-387` — `de25_06_health_vorsorge_sa`
  reads `person.wage.employee_health_insurance_eur`,
  `employee_nursing_care_insurance_eur`, and
  `employee_unemployment_insurance_eur` and runs them through
  `deductible_basic_health_contribution_2025` /
  `other_vorsorge_allowed_employee_2025`.

A pure freelancer (`worker_type=self_employed`, no wages) has a
`WageFacts2025` whose contribution fields are all `0.00` (no
Lohnsteuerbescheinigung). Therefore:

- `de25_05_retirement_sa` → `retirement_special_expenses_total_eur = 0.00`.
- `de25_06_health_vorsorge_sa` → `health_vorsorge_total_eur = 0.00`.
- `DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG` adds only the § 10c €36/€72
  Pauschbetrag floor, so `total_special_expenses ≈ 36/72 EUR`.
- `DE25-07-TAXABLE-INCOME` subtracts that near-zero special-expenses
  block from the income sum (which now includes the § 18 profit from the
  EÜR slice). **Result: the freelancer's taxable income — and § 32a tax —
  is overstated by the full value of their § 10 deductions** (potentially
  five figures of deduction: the Altersvorsorge cap alone is €29,344).

The EÜR slice already named this gap and chose to **fail closed** rather
than ship the silent zero — `FREELANCER-DE-EUER-SLICE-SPEC.md:29-34` and
its § 9 gate item "Vorsorge scope." This slice replaces that interim
fail-closed with the real deduction path. The current state on `main`
must therefore *already* be fail-closing a self-employed workspace at the
loader (verify in § 10 / build step 0); if a self-employed return can be
computed today with zero Vorsorge, that is the live bug this slice fixes.

---

## 3. Reference laws (verify each in § 11 before merge)

| Provision | Role | URL |
|---|---|---|
| § 10 Abs. 1 Nr. 2 EStG | Altersvorsorgeaufwendungen (Basisrente / gesetzl. + berufsständ. RV) are Sonderausgaben | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 1 Nr. 3 EStG | Basiskranken- + Pflegeversicherung fully deductible (base tier; 4% Krankengeld reduction on KV) | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 1 Nr. 3a EStG | sonstige Vorsorgeaufwendungen (further insurances), within the Abs. 4 cap | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 3 EStG | Altersvorsorge Höchstbetrag = max. (AG+AN) knappschaftliche-RV contribution; **100% of the capped base from 2023** | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 4 Satz 1 EStG | sonstige-Vorsorge cap €1,900 for taxpayers with employer/§3-Nr-62 KV cover (employees) | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 4 Satz 2/3 EStG | sonstige-Vorsorge cap €2,800 for taxpayers who fund their **own** KV (self-employed) | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10 Abs. 4 Satz 4 EStG | joint cap = sum of each spouse's individual cap (Zusammenveranlagung) | https://www.gesetze-im-internet.de/estg/__10.html |
| § 10c EStG | Sonderausgaben-Pauschbetrag €36/€72 floor (consumed unchanged in DE25-06B) | https://www.gesetze-im-internet.de/estg/__10c.html |
| § 3 Nr. 62 EStG | tax-free employer share subtracted from the retirement base (N/A for a pure freelancer — no employer share) | https://www.gesetze-im-internet.de/estg/__3.html |
| Anlage Vorsorgeaufwand (2025) | form: Altersvorsorge Zeilen 4-9, KV/PV Zeilen 11-14, sonstige Zeilen 31-37 (**VERIFY 2025 line numbers**) | https://www.bundesfinanzministerium.de/.../anlage-vorsorgeaufwand.html |

### 2025 statutory constants — all already in `law/germany/year_2025/estg/p10.toml`; verify each (VERIFY)

This slice introduces **no new statutory constant** if the existing § 10
constants are confirmed to cover the self-employed case. Each must be
re-confirmed against the controlling 2025 authority in § 11:

- **VERIFY** `RETIREMENT_SPECIAL_EXPENSE_CAP_SINGLE_EUR = 29344.00`
  (`p10.toml:27`) — § 10 Abs. 3; BBG knappschaftliche RV €118,800 × 24.7%
  = €29,343.60 → €29,344. Joint = ×2 = €58,688 (applied by
  `joint_retirement_special_expense_deductions_2025`). Confirm both the
  single figure **and** that ×2 is the correct 2025 joint Höchstbetrag.
- **VERIFY** `RETIREMENT_SPECIAL_EXPENSE_CAP_BBG_KNAPPSCHAFT_RV_WEST_2025_EUR
  = 118800.00` and `..._KNAPPSCHAFT_BEITRAGSSATZ_2025 = 0.247`
  (`p10.toml:32,37`) — the BMAS Sozialversicherungs-Rechengrößenverordnung
  2025 inputs to the cap.
- **VERIFY** the **100% Altersvorsorge deductibility for 2025**. The
  current code (`law/germany/year_2025/estg/p10.py:117-137`) implements
  100% (no fractional Abzugssatz applied). Confirm § 10 Abs. 3 Satz 6
  reaches 100% from 2023 and that **no separate reduced rate applies to a
  self-employed person's own Altersvorsorge** — the AG-share subtraction
  is simply €0 for a freelancer, so the same function is correct.
- **VERIFY** `OTHER_VORSORGE_CAP_GENERAL_EUR = 2800.00` (`p10.toml:12`) —
  § 10 Abs. 4 Satz 2/3, the **self-employed** cap. Confirm the
  self-employed who fund their own KV get the **€2,800** cap, NOT the
  €1,900 employee cap.
- **VERIFY** `OTHER_VORSORGE_CAP_EMPLOYEE_EUR = 1900.00` (`p10.toml:7`) —
  § 10 Abs. 4 Satz 1, the employee cap (relevant for the `both` worker
  type, and for the spouse who is an employee in a joint return).
- **VERIFY** `STATUTORY_HEALTH_SICK_PAY_REDUCTION_RATE = 0.04`
  (`p10.toml:42`) — § 10 Abs. 1 Nr. 3 Satz 4 KV reduction. Confirm
  whether this 4% Krankengeld reduction applies to a **voluntarily** or
  **privately** insured freelancer's base-tier KV the same way it applies
  to a statutory employee's KV (the rate is workspace-overridable per the
  existing `health_insurance_sick_pay_reduction_rate` person field; a
  freelancer with no Krankengeld entitlement may have a 0% reduction).
  **This is the highest-risk legal item in the slice** — get it confirmed.
- **VERIFY** `SONDERAUSGABEN_PAUSCHBETRAG_SINGLE/JOINT_EUR = 36/72`
  (`p10.toml:17,22`) — § 10c floor, unchanged but in the path.

**Conclusion to confirm in § 11:** the slice is **constant-free** — every
2025 figure it needs already lives signed in `p10.toml`/`p10.py`. If any
VERIFY above reveals a missing or wrong 2025 figure, that figure is a
**new statutory constant** and must be added to `p10.toml`, re-signed
(A4), and round-tripped (F1) **before** any rule reads it. Do not write a
literal into a loader or rule (I1).

---

## 4. Facts / Positions / Operations (this slice)

**Facts** (`normalized/` — economic reality, provenance-carrying):
- `se_retirement_contributions_eur` — the freelancer's own
  Altersvorsorge (Basisrente/RV/Versorgungswerk) contributions paid in
  2025.
- `se_basic_health_contributions_eur` — base-tier Krankenversicherung.
- `se_nursing_care_contributions_eur` — Pflegeversicherung.
- `se_other_vorsorge_contributions_eur` — § 10 Abs. 1 Nr. 3a sonstige
  (e.g. Unfall-, Haftpflicht-, Arbeitslosenversicherung the freelancer
  pays).
- Source: a new per-person file
  `normalized/derived-facts/germany/business-vorsorge.csv` (or
  `config/business-vorsorge.csv` for direct user entry), header
  `slot,key,amount_eur,source,note`, keyed by person slot so it parallels
  `people.csv`. **File-presence semantics** per CLAUDE.md null/zero/missing:
  absent file = not declared; header-only = explicit zero; rows =
  populated. The loader must return `(values, file_declared)` and never
  collapse missing→zero (mirror `_load_business_income_facts`,
  `germany_inputs.py:81-111`).
- Each contribution fact carries source provenance (file/section/snippet)
  exactly like the wage facts it parallels.

**Positions** (declared, cited):
- `worker_type ∈ {employee, self_employed, both}` — **already exists**
  (`postures.py:277-303`, `profile.py:122`). Reused, not re-declared.
- `de_self_employment_class ∈ {freiberuflich_18, gewerbe_15}` —
  **already exists** (`postures.py:304-328`); `gewerbe_15` already fails
  closed.
- **The § 10 Abs. 4 cap selection (€1,900 vs €2,800) is ALREADY a
  declared, validated position** — the per-person
  `german_other_vorsorge_cap_eur` field, validated to be exactly
  `1900.00` or `2800.00` against the named constants
  (`germany_inputs.py:395-406`), surfaced as
  `PersonOrdinaryInputs2025.other_vorsorge_cap_eur`
  (`germany_law.py:732`). **A self-employed person must declare
  `2800.00`.** This slice does NOT add a new cap position; it ensures the
  freelancer's contributions flow through the existing
  `other_vorsorge_allowed_employee_2025` /
  `joint_other_vorsorge_allowed_employee_2025` functions that already
  honor this per-person cap. (Open question for § 11: whether the loader
  should additionally *require* `2800.00` when `worker_type` includes
  self-employment for that person, or leave it a free declaration — the
  conservative answer is to validate consistency and fail closed on a
  freelancer who declares €1,900 without an employee KV basis.)
- New sub-position, if § 11 confirms the KV-reduction question is
  person-specific: a `se_kv_has_krankengeld` marker driving whether the
  4% § 10 Abs. 1 Nr. 3 Satz 4 reduction applies. The existing
  `health_insurance_sick_pay_reduction_rate` person field
  (`germany_law.py:731`) already carries this — reuse it; do not add a
  parallel rate.

**Operations** (deterministic, cited, in the rule graph):
- **No new law function.** The four existing, signed § 10 functions —
  `retirement_special_expense_deduction_2025`,
  `joint_retirement_special_expense_deductions_2025`,
  `deductible_basic_health_contribution_2025`,
  `other_vorsorge_allowed_employee_2025`,
  `joint_other_vorsorge_allowed_employee_2025`
  (`germany_law.py` / `law/germany/year_2025/estg/p10.py`) — already
  compute the caps. They are already registered to `DE25-05` / `DE25-06`
  (`germany_law.py:427-431`). This slice **feeds them a freelancer's
  contributions** instead of (only) wage-derived ones.

The architectural consequence (see § 7): because the calculations already
exist as registered rule functions, this slice's *new* work is **fact
plumbing and a possible per-person contribution-source merge**, NOT a new
legal function. That keeps it on the right side of
`LegalArchitectureEnforcement` by construction — there is no standalone
legal helper to register.

---

## 5. Function & file change-list (exhaustive)

The design principle: **add a parallel set of declared per-person
contribution facts** (self-employed, out-of-pocket) and **sum them into
the same arguments** the existing § 10 functions already consume, so the
existing caps apply once over the combined base. Do **not** add a second
deduction computation.

### 5.1 Input container — `tax_pipeline/y2025/germany_law.py`
- **ADD** a frozen dataclass `BusinessVorsorgeInputs2025` (sibling to
  `BusinessIncomeInputs2025`, `germany_law.py:592-604`):
  ```
  @dataclass(frozen=True)
  class BusinessVorsorgeInputs2025:
      slot: str                                  # person slot the contributions belong to
      retirement_contributions_eur: Decimal       # § 10 Abs. 1 Nr. 2
      basic_health_contributions_eur: Decimal     # § 10 Abs. 1 Nr. 3 (KV base)
      nursing_care_contributions_eur: Decimal     # § 10 Abs. 1 Nr. 3 (PV)
      other_vorsorge_contributions_eur: Decimal   # § 10 Abs. 1 Nr. 3a
  ```
  Docstring cites § 10 Abs. 1 Nr. 2 / Nr. 3 / Nr. 3a EStG with the URL
  (CLAUDE.md position/operation citation rule).
- **MODIFY** `JointOrdinaryInputs2025` (`germany_law.py:749`): add field
  `business_vorsorge: tuple[BusinessVorsorgeInputs2025, ...] = ()`
  (empty tuple = no self-employed Vorsorge declared, default = back-compat
  for wage-only constructions; per-person so `both`/joint households work).
  Note the **distinction**: `()` here is "declared empty / none" — the
  loader is responsible for converting "missing under an active
  self-employment posture" into a fail-closed error **before** this
  container is built, so `()` reaching a rule always means a legitimate
  "this household has no self-employed contributions" (CLAUDE.md
  null/zero/missing; mirror the EÜR `business_income=None` contract).

### 5.2 Inputs loader — `tax_pipeline/y2025/germany_inputs.py`
- **ADD** `_load_business_vorsorge_facts(paths) -> (rows: tuple[dict, ...],
  file_declared: bool)` mirroring `_load_business_income_facts`
  (`germany_inputs.py:81-111`): returns the `(value, file_declared)` pair,
  preserves missing-vs-empty, validates the known keys
  (`retirement/basic_health/nursing_care/other_vorsorge`), fails closed on
  an unknown key with the § 10 citation.
- **ADD** `_load_business_vorsorge_positions(paths, profile, person_slots)
  -> tuple[BusinessVorsorgeInputs2025, ...]` mirroring
  `_load_business_income_position` (`germany_inputs.py:114-157`):
  - returns `()` when `worker_type == "employee"`;
  - when `worker_type ∈ {self_employed, both}`: **require** the
    business-vorsorge file — if `not file_declared`, **fail closed** with
    the § 10 Abs. 1 Nr. 2/3/3a citation and a message that a freelancer's
    out-of-pocket KV/PV/RV must be declared (no silent zero). This is the
    real-deduction-path replacement for the EÜR slice's interim
    fail-closed; see § 10.
  - validate that every declared slot exists in `person_slots`;
  - **(open, § 11)** if a self-employed person declares
    `german_other_vorsorge_cap_eur=1900.00`, fail closed (a freelancer who
    funds their own KV takes the €2,800 cap per § 10 Abs. 4 Satz 2/3) —
    unless the cap field already enforces this consistently; resolve in
    review.
- **MODIFY** `load_joint_ordinary_inputs_2025` (`germany_inputs.py:813`):
  call `_load_business_vorsorge_positions(...)` and pass the result into
  `JointOrdinaryInputs2025(business_vorsorge=...)` alongside the existing
  `business_income=...` wiring (`germany_inputs.py:830,877`).

### 5.3 Initial facts — `tax_pipeline/y2025/germany_ordinary_rules.py`
- **ADD** to `germany_ordinary_initial_facts_2025` (`germany_ordinary_rules.py:981-1031`)
  a declared per-person fact key carrying the self-employed contributions,
  e.g. `de.ordinary.se_vorsorge_by_slot` (a mapping slot→the four Decimal
  amounts), built from `inputs.business_vorsorge`. When
  `inputs.business_vorsorge == ()` (wage earner) the value is an **empty
  mapping** — a legitimate explicit "no self-employed contributions," so
  the demo is **unchanged in value** (mirror the
  `business_receipts/expenses` zero-default at
  `germany_ordinary_rules.py:1022-1031`).

### 5.4 Rule graph — `tax_pipeline/y2025/germany_stages.py`
- **MODIFY `DE25-05-RETIREMENT-SA`** (`germany_stages.py:403-454`): add
  `"de.ordinary.se_vorsorge_by_slot"` to `input_fact_keys` (currently
  `("de.ordinary.people", "de.ordinary.filing_posture")`,
  `germany_stages.py:408`). Update `legal_formula` to note that the
  retirement base = `employee_pension + employer_pension + se_retirement`
  for each person, capped per § 10 Abs. 3 as today. No new
  `OutputDeclaration` and no new `form_line_refs` — the same
  `retirement_special_expenses_total_eur` scalar already lands on Anlage
  Vorsorgeaufwand Zeilen 4-9 (`germany_stages.py:442-452`); its value
  simply becomes non-zero for a freelancer.
- **MODIFY `DE25-06-HEALTH-VORSORGE-SA`** (`germany_stages.py:455-533`):
  add `"de.ordinary.se_vorsorge_by_slot"` to `input_fact_keys`
  (`germany_stages.py:460`). Update `legal_formula` so the health base =
  `employee_health + se_basic_health`, nursing base = `employee_nursing +
  se_nursing`, other base = `employee_unemployment + se_other`. The
  existing three output scalars (basic_health → Zeilen 11-14, other_allowed
  → Zeilen 31-37, total) are unchanged in shape; values become non-zero.
- **No new stage.** Reusing `DE25-05`/`DE25-06` is mandatory so the § 10
  Abs. 3 / Abs. 4 caps are applied exactly once over the combined base
  (the "do not create a parallel deduction path" requirement).

### 5.5 Rule calculate bodies — `tax_pipeline/y2025/germany_ordinary_rules.py`
- **MODIFY `de25_05_retirement_sa`** (`germany_ordinary_rules.py:292-323`):
  read the new `de.ordinary.se_vorsorge_by_slot` fact; for each person,
  add their `se_retirement_contributions_eur` to the **employee** pension
  argument passed to `retirement_special_expense_deduction_2025`
  (employer share stays the wage value — a freelancer's is €0). For the
  `married_joint` branch, the existing
  `joint_retirement_special_expense_deductions_2025(people)` reads
  `person.wage.*` directly (`germany_law.py:1571-1582`); rather than mutate
  `people`, **extend that joint function (or pass an explicit per-person
  combined-base tuple)** so the SE contributions enter the joint cap. The
  cleanest seam is to make the joint aggregator accept the already-summed
  per-person base; pick the minimal change that keeps the function pure and
  keeps the cap on the **combined** base. (Resolve the exact signature in
  build step 2; the constraint is: SE retirement contributions must be in
  the base the § 10 Abs. 3 cap is applied to, single and joint.)
- **MODIFY `de25_06_health_vorsorge_sa`** (`germany_ordinary_rules.py:326-387`):
  for each person, add `se_basic_health` to the health argument and
  `se_nursing` to the nursing argument of
  `deductible_basic_health_contribution_2025`, and add `se_other` to the
  `per_person_other_contributions` feeding
  `other_vorsorge_allowed_employee_2025` /
  `joint_other_vorsorge_allowed_employee_2025`. The per-person
  `other_vorsorge_cap_eur` (€1,900/€2,800) is already passed
  (`germany_ordinary_rules.py:346,354`) — a freelancer's €2,800 flows
  through unchanged. **Do not bypass these functions.**
- **No change to `de25_06b_sonderausgaben_pauschbetrag`,
  `de25_07_taxable_income`** — they consume the (now non-zero) § 10
  outputs unchanged. The freelancer's larger Vorsorge total automatically
  reduces `total_special_expenses` and hence taxable income.

### 5.6 Forms — Anlage Vorsorgeaufwand (no new schema)
- **NO new form schema.** The three Anlage Vorsorgeaufwand line groups
  already exist (`tax_pipeline/forms/schemas/anlage_vorsorgeaufwand.toml`:
  `zeilen_4_9`, `zeilen_11_14`, `zeilen_31_37`) and are already bound to
  the `DE25-05`/`DE25-06` scalar outputs via
  `OutputDeclaration.form_line_refs` (I3) and written via the I11
  `legal_value_entry` boundary. The freelancer's values flow to the **same
  lines**. **VERIFY** in § 11 that the 2025 ELSTER Anlage Vorsorgeaufwand
  Zeile groupings are correct (the schema header already flags a possible
  2026 renumber) — this is the only label-inventory (New-2) surface, and
  it is a **re-verification**, not a new line.

### 5.7 Position / posture — `postures.py`, intake
- `worker_type` / `de_self_employment_class` already exist
  (`postures.py:277-328`). **ADD** intake guidance (tooltip text) on the
  new business-vorsorge fact entry surface explaining that a freelancer
  must enter their **own** KV/PV/RV contributions (which an employee would
  see pre-filled from the Lohnsteuerbescheinigung), with the
  `(Legal: § 10 Abs. 1 Nr. 2/3/3a EStG)` parenthetical (usability ratchet).
  No new *election* position is required beyond the cap field already
  validated at `germany_inputs.py:395-406`.

### 5.8 Narrative — `tax_pipeline/narrative/templates/`
- **UPDATE** `DE25-05-RETIREMENT-SA.{de,en}.jinja` and
  `DE25-06-HEALTH-VORSORGE-SA.{de,en}.jinja` to narrate the
  self-employed contribution source when present, addressing the new input
  by key (`rule.inputs_by_key["de.ordinary.se_vorsorge_by_slot"]`, **never
  positional** — I12), citing the same § 10 refs the rules carry
  (CLAUDE.md narrative-naming rule). Adding a declared input means the
  positional-index trap (I12 rationale) applies — keep keyed access.

---

## 6. Demo / fingerprint impact

- The demo is a wage earner: `worker_type=employee` →
  `business_vorsorge=()` → `se_vorsorge_by_slot = {}` → every § 10
  function receives the **same** wage-derived arguments as today →
  `retirement_special_expenses_total_eur`, `health_vorsorge_total_eur`,
  and `total_special_expenses` are **value-identical** to pre-slice.
- BUT adding `de.ordinary.se_vorsorge_by_slot` to the `input_fact_keys` of
  `DE25-05` and `DE25-06` changes those stages' declared inputs and hence
  their `output_fingerprint`. Expect:
  - `DE25-05` and `DE25-06` fingerprints change (new input in the chain);
    downstream `DE25-06B` / `DE25-07` fingerprints change transitively.
    Update any golden fingerprints, but **assert the deduction and
    taxable-income *values* are identical** to pre-change for the demo.
  - A new `de.ordinary.se_vorsorge_by_slot` key appears in
    `final-legal-output` `_provenance.rule_outputs[germany]` only if it is
    an output; it is an **input** fact, so it appears in the stage's
    `input_fact_keys` / fingerprint payload, not as a rule output.
- Tests asserting the exact `input_fact_keys` set or fingerprint of
  `DE25-05`/`DE25-06`/`DE25-06B`/`DE25-07` must be updated; tests
  asserting Vorsorge / taxable-income / tariff **values** for the
  wage-earner demo must stay green unchanged.

---

## 7. Invariant compliance (must hold)

- **I1 / A4** — no new statutory literal: every § 10 figure already lives
  in signed `p10.toml`/`p10.py`. If a VERIFY in § 3 surfaces a missing
  2025 figure, it is added to `p10.toml`, re-signed
  (`python -m law.audit sign law/germany/year_2025/estg/p10.toml` and
  `p10.py`), and round-tripped (F1) before any rule reads it. No literal
  in a loader or rule.
- **LegalArchitectureEnforcement** — **no new public law function**, so
  nothing to register and nothing that could become a standalone legal
  helper. The existing four/five § 10 functions remain registered to
  `DE25-05`/`DE25-06` (`germany_law.py:427-431`). This is the structural
  reason the slice is fact-plumbing, not new math (the EÜR slice's
  blocker does not recur here).
- **I4 / I7 / I8** — `DE25-05`/`DE25-06` read only their declared inputs
  (now including `de.ordinary.se_vorsorge_by_slot`) and write only their
  existing declared outputs; the loader fails closed on missing
  self-employed Vorsorge facts under an active self-employment posture (no
  silent zero — closes the headline gap).
- **I3 / I11** — Anlage Vorsorgeaufwand lines are already declared in the
  schema and written via `legal_value_entry`; the freelancer's values use
  the **same** bidirectional bindings. No new form-line refs needed (the
  values just become non-zero).
- **I2** — every Vorsorge value still traces to `DE25-05`/`DE25-06`
  `output_fingerprint`; it reaches a form line only through the graph.
- **I12** — the updated `DE25-05`/`DE25-06` narratives address the new
  input by key, never positional.
- **I13** — when `worker_type=employee`, no self-employed-Vorsorge
  artifacts are fabricated; `se_vorsorge_by_slot = {}` is a legitimate
  "no self-employed contributions," distinct from I13's
  disabled-jurisdiction opt-out marker (same posture as the EÜR slice's
  `business_income=None`).
- **New-2 label inventory** — no new label; the existing Anlage
  Vorsorgeaufwand Zeile groups are **re-verified** against the 2025 form
  (the schema already flags a plausible renumber). If a 2025 Zeile differs
  from the baseline, update `tests/data/label_inventory_baseline.json` with
  an ELSTER-verified marker.
- **A4 lock** — `p10.py`/`p10.toml` are already signed; touch them **only**
  if a VERIFY surfaces a missing/wrong 2025 constant, then re-sign
  (current lock is 125/125 per the EÜR slice landing note).

---

## 8. Tests to add (cite authority, assert numbers)

- `law/germany/year_2025/estg/p10_test.py` (exists) — extend with
  self-employed cases: a freelancer Altersvorsorge above and at the
  €29,344 cap (assert capped); KV/PV base fully deductible (Nr. 3); sonstige
  at the €2,800 cap (assert the €2,800 ceiling binds, NOT €1,900). Cite
  § 10 Abs. 1 Nr. 2/3/3a, Abs. 3, Abs. 4 Satz 2/3.
- Stage tests: `DE25-05`/`DE25-06` declare the new input key; the registry
  still maps the § 10 functions to those stages (architecture test).
- End-to-end (mirror `tests/y2025/test_germany_euer.py`): a pure
  freelancer fixture (e.g. EÜR profit €61,750 from the EÜR slice +
  Altersvorsorge €12,000, KV €5,000, PV €1,000, sonstige €1,200) → assert
  the § 10 total deduction, the resulting `taxable_income`, and the § 32a
  tariff **by hand**. Show the tariff is **materially lower** than the
  current zero-Vorsorge behavior (the bug being fixed).
- `both` worker type: wage Vorsorge + self-employed Vorsorge combine under
  one § 10 Abs. 3 / Abs. 4 cap (assert the cap is applied **once** over the
  combined base, not twice).
- Joint return with one self-employed spouse: the €2,800 + €1,900 joint cap
  (§ 10 Abs. 4 Satz 4) is applied correctly.
- Fail-closed: `worker_type=self_employed` with no business-vorsorge file →
  fail closed with the § 10 citation (the headline fix).
- Demo invariance: wage-earner Vorsorge totals and `taxable_income` are
  value-identical to the pre-slice baseline.

---

## 9. Build order (sub-slices, each green before the next)

1. **Law-test extension only** — extend `p10_test.py` with the
   self-employed cap cases (no plumbing). Confirms the existing functions
   already produce the legally correct self-employed numbers (and surfaces
   any VERIFY failure from § 3 *before* any plumbing is built).
2. **Loader + `BusinessVorsorgeInputs2025` + initial facts** — fact path
   only, with fail-closed wiring; no graph input-key change yet. The
   per-person facts exist but are not yet read by the rules.
3. **Wire into `DE25-05`/`DE25-06`** — add the input key to both stages,
   extend the calculate bodies and (minimally) the joint retirement
   aggregator to fold SE contributions into the **combined capped base**.
   Update the `DE25-05`/`DE25-06`/`DE25-06B`/`DE25-07` fingerprint/key-set
   tests; assert demo Vorsorge/taxable-income values unchanged.
4. **Narrative (I12)** update for `DE25-05`/`DE25-06`.
5. **End-to-end self-employed + `both` + joint + fail-closed tests**;
   hand-derived euro outcomes confirmed.

---

## 10. Interim fail-closed recommendation

**Recommendation: keep the engine fail-closed for self-employed workspaces
until this slice lands, and locate the gate in the loader.**

The EÜR slice already deferred the Vorsorge input path and committed to
failing closed (`FREELANCER-DE-EUER-SLICE-SPEC.md:29-34` and § 9 "Vorsorge
scope"). The structurally correct place for the interim gate is the
**same loader function that already fails closed for the EÜR slice** —
`_load_business_income_position` (`germany_inputs.py:114-157`), or a sibling
called from `load_joint_ordinary_inputs_2025` (`germany_inputs.py:813-877`).

Concretely, until step 3 of § 9 lands:
- when `worker_type ∈ {self_employed, both}` and **no** business-vorsorge
  source is declared, **raise** with the § 10 Abs. 1 Nr. 2/3/3a citation
  and a message stating that a freelancer's out-of-pocket KV/PV/RV must be
  declared and that the engine refuses to compute a return that would
  silently understate the § 10 deduction (mirror the EÜR fail-closed
  message at `germany_inputs.py:146-152`).

This guarantees the engine **never silently understates** a freelancer's
Vorsorge: it either deducts the declared contributions through the capped
§ 10 path (post-slice) or refuses to run (interim). It must **never** reach
`de25_05_retirement_sa` / `de25_06_health_vorsorge_sa` with a self-employed
posture and an all-zero wage-derived base and emit a zero deduction — that
is the LEAK-class silent zero this whole slice exists to remove.

**Action before this slice lands:** verify on `main` that a self-employed
workspace already fails closed at the loader (build step 0 / § 11 first
box). If it does **not** — i.e. a `worker_type=self_employed` return can be
computed today with `total_special_expenses ≈ €36/72` — that is the live
correctness bug, and the interim fail-closed gate above should be added as
a **standalone hotfix** ahead of the full deduction path.

---

## 11. Mandatory final review & legal audit (gating — do NOT merge until all checked)

Every box must be checked by a reviewer auditing against the **actual legal
authority**, not against this spec:

- [ ] **Live-bug confirmation** — confirm on `main` whether a
  `worker_type=self_employed` workspace currently (a) fails closed at the
  loader, or (b) computes a return with zero § 10 Vorsorge. If (b), the
  interim fail-closed (§ 10) ships first as a hotfix.
- [ ] **§ 10 Abs. 1 Nr. 2 Altersvorsorge 100% for 2025** — confirm § 10
  Abs. 3 Satz 6 reaches 100% from 2023 and that a self-employed person's
  own Basisrente/RV/Versorgungswerk contribution is deductible at 100% up
  to the Höchstbetrag, with **no** separate reduced Abzugssatz; confirm the
  AG-share subtraction is correctly €0 for a freelancer.
- [ ] **§ 10 Abs. 3 Höchstbetrag** — re-verify €29,344 single / €58,688
  joint for 2025 against the BMAS Sozialversicherungs-Rechengrößenverordnung
  2025 (BBG knappschaftliche RV €118,800 × 24.7%); confirm ×2 is the
  correct joint cap.
- [ ] **§ 10 Abs. 4 €2,800 vs €1,900** — confirm the **self-employed** who
  fund their own KV take the **€2,800** cap (Satz 2/3), the employee takes
  €1,900 (Satz 1), and the joint cap is the **sum** of each spouse's
  individual cap (Satz 4); confirm the `both` worker type and mixed-spouse
  joint case apply the right per-person cap.
- [ ] **§ 10 Abs. 1 Nr. 3 base-tier KV/PV** — confirm a freelancer's
  base-tier Kranken- + Pflegeversicherung is **fully deductible** (not
  subject to the €2,800/€1,900 cap — that cap is for Nr. 3a sonstige only),
  and confirm whether the 4% § 10 Abs. 1 Nr. 3 Satz 4 Krankengeld reduction
  applies to a freelancer's KV (voluntary statutory vs private; Krankengeld
  entitlement). **Highest-risk item — get professional confirmation.**
- [ ] **Single combined cap** — confirm that for a `both` taxpayer, wage
  and self-employed contributions enter **one** § 10 Abs. 3 base and **one**
  § 10 Abs. 4 cap (the cap is not applied twice).
- [ ] **Anlage Vorsorgeaufwand 2025 line numbers** — verify the Zeilen
  4-9 / 11-14 / 31-37 groupings against the published 2025 ELSTER Anlage
  Vorsorgeaufwand PDF; New-2 marker present; schema labels match.
- [ ] **Citations** — every `legal_refs` / `authority_url` / narrative
  citation resolves to the cited provision (URL-liveness); the narrative
  citations match the rule law refs (CLAUDE.md).
- [ ] **Constant-free claim** — confirm the slice added **no** new
  statutory literal; if any 2025 figure was missing/wrong, it was added to
  `p10.toml`, re-signed (A4), and round-tripped (F1) before use.
- [ ] **Demo invariance** — wage-earner demo § 10 deductions and
  `de.ordinary.taxable_income` are byte-identical (value, not fingerprint)
  to the pre-slice baseline.
- [ ] **Independent recompute** — a reviewer recomputes, by hand, the
  freelancer fixture's contributions → § 10 Abs. 3 cap → § 10 Abs. 4 cap →
  total_special_expenses → zvE → § 32a tariff and confirms the asserted
  numbers, and confirms the tariff is lower than the current zero-Vorsorge
  behavior by exactly the deduction value.
- [ ] **Full suite + invariants + A4 + label-inventory green**; demo runs
  end-to-end (exit 0).

> This slice changes how taxable income is computed for a real filer class
> (the pure Freiberufler) and removes a known silent understatement of a
> deduction. Per the project's posture it is not done until every box above
> is checked against authoritative sources, ideally with a qualified
> professional confirming the § 10 Abs. 1 Nr. 3 Satz 4 KV-reduction
> treatment and the § 10 Abs. 4 cap selection.
