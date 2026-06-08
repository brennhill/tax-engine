"""Partial-save / restore screens for the intake wizard (Wave 6).

This module groups the five new screens that the Wave 6 intake-wizard pass
adds beyond the household / payments / postures forms shipped earlier:

  1. Identity & Employment      — profile.json + people.csv profile fields
  2. Bank accounts              — config/bank_accounts.csv (Schedule B Part III)
  3. DE Wave-3A deduction inputs — config/manual_overrides.json deductions
  4. Vorabpauschale per-fund     — normalized/reference-data/de-vorabpauschale-inputs-2025.csv
  5. Prior-year carryovers       — config/manual_overrides.json + de-loss-carryforwards.csv

Every public ``read_*_state`` / ``write_*_state`` helper in this module
implements the **partial-save + restore** contract:

  * ``read`` always returns a dict whose shape matches what the form
    submits, with empty strings for missing scalar fields and an empty
    list for missing repeated rows. The frontend can therefore restore
    state on screen activation without raising.
  * ``write`` only persists keys that the caller actually included in
    the submission (None / missing means "leave existing on-disk value
    untouched"); blank strings on scalars are interpreted as "user
    explicitly cleared this field" and ARE persisted. Repeated-row
    sections (bank accounts, vorabpauschale funds) replace the full
    list because users add and remove rows in-place.
  * Each ``write`` performs validation and raises ``ScreenValidationError``
    when an input is structurally invalid; the on-disk state is then
    untouched (the writer reads, mutates in memory, and only writes once
    every value validates).

CLAUDE.md tax-rule requirements are honored by the engine, not by this
intake module: the screens here only capture inputs and route them to
the existing CSV / JSON files the engine already reads. Citations live
in the field-level tooltips that the frontend renders alongside each
input.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tax_pipeline.core.io import atomic_write_text
from tax_pipeline.paths import YearPaths
from tax_pipeline.scaffold_year import (
    PEOPLE_COLUMNS,
    ensure_year_scaffold,
)


class ScreenValidationError(ValueError):
    """Raised when a screen submission fails structural validation."""


# ---------------------------------------------------------------------------
# Tooltip + citation registry — used by both backend (for documentation)
# and frontend (rendered next to each input).
#
# Structure: ``{screen: {field_key: {"tooltip", "legal_refs", "legal_urls"}}}``
# ---------------------------------------------------------------------------
SCREEN_TOOLTIPS: dict[str, dict[str, dict[str, Any]]] = {
    "identity": {
        "full_legal_name": {
            "tooltip": (
                "Type your full legal name exactly as it appears on your "
                "passport or driver's license. The IRS and the German tax "
                "office both compare names to your tax ID, so a typo can "
                "delay your refund. Use your married name only if you "
                "have legally changed it. (Legal: § 25 EStG; 26 U.S.C. "
                "§ 6011)"
            ),
            "legal_refs": ("§ 25 EStG", "26 U.S.C. § 6011"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/estg/__25.html",
                "https://www.law.cornell.edu/uscode/text/26/6011",
            ),
        },
        "address_street": {
            "tooltip": (
                "Type the street name and house number where you currently "
                "live, just like you would write it on an envelope. Both "
                "the IRS and ELSTER need this to mail you assessment "
                "letters; a mismatch can delay processing. (Legal: § 8 AO; "
                "26 U.S.C. § 6011)"
            ),
            "legal_refs": ("§ 8 AO", "26 U.S.C. § 6011"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/ao_1977/__8.html",
                "https://www.law.cornell.edu/uscode/text/26/6011",
            ),
        },
        "address_city": {
            "tooltip": (
                "Type the city where you lived on December 31 of the tax "
                "year. This is the city the German tax office considers "
                "your home for the year. (Legal: § 8 AO)"
            ),
            "legal_refs": ("§ 8 AO",),
            "legal_urls": ("https://www.gesetze-im-internet.de/ao_1977/__8.html",),
        },
        "address_postal_code": {
            "tooltip": (
                "Type your ZIP/postal code: 5 digits in Germany (like "
                "10115), or 5 or 9 digits in the U.S. (like 90210 or "
                "90210-1234). (Legal: § 8 AO)"
            ),
            "legal_refs": ("§ 8 AO",),
            "legal_urls": ("https://www.gesetze-im-internet.de/ao_1977/__8.html",),
        },
        "address_country": {
            "tooltip": (
                "Type the 2-letter country code where you live: DE for "
                "Germany, US for the United States, AT for Austria, and "
                "so on. The country decides whether Germany taxes you on "
                "your worldwide income or only on your German income. "
                "(Legal: § 1 EStG)"
            ),
            "legal_refs": ("§ 1 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__1.html",),
        },
        "us_ssn_or_itin": {
            "tooltip": (
                "Type your 9-digit U.S. Social Security Number or ITIN, "
                "like 123-45-6789. The IRS will not accept a Form 1040 "
                "without it. If you do not have one and need to file, "
                "apply for an ITIN with Form W-7. (Legal: 26 U.S.C. "
                "§ 6109)"
            ),
            "legal_refs": ("26 U.S.C. § 6109",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/6109",),
        },
        "german_tax_id": {
            "tooltip": (
                "Type your 11-digit German Steuer-Identifikationsnummer "
                "(Steuer-ID). It is the number on the letter you got from "
                "the Bundeszentralamt fuer Steuern when you registered "
                "your address. Every German tax form needs it. (Legal: "
                "§ 139b AO)"
            ),
            "legal_refs": ("§ 139b AO",),
            "legal_urls": ("https://www.gesetze-im-internet.de/ao_1977/__139b.html",),
        },
        "date_of_birth": {
            "tooltip": (
                "Type your birth date as YYYY-MM-DD (for example, "
                "1985-03-12). Germany uses your birth date to figure out "
                "if you qualify for the senior age allowance, which "
                "starts the year after you turn 64. (Legal: § 24a EStG)"
            ),
            "legal_refs": ("§ 24a EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__24a.html",),
        },
        "citizenship_status": {
            "tooltip": (
                "Pick whether you are a U.S. citizen, a U.S. green-card "
                "holder, or neither. U.S. citizens and green-card holders "
                "have to file a U.S. return on their worldwide income, no "
                "matter where they live. Picking 'neither' turns off the "
                "U.S. side of this calculator entirely. (Legal: 26 U.S.C. "
                "§§ 6012, 7701(b))"
            ),
            "legal_refs": ("26 U.S.C. § 6012", "26 U.S.C. § 7701(b)"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/26/6012",
                "https://www.law.cornell.edu/uscode/text/26/7701",
            ),
        },
        "employment_city": {
            "tooltip": (
                "Type the city where you actually go to work. Germany "
                "uses the distance between home and work to figure out "
                "your commuter deduction, and the city decides which "
                "state's solidarity and church-tax rates apply. (Legal: "
                "§ 9 EStG)"
            ),
            "legal_refs": ("§ 9 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__9.html",),
        },
        "employment_country": {
            "tooltip": (
                "Type the 2-letter country code for the country where "
                "you actually do your job (DE for Germany, US for the "
                "United States, etc.). This decides whether your wages "
                "are German-source or U.S.-source for treaty and credit "
                "rules. (Legal: § 19 EStG; 26 U.S.C. § 861)"
            ),
            "legal_refs": ("§ 19 EStG", "26 U.S.C. § 861"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/estg/__19.html",
                "https://www.law.cornell.edu/uscode/text/26/861",
            ),
        },
    },
    "bank_accounts": {
        "label": {
            "tooltip": (
                "Type a short nickname for this account so you can tell it "
                "apart from your others, like 'Sparkasse Berlin checking' "
                "or 'Schwab brokerage'. This is just for your eyes; it is "
                "not sent to any tax office. (Legal: 31 U.S.C. § 5314)"
            ),
            "legal_refs": ("31 U.S.C. § 5314",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/31/5314",),
        },
        "country": {
            "tooltip": (
                "Type the 2-letter country code where the bank or broker "
                "is based (DE for Germany, US for the U.S., etc.). If the "
                "country is anything other than US, the IRS treats it as "
                "a 'foreign account' and you may have to file an FBAR "
                "report when your foreign accounts add up to more than "
                "$10,000 at any point in the year. (Legal: 31 U.S.C. "
                "§ 5314; 26 U.S.C. § 6038D)"
            ),
            "legal_refs": ("31 U.S.C. § 5314", "26 U.S.C. § 6038D"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/31/5314",
                "https://www.law.cornell.edu/uscode/text/26/6038D",
            ),
        },
        "account_number": {
            "tooltip": (
                "Type your IBAN or account number. The IRS asks for it on "
                "FBAR (FinCEN 114) and on Form 8938 if you have to file "
                "those. We store it locally; we never email it. (Legal: "
                "31 U.S.C. § 5314)"
            ),
            "legal_refs": ("31 U.S.C. § 5314",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/31/5314",),
        },
        "year_end_balance_usd": {
            "tooltip": (
                "Type the U.S. dollar balance in this account on December "
                "31. If the account is in euros or another currency, "
                "convert to dollars using the year-end exchange rate. We "
                "use this number to check whether you cross the FBAR "
                "$10,000 threshold or the Form 8938 thresholds. (Legal: "
                "31 U.S.C. § 5314; 26 U.S.C. § 6038D)"
            ),
            "legal_refs": ("31 U.S.C. § 5314", "26 U.S.C. § 6038D"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/31/5314",
                "https://www.law.cornell.edu/uscode/text/26/6038D",
            ),
        },
        "linked_certificate_hash": {
            "tooltip": (
                "Optional. If you have uploaded a year-end statement or "
                "tax certificate from this bank, paste its SHA-256 hash "
                "here so the audit trail can match the document to the "
                "account. Leave blank if you do not have one. (Legal: "
                "§ 90 AO)"
            ),
            "legal_refs": ("§ 90 AO",),
            "legal_urls": ("https://www.gesetze-im-internet.de/ao_1977/__90.html",),
        },
    },
    "de_deductions": {
        "medical_expenses_eur": {
            "tooltip": (
                "Type the total euros you paid out of pocket for doctors, "
                "dentists, prescriptions, glasses, and similar medical "
                "costs that your insurance did not cover. Germany only "
                "lets you deduct the part above a 'reasonable burden' "
                "threshold that is based on your income and family. We "
                "subtract that threshold for you, so just enter the "
                "gross amount you paid. (Legal: § 33 EStG)"
            ),
            "legal_refs": ("§ 33 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33.html",),
        },
        "charitable_donations_eur": {
            "tooltip": (
                "Type the euros you gave to recognized charities or "
                "religious bodies during the year. Germany lets you "
                "deduct up to 20% of your total income. Anything above "
                "that is supposed to carry over to next year, but our "
                "calculator does not yet handle the carryover, so enter "
                "only the part that fits this year's cap. (Legal: § 10b "
                "EStG)"
            ),
            "legal_refs": ("§ 10b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__10b.html",),
        },
        "support_payments_eur": {
            "tooltip": (
                "Type the euros you paid to support someone you have a "
                "legal duty to support, like an ex-spouse, a parent, or "
                "an adult child no longer eligible for Kindergeld. The "
                "deduction is capped at the basic personal allowance "
                "(Grundfreibetrag) and shrinks if the person you support "
                "earned more than 624 EUR of their own. (Legal: § 33a "
                "EStG)"
            ),
            "legal_refs": ("§ 33a EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33a.html",),
        },
        "support_recipient_relationship": {
            "tooltip": (
                "Pick how the person you are supporting is related to "
                "you. Germany only lets you deduct support payments for "
                "people you have a legal duty to support, like an "
                "ex-spouse, a parent, or an adult child not on "
                "Kindergeld. (Legal: § 33a EStG)"
            ),
            "legal_refs": ("§ 33a EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33a.html",),
        },
        "support_recipient_income_eur": {
            "tooltip": (
                "Type the euros the person you are supporting earned on "
                "their own during the year (wages, pension, etc.). "
                "Germany shrinks your support deduction by every euro "
                "they earned above 624 EUR. If they earned nothing, "
                "enter 0. (Legal: § 33a EStG)"
            ),
            "legal_refs": ("§ 33a EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33a.html",),
        },
        "gdb": {
            "tooltip": (
                "If you have a recognized disability rating from the "
                "German government, type the percentage from your "
                "Schwerbehindertenausweis (20, 30, 40, ... up to 100). "
                "Otherwise enter 0. The percentage decides how big a "
                "flat-rate disability deduction you get. (Legal: § 33b "
                "EStG)"
            ),
            "legal_refs": ("§ 33b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33b.html",),
        },
        "hilflos_or_blind": {
            "tooltip": (
                "Check this if you are blind or your disability ID lists "
                "you as 'hilflos' (helpless and needing constant "
                "assistance). It unlocks a special 7,400 EUR flat-rate "
                "deduction that is bigger than the regular disability "
                "table. (Legal: § 33b EStG)"
            ),
            "legal_refs": ("§ 33b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__33b.html",),
        },
        "arbeitszimmer_claimed": {
            "tooltip": (
                "Check this if you have a separate room in your home "
                "used only for work (a real home office, not just a "
                "kitchen table). You cannot also claim the new daily "
                "home-office flat rate for the same days. (Legal: § 4 "
                "Abs. 5 Satz 1 Nr. 6b EStG)"
            ),
            "legal_refs": ("§ 4 Abs. 5 Satz 1 Nr. 6b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__4.html",),
        },
        "arbeitszimmer_qualifies_as_mittelpunkt": {
            "tooltip": (
                "Check this only if your home office is truly the center "
                "of your work life (you mostly work from there, not at "
                "an employer's office). If it is, you can deduct your "
                "actual costs. If not, you get a fixed 1,260 EUR flat "
                "rate instead. (Legal: § 4 Abs. 5 Satz 1 Nr. 6b EStG)"
            ),
            "legal_refs": ("§ 4 Abs. 5 Satz 1 Nr. 6b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__4.html",),
        },
        "arbeitszimmer_actual_costs_eur": {
            "tooltip": (
                "Type the euros you actually spent on the home-office "
                "room: rent share, utilities, internet, etc. We only "
                "deduct the full amount if you also checked the "
                "'Mittelpunkt' box; otherwise we apply the 1,260 EUR "
                "flat rate instead. (Legal: § 4 Abs. 5 Satz 1 Nr. 6b "
                "EStG)"
            ),
            "legal_refs": ("§ 4 Abs. 5 Satz 1 Nr. 6b EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__4.html",),
        },
        "taxpayer_birth_year": {
            "tooltip": (
                "Type the 4-digit year you were born (for example, "
                "1958). Germany uses your birth year to figure out the "
                "senior age allowance: the rate is locked in the year "
                "after you turn 64 and stays the same forever after. "
                "(Legal: § 24a EStG)"
            ),
            "legal_refs": ("§ 24a EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__24a.html",),
        },
    },
    "vorabpauschale": {
        "symbol": {
            "tooltip": (
                "Type the fund's ticker symbol (like VWCE) or its 12-"
                "character ISIN code (like IE00BK5BQT80). You can find "
                "the ISIN on your broker's year-end statement. We use "
                "this to match the fund to its tax class. (Legal: "
                "InvStG § 18)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "fund_name": {
            "tooltip": (
                "Type a friendly name for the fund, like 'Vanguard FTSE "
                "All-World'. This is just a label so you can find it "
                "later; nothing is sent anywhere. (Legal: InvStG § 18)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "nav_start_eur": {
            "tooltip": (
                "Type the fund's price per share in euros on the first "
                "trading day of the year. Your broker statement usually "
                "calls this the 'beginning value'. We use it to figure "
                "out how much the fund grew during the year. (Legal: "
                "InvStG § 18)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "nav_end_eur": {
            "tooltip": (
                "Type the fund's price per share in euros on the last "
                "trading day of the year. Together with the start price, "
                "this tells us how much the fund grew. Germany's "
                "'Vorabpauschale' tax is the smaller of the actual "
                "growth or a benchmark interest rate. (Legal: InvStG "
                "§ 18)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "ausschuettung_eur": {
            "tooltip": (
                "Type the euros the fund actually paid out to you in "
                "dividends or distributions during the year. We "
                "subtract those from the Vorabpauschale base because "
                "Germany already taxed them when they hit your account. "
                "Enter 0 if the fund pays nothing out. (Legal: InvStG "
                "§ 18 Abs. 1)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "months_held": {
            "tooltip": (
                "Type how many full months you owned the fund during "
                "the year, 0 through 12. If you bought it mid-year and "
                "held it through December, count only full months you "
                "had it. The tax is prorated by months. (Legal: InvStG "
                "§ 18 Abs. 2)"
            ),
            "legal_refs": ("InvStG § 18",),
            "legal_urls": ("https://www.gesetze-im-internet.de/invstg_2018/__18.html",),
        },
        "fund_classification": {
            "tooltip": (
                "Pick the fund's category. Pure stock funds "
                "(Aktienfonds) get a 30% tax break. Mixed funds get "
                "15%. Real-estate funds get 60% (German real estate) or "
                "80% (foreign real estate). 'Sonstige' is the catch-all "
                "for everything else and gets no break. Your broker's "
                "tax certificate usually tells you the category. "
                "(Legal: InvStG §§ 2, 20)"
            ),
            "legal_refs": ("InvStG § 20", "InvStG § 2"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/invstg_2018/__20.html",
                "https://www.gesetze-im-internet.de/invstg_2018/__2.html",
            ),
        },
    },
    "children": {
        "name": {
            "tooltip": (
                "Type the child's full legal name as it appears on their "
                "Social Security card, ITIN letter, or German Steuer-ID "
                "letter. The IRS and the Familienkasse both compare names "
                "to ID numbers, so a typo can stall the dependent claim "
                "or Kindergeld. (Legal: 26 U.S.C. § 152; § 32 EStG)"
            ),
            "legal_refs": ("26 U.S.C. § 152", "§ 32 EStG"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/26/152",
                "https://www.gesetze-im-internet.de/estg/__32.html",
            ),
        },
        "date_of_birth": {
            "tooltip": (
                "Type the child's birth date as YYYY-MM-DD (for example, "
                "2018-09-12). The IRS uses age to decide between the "
                "$2,200 Child Tax Credit (under 17) and the $500 Credit "
                "for Other Dependents. Germany uses age to decide whether "
                "Kindergeld and the Kinderfreibetrag still apply. (Legal: "
                "26 U.S.C. § 24; § 32 Abs. 4 EStG)"
            ),
            "legal_refs": ("26 U.S.C. § 24", "§ 32 EStG"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/26/24",
                "https://www.gesetze-im-internet.de/estg/__32.html",
            ),
        },
        "ssn": {
            "tooltip": (
                "The child's U.S. Social Security Number, exactly 9 "
                "digits like 123-45-6789. Required for the Child Tax "
                "Credit ($2,200). Without an SSN the child can still "
                "qualify for the smaller Credit for Other Dependents "
                "($500) if they have an ITIN. (Legal: 26 U.S.C. "
                "§ 24(h)(7))"
            ),
            "legal_refs": ("26 U.S.C. § 24(h)(7)",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/24",),
        },
        "itin": {
            "tooltip": (
                "The child's U.S. Individual Taxpayer Identification "
                "Number (ITIN), exactly 9 digits like 9NN-NN-NNNN. Use "
                "this if the child is not eligible for an SSN but you "
                "still want to claim them. An ITIN unlocks the $500 "
                "Credit for Other Dependents but never the $2,200 Child "
                "Tax Credit. (Legal: 26 U.S.C. § 6109; 26 U.S.C. "
                "§ 24(h)(7))"
            ),
            "legal_refs": ("26 U.S.C. § 6109", "26 U.S.C. § 24(h)(7)"),
            "legal_urls": (
                "https://www.law.cornell.edu/uscode/text/26/6109",
                "https://www.law.cornell.edu/uscode/text/26/24",
            ),
        },
        "steuer_id": {
            "tooltip": (
                "The child's German tax ID (Steuer-ID), exactly 11 "
                "digits. The Familienkasse uses this to confirm "
                "Kindergeld payments and the Finanzamt uses it for the "
                "Kinderfreibetrag on Anlage Kind. Every German-resident "
                "child gets one automatically a few weeks after birth. "
                "(Legal: § 32 Abs. 6 EStG; § 139b AO)"
            ),
            "legal_refs": ("§ 32 Abs. 6 EStG", "§ 139b AO"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/estg/__32.html",
                "https://www.gesetze-im-internet.de/ao_1977/__139b.html",
            ),
        },
        "relationship": {
            "tooltip": (
                "Pick 'qualifying child' for sons, daughters, "
                "stepchildren, foster children, siblings, or descendants "
                "of any of those, who lived with you more than half the "
                "year and didn't pay for more than half their own "
                "support. Pick 'qualifying relative' for parents, "
                "grandparents, or other dependents who don't meet the "
                "qualifying-child rules but still depend on you "
                "financially. (Legal: 26 U.S.C. § 152)"
            ),
            "legal_refs": ("26 U.S.C. § 152",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/152",),
        },
        "months_in_household": {
            "tooltip": (
                "How many full months in the tax year the child lived "
                "in your German household, 0 through 12. Germany pays "
                "Kindergeld for every month the child was part of your "
                "household, even partial months. The IRS uses the "
                "matching U.S.-household months below for the "
                "qualifying-child residency test. (Legal: § 32 Abs. 1 "
                "EStG)"
            ),
            "legal_refs": ("§ 32 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__32.html",),
        },
        "months_in_us_household": {
            "tooltip": (
                "How many full months in the tax year the child lived "
                "in your U.S. household, 0 through 12. The IRS "
                "qualifying-child residency test wants more than half "
                "the year (so 7+ months). For a child living with you "
                "in Germany the whole year, this is normally 0 unless "
                "you also kept a U.S. home together. (Legal: 26 U.S.C. "
                "§ 152(c)(1)(B))"
            ),
            "legal_refs": ("26 U.S.C. § 152",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/152",),
        },
        "annual_gross_income_eur": {
            "tooltip": (
                "How much the child earned on their own during 2025, in "
                "euros. Wages, internships, freelance — anything that "
                "shows up on a Lohnsteuerbescheinigung or invoice. "
                "Germany uses this for adult-child Kindergeld eligibility "
                "(over 18 the rules tighten). Enter 0 if the child "
                "earned nothing. (Legal: § 32 Abs. 4 EStG)"
            ),
            "legal_refs": ("§ 32 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__32.html",),
        },
        "annual_gross_income_usd": {
            "tooltip": (
                "How much the child earned on their own during 2025, in "
                "U.S. dollars. The IRS qualifying-relative test caps the "
                "dependent's income at $5,200 for 2025; cross that line "
                "and the dependent claim disappears. Enter 0 if the "
                "child earned nothing. (Legal: 26 U.S.C. § 152(d)(1)(B))"
            ),
            "legal_refs": ("26 U.S.C. § 152",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/152",),
        },
        "kindergeld_received_eur": {
            "tooltip": (
                "How much Kindergeld the Familienkasse paid out for "
                "this child during 2025, in euros. The standard rate "
                "is €250 per month, so a full year is €3,000. The "
                "Finanzamt automatically picks the better of Kindergeld "
                "or the Kinderfreibetrag (Günstigerprüfung) for you — "
                "but we still need to know what was paid. (Legal: BKGG "
                "§ 6; § 31 EStG)"
            ),
            "legal_refs": ("BKGG § 6", "§ 31 EStG"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/bkgg_1996/__6.html",
                "https://www.gesetze-im-internet.de/estg/__31.html",
            ),
        },
        "kindergeld_recipient": {
            "tooltip": (
                "Pick who actually got the Kindergeld payments: the "
                "taxpayer, the spouse, the other parent (if you are "
                "separated), or 'none' if no Kindergeld was paid. "
                "Germany splits the half-Kinderfreibetrag between "
                "parents based on who received Kindergeld. (Legal: "
                "BKGG § 3; § 32 Abs. 6 EStG)"
            ),
            "legal_refs": ("BKGG § 3", "§ 32 EStG"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/bkgg_1996/__3.html",
                "https://www.gesetze-im-internet.de/estg/__32.html",
            ),
        },
        "disability_gdb": {
            "tooltip": (
                "If the child has a recognized German disability "
                "rating, type the percentage from their "
                "Schwerbehindertenausweis (20, 30, ... up to 100). "
                "Enter 100 for 'hilflos' or blind. Germany pays "
                "Kindergeld past age 25 if the child cannot support "
                "themselves due to a disability that began before 25. "
                "Enter 0 for no rating. (Legal: § 32 Abs. 4 Satz 1 "
                "Nr. 3 EStG; § 33b EStG)"
            ),
            "legal_refs": ("§ 32 EStG", "§ 33b EStG"),
            "legal_urls": (
                "https://www.gesetze-im-internet.de/estg/__32.html",
                "https://www.gesetze-im-internet.de/estg/__33b.html",
            ),
        },
    },
    "carryovers": {
        "us_passive_ftc_carryover_2024_usd": {
            "tooltip": (
                "Type the U.S. dollar amount of unused foreign tax "
                "credit you brought forward from your 2024 U.S. return "
                "in the 'passive' basket (mostly investment income). "
                "The IRS lets you carry unused credit forward for up to "
                "10 years. Look at your 2024 Form 1116 line 10. (Legal: "
                "26 U.S.C. § 904(c))"
            ),
            "legal_refs": ("26 U.S.C. § 904(c)",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/904",),
        },
        "us_general_ftc_carryover_2024_usd": {
            "tooltip": (
                "Type the U.S. dollar amount of unused foreign tax "
                "credit you brought forward from your 2024 U.S. return "
                "in the 'general' basket (mostly wages and active "
                "business income). The IRS lets you carry it forward "
                "for up to 10 years. (Legal: 26 U.S.C. § 904(c))"
            ),
            "legal_refs": ("26 U.S.C. § 904(c)",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/904",),
        },
        "us_short_term_capital_loss_carryover_2024_usd": {
            "tooltip": (
                "Type the U.S. dollar short-term capital loss you "
                "brought forward from 2024. 'Short-term' means assets "
                "you held for one year or less. The IRS lets you offset "
                "2025 gains with it; if you still have leftover loss, "
                "up to $3,000 ($1,500 if married filing separately) can "
                "reduce your other income. (Legal: 26 U.S.C. § 1212(b))"
            ),
            "legal_refs": ("26 U.S.C. § 1212(b)",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/1212",),
        },
        "us_long_term_capital_loss_carryover_2024_usd": {
            "tooltip": (
                "Type the U.S. dollar long-term capital loss you "
                "brought forward from 2024. 'Long-term' means assets "
                "you held for more than one year. Same rules as the "
                "short-term box: it offsets gains first, then up to "
                "$3,000 of other income per year. (Legal: 26 U.S.C. "
                "§ 1212(b))"
            ),
            "legal_refs": ("26 U.S.C. § 1212(b)",),
            "legal_urls": ("https://www.law.cornell.edu/uscode/text/26/1212",),
        },
        "de_stock_loss_carryforward_2024_eur": {
            "tooltip": (
                "Type the euros of unused stock losses you brought "
                "forward from 2024. Germany has a special rule: losses "
                "from selling individual stocks can only offset gains "
                "from selling individual stocks, never dividends or "
                "fund gains. (Legal: § 20 Abs. 6 Satz 4 EStG)"
            ),
            "legal_refs": ("§ 20 Abs. 6 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__20.html",),
        },
        "de_non_stock_loss_carryforward_2024_eur": {
            "tooltip": (
                "Type the euros of other unused capital losses you "
                "brought forward from 2024 (fund redemptions, bond "
                "losses, etc., but not single-stock losses). These can "
                "offset any 2025 investment income except gains from "
                "single stocks. (Legal: § 20 Abs. 6 Satz 1 EStG)"
            ),
            "legal_refs": ("§ 20 Abs. 6 EStG",),
            "legal_urls": ("https://www.gesetze-im-internet.de/estg/__20.html",),
        },
    },
}


SCREEN_NAMES = (
    "identity",
    "bank_accounts",
    "de_deductions",
    "vorabpauschale",
    "carryovers",
    "children",
)


# Map a field-key suffix to the currency it implies. Money fields end in
# ``_eur`` or ``_usd``; ``serialize_screen_metadata`` uses this to publish
# a currency hint so the frontend can render a matching marker.
_CURRENCY_BY_SUFFIX: tuple[tuple[str, str], ...] = (
    ("_eur", "EUR"),
    ("_usd", "USD"),
)


def _infer_currency_for_field(field_key: str) -> str:
    """Return 'EUR' or 'USD' for fields whose key ends with the matching
    suffix; '' for fields that are not money values."""

    for suffix, currency in _CURRENCY_BY_SUFFIX:
        if field_key.endswith(suffix):
            return currency
    return ""


def serialize_screen_metadata() -> dict[str, Any]:
    """Return tooltip + citation metadata for the frontend, JSON-safe.

    Money fields (those whose key ends with ``_eur`` or ``_usd``) carry a
    ``currency`` value of ``"EUR"`` or ``"USD"`` so the frontend can
    render a matching currency marker beside the input. Non-money fields
    carry an empty ``currency`` string so consumers can detect them
    uniformly.
    """

    out: dict[str, Any] = {}
    for screen, fields in SCREEN_TOOLTIPS.items():
        out[screen] = {
            key: {
                "tooltip": meta.get("tooltip", ""),
                "legal_refs": list(meta.get("legal_refs", ())),
                "legal_urls": list(meta.get("legal_urls", ())),
                "currency": meta.get("currency") or _infer_currency_for_field(key),
            }
            for key, meta in fields.items()
        }
    return out


# ---------------------------------------------------------------------------
# Helpers shared across screens.
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    # Atomic write (invariant I9 — unique temp filename + parent fsync)
    # so a concurrent partial-save or crash mid-write cannot leave a
    # torn JSON document on disk for the next screen-restore read.
    atomic_write_text(path, json.dumps(payload, indent=2) + "\n")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            {key: (value or "") for key, value in row.items() if key is not None}
            for row in csv.DictReader(handle)
        ]


def _write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    # Build CSV text in memory and atomic_write_text it (invariant I9)
    # so a crash or concurrent writer cannot leave a torn CSV on disk.
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    atomic_write_text(path, buffer.getvalue())


def _set_dotted(profile: dict[str, Any], dotted_key: str, value: Any) -> None:
    cursor: dict[str, Any] = profile
    segments = dotted_key.split(".")
    for segment in segments[:-1]:
        next_cursor = cursor.get(segment)
        if not isinstance(next_cursor, dict):
            next_cursor = {}
            cursor[segment] = next_cursor
        cursor = next_cursor
    cursor[segments[-1]] = value


def _get_dotted(profile: dict[str, Any], dotted_key: str) -> Any:
    cursor: Any = profile
    for segment in dotted_key.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return None
        cursor = cursor[segment]
    return cursor


def _stamp_save(paths: YearPaths, screen: str) -> None:
    """Write a per-screen last-saved timestamp into config/intake_progress.json."""

    progress_path = paths.config_root / "intake_progress.json"
    progress = _read_json(progress_path)
    progress.setdefault("screens", {})[screen] = {"last_saved_at": _now_iso()}
    _write_json(progress_path, progress)


def read_progress(paths: YearPaths) -> dict[str, Any]:
    """Return the cross-screen progress timestamps + per-screen completeness."""

    ensure_year_scaffold(paths)
    progress_path = paths.config_root / "intake_progress.json"
    progress = _read_json(progress_path)
    completeness = compute_completeness(paths)
    return {
        "screens": progress.get("screens", {}),
        "completeness": completeness,
    }


def compute_completeness(paths: YearPaths) -> dict[str, Any]:
    """Return a {screen: {filled: bool, ...}} summary so the toolbar can
    show a 'X of N sections filled' indicator. Conservative: a screen is
    'filled' if ANY field has been saved (i.e. on-disk file exists with
    non-default content)."""

    summary: dict[str, Any] = {}
    summary["identity"] = {
        "filled": _identity_filled(paths),
    }
    summary["bank_accounts"] = {
        "filled": (paths.config_root / "bank_accounts.csv").exists()
        and len(read_bank_accounts_state(paths).get("accounts", [])) > 0,
    }
    summary["de_deductions"] = {"filled": _de_deductions_filled(paths)}
    summary["vorabpauschale"] = {
        "filled": len(read_vorabpauschale_state(paths).get("funds", [])) > 0,
    }
    summary["carryovers"] = {"filled": _carryovers_filled(paths)}
    summary["children"] = {
        "filled": (paths.config_root / "children.csv").exists()
        and len(read_children_state(paths).get("children", [])) > 0,
    }
    filled_count = sum(1 for entry in summary.values() if entry.get("filled"))
    return {
        "by_screen": summary,
        "filled": filled_count,
        "total": len(summary),
    }


def _identity_filled(paths: YearPaths) -> bool:
    profile = _read_json(paths.profile_path)
    taxpayer = profile.get("taxpayer", {}) or {}
    if isinstance(taxpayer, dict) and taxpayer.get("name", "").strip():
        return True
    if isinstance(taxpayer, dict) and taxpayer.get("date_of_birth", "").strip():
        return True
    rows = _read_csv_rows(paths.people_path)
    for row in rows:
        if row.get("date_of_birth") or row.get("us_ssn_or_itin") or row.get("german_tax_id"):
            return True
    return False


def _de_deductions_filled(paths: YearPaths) -> bool:
    overrides = _read_json(paths.manual_overrides_path)
    deductions = overrides.get("deductions", {}) or {}
    wave3a = deductions.get("wave3a", {}) or {}
    return bool(wave3a)


def _carryovers_filled(paths: YearPaths) -> bool:
    overrides = _read_json(paths.manual_overrides_path)
    carry = overrides.get("carryovers", {}) or {}
    if any((carry.get("us_ftc") or {}).values()):
        return True
    if any((carry.get("us_capital") or {}).values()):
        return True
    de_loss = paths.facts_root / "de-loss-carryforwards.csv"
    if de_loss.exists():
        rows = _read_csv_rows(de_loss)
        for row in rows:
            value = row.get("value", "").strip()
            if value and value not in {"0", "0.00", "0.0"}:
                return True
    return False


# ---------------------------------------------------------------------------
# Screen 1 — Identity & Employment
# ---------------------------------------------------------------------------

CITIZENSHIP_OPTIONS = ("us_citizen", "us_green_card", "neither")
ITIN_OR_SSN_PATTERN = re.compile(r"^\d{9}$")
GERMAN_TAX_ID_PATTERN = re.compile(r"^\d{11}$")
ISO_3166_PATTERN = re.compile(r"^[A-Z]{2}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
POSTAL_PATTERN = re.compile(r"^[A-Za-z0-9 \-]{3,12}$")


def _validate_identity_person(person: dict[str, Any], role_label: str) -> dict[str, Any]:
    """Validate one person's identity submission. Empty / missing fields
    are allowed (partial save). Returns a normalized dict with stripped
    string values."""

    if not isinstance(person, dict):
        raise ScreenValidationError(
            f"We could not read the {role_label} block. Please use a JSON "
            "object with one entry per field, like {\"full_legal_name\": "
            "\"Jane Doe\"}."
        )

    cleaned: dict[str, Any] = {}
    for key in (
        "full_legal_name",
        "address_street",
        "address_city",
        "address_postal_code",
        "address_country",
        "us_ssn_or_itin",
        "german_tax_id",
        "date_of_birth",
        "citizenship_status",
        "employment_city",
        "employment_country",
    ):
        if key not in person:
            continue
        raw = person.get(key)
        value = "" if raw is None else str(raw).strip()
        cleaned[key] = value

    if cleaned.get("us_ssn_or_itin"):
        digits = cleaned["us_ssn_or_itin"].replace("-", "").replace(" ", "")
        if not ITIN_OR_SSN_PATTERN.match(digits):
            raise ScreenValidationError(
                f"{role_label}: U.S. SSN or ITIN must be exactly 9 digits, "
                f"like 123-45-6789. You entered {cleaned['us_ssn_or_itin']!r}. "
                "Please re-type the 9-digit number from your Social Security "
                "card or ITIN letter."
            )
        cleaned["us_ssn_or_itin"] = digits
    if cleaned.get("german_tax_id"):
        digits = cleaned["german_tax_id"].replace(" ", "").replace("-", "")
        if not GERMAN_TAX_ID_PATTERN.match(digits):
            raise ScreenValidationError(
                f"{role_label}: German Steuer-ID must be exactly 11 digits, "
                f"like 12345678901. You entered {cleaned['german_tax_id']!r}. "
                "Please re-type the 11-digit number from your "
                "Steuer-Identifikationsnummer letter. (Legal: § 139b AO)"
            )
        cleaned["german_tax_id"] = digits
    if cleaned.get("address_country"):
        if not ISO_3166_PATTERN.match(cleaned["address_country"].upper()):
            raise ScreenValidationError(
                f"{role_label}: address country must be a 2-letter country "
                f"code, like DE for Germany or US for the United States. "
                f"You entered {cleaned['address_country']!r}. Please use the "
                "ISO-3166 alpha-2 code."
            )
        cleaned["address_country"] = cleaned["address_country"].upper()
    if cleaned.get("employment_country"):
        if not ISO_3166_PATTERN.match(cleaned["employment_country"].upper()):
            raise ScreenValidationError(
                f"{role_label}: employment country must be a 2-letter "
                f"country code, like DE for Germany or US for the United "
                f"States. You entered {cleaned['employment_country']!r}. "
                "Please use the ISO-3166 alpha-2 code."
            )
        cleaned["employment_country"] = cleaned["employment_country"].upper()
    if cleaned.get("address_postal_code"):
        if not POSTAL_PATTERN.match(cleaned["address_postal_code"]):
            raise ScreenValidationError(
                f"{role_label}: postal code looks wrong "
                f"({cleaned['address_postal_code']!r}). Please use 5 digits "
                "for Germany (like 10115) or 5 or 9 digits for the U.S. "
                "(like 90210 or 90210-1234)."
            )
    if cleaned.get("date_of_birth"):
        if not DATE_PATTERN.match(cleaned["date_of_birth"]):
            raise ScreenValidationError(
                f"{role_label}: date of birth must be in YYYY-MM-DD format, "
                f"like 1985-03-12. You entered {cleaned['date_of_birth']!r}. "
                "Please re-type using 4-digit year, then month, then day "
                "with dashes."
            )
    if cleaned.get("citizenship_status"):
        if cleaned["citizenship_status"] not in CITIZENSHIP_OPTIONS:
            raise ScreenValidationError(
                f"{role_label}: citizenship_status must be one of "
                f"{list(CITIZENSHIP_OPTIONS)}. You entered "
                f"{cleaned['citizenship_status']!r}. Please pick "
                "'us_citizen', 'us_green_card', or 'neither'."
            )
    return cleaned


def read_identity_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current identity state for taxpayer + spouse."""

    ensure_year_scaffold(paths)
    profile = _read_json(paths.profile_path)
    people_rows = _read_csv_rows(paths.people_path)

    def _person_block(role: str) -> dict[str, str]:
        # Map role -> people.csv row by relationship_role.
        match = next(
            (row for row in people_rows if row.get("relationship_role") == role),
            None,
        )
        block_profile = profile.get(role, {}) if isinstance(profile.get(role), dict) else {}
        match = match or {}
        return {
            "full_legal_name": match.get("display_name", "")
            or block_profile.get("name", ""),
            "address_street": _get_dotted(profile, f"{role}.address.street") or "",
            "address_city": _get_dotted(profile, f"{role}.address.city") or "",
            "address_postal_code": _get_dotted(profile, f"{role}.address.postal_code") or "",
            "address_country": _get_dotted(profile, f"{role}.address.country") or "",
            "us_ssn_or_itin": match.get("us_ssn_or_itin", ""),
            "german_tax_id": match.get("german_tax_id", ""),
            "date_of_birth": match.get("date_of_birth", ""),
            "citizenship_status": _get_dotted(profile, f"{role}.citizenship_status") or "",
            "employment_city": _get_dotted(profile, f"{role}.employment_city") or "",
            "employment_country": _get_dotted(profile, f"{role}.employment_country") or "",
        }

    return {
        "taxpayer": _person_block("taxpayer"),
        "spouse": _person_block("spouse"),
    }


