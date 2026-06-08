from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from tax_pipeline.core.narrative import RuleNarrative, rule_narrative_from_mapping

DEFAULT_TEMPLATE_ROOT = Path(__file__).resolve().parent / "templates"


def _as_rule(payload: RuleNarrative | Mapping[str, Any]) -> RuleNarrative:
    if isinstance(payload, RuleNarrative):
        return payload
    return rule_narrative_from_mapping(payload)


def _filter_from_json(value: str) -> Any:
    # Parse a JSON-stringified payload (typically a structured rule output dict)
    # so prose templates can weave specific fields into sentences. The packet
    # builder formats dict/list outputs with json.dumps, so this is the inverse.
    return json.loads(value)


def _filter_money(value: object, *, currency: str = "") -> str:
    # Format a numeric value as a thousands-separated amount with the supplied
    # currency suffix. Accepts the JSON-formatted Decimal strings produced by
    # the packet builder as well as raw numbers.
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    sign = "-" if amount < 0 else ""
    absolute = -amount if amount < 0 else amount
    quantized = absolute.quantize(Decimal("0.01"))
    integer_part, _, fractional_part = format(quantized, "f").partition(".")
    grouped = "{:,}".format(int(integer_part))
    body = f"{sign}{grouped}.{fractional_part}" if fractional_part else f"{sign}{grouped}"
    return f"{body} {currency}".rstrip() if currency else body


def _environment(template_root: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["from_json"] = _filter_from_json
    env.filters["money"] = _filter_money
    return env


def render_narrative_markdown(
    narratives: Iterable[RuleNarrative | Mapping[str, Any]],
    *,
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
    title: str,
) -> str:
    env = _environment(template_root)
    lines = [f"# {title}", ""]
    for payload in narratives:
        rule = _as_rule(payload)
        template_name = f"{rule.template_id}.jinja"
        template_path = template_root / template_name
        if not template_path.exists():
            raise FileNotFoundError(f"Missing rule narrative template: {template_name}")
        try:
            rendered = env.get_template(template_name).render(rule=rule.to_dict())
        except TemplateError as exc:
            raise ValueError(f"Failed to render rule narrative template {template_name}: {exc}") from exc
        lines.append(rendered.strip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_narrative_to_path(
    narratives: Iterable[RuleNarrative | Mapping[str, Any]],
    *,
    output_path: Path,
    title: str,
    template_root: Path = DEFAULT_TEMPLATE_ROOT,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_narrative_markdown(narratives, template_root=template_root, title=title), encoding="utf-8")
    return output_path


__all__ = ["render_narrative_markdown", "render_narrative_to_path"]
