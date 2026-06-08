"""Invariant I11 — Form-bound legal values flow only via a typed LegalValue
envelope.

Authority for fail-closed enforcement: § 32d Abs. 5 EStG (per-Posten foreign
tax credit) and 26 U.S.C. § 901 require a verifiable, traceable foreign-tax
basis. The audit-trail discipline (CLAUDE.md) demands that every value
crossing into a form line carries its (stage_id, output_key, fingerprint)
provenance so a reviewer can trace the rule that produced it.

https://www.gesetze-im-internet.de/estg/__32d.html
https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
"""

from __future__ import annotations

import unittest
from decimal import Decimal
from typing import Any, Mapping

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.legal_value import (
    LegalValue,
    require_legal_value,
)
from tax_pipeline.core.money import Currency
from tax_pipeline.core.stages import (
    AuditWaypoint,
    FormLineRef,
    LawRule,
    LawStage,
    OutputDeclaration,
    execute_rule_graph,
)
from tax_pipeline.forms.common import (
    legal_value_entry,
    legal_value_from_decimal,
    legal_value_from_dict,
)


def _stage(stage_id: str, *, inputs: tuple[str, ...], outputs: tuple[str, ...]) -> LawStage:
    return LawStage(
        stage_id=stage_id,
        country_or_scope="DE",
        legal_refs=("§ 32d EStG",),
        authority_urls=("https://www.gesetze-im-internet.de/estg/__32d.html",),
        input_fact_keys=inputs,
        rounding_policy="cents",
        law_order_note=f"{stage_id} order note",
        legal_formula=f"{stage_id} legal formula expression",
        narrative_templates={"de": stage_id, "en": stage_id},
        outputs=tuple(
            OutputDeclaration(
                key=key,
                form_line_refs=(FormLineRef(form="Anlage KAP", line="Zeile 19", url="https://example.test"),),
            )
            for key in outputs
        ),
    )


class LegalValueValidationTest(unittest.TestCase):
    def test_construct_and_validate(self) -> None:
        fp = stable_fingerprint({"stage_id": "DE25-X", "output_key": "de.x", "value": Decimal("1.00")})
        value = LegalValue(
            amount=Decimal("1.00"),
            stage_id="DE25-X",
            output_key="de.x",
            fingerprint=fp,
        )
        self.assertEqual(value.amount, Decimal("1.00"))
        self.assertEqual(value.stage_id, "DE25-X")
        self.assertEqual(value.output_key, "de.x")
        self.assertEqual(value.fingerprint, fp)

    def test_amount_must_be_decimal(self) -> None:
        with self.assertRaises(TypeError):
            LegalValue(amount=1.0, stage_id="S", output_key="k", fingerprint="a" * 64)
        with self.assertRaises(TypeError):
            LegalValue(amount="1.00", stage_id="S", output_key="k", fingerprint="a" * 64)

    def test_string_fields_must_be_non_empty(self) -> None:
        with self.assertRaises(ValueError):
            LegalValue(amount=Decimal("0"), stage_id="", output_key="k", fingerprint="a" * 64)
        with self.assertRaises(ValueError):
            LegalValue(amount=Decimal("0"), stage_id="S", output_key="", fingerprint="a" * 64)
        with self.assertRaises(ValueError):
            LegalValue(amount=Decimal("0"), stage_id="S", output_key="k", fingerprint="")

    def test_require_legal_value_rejects_raw_decimal(self) -> None:
        # The form-renderer-boundary guard MUST reject a bare Decimal.
        with self.assertRaises(TypeError) as ctx:
            require_legal_value(Decimal("1.00"), context="Anlage KAP Zeile 19")
        self.assertIn("LegalValue", str(ctx.exception))
        self.assertIn("Anlage KAP Zeile 19", str(ctx.exception))

    def test_require_legal_value_accepts_legal_value(self) -> None:
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.00")})
        value = LegalValue(amount=Decimal("1.00"), stage_id="S", output_key="k", fingerprint=fp)
        self.assertIs(require_legal_value(value, context="Anlage KAP"), value)

    def test_currency_optional_defaults_to_none(self) -> None:
        # P4: ``currency`` is an optional field — call sites that don't
        # pass it default to None and the renderer falls back to the
        # legacy ``unit=`` path. This preserves the byte-stable md5s
        # of ``final-legal-output.json`` because the canonical payload
        # is unchanged for any LegalValue constructed without currency.
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.00")})
        value = LegalValue(
            amount=Decimal("1.00"),
            stage_id="S",
            output_key="k",
            fingerprint=fp,
        )
        self.assertIsNone(value.currency)

    def test_currency_carries_when_provided(self) -> None:
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.00")})
        value = LegalValue(
            amount=Decimal("1.00"),
            stage_id="S",
            output_key="k",
            fingerprint=fp,
            currency=Currency.USD,
        )
        self.assertEqual(value.currency, Currency.USD)

    def test_currency_must_be_enum_or_none(self) -> None:
        # Stray string labels (e.g. ``"USD"``) must fail closed —
        # the renderer relies on the closed Currency set.
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.00")})
        with self.assertRaises(TypeError):
            LegalValue(
                amount=Decimal("1.00"),
                stage_id="S",
                output_key="k",
                fingerprint=fp,
                currency="USD",  # type: ignore[arg-type]
            )


