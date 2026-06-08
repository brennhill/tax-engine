"""§ 55(d)(3) AMT exemption ZEROING at the exact phase-out completion AMTI.

Authority: 26 U.S.C. § 55(d)(3) — the AMT exemption is reduced by 25
cents per dollar of AMTI above the filing-status phase-out start, and
floored at zero. The first AMTI dollar at which the reduced exemption
hits zero is therefore::

    AMTI_zero = phaseout_start + exemption / 0.25

For Single 2025 (Rev. Proc. 2024-40 § 3.11)::

    phaseout_start = $626,350
    exemption      = $88,100
    AMTI_zero      = 626,350 + 88,100 / 0.25 = 978,750.00 USD

URL: https://www.law.cornell.edu/uscode/text/26/55
URL: https://www.irs.gov/pub/irs-drop/rp-24-40.pdf
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from law.usa.year_2025.rev_proc.proc_2024_40.p3_11 import (
    AMT_EXEMPTION_MFJ_2025_USD,
    AMT_EXEMPTION_MFS_2025_USD,
    AMT_EXEMPTION_SINGLE_2025_USD,
    AMT_PHASEOUT_START_MFJ_2025_USD,
    AMT_PHASEOUT_START_MFS_2025_USD,
    AMT_PHASEOUT_START_SINGLE_2025_USD,
)
from law.usa.year_2025.usc26.p55 import (
    AMT_PHASEOUT_RATE,
    amt_exemption_after_phaseout_2025,
)


class P55AmtExemptionZeroingTest(unittest.TestCase):
    """Pin the exact AMTI at which the exemption hits zero for each
    filing status, on both sides of the boundary.
    """

    def test_phaseout_rate_is_25_cents_per_dollar(self) -> None:
        # § 55(d)(3) statutory rate.
        self.assertEqual(AMT_PHASEOUT_RATE, Decimal("0.25"))

    def test_exemption_zeros_at_each_filing_status_amti_zero(self) -> None:
        # § 55(d)(3): the AMT exemption is reduced by 25 cents per dollar
        # above the phase-out start. ``AMTI_zero = phaseout_start +
        # exemption / 0.25`` is the first dollar where the reduced
        # exemption hits zero. Pin all three filing statuses on a single
        # matrix so a Rev. Proc. 2024-40 inflation update touches one
        # place.
        cases = (
            (
                "Single",
                AMT_PHASEOUT_START_SINGLE_2025_USD,
                AMT_EXEMPTION_SINGLE_2025_USD,
                Decimal("978750.00"),
            ),
            (
                "Married filing jointly",
                AMT_PHASEOUT_START_MFJ_2025_USD,
                AMT_EXEMPTION_MFJ_2025_USD,
                Decimal("1800700.00"),
            ),
            (
                "Married filing separately",
                AMT_PHASEOUT_START_MFS_2025_USD,
                AMT_EXEMPTION_MFS_2025_USD,
                Decimal("900350.00"),
            ),
        )
        for status, phaseout_start, exemption, expected_zero in cases:
            with self.subTest(status=status):
                amti_zero = phaseout_start + (exemption / AMT_PHASEOUT_RATE)
                self.assertEqual(amti_zero, expected_zero)
                self.assertEqual(
                    amt_exemption_after_phaseout_2025(
                        amti_usd=amti_zero,
                        filing_status_label=status,
                    ),
                    Decimal("0"),
                )

    def test_exemption_phase_out_around_single_zeroing_point(self) -> None:
        # Single around the $978,750 zero-point + at-phaseout-start full
        # exemption. The four points pin the linear-then-floored
        # behaviour at the cents.
        cases = (
            (AMT_PHASEOUT_START_SINGLE_2025_USD, AMT_EXEMPTION_SINGLE_2025_USD,
             "at phaseout start: full exemption"),
            (Decimal("978749"), Decimal("0.25"),
             "1 dollar below zero-point: 88100 − 88099.75"),
            (Decimal("978750.00"), Decimal("0"),
             "exactly at zero-point"),
            (Decimal("978751"), Decimal("0"),
             "1 dollar above: floored to 0"),
        )
        for amti, expected, note in cases:
            with self.subTest(amti=amti, note=note):
                self.assertEqual(
                    amt_exemption_after_phaseout_2025(
                        amti_usd=amti,
                        filing_status_label="Single",
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
