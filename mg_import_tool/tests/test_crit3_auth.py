"""
test_crit3_auth.py
==================
CRIT-3 unit tests for the mg_import authentication gate.

Verifies:
  - All sensitive routes redirect/401 when not logged in
  - /login accepts the configured password and rejects wrong ones
  - /api/* returns 401 JSON when unauthenticated
  - HTML routes redirect to /login
  - /healthz is unauthenticated by design
  - Sessions expire after MG_IMPORT_SESSION_TTL_SECONDS
  - Constant-time compare is used (smoke check via hmac in the source)

These tests don't need a live Postgres — they only exercise the auth wrapper.
The DB-touching paths short-circuit on `psycopg2` import failure inside the
sandbox, which is fine; the auth gate runs before any DB code.

Run:
    python -m pytest mg_import_tool/tests/test_crit3_auth.py -v
"""
import os
import sys
import time
import pytest

# Set required env vars BEFORE importing mg_import so module-level code that
# reads env doesn't blow up. We intentionally do NOT set MG_DB_PASSWORD here
# because the auth code path doesn't need it; tests that hit DB code would.
os.environ.setdefault("MG_IMPORT_PASSWORD", "test-password-correct-horse")
os.environ.setdefault("MG_IMPORT_SECRET_KEY", "x" * 64)  # 64-char test key
os.environ.setdefault("MG_IMPORT_SESSION_TTL_SECONDS", "28800")
os.environ.setdefault("MG_DB_PASSWORD", "unused-in-these-tests")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mg_import  # noqa: E402


@pytest.fixture
def client():
    mg_import.app.config["TESTING"] = True
    with mg_import.app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Unauth behavior
# ---------------------------------------------------------------------------

