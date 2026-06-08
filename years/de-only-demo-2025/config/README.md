# Workspace Config

The local intake wizard (`tax-pipeline-intake`, served at
`http://127.0.0.1:8765`) is the canonical input surface for this
workspace. All filing choices (household, postures, payments, elections,
identity, bank accounts, deductions, children, ...) should be entered
through the wizard, which writes the synchronized files in this folder.

The CSV / JSON files here are **an export and audit format**, not the
hand-edit surface. They are still human-readable so a reviewer can
diff them against the wizard's state, but editing them directly risks
column-shift errors and boolean-typo errors that propagate silently
into the rule graph.

If you must edit a file directly (e.g. to recover a corrupted wizard
session), run `tax-pipeline-validate <year>` afterward — it now flags
boolean columns that contain anything other than the literal strings
`true` / `false`.

## Recommended workflow

1. `tax-pipeline-intake` — start the wizard (entry point, served at
   `http://127.0.0.1:8765`).
2. Walk through the wizard's screens; the wizard writes
   `config/people.csv`, `config/payments.csv`, `config/elections.csv`,
   `config/children.csv`, `config/profile.json`, and
   `config/manual_overrides.json` as you go.
3. `tax-pipeline-validate <year>` — confirm the workspace is ready.
4. `tax-pipeline-run <year>` — run the pipeline. (The wizard's "Run
   pipeline" button does the same thing.)

## Raw document layout (Proposal 8)

Source documents live one level up under `raw/`. As of the Proposal 8
raw-bucket redesign (architecture review 2026-05-04), `raw/` is
organised along two independent dimensions:

```
raw/
  jurisdictions/
    de/        # German-side documents (Lohnsteuerbescheinigung,
               # Steuerbescheid, Anlage attachments, ...)
    us/        # U.S.-side documents -- empty in the DE-only demo
               # because the U.S. pathway is disabled.
  asset_classes/
    brokers/        # Schwab/IBKR 1099s and transaction CSVs
    crypto/         # Coinbase/Binance year-end summaries
    equity_comp/    # RSU / ESPP grants and Shareworks statements
    receipts/       # Donation EMLs, Werbungskosten invoices
    real_estate/    # Closing statements, mortgage interest
```

The wizard's upload flow routes each document into the right bucket
automatically; if you drop a file in by hand, place jurisdiction-bound
documents under `raw/jurisdictions/<iso>/...` and cross-jurisdiction
asset documents under `raw/asset_classes/<class>/...`.

The legacy flat layout (`raw/germany/`, `raw/us/`, `raw/brokers/`,
...) is still readable -- the runtime falls back to it transparently
so older workspaces keep working. To convert a workspace from the
legacy layout to the canonical one, run:

```
tax-pipeline-migrate-buckets <workspace>            # dry-run
tax-pipeline-migrate-buckets <workspace> --apply    # copy files
tax-pipeline-migrate-buckets <workspace> --apply --remove-legacy
```

The helper is non-destructive by default (it copies, leaving the
legacy tree intact) and idempotent (re-running on an already-migrated
workspace is a no-op). `--remove-legacy` deletes the legacy bucket
directories after a successful copy.

## Demo posture: DE-only opt-out

This folder ships a public-safe synthetic config for the
`de-only-demo-2025` workspace, which exercises the
`elections.us_filing_required=false` opt-out under 26 U.S.C. § 6012.
The U.S. side is intentionally turned off here so the test suite can
verify the I13 invariant — when the user opts out of the U.S.
pathway, the engine emits no U.S. forms / legal-audit packets while
the German pipeline still runs end-to-end.

In a real private workspace the same files live under
`~/taxes/<year>/config/`. The wizard will create that path
automatically when you click "Create workspace".

Before entering real filing choices, also read the repo documentation:

- `README.md` (project root)
- `docs/support-matrix.md`
- `docs/provider-support.md`

## Reference: CSV column reference (read-only)

The columns below are documented for audit / review purposes only.
Treat them as read-only — use the wizard to make changes.

- `people.csv` — one row per assessed person (taxpayer, spouse). Boolean
  columns: `us_filer`, `is_taxpayer`, `is_spouse`, `nra_for_us_return`,
  `german_statutory_health_with_sick_pay`, `church_tax_applicable`. All
  boolean cells must be the literal string `true` or `false`; any other
  value (including `True`, `yes`, `1`, or a typo like `ture`) is
  rejected by `tax-pipeline-validate`.
- `payments.csv` — one row per estimated-tax / withholding payment.
  Columns: `jurisdiction`, `person_id`, `payment_type`, `amount`,
  `currency`, `source`, `note`.
- `elections.csv` — one row per `(jurisdiction, key)` posture choice.
  Boolean keys (where `value` must be `true` / `false`): `enabled`,
  `use_treaty_resourcing`, `elect_joint_return_with_nra_spouse`,
  `us_filing_required`. The DE-only demo sets
  `(usa, us_filing_required, false)` to disable the U.S. pathway under
  26 U.S.C. § 6012.
- `children.csv` — one row per child for § 31 EStG / § 32 Abs. 6 EStG
  / 26 U.S.C. § 24 / § 152 (Familienleistungsausgleich + CTC / ODC).
- `profile.json` — engine-facing derived config; the wizard keeps it
  synchronized with the CSV files.
- `manual_overrides.json` — engine-facing escape hatch for cases the
  CSV / wizard surface does not yet model.
