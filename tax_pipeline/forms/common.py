from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.legal_value import LegalValue, require_legal_value
from tax_pipeline.core.money import Currency, Money


@dataclass(frozen=True)
class FormEntry:
    """A single rendered form-line row.

    ``provenance`` carries the (stage_id, output_key, fingerprint) triple
    when this entry was built via :func:`legal_value_entry` — invariant
    I11's form-renderer boundary. The markdown renderer does NOT render
    this field into the visible table; it stays on the FormEntry as a
    structured audit handle that downstream consumers (audit packets,
    JSON exports) can inspect without parsing notes-as-text.
    """

    line: str
    value: str
    source: str = ""
    notes: str = ""
    provenance: tuple[str, str, str] | None = None


def _resolve_unit_label(
    *,
    legal_currency: Currency | None,
    arg_currency: Currency | None,
    unit: str | None,
    context: str,
) -> str:
    """Resolve the rendering unit label from (priority order):

    1. an explicit ``currency=`` argument passed by the caller (P4),
    2. a :class:`Currency` tag carried on the :class:`LegalValue`
       envelope (P4 transitional path),
    3. the legacy ``unit=`` string label (back-compat for un-migrated
       call sites — accepts both ISO-4217 codes and non-currency labels
       like ``"count"`` for Schedule 8812 line-4 / line-6 dependent
       counts).

    Returns the unit label as a string (the ISO-4217 code for currency
    paths, or the verbatim ``unit=`` argument for non-currency labels).
    The default when nothing is supplied is ``"EUR"`` for parity with
    pre-P4 behavior.
    """
    if arg_currency is not None:
        if not isinstance(arg_currency, Currency):
            raise TypeError(
                f"{context}: currency must be a Currency enum member; "
                f"got {type(arg_currency).__qualname__}"
            )
        return arg_currency.value
    if legal_currency is not None:
        return legal_currency.value
    if unit is None:
        # No currency supplied at any layer — preserve the historical
        # default of EUR for the un-migrated call sites that omitted
        # ``unit=`` entirely.
        return Currency.EUR.value
    # Legacy free-text label path. Accepts both currency codes (USD,
    # EUR) and non-currency markers (``"count"`` for dependent-count
    # form lines). Non-currency unit labels remain untyped during the
    # P4 migration window — no future country will need them, but
    # Schedule 8812 line-4 / line-6 do.
    return unit


def legal_value_entry(
    line: str,
    value: LegalValue,
    *,
    unit: str | None = None,
    currency: Currency | None = None,
    source: str = "",
    notes: str = "",
) -> FormEntry:
    """Build a :class:`FormEntry` from a :class:`LegalValue` envelope.

    The form-renderer boundary guard for invariant I11. Passing a raw
    ``Decimal`` here fails closed with a ``TypeError`` (via
    ``require_legal_value``). The ``(stage_id, output_key, fingerprint)``
    provenance is captured on the returned ``FormEntry.provenance``
    structured field so audit consumers can inspect it without parsing
    notes-as-text. The visible ``notes`` are left untouched so renderer
    fixtures stay stable.

    P4: ``currency`` is the typed-currency replacement for the legacy
    ``unit=`` string argument. Both are accepted during the migration
    window — see :func:`_resolve_currency` for the priority order. The
    rendered cell text remains ``"<amount> <ISO-4217-code>"`` so all
    pre-P4 form-output fixtures stay byte-identical.

    See ``docs/invariant-migration-plan.md`` §6 / WS-4D and
    ``CLAUDE.md`` invariant I11.
    """
    legal = require_legal_value(value, context=f"{line}")
    unit_label = _resolve_unit_label(
        legal_currency=legal.currency,
        arg_currency=currency,
        unit=unit,
        context=f"legal_value_entry({line!r})",
    )
    formatted = format_currency(legal.amount, unit_label)
    provenance_triple = (legal.stage_id, legal.output_key, legal.fingerprint)
    return FormEntry(
        line=line,
        value=formatted,
        source=source,
        notes=notes,
        provenance=provenance_triple,
    )


