# Local Intake Wizard Design

## Goal

Design a local web app that makes the repo usable for end users in the repo's main target case:

- Germany + U.S. cross-border individual filing
- payroll documents
- broker documents
- payments / prepayments

The wizard should replace manual folder placement and most direct config editing for normal users.

## Product Position

This is not a generic document cabinet and not yet a full consumer tax product.

It is a local intake wizard that:

1. creates or opens a private year workspace
2. gathers household and filing-posture inputs
3. gathers payment inputs
4. accepts uploaded documents
5. classifies and places them into the correct workspace buckets
6. runs workspace validation
7. runs the existing pipeline
8. points the user to the generated outputs

## Primary User

The only user that matters for this first version is:

- an end user with Germany + U.S. cross-border tax needs
- using a local machine
- not comfortable managing raw folder trees or config files by hand

## Platform

Primary target:

- local web app

Not in scope for this first version:

- hosted multi-user app
- desktop-native packaged app

## Core Product Decision

The first version should be a full intake wizard, not a thin workspace manager.

That means:

- the UI owns document placement
- the UI owns the core config collection
- users should not need to understand `~/taxes/<year>/raw/...` to succeed

## Required Flows

### 1. Create Or Open Workspace

The wizard must let the user:

- create a year workspace
- open an existing year workspace

Default location:

- `~/taxes/<year>/`

The UI may still expose the resolved path, but the path should not be the primary interaction model.

### 2. Household Intake

The wizard must collect:

- one person or married household
- Germany filing posture
- U.S. filing posture
- names and core identity data required by the engine

This should map into the existing config surfaces:

- `people.csv`
- `elections.csv`
- derived `profile.json`

### 3. Payments Intake

The wizard must collect at least:

- Germany tax prepayments
- U.S. estimated payments

This should map into:

- `payments.csv`

### 4. Document Upload And Placement

The wizard must support drag/drop or file-picker upload and then:

- classify the document if possible
- preview the detected provider / family / format
- place the file into the correct raw bucket automatically

Users should not need to know:

- `raw/germany/`
- `raw/us/`
- `raw/brokers/`
- `raw/equity_comp/`

The UI should choose those locations.

### 5. Unsupported Documents

If a parser is unsupported or the document cannot be confidently classified, the wizard must not silently guess.

It should instead show:

- unsupported or needs-review status
- what the user can do next
- whether this document can still live as evidence only
- whether the facts need to be entered through structured config or manual tax-position surfaces

### 6. Readiness / Validation

The wizard must expose the results of `validate_workspace` in UI form, including:

- missing config
- missing structured inputs
- unsupported or unreviewed documents
- whether the workspace is ready to run

### 7. Run Pipeline

The wizard must be able to invoke the existing pipeline and show:

- progress
- success / failure
- where to look next

At minimum it should point users to:

- `outputs/analysis-steps/`
- `outputs/forms/`
- `normalized/facts/REVIEW.md`

## Core Screens

### Workspace

- choose year
- create/open workspace
- show resolved path

### Household

- one person vs married
- Germany posture
- U.S. posture
- names and IDs

### Payments

- Germany prepayments
- U.S. estimated payments

### Documents

- upload area
- classification preview
- placement preview
- unsupported / review-required messaging

### Readiness

- validator summary
- missing items
- next actions

### Run

- run extraction / validation / pipeline
- show progress and output pointers

## Backend Boundary

The wizard should sit on top of the current engine. It should not rewrite the tax engine first.

So the intended architecture is:

- local web UI
- thin local app backend
- backend writes existing workspace files
- backend calls existing commands:
  - `tax-pipeline-scaffold`
  - `tax-pipeline-validate`
  - `tax-pipeline-run`

The wizard is therefore an orchestration and UX layer, not a replacement tax engine.

## Key UX Principle

Users should think in terms of:

- "this is my wage statement"
- "this is my broker 1099"
- "this is my Germany prepayment notice"

not in terms of:

- "which raw bucket should this file live in?"

## Non-Goals

Do not include in v1:

- full line-by-line return preparation UI
- embedded filing submission UI
- full document OCR/editor workflow
- support for every possible provider or filing posture
- generic all-taxpayer product scope outside the repo's main cross-border case

## Success Criteria

The wizard is successful if a normal end user can:

1. create a private workspace
2. answer the basic household / payment questions
3. upload documents without understanding the raw folder layout
4. see what was recognized and what still needs help
5. run validation and the pipeline
6. reach the existing analysis and filing outputs without touching CSVs manually
