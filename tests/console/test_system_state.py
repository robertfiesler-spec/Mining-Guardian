"""
tests/console/test_system_state.py — D-19 console (P-006)

Unit tests for console/system_state.py. Probes are mocked at the socket
and HTTP layers so tests are deterministic.
"""

from unittest.mock import MagicMock, patch

import pytest

from console import system_state as ss


def test_tcp_probe_ok():
    with patch("socket.create_connection", return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock())):
        assert ss._tcp_probe("h", 1) is True  # noqa: SLF001


def test_tcp_probe_fail():
    with patch("socket.create_connection", side_effect=OSError("nope")):
        assert ss._tcp_probe("h", 1) is False  # noqa: SLF001


def test_http_probe_ok():
    fake_resp = MagicMock(status=200)
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock()
    with patch("console.system_state.urlopen", return_value=fake_resp):
        assert ss._http_probe("http://localhost:80") == 200  # noqa: SLF001


def test_http_probe_fail_returns_none():
    with patch("console.system_state.urlopen", side_effect=OSError("nope")):
        assert ss._http_probe("http://localhost:80") is None  # noqa: SLF001


def test_probe_postgres_up():
    with patch("console.system_state._tcp_probe", return_value=True):
        out = ss.probe_postgres()
    assert out["status"] == "up"


def test_probe_postgres_down():
    with patch("console.system_state._tcp_probe", return_value=False):
        out = ss.probe_postgres()
    assert out["status"] == "down"


def test_probe_ollama_up_on_200():
    with patch("console.system_state._http_probe", return_value=200):
        out = ss.probe_ollama()
    assert out["status"] == "up"


def test_probe_ollama_degraded_on_500():
    with patch("console.system_state._http_probe", return_value=500):
        out = ss.probe_ollama()
    assert out["status"] == "degraded"


def test_probe_grafana_down():
    with patch("console.system_state._http_probe", return_value=None):
        out = ss.probe_grafana()
    assert out["status"] == "down"


def test_probe_tailscale_unknown_when_unreachable():
    with patch("console.system_state._tcp_probe", return_value=False):
        out = ss.probe_tailscale()
    # Tailscale probe is best-effort — treat as 'unknown' rather than 'down'.
    assert out["status"] == "unknown"


def test_probe_last_scan_handles_db_error():
    """psycopg2 is imported lazily inside probe_last_scan; force the
    import itself to raise so we hit the except branch deterministically."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg2":
            raise ImportError("forced for test")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        out = ss.probe_last_scan()
    assert out["status"] == "unknown"


def test_collect_system_state_returns_all_keys():
    """Even with every probe failing, the collector must still return
    the full key set so the template never KeyErrors."""
    with patch("console.system_state.probe_postgres",
               return_value={"status": "down", "detail": "x"}), \
         patch("console.system_state.probe_ollama",
               return_value={"status": "down", "detail": "x"}), \
         patch("console.system_state.probe_grafana",
               return_value={"status": "down", "detail": "x"}), \
         patch("console.system_state.probe_tailscale",
               return_value={"status": "unknown", "detail": "x"}), \
         patch("console.system_state.probe_last_scan",
               return_value={"status": "unknown", "detail": "x"}), \
         patch("console.system_state.probe_miner_reachability",
               return_value={"status": "unknown", "detail": "x"}):
        out = ss.collect_system_state()
    assert set(out.keys()) == {
        "postgres", "ollama", "grafana", "tailscale",
        "last_scan", "miner_reach",
    }
