from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tax_pipeline.fact_extraction import (
    DocumentFacts,
    FactRecord,
    extract_all_facts,
    extract_document_facts_from_pages,
    write_document_facts,
)
from tax_pipeline.manifest import write_manifest
from tax_pipeline.paths import YearPaths
from tax_pipeline.providers.base import CallableDocumentHandler
from tax_pipeline.providers.registry import ProviderRegistry
from tax_pipeline.providers.shared.document import DocumentDescriptor


LOHNSTEUER_PAGE = """Electronic certificate of wage tax deduction for 2025
1. Period of certification
01.01.-31.12.
3. Gross wage incl. benefits in kind
171.80061
4. Withheld wage tax from 3
42.97194
5. Withheld solidarity surcharge from 3
37770
10. Multiannual wage, compensations, e.g.
dismissal pay (included in 3, excl. 9)
29.49309
22. Employer contribution / subsidy to statutory pension insurance
8.98380
23. Employee contribution to statutory pension insurance
8.98380
25. Employee contributions to statutory health insurance
11.27868
26. Employee contributions to statutory nursing care insurance
2.77836
27. Employee contributions to statutory unemployment insurance
1.25580
"""

LOHNSTEUER_GERMAN_PAGE = """Ausdruck der elektronischen Lohnsteuerbescheinigung für 2025
1. Bescheinigungszeitraum                                               vom - bis
                                                                         01.01.-28.12.
3. Bruttoarbeitslohn einschl. Sachbezüge
                                                                            14.73663
4. Einbehaltene Lohnsteuer von 3.
                                                                             1.48354
5. Einbehaltener Solidaritätszuschlag von 3.
6. Einbehaltene Kirchensteuer des Arbeitnehmers
8. In 3. enthaltene Versorgungsbezüge
9. Versorgungsbezüge für mehrere Kalenderjahre
10. Arbeitslohn für mehrere Kalenderjahre, Entschädigungen z.B.
    Abfindungen (in 3. enthalten, ohne 9.)
11. unbesetzt
22. Arbeitgeberanteil / -zuschuss zur gesetzlichen Rentenversicherung
                                                                             1.47983
23. Arbeitnehmerbeitrag zur gesetzlichen Rentenversicherung
                                                                             1.04573
25. Arbeitnehmerbeitrag zur gesetzlichen Krankenversicherung
                                                                               95857
26. Arbeitnehmerbeitrag zur sozialen Pflegeversicherung
                                                                               28389
27. Arbeitnehmerbeitrag zur Arbeitslosenversicherung
                                                                               14617
"""

VERLUST_PAGE = """Bescheid
über die gesonderte Feststellung des verbleibenden Verlustvortrags
zur Einkommensteuer auf den 31.12.2024
§ 10d Abs. 4 EStG festgestellt für die Einkünfte aus
Kapitalvermögen (Veräußerung von Aktien) auf
2.101
privaten Veräußerungsgeschäften auf
869
"""

VERLUST_PAGE_REAL = """über
die gesonderte            Feststellung
des   verbleibenden Verlustvortrags
zur Einkommensteuer
auf    den    31.12.2024

Der verbleibende Verlustvortrag wird nach
 § 10d Abs. 4 EStG festgestellt für die Einkünfte aus
   Kapitalvermögen (Veräußerung von Aktien) auf                                                     2.101
   privaten Veräußerungsgeschäften auf                                                                869
"""

STEUERBESCHEID_PAGE_1 = """Bescheid für 2024
über
Einkommensteuer
und
Solidaritätszuschlag

Festgesetzt werden                                                                           52.915,00                       1.848,62
ab Steuerabzug vom Lohn                                                                      47.435,00                         846,45

verbleibende Steuer                                                                           5.480,00                       1.002,17

Bitte zahlen Sie
spätestens am 03 .12.2025                                                                     5.480,00                       1.002,17

Den Gesamtbetrag von 6.482,17 € zahlen Sie bitte bis zum
angegebenen Fälligkeitstag auf eines der angeführten Konten.
"""

PREPAYMENT_PAGE = """Transfer Confirmation

Transfer Type                                         Amount

Instant bank transfer                                 5.000,00 EUR

Value Date                                            Booking Date

01.12.2025                                            01.12.2025

Reference text

ESt-VZ 4.Quartal 2025 16/064/13281
"""

N26_TRANSFER_PAGE = """Transfer Confirmation

TRANSFER DETAILS

Transfer Type                                         Amount
Instant bank transfer                                 5.000,00 EUR

Value Date                                            Booking Date
01.12.2025                                            01.12.2025

Transaction ID                                        Fee
O-d137bb257fe939ca94cdf14eeb74b81c                    0,00 EUR

Reference text
ESt-VZ 4.Quartal 2025 16/064/13281

SENDER DETAILS
ALEX EXAMPLE

RECIPIENT DETAILS
DAS FINANZAMT

N26 Bank SE Voltairestraße 8, 10179 Berlin, Germany                            Issued on   11.04.2026
"""