class FormatCurrencyMoneyTest(unittest.TestCase):
    """``format_currency`` accepts both legacy bare-Decimal + unit and
    typed Money — the renderer cell text is byte-identical in both
    paths so pre-P4 form-output goldens stay green.
    """

    def test_format_currency_accepts_money(self) -> None:
        from tax_pipeline.core.money import Money
        from tax_pipeline.forms.common import format_currency
        m = Money.usd(Decimal("100"))
        self.assertEqual(format_currency(m), "100.00 USD")

    def test_format_currency_accepts_money_eur(self) -> None:
        from tax_pipeline.core.money import Money
        from tax_pipeline.forms.common import format_currency
        m = Money.eur(Decimal("250.50"))
        self.assertEqual(format_currency(m), "250.50 EUR")

    def test_format_currency_legacy_decimal_unit(self) -> None:
        # Back-compat path: bare Decimal + free-text unit still works
        # for the un-migrated provider call sites.
        from tax_pipeline.forms.common import format_currency
        self.assertEqual(format_currency(Decimal("100"), "USD"), "100.00 USD")
        self.assertEqual(format_currency("250.50", "EUR"), "250.50 EUR")

    def test_format_currency_money_ignores_unit_arg(self) -> None:
        # When a Money is passed, the unit kwarg is irrelevant — the
        # currency tag wins. This is the documented P4 contract.
        from tax_pipeline.core.money import Money
        from tax_pipeline.forms.common import format_currency
        m = Money.usd(Decimal("1"))
        # Even with a contradicting unit= the Money's currency wins.
        self.assertEqual(format_currency(m, "EUR"), "1.00 USD")


