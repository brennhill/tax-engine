# Germany Legal Audit Design

## Goal

Make the 2025 Germany calculation auditable by a non-tax professional by:

- computing the mechanical parts directly from structured facts,
- citing official legal sources at each step,
- showing the statutory order of operations explicitly,
- isolating judgment-based positions as explicit manual tax positions instead of hidden approximations.

## Scope

This design applies to the Germany 2025 calculation path only.

In scope:

- wage-side Germany tax computation,
- exact integration of work-expense deductions into the wage-side computation,
- exact treatment of `§ 22 Nr. 3 EStG` staking income in the regular tariff path,
- preservation of separate `§ 32d EStG` / `InvStG` capital-tax treatment,
- code comments linking to official sources,
- audit traces and tests that prove the computation order.

Out of scope:

- replacing the saved treaty-credit position with a new treaty engine,
- redesigning the U.S. pipeline,
- building a generic multi-year Germany rule engine.

## Required Outcome

The Germany model must stop depending on:

- imported `zero_capital_refund_no34_eur`,
- imported marginal tax approximations for equipment and staking income.

Instead, it must:

1. derive wage-side inputs from source facts,
2. compute deductions in the order required by the EStG,
3. compute taxable ordinary income and splitting-tariff tax directly,
4. add exact wage-side withholding / prepayment credits,
5. add the separate capital-tax layer,
6. add explicit manual tax positions only where the law is not purely mechanical.

## Calculation Boundary

The calculation will be split into two classes of inputs:

### Mechanical legal inputs

These can be computed directly from facts and law:

- wages from `Lohnsteuerbescheinigung`,
- wage tax and solidarity surcharge withheld,
- employee pension contributions,
- employee health and nursing contributions,
- statutory `Arbeitnehmer-Pauschbetrag`,
- statutory `Sonderausgaben-Pauschbetrag`,
- home-office Tagespauschale from configured day counts,
- telecom simplification amount from configured monthly spend,
- exact `§ 32a EStG` splitting tariff,
- exact `§ 22 Nr. 3 EStG` threshold handling,
- exact wage-side refund/balance arithmetic.

### Manual tax positions

These remain explicit model positions because the law requires factual or classification judgment beyond a pure formula:

- treaty dividend credit,
- legal-insurance deductible employment share,
- cross-border tax-preparation deductible share,
- Aktienfonds / non-Aktienfonds classification,
- any equity-comp basis inference already modeled outside the wage-side tariff logic.

These manual positions must remain visible in structured tax-position inputs with notes and legal references.

## Legal Order

The code and trace must reflect this order:

1. collect ordinary-income source facts,
2. compute Werbungskosten per person,
3. apply `§ 9a EStG` floor per person,
4. derive Einkünfte aus nichtselbständiger Arbeit,
5. sum ordinary-income components including `§ 22 Nr. 3`,
6. compute Gesamtbetrag der Einkünfte,
7. subtract deductible `§ 10 EStG` amounts and `§ 10c EStG` items where applicable,
8. derive `zu versteuerndes Einkommen`,
9. compute joint tariff tax under `§ 32a Abs. 5 EStG`,
10. compute solidarity surcharge on the ordinary-tax side,
11. add the separate capital-tax side under `§ 32d EStG` / `InvStG`,
12. subtract withholding/prepayments/credits under `§ 36 EStG`,
13. surface remaining manual tax positions separately.

## Data Changes

The facts layer must expose wage-certificate lines needed for exact Germany tariff computation:

- line 3 gross wage,
- line 4 wage tax,
- line 5 solidarity surcharge,
- line 10 multiannual wage,
- line 22 employer pension share,
- line 23 employee pension share,
- line 24 employer health/pflege subsidies where present,
- line 25 employee health insurance,
- line 26 employee nursing insurance,
- line 27 employee unemployment insurance.

Manual deduction inputs that are not document-native should be represented as explicit config/tax-position facts, not hidden constants in analysis notes.

## Audit Surface

The generated Germany trace must show:

- each calculation step,
- numeric value,
- legal reference,
- official URL,
- why the step occurs in that order,
- whether the step is mechanical or a manual tax position.

The final audit summary should explicitly name any remaining manual positions.
