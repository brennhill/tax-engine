# Demo Year Workspace

`demo-2025` is a fully synthetic, runnable workspace for the public repo.

It demonstrates a single-person cross-border case:

- one dual-national taxpayer
- Germany filing posture: `single`
- U.S. filing posture: `single`
- German wage income with stock compensation embedded in payroll
- one German prepayment and one U.S. estimated payment
- U.S. broker dividends plus a small set of stock sales
- FTC and treaty re-sourcing exercised without spouse-specific paths

This workspace is meant to be copied into a numeric year tree with:

```bash
python3 -m tax_pipeline.demo_workspace --project-root . --year 2025
python3 -m tax_pipeline.run_year 2025
```

Layout:

- `raw/`
- `config/`
- `normalized/`
- `outputs/`

Everything in this workspace is synthetic and public-safe.
