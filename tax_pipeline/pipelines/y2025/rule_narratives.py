from __future__ import annotations

from pathlib import Path

from tax_pipeline.narrative.render import render_narrative_to_path
from tax_pipeline.paths import YearPaths
from tax_pipeline.pipelines.y2025.final_legal_output import load_final_legal_output_2025
from tax_pipeline.year_runtime import active_year_paths

YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)


def render_rule_narratives(paths: YearPaths = YEAR_PATHS) -> dict[str, Path]:
    final_output = load_final_legal_output_2025(paths)
    narratives = final_output["narratives"]
    outputs: dict[str, Path] = {}
    if narratives.get("DE", {}).get("de"):
        outputs["DE-de"] = render_narrative_to_path(
            narratives["DE"]["de"],
            output_path=paths.analysis_root / "DE-de-narrative.md",
            title="Germany 2025 Berechnungsnarrativ",
        )
    if narratives.get("DE", {}).get("en"):
        outputs["DE-en"] = render_narrative_to_path(
            narratives["DE"]["en"],
            output_path=paths.analysis_root / "DE-en-narrative.md",
            title="Germany 2025 Calculation Narrative",
        )
    if narratives.get("US", {}).get("en"):
        outputs["US-en"] = render_narrative_to_path(
            narratives["US"]["en"],
            output_path=paths.analysis_root / "US-en-narrative.md",
            title="U.S. 2025 Calculation Narrative",
        )
    return outputs


def main() -> None:
    render_rule_narratives(YEAR_PATHS)


if __name__ == "__main__":
    main()
