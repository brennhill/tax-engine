"""Round-trip test for the F4 carryforward auto-export.

The carryforward auto-export module (``tax_pipeline/y2025/carryforward_export.py``,
W1.B / T2.1) emits ``carryforward-out-<juri>.csv`` files under
``outputs/`` whose schema must match the loader-side CSVs that next
year's pipeline will consume (today: ``years/<next>/normalized/facts/
de-loss-carryforwards.csv`` and ``us-carryovers-and-payments.csv``).

This test proves the year-boundary contract:

  1. Run the demo-2025 pipeline end-to-end against a tempdir workspace.
  2. Read the resulting carryforward-out CSVs.
  3. Re-parse them with the same loader-shape ``csv.DictReader`` that
     ``tax_pipeline.analysis_inputs._read_row_csv`` uses, then convert
     each ``value`` to ``Decimal`` exactly like
     ``_rows_to_decimal_map`` does.
  4. Assert the round-tripped Decimals equal the rule-graph outputs in
     ``final-legal-output.json`` at the original key locations.

A live 2026 workspace does not exist yet — full 2026 pipeline coverage
follows under Y1 (roll-forward harness) per the 2026-05-10 review §5.
For F4 it is sufficient to prove the CSV bytes are loader-consumable
in the loader's existing shape; the key-rename from 2025 to 2026
(``stock_loss_carryforward_2025_eur`` → next year's input key) is the
2026 loader's responsibility, not this export's.

Authority context: § 20 Abs. 6 EStG, § 23 Abs. 3 Sätze 7-9 EStG,
26 U.S.C. §§ 1211-1212. Same authorities cited in the export module
and (in the next year) in the loader-side CSV ``note`` column.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

from tax_pipeline.analysis_inputs import CSV_FIELDS
from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.run_year import run_year
from tax_pipeline.y2025.carryforward_export import (
    DE_CARRYFORWARD_OUT_FILENAME,
    US_CARRYFORWARD_OUT_FILENAME,
    build_de_carryforward_rows,
    build_us_carryforward_rows,
    export_carryforwards_2025,
)


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    """Re-parse a carryforward-out CSV the same way the loader does.

    Mirrors the loader-side ``_read_row_csv`` in
    ``tax_pipeline.analysis_inputs`` so the test exercises the same
    reader shape the 2026 pipeline will use.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in reader
        ]


def _rows_to_decimal_map(rows: list[dict[str, str]]) -> dict[str, Decimal]:
    """Same shape as ``analysis_inputs._rows_to_decimal_map``."""
    return {row["key"]: Decimal(row["value"]) for row in rows}