SCHWAB_TRANSACTIONS_CSV = """Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount
12/31/2025,Cash Dividend,QQQE,DIREXION NASDAQ 100 ETF,,,,$3.63
12/31/2025,Cash Dividend,QQQ,INVSC QQQ TRUST SRS 1 ETF,,,,$28.59
12/30/2025,Credit Interest,,SCHWAB1 INT 11/26-12/29,,,,$3.92
12/30/2025,Buy,PLTR,PALANTIR TECHNOLOGIES INCLASS A,5,$181.93,,-$909.65
"""

SCHWAB_TRANSACTIONS_CSV_AS_OF = """Date,Action,Symbol,Description,Quantity,Price,Fees & Comm,Amount
07/11/2025 as of 07/10/2025,Cash Dividend,QQQ,INVSC QQQ TRUST SRS 1 ETF,,,,$28.59
"""

SCHWAB_1099_CSV = """Account,XXXX-X273
Tax Year,2025

"Form 1099DIV",
"Corrected","Yes",
"Box","Description","Amount","Total","Details",
"1a","Total Ordinary Dividends (Includes amount shown in box 1b)","","$9596.58","",
"1b","Qualified Dividends","$1624.17","","",
"2a","Total Capital Gain Distributions (Includes amounts shown in boxes 2b 2c and 2d)","","$1219.90","",
"3","Nondividend Distributions","","$475.51","",
"7","Foreign Tax Paid","","$50.09","",
"8","Foreign Country or U.S. Possession","","","VARIOUS",
"Form 1099INT",
"Box","Description","Amount","Total","Details",
"1","Interest Income","","$12.25","",
"Form 1099MISC",
"Box","Description","Amount","Total","Details",
"8","Substitute payments in lieu of dividends or interest","","$105.26","",
"Form 1099 B",
"1a","1b","1c","1d",
"Description of property (Example 100 sh. XYZ Co.)","Date acquired","Date sold or disposed","Proceeds",
"16.00 PALANTIR TECHNOLOGIES INCLASS            CLASS A","Various","02/21/2025","1699.15",
"19.00 TESLA INC","Various","02/24/2025","6197.82",
"""

COINBASE_TRANSACTIONS_CSV = """
Transactions
User,ALEX EXAMPLE,a95e2b40-b426-5e5e-b6d0-1b23a6e09703
ID,Timestamp,Transaction Type,Asset,Quantity Transacted,Price Currency,Price at Transaction,Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes
695467c4002f83090bd2641b,2025-12-31 00:01:08 UTC,Staking Income,SOL,0.000225734006,USD,$124.595,$0.02813,$0.02813,$0.00,
695467c4002f83090bd2641c,2025-01-01 10:00:00 UTC,Buy,BTC,0.01000000,USD,$43000.00,$430.00,$430.00,$0.00,
"""

COINBASE_1099_DA_PAGE_2 = """Form 1099-DA
SUMMARY OF ACTIVITY

Summary For Trading

Cost basis source                                               Term                                    Total proceeds                       Total cost basis    Total gains/losses

Coinbase                                                        Short                                       $ 7,190.90                            $ 11,753.43          -$ 4,562.53
Not available                                                   Short                                          $ 70.35                              Unknown              Unknown
Coinbase                                                        Long                                       $ 17,147.62                            $ 22,564.21          -$ 5,416.59

Total¹                                                                                                    $ 24,408.87                             $ 34,317.64          -$ 9,979.12
"""

SCHWAB_PAGE_3 = """Form 1099-DIV
1a     Total Ordinary Dividends                                                     $            9,596.58
1b       Qualified Dividends                                                        $            1,624.17
2a     Total Capital Gain Distributions                                             $            1,219.90
3      Nondividend Distributions                                                    $              475.51
7      Foreign Tax Paid                                                             $               50.09
"""

SCHWAB_PAGE_5 = """Form 1099-INT
1      Interest Income                                                              $               12.25
"""

SCHWAB_PAGE_7 = """Form 1099-MISC
8      Substitute Payments in Lieu of Dividends or Interest                         $              105.26
"""

SCHWAB_PAGE_90 = """Foreign Tax Paid and Income Summary
Total Foreign Tax Paid and Income
(50.09)
626.74
"""

JPM_PAGE_1 = """Tax Information for Account 2508170-UK
Statement Date
29-Jan-2026
SUMMARY of PROCEEDS, GAINS & LOSSES, ADJUSTMENTS AND WITHHOLDING 1099-B
Short
A (basis reported to the IRS)
Proceeds
29,700.38
Cost basis
28,947.54
Net gain or loss(-)
752.84
"""

US_1040_PACKET_PAGE_1 = """U.S. FEDERAL – FORM 1040
Prepared for:        Mr. Alex Example
Income tax payable: US$ 8,470
Filing deadline:     June 16, 2025

Form   1040 U.S. Individual Income Tax Return 2024
Filing Status                Married filing separately (MFS)
If you checked the HOH or QSS box, enter the child’s name if the
qualifying person is a child but not your dependent: SAM EXAMPLE NRA
Digital Assets               Yes          No
1h   Other earned income                                                          185,476.
1z   Add lines 1a through 1h                                                     185,476.
2a   Tax-exempt interest .          2a                                  b Taxable interest            2b               3,539.
3a   Qualified dividends .          3a            3,047.                b Ordinary dividends          3b              13,279.
"""

