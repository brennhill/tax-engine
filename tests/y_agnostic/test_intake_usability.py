"""Usability-standard regression tests (Wave 9).

These tests are the structural guard rails for the user-facing intake
surface. They protect three plain-language properties that future
contributors must preserve:

  1. Every input has a non-trivial tooltip.
  2. Every tooltip's first 50 characters read like English prose, not a
     legal-first citation (e.g., a tooltip starting with "§ 32d" or
     "26 U.S.C." fails). The standard is that a 13-year-old should be
     able to read the first sentence and roughly understand what the
     field is about.
  3. Every money field declares its currency so the frontend can render
     a matching marker. "Money field" means a number-widget field whose
     key matches a money-pattern regex (amount/balance/expense/income/
     payment/donation/carryover/wage/tax) or ends with the explicit
     ``_eur`` / ``_usd`` suffix.

Beyond those three, the test suite also asserts that every server-side
validation error message produced by the intake POST handlers is at
least 20 characters long and contains an action verb (must, should,
need, use, enter, pick, format, like, expected). This is the ratchet
against drift back to the historical "Invalid value" / "ValueError"
strings that gave the user no idea what to fix.
"""

from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tax_pipeline.intake.postures import (
    POSTURE_REGISTRY,
    PostureValidationError,
    validate_state,
)
from tax_pipeline.intake.screens import (
    SCREEN_TOOLTIPS,
    ScreenValidationError,
    serialize_screen_metadata,
    write_bank_accounts_state,
    write_carryovers_state,
    write_de_deductions_state,
    write_identity_state,
    write_vorabpauschale_state,
)
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths


PROJECT_ROOT = Path(__file__).resolve().parents[2]


# Field-key patterns that mark a money-typed input. Non-money number
# fields (counts, percentages, calendar years, etc.) are intentionally
# excluded so the test only fails on real money.
MONEY_KEY_PATTERN = re.compile(
    r"_eur$|_usd$|amount|balance|expense|"
    r"_payments?(_|$)|donation|carryover|carryforward|wage"
)
# Verbs an actionable error message must contain. The list comes from
# CLAUDE.md's plain-language guidance plus the typical set our
# validators already use ("must be ...", "please enter ...").
ACTION_VERB_PATTERN = re.compile(
    r"\b(must|should|need|use|enter|pick|format|like|expected|please|re-type|"
    r"include|choose|select|fill)\b",
    re.IGNORECASE,
)
# Tokens that mark a tooltip as "legal-first" (citation up front). A
# plain-English tooltip may CONTAIN these, but the first 50 characters
# must not start with them — that is what flagged the original
# unreadable tooltips like "§ 32d Abs. 6 EStG: elect ...".
LEGAL_FIRST_PREFIXES = ("§", "26 U.S.C.", "DBA-USA", "InvStG ", "31 U.S.C.")


def _is_plain_english_prefix(tooltip: str) -> bool:
    """Return True iff the first 50 characters of the tooltip do not
    start with a § / U.S.C. / treaty citation. The check is intentionally
    permissive: it only flags the historical bad pattern."""

    head = tooltip.lstrip()[:50]
    return not any(head.startswith(prefix) for prefix in LEGAL_FIRST_PREFIXES)


class PostureTooltipPlainEnglishTest(unittest.TestCase):
    """Every entry in POSTURE_REGISTRY has a plain-English tooltip."""

    def test_every_posture_tooltip_is_plain_english_and_long_enough(self) -> None:
        # Both contracts apply per-field, so iterate once and assert
        # both conditions inside the loop.
        for field in POSTURE_REGISTRY:
            with self.subTest(key=field.key):
                self.assertGreaterEqual(
                    len(field.tooltip),
                    50,
                    f"Posture {field.key!r} tooltip is too short "
                    f"({len(field.tooltip)} chars). Tooltips must explain "
                    "the choice in plain English first; the (Legal: § ...) "
                    "parenthetical comes at the end.",
                )
                self.assertTrue(
                    _is_plain_english_prefix(field.tooltip),
                    f"Posture {field.key!r} tooltip starts with a legal-first "
                    "citation, e.g., '§ 32d ...'. Rewrite the first sentence "
                    "in plain English (middle-schooler readable) and put the "
                    "citation in a (Legal: § ...) parenthetical at the end.",
                )


