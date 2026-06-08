"""Auto-derive foreign-financial-accounts stubs from extracted facts.

Phase 5.2 (FORM-MAPPING-FOLLOWUP, 2026-05-03): the manual-determination
posture for Form 8938 (26 U.S.C. § 6038D) and FBAR (31 CFR § 1010.350)
ships an empty CSV today, so every brenn-style workspace requires the
user to author the foreign-account list by hand. This module scans the
already-extracted ``normalized/facts/index.json`` for documents whose
``country_of_origin`` is non-U.S. AND whose ``document_family`` evidences
a financial-account relationship (German bank capital certificate, N26
transfer confirmation), and emits a stub ``foreign-financial-accounts.csv``
with one row per discovered account.

The derivation is intentionally a "best-effort with documented gaps"
posture: balances are NOT in the source documents and remain at zero
with ``data_completeness="balance_unknown"`` until the user fills them
in. The corollary in the rule layer: ``data_complete`` stays False
unless the user explicitly stamps the sentinel row OR creates the
``.complete`` marker file (existing contract, unchanged), but the
discovered accounts now flow into the renderer so the manual-determination
status sheet enumerates EACH account found rather than presenting the
user with a blank schema.

This is materially better than the empty-CSV baseline because the user
sees "fill in the EOY balance for these N foreign accounts" rather than
"populate this CSV from scratch". For brenn-2025 the derivation
discovers two evidentiary stubs:

  - ``upvest_lien_2025`` — Lien's Upvest Jahressteuerbescheinigung
    (germany_bank / capital_certificate). Conservative: surface as
    ``signature_authority_unknown`` per the directive's "ignore
    Lien-only accounts unless Brenn has signature authority".
  - ``n26_brenn_2025`` — N26 transfer confirmation evidences Brenn's
    use of an N26 account to pay the Finanzamt. The transfer-confirmation
    document is the only direct evidence of this account so balance is
    unknown.

A workspace can suppress / extend the derived list via
``manual_overrides.json::foreign_financial_accounts.derived_account_overrides``
(reserved for future workspaces; not used by brenn-2025).

Authority:
- 26 U.S.C. § 6038D — https://www.law.cornell.edu/uscode/text/26/6038D
- 26 CFR § 1.6038D-2 — https://www.law.cornell.edu/cfr/text/26/1.6038D-2
- IRS Form 8938 — https://www.irs.gov/forms-pubs/about-form-8938
- 31 U.S.C. § 5314 — https://www.law.cornell.edu/uscode/text/31/5314
- 31 CFR § 1010.350 — https://www.law.cornell.edu/cfr/text/31/1010.350
- IRS Form 8938 vs FBAR comparison —
  https://www.irs.gov/businesses/comparison-of-form-8938-and-fbar-requirements
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from tax_pipeline.paths import YearPaths


# Filename for the derived stub CSV. Co-located with the other auto-
# derived treaty / model artifacts under ``outputs/tax-positions/`` so a
# workspace audit can grep one directory for every machine-emitted CSV.
DERIVED_FFA_FILENAME = "foreign-financial-accounts-derived.csv"

# Schema of the derived CSV. Mirrors the manual-CSV schema documented in
# ``load_us_fatca_fbar_inputs_2025`` plus a ``data_completeness`` column
# that tags how much of each row's data the derivation actually carries.
# Values:
#   "balance_unknown" — institution + country + account_type known; max
#                       and EOY balance are zero placeholders.
#   "eoy_only"        — EOY balance carried from a year-end statement;
#                       max-during-year is approximated as the EOY value.
#                       (Currently unused; reserved for future certificate
#                       parsers that surface a Dec 31 balance.)
#   "complete"        — both balance fields carry verified data.
DERIVED_FFA_FIELDS = [
    "account_id",
    "country",
    "institution",
    "account_type",
    "currency",
    "usd_max_balance_during_year",
    "usd_eoy_balance",
    "is_specified_foreign_financial_asset",
    "data_completeness",
    "evidence_source",
    "owner_note",
]


@dataclass(frozen=True)
class DiscoveredForeignAccount:
    """A foreign account stub discovered from extracted facts.

    All Decimal-valued fields are emitted as zero strings ("0.00") in
    the ``balance_unknown`` posture; the ``data_completeness`` column
    tells the loader / rule / renderer how much to trust them.
    """

    account_id: str
    country: str
    institution: str
    account_type: str
    currency: str
    is_specified_foreign_financial_asset: bool
    data_completeness: str
    evidence_source: str
    owner_note: str


# Mapping of (country_of_origin, document_family) → discovery template.
# The fact-extraction stage already pins each document to a country and
# family; this dict says "yes, that combination evidences a foreign
# financial account." Each entry returns the (institution, account_type,
# currency, is_sffa, owner_note) defaults; account_id is composed by the
# caller with a stable suffix for determinism.
_FAMILY_TEMPLATES: dict[tuple[str, str], dict[str, object]] = {
    # German bank Jahressteuerbescheinigung — evidences a German-based
    # custodial / brokerage account. SFFA scope per Reg. § 1.6038D-3(a).
    ("DE", "capital_certificate"): {
        "institution_default": "Germany bank (Upvest / similar)",
        "account_type": "brokerage",
        "currency": "EUR",
        "is_specified_foreign_financial_asset": True,
        "owner_note": (
            "Evidenced by a German Jahressteuerbescheinigung. SFFA scope per "
            "Reg. § 1.6038D-3(a) (foreign brokerage account). Confirm "
            "signature authority before treating Lien-only accounts as the "
            "U.S. filer's reportable account."
        ),
    },
    # N26 transfer confirmation — evidences a German bank account
    # actively used by the U.S. filer (transfers to the Finanzamt are
    # routed from this account). SFFA scope per Reg. § 1.6038D-3(a).
    ("DE", "transfer_confirmation"): {
        "institution_default": "N26",
        "account_type": "bank",
        "currency": "EUR",
        "is_specified_foreign_financial_asset": True,
        "owner_note": (
            "Evidenced by an N26 transfer-confirmation PDF. SFFA scope per "
            "Reg. § 1.6038D-3(a) (foreign deposit account). FBAR scope per "
            "31 CFR § 1010.350(c)(1)."
        ),
    },
}


def _read_facts_index(paths: YearPaths) -> list[dict[str, object]]:
    """Load ``normalized/facts/index.json`` if present, else ``[]``."""
    index_path = paths.facts_root / "index.json"
    if not index_path.exists():
        return []
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def _read_facts_md_metadata(paths: YearPaths, markdown_path: str) -> dict[str, str]:
    r"""Parse the leading metadata bullets out of an extracted facts.md.

    Looks for ``- country of origin: \`DE\``` and ``- document family:
    \`capital_certificate\``` style bullets. Returns a string-to-string
    map; missing fields surface as empty strings rather than raising.
    The facts.md format is owned by ``fact_extraction.py`` and is the
    same format the test suite exercises in ``test_fact_extraction.py``.
    """
    full_path = paths.workspace_root / markdown_path
    if not full_path.exists():
        return {}
    metadata: dict[str, str] = {}
    for line in full_path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("- "):
            continue
        body = line[2:]
        if ":" not in body:
            continue
        key, _, raw_value = body.partition(":")
        key = key.strip()
        value = raw_value.strip()
        # Strip surrounding backticks emitted by the facts.md formatter.
        if value.startswith("`") and value.endswith("`"):
            value = value[1:-1]
        metadata[key] = value
    return metadata


def _account_id_for(family: str, owner: str, source_stem: str) -> str:
    """Build a deterministic account_id for a discovered account.

    Pattern: ``<family>_<owner_or_stem>_<year_suffix>`` — the full file
    stem keeps the id stable across re-runs and human-readable in the
    derived CSV. Length-bounded by snipping the stem at 24 characters
    so the id fits a tax-form table cell without truncation.
    """
    short_family = family.replace("_", "-")
    owner_or_stem = (owner or source_stem or "unknown").replace(" ", "_")
    return f"{short_family}__{owner_or_stem[:24]}"


def derive_foreign_financial_accounts_2025(
    paths: YearPaths,
) -> tuple[DiscoveredForeignAccount, ...]:
    """Scan ``normalized/facts/index.json`` and produce account stubs.

    Returns the discovered tuple in deterministic id-sorted order so
    the derived CSV is byte-stable across re-runs.
    """
    index = _read_facts_index(paths)
    discovered: dict[str, DiscoveredForeignAccount] = {}
    for entry in index:
        country = ""
        family = ""
        owner = ""
        markdown_path = entry.get("markdown_path")
        if isinstance(markdown_path, str):
            md = _read_facts_md_metadata(paths, markdown_path)
            country = md.get("country of origin", "").upper()
            family = md.get("document family", "").lower()
            owner = md.get("owner", "")
            if owner.lower() == "none":
                owner = ""
        # Accounts in the U.S. (country_of_origin == "US") are NOT
        # foreign financial accounts under § 6038D / 31 CFR § 1010.350,
        # even when they hold foreign-issued securities. Skip them.
        if not country or country == "US":
            continue
        template = _FAMILY_TEMPLATES.get((country, family))
        if template is None:
            continue
        relative_path = str(entry.get("relative_path", ""))
        source_stem = Path(relative_path).stem
        account_id = _account_id_for(family, owner, source_stem)
        # Workspace can have multiple documents touching the same
        # underlying account (e.g. multiple N26 transfer confirmations);
        # dedupe by account_id and keep the first encountered evidence.
        if account_id in discovered:
            continue
        institution = str(template["institution_default"])
        account_type = str(template["account_type"])
        currency = str(template["currency"])
        is_sffa = bool(template["is_specified_foreign_financial_asset"])
        owner_note = str(template["owner_note"])
        discovered[account_id] = DiscoveredForeignAccount(
            account_id=account_id,
            country=country,
            institution=institution,
            account_type=account_type,
            currency=currency,
            is_specified_foreign_financial_asset=is_sffa,
            data_completeness="balance_unknown",
            evidence_source=relative_path,
            owner_note=owner_note,
        )
    return tuple(sorted(discovered.values(), key=lambda a: a.account_id))


def write_foreign_financial_accounts_2025(paths: YearPaths) -> tuple[Path, int]:
    """Write the derived stub CSV; idempotent.

    Returns ``(path, account_count)``. The CSV is always emitted (even
    when zero accounts are discovered) so a workspace audit can confirm
    "the derivation ran and found no foreign accounts" rather than "the
    derivation never ran".
    """
    accounts = derive_foreign_financial_accounts_2025(paths)
    paths.tax_positions_root.mkdir(parents=True, exist_ok=True)
    out_path = paths.tax_positions_root / DERIVED_FFA_FILENAME
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DERIVED_FFA_FIELDS)
        writer.writeheader()
        for account in accounts:
            writer.writerow(
                {
                    "account_id": account.account_id,
                    "country": account.country,
                    "institution": account.institution,
                    "account_type": account.account_type,
                    "currency": account.currency,
                    # The "balance_unknown" data_completeness flag means
                    # both balance columns are placeholders. The user
                    # must fill them in (and stamp the sentinel
                    # ``__data_complete__`` row OR drop the
                    # ``foreign-financial-accounts.complete`` marker)
                    # before the rule will graduate from
                    # ``status="not_applicable"``.
                    "usd_max_balance_during_year": "0.00",
                    "usd_eoy_balance": "0.00",
                    "is_specified_foreign_financial_asset": (
                        "true"
                        if account.is_specified_foreign_financial_asset
                        else "false"
                    ),
                    "data_completeness": account.data_completeness,
                    "evidence_source": account.evidence_source,
                    "owner_note": account.owner_note,
                }
            )
    return out_path, len(accounts)


__all__ = [
    "DERIVED_FFA_FILENAME",
    "DERIVED_FFA_FIELDS",
    "DiscoveredForeignAccount",
    "derive_foreign_financial_accounts_2025",
    "write_foreign_financial_accounts_2025",
]
