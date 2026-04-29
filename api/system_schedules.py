"""
api/system_schedules.py — Mining Guardian Bucket 9 §10.7

Read/write helpers for the operator-controlled schedule table introduced in
migration 005. Every in-process daemon (overnight automation, intelligence
report, AMS alert listener, slack listener, catalog auto-refresh) calls
get_schedule(job_key) at the top of each loop iteration, so changes made
through the Web GUI take effect within one cycle without a launchctl
kickstart.

Failure mode is fail-open: if the DB is unreachable or the row is missing,
get_schedule() returns the in-code default for that job_key. A daemon
should never silently halt because of a transient DB error — it should
behave the way it did before §10.7 existed.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any

from api.system_settings import _pg_dsn  # reuse existing DSN helper

logger = logging.getLogger(__name__)

# Schedule type constants
SCHEDULE_TYPE_WINDOW = "window"
SCHEDULE_TYPE_TIME_OF_DAY = "time_of_day"
SCHEDULE_TYPE_INTERVAL = "interval"

ALLOWED_SCHEDULE_TYPES = {
    SCHEDULE_TYPE_WINDOW,
    SCHEDULE_TYPE_TIME_OF_DAY,
    SCHEDULE_TYPE_INTERVAL,
}

# In-code defaults. These mirror the migration seed values exactly.
# If the DB is down OR the row is missing OR the row is corrupt, get_schedule()
# returns one of these so the daemon keeps doing what it always did.
DEFAULT_SCHEDULES: Dict[str, Dict[str, Any]] = {
    "overnight_window": {
        "schedule_type": SCHEDULE_TYPE_WINDOW,
        "start_hour": 0, "start_minute": 0,
        "end_hour": 24, "end_minute": 0,
        "interval_seconds": None,
        "days_of_week": "0,1,2,3,4,5,6",
        "enabled": True,
    },
    "ams_alert_poll": {
        "schedule_type": SCHEDULE_TYPE_INTERVAL,
        "start_hour": None, "start_minute": None,
        "end_hour": None, "end_minute": None,
        "interval_seconds": 15,
        "days_of_week": "0,1,2,3,4,5,6",
        "enabled": True,
    },
    "slack_listener_poll": {
        "schedule_type": SCHEDULE_TYPE_INTERVAL,
        "start_hour": None, "start_minute": None,
        "end_hour": None, "end_minute": None,
        "interval_seconds": 15,
        "days_of_week": "0,1,2,3,4,5,6",
        "enabled": True,
    },
    "catalog_auto_refresh": {
        "schedule_type": SCHEDULE_TYPE_INTERVAL,
        "start_hour": None, "start_minute": None,
        "end_hour": None, "end_minute": None,
        "interval_seconds": 300,
        "days_of_week": "0,1,2,3,4,5,6",
        "enabled": True,
    },
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_dow(s: str) -> set:
    """Parse '0,1,2,3,4,5,6' → {0,1,2,3,4,5,6}. Robust to whitespace, empties."""
    if not s:
        return {0, 1, 2, 3, 4, 5, 6}
    out = set()
    for token in s.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            n = int(token)
            if 0 <= n <= 6:
                out.add(n)
        except ValueError:
            continue
    return out or {0, 1, 2, 3, 4, 5, 6}


def _today_dow() -> int:
    """Return today's day-of-week using Python convention: Monday=0..Sunday=6."""
    return datetime.now().weekday()


# ── DB layer ─────────────────────────────────────────────────────────────────

def _connect():
    import psycopg2
    return psycopg2.connect(_pg_dsn())


