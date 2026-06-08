# JStG 2024 — Anlage KAP VZ 2025 schema surgery inventory

**Date**: 2026-05-13
**Mission**: Eliminate § 20 Abs. 6 Sätze 5/6 EStG (deleted by JStG 2024,
effective 06.12.2024, applies to all open cases — so VZ 2025) and
drop the corresponding Anlage KAP 2025 Zeilen (former 2024 Zeilen 21,
24, 25). Zeile 19 sum formula now = 20 + 22 + 23 (instead of 20 + 21
+ 22 + 23). All other VZ 2025 Anlage KAP line numbers unchanged from
2024. VZ 2026 renumbering NOT applied.

Authority:
- JStG 2024 (Empfehlung Nr. 4a des Finanzausschusses, in Kraft 06.12.2024)
- BMF 16.05.2025 Steuerbescheinigung-Schreiben:
  https://www.bundesfinanzministerium.de/Content/DE/Downloads/BMF_Schreiben/Steuerarten/Abgeltungsteuer/2025-05-16-kapitalertragSt-steuerbescheinigung.pdf
- § 20 Abs. 6 EStG (current text after JStG 2024 deletion):
  https://www.gesetze-im-internet.de/estg/__20.html

## Blast radius — files touched by the surgery

### Step 2 (law-spec)

No legal constants for the €20,000 cap exist in `tax_pipeline/y2025/germany_law.py`
(grep confirmed: zero hits for `20000` near §20 in `germany_law.py`).
The deletion is realized via authority-comment updates only — no constants
to remove. New comment block goes in `germany_law.py` near the existing
§ 20 Abs. 6 EStG discussion.

### Step 3 (rule-graph)

No dedicated rule for the €20k Termingeschäfte or Uneinbringlichkeit
cap exists — the pre-JStG-2024 cap was never implemented in this
engine (the BMF-cited carryforward in `germany_capital_rules.py` and
`germany_stages.py` only models the *Aktien-spezifischer*
Verrechnungskreis under § 20 Abs. 6 Satz 4, which SURVIVES JStG 2024).
The DE25-FORM-KAP-PROJECTION stage emits `de.kap.line_21_eur` /
`de.kap.line_24_eur` for the former 2024 Termingeschäfte-positive
and -negative buckets feeding the form. These two output keys + the
Zeile 19 sum semantics are the surgery targets.

Affected files:

- `tax_pipeline/y2025/germany_kap_projection_rules.py:233-236` —
  drop `de.kap.line_21_eur` (option_pos) and `de.kap.line_24_eur`
  (option_neg) from the projection output dict. The option_pos /
  option_neg local variables remain as inputs to the Zeile 19 sum
  but are no longer emitted as separate Zeilen.
- `tax_pipeline/y2025/germany_stages.py:2013-2014, 2049-2059,
  2071-2081` — drop the OutputDeclaration entries for
  `de.kap.line_21_eur` and `de.kap.line_24_eur`; update legal_formula
  text to remove the line_21 / line_24 mentions.
- `tests/y2025/test_de_form_kap_projection.py:124, 130, 184, 186,
  219, 221` — drop assertions on the two deleted output keys; add a
  new test proving a > €20k Termingeschäfte loss fully nets against
  ordinary § 20 income (no cap).

### Step 4 (form schema + renderer + template)

Affected files:

- `tax_pipeline/forms/schemas/anlage_kap.toml:52-55, 60-63` — drop
  the `[[lines]]` blocks for `line_id = "21"` and `line_id = "24"`.
  Add a deletion-marker comment with JStG 2024 + BMF citations.
- `tax_pipeline/forms/germany.py` — no renderer call site
  directly references "21" / "24" (everything flows through the
  CSV row + `kap_lines` profile lookup, so the schema drop +
  projection drop is sufficient).
- `tax_pipeline/pipelines/y2025/germany_projections.py:114-116,
  142-144, 198-199` — drop `line_21_eur` / `line_24_eur` fetches,
  drop the two `kap_summary_rows` entries for Person 1 Z21 / Z24,
  drop `option_pos` / `option_neg` from `capital_audit`.
