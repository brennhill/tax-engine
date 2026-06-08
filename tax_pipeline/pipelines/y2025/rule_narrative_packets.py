from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from decimal import Decimal

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.io import AuditEncoder
from tax_pipeline.core.narrative import NarrativeFormLine, NarrativeMathStep, NarrativeValue, RuleNarrative
from tax_pipeline.core.stages import LawRule, LawStage, StageResult, execute_rule_graph
from tax_pipeline.y2025.germany_law import (
    BMF_PAP_2025_URL,
    ESTG_25_URL,
    ESTG_26_URL,
    ESTG_26B_URL,
    ESTG_32A_URL,
    ESTG_32D_URL,
    SOLZG_4_URL,
)
from tax_pipeline.y2025.us_law import (
    IRS_GERMANY_TECH,
    IRS_I1040,
    IRS_I1116,
    IRS_I8960,
    IRS_P514,
    USC_1411_URL,
    USC_6012_URL,
    USC_6013_URL,
)
from tax_pipeline.y2025.germany_stages import (
    germany_capital_law_stages_2025,
    germany_final_law_stages_2025,
    germany_kap_projection_law_stages_2025,
    germany_ordinary_law_stages_2025,
)
from tax_pipeline.y2025.germany_capital_rules import GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.germany_final_rules import GERMANY_FINAL_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.germany_kap_projection_rules import (
    GERMANY_KAP_PROJECTION_EXECUTION_CONTEXT_KEY,
)
from tax_pipeline.y2025.germany_ordinary_rules import GERMANY_ORDINARY_EXECUTION_CONTEXT_KEY
from tax_pipeline.pipeline_context import get_pipeline_context_value
from tax_pipeline.y2025.treaty_rules import TREATY_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.us_rules import US_EXECUTION_CONTEXT_KEY
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.us_stages import usa_law_stages_2025


def _value(label: str, value: str, key: str, *, source: str = "final-legal-output.json", note: str = "") -> NarrativeValue:
    return NarrativeValue(label, value, key, source, note)


def _step(statement: str, formula: str, result: str, *, rounding_note: str = "") -> NarrativeMathStep:
    return NarrativeMathStep(statement, formula, result, rounding_note)


def _line(form: str, line: str, value: str, *, note: str = "", url: str = "") -> NarrativeFormLine:
    return NarrativeFormLine(form, line, value, note, url)


def _format_value(value: object) -> str:
    if isinstance(value, (dict, list, tuple, frozenset, set)):
        return json.dumps(value, sort_keys=True, cls=AuditEncoder)
    if isinstance(value, Decimal):
        return format(value, "f")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json.dumps(dataclasses.asdict(value), sort_keys=True, cls=AuditEncoder)
    # NOTE (L4, 2026-05-01 correctness review): unrecognized types fall back
    # to ``str(value)``, whose output is the implementing class's __str__ /
    # __repr__. That is not guaranteed to be stable across Python versions
    # for arbitrary types, so an unfamiliar value reaching this branch is a
    # latent fingerprint-stability hazard. The current rule-graph contract
    # only routes Decimals, dataclasses, dicts, lists, tuples, sets, and
    # primitives through this formatter, so the fallback is gated by
    # upstream typing rather than by an explicit assertion here.
    return str(value)