def get_schedule(job_key: str) -> Dict[str, Any]:
    """Return the schedule row for job_key as a dict, or the in-code default
    if the DB is unreachable or the row is missing.

    Returned dict always has the keys: enabled, schedule_type, start_hour,
    start_minute, end_hour, end_minute, interval_seconds, days_of_week.
    """
    default = DEFAULT_SCHEDULES.get(job_key)
    if default is None:
        # Unknown job_key. Caller asked for something we don't know about;
        # return a sensible "always-on every-15-seconds" fallback rather than
        # raising, so daemons don't crash mid-loop.
        return {
            "enabled": True,
            "schedule_type": SCHEDULE_TYPE_INTERVAL,
            "start_hour": None, "start_minute": None,
            "end_hour": None, "end_minute": None,
            "interval_seconds": 15,
            "days_of_week": "0,1,2,3,4,5,6",
        }

    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT enabled, schedule_type, start_hour, start_minute,
                           end_hour, end_minute, interval_seconds, days_of_week
                    FROM system_schedules WHERE job_key = %s
                    """,
                    (job_key,),
                )
                row = cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.warning("get_schedule(%s) DB error, using default: %s", job_key, e)
        return dict(default)

    if row is None:
        return dict(default)

    return {
        "enabled": bool(row[0]),
        "schedule_type": row[1],
        "start_hour": row[2],
        "start_minute": row[3],
        "end_hour": row[4],
        "end_minute": row[5],
        "interval_seconds": row[6],
        "days_of_week": row[7] or "0,1,2,3,4,5,6",
    }


def list_schedules() -> list:
    """Return all schedules joined with their default category/description.
    Used by GET /schedules to render the GUI tab.
    """
    rows_out = []
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT job_key, enabled, schedule_type, start_hour, start_minute,
                           end_hour, end_minute, interval_seconds, days_of_week,
                           description, category, updated_at, updated_by
                    FROM system_schedules
                    ORDER BY category, job_key
                    """,
                )
                for row in cur.fetchall():
                    rows_out.append({
                        "job_key": row[0],
                        "enabled": bool(row[1]),
                        "schedule_type": row[2],
                        "start_hour": row[3],
                        "start_minute": row[4],
                        "end_hour": row[5],
                        "end_minute": row[6],
                        "interval_seconds": row[7],
                        "days_of_week": row[8] or "0,1,2,3,4,5,6",
                        "description": row[9],
                        "category": row[10],
                        "updated_at": row[11].isoformat() if row[11] else None,
                        "updated_by": row[12],
                    })
        finally:
            conn.close()
    except Exception as e:
        logger.warning("list_schedules() DB error, returning defaults: %s", e)
        for key, val in DEFAULT_SCHEDULES.items():
            rows_out.append({
                "job_key": key,
                "enabled": val["enabled"],
                "schedule_type": val["schedule_type"],
                "start_hour": val["start_hour"],
                "start_minute": val["start_minute"],
                "end_hour": val["end_hour"],
                "end_minute": val["end_minute"],
                "interval_seconds": val["interval_seconds"],
                "days_of_week": val["days_of_week"],
                "description": "(default — DB unavailable)",
                "category": None,
                "updated_at": None,
                "updated_by": None,
            })
    return rows_out


