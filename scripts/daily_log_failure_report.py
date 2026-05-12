#!/usr/bin/env python3
"""
daily_log_failure_report.py
Mining Guardian — Daily Log Failure Report (4:15pm)

Lists all miners that DID NOT get fresh logs today so the operator
can investigate before leaving work. Runs at 4:15pm daily.
"""

import os
import sys
import json
import psycopg2
from psycopg2.extras import DictCursor
import logging
from pathlib import Path
from datetime import datetime
from slack_sdk import WebClient

from core.db_targets import operational_target

_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def _pg_dsn() -> str:
    """Build operational Postgres DSN via core.db_targets.

    Delegates to the resolver (W14a, 2026-05-12) — the previous direct
    `os.environ.get(...)` reads of the connect params bypassed
    `core.db_targets` and would silently misroute to the operational
    instance once W14 splits catalog onto port 5433. This script reads
    only operational tables (miner_readings, miner_logs, scans), so
    `operational_target()` is correct here.

    Also fixes a latent bug from the pre-W14a defaults: this function
    used to hardcode a user default of `"guardian_app"`, the wrong
    role name. The current resolver defaults to `"mg"`, matching the
    role the installer's `step_reconcile_postgres_password` provisions.
    """
    return operational_target().dsn()


class _PgConnWrapper:
    """Thin wrapper over psycopg2 Connection with SQLite-style execute shortcut."""

    def __init__(self, dsn: str):
        self._conn = psycopg2.connect(dsn, cursor_factory=DictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(sql, seq_of_params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()
        return False
CONFIG_PATH = _ROOT / "config.json"


def get_slack_client():
    """Load config and return Slack client."""
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    token = cfg.get("slack_bot_token") or os.environ.get("SLACK_BOT_TOKEN")
    return WebClient(token=token)


def get_miners_without_logs():
    """Get all miners that did NOT get logs in the last 12 hours."""
    conn = _PgConnWrapper(_pg_dsn())
    rows = conn.execute("""
        SELECT DISTINCT mr.miner_id, mr.ip, mr.model, mr.status
        FROM miner_readings mr
        WHERE mr.scanned_at > (NOW() - INTERVAL '1 day')
        AND mr.id = (SELECT MAX(id) FROM miner_readings WHERE miner_id = mr.miner_id)
        AND mr.miner_id NOT IN (
            SELECT DISTINCT miner_id FROM miner_logs 
            WHERE collected_at > (NOW() - INTERVAL '12 hours')
        )
        ORDER BY mr.ip
    """).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def get_fleet_stats():
    """Get fleet size and log count."""
    conn = _PgConnWrapper(_pg_dsn())
    
    fleet = conn.execute(
        "SELECT COUNT(DISTINCT miner_id) FROM miner_readings WHERE scanned_at > (NOW() - INTERVAL '1 day')"
    ).fetchone()[0]
    
    with_logs = conn.execute(
        "SELECT COUNT(DISTINCT miner_id) FROM miner_logs WHERE collected_at > (NOW() - INTERVAL '12 hours')"
    ).fetchone()[0]
    
    conn.close()
    return fleet, with_logs


def main():
    logger.info("=== DAILY LOG FAILURE REPORT ===")
    
    slack = get_slack_client()
    channel = "C0ASH2CPHBJ"  # #mg-logs
    
    missing = get_miners_without_logs()
    fleet, with_logs = get_fleet_stats()
    
    if not missing:
        message = f":white_check_mark: *Daily Log Report — All {fleet} miners got logs!*\n_No investigation needed._"
        slack.chat_postMessage(channel=channel, text=message)
        logger.info("All miners have logs!")
        return
    
    # Build the failure report
    lines = [
        f":warning: *Daily Log Failures — {len(missing)} miners need investigation*",
        f"_Coverage: {with_logs}/{fleet} ({100*with_logs//fleet}%) — {datetime.now().strftime('%Y-%m-%d %I:%M %p')}_",
        "",
    ]
    
    # Group by online vs offline
    online_miners = [m for m in missing if m.get('status') == 'ONLINE']
    offline_miners = [m for m in missing if m.get('status') != 'ONLINE']
    
    if online_miners:
        lines.append(f"*Online but no logs ({len(online_miners)}):*")
        for m in online_miners:
            ip = m['ip']
            model = m['model'][:25] if m['model'] else 'Unknown'
            lines.append(f"  • `{ip}` — {model}")
        lines.append("")
    
    if offline_miners:
        lines.append(f"*Offline ({len(offline_miners)}):*")
        for m in offline_miners:
            ip = m['ip']
            model = m['model'][:25] if m['model'] else 'Unknown'
            lines.append(f"  • `{ip}` — {model}")
        lines.append("")
    
    lines.append("_Check AMS web UI for export errors or try manual export._")
    
    message = "\n".join(lines)
    slack.chat_postMessage(channel=channel, text=message)
    logger.info("Sent log failure report: %d miners missing logs", len(missing))


if __name__ == "__main__":
    main()
