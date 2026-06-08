from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.y2025.germany_law import (
    ESTG_19_URL,
    ESTG_20_URL,
    ESTH_PARAGRAF_19A_URL as ESTG_19A_URL,
)
from tax_pipeline.year_runtime import analysis_root

getcontext().prec = 28
D = Decimal


STEPS = analysis_root(Path(__file__), default_year=2025)
DETAIL_CSV = STEPS / "germany-dher-capital-detail.csv"
RESULTS_JSON = STEPS / "germany-dher-results.json"
SUMMARY_MD = STEPS / "germany-dher-summary.md"



def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    return format(q2(value), "f")


@dataclass(frozen=True)
class SaleRow:
    acquisition_date: str
    sale_date: str
    transaction_type: str
    plan_type: str
    shares: Decimal
    basis_price_eur: Decimal
    sale_price_gross_eur: Decimal
    allocated_fees_eur: Decimal
    note: str

    @property
    def gross_proceeds_eur(self) -> Decimal:
        return self.shares * self.sale_price_gross_eur

    @property
    def net_proceeds_eur(self) -> Decimal:
        return self.gross_proceeds_eur - self.allocated_fees_eur

    @property
    def basis_eur(self) -> Decimal:
        return self.shares * self.basis_price_eur

    @property
    def gain_eur(self) -> Decimal:
        return self.net_proceeds_eur - self.basis_eur


