# Code Auditability and Locking Plan

**Status**: design proposal — not implemented yet. Document captured 2026-05-03; revised 2026-05-03 (per-§ unit, not per-function).

**Goal**: make the legal-bearing code as easy as possible for a human auditor to verify against statutory source, and make accidental AI edits to vetted code structurally hard.

---

## 1. Hierarchy: mirror the statute, lock at the §

### Current shape

`tax_pipeline/germany_2025_law.py` (~1,800 lines), `germany_ordinary_2025_rules.py` (~900 lines), `usa_2025_stages.py` (~1,000 lines). Each file mixes constants, dataclasses, and many functions across multiple statutes. To audit "§ 32 Abs. 6 EStG Kinderfreibetrag" today a human navigates by `grep` and reads ~50 lines out of context.

### Proposed shape — one § per file

Lock at the **single statutory section** level: `germany/2025/estg/p32.py` contains everything § 32 EStG governs (Berücksichtigungsfähigkeit, Kinderfreibetrag + BEA, Übertragung, etc.) — typically 5-10 functions. `usa/2025/usc26/p24.py` contains § 24's CTC + ODC + ACTC together (~8 functions).

```
law/
  germany/
    2025/
      estg/
        p2.py        # GdE definition + § 2 Abs. 4 ordering
        p9.py        # Werbungskosten (5-7 fns)
        p9a.py       # Arbeitnehmer-Pauschbetrag (1-2 fns)
        p10.py       # Sonderausgaben incl. Vorsorge caps (8-12 fns)
        p22.py       # Sonstige Einkünfte incl. Nr. 3 Freigrenze (3-5 fns)
        p24a.py      # Altersentlastungsbetrag cohort table + lookup (3-4 fns)
        p31.py       # Familienleistungsausgleich + Satz 4 add-back (2-3 fns)
        p32.py       # Kinderfreibetrag, BEA-Freibetrag, Berücksichtigung (5-8 fns)
        p32a.py      # Tariff: Grundtarif + Splittingtarif (4-6 fns)
        p32d.py      # Abgeltungsteuer + Abs. 5 FTC + Abs. 6 Günstigerprüfung (8-12 fns)
        p33.py       # Außergewöhnliche Belastungen + zumutbare Belastung (4-6 fns)
        p33b.py      # Behinderten-Pauschbetrag table + Abs. 5 transferral (4-6 fns)
        p36.py       # Refund balance + § 36 Abs. 2 advance-payment netting (3-5 fns)
      solzg/
        p3.py        # Soli rate
        p4.py        # Freigrenze + Milderungszone (Satz 1, Satz 2)
      bkgg/
        p6.py        # Kindergeld monthly amount
      invstg/
        p18.py       # Vorabpauschale formula
        p20.py       # Teilfreistellung table + caps
    dba_usa/
      art10.py       # Portfolio dividend rate (2)(b), direct-investment (2)(a), 0% (3)(b)
      art11.py       # Interest
      art17.py       # Pensions
      art23.py       # Elimination of double taxation
    compositions/
      DE25-04-OTHER-22NR3.py            # imports estg/p22
      DE25-08-INCOME-TAX-TARIFF.py      # imports estg/p32a, p26b
      DE25-CHILDREN-CREDITS.py          # imports estg/p31, estg/p32, estg/p32a, bkgg/p6
      DE25-CHILDREN-DISABILITY.py       # imports estg/p33b
      DE25-22-FINAL-REFUND.py           # imports estg/p36, estg/p31
  usa/
    2025/
      usc26/
        p24.py       # CTC + ODC + ACTC (8 fns including phaseout, refundable cap, SSN gate)
        p55.py       # AMT exemption + rate breaks + phaseout (5-7 fns)
        p56.py       # AMTI add-backs (3-4 fns)
        p59.py       # AMTFTC (2-3 fns)
        p152.py      # Qualifying child / qualifying relative (4-6 fns)
        p911.py      # FEIE base + housing exclusion (4-6 fns)
        p1401.py     # SE OASDI + Medicare (3-5 fns)
        p1411.py     # NIIT rate + thresholds + § 1411(d)(1)(A) MAGI add-back (3-5 fns)
        p3101.py     # Additional Medicare 0.9% (2-3 fns)
      compositions/
        US25-CTC-AND-ODC.py             # imports usc26/p24, usc26/p152, usc26/p911
        US25-AMT-TENTATIVE.py           # imports usc26/p55, usc26/p56
        US25-NIIT.py                    # imports usc26/p1411, usc26/p911
      rev_proc/
        2024_40/
          p3_05.py   # CTC refundable cap $1,700 for 2025
          p3_11.py   # AMT exemption + rate breaks for 2025
          p3_34.py   # FEIE base $130,000 for 2025
  treaty/                               # cross-jurisdictional helpers if needed
    dba_usa/
      art10_pub514_average_tax.py
      art23_resourcing.py
```

