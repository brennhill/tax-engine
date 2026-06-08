"""Per-jurisdiction filing-guide renderer (Pipeline 2 sidecar).

Produces ``FILING-GUIDE.md`` per jurisdiction — a single end-user-facing
walkthrough that re-presents the existing per-form Markdown files in
dependency order, with explicit cross-form transfer notes so a human
filer can step through ELSTER / IRS Free File / TurboTax line by line.

Design and invariants
=====================

- This is a **meta-renderer**. It reads the already-rendered per-form
  Markdown files in ``outputs/forms/{country}/`` and rearranges them.
  No legal math runs here — every Decimal value displayed in the
  filing guide comes verbatim from the source form's ``## Lines``
  table, which itself was built via the I11 ``LegalValue`` envelope
  in ``tax_pipeline/forms/{germany,usa}.py``. This satisfies CLAUDE.md
  invariants I2 / I3 / I5: no new form-line writes, no Decimal
  arithmetic in the renderer, no new ``OutputDeclaration.form_line_refs``.
- The dependency graph is **hand-curated** below in
  :data:`USA_FORMS` / :data:`GERMANY_FORMS`. The list of forms-and-
  dependencies is small, well-known, and changes annually with the
  IRS / BMF revisions. Encoding it here (rather than deriving it
  programmatically) keeps the cross-form transfer wiring legible and
  reviewable. The ``feeds_into`` field is the directed edge:
  ``A.feeds_into = ["B"]`` means "A feeds into B" — A must be filled
  out before B.
- Conditional forms (Form 2555, Form 8959, Schedule SE, Form 8833)
  may not be rendered for every workspace. The guide renderer
  inspects the ``outputs/forms/{country}/`` directory at call time
  and only includes forms whose Markdown file actually exists. This
  matches CLAUDE.md invariant I13: a missing form file means the
  rule graph has determined that form does not apply, and the guide
  must reflect that absence rather than fabricating a zero-line entry.
- Filing-order tie-breaker is **lexicographic on form name** so the
  output is deterministic across runs.

Authority
=========

- IRS Form 1040 instructions (2025) — line ordering and cross-form
  transfer references: https://www.irs.gov/instructions/i1040gi
- ELSTER Hilfe / BMF Anlage instructions (2025) — Zeile ordering and
  Mantelbogen ↔ Anlage transfer references:
  https://www.elster.de/eportal/helpGlobal
- 26 U.S.C. § 6012 (CLAUDE.md invariant I13) — when
  ``us_filing_required=false``, the U.S. ``FILING-GUIDE.md`` MUST NOT
  render. The orchestrator gates the call accordingly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tax_pipeline.y2025.germany_law import (
    ELSTER_HELP_GLOBAL_URL,
    ELSTER_PORTAL_URL,
)
from tax_pipeline.paths import YearPaths
from tax_pipeline.y2025.us_law import (
    FINCEN_BSA_EFILING_URL,
    IRS_FREE_FILE_URL,
    IRS_I1040,
)


# ----- Source citations (renderer references — no legal math) -----------
#
# All URLs come from the centralized law modules per CLAUDE.md
# invariant I1 ("No legal constant literal outside the law modules").
# The aliases below are local readability shorthand; they re-export
# the same constants without introducing new literals.

IRS_FORM_1040_INSTRUCTIONS_URL = IRS_I1040
ELSTER_HELP_URL = ELSTER_HELP_GLOBAL_URL
FBAR_BSA_EFILING_URL = FINCEN_BSA_EFILING_URL


# ----- Dependency graph models -----------------------------------------------


@dataclass(frozen=True)
class FormSpec:
    """A single form/Anlage in the filing guide.

    - ``basename``: the rendered Markdown file basename, e.g.
      ``"2025_form_8949.md"``. Must match the file the per-jurisdiction
      renderer in ``forms/{germany,usa}.py`` writes.
    - ``display_name``: the human-readable form title shown in the guide.
    - ``what_for``: a one-line "what this is for" string.
    - ``triggered_because``: the workspace condition that caused this
      form to apply (e.g., "capital sales documented", "treaty
      re-sourcing claimed").
    - ``feeds_into``: list of downstream form ``basename``s that
      consume values from this form. Empty list means no downstream
      consumer (informational / disclosure / main return).
    - ``role``: ordering hint for the topo sort tie-break.
        - ``"functional"`` (default) — has downstream consumers; placed
          in the natural dependency order.
        - ``"standalone"`` — disclosure / status sheets that the user
          handles AFTER the numeric chain but they should still come
          BEFORE the main-return form (so the user encounters them
          while still in "form work mode").
        - ``"main_return"`` — Form 1040 / Hauptvordruck. Always last:
          every other form has fed in by the time the user reaches it.
    - ``transfer_targets``: per-line transfer annotations. Maps a
      ``Line`` cell from THIS form's rendered table to a human
      transfer note like ``"→ transfer to Form 1040 Line 7"``. The
      key is the literal ``Line`` cell (case-sensitive) and the value
      is the target description suffix.
    """

    basename: str
    display_name: str
    what_for: str
    triggered_because: str
    feeds_into: tuple[str, ...] = ()
    role: str = "functional"
    transfer_targets: dict[str, str] = field(default_factory=dict)


# ----- USA dependency graph -----------------------------------------------
#
# Authority: IRS Form 1040 instructions (2025) for cross-form transfer
# references — https://www.irs.gov/instructions/i1040gi. The
# transfer_targets cells below are the literal ``Line`` cells emitted
# by ``tax_pipeline/forms/usa.py`` so the lookup is exact.

USA_FORMS: tuple[FormSpec, ...] = (
    FormSpec(
        basename="2025_form_8949.md",
        display_name="Form 8949 — Sales and Other Dispositions of Capital Assets",
        what_for="Lists every capital sale lot, bucketed by short/long term and reporting category.",
        triggered_because="capital sales documented in the workspace",
        feeds_into=("2025_schedule_d.md",),
        transfer_targets={
            "Part I Box A": "→ Schedule D Line 1b",
            "Part I Box B": "→ Schedule D Line 2",
            "Part I Box H": "→ Schedule D Line 3",
            "Part II Box D": "→ Schedule D Line 8b",
            "Part II Box K": "→ Schedule D Line 10",
        },
    ),
    FormSpec(
        basename="2025_form_6781.md",
        display_name="Form 6781 — Section 1256 Contracts and Straddles",
        what_for="Splits the net Section 1256 result 40 % short-term / 60 % long-term.",
        triggered_because="Section 1256 contracts present (Schwab marked-to-market)",
        feeds_into=("2025_schedule_d.md",),
        transfer_targets={
            "40% short-term portion": "→ Schedule D Line 4 (short-term)",
            "60% long-term portion": "→ Schedule D Line 11 (long-term)",
        },
    ),
    FormSpec(
        basename="2025_schedule_d.md",
        display_name="Schedule D — Capital Gains and Losses",
        what_for="Aggregates Form 8949 buckets, capital-gain distributions, and the Form 6781 split.",
        triggered_because="Form 8949 / Form 6781 / capital-gain distributions present",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Capital loss deduction carried to Form 1040 line 7a": "→ Form 1040 Line 7",
        },
    ),
    FormSpec(
        basename="2025_schedule_b.md",
        display_name="Schedule B — Interest and Ordinary Dividends",
        what_for="Reports interest, ordinary dividends, and the Part III foreign-account question.",
        triggered_because="interest > $1,500 OR ordinary dividends > $1,500 OR foreign account present",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Line 2": "→ Form 1040 Line 2b",
            "Line 5": "→ Form 1040 Line 3b",
        },
    ),
    FormSpec(
        basename="2025_form_6251.md",
        display_name="Form 6251 — Alternative Minimum Tax",
        what_for="Computes the AMT under 26 U.S.C. § 55 — line 11 carries to Schedule 2.",
        triggered_because="AMTI exceeds the exemption / phase-out threshold",
        feeds_into=("2025_schedule_2.md",),
        # IRS-VERIFIED 2026-05-10 — Form 6251 line 11 → Schedule 2 line 2
        # (2025 revision; was line 1 on 2024 revision) per
        # https://www.irs.gov/pub/irs-pdf/f1040s2.pdf and
        # https://www.irs.gov/pub/irs-pdf/f6251.pdf.
        transfer_targets={
            "Line 11": "→ Schedule 2 Line 2",
        },
    ),
    FormSpec(
        basename="2025_schedule_8812.md",
        display_name="Schedule 8812 — Credits for Qualifying Children and Other Dependents",
        what_for="Computes the § 24 nonrefundable CTC + ODC (line 14) and the refundable ACTC (line 27).",
        triggered_because="children / other dependents declared in the workspace",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Line 14": "→ Form 1040 Line 19",
            "Line 27": "→ Form 1040 Line 28",
        },
    ),
    FormSpec(
        basename="2025_schedule_se.md",
        display_name="Schedule SE — Self-Employment Tax",
        what_for="Computes § 1401 SE tax on net self-employment earnings.",
        triggered_because="net self-employment earnings > $0",
        feeds_into=("2025_schedule_2.md",),
        transfer_targets={
            "Line 12": "→ Schedule 2 Line 4",
        },
    ),
    FormSpec(
        basename="2025_form_8959.md",
        display_name="Form 8959 — Additional Medicare Tax",
        what_for="Computes § 3101(b)(2) Additional Medicare on wages + SE earnings above threshold.",
        triggered_because="wages + SE earnings exceed the § 3101(b)(2) threshold",
        feeds_into=("2025_schedule_2.md",),
        transfer_targets={
            "Line 18": "→ Schedule 2 Line 11",
        },
    ),
    FormSpec(
        basename="2025_form_8960.md",
        display_name="Form 8960 — Net Investment Income Tax",
        what_for="Computes the § 1411 3.8 % NIIT on net investment income.",
        triggered_because="modified AGI exceeds the § 1411 threshold",
        feeds_into=("2025_schedule_2.md",),
        transfer_targets={
            "Line 17": "→ Schedule 2 Line 12",
        },
    ),
    FormSpec(
        basename="2025_form_1116_passive.md",
        display_name="Form 1116 — Passive Category (Foreign Tax Credit)",
        what_for="Computes the § 904 limitation on passive-basket foreign tax credit.",
        triggered_because="foreign tax paid on passive income (dividends/interest)",
        feeds_into=("2025_schedule_3.md",),
        transfer_targets={
            "Line 22 (allowed passive credit)": "→ Schedule 3 Line 1 (combined FTC)",
        },
    ),
    FormSpec(
        basename="2025_form_1116_general.md",
        display_name="Form 1116 — General Category (Foreign Tax Credit)",
        what_for="Computes the § 904 limitation on general-basket (e.g., foreign wage) foreign tax credit.",
        triggered_because="foreign tax paid on general-basket income (e.g., wages)",
        feeds_into=("2025_schedule_3.md",),
        transfer_targets={
            "Line 22 (allowed general credit)": "→ Schedule 3 Line 1 (combined FTC)",
        },
    ),
    FormSpec(
        basename="2025_form_1116_resourced.md",
        display_name="Form 1116 — Certain Income Resourced by Treaty",
        what_for="§ 904(d)(6) separate basket for treaty-resourced U.S.-source income.",
        triggered_because="DBA-USA Art. 23(3) treaty re-sourcing claimed",
        feeds_into=("2025_schedule_3.md", "2025_form_8833.md"),
        transfer_targets={
            "Line 32": "→ Schedule 3 Line 1 (combined FTC across all baskets)",
        },
    ),
    FormSpec(
        basename="2025_form_2555.md",
        display_name="Form 2555 — Foreign Earned Income Exclusion",
        what_for="Elects the § 911(a) FEIE; subtracts from wages on Form 1040 line 1.",
        triggered_because="§ 911 FEIE election made for foreign earned income",
        feeds_into=("2025_1040.md", "2025_schedule_1.md"),
        transfer_targets={
            "Line 36": "→ Form 1040 Line 1 reduction (excluded foreign earned income)",
            "Line 45": "→ Schedule 1 Line 8 reduction (housing exclusion)",
        },
    ),
    FormSpec(
        basename="2025_schedule_1.md",
        display_name="Schedule 1 — Additional Income and Adjustments to Income",
        what_for="Reports other income (line 8z: substitute payments, staking) and above-the-line adjustments.",
        triggered_because="other income or above-the-line adjustments present",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Line 8z total": "→ Form 1040 Line 8 (via Schedule 1 line 10 total)",
        },
    ),
    FormSpec(
        basename="2025_schedule_2.md",
        display_name="Schedule 2 — Additional Taxes",
        what_for="Aggregates AMT (Part I), SE tax + Additional Medicare + NIIT (Part II).",
        triggered_because="Form 6251 / Schedule SE / Form 8959 / Form 8960 attaches",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Line 3": "→ Form 1040 Line 17",
            "Line 21": "→ Form 1040 Line 23",
        },
    ),
    FormSpec(
        basename="2025_schedule_3.md",
        display_name="Schedule 3 — Additional Credits and Payments",
        what_for="Aggregates nonrefundable credits (Part I, line 8) and refundable credits / payments (Part II, line 15).",
        triggered_because="Form 1116 baskets / treaty re-sourcing additional credit / refundable credits present",
        feeds_into=("2025_1040.md",),
        transfer_targets={
            "Line 8": "→ Form 1040 Line 20",
        },
    ),
    FormSpec(
        basename="2025_form_8833.md",
        display_name="Form 8833 — Treaty-Based Return Position Disclosure",
        what_for="26 U.S.C. § 6114 / Reg. § 301.6114-1 disclosure for the treaty-based return position.",
        triggered_because="treaty re-sourcing position claimed AND DBA-USA Art. 28 LOB qualified",
        feeds_into=(),  # standalone disclosure attached to Form 1040
        role="standalone",
    ),
    FormSpec(
        basename="2025_form_8938_status.md",
        display_name="Form 8938 — FATCA Filing Determination (Status Sheet)",
        what_for="26 U.S.C. § 6038D filing determination for specified foreign financial assets.",
        triggered_because="foreign financial assets workspace fact present",
        feeds_into=(),  # standalone (attached to Form 1040 if Form 8938 itself is required)
        role="standalone",
    ),
    FormSpec(
        basename="2025_fincen_114_status.md",
        display_name="FinCEN Form 114 (FBAR) — Filing Determination (Status Sheet)",
        what_for="31 U.S.C. § 5314 / 31 CFR § 1010.350 filing determination — FBAR is filed SEPARATELY at FinCEN, NOT with Form 1040.",
        triggered_because="aggregate foreign financial accounts may exceed $10,000",
        feeds_into=(),  # standalone — filed at https://bsaefiling.fincen.treas.gov/
        role="standalone",
    ),
    FormSpec(
        basename="2025_1040.md",
        display_name="Form 1040 — U.S. Individual Income Tax Return (main return)",
        what_for="The main return — every other form feeds into this.",
        triggered_because="U.S. filing required (26 U.S.C. § 6012)",
        feeds_into=(),
        role="main_return",
    ),
)


# ----- Germany dependency graph ------------------------------------------
#
# Authority: ELSTER help (2025) — https://www.elster.de/eportal/helpGlobal
# and per-Anlage instructions on https://www.gesetze-im-internet.de/estg/.
# Anlagen feed into the Hauptvordruck (Mantelbogen) total assembly:
# Anlage N → wage section, Anlage KAP → § 32d capital tax line, Anlage
# AUS → § 34c FTC, Anlage Vorsorgeaufwand / Sonderausgaben → § 10 / § 33a
# Sonderausgaben sum, Anlage Kind → Familienleistungsausgleich, Anlage
# SO → § 22 Nr. 3 other-income line.

GERMANY_FORMS: tuple[FormSpec, ...] = (
    FormSpec(
        basename="2025_anlage_n_person_1.md",
        display_name="Anlage N — Person 1 (Bruttoarbeitslohn / Werbungskosten)",
        what_for="Person 1's wage income and § 9 EStG Werbungskosten.",
        triggered_because="Person 1 has wage income (Lohnsteuerbescheinigung present)",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={
            "Anlage N Zeile 6 (Bruttoarbeitslohn)": "→ Mantelbogen wage assembly",
            "Anlage N Zeile 7 (Einbehaltene Lohnsteuer)": "→ Mantelbogen § 36 Abs. 2 Nr. 2 EStG credit",
            "Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag)": "→ Mantelbogen SolzG credit",
        },
    ),
    FormSpec(
        basename="2025_anlage_n_person_2.md",
        display_name="Anlage N — Person 2 (Bruttoarbeitslohn / Werbungskosten)",
        what_for="Person 2's wage income and § 9 EStG Werbungskosten (joint assessment only).",
        triggered_because="Person 2 has wage income (joint Veranlagung, Lohnsteuerbescheinigung present)",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={
            "Anlage N Zeile 6 (Bruttoarbeitslohn)": "→ Mantelbogen wage assembly",
            "Anlage N Zeile 7 (Einbehaltene Lohnsteuer)": "→ Mantelbogen § 36 Abs. 2 Nr. 2 EStG credit",
            "Anlage N Zeile 8 (Einbehaltener Solidaritätszuschlag)": "→ Mantelbogen SolzG credit",
        },
    ),
    FormSpec(
        basename="2025_anlage_kap_person_1.md",
        display_name="Anlage KAP — Person 1 (Capital Income § 20 EStG)",
        what_for="Person 1's foreign / domestic capital income and § 32d Abs. 5 EStG foreign-tax credit input.",
        triggered_because="Person 1 has capital income (broker / bank statements)",
        feeds_into=("2025_anlage_aus.md", "2025_hauptvordruck.md"),
        transfer_targets={
            "Anlage KAP Zeile 41": "→ Anlage AUS per-country foreign-tax aggregation",
        },
    ),
    FormSpec(
        basename="2025_anlage_kap_person_2.md",
        display_name="Anlage KAP — Person 2 (Capital Income § 20 EStG)",
        what_for="Person 2's foreign / domestic capital income and § 32d Abs. 5 EStG foreign-tax credit input.",
        triggered_because="Person 2 has capital income (joint Veranlagung, broker / bank statements)",
        feeds_into=("2025_anlage_aus.md", "2025_hauptvordruck.md"),
        transfer_targets={
            "Anlage KAP Zeile 41": "→ Anlage AUS per-country foreign-tax aggregation",
        },
    ),
    FormSpec(
        basename="2025_anlage_kap_inv.md",
        display_name="Anlage KAP-INV (Investmentfonds — InvStG)",
        what_for="Investment-fund distributions, Vorabpauschale, and Aktienfonds / sonstige Fonds gain/loss.",
        triggered_because="investment-fund (InvStG) holdings present in the capital book",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={},
    ),
    FormSpec(
        basename="2025_anlage_aus.md",
        display_name="Anlage AUS (Auslandseinkünfte / § 34c EStG FTC)",
        what_for="Per-country foreign-tax credit under § 34c (1) EStG; reconciles to the § 32d (5) per-Posten cap.",
        triggered_because="foreign tax paid on capital / wage income",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={
            "Anlage AUS Aggregate (cross-check)": "→ Mantelbogen § 34c EStG FTC line",
        },
    ),
    FormSpec(
        basename="2025_anlage_vorsorgeaufwand.md",
        display_name="Anlage Vorsorgeaufwand (§ 10 EStG)",
        what_for="Beiträge zur Altersvorsorge / Krankenversicherung / sonstige Vorsorgeaufwendungen.",
        triggered_because="Vorsorgeaufwendungen present in payroll / private statements",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={},
    ),
    FormSpec(
        basename="2025_anlage_sonderausgaben.md",
        display_name="Anlage Sonderausgaben (§§ 10b, 33a, 10c EStG)",
        what_for="Spendenabzug, Unterhaltsleistungen, Sonderausgaben-Pauschbetrag.",
        triggered_because="Spenden / Unterhalt or always (§ 10c Pauschbetrag)",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={},
    ),
    FormSpec(
        basename="2025_anlage_kind.md",
        display_name="Anlage Kind (§ 32 / § 33b EStG)",
        what_for="Per-child Kinderfreibetrag + BEA + transferred Behinderten-Pauschbetrag.",
        triggered_because="children declared OR transferred § 33b Abs. 5 Pauschbetrag",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={},
    ),
    FormSpec(
        basename="2025_anlage_so.md",
        display_name="Anlage SO (§ 22 Nr. 3, § 23 EStG)",
        what_for="Other income under § 22 Nr. 3 EStG and private-sale gains/losses under § 23.",
        triggered_because="other income (§ 22 Nr. 3) or private-sale items present",
        feeds_into=("2025_hauptvordruck.md",),
        transfer_targets={},
    ),
    FormSpec(
        basename="2025_hauptvordruck.md",
        display_name="Hauptvordruck (Mantelbogen — main return)",
        what_for="The cover sheet — identity, Veranlagungsart, banking, Anlagen assembly.",
        triggered_because="every Einkommensteuererklärung",
        feeds_into=(),
        role="main_return",
    ),
)


# ----- Topological sort -------------------------------------------------


def _topological_sort(forms: Iterable[FormSpec]) -> list[FormSpec]:
    """Return ``forms`` in dependency order (a form's ``feeds_into``
    targets all appear AFTER it).

    Tie-break (in priority order):

    1. **Functional forms before standalone forms.** A form with
       ``feeds_into`` non-empty represents real numeric flow into a
       downstream form (e.g., Form 8949 → Schedule D). A form with
       empty ``feeds_into`` is a disclosure / status sheet (e.g., Form
       8833, FinCEN 114 status, Form 8938 status) and the user wants
       to handle those AFTER walking through the numeric chain — but
       still BEFORE the main return (Form 1040 / Hauptvordruck), which
       is always last because everything feeds into it.
    2. **Lexicographic on basename** for full determinism within a tie.

    Standalone-vs-functional is decided by the ``feeds_into`` field
    when the catalog is authored — the topo sort just respects it.
    """
    forms_list = list(forms)
    by_name = {form.basename: form for form in forms_list}
    # in_degree[name] = number of incoming edges (= number of forms
    # that feed INTO this form). A form with in_degree 0 has no
    # prerequisites and can come first.
    in_degree: dict[str, int] = {form.basename: 0 for form in forms_list}
    for form in forms_list:
        for downstream in form.feeds_into:
            if downstream in in_degree:
                in_degree[downstream] += 1

    def _priority(name: str) -> tuple[int, str]:
        # Priority bucket: functional (1) → standalone (2) → main return (3).
        # See FormSpec.role docstring for the rationale.
        spec = by_name[name]
        role_bucket = {"functional": 1, "standalone": 2, "main_return": 3}.get(
            spec.role, 1
        )
        return (role_bucket, name)

    ordered: list[FormSpec] = []
    # Kahn's algorithm with deterministic tie-break.
    while in_degree:
        ready_names = [name for name, degree in in_degree.items() if degree == 0]
        ready_names.sort(key=_priority)
        if not ready_names:
            # Cycle detected — return the remaining forms in
            # lexicographic order rather than crashing the renderer.
            ordered.extend(by_name[name] for name in sorted(in_degree))
            break
        # Take only the highest-priority ready form per pass so the
        # priority ordering propagates through the DAG layers.
        head = ready_names[0]
        ordered.append(by_name[head])
        for downstream in by_name[head].feeds_into:
            if downstream in in_degree:
                in_degree[downstream] -= 1
        del in_degree[head]
    return ordered


# ----- Markdown line-table parsing -------------------------------------


_LINE_TABLE_HEADER_RE = re.compile(r"^\s*\|\s*Line\s*\|\s*Value\s*\|\s*Source\s*\|\s*Notes\s*\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|\s*-+\s*\|")


def _split_table_row(row: str) -> list[str]:
    # Drop leading and trailing pipe, then split on `|`. The renderer
    # markdown does not contain unescaped `|` inside cells (see
    # ``markdown_table`` in forms/common.py).
    inner = row.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [cell.strip() for cell in inner.split("|")]


def parse_lines_table(markdown_text: str) -> list[tuple[str, str, str, str]]:
    """Extract the ``## Lines`` table rows from a rendered form Markdown.

    Returns a list of ``(line, value, source, notes)`` tuples in the
    file's original order. Missing or malformed tables return an empty
    list — the guide renderer treats this as "no per-line entries to
    walk through" and surfaces a posture-only step (e.g., Form 8833
    disclosure).
    """
    lines = markdown_text.splitlines()
    in_table = False
    after_separator = False
    rows: list[tuple[str, str, str, str]] = []
    for raw in lines:
        if not in_table:
            if _LINE_TABLE_HEADER_RE.match(raw):
                in_table = True
                after_separator = False
            continue
        if not after_separator:
            if _TABLE_SEPARATOR_RE.match(raw):
                after_separator = True
            continue
        # Table body: stop on the first non-table line (blank or `## ...`).
        stripped = raw.strip()
        if not stripped or not stripped.startswith("|"):
            break
        cells = _split_table_row(raw)
        if len(cells) < 4:
            # Pad trailing empty cells when notes is empty.
            cells = cells + [""] * (4 - len(cells))
        rows.append((cells[0], cells[1], cells[2], cells[3]))
    return rows


_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$")


def parse_title(markdown_text: str) -> str | None:
    for line in markdown_text.splitlines():
        match = _TITLE_RE.match(line)
        if match:
            return match.group(1)
    return None


# ----- Renderer ---------------------------------------------------------


def _render_section_a(
    ordered: list[FormSpec],
    forms_root: Path,
) -> list[str]:
    """Section A — numbered filing-order list."""
    out: list[str] = ["## Section A — Form filing order", ""]
    for index, form in enumerate(ordered, start=1):
        link = f"[{form.basename}]({form.basename})"
        feeds_into = (
            ", ".join(
                _display_name(target, forms_root) or target
                for target in form.feeds_into
            )
            if form.feeds_into
            else "Standalone"
        )
        out.append(f"### Step {index}. {form.display_name}")
        out.append("")
        out.append(f"- File: {link}")
        out.append(f"- What this is for: {form.what_for}")
        out.append(f"- Triggered because: {form.triggered_because}")
        out.append(f"- Feeds into: {feeds_into}")
        out.append("")
    return out


def _display_name(basename: str, forms_root: Path) -> str | None:
    """Best-effort display-name lookup for a form basename."""
    # Try the curated catalogs first.
    for catalog in (USA_FORMS, GERMANY_FORMS):
        for spec in catalog:
            if spec.basename == basename:
                return spec.display_name
    # Fall back to the rendered file's title.
    path = forms_root / basename
    if path.exists():
        title = parse_title(path.read_text(encoding="utf-8"))
        if title:
            return title
    return None


def _render_section_b(
    ordered: list[FormSpec],
    forms_root: Path,
) -> list[str]:
    """Section B — per-form fill-in checklist (Zeile-by-Zeile)."""
    out: list[str] = ["## Section B — Per-form fill-in checklist", ""]
    for index, form in enumerate(ordered, start=1):
        path = forms_root / form.basename
        out.append(f"### Step {index}. {form.display_name}")
        out.append("")
        out.append(f"Open: [{form.basename}]({form.basename})")
        out.append("")
        if not path.exists():
            out.append("> Form Markdown is missing — re-run the pipeline to regenerate.")
            out.append("")
            continue
        text = path.read_text(encoding="utf-8")
        rows = parse_lines_table(text)
        if not rows:
            out.append("> This form has no per-line numeric entries — see the form Markdown for posture / disclosure text to enter verbatim.")
            out.append("")
            continue
        out.append("Enter each line in the order shown:")
        out.append("")
        out.append("| # | Line / Zeile | Value to enter | Source | Cross-form transfer / Notes |")
        out.append("| --- | --- | --- | --- | --- |")
        for line_no, (line, value, source, notes) in enumerate(rows, start=1):
            transfer = form.transfer_targets.get(line, "")
            combined_notes = transfer
            if notes:
                combined_notes = f"{transfer} — {notes}" if transfer else notes
            out.append(
                "| {n} | {line} | {value} | {source} | {notes} |".format(
                    n=line_no,
                    line=line,
                    value=value,
                    source=source,
                    notes=combined_notes,
                )
            )
        out.append("")
    return out


def _existing_forms_in_order(
    catalog: tuple[FormSpec, ...],
    forms_root: Path,
) -> list[FormSpec]:
    """Filter ``catalog`` to forms whose Markdown actually exists, then
    topologically sort. A missing file means the rule graph (or a
    conditional renderer) determined the form does not apply for this
    workspace — per CLAUDE.md invariant I13, the guide must reflect
    that absence rather than fabricating a zero-line entry."""
    present = [form for form in catalog if (forms_root / form.basename).exists()]
    return _topological_sort(present)


def render_usa_filing_guide(paths: YearPaths) -> Path:
    """Render ``outputs/forms/usa/FILING-GUIDE.md``.

    Caller is responsible for gating on
    ``elections.us_filing_required=true`` (CLAUDE.md invariant I13).
    """
    forms_root = paths.usa_forms_root
    ordered = _existing_forms_in_order(USA_FORMS, forms_root)
    sections: list[str] = [
        f"# U.S. Filing Guide — {paths.year}",
        "",
        "Walkthrough for filing the U.S. side of this return into IRS Free File / TurboTax / a preparer's software.",
        "",
        "**How to use this guide:**",
        "",
        "1. Work through Section A (filing order) so you know which form to open first, second, third.",
        "2. For each form, jump to its entry in Section B and type the listed values into the matching IRS line in IRS Free File / your preparer's software.",
        "3. Each line carries a Source citation showing where the engine pulled the number from. Spot-check against the underlying broker / payroll document before submitting.",
        "4. Cross-form transfers are explicit (e.g., Schedule D Line 16 → Form 1040 Line 7). When you reach Form 1040, every line is either typed in directly or transferred from a prior form.",
        "",
        f"Authority: Form 1040 instructions (2025) — {IRS_FORM_1040_INSTRUCTIONS_URL}",
        "",
    ]
    sections.extend(_render_section_a(ordered, forms_root))
    sections.extend(_render_section_b(ordered, forms_root))
    sections.extend(
        [
            "## You're done",
            "",
            f"- File the main return via IRS Free File ({IRS_FREE_FILE_URL}), TurboTax / H&R Block / a preparer, or paper-mail.",
            f"- **FBAR (FinCEN Form 114) is filed SEPARATELY at {FBAR_BSA_EFILING_URL} — NOT with Form 1040.** See `2025_fincen_114_status.md` for the determination.",
            "- **Form 8938 (FATCA)** is attached to Form 1040 if required. See `2025_form_8938_status.md` for the determination.",
            "",
            "## Source files",
            "",
            "- `final-legal-output.json` (the audited rule-graph output every line in this guide traces to)",
            "- Per-form Markdown files in this directory (each line in Section B links back to its source form)",
            "",
        ]
    )
    output_path = forms_root / "FILING-GUIDE.md"
    output_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return output_path


def render_germany_filing_guide(paths: YearPaths) -> Path:
    """Render ``outputs/forms/germany/FILING-GUIDE.md``."""
    forms_root = paths.germany_forms_root
    ordered = _existing_forms_in_order(GERMANY_FORMS, forms_root)
    sections: list[str] = [
        f"# Deutscher Filing-Guide — {paths.year}",
        "",
        "Walkthrough für die Eingabe der ESt-Erklärung 2025 in ELSTER (oder ein vergleichbares Steuerprogramm).",
        "",
        "**Verwendung dieses Guides:**",
        "",
        "1. Section A zeigt die Reihenfolge der Anlagen / Mantelbogen.",
        "2. Section B listet pro Anlage jede Zeile in der Reihenfolge, in der ELSTER sie abfragt — Wert, Quelle, Verweis.",
        "3. Cross-form-Transfers (z. B. Anlage N Zeile 6 → Mantelbogen Bruttoarbeitslohn) sind explizit. Wenn der Mantelbogen erreicht wird, sind alle Zeilen entweder direkt eingegeben oder aus einer Anlage übernommen.",
        "",
        f"Authority: ELSTER Hilfe — {ELSTER_HELP_URL}",
        "",
        "**Usage (EN):**",
        "",
        "1. Section A is the fill-out order (Anlage → Mantelbogen).",
        "2. Section B walks each Anlage Zeile-by-Zeile in the order ELSTER presents them.",
        "3. Cross-form transfers to the Hauptvordruck (Mantelbogen) are explicit.",
        "",
    ]
    sections.extend(_render_section_a(ordered, forms_root))
    sections.extend(_render_section_b(ordered, forms_root))
    sections.extend(
        [
            "## Fertig / Done",
            "",
            f"- Reichen Sie die Erklärung über ELSTER ein: {ELSTER_PORTAL_URL}",
            "- Submit the assembled return via ELSTER (the Mantelbogen + every attached Anlage).",
            "",
            "## Source files",
            "",
            "- `final-legal-output.json` (audited rule-graph output every Zeile in this guide traces to)",
            "- Per-Anlage Markdown files in this directory (each Section B row links back to its source form)",
            "",
        ]
    )
    output_path = forms_root / "FILING-GUIDE.md"
    output_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return output_path