def build_rows() -> list[SaleRow]:
    dec23_gross_price = D("22.658465")
    dec23_fee_total = D("40.28")
    dec23_total_shares = D("808")
    dec23_fee_per_share = dec23_fee_total / dec23_total_shares

    rows = [
        SaleRow(
            acquisition_date="2025-02-06",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="RSU",
            shares=D("182.999559"),
            basis_price_eur=D("25.12"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("182.999559") * dec23_fee_per_share,
            note="JPM lot acquired 2025-02-06 reconciled to Shareworks release RBC8D30520 with release price EUR 25.12.",
        ),
        SaleRow(
            acquisition_date="2025-02-12",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("7.972377"),
            basis_price_eur=D("26.23"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("7.972377") * dec23_fee_per_share,
            note="JPM lot acquired 2025-02-12 reconciled to Shareworks release OBC9348DA2 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-02-12",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("9.303709"),
            basis_price_eur=D("26.23"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("9.303709") * dec23_fee_per_share,
            note="JPM lot acquired 2025-02-12 reconciled to Shareworks release OBC9348DA2 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-02-12",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("11.830395"),
            basis_price_eur=D("26.23"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("11.830395") * dec23_fee_per_share,
            note="JPM lot acquired 2025-02-12 reconciled to Shareworks release OBC9348DA2 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-02-12",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("0.893519"),
            basis_price_eur=D("26.23"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("0.893519") * dec23_fee_per_share,
            note="JPM lot acquired 2025-02-12 reconciled to Shareworks ad hoc adjustment at the same release price.",
        ),
        SaleRow(
            acquisition_date="2025-05-06",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="RSU",
            shares=D("214"),
            basis_price_eur=D("25.43"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("214") * dec23_fee_per_share,
            note="JPM lot acquired 2025-05-06 reconciled to Shareworks release RBCDCF3711 with release price EUR 25.43.",
        ),
        SaleRow(
            acquisition_date="2025-05-09",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("11.522430"),
            basis_price_eur=D("24.90"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("11.522430") * dec23_fee_per_share,
            note="JPM lot acquired 2025-05-09 reconciled to Shareworks release OBCE246D12 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-05-09",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("9.330879"),
            basis_price_eur=D("24.90"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("9.330879") * dec23_fee_per_share,
            note="JPM lot acquired 2025-05-09 reconciled to Shareworks release OBCE246D12 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-05-09",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("9.020960"),
            basis_price_eur=D("24.90"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("9.020960") * dec23_fee_per_share,
            note="JPM lot acquired 2025-05-09 reconciled to Shareworks release OBCE246D12 / matching shares.",
        ),
        SaleRow(
            acquisition_date="2025-05-09",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="ESPP_matching",
            shares=D("0.125731"),
            basis_price_eur=D("24.90"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("0.125731") * dec23_fee_per_share,
            note="JPM lot acquired 2025-05-09 reconciled to Shareworks ad hoc adjustment at the same release price.",
        ),
        SaleRow(
            acquisition_date="2025-08-18",
            sale_date="2025-08-18",
            transaction_type="Sell To Market To Cover Cost",
            plan_type="RSU",
            shares=D("177"),
            basis_price_eur=D("22.69701"),
            sale_price_gross_eur=D("22.69701"),
            allocated_fees_eur=D("8.84"),
            note="Same-day sell-to-cover on the 2025-08-18 Shareworks release; only broker fees create the capital loss.",
        ),
        SaleRow(
            acquisition_date="2025-08-18",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="RSU",
            shares=D("176"),
            basis_price_eur=D("22.69701"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("176") * dec23_fee_per_share,
            note="JPM lot acquired 2025-08-18 reconciled to the same Shareworks release; 176 shares remained after sell-to-cover.",
        ),
        SaleRow(
            acquisition_date="2025-11-10",
            sale_date="2025-11-10",
            transaction_type="Sell To Market To Cover Cost",
            plan_type="RSU",
            shares=D("177"),
            basis_price_eur=D("17.233696"),
            sale_price_gross_eur=D("17.233696"),
            allocated_fees_eur=D("6.72"),
            note="Same-day sell-to-cover on the 2025-11-10 Shareworks release; only broker fees create the capital loss.",
        ),
        SaleRow(
            acquisition_date="2025-11-10",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="RSU",
            shares=D("175"),
            basis_price_eur=D("17.233696"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("175") * dec23_fee_per_share,
            note="JPM lot acquired 2025-11-10 reconciled to the same Shareworks release; 175 shares remained after sell-to-cover.",
        ),
        SaleRow(
            acquisition_date="2025-11-20",
            sale_date="2025-12-23",
            transaction_type="Sell To Market",
            plan_type="fractional_adjustment",
            shares=D("0.000441"),
            basis_price_eur=D("16.130558"),
            sale_price_gross_eur=dec23_gross_price,
            allocated_fees_eur=D("0.000441") * dec23_fee_per_share,
            note="De minimis fractional free-share adjustment from Shareworks; basis uses the contemporaneous quoted price on the statement.",
        ),
    ]
    return rows


def main() -> None:
    rows = build_rows()

    with DETAIL_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "symbol",
                "acquisition_date",
                "sale_date",
                "transaction_type",
                "plan_type",
                "shares",
                "basis_price_eur",
                "gross_proceeds_eur",
                "allocated_fees_eur",
                "net_proceeds_eur",
                "basis_eur",
                "gain_eur",
                "legal_reference",
                "authority_url",
                "precision_note",
                "note",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    "DHER",
                    row.acquisition_date,
                    row.sale_date,
                    row.transaction_type,
                    row.plan_type,
                    format(row.shares, "f"),
                    fmt(row.basis_price_eur),
                    fmt(row.gross_proceeds_eur),
                    fmt(row.allocated_fees_eur),
                    fmt(row.net_proceeds_eur),
                    fmt(row.basis_eur),
                    fmt(row.gain_eur),
                    "§ 19 EStG; § 20 Abs. 2 Satz 1 Nr. 1 und Abs. 4 EStG; § 19a EStG",
                    f"{ESTG_19_URL} | {ESTG_20_URL} | {ESTG_19A_URL}",
                    "Basis uses the Shareworks release value / taxed compensation value as the acquisition-cost anchor; this is an inference from the employee-share documents, with § 19a used as the closest explicit statutory confirmation of the same basis logic.",
                    row.note,
                ]
            )

    total_gain = sum((row.gain_eur for row in rows), D("0"))
    same_day_gain = sum((row.gain_eur for row in rows if row.sale_date == row.acquisition_date), D("0"))
    later_sale_gain = total_gain - same_day_gain

    results = {
        "symbol": "DHER",
        "total_gain_eur": fmt(total_gain),
        "same_day_sell_to_cover_gain_eur": fmt(same_day_gain),
        "later_sale_gain_eur": fmt(later_sale_gain),
        "row_count": len(rows),
    }
    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")

    SUMMARY_MD.write_text(
        "\n".join(
            [
                "# DHER German 2025 Capital Summary",
                "",
                "This file is generated by `python3 -m tax_pipeline.pipelines.y2025.dher_german` from the JPM sale rows and the old Shareworks release records.",
                "",
                f"- Total DHER 2025 capital result: **{fmt(total_gain)} EUR**",
                f"- Same-day sell-to-cover result: {fmt(same_day_gain)} EUR",
                f"- Later 2025 sale result: {fmt(later_sale_gain)} EUR",
                "",
                "Method:",
                "- Shareworks release / matching-share documents provide the acquisition-price anchor in EUR.",
                "- The later `2025-12-23` sale commission of `40.28 EUR` is allocated pro rata by share across the 808-share order.",
                "- Same-day sell-to-cover rows are treated as sale proceeds at the release price less direct broker fees.",
                "",
                "Key assumption:",
                "- The employment-income piece of the RSU / ESPP releases is already reflected in payroll or taxed compensation records, so only the post-release value change is included here on the capital side.",
                "",
                "Official references:",
                f"- § 19 EStG: {ESTG_19_URL}",
                f"- § 20 EStG: {ESTG_20_URL}",
                f"- § 19a EStG / EStH 2025: {ESTG_19A_URL}",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
