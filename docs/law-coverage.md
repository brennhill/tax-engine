# Law Coverage — 2025 DE/US Cross-Border Tax Engine

This document maps every potentially-applicable statute and treaty article to
the engine stage that implements it, or to an explicit "out of scope" reason.
It is a contract: every entry must point to a real stage ID or carry a
fail-closed gate that triggers when input facts imply the statute should
apply.

CLAUDE.md says: "If a legal source is unclear, year-specific, conflicting,
missing, or not yet modeled, fail closed with an explicit error or
`not_applicable`; never silently default to zero." Items marked
**OUT OF SCOPE** below must have a fail-closed gate; items marked
**OUT OF SCOPE (no triggering facts)** apply only when input data implies
the statute, in which case the engine must fail closed.

---

## Germany — Einkommensteuergesetz (EStG)

| Statute | URL | Stage / handling | Status |
| --- | --- | --- | --- |
| § 2 Abs. 2 / Abs. 3 / Abs. 5 EStG (Einkünfte / zvE) | https://www.gesetze-im-internet.de/estg/__2.html | DE25-03, DE25-07 | IN SCOPE |
| § 3 Nr. 62 EStG (employer-share carve-out) | https://www.gesetze-im-internet.de/estg/__3.html | DE25-05 | IN SCOPE |
| § 4 Abs. 5 Satz 1 Nr. 6c EStG (home office Tagespauschale) | https://www.gesetze-im-internet.de/estg/__4.html | DE25-02 | IN SCOPE |
| § 9 / § 9a EStG (Werbungskosten / Pauschbetrag) | https://www.gesetze-im-internet.de/estg/__9.html | DE25-02 | IN SCOPE |
| § 10 Abs. 1 Nr. 2 / Abs. 3 EStG (retirement Vorsorge) | https://www.gesetze-im-internet.de/estg/__10.html | DE25-05 | IN SCOPE |
| § 10 Abs. 1 Nr. 3 / Abs. 4 EStG (health/Vorsorge) | https://www.gesetze-im-internet.de/estg/__10.html | DE25-06 | IN SCOPE |
| § 10c EStG (Sonderausgaben-Pauschbetrag) | https://www.gesetze-im-internet.de/estg/__10c.html | DE25-06B | IN SCOPE |
| § 19 Abs. 1 EStG (employment income) | https://www.gesetze-im-internet.de/estg/__19.html | DE25-01 | IN SCOPE |
| § 20 Abs. 2 / Abs. 6 / Abs. 9 EStG (capital income) | https://www.gesetze-im-internet.de/estg/__20.html | DE25-13 / DE25-15 / DE25-16 | IN SCOPE |
| § 22 Nr. 3 EStG (other income / Freigrenze) | https://www.gesetze-im-internet.de/estg/__22.html | DE25-04 | IN SCOPE |
| § 25 EStG (Veranlagungspflicht) | https://www.gesetze-im-internet.de/estg/__25.html | DE25-FACTS (narrative) | IN SCOPE |
| § 26 / § 26a / § 26b EStG (Veranlagungsart) | https://www.gesetze-im-internet.de/estg/__26.html | DE25-00 | IN SCOPE |
| § 32a Abs. 1 / Abs. 5 EStG (Tarif / Splittingtarif) | https://www.gesetze-im-internet.de/estg/__32a.html | DE25-08 | IN SCOPE |
| § 32d Abs. 1 EStG (Abgeltungsteuer 25 %) | https://www.gesetze-im-internet.de/estg/__32d.html | DE25-17 | IN SCOPE |
| § 32d Abs. 5 EStG (per-Posten FTC) | https://www.gesetze-im-internet.de/estg/__32d.html | DE25-18 | IN SCOPE |
| § 32d Abs. 6 EStG (Günstigerprüfung) | https://www.gesetze-im-internet.de/estg/__32d.html | `germany_model.ensure_capital_guenstigerpruefung_position_2025` | OUT OF SCOPE — fail-closed gate; profile must elect 0 |
| § 33 EStG (außergewöhnliche Belastungen) | https://www.gesetze-im-internet.de/estg/__33.html | None | OUT OF SCOPE (no triggering facts) — manual position required if claimed |
| § 35a EStG (haushaltsnahe Dienstleistungen) | https://www.gesetze-im-internet.de/estg/__35a.html | None | OUT OF SCOPE (no triggering facts) |
| § 36 Abs. 2 / Abs. 3 EStG (Anrechnungen) | https://www.gesetze-im-internet.de/estg/__36.html | DE25-10 | IN SCOPE (ordinary side); capital-side KESt crediting handled in `germany_model.py` orchestrator |
| § 51a EStG (Kirchensteuer / Solidaritätszuschlag) | https://www.gesetze-im-internet.de/estg/__51a.html | `germany_2025_inputs._required_germany_kirchensteuer_membership` | OUT OF SCOPE — fail-closed gate; profile must declare `germany_kirchensteuer_membership: "none"` |

