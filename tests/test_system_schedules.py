"""
tests/test_system_schedules.py — Bucket 9 §10.7

Unit tests for the operator-controlled schedule layer. All DB calls are
mocked — these tests must never touch a live Postgres instance.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# ── Constants & defaults ─────────────────────────────────────────────────────

def test_allowed_schedule_types():
    from api.system_schedules import (
        ALLOWED_SCHEDULE_TYPES,
        SCHEDULE_TYPE_WINDOW,
        SCHEDULE_TYPE_TIME_OF_DAY,
        SCHEDULE_TYPE_INTERVAL,
    )
    assert ALLOWED_SCHEDULE_TYPES == {
        SCHEDULE_TYPE_WINDOW,
        SCHEDULE_TYPE_TIME_OF_DAY,
        SCHEDULE_TYPE_INTERVAL,
    }


def test_default_schedules_present():
    """All four shipped jobs must be in DEFAULT_SCHEDULES."""
    from api.system_schedules import DEFAULT_SCHEDULES
    expected_keys = {
        "overnight_window",
        "ams_alert_poll",
        "slack_listener_poll",
        "catalog_auto_refresh",
    }
    assert expected_keys.issubset(set(DEFAULT_SCHEDULES.keys()))


# ── _parse_dow ───────────────────────────────────────────────────────────────

def test_parse_dow_full_week():
    from api.system_schedules import _parse_dow
    assert _parse_dow("0,1,2,3,4,5,6") == {0, 1, 2, 3, 4, 5, 6}


def test_parse_dow_subset():
    from api.system_schedules import _parse_dow
    assert _parse_dow("0,2,4") == {0, 2, 4}


def test_parse_dow_handles_empty():
    from api.system_schedules import _parse_dow
    # Empty string returns full week (fail-open default)
    assert _parse_dow("") == {0, 1, 2, 3, 4, 5, 6}


def test_parse_dow_strips_whitespace():
    from api.system_schedules import _parse_dow
    assert _parse_dow(" 0 , 1 , 2 ") == {0, 1, 2}


def test_parse_dow_rejects_out_of_range():
    from api.system_schedules import _parse_dow
    # 7 is out of range; only 0,1 survive
    assert _parse_dow("0,1,7,99") == {0, 1}


def test_parse_dow_rejects_garbage():
    from api.system_schedules import _parse_dow
    # All garbage → falls back to full week
    assert _parse_dow("garbage,xyz") == {0, 1, 2, 3, 4, 5, 6}


# ── get_schedule fail-open behaviour ─────────────────────────────────────────

def test_get_schedule_returns_default_on_db_error():
    """If DB throws, we return the in-code default, never raise."""
    from api import system_schedules
    with patch.object(system_schedules, "_connect", side_effect=RuntimeError("db down")):
        sched = system_schedules.get_schedule("overnight_window")
    assert sched["schedule_type"] == "window"
    assert sched["start_hour"] == 0
    assert sched["end_hour"] == 24
    assert sched["enabled"] is True


def test_get_schedule_unknown_job_key_returns_safe_fallback():
    """Asking for a job we don't know about returns a permissive default
    rather than crashing the daemon."""
    from api.system_schedules import get_schedule
    sched = get_schedule("does_not_exist")
    assert sched["enabled"] is True
    assert sched["schedule_type"] == "interval"
    assert sched["interval_seconds"] >= 5


def test_get_schedule_returns_db_row_when_present():
    """When DB returns a row, we honour it."""
    from api import system_schedules

    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_cur.fetchone.return_value = (
        True, "window", 22, 30, 6, 0, None, "0,1,2,3,4,5,6"
    )

    with patch.object(system_schedules, "_connect", return_value=fake_conn):
        sched = system_schedules.get_schedule("overnight_window")

    assert sched["enabled"] is True
    assert sched["schedule_type"] == "window"
    assert sched["start_hour"] == 22
    assert sched["start_minute"] == 30
    assert sched["end_hour"] == 6


# ── is_in_window ─────────────────────────────────────────────────────────────

def test_is_in_window_full_day():
    """end_hour=24 means always-active."""
    from api import system_schedules
    fake_sched = {
        "enabled": True, "schedule_type": "window",
        "start_hour": 0, "start_minute": 0,
        "end_hour": 24, "end_minute": 0,
        "interval_seconds": None, "days_of_week": "0,1,2,3,4,5,6",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        for h in range(24):
            assert system_schedules.is_in_window("x", datetime(2026, 1, 5, h, 0))


def test_is_in_window_disabled_returns_false():
    """enabled=False short-circuits to False regardless of time."""
    from api import system_schedules
    fake_sched = {
        "enabled": False, "schedule_type": "window",
        "start_hour": 0, "start_minute": 0,
        "end_hour": 24, "end_minute": 0,
        "interval_seconds": None, "days_of_week": "0,1,2,3,4,5,6",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 12, 0)) is False


def test_is_in_window_spans_midnight():
    """22:00 → 06:00 window: hours 22, 0, 5 inside; 8, 21 outside."""
    from api import system_schedules
    fake_sched = {
        "enabled": True, "schedule_type": "window",
        "start_hour": 22, "start_minute": 0,
        "end_hour": 6, "end_minute": 0,
        "interval_seconds": None, "days_of_week": "0,1,2,3,4,5,6",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        # 22:30 → in
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 22, 30))
        # 00:30 → in
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 0, 30))
        # 05:59 → in
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 5, 59))
        # 06:00 → out (exclusive)
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 6, 0)) is False
        # 12:00 → out
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 12, 0)) is False


def test_is_in_window_respects_day_of_week():
    """Window with days='0,1,2' (Mon/Tue/Wed) skips Thursday."""
    from api import system_schedules
    fake_sched = {
        "enabled": True, "schedule_type": "window",
        "start_hour": 0, "start_minute": 0,
        "end_hour": 24, "end_minute": 0,
        "interval_seconds": None, "days_of_week": "0,1,2",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        # Monday 2026-01-05 → in
        assert system_schedules.is_in_window("x", datetime(2026, 1, 5, 12, 0))
        # Thursday 2026-01-08 → out
        assert system_schedules.is_in_window("x", datetime(2026, 1, 8, 12, 0)) is False


# ── get_interval_seconds ─────────────────────────────────────────────────────

def test_get_interval_seconds_returns_configured_value():
    from api import system_schedules
    fake_sched = {
        "enabled": True, "schedule_type": "interval",
        "start_hour": None, "start_minute": None,
        "end_hour": None, "end_minute": None,
        "interval_seconds": 42, "days_of_week": "0,1,2,3,4,5,6",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        assert system_schedules.get_interval_seconds("ams_alert_poll") == 42


def test_get_interval_seconds_falls_back_when_too_low():
    """interval < 5 is rejected; we return the in-code default."""
    from api import system_schedules
    fake_sched = {
        "enabled": True, "schedule_type": "interval",
        "start_hour": None, "start_minute": None,
        "end_hour": None, "end_minute": None,
        "interval_seconds": 1, "days_of_week": "0,1,2,3,4,5,6",
    }
    with patch.object(system_schedules, "get_schedule", return_value=fake_sched):
        assert system_schedules.get_interval_seconds("ams_alert_poll") == 15


# ── update_schedule validation ───────────────────────────────────────────────

def test_update_schedule_rejects_unknown_job_key():
    from api.system_schedules import update_schedule
    with pytest.raises(ValueError, match="unknown job_key"):
        update_schedule("not_a_real_job", {"schedule_type": "interval", "interval_seconds": 60}, "tester")


def test_update_schedule_rejects_invalid_type():
    from api.system_schedules import update_schedule
    with pytest.raises(ValueError, match="invalid schedule_type"):
        update_schedule("overnight_window", {"schedule_type": "WEEKLY"}, "tester")


def test_update_schedule_window_requires_hours():
    from api.system_schedules import update_schedule
    with pytest.raises(ValueError, match="start_hour"):
        update_schedule("overnight_window", {"schedule_type": "window"}, "tester")


def test_update_schedule_interval_requires_seconds():
    from api.system_schedules import update_schedule
    with pytest.raises(ValueError, match="interval_seconds"):
        update_schedule("ams_alert_poll", {"schedule_type": "interval"}, "tester")


def test_update_schedule_interval_rejects_too_high():
    from api.system_schedules import update_schedule
    with pytest.raises(ValueError, match="interval_seconds"):
        update_schedule("ams_alert_poll", {"schedule_type": "interval", "interval_seconds": 999999}, "tester")


def test_update_schedule_persists_via_upsert():
    """Happy path: valid window payload → DB upsert + return."""
    from api import system_schedules

    fake_conn = MagicMock()
    fake_cur = MagicMock()
    fake_conn.cursor.return_value.__enter__.return_value = fake_cur
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False

    # First call (during update_schedule's UPSERT): returns nothing meaningful.
    # Second call (inside get_schedule, called by update_schedule on its way out): returns the row we just wrote.
    fake_cur.fetchone.return_value = (True, "window", 22, 0, 6, 0, None, "0,1,2,3,4,5,6")

    with patch.object(system_schedules, "_connect", return_value=fake_conn):
        result = system_schedules.update_schedule(
            "overnight_window",
            {
                "schedule_type": "window",
                "enabled": True,
                "start_hour": 22, "start_minute": 0,
                "end_hour": 6, "end_minute": 0,
                "days_of_week": "0,1,2,3,4,5,6",
            },
            "tester",
        )
    assert result["schedule_type"] == "window"
    assert result["start_hour"] == 22
    assert result["end_hour"] == 6
