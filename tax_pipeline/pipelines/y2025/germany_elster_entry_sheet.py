from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.analysis_inputs import load_german_model_inputs, structured_input_files
from tax_pipeline.y2025.germany_inputs import load_german_person_slots, load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.germany_law import (
    ELSTER_ANLAGE_AUS_2025_URL as ELSTER_HELP,
    ESTG_9_URL as ESTG_9,
    ESTG_20_URL as ESTG_20,
    ESTG_22_URL as ESTG_22,
    ESTG_23_URL as ESTG_23,
    INVSTG_20_URL as INVSTG_20,
    compute_joint_ordinary_assessment_2025,
)
from tax_pipeline.pipelines.y2025.germany_model import (
    load_fund_classification,
)
from tax_pipeline.postures import get_posture_definition
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28
D = Decimal


YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STRUCTURED_INPUTS = structured_input_files(YEAR_PATHS)
STEPS = analysis_root(Path(__file__), default_year=2025)
RESULTS_JSON = STEPS / "germany-model-results.json"
KAP_SUMMARY_CSV = STEPS / "germany-kap-summary.csv"
KIND_SUMMARY_CSV = STEPS / "germany-kind-summary.csv"
N_BREAKDOWN_CSV = STEPS / "germany-n-work-expenses.csv"
KAP_INV_FUND_CSV = STEPS / "germany-kap-inv-fund-summary.csv"
ENTRY_MD = STEPS / "germany-elster-entry-sheet.md"
PERSON_2_BANK_SUMMARY_MD = STEPS / "spouse-bank-capital-certificate-summary.md"
PRIVATE_SALES_DETAIL_CSV = STEPS / "crypto-private-sales-dispositions.csv"
DHER_DETAIL_CSV = STEPS / "germany-dher-capital-detail.csv"
MARRIED_SEPARATE_UNSUPPORTED = (
    "Germany filing posture 'married_separate' is not supported for the 2025 ELSTER audit surface yet."
)



def q2(x: Decimal) -> Decimal:
    return x.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def fmt(x: Decimal) -> str:
    return format(q2(x), "f")


def result_phrase(amount: Decimal | str) -> str:
    value = D(str(amount))
    if value < D("0.00"):
        return f"{fmt(-value)} EUR balance due"
    return f"{fmt(value)} EUR refund"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_inputs() -> dict[str, Decimal]:
    return load_german_model_inputs(YEAR_PATHS)


def load_manual_overrides() -> dict:
    return json.loads(YEAR_PATHS.manual_overrides_path.read_text(encoding="utf-8"))


def load_profile() -> dict:
    return json.loads(YEAR_PATHS.profile_path.read_text(encoding="utf-8"))


def _private_sale_result(results: dict) -> Decimal:
    return D(str(results.get("private_sales", {}).get("private_sale_result_eur", "0.00")))


def _required_elster_projection(results: dict) -> dict:
    projection = results.get("render_projection", {}).get("elster")
    if not isinstance(projection, dict):
        raise ValueError(
            "germany-model-results.json is missing render_projection.elster. "
            "Run the Germany core model before rendering ELSTER artifacts."
        )
    return projection


def _write_projection_artifacts(projection: dict) -> dict[str, Decimal]:
    with KAP_INV_FUND_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["symbol", "fund_type", "income_eur", "sale_result_eur", "combined_eur"])
        writer.writerows(projection.get("kap_inv_fund_rows", ()))

    with KAP_SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["form", "line", "amount_eur", "note"])
        writer.writerows(projection.get("kap_summary_rows", ()))

    # Anlage Kind summary — § 33b Abs. 5 EStG transferred Pauschbetrag
    # surface for the form-renderer (BMF Anlage Kind 2025 Zeilen 64-66).
    # https://www.gesetze-im-internet.de/estg/__33b.html
    with KIND_SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["form", "line", "amount_eur", "note"])
        writer.writerows(projection.get("kind_summary_rows", ()))

    with N_BREAKDOWN_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["form", "line", "description", "amount_eur", "note"])
        writer.writerows(projection.get("n_breakdown_rows", ()))

    bank_summary = str(projection.get("person_2_bank_summary_markdown", "")).strip()
    if bank_summary:
        PERSON_2_BANK_SUMMARY_MD.write_text(bank_summary + "\n", encoding="utf-8")
    elif PERSON_2_BANK_SUMMARY_MD.exists():
        PERSON_2_BANK_SUMMARY_MD.unlink()

    return {key: D(str(value)) for key, value in projection.get("capital_audit", {}).items()}


def aggregate(inputs: dict[str, Decimal]) -> dict[str, Decimal]:
    # Render only the frozen Germany core projection. Typed bank certificates are
    # integrated in germany_model under § 20/§ 32d/§ 36 before this renderer runs.
    return _write_projection_artifacts(_required_elster_projection(load_json(RESULTS_JSON)))


def main() -> None:
    results = load_json(RESULTS_JSON)
    posture = get_posture_definition("germany", results.get("ordinary", {}).get("filing_posture", ""))
    if not posture.output_support.entry_sheet:
        raise NotImplementedError(MARRIED_SEPARATE_UNSUPPORTED)
    private_sale_result = _private_sale_result(results)
    if private_sale_result > D("0.00"):
        raise ValueError("Positive § 23 EStG private-sale results must be integrated by germany_model before ELSTER rendering.")
    projection = _required_elster_projection(results)
    _write_projection_artifacts(projection)
    ENTRY_MD.write_text(str(projection["entry_sheet_markdown"]).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