class CarryforwardExportSchemaTest(unittest.TestCase):
    """Schema-only checks that don't require a pipeline run.

    Builds the export rows from a minimal in-memory final-legal-output
    skeleton so the schema invariant is exercised without paying the
    cost of the full demo pipeline. The end-to-end round-trip in
    ``CarryforwardRoundTripTest`` covers the integration.
    """

    def _final_output_skeleton(self) -> dict[str, object]:
        # Mirrors the relevant subset of years/<ws>/outputs/analysis-
        # steps/final-legal-output.json that the export reads.
        return {
            "germany": {
                "forms": {
                    "results": {
                        "capital": {
                            "stock_loss_carryforward_remaining_eur": "123.45",
                        },
                        "private_sales": {
                            "updated_private_sale_carryforward_eur": "678.90",
                        },
                    }
                }
            },
            "usa": {
                "forms": {
                    "capital_results": {
                        "capital": {
                            "tentative_capital_loss_carryforward_2026_usd": "999.99",
                        }
                    }
                }
            },
        }

    def test_de_rows_match_loader_schema(self) -> None:
        rows = build_de_carryforward_rows(self._final_output_skeleton())
        for row in rows:
            self.assertEqual(set(row.keys()), set(CSV_FIELDS))

    def test_us_rows_match_loader_schema(self) -> None:
        rows = build_us_carryforward_rows(self._final_output_skeleton())
        for row in rows:
            self.assertEqual(set(row.keys()), set(CSV_FIELDS))

    def test_de_rows_emit_2025_year_stamped_keys(self) -> None:
        # The exported keys advance the year stamp from the prior
        # year's loader (``_2024_eur``) to the current year's end-of-
        # year balance (``_2025_eur``). Matching the loader's
        # established naming convention keeps the 2026 loader's
        # 2025-stamp-aware code path single-key, single-§.
        rows = build_de_carryforward_rows(self._final_output_skeleton())
        keys = {row["key"] for row in rows}
        self.assertEqual(
            keys,
            {
                "stock_loss_carryforward_2025_eur",
                "private_sale_loss_carryforward_2025_eur",
            },
        )

    def test_us_row_uses_engine_existing_key_name(self) -> None:
        # The engine's existing output key already names 2026 in its
        # name (``tentative_capital_loss_carryforward_2026_usd``). The
        # export preserves the 2026 year stamp under a renamed key
        # (``capital_loss_carryforward_into_2026_usd``) so the next
        # year's loader can address it directly.
        rows = build_us_carryforward_rows(self._final_output_skeleton())
        keys = {row["key"] for row in rows}
        self.assertEqual(keys, {"capital_loss_carryforward_into_2026_usd"})

    def test_disabled_germany_emits_no_rows(self) -> None:
        # CLAUDE.md invariant I13: a not_applicable jurisdiction
        # produces no rows (the absence IS the audit posture).
        final_output: dict[str, object] = {
            "germany": {"forms": {"status": "not_applicable"}},
            "usa": {"forms": {"status": "not_applicable"}},
        }
        self.assertEqual(build_de_carryforward_rows(final_output), [])
        self.assertEqual(build_us_carryforward_rows(final_output), [])

    def test_missing_input_fails_closed(self) -> None:
        # Per CLAUDE.md "fail closed; never silently default to zero":
        # an absent carryforward output must raise rather than write
        # 0.00 (which would corrupt the next year's loader by
        # fabricating a zeroed-out carryforward state).
        final_output: dict[str, object] = {
            "germany": {"forms": {"results": {"capital": {}, "private_sales": {}}}}
        }
        with self.assertRaises(KeyError):
            build_de_carryforward_rows(final_output)

    def test_decimal_values_round_trip_through_csv(self) -> None:
        # A CSV-written value must parse back to the same Decimal.
        # This is the load-bearing property: the 2026 loader's
        # ``_rows_to_decimal_map`` is a thin csv.DictReader + Decimal()
        # wrapper, so anything that round-trips through Python's csv
        # module + Decimal() round-trips for the loader too.
        from tax_pipeline.y2025.carryforward_export import render_carryforward_csv

        rows = build_de_carryforward_rows(self._final_output_skeleton())
        rendered = render_carryforward_csv(rows)
        reparsed = list(csv.DictReader(io.StringIO(rendered)))
        self.assertEqual(
            Decimal(reparsed[0]["value"]),
            Decimal("123.45"),
        )
        self.assertEqual(
            Decimal(reparsed[1]["value"]),
            Decimal("678.90"),
        )


