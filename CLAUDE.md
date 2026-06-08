# Claude Instructions

## Tax-Law Rule Requirements

- Every tax-rule implementation must cite the controlling legal authority in code comments near the calculation.
- Every tax-rule implementation must include an official web link to the authority in the law spec, rule metadata, trace output, or narrative template.
- Tests for tax rules must cite the same authority and assert concrete numeric outcomes, not just that functions run.
- If a legal source is unclear, year-specific, conflicting, missing, or not yet modeled, fail closed with an explicit error or `not_applicable`; never silently default to zero.
- Renderers must not perform legal math. They may only display final legal-core outputs and cited trace/narrative metadata.
- Cross-border treaty rules must identify the treaty article, domestic-law section, source/residence country role, currency, and affected form line.
- Prefer official sources: IRS, Treasury, BMF, Gesetze-im-Internet, ELSTER/BMF instructions. Non-official sources may supplement but not replace official authority.
- Jinja narrative templates must be named by jurisdiction and rule, and must match the same law citation used by the core function and tests.

## Design Pattern: Facts, Positions, Deterministic Operations

Every value in the engine belongs to exactly one of three categories.
Adding a new input, output, or computation requires picking the right
category up front; bypassing the boundary is the same class of failure
as bypassing the rule graph.

### 1. Facts — raw, observed reality

**What they are:** Numbers, dates, identifiers, and text extracted
verbatim from source documents (W-2s, Lohnsteuerbescheinigungen,
broker statements, payment confirmations, etc.) or supplied directly
by the user via the intake wizard.

**Rules:**
- Every fact carries source provenance: file path, page number,
  section, and a quoted source snippet. The provenance is part of the
  fact, not metadata about it.
- Facts are descriptive, not legal: a fact says "this document on this
  page reports €X gross wages," never "this is W-2 box 1 income for
  U.S. purposes." Legal classification happens at the position layer.
- Facts are immutable once extracted. Re-extracting from the same bytes
  must produce the same fact. Non-deterministic extraction (OCR,
  LLM-assisted parsing) must record a confidence score and a
  human-review marker.
- A fact missing from a source document is **null**, not zero. See
  "Null / zero / missing" below.

**Lives under:** `normalized/facts/`, `normalized/derived-facts/` (for
deterministic facts derived from raw facts), and the intake-wizard
config CSVs.

### 2. Positions — explicit legal choices, each with a cited basis

**What they are:** Legal stances the taxpayer (or the engine on their
behalf) takes — filing posture, treaty elections, FTC method
(accrued vs. paid), Arbeitszimmer election, FEIE vs. FTC, jurisdiction
opt-outs, item-level treaty coverage declarations, etc.

**Rules:**
- Every position must link to the controlling legal authority
  explaining *why a position must be taken at all* and what the
  consequences of each option are. The link goes in the position file
  (CSV header comment, JSON `_authority` field, schema description) or
  in the loader's docstring — not only in the rule that consumes it.
- A position is taken explicitly. There is no "default" silently chosen
  by the engine. If the workspace does not declare a required position,
  the loader fails closed with the citation in the error message.
- Positions are auditable in isolation: a reader of the position file
  alone, with the cited authority, can verify the choice is legal even
  before any rule runs.
- Renderers may not invent positions. A form line that depends on a
  position must read the position from a declared input.

**Lives under:** `config/elections.csv`, `config/manual_overrides.json`,
`outputs/tax-positions/`, and the profile-level posture registry.

### 3. Deterministic operations — everything else

**What they are:** All math, classification, projection, currency
conversion, rounding, aggregation, form-line population, and narrative
rendering that connects facts + positions to a filed return.

**Rules:**
- Every operation must be deterministic: same inputs → same outputs,
  byte-identical, across runs.
- Every operation must link to the controlling legal authority. The
  link appears in three places: (a) a code comment near the
  calculation, (b) the rule metadata (`law_ref`, `citation_url`), and
  (c) the trace output / narrative template that explains the step to
  a reader.
- Statutory constants live only in the law modules (invariant I1). An
  operation that needs a rate, threshold, or schedule imports the
  named constant.
- Operations may not read undeclared facts or positions (invariants
  I4, I7, I8). The declared input/output keys are the contract.
- Operations fail closed on missing inputs (invariant I4). Silent
  defaults to zero are the highest-severity bug class in this
  codebase — see LEAK-1, LEAK-3, H5 (CLAUDE.md history).

### Why these three, and only these three