class LegalValueEntryCurrencyTest(unittest.TestCase):
    """The form-line entry helper carries a typed Currency through to
    the rendered cell — both via the explicit ``currency=`` argument
    and via the LegalValue.currency tag (P4 transitional path).
    """

    def _value(self, *, currency=None) -> LegalValue:
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.23")})
        return LegalValue(
            amount=Decimal("1.23"),
            stage_id="S",
            output_key="k",
            fingerprint=fp,
            currency=currency,
        )

    def test_legal_value_entry_accepts_currency_kwarg(self) -> None:
        from tax_pipeline.forms.common import legal_value_entry
        entry = legal_value_entry("Line 1", self._value(), currency=Currency.USD)
        self.assertEqual(entry.value, "1.23 USD")

    def test_legal_value_entry_uses_currency_from_legal_value(self) -> None:
        from tax_pipeline.forms.common import legal_value_entry
        entry = legal_value_entry("Line 1", self._value(currency=Currency.EUR))
        self.assertEqual(entry.value, "1.23 EUR")

    def test_legal_value_entry_currency_kwarg_overrides_legal_value(self) -> None:
        # Per :func:`_resolve_unit_label`: explicit ``currency=`` arg
        # has highest priority and wins over a tag on the LegalValue.
        from tax_pipeline.forms.common import legal_value_entry
        entry = legal_value_entry(
            "Line 1",
            self._value(currency=Currency.EUR),
            currency=Currency.USD,
        )
        self.assertEqual(entry.value, "1.23 USD")

    def test_legal_value_entry_legacy_unit_still_works(self) -> None:
        # Back-compat: the ``unit="USD"`` path still produces the same
        # rendered cell text for un-migrated callers.
        from tax_pipeline.forms.common import legal_value_entry
        entry = legal_value_entry("Line 1", self._value(), unit="USD")
        self.assertEqual(entry.value, "1.23 USD")

    def test_legal_value_entry_non_currency_unit_passthrough(self) -> None:
        # Schedule 8812 line 4 / line 6 use ``unit="count"`` for
        # dependent counts. The free-text passthrough remains.
        from tax_pipeline.forms.common import legal_value_entry
        entry = legal_value_entry("Line 4", self._value(), unit="count")
        self.assertEqual(entry.value, "1.23 count")

    def test_legal_value_entry_rejects_string_currency(self) -> None:
        from tax_pipeline.forms.common import legal_value_entry
        with self.assertRaises(TypeError):
            legal_value_entry("Line 1", self._value(), currency="USD")  # type: ignore[arg-type]


class LegalValueFromDictCurrencyTest(unittest.TestCase):
    """``legal_value_from_dict`` propagates a typed Currency onto the
    returned :class:`LegalValue` so a downstream ``legal_value_entry``
    call doesn't need the redundant ``currency=`` kwarg."""

    def test_currency_propagates_through_from_dict(self) -> None:
        from tax_pipeline.forms.common import legal_value_from_dict
        container = {"line_1z": "12345.67"}
        lv = legal_value_from_dict(
            container, "line_1z",
            country="US", section="form_1040",
            currency=Currency.USD,
        )
        self.assertEqual(lv.currency, Currency.USD)

    def test_currency_propagates_through_from_decimal(self) -> None:
        from tax_pipeline.forms.common import legal_value_from_decimal
        lv = legal_value_from_decimal(
            Decimal("250.00"),
            country="DE", section="anlage_kap.zeile_19",
            output_key="creditable_foreign_tax_eur",
            currency=Currency.EUR,
        )
        self.assertEqual(lv.currency, Currency.EUR)


