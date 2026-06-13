from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from tax_pipeline.analysis_inputs import structured_input_files
from tax_pipeline.y2025.germany_law import GermanyUSTreatyDividendPacketItem2025
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.treaty_bridge import (
    US_TREATY_DIVIDEND_ITEMS_NAME,
    convert_germany_treaty_dividend_items_to_us_2025,
)
from tax_pipeline.y2025.us_law import (
    BUSINESS_INCOME_SOURCE_FOREIGN,
    BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED,
    BUSINESS_INCOME_SOURCES,
    GermanyTreatyDividendPacketItem2025,
    IRS_SCHEDULE_C_URL,
    MFS_CAPITAL_LOSS_LIMIT_USD,
    STANDARD_CAPITAL_LOSS_LIMIT_USD,
    USAssessmentInputs2025,
    USCapitalSourceFacts2025,
    USChild2025,
    USChildrenFacts2025,
    USFATCAFBARInputs2025,
    USFEIEInputs2025,
    USForeignFinancialAccount2025,
    USFTCInputs2025,
    USReturnProfile2025,
    USScheduleCInputs2025,
    USSelfEmploymentInputs2025,
    USC_162_URL,
    USC_199A_URL,
    USC_61_URL,
    USTaxConstants2025,
    USTreatyDividendItem2025,
    USTreatyInputs2025,
    schedule_c_net_profit_2025,
)

from datetime import date


# 26 U.S.C. § 24(c)(1) — qualifying child age limit (under 17 at end of
# tax year for CTC). § 152(c)(3) — qualifying child age limit (under 19,
# or under 24 if full-time student) for the dependent definition that
# also gates ODC for older dependents.
_CTC_QUALIFYING_AGE_CEILING = 17
_QUALIFYING_CHILD_AGE_CEILING = 19
TAX_YEAR_END_2025 = date(2025, 12, 31)


def _read_row_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: (value or "") for key, value in row.items() if key is not None} for row in csv.DictReader(handle)]


def _decimal_map(path: Path) -> dict[str, Decimal]:
    return {row["key"]: Decimal(row["value"]) for row in _read_row_csv(path)}


def _profile(paths: YearPaths) -> dict:
    return json.loads(paths.profile_path.read_text(encoding="utf-8"))


def _manual_overrides(paths: YearPaths) -> dict:
    return json.loads(paths.manual_overrides_path.read_text(encoding="utf-8"))


# 26 U.S.C. § 61 / § 162 Schedule C business-income source (Phase 2 freelancer
# support — the U.S. mirror of the German § 18 / § 4 Abs. 3 EÜR loader).
# config/us-business-income.csv carries the aggregated cash-basis totals as
# ``key,amount_usd,source,note`` rows with keys ``gross_receipts_usd`` /
# ``business_expenses_usd``. The jurisdiction-boundary rule: one economic fact,
# two legal classifications (the same receipts/expenses the German EÜR nets are
# the Schedule C gross income less § 162 expenses, restated in U.S. dollars).
US_BUSINESS_INCOME_FILE_NAME = "us-business-income.csv"


def _load_us_business_income_facts(paths: YearPaths) -> tuple[Decimal, Decimal, bool]:
    """Return ``(gross_receipts_usd, business_expenses_usd, file_declared)``.

    File-presence semantics (CLAUDE.md null/zero/missing): an absent file is
    "not declared" (``file_declared=False``); a header-only or populated file is
    "declared" and the missing rows are an explicit zero. The receiving loader
    uses ``file_declared`` to fail closed when a self-employment posture is
    active but no business facts exist. Mirrors ``germany_inputs.py``'s
    ``_load_business_income_facts`` exactly (same ``(value, file_declared)``
    contract). Authority: 26 U.S.C. § 61 / § 162; IRS Schedule C (Form 1040).
    """
    src = paths.config_root / US_BUSINESS_INCOME_FILE_NAME
    if not src.exists():
        return Decimal("0.00"), Decimal("0.00"), False
    gross_receipts = Decimal("0.00")
    business_expenses = Decimal("0.00")
    for row in _read_row_csv(src):
        key = (row.get("key") or "").strip()
        amount = (row.get("amount_usd") or "").strip()
        if not key:
            continue
        value = Decimal(amount) if amount else Decimal("0.00")
        if key == "gross_receipts_usd":
            gross_receipts += value
        elif key == "business_expenses_usd":
            business_expenses += value
        else:
            raise ValueError(
                f"Unknown us-business-income key {key!r} in "
                f"{US_BUSINESS_INCOME_FILE_NAME}; expected gross_receipts_usd / "
                f"business_expenses_usd (26 U.S.C. § 61 / § 162). Authority: "
                f"{IRS_SCHEDULE_C_URL}."
            )
    return gross_receipts, business_expenses, True


def _load_us_business_income_position(
    paths: YearPaths, profile: dict
) -> USScheduleCInputs2025 | None:
    """Resolve the 26 U.S.C. § 61 / § 162 Schedule C self-employment position.

    Returns ``None`` for a pure wage earner (``worker_type == "employee"``).
    Fails closed (with the cited authority) when a self-employment
    ``worker_type`` is declared but the business-income facts are absent, and
    fails closed on ``business_income_source == "us_effectively_connected"``
    (the 26 U.S.C. § 199A QBI-granting path is not yet modeled — the W-2-wage /
    UBIA / SSTB above-threshold limits need verified 2025 thresholds).

    ``worker_type`` is the SAME shared position the German § 18 loader reads
    (``elections.worker_type``): a U.S.-citizen freelancer in Germany is
    self-employed on both sides. ``business_income_source`` defaults to
    ``foreign`` (the cited § 199A(c)(3)(A)(i) / § 864(c) position for this
    engine's taxpayer); see ``qbi_gate_2025``.
    """
    elections = profile.get("elections", {}) if isinstance(profile, dict) else {}
    worker_type = str(elections.get("worker_type", "employee")).strip() or "employee"
    if worker_type == "employee":
        return None
    if worker_type not in ("self_employed", "both"):
        raise ValueError(
            f"Unsupported worker_type {worker_type!r}; expected one of "
            "'employee', 'self_employed', 'both'."
        )
    business_income_source = (
        str(elections.get("business_income_source", BUSINESS_INCOME_SOURCE_FOREIGN)).strip()
        or BUSINESS_INCOME_SOURCE_FOREIGN
    )
    if business_income_source not in BUSINESS_INCOME_SOURCES:
        raise ValueError(
            f"Unsupported business_income_source {business_income_source!r}; "
            f"expected one of {BUSINESS_INCOME_SOURCES} "
            f"(26 U.S.C. § 199A(c)(3)(A)(i) / § 864(c)). Authority: {USC_199A_URL}."
        )
    if business_income_source == BUSINESS_INCOME_SOURCE_US_EFFECTIVELY_CONNECTED:
        # The § 199A QBI-granting path (US-effectively-connected business
        # income) is not modeled: the W-2-wage / UBIA / SSTB above-threshold
        # limits need VERIFIED 2025 § 199A taxable-income thresholds from the
        # Rev. Proc. The engine fails closed rather than guessing a granted
        # deduction (a LEAK-class over-deduction is the inverse of an
        # understatement, equally forbidden).
        raise NotImplementedError(
            "elections.business_income_source='us_effectively_connected' would "
            "grant a 26 U.S.C. § 199A QBI deduction, but the W-2-wage / UBIA / "
            "SSTB above-threshold limits (verified 2025 § 199A thresholds) are "
            f"not modeled. The engine fails closed. Authority: {USC_199A_URL}."
        )
    gross_receipts, business_expenses, declared = _load_us_business_income_facts(paths)
    if not declared:
        raise ValueError(
            "worker_type declares self-employment but no U.S. business-income "
            f"facts were found ({US_BUSINESS_INCOME_FILE_NAME}). The 26 U.S.C. "
            "§ 61 / § 162 Schedule C netting needs gross receipts and business "
            f"expenses. Authority: {USC_61_URL} / {USC_162_URL} / "
            f"{IRS_SCHEDULE_C_URL}."
        )
    return USScheduleCInputs2025(
        gross_receipts_usd=gross_receipts,
        business_expenses_usd=business_expenses,
        business_income_source=business_income_source,
    )


