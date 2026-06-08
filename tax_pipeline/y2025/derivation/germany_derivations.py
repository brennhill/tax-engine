"""German Pipeline 1 (Derivation) stages for the 2025 tax year.

Pipeline 1 contract per ``docs/invariant-migration-plan.md`` §1.5:
deterministic, typed transformations of raw broker / 1099 / bank
certificate / fund-classification inputs into canonical derived facts.
NO legal interpretation lives here — that stays in the existing
DE25-* stages (Pipeline 2). Stage IDs are prefixed ``DERIVE-DE25-``.

WS-5A registers the five DE25-13 derivation extractions (per-symbol
sale aggregation, 1099 box filtering, per-symbol bank-certificate
buckets, source-country classification, foreign-tax indexing) so the
DE25-13 (Pipeline 2) calculate body shrinks to legal § 20 EStG bucket
assembly only. WS-5B will register
``DERIVE-DE25-FUND-CLASSIFICATION`` alongside.

Authority context: cost-basis aggregation per § 20 Abs. 4 EStG,
1099 reporting taxonomy per 26 U.S.C. §§ 6042/6045, bank-certificate
shape per § 43a Abs. 3 EStG, source rules per DBA-USA Art. 10,
per-Posten foreign-tax credit per § 32d Abs. 5 EStG, fund taxonomy
per InvStG § 2 Abs. 6.
- https://www.gesetze-im-internet.de/estg/__20.html
- https://www.gesetze-im-internet.de/estg/__32d.html
- https://www.gesetze-im-internet.de/estg/__43a.html
- https://www.gesetze-im-internet.de/invstg_2018/__2.html
- https://www.irs.gov/pub/irs-trty/germany.pdf
- https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6042&num=0&edition=prelim
- https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6045&num=0&edition=prelim
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.stages import (
    AuditWaypoint,
    LawRule,
    LawStage,
    OutputDeclaration,
)
from tax_pipeline.fund_classification_data import merge_fund_classification
from tax_pipeline.y2025.germany_law import (
    BKGG_URL,
    Child2025,
    ESTG_20_URL,
    ESTG_31_URL,
    ESTG_32_URL,
    ESTG_32D_URL,
    ESTG_33B_URL,
    GermanyBankCapitalCertificate2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
    GermanyChildrenFacts2025,
    GermanyVorabpauschaleInput2025,
    INVSTG_2_URL,
    INVSTG_18_URL,
    INVSTG_19_URL,
    INVSTG_20_URL,
    _validated_capital_income_classification_2025,
    _validated_capital_sale_bucket_2025,
    aggregate_germany_children_facts_2025,
    fund_type_for_symbol_2025,
    q2,
)
from tax_pipeline.y2025.treaty_law import DBA_USA_ART_10_URL


DE_2025_DERIVATION_SCOPE = "DE-2025-DERIVATION"

DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID = "DERIVE-DE25-FUND-CLASSIFICATION"

# Fact-key contract for the fund-classification merge stage. Initial-fact
# names are stable so downstream callers (Pipeline 2 wiring, the
# reproducibility test) can address them by string without re-importing.
FUND_CLASSIFICATION_INPUT_REPO_CSV = "de.input.repo_fund_classification_csv"
FUND_CLASSIFICATION_INPUT_FUND_TYPES = "de.input.manual_overrides_fund_types"
FUND_CLASSIFICATION_INPUT_AKTIENFONDS = "de.input.manual_overrides_aktienfonds_list"
FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS = "de.input.manual_overrides_non_aktienfonds_list"
FUND_CLASSIFICATION_OUTPUT_KEY = "de.derived.fund_classification"


def _fund_classification_stage() -> LawStage:
    """Build the LawStage declaration for ``DERIVE-DE25-FUND-CLASSIFICATION``.

    InvStG § 2 Abs. 6 fund-type taxonomy applied to a workspace's
    universe of symbols. Pipeline 1 derivation: deterministic merge of
    the engine-shipped repo CSV with three workspace-level overrides
    (explicit map, bulk Aktienfonds list, bulk Sonstige list).
    """
    return LawStage(
        stage_id=DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID,
        country_or_scope=DE_2025_DERIVATION_SCOPE,
        legal_refs=("InvStG § 2 Abs. 6",),
        authority_urls=(INVSTG_2_URL,),
        input_fact_keys=(
            FUND_CLASSIFICATION_INPUT_REPO_CSV,
            FUND_CLASSIFICATION_INPUT_FUND_TYPES,
            FUND_CLASSIFICATION_INPUT_AKTIENFONDS,
            FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS,
        ),
        rounding_policy=(
            "Fund classification is a categorical taxonomy under InvStG "
            "§ 2 Abs. 6, not a monetary value: no quantization applies. "
            "Keys are upper-cased ASCII tickers; values are the closed "
            "set declared by FUND_TEILFREISTELLUNG_RATES_2025."
        ),
        law_order_note=(
            "Fund classification is a Pipeline 1 derivation: the merge "
            "of the engine-shipped baseline with the workspace overrides "
            "must complete before InvStG § 20 Teilfreistellung rates "
            "(applied in the Pipeline 2 capital stages) can be looked "
            "up per symbol."
        ),
        legal_formula=(
            "de.derived.fund_classification = repo_csv "
            "<- override(fund_types) <- override(non_aktienfonds='sonstige') "
            "<- override(aktienfonds='aktienfonds')"
        ),
        narrative_templates={"en": DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID},
        outputs=(
            OutputDeclaration(
                key=FUND_CLASSIFICATION_OUTPUT_KEY,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
        ),
    )


def _derive_de25_fund_classification(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Run the InvStG § 2 Abs. 6 fund-classification merge.

    Reads the four declared inputs by key, delegates to the pure
    :func:`tax_pipeline.fund_classification_data.merge_fund_classification`
    helper, returns a single derived fact mapping ticker to fund type.
    """
    repo_csv = facts[FUND_CLASSIFICATION_INPUT_REPO_CSV]
    fund_types = facts[FUND_CLASSIFICATION_INPUT_FUND_TYPES]
    non_aktienfonds = facts[FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS]
    aktienfonds = facts[FUND_CLASSIFICATION_INPUT_AKTIENFONDS]
    merged = merge_fund_classification(
        repo_csv,
        fund_types,
        non_aktienfonds,
        aktienfonds,
    )
    return {FUND_CLASSIFICATION_OUTPUT_KEY: merged}


# § 43a Abs. 3 EStG (Steuerbescheinigung shape) authority URL. Centralized
# here because the existing germany_2025_law module had not yet declared
# this constant — Pipeline 1 derivation stages cite the canonical source
# of the bank-certificate KAP Zeile 7 / 8 / 17 / 37 / 38 / 40 / 41 schema.
# https://www.gesetze-im-internet.de/estg/__43a.html
ESTG_43A_URL = "https://www.gesetze-im-internet.de/estg/__43a.html"

# 26 U.S.C. §§ 6042 (1099-DIV ordinary-dividend reporting) and 6045
# (broker-reported gross-proceeds gains) define the IRS reporting taxonomy
# that the German § 20 EStG income/sale classification rests on. Pipeline
# 1 cites the IRC granule URLs directly.
USC_6042_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6042&num=0&edition=prelim"
USC_6045_URL = "https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6045&num=0&edition=prelim"


ZERO_EUR = Decimal("0.00")


