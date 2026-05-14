"""
Unit tests for `core/db_targets.py` (P-018A).

Covers default values, env-var override behavior, password masking, and
the operational-vs-catalog dbname split. No DB connection required —
the helper is dependency-free by design.
"""

from __future__ import annotations

import pytest

from core.db_targets import (
    DBTarget,
    catalog_target,
    operational_target,
)


# All `GUARDIAN_PG_*` and `MG_DB_PASSWORD` env vars that the helper reads.
# Wiped at the start of every test via the fixture below so the test
# process doesn't leak state from a real `.env` if pytest is run on a
# developer machine.
_DB_ENV_VARS = (
    "GUARDIAN_PG_HOST",
    "GUARDIAN_PG_PORT",
    "GUARDIAN_PG_USER",
    "GUARDIAN_PG_PASSWORD",
    "GUARDIAN_PG_DBNAME",
    "GUARDIAN_PG_CATALOG_DBNAME",
    "MG_DB_PASSWORD",
)


@pytest.fixture(autouse=True)
def _clean_db_env(monkeypatch):
    """Strip every DB-related env var before each test."""
    for name in _DB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Default values (no env vars set)
# ---------------------------------------------------------------------------


def test_operational_target_returns_documented_defaults():
    target = operational_target()
    assert target.host == "127.0.0.1"
    assert target.port == 5432
    assert target.user == "mg"
    assert target.dbname == "mining_guardian"
    assert target.password == ""


def test_catalog_target_returns_documented_defaults():
    target = catalog_target()
    assert target.host == "127.0.0.1"
    assert target.port == 5432
    assert target.user == "mg"
    assert target.dbname == "mining_guardian_catalog"
    assert target.password == ""


def test_operational_and_catalog_dbnames_differ_by_default():
    """The whole point of the helper: catalog dbname must NOT collapse to
    the operational dbname when no env is set. This is the regression
    guard against the original bug."""
    assert operational_target().dbname != catalog_target().dbname
    assert operational_target().dbname == "mining_guardian"
    assert catalog_target().dbname == "mining_guardian_catalog"


# ---------------------------------------------------------------------------
# Env-var overrides
# ---------------------------------------------------------------------------


def test_operational_target_honors_env_overrides(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("GUARDIAN_PG_PORT", "55432")
    monkeypatch.setenv("GUARDIAN_PG_USER", "mg")
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "secret-op-pw")
    monkeypatch.setenv("GUARDIAN_PG_DBNAME", "custom_operational")

    target = operational_target()

    assert target.host == "127.0.0.1"
    assert target.port == 55432
    assert target.user == "mg"
    assert target.password == "secret-op-pw"
    assert target.dbname == "custom_operational"


def test_catalog_target_honors_env_overrides(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("GUARDIAN_PG_PORT", "55432")
    monkeypatch.setenv("GUARDIAN_PG_USER", "mg")
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "secret-cat-pw")
    monkeypatch.setenv("GUARDIAN_PG_CATALOG_DBNAME", "custom_catalog")

    target = catalog_target()

    assert target.host == "127.0.0.1"
    assert target.port == 55432
    assert target.user == "mg"
    assert target.password == "secret-cat-pw"
    assert target.dbname == "custom_catalog"


def test_catalog_dbname_is_independent_of_operational_dbname(monkeypatch):
    """Override only operational; catalog must still pick up its own var
    (or default), never the operational override."""
    monkeypatch.setenv("GUARDIAN_PG_DBNAME", "operational_only")

    assert operational_target().dbname == "operational_only"
    assert catalog_target().dbname == "mining_guardian_catalog"


def test_operational_dbname_is_independent_of_catalog_dbname(monkeypatch):
    """And the inverse — overriding the catalog must not bleed into
    operational."""
    monkeypatch.setenv("GUARDIAN_PG_CATALOG_DBNAME", "catalog_only")

    assert operational_target().dbname == "mining_guardian"
    assert catalog_target().dbname == "catalog_only"


def test_host_port_user_are_shared_between_operational_and_catalog(monkeypatch):
    """The whole reason the helper can be one module: both targets share
    everything except dbname."""
    monkeypatch.setenv("GUARDIAN_PG_HOST", "10.0.0.5")
    monkeypatch.setenv("GUARDIAN_PG_PORT", "6543")
    monkeypatch.setenv("GUARDIAN_PG_USER", "shared_user")
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "shared-pw")

    op = operational_target()
    cat = catalog_target()

    assert op.host == cat.host == "10.0.0.5"
    assert op.port == cat.port == 6543
    assert op.user == cat.user == "shared_user"
    assert op.password == cat.password == "shared-pw"
    assert op.dbname != cat.dbname