def _usa_filing_posture(profile: dict) -> str:
    text = str(profile.get("jurisdictions", {}).get("usa", {}).get("filing_posture", "")).strip().lower()
    if not text:
        # Filing posture selects threshold-sensitive rules under 26 U.S.C.
        # § 1, § 63, § 1211(b), and § 1411. A missing posture is not a legal
        # election, so fail closed instead of falling back to MFS/NRA spouse.
        raise ValueError("config/profile.json must provide an explicit U.S. filing_posture")
    aliases = {
        "single": "single",
        "mfs": "mfs_nra_spouse",
        "mfs_nra_spouse": "mfs_nra_spouse",
        "married_joint": "married_joint",
        "joint": "married_joint",
        "mfj": "married_joint",
    }
    if text not in aliases:
        # Filing posture chooses the thresholds for 26 U.S.C. § 1, § 63,
        # § 1211(b), and § 1411. Unknown text must fail closed instead of
        # falling through to married-filing-separately.
        raise ValueError(
            "Unsupported U.S. filing posture in config/profile.json: "
            f"{text!r}. Expected one of: " + ", ".join(sorted(aliases))
        )
    return aliases[text]


def _required_profile_value(profile: dict, path: tuple[str, ...], *, label: str) -> object:
    current: object = profile
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise ValueError(f"Missing required {label} in config/profile.json")
        current = current[key]
    return current


def _required_profile_text(profile: dict, path: tuple[str, ...], *, label: str) -> str:
    value = _required_profile_value(profile, path, label=label)
    text = str(value).strip()
    if not text:
        raise ValueError(f"Missing required {label} in config/profile.json")
    return text


def _required_profile_bool(profile: dict, path: tuple[str, ...], *, label: str) -> bool:
    value = _required_profile_value(profile, path, label=label)
    if not isinstance(value, bool):
        raise ValueError(f"Missing required {label} in config/profile.json")
    return value


def _optional_profile_bool(profile: dict, path: tuple[str, ...]) -> bool | None:
    current: object = profile
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    if isinstance(current, bool):
        return current
    return None


def _required_assumption_decimal(assumptions: dict[str, Decimal], key: str, *, label: str) -> Decimal:
    if key not in assumptions:
        raise ValueError(f"Missing required U.S. assumption: {label}")
    return assumptions[key]


def _required_assumption_bool(assumptions: dict[str, Decimal], key: str, *, label: str) -> bool:
    value = _required_assumption_decimal(assumptions, key, label=label)
    if value not in (Decimal("0"), Decimal("1")):
        raise ValueError(f"Invalid U.S. assumption {label}: expected 0 or 1")
    return bool(value)


def _load_us_treaty_dividend_items_2025(
    paths: YearPaths,
) -> tuple[tuple[USTreatyDividendItem2025, ...], bool]:
    """Load U.S. treaty dividend items and report whether the file was declared.

    Returns ``(items, file_present)``. The file-presence flag separates three
    states the engine must keep distinct (see CLAUDE.md "Null / zero / missing"):

    * **missing** — ``us-treaty-dividend-items.csv`` does not exist. The U.S.
      side has not declared a Pub. 514 treaty position at all. Caller must
      treat an explicit same-run Germany packet as a coverage contract
      violation, not silently re-source as zero.
    * **empty** — file exists with only a header. The U.S. side has
      explicitly declared zero items (e.g., § 20 Abs. 9 Sparer-Pauschbetrag
      shelters all U.S.-source dividends). Pub. 514 worksheet legitimately
      evaluates to zero on both sides.
    * **populated** — file lists items. Standard coverage-matching path.

    Source: https://www.irs.gov/publications/p514.
    """
    source = paths.tax_positions_root / US_TREATY_DIVIDEND_ITEMS_NAME
    if not source.exists():
        return (), False
    items: list[USTreatyDividendItem2025] = []
    seen: set[str] = set()
    for row in _read_row_csv(source):
        item_id = str(row.get("item_id", "")).strip()
        if not item_id:
            continue
        if item_id in seen:
            raise ValueError(f"Duplicate U.S. treaty dividend item_id: {item_id}")
        seen.add(item_id)
        items.append(
            USTreatyDividendItem2025(
                item_id=item_id,
                treaty_bucket=str(row.get("treaty_bucket", "")).strip(),
                gross_dividend_usd=Decimal(row["gross_dividend_usd"]),
            )
        )
    return tuple(items), True


def _germany_treaty_dividend_outputs_usd(
    *,
    germany_treaty_dividend_items: tuple[GermanyUSTreatyDividendPacketItem2025, ...] | None,
    us_treaty_dividend_items: tuple[USTreatyDividendItem2025, ...],
    eur_per_usd: Decimal,
) -> tuple[
    Decimal | None,
    Decimal | None,
    Decimal | None,
    Decimal | None,
    tuple[GermanyTreatyDividendPacketItem2025, ...],
]:
    if germany_treaty_dividend_items is None:
        return None, None, None, None, ()
    cent = Decimal("0.01")
    items = convert_germany_treaty_dividend_items_to_us_2025(
        germany_items=germany_treaty_dividend_items,
        us_items=us_treaty_dividend_items,
        eur_per_usd=eur_per_usd,
    )
    if not items:
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), ()
    return (
        sum((item.gross_dividend_usd for item in items), Decimal("0.00")).quantize(cent, rounding=ROUND_HALF_UP),
        sum((item.article_10_source_tax_ceiling_usd for item in items), Decimal("0.00")).quantize(cent, rounding=ROUND_HALF_UP),
        sum((item.german_precredit_tax_on_us_source_dividend_usd for item in items), Decimal("0.00")).quantize(cent, rounding=ROUND_HALF_UP),
        sum((item.german_residence_credit_for_us_tax_usd for item in items), Decimal("0.00")).quantize(cent, rounding=ROUND_HALF_UP),
        tuple(items),
    )


def _parse_int_field(raw: str, *, label: str, default: int = 0) -> int:
    text = (raw or "").strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid integer for {label}: {raw!r}") from exc


def _parse_decimal_field(raw: str, *, label: str, default: str = "0") -> Decimal:
    text = (raw or "").strip()
    if not text:
        return Decimal(default)
    try:
        return Decimal(text)
    except Exception as exc:  # pragma: no cover - delegated to Decimal
        raise ValueError(f"Invalid decimal for {label}: {raw!r}") from exc


