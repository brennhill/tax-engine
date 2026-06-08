from __future__ import annotations

import contextvars
import csv
import json
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

from tax_pipeline.analysis_inputs import load_german_model_inputs, structured_input_files
from tax_pipeline.y2025.germany_inputs import load_german_person_slots
from tax_pipeline.y2025.germany_law import (
    FUND_TEILFREISTELLUNG_RATES_2025,
    GermanyBankCapitalCertificate2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
    GermanyTreatyDividendItem2025,
    GermanyVorabpauschaleInput2025,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE,
)
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28
D = Decimal


# WS-5D (invariant migration plan §7): workspace resolution is lazy.
# Resolving ``YEAR_PATHS`` at import time fired filesystem ``stat`` calls
# before any explicit pipeline call and froze the resolved paths for the
# lifetime of the import. The cache is held in a ``ContextVar`` so parallel
# pipeline runs in the same process (different threads / asyncio tasks)
# each see their own resolved paths and a ``runpy.run_module`` re-execution
# of the orchestrator can invalidate the cache via ``reset_year_paths``.
_YEAR_PATHS_VAR: contextvars.ContextVar[YearPaths | None] = contextvars.ContextVar(
    "germany_loaders_year_paths",
    default=None,
)
_STEPS_VAR: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "germany_loaders_steps",
    default=None,
)


def _year_paths() -> YearPaths:
    """Resolve and cache the active ``YearPaths`` for the current context.

    First call performs the environment-driven resolution; subsequent calls
    in the same ``contextvars.Context`` reuse the cached value. Different
    threads or asyncio tasks each see their own cache because they each
    inherit and then write to a private copy of the ContextVar.
    """
    cached = _YEAR_PATHS_VAR.get()
    if cached is not None:
        return cached
    resolved = active_year_paths(Path(__file__), default_year=2025)
    _YEAR_PATHS_VAR.set(resolved)
    return resolved


def _steps() -> Path:
    """Resolve and cache the active ``analysis_root`` for the current context."""
    cached = _STEPS_VAR.get()
    if cached is not None:
        return cached
    resolved = analysis_root(Path(__file__), default_year=2025)
    _STEPS_VAR.set(resolved)
    return resolved


def _structured_inputs() -> dict[str, Path]:
    return structured_input_files(_year_paths())


def _sales_csv() -> Path:
    return _structured_inputs()["germany_capital_sales_detail"]


def _income_csv() -> Path:
    return _structured_inputs()["germany_income_cashflows"]


def _de_us_treaty_dividends_csv() -> Path:
    return _year_paths().tax_positions_root / "de-us-treaty-dividend-items.csv"


def _de_vorabpauschale_inputs_csv() -> Path:
    # InvStG § 19 Vorabpauschale (deemed-distribution) per-fund inputs.
    # Lives under normalized/reference-data/ alongside other workspace-supplied
    # reference inputs (de-tax-constants.csv, ECB rates).
    return (
        _year_paths().reference_data_root
        / "de-vorabpauschale-inputs-2025.csv"
    )


def _coinbase_results_json() -> Path:
    return _steps() / "crypto-private-sales-results.json"


def _dher_results_json() -> Path:
    return _steps() / "germany-dher-results.json"


def reset_year_paths() -> None:
    """Invalidate the cached resolution so the next access re-reads the env.

    ``germany_model.py`` runs the pipeline via ``runpy.run_module(..., alter_sys=True)``
    which re-executes the orchestrator under a fresh env-derived workspace.
    The orchestrator calls this helper after re-binding env vars so the
    next ``_year_paths()`` access reflects the freshly configured workspace
    even if a caller in the same context resolved earlier.
    """
    _YEAR_PATHS_VAR.set(None)
    _STEPS_VAR.set(None)


def __getattr__(name: str):
    """Compatibility shim for legacy module-attribute access.

    Older code (and a few tests that ``mock.patch.object(germany_loaders, ...)``)
    reads ``germany_loaders.YEAR_PATHS`` / ``SALES_CSV`` / etc. directly. Each
    access now triggers the lazy resolver instead of returning a frozen
    import-time value. ``mock.patch.object`` still works because patching sets
    a real module attribute, which shadows ``__getattr__``.
    """
    if name == "YEAR_PATHS":
        return _year_paths()
    if name == "STEPS":
        return _steps()
    if name == "STRUCTURED_INPUTS":
        return _structured_inputs()
    if name == "SALES_CSV":
        return _sales_csv()
    if name == "INCOME_CSV":
        return _income_csv()
    if name == "DE_US_TREATY_DIVIDENDS_CSV":
        return _de_us_treaty_dividends_csv()
    if name == "COINBASE_RESULTS_JSON":
        return _coinbase_results_json()
    if name == "DHER_RESULTS_JSON":
        return _dher_results_json()
    raise AttributeError(f"module 'germany_loaders' has no attribute {name!r}")