def write_identity_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a partial identity submission. Only fields present in the
    payload are written; on-disk fields not addressed in the payload are
    preserved."""

    ensure_year_scaffold(paths)

    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the identity submission. Please send a JSON "
            "object with 'taxpayer' and (optionally) 'spouse' blocks."
        )

    taxpayer_in = payload.get("taxpayer")
    spouse_in = payload.get("spouse")
    if taxpayer_in is None:
        taxpayer_in = {}
    if spouse_in is None:
        spouse_in = {}

    cleaned_taxpayer = _validate_identity_person(taxpayer_in, "taxpayer")
    cleaned_spouse = _validate_identity_person(spouse_in, "spouse")

    profile = _read_json(paths.profile_path)
    if not isinstance(profile, dict):
        profile = {}

    def _apply_to_profile(role: str, cleaned: dict[str, Any]) -> None:
        if not cleaned:
            return
        # Existing block to preserve unrelated fields.
        block = profile.get(role)
        if not isinstance(block, dict):
            block = {}
        # Field-by-field, only touch what the user submitted.
        if "full_legal_name" in cleaned:
            block["name"] = cleaned["full_legal_name"]
        if any(k in cleaned for k in ("address_street", "address_city", "address_postal_code", "address_country")):
            address = block.get("address")
            if not isinstance(address, dict):
                address = {}
            if "address_street" in cleaned:
                address["street"] = cleaned["address_street"]
            if "address_city" in cleaned:
                address["city"] = cleaned["address_city"]
            if "address_postal_code" in cleaned:
                address["postal_code"] = cleaned["address_postal_code"]
            if "address_country" in cleaned:
                address["country"] = cleaned["address_country"]
            block["address"] = address
        if "citizenship_status" in cleaned:
            block["citizenship_status"] = cleaned["citizenship_status"]
        if "employment_city" in cleaned:
            block["employment_city"] = cleaned["employment_city"]
        if "employment_country" in cleaned:
            block["employment_country"] = cleaned["employment_country"]
        if "date_of_birth" in cleaned:
            block["date_of_birth"] = cleaned["date_of_birth"]
        profile[role] = block

    _apply_to_profile("taxpayer", cleaned_taxpayer)
    _apply_to_profile("spouse", cleaned_spouse)

    # Update people.csv: merge by relationship_role, preserving columns
    # outside this screen's scope.
    people_rows = _read_csv_rows(paths.people_path)
    if not people_rows:
        # Synthesize a minimal person_1 row so identity edits have a home.
        people_rows = [
            {
                "person_id": "person_1",
                "display_name": "",
                "first_name": "",
                "last_name": "",
                "gender": "",
                "relationship_role": "taxpayer",
                "elster_order": "1",
                "us_filer": "true",
                "is_taxpayer": "true",
                "is_spouse": "false",
                "date_of_birth": "",
                "citizenship": "",
                "country_of_tax_residence": "",
                "german_tax_id": "",
                "us_ssn_or_itin": "",
                "nra_for_us_return": "false",
                "german_health_insurer": "",
                "german_statutory_health_with_sick_pay": "",
                "german_other_vorsorge_cap_eur": "",
                "church_tax_applicable": "",
            }
        ]

    def _merge_role(role: str, cleaned: dict[str, Any]) -> None:
        if not cleaned:
            return
        match = next((row for row in people_rows if row.get("relationship_role") == role), None)
        if match is None and role == "spouse":
            # Add a spouse row if the user is filling spouse identity.
            match = {
                "person_id": "person_2",
                "display_name": "",
                "first_name": "",
                "last_name": "",
                "gender": "",
                "relationship_role": "spouse",
                "elster_order": "2",
                "us_filer": "false",
                "is_taxpayer": "false",
                "is_spouse": "true",
                "date_of_birth": "",
                "citizenship": "",
                "country_of_tax_residence": "",
                "german_tax_id": "",
                "us_ssn_or_itin": "",
                "nra_for_us_return": "false",
                "german_health_insurer": "",
                "german_statutory_health_with_sick_pay": "",
                "german_other_vorsorge_cap_eur": "",
                "church_tax_applicable": "",
            }
            people_rows.append(match)
        if match is None:
            return
        if "full_legal_name" in cleaned:
            match["display_name"] = cleaned["full_legal_name"]
        if "us_ssn_or_itin" in cleaned:
            match["us_ssn_or_itin"] = cleaned["us_ssn_or_itin"]
        if "german_tax_id" in cleaned:
            match["german_tax_id"] = cleaned["german_tax_id"]
        if "date_of_birth" in cleaned:
            match["date_of_birth"] = cleaned["date_of_birth"]

    _merge_role("taxpayer", cleaned_taxpayer)
    _merge_role("spouse", cleaned_spouse)

    _write_csv(paths.people_path, PEOPLE_COLUMNS, people_rows)
    _write_json(paths.profile_path, profile)
    _stamp_save(paths, "identity")
    return read_identity_state(paths)


# ---------------------------------------------------------------------------
# Screen 2 — Bank accounts
# ---------------------------------------------------------------------------

BANK_ACCOUNTS_COLUMNS = [
    "label",
    "country",
    "account_number",
    "year_end_balance_usd",
    "linked_certificate_hash",
]


def _bank_accounts_path(paths: YearPaths) -> Path:
    return paths.config_root / "bank_accounts.csv"


def read_bank_accounts_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current bank-accounts list."""

    ensure_year_scaffold(paths)
    rows = _read_csv_rows(_bank_accounts_path(paths))
    accounts = [
        {
            "label": row.get("label", ""),
            "country": row.get("country", ""),
            "account_number": row.get("account_number", ""),
            "year_end_balance_usd": row.get("year_end_balance_usd", ""),
            "linked_certificate_hash": row.get("linked_certificate_hash", ""),
        }
        for row in rows
    ]
    return {"accounts": accounts}


