"""TREATY25-17 with explicitly-declared (not missing) zero German tax.

Authority: DBA-USA Art. 23 (Vermeidung der Doppelbesteuerung) and IRS
Pub. 514 worksheet lines 19 / 20c.
URL: https://www.irs.gov/pub/irs-trty/germany.pdf
URL: https://www.irs.gov/publications/p514

Per CLAUDE.md fail-closed contract (invariant I4): the producer
populates ``de.treaty.us_source_dividend_tax_and_credit`` with explicit
zeros when the German residence-country tax on the U.S.-source dividend
stack is genuinely zero (e.g., Sparer-Pauschbetrag absorbs the full
stack). The rule must compute a sensible re-sourced number from the
explicit zeros — NOT raise (the keys ARE declared) and NOT silently
return zero from a missing-key fallback (which H5 documented as the
silent-FTC-denial bug class).

This test pins the boundary: with both German precredit and residence
credit declared as Decimal("0.00"), TREATY25-17 must still execute and
produce ``treaty.german_residual_cap = 0.00`` (because there is no
residual residence-country tax to cap against). The worksheet line 19
maximum credit equals the U.S. tax above the 15 % floor — unchanged
by the German-side zeros.
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.treaty_rules import treaty25_17_german_residual_cap
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
)
from tax_pipeline.y2025.us_law import USTreatyInputs2025


def _facts(*, german_precredit: Decimal, residence_credit: Decimal) -> dict:
    # Construct a minimal fact bundle exercising the TREATY25-17 rule
    # with treaty re-sourcing enabled. Upstream values (us_tax /
    # treaty_minimum) come from a worked Pub. 514 example. The
    # ``de.treaty.us_source_dividend_tax_and_credit`` dict is what
    # carries the German-side declared values; the rule subscripts
    # both keys explicitly so a missing-key bug raises KeyError per
    # invariant I4 (the H5 silent-denial fingerprint).
    treaty_inputs = USTreatyInputs2025(
        use_treaty_resourcing=True,
        us_source_direct_equity_dividends_usd=Decimal("10000.00"),
        us_source_equity_fund_dividends_usd=Decimal("0.00"),
        us_source_non_equity_fund_dividends_usd=Decimal("0.00"),
    )
    return {
        "us.treaty.inputs": treaty_inputs,
        # Pub. 514 line 16 (avg-rate U.S. tax on $10k US-source).
        "treaty.us_tax_on_us_source_dividends": Decimal("2500.00"),
        # Line 17 (15 % treaty floor): 0.15 * $10,000 = $1,500.
        "treaty.treaty_minimum_us_tax_at_source": Decimal("1500.00"),
        "de.treaty.us_source_dividend_tax_and_credit": {
            "german_precredit_tax_on_us_source_dividends_usd": german_precredit,
            "german_residence_credit_for_us_tax_usd": residence_credit,
        },
    }


class Treaty25_17ExplicitZeroGermanTaxTest(unittest.TestCase):
    """TREATY25-17 with explicit Decimal('0.00') German tax fields."""

    def test_explicit_zero_german_precredit_yields_zero_residual_cap(self) -> None:
        # § 23 DBA-USA: residual residence-country tax = max(0,
        # German_precredit − greater_of(treaty_floor, residence_credit))
        # = max(0, 0 − max(1500, 0)) = 0. The result is a SENSIBLE
        # zero, NOT a silent-default zero — the rule executed
        # end-to-end with explicit inputs.
        out = treaty25_17_german_residual_cap(
            _facts(
                german_precredit=Decimal("0.00"),
                residence_credit=Decimal("0.00"),
            )
        )
        self.assertEqual(out["treaty.german_residual_cap"], Decimal("0.00"))
        # Line 19 (U.S. tax above 15 % floor) is independent of the
        # German-side zeros: 2500 − max(1500, 0) = 1000. F-USLAW-style
        # check: explicit zero must not poison the line-19 computation.
        self.assertEqual(
            out["treaty.worksheet_line_19_maximum_credit"],
            Decimal("1000.00"),
        )
        # Pinned canonical 15 % rate from DBA-USA Art. 10(2)(b).
        self.assertEqual(
            DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, Decimal("0.15")
        )
        # And both inputs are echoed back canonicalised at cents.
        self.assertEqual(
            out["treaty.german_precredit_tax_on_us_source_dividends"],
            Decimal("0.00"),
        )
        self.assertEqual(
            out["treaty.german_residence_credit_for_us_tax"],
            Decimal("0.00"),
        )

    def test_zero_german_precredit_with_nonzero_residence_credit(self) -> None:
        # German precredit zero + residence credit $200: line 20c =
        # max(0, 0 − max(1500, 200)) = 0; line 19 = max(0, 2500 −
        # max(1500, 200)) = 1000. The residence credit only binds
        # when it exceeds the 15 % floor.
        out = treaty25_17_german_residual_cap(
            _facts(
                german_precredit=Decimal("0.00"),
                residence_credit=Decimal("200.00"),
            )
        )
        self.assertEqual(out["treaty.german_residual_cap"], Decimal("0.00"))
        self.assertEqual(
            out["treaty.worksheet_line_19_maximum_credit"],
            Decimal("1000.00"),
        )

    def test_zero_german_precredit_with_residence_credit_above_floor(self) -> None:
        # Residence credit $1,800 exceeds the $1,500 treaty floor →
        # line 19 = max(0, 2500 − 1800) = 700; line 20c = max(0, 0 −
        # 1800) = 0. The bug class fingerprinted by H5 was that the
        # residence credit could quietly default to zero, masking
        # this clamp; the explicit zero here proves the producer-
        # contract path works.
        out = treaty25_17_german_residual_cap(
            _facts(
                german_precredit=Decimal("0.00"),
                residence_credit=Decimal("1800.00"),
            )
        )
        self.assertEqual(out["treaty.german_residual_cap"], Decimal("0.00"))
        self.assertEqual(
            out["treaty.worksheet_line_19_maximum_credit"],
            Decimal("700.00"),
        )


if __name__ == "__main__":
    unittest.main()
