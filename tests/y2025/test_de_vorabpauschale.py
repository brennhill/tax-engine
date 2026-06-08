"""Worked-example tests for DE25-13F-VORABPAUSCHALE (InvStG § 19).

Authority — controlling statute, BMF guidance, and form anchors:

- InvStG § 18 Abs. 1: Basisertrag formula
  ``Basisertrag = NAV_start * 0.7 * Basiszinssatz * months_held / 12``.
  https://www.gesetze-im-internet.de/invstg_2018/__18.html
- InvStG § 19: Vorabpauschale arises from the Basisertrag minus actual
  distributions; § 20 Teilfreistellung applies as it does to ordinary
  fund income.
  https://www.gesetze-im-internet.de/invstg_2018/__19.html
- InvStG § 16 Abs. 1 Nr. 2: cap at the year's actual NAV gain
  ``max(0, NAV_end - NAV_start)``.
  https://www.gesetze-im-internet.de/invstg_2018/__16.html
- InvStG § 20: Teilfreistellung rates (30 % Aktienfonds, 15 % Mischfonds,
  60 % / 80 % Immobilienfonds).
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
- BMF-Schreiben vom 16.01.2025 (IV C 1 - S 1980-1/19/10005:008): the
  Basiszinssatz for tax year 2025 is **2,53 %**.
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuergesetz/2025-01-16-basiszins-zur-berechnung-der-vorabpauschale.pdf?__blob=publicationFile&v=2
- § 20 Abs. 6 Satz 4 EStG: Vorabpauschale is laufender Ertrag (NOT a
  Veräusserungsgewinn) and may not offset stock losses; it joins the
  non-stock-net side of the § 20 Abs. 6 ordering.
  https://www.gesetze-im-internet.de/estg/__20.html
- Anlage KAP-INV Zeilen 9-13 carry the post-Teilfreistellung amount.

The tests pin the seven worked examples described in the law-flow
review (``.review/2026-05-01-legal-flow/germany-legal-flow.md`` gap
#9): zero scenario, Aktienfonds with retained earnings, distribution
exceeding Basisertrag, NAV-loss cap, partial-year proration, Mischfonds
variant, and § 20 Abs. 6 integration.
"""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.y2025.germany_law import (
    BASISZINS_2025,
    FUND_TEILFREISTELLUNG_RATES_2025,
    VORABPAUSCHALE_BASISERTRAG_FACTOR,
)
from tax_pipeline.y2025.germany_capital_rules import (
    de25_13f_vorabpauschale,
    de25_15_section_20_6_netting,
)


D = Decimal


def _facts(
    *,
    vorabpauschale_inputs: dict,
    fund_classification: dict[str, str] | None = None,
) -> dict:
    """Minimal facts shape for the rule body. The Pipeline 1 derivation
    has already projected the per-fund inputs into a dict of dicts; this
    helper mirrors that contract for direct rule-body invocation in
    unit tests.
    """
    return {
        "de.derived.vorabpauschale_inputs": vorabpauschale_inputs,
        "de.capital.fund_classification": fund_classification or {},
        "de.capital.fund_teilfreistellung_rates": dict(FUND_TEILFREISTELLUNG_RATES_2025),
        "de.capital.basiszins": BASISZINS_2025,
        "de.capital.vorabpauschale_basisertrag_factor": (
            VORABPAUSCHALE_BASISERTRAG_FACTOR
        ),
    }


