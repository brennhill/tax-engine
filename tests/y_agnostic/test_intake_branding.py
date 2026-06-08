"""Branding regression tests for the intake wizard.

The user-facing UI is branded as the **Tax Engine** — a neutral product
name for a 2025 Germany / U.S. cross-border tax pipeline. This test
locks the branding surface in place and asserts that no political /
satirical content (Moral-Alignment License, "Thievery Calculator", CBT
denunciation, Eritrea comparisons, "Cartoon TBD" placeholders) sneaks
back in.

Authority: there is no legal authority for branding strings; this test
asserts UX contract only. Numeric / legal-output regressions are
covered by other test files (e.g. tests under tests/test_germany_*,
tests/test_us_*, tests/test_treaty_*).
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = REPO_ROOT / "tax_pipeline" / "intake" / "static"
INDEX_HTML = STATIC_DIR / "index.html"

# Substrings that must never reappear in the user-facing HTML.
# Each entry pairs the forbidden token with a short reason so a failing
# assertion explains itself.
FORBIDDEN_SUBSTRINGS: tuple[tuple[str, str], ...] = (
    ("Thievery", "old satirical product name has been retired"),
    ("Moral-Alignment", "license was changed to AGPL-3.0-or-later"),
    ("Compute Thievery", "run button label has been renamed"),
    ("Citizenship-based taxation", "political framing has been removed"),
    ("Eritrea", "political comparison has been removed"),
    ("Cartoon TBD", "cartoon slots have been removed"),
    ("cartoon-slot", "cartoon figure markup has been removed"),
    ("/static/cartoons/", "cartoons directory has been removed"),
    ("manifesto-banner", "footer manifesto has been replaced with a disclaimer"),
    ("truisms", "header truisms list has been removed"),
)


class IntakeBrandingTests(unittest.TestCase):
    """Lock the neutral branding surface in place."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.html = INDEX_HTML.read_text(encoding="utf-8")

    def test_page_title_and_header_use_tax_engine_name(self) -> None:
        self.assertIn(
            "<title>Tax Engine</title>",
            self.html,
            "Page <title> must brand the wizard as 'Tax Engine'.",
        )
        self.assertRegex(
            self.html,
            r"<h1>\s*Tax Engine\s*</h1>",
            "Header <h1> must read 'Tax Engine'.",
        )

    def test_run_button_label_is_neutral(self) -> None:
        match = re.search(
            r'<button[^>]*id="run-button"[^>]*>([^<]+)</button>',
            self.html,
        )
        self.assertIsNotNone(match, "run-button must exist in index.html")
        assert match is not None  # for type-checker
        self.assertEqual(
            match.group(1).strip(),
            "Run pipeline",
            "Run button must be labeled 'Run pipeline'.",
        )

    def test_disclaimer_banner_is_present(self) -> None:
        # The footer disclaimer is load-bearing for the not-professional-
        # advice posture; assert both the banner class and the substantive
        # warning text.
        self.assertIn(
            'class="disclaimer-banner"',
            self.html,
            "Footer must carry a .disclaimer-banner element.",
        )
        self.assertIn(
            "Not professional tax advice",
            self.html,
            "Disclaimer banner must warn that the engine is not professional tax advice.",
        )

    def test_no_political_or_satirical_content_returns(self) -> None:
        for needle, reason in FORBIDDEN_SUBSTRINGS:
            with self.subTest(needle=needle):
                self.assertNotIn(
                    needle,
                    self.html,
                    f"Forbidden substring '{needle}' reappeared in index.html — {reason}.",
                )


if __name__ == "__main__":
    unittest.main()