def _validate_bank_account_row(row: dict[str, Any], index: int) -> dict[str, str]:
    if not isinstance(row, dict):
        raise ScreenValidationError(
            f"Bank account row {index}: we could not read this row. Please "
            "fill in the label, country, account number, and year-end "
            "balance, then try again."
        )
    cleaned: dict[str, str] = {col: "" for col in BANK_ACCOUNTS_COLUMNS}
    for key in BANK_ACCOUNTS_COLUMNS:
        raw = row.get(key)
        cleaned[key] = "" if raw is None else str(raw).strip()
    if cleaned["country"]:
        if not ISO_3166_PATTERN.match(cleaned["country"].upper()):
            raise ScreenValidationError(
                f"Bank account row {index}: country must be a 2-letter "
                f"country code, like DE for Germany or US for the United "
                f"States. You entered {cleaned['country']!r}. Please use "
                "the ISO-3166 alpha-2 code."
            )
        cleaned["country"] = cleaned["country"].upper()
    if cleaned["year_end_balance_usd"]:
        try:
            float(cleaned["year_end_balance_usd"])
        except ValueError as exc:
            raise ScreenValidationError(
                f"Bank account row {index}: year_end_balance_usd must be "
                f"a number in U.S. dollars, like 1234.56. You entered "
                f"{cleaned['year_end_balance_usd']!r}. Please enter the "
                "balance in USD without currency symbols or thousands "
                "separators."
            ) from exc
    return cleaned