### Conventions

- **One § per file.** File holds all functions, constants, types directly bound to that statutory section. Internal cross-references inside the same § are plain function calls; cross-§ references are explicit imports.
- **Frontmatter at the top of each file**:

  ```python
  """
  ---
  jurisdiction: DE
  tax_year: 2025
  statute: § 32 EStG
  url: https://www.gesetze-im-internet.de/estg/__32.html
  contains:
    - § 32 Abs. 1: Berücksichtigung von Kindern
    - § 32 Abs. 6 Satz 1: Kinderfreibetrag
    - § 32 Abs. 6 Satz 1 (BEA): BEA-Freibetrag
    - § 32 Abs. 6 Satz 4-6: Übertragung des Freibetrags
  numeric_constants:
    - KINDERFREIBETRAG_PER_PARENT_2025_EUR: 3336  # § 32 Abs. 6 Satz 1, Steuerfortentwicklungsgesetz 2024
    - BEA_FREIBETRAG_PER_PARENT_2025_EUR: 1464   # § 32 Abs. 6 Satz 1
  amended_by:
    - Steuerfortentwicklungsgesetz, BGBl. 2024 I (Kinderfreibetrag €3,336)
  audited_by: brenn
  audited_on: 2026-05-03
  audit_hash: sha256:7d3a9f1b...   # body hash; updated by audit-sign CLI
  ---
  """
  ```

- **Co-located tests**. `germany/2025/estg/p32.py` ↔ `germany/2025/estg/p32_test.py`. Tests are locked alongside the rule file (drift in the test = drift in the law assertion).
- **Helpers** (q2 / floor_euro / Decimal validators) live in `law/_utils/` and are NOT locked — they don't carry legal math.
- **Compositions** (existing DE25-* / US25-* stages) sit in `compositions/` and explicitly import their statutory dependencies. The import graph mirrors the legal cross-reference graph; a reader sees at a glance which statutes a composition pulls from.
- **Rev. Proc. inflation tables** get one file per published section (`usa/2025/rev_proc/2024_40/p3_05.py`). They have a different amendment cadence (annual) and audit-sign separately from the underlying IRC §.
- **Treaty articles** → `dba_usa/art10.py`, etc. — one Article per file.
- **Cross-jurisdictional** rules (e.g. Pub. 514 average-tax-rate worksheet) live in `treaty/dba_usa/` and import from both jurisdictions.
- **Aggregator at the year level** (`law/germany/2025/__init__.py`) re-exports the public surface so callers don't change imports during the migration.

### Why a § (not per-function, not per-Absatz, not per-composition)

| Unit | Files | Pros | Cons |
|--|--|--|--|
| Per-function | ~300 | One file = one rule; tightest possible audit | Grep noise, fights Python idioms, ~12× the file count |
| Per-Absatz | ~150 | Matches Bundestag amendments at the Absatz level | Many Absätze are 1-2 lines and pollute the tree |
| **Per-§** | **~80** | **Matches legislative amendment unit, Steuerberater audit unit, IDE navigability** | **Cross-§ refs become imports (this is wanted but adds noise)** |
| Per-composition | ~40 | Matches engine execution | Doesn't audit cleanly against a single legal source |

Per-§ wins on: **(a) matches how legislation amends** (Bundestag amends "§ 32 Abs. 6 EStG" via a named Steueränderungsgesetz; Congress amends "26 U.S.C. § 24" via a named Public Law), **(b) matches how Steuerberater / tax counsel reason** ("what does § 32 EStG say?" is the natural audit question), **(c) 5-10 functions per file is the right read-in-one-sitting size**, **(d) cross-statute references stay visible as imports**.

### Open structural questions

- **Where do dataclasses live** (`JointOrdinaryAssessment2025`, `Child2025`, etc.)? Proposal: `law/<jurisdiction>/<year>/types.py` — they're not legal math but they shape the audit surface. Single file per jurisdiction per year keeps types co-located.
- **Where do stage declarations live** (`OutputDeclaration`, `FormLineRef`, `LawStage`)? Proposal: alongside the composition file at `compositions/<STAGE_ID>.py`. The composition imports from the law leaves and declares its stage.
- **Multi-Absatz amendments**: when Bundestag amends both § 32 Abs. 6 and § 32 Abs. 4 in the same Steueränderungsgesetz, the unlock is one re-sign of `p32.py`. This is fine — the re-sign carries a rationale pointing at the named law. If only Abs. 6 changes but Abs. 4 stayed the same, the audit log entry says so.
- **Within-§ helpers**: e.g. `_ctc_phaseout_threshold_2025` is internal to § 24's logic. Stays inside `p24.py` as a `_underscore_prefixed` private function. No separate file.
- **Constants vs. functions**: both live in the same § file. E.g. `p55.py` contains `AMT_EXEMPTION_*` constants AND `_amt_exemption_for_filing_status_2025()`.

