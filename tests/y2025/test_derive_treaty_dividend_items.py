from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.y2025.derive_treaty_dividend_items import (
    DEFAULT_FOREIGN_SOURCE_SYMBOLS,
    TREATY_RATE,
    _looks_auto_generated_treaty_item_id,
    derive_treaty_dividend_items_2025,
)


class DeriveTreatyDividendItemsTest(unittest.TestCase):
    """Pin the auto-derivation of Pub. 514 / DBA-USA Art. 23 treaty
    dividend items from the per-row income-cashflows derived facts.

    Authority for the per-Posten approach:
    - DBA-USA Art. 10 (15 % portfolio dividend cap):
      https://www.irs.gov/pub/irs-trty/germtech.pdf
    - IRS Publication 514 worksheet:
      https://www.irs.gov/publications/p514
    - § 32d Abs. 5 EStG (per-Posten cap):
      https://www.gesetze-im-internet.de/estg/__32d.html
    """

    def _row(self, **kw: str) -> dict[str, str]:
        defaults = {
            "date": "2025-01-15",
            "action": "Cash Dividend",
            "kind": "dividend",
            "symbol": "MAIN",
            "description": "MAIN STR CAP CORP",
            "asset_bucket": "stock",
            "usd_amount": "158.25",
            "usd_eur_rate": "1.03",
            "eur_amount": "153.6408",
            "refund_entitlement_eur": "",
            "foreign_tax_item_id": "",
        }
        defaults.update(kw)
        return defaults

    def test_direct_stock_dividend_becomes_portfolio_dividend_direct_equity(self) -> None:
        # MAIN is a U.S. stock; asset_bucket="stock" → portfolio_dividend / direct_equity.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[self._row()],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(de), 1)
        self.assertEqual(len(us), 1)
        self.assertEqual(de[0]["dividend_class"], "portfolio_dividend")
        self.assertEqual(us[0]["treaty_bucket"], "direct_equity")
        self.assertEqual(de[0]["item_id"], us[0]["item_id"])  # paired by item_id
        self.assertEqual(de[0]["item_id"], "main_2025_person_1")

    def test_aktienfonds_etf_becomes_equity_fund(self) -> None:
        # VOO is an Aktienfonds; asset_bucket="fund_like" + aktienfonds → equity_fund_dividend.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(symbol="VOO", asset_bucket="fund_like", eur_amount="100.00", usd_amount="113.00"),
            ],
            aktienfonds=["VOO"],
            non_aktienfonds=[],
        )
        self.assertEqual(de[0]["dividend_class"], "equity_fund_dividend")
        self.assertEqual(us[0]["treaty_bucket"], "equity_fund")

    def test_non_aktienfonds_etf_becomes_non_equity_fund(self) -> None:
        # AMZA is documented as non_aktienfonds — InvStG § 2 Abs. 6 (<51% equity).
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(symbol="AMZA", asset_bucket="fund_like", eur_amount="3.27", usd_amount="3.38"),
            ],
            aktienfonds=[],
            non_aktienfonds=["AMZA"],
        )
        self.assertEqual(de[0]["dividend_class"], "non_equity_fund_dividend")
        self.assertEqual(us[0]["treaty_bucket"], "non_equity_fund")

    def test_unclassified_fund_like_symbol_fails_closed(self) -> None:
        # InvStG § 2 Abs. 6 EStG requires explicit classification; an unknown
        # fund_like symbol must fail closed instead of silently being treated.
        with self.assertRaisesRegex(ValueError, "fund_classification"):
            derive_treaty_dividend_items_2025(
                income_cashflows_rows=[
                    self._row(symbol="MYSTERY", asset_bucket="fund_like", eur_amount="10.00", usd_amount="11.00"),
                ],
                aktienfonds=[],
                non_aktienfonds=[],
            )

    def test_foreign_source_symbol_is_excluded(self) -> None:
        # ENB Canadian dividends are NOT U.S.-source; Pub. 514 re-sourcing
        # cannot apply. The default foreign-source set excludes them.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(symbol="ENB", asset_bucket="stock", eur_amount="23.10", usd_amount="24.20"),
                self._row(symbol="MAIN", asset_bucket="stock"),
            ],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(de), 1)
        self.assertEqual(de[0]["item_id"].startswith("main_"), True)

    def test_non_dividend_kinds_are_skipped(self) -> None:
        # Only kind=dividend rows enter the treaty packet; foreign_tax,
        # interest, substitute_payment are not treaty-resourced.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(kind="foreign_tax", symbol="ENB"),
                self._row(kind="interest", symbol="MMF"),
                self._row(kind="substitute_payment", symbol="MAIN"),
                self._row(kind="dividend", symbol="MAIN"),
            ],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(de), 1)
        self.assertEqual(de[0]["item_id"].startswith("main_"), True)

    def test_treaty_rate_is_dba_usa_art10_15_percent(self) -> None:
        # DBA-USA Art. 10 portfolio-dividend cap = 15 %; allocated U.S. tax
        # paid at the per-item level uses this rate verbatim.
        # https://www.irs.gov/pub/irs-trty/germtech.pdf
        self.assertEqual(TREATY_RATE, Decimal("0.15"))
        de, _us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[self._row(eur_amount="100.00")],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(de[0]["treaty_rate"], "0.15")
        self.assertEqual(de[0]["allocated_us_tax_paid_eur"], "15.00")

    def test_de_and_us_item_ids_pair_byte_for_byte(self) -> None:
        # The cross-border bridge in tax_pipeline/y2025/treaty_bridge.py
        # matches DE and US items by item_id; bytes must agree exactly.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(symbol="MAIN", date="2025-01-15"),
                self._row(symbol="O", date="2025-01-15", asset_bucket="stock", eur_amount="2.56", usd_amount="2.64"),
                self._row(symbol="VOO", date="2025-01-15", asset_bucket="fund_like", eur_amount="50.00", usd_amount="56.50"),
            ],
            aktienfonds=["VOO"],
            non_aktienfonds=[],
        )
        de_ids = [r["item_id"] for r in de]
        us_ids = [r["item_id"] for r in us]
        self.assertEqual(de_ids, us_ids)

    def test_multiple_rows_same_symbol_aggregate_into_one_item(self) -> None:
        # § 32d Abs. 5 EStG / Pub. 514 treat the residence-country credit on a
        # per-symbol-annual stack. Multiple Schwab payments of the same symbol
        # in the same year collapse into ONE treaty item whose gross is the
        # annual sum. This avoids per-payment quantization drift in the
        # USD-EUR round-trip on the Pub. 514 line 16 ceiling.
        de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(date="2025-01-15", usd_amount="100.00", eur_amount="88.60"),
                self._row(date="2025-04-15", usd_amount="100.00", eur_amount="88.60"),
            ],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(de), 1)
        self.assertEqual(len(us), 1)
        self.assertEqual(de[0]["item_id"], "main_2025_person_1")
        self.assertEqual(us[0]["gross_dividend_usd"], "200.00")
        self.assertEqual(de[0]["gross_dividend_eur"], "177.20")

    def test_zero_or_negative_dividend_rows_are_skipped(self) -> None:
        # Pub. 514 treaty re-sourcing applies to positive dividend amounts
        # only; reclass / return-of-capital corrections are skipped.
        de, _us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(eur_amount="0.00"),
                self._row(eur_amount="-5.00"),
                self._row(eur_amount="153.6408"),
            ],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(de), 1)

    def test_updated_income_cashflows_rows_carry_foreign_tax_item_id(self) -> None:
        # DE25-15 (y2025/germany_capital_rules.py:407) requires the income-
        # cashflows row to carry the same foreign_tax_item_id as the treaty
        # packet item so per-Posten taxable income can be paired with the
        # treaty entry. The derivation must stamp the IDs back onto the
        # corresponding dividend rows.
        original = [
            self._row(symbol="MAIN", date="2025-01-15"),
            self._row(symbol="ENB", asset_bucket="stock", eur_amount="23.10", usd_amount="24.20", date="2025-03-03"),
        ]
        de, _us, updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=original,
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(len(updated), 2)
        # MAIN was eligible: its row got stamped with the treaty item id.
        self.assertEqual(updated[0]["foreign_tax_item_id"], de[0]["item_id"])
        # ENB is foreign-source; its row's foreign_tax_item_id is untouched.
        self.assertEqual(updated[1]["foreign_tax_item_id"], "")

    def test_existing_user_authored_foreign_tax_item_id_is_preserved(self) -> None:
        # If the user (or a prior derivation pass) has already pinned a
        # foreign_tax_item_id on a dividend row, the derivation must NOT
        # overwrite it. The treaty item adopts the user's id so DE25-15
        # still pairs.
        de, _us, updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=[
                self._row(symbol="MAIN", foreign_tax_item_id="manual_main_q1"),
            ],
            aktienfonds=[],
            non_aktienfonds=[],
        )
        self.assertEqual(updated[0]["foreign_tax_item_id"], "manual_main_q1")
        self.assertEqual(de[0]["item_id"], "manual_main_q1")

    def test_per_item_aggregates_match_us_model_assumptions(self) -> None:
        # Sum of per-item gross dividends by treaty_bucket should equal the
        # us_source_*_dividends_usd aggregate values declared in
        # outputs/tax-positions/us-model-assumptions.csv. Pin this
        # invariant so a future refactor cannot let the per-item and
        # aggregate paths drift.
        rows = [
            # direct_equity: $100 + $200 = $300
            self._row(symbol="MAIN", asset_bucket="stock", usd_amount="100.00", eur_amount="88.60"),
            self._row(symbol="O", asset_bucket="stock", date="2025-02-15", usd_amount="200.00", eur_amount="177.20"),
            # equity_fund: $50 + $50 = $100
            self._row(symbol="VOO", asset_bucket="fund_like", date="2025-03-15", usd_amount="50.00", eur_amount="44.30"),
            self._row(symbol="QQQ", asset_bucket="fund_like", date="2025-04-15", usd_amount="50.00", eur_amount="44.30"),
            # non_equity_fund: $30
            self._row(symbol="AMZA", asset_bucket="fund_like", date="2025-05-15", usd_amount="30.00", eur_amount="26.58"),
        ]
        _de, us, _updated = derive_treaty_dividend_items_2025(
            income_cashflows_rows=rows,
            aktienfonds=["VOO", "QQQ"],
            non_aktienfonds=["AMZA"],
        )
        by_bucket = {b: Decimal("0") for b in ("direct_equity", "equity_fund", "non_equity_fund")}
        for r in us:
            by_bucket[r["treaty_bucket"]] += Decimal(r["gross_dividend_usd"])
        self.assertEqual(by_bucket["direct_equity"], Decimal("300.00"))
        self.assertEqual(by_bucket["equity_fund"], Decimal("100.00"))
        self.assertEqual(by_bucket["non_equity_fund"], Decimal("30.00"))