def write_bank_accounts_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the bank-accounts list. Replaces the CSV (this is a list-
    editor screen, not a scalar-merge screen)."""

    ensure_year_scaffold(paths)
    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the bank-accounts submission. Please send a "
            "JSON object with an 'accounts' list of rows."
        )
    accounts = payload.get("accounts")
    if accounts is None:
        # Partial save: caller did not include the accounts list at all,
        # so leave the on-disk CSV alone.
        _stamp_save(paths, "bank_accounts")
        return read_bank_accounts_state(paths)
    if not isinstance(accounts, list):
        raise ScreenValidationError(
            "The 'accounts' field must be a list of bank-account rows. "
            "Please send an array, even if it is empty: \"accounts\": []."
        )
    cleaned = []
    for index, row in enumerate(accounts, start=1):
        cleaned.append(_validate_bank_account_row(row, index))
    # Drop fully-empty rows so the CSV stays tidy.
    cleaned = [
        row for row in cleaned
        if any(value for value in row.values())
    ]
    _write_csv(_bank_accounts_path(paths), BANK_ACCOUNTS_COLUMNS, cleaned)
    _stamp_save(paths, "bank_accounts")
    return read_bank_accounts_state(paths)


# ---------------------------------------------------------------------------
# Screen 3 — DE deductions input (Wave 3A coverage)
# ---------------------------------------------------------------------------

DE_DEDUCTIONS_NUMERIC_FIELDS = (
    "medical_expenses_eur",
    "charitable_donations_eur",
    "support_payments_eur",
    "support_recipient_income_eur",
    "arbeitszimmer_actual_costs_eur",
)
DE_DEDUCTIONS_INT_FIELDS = ("gdb", "taxpayer_birth_year")
DE_DEDUCTIONS_BOOL_FIELDS = (
    "hilflos_or_blind",
    "arbeitszimmer_claimed",
    "arbeitszimmer_qualifies_as_mittelpunkt",
)
DE_DEDUCTIONS_STRING_FIELDS = ("support_recipient_relationship",)
SUPPORT_RELATIONSHIPS = (
    "estranged_spouse",
    "divorced_spouse",
    "parent",
    "child_no_kindergeld",
)


def read_de_deductions_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current Wave-3A deduction inputs from manual_overrides."""

    ensure_year_scaffold(paths)
    overrides = _read_json(paths.manual_overrides_path)
    wave3a = (overrides.get("deductions", {}) or {}).get("wave3a", {}) or {}
    out: dict[str, Any] = {}
    for key in DE_DEDUCTIONS_NUMERIC_FIELDS + DE_DEDUCTIONS_INT_FIELDS + DE_DEDUCTIONS_STRING_FIELDS:
        out[key] = wave3a.get(key, "")
    for key in DE_DEDUCTIONS_BOOL_FIELDS:
        value = wave3a.get(key)
        if isinstance(value, bool):
            out[key] = value
        elif isinstance(value, str):
            out[key] = value.strip().lower() in {"true", "1", "yes"}
        else:
            out[key] = bool(value) if value not in (None, "") else False
    return out


