# Germany Golden Fixtures

`bmf_2025_tariff_and_soli_samples.csv` is an always-on public golden fixture for the mechanical 2025 German tariff and solidarity-surcharge math.

The values are derived from the official BMF 2025 XML pseudocode:

- `GFB = 12096`
- `SOLZFREI = 19950`
- `UPTAB25` tariff formulas and thresholds
- `MSOLZ` solidarity-surcharge free limit and mitigation formula

Sources:

- https://bmf-steuerrechner.de/javax.faces.resource/daten/xmls/Lohnsteuer2025.xml.xhtml
- https://www.bmf-steuerrechner.de/ekst/eingabeformekst.xhtml
- https://www.gesetze-im-internet.de/estg/__32a.html
- https://www.gesetze-im-internet.de/solzg_1995/__3.html
- https://www.gesetze-im-internet.de/solzg_1995/__4.html

DATEV fixtures live under `datev/`. DATEV numeric golden cases are intentionally user-provided so the public repo can test against purchased or access-controlled DATEV examples without redistributing proprietary case material.