class TestUnauthRedirect:
    def test_root_redirects_to_login(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_rma_redirects_to_login(self, client):
        resp = client.get("/rma", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_dormant_redirects_to_login(self, client):
        resp = client.get("/dormant", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_redirect_preserves_next(self, client):
        resp = client.get("/dormant", follow_redirects=False)
        loc = resp.headers["Location"]
        # Werkzeug may or may not percent-encode the slash; accept either form.
        assert "next=/dormant" in loc or "next=%2Fdormant" in loc


class TestUnauthApi:
    def test_api_test_connection_returns_401_json(self, client):
        resp = client.post("/api/test-connection", json={})
        assert resp.status_code == 401
        body = resp.get_json()
        assert body["ok"] is False
        assert body["error"] == "authentication required"
        assert body["login_url"] == "/login"

    def test_api_import_history_returns_401(self, client):
        resp = client.get("/api/import-history")
        assert resp.status_code == 401

    def test_api_browse_tables_returns_401(self, client):
        resp = client.get("/api/browse-tables")
        assert resp.status_code == 401

    def test_api_clear_history_returns_401(self, client):
        resp = client.post("/api/clear-history", json={})
        assert resp.status_code == 401

    def test_api_run_sql_returns_401(self, client):
        resp = client.post("/api/run-sql", json={"sql": "SELECT 1"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /login flow
# ---------------------------------------------------------------------------

class TestLogin:
    def test_get_login_page_renders(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Mining Guardian" in resp.data
        assert b'type="password"' in resp.data

    def test_post_wrong_password_rejected(self, client):
        resp = client.post("/login", data={"password": "wrong"})
        assert resp.status_code == 401
        assert b"Incorrect password" in resp.data

    def test_post_correct_password_accepted(self, client):
        resp = client.post(
            "/login",
            data={"password": "test-password-correct-horse"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

    def test_post_correct_password_then_root_works(self, client):
        client.post("/login", data={"password": "test-password-correct-horse"})
        resp = client.get("/", follow_redirects=False)
        # Should NOT be a redirect to /login. May be 200 (HTML_PAGE) or 500
        # if HTML_PAGE references something not initialised under TESTING; the
        # contract here is purely "auth gate let it through".
        if resp.status_code == 302:
            assert "/login" not in resp.headers.get("Location", "")

    def test_post_correct_password_then_api_returns_non_401(self, client):
        client.post("/login", data={"password": "test-password-correct-horse"})
        resp = client.get("/api/import-history")
        # Either 200 (no history) or a 500 from DB-not-available;
        # what matters is auth no longer rejects it.
        assert resp.status_code != 401

    def test_next_path_traversal_blocked(self, client):
        resp = client.post(
            "/login",
            data={"password": "test-password-correct-horse",
                  "next": "//evil.example.com/x"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        # Should fall back to "/" rather than honoring the protocol-relative URL
        assert resp.headers["Location"].endswith("/")


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_clears_session(self, client):
        client.post("/login", data={"password": "test-password-correct-horse"})
        client.get("/logout")
        resp = client.get("/api/import-history")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /healthz
# ---------------------------------------------------------------------------

class TestHealthz:
    def test_healthz_unauth(self, client):
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        assert body["service"] == "mg_import"


# ---------------------------------------------------------------------------
# Session TTL
# ---------------------------------------------------------------------------

class TestSessionTtl:
    def test_default_ttl_is_8_hours(self):
        # Default is 28800 seconds = 8 hours per D-4
        old = os.environ.pop("MG_IMPORT_SESSION_TTL_SECONDS", None)
        try:
            assert mg_import._import_session_ttl() == 28800
        finally:
            if old is not None:
                os.environ["MG_IMPORT_SESSION_TTL_SECONDS"] = old

    def test_expired_session_treated_as_unauthed(self, client, monkeypatch):
        # Log in, then forge an expired authed_at by patching session TTL to 1s
        # and sleeping past it.
        client.post("/login", data={"password": "test-password-correct-horse"})
        # Confirm logged in
        assert client.get("/api/import-history").status_code != 401
        # Force the next ttl read to return 1s, then advance time virtually.
        # Easier: hand-edit session via test_request_context.
        with client.session_transaction() as sess:
            sess["authed_at"] = time.time() - 999_999  # very old
        resp = client.get("/api/import-history")
        assert resp.status_code == 401

    def test_invalid_ttl_raises(self, monkeypatch):
        monkeypatch.setenv("MG_IMPORT_SESSION_TTL_SECONDS", "not-a-number")
        with pytest.raises(EnvironmentError):
            mg_import._import_session_ttl()

    def test_too_short_ttl_raises(self, monkeypatch):
        monkeypatch.setenv("MG_IMPORT_SESSION_TTL_SECONDS", "30")
        with pytest.raises(EnvironmentError):
            mg_import._import_session_ttl()


# ---------------------------------------------------------------------------
# Env var validation at module level
# ---------------------------------------------------------------------------

class TestEnvValidation:
    def test_missing_password_raises(self, monkeypatch):
        monkeypatch.delenv("MG_IMPORT_PASSWORD", raising=False)
        with pytest.raises(EnvironmentError) as ei:
            mg_import._import_password()
        assert "MG_IMPORT_PASSWORD" in str(ei.value)

    def test_missing_secret_key_raises(self, monkeypatch):
        monkeypatch.delenv("MG_IMPORT_SECRET_KEY", raising=False)
        with pytest.raises(EnvironmentError) as ei:
            mg_import._import_secret_key()
        assert "MG_IMPORT_SECRET_KEY" in str(ei.value)

    def test_short_secret_key_raises(self, monkeypatch):
        monkeypatch.setenv("MG_IMPORT_SECRET_KEY", "tooshort")
        with pytest.raises(EnvironmentError) as ei:
            mg_import._import_secret_key()
        assert "too short" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Constant-time compare
# ---------------------------------------------------------------------------

class TestConstantTimeCompare:
    def test_login_view_uses_hmac_compare(self):
        # Smoke check: confirm the source uses hmac.compare_digest, not ==.
        import inspect
        src = inspect.getsource(mg_import.login_view)
        assert "hmac.compare_digest" in src, (
            "login_view must use hmac.compare_digest to avoid timing oracles"
        )
