"""Per-stage rule functions for the Germany 2025 capital-income graph.

This module is the single execution path for the nine declared
``DE25-13`` through ``DE25-21`` LawStages. Bodies are lifted from the
historical ``compute_germany_capital_assessment_2025`` monolith in
``tax_pipeline/y2025/germany_law.py``, split on stage boundaries so every
legal value tracked by ``GermanyCapitalAssessment2025`` is produced by a
``LawRule.calculate`` invocation through ``execute_rule_graph``.

Each stage's output is a single rich dict carrying all the values that
legal step generates. Downstream stages destructure the upstream dicts
in their own ``calculate`` body. This keeps the LawStage declarations
clean (one named edge per dependency) while satisfying the ENGINE-SPEC
principle that every legal value is reachable from a stage output.

Authority:

- § 20 EStG (https://www.gesetze-im-internet.de/estg/__20.html) -
  general capital-income classification.
- InvStG §§ 16, 19, 20, 21 (https://www.gesetze-im-internet.de/invstg_2018/)
  - investment-fund partial exemption / partial loss disallowance.
- § 20 Abs. 6 EStG, BMF Abgeltungsteuer 14.05.2025 Rn. 120, 122,
  228-230 - § 20 loss-class ordering. **JStG 2024 (Empfehlung Nr. 4a
  des Finanzausschusses, in Kraft 06.12.2024) gestrichen:** § 20 Abs. 6
  Sätze 5 und 6 EStG (€20,000 loss-offset caps for Termingeschäfte
  and Uneinbringlichkeit von Kapitalforderungen / Wertlosigkeit).
  Effective for all assessment years open on 06.12.2024 — so VZ 2025
  Anlage KAP no longer carries the three former 2024 per-bucket lines
  that surfaced those caps. The surviving Aktien-spezifischer
  Verrechnungskreis (§ 20 Abs. 6 Satz 4 EStG) remains in force and is
  modeled in ``de25_15_section_20_6_netting``. Authority — BMF
  16.05.2025 Steuerbescheinigung-Schreiben (BMF-VERIFIED 2026-05-13):
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
  and the post-JStG-2024 text of § 20 Abs. 6 EStG at
  https://www.gesetze-im-internet.de/estg/__20.html .
- § 20 Abs. 9 EStG - Sparer-Pauschbetrag.
- § 32d Abs. 1, 5 EStG (https://www.gesetze-im-internet.de/estg/__32d.html)
  - flat capital tax and per-item foreign-tax credit.
- § 4, § 5 SolzG 1995 (https://www.gesetze-im-internet.de/solzg_1995/) -
  capital solidarity surcharge.
- DBA-USA Art. 10 / Art. 23
  (https://www.bundesfinanzministerium.de/Web/DE/Themen/Steuern/Internationales_Steuerrecht/Staatenbezogene_Informationen/Vereinigte_Staaten/vereinigte_staaten.html)
  - U.S.-source treaty dividend ordering through § 32d Abs. 5.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import LawRule, LawStage, RuleGraphExecution, execute_rule_graph
from tax_pipeline.y2025.germany_law import (
    BASISZINS_2025,
    FUND_TEILFREISTELLUNG_RATES_2025,
    VORABPAUSCHALE_BASISERTRAG_FACTOR,
    CapitalTaxAssessment2025,
    GermanyCapitalAssessment2025,
    GermanyCapitalAssessmentInputs2025,
    GermanyTreatyDividendItem2025,
    GermanyUSTreatyDividendPacketItem2025,
    TreatyRelievedCapitalTax2025,
    _allocated_applied_credit_2025,
    _taxable_capital_item_after_saver_allowance_2025,
    _validate_germany_capital_inputs_2025,
    floor_cent,
    foreign_tax_credit_32d5_cap_2025,
    fund_type_for_symbol_2025,
    q2,
    saver_allowance_for_spouse_20_9_2025,
)
from tax_pipeline.y2025.germany_stages import germany_capital_law_stages_2025
from tax_pipeline.pipeline_context import set_pipeline_context_value

ZERO_EUR = Decimal("0.00")
GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY = "de25.capital_rule_graph_execution"
"""Pipeline-context key under which ``execute_germany_capital_rule_graph``
stashes the executed ``RuleGraphExecution`` for in-memory hand-off to the
narrative packet builder.
"""


def de25_13_capital_raw_buckets(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 20 EStG legal bucket assembly. The five raw-input derivations
    # DE25-13 historically performed inline now live as Pipeline 1 stages
    # DERIVE-DE25-13A through 13E (see WS-5A in
    # docs/invariant-migration-plan.md). This body keeps only the legal
    # interpretation under § 20 Abs. 1 / Abs. 2 EStG and InvStG § 20.
    # https://www.gesetze-im-internet.de/estg/__20.html
    # https://www.gesetze-im-internet.de/invstg_2018/__20.html
    sa = facts["de.derived.per_symbol_sale_aggregation"]
    box = facts["de.derived.box_1a_filtered_dividends"]
    bc = facts["de.derived.per_symbol_bank_certificate_buckets"]
    cl = facts["de.derived.source_country_classification"]
    ft = facts["de.derived.foreign_tax_indexing"]
    summary = bc["bank_certificate_summary"]
    # § 20 Abs. 2 Satz 1 Nr. 1 EStG: bank-certificate stock-sale gains
    # (KAP Zeile 8 subset) merge into the same stock bucket as broker
    # sales so § 20 Abs. 6 ordering treats them uniformly. § 20 Abs. 1
    # EStG: bank-certificate non-stock income is § 20 Abs. 1 capital
    # income (non-fund — the certificate already nets InvStG § 20).
    return {
        "de.capital.raw_buckets": {
            "stock_gain": sa["stock_gain"] + summary["stock_gain"],
            "fund_gain": sa["fund_gain"],
            "option_gain": sa["option_gain"],
            "positive_income_total": box["positive_income_total"] + summary["non_stock_income"],
            "non_fund_positive_income_total": box["non_fund_positive_income_total"] + summary["non_stock_income"],
            "explicit_foreign_tax_total": ft["explicit_foreign_tax_total"],
            "stock_symbol_gain": {**sa["stock_symbol_gain"], **bc["stock_subset_by_certificate"]},
            "fund_symbol_gain": sa["fund_symbol_gain"],
            "fund_symbol_income": box["fund_symbol_income"],
            "option_symbol_gain": sa["option_symbol_gain"],
            "income_items": box["income_items"],
            "foreign_tax_by_item": ft["foreign_tax_by_item"],
            "foreign_tax_refund_by_item": ft["foreign_tax_refund_by_item"],
            "bank_certificate_non_stock_by_symbol": bc["bank_certificate_non_stock_by_symbol"],
            "bank_certificate_foreign_taxable_by_item": bc["bank_certificate_foreign_taxable_by_item"],
            "bank_certificate_summary": summary,
            "domestic_capital_tax_withheld": bc["domestic_capital_tax_withheld"],
            "domestic_capital_soli_withheld": bc["domestic_capital_soli_withheld"],
            "fund_symbols": cl["fund_symbols"],
            "fund_types": cl["fund_types"],
            "equity_fund_total": cl["equity_fund_total"],
            "non_equity_fund_total": cl["non_equity_fund_total"],
            "dher_stock_gain": sa["dher_stock_gain"],
        }
    }


def de25_13f_vorabpauschale(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """InvStG § 19 Vorabpauschale (deemed-distribution) per accumulating fund.

    For each accumulating fund the taxpayer held during the year:

    1. ``basisertrag = max(0, NAV_start * 0.7 * Basiszins * months_held / 12)``
       per InvStG § 18 Abs. 1.
    2. ``gross_vorabpauschale = max(0, basisertrag - Ausschuettung_year)``
       per InvStG § 18 Abs. 1 Satz 3 (the actual distribution is netted
       against the Basisertrag floor before the Vorabpauschale arises).
    3. ``nav_gain = max(0, NAV_end - NAV_start)`` is the § 16 Abs. 1 Nr. 2
       cap: a Vorabpauschale cannot exceed the year's actual market gain.
    4. ``vorabpauschale = min(gross_vorabpauschale, nav_gain)``.
    5. ``taxable_after_teilfreistellung = vorabpauschale * (1 - rate)``
       where the InvStG § 20 Teilfreistellung rate is keyed by the
       fund's classification (Aktien / Misch / Immobilien / Sonstige).

    The Basiszinssatz for 2025 is 2.53 % (BMF Schreiben 16.01.2025,
    IV C 1 - S 1980-1/19/10005:008). The Vorabpauschale is laufender
    Ertrag under § 32d Abs. 1 EStG (subject to 25 % Abgeltungsteuer)
    and feeds § 20 Abs. 6 EStG netting as a non-stock-gain bucket
    (NOT a Veräusserungsgewinn — § 20 Abs. 6 Satz 4 prohibits
    offsetting against stock losses).

    Authority:

    - InvStG § 18 (Basisertrag formula):
      https://www.gesetze-im-internet.de/invstg_2018/__18.html
    - InvStG § 19 (Vorabpauschale):
      https://www.gesetze-im-internet.de/invstg_2018/__19.html
    - InvStG § 16 Abs. 1 Nr. 2 (NAV-gain cap):
      https://www.gesetze-im-internet.de/invstg_2018/__16.html
    - InvStG § 20 (Teilfreistellung):
      https://www.gesetze-im-internet.de/invstg_2018/__20.html
    - § 32d Abs. 1 EStG (25 % Abgeltungsteuer):
      https://www.gesetze-im-internet.de/estg/__32d.html
    """
    vorab_inputs: Mapping[str, Mapping[str, Any]] = facts[
        "de.derived.vorabpauschale_inputs"
    ]
    fund_classification: Mapping[str, str] = facts["de.capital.fund_classification"]
    teilfreistellung_rates: Mapping[str, Decimal] = facts[
        "de.capital.fund_teilfreistellung_rates"
    ]
    basiszins: Decimal = Decimal(str(facts["de.capital.basiszins"]))
    basisertrag_factor: Decimal = Decimal(
        str(facts["de.capital.vorabpauschale_basisertrag_factor"])
    )

    per_symbol: dict[str, Decimal] = {}
    total_gross = ZERO_EUR
    total_after_teilfreistellung = ZERO_EUR
    months_per_year = Decimal("12")

    # Sort the inputs deterministically so dict insertion order is stable.
    for symbol in sorted(vorab_inputs):
        row = vorab_inputs[symbol]
        nav_start = Decimal(str(row["nav_start_eur"]))
        nav_end = Decimal(str(row["nav_end_eur"]))
        ausschuettung = Decimal(str(row["ausschuettung_eur"]))
        months_held = Decimal(str(int(row["months_held"])))

        # InvStG § 18 Abs. 1 Satz 1 + Abs. 2: pro-rated Basisertrag.
        basisertrag = nav_start * basisertrag_factor * basiszins * months_held / months_per_year
        if basisertrag < ZERO_EUR:
            basisertrag = ZERO_EUR

        # InvStG § 18 Abs. 1 Satz 3: net actual distributions out of the
        # Basisertrag before declaring a Vorabpauschale.
        gross_vorabpauschale = basisertrag - ausschuettung
        if gross_vorabpauschale < ZERO_EUR:
            gross_vorabpauschale = ZERO_EUR

        # InvStG § 16 Abs. 1 Nr. 2: cap at the year's actual NAV gain.
        nav_gain = nav_end - nav_start
        if nav_gain < ZERO_EUR:
            nav_gain = ZERO_EUR
        vorabpauschale = gross_vorabpauschale if gross_vorabpauschale < nav_gain else nav_gain

        vorab_q2 = q2(vorabpauschale)
        per_symbol[symbol] = vorab_q2
        total_gross += vorab_q2

        # InvStG § 20 Teilfreistellung — same rate that already routes
        # Ausschuettungen (DE25-14) applies to the Vorabpauschale.
        fund_type = fund_type_for_symbol_2025(symbol, fund_classification)
        rate = teilfreistellung_rates[fund_type]
        taxable_after_rate = q2(vorab_q2 * (Decimal("1.00") - rate))
        total_after_teilfreistellung += taxable_after_rate

    return {
        "de.capital.vorabpauschale_per_symbol_eur": dict(per_symbol),
        "de.capital.vorabpauschale_total_eur": q2(total_gross),
        "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": q2(
            total_after_teilfreistellung
        ),
    }


def de25_14_fund_teilfreistellung(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # InvStG § 20 exempts the statutory percentage of fund gains from tax;
    # InvStG § 21 disallows the same percentage of related losses. Apply the
    # taxable factor before § 20 netting / saver allowance ordering.
    raw_buckets = facts["de.capital.raw_buckets"]
    teilfreistellung_rates: Mapping[str, Decimal] = facts["de.capital.fund_teilfreistellung_rates"]
    fund_symbols: frozenset[str] = raw_buckets["fund_symbols"]
    fund_types: dict[str, str] = raw_buckets["fund_types"]
    fund_symbol_gain: dict[str, Decimal] = raw_buckets["fund_symbol_gain"]
    fund_symbol_income: dict[str, Decimal] = raw_buckets["fund_symbol_income"]

    taxable_by_symbol_after_fund_teilfreistellung: dict[str, Decimal] = {}
    fund_teilfreistellung_reduction = ZERO_EUR
    fund_taxable_after_teilfreistellung = ZERO_EUR
    # Sort the frozenset so dict insertion order is deterministic across runs.
    # frozenset iteration order is hash-based and process-stable but not
    # input-order preserving; downstream JSON / fingerprint payloads must not
    # depend on hash randomization seed.
    for symbol in sorted(fund_symbols):
        fund_taxable = fund_symbol_gain.get(symbol, ZERO_EUR) + fund_symbol_income.get(symbol, ZERO_EUR)
        rate = teilfreistellung_rates[fund_types[symbol]]
        fund_taxable_after_rate = fund_taxable * (Decimal("1.00") - rate)
        fund_taxable_after_teilfreistellung += fund_taxable_after_rate
        fund_teilfreistellung_reduction += fund_taxable - fund_taxable_after_rate
        taxable_by_symbol_after_fund_teilfreistellung[symbol] = (
            taxable_by_symbol_after_fund_teilfreistellung.get(symbol, ZERO_EUR) + fund_taxable_after_rate
        )
    return {
        "de.capital.fund_after_teilfreistellung": {
            "fund_taxable_after_teilfreistellung": fund_taxable_after_teilfreistellung,
            "fund_teilfreistellung_reduction": fund_teilfreistellung_reduction,
            "taxable_by_symbol_after_fund_teilfreistellung": taxable_by_symbol_after_fund_teilfreistellung,
        }
    }


def de25_15_section_20_6_netting(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 20 Abs. 6 EStG (BMF Abgeltungsteuer 14.05.2025 Rn. 120, 122, 228-230):
    # current-year non-stock losses net against positive § 20 income before
    # consuming a separately restricted prior-year stock-loss carryforward.
    # Treaty dividend items integrate into the per-item foreign-tax index here.
    #
    # JStG 2024 (Empfehlung Nr. 4a des Finanzausschusses, in Kraft 06.12.2024)
    # gestrichen § 20 Abs. 6 Sätze 5 und 6 EStG ohne Ersatz: the €20,000
    # loss-offset cap for Termingeschäfte and the €20,000 cap for
    # Uneinbringlichkeit von Kapitalforderungen / Wertlosigkeit are GONE
    # as of 06.12.2024 and apply to every assessment year still open on
    # that date — so VZ 2025 the engine models. This rule was already
    # only implementing the surviving Aktien-spezifischer
    # Verrechnungskreis (§ 20 Abs. 6 Satz 4 EStG), so the legal-math
    # body needs no edit. The former 2024 Anlage KAP per-bucket lines
    # that carried the now-deleted caps ARE dropped downstream in
    # DE25-FORM-KAP-PROJECTION.
    # Authority: BMF 16.05.2025 Steuerbescheinigung-Schreiben at
    # https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
    # and post-JStG-2024 § 20 Abs. 6 EStG at
    # https://www.gesetze-im-internet.de/estg/__20.html
    raw_buckets = facts["de.capital.raw_buckets"]
    fund_after = facts["de.capital.fund_after_teilfreistellung"]
    stock_loss_carryforward_2024: Decimal = Decimal(str(facts["de.capital.stock_loss_carryforward_2024"]))
    treaty_dividend_items: tuple[GermanyTreatyDividendItem2025, ...] = facts["de.capital.treaty_dividend_items"]
    teilfreistellung_rates: Mapping[str, Decimal] = facts["de.capital.fund_teilfreistellung_rates"]
    # InvStG § 19 Vorabpauschale (laufender Ertrag, NOT a Veräusserungsgewinn).
    # § 20 Abs. 6 Satz 4 EStG forbids offsetting against stock losses, so the
    # taxable Vorabpauschale (already net of InvStG § 20 Teilfreistellung) joins
    # the non-stock-gain side of § 20 Abs. 6 ordering — it absorbs current-year
    # non-stock losses but never current-year or carried stock losses.
    vorabpauschale_taxable_after_teilfreistellung: Decimal = Decimal(
        str(facts["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"])
    )
    fund_types: dict[str, str] = raw_buckets["fund_types"]
    fund_symbols: frozenset[str] = raw_buckets["fund_symbols"]

    stock_gain: Decimal = raw_buckets["stock_gain"]
    fund_taxable_after_teilfreistellung: Decimal = fund_after["fund_taxable_after_teilfreistellung"]
    option_gain: Decimal = raw_buckets["option_gain"]
    non_fund_positive_income_total: Decimal = raw_buckets["non_fund_positive_income_total"]
    stock_symbol_gain: dict[str, Decimal] = raw_buckets["stock_symbol_gain"]
    option_symbol_gain: dict[str, Decimal] = raw_buckets["option_symbol_gain"]
    bank_certificate_non_stock_by_symbol: dict[str, Decimal] = raw_buckets["bank_certificate_non_stock_by_symbol"]
    income_items: tuple[tuple[str, str, str, Decimal], ...] = raw_buckets["income_items"]
    bank_certificate_foreign_taxable_by_item: dict[str, Decimal] = raw_buckets[
        "bank_certificate_foreign_taxable_by_item"
    ]
    foreign_tax_by_item: dict[str, Decimal] = dict(raw_buckets["foreign_tax_by_item"])
    foreign_tax_refund_by_item: dict[str, Decimal] = dict(raw_buckets["foreign_tax_refund_by_item"])

    # § 20 Abs. 6 EStG (https://www.gesetze-im-internet.de/estg/__20.html)
    # ordering. Authority: BMF-Schreiben vom 19.05.2022 (Einzelfragen zur
    # Abgeltungsteuer), in der Fassung vom 14.05.2025 (BMF_ABGELTUNGSTEUER_URL),
    # Rn. 118 (Verlustverrechnungsreihenfolge) — and Rn. 122 for the related
    # foreign-tax-credit-after-loss-netting rule consumed downstream by
    # de25_18_section_32d5_ftc.
    #
    # Rn. 118 verbatim (German):
    #   "Für die Verlustverrechnung in den Verlustverrechnungskreisen ist in
    #    der Veranlagung nachfolgende Reihenfolge zu berücksichtigen:
    #    1. Aktienveräußerungsgewinne/ -verluste im Sinne des § 20 Absatz 6
    #       Satz 4 EStG aus dem aktuellen Jahr; Aktienveräußerungsverluste
    #       … dürfen nur mit Aktienveräußerungsgewinnen verrechnet werden.
    #    2. sonstige Kapitalerträge/Verluste aus dem aktuellen Jahr;
    #       sonstige negative Einkünfte aus dem aktuellen Jahr im Sinne des
    #       § 20 EStG dürfen mit positiven Einkünften im Sinne des § 20 EStG
    #       verrechnet werden.
    #    3. Verlustvorträge … aus Aktienveräußerungen … dürfen nur mit nach
    #       Verrechnung gemäß Ziffer 1 und 2 verbleibenden
    #       Aktienveräußerungsgewinnen verrechnet werden."
    #
    # Rn. 122 verbatim (German):
    #   "Verluste mindern die abgeltungsteuerpflichtigen Erträge unabhängig
    #    davon, ob diese aus in- oder ausländischen Quellen stammen. Die
    #    Summe der anrechenbaren ausländischen Quellensteuer ist auf die
    #    nach Verlustverrechnung verbleibende Abgeltungsteuerschuld
    #    anzurechnen."
    #
    # Reading implemented here: BMF Rn. 118 step 2 ("sonstige negative
    # Einkünfte … mit positiven Einkünften … verrechnet") consumes the
    # current-year non-stock loss against the current-year stock gain
    # BEFORE the prior-year stock-loss carryforward (step 3) is applied.
    # Consequence: when both a current-year non-stock loss and a prior-year
    # stock-loss carryforward exist alongside a current-year stock gain,
    # the carryforward consumed equals (stock_gain − non_stock_loss),
    # leaving the unused part of the carryforward intact for future years
    # rather than burning it to offset a stock gain that step 2 already
    # absorbed. The alternative reading — applying carryforward first,
    # then current-year non-stock losses — would silently consume more of
    # the carryforward and is the reading that BMF Rn. 118 Ziffer 3
    # ("nur mit nach Verrechnung gemäß Ziffer 1 und 2 verbleibenden
    # Aktienveräußerungsgewinnen") explicitly forbids.
    # See tests/y2025/test_section_20_6_ordering.py for the worked example
    # distinguishing the two readings with concrete EUR amounts.
    # InvStG § 19 Vorabpauschale joins the non-stock-net bucket per § 20 Abs. 6
    # Satz 4 EStG (laufender Ertrag, NOT a Veräusserungsgewinn). It is a
    # positive non-stock contribution; the netting absorbs current-year non-stock
    # losses against the entire non-stock total including Vorabpauschale.
    current_year_non_stock_net = (
        option_gain
        + fund_taxable_after_teilfreistellung
        + non_fund_positive_income_total
        + vorabpauschale_taxable_after_teilfreistellung
    )
    current_year_non_stock_loss = max(ZERO_EUR, -current_year_non_stock_net)
    stock_gain_available_for_carryforward = max(ZERO_EUR, stock_gain - current_year_non_stock_loss)
    stock_loss_carryforward_used = min(stock_gain_available_for_carryforward, stock_loss_carryforward_2024)
    stock_gain_after_carryforward = max(stock_gain - stock_loss_carryforward_used, ZERO_EUR)
    current_year_stock_loss = max(-stock_gain, ZERO_EUR)
    stock_loss_carryforward_remaining = (
        stock_loss_carryforward_2024 - stock_loss_carryforward_used + current_year_stock_loss
    )

    taxable_by_symbol_before_allowance: dict[str, Decimal] = dict(
        fund_after["taxable_by_symbol_after_fund_teilfreistellung"]
    )
    for symbol, amount in bank_certificate_non_stock_by_symbol.items():
        taxable_by_symbol_before_allowance[symbol] = (
            taxable_by_symbol_before_allowance.get(symbol, ZERO_EUR) + amount
        )

    positive_stock_symbol_total = sum((max(value, ZERO_EUR) for value in stock_symbol_gain.values()), ZERO_EUR)
    for symbol, gain in stock_symbol_gain.items():
        positive_gain = max(gain, ZERO_EUR)
        if positive_gain == ZERO_EUR:
            continue
        loss_share = (
            stock_loss_carryforward_used * positive_gain / positive_stock_symbol_total
            if positive_stock_symbol_total
            else ZERO_EUR
        )
        taxable_by_symbol_before_allowance[symbol] = (
            taxable_by_symbol_before_allowance.get(symbol, ZERO_EUR)
            + max(ZERO_EUR, positive_gain - loss_share)
        )
    for symbol, gain in option_symbol_gain.items():
        taxable_by_symbol_before_allowance[symbol] = (
            taxable_by_symbol_before_allowance.get(symbol, ZERO_EUR) + gain
        )

    # InvStG § 19 Vorabpauschale (laufender Ertrag, post-Teilfreistellung)
    # joins the per-symbol pre-allowance index under a synthetic
    # ``__vorabpauschale__`` key so § 20 Abs. 9 Sparer-Pauschbetrag
    # allocation and § 32d Abs. 5 per-Posten allocation can address it
    # uniformly with the rest of the non-stock-gain side. The key is
    # synthetic because Vorabpauschale is per-fund (already indexed in
    # ``de.capital.vorabpauschale_per_symbol_eur``); the saver-allowance
    # math operates on the aggregate non-stock-gain total, not per-fund.
    if vorabpauschale_taxable_after_teilfreistellung > ZERO_EUR:
        # The ``__vorabpauschale__`` slot is unique to InvStG § 19 deemed
        # distribution (laufender Ertrag) and never collides with a real
        # symbol; the synthetic key is created here for the first and
        # only time per execution. Direct assignment is safe.
        taxable_by_symbol_before_allowance["__vorabpauschale__"] = (
            vorabpauschale_taxable_after_teilfreistellung
        )

    # Build foreign_taxable_item_by_key_before_allowance with teilfreistellung-
    # adjusted fund items + non-fund items + bank certificate carry-through.
    foreign_taxable_item_by_key_before_allowance: dict[str, Decimal] = dict(
        bank_certificate_foreign_taxable_by_item
    )
    for credit_item_id, symbol, bucket, amount in income_items:
        taxable_income = max(amount, ZERO_EUR)
        if bucket == "fund_like":
            taxable_income *= Decimal("1.00") - teilfreistellung_rates[fund_types[symbol]]
        if taxable_income:
            foreign_taxable_item_by_key_before_allowance[credit_item_id] = (
                foreign_taxable_item_by_key_before_allowance.get(credit_item_id, ZERO_EUR) + taxable_income
            )
        if symbol in fund_symbols:
            continue
        taxable_by_symbol_before_allowance[symbol] = (
            taxable_by_symbol_before_allowance.get(symbol, ZERO_EUR) + taxable_income
        )

    # Treaty dividend items integration: validate matching taxable income, route
    # treaty-allowed source-tax through § 32d Abs. 5 per-item cap.
    treaty_us_source_dividend_gross = ZERO_EUR
    treaty_us_source_dividend_allowed_us_tax = ZERO_EUR
    treaty_us_source_dividend_taxable_by_item: dict[str, Decimal] = {}
    treaty_us_source_dividend_allowed_tax_by_item: dict[str, Decimal] = {}
    treaty_dividend_input_by_item: dict[str, GermanyTreatyDividendItem2025] = {}
    explicit_foreign_tax_total: Decimal = raw_buckets["explicit_foreign_tax_total"]
    for item in treaty_dividend_items:
        item_id = str(item.item_id).strip()
        matching_taxable_income = q2(foreign_taxable_item_by_key_before_allowance.get(item_id, ZERO_EUR))
        if matching_taxable_income <= ZERO_EUR:
            raise ValueError(
                "Germany U.S.-source treaty dividend items require a matching taxable U.S.-source dividend "
                f"in income-cashflows.csv by foreign_tax_item_id: {item_id}"
            )
        if matching_taxable_income != q2(item.german_taxable_dividend_eur):
            raise ValueError(
                "Germany U.S.-source treaty dividend taxable amount must match the § 20/InvStG taxable "
                f"dividend item for § 32d(5): {item_id}"
            )
        item_treaty_allowed_us_tax = q2(item.gross_dividend_eur * item.treaty_rate)
        treaty_us_source_dividend_gross += item.gross_dividend_eur
        treaty_us_source_dividend_allowed_us_tax += item_treaty_allowed_us_tax
        treaty_us_source_dividend_taxable_by_item[item_id] = matching_taxable_income
        treaty_us_source_dividend_allowed_tax_by_item[item_id] = item_treaty_allowed_us_tax
        treaty_dividend_input_by_item[item_id] = item
        if item_id in foreign_tax_by_item:
            # DBA-USA Art. 10/23 and § 32d Abs. 5 EStG: a generic foreign_tax row
            # with the same foreign_tax_item_id would be a second credit path for
            # the same dividend item. Fail closed.
            raise ValueError(
                "Germany duplicate U.S. treaty dividend foreign_tax item_id would double-credit § 32d(5): "
                f"{item_id}"
            )
        if item_treaty_allowed_us_tax:
            explicit_foreign_tax_total += item_treaty_allowed_us_tax
            foreign_tax_by_item[item_id] = foreign_tax_by_item.get(item_id, ZERO_EUR) + item_treaty_allowed_us_tax
            foreign_tax_refund_by_item[item_id] = foreign_tax_refund_by_item.get(item_id, ZERO_EUR)

    return {
        "de.capital.after_section_20_6_netting": {
            "stock_gain_after_carryforward": stock_gain_after_carryforward,
            "stock_loss_carryforward_used": stock_loss_carryforward_used,
            "stock_loss_carryforward_remaining": stock_loss_carryforward_remaining,
            "taxable_by_symbol_before_allowance": taxable_by_symbol_before_allowance,
            "foreign_taxable_item_by_key_before_allowance": foreign_taxable_item_by_key_before_allowance,
            "foreign_tax_by_item": foreign_tax_by_item,
            "foreign_tax_refund_by_item": foreign_tax_refund_by_item,
            "explicit_foreign_tax_total": explicit_foreign_tax_total,
            "treaty_us_source_dividend_gross": treaty_us_source_dividend_gross,
            "treaty_us_source_dividend_allowed_us_tax": treaty_us_source_dividend_allowed_us_tax,
            "treaty_us_source_dividend_taxable_by_item": treaty_us_source_dividend_taxable_by_item,
            "treaty_us_source_dividend_allowed_tax_by_item": treaty_us_source_dividend_allowed_tax_by_item,
            "treaty_dividend_input_by_item": treaty_dividend_input_by_item,
        }
    }


def de25_16_section_20_9_saver(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 20 Abs. 9 Satz 3 EStG: Sparer-Pauschbetrag applied to net capital income
    # before § 32d tax. Spouse-allocation per § 26b joint assessment uses the
    # other-spouse pre-allowance taxable amount when present.
    netting = facts["de.capital.after_section_20_6_netting"]
    raw_buckets = facts["de.capital.raw_buckets"]
    fund_after = facts["de.capital.fund_after_teilfreistellung"]
    saver_allowance_eur: Decimal = Decimal(str(facts["de.capital.saver_allowance"]))
    other_spouse_capital_before_allowance = facts.get("de.capital.other_spouse_capital_before_allowance")
    # InvStG § 19 Vorabpauschale (laufender Ertrag, post-Teilfreistellung)
    # joins the saver-allowance / § 32d tax base alongside the other
    # non-stock-gain components. Already net of InvStG § 20 Teilfreistellung
    # at this point so it adds identically to both the
    # ``primary_taxable_after_teilfreistellung_before_allowance`` total (post-
    # Teilfreistellung path) and the ``combined_current_capital`` total
    # (pre-Teilfreistellung path).
    vorabpauschale_taxable_after_teilfreistellung: Decimal = Decimal(
        str(facts["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"])
    )

    taxable_by_symbol_before_allowance: dict[str, Decimal] = netting["taxable_by_symbol_before_allowance"]
    # § 20 Abs. 9 EStG / § 32d Abs. 5 EStG: per-Posten saver-allowance allocation
    # divides each item's q2-quantized pre-allowance amount by the total. Both
    # numerator and denominator must live in the same q2 precision domain or the
    # resulting share will reference fractional cents that the per-symbol path
    # cannot reproduce, leaking sub-cent residue into the final foreign-tax
    # credit.
    total_taxable_before_allowance = q2(
        max(
            ZERO_EUR,
            sum(taxable_by_symbol_before_allowance.values(), ZERO_EUR),
        )
    )

    if other_spouse_capital_before_allowance is not None:
        saver_allowance_used = saver_allowance_for_spouse_20_9_2025(
            total_taxable_before_allowance,
            Decimal(str(other_spouse_capital_before_allowance)),
            saver_allowance_eur,
        )
    else:
        saver_allowance_used = min(saver_allowance_eur, total_taxable_before_allowance)

    stock_gain_after_carryforward: Decimal = netting["stock_gain_after_carryforward"]
    fund_gain: Decimal = raw_buckets["fund_gain"]
    option_gain: Decimal = raw_buckets["option_gain"]
    positive_income_total: Decimal = raw_buckets["positive_income_total"]
    fund_taxable_after_teilfreistellung: Decimal = fund_after["fund_taxable_after_teilfreistellung"]
    non_fund_positive_income_total: Decimal = raw_buckets["non_fund_positive_income_total"]

    combined_current_capital = q2(
        stock_gain_after_carryforward
        + fund_gain
        + option_gain
        + positive_income_total
        + vorabpauschale_taxable_after_teilfreistellung
    )
    taxable_before_teilfreistellung = q2(
        max(ZERO_EUR, combined_current_capital - saver_allowance_used)
    )
    primary_taxable_after_teilfreistellung_before_allowance = q2(
        max(
            ZERO_EUR,
            stock_gain_after_carryforward
            + fund_taxable_after_teilfreistellung
            + option_gain
            + non_fund_positive_income_total
            + vorabpauschale_taxable_after_teilfreistellung,
        )
    )
    taxable_after_teilfreistellung = q2(
        max(ZERO_EUR, primary_taxable_after_teilfreistellung_before_allowance - saver_allowance_used)
    )

    return {
        "de.capital.taxable_after_allowance": {
            "saver_allowance_used": saver_allowance_used,
            "total_taxable_before_allowance": total_taxable_before_allowance,
            "primary_taxable_after_teilfreistellung_before_allowance": primary_taxable_after_teilfreistellung_before_allowance,
            "taxable_before_teilfreistellung": taxable_before_teilfreistellung,
            "taxable_after_teilfreistellung": taxable_after_teilfreistellung,
            "combined_current_capital": combined_current_capital,
        },
        # A4 (FORM-MAPPING-FOLLOWUP): § 20 Abs. 9 Satz 1/2 EStG
        # Sparer-Pauschbetrag claim line. The renderer previously only
        # surfaced Anlage KAP Zeile 17 (already-used at the bank); the
        # statutory €1,000 single / €2,000 joint claim that the user
        # enters on Anlage KAP Zeile 4 was missing. ``saver_allowance_eur``
        # is the statutory cap (read from
        # ``de.capital.saver_allowance``, which traces to
        # ``SAVER_ALLOWANCE_SINGLE_2025_EUR`` /
        # ``SAVER_ALLOWANCE_JOINT_2025_EUR`` in
        # ``germany_2025_law.py`` per invariant I1) and equals the
        # value the user writes on Anlage KAP Zeile 4 of each spouse's
        # form under the joint-assessment convention. Authority:
        #   - § 20 Abs. 9 Satz 1 EStG (€1,000 single)
        #   - § 20 Abs. 9 Satz 2 EStG (€2,000 jointly assessed spouses)
        #   - § 20 Abs. 9 Satz 3 EStG (spouse-allocation; handled by
        #     ``saver_allowance_for_spouse_20_9_2025`` for the *used*
        #     amount on Zeile 17, not for the *claimed* amount on
        #     Zeile 4).
        # https://www.gesetze-im-internet.de/estg/__20.html
        "de.capital.sparer_pauschbetrag_claimed_eur": q2(saver_allowance_eur),
    }


def de25_17_section_32d1_gross_tax(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 32d Abs. 1 EStG: 25 percent flat tax on net capital income. Both versions
    # (with / without InvStG § 20 partial exemption) tracked for audit.
    taxable_after_allowance = facts["de.capital.taxable_after_allowance"]
    capital_tax_rate: Decimal = Decimal(str(facts["de.capital.capital_tax_rate"]))
    return {
        "de.capital.section_32d1_gross_tax": {
            "gross_income_tax_with_teilfreistellung": q2(
                taxable_after_allowance["taxable_after_teilfreistellung"] * capital_tax_rate
            ),
            "gross_income_tax_no_teilfreistellung": q2(
                taxable_after_allowance["taxable_before_teilfreistellung"] * capital_tax_rate
            ),
        }
    }


def de25_18_section_32d5_ftc(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 32d Abs. 5 EStG: per-item foreign-tax credit cap, then aggregate against
    # the remaining § 32d Abs. 1 tax. Per-item caps after § 20 Abs. 9 allowance
    # allocation are also retained for treaty exports.
    netting = facts["de.capital.after_section_20_6_netting"]
    taxable_after_allowance = facts["de.capital.taxable_after_allowance"]
    section_32d1 = facts["de.capital.section_32d1_gross_tax"]
    capital_tax_rate: Decimal = Decimal(str(facts["de.capital.capital_tax_rate"]))

    foreign_tax_by_item: dict[str, Decimal] = netting["foreign_tax_by_item"]
    foreign_tax_refund_by_item: dict[str, Decimal] = netting["foreign_tax_refund_by_item"]
    foreign_taxable_item_by_key_before_allowance: dict[str, Decimal] = netting[
        "foreign_taxable_item_by_key_before_allowance"
    ]

    # Validate matching taxable foreign income items.
    missing_foreign_income_items = sorted(
        item_id
        for item_id in foreign_tax_by_item
        if foreign_taxable_item_by_key_before_allowance.get(item_id, ZERO_EUR) <= ZERO_EUR
    )
    if missing_foreign_income_items:
        raise ValueError(
            "Germany foreign_tax rows require a matching taxable foreign income item for § 32d(5): "
            + ", ".join(missing_foreign_income_items)
        )

    foreign_tax_credit_cap = foreign_tax_credit_32d5_cap_2025(
        tuple(
            (
                foreign_taxable_item_by_key_before_allowance.get(item_id, ZERO_EUR),
                foreign_tax_paid,
                foreign_tax_refund_by_item.get(item_id, ZERO_EUR),
            )
            for item_id, foreign_tax_paid in sorted(foreign_tax_by_item.items())
        ),
        capital_tax_rate=capital_tax_rate,
    )
    net_creditable_foreign_tax_total = q2(
        sum(
            (
                max(ZERO_EUR, foreign_tax_paid - foreign_tax_refund_by_item.get(item_id, ZERO_EUR))
                for item_id, foreign_tax_paid in foreign_tax_by_item.items()
            ),
            ZERO_EUR,
        )
    )

    gross_income_tax_with_teilfreistellung: Decimal = section_32d1["gross_income_tax_with_teilfreistellung"]
    gross_income_tax_no_teilfreistellung: Decimal = section_32d1["gross_income_tax_no_teilfreistellung"]
    foreign_tax_credit_applied_with_teilfreistellung = q2(
        min(foreign_tax_credit_cap, gross_income_tax_with_teilfreistellung)
    )
    foreign_tax_credit_applied_no_teilfreistellung = q2(
        min(foreign_tax_credit_cap, gross_income_tax_no_teilfreistellung)
    )
    income_tax_after_foreign_credit_with_teilfreistellung = q2(
        max(ZERO_EUR, gross_income_tax_with_teilfreistellung - foreign_tax_credit_applied_with_teilfreistellung)
    )
    income_tax_after_foreign_credit_no_teilfreistellung = q2(
        max(ZERO_EUR, gross_income_tax_no_teilfreistellung - foreign_tax_credit_applied_no_teilfreistellung)
    )

    # Per-item credit caps after § 20 Abs. 9 allowance allocation (for treaty exports).
    total_taxable_before_allowance: Decimal = taxable_after_allowance["total_taxable_before_allowance"]
    saver_allowance_used: Decimal = taxable_after_allowance["saver_allowance_used"]
    foreign_tax_credit_cap_after_allowance_by_item: dict[str, Decimal] = {}
    for item_id, foreign_tax_paid in sorted(foreign_tax_by_item.items()):
        item_taxable_after_allowance = _taxable_capital_item_after_saver_allowance_2025(
            q2(foreign_taxable_item_by_key_before_allowance.get(item_id, ZERO_EUR)),
            total_taxable_before_allowance_eur=total_taxable_before_allowance,
            saver_allowance_eur=saver_allowance_used,
        )
        item_net_foreign_tax = max(
            ZERO_EUR,
            foreign_tax_paid - foreign_tax_refund_by_item.get(item_id, ZERO_EUR),
        )
        foreign_tax_credit_cap_after_allowance_by_item[item_id] = q2(
            min(item_net_foreign_tax, item_taxable_after_allowance * capital_tax_rate)
        )
    foreign_tax_credit_cap_after_allowance_total = q2(
        sum(foreign_tax_credit_cap_after_allowance_by_item.values(), ZERO_EUR)
    )
    actual_credit_pool_for_item_exports = q2(
        min(
            foreign_tax_credit_applied_with_teilfreistellung,
            foreign_tax_credit_cap_after_allowance_total,
        )
    )

    return {
        "de.capital.section_32d5_foreign_tax_credit": {
            "foreign_tax_credit_cap": foreign_tax_credit_cap,
            "net_creditable_foreign_tax_total": net_creditable_foreign_tax_total,
            "foreign_tax_credit_applied_with_teilfreistellung": foreign_tax_credit_applied_with_teilfreistellung,
            "foreign_tax_credit_applied_no_teilfreistellung": foreign_tax_credit_applied_no_teilfreistellung,
            "income_tax_after_foreign_credit_with_teilfreistellung": income_tax_after_foreign_credit_with_teilfreistellung,
            "income_tax_after_foreign_credit_no_teilfreistellung": income_tax_after_foreign_credit_no_teilfreistellung,
            "foreign_tax_credit_cap_after_allowance_by_item": foreign_tax_credit_cap_after_allowance_by_item,
            "foreign_tax_credit_cap_after_allowance_total": foreign_tax_credit_cap_after_allowance_total,
            "actual_credit_pool_for_item_exports": actual_credit_pool_for_item_exports,
        }
    }


def de25_19_capital_soli(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # § 4 SolzG 1995: solidarity surcharge on the income tax remaining after the
    # § 32d Abs. 5 foreign-tax credit. Both teilfreistellung versions tracked so
    # the audit captures the InvStG § 20 differential.
    section_32d5 = facts["de.capital.section_32d5_foreign_tax_credit"]
    soli_rate: Decimal = Decimal(str(facts["de.capital.soli_rate"]))
    income_tax_after_foreign_credit_with_teilfreistellung = section_32d5[
        "income_tax_after_foreign_credit_with_teilfreistellung"
    ]
    income_tax_after_foreign_credit_no_teilfreistellung = section_32d5[
        "income_tax_after_foreign_credit_no_teilfreistellung"
    ]
    solidarity_surcharge_with_teilfreistellung = floor_cent(
        income_tax_after_foreign_credit_with_teilfreistellung * soli_rate
    )
    solidarity_surcharge_no_teilfreistellung = floor_cent(
        income_tax_after_foreign_credit_no_teilfreistellung * soli_rate
    )
    capital_tax_total_with_teilfreistellung_before_treaty = q2(
        income_tax_after_foreign_credit_with_teilfreistellung + solidarity_surcharge_with_teilfreistellung
    )
    capital_tax_total_no_teilfreistellung = q2(
        income_tax_after_foreign_credit_no_teilfreistellung + solidarity_surcharge_no_teilfreistellung
    )
    return {
        "de.capital.solidarity_surcharge": {
            "solidarity_surcharge_with_teilfreistellung": solidarity_surcharge_with_teilfreistellung,
            "solidarity_surcharge_no_teilfreistellung": solidarity_surcharge_no_teilfreistellung,
            "capital_tax_total_with_teilfreistellung_before_treaty": capital_tax_total_with_teilfreistellung_before_treaty,
            "capital_tax_total_no_teilfreistellung": capital_tax_total_no_teilfreistellung,
        }
    }


def de25_20_treaty_check(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # DBA-USA Art. 10 / Art. 23 and § 32d Abs. 5 EStG: per-item U.S.-source
    # dividend allocation routed through the post-allowance § 32d(5) credit
    # pool, then § 5 SolzG 1995 ordering of any separate treaty credit (which
    # fails closed; treaty credits must flow through the per-item cap).
    soli_block = facts["de.capital.solidarity_surcharge"]
    section_32d5 = facts["de.capital.section_32d5_foreign_tax_credit"]
    netting = facts["de.capital.after_section_20_6_netting"]
    taxable_after_allowance = facts["de.capital.taxable_after_allowance"]
    treaty_dividend_credit: Decimal = Decimal(str(facts["de.capital.treaty_dividend_credit"]))
    capital_tax_rate: Decimal = Decimal(str(facts["de.capital.capital_tax_rate"]))

    treaty_us_source_dividend_taxable_by_item: dict[str, Decimal] = netting[
        "treaty_us_source_dividend_taxable_by_item"
    ]
    treaty_us_source_dividend_allowed_tax_by_item: dict[str, Decimal] = netting[
        "treaty_us_source_dividend_allowed_tax_by_item"
    ]
    treaty_dividend_input_by_item: dict[str, GermanyTreatyDividendItem2025] = netting[
        "treaty_dividend_input_by_item"
    ]
    foreign_tax_credit_cap_after_allowance_by_item: dict[str, Decimal] = section_32d5[
        "foreign_tax_credit_cap_after_allowance_by_item"
    ]
    foreign_tax_credit_cap_after_allowance_total: Decimal = section_32d5[
        "foreign_tax_credit_cap_after_allowance_total"
    ]
    actual_credit_pool_for_item_exports: Decimal = section_32d5["actual_credit_pool_for_item_exports"]
    total_taxable_before_allowance: Decimal = taxable_after_allowance["total_taxable_before_allowance"]
    saver_allowance_used: Decimal = taxable_after_allowance["saver_allowance_used"]

    treaty_us_source_dividend_precredit_tax = ZERO_EUR
    treaty_us_source_dividend_credit = ZERO_EUR
    treaty_dividend_packet_items: list[GermanyUSTreatyDividendPacketItem2025] = []
    for item_id, item_taxable_before_allowance in sorted(treaty_us_source_dividend_taxable_by_item.items()):
        # DBA-USA Art. 23 + Pub. 514 worksheet lines 17/18: residence-country tax
        # and credit on the same U.S.-source dividend stack must be exported
        # *after* § 20 Abs. 9 EStG allowance ordering and the actual § 32d Abs. 5
        # credit cap, not the pre-allowance item cap.
        item_taxable_after_allowance = _taxable_capital_item_after_saver_allowance_2025(
            item_taxable_before_allowance,
            total_taxable_before_allowance_eur=total_taxable_before_allowance,
            saver_allowance_eur=saver_allowance_used,
        )
        item_precredit_tax = q2(item_taxable_after_allowance * capital_tax_rate)
        item_credit_cap_after_allowance = min(
            treaty_us_source_dividend_allowed_tax_by_item[item_id],
            foreign_tax_credit_cap_after_allowance_by_item.get(item_id, ZERO_EUR),
            item_precredit_tax,
        )
        item_credit = _allocated_applied_credit_2025(
            item_credit_cap_after_allowance,
            total_credit_cap_eur=foreign_tax_credit_cap_after_allowance_total,
            actual_applied_credit_eur=actual_credit_pool_for_item_exports,
        )
        treaty_us_source_dividend_precredit_tax += item_precredit_tax
        treaty_us_source_dividend_credit += item_credit
        item = treaty_dividend_input_by_item[item_id]
        treaty_dividend_packet_items.append(
            GermanyUSTreatyDividendPacketItem2025(
                item_id=item_id,
                owner_slot=item.owner_slot,
                dividend_class=item.dividend_class,
                gross_dividend_eur=q2(item.gross_dividend_eur),
                german_taxable_dividend_eur=q2(item.german_taxable_dividend_eur),
                article_10_source_tax_ceiling_eur=q2(treaty_us_source_dividend_allowed_tax_by_item[item_id]),
                germany_precredit_tax_eur=q2(item_precredit_tax),
                germany_residence_credit_eur=q2(item_credit),
            )
        )

    # § 5 SolzG 1995 ordering of any separate treaty credit (fails closed unless
    # treaty_dividend_credit == 0, since manual treaty credits must flow through
    # § 32d Abs. 5 per-item caps).
    if q2(treaty_dividend_credit) != ZERO_EUR:
        raise NotImplementedError(
            "Manual Germany treaty dividend credits are not supported as a separate second capital credit. "
            "Credit foreign tax through the § 32d(5) per-item cap instead."
        )
    income_tax_after_foreign_credit_with_teilfreistellung = facts[
        "de.capital.section_32d5_foreign_tax_credit"
    ]["income_tax_after_foreign_credit_with_teilfreistellung"]
    solidarity_surcharge_with_teilfreistellung = soli_block["solidarity_surcharge_with_teilfreistellung"]
    solidarity_surcharge_after_treaty = q2(
        max(ZERO_EUR, solidarity_surcharge_with_teilfreistellung - treaty_dividend_credit)
    )
    remaining_credit = q2(max(ZERO_EUR, treaty_dividend_credit - solidarity_surcharge_with_teilfreistellung))
    income_tax_after_treaty = q2(
        max(ZERO_EUR, income_tax_after_foreign_credit_with_teilfreistellung - remaining_credit)
    )

    return {
        "de.capital.treaty_credit_check": {
            "treaty_credit_eur": q2(treaty_dividend_credit),
            "treaty_us_source_dividend_precredit_tax": treaty_us_source_dividend_precredit_tax,
            "treaty_us_source_dividend_credit": treaty_us_source_dividend_credit,
            "treaty_dividend_packet_items": tuple(treaty_dividend_packet_items),
            "solidarity_surcharge_after_treaty": solidarity_surcharge_after_treaty,
            "income_tax_after_treaty": income_tax_after_treaty,
            "income_tax_before_treaty": q2(income_tax_after_foreign_credit_with_teilfreistellung),
            "solidarity_surcharge_before_treaty": q2(solidarity_surcharge_with_teilfreistellung),
        }
    }


def de25_21_final_capital_tax(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    # Final modeled capital tax = post-treaty income tax + post-treaty soli per
    # § 32d Abs. 1/5 EStG and § 4 SolzG 1995 ordering plus the treaty fail-closed
    # check executed in DE25-20.
    treaty = facts["de.capital.treaty_credit_check"]
    return {
        "de.capital.final_tax": q2(treaty["income_tax_after_treaty"] + treaty["solidarity_surcharge_after_treaty"])
    }


_RULE_FUNCTIONS = {
    "DE25-13-CAPITAL-RAW-BUCKETS": de25_13_capital_raw_buckets,
    "DE25-13F-VORABPAUSCHALE": de25_13f_vorabpauschale,
    "DE25-14-FUND-TEILFREISTELLUNG": de25_14_fund_teilfreistellung,
    "DE25-15-SECTION-20-6-NETTING": de25_15_section_20_6_netting,
    "DE25-16-SECTION-20-9-SAVER": de25_16_section_20_9_saver,
    "DE25-17-SECTION-32D1-GROSS-TAX": de25_17_section_32d1_gross_tax,
    "DE25-18-SECTION-32D5-FTC": de25_18_section_32d5_ftc,
    "DE25-19-CAPITAL-SOLI": de25_19_capital_soli,
    "DE25-20-TREATY-CHECK": de25_20_treaty_check,
    "DE25-21-FINAL-CAPITAL-TAX": de25_21_final_capital_tax,
}


def germany_capital_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_capital_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(f"No germany capital calculate function registered for {stage.stage_id}")
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


_GERMANY_CAPITAL_DERIVED_FACT_KEYS = (
    "de.derived.per_symbol_sale_aggregation",
    "de.derived.box_1a_filtered_dividends",
    "de.derived.per_symbol_bank_certificate_buckets",
    "de.derived.source_country_classification",
    "de.derived.foreign_tax_indexing",
    "de.derived.fund_classification",
    "de.derived.vorabpauschale_inputs",
)
"""``de.derived.*`` keys DE25-13 through DE25-21 declare as inputs.

