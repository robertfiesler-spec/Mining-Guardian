#!/usr/bin/env python3
"""
dashboard_api.py
Mining Guardian — Local Dashboard API

Serves pre-built queries from guardian.db as JSON endpoints.
Used by Retool dashboard and future custom React dashboard.
Also available to OpenClaw for AI context.

Usage:
    source venv/bin/activate
    python dashboard_api.py

Runs on: http://localhost:8585
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

DB_PATH = os.path.join(os.path.dirname(__file__), "guardian.db")
app = FastAPI(title="Mining Guardian API", version="1.0.0")

# Allow Retool and any local client to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Fleet Status ─────────────────────────────────────────────

@app.get("/fleet/latest")
def fleet_latest():
    """Latest scan summary — fleet status right now."""
    conn = get_db()
    scan = conn.execute(
        "SELECT * FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not scan:
        return {"error": "No scans yet"}
    scan = dict(scan)

    # Latest readings breakdown
    readings = conn.execute("""
        SELECT action, COUNT(*) as count
        FROM miner_readings
        WHERE scan_id = ? AND action IS NOT NULL
        GROUP BY action
    """, (scan["id"],)).fetchall()

    scan["action_breakdown"] = {r["action"]: r["count"] for r in readings}
    conn.close()
    return scan


@app.get("/fleet/history")
def fleet_history(days: int = 7):
    """Scan history over the last N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM scans WHERE scanned_at > ? ORDER BY id DESC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Miners ───────────────────────────────────────────────────

@app.get("/miners/flagged")
def miners_flagged():
    """All miners currently flagged in the latest scan."""
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, status, hashrate_pct,
               temp_chip, action, issue
        FROM miner_readings
        WHERE scan_id = ? AND action IS NOT NULL
        ORDER BY action, ip
    """, (scan["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/most_flagged")
def miners_most_flagged(limit: int = 20):
    """Miners flagged most often — trouble list."""
    conn = get_db()
    rows = conn.execute("""
        SELECT miner_id, ip, model,
               COUNT(*) as times_flagged,
               MAX(scanned_at) as last_flagged,
               action
        FROM miner_readings
        WHERE action IS NOT NULL
        GROUP BY miner_id
        ORDER BY times_flagged DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/history")
def miner_history(miner_id: str, days: int = 7):
    """Full telemetry history for a specific miner."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute("""
        SELECT scanned_at, hashrate_pct, temp_chip, status, action, issue
        FROM miner_readings
        WHERE miner_id = ? AND scanned_at > ?
        ORDER BY scanned_at ASC
    """, (miner_id, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/miners/{miner_id}/logs")
def miner_logs(miner_id: str, limit: int = 10):
    """Recent log files collected for a miner."""
    conn = get_db()
    rows = conn.execute("""
        SELECT collected_at, health_status, log_file, content
        FROM miner_logs
        WHERE miner_id = ?
        ORDER BY id DESC
        LIMIT ?
    """, (miner_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Temperature ───────────────────────────────────────────────

@app.get("/temps/hot_miners")
def temps_hot_miners():
    """Miners currently in yellow or red temp zones."""
    conn = get_db()
    scan = conn.execute("SELECT id FROM scans ORDER BY id DESC LIMIT 1").fetchone()
    if not scan:
        return []
    rows = conn.execute("""
        SELECT miner_id, ip, model, temp_chip, action
        FROM miner_readings
        WHERE scan_id = ? AND temp_chip >= 76
        ORDER BY temp_chip DESC
    """, (scan["id"],)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/temps/history")
def temps_history(days: int = 7):
    """Average chip temp across fleet over time."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute("""
        SELECT s.scanned_at,
               AVG(r.temp_chip) as avg_temp,
               MAX(r.temp_chip) as max_temp,
               MIN(r.temp_chip) as min_temp
        FROM miner_readings r
        JOIN scans s ON r.scan_id = s.id
        WHERE s.scanned_at > ? AND r.temp_chip > 0
        GROUP BY s.id
        ORDER BY s.scanned_at ASC
    """, (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Power ─────────────────────────────────────────────────────

@app.get("/weather/history")
def weather_history(days: int = 7):
    """Ambient temp and humidity history."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM weather_readings WHERE recorded_at > ? ORDER BY id ASC",
        (cutoff,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Notifications ─────────────────────────────────────────────

@app.get("/notifications/recent")
def notifications_recent(limit: int = 50):
    """Recent AMS notifications grouped by type."""
    conn = get_db()
    rows = conn.execute("""
        SELECT key, alert_level, miner_ip, recorded_at
        FROM ams_notifications
        ORDER BY id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/notifications/summary")
def notifications_summary():
    """Notification counts grouped by type and severity."""
    conn = get_db()
    rows = conn.execute("""
        SELECT key, alert_level, COUNT(*) as count
        FROM ams_notifications
        GROUP BY key, alert_level
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Restarts ──────────────────────────────────────────────────

@app.get("/restarts/recent")
def restarts_recent(limit: int = 20):
    """Recent restart events."""
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM miner_restarts
        ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/log")
def audit_log(days: int = None, miner_id: str = None, limit: int = 100):
    """Permanent action audit log — every approval and denial ever recorded.

    Filterable by date range (days) and miner_id.
    Grouped by date for easy review. Never expires.
    """
    conn   = get_db()
    query  = "SELECT * FROM action_audit_log WHERE 1=1"
    params = []
    if days:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        query += " AND date >= ?"
        params.append(cutoff)
    if miner_id:
        query += " AND miner_id = ?"
        params.append(miner_id)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/audit/summary")
def audit_summary():
    """Audit log summary — counts by decision, action, and approver."""
    conn = get_db()
    by_decision = conn.execute("""
        SELECT decision, COUNT(*) as count
        FROM action_audit_log
        GROUP BY decision
    """).fetchall()
    by_action = conn.execute("""
        SELECT action_taken, decision, COUNT(*) as count
        FROM action_audit_log
        GROUP BY action_taken, decision
        ORDER BY count DESC
    """).fetchall()
    by_approver = conn.execute("""
        SELECT approved_by, decision, COUNT(*) as count
        FROM action_audit_log
        WHERE approved_by IS NOT NULL
        GROUP BY approved_by, decision
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return {
        "by_decision": [dict(r) for r in by_decision],
        "by_action":   [dict(r) for r in by_action],
        "by_approver": [dict(r) for r in by_approver],
    }


# ── Health Check ──────────────────────────────────────────────

@app.get("/")
def health():
    conn = get_db()
    scan_count = conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0]
    latest = conn.execute(
        "SELECT scanned_at FROM scans ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return {
        "status": "online",
        "db": DB_PATH,
        "total_scans": scan_count,
        "last_scan": latest[0] if latest else None,
    }


if __name__ == "__main__":
    import uvicorn
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Mining Guardian Dashboard API")
    print("  http://localhost:8585")
    print("  http://localhost:8585/docs  ← interactive API docs")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    uvicorn.run(app, host="0.0.0.0", port=8585)
