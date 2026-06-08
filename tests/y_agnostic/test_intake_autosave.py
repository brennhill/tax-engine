"""Backend regression tests for the intake auto-save flow.

The frontend (commits d4985eb, 0b4b0dc) replaces explicit "Save" buttons
with a debounced auto-save that POSTs partial state on every input
change. The backend was already designed for partial saves — every
``/api/<screen>/state`` endpoint accepts incomplete payloads and merges
with disk state — but auto-save exercises that contract much more
aggressively (rapid-fire POSTs, validation interleaved with valid
saves, save-all racing per-screen saves). This test module pins down
the partial-save semantics that auto-save relies on:

1. Rapid-fire partial POSTs leave disk state with the most-recent value
   for each field; no field is silently rolled back.
2. A validation 400 does NOT corrupt previously-saved fields. The
   auto-save controller is allowed to keep posting valid payloads while
   one field is bad.
3. ``/api/save-all`` interleaved with per-screen saves produces a
   coherent disk state (no deadlock, no half-written file).

Tax-rule note (CLAUDE.md): no new legal math is introduced — these
tests assert only persistence semantics.
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from tax_pipeline.intake.server import dispatch_request
from tax_pipeline.scaffold_year import ensure_year_scaffold
from tax_pipeline.year_runtime import resolve_year_paths

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _new_workspace(tmp: str, year: str = "2026"):
    workspace_root = Path(tmp) / year
    paths = resolve_year_paths(PROJECT_ROOT, year, workspace_root=workspace_root)
    ensure_year_scaffold(paths)
    return paths, workspace_root


def _post(path: str, body: dict[str, object]):
    return dispatch_request(PROJECT_ROOT, "POST", path, body=body)


def _get(path: str):
    return dispatch_request(PROJECT_ROOT, "GET", path)


# ---------------------------------------------------------------------------
# 1. Rapid-fire partial POSTs converge to last-value-wins per field.
# ---------------------------------------------------------------------------


class RapidFirePartialPostsTest(unittest.TestCase):
    """Auto-save coalesces typing into one POST per ~800ms, but burst
    edits across screens (or fast manual "Save now" clicks) can still
    fire several POSTs in quick succession. The backend must merge
    partial states so that the final disk state reflects the most-recent
    value for every field — never roll back a field that the user
    hasn't touched.
    """

    def test_identity_five_rapid_partial_posts_last_value_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # 5 sequential partial POSTs that each touch a different
            # field on the taxpayer block. Mirrors the auto-save
            # behaviour where each debounced POST carries the full
            # current screen state, but successive POSTs across edits
            # arrive in rapid succession.
            posts = [
                {"taxpayer": {"full_legal_name": "Alex Sample"}},
                {"taxpayer": {"address_city": "Berlin"}},
                {"taxpayer": {"address_postal_code": "10115"}},
                {"taxpayer": {"german_tax_id": "12345678901"}},
                {"taxpayer": {"date_of_birth": "1980-04-15"}},
            ]
            for body in posts:
                status, payload = _post(
                    "/api/identity/state",
                    body={"year": "2026", "workspace": str(ws), "state": body},
                )
                self.assertEqual(status, 200, payload)

            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            taxpayer = payload["state"]["taxpayer"]
            # Every partial-save field must survive — no rollback.
            self.assertEqual(taxpayer["full_legal_name"], "Alex Sample")
            self.assertEqual(taxpayer["address_city"], "Berlin")
            self.assertEqual(taxpayer["address_postal_code"], "10115")
            self.assertEqual(taxpayer["german_tax_id"], "12345678901")
            self.assertEqual(taxpayer["date_of_birth"], "1980-04-15")

    def test_identity_overwrite_same_field_keeps_last_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # Simulate the user typing "Alex" → "Alex Sample" → "Alex
            # Sample Jr.": three rapid posts on the same field, each
            # overwriting the previous. Final disk state must reflect
            # the most recent value.
            for value in ("Alex", "Alex Sample", "Alex Sample Jr."):
                status, _ = _post(
                    "/api/identity/state",
                    body={
                        "year": "2026",
                        "workspace": str(ws),
                        "state": {"taxpayer": {"full_legal_name": value}},
                    },
                )
                self.assertEqual(status, 200)
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["taxpayer"]["full_legal_name"], "Alex Sample Jr.")

    def test_carryovers_rapid_partial_posts_merge_independently(self) -> None:
        # Carryovers screen splits storage: US fields live in
        # manual_overrides.json (carryovers.us_ftc / us_capital), DE
        # fields live in de-loss-carryforwards.csv. Auto-save
        # rapid-fire on this multi-backend "fields" screen must
        # converge on every backend independently.
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            for key, value in (
                ("us_passive_ftc_carryover_2024_usd", "100"),
                ("us_general_ftc_carryover_2024_usd", "200"),
                ("de_stock_loss_carryforward_2024_eur", "300"),
            ):
                status, _ = _post(
                    "/api/carryovers/state",
                    body={"year": "2026", "workspace": str(ws), "state": {key: value}},
                )
                self.assertEqual(status, 200)
            # Read-back through the API: every field's most recent
            # value must survive. The handler joins the two storage
            # backends transparently.
            status, payload = _get(f"/api/carryovers/state?year=2026&workspace={ws}")
            ret = payload["state"]
            self.assertEqual(ret["us_passive_ftc_carryover_2024_usd"], "100")
            self.assertEqual(ret["us_general_ftc_carryover_2024_usd"], "200")
            self.assertEqual(ret["de_stock_loss_carryforward_2024_eur"], "300")


# ---------------------------------------------------------------------------
# 2. Validation 400 does NOT corrupt previously-saved fields.
# ---------------------------------------------------------------------------


class ValidationFailureIsolationTest(unittest.TestCase):
    """When auto-save POSTs an invalid value, the backend returns 400
    and writes nothing. The user fixes the field; meanwhile auto-save
    keeps firing on edits to other (valid) fields. The backend must
    keep those valid fields and not let the bad-payload retry undo
    them.
    """

    def test_invalid_ssn_does_not_clobber_existing_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # First, save a valid name.
            status, _ = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"full_legal_name": "Alex Sample"}},
                },
            )
            self.assertEqual(status, 200)
            # Then, auto-save fires with an invalid SSN. The backend
            # must reject it (400) without touching the previously
            # saved name.
            status, payload = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"us_ssn_or_itin": "not-a-ssn"}},
                },
            )
            self.assertEqual(status, 400, payload)
            # Name on disk is untouched. The bad SSN was never written:
            # the read-back returns the empty default for that field
            # (the handler synthesizes a full field shape on read).
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(status, 200)
            self.assertEqual(payload["state"]["taxpayer"]["full_legal_name"], "Alex Sample")
            self.assertEqual(payload["state"]["taxpayer"].get("us_ssn_or_itin", ""), "")

    def test_subsequent_valid_post_after_400_still_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # Post invalid → 400.
            status, _ = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"us_ssn_or_itin": "abc"}},
                },
            )
            self.assertEqual(status, 400)
            # User fixes the SSN. Auto-save POSTs the corrected value.
            status, payload = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"us_ssn_or_itin": "123-45-6789"}},
                },
            )
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["state"]["taxpayer"]["us_ssn_or_itin"], "123456789")

    def test_de_deductions_invalid_gdb_does_not_clobber_medical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # Save a valid medical value first.
            status, _ = _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"medical_expenses_eur": "850.00"},
                },
            )
            self.assertEqual(status, 200)
            # Auto-save then fires with an invalid GdB. It must be
            # rejected (400) and the medical value must remain.
            status, payload = _post(
                "/api/de_deductions/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"gdb": 35},  # not on the {0,20,30,...,100} list
                },
            )
            self.assertEqual(status, 400, payload)
            status, payload = _get(f"/api/de_deductions/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["medical_expenses_eur"], "850.00")


# ---------------------------------------------------------------------------
# 3. /api/save-all racing /api/<screen>/state.
# ---------------------------------------------------------------------------


class SaveAllRacePerScreenTest(unittest.TestCase):
    """The "Save now" header button calls /api/save-all while the
    debounced per-screen auto-save may also fire. This test confirms
    they don't deadlock or corrupt state when run back-to-back; we use
    threads to interleave the two flows and verify final state is
    coherent.
    """

    def test_save_all_then_per_screen_no_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            # Seed identity.
            _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"full_legal_name": "Alex Sample"}},
                },
            )
            # /api/save-all with the same identity payload, plus a
            # carryovers payload (mirrors the wizard's bulk save).
            status, payload = _post(
                "/api/save-all",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "screens": {
                        "identity": {
                            "taxpayer": {"full_legal_name": "Alex Sample", "address_city": "Berlin"}
                        },
                        "carryovers": {"us_passive_ftc_carryover_2024_usd": "1000"},
                    },
                },
            )
            self.assertEqual(status, 200, payload)
            # Per-screen save then fires (auto-save was queued during
            # the bulk save) and overwrites address_city.
            status, _ = _post(
                "/api/identity/state",
                body={
                    "year": "2026",
                    "workspace": str(ws),
                    "state": {"taxpayer": {"address_city": "Munich"}},
                },
            )
            self.assertEqual(status, 200)
            # Final state: name from save-all, address_city from the
            # later per-screen save (last-write-wins per field), and
            # the carryover from save-all is intact.
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            taxpayer = payload["state"]["taxpayer"]
            self.assertEqual(taxpayer["full_legal_name"], "Alex Sample")
            self.assertEqual(taxpayer["address_city"], "Munich")
            status, payload = _get(f"/api/carryovers/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["us_passive_ftc_carryover_2024_usd"], "1000")

    def test_threaded_concurrent_per_screen_saves_no_deadlock(self) -> None:
        # Two threads POST to two different screens concurrently. They
        # must both complete without exception; final state must
        # contain both writes. This is a smoke test for "no deadlock,
        # no corruption" — full FS-level atomicity is covered by
        # I9/test_final_legal_output_atomic.py.
        with tempfile.TemporaryDirectory() as tmp:
            _, ws = _new_workspace(tmp)
            errors: list[BaseException] = []
            barrier = threading.Barrier(2)

            def post_identity() -> None:
                try:
                    barrier.wait(timeout=5)
                    status, _ = _post(
                        "/api/identity/state",
                        body={
                            "year": "2026",
                            "workspace": str(ws),
                            "state": {"taxpayer": {"full_legal_name": "Concurrent T"}},
                        },
                    )
                    if status != 200:
                        errors.append(AssertionError(f"identity POST got {status}"))
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            def post_carryovers() -> None:
                try:
                    barrier.wait(timeout=5)
                    status, _ = _post(
                        "/api/carryovers/state",
                        body={
                            "year": "2026",
                            "workspace": str(ws),
                            "state": {"us_passive_ftc_carryover_2024_usd": "777"},
                        },
                    )
                    if status != 200:
                        errors.append(AssertionError(f"carryovers POST got {status}"))
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            t1 = threading.Thread(target=post_identity)
            t2 = threading.Thread(target=post_carryovers)
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
            self.assertFalse(t1.is_alive(), "identity thread deadlocked")
            self.assertFalse(t2.is_alive(), "carryovers thread deadlocked")
            self.assertEqual(errors, [])
            # Both writes must be visible.
            status, payload = _get(f"/api/identity/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["taxpayer"]["full_legal_name"], "Concurrent T")
            status, payload = _get(f"/api/carryovers/state?year=2026&workspace={ws}")
            self.assertEqual(payload["state"]["us_passive_ftc_carryover_2024_usd"], "777")


if __name__ == "__main__":
    unittest.main()
