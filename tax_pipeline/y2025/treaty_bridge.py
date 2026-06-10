from __future__ import annotations

import hashlib
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from tax_pipeline.analysis_inputs import structured_input_files
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.us_law import (
    GermanyTreatyDividendPacketItem2025,
    USTreatyDividendItem2025,
)

GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY = "germany_2025.us_treaty_dividend_packet_items"
GERMANY_US_TREATY_DIVIDEND_AUDIT_NAME = "de-us-treaty-dividend-packet.md"
US_TREATY_DIVIDEND_ITEMS_NAME = "us-treaty-dividend-items.csv"
DE_US_TREATY_DIVIDEND_ITEMS_NAME = "de-us-treaty-dividend-items.csv"


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_decimal(value: Decimal) -> str:
    return format(q2(value), "f")


def sha256_file(path: Path) -> str:
    if not path.exists():
        return "missing"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_year_path(paths: YearPaths, path: Path) -> str:
    return path.relative_to(paths.year_root).as_posix()


def germany_treaty_dividend_source_fingerprints_2025(paths: YearPaths) -> dict[str, str]:
    files = structured_input_files(paths)
    source_paths = (
        paths.tax_positions_root / DE_US_TREATY_DIVIDEND_ITEMS_NAME,
        files["germany_income_cashflows"],
    )
    return {relative_year_path(paths, path): sha256_file(path) for path in source_paths}


def convert_germany_treaty_dividend_items_to_us_2025(
    *,
    germany_items: tuple[GermanyUSTreatyDividendPacketItem2025, ...],
    us_items: tuple[USTreatyDividendItem2025, ...],
    eur_per_usd: Decimal,
) -> tuple[GermanyTreatyDividendPacketItem2025, ...]:
    # DBA-USA Art. 23(5)(c) (re-sourcing — U.S.-source items deemed to arise
    # in Germany) read with Art. 23(5)(b) (the U.S. credit for the German
    # tax on those items), and IRS Pub. 514 (2024 ed., applicable for 2025
    # returns) "Tax Treaties" worksheet, require Germany's residence-country
    # tax/credit on the same U.S.-source dividend stack used on the U.S.
    # additional-credit worksheet. Match by item ID first; FX is an audit
    # reconciliation, not the source of legal identity.
    # Sources: https://www.irs.gov/pub/irs-trty/germany.pdf (1989 treaty +
    # 2006 protocol) and https://www.irs.gov/publications/p514.
    if eur_per_usd <= Decimal("0.00"):
        raise ValueError("eur_per_usd_yearly_average_2025 must be positive to convert Germany treaty dividend outputs.")
    us_by_item_id = {item.item_id: item for item in us_items}
    germany_by_item_id = {item.item_id: item for item in germany_items}
    if len(us_by_item_id) != len(us_items):
        raise ValueError("Duplicate U.S. treaty dividend item_id.")
    if len(germany_by_item_id) != len(germany_items):
        raise ValueError("Duplicate Germany treaty dividend packet item_id.")
    if set(us_by_item_id) != set(germany_by_item_id):
        raise ValueError("Germany-U.S. treaty dividend item coverage does not match U.S. treaty dividend items.")

    cent = Decimal("0.01")
    # DBA-USA Art. 10(2)(b) portfolio-dividend source-tax ceiling = 15 % of
    # gross. Pub. 514 (2024 ed.) worksheet line 16 expresses this in USD:
    # gross_usd × 0.15. Computing the ceiling in USD directly (instead of
    # via the EUR side and then dividing by the yearly-average FX) avoids
    # per-item round-trip drift where EUR ceiling quantization can push the
    # summed DE-side ceiling marginally above the US-side aggregate ceiling.
    # Imported from derive_treaty_dividend_items_2025 so a future treaty
    # rate change is picked up by both sides automatically.
    from tax_pipeline.y2025.derive_treaty_dividend_items import TREATY_RATE as article_10_rate
    converted: list[GermanyTreatyDividendPacketItem2025] = []
    for item_id in sorted(germany_by_item_id):
        germany_item = germany_by_item_id[item_id]
        us_item = us_by_item_id[item_id]
        if us_item.gross_dividend_usd <= Decimal("0.00"):
            raise ValueError("U.S. treaty dividend item gross must be positive when matched to a Germany packet item.")
        gross_eur = germany_item.gross_dividend_eur
        implied_fx = (gross_eur / us_item.gross_dividend_usd).quantize(
            Decimal("0.000001"),
            rounding=ROUND_HALF_UP,
        )
        article_10_ceiling_usd = (us_item.gross_dividend_usd * article_10_rate).quantize(
            cent, rounding=ROUND_HALF_UP
        )
        converted.append(
            GermanyTreatyDividendPacketItem2025(
                item_id=item_id,
                owner_slot=germany_item.owner_slot,
                dividend_class=germany_item.dividend_class,
                gross_dividend_eur=gross_eur,
                gross_dividend_usd=us_item.gross_dividend_usd,
                german_taxable_dividend_eur=germany_item.german_taxable_dividend_eur,
                article_10_source_tax_ceiling_usd=article_10_ceiling_usd,
                german_precredit_tax_on_us_source_dividend_usd=(
                    germany_item.germany_precredit_tax_eur / eur_per_usd
                ).quantize(cent, rounding=ROUND_HALF_UP),
                german_residence_credit_for_us_tax_usd=min(
                    (germany_item.germany_residence_credit_eur / eur_per_usd).quantize(
                        cent, rounding=ROUND_HALF_UP
                    ),
                    # DBA-USA Art. 23 + Pub. 514 line 17: residence-country credit
                    # cannot exceed the source-country treaty rate. Clip by the
                    # USD-clean Article 10 ceiling so per-item EUR rounding cannot
                    # push the converted credit above the matched ceiling.
                    article_10_ceiling_usd,
                ),
                fx_reconciliation=(
                    "Germany same-run treaty packet EUR gross matched to explicit U.S. treaty dividend item "
                    f"{item_id} at implied EUR/USD {implied_fx}; amount coverage is by item ID, not reverse-FX "
                    "equality. EUR-side per-Posten cap was built from daily-FX-priced underlying dividend rows "
                    "per § 32d Abs. 5 EStG; USD-side projection uses IRS yearly-average FX "
                    f"{eur_per_usd} per Pub. 514 (2024 ed.) FX guidance. Article 10(2)(b) source-tax ceiling is "
                    "computed directly from US gross at 15 percent (no EUR round-trip), and the residence-"
                    "country credit is clipped by that USD ceiling so daily/yearly FX basis mismatch cannot "
                    "let the converted credit exceed Pub. 514 line 17."
                ),
            )
        )
    return tuple(converted)