US_1040_PACKET_REAL_LAYOUT = """Filing Status                Single                                                                                         Head of household (HOH)
                              Married filing jointly (even if only one had income)
 Check only
 one box.                       Married filing separately (MFS)                                        Qualifying surviving spouse (QSS)
                           If you checked the MFS box, enter the name of your spouse. If you checked the HOH or QSS box, enter the child’s name if the
                           qualifying person is a child but not your dependent: SAM EXAMPLE NRA
 Income               1a      Total amount from Form(s) W-2, box 1 (see instructions) . . . . .
                          h   Other earned income (see instructions) . . . .                   .   .   .     .      .   .     .   . .     .    .     .   .   .       1h             185,476.
                          z   Add lines 1a through 1h    . . . . . . . .                       .   .   .     .      .   .     .   . .     .    .     .   .   .        1z            185,476.
 Attach Sch. B        2a      Tax-exempt interest .          .   .     2a                                  b Taxable interest   .              .     .   .   .       2b               3,539.
 if required.         3a      Qualified dividends .          .   .     3a            3,047.                b Ordinary dividends .              .     .   .   .       3b              13,279.
"""

US_8879_PAGE_1 = """U.S. FEDERAL – FORM 8879
Prepared for:         Mr. Alex Example
Signed and dated
by:                   Mr. Alex Example
Income tax payable: US$ 4,288
Late payment penalty + interest: $30
Total: $4,318
Filing deadline:      June 16, 2025

Part I         Tax Return Information — Tax Year Ending December 31,                                 2024 (Enter year you are authorizing.)
1    Adjusted gross income . . . . . . . . . . . . . . .                                1          205,294.
2    Total tax . . . . . . . . . . . . . . . . . . . .                                  2            4,288.
5    Amount you owe . . . . . . . . . . . . . . . . .                                   4,288..         5
"""

US_8879_REAL_LAYOUT = """Prepared for:         Mr. Alex Example
                      .

Signed and dated      Mr. Alex Example
by:

Income tax payable: US$ 4,288
                    Late payment penalty + interest: $30
                    Total: $4,318
Filing deadline:      June 16, 2025
"""

SHAREWORKS_NO_RECORDS_PAGE = """No records found

Page 1 of 1
"""

SHAREWORKS_STATEMENT_PAGE_1 = """Account Statement
Published Date:    2026-02-17

Muriel Siebert & Co., Inc
Account Number
AA841002CC0009001D6279

Statement Period                    2025-10-01   to 2025-12-31

Current Statement Reference         316527

Account Transactions
Instrument                      Transaction Type       Quantity             Price      Side         Value           Commissions & Fees        Transaction Date   Settlement Date
Delivery Hero SE                Share Release             352.00   EUR 17.233696        Buy                                  EUR 0.00               2025-11-10        2025-11-10
Delivery Hero SE                Share Sale                177.00   EUR 17.233696        Sell     EUR 3,050.36            EUR (6.72)                 2025-11-10        2025-11-12
Delivery Hero SE                Free Share              0.000441   EUR 16.130558        Buy                                  EUR 0.00               2025-11-20        2025-11-20
EUR                             Tax                                                             EUR (3,033.13)               EUR 0.00               2025-11-24
EUR                             Participant
Payment                                                         EUR (10.51)                 EUR 0.00               2025-11-24
Delivery Hero SE                Share Sale                808.00   EUR 22.658465        Sell    EUR 18,308.04           EUR (40.28)                 2025-12-23        2025-12-30
"""

SHAREWORKS_SUMMARY_PAGE = """Alex Example
Account Summary
Summary Period: 15-Jun-2023 to 17-Jun-2025
Account Number: CS-E154B8-12
Company: Delivery Hero SE

Account Summary
                                                          Total Value                 Available Value
(RSU) LTIP 2.0                                           €31,400.70                        €7,861.31
Delivery Hero ESPP Global                                 €3,963.20                        €3,963.20
Vested Share Holdings Account                            €26,278.60                       €26,278.60
Total                                                    €61,642.50                       €38,103.11
"""

SOCIAL_NOTICE_PAGE = """Meldebescheinigung zur Sozialversicherung                                                               Datum:  12.01.2026
                                                                              Pers.-Nr.            Erstellungs-/Übermittlungsdatum
                                                                               00148                12.01.2026 / 10:31
                                                                              Versicherungsnummer                 Geburtsdatum
                                                                               25101294B551
     ArabiCo GmbH*Reichenberger Str. 36*10999 Berlin
     *Pers.-Nr. 00148*
     Sam Example
     c/o Example Household
Grund der Abgabe                                       30            Abmeldung wegen Ende der Beschäftigung
Betriebs-Nr. Krankenkasse/Einzugsstelle                15027365      EK   Techniker Krankenkasse
Betriebs-Nr. Arbeitgeber                               94928684
Staatsangehörigkeit                                    432           vietnamesisch
"""

