"""``law.audit`` — sign / verify CLI for the law shadow tree.

Implements proposal A4 from
``.review/2026-05-08-platform-flexibility-review.md`` and the lock-mechanism
design in ``LOCK.md`` § 2 Layer 1.

Goal: turn "did the AI agent silently change a vetted constant?" from
"answerable only via ``git log -p``" into a structural CI check.

Usage::

    python -m law.audit sign <path1> [<path2> ...]   # add/refresh registry entries
    python -m law.audit sign --all                   # discover & sign every signable file
    python -m law.audit verify                       # CI check; exits non-zero on drift
    python -m law.audit status                       # signed / unsigned / drifted

Signable scope:

* ``law/**/*.{py,toml}`` — F1 statutory-constant TOMLs + shadow ``.py``
  files (the original A4 scope).
* ``tax_pipeline/law_spec/**/*.md`` — authority-bearing law-matrix
  markdown (added by slice W2.C / T3.3, 2026-05-11).

Files outside these two roots (``tests/``, ``tax_pipeline/forms/``,
the repo-root ``README.md`` / ``CONTRIBUTING.md`` / ``LOCK.md``) are
not signed by A4 — the lock scope is authority-bearing law content.

Registry: ``.audit/hashes.toml`` (single source of truth, checked into git;
git history is the audit log). Per LOCK.md § 2:

* The audit hash covers the file content with the in-file ``audit_hash:``
  frontmatter line normalised to a fixed sentinel — so updating
  ``audit_hash: pending`` to the real digest does not itself trigger drift.
  Any change to ANY other byte (numeric value, citation URL, comment,
  body code) triggers drift on the next ``verify``.

* ``.py`` shadow files carry their hash in two places: the registry (CI
  check) and the in-file ``audit_hash:`` frontmatter (visible at the file
  level). ``sign`` keeps both in sync. The registry is the source of truth
  per LOCK.md § 2 Layer 1.

* ``.toml`` data files have no frontmatter; the registry is the only record.

Suggested pre-commit hook (NOT installed automatically per A4 deferred
scope) — add to ``.git/hooks/pre-commit`` to fail commits that drift::

    #!/usr/bin/env bash
    python -m law.audit verify || {
        echo "audit-verify failed; re-sign with python -m law.audit sign <path>"
        exit 1
    }

Stdlib only: ``hashlib`` for SHA-256, ``tomllib`` for read, manual TOML
emit for deterministic output (no third-party ``tomli_w`` dependency).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Repository root resolved relative to this file. ``law/audit.py`` lives at
# ``<repo>/law/audit.py``, so the repo root is the parent of this file's
# parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
LAW_DIR = REPO_ROOT / "law"
# Slice W2.C / T3.3 (2026-05-11): the law-spec markdown tree is a SECOND
# signable root. The 40 markdown files under
# ``tax_pipeline/law_spec/<juri>/<year>/`` carry authority-bearing prose
# (inline ``gesetze-im-internet.de`` / ``law.cornell.edu`` URLs, restated
# § citations, "Authority" + "Implemented By" + "Test Coverage"
# sections). They are NOT legal math — they are the human-readable law
# matrix that ``tax_pipeline/legal_audit/`` renders. The third-pass
# legal-accuracy audit (2026-05-04) hand-verified each file against the
# cited authority; A4 now structurally enforces that signed state, so an
# agent silently editing a § citation or authority URL trips
# ``make check-invariants``.
LAW_SPEC_DIR = REPO_ROOT / "tax_pipeline" / "law_spec"
REGISTRY_PATH = REPO_ROOT / ".audit" / "hashes.toml"


def _signable_roots() -> tuple[Path, ...]:
    """Return the directories whose contents are eligible for signing.

    Resolved at call time (not module-load time) so tests that
    ``mock.patch.object(audit, "LAW_DIR", <temp>)`` see the patched
    value. The scope is intentionally narrow: only authority-bearing
    content (numeric law data, shadow law-math modules, law-spec
    authority markdown) is locked. Tests, arbitrary documentation, and
    form-renderer modules are NOT signed by A4 — they have other
    defenses (label-inventory ratchet, I3, etc.).
    """
    return (LAW_DIR, LAW_SPEC_DIR)

# Sentinel inserted in place of the actual hash digest when computing the
# canonical body hash. Both ``audit_hash: pending`` and ``audit_hash:
# sha256:abcd...`` normalise to the same byte sequence for hashing, so the
# act of writing the digest into the file does not itself change its hash.
_AUDIT_HASH_SENTINEL = "audit_hash: <NORMALISED_FOR_SIGNING>"

# Files that carry an in-file ``audit_hash:`` frontmatter line. The CLI
# rewrites this line on ``sign`` so the file records its own signed state.
_FRONTMATTER_FILE_SUFFIXES = (".py",)

# Files that DON'T carry frontmatter — their hash is the raw bytes.
#
# ``.md`` files joined this set with slice W2.C / T3.3 (2026-05-11): the
# law-spec markdown is hashed as raw bytes. No in-file marker is written
# (Option A in the slice brief): the registry at ``.audit/hashes.toml``
# is the trusted root. Adding an HTML-comment marker would only restate
# what the registry already records and would itself change the bytes,
# adding complexity for no audit gain.
_RAW_FILE_SUFFIXES = (".toml", ".md")

# Files we'll never sign — caches, generated artifacts, internal helpers
# that LOCK.md § 1 explicitly excludes from locking.
_NEVER_SIGN_NAME_PREFIXES = ("__pycache__",)
_NEVER_SIGN_NAMES = ("__init__.py",)
_NEVER_SIGN_REL_PATHS = (
    # Per LOCK.md § 1 Convention: "Helpers (q2 / floor_euro / Decimal
    # validators) live in law/_utils/ and are NOT locked — they don't carry
    # legal math."
    Path("_utils/constants.py"),
    Path("_utils/money.py"),
    # The CLI itself is not legal math; it is the lock mechanism.
    Path("audit.py"),
)

# Test-file suffix excluded from the default sign / discovery scope. LOCK.md
# § 6 Q2 recommends locking tests too ("if the test drifts the law assertion
# drifts"), but proposal A4's scope is the 29 TOMLs + their sibling shadow
# .py files; expanding to tests is a future workspace extension. Surface a
# clear marker so a future session can flip this to enabled if desired.
_TEST_FILE_SUFFIX = "_test.py"


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _normalise_for_hash(text: str) -> bytes:
    """Return the bytes used to compute the canonical SHA-256.

    For files that carry an ``audit_hash:`` frontmatter line, the line is
    replaced with a fixed sentinel so writing the real digest into the
    file does not change the file's own hash. For files with no such line
    (TOML data files), the bytes pass through unchanged.

    The substitution is conservative: only the FIRST occurrence of a line
    starting with ``audit_hash:`` (any leading whitespace) is rewritten;
    if the file has none, the bytes pass through unchanged.
    """
    lines = text.splitlines(keepends=True)
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("audit_hash:"):
            # Preserve leading whitespace + line ending; replace the body.
            indent_len = len(line) - len(stripped)
            indent = line[:indent_len]
            # Detect line ending: the original may have had \n or \r\n.
            if line.endswith("\r\n"):
                eol = "\r\n"
            elif line.endswith("\n"):
                eol = "\n"
            else:
                eol = ""
            lines[idx] = f"{indent}{_AUDIT_HASH_SENTINEL}{eol}"
            break
    return "".join(lines).encode("utf-8")


def compute_hash(path: Path) -> str:
    """Compute the canonical SHA-256 hex digest for ``path``.

    The digest is computed over the file's UTF-8 bytes after normalising
    any in-file ``audit_hash:`` line to a fixed sentinel (see
    ``_normalise_for_hash``).

    Returns the bare hex digest WITHOUT the ``sha256:`` prefix; callers
    that want the prefixed form (matching the in-file frontmatter format
    documented in LOCK.md § 2 Layer 1) prepend it themselves.
    """
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256(_normalise_for_hash(text)).hexdigest()


# ---------------------------------------------------------------------------
# Registry I/O
# ---------------------------------------------------------------------------


def _load_registry() -> dict[str, dict[str, str]]:
    """Load ``.audit/hashes.toml`` as ``{rel_path: {field: value}}``.

    Returns an empty dict if the registry doesn't exist yet (first run).
    """
    if not REGISTRY_PATH.exists():
        return {}
    with REGISTRY_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    out: dict[str, dict[str, str]] = {}
    for key, entry in data.items():
        if isinstance(entry, dict):
            out[key] = {k: str(v) for k, v in entry.items()}
    return out


def _format_registry(entries: dict[str, dict[str, str]]) -> str:
    """Emit ``.audit/hashes.toml`` deterministically (sorted by path).

    Hand-rolled because we forbid ``tomli_w`` / external deps. Emits one
    table per signed file with the LOCK.md § 2 Layer 1 fields:
    ``hash``, ``audited_by``, ``audited_on``.
    """
    header = (
        "# .audit/hashes.toml — registry of signed law-shadow files.\n"
        "# Maintained by `python -m law.audit`. Per LOCK.md § 2 Layer 1\n"
        "# this file is the source of truth: drift between any signed\n"
        "# file and its registered hash fails `make check-invariants`.\n"
        "# Re-sign after intentional updates with:\n"
        "#   python -m law.audit sign <path>\n"
    )
    lines: list[str] = [header]
    for rel_path in sorted(entries):
        entry = entries[rel_path]
        # Quote the table header conservatively — TOML allows bare keys
        # only for ASCII identifiers. File paths contain ``/`` so we
        # always use a quoted key.
        lines.append(f'\n["{rel_path}"]\n')
        # Stable field order matches LOCK.md § 2 Layer 1 sample.
        for field in ("hash", "audited_by", "audited_on"):
            if field in entry:
                value = entry[field].replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{field} = "{value}"\n')
        # Any extra fields (forward-compatibility) emit alphabetically
        # AFTER the canonical three.
        for field in sorted(entry):
            if field in ("hash", "audited_by", "audited_on"):
                continue
            value = entry[field].replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{field} = "{value}"\n')
    return "".join(lines)


def _write_registry(entries: dict[str, dict[str, str]]) -> None:
    """Persist the registry atomically (temp file + rename + parent fsync).

    Mirrors invariant I9: atomic file writes use a unique temp filename,
    f.Sync(), os.Rename, and parent fsync. The registry is a critical
    audit artifact — a torn write would leave the lock state ambiguous.
    """
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = _format_registry(entries)
    # Use NamedTemporaryFile for a unique name in the destination
    # directory (so os.rename is a same-filesystem atomic move).
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=REGISTRY_PATH.parent,
        prefix=".hashes.toml.",
        suffix=".tmp",
        delete=False,
    ) as tf:
        tf.write(text)
        tf.flush()
        os.fsync(tf.fileno())
        tmp_path = Path(tf.name)
    os.replace(tmp_path, REGISTRY_PATH)
    # Parent-directory fsync so the rename itself is durable.
    try:
        dir_fd = os.open(str(REGISTRY_PATH.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        # Some filesystems (notably some on macOS) don't support directory
        # fsync; we tolerate this rather than failing the sign.
        pass


# ---------------------------------------------------------------------------
# In-file frontmatter rewrite
# ---------------------------------------------------------------------------


def _update_frontmatter_hash(path: Path, digest: str) -> bool:
    """Rewrite the in-file ``audit_hash:`` line to ``sha256:<digest>``.

    Returns True if the file was modified, False if the file has no
    ``audit_hash:`` line (TOML data files) or already records this digest.

    Atomic: temp file + rename + parent fsync, mirroring invariant I9.
    """
    text = path.read_text(encoding="utf-8")
    new_value = f"audit_hash: sha256:{digest}"
    lines = text.splitlines(keepends=True)
    changed = False
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("audit_hash:"):
            indent_len = len(line) - len(stripped)
            indent = line[:indent_len]
            if line.endswith("\r\n"):
                eol = "\r\n"
            elif line.endswith("\n"):
                eol = "\n"
            else:
                eol = ""
            new_line = f"{indent}{new_value}{eol}"
            if new_line != line:
                lines[idx] = new_line
                changed = True
            break
    if not changed:
        return False
    new_text = "".join(lines)
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tf:
        tf.write(new_text)
        tf.flush()
        os.fsync(tf.fileno())
        tmp_path = Path(tf.name)
    os.replace(tmp_path, path)
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    return True


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------


def _to_rel_path(path: Path) -> str:
    """Return the path relative to repo root, with forward slashes.

    The registry stores paths as POSIX-style relative strings so the
    registry is portable between platforms (the test that opens the
    registry on Linux CI must read the same string a macOS contributor
    wrote).
    """
    p = path.resolve()
    rel = p.relative_to(REPO_ROOT)
    return rel.as_posix()


def _signable_root(path: Path) -> Path | None:
    """Return the signable root (``law/`` or ``tax_pipeline/law_spec/``)
    that contains ``path``, or ``None`` if ``path`` is outside every
    signable root.

    Centralising the root check keeps the two-root scope explicit: a file
    is only a candidate for signing if it lives inside ONE of the
    declared signable roots. Anything outside (``tests/``, ``forms/``,
    repo-root ``README.md``, ``CONTRIBUTING.md``) is structurally
    excluded — A4's scope is authority-bearing law content, not arbitrary
    documentation.
    """
    resolved = path.resolve()
    for root in _signable_roots():
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return root
    return None


def _is_signable(path: Path) -> bool:
    """Return True if ``path`` is a candidate for signing.

    A file is signable when it satisfies ALL of:

    * It lives under one of the declared signable roots (``law/`` or
      ``tax_pipeline/law_spec/``) — see ``_signable_root``.
    * Its suffix is in the signable-suffix tuple (``.py`` / ``.toml``
      under ``law/``; ``.md`` under ``tax_pipeline/law_spec/``).
    * It is not a ``__init__.py`` package marker, a ``__pycache__``
      artifact, or a test file (LOCK.md § 1, § 6 Q2; A4 scope).
    * It is not on the per-root exclusion list (``law/audit.py`` itself,
      ``law/_utils/`` helpers).

    Suffixes are gated by root: ``.md`` is signable only under
    ``tax_pipeline/law_spec/`` (the slice W2.C / T3.3 scope); ``.md``
    files elsewhere (the root ``README.md``, ``CONTRIBUTING.md``,
    ``LOCK.md``, etc.) stay unsigned.
    """
    if not path.is_file():
        return False
    if path.suffix not in _FRONTMATTER_FILE_SUFFIXES + _RAW_FILE_SUFFIXES:
        return False
    if path.name in _NEVER_SIGN_NAMES:
        return False
    if path.name.endswith(_TEST_FILE_SUFFIX):
        # Test files are out of A4 scope; see _TEST_FILE_SUFFIX comment.
        return False
    for part in path.parts:
        if part in _NEVER_SIGN_NAME_PREFIXES:
            return False
    root = _signable_root(path)
    if root is None:
        return False
    rel = path.resolve().relative_to(root)
    if root == LAW_DIR:
        for excluded in _NEVER_SIGN_REL_PATHS:
            if rel == excluded:
                return False
        # Only .py and .toml under law/ — markdown under law/ (if it
        # ever appears) is not in A4 scope.
        if path.suffix not in (".py", ".toml"):
            return False
        return True
    if root == LAW_SPEC_DIR:
        # Only markdown under tax_pipeline/law_spec/ — the directory
        # contains nothing else today, but be explicit so a future
        # __init__.py or sidecar TOML doesn't silently enter A4 scope.
        if path.suffix != ".md":
            return False
        return True
    return False


def _discover_all_signable() -> list[Path]:
    """Walk every signable root and return every signable file.

    Includes:

    * Under ``law/`` — the 29+ sibling TOML data files (F1
      statutory-constant migration's vetted values + citations) and the
      52+ shadow ``.py`` files (carrying the legal-math + frontmatter
      that cites authority for each constant). Pure-citation ``.py``
      files (with ``numeric_constants: []``) are also signed: their
      citation URLs and authority text are vetted state too.

    * Under ``tax_pipeline/law_spec/`` (added by slice W2.C / T3.3,
      2026-05-11) — the 40 authority-bearing markdown files at
      ``<juri>/<year>/*.md`` consumed by ``tax_pipeline/legal_audit/``
      to render the law matrix. They carry inline statute URLs and
      restate § citations in prose, so silent edits would mis-state
      the cited authority undetectably without A4.
    """
    out: list[Path] = []
    seen: set[Path] = set()
    for root in _signable_roots():
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path in seen:
                continue
            if (
                path.suffix in _FRONTMATTER_FILE_SUFFIXES + _RAW_FILE_SUFFIXES
                and _is_signable(path)
            ):
                out.append(path)
                seen.add(path)
    return sorted(out)


# ---------------------------------------------------------------------------
# Sign / verify / status implementations
# ---------------------------------------------------------------------------


def _git_user_email() -> str:
    """Resolve the signing identity from ``git config user.email``.

    Falls back to ``$USER@<hostname>`` if git isn't configured. The
    identity is recorded in the registry as ``audited_by`` per LOCK.md
    § 2 Layer 1 ("audited_by = "brenn"").
    """
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        email = result.stdout.strip()
        if email:
            return email
    except (OSError, subprocess.SubprocessError):
        pass
    return f"{os.environ.get('USER', 'unknown')}@{os.uname().nodename}"


def sign(paths: Iterable[Path]) -> int:
    """Sign each path in ``paths``: register hash + rewrite in-file marker.

    Returns 0 on success, non-zero on first error (caller prints).
    """
    today = _dt.date.today().isoformat()
    signer = _git_user_email()
    entries = _load_registry()
    paths_list = [Path(p).resolve() for p in paths]
    if not paths_list:
        print("audit-sign: no paths supplied (use --all to sign every law/ file).", file=sys.stderr)
        return 2
    for path in paths_list:
        if not path.exists():
            print(f"audit-sign: {path} does not exist.", file=sys.stderr)
            return 2
        if not _is_signable(path):
            print(
                f"audit-sign: {path} is not a signable A4 file "
                "(must be law/**/*.py, law/**/*.toml, or "
                "tax_pipeline/law_spec/**/*.md, excluding __init__.py "
                "and law/_utils/).",
                file=sys.stderr,
            )
            return 2
    for path in paths_list:
        rel = _to_rel_path(path)
        digest = compute_hash(path)
        entries[rel] = {
            "hash": f"sha256:{digest}",
            "audited_by": signer,
            "audited_on": today,
        }
        if path.suffix in _FRONTMATTER_FILE_SUFFIXES:
            _update_frontmatter_hash(path, digest)
            # Re-compute hash after the frontmatter rewrite — the digest
            # SHOULD be unchanged (the hash is computed with the line
            # normalised to a sentinel) but we assert this property
            # explicitly so a refactor that breaks it fails loudly.
            post_digest = compute_hash(path)
            if post_digest != digest:
                print(
                    f"audit-sign: BUG — hash changed after frontmatter "
                    f"rewrite for {rel}: {digest} -> {post_digest}",
                    file=sys.stderr,
                )
                return 3
        print(f"signed {rel}  sha256:{digest[:16]}...")
    _write_registry(entries)
    print(f"\n{len(paths_list)} file(s) signed; registry updated at {_to_rel_path(REGISTRY_PATH)}")
    return 0


