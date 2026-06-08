"""TREATY25-LOB-QUALIFICATION — DBA-USA Art. 28 LOB gate (Workstream 4).

Authority:
- DBA-USA (Germany–United States Convention for the Avoidance of Double
  Taxation, Income and Capital, signed 1989, amended 2006 Protocol),
  Article 28 (Limitation on Benefits).
- Bilingual treaty text: https://www.irs.gov/pub/irs-trty/germany.pdf
- IRS Form 8833 — treaty-based return position disclosure under § 6114:
  https://www.irs.gov/forms-pubs/about-form-8833

Workstream 4 of the 2026-05-01 USA legal-flow review fills the LOB
qualification gap. Previously the treaty resourcing rule graph
performed the Pub. 514 worksheet whenever ``use_treaty_resourcing``
was True; there was no Art. 28 gate. Now the head of the treaty graph
is ``TREATY25-LOB-QUALIFICATION``, which validates the
``USTreatyInputs2025.lob_qualification_category`` against the closed
enum ``LOB_QUALIFICATION_CATEGORIES`` and fails closed if the taxpayer
claims re-sourcing without qualifying.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from tax_pipeline.y2025.treaty_law import (
    DBA_USA_ART_28_URL,
    LOB_QUALIFICATION_CATEGORIES,
)
from tax_pipeline.y2025.treaty_rules import (
    treaty25_lob_qualification,
    treaty_law_rules_2025,
)
from tax_pipeline.y2025.treaty_stages import treaty_law_stages_2025
from tax_pipeline.y2025.us_law import USTreatyInputs2025

D = Decimal


def _treaty_inputs(category: str = "qualified_resident", *, use_resourcing: bool = True) -> USTreatyInputs2025:
    return USTreatyInputs2025(
        use_treaty_resourcing=use_resourcing,
        us_source_direct_equity_dividends_usd=D("0"),
        us_source_equity_fund_dividends_usd=D("0"),
        us_source_non_equity_fund_dividends_usd=D("0"),
        lob_qualification_category=category,
    )


class LOBQualificationCategoriesTest(unittest.TestCase):
    """The closed-enum LOB categories cover the five Art. 28 paragraphs
    plus an explicit ``not_qualified`` opt-out."""

    def test_categories_cover_five_art_28_paragraphs(self) -> None:
        self.assertEqual(
            set(LOB_QUALIFICATION_CATEGORIES),
            {
                "publicly_traded",
                "qualified_resident",
                "active_business",
                "derivative_benefits",
                "competent_authority",
                "not_qualified",
            },
        )

    def test_dba_usa_art_28_url_centralized(self) -> None:
        # Every Art. 28 callsite references DBA_USA_ART_28_URL.
        self.assertTrue(DBA_USA_ART_28_URL.endswith("germany.pdf"))


class LOBStagePositionTest(unittest.TestCase):
    """TREATY25-LOB-QUALIFICATION must run BEFORE TREATY25-15 so the
    rest of the graph never executes for a non-qualified taxpayer.
    """

    def test_lob_stage_is_first(self) -> None:
        stage_ids = [s.stage_id for s in treaty_law_stages_2025()]
        self.assertEqual(stage_ids[0], "TREATY25-LOB-QUALIFICATION")
        self.assertIn("TREATY25-15-US-SOURCE-DIVIDENDS", stage_ids)
        self.assertLess(
            stage_ids.index("TREATY25-LOB-QUALIFICATION"),
            stage_ids.index("TREATY25-15-US-SOURCE-DIVIDENDS"),
        )

    def test_lob_stage_cites_article_28(self) -> None:
        lob = next(
            s for s in treaty_law_stages_2025() if s.stage_id == "TREATY25-LOB-QUALIFICATION"
        )
        self.assertTrue(any("Art. 28" in ref for ref in lob.legal_refs))
        self.assertIn(DBA_USA_ART_28_URL, lob.authority_urls)

    def test_lob_rule_function_is_registered(self) -> None:
        rules = treaty_law_rules_2025()
        rule_ids = [r.stage.stage_id for r in rules]
        self.assertIn("TREATY25-LOB-QUALIFICATION", rule_ids)


class LOBRuleFunctionTest(unittest.TestCase):
    """Direct exercises of ``treaty25_lob_qualification`` validate the
    closed-enum / fail-closed posture without spinning up the graph.
    """

    def _facts(self, treaty_inputs: USTreatyInputs2025) -> dict:
        return {"us.treaty.inputs": treaty_inputs}

    def test_each_qualifying_category_passes(self) -> None:
        # Every Art. 28 qualifying category yields ``lob_qualified=True``
        # and (under ``use_resourcing=True``) ``form_8833_required=True``
        # via § 6114. The category surface is the closed-enum check.
        for category in (
            "qualified_resident",
            "publicly_traded",
            "active_business",
            "derivative_benefits",
            "competent_authority",
        ):
            with self.subTest(category=category):
                result = treaty25_lob_qualification(
                    self._facts(_treaty_inputs(category))
                )
                self.assertTrue(result["treaty.lob_qualified"])
                self.assertEqual(result["treaty.lob_category"], category)
                self.assertTrue(result["treaty.form_8833_required"])

    def test_not_qualified_with_resourcing_fails_closed(self) -> None:
        # Per CLAUDE.md "fail closed" — Art. 28 + Pub. 514 require
        # qualification before treaty re-sourcing can be claimed.
        with self.assertRaisesRegex(ValueError, "LOB qualification"):
            treaty25_lob_qualification(
                self._facts(_treaty_inputs("not_qualified", use_resourcing=True))
            )

    def test_not_qualified_without_resourcing_passes_with_zero(self) -> None:
        # Without a resourcing claim, a not-qualified taxpayer is
        # legitimate — the LOB stage records the posture and disables
        # downstream resourcing.
        result = treaty25_lob_qualification(
            self._facts(_treaty_inputs("not_qualified", use_resourcing=False))
        )
        self.assertFalse(result["treaty.lob_qualified"])
        self.assertFalse(result["treaty.form_8833_required"])

    def test_unknown_category_fails_closed(self) -> None:
        # An unrecognized category is not a legal posture; fail closed.
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            treaty25_lob_qualification(
                self._facts(_treaty_inputs("totally_made_up_category"))
            )


class LOBForm8833RequirementTest(unittest.TestCase):
    """Form 8833 disclosure under § 6114 is required when treaty
    benefits are claimed."""

    def test_form_8833_required_when_resourcing_and_qualified(self) -> None:
        result = treaty25_lob_qualification(
            {"us.treaty.inputs": _treaty_inputs("qualified_resident", use_resourcing=True)}
        )
        self.assertTrue(result["treaty.form_8833_required"])

    def test_form_8833_not_required_without_resourcing(self) -> None:
        result = treaty25_lob_qualification(
            {"us.treaty.inputs": _treaty_inputs("qualified_resident", use_resourcing=False)}
        )
        self.assertFalse(result["treaty.form_8833_required"])


if __name__ == "__main__":
    unittest.main()
