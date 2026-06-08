from __future__ import annotations

import re
from datetime import datetime


def normalize_date(raw: str) -> str:
    return re.sub(r"\s+", "", raw)


def iso_us_date(raw: str) -> str:
    return datetime.strptime(raw, "%m/%d/%Y").date().isoformat()


def primary_us_date(raw: str) -> str:
    match = re.search(r"([0-9]{2}/[0-9]{2}/[0-9]{4})", raw)
    if not match:
        raise ValueError(f"No MM/DD/YYYY date found in {raw!r}")
    return match.group(1)


_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}


def iso_named_date(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw.strip())
    match = re.match(r"(\d{1,2})\s+([A-Za-zäöüÄÖÜ]+),?\s+(\d{4})", cleaned)
    if not match:
        raise ValueError(f"No named date found in {raw!r}")
    day = int(match.group(1))
    month_name = match.group(2).lower()
    month = _MONTHS[month_name]
    year = int(match.group(3))
    return datetime(year, month, day).date().isoformat()


def iso_month_day_year(raw: str) -> str:
    cleaned = re.sub(r"\s+", " ", raw.strip())
    match = re.match(r"([A-Za-zäöüÄÖÜ]+)\s+(\d{1,2}),\s*(\d{4})", cleaned)
    if not match:
        raise ValueError(f"No month-day-year date found in {raw!r}")
    month_name = match.group(1).lower()
    month = _MONTHS[month_name]
    day = int(match.group(2))
    year = int(match.group(3))
    return datetime(year, month, day).date().isoformat()


def iso_dash_abbrev_date(raw: str) -> str:
    return datetime.strptime(raw.strip(), "%d-%b-%Y").date().isoformat()
