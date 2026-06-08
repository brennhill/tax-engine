from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.y2025.us_inputs import load_us_assessment_inputs_2025
from tax_pipeline.y2025.us_inputs import load_us_capital_source_facts_2025
from tax_pipeline.y2025.us_law import (
    IRS_DIGITAL_ASSETS,
    IRS_I1099B,
    IRS_I1116,
    IRS_I8949,
    IRS_P525,
    IRS_P550,
    compute_capital_assessment_2025,
)
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28

YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STEPS = analysis_root(Path(__file__), default_year=2025)
BUCKETS_CSV = STEPS / "us-form-8949-income-buckets.csv"
RESULTS_JSON = STEPS / "us-capital-results.json"
SUMMARY_MD = STEPS / "us-capital-summary.md"

def round_cents(amount_usd: Decimal) -> Decimal:
    return amount_usd.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt(amount_usd: Decimal) -> str:
    return format(round_cents(amount_usd), "f")


def main() -> None:
    facts = load_us_capital_source_facts_2025(YEAR_PATHS)
    assessment_inputs = load_us_assessment_inputs_2025(YEAR_PATHS)
    # 26 U.S.C. § 1211(b) uses a $3,000 annual capital-loss limit except $1,500
    # for married filing separately. The workpaper must use the filing-status
    # threshold selected by the input loader, not the law core's MFS default.
    capital = compute_capital_assessment_2025(
        facts,
        capital_loss_limit_usd=assessment_inputs.constants.capital_loss_limit_usd,
    )
    filing_status_label = assessment_inputs.profile.filing_status_label

    schedule_b_ordinary_dividends = facts.ordinary_dividends_usd
    schedule_b_qualified_dividends = facts.qualified_dividends_usd
    schedule_b_interest = facts.interest_income_usd
    capital_gain_distributions = facts.capital_gain_distributions_usd
    substitute_payments = facts.substitute_payments_usd
    staking_income = facts.staking_income_usd
    # B-audit-2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): this duplicates the
    # rule-graph computation at us25_02_income_side_inputs (which already
    # publishes us.stage.income_side_inputs.schedule_1_other_income_usd
    # as a declared rule output under § 61 / Pub. 525 / Pub. 550). The
    # workpaper currently consumes raw assessment-input facts directly
    # rather than the executed rule-graph result, so the I5 detector
    # flags this addition. Promoting the workpaper to consume the
    # executed rule-graph output is a small refactor scheduled for the
    # post-Group-B follow-up; the value remains correct and equals the
    # rule output to the cent. # pragma: legal-math-ok pre-graph workpaper
    # aggregation of raw input facts; equals us.stage.income_side_inputs
    # .schedule_1_other_income_usd (US25-02-INCOME-SIDE-INPUTS) by
    # construction — see deferred follow-up for the rule-graph read.
    schedule_1_other_income_total = substitute_payments + staking_income  # pragma: legal-math-ok pre-graph workpaper aggregation; equals US25-02 schedule_1_other_income_usd

    rows = [
        ("Schedule B", "Line 5", schedule_b_ordinary_dividends, "Ordinary dividends"),
        ("Form 1040", "Line 3a", schedule_b_qualified_dividends, "Qualified dividends"),
        ("Form 1040", "Line 3b", schedule_b_ordinary_dividends, "Ordinary dividends"),
        ("Schedule B", "Line 2", schedule_b_interest, "Interest income"),
        ("Schedule 1", "Line 8z", substitute_payments, "Substitute payments in lieu of dividends / interest"),
        ("Schedule 1", "Line 8z", staking_income, "Digital-asset staking income"),
        ("Schedule D", "Line 13", capital_gain_distributions, "Capital gain distributions"),
        ("Form 8949", "Part I Box A", capital.short_box_a_usd, "Short covered broker transactions reported with basis to the IRS"),
        ("Form 8949", "Part I Box B", capital.short_box_b_usd, "Schwab short noncovered"),
        ("Form 8949", "Part I Box H", capital.short_box_h_usd, "Short digital-asset transactions not reported with basis to the IRS"),
        ("Form 8949 / Schedule D", "Part II Box D", capital.long_box_d_usd, "Schwab long covered"),
        ("Form 8949", "Part II Box K", capital.long_box_k_usd, "Long digital-asset transactions not reported with basis to the IRS"),
        ("Form 6781", "Net section 1256", capital.section_1256_total_usd, "Schwab section 1256 total"),
        ("Schedule D", "Net capital before 1256", capital.net_capital_before_1256_usd, "Short + long + capital gain distributions"),
        ("Schedule D", "Net capital after 1256", capital.net_capital_after_1256_usd, "After Form 6781 overlay"),
        (
            "Schedule D",
            "Capital loss deduction 2025",
            capital.capital_loss_deduction_2025_usd,
            f"{filing_status_label} annual capital-loss limit under 26 U.S.C. § 1211(b).",
        ),
        ("Carryforward", "Capital loss carryforward to 2026", capital.tentative_capital_loss_carryforward_2026_usd, "Tentative amount under 26 U.S.C. § 1212(b)."),
    ]

    with BUCKETS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["form", "line_or_bucket", "amount_usd", "note"])
        for row in rows:
            writer.writerow([row[0], row[1], fmt(row[2]), row[3]])

    results = {
        "income": {
            "ordinary_dividends_usd": fmt(schedule_b_ordinary_dividends),
            "qualified_dividends_usd": fmt(schedule_b_qualified_dividends),
            "interest_income_usd": fmt(schedule_b_interest),
            "capital_gain_distributions_usd": fmt(capital_gain_distributions),
            "substitute_payments_usd": fmt(substitute_payments),
            "staking_income_usd": fmt(staking_income),
            "schedule_1_other_income_total_usd": fmt(schedule_1_other_income_total),
            "nondividend_distributions_usd": fmt(facts.nondividend_distributions_usd),
            "foreign_tax_paid_usd": fmt(facts.foreign_tax_paid_usd),
        },
        "capital": {
            "short_box_a_usd": fmt(capital.short_box_a_usd),
            "short_box_b_usd": fmt(capital.short_box_b_usd),
            "short_box_h_usd": fmt(capital.short_box_h_usd),
            "short_term_total_usd": fmt(capital.short_term_total_usd),
            "long_box_d_usd": fmt(capital.long_box_d_usd),
            "long_box_k_usd": fmt(capital.long_box_k_usd),
            "capital_gain_distributions_usd": fmt(capital_gain_distributions),
            "long_term_total_with_cgd_usd": fmt(capital.long_term_total_with_cgd_usd),
            "section_1256_total_usd": fmt(capital.section_1256_total_usd),
            "section_1256_short_term_usd": fmt(capital.section_1256_short_term_usd),
            "section_1256_long_term_usd": fmt(capital.section_1256_long_term_usd),
            "net_capital_before_1256_usd": fmt(capital.net_capital_before_1256_usd),
            "net_capital_after_1256_usd": fmt(capital.net_capital_after_1256_usd),
            "capital_loss_deduction_2025_usd": fmt(capital.capital_loss_deduction_2025_usd),
            "tentative_capital_loss_carryforward_2026_usd": fmt(capital.tentative_capital_loss_carryforward_2026_usd),
            "form_1040_line_7a_usd": fmt(capital.form_1040_line_7a_usd),
        },
        "ftc_starting_point": {
            "passive_ftc_carryover_2024_usd": fmt(facts.passive_ftc_carryover_2024_usd),
            "general_ftc_carryover_2024_usd": fmt(facts.general_ftc_carryover_2024_usd),
            "foreign_tax_paid_schwab_usd": fmt(facts.foreign_tax_paid_usd),
            "german_2024_redetermination_paid_2025_eur": fmt(facts.german_2024_redetermination_paid_2025_eur),
        },
        "payments": {
            "estimated_payment_2025_usd": fmt(facts.estimated_payment_2025_usd),
        },
    }
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    SUMMARY_MD.write_text(
        "\n".join(
            [
                "# U.S. 2025 Capital And Income Summary",
                "",
                "This file is generated by `python3 -m tax_pipeline.pipelines.y2025.us_capital_workpaper` from structured year inputs under `normalized/facts/` and `normalized/derived-facts/`.",
                "",
                "## Income",
                f"- ordinary dividends: **{fmt(schedule_b_ordinary_dividends)} USD**",
                f"- qualified dividends: {fmt(schedule_b_qualified_dividends)} USD",
                f"- interest income: {fmt(schedule_b_interest)} USD",
                f"- capital gain distributions: {fmt(capital_gain_distributions)} USD",
                f"- substitute payments (Schedule 1): {fmt(substitute_payments)} USD",
                f"- staking income (Schedule 1): {fmt(staking_income)} USD",
                f"- Schedule 1 other income subtotal from these two items: {fmt(schedule_1_other_income_total)} USD",
                f"- nondividend distributions: {fmt(facts.nondividend_distributions_usd)} USD (basis-reducing, not current-year income)",
                "",
                "## Capital buckets",
                f"- short-term Form 8949 box A: {fmt(capital.short_box_a_usd)} USD",
                f"- short-term Form 8949 box B: {fmt(capital.short_box_b_usd)} USD",
                f"- short-term Form 8949 box H: {fmt(capital.short_box_h_usd)} USD",
                f"- long-term Form 8949 / Schedule D box D: {fmt(capital.long_box_d_usd)} USD",
                f"- long-term Form 8949 box K: {fmt(capital.long_box_k_usd)} USD",
                f"- Form 6781 section 1256 total: {fmt(capital.section_1256_total_usd)} USD",
                f"- net capital before 1256: {fmt(capital.net_capital_before_1256_usd)} USD",
                f"- net capital after 1256: {fmt(capital.net_capital_after_1256_usd)} USD",
                f"- tentative 2025 capital-loss deduction: {fmt(capital.capital_loss_deduction_2025_usd)} USD",
                f"- tentative 2026 capital-loss carryforward: {fmt(capital.tentative_capital_loss_carryforward_2026_usd)} USD",
                "",
                "## FTC starting point",
                f"- passive FTC carryover into 2025: {fmt(facts.passive_ftc_carryover_2024_usd)} USD",
                f"- general FTC carryover into 2025: {fmt(facts.general_ftc_carryover_2024_usd)} USD",
                f"- 2025 passive foreign tax from Schwab: {fmt(facts.foreign_tax_paid_usd)} USD",
                f"- 2024 German redetermination paid in 2025: {fmt(facts.german_2024_redetermination_paid_2025_eur)} EUR",
                "",
                "## Current filing implications",
                "- The 2025 return will almost certainly need Schedule B, Schedule 1, Schedule D, Form 8949, Form 6781, and at least passive/general Form 1116 work.",
                f"- The capital-loss deduction limit here follows the {filing_status_label.lower()} annual limit under 26 U.S.C. § 1211(b).",
                "- The 2024 German redetermination belongs in the accrued-basis FTC review, not in the capital workpaper.",
                "",
                "## Official sources",
                f"- IRS Instructions for Form 1116: {IRS_I1116}",
                f"- IRS Instructions for Form 8949: {IRS_I8949}",
                f"- IRS Instructions for Form 1099-B: {IRS_I1099B}",
                f"- IRS Publication 525: {IRS_P525}",
                f"- IRS Publication 550: {IRS_P550}",
                f"- IRS Digital Assets page: {IRS_DIGITAL_ASSETS}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