## Germany — Solidaritätszuschlaggesetz (SolzG)

| Statute | URL | Stage / handling | Status |
| --- | --- | --- | --- |
| § 3 SolzG (Freigrenze) | https://www.gesetze-im-internet.de/solzg_1995/__3.html | DE25-09 (ordinary), DE25-19 (capital) | IN SCOPE |
| § 4 SolzG (Rate, Milderungszone) | https://www.gesetze-im-internet.de/solzg_1995/__4.html | DE25-09, DE25-19, DE25-21 | IN SCOPE |

## Germany — Investmentsteuergesetz (InvStG)

| Statute | URL | Stage / handling | Status |
| --- | --- | --- | --- |
| InvStG § 16 / § 19 / § 20 (fund classification) | https://www.gesetze-im-internet.de/invstg_2018/__16.html | DE25-13 | IN SCOPE |
| InvStG § 20 (Teilfreistellung) | https://www.gesetze-im-internet.de/invstg_2018/__20.html | DE25-14 | IN SCOPE |
| InvStG § 21 (Verlustabzugsverbot) | https://www.gesetze-im-internet.de/invstg_2018/__21.html | DE25-14 | IN SCOPE |

---

## United States — Internal Revenue Code (Title 26 USC)

| Statute | URL | Stage / handling | Status |
| --- | --- | --- | --- |
| 26 U.S.C. § 1 / § 1(h) (ordinary + preferential rates) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1 | US25-09, US25-06 | IN SCOPE |
| 26 U.S.C. § 55-59 (AMT) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section55 | None | OUT OF SCOPE (no triggering facts) — should fail closed when AMTI > exemption |
| 26 U.S.C. § 61 (gross income) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section61 | US25-02, US25-07 | IN SCOPE |
| 26 U.S.C. § 63 (taxable income) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section63 | US25-08 | IN SCOPE |
| 26 U.S.C. § 901 (FTC eligibility) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901 | US25-13, US25-14 | IN SCOPE (accrued only; paid timing fails closed) |
| 26 U.S.C. § 904 (FTC limitation) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section904 | US25-10 through US25-14 | IN SCOPE |
| 26 U.S.C. § 905 (paid/accrued election) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905 | `us_2025_inputs.load_us_assessment_inputs_2025` | OUT OF SCOPE — fail-closed if `us_ftc_method=paid` |
| 26 U.S.C. § 911 (Foreign Earned Income Exclusion) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911 | `us_2025_inputs.load_us_assessment_inputs_2025` | OUT OF SCOPE — fail-closed if `elect_section_911_feie=true` |
| 26 U.S.C. § 1211(b) (capital loss cap) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1211 | US25-05 | IN SCOPE |
| 26 U.S.C. § 1212 (capital loss carryforward) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1212 | US25-05 | IN SCOPE (consume only); year-end carryforward output not yet emitted as a declared fact |
| 26 U.S.C. § 1256 (60/40 mark-to-market) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1256 | US25-04 | IN SCOPE |
| 26 U.S.C. § 1401-1403 (self-employment tax) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401 | None | OUT OF SCOPE (no triggering facts) — should fail closed if Schedule C income present |
| 26 U.S.C. § 1411 (NIIT) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1411 | US25-20 | IN SCOPE (no § 911 add-back required because § 911 fails closed; PFIC / CFC inclusions out of scope) |
| 26 U.S.C. § 3101(b)(2) (Additional Medicare Tax 0.9 %) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101 | `us_2025_inputs.load_us_assessment_inputs_2025` | OUT OF SCOPE — Totalization Agreement makes German-employer wages exempt; fail-closed if `acknowledges_totalization_agreement_germany_us=false` or any U.S.-source Medicare-taxable wages present |
| 26 U.S.C. § 6012 (filing threshold) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6012 | US25-FACTS (narrative); enforced by income-side stages | IN SCOPE |
| 26 U.S.C. § 6013(g)/(h) (NRA spouse joint election) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6013 | `us_2025_inputs.load_us_assessment_inputs_2025` | IN SCOPE — explicit profile election required |
| 26 U.S.C. § 6654 (estimated-tax penalty) | https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6654 | None | OUT OF SCOPE (assessment-only) |