def _age_at_year_end_2025(date_of_birth: str) -> int:
    """Return the child's age on 2025-12-31 per § 152(c)(3) ordering."""
    text = (date_of_birth or "").strip()
    if not text:
        # Without a date of birth we cannot run § 24(c)(1) or § 152(c)(3)
        # ordering, so the row cannot qualify for CTC. Treat as adult so
        # downstream code denies CTC unless the date is filled.
        return 99
    try:
        dob = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"config/children.csv date_of_birth must be ISO YYYY-MM-DD; got {date_of_birth!r}"
        ) from exc
    end = TAX_YEAR_END_2025
    age = end.year - dob.year - (1 if (end.month, end.day) < (dob.month, dob.day) else 0)
    return age


def _classify_child_2025(row: dict[str, str]) -> USChild2025:
    """Classify one row of ``config/children.csv`` per § 24 + § 152.

    Authority:
      - § 24(c)(1) — CTC requires the child to be under age 17.
      - § 24(h)(7) — CTC requires a valid SSN issued before the return
        due date. ITIN-only children fail the CTC SSN test and route to
        the § 24(h)(4) ODC instead.
      - § 24(h)(4) — ODC: $500 for a qualifying child age 17+ (or a CTC
        child denied for SSN reasons), or for a qualifying relative
        with a TIN.
      - § 152(c) — qualifying child definition; § 152(c)(1)(B) treats
        time abroad with a U.S.-citizen parent as time with the
        taxpayer, so the loader does NOT require physical U.S.
        presence.
    """
    child_id = (row.get("child_id") or "").strip()
    if not child_id:
        raise ValueError("config/children.csv: every populated row must have a child_id")
    name = (row.get("name") or "").strip()
    date_of_birth = (row.get("date_of_birth") or "").strip()
    ssn = (row.get("ssn") or "").strip()
    itin = (row.get("itin") or "").strip()
    relationship = (row.get("relationship") or "").strip().lower() or "qualifying_child"
    months_in_us_household = _parse_int_field(
        row.get("months_in_us_household", ""),
        label=f"children.csv:{child_id}.months_in_us_household",
    )
    annual_gross_income_usd = _parse_decimal_field(
        row.get("annual_gross_income_usd", ""),
        label=f"children.csv:{child_id}.annual_gross_income_usd",
    )
    disability_gdb = _parse_int_field(
        row.get("disability_gdb", ""),
        label=f"children.csv:{child_id}.disability_gdb",
    )
    age = _age_at_year_end_2025(date_of_birth)
    has_ssn = bool(ssn)
    has_itin = bool(itin)
    # § 24(c)(1) and § 24(h)(7): CTC eligibility requires (i) under 17,
    # (ii) qualifying-child relationship, (iii) a valid SSN, and (iv)
    # months living with the taxpayer > half the year (~ 6 months).
    qualifies_for_ctc = (
        relationship == "qualifying_child"
        and age < _CTC_QUALIFYING_AGE_CEILING
        and has_ssn
        and months_in_us_household > 6
    )
    # § 24(h)(4): ODC catches both (a) qualifying-relative dependents and
    # (b) CTC-shaped children who fail the CTC SSN/age tests but still
    # have a TIN (SSN or ITIN). Months > half year is required for the
    # underlying § 152(c) qualifying-child relationship; for qualifying
    # relatives § 152(d) does not have the months-in-household test, so
    # the loader uses presence of a TIN + recognized relationship.
    qualifies_for_odc = False
    if not qualifies_for_ctc:
        if relationship == "qualifying_relative" and (has_ssn or has_itin):
            qualifies_for_odc = True
        elif relationship == "qualifying_child":
            # Still a qualifying child for § 152(c) but fails CTC under
            # § 24(c)(1) (age 17+) or § 24(h)(7) (no SSN). § 24(h)(4)
            # routes to ODC if there is a TIN and either age >= 17
            # (still under 19/24 dependent test) or no SSN.
            if (has_ssn or has_itin) and age < 24 and months_in_us_household > 6:
                qualifies_for_odc = True
    return USChild2025(
        child_id=child_id,
        name=name,
        date_of_birth=date_of_birth,
        ssn=ssn,
        itin=itin,
        relationship=relationship,
        months_in_us_household=months_in_us_household,
        annual_gross_income_usd=annual_gross_income_usd,
        disability_gdb=disability_gdb,
        age_at_year_end=age,
        qualifies_for_ctc=qualifies_for_ctc,
        qualifies_for_odc=qualifies_for_odc,
    )


def load_us_children_facts_2025(paths: YearPaths) -> USChildrenFacts2025:
    """Load ``config/children.csv`` and classify each row per § 24 + § 152.

    Empty file (header only) or missing file → zero-count facts. The
    file is treated as an opt-in artifact: when absent the engine emits
    zero credits, preserving demo numerics.

    Authority: 26 U.S.C. §§ 24, 152.
    https://www.law.cornell.edu/uscode/text/26/24
    https://www.law.cornell.edu/uscode/text/26/152
    """
    source = paths.config_root / "children.csv"
    if not source.exists():
        return USChildrenFacts2025(
            children=(),
            children_count_qualifying_for_ctc=0,
            children_count_qualifying_for_odc=0,
        )
    rows = _read_row_csv(source)
    children: list[USChild2025] = []
    seen_ids: set[str] = set()
    for raw_row in rows:
        # Skip blank rows: when every meaningful field is empty.
        meaningful = any(
            (raw_row.get(col) or "").strip()
            for col in (
                "child_id",
                "name",
                "date_of_birth",
                "ssn",
                "itin",
                "relationship",
                "months_in_us_household",
                "annual_gross_income_usd",
            )
        )
        if not meaningful:
            continue
        child = _classify_child_2025(raw_row)
        if child.child_id in seen_ids:
            raise ValueError(
                f"config/children.csv: duplicate child_id {child.child_id!r}"
            )
        seen_ids.add(child.child_id)
        children.append(child)
    ctc_count = sum(1 for c in children if c.qualifies_for_ctc)
    odc_count = sum(1 for c in children if c.qualifies_for_odc)
    return USChildrenFacts2025(
        children=tuple(children),
        children_count_qualifying_for_ctc=ctc_count,
        children_count_qualifying_for_odc=odc_count,
    )