class LooksAutoGeneratedTreatyItemIdTest(unittest.TestCase):
    """Pin the recognition heuristic for prior-run auto-generated foreign_tax_
    item_id values on income-cashflows rows. The auto-derivation overwrites
    only auto-generated ids; user-authored ids must survive untouched.
    """

    # ``(item_id, expected_recognized, note)`` tuples. ``expected_recognized``
    # is True iff ``_looks_auto_generated_treaty_item_id`` should return True
    # for the given id. ``symbol="MAIN"`` and ``owner="person_1"`` for every
    # case so the heuristic is exercised against the same lookup pair.
    _CASES: tuple[tuple[str, bool, str], ...] = (
        ("main_2025_person_1", True, "current per-symbol annual id"),
        ("main_2025_01_15_person_1", True, "legacy per-payment id (Jan 15)"),
        ("main_2025_12_31_person_1", True, "legacy per-payment id (Dec 31)"),
        ("main_2025_01_15_person_1_2", True, "legacy per-payment with collision suffix"),
        ("MAIN_2025_PERSON_1", True, "case-insensitive symbol+owner (upper)"),
        ("Main_2025_Person_1", True, "case-insensitive symbol+owner (mixed)"),
        # Strict MM/DD validation: invalid month/day → user-authored.
        ("main_2025_13_15_person_1", False, "month 13 invalid"),
        ("main_2025_00_15_person_1", False, "month 00 invalid"),
        ("main_2025_01_32_person_1", False, "day 32 invalid"),
        ("main_2025_01_00_person_1", False, "day 00 invalid"),
        # Two-digit groups that look like dates but aren't: user-authored.
        ("main_2025_42_99_person_1", False, "two-digit groups, not MM/DD"),
        ("main_2025_q1_person_1", False, "quarter id"),
        # IDs without the auto-generated prefix shape: user-authored.
        ("manual_main_q1", False, "freeform user id (manual_)"),
        ("schwab-main-2025", False, "freeform user id (schwab-)"),
        # Empty / whitespace: never an auto-generated id.
        ("", False, "empty string"),
        ("   ", False, "whitespace only"),
    )

    def test_recognition_heuristic_matrix(self) -> None:
        for item_id, expected, note in self._CASES:
            with self.subTest(item_id=item_id, note=note):
                self.assertEqual(
                    _looks_auto_generated_treaty_item_id(
                        item_id, symbol="MAIN", owner="person_1"
                    ),
                    expected,
                    f"{note} → expected recognized={expected}",
                )


if __name__ == "__main__":
    unittest.main()
