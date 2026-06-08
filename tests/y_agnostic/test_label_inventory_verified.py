"""Label-inventory structural test (proposal New-2 from
``.review/2026-05-10-platform-flexibility-review.md``).

The 2026-05-09 fixes (``ac72906``, ``a1f412d``) corrected two
user-facing line labels that had been wrong since the form-renderer was
first written:

- Form 1040 line 17 said "Schedule 2 line 1"; IRS specifies line 3.
- Anlage SO labels said "Zeilen 45-49 / 56-57" + "Zeile 66"; the 2025
  ELSTER form specifies 41-47 + 62.

Both labels survived multiple reviews; they were only caught because
the Y2/P5 schema migration forced a contributor to read every label
while moving them. The structural invariant I3 only protects
form-renderer schema labels (the first positional arg of
``schema.label("X")`` / ``legal_value_entry(...)``); the same drift
class lives in many other strings:

* ``notes=`` argument of ``FormEntry(...)`` in ``forms/germany.py`` and
  ``forms/usa.py`` — prose that quotes ``"Line N"`` /
  ``"Schedule 2 line 1"``.
* ``tax_pipeline/legal_audit/germany.py`` regex match strings that name
  ``§ 32a Abs. 1`` literally.
* Free-text Statutory-Order-Used prose in
  ``tax_pipeline/pipelines/y2025/germany_model.py:1318-1328`` (each
  bullet quotes a § and an Absatz).
* 9 narrative Jinja templates with hardcoded ``Zeile <N>`` /
  ``Line <N>`` references (``DE25-01-WAGE-INCOME.jinja:5,13`` →
  "Zeile 3 / 4" + "Anlage N Zeile 6", etc).
* User-facing profile JSON (``years/*/config/profile.json``)
  ``kap_lines`` arrays — ELSTER Zeile numbers as a hand-edited array.

This test walks every relevant file, regex-matches user-facing line /
Zeile / authority-line references, and classifies each:

1. **schema-covered** — the surrounding string matches a label
   declared in ``tax_pipeline/forms/schemas/*.toml``. Pass (the
   Y2/P5 / I3 invariant already protects it).
2. **VERIFIED** — within ``_PROXIMITY_LINES`` lines (above or below)
   there is a marker comment containing
   ``ELSTER-VERIFIED <YYYY-MM-DD>`` /
   ``IRS-VERIFIED <YYYY-MM-DD>`` /
   ``BMF-VERIFIED <YYYY-MM-DD>``. Pass.
3. **NEEDS-VERIFICATION** — same proximity, the marker is
   ``ELSTER-NEEDS-VERIFICATION <YYYY-MM-DD>`` (or IRS/BMF). Passes
   under Phase A posture (see below). Phase B posture will fail.
4. **unverified** — no marker. The test fails when an unverified hit
   appears that is NOT in the bootstrap baseline (see
   ``BASELINE_FINGERPRINTS`` below). Hits already in the baseline are
   treated as acknowledged-tech-debt and pass during the bootstrap
   window.

## Baseline / ratchet posture (Phase A)

The bootstrap inventory ran on 2026-05-10 surfaced ~1,360 user-facing
line/Zeile references that pre-date this test and have no marker. Per
proposal New-2:

  > Loud at first (every existing string needs marking). After the
  > bootstrap, the test only fires for new unmarked strings.

We adopt the **ratchet** posture: the bootstrap inventory is captured
in ``BASELINE_FINGERPRINTS`` (a frozenset of stable per-hit
fingerprints). The test fails when:

* a hit exists today whose fingerprint is NOT in
  ``BASELINE_FINGERPRINTS`` and is NOT VERIFIED / NEEDS-VERIFICATION /
  schema-covered. This is the regression case: a new unmarked
  reference was added. The contributor must either verify the label
  and add a ``# ELSTER-VERIFIED 2026-MM-DD`` marker, mark it
  ``NEEDS-VERIFICATION``, or move it to a form schema.

* the baseline contains fingerprints that no longer match any
  currently-unverified hit (stale baseline entries left behind after
  the hit was either deleted, moved into a form schema, or upgraded
  with a ``VERIFIED`` / ``NEEDS-VERIFICATION`` marker). The baseline
  must shrink as the backlog closes; stale entries must be removed.

The baseline is the explicit, reviewable record of every label in
this codebase that has not yet been verified against ELSTER / IRS /
BMF. Closing it is a New-2 follow-on: add VERIFIED markers, move
strings into form schemas, or fix wrong labels (with documented web
authority).

## Phase B (later)

Set ``_PHASE_B_STRICT = True`` once the backlog is closed.
``NEEDS-VERIFICATION`` markers then fail. The baseline frozenset
should be empty by Phase B.

Authority:
- Proposal: ``.review/2026-05-10-platform-flexibility-review.md`` New-2
  (lines 238-282).
- Anlage SO / Form 1040 line 17 fix: commits ``ac72906`` + ``a1f412d``.
- Y2/P5 schema-driven labels:
  ``tax_pipeline/forms/_schema.py`` and ``tax_pipeline/forms/schemas/*.toml``.

Stdlib only — ``re`` for regex, ``hashlib`` for fingerprinting, ``json``
for profile JSON parsing.
"""
from __future__ import annotations