# ---------------------------------------------------------------------------
# Password resolution (two env-var conventions)
# ---------------------------------------------------------------------------


def test_password_falls_back_to_mg_db_password_when_guardian_pg_password_unset(
    monkeypatch,
):
    """`mg_import_tool` / `dual_writer` use `MG_DB_PASSWORD`. If
    `GUARDIAN_PG_PASSWORD` isn't set, fall back to `MG_DB_PASSWORD`."""
    monkeypatch.setenv("MG_DB_PASSWORD", "from-mg-db-password")

    assert operational_target().password == "from-mg-db-password"
    assert catalog_target().password == "from-mg-db-password"


def test_guardian_pg_password_takes_precedence_over_mg_db_password(monkeypatch):
    """When both are set, prefer the more specific `GUARDIAN_PG_PASSWORD`."""
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "from-guardian-pg")
    monkeypatch.setenv("MG_DB_PASSWORD", "from-mg-db")

    assert operational_target().password == "from-guardian-pg"
    assert catalog_target().password == "from-guardian-pg"


def test_password_is_empty_string_when_neither_env_var_is_set():
    """Empty string is intentional: psycopg2 surfaces a clear auth error
    rather than silently picking up `~/.pgpass`."""
    assert operational_target().password == ""
    assert catalog_target().password == ""


# ---------------------------------------------------------------------------
# Port parsing
# ---------------------------------------------------------------------------


def test_invalid_port_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_PORT", "not-a-number")
    assert operational_target().port == 5432
    assert catalog_target().port == 5432


def test_empty_port_string_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_PORT", "")
    assert operational_target().port == 5432


# ---------------------------------------------------------------------------
# Password masking — the bug we don't want to ship
# ---------------------------------------------------------------------------


def test_repr_masks_password(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "super-secret-do-not-leak")

    rendered = repr(operational_target())

    assert "super-secret-do-not-leak" not in rendered
    assert "***" in rendered


def test_str_masks_password(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "super-secret-do-not-leak")

    rendered = str(catalog_target())

    assert "super-secret-do-not-leak" not in rendered
    assert "***" in rendered


def test_safe_repr_masks_password(monkeypatch):
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "super-secret-do-not-leak")

    rendered = operational_target().safe_repr()

    assert "super-secret-do-not-leak" not in rendered
    assert "***" in rendered


def test_format_string_uses_masked_repr(monkeypatch):
    """`f"{target}"` and `f"{target!r}"` must both mask the password —
    these are the two ways a careless logging line would leak it."""
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "super-secret-do-not-leak")

    target = operational_target()
    formatted = f"{target} / {target!r}"

    assert "super-secret-do-not-leak" not in formatted


# ---------------------------------------------------------------------------
# DSN / connect_kwargs — these MUST still carry the real password
# ---------------------------------------------------------------------------


def test_connect_kwargs_carries_real_password(monkeypatch):
    """connect_kwargs() is the path that reaches psycopg2 — the real
    password has to be present here (callers pass the dict to connect)."""
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "real-pw")

    kwargs = operational_target().connect_kwargs()

    assert kwargs == {
        "host": "127.0.0.1",
        "port": 5432,
        "user": "mg",
        "password": "real-pw",
        "dbname": "mining_guardian",
    }


def test_dsn_string_includes_real_password(monkeypatch):
    """dsn() is sensitive but the password has to be in the string."""
    monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "real-pw")

    dsn = catalog_target().dsn()

    assert "host=127.0.0.1" in dsn
    assert "port=5432" in dsn
    assert "user=mg" in dsn
    assert "password=real-pw" in dsn
    assert "dbname=mining_guardian_catalog" in dsn


# ---------------------------------------------------------------------------
# Frozen-dataclass guarantee
# ---------------------------------------------------------------------------


def test_dbtarget_is_frozen():
    """A caller can't mutate a resolved target mid-flight (defensive
    guard against accidental dbname swap after resolution)."""
    target = operational_target()
    with pytest.raises(Exception):  # FrozenInstanceError on 3.10+
        target.dbname = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Sanity: returned types
# ---------------------------------------------------------------------------


def test_returns_DBTarget_instances():
    assert isinstance(operational_target(), DBTarget)
    assert isinstance(catalog_target(), DBTarget)
