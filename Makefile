# Makefile — Tax Year Pipeline
#
# This project has no CI; `make check` is the local CI surrogate.
# Run `make check` before every commit and before sending any PR.
#
# Targets:
#   check              full local CI: invariants + suite (default)
#   check-invariants   ONLY the structural invariant tests (I1..I12)
#   check-suite        full unittest discovery over tests/
#   help               list targets
#
# ============================================================================
# STRUCTURAL INVARIANTS (I1..I12)
# ============================================================================
# The engine guarantees twelve structural invariants. Eleven of them are
# enforced by dedicated test modules; I8 is enforced inline by
# `validate_result`; I11 is deferred to WS-4D (LegalValue). When you add a new
# invariant test, you MUST list it under `check-invariants` below — that
# friction is deliberate, so a human reviews every addition.
#
# Invariant -> test module:
#   I1  No legal-constant literal bypass
#       tests/y_agnostic/test_no_legal_constant_literal_bypass.py
#   I2  Final-output values trace to rule outputs
#       tests/y_agnostic/test_final_output_values_trace_to_rule_outputs.py
#   I3  Form-renderer lines match output declarations
#       tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py
#   I4  No silent-zero defaults in rules
#       tests/y_agnostic/test_no_silent_zero_defaults_in_rules.py
#   I5  No legal math outside the rule graph
#       tests/y_agnostic/test_no_legal_math_outside_rule_graph.py
#   I6  Fingerprint uses canonical value
#       tests/y_agnostic/test_fingerprint_uses_canonical_value.py
#   I7  Rule input tracking
#       tests/y_agnostic/test_rule_input_tracking.py
#   I8  validate_result (enforced inline; no dedicated test file)
#   I9  Final legal output atomic write
#       tests/y_agnostic/test_final_legal_output_atomic.py
#   I10 File reads specify utf-8 encoding
#       tests/y_agnostic/test_file_reads_specify_utf8_encoding.py
#   I11 Deferred to WS-4D (LegalValue) — not enforced yet
#   I12 Narrative templates index inputs by key
#       tests/y_agnostic/test_narrative_templates_index_inputs_by_key.py
#
# ============================================================================
# NEW-2 — LABEL-INVENTORY RATCHET (proposal New-2, 2026-05-10 review)
# ============================================================================
# Separate from I1..I12: every user-facing line / Zeile / Schedule X line N /
# Form NNNN line N reference outside the Y2/P5 form-schema TOMLs must either
# match a declared schema label OR carry an ELSTER-VERIFIED / IRS-VERIFIED /
# BMF-VERIFIED marker comment within 3 lines. A bootstrap baseline at
# `tests/data/label_inventory_baseline.json` acknowledges the existing
# pre-test references; the test fails when a NEW unverified reference appears
# OR when a baselined fingerprint goes stale. Closes the Anlage-SO /
# Form 1040 line 17 silent-wrong-label-for-years incident class. See the
# header of `tests/y_agnostic/test_label_inventory_verified.py` for the full
# posture.
#
#   New-2  Label inventory verified
#       tests/y_agnostic/test_label_inventory_verified.py
#
# ============================================================================
# W1.E / T3.2 — F-STRING BYPASS STRUCTURAL TEST (2026-05-11 plan)
# ============================================================================
# Companion to Y2/P5 + I3 + New-2: a contributor could sidestep both
# defenses by constructing a form-line label dynamically with an f-string
# (`f"Line {n}"`, `f"Zeile {n}"`). The label inventory scans literals
# and I3 scans `schema.label(...)` calls; neither sees a JoinedStr that
# carries a runtime variable. This test walks renderer modules under
# `tax_pipeline/forms/` and fails on any f-string whose constant prefix
# ends in a label-tag token (`Line `, `Zeile `, `Anlage `, etc.) and is
# followed by a `{expr}` placeholder. Allow-list via the marker comment
# `# label-fstring-ok: <reason>` (same line or line above). See
# CONTRIBUTING.md "F-string bypass — label construction" for the
# contributor flow.
#
#   W1.E  Renderer no f-string line labels
#       tests/y_agnostic/test_renderer_no_f_string_line_labels.py
#
# ============================================================================
# A4 — LAW-SHADOW LOCK (proposal A4, LOCK.md § 2 Layer 1)
# ============================================================================
# A separate structural protection on top of I1..I12: every signed file
# under law/ (29 sibling TOML data files + 52 shadow .py files) must match
# its SHA-256 digest in .audit/hashes.toml. Catches agents (and humans)
# silently editing vetted statutory state — re-sign with
# `python -m law.audit sign <path>` to record an intentional update.
#
#   A4  Law-audit signed files unchanged
#       tests/y_agnostic/test_law_audit_signed_files_unchanged.py
#
# ============================================================================
# KNOWN-RED INVARIANTS (Phase 4 in progress)
# ============================================================================
# Per docs/invariant-migration-plan.md, the following invariants are expected
# to fail on `main` until Phase 4 (WS-4C + WS-4D) lands:
#   - I2 (y_agnostic/test_final_output_values_trace_to_rule_outputs.py)
#   - I5 (y_agnostic/test_no_legal_math_outside_rule_graph.py)
# These are documented Phase-4-targeted failures; do NOT silence them.
# Once WS-4C and WS-4D land, both must turn green and stay green.
# ============================================================================

# Default to the uv-managed .venv interpreter so dependencies (jinja2,
# pytest, ...) are always present. Override with `make PYTHON=python3`
# if you are deliberately running outside the venv.
PYTHON ?= .venv/bin/python

