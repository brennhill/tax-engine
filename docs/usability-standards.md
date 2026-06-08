# Usability Standards

The intake wizard is the only surface non-lawyers ever touch. The
user-facing name of that wizard is the **Tax Engine** &mdash; a neutral
product brand for a 2025 Germany / U.S. cross-border tax pipeline.
Tooltip wording, validation copy, currency labeling, and every other
usability rule below are written in plain English so a stressed filer
can read each tooltip and finish their return without giving up. The
engine, narratives, and `final-legal-output.json` keep their neutral
professional voice.

These standards exist so a stressed-out filer who has never read the
Internal Revenue Code can sit down, read each tooltip, and finish
their return without giving up. Every change to the intake forms
(posture registry, screen registry, server messages, frontend
templates) must hold the lines below.

The regression tests in `tests/y_agnostic/test_intake_usability.py` are the
ratchet — they run on every PR and fail when any of these standards
slip.

## 1. Tooltip standard

Every input field has a tooltip. The tooltip must:

1. Lead with **1-3 sentences of plain English** that a 13-year-old
   can read on the first pass. The first sentence answers "what
   does this field do?" without using any tax-code citation.
2. Mention the **consequence**: what does the choice change, what
   does it foreclose, and when does it matter?
3. End with a `(Legal: § X)` parenthetical for the lawyer-curious
   and the auditor.

The first 50 characters must not begin with `§`, `26 U.S.C.`,
`DBA-USA`, `InvStG `, or `31 U.S.C.`. That is the "legal-first" tell
the regression test catches.

### Bad / good examples

Bad — legal-first, no plain-English explanation:

> § 32d Abs. 6 EStG: elect § 32a tariff for capital income if it
> produces lower total tax than § 32d Abs. 1 25 % flat.

Good — plain English first, citation parenthetical at the end:

> Normally Germany taxes your investment income at a flat 25%. If
> your other income is low enough, you can ask Germany to use the
> regular income-tax brackets on it instead, which is sometimes
> cheaper. We will show you whether the swap would have saved you
> money, but the calculator does not yet apply the swap automatically.
> (Legal: § 32d Abs. 6 EStG)

Bad — abbreviation-first:

> FTC carryover from 2024.

Good:

> Type the U.S. dollar amount of unused foreign tax credit you
> brought forward from your 2024 U.S. return in the 'passive' basket
> (mostly investment income). The IRS lets you carry unused credit
> forward for up to 10 years. Look at your 2024 Form 1116 line 10.
> (Legal: 26 U.S.C. § 904(c))

### Contributor checklist for a new tooltip

- [ ] First sentence answers "what does this field do?"
- [ ] Second sentence (if needed) explains the consequence: what
      does it change, what does it foreclose?
- [ ] Length is at least 50 characters.
- [ ] Citation lives only in a `(Legal: § ...)` parenthetical at
      the end.
- [ ] No bare `§ ...:` at the start of the tooltip.
- [ ] Run `uv run pytest tests/y_agnostic/test_intake_usability.py -q`.

## 2. Validation standard

Every field is validated server-side before it touches disk. We never
silently accept an invalid value. Every validation error message
must:

