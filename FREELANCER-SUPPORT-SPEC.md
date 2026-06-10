# Freelancer / Self-Employment Support — Phase 0–4 Specification

Status: **proposed** (no code written). This is a plan-of-record for
extending the engine from a pure wage-earner model to a cross-border
**self-employed** taxpayer: a U.S. citizen resident in Germany who earns
freelance / business income.

It follows the existing architecture verbatim — the rule graph is the
legal core (`ENGINE-RESTRUCTURE-PLAN.md`), every value is a **fact**, a
cited **position**, or a deterministic legally-cited **operation**
(`CLAUDE.md` § "Facts, Positions, Deterministic Operations"), statutory
constants live only in `law/` signed modules (invariant I1, A4 lock),
and nothing reaches a form line outside the graph (invariants I2–I13).

> **Disclaimer carries through.** Self-employment tax law — the § 18 vs
> § 15 line, the EÜR, § 199A QBI, and Totalization mechanics — is
> judgment-heavy. This spec describes *what to model*, not tax advice.
> Every constant below is marked **VERIFY** where it must be confirmed
> against the controlling 2025 authority before it is written into a
> signed `law/` module. Conflicting / unclear sources fail closed
> (`not_applicable` or explicit error), never a silent zero.

---

## 0. Current state (what already exists)

| Capability | State | Where |
|---|---|---|
| U.S. SE tax (§ 1401/§ 1402) | **Implemented & audited** — but fed one manual number `manual_overrides.se_net_earnings_usd` | `law/usa/year_2025/usc26/p1401.py`, `tax_pipeline/y2025/us_inputs.py:905` |
| Schedule SE form schema | **Exists** | `tax_pipeline/forms/schemas/schedule_se.toml` |
| Totalization Agreement | **Stubbed — fails closed** when a Certificate of Coverage applies | `law/usa/year_2025/usc26/p1401.py:115-126` |
| Totalization acknowledgment election | **Exists** | `tax_pipeline/intake/postures.py` (`elections.acknowledges_totalization_agreement_germany_us`) |
| German freelance income (§ 18 / § 15) | **Not modeled** — income side is wage-only (Anlage N / Lohnsteuer) | — |
| Anlage S / Anlage G / Anlage EÜR | **Not modeled** | — |
| Gewerbesteuer (trade tax) | **Not modeled** | — |
| Umsatzsteuer (VAT) | **Not modeled** | — |
| U.S. Schedule C / § 199A QBI | **Not modeled** | — |

The engine therefore *can* compute a freelancer's U.S. SE tax today only
if you hand-type the net profit, and it has **no** German business-income
path at all. The Totalization stub is the single highest-value blocker:
a Germany-resident U.S.-citizen freelancer is normally **exempt from U.S.
SE tax** (covered by the German system) yet the engine refuses to run
when that is declared.

---

## 1. Scope & the worker-type axis

A new top-level **position**: `worker_type ∈ {employee, self_employed, both}`.
This is a declared legal posture (it changes which income categories and
forms exist), not a derived fact. It lives alongside the filing postures
in the profile / posture registry and gates the new screens, rules, and
form renderers.

Two German self-employment sub-postures, themselves cited positions
(they change the entire downstream form set):

- **Freiberufler** — Einkünfte aus selbständiger Arbeit, **§ 18 EStG**.
  No Gewerbesteuer, no Gewerbeanmeldung. Anlage S.
- **Gewerbetreibender** — Einkünfte aus Gewerbebetrieb, **§ 15 EStG**.
  Triggers Gewerbesteuer (GewStG) and the § 35 EStG credit. Anlage G.

The § 18/§ 15 classification is a **position with a cited basis**: the
loader fails closed if `worker_type=self_employed` and no sub-posture is
declared (`CLAUDE.md` "A position is taken explicitly").

---

## Phase 0 — U.S.-Germany Totalization Agreement (unblock the common case)

**Goal.** Make a Germany-resident U.S.-citizen freelancer's *U.S.* SE-tax
posture correct: covered by the German social-insurance system, exempt
from § 1401 with a German Certificate of Coverage.

**Authority.** SSA U.S.-Germany Totalization Agreement (1979),
`https://www.ssa.gov/international/Agreement_Pamphlets/germany.html`;
26 U.S.C. § 1401; the existing `SSA_TOTALIZATION_DE_URL` constant.

**Design.**

1. **Position** — a new declared election
   `elections.se_social_security_coverage ∈ {german_system, us_system, none}`
   with a `certificate_of_coverage_held: bool`. The position file carries
   the SSA authority link in its header (`CLAUDE.md` position rules). The
   *acknowledgment* flag already present is necessary but not sufficient;
   this position states *which* system covers the SE earner.