SOCIAL_NOTICE_REAL_LAYOUT = """Meldebescheinigung zur Sozialversicherung                                                               Datum:  12.01.2026
                                                                              Pers.-Nr.            Erstellungs-/Übermittlungsdatum
                                                                               00148                12.01.2026 / 10:31
                                                                              Versicherungsnummer                 Geburtsdatum
                                                                               25101294B551
     ArabiCo GmbH*Reichenberger Str. 36*10999 Berlin                          Geburtsname (falls Versicherungsnummer unbekannt)

                                                                   SV
     *Pers.-Nr. 00148*                                             A9F        Geburtsort (falls Versicherungsnr. unbekannt)


                                                                              Geschlecht (falls Versicherungsnr. unbekannt)
     Sam Example
     c/o Example Household
Grund der Abgabe                                       30            Abmeldung wegen Ende der Beschäftigung
Betriebs-Nr. Krankenkasse/Einzugsstelle                15027365      EK   Techniker Krankenkasse
Betriebs-Nr. Arbeitgeber                               94928684
Staatsangehörigkeit                                    432           vietnamesisch
"""

SCHWAB_LIMITATION_OCR = """Only 4 prior years of data are available. Select a starting date no earlier than 04/11/2022
Date range From (mm/dd/yyyy) To (mm/dd/yyyy) Symbol (Optional)
Cannot be earlier than 04/11/2022
"""

AMAZON_ORDER_DETAILS_PAGE = """Order Summary
Order placed 1 December 2025         Order No. 304-3794232-9113914

Payment method                                             Order Summary
MasterCard •••• 4239                                       Item(s) Subtotal:    €35.28
Estimated VAT:        €6.70
Total:               €41.98
Grand Total:         €41.98

FIFINE XLR Streaming Microphone for Podcast Studio, USB Dynamic Microphone
Gaming PC with Mute Button, for PS4/5 Mac Mixer Sound Cards
Sold by: Amazon.de
"""

AMAZON_INVOICE_PAGE = """Rechnung
Zahlungsreferenznummer 1EP4RAB2yLTckgx8PYwt
Verkauft von Amazon EU S.à r.l., Niederlassung Deutschland

Rechnungsdatum
/Lieferdatum                        13 Februar 2025
Rechnungsnummer                     LU5R3O01AEUI
Zahlbetrag                          26,74 €

Bestelldatum                                12 Februar 2025
Bestellnummer                               302-3739720-9782732

Rechnungsdetails
Somehow We Manage: AKA - The Practical Manager’s Guide to the Galaxy                                    1               24,99 €         7%          26,74 €                    26,74 €
ASIN: B0DWGFNG9Z
"""

DONATION_RECEIPT_EML = """Subject: Thanks for Donating to Example Charity Org
From: Example Charity Org <receipts@mail2.donorbox.org>
Content-Type: text/html; charset=utf-8

<html><body>
Dear Alex Example,
This is a receipt for your gracious donation to Example Charity Org.
Organization: <b>Example Charity Org</b><br />
Campaign: <b>Support Example Charity Org</b><br />
Donor Name: <b>Alex Example</b><br />
Amount: <b>$104.43</b><br />
Donation Interval: <b>One-time</b><br />
Receipt #: <b>62232748</b><br />
Donated At: <b>29/12/2025 14:50:35 CET</b><br />
Payment Method: <b>MasterCard 3634</b><br />
</body></html>
"""


