"""
tests/console/test_launchd_controls.py — D-19 console (P-006)

Unit tests for the launchctl wrapper. Mocked — never touches host launchd.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from console import launchd_controls as lc


@pytest.fixture(autouse=True)
def _clear_mock_env(monkeypatch):
    """Default to non-mock mode for these tests; opt in per-test."""
    monkeypatch.delenv("MG_CONSOLE_LAUNCHCTL", raising=False)


def test_status_in_process_returns_none_loaded():
    out = lc.status(None)
    assert out["loaded"] is None
    assert out["running"] is None


def test_mock_mode_returns_running():
    with patch.dict(os.environ, {"MG_CONSOLE_LAUNCHCTL": "mock"}):
        out = lc.status("com.miningguardian.scanner")
    assert out["loaded"] is True
    assert out["running"] is True
    assert out["pid"] == 1234


def test_status_handles_missing_launchctl():
    """If launchctl isn't installed (e.g., test runner), every status
    probe must fall back gracefully — never raise."""
    with patch("subprocess.run", side_effect=FileNotFoundError("launchctl not found")):
        out = lc.status("com.miningguardian.scanner")
    assert out["loaded"] is None
    assert out["running"] is None


def test_status_parses_print_output():
    raw_stdout = """system/com.miningguardian.scanner = {
        active count = 1
        pid = 4321
        last exit code = 0
}"""
    fake_proc = MagicMock(returncode=0, stdout=raw_stdout, stderr="")
    with patch("subprocess.run", return_value=fake_proc):
        out = lc.status("com.miningguardian.scanner")
    assert out["loaded"] is True
    assert out["pid"] == 4321
    assert out["last_exit_code"] == 0


def test_status_when_launchctl_returns_nonzero_means_not_loaded():
    fake_proc = MagicMock(returncode=1, stdout="", stderr="No such service")
    with patch("subprocess.run", return_value=fake_proc):
        out = lc.status("com.miningguardian.bogus")
    assert out["loaded"] is False
    assert out["running"] is False


def test_pause_in_mock_mode_succeeds():
    with patch.dict(os.environ, {"MG_CONSOLE_LAUNCHCTL": "mock"}):
        assert lc.pause("com.miningguardian.scanner") is True


def test_resume_rejects_relative_plist_path():
    with patch.dict(os.environ, {"MG_CONSOLE_LAUNCHCTL": ""}, clear=False):
        # Relative paths refused; nothing is shelled out.
        assert lc.resume("com.miningguardian.scanner", "relative.plist") is False


def test_resume_in_mock_mode_succeeds():
    with patch.dict(os.environ, {"MG_CONSOLE_LAUNCHCTL": "mock"}):
        assert lc.resume("com.miningguardian.scanner", "/Library/LaunchDaemons/x.plist") is True


def test_pause_handles_subprocess_error():
    with patch("subprocess.run", side_effect=OSError("nope")):
        assert lc.pause("com.miningguardian.scanner") is False
