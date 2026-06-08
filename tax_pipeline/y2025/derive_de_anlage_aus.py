"""Auto-derive per-country § 34c / § 32d Abs. 5 EStG foreign-tax-credit
breakdown for Anlage AUS 2025.

Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the C2 deferred item.

Anlage AUS is the German tax-return surface for foreign income / per-
country § 34c EStG foreign-tax-credit determinations. The form expects
one block per country with Zeile 4 (Land) / 6 (Art der Einkünfte) /
8-9 (Einkünfte EUR) / 11-13 (Steuer in Quellenwährung + EUR) / 15
(anrechenbare Steuer per § 34c (1) EStG).

The engine's existing rule graph aggregates foreign-tax credit at
``de.capital.foreign_tax_credit_applied_eur`` (DE25-18-SECTION-32D5-FTC).
This module breaks that aggregate down by country by reading the two
upstream artifacts that already carry country attribution:

1. ``outputs/tax-positions/de-us-treaty-dividend-items.csv`` —
   one row per U.S.-source dividend item with its allocated treaty
   foreign tax in EUR. All rows here are ``country = "US"``.
2. ``normalized/derived-facts/usa/1099-div-detail.csv`` —
   per-symbol Box 1a / 7 columns + a ``foreign_tax_country`` column.
   Symbols with ``box_7_foreign_tax_paid_usd > 0`` AND a non-empty
   ``foreign_tax_country`` are foreign-source under IRC § 862(a)(2)
   and the Box 7 dollars are NOT eligible for DBA-USA Art. 23 re-
   sourcing. The corresponding EUR-translated foreign-tax flows into
   ``de.capital.foreign_tax_credit_applied_eur`` from the
   ``income-cashflows.csv`` ``foreign_tax`` rows for the same symbol.

Output: ``outputs/tax-positions/de-anlage-aus-by-country.csv`` with
columns:

  - ``country`` — ISO-3166 alpha-2 country code
  - ``income_type`` — ``"capital_dividend"`` (the only modeled type)
  - ``foreign_income_eur`` — EUR aggregate of foreign-source income
  - ``foreign_tax_source_currency`` — source-currency tax (USD for
    Schwab-domiciled rows; informational, not transmitted on the form
    line — Anlage AUS Zeilen 11-13 transcribe both source-currency
    and EUR-translated)
  - ``foreign_tax_eur`` — EUR-translated foreign tax paid
  - ``anrechenbar_eur`` — the per-country anrechenbare Steuer claimed
    on Anlage AUS Zeile 15. For brenn-2025 with a single dominant US
    bucket this matches the per-country foreign_tax_eur up to the
    DE25-18 aggregate cap; the renderer also surfaces a reconciliation
    row that equals the aggregate ``foreign_tax_credit_applied_eur``
    output of the rule graph.

Authority:
- § 34c Abs. 1 EStG — https://www.gesetze-im-internet.de/estg/__34c.html
- § 32d Abs. 5 EStG — https://www.gesetze-im-internet.de/estg/__32d.html
- DBA-USA Art. 10 / Art. 23 — https://www.irs.gov/pub/irs-trty/germany.pdf
- IRS Pub. 514 — https://www.irs.gov/publications/p514
- IRC § 862(a)(2) — https://www.law.cornell.edu/uscode/text/26/862
- ELSTER help (Anlage AUS 2025) —
  https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_2025
- R 34c EStR — https://ao.bundesfinanzministerium.de/esth/2025/A-Einkommensteuergesetz/V-Steuerermaessigungen-34c-35c/1-Steuerermaessigung-bei-ausl-Eink-34c-34d/Paragraf-34c/r-34c-1-2.html

Authoring constraint (I5): this module lives outside the rule graph,
mirroring ``derive_treaty_dividend_items_2025.py`` and
``derive_foreign_financial_accounts_2025.py``. The renderer reads the
emitted CSV; it does not perform Decimal arithmetic on the emitted
values. The renderer reconciles the per-country sum against the
existing ``de.capital.foreign_tax_credit_applied_eur`` aggregate and
fails closed if they diverge by more than 0.01 EUR.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from tax_pipeline.paths import YearPaths


DE_ANLAGE_AUS_FILENAME = "de-anlage-aus-by-country.csv"

DE_ANLAGE_AUS_FIELDS = [
    "country",
    "income_type",
    "foreign_income_eur",
    "foreign_tax_source_currency",
    "foreign_tax_source_amount",
    "foreign_tax_eur",
    "anrechenbar_eur",
    "evidence_source",
]

ZERO_EUR = Decimal("0.00")
ZERO_USD = Decimal("0.00")


@dataclass(frozen=True)
class AnlageAusCountryRow:
    """A per-country breakdown row for Anlage AUS rendering.

    Identifies (country, income_type) and carries the EUR aggregates
    plus a single source-currency total for the Zeile 11-13 transcription
    (the form lets you write the source-currency amount alongside the
    EUR translation; we surface the dominant source currency observed
    for the country bucket).
    """

    country: str
    income_type: str
    foreign_income_eur: Decimal
    foreign_tax_source_currency: str
    foreign_tax_source_amount: Decimal
    foreign_tax_eur: Decimal
    anrechenbar_eur: Decimal
    evidence_source: str


def _read_csv(path: Path) -> list[dict[str, str]]:
    """Read ``path`` as a list-of-dict CSV (utf-8). Returns ``[]`` when
    the file is absent — callers treat absence as "no rows".
    """
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]


def _read_anlage_aus_overrides(paths: YearPaths) -> dict[str, object]:
    """Load ``manual_overrides.anlage_aus`` if present, else ``{}``.

    Schema (every key is optional; missing keys keep the engine's
    default fail-closed posture):

      {
        "ric_country_breakdown": {
          # Per-symbol manual reclassification of a 1099 RIC pass-
          # through Box 7 row whose underlying fund administrator
          # has supplied a country-of-source breakdown. Without an
          # override the engine emits ``country="RIC"`` (Verschiedene)
          # so the user sees the gap on the rendered Anlage AUS.
          # Authority: IRS Pub. 514 RIC pass-through; § 34c Abs. 1
          # EStG per-Quellenstaat allocation.
          "VXUS": {"country": "JP", "note": "Vanguard 2025 supplemental, JP largest weight"},
          ...
        },
        "bank_certificate_country": {
          # Per-row reclassification of a German-bank-certificate
          # already-credited foreign-tax row whose underlying source
          # country is not recorded on the certificate. Without an
          # override the engine emits ``country="UNKNOWN"``
          # (Verschiedene depository-credited).
          # Authority: § 34c Abs. 1 EStG — the Anrechnungsverfahren
          # is per Quellenstaat; the bank-credited tax must
          # ultimately attach to a country block for filing.
          "lien_bank_foreign_tax_credit_eur": {
              "country": "JP", "note": "Upvest custodian breakdown, JP-source"
          }
        }
      }

    Both override sections are pure reclassification: they NEVER
    change Decimal amounts, only the ``country`` label that flows to
    Anlage AUS Zeile 4. This keeps invariant I5 intact (no Decimal
    arithmetic outside the rule graph) — the override is a string-
    only label substitution.
    """
    if not paths.manual_overrides_path.exists():
        return {}
    try:
        raw = json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    section = raw.get("anlage_aus")
    if not isinstance(section, dict):
        return {}
    return section


def _override_ric_country(
    overrides: dict[str, object], symbol: str
) -> str | None:
    """Return the override country code for ``symbol`` under
    ``manual_overrides.anlage_aus.ric_country_breakdown``, or ``None``
    when no override is configured. Symbol matching is case-insensitive.
    """
    section = overrides.get("ric_country_breakdown")
    if not isinstance(section, dict):
        return None
    entry = section.get(symbol) or section.get(symbol.upper()) or section.get(symbol.lower())
    if not isinstance(entry, dict):
        return None
    country = entry.get("country")
    if isinstance(country, str) and country.strip():
        return country.strip().upper()
    return None


def _override_bank_certificate_country(
    overrides: dict[str, object], row_key: str
) -> str | None:
    """Return the override country code for the German-bank-certificate
    already-credited foreign-tax row keyed by ``row_key``, or ``None``
    when no override is configured.
    """
    section = overrides.get("bank_certificate_country")
    if not isinstance(section, dict):
        return None
    entry = section.get(row_key)
    if not isinstance(entry, dict):
        return None
    country = entry.get("country")
    if isinstance(country, str) and country.strip():
        return country.strip().upper()
    return None


def _q2(value: Decimal) -> Decimal:
    """Quantize to 2 decimal places — matches the engine's q2 helper.

    Re-defined locally so this module does not depend on
    ``germany_capital_2025_rules`` (which would import the rule graph
    transitively).
    """
    return value.quantize(Decimal("0.01"))


def _treaty_us_rows(paths: YearPaths) -> list[AnlageAusCountryRow]:
    """Aggregate the U.S.-source treaty dividend items into one row.

    DBA-USA Art. 10/23: U.S.-source portfolio dividends are foreign-
    source from the German perspective; the treaty caps source-state
    tax at 15 % and the residence state (Germany) credits up to that
    cap under § 32d Abs. 5 EStG. Per-symbol rows aggregate to a single
    Anlage AUS country block ``Land = USA``.
    """
    treaty_csv = paths.tax_positions_root / "de-us-treaty-dividend-items.csv"
    rows = _read_csv(treaty_csv)
    if not rows:
        return []
    foreign_income_eur = ZERO_EUR
    foreign_tax_eur = ZERO_EUR
    for row in rows:
        gross_text = (row.get("gross_dividend_eur") or "").strip()
        tax_text = (row.get("allocated_us_tax_paid_eur") or "").strip()
        if not gross_text or not tax_text:
            continue
        foreign_income_eur += Decimal(gross_text)
        foreign_tax_eur += Decimal(tax_text)
    if foreign_income_eur == ZERO_EUR and foreign_tax_eur == ZERO_EUR:
        return []
    # Source currency for the U.S. bucket is USD; surface the EUR
    # translation in the foreign_tax_eur column and leave the source-
    # currency amount blank — Anlage AUS Zeilen 11-13 accept the EUR
    # number alone for treaty rows that have already been translated.
    return [
        AnlageAusCountryRow(
            country="US",
            income_type="capital_dividend",
            foreign_income_eur=_q2(foreign_income_eur),
            foreign_tax_source_currency="USD",
            foreign_tax_source_amount=ZERO_USD,
            foreign_tax_eur=_q2(foreign_tax_eur),
            anrechenbar_eur=_q2(foreign_tax_eur),
            evidence_source=str(treaty_csv.name),
        )
    ]


def _non_treaty_1099_rows(paths: YearPaths) -> list[AnlageAusCountryRow]:
    """Aggregate non-U.S.-source 1099 Box 7 foreign tax by country.

    1099-div-detail.csv carries the ``foreign_tax_country`` column for
    every Schwab dividend payer that withheld foreign tax. Symbols with
    a non-empty ``foreign_tax_country`` are NOT U.S.-source under IRC
    § 862(a)(2) (e.g. ENB = CANADA, VXUS = RIC = pass-through fund).
    These are captured here so a future workspace with multi-country
    Schwab payers gets per-country Anlage AUS rows.

    Brenn-2025 carries ENB (CANADA, $15.23) and VXUS (RIC, $34.86) in
    1099-div-detail.csv. The income-cashflows.csv side has the
    EUR-translated equivalents; here we surface the USD source-currency
    aggregate for transparency, with the EUR translation pulled from
    income-cashflows.csv via a per-symbol lookup.

    For the ``RIC`` (Regulated Investment Company) bucket: under IRS
    Pub. 514 / 1099-DIV instructions a ``RIC`` country code means the
    foreign tax was paid to multiple jurisdictions and the fund passed
    them through aggregated. The German Finanzamt's treatment is
    pragmatic: list as ``Verschiedene`` (multiple) on Anlage AUS unless
    the user has a per-country breakdown from the fund administrator.
    We surface ``country="RIC"`` to flag this; the user must reclassify
    to a specific country (or ``Verschiedene``) before filing.
    """
    detail_csv = paths.derived_facts_root / "usa" / "1099-div-detail.csv"
    cashflows_csv = paths.derived_facts_root / "germany" / "income-cashflows.csv"
    detail_rows = _read_csv(detail_csv)
    if not detail_rows:
        return []
    overrides = _read_anlage_aus_overrides(paths)
    # Build a per-symbol EUR foreign-tax tally from income-cashflows.csv.
    # This is the authoritative EUR translation for foreign-source
    # rows because the Schwab cashflow extractor applies the year-aware
    # ECB rate at each foreign_tax row.
    cashflow_rows = _read_csv(cashflows_csv)
    eur_tax_by_symbol: dict[str, Decimal] = {}
    eur_income_by_symbol: dict[str, Decimal] = {}
    for row in cashflow_rows:
        symbol = (row.get("symbol") or "").strip().upper()
        kind = (row.get("kind") or "").strip().lower()
        eur_text = (row.get("eur_amount") or "").strip()
        if not symbol or not eur_text:
            continue
        try:
            eur_amount = Decimal(eur_text)
        except (ArithmeticError, ValueError):
            continue
        if kind == "foreign_tax":
            eur_tax_by_symbol[symbol] = eur_tax_by_symbol.get(symbol, ZERO_EUR) + eur_amount
        elif kind == "dividend":
            eur_income_by_symbol[symbol] = eur_income_by_symbol.get(symbol, ZERO_EUR) + eur_amount
    # Bucket detail rows by foreign_tax_country, applying the manual
    # ``ric_country_breakdown`` override when the user has supplied
    # per-symbol country attribution from the fund administrator's
    # supplemental (e.g., Vanguard's annual country-of-source data).
    by_country: dict[str, dict[str, Decimal]] = {}
    for row in detail_rows:
        country = (row.get("foreign_tax_country") or "").strip().upper()
        if not country:
            continue
        symbol = (row.get("symbol") or "").strip().upper()
        # RIC override — per-symbol reclassification under
        # manual_overrides.anlage_aus.ric_country_breakdown.
        if country == "RIC":
            override_country = _override_ric_country(overrides, symbol)
            if override_country:
                country = override_country
        usd_text = (row.get("box_7_foreign_tax_paid_usd") or "0").strip() or "0"
        try:
            usd_amount = Decimal(usd_text)
        except (ArithmeticError, ValueError):
            usd_amount = ZERO_USD
        if usd_amount == ZERO_USD:
            continue
        bucket = by_country.setdefault(
            country,
            {
                "foreign_income_eur": ZERO_EUR,
                "foreign_tax_eur": ZERO_EUR,
                "foreign_tax_usd": ZERO_USD,
            },
        )
        bucket["foreign_income_eur"] += eur_income_by_symbol.get(symbol, ZERO_EUR)
        bucket["foreign_tax_eur"] += eur_tax_by_symbol.get(symbol, ZERO_EUR)
        bucket["foreign_tax_usd"] += usd_amount
    out: list[AnlageAusCountryRow] = []
    for country, totals in sorted(by_country.items()):
        out.append(
            AnlageAusCountryRow(
                country=country,
                income_type="capital_dividend",
                foreign_income_eur=_q2(totals["foreign_income_eur"]),
                foreign_tax_source_currency="USD",
                foreign_tax_source_amount=_q2(totals["foreign_tax_usd"]),
                foreign_tax_eur=_q2(totals["foreign_tax_eur"]),
                # § 32d Abs. 5 EStG: anrechenbar is bounded by the per-
                # country foreign tax actually paid; for non-treaty rows
                # there is no separate cap because the source country
                # didn't impose a treaty rate. Surface the same value as
                # foreign_tax_eur and let the renderer's reconciliation
                # row enforce the aggregate cap.
                anrechenbar_eur=_q2(totals["foreign_tax_eur"]),
                evidence_source=f"{detail_csv.name} + {cashflows_csv.name}",
            )
        )
    return out


def _german_bank_certificate_credited_row(
    paths: YearPaths,
) -> list[AnlageAusCountryRow]:
    """Surface the German-bank-certificate already-credited foreign tax
    as an Anlage AUS row with ``country="UNKNOWN"``.

    Lien's Upvest Jahressteuerbescheinigung Zeile 40 reports
    ``foreign_tax_credit_eur=15.78`` — a foreign tax already credited
    by the German depository under the bank's Quellenstaat
    Anrechnungs­bestätigung mechanism. The amount flows into
    ``de.capital.foreign_tax_credit_applied_eur`` via DE25-18 but the
    underlying source country is not recorded on the German bank
    certificate (the depository abstracts it away). This row exists so
    the Anlage AUS reconciliation against the aggregate
    ``foreign_tax_credit_applied_eur`` closes — the user must
    reclassify ``country="UNKNOWN"`` to a specific country before
    filing if the underlying fund administrator can identify it.

    Authority: § 34c Abs. 1 EStG — the Anrechnungsverfahren applies on
    a per-country basis; the bank-credited tax is included pro forma
    here as ``UNKNOWN`` rather than silently dropped from the
    breakdown. This is the I3-compliant way to surface the gap.
    """
    cert_csv = paths.facts_root / "de-spouse-bank-capital-certificate.csv"
    rows = _read_csv(cert_csv)
    if not rows:
        return []
    foreign_tax_credit_eur = ZERO_EUR
    for row in rows:
        key = (row.get("key") or "").strip()
        if key != "lien_bank_foreign_tax_credit_eur":
            continue
        text = (row.get("value") or "").strip()
        if not text:
            continue
        try:
            foreign_tax_credit_eur = Decimal(text)
        except (ArithmeticError, ValueError):
            return []
        break
    if foreign_tax_credit_eur <= ZERO_EUR:
        return []
    # Bank-certificate country override — per-row reclassification
    # under manual_overrides.anlage_aus.bank_certificate_country.
    # Without an override the engine emits ``country="UNKNOWN"``
    # (Verschiedene depository-credited) so the user sees the gap
    # on the rendered Anlage AUS.
    overrides = _read_anlage_aus_overrides(paths)
    override_country = _override_bank_certificate_country(
        overrides, "lien_bank_foreign_tax_credit_eur"
    )
    country_label = override_country or "UNKNOWN"
    return [
        AnlageAusCountryRow(
            country=country_label,
            income_type="capital_dividend_bank_credited",
            foreign_income_eur=ZERO_EUR,
            foreign_tax_source_currency="EUR",
            foreign_tax_source_amount=_q2(foreign_tax_credit_eur),
            foreign_tax_eur=_q2(foreign_tax_credit_eur),
            anrechenbar_eur=_q2(foreign_tax_credit_eur),
            evidence_source=str(cert_csv.name),
        )
    ]


def derive_anlage_aus_by_country_2025(
    paths: YearPaths,
) -> tuple[AnlageAusCountryRow, ...]:
    """Build the per-country Anlage AUS rows.

    Returns a deterministic id-sorted tuple. Treaty US row (when
    present) is emitted first; non-treaty 1099 rows follow in
    alphabetical country order; the German-bank-certificate
    already-credited row (``country="UNKNOWN"``) is appended last
    when present.
    """
    rows: list[AnlageAusCountryRow] = []
    rows.extend(_treaty_us_rows(paths))
    # Non-treaty rows for non-U.S. countries.
    for non_treaty in _non_treaty_1099_rows(paths):
        if non_treaty.country == "US":
            continue
        rows.append(non_treaty)
    # German-bank-certificate already-credited foreign tax (UNKNOWN
    # country until the user reclassifies).
    rows.extend(_german_bank_certificate_credited_row(paths))
    return tuple(rows)


def write_anlage_aus_by_country_2025(paths: YearPaths) -> tuple[Path, int]:
    """Write the derived per-country CSV; idempotent.

    Returns ``(path, row_count)``.
    """
    rows = derive_anlage_aus_by_country_2025(paths)
    paths.tax_positions_root.mkdir(parents=True, exist_ok=True)
    out_path = paths.tax_positions_root / DE_ANLAGE_AUS_FILENAME
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DE_ANLAGE_AUS_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "country": row.country,
                    "income_type": row.income_type,
                    "foreign_income_eur": format(row.foreign_income_eur, "f"),
                    "foreign_tax_source_currency": row.foreign_tax_source_currency,
                    "foreign_tax_source_amount": format(
                        row.foreign_tax_source_amount, "f"
                    ),
                    "foreign_tax_eur": format(row.foreign_tax_eur, "f"),
                    "anrechenbar_eur": format(row.anrechenbar_eur, "f"),
                    "evidence_source": row.evidence_source,
                }
            )
    return out_path, len(rows)


__all__ = [
    "DE_ANLAGE_AUS_FILENAME",
    "DE_ANLAGE_AUS_FIELDS",
    "AnlageAusCountryRow",
    "derive_anlage_aus_by_country_2025",
    "write_anlage_aus_by_country_2025",
]
