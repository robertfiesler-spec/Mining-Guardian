"""
test_crit6_hardening.py
=======================
CRIT-6 unit tests for catalog API hardening.

Verifies:
  - Module REFUSES to import with placeholder/missing API key
  - Bearer token compare is constant-time (uses hmac.compare_digest)
  - Wrong-token requests get 403
  - Missing-token requests get 401
  - Malformed Authorization header gets 401
  - Section name allow-list rejects unknown values
  - Per-field length caps reject oversized payloads
  - Per-string length cap rejects very long strings
  - Rate limit returns 429 after the threshold
  - /api/v1/health is exempt from auth (intentional)

Run:
    cd intelligence-catalog/catalog-api
    python -m pytest test_crit6_hardening.py -v

These tests use FastAPI's TestClient and never hit the real DB \u2014 the DB pool
is lazily created in the lifespan handler, but no test endpoint here triggers
a DB query that requires a live connection (we test auth/validation, not the
data path).
"""
import importlib
import os
import sys
import pytest


# ---------------------------------------------------------------------------
# Sandbox guard: skip if FastAPI/slowapi aren't installed locally. CI / Mac
# Mini install will have them; the dev sandbox may not.
# ---------------------------------------------------------------------------
fastapi = pytest.importorskip("fastapi")
slowapi = pytest.importorskip("slowapi")
psycopg2 = pytest.importorskip("psycopg2")

from fastapi.testclient import TestClient  # noqa: E402


VALID_KEY = "a" * 64  # 64-char hex-ish key, satisfies >= 32 chars rule


@pytest.fixture(autouse=True)
def _set_required_env(monkeypatch):
    """Set the env required for module import. Each test gets a clean slate."""
    monkeypatch.setenv("DB_PASSWORD", "test-db-pw-not-real")
    monkeypatch.setenv("CATALOG_API_KEY", VALID_KEY)
    # Loosen rate limit so the test_rate_limit case can hit it cleanly without
    # affecting other tests.
    monkeypatch.setenv("CATALOG_RATE_LIMIT_SCAN_BUNDLE", "60/minute")
    monkeypatch.setenv("CATALOG_RATE_LIMIT_MINER", "120/minute")
    monkeypatch.setenv("CATALOG_RATE_LIMIT_HEALTH", "600/minute")


@pytest.fixture
def app_module(monkeypatch):
    """Re-import the catalog_api module fresh for each test so env-var
    validation runs with the patched environment."""
    sys.modules.pop("catalog_api", None)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    mod = importlib.import_module("catalog_api")
    return mod


@pytest.fixture
def client(app_module):
    return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Startup-time env validation
# ---------------------------------------------------------------------------

class TestStartupEnvValidation:
    def test_placeholder_api_key_rejected(self, monkeypatch):
        sys.modules.pop("catalog_api", None)
        monkeypatch.setenv("CATALOG_API_KEY", "CHANGE_ME_TO_A_REAL_SECRET")
        with pytest.raises(EnvironmentError) as ei:
            importlib.import_module("catalog_api")
        assert "placeholder" in str(ei.value).lower()

    def test_installer_placeholder_rejected(self, monkeypatch):
        sys.modules.pop("catalog_api", None)
        monkeypatch.setenv("CATALOG_API_KEY", "__GENERATE_AT_INSTALL_TIME__")
        with pytest.raises(EnvironmentError):
            importlib.import_module("catalog_api")

    def test_empty_api_key_rejected(self, monkeypatch):
        sys.modules.pop("catalog_api", None)
        monkeypatch.setenv("CATALOG_API_KEY", "")
        with pytest.raises(EnvironmentError):
            importlib.import_module("catalog_api")

    def test_short_api_key_rejected(self, monkeypatch):
        sys.modules.pop("catalog_api", None)
        monkeypatch.setenv("CATALOG_API_KEY", "tooshort1234")  # 12 chars
        with pytest.raises(EnvironmentError) as ei:
            importlib.import_module("catalog_api")
        assert "too short" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Auth behavior on a real endpoint
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_token_401(self, client):
        # /api/v1/knowledge/miner/{slug} requires auth and is a GET, simpler
        # than the scan-bundle DB-touching path.
        resp = client.get("/api/v1/knowledge/miner/s19")
        assert resp.status_code == 401

    def test_malformed_header_401(self, client):
        resp = client.get(
            "/api/v1/knowledge/miner/s19",
            headers={"Authorization": "NotBearer xyz"},
        )
        assert resp.status_code == 401

    def test_wrong_token_403(self, client):
        resp = client.get(
            "/api/v1/knowledge/miner/s19",
            headers={"Authorization": f"Bearer {'b' * 64}"},
        )
        assert resp.status_code == 403

    def test_constant_time_compare_used(self, app_module):
        import inspect
        src = inspect.getsource(app_module.verify_token)
        assert "hmac.compare_digest" in src

    def test_health_unauth_allowed(self, client):
        # Health may return 200 (DB ok) or 200/degraded (DB down). What
        # matters is auth doesn't reject it.
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Input validation on ScanBundleRequest
# ---------------------------------------------------------------------------

class TestInputValidation:
    AUTH = {"Authorization": f"Bearer {VALID_KEY}"}

    def test_unknown_section_rejected(self, client):
        resp = client.post(
            "/api/v1/context/scan-bundle",
            headers=self.AUTH,
            json={
                "miner_models": ["S19"],
                "include_sections": ["failure_patterns", "evil_payload"],
            },
        )
        assert resp.status_code == 422  # FastAPI/Pydantic validation error

    def test_too_many_models_rejected(self, client):
        resp = client.post(
            "/api/v1/context/scan-bundle",
            headers=self.AUTH,
            json={"miner_models": ["S19"] * 201},  # _MAX_MODELS = 200
        )
        assert resp.status_code == 422

    def test_too_many_issues_rejected(self, client):
        resp = client.post(
            "/api/v1/context/scan-bundle",
            headers=self.AUTH,
            json={"active_issues": ["E001"] * 101},  # _MAX_ISSUES = 100
        )
        assert resp.status_code == 422

    def test_oversized_string_rejected(self, client):
        big = "X" * 257  # _MAX_STR_LEN = 256
        resp = client.post(
            "/api/v1/context/scan-bundle",
            headers=self.AUTH,
            json={"miner_models": [big]},
        )
        assert resp.status_code == 422

    def test_at_limits_accepted(self, client):
        # 200 models, 256-char string \u2014 boundary cases should pass validation
        # (the request may then fail downstream at the DB layer in this sandbox,
        # but auth + validation must let it through with a non-422).
        resp = client.post(
            "/api/v1/context/scan-bundle",
            headers=self.AUTH,
            json={
                "miner_models": ["X" * 256] * 200,
                "active_issues": [],
                "include_sections": ["failure_patterns"],
            },
        )
        assert resp.status_code != 422, resp.text

    def test_miner_slug_query_length_capped(self, client):
        big = "y" * 300  # > 256
        resp = client.get(
            f"/api/v1/knowledge/miner/s19?include={big}",
            headers=self.AUTH,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_rate_limit_triggers_429(self, monkeypatch):
        # Set a *very* low limit and re-import so the new value sticks.
        monkeypatch.setenv("CATALOG_RATE_LIMIT_HEALTH", "3/minute")
        sys.modules.pop("catalog_api", None)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        mod = importlib.import_module("catalog_api")
        c = TestClient(mod.app)
        codes = [c.get("/api/v1/health").status_code for _ in range(8)]
        # First 3 should pass (200), at least one of the next 5 should be 429.
        assert codes[:3] == [200, 200, 200], codes
        assert 429 in codes[3:], codes
