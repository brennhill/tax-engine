# Engine Spec: Auditability And Narratives

This document is the product contract for the tax engine's legal execution,
audit trail, rule graph, and narrative outputs.

The engine's central promise is:

> A tax result is only trustworthy if every legal rule that produced it can be
> traced to the law, the exact inputs consumed, the exact outputs produced, the
> rounding/precision policy applied, and the narrative text shown to the user.

This spec is intentionally stricter than ordinary reporting documentation. It
defines invariants that code and tests must enforce.

## Scope

This spec covers:

- How legal rules are identified.
- How rule execution is ordered.
- What each rule must log while executing.
- Where those logs are stored.
- How Jinja narratives receive values.
- How graph and narrative outputs stay synchronized.
- What must fail closed.

This spec does not define the substantive tax law for Germany, the United
States, or the treaty. Substantive rules belong in year/jurisdiction law specs,
stage declarations, legal core functions, and tests that cite the law.

## Core Principle

The legal engine has three layers:

1. Imperative input/output shell.
2. Functional legal core.
3. Audit/rendering projections.

Only the input/output shell reads and writes files. The legal core receives
typed facts and returns typed legal results. Rendering is a projection of the
legal results and executed audit packets. Rendering must never calculate tax,
choose legal branches, infer missing values, or fill in placeholders.

## Rule Identity

Every legal rule has one stable `rule_id`.

Rule IDs are globally unique within one executed country/language graph node
set. A rule ID must not be reused for two different computations, two different
output meanings, or a hand-authored narrative and a declared stage.

The same legal rule may be rendered in multiple languages. In that case:

- The `rule_id` is the same.
- The legal inputs are the same.
- The legal outputs are the same.
- The fingerprints are derived from the same executed values.
- The language-specific narrative template may differ only in wording.

For example, Germany may render `DE25-08-SPLIT-TARIFF` in German and English.
Those are two language renderings of the same legal rule, not two rules.

Rule IDs must be jurisdiction/year/rule specific enough to avoid accidental
overlap:

- `DE25-18-SECTION-32D5-FTC`
- `US25-18-TREATY-ADDITIONAL-FTC`
- `TREATY25-17-GERMAN-RESIDUAL-CAP`

Rule IDs must not be generic:

- `capital_tax`
- `foreign_tax_credit`
- `stage_7`
- `summary`

## Rule Declaration

Every public legal calculation must be represented by a declared law rule.

A declared rule must include:

- `rule_id`
- country or treaty scope
- legal references
- authority URLs
- required input keys
- produced output keys
- rounding policy
- law-order note
- form-line references, if applicable
- narrative template IDs
- implementation reference

The declaration is the static contract. It says what the rule is allowed to
consume and produce. It is not enough for auditability because it does not prove
what actually happened in one run.

## Rule Execution

The engine must execute legal rules through the rule graph, not by having
pipeline or renderer code call legal functions ad hoc.

The rule graph is the ordered execution path. It enforces:

- all required inputs are available before a rule runs
- no duplicate rule IDs
- no duplicate output keys in the same graph
- no unknown stage results
- no untracked outputs
- no missing fingerprints
- no missing precision notes

If a rule cannot run because an input is missing, unsupported, ambiguous, or not
applicable without an explicit `not_applicable` posture, the engine must fail
closed.

## Executed Audit Packet

Each executed rule must produce one audit packet from the same run.

The audit packet is the source of truth for both graph output and narrative
output. It must include:

- `rule_id`
- country
- language, for rendered packet projections
- template ID
- legal references
- authority URLs
- actual input values
- input keys
- input fingerprints
- actual output values
- output keys
- output fingerprints
- math steps
- rounding and precision notes
- diagnostics, if any
- form lines, if any
- packet fingerprint

The audit packet must be generated from executed rule data, not from static
metadata alone.

## Where Values Are Logged

Values are logged in stages:

