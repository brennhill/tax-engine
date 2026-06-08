# Audit-Lock Migration Plan

**Companion to**: `LOCK.md`. Where `LOCK.md` describes the target shape and locking mechanism, this document is the step-by-step plan to get there from today's code.

**Status**: design proposal — not started.

**Time estimate**: 1-2 weeks for Phase 0 (tooling). 1-2 weeks for Phase 1 (pilot). 2-3 months elapsed for Phases 2-7 (incremental § extraction, ~1 PR per §, can be parallelized). Phase 8 is independent and parallel.

**Invariants preserved at every commit**:
- Full test suite stays green (currently 943 passed / 1 skipped).
- Demo-workspace numerics are byte-identical (no functional changes during the refactor).
- Existing public API (`tax_pipeline.germany_2025_law.*`, `tax_pipeline.us_2025_law.*`) keeps working via re-export shims until Phase 7.

---

## Phase 0 — Lock infrastructure (no code reorganization)

**Goal**: build the audit-sign tooling and lock the existing files in place. ~80% of the audit benefit at ~10% of the cost.

### 0.1 — Build `audit-sign` CLI

Path: `tools/audit_sign.py`. uv-runnable. Subcommands:

```sh
audit-sign <file>                              # single-file unlock + re-sign
audit-sign --batch --reason "<text>" <files>   # batch unlock + re-sign
audit-sign --verify                            # check all hashes match (used by hook)
audit-sign --add <file>                        # initial sign (file enters .audit/hashes.toml)
audit-sign --status                            # list all locked files + last sign date
audit-sign --history <file>                    # show .audit/log/ entries for one file
```

