# Flexibility Architecture Design

## Context

The public repo is now safe to use as a `2025` engine with an external-first workspace model, a synthetic demo, and explicit support boundaries. The next architectural goal is not immediate `2026` support. The priority is to make the codebase flexible enough to:

- support more filing postures cleanly
- support more raw-document parsers through straightforward pull requests
- leave a clean seam for eventual multi-year expansion

The first new filing posture target is U.S. `married_joint`, including:

- ordinary joint filing for two U.S. taxpayers
- elected joint filing with an NRA spouse

Parser growth should remain in-repo through pull requests, not through an external plugin ecosystem.

## Goals

- Make filing posture a first-class architecture concept instead of a set of hidden flags.
- Make parser/provider additions a stable, documented contributor surface.
- Preserve the current `2025` engine while introducing a clear year boundary for future expansion.
- Keep unsupported combinations failing loudly instead of producing misleading outputs.

## Non-Goals

- Full multi-year implementation beyond `2025`
- Broad plugin/package loading for third-party parsers
- Generic support for arbitrary household sizes beyond the current `single` and `married` model
- Immediate implementation of every Germany or U.S. filing status

## Design Summary

The flexibility work should be built around three explicit extension seams:

1. filing posture seam
2. provider/parser seam
3. year seam

The recommendation is to keep `2025` as the only implemented year while extracting interfaces that allow the current engine to grow without accumulating posture-specific or provider-specific branching inside the central runtime.

## 1. Filing Posture Seam

### Problem

Right now, filing posture behavior is spread across:

- jurisdiction loaders
- law helpers
- form renderers
- entry-sheet generation
- runtime gating

That makes each new posture feel like a cross-repo patch instead of an isolated capability.

### Design

Introduce explicit posture modules per jurisdiction. These modules are responsible for:

- validating the required household shape
- selecting which people participate in the assessment
- shaping facts for the law layer
- choosing which outputs are legal to render
- blocking unsupported surfaces loudly

Illustrative structure:

- `tax_pipeline/postures/germany/single.py`
- `tax_pipeline/postures/germany/married_joint.py`
- `tax_pipeline/postures/germany/married_separate.py`
- `tax_pipeline/postures/usa/single.py`
- `tax_pipeline/postures/usa/mfs_nra_spouse.py`
- `tax_pipeline/postures/usa/married_joint.py`

The lower-level `*_2025_law.py` modules remain the rule libraries. Posture modules become the orchestration layer that decides how those rules apply to a household and which filing surfaces can be emitted.

### Expected Benefits

- New posture support becomes additive rather than invasive.
- Unsupported posture/output combinations become explicit and testable.
- The support matrix can map directly to posture modules instead of hand-written caveats.

## 2. Provider / Parser Seam

### Problem

The repo already has a registry-backed parser system, but it is not yet a polished public contributor surface. Adding a new parser still requires understanding too much implicit project structure.

### Design

Treat the provider registry as the official public parser extension seam for pull requests.

Every parser contribution should follow one documented contract:

- classifier rules determine the provider, family, and format
- a provider handler implements deterministic extraction for that exact descriptor
- the handler returns structured facts or an explicit needs-review / unsupported result
- no silent heuristics or fallback guessing

The contributor workflow should be standardized:

1. add or update classifier rules
2. implement the provider handler
3. register it in the provider registry
4. add fixtures and parser conformance tests
5. update provider support docs

### Required Public Surface

This seam should be documented through:

- a parser contributor guide
- a provider handler template or minimal example
- parser conformance tests that every new provider must satisfy
- explicit rules for unsupported/failure behavior

### Expected Benefits

- Contributors can add parser support without reverse-engineering the whole repo.
- Supported parser coverage becomes easier to audit.
- Provider growth stays deterministic and reviewable.

## 3. Year Seam

### Problem

The repo is explicitly `2025`-only, but year specificity is currently embedded directly in filenames, imports, and runtime assumptions. That is acceptable today, but it creates friction for future `2026` work.

### Design

Introduce a year registry without claiming multi-year support yet.

The registry should map a year to:

- law modules
- posture support declarations
- reference-data expectations
- output renderers
- demo and validation expectations

Only `2025` needs to be registered initially. Unsupported years should continue to fail loudly unless they are scaffold-only.

This gives the codebase an explicit answer to:

- what this year supports
- which modules belong to it
- which postures and outputs are legal

### Expected Benefits

- `2026` can be added as a new registered year instead of another round of repo-wide special casing.
- Year-specific logic becomes easier to locate and review.

## Data Model Implications

The current shared household model remains intentionally narrow:

- one person: `single`
- two married people: `married`

Filing posture remains jurisdiction-specific and should continue to be declared in structured config.

Illustrative posture rows in `config/elections.csv`:

- `germany,filing_status,single`
- `germany,filing_status,married_joint`
- `germany,filing_status,married_separate`
- `usa,filing_status,single`
- `usa,filing_status,mfs_nra_spouse`
- `usa,filing_status,married_joint`

For U.S. `married_joint`, the posture layer must distinguish:

- ordinary joint filing for two U.S. taxpayers
- elected joint filing with an NRA spouse

That distinction belongs in explicit posture assumptions and validation, not hidden defaults.

## Error Handling

The repo should continue to prefer loud failure over ambiguous fallback:

- unsupported filing posture -> explicit validation error
- posture supported at the law layer but not at the forms/output layer -> explicit block
- unknown provider/family combination -> unsupported parser result
- invalid household shape for a posture -> explicit validation error

This keeps the public contract honest.

## Testing Strategy

The flexibility work should add dedicated tests at each seam:

### Filing posture tests

- posture validation for supported and unsupported combinations
- posture-specific output blocking
- end-to-end posture smoke tests for supported surfaces

### Parser seam tests

- registry resolution
- parser conformance tests
- unsupported parser behavior
- classifier-to-handler integration

### Year seam tests

- registry resolution for `2025`
- loud failure for unsupported years
- posture availability by year

## Recommended Execution Order

1. extract a jurisdiction posture interface
2. move the current supported postures behind that interface
3. implement U.S. `married_joint`
   - ordinary joint filing
   - elected joint return with NRA spouse
4. publish the parser contributor contract and test harness
5. introduce a year registry that still only registers `2025`
6. expand provider coverage and additional postures from the new seams

## Why This Approach

This design deliberately avoids overbuilding a generic tax platform too early.

It creates just enough architecture to:

- add real filing postures cleanly
- accept more parser contributions through PRs
- keep the `2025` engine stable
- prepare for `2026` later without pretending it exists now

That is the shortest path to a more flexible public repo without losing the auditability and explicitness that the current codebase has already gained.