class RendererBoundaryTest(unittest.TestCase):
    """The form-renderer boundary helpers must reject raw Decimals
    (invariant I11) — Germany and U.S. batches both."""

    def _value(self) -> LegalValue:
        fp = stable_fingerprint({"stage_id": "S", "output_key": "k", "value": Decimal("1.23")})
        return LegalValue(amount=Decimal("1.23"), stage_id="S", output_key="k", fingerprint=fp)

    def test_legal_value_entry_accepts_legal_value(self) -> None:
        entry = legal_value_entry("Anlage KAP Zeile 19", self._value(), source="rule")
        self.assertEqual(entry.line, "Anlage KAP Zeile 19")
        self.assertIn("1.23", entry.value)
        # The full (stage_id, output_key, fingerprint) audit triple lives
        # on the structured ``provenance`` field — the markdown renderer
        # leaves it out of the visible row so renderer fixtures stay
        # stable, but audit consumers (final-legal-output JSON exports,
        # downstream auditors) read it directly off the FormEntry.
        self.assertEqual(entry.provenance, ("S", "k", self._value().fingerprint))
        # The visible notes are exactly what the caller passed (no auto-
        # injected provenance string, so existing form-output fixtures
        # are unchanged by the I11 wiring).
        self.assertEqual(entry.notes, "")

    def test_legal_value_entry_preserves_caller_notes(self) -> None:
        entry = legal_value_entry(
            "Line 1z", self._value(),
            unit="USD",
            source="us-treaty-package.json",
            notes="caller note text",
        )
        self.assertEqual(entry.notes, "caller note text")
        self.assertEqual(entry.provenance, ("S", "k", self._value().fingerprint))

    def test_legal_value_entry_rejects_raw_decimal(self) -> None:
        with self.assertRaises(TypeError):
            legal_value_entry("Anlage KAP Zeile 19", Decimal("1.23"), source="rule")

    def test_legal_value_from_dict_synthesizes_provenance(self) -> None:
        # When ``_provenance.form_lines[country]`` does not carry a triple
        # for the given output_key (the Shape A "renderer-side projection"
        # case), the adapter synthesizes a deterministic
        # (renderer:<country>:<section>, line_key, value) fingerprint so
        # the form-line write still transits a typed ``LegalValue``.
        container = {"line_1z_total_wages_usd": "12345.67"}
        lv = legal_value_from_dict(
            container, "line_1z_total_wages_usd",
            country="US", section="form_1040",
        )
        self.assertIsInstance(lv, LegalValue)
        self.assertEqual(lv.amount, Decimal("12345.67"))
        self.assertEqual(lv.stage_id, "renderer:US:form_1040")
        self.assertEqual(lv.output_key, "line_1z_total_wages_usd")
        self.assertEqual(len(lv.fingerprint), 64)  # sha256 hex
        # Determinism: same inputs => same fingerprint.
        lv2 = legal_value_from_dict(
            dict(container), "line_1z_total_wages_usd",
            country="US", section="form_1040",
        )
        self.assertEqual(lv.fingerprint, lv2.fingerprint)

    def test_legal_value_from_dict_prefers_real_provenance(self) -> None:
        # When ``_provenance.form_lines`` carries a real (stage_id,
        # output_key, fingerprint) triple, the adapter uses it verbatim
        # rather than synthesizing one. This is the audit-true path for
        # rule-graph stage outputs that happen to land under the same
        # JSON key as the form-line.
        real_fp = "a" * 64
        provenance = {
            "schema_version": 1,
            "form_lines": {
                "US": {
                    "us.stage.wages_usd": {
                        "stage_id": "US25-01-WAGE-TRANSLATION",
                        "output_key": "us.stage.wages_usd",
                        "fingerprint": real_fp,
                    }
                }
            },
        }
        container = {"us.stage.wages_usd": "98765.43"}
        lv = legal_value_from_dict(
            container, "us.stage.wages_usd",
            country="US", section="form_1040",
            provenance=provenance,
        )
        self.assertEqual(lv.stage_id, "US25-01-WAGE-TRANSLATION")
        self.assertEqual(lv.fingerprint, real_fp)
        self.assertEqual(lv.amount, Decimal("98765.43"))

    def test_legal_value_from_dict_rejects_missing_key(self) -> None:
        with self.assertRaises(KeyError):
            legal_value_from_dict(
                {"some_other_key": "0.00"}, "missing_line_key",
                country="DE", section="anlage_kap",
            )

    def test_legal_value_from_decimal_wraps_renderer_computed_amount(self) -> None:
        # The companion adapter for Decimals already extracted by a
        # renderer-side helper (e.g., a CSV row lookup keyed by step).
        lv = legal_value_from_decimal(
            Decimal("250.00"),
            country="US", section="tax_trace.niit",
            output_key="amount_usd",
        )
        self.assertIsInstance(lv, LegalValue)
        self.assertEqual(lv.amount, Decimal("250.00"))
        self.assertEqual(lv.stage_id, "renderer:US:tax_trace.niit")
        self.assertEqual(lv.output_key, "amount_usd")