def _classify(
    entries: dict[str, dict[str, str]],
) -> tuple[list[str], list[Path], list[tuple[str, str, str]]]:
    """Walk every signable root and bucket into (signed_ok, unsigned, drifted).

    Returns:
        signed_ok: list of registered rel-paths whose recorded hash matches
            the file's current hash.
        unsigned: list of signable files NOT in the registry.
        drifted: list of (rel_path, registered_hash, current_hash) for
            registered files whose current hash differs.
    """
    signed_ok: list[str] = []
    unsigned: list[Path] = []
    drifted: list[tuple[str, str, str]] = []

    discovered = _discover_all_signable()
    discovered_rels = {_to_rel_path(p): p for p in discovered}

    # Files registered but missing on disk also count as drift.
    for rel, entry in entries.items():
        registered = entry.get("hash", "")
        path = REPO_ROOT / rel
        if not path.exists():
            drifted.append((rel, registered, "<file missing>"))
            continue
        try:
            current = f"sha256:{compute_hash(path)}"
        except (OSError, UnicodeDecodeError) as exc:
            drifted.append((rel, registered, f"<unreadable: {exc}>"))
            continue
        if current == registered:
            signed_ok.append(rel)
        else:
            drifted.append((rel, registered, current))

    for rel, path in discovered_rels.items():
        if rel not in entries:
            unsigned.append(path)
    return signed_ok, unsigned, drifted