def _coerce_decimal(value: object, *, context: str) -> Decimal:
    """Best-effort Decimal coercion for legal-value rendering.

    Form-line values reach the renderer as either a numeric Decimal (rule
    output) or a pre-formatted string (JSON-serialized projection of a
    rule output). Both reduce to the same canonical Decimal via
    ``Decimal(str(value))``. Anything else (None, dict, list) is a
    boundary defect — fail closed with a clear context.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, str)):
        try:
            return Decimal(str(value))
        except Exception as exc:  # noqa: BLE001 - re-wrapped with context
            raise TypeError(
                f"{context}: cannot coerce form-line value to Decimal: {value!r}"
            ) from exc
    raise TypeError(
        f"{context}: form-line value must be Decimal/int/str; got "
        f"{type(value).__qualname__}"
    )


def _stage_provenance_lookup(
    provenance: Mapping[str, Any] | None,
    *,
    country: str,
    output_key: str,
) -> dict[str, str] | None:
    """Return a real stage-backed (stage_id, fingerprint) triple if the
    final-legal-output ``_provenance`` block carries one for this output_key.

    The map is structured as
    ``provenance["form_lines"][country][output_key] = {stage_id, output_key,
    fingerprint}``. Most form-line scalars are renderer-side projections
    of stage outputs (e.g., ``form_1040.line_1z_total_wages_usd`` is a
    projection of ``us.stage.wages_usd`` produced by US25-01) and therefore
    do not have a direct match here. Callers must fall back to a
    renderer-derived deterministic fingerprint when this returns ``None``.
    """
    if not isinstance(provenance, Mapping):
        return None
    form_lines = provenance.get("form_lines")
    if not isinstance(form_lines, Mapping):
        return None
    by_country = form_lines.get(country)
    if not isinstance(by_country, Mapping):
        return None
    triple = by_country.get(output_key)
    if not isinstance(triple, Mapping):
        return None
    stage_id = str(triple.get("stage_id", "")).strip()
    fingerprint = str(triple.get("fingerprint", "")).strip()
    if not stage_id or not fingerprint:
        return None
    return {
        "stage_id": stage_id,
        "output_key": str(triple.get("output_key", output_key)),
        "fingerprint": fingerprint,
    }


def legal_value_from_dict(
    container: Mapping[str, Any],
    line_key: str,
    *,
    country: str,
    section: str,
    provenance: Mapping[str, Any] | None = None,
    provenance_output_key: str | None = None,
    currency: Currency | None = None,
) -> LegalValue:
    """Renderer-side adapter that wraps a JSON-projected scalar in a
    :class:`LegalValue` envelope (invariant I11 / F-CQ-1).

    Form renderers consume ``final-legal-output.json`` — a fully
    serialized projection of the rule-graph result — and pull form-line
    scalars from nested dicts (e.g., ``treaty["form_1040"][line_key]``).
    Before WS-4D the value flowed straight into ``format_currency(...)``
    as a bare ``Decimal``-or-string with no provenance. This adapter
    makes the form-line boundary load-bearing for I11 by wrapping every
    scalar in a typed ``LegalValue`` whose ``(stage_id, output_key,
    fingerprint)`` is either taken from the
    ``final-legal-output.json:_provenance.form_lines`` block (when the
    rule-graph attaches one for this output_key) or derived
    deterministically from the JSON path + value (when the form-line
    scalar is a renderer-side projection of a stage output rather than
    an output_key directly).

    ``provenance_output_key`` lets callers decouple the dict-access key
    (``line_key``) from the provenance-lookup key. This is required when
    a renderer-side projection block uses line-numbered keys (e.g.,
    ``line_10_modified_agi_usd``) but the corresponding declared rule
    output uses the executor namespace (``us.ctc.modified_agi_usd``).
    Without the override, the lookup would miss the real
    ``StageResult.output_fingerprint`` and fall back to a synthesized
    fingerprint — which violates invariants I2 / I11 for any value the
    rule already commits to.

    Authority: § 32d Abs. 5 EStG, 26 U.S.C. § 901 — both require a
    verifiable per-line foreign-tax / credit basis.
    https://www.gesetze-im-internet.de/estg/__32d.html
    https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
    """
    if line_key not in container:
        raise KeyError(
            f"legal_value_from_dict: missing form-line key {line_key!r} in "
            f"section {section!r}"
        )
    raw = container[line_key]
    amount = _coerce_decimal(raw, context=f"{country}.{section}.{line_key}")
    lookup_key = provenance_output_key if provenance_output_key is not None else line_key
    real = _stage_provenance_lookup(provenance, country=country, output_key=lookup_key)
    if real is not None:
        return LegalValue(
            amount=amount,
            stage_id=real["stage_id"],
            output_key=real["output_key"],
            fingerprint=real["fingerprint"],
            currency=currency,
        )
    # Renderer-side projection — synthesize a deterministic fingerprint
    # from (country, section, line_key, value). The fingerprint is
    # reproducible (stable_fingerprint over canonical Decimal payload),
    # so the audit trail still binds the form-line value to a verifiable
    # triple. This is the Shape-A wiring described in F-CQ-1: the goal
    # is for every form-line write to transit ``legal_value_entry``,
    # not for every scalar to acquire a parallel third-domain hash chain.
    synthetic_stage_id = f"renderer:{country}:{section}"
    fingerprint = stable_fingerprint(
        {
            "stage_id": synthetic_stage_id,
            "output_key": line_key,
            "value": amount,
        }
    )
    return LegalValue(
        amount=amount,
        stage_id=synthetic_stage_id,
        output_key=line_key,
        fingerprint=fingerprint,
        currency=currency,
    )


def legal_value_from_decimal(
    amount: object,
    *,
    country: str,
    section: str,
    output_key: str,
    provenance: Mapping[str, Any] | None = None,
    currency: Currency | None = None,
) -> LegalValue:
    """Wrap a renderer-computed Decimal/string in a :class:`LegalValue`.

    Used for form-line values that are not pulled directly from a JSON
    container key — e.g., a row from ``us-tax-trace.csv`` (looked up by
    ``step``) or a Decimal already extracted by a small lookup helper
    in the renderer. Same provenance discipline as
    :func:`legal_value_from_dict`: stage-backed if available, otherwise
    deterministic synthetic from (country, section, output_key, value).
    """
    amount_dec = _coerce_decimal(amount, context=f"{country}.{section}.{output_key}")
    real = _stage_provenance_lookup(provenance, country=country, output_key=output_key)
    if real is not None:
        return LegalValue(
            amount=amount_dec,
            stage_id=real["stage_id"],
            output_key=real["output_key"],
            fingerprint=real["fingerprint"],
            currency=currency,
        )
    synthetic_stage_id = f"renderer:{country}:{section}"
    fingerprint = stable_fingerprint(
        {
            "stage_id": synthetic_stage_id,
            "output_key": output_key,
            "value": amount_dec,
        }
    )
    return LegalValue(
        amount=amount_dec,
        stage_id=synthetic_stage_id,
        output_key=output_key,
        fingerprint=fingerprint,
        currency=currency,
    )


def markdown_heading(title: str, level: int = 1) -> str:
    if level < 1:
        raise ValueError("Heading level must be at least 1")
    return f"{'#' * level} {html.escape(title)}"


def markdown_link(label: str, target: str) -> str:
    return f"[{html.escape(label)}]({target})"


def _escape_table_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return html.escape(text).replace("|", r"\|")


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    header_row = "| " + " | ".join(_escape_table_cell(header) for header in headers) + " |"
    separator_row = "| " + " | ".join("---" for _ in headers) + " |"
    body_rows = [
        "| " + " | ".join(_escape_table_cell(cell) for cell in row) + " |"
        for row in rows
    ]
    return "\n".join([header_row, separator_row, *body_rows])


def format_currency(value: object, unit: str = "EUR") -> str:
    """Render a Decimal/string/:class:`Money` to a tabular cell string.

    Three call shapes:
      * ``format_currency(Decimal("100"), "USD")`` — legacy bare
        Decimal + free-text unit (still supported for the un-migrated
        call sites).
      * ``format_currency("100.00", "EUR")`` — ditto, for JSON-side
        scalars that arrive pre-stringified.
      * ``format_currency(Money(amount=Decimal("100"), currency=USD))``
        — P4 typed-currency path. The ``unit`` argument is ignored when
        a :class:`Money` is passed; the currency tag wins.

    The cell text is ``"<amount>.NN <ISO-4217-code>"`` in every case so
    the rendered Markdown is byte-identical pre / post P4 for any
    LegalValue whose Decimal hasn't changed.
    """
    if isinstance(value, Money):
        return f"{value.amount:.2f} {value.currency.value}"
    return f"{Decimal(str(value)):.2f} {unit}"


def result_phrase(amount: object, unit: str = "EUR") -> str:
    value = Decimal(str(amount))
    return f"{format_currency(abs(value), unit)} {'refund' if value >= 0 else 'balance due'}"


def required_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing required analysis artifact: {path}")
    return path.read_text(encoding="utf-8")


def required_json(path: Path) -> dict:
    return json.loads(required_text(path))


def required_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required analysis artifact: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def ensure_required_paths(paths: Sequence[Path], *, label: str) -> None:
    missing = [path for path in paths if not path.exists()]
    if missing:
        names = ", ".join(path.name for path in missing)
        raise FileNotFoundError(f"Missing {label}: {names}")


def clear_markdown_outputs(root: Path) -> None:
    if not root.exists():
        return
    for path in root.glob("*.md"):
        path.unlink()


def _bullet_list(lines: Iterable[str]) -> list[str]:
    return [f"- {html.escape(line)}" for line in lines]


def write_form(
    path: Path,
    title: str,
    posture_lines: Iterable[str] | None,
    entries: Sequence[FormEntry],
    notes: Iterable[str] | None,
) -> str:
    sections: list[str] = [markdown_heading(title)]

    posture_items = list(posture_lines or [])
    if posture_items:
        sections.extend(["", markdown_heading("Posture", level=2)])
        sections.extend(_bullet_list(posture_items))

    if entries:
        sections.extend(["", markdown_heading("Lines", level=2)])
        sections.append(
            markdown_table(
                ("Line", "Value", "Source", "Notes"),
                ((entry.line, entry.value, entry.source, entry.notes) for entry in entries),
            )
        )

    note_items = list(notes or [])
    if note_items:
        sections.extend(["", markdown_heading("Notes", level=2)])
        sections.extend(_bullet_list(note_items))

    content = "\n".join(sections).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return content