class RuleGraphExecutionLegalOutputsTest(unittest.TestCase):
    def test_legal_outputs_wraps_each_output(self) -> None:
        stage_a = _stage("DE25-LV-A", inputs=("de.input",), outputs=("de.a",))
        stage_b = _stage("DE25-LV-B", inputs=("de.a",), outputs=("de.b",))

        def calc_a(facts: Mapping[str, Any]) -> Mapping[str, Any]:
            return {"de.a": facts["de.input"] + Decimal("1")}

        def calc_b(facts: Mapping[str, Any]) -> Mapping[str, Any]:
            return {"de.b": facts["de.a"] * Decimal("2")}

        rules = (
            LawRule(stage=stage_a, implementation_ref="test:calc_a", calculate=calc_a),
            LawRule(stage=stage_b, implementation_ref="test:calc_b", calculate=calc_b),
        )
        execution = execute_rule_graph(
            initial_facts={"de.input": Decimal("10")},
            rules=rules,
        )
        legal_outputs = execution.legal_outputs
        # Both rule outputs are wrapped.
        self.assertIn("de.a", legal_outputs)
        self.assertIn("de.b", legal_outputs)
        a = legal_outputs["de.a"]
        b = legal_outputs["de.b"]
        self.assertIsInstance(a, LegalValue)
        self.assertIsInstance(b, LegalValue)
        self.assertEqual(a.amount, Decimal("11"))
        self.assertEqual(a.stage_id, "DE25-LV-A")
        self.assertEqual(a.output_key, "de.a")
        self.assertEqual(b.amount, Decimal("22"))
        self.assertEqual(b.stage_id, "DE25-LV-B")
        self.assertEqual(b.output_key, "de.b")
        # Fingerprints come from the executor's StageResult chain (no
        # parallel third-domain re-hash).
        result_a = next(r for r in execution.stage_results if r.stage_id == "DE25-LV-A")
        result_b = next(r for r in execution.stage_results if r.stage_id == "DE25-LV-B")
        self.assertEqual(a.fingerprint, result_a.output_fingerprints["de.a"])
        self.assertEqual(b.fingerprint, result_b.output_fingerprints["de.b"])
        # Initial facts are NOT wrapped — only rule outputs are legal values.
        self.assertNotIn("de.input", legal_outputs)