If a value is not a fact, not a cited position, and not produced by a
deterministic legally-cited operation, **it does not belong in the
engine**. Heuristics, "reasonable defaults," fallback estimates, and
LLM-generated numbers are out of scope by construction. The audit
trail (provenance for facts, citation for positions, fingerprint +
citation for operations) must cover every value that reaches a form
line.

### Null / zero / missing — three distinct states

The engine must distinguish three states that look alike at the bit
level but mean different things legally. Conflating them is the same
class of failure as silently defaulting to zero — see LEAK-1, H5, and
the U.S. treaty dividend coverage-gap bug closed 2026-06-08
(``tests/y2025/test_us_law.py::test_load_us_assessment_inputs_rejects_explicit_germany_packet_coverage_gap``).

| State | Meaning | Representation | Engine response |
|---|---|---|---|
| **Missing** | The data has not been declared. No position file exists, no source document was provided, the orchestrator did not publish the value. | `None` (Python) / absent file / absent key | Fail closed with the citation in the error, or surface as `not_applicable` when the legal posture explicitly opts out (invariant I13). |
| **Empty / explicit zero** | The data has been declared and the declaration is "no items," "zero euros," "no foreign accounts." The taxpayer has taken a legal position that the value is zero. | `()` / `[]` / header-only CSV / `Decimal("0.00")` | Treat as a legitimate legal value. Carry it through the pipeline. Render the form line as zero, not blank. |
| **Populated** | The data has one or more values. | Non-empty collection or non-zero scalar | Standard processing. |

**Rules for distinguishing them:**

- File-backed inputs: **file does not exist** = missing; **file exists
  with header only** = empty; **file has rows** = populated. Loaders
  must report the distinction (e.g., return `(items, file_declared)`
  rather than collapsing both states into `()`).
- Function arguments: **`None`** = missing; **`()` / `[]`** = empty;
  non-empty = populated. Loader signatures that accept "the absence of
  a value" should use `Optional[...] = None`, never an empty default.
- Decimal scalars: **`None`** = missing; **`Decimal("0.00")`** =
  explicit zero. Never collapse `None` to zero at the boundary.
- Bridging: when an orchestrator hands one jurisdiction's output to
  another's loader, the contract is "an empty packet under an active
  election asserts coverage of zero items; a missing packet asserts
  nothing." The receiving loader must check both the value and the
  declaration state.

The U.S. treaty dividend coverage-gap case is the canonical example:
``germany_treaty_dividend_items=None`` means "no same-run Germany
packet provided"; ``germany_treaty_dividend_items=()`` under an active
treaty election + a declared (possibly empty) U.S. position means
"zero items, legitimately zero outputs"; ``germany_treaty_dividend_items=()``
under an active treaty election + no declared U.S. position is a
**coverage-contract violation** and the loader fails closed
(``tax_pipeline/y2025/us_inputs.py::load_us_assessment_inputs_2025``).

## Structural Invariants the Engine Guarantees

This list is what future contributors and agents must protect.
Adding a new tax-rule, refactoring a stage, or extending the
pipeline must NOT silently weaken any of these invariants. The
tests listed under each entry are the structural guard rails;
if you find yourself fighting one, talk to a maintainer instead
of disabling the test.

### I1 — No legal constant literal outside the law modules

**Rule:** Statutory rates and named threshold constants live in
`germany_2025_law.py`, `us_2025_law.py`, or `treaty_2025_law.py`.
Any other module that needs them imports the named constant.

**Why:** A literal `Decimal("0.15")` smuggled into a loader is invisible
when the DBA-USA Art. 10(2)(b) rate ever changes. Centralizing them
makes every authority cite a single edit point.

**Enforced by:** `tests/y_agnostic/test_no_legal_constant_literal_bypass.py`

### I2 — Every value in `final-legal-output.json` traces to a `StageResult.output_fingerprint`

**Rule:** No value may appear in `final-legal-output.json` unless it
was produced by a declared stage's `output_keys` and recorded in that
stage's `output_fingerprint`.

**Why:** Final outputs that bypass the rule graph (computed in an
orchestrator main() or a renderer) leave the audit trail incomplete
and let legal math escape review — the failure mode behind LEAK-1
(final refund) and LEAK-3 (Anlage KAP line 19).

**Enforced by:** `tests/y_agnostic/test_final_output_values_trace_to_rule_outputs.py`

### I3 — Every form line the renderer touches has a matching `OutputDeclaration.form_line_refs`