def _profile_residency_basis_for_fatca(profile: dict) -> str:
    """Map profile.json fields onto the Reg. § 1.6038D-2(b)(1) tier.

    The conservative default is ``"domestic"`` — only return an
    ``"abroad_*"`` tier when the profile clearly evidences one of the
    two § 911(d)(1) tests Reg. § 1.6038D-2(b)(1) cross-references:

    1. **§ 911(d)(1)(A)** — bona-fide residence abroad
       (``primary_tax_residence`` is a non-US country AND
       ``us_citizen_or_long_term_resident`` is true). For brenn-2025
       this is the load-bearing branch and the result is
       ``abroad_section_911_d_1_a``.
    2. **§ 911(d)(1)(B)** — 330 full days of physical presence in a
       foreign country during any 12-month period ending in the tax
       year. The profile may carry an integer
       ``days_outside_us_during_year`` fact under the top-level key OR
       under ``taxpayer.days_outside_us_during_year``; when it is set
       and ``>= 330`` the function returns
       ``abroad_330_day_physical_presence``. The 330 threshold is the
       statutory floor under § 911(d)(1)(B); Reg. § 1.6038D-2(b)(1)
       extends the same "presence abroad" branch to Form 8938
       thresholds.

    Authority: 26 U.S.C. § 911(d)(1) — https://www.law.cornell.edu/uscode/text/26/911
    Reg. § 1.6038D-2(b)(1) — https://www.law.cornell.edu/cfr/text/26/1.6038D-2

    Phase 5.1 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the 330-day branch
    was previously deferred. ``days_outside_us_during_year`` is an
    OPTIONAL fact — when absent the auto-derivation falls back to the
    bona-fide-resident logic. For brenn-2025 the bona-fide branch
    already fires (primary_tax_residence == "DE" + US citizen), so the
    330-day branch is non-load-bearing for him; it lights up the tier
    only for U.S. citizens / long-term residents whose primary tax
    residence cannot be established under § 911(d)(1)(A) (e.g. itinerant
    expats with no settled fiscal home).
    """
    primary = str(profile.get("primary_tax_residence", "")).strip().upper()
    us_citizen = bool(profile.get("us_citizen_or_long_term_resident", False))
    # § 911(d)(1)(A) bona-fide residence — primary tax residence in a
    # foreign country plus U.S. citizenship is the classic abroad tier
    # for Form 8938. Take this branch first because it does not depend
    # on a day-count fact.
    if primary and primary != "US" and us_citizen:
        return "abroad_section_911_d_1_a"
    # § 911(d)(1)(B) physical-presence test — 330 full days in any
    # foreign country during a 12-month period ending in the tax year.
    # The day-count fact is optional; when missing or < 330 the function
    # falls through to ``"domestic"``. Only U.S. citizens / long-term
    # residents qualify for the abroad tier under Reg. § 1.6038D-2(b)(1).
    if us_citizen:
        days_outside = _profile_days_outside_us(profile)
        if days_outside is not None and days_outside >= 330:
            return "abroad_330_day_physical_presence"
    return "domestic"


def _profile_days_outside_us(profile: dict) -> int | None:
    """Read the optional ``days_outside_us_during_year`` fact.

    Looks under the top-level key first, then under
    ``taxpayer.days_outside_us_during_year``. Returns ``None`` when
    neither is present or when the value cannot be parsed as a
    non-negative integer (silent absence is the documented contract).

    The fact only feeds the § 911(d)(1)(B) physical-presence branch of
    ``_profile_residency_basis_for_fatca``; if a future workspace ever
    needs to claim the abroad-presence tier without a bona-fide
    residence, set this fact to a value ``>= 330``.
    """
    candidates: list[object] = []
    top = profile.get("days_outside_us_during_year")
    if top is not None:
        candidates.append(top)
    taxpayer = profile.get("taxpayer")
    if isinstance(taxpayer, dict):
        nested = taxpayer.get("days_outside_us_during_year")
        if nested is not None:
            candidates.append(nested)
    for raw in candidates:
        try:
            days = int(raw)
        except (TypeError, ValueError):
            continue
        if days < 0:
            continue
        return days
    return None


def _ffa_row_to_account(
    row: dict[str, str],
    *,
    csv_label: str,
) -> USForeignFinancialAccount2025:
    """Translate a CSV row into a ``USForeignFinancialAccount2025``."""
    account_id = (row.get("account_id") or "").strip()
    is_sffa_text = (row.get("is_specified_foreign_financial_asset") or "").strip().lower()
    is_sffa = is_sffa_text in {"true", "yes", "1"}
    return USForeignFinancialAccount2025(
        account_id=account_id,
        country=(row.get("country") or "").strip(),
        institution=(row.get("institution") or "").strip(),
        account_type=(row.get("account_type") or "").strip().lower(),
        currency=(row.get("currency") or "").strip().upper(),
        usd_max_balance_during_year=_parse_decimal_field(
            row.get("usd_max_balance_during_year", ""),
            label=f"{csv_label}:{account_id}.usd_max_balance_during_year",
        ),
        usd_eoy_balance=_parse_decimal_field(
            row.get("usd_eoy_balance", ""),
            label=f"{csv_label}:{account_id}.usd_eoy_balance",
        ),
        is_specified_foreign_financial_asset=is_sffa,
    )


def load_us_fatca_fbar_inputs_2025(
    paths: YearPaths,
    *,
    filing_status_label: str,
) -> USFATCAFBARInputs2025:
    """Load the foreign-financial-accounts inputs for FATCA / FBAR.

    Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03) introduced the
    ``data_complete=False`` fail-closed posture; Phase 5.2 (2026-05-03)
    adds an auto-derived stub CSV so the manual-determination renderer
    can enumerate the accounts the engine has already discovered from
    extracted facts.

    Two source paths are consulted, in this order:

    1. ``normalized/facts/foreign-financial-accounts.csv`` (manual,
       authoritative). If the file exists, it is the sole source of
       account rows; the engine does NOT silently merge derived stubs
       on top of a user-authored CSV.
    2. ``outputs/tax-positions/foreign-financial-accounts-derived.csv``
       (auto-derived by ``derive_foreign_financial_accounts_2025``).
       Read only if the manual CSV is absent. Surfaces stub rows whose
       ``data_completeness="balance_unknown"`` flag tells the rule
       layer "we discovered these accounts but never observed
       balances", so ``data_complete`` stays False (no sentinel) and
       the rule fails closed but with a richer per-account list in the
       reason.

    Required CSV columns:
      - ``account_id`` — unique within file
      - ``country`` — ISO-3166 alpha-2 country of the institution
      - ``institution`` — bank / broker / other custodian name
      - ``account_type`` — bank | brokerage | pension | insurance | other
      - ``currency`` — source-currency ISO code
      - ``usd_max_balance_during_year`` — max balance during year, USD-translated
      - ``usd_eoy_balance`` — Dec 31 balance, USD-translated
      - ``is_specified_foreign_financial_asset`` — true/false (§ 6038D scope)

    A workspace declares the manual CSV "complete" by including a single
    sentinel row with ``account_id=__data_complete__`` and any single
    truthy/falsy value in the ``is_specified_foreign_financial_asset``
    column; alternatively a marker file
    ``foreign-financial-accounts.complete`` next to the CSV declares
    completeness. The derived stub CSV NEVER carries the sentinel and
    NEVER triggers ``data_complete=True`` on its own — by construction
    the derivation cannot evidence per-account balances.

    Authority: 26 U.S.C. § 6038D / Reg. § 1.6038D-2 / 31 CFR § 1010.350.
    """
    profile = _profile(paths)
    residency_basis = _profile_residency_basis_for_fatca(profile)
    manual_source = paths.facts_root / "foreign-financial-accounts.csv"
    marker = paths.facts_root / "foreign-financial-accounts.complete"
    # Phase 5.2 derived path — co-located with other auto-derived
    # tax-position artifacts (treaty-dividend-items, model-assumptions).
    # Filename pinned to ``foreign-financial-accounts-derived.csv`` so a
    # workspace can ship BOTH a manual CSV (authoritative) and the
    # derived stub (audit-only) without filename collision.
    derived_source = paths.tax_positions_root / "foreign-financial-accounts-derived.csv"
    if manual_source.exists():
        rows = _read_row_csv(manual_source)
        csv_label = "foreign-financial-accounts.csv"
    elif derived_source.exists():
        rows = _read_row_csv(derived_source)
        csv_label = "foreign-financial-accounts-derived.csv"
    else:
        return USFATCAFBARInputs2025(
            filing_status_label=filing_status_label,
            residency_basis=residency_basis,
            accounts=(),
            data_complete=False,
        )
    accounts: list[USForeignFinancialAccount2025] = []
    seen_ids: set[str] = set()
    data_complete_from_sentinel = False
    derived_stub_seen = False
    for row in rows:
        account_id = (row.get("account_id") or "").strip()
        if not account_id:
            continue
        if account_id == "__data_complete__":
            data_complete_from_sentinel = True
            continue
        if account_id in seen_ids:
            raise ValueError(
                f"{csv_label}: duplicate account_id {account_id!r}"
            )
        seen_ids.add(account_id)
        accounts.append(_ffa_row_to_account(row, csv_label=csv_label))
        # The derived CSV stamps ``data_completeness="balance_unknown"``
        # on every row to mark "balances are placeholders". The
        # ``data_complete`` flag is only flipped True by the sentinel
        # row or marker file — the derived stub CSV by construction
        # never carries either, so this is a defensive cross-check.
        if (row.get("data_completeness") or "").strip().lower() == "balance_unknown":
            derived_stub_seen = True
    # ``data_complete`` is True only when the workspace explicitly
    # declares the manual CSV exhaustive. A derived-stub-only posture
    # means ``data_complete=False`` and the rule's fail-closed branch
    # surfaces the per-account list to the renderer via the reason text.
    data_complete = data_complete_from_sentinel or marker.exists()
    if derived_stub_seen and data_complete:
        # Defensive: a workspace that stamped __data_complete__ on the
        # derived stub CSV would silently bypass the balance-unknown
        # contract. Reject loudly.
        raise ValueError(
            f"{csv_label}: data-completeness sentinel must not appear in the "
            f"auto-derived stub CSV. Author "
            f"normalized/facts/foreign-financial-accounts.csv with verified "
            f"balances instead."
        )
    return USFATCAFBARInputs2025(
        filing_status_label=filing_status_label,
        residency_basis=residency_basis,
        accounts=tuple(accounts),
        data_complete=data_complete,
    )