---

## U.S.–Germany Treaty (DBA-USA)

The treaty technical explanation lives at https://www.irs.gov/pub/irs-trty/germtech.pdf
and IRS Pub. 514 worksheet at https://www.irs.gov/publications/p514.

| Article | Topic | Stage / handling | Status |
| --- | --- | --- | --- |
| Art. 10 | Portfolio dividends — 15 % source-country cap | DE25-15, DE25-20, US25-15, TREATY25-15 | IN SCOPE |
| Art. 11 | Interest — generally 0 % source | None — engine assumes residence-only taxation | OUT OF SCOPE (no triggering facts) — should fail closed if U.S.-source interest present |
| Art. 12 | Royalties | None | OUT OF SCOPE (no triggering facts) |
| Art. 13 | Capital gains | None — engine assumes residence-state taxation | OUT OF SCOPE (no triggering facts) |
| Art. 18 | Pensions | None | OUT OF SCOPE (no triggering facts) — should fail closed if pension distributions present |
| Art. 19 | Government service | None | OUT OF SCOPE (no triggering facts) |
| Art. 20 | Students / teachers | None | OUT OF SCOPE (no triggering facts) |
| Art. 23 | Methods (residence-state credit) | DE25-18 (routed via § 32d Abs. 5 EStG); fail-closed gate at DE25-20 prevents standalone treaty credit | IN SCOPE |
| Art. 28 | Limitation on Benefits (LOB, as amended by the 2006 Protocol) | LOB qualification category enforced in treaty_law.py (Art. 28(2)(a) qualified-resident — individual) | IN SCOPE — a treaty position must declare its Art. 28 qualifying category |

## U.S.–Germany Totalization Agreement (Social Security)

URL: https://www.ssa.gov/international/Agreement_Pamphlets/germany.html

| Topic | Engine handling | Status |
| --- | --- | --- |
| German-employer wages exempt from U.S. FICA / Medicare | `us_2025_inputs.load_us_assessment_inputs_2025` requires `acknowledges_totalization_agreement_germany_us=true` | IN SCOPE — explicit acknowledgment + fail-closed if U.S.-source Medicare-taxable wages present |

---

## Cross-jurisdiction bridge keys

The treaty and U.S. graphs reference DE-side facts that are produced by the
DE rule graph plus a typed conversion in `treaty_bridge_2025.py`. These are
the bridge fact keys (currently produced outside the validated stage graph):

| Key | Producer | Consumers |
| --- | --- | --- |
| `de.stage.us_source_dividend_tax_and_credit` | `treaty_bridge_2025.convert_germany_treaty_dividend_items_to_us_2025` | US25-17 |
| `de.treaty.us_source_dividend_tax_and_credit` | `treaty_initial_facts_2025` | TREATY25-17 |
| `us.treaty.inputs` | `treaty_initial_facts_2025` | TREATY25-* |
| `treaty.dividend_split` | `treaty_initial_facts_2025` | TREATY25-15 |
| `us.constants.treaty_dividend_rate` | `treaty_initial_facts_2025` | TREATY25-16 |
| `us.stage.regular_tax_after_ftc` | derived from US25-19 | TREATY25-18 |
| `us.stage.remaining_form_1116_line_33_cap` | derived from US25-19 | TREATY25-18 |

A future refactor (item 4 of the review punch list) should promote this
bridge to a first-class `LawStage` so the union DE+US+treaty graph
validates with no implicit facts.

---

## Coverage tests

The following tests pin the contract above:

- `tests/y_agnostic/test_law_stage_graph.py::test_union_law_stage_graph_validates`
  asserts that the union of DE+US+treaty stages validates when supplied
  with the documented set of initial facts plus the bridge keys above.
  If a future refactor adds a new stage or renames a key without updating
  the bridge-keys list, the test fails.

- `tests/y2025/test_us_law.py::test_section_911_election_required_in_profile`
  and friends pin the fail-closed gates listed above.
