"""Engine-shipped German InvStG fund classification.

The repo-level CSV at tax_pipeline/data/german_fund_classification.csv maps
common U.S.-broker tickers to InvStG § 2 Abs. 6 fund types ("aktienfonds"
or "sonstige") with citations. Classifications are stable over time for
most funds, so shipping them with the engine lets workspaces omit symbols
that are already classified here. A workspace's `config/manual_overrides.
json` `fund_classification` block can extend or override the seed.

Authority:
- InvStG § 2 Abs. 6 (Aktienfonds vs. Sonstige threshold):
  https://www.gesetze-im-internet.de/invstg_2018/__2.html
- InvStG § 2 Abs. 8 (Beteiligungskapital definition; partnership units
  and preferred shares excluded):
  https://www.gesetze-im-internet.de/invstg_2018/__2.html
- InvStG § 20 (Teilfreistellung rates: 30 % Aktienfonds for natural-
  person Privatvermögen, 0 % Sonstige):
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
- BMF Schreiben v. 21.05.2019, IV C 1 - S 1980-1/16/10010 :001 (Anwendung
  des Investmentsteuergesetzes; U.S. RIC / closed-end-fund qualification
  as Investmentfonds under InvStG § 1 Abs. 2):
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Investmentsteuer/2019-05-21-anwendung-des-investmentsteuergesetzes.html
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from pathlib import Path

from tax_pipeline.y2025.germany_law import normalized_fund_type_2025

_DATA_PATH = Path(__file__).resolve().parent / "data" / "german_fund_classification.csv"
_REQUIRED_COLUMNS = frozenset({"symbol", "fund_type"})


def load_repo_german_fund_classification() -> dict[str, str]:
    """Return the engine-shipped ticker → fund-type map.

    Each row in the CSV declares a ticker as "aktienfonds" (>50 % qualifying
    equity Beteiligungskapital under InvStG § 2 Abs. 8) or "sonstige"
    (everything else, including bond CEFs, commodity trusts, MLP funds, and
    preferred-stock ETFs whose underlying is not Beteiligungskapital).

    Fails closed if the CSV is missing or has the wrong header — the file
    ships with the engine, so its absence indicates a packaging or install
    problem that must not silently degrade fund classification.
    """
    if not _DATA_PATH.exists():
        raise FileNotFoundError(
            f"Engine-shipped fund classification CSV is missing at "
            f"{_DATA_PATH}. This file is part of the engine package; an empty "
            "result would silently misclassify every workspace's fund_like "
            "symbols. Reinstall the engine or restore the file from git."
        )
    result: dict[str, str] = {}
    with _DATA_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not _REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = sorted(_REQUIRED_COLUMNS - set(reader.fieldnames or []))
            raise ValueError(
                f"{_DATA_PATH.name} is missing required column(s): {missing}. "
                "The file must declare at least 'symbol' and 'fund_type'."
            )
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            fund_type = normalized_fund_type_2025(row.get("fund_type"), symbol=symbol)
            if symbol in result and result[symbol] != fund_type:
                raise ValueError(
                    f"Duplicate fund classification for {symbol} in "
                    f"{_DATA_PATH.name} with conflicting types: "
                    f"{result[symbol]!r} vs {fund_type!r}"
                )
            result[symbol] = fund_type
    return result


def merge_fund_classification(
    repo_csv: Mapping[str, str],
    fund_types: Mapping[str, str],
    non_aktienfonds: Iterable[str],
    aktienfonds: Iterable[str],
) -> dict[str, str]:
    """Merge the engine-shipped repo CSV with the three workspace overrides.

    Pure function (no I/O) extracted from
    ``tax_pipeline.pipelines.y2025.germany_loaders.load_fund_classification``
    for the WS-5B Pipeline 1 stage ``DERIVE-DE25-FUND-CLASSIFICATION``. The
    engine's repo CSV seeds a stable, citation-anchored baseline; a
    workspace's ``manual_overrides.json`` ``fund_classification`` block then
    extends or overrides per-symbol entries with three knobs:

    1. ``fund_types`` — explicit ``{symbol: fund_type}`` map. Values pass
       through :func:`normalized_fund_type_2025` so unknown labels fail
       closed instead of silently aliasing.
    2. ``non_aktienfonds`` — bulk list of symbols to mark as ``"sonstige"``
       (0 % Teilfreistellung under InvStG § 20 Abs. 1).
    3. ``aktienfonds`` — bulk list of symbols to mark as ``"aktienfonds"``
       (30 % Teilfreistellung under InvStG § 20 Abs. 1 Nr. 1 for natural
       persons holding Privatvermögen).

    Application order matches the legacy loader so behaviour is unchanged:
    repo CSV → ``fund_types`` map → ``non_aktienfonds`` list →
    ``aktienfonds`` list. Later entries override earlier ones for the same
    symbol; this is intentional so workspaces can promote a holding's
    classification when the repo CSV is conservative.

    Authority:

    - InvStG § 2 Abs. 6 (Aktienfonds vs. Sonstige threshold):
      https://www.gesetze-im-internet.de/invstg_2018/__2.html
    - InvStG § 20 (Teilfreistellung rates):
      https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    if not isinstance(fund_types, Mapping):
        # Per CLAUDE.md fail-closed discipline: a non-mapping override would
        # silently lose entries. Surface it as an explicit error so the
        # workspace author fixes the manual_overrides.json schema.
        raise ValueError(
            "fund_classification.fund_types must be an object keyed by symbol."
        )
    result: dict[str, str] = dict(repo_csv)
    for symbol, fund_type in fund_types.items():
        cleaned = str(symbol).strip().upper()
        if cleaned:
            result[cleaned] = normalized_fund_type_2025(fund_type, symbol=cleaned)
    for symbol in non_aktienfonds:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            result[cleaned] = "sonstige"
    for symbol in aktienfonds:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            result[cleaned] = "aktienfonds"
    return result
