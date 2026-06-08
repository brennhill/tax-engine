# Germany 2025 Günstigerprüfung Shadow Audit (F-DE-2)

## Authority

- `§ 32d Abs. 6 EStG` (Antragsveranlagung — election to apply the § 32a tariff to capital income)
- `§ 32d Abs. 1 EStG` (the 25 % flat capital tax this election competes against)
- `§ 32a Abs. 1 EStG` (basic ordinary tariff)
- `§ 32a Abs. 5 EStG` (joint splitting tariff)
- `§ 32d Abs. 5 EStG` (foreign-tax credit; reads through under the election)
- BMF-Schreiben Abgeltungsteuer 14.05.2025 — Einzelfragen (Günstigerprüfung mechanics)
- Official URLs:
  - https://www.gesetze-im-internet.de/estg/__32d.html
  - https://www.gesetze-im-internet.de/estg/__32a.html
  - https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf?__blob=publicationFile&v=6

## What This Rule Governs

§ 32d Abs. 6 EStG (Antragsveranlagung) lets a taxpayer elect to apply the ordinary § 32a tariff to capital income when it produces a lower total tax than the § 32d Abs. 1 flat 25 %. The 2025 engine fails closed when `capital_guenstigerpruefung_requested=1` (the election is not yet implemented), but it gave no signal that the election would be favorable. F-DE-2 adds an audit-only shadow comparison so a low-bracket taxpayer is informed when they would benefit.

The shadow stage **does not** change the modeled refund. Its outputs are the diff and a recommendation flag, surfaced under `audit_warnings` in `germany-model-results.json` and as a row in `germany-model-trace.csv`.

## Inputs

- `de.audit.guenstiger.zve_ordinary_eur` — modeled `§ 2 Abs. 5 EStG` zu versteuerndes Einkommen
- `de.audit.guenstiger.capital_taxable_after_teilfreistellung_eur` — modeled `§ 20 Abs. 9 / InvStG § 20` capital base after Teilfreistellung and Sparer-Pauschbetrag
- `de.audit.guenstiger.status_quo_total_tax_eur` — modeled `§ 32d Abs. 1 + Abs. 5 + SolzG` capital tax (post-treaty)
- `de.audit.guenstiger.foreign_tax_credit_applied_eur` — `§ 32d Abs. 5 EStG` credit applied; carries through under the election
- `de.audit.guenstiger.filing_posture` — selects `§ 32a Abs. 1` vs `§ 32a Abs. 5` tariff variant

## Formula

1. `ordinary_only_tax = tariff(zvE_ordinary)`
2. `shadow_combined_tax = tariff(zvE_ordinary + capital_taxable)`
3. `shadow_capital_increment = max(0, shadow_combined_tax - ordinary_only_tax - foreign_tax_credit_applied)`
4. `diff = status_quo_total_tax - shadow_capital_increment`
5. `election_recommended = (diff > GUENSTIGERPRUEFUNG_MATERIALITY_EUR)`

## Ordering

This stage runs after `DE25-21-FINAL-CAPITAL-TAX` and `DE25-22-FINAL-REFUND` so the status-quo capital tax is the post-treaty total. The shadow does not feed any later stage.

## Rounding

- cent precision via `q2`; the `§ 32a` tariff itself uses `floor_euro` per `BMF Programmablaufplan 2025`
- the materiality threshold is `€10` (project-internal, see `GUENSTIGERPRUEFUNG_MATERIALITY_EUR`)

## Edge Cases

- zero capital income → diff = 0, election_recommended = 0
- ordinary tariff at top rate (`§ 32a Abs. 1` Spitzensteuer ≥ 25 %) → diff is typically negative; election_recommended = 0
- low brackets where the entire combined `zvE` is in the Grundfreibetrag → tariff returns 0 on both sides, diff = full status-quo capital tax, election_recommended = 1 if status-quo > €10

## Ambiguities / Filing Positions

This is an audit-only diagnostic; the engine still fails closed when the election is requested. The recommendation does not constitute legal advice — the taxpayer must execute the election manually in ELSTER and the engine will need a future implementation of the `§ 32a` capital path before this can be filed automatically.

## Implemented By

- `tax_pipeline/y2025/germany_stages.py` (DE25-GUENSTIGERPRUEFUNG-SHADOW LawStage declaration)
- `tax_pipeline/y2025/germany_guenstigerpruefung_rules.py` (rule body)
- `tax_pipeline/pipelines/y2025/germany_model.py` (orchestrator wiring; trace row)

## Test Coverage

- `tests/test_de25_guenstigerpruefung_shadow.py`

## Outputs Affected

- `guenstigerpruefung_shadow_diff` (trace row)
- `de.audit.guenstigerpruefung_shadow_diff_eur`
- `de.audit.guenstigerpruefung_election_recommended`
