"""
---
jurisdiction: US
tax_year: 2025
statute: 26 U.S.C. § 152 (Dependent defined)
url: https://www.law.cornell.edu/uscode/text/26/152
contains:
  - § 152(c): qualifying child (relationship, age, residency, support,
    joint-return tests)
  - § 152(d): qualifying relative (relationship, gross-income, support tests)
  - For a U.S.-citizen-in-Germany filer, § 152(c)(1)(B) treats months
    living abroad with a U.S.-citizen parent as months "with the
    taxpayer," so ``USChild2025.months_in_us_household`` measures shared
    residency with the taxpayer, NOT months physically inside the
    United States.
  - The classification function ``_classify_child_2025`` lives at the
    loader (``tax_pipeline/y2025/us_inputs.py``) rather than at the law
    layer, so this file is cite-only at the law boundary.
numeric_constants: []
amended_by: []
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:f65b2911b1455460916929d63251c86918dbcbcee8392f6ae5bc9fc5b2313154
---
"""
# Shadow extraction of § 152 citation surface (Phase 2 leaf §). Mirrors
# ``tax_pipeline.y2025.us_law``: § 152 is consumed by § 24 (CTC qualifying
# child test) and the loader's ``_classify_child_2025`` boundary check;
# no math helper directly bound to § 152 lives in the law module.
#
# Authority: 26 U.S.C. § 152 — qualifying child (§ 152(c)) / qualifying
# relative (§ 152(d)). Cited by § 24 (CTC) and by Schedule 8812 (2025)
# instructions.
# https://www.law.cornell.edu/uscode/text/26/152
from __future__ import annotations

USC_152_URL = "https://www.law.cornell.edu/uscode/text/26/152"

__all__ = ("USC_152_URL",)