# ---------------------------------------------------------------------------
# DERIVE-DE25-13A — Per-symbol sale aggregation (§ 20 Abs. 4 EStG cost-basis
# aggregation convention). Roll up broker sale facts into per-symbol gain
# dicts plus the DHER stock-gain sidecar.
# ---------------------------------------------------------------------------
def derive_de25_13a_per_symbol_sale_aggregation(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Aggregate broker sale facts per symbol-bucket pair.

    § 20 Abs. 4 EStG specifies cost-basis aggregation per individual
    Wertpapier; this derivation stage produces the per-symbol roll-up that
    DE25-13's § 20 Abs. 1 / Abs. 2 bucket assembly consumes. The DHER
    stock-gain sidecar is added to the stock total under the synthetic
    ``__equity_comp_sidecar__`` symbol so DE25-15's § 20 Abs. 6 ordering
    can address it without losing provenance.
    https://www.gesetze-im-internet.de/estg/__20.html
    """
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...] = facts["de.capital.sale_facts"]
    dher_stock_gain: Decimal = Decimal(str(facts["de.capital.dher_stock_gain"]))

    stock_gain = ZERO_EUR
    fund_gain = ZERO_EUR
    option_gain = ZERO_EUR
    stock_symbol_gain: dict[str, Decimal] = {}
    fund_symbol_gain: dict[str, Decimal] = {}
    option_symbol_gain: dict[str, Decimal] = {}

    for fact in sale_facts:
        gain = Decimal(str(fact.gain_eur_matched))
        bucket = _validated_capital_sale_bucket_2025(fact)
        symbol = fact.symbol
        if bucket == "stock":
            stock_gain += gain
            stock_symbol_gain[symbol] = stock_symbol_gain.get(symbol, ZERO_EUR) + gain
        elif bucket == "fund_like":
            fund_gain += gain
            fund_symbol_gain[symbol] = fund_symbol_gain.get(symbol, ZERO_EUR) + gain
        elif bucket == "option":
            option_gain += gain
            option_symbol_gain[symbol] = option_symbol_gain.get(symbol, ZERO_EUR) + gain

    stock_gain += dher_stock_gain
    if dher_stock_gain:
        # The synthetic ``__equity_comp_sidecar__`` symbol keeps DHER
        # provenance addressable from DE25-15's § 20 Abs. 6 ordering.
        # ``stock_symbol_gain`` is a freshly constructed local dict (not a
        # facts lookup), so the ``.get(symbol, ZERO_EUR)`` accumulator
        # idiom here is not a silent zero-default on a declared input.
        stock_symbol_gain["__equity_comp_sidecar__"] = (
            stock_symbol_gain.get("__equity_comp_sidecar__", ZERO_EUR) + dher_stock_gain  # pragma: nzd-allow accumulator-dict idiom on local stock_symbol_gain (not a facts lookup)
        )

    return {
        "de.derived.per_symbol_sale_aggregation": {
            "stock_gain": stock_gain,
            "fund_gain": fund_gain,
            "option_gain": option_gain,
            "stock_symbol_gain": stock_symbol_gain,
            "fund_symbol_gain": fund_symbol_gain,
            "option_symbol_gain": option_symbol_gain,
            "dher_stock_gain": dher_stock_gain,
        }
    }


# ---------------------------------------------------------------------------
# DERIVE-DE25-13B — 1099-DIV box filtering / income-fact taxonomy split.
# Mirrors the IRS reporting taxonomy in 26 U.S.C. §§ 6042 / 6045: ordinary
# dividends (Box 1a-style) and substitute payments / interest land in the
# § 20 Abs. 1 EStG income totals; the foreign-tax-paid rows are split out
# into the per-Posten foreign-tax index that DE25-18 consumes through the
# § 32d Abs. 5 EStG cap. (Box-2a capital-gain distributions / Box-3
# nondividend distributions are NOT § 20 Abs. 1 income — they arrive via
# the broker sale-fact bucket handled in DERIVE-DE25-13A.)
# ---------------------------------------------------------------------------
def derive_de25_13b_1099_box_filtering(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Filter income-fact rows into § 20 Abs. 1 income vs § 32d Abs. 5 foreign tax.

    Each ``GermanyCapitalIncomeFact2025`` carries an IRS-side ``kind`` that
    maps onto a 1099-DIV / 1099-INT box: ``dividend`` and
    ``substitute_payment`` collapse to Box 1a-style ordinary-dividend
    income (26 U.S.C. § 6042); ``interest`` to 1099-INT Box 1
    (§ 6049); ``foreign_tax`` to the Box 7 foreign-tax-paid column.

    The function emits the per-Posten foreign-tax table (
    ``foreign_tax_by_item``) AND the symbol-fallback ambiguity counts so
    DERIVE-DE25-13E can surface § 32d Abs. 5 EStG fail-closed errors when
    the symbol-only fallback is ambiguous (multiple income rows or
    foreign-tax rows tied to the same symbol without an explicit
    ``foreign_tax_item_id``).
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6042&num=0&edition=prelim
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section6045&num=0&edition=prelim
    """
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...] = facts["de.capital.income_facts"]

    positive_income_total = ZERO_EUR
    non_fund_positive_income_total = ZERO_EUR
    explicit_foreign_tax_total = ZERO_EUR
    foreign_tax_by_item: dict[str, Decimal] = {}
    foreign_tax_refund_by_item: dict[str, Decimal] = {}
    fund_symbol_income: dict[str, Decimal] = {}
    income_items: list[tuple[str, str, str, Decimal]] = []
    fallback_income_count_by_symbol: dict[str, int] = {}
    fallback_tax_count_by_symbol: dict[str, int] = {}

    for fact in income_facts:
        amount = Decimal(str(fact.eur_amount))
        kind, bucket = _validated_capital_income_classification_2025(fact)
        symbol = fact.symbol
        explicit_credit_item_id = str(fact.foreign_tax_item_id or "").strip()
        credit_item_id = explicit_credit_item_id or symbol
        if kind == "foreign_tax":
            if amount < ZERO_EUR:
                raise ValueError("foreign_tax_eur_amount must be non-negative")
            if fact.refund_entitlement_eur is None:
                raise ValueError(
                    "Germany foreign_tax rows in income-cashflows.csv must include refund_entitlement_eur."
                )
            refund = Decimal(str(fact.refund_entitlement_eur))
            if refund < ZERO_EUR:
                raise ValueError("foreign_tax_refund_entitlement_eur must be non-negative")
            if not explicit_credit_item_id:
                fallback_tax_count_by_symbol[symbol] = (
                    fallback_tax_count_by_symbol.get(symbol, 0) + 1  # pragma: nzd-allow accumulator-dict idiom on local fallback_tax_count_by_symbol (not a facts lookup)
                )
            explicit_foreign_tax_total += amount
            foreign_tax_by_item[credit_item_id] = (
                foreign_tax_by_item.get(credit_item_id, ZERO_EUR) + amount  # pragma: nzd-allow accumulator-dict idiom on local foreign_tax_by_item (not a facts lookup)
            )
            foreign_tax_refund_by_item[credit_item_id] = (
                foreign_tax_refund_by_item.get(credit_item_id, ZERO_EUR) + refund  # pragma: nzd-allow accumulator-dict idiom on local foreign_tax_refund_by_item (not a facts lookup)
            )
            continue
        if amount < ZERO_EUR:
            raise ValueError(f"{kind}_eur_amount must be non-negative")
        positive_income_total += amount
        if not explicit_credit_item_id:
            fallback_income_count_by_symbol[symbol] = (
                fallback_income_count_by_symbol.get(symbol, 0) + 1  # pragma: nzd-allow accumulator-dict idiom on local fallback_income_count_by_symbol (not a facts lookup)
            )
        income_items.append((credit_item_id, symbol, bucket, amount))
        if bucket == "fund_like":
            fund_symbol_income[symbol] = (
                fund_symbol_income.get(symbol, ZERO_EUR) + amount  # pragma: nzd-allow accumulator-dict idiom on local fund_symbol_income (not a facts lookup)
            )
        else:
            non_fund_positive_income_total += amount

    return {
        "de.derived.box_1a_filtered_dividends": {
            "positive_income_total": positive_income_total,
            "non_fund_positive_income_total": non_fund_positive_income_total,
            "explicit_foreign_tax_total": explicit_foreign_tax_total,
            "foreign_tax_by_item": foreign_tax_by_item,
            "foreign_tax_refund_by_item": foreign_tax_refund_by_item,
            "fund_symbol_income": fund_symbol_income,
            "income_items": tuple(income_items),
            "fallback_income_count_by_symbol": fallback_income_count_by_symbol,
            "fallback_tax_count_by_symbol": fallback_tax_count_by_symbol,
        }
    }