class CarryforwardRoundTripTest(unittest.TestCase):
    """End-to-end: run the demo pipeline, read the exported CSVs, then
    confirm the loader-shape parser recovers the same Decimal values
    that the rule graph wrote into ``final-legal-output.json``.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        root = Path(cls.tempdir.name)
        cls.paths = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
        with redirect_stdout(io.StringIO()):
            run_year(root, "2025", workspace_root=cls.paths.year_root)
        cls.final_output = json.loads(
            (cls.paths.analysis_root / "final-legal-output.json").read_text(
                encoding="utf-8"
            )
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tempdir.cleanup()

    def test_de_carryforward_out_file_exists(self) -> None:
        path = self.paths.outputs_root / DE_CARRYFORWARD_OUT_FILENAME
        self.assertTrue(
            path.exists(),
            f"Expected carryforward export at {path}",
        )

    def test_us_carryforward_out_file_exists(self) -> None:
        path = self.paths.outputs_root / US_CARRYFORWARD_OUT_FILENAME
        self.assertTrue(
            path.exists(),
            f"Expected carryforward export at {path}",
        )

    def test_de_csv_round_trips_to_rule_graph_outputs(self) -> None:
        # § 20 Abs. 6 EStG stock-loss carryforward remaining at year end +
        # § 23 Abs. 3 Sätze 7-9 EStG updated private-sale-loss carryforward.
        path = self.paths.outputs_root / DE_CARRYFORWARD_OUT_FILENAME
        loaded = _rows_to_decimal_map(_load_csv_rows(path))

        results = self.final_output["germany"]["forms"]["results"]
        expected_stock = Decimal(
            results["capital"]["stock_loss_carryforward_remaining_eur"]
        )
        expected_private = Decimal(
            results["private_sales"]["updated_private_sale_carryforward_eur"]
        )

        self.assertEqual(loaded["stock_loss_carryforward_2025_eur"], expected_stock)
        self.assertEqual(
            loaded["private_sale_loss_carryforward_2025_eur"], expected_private
        )

    def test_us_csv_round_trips_to_rule_graph_outputs(self) -> None:
        # 26 U.S.C. §§ 1211-1212 tentative capital-loss carryforward
        # into 2026.
        path = self.paths.outputs_root / US_CARRYFORWARD_OUT_FILENAME
        loaded = _rows_to_decimal_map(_load_csv_rows(path))

        capital_results = self.final_output["usa"]["forms"]["capital_results"]
        expected_capital_loss = Decimal(
            capital_results["capital"]["tentative_capital_loss_carryforward_2026_usd"]
        )

        self.assertEqual(
            loaded["capital_loss_carryforward_into_2026_usd"],
            expected_capital_loss,
        )

    def test_csv_header_matches_loader_csv_fields(self) -> None:
        # The 2026 loader will consume these CSVs by name. If the
        # header drifts from ``CSV_FIELDS`` the loader's
        # ``_read_row_csv`` returns rows with surprise / missing keys
        # and the next year's run fails closed at an unhelpful point.
        for filename in (DE_CARRYFORWARD_OUT_FILENAME, US_CARRYFORWARD_OUT_FILENAME):
            path = self.paths.outputs_root / filename
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.reader(handle)
                header = next(reader)
            self.assertEqual(header, list(CSV_FIELDS), f"Header drift in {filename}")

    def test_each_row_carries_authority_citation(self) -> None:
        # CLAUDE.md "Tax-Law Rule Requirements" mandates every tax-rule
        # implementation include an official web link to the authority.
        # The carryforward export carries the citation in the ``note``
        # column so a 2026 audit packet can trace each imported value
        # back to its § / 26 U.S.C. basis.
        for filename in (DE_CARRYFORWARD_OUT_FILENAME, US_CARRYFORWARD_OUT_FILENAME):
            path = self.paths.outputs_root / filename
            for row in _load_csv_rows(path):
                self.assertIn(
                    "https://",
                    row["note"],
                    f"Row {row['key']} in {filename} is missing an authority URL",
                )

    def test_export_is_idempotent(self) -> None:
        # Re-running the export with the same final-legal-output must
        # produce byte-identical CSVs. Idempotency is part of the
        # roll-forward contract: a re-run never silently rotates the
        # next year's seed values.
        path_de = self.paths.outputs_root / DE_CARRYFORWARD_OUT_FILENAME
        path_us = self.paths.outputs_root / US_CARRYFORWARD_OUT_FILENAME
        before_de = path_de.read_bytes()
        before_us = path_us.read_bytes()

        export_carryforwards_2025(self.paths, self.final_output)

        self.assertEqual(path_de.read_bytes(), before_de)
        self.assertEqual(path_us.read_bytes(), before_us)


class CarryforwardLoaderConsumabilityTest(unittest.TestCase):
    """The exported CSVs must be readable by the loader-side helpers
    without any export-specific knowledge.

    Today's 2025 loaders consume keys like ``stock_loss_carryforward_2024_eur``
    (prior-year carryforward into 2025). The 2026 loader will consume
    ``stock_loss_carryforward_2025_eur`` — the same shape, year stamp
    advanced. To prove the format is consumable without standing up a
    full 2026 workspace, we render the exported CSVs through the
    loader's own ``csv.DictReader`` + ``Decimal`` round-trip and check
    that every row is well-formed.
    """

    def test_de_csv_decimals_are_well_formed(self) -> None:
        # Build a minimal final-legal-output and run the export to a
        # tempdir. The DE side has non-zero values worth checking.
        from tax_pipeline.y2025.carryforward_export import render_carryforward_csv

        final_output = {
            "germany": {
                "forms": {
                    "results": {
                        "capital": {
                            "stock_loss_carryforward_remaining_eur": "100.50",
                        },
                        "private_sales": {
                            "updated_private_sale_carryforward_eur": "200.75",
                        },
                    }
                }
            }
        }
        rows = build_de_carryforward_rows(final_output)
        rendered = render_carryforward_csv(rows)
        reloaded = list(csv.DictReader(io.StringIO(rendered)))
        as_decimals = _rows_to_decimal_map(reloaded)
        self.assertEqual(as_decimals["stock_loss_carryforward_2025_eur"], Decimal("100.50"))
        self.assertEqual(
            as_decimals["private_sale_loss_carryforward_2025_eur"], Decimal("200.75")
        )


if __name__ == "__main__":
    unittest.main()