---

## 2. Lock mechanism: three defense-in-depth layers

The goal is to make accidental AI edits structurally hard, while keeping deliberate human edits a single explicit step.

### Layer 1 — `AUDIT-HASH` header + pre-commit hook

Every locked file carries a hash of its body. A pre-commit hook recomputes the hash and rejects commits where the recorded hash doesn't match the current content.

**File side** (in the frontmatter):

```python
"""
---
audit_hash: sha256:7d3a9f1b...
---
"""
```

**Sidecar side** (`.audit/hashes.toml`, single source of truth):

```toml
["law/germany/2025/estg/p32.py"]
hash = "sha256:7d3a9f1b..."
audited_by = "brenn"
audited_on = "2026-05-03"
amendments = [
  "Steuerfortentwicklungsgesetz 2024, BGBl. 2024 I",
]
```

The hook reads the sidecar, NOT the in-file frontmatter — so an AI that edits the body and updates the in-file hash header still fails the hook because it can't update the sidecar (which is in `permissions.deny`, see Layer 3).

The audit hash covers the **body**, not the frontmatter — so updating the `audited_by` / `audited_on` / `audit_hash` header doesn't itself trigger drift.

**Unlocking** is a human-only CLI:

```sh
audit-sign law/germany/2025/estg/p32.py
```

This is the explicit "I am taking ownership of this change" moment. The CLI prompts for a reason, recomputes the hash, updates `.audit/hashes.toml`, updates the in-file frontmatter, and creates a `.audit/log/<timestamp>-p32.md` entry recording the diff and the human-supplied rationale.

For batch updates (e.g. annual Rev. Proc. inflation roll-forward touching ~10 IRC §s):

```sh
audit-sign --batch --reason "Rev. Proc. 2025-XX § 3.05/3.11/3.34 inflation update" \
  law/usa/2025/usc26/p24.py \
  law/usa/2025/usc26/p55.py \
  law/usa/2025/rev_proc/2024_40/p3_*.py
```

One log entry, one human-supplied rationale, multiple files re-signed.

### Layer 2 — CODEOWNERS + branch protection

```
# .github/CODEOWNERS
/law/                                  @brenn
/law/germany/2025/estg/                @brenn @de-tax-reviewer
/law/usa/2025/usc26/                   @brenn @us-tax-reviewer
/law/treaty/dba_usa/                   @brenn @de-tax-reviewer @us-tax-reviewer
/.audit/                               @brenn
```

GitHub branch protection requires CODEOWNERS approval on PRs touching these paths. Pre-commit hooks can be bypassed with `--no-verify`; CODEOWNERS rules cannot without admin override.

### Layer 3 — Claude Code `permissions.deny`

In `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Edit(./law/**)",
      "Write(./law/**)",
      "Edit(./.audit/**)",
      "Write(./.audit/**)",
      "Bash(sed*./law/**)",
      "Bash(audit-sign*)"
    ],
    "allow": [
      "Read(./law/**)",
      "Read(./.audit/**)"
    ]
  }
}
```

The AI can read locked files (necessary for review and explanation) but cannot edit them or invoke `audit-sign`. To make a change, the AI proposes a diff to the human, who runs `audit-sign` themselves.

### Why three layers

| Threat | Layer 1 (hash) | Layer 2 (CODEOWNERS) | Layer 3 (Claude deny) |
|--|--|--|--|
| AI silently edits a locked § file | catches it | catches it on PR | prevents the edit |
| AI edits and updates the in-file hash | catches it (sidecar mismatch) | — | prevents the edit |
| Human pushes with `--no-verify` | bypassed | catches it | — |
| Human admin force-merges | bypassed | bypassed | — |
| AI runs `sed` via Bash | catches it | catches it on PR | denies the Bash call |

No single layer is sufficient; together they make accidental drift very hard.

---

## 3. Tradeoffs

### Costs

- **~80 files where there are ~25 today.** Manageable. Grep, git log, IDE search stay roughly the same as today. PR diffs span more files but each file is small.
- **Lock fires on the whole § when amended.** A Steuerfortentwicklungsgesetz that raises Kinderfreibetrag also forces re-audit of the rest of § 32 in the same session — actually *desired* (changes to one Absatz often affect others).
- **Lock friction is the feature, not a bug** — but adds ceremony to every numeric change, including legitimate ones. A 2025 → 2026 roll-forward might touch ~15 § files (down from ~40 if locked per-function).
- **Cross-statute compositions get explicit.** `DE25-CHILDREN-CREDITS` imports from § 31 + § 32 + § 32a + BKGG § 6 — verbose but legible. The import graph IS the legal cross-reference graph.
- **The `audit-sign` workflow is new tooling** that has to be built, tested, documented, and onboarded — its own minor project (~1-2 weeks).