2. **Operation** — replace the `NotImplementedError` in `p1401.py:115-126`
   with a real branch:
   - `german_system` + certificate held → SE earnings are **out of
     scope** of § 1401: return a `not_applicable` SE assessment carrying
     the Totalization citation (invariant I13 posture — explicitly absent,
     not a silent zero).
   - `us_system` → compute § 1401 normally (already implemented).
   - `none` / undeclared while `worker_type` includes self-employment →
     **fail closed** with the citation in the error.
3. **Renderer / narrative** — the Schedule SE / Form 1040 SE line shows a
   `not_applicable` status with the Totalization reason string; the U.S.
   narrative explains the exemption and references the certificate. No
   legal math in the renderer (Invariant I3/I11).

**New / changed files.** `law/usa/year_2025/usc26/p1401.py` (+ re-sign,
A4), `p1401_test.py`, `us_inputs.py`, posture registry, `US-en-narrative`
template, `tests/y2025/test_us_law.py`.

**Tests (cite authority, assert outcomes).** certificate-held → SE tax
`not_applicable` and total tax excludes SE; `us_system` → SE tax computed;
undeclared-but-self-employed → fail closed. Invariant I13 test that the
disabled SE artifact is explicitly absent, not zeroed.

**Effort / risk.** ~2–4 days. Low risk — isolated branch, reuses the
existing (correct) § 1401 math. **Do this first.**

---

## Phase 1 — German self-employment income (Anlage S / EÜR)

**Goal.** A first-class German business-income category feeding the
income tax return, computed from an Einnahmenüberschussrechnung.

**Authority.** § 18 EStG (selbständige Arbeit), § 15 EStG (Gewerbe),
**§ 4 Abs. 3 EStG** (Einnahmenüberschussrechnung — cash-basis P&L);
Anlage S / Anlage G / Anlage EÜR (ELSTER 2025 form lines — **VERIFY**).

**Facts (raw economic reality — `normalized/facts/`).** Per the
jurisdiction-boundary rule, facts describe *economic* reality and are
shared across countries; legal classification is per-jurisdiction.
- `business_revenue_items` — date, amount (EUR), counterparty, source
  document provenance (invoice / bank export).
- `business_expense_items` — date, amount, category, deductibility marker,
  provenance.
- Derived fact: `business_net_profit_eur = Σrevenue − Σdeductible_expense`
  (deterministic, cited to § 4 Abs. 3 EStG).
- **Null/zero/missing** applies: header-only EÜR = "declared zero
  profit," absent file = missing (fail closed if `worker_type` says
  self-employed). See `CLAUDE.md` "Null / zero / missing".

**Positions.** § 18 vs § 15 classification; the EÜR-vs-Bilanz method
(default EÜR for natural persons under the §141 AO thresholds — **VERIFY**);
home-office and asset-depreciation elections (these may reuse existing
DE deduction positions).

**Law module (new chapter files under `law/germany/year_2025/estg/`).**
- `p18.py/.toml/_test.py` — selbständige Arbeit income recognition.
  *(Note: `p18` already exists under `invstg/` for Vorabpauschale — this
  is EStG § 18, a distinct file under `estg/`.)*
- `p15.py/.toml/_test.py` — Gewerbe income recognition.
- `p4_abs3.py/.toml/_test.py` — EÜR netting rule.
- Knock-on to `estg/p10.*` (Vorsorge): a self-employed person pays the
  **full** Kranken-/Pflegeversicherung (no employer split) — the § 10
  deductible-contribution math changes; the Arbeitnehmer-Pauschbetrag
  (§ 9a) no longer applies to business income.

**Rules (graph stages in `tax_pipeline/y2025/germany_*_rules.py`).** New
stages: EÜR aggregation → § 18/§ 15 classification → income integration
into the § 2 EStG summe der Einkünfte → flows into the existing § 32a
tariff. Declared `input_fact_keys` / `output_keys` (invariants I4, I7, I8).

**Forms (new schemas under `tax_pipeline/forms/schemas/`).**
`anlage_s.toml`, `anlage_g.toml`, `anlage_eur.toml` + renderers in
`tax_pipeline/forms/germany.py` via `legal_value_entry` (invariant I11),
form-line refs declared (invariant I3).

**Tests.** Concrete EÜR → net profit → tariff outcomes with § 18/§ 15
citations; Vorsorge recomputation for self-employed; Anlage S/EÜR line
population.

**Effort / risk.** ~2–3 weeks. Medium-high — new income category touching
the § 2 summation and Vorsorge; the form-line numbering needs ELSTER 2025
verification (the New-2 label-inventory ratchet applies).

---

