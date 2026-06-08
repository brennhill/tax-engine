from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tax_pipeline.y2025.germany_law import (
    NON_RULE_PUBLIC_HELPERS_2025 as DE_NON_RULE_PUBLIC_HELPERS_2025,
    REGISTERED_LAW_FUNCTIONS_2025 as DE_REGISTERED_LAW_FUNCTIONS_2025,
)
from tax_pipeline.y2025.germany_stages import (
    germany_capital_law_stages_2025,
    germany_children_law_stages_2025,
    germany_ordinary_law_stages_2025,
)
from tax_pipeline.y2025.us_law import (
    NON_RULE_PUBLIC_HELPERS_2025 as US_NON_RULE_PUBLIC_HELPERS_2025,
    REGISTERED_LAW_FUNCTIONS_2025 as US_REGISTERED_LAW_FUNCTIONS_2025,
)
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _public_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }


class LegalArchitectureEnforcementTest(unittest.TestCase):
    def test_public_law_functions_are_registered_or_explicitly_marked_non_rule_helpers(self) -> None:
        # Public functions in law modules are part of the audit surface. A new
        # public calculation must either be registered to legal stages or be
        # explicitly marked as a non-rule helper; otherwise it can bypass the graph.
        checks = (
            (
                PROJECT_ROOT / "tax_pipeline" / "y2025" / "germany_law.py",
                DE_REGISTERED_LAW_FUNCTIONS_2025,
                DE_NON_RULE_PUBLIC_HELPERS_2025,
            ),
            (
                PROJECT_ROOT / "tax_pipeline" / "y2025" / "us_law.py",
                US_REGISTERED_LAW_FUNCTIONS_2025,
                US_NON_RULE_PUBLIC_HELPERS_2025,
            ),
        )
        for path, registered, helpers in checks:
            with self.subTest(path=path.name):
                public = _public_functions(path)
                self.assertEqual(public - set(registered) - set(helpers), set())
                self.assertEqual(set(registered) - public, set())
                self.assertEqual(set(helpers) - public, set())

    def test_registered_law_functions_reference_declared_stage_ids(self) -> None:
        declared_stage_ids = {
            *(stage.stage_id for stage in germany_ordinary_law_stages_2025()),
            *(stage.stage_id for stage in germany_capital_law_stages_2025()),
            *(stage.stage_id for stage in germany_children_law_stages_2025()),
            *(stage.stage_id for stage in usa_law_stages_2025()),
        }
        for registry in (DE_REGISTERED_LAW_FUNCTIONS_2025, US_REGISTERED_LAW_FUNCTIONS_2025):
            for function_name, stage_ids in registry.items():
                with self.subTest(function_name=function_name):
                    self.assertTrue(stage_ids)
                    self.assertTrue(set(stage_ids).issubset(declared_stage_ids))


if __name__ == "__main__":
    unittest.main()