Behavior:
- Computes SHA-256 of the file body (excluding frontmatter `audit_hash` line).
- Reads `.audit/hashes.toml`; updates the file's entry; writes back atomically (tempfile + rename + parent fsync, per invariant I9 in CLAUDE.md).
- Updates the in-file frontmatter `audit_hash`, `audited_by`, `audited_on` lines.
- Appends a `.audit/log/<ISO-timestamp>-<filename>.md` entry with: file path, old hash → new hash, diff (truncated to first 200 lines), human-supplied reason.
- Exits 0 on success, non-zero on validation failure (e.g. file doesn't exist, malformed frontmatter).

Tests: cover the round-trip (sign → verify), batch behavior, malformed-frontmatter handling, atomic-write contract.

### 0.2 — Pre-commit hook

Path: `.githooks/pre-commit` (or use existing `pre-commit` framework via `.pre-commit-config.yaml`).

Behavior:
- For every staged file in the `.audit/hashes.toml` keyset, recompute the body hash and compare against the recorded hash.
- On mismatch, reject the commit with a message naming the drifted file and pointing at `audit-sign`.
- Skipped when `--no-verify` is used; CI also runs `audit-sign --verify` on the full repo, so `--no-verify` commits get caught at the PR layer.

Wire-up: `make install-hooks` adds it to `.git/hooks/`.

### 0.3 — `.audit/` directory schema

```
.audit/
  hashes.toml           # one entry per locked file
  log/
    2026-05-04T09-15-22-p32.md
    2026-05-04T09-15-23-p33b.md
    ...
  README.md             # explains the lock workflow to anyone landing here
```

`hashes.toml` schema (per-file table):

```toml
["law/germany/2025/estg/p32.py"]
hash = "sha256:7d3a9f1b..."
audited_by = "brenn"
audited_on = "2026-05-03"
amendments = ["Steuerfortentwicklungsgesetz 2024, BGBl. 2024 I"]

["law/germany/2025/estg/p32_test.py"]
hash = "sha256:..."
audited_by = "brenn"
audited_on = "2026-05-03"
amendments = []
```

### 0.4 — CODEOWNERS

`.github/CODEOWNERS`:

```
# Existing repo files: default owner
* @brenn

# Legal-bearing files require explicit reviewer approval
/tax_pipeline/germany_2025_law.py    @brenn @de-tax-reviewer
/tax_pipeline/us_2025_law.py         @brenn @us-tax-reviewer
/tax_pipeline/treaty_2025_law.py     @brenn @de-tax-reviewer @us-tax-reviewer
/tax_pipeline/germany_2025_stages.py @brenn @de-tax-reviewer
/tax_pipeline/usa_2025_stages.py     @brenn @us-tax-reviewer
/.audit/                             @brenn
```

### 0.5 — Claude Code permissions

`.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Edit(./tax_pipeline/germany_2025_law.py)",
      "Edit(./tax_pipeline/us_2025_law.py)",
      "Edit(./tax_pipeline/treaty_2025_law.py)",
      "Edit(./tax_pipeline/germany_2025_stages.py)",
      "Edit(./tax_pipeline/usa_2025_stages.py)",
      "Edit(./.audit/**)",
      "Write(./.audit/**)",
      "Bash(audit-sign*)"
    ],
    "allow": [
      "Read(./tax_pipeline/**)",
      "Read(./.audit/**)"
    ]
  }
}
```

### 0.6 — Lock the existing high-stakes files

Run `audit-sign --add` on:
- `tax_pipeline/germany_2025_law.py`
- `tax_pipeline/us_2025_law.py`
- `tax_pipeline/treaty_2025_law.py`
- `tax_pipeline/germany_2025_stages.py`
- `tax_pipeline/usa_2025_stages.py`
- `tax_pipeline/germany_ordinary_2025_rules.py`
- `tax_pipeline/germany_capital_2025_rules.py`
- `tax_pipeline/us_2025_rules.py`
- `tax_pipeline/treaty_2025_rules.py`
- `tax_pipeline/germany_children_2025_rules.py`
- `tax_pipeline/germany_final_2025_rules.py`
- `tax_pipeline/germany_guenstigerpruefung_2025_rules.py`
- `tax_pipeline/germany_kap_projection_2025_rules.py`

### 0.7 — CI check

GitHub Actions step:

```yaml
- name: Verify audit hashes
  run: |
    uv run python -m tools.audit_sign --verify
```

### 0.8 — Soak period

Run for 2-4 weeks. Measure:
- How often does the lock fire on legitimate edits?
- How often does a human get blocked?
- Is the friction tolerable?
- Does the AI try to edit locked files (audit Claude transcripts)?

**Exit criterion**: lock catches at least one drift incident or false-positive; team agrees the friction is acceptable. If lock proves flaky or annoying, fix before Phase 1.

---

## Phase 1 — Pilot one § extraction

**Goal**: prove the per-§ refactor works. One PR, one §.

### 1.1 — Pick the pilot

`§ 22 Nr. 3 EStG` (Sonstige Einkünfte Freigrenze) is the right pilot:
- Single function (`other_income_22nr3_taxable_2025`)
- Single threshold constant (`OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR`)
- Single composition consumer (`DE25-04-OTHER-22NR3`)
- Already reviewed/fixed during the May 2 R-A audit (F-DE-1)
- No cross-§ dependencies inside the rule body

### 1.2 — Set up the new tree

```
law/
  __init__.py
  germany/
    __init__.py
    2025/
      __init__.py
      estg/
        __init__.py
        p22.py
        p22_test.py
```

`law/__init__.py` is empty. `law/germany/2025/__init__.py` re-exports `p22.py` so existing imports keep working:

```python
from law.germany._2025.estg.p22 import (
    OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
    other_income_22nr3_taxable_2025,
)
```

(Python doesn't allow `2025` as a module name without quotes; use `_2025` and re-export.)

### 1.3 — Move the function + constant + test

- Cut `other_income_22nr3_taxable_2025` from `germany_2025_law.py` to `p22.py`.
- Cut `OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR` to `p22.py`.
- Cut the relevant `Other22Nr3FreigrenzeTest` test to `p22_test.py`.
- In `germany_2025_law.py`, replace with a re-export:

```python
# § 22 Nr. 3 EStG Sonstige Einkünfte Freigrenze migrated to law/germany/_2025/estg/p22.py
# (audit-locked at the per-§ unit per LOCK.md / MIGRATION.md Phase 1).
from law.germany._2025.estg.p22 import (
    OTHER_INCOME_22NR3_FREIGRENZE_2025_EUR,
    other_income_22nr3_taxable_2025,
)
```

### 1.4 — Add frontmatter + audit-sign

Add the YAML frontmatter to `p22.py` (statute, contains, numeric_constants, audited_by/on/hash). Run `audit-sign --add law/germany/_2025/estg/p22.py` and `audit-sign --add law/germany/_2025/estg/p22_test.py`.

### 1.5 — Verify

```sh
uv run python -m pytest tests/ -q
make check
```

Both green; no demo numeric drift.

### 1.6 — Lock review

Try editing `p22.py` (in a separate branch) and confirm:
- Pre-commit hook catches the drift.
- Claude Code denies the edit per Layer 3.
- CI verify step also catches it.

### 1.7 — Measure

Time-to-audit `§ 22 Nr. 3 EStG` end-to-end (statute → code → test → numeric outcome) BEFORE and AFTER. Target: 50% reduction.

**Exit criterion**: pilot PR merges cleanly; audit time drops measurably; no demo drift; lock layer worked end-to-end. If any of those fail, pause and fix before Phase 2.

---

## Phase 2 — Extract leaf §s

**Goal**: extract the §s that don't import from other §s. Each §-file is one PR. Tests stay co-located. Re-export shim stays in the original file until Phase 7.

### Order (Germany side)

By dependency rank (none of these import from another § in our codebase):

1. `germany/_2025/estg/p9.py` (Werbungskosten)
2. `germany/_2025/estg/p9a.py` (Arbeitnehmer-Pauschbetrag)
3. `germany/_2025/estg/p10.py` (Sonderausgaben + Vorsorge caps)
4. `germany/_2025/estg/p24a.py` (Altersentlastungsbetrag)
5. `germany/_2025/estg/p33.py` (AB + zumutbare Belastung)
6. `germany/_2025/estg/p33b.py` (Behinderten-Pauschbetrag)
7. `germany/_2025/solzg/p3.py` (Soli rate)
8. `germany/_2025/solzg/p4.py` (Soli Freigrenze + Milderungszone)
9. `germany/_2025/bkgg/p6.py` (Kindergeld)
10. `germany/_2025/invstg/p18.py` (Vorabpauschale)
11. `germany/_2025/invstg/p20.py` (Teilfreistellung)

Each PR: cut the function(s) + constants + test; add frontmatter; `audit-sign --add`; re-export shim; tests stay green.

### Order (US side)

1. `usa/_2025/usc26/p152.py` (qualifying child / qualifying relative)
2. `usa/_2025/usc26/p911.py` (FEIE)
3. `usa/_2025/usc26/p1401.py` (SE OASDI + Medicare)
4. `usa/_2025/usc26/p3101.py` (Additional Medicare 0.9%)

These don't import other §s — extract first.

**Exit criterion**: every leaf § extracted, tests green, demo numerics unchanged. Each PR audit-signed.

---

## Phase 3 — Extract composing §s

**Goal**: extract §s that reference other §s. Order matters: extract the imported one before the importer.

### Germany dependency order

1. `p32.py` (Kinderfreibetrag, BEA-Freibetrag — depends on nothing)
2. `p32a.py` (Tariff — depends on nothing)
3. `p2.py` (GdE definition — depends on `p9`, `p9a`, `p10`, `p24a`)
4. `p32d.py` (Abgeltungsteuer + § 32d(5) FTC + § 32d(6) Günstigerprüfung — depends on `p32a` for Günstigerprüfung)
5. `p31.py` (Familienleistungsausgleich — depends on `p32`, `p32a`, `bkgg/p6`)
6. `p36.py` (Refund balance — depends on `p31` for Satz 4)

Each PR cuts one §, adds frontmatter, audit-signs.

### US dependency order

1. `p55.py` (AMT exemption + rate breaks)
2. `p56.py` (AMTI add-backs — may import from `p55`)
3. `p59.py` (AMTFTC — imports `p55`)
4. `p1411.py` (NIIT — imports `p911` for MAGI add-back)
5. `p24.py` (CTC + ODC + ACTC — imports `p152`, `p911` for MAGI)

**Exit criterion**: every law-bearing § extracted to `law/`. The original `germany_2025_law.py` and `us_2025_law.py` are now thin re-export shims (~50 lines each).

---

## Phase 4 — Extract compositions (Pipeline 2 stages)

**Goal**: move the rule bodies and stage declarations from `*_rules.py` and `*_stages.py` into per-stage files under `compositions/`.

### Mechanical pattern per stage

For each existing DE25-* / US25-* stage in `tax_pipeline/germany_2025_stages.py` / `tax_pipeline/usa_2025_stages.py` and its rule body in `*_rules.py`:

1. Create `law/germany/_2025/compositions/DE25-XX-NAME.py` (or `usa/_2025/compositions/US25-XX-NAME.py`).
2. Move the `LawStage` declaration + the `def deXX_xx_name(facts):` rule body into one file. Co-locate `OutputDeclaration` and `FormLineRef` declarations.
3. Imports come from the leaf § files: `from law.germany._2025.estg.p32 import kinderfreibetrag_for_child_2025`. The import graph is now the legal cross-reference graph.
4. Aggregator factories (`germany_ordinary_law_stages_2025`, `_RULE_FUNCTIONS` registries) update to point at the new locations. Keep them in `tax_pipeline/` as thin re-exports for now.
5. Co-located `DE25-XX-NAME_test.py` if there's a stage-specific test (most stages get tested via the leaf § tests + integration tests).
6. Frontmatter + `audit-sign --add`.

### Order

By PR-friendliness (smallest stages first):

Germany ordinary:
1. `DE25-04-OTHER-22NR3` (already extracted in Phase 1's leaf? No — Phase 1 extracted only the leaf §; the stage file is its consumer)
2. `DE25-ALTERSENTLASTUNGSBETRAG`
3. `DE25-SPENDENABZUG`
4. `DE25-AUSSERGEWOEHNLICHE-BELASTUNGEN`
5. `DE25-UNTERHALTSLEISTUNGEN`
6. `DE25-BEHINDERUNG-PAUSCHBETRAG`
7. `DE25-09-ORDINARY-SOLI`
8. `DE25-08-INCOME-TAX-TARIFF`
9. `DE25-07-TAXABLE-INCOME`
10. `DE25-10-ORDINARY-CREDITS`
11. (...DE25-00 through DE25-06B in any order)

Germany capital, kap_projection, guenstigerpruefung, final, children: same pattern.

US: extract `US25-CTC-AND-ODC`, `US25-AMT-*`, `US25-NIIT`, etc.

**Exit criterion**: every composition is its own file. `*_stages.py` and `*_rules.py` in `tax_pipeline/` are thin shims (~50 lines each, just registries).

---

## Phase 5 — Treaty + Rev. Proc.

### Treaty articles

Move treaty rules from `tax_pipeline/treaty_2025_law.py` and `treaty_2025_rules.py` to `law/treaty/dba_usa/art10.py`, `art11.py`, `art17.py`, `art23.py`, etc. Pub. 514 worksheet helpers go to `law/treaty/dba_usa/art10_pub514_average_tax.py`. Each Article gets its own file + frontmatter + audit-sign.

### Rev. Proc. inflation tables

Move the per-section inflation amounts to `law/usa/_2025/rev_proc/2024_40/p3_05.py` (CTC), `p3_11.py` (AMT), `p3_34.py` (FEIE), etc. The IRC § files import from these:

```python
# law/usa/_2025/usc26/p24.py
from law.usa._2025.rev_proc._2024_40.p3_05 import CTC_REFUNDABLE_CAP_2025_USD
```

The audit cadence diverges: when 2026 ships, `p3_05.py` becomes `rev_proc/2025_XX/p3_05.py` and the IRC § file's import flips to the new year. The IRC § file itself doesn't re-sign because the underlying statutory text didn't change — only the indexed amount.

**Exit criterion**: every treaty article and Rev. Proc. amount is its own file. `tax_pipeline/treaty_2025_law.py` is a thin shim.

---

## Phase 6 — Move types and helpers

### Types (dataclasses)

Move `JointOrdinaryAssessment2025`, `Child2025`, `USChildTaxCreditAssessment2025`, etc. to `law/germany/_2025/types.py` and `law/usa/_2025/types.py`. Single file per jurisdiction-year.

### Helpers

Move `q2`, `floor_euro`, `ceil_euro`, `round_cents`, Decimal validators to `law/_utils/`. These do NOT get locked — they don't carry legal math.

**Exit criterion**: every dataclass moved; helpers consolidated; the law tree contains only legal math + types + compositions.

---

## Phase 7 — Drop the re-export shims

**Goal**: stop maintaining `tax_pipeline/germany_2025_law.py` etc. as legacy entrypoints. Update all callers to import from `law/`.

### Callers to update

- `tax_pipeline/pipelines/y2025/germany_model.py` (the entry point)
- `tax_pipeline/pipelines/y2025/us_model.py`
- `tax_pipeline/pipelines/y2025/us_treaty_packet.py`
- `tax_pipeline/forms/germany.py`
- `tax_pipeline/forms/usa.py`
- `tax_pipeline/derivation/germany_2025_derivations.py`
- All `tests/test_*.py` files

### Mechanical migration

Use `sed` (or a one-off Python script) to rewrite imports:

```sh
# from tax_pipeline.germany_2025_law import X
# →
# from law.germany._2025 import X
```

Run tests, fix any breakage (most should be straightforward).

After all imports are migrated, delete the shim files in `tax_pipeline/`. Final state: `tax_pipeline/` contains only the engine (executors, runtime, paths, postures, etc.); `law/` contains all legal math.

**Exit criterion**: `tax_pipeline/germany_2025_law.py` doesn't exist. No imports from `tax_pipeline.germany_2025_*` exist anywhere except in the deleted-files list.

---

## Phase 8 — Rendered audit packets (parallel, independent)

**Goal**: per-stage Markdown audit document combining citation + code + test + numeric output.

Build a CLI:

```sh
audit-render <stage_id>
audit-render --all
```

Reads the `LawStage` declaration, the rule body, the co-located test, and the final numeric output for the demo workspace. Outputs a single Markdown file per stage at `.audit/packets/<STAGE_ID>.md` with:

- Stage ID + title + citations
- Statutory cross-references (with URLs)
- Rule body (syntax-highlighted code excerpt)
- Test cases with assertions and expected values
- Demo-workspace concrete output value
- `OutputDeclaration` form_line_refs (form lines this stage feeds)
- Audit-sign metadata for the underlying § files

Run weekly via CI; commit results; reviewers can read the packet without opening the codebase.

This phase is independent of Phases 1-7 and can start anytime after Phase 0.

---

## Risk callouts

| Risk | Mitigation |
|--|--|
| Mid-migration tests break and demo numerics shift | Every PR is tested. If demo drifts even by €0.01, revert and investigate. |
| Re-export shims hide circular imports | Use `from law.germany._2025.estg.p32 import ...`, never `from law.germany._2025 import *`. Explicit imports surface cycles. |
| Phase 4 rule-body extraction breaks the executor's `_RULE_FUNCTIONS` registry | Update the registry in the same commit that moves the rule body. Add a "verify all stages registered" test if not present. |
| Audit-sign tooling has a bug that corrupts `.audit/hashes.toml` | Atomic-write contract (I9), `audit-sign --verify` runs in CI; corruption surfaces immediately. |
| 80-PR rollout drags on for months and demoralizes reviewers | Batch PRs by sub-tree (all of `estg/p3X` together if they're truly independent). Cap at 1-2 PRs/week. |
| Cross-jurisdictional treaty rules don't fit into the §-per-file mold cleanly | Use `law/treaty/` as a separate sibling tree; a treaty article CAN import from both `germany/` and `usa/`. |
| Numeric constants get duplicated between `usc26/p24.py` and `rev_proc/2024_40/p3_05.py` | Constants live exclusively in the Rev. Proc. file; IRC § files import them. The IRC § stays stable across years; only the Rev. Proc. file rolls forward. |

---

## Rollback options

- **Phase 0 only**: revert by removing `.audit/`, `.githooks/pre-commit`, the Claude permissions deny rules, and the CODEOWNERS additions. No code change to revert.
- **Phase 1**: revert the single pilot PR. The `law/` tree disappears; everything is back in `tax_pipeline/`.
- **Phase 2-7**: each phase is composed of small PRs; revert any subset. As long as the re-export shims in `tax_pipeline/` are still in place (which they are until Phase 7), callers don't break.
- **Phase 7**: this is the irreversible commit (shims gone). Hold off on Phase 7 until the team is confident in the new shape.
- **Phase 8**: independent; start/stop without affecting the refactor.

---

## Schedule (illustrative)

| Week | Phase | Output |
|--|--|--|
| 1 | Phase 0.1-0.5 | `audit-sign` CLI + hooks + CODEOWNERS + Claude deny |
| 2 | Phase 0.6-0.8 | Existing big files locked; soak begins |
| 3-5 | Phase 0 soak | Lock catches drift / friction observed; tooling iterated |
| 6 | Phase 1 | `§ 22 Nr. 3 EStG` extracted; metrics measured |
| 7-8 | Phase 2 (DE leaves) | `p9, p9a, p10, p24a, p33, p33b, solzg/p3, solzg/p4, bkgg/p6, invstg/p18, invstg/p20` |
| 9 | Phase 2 (US leaves) | `p152, p911, p1401, p3101` |
| 10-11 | Phase 3 (DE composing) | `p32, p32a, p2, p32d, p31, p36` |
| 12 | Phase 3 (US composing) | `p55, p56, p59, p1411, p24` |
| 13-14 | Phase 4 (compositions) | `compositions/` populated; `*_rules.py` shrunken |
| 15 | Phase 5 | Treaty articles + Rev. Proc. extracted |
| 16 | Phase 6 | Types + helpers consolidated |
| 17 | Phase 7 | Re-export shims dropped; final state |
| Weeks 4+ (parallel) | Phase 8 | `audit-render` CLI + per-stage packets |

Real timeline likely 1.5-2× this depending on review cadence and other priorities. Phase 0 alone gives the bulk of the audit value, so even stopping after Week 5 leaves the codebase in a meaningfully better state.

---

## Decision points along the way

After Phase 0 soak:
- [ ] Lock layer is working (no false positives, no missed drift)?
- [ ] CODEOWNERS reviewers responsive?
- [ ] Friction tolerable?
- → Proceed to Phase 1 only if all three.

After Phase 1 pilot:
- [ ] Audit time measurably lower?
- [ ] No demo drift?
- [ ] Re-export pattern works cleanly?
- [ ] Frontmatter / audit-sign workflow ergonomic?
- → Proceed to Phase 2 only if all four. Otherwise, refine the pilot pattern before scaling.

After Phase 4 (compositions extracted):
- [ ] Import graph reads cleanly (legal cross-references visible)?
- [ ] Tests still green, no integration breakage?
- → Proceed to Phase 5 only if both. Otherwise pause and clean up.

Phase 7 (drop shims) is a hard commitment — only proceed when confident in the new shape.
