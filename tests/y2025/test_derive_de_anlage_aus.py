"""Tests for ``derive_de_anlage_aus_2025`` (Phase 5.3 of FORM-MAPPING-
FOLLOWUP, 2026-05-03).

Authority:
- § 34c Abs. 1 EStG — https://www.gesetze-im-internet.de/estg/__34c.html
- § 32d Abs. 5 EStG — https://www.gesetze-im-internet.de/estg/__32d.html
- DBA-USA Art. 10 / Art. 23 — https://www.irs.gov/pub/irs-trty/germany.pdf
- IRS Pub. 514 — https://www.irs.gov/publications/p514
- ELSTER help (Anlage AUS 2025) —
  https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025
"""
from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.y2025.derive_de_anlage_aus import (
    DE_ANLAGE_AUS_FILENAME,
    derive_anlage_aus_by_country_2025,
    write_anlage_aus_by_country_2025,
)
from tax_pipeline.paths import YearPaths


def _build_workspace(tmpdir: Path) -> YearPaths:
    paths = YearPaths.for_workspace(tmpdir, tmpdir, 2025)
    paths.ensure_directories()
    profile = {
        "primary_tax_residence": "DE",
        "us_citizen_or_long_term_resident": True,
        "jurisdictions": {
            "germany": {"filing_posture": "married_joint"},
            "usa": {"filing_posture": "mfs_nra_spouse"},
        },
    }
    paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")
    paths.manual_overrides_path.write_text("{}", encoding="utf-8")
    return paths


def _seed_treaty_csv(paths: YearPaths, rows: list[dict[str, str]]) -> None:
    """Write a minimal de-us-treaty-dividend-items.csv with the columns
    derive_anlage_aus_by_country_2025 reads."""
    paths.tax_positions_root.mkdir(parents=True, exist_ok=True)
    out = paths.tax_positions_root / "de-us-treaty-dividend-items.csv"
    fieldnames = [
        "item_id",
        "owner_slot",
        "gross_dividend_eur",
        "german_taxable_dividend_eur",
        "allocated_us_tax_paid_eur",
        "treaty_rate",
        "dividend_class",
        "source",
        "note",
    ]
    with out.open("w", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            handle.write(",".join(row.get(k, "") for k in fieldnames) + "\n")


def _seed_1099_div_detail(paths: YearPaths, rows: list[dict[str, str]]) -> None:
    out = paths.derived_facts_root / "usa" / "1099-div-detail.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "name",
        "cusip",
        "box_1a_total_usd",
        "box_2a_total_usd",
        "box_3_total_usd",
        "box_5_199a_dividends_usd",
        "box_7_foreign_tax_paid_usd",
        "foreign_tax_country",
        "note",
    ]
    with out.open("w", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            handle.write(",".join(row.get(k, "") for k in fieldnames) + "\n")


def _seed_cashflows(paths: YearPaths, rows: list[dict[str, str]]) -> None:
    out = paths.derived_facts_root / "germany" / "income-cashflows.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "date",
        "action",
        "kind",
        "symbol",
        "description",
        "asset_bucket",
        "usd_amount",
        "usd_eur_rate",
        "eur_amount",
        "refund_entitlement_eur",
        "foreign_tax_item_id",
        "us_1099_box",
    ]
    with out.open("w", encoding="utf-8") as handle:
        handle.write(",".join(fieldnames) + "\n")
        for row in rows:
            handle.write(",".join(row.get(k, "") for k in fieldnames) + "\n")


def _seed_bank_cert(paths: YearPaths, foreign_tax_credit_eur: str) -> None:
    out = paths.facts_root / "de-spouse-bank-capital-certificate.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "section,key,value,source,note\n"
        f"spouse_bank_capital,lien_bank_foreign_tax_credit_eur,{foreign_tax_credit_eur},test.pdf,test\n",
        encoding="utf-8",
    )