def verify(strict_unsigned: bool = True) -> int:
    """Re-hash every registered file; exit 0 iff every hash matches.

    If ``strict_unsigned`` is True, signable files NOT in the registry
    also fail verification — otherwise the lock is trivially bypassable
    by simply never signing a new file. Default True; pre-signing-pass
    callers may pass False to enable a one-time bootstrap.
    """
    entries = _load_registry()
    signed_ok, unsigned, drifted = _classify(entries)
    if drifted:
        print(
            f"audit-verify: {len(drifted)} file(s) drifted from their "
            f"registered hash:\n",
            file=sys.stderr,
        )
        for rel, registered, current in drifted:
            print(f"  {rel}", file=sys.stderr)
            print(f"    registered: {registered}", file=sys.stderr)
            print(f"    current:    {current}", file=sys.stderr)
            print(
                f"    to re-sign after intentional update: "
                f"python -m law.audit sign {rel}",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
    if strict_unsigned and unsigned:
        print(
            f"audit-verify: {len(unsigned)} signable file(s) under law/ "
            f"or tax_pipeline/law_spec/ are not registered:\n",
            file=sys.stderr,
        )
        for path in unsigned:
            print(f"  {_to_rel_path(path)}", file=sys.stderr)
        print(
            "  to sign these files: python -m law.audit sign --all",
            file=sys.stderr,
        )
    if drifted or (strict_unsigned and unsigned):
        return 1
    print(
        f"audit-verify: OK — {len(signed_ok)} signed file(s) match their "
        f"registered hashes; 0 drifted, 0 unsigned."
    )
    return 0


def status() -> int:
    """Human-friendly summary: how many signed / unsigned / drifted."""
    entries = _load_registry()
    signed_ok, unsigned, drifted = _classify(entries)
    total = len(signed_ok) + len(unsigned) + len(drifted)
    print(
        f"audit-status: {total} signable file(s) under law/ "
        f"+ tax_pipeline/law_spec/"
    )
    print(f"  signed (clean): {len(signed_ok)}")
    print(f"  unsigned:       {len(unsigned)}")
    print(f"  drifted:        {len(drifted)}")
    if unsigned:
        print("\nunsigned files:")
        for path in unsigned:
            print(f"  {_to_rel_path(path)}")
    if drifted:
        print("\ndrifted files:")
        for rel, registered, current in drifted:
            print(f"  {rel}")
            print(f"    registered: {registered}")
            print(f"    current:    {current}")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m law.audit",
        description=(
            "Sign / verify the law-shadow tree. See LOCK.md § 2 Layer 1 "
            "and proposal A4 in "
            ".review/2026-05-08-platform-flexibility-review.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Convenience wrappers (preferred for human contributors):\n"
            "  make resign FILE=<path>   # re-sign one file\n"
            "  make resign-all           # re-sign every signed law-shadow file\n"
            "  make audit-status         # signed / unsigned / drifted summary\n"
            "\n"
            "Full editor-side workflow (per-section update vs. Rev. Proc.\n"
            "inflation batch, what to do when CI reports drift):\n"
            "  CONTRIBUTING.md § \"Updating a Vetted Statutory Constant (A4 Lock)\"\n"
            "\n"
            "Suggested pre-commit hook (NOT installed automatically):\n"
            "  #!/usr/bin/env bash\n"
            "  python -m law.audit verify || {\n"
            '      echo "audit-verify failed; re-sign with python -m law.audit sign <path>"\n'
            "      exit 1\n"
            "  }\n"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sp_sign = sub.add_parser(
        "sign",
        help="Hash one or more files and record them in .audit/hashes.toml.",
    )
    sp_sign.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files to sign (e.g. law/germany/year_2025/estg/p32.py).",
    )
    sp_sign.add_argument(
        "--all",
        dest="all_files",
        action="store_true",
        help=(
            "Sign every signable file under law/ and "
            "tax_pipeline/law_spec/ (excludes __init__.py and "
            "law/_utils/ helpers per LOCK.md § 1; slice W2.C / T3.3 "
            "added the law_spec markdown to A4 scope)."
        ),
    )

    sp_verify = sub.add_parser(
        "verify",
        help=(
            "Re-hash every registered file and exit non-zero on drift. "
            "Used by `make check-invariants`."
        ),
    )
    sp_verify.add_argument(
        "--allow-unsigned",
        action="store_true",
        help=(
            "Tolerate signable files that have no registry entry (default "
            "is to flag them as drift, since silent additions defeat the "
            "lock)."
        ),
    )

    sub.add_parser(
        "status",
        help="Print signed / unsigned / drifted counts (human-readable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "sign":
        if args.all_files:
            paths = _discover_all_signable()
            if not paths:
                print(
                    "audit-sign --all: no signable files found under "
                    "law/ or tax_pipeline/law_spec/.",
                    file=sys.stderr,
                )
                return 2
        else:
            paths = list(args.paths)
        return sign(paths)
    if args.cmd == "verify":
        return verify(strict_unsigned=not args.allow_unsigned)
    if args.cmd == "status":
        return status()
    parser.error(f"unknown command: {args.cmd}")
    return 2  # unreachable, but mypy-friendly


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
