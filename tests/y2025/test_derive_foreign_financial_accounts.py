"""Tests for ``derive_foreign_financial_accounts_2025`` and the loader
integration with the auto-derived stub CSV.

Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03).

Authority:
- 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
- 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
- 26 CFR § 1.6038D-3 — https://www.law.cornell.edu/cfr/text/26/1.6038D-3
- 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
- 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
"""
from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from tax_pipeline.y2025.derive_foreign_financial_accounts import (
    DERIVED_FFA_FILENAME,
    derive_foreign_financial_accounts_2025,
    write_foreign_financial_accounts_2025,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.us_inputs import load_us_fatca_fbar_inputs_2025


def _build_workspace(tmpdir: Path) -> YearPaths:
    """Build a minimal workspace under ``tmpdir`` with empty config /
    facts trees and a primary-tax-residence-DE profile.

    Returns the resolved ``YearPaths``. Caller owns ``tmpdir`` lifetime.
    """
    paths = YearPaths.for_workspace(tmpdir, tmpdir, 2025)
    paths.ensure_directories()
    profile = {
        "primary_tax_residence": "DE",
        "us_citizen_or_long_term_resident": True,
        "jurisdictions": {"usa": {"filing_posture": "mfs_nra_spouse"}},
    }
    paths.profile_path.write_text(json.dumps(profile), encoding="utf-8")
    paths.manual_overrides_path.write_text("{}", encoding="utf-8")
    return paths


def _seed_fact(
    paths: YearPaths,
    *,
    relative_path: str,
    country: str,
    family: str,
    owner: str = "None",
) -> None:
    """Seed a single facts.md + index.json entry for one document."""
    md_relative = Path(
        "normalized/facts"
    ) / f"{relative_path.replace('/', '_').replace('.', '_')}.facts.md"
    md_full = paths.workspace_root / md_relative
    md_full.parent.mkdir(parents=True, exist_ok=True)
    md_full.write_text(
        "\n".join(
            [
                f"# Facts For {relative_path}",
                "",
                "- doc type: `synthetic`",
                "- parser: `synthetic.v1`",
                "- provider: `synthetic`",
                f"- document family: `{family}`",
                f"- country of origin: `{country}`",
                f"- owner: `{owner}`",
                "- tax year: `2025`",
                "- status: `ok`",
                "- facts: `0`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    index_path = paths.facts_root / "index.json"
    if index_path.exists():
        existing = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        existing = []
    existing.append(
        {
            "relative_path": relative_path,
            "doc_type": "synthetic",
            "status": "ok",
            "facts_count": 0,
            "json_path": str(md_relative.with_suffix(".json")),
            "markdown_path": str(md_relative),
        }
    )
    index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


class DeriveForeignFinancialAccountsTest(unittest.TestCase):
    """Per Reg. § 1.6038D-3(a) the rule needs an enumeration of the
    user's foreign accounts; the derivation builds a stub list from
    extracted facts so the manual-determination renderer can address
    each by id.
    """

    def test_no_index_returns_empty_tuple(self) -> None:
        # Empty workspace → no facts → no discovered accounts.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            self.assertEqual(derive_foreign_financial_accounts_2025(paths), ())

    def test_us_documents_are_excluded(self) -> None:
        # A Schwab 1099 / Coinbase fact entry must NEVER produce a
        # foreign-account row — Schwab and Coinbase are U.S. custodians
        # under 31 CFR § 1010.350(c) and an account at a U.S. financial
        # institution is not a foreign account, even when it holds
        # foreign-issued securities.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="brokers/schwab.pdf",
                country="US",
                family="1099_composite",
            )
            _seed_fact(
                paths,
                relative_path="crypto/coinbase.pdf",
                country="US",
                family="1099_da",
            )
            self.assertEqual(derive_foreign_financial_accounts_2025(paths), ())

    def test_german_capital_certificate_is_discovered_as_brokerage(self) -> None:
        # Reg. § 1.6038D-3(a) — a foreign brokerage account is SFFA.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="germany/Upvest-Jahressteuerbescheinigung.pdf",
                country="DE",
                family="capital_certificate",
            )
            accounts = derive_foreign_financial_accounts_2025(paths)
            self.assertEqual(len(accounts), 1)
            account = accounts[0]
            self.assertEqual(account.country, "DE")
            self.assertEqual(account.account_type, "brokerage")
            self.assertEqual(account.currency, "EUR")
            self.assertTrue(account.is_specified_foreign_financial_asset)
            self.assertEqual(account.data_completeness, "balance_unknown")

    def test_n26_transfer_confirmation_is_discovered_as_bank(self) -> None:
        # N26 is a German bank; the transfer-confirmation document is
        # the only direct evidence Brenn uses an N26 account but it is
        # sufficient to pull it into the FBAR / Form 8938 enumeration.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="us/N26-transfer.pdf",
                country="DE",
                family="transfer_confirmation",
            )
            accounts = derive_foreign_financial_accounts_2025(paths)
            self.assertEqual(len(accounts), 1)
            self.assertEqual(accounts[0].institution, "N26")
            self.assertEqual(accounts[0].account_type, "bank")

    def test_write_csv_is_idempotent_and_sorted(self) -> None:
        # The on-disk CSV is byte-stable across re-runs.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="germany/Upvest.pdf",
                country="DE",
                family="capital_certificate",
            )
            _seed_fact(
                paths,
                relative_path="us/N26-transfer.pdf",
                country="DE",
                family="transfer_confirmation",
            )
            out1, count1 = write_foreign_financial_accounts_2025(paths)
            text1 = out1.read_text(encoding="utf-8")
            out2, count2 = write_foreign_financial_accounts_2025(paths)
            text2 = out2.read_text(encoding="utf-8")
            self.assertEqual(text1, text2)
            self.assertEqual(count1, count2)
            self.assertEqual(count1, 2)
            self.assertEqual(out1.name, DERIVED_FFA_FILENAME)


