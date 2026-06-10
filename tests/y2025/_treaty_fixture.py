"""Shared test fixture: the demo's U.S. treaty-dividend-items file.

Several U.S. decomposition / stage tests inject the *synthetic* demo
Germany treaty dividend packet (``msft_us_dividend``, 280 EUR) into
``load_us_assessment_inputs_2025`` to exercise the Pub. 514 treaty
re-sourcing path. The real pipeline auto-derives the matching
``us-treaty-dividend-items.csv`` during a run, so by the time the U.S.
model loads, the file exists and the coverage gate passes.

Tests that materialize a fresh demo workspace and then load directly
(skipping the derivation step) must write that matching file themselves
— otherwise the loader correctly fail-closes: a Germany treaty packet
under an active treaty election with no declared U.S. position is a
coverage-contract violation (CLAUDE.md "Null / zero / missing"; the
2026-06-08 coverage-gap fix in ``us_inputs.py``).

This helper writes the single canonical row that matches the demo
packet. The gross_dividend_usd (316.03) is 280 EUR ÷ 0.886 (the 2025
IRS yearly-average rate) and yields the asserted treaty outputs
(gross 316.03, German pre-credit 40.91, allowed U.S. tax 47.40).
"""

from __future__ import annotations

from tax_pipeline.paths import YearPaths

# item_id must match _demo_germany_treaty_dividend_packet_items() /
# the GermanyUSTreatyDividendPacketItem2025 the tests inject.
# treaty_bucket must be one of {direct_equity, equity_fund,
# non_equity_fund} (validate_treaty_resourcing_inputs_2025). MSFT is a
# direct stock holding → direct_equity.
_DEMO_US_TREATY_ITEMS_CSV = (
    "item_id,treaty_bucket,gross_dividend_usd,source,note\n"
    "msft_us_dividend,direct_equity,316.03,test_fixture,"
    "Matches the synthetic demo Germany treaty dividend packet "
    "(msft_us_dividend); the real pipeline auto-derives this file.\n"
)


def write_demo_us_treaty_dividend_items(paths: YearPaths) -> None:
    """Write the U.S. treaty-dividend-items file matching the demo packet.

    Call this right after ``materialize_demo_workspace`` in any fixture
    that passes a populated ``germany_treaty_dividend_items`` packet to
    ``load_us_assessment_inputs_2025``.
    """
    paths.tax_positions_root.mkdir(parents=True, exist_ok=True)
    (paths.tax_positions_root / "us-treaty-dividend-items.csv").write_text(
        _DEMO_US_TREATY_ITEMS_CSV, encoding="utf-8"
    )