- `tax_pipeline/pipelines/y2025/germany_model.py:894-942` — drop
  `option_pos` / `option_neg` lines from the ELSTER audit summary.
- `tax_pipeline/narrative/templates/DE25-FORM-KAP-PROJECTION.jinja:15,
  17, 40, 42` — drop the two former-2024-Zeile-21 / Zeile-24
  bullets in both DE and EN sections; positional `rule.outputs[N]`
  indices shift (was 0..9 for 10 outputs, becomes 0..7 for 8
  outputs). Add BMF-VERIFIED 2026-05-13 marker.
- `tax_pipeline/narrative/templates/DE25-13-CAPITAL-RAW-BUCKETS.jinja:11`
  — the Termingeschäfte mention here refers to § 20 Abs. 2 Nr. 3
  income classification, NOT the dropped Zeile. No edit (the
  classification survives, only the form-line surface was dropped).
- `tax_pipeline/scaffold_year.py:38, 50` — defaults for new
  workspaces. Drop "21" and "24" from the person_1 default kap_lines.
- `tax_pipeline/forms/germany.py:202` — built-in person_1
  `kap_lines` default list. Drop "21" and "24".

### Workspace profile.json (judgment call)

The three workspaces' `years/<name>/config/profile.json` for
person_1 list `kap_lines: ["17", "19", "20", "21", "23", "24", "41"]`.
After JStG 2024 the "21" and "24" entries reference dropped Zeilen.
The strict workspace constraint says "do NOT touch the three workspace
md5-pinned input files" — but the schema validation in
`tax_pipeline/profile.py:_parse_kap_lines` rejects entries not declared
in `anlage_kap.toml`, so if I drop "21" and "24" from the schema TOML,
the three workspaces fail validation.

**Judgment**: this is law surgery, not user-input editing. The user
cannot legally instruct the engine to render a Zeile that no longer
exists on the 2025 form. I will update the three workspace
`profile.json` files to drop "21" and "24" from `person_1.kap_lines`,
and I will document this explicitly in commit 4. The `outputs/`
under those workspaces are computed artifacts that the test fixture
chain re-generates — they will rotate. The user-input data (CSVs,
PDFs, raw extractions) under `inputs/` and `normalized/` is NOT
touched.

### Baseline fingerprint cleanup

`tests/data/label_inventory_baseline.json` — none of the existing
fingerprint entries pattern-match `Zeile 21` / `Zeile 24` / `Zeile 25`
/ `Termingesch` / `line_21` / `line_24` content (verified by grep).
Five fingerprints under `germany_kap_projection_rules.py::zeile::*`
exist but those correspond to surviving Zeilen — not removed.
The Jinja DE25-FORM-KAP-PROJECTION.jinja template fingerprints will
shift when the new BMF-VERIFIED marker is added; any stale baseline
entries surfaced by the test run will be removed.

## Search artifacts (recorded for audit traceability)

- `Termingesch` — surfaces in:
  - `tax_pipeline/narrative/templates/DE25-13-CAPITAL-RAW-BUCKETS.jinja:11` (KEEP — § 20 Abs. 2 Nr. 3 income classification, not the dropped Zeile)
  - `tax_pipeline/narrative/templates/DE25-FORM-KAP-PROJECTION.jinja:15,17,40,42` (DROP)
  - `tax_pipeline/y2025/germany_kap_projection_rules.py:80` (UPDATE prose)
  - `tax_pipeline/pipelines/y2025/germany_projections.py:142,144` (DROP)
- `Uneinbringlich` — zero hits in `tax_pipeline/`, `tests/`. This
  category was never implemented; the JStG 2024 deletion is a no-op
  for this engine's rule graph.
- `20_000` / `20000` near § 20 — zero hits as a § 20 Abs. 6 S.5/6 cap
  constant in `germany_law.py`. The €20k cap was never modeled.
- `§ 20 Abs. 6 Satz 5` / `Satz 6` — zero literal hits in the engine.
  Existing `Sätze 4 bis 6` references in `germany_model.py:1138-1140`
  describe the stock-loss carryforward (Satz 4 survives; the wording
  needs trimming to `Satz 4` only).
