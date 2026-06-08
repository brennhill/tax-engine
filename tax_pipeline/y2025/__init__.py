# Year-2025 legal-core package.
#
# Naming convention (as of P1, the year-namespace refactor):
#
#   * `us_*` for legal-core modules under this package — `us_law.py`,
#     `us_stages.py`, `us_rules.py`, `us_inputs.py`, and
#     `derivation/us_derivations.py`. The `us_` prefix matches the rest of
#     the legal-core module set (ISO-3166 alpha-2 style: `de_*`, `us_*`).
#   * `forms/usa.py` and `legal_audit/usa.py` retain the `usa` spelling at
#     `tax_pipeline/forms/` and `tax_pipeline/legal_audit/`. These modules
#     were not in P1's scope (they are year-agnostic by path); convergence
#     to a single `us` / `usa` spelling across the codebase is a Phase-2
#     follow-up item.
#
# Keep this `__init__.py` free of re-exports. Per the P1 contract, every
# import site should refer to the concrete module under `tax_pipeline.y2025`
# (e.g. `from tax_pipeline.y2025 import us_law`) so the year-namespace
# boundary stays inspectable in `grep` and import-graph tools.