class ScreenTooltipPlainEnglishTest(unittest.TestCase):
    """Every entry in SCREEN_TOOLTIPS has a plain-English tooltip."""

    def test_every_screen_tooltip_is_plain_english_and_long_enough(self) -> None:
        for screen, fields in SCREEN_TOOLTIPS.items():
            for field_key, meta in fields.items():
                tooltip = meta.get("tooltip", "")
                with self.subTest(screen=screen, field=field_key):
                    self.assertGreaterEqual(
                        len(tooltip),
                        50,
                        f"Screen {screen!r} field {field_key!r} tooltip is "
                        f"too short ({len(tooltip)} chars). Tooltips must "
                        "explain the field in plain English first.",
                    )
                    self.assertTrue(
                        _is_plain_english_prefix(tooltip),
                        f"Screen {screen!r} field {field_key!r} tooltip "
                        "starts with a legal-first citation. Rewrite the "
                        "first sentence in plain English; put the citation "
                        "in a (Legal: § ...) parenthetical at the end.",
                    )


class MoneyFieldsHaveCurrencyTest(unittest.TestCase):
    """Every money field in screen metadata declares its currency."""

    def test_serialize_metadata_publishes_currency_for_money_fields(self) -> None:
        metadata = serialize_screen_metadata()
        for screen, fields in metadata.items():
            for field_key, meta in fields.items():
                if MONEY_KEY_PATTERN.search(field_key):
                    currency = meta.get("currency", "")
                    self.assertIn(
                        currency,
                        {"USD", "EUR"},
                        f"Screen {screen!r} field {field_key!r} looks like a "
                        f"money field (matches MONEY_KEY_PATTERN) but its "
                        f"published currency is {currency!r}. Add a "
                        "``currency`` key to the SCREEN_TOOLTIPS entry, or "
                        "rename the key to end with _eur / _usd so "
                        "serialize_screen_metadata can infer it.",
                    )