class Vorabpauschale2025WorkedExamplesTest(unittest.TestCase):
    """InvStG § 19 deemed-distribution worked examples for tax year 2025.

    Each case documents the BMF-referenced inputs and asserts the Decimal
    EUR amount the legal core must produce, never just the function's
    return shape.
    """

    def test_zero_scenario_no_funds_in_scope(self) -> None:
        # Authority: InvStG § 19 only applies to accumulating funds the
        # taxpayer holds. An empty per-fund index produces 0,00 EUR
        # gross and 0,00 EUR after Teilfreistellung.
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        facts = _facts(vorabpauschale_inputs={})
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(out["de.capital.vorabpauschale_per_symbol_eur"], {})
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("0.00"))
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("0.00"),
        )

    def test_aktienfonds_full_year_retained_earnings(self) -> None:
        # Authority: InvStG § 18 Abs. 1 Satz 1 — Basisertrag formula.
        # InvStG § 20 Abs. 1 — 30 % Teilfreistellung for Aktienfonds.
        # BMF-Schreiben 16.01.2025 — Basiszinssatz 2025 = 2,53 %.
        #
        # NAV_start = 10_000,00; NAV_end = 12_000,00; Ausschuettung = 0;
        # full-year hold (months_held = 12). Aktienfonds retains all
        # earnings, so Vorabpauschale = full Basisertrag, capped only by
        # the 2_000,00 NAV gain (the cap doesn't bind here).
        #
        # Basisertrag = 10_000 * 0.7 * 0.0253 * 12 / 12 = 177.10
        # gross_vorab = max(0, 177.10 - 0) = 177.10
        # nav_gain    = max(0, 12_000 - 10_000) = 2_000.00
        # vorab       = min(177.10, 2_000) = 177.10
        # taxable_after_30%_TF = 177.10 * 0.70 = 123.97
        facts = _facts(
            vorabpauschale_inputs={
                "AKTIENFOND-A": {
                    "nav_start_eur": D("10000.00"),
                    "nav_end_eur": D("12000.00"),
                    "ausschuettung_eur": D("0.00"),
                    "months_held": 12,
                }
            },
            fund_classification={"AKTIENFOND-A": "aktienfonds"},
        )
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(
            out["de.capital.vorabpauschale_per_symbol_eur"],
            {"AKTIENFOND-A": D("177.10")},
        )
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("177.10"))
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("123.97"),
        )

    def test_distribution_exceeds_basisertrag_drops_vorabpauschale_to_zero(
        self,
    ) -> None:
        # Authority: InvStG § 18 Abs. 1 Satz 3 — actual Ausschuettungen are
        # subtracted from the Basisertrag before a Vorabpauschale arises.
        # When the distribution ≥ Basisertrag, no Vorabpauschale at all.
        # https://www.gesetze-im-internet.de/invstg_2018/__18.html
        #
        # NAV_start = 10_000; Ausschuettung = 200,00 (exceeds 177,10
        # Basisertrag); NAV_end = 11_000.
        # gross_vorab = max(0, 177.10 - 200) = 0.00
        facts = _facts(
            vorabpauschale_inputs={
                "AKTIENFOND-B": {
                    "nav_start_eur": D("10000.00"),
                    "nav_end_eur": D("11000.00"),
                    "ausschuettung_eur": D("200.00"),
                    "months_held": 12,
                }
            },
            fund_classification={"AKTIENFOND-B": "aktienfonds"},
        )
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("0.00"))
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("0.00"),
        )

    def test_nav_loss_cap_zeros_vorabpauschale(self) -> None:
        # Authority: InvStG § 16 Abs. 1 Nr. 2 — the Vorabpauschale cannot
        # exceed the year's actual NAV gain (NAV_end − NAV_start). When
        # the fund is flat or down for the year the cap forces the result
        # to zero even if the Basisertrag formula would yield a positive
        # number.
        # https://www.gesetze-im-internet.de/invstg_2018/__16.html
        #
        # NAV_start = 10_000; NAV_end = 9_500 (loss); Ausschuettung = 0.
        # Basisertrag = 177.10 but nav_gain = max(0, -500) = 0.00,
        # so vorab = min(177.10, 0) = 0.00.
        facts = _facts(
            vorabpauschale_inputs={
                "AKTIENFOND-C": {
                    "nav_start_eur": D("10000.00"),
                    "nav_end_eur": D("9500.00"),
                    "ausschuettung_eur": D("0.00"),
                    "months_held": 12,
                }
            },
            fund_classification={"AKTIENFOND-C": "aktienfonds"},
        )
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("0.00"))
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("0.00"),
        )

    def test_partial_year_proration_six_months(self) -> None:
        # Authority: InvStG § 18 Abs. 2 — pro-rated Basisertrag by 1/12 per
        # full month of ownership during the calendar year.
        # https://www.gesetze-im-internet.de/invstg_2018/__18.html
        #
        # NAV_start = 10_000; NAV_end = 12_000; Ausschuettung = 0;
        # six full months held (e.g., bought July 1).
        # Basisertrag = 10_000 * 0.7 * 0.0253 * 6 / 12 = 88.55
        # vorab       = min(88.55, 2_000) = 88.55
        # taxable_after_30%_TF = 88.55 * 0.70 = 61.985 -> q2 -> 61.99
        facts = _facts(
            vorabpauschale_inputs={
                "AKTIENFOND-D": {
                    "nav_start_eur": D("10000.00"),
                    "nav_end_eur": D("12000.00"),
                    "ausschuettung_eur": D("0.00"),
                    "months_held": 6,
                }
            },
            fund_classification={"AKTIENFOND-D": "aktienfonds"},
        )
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("88.55"))
        # 88.55 * 0.70 = 61.985 -> ROUND_HALF_UP -> 61.99.
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("61.99"),
        )

    def test_mischfonds_uses_fifteen_percent_teilfreistellung(self) -> None:
        # Authority: InvStG § 20 Abs. 1 Satz 2 — Mischfonds Teilfreistellung
        # is 15 % (half the Aktienfonds rate).
        # https://www.gesetze-im-internet.de/invstg_2018/__20.html
        #
        # NAV_start = 10_000; NAV_end = 12_000; Ausschuettung = 0;
        # full-year hold; Mischfonds classification.
        # Basisertrag = 177.10
        # taxable_after_15%_TF = 177.10 * 0.85 = 150.535 -> q2 -> 150.54
        facts = _facts(
            vorabpauschale_inputs={
                "MISCHFOND-E": {
                    "nav_start_eur": D("10000.00"),
                    "nav_end_eur": D("12000.00"),
                    "ausschuettung_eur": D("0.00"),
                    "months_held": 12,
                }
            },
            fund_classification={"MISCHFOND-E": "mischfonds"},
        )
        out = de25_13f_vorabpauschale(facts)
        self.assertEqual(out["de.capital.vorabpauschale_total_eur"], D("177.10"))
        # 177.10 * 0.85 = 150.535 -> ROUND_HALF_UP -> 150.54.
        self.assertEqual(
            out["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"],
            D("150.54"),
        )