def update_schedule(job_key: str, payload: Dict[str, Any], updated_by: str) -> Dict[str, Any]:
    """Validate then UPSERT a schedule row. Returns the resulting row.

    Raises ValueError on validation failure (FastAPI converts to 400).
    """
    if job_key not in DEFAULT_SCHEDULES:
        raise ValueError(f"unknown job_key: {job_key}")

    schedule_type = payload.get("schedule_type") or DEFAULT_SCHEDULES[job_key]["schedule_type"]
    if schedule_type not in ALLOWED_SCHEDULE_TYPES:
        raise ValueError(f"invalid schedule_type: {schedule_type}")

    enabled = bool(payload.get("enabled", True))
    start_hour = payload.get("start_hour")
    start_minute = payload.get("start_minute")
    end_hour = payload.get("end_hour")
    end_minute = payload.get("end_minute")
    interval_seconds = payload.get("interval_seconds")
    days_of_week = payload.get("days_of_week", "0,1,2,3,4,5,6")

    # Per-type validation
    def _check_hour(name, val, lo=0, hi=23):
        if val is None:
            raise ValueError(f"{name} required for schedule_type={schedule_type}")
        if not isinstance(val, int) or val < lo or val > hi:
            raise ValueError(f"{name} must be int between {lo} and {hi}")

    def _check_minute(name, val):
        if val is None:
            raise ValueError(f"{name} required for schedule_type={schedule_type}")
        if not isinstance(val, int) or val < 0 or val > 59:
            raise ValueError(f"{name} must be int between 0 and 59")

    if schedule_type == SCHEDULE_TYPE_WINDOW:
        _check_hour("start_hour", start_hour)
        _check_minute("start_minute", start_minute)
        _check_hour("end_hour", end_hour, lo=0, hi=24)  # 24 = end-of-day sentinel
        # end_minute may be None when end_hour=24
        if end_hour != 24:
            _check_minute("end_minute", end_minute)
        else:
            end_minute = end_minute if end_minute is not None else 0
        interval_seconds = None
    elif schedule_type == SCHEDULE_TYPE_TIME_OF_DAY:
        _check_hour("start_hour", start_hour)
        _check_minute("start_minute", start_minute)
        end_hour = end_minute = interval_seconds = None
    elif schedule_type == SCHEDULE_TYPE_INTERVAL:
        if not isinstance(interval_seconds, int) or interval_seconds < 5 or interval_seconds > 86400:
            raise ValueError("interval_seconds must be int between 5 and 86400")
        start_hour = start_minute = end_hour = end_minute = None

    # days_of_week sanity
    parsed_dow = _parse_dow(days_of_week)
    days_of_week_norm = ",".join(str(d) for d in sorted(parsed_dow))

    conn = _connect()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO system_schedules
                        (job_key, enabled, schedule_type, start_hour, start_minute,
                         end_hour, end_minute, interval_seconds, days_of_week,
                         updated_at, updated_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                    ON CONFLICT (job_key) DO UPDATE SET
                        enabled = EXCLUDED.enabled,
                        schedule_type = EXCLUDED.schedule_type,
                        start_hour = EXCLUDED.start_hour,
                        start_minute = EXCLUDED.start_minute,
                        end_hour = EXCLUDED.end_hour,
                        end_minute = EXCLUDED.end_minute,
                        interval_seconds = EXCLUDED.interval_seconds,
                        days_of_week = EXCLUDED.days_of_week,
                        updated_at = NOW(),
                        updated_by = EXCLUDED.updated_by
                    """,
                    (job_key, enabled, schedule_type, start_hour, start_minute,
                     end_hour, end_minute, interval_seconds, days_of_week_norm,
                     updated_by),
                )
    finally:
        conn.close()

    logger.info("update_schedule(%s) by %s: type=%s enabled=%s",
                job_key, updated_by, schedule_type, enabled)
    return get_schedule(job_key)


# ── runtime gating helpers ───────────────────────────────────────────────────

def is_in_window(job_key: str, now: Optional[datetime] = None) -> bool:
    """For schedule_type=window: True if `now` is inside the configured window
    AND today is an enabled day-of-week AND the job is enabled. False otherwise.

    Conservative on bad data: returns True when schedule is disabled? NO —
    disabled means "don't run", so returns False when enabled=False.

    For backward compatibility, callers should fall back to their pre-§10.7
    constant if the schedule is disabled and they want to keep running.
    Most callers should respect `enabled=False` literally.
    """
    sched = get_schedule(job_key)
    if not sched["enabled"]:
        return False
    if sched["schedule_type"] != SCHEDULE_TYPE_WINDOW:
        # Caller used the wrong helper; be permissive rather than crash
        return True

    now = now or datetime.now()
    if now.weekday() not in _parse_dow(sched["days_of_week"]):
        return False

    sh, sm = sched["start_hour"] or 0, sched["start_minute"] or 0
    eh, em = sched["end_hour"], sched["end_minute"] or 0
    if eh is None:
        return True
    if eh >= 24:
        # end-of-day sentinel — full-day window
        return True

    cur_minutes = now.hour * 60 + now.minute
    start_min = sh * 60 + sm
    end_min = eh * 60 + em

    if start_min <= end_min:
        return start_min <= cur_minutes < end_min
    else:
        # spans midnight (e.g., 22:00 → 06:00)
        return cur_minutes >= start_min or cur_minutes < end_min


def should_run_today(job_key: str, now: Optional[datetime] = None) -> bool:
    """For schedule_type=time_of_day: True if today is an enabled day."""
    sched = get_schedule(job_key)
    if not sched["enabled"]:
        return False
    now = now or datetime.now()
    return now.weekday() in _parse_dow(sched["days_of_week"])


def get_interval_seconds(job_key: str) -> int:
    """For schedule_type=interval: return the configured poll interval, or
    the default if the schedule is disabled or misconfigured.

    Disabled interval jobs return their default (i.e., disabling an interval
    job has no runtime effect — operator should toggle the daemon itself
    via launchctl). Documented behavior; tested.
    """
    sched = get_schedule(job_key)
    val = sched.get("interval_seconds")
    if val is None or val < 5:
        return DEFAULT_SCHEDULES.get(job_key, {}).get("interval_seconds", 60)
    return int(val)