def load_us_capital_source_facts_2025(paths: YearPaths) -> USCapitalSourceFacts2025:
    files = structured_input_files(paths)
    income = _decimal_map(files["usa_income_summary"])
    other_income = _decimal_map(files["common_other_income_facts"])
    capital = _decimal_map(files["usa_capital_summary"])
    carryovers = _decimal_map(files["us_carryovers_and_payments"])
    return USCapitalSourceFacts2025(
        ordinary_dividends_usd=income["ordinary_dividends_usd"],
        qualified_dividends_usd=income["qualified_dividends_usd"],
        capital_gain_distributions_usd=income["capital_gain_distributions_usd"],
        nondividend_distributions_usd=income["nondividend_distributions_usd"],
        foreign_tax_paid_usd=income["foreign_tax_paid_usd"],
        interest_income_usd=income["interest_income_usd"],
        substitute_payments_usd=income["substitute_payments_usd"],
        staking_income_usd=other_income["staking_income_usd"],
        estimated_payment_2025_usd=carryovers["estimated_payment_2025_usd"],
        passive_ftc_carryover_2024_usd=carryovers["passive_ftc_carryover_2024_usd"],
        general_ftc_carryover_2024_usd=carryovers["general_ftc_carryover_2024_usd"],
        german_2024_redetermination_paid_2025_eur=carryovers["german_2024_redetermination_paid_2025_eur"],
        schwab_short_box_a_gain_usd=capital["schwab_short_box_a_gain_usd"],
        schwab_short_box_b_gain_usd=capital["schwab_short_box_b_gain_usd"],
        schwab_long_box_d_gain_usd=capital["schwab_long_box_d_gain_usd"],
        schwab_section_1256_total_usd=capital["schwab_section_1256_total_usd"],
        jpm_short_type_a_gain_usd=capital["jpm_short_type_a_gain_usd"],
        coinbase_short_with_basis_proceeds_usd=capital["coinbase_short_with_basis_proceeds_usd"],
        coinbase_short_with_basis_basis_usd=capital["coinbase_short_with_basis_basis_usd"],
        coinbase_short_unknown_proceeds_usd=capital["coinbase_short_unknown_proceeds_usd"],
        coinbase_short_unknown_basis_reconstructed_usd=capital["coinbase_short_unknown_basis_reconstructed_usd"],
        coinbase_long_with_basis_proceeds_usd=capital["coinbase_long_with_basis_proceeds_usd"],
        coinbase_long_with_basis_basis_usd=capital["coinbase_long_with_basis_basis_usd"],
    )


