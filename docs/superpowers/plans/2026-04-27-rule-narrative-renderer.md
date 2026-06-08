# Rule Narrative Renderer Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add country/language narrative outputs where each legal rule emits structured inputs, math steps, outputs, form lines, and a rule-named Jinja template.

**Architecture:** Legal stage adapters produce structured narrative packets; `final-legal-output.json` validates and stores those packets; a narrative renderer uses Jinja `StrictUndefined` templates to produce `DE-de`, `DE-en`, and `US-en` Markdown files without recomputing tax math. Template filenames are stable legal contracts named by country, domain, and law/form reference.

**Tech Stack:** Python dataclasses, `jinja2.StrictUndefined`, existing `LawStage`/`StageResult`, `unittest`, Markdown outputs.

---

## File Structure

- Create `tax_pipeline/core/narrative.py`: immutable narrative dataclasses, serialization, and fail-closed validation.
- Create `tax_pipeline/narrative/render.py`: Jinja environment, template resolution, country/language rendering.
- Create `tax_pipeline/narrative/templates/*.jinja`: shared v1 rule templates named by country/domain/rule/language.
- Modify `tax_pipeline/germany_2025_stages.py`: emit Germany rule narratives from existing stage values.
- Modify `tax_pipeline/usa_2025_stages.py`: emit U.S. rule narratives from existing stage values.
- Modify `tax_pipeline/treaty_2025_stages.py`: emit treaty rule narratives for U.S. treaty logic.
- Modify `tax_pipeline/pipelines/y2025/final_legal_output.py`: include narrative packets from validated final outputs.
- Create `tax_pipeline/pipelines/y2025/rule_narratives.py`: render narrative files after final output is built.
- Modify `tax_pipeline/year_registry.py`: run rule narrative output after final output and before verbose report.
- Add tests in `tests/test_rule_narratives.py`.

## Chunk 1: Structured Narrative Model

### Task 1: Narrative Dataclasses

**Files:**
- Create: `tax_pipeline/core/narrative.py`
- Test: `tests/test_rule_narratives.py`

- [ ] **Step 1: Write failing tests**

Test that a `RuleNarrative` requires non-empty `rule_id`, `template_id`, `language`, `inputs`, `math_steps`, `outputs`, and `form_lines`, and serializes to JSON-safe dictionaries.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeModelTest`

- [ ] **Step 3: Implement minimal dataclasses**

Implement `NarrativeValue`, `NarrativeMathStep`, `NarrativeFormLine`, and `RuleNarrative` with `to_dict()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeModelTest`

## Chunk 2: Jinja Template Renderer

### Task 2: Fail-Closed Template Rendering

**Files:**
- Create: `tax_pipeline/narrative/render.py`
- Create: `tax_pipeline/narrative/templates/DE_ordinary_EStG-32a-5-splitting_de.jinja`
- Create: `tax_pipeline/narrative/templates/DE_ordinary_EStG-32a-5-splitting_en.jinja`
- Create: `tax_pipeline/narrative/templates/US_ftc_Form1116-line12_en.jinja`
- Test: `tests/test_rule_narratives.py`

- [ ] **Step 1: Write failing tests**

Test that template names resolve exactly from `template_id`, missing templates fail, and missing variables fail through `StrictUndefined`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeRendererTest`

- [ ] **Step 3: Implement renderer**

Use Jinja `Environment(undefined=StrictUndefined)` and render each country/language list into a single Markdown file.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeRendererTest`

## Chunk 3: Stage Adapter Narratives

### Task 3: Emit Rule Narratives From Existing Stages

**Files:**
- Modify: `tax_pipeline/germany_2025_stages.py`
- Modify: `tax_pipeline/usa_2025_stages.py`
- Modify: `tax_pipeline/treaty_2025_stages.py`
- Test: `tests/test_rule_narratives.py`

- [ ] **Step 1: Write failing tests**

Test that Germany split-tariff, Germany capital FTC, U.S. Form 1116/treaty, and U.S. NIIT stages emit narrative packets with legal refs and form lines.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeStageAdapterTest`

- [ ] **Step 3: Implement minimal adapters**

Add helper functions that map existing stage values into rule narratives without recomputing tax.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativeStageAdapterTest`

## Chunk 4: Final Output And Pipeline Integration

### Task 4: Persist And Render Narrative Outputs

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/final_legal_output.py`
- Create: `tax_pipeline/pipelines/y2025/rule_narratives.py`
- Modify: `tax_pipeline/year_registry.py`
- Test: `tests/test_rule_narratives.py`

- [ ] **Step 1: Write failing tests**

Test that final output contains narrative packets and the pipeline renders `DE-de-narrative.md`, `DE-en-narrative.md`, and `US-en-narrative.md`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_rule_narratives.RuleNarrativePipelineTest`

- [ ] **Step 3: Implement integration**

Add narrative packets to final output and run `tax_pipeline.pipelines.y2025.rule_narratives` after final output.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_rule_narratives`

## Final Verification

- [ ] Run `python3 -m unittest`.
- [ ] Run `python3 -m tax_pipeline.run_year demo-2025`.
- [ ] Confirm narrative files exist and render legal references, inputs, math steps, outputs, and form lines.
