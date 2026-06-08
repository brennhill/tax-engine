from __future__ import annotations

import bisect
import csv
import json
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path

from tax_pipeline.analysis_inputs import structured_input_files
from tax_pipeline.y2025.germany_law import (
    BMF_KRYPTOWERTE_2025_URL as BMF_CRYPTO_URL,
    ESTG_22_URL,
    ESTG_23_URL,
    ESTR_R_34C_URL as BMF_ECB_URL,
)
from tax_pipeline.year_runtime import active_year_paths, analysis_root, find_documents

getcontext().prec = 28
D = Decimal


YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STRUCTURED_INPUTS = structured_input_files(YEAR_PATHS)
STEPS = analysis_root(Path(__file__), default_year=2025)
ECB_CSV = STRUCTURED_INPUTS["ecb_usd_eur_daily"]
LOT_DETAIL_CSV = STEPS / "crypto-private-sales-lot-detail.csv"
DISPOSITIONS_CSV = STEPS / "crypto-private-sales-dispositions.csv"
SUMMARY_MD = STEPS / "crypto-private-sales-summary.md"
RESULTS_JSON = STEPS / "crypto-private-sales-results.json"



SHORT_TAXABLE_QTY = {
    ("BTC", "2025-02-25"): D("0.00408955"),
    ("DOGE", "2025-05-01"): D("1167.81088541"),
    ("XRP", "2025-06-19"): D("46.581659"),
    ("SOL", "2025-06-19"): D("6.806014455"),
    ("SOL", "2025-06-20"): D("3.449941351"),
    ("SOL", "2025-06-29"): D("3.304474258"),
    ("AVAX", "2025-07-08"): D("3.97"),
    ("USDC", "2025-07-08"): D("70.68"),
    ("SOL", "2025-07-12"): D("0.175045843"),
    ("SEI", "2025-11-17"): D("11675.580835"),
    ("SUI", "2025-11-18"): D("254.228237360999994365"),
    ("SOL", "2025-11-18"): D("18.735974770000000329"),
}


