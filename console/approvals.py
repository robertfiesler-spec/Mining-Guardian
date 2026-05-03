"""
console/approvals.py — D-19 approval queue (server-side only)

Reads PENDING rows from the existing `pending_approvals` table (Postgres,
operational DB) and exposes Approve / Deny / Snooze. All DB writes happen
in this process; we do not call api/approval_api.py over HTTP and we do
not put INTERNAL_API_SECRET in any HTML response.

Why we update pending_approvals directly rather than calling the
approval_api HTTP surface:

  1. The console runs as root in the same OS install as approval_api;
     direct DB access is the smaller blast radius (no extra HTTP hop, no
     shared-secret in the browser session).
  2. INTERNAL_API_SECRET stays out of the browser. The console never
     ships it to the client; even the snooze/approve POSTs that the
     browser issues only carry an opaque approval id.
  3. Slack approval flow already writes to pending_approvals directly
     (see core/overnight_automation.py). We mirror that pattern.

If a future change moves the approval execution side-effects into a
single shared library, we'll switch to the library. For v1 we deliberately
do NOT trigger remediation (restart / PDU cycle) from the console — the
v1 console is queue-management only. Remediation execution stays with
the existing approval_api Slack flow. This is documented in
docs/CONSOLE_OPERATIONS_GUIDE.md.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("console.approvals")


def _connect():
    """Open a Postgres connection using the same DSN helper as the rest
    of the codebase. Imports are lazy so module import works even on a
    host without psycopg2 installed (test environments)."""
    import psycopg2  # type: ignore
    from psycopg2.extras import DictCursor  # type: ignore
    from api.system_settings import _pg_dsn
    return psycopg2.connect(_pg_dsn(), cursor_factory=DictCursor)


VALID_DECISIONS = frozenset({"APPROVED", "DENIED", "SNOOZED"})

# Snooze pushes the row's status back to PENDING after the snooze window.
# We don't have a dedicated SNOOZED status column, so we use a side-table
# approach: write a row to system_settings under key
# "console_snooze:<approval_id>" with the wake time.
_SNOOZE_KEY_PREFIX = "console_snooze:"


def list_pending(limit: int = 200) -> List[Dict[str, Any]]:
    """Return PENDING approvals, newest first. Best-effort: DB errors are
    logged and an empty list is returned rather than raised."""
    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, thread_ts, scan_id, miner_id, ip, action_type,
                       reason, classification, confidence, status,
                       created_at, responded_at
                FROM pending_approvals
                WHERE status = 'PENDING'
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("list_pending failed: %s", exc)
        return []


def _set_status(approval_id: int, decision: str, operator: str) -> bool:
    """Internal: flip a pending_approvals row to APPROVED or DENIED.
    Returns True on success.

    Note: we do NOT execute remediation from the console in v1 (see
    module docstring). This only updates the queue row. The Slack
    approval flow remains the side-effect driver until a unified
    execution library lands.
    """
    if decision not in {"APPROVED", "DENIED"}:
        raise ValueError(f"unsupported decision: {decision!r}")

    try:
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE pending_approvals
                   SET status = %s,
                       responded_at = %s,
                       responded_by = %s
                 WHERE id = %s AND status = 'PENDING'
                """,
                (decision, datetime.now(timezone.utc), operator, approval_id),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("_set_status(%s, %s) failed: %s", approval_id, decision, exc)
        return False


def approve(approval_id: int, operator: str = "console") -> bool:
    return _set_status(approval_id, "APPROVED", operator)


def deny(approval_id: int, operator: str = "console") -> bool:
    return _set_status(approval_id, "DENIED", operator)


def snooze(approval_id: int, minutes: int = 30, operator: str = "console") -> bool:
    """Push wake time forward in system_settings. The row stays PENDING.
    A future console release (or a small cron) wakes the row up by clearing
    the snooze key. v1 just records the snooze for visibility — it does
    not hide the row from list_pending. Returns True on success."""
    if minutes <= 0 or minutes > 24 * 60:
        raise ValueError("minutes must be in (0, 1440]")
    try:
        from api.system_settings import set_setting
        wake = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return set_setting(
            f"{_SNOOZE_KEY_PREFIX}{approval_id}",
            wake.isoformat(),
            updated_by=f"console:{operator}",
        )
    except Exception as exc:
        logger.warning("snooze(%s, %s) failed: %s", approval_id, minutes, exc)
        return False


def snoozed_until(approval_id: int) -> Optional[str]:
    """Return ISO timestamp string if snoozed, else None."""
    try:
        from api.system_settings import get_setting
        return get_setting(f"{_SNOOZE_KEY_PREFIX}{approval_id}")
    except Exception:
        return None