## Phase 2 — U.S. Schedule C + § 199A QBI

**Goal.** The U.S. side of the same business: Schedule C profit/loss, the
§ 199A QBI deduction, and the FEIE × SE-tax interaction — all reusing the
economic facts from Phase 1.

**Authority.** Schedule C (Profit or Loss from Business); 26 U.S.C.
§ 162 (ordinary & necessary expenses); **26 U.S.C. § 199A** (QBI
deduction — 20 %, with the taxable-income thresholds, SSTB phaseout, and
W-2-wage / UBIA limits — **VERIFY** 2025 thresholds via Rev. Proc.);
§ 911 (FEIE) × SE interaction; § 1401 (Phase 0).

**Facts.** Reuse `business_revenue_items` / `business_expense_items` from
Phase 1 (the jurisdiction-boundary rule: one economic fact, two legal
classifications). USD conversion via the existing
`eur_per_usd_yearly_average_2025` constant.

**Positions.** QBI eligibility & SSTB classification (a cited position —
a "specified service trade or business" is phased out above the
threshold); aggregation elections; the FEIE-vs-FTC choice already exists.

**Law module (`law/usa/year_2025/usc26/`).**
- `p162.py/.toml/_test.py` — business-expense deductibility.
- `p199a.py/.toml/_test.py` — QBI deduction with the 2025 thresholds
  (new signed constants, A4 lock).
- Interaction note: **FEIE excludes from income tax but NOT from SE tax**
  (§ 1402 net earnings are pre-FEIE). With Phase 0 Totalization the SE
  tax is `not_applicable` for the DE-resident case, but the engine must
  still compute the correct § 199A base and FEIE interaction for U.S.
  income-tax purposes. Document this cross-rule dependency explicitly.

**Treaty note.** Independent personal services fold into **Art. 7
(Business Profits)** under the 2006 protocol (the former Art. 14 was
deleted — **VERIFY**). For a freelancer resident in Germany with no U.S.
permanent establishment, business profits are taxable only in Germany;
the saving clause (Art. 1(4)) lets the U.S. tax its citizen with FEIE/FTC
relief. This reuses the existing treaty re-sourcing machinery
(`treaty_law.py`, the `DBA_USA_ART_*` citation constants).

**Forms.** `schedule_c.toml` + `form_8995.toml` (QBI) schemas and
renderers in `tax_pipeline/forms/usa.py`; Schedule SE already exists.

**Tests.** Schedule C net profit; § 199A under/over threshold; SSTB
phaseout; FEIE × SE-base interaction; the Totalization `not_applicable`
path from Phase 0 combined with a non-zero § 199A base.

**Effort / risk.** ~2–3 weeks. Medium-high — § 199A has real complexity
(thresholds, SSTB, wage/UBIA limits); start with the below-threshold
simple case and gate the above-threshold limits behind an explicit
fail-closed `not_applicable` until modeled.

---

## Phase 3 — German trade & turnover taxes (the long tail)

Only required for a **§ 15 Gewerbe** business and/or a VAT-registered
freelancer. A pure Freiberufler under the Kleinunternehmer regime skips
this phase entirely.

### 3a. Gewerbesteuer (trade tax)

**Authority.** GewStG; § 35 EStG (Gewerbesteuer-Anrechnung); the §  11
Abs. 1 Freibetrag €24,500 for natural persons and the 3.5 % Steuermesszahl
(**VERIFY**); the municipality **Hebesatz** (config, not a statutory
constant — varies by Gemeinde).

**Design.** New `law/germany/year_2025/gewstg/` chapter; Gewerbesteuer is
a **separate filing surface** (Gewerbesteuererklärung), not just an
income-return line. The § 35 EStG credit (≈ 4× Messbetrag, capped at the
actual trade tax and at the income-tax share on Gewerbe income) flows
back into the income return. Hebesatz is a declared config value (like a
position) with the municipality cited.

### 3b. Umsatzsteuer (VAT)

**Authority.** UStG; **§ 19 UStG Kleinunternehmerregelung** — the 2025
thresholds changed under the Jahressteuergesetz 2024 (prior-year /
current-year limits — **VERIFY** the exact 2025 figures); standard 19 % /
reduced 7 % rates; Umsatzsteuer-Voranmeldung cadence.

**Design.** A **position** — Kleinunternehmer election (§ 19) vs.
Regelbesteuerung. Under Kleinunternehmer, no VAT is charged or filed
(the common freelancer case) — model it as an explicit `not_applicable`
VAT posture with the § 19 citation. Above the threshold, VAT becomes its
own periodic filing surface (Voranmeldung + Jahreserklärung) — a large,
separable workstream.

