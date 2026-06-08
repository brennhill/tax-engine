"""Per-stage rule functions for the Germany 2025 Anlage KAP form-line projection.

This module is the single execution path for ``DE25-FORM-KAP-PROJECTION``,
the Anlage KAP / KAP-INV form-line projection stage that promotes the
script-level arithmetic at
``tax_pipeline/pipelines/y2025/germany_projections.py:113`` (the
``kap_line_19 = ordinary + stock_pos - stock_neg + option_pos -
option_neg`` computation, plus the per-line bucket roll-ups feeding
the surviving KAP Zeilen and KAP-INV per-fund Zeilen) into a
``LawRule.calculate`` body.

The former 2024 Anlage KAP per-bucket lines for Termingeschäfte
positives, Termingeschäfte negatives, and Uneinbringlichkeit von
Kapitalforderungen are DROPPED for VZ 2025 per the JStG 2024
deletion of § 20 Abs. 6 Sätze 5 und 6 EStG (in Kraft 06.12.2024).
Option-bucket sale results still feed the surviving Zeile 19 via
the ordinary + option_pos - option_neg portion of the sum; they
are no longer surfaced on their own per-bucket form line.
BMF-VERIFIED 2026-05-13 against BMF 16.05.2025
Steuerbescheinigung-Schreiben.

Promoting the projection arithmetic into a stage brings every rendered
EUR amount inside the audit graph: the executed ``StageResult``
fingerprints commit to the per-Zeile outputs, and
``OutputDeclaration.form_line_refs`` declares the bidirectional
contract with the renderer's ``_required_form_line`` reads. This is
WS-4C of ``docs/invariant-migration-plan.md``; it removes the I2 / I5
flags on ``germany_projections.py`` for the KAP-line sites.

Authority:

- § 20 Abs. 1 / Abs. 2 EStG fixes the capital-income classification
  feeding Anlage KAP Zeilen 19-24.
  https://www.gesetze-im-internet.de/estg/__20.html
- § 32d Abs. 1 EStG governs the flat capital-tax surface that Anlage
  KAP collects on Zeile 41 (foreign tax).
  https://www.gesetze-im-internet.de/estg/__32d.html
- InvStG § 20 governs the fund-related Teilfreistellung / fund-type
  taxonomy feeding Anlage KAP-INV Zeilen 4 / 8 / 14 / 26.
  https://www.gesetze-im-internet.de/invstg_2018/__20.html
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.stages import (
    LawRule,
    RuleGraphExecution,
    execute_rule_graph,
)
from tax_pipeline.y2025.germany_law import (
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
    fund_type_for_symbol_2025,
    q2,
)
from tax_pipeline.y2025.germany_stages import germany_kap_projection_law_stages_2025
from tax_pipeline.pipeline_context import set_pipeline_context_value


GERMANY_KAP_PROJECTION_EXECUTION_CONTEXT_KEY = (
    "germany_kap_projection_2025.rule_graph_execution"
)
"""Pipeline-context key under which ``execute_germany_kap_projection_rule_graph``
stashes the executed ``RuleGraphExecution`` for in-memory hand-off
(mirrors the per-jurisdiction context keys used by the ordinary /
capital / final / treaty / U.S. graphs)."""


DE25_FORM_KAP_PROJECTION_STAGE_ID = "DE25-FORM-KAP-PROJECTION"


ZERO_EUR = Decimal("0.00")


def de25_form_kap_projection(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Compute the Anlage KAP / KAP-INV form-line projection.

    Legal authority and ordering:

    - § 20 Abs. 1 EStG (Kapitalertraege) classifies dividends, interest,
      and substitute payments into the non-fund ordinary capital-income
      bucket that lands on Anlage KAP Zeile 19.
      https://www.gesetze-im-internet.de/estg/__20.html
    - § 20 Abs. 2 EStG (Veraeusserungen) supplies the stock-sale and
      option/Termingeschaeft gains. Per the JStG 2024 deletion of
      § 20 Abs. 6 Sätze 5 und 6 EStG (in Kraft 06.12.2024), VZ 2025
      Anlage KAP no longer carries the former 2024 per-bucket
      Termingeschäfte gain / loss lines or the Uneinbringlichkeit
      line; option-bucket sale results net into the surviving
      Zeile 19 sum (= stock-positives Z20 + the dropped former
      Z21/Z22 plus stock-negatives Z23, NOW only stock-positives Z20
      + non-fund ordinary + option_pos - option_neg feeding Z19
      directly). BMF-VERIFIED 2026-05-13 against
      https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf .
    - § 32d Abs. 1 EStG (Abgeltungsteuer) defines the flat capital-tax
      surface that Anlage KAP collects on Zeile 41 (foreign tax).
      https://www.gesetze-im-internet.de/estg/__32d.html
    - InvStG § 20 (Teilfreistellung) defines the Aktienfonds /
      sonstige Investmentfonds split feeding KAP-INV Zeilen 4 / 8 /
      14 / 26.
      https://www.gesetze-im-internet.de/invstg_2018/__20.html

    The body mirrors the historical projection helper (now thin shim)
    so the rendered Zeile values remain byte-identical: the only change
    is that each value is now a fingerprinted stage output rather than
    a script-level Decimal.
    """
    foreign_tax_1099 = q2(Decimal(str(facts["de.kap.foreign_tax_1099_eur"])))
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...] = facts["de.capital.sale_facts"]
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...] = facts["de.capital.income_facts"]
    fund_classification: dict[str, str] = dict(facts["de.capital.fund_classification"])
    dher_stock_gain_eur = Decimal(str(facts["de.capital.dher_stock_gain"]))
    # InvStG § 19 Vorabpauschale (laufender Ertrag, post-§ 20 Teilfreistellung)
    # lands on Anlage KAP-INV Zeilen 9-13. The legal arithmetic happened
    # inside DE25-13F-VORABPAUSCHALE; this projection only re-publishes the
    # value under a `de.kap_inv.*` key so the renderer's _required_form_line
    # consumer reads it through the same channel as the other Zeilen.
    # https://www.gesetze-im-internet.de/invstg_2018/__19.html
    vorabpauschale_zeile_9_13 = q2(
        Decimal(
            str(facts["de.capital.vorabpauschale_taxable_after_teilfreistellung_eur"])
        )
    )

    ordinary = ZERO_EUR
    stock_pos = ZERO_EUR
    stock_neg = ZERO_EUR
    option_pos = ZERO_EUR
    option_neg = ZERO_EUR
    fund_income_akt = ZERO_EUR
    fund_income_sonst = ZERO_EUR
    fund_sales_akt = ZERO_EUR
    fund_sales_sonst = ZERO_EUR
    per_fund: dict[str, dict[str, Any]] = {}

    # § 20 Abs. 1 EStG bucket roll-up for income facts. Foreign-tax
    # rows are excluded (they feed Zeile 41 separately via the 1099
    # input, not Zeile 19). Fund_like substitute_payment is treated as
    # ordinary income per BMF guidance on Wertpapierleihe substitute
    # payments.
    for fact in income_facts:
        amt = Decimal(str(fact.eur_amount))
        kind = str(fact.kind).strip()
        bucket = str(fact.asset_bucket).strip()
        sym = str(fact.symbol).strip().upper()
        if kind == "foreign_tax":
            continue
        if bucket != "fund_like":
            ordinary += amt
            continue
        if kind == "substitute_payment":
            ordinary += amt
            continue

        fund_type = (
            "aktienfonds"
            if fund_type_for_symbol_2025(sym, fund_classification)
            in {"aktienfonds", "equity"}
            else "sonstige"
        )
        if sym not in per_fund:
            per_fund[sym] = {
                "fund_type": fund_type,
                "income_eur": ZERO_EUR,
                "sale_result_eur": ZERO_EUR,
            }
        per_fund[sym]["income_eur"] = per_fund[sym]["income_eur"] + amt
        if fund_type == "sonstige":
            fund_income_sonst += amt
        else:
            fund_income_akt += amt

    # § 20 Abs. 2 EStG bucket roll-up for sale facts. Stock and option
    # buckets sign-split into pos/neg sub-totals so KAP Zeilen 20-24
    # carry the gross gains and losses separately. Fund_like sales feed
    # the InvStG § 20 Aktienfonds vs. sonstige split.
    for fact in sale_facts:
        gain = Decimal(str(fact.gain_eur_matched))
        bucket = str(fact.asset_bucket).strip()
        sym = str(fact.symbol).strip().upper()
        if bucket == "stock":
            if gain >= 0:
                stock_pos += gain
            else:
                stock_neg += -gain
        elif bucket == "option":
            if gain >= 0:
                option_pos += gain
            else:
                option_neg += -gain
        elif bucket == "fund_like":
            fund_type = (
                "aktienfonds"
                if fund_type_for_symbol_2025(sym, fund_classification)
                in {"aktienfonds", "equity"}
                else "sonstige"
            )
            if sym not in per_fund:
                per_fund[sym] = {
                    "fund_type": fund_type,
                    "income_eur": ZERO_EUR,
                    "sale_result_eur": ZERO_EUR,
                }
            per_fund[sym]["sale_result_eur"] = per_fund[sym]["sale_result_eur"] + gain
            if fund_type == "sonstige":
                fund_sales_sonst += gain
            else:
                fund_sales_akt += gain

    # § 19a EStG dher_stock_gain (Shareworks equity-comp release) folds
    # into the stock-sale sign bucket so KAP Zeilen 20/23 mirror the
    # capital-side recognition.
    if dher_stock_gain_eur >= 0:
        stock_pos += dher_stock_gain_eur
    else:
        stock_neg += -dher_stock_gain_eur

    # § 20 Abs. 1 / Abs. 2 EStG net non-fund foreign capital income on
    # Anlage KAP Person 1 Zeile 19. This is the headline KAP-line value
    # that the historical script-level arithmetic at
    # ``germany_projections.py:113`` produced; promoting it into the
    # rule graph is the I2 / I5 progress condition for WS-4C.
    kap_line_19 = ordinary + stock_pos - stock_neg + option_pos - option_neg

    # Per-fund summary rows for the KAP-INV per-fund support CSV. The
    # per-symbol amounts retain Decimal precision; the renderer
    # quantizes to cents at write time. Sorting by symbol guarantees
    # deterministic iteration / fingerprint output.
    fund_rows: list[dict[str, Any]] = []
    for sym in sorted(per_fund):
        record = per_fund[sym]
        fund_rows.append(
            {
                "symbol": sym,
                "fund_type": str(record["fund_type"]),
                "income_eur": q2(Decimal(str(record["income_eur"]))),
                "sale_result_eur": q2(Decimal(str(record["sale_result_eur"]))),
                "combined_eur": q2(
                    Decimal(str(record["income_eur"]))
                    + Decimal(str(record["sale_result_eur"]))
                ),
            }
        )

    # JStG 2024 (06.12.2024) deleted § 20 Abs. 6 Sätze 5 und 6 EStG, so
    # VZ 2025 Anlage KAP drops the former 2024 per-bucket lines for
    # Termingeschäfte positives, Termingeschäfte negatives, and
    # Uneinbringlichkeit von Kapitalforderungen. option_pos / option_neg
    # still flow into the surviving Zeile 19 via the kap_line_19 sum
    # above but are no longer emitted as their own output_keys.
    # BMF-VERIFIED 2026-05-13 against BMF 16.05.2025
    # Steuerbescheinigung-Schreiben:
    # https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
    return {
        "de.kap.line_19_eur": q2(kap_line_19),
        "de.kap.line_20_eur": q2(stock_pos),
        "de.kap.line_23_eur": q2(stock_neg),
        "de.kap.line_41_eur": q2(foreign_tax_1099),
        "de.kap_inv.line_4_eur": q2(fund_income_akt),
        "de.kap_inv.line_8_eur": q2(fund_income_sonst),
        # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung), passed
        # through unchanged from DE25-13F-VORABPAUSCHALE.
        "de.kap_inv.line_9_13_eur": vorabpauschale_zeile_9_13,
        "de.kap_inv.line_14_eur": q2(fund_sales_akt),
        "de.kap_inv.line_26_eur": q2(fund_sales_sonst),
        "de.kap_inv.fund_rows": tuple(fund_rows),
    }


