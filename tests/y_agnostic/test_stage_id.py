"""Tests for the typed ``StageId`` triple (Proposal 9).

These tests pin two contracts:

1. ``str(StageId(...))`` is byte-identical to every historical
   stage-id literal in the 2025 rule graph. Fingerprint payloads
   (invariant I6) include the string form verbatim, so any change to
   ``__str__`` is fingerprint-breaking.
2. ``StageId.parse(...)`` round-trips: ``str(StageId.parse(s)) == s``
   for every known stage-id shape.
"""

from __future__ import annotations

import unittest

from tax_pipeline.core.stage_id import StageId


# Frozen list of every stage-id literal currently emitted by the rule
# graph. Sourced from a grep of ``stage_id="…"`` across
# ``tax_pipeline/y2025/`` (germany_stages.py, us_stages.py,
# treaty_stages.py, bridge_stages.py, derivation/germany_derivations.py)
# on 2026-05-04. This list is the authoritative pre-P9 contract: no
# implementation may serialize any other shape, and renaming a stage
# requires updating this list deliberately.
PRE_P9_STAGE_IDS: tuple[str, ...] = (
    # DE25 — Germany 2025 law stages
    "DE25-00-FILING-POSTURE-GATE",
    "DE25-01-WAGE-INCOME",
    "DE25-02-WERBUNGSKOSTEN",
    "DE25-03-NET-EMPLOYMENT",
    "DE25-04-OTHER-22NR3",
    "DE25-05-RETIREMENT-SA",
    "DE25-06-HEALTH-VORSORGE-SA",
    "DE25-06B-SONDERAUSGABEN-PAUSCHBETRAG",
    "DE25-07-TAXABLE-INCOME",
    "DE25-08-INCOME-TAX-TARIFF",
    "DE25-09-ORDINARY-SOLI",
    "DE25-10-ORDINARY-CREDITS",
    "DE25-13-CAPITAL-RAW-BUCKETS",
    "DE25-13F-VORABPAUSCHALE",
    "DE25-14-FUND-TEILFREISTELLUNG",
    "DE25-15-SECTION-20-6-NETTING",
    "DE25-16-SECTION-20-9-SAVER",
    "DE25-17-SECTION-32D1-GROSS-TAX",
    "DE25-18-SECTION-32D5-FTC",
    "DE25-19-CAPITAL-SOLI",
    "DE25-20-TREATY-CHECK",
    "DE25-21-FINAL-CAPITAL-TAX",
    "DE25-22-FINAL-REFUND",
    "DE25-ALTERSENTLASTUNGSBETRAG",
    "DE25-ARBEITSZIMMER",
    "DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN",
    "DE25-BEHINDERUNG-PAUSCHBETRAG",
    "DE25-CHILDREN-CREDITS",
    "DE25-CHILDREN-DISABILITY-PAUSCHBETRAG",
    "DE25-FORM-KAP-PROJECTION",
    "DE25-GUENSTIGERPRUEFUNG-SHADOW",
    "DE25-SPENDENABZUG",
    "DE25-UNTERHALTSLEISTUNGEN",
    # US25 — United States 2025 law stages
    "US25-00-FILING-POSITION",
    "US25-01-WAGE-TRANSLATION",
    "US25-02-INCOME-SIDE-INPUTS",
    "US25-03-CAPITAL-BUCKETS",
    "US25-04-SECTION-1256",
    "US25-05-CAPITAL-LOSS-LINE-7A",
    "US25-06-PREFERENTIAL-CAPITAL-BASE",
    "US25-07-AGI",
    "US25-08-TAXABLE-INCOME",
    "US25-09-REGULAR-TAX",
    "US25-10-FORM-1116-PREFERENTIAL-GATE",
    "US25-11-FTC-DENOMINATOR",
    "US25-12-FTC-LIMITATIONS",
    "US25-13-FOREIGN-TAX-AVAILABLE",
    "US25-14-BASELINE-ALLOWED-FTC",
    "US25-15-TREATY-US-SOURCE-DIVIDENDS",
    "US25-16-TREATY-AVERAGE-TAX-FLOOR",
    "US25-17-TREATY-GERMAN-RESIDUAL-CAP",
    "US25-18-TREATY-ADDITIONAL-FTC",
    "US25-19-ALLOWED-FTC",
    "US25-19A-ALLOWED-FTC-AFTER-RESOURCING",
    "US25-20-NIIT",
    "US25-21-PAYMENTS",
    "US25-ADDITIONAL-MEDICARE",
    "US25-AMT-AMTI",
    "US25-AMT-FTC-AND-COMPARE",
    "US25-AMT-TENTATIVE",
    "US25-CTC-AND-ODC",
    "US25-FATCA-FBAR-DETERMINATION",
    "US25-FEIE",
    "US25-SE-TAX",
    # TREATY25 — DBA-USA treaty stages
    "TREATY25-15-US-SOURCE-DIVIDENDS",
    "TREATY25-16-AVERAGE-TAX-FLOOR",
    "TREATY25-17-GERMAN-RESIDUAL-CAP",
    "TREATY25-18-ADDITIONAL-FTC",
    "TREATY25-LOB-QUALIFICATION",
    # BRIDGE25 — cross-jurisdiction reconciliation
    "BRIDGE25-FOREIGN-TAX-RECONCILIATION",
    # DERIVE-DE25 — Pipeline-1 derivation stages (Germany)
    "DERIVE-DE25-13A-PER-SYMBOL-SALE-AGGREGATION",
    "DERIVE-DE25-13B-1099-BOX-FILTERING",
    "DERIVE-DE25-13C-PER-SYMBOL-BANK-CERTIFICATE-BUCKETS",
    "DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION",
    "DERIVE-DE25-13E-FOREIGN-TAX-INDEXING",
    "DERIVE-DE25-13F-VORABPAUSCHALE-INPUTS",
    "DERIVE-DE25-CHILDREN",
    "DERIVE-DE25-FUND-CLASSIFICATION",
)


