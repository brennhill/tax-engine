"""Auto-derive treaty dividend items from extracted dividend facts.

Pub. 514 treaty re-sourcing (DBA-USA Art. 23(5)(c)) requires per-item
U.S.-source dividend records on both the Germany side (with treaty rate,
allocated treaty-allowed U.S. tax, and dividend classification) and the
U.S. side (with treaty bucket and gross USD amount). Authoring these by
hand for a real Schwab portfolio means dozens to hundreds of rows that
already exist in `derived-facts/germany/income-cashflows.csv`. This
module derives them.

Source authorities (links pinned to year-aware editions where available):
- DBA-USA Art. 10(2)(b) (15 % portfolio-dividend source-tax cap):
  https://www.irs.gov/pub/irs-trty/germany.pdf (1989 treaty + 2006 protocol)
  Technical Explanation: https://www.irs.gov/pub/irs-trty/germtech.pdf
- DBA-USA Art. 23(5)(c) (re-sourcing rule — U.S.-source items deemed to
  arise in Germany), read with Art. 23(5)(b) (U.S. credit for the German
  tax on those items): https://www.irs.gov/pub/irs-trty/germany.pdf
- IRS Publication 514 (2024 ed., applicable for 2025 returns) "Tax
  Treaties" section, treaty-resourcing worksheet lines 16/17/18/19:
  https://www.irs.gov/publications/p514
- IRC §§ 861(a)(2), 862(a)(2) (dividend source by payor incorporation):
  https://www.law.cornell.edu/uscode/text/26/861
- § 32d Abs. 5 EStG (Germany per-Posten foreign tax credit):
  https://www.gesetze-im-internet.de/estg/__32d.html
- BMF Schreiben v. 19.05.2022, IV C 1 - S 2252/19/10003 :009 (Einzelfragen
  zur Abgeltungsteuer; Posten-Begriff für § 32d Abs. 5 EStG, Rn. 202-204):
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2022-05-19-einzelfragen-zur-abgeltungsteuer.html
- InvStG § 2 Abs. 6 (Aktienfonds vs. Sonstige threshold) and § 2 Abs. 8
  (Beteiligungskapital definition):
  https://www.gesetze-im-internet.de/invstg_2018/__2.html
- InvStG § 20 (Teilfreistellung rates: 30 % Aktienfonds for natural-person
  Privatvermögen, 0 % Sonstige):
  https://www.gesetze-im-internet.de/invstg_2018/__20.html

Derivation rules:
1. For every `kind=dividend` row in income-cashflows.csv whose symbol is
   NOT in the configured foreign-source set (default: ENB; workspaces add
   foreign-domiciled holdings via `manual_overrides.treaty_resourcing.
   non_us_source_symbols`), aggregate by symbol-year and generate matching
   DE/US treaty items with shared `item_id`.
2. Skip rows whose `us_1099_box` column is set to a value other than `1a`
   (typically `2a` = capital-gain distributions, `3` = nondividend / return
   of capital). These are German-taxable as fund Ausschüttungen under
   InvStG § 16 but not eligible for Pub. 514 treaty re-sourcing because
   they are not "ordinary dividends" under IRC § 316.
3. Map `asset_bucket` + repo fund classification → `dividend_class` (DE)
   and `treaty_bucket` (US):
     stock                       → portfolio_dividend / direct_equity
     fund_like + aktienfonds     → equity_fund_dividend / equity_fund
     fund_like + non_aktienfonds → non_equity_fund_dividend / non_equity_fund
4. `treaty_rate = 0.15` (DBA-USA Art. 10(2)(b) portfolio-dividend cap).
5. `allocated_us_tax_paid_eur = TREATY_RATE × gross_dividend_eur` (treaty-
   imputed U.S. tax — actual U.S. tax for a U.S. citizen of Germany is paid
   via Form 1040, not withheld at source; Pub. 514 worksheet uses the
   treaty cap as the residence-credit ceiling on line 17).
6. `german_taxable_dividend_eur = gross × (1 - Teilfreistellung)` to mirror
   what DE25-15 computes inside `foreign_taxable_item_by_key_before_
   allowance`. Teilfreistellung rates assume natural-person investor in
   Privatvermögen; betriebliches Vermögen would use 60 %/40 %.
7. `item_id = <symbol>_<YYYY>_<owner>` for determinism. Per-symbol-annual
   aggregation is the smallest unit that round-trips between EUR and USD
   without per-payment quantization drift on Pub. 514 line 16 (BMF
   Abgeltungsteuer Schreiben treats the symbol-year stack as one Posten
   for § 32d(5) cap purposes).
8. Owner defaults to `person_1` (the household U.S. filer); workspaces
   with per-row owner annotations in income-cashflows need a future
   extension here.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
from pathlib import Path
from typing import Iterable

from tax_pipeline.paths import YearPaths
from tax_pipeline.year_runtime import resolve_year_paths

# DBA-USA Art. 10(2)(b) portfolio-dividend source-tax cap.
# https://www.irs.gov/pub/irs-trty/germany.pdf
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE as _DBA_ART_10_2_B_RATE,
)

TREATY_RATE = _DBA_ART_10_2_B_RATE

# InvStG § 20 Teilfreistellung rates for natural-person investors holding
# investment-fund shares in Privatvermögen (non-business). Betriebliches
# Vermögen uses 60 %/40 % under § 20 Abs. 1 Nr. 1; the engine does not
# currently model business holdings.
# The German rule graph at DE25-15 multiplies fund-like dividend gross
# amounts by (1 - rate) when building
# `foreign_taxable_item_by_key_before_allowance`, so the treaty packet
# item's `german_taxable_dividend_eur` must mirror that reduction or
# DE25-15 fails closed (y2025/germany_capital_rules.py:411-415).
# https://www.gesetze-im-internet.de/invstg_2018/__20.html
TEILFREISTELLUNG_RATE_AKTIENFONDS = Decimal("0.30")
TEILFREISTELLUNG_RATE_NON_AKTIENFONDS = Decimal("0.00")
TEILFREISTELLUNG_RATE_DIRECT_STOCK = Decimal("0.00")

# Default set of symbols whose dividends are NOT U.S.-source under the
# IRC §§ 861(a)(2) / 862(a)(2) source-by-payor rule and therefore cannot
# benefit from DBA-USA Art. 10/23 re-sourcing. ENB (Enbridge Inc.) is a
# Canadian payor; its dividends are Canadian-source. Workspaces extend
# this set via `manual_overrides.treaty_resourcing.non_us_source_symbols`
# for additional foreign-domiciled holdings.
# https://www.law.cornell.edu/uscode/text/26/861
DEFAULT_FOREIGN_SOURCE_SYMBOLS = frozenset({"ENB"})

# Output filenames (must match treaty_bridge_2025.py constants).
DE_TREATY_ITEMS_FILENAME = "de-us-treaty-dividend-items.csv"
US_TREATY_ITEMS_FILENAME = "us-treaty-dividend-items.csv"


def _looks_auto_generated_treaty_item_id(value: str, *, symbol: str, owner: str) -> bool:
    """Return True if `value` looks like a foreign_tax_item_id this module
    previously generated for `(symbol, owner)`.

    Two patterns are considered auto-generated:
    - Per-symbol-annual:    ``<symbol>_2025_<owner>``
    - Legacy per-payment:   ``<symbol>_2025_<MM>_<DD>_<owner>[_<n>]`` where
      ``MM`` ∈ 01-12 and ``DD`` ∈ 01-31. Strict MM/DD validation prevents a
      user-authored id like ``<symbol>_2025_42_99_<owner>`` from being
      mistaken for an auto-generated one and silently overwritten.

    Comparison is case-insensitive on the symbol and owner parts so legacy
    casings still match.
    """
    import re

    v = (value or "").strip()
    if not v:
        return False
    sym = symbol.lower()
    own = owner.lower()
    v_lower = v.lower()
    annual = f"{sym}_2025_{own}"
    if v_lower == annual:
        return True
    # Per-payment: <sym>_2025_MM_DD_<own>[_<digits>]
    pattern = rf"^{re.escape(sym)}_2025_(\d{{2}})_(\d{{2}})_{re.escape(own)}(?:_\d+)?$"
    match = re.match(pattern, v_lower)
    if not match:
        return False
    month = int(match.group(1))
    day = int(match.group(2))
    if not (1 <= month <= 12):
        return False
    if not (1 <= day <= 31):
        return False
    return True


def _classify(symbol: str, asset_bucket: str, aktienfonds: frozenset[str], non_aktienfonds: frozenset[str]) -> tuple[str, str]:
    """Return (dividend_class, treaty_bucket) for one row.

    InvStG § 2 Abs. 6 distinguishes equity-fund and non-equity-fund
    Investmentanteile based on the >50 % Beteiligungskapital threshold
    defined in § 2 Abs. 8. Direct-stock dividends are portfolio_dividend /
    direct_equity (no Teilfreistellung).
    https://www.gesetze-im-internet.de/invstg_2018/__2.html
    """
    if asset_bucket == "stock":
        return ("portfolio_dividend", "direct_equity")
    if asset_bucket == "fund_like":
        if symbol in aktienfonds:
            return ("equity_fund_dividend", "equity_fund")
        if symbol in non_aktienfonds:
            return ("non_equity_fund_dividend", "non_equity_fund")
        raise ValueError(
            f"Symbol {symbol!r} (asset_bucket=fund_like) has no InvStG § 2 Abs. 6 "
            "classification. Add the symbol to either tax_pipeline/data/"
            "german_fund_classification.csv (preferred — engine-shipped, citation-"
            "anchored) or to this workspace's manual_overrides.fund_classification "
            "block. Failing closed because the Teilfreistellung rate cannot be "
            "guessed from the ticker."
        )
    raise ValueError(f"Unsupported asset_bucket {asset_bucket!r} for symbol {symbol!r}.")


def _ensure_unique(seen: set[str], candidate: str) -> str:
    base = candidate
    i = 2
    while candidate in seen:
        candidate = f"{base}_{i}"
        i += 1
    seen.add(candidate)
    return candidate


def derive_treaty_dividend_items_2025(
    *,
    income_cashflows_rows: Iterable[dict[str, str]],
    aktienfonds: Iterable[str],
    non_aktienfonds: Iterable[str],
    foreign_source_symbols: Iterable[str] = DEFAULT_FOREIGN_SOURCE_SYMBOLS,
    default_owner_slot: str = "person_1",
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Pure derivation function.

    Returns ``(de_rows, us_rows, updated_income_cashflows_rows)``:
    - ``de_rows``: rows for ``de-us-treaty-dividend-items.csv``
    - ``us_rows``: rows for ``us-treaty-dividend-items.csv``
    - ``updated_income_cashflows_rows``: copy of the input rows with each
      treaty-eligible dividend's ``foreign_tax_item_id`` populated to the
      matching treaty item's id, so the German rule graph at DE25-15 can
      pair the per-Posten taxable-income with the treaty packet item via
      ``foreign_tax_item_id`` (y2025/germany_capital_rules.py:407).

    Inputs are normalized strings/sequences so the function is trivially
    testable without filesystem fixtures.
    """
    aktienfonds_set = frozenset(aktienfonds)
    non_aktienfonds_set = frozenset(non_aktienfonds)
    # Normalize the foreign-source set to upper-case so case differences
    # between the workspace config and the income-cashflows rows cannot
    # silently let a foreign-source row leak into the treaty packet.
    foreign_source_set = frozenset(s.upper() for s in foreign_source_symbols)

    # Per-symbol-annual aggregation: § 32d Abs. 5 EStG accepts per-symbol-year
    # as the "Posten" unit per BMF Schreiben v. 19.05.2022 IV C 1 - S 2252/19/
    # 10003 :009 (Einzelfragen zur Abgeltungsteuer; Posten-Begriff für § 32d
    # Abs. 5, Rn. 202-204). Pub. 514 likewise treats Box 1a as an annual stack
    # and DBA-USA Art. 23(5)(b) references the residence-country tax on the
    # same dividend stack used on the U.S. additional-FTC worksheet.
    # Aggregating per-symbol-year is also the smallest unit that round-trips
    # between EUR and USD without per-payment rounding accumulation pushing
    # the German allowed-U.S.-tax over the Pub. 514 line 16 ceiling.
    aggregates: dict[str, dict[str, object]] = {}
    updated_rows: list[dict[str, str]] = []

    for row in income_cashflows_rows:
        out_row = dict(row)
        updated_rows.append(out_row)

        if row.get("kind") != "dividend":
            continue
        # Normalize symbol to upper-case once so downstream membership
        # tests against the (upper-cased) classification sets and the
        # foreign-source set work regardless of casing on input rows.
        symbol = (row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        if symbol in foreign_source_set:
            continue
        # Skip non-Box-1a rows: Box 2a (capital-gain distributions) and
        # Box 3 (nondividend / return of capital) are German-taxable as
        # fund Ausschüttungen under InvStG § 16 but are not "ordinary
        # dividends" under IRC § 316 and therefore not eligible for
        # Pub. 514 / DBA-USA Art. 10 source-country re-sourcing.
        us_1099_box = (row.get("us_1099_box") or "").strip().lower()
        if us_1099_box and us_1099_box != "1a":
            continue
        asset_bucket = (row.get("asset_bucket") or "").strip()
        if not asset_bucket:
            raise ValueError(
                f"Missing asset_bucket on dividend row for {symbol} "
                f"({row.get('date')}): every dividend row must specify "
                "stock | fund_like | option | cash so InvStG § 2 Abs. 6 "
                "classification can be applied."
            )
        try:
            gross_eur_row = Decimal(row["eur_amount"])
            gross_usd_row = Decimal(row["usd_amount"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(
                f"Dividend row for {symbol} ({row.get('date')}) has missing or "
                f"non-numeric eur_amount / usd_amount; both columns are "
                f"required for the Pub. 514 EUR/USD round-trip."
            ) from exc
        if gross_eur_row <= Decimal("0.00"):
            continue
        owner = default_owner_slot
        item_id = f"{symbol.lower()}_2025_{owner}"
        agg = aggregates.setdefault(
            symbol,
            {
                "item_id": item_id,
                "owner": owner,
                "asset_bucket": asset_bucket,
                "gross_eur": Decimal("0.00"),
                "gross_usd": Decimal("0.00"),
                "rows": [],
            },
        )
        if agg["asset_bucket"] != asset_bucket:
            raise ValueError(
                f"Symbol {symbol} has inconsistent asset_bucket across dividend rows: "
                f"{agg['asset_bucket']!r} vs {asset_bucket!r}."
            )
        agg["gross_eur"] = agg["gross_eur"] + gross_eur_row
        agg["gross_usd"] = agg["gross_usd"] + gross_usd_row
        agg["rows"].append(out_row)

    de_rows: list[dict[str, str]] = []
    us_rows: list[dict[str, str]] = []
    for symbol, agg in sorted(aggregates.items()):
        item_id = agg["item_id"]
        owner = agg["owner"]
        asset_bucket = agg["asset_bucket"]
        # Keep the EUR sum at full precision until after Teilfreistellung is
        # applied — DE25-15 (y2025/germany_capital_rules.py:411) compares
        # q2(sum(row.eur × (1 - rate))) to q2(german_taxable_dividend_eur),
        # so quantizing gross_eur first would drift by sub-cent rounding.
        gross_eur_precise = agg["gross_eur"]
        gross_eur = gross_eur_precise.quantize(Decimal("0.01"))
        gross_usd = agg["gross_usd"].quantize(Decimal("0.01"))
        dividend_class, treaty_bucket = _classify(
            symbol,
            asset_bucket,
            aktienfonds_set,
            non_aktienfonds_set,
        )
        if treaty_bucket == "equity_fund":
            teilfreistellung_rate = TEILFREISTELLUNG_RATE_AKTIENFONDS
        elif treaty_bucket == "non_equity_fund":
            teilfreistellung_rate = TEILFREISTELLUNG_RATE_NON_AKTIENFONDS
        else:
            teilfreistellung_rate = TEILFREISTELLUNG_RATE_DIRECT_STOCK
        german_taxable_eur = (gross_eur_precise * (Decimal("1.00") - teilfreistellung_rate)).quantize(Decimal("0.01"))
        # User-authored foreign_tax_item_ids on the income-cashflows rows take
        # precedence (so manually pinned ids survive); auto-generated ids from
        # earlier runs (per-symbol-annual or per-payment-date patterns) are
        # overwritten with the current per-symbol-annual id so DE25-15 can
        # pair the stack via § 32d(5). Recognition uses strict MM/DD
        # validation — see _looks_auto_generated_treaty_item_id.
        user_ids = {
            (r.get("foreign_tax_item_id") or "").strip()
            for r in agg["rows"]
            if (r.get("foreign_tax_item_id") or "").strip()
            and not _looks_auto_generated_treaty_item_id(
                (r.get("foreign_tax_item_id") or "").strip(),
                symbol=symbol,
                owner=owner,
            )
        }
        if len(user_ids) == 1:
            item_id = next(iter(user_ids))
        elif len(user_ids) > 1:
            raise ValueError(
                f"Symbol {symbol} has conflicting user-authored foreign_tax_item_id values across rows: "
                f"{sorted(user_ids)}; cannot pick one for the per-symbol-annual treaty item."
            )
        for r in agg["rows"]:
            existing = (r.get("foreign_tax_item_id") or "").strip()
            if existing and not _looks_auto_generated_treaty_item_id(
                existing, symbol=symbol, owner=owner
            ) and existing != item_id:
                # User-authored ID different from chosen one; should not happen because
                # we'd have raised above, but defensive.
                continue
            r["foreign_tax_item_id"] = item_id
        allocated_us_tax_eur = (gross_eur_precise * TREATY_RATE).quantize(Decimal("0.01"))
        de_rows.append(
            {
                "item_id": item_id,
                "owner_slot": owner,
                "gross_dividend_eur": format(gross_eur, "f"),
                "german_taxable_dividend_eur": format(german_taxable_eur, "f"),
                "allocated_us_tax_paid_eur": format(allocated_us_tax_eur, "f"),
                "treaty_rate": format(TREATY_RATE, "f"),
                "dividend_class": dividend_class,
                "source": "auto-derived from derived-facts/germany/income-cashflows.csv",
                "note": (
                    f"DBA-USA Art. 10 + Pub. 514: U.S.-source dividend stack on {symbol} for 2025; "
                    "imputed treaty-allowed U.S. tax = 15 % of annual gross."
                ),
            }
        )
        us_rows.append(
            {
                "item_id": item_id,
                "treaty_bucket": treaty_bucket,
                "gross_dividend_usd": format(gross_usd, "f"),
                "source": "auto-derived from derived-facts/germany/income-cashflows.csv",
                "note": f"Matches the Germany treaty-dividend item for {symbol} 2025 Pub. 514 re-sourcing.",
            }
        )

    return de_rows, us_rows, updated_rows


def _read_income_cashflows(paths: YearPaths) -> list[dict[str, str]]:
    """Read derived Germany income-cashflows for the year.

    Returns an empty list when the CSV is absent. This is intentional for
    empty workspaces (no per-row dividend facts have been derived yet);
    callers gate on ``rows`` being non-empty before writing the treaty
    items file, so a missing CSV produces zero treaty items rather than
    crashing. Note (L5, 2026-05-01 correctness review): a malformed-but-
    technically-readable CSV with zero data rows would also produce an
    empty list silently. Validation of the upstream income-cashflows
    derivation is the responsibility of that derivation, not this reader.
    """
    p = paths.derived_facts_root / "germany" / "income-cashflows.csv"
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_manual_overrides(paths: YearPaths) -> dict:
    """Load manual_overrides.json with the canonical error wrapping.

    Mirrors run_year._read_json_config so the "Invalid JSON in config/
    manual_overrides.json" error message remains stable for tests and
    operators. Returns an empty dict when the file is absent — the
    auto-derivation also gates on income-cashflows.csv presence, so an
    empty workspace produces zero treaty items rather than crashing.
    """
    import json
    if not paths.manual_overrides_path.exists():
        return {}
    try:
        payload = json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in config/manual_overrides.json: {paths.manual_overrides_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"config/manual_overrides.json must contain a JSON object: {paths.manual_overrides_path}"
        )
    return payload


def _read_fund_classification(paths: YearPaths) -> tuple[frozenset[str], frozenset[str]]:
    """Read fund classification by merging the engine-shipped repo CSV with
    workspace ``manual_overrides.fund_classification``.

    Seeds from ``tax_pipeline/data/german_fund_classification.csv`` (canonical
    InvStG § 2 Abs. 6 mapping, stable across years). Workspace
    ``manual_overrides.json`` then extends or overrides per-symbol entries.
    Both array and ``fund_types`` dict schemas are accepted on the workspace
    side. Symbols are upper-cased exactly as the rest of the engine does so
    the per-Posten classification here matches what germany_capital_2025_rules
    applies downstream.
    """
    from tax_pipeline.fund_classification_data import load_repo_german_fund_classification

    classification: dict[str, str] = dict(load_repo_german_fund_classification())

    overrides = _load_manual_overrides(paths)
    fc = overrides.get("fund_classification", {})

    fund_types = fc.get("fund_types", {}) or {}
    if not isinstance(fund_types, dict):
        raise ValueError("manual_overrides.fund_classification.fund_types must be an object keyed by symbol.")
    for symbol, raw_type in fund_types.items():
        cleaned = str(symbol).strip().upper()
        if not cleaned:
            continue
        normalized = str(raw_type).strip().lower()
        if normalized in {"aktienfonds", "equity"}:
            classification[cleaned] = "aktienfonds"
        elif normalized in {"sonstige", "non_equity", "non_aktienfonds"}:
            classification[cleaned] = "sonstige"
        else:
            raise ValueError(
                f"manual_overrides.fund_classification.fund_types[{cleaned!r}] is "
                f"{raw_type!r}; must be one of aktienfonds/equity or sonstige/non_aktienfonds."
            )
    for symbol in fc.get("aktienfonds", []) or []:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            classification[cleaned] = "aktienfonds"
    for symbol in fc.get("non_aktienfonds", []) or []:
        cleaned = str(symbol).strip().upper()
        if cleaned:
            classification[cleaned] = "sonstige"

    aktienfonds_set = {sym for sym, t in classification.items() if t == "aktienfonds"}
    non_aktienfonds_set = {sym for sym, t in classification.items() if t == "sonstige"}
    return frozenset(aktienfonds_set), frozenset(non_aktienfonds_set)


def _read_foreign_source_symbols(paths: YearPaths) -> frozenset[str]:
    """Read manual_overrides.json treaty_resourcing.non_us_source_symbols, if any.

    Defaults to ``DEFAULT_FOREIGN_SOURCE_SYMBOLS`` (currently ``{"ENB"}`` —
    the Canadian midstream pipeline whose dividends are NOT U.S.-source
    under DBA-USA Art. 10). Workspaces that hold additional non-U.S.-domiciled
    holdings on a U.S. broker (e.g. an international fund) must declare them
    explicitly in ``treaty_resourcing.non_us_source_symbols`` so Pub. 514
    re-sourcing does not erroneously include them.
    """
    overrides = _load_manual_overrides(paths)
    block = overrides.get("treaty_resourcing", {}) or {}
    extras = block.get("non_us_source_symbols", []) or []
    if not isinstance(extras, list):
        raise ValueError(
            "manual_overrides.treaty_resourcing.non_us_source_symbols must be a list of ticker strings."
        )
    cleaned = {str(s).strip().upper() for s in extras if str(s).strip()}
    return frozenset(DEFAULT_FOREIGN_SOURCE_SYMBOLS | cleaned)


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_treaty_dividend_items_2025(paths: YearPaths) -> tuple[Path, Path, int]:
    """Derive and write both treaty-dividend-items CSVs, plus stamp the
    matching ``foreign_tax_item_id`` into income-cashflows.csv.

    Returns (de_path, us_path, item_count). Idempotent: each call rebuilds
    from the current income-cashflows.csv and overwrites the two output
    files. The income-cashflows.csv is rewritten only if the IDs changed.

    Fails closed if the workspace's income-cashflows.csv lacks per-row
    ``usd_amount`` or ``asset_bucket`` columns. Tax-law math cannot be
    guessed from a partial schema; auditable per-Posten Pub. 514 treaty
    items require both the EUR amount (for the German § 32d Abs. 5 cap)
    and the USD amount (for the U.S. Form 1116 re-sourcing aggregate).
    """
    rows = _read_income_cashflows(paths)
    if rows:
        required = {"usd_amount", "asset_bucket"}
        missing = required - rows[0].keys()
        if missing:
            raise ValueError(
                "Cannot auto-derive Pub. 514 treaty dividend items: "
                f"derived-facts/germany/income-cashflows.csv is missing column(s) {sorted(missing)}. "
                "Tax-law math must not be guessed from a partial schema — populate the column "
                "(see DBA-USA Art. 10 / IRS Pub. 514 worksheet) or fix the upstream extractor."
            )
    aktienfonds, non_aktienfonds = _read_fund_classification(paths)
    foreign_source = _read_foreign_source_symbols(paths)
    de_rows, us_rows, updated_rows = derive_treaty_dividend_items_2025(
        income_cashflows_rows=rows,
        aktienfonds=aktienfonds,
        non_aktienfonds=non_aktienfonds,
        foreign_source_symbols=foreign_source,
    )
    de_path = paths.tax_positions_root / DE_TREATY_ITEMS_FILENAME
    us_path = paths.tax_positions_root / US_TREATY_ITEMS_FILENAME
    de_fields = [
        "item_id",
        "owner_slot",
        "gross_dividend_eur",
        "german_taxable_dividend_eur",
        "allocated_us_tax_paid_eur",
        "treaty_rate",
        "dividend_class",
        "source",
        "note",
    ]
    us_fields = ["item_id", "treaty_bucket", "gross_dividend_usd", "source", "note"]
    _write_csv(de_path, de_rows, de_fields)
    _write_csv(us_path, us_rows, us_fields)

    # Write back the income-cashflows.csv with stamped foreign_tax_item_ids
    # so DE25-15 can pair each treaty packet item with its taxable income.
    income_path = paths.derived_facts_root / "germany" / "income-cashflows.csv"
    if rows and updated_rows != rows:
        original_fields = list(rows[0].keys())
        # Ensure foreign_tax_item_id is part of the schema even if it wasn't
        # in the source CSV (legacy workspaces may lack the column).
        if "foreign_tax_item_id" not in original_fields:
            original_fields.append("foreign_tax_item_id")
        _write_csv(income_path, updated_rows, original_fields)

    return de_path, us_path, len(de_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("year", help="tax year, e.g. 2025 or demo-2025")
    parser.add_argument("--workspace", type=Path, default=None, help="optional workspace override")
    args = parser.parse_args()
    # NOTE (L6, 2026-05-01 correctness review): hardcodes the assumption
    # that this file lives at ``tax_pipeline/y2025/derive_treaty_dividend_items.py``
    # (depth 2 -> project root). Moving the file requires updating this
    # parents[N] index. A centralized ``project_root`` helper would be
    # more robust; deferred to a future structural cleanup.
    project_root = Path(__file__).resolve().parents[1]
    paths = resolve_year_paths(project_root, args.year, workspace_root=args.workspace)
    de_path, us_path, count = write_treaty_dividend_items_2025(paths)
    print(f"Wrote {count} treaty dividend items:")
    print(f"  Germany side: {de_path}")
    print(f"  U.S. side:    {us_path}")


if __name__ == "__main__":
    main()