class VorabpauschaleSection20Abs6IntegrationTest(unittest.TestCase):
    """Pin § 20 Abs. 6 Satz 4 EStG integration: Vorabpauschale is
    laufender Ertrag, not a Veräusserungsgewinn, so it joins the
    non-stock-net bucket and absorbs current-year non-stock losses but
    NEVER offsets stock losses (current-year or carried).
    https://www.gesetze-im-internet.de/estg/__20.html
    https://www.gesetze-im-internet.de/invstg_2018/__19.html
    """

    @staticmethod
    def _section_20_6_facts(
        *,
        stock_gain: Decimal,
        option_gain: Decimal,
        fund_taxable_after_teilfreistellung: Decimal,
        non_fund_positive_income_total: Decimal,
        stock_loss_carryforward_2024: Decimal,
        vorabpauschale_taxable_after_teilfreistellung_eur: Decimal,
    ) -> dict:
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
                "fund_taxable_after_teilfreistellung": (
                    fund_taxable_after_teilfreistellung
                ),
                "taxable_by_symbol_after_fund_teilfreistellung": {},
            },
            "de.capital.stock_loss_carryforward_2024": stock_loss_carryforward_2024,
            "de.capital.treaty_dividend_items": (),
            "de.capital.fund_classification": {},
            "de.capital.fund_teilfreistellung_rates": {},
            "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": (
                vorabpauschale_taxable_after_teilfreistellung_eur
            ),
        }

    def test_vorabpauschale_joins_non_stock_net_bucket_not_stock_gain(
        self,
    ) -> None:
        # Authority: § 20 Abs. 6 Satz 4 EStG — Aktienverluste only offset
        # Aktiengewinne. Vorabpauschale is laufender Ertrag, so it cannot
        # absorb stock losses. With a current-year non-stock loss
        # (option_gain = -300) and Vorabpauschale = +500, the net
        # non-stock-net should be 500 - 300 = 200 (positive), so no loss
        # is consumed against the stock-gain side, and the carryforward
        # is preserved.
        facts = self._section_20_6_facts(
            stock_gain=D("1000.00"),
            option_gain=D("-300.00"),
            fund_taxable_after_teilfreistellung=D("0.00"),
            non_fund_positive_income_total=D("0.00"),
            stock_loss_carryforward_2024=D("500.00"),
            vorabpauschale_taxable_after_teilfreistellung_eur=D("500.00"),
        )
        result = de25_15_section_20_6_netting(facts)[
            "de.capital.after_section_20_6_netting"
        ]
        # current_year_non_stock_net = -300 + 0 + 0 + 500 = +200 (positive,
        # no current-year non-stock loss); stock gain stays at 1000;
        # stock_loss_carryforward consumed = min(1000, 500) = 500.
        self.assertEqual(
            result["stock_gain_after_carryforward"],
            D("500.00"),
        )
        self.assertEqual(result["stock_loss_carryforward_used"], D("500.00"))
        self.assertEqual(result["stock_loss_carryforward_remaining"], D("0.00"))


if __name__ == "__main__":
    unittest.main()
