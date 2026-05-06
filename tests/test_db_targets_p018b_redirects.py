"""
P-018B redirect tests.

Verify that the catalog WRITER paths (`intelligence-catalog/db/dual_writer.py`)
and the importer (`mg_import_tool/mg_import.py`) source their connection
parameters from `core.db_targets` — and specifically that the catalog
writer reads `GUARDIAN_PG_CATALOG_DBNAME` rather than `GUARDIAN_PG_DBNAME`
or a hard-coded `mining_guardian` literal.

These are unit tests with `psycopg2.connect` mocked at the module level,
so no DB is required and the test is fast. The point is to lock in the
P-018B contract: future code that re-introduces the operational default
inside these writer paths fails the test.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


# Same env-var hygiene as test_db_targets.py — strip everything between tests.
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
    for name in _DB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Loader: import the hyphenated `intelligence-catalog/db/dual_writer.py`
# under a stable name so we can mock its `psycopg2.connect`.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_psycopg2(monkeypatch):
    """Install a fake `psycopg2` only for the duration of the test.

    `monkeypatch.setitem` on `sys.modules` rolls back automatically when
    the test exits, so this never pollutes other tests' real-psycopg2
    imports — we tripped on that the first time around.
    """
    fake_connect = mock.MagicMock(name="psycopg2.connect")
    fake_extras = types.SimpleNamespace(
        Json=lambda x: x,
        register_uuid=lambda: None,
    )
    fake_pkg = types.ModuleType("psycopg2")
    fake_pkg.connect = fake_connect  # type: ignore[attr-defined]
    fake_pkg.extras = fake_extras  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "psycopg2", fake_pkg)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", fake_extras)  # type: ignore[arg-type]
    return fake_connect


def _load_dual_writer_fresh():
    """Load dual_writer.py under a stable name, fresh per test.

    Repo root is added to sys.path so the module can resolve
    `from core.db_targets import catalog_target`. Module is loaded fresh
    each time so module-level state (e.g. `_UUID_ADAPTER_REGISTERED`)
    doesn't leak across tests.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    spec = importlib.util.spec_from_file_location(
        "_p018b_dual_writer",
        REPO_ROOT / "intelligence-catalog" / "db" / "dual_writer.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# dual_writer.py — must connect to the CATALOG DB
# ---------------------------------------------------------------------------


class TestDualWriterTargetsCatalog:
    def test_get_connection_uses_catalog_dbname_default(self, monkeypatch, fake_psycopg2):
        """No env set ⇒ catalog default `mining_guardian_catalog`."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        dw = _load_dual_writer_fresh()

        dw._get_connection()

        fake_psycopg2.assert_called_once()
        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "mining_guardian_catalog"

    def test_get_connection_honors_catalog_dbname_override(self, monkeypatch, fake_psycopg2):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_CATALOG_DBNAME", "custom_catalog")
        dw = _load_dual_writer_fresh()

        dw._get_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "custom_catalog"

    def test_get_connection_does_not_use_operational_dbname(self, monkeypatch, fake_psycopg2):
        """Setting GUARDIAN_PG_DBNAME (operational) must NOT redirect the
        catalog writer. This is the regression guard for the original bug."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_DBNAME", "some_operational_name")
        dw = _load_dual_writer_fresh()

        dw._get_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] != "some_operational_name"
        assert kwargs["dbname"] == "mining_guardian_catalog"

    def test_get_connection_reads_shared_host_port_user(self, monkeypatch, fake_psycopg2):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_HOST", "10.0.0.5")
        monkeypatch.setenv("GUARDIAN_PG_PORT", "6543")
        monkeypatch.setenv("GUARDIAN_PG_USER", "shared_user")
        dw = _load_dual_writer_fresh()

        dw._get_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["host"] == "10.0.0.5"
        assert kwargs["port"] == 6543
        assert kwargs["user"] == "shared_user"
        assert kwargs["password"] == "test-pw"

    def test_get_connection_returns_none_when_password_missing(self, fake_psycopg2):
        # No password set anywhere — fail-soft, return None.
        dw = _load_dual_writer_fresh()

        result = dw._get_connection()

        assert result is None
        fake_psycopg2.assert_not_called()

    def test_get_connection_falls_back_to_guardian_pg_password(
        self, monkeypatch, fake_psycopg2
    ):
        """`core.db_targets` prefers GUARDIAN_PG_PASSWORD over MG_DB_PASSWORD;
        verify that path through to dual_writer."""
        monkeypatch.setenv("GUARDIAN_PG_PASSWORD", "from-guardian-pg")
        dw = _load_dual_writer_fresh()

        dw._get_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["password"] == "from-guardian-pg"


# ---------------------------------------------------------------------------
# mg_import.py — must keep targeting the OPERATIONAL DB by design
# ---------------------------------------------------------------------------


