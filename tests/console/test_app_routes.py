"""
tests/console/test_app_routes.py — D-19 console (P-006)

End-to-end-ish tests using FastAPI's TestClient. DB and launchctl are
both mocked, so these tests do not require a Postgres or a launchd.
"""

import os
from unittest.mock import patch

import pytest

# Force mock mode so launchctl is never invoked.
os.environ["MG_CONSOLE_LAUNCHCTL"] = "mock"


@pytest.fixture
def client():
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from console.main import app
    return TestClient(app)


def test_healthz_returns_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_root_redirects_to_tasks(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/tasks"


def test_tasks_page_renders(client):
    r = client.get("/tasks")
    assert r.status_code == 200
    body = r.text
    # Spot-check a couple of registered tasks render in the HTML.
    assert "Hourly Scanner" in body
    assert "Morning Briefing" in body
    assert "Approve" not in body  # tasks page must not show approval buttons


def test_tasks_htmx_partial(client):
    r = client.get("/tasks/htmx")
    assert r.status_code == 200
    # Partial: should NOT include the <html> shell.
    assert "<!doctype html>" not in r.text.lower()
    assert "Hourly Scanner" in r.text


def test_pause_unknown_task_404s(client):
    r = client.post("/tasks/no-such-task/pause")
    assert r.status_code == 404


def test_pause_non_pausable_400s(client):
    # dashboard_api is not pausable in v1.
    r = client.post("/tasks/dashboard_api/pause")
    assert r.status_code == 400


def test_pause_pausable_task_returns_row(client):
    r = client.post("/tasks/scanner/pause")
    assert r.status_code == 200
    assert "task-scanner" in r.text


def test_resume_pausable_task_returns_row(client):
    r = client.post("/tasks/scanner/resume")
    assert r.status_code == 200
    assert "task-scanner" in r.text


def test_automation_page_renders(client):
    # Patch get_setting so DB is not required.
    with patch("api.system_settings.get_setting", return_value="FULL_AUTO"):
        r = client.get("/automation")
    assert r.status_code == 200
    assert "FULL_AUTO" in r.text


def test_automation_set_invalid_mode_400(client):
    r = client.post("/automation/mode", data={"mode": "BOGUS"})
    assert r.status_code == 400


def test_automation_set_valid_mode(client):
    with patch("api.system_settings.set_setting", return_value=True):
        r = client.post("/automation/mode", data={"mode": "SEMI_AUTO"})
    assert r.status_code == 200
    assert "SEMI_AUTO" in r.text


def test_approvals_page_renders_empty(client):
    with patch("console.approvals.list_pending", return_value=[]):
        r = client.get("/approvals")
    assert r.status_code == 200
    assert "No pending approvals" in r.text


def test_approvals_page_renders_rows(client):
    fake_rows = [{
        "id": 42, "thread_ts": "1714000000.000100", "scan_id": 1,
        "miner_id": "ant-001", "ip": "192.168.188.10",
        "action_type": "RESTART", "reason": "offline > 10min",
        "classification": "AUTO", "confidence": 0.92,
        "status": "PENDING", "created_at": "2026-05-03T10:00:00Z",
        "responded_at": None,
    }]
    with patch("console.approvals.list_pending", return_value=fake_rows), \
         patch("console.approvals.snoozed_until", return_value=None):
        r = client.get("/approvals")
    assert r.status_code == 200
    assert "ant-001" in r.text
    assert "192.168.188.10" in r.text


def test_approval_approve_endpoint(client):
    with patch("console.approvals.approve", return_value=True) as m:
        r = client.post("/approvals/42/approve")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "id": 42, "decision": "APPROVED"}
    m.assert_called_once()


def test_approval_deny_endpoint(client):
    with patch("console.approvals.deny", return_value=True):
        r = client.post("/approvals/42/deny")
    assert r.status_code == 200
    assert r.json()["decision"] == "DENIED"


def test_approval_snooze_endpoint(client):
    with patch("console.approvals.snooze", return_value=True):
        r = client.post("/approvals/42/snooze", data={"minutes": "60"})
    assert r.status_code == 200
    assert r.json()["snoozed_minutes"] == 60


def test_approval_snooze_invalid_minutes_400(client):
    r = client.post("/approvals/42/snooze", data={"minutes": "not-an-int"})
    assert r.status_code == 400


def test_approval_snooze_out_of_range_400(client):
    """approvals.snooze raises ValueError on out-of-range; the route maps
    that to HTTP 400."""
    with patch("console.approvals.snooze", side_effect=ValueError("minutes must be in (0, 1440]")):
        r = client.post("/approvals/42/snooze", data={"minutes": "9999"})
    assert r.status_code == 400


def test_system_state_page_renders(client):
    fake_state = {
        "postgres": {"status": "up", "detail": "localhost:5432"},
        "ollama": {"status": "up", "detail": "http://localhost:11434"},
        "grafana": {"status": "down", "detail": "http://localhost:3000 unreachable"},
        "tailscale": {"status": "unknown", "detail": "best-effort"},
        "last_scan": {"status": "up", "detail": "2026-05-03T10:00:00"},
        "miner_reach": {"status": "up", "detail": "57/58 online"},
    }
    with patch("console.system_state.collect_system_state", return_value=fake_state):
        r = client.get("/system")
    assert r.status_code == 200
    assert "57/58 online" in r.text
    # Two valid phrasings: footer "Grafana remains the visibility surface"
    # OR system page "Grafana stays the visualization surface" — either
    # confirms the doc string is rendering the Grafana-visibility callout.
    assert ("Grafana remains the visibility surface" in r.text
            or "Grafana stays the visualization surface" in r.text)


def test_internal_secret_never_appears_in_html(client):
    """Critical: INTERNAL_API_SECRET must not leak into any rendered HTML.
    We set a sentinel value into the env and then walk every public GET
    page to confirm it's absent."""
    SENTINEL = "do-not-leak-this-very-secret-token-12345"
    with patch.dict(os.environ, {"INTERNAL_API_SECRET": SENTINEL}):
        for path in ("/healthz", "/tasks", "/tasks/htmx",
                     "/automation", "/system"):
            with patch("api.system_settings.get_setting", return_value="FULL_AUTO"), \
                 patch("console.approvals.list_pending", return_value=[]), \
                 patch("console.system_state.collect_system_state", return_value={}):
                r = client.get(path)
            assert SENTINEL not in r.text, f"secret leaked into {path}"


def test_console_binds_only_to_localhost_in_main():
    """Belt-and-braces: import and inspect the entrypoint to confirm it
    pins host=127.0.0.1. Never trust a launcher to enforce binding."""
    import inspect
    from console import main as console_main
    src = inspect.getsource(console_main.main)
    assert 'host="127.0.0.1"' in src, "console.main.main must hard-code host=127.0.0.1"