def _de25_13b_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13B."""
    return LawStage(
        stage_id="DERIVE-DE25-13B-1099-BOX-FILTERING",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("26 U.S.C. § 6042", "26 U.S.C. § 6045"),
        authority_urls=(USC_6042_URL, USC_6045_URL),
        input_fact_keys=("de.capital.income_facts",),
        rounding_policy=(
            "Per-row dividend / foreign-tax amounts retain cent-level "
            "Decimal precision; no monetary rounding pre-§ 20 Abs. 1 EStG "
            "aggregation."
        ),
        law_order_note=(
            "1099 box taxonomy split runs before § 20 Abs. 1 / § 32d Abs. 5 "
            "EStG totals so the legal stages consume a typed dividend / "
            "foreign-tax index."
        ),
        legal_formula=(
            "de.derived.box_1a_filtered_dividends := partition(income_facts) by "
            "kind into (positive § 20 Abs. 1 income items, foreign-tax rows "
            "indexed by item id, symbol-fallback ambiguity counts) per "
            "26 U.S.C. § 6042 (1099-DIV) / § 6045 (1099-B) reporting taxonomy"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13B-1099-BOX-FILTERING",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.box_1a_filtered_dividends",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# DERIVE-DE25-13C — Per-symbol bank-certificate aggregation. § 43a Abs. 3
# EStG defines the Steuerbescheinigung shape: KAP Zeile 7 carries the total
# capital income, Zeile 8 the stock-sale subset already inside Zeile 7,
# Zeile 17 the saver-allowance used at source, Zeile 37/38 the domestic
# KESt and SolZ withholding, and Zeile 40/41 the foreign-tax credited /
# not-credited columns. This stage rolls the per-certificate values up
# into the index DE25-13 currently builds inline.
# ---------------------------------------------------------------------------
def derive_de25_13c_per_symbol_bank_certificate_buckets(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Aggregate bank-certificate rows into per-Posten / summary indexes.

    § 43a Abs. 3 EStG fixes the Steuerbescheinigung structure that the
    German bank certificates follow. This stage produces:
    - per-certificate stock-subset and non-stock-income amounts keyed
      by the synthetic ``__bank_certificate_*__:<id>`` symbols;
    - per-certificate foreign-tax-paid totals (credited + not credited)
      keyed by ``__bank_certificate_foreign_tax__:<id>``;
    - the foreign-taxable base used by the § 32d Abs. 5 EStG cap;
    - the headline summary dict (income / stock_gain / non_stock_income
      / saver_allowance_used / foreign_tax_credited /
      foreign_tax_not_credited);
    - the domestic KESt + SolZ withholding totals consumed downstream
      by DE25-21's final-capital-tax computation.
    https://www.gesetze-im-internet.de/estg/__43a.html
    """
    bank_certificates: tuple[GermanyBankCapitalCertificate2025, ...] = facts[
        "de.capital.bank_certificates"
    ]

    bank_certificate_income = ZERO_EUR
    bank_certificate_stock_gain = ZERO_EUR
    bank_certificate_non_stock_income = ZERO_EUR
    bank_certificate_saver_allowance_used = ZERO_EUR
    bank_certificate_foreign_tax_credited = ZERO_EUR
    bank_certificate_foreign_tax_not_credited = ZERO_EUR
    domestic_capital_tax_withheld = ZERO_EUR
    domestic_capital_soli_withheld = ZERO_EUR
    bank_certificate_non_stock_by_symbol: dict[str, Decimal] = {}
    bank_certificate_foreign_taxable_by_item: dict[str, Decimal] = {}
    stock_subset_by_certificate: dict[str, Decimal] = {}
    foreign_tax_by_certificate: dict[str, Decimal] = {}

    for certificate in bank_certificates:
        certificate_id = str(certificate.certificate_id).strip()
        stock_subset = q2(certificate.kap_line_8_stock_gains_eur)
        non_stock_income = q2(
            certificate.kap_line_7_income_eur
            - certificate.kap_line_8_stock_gains_eur
        )
        foreign_tax = q2(
            certificate.kap_line_40_foreign_tax_credited_eur
            + certificate.kap_line_41_foreign_tax_not_credited_eur
        )
        stock_symbol = f"__bank_certificate_stock__:{certificate_id}"
        non_stock_symbol = f"__bank_certificate_non_stock__:{certificate_id}"
        credit_item_id = f"__bank_certificate_foreign_tax__:{certificate_id}"

        # § 20 EStG bank-certificate Zeile 7 is the capital-income amount;
        # Zeile 8 is the stock-sale subset already inside Zeile 7. The
        # split into a restricted-stock bucket plus non-stock remainder is
        # what makes § 20 Abs. 6 ordering treat the two correctly.
        stock_subset_by_certificate[stock_symbol] = (
            stock_subset_by_certificate.get(stock_symbol, ZERO_EUR) + stock_subset  # pragma: nzd-allow accumulator-dict idiom on local stock_subset_by_certificate (not a facts lookup)
        )
        bank_certificate_non_stock_by_symbol[non_stock_symbol] = (
            bank_certificate_non_stock_by_symbol.get(non_stock_symbol, ZERO_EUR)
            + non_stock_income  # pragma: nzd-allow accumulator-dict idiom on local bank_certificate_non_stock_by_symbol (not a facts lookup)
        )
        bank_certificate_foreign_taxable_by_item[credit_item_id] = (
            bank_certificate_foreign_taxable_by_item.get(credit_item_id, ZERO_EUR)
            + certificate.kap_line_7_income_eur  # pragma: nzd-allow accumulator-dict idiom on local bank_certificate_foreign_taxable_by_item (not a facts lookup)
        )
        if foreign_tax:
            foreign_tax_by_certificate[credit_item_id] = (
                foreign_tax_by_certificate.get(credit_item_id, ZERO_EUR) + foreign_tax  # pragma: nzd-allow accumulator-dict idiom on local foreign_tax_by_certificate (not a facts lookup)
            )

        bank_certificate_income += certificate.kap_line_7_income_eur
        bank_certificate_stock_gain += stock_subset
        bank_certificate_non_stock_income += non_stock_income
        bank_certificate_saver_allowance_used += (
            certificate.kap_line_17_saver_allowance_used_eur
        )
        bank_certificate_foreign_tax_credited += (
            certificate.kap_line_40_foreign_tax_credited_eur
        )
        bank_certificate_foreign_tax_not_credited += (
            certificate.kap_line_41_foreign_tax_not_credited_eur
        )
        domestic_capital_tax_withheld += certificate.kap_line_37_kest_withheld_eur
        domestic_capital_soli_withheld += certificate.kap_line_38_soli_withheld_eur

    return {
        "de.derived.per_symbol_bank_certificate_buckets": {
            "bank_certificate_summary": {
                "income": bank_certificate_income,
                "stock_gain": bank_certificate_stock_gain,
                "non_stock_income": bank_certificate_non_stock_income,
                "saver_allowance_used": bank_certificate_saver_allowance_used,
                "foreign_tax_credited": bank_certificate_foreign_tax_credited,
                "foreign_tax_not_credited": bank_certificate_foreign_tax_not_credited,
            },
            "domestic_capital_tax_withheld": domestic_capital_tax_withheld,
            "domestic_capital_soli_withheld": domestic_capital_soli_withheld,
            "bank_certificate_non_stock_by_symbol": bank_certificate_non_stock_by_symbol,
            "bank_certificate_foreign_taxable_by_item": (
                bank_certificate_foreign_taxable_by_item
            ),
            "stock_subset_by_certificate": stock_subset_by_certificate,
            "foreign_tax_by_certificate": foreign_tax_by_certificate,
        }
    }


