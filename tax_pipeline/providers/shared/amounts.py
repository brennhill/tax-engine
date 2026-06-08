from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def fmt_money(value: Decimal) -> str:
    return format(q2(value), "f")


def fmt_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return format(value.quantize(Decimal("1")), "f")
    return fmt_money(value)


def parse_us_amount(raw: str) -> Decimal:
    cleaned = raw.replace(",", "").replace("$", "").replace(" ", "").strip()
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    return Decimal(cleaned)


def parse_german_standard_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def parse_german_decimal_comma_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(".", "").replace(",", ".").replace("€", "")
    return Decimal(cleaned)


def parse_localized_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace("$", "").replace("€", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(".") > cleaned.rfind(","):
            cleaned = cleaned.replace(",", "")
        else:
            cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return Decimal(cleaned)


def parse_german_compact_cents(raw: str) -> Decimal:
    digits = "".join(char for char in raw if char.isdigit())
    return Decimal(digits) / Decimal("100")