def write_germany_treaty_dividend_audit_2025(
    paths: YearPaths,
    *,
    items: tuple[GermanyUSTreatyDividendPacketItem2025, ...],
) -> Path:
    output_path = paths.analysis_root / GERMANY_US_TREATY_DIVIDEND_AUDIT_NAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprints = germany_treaty_dividend_source_fingerprints_2025(paths)
    lines = [
        "# Germany-U.S. Treaty Dividend Packet",
        "",
        "Audit-only output. The U.S. model does not read this file; the same-run pipeline passes the typed packet in memory.",
        "",
        "## Source Fingerprints",
        "",
    ]
    for path, digest in sorted(fingerprints.items()):
        lines.append(f"- `{path}`: `{digest}`")
    lines.extend(
        [
            "",
            "## Items",
            "",
            "| item_id | owner_slot | dividend_class | gross_dividend_eur | german_taxable_dividend_eur | article_10_source_tax_ceiling_eur | germany_precredit_tax_eur | germany_residence_credit_eur |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in items:
        lines.append(
            " | ".join(
                [
                    f"| {item.item_id}",
                    item.owner_slot,
                    item.dividend_class,
                    format_decimal(item.gross_dividend_eur),
                    format_decimal(item.german_taxable_dividend_eur),
                    format_decimal(item.article_10_source_tax_ceiling_eur),
                    format_decimal(item.germany_precredit_tax_eur),
                    f"{format_decimal(item.germany_residence_credit_eur)} |",
                ]
            )
        )
    lines.extend(
        [
            "",
            "## Totals",
            "",
            f"- gross dividend: {format_decimal(sum((item.gross_dividend_eur for item in items), Decimal('0.00')))} EUR",
            f"- Article 10 source-tax ceiling: {format_decimal(sum((item.article_10_source_tax_ceiling_eur for item in items), Decimal('0.00')))} EUR",
            f"- Germany pre-credit tax: {format_decimal(sum((item.germany_precredit_tax_eur for item in items), Decimal('0.00')))} EUR",
            f"- Germany residence credit: {format_decimal(sum((item.germany_residence_credit_eur for item in items), Decimal('0.00')))} EUR",
            "",
        ]
    )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