### Benefits

- A human auditor opens **one file per § audited** and sees: cited statute, URL to source, amendment history, every numeric constant, every function bound to that §, every test, the audit-sign record. No grepping.
- Statutory cross-references manifest as Python imports — the legal dependency graph IS the import graph.
- Drift between code and statute becomes structurally visible (hash mismatch on PR) rather than hidden in a 1,800-line file diff.
- AI-induced drift is detectable AND preventable, not just detectable.
- The audit log (`.audit/log/`) becomes a permanent compliance artifact — every legal-math change has a signed record with a rationale that points at the named amending law.

---

## 4. Recommended phasing (overview)

See `MIGRATION.md` for the full step-by-step plan with exit criteria, risk callouts, dependency graph, and rollback options. Headline:

- **Phase 0** (~1-2 weeks): build lock infrastructure + lock the existing big files in place. No code reorg. ~80% of audit benefit.
- **Phase 1** (~1 PR): pilot one § extraction (`§ 22 Nr. 3` Freigrenze — smallest, least cross-ref).
- **Phase 2-7** (~50-80 PRs over 2-3 months): incremental § extraction, leaves first then composing §s, then compositions, then US, then Rev. Proc. + treaties.
- **Phase 8** (independent): rendered audit packets per stage as one Markdown document.

---

## 5. Don't do (or defer)

- **Don't refactor before piloting the lock.** The lock layer alone may close 80% of the audit gap. Refactoring before knowing the lock works is risk for unknown benefit.
- **Don't lock per-function.** ~300 files is too much grep noise; per-Absatz fragments many trivial sections; per-composition doesn't audit against a clean legal source. Per-§ is the right unit.
- **Don't rely on `chmod 444` or `git update-index --skip-worktree`** alone — neither survives clones, neither integrates with PR review.
- **Don't store hashes only in-file.** An AI that edits the body can also edit the in-file hash; the only way to detect that is a sidecar the AI can't touch.
- **Don't use external signing services or HSMs** unless the regulatory regime actually requires it. SHA-256 + git history is sufficient for "did this drift?".
- **Don't allow `git commit --no-verify` on legal-bearing paths** without a paper-trail comment. CODEOWNERS catches the missing-review case; a CI rule that rejects no-verify commits in legal paths catches the rest.
- **Don't lock helpers in `_utils/`.** They're not legal math. Locking them creates churn without audit value.

---

## 6. Open questions before committing to Phase 0

1. **Who is "the human" who unlocks?** A maintainer? A second pair of eyes? A licensed Steuerberater? The answer drives CODEOWNERS strictness.
2. **Are tests locked too?** Yes — tests cite authority and assert numerics; if the test drifts the law assertion drifts. `p32_test.py` locks alongside `p32.py`.
3. **What's the unlock cadence for inflation roll-forward?** Annual Rev. Proc. updates touch ~10 § files. Use `audit-sign --batch` with one rationale per Rev. Proc. publication. ~10-15 unlock events per year, not 50.
4. **Does the audit hash cover the frontmatter?** No — body only, so updating `audited_by`/`audited_on` doesn't itself trigger drift.
5. **Where does `audit-sign` live?** `tools/audit_sign.py` as a uv-runnable CLI. `make audit-sign FILE=...` for ergonomics.
6. **Hook behavior on first introduction.** When a file becomes locked, the initial `audit-sign` is the moment of "I trust this snapshot." First sign requires a CODEOWNERS-approved PR that adds the file to `.audit/hashes.toml`.
7. **What about Pipeline 2 stage declarations and rule-graph compositions** that aren't legal math but reference legal § files? Proposal: lock them at a coarser cadence (re-sign only when `OutputDeclaration` shape changes, not when the underlying § amount changes — the § file's hash carries the legal-amount drift).

---

## 7. Decision checkpoint

Before any code change, decide:

- [ ] Phase 0 pilot is worth ~1–2 weeks of tooling work?
- [ ] CODEOWNERS reviewers are identified and willing?
- [ ] Numeric-roll-forward friction (~15 unlock signs/year for inflation, batchable) is acceptable?
- [ ] Are the open questions above answered, or do we proceed with proposals as defaults?

If yes to all four, start Phase 0 with the locked-files pilot per `MIGRATION.md`. If no, the alternative cheaper path is the rendered audit-packet approach (Phase 8) on the current tree shape.