import hashlib
import json
import re
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tax_pipeline.forms._schema import (
    iter_schema_form_ids,
    load_form_schema,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TAX_PIPELINE_ROOT = PROJECT_ROOT / "tax_pipeline"
NARRATIVE_TEMPLATES_ROOT = TAX_PIPELINE_ROOT / "narrative" / "templates"
LAW_SPEC_ROOT = TAX_PIPELINE_ROOT / "law_spec"
SCHEMAS_ROOT = TAX_PIPELINE_ROOT / "forms" / "schemas"
YEARS_ROOT = PROJECT_ROOT / "years"
BASELINE_PATH = (
    PROJECT_ROOT / "tests" / "data" / "label_inventory_baseline.json"
)

# Excluded directories under ``tax_pipeline/`` — these are NOT scanned
# because either Y2/P5 already protects them (form schemas) or they are
# vendored / generated. ``forms/schemas/`` is the schema source-of-
# truth; scanning it would create a false positive on every declared
# label.
_EXCLUDED_DIR_NAMES = frozenset({
    "schemas",
    "__pycache__",
})

# Test file itself is allowed to reference Zeile/Line in docstrings
# without markers — the test is meta about labels, not a renderer.
_EXCLUDED_FILES = frozenset({
    PROJECT_ROOT / "tests" / "test_label_inventory_verified.py",
})

# Proximity window: a VERIFIED / NEEDS-VERIFICATION marker comment must
# appear within this many lines (above OR below) the matched string.
# The proposal text says "within ~3 lines"; in practice a marker that
# cites its authority URL plus quoted source text comfortably spans 4-5
# lines, so we widen the window to 5 to keep markers self-contained
# (rather than forcing terse, citation-poor markers OR repeating the
# same marker keyword multiple times in one comment block). A 5-line
# window still keeps the marker visually adjacent to the cited string
# without weakening the contract that the marker must be "right next
# to" the reference it justifies.
_PROXIMITY_LINES = 5

# Regex pattern catalog. Each entry is a (name, compiled_regex) pair.
# Patterns are applied per-line; we want to catch user-facing
# line/Zeile references regardless of surrounding quoting / formatting.
#
# Patterns are deliberately *anchored to numeric or numeric-range
# tokens* so we don't trigger on bare nouns ("line" / "Zeile" in prose
# without a number). The Anlage SO incident class is specifically about
# numeric Zeile / Line drift.
_LABEL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # German Zeile / Zeilen — single or hyphen range, optional Anlage
    # prefix. Captures the matched text in group 0.
    ("zeile", re.compile(r"\bZeilen?\s+\d+(?:\s*[-–]\s*\d+)?(?:\s*(?:ff\.|f\.))?", re.IGNORECASE)),
    # English Line N / Line Na / Line N-M / Lines N through M.
    ("line", re.compile(r"\bLines?\s+\d+[a-z]?(?:\s*(?:through|[-–])\s*\d+[a-z]?)?", re.IGNORECASE)),
    # Schedule X line N (e.g., "Schedule 2 line 1", "Schedule D line 16").
    ("schedule_line", re.compile(r"\bSchedule\s+[0-9A-Z]+\s+line\s+\d+[a-z]?", re.IGNORECASE)),
    # Form NNNN line N (e.g., "Form 1040 line 17").
    ("form_line", re.compile(r"\bForm\s+\d{3,4}[A-Z]?\s+line\s+\d+[a-z]?", re.IGNORECASE)),
    # W-2 / 1099 "Box N" references (e.g., "W-2 box 3", "1099-DIV box
    # 1a", "Box 7"). Same Anlage-SO drift class — a wrong numeric Box
    # number on a W-2 / 1099 reference is a silent-wrong-label hazard
    # for years. Pattern catches an optional "W-?2 " or
    # "1099(-suffix)? " prefix followed by [Bb]ox + whitespace + a
    # numeric token with optional single-letter suffix (Box 1a, Box 2a,
    # Box 8z). Letter-only Form 8949 boxes (Box D, H, K) are NOT in
    # scope — those are letter codes, not numeric labels subject to the
    # drift class. Identifier-style ``box_1a_usd`` / ``us_1099_box``
    # forms are skipped because they have no whitespace between "box"
    # and the number.
    ("w2_or_1099_box", re.compile(
        r"(?:\bW-?2\s+|\b1099(?:-?\w+)?\s+)?\b[Bb]ox\s+\d+[a-z]?"
    )),
)