def _de25_13c_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13C."""
    return LawStage(
        stage_id="DERIVE-DE25-13C-PER-SYMBOL-BANK-CERTIFICATE-BUCKETS",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("§ 43a Abs. 3 EStG",),
        authority_urls=(ESTG_43A_URL,),
        input_fact_keys=("de.capital.bank_certificates",),
        rounding_policy=(
            "Per-certificate stock-subset and non-stock-income are q2 to "
            "match § 43a Abs. 3 Steuerbescheinigung cent precision; running "
            "totals stay at full Decimal precision for the legal stage."
        ),
        law_order_note=(
            "Bank-certificate aggregation runs before § 20 Abs. 1 / Abs. 2 "
            "EStG bucket assembly so DE25-13 consumes a pre-split index."
        ),
        legal_formula=(
            "de.derived.per_symbol_bank_certificate_buckets := for each "
            "certificate, q2(kap_line_8) -> stock_subset / "
            "q2(kap_line_7 - kap_line_8) -> non_stock_income / "
            "q2(kap_line_40 + kap_line_41) -> foreign_tax; aggregate per "
            "synthetic __bank_certificate_*__:<id> symbol per § 43a Abs. 3 "
            "EStG"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13C-PER-SYMBOL-BANK-CERTIFICATE-BUCKETS",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.per_symbol_bank_certificate_buckets",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# DERIVE-DE25-13D — Source-country classification of fund symbols. DBA-USA
# Art. 10 governs source-state taxation for portfolio dividends; the
# equity / non-equity fund-type axis (also documented in InvStG § 20) is
# the source-relevance step that drives the partial-exemption rate
# applied in DE25-14 and the per-Posten foreign-tax indexing in DE25-18.
# ---------------------------------------------------------------------------
def derive_de25_13d_source_country_classification(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Partition fund symbols into equity vs. non-equity buckets.

    DBA-USA Art. 10 / InvStG § 20: the partial-exemption rate that
    applies to a fund distribution depends on whether the fund is an
    Aktienfonds (equity) or one of the other categories. This stage
    cross-references the per-symbol fund / income aggregates from
    DERIVE-DE25-13A and DERIVE-DE25-13B against
    ``de.capital.fund_classification`` and emits the typed
    classification index DE25-13 currently builds inline.
    https://www.irs.gov/pub/irs-trty/germany.pdf
    https://www.gesetze-im-internet.de/invstg_2018/__20.html
    """
    sale_aggregation = facts["de.derived.per_symbol_sale_aggregation"]
    box_filtered = facts["de.derived.box_1a_filtered_dividends"]
    fund_classification: dict[str, str] = facts["de.capital.fund_classification"]

    fund_symbol_gain: dict[str, Decimal] = sale_aggregation["fund_symbol_gain"]
    fund_symbol_income: dict[str, Decimal] = box_filtered["fund_symbol_income"]
    # Sort the symbol union so downstream Decimal accumulation is order-stable.
    # `set | set` is hash-randomized and the unrounded fund-symbol gains carry
    # ~25-digit Decimal tails; summing them in hash order produced different
    # last-digit precision tails between runs, drifting the rule-graph
    # fingerprint without changing q2-rounded headline numbers. Sorting the
    # symbol list (and rebuilding fund_types in that order) makes
    # equity_fund_total / non_equity_fund_total byte-stable across runs and
    # restores `final-legal-output.json` byte-identity (P1 audit follow-up to
    # a pre-existing audit-graph defect introduced in 81d01e8).
    fund_symbols_sorted = sorted(set(fund_symbol_gain) | set(fund_symbol_income))
    fund_symbols = frozenset(fund_symbols_sorted)
    fund_types = {
        symbol: fund_type_for_symbol_2025(symbol, fund_classification)
        for symbol in fund_symbols_sorted
    }
    equity_fund_symbols = [
        symbol
        for symbol in fund_symbols_sorted
        if fund_types[symbol] in {"aktienfonds", "equity"}
    ]
    equity_fund_total = sum(
        (
            fund_symbol_gain.get(sym, ZERO_EUR) + fund_symbol_income.get(sym, ZERO_EUR)
            for sym in equity_fund_symbols
        ),
        ZERO_EUR,
    )
    non_equity_fund_total = sum(
        (
            fund_symbol_gain.get(sym, ZERO_EUR) + fund_symbol_income.get(sym, ZERO_EUR)
            for sym in fund_symbols_sorted
            if fund_types[sym] not in {"aktienfonds", "equity"}
        ),
        ZERO_EUR,
    )

    return {
        "de.derived.source_country_classification": {
            "fund_symbols": frozenset(fund_symbols),
            "fund_types": fund_types,
            "equity_fund_total": equity_fund_total,
            "non_equity_fund_total": non_equity_fund_total,
        }
    }


