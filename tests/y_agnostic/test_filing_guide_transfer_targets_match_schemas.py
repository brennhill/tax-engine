"""Y2 / P5 Phase 4 — filing-guide transfer-target keys must match schema labels.

The FILING-GUIDE.md generator (``tax_pipeline/forms/filing_guide.py``)
references rendered ``Line`` cells from the per-form Markdown by literal
string (e.g., ``"Line 8z total"`` → ``"→ Form 1040 Line 8 (via Schedule 1
line 10 total)"``). Those keys must agree byte-for-byte with the
schema-driven labels emitted by the per-form renderer. After Phase 2 of
the form-schema-as-data refactor those labels live in
``tax_pipeline/forms/schemas/<form_id>.toml``; if a 2026 schema relabels
a line ("Line 16" → "Line 16a") the transfer_targets key would silently
miss without a paired update here.

This test catches that drift class. Per the same convention as the
strengthened I3 check (Phase 3): the cross-check fires only for forms
whose basename maps to a known schema; forms whose basename is not
declared as a schema fall back to the previous unchecked posture.

Authority for transfer-line bookkeeping:
- IRS Form 1040 instructions (2025): https://www.irs.gov/instructions/i1040gi
- ELSTER Hilfe / BMF Anlage instructions (2025):
  https://www.elster.de/eportal/helpGlobal
"""
from __future__ import annotations

import re
import unittest

from tax_pipeline.forms._schema import iter_schema_form_ids, load_form_schema
from tax_pipeline.forms.filing_guide import GERMANY_FORMS, USA_FORMS


_BASENAME_RE = re.compile(r"^\d{4}_(?P<form_id>[A-Za-z0-9_]+)\.md$")


def _basename_to_form_id(basename: str) -> str | None:
    """Return the schema form_id matching a rendered Markdown basename.

    ``"2025_schedule_8812.md"`` → ``"schedule_8812"``. ``"2025_1040.md"``
    is the special case the U.S. renderer uses for the main return; we
    map it explicitly to ``"form_1040"`` to match the schema filename.
    Anything else returns the bare ``<form_id>`` extracted from the
    filename, which we then test for schema existence.
    """
    if basename == "2025_1040.md":
        return "form_1040"
    match = _BASENAME_RE.match(basename)
    if match is None:
        return None
    return match.group("form_id")


class FilingGuideTransferTargetsMatchSchemasTest(unittest.TestCase):
    """Phase 4 — every transfer_targets key in filing_guide.py must
    match a label in the corresponding form's schema.
    """

    def test_every_transfer_target_key_matches_a_schema_label(self) -> None:
        schema_form_ids = set(iter_schema_form_ids())
        offenders: list[str] = []
        for spec_set, set_name in (
            (USA_FORMS, "USA_FORMS"),
            (GERMANY_FORMS, "GERMANY_FORMS"),
        ):
            for spec in spec_set:
                form_id = _basename_to_form_id(spec.basename)
                if form_id is None or form_id not in schema_form_ids:
                    # Form does not have a schema yet — older posture.
                    continue
                schema = load_form_schema(form_id)
                if not schema.lines:
                    # Dynamic-lines schema (Schedule D, Form 8949): the
                    # rendered table comes wholly from runtime JSON / CSV
                    # data, so the transfer_targets keys reference data
                    # labels rather than schema labels. Skip the cross-
                    # check for these — the schema has nothing to enforce
                    # against.
                    continue
                schema_labels = {line.label for line in schema.lines}
                for key in spec.transfer_targets.keys():
                    if key not in schema_labels:
                        offenders.append(
                            f"  - {set_name} basename={spec.basename!r} "
                            f"transfer_targets key {key!r} does not match "
                            f"any label in schema {form_id!r}. Schema "
                            f"labels: {sorted(schema_labels)!r}"
                        )
        if offenders:
            self.fail(
                "Y2 / P5 Phase 4: filing-guide transfer_targets keys must "
                "match schema-declared labels (the rendered Markdown "
                "Line cell). When a schema relabels a line, the matching "
                "filing_guide.py transfer_targets entry must be updated "
                f"in the same commit. {len(offenders)} mismatch(es):\n"
                + "\n".join(offenders)
            )


if __name__ == "__main__":
    unittest.main()