class TreatyUSRowAggregationTest(unittest.TestCase):
    """DBA-USA Art. 10/23: U.S.-source portfolio dividends aggregate to
    a single Anlage AUS country block ``Land = USA``."""

    def test_treaty_csv_aggregates_to_single_us_row(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_treaty_csv(
                paths,
                [
                    {
                        "item_id": "amza_2025_person_1",
                        "gross_dividend_eur": "100.00",
                        "allocated_us_tax_paid_eur": "15.00",
                    },
                    {
                        "item_id": "main_2025_person_1",
                        "gross_dividend_eur": "200.00",
                        "allocated_us_tax_paid_eur": "30.00",
                    },
                ],
            )
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            us_row = rows[0]
            self.assertEqual(us_row.country, "US")
            self.assertEqual(us_row.income_type, "capital_dividend")
            self.assertEqual(us_row.foreign_income_eur, Decimal("300.00"))
            self.assertEqual(us_row.foreign_tax_eur, Decimal("45.00"))
            self.assertEqual(us_row.anrechenbar_eur, Decimal("45.00"))


class NonTreaty1099CountryAggregationTest(unittest.TestCase):
    """1099-div-detail Box 7 + foreign_tax_country aggregates by country.
    For each country: sum Box 7 (USD source-currency) and the matching
    EUR-translated foreign_tax row in income-cashflows.
    """

    def test_canadian_dividend_with_eur_cashflow_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_1099_div_detail(
                paths,
                [
                    {
                        "symbol": "ENB",
                        "box_7_foreign_tax_paid_usd": "15.23",
                        "foreign_tax_country": "CANADA",
                    }
                ],
            )
            _seed_cashflows(
                paths,
                [
                    {"symbol": "ENB", "kind": "dividend", "eur_amount": "90.18"},
                    {"symbol": "ENB", "kind": "foreign_tax", "eur_amount": "13.53"},
                ],
            )
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row.country, "CANADA")
            self.assertEqual(row.foreign_tax_source_amount, Decimal("15.23"))
            self.assertEqual(row.foreign_tax_eur, Decimal("13.53"))
            self.assertEqual(row.foreign_income_eur, Decimal("90.18"))

    def test_ric_pass_through_country_is_preserved(self) -> None:
        # RIC = Regulated Investment Company; the bucket has no per-
        # country breakdown from the fund administrator. Surface as
        # country="RIC" so the user reclassifies before filing.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_1099_div_detail(
                paths,
                [
                    {
                        "symbol": "VXUS",
                        "box_7_foreign_tax_paid_usd": "34.86",
                        "foreign_tax_country": "RIC",
                    }
                ],
            )
            _seed_cashflows(paths, [])
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].country, "RIC")
            self.assertEqual(rows[0].foreign_tax_source_amount, Decimal("34.86"))


class BankCertificateRowTest(unittest.TestCase):
    """The German bank certificate's already-credited foreign tax (Zeile
    40 Anlage KAP) surfaces as country="UNKNOWN" so the per-country
    sum reconciles to the aggregate ``foreign_tax_credit_applied_eur``.
    """

    def test_bank_credited_row_emitted_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_bank_cert(paths, "15.78")
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].country, "UNKNOWN")
            self.assertEqual(rows[0].anrechenbar_eur, Decimal("15.78"))
            self.assertEqual(
                rows[0].income_type, "capital_dividend_bank_credited"
            )

    def test_zero_bank_credit_is_not_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_bank_cert(paths, "0.00")
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(rows, ())


class WriteAnlageAusCsvTest(unittest.TestCase):
    """Idempotent CSV writer; the on-disk byte content is stable across
    re-runs.
    """

    def test_write_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_treaty_csv(
                paths,
                [
                    {
                        "item_id": "amza_2025_person_1",
                        "gross_dividend_eur": "100.00",
                        "allocated_us_tax_paid_eur": "15.00",
                    }
                ],
            )
            out1, count1 = write_anlage_aus_by_country_2025(paths)
            text1 = out1.read_text(encoding="utf-8")
            out2, count2 = write_anlage_aus_by_country_2025(paths)
            text2 = out2.read_text(encoding="utf-8")
            self.assertEqual(text1, text2)
            self.assertEqual(count1, count2)
            self.assertEqual(out1.name, DE_ANLAGE_AUS_FILENAME)


