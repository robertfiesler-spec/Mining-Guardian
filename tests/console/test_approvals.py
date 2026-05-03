"""
tests/console/test_approvals.py — D-19 console (P-006)

Unit tests for console/approvals.py. DB is mocked; tests do not require
a live Postgres.
"""

from unittest.mock import MagicMock, patch

import pytest

from console import approvals


def test_snooze_rejects_zero_minutes():
    with pytest.raises(ValueError):
        approvals.snooze(1, minutes=0)


def test_snooze_rejects_huge_minutes():
    with pytest.raises(ValueError):
        approvals.snooze(1, minutes=10_000)


def test_set_status_rejects_invalid_decision():
    with pytest.raises(ValueError):
        approvals._set_status(1, "MAYBE", operator="test")  # noqa: SLF001


def test_list_pending_returns_empty_on_db_error():
    with patch("console.approvals._connect", side_effect=Exception("no db")):
        result = approvals.list_pending()
    assert result == []


def test_list_pending_returns_rows_when_db_works():
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = [
        {"id": 1, "miner_id": "m-1", "ip": "192.168.1.1",
         "action_type": "RESTART", "reason": "test",
         "classification": "AUTO", "confidence": 0.9,
         "status": "PENDING", "thread_ts": "1.1", "scan_id": 1,
         "created_at": "2026-05-03T00:00:00Z", "responded_at": None},
    ]
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    with patch("console.approvals._connect", return_value=fake_conn):
        rows = approvals.list_pending()
    assert len(rows) == 1
    assert rows[0]["miner_id"] == "m-1"


def test_approve_calls_set_status_with_approved():
    with patch("console.approvals._set_status", return_value=True) as m:
        ok = approvals.approve(7, operator="test")
    assert ok is True
    m.assert_called_once_with(7, "APPROVED", "test")


def test_deny_calls_set_status_with_denied():
    with patch("console.approvals._set_status", return_value=True) as m:
        ok = approvals.deny(8, operator="test")
    assert ok is True
    m.assert_called_once_with(8, "DENIED", "test")


def test_snooze_writes_to_system_settings():
    with patch("api.system_settings.set_setting", return_value=True) as m:
        ok = approvals.snooze(11, minutes=15, operator="op")
    assert ok is True
    args, kwargs = m.call_args
    assert args[0].startswith("console_snooze:11")
    assert "op" in kwargs.get("updated_by", "")


def test_snoozed_until_returns_none_on_failure():
    with patch("api.system_settings.get_setting", side_effect=Exception("x")):
        assert approvals.snoozed_until(1) is None