FUND_TEILFREISTELLUNG_RATES = FUND_TEILFREISTELLUNG_RATES_2025

BANK_CERTIFICATE_FIELD_ALIASES = {
    "person_2_bank_certificate_kap_income_eur": "kap_line_7_income_eur",
    "lien_bank_kap_income_eur": "kap_line_7_income_eur",
    "person_2_bank_certificate_kap_stock_gain_eur": "kap_line_8_stock_gains_eur",
    "lien_bank_kap_stock_gain_eur": "kap_line_8_stock_gains_eur",
    "person_2_bank_certificate_sparer_pauschbetrag_used_eur": "kap_line_17_saver_allowance_used_eur",
    "lien_bank_sparer_pauschbetrag_used_eur": "kap_line_17_saver_allowance_used_eur",
    "person_2_bank_certificate_kest_withheld_eur": "kap_line_37_kest_withheld_eur",
    "lien_bank_kest_withheld_eur": "kap_line_37_kest_withheld_eur",
    "person_2_bank_certificate_soli_withheld_eur": "kap_line_38_soli_withheld_eur",
    "lien_bank_soli_withheld_eur": "kap_line_38_soli_withheld_eur",
    "person_2_bank_certificate_foreign_tax_credit_eur": "kap_line_40_foreign_tax_credited_eur",
    "lien_bank_foreign_tax_credit_eur": "kap_line_40_foreign_tax_credited_eur",
    "person_2_bank_certificate_foreign_tax_not_credited_eur": "kap_line_41_foreign_tax_not_credited_eur",
    "lien_bank_foreign_tax_not_credited_eur": "kap_line_41_foreign_tax_not_credited_eur",
}


def load_inputs() -> dict[str, Decimal]:
    return load_german_model_inputs(_year_paths())


def load_manual_overrides() -> dict:
    return json.loads(_year_paths().manual_overrides_path.read_text(encoding="utf-8"))


def load_coinbase_results() -> dict[str, Decimal]:
    coinbase_path = _coinbase_results_json()
    if not coinbase_path.exists():
        # Single-filer or non-crypto workspaces may legitimately skip the private-sales sidecar.
        # Keep the core Germany model runnable by treating the missing sidecar as an explicit
        # zero-result path instead of forcing fake Coinbase inputs into the year workspace.
        return {
            "private_sale_result_eur": D("0.00"),
            "prior_private_sale_carryforward_eur": D("0.00"),
            "updated_private_sale_carryforward_eur": D("0.00"),
        }
    raw = json.loads(coinbase_path.read_text(encoding="utf-8"))
    return {key: D(value) for key, value in raw.items()}


def load_dher_results() -> dict[str, Decimal]:
    dher_path = _dher_results_json()
    if not dher_path.exists():
        # Workspaces that only model stock compensation inside payroll can disable the separate
        # equity-comp capital sidecar entirely. In that case the Germany capital model should use
        # an explicit zero employee-share result rather than failing on a missing file.
        return {"total_gain_eur": D("0.00")}
    raw = json.loads(dher_path.read_text(encoding="utf-8"))
    return {key: D(value) for key, value in raw.items() if key.endswith("_eur")}