**Rule:** Form renderers may write only to form lines that are
declared in some stage's `OutputDeclaration.form_line_refs`. The
mapping is bidirectional: every declared `form_line_refs` entry must
correspond to a real renderer touch point.

**Why:** Without bidirectional enforcement, a renderer can quietly
emit a number to a form line that no rule justifies (the CR3
waypoint-misclassification class) or a stage can declare a form line
that nothing actually fills.

**Enforced by:** `tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py`

### I4 — No silent zero defaults on declared rule inputs

**Rule:** Inside `*_2025_rules.py`, a rule's `calculate(facts)` body
may not read a declared input via `facts.get(key, ZERO_*)` or any
silent default. Missing inputs must fail closed.

**Why:** H5 (treaty25_17 silent FTC denial) silently zeroed a missing
foreign-tax fact and the rule kept running. A `not_applicable` or
explicit error is the legally correct posture.

**Enforced by:** `tests/y_agnostic/test_no_silent_zero_defaults_in_rules.py`

### I5 — No `Decimal` arithmetic in projection or orchestrator main() bodies

**Rule:** `tax_pipeline/pipelines/y2025/*projections*.py` and the
orchestrator main() bodies under `pipelines/y2025/` must not perform
`Decimal` arithmetic on legal output keys. All math lives inside
declared rule `calculate` bodies.

**Why:** Decimal math in projections is exactly how LEAK-1 and LEAK-3
escaped the rule graph. The audit graph can only audit what runs
inside the graph.

**Enforced by:** `tests/y_agnostic/test_no_legal_math_outside_rule_graph.py`

### I6 — Fingerprint payloads contain only canonical values, never `repr(value)`

**Rule:** `stable_fingerprint` payloads use canonical Decimal/string
representations. No `*_repr` keys, no `repr(value)` smuggled into a
fingerprint dict.

**Why:** H1 (germany_ordinary_2025_rules.py:544) used `repr(...)` in
a fingerprint, which made the fingerprint sensitive to Python's
internal Decimal formatting and caused spurious drift between runs.

**Enforced by:** `tests/y_agnostic/test_fingerprint_uses_canonical_value.py`

### I7 — Rules read only declared `input_fact_keys`

**Rule:** A rule's `calculate(facts)` may only read keys that appear
in its stage's `input_fact_keys`. Reading anything else raises
`RuleInputDeclarationError`.

**Why:** DE25-00 was reading `de.ordinary.raw_inputs` without
declaring it, which hid a real dependency from the audit graph and
broke reproducibility under partial replay.

**Enforced by:** `tests/y_agnostic/test_rule_input_tracking.py`

### I8 — Rules write only declared `output_keys`

**Rule:** A rule's `calculate(facts)` return value contains exactly
the keys declared in its stage's `output_keys` — no extras, no
omissions.

**Why:** Undeclared outputs cannot be audited and silently break
downstream stages that consume them. Declared outputs that go
missing leave the legal computation incomplete.

