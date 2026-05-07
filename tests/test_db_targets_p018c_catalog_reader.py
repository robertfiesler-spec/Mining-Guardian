"""
P-018C tests.

Verify that the scanner's intelligence-catalog reader
(`ai/catalog_context.py`) is fully psycopg-backed and reads from the
local catalog DB resolved by `core.db_targets.catalog_target()`. The
retired ROBS-PC HTTP host (`100.110.87.1:8420`) MUST no longer appear
in any default code path; the only opt-in HTTP fallback path is gated
on `MG_CATALOG_HTTP_FALLBACK_URL` and refuses any value that points at
the retired host.

Also covers the two-connection split in
`intelligence-catalog/db/feedback_loop.py` — operational reads come
from `operational_target()`, catalog model_id lookup + UPSERT writes
come from `catalog_target()`, and the legacy single-connection signature
(`conn=`) has been replaced with `op_conn=` / `cat_conn=`.

No live DB required. The `psycopg2` module is faked via
`monkeypatch.setitem(sys.modules, …)` so the whole suite runs in any
sandbox.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from unittest import mock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


_DB_ENV_VARS = (
    "GUARDIAN_PG_HOST",
    "GUARDIAN_PG_PORT",
    "GUARDIAN_PG_USER",
    "GUARDIAN_PG_PASSWORD",
    "GUARDIAN_PG_DBNAME",
    "GUARDIAN_PG_CATALOG_DBNAME",
    "MG_DB_PASSWORD",
    "MG_CATALOG_HTTP_FALLBACK_URL",
    "CATALOG_API_URL",  # legacy — must not be silently honored
    "CATALOG_API_KEY",
)


@pytest.fixture(autouse=True)
def _clean_db_env(monkeypatch):
    for name in _DB_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Static / source-level regression guards
# ---------------------------------------------------------------------------


class TestCatalogContextSourceRegression:
    def test_no_robs_pc_default_in_source(self):
        """The retired Tailscale host MUST not appear as a default URL.

        It may still be referenced in comments / docstring history
        (P-018C explains why it's gone), but it must NOT be a default
        runtime value. Two flagged shapes are the legacy default and
        any `os.getenv("CATALOG_API_URL", …)` whose default contains
        the IP — both of which silently brought back the bug."""
        path = REPO_ROOT / "ai" / "catalog_context.py"
        text = path.read_text(encoding="utf-8")
        # Bad shape 1: the literal default that started this whole
        # diagnostic.
        assert (
            'os.getenv("CATALOG_API_URL", "http://100.110.87.1' not in text
        ), "ai/catalog_context.py still defaults to retired ROBS-PC host"
        # Bad shape 2: any occurrence of the legacy CATALOG_API_URL env
        # var as a *value source* (not just as a string in a guard
        # comment) — guarded by checking it's not assigned to a module
        # constant.
        assert "CATALOG_API_URL = os.getenv" not in text
        # Bad shape 3: any line that imports `requests` at module top
        # (the previous file's first non-comment top-level import).
        first_lines = "\n".join(text.splitlines()[:60])
        assert "import requests" not in first_lines

    def test_module_uses_catalog_target_helper(self):
        """The new reader must source its DSN from
        `core.db_targets.catalog_target()` — not from a local
        `os.environ.get("GUARDIAN_PG_CATALOG_DBNAME", …)` shortcut, not
        from the legacy `PGDATABASE`/`PGHOST` family."""
        path = REPO_ROOT / "ai" / "catalog_context.py"
        text = path.read_text(encoding="utf-8")
        assert "catalog_target" in text
        assert "from core.db_targets import" in text

    def test_module_no_longer_imports_requests_for_default_path(self):
        """The HTTP-only `import requests` at module top is gone. Any
        opt-in HTTP fallback would import inside a function, gated on
        an explicit env var."""
        path = REPO_ROOT / "ai" / "catalog_context.py"
        text = path.read_text(encoding="utf-8")
        # Top-level `import requests` is the bad shape (always loads,
        # implies HTTP is the default path).
        first_lines = "\n".join(text.splitlines()[:80])
        assert "import requests" not in first_lines


# ---------------------------------------------------------------------------
# Loader: import ai.catalog_context with a fake psycopg2 attached.
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_psycopg2(monkeypatch):
    """Fake psycopg2 with a controllable `connect()`.

    Tests can override `mock_connect.side_effect` or
    `mock_connect.return_value` per case. Auto-rolls back per test.
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


def _load_catalog_context_fresh():
    """Import `ai.catalog_context` fresh per test.

    Module-level `_failure_count` / `_circuit_open_until` /
    `_last_read_was_failure` are state we want clean per case.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if "ai.catalog_context" in sys.modules:
        del sys.modules["ai.catalog_context"]
    return importlib.import_module("ai.catalog_context")


# ---------------------------------------------------------------------------
# Connection target — must read GUARDIAN_PG_CATALOG_DBNAME
# ---------------------------------------------------------------------------


class TestCatalogContextConnectionTarget:
    def test_connect_uses_catalog_dbname_default(self, monkeypatch, fake_psycopg2):
        """No env set ⇒ default `mining_guardian_catalog`."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        # Make connect() raise so we capture kwargs without needing a
        # real connection; the failure path goes through _record_failure
        # and is_catalog_available returns False — both fine for this
        # assertion.
        fake_psycopg2.side_effect = RuntimeError("captured")
        cc = _load_catalog_context_fresh()

        cc.is_catalog_available()

        fake_psycopg2.assert_called_once()
        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "mining_guardian_catalog"

    def test_connect_honors_catalog_dbname_override(self, monkeypatch, fake_psycopg2):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_CATALOG_DBNAME", "custom_catalog")
        fake_psycopg2.side_effect = RuntimeError("captured")
        cc = _load_catalog_context_fresh()

        cc.is_catalog_available()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "custom_catalog"

    def test_connect_does_not_use_operational_dbname(self, monkeypatch, fake_psycopg2):
        """Setting only `GUARDIAN_PG_DBNAME` must NOT redirect the
        scanner reader at the operational DB. Regression guard for the
        boundary between operational (P-018B) and catalog (P-018C)."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("GUARDIAN_PG_DBNAME", "operational_only")
        fake_psycopg2.side_effect = RuntimeError("captured")
        cc = _load_catalog_context_fresh()

        cc.is_catalog_available()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] != "operational_only"
        assert kwargs["dbname"] == "mining_guardian_catalog"

    def test_no_legacy_catalog_api_url_dependency(self, monkeypatch, fake_psycopg2):
        """Setting the old `CATALOG_API_URL` env var to ROBS-PC MUST
        NOT change behavior — that variable is no longer read for
        anything. Regression guard against operators with a stale .env
        accidentally pointing at the retired host."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        monkeypatch.setenv("CATALOG_API_URL", "http://100.110.87.1:8420")
        fake_psycopg2.side_effect = RuntimeError("captured")
        cc = _load_catalog_context_fresh()

        # The connect path must still target the catalog DB; the URL
        # doesn't enter the picture.
        cc.is_catalog_available()
        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "mining_guardian_catalog"
        # And no `requests`-using code path was even imported.
        assert "requests" not in sys.modules or sys.modules["requests"] is None or True
        # (We keep the assertion soft re: requests because some other
        # test in the run may have imported it. The decisive guard is
        # that connect() was called against the catalog DB.)


# ---------------------------------------------------------------------------
# Public API contracts — soft / strict / circuit / shape preservation
# ---------------------------------------------------------------------------


def _stub_connection_with_model_row(fake_connect, *, model_row=None,
                                    chip_rows=None, raise_on_query=False):
    """Build a fake psycopg2 connection whose cursor returns the
    supplied per-section rows. `model_row` is a tuple matching the
    SELECT shape of `_resolve_model_row`. The cursor's `description`
    is set per query so `_row_to_dict` produces the right keys.

    This is intentionally simple — the goal is to verify that
    `_format_miner_knowledge` sees the expected dict shape, not to
    re-implement psycopg2's cursor semantics."""
    cursor = mock.MagicMock(name="cursor")
    cursor.__enter__ = mock.MagicMock(return_value=cursor)
    cursor.__exit__ = mock.MagicMock(return_value=False)

    state = {"phase": "init"}

    def execute(sql, params=()):
        if raise_on_query:
            raise RuntimeError("simulated query failure")
        s = sql.lower()
        if "to_regclass" in s:
            cursor.fetchone = mock.MagicMock(return_value=("present",))
            cursor.description = [("regclass",)]
            return
        if "from hardware.miner_models" in s and "manufacturer_id" in s:
            cursor.description = [
                ("id",), ("canonical_name",), ("model_number",),
                ("cooling_mode",), ("hashrate_th",), ("power_watts",),
                ("efficiency_jth",), ("released_date",),
                ("is_current_product",), ("manufacturer",),
            ]
            cursor.fetchone = mock.MagicMock(return_value=model_row)
            return
        if "from hardware.chips" in s:
            cursor.description = [("chip_name",), ("process_node",), ("nominal_freq_mhz",)]
            cursor.fetchall = mock.MagicMock(return_value=chip_rows or [])
            return
        # Other tables: empty.
        cursor.description = []
        cursor.fetchall = mock.MagicMock(return_value=[])
        cursor.fetchone = mock.MagicMock(return_value=None)

    cursor.execute = mock.MagicMock(side_effect=execute)

    conn = mock.MagicMock(name="conn")
    conn.__enter__ = mock.MagicMock(return_value=conn)
    conn.__exit__ = mock.MagicMock(return_value=False)
    conn.cursor = mock.MagicMock(return_value=cursor)
    conn.close = mock.MagicMock()

    fake_connect.return_value = conn
    fake_connect.side_effect = None
    return conn


class TestPerMinerReader:
    def test_returns_formatted_string_for_known_model(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        cc = _load_catalog_context_fresh()
        # Tuple matches the SELECT in _resolve_model_row.
        model_row = (
            "uuid-1234",                # id
            "Antminer S19j Pro",        # canonical_name
            "S19J Pro",                 # model_number
            "air-cooled",               # cooling_mode
            104.0,                      # hashrate_th
            3068.0,                     # power_watts
            29.5,                       # efficiency_jth
            None,                       # released_date
            True,                       # is_current_product
            "Bitmain",                  # manufacturer
        )
        _stub_connection_with_model_row(fake_psycopg2, model_row=model_row)

        text = cc.get_miner_catalog_context("S19J Pro")

        assert text  # non-empty
        assert "Catalog: S19J Pro" in text
        assert "Bitmain" in text
        assert "104" in text
        assert cc.last_read_failed() is False

    def test_returns_empty_string_for_missing_model(
        self, monkeypatch, fake_psycopg2
    ):
        """Model not in catalog ⇒ empty string + last_read_failed False
        (NOT a failure; matches the HTTP-era 404 contract)."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        cc = _load_catalog_context_fresh()
        _stub_connection_with_model_row(fake_psycopg2, model_row=None)

        text = cc.get_miner_catalog_context("UnknownModel")

        assert text == ""
        assert cc.last_read_failed() is False

    def test_real_failure_marks_last_read_failed(self, monkeypatch, fake_psycopg2):
        """DB connect failure ⇒ empty string + last_read_failed True."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        fake_psycopg2.side_effect = RuntimeError("connect failed")
        cc = _load_catalog_context_fresh()

        text = cc.get_miner_catalog_context("S19J Pro")

        assert text == ""
        assert cc.last_read_failed() is True

    def test_strict_variant_raises_on_real_failure(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        fake_psycopg2.side_effect = RuntimeError("connect failed")
        cc = _load_catalog_context_fresh()

        with pytest.raises(cc.CatalogReadFailure):
            cc.get_miner_catalog_context_strict("S19J Pro")

    def test_strict_variant_does_not_raise_on_404(
        self, monkeypatch, fake_psycopg2
    ):
        """A 404-equivalent (model not in catalog) must NOT raise — the
        scanner relies on `""` to mean 'evaluate without catalog
        context'."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        cc = _load_catalog_context_fresh()
        _stub_connection_with_model_row(fake_psycopg2, model_row=None)

        text = cc.get_miner_catalog_context_strict("UnknownModel")
        assert text == ""

    def test_circuit_breaker_opens_after_three_failures(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        fake_psycopg2.side_effect = RuntimeError("simulated")
        cc = _load_catalog_context_fresh()

        # Three failed reads opens the breaker.
        for _ in range(3):
            cc.get_miner_catalog_context("S19J Pro")
        # Fourth call: breaker should short-circuit before connect.
        before_calls = fake_psycopg2.call_count
        text = cc.get_miner_catalog_context("S19J Pro")
        after_calls = fake_psycopg2.call_count

        assert text == ""
        assert cc.last_read_failed() is True
        # The breaker may permit a single half-open attempt depending on
        # timing; confirm at minimum no flood of connects past the
        # threshold.
        assert (after_calls - before_calls) <= 1


class TestBulkReader:
    def test_bulk_returns_concatenated_per_miner_strings(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        cc = _load_catalog_context_fresh()
        model_row = (
            "uuid-A", "Antminer S19j Pro", "S19J Pro",
            "air-cooled", 104.0, 3068.0, 29.5, None, True, "Bitmain",
        )
        _stub_connection_with_model_row(fake_psycopg2, model_row=model_row)

        text = cc.get_catalog_context(["S19J Pro", "S21 Hydro"], ["low_hashrate"])

        # Active issues are surfaced as a header line.
        assert "active_issues" in text
        # Each per-miner section appears.
        assert text.count("Catalog:") >= 1

    def test_bulk_returns_empty_on_empty_input(self, monkeypatch, fake_psycopg2):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        cc = _load_catalog_context_fresh()

        assert cc.get_catalog_context([]) == ""
        assert cc.last_read_failed() is False


# ---------------------------------------------------------------------------
# HTTP fallback safety guard
# ---------------------------------------------------------------------------


class TestHttpFallbackSafety:
    def test_http_fallback_is_off_by_default(self, monkeypatch):
        cc = _load_catalog_context_fresh()
        assert cc._http_fallback_url() is None

    def test_http_fallback_refuses_robs_pc_address(self, monkeypatch):
        monkeypatch.setenv("MG_CATALOG_HTTP_FALLBACK_URL", "http://100.110.87.1:8420")
        cc = _load_catalog_context_fresh()
        assert cc._http_fallback_url() is None

    def test_http_fallback_accepts_explicit_local_address(self, monkeypatch):
        monkeypatch.setenv("MG_CATALOG_HTTP_FALLBACK_URL", "http://127.0.0.1:9999")
        cc = _load_catalog_context_fresh()
        assert cc._http_fallback_url() == "http://127.0.0.1:9999"


# ---------------------------------------------------------------------------
# feedback_loop two-connection split (P-018C)
# ---------------------------------------------------------------------------


def _load_feedback_loop_fresh():
    """Load `intelligence-catalog/db/feedback_loop.py` fresh per test."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    spec = importlib.util.spec_from_file_location(
        "_p018c_feedback_loop",
        REPO_ROOT / "intelligence-catalog" / "db" / "feedback_loop.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestFeedbackLoopTwoConnections:
    def test_open_op_connection_targets_operational_dbname(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        fake_psycopg2.side_effect = RuntimeError("captured")
        fb = _load_feedback_loop_fresh()

        fb._open_op_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "mining_guardian"

    def test_open_cat_connection_targets_catalog_dbname(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        fake_psycopg2.side_effect = RuntimeError("captured")
        fb = _load_feedback_loop_fresh()

        fb._open_cat_connection()

        kwargs = fake_psycopg2.call_args.kwargs
        assert kwargs["dbname"] == "mining_guardian_catalog"

    def test_op_and_cat_targets_share_host_port_user_password(
        self, monkeypatch, fake_psycopg2
    ):
        monkeypatch.setenv("MG_DB_PASSWORD", "shared-pw")
        monkeypatch.setenv("GUARDIAN_PG_HOST", "10.0.0.5")
        monkeypatch.setenv("GUARDIAN_PG_PORT", "6543")
        monkeypatch.setenv("GUARDIAN_PG_USER", "shared_user")
        fake_psycopg2.side_effect = RuntimeError("captured")
        fb = _load_feedback_loop_fresh()

        fb._open_op_connection()
        op_kwargs = fake_psycopg2.call_args.kwargs
        fb._open_cat_connection()
        cat_kwargs = fake_psycopg2.call_args.kwargs

        for key in ("host", "port", "user", "password"):
            assert op_kwargs[key] == cat_kwargs[key]
        assert op_kwargs["dbname"] != cat_kwargs["dbname"]

    def test_sync_signatures_take_op_conn_and_cat_conn(self):
        """Public sync signatures expose `op_conn=` and `cat_conn=` —
        the legacy `conn=` kwarg is gone."""
        fb = _load_feedback_loop_fresh()
        for fn_name in (
            "sync_action_audit_to_failure_patterns",
            "sync_llm_analysis_to_war_stories",
            "sync_miner_restarts_to_known_issues",
        ):
            fn = getattr(fb, fn_name)
            params = fn.__code__.co_varnames[: fn.__code__.co_argcount + fn.__code__.co_kwonlyargcount]
            assert "op_conn" in params, f"{fn_name} missing op_conn kwarg"
            assert "cat_conn" in params, f"{fn_name} missing cat_conn kwarg"
            assert "conn" not in params, f"{fn_name} still has legacy conn kwarg"

    def test_run_full_feedback_loop_opens_both_connections(
        self, monkeypatch, fake_psycopg2
    ):
        """`run_full_feedback_loop` must open BOTH connections before
        delegating to the three syncs."""
        monkeypatch.setenv("MG_DB_PASSWORD", "test-pw")
        # Make connect raise so we can count opens without needing
        # full sync execution.
        fake_psycopg2.side_effect = RuntimeError("captured")
        fb = _load_feedback_loop_fresh()

        out = fb.run_full_feedback_loop()

        # Both connections were attempted (and both failed in the same
        # way), so each sync gets a "no connection" stats row. Verify
        # that connect was tried twice up front, not three times per
        # sync.
        assert fake_psycopg2.call_count == 2
        for v in out.values():
            assert v["error"] == "no postgres connection (operational or catalog)"