# Marker regexes — the date format is YYYY-MM-DD; the marker family
# names which authority was consulted.
_VERIFIED_MARKER_RE = re.compile(
    r"\b(?:ELSTER|IRS|BMF)-VERIFIED\s+\d{4}-\d{2}-\d{2}\b"
)
_NEEDS_VERIFICATION_MARKER_RE = re.compile(
    r"\b(?:ELSTER|IRS|BMF)-NEEDS-VERIFICATION\s+\d{4}-\d{2}-\d{2}\b"
)


@dataclass(frozen=True)
class _Hit:
    """A single line/Zeile reference found in a scanned file."""

    file_path: Path
    line_number: int  # 1-based
    line_text: str
    matched_text: str
    pattern_name: str

    def display_path(self) -> str:
        try:
            return str(self.file_path.relative_to(PROJECT_ROOT))
        except ValueError:
            return str(self.file_path)

    def fingerprint(self) -> str:
        """Stable per-hit fingerprint for the baseline ratchet.

        Composed of:
          * relative file path (so a rename forces a re-baseline);
          * pattern name (so a new pattern catches what it should);
          * the SHA-256 of ``stripped_line_text + matched_text`` (line
            number is omitted so unrelated edits above the hit don't
            invalidate the fingerprint, but the content of the line is
            captured so a hit silently moving to a different line of
            the same file still matches).

        The fingerprint is a hex string suitable for JSON storage.
        """
        body = f"{self.line_text.strip()}\x00{self.matched_text}".encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()
        return f"{self.display_path()}::{self.pattern_name}::{digest[:16]}"


@dataclass(frozen=True)
class _ClassifiedHit:
    """A hit plus its classification."""

    hit: _Hit
    classification: str  # schema_covered | verified | needs_verification | unverified
    reason: str = ""


def _is_excluded_dir(path: Path) -> bool:
    return any(part in _EXCLUDED_DIR_NAMES for part in path.parts)


def _iter_scan_files() -> Iterable[Path]:
    """Yield every file the label inventory should scan."""
    # Python sources under tax_pipeline/, except forms/schemas/.
    for path in sorted(TAX_PIPELINE_ROOT.rglob("*.py")):
        if _is_excluded_dir(path.relative_to(TAX_PIPELINE_ROOT)):
            continue
        if path in _EXCLUDED_FILES:
            continue
        yield path
    # Jinja narrative templates.
    if NARRATIVE_TEMPLATES_ROOT.exists():
        for path in sorted(NARRATIVE_TEMPLATES_ROOT.rglob("*.jinja")):
            yield path
    # Law-spec markdown.
    if LAW_SPEC_ROOT.exists():
        for path in sorted(LAW_SPEC_ROOT.rglob("*.md")):
            yield path
    # Workspace profile JSON files (years/*/config/profile.json).
    if YEARS_ROOT.exists():
        for path in sorted(YEARS_ROOT.glob("*/config/profile.json")):
            yield path


