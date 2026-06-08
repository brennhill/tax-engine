"""
---
jurisdiction: TREATY
treaty: DBA-USA (Germany–United States Convention for the Avoidance of Double Taxation, Income and Capital, signed 1989, amended 2006 Protocol)
tax_year: 2025
statute: DBA-USA Art. 17 (Renten / Pensions)
url: https://www.irs.gov/pub/irs-trty/germany.pdf
contains:
  - DBA-USA Art. 17(1): private pensions paid to a resident of the other
    state are taxable only in that residence state
  - DBA-USA Art. 17(2): government / public-sector pensions remain in the
    paying state's tax jurisdiction (with carve-outs for residents who are
    citizens of the other state)
  - DBA-USA Art. 17(3): social-security payments (e.g. U.S. Social
    Security, German gesetzliche Rente) are taxable only in the
    residence state
amended_by:
  - 2006 Protocol amending DBA-USA (Senate Treaty Doc. No. 109-20)
audited_by: claude-opus-4-7
audited_on: 2026-05-03
audit_hash: sha256:53810e64045aae64a2f1afd1771f7424c67fc7ec0ede4790bf022a67781c85d6
---
"""
# Shadow extraction of DBA-USA Art. 17 (Phase 5 treaty article). The 2025
# engine does not currently model pension positions for the demo
# workspace, so this Article appears as cite-only — the audit surface
# carries the URL and the contained-paragraphs frontmatter so a Phase 8
# audit packet has the citation even when no numeric output flows
# through the article.
from __future__ import annotations

# DBA-USA Art. 17 authority URL (IRS-hosted bilingual treaty text).
DBA_USA_ART_17_URL = "https://www.irs.gov/pub/irs-trty/germany.pdf"
