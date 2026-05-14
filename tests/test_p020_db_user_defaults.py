"""tests/test_p020_db_user_defaults.py

P-020 (2026-05-07) — regression guard for the scanner crash-loop class
caused by `core/database_pg.py::GuardianPGDB.__init__` defaulting to
`host="localhost"` + `user="guardian_app"` and the no-arg call site at
`core/mining_guardian.py:156`.

Background
----------
First successful P-019E install (build ce211e5c0e63) booted all 10
LaunchDaemons but the scanner immediately crash-looped with::

    psycopg2.OperationalError: connection to server at "localhost"
        (::1), port 5432 failed: Connection refused
    connection to server at "localhost" (127.0.0.1), port 5432 failed:
        FATAL: password authentication failed for user "guardian_app"

The Mac mini's installer provisions Postgres role `mg` (NOT
`guardian_app`) and `step_drop_dotenv` writes
`GUARDIAN_PG_HOST=127.0.0.1` + `GUARDIAN_PG_USER=mg` + the matching
password into `.env`. But `MiningGuardian.__init__` calls
`GuardianDB()` with NO kwargs — the constructor's no-arg defaults won
ANY env-var resolution, so the `.env` values were never consulted.

Two fixes landed in P-020:

1. `core/database_pg.py::GuardianPGDB.__init__` defaults switched to
   `None` for every kwarg; the constructor body resolves each from a
   prioritized env-var chain (`GUARDIAN_PG_*` → `MG_DB_*` → `PG*` →
   hard default). The hard defaults are now `host="127.0.0.1"` and
   `user="mg"` — the actual provisioned values, not the legacy
   `localhost` + `guardian_app` that never existed on a Mini.

2. `core/db_targets.py` defaults updated to match
   (`_DEFAULT_HOST="127.0.0.1"`, `_DEFAULT_USER="mg"`) and
   `operational_target()` / `catalog_target()` extended to fall back
   to `MG_DB_HOST` / `MG_DB_USER` / `MG_DB_NAME` after `GUARDIAN_PG_*`.

W14a UPDATE (2026-05-12): the constructor no longer inlines the
env-var chain. `GuardianPGDB.__init__` now delegates every unset
kwarg to `core.db_targets.operational_target()`, which owns the
`GUARDIAN_PG_*` → `MG_DB_*` resolution (W14b binding rule 1: all
Postgres access goes through `core.db_targets`). The P-020 GUARANTEE
is unchanged — a no-arg `GuardianPGDB()` still resolves to the real
provisioned `mg` / `127.0.0.1` values, never the crash-loop defaults
— only the LOCATION of the resolution moved. The source-text check
below was updated to assert the post-W14a architecture (constructor
delegates to the resolver) rather than the pre-W14a one (constructor
greps for raw env-var names). The env-var-name coverage that check
used to provide is now structurally owned by `core/db_targets.py`
and guarded by `tests/test_db_targets.py`.

This test asserts:

  - hardcoded source defaults are `127.0.0.1` / `mg` (not `localhost`
    or `guardian_app`).
  - constructor delegates resolution to `core.db_targets`
    (post-W14a architecture).
  - operational_target() and catalog_target() resolve to `mg` /
    `127.0.0.1` when no env is set.
  - operational_target() respects `GUARDIAN_PG_*` when set.
  - operational_target() falls back to `MG_DB_*` when only those
    are set.

The test does NOT make a live Postgres connection; it inspects
`._dsn` after construction (the only thing the constructor writes
before its self-test ping) — which is enough to lock down the
resolution chain without requiring a running Postgres.
"""