def load_fund_classification() -> dict[str, str]:
    """Backward-compatible loader-side shim over :func:`merge_fund_classification`.

    The InvStG § 2 Abs. 6 fund-classification merge has been promoted to
    Pipeline 1 stage ``DERIVE-DE25-FUND-CLASSIFICATION`` (WS-5B,
    ``docs/invariant-migration-plan.md`` §1.5). The pure merge function
    lives in :mod:`tax_pipeline.fund_classification_data`. This shim
    keeps the legacy loader-side call sites (``germany_model``,
    ``germany_elster_entry_sheet``, several tests that ``mock.patch`` on
    this name) working unchanged until the Pipeline 2 → derived-facts.json
    wiring lands as a separate workstream.

    Authority:
    - InvStG § 2 Abs. 6 (Aktienfonds vs. Sonstige threshold):
      https://www.gesetze-im-internet.de/invstg_2018/__2.html
    """
    # Seed from the engine-shipped repo CSV (stable over time, with citations).
    # Workspace overrides extend or override per-symbol entries via the
    # canonical merge helper so the legacy and Pipeline 1 paths stay byte-
    # identical for the same inputs.
    from tax_pipeline.fund_classification_data import (
        load_repo_german_fund_classification,
        merge_fund_classification,
    )

    repo_csv = load_repo_german_fund_classification()
    configured = load_manual_overrides().get("fund_classification", {})
    fund_types = configured.get("fund_types", {})
    non_aktienfonds = configured.get("non_aktienfonds", [])
    aktienfonds = configured.get("aktienfonds", [])
    return merge_fund_classification(
        repo_csv,
        fund_types,
        non_aktienfonds,
        aktienfonds,
    )


def load_capital_sale_facts_2025(path: Path | None = None) -> tuple[GermanyCapitalSaleFact2025, ...]:
    source = path or _sales_csv()
    sale_facts: list[GermanyCapitalSaleFact2025] = []
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sale_facts.append(
                GermanyCapitalSaleFact2025(
                    asset_bucket=row["asset_bucket"],
                    symbol=row["symbol"],
                    gain_eur_matched=D(row["gain_eur_matched"]),
                )
            )
    return tuple(sale_facts)


def load_capital_income_facts_2025(path: Path | None = None) -> tuple[GermanyCapitalIncomeFact2025, ...]:
    source = path or _income_csv()
    income_facts: list[GermanyCapitalIncomeFact2025] = []
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            refund_entitlement_raw = row.get("refund_entitlement_eur")
            refund_entitlement = (
                None
                if refund_entitlement_raw in {None, ""}
                else D(refund_entitlement_raw)
            )
            income_facts.append(
                GermanyCapitalIncomeFact2025(
                    kind=row["kind"],
                    asset_bucket=row["asset_bucket"],
                    symbol=row["symbol"],
                    eur_amount=D(row["eur_amount"]),
                    refund_entitlement_eur=refund_entitlement,
                    foreign_tax_item_id=str(row.get("foreign_tax_item_id", "")).strip(),
                )
            )
    return tuple(income_facts)


def load_bank_capital_certificates_2025(
    path: Path | None = None,
    *,
    person_slots: list[dict[str, str]] | None = None,
) -> tuple[GermanyBankCapitalCertificate2025, ...]:
    source = path or _structured_inputs()["de_spouse_bank_capital_certificate"]
    if not source.exists():
        return ()
    available_slots = {slot["slot"] for slot in (person_slots or load_german_person_slots(_year_paths()))}
    values = {
        "kap_line_7_income_eur": D("0.00"),
        "kap_line_8_stock_gains_eur": D("0.00"),
        "kap_line_17_saver_allowance_used_eur": D("0.00"),
        "kap_line_37_kest_withheld_eur": D("0.00"),
        "kap_line_38_soli_withheld_eur": D("0.00"),
        "kap_line_40_foreign_tax_credited_eur": D("0.00"),
        "kap_line_41_foreign_tax_not_credited_eur": D("0.00"),
    }
    source_files: set[str] = set()
    seen_fields: dict[str, str] = {}
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = str(row.get("key", "")).strip()
            if key not in BANK_CERTIFICATE_FIELD_ALIASES:
                value_text = str(row.get("value", "0.00") or "0.00").strip()
                try:
                    value = D(value_text)
                except (InvalidOperation, ValueError) as exc:
                    # ``Decimal(...)`` raises ``InvalidOperation`` for malformed
                    # numeric strings; ``ValueError`` covers the path where a
                    # caller passed a non-string we cannot parse. Anything else
                    # (e.g., MemoryError, KeyboardInterrupt) is a real failure
                    # and must propagate — the previous bare ``except Exception``
                    # masked those, conflating "user CSV typo" with "engine bug".
                    raise ValueError(f"Unsupported bank certificate key: {key}") from exc
                if value != D("0.00"):
                    # § 20/§ 32d/§ 36 certificate facts are typed legal inputs. Unknown
                    # nonzero rows must not be silently ignored because that can drop a
                    # withholding credit, foreign-tax credit, or taxable capital amount.
                    raise ValueError(f"Unsupported bank certificate key with nonzero value: {key}")
                continue
            field_name = BANK_CERTIFICATE_FIELD_ALIASES[key]
            if field_name in seen_fields:
                # Each typed Anlage KAP certificate field must be exact-one. Accepting
                # multiple aliases would make the last CSV row replace a legal fact.
                raise ValueError(
                    f"Duplicate bank certificate field {field_name}: {seen_fields[field_name]} and {key}"
                )
            values[field_name] = D(str(row.get("value", "0.00") or "0.00"))
            seen_fields[field_name] = key
            source_file = str(row.get("source", "")).strip()
            if source_file:
                source_files.add(source_file)
    if not any(amount != D("0.00") for amount in values.values()):
        return ()
    owner_slot = "person_2"
    if owner_slot not in available_slots:
        # § 36 Abs. 2 Nr. 2 EStG credits certificate withholding to the owner of
        # the certificate. Nonzero legacy person_2 certificate rows must fail
        # closed if the profile has no second Germany person.
        raise ValueError("person_2 bank certificate facts require a second Germany person slot.")
    return (
        GermanyBankCapitalCertificate2025(
            owner_slot=owner_slot,
            certificate_id="person_2_bank_certificate_1",
            source_file="; ".join(sorted(source_files)) or source.name,
            **values,
        ),
    )