def _q2(value: object) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _q2_str(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _sum_decimal_strings(*values: object) -> str:
    return _q2_str(sum((_q2(value) for value in values), Decimal("0.00")))


def _subtract_decimal_strings(left: object, right: object) -> str:
    return _q2_str(_q2(left) - _q2(right))


def _execute_stage_projection(
    stages: Sequence[LawStage],
    *,
    initial_values: Mapping[str, object],
    stage_values: Mapping[str, object],
) -> tuple[StageResult, ...]:
    missing_stage_values = [stage.stage_id for stage in stages if stage.stage_id not in stage_values]
    if missing_stage_values:
        raise ValueError(f"missing stage output values: {missing_stage_values}")
    rules = tuple(
        LawRule(
            stage=stage,
            implementation_ref=f"{__name__}:{stage.stage_id}",
            calculate=lambda facts, stage=stage: {stage.output_keys[0]: stage_values[stage.stage_id]},
        )
        for stage in stages
    )
    return execute_rule_graph(
        dict(initial_values),
        rules,
        initial_fingerprints={
            key: stable_fingerprint({"fact_key": key, "value": value})
            for key, value in initial_values.items()
        },
    ).stage_results


def _stage_rule(stage: LawStage, result: StageResult, *, country: str, language: str) -> dict:
    if result.stage_id != stage.stage_id:
        raise ValueError(f"StageResult {result.stage_id} does not belong to {stage.stage_id}")
    stage.validate_result(result)
    template_id = stage.narrative_templates.get(language)
    if not template_id:
        raise ValueError(f"{stage.stage_id} has no narrative template for language {language!r}")
    input_label = "Eingabe" if language == "de" else "Input"
    output_label = "Ausgabe" if language == "de" else "Output"
    form_label = "Formular-/Audit-Ziel" if language == "de" else "Form/audit destination"
    input_values = tuple(
        _value(
            input_label,
            _format_value(result.input_values[key]),
            key,
            source="executed-stage-result",
            note=f"input fingerprint {result.input_fingerprints[key]}",
        )
        for key in stage.input_fact_keys
    )
    output_values = tuple(
        _value(
            output_label,
            _format_value(result.outputs[key]),
            key,
            source="executed-stage-result",
            note=f"output fingerprint {result.output_fingerprints[key]}",
        )
        for key in stage.output_keys
    )
    packet = _rule(
        rule_id=stage.stage_id,
        country=country,
        language=language,
        template_id=template_id,
        title=f"{stage.stage_id}: {stage.legal_refs[0]}",
        legal_refs=stage.legal_refs,
        authority_urls=stage.authority_urls,
        inputs=input_values,
        math_steps=(
            _step(
                stage.law_order_note,
                stage.legal_formula,
                "; ".join(f"{value.key} = {value.value}" for value in output_values),
                rounding_note="; ".join(result.precision_notes[key] for key in stage.output_keys),
            ),
        ),
        outputs=output_values,
        form_lines=tuple(
            _line(
                ref,
                "stage output",
                "; ".join(f"{value.key} = {value.value}" for value in output_values),
                note=form_label,
                url=(
                    stage.form_line_urls[idx]
                    if stage.form_line_urls and idx < len(stage.form_line_urls)
                    else ""
                ),
            )
            for idx, ref in enumerate(stage.form_line_refs)
        ),
    )
    # WS-5C: thread the executor's StageResult fingerprints directly into
    # the narrative packet so the legal-execution-graph can reference them
    # verbatim, instead of recomputing a parallel third-domain hash chain
    # over the narrative dict shape (architecture review's net-new finding,
    # see docs/invariant-migration-plan.md §7 WS-5C).
    packet["stage_input_fingerprints"] = dict(result.input_fingerprints)
    packet["stage_output_fingerprints"] = dict(result.output_fingerprints)
    return packet


def _with_missing_stage_rules(
    rules: Sequence[dict],
    stages: Sequence[LawStage],
    *,
    country: str,
    language: str,
    stage_results: Sequence[StageResult] = (),
) -> list[dict]:
    result = list(rules)
    declared_stage_ids = {stage.stage_id for stage in stages}
    supplemental_stage_reuse = sorted(
        str(rule.get("rule_id", ""))
        for rule in result
        if str(rule.get("rule_id", "")) in declared_stage_ids
    )
    if supplemental_stage_reuse:
        raise ValueError(
            f"{country}-{language} supplemental narrative reuses declared LawStage rule_id: {supplemental_stage_reuse}"
        )
    existing_rule_ids: set[str] = set()
    for rule in result:
        rule_id = str(rule.get("rule_id", ""))
        if rule_id in existing_rule_ids:
            raise ValueError(f"{country}-{language} duplicate narrative rule_id: {rule_id}")
        existing_rule_ids.add(rule_id)
    result_by_stage = {stage_result.stage_id: stage_result for stage_result in stage_results}
    for stage in stages:
        if stage.stage_id in existing_rule_ids:
            raise ValueError(f"{country}-{language} duplicate narrative rule_id: {stage.stage_id}")
        stage_result = result_by_stage.get(stage.stage_id)
        if stage_result is None:
            raise ValueError(f"{country}-{language} missing executed StageResult for {stage.stage_id}")
        result.append(_stage_rule(stage, stage_result, country=country, language=language))
        existing_rule_ids.add(stage.stage_id)
    return result


def _trace_amount(rows: Sequence[dict], step: str, amount_key: str) -> str:
    matches = [row for row in rows if row.get("step") == step]
    if not matches:
        raise FileNotFoundError(f"Missing narrative trace row: {step}")
    if len(matches) > 1:
        raise ValueError(f"Expected exactly one narrative trace row for {step}")
    return str(matches[0][amount_key])


def _rule(
    *,
    rule_id: str,
    country: str,
    language: str,
    template_id: str,
    title: str,
    legal_refs: Sequence[str],
    authority_urls: Sequence[str],
    inputs: Sequence[NarrativeValue],
    math_steps: Sequence[NarrativeMathStep],
    outputs: Sequence[NarrativeValue],
    form_lines: Sequence[NarrativeFormLine],
) -> dict:
    return RuleNarrative(
        rule_id=rule_id,
        country=country,
        language=language,
        template_id=template_id,
        title=title,
        legal_refs=tuple(legal_refs),
        authority_urls=tuple(authority_urls),
        inputs=tuple(inputs),
        math_steps=tuple(math_steps),
        outputs=tuple(outputs),
        form_lines=tuple(form_lines),
    ).to_dict()


def _germany_facts(forms: dict, *, language: str) -> dict:
    results = forms["results"]
    ordinary = results["ordinary"]
    capital = results["capital"]
    refunds = results["refunds"]
    title = "Grunddaten" if language == "de" else "Germany basic facts"
    labels = {
        "filing": "Veranlagungsart" if language == "de" else "Filing posture",
        "taxable": "Zu versteuerndes Einkommen" if language == "de" else "Taxable income",
        "stock": "Aktiengewinne" if language == "de" else "Stock gains",
        "fund": "Fondsgewinne" if language == "de" else "Fund gains",
        "foreign_tax": "Gezahlte auslaendische Steuer" if language == "de" else "Foreign tax paid",
        "final": "Endergebnis Erstattung/Nachzahlung" if language == "de" else "Final target refund/balance",
        "statement": (
            "Die validierten Deutschland-Fakten werden nach Parsing, Normalisierung und Rechtsmodell gesammelt."
            if language == "de"
            else "Collect validated Germany facts after parsing, normalization, and legal model execution."
        ),
        "formula": "nur validierter Final Output; keine Steuerberechnung im Renderer" if language == "de" else "validated final output only; no renderer-side tax calculation",
    }
    return _rule(
        rule_id="DE25-FACTS",
        country="DE",
        language=language,
        template_id="DE25-FACTS",
        title=title,
        legal_refs=("§ 25 EStG", "§ 26 EStG"),
        authority_urls=(ESTG_25_URL, ESTG_26_URL),
        inputs=(
            _value(labels["filing"], ordinary["filing_posture"], "de.ordinary.filing_posture"),
            _value(labels["taxable"], f"{ordinary['joint_taxable_income_eur']} EUR", "de.ordinary.joint_taxable_income_eur"),
            _value(labels["stock"], f"{capital['stock_gain_eur']} EUR", "de.capital.stock_gain_eur"),
            _value(labels["fund"], f"{capital['fund_gain_eur']} EUR", "de.capital.fund_gain_eur"),
            _value(labels["foreign_tax"], f"{capital['explicit_foreign_tax_total_eur']} EUR", "de.capital.explicit_foreign_tax_total_eur"),
        ),
        math_steps=(
            _step(
                labels["statement"],
                labels["formula"],
                f"{refunds['final_target_refund_eur']} EUR",
            ),
        ),
        outputs=(
            _value(labels["final"], f"{refunds['final_target_refund_eur']} EUR", "de.refunds.final_target_refund_eur"),
        ),
        form_lines=(
            _line(
                "ELSTER / Germany forms package" if language == "en" else "ELSTER / Deutschland-Formularpaket",
                "summary anchor" if language == "en" else "Ergebnisanker",
                f"{refunds['final_target_refund_eur']} EUR",
            ),
        ),
    )


def _germany_split_tariff(forms: dict, *, language: str) -> dict:
    ordinary = forms["results"]["ordinary"]
    filing_posture = ordinary["filing_posture"]
    is_joint = filing_posture == "married_joint"
    labels = {
        "filing": "Veranlagungsart" if language == "de" else "Filing posture",
        "taxable": "Zu versteuerndes Einkommen" if language == "de" else "Taxable income",
        "statement": (
            "Der Tarif fuer 2025 wird anhand der Veranlagungsart angewendet."
            if language == "de"
            else "Apply the 2025 tariff selected by the filing posture."
        ),
        "formula": (
            "zusammen: 2 * Grundtarif(zvE / 2)"
            if language == "de" and is_joint
            else "Grundtarif(zvE)"
            if language == "de"
            else "married_joint: 2 * basic_tax(zvE / 2)"
            if is_joint
            else "basic_tax(taxable income)"
        ),
        "rounding": (
            "Die Tarifberechnung folgt der Euro-Rundung des BMF-PAP 2025."
            if language == "de"
            else "The tariff implementation follows the BMF 2025 PAP euro-rounding sequence."
        ),
        "output": "Einkommensteuer" if language == "de" else "Income tax",
    }
    return _rule(
        rule_id="DE25-NARRATIVE-TARIFF",
        country="DE",
        language=language,
        template_id="DE25-NARRATIVE-TARIFF",
        title=(
            "Splittingtarif" if language == "de" and is_joint
            else "Grundtarif" if language == "de"
            else "Splitting tariff" if is_joint
            else "Basic income tax tariff"
        ),
        legal_refs=(
            ("§ 26b EStG", "§ 32a Abs. 1 und 5 EStG", "BMF Programmablaufplan 2025")
            if is_joint
            else ("§ 32a Abs. 1 EStG", "BMF Programmablaufplan 2025")
        ),
        authority_urls=(
            (
                ESTG_26B_URL,
                ESTG_32A_URL,
                BMF_PAP_2025_URL,
            )
            if is_joint
            else (ESTG_32A_URL, BMF_PAP_2025_URL)
        ),
        inputs=(
            _value(labels["filing"], ordinary["filing_posture"], "de.ordinary.filing_posture"),
            _value(labels["taxable"], f"{ordinary['joint_taxable_income_eur']} EUR", "de.ordinary.joint_taxable_income_eur"),
        ),
        math_steps=(
            _step(
                labels["statement"],
                labels["formula"],
                f"{ordinary['joint_income_tax_eur']} EUR",
                rounding_note=labels["rounding"],
            ),
        ),
        outputs=(
            _value(labels["output"], f"{ordinary['joint_income_tax_eur']} EUR", "de.ordinary.joint_income_tax_eur"),
        ),
        form_lines=(
            _line("ELSTER Einkommensteuerberechnung", "tarifliche Einkommensteuer", f"{ordinary['joint_income_tax_eur']} EUR"),
        ),
    )


def _germany_capital_ftc(forms: dict, *, language: str) -> dict:
    capital = forms["results"]["capital"]
    labels = {
        "before_tax": "Kapitalertragsteuer vor Anrechnung" if language == "de" else "Capital income tax before foreign tax",
        "foreign_tax": "Gezahlte auslaendische Steuer" if language == "de" else "Foreign tax paid",
        "net_foreign_tax": "Netto anrechenbare auslaendische Steuer" if language == "de" else "Net creditable foreign tax after refund entitlement",
        "cap": "Anrechnungshoechstbetrag" if language == "de" else "Foreign tax credit cap",
        "credit": "Angerechnete auslaendische Steuer" if language == "de" else "Foreign tax credit applied",
        "statement": (
            "Die auslaendische Steuer wird auf die deutsche Steuer fuer dieselben Kapitalertraege begrenzt."
            if language == "de"
            else "Limit foreign tax credit to the domestic tax attributable to the same capital income."
        ),
        "formula": (
            "Anrechnung = min(Netto-auslandssteuer nach Erstattungsanspruch, Hoechstbetrag je Einzelposten/Quelle)"
            if language == "de"
            else "credit = min(net foreign tax after refund entitlement, per-item/source cap), limited again by aggregate §32d(1) tax"
        ),
        "post_credit_statement": "Die Kapitalertragsteuer wird nach der Anrechnung fortgefuehrt." if language == "de" else "Carry the remaining capital income tax into SolzG and treaty checks.",
        "post_credit_formula": "Reststeuer = Steuer vor Anrechnung - Anrechnung" if language == "de" else "remaining capital tax = gross tax - applied credit",
        "final_statement": "Danach werden SolZ und Treaty-Pruefung angewendet." if language == "de" else "Compute final capital tax after SolzG and treaty check",
        "final_formula": "final = Steuer nach Anrechnung + SolZ nach Treaty-Pruefung" if language == "de" else "final = post-credit income tax + post-credit SolzG after treaty check",
        "output": "Kapitalsteuer nach Anrechnungs-/Treaty-Pruefung" if language == "de" else "Capital tax after foreign-tax/treaty check",
        "note": (
            "Gezahlte auslaendische Steuer vor Erstattungsanspruch und Hoechstbetragspruefung; nicht automatisch die angerechnete Steuer."
            if language == "de"
            else "Foreign tax paid before refund entitlement and credit-cap review; not automatically the applied credit."
        ),
    }
    credit_applied = capital["foreign_tax_credit_applied_eur"]
    return _rule(
        rule_id="DE25-NARRATIVE-CAPITAL-FTC",
        country="DE",
        language=language,
        template_id="DE25-NARRATIVE-CAPITAL-FTC",
        title=(
            "Auslaendische Steuer auf Kapitalertraege"
            if language == "de"
            else "Foreign tax credit for capital income"
        ),
        legal_refs=("§ 32d Abs. 1 EStG", "§ 32d Abs. 5 EStG", "§ 4 SolzG 1995"),
        authority_urls=(ESTG_32D_URL, SOLZG_4_URL),
        inputs=(
            _value(labels["before_tax"], f"{capital['capital_income_tax_with_teilfreistellung_eur']} EUR", "de.capital.capital_income_tax_with_teilfreistellung_eur"),
            _value(labels["foreign_tax"], f"{capital['explicit_foreign_tax_total_eur']} EUR", "de.capital.explicit_foreign_tax_total_eur"),
            _value(labels["net_foreign_tax"], f"{capital['net_creditable_foreign_tax_total_eur']} EUR", "de.capital.net_creditable_foreign_tax_total_eur"),
            _value(labels["cap"], f"{capital['foreign_tax_credit_cap_eur']} EUR", "de.capital.foreign_tax_credit_cap_eur"),
        ),
        math_steps=(
            _step(
                "§ 32d(5) credit limit" if language == "en" else "§ 32d Abs. 5 Anrechnungshoechstbetrag",
                labels["formula"],
                f"{credit_applied} EUR",
            ),
            _step(
                "Apply § 32d(5) foreign-tax credit" if language == "en" else "§ 32d Abs. 5 Anrechnung anwenden",
                labels["post_credit_formula"],
                f"{capital['capital_income_tax_after_foreign_credit_eur']} EUR",
            ),
            _step(
                labels["final_statement"],
                labels["final_formula"],
                f"{capital['capital_tax_with_teilfreistellung_after_treaty_eur']} EUR",
            ),
        ),
        outputs=(
            _value(labels["credit"], f"{credit_applied} EUR", "de.capital.foreign_tax_credit_applied_eur"),
            _value(labels["output"], f"{capital['capital_tax_with_teilfreistellung_after_treaty_eur']} EUR", "de.capital.capital_tax_with_teilfreistellung_after_treaty_eur"),
        ),
        form_lines=(
            _line("Anlage KAP", "Zeile 41" if language == "de" else "line 41", f"{capital['explicit_foreign_tax_total_eur']} EUR", note=labels["note"]),
        ),
    )


def _usa_facts(forms: dict) -> dict:
    tax = forms["tax_estimate"]
    capital = forms["capital_results"]["capital"]
    income = forms["capital_results"]["income"]
    payments = tax["payments"]
    return _rule(
        rule_id="US25-FACTS",
        country="US",
        language="en",
        template_id="US25-FACTS",
        title="U.S. basic facts",
        legal_refs=("26 U.S.C. § 6012", "26 U.S.C. § 6013"),
        authority_urls=(USC_6012_URL, USC_6013_URL),
        inputs=(
            _value("Filing status", tax["filing_assumptions"]["filing_status"], "us.filing_assumptions.filing_status"),
            _value("Wages", f"{tax['income']['wages_usd']} USD", "us.income.wages_usd"),
            _value("Ordinary dividends", f"{income['ordinary_dividends_usd']} USD", "us.income.ordinary_dividends_usd"),
            _value("Short-term capital total", f"{capital['short_term_total_usd']} USD", "us.capital.short_term_total_usd"),
            _value("Long-term capital total", f"{capital['long_term_total_with_cgd_usd']} USD", "us.capital.long_term_total_with_cgd_usd"),
        ),
        math_steps=(
            _step(
                "Collect validated U.S. facts after parsing, normalization, and legal model execution.",
                "validated final output only; no renderer-side tax calculation",
                f"{payments['refund_with_treaty_resourcing_usd']} USD refund / {payments['amount_owed_with_treaty_resourcing_usd']} USD amount owed",
            ),
        ),
        outputs=(
            _value("Treaty refund", f"{payments['refund_with_treaty_resourcing_usd']} USD", "us.payments.refund_with_treaty_resourcing_usd"),
            _value("Treaty amount owed", f"{payments['amount_owed_with_treaty_resourcing_usd']} USD", "us.payments.amount_owed_with_treaty_resourcing_usd"),
        ),
        form_lines=(
            _line("Form 1040", "line 35a", f"{payments['refund_with_treaty_resourcing_usd']} USD"),
            _line("Form 1040", "line 37", f"{payments['amount_owed_with_treaty_resourcing_usd']} USD"),
        ),
    )


def _usa_treaty_ftc(forms: dict) -> dict:
    tax = forms["tax_estimate"]
    treaty = tax["treaty_resourcing"]
    worksheet_line_21 = treaty.get(
        "worksheet_line_21_additional_credit_usd",
        treaty["treaty_resourcing_additional_ftc_usd"],
    )
    return _rule(
        rule_id="US25-NARRATIVE-TREATY-FTC",
        country="US",
        language="en",
        template_id="US25-NARRATIVE-TREATY-FTC",
        title="Publication 514 treaty additional foreign tax credit",
        legal_refs=("IRS Publication 514", "Germany treaty technical explanation", "Instructions for Form 1116"),
        authority_urls=(
            IRS_P514,
            IRS_GERMANY_TECH,
            IRS_I1116,
        ),
        inputs=(
            _value("U.S.-source dividends", f"{treaty['us_source_dividends_usd']} USD", "us.treaty_resourcing.us_source_dividends_usd"),
            _value("U.S. tax above treaty floor", f"{treaty['treaty_resourcing_us_limitation_usd']} USD", "us.treaty_resourcing.treaty_resourcing_us_limitation_usd"),
            _value("German residual tax cap", f"{treaty['worksheet_line_20c_residual_residence_country_tax_usd']} USD", "us.treaty_resourcing.worksheet_line_20c_residual_residence_country_tax_usd"),
        ),
        math_steps=(
            _step(
                "Compute Publication 514 worksheet line 21.",
                "worksheet line 21 = min(line 19 maximum credit, line 20c residual residence-country tax)",
                f"{worksheet_line_21} USD",
            ),
            _step(
                "Apply the remaining Form 1116 line-33 nonrefundable-credit cap.",
                "allowed treaty FTC add-on = min(worksheet line 21, remaining Form 1116 line 33 cap)",
                f"{treaty['treaty_resourcing_additional_ftc_usd']} USD",
            ),
        ),
        outputs=(
            _value("Publication 514 worksheet line 21", f"{worksheet_line_21} USD", "us.treaty_resourcing.worksheet_line_21_additional_credit_usd"),
            _value("Additional treaty FTC", f"{treaty['treaty_resourcing_additional_ftc_usd']} USD", "us.treaty_resourcing.treaty_resourcing_additional_ftc_usd"),
        ),
        form_lines=(
            _line("Form 1116", "line 12 / line 32", f"{worksheet_line_21} USD", note="Attach the Publication 514 treaty worksheet; Form 1116 line 33 caps the final allowed credit."),
        ),
    )


def _usa_niit(forms: dict) -> dict:
    tax = forms["tax_estimate"]
    return _rule(
        rule_id="US25-NARRATIVE-NIIT",
        country="US",
        language="en",
        template_id="US25-NARRATIVE-NIIT",
        title="Net investment income tax",
        legal_refs=("26 U.S.C. § 1411", "Instructions for Form 8960"),
        authority_urls=(
            USC_1411_URL,
            IRS_I8960,
        ),
        inputs=(
            _value("Adjusted gross income", f"{tax['income']['adjusted_gross_income_usd']} USD", "us.income.adjusted_gross_income_usd"),
            _value("NIIT threshold", f"{tax['filing_assumptions']['niit_threshold_usd']} USD", "us.filing_assumptions.niit_threshold_usd"),
            _value("Net investment income", f"{_trace_amount(forms['trace_rows'], 'net_investment_income', 'amount_usd')} USD", "us.tax.net_investment_income_usd"),
        ),
        math_steps=(
            _step(
                "Apply 3.8 percent NIIT to the lesser of net investment income and modified-AGI excess.",
                "NIIT = 3.8% * min(NII, max(0, MAGI - threshold))",
                f"{tax['tax']['niit_usd']} USD",
            ),
        ),
        outputs=(
            _value("NIIT", f"{tax['tax']['niit_usd']} USD", "us.tax.niit_usd"),
        ),
        form_lines=(
            _line("Form 8960", "line 17", f"{tax['tax']['niit_usd']} USD"),
            _line("Schedule 2", "line 12", f"{tax['tax']['niit_usd']} USD"),
        ),
    )


def _usa_payments(forms: dict) -> dict:
    tax = forms["tax_estimate"]
    payments = tax["payments"]
    refund = payments["refund_with_treaty_resourcing_usd"]
    amount_owed = payments["amount_owed_with_treaty_resourcing_usd"]
    return _rule(
        rule_id="US25-NARRATIVE-PAYMENTS",
        country="US",
        language="en",
        template_id="US25-NARRATIVE-PAYMENTS",
        title="Form 1040 payment/refund result",
        legal_refs=("Instructions for Form 1040",),
        authority_urls=(IRS_I1040,),
        inputs=(
            _value("Total tax with treaty resourcing", f"{tax['tax']['total_tax_with_treaty_resourcing_usd']} USD", "us.tax.total_tax_with_treaty_resourcing_usd"),
            _value("Estimated payments", f"{payments['estimated_payment_usd']} USD", "us.payments.estimated_payment_usd"),
        ),
        math_steps=(
            _step(
                "Apply payments to the modeled total tax.",
                "overpayment = payments - total tax after credits and additional taxes; refund = max(0, overpayment); amount owed = max(0, -overpayment)",
                f"{refund} USD refund / {amount_owed} USD amount owed",
            ),
        ),
        outputs=(
            _value("Refund", f"{refund} USD", "us.payments.refund_with_treaty_resourcing_usd"),
            _value("Amount owed", f"{amount_owed} USD", "us.payments.amount_owed_with_treaty_resourcing_usd"),
        ),
        form_lines=(
            _line("Form 1040", "line 26", f"{payments['estimated_payment_usd']} USD"),
            _line("Form 1040", "line 35a", f"{refund} USD"),
            _line("Form 1040", "line 37", f"{amount_owed} USD"),
        ),
    )


def _germany_ordinary_stage_results(forms: dict, stages: Sequence[LawStage]) -> tuple[StageResult, ...]:
    # Phase 3 of the engine restructure: ordinary StageResults come from the
    # executed RuleGraphExecution stashed in pipeline_context by
    # ``execute_germany_ordinary_rule_graph`` during the Germany model run. No
    # JSON replay, no lookup-lambda projection.
    execution = get_pipeline_context_value(GERMANY_ORDINARY_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "Germany ordinary rule graph execution missing from pipeline context. "
            "Ensure germany_model.py / compute_joint_ordinary_assessment_2025 ran before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"Germany ordinary rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def _germany_capital_stage_results(forms: dict, stages: Sequence[LawStage]) -> tuple[StageResult, ...]:
    # Phase 2 of the engine restructure: capital StageResults come from the
    # executed RuleGraphExecution stashed in pipeline_context by
    # ``execute_germany_capital_rule_graph`` during the Germany model run. No
    # JSON replay, no lookup-lambda projection.
    execution = get_pipeline_context_value(GERMANY_CAPITAL_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "Germany capital rule graph execution missing from pipeline context. "
            "Ensure germany_model.py / compute_germany_capital_assessment_2025 ran before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"Germany capital rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def _germany_final_stage_results(forms: dict, stages: Sequence[LawStage]) -> tuple[StageResult, ...]:
    # WS-4B (invariant migration plan §6): final-refund StageResults come
    # from the executed RuleGraphExecution stashed in pipeline_context by
    # ``execute_germany_final_rule_graph`` during the Germany model run.
    # The DE25-22-FINAL-REFUND stage's outputs (target_refund_eur,
    # refund_before_treaty_eur, chosen_refund_before_domestic_certificate_eur)
    # used to be script-level Decimal arithmetic in ``germany_model.main()``;
    # promoting them into the rule graph brings the headline number inside
    # the audit fingerprint chain (invariant I2) and removes the
    # script-level arithmetic invariant I5 flagged. Authority:
    # § 36 Abs. 2 EStG; § 32d Abs. 1 EStG; InvStG § 20.
    execution = get_pipeline_context_value(GERMANY_FINAL_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "Germany final-refund rule graph execution missing from pipeline context. "
            "Ensure germany_model.py ran execute_germany_final_rule_graph before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"Germany final-refund rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def _germany_kap_projection_stage_results(
    forms: dict, stages: Sequence[LawStage]
) -> tuple[StageResult, ...]:
    # WS-4C (invariant migration plan §6): the Anlage KAP / KAP-INV
    # form-line projection runs through ``execute_germany_kap_projection_rule_graph``
    # during the Germany model run. The executed StageResult carries
    # fingerprints for each per-Zeile EUR scalar (Zeilen 19/20/21/23/24/41 +
    # KAP-INV 4/8/14/26 + per-fund rows), promoting the prior script-level
    # arithmetic at ``germany_projections.py:113`` into the audit graph so
    # invariants I2 (final-output traceability) and I5 (no Decimal math
    # in orchestrators) hold. Authority: § 20 Abs. 1 / Abs. 2 EStG;
    # § 32d Abs. 1 EStG; InvStG § 20.
    execution = get_pipeline_context_value(GERMANY_KAP_PROJECTION_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "Germany KAP projection rule graph execution missing from pipeline context. "
            "Ensure germany_model.py ran execute_germany_kap_projection_rule_graph before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"Germany KAP projection rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def _usa_stage_results(forms: dict, stages: Sequence[LawStage]) -> tuple[StageResult, ...]:
    # Phase 4 of the engine restructure: US StageResults come from the executed
    # RuleGraphExecution stashed in pipeline_context by ``execute_us_rule_graph``
    # during the U.S. model run. No JSON replay, no lookup-lambda projection.
    execution = get_pipeline_context_value(US_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "U.S. rule graph execution missing from pipeline context. "
            "Ensure us_model.py / compute_us_assessment_2025 ran before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"U.S. rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def _treaty_stage_results(forms: dict, stages: Sequence[LawStage]) -> tuple[StageResult, ...]:
    # Phase 1 of the engine restructure: the treaty stages execute through
    # ``execute_treaty_rule_graph`` during the main pipeline run. The narrative
    # packet builder must consume those *same* StageResults, not replay values
    # from the JSON. ``us_2025_law.treaty_resourcing_assessment_2025`` stashes
    # the ``RuleGraphExecution`` under TREATY_EXECUTION_CONTEXT_KEY for this
    # in-memory hand-off.
    execution = get_pipeline_context_value(TREATY_EXECUTION_CONTEXT_KEY)
    if execution is None:
        raise RuntimeError(
            "Treaty rule graph execution missing from pipeline context. "
            "Ensure us_model.py / compute_us_assessment_2025 ran before the narrative packet builder."
        )
    declared_stage_ids = {stage.stage_id for stage in stages}
    executed_stage_ids = {result.stage_id for result in execution.stage_results}
    if declared_stage_ids != executed_stage_ids:
        raise RuntimeError(
            f"Treaty rule graph execution does not match declared stages: "
            f"declared={sorted(declared_stage_ids)} executed={sorted(executed_stage_ids)}"
        )
    return execution.stage_results


def build_rule_narratives_2025(final_output: dict) -> dict[str, dict[str, list[dict]]]:
    narratives: dict[str, dict[str, list[dict]]] = {
        "DE": {"de": [], "en": []},
        "US": {"en": []},
    }
    germany_forms = final_output.get("germany", {}).get("forms", {})
    germany_results = germany_forms.get("results", {})
    germany_complete = all(key in germany_results for key in ("ordinary", "capital", "refunds"))
    if germany_forms.get("status") != "not_applicable" and germany_complete:
        germany_stages = (
            germany_ordinary_law_stages_2025()
            + germany_capital_law_stages_2025()
            + germany_final_law_stages_2025()
            + germany_kap_projection_law_stages_2025()
        )
        germany_stage_results = (
            _germany_ordinary_stage_results(germany_forms, germany_ordinary_law_stages_2025())  # pragma: legal-math-ok tuple-of-StageResult concatenation, not Decimal arithmetic
            + _germany_capital_stage_results(germany_forms, germany_capital_law_stages_2025())  # pragma: legal-math-ok tuple-of-StageResult concatenation
            + _germany_final_stage_results(germany_forms, germany_final_law_stages_2025())  # pragma: legal-math-ok tuple-of-StageResult concatenation
            + _germany_kap_projection_stage_results(
                germany_forms, germany_kap_projection_law_stages_2025()
            )
        )
        narratives["DE"]["de"] = _with_missing_stage_rules(
            [
                _germany_facts(germany_forms, language="de"),
                _germany_split_tariff(germany_forms, language="de"),
                _germany_capital_ftc(germany_forms, language="de"),
            ],
            germany_stages,
            country="DE",
            language="de",
            stage_results=germany_stage_results,
        )
        narratives["DE"]["en"] = _with_missing_stage_rules(
            [
                _germany_facts(germany_forms, language="en"),
                _germany_split_tariff(germany_forms, language="en"),
                _germany_capital_ftc(germany_forms, language="en"),
            ],
            germany_stages,
            country="DE",
            language="en",
            stage_results=germany_stage_results,
        )
    usa_forms = final_output.get("usa", {}).get("forms", {})
    usa_complete = all(key in usa_forms for key in ("tax_estimate", "capital_results", "trace_rows"))
    if usa_forms.get("status") != "not_applicable" and usa_complete:
        usa_stages = usa_law_stages_2025()
        treaty_stages = treaty_law_stages_2025()
        usa_stage_results = _usa_stage_results(usa_forms, usa_stages) + _treaty_stage_results(usa_forms, treaty_stages)  # pragma: legal-math-ok tuple-of-StageResult concatenation, not Decimal arithmetic
        narratives["US"]["en"] = _with_missing_stage_rules(
            [
                _usa_facts(usa_forms),
                _usa_treaty_ftc(usa_forms),
                _usa_niit(usa_forms),
                _usa_payments(usa_forms),
            ],
            (*usa_stages, *treaty_stages),
            country="US",
            language="en",
            stage_results=usa_stage_results,
        )
    return narratives


__all__ = ["build_rule_narratives_2025"]
