# Provider And Parser Support

This page describes the current document-parser boundary of the public repo.

The parser layer is deterministic-first. Supported provider handlers extract structured facts from specific document families and formats. Unsupported document families do not crash the pipeline; they are marked as unsupported or routed to manual/derived inputs instead.

Provider support is narrower than tax support. A supported parser means the repo can extract facts from that document family. It does **not** mean every downstream tax posture or filing outcome involving those facts is implemented generically.

## Supported Deterministic Handlers

| Provider | Document family | Format | Status | Notes |
| --- | --- | --- | --- | --- |
| `datev` | `lohnsteuerbescheinigung` | `pdf` | Supported | Germany wage certificate extraction. |
| `germany_payroll` | `social_insurance_notice` | `pdf` | Supported | Germany payroll-side social-insurance notice extraction. |
| `finanzamt` | `prepayment` | `pdf` | Supported | Germany prepayment notice / confirmation extraction. |
| `finanzamt` | `steuerbescheid` | `pdf` | Supported | Germany tax assessment notice extraction. |
| `finanzamt` | `verlustvortrag` | `pdf` | Supported | Germany loss-carryforward notice extraction. |
| `coinbase` | `transactions` | `csv` | Supported | Coinbase transaction export parsing. |
| `coinbase` | `1099_da` | `pdf` | Supported | Coinbase 1099-DA summary extraction. |
| `schwab` | `1099_composite` | `pdf` | Supported | Schwab composite 1099 parsing. |
| `schwab` | `1099` | `csv` | Supported | Schwab machine-readable 1099 export parsing. |
| `schwab` | `transactions` | `csv` | Supported | Schwab transactions export parsing. |
| `schwab` | `limitation_notice` | `image` | Supported | OCR-backed image extraction for the limitation notice path. |
| `jpm` | `1099_b` | `pdf` | Supported | JPM 1099-B summary extraction. |
| `shareworks` | `statement` | `pdf` | Supported | Equity-comp statement parsing. |
| `tax_preparer` | `1040_packet` | `pdf` | Supported | Existing U.S. return packet extraction. |
| `tax_preparer` | `8879` | `pdf` | Supported | Existing U.S. signature packet extraction. |
| `n26` | `transfer_confirmation` | `pdf` | Supported | Transfer confirmation parsing for payment evidence. |
| `merchant` | `invoice` | `pdf` | Supported | Generic invoice extraction used by selected receipt paths. |
| `donation_platform` | `donation_receipt` | `eml` | Supported | Donation receipt email extraction. |

## Explicitly Unsupported / Manual Paths

| Provider | Document family | Format | Status | Notes |
| --- | --- | --- | --- | --- |
| `germany_bank` | `capital_certificate` | `pdf` | Explicitly unsupported parser | The current code registers this family as unsupported. Use the structured capital inputs or manual facts / tax-position surfaces instead of expecting direct parser support. |
| Unknown provider / family combinations | any | any | Unsupported document type | The pipeline emits an unsupported-document facts stub rather than silently guessing. |

## What Still Requires Manual Or Structured Inputs

The public engine still expects some reviewed structured inputs that are not automatically derived from raw documents in every case.

Examples:

- `normalized/reference-data/`
  - year constants, FX support, and similar reference inputs
- `normalized/derived-facts/`
  - jurisdiction-shaped support files like FTC support, capital summaries, and Germany capital support
- `outputs/tax-positions/`
  - explicit model assumptions and filing-position surfaces
- `config/manual_overrides.json`
  - work-use percentages, manual deductions, treaty posture toggles, and other judgment calls

This is intentional. The repo is auditable because these positions are explicit, not hidden.

## Failure Behavior

- Supported handler + valid document shape:
  - parser returns structured facts
- Supported handler + invalid or unreadable contents:
  - parser may emit a needs-review / needs-OCR style result depending on the handler
- Unsupported handler:
  - pipeline records an unsupported-document fact result instead of crashing

This means "unsupported parser" is not the same thing as "unsupported tax return." It often means the user must supply that part through a structured manual surface instead.

## Practical Guidance For New Users

- Put clearly supported documents into `raw/` and let the deterministic parser handle them.
- Treat unsupported provider families as manual or structured-input work from the start.
- Do not assume a parser exists just because a document belongs to a familiar institution.
- Check the generated `normalized/facts/REVIEW.md` after each run to see which documents were actually parsed and which need manual follow-up.

## Intake Wizard Behavior For Unsupported Documents

In the local intake wizard:

- supported uploads are classified and placed into the correct raw bucket automatically
- unsupported documents are shown as unsupported documents instead of being silently guessed
- the user can still store an unsupported document as evidence-only
- evidence-only files are kept with the workspace without being promoted into the normal parser manifest

That behavior is intentional. The wizard should reduce folder friction without hiding parser uncertainty.

## Related Docs

- Product boundary and filing-posture support: [support-matrix.md](support-matrix.md)
- Parser contributor workflow: [parser-contributor-guide.md](parser-contributor-guide.md)
- Public usage and workspace model: [README.md](../README.md)