# Bootstrap the .venv if it doesn't exist yet. Targets that exercise the
# engine depend on this so a fresh clone "just works" via `make check`.
.venv/bin/python: pyproject.toml uv.lock
	@command -v uv >/dev/null 2>&1 || { \
		echo "uv not found. Install from https://docs.astral.sh/uv/ — e.g. 'brew install uv'."; \
		exit 1; \
	}
	uv sync --extra dev
	@touch $@

INVARIANT_TESTS := \
	tests.y_agnostic.test_no_legal_constant_literal_bypass \
	tests.y_agnostic.test_final_output_values_trace_to_rule_outputs \
	tests.y_agnostic.test_form_renderer_lines_match_output_declarations \
	tests.y_agnostic.test_no_silent_zero_defaults_in_rules \
	tests.y_agnostic.test_no_legal_math_outside_rule_graph \
	tests.y_agnostic.test_fingerprint_uses_canonical_value \
	tests.y_agnostic.test_rule_input_tracking \
	tests.y_agnostic.test_final_legal_output_atomic \
	tests.y_agnostic.test_file_reads_specify_utf8_encoding \
	tests.y_agnostic.test_narrative_templates_index_inputs_by_key \
	tests.y_agnostic.test_law_audit_signed_files_unchanged \
	tests.y_agnostic.test_label_inventory_verified \
	tests.y_agnostic.test_renderer_no_f_string_line_labels

.PHONY: check check-invariants check-suite check-urls help resign resign-all audit-status sync

# Install / refresh project dependencies into the local .venv via uv.
# Idempotent — safe to run on every clone or after editing pyproject.toml.
sync: .venv/bin/python

check: .venv/bin/python check-invariants check-suite
	@echo ""
	@echo "make check: complete."
	@echo "Note: I2 and I5 are expected RED until Phase 4 (WS-4C + WS-4D) lands."
	@echo "See docs/invariant-migration-plan.md \xc2\xa78 and the header of this Makefile."

check-invariants: .venv/bin/python
	@echo "==> check-invariants: running structural invariants I1..I12"
	@echo "    (a failure here points at the broken invariant by test-module name)"
	$(PYTHON) -m unittest -v $(INVARIANT_TESTS)

check-suite: .venv/bin/python
	@echo "==> check-suite: running full unittest discovery over tests/"
	$(PYTHON) -m unittest discover tests

# A1 / W1.C — URL-liveness invariant. Separate cadence from check-suite /
# check-invariants because (a) it requires outbound HTTPS, (b) transient
# 4xx from upstream sites is not an engine bug. Skip-by-default in the
# main suite via the RUN_URL_CHECKS env gate; explicit invocation here.
check-urls: .venv/bin/python
	@echo "==> check-urls: HEAD-checking every cited authority URL"
	@echo "    (failures are real URL rot — see tests/data/url_health.json)"
	RUN_URL_CHECKS=1 $(PYTHON) -m unittest -v tests.y_agnostic.test_url_liveness_invariant

# ============================================================================
# A4 — LAW-SHADOW LOCK: contributor-facing convenience targets (proposal New-5)
# ============================================================================
# Editing a signed file under law/ without re-signing breaks
# `make check-invariants`. These targets surface the audit-sign CLI in the
# human contributor flow; see CONTRIBUTING.md "Updating a vetted statutory
# constant" for the full workflow.
#
#   make resign FILE=<path>   re-sign one file after an intentional edit
#   make resign-all           re-sign every signed law-shadow file
#   make audit-status         print signed / unsigned / drifted breakdown
# ============================================================================

# Re-sign a single law-shadow file after an intentional update.
# Usage: make resign FILE=law/germany/year_2025/bkgg/p6.toml
resign:
	@if [ -z "$(FILE)" ]; then \
		echo "Usage: make resign FILE=<path>"; \
		echo "Example: make resign FILE=law/germany/year_2025/bkgg/p6.toml"; \
		exit 1; \
	fi
	$(PYTHON) -m law.audit sign $(FILE)
	@echo ""
	@echo "Re-signed $(FILE). Run 'make check-invariants' to verify."

# Re-sign every signed law-shadow file. Use after a batch update
# (Rev. Proc. inflation roll, BMF Programmablaufplan re-issue).
resign-all:
	$(PYTHON) -m law.audit sign --all
	@echo ""
	@echo "Re-signed all law-shadow files. Run 'make check-invariants' to verify."

# Show current audit-sign status: signed / unsigned / drifted.
audit-status:
	$(PYTHON) -m law.audit status

help:
	@echo "Tax Year Pipeline — make targets"
	@echo ""
	@echo "  make sync               install/refresh deps into .venv via uv"
	@echo "  make check              full local CI (invariants + suite); default"
	@echo "  make check-invariants   ONLY the structural invariants (I1..I12)"
	@echo "  make check-suite        full unittest discovery over tests/"
	@echo "  make check-urls         A1 URL-liveness (weekly cadence; needs net)"
	@echo "  make help               this message"
	@echo ""
	@echo "Audit-sign (A4 law-shadow lock):"
	@echo "  make resign FILE=<path> re-sign one file after an intentional edit"
	@echo "  make resign-all         re-sign every signed law-shadow file"
	@echo "  make audit-status       print signed / unsigned / drifted breakdown"
	@echo ""
	@echo "Phase 4 in progress: I2 and I5 are expected RED until WS-4C + WS-4D land."
	@echo "See docs/invariant-migration-plan.md \xc2\xa78."
