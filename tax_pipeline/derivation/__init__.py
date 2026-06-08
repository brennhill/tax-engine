"""Pipeline 1 (Derivation) framework.

The two-pipeline architecture (`docs/invariant-migration-plan.md` §1.5)
splits the engine into:

- Pipeline 1 (Derivation): deterministic transformations of raw inputs
  (per-symbol aggregation, 1099 box filtering, fund classification
  merge, source-country splits, …) into typed canonical derived facts.
  Outputs land in ``derived-facts.json`` + ``derivation-graph.json``.
- Pipeline 2 (Legal): the existing DE25-* / US25-* / TREATY25-* stages
  that read derived facts and apply controlling tax law.

WS-5H lands the empty framework. WS-5A and WS-5B then register the
first concrete derivation stages on top of this scaffold.
"""

from tax_pipeline.derivation.persistence import (
    DERIVATION_FACTS_NAME,
    DERIVATION_GRAPH_NAME,
    derivation_facts_path,
    derivation_graph_path,
    hydrate_germany_capital_derived_facts,
    load_derivation_facts,
    load_germany_capital_derived_facts,
    write_derivation_artifacts,
)
from tax_pipeline.derivation.runtime import execute_derivation_pipeline
from tax_pipeline.y2025.derivation.germany_derivations import (
    germany_derivation_law_rules_2025,
)
from tax_pipeline.y2025.derivation.us_derivations import (
    usa_derivation_law_rules_2025,
)

__all__ = [
    "DERIVATION_FACTS_NAME",
    "DERIVATION_GRAPH_NAME",
    "derivation_facts_path",
    "derivation_graph_path",
    "execute_derivation_pipeline",
    "germany_derivation_law_rules_2025",
    "hydrate_germany_capital_derived_facts",
    "load_derivation_facts",
    "load_germany_capital_derived_facts",
    "usa_derivation_law_rules_2025",
    "write_derivation_artifacts",
]
