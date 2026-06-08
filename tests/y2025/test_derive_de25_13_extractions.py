"""Equivalence tests for the five DE25-13 → Pipeline 1 derivation extractions.

Per ``docs/invariant-migration-plan.md`` §7 / WS-5A (re-scoped) the five
data-only sub-blocks embedded in DE25-13's calculate body are extracted
to first-class Pipeline 1 stages. Each test in this file pins the
derived-fact output of one extracted stage against the value DE25-13
currently materializes inside its ``de.capital.raw_buckets`` dict so a
regression in the extraction is caught before the legal pipeline runs.

Authority context:
- § 20 Abs. 4 EStG cost-basis aggregation (per-symbol sale roll-up).
  https://www.gesetze-im-internet.de/estg/__20.html
- 26 U.S.C. §§ 6042 / 6045 reporting taxonomy (1099-DIV box-1a vs the
  capital-gain / nondividend boxes that are NOT German § 20 Abs. 1
  income).
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6042&num=0&edition=prelim
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6045&num=0&edition=prelim
- § 43a Abs. 3 EStG bank-certificate format (KAP Zeile 7/8 income +
  stock-gain split).
  https://www.gesetze-im-internet.de/estg/__43a.html
- DBA-USA Art. 10 source rules (fund-type classification driving the
  InvStG § 20 partial-exemption rate that flows through the residence /
  source split).
  https://www.irs.gov/pub/irs-trty/germany.pdf
- § 32d Abs. 5 EStG per-Posten foreign-tax credit (the indexing target).
  https://www.gesetze-im-internet.de/estg/__32d.html
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
    GermanyBankCapitalCertificate2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
)


D = Decimal


def _common_facts() -> dict:
    """Build a shared raw-fact dict that exercises every DE25-13 sub-block.

    The fact pattern crosses the four moving parts: stock + fund + option
    sales, dividend + interest + foreign-tax income items, two bank
    certificates, and a non-zero DHER stock gain.
    """
    sale_facts = (
        GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="AAPL", gain_eur_matched=D("100.00")),
        GermanyCapitalSaleFact2025(asset_bucket="stock", symbol="AAPL", gain_eur_matched=D("50.00")),
        GermanyCapitalSaleFact2025(asset_bucket="fund_like", symbol="VWRL", gain_eur_matched=D("80.00")),
        GermanyCapitalSaleFact2025(asset_bucket="option", symbol="SPY_OPT", gain_eur_matched=D("25.00")),
    )
    income_facts = (
        # § 20 Abs. 1 dividend on a stock — Box 1a-style ordinary dividend.
        GermanyCapitalIncomeFact2025(
            kind="dividend",
            asset_bucket="stock",
            symbol="AAPL",
            eur_amount=D("12.00"),
            foreign_tax_item_id="aapl_div_2025",
        ),
        # Per-Posten foreign tax row keyed to AAPL via item id.
        GermanyCapitalIncomeFact2025(
            kind="foreign_tax",
            asset_bucket="stock",
            symbol="AAPL",
            eur_amount=D("1.80"),
            refund_entitlement_eur=D("0.00"),
            foreign_tax_item_id="aapl_div_2025",
        ),
        # Fund-distribution income; classified into fund_symbol_income.
        GermanyCapitalIncomeFact2025(
            kind="dividend",
            asset_bucket="fund_like",
            symbol="VWRL",
            eur_amount=D("5.00"),
            foreign_tax_item_id="vwrl_div_2025",
        ),
        # Cash-bucket interest, no foreign tax.
        GermanyCapitalIncomeFact2025(
            kind="interest",
            asset_bucket="cash",
            symbol="ALLY",
            eur_amount=D("3.50"),
            foreign_tax_item_id="ally_int_2025",
        ),
    )
    bank_certificates = (
        GermanyBankCapitalCertificate2025(
            owner_slot="person_1",
            certificate_id="DE_BANK_A",
            source_file="bank_a.pdf",
            kap_line_7_income_eur=D("400.00"),
            kap_line_8_stock_gains_eur=D("250.00"),
            kap_line_17_saver_allowance_used_eur=D("100.00"),
            kap_line_37_kest_withheld_eur=D("60.00"),
            kap_line_38_soli_withheld_eur=D("3.30"),
            kap_line_40_foreign_tax_credited_eur=D("12.00"),
            kap_line_41_foreign_tax_not_credited_eur=D("4.00"),
        ),
        GermanyBankCapitalCertificate2025(
            owner_slot="person_1",
            certificate_id="DE_BANK_B",
            source_file="bank_b.pdf",
            kap_line_7_income_eur=D("100.00"),
            kap_line_8_stock_gains_eur=D("0.00"),
            kap_line_17_saver_allowance_used_eur=D("0.00"),
            kap_line_37_kest_withheld_eur=D("15.00"),
            kap_line_38_soli_withheld_eur=D("0.82"),
            kap_line_40_foreign_tax_credited_eur=D("0.00"),
            kap_line_41_foreign_tax_not_credited_eur=D("0.00"),
        ),
    )
    fund_classification = {"VWRL": "aktienfonds"}
    return {
        "de.capital.sale_facts": sale_facts,
        "de.capital.income_facts": income_facts,
        "de.capital.bank_certificates": bank_certificates,
        "de.capital.fund_classification": fund_classification,
        "de.capital.dher_stock_gain": D("75.00"),
    }


class DeriveDe25_13APerSymbolSaleAggregationTest(unittest.TestCase):
    """DERIVE-DE25-13A: § 20 Abs. 4 EStG cost-basis aggregation.

    Authority: § 20 Abs. 4 EStG and BMF Abgeltungsteuer Rn. 122.
    https://www.gesetze-im-internet.de/estg/__20.html
    """

    def test_per_symbol_sale_aggregation_matches_de25_13_internal_buckets(self) -> None:
        from tax_pipeline.y2025.derivation.germany_derivations import (
            derive_de25_13a_per_symbol_sale_aggregation,
        )

        facts = _common_facts()
        result = derive_de25_13a_per_symbol_sale_aggregation(facts)
        agg = result["de.derived.per_symbol_sale_aggregation"]

        # Stock totals roll up to AAPL=150 plus the DHER sidecar 75 = 225.
        self.assertEqual(agg["stock_gain"], D("225.00"))
        self.assertEqual(agg["stock_symbol_gain"]["AAPL"], D("150.00"))
        self.assertEqual(agg["stock_symbol_gain"]["__equity_comp_sidecar__"], D("75.00"))
        # Fund and option totals come straight from the per-bucket sums.
        self.assertEqual(agg["fund_gain"], D("80.00"))
        self.assertEqual(agg["fund_symbol_gain"]["VWRL"], D("80.00"))
        self.assertEqual(agg["option_gain"], D("25.00"))
        self.assertEqual(agg["option_symbol_gain"]["SPY_OPT"], D("25.00"))
        self.assertEqual(agg["dher_stock_gain"], D("75.00"))


class DeriveDe25_13B_1099BoxFilteringTest(unittest.TestCase):
    """DERIVE-DE25-13B: 26 U.S.C. §§ 6042 / 6045 reporting taxonomy split.

    Authority: 26 U.S.C. § 6042 (1099-DIV ordinary-dividend reporting) and
    § 6045 (broker-reported gross-proceeds gains). DE25-13 historically
    routed Box-1a-style ordinary dividends into Germany's § 20 Abs. 1
    income totals while Box-2a / Box-3 rows arrive via the sale-fact
    bucket. This stage pins the income-fact filter that produces the
    § 20 Abs. 1 income index.
    """

    def test_box_1a_filtering_separates_foreign_tax_and_income_items(self) -> None:
        from tax_pipeline.y2025.derivation.germany_derivations import (
            derive_de25_13b_1099_box_filtering,
        )

        facts = _common_facts()
        result = derive_de25_13b_1099_box_filtering(facts)
        box = result["de.derived.box_1a_filtered_dividends"]

        # Positive income totals: AAPL 12 + VWRL 5 + ALLY 3.50 = 20.50.
        self.assertEqual(box["positive_income_total"], D("20.50"))
        # Non-fund positive income excludes the VWRL fund_like row.
        self.assertEqual(box["non_fund_positive_income_total"], D("15.50"))
        # Foreign-tax row routed via foreign_tax_by_item.
        self.assertEqual(box["foreign_tax_by_item"]["aapl_div_2025"], D("1.80"))
        # Fund-symbol income index registers VWRL alone.
        self.assertEqual(box["fund_symbol_income"]["VWRL"], D("5.00"))
        # Income items expose (item_id, symbol, bucket, amount) tuples.
        item_ids = {row[0] for row in box["income_items"]}
        self.assertEqual(item_ids, {"aapl_div_2025", "vwrl_div_2025", "ally_int_2025"})
        # Total foreign tax rolls up through explicit_foreign_tax_total.
        self.assertEqual(box["explicit_foreign_tax_total"], D("1.80"))


class DeriveDe25_13CPerSymbolBankCertificateBucketsTest(unittest.TestCase):
    """DERIVE-DE25-13C: § 43a Abs. 3 EStG bank-certificate aggregation.

    Authority: § 43a Abs. 3 EStG governs the Steuerbescheinigung shape;
    KAP Zeile 7 carries total capital income, Zeile 8 the stock-gain
    subset already inside Zeile 7, and Zeilen 40/41 the foreign-tax
    credited / not-credited columns.
    https://www.gesetze-im-internet.de/estg/__43a.html
    """

    def test_per_symbol_bank_certificate_buckets_match_inline_totals(self) -> None:
        from tax_pipeline.y2025.derivation.germany_derivations import (
            derive_de25_13c_per_symbol_bank_certificate_buckets,
        )

        facts = _common_facts()
        result = derive_de25_13c_per_symbol_bank_certificate_buckets(facts)
        bank = result["de.derived.per_symbol_bank_certificate_buckets"]

        # Aggregated headline numbers across both certificates.
        self.assertEqual(bank["bank_certificate_summary"]["income"], D("500.00"))
        self.assertEqual(bank["bank_certificate_summary"]["stock_gain"], D("250.00"))
        # 400 - 250 = 150 from cert A; cert B contributes 100; total 250.
        self.assertEqual(bank["bank_certificate_summary"]["non_stock_income"], D("250.00"))
        self.assertEqual(bank["bank_certificate_summary"]["saver_allowance_used"], D("100.00"))
        self.assertEqual(bank["bank_certificate_summary"]["foreign_tax_credited"], D("12.00"))
        self.assertEqual(bank["bank_certificate_summary"]["foreign_tax_not_credited"], D("4.00"))
        self.assertEqual(bank["domestic_capital_tax_withheld"], D("75.00"))
        self.assertEqual(bank["domestic_capital_soli_withheld"], D("4.12"))
        # Per-symbol non-stock income index uses the synthetic bank-cert key.
        self.assertEqual(
            bank["bank_certificate_non_stock_by_symbol"]["__bank_certificate_non_stock__:DE_BANK_A"],
            D("150.00"),
        )
        # Stock-subset tracks the per-cert split for downstream stock_symbol_gain.
        self.assertEqual(
            bank["stock_subset_by_certificate"]["__bank_certificate_stock__:DE_BANK_A"],
            D("250.00"),
        )


class DeriveDe25_13DSourceCountryClassificationTest(unittest.TestCase):
    """DERIVE-DE25-13D: DBA-USA Art. 10 source rules / InvStG § 20 fund-type split.

    Authority: DBA-USA Art. 10 governs source-state taxation for
    portfolio dividends; the equity / non-equity fund-type axis (also
    documented in InvStG § 20) drives the partial-exemption rate that
    feeds the per-Posten foreign-tax indexing in DE25-18.
    https://www.irs.gov/pub/irs-trty/germany.pdf
    https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """

    def test_source_country_classification_partitions_fund_symbols(self) -> None:
        from tax_pipeline.y2025.derivation.germany_derivations import (
            derive_de25_13a_per_symbol_sale_aggregation,
            derive_de25_13b_1099_box_filtering,
            derive_de25_13d_source_country_classification,
        )

        base = _common_facts()
        agg = derive_de25_13a_per_symbol_sale_aggregation(base)[
            "de.derived.per_symbol_sale_aggregation"
        ]
        box = derive_de25_13b_1099_box_filtering(base)[
            "de.derived.box_1a_filtered_dividends"
        ]
        facts = {
            **base,
            "de.derived.per_symbol_sale_aggregation": agg,
            "de.derived.box_1a_filtered_dividends": box,
        }
        result = derive_de25_13d_source_country_classification(facts)
        classification = result["de.derived.source_country_classification"]

        # VWRL is the only fund symbol; classified as aktienfonds via the
        # workspace fund_classification override.
        self.assertEqual(classification["fund_symbols"], frozenset({"VWRL"}))
        self.assertEqual(classification["fund_types"], {"VWRL": "aktienfonds"})
        # Equity-fund total combines VWRL sale gain (80) and fund income (5).
        self.assertEqual(classification["equity_fund_total"], D("85.00"))
        self.assertEqual(classification["non_equity_fund_total"], D("0.00"))


class DeriveDe25_13EForeignTaxIndexingTest(unittest.TestCase):
    """DERIVE-DE25-13E: § 32d Abs. 5 EStG per-Posten foreign-tax indexing.

    Authority: § 32d Abs. 5 EStG caps foreign tax per individual taxable
    item / source. This stage assembles the per-item foreign-tax table
    consumed by DE25-18 and validates that symbol-only fallback is
    unambiguous (the legal precondition under § 32d Abs. 5).
    https://www.gesetze-im-internet.de/estg/__32d.html
    """

    def test_foreign_tax_indexing_assembles_per_item_table(self) -> None:
        from tax_pipeline.y2025.derivation.germany_derivations import (
            derive_de25_13b_1099_box_filtering,
            derive_de25_13c_per_symbol_bank_certificate_buckets,
            derive_de25_13e_foreign_tax_indexing,
        )

        base = _common_facts()
        box = derive_de25_13b_1099_box_filtering(base)[
            "de.derived.box_1a_filtered_dividends"
        ]
        bank = derive_de25_13c_per_symbol_bank_certificate_buckets(base)[
            "de.derived.per_symbol_bank_certificate_buckets"
        ]
        facts = {
            "de.derived.box_1a_filtered_dividends": box,
            "de.derived.per_symbol_bank_certificate_buckets": bank,
        }
        result = derive_de25_13e_foreign_tax_indexing(facts)
        index = result["de.derived.foreign_tax_indexing"]

        # AAPL 1099-DIV per-Posten foreign tax flows in from box filtering.
        self.assertEqual(index["foreign_tax_by_item"]["aapl_div_2025"], D("1.80"))
        # Bank-certificate A foreign tax (12 + 4 = 16) is keyed by certificate id.
        self.assertEqual(
            index["foreign_tax_by_item"]["__bank_certificate_foreign_tax__:DE_BANK_A"],
            D("16.00"),
        )
        # Explicit foreign-tax total combines income-fact rows + bank-certificate rows.
        self.assertEqual(index["explicit_foreign_tax_total"], D("17.80"))
        # Bank-certificate "foreign-taxable" base for cap calculations indexes by cert id.
        self.assertEqual(
            index["bank_certificate_foreign_taxable_by_item"][
                "__bank_certificate_foreign_tax__:DE_BANK_A"
            ],
            D("400.00"),
        )


if __name__ == "__main__":
    unittest.main()