class ExtractDocumentFactsTest(unittest.TestCase):
    def test_descriptor_backed_dispatch_uses_registry_handler(self) -> None:
        registry = ProviderRegistry()
        descriptor = DocumentDescriptor(
            provider="schwab",
            document_family="transactions",
            format="csv",
            doc_type="schwab_transactions_csv",
            owner="person_1",
            tax_year=2025,
            country_of_origin="US",
            confidence="high",
        )
        registry.register(
            "schwab",
            "transactions",
            "csv",
            CallableDocumentHandler(
                lambda relative_path, pages: DocumentFacts(
                    relative_path=relative_path.as_posix(),
                    doc_type="schwab_transactions_csv",
                    parser="deterministic.test_registry.v1",
                    status="ok",
                    facts=[],
                    warnings=[f"rows={len(pages)}"],
                )
            ),
        )

        doc = extract_document_facts_from_pages(
            relative_path=Path("brokers/2025-Individual_XXX273_Transactions_schwab.csv"),
            doc_type="schwab_transactions_csv",
            pages=[SCHWAB_TRANSACTIONS_CSV],
            descriptor=descriptor,
            registry=registry,
        )

        self.assertEqual(doc.parser, "deterministic.test_registry.v1")
        self.assertEqual(doc.provider, "schwab")
        self.assertEqual(doc.document_family, "transactions")
        self.assertEqual(doc.country_of_origin, "US")
        self.assertEqual(doc.warnings, ["rows=1"])

    def test_extracts_lohnsteuer_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/Certificate of wage tax deduction 2025 12 December.pdf"),
            doc_type="german_lohnsteuer_pdf",
            pages=[LOHNSTEUER_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["period_certification"].value, "01.01.-31.12.")
        self.assertEqual(facts["gross_wage_eur"].value, "171800.61")
        self.assertEqual(facts["withheld_wage_tax_eur"].value, "42971.94")
        self.assertEqual(facts["withheld_solidarity_surcharge_eur"].value, "377.70")
        self.assertEqual(facts["multiannual_wage_eur"].value, "29493.09")
        self.assertEqual(facts["employer_pension_contribution_eur"].value, "8983.80")
        self.assertEqual(facts["employee_pension_contribution_eur"].value, "8983.80")
        self.assertEqual(facts["employee_health_insurance_eur"].value, "11278.68")
        self.assertEqual(facts["employee_nursing_care_insurance_eur"].value, "2778.36")
        self.assertEqual(facts["employee_unemployment_insurance_eur"].value, "1255.80")
        self.assertEqual(facts["gross_wage_eur"].source["page"], 1)

    def test_extracts_german_lohnsteuer_variant(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/person_2_Lohnsteuerbescheinigung_122025_260410_210646.pdf"),
            doc_type="german_lohnsteuer_pdf",
            pages=[LOHNSTEUER_GERMAN_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["period_certification"].value, "01.01.-28.12.")
        self.assertEqual(facts["gross_wage_eur"].value, "14736.63")
        self.assertEqual(facts["withheld_wage_tax_eur"].value, "1483.54")
        self.assertEqual(facts["withheld_solidarity_surcharge_eur"].value, "0.00")
        self.assertEqual(facts["multiannual_wage_eur"].value, "0.00")
        self.assertEqual(facts["employer_pension_contribution_eur"].value, "1479.83")
        self.assertEqual(facts["employee_pension_contribution_eur"].value, "1045.73")
        self.assertEqual(facts["employee_health_insurance_eur"].value, "958.57")
        self.assertEqual(facts["employee_nursing_care_insurance_eur"].value, "283.89")
        self.assertEqual(facts["employee_unemployment_insurance_eur"].value, "146.17")
        self.assertEqual(doc.warnings, [])

    def test_extracts_verlustvortrag_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/ESt-Verlustvortrag-Bescheid 2024.pdf"),
            doc_type="german_verlustvortrag_pdf",
            pages=[VERLUST_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["loss_carryforward_stock_sales_eur"].value, "2101")
        self.assertEqual(facts["loss_carryforward_private_sales_eur"].value, "869")
        self.assertEqual(facts["loss_carryforward_as_of"].value, "31.12.2024")

    def test_extracts_verlustvortrag_real_heading_shape(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/ESt-Verlustvortrag-Bescheid 2024.pdf"),
            doc_type="german_verlustvortrag_pdf",
            pages=[VERLUST_PAGE_REAL],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["loss_carryforward_as_of"].value, "31.12.2024")
        self.assertEqual(facts["loss_carryforward_stock_sales_eur"].value, "2101")

    def test_extracts_steuerbescheid_summary_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/ESt-Bescheid inkl. VZ 2024.pdf"),
            doc_type="german_steuerbescheid_pdf",
            pages=[STEUERBESCHEID_PAGE_1],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["assessed_income_tax_eur"].value, "52915.00")
        self.assertEqual(facts["assessed_solidarity_surcharge_eur"].value, "1848.62")
        self.assertEqual(facts["withheld_income_tax_credit_eur"].value, "47435.00")
        self.assertEqual(facts["withheld_solidarity_credit_eur"].value, "846.45")
        self.assertEqual(facts["residual_income_tax_eur"].value, "5480.00")
        self.assertEqual(facts["residual_solidarity_surcharge_eur"].value, "1002.17")
        self.assertEqual(facts["amount_due_total_eur"].value, "6482.17")
        self.assertEqual(facts["payment_due_date"].value, "03.12.2025")

    def test_extracts_german_prepayment_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/TV2025-prepay-5000-finanzampt.pdf"),
            doc_type="german_prepayment_pdf",
            pages=[PREPAYMENT_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["payment_amount_eur"].value, "5000.00")
        self.assertEqual(facts["value_date"].value, "01.12.2025")
        self.assertEqual(facts["booking_date"].value, "01.12.2025")
        self.assertEqual(facts["reference_text"].value, "ESt-VZ 4.Quartal 2025 16/064/13281")

    def test_extracts_schwab_transactions_csv_summary(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("brokers/2025-Individual_XXX273_Transactions_schwab.csv"),
            doc_type="schwab_transactions_csv",
            pages=[SCHWAB_TRANSACTIONS_CSV],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["transaction_row_count"].value, "4")
        self.assertEqual(facts["first_transaction_date"].value, "2025-12-30")
        self.assertEqual(facts["last_transaction_date"].value, "2025-12-31")
        self.assertEqual(facts["distinct_action_count"].value, "3")

    def test_extracts_schwab_1099_csv_summary(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("brokers/1099-2025-XXXX-X273.CSV"),
            doc_type="schwab_1099_csv",
            pages=[SCHWAB_1099_CSV],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["ordinary_dividends_box_1a_usd"].value, "9596.58")
        self.assertEqual(facts["qualified_dividends_box_1b_usd"].value, "1624.17")
        self.assertEqual(facts["foreign_tax_paid_box_7_usd"].value, "50.09")
        self.assertEqual(facts["interest_income_box_1_usd"].value, "12.25")
        self.assertEqual(facts["substitute_payments_box_8_usd"].value, "105.26")
        self.assertEqual(facts["form_1099_b_row_count"].value, "2")

    def test_extracts_schwab_transactions_csv_as_of_date_variant(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("brokers/2025-Individual_XXX273_Transactions_schwab.csv"),
            doc_type="schwab_transactions_csv",
            pages=[SCHWAB_TRANSACTIONS_CSV_AS_OF],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["first_transaction_date"].value, "2025-07-11")
        self.assertEqual(facts["last_transaction_date"].value, "2025-07-11")

    def test_extracts_coinbase_transactions_csv_summary(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("crypto/coinbase-transactions-2025.csv"),
            doc_type="coinbase_transactions_csv",
            pages=[COINBASE_TRANSACTIONS_CSV],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["user_name"].value, "ALEX EXAMPLE")
        self.assertEqual(facts["transaction_row_count"].value, "2")
        self.assertEqual(facts["first_transaction_timestamp"].value, "2025-01-01 10:00:00 UTC")
        self.assertEqual(facts["last_transaction_timestamp"].value, "2025-12-31 00:01:08 UTC")
        self.assertEqual(facts["distinct_transaction_type_count"].value, "2")

    def test_extracts_coinbase_1099_da_summary_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("crypto/coinbase-1099-DA.pdf"),
            doc_type="coinbase_1099_da_pdf",
            pages=["", COINBASE_1099_DA_PAGE_2],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["short_term_proceeds_usd"].value, "7190.90")
        self.assertEqual(facts["short_term_cost_basis_usd"].value, "11753.43")
        self.assertEqual(facts["short_term_gain_or_loss_usd"].value, "-4562.53")
        self.assertEqual(facts["long_term_proceeds_usd"].value, "17147.62")
        self.assertEqual(facts["total_proceeds_usd"].value, "24408.87")
        self.assertEqual(facts["total_cost_basis_usd"].value, "34317.64")
        self.assertEqual(facts["total_gain_or_loss_usd"].value, "-9979.12")

    def test_extracts_schwab_1099_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("brokers/1099 Composite and Year-End Summary - 2025_273.PDF"),
            doc_type="schwab_1099_pdf",
            pages=["", "", SCHWAB_PAGE_3, "", SCHWAB_PAGE_5, "", SCHWAB_PAGE_7] + [""] * 82 + [SCHWAB_PAGE_90],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["ordinary_dividends_box_1a_usd"].value, "9596.58")
        self.assertEqual(facts["qualified_dividends_box_1b_usd"].value, "1624.17")
        self.assertEqual(facts["capital_gain_distributions_box_2a_usd"].value, "1219.90")
        self.assertEqual(facts["interest_income_box_1_usd"].value, "12.25")
        self.assertEqual(facts["substitute_payments_box_8_usd"].value, "105.26")
        self.assertEqual(facts["foreign_source_income_summary_usd"].value, "626.74")
        self.assertEqual(facts["ordinary_dividends_box_1a_usd"].source["page"], 3)
        self.assertEqual(facts["foreign_source_income_summary_usd"].source["page"], 90)

    def test_extracts_jpm_1099_summary_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("equity_comp/JPM-1099Statement.pdf"),
            doc_type="jpm_1099_pdf",
            pages=[JPM_PAGE_1],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["account_number"].value, "2508170-UK")
        self.assertEqual(facts["statement_date"].value, "29-Jan-2026")
        self.assertEqual(facts["short_term_type_a_proceeds_usd"].value, "29700.38")
        self.assertEqual(facts["short_term_type_a_cost_basis_usd"].value, "28947.54")
        self.assertEqual(facts["short_term_type_a_net_gain_usd"].value, "752.84")
        self.assertEqual(doc.warnings, [])

    def test_extracts_shareworks_no_records_marker(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("equity_comp/Shareworks/Shareworks - Capital Gain Overview.pdf"),
            doc_type="shareworks_statement_pdf",
            pages=[SHAREWORKS_NO_RECORDS_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["report_result"].value, "no_records_found")

    def test_extracts_shareworks_statement_summary(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("equity_comp/Shareworks/Statement (1).pdf"),
            doc_type="shareworks_statement_pdf",
            pages=[SHAREWORKS_STATEMENT_PAGE_1, SHAREWORKS_SUMMARY_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["account_number"].value, "AA841002CC0009001D6279")
        self.assertEqual(facts["statement_period_start"].value, "2025-10-01")
        self.assertEqual(facts["statement_period_end"].value, "2025-12-31")
        self.assertEqual(facts["transaction_row_count"].value, "6")
        self.assertEqual(facts["company_name"].value, "Delivery Hero SE")
        self.assertEqual(facts["summary_total_value_eur"].value, "61642.50")

    def test_extracts_amazon_order_details_invoice_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("receipts/Order Details.pdf"),
            doc_type="expense_invoice",
            pages=[AMAZON_ORDER_DETAILS_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["document_variant"].value, "amazon_order_details")
        self.assertEqual(facts["order_number"].value, "304-3794232-9113914")
        self.assertEqual(facts["order_date"].value, "2025-12-01")
        self.assertEqual(facts["seller_name"].value, "Amazon.de")
        self.assertEqual(facts["total_amount_eur"].value, "41.98")

    def test_extracts_amazon_rechnung_invoice_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("receipts/management-book-invoice.pdf"),
            doc_type="expense_invoice",
            pages=[AMAZON_INVOICE_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["document_variant"].value, "amazon_rechnung")
        self.assertEqual(facts["invoice_number"].value, "LU5R3O01AEUI")
        self.assertEqual(facts["invoice_date"].value, "2025-02-13")
        self.assertEqual(facts["order_number"].value, "302-3739720-9782732")
        self.assertEqual(facts["total_amount_eur"].value, "26.74")

    def test_extracts_donation_receipt_email_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("receipts/Thanks for Donating to Example Charity Org.eml"),
            doc_type="donation_receipt_eml",
            pages=[DONATION_RECEIPT_EML],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["organization_name"].value, "Example Charity Org")
        self.assertEqual(facts["donor_name"].value, "Alex Example")
        self.assertEqual(facts["donation_amount_usd"].value, "104.43")
        self.assertEqual(facts["receipt_number"].value, "62232748")
        self.assertEqual(facts["payment_method"].value, "MasterCard 3634")

    def test_extracts_n26_transfer_confirmation_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/TY2024-additional-6000.pdf"),
            doc_type="n26_transfer_confirmation_pdf",
            pages=[N26_TRANSFER_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["transfer_type"].value, "Instant bank transfer")
        self.assertEqual(facts["amount_eur"].value, "5000.00")
        self.assertEqual(facts["booking_date"].value, "01.12.2025")
        self.assertEqual(facts["sender_name"].value, "ALEX EXAMPLE")
        self.assertEqual(facts["issued_on"].value, "11.04.2026")

    def test_extracts_us_1040_packet_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/1040-2024-Alex-Example-final.pdf"),
            doc_type="us_1040_packet_pdf",
            pages=[US_1040_PACKET_PAGE_1],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["prepared_for"].value, "Mr. Alex Example")
        self.assertEqual(facts["cover_income_tax_payable_usd"].value, "8470.00")
        self.assertEqual(facts["cover_filing_deadline"].value, "2025-06-16")
        self.assertEqual(facts["mfs_spouse_name"].value, "SAM EXAMPLE NRA")
        self.assertEqual(facts["form_1040_line_3b_ordinary_dividends_usd"].value, "13279.00")

    def test_extracts_us_1040_packet_real_layout_lines(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/1040-2024-Alex-Example-final.pdf"),
            doc_type="us_1040_packet_pdf",
            pages=[US_1040_PACKET_REAL_LAYOUT],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(facts["form_1040_line_1h_other_earned_income_usd"].value, "185476.00")
        self.assertEqual(facts["form_1040_line_1z_total_income_usd"].value, "185476.00")

    def test_extracts_us_8879_packet_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/8879-2024-Alex-Example-final.pdf"),
            doc_type="us_8879_pdf",
            pages=[US_8879_PAGE_1],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["prepared_for"].value, "Mr. Alex Example")
        self.assertEqual(facts["signed_by"].value, "Mr. Alex Example")
        self.assertEqual(facts["cover_total_due_usd"].value, "4318.00")
        self.assertEqual(facts["agi_usd"].value, "205294.00")
        self.assertEqual(facts["amount_owed_usd"].value, "4288.00")

    def test_extracts_us_8879_signed_by_real_layout(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/8879-2024-Alex-Example-final.pdf"),
            doc_type="us_8879_pdf",
            pages=[US_8879_REAL_LAYOUT],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(facts["signed_by"].value, "Mr. Alex Example")

    def test_extracts_german_social_notice_facts(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/person_2-social-2025.pdf"),
            doc_type="german_social_insurance_notice_pdf",
            pages=[SOCIAL_NOTICE_PAGE],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["notice_date"].value, "12.01.2026")
        self.assertEqual(facts["personnel_number"].value, "00148")
        self.assertEqual(facts["employee_name"].value, "Sam Example")
        self.assertEqual(facts["employer_name"].value, "ArabiCo GmbH")
        self.assertEqual(facts["health_insurer_name"].value, "Techniker Krankenkasse")

    def test_extracts_german_social_notice_real_layout(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/person_2-social-2025.pdf"),
            doc_type="german_social_insurance_notice_pdf",
            pages=[SOCIAL_NOTICE_REAL_LAYOUT],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(facts["created_or_transmitted_at"].value, "12.01.2026 / 10:31")
        self.assertEqual(facts["insurance_number"].value, "25101294B551")
        self.assertEqual(facts["employee_name"].value, "Sam Example")

    def test_blank_pdf_is_marked_needs_ocr(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("germany/person_2-capital-annual_income_statement.pdf"),
            doc_type="german_capital_certificate_pdf",
            pages=[""],
        )

        self.assertEqual(doc.status, "needs_ocr")
        self.assertEqual(doc.facts, [])

    def test_extracts_schwab_limitation_notice_from_ocr_text(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("us/Schwab-limitations.png"),
            doc_type="schwab_limitation_image",
            pages=[SCHWAB_LIMITATION_OCR],
        )

        facts = {fact.key: fact for fact in doc.facts}
        self.assertEqual(doc.status, "ok")
        self.assertEqual(facts["historical_data_window_years"].value, "4")
        self.assertEqual(facts["earliest_available_start_date"].value, "2022-04-11")

    def test_unsupported_doc_type_yields_stub_status(self) -> None:
        doc = extract_document_facts_from_pages(
            relative_path=Path("real_estate/closing-statement.pdf"),
            doc_type="unknown",
            pages=["placeholder"],
        )

        self.assertEqual(doc.status, "unsupported_doc_type")
        self.assertEqual(doc.parser, "deterministic.unsupported.v1")
        self.assertEqual(doc.facts, [])


class WriteDocumentFactsTest(unittest.TestCase):
    def test_write_document_facts_creates_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2026)
            paths.ensure_directories()

            facts_doc = DocumentFacts(
                relative_path="germany/sample.pdf",
                doc_type="german_lohnsteuer_pdf",
                parser="deterministic.german_lohnsteuer_pdf.v1",
                status="ok",
                facts=[
                    FactRecord(
                        key="gross_wage_eur",
                        value="171800.61",
                        value_type="decimal",
                        unit="EUR",
                        confidence="high",
                        source={
                            "file": "germany/sample.pdf",
                            "page": 1,
                            "section": "Line 3",
                            "snippet": "3. Gross wage incl. benefits in kind\n171.80061",
                        },
                        notes="",
                    )
                ],
                warnings=[],
            )

            json_path, md_path = write_document_facts(paths, facts_doc)

            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            payload = json.loads(json_path.read_text())
            self.assertEqual(payload["doc_type"], "german_lohnsteuer_pdf")
            self.assertIsNone(payload["provider"])
            self.assertEqual(payload["facts"][0]["key"], "gross_wage_eur")
            self.assertIn("gross_wage_eur", md_path.read_text())


class ExtractAllFactsOverrideTest(unittest.TestCase):
    def test_manual_fact_override_replaces_needs_ocr_document(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = YearPaths.for_year(root, 2025)
            paths.ensure_directories()

            target = paths.raw_root / "germany" / "person_2-capital-annual_income_statement.pdf"
            target.write_text("")
            write_manifest(paths.raw_root, paths.manifest_path, year=2025)

            override_path = paths.manual_facts_root / "germany_person_2_capital_annual_income_statement_pdf.json"
            override_path.write_text(
                json.dumps(
                    {
                        "parser": "manual.reviewed.v1",
                        "status": "ok",
                        "warnings": [],
                        "facts": [
                            {
                                "key": "capital_income_line_7_eur",
                                "value": "189.28",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 7",
                                    "snippet": "Zeile 7 ... 189,28 €"
                                },
                                "notes": ""
                            },
                            {
                                "key": "stock_sale_gain_line_8_eur",
                                "value": "65.62",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 8",
                                    "snippet": "Zeile 8 ... 65,62 €"
                                },
                                "notes": ""
                            },
                            {
                                "key": "saver_allowance_used_line_17_eur",
                                "value": "0.00",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 17",
                                    "snippet": "Zeile 17 ... 0,00 €"
                                },
                                "notes": ""
                            },
                            {
                                "key": "capital_gains_tax_line_37_eur",
                                "value": "31.57",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 37",
                                    "snippet": "Zeile 37 ... 31,57 €"
                                },
                                "notes": ""
                            },
                            {
                                "key": "solidarity_surcharge_line_38_eur",
                                "value": "1.64",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 38",
                                    "snippet": "Zeile 38 ... 1,64 €"
                                },
                                "notes": ""
                            },
                            {
                                "key": "foreign_tax_credit_line_40_eur",
                                "value": "15.78",
                                "value_type": "decimal",
                                "unit": "EUR",
                                "confidence": "manual_verified",
                                "source": {
                                    "file": "germany/person_2-capital-annual_income_statement.pdf",
                                    "page": 1,
                                    "section": "Zeile 40",
                                    "snippet": "Zeile 40 ... 15,78 €"
                                },
                                "notes": ""
                            }
                        ]
                    },
                    indent=2,
                )
                + "\n"
            )

            rows = extract_all_facts(paths)

            self.assertEqual(rows[0]["status"], "ok")
            payload = json.loads((paths.facts_root / "germany_person_2_capital_annual_income_statement_pdf.facts.json").read_text())
            self.assertEqual(payload["parser"], "manual.reviewed.v1")
            self.assertEqual(payload["facts"][0]["key"], "capital_income_line_7_eur")


if __name__ == "__main__":
    unittest.main()