def load_us_treaty_dividend_items_2025(
    path: Path | None = None,
) -> tuple[GermanyTreatyDividendItem2025, ...]:
    source = path or _de_us_treaty_dividends_csv()
    if not source.exists():
        return ()
    items: list[GermanyTreatyDividendItem2025] = []
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not str(row.get("item_id", "")).strip():
                continue
            items.append(
                GermanyTreatyDividendItem2025(
                    item_id=str(row["item_id"]).strip(),
                    owner_slot=str(row.get("owner_slot", "")).strip(),
                    gross_dividend_eur=D(row["gross_dividend_eur"]),
                    german_taxable_dividend_eur=D(row["german_taxable_dividend_eur"]),
                    allocated_us_tax_paid_eur=D(row["allocated_us_tax_paid_eur"]),
                    # DBA-USA Art. 10(2)(b): the source state's tax on portfolio
                    # dividends paid to a resident of the other state may not
                    # exceed 15 % of the gross dividend. The named constant in
                    # tax_pipeline.y2025.treaty_law is the single canonical
                    # declaration of that rate; never re-type "0.15" here.
                    # Authority: https://www.irs.gov/pub/irs-trty/germany.pdf
                    treaty_rate=(
                        D(row["treaty_rate"])
                        if row.get("treaty_rate")
                        else DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE
                    ),
                    dividend_class=str(row.get("dividend_class", "portfolio_dividend") or "portfolio_dividend").strip(),
                )
            )
    return tuple(items)


def load_vorabpauschale_inputs_2025(
    path: Path | None = None,
) -> tuple[GermanyVorabpauschaleInput2025, ...]:
    """Load per-fund Vorabpauschale (InvStG § 18 / § 19) raw inputs.

    Workspace CSV schema (``de-vorabpauschale-inputs-2025.csv``):

    - ``symbol`` — ticker / ISIN (matches fund_classification taxonomy).
    - ``nav_start_eur`` — NAV at the first valuation of the calendar year.
    - ``nav_end_eur`` — NAV at the last valuation of the calendar year.
    - ``ausschuettung_eur`` — actual distributions paid during the year.
    - ``months_held`` — full months of ownership during the calendar year
      (integer 0..12; pro-ration per InvStG § 18 Abs. 2).

    Empty file (header only) is the supported zero-Vorabpauschale path:
    workspaces with no accumulating funds in scope continue to produce
    Vorabpauschale = 0.00 EUR.
    https://www.gesetze-im-internet.de/invstg_2018/__18.html
    https://www.gesetze-im-internet.de/invstg_2018/__19.html
    """
    source = path or _de_vorabpauschale_inputs_csv()
    if not source.exists():
        return ()
    items: list[GermanyVorabpauschaleInput2025] = []
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            items.append(
                GermanyVorabpauschaleInput2025(
                    symbol=symbol,
                    nav_start_eur=D(row["nav_start_eur"]),
                    nav_end_eur=D(row["nav_end_eur"]),
                    ausschuettung_eur=D(row["ausschuettung_eur"]),
                    months_held=int(row["months_held"]),
                )
            )
    return tuple(items)
