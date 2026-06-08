"""Typed currency value (Proposal P4 from the architecture review).

Today, currency is a free-text string label. ``format_currency(value,
unit="EUR")`` carries ``unit`` as a string at 161 call sites. The
``LegalValue.amount`` field is a bare ``Decimal`` with no currency tag —
currency can only be inferred at the renderer boundary from a literal
``unit=`` argument. This module introduces a typed ``Money(amount,
currency)`` so currency becomes a structural property of the value, not
a render-time annotation.

Authority for the audit-trail discipline:
- § 32d Abs. 5 EStG (per-Posten foreign tax credit) — requires a
  verifiable per-line foreign-tax basis, denominated in EUR.
  https://www.gesetze-im-internet.de/estg/__32d.html
- 26 U.S.C. § 901 (foreign tax credit) — requires a verifiable
  USD-denominated foreign-tax-paid figure as the credit basis.
  https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title26-section901&num=0&edition=prelim
- DBA-USA Art. 23 / IRS Pub. 514 — cross-border resourcing depends on
  consistent EUR↔USD framing of source-state and residence-state
  amounts.
  https://www.irs.gov/pub/irs-pdf/p514.pdf

Fingerprint stability (CLAUDE.md invariant I6) is paramount: the
canonical fingerprint payload of a legal value is the value's
``Decimal`` only — currency travels alongside but does NOT enter
``LegalValue.fingerprint`` or any ``stable_fingerprint`` payload.
``Money.__str__`` returns ``"<amount> <currency>"`` for *display*,
which is intentionally distinct from the canonical fingerprint
serialization (just ``str(amount)``). See P4 review §1 and the
``test_money_fingerprint_stability`` regression for the byte-stability
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Currency(str, Enum):
    """Currencies the engine knows how to denominate.

    The two currencies that exist as legal-value units in the 2025
    Germany / U.S. cross-border engine are EUR and USD. Future
    expansion (GBP for UK, CHF for Switzerland, VND for Vietnam, INR
    for India) lands here when the corresponding country's law modules
    land. Each future currency will need its own
    :func:`Currency.tabular_decimal_places` row because rounding
    conventions differ (VND has 0 decimal places; CHF rounds to 0.05
    on certain form lines; INR is whole-rupee for most form lines).
    """

    USD = "USD"
    EUR = "EUR"

    @classmethod
    def tabular_decimal_places(cls, currency: "Currency") -> int:
        """Number of decimal places a tabular form-line render uses.

        For the 2025 engine both supported currencies render with two
        decimal places (USD per IRS Form 1040 instructions, EUR per
        ELSTER tabular fields). Future currencies (JPY, VND) will
        return ``0``; CHF will keep ``2`` plus a separate
        rounding-step marker for the 0.05 lines.
        """
        if currency in (cls.USD, cls.EUR):
            return 2
        raise ValueError(f"Unknown currency for tabular rendering: {currency!r}")


@dataclass(frozen=True)
class Money:
    """A currency-tagged Decimal value at the form-line boundary.

    ``Money`` is the typed companion to :class:`LegalValue` for the
    P4 migration: legal values that cross the rule-graph → form-renderer
    boundary travel with their currency tag attached, so the renderer
    no longer has to infer currency from a string ``unit=`` argument.

    Fingerprint discipline (invariant I6):
        ``str(money) == "<amount> <currency>"`` is for *display only*
        and intentionally differs from the canonical fingerprint
        payload, which uses ``str(amount)`` alone. ``Money`` instances
        must NOT be passed to ``stable_fingerprint`` — pass
        ``money.amount`` instead. The
        ``test_money_fingerprint_stability`` regression asserts the
        Decimal-only payload remains byte-identical pre / post P4 so
        the three workspace md5s
        (brenn-2025: 9f5eb164a5be61d83454b32ec18878d0,
        demo-2025: 92ec7bb510e449e7e6cadde54bd5df40,
        de-only-demo-2025: b3c89e3734ba123b0117bf64064559bb;
        rotated 2026-05-10 from the prior pinned set as part of the
        Schedule 2 (2025) Part I line-numbering fix — AMT row moved
        from line 1 to line 2 (IRS-VERIFIED 2026-05-10 against
        https://www.irs.gov/pub/irs-pdf/f1040s2.pdf), with corresponding
        renderer caption / FormLineRef.line / form_6251 caption
        updates. de-only-demo-2025 has no U.S. side and so was
        unchanged by the U.S. Schedule 2 fix.)
        do not regress.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                "Money.amount must be a Decimal; "
                f"got {type(self.amount).__qualname__}"
            )
        if not isinstance(self.currency, Currency):
            raise TypeError(
                "Money.currency must be a Currency enum member; "
                f"got {type(self.currency).__qualname__}"
            )

    def __str__(self) -> str:
        # Display-only. Do not pass a ``Money`` to ``stable_fingerprint``
        # — the canonical fingerprint payload remains the Decimal alone.
        return f"{self.amount} {self.currency.value}"

    @classmethod
    def usd(cls, amount: Decimal) -> "Money":
        return cls(amount, Currency.USD)

    @classmethod
    def eur(cls, amount: Decimal) -> "Money":
        return cls(amount, Currency.EUR)


__all__ = [
    "Currency",
    "Money",
]
