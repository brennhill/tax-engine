from __future__ import annotations

import csv
import json
from decimal import Decimal, getcontext
from pathlib import Path

from tax_pipeline.y2025.bridge_rules import (
    bridge_initial_facts_2025,
    bridge_initial_fingerprints_2025,
    execute_bridge_rule_graph,
)
from tax_pipeline.y2025.cross_jurisdiction import (
    should_include_bridge_2025_stages,
)
from tax_pipeline.y2025.germany_final_rules import (
    execute_germany_final_rule_graph,
    germany_final_initial_facts_2025,
    germany_final_initial_fingerprints_2025,
)
from tax_pipeline.y2025.germany_guenstigerpruefung_rules import (
    execute_germany_guenstigerpruefung_rule_graph,
    germany_guenstigerpruefung_initial_facts_2025,
    germany_guenstigerpruefung_initial_fingerprints_2025,
)
from tax_pipeline.y2025.germany_inputs import load_joint_ordinary_inputs_2025
from tax_pipeline.y2025.germany_law import (
    BMF_ABGELTUNGSTEUER_URL,
    BMF_PAP_2025_URL,
    BMF_USA_PAGE_URL,
    CAPITAL_TAX_RATE_2025,
    ELSTER_ANLAGE_AUS_2025_URL as ELSTER_2025_URL,
    ESTG_4_5_6C_URL,
    ESTG_9_URL,
    ESTG_9A_URL,
    ESTG_10C_URL,
    ESTG_10_URL,
    ESTG_19_URL,
    ESTG_20_URL,
    ESTG_22_URL,
    ESTG_23_URL,
    ESTG_26_URL,
    ESTG_26B_URL,
    ESTG_2_URL,
    ESTG_32A_URL,
    ESTG_32D_URL,
    ESTG_33B_URL,
    ESTG_36_URL,
    ESTG_3_URL,
    ESTH_PARAGRAF_19A_URL as ESTH_19A_URL,
    ESTR_R_34C_URL as BMF_ECB_URL,
    GermanyBankCapitalCertificate2025,
    GermanyCapitalAssessment2025,
    GermanyCapitalAssessmentInputs2025,
    GermanyCapitalIncomeFact2025,
    GermanyCapitalSaleFact2025,
    GUENSTIGERPRUEFUNG_MATERIALITY_EUR,
    GermanyTreatyDividendItem2025,
    INVSTG_20_URL,
    INVSTG_21_URL,
    SAVER_ALLOWANCE_JOINT_2025_EUR,
    SAVER_ALLOWANCE_SINGLE_2025_EUR,
    SOLI_RATE,
    SOLZG_3_URL,
    SOLZG_4_URL,
    TAX_ADVICE_BMF_URL,
    compute_germany_capital_assessment_2025,
    compute_germany_children_assessment_2025,
    compute_joint_ordinary_assessment_2025,
)
from tax_pipeline.pipeline_context import set_pipeline_context_value
from tax_pipeline.pipelines.y2025 import germany_loaders as _germany_loaders
from tax_pipeline.pipelines.y2025.germany_loaders import (
    BANK_CERTIFICATE_FIELD_ALIASES,
    FUND_TEILFREISTELLUNG_RATES,
    load_bank_capital_certificates_2025,
    load_capital_income_facts_2025,
    load_capital_sale_facts_2025,
    load_coinbase_results,
    load_dher_results,
    load_fund_classification,
    load_inputs,
    load_manual_overrides,
    load_us_treaty_dividend_items_2025,
    load_vorabpauschale_inputs_2025,
)
from tax_pipeline.pipelines.y2025.germany_projections import (
    anlage_n_entries_projection_2025 as _anlage_n_entries_projection_2025,
    capital_form_projection_2025 as _capital_form_projection_2025,
    children_form_projection_2025 as _children_form_projection_2025,
    fmt,
    ordinary_form_projection_rows_2025 as _ordinary_form_projection_rows_2025,
    person_projection_2025 as _person_projection_2025,
    person_slots_for_projection_2025 as _person_slots_for_projection_2025,
    q2,
)
from tax_pipeline.pipelines.y2025.vanilla_checkpoint import (
    compute_germany_vanilla_checkpoint_2025,
)
from tax_pipeline.postures import get_posture_definition
from tax_pipeline.y2025.treaty_bridge import (
    GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY,
    write_germany_treaty_dividend_audit_2025,
)
from tax_pipeline.year_runtime import active_year_paths, analysis_root

getcontext().prec = 28
D = Decimal


# WS-5D (invariant migration plan §7): germany_loaders now resolves its
# workspace lazily, so the previous explicit-rebind ritual (which existed
# only to propagate module-level state into a once-imported loader) is
# unnecessary. We still resolve our own YEAR_PATHS / STEPS here because
# this module runs as ``__main__`` under ``runpy.run_module(..., alter_sys=True)``
# and is re-executed on every pipeline run; the rebind on germany_loaders
# is replaced by an explicit cache reset so its cached values pick up any
# env changes between runs.
YEAR_PATHS = active_year_paths(Path(__file__), default_year=2025)
STEPS = analysis_root(Path(__file__), default_year=2025)
_germany_loaders.reset_year_paths()

# Compatibility re-exports (modules that imported these names from germany_model)
STRUCTURED_INPUTS = _germany_loaders._structured_inputs()
SALES_CSV = _germany_loaders._sales_csv()
INCOME_CSV = _germany_loaders._income_csv()
DE_US_TREATY_DIVIDENDS_CSV = _germany_loaders._de_us_treaty_dividends_csv()
COINBASE_RESULTS_JSON = _germany_loaders._coinbase_results_json()
DHER_RESULTS_JSON = _germany_loaders._dher_results_json()

RESULTS_JSON = STEPS / "germany-model-results.json"
TRACE_CSV = STEPS / "germany-model-trace.csv"
SUMMARY_MD = STEPS / "germany-summary.md"
AUDIT_NOTE_MD = STEPS / "germany-audit-note.md"

MARRIED_SEPARATE_UNSUPPORTED = (
    "Germany filing posture 'married_separate' is not supported for the 2025 capital/output pipeline yet."
)


CapitalBuckets = GermanyCapitalAssessment2025


def _ensure_supported_filing_posture(filing_posture: str) -> None:
    posture = get_posture_definition("germany", filing_posture)
    if not posture.output_support.forms:
        raise NotImplementedError(MARRIED_SEPARATE_UNSUPPORTED)


# Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-country § 34c (1)
# EStG / § 32d Abs. 5 EStG foreign-tax-credit breakdown read from the
# auto-derived ``de-anlage-aus-by-country.csv``. The helper returns the
# rows as a list of dicts with EUR amounts as Decimal-as-string values
# (no Decimal arithmetic in the projection — invariant I5). The
# downstream renderer wraps each Decimal-amount cell in a LegalValue
# envelope via ``legal_value_from_decimal`` (invariant I11) and writes
# only to the Anlage AUS Zeilen declared in
# DE25-18-SECTION-32D5-FTC.outputs.form_line_refs (invariant I3).
def _read_anlage_aus_by_country_rows(year_paths) -> list[dict[str, str]]:
    """Read the auto-derived per-country Anlage AUS rows.

    Returns ``[]`` when the CSV is absent (e.g. ``us_filing_required=false``
    workspaces have no treaty dividend items so the CSV is also empty).
    """
    csv_path = year_paths.tax_positions_root / "de-anlage-aus-by-country.csv"
    if not csv_path.exists():
        return []
    with csv_path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]