**Enforced by:** `validate_result` inline at the end of every rule
execution in `core/stages.py` (no dedicated test file — this check
runs on every rule call as part of the executor's contract).

### I9 — Atomic file writes use unique temp filenames + parent fsync

**Rule:** Persisting JSON or any artifact to disk uses
`tempfile.NamedTemporaryFile` (or equivalent unique-name temp file)
followed by `f.Sync()` and `os.Rename`, with the parent directory
fsynced.

**Why:** H9 surfaced a real race where two concurrent writers
collided on a non-unique temp filename. Without unique naming and
parent fsync the on-disk state can be torn or lost across crashes.

**Enforced by:** `tests/y_agnostic/test_final_legal_output_atomic.py`

### I10 — All file reads pass `encoding="utf-8"`

**Rule:** Every `Path.read_text(...)`, `open(...)`, and
`csv.DictReader(open(...))` site passes `encoding="utf-8"`.

**Why:** Implicit-locale decoding is non-deterministic across
machines and is a portability hazard for tax data containing umlauts
(Anlage names, Steuerbescheid fields). Determinism is part of the
audit contract.

**Enforced by:** `tests/y_agnostic/test_file_reads_specify_utf8_encoding.py`

### I11 — Form-bound legal values flow only via a typed `LegalValue` envelope

**Rule:** Values that cross the rule-graph → form-renderer boundary
travel inside a typed `LegalValue(amount, stage_id, output_key,
fingerprint)` envelope (`tax_pipeline/core/legal_value.py`).
`RuleGraphExecution.legal_outputs` wraps every Decimal-valued rule
output at the executor boundary, using the executor's existing
`StageResult.output_fingerprints` chain — no parallel third-domain
re-hash. The `(stage_id, output_key, fingerprint)` triple is persisted
under the top-level `_provenance` key in `final-legal-output.json`,
so the audit packet carries per-rule-output provenance at the
form-line boundary.

The form-renderer boundary is enforced at two complementary layers:

1. **Type boundary** — `legal_value_entry(line, value, …)` in
   `forms/common.py` calls `require_legal_value(value, …)` and raises
   `TypeError` if `value` is not a `LegalValue`. This is the
   fail-closed runtime check on every form-line write.
2. **Wiring audit (F-CQ-1)** — every `FormEntry(...)` constructor in
   `forms/germany.py` and `forms/usa.py` that carries a legal-value
   amount must obtain that amount via `legal_value_entry(...)`. An AST
   regression test in `tests/y_agnostic/test_legal_value_envelope.py` rejects any
   `format_currency(...)` call appearing as a direct `FormEntry(...)`
   value argument so the boundary helpers cannot silently become dead
   code again. Renderer-side projections (form-line dict keys that do
   not 1:1 match a stage output_key) get their `LegalValue` from
   `legal_value_from_dict` / `legal_value_from_decimal`, which prefer
   the executor's StageResult fingerprint via
   `_provenance.form_lines[country][output_key]` when one exists and
   otherwise synthesize a deterministic
   `(renderer:<country>:<section>, line_key, value)` fingerprint so
   every rendered legal value still carries an auditable triple
   (captured on `FormEntry.provenance`).

**Why:** This is the strongest defense against the LEAK-1 / LEAK-3
class — legal math escaping the graph and reaching a form line with
no audit trail. Catching it at the type boundary makes the runtime
bug unrepresentable; the AST audit prevents the type boundary from
becoming an isolated, never-invoked helper (the F-CQ-1 dead-code
defect closed on 2026-05-01).

**Enforced by:** `tests/y_agnostic/test_legal_value_envelope.py` (LegalValue
validation, executor wrap, renderer-boundary `TypeError`, AST audit
of `FormEntry`/`format_currency` call sites in the form modules, and
end-to-end provenance section in `final-legal-output.json`).

### I12 — Narrative templates address inputs by key, never positional

**Rule:** Jinja narrative templates reference rule inputs as
`rule.inputs_by_key["de.ordinary.gross_wages"].value`, never
`rule.inputs[N]` with a positional integer index.

**Why:** Prepending a new declared input (the WS-3A redo on DE25-00 /
DE25-07 / US25-08+) silently shifts every positional index, so a
template that read `rule.inputs[2]` will now narrate the wrong number
without raising. Keyed access is position-stable.

**Enforced by:** `tests/y_agnostic/test_narrative_templates_index_inputs_by_key.py`

### I13 — Disabled-jurisdiction artifacts are explicitly absent, not silently zeroed

**Rule:** When the user opts a jurisdiction out (e.g.
`elections.us_filing_required=false` under 26 U.S.C. § 6012), the
engine must not write that jurisdiction's analysis-step JSON, rendered
forms, legal-audit packets, or per-rule fingerprint entries.
`final-legal-output.json` carries:

  * a top-level `us_filing_required: bool` marker;
  * the disabled jurisdiction's `forms` and `legal_audit` blocks set to
    `{"status": "not_applicable", "reason": <citation-bearing string>}`;
  * an empty `_provenance.rule_outputs[country]` for the disabled side.

The cross-jurisdiction reconciliation stages
(`BRIDGE25-FOREIGN-TAX-RECONCILIATION`) and treaty re-sourcing stages
(`TREATY25-*`) must not be added to the executed law-stage graph when
the U.S. side is disabled.

**Why:** A "disabled" jurisdiction that silently emits zero-valued
forms is indistinguishable from a real return with $0 tax — the audit
packet cannot tell apart "user has no U.S. obligation" from "engine
computed $0 of U.S. tax". Forcing the absence to be explicit (status,
reason citation, missing rule_outputs) makes the opt-out posture
auditable and prevents a partial U.S. package from leaking out under a
posture that legally turns the entire pathway off.

**Enforced by:** `tests/y2025/test_us_filing_not_required.py`
(`test_no_us_artifacts_are_written`,
`test_final_legal_output_marks_opt_out`,
`test_de_outputs_still_trace_to_rule_outputs`).