class ReconciliationAgainstAggregateTest(unittest.TestCase):
    """The per-country sum of ``anrechenbar_eur`` must reconcile with the
    aggregate ``de.capital.foreign_tax_credit_applied_eur`` scalar
    emitted by DE25-18 within rounding tolerance.

    For brenn-2025 (engine output): aggregate = 1221.42 EUR; per-country
    sum should be 1221.41 (off by 0.01 EUR — q2 rounding noise).
    """

    def test_brenn_2025_per_country_sum_within_rounding_of_aggregate(self) -> None:
        # This is a self-contained reconciliation against the live
        # brenn-2025 derivation — the test re-runs the derivation
        # against the actual workspace files and compares against the
        # known aggregate.
        project_root = Path(__file__).resolve().parents[2]
        workspace_root = project_root / "years" / "brenn-2025"
        if not workspace_root.exists():
            self.skipTest("brenn-2025 workspace not present in this checkout")
        paths = YearPaths.for_workspace(project_root, workspace_root, 2025)
        rows = derive_anlage_aus_by_country_2025(paths)
        if not rows:
            self.skipTest("brenn-2025 derivation produced no rows")
        per_country_sum = sum(
            (row.anrechenbar_eur for row in rows), Decimal("0.00")
        )
        # Read the aggregate from germany-model-results.json.
        results_path = paths.analysis_root / "germany-model-results.json"
        if not results_path.exists():
            self.skipTest("germany-model-results.json missing; run pipeline first")
        results = json.loads(results_path.read_text(encoding="utf-8"))
        aggregate = Decimal(
            str(results["capital"]["foreign_tax_credit_applied_eur"])
        )
        # Reconciliation tolerance: 0.01 EUR per row (q2 rounding noise).
        tolerance = Decimal("0.01") * Decimal(len(rows))
        self.assertLessEqual(
            abs(per_country_sum - aggregate),
            tolerance,
            f"per-country sum {per_country_sum} EUR diverges from aggregate "
            f"{aggregate} EUR by more than {tolerance} EUR rounding tolerance",
        )


class ManualOverridesTest(unittest.TestCase):
    """``manual_overrides.anlage_aus`` lets the user reclassify the
    ``country="RIC"`` (1099 RIC pass-through) and ``country="UNKNOWN"``
    (German bank-credited foreign tax) rows once the underlying fund
    administrator or depository has supplied a country-of-source
    breakdown.

    The override is pure label substitution: it never changes Decimal
    amounts, only the ``country`` label that flows to Anlage AUS
    Zeile 4. Invariant I5 (no Decimal arithmetic outside the rule
    graph) stays intact.
    """

    def _write_overrides(self, paths: YearPaths, overrides: dict) -> None:
        paths.manual_overrides_path.write_text(
            json.dumps({"anlage_aus": overrides}), encoding="utf-8"
        )

    def test_ric_country_override_relabels_country_only(self) -> None:
        # Without override: country="RIC". With override: country="JP".
        # Decimal amounts (foreign_tax_source_amount, etc.) unchanged.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            self._write_overrides(
                paths,
                {
                    "ric_country_breakdown": {
                        "VXUS": {
                            "country": "JP",
                            "note": "Vanguard 2025 supplemental",
                        },
                    },
                },
            )
            _seed_1099_div_detail(
                paths,
                [
                    {
                        "symbol": "VXUS",
                        "box_7_foreign_tax_paid_usd": "34.86",
                        "foreign_tax_country": "RIC",
                    }
                ],
            )
            _seed_cashflows(paths, [])
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].country, "JP")
            self.assertEqual(rows[0].foreign_tax_source_amount, Decimal("34.86"))

    def test_ric_override_absent_falls_back_to_ric_label(self) -> None:
        # Empty override section: country stays as "RIC" (Verschiedene).
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            self._write_overrides(paths, {"ric_country_breakdown": {}})
            _seed_1099_div_detail(
                paths,
                [
                    {
                        "symbol": "VXUS",
                        "box_7_foreign_tax_paid_usd": "34.86",
                        "foreign_tax_country": "RIC",
                    }
                ],
            )
            _seed_cashflows(paths, [])
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(rows[0].country, "RIC")

    def test_bank_certificate_override_relabels_country_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            self._write_overrides(
                paths,
                {
                    "bank_certificate_country": {
                        "lien_bank_foreign_tax_credit_eur": {
                            "country": "JP",
                            "note": "Upvest custodian breakdown",
                        }
                    }
                },
            )
            _seed_bank_cert(paths, "15.78")
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].country, "JP")
            self.assertEqual(rows[0].anrechenbar_eur, Decimal("15.78"))

    def test_bank_certificate_override_absent_falls_back_to_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            # No anlage_aus overrides at all.
            paths.manual_overrides_path.write_text("{}", encoding="utf-8")
            _seed_bank_cert(paths, "15.78")
            rows = derive_anlage_aus_by_country_2025(paths)
            self.assertEqual(rows[0].country, "UNKNOWN")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