class LoaderReadsDerivedStubsTest(unittest.TestCase):
    """``load_us_fatca_fbar_inputs_2025`` reads the derived stub CSV
    when the manual one is absent. The auto-derived stubs flow through
    to ``inputs.accounts`` so the rule's fail-closed branch can
    enumerate them in the reason string for the renderer.
    """

    def test_derived_csv_populates_accounts_with_data_complete_false(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="germany/Upvest.pdf",
                country="DE",
                family="capital_certificate",
            )
            write_foreign_financial_accounts_2025(paths)
            inputs = load_us_fatca_fbar_inputs_2025(
                paths, filing_status_label="Married filing separately"
            )
            self.assertFalse(inputs.data_complete)
            self.assertEqual(len(inputs.accounts), 1)
            account = inputs.accounts[0]
            self.assertEqual(account.country, "DE")
            self.assertEqual(account.account_type, "brokerage")
            # Balances are zero placeholders — the loader reads the
            # data_completeness column but the rule only flips
            # data_complete=True via the sentinel row OR the marker.
            self.assertEqual(account.usd_eoy_balance, Decimal("0.00"))
            self.assertEqual(account.usd_max_balance_during_year, Decimal("0.00"))

    def test_manual_csv_takes_precedence_over_derived(self) -> None:
        # When BOTH files exist the manual CSV wins (authoritative).
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            _seed_fact(
                paths,
                relative_path="germany/Upvest.pdf",
                country="DE",
                family="capital_certificate",
            )
            write_foreign_financial_accounts_2025(paths)
            manual = paths.facts_root / "foreign-financial-accounts.csv"
            manual.write_text(
                "account_id,country,institution,account_type,currency,"
                "usd_max_balance_during_year,usd_eoy_balance,"
                "is_specified_foreign_financial_asset\n"
                "manual_n26,DE,N26,bank,EUR,15000,12000,true\n"
                "__data_complete__,,,,,,,,\n",
                encoding="utf-8",
            )
            inputs = load_us_fatca_fbar_inputs_2025(
                paths, filing_status_label="Married filing separately"
            )
            self.assertTrue(inputs.data_complete)
            self.assertEqual(len(inputs.accounts), 1)
            self.assertEqual(inputs.accounts[0].account_id, "manual_n26")
            self.assertEqual(
                inputs.accounts[0].usd_eoy_balance, Decimal("12000")
            )

    def test_derived_csv_with_sentinel_row_rejected(self) -> None:
        # Defensive: if a workspace ever stamps __data_complete__ on
        # the derived stub CSV, the loader rejects loudly. The derived
        # stub is by-construction balance-unknown — letting it claim
        # data_complete=True would silently bypass the fail-closed
        # contract under § 6038D.
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            paths = _build_workspace(tmp)
            derived_path = paths.tax_positions_root / DERIVED_FFA_FILENAME
            paths.tax_positions_root.mkdir(parents=True, exist_ok=True)
            derived_path.write_text(
                "account_id,country,institution,account_type,currency,"
                "usd_max_balance_during_year,usd_eoy_balance,"
                "is_specified_foreign_financial_asset,data_completeness,"
                "evidence_source,owner_note\n"
                "stub_n26,DE,N26,bank,EUR,0.00,0.00,true,balance_unknown,test,test\n"
                "__data_complete__,,,,,,,,,,\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_us_fatca_fbar_inputs_2025(
                    paths, filing_status_label="Married filing separately"
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
