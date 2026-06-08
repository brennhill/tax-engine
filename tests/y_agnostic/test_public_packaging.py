from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class PublicPackagingTest(unittest.TestCase):
    def test_pyproject_declares_console_scripts(self) -> None:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        self.assertTrue(pyproject.exists(), "pyproject.toml should exist for public packaging")

        payload = tomllib.loads(pyproject.read_text())
        build_system = payload["build-system"]
        project = payload["project"]
        scripts = project["scripts"]

        self.assertEqual(project["name"], "tax-year-pipeline")
        self.assertEqual(build_system["build-backend"], "local_backend")
        self.assertEqual(build_system["backend-path"], ["."])
        self.assertEqual(scripts["tax-pipeline-run"], "tax_pipeline.run_year:main")
        self.assertEqual(scripts["tax-pipeline-scaffold"], "tax_pipeline.scaffold_year:main")
        self.assertEqual(scripts["tax-pipeline-validate"], "tax_pipeline.validate_workspace:main")
        self.assertEqual(scripts["tax-pipeline-demo"], "tax_pipeline.demo_workspace:main")
        self.assertEqual(scripts["tax-pipeline-intake"], "tax_pipeline.intake_app:main")

    def test_contributing_documents_public_synthetic_workflow(self) -> None:
        contributing = PROJECT_ROOT / "CONTRIBUTING.md"
        self.assertTrue(contributing.exists(), "CONTRIBUTING.md should exist for public contributors")
        text = contributing.read_text()

        # uv-managed dependency workflow (replaces the older
        # `python3 -m venv .venv` + `pip install -e .` instructions).
        self.assertIn("uv sync", text)
        self.assertIn(".venv", text)
        self.assertIn("demo-2025", text)
        self.assertIn("python -m unittest discover -s tests -v", text)
        self.assertIn("synthetic", text.lower())
        self.assertIn("do not add real taxpayer data", text.lower())

    def test_public_docs_link_parser_contributor_contract_and_support_boundaries(self) -> None:
        guide = PROJECT_ROOT / "docs" / "parser-contributor-guide.md"
        provider_support = PROJECT_ROOT / "docs" / "provider-support.md"
        readme = PROJECT_ROOT / "README.md"
        support_matrix = PROJECT_ROOT / "docs" / "support-matrix.md"

        self.assertTrue(guide.exists(), "Parser contributor guide should exist for public contributors")

        guide_text = guide.read_text()
        provider_text = provider_support.read_text()
        readme_text = readme.read_text()
        support_text = support_matrix.read_text()

        self.assertIn("classifier rule", guide_text.lower())
        self.assertIn("registry registration", guide_text.lower())
        self.assertIn("conformance tests", guide_text.lower())
        self.assertIn("unsupported", guide_text.lower())
        self.assertIn("parser-contributor-guide.md", provider_text)
        self.assertIn("parser-contributor-guide.md", readme_text)
        self.assertIn("married_joint", support_text)
        self.assertIn("nra spouse", support_text.lower())
        self.assertIn("2025", support_text)

    def test_readme_and_support_docs_publish_intake_wizard_as_end_user_flow(self) -> None:
        readme_text = (PROJECT_ROOT / "README.md").read_text()
        support_text = (PROJECT_ROOT / "docs" / "support-matrix.md").read_text()
        provider_text = (PROJECT_ROOT / "docs" / "provider-support.md").read_text()

        self.assertIn("tax-pipeline-intake", readme_text)
        self.assertIn("preferred end-user flow", readme_text.lower())
        self.assertIn("local intake wizard", readme_text.lower())
        self.assertIn("upload", readme_text.lower())
        self.assertIn("wizard", support_text.lower())
        self.assertIn("unsupported documents", provider_text.lower())
        self.assertIn("evidence-only", provider_text.lower())


if __name__ == "__main__":
    unittest.main()
