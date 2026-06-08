"""Worked-example pinning of § 20 Abs. 6 EStG loss-class ordering.

WS-5E of docs/invariant-migration-plan.md: the 2026-05-01 correctness review
flagged the ordering between current-year non-stock losses and a prior-year
stock-loss carryforward in
``tax_pipeline/y2025/germany_capital_rules.py::de25_15_section_20_6_netting``
as plausible-but-unverified.

Authority:

- § 20 Abs. 6 EStG (https://www.gesetze-im-internet.de/estg/__20.html).
- BMF-Schreiben vom 19.05.2022 (Einzelfragen zur Abgeltungsteuer), in der
  Fassung vom 14.05.2025, Rn. 118 (Verlustverrechnungsreihenfolge) and
  Rn. 122 (Verluste mindern die abgeltungsteuerpflichtigen Erträge / FTC
  applies to the post-netting Abgeltungsteuerschuld). Official URL:
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf

The BMF Rn. 118 ordering, verbatim (excerpt):

    1. Aktienveräußerungsgewinne/ -verluste … aus dem aktuellen Jahr;
       Aktienveräußerungsverluste … dürfen nur mit Aktienveräußerungs-
       gewinnen verrechnet werden.
    2. sonstige Kapitalerträge/Verluste aus dem aktuellen Jahr; sonstige
       negative Einkünfte … dürfen mit positiven Einkünften im Sinne des
       § 20 EStG verrechnet werden.
    3. Verlustvorträge … aus Aktienveräußerungen … dürfen nur mit nach
       Verrechnung gemäß Ziffer 1 und 2 verbleibenden Aktienveräußerungs-
       gewinnen verrechnet werden.

The two readings the test distinguishes:

  Reading A (BMF Rn. 118 — implemented):
      current-year non-stock loss reduces the stock gain available for
      carryforward FIRST; the prior-year stock-loss carryforward is then
      applied only to what remains.
  Reading B (alternative — would silently burn carryforward):
      prior-year stock-loss carryforward consumes stock gains BEFORE
      current-year non-stock losses are applied.

These two readings produce identical taxable § 20 income but DIFFERENT
``stock_loss_carryforward_used`` and ``stock_loss_carryforward_remaining``
values. The carryforward is a multi-year legal balance; mis-ordering
silently destroys taxpayer value in future years. Reading A is the only
reading consistent with BMF Rn. 118 Ziffer 3's "nur mit nach
Verrechnung gemäß Ziffer 1 und 2 verbleibenden Aktienveräußerungs-
gewinnen" qualifier.
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.y2025.germany_capital_rules import de25_15_section_20_6_netting


D = Decimal


class Section20Abs6OrderingTest(unittest.TestCase):
    """Pin BMF Rn. 118 ordering with a worked example.

    Authority: § 20 Abs. 6 EStG
    (https://www.gesetze-im-internet.de/estg/__20.html); BMF-Schreiben
    19.05.2022 / Fassung 14.05.2025, Rn. 118 and Rn. 122
    (https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-14-einzelfragen-zur-abgeltungsteuer.pdf).
    """

    @staticmethod
    def _build_facts(
        *,
        stock_gain: Decimal,
        option_gain: Decimal,
        fund_taxable_after_teilfreistellung: Decimal,
        non_fund_positive_income_total: Decimal,
        stock_loss_carryforward_2024: Decimal,
    ) -> dict:
        # Minimal facts shape for de25_15_section_20_6_netting. We
        # construct the upstream raw_buckets / fund_after dicts directly
        # so the test exercises only the § 20 Abs. 6 ordering logic.
        return {
            "de.capital.raw_buckets": {
                "stock_gain": stock_gain,
                "option_gain": option_gain,
                "non_fund_positive_income_total": non_fund_positive_income_total,
                "stock_symbol_gain": (
                    {"AAPL": stock_gain} if stock_gain > D("0.00") else {}
                ),
                "option_symbol_gain": {},
                "bank_certificate_non_stock_by_symbol": {},
                "income_items": (),
                "bank_certificate_foreign_taxable_by_item": {},
                "explicit_foreign_tax_total": D("0.00"),
                "foreign_tax_by_item": {},
                "foreign_tax_refund_by_item": {},
                "fund_types": {},
                "fund_symbols": frozenset(),
            },
            "de.capital.fund_after_teilfreistellung": {
                "fund_taxable_after_teilfreistellung": fund_taxable_after_teilfreistellung,
                "taxable_by_symbol_after_fund_teilfreistellung": {},
            },
            "de.capital.stock_loss_carryforward_2024": stock_loss_carryforward_2024,
            "de.capital.treaty_dividend_items": (),
            "de.capital.fund_classification": {},
            "de.capital.fund_teilfreistellung_rates": {},
            # InvStG § 19 Vorabpauschale (laufender Ertrag) is part of the
            # § 20 Abs. 6 non-stock-net bucket (Satz 4 forbids offsetting
            # against stock losses). These tests pin the BMF Rn. 118 ordering
            # for stock-loss carryforward consumption with no Vorabpauschale.
            # https://www.gesetze-im-internet.de/invstg_2018/__19.html
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": D("0.00"),
        }

    def test_bmf_rn_118_non_stock_loss_consumes_stock_gain_before_carryforward(
        self,
    ) -> None:
        # Worked example, EUR.
        #
        # Inputs:
        #   current-year stock gain (Aktiengewinn 2025)        = 10_000
        #   current-year non-stock pool (option loss)          = -4_000
        #   prior-year stock-loss carryforward (Verlustvortrag) =  8_000
        #
        # BMF Rn. 118 walk:
        #   Ziffer 1 — within-stock netting: no current-year stock loss,
        #     stock_gain stays at 10_000.
        #   Ziffer 2 — current-year non-stock loss (4_000) offsets
        #     positive § 20 income (which includes the stock gain), so
        #     6_000 of stock gain remains "available" before Ziffer 3.
        #   Ziffer 3 — prior-year stock-loss carryforward applies to that
        #     remaining 6_000 only:
        #       used      = min(6_000, 8_000) = 6_000
        #       remaining =        8_000 − 6_000 = 2_000
        #
        # Reading A (BMF Rn. 118, implemented): used = 6_000,
        #   remaining = 2_000.
        # Reading B (alternative, forbidden by Ziffer 3's "nur mit nach
        #   Verrechnung gemäß Ziffer 1 und 2 verbleibenden
        #   Aktienveräußerungsgewinnen"): would use 8_000 of the 8_000
        #   carryforward against the 10_000 stock gain first, leaving
        #   remaining = 0 and silently destroying taxpayer carryforward.
        facts = self._build_facts(
            stock_gain=D("10000.00"),
            option_gain=D("-4000.00"),
            fund_taxable_after_teilfreistellung=D("0.00"),
            non_fund_positive_income_total=D("0.00"),
            stock_loss_carryforward_2024=D("8000.00"),
        )
        netting = de25_15_section_20_6_netting(facts)[
            "de.capital.after_section_20_6_netting"
        ]
        self.assertEqual(netting["stock_loss_carryforward_used"], D("6000.00"))
        self.assertEqual(
            netting["stock_loss_carryforward_remaining"], D("2000.00")
        )
        # stock_gain_after_carryforward = 10_000 − 6_000 = 4_000 (the
        # non-stock loss does not appear here; it lowers
        # combined_current_capital in DE25-16 via raw_buckets.option_gain
        # so the joint taxable base is 4_000 + (−4_000) = 0).
        self.assertEqual(
            netting["stock_gain_after_carryforward"], D("4000.00")
        )

    def test_no_non_stock_loss_carryforward_consumes_full_stock_gain(self) -> None:
        # Sanity: with no current-year non-stock loss, the stock-loss
        # carryforward consumes stock gains directly (BMF Rn. 118 Ziffer
        # 1 → Ziffer 3, Ziffer 2 a no-op). Same fact pattern as above
        # but with a positive non-stock pool, isolating that the
        # ordering only KICKS IN when a non-stock loss exists.
        facts = self._build_facts(
            stock_gain=D("10000.00"),
            option_gain=D("0.00"),
            fund_taxable_after_teilfreistellung=D("0.00"),
            non_fund_positive_income_total=D("500.00"),
            stock_loss_carryforward_2024=D("8000.00"),
        )
        netting = de25_15_section_20_6_netting(facts)[
            "de.capital.after_section_20_6_netting"
        ]
        # With no non-stock loss, all 8_000 of carryforward applies
        # against the 10_000 stock gain.
        self.assertEqual(netting["stock_loss_carryforward_used"], D("8000.00"))
        self.assertEqual(
            netting["stock_loss_carryforward_remaining"], D("0.00")
        )
        self.assertEqual(
            netting["stock_gain_after_carryforward"], D("2000.00")
        )

    def test_non_stock_loss_exceeding_stock_gain_zeros_carryforward_use(
        self,
    ) -> None:
        # Non-stock loss (5_000) exceeds stock gain (3_000): under BMF
        # Rn. 118 Ziffer 2 the entire stock gain is absorbed by the
        # non-stock loss, leaving zero stock gain for the Ziffer 3
        # carryforward to consume. The carryforward must be preserved
        # in full.
        facts = self._build_facts(
            stock_gain=D("3000.00"),
            option_gain=D("-5000.00"),
            fund_taxable_after_teilfreistellung=D("0.00"),
            non_fund_positive_income_total=D("0.00"),
            stock_loss_carryforward_2024=D("8000.00"),
        )
        netting = de25_15_section_20_6_netting(facts)[
            "de.capital.after_section_20_6_netting"
        ]
        self.assertEqual(netting["stock_loss_carryforward_used"], D("0.00"))
        self.assertEqual(
            netting["stock_loss_carryforward_remaining"], D("8000.00")
        )
        # stock_gain_after_carryforward stays at the full stock_gain
        # (3_000); the non-stock loss is realized in DE25-16 via
        # combined_current_capital, not by mutating this field.
        self.assertEqual(
            netting["stock_gain_after_carryforward"], D("3000.00")
        )


if __name__ == "__main__":
    unittest.main()