These are the keys the Pipeline 2 boundary needs back from
``derived-facts.json``. Listed explicitly (not derived from the rule
graph) so adding a new derivation stage that DE25-* doesn't yet consume
doesn't accidentally pull a stale key into Pipeline 2's initial facts.
"""


def _build_germany_capital_raw_facts(
    inputs: GermanyCapitalAssessmentInputs2025,
) -> dict[str, Any]:
    """Build the ``de.capital.*`` raw inputs dict (Pipeline 2 side).

    These keys come straight from the dataclass inputs and never live in
    ``derived-facts.json`` — Pipeline 2 always carries them through to
    DE25-13's ``input_fact_keys``. The dict shape pins the contract that
    every key DE25-13 declares as a ``de.capital.*`` input is sourced
    from the inputs dataclass, not from a derivation stage output.
    """
    return {
        "de.capital.sale_facts": inputs.sale_facts,
        "de.capital.income_facts": inputs.income_facts,
        "de.capital.bank_certificates": inputs.bank_certificates,
        "de.capital.treaty_dividend_items": inputs.treaty_dividend_items,
        "de.capital.fund_classification": dict(inputs.fund_classification),
        "de.capital.fund_teilfreistellung_rates": dict(FUND_TEILFREISTELLUNG_RATES_2025),
        "de.capital.dher_stock_gain": inputs.dher_stock_gain_eur,
        "de.capital.stock_loss_carryforward_2024": inputs.stock_loss_carryforward_2024_eur,
        "de.capital.saver_allowance": inputs.saver_allowance_eur,
        "de.capital.other_spouse_capital_before_allowance": inputs.other_spouse_capital_before_allowance_eur,
        "de.capital.capital_tax_rate": inputs.capital_tax_rate,
        "de.capital.soli_rate": inputs.soli_rate,
        "de.capital.treaty_dividend_credit": inputs.treaty_dividend_credit_eur,
        # InvStG § 18 / § 19 Vorabpauschale parameters and per-fund raw inputs.
        # The Basiszinssatz (2.53 % for 2025) and statutory 0.7 factor live
        # in germany_2025_law.py; the Pipeline 2 stage DE25-13F-VORABPAUSCHALE
        # consumes them as declared inputs alongside the derived per-fund
        # index ``de.derived.vorabpauschale_inputs``.
        "de.capital.basiszins": BASISZINS_2025,
        "de.capital.vorabpauschale_basisertrag_factor": VORABPAUSCHALE_BASISERTRAG_FACTOR,
        "de.capital.vorabpauschale_inputs": inputs.vorabpauschale_inputs,
    }


def _load_persisted_germany_derived_facts() -> dict[str, Any] | None:
    """Load ``de.derived.*`` from the active workspace's disk artifact.

    Returns ``None`` if no workspace can be resolved (no ``TAX_*`` env
    vars in scope), so the caller can raise a fail-closed error pointing
    operators at ``run_derivation``. Pre-F-A4 this returned ``None`` for
    several "no on-disk artifact" conditions and the caller fell back to
    an in-memory Pipeline 1 invocation. F-A4 (architecture review,
    ``.review/2026-05-01-final/architecture.md``) removed that fallback
    because it weakened the on-disk Pipeline 1 → Pipeline 2 boundary
    that I13 + the two-pipeline architecture require.

    When the file exists, this is the canonical Pipeline 1 → Pipeline 2
    boundary: DE25-13 reads the persisted shape rather than recomputing
    it, so a Pipeline 1 bug surfaces as a stale ``derived-facts.json``
    rather than as a Pipeline 2 mismatch.

    Authority: § 32d Abs. 5 EStG per-Posten audit trail
    (https://www.gesetze-im-internet.de/estg/__32d.html) and InvStG § 2
    Abs. 6 fund taxonomy
    (https://www.gesetze-im-internet.de/invstg_2018/__2.html) require
    the boundary state stay byte-stable end-to-end.
    """
    import os
    import sys
    from pathlib import Path

    from tax_pipeline.derivation.persistence import (
        derivation_facts_path,
        load_germany_capital_derived_facts,
    )
    from tax_pipeline.year_runtime import active_year_paths

    # ``active_year_paths`` consults TAX_PROJECT_ROOT / TAX_WORKSPACE_ROOT
    # / TAX_YEAR. If none are set we are running outside a pipeline
    # invocation (e.g., a unit test that constructs inputs directly).
    if not os.environ.get("TAX_WORKSPACE_ROOT") and not os.environ.get("TAX_PROJECT_ROOT"):
        return None

    try:
        paths = active_year_paths(Path(__file__), default_year=2025)
    except Exception:
        return None

    facts_path = derivation_facts_path(paths)
    if not facts_path.exists():
        return None

    print(
        f"[germany_capital] reading de.derived.* from {facts_path}",
        file=sys.stderr,
    )
    return load_germany_capital_derived_facts(paths)


def germany_capital_initial_facts_2025(
    inputs: GermanyCapitalAssessmentInputs2025,
    *,
    derived_facts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build DE25-13's initial facts: raw ``de.capital.*`` + derived ``de.derived.*``.

    Per ``docs/invariant-migration-plan.md`` §1.5 / WS-5A: DE25-13 reads
    its derived facts from the persisted ``derived-facts.json`` that
    Pipeline 1 (``run_derivation``) writes. The two-pipeline architecture
    isolates Pipeline 1 bugs (raw-data drift) from Pipeline 2 bugs
    (legal-interpretation drift) by making the on-disk artifact the
    canonical boundary state.

    Disk path: when ``derived-facts.json`` exists in the resolved
    ``YearPaths.derivation_root`` (which the orchestrator's pipeline-
    module ordering guarantees: ``run_derivation`` runs before
    ``germany_model``), this function loads + rehydrates the
    ``de.derived.*`` keys via :func:`load_germany_capital_derived_facts`.

    Test injection: tests that bypass ``run_year`` (e.g., direct calls
    to ``compute_germany_capital_assessment_2025`` from
    ``test_germany_2025_law.py``) materialize the boundary state via
    ``tests/_germany_derived_facts.py:germany_derived_facts_for_inputs``
    and pass the result through the ``derived_facts`` keyword argument.
    The in-memory derivation path is intentionally confined to
    ``tests/`` so production Pipeline 2 never imports the Pipeline 1
    runtime — F-A4 (architecture review) removed the production
    fallback that weakened that boundary.

    Fail-closed: if ``derived_facts`` is not supplied and
    ``derived-facts.json`` is not on disk, this function raises
    ``FileNotFoundError`` pointing operators at ``run_derivation``.
    Silently re-deriving in memory hid Pipeline 1 staleness behind
    Pipeline 2 results.

    Authority: § 32d Abs. 5 EStG per-Posten audit trail (
    https://www.gesetze-im-internet.de/estg/__32d.html), InvStG § 2
    Abs. 6 fund taxonomy
    (https://www.gesetze-im-internet.de/invstg_2018/__2.html), and
    InvStG § 20 partial exemption
    (https://www.gesetze-im-internet.de/invstg_2018/__20.html) — the
    derived facts feed § 32d Abs. 5's per-Posten cap and DE25-14's
    Teilfreistellung application; rigor in this boundary protects both
    citations downstream.
    """
    raw_facts = _build_germany_capital_raw_facts(inputs)

    if derived_facts is not None:
        derived = dict(derived_facts)
    else:
        loaded = _load_persisted_germany_derived_facts()
        if loaded is None:
            # F-A4: fail closed. The in-memory fallback that previously
            # ran here let Pipeline 1 staleness escape detection. The
            # two-pipeline architecture (docs/invariant-migration-plan.md
            # §1.5) requires Pipeline 1 to commit ``derived-facts.json``
            # before Pipeline 2 reads it; tests that bypass ``run_year``
            # must inject derived facts via the ``derived_facts``
            # keyword argument.
            from tax_pipeline.derivation.persistence import (
                derivation_facts_path,
            )
            from tax_pipeline.year_runtime import active_year_paths
            from pathlib import Path
            try:
                paths = active_year_paths(Path(__file__), default_year=2025)
                expected_path = derivation_facts_path(paths)
                location_hint = f" at {expected_path}"
            except Exception:
                location_hint = ""
            raise FileNotFoundError(
                f"derived-facts.json not found{location_hint}. "
                f"Pipeline 1 (Derivation) must run before Pipeline 2 "
                f"(Legal). Run "
                f"`python -m tax_pipeline.pipelines.y2025.run_derivation` "
                f"first, or pass derived_facts= to inject the boundary "
                f"state directly (test scenarios)."
            )
        derived = loaded

    # Splice ``de.derived.*`` into ``de.capital.*``. The two key spaces
    # are disjoint by design (Pipeline 1 outputs vs. Pipeline 2 raw
    # inputs), so ``{**raw, **derived}`` cannot collide.
    return {**raw_facts, **derived}


def germany_capital_initial_fingerprints_2025(initial_facts: Mapping[str, Any]) -> dict[str, str]:
    # Pass the raw value through ``stable_fingerprint``; its ``_fingerprintable``
    # walker canonicalizes Mapping/Set/Decimal/dataclass shapes so that two
    # semantically identical fact dicts inserted in different orders yield the
    # same hash. Using ``repr(value)`` instead would leak Python dict insertion
    # order into the fingerprint and break audit-packet identity.
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_capital_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_capital_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY, execution)
    return execution


def germany_capital_assessment_from_final_facts(
    final_facts: Mapping[str, Any],
    *,
    inputs: GermanyCapitalAssessmentInputs2025,
) -> GermanyCapitalAssessment2025:
    """Project executed final_facts back into the legacy view dataclass.

    Per Phase 2 of the engine restructure, ``GermanyCapitalAssessment2025`` is
    a typed view assembled from rule-graph outputs, not produced by a separate
    compute path.
    """
    raw = final_facts["de.capital.raw_buckets"]
    fund_after = final_facts["de.capital.fund_after_teilfreistellung"]
    netting = final_facts["de.capital.after_section_20_6_netting"]
    taxable_after_allowance = final_facts["de.capital.taxable_after_allowance"]
    section_32d1 = final_facts["de.capital.section_32d1_gross_tax"]
    section_32d5 = final_facts["de.capital.section_32d5_foreign_tax_credit"]
    soli = final_facts["de.capital.solidarity_surcharge"]
    treaty = final_facts["de.capital.treaty_credit_check"]
    final_tax: Decimal = final_facts["de.capital.final_tax"]

    capital_no_teilfreistellung = CapitalTaxAssessment2025(
        taxable_capital_eur=q2(taxable_after_allowance["taxable_before_teilfreistellung"]),
        gross_income_tax_eur=q2(section_32d1["gross_income_tax_no_teilfreistellung"]),
        foreign_tax_credit_eur=q2(section_32d5["foreign_tax_credit_applied_no_teilfreistellung"]),
        income_tax_after_foreign_credit_eur=q2(section_32d5["income_tax_after_foreign_credit_no_teilfreistellung"]),
        solidarity_surcharge_eur=q2(soli["solidarity_surcharge_no_teilfreistellung"]),
        total_tax_eur=q2(soli["capital_tax_total_no_teilfreistellung"]),
    )
    capital_with_teilfreistellung = CapitalTaxAssessment2025(
        taxable_capital_eur=q2(taxable_after_allowance["taxable_after_teilfreistellung"]),
        gross_income_tax_eur=q2(section_32d1["gross_income_tax_with_teilfreistellung"]),
        foreign_tax_credit_eur=q2(section_32d5["foreign_tax_credit_applied_with_teilfreistellung"]),
        income_tax_after_foreign_credit_eur=q2(section_32d5["income_tax_after_foreign_credit_with_teilfreistellung"]),
        solidarity_surcharge_eur=q2(soli["solidarity_surcharge_with_teilfreistellung"]),
        total_tax_eur=q2(soli["capital_tax_total_with_teilfreistellung_before_treaty"]),
    )
    treaty_relieved_capital = TreatyRelievedCapitalTax2025(
        treaty_credit_eur=q2(treaty["treaty_credit_eur"]),
        solidarity_surcharge_before_treaty_eur=q2(treaty["solidarity_surcharge_before_treaty"]),
        solidarity_surcharge_after_treaty_eur=q2(treaty["solidarity_surcharge_after_treaty"]),
        income_tax_before_treaty_eur=q2(treaty["income_tax_before_treaty"]),
        income_tax_after_treaty_eur=q2(treaty["income_tax_after_treaty"]),
        total_tax_after_treaty_eur=q2(final_tax),
    )

    bank_summary = raw["bank_certificate_summary"]
    return GermanyCapitalAssessment2025(
        stock_gain=q2(raw["stock_gain"]),
        dher_stock_gain=q2(inputs.dher_stock_gain_eur),
        stock_gain_after_carryforward=q2(netting["stock_gain_after_carryforward"]),
        stock_loss_carryforward_used=q2(netting["stock_loss_carryforward_used"]),
        stock_loss_carryforward_remaining=q2(netting["stock_loss_carryforward_remaining"]),
        fund_gain=q2(raw["fund_gain"]),
        option_gain=q2(raw["option_gain"]),
        positive_income_total=q2(raw["positive_income_total"]),
        non_fund_positive_income_total=q2(raw["non_fund_positive_income_total"]),
        explicit_foreign_tax_total=q2(netting["explicit_foreign_tax_total"]),
        net_creditable_foreign_tax_total=q2(section_32d5["net_creditable_foreign_tax_total"]),
        foreign_tax_credit_cap_eur=q2(section_32d5["foreign_tax_credit_cap"]),
        equity_fund_total=q2(raw["equity_fund_total"]),
        non_equity_fund_total=q2(raw["non_equity_fund_total"]),
        fund_taxable_after_teilfreistellung_eur=q2(fund_after["fund_taxable_after_teilfreistellung"]),
        saver_allowance_used_eur=q2(taxable_after_allowance["saver_allowance_used"]),
        fund_teilfreistellung_reduction_eur=q2(fund_after["fund_teilfreistellung_reduction"]),
        combined_current_capital_eur=q2(taxable_after_allowance["combined_current_capital"]),
        taxable_before_teilfreistellung_eur=q2(taxable_after_allowance["taxable_before_teilfreistellung"]),
        taxable_after_teilfreistellung_eur=q2(taxable_after_allowance["taxable_after_teilfreistellung"]),
        capital_no_teilfreistellung=capital_no_teilfreistellung,
        capital_with_teilfreistellung=capital_with_teilfreistellung,
        treaty_relieved_capital=treaty_relieved_capital,
        bank_certificate_income_eur=q2(bank_summary["income"]),
        bank_certificate_stock_gain_eur=q2(bank_summary["stock_gain"]),
        bank_certificate_non_stock_income_eur=q2(bank_summary["non_stock_income"]),
        bank_certificate_saver_allowance_used_eur=q2(bank_summary["saver_allowance_used"]),
        bank_certificate_foreign_tax_credited_eur=q2(bank_summary["foreign_tax_credited"]),
        bank_certificate_foreign_tax_not_credited_eur=q2(bank_summary["foreign_tax_not_credited"]),
        domestic_capital_tax_withheld_eur=q2(raw["domestic_capital_tax_withheld"]),
        domestic_capital_soli_withheld_eur=q2(raw["domestic_capital_soli_withheld"]),
        domestic_capital_withholding_credit_eur=q2(
            raw["domestic_capital_tax_withheld"] + raw["domestic_capital_soli_withheld"]
        ),
        treaty_us_source_dividend_gross_eur=q2(netting["treaty_us_source_dividend_gross"]),
        treaty_us_source_dividend_precredit_tax_eur=q2(treaty["treaty_us_source_dividend_precredit_tax"]),
        treaty_us_source_dividend_allowed_us_tax_eur=q2(netting["treaty_us_source_dividend_allowed_us_tax"]),
        treaty_us_source_dividend_credit_eur=q2(treaty["treaty_us_source_dividend_credit"]),
        treaty_dividend_packet_items=treaty["treaty_dividend_packet_items"],
        capital_tax_no_teilfreistellung_eur=q2(soli["capital_tax_total_no_teilfreistellung"]),
        capital_tax_with_teilfreistellung_before_treaty_eur=q2(soli["capital_tax_total_with_teilfreistellung_before_treaty"]),
        capital_tax_with_teilfreistellung_after_treaty_eur=q2(final_tax),
        # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung) — surfaced
        # so the KAP-form projection (DE25-FORM-KAP-PROJECTION) can re-emit
        # it under ``de.kap_inv.line_9_13_eur``.
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        vorabpauschale_taxable_after_teilfreistellung_eur=q2(
            final_facts["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"]
        ),
        # The audit law-order trace remains stage-keyed; the new rule graph is the
        # canonical execution trace, so the legacy ``law_order_stages`` tuple is
        # left at its empty default for callers that still inspect it.
    )


__all__ = [
    "GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY",
    "execute_germany_capital_rule_graph",
    "germany_capital_assessment_from_final_facts",
    "germany_capital_initial_facts_2025",
    "germany_capital_initial_fingerprints_2025",
    "germany_capital_law_rules_2025",
    "de25_13_capital_raw_buckets",
    "de25_14_fund_teilfreistellung",
    "de25_15_section_20_6_netting",
    "de25_16_section_20_9_saver",
    "de25_17_section_32d1_gross_tax",
    "de25_18_section_32d5_ftc",
    "de25_19_capital_soli",
    "de25_20_treaty_check",
    "de25_21_final_capital_tax",
]