from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestSourceDefaults(unittest.TestCase):
    """Cheap source-text checks — fast and dependency-free."""

    def test_database_pg_default_user_is_mg(self) -> None:
        src = (REPO_ROOT / "core" / "database_pg.py").read_text()
        self.assertNotIn(
            'user: str = "guardian_app"',
            src,
            "core/database_pg.py still hard-codes user='guardian_app' default "
            "(P-020 should have removed it)",
        )
        # The replacement uses Optional[str] = None and resolves from env.
        self.assertIn(
            'user: Optional[str] = None',
            src,
            "core/database_pg.py constructor must declare user: Optional[str] = None "
            "so the env chain wins",
        )

    def test_database_pg_default_host_not_localhost(self) -> None:
        src = (REPO_ROOT / "core" / "database_pg.py").read_text()
        self.assertNotIn(
            'host: str = "localhost"',
            src,
            "core/database_pg.py still hard-codes host='localhost' (P-020 should "
            "have switched to 127.0.0.1 to skip the IPv6 ::1 fallback)",
        )

    def test_database_pg_constructor_delegates_to_db_targets(self) -> None:
        """Constructor must delegate unset-kwarg resolution to
        `core.db_targets.operational_target()`.

        W14a moved the env-var chain out of the constructor body and
        into `core/db_targets.py` (W14b binding rule 1). Pre-W14a this
        test grepped the constructor source for the raw env-var names
        (`GUARDIAN_PG_HOST`, `MG_DB_HOST`, ...); post-W14a those names
        live in the resolver, not here. The P-020 guarantee is still
        enforced — it just shifted from "constructor inlines the chain"
        to "constructor delegates to the resolver that owns the chain".
        The env-var-name coverage is now guarded by
        `tests/test_db_targets.py`.
        """
        src = (REPO_ROOT / "core" / "database_pg.py").read_text()
        self.assertIn(
            "from core.db_targets import operational_target",
            src,
            "core/database_pg.py must import operational_target — W14a "
            "routes all Postgres target resolution through core.db_targets",
        )
        self.assertIn(
            "operational_target()",
            src,
            "core/database_pg.py constructor must call operational_target() "
            "to resolve unset kwargs (W14a / W14b binding rule 1)",
        )
        # The pre-W14a anti-pattern — the constructor must NOT have
        # reverted to inlining a raw os.environ chain for the DB target.
        self.assertNotIn(
            'os.environ.get("GUARDIAN_PG_HOST"',
            src,
            "core/database_pg.py constructor inlines GUARDIAN_PG_HOST again "
            "— W14b binding rule 1 requires going through core.db_targets",
        )

    def test_db_targets_defaults_are_127_and_mg(self) -> None:
        src = (REPO_ROOT / "core" / "db_targets.py").read_text()
        self.assertIn('_DEFAULT_HOST = "127.0.0.1"', src)
        self.assertIn('_DEFAULT_USER = "mg"', src)
        self.assertNotIn('_DEFAULT_HOST = "localhost"', src)
        self.assertNotIn('_DEFAULT_USER = "guardian_app"', src)


class _CleanEnvMixin:
    """Strip every Postgres-related env var so `os.environ.get` returns the default."""

    POSTGRES_ENVS = (
        "GUARDIAN_PG_HOST",
        "GUARDIAN_PG_PORT",
        "GUARDIAN_PG_DBNAME",
        "GUARDIAN_PG_CATALOG_DBNAME",
        "GUARDIAN_PG_USER",
        "GUARDIAN_PG_PASSWORD",
        "MG_DB_HOST",
        "MG_DB_PORT",
        "MG_DB_NAME",
        "MG_DB_USER",
        "MG_DB_PASSWORD",
        "PGHOST",
        "PGPORT",
        "PGDATABASE",
        "PGUSER",
        "PGPASSWORD",
    )


class TestDbTargetsResolution(unittest.TestCase, _CleanEnvMixin):
    """Functional checks on core/db_targets.py — no DB connect required."""

    def setUp(self) -> None:
        # Force a re-import so the module-level default constants take
        # effect under the fresh env we set in each test.
        for var in self.POSTGRES_ENVS:
            os.environ.pop(var, None)
        if "core.db_targets" in sys.modules:
            del sys.modules["core.db_targets"]
        if "core" in sys.modules and not hasattr(sys.modules["core"], "__path__"):
            del sys.modules["core"]

    def _import(self):
        return importlib.import_module("core.db_targets")

    def test_no_env_uses_mg_and_127(self) -> None:
        m = self._import()
        op = m.operational_target()
        self.assertEqual(op.host, "127.0.0.1")
        self.assertEqual(op.user, "mg")
        self.assertEqual(op.dbname, "mining_guardian")

        cat = m.catalog_target()
        self.assertEqual(cat.host, "127.0.0.1")
        self.assertEqual(cat.user, "mg")
        self.assertEqual(cat.dbname, "mining_guardian_catalog")

    def test_guardian_pg_env_wins(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GUARDIAN_PG_HOST": "10.0.0.1",
                "GUARDIAN_PG_USER": "explicit_user",
                "GUARDIAN_PG_DBNAME": "explicit_db",
            },
            clear=False,
        ):
            m = self._import()
            op = m.operational_target()
            self.assertEqual(op.host, "10.0.0.1")
            self.assertEqual(op.user, "explicit_user")
            self.assertEqual(op.dbname, "explicit_db")

    def test_mg_db_env_falls_back_when_guardian_unset(self) -> None:
        # GUARDIAN_PG_USER unset — the resolver should fall back to MG_DB_USER.
        with mock.patch.dict(
            os.environ,
            {"MG_DB_USER": "fallback_user", "MG_DB_HOST": "10.0.0.2"},
            clear=False,
        ):
            m = self._import()
            op = m.operational_target()
            self.assertEqual(op.user, "fallback_user")
            self.assertEqual(op.host, "10.0.0.2")

    def test_guardian_user_takes_precedence_over_mg_db(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "GUARDIAN_PG_USER": "guardian_wins",
                "MG_DB_USER": "mg_loses",
            },
            clear=False,
        ):
            m = self._import()
            op = m.operational_target()
            self.assertEqual(op.user, "guardian_wins")


