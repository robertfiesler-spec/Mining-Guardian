"""
core/db_targets.py — Central operational vs catalog Postgres target helper.

P-018A: thin, dependency-free helpers that resolve Postgres connection
parameters for the two databases that live on the customer Mac mini:

  - **Operational** DB (`mining_guardian`, default) — scan/audit/AI tables.
  - **Catalog** DB (`mining_guardian_catalog`, default) — the seeded
    Mining Intelligence Catalog (`hardware.miner_models`,
    `hardware.manufacturers`, `staging.miner_model_proposals`, …).

Why this exists
---------------
Both DBs run on the same Postgres container (same host, port, user, password)
— only the `dbname` differs. The installer writes `GUARDIAN_PG_CATALOG_DBNAME`
into `.env` (`installer/macos-pkg/scripts/postinstall.sh:925`), but as of
P-018A no Python code reads that variable, so every catalog/import code path
silently defaults to the operational DB. P-018B/P-018C will redirect specific
writers/readers; this module is the missing one-place-to-resolve-it layer
those PRs will use.

This module deliberately:

  - Imports no DB driver (`psycopg2` etc.) — it returns a kwargs dict and a
    libpq DSN string, leaving the actual connect to callers. Keeps tests
    fast and avoids a hard psycopg2 dependency for the helper itself.
  - Performs no logging at import time and emits no INFO/DEBUG lines from
    the resolver functions. Connection-time logging belongs to callers.
  - Masks the password in `__repr__` / `__str__` so tracebacks, debug
    prints, and structured logs do not leak it. (Password is still
    accessible via the `password` attribute when an actual connect needs
    it.)
  - Reads `GUARDIAN_PG_*` only — does NOT honor libpq's `PGHOST` / `PGPORT`
    / `PGUSER` / `PGDATABASE` envs. The Mini's `.env` writes both families
    with the same operational values, but the catalog DB is named ONLY by
    `GUARDIAN_PG_CATALOG_DBNAME`; mixing in `PGDATABASE` would re-introduce
    the operational default for catalog callers and recreate the bug.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict


# Defaults match `installer/macos-pkg/scripts/postinstall.sh:919-927` and the
# existing pattern in ai/{ai_score,fingerprint_builder,...}.py:38-42.
_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 5432
_DEFAULT_USER = "guardian_app"
_DEFAULT_OPERATIONAL_DBNAME = "mining_guardian"
_DEFAULT_CATALOG_DBNAME = "mining_guardian_catalog"

# Sentinel that `__repr__` / `__str__` substitute for the real password so
# the value never leaks via accidental logging or traceback rendering.
_PASSWORD_MASK = "***"


@dataclass(frozen=True)
class DBTarget:
    """Resolved Postgres connection parameters for one logical target.

    Frozen dataclass so a target produced by `operational_target()` /
    `catalog_target()` cannot be mutated mid-flight — guards against a
    caller accidentally swapping the dbname after the fact.
    """

    host: str
    port: int
    user: str
    password: str
    dbname: str

    def connect_kwargs(self) -> Dict[str, Any]:
        """Return a psycopg2.connect()-compatible kwargs dict.

        Includes `password` — callers that pass the result to
        `psycopg2.connect(**target.connect_kwargs())` get a working
        connection. Callers that want to log the kwargs should use
        `safe_repr()` instead of stringifying this dict directly.
        """
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dbname": self.dbname,
        }

    def dsn(self) -> str:
        """Return a libpq DSN string with the password embedded.

        Useful for callers (e.g., `psycopg2.connect(dsn)`, `pg_dump`) that
        want a single string. Treat the return value as sensitive — do
        NOT log it. Use `safe_repr()` for logging.
        """
        return (
            f"host={self.host} port={self.port} "
            f"user={self.user} password={self.password} "
            f"dbname={self.dbname}"
        )

    def safe_repr(self) -> str:
        """Return a loggable representation with the password masked."""
        return (
            f"DBTarget(host={self.host!r}, port={self.port}, "
            f"user={self.user!r}, password={_PASSWORD_MASK!r}, "
            f"dbname={self.dbname!r})"
        )

    def __repr__(self) -> str:  # noqa: D401 - dataclass override
        return self.safe_repr()

    def __str__(self) -> str:
        return self.safe_repr()


def _resolve_password() -> str:
    """Resolve the operational/catalog Postgres password.

    Two env-var conventions exist in the Mini's `.env`:

      - `GUARDIAN_PG_PASSWORD` (used by `core/database_pg.py` and the eight
        AI consumers in `ai/*.py`).
      - `MG_DB_PASSWORD` (used by `mg_import_tool/mg_import.py` and
        `intelligence-catalog/db/dual_writer.py`).

    `installer/macos-pkg/scripts/postinstall.sh:919-930` writes both with
    the same value, so either is correct on the Mini. We prefer
    `GUARDIAN_PG_PASSWORD` because it is the more specific name; we fall
    back to `MG_DB_PASSWORD` so a caller migrated to this helper from the
    importer/dual-writer side keeps working without an extra env-var
    rename. Empty string is returned if neither is set; psycopg2 will then
    surface a clear authentication error to the caller, which is the right
    failure mode (better than silently picking up `~/.pgpass`).
    """
    return os.environ.get("GUARDIAN_PG_PASSWORD") or os.environ.get("MG_DB_PASSWORD") or ""


def _resolve_port() -> int:
    """Parse `GUARDIAN_PG_PORT` as int; default to 5432 if unset/invalid.

    A non-integer port is a misconfiguration we surface as the default
    rather than a crash inside resolve — psycopg2 will surface a clearer
    error if 5432 is wrong than a `ValueError` from this helper.
    """
    raw = os.environ.get("GUARDIAN_PG_PORT", "")
    if not raw:
        return _DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_PORT


def operational_target() -> DBTarget:
    """Return the resolved Postgres target for the OPERATIONAL DB.

    dbname comes from `GUARDIAN_PG_DBNAME` (default `mining_guardian`).
    All other fields are shared with `catalog_target()`.
    """
    return DBTarget(
        host=os.environ.get("GUARDIAN_PG_HOST", _DEFAULT_HOST),
        port=_resolve_port(),
        user=os.environ.get("GUARDIAN_PG_USER", _DEFAULT_USER),
        password=_resolve_password(),
        dbname=os.environ.get("GUARDIAN_PG_DBNAME", _DEFAULT_OPERATIONAL_DBNAME),
    )


def catalog_target() -> DBTarget:
    """Return the resolved Postgres target for the CATALOG DB.

    dbname comes from `GUARDIAN_PG_CATALOG_DBNAME` (default
    `mining_guardian_catalog`). All other fields are shared with
    `operational_target()` — both DBs live on the same Postgres container.
    """
    return DBTarget(
        host=os.environ.get("GUARDIAN_PG_HOST", _DEFAULT_HOST),
        port=_resolve_port(),
        user=os.environ.get("GUARDIAN_PG_USER", _DEFAULT_USER),
        password=_resolve_password(),
        dbname=os.environ.get("GUARDIAN_PG_CATALOG_DBNAME", _DEFAULT_CATALOG_DBNAME),
    )