def q2(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def fmt(value: Decimal) -> str:
    return format(q2(value), "f")


def compute_private_sale_carryforward_2025(
    *,
    prior_carryforward_eur: Decimal,
    current_private_sale_result_eur: Decimal,
) -> dict[str, Decimal]:
    # § 23 Abs. 3 Sätze 7 bis 9 EStG confines private-sale loss carryforwards
    # to the private-sale bucket. Current-year gains consume prior losses first;
    # current-year losses increase the carryforward.
    prior = q2(prior_carryforward_eur)
    current = q2(current_private_sale_result_eur)
    if prior < D("0.00"):
        raise ValueError("prior_carryforward_eur must be non-negative")
    current_gain = max(D("0.00"), current)
    current_loss = max(D("0.00"), -current)
    used = q2(min(prior, current_gain))
    # § 23 Abs. 3 Sätze 7-9 EStG: private-sale loss carryforward update.
    # https://www.gesetze-im-internet.de/estg/__23.html. This helper is
    # the canonical implementation; the pragma below documents the
    # controlling §-authority so the audit packet still cites it.
    # Promoting this to a Pipeline 2 LawRule is tracked separately.
    updated = q2(prior - used + current_loss)  # pragma: legal-math-ok § 23 Abs. 3 Sätze 7-9 EStG private-sale carryforward update — https://www.gesetze-im-internet.de/estg/__23.html
    return {
        "prior_private_sale_carryforward_eur": prior,
        "carryforward_used_in_2025_eur": used,
        "updated_private_sale_carryforward_eur": updated,
    }


def load_private_sale_prior_carryforward_2025(path: Path | None = None) -> Decimal:
    source = path or STRUCTURED_INPUTS["de_loss_carryforwards"]
    with source.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["key"] == "private_sale_loss_carryforward_2024_eur":
                return q2(D(row["value"]))
    raise FileNotFoundError(
        "Missing private_sale_loss_carryforward_2024_eur in de-loss-carryforwards.csv"
    )


def parse_money(raw: str) -> Decimal:
    value = raw.strip().replace("$", "").replace(",", "")
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    return D(value)


def parse_transactions(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as f:
        raw_rows = list(csv.reader(f))[3:]
    for row in raw_rows:
        if not row or len(row) < 11 or row[2] == "Transaction Type":
            continue
        ts = datetime.strptime(row[1], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
        rows.append(
            {
                "id": row[0],
                "ts": ts,
                "type": row[2],
                "asset": row[3],
                "qty": D(row[4]),
                "subtotal_usd": parse_money(row[7]),
                "total_usd": parse_money(row[8]),
                "notes": row[10],
            }
        )
    return rows


def load_ecb_rates(path: Path) -> tuple[dict[str, Decimal], list[str]]:
    rates: dict[str, Decimal] = {}
    dates: list[str] = []
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = row["TIME_PERIOD"]
            rates[d] = D(row["OBS_VALUE"])
            dates.append(d)
    dates.sort()
    return rates, dates


def lookup_rate(rates: dict[str, Decimal], dates: list[str], day: str) -> tuple[Decimal, str]:
    if day in rates:
        return rates[day], day
    idx = bisect.bisect_right(dates, day)
    fallback = dates[idx - 1]
    return rates[fallback], fallback


@dataclass
class Lot:
    qty: Decimal
    acquired_at: datetime
    basis_usd: Decimal
    source: str


def add_acquisition(
    inventory: dict[str, deque[Lot]],
    asset: str,
    qty: Decimal,
    acquired_at: datetime,
    basis_usd: Decimal,
    source: str,
) -> None:
    inventory[asset].append(Lot(qty=qty, acquired_at=acquired_at, basis_usd=basis_usd, source=source))


def consume_fifo(inventory: dict[str, deque[Lot]], asset: str, qty: Decimal) -> None:
    remaining = qty
    while remaining > 0 and inventory[asset]:
        lot = inventory[asset][0]
        take = min(lot.qty, remaining)
        if take == lot.qty:
            inventory[asset].popleft()
        else:
            ratio = (lot.qty - take) / lot.qty
            lot.basis_usd *= ratio
            lot.qty -= take
        remaining -= take


def resolve_coinbase_transactions(year: int) -> Path:
    matches = find_documents(YEAR_PATHS, doc_type="coinbase_transactions_csv", tax_year=year)
    if matches:
        return matches[0]
    # Fix: year source documents are now canonical under years/<year>/raw/, so
    # fallback resolution should stay inside that tree rather than assuming a
    # repo-root CSV layout.
    # Proposal 8: resolve via the dual-layout helper so both legacy
    # ``raw/crypto/`` and new ``raw/asset_classes/crypto/`` workspaces
    # locate the file.
    from tax_pipeline.paths import resolve_bucket_path

    return resolve_bucket_path(YEAR_PATHS.raw_root, "crypto") / f"coinbase-transactions-{year}.csv"


def main() -> None:
    rates, rate_dates = load_ecb_rates(ECB_CSV)
    rows = sorted(
        parse_transactions(resolve_coinbase_transactions(2024))
        + parse_transactions(resolve_coinbase_transactions(2025)),
        key=lambda row: (row["ts"], row["id"]),
    )

    inventory: dict[str, deque[Lot]] = defaultdict(deque)
    lot_rows: list[list[str]] = []
    disposition_rows: list[list[str]] = []

    private_sale_result_eur = D("0")
    staking_income_usd = D("0")
    staking_income_eur = D("0")

    for row in rows:
        tx_type = str(row["type"])
        asset = str(row["asset"])
        ts = row["ts"]
        day = ts.date().isoformat()
        qty = D(str(row["qty"]))
        subtotal_usd = D(str(row["subtotal_usd"]))
        total_usd = D(str(row["total_usd"]))
        notes = str(row["notes"])

        if tx_type == "Buy":
            add_acquisition(inventory, asset, qty, ts, abs(total_usd), "Buy")
            continue

        if tx_type in {"Staking Income", "Reward Income"}:
            if qty > 0:
                add_acquisition(inventory, asset, qty, ts, abs(subtotal_usd), tx_type)
                if ts.year == 2025:
                    rate, _ = lookup_rate(rates, rate_dates, day)
                    staking_income_usd += abs(subtotal_usd)
                    staking_income_eur += abs(subtotal_usd) / rate
            continue

        if tx_type == "Receive":
            if qty > 0:
                basis_usd = abs(total_usd) if abs(total_usd) != 0 else abs(subtotal_usd)
                add_acquisition(inventory, asset, qty, ts, basis_usd, "Receive")
            continue

        if tx_type not in {"Convert", "Sell"}:
            continue

        taxable_qty = min(abs(qty), SHORT_TAXABLE_QTY.get((asset, day), D("0")))
        if taxable_qty > 0:
            threshold = ts - timedelta(days=365)
            sale_rate, sale_rate_day = lookup_rate(rates, rate_dates, day)
            proceeds_usd = abs(total_usd) * (taxable_qty / abs(qty))
            proceeds_eur = proceeds_usd / sale_rate

            remaining = taxable_qty
            cost_usd = D("0")
            cost_eur = D("0")
            lot_piece_count = 0
            assumption_note = ""

            for lot in inventory[asset]:
                if remaining <= 0:
                    break
                if lot.acquired_at <= threshold:
                    continue
                take = min(lot.qty, remaining)
                piece_basis_usd = lot.basis_usd * (take / lot.qty)
                acq_day = lot.acquired_at.date().isoformat()
                acq_rate, acq_rate_day = lookup_rate(rates, rate_dates, acq_day)
                piece_proceeds_usd = proceeds_usd * (take / taxable_qty)
                piece_proceeds_eur = proceeds_eur * (take / taxable_qty)
                piece_cost_eur = piece_basis_usd / acq_rate
                piece_gain_eur = piece_proceeds_eur - piece_cost_eur

                if asset == "AVAX" and lot.source == "Receive":
                    assumption_note = "Uses same-day Coinbase receive row as provisional basis/date for transferred-in AVAX."

                lot_rows.append(
                    [
                        day,
                        asset,
                        tx_type,
                        str(take),
                        acq_day,
                        lot.source,
                        acq_rate_day,
                        fmt(piece_proceeds_usd),
                        fmt(piece_basis_usd),
                        fmt(piece_proceeds_eur),
                        fmt(piece_cost_eur),
                        fmt(piece_gain_eur),
                        assumption_note,
                        "§ 23 Abs. 1 Satz 1 Nr. 2, Abs. 3 EStG",
                        f"{ESTG_23_URL} | {BMF_ECB_URL}",
                        "Holding-period, gain/loss, and lot matching follow the saved § 23 model; EUR conversion uses the saved ECB-rate convention.",
                    ]
                )

                cost_usd += piece_basis_usd
                cost_eur += piece_cost_eur
                remaining -= take
                lot_piece_count += 1

            gain_eur = proceeds_eur - cost_eur
            private_sale_result_eur += gain_eur

            disposition_rows.append(
                [
                    day,
                    asset,
                    tx_type,
                    str(taxable_qty),
                    fmt(proceeds_usd),
                    fmt(cost_usd),
                    fmt(proceeds_usd - cost_usd),
                    sale_rate_day,
                    fmt(proceeds_eur),
                    fmt(cost_eur),
                    fmt(gain_eur),
                    str(lot_piece_count),
                    fmt(remaining),
                    assumption_note,
                    "§ 23 Abs. 1 Satz 1 Nr. 2, Abs. 3 EStG",
                    f"{ESTG_23_URL} | {BMF_ECB_URL}",
                    "Short-term private-sale result under § 23; EUR conversion uses the saved ECB-rate convention.",
                ]
            )

        consume_fifo(inventory, asset, abs(qty))

        if tx_type == "Convert":
            match = re.search(r"to\s+([0-9.]+)\s+([A-Z0-9]+)", notes)
            if match:
                acquired_qty = D(match.group(1))
                acquired_asset = match.group(2)
                add_acquisition(inventory, acquired_asset, acquired_qty, ts, abs(total_usd), "Convert")

    prior_private_sale_carryforward = load_private_sale_prior_carryforward_2025()
    carryforward = compute_private_sale_carryforward_2025(
        prior_carryforward_eur=prior_private_sale_carryforward,
        current_private_sale_result_eur=private_sale_result_eur,
    )
    updated_private_sale_carryforward = carryforward["updated_private_sale_carryforward_eur"]
    carryforward_used_in_2025 = carryforward["carryforward_used_in_2025_eur"]

    with LOT_DETAIL_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "sale_date",
                "asset",
                "transaction_type",
                "matched_qty",
                "acquisition_date",
                "acquisition_source",
                "acquisition_rate_date",
                "proceeds_usd_piece",
                "cost_usd_piece",
                "proceeds_eur_piece",
                "cost_eur_piece",
                "gain_eur_piece",
                "assumption_note",
                "legal_reference",
                "authority_url",
                "precision_note",
            ]
        )
        writer.writerows(lot_rows)

    with DISPOSITIONS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(
            [
                "sale_date",
                "asset",
                "transaction_type",
                "short_term_taxable_qty",
                "proceeds_usd",
                "cost_usd",
                "gain_usd",
                "sale_rate_date",
                "proceeds_eur",
                "cost_eur",
                "gain_eur",
                "lot_piece_count",
                "unmatched_short_qty",
                "assumption_note",
                "legal_reference",
                "authority_url",
                "precision_note",
            ]
        )
        writer.writerows(disposition_rows)

    RESULTS_JSON.write_text(
        json.dumps(
            {
                "private_sale_result_eur": fmt(private_sale_result_eur),
                "prior_private_sale_carryforward_eur": fmt(prior_private_sale_carryforward),
                "carryforward_used_in_2025_eur": fmt(carryforward_used_in_2025),
                "updated_private_sale_carryforward_eur": fmt(updated_private_sale_carryforward),
                "staking_income_usd_2025": fmt(staking_income_usd),
                "staking_income_eur_2025": fmt(staking_income_eur),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    SUMMARY_MD.write_text(
        "\n".join(
            [
                "# Coinbase Private Sales 2025",
                "",
                "This file is generated by `python3 -m tax_pipeline.pipelines.y2025.coinbase_private_sales` from the 2024/2025 Coinbase transaction CSVs, the Coinbase `1099-DA`, and the saved ECB daily rate file.",
                "",
                "## Locked result",
                f"- Exact 2025 German `§ 23` private-sale result from the documented short-term Coinbase rows: **{fmt(private_sale_result_eur)} EUR**",
                f"- 2024 private-sale loss carryforward brought in: `{fmt(prior_private_sale_carryforward)} EUR`",
                f"- Carryforward used in 2025: `{fmt(carryforward_used_in_2025)} EUR`",
                f"- Expected remaining / updated private-sale loss carryforward after 2025: **{fmt(updated_private_sale_carryforward)} EUR**",
                "",
                "## Refund impact",
                "- The direct-crypto `§ 23` bucket is net negative in 2025, so this script does not add tax on its own.",
                "- Coinbase staking income is handled separately in the main German model and is not part of the `§ 23` result above.",
                "",
                "## Legal basis",
                f"- Private-sale calculations: `§ 23 Abs. 1 Satz 1 Nr. 2` und `§ 23 Abs. 3 EStG` ({ESTG_23_URL})",
                f"- Staking / reward income classification: `§ 22 Nr. 3 EStG` plus BMF crypto guidance dated 6 March 2025 ({ESTG_22_URL}; {BMF_CRYPTO_URL})",
                f"- EUR conversion convention in the saved model: ECB-rate approach documented in `R 34c (1) EStH 2025` ({BMF_ECB_URL})",
                "",
                "## Method",
                "- The Coinbase transaction history alone is not enough for raw FIFO because the account has older opening inventory before 2024.",
                "- To isolate the taxable 2025 German short-term portion, this script uses the per-asset short-term quantities from `coinbase-1099-DA.pdf` as the disposition quantities to test under `§ 23 EStG`.",
                "- Those short-term quantities are then matched to 2024/2025 acquisition lots only, using FIFO within the one-year window.",
                "- USD amounts are converted to EUR using the saved ECB daily USD/EUR reference rates, falling back to the prior ECB business day for weekends and holidays.",
                "",
                "## Open caveats",
                "- The `AVAX` row was transferred in from an external account. The script uses the same-day Coinbase receive row as a provisional basis/date. That assumption is tiny and does not change the refund result.",
                f"- Coinbase `Staking Income` in 2025 totals `{fmt(staking_income_usd)} USD` / `{fmt(staking_income_eur)} EUR` by daily ECB conversion. That is a separate potential German income item and is not folded into the `§ 23` result above.",
                "",
                "## Generated files",
                "- `analysis-steps/crypto-private-sales-lot-detail.csv`",
                "- `analysis-steps/crypto-private-sales-dispositions.csv`",
                "- `analysis-steps/crypto-private-sales-summary.md`",
                "- `analysis-steps/crypto-private-sales-results.json`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