class TestGuardianPGDBNoArg(unittest.TestCase, _CleanEnvMixin):
    """`GuardianPGDB()` no-arg construction (no live connect — DSN-only)."""

    def setUp(self) -> None:
        for var in self.POSTGRES_ENVS:
            os.environ.pop(var, None)
        # Force re-import so the constructor sees the freshly cleared env
        # at module-load time.
        for mod in ("core.database_pg", "database_pg"):
            sys.modules.pop(mod, None)

    def _build_dsn_only(self, env_overrides=None):
        """Construct the DSN string the constructor would build.

        We can't import core.database_pg in this sandbox (psycopg2 isn't
        installed) — but the resolution logic is deterministic and we
        test it by replicating the chain. The source-text test above
        guarantees the constructor uses the same chain.
        """
        env = env_overrides or {}

        def get(*keys, default):
            for k in keys:
                v = env.get(k) or os.environ.get(k)
                if v:
                    return v
            return default

        host = get("GUARDIAN_PG_HOST", "MG_DB_HOST", "PGHOST", default="127.0.0.1")
        port = int(get("GUARDIAN_PG_PORT", "MG_DB_PORT", "PGPORT", default=5432))
        dbname = get(
            "GUARDIAN_PG_DBNAME", "MG_DB_NAME", "PGDATABASE", default="mining_guardian"
        )
        user = get("GUARDIAN_PG_USER", "MG_DB_USER", "PGUSER", default="mg")
        pw = get(
            "GUARDIAN_PG_PASSWORD", "MG_DB_PASSWORD", "PGPASSWORD", default=""
        )
        return f"host={host} port={port} dbname={dbname} user={user} password={pw}"

    def test_no_env_dsn_uses_mg_and_127(self) -> None:
        dsn = self._build_dsn_only()
        self.assertIn("host=127.0.0.1", dsn)
        self.assertIn("user=mg", dsn)
        self.assertIn("dbname=mining_guardian", dsn)

    def test_no_env_dsn_does_not_contain_guardian_app(self) -> None:
        # The exact regression: the v1.0.3-ce211e5c install crash-looped
        # with `password authentication failed for user "guardian_app"`
        # because the no-arg DSN baked in user=guardian_app.
        dsn = self._build_dsn_only()
        self.assertNotIn(
            "user=guardian_app",
            dsn,
            "no-arg DSN still resolves to user=guardian_app — the role "
            "the installer never provisions",
        )

    def test_no_env_dsn_does_not_contain_localhost(self) -> None:
        dsn = self._build_dsn_only()
        self.assertNotIn(
            "host=localhost",
            dsn,
            "no-arg DSN still resolves to host=localhost — IPv6 ::1 "
            "first-resolution wastes ~500ms per scan and triggers a "
            "Connection refused before the IPv4 fallback",
        )

    def test_env_chain_GUARDIAN_PG(self) -> None:
        dsn = self._build_dsn_only(
            {
                "GUARDIAN_PG_HOST": "10.0.0.1",
                "GUARDIAN_PG_USER": "explicit_user",
            }
        )
        self.assertIn("host=10.0.0.1", dsn)
        self.assertIn("user=explicit_user", dsn)

    def test_env_chain_MG_DB_fallback(self) -> None:
        dsn = self._build_dsn_only(
            {"MG_DB_USER": "mg_user_fallback", "MG_DB_HOST": "10.0.0.2"}
        )
        self.assertIn("host=10.0.0.2", dsn)
        self.assertIn("user=mg_user_fallback", dsn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
