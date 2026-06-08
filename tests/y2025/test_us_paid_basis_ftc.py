"""§ 905(a) paid-basis FTC posture (Workstream 3).

Authority:
- 26 U.S.C. § 901 — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901
- 26 U.S.C. § 904(c) — carryforward / carryback rules.
- 26 U.S.C. § 905(a) — https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905

The default § 901 timing is accrued (FTC for foreign taxes accrued
during the tax year). § 905(a) lets the taxpayer elect cash/paid-basis
timing instead, binding for that year and every subsequent year until
revoked. Workstream 3 of the 2026-05-01 USA legal-flow review fills
the paid-basis posture gap that was a NotImplementedError in
``tax_pipeline/y2025/us_inputs.py``.

The legal arithmetic still uses available foreign tax (current +
carryover) under both timings; the difference is what counts as
"current-year" foreign tax — cash-basis filers count only foreign tax
actually paid in the calendar year, while accrued-basis filers count
tax accrued for the tax year. The posture is recorded on
``USReturnProfile2025.accrued_basis_ftc`` so downstream consumers
(US25-13 / US25-14) can select the correct timing.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_law import (
    USC_905_URL,
    validate_supported_us_filing_positions_2025,
)


class PaidBasisFTCURLTest(unittest.TestCase):
    """The § 905(a) authority URL is centralized for renderers and
    narrative templates."""

    def test_section_905_url_is_canonical(self) -> None:
        self.assertEqual(
            USC_905_URL,
            "https://uscode.house.gov/view.xhtml?req=granuleid:"
            "USC-prelim-title26-section905&num=0&edition=prelim",
        )


class PaidBasisFTCLoaderTest(unittest.TestCase):
    """Loader accepts ``elections.us_ftc_method=paid`` and records the
    posture on ``USReturnProfile2025.accrued_basis_ftc``.
    """

    def _seed_demo(self, root: Path):
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        return materialize_demo_workspace(
            root, demo_name="demo-2025", year=2025
        )

    def test_accrued_default_recorded_as_accrued_basis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_demo(Path(tmp))
            inputs = load_us_assessment_inputs_2025(paths)
            self.assertTrue(inputs.profile.accrued_basis_ftc)

    def test_paid_election_loads_with_accrued_basis_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_demo(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["us_ftc_method"] = "paid"
            paths.profile_path.write_text(json.dumps(profile))
            inputs = load_us_assessment_inputs_2025(paths)
            # Workstream 3: paid-basis posture no longer fails closed —
            # the loader records it for the FTC chain to consume.
            self.assertFalse(inputs.profile.accrued_basis_ftc)

    def test_invalid_ftc_method_still_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._seed_demo(Path(tmp))
            profile = json.loads(paths.profile_path.read_text())
            profile["elections"]["us_ftc_method"] = "something_else"
            paths.profile_path.write_text(json.dumps(profile))
            with self.assertRaisesRegex(ValueError, "expected 'accrued' or 'paid'"):
                load_us_assessment_inputs_2025(paths)


class PaidBasisFTCValidatorTest(unittest.TestCase):
    """``validate_supported_us_filing_positions_2025`` no longer
    rejects ``accrued_basis_ftc=False``.
    """

    def _demo_inputs(self):
        from tax_pipeline.demo_workspace import materialize_demo_workspace

        with tempfile.TemporaryDirectory() as tmp:
            paths = materialize_demo_workspace(
                Path(tmp), demo_name="demo-2025", year=2025
            )
            return load_us_assessment_inputs_2025(paths)

    def test_validator_accepts_paid_basis_posture(self) -> None:
        inputs = self._demo_inputs()
        paid = replace(inputs, profile=replace(inputs.profile, accrued_basis_ftc=False))
        # Should not raise.
        validate_supported_us_filing_positions_2025(paid)


if __name__ == "__main__":
    unittest.main()