_RULE_FUNCTIONS = {
    DE25_FORM_KAP_PROJECTION_STAGE_ID: de25_form_kap_projection,
}


def germany_kap_projection_law_rules_2025() -> tuple[LawRule, ...]:
    stages = germany_kap_projection_law_stages_2025()
    rules: list[LawRule] = []
    for stage in stages:
        calculate = _RULE_FUNCTIONS.get(stage.stage_id)
        if calculate is None:
            raise ValueError(
                f"No germany kap-projection calculate function registered for {stage.stage_id}"
            )
        rules.append(
            LawRule(
                stage=stage,
                implementation_ref=f"{__name__}:{calculate.__name__}",
                calculate=calculate,
            )
        )
    return tuple(rules)


def germany_kap_projection_initial_facts_2025(
    *,
    foreign_tax_1099_eur: Decimal,
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...],
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...],
    fund_classification: Mapping[str, str],
    dher_stock_gain_eur: Decimal,
    vorabpauschale_taxable_after_teilfreistellung_eur: Decimal,
) -> dict[str, Any]:
    """Assemble the initial-fact dict for ``execute_germany_kap_projection_rule_graph``.

    Inputs (all sourced from the existing germany_capital pipeline /
    loaders; see ``tax_pipeline/pipelines/y2025/germany_loaders.py`` and
    ``germany_2025_inputs.py``):

    - ``foreign_tax_1099_eur`` — the 1099 foreign-tax EUR amount that
      lands on Anlage KAP Zeile 41 (gross, before § 32d Abs. 5 cap).
    - ``sale_facts`` — per-symbol sale facts from
      ``capital-sales-detail.csv``; the projection sign-splits stock
      and option buckets onto Zeilen 20/21/23/24.
    - ``income_facts`` — per-symbol income facts from
      ``income-cashflows.csv``; the projection rolls non-fund_like
      income (excluding ``foreign_tax`` rows) into the Zeile 19
      ordinary bucket.
    - ``fund_classification`` — InvStG § 20 fund taxonomy.
    - ``dher_stock_gain_eur`` — Shareworks equity-comp capital sidecar
      result (§ 19a EStG → § 20 Abs. 2 EStG).
    - ``vorabpauschale_taxable_after_teilfreistellung_eur`` — InvStG
      § 19 Vorabpauschale (post-§ 20 Teilfreistellung) computed by
      DE25-13F-VORABPAUSCHALE; this projection re-emits it under
      ``de.kap_inv.line_9_13_eur`` for the renderer.
      https://www.gesetze-im-internet.de/invstg_2018/__19.html
    """
    return {
        "de.kap.foreign_tax_1099_eur": foreign_tax_1099_eur,
        "de.capital.sale_facts": sale_facts,
        "de.capital.income_facts": income_facts,
        "de.capital.fund_classification": dict(fund_classification),
        "de.capital.dher_stock_gain": dher_stock_gain_eur,
        "de.capital.vorabpauschale_taxable_after_teilfreistellung_eur": (
            vorabpauschale_taxable_after_teilfreistellung_eur
        ),
    }


def germany_kap_projection_initial_fingerprints_2025(
    initial_facts: Mapping[str, Any],
) -> dict[str, str]:
    return {
        key: stable_fingerprint({"fact_key": key, "value": value})
        for key, value in initial_facts.items()
    }


def execute_germany_kap_projection_rule_graph(
    initial_facts: Mapping[str, Any],
    *,
    input_fingerprints: Mapping[str, str] | None = None,
) -> RuleGraphExecution:
    execution = execute_rule_graph(
        dict(initial_facts),
        germany_kap_projection_law_rules_2025(),
        initial_fingerprints=input_fingerprints,
    )
    set_pipeline_context_value(
        GERMANY_KAP_PROJECTION_EXECUTION_CONTEXT_KEY, execution
    )
    return execution


__all__ = [
    "DE25_FORM_KAP_PROJECTION_STAGE_ID",
    "GERMANY_KAP_PROJECTION_EXECUTION_CONTEXT_KEY",
    "de25_form_kap_projection",
    "execute_germany_kap_projection_rule_graph",
    "germany_kap_projection_initial_facts_2025",
    "germany_kap_projection_initial_fingerprints_2025",
    "germany_kap_projection_law_rules_2025",
]