def _de25_13d_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13D."""
    return LawStage(
        stage_id="DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("DBA-USA Art. 10", "InvStG § 20"),
        authority_urls=(DBA_USA_ART_10_URL, INVSTG_20_URL),
        input_fact_keys=(
            "de.derived.per_symbol_sale_aggregation",
            "de.derived.box_1a_filtered_dividends",
            "de.capital.fund_classification",
        ),
        rounding_policy=(
            "Equity / non-equity fund totals stay at full Decimal precision; "
            "rounding happens at the legal-stage boundary (DE25-14 partial "
            "exemption)."
        ),
        law_order_note=(
            "Source classification runs after DERIVE-DE25-13A / 13B (which "
            "produce the per-symbol fund gain / income indexes) and before "
            "DE25-14's InvStG § 20 partial-exemption application."
        ),
        legal_formula=(
            "de.derived.source_country_classification := classify(fund_symbols) "
            "via fund_type_for_symbol_2025; equity_fund_total = "
            "sum(fund_symbol_gain + fund_symbol_income for symbols typed "
            "aktienfonds/equity); non_equity_fund_total = sum for the "
            "complement per DBA-USA Art. 10 / InvStG § 20"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.source_country_classification",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# DERIVE-DE25-13E — Per-Posten foreign-tax indexing. § 32d Abs. 5 EStG
# caps the foreign-tax credit per individual taxable item / source. This
# stage combines the income-fact foreign-tax index (DE25-13B) with the
# bank-certificate foreign-tax index (DE25-13C) into a single per-Posten
# table the legal stages consume, AND validates that any symbol-only
# fallback is unambiguous (the legal precondition under § 32d Abs. 5 —
# multiple income rows or foreign-tax rows tied to the same symbol
# without an explicit ``foreign_tax_item_id`` would silently merge two
# distinct taxable items into one credit cap, defeating the per-Posten
# rule).
# ---------------------------------------------------------------------------
def derive_de25_13e_foreign_tax_indexing(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Assemble the per-Posten foreign-tax table consumed by DE25-18.

    § 32d Abs. 5 EStG caps the foreign tax per individual taxable item.
    The fail-closed precondition is that every foreign-tax row must
    map unambiguously to one taxable item; symbol-only fallback is
    permitted only when one income row and one foreign-tax row share
    the same symbol. The check is run here at the Pipeline 1 boundary
    so DE25-18 can rely on a clean per-Posten table.
    https://www.gesetze-im-internet.de/estg/__32d.html
    """
    box_filtered = facts["de.derived.box_1a_filtered_dividends"]
    bank_certificate = facts["de.derived.per_symbol_bank_certificate_buckets"]

    fallback_income_count_by_symbol: dict[str, int] = box_filtered[
        "fallback_income_count_by_symbol"
    ]
    fallback_tax_count_by_symbol: dict[str, int] = box_filtered[
        "fallback_tax_count_by_symbol"
    ]
    ambiguous_foreign_tax_symbols = sorted(
        symbol
        for symbol, tax_count in fallback_tax_count_by_symbol.items()
        if tax_count != 1 or fallback_income_count_by_symbol.get(symbol, 0) != 1
    )
    if ambiguous_foreign_tax_symbols:
        # § 32d Abs. 5 EStG caps foreign tax per individual taxable
        # item/source. Symbol-only fallback is legally safe only when
        # one taxable item maps to one foreign-tax row.
        raise ValueError(
            "Germany foreign_tax rows require foreign_tax_item_id when "
            "symbol fallback is ambiguous for § 32d(5): "
            + ", ".join(ambiguous_foreign_tax_symbols)
        )

    # Combine the income-fact foreign-tax index with the bank-certificate
    # foreign-tax index. Both pre-keyed by their canonical credit_item_id
    # convention (explicit item-id or fallback symbol for income facts;
    # ``__bank_certificate_foreign_tax__:<id>`` for bank certificates), so
    # the merge is a simple key-disjoint union — accumulate to defend
    # against future overlaps.
    income_foreign_tax_by_item: dict[str, Decimal] = box_filtered["foreign_tax_by_item"]
    income_foreign_tax_refund_by_item: dict[str, Decimal] = box_filtered[
        "foreign_tax_refund_by_item"
    ]
    cert_foreign_tax_by_item: dict[str, Decimal] = bank_certificate[
        "foreign_tax_by_certificate"
    ]

    foreign_tax_by_item: dict[str, Decimal] = {}
    for key, value in income_foreign_tax_by_item.items():
        foreign_tax_by_item[key] = (
            foreign_tax_by_item.get(key, ZERO_EUR) + value  # pragma: nzd-allow accumulator-dict idiom on local foreign_tax_by_item (not a facts lookup)
        )
    for key, value in cert_foreign_tax_by_item.items():
        foreign_tax_by_item[key] = (
            foreign_tax_by_item.get(key, ZERO_EUR) + value  # pragma: nzd-allow accumulator-dict idiom on local foreign_tax_by_item (not a facts lookup)
        )

    # The refund-entitlement index covers income-fact rows; bank-certificate
    # rows have no refund-entitlement field per § 43a Abs. 3 EStG, so DE25-13
    # historically defaulted them to ZERO via ``.get(..., ZERO_EUR)`` only
    # when the cert had nonzero foreign tax. Mirror that behavior here.
    foreign_tax_refund_by_item: dict[str, Decimal] = dict(income_foreign_tax_refund_by_item)
    for key in cert_foreign_tax_by_item:
        if key not in foreign_tax_refund_by_item:
            foreign_tax_refund_by_item[key] = ZERO_EUR

    # DE25-13's inline math summed q2(line_40 + line_41) per certificate
    # into the running ``explicit_foreign_tax_total``. ``cert_foreign_tax_by_item``
    # already carries the per-cert q2 values, so summing them here
    # preserves the legacy ``sum(q2(...))`` ordering (which can differ
    # from ``q2(sum(...))`` at sub-cent residues).
    explicit_foreign_tax_total = (
        box_filtered["explicit_foreign_tax_total"]
        + sum(cert_foreign_tax_by_item.values(), ZERO_EUR)
    )

    return {
        "de.derived.foreign_tax_indexing": {
            "foreign_tax_by_item": foreign_tax_by_item,
            "foreign_tax_refund_by_item": foreign_tax_refund_by_item,
            "explicit_foreign_tax_total": explicit_foreign_tax_total,
            "bank_certificate_foreign_taxable_by_item": (
                bank_certificate["bank_certificate_foreign_taxable_by_item"]
            ),
        }
    }