**Effort / risk.** ~3–4 weeks combined. High — two new filing surfaces,
municipality-specific config, periodic (not annual) VAT filings. Schedule
this only when a real Gewerbe / VAT-registered fixture exists.

---

## Phase 4 — Intake, facts pipeline & parsers

**Goal.** Let a non-lawyer enter all of the above through the wizard, with
the same plain-English + cited-tooltip standard (`docs/usability-standards.md`).

**Intake screens (new entries in `tax_pipeline/intake/screens.py`
`SCREEN_HANDLERS`).**
- `worker_type` selector on the Household/posture surface (employee /
  self-employed / both) — gates the rest.
- `business_profile` — § 18 vs § 15 sub-posture, Kleinunternehmer
  election, Hebesatz, Certificate of Coverage held.
- `euer` — the Einnahmenüberschussrechnung entry screen: revenue rows and
  categorized expense rows, mirroring the existing repeated-row screens
  (`children`, `bank_accounts`, `vorabpauschale`). One economic fact set
  feeds both Anlage S/EÜR and Schedule C.

**Posture registry (`tax_pipeline/intake/postures.py`).** New section
`SECTION_SELF_EMPLOYMENT` with the worker-type, § 18/§ 15, Totalization
coverage, Kleinunternehmer, and QBI/SSTB positions — each with the
plain-English tooltip + `(Legal: § X)` parenthetical the usability ratchet
requires.

**Facts / parsers.** Deterministic-first (`README.md` "Deterministic-First
Extraction"): CSV/accounting-export parsers for revenue & expense lines,
reusing the classifier's existing `receipts` / `expense_invoice` bucket
(`tax_pipeline/classify.py`). OCR/LLM only after deterministic extraction
is exhausted, with confidence + human-review markers
(`CLAUDE.md` fact rules).

**Stepper.** Add the new screens to the vertical stepper with status
badges (the polish-pass pattern), locked until a workspace is open.

**Effort / risk.** ~1–2 weeks (after Phases 1–2 define the fact shapes).
Medium — UI plumbing + parsers; the usability and label-inventory ratchets
apply.

---

## Cross-cutting: invariants & contracts every phase must hold

- **I1** — all new statutory constants (SECA factor exists; add § 199A
  thresholds, Gewerbesteuer Messzahl/Freibetrag, VAT rates) live only in
  `law/` modules; re-sign on every edit (A4 lock).
- **I3 / I11** — every new form line (Anlage S/G/EÜR, Schedule C, 8995,
  Gewerbesteuer) is declared in a schema and written via
  `legal_value_entry`; the AST audit rejects bare `format_currency`.
- **I4 / I7 / I8** — new rules read only declared `input_fact_keys`,
  write only declared `output_keys`, and fail closed on missing inputs
  (no silent zero — the highest-severity bug class here).
- **I12** — new narrative templates address inputs by key.
- **I13** — disabled postures (Totalization-exempt SE, Kleinunternehmer
  VAT, no-Gewerbe) emit explicit `not_applicable` artifacts with a
  citation-bearing reason, never zero-valued forms.
- **New-2 label inventory** — every new ELSTER/IRS form-line label is
  VERIFIED against the 2025 source PDF or moved into a form schema.
- **Null / zero / missing** — header-only EÜR = declared zero; absent =
  missing → fail closed; never collapse the three.

## Recommended sequencing

1. **Phase 0** (days) — correctness win for the most common case; ships alone.
2. **Phase 1 + 2** (the MVP, ~4–6 weeks) — a real Freiberufler return on
   both sides. Reuses one economic fact set across DE and U.S.
3. **Phase 4** (intake) — interleave with 1–2 as the fact shapes settle.
4. **Phase 3** (Gewerbe / VAT) — only when a trade-business or
   VAT-registered fixture exists; largest and most separable.

## Open questions to resolve before writing signed constants

- **VERIFY**: 2025 § 199A taxable-income thresholds + SSTB phaseout range
  (Rev. Proc.); whether the former treaty Art. 14 is fully folded into
  Art. 7 by the 2006 protocol; Gewerbesteuer Freibetrag/Messzahl 2025;
  the § 19 UStG Kleinunternehmer 2025 thresholds (changed by JStG 2024);
  the § 141 AO EÜR-vs-Bilanz thresholds; Anlage S/G/EÜR + Schedule C /
  Form 8995 2025 line numbers.
- A real (synthetic, public-safe) self-employed fixture for
  `years/demo-2025/` — none exists today, mirroring the child-handling
  gap noted in `README.md` § "Help wanted".

---

*This spec describes scope and structure only. Per the project's posture,
no number above should reach a form line until it is computed by a
deterministic, legally-cited rule and independently audited.*
