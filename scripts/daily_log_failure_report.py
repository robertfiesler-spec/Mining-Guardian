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
import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from slack_sdk import WebClient

_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = _ROOT / "guardian.db"
CONFIG_PATH = _ROOT / "config.json"


def get_slack_client():
    """Load config and return Slack client."""
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    token = cfg.get("slack_bot_token") or os.environ.get("SLACK_BOT_TOKEN")
    return WebClient(token=token)


def get_miners_without_logs():
    """Get all miners that did NOT get logs in the last 12 hours."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute("""
        SELECT DISTINCT mr.miner_id, mr.ip, mr.model, mr.status
        FROM miner_readings mr
        WHERE mr.scanned_at > datetime('now', '-1 day')
        AND mr.id = (SELECT MAX(id) FROM miner_readings WHERE miner_id = mr.miner_id)
        AND mr.miner_id NOT IN (
            SELECT DISTINCT miner_id FROM miner_logs 
            WHERE collected_at > datetime('now', '-12 hours')
        )
        ORDER BY mr.ip
    """).fetchall()
    
    conn.close()
    return [dict(r) for r in rows]


def get_fleet_stats():
    """Get fleet size and log count."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    
    fleet = conn.execute(
        "SELECT COUNT(DISTINCT miner_id) FROM miner_readings WHERE scanned_at > datetime('now', '-1 day')"
    ).fetchone()[0]
    
    with_logs = conn.execute(
        "SELECT COUNT(DISTINCT miner_id) FROM miner_logs WHERE collected_at > datetime('now', '-12 hours')"
    ).fetchone()[0]
    
    conn.close()
    return fleet, with_logs


def main():
    logger.info("=== DAILY LOG FAILURE REPORT ===")
    
    slack = get_slack_client()
    channel = "C0AQ8SE1448"  # #mining-guardian
    
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