def _load_derived_disability_pauschbetrag_total_2025() -> Decimal:
    """Read the § 33b Abs. 5 EStG transferral total from Pipeline 1.

    Gap 2 boundary helper. The orchestrator runs ``run_derivation``
    before ``germany_model`` so ``derived-facts.json`` exists in
    production. Reads only the single Decimal-coercible EUR amount the
    ordinary graph needs as an additional input fact — keeps the rest
    of the derivation surface out of this loader.

    Resolves the active workspace at call-time (mirroring the capital
    sub-graph boundary loader) so test harnesses that set
    ``TAX_WORKSPACE_ROOT`` per-test pick up the right artifact even
    when ``germany_model`` was imported under a different default.

    Returns Decimal("0.00") when no workspace is resolvable or
    ``derived-facts.json`` is missing — these are the test harnesses
    that mock out ``compute_joint_ordinary_assessment_2025`` /
    ``germany_model.main()`` rather than running the full pipeline,
    so the transferral total is irrelevant. Production callers always
    have the artifact (the year orchestrator schedules
    ``run_derivation`` first).

    Authority: § 33b Abs. 5 EStG transferral routed through the
    Pipeline 1 → Pipeline 2 boundary state per
    ``docs/invariant-migration-plan.md`` §1.5.
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    import os

    from tax_pipeline.derivation.persistence import (
        derivation_facts_path,
        load_derivation_facts,
    )

    if not os.environ.get("TAX_WORKSPACE_ROOT") and not os.environ.get(
        "TAX_PROJECT_ROOT"
    ):
        return Decimal("0.00")
    try:
        paths = active_year_paths(Path(__file__), default_year=2025)
    except Exception:
        return Decimal("0.00")
    if not derivation_facts_path(paths).exists():
        return Decimal("0.00")
    raw_facts = load_derivation_facts(paths)
    raw_value = raw_facts.get(
        "de.derived.children_disability_pauschbetrag_total_eur"
    )
    if raw_value is None:
        # Pipeline 1 must produce this key for every workspace (the
        # derivation runs the same DERIVE-DE25-CHILDREN stage even when
        # no children are declared, in which case the value is "0.00").
        # Missing from a present derived-facts.json indicates a stale
        # derivation artifact — fail closed rather than silently zero.
        raise ValueError(
            "derived-facts.json is missing "
            "'de.derived.children_disability_pauschbetrag_total_eur'. "
            "Pipeline 1 (run_derivation) must regenerate the artifact "
            "before germany_model runs. Authority: § 33b Abs. 5 EStG."
        )
    return Decimal(str(raw_value))


def _load_disability_pauschbetrag_transfer_split_2025() -> (
    tuple[Decimal, ...] | None
):
    """Load the § 33b Abs. 5 Satz 3 EStG joint-election split override.

    Reads ``elections.germany_disability_pauschbetrag_transfer_split``
    from the workspace ``profile.json``. Returns ``None`` when the
    election is omitted (statutory 50/50 default applies); returns a
    tuple of Decimal shares when the parents jointly elected another
    allocation per Anlage Kind 2025 Zeile 66 ("anderweitige prozentuale
    Aufteilung"). The shares are validated for shape (Decimal-convertible,
    non-negative) at load time; sum-to-1 + arity validation against the
    person count happens inside the rule body so the failing input ties
    back to the correct § 33b Abs. 5 Satz 3 EStG citation.

    Authority: § 33b Abs. 5 Satz 3 EStG —
        "Der einem Kind zustehende Pauschbetrag … wird auf die
        Elternteile zu gleichen Teilen aufgeteilt, es sei denn, sie
        beantragen gemeinsam eine andere Aufteilung."
    https://www.gesetze-im-internet.de/estg/__33b.html
    """
    if not YEAR_PATHS.profile_path.exists():
        return None
    profile = json.loads(YEAR_PATHS.profile_path.read_text(encoding="utf-8"))
    elections = profile.get("elections")
    if not isinstance(elections, dict):
        return None
    raw = elections.get(
        "germany_disability_pauschbetrag_transfer_split", None
    )
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)):
        raise ValueError(
            "elections.germany_disability_pauschbetrag_transfer_split must "
            "be a list of share values per § 33b Abs. 5 Satz 3 EStG; "
            f"got {type(raw).__name__}. {ESTG_33B_URL}"
        )
    shares: list[Decimal] = []
    for index, entry in enumerate(raw):
        try:
            share = Decimal(str(entry))
        except Exception as exc:
            raise ValueError(
                "elections.germany_disability_pauschbetrag_transfer_split"
                f"[{index}] must be Decimal-convertible per "
                f"§ 33b Abs. 5 Satz 3 EStG; got {entry!r}. {ESTG_33B_URL}"
            ) from exc
        shares.append(share)
    return tuple(shares)


def compute_capital_buckets(
    inputs: dict[str, Decimal],
    dher: dict[str, Decimal],
    fund_classification: dict[str, str],
    *,
    sale_facts: tuple[GermanyCapitalSaleFact2025, ...] | None = None,
    income_facts: tuple[GermanyCapitalIncomeFact2025, ...] | None = None,
    bank_certificates: tuple[GermanyBankCapitalCertificate2025, ...] = (),
    treaty_dividend_items: tuple[GermanyTreatyDividendItem2025, ...] = (),
    vorabpauschale_inputs: tuple = (),
    derived_facts: dict | None = None,
) -> CapitalBuckets:
    # ``derived_facts`` is the optional Pipeline 1 → Pipeline 2 boundary
    # state. Production callers (germany_model.main()) leave it ``None``
    # so ``compute_germany_capital_assessment_2025`` reads
    # ``derived-facts.json`` from the active workspace (run_derivation
    # writes it before germany_model runs). Test callers that bypass
    # ``run_year`` and stub ``germany_model.SALES_CSV`` / ``INCOME_CSV``
    # synthesize the boundary via
    # ``tests/_germany_derived_facts.py:germany_derived_facts_for_inputs``
    # and forward it through this kwarg — F-A4 (architecture review,
    # ``.review/2026-05-01-final/architecture.md``) removed the in-memory
    # Pipeline 1 fallback that previously hid the boundary inside
    # production code.
    if sale_facts is None:
        # Pass module-level SALES_CSV / INCOME_CSV explicitly so tests that
        # ``mock.patch.object(germany_model, "SALES_CSV", ...)`` reach the
        # loader. Calling the loader without an argument would resolve the
        # path against germany_loaders.SALES_CSV and bypass the patch.
        sale_facts = load_capital_sale_facts_2025(SALES_CSV)
    if income_facts is None:
        income_facts = load_capital_income_facts_2025(INCOME_CSV)

    # § 20 Abs. 9 EStG: the workspace ``saver_allowance_eur`` row is a
    # redundant declaration of SAVER_ALLOWANCE_JOINT_2025_EUR; the loader
    # has already asserted it equals the canonical statutory value via
    # ``assert_germany_csv_statutory_constants_2025`` (invariant I1).
    effective_saver_allowance = inputs.get(
        "effective_saver_allowance_eur",
        inputs.get("saver_allowance_eur", SAVER_ALLOWANCE_JOINT_2025_EUR),
    )
    other_spouse_capital_before_allowance = None
    if "other_spouse_capital_before_allowance_eur" in inputs:
        saver_allowance = inputs.get("saver_allowance_eur", effective_saver_allowance)
        other_spouse_capital_before_allowance = inputs["other_spouse_capital_before_allowance_eur"]
    else:
        saver_allowance = effective_saver_allowance

    return compute_germany_capital_assessment_2025(
        GermanyCapitalAssessmentInputs2025(
            sale_facts=sale_facts,
            income_facts=income_facts,
            dher_stock_gain_eur=dher["total_gain_eur"],
            stock_loss_carryforward_2024_eur=inputs["stock_loss_carryforward_2024_eur"],
            saver_allowance_eur=saver_allowance,
            # § 32d Abs. 1 Satz 1 EStG: 25% Abgeltungsteuer rate. The single
            # canonical declaration lives in tax_pipeline.y2025.germany_law as
            # CAPITAL_TAX_RATE_2025; the workspace CSV row is a redundant
            # declaration validated at load time (invariant I1). Tests that
            # mock ``load_inputs`` may pass an explicit override for replay.
            # Authority: https://www.gesetze-im-internet.de/estg/__32d.html
            capital_tax_rate=inputs.get("capital_tax_rate", CAPITAL_TAX_RATE_2025),
            # § 4 Satz 1 SolzG 1995: 5.5 % Solidaritätszuschlag. SOLI_RATE is
            # the single canonical declaration; the workspace CSV row is a
            # redundant declaration validated at load time (invariant I1).
            # Authority: https://www.gesetze-im-internet.de/solzg_1995/__4.html
            soli_rate=inputs.get("soli_rate", SOLI_RATE),
            treaty_dividend_credit_eur=inputs.get("treaty_dividend_credit_eur", D("0.00")),
            fund_classification=dict(fund_classification),
            bank_certificates=bank_certificates,
            treaty_dividend_items=treaty_dividend_items,
            other_spouse_capital_before_allowance_eur=other_spouse_capital_before_allowance,
            vorabpauschale_inputs=vorabpauschale_inputs,
        ),
        derived_facts=derived_facts,
    )


def write_trace_row(
    writer: csv.writer,
    step: str,
    value: Decimal,
    note: str,
    legal_reference: str,
    authority_url: str,
    precision_note: str = "",
) -> None:
    writer.writerow([step, fmt(value), note, legal_reference, authority_url, precision_note])


def ensure_private_sales_integrated_or_nonpositive_2025(
    inputs: dict[str, Decimal],
    coinbase: dict[str, Decimal],
) -> None:
    current_sidecar_result = D(str(coinbase.get("private_sale_result_eur", D("0.00"))))
    configured_current_gains = D(str(inputs.get("private_sale_gains_2025_eur", D("0.00"))))
    if current_sidecar_result <= D("0.00") and configured_current_gains <= D("0.00"):
        return
    # § 23 Abs. 3 EStG includes private-sale gains in the taxable result and allows
    # private-sale losses only inside the § 23 bucket. A positive current-year result
    # cannot remain as an audit sidecar after the § 2 / § 32d / § 36 final result is assembled.
    raise ValueError(
        "Positive § 23 EStG private-sale results must be integrated into the Germany core "
        "ordinary/final refund calculation before rendering; sidecar result "
        f"{fmt(current_sidecar_result)} EUR, configured private_sale_gains_2025_eur "
        f"{fmt(configured_current_gains)} EUR."
    )


def ensure_capital_guenstigerpruefung_position_2025(
    inputs: dict[str, Decimal],
    capital: GermanyCapitalAssessment2025,
) -> None:
    taxable_capital = D(str(capital.taxable_after_teilfreistellung_eur))
    if taxable_capital <= D("0.00"):
        return
    if "capital_guenstigerpruefung_requested" not in inputs:
        # § 32d Abs. 6 EStG is an explicit application/election for ordinary-tariff
        # treatment of capital income. Missing election posture must not default to
        # "not requested" when capital income exists.
        raise ValueError(
            "Germany § 32d Abs. 6 Günstigerprüfung posture is required for capital income: "
            "add capital_guenstigerpruefung_requested=0 or 1 to de-model-assumptions.csv."
        )
    requested = D(str(inputs["capital_guenstigerpruefung_requested"]))
    if requested not in {D("0"), D("1")}:
        raise ValueError("Germany § 32d Abs. 6 capital_guenstigerpruefung_requested must be 0 or 1.")
    if requested == D("1"):
        # § 32d Abs. 6 EStG would move capital income into the ordinary tariff
        # comparison. The 2025 model has not implemented that branch yet.
        raise NotImplementedError("Germany § 32d Abs. 6 Günstigerprüfung is not implemented.")


def main() -> None:
    ordinary_inputs = load_joint_ordinary_inputs_2025(YEAR_PATHS)
    # Gap 2 — § 33b Abs. 5 EStG transferral. Pipeline 1 already ran (the
    # year orchestrator schedules ``run_derivation`` BEFORE ``germany_model``);
    # read the derived total off ``derived-facts.json`` and thread it
    # into the ordinary graph so DE25-BEHINDERUNG-PAUSCHBETRAG adds it to
    # the parents' household total. Demo posture (no children → empty
    # children-tuple → election_active=False → derived total 0.00) keeps
    # demo numerics unchanged.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    children_disability_pauschbetrag_total = (
        _load_derived_disability_pauschbetrag_total_2025()
    )
    # § 33b Abs. 5 Satz 3 EStG joint-election split override (Gap 2
    # deferred). ``None`` selects the statutory 50/50 default. A
    # workspace that wires Anlage Kind 2025 Zeile 66 (anderweitige
    # prozentuale Aufteilung) sets a ratio in profile.json under
    # ``elections.germany_disability_pauschbetrag_transfer_split``.
    # https://www.gesetze-im-internet.de/estg/__33b.html
    disability_pauschbetrag_transfer_split = (
        _load_disability_pauschbetrag_transfer_split_2025()
    )
    ordinary = compute_joint_ordinary_assessment_2025(
        ordinary_inputs,
        children_disability_pauschbetrag_total_eur=(
            children_disability_pauschbetrag_total
        ),
        disability_pauschbetrag_transfer_split=(
            disability_pauschbetrag_transfer_split
        ),
    )
    _ensure_supported_filing_posture(ordinary.filing_posture)
    # ``load_inputs`` runs through ``analysis_inputs.load_german_model_inputs``,
    # which asserts the four statutory rows in de-tax-constants.csv agree with
    # the centralized 2025 law-module constants per invariant I1.
    inputs = load_inputs()
    person_count = len(ordinary.people)
    bank_certificates = load_bank_capital_certificates_2025()
    treaty_dividend_items = load_us_treaty_dividend_items_2025()
    vorabpauschale_inputs = load_vorabpauschale_inputs_2025()
    person_2_bank_certificate_has_amounts = bool(bank_certificates)
    # § 20 Abs. 9 Sätze 1 und 2 EStG: jointly assessed spouses share the
    # €2,000 Sparer-Pauschbetrag; otherwise each filer gets €1,000. Both
    # values are centralized law-module constants per invariant I1. The
    # workspace ``saver_allowance_eur`` input is a redundant declaration
    # validated at load time, so we read it here for backwards-compatible
    # test fixtures and fall back to the law-module constant when absent.
    inputs_saver_allowance = inputs.get(
        "saver_allowance_eur", SAVER_ALLOWANCE_JOINT_2025_EUR
    )
    if ordinary.filing_posture == "married_joint":
        effective_saver_allowance = inputs_saver_allowance
    else:
        # § 20 Abs. 9 Satz 1 EStG: half-share for non-joint filers, expressed
        # as the law-module SAVER_ALLOWANCE_SINGLE_2025_EUR constant when the
        # input matches the canonical joint amount; otherwise honor the
        # explicit input (test fixture override) by halving it.
        if inputs_saver_allowance == SAVER_ALLOWANCE_JOINT_2025_EUR:
            effective_saver_allowance = SAVER_ALLOWANCE_SINGLE_2025_EUR
        else:
            effective_saver_allowance = q2(inputs_saver_allowance / D("2"))  # pragma: legal-math-ok § 20 Abs. 9 EStG: single-filer half-share derived from a non-canonical fixture override; the canonical statutory path uses SAVER_ALLOWANCE_SINGLE_2025_EUR directly.
    coinbase = load_coinbase_results()
    ensure_private_sales_integrated_or_nonpositive_2025(inputs, coinbase)
    dher = load_dher_results()
    fund_classification = load_fund_classification()
    capital_inputs = dict(inputs)
    capital_inputs["effective_saver_allowance_eur"] = effective_saver_allowance
    capital = compute_capital_buckets(
        capital_inputs,
        dher,
        fund_classification,
        bank_certificates=bank_certificates,
        treaty_dividend_items=treaty_dividend_items,
        vorabpauschale_inputs=vorabpauschale_inputs,
    )
    ensure_capital_guenstigerpruefung_position_2025(inputs, capital)
    # WS-4A (invariant migration plan §6): the foreign-tax reconciliation
    # invariant — that the four independently sourced foreign-tax-paid
    # components (1099 input, German bank certificate credited bucket,
    # German bank certificate not-yet-credited bucket, treaty re-sourcing
    # add-on) sum to ``capital.explicit_foreign_tax_total`` — is now
    # asserted by the BRIDGE25-FOREIGN-TAX-RECONCILIATION rule. Promoting
    # the assertion into the rule graph brings the verified total inside
    # the audit fingerprint chain (invariant I2) and removes the
    # script-level Decimal arithmetic that invariant I5 flagged.
    # Authority: § 32d Abs. 5 EStG; 26 U.S.C. § 901; DBA-USA Art. 23.
    # 26 U.S.C. § 6012 cross-jurisdiction gate: when the household has
    # opted out of the U.S. pathway (``elections.us_filing_required=false``)
    # the BRIDGE25-FOREIGN-TAX-RECONCILIATION stage has no
    # cross-jurisdiction surface to reconcile — the treaty re-sourcing
    # add-on component is identically zero, and the U.S. § 901 chain it
    # ties into does not run. The DE-side § 32d Abs. 5 EStG per-Posten
    # cap continues to apply inside the German capital rule graph.
    # Skipping the bridge keeps the audit graph faithful to what
    # actually executed instead of asserting a degenerate identity.
    # https://www.law.cornell.edu/uscode/text/26/6012
    # https://www.gesetze-im-internet.de/estg/__32d.html
    if YEAR_PATHS.profile_path.exists():
        profile = json.loads(YEAR_PATHS.profile_path.read_text(encoding="utf-8"))
    else:
        # Legacy unit-test entry points patch the loaders but do not
        # materialize a profile.json on disk. Default to bridge-runs
        # (us_filing_required=true) so those tests keep observing the
        # historical behaviour. The full pipeline (run_year.py) always
        # writes profile.json before reaching here.
        profile = {}
    if should_include_bridge_2025_stages(profile):
        bridge_initial_facts = bridge_initial_facts_2025(
            foreign_tax_1099_eur=inputs["foreign_tax_1099_eur"],
            bank_certificate_foreign_tax_credited_eur=(
                capital.bank_certificate_foreign_tax_credited_eur
            ),
            bank_certificate_foreign_tax_not_credited_eur=(
                capital.bank_certificate_foreign_tax_not_credited_eur
            ),
            treaty_us_source_dividend_allowed_us_tax_eur=(
                capital.treaty_us_source_dividend_allowed_us_tax_eur
            ),
            capital_explicit_foreign_tax_total_eur=(
                capital.explicit_foreign_tax_total
            ),
        )
        bridge_execution = execute_bridge_rule_graph(
            bridge_initial_facts,
            input_fingerprints=bridge_initial_fingerprints_2025(
                bridge_initial_facts
            ),
        )
        foreign_tax_reconciliation_total = bridge_execution.final_facts[
            "bridge.foreign_tax_reconciliation_total_eur"
        ]
        foreign_tax_reconciliation_status = bridge_execution.final_facts[
            "bridge.foreign_tax_reconciliation_status"
        ]
    vanilla_checkpoint = compute_germany_vanilla_checkpoint_2025(ordinary_inputs)
    combined_current_capital = capital.combined_current_capital_eur
    taxable_before_teilfreistellung = capital.taxable_before_teilfreistellung_eur
    capital_no_teilfreistellung = capital.capital_no_teilfreistellung
    if capital_no_teilfreistellung is None:
        raise ValueError("Germany capital assessment missing no-Teilfreistellung tax stage.")
    capital_tax_no_teilfreistellung = capital.capital_tax_no_teilfreistellung_eur
    teilfreistellung_reduction_base = capital.fund_teilfreistellung_reduction_eur
    taxable_after_teilfreistellung = capital.taxable_after_teilfreistellung_eur
    capital_with_teilfreistellung = capital.capital_with_teilfreistellung
    if capital_with_teilfreistellung is None:
        raise ValueError("Germany capital assessment missing post-Teilfreistellung tax stage.")
    capital_tax_with_teilfreistellung_before_treaty = capital.capital_tax_with_teilfreistellung_before_treaty_eur
    treaty_relieved_capital = capital.treaty_relieved_capital
    if treaty_relieved_capital is None:
        raise ValueError("Germany capital assessment missing treaty-credit check stage.")
    capital_tax_with_teilfreistellung_after_treaty = capital.capital_tax_with_teilfreistellung_after_treaty_eur

    domestic_capital_withholding_credit = capital.domestic_capital_withholding_credit_eur

    # § 31 EStG Familienleistungsausgleich Günstigerprüfung sub-graph
    # (Wave 11A). Sibling Pipeline 2 sub-graph that runs AFTER ordinary
    # (it reads the as-modeled zvE and income tax) and BEFORE the final
    # settlement (which consumes ``de.children.applied_relief_eur`` /
    # ``de.children.guenstigerpruefung_choice`` /
    # ``de.children.kindergeld_total_eur`` to apply § 31 Satz 4 EStG
    # netting). The children sub-graph reads ``de.derived.children_*``
    # from the persisted ``derived-facts.json`` produced by Pipeline 1
    # (DERIVE-DE25-CHILDREN). Demo posture (zero qualifying children)
    # short-circuits to all-zero outputs so demo numerics are unchanged.
    # Authority:
    #   § 31 EStG: https://www.gesetze-im-internet.de/estg/__31.html
    #   § 32 Abs. 6 EStG: https://www.gesetze-im-internet.de/estg/__32.html
    #   BKGG § 6 Abs. 2: https://www.gesetze-im-internet.de/bkgg_1996/
    children_assessment = compute_germany_children_assessment_2025(
        ordinary_taxable_income_eur=ordinary.joint_taxable_income_eur,
        ordinary_income_tax_eur=ordinary.joint_income_tax_eur,
        filing_posture=ordinary.filing_posture,
    )
    children_applied_relief = children_assessment.applied_relief_eur
    children_guenstigerpruefung_choice = (
        children_assessment.guenstigerpruefung_choice
    )
    children_kindergeld_total = children_assessment.kindergeld_total_eur

    # WS-4B (invariant migration plan §6): the headline refund
    # computation is now a LawStage. ``DE25-22-FINAL-REFUND`` consumes
    # the four ordinary/capital outputs plus the three children outputs
    # and produces the three refund values (``refund_before_treaty``,
    # ``chosen_refund_before_domestic_certificate``, ``target_refund``)
    # that previously were script-level Decimal arithmetic flagged by
    # invariants I2 (no fingerprint) and I5 (legal math outside the
    # rule graph). The math itself is § 36 Abs. 2 EStG netting plus
    # § 31 Satz 4 EStG Familienleistungsausgleich routing; promoting
    # it into a stage brings ``de.final.target_refund_eur`` inside the
    # audit graph.
    # Authority: § 36 Abs. 2 EStG; § 31 Satz 4 EStG; § 32d Abs. 1 EStG; InvStG § 20.
    germany_final_initial_facts = germany_final_initial_facts_2025(
        ordinary_refund_before_capital_eur=(
            ordinary.ordinary_refund_before_capital_eur
        ),
        capital_tax_with_teilfreistellung_before_treaty_eur=(
            capital_tax_with_teilfreistellung_before_treaty
        ),
        capital_tax_with_teilfreistellung_after_treaty_eur=(
            capital_tax_with_teilfreistellung_after_treaty
        ),
        domestic_capital_withholding_credit_eur=(
            domestic_capital_withholding_credit
        ),
        children_applied_relief_eur=children_applied_relief,
        children_guenstigerpruefung_choice=children_guenstigerpruefung_choice,
        children_kindergeld_total_eur=children_kindergeld_total,
    )
    germany_final_execution = execute_germany_final_rule_graph(
        germany_final_initial_facts,
        input_fingerprints=germany_final_initial_fingerprints_2025(
            germany_final_initial_facts
        ),
    )
    refund_before_treaty = germany_final_execution.final_facts[
        "de.final.refund_before_treaty_eur"
    ]
    chosen_refund_before_domestic_certificate = (
        germany_final_execution.final_facts[
            "de.final.chosen_refund_before_domestic_certificate_eur"
        ]
    )
    final_target = germany_final_execution.final_facts[
        "de.final.target_refund_eur"
    ]
    chosen_refund_before_equipment = final_target

    # F-DE-2: § 32d Abs. 6 EStG Günstigerprüfung shadow comparison.
    # AUDIT-ONLY — does NOT change final_target. Runs unconditionally so a
    # taxpayer in a low ordinary bracket gets a recommendation to elect
    # the § 32a tariff under § 32d Abs. 6, even though the engine still
    # fails closed when ``capital_guenstigerpruefung_requested=1`` (per
    # ``ensure_capital_guenstigerpruefung_position_2025``). The outputs
    # land under ``de.audit.*`` and surface in ``germany-model-results.json``
    # under ``audit_warnings``; no form line is written.
    # Authority:
    # - § 32d Abs. 6 EStG: https://www.gesetze-im-internet.de/estg/__32d.html
    # - § 32a Abs. 1 / Abs. 5 EStG: https://www.gesetze-im-internet.de/estg/__32a.html
    # - § 32d Abs. 5 EStG (FTC reads through): https://www.gesetze-im-internet.de/estg/__32d.html
    guenstiger_initial_facts = germany_guenstigerpruefung_initial_facts_2025(
        zve_ordinary_eur=ordinary.joint_taxable_income_eur,
        capital_taxable_after_teilfreistellung_eur=taxable_after_teilfreistellung,
        status_quo_total_tax_eur=capital_tax_with_teilfreistellung_after_treaty,
        foreign_tax_credit_applied_eur=(
            capital_with_teilfreistellung.foreign_tax_credit_eur
        ),
        filing_posture=ordinary.filing_posture,
    )
    guenstiger_execution = execute_germany_guenstigerpruefung_rule_graph(
        guenstiger_initial_facts,
        input_fingerprints=germany_guenstigerpruefung_initial_fingerprints_2025(
            guenstiger_initial_facts
        ),
    )
    guenstiger_diff = guenstiger_execution.final_facts[
        "de.audit.guenstigerpruefung_shadow_diff_eur"
    ]
    guenstiger_election_recommended = guenstiger_execution.final_facts[
        "de.audit.guenstigerpruefung_election_recommended"
    ]
    guenstiger_recommended_bool = guenstiger_election_recommended == D("1")

    equipment_total = sum((person.work_equipment_eur for person in ordinary.people), D("0.00"))
    other_income_22nr3_eur = ordinary.other_income_22nr3_eur
    other_income_22nr3_taxable = ordinary.other_income_22nr3_taxable_eur
    ordinary_people = tuple(getattr(ordinary, "people", ()))

    results = {
        "ordinary": {
            "gross_wages_eur": fmt(sum((person.wage.gross_wage_eur for person in ordinary_people), D("0.00"))),
            "work_expenses_eur": fmt(sum((person.allowed_werbungskosten_eur for person in ordinary_people), D("0.00"))),
            "net_employment_income_eur": fmt(getattr(ordinary, "sum_income_after_werbungskosten_eur", D("0.00"))),
            "other_income_22nr3_taxable_eur": fmt(getattr(ordinary, "other_income_22nr3_taxable_eur", D("0.00"))),
            "retirement_special_expenses_eur": fmt(getattr(ordinary, "retirement_contributions_eur", D("0.00"))),
            # C3-prereq (FORM-MAPPING-FOLLOWUP, 2026-05-03): the
            # § 10 Abs. 1 Nr. 3 + Nr. 3a + § 10 Abs. 4 EStG total
            # Vorsorgeaufwendungen is now a declared DE25-06-HEALTH-
            # VORSORGE-SA scalar output (``de.ordinary.health_vorsorge_total_eur``)
            # rather than a projection-side sum of two view-dataclass
            # fields. The pragma bypass is gone — this is now a direct
            # attribute read of a fingerprinted Decimal that lands on
            # Anlage Vorsorgeaufwand Zeilen 11-14 via the C3 renderer.
            # https://www.gesetze-im-internet.de/estg/__10.html
            "health_vorsorge_special_expenses_eur": fmt(
                getattr(ordinary, "health_vorsorge_total_eur", D("0.00"))
            ),
            # C3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket
            # scalars for Anlage Vorsorgeaufwand renderer. Each value is
            # a declared DE25-05 / DE25-06 scalar output flowing through
            # the executor's StageResult fingerprint chain.
            # https://www.gesetze-im-internet.de/estg/__10.html
            "vorsorge_retirement_total_eur": fmt(
                getattr(ordinary, "retirement_special_expenses_total_eur", D("0.00"))
            ),
            "vorsorge_basic_health_eur": fmt(
                getattr(ordinary, "health_vorsorge_basic_health_eur", D("0.00"))
            ),
            "vorsorge_other_allowed_eur": fmt(
                getattr(ordinary, "health_vorsorge_other_allowed_eur", D("0.00"))
            ),
            # C4 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-Zeile bucket
            # scalars for Anlage Sonderausgaben renderer.
            # https://www.gesetze-im-internet.de/estg/__10b.html
            # https://www.gesetze-im-internet.de/estg/__33a.html
            # https://www.gesetze-im-internet.de/estg/__10c.html
            "sonderausgaben_spenden_eur": fmt(
                getattr(ordinary, "spendenabzug_deductible_eur", D("0.00"))
            ),
            "sonderausgaben_unterhalt_eur": fmt(
                getattr(ordinary, "unterhaltsleistungen_deductible_eur", D("0.00"))
            ),
            "sonderausgaben_pauschbetrag_eur": fmt(
                getattr(ordinary, "sonderausgaben_pauschbetrag_applied_eur", D("0.00"))
            ),
            "total_special_expenses_eur": fmt(getattr(ordinary, "total_special_expenses_eur", D("0.00"))),
            "joint_taxable_income_eur": fmt(ordinary.joint_taxable_income_eur),
            "joint_income_tax_eur": fmt(ordinary.joint_income_tax_eur),
            "joint_solidarity_surcharge_eur": fmt(ordinary.joint_solidarity_surcharge_eur),
            "filing_posture": ordinary.filing_posture,
            "withheld_wage_tax_eur": fmt(ordinary.withheld_wage_tax_eur),
            "withheld_wage_solidarity_surcharge_eur": fmt(ordinary.withheld_wage_solidarity_surcharge_eur),
            "prepayments_eur": fmt(ordinary.prepayments_eur),
            "ordinary_refund_before_capital_eur": fmt(ordinary.ordinary_refund_before_capital_eur),
        },
        "capital": {
            "stock_gain_eur": fmt(capital.stock_gain),
            "dher_stock_gain_eur": fmt(capital.dher_stock_gain),
            "stock_loss_carryforward_2024_eur": fmt(inputs["stock_loss_carryforward_2024_eur"]),
            "stock_loss_carryforward_used_eur": fmt(capital.stock_loss_carryforward_used),
            "stock_loss_carryforward_remaining_eur": fmt(capital.stock_loss_carryforward_remaining),
            "stock_gain_after_carryforward_eur": fmt(capital.stock_gain_after_carryforward),
            "fund_gain_eur": fmt(capital.fund_gain),
            "fund_taxable_after_teilfreistellung_eur": fmt(capital.fund_taxable_after_teilfreistellung_eur),
            "option_gain_eur": fmt(capital.option_gain),
            "positive_income_total_eur": fmt(capital.positive_income_total),
            "saver_allowance_used_eur": fmt(capital.saver_allowance_used_eur),
            "explicit_foreign_tax_total_eur": fmt(capital.explicit_foreign_tax_total),
            "net_creditable_foreign_tax_total_eur": fmt(capital.net_creditable_foreign_tax_total),
            "foreign_tax_credit_cap_eur": fmt(capital.foreign_tax_credit_cap_eur),
            "foreign_tax_credit_applied_eur": fmt(capital_with_teilfreistellung.foreign_tax_credit_eur),
            "bank_certificate_income_eur": fmt(capital.bank_certificate_income_eur),
            "bank_certificate_stock_gain_eur": fmt(capital.bank_certificate_stock_gain_eur),
            "bank_certificate_non_stock_income_eur": fmt(capital.bank_certificate_non_stock_income_eur),
            "bank_certificate_saver_allowance_used_eur": fmt(capital.bank_certificate_saver_allowance_used_eur),
            "bank_certificate_foreign_tax_credited_eur": fmt(capital.bank_certificate_foreign_tax_credited_eur),
            "bank_certificate_foreign_tax_not_credited_eur": fmt(capital.bank_certificate_foreign_tax_not_credited_eur),
            "domestic_capital_tax_withheld_eur": fmt(capital.domestic_capital_tax_withheld_eur),
            "domestic_capital_soli_withheld_eur": fmt(capital.domestic_capital_soli_withheld_eur),
            "domestic_capital_withholding_credit_eur": fmt(domestic_capital_withholding_credit),
            "treaty_us_source_dividend_gross_eur": fmt(capital.treaty_us_source_dividend_gross_eur),
            "treaty_us_source_dividend_precredit_tax_eur": fmt(capital.treaty_us_source_dividend_precredit_tax_eur),
            "treaty_us_source_dividend_allowed_us_tax_eur": fmt(capital.treaty_us_source_dividend_allowed_us_tax_eur),
            "treaty_us_source_dividend_credit_eur": fmt(capital.treaty_us_source_dividend_credit_eur),
            "equity_fund_total_eur": fmt(capital.equity_fund_total),
            "non_equity_fund_total_eur": fmt(capital.non_equity_fund_total),
            "combined_current_capital_eur": fmt(combined_current_capital),
            "taxable_before_teilfreistellung_eur": fmt(taxable_before_teilfreistellung),
            "capital_income_tax_no_teilfreistellung_eur": fmt(capital_no_teilfreistellung.gross_income_tax_eur),
            "capital_tax_no_teilfreistellung_eur": fmt(capital_tax_no_teilfreistellung),
            "teilfreistellung_reduction_base_eur": fmt(teilfreistellung_reduction_base),
            "taxable_after_teilfreistellung_eur": fmt(taxable_after_teilfreistellung),
            "capital_income_tax_with_teilfreistellung_eur": fmt(capital_with_teilfreistellung.gross_income_tax_eur),
            "capital_income_tax_after_foreign_credit_eur": fmt(capital_with_teilfreistellung.income_tax_after_foreign_credit_eur),
            "capital_solidarity_surcharge_eur": fmt(capital_with_teilfreistellung.solidarity_surcharge_eur),
            "capital_tax_with_teilfreistellung_before_treaty_eur": fmt(capital_tax_with_teilfreistellung_before_treaty),
            "capital_tax_with_teilfreistellung_after_treaty_eur": fmt(capital_tax_with_teilfreistellung_after_treaty),
            "private_sale_loss_carryforward_2024_eur": fmt(inputs["private_sale_loss_carryforward_2024_eur"]),
            "private_sale_gains_2025_eur": fmt(inputs["private_sale_gains_2025_eur"]),
            "private_sale_loss_used_eur": fmt(min(inputs["private_sale_loss_carryforward_2024_eur"], inputs["private_sale_gains_2025_eur"])),  # pragma: legal-math-ok § 23 Abs. 3 Satz 7 EStG private-sale loss carryforward used; this is display-only audit row mirroring inputs already validated against § 23 EStG.
            "private_sale_loss_remaining_eur": fmt(inputs["private_sale_loss_carryforward_2024_eur"] - min(inputs["private_sale_loss_carryforward_2024_eur"], inputs["private_sale_gains_2025_eur"])),  # pragma: legal-math-ok § 23 Abs. 3 EStG private-sale loss remainder; display-only audit row.
        },
        "refunds": {
            "refund_before_treaty_eur": fmt(refund_before_treaty),
            "treaty_dividend_credit_eur": fmt(inputs["treaty_dividend_credit_eur"]),
            "chosen_refund_before_domestic_certificate_eur": fmt(chosen_refund_before_domestic_certificate),
            "domestic_capital_withholding_credit_eur": fmt(domestic_capital_withholding_credit),
            "chosen_refund_before_equipment_eur": fmt(chosen_refund_before_equipment),
            "equipment_work_share_total_eur": fmt(equipment_total),
            "other_income_22nr3_eur": fmt(other_income_22nr3_eur),
            "other_income_22nr3_taxable_eur": fmt(other_income_22nr3_taxable),
            "final_target_refund_eur": fmt(final_target),
        },
        "vanilla_checkpoint": {
            "taxable_income_eur": fmt(vanilla_checkpoint.taxable_income_eur),
            "income_tax_eur": fmt(vanilla_checkpoint.income_tax_eur),
            "soli_eur": fmt(vanilla_checkpoint.soli_eur),
            "total_tax_eur": fmt(vanilla_checkpoint.total_tax_eur),
            "refund_or_balance_due_eur": fmt(vanilla_checkpoint.refund_or_balance_due_eur),
        },
        "private_sales": {
            "private_sale_result_eur": fmt(coinbase["private_sale_result_eur"]),
            "prior_private_sale_carryforward_eur": fmt(coinbase["prior_private_sale_carryforward_eur"]),
            "updated_private_sale_carryforward_eur": fmt(coinbase["updated_private_sale_carryforward_eur"]),
        },
        # Phase 5.3 (FORM-MAPPING-FOLLOWUP, 2026-05-03): per-country
        # § 34c (1) EStG / § 32d Abs. 5 EStG foreign-tax-credit
        # breakdown for Anlage AUS rendering. The list is built by the
        # standalone ``derive_de_anlage_aus_2025`` derivation (no rule-
        # graph arithmetic). Strings are read directly from the
        # derived CSV so this projection contains zero Decimal math
        # (per invariant I5). The renderer wraps each Decimal-valued
        # cell in a LegalValue envelope via legal_value_from_decimal
        # using a renderer-side synthesized fingerprint (F-CQ-1
        # Shape-A wiring); the Anlage AUS Zeilen are declared on
        # DE25-18-SECTION-32D5-FTC's OutputDeclaration.form_line_refs
        # (per invariant I3).
        "anlage_aus": {
            "by_country": _read_anlage_aus_by_country_rows(YEAR_PATHS),
        },
        "assumptions": {
            "fund_classification": dict(sorted(fund_classification.items())),
        },
        # F-DE-2: § 32d Abs. 6 EStG Günstigerprüfung shadow audit. The
        # diff is positive ⇒ electing § 32a (Antragsveranlagung) would
        # reduce total tax by that amount; election_recommended is "1"
        # only when the diff exceeds the project materiality threshold
        # (see GUENSTIGERPRUEFUNG_MATERIALITY_EUR). The election is not
        # currently implemented — setting capital_guenstigerpruefung_requested=1
        # still fails closed in ensure_capital_guenstigerpruefung_position_2025.
        # Authority: § 32d Abs. 6 EStG (https://www.gesetze-im-internet.de/estg/__32d.html);
        # § 32a Abs. 1 / Abs. 5 EStG (https://www.gesetze-im-internet.de/estg/__32a.html).
        "audit_warnings": {
            "guenstigerpruefung_shadow": {
                "shadow_diff_eur": fmt(guenstiger_diff),
                "election_recommended": "1" if guenstiger_recommended_bool else "0",
                "materiality_threshold_eur": fmt(GUENSTIGERPRUEFUNG_MATERIALITY_EUR),
                "message": (
                    f"§ 32d Abs. 6 Günstigerprüfung: electing § 32a tariff "
                    f"would reduce total tax by {fmt(guenstiger_diff)} EUR. "
                    "The election is not currently implemented; setting "
                    "capital_guenstigerpruefung_requested=1 will fail closed. "
                    "Consider this manually."
                )
                if guenstiger_recommended_bool
                else (
                    f"§ 32d Abs. 6 Günstigerprüfung: shadow diff "
                    f"{fmt(guenstiger_diff)} EUR is below the "
                    f"{fmt(GUENSTIGERPRUEFUNG_MATERIALITY_EUR)} EUR materiality "
                    "threshold; § 32d Abs. 1 flat 25 % path remains favorable."
                ),
                "legal_reference": "§ 32d Abs. 6 EStG; § 32a Abs. 1 EStG; § 32a Abs. 5 EStG; § 32d Abs. 5 EStG",
                "authority_url": ESTG_32D_URL,
            },
        },
    }
    person_slots = _person_slots_for_projection_2025(ordinary)
    # Pass module-level CSV constants explicitly so tests that patch
    # ``germany_model.SALES_CSV`` / ``germany_model.INCOME_CSV`` reach the
    # loader (the loader's default falls back to germany_loaders module-level
    # state and would bypass the patch).
    sale_facts = load_capital_sale_facts_2025(SALES_CSV)
    income_facts = load_capital_income_facts_2025(INCOME_CSV)
    capital_form_projection = _capital_form_projection_2025(
        inputs=inputs,
        sale_facts=sale_facts,
        income_facts=income_facts,
        bank_certificates=bank_certificates,
        fund_classification=fund_classification,
        person_slots=person_slots,
        dher_stock_gain_eur=capital.dher_stock_gain,
        # InvStG § 19 Vorabpauschale (post-§ 20 Teilfreistellung) is
        # threaded into the KAP-form projection so the renderer reads
        # the fingerprinted Zeile-9-13 value rather than a hard-zero.
        # https://www.gesetze-im-internet.de/invstg_2018/__19.html
        vorabpauschale_taxable_after_teilfreistellung_eur=(
            capital.vorabpauschale_taxable_after_teilfreistellung_eur
        ),
    )
    people_projection = _person_projection_2025(ordinary, person_slots)
    person_1_projection = people_projection["person_1"]
    person_2_projection = people_projection.get("person_2")
    capital_audit = capital_form_projection["capital_audit"]
    entry_lines = [
        "# ELSTER Audit Summary - 2025",
        "",
        f"Current modeled filing result: **{fmt(final_target) if final_target >= D('0.00') else fmt(-final_target)} EUR {'refund' if final_target >= D('0.00') else 'balance due'}**.",
        "",
        "This file is rendered from the frozen Germany core model projection in `germany-model-results.json`.",
        "Use `outputs/forms/germany/` for the filing package. Do not use this audit summary as the primary form-entry surface.",
        "",
        "## Main Return Audit Notes",
        f"- Filing posture in the current model: {ordinary.filing_posture}.",
        f"- The `{fmt(ordinary_inputs.prepayments_eur)} EUR` prepayment remains an audit note only; ELSTER says the estimate-screen prepayment entry is not transmitted.",
        "",
        "## Wage Certificate Audit",
        f"- {person_1_projection['display_label']} wage-certificate values locked from the core model:",
        f"  - gross wage: `{person_1_projection['gross_wage_eur']} EUR`",
        f"  - wage tax: `{person_1_projection['withheld_wage_tax_eur']} EUR`",
        f"  - solidarity surcharge: `{person_1_projection['withheld_solidarity_surcharge_eur']} EUR`",
        f"  - line-10 multiannual-wage / compensation item on certificate: `{person_1_projection['multiannual_wage_eur']} EUR`",
        f"- {person_1_projection['display_label']} Werbungskosten audit totals from `germany-n-work-expenses.csv`:",
        f"  - `54-56` Arbeitsmittel: `{person_1_projection['work_equipment_eur']} EUR`",
        f"  - `58` Homeoffice-Tage: `{person_1_projection['home_office_days_without_visit']}`",
        f"  - `59` Homeoffice-Tage mit gleichzeitigem Tätigkeitsstättenbesuch: `{person_1_projection['home_office_days_with_visit']}`",
        f"  - `61-64` weitere Werbungskosten total: `{person_1_projection['other_work_expenses_eur']} EUR`",
    ]
    if person_2_projection is not None:
        entry_lines.extend(
            [
                f"- {person_2_projection['display_label']} wage-certificate values locked from the core model:",
                f"  - gross wage: `{person_2_projection['gross_wage_eur']} EUR`",
                f"  - wage tax: `{person_2_projection['withheld_wage_tax_eur']} EUR`",
                (
                    f"- No extra {person_2_projection['display_label']} Werbungskosten are included in the current refund model."
                    if D(person_2_projection["actual_werbungskosten_eur"]) == D("0.00")
                    else f"- {person_2_projection['display_label']} Werbungskosten are itemized in `germany-n-work-expenses.csv`."
                ),
            ]
        )
    entry_lines.extend(
        [
            "",
            "## Capital Audit Notes",
            f"- {person_1_projection['display_label']} foreign-capital lines are summarized in `germany-kap-summary.csv`.",
            # JStG 2024 (in Kraft 06.12.2024) deleted § 20 Abs. 6 Sätze 5
            # und 6 EStG; the former 2024 per-bucket Zeilen for
            # Termingeschäfte positives and Termingeschäfte losses are
            # dropped for VZ 2025. option_pos / option_neg components
            # remain audited inside the rule via the surviving Zeile 19.
            # BMF-VERIFIED 2026-05-13 against BMF 16.05.2025
            # Steuerbescheinigung-Schreiben.
            f"  - `19`: `{capital_audit['kap_line_19']} EUR`",
            f"  - `20`: `{capital_audit['stock_pos']} EUR`",
            f"  - `23`: `{capital_audit['stock_neg']} EUR`",
            f"  - `41`: `{capital_audit['foreign_tax_full']} EUR`",
            "",
            "## Fund And SO Audit Notes",
            f"- `KAP-INV Zeile 4`: `{capital_audit['fund_income_akt']} EUR`",
            f"- `KAP-INV Zeile 8`: `{capital_audit['fund_income_sonst']} EUR`",
            f"- `KAP-INV Zeile 14`: `{capital_audit['fund_sales_akt']} EUR`",
            f"- `KAP-INV Zeile 26`: `{capital_audit['fund_sales_sonst']} EUR`",
            "- `KAP-INV Zeilen 9 bis 13`: `0.00 EUR` in the current model; no separately identified 2024 Vorabpauschalen are in the file set.",
            f"- `Anlage SO` staking amount: `{fmt(other_income_22nr3_eur)} EUR`",
            f"- `Anlage SO` documented 2025 private-sale result: `{fmt(coinbase['private_sale_result_eur'])} EUR`",
            "- `Anlage SO Zeile 62`: leave blank in the current model because the private-sale bucket is already net negative.",
            "",
            "## Support Files",
            f"- `KAP` line summary: `{Path('germany-kap-summary.csv').name}`",
            f"- `Anlage N` deduction breakdown: `{Path('germany-n-work-expenses.csv').name}`",
            f"- `KAP-INV` per-fund summary: `{Path('germany-kap-inv-fund-summary.csv').name}`",
            "- Germany filing package: `outputs/forms/germany/`",
            "",
            "## Pre-Submit Checklist",
            "- Wage certificates: confirm all wage certificates are present and the imported values match the audit numbers above before you rely on the ELSTER calculation.",
            f"- {person_1_projection['display_label']} foreign-capital package: confirm `{person_1_projection['anlage_kap_label']}` includes lines `19`, `20`, `21`, `23`, `24`, and `41` with the values listed in this sheet. If these lines are missing, the ELSTER result will materially understate the capital side.",
            "- Investment funds: confirm `Anlage KAP-INV` includes lines `4`, `8`, `14`, and `26` with the values listed in this sheet. Do not enter every individual fund trade into ELSTER when the form is asking for the aggregate line totals.",
            f"- Other income / Anlage SO: confirm staking income `{fmt(other_income_22nr3_eur)} EUR` and private-sale result `{fmt(coinbase['private_sale_result_eur'])} EUR` are entered if those buckets are present in the year workspace.",
            f"- Prepayment: confirm the `{fmt(ordinary_inputs.prepayments_eur)} EUR` German prepayment is accounted for in your own pre-submit review even though the ELSTER estimate-screen field is not transmitted as part of the filing payload.",
            f"- Final anchor: after all entries are complete, the full modeled filing target is `{fmt(final_target) if final_target >= D('0.00') else fmt(-final_target)} EUR {'refund' if final_target >= D('0.00') else 'balance due'}`. A materially different ELSTER preview means a required bucket is still missing or mis-entered.",
            "",
            "## Official ELSTER Help / Law",
            f"- ELSTER 2025 help: {ELSTER_2025_URL}",
            f"- `§ 9 EStG`: {ESTG_9_URL}",
            f"- `§ 20 EStG`: {ESTG_20_URL}",
            f"- `§ 22 EStG`: {ESTG_22_URL}",
            f"- `§ 23 EStG`: {ESTG_23_URL}",
            f"- `§ 20 InvStG`: {INVSTG_20_URL}",
            "",
        ]
    )
    n_breakdown_rows = _ordinary_form_projection_rows_2025(ordinary, person_slots)
    # Anlage Kind projection — § 33b Abs. 5 EStG transferred Pauschbetrag.
    # The legally-effective EUR amount comes from the children sub-graph
    # output ``de.children.disability_pauschbetrag_transferred_eur`` per
    # invariant I11; here we shape the CSV row the renderer writes to
    # Anlage Kind 2025 Zeile 65 (BMF Steuerformular id 034025_25).
    # https://www.gesetze-im-internet.de/estg/__33b.html
    children_form_projection = _children_form_projection_2025(
        children_disability_pauschbetrag_transferred_eur=(
            children_assessment.disability_pauschbetrag_transferred_eur
        ),
    )
    results["children"] = {
        "disability_pauschbetrag_transferred_eur": fmt(
            children_assessment.disability_pauschbetrag_transferred_eur
        ),
        "guenstigerpruefung_choice": children_assessment.guenstigerpruefung_choice,
        "applied_relief_eur": fmt(children_assessment.applied_relief_eur),
        "kindergeld_total_eur": fmt(children_assessment.kindergeld_total_eur),
        "qualifying_children_count": (
            children_assessment.qualifying_children_count
        ),
        # C5 (FORM-MAPPING-FOLLOWUP, 2026-05-03): household-level
        # § 32 Abs. 6 EStG Kinderfreibetrag + BEA-Freibetrag total +
        # § 31 EStG Satz 1 Günstigerprüfung counterfactual tariff
        # saving. Both come from the DE25-CHILDREN-CREDITS rule outputs
        # ``de.children.kinderfreibetrag_total_eur`` and
        # ``de.children.kinderfreibetrag_tax_saving_eur``.
        # https://www.gesetze-im-internet.de/estg/__32.html
        # https://www.gesetze-im-internet.de/estg/__31.html
        "kinderfreibetrag_total_eur": fmt(
            children_assessment.kinderfreibetrag_total_eur
        ),
        "kinderfreibetrag_tax_saving_eur": fmt(
            children_assessment.kinderfreibetrag_tax_saving_eur
        ),
    }
    results["render_projection"] = {
        "elster": {
            "kap_summary_rows": capital_form_projection["kap_summary_rows"],
            "kap_inv_fund_rows": capital_form_projection["kap_inv_fund_rows"],
            "kind_summary_rows": children_form_projection["kind_summary_rows"],
            "n_breakdown_rows": n_breakdown_rows,
            "anlage_n_entries_by_slot": _anlage_n_entries_projection_2025(
                ordinary,
                person_slots,
                n_breakdown_rows,
            ),
            "capital_audit": capital_form_projection["capital_audit"],
            "entry_sheet_markdown": "\n".join(entry_lines),
            "person_2_bank_summary_markdown": "",
        }
    }

    RESULTS_JSON.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    set_pipeline_context_value(
        GERMANY_US_TREATY_DIVIDEND_CONTEXT_KEY,
        capital.treaty_dividend_packet_items,
    )
    write_germany_treaty_dividend_audit_2025(
        YEAR_PATHS,
        items=capital.treaty_dividend_packet_items,
    )

    ordinary_inputs_by_slot = {person.slot: person for person in ordinary_inputs.people}
    joint_other_vorsorge_cap = q2(
        sum((person.other_vorsorge_cap_eur for person in ordinary_inputs.people), D("0.00"))
    )
    joint_other_vorsorge_health_nursing_consumed = q2(
        min(ordinary.health_and_nursing_contributions_eur, joint_other_vorsorge_cap)
    )

    with TRACE_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["step", "value_eur", "note", "legal_reference", "authority_url", "precision_note"])
        if ordinary.filing_posture == "married_joint":
            assessment_reference = "§ 2 Abs. 2 bis 6 EStG; § 26 EStG; § 26b EStG; § 32a Abs. 5 EStG; § 36 Abs. 2 EStG"
            assessment_url = f"{ESTG_2_URL} | {ESTG_26_URL} | {ESTG_26B_URL} | {ESTG_32A_URL} | {ESTG_36_URL}"
            income_tax_reference = "§ 26b EStG; § 32a Abs. 1 und 5 EStG; BMF Programmablaufplan 2025"
            income_tax_note = "Tariff income tax under the 2025 splitting tariff"
            income_tax_url = f"{ESTG_32A_URL} | {BMF_PAP_2025_URL}"
        else:
            assessment_reference = "§ 2 Abs. 2 bis 6 EStG; § 32a Abs. 1 EStG; § 36 Abs. 2 EStG"
            assessment_url = f"{ESTG_2_URL} | {ESTG_32A_URL} | {ESTG_36_URL}"
            income_tax_reference = "§ 32a Abs. 1 EStG; BMF Programmablaufplan 2025"
            income_tax_note = "Tariff income tax under the 2025 basic tariff"
            income_tax_url = f"{ESTG_32A_URL} | {BMF_PAP_2025_URL}"
        write_trace_row(writer, "joint_assessment_order", D("0"), f"Ordinary-income assessment follows the statutory order gross income -> Werbungskosten -> Summe der Einkünfte -> Sonderausgaben -> zu versteuerndes Einkommen -> tarifliche Einkommensteuer -> Solidaritätszuschlag -> Steueranrechnung under filing posture {ordinary.filing_posture}", assessment_reference, assessment_url, "This trace is ordered to match the statute rather than the earlier worksheet sequence.")
        for person in ordinary.people:
            prefix = person.slot
            input_person = ordinary_inputs_by_slot[prefix]
            write_trace_row(writer, f"{prefix}_gross_wage", person.wage.gross_wage_eur, f"{person.order_label} gross wage aggregated from the wage certificate facts", "§ 19 Abs. 1 EStG", ESTG_19_URL)
            for item in person.work_equipment_items:
                write_trace_row(writer, f"{prefix}_equipment_{item.key}_gross", item.gross_amount_eur, "Gross invoice amount", "§ 9 Abs. 1 EStG", ESTG_9_URL)
                write_trace_row(writer, f"{prefix}_equipment_{item.key}_share", item.work_use_share, "Work-use share from config/manual_overrides.json", "§ 9 Abs. 1 EStG", ESTG_9_URL, "Share is a factual user allocation, not a statutory percentage.")
                write_trace_row(writer, f"{prefix}_equipment_{item.key}_work_share", item.deductible_amount_eur, "Gross amount multiplied by work-use share", "§ 9 Abs. 1 EStG", ESTG_9_URL)
            write_trace_row(writer, f"{prefix}_manual_work_equipment", person.manual_work_equipment_deduction_eur, f"{person.order_label} explicit manual work-equipment deduction position", "§ 9 Abs. 1 EStG", ESTG_9_URL, "This amount comes from config/manual_overrides.json rather than invoice-derived source facts.")
            write_trace_row(writer, f"{prefix}_work_equipment", person.work_equipment_eur, f"{person.order_label} deductible work-equipment share", "§ 9 Abs. 1 EStG", ESTG_9_URL)
            write_trace_row(writer, f"{prefix}_home_office_deduction", person.home_office_deduction_eur, f"{person.order_label} home-office Tagespauschale from configured days", "§ 4 Abs. 5 Satz 1 Nr. 6c; § 9 Abs. 5 EStG", f"{ESTG_4_5_6C_URL} | {ESTG_9_URL}", "Configured days are factual inputs from config/manual_overrides.json.")
            write_trace_row(writer, f"{prefix}_telecom_deduction", person.telecom_deduction_eur, f"{person.order_label} telecom deduction manual position", "§ 9 Abs. 1 EStG", ESTG_9_URL, "This is an explicit manual deduction position from config/manual_overrides.json, not a parser-derived amount.")
            write_trace_row(writer, f"{prefix}_employment_legal_insurance_deduction", person.employment_legal_insurance_deduction_eur, f"{person.order_label} work-related legal-insurance deduction manual position", "§ 9 Abs. 1 EStG", ESTG_9_URL, "The work-related share is a manual factual allocation from config/manual_overrides.json.")
            write_trace_row(writer, f"{prefix}_cross_border_tax_help_deduction", person.cross_border_tax_help_deduction_eur, f"{person.order_label} work-related tax-advice deduction manual position", "§ 9 Abs. 1 EStG; BMF Anhang 16 XIII", f"{ESTG_9_URL} | {TAX_ADVICE_BMF_URL}", "The deductible share is a manual factual allocation from config/manual_overrides.json.")
            write_trace_row(writer, f"{prefix}_actual_werbungskosten", person.actual_werbungskosten_eur, f"{person.order_label} actual Werbungskosten before the employee lump sum comparison", "§ 9 Abs. 1 EStG", ESTG_9_URL)
            write_trace_row(writer, f"{prefix}_allowed_werbungskosten", person.allowed_werbungskosten_eur, f"{person.order_label} allowed Werbungskosten after comparing actual deductions with the Arbeitnehmer-Pauschbetrag", "§ 9a Satz 1 Nr. 1 Buchst. a EStG", ESTG_9A_URL)
            write_trace_row(writer, f"{prefix}_income_after_werbungskosten", person.income_after_werbungskosten_eur, f"{person.order_label} employment income after Werbungskosten", "§ 2 Abs. 2 Satz 1 Nr. 2 EStG; § 19 EStG; § 9 EStG", f"{ESTG_2_URL} | {ESTG_19_URL} | {ESTG_9_URL}")
            write_trace_row(writer, f"{prefix}_employer_pension_contribution", person.wage.employer_pension_contribution_eur, f"{person.order_label} tax-free employer pension contribution tracked for audit but not deducted again", "§ 3 Nr. 62 EStG; § 10 Abs. 1 Nr. 2 Satz 6 und Abs. 3 Sätze 5 bis 6 EStG", f"{ESTG_3_URL} | {ESTG_10_URL}", "For joint assessment, the household retirement base is capped first and total employer shares are subtracted before any per-person audit allocation.")
            write_trace_row(writer, f"{prefix}_employee_pension_contribution", person.wage.employee_pension_contribution_eur, f"{person.order_label} employee pension contribution from the wage certificate", "§ 10 Abs. 1 Nr. 2 EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_retirement_contributions", person.retirement_contributions_eur, f"{person.order_label} deductible retirement contribution after the statutory employer-share reduction", "§ 10 Abs. 1 Nr. 2 Satz 6 und Abs. 3 Sätze 5 bis 6 EStG; § 3 Nr. 62 EStG", f"{ESTG_10_URL} | {ESTG_3_URL}")
            write_trace_row(writer, f"{prefix}_health_gross", input_person.wage.employee_health_insurance_eur, f"{person.order_label} statutory/basic health-insurance contribution before any Krankengeld reduction", "§ 10 Abs. 1 Nr. 3 Buchst. a EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_health_sick_pay_reduction", q2(input_person.wage.employee_health_insurance_eur * input_person.health_insurance_sick_pay_reduction_rate), f"{person.order_label} non-deductible sick-pay component removed from statutory health insurance", "§ 10 Abs. 1 Nr. 3 Satz 4 EStG", ESTG_10_URL, "The rate is loaded from config/manual_overrides.json and checked against people.csv Krankengeld entitlement.")
            write_trace_row(writer, f"{prefix}_nursing_care", input_person.wage.employee_nursing_care_insurance_eur, f"{person.order_label} nursing-care insurance contribution", "§ 10 Abs. 1 Nr. 3 Buchst. b EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_health_and_nursing", person.health_and_nursing_contributions_eur, f"{person.order_label} basic health and nursing insurance contributions after the § 10 Abs. 1 Nr. 3 Satz 4 sick-pay reduction", "§ 10 Abs. 1 Nr. 3 Buchst. a und b; Satz 4 EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_other_vorsorge_contributions", person.other_vorsorge_contributions_eur, f"{person.order_label} other Vorsorgeaufwendungen before the employee cap comparison", "§ 10 Abs. 1 Nr. 3a und Abs. 4 EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_other_vorsorge_allowed", person.other_vorsorge_allowed_eur, f"{person.order_label} allowed other Vorsorgeaufwendungen inside the § 10 Abs. 4 cap", "§ 10 Abs. 1 Nr. 3a, Abs. 4 EStG", ESTG_10_URL)
            write_trace_row(writer, f"{prefix}_special_expenses_total", person.total_special_expenses_eur, f"{person.order_label} total special-expense deduction used in the joint assessment", "§ 10 Abs. 1 Nr. 2, 3 und 3a EStG", ESTG_10_URL)
        write_trace_row(writer, "other_income_22nr3_eur", other_income_22nr3_eur, "Configured § 22 Nr. 3 amount from normalized/derived-facts/common/other-income-facts.csv", "§ 22 Nr. 3 EStG; BMF-Schreiben vom 06.03.2025 zu Kryptowerte", f"{ESTG_22_URL} | https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Einkommensteuer/2025-03-06-einzelfragen-kryptowerte-bmf-schreiben.pdf?__blob=publicationFile&v=2")
        write_trace_row(writer, "other_income_22nr3_freigrenze", inputs["other_income_22nr3_freigrenze_eur"], "§ 22 Nr. 3 EStG Freigrenze", "§ 22 Nr. 3 EStG", ESTG_22_URL)
        for person, taxable_other_income in zip(
            ordinary.people,
            ordinary.other_income_22nr3_by_person_taxable_eur,
            strict=True,
        ):
            write_trace_row(
                writer,
                f"{person.slot}_other_income_22nr3_taxable",
                taxable_other_income,
                f"{person.order_label} § 22 Nr. 3 taxable amount after applying the per-spouse Freigrenze",
                "§ 22 Nr. 3 EStG",
                ESTG_22_URL,
            )
        if other_income_22nr3_taxable > D("0.00"):
            other_income_note = "Full amount taxable because it reaches or exceeds the Freigrenze"
        else:
            other_income_note = "Amount not taxable because it does not reach the Freigrenze"
        write_trace_row(writer, "other_income_22nr3_taxable", other_income_22nr3_taxable, other_income_note, "§ 22 Nr. 3 EStG", ESTG_22_URL)
        write_trace_row(
            writer,
            "sum_income_after_werbungskosten",
            ordinary.sum_income_after_werbungskosten_eur,
            "Employment income after per-person Werbungskosten before adding taxable § 22 Nr. 3 income",
            "§ 2 Abs. 2 Satz 1 Nr. 2 EStG; § 19 EStG; § 9 EStG",
            f"{ESTG_2_URL} | {ESTG_19_URL} | {ESTG_9_URL}",
        )
        write_trace_row(
            writer,
            "sum_of_income",
            q2(ordinary.sum_income_after_werbungskosten_eur + ordinary.other_income_22nr3_taxable_eur),  # pragma: legal-math-ok § 2 Abs. 3 EStG Summe der Einkünfte; display-only trace row, the underlying components already trace to DE25-03 (sum_income_after_werbungskosten) and DE25-04 (other_income_22nr3_taxable).
            "Summe der Einkünfte after adding taxable § 22 Nr. 3 income to employment income",
            "§ 2 Abs. 3 EStG; § 22 Nr. 3 EStG",
            f"{ESTG_2_URL} | {ESTG_22_URL}",
        )
        write_trace_row(writer, "joint_other_vorsorge_cap", joint_other_vorsorge_cap, "Sum of the per-person § 10 Abs. 4 caps used for other Vorsorgeaufwendungen", "§ 10 Abs. 4 Satz 1 bis 4 EStG", ESTG_10_URL, "For joint assessment, § 10 Abs. 4 Satz 3 uses the sum of each spouse's applicable cap.")
        write_trace_row(writer, "joint_other_vorsorge_health_nursing_consumed", joint_other_vorsorge_health_nursing_consumed, "Basic health/nursing contributions consume the joint § 10 Abs. 4 cap before § 10 Abs. 1 Nr. 3a items", "§ 10 Abs. 4 Satz 3 und 4 EStG", ESTG_10_URL)
        write_trace_row(writer, "total_special_expenses", ordinary.total_special_expenses_eur, "Joint special expenses after applying the statutory categories and minimum Sonderausgaben-Pauschbetrag", "§ 10 Abs. 1 und Abs. 4 EStG; § 10c EStG", f"{ESTG_10_URL} | {ESTG_10C_URL}")
        write_trace_row(writer, "joint_taxable_income", ordinary.joint_taxable_income_eur, "Joint zu versteuerndes Einkommen", "§ 2 Abs. 5 EStG", ESTG_2_URL)
        write_trace_row(writer, "joint_income_tax", ordinary.joint_income_tax_eur, income_tax_note, income_tax_reference, income_tax_url)
        write_trace_row(writer, "joint_solidarity_surcharge", ordinary.joint_solidarity_surcharge_eur, "Solidarity surcharge on the ordinary assessment under the posture-specific 2025 threshold and mitigation-zone rules", "§ 3 und § 4 SolzG 1995; BMF Programmablaufplan 2025", f"{SOLZG_3_URL} | {SOLZG_4_URL} | {BMF_PAP_2025_URL}")
        write_trace_row(writer, "ordinary_refund_before_capital", ordinary.ordinary_refund_before_capital_eur, "Wage tax, wage soli, and prepayments less the exact ordinary assessment; withholding-credit sums are rounded up under § 36 Abs. 3 EStG", "§ 36 Abs. 2 und Abs. 3 EStG", ESTG_36_URL)
        write_trace_row(writer, "dher_stock_gain", capital.dher_stock_gain, "From germany-dher-results.json, based on Shareworks release values and JPM / Shareworks sale rows", "§ 19 EStG; § 20 Abs. 2 Satz 1 Nr. 1 und Abs. 4 EStG; § 19a EStG", f"{ESTG_19_URL} | {ESTG_20_URL} | {ESTH_19A_URL}", "Uses the Shareworks release / taxed compensation value as the basis anchor for the later capital sale calculation.")
        write_trace_row(writer, "stock_gain", capital.stock_gain, "From normalized/derived-facts/germany/capital-sales-detail.csv stock bucket plus any enabled equity-comp capital sidecar result", "§ 20 Abs. 2 Satz 1 Nr. 1 EStG", ESTG_20_URL)
        # § 20 Abs. 6 Satz 4 EStG carries the surviving Aktien-spezifischer
        # Verrechnungskreis (the stock-loss / stock-gain matching used for
        # the carryforward). § 20 Abs. 6 Sätze 5 und 6 EStG were deleted
        # by the JStG 2024 (Empfehlung Nr. 4a des Finanzausschusses, in
        # Kraft 06.12.2024, alle offenen Fälle), so the citation now reads
        # "Satz 4" only, not "Sätze 4 bis 6". Authority: BMF 16.05.2025
        # Steuerbescheinigung-Schreiben and § 20 EStG post-JStG-2024 text.
        # https://www.gesetze-im-internet.de/estg/__20.html
        write_trace_row(writer, "stock_loss_carryforward_2024", inputs["stock_loss_carryforward_2024_eur"], "From ESt-Verlustvortrag-Bescheid 2024.pdf, loss carryforward for share-sale capital income", "§ 20 Abs. 6 Satz 4 EStG; Verlustfeststellung per Bescheid", ESTG_20_URL)
        write_trace_row(writer, "stock_loss_carryforward_used", capital.stock_loss_carryforward_used, "Applied against positive 2025 stock-sale gains only", "§ 20 Abs. 6 Satz 4 EStG", ESTG_20_URL)
        write_trace_row(writer, "stock_gain_after_carryforward", capital.stock_gain_after_carryforward, "Positive 2025 stock-sale gains remaining after carryforward", "§ 20 Abs. 2 Satz 1 Nr. 1 EStG; § 20 Abs. 6 Satz 4 EStG", ESTG_20_URL)
        write_trace_row(writer, "fund_gain", capital.fund_gain, "From normalized/derived-facts/germany/capital-sales-detail.csv, fund_like bucket before Teilfreistellung", "InvStG § 16, § 19, § 20", INVSTG_20_URL)
        write_trace_row(writer, "fund_taxable_after_teilfreistellung", capital.fund_taxable_after_teilfreistellung_eur, "Fund bucket after applying InvStG § 20 partial exemptions to gains and InvStG § 21 partial deduction limits to losses", "InvStG § 20; InvStG § 21", f"{INVSTG_20_URL} | {INVSTG_21_URL}")
        write_trace_row(writer, "option_gain", capital.option_gain, "From normalized/derived-facts/germany/capital-sales-detail.csv, option bucket", "§ 20 Abs. 2 Satz 1 Nr. 3 EStG", ESTG_20_URL)
        write_trace_row(writer, "positive_income_total", capital.positive_income_total, "From normalized/derived-facts/germany/income-cashflows.csv excluding foreign_tax rows", "§ 20 Abs. 1 EStG", ESTG_20_URL)
        write_trace_row(writer, "combined_current_capital", combined_current_capital, "Stock gains after carryforward + fund gains + option gains + positive income", "§ 20 EStG; InvStG § 16, § 19, § 20", f"{ESTG_20_URL} | {INVSTG_20_URL}")
        write_trace_row(writer, "saver_allowance", capital.saver_allowance_used_eur, "Effective saver allowance used for the primary Germany capital package under the configured filing posture", "§ 20 Abs. 9 EStG", ESTG_20_URL)
        write_trace_row(writer, "taxable_before_teilfreistellung", taxable_before_teilfreistellung, "Combined current capital minus saver allowance", "§ 20 Abs. 9 EStG; § 32d Abs. 1 EStG", f"{ESTG_20_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "foreign_tax_1099_eur", inputs["foreign_tax_1099_eur"], "Full 1099 foreign tax converted to EUR before the per-item § 32d(5) cap", "§ 32d Abs. 5 EStG; R 34c (1) EStH 2025", f"{ESTG_32D_URL} | {BMF_ECB_URL}", "EUR conversion uses the saved ECB-rate convention.")
        write_trace_row(writer, "foreign_tax_credit_cap_eur", capital.foreign_tax_credit_cap_eur, "Creditable foreign tax after applying § 32d(5) per-item/source caps and reducing any refund entitlement", "§ 32d Abs. 5 EStG", ESTG_32D_URL, "Rows are matched by foreign_tax_item_id when present, otherwise by legacy symbol; refund entitlement must be explicit on foreign_tax rows.")
        write_trace_row(writer, "capital_income_tax_no_teilfreistellung_after_foreign_tax", capital_no_teilfreistellung.income_tax_after_foreign_credit_eur, "Flat-rate capital income tax after the statutory foreign-tax credit", "§ 32d Abs. 1 und 5 EStG", ESTG_32D_URL)
        write_trace_row(writer, "capital_soli_no_teilfreistellung", capital_no_teilfreistellung.solidarity_surcharge_eur, "Solidarity surcharge on the remaining flat-rate capital income tax", "§ 4 SolzG 1995", SOLZG_4_URL)
        write_trace_row(writer, "capital_tax_no_teilfreistellung", capital_tax_no_teilfreistellung, "25% capital income tax reduced by statutory foreign-tax credit, then 5.5% solidarity surcharge on the remaining tax", "§ 32d Abs. 1 und 5 EStG; § 4 SolzG 1995; BMF Abgeltungsteuer-Schreiben 14.05.2025", f"{ESTG_32D_URL} | {SOLZG_4_URL} | {BMF_ABGELTUNGSTEUER_URL}")
        write_trace_row(writer, "equity_fund_total", capital.equity_fund_total, "Fund gains + income for symbols explicitly classified as Aktienfonds", "InvStG § 20 Abs. 1", INVSTG_20_URL, "Fund classification is a manual tax-position assumption in config/manual_overrides.json.")
        write_trace_row(writer, "teilfreistellung_reduction_base", teilfreistellung_reduction_base, "Configured fund totals multiplied by their InvStG § 20 Teilfreistellung rates", "InvStG § 20 Abs. 1", INVSTG_20_URL)
        write_trace_row(writer, "taxable_after_teilfreistellung", taxable_after_teilfreistellung, "Taxable_before_teilfreistellung minus Teilfreistellung reduction base", "InvStG § 20 Abs. 1; § 32d Abs. 1 EStG", f"{INVSTG_20_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "capital_income_tax_with_teilfreistellung_after_foreign_tax", capital_with_teilfreistellung.income_tax_after_foreign_credit_eur, "Capital-income tax after Teilfreistellung and the statutory foreign-tax credit", "InvStG § 20 Abs. 1; § 32d Abs. 1 und 5 EStG", f"{INVSTG_20_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "capital_soli_with_teilfreistellung_before_treaty", capital_with_teilfreistellung.solidarity_surcharge_eur, "Solidarity surcharge on the remaining capital-income tax before any treaty-position relief", "§ 4 SolzG 1995", SOLZG_4_URL)
        write_trace_row(writer, "capital_tax_with_teilfreistellung_before_treaty", capital_tax_with_teilfreistellung_before_treaty, "Capital-income tax after statutory foreign-tax credit and capital soli, before the separate treaty-position credit", "InvStG § 20 Abs. 1; § 32d Abs. 1 und 5 EStG; § 4 SolzG 1995", f"{INVSTG_20_URL} | {ESTG_32D_URL} | {SOLZG_4_URL}")
        write_trace_row(writer, "treaty_us_source_dividend_allowed_us_tax", capital.treaty_us_source_dividend_allowed_us_tax_eur, "DBA-USA Article 10 caps the U.S. source-country tax on supported portfolio dividends before Germany applies the § 32d(5) per-item credit.", "DBA-USA Art. 10 und Art. 23; § 32d Abs. 5 EStG", f"{BMF_USA_PAGE_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "treaty_us_source_dividend_credit", capital.treaty_us_source_dividend_credit_eur, "Germany-side credit for supported U.S.-source dividends, computed inside the § 32d(5) credit path and exposed for the U.S. Pub. 514 worksheet.", "DBA-USA Art. 23; § 32d Abs. 5 EStG", f"{BMF_USA_PAGE_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "treaty_dividend_credit", inputs["treaty_dividend_credit_eur"], "Unsupported separate Germany treaty-position credit amount; must be zero in this model to avoid double-counting the § 32d(5) credit", "DBA-USA Art. 10 und Art. 23; § 32d Abs. 5 EStG", f"{BMF_USA_PAGE_URL} | {ESTG_32D_URL}", "Nonzero values fail closed in tax_pipeline/y2025/germany_law.py.")
        write_trace_row(writer, "capital_soli_with_teilfreistellung_after_treaty", treaty_relieved_capital.solidarity_surcharge_after_treaty_eur, "No separate Germany treaty-position credit is applied; capital soli remains the post-§32d(5) amount", "§ 32d Abs. 5 EStG; § 4 SolzG 1995", f"{ESTG_32D_URL} | {SOLZG_4_URL}")
        write_trace_row(writer, "capital_income_tax_with_teilfreistellung_after_treaty", treaty_relieved_capital.income_tax_after_treaty_eur, "No separate Germany treaty-position credit is applied; capital income tax remains the post-§32d(5) amount", "§ 32d Abs. 5 EStG", ESTG_32D_URL)
        write_trace_row(writer, "capital_tax_with_teilfreistellung_after_treaty", capital_tax_with_teilfreistellung_after_treaty, "Capital-income liability after confirming no separate Germany treaty-position credit is applied", "§ 32d Abs. 5 EStG", ESTG_32D_URL)
        write_trace_row(writer, "refund_before_treaty", refund_before_treaty, "Exact ordinary refund base minus capital tax before treaty credit", "§ 36 Abs. 2 EStG; § 32d Abs. 1 EStG", f"{ESTG_36_URL} | {ESTG_32D_URL}")
        write_trace_row(writer, "chosen_refund_before_domestic_certificate", chosen_refund_before_domestic_certificate, "Exact ordinary refund base minus capital tax after treaty credit, before domestic capital withholding credits", "§ 36 Abs. 2 EStG; § 32d Abs. 5 EStG", f"{ESTG_36_URL} | {ESTG_32D_URL}")
        if person_2_bank_certificate_has_amounts:
            write_trace_row(writer, "bank_certificate_capital_income", capital.bank_certificate_income_eur, "Typed bank-certificate line 7 income included inside the joint § 20 capital base", "§ 20 EStG", ESTG_20_URL, "Line 8 stock gains are treated as a subset of line 7, not added twice.")
            write_trace_row(writer, "bank_certificate_foreign_tax_credit", capital.bank_certificate_foreign_tax_credited_eur + capital.bank_certificate_foreign_tax_not_credited_eur, "Bank-certificate foreign tax included inside the § 32d Abs. 5 per-item credit cap", "§ 32d Abs. 5 EStG", ESTG_32D_URL)  # pragma: legal-math-ok display-only trace; the BRIDGE25-FOREIGN-TAX-RECONCILIATION stage already enforces the same sum as a legal invariant under § 32d Abs. 5 EStG.
            write_trace_row(writer, "domestic_capital_withholding_credit", domestic_capital_withholding_credit, "Bank-certificate Kapitalertragsteuer and solidarity surcharge credited after capital tax is computed", "§ 36 Abs. 2 Nr. 2 EStG; § 4 SolzG 1995", f"{ESTG_36_URL} | {SOLZG_4_URL}")
        else:
            write_trace_row(writer, "bank_certificate_status", D("0.00"), "No typed domestic bank-certificate capital facts are present in this workspace", "§ 20 EStG; § 36 Abs. 2 Nr. 2 EStG", f"{ESTG_20_URL} | {ESTG_36_URL}")
        if COINBASE_RESULTS_JSON.exists():
            write_trace_row(writer, "private_sale_loss_carryforward_2024", inputs["private_sale_loss_carryforward_2024_eur"], "From ESt-Verlustvortrag-Bescheid 2024.pdf", "§ 23 Abs. 3 Sätze 7 bis 9 EStG; Verlustfeststellung per Bescheid", ESTG_23_URL)
            write_trace_row(writer, "private_sale_gains_2025", inputs["private_sale_gains_2025_eur"], "Current model assumption: no documented 2025 § 23 gains in the base wage/capital model", "§ 23 Abs. 1 und 3 EStG", ESTG_23_URL, "The separate private-sale sidecar calculates the actual documented 2025 § 23 result.")
            write_trace_row(writer, "private_sale_loss_used", min(inputs["private_sale_loss_carryforward_2024_eur"], inputs["private_sale_gains_2025_eur"]), "Carryforward used against documented 2025 § 23 gains in the base model", "§ 23 Abs. 3 Sätze 7 bis 9 EStG", ESTG_23_URL)
            write_trace_row(writer, "private_sale_loss_remaining", inputs["private_sale_loss_carryforward_2024_eur"] - min(inputs["private_sale_loss_carryforward_2024_eur"], inputs["private_sale_gains_2025_eur"]), "Unused 2024 private-sale carryforward remaining in the base model before sidecar recomputation", "§ 23 Abs. 3 Sätze 7 bis 9 EStG", ESTG_23_URL)  # pragma: legal-math-ok § 23 Abs. 3 EStG private-sale loss remainder; display-only trace row.
            write_trace_row(writer, "coinbase_private_sale_result_2025", coinbase["private_sale_result_eur"], "Documented 2025 § 23 result from crypto-private-sales-results.json", "§ 23 Abs. 1 Satz 1 Nr. 2, Abs. 3 EStG", ESTG_23_URL)
            write_trace_row(writer, "coinbase_private_sale_carryforward_after_2025", coinbase["updated_private_sale_carryforward_eur"], "Updated expected private-sale loss carryforward after the sidecar recomputation", "§ 23 Abs. 3 Sätze 7 bis 9 EStG", ESTG_23_URL)
        final_note_parts = ["Exact ordinary assessment", "exact capital assessment", "treaty-position credit"]
        if person_2_bank_certificate_has_amounts:
            final_note_parts.append("domestic bank-certificate withholding credit")
        write_trace_row(writer, "final_target_refund", final_target, ", ".join(final_note_parts) + " combined", "§ 36 Abs. 2 EStG; § 32d EStG; InvStG § 20; § 22 Nr. 3 EStG", f"{ESTG_36_URL} | {ESTG_32D_URL} | {INVSTG_20_URL} | {ESTG_22_URL}", "No imported wage-side approximation or marginal-rate shortcut remains in this result.")
        # F-DE-2: § 32d Abs. 6 EStG Günstigerprüfung shadow audit row.
        # AUDIT-ONLY — does not feed final_target. Surfaces whether the
        # taxpayer would benefit from electing the § 32a tariff under
        # § 32d Abs. 6 instead of paying the § 32d Abs. 1 flat 25 %.
        guenstiger_note = (
            f"§ 32d Abs. 6 EStG shadow: electing § 32a would reduce capital tax "
            f"by {fmt(guenstiger_diff)} EUR. The election is not implemented; "
            "consider this manually."
            if guenstiger_recommended_bool
            else (
                f"§ 32d Abs. 6 EStG shadow: diff {fmt(guenstiger_diff)} EUR "
                f"is below the {fmt(GUENSTIGERPRUEFUNG_MATERIALITY_EUR)} EUR "
                "materiality threshold; § 32d Abs. 1 path remains favorable."
            )
        )
        write_trace_row(
            writer,
            "guenstigerpruefung_shadow_diff",
            guenstiger_diff,
            guenstiger_note,
            "§ 32d Abs. 6 EStG; § 32a Abs. 1 EStG; § 32a Abs. 5 EStG; § 32d Abs. 5 EStG",
            f"{ESTG_32D_URL} | {ESTG_32A_URL} | {BMF_ABGELTUNGSTEUER_URL}",
            "Audit-only diagnostic; does not change the modeled refund.",
        )

    taxable_income_label = "Household taxable income" if person_count > 1 else "Taxable income"
    income_tax_label = "Household income tax" if person_count > 1 else "Income tax"
    soli_label = "Household solidarity surcharge" if person_count > 1 else "Solidarity surcharge"
    assumptions_lines = [
        f"- Fund classifications: {', '.join(f'{symbol}={fund_type}' for symbol, fund_type in sorted(fund_classification.items())) or 'none'}",
        "- Fund-like symbols without an explicit classification fail closed because InvStG § 20 rates differ by fund type.",
        "- Separate Germany treaty-level dividend credits are unsupported unless modeled through the § 32d(5) per-item foreign-tax cap.",
        "- No § 34 uplift is used.",
    ]
    if equipment_total > D("0.00"):
        assumptions_lines.append(
            "- Work-equipment deductions come from explicit manual positions and configured work-use shares in `config/manual_overrides.json`."
        )
    else:
        assumptions_lines.append("- No separate work-equipment deduction is modeled in this demo workspace.")
    if capital.dher_stock_gain != D("0.00"):
        assumptions_lines.append(
            "- A separate equity-comp capital sidecar is included using release values as the basis anchor for the later capital-sale calculation."
        )
    else:
        assumptions_lines.append("- No separate equity-comp capital sidecar is included in this workspace.")
    if person_2_bank_certificate_has_amounts:
        assumptions_lines.append(
            "- Domestic bank tax certificates are typed inputs integrated into the joint § 20/§ 32d/§ 36 capital calculation; KEST/soli withholding is credited only after capital tax is computed."
        )
    else:
        assumptions_lines.append(
            "- No domestic bank tax certificates are included in this workspace."
        )
    assumptions_lines.append(
        f"- 2024 stock-loss carryforward used in the current capital model: {fmt(capital.stock_loss_carryforward_used)} EUR."
    )
    if COINBASE_RESULTS_JSON.exists():
        assumptions_lines.append(
            f"- 2024 private-sale loss carryforward remaining after the private-sale sidecar: {fmt(coinbase['updated_private_sale_carryforward_eur'])} EUR."
        )
    assumptions_lines.append(
        f"- Other income under § 22 Nr. 3 included in the ordinary assessment: {fmt(other_income_22nr3_eur)} EUR."
    )

    summary_lines = [
        "# Final German 2025 Result",
        "",
        "This file is generated by `python3 -m tax_pipeline.pipelines.y2025.germany_model` from structured year inputs under `normalized/` and `outputs/tax-positions/`, plus the derived capital and income CSV exports.",
        "",
        f"- Chosen filing target refund: **{fmt(final_target)} EUR**",
        f"- Exact ordinary refund before capital: {fmt(ordinary.ordinary_refund_before_capital_eur)} EUR",
        f"- Filing posture: {ordinary.filing_posture}",
        f"- {taxable_income_label}: {fmt(ordinary.joint_taxable_income_eur)} EUR",
        f"- {income_tax_label}: {fmt(ordinary.joint_income_tax_eur)} EUR",
        f"- {soli_label}: {fmt(ordinary.joint_solidarity_surcharge_eur)} EUR",
        f"- Capital tax with favorable equity-fund treatment before separate treaty credit: {fmt(capital_tax_with_teilfreistellung_before_treaty)} EUR",
        f"- Separate Germany treaty dividend credit included: {fmt(inputs['treaty_dividend_credit_eur'])} EUR",
        f"- Capital tax with favorable equity-fund treatment after separate treaty-credit check: {fmt(capital_tax_with_teilfreistellung_after_treaty)} EUR",
        f"- 2024 stock-loss carryforward used: {fmt(capital.stock_loss_carryforward_used)} EUR",
        f"- Work-equipment share included: {fmt(equipment_total)} EUR",
        f"- Other income included under § 22 Nr. 3: {fmt(other_income_22nr3_eur)} EUR",
        f"- Private-sale carryforward after 2025: {fmt(coinbase['updated_private_sale_carryforward_eur'])} EUR",
    ]
    if capital.dher_stock_gain != D("0.00"):
        summary_lines.append(f"- Equity-comp capital sidecar included: {fmt(capital.dher_stock_gain)} EUR")
    if domestic_capital_withholding_credit != D("0.00"):
        summary_lines.append(f"- Domestic bank withholding credit included under § 36: {fmt(domestic_capital_withholding_credit)} EUR")
    summary_lines.extend(
        [
            "",
            "## Vanilla checkpoint for commercial software comparison",
            "- Wage income only, with the normal statutory wage-side treatment still applied.",
            "- No KAP / KAP-INV / treaty / staking / private-sale / home-office / work-equipment / other manual deduction positions.",
            f"- Taxable income in the checkpoint: {fmt(vanilla_checkpoint.taxable_income_eur)} EUR",
            f"- Income tax in the checkpoint: {fmt(vanilla_checkpoint.income_tax_eur)} EUR",
            f"- Solidarity surcharge in the checkpoint: {fmt(vanilla_checkpoint.soli_eur)} EUR",
            f"- Total ordinary tax in the checkpoint: {fmt(vanilla_checkpoint.total_tax_eur)} EUR",
            f"- Refund or balance due in the checkpoint after wage withholding and the {fmt(ordinary_inputs.prepayments_eur)} EUR prepayment: {fmt(vanilla_checkpoint.refund_or_balance_due_eur)} EUR",
            "",
            "Audit posture:",
            "- The ordinary-income side is now recomputed directly from wage-document facts, explicit manual deduction positions, and the 2025 tariff / solidarity statutes.",
            "- The capital side keeps the existing matched sale and cashflow inputs, but foreign-tax credit sequencing now follows the statutory order instead of the old combined-rate shortcut.",
            "- Manual deduction positions remain explicit in `config/manual_overrides.json` rather than being hidden inside approximation rates.",
            "",
            "Generated files:",
            "- `analysis-steps/germany-model-results.json`",
            "- `analysis-steps/germany-model-trace.csv`",
            "- `analysis-steps/germany-summary.md`",
            "",
            "Key assumptions locked in the current model:",
            *assumptions_lines,
            "",
        ]
    )
    SUMMARY_MD.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    income_step_3 = (
        "3. The sum of income is formed under `§ 2 Abs. 3 EStG`."
        if ordinary.filing_posture == "single"
        else "3. The joint sum of income is formed under `§ 2 Abs. 3 EStG`."
    )
    tariff_step_6 = (
        "6. `zvE` is computed under `§ 2 Abs. 5 EStG` and taxed under the basic tariff in `§ 32a Abs. 1 EStG`."
        if ordinary.filing_posture == "single"
        else "6. Joint `zvE` is computed under `§ 2 Abs. 5 EStG` and taxed under the splitting tariff in `§ 26b` and `§ 32a Abs. 5 EStG`."
    )
    AUDIT_NOTE_MD.write_text(
        "\n".join(
            [
                "# Germany 2025 Legal Audit Note",
                "",
                "This file is generated to let a non-tax professional audit the Germany model against the statutory order and the concrete code entry points.",
                "",
                "## Statutory Order Used",
                "1. Employment income is determined from the wage certificates under `§ 19 EStG`.",
                "2. Werbungskosten are determined per person under `§ 9 EStG`, then compared against the Arbeitnehmer-Pauschbetrag under `§ 9a EStG`.",
                income_step_3,
                "4. `§ 22 Nr. 3 EStG` other income is added only after testing the Freigrenze.",
                "5. Sonderausgaben are deducted under `§ 10 EStG`, including the `§ 10 Abs. 1 Nr. 3 Satz 4 EStG` 4% sick-pay reduction for statutory health insurance and the `§ 10c EStG` minimum check.",
                tariff_step_6,
                "7. Ordinary solidarity surcharge is applied under `§ 3` and `§ 4 SolzG 1995`.",
                "8. Wage tax, wage soli, and prepayments are credited under `§ 36 Abs. 2 EStG`.",
                "9. Capital income is assessed separately under `§ 32d EStG` and `InvStG § 20`, with saver allowance first, then per-item/source capped foreign-tax credit under `§ 32d Abs. 5 EStG`, then capital soli.",
                "10. Separate Germany treaty-position dividend credits are rejected unless they are modeled as part of the `§ 32d Abs. 5 EStG` foreign-tax-credit calculation.",
                "",
                "## Code Entry Points",
                f"- Pure 2025 Germany law helpers: `tax_pipeline/y2025/germany_law.py` (`{ESTG_2_URL}`, `{ESTG_10_URL}`, `{ESTG_26B_URL}`, `{ESTG_32A_URL}`, `{SOLZG_3_URL}`)",
                "- Facts/config loader for those pure functions: `tax_pipeline/y2025/germany_inputs.py`",
                "- Staking-income input is sourced from `normalized/derived-facts/common/other-income-facts.csv`, not from a generated refund JSON.",
                f"- Capital-tax sequencing and foreign-tax credit caps: `tax_pipeline/y2025/germany_law.py` (`{ESTG_32D_URL}`, `{BMF_ABGELTUNGSTEUER_URL}`)",
                "- Top-level 2025 Germany model: `python3 -m tax_pipeline.pipelines.y2025.germany_model`",
                "- Filing sheet generator: `python3 -m tax_pipeline.pipelines.y2025.germany_elster_entry_sheet`",
                "",
                "## Manual Factual Positions Still Explicitly Configured",
                "- Home-office day counts",
                "- Telecom deduction amount",
                "- Employment legal-insurance deduction amount",
                "- Cross-border tax-help deduction amount",
                "- Work-use percentages for equipment",
                "- Non-Aktienfonds classification list",
                "- Unsupported separate treaty dividend credit amount, which must be zero",
                "",
                "These manual positions live in `config/manual_overrides.json` and are called out in the trace instead of being hidden inside approximation rates.",
                "",
                "## Current Locked Germany 2025 Result",
                f"- Final modeled refund: `{fmt(final_target)} EUR`",
                f"- Ordinary refund before capital: `{fmt(ordinary.ordinary_refund_before_capital_eur)} EUR`",
                f"- Capital tax after separate treaty-credit check: `{fmt(capital_tax_with_teilfreistellung_after_treaty)} EUR`",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
