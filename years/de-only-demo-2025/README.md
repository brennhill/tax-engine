# DE-Only Demo Year Workspace

`de-only-demo-2025` is a fully synthetic, runnable workspace for the
public repo demonstrating the `elections.us_filing_required=false`
opt-out path (26 U.S.C. § 6012).

It demonstrates a single-person Germany-only case:

- one non-American German resident (no U.S. citizenship, no green card,
  no other U.S. filing obligation)
- Germany filing posture: `single`
- U.S. pathway disabled at the engine boundary
- German wage income with stock compensation embedded in payroll
- one German prepayment, no U.S. estimated payment
- U.S.-source dividends are still credited under § 32d Abs. 5 EStG
  per-Posten cap and DBA-USA Art. 10/23 inside the German return
- no Form 1040 / 1116 / 2555 / 6251 / 8959 / Schedule B / D / SE
  rendering; no `us-tax-package.json`; no `BRIDGE25-FOREIGN-TAX-RECONCILIATION`
  stage executes

Authority:

- 26 U.S.C. § 6012 — Persons required to make returns of income
  https://www.law.cornell.edu/uscode/text/26/6012
- § 32d Abs. 5 EStG — per-Posten foreign-tax credit cap
  https://www.gesetze-im-internet.de/estg/__32d.html
- DBA-USA 1989 Art. 10 / 23 — German residence-state credit on
  U.S.-source portfolio dividends
  https://www.irs.gov/pub/irs-trty/germany.pdf
- InvStG § 2 / § 19 / § 20 — fund taxation regime
  https://www.gesetze-im-internet.de/invstg_2018/

This workspace is meant to be copied into a numeric year tree with:

```bash
python3 -m tax_pipeline.demo_workspace --project-root . --year 2025 --demo-name de-only-demo-2025
python3 -m tax_pipeline.run_year 2025
```

Layout:

- `config/`
- `normalized/`
- `outputs/`

Everything in this workspace is synthetic and public-safe.
