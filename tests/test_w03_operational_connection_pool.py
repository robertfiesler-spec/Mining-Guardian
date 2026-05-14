"""
tests/test_w03_operational_connection_pool.py

W03 cohort guard (2026-05-14) — operational Postgres connection pooling.

Why this guard exists
---------------------
Before W03, `core/database_pg.py::GuardianPGDB._connect()` opened a fresh
`psycopg2.connect()` (full TCP connect + auth handshake) on every call and
closed it immediately afterward. The hourly scanner
(`core/mining_guardian.py`) makes ~500 calls/scan through this adapter, so
every scan paid ~500 connect/close round-trips. The catalog API
(`intelligence-catalog/catalog-api/catalog_api.py`) had already proven the
fix — a `psycopg2.pool.ThreadedConnectionPool` — on its side; W03 brings the
operational adapter in line.

W03 made each `GuardianPGDB` instance own a `ThreadedConnectionPool`, built
in `__init__` and torn down by `close()`. `_connect()` now borrows via
`getconn()` and returns via `putconn()`. Transaction semantics are unchanged
(commit on clean exit, rollback on exception); the one pooling-specific
nuance is that the exception path returns the connection with
`putconn(..., close=True)` so a connection carrying an aborted transaction
is discarded rather than recycled to the next borrower.

This test asserts:

  S1. After construction, the instance owns a `psycopg2.pool` pool object
      (`_pool`) — i.e. the adapter is actually pooled, not silently back on
      per-call connects.

  S2. Pool sizing comes from `_resolve_pool_sizing()`, which honours
      `MG_PG_POOL_MIN` / `MG_PG_POOL_MAX` and falls back to the documented
      defaults (2 / 20) on any malformed value (non-int, non-positive,
      min > max) rather than crashing the adapter at construction.

  S3. `_connect()` is balanced: a connection borrowed at the start of a
      `with self._connect()` block is returned to the pool at the end.
      The pool's internal free-list count is identical before and after a
      clean `with` block — no leak.

  S4. `_connect()` is balanced on the ERROR path too: when an exception is
      raised inside the `with` block, the connection is still returned to
      the pool (discarded, not leaked). The pool does not bleed connections
      on errors — a slow leak that would only surface as `PoolError: pool
      exhausted` after enough failed operations in a long-lived process.

  S5. `close()` tears the pool down and is idempotent — a second call after
      the pool is already closed does not raise.

  S6. A representative real method (`load_known_firmware`, a simple pooled
      read) round-trips through the pool and returns a sane result — i.e.
      the pool change did not break the actual method call path, only the
      connection plumbing underneath it.

Live-Mini only — skips gracefully if Postgres is unreachable or psycopg2
is missing (CI runners, fresh-clone workstations, mid-rollback states).
This is intentional and mirrors `test_w14_password_quote_consistency.py`
and `test_w26_catalog_timestamp_columns.py`: the test exercises the real
pool against the real operational database, so it is a deployment-time
guard, not a pure unit test.

By design this test does NOT:
  - Read, print, or log any password bytes
  - Write to any table (S6 is a read-only `load_known_firmware` call)
  - Touch the catalog database (operational adapter only)
  - Assume a specific row count from the live DB (S6 asserts type/shape,
    not contents)

References
----------
- docs/EXECUTION_PLAN_STATUS.md W03
- core/database_pg.py (the pool lives here; see the module docstring's
  "Connection pooling (W03, 2026-05-14)" section)
- intelligence-catalog/catalog-api/catalog_api.py (the proven pool pattern
  W03 mirrors)
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add repo root to sys.path so we can import core.database_pg.
# (Same pattern as test_w14_password_quote_consistency.py and
# test_w26_catalog_timestamp_columns.py.)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _try_psycopg2():
    """Import psycopg2 (with .pool) or return None if unavailable."""
    try:
        import psycopg2  # type: ignore  # noqa: F401
        import psycopg2.pool  # type: ignore  # noqa: F401
        return psycopg2
    except ImportError:
        return None


def _try_guardian_pgdb():
    """Import GuardianPGDB + the pool-sizing helper, or return None."""
    try:
        from core.database_pg import GuardianPGDB, _resolve_pool_sizing
        return GuardianPGDB, _resolve_pool_sizing
    except ImportError:
        return None


def _try_resolver():
    """Import the operational target resolver or return None."""
    try:
        from core.db_targets import operational_target
        return operational_target
    except ImportError:
        return None


def _can_reach_postgres() -> bool:
    """Quick reachability probe against the operational target with a short
    timeout. If this fails the test would skip anyway — bail early rather
    than emit a separate skip per sub-test."""
    psycopg2 = _try_psycopg2()
    resolver = _try_resolver()
    if psycopg2 is None or resolver is None:
        return False
    try:
        conn = psycopg2.connect(**resolver().connect_kwargs(), connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


def _free_count(pool) -> int:
    """Best-effort count of connections currently available (not checked out)
    in a psycopg2 ThreadedConnectionPool.

    psycopg2's pool keeps available connections in the private `_pool` list
    and checked-out ones in the private `_used` dict. There is no public
    accessor, so this guard reads the private attribute — acceptable for a
    test that is specifically verifying pool internals behave. Falls back to
    a sentinel if psycopg2's internals ever change shape, so the assertion
    using it can detect that rather than crash opaquely.
    """
    inner = getattr(pool, "_pool", None)
    if inner is None:
        return -1
    return len(inner)


class TestW03OperationalConnectionPool(unittest.TestCase):
    """W03 cohort guard. Live-Mini only; skips if Postgres unreachable.

    Verifies the operational adapter is genuinely pooled and that the
    pool's borrow/return accounting is balanced on both the clean and the
    error path — a leak here would surface only as eventual pool
    exhaustion in a long-lived process, exactly the kind of bug that is
    invisible until it bites at scale.
    """

    @classmethod
    def setUpClass(cls):
        # Bail early if the environment can't run this test at all.
        if not _can_reach_postgres():
            raise unittest.SkipTest(
                "Live Postgres unreachable (psycopg2 missing, container "
                "down, or operational auth fails). W03 connection-pool "
                "guard exercises the real pool against the real "
                "operational DB — skipping in unit-test contexts."
            )

        psycopg2 = _try_psycopg2()
        assert psycopg2 is not None  # _can_reach_postgres already verified
        cls.psycopg2 = psycopg2

        imports = _try_guardian_pgdb()
        assert imports is not None
        guardian_pgdb, resolve_pool_sizing = imports
        cls.GuardianPGDB = guardian_pgdb
        cls.resolve_pool_sizing = staticmethod(resolve_pool_sizing)

    def setUp(self):
        """Each test gets its own GuardianPGDB instance (its own pool).

        Constructed in setUp rather than setUpClass so a test that closes
        the pool (S5) cannot poison sibling tests. Tests that need the
        instance closed do so explicitly; tearDown closes it otherwise.
        """
        self.db = self.GuardianPGDB()

    def tearDown(self):
        # close() is idempotent (W03), so calling it here is safe even for
        # the test that already closed the pool itself.
        try:
            self.db.close()
        except Exception:
            pass

    # ── S1 ────────────────────────────────────────────────────────────
    def test_S1_instance_owns_a_threaded_connection_pool(self):
        """After construction the instance must own a psycopg2 pool object.

        If `_pool` is missing or is not a psycopg2 pool, the adapter has
        silently regressed to per-call connects and the whole point of W03
        is gone.
        """
        pool = getattr(self.db, "_pool", None)
        self.assertIsNotNone(
            pool,
            "GuardianPGDB instance has no _pool attribute — the W03 "
            "connection pool was not created in __init__.",
        )
        self.assertIsInstance(
            pool,
            self.psycopg2.pool.ThreadedConnectionPool,
            f"GuardianPGDB._pool is {type(pool)!r}, expected a "
            "psycopg2.pool.ThreadedConnectionPool.",
        )

    # ── S2 ────────────────────────────────────────────────────────────
    def test_S2_pool_sizing_resolver_defaults_and_fallback(self):
        """_resolve_pool_sizing() honours the env vars and falls back to the
        documented 2/20 defaults on any malformed value, never crashing.

        Uses os.environ directly (save/restore) rather than monkeypatch so
        this stays a plain unittest.TestCase consistent with the sibling
        live-PG guards.
        """
        resolve = self.resolve_pool_sizing
        saved = {
            k: os.environ.get(k)
            for k in ("MG_PG_POOL_MIN", "MG_PG_POOL_MAX")
        }
        try:
            # No env set -> documented defaults.
            for k in ("MG_PG_POOL_MIN", "MG_PG_POOL_MAX"):
                os.environ.pop(k, None)
            self.assertEqual(
                resolve(), (2, 20),
                "_resolve_pool_sizing() with no env vars must return the "
                "documented defaults (2, 20).",
            )

            # Valid override -> honoured.
            os.environ["MG_PG_POOL_MIN"] = "3"
            os.environ["MG_PG_POOL_MAX"] = "12"
            self.assertEqual(
                resolve(), (3, 12),
                "_resolve_pool_sizing() must honour valid "
                "MG_PG_POOL_MIN / MG_PG_POOL_MAX overrides.",
            )

            # Malformed values -> fall back to defaults, do NOT raise.
            for bad_min, bad_max in (
                ("not-an-int", "20"),   # non-integer
                ("0", "20"),            # non-positive min
                ("5", "0"),             # non-positive max
                ("30", "10"),           # min > max
            ):
                os.environ["MG_PG_POOL_MIN"] = bad_min
                os.environ["MG_PG_POOL_MAX"] = bad_max
                try:
                    result = resolve()
                except Exception as exc:  # noqa: BLE001
                    self.fail(
                        f"_resolve_pool_sizing() raised {exc!r} on bad input "
                        f"({bad_min!r}, {bad_max!r}) — it must fall back to "
                        "the defaults, never crash the adapter."
                    )
                self.assertEqual(
                    result, (2, 20),
                    f"_resolve_pool_sizing() with bad input "
                    f"({bad_min!r}, {bad_max!r}) must fall back to (2, 20), "
                    f"got {result!r}.",
                )
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # ── S3 ────────────────────────────────────────────────────────────
    def test_S3_connect_returns_connection_on_clean_exit(self):
        """A clean `with self._connect()` block must leave the pool's
        free-connection count unchanged — borrow then return, no leak.
        """
        pool = self.db._pool
        before = _free_count(pool)
        self.assertGreaterEqual(
            before, 0,
            "Could not read the pool's free-connection list — psycopg2's "
            "internal pool shape may have changed; update _free_count().",
        )
        with self.db._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        after = _free_count(pool)
        self.assertEqual(
            before, after,
            f"_connect() leaked a connection on the clean path: pool free "
            f"count was {before} before the `with` block and {after} after. "
            "A connection borrowed via getconn() was not returned via "
            "putconn().",
        )

    # ── S4 ────────────────────────────────────────────────────────────
    def test_S4_connect_returns_connection_on_error_path(self):
        """When an exception is raised inside the `with self._connect()`
        block, the connection must still be returned to the pool (the W03
        error path discards it via putconn(close=True), which keeps the
        pool's accounting balanced — the discarded slot is freed).

        A leak here would be invisible until a long-lived process had
        thrown enough errors to exhaust the pool ("PoolError: connection
        pool exhausted") — exactly the kind of slow failure W03's cohort
        guard exists to catch up front.
        """
        pool = self.db._pool
        before = _free_count(pool)

        class _IntentionalError(RuntimeError):
            pass

        with self.assertRaises(_IntentionalError):
            with self.db._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
                raise _IntentionalError("intentional — exercising error path")

        after = _free_count(pool)
        self.assertEqual(
            before, after,
            f"_connect() leaked a connection on the ERROR path: pool free "
            f"count was {before} before the failing `with` block and "
            f"{after} after. The exception path must still return the "
            "connection to the pool (discarded via putconn(close=True)).",
        )

    # ── S5 ────────────────────────────────────────────────────────────
    def test_S5_close_tears_down_pool_and_is_idempotent(self):
        """close() must close the pool, and a second close() must not raise.

        Uses a dedicated instance so closing it cannot affect other tests
        (setUp's self.db is left alone).
        """
        db = self.GuardianPGDB()
        pool = db._pool

        # First close — should close the underlying pool.
        db.close()
        self.assertTrue(
            getattr(pool, "closed", False),
            "After GuardianPGDB.close(), the underlying "
            "ThreadedConnectionPool should report .closed == True.",
        )

        # Second close — must be a no-op, not an exception (W03 documents
        # close() as idempotent).
        try:
            db.close()
        except Exception as exc:  # noqa: BLE001
            self.fail(
                f"A second GuardianPGDB.close() raised {exc!r} — close() is "
                "documented idempotent and must swallow a double-close."
            )

    # ── S6 ────────────────────────────────────────────────────────────
    def test_S6_representative_method_round_trips_through_pool(self):
        """A real pooled read method must still work end-to-end.

        `load_known_firmware()` is a simple read: it borrows a connection
        from the pool, runs one SELECT DISTINCT, returns a set. This
        asserts the pool change did not break the actual method call path
        — only the connection plumbing underneath changed. Asserts on the
        RESULT TYPE (a set), not its contents, since the live DB's row
        count is not fixed.
        """
        result = self.db.load_known_firmware()
        self.assertIsInstance(
            result, set,
            f"load_known_firmware() returned {type(result)!r}, expected a "
            "set — the pooled connection path may be broken.",
        )
        # Every element, if any, should be a (manufacturer, version) pair.
        for item in result:
            self.assertIsInstance(
                item, tuple,
                f"load_known_firmware() set contains a non-tuple {item!r}.",
            )
            self.assertEqual(
                len(item), 2,
                f"load_known_firmware() set contains a non-pair {item!r}.",
            )


if __name__ == "__main__":
    unittest.main()
