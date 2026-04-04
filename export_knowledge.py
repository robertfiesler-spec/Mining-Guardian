#!/usr/bin/env python3
"""
export_knowledge.py
Mining Guardian — Knowledge Export

Exports a knowledge.json file from guardian.db containing:
- Log patterns per miner model (healthy vs flagged)
- Failure signatures — what patterns appear before failures
- Remediation outcomes — what worked and what didn't
- Scan statistics — hashrate and temp baselines per model
- Action audit log — all approvals/denials

Run this monthly at each customer site before USB collection.

Usage:
    python export_knowledge.py
    python export_knowledge.py --output /path/to/knowledge.json
"""

import sqlite3
import json
import os
import argparse
from datetime import datetime, date
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(__file__), "guardian.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def export_knowledge(output_path: str = "knowledge.json") -> dict:
    conn = get_db()

    # ── Scan statistics per model ──────────────────────────────
    model_stats = conn.execute("""
        SELECT model,
               COUNT(*)                          AS total_readings,
               AVG(CASE WHEN status='online' AND hashrate_pct > 90
                        THEN hashrate_pct END)   AS avg_healthy_hashrate,
               AVG(CASE WHEN temp_chip > 0
                        THEN temp_chip END)       AS avg_temp,
               MAX(temp_chip)                    AS max_temp_seen,
               SUM(CASE WHEN action='RESTART'
                        THEN 1 ELSE 0 END)       AS restart_count,
               SUM(CASE WHEN action='PDU_CYCLE'
                        THEN 1 ELSE 0 END)       AS pdu_cycle_count,
               SUM(CASE WHEN action='PHYSICAL_CYCLE'
                        THEN 1 ELSE 0 END)       AS physical_cycle_count,
               SUM(CASE WHEN status='offline'
                        THEN 1 ELSE 0 END)       AS offline_count
        FROM miner_readings
        WHERE model IS NOT NULL
        GROUP BY model
        ORDER BY total_readings DESC
    """).fetchall()

    # ── Most problematic miners ────────────────────────────────
    trouble_list = conn.execute("""
        SELECT miner_id, ip, model,
               COUNT(*)                           AS times_flagged,
               SUM(CASE WHEN action='RESTART'
                        THEN 1 ELSE 0 END)        AS restarts,
               SUM(CASE WHEN action='PDU_CYCLE'
                        THEN 1 ELSE 0 END)        AS pdu_cycles,
               MAX(scanned_at)                    AS last_flagged
        FROM miner_readings
        WHERE action IS NOT NULL
        GROUP BY miner_id
        HAVING times_flagged > 3
        ORDER BY times_flagged DESC
        LIMIT 50
    """).fetchall()

    # ── AMS notification patterns ──────────────────────────────
    notification_patterns = conn.execute("""
        SELECT key, alert_level, COUNT(*) AS count
        FROM ams_notifications
        GROUP BY key, alert_level
        ORDER BY count DESC
    """).fetchall()

    # ── Action audit log ───────────────────────────────────────
    audit_log = conn.execute("""
        SELECT date, miner_id, ip, model, problem,
               action_taken, decision, approved_by
        FROM action_audit_log
        ORDER BY timestamp DESC
        LIMIT 500
    """).fetchall()

    # ── Log patterns per model ─────────────────────────────────
    log_patterns = conn.execute("""
        SELECT r.model, l.health_status, l.log_file,
               COUNT(*) AS occurrences
        FROM miner_logs l
        JOIN miner_readings r ON l.miner_id = r.miner_id
        WHERE r.model IS NOT NULL
        GROUP BY r.model, l.health_status, l.log_file
        ORDER BY occurrences DESC
    """).fetchall()

    conn.close()

    knowledge = {
        "exported_at":    datetime.now().isoformat(),
        "export_version": "1.0",
        "db_path":        DB_PATH,
        "model_statistics": [dict(r) for r in model_stats],
        "trouble_miners":   [dict(r) for r in trouble_list],
        "notification_patterns": [dict(r) for r in notification_patterns],
        "action_audit_log":      [dict(r) for r in audit_log],
        "log_patterns":          [dict(r) for r in log_patterns],
    }

    with open(output_path, "w") as f:
        json.dump(knowledge, f, indent=2, default=str)

    print(f"\n✅ Knowledge exported to {output_path}")
    print(f"   Models tracked:     {len(model_stats)}")
    print(f"   Trouble miners:     {len(trouble_list)}")
    print(f"   Audit log entries:  {len(audit_log)}")
    print(f"   Notification types: {len(notification_patterns)}")
    return knowledge


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export Mining Guardian knowledge")
    parser.add_argument("--output", default="knowledge.json",
                        help="Output file path (default: knowledge.json)")
    args = parser.parse_args()
    export_knowledge(args.output)