def _de25_13e_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13E."""
    return LawStage(
        stage_id="DERIVE-DE25-13E-FOREIGN-TAX-INDEXING",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("§ 32d Abs. 5 EStG",),
        authority_urls=(ESTG_32D_URL,),
        input_fact_keys=(
            "de.derived.box_1a_filtered_dividends",
            "de.derived.per_symbol_bank_certificate_buckets",
        ),
        rounding_policy=(
            "Per-Posten foreign tax stays at full Decimal precision; "
            "bank-certificate aggregate foreign tax is q2 to match § 43a "
            "Abs. 3 Steuerbescheinigung cent precision."
        ),
        law_order_note=(
            "Foreign-tax indexing runs after DERIVE-DE25-13B and "
            "DERIVE-DE25-13C and validates the symbol-fallback ambiguity "
            "rule before DE25-18's § 32d Abs. 5 EStG per-Posten cap."
        ),
        legal_formula=(
            "de.derived.foreign_tax_indexing := merge("
            "box_1a_filtered_dividends.foreign_tax_by_item, "
            "per_symbol_bank_certificate_buckets.foreign_tax_by_certificate"
            ") with fail-closed validation that no symbol fallback is "
            "ambiguous per § 32d Abs. 5 EStG"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13E-FOREIGN-TAX-INDEXING",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.foreign_tax_indexing",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


def _de25_13a_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13A."""
    return LawStage(
        stage_id="DERIVE-DE25-13A-PER-SYMBOL-SALE-AGGREGATION",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("§ 20 Abs. 4 EStG",),
        authority_urls=(ESTG_20_URL,),
        input_fact_keys=(
            "de.capital.sale_facts",
            "de.capital.dher_stock_gain",
        ),
        rounding_policy=(
            "Per-symbol sale gains stay at cent-level Decimal precision; "
            "no monetary rounding per § 20 Abs. 4 EStG cost-basis aggregation."
        ),
        law_order_note=(
            "Per-symbol roll-up runs before § 20 Abs. 1 / Abs. 2 bucket "
            "assembly (DE25-13) so the legal stage consumes a typed index."
        ),
        legal_formula=(
            "de.derived.per_symbol_sale_aggregation := group(sale_facts) by "
            "(asset_bucket, symbol) -> stock/fund/option gain dicts; add "
            "dher_stock_gain into stock total under __equity_comp_sidecar__"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13A-PER-SYMBOL-SALE-AGGREGATION",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.per_symbol_sale_aggregation",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# DERIVE-DE25-13F — Per-fund Vorabpauschale (deemed-distribution) inputs.
# InvStG § 19 governs the deemed-distribution mechanism for accumulating
# (thesaurierende) funds; § 18 fixes the Basisertrag formula
# (NAV_start × 0.7 × Basiszinssatz × months_held / 12); § 16 Abs. 1 Nr. 2
# caps the resulting Vorabpauschale at the year's actual NAV gain.
# This stage materializes the per-fund raw inputs that the Pipeline 2 legal
# stage DE25-13F-VORABPAUSCHALE consumes; no legal arithmetic happens here.
# ---------------------------------------------------------------------------
def derive_de25_13f_vorabpauschale_inputs(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Project the per-fund Vorabpauschale raw inputs into a typed index.

    InvStG § 18 Abs. 1 / § 19 Abs. 1: the deemed-distribution surface is
    one row per accumulating fund the taxpayer held during the calendar
    year. The raw inputs (NAV start/end, year's distribution, months held)
    are workspace-supplied via ``de-vorabpauschale-inputs-2025.csv`` so
    this derivation is a pure index re-shape, not a legal calculation.

    Output shape::

        {
            "de.derived.vorabpauschale_inputs": {
                "<symbol>": {
                    "nav_start_eur": Decimal,
                    "nav_end_eur": Decimal,
                    "ausschuettung_eur": Decimal,
                    "months_held": int,
                },
                ...
            }
        }

    https://www.gesetze-im-internet.de/invstg_2018/__18.html
    https://www.gesetze-im-internet.de/invstg_2018/__19.html
    """
    inputs: tuple[GermanyVorabpauschaleInput2025, ...] = facts[
        "de.capital.vorabpauschale_inputs"
    ]

    by_symbol: dict[str, dict[str, Any]] = {}
    for row in inputs:
        symbol = str(row.symbol).strip().upper()
        if not symbol:
            # InvStG § 19 Vorabpauschale is per-fund. A blank symbol cannot be
            # routed through the Teilfreistellung lookup (InvStG § 20) so fail
            # closed rather than silently aggregating across funds.
            raise ValueError(
                "Vorabpauschale input row missing symbol; required for "
                "InvStG § 20 Teilfreistellung routing."
            )
        if symbol in by_symbol:
            raise ValueError(
                f"Duplicate Vorabpauschale input row for symbol {symbol!r}; "
                "InvStG § 19 deemed-distribution must be exact-one per fund."
            )
        nav_start = Decimal(str(row.nav_start_eur))
        nav_end = Decimal(str(row.nav_end_eur))
        ausschuettung = Decimal(str(row.ausschuettung_eur))
        months_held = int(row.months_held)
        if nav_start < ZERO_EUR or nav_end < ZERO_EUR:
            raise ValueError(
                f"Vorabpauschale NAV values must be non-negative for {symbol!r}."
            )
        if ausschuettung < ZERO_EUR:
            raise ValueError(
                f"Vorabpauschale Ausschuettung must be non-negative for {symbol!r}."
            )
        if months_held < 0 or months_held > 12:
            raise ValueError(
                f"Vorabpauschale months_held must be in [0, 12] for {symbol!r}."
            )
        by_symbol[symbol] = {
            "nav_start_eur": q2(nav_start),
            "nav_end_eur": q2(nav_end),
            "ausschuettung_eur": q2(ausschuettung),
            "months_held": months_held,
        }
    # Sort the dict by symbol so iteration order is deterministic across
    # runs — downstream fingerprints and final-output JSON must be byte-stable.
    sorted_by_symbol = {symbol: by_symbol[symbol] for symbol in sorted(by_symbol)}
    return {"de.derived.vorabpauschale_inputs": sorted_by_symbol}


def _de25_13f_stage() -> LawStage:
    """LawStage declaration for DERIVE-DE25-13F-VORABPAUSCHALE-INPUTS."""
    return LawStage(
        stage_id="DERIVE-DE25-13F-VORABPAUSCHALE-INPUTS",
        country_or_scope="DE-2025-DERIVATION",
        legal_refs=("InvStG § 18", "InvStG § 19"),
        authority_urls=(INVSTG_18_URL, INVSTG_19_URL),
        input_fact_keys=("de.capital.vorabpauschale_inputs",),
        rounding_policy=(
            "NAV / Ausschuettung amounts are q2-quantized at cent precision; "
            "months_held is the exact integer count from the workspace CSV. "
            "Statutory rounding (InvStG § 18) is applied in Pipeline 2."
        ),
        law_order_note=(
            "Per-fund Vorabpauschale input derivation runs before the "
            "Pipeline 2 legal stage DE25-13F-VORABPAUSCHALE so the legal "
            "stage consumes a typed per-symbol index."
        ),
        legal_formula=(
            "de.derived.vorabpauschale_inputs := index(workspace_rows) by "
            "symbol -> {nav_start_eur, nav_end_eur, ausschuettung_eur, "
            "months_held} per InvStG § 18 Abs. 1 / § 19 Abs. 1"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-13F-VORABPAUSCHALE-INPUTS",
        },
        outputs=(
            OutputDeclaration(
                key="de.derived.vorabpauschale_inputs",
                audit_waypoints=frozenset({AuditWaypoint.PER_POSTEN_AGGREGATION}),
            ),
        ),
    )


DERIVE_DE25_CHILDREN_STAGE_ID = "DERIVE-DE25-CHILDREN"

# Initial-fact keys for the children Pipeline 1 derivation. The raw
# children tuple is supplied by the inputs loader; the filing posture
# is required to apply the § 32 Abs. 6 Satz 1/2 EStG split-vs-combined
# Freibetrag rule.
CHILDREN_INPUT_RAW_KEY = "de.input.children_raw"
CHILDREN_INPUT_FILING_POSTURE_KEY = "de.input.children_filing_posture"
# § 33b Abs. 5 EStG transferral election. Profile-level boolean read
# from ``elections.germany_disability_pauschbetrag_transfer``. The
# loader fails closed when any child has ``disability_gdb > 0`` and
# the election is missing — the engine refuses to silently skip a
# §-33b-Abs.-5-EStG transferral the household may be entitled to.
CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY = (
    "de.input.children_disability_pauschbetrag_transfer_election"
)

# Output fact keys feeding Pipeline 2's DE25-CHILDREN-CREDITS stage.
CHILDREN_OUTPUT_PRESENT = "de.derived.children_present"
CHILDREN_OUTPUT_COUNT = "de.derived.children_count"
CHILDREN_OUTPUT_KINDERFREIBETRAG_TOTAL = (
    "de.derived.kinderfreibetrag_total_eur"
)
CHILDREN_OUTPUT_KINDERGELD_TOTAL = (
    "de.derived.kindergeld_received_total_eur"
)
# § 33b Abs. 5 EStG transferral total — sum across qualifying children
# of the per-child §-33b-Abs.-3-EStG Pauschbetrag, gated on the profile
# election. Consumed by:
#   - Pipeline 2 ordinary stage ``DE25-BEHINDERUNG-PAUSCHBETRAG``
#     (extends the household total so the transferral flows naturally
#     through DE25-07 zvE → DE25-08 tariff).
#   - Pipeline 2 children sub-graph audit stage
#     ``DE25-CHILDREN-DISABILITY-PAUSCHBETRAG`` (re-emits for audit).
CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL = (
    "de.derived.children_disability_pauschbetrag_total_eur"
)
# Surfaced election value — exposed as a derived fact so the Pipeline
# 2 children sub-graph can declare it as an input_fact_key (per
# invariant I7) without re-reading the profile inside Pipeline 2.
CHILDREN_OUTPUT_DISABILITY_TRANSFER_ELECTION = (
    "de.derived.children_disability_pauschbetrag_transfer_election"
)
CHILDREN_OUTPUT_FACTS = "de.derived.children_facts"


def derive_de25_children(
    facts: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Pipeline 1 derivation for § 31 EStG Familienleistungsausgleich.

    Reads the typed ``Child2025`` tuple from the workspace
    ``config/children.csv`` (loaded in ``germany_2025_inputs.py``) and
    aggregates per-child Kinderfreibetrag and Kindergeld into household
    totals. ``children_present`` is ``False`` when no qualifying child
    is declared so the Pipeline 2 stage
    ``DE25-CHILDREN-CREDITS`` short-circuits
    to pass-through behaviour and demo workspaces without children
    keep producing identical numerics.

    Gap 2 (§ 33b Abs. 5 EStG transferral): the per-child
    Behinderten-Pauschbetrag is summed into
    ``de.derived.children_disability_pauschbetrag_total_eur`` only when
    the profile-level election
    ``elections.germany_disability_pauschbetrag_transfer`` is true. The
    derivation fails closed when any qualifying child has
    ``disability_gdb > 0`` (or ``disability_helpless_or_blind``) and the
    election is unset — the engine refuses to silently forfeit a
    transferral the parents may be entitled to.

    Authority:
    - § 31 EStG: https://www.gesetze-im-internet.de/estg/__31.html
    - § 32 Abs. 6 EStG: https://www.gesetze-im-internet.de/estg/__32.html
    - BKGG: https://www.gesetze-im-internet.de/bkgg_1996/
    - § 33b Abs. 3 EStG / § 33b Abs. 5 EStG:
      https://www.gesetze-im-internet.de/estg/__33b.html
    """
    raw_children = facts[CHILDREN_INPUT_RAW_KEY]
    filing_posture = str(facts[CHILDREN_INPUT_FILING_POSTURE_KEY])
    if not isinstance(raw_children, tuple):
        raise TypeError(
            f"{CHILDREN_INPUT_RAW_KEY} must be a tuple of Child2025."
        )
    for entry in raw_children:
        if not isinstance(entry, Child2025):
            raise TypeError(
                f"{CHILDREN_INPUT_RAW_KEY} entries must be Child2025 instances."
            )

    # § 33b Abs. 5 EStG election. The election is a profile-level
    # boolean; the loader resolves it as either ``True`` / ``False`` /
    # ``None`` (election absent). Pipeline 1 fails closed when a child
    # carries a non-zero §-33b-Abs.-3-EStG Pauschbetrag and the
    # election is absent — the engine cannot silently choose between
    # transferring and forfeiting on the household's behalf.
    raw_election = facts[CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY]
    qualifying_children_with_disability = tuple(
        child
        for child in raw_children
        if child.relationship == "qualifying_child"
        and (int(child.disability_gdb) > 0 or bool(child.disability_helpless_or_blind))
    )
    if raw_election is None:
        if qualifying_children_with_disability:
            raise NotImplementedError(
                "§ 33b Abs. 5 EStG transferral of a qualifying child's "
                "Behinderten-Pauschbetrag requires an explicit profile "
                "election. Set "
                "``elections.germany_disability_pauschbetrag_transfer`` "
                "to ``true`` (parents claim the transferral) or "
                "``false`` (Pauschbetrag forfeit per § 33b Abs. 5 Satz 1 "
                "EStG) in profile.json. Refusing to compute a return "
                "that would silently choose between transferral and "
                "forfeiture. Authority: "
                "https://www.gesetze-im-internet.de/estg/__33b.html"
            )
        # No child has a Pauschbetrag attached — default to False so the
        # downstream rule reads a deterministic boolean. Election
        # remains semantically absent (no parents-side transferral
        # would attach anyway).
        election_active = False
    elif isinstance(raw_election, bool):
        election_active = raw_election
    else:
        raise TypeError(
            f"{CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY} must be a "
            f"bool or None; got {type(raw_election).__name__}."
        )

    aggregated: GermanyChildrenFacts2025 = aggregate_germany_children_facts_2025(
        raw_children,
        filing_posture=filing_posture,
        disability_pauschbetrag_transfer_election=election_active,
    )
    # § 31 EStG Familienleistungsausgleich is now routed into the
    # executed Pipeline 2 graph via the children sub-graph
    # (``germany_children_2025_rules.execute_germany_children_rule_graph``).
    # The sub-graph performs the Günstigerprüfung between Kindergeld
    # retention and Kinderfreibetrag deduction; the chosen relief flows
    # into DE25-22-FINAL-REFUND for § 31 Satz 4 EStG netting. The
    # earlier fail-closed guard (R-A finding F-DE-2, 2026-05-02) is no
    # longer needed because the legal effect now reaches the assessment.
    # https://www.gesetze-im-internet.de/estg/__31.html
    return {
        CHILDREN_OUTPUT_FACTS: aggregated,
        CHILDREN_OUTPUT_PRESENT: aggregated.children_present,
        CHILDREN_OUTPUT_COUNT: aggregated.children_count,
        CHILDREN_OUTPUT_KINDERFREIBETRAG_TOTAL: q2(
            aggregated.kinderfreibetrag_total_eur
        ),
        CHILDREN_OUTPUT_KINDERGELD_TOTAL: q2(
            aggregated.kindergeld_received_total_eur
        ),
        # Gap 2 outputs — § 33b Abs. 5 EStG transferral total + the
        # election value surfaced as a derived fact so the Pipeline 2
        # children sub-graph can declare it as an input_fact_key
        # without re-reading the profile.
        CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL: q2(
            aggregated.disability_pauschbetrag_total_transferred_eur
        ),
        CHILDREN_OUTPUT_DISABILITY_TRANSFER_ELECTION: election_active,
    }


def _de25_children_stage() -> LawStage:
    """LawStage declaration for ``DERIVE-DE25-CHILDREN``.

    § 31 EStG Familienleistungsausgleich aggregation: per-child
    Kinderfreibetrag (§ 32 Abs. 6 EStG) and Kindergeld (BKGG) summed
    into household totals. Pipeline 1 derivation — no legal arithmetic
    or comparison happens here; the § 31 Günstigerprüfung lives in
    the Pipeline 2 stage.
    """
    return LawStage(
        stage_id=DERIVE_DE25_CHILDREN_STAGE_ID,
        country_or_scope=DE_2025_DERIVATION_SCOPE,
        legal_refs=(
            "§ 31 EStG",
            "§ 32 Abs. 6 EStG",
            "BKGG",
            "§ 33b Abs. 3 EStG",
            "§ 33b Abs. 5 EStG",
        ),
        authority_urls=(ESTG_31_URL, ESTG_32_URL, BKGG_URL, ESTG_33B_URL),
        input_fact_keys=(
            CHILDREN_INPUT_RAW_KEY,
            CHILDREN_INPUT_FILING_POSTURE_KEY,
            CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY,
        ),
        rounding_policy=(
            "Per-child Kinderfreibetrag and Kindergeld amounts arrive "
            "q2-quantized at cent precision; household totals are sums "
            "of those q2 amounts. Statutory partial-year proration is "
            "by full months under § 32 Abs. 6 EStG and BKGG. The "
            "§ 33b Abs. 3 EStG schedule is fixed-cent EUR; the "
            "transferral total is summed at cent precision."
        ),
        law_order_note=(
            "Children aggregation is a Pipeline 1 derivation: the "
            "household totals must complete before the Pipeline 2 "
            "stage DE25-CHILDREN-CREDITS "
            "performs the § 31 EStG Günstigerprüfung. The § 33b Abs. 5 "
            "EStG transferral total is consumed by the Pipeline 2 "
            "ordinary stage DE25-BEHINDERUNG-PAUSCHBETRAG (which adds "
            "it to the parents' household total) and re-emitted by the "
            "children sub-graph stage DE25-CHILDREN-DISABILITY-"
            "PAUSCHBETRAG for audit."
        ),
        legal_formula=(
            "de.derived.kinderfreibetrag_total_eur = "
            "sum(per-child kinderfreibetrag_for_child_2025) over qualifying_child rows; "
            "de.derived.kindergeld_received_total_eur = "
            "sum(per-child kindergeld_for_child_2025) where recipient in "
            "{taxpayer, spouse} and months_in_household; "
            "de.derived.children_present = (children_count > 0); "
            "de.derived.children_disability_pauschbetrag_total_eur = "
            "sum(child_disability_pauschbetrag_for_transferral_2025) "
            "over qualifying_child rows when "
            "germany_disability_pauschbetrag_transfer_election is true, "
            "else 0 (per § 33b Abs. 5 EStG forfeit branch)"
        ),
        narrative_templates={
            "en": "DERIVE-DE25-CHILDREN",
            "de": "DERIVE-DE25-CHILDREN",
        },
        outputs=(
            OutputDeclaration(
                key=CHILDREN_OUTPUT_FACTS,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_PRESENT,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_COUNT,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_KINDERFREIBETRAG_TOTAL,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_KINDERGELD_TOTAL,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL,
                audit_waypoints=frozenset(
                    {AuditWaypoint.PER_POSTEN_AGGREGATION}
                ),
            ),
            OutputDeclaration(
                key=CHILDREN_OUTPUT_DISABILITY_TRANSFER_ELECTION,
                audit_waypoints=frozenset(
                    {AuditWaypoint.DIAGNOSTIC_CROSS_CHECK}
                ),
            ),
        ),
    )


def germany_derivation_law_rules_2025() -> tuple[LawRule, ...]:
    """Return the German Pipeline 1 rule set for tax year 2025.

    WS-5B registers ``DERIVE-DE25-FUND-CLASSIFICATION``. WS-5A registers
    the five DE25-13 derivation extractions. The stages have no
    inter-dependencies; declaration order doesn't affect rule-graph
    semantics.
    """
    return (
        LawRule(
            stage=_fund_classification_stage(),
            implementation_ref=(
                f"{__name__}:_derive_de25_fund_classification"
            ),
            calculate=_derive_de25_fund_classification,
        ),
        LawRule(
            stage=_de25_13a_stage(),
            implementation_ref=f"{__name__}:derive_de25_13a_per_symbol_sale_aggregation",
            calculate=derive_de25_13a_per_symbol_sale_aggregation,
        ),
        LawRule(
            stage=_de25_13b_stage(),
            implementation_ref=f"{__name__}:derive_de25_13b_1099_box_filtering",
            calculate=derive_de25_13b_1099_box_filtering,
        ),
        LawRule(
            stage=_de25_13c_stage(),
            implementation_ref=(
                f"{__name__}:derive_de25_13c_per_symbol_bank_certificate_buckets"
            ),
            calculate=derive_de25_13c_per_symbol_bank_certificate_buckets,
        ),
        LawRule(
            stage=_de25_13d_stage(),
            implementation_ref=(
                f"{__name__}:derive_de25_13d_source_country_classification"
            ),
            calculate=derive_de25_13d_source_country_classification,
        ),
        LawRule(
            stage=_de25_13e_stage(),
            implementation_ref=f"{__name__}:derive_de25_13e_foreign_tax_indexing",
            calculate=derive_de25_13e_foreign_tax_indexing,
        ),
        LawRule(
            stage=_de25_13f_stage(),
            implementation_ref=f"{__name__}:derive_de25_13f_vorabpauschale_inputs",
            calculate=derive_de25_13f_vorabpauschale_inputs,
        ),
        LawRule(
            stage=_de25_children_stage(),
            implementation_ref=f"{__name__}:derive_de25_children",
            calculate=derive_de25_children,
        ),
    )


__all__ = [
    "CHILDREN_INPUT_DISABILITY_TRANSFER_ELECTION_KEY",
    "CHILDREN_INPUT_FILING_POSTURE_KEY",
    "CHILDREN_INPUT_RAW_KEY",
    "CHILDREN_OUTPUT_COUNT",
    "CHILDREN_OUTPUT_DISABILITY_PAUSCHBETRAG_TOTAL",
    "CHILDREN_OUTPUT_DISABILITY_TRANSFER_ELECTION",
    "CHILDREN_OUTPUT_FACTS",
    "CHILDREN_OUTPUT_KINDERFREIBETRAG_TOTAL",
    "CHILDREN_OUTPUT_KINDERGELD_TOTAL",
    "CHILDREN_OUTPUT_PRESENT",
    "DE_2025_DERIVATION_SCOPE",
    "DERIVE_DE25_CHILDREN_STAGE_ID",
    "DERIVE_DE25_FUND_CLASSIFICATION_STAGE_ID",
    "FUND_CLASSIFICATION_INPUT_AKTIENFONDS",
    "FUND_CLASSIFICATION_INPUT_FUND_TYPES",
    "FUND_CLASSIFICATION_INPUT_NON_AKTIENFONDS",
    "FUND_CLASSIFICATION_INPUT_REPO_CSV",
    "FUND_CLASSIFICATION_OUTPUT_KEY",
    "derive_de25_13a_per_symbol_sale_aggregation",
    "derive_de25_13b_1099_box_filtering",
    "derive_de25_13c_per_symbol_bank_certificate_buckets",
    "derive_de25_13d_source_country_classification",
    "derive_de25_13e_foreign_tax_indexing",
    "derive_de25_13f_vorabpauschale_inputs",
    "derive_de25_children",
    "germany_derivation_law_rules_2025",
]