def load_us_assessment_inputs_2025(
    paths: YearPaths,
    *,
    germany_treaty_dividend_items: tuple[GermanyUSTreatyDividendPacketItem2025, ...] | None = None,
) -> USAssessmentInputs2025:
    files = structured_input_files(paths)
    constants = _decimal_map(files["us_tax_constants"])
    ftc_support = _decimal_map(files["usa_ftc_support"])
    wage_support = _decimal_map(files["usa_foreign_wage_support"])
    assumptions = _decimal_map(files["us_model_assumptions"])
    profile = _profile(paths)
    manual_overrides = _manual_overrides(paths)
    filing_posture = _usa_filing_posture(profile)
    us_treaty_items, us_treaty_items_file_declared = _load_us_treaty_dividend_items_2025(paths)
    # Resolve the treaty-resourcing election early so the coverage-contract
    # check below can short-circuit when the user has disabled treaty
    # re-sourcing entirely — in that posture, no Pub. 514 worksheet runs
    # and the missing U.S. items file is the legitimate absence, not a
    # coverage gap. The full election is also re-resolved later (at line
    # ~995) for the USTreatyInputs2025 envelope; computing it twice is
    # cheaper than restructuring the rest of the loader.
    treaty_override_for_gate = manual_overrides.get("treaty_resourcing", {}).get("enabled")
    treaty_election_active = (
        bool(treaty_override_for_gate)
        if treaty_override_for_gate is not None
        else bool(profile.get("elections", {}).get("use_treaty_resourcing", False))
    )
    # When an orchestrator passes a same-run Germany treaty packet under
    # an active treaty election, it is asserting that the Pub. 514
    # worksheet has been computed against an explicit U.S. position. If
    # the U.S. side has not declared one — no ``us-treaty-dividend-items
    # .csv`` file at all (null/missing, not empty) — we must refuse to
    # silently re-source as zero. An empty header-only file means the
    # U.S. side has explicitly declared zero items (e.g., § 20 Abs. 9
    # Sparer-Pauschbetrag shelters the dividend) and that path is
    # preserved by ``_germany_treaty_dividend_outputs_usd``. The error
    # string carries "item coverage" so the regression test
    # ``test_load_us_assessment_inputs_rejects_explicit_germany_packet_coverage_gap``
    # locks the contract.
    # Source: https://www.irs.gov/publications/p514.
    if (
        treaty_election_active
        and germany_treaty_dividend_items is not None
        and not us_treaty_items_file_declared
    ):
        raise ValueError(
            "Same-run Germany treaty dividend packet was supplied under an "
            "active treaty election, but the U.S. side has not declared a "
            "Pub. 514 treaty position (missing us-treaty-dividend-items.csv). "
            "Refusing to silently re-source as zero — explicit item coverage "
            "is required."
        )
    (
        germany_treaty_gross_usd,
        germany_treaty_allowed_us_tax_usd,
        germany_treaty_precredit_usd,
        germany_treaty_credit_usd,
        germany_treaty_items,
    ) = _germany_treaty_dividend_outputs_usd(
        germany_treaty_dividend_items=germany_treaty_dividend_items,
        us_treaty_dividend_items=us_treaty_items,
        eur_per_usd=constants["eur_per_usd_yearly_average_2025"],
    )

    if filing_posture == "single":
        filing_status_label = "Single"
        spouse_name_for_mfs_line = ""
        joint_return_spouse_name = ""
        joint_return_with_nra_spouse_election = False
        standard_deduction_key = "standard_deduction_single_2025_usd"
        capital_loss_limit_usd = STANDARD_CAPITAL_LOSS_LIMIT_USD
        niit_threshold_key = "niit_threshold_single_usd"
        qualified_dividend_zero_rate_key = "qualified_dividend_zero_rate_ceiling_single_2025_usd"
        qualified_dividend_fifteen_rate_key = "qualified_dividend_fifteen_rate_ceiling_single_2025_usd"
        tax_bracket_10_key = "tax_bracket_10_ceiling_single_2025_usd"
        tax_bracket_12_key = "tax_bracket_12_ceiling_single_2025_usd"
        tax_bracket_22_key = "tax_bracket_22_ceiling_single_2025_usd"
        tax_bracket_24_key = "tax_bracket_24_ceiling_single_2025_usd"
        tax_bracket_32_key = "tax_bracket_32_ceiling_single_2025_usd"
        tax_bracket_35_key = "tax_bracket_35_ceiling_single_2025_usd"
    elif filing_posture == "married_joint":
        spouse_name = _required_profile_text(profile, ("spouse", "name"), label="spouse name")
        spouse_tax_status = str(profile.get("spouse", {}).get("us_tax_status", "")).strip().lower()
        election = _optional_profile_bool(profile, ("elections", "elect_joint_return_with_nra_spouse"))
        if spouse_tax_status == "nra":
            if election is not True:
                raise ValueError(
                    "Joint U.S. return with NRA spouse requires an explicit election in config/profile.json."
                )
            joint_return_with_nra_spouse_election = True
            niit_joint_election = _optional_profile_bool(
                profile,
                ("elections", "elect_joint_return_with_nra_spouse_for_niit"),
            )
            if niit_joint_election is not True:
                # Form 8960 instructions for 26 U.S.C. § 1411 keep the MFS
                # threshold for a § 6013(g)/(h) NRA-spouse joint return unless
                # the taxpayer also makes the separate NIIT joint-election posture.
                niit_joint_election = False
        else:
            joint_return_with_nra_spouse_election = False
            niit_joint_election = True
        filing_status_label = "Married filing jointly"
        spouse_name_for_mfs_line = ""
        joint_return_spouse_name = spouse_name
        standard_deduction_key = "standard_deduction_married_joint_2025_usd"
        capital_loss_limit_usd = STANDARD_CAPITAL_LOSS_LIMIT_USD
        niit_threshold_key = (
            "niit_threshold_married_joint_usd"
            if niit_joint_election is True
            else "niit_threshold_mfs_usd"
        )
        qualified_dividend_zero_rate_key = "qualified_dividend_zero_rate_ceiling_married_joint_2025_usd"
        qualified_dividend_fifteen_rate_key = "qualified_dividend_fifteen_rate_ceiling_married_joint_2025_usd"
        tax_bracket_10_key = "tax_bracket_10_ceiling_married_joint_2025_usd"
        tax_bracket_12_key = "tax_bracket_12_ceiling_married_joint_2025_usd"
        tax_bracket_22_key = "tax_bracket_22_ceiling_married_joint_2025_usd"
        tax_bracket_24_key = "tax_bracket_24_ceiling_married_joint_2025_usd"
        tax_bracket_32_key = "tax_bracket_32_ceiling_married_joint_2025_usd"
        tax_bracket_35_key = "tax_bracket_35_ceiling_married_joint_2025_usd"
    else:
        spouse_name = _required_profile_text(profile, ("spouse", "name"), label="spouse name")
        filing_status_label = "Married filing separately"
        spouse_name_for_mfs_line = f"{spouse_name.upper()} NRA"
        joint_return_spouse_name = ""
        joint_return_with_nra_spouse_election = False
        standard_deduction_key = "standard_deduction_mfs_2025_usd"
        capital_loss_limit_usd = MFS_CAPITAL_LOSS_LIMIT_USD
        niit_threshold_key = "niit_threshold_mfs_usd"
        qualified_dividend_zero_rate_key = "qualified_dividend_zero_rate_ceiling_mfs_2025_usd"
        qualified_dividend_fifteen_rate_key = "qualified_dividend_fifteen_rate_ceiling_mfs_2025_usd"
        tax_bracket_10_key = "tax_bracket_10_ceiling_mfs_2025_usd"
        tax_bracket_12_key = "tax_bracket_12_ceiling_mfs_2025_usd"
        tax_bracket_22_key = "tax_bracket_22_ceiling_mfs_2025_usd"
        tax_bracket_24_key = "tax_bracket_24_ceiling_mfs_2025_usd"
        tax_bracket_32_key = "tax_bracket_32_ceiling_mfs_2025_usd"
        tax_bracket_35_key = "tax_bracket_35_ceiling_mfs_2025_usd"
    treaty_override = manual_overrides.get("treaty_resourcing", {}).get("enabled")
    if treaty_override is not None and not isinstance(treaty_override, bool):
        raise ValueError("Invalid treaty_resourcing.enabled in config/manual_overrides.json: expected true, false, or null")
    use_treaty_resourcing = (
        bool(treaty_override)
        if treaty_override is not None
        else _required_profile_bool(profile, ("elections", "use_treaty_resourcing"), label="U.S. treaty resourcing election")
    )
    us_ftc_method = _required_profile_text(profile, ("elections", "us_ftc_method"), label="U.S. FTC method").lower()
    if us_ftc_method not in {"accrued", "paid"}:
        raise ValueError("Invalid U.S. FTC method in config/profile.json: expected 'accrued' or 'paid'")
    # Workstream 3 — 26 U.S.C. § 905(a) paid-basis FTC posture. The
    # default § 901 timing is accrued (FTC for foreign taxes accrued
    # during the tax year). § 905(a) lets the taxpayer elect cash/paid-
    # basis timing, binding for that year and every subsequent year
    # until revoked. The posture flows through ``accrued_basis_ftc``
    # on ``USReturnProfile2025`` to downstream consumers; the FTC math
    # itself uses available foreign tax (current + carryover) under
    # both timings, but cash-basis filers count only foreign tax actually
    # paid in the calendar year (vs. accrued for the tax year).
    # Carryforward / carryback rules differ per § 904(c).
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section905

    # 26 U.S.C. § 911 Foreign Earned Income Exclusion (Workstream 1). When
    # elected, the loader pulls the supporting amounts from manual_overrides
    # and validates them. § 911(b)(2)(D) caps the exclusion at $130,000 for
    # 2025 (Rev. Proc. 2024-40). § 911(c) routes housing expenses to either
    # the housing exclusion (employees) or the housing deduction (self-
    # employed under § 911(c)(4)). § 911(d)(6) denies any FTC on foreign
    # taxes allocable to the excluded amount. § 1411(d)(1)(A) requires the
    # excluded amount to be added back to NIIT MAGI. Authority:
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section911
    # https://www.irs.gov/publications/p54
    # https://www.irs.gov/forms-pubs/about-form-2555
    # https://www.irs.gov/pub/irs-drop/n-24-77.pdf
    elect_section_911_feie = _required_profile_bool(
        profile,
        ("elections", "elect_section_911_feie"),
        label="U.S. § 911 Foreign Earned Income Exclusion election",
    )
    if elect_section_911_feie:
        feie_test = str(manual_overrides.get("feie_qualifying_test", "")).strip().lower()
        if feie_test not in {"bona_fide_residence", "physical_presence"}:
            # Fail closed: § 911(d)(1) requires either bona-fide-residence or
            # physical-presence to qualify; without it the exclusion is invalid.
            raise NotImplementedError(
                "U.S. § 911 FEIE is elected but config/manual_overrides.json "
                "is missing 'feie_qualifying_test' (bona_fide_residence | "
                "physical_presence). § 911(d)(1) requires one of the two "
                "qualifying tests; fix the profile or de-elect § 911."
            )
        feie_fei = manual_overrides.get("feie_foreign_earned_income_usd")
        if feie_fei is None:
            raise NotImplementedError(
                "U.S. § 911 FEIE is elected but config/manual_overrides.json "
                "is missing 'feie_foreign_earned_income_usd' — the gross "
                "foreign earned income to exclude under § 911(b)."
            )
        feie_housing = manual_overrides.get("feie_housing_expenses_usd", "0.00")
        feie_ceiling_raw = manual_overrides.get("feie_location_adjusted_housing_ceiling_usd")
        if feie_ceiling_raw is None:
            feie_ceiling: Decimal | None = None
        else:
            feie_ceiling = Decimal(str(feie_ceiling_raw))
        feie_self_employed = bool(manual_overrides.get("feie_self_employed", False))
        feie_disallowed_ftc = manual_overrides.get(
            "feie_foreign_tax_paid_on_excluded_income_usd", "0.00"
        )
        feie_inputs = USFEIEInputs2025(
            elected=True,
            foreign_earned_income_usd=Decimal(str(feie_fei)),
            qualifying_test=feie_test,
            housing_expenses_usd=Decimal(str(feie_housing)),
            location_adjusted_housing_ceiling_usd=feie_ceiling,
            self_employed=feie_self_employed,
            foreign_tax_paid_on_excluded_income_usd=Decimal(str(feie_disallowed_ftc)),
        )
    else:
        feie_inputs = USFEIEInputs2025(
            elected=False,
            foreign_earned_income_usd=Decimal("0.00"),
            qualifying_test="",
            housing_expenses_usd=Decimal("0.00"),
            location_adjusted_housing_ceiling_usd=None,
            self_employed=False,
            foreign_tax_paid_on_excluded_income_usd=Decimal("0.00"),
        )

    # 26 U.S.C. § 1401 Self-Employment tax + 26 U.S.C. § 3101(b)(2) /
    # § 1401(b)(2) Additional Medicare Tax (Workstream 2). The acknowledgment
    # flag remains: it confirms the modeled posture (German-employer wages
    # under the U.S.-Germany Totalization Agreement) is what the engine sees.
    # SE earnings and U.S.-source Medicare-taxable wages flow through manual
    # overrides; when zero the SE-tax / Additional-Medicare stages emit zero.
    # https://www.ssa.gov/international/Agreement_Pamphlets/germany.html
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section1401
    # https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section3101
    acknowledges_totalization = _required_profile_bool(
        profile,
        ("elections", "acknowledges_totalization_agreement_germany_us"),
        label="U.S.-Germany Totalization Agreement acknowledgment for § 3101 Additional Medicare Tax",
    )
    if not acknowledges_totalization:
        # Rationale: the demo-public posture acknowledges the Totalization
        # Agreement to confirm its applicability; an explicit "no" without
        # any other context is ambiguous and best handled by a real-world
        # configuration step rather than silent zero. Fail closed.
        # Note: registry key is ``elections.acknowledges_totalization_agreement_germany_us``.
        raise NotImplementedError(
            "Profile must explicitly acknowledge the U.S.-Germany "
            "Totalization Agreement before the engine evaluates § 3101 / "
            "§ 1401. Set the engine election keyed under "
            "elections (acknowledges_totalization_agreement_germany_us=true, "
            "recommended for a German-employer-wage posture) or wire a "
            "different SSA-coverage profile."
        )
    # 26 U.S.C. § 61 / § 162 Schedule C business-income position (Phase 2
    # freelancer support). ``None`` for a pure wage earner; otherwise the
    # § 61/§ 162 gross-receipts/expenses facts under a self-employed
    # ``worker_type`` (fails closed on missing facts / us_effectively_connected).
    schedule_c_inputs = _load_us_business_income_position(paths, profile)

    us_source_medicare_wages = manual_overrides.get(
        "us_source_medicare_taxable_wages_usd", "0.00"
    )
    totalization_certificate = bool(
        manual_overrides.get("totalization_agreement_certificate_present", False)
    )
    # Derive the § 1402(a)(12) self-employment-tax base from the Schedule C net
    # profit when self-employment is declared (the headline cross-border wiring:
    # the SAME § 61/§ 162 net profit is both income → AGI and the SE-tax base).
    # A Schedule C LOSS produces zero net SE earnings (SE tax applies only to
    # positive net earnings from self-employment under § 1402(a)). For a wage
    # earner (no Schedule C position) the manual override is kept for
    # back-compat so the demo and existing SE-tax tests are unchanged. If both
    # a self-employed Schedule C position AND a non-zero
    # ``se_net_earnings_usd`` override are set, fail closed rather than silently
    # picking one — the SE base must have a single unambiguous source.
    se_net_earnings_override = manual_overrides.get("se_net_earnings_usd", "0.00")
    if schedule_c_inputs is not None:
        if Decimal(str(se_net_earnings_override)) != Decimal("0.00"):
            raise ValueError(
                "Both a self-employed Schedule C position (config/"
                f"{US_BUSINESS_INCOME_FILE_NAME}) and a non-zero manual "
                "se_net_earnings_usd override are declared. Under a self-"
                "employment worker_type the § 1402(a)(12) SE-tax base is "
                "DERIVED from Schedule C net profit; the manual override is "
                "only for the wage-earner posture. Remove one. Authority: "
                f"{USC_162_URL}."
            )
        net_profit = schedule_c_net_profit_2025(inputs=schedule_c_inputs).net_profit_usd
        # § 1402(a): self-employment tax applies to NET EARNINGS from self-
        # employment; a Schedule C loss is not negative SE earnings.
        se_net_earnings = max(Decimal("0.00"), net_profit)
    else:
        se_net_earnings = Decimal(str(se_net_earnings_override))
    se_inputs = USSelfEmploymentInputs2025(
        net_se_earnings_usd=se_net_earnings,
        us_w2_medicare_taxable_wages_usd=Decimal(str(us_source_medicare_wages)),
        totalization_certificate_present=totalization_certificate,
    )

    # F-US-1: 26 U.S.C. § 56 AMTI add-backs (incentive stock option bargain
    # element, accelerated depreciation timing differences, NOL adjustments,
    # state/local tax itemized deduction). The current 2025 model is the
    # standard-deduction posture only — there is no § 56(b)(1)(E) SALT add-
    # back to compute (TCJA suspended the SALT-itemizer add-back through
    # 2025; standard-deduction filers have no add-back). ISO and depreciation
    # add-backs require § 6251 line-2c / line-2d worksheets that this model
    # does not implement, so any non-zero amount in the manual_overrides
    # under-the-line entries must fail closed.
    # https://www.law.cornell.edu/uscode/text/26/56
    # https://www.irs.gov/forms-pubs/about-form-6251
    for amt_pref_key in (
        "amt_iso_bargain_element_usd",
        "amt_accelerated_depreciation_addback_usd",
        "amt_private_activity_bond_interest_usd",
        "amt_other_section_56_addbacks_usd",
        "itemized_state_and_local_tax_deduction_usd",
    ):
        amt_pref_value = manual_overrides.get(amt_pref_key)
        if amt_pref_value not in (None, 0, "0", "0.00", Decimal("0.00"), False):
            raise NotImplementedError(
                f"U.S. § 56 AMT preference item is present ({amt_pref_key}="
                f"{amt_pref_value!r}) but the corresponding Form 6251 line-2 "
                "worksheet is not implemented for 2025. The engine fails "
                "closed: implement the § 56 AMT add-back path (with the "
                "appropriate Form 6251 line and citation) before computing "
                "with non-zero AMT preferences. Authority: 26 U.S.C. § 56 "
                "(https://www.law.cornell.edu/uscode/text/26/56) and Form "
                "6251 instructions (https://www.irs.gov/forms-pubs/about-form-6251)."
            )

    return USAssessmentInputs2025(
        constants=USTaxConstants2025(
            eur_per_usd_yearly_average_2025=constants["eur_per_usd_yearly_average_2025"],
            # Keep the existing law dataclass shape stable while selecting the right
            # thresholds for the chosen filing posture in the loader.
            standard_deduction_2025_usd=constants[standard_deduction_key],
            capital_loss_limit_usd=capital_loss_limit_usd,
            niit_threshold_usd=constants[niit_threshold_key],
            qualified_dividend_zero_rate_ceiling_2025_usd=constants[qualified_dividend_zero_rate_key],
            qualified_dividend_fifteen_rate_ceiling_2025_usd=constants[qualified_dividend_fifteen_rate_key],
            tax_bracket_10_ceiling_2025_usd=constants[tax_bracket_10_key],
            tax_bracket_12_ceiling_2025_usd=constants[tax_bracket_12_key],
            tax_bracket_22_ceiling_2025_usd=constants[tax_bracket_22_key],
            tax_bracket_24_ceiling_2025_usd=constants[tax_bracket_24_key],
            tax_bracket_32_ceiling_2025_usd=constants[tax_bracket_32_key],
            tax_bracket_35_ceiling_2025_usd=constants[tax_bracket_35_key],
        ),
        profile=USReturnProfile2025(
            filing_status_label=filing_status_label,
            spouse_name_for_mfs_line=spouse_name_for_mfs_line,
            joint_return_spouse_name=joint_return_spouse_name,
            joint_return_with_nra_spouse_election=joint_return_with_nra_spouse_election,
            accrued_basis_ftc=us_ftc_method == "accrued",
            include_staking_in_niit=_required_assumption_bool(
                assumptions,
                "include_staking_in_niit",
                label="include_staking_in_niit",
            ),
        ),
        capital_facts=load_us_capital_source_facts_2025(paths),
        ftc_inputs=USFTCInputs2025(
            taxpayer_gross_wages_eur=wage_support["taxpayer_gross_wages_eur"],
            spouse_gross_wages_eur=wage_support["spouse_gross_wages_eur"],
            joint_wage_side_tax_eur=ftc_support["joint_wage_side_tax_eur"],
            foreign_source_passive_dividends_usd=ftc_support["foreign_source_passive_dividends_usd"],
            foreign_source_qualified_dividends_usd=ftc_support["foreign_source_qualified_dividends_usd"],
            foreign_source_net_capital_gain_usd=ftc_support["foreign_source_net_capital_gain_usd"],
            known_positive_short_capital_gain_usd=ftc_support["known_positive_short_capital_gain_usd"],
            known_positive_long_capital_gain_usd=ftc_support["known_positive_long_capital_gain_usd"],
            conservative_positive_income_only=_required_assumption_bool(
                assumptions,
                "ftc_denominator_positive_income_only",
                label="ftc_denominator_positive_income_only",
            ),
            allocate_joint_german_tax_by_wage_share=_required_assumption_bool(
                assumptions,
                "allocate_joint_german_tax_by_wage_share",
                label="allocate_joint_german_tax_by_wage_share",
            ),
        ),
        treaty_inputs=USTreatyInputs2025(
            use_treaty_resourcing=use_treaty_resourcing,
            us_source_direct_equity_dividends_usd=assumptions["us_source_direct_equity_dividends_usd"],
            us_source_equity_fund_dividends_usd=assumptions["us_source_equity_fund_dividends_usd"],
            us_source_non_equity_fund_dividends_usd=assumptions["us_source_non_equity_fund_dividends_usd"],
            us_treaty_dividend_items=us_treaty_items,
            germany_treaty_dividend_items=germany_treaty_items,
            germany_treaty_us_source_dividend_gross_usd=germany_treaty_gross_usd,
            germany_treaty_us_source_dividend_allowed_us_tax_usd=germany_treaty_allowed_us_tax_usd,
            german_precredit_tax_on_us_source_dividends_usd=germany_treaty_precredit_usd,
            german_residence_credit_for_us_tax_usd=germany_treaty_credit_usd,
        ),
        feie_inputs=feie_inputs,
        se_inputs=se_inputs,
        schedule_c_inputs=schedule_c_inputs,
        children_facts=load_us_children_facts_2025(paths),
        # Group D (FORM-MAPPING-FOLLOWUP, 2026-05-03): FATCA Form 8938
        # / FBAR FinCEN 114 inputs. Loader fails closed with
        # ``data_complete=False`` when the workspace has not populated
        # ``normalized/facts/foreign-financial-accounts.csv`` (or the
        # paired completeness marker). The US25-FATCA-FBAR-DETERMINATION
        # rule then surfaces a manual-determination status sheet
        # rather than a silent "not required". 26 U.S.C. § 6038D /
        # 31 CFR § 1010.350.
        fatca_fbar_inputs=load_us_fatca_fbar_inputs_2025(
            paths,
            filing_status_label=filing_status_label,
        ),
    )