1. Say **what was wrong** ("U.S. SSN must be 9 digits, you entered
   12345").
2. State the **format expected** ("like 123-45-6789").
3. Tell the user **what to do** ("Please re-type the 9-digit number
   from your Social Security card").

Every message is at least 20 characters and contains an action verb
(`must`, `should`, `need`, `use`, `enter`, `pick`, `format`, `like`,
`expected`, `please`, `re-type`, `include`, `choose`, `select`,
`fill`). The regression test enforces both.

### Bad / good examples

Bad:

> ValueError

Good:

> Bank account row 1: year_end_balance_usd must be a number in U.S.
> dollars, like 1234.56. You entered 'hello'. Please enter the
> balance in USD without currency symbols or thousands separators.

Bad:

> Invalid value.

Good:

> gdb (Grad der Behinderung): must be 0 (no rating) or a multiple
> of 10 between 20 and 100, like 30, 50, or 100. You entered 17.
> Please use the percentage from your Schwerbehindertenausweis.
> (Legal: § 33b Abs. 3 EStG)

### Where validation lives

- **Posture-registry validators** in
  `tax_pipeline/intake/postures.py` (boolean coercion, option
  enum check, `requires` precondition).
- **Screen-writer validators** in
  `tax_pipeline/intake/screens.py` (one per screen).
- **HTTP-layer validators** in `tax_pipeline/intake/server.py`
  (missing `year`, missing `state`, oversized body, malformed
  base64, etc.).

## 3. Currency labeling standard

Every money input is labeled in three places at once:

1. **Field label** carries the currency in parentheses, e.g.
   `Year-end balance (USD)` or `Medical expenses (EUR)`.
2. **Inline visual marker** sits next to the input: a `$` or `€`
   prefix glyph and a small `USD` / `EUR` pill on the right.
3. **Tooltip** mentions the currency in prose ("Type the U.S.
   dollar amount ..." / "Type the euro amount ...").

The frontend gets the currency from the screen-metadata API:
`serialize_screen_metadata` publishes a `currency` value of `"USD"`
or `"EUR"` for every field whose key ends in `_usd` or `_eur`. The
regression test checks every field whose key matches the money-field
regex (`_eur$|_usd$|amount|balance|expense|payment|donation|`
`carryover|carryforward|wage`) — if a field is money but has no
currency, the test fails and the contributor must either add a
`currency` key to the SCREEN_TOOLTIPS entry or rename the key to end
in `_eur` / `_usd`.

### Bad / good examples

Bad:

> Year-end balance: [        ]

Good:

> Year-end balance (USD)
> $ [        ] USD

### Contributor checklist for a new money field

- [ ] Key ends in `_eur` or `_usd`, OR explicitly carries
      `"currency": "EUR"` / `"currency": "USD"` in
      `SCREEN_TOOLTIPS`.
- [ ] Frontend label includes `(USD)` / `(EUR)`.
- [ ] Tooltip mentions "U.S. dollar amount" or "euro amount".
- [ ] Run `uv run pytest tests/y_agnostic/test_intake_usability.py -q`.

## 4. Plain-language guide

The middle-schooler test: **would a 13-year-old understand the first
sentence without context?** If you have to use a § citation, an
abbreviation, or a Latin-derived noun in the first sentence, you
have failed. Move that detail to a later sentence or to the (Legal:
...) parenthetical.

Five before/after pairs from the actual codebase:

1. **Filing posture (DE).**

   Before: *Determines § 32a tariff brackets (Splittingtarif if
   married_joint), § 26b joint-assessment prerequisites, and
   Sparer-Pauschbetrag halving for single.*

   After: *Pick how Germany should treat you for the year: single,
   married filing together, or married filing on your own. Married
   filing together (Splittingtarif) usually saves money for couples
   with uneven incomes.*

2. **§ 6013(g) NRA spouse election.**

   Before: *26 U.S.C. § 6013(g) election to treat an NRA spouse as
   a U.S. resident for the entire tax year, bringing the spouse's
   worldwide income into the U.S. tax base.*

   After: *Check this if your spouse is not a U.S. citizen or
   green-card holder, but you want to file a joint U.S. tax return
   with them. Doing this means your spouse's worldwide income gets
   added to your U.S. return.*

3. **Charitable donations.**

   Before: *§ 10b Abs. 1 Satz 1 Nr. 1 EStG: deductible as
   Sonderausgabe up to 20 % of the Gesamtbetrag der Einkünfte.*

   After: *Type the euros you gave to recognized charities or
   religious bodies during the year. Germany lets you deduct up to
   20% of your total income.*

4. **Vorabpauschale months held.**

   Before: *Full months of ownership during the calendar year
   (0..12). Vorabpauschale prorates per InvStG § 18 Abs. 2.*

   After: *Type how many full months you owned the fund during the
   year, 0 through 12. If you bought it mid-year and held it through
   December, count only full months you had it.*

5. **U.S. SSN error message.**

   Before: *us_ssn_or_itin must be 9 digits (got '12345').*

   After: *taxpayer: U.S. SSN or ITIN must be exactly 9 digits, like
   123-45-6789. You entered '12345'. Please re-type the 9-digit
   number from your Social Security card or ITIN letter.*

## 5. Test requirements

A new screen or new field is not landed until:

1. The tooltip passes
   `tests/y_agnostic/test_intake_usability.py::*TooltipPlainEnglishTest`.
2. Money fields pass
   `tests/y_agnostic/test_intake_usability.py::MoneyFieldsHaveCurrencyTest`.
3. Validators pass
   `tests/y_agnostic/test_intake_usability.py::ValidationMessagesArePlainEnglishTest`.
4. The full intake suite still passes:
   `uv run pytest tests/y_agnostic/test_intake_*.py -q`.

If a contributor fights a test instead of fixing the tooltip /
message, that is a sign the standard is doing its job. Talk to a
maintainer rather than disabling the test.

## 6. Maintenance

Adding a new posture or field is a four-step exercise:

1. Add the entry to `POSTURE_REGISTRY` (postures.py) or
   `SCREEN_TOOLTIPS` (screens.py). The tooltip leads with plain
   English and ends with a `(Legal: § ...)` parenthetical.
2. If the field is a money field, end its key with `_eur` or
   `_usd` so `serialize_screen_metadata` infers the currency.
3. Wire up validation. The error message follows the validation
   standard (what / format / what to do, plus an action verb).
4. Run `uv run pytest tests/y_agnostic/test_intake_usability.py -q` and
   `uv run pytest tests/y_agnostic/test_intake_*.py -q`. Both must be green
   before you commit.

The regression tests will catch most violations automatically. The
ones they cannot catch (vocabulary, sentence rhythm, "would a
13-year-old understand?") are why we write these standards down.
