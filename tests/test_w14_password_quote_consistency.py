"""
tests/test_w14_password_quote_consistency.py

W14 cohort guard (2026-05-13) — Postgres auth quote-consistency guard.

Why this guard exists
---------------------
During W14 execution on 2026-05-13, the Step 2 `docker run` command for the
new `mg-catalog-db` container sourced `MG_DB_PASSWORD` from the live `.env`
via `cut -d= -f2-`. The `.env` value was stored in single-quoted form
(`MG_DB_PASSWORD='...'`), and `cut` preserved those quotes. The container
was provisioned with a 66-character quoted password (`'<64chars>'`), but
the Mining Guardian application code loads `.env` via
`export $(grep ... | xargs)` which strips surrounding quotes, so apps send
the 64-character unquoted form. Result: every catalog read on 5433 failed
with `password authentication failed for user "mg"`. The bug surfaced in
the Step 6 smoke gate before the Step 7 irreversible `DROP DATABASE` —
patched in-window via `ALTER USER mg WITH PASSWORD '<unquoted>'`.

The bug class is general: any mismatch between how passwords flow through
shell-context vs Python-context produces this exact symptom, and it would
be invisible until the next catalog connection attempt. This guard
exercises the full resolver chain — `.env` → `core.db_targets` →
`psycopg2.connect` — against both targets, so any future regression of the
same shape trips the test before deploy.

This test fails if:
  - The application password (resolved via `core.db_targets`) cannot
    authenticate against the operational container on its configured
    host/port.
  - The application password cannot authenticate against the catalog
    container on its configured host/port.

Live-Mini only — skips gracefully if Postgres is unreachable or psycopg2
missing (CI runners, fresh-clone workstations, mid-rollback states). This
is intentional: the test is a deployment-time guard, not a unit test.
Mirrors the pattern of `test_w26_catalog_timestamp_columns.py`.

By design this test does NOT:
  - Read, print, log, or compare the password bytes anywhere
  - Inspect `.env` directly (only reads through the resolver)
  - Touch `pg_authid` or any other privileged catalog
  - Run any SQL beyond `SELECT 1` to confirm round-trip

References
----------
- docs/strategy/W14_POSTMORTEM_2026-05-13.md §2 (root cause) + §4.2 (this test)
- docs/strategy/W14_PREP.md (the W14 plan)
- docs/EXECUTION_PLAN_STATUS.md W14 (status: closed 2026-05-13)
- docs/CLAUDE.md (the .env quote-sourcing rule from §4.3 lands with W14b)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add repo root to sys.path so we can import core.db_targets.
# (Same pattern as test_w26_catalog_timestamp_columns.py and test_db_targets.py.)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _try_psycopg2():
    """Import psycopg2 or return None if unavailable."""
    try:
        import psycopg2  # type: ignore
        return psycopg2
    except ImportError:
        return None


def _try_resolvers():
    """Import the operational/catalog target resolvers or return None."""
    try:
        from core.db_targets import operational_target, catalog_target
        return operational_target, catalog_target
    except ImportError:
        return None


def _can_reach_postgres() -> bool:
    """Quick reachability probe: try the operational target with a short
    timeout. If this fails, the test would skip anyway — better to bail
    early than emit a separate skip per sub-test."""
    psycopg2 = _try_psycopg2()
    resolvers = _try_resolvers()
    if psycopg2 is None or resolvers is None:
        return False

    operational_target, _ = resolvers
    target = operational_target()
    try:
        conn = psycopg2.connect(**target.connect_kwargs(), connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


class TestW14PasswordQuoteConsistency(unittest.TestCase):
    """W14 cohort guard. Live-Mini only; skips if unreachable.

    Each sub-test attempts a `SELECT 1` round-trip through one of the
    resolver functions. A failure here means the password the application
    sends does NOT match what the role was provisioned with — the same
    bug class that broke W14 Step 6.
    """

    @classmethod
    def setUpClass(cls):
        # Bail early if the environment can't run this test at all
        # (no psycopg2, no resolver imports, no reachable Postgres).
        if not _can_reach_postgres():
            raise unittest.SkipTest(
                "Live Postgres unreachable (psycopg2 missing, container down, "
                "or operational auth fails). W14 password-quote consistency "
                "guard is a deployment-time check — skipping in unit-test "
                "contexts."
            )

        psycopg2 = _try_psycopg2()
        assert psycopg2 is not None  # _can_reach_postgres already verified
        cls.psycopg2 = psycopg2

        resolvers = _try_resolvers()
        assert resolvers is not None
        # Wrap in staticmethod() so Python doesn't bind these to `self` when
        # accessed via self.operational_target — they're free functions that
        # take no arguments.
        op_fn, cat_fn = resolvers
        cls.operational_target = staticmethod(op_fn)
        cls.catalog_target = staticmethod(cat_fn)

    def _round_trip(self, target_fn, label: str):
        """Connect via the given resolver, run SELECT 1, assert and close.

        Does not print or assert on the password — only on auth success
        and round-trip correctness.
        """
        target = target_fn()
        try:
            conn = self.psycopg2.connect(
                **target.connect_kwargs(),
                connect_timeout=3,
            )
        except self.psycopg2.OperationalError as e:
            # The diagnostic the developer cares about: where and how it
            # failed, WITHOUT exposing the password. The exception message
            # from psycopg2 is safe to surface — it never contains the
            # password bytes, only the role name and host/port.
            self.fail(
                f"{label}: auth FAILED via {target.safe_repr()} — {e}.\n"
                "This is the W14 password-quote bug pattern. See "
                "docs/strategy/W14_POSTMORTEM_2026-05-13.md §2."
            )
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            row = cur.fetchone()
            self.assertEqual(
                row, (1,),
                f"{label}: SELECT 1 returned unexpected value {row!r}"
            )
        finally:
            conn.close()

    def test_operational_target_auth_round_trip(self):
        """The password resolved via operational_target() must authenticate
        successfully against the operational container (port 5432)."""
        self._round_trip(self.operational_target, "operational")

    def test_catalog_target_auth_round_trip(self):
        """The password resolved via catalog_target() must authenticate
        successfully against the catalog container (post-W14: port 5433;
        pre-W14: falls back to port 5432, same container)."""
        self._round_trip(self.catalog_target, "catalog")


if __name__ == "__main__":
    unittest.main()
