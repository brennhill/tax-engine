"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 11 (Zinsen / Interest)
url: https://www.irs.gov/pub/irs-trty/germany.pdf
contains:
  - DBA-USA Art. 11(1): interest paid to a resident of the other state is
    taxable only in that residence state (i.e. 0 % source-state rate). The
    2006 Protocol kept the bilateral 0 % rate in place; specific exceptions
    (contingent / equity-linked interest) are governed by Art. 11(5).
    Cited only — see scope note below.
numeric_constants: []  # see scope note
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20)
audited_by: claude-opus-4-7
audited_on: 2026-05-11
audit_hash: sha256:8fae3f6b249fdf47378af00929a32fbeab0b7c1d4cee33dfe5317c107ddecbe7
---
"""
# Shadow extraction of DBA-USA Art. 11 (Phase 5 treaty article). The 2025
# engine does not currently emit treaty-eligible interest positions, so
# the Article appears here as cite-only.
#
# Scope note (W1.A / T1.1, 2026-05-11): the Art. 11(1) 0 % source-state
# interest rate constant (``DBA_USA_ART_11_INTEREST_RATE``) was removed
# from ``art11.toml`` and from this sidecar because no working-tree
# rule consumed it (it was flagged as an orphan by the New-1 verifier).
# The citation URLs below remain so the Article is still registered as
# an authority surface; when a future return adds a treaty-interest
# pathway, declare the rate in ``art11.toml`` and wire it into the rule
# that applies it.
from __future__ import annotations

# DBA-USA Art. 11 authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_11_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"
