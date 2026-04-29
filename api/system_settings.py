"""
api/system_settings.py
Mining Guardian — System Settings (Bucket 9 §10.1/§10.2)

Read/write helpers for the `system_settings` key/value table. Used by:
  - approval_api.py    (Web GUI mode selector + read for /mode endpoint)
  - overnight_automation.py (gate AUTO classification on automation_mode)

The helpers are deliberately tiny — no ORM, no caching layer. Postgres gives
us sub-millisecond reads on a 1-row primary key lookup, and operator mode
changes are infrequent (a few per day at most), so caching is not worth
the staleness risk.

Allowed automation_mode values (string match — application enforces):
  FULL_AUTO  — AUTO-classified actions auto-execute (current behavior)
  SEMI_AUTO  — AUTO-classified actions queue for human approval (treated as HOLD)
  MANUAL     — every action queues for human approval, no auto-execution at all

If the row is missing or unreadable, callers must default to FULL_AUTO so the
system fails open to its historical behavior. Failing closed (defaulting to
MANUAL) would silently halt all automation on a transient DB outage.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import psycopg2
from psycopg2.extras import DictCursor

logger = logging.getLogger("system_settings")

# ── Allowed values ───────────────────────────────────────────────────────────
AUTOMATION_MODE_FULL_AUTO = "FULL_AUTO"
AUTOMATION_MODE_SEMI_AUTO = "SEMI_AUTO"
AUTOMATION_MODE_MANUAL    = "MANUAL"
ALLOWED_AUTOMATION_MODES  = frozenset(
    {AUTOMATION_MODE_FULL_AUTO, AUTOMATION_MODE_SEMI_AUTO, AUTOMATION_MODE_MANUAL}
)

DEFAULT_AUTOMATION_MODE   = AUTOMATION_MODE_FULL_AUTO


def _pg_dsn() -> str:
    """Build Postgres DSN from environment variables. Mirrors approval_api._pg_dsn."""
    host     = os.environ.get("GUARDIAN_PG_HOST",     "localhost")
    port     = os.environ.get("GUARDIAN_PG_PORT",     "5432")
    dbname   = os.environ.get("GUARDIAN_PG_DBNAME",   "mining_guardian")
    user     = os.environ.get("GUARDIAN_PG_USER",     "guardian_app")
    password = os.environ.get("GUARDIAN_PG_PASSWORD", "")
    return f"host={host} port={port} dbname={dbname} user={user} password={password}"


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    """Read a single setting from system_settings. Returns `default` on missing key
    or DB error. Never raises."""
    try:
        conn = psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor)
        try:
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_settings WHERE key = %s", (key,))
            row = cur.fetchone()
            if row is None:
                return default
            return row["value"]
        finally:
            conn.close()
    except Exception as exc:
        logger.error("get_setting(%s) failed: %s — falling back to default %r",
                     key, exc, default)
        return default


def set_setting(key: str, value: str, updated_by: str = "system") -> bool:
    """Upsert a setting. Returns True on success, False on error.

    `updated_by` should be a stable operator identifier — e.g.
    "slack:U12345" or "web_gui:bobby". This is the audit trail for who
    flipped the knob.
    """
    try:
        conn = psycopg2.connect(_pg_dsn())
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO system_settings (key, value, updated_by, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                  SET value      = EXCLUDED.value,
                      updated_by = EXCLUDED.updated_by,
                      updated_at = EXCLUDED.updated_at
                """,
                (key, value, updated_by),
            )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as exc:
        logger.exception("set_setting(%s=%s) failed: %s", key, value, exc)
        return False


# ── automation_mode convenience accessors ─────────────────────────────────────

def get_automation_mode() -> str:
    """Return the current automation mode. Defaults to FULL_AUTO on any failure
    so we never silently halt automation."""
    raw = get_setting("automation_mode", DEFAULT_AUTOMATION_MODE)
    if raw not in ALLOWED_AUTOMATION_MODES:
        logger.warning(
            "automation_mode=%r not in allowed set %s — using default %s",
            raw, sorted(ALLOWED_AUTOMATION_MODES), DEFAULT_AUTOMATION_MODE,
        )
        return DEFAULT_AUTOMATION_MODE
    return raw


def set_automation_mode(mode: str, updated_by: str) -> bool:
    """Set the automation mode. Validates against ALLOWED_AUTOMATION_MODES."""
    if mode not in ALLOWED_AUTOMATION_MODES:
        logger.warning("rejected set_automation_mode(%r) — not in allowed set", mode)
        return False
    return set_setting("automation_mode", mode, updated_by=updated_by)


def get_setting_record(key: str) -> Optional[dict]:
    """Return the full row including updated_at and updated_by for display in
    the Web GUI. Returns None on missing or DB error."""
    try:
        conn = psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT key, value, updated_at, updated_by FROM system_settings "
                "WHERE key = %s",
                (key,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    except Exception as exc:
        logger.error("get_setting_record(%s) failed: %s", key, exc)
        return None
