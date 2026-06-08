"""URL-liveness structural invariant (proposal A1 / slice W1.C-T2.2).

Why this test exists
--------------------
Every tax-rule implementation in this codebase must cite the controlling
legal authority (per ``CLAUDE.md``) and provide an official web link in
either the law spec, rule metadata, trace output, or narrative template.
After the F1 statutory-constant migration + Y2/P5 form schemas, 115 of
the most load-bearing URLs live in TOML data and another tranche lives
in narrative Jinja templates and the ``tax_pipeline/y2025/`` rule and
law modules.

When an authority page rolls (IRS publishes a new yearly Rev. Proc.,
BMF re-issues the Programmablaufplan, ELSTER moves a form URL), our
cited URLs go stale silently — the test suite has no way to know the
citation now 404s. That is *exactly* the failure class A1 catches:

  Walk every ``https://`` URL in the cited surface; HEAD-request it;
  record ``(url, status, last_check_iso8601)`` to a tracked health
  file; fail if any URL has been 4xx for two consecutive runs.

Hard constraints (from the slice brief)
---------------------------------------

1.  *Stdlib only.* ``urllib.request`` + ``json`` + ``re``. No
    ``requests`` library — keeps the engine's stdlib-only posture.

2.  *Skip gracefully when offline.* The first uncached URL doubles as a
    network-availability canary: if it raises ``URLError`` / ``OSError``
    at the connection layer (DNS failure, refused, timeout) we
    ``pytest.skip("network unavailable")``. CI environments and dev
    machines without outbound HTTP must not break the suite.

3.  *Per-URL HTTP errors are recorded, not raised.* Once the canary is
    happy, every other URL gets its observed status code logged. The
    test only **fails** when a URL has been 4xx for two consecutive
    runs (true rot, not transient).

4.  *24-hour cache.* If ``url_health.json`` records a URL was last
    checked successfully <24 h ago, skip re-checking it. Cuts a warm
    run to seconds; a cold run is a few minutes.

5.  *Deterministic same-hour reruns.* The schema's
    ``metadata.last_full_run_iso8601`` may move, but the ``urls`` map
    must not drift between two runs in the same hour (all URLs hit
    cache → no writes to the URL entries).

This test is **not** in ``make check-invariants`` — URL liveness is a
weekly-cadence check, not a per-commit check. It lives under
``make check-urls`` (see Makefile).
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import socket
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urldefrag, urlsplit, urlunsplit

REPO_ROOT = Path(__file__).resolve().parents[2]
HEALTH_FILE = REPO_ROOT / "tests" / "data" / "url_health.json"

CACHE_TTL_HOURS = 24
HEAD_TIMEOUT_SECONDS = 10
SCHEMA_VERSION = 1
# Network-availability canary budget. We try this many URLs at the start
# of a re-check pass; if every one fails at the connection layer, we
# treat the run as offline and skip. Set high enough to tolerate a
# single chronically-flaky authority (uscode.house.gov has historically
# rejected/timed-out HEAD), but low enough that a real outage is
# detected before we wait through a couple hundred 10s timeouts.
_CANARY_BUDGET = 5

# Bot-blocking allowlist. URLs in this set are KNOWN to be alive when
# fetched from a normal interactive browser, but the upstream actively
# refuses non-browser traffic (User-Agent / IP-range / TLS fingerprint
# heuristics) so the GET-fallback can't reach them either. The test
# records their observed status code but treats them as "not rotten" so
# a real-but-bot-blocked authority does not masquerade as URL rot. Every
# entry MUST be (a) a real authority surface this engine relies on, (b)
# manually verified live in a browser on the date listed, and (c)
# accompanied by a one-line reason. Re-verify each entry whenever an
# A1 / W1.C reviewer flags this allowlist as drifting.
_BOT_BLOCKED_ALLOWLIST: frozenset[str] = frozenset({
    # SSA actively blocks non-browser User-Agents and request patterns
    # (verified 2026-05-12: 403 on HEAD, 403 on GET with browser UA from
    # this CI network). The U.S.-Germany Totalization Agreement page and
    # the OASDI wage-base COLA page are both alive in a browser. Cited
    # by tax_pipeline/y2025/us_law.py + law/usa/year_2025/usc26/p1401.
    "https://www.ssa.gov/international/Agreement_Pamphlets/germany.html",
    "https://www.ssa.gov/oact/cola/cbb.html",
})

# Stop-class characters: the URL ends at the first whitespace, quote,
# angle/round/curly/square bracket, backtick, or comma. ``#`` is kept so
# the canonicalizer can strip the fragment deterministically.
_URL_RE = re.compile(r"https://[^\s\"'<>)\]}`,]+")

# Trailing-junk punctuation that often follows a URL in prose. These are
# stripped after extraction (e.g. URL at end of a sentence: "see X.").
_TRAILING_JUNK = ".,;:)>\"'-"

# Roots to walk for URL references. Order matters only for stable
# fingerprints in the inventory.
_ROOTS: tuple[tuple[Path, str], ...] = (
    (REPO_ROOT / "law", "**/*.toml"),
    (REPO_ROOT / "tax_pipeline" / "forms" / "schemas", "*.toml"),
    (REPO_ROOT / "tax_pipeline" / "y2025", "**/*.py"),
    (REPO_ROOT / "tax_pipeline" / "narrative" / "templates", "**/*.jinja"),
)


def _canonical_url(raw: str) -> str:
    """Canonicalize a URL: strip trailing junk + fragment, lowercase host."""
    stripped = raw.rstrip(_TRAILING_JUNK)
    defragged, _frag = urldefrag(stripped)
    parts = urlsplit(defragged)
    # Lowercase the scheme + host; preserve path/query case (path-case is
    # significant on many statute sites — gesetze-im-internet.de paths
    # are case-sensitive).
    host = parts.netloc.lower()
    return urlunsplit((parts.scheme.lower(), host, parts.path, parts.query, ""))


def _collect_urls() -> list[str]:
    """Return the sorted, deduplicated canonical URL inventory."""
    found: set[str] = set()
    for root, pattern in _ROOTS:
        if not root.exists():
            continue
        for file_path in root.glob(pattern):
            if not file_path.is_file():
                continue
            text = file_path.read_text(encoding="utf-8")
            for match in _URL_RE.findall(text):
                canon = _canonical_url(match)
                # Reject obviously broken / placeholder URLs after canon.
                if not canon.startswith("https://") or "://" not in canon:
                    continue
                if "." not in urlsplit(canon).netloc:
                    continue  # e.g. https://localhost — not an authority URL
                found.add(canon)
    return sorted(found)


def _load_health() -> dict:
    if not HEALTH_FILE.exists():
        return {
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "last_full_run_iso8601": None,
                "cache_ttl_hours": CACHE_TTL_HOURS,
            },
            "urls": {},
        }
    return json.loads(HEALTH_FILE.read_text(encoding="utf-8"))


def _save_health(health: dict) -> None:
    HEALTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Sort the URL keys so the on-disk JSON is reviewer-friendly + diff-stable.
    ordered = {
        "metadata": health["metadata"],
        "urls": {k: health["urls"][k] for k in sorted(health["urls"].keys())},
    }
    HEALTH_FILE.write_text(
        json.dumps(ordered, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _iso(now: _dt.datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_cache_fresh(entry: dict, now: _dt.datetime) -> bool:
    last_iso = entry.get("last_check_iso8601")
    if not last_iso:
        return False
    try:
        last = _dt.datetime.strptime(last_iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc
        )
    except ValueError:
        return False
    if (now - last) >= _dt.timedelta(hours=CACHE_TTL_HOURS):
        return False
    last_status = entry.get("status")
    # 2xx / 3xx → confidently fresh.
    if isinstance(last_status, int) and 200 <= last_status < 400:
        return True
    # 4xx / 5xx are the test's core signal class; ALWAYS re-check so
    # we either confirm 2-consecutive (the fail signal) or see the URL
    # recover on the next run.
    if isinstance(last_status, int):
        return False
    # Unreachable (status=None) is treated as transient and IS cache-fresh
    # for the TTL window. Re-checking 30+ URLs that consistently time out
    # would blow the per-run budget (each timeout costs HEAD_TIMEOUT_SECONDS)
    # without surfacing new signal. Connection-layer outages are not the
    # rot class A1 is designed to catch; HTTP-layer 4xx is.
    return True


def _head_request(url: str) -> tuple[int | None, str | None]:
    """HEAD-request ``url``.

    Returns ``(status_code_or_None, error_class_or_None)``.

    Connection-layer errors return ``(None, "<error_class>")`` so the
    caller can distinguish "unreachable" (network gone, treat as
    transient) from "responded with 4xx/5xx" (true defect class).
    HTTP-layer errors (4xx/5xx) return their status code — those *are*
    a response.
    """
    request = urllib.request.Request(url, method="HEAD")
    request.add_header("User-Agent", "taxes-2025-url-liveness/1.0")
    try:
        with urllib.request.urlopen(request, timeout=HEAD_TIMEOUT_SECONDS) as response:
            return int(response.status), None
    except urllib.error.HTTPError as exc:
        # HTTPError IS a response (e.g. 404, 403, 405-for-HEAD). Record it.
        # Some servers reject HEAD outright (SSA, BMF formulare-bfinv) but
        # serve content fine on GET — retry once with a bytes-discarding
        # GET on the 400/403/405 class so a HEAD-policy quirk does not
        # masquerade as URL rot.
        if exc.code in (400, 403, 405):
            # Some authority sites (notably SSA.gov) reject *any* request
            # whose User-Agent is not a real browser UA. The retry uses a
            # widely-recognized browser UA so SSA + similarly-tightened
            # endpoints stop masquerading as dead URLs.
            get_request = urllib.request.Request(url, method="GET")
            get_request.add_header(
                "User-Agent",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
            )
            get_request.add_header("Accept", "text/html,*/*;q=0.5")
            try:
                with urllib.request.urlopen(get_request, timeout=HEAD_TIMEOUT_SECONDS) as response:
                    # Drain a small prefix so the connection closes cleanly;
                    # we only care about the status code.
                    response.read(1024)
                    return int(response.status), None
            except urllib.error.HTTPError as get_exc:
                return int(get_exc.code), None
            except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as get_exc:
                return None, type(get_exc).__name__
        return int(exc.code), None
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError) as exc:
        # Connection-layer failure (DNS, refused, timeout). Treat as
        # unreachable for the caller to interpret.
        return None, type(exc).__name__


class UrlLivenessInvariantTest(unittest.TestCase):
    """A1 invariant: every cited authority URL responds with a status code,
    and no URL has been 4xx for two consecutive runs.

    Skip-by-default: the brief specifies a separate ``make check-urls``
    target (different cadence from ``check-invariants`` / ``check-suite``).
    The test only runs when ``RUN_URL_CHECKS=1`` is set in the environment;
    ``make check-urls`` sets it. Other test invocations (``make check-suite``,
    plain ``python -m unittest discover``) get a skip so a developer's
    network conditions / transient 4xx / fork-mode discovery does not break
    the suite.
    """

    def setUp(self) -> None:
        import os
        if os.environ.get("RUN_URL_CHECKS") != "1":
            self.skipTest(
                "URL-liveness invariant is opt-in via RUN_URL_CHECKS=1 "
                "(run `make check-urls` to exercise it)."
            )

    def test_every_cited_url_returns_a_status_code(self) -> None:
        urls = _collect_urls()
        self.assertGreater(
            len(urls),
            50,
            "URL inventory looks suspiciously small — the walker glob may "
            "have regressed. Expected >50 unique URLs in law/ + schemas/ + "
            "y2025/ + narrative templates.",
        )

        health = _load_health()
        prior_urls: dict = dict(health.get("urls", {}))
        now = _now_utc()
        now_iso = _iso(now)

        # Carry forward any prior entry; we'll update/touch it below.
        urls_state: dict[str, dict] = {}
        for url, entry in prior_urls.items():
            urls_state[url] = dict(entry)

        # Drop entries for URLs that no longer appear in the source tree
        # (citation surface shrank). Re-add fresh empty entries for new URLs.
        urls_state = {u: urls_state[u] for u in urls_state if u in set(urls)}
        for url in urls:
            urls_state.setdefault(
                url,
                {
                    "last_check_iso8601": None,
                    "status": None,
                    "consecutive_4xx_count": 0,
                },
            )

        # Identify the URLs that need re-checking on this run.
        to_check = [u for u in urls if not _is_cache_fresh(urls_state[u], now)]
        if not to_check:
            # Every URL is cache-fresh; no network needed. Just save and pass.
            self._finalize_pass(health, urls_state, now_iso, prior_urls)
            return

        # Network-availability canaries. A single URL is not enough — a
        # specific authority (uscode.house.gov, e.g.) can chronically
        # time out even when general connectivity is fine. Try up to
        # ``_CANARY_BUDGET`` candidates; if EVERY one fails at the
        # connection layer (not HTTPError), assume offline and skip.
        # Prefer URLs that previously returned 2xx so we don't keep
        # skipping on the same flaky endpoint.
        canary_budget = min(_CANARY_BUDGET, len(to_check))
        prior_200 = [
            u
            for u in to_check
            if isinstance(prior_urls.get(u, {}).get("status"), int)
            and 200 <= prior_urls[u]["status"] < 300
        ]
        canaries: list[str] = prior_200[:canary_budget]
        for url in to_check:
            if len(canaries) >= canary_budget:
                break
            if url not in canaries:
                canaries.append(url)
        canary_results: dict[str, tuple[int | None, str | None]] = {}
        any_response_seen = False
        last_error: str | None = None
        for canary in canaries:
            status, err = _head_request(canary)
            canary_results[canary] = (status, err)
            if status is not None:
                any_response_seen = True
                break
            last_error = err
        if not any_response_seen:
            # Every canary failed at the connection layer → assume offline.
            # Don't touch url_health.json so a same-hour rerun stays stable.
            self.skipTest(
                f"network unavailable (all {len(canaries)} canary URL(s) "
                f"failed at connection layer; last error: {last_error}); "
                "URL-liveness check skipped"
            )

        # Apply the canary results that did fire.
        for url, (status, _err) in canary_results.items():
            self._apply_result(urls_state[url], status, now_iso)

        # Walk the rest. Each individual URL may fail with a connection
        # error (recorded as unreachable, status=None); the test only
        # fails when a URL is 4xx for two consecutive runs.
        for url in to_check:
            if url in canary_results:
                continue
            status, _err = _head_request(url)
            self._apply_result(urls_state[url], status, now_iso)

        # Persist and check.
        self._finalize_pass(health, urls_state, now_iso, prior_urls)
        self._assert_no_consecutive_4xx(urls_state)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _apply_result(self, entry: dict, status: int | None, now_iso: str) -> None:
        entry["last_check_iso8601"] = now_iso
        entry["status"] = status
        if status is not None and 400 <= status < 500:
            entry["consecutive_4xx_count"] = int(entry.get("consecutive_4xx_count", 0)) + 1
        else:
            entry["consecutive_4xx_count"] = 0

    def _finalize_pass(
        self,
        health: dict,
        urls_state: dict[str, dict],
        now_iso: str,
        prior_urls: dict,
    ) -> None:
        # Same-hour rerun determinism: if the URL map is byte-identical
        # to the prior on-disk state, don't even bump
        # ``last_full_run_iso8601`` — keeps `tests/data/url_health.json`
        # truly stable across rapid back-to-back invocations.
        if urls_state == prior_urls and health["metadata"].get("last_full_run_iso8601"):
            return
        health["metadata"]["schema_version"] = SCHEMA_VERSION
        health["metadata"]["cache_ttl_hours"] = CACHE_TTL_HOURS
        health["metadata"]["last_full_run_iso8601"] = now_iso
        health["urls"] = urls_state
        _save_health(health)

    def _assert_no_consecutive_4xx(self, urls_state: dict[str, dict]) -> None:
        rotten: list[str] = []
        for url, entry in sorted(urls_state.items()):
            if int(entry.get("consecutive_4xx_count", 0)) >= 2:
                # Bot-blocked authorities surface here as 4xx-consecutive
                # but are NOT rot — they're verified live in a browser
                # and just block CI traffic. Skip silently; the observed
                # status is still recorded in url_health.json so anyone
                # auditing can see the upstream behavior.
                if url in _BOT_BLOCKED_ALLOWLIST:
                    continue
                rotten.append(f"  {url}  status={entry.get('status')}")
        self.assertFalse(
            rotten,
            "URL rot: the following authority URLs have returned 4xx for "
            "two consecutive runs (the slice brief defines this as the "
            "fail signal — one-off 4xx is permitted as transient):\n"
            + "\n".join(rotten),
        )


if __name__ == "__main__":
    unittest.main()