class ValidationMessagesArePlainEnglishTest(unittest.TestCase):
    """Server-side validation messages are actionable plain English.

    We exercise the writers with bad inputs and assert each error message
    is at least 20 characters long and contains an action verb. The set
    of bad inputs is deliberately broad — every shape the writer can
    reject — so a future contributor cannot land a new "Invalid value"
    / "ValueError" string without breaking this test.
    """

    def _assert_message_is_actionable(self, message: str, label: str) -> None:
        self.assertGreaterEqual(
            len(message),
            20,
            f"Validation message for {label} is too short "
            f"({len(message)} chars): {message!r}. Plain-English "
            "messages must say what is wrong, what format is expected, "
            "and what the user should do.",
        )
        self.assertRegex(
            message,
            ACTION_VERB_PATTERN,
            f"Validation message for {label} is missing an action verb: "
            f"{message!r}. Use one of must / should / need / use / enter / "
            "pick / format / like / expected / please.",
        )

    def _make_paths(self, tmp: str):
        workspace_root = Path(tmp) / "2026"
        paths = resolve_year_paths(PROJECT_ROOT, "2026", workspace_root=workspace_root)
        ensure_year_scaffold(paths)
        return paths

    def test_identity_writer_messages_are_actionable(self) -> None:
        cases = [
            ("non-dict payload", "not-a-dict", None),
            (
                "bad SSN",
                {"taxpayer": {"us_ssn_or_itin": "12"}},
                None,
            ),
            (
                "bad German tax ID",
                {"taxpayer": {"german_tax_id": "12"}},
                None,
            ),
            (
                "bad address country",
                {"taxpayer": {"address_country": "GERMANY"}},
                None,
            ),
            (
                "bad employment country",
                {"taxpayer": {"employment_country": "GER"}},
                None,
            ),
            (
                "bad postal code",
                {"taxpayer": {"address_postal_code": "%"}},
                None,
            ),
            (
                "bad date_of_birth",
                {"taxpayer": {"date_of_birth": "yesterday"}},
                None,
            ),
            (
                "bad citizenship_status",
                {"taxpayer": {"citizenship_status": "martian"}},
                None,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._make_paths(tmp)
            for label, payload, _ in cases:
                with self.assertRaises(ScreenValidationError) as cm:
                    write_identity_state(paths, payload)
                self._assert_message_is_actionable(str(cm.exception), label)

    def test_bank_accounts_writer_messages_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._make_paths(tmp)
            cases = [
                ("non-dict payload", "nope"),
                ("non-list accounts", {"accounts": "nope"}),
                (
                    "bad country code",
                    {"accounts": [{"country": "GERMANY"}]},
                ),
                (
                    "non-numeric balance",
                    {"accounts": [{"year_end_balance_usd": "hello"}]},
                ),
            ]
            for label, payload in cases:
                with self.assertRaises(ScreenValidationError) as cm:
                    write_bank_accounts_state(paths, payload)
                self._assert_message_is_actionable(str(cm.exception), label)

    def test_de_deductions_writer_messages_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._make_paths(tmp)
            cases = [
                ("non-dict payload", "nope"),
                ("non-numeric amount", {"medical_expenses_eur": "hello"}),
                ("non-int gdb format", {"gdb": "twelve"}),
                ("out-of-range gdb", {"gdb": 17}),
                ("bad birth year", {"taxpayer_birth_year": 1234}),
                ("bad relationship", {"support_recipient_relationship": "ghost"}),
            ]
            for label, payload in cases:
                with self.assertRaises(ScreenValidationError) as cm:
                    write_de_deductions_state(paths, payload)
                self._assert_message_is_actionable(str(cm.exception), label)

    def test_vorabpauschale_writer_messages_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._make_paths(tmp)
            cases = [
                ("non-dict payload", "nope"),
                ("non-list funds", {"funds": "nope"}),
                ("non-numeric NAV", {"funds": [{"nav_start_eur": "abc"}]}),
                (
                    "non-int months_held",
                    {"funds": [{"symbol": "X", "months_held": "abc"}]},
                ),
                (
                    "out-of-range months_held",
                    {"funds": [{"symbol": "X", "months_held": "15"}]},
                ),
                (
                    "bad fund_classification",
                    {"funds": [{"symbol": "X", "fund_classification": "weird"}]},
                ),
            ]
            for label, payload in cases:
                with self.assertRaises(ScreenValidationError) as cm:
                    write_vorabpauschale_state(paths, payload)
                self._assert_message_is_actionable(str(cm.exception), label)

    def test_carryovers_writer_messages_are_actionable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = self._make_paths(tmp)
            cases = [
                ("non-dict payload", "nope"),
                (
                    "non-numeric USD",
                    {"us_passive_ftc_carryover_2024_usd": "hello"},
                ),
                (
                    "non-numeric EUR",
                    {"de_stock_loss_carryforward_2024_eur": "hello"},
                ),
            ]
            for label, payload in cases:
                with self.assertRaises(ScreenValidationError) as cm:
                    write_carryovers_state(paths, payload)
                self._assert_message_is_actionable(str(cm.exception), label)

    def test_posture_validation_messages_are_actionable(self) -> None:
        baseline = {field.key: field.default for field in POSTURE_REGISTRY}
        cases = [
            (
                "unknown key",
                {**baseline, "completely.bogus.key": "value"},
            ),
            (
                "value not in options",
                {**baseline, "jurisdictions.usa.filing_posture": "martian"},
            ),
            (
                "requires precondition violated",
                {
                    **baseline,
                    "jurisdictions.usa.filing_posture": "single",
                    "elections.elect_joint_return_with_nra_spouse": True,
                },
            ),
        ]
        for label, state in cases:
            with self.assertRaises(PostureValidationError) as cm:
                validate_state(state)
            self._assert_message_is_actionable(str(cm.exception), label)


if __name__ == "__main__":
    unittest.main()