def _load_mg_import():
    """Import mg_import_tool/mg_import.py under a stable name without
    starting Flask. We only need `_connect_kwargs` /
    `_resolve_operational_target` which run module-import-time pure-python
    code; we do NOT call `app.run`. To avoid the env-required startup
    guard inside `_db_password`, callers set MG_DB_PASSWORD before
    invoking those helpers.

    Loaded fresh per call so module-level state doesn't leak across tests.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    spec = importlib.util.spec_from_file_location(
        "_p018b_mg_import",
        REPO_ROOT / "mg_import_tool" / "mg_import.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestMgImportTargetsOperational:
    def test_connect_kwargs_uses_operational_dbname_default(self, monkeypatch):
        """Empty conn_params ⇒ operational default `mining_guardian`.

        The importer writes `knowledge.field_log_*` and `mg.import_runs`,
        which live in the operational DB, so this is the correct target.
        P-018B redirected the *resolution* through `operational_target()`,
        but the runtime default must remain operational, not catalog.
        """
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        mod = _load_mg_import()

        kwargs = mod._connect_kwargs({})

        assert kwargs["dbname"] == "mining_guardian"

    def test_connect_kwargs_does_not_use_catalog_dbname(self, monkeypatch):
        """Setting GUARDIAN_PG_CATALOG_DBNAME must NOT redirect the
        importer. Importer writes operational tables; only the catalog
        writer in dual_writer.py should respond to that env var.

        This locks in the boundary between P-018B (writers redirected)
        and P-018C (importer Tier-1 alias lookup redirected).
        """
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv(
            "GUARDIAN_PG_CATALOG_DBNAME", "should_not_be_picked_up"
        )
        mod = _load_mg_import()

        kwargs = mod._connect_kwargs({})

        assert kwargs["dbname"] != "should_not_be_picked_up"
        assert kwargs["dbname"] == "mining_guardian"

    def test_connect_kwargs_honors_operational_dbname_override(self, monkeypatch):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_DBNAME", "custom_operational")
        mod = _load_mg_import()

        kwargs = mod._connect_kwargs({})

        assert kwargs["dbname"] == "custom_operational"

    def test_connect_kwargs_request_dict_overrides_target(self, monkeypatch):
        """A non-empty `conn_params` (i.e., the user passed an explicit
        host/port/database/user via the importer's connection form)
        wins over the resolved target."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        mod = _load_mg_import()

        kwargs = mod._connect_kwargs({
            "host": "explicit.host",
            "port": "9999",
            "database": "explicit_db",
            "user": "explicit_user",
        })

        assert kwargs["host"] == "explicit.host"
        assert kwargs["port"] == 9999
        assert kwargs["dbname"] == "explicit_db"
        assert kwargs["user"] == "explicit_user"

    def test_connect_kwargs_fills_password_from_env(self, monkeypatch):
        """Password is never read from `conn_params` (security) — it
        always comes from `_db_password()` reading MG_DB_PASSWORD."""
        monkeypatch.setenv("MG_DB_PASSWORD", "from-env")
        mod = _load_mg_import()

        kwargs = mod._connect_kwargs({"password": ""})

        assert kwargs["password"] == "from-env"


# ---------------------------------------------------------------------------
# feedback_loop.py — P-018B set the deferral marker; P-018C completed the
# two-connection refactor. The regression guards below were written for
# the deferral state (P-018B); they're updated here to assert the
# completed state (P-018C) so the suite continues to fence the file.
# ---------------------------------------------------------------------------


class TestFeedbackLoopRefactored:
    def test_module_uses_p018c_two_connection_split(self):
        """Module must reference both operational AND catalog targets
        (via core.db_targets) and must NOT keep the single-connection
        helper as the active path. If a future patch collapses back to
        one connection, this test fails."""
        path = REPO_ROOT / "intelligence-catalog" / "db" / "feedback_loop.py"
        text = path.read_text(encoding="utf-8")
        assert "operational_target" in text
        assert "catalog_target" in text
        assert "_open_op_connection" in text
        assert "_open_cat_connection" in text
        # The legacy single-connection comment block from P-018B must be
        # gone — leaving it would falsely advertise a deferral state.
        assert "P-018B note (deferred to P-018C)" not in text

    def test_module_no_longer_hardcodes_pgdatabase_default(self):
        """The pre-P-018C single-connection helper hard-coded
        `os.environ.get("PGDATABASE", "mining_guardian")` as the only
        DSN source. With the two-connection split, all DSN resolution
        goes through `core.db_targets`; the literal must be gone."""
        path = REPO_ROOT / "intelligence-catalog" / "db" / "feedback_loop.py"
        text = path.read_text(encoding="utf-8")
        assert 'os.environ.get("PGDATABASE", "mining_guardian")' not in text