1. In memory during rule execution as `StageResult`.
2. In `final-legal-output.json` as narrative/audit packets.
3. In `legal-execution-graph.json` as graph nodes referencing the same packet
   fingerprints.
4. In country/language narrative Markdown files rendered from the same packets.

For a normal workspace, these generated files live under:

```text
~/taxes/<year>/outputs/analysis-steps/
  final-legal-output.json
  legal-execution-graph.json
  legal-execution-graph.mmd
  DE-de-narrative.md
  DE-en-narrative.md
  US-en-narrative.md
```

The durable audit log is not a separate manual file. It is the combination of
`final-legal-output.json` and `legal-execution-graph.json`. Narrative Markdown is
a human-readable rendering of the same data.

## StageResult Contract

`StageResult` is the first audit record created by execution.

It must include:

- `stage_id`
- actual `input_values`
- `input_fingerprints`
- actual `outputs`
- `output_fingerprints`
- diagnostics
- `precision_notes`
- result fingerprint

`StageResult.input_values` must have exactly the same keys as
`StageResult.input_fingerprints`.

`StageResult.outputs`, `StageResult.output_fingerprints`, and
`StageResult.precision_notes` must have exactly the same keys.

If those key sets differ, construction must fail.

## Fingerprints

Fingerprints make the audit trail tamper-evident and reproducible.

The engine must fingerprint:

- canonical facts
- rule inputs
- rule outputs
- stage results
- narrative/audit packets
- graph nodes that reference packet fingerprints

The graph must include each node's `audit_packet_fingerprint`. That value must
equal the fingerprint in the narrative/audit packet used to render that node.

If a graph node lacks the packet fingerprint, graph generation must fail.

## Math Steps

Math-step descriptions belong in the legal rule layer, not in templates.

Each rule must describe:

- which inputs were used
- the legal formula or decision applied
- intermediate legal sub-steps where relevant
- rounding policy
- resulting output values
- form lines affected

Templates may render math steps. Templates must not create math steps by
calculating, branching, or inferring values.

Good:

```text
Rule packet:
  input: de.capital.net_creditable_foreign_tax_total_eur = 150.00
  formula: min(net foreign tax, per-item/source cap)
  result: de.capital.foreign_tax_credit_applied_eur = 150.00
```

Bad:

```text
Template:
  {% set credit = [foreign_tax, cap] | min %}
```

## Template Contract

Each Jinja template is a renderer for one `rule_id`.

The template filename must equal the rule ID:

```text
tax_pipeline/narrative/templates/<rule_id>.jinja
```

The packet's `template_id` must equal `rule_id`.

The template may read only structured packet fields:

- title
- legal references
- authority URLs
- inputs
- math steps
- outputs
- form lines
- fingerprints and notes

The template must not:

- calculate tax
- choose legal branches
- synthesize missing inputs
- synthesize missing outputs
- use placeholder phrases such as "available before" or "produced by"
- depend on renderer-side sidecars that are not part of the executed packet

Missing packet data must fail closed before rendering.

## Narrative Outputs

Narrative outputs are human-readable audit workpapers.

Germany must support:

- `DE-de-narrative.md`
- `DE-en-narrative.md`

The United States must support:

- `US-en-narrative.md`

Each narrative must be an ordered rendering of executed rule packets. It must
flow in the same order as the legal graph. If a rule result feeds a form line,
the narrative should say which form and line receives the result.

The narrative's values must be exactly the values in the packet. If the packet
says an output is `29726.00`, the narrative may format it for readability, but
it must not change the value or recompute it.

## Execution Graph

`legal-execution-graph.json` is the machine-readable execution graph.

It must include:

- schema version
- source artifact
- ordered nodes
- edges from produced outputs to consumed inputs
- rule IDs
- country/language scope
- template IDs
- legal references
- authority URLs
- input keys
- output keys
- input fingerprints
- output fingerprints
- packet fingerprints
- form lines

