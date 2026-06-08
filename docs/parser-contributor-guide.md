# Parser Contributor Guide

This repo accepts parser additions through normal pull requests to the main codebase.

The contract is deterministic-first:

- add a classifier rule
- add a handler module
- add registry registration
- add conformance tests
- fail explicitly for unsupported shapes instead of guessing

## Required Steps For A New Parser

1. Add or extend the classifier rule.

   The classifier must identify the provider, document family, format, and doc type for the new document shape.

2. Add a deterministic handler.

   The handler must implement the existing extraction contract and return a `DocumentFacts` result with an explicit parser name and status.

3. Add registry registration.

   Register the handler by `(provider, document_family, format)` in the same style as the built-in handlers.

4. Add conformance tests.

   Every new parser PR should include:
   - a registry-resolution test
   - at least one extraction test on representative input
   - explicit unsupported / invalid-shape behavior where relevant

5. Update the public support docs.

   Add the provider/family/format row to:
   - [provider-support.md](provider-support.md)

## Required Contract

Your parser contribution should make these statements true:

- the classifier rule is explicit
- the registry registration is explicit
- the handler is deterministic for the supported document family
- conformance tests cover registry resolution and extraction behavior
- unsupported variants do not silently fall back to guessed facts

## Unsupported Behavior

Do not add heuristic "best effort" parsing that guesses fields from vaguely similar files.

If a provider/family/format combination is not supported:

- return the documented unsupported result
- keep the parser status explicit
- route the user toward manual or structured inputs instead of inventing facts

## Minimal PR Checklist

- classifier rule added or updated
- handler module added or updated
- registry registration added or updated
- extraction tests added
- provider-support docs updated
- no real taxpayer data added to fixtures

## Good First Targets

The intended public contribution pattern is exactly the kind of parser you mentioned, such as a new:

- `schwab` family extension
- broker export parser
- payroll-side statement parser

Examples already in-repo include deterministic handlers for:

- Schwab
- Coinbase
- DATEV / German payroll
- Finanzamt notices

Use those as structural examples, not as permission to broaden unsupported documents heuristically.
