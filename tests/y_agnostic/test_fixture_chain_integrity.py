from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

from tax_pipeline.demo_workspace import materialize_demo_workspace
from tax_pipeline.run_year import run_year


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _fixture_workspaces() -> tuple[tuple[str, int], ...]:
    fixtures: list[tuple[str, int]] = []
    for path in sorted((PROJECT_ROOT / "years").glob("demo-*")):
        if not path.is_dir():
            continue
        year_text = path.name.rsplit("-", 1)[-1]
        if year_text.isdigit():
            fixtures.append((path.name, int(year_text)))
    return tuple(fixtures)


def _iter_narrative_packets(final_output: dict[str, Any]) -> dict[str, dict[str, Any]]:
    packets: dict[str, dict[str, Any]] = {}
    for country, languages in final_output.get("narratives", {}).items():
        for language, rules in languages.items():
            for rule in rules:
                node_id = f"{country}-{language}-{rule['rule_id']}"
                packets[node_id] = rule
    return packets


class FixtureChainIntegrityTest(unittest.TestCase):
    def test_all_workspace_fixtures_run_and_graph_edges_match_produced_outputs(self) -> None:
        # The self-audit graph is only useful if it is generated from the same
        # end-to-end fixture run as the final legal output. Every producer->consumer
        # edge must preserve the exact output fingerprint, otherwise the graph is
        # just prose metadata rather than an auditable computation chain.
        fixtures = _fixture_workspaces()
        self.assertGreater(len(fixtures), 0, "expected at least one years/demo-* fixture workspace")

        for demo_name, year in fixtures:
            with self.subTest(demo_name=demo_name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    paths = materialize_demo_workspace(root, demo_name=demo_name, year=year)

                    with redirect_stdout(io.StringIO()):
                        run_year(root, str(year), workspace_root=paths.year_root)

                    final_output = json.loads((paths.analysis_root / "final-legal-output.json").read_text())
                    graph = json.loads((paths.analysis_root / "legal-execution-graph.json").read_text())
                    mermaid_exists = (paths.analysis_root / "legal-execution-graph.mmd").exists()

                packets_by_node_id = _iter_narrative_packets(final_output)
                nodes_by_id = {node["node_id"]: node for node in graph["nodes"]}

                self.assertEqual(set(nodes_by_id), set(packets_by_node_id))
                self.assertEqual(len(nodes_by_id), len(graph["nodes"]))
                self.assertTrue(mermaid_exists)

                for node_id, node in nodes_by_id.items():
                    packet = packets_by_node_id[node_id]
                    self.assertEqual(node["template_id"], packet["template_id"])
                    self.assertEqual(node["template_id"], node["rule_id"])
                    self.assertEqual(node["audit_packet_fingerprint"], packet["fingerprint"])
                    self.assertTrue((PROJECT_ROOT / "tax_pipeline/narrative/templates" / f"{node['rule_id']}.jinja").exists())
                    self.assertEqual(node["legal_refs"], packet["legal_refs"])
                    self.assertEqual(node["authority_urls"], packet["authority_urls"])
                    self.assertEqual(node["form_lines"], packet["form_lines"])
                    self.assertEqual(node["input_keys"], [item["key"] for item in packet["inputs"]])
                    self.assertEqual(node["output_keys"], [item["key"] for item in packet["outputs"]])
                    self.assertEqual(set(node["input_fingerprints"]), set(node["input_keys"]))
                    self.assertEqual(set(node["output_fingerprints"]), set(node["output_keys"]))

                for edge in graph["edges"]:
                    producer = nodes_by_id[edge["from_node_id"]]
                    consumer = nodes_by_id[edge["to_node_id"]]
                    self.assertEqual(edge["from_output_key"], edge["to_input_key"])
                    self.assertIn(edge["from_output_key"], producer["output_fingerprints"])
                    self.assertIn(edge["to_input_key"], consumer["input_fingerprints"])
                    self.assertEqual(
                        producer["output_fingerprints"][edge["from_output_key"]],
                        consumer["input_fingerprints"][edge["to_input_key"]],
                        f"{edge['from_node_id']} -> {edge['to_node_id']} must preserve {edge['from_output_key']}",
                    )


if __name__ == "__main__":
    unittest.main()
