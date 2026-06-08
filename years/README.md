# Year Workspaces

This public repo does not ship with any real taxpayer data.

- `years/demo-2025/`
  Synthetic example workspace used to show the intended folder layout.
- `~/taxes/<year>/`
  Default location for your own private real-filing workspace.

Use:

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.scaffold_year 2026
python3 -m tax_pipeline.run_year 2026
```

If you do not want the default location, pass:

```bash
--workspace /custom/path
```

Do not commit real tax documents, config, normalized facts, or generated outputs to this repo.