def write_de_deductions_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a partial Wave-3A deduction submission into manual_overrides.json."""

    ensure_year_scaffold(paths)
    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the German-deductions submission. Please "
            "send a JSON object with one entry per field, like "
            "{\"medical_expenses_eur\": \"1234.56\"}."
        )

    overrides = _read_json(paths.manual_overrides_path)
    if not isinstance(overrides, dict):
        overrides = {}
    deductions = overrides.get("deductions")
    if not isinstance(deductions, dict):
        deductions = {}
    wave3a = deductions.get("wave3a")
    if not isinstance(wave3a, dict):
        wave3a = {}

    for key in DE_DEDUCTIONS_NUMERIC_FIELDS:
        if key not in payload:
            continue
        raw = payload[key]
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            wave3a[key] = ""
            continue
        try:
            float(str(raw))
        except ValueError as exc:
            raise ScreenValidationError(
                f"{key}: must be a number in euros (EUR), like 1234.56. "
                f"You entered {raw!r}. Please enter only digits and a "
                "decimal point, with no currency symbols or thousands "
                "separators."
            ) from exc
        wave3a[key] = str(raw).strip()

    for key in DE_DEDUCTIONS_INT_FIELDS:
        if key not in payload:
            continue
        raw = payload[key]
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            wave3a[key] = ""
            continue
        try:
            value = int(str(raw))
        except ValueError as exc:
            raise ScreenValidationError(
                f"{key}: must be a whole number, like 1985 or 50. You "
                f"entered {raw!r}. Please enter only digits with no decimal "
                "point."
            ) from exc
        if key == "gdb":
            if value != 0 and (value < 20 or value > 100 or value % 10 != 0):
                raise ScreenValidationError(
                    f"gdb (Grad der Behinderung): must be 0 (no rating) or "
                    "a multiple of 10 between 20 and 100, like 30, 50, or "
                    f"100. You entered {value}. Please use the percentage "
                    "from your Schwerbehindertenausweis. (Legal: § 33b "
                    "Abs. 3 EStG)"
                )
        if key == "taxpayer_birth_year":
            if value != 0 and (value < 1900 or value > 2100):
                raise ScreenValidationError(
                    f"Taxpayer birth year: must be a 4-digit calendar "
                    f"year, like 1985. You entered {value}. Please enter "
                    "your full year of birth."
                )
        wave3a[key] = value

    for key in DE_DEDUCTIONS_BOOL_FIELDS:
        if key not in payload:
            continue
        raw = payload[key]
        if isinstance(raw, bool):
            wave3a[key] = raw
        elif isinstance(raw, str):
            wave3a[key] = raw.strip().lower() in {"true", "1", "yes", "y"}
        else:
            wave3a[key] = bool(raw) if raw not in (None, "") else False

    if "support_recipient_relationship" in payload:
        raw = payload["support_recipient_relationship"]
        value = "" if raw is None else str(raw).strip()
        if value and value not in SUPPORT_RELATIONSHIPS:
            raise ScreenValidationError(
                f"support_recipient_relationship: must be one of "
                f"{list(SUPPORT_RELATIONSHIPS)}. You entered {value!r}. "
                "Please pick the option that matches your legal duty of "
                "support (estranged spouse, divorced spouse, parent, or "
                "adult child no longer eligible for Kindergeld). "
                "(Legal: § 33a Abs. 1 EStG)"
            )
        wave3a["support_recipient_relationship"] = value

    if wave3a.get("arbeitszimmer_actual_costs_eur") and not wave3a.get("arbeitszimmer_qualifies_as_mittelpunkt"):
        # Allowed but flagged — engine will fall back to Jahrespauschale.
        # We do not raise; we only require the field be storable.
        pass

    deductions["wave3a"] = wave3a
    overrides["deductions"] = deductions
    _write_json(paths.manual_overrides_path, overrides)
    _stamp_save(paths, "de_deductions")
    return read_de_deductions_state(paths)


# ---------------------------------------------------------------------------
# Screen 4 — Vorabpauschale per-fund inputs
# ---------------------------------------------------------------------------

VORABPAUSCHALE_COLUMNS = [
    "symbol",
    "fund_name",
    "nav_start_eur",
    "nav_end_eur",
    "ausschuettung_eur",
    "months_held",
    "fund_classification",
]
FUND_CLASSIFICATIONS = (
    "aktienfonds",
    "mischfonds",
    "immobilien_deutsch",
    "immobilien_auslaendisch",
    "sonstige",
)


def _vorabpauschale_path(paths: YearPaths) -> Path:
    return paths.reference_data_root / "de-vorabpauschale-inputs-2025.csv"


def read_vorabpauschale_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current per-fund Vorabpauschale list."""

    ensure_year_scaffold(paths)
    rows = _read_csv_rows(_vorabpauschale_path(paths))
    funds = []
    for row in rows:
        funds.append(
            {
                "symbol": row.get("symbol", ""),
                "fund_name": row.get("fund_name", ""),
                "nav_start_eur": row.get("nav_start_eur", ""),
                "nav_end_eur": row.get("nav_end_eur", ""),
                "ausschuettung_eur": row.get("ausschuettung_eur", ""),
                "months_held": row.get("months_held", ""),
                "fund_classification": row.get("fund_classification", ""),
            }
        )
    return {"funds": funds}


