from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.fund_classification_data import load_repo_german_fund_classification
from tax_pipeline.y2025.germany_law import FUND_TEILFREISTELLUNG_RATES_2025


class FundClassificationDataTest(unittest.TestCase):
    """Pin the engine-shipped InvStG § 2 Abs. 6 fund classifications.

    The repo CSV is consulted by germany_model.load_fund_classification and by
    the auto-derivation of Pub. 514 treaty dividend items. Values are stable
    over time for a given fund's structure; this test pins well-known
    classifications so a future edit cannot silently flip one, and asserts
    the resulting Teilfreistellung amount each classification produces under
    InvStG § 20 (numeric outcome, not just classification string).
    Authority:
    - InvStG § 2 Abs. 6 (https://www.gesetze-im-internet.de/invstg_2018/__2.html)
    - InvStG § 20 (https://www.gesetze-im-internet.de/invstg_2018/__20.html)
    """

    def _taxable_eur_after_teilfreistellung(self, fund_type: str, gross_eur: Decimal) -> Decimal:
        rate = FUND_TEILFREISTELLUNG_RATES_2025[fund_type]
        return (gross_eur * (Decimal("1.00") - rate)).quantize(Decimal("0.01"))

    def test_known_fund_classifications_pin_invstg_20_taxable_amounts(self) -> None:
        # ``(symbol, expected_classification, expected_taxable_eur, citation)``
        # pinning the InvStG § 20 Abs. 1 Nr. 1 Teilfreistellung-rate
        # outcome for €100 gross. A regression that flips a symbol's
        # classification (or the rate table) is caught by the cents
        # value, not just the classification string.
        cases = (
            # Broad U.S. equity ETFs: Aktienfonds, 30 % Teilfreistellung → €70 taxable.
            ("VOO", "aktienfonds", Decimal("70.00"), "broad U.S. equity"),
            ("VTI", "aktienfonds", Decimal("70.00"), "broad U.S. equity"),
            ("QQQ", "aktienfonds", Decimal("70.00"), "Nasdaq-100 ETF"),
            ("SCHD", "aktienfonds", Decimal("70.00"), "dividend-equity ETF"),
            ("VXUS", "aktienfonds", Decimal("70.00"),
             "ex-U.S. equity (independent of IRC § 861 source)"),
            # JEPI's direct-equity sleeve > 50 % even when ELN excluded
            # per InvStG § 2 Abs. 8.
            ("JEPI", "aktienfonds", Decimal("70.00"), "JEPI w/ ELN overlay"),
            # Commodity trusts → Sonstige, 0 % → €100 taxable.
            ("IBIT", "sonstige", Decimal("100.00"), "spot bitcoin trust"),
            ("FBTC", "sonstige", Decimal("100.00"), "spot bitcoin trust"),
            ("GLD", "sonstige", Decimal("100.00"), "gold trust"),
            ("SLV", "sonstige", Decimal("100.00"), "silver trust"),
            # Bond CEFs and preferred-equity overlays: Sonstige.
            ("PTY", "sonstige", Decimal("100.00"), "bond CEF"),
            ("PFN", "sonstige", Decimal("100.00"), "bond CEF"),
            ("PFFA", "sonstige", Decimal("100.00"),
             "preferred ETF — not Beteiligungskapital per § 2 Abs. 8"),
            ("AMZA", "sonstige", Decimal("100.00"),
             "MLP fund — not Beteiligungskapital per § 2 Abs. 8"),
            ("GRNY", "sonstige", Decimal("100.00"),
             "put-write overlay on Treasuries: neither options nor "
             "Treasuries are Beteiligungskapital"),
        )
        cls = load_repo_german_fund_classification()
        for symbol, expected_class, expected_taxable, citation in cases:
            with self.subTest(symbol=symbol, citation=citation):
                self.assertEqual(cls[symbol], expected_class)
                self.assertEqual(
                    self._taxable_eur_after_teilfreistellung(
                        cls[symbol], Decimal("100.00")
                    ),
                    expected_taxable,
                )

    def test_symbols_are_upper_case(self) -> None:
        cls = load_repo_german_fund_classification()
        for symbol in cls:
            self.assertEqual(symbol, symbol.upper())

    def test_only_recognized_fund_types(self) -> None:
        # Loader normalizes through germany_2025_law.normalized_fund_type_2025
        # which only accepts values keyed in FUND_TEILFREISTELLUNG_RATES_2025.
        cls = load_repo_german_fund_classification()
        for symbol, fund_type in cls.items():
            self.assertIn(fund_type, FUND_TEILFREISTELLUNG_RATES_2025, symbol)


if __name__ == "__main__":
    unittest.main()
