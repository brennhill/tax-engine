from __future__ import annotations

import unittest

from tax_pipeline.pipelines.y2025.final_legal_output import write_final_legal_output_2025
from tax_pipeline.pipelines.y2025.verbose_report import render_verbose_report
from tests.generated_demo import generated_demo_paths


class VerboseReportTest(unittest.TestCase):
    def test_verbose_report_shows_high_level_facts_and_law_backed_calculations(self) -> None:
        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)

            report_path = render_verbose_report(paths)

            self.assertEqual(report_path, paths.analysis_root / "verbose-report.md")
            text = report_path.read_text()
            self.assertIn("# Verbose 2025 Tax Calculation Report", text)
            self.assertIn("This report is derived from `final-legal-output.json`; it does not recompute tax.", text)
            self.assertIn("## High-Level Facts", text)
            self.assertIn("### Germany Investment Facts", text)
            self.assertIn("- Stock gains: `1500.00 EUR`", text)
            self.assertIn("- Equity-fund income/gains before Teilfreistellung: `420.00 EUR`", text)
            self.assertIn("### U.S. Investment Facts", text)
            self.assertIn("- Short-term total: `350.00 USD`", text)
            self.assertIn("- Long-term total including capital-gain distributions: `700.00 USD`", text)
            self.assertIn("## Germany Full Calculation Trace", text)
            self.assertIn("| joint_taxable_income |", text)
            self.assertIn("§ 32d Abs. 1 und 5 EStG", text)
            self.assertIn("https://www.gesetze-im-internet.de/estg/__32d.html", text)
            self.assertIn("https://www.gesetze-im-internet.de/estg/__10.html \\| https://www.gesetze-im-internet.de/estg/__10c.html", text)
            self.assertIn("## U.S. Full Calculation Trace", text)
            self.assertIn("| regular_tax_before_credits |", text)
            self.assertIn("26 U.S.C. § 904", text)

    def test_verbose_report_fails_closed_when_trace_lacks_legal_references(self) -> None:
        with generated_demo_paths() as paths:
            (paths.analysis_root / "germany-model-trace.csv").write_text(
                "step,value_eur,note\n"
                "joint_taxable_income,1000.00,no law column\n"
            )
            with self.assertRaisesRegex(ValueError, "Missing required values for germany-model-trace.csv: row 1:legal_reference"):
                write_final_legal_output_2025(paths)

    def test_verbose_report_fails_closed_when_trace_lacks_authority_urls(self) -> None:
        with generated_demo_paths() as paths:
            (paths.analysis_root / "germany-model-trace.csv").write_text(
                "step,value_eur,note,legal_reference,authority_url\n"
                "joint_taxable_income,1000.00,calculation,§ 2 Abs. 5 EStG,\n"
            )
            with self.assertRaisesRegex(ValueError, "Missing required values for germany-model-trace.csv: row 1:authority_url"):
                write_final_legal_output_2025(paths)


if __name__ == "__main__":
    unittest.main()