def _validate_vorabpauschale_row(row: dict[str, Any], index: int) -> dict[str, str]:
    if not isinstance(row, dict):
        raise ScreenValidationError(
            f"Fund row {index}: we could not read this row. Please fill in "
            "the symbol, fund name, NAV start and end (EUR), distributions "
            "(EUR), months held, and fund class, then try again."
        )
    cleaned: dict[str, str] = {col: "" for col in VORABPAUSCHALE_COLUMNS}
    for key in VORABPAUSCHALE_COLUMNS:
        raw = row.get(key)
        cleaned[key] = "" if raw is None else str(raw).strip()
    _eur_label = {
        "nav_start_eur": "NAV start (EUR)",
        "nav_end_eur": "NAV end (EUR)",
        "ausschuettung_eur": "distributions (EUR)",
    }
    for key in ("nav_start_eur", "nav_end_eur", "ausschuettung_eur"):
        if cleaned[key]:
            try:
                float(cleaned[key])
            except ValueError as exc:
                raise ScreenValidationError(
                    f"Fund row {index}: {_eur_label[key]} must be a number "
                    f"in euros, like 1234.56. You entered "
                    f"{cleaned[key]!r}. Please enter only digits and a "
                    "decimal point, with no currency symbols or thousands "
                    "separators."
                ) from exc
    if cleaned["months_held"]:
        try:
            months = int(cleaned["months_held"])
        except ValueError as exc:
            raise ScreenValidationError(
                f"Fund row {index}: months_held must be a whole number "
                f"between 0 and 12. You entered {cleaned['months_held']!r}. "
                "Please enter how many full months you held this fund "
                "during the year (0 if you sold before holding a full "
                "month)."
            ) from exc
        if months < 0 or months > 12:
            raise ScreenValidationError(
                f"Fund row {index}: months_held must be a whole number "
                f"between 0 and 12. You entered {months}. Please enter "
                "the number of full months in the calendar year. (Legal: "
                "InvStG § 18 Abs. 2)"
            )
    if cleaned["fund_classification"] and cleaned["fund_classification"] not in FUND_CLASSIFICATIONS:
        raise ScreenValidationError(
            f"Fund row {index}: fund_classification must be one of "
            f"{list(FUND_CLASSIFICATIONS)}. You entered "
            f"{cleaned['fund_classification']!r}. Please pick the "
            "category that matches the fund: 'aktienfonds' for stock "
            "funds, 'mischfonds' for mixed, 'immobilien_deutsch' or "
            "'immobilien_auslaendisch' for real-estate funds, "
            "'sonstige' for everything else."
        )
    return cleaned


def write_vorabpauschale_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the per-fund list. Replaces the CSV (list-editor)."""

    ensure_year_scaffold(paths)
    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the Vorabpauschale submission. Please send "
            "a JSON object with a 'funds' list of rows."
        )
    funds = payload.get("funds")
    if funds is None:
        _stamp_save(paths, "vorabpauschale")
        return read_vorabpauschale_state(paths)
    if not isinstance(funds, list):
        raise ScreenValidationError(
            "The 'funds' field must be a list of fund rows. Please send "
            "an array, even if it is empty: \"funds\": []."
        )
    cleaned = []
    for index, row in enumerate(funds, start=1):
        cleaned.append(_validate_vorabpauschale_row(row, index))
    cleaned = [row for row in cleaned if row.get("symbol")]
    _write_csv(_vorabpauschale_path(paths), VORABPAUSCHALE_COLUMNS, cleaned)
    _stamp_save(paths, "vorabpauschale")
    return read_vorabpauschale_state(paths)


# ---------------------------------------------------------------------------
# Screen 5 — Prior-year carryovers
# ---------------------------------------------------------------------------

CARRYOVER_US_FTC_FIELDS = (
    "us_passive_ftc_carryover_2024_usd",
    "us_general_ftc_carryover_2024_usd",
)
CARRYOVER_US_CAPITAL_FIELDS = (
    "us_short_term_capital_loss_carryover_2024_usd",
    "us_long_term_capital_loss_carryover_2024_usd",
)
CARRYOVER_DE_FIELDS = (
    "de_stock_loss_carryforward_2024_eur",
    "de_non_stock_loss_carryforward_2024_eur",
)


def _de_loss_carry_path(paths: YearPaths) -> Path:
    return paths.facts_root / "de-loss-carryforwards.csv"


def read_carryovers_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current carryover values from disk."""

    ensure_year_scaffold(paths)
    overrides = _read_json(paths.manual_overrides_path)
    carry = overrides.get("carryovers", {}) or {}
    us_ftc = carry.get("us_ftc", {}) or {}
    us_capital = carry.get("us_capital", {}) or {}
    out: dict[str, Any] = {}
    for key in CARRYOVER_US_FTC_FIELDS:
        out[key] = us_ftc.get(key, "")
    for key in CARRYOVER_US_CAPITAL_FIELDS:
        out[key] = us_capital.get(key, "")

    # DE side comes from de-loss-carryforwards.csv.
    de_rows = _read_csv_rows(_de_loss_carry_path(paths))
    by_key = {row.get("key", ""): row.get("value", "") for row in de_rows}
    out["de_stock_loss_carryforward_2024_eur"] = by_key.get("stock_loss_carryforward_2024_eur", "")
    out["de_non_stock_loss_carryforward_2024_eur"] = by_key.get(
        "private_sale_loss_carryforward_2024_eur", ""
    )
    return out