class FinalLegalOutputProvenanceTest(unittest.TestCase):
    """Invariant I11: ``final-legal-output.json`` must persist the
    ``(stage_id, output_key, fingerprint)`` triple for every rule
    output — the audit packet then carries per-value provenance at the
    form-line boundary.

    Authority: § 32d Abs. 5 EStG; 26 U.S.C. § 901.
    """

    def test_provenance_section_present_with_triples(self) -> None:
        # Lazy import: this end-to-end test runs the demo workspace pipeline,
        # which imports germany / usa pipeline modules that pull in the
        # full year_2025 stack. Keeping the import inside the test method
        # avoids slowing down the lightweight LegalValue unit tests.
        import json
        from tax_pipeline.pipelines.y2025.final_legal_output import (
            write_final_legal_output_2025,
        )
        from tests.generated_demo import generated_demo_paths

        with generated_demo_paths() as paths:
            write_final_legal_output_2025(paths)
            final_output = json.loads(
                (paths.analysis_root / "final-legal-output.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertIn("_provenance", final_output)
        provenance = final_output["_provenance"]
        self.assertEqual(provenance.get("schema_version"), 1)
        rule_outputs = provenance.get("rule_outputs", {})
        # Both jurisdictions must populate per-rule provenance triples
        # for the demo workspace.
        self.assertIn("DE", rule_outputs)
        self.assertIn("US", rule_outputs)
        self.assertGreater(len(rule_outputs["DE"]), 0)
        self.assertGreater(len(rule_outputs["US"]), 0)
        # Every triple has exactly the (stage_id, output_key, fingerprint)
        # shape demanded by invariant I11.
        for country_rules in rule_outputs.values():
            for rule_id, per_output in country_rules.items():
                self.assertGreater(len(per_output), 0)
                for output_key, triple in per_output.items():
                    self.assertEqual(triple["stage_id"], rule_id)
                    self.assertEqual(triple["output_key"], output_key)
                    fingerprint = triple["fingerprint"]
                    self.assertIsInstance(fingerprint, str)
                    self.assertEqual(len(fingerprint), 64)  # sha256 hex
        # The flat form-line view exists per jurisdiction.
        form_lines = provenance.get("form_lines", {})
        self.assertIn("DE", form_lines)
        self.assertIn("US", form_lines)
        # Each form_lines entry is the same triple shape, keyed by output_key.
        for country_lines in form_lines.values():
            for output_key, triple in country_lines.items():
                self.assertEqual(triple["output_key"], output_key)
                self.assertEqual(len(triple["fingerprint"]), 64)


class FormEntryFormatCurrencyAstAuditTest(unittest.TestCase):
    """Invariant I11 / F-CQ-1: every legal-value-bearing form line must
    transit through ``legal_value_entry``.

    Before this fix the form-renderer modules wrote ``FormEntry(line,
    format_currency(form[<key>], unit), ...)`` which fed a bare scalar
    to the form-line boundary with no provenance. The
    ``_legal_value_form_line`` boundary helpers existed but were never
    invoked at any actual call site (F-CQ-1, HIGH). This AST audit
    catches the deletion / regression of the wiring: any
    ``format_currency(<subscript-or-name>)`` call that appears as a
    direct argument to a ``FormEntry(...)`` constructor is forbidden.
    Use ``legal_value_entry(line, legal_value_from_dict(...))`` (or
    ``legal_value_from_decimal(...)``) instead.

    Bare ``format_currency(...)`` calls *outside* a ``FormEntry``
    constructor (e.g., in narrative-summary f-strings produced by
    ``_write_index``) are allowed and continue to use the simple
    formatter — those are documentation strings, not form-line writes.
    """

    FORM_RENDERERS = (
        "tax_pipeline/forms/germany.py",
        "tax_pipeline/forms/usa.py",
    )

    def _project_root(self) -> "Path":  # type: ignore[name-defined]
        from pathlib import Path
        return Path(__file__).resolve().parents[2]

    def _form_entry_calls_with_format_currency(self, source: str) -> list[tuple[int, str]]:
        """Return ``(lineno, snippet)`` for every ``FormEntry(...)`` call
        whose ``value`` argument (positional[1] or kwarg ``value``)
        contains a ``format_currency(...)`` call expression.

        AST-based so it survives reformatting and string concatenation.
        """
        import ast

        violations: list[tuple[int, str]] = []
        tree = ast.parse(source)

        def contains_format_currency(node: ast.AST) -> bool:
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Call)
                    and isinstance(sub.func, ast.Name)
                    and sub.func.id == "format_currency"
                ):
                    return True
            return False

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "FormEntry":
                continue
            # FormEntry signature: (line, value, *, source="", notes="").
            value_node: ast.AST | None = None
            if len(node.args) >= 2:
                value_node = node.args[1]
            for kw in node.keywords:
                if kw.arg == "value":
                    value_node = kw.value
            if value_node is None:
                continue
            if contains_format_currency(value_node):
                snippet = ast.unparse(node) if hasattr(ast, "unparse") else "<FormEntry call>"
                violations.append((node.lineno, snippet))
        return violations

    def test_no_format_currency_inside_FormEntry_arg(self) -> None:
        root = self._project_root()
        for relpath in self.FORM_RENDERERS:
            path = root / relpath
            source = path.read_text(encoding="utf-8")
            violations = self._form_entry_calls_with_format_currency(source)
            if violations:
                detail = "\n".join(f"  {relpath}:{ln}: {snippet}" for ln, snippet in violations)
                self.fail(
                    "F-CQ-1 / I11 regression: FormEntry(...) call sites must transit "
                    "through legal_value_entry(legal_value_from_dict(...)) — bare "
                    "format_currency(...) inside a FormEntry value argument bypasses "
                    "the LegalValue form-renderer boundary and re-introduces the "
                    "dead-code defect F-CQ-1 fixed.\n"
                    f"Offending call sites:\n{detail}"
                )

    def test_legal_value_entry_is_invoked_at_form_line_sites(self) -> None:
        # Positive sanity check: each renderer must actually call
        # legal_value_entry SOMEWHERE — otherwise the wiring is just gone.
        import ast

        root = self._project_root()
        for relpath in self.FORM_RENDERERS:
            source = (root / relpath).read_text(encoding="utf-8")
            tree = ast.parse(source)
            invocations = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "legal_value_entry"
            ]
            self.assertGreater(
                len(invocations), 0,
                f"{relpath}: must invoke legal_value_entry(...) at least once "
                "to keep the I11 form-renderer boundary load-bearing.",
            )


if __name__ == "__main__":
    unittest.main()