def _load_schema_labels() -> frozenset[str]:
    """Return the frozenset of every declared form-schema label.

    Y2/P5 / I3 already protects these labels — they are the
    source-of-truth string the renderer emits, and the schema TOML is
    the single edit point for a label fix. Any line-reference string
    that *equals* a schema label is automatically considered
    schema-covered.
    """
    labels: set[str] = set()
    for form_id in iter_schema_form_ids():
        schema = load_form_schema(form_id)
        for line in schema.lines:
            labels.add(line.label.strip())
    return frozenset(labels)


def _scan_file(path: Path) -> list[_Hit]:
    """Return all line/Zeile reference hits in ``path``."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    hits: list[_Hit] = []
    for lineno, line_text in enumerate(text.splitlines(), start=1):
        for pattern_name, pattern in _LABEL_PATTERNS:
            for match in pattern.finditer(line_text):
                hits.append(
                    _Hit(
                        file_path=path,
                        line_number=lineno,
                        line_text=line_text,
                        matched_text=match.group(0),
                        pattern_name=pattern_name,
                    )
                )
    return hits


def _surrounding_lines(
    path_text: str, line_number: int, window: int
) -> str:
    """Return the concatenation of lines [line_number - window,
    line_number + window] from ``path_text`` (1-based)."""
    all_lines = path_text.splitlines()
    lo = max(1, line_number - window)
    hi = min(len(all_lines), line_number + window)
    return "\n".join(all_lines[lo - 1 : hi])


def _classify_hit(
    hit: _Hit,
    *,
    file_text: str,
    schema_labels: frozenset[str],
) -> _ClassifiedHit:
    """Classify a single ``_Hit`` against the inventory rules."""
    # 1. schema-covered: the matched regex hit must coincide with a
    #    known schema label. The schema label is the canonical full
    #    label string ("Anlage SO Zeilen 41-47"); the bare regex hit
    #    is its suffix ("Zeilen 41-47"). We require:
    #      (a) the schema label appears as a substring of the line, AND
    #      (b) that schema-label occurrence *ends at the same offset*
    #          as the regex hit (so the hit really is the tail of a
    #          full label, not a numerically-different sub-line like
    #          "Line 8z" matching "Line 8" loosely).
    # This rejects the loose substring match that flagged "Line 1b" as
    # schema-covered just because the renderer declares "Line 1" — the
    # two are different IRS sub-lines.
    hit_end = hit.line_text.find(hit.matched_text)
    if hit_end >= 0:
        hit_end = hit_end + len(hit.matched_text)
        for label in schema_labels:
            label_pos = hit.line_text.find(label)
            while label_pos != -1:
                label_end = label_pos + len(label)
                if label_end == hit_end and label.endswith(hit.matched_text):
                    return _ClassifiedHit(
                        hit=hit,
                        classification="schema_covered",
                        reason=f"matches schema label {label!r}",
                    )
                label_pos = hit.line_text.find(label, label_pos + 1)
    # 2/3. Look for VERIFIED or NEEDS-VERIFICATION markers within
    #      proximity.
    window = _surrounding_lines(file_text, hit.line_number, _PROXIMITY_LINES)
    if _VERIFIED_MARKER_RE.search(window):
        return _ClassifiedHit(hit=hit, classification="verified")
    if _NEEDS_VERIFICATION_MARKER_RE.search(window):
        return _ClassifiedHit(hit=hit, classification="needs_verification")
    # 4. Unverified — failure unless baselined.
    return _ClassifiedHit(hit=hit, classification="unverified")


def _classify_all() -> list[_ClassifiedHit]:
    schema_labels = _load_schema_labels()
    classified: list[_ClassifiedHit] = []
    for path in _iter_scan_files():
        try:
            file_text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for hit in _scan_file(path):
            classified.append(
                _classify_hit(
                    hit, file_text=file_text, schema_labels=schema_labels
                )
            )
    return classified


def _load_baseline() -> frozenset[str]:
    """Load the bootstrap baseline of acknowledged-unverified hits.

    The baseline file is a JSON object with two top-level keys:
      * ``fingerprints``: array of hit fingerprints (see
        ``_Hit.fingerprint``).
      * ``metadata``: object documenting the bootstrap (date, source
        commit, count).

    Returns the frozenset of fingerprint strings. Returns an empty
    frozenset if the baseline file is missing (Phase B / closed
    backlog state).
    """
    if not BASELINE_PATH.exists():
        return frozenset()
    with BASELINE_PATH.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError(
            f"label inventory baseline at {BASELINE_PATH} must be a JSON object"
        )
    fingerprints = payload.get("fingerprints", [])
    if not isinstance(fingerprints, list):
        raise ValueError(
            f"label inventory baseline {BASELINE_PATH}: "
            "'fingerprints' must be a JSON array of strings"
        )
    return frozenset(str(fp) for fp in fingerprints)


def _format_new_unverified_failure(hits: list[_ClassifiedHit]) -> str:
    """Build the actionable failure message for NEW unverified hits
    (the regression case)."""
    lines: list[str] = [
        "",
        f"Label inventory: {len(hits)} NEW unverified line/Zeile reference(s).",
        "",
        "These references are not in the bootstrap baseline at",
        f"  {BASELINE_PATH.relative_to(PROJECT_ROOT)}",
        "and have NO marker. This is the regression case proposal New-2",
        "(`.review/2026-05-10-platform-flexibility-review.md`) exists to",
        "catch: a new user-facing line/Zeile reference shipped without",
        "any marker recording who verified it.",
        "",
        "Fix one of four ways:",
        "  (a) verify the label against the cited authority and add a",
        "      `# ELSTER-VERIFIED 2026-MM-DD` (or `# IRS-VERIFIED`, ",
        "      `# BMF-VERIFIED`) marker within 3 lines, OR",
        "  (b) add a `# ELSTER-NEEDS-VERIFICATION 2026-MM-DD` marker",
        "      (Phase A posture: temporarily acceptable; future Phase B",
        "      tightening rejects this), OR",
        "  (c) move the label to `tax_pipeline/forms/schemas/<form_id>.toml`",
        "      so Y2/P5 / I3 protects it, OR",
        "  (d) if you are intentionally adding to the bootstrap backlog,",
        "      append the hit's fingerprint to ",
        f"      {BASELINE_PATH.relative_to(PROJECT_ROOT)} (NOT recommended:",
        "      prefer (a) or (b)).",
        "",
    ]
    for ch in hits[:80]:
        snippet = ch.hit.line_text.strip()
        if len(snippet) > 140:
            snippet = snippet[:137] + "..."
        lines.append(
            f"  {ch.hit.display_path()}:{ch.hit.line_number}: "
            f"({ch.hit.pattern_name}) match={ch.hit.matched_text!r}"
        )
        lines.append(f"      | {snippet}")
        lines.append(f"      fingerprint: {ch.hit.fingerprint()}")
    if len(hits) > 80:
        lines.append(f"  ... and {len(hits) - 80} more.")
    lines.append("")
    return "\n".join(lines)


def _format_stale_baseline_failure(stale_fingerprints: list[str]) -> str:
    """Build the actionable failure message for baseline entries that
    no longer match any current hit (the baseline must shrink, not go
    stale)."""
    lines: list[str] = [
        "",
        f"Label inventory baseline: {len(stale_fingerprints)} stale "
        "fingerprint(s).",
        "",
        f"  {BASELINE_PATH.relative_to(PROJECT_ROOT)}",
        "",
        "These fingerprints do not match any current hit — the line",
        "they recorded was either deleted or edited beyond recognition.",
        "Remove these stale fingerprints from the baseline so the",
        "remaining list is an honest record of unverified labels.",
        "",
    ]
    for fp in stale_fingerprints[:40]:
        lines.append(f"  {fp}")
    if len(stale_fingerprints) > 40:
        lines.append(f"  ... and {len(stale_fingerprints) - 40} more.")
    lines.append("")
    return "\n".join(lines)


class LabelInventoryVerifiedTest(unittest.TestCase):
    """Label-inventory ratchet test.

    Phase A posture: a baseline JSON file captures the bootstrap
    inventory of acknowledged-unverified line/Zeile references. The
    test fails when:
      * a NEW unverified reference appears (not in the baseline,
        not VERIFIED, not NEEDS-VERIFICATION, not schema-covered);
      * a baselined fingerprint no longer matches any current hit
        (the baseline must shrink as the backlog closes, not go
        silently stale).

    Phase B posture (future): set ``_PHASE_B_STRICT = True`` once the
    NEEDS-VERIFICATION backlog is empty and the baseline is empty.
    """

    # Phase B switch: set True once the baseline is empty and every
    # marker is VERIFIED.
    _PHASE_B_STRICT = False

    def test_no_new_unverified_label_references(self) -> None:
        """Every regex hit must classify as schema_covered, verified,
        needs_verification, OR be present in the bootstrap baseline."""
        classified = _classify_all()
        baseline = _load_baseline()
        new_unverified: list[_ClassifiedHit] = []
        for ch in classified:
            if ch.classification != "unverified":
                continue
            if ch.hit.fingerprint() in baseline:
                continue
            new_unverified.append(ch)
        if new_unverified:
            self.fail(_format_new_unverified_failure(new_unverified))

    def test_baseline_has_no_stale_entries(self) -> None:
        """Every fingerprint in the baseline must match a current
        *unverified* hit. Stale entries (left after a label was
        deleted, rewritten, moved to a schema, OR upgraded to a
        VERIFIED marker) must be removed so the baseline shrinks as
        the backlog closes."""
        baseline = _load_baseline()
        if not baseline:
            return  # baseline empty -> nothing to check
        # Only currently-unverified hits keep a baseline entry alive.
        # When a contributor adds a VERIFIED / NEEDS-VERIFICATION
        # marker (or moves the label into a schema), the hit's
        # classification changes and its fingerprint must be removed
        # from the baseline so the inventory is honest.
        current_unverified_fingerprints = {
            ch.hit.fingerprint()
            for ch in _classify_all()
            if ch.classification == "unverified"
        }
        stale = sorted(baseline - current_unverified_fingerprints)
        if stale:
            self.fail(_format_stale_baseline_failure(stale))

    def test_phase_b_strict_rejects_needs_verification(self) -> None:
        """Phase B (``_PHASE_B_STRICT = True``): every
        NEEDS-VERIFICATION marker must be upgraded to VERIFIED."""
        if not self._PHASE_B_STRICT:
            self.skipTest(
                "Phase A posture: NEEDS-VERIFICATION markers are accepted "
                "during the bootstrap window. Set _PHASE_B_STRICT=True to "
                "enforce VERIFIED-only."
            )
        classified = _classify_all()
        pending = [c for c in classified if c.classification == "needs_verification"]
        if pending:
            self.fail(
                f"Phase B strict mode: {len(pending)} NEEDS-VERIFICATION "
                "marker(s) remain. Verify each against the cited authority "
                "and replace the marker with `<AUTHORITY>-VERIFIED "
                "YYYY-MM-DD`."
            )

    def test_phase_b_strict_rejects_baseline(self) -> None:
        """Phase B: the baseline must be empty (every former
        bootstrap entry has been resolved)."""
        if not self._PHASE_B_STRICT:
            self.skipTest(
                "Phase A posture: bootstrap baseline is non-empty by design."
            )
        baseline = _load_baseline()
        self.assertEqual(
            len(baseline),
            0,
            "Phase B strict mode: bootstrap baseline must be empty "
            "(every former entry resolved via VERIFIED, NEEDS-VERIFICATION "
            "removal, schema move, or label fix).",
        )

    def test_inventory_is_runnable(self) -> None:
        """The classifier must produce at least the schema-covered
        count (sanity check — if every count is zero, the scanner
        broke or the schemas vanished)."""
        classified = _classify_all()
        self.assertGreater(
            len(classified),
            0,
            "label inventory found zero references — the scanner is broken",
        )


if __name__ == "__main__":
    unittest.main()