def write_carryovers_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a partial carryover submission. US fields go into manual_overrides.json
    (carryovers.us_ftc / carryovers.us_capital); DE fields go into
    de-loss-carryforwards.csv (preserving existing rows)."""

    ensure_year_scaffold(paths)
    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the carryovers submission. Please send a "
            "JSON object with one entry per carryover field, like "
            "{\"us_passive_ftc_carryover_2024_usd\": \"500.00\"}."
        )

    def _coerce_money(value: Any, label: str) -> str:
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return ""
        try:
            float(str(value))
        except ValueError as exc:
            currency = "USD" if label.endswith("_usd") else (
                "EUR" if label.endswith("_eur") else "the listed currency"
            )
            raise ScreenValidationError(
                f"{label}: must be a number in {currency}, like 1234.56. "
                f"You entered {value!r}. Please enter only digits and a "
                "decimal point, with no currency symbols or thousands "
                "separators. Carryovers can be 0 if you have nothing to "
                "carry forward."
            ) from exc
        return str(value).strip()

    overrides = _read_json(paths.manual_overrides_path)
    if not isinstance(overrides, dict):
        overrides = {}
    carry = overrides.get("carryovers")
    if not isinstance(carry, dict):
        carry = {}

    us_ftc = carry.get("us_ftc")
    if not isinstance(us_ftc, dict):
        us_ftc = {}
    for key in CARRYOVER_US_FTC_FIELDS:
        if key in payload:
            us_ftc[key] = _coerce_money(payload[key], key)
    carry["us_ftc"] = us_ftc

    us_capital = carry.get("us_capital")
    if not isinstance(us_capital, dict):
        us_capital = {}
    for key in CARRYOVER_US_CAPITAL_FIELDS:
        if key in payload:
            us_capital[key] = _coerce_money(payload[key], key)
    carry["us_capital"] = us_capital

    overrides["carryovers"] = carry
    _write_json(paths.manual_overrides_path, overrides)

    # DE side: merge into de-loss-carryforwards.csv preserving existing rows.
    de_rows = _read_csv_rows(_de_loss_carry_path(paths))
    by_key: dict[str, dict[str, str]] = {row.get("key", ""): dict(row) for row in de_rows}
    de_columns = ["section", "key", "value", "source", "note"]

    if "de_stock_loss_carryforward_2024_eur" in payload:
        value = _coerce_money(payload["de_stock_loss_carryforward_2024_eur"], "de_stock_loss_carryforward_2024_eur")
        existing = by_key.get(
            "stock_loss_carryforward_2024_eur",
            {
                "section": "germany",
                "key": "stock_loss_carryforward_2024_eur",
                "value": "",
                "source": "intake_wizard",
                "note": "§ 20 Abs. 6 Satz 4 EStG single-stock-loss carryforward.",
            },
        )
        existing["value"] = value or "0.00"
        existing["section"] = existing.get("section") or "germany"
        existing["source"] = existing.get("source") or "intake_wizard"
        existing["note"] = existing.get("note") or "§ 20 Abs. 6 Satz 4 EStG single-stock-loss carryforward."
        by_key["stock_loss_carryforward_2024_eur"] = existing

    if "de_non_stock_loss_carryforward_2024_eur" in payload:
        value = _coerce_money(
            payload["de_non_stock_loss_carryforward_2024_eur"],
            "de_non_stock_loss_carryforward_2024_eur",
        )
        existing = by_key.get(
            "private_sale_loss_carryforward_2024_eur",
            {
                "section": "germany",
                "key": "private_sale_loss_carryforward_2024_eur",
                "value": "",
                "source": "intake_wizard",
                "note": "§ 20 Abs. 6 Satz 1 EStG non-stock capital-loss carryforward.",
            },
        )
        existing["value"] = value or "0.00"
        existing["section"] = existing.get("section") or "germany"
        existing["source"] = existing.get("source") or "intake_wizard"
        existing["note"] = existing.get("note") or "§ 20 Abs. 6 Satz 1 EStG non-stock capital-loss carryforward."
        by_key["private_sale_loss_carryforward_2024_eur"] = existing

    if by_key:
        _write_csv(_de_loss_carry_path(paths), de_columns, list(by_key.values()))

    _stamp_save(paths, "carryovers")
    return read_carryovers_state(paths)


# ---------------------------------------------------------------------------
# Screen 6 — Children & Dependents
#
# One row per child in ``config/children.csv``. The engine consumes this CSV
# directly to compute the U.S. Child Tax Credit / Credit for Other Dependents
# (26 U.S.C. § 24, § 152) and the German Kinderfreibetrag / Kindergeld
# Günstigerprüfung (§ 31, § 32 EStG; BKGG § 6). An empty file (header only)
# means no children, which the engine reads as zero credits / zero
# Freibeträge.
# ---------------------------------------------------------------------------

CHILDREN_COLUMNS = [
    "child_id",
    "name",
    "date_of_birth",
    "ssn",
    "itin",
    "steuer_id",
    "relationship",
    "months_in_household",
    "months_in_us_household",
    "annual_gross_income_eur",
    "annual_gross_income_usd",
    "kindergeld_received_eur",
    "kindergeld_recipient",
    "disability_gdb",
]
CHILD_RELATIONSHIPS = ("qualifying_child", "qualifying_relative")
KINDERGELD_RECIPIENTS = ("taxpayer", "spouse", "other_parent", "none")

# A 9-digit ITIN starts with 9; otherwise the same shape as an SSN. We accept
# either bare 9 digits or the standard NNN-NN-NNNN with hyphens.
_SSN_DIGITS_PATTERN = re.compile(r"^\d{9}$")
_STEUER_ID_DIGITS_PATTERN = re.compile(r"^\d{11}$")


def _children_path(paths: YearPaths) -> Path:
    return paths.config_root / "children.csv"


def _us_filing_posture_from_disk(paths: YearPaths) -> str:
    """Read the household's U.S. filing posture from profile.json. Returns
    "" when not yet set, "single", "married_joint", "mfs_nra_spouse", etc.
    Only used to decide whether SSN/ITIN is required for qualifying-child
    rows; never for legal math."""

    profile = _read_json(paths.profile_path)
    if not isinstance(profile, dict):
        return ""
    jurisdictions = profile.get("jurisdictions") or {}
    usa = jurisdictions.get("usa") if isinstance(jurisdictions, dict) else {}
    if not isinstance(usa, dict):
        return ""
    if not usa.get("enabled", False):
        return ""
    return str(usa.get("filing_posture", "") or "").strip()


def read_children_state(paths: YearPaths) -> dict[str, Any]:
    """Return the current children list."""

    ensure_year_scaffold(paths)
    rows = _read_csv_rows(_children_path(paths))
    children = [
        {column: row.get(column, "") for column in CHILDREN_COLUMNS}
        for row in rows
    ]
    return {"children": children}


def _validate_child_row(
    row: dict[str, Any],
    index: int,
    *,
    require_us_id: bool,
) -> dict[str, str]:
    if not isinstance(row, dict):
        raise ScreenValidationError(
            f"Child row {index}: we could not read this row. Please fill "
            "in at least the child's name, date of birth, and "
            "relationship, then try again."
        )
    cleaned: dict[str, str] = {col: "" for col in CHILDREN_COLUMNS}
    for key in CHILDREN_COLUMNS:
        raw = row.get(key)
        cleaned[key] = "" if raw is None else str(raw).strip()

    if not cleaned["name"]:
        raise ScreenValidationError(
            f"Child row {index}: the name is required. Please type the "
            "child's full legal name as it appears on their Social "
            "Security card or German Steuer-ID letter."
        )

    if cleaned["date_of_birth"]:
        if not DATE_PATTERN.match(cleaned["date_of_birth"]):
            raise ScreenValidationError(
                f"Child row {index}: the date of birth must be in "
                f"YYYY-MM-DD format, like 2018-09-12. You entered "
                f"{cleaned['date_of_birth']!r}. Please re-type using "
                "4-digit year, then month, then day with dashes."
            )
        try:
            parsed_dob = datetime.strptime(cleaned["date_of_birth"], "%Y-%m-%d")
        except ValueError as exc:
            raise ScreenValidationError(
                f"Child row {index}: the date of birth "
                f"{cleaned['date_of_birth']!r} is not a real calendar "
                "date. Please pick a valid year, month, and day."
            ) from exc
        current_year = datetime.now(timezone.utc).year
        if parsed_dob.year < 1900 or parsed_dob.year > current_year:
            raise ScreenValidationError(
                f"Child row {index}: the date of birth year must be "
                f"between 1900 and {current_year}. You entered "
                f"{cleaned['date_of_birth']!r}. Please re-type the "
                "child's actual year of birth."
            )

    def _normalize_us_id(value: str, label: str) -> str:
        digits = value.replace("-", "").replace(" ", "")
        if not _SSN_DIGITS_PATTERN.match(digits):
            raise ScreenValidationError(
                f"Child row {index}: an {label} is exactly 9 digits, "
                f"like 123-45-6789. You entered {value!r}. Please "
                f"re-type the 9-digit number from the child's "
                f"{label} card or letter."
            )
        return digits

    if cleaned["ssn"]:
        cleaned["ssn"] = _normalize_us_id(cleaned["ssn"], "SSN")
    if cleaned["itin"]:
        cleaned["itin"] = _normalize_us_id(cleaned["itin"], "ITIN")

    if cleaned["steuer_id"]:
        digits = cleaned["steuer_id"].replace("-", "").replace(" ", "")
        if not _STEUER_ID_DIGITS_PATTERN.match(digits):
            raise ScreenValidationError(
                f"Child row {index}: a German Steuer-ID is exactly 11 "
                f"digits, like 12345678901. You entered "
                f"{cleaned['steuer_id']!r}. Please re-type the 11-digit "
                "number from the child's Steuer-Identifikationsnummer "
                "letter. (Legal: § 139b AO)"
            )
        cleaned["steuer_id"] = digits

    if cleaned["relationship"]:
        if cleaned["relationship"] not in CHILD_RELATIONSHIPS:
            raise ScreenValidationError(
                f"Child row {index}: relationship must be one of "
                f"{list(CHILD_RELATIONSHIPS)}. You entered "
                f"{cleaned['relationship']!r}. Please pick "
                "'qualifying_child' for sons, daughters, stepchildren, "
                "foster children, siblings, or descendants of any of "
                "those, or 'qualifying_relative' for parents, "
                "grandparents, and other dependents who depend on you "
                "financially. (Legal: 26 U.S.C. § 152)"
            )

    # If the household is filing a U.S. return AND the child is a
    # qualifying child, the IRS needs at least an SSN or an ITIN to
    # link the dependent to the return (26 U.S.C. § 152(g)). We fail
    # closed in the intake layer rather than letting the engine
    # silently drop the credit.
    if (
        require_us_id
        and cleaned["relationship"] == "qualifying_child"
        and not cleaned["ssn"]
        and not cleaned["itin"]
    ):
        raise ScreenValidationError(
            f"Child row {index}: the household is filing a U.S. return "
            "and this is a qualifying child, so an SSN or an ITIN is "
            "required. An SSN unlocks the $2,200 Child Tax Credit; an "
            "ITIN unlocks the $500 Credit for Other Dependents. Please "
            "type whichever 9-digit number the child has. (Legal: "
            "26 U.S.C. § 24(h)(7); 26 U.S.C. § 152)"
        )

    for key in ("months_in_household", "months_in_us_household"):
        if cleaned[key]:
            try:
                months = int(cleaned[key])
            except ValueError as exc:
                raise ScreenValidationError(
                    f"Child row {index}: {key} must be a whole number "
                    f"between 0 and 12. You entered {cleaned[key]!r}. "
                    "Please enter how many full months in the year the "
                    "child lived in your household."
                ) from exc
            if months < 0 or months > 12:
                raise ScreenValidationError(
                    f"Child row {index}: {key} must be between 0 and "
                    f"12. You entered {months}. Please enter the number "
                    "of full months in the calendar year (January is 1, "
                    "December is 12)."
                )
            cleaned[key] = str(months)

    for key in (
        "annual_gross_income_eur",
        "annual_gross_income_usd",
        "kindergeld_received_eur",
    ):
        if cleaned[key]:
            currency = "EUR" if key.endswith("_eur") else "USD"
            try:
                amount = float(cleaned[key])
            except ValueError as exc:
                raise ScreenValidationError(
                    f"Child row {index}: {key} must be a number in "
                    f"{currency}, like 1234.56. You entered "
                    f"{cleaned[key]!r}. Please enter only digits and a "
                    "decimal point, with no currency symbols or "
                    "thousands separators."
                ) from exc
            if amount < 0:
                raise ScreenValidationError(
                    f"Child row {index}: {key} must be 0 or greater. "
                    f"You entered {cleaned[key]!r}. Negative income / "
                    "Kindergeld is not a valid input — enter 0 if the "
                    "child earned nothing or no Kindergeld was paid."
                )

    if cleaned["kindergeld_recipient"]:
        if cleaned["kindergeld_recipient"] not in KINDERGELD_RECIPIENTS:
            raise ScreenValidationError(
                f"Child row {index}: kindergeld_recipient must be one "
                f"of {list(KINDERGELD_RECIPIENTS)}. You entered "
                f"{cleaned['kindergeld_recipient']!r}. Please pick "
                "'taxpayer', 'spouse', 'other_parent' (if you are "
                "separated), or 'none' if no Kindergeld was paid. "
                "(Legal: BKGG § 3)"
            )

    kindergeld_amount_str = cleaned["kindergeld_received_eur"]
    if kindergeld_amount_str:
        kg_amount = float(kindergeld_amount_str)
        recipient = cleaned["kindergeld_recipient"]
        if kg_amount > 0 and recipient in ("", "none"):
            raise ScreenValidationError(
                f"Child row {index}: kindergeld_received_eur is "
                f"{kindergeld_amount_str} but kindergeld_recipient is "
                f"{recipient!r}. If Kindergeld was actually paid, please "
                "pick who received it (taxpayer, spouse, or other "
                "parent). If no Kindergeld was paid, set the amount to "
                "0. (Legal: BKGG § 3)"
            )
        if kg_amount == 0 and recipient not in ("", "none"):
            raise ScreenValidationError(
                f"Child row {index}: kindergeld_recipient is "
                f"{recipient!r} but kindergeld_received_eur is 0. "
                "Either set the amount to the actual euros paid, or "
                "change the recipient to 'none'. (Legal: BKGG § 3)"
            )

    if cleaned["disability_gdb"]:
        try:
            gdb = int(cleaned["disability_gdb"])
        except ValueError as exc:
            raise ScreenValidationError(
                f"Child row {index}: disability_gdb must be a whole "
                f"number between 0 and 100. You entered "
                f"{cleaned['disability_gdb']!r}. Please use the "
                "percentage from the Schwerbehindertenausweis (20, 30, "
                "... up to 100), or 0 if the child has no rating. "
                "(Legal: § 33b EStG)"
            ) from exc
        if gdb < 0 or gdb > 100:
            raise ScreenValidationError(
                f"Child row {index}: disability_gdb must be between 0 "
                f"and 100. You entered {gdb}. Please use the percentage "
                "from the child's Schwerbehindertenausweis. (Legal: "
                "§ 33b EStG)"
            )
        cleaned["disability_gdb"] = str(gdb)

    return cleaned


def write_children_state(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the children list. Replaces the CSV (list-editor pattern,
    same as bank_accounts and vorabpauschale). Validation runs in memory;
    only when every row passes do we touch disk."""

    # Read the U.S.-filing posture BEFORE ensure_year_scaffold runs,
    # because the scaffold re-syncs profile.json from people.csv /
    # elections.csv on every invocation and would clobber an explicit
    # profile edit (e.g., a Germany-only household that toggled
    # jurisdictions.usa.enabled = false directly on the profile).
    require_us_id = _us_filing_posture_from_disk(paths) != ""

    ensure_year_scaffold(paths)
    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the children submission. Please send a "
            "JSON object with a 'children' list of rows."
        )
    children = payload.get("children")
    if children is None:
        # Partial save: caller did not include the list at all, leave
        # the on-disk CSV alone (matches bank_accounts / vorabpauschale).
        _stamp_save(paths, "children")
        return read_children_state(paths)
    if not isinstance(children, list):
        raise ScreenValidationError(
            "The 'children' field must be a list of child rows. Please "
            "send an array, even if it is empty: \"children\": []."
        )
    cleaned: list[dict[str, str]] = []
    for index, row in enumerate(children, start=1):
        cleaned.append(
            _validate_child_row(row, index, require_us_id=require_us_id)
        )
    # Drop fully-empty rows so the CSV stays tidy. A child row with only
    # ``child_id`` (auto-generated) but no name was never really filled.
    cleaned = [
        row for row in cleaned
        if any(row.get(col, "") for col in CHILDREN_COLUMNS if col != "child_id")
    ]
    # Auto-assign ``child_id`` for rows that don't have one so the engine
    # can join to per-child posture entries by stable id.
    for index, row in enumerate(cleaned, start=1):
        if not row.get("child_id"):
            row["child_id"] = f"child_{index}"

    _write_csv(_children_path(paths), CHILDREN_COLUMNS, cleaned)
    _stamp_save(paths, "children")
    return read_children_state(paths)


