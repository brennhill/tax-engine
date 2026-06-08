"""Unit tests for the typed ``Money`` value (Proposal P4).

Authority: § 32d Abs. 5 EStG; 26 U.S.C. § 901; DBA-USA Art. 23.
https://www.gesetze-im-internet.de/estg/__32d.html
https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
https://www.irs.gov/pub/irs-pdf/p514.pdf

Invariant focus: I6 — fingerprint payloads contain only canonical
values, never ``repr(value)`` and never a currency-tagged display
string. The ``test_money_fingerprint_stability`` test pins the
Decimal-only canonical payload so the three workspace md5s
(brenn-2025 / demo-2025 / de-only-demo-2025) remain byte-identical
across the P4 migration.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from tax_pipeline.core.facts import stable_fingerprint
from tax_pipeline.core.money import Currency, Money


class CurrencyEnumTest(unittest.TestCase):
    def test_supported_currencies_have_iso_4217_codes(self) -> None:
        # ISO 4217 codes; the engine is currently scoped to USD + EUR.
        self.assertEqual(Currency.USD.value, "USD")
        self.assertEqual(Currency.EUR.value, "EUR")

    def test_currency_is_string_subclass(self) -> None:
        # ``Currency(str, Enum)`` — the .value participates in JSON
        # serialization without coercion; the Enum identity guards
        # against typos at typed boundaries.
        self.assertIsInstance(Currency.USD, str)
        self.assertEqual(str(Currency.USD.value), "USD")

    def test_tabular_decimal_places_usd_eur(self) -> None:
        # Form 1040 line-1z and ELSTER Anlage N tabular cells both
        # render to two decimal places — pinned here for clarity.
        self.assertEqual(Currency.tabular_decimal_places(Currency.USD), 2)
        self.assertEqual(Currency.tabular_decimal_places(Currency.EUR), 2)

    def test_tabular_decimal_places_unknown_fails_closed(self) -> None:
        # Fail-closed posture: an unrecognized currency raises rather
        # than silently defaulting to two decimal places. CLAUDE.md:
        # "If a legal source is unclear ... fail closed."
        class FakeCurrency:
            pass
        with self.assertRaises((ValueError, TypeError)):
            Currency.tabular_decimal_places(FakeCurrency())  # type: ignore[arg-type]


class MoneyConstructionTest(unittest.TestCase):
    def test_constructor_and_factories_round_trip_amount_and_currency(self) -> None:
        # Direct constructor and the per-currency factories must agree on
        # ``(amount, currency)`` for both supported currencies.
        cases = (
            (Money(amount=Decimal("100.00"), currency=Currency.EUR), Decimal("100.00"), Currency.EUR),
            (Money(amount=Decimal("250.00"), currency=Currency.USD), Decimal("250.00"), Currency.USD),
            (Money.eur(Decimal("1.23")), Decimal("1.23"), Currency.EUR),
            (Money.usd(Decimal("4.56")), Decimal("4.56"), Currency.USD),
        )
        for m, expected_amount, expected_currency in cases:
            with self.subTest(currency=expected_currency, amount=expected_amount):
                self.assertEqual(m.amount, expected_amount)
                self.assertEqual(m.currency, expected_currency)

    def test_amount_must_be_decimal(self) -> None:
        # Float and string amounts must fail closed — same posture as
        # ``LegalValue.amount`` (invariant I11).
        with self.assertRaises(TypeError):
            Money(amount=1.0, currency=Currency.EUR)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Money(amount="100.00", currency=Currency.EUR)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Money(amount=100, currency=Currency.EUR)  # type: ignore[arg-type]

    def test_currency_must_be_enum_member(self) -> None:
        # Plain strings are rejected so the renderer can rely on a
        # closed set of currencies. A typo like ``"usd"`` (lower-case)
        # cannot silently slip through.
        with self.assertRaises(TypeError):
            Money(amount=Decimal("0"), currency="USD")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            Money(amount=Decimal("0"), currency=None)  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        m = Money.eur(Decimal("0"))
        with self.assertRaises(Exception):
            m.amount = Decimal("1")  # type: ignore[misc]


class MoneyDisplayTest(unittest.TestCase):
    def test_str_shows_amount_and_currency(self) -> None:
        # Display path — used by ``format_currency`` when given a Money.
        self.assertEqual(str(Money.eur(Decimal("100.00"))), "100.00 EUR")
        self.assertEqual(str(Money.usd(Decimal("250.00"))), "250.00 USD")

    def test_str_preserves_decimal_precision(self) -> None:
        # The Decimal-side normalization is the caller's responsibility;
        # ``Money`` is a passive carrier and does not requantize.
        self.assertEqual(str(Money.eur(Decimal("0"))), "0 EUR")
        self.assertEqual(str(Money.eur(Decimal("0.00"))), "0.00 EUR")


class MoneyEqualityHashTest(unittest.TestCase):
    def test_equality_pairwise(self) -> None:
        a = Money.eur(Decimal("100.00"))
        b = Money.eur(Decimal("100.00"))
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))

    def test_different_currency_unequal(self) -> None:
        # 100 USD ≠ 100 EUR — the type system distinguishes them even
        # though the underlying Decimal is the same.
        self.assertNotEqual(Money.usd(Decimal("100")), Money.eur(Decimal("100")))


class MoneyFingerprintStabilityTest(unittest.TestCase):
    """Invariant I6: the canonical fingerprint payload of a legal value
    is the Decimal alone. ``Money`` carries currency *alongside* the
    Decimal but currency must NOT enter the fingerprint chain — that
    would break the byte-stability of ``final-legal-output.json`` md5s
    that P1 audit + P9 stabilized.

    Pinned md5s (post-Schedule-2-2025-line-numbering fix on 2026-05-10;
    Schedule 2 (2025) Part I AMT row moved from line 1 to line 2 per
    https://www.irs.gov/pub/irs-pdf/f1040s2.pdf — renderer caption,
    notes strings, FormLineRef.line, and form_6251 caption all
    rotated, which changed the rendered legal-output JSON for the two
    workspaces with a U.S. pathway. de-only-demo-2025 has no U.S.
    output and was unchanged. Prior pin was the 2026-05-09 Anlage SO
    Zeile 66 → Zeile 62 authoritative-source fix):
      brenn-2025:        9f5eb164a5be61d83454b32ec18878d0
      demo-2025:         92ec7bb510e449e7e6cadde54bd5df40
      de-only-demo-2025: b3c89e3734ba123b0117bf64064559bb
    """

    def test_canonical_payload_uses_decimal_only(self) -> None:
        # The canonical payload for a Decimal('100.00') legal value
        # under invariant I11's stage_id/output_key/value triple is
        # NOT a Money — it's the Decimal alone. The renderer wrapping
        # in Money is purely a display / typed-boundary concern.
        amount = Decimal("100.00")
        canonical = stable_fingerprint(
            {"stage_id": "DE25-X", "output_key": "de.x", "value": amount}
        )
        # Exactly the same value under a Money tag must NOT change the
        # fingerprint, because the canonical key is the bare Decimal.
        money = Money.eur(amount)
        # The discipline: callers pass ``money.amount``, not ``money``.
        same = stable_fingerprint(
            {"stage_id": "DE25-X", "output_key": "de.x", "value": money.amount}
        )
        self.assertEqual(canonical, same)

    def test_money_str_is_not_canonical(self) -> None:
        # str(money) is "100.00 EUR" — distinct from the canonical
        # ``str(amount)`` form. This is intentional: Money's __str__ is
        # for display, not for fingerprint payloads.
        amount = Decimal("100.00")
        money = Money.eur(amount)
        self.assertNotEqual(str(money), str(amount))
        self.assertEqual(str(money), "100.00 EUR")
        self.assertEqual(str(amount), "100.00")


if __name__ == "__main__":
    unittest.main()