class StageIdParseRoundTripTest(unittest.TestCase):
    def test_parse_str_roundtrip_byte_identical_for_every_pre_p9_id(self) -> None:
        """``str(StageId.parse(raw)) == raw`` for every historical literal.

        This is the contract that protects fingerprint stability across the
        P9 migration: the serialized form must be byte-identical to today's
        string IDs because ``stable_fingerprint`` payloads include the
        string verbatim (invariant I6).
        """
        for raw in PRE_P9_STAGE_IDS:
            with self.subTest(stage_id=raw):
                parsed = StageId.parse(raw)
                self.assertEqual(str(parsed), raw)


class StageIdParsePrefixTest(unittest.TestCase):
    def test_parse_extracts_country_prefix_for_each_known_shape(self) -> None:
        # One representative literal per supported country prefix. The
        # ``DERIVE-DE`` / ``DERIVE-USA`` rows pin the longest-match rule:
        # the parser must beat them before the bare ``DE`` / ``US``
        # alternation, otherwise ``DERIVE-DE25-13D-...`` would be misread
        # as country=``DE``, sequence=``RIVE-DE25-...``.
        cases = (
            ("DE25-13F-VORABPAUSCHALE", "DE", "25", "13F-VORABPAUSCHALE"),
            ("US25-19A-ALLOWED-FTC-AFTER-RESOURCING", "US", "25", "19A-ALLOWED-FTC-AFTER-RESOURCING"),
            ("TREATY25-17-GERMAN-RESIDUAL-CAP", "TREATY", "25", "17-GERMAN-RESIDUAL-CAP"),
            ("BRIDGE25-FOREIGN-TAX-RECONCILIATION", "BRIDGE", "25", "FOREIGN-TAX-RECONCILIATION"),
            ("DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION", "DERIVE-DE", "25", "13D-SOURCE-COUNTRY-CLASSIFICATION"),
            ("DERIVE-USA25-FOO-BAR", "DERIVE-USA", "25", "FOO-BAR"),
        )
        for raw, country, year, sequence in cases:
            with self.subTest(raw=raw):
                sid = StageId.parse(raw)
                self.assertEqual(sid.country, country)
                self.assertEqual(sid.year_short, year)
                self.assertEqual(sid.sequence, sequence)


class StageIdParseRejectsTest(unittest.TestCase):
    def test_parse_rejects_invalid_shapes(self) -> None:
        # One representative invalid input per validation branch.
        invalid_inputs = [
            "UK25-01-FOREIGN-PENSION",      # unknown country prefix
            "DE25-13f-vorabpauschale",      # lowercase sequence
            "DE25-",                         # empty sequence
            "DE-13F-VORABPAUSCHALE",         # missing year
            "DE2025-13F-VORABPAUSCHALE",     # three-digit year
        ]
        for raw in invalid_inputs:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    StageId.parse(raw)

    def test_parse_rejects_non_string_or_blank(self) -> None:
        for raw in (None, "   "):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "non-empty string"):
                    StageId.parse(raw)  # type: ignore[arg-type]


class StageIdConstructorTest(unittest.TestCase):
    def test_constructor_rejects_unknown_country(self) -> None:
        with self.assertRaisesRegex(ValueError, "StageId.country must be one of"):
            StageId(country="UK", year_short="25", sequence="01-FOO")

    def test_constructor_rejects_invalid_year_or_sequence(self) -> None:
        cases = [
            ("DE", "5", "01-FOO"),       # one-digit year
            ("DE", "25", "13f-vorab"),   # lowercase sequence
            ("DE", "25", ""),             # empty sequence
        ]
        for country, year, seq in cases:
            with self.subTest(country=country, year=year, seq=seq):
                with self.assertRaises(ValueError):
                    StageId(country=country, year_short=year, sequence=seq)


class StageIdCoerceTest(unittest.TestCase):
    def test_coerce_passes_through_stage_id(self) -> None:
        sid = StageId(country="DE", year_short="25", sequence="13F-VORABPAUSCHALE")
        self.assertIs(StageId.coerce(sid), sid)

    def test_coerce_parses_strings(self) -> None:
        sid = StageId.coerce("DE25-13F-VORABPAUSCHALE")
        self.assertIsInstance(sid, StageId)
        self.assertEqual(str(sid), "DE25-13F-VORABPAUSCHALE")


class StageIdHashableFrozenTest(unittest.TestCase):
    def test_stage_id_is_hashable_and_frozen(self) -> None:
        """``LawStage`` is a frozen dataclass; ``StageId`` must be too so a
        ``LawStage`` containing a ``StageId`` stays hashable / equality-stable.
        """
        a = StageId(country="DE", year_short="25", sequence="13F-VORABPAUSCHALE")
        b = StageId(country="DE", year_short="25", sequence="13F-VORABPAUSCHALE")
        c = StageId(country="DE", year_short="25", sequence="14-FUND-TEILFREISTELLUNG")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(hash(a), hash(b))
        # Frozen — assignment raises.
        with self.assertRaises(Exception):  # FrozenInstanceError is a subclass of AttributeError
            a.country = "US"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