The graph is not a second source of truth. It is a graph rendering of the same
audit packets used by the narratives.

`legal-execution-graph.mmd` is a visual projection of the JSON graph. It is
useful for order review but is not itself the audit source.

## Country And Language Scoping

Rule identity is legal identity. Language is presentation.

Within a country:

- one legal rule has one `rule_id`
- German and English renderings share the same `rule_id`
- language-specific packets may exist because the rendered text differs
- input/output values must remain the same across languages

Across countries:

- rule IDs should include country/year prefixes to avoid overlap
- treaty rules should use a treaty-specific prefix
- a U.S. rule must not reuse a Germany rule ID
- a treaty rule must not reuse a country rule ID

## Fail-Closed Rules

The engine must fail closed when:

- a required fact is missing
- a required input key has no value
- a rule produces an undeclared output
- a declared output is missing
- a required fingerprint is missing
- a rule ID is duplicated
- a template ID does not equal the rule ID
- a required template is missing
- a generic template is used for a legal rule
- a narrative packet is missing audit data
- a graph node lacks a matching packet fingerprint
- a renderer attempts to calculate legal math
- unsupported filing posture or unsupported document facts would affect tax

`0`, empty, and `not_applicable` are different states:

- `0` means the value was present and legally zero.
- empty means no data is present and is only valid when the rule explicitly
  allows an empty value.
- `not_applicable` means the rule does not legally apply and that posture was
  explicitly recorded.

The engine must not treat missing data as zero.

## Output Ownership

Generated outputs are audit artifacts, not future inputs.

The legal engine reads:

- user-provided raw files
- config files
- normalized facts
- reference data
- explicit tax positions/elections

The legal engine writes:

- analysis outputs
- final legal output
- legal execution graph
- narratives
- filing packages
- legal audit packages

Generated analysis outputs must not become hidden inputs for a later legal
calculation. If Germany computes a treaty packet that the U.S. needs in the same
run, the typed value must be passed in memory during that run. A JSON, CSV, or
Markdown packet may be written afterward for audit, but it must not be read back
as the source of legal truth.

## Tests And Enforcement

The test suite must enforce the architecture, not just example numbers.

Required test classes include:

- rule graph validation tests
- duplicate rule ID tests
- template naming tests
- missing template tests
- missing audit packet tests
- missing input/output value tests
- graph/narrative fingerprint equality tests
- no-placeholder narrative tests
- fixture chain integrity tests
- renderer no-legal-math tests

Tests should fail if:

- a public law rule is not registered
- a declared rule lacks legal references or authority URLs
- a declared rule lacks a legally named template
- two rules reuse a rule ID
- a narrative packet does not match the executed stage result
- a graph node does not match a narrative packet
- a template emits values not present in the packet
- renderer code recalculates legal math

## Contributor Rules

When adding or changing a tax rule:

1. Identify the law first.
2. Add or update the rule declaration.
3. Add legal references and authority URLs.
4. Add input keys and output keys.
5. Add or update the pure legal function.
6. Make the function produce or adapt to an executed audit packet.
7. Add or update the rule-named Jinja template.
8. Add tests that cite the relevant law.
9. Verify graph, packet, and narrative outputs agree.

If the law is uncertain, do not encode a guess as default behavior. Add an
explicit unsupported state, explicit election, or explicit tax position and make
the engine fail closed until the user chooses a supported posture.

## Trust Model

The engine cannot prove that the tax law itself is correct. It can prove that:

- every modeled rule cites an authority
- every calculation used declared inputs
- every calculation produced declared outputs
- every output can be traced to fingerprints
- every narrative value came from the executed packet
- renderers did not silently recalculate or invent legal values
- unsupported facts and postures do not silently disappear

That is the auditability target: a human, reviewer, or future agent can compare
law to code, code to executed packet, packet to graph, and packet to narrative
without guessing where a number came from.