# ---------------------------------------------------------------------------
# Save-all-progress helper.
# ---------------------------------------------------------------------------
SCREEN_HANDLERS = {
    "identity": (read_identity_state, write_identity_state),
    "bank_accounts": (read_bank_accounts_state, write_bank_accounts_state),
    "de_deductions": (read_de_deductions_state, write_de_deductions_state),
    "vorabpauschale": (read_vorabpauschale_state, write_vorabpauschale_state),
    "carryovers": (read_carryovers_state, write_carryovers_state),
    "children": (read_children_state, write_children_state),
}


def save_all_progress(paths: YearPaths, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a multi-screen payload in one shot. Each top-level key
    must match a known screen; the value is forwarded to the per-screen
    write_*_state. Validation errors abort the whole batch."""

    if not isinstance(payload, dict):
        raise ScreenValidationError(
            "We could not read the save-all submission. Please send a JSON "
            "object whose top-level keys are screen names like 'identity' "
            "or 'bank_accounts'."
        )
    results: dict[str, Any] = {}
    for screen, body in payload.items():
        if screen not in SCREEN_HANDLERS:
            raise ScreenValidationError(
                f"Unknown screen name: {screen!r}. Please use one of "
                f"{sorted(SCREEN_HANDLERS.keys())}."
            )
        if body is None:
            continue
        _, writer = SCREEN_HANDLERS[screen]
        results[screen] = writer(paths, body)
    return {"saved": results, "progress": read_progress(paths)}


__all__ = [
    "BANK_ACCOUNTS_COLUMNS",
    "CARRYOVER_DE_FIELDS",
    "CARRYOVER_US_CAPITAL_FIELDS",
    "CARRYOVER_US_FTC_FIELDS",
    "CHILDREN_COLUMNS",
    "CHILD_RELATIONSHIPS",
    "CITIZENSHIP_OPTIONS",
    "DE_DEDUCTIONS_BOOL_FIELDS",
    "DE_DEDUCTIONS_INT_FIELDS",
    "DE_DEDUCTIONS_NUMERIC_FIELDS",
    "DE_DEDUCTIONS_STRING_FIELDS",
    "FUND_CLASSIFICATIONS",
    "KINDERGELD_RECIPIENTS",
    "SCREEN_HANDLERS",
    "SCREEN_NAMES",
    "SCREEN_TOOLTIPS",
    "SUPPORT_RELATIONSHIPS",
    "ScreenValidationError",
    "VORABPAUSCHALE_COLUMNS",
    "compute_completeness",
    "read_bank_accounts_state",
    "read_carryovers_state",
    "read_children_state",
    "read_de_deductions_state",
    "read_identity_state",
    "read_progress",
    "read_vorabpauschale_state",
    "save_all_progress",
    "serialize_screen_metadata",
    "write_bank_accounts_state",
    "write_carryovers_state",
    "write_children_state",
    "write_de_deductions_state",
    "write_identity_state",
    "write_vorabpauschale_state",
]
