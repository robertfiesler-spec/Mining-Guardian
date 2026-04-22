#!/usr/bin/env python3
"""
Maintenance Scheduler for Mining Guardian
- Schedule maintenance windows (planned downtime)
- Suppress alerts during maintenance periods
- Track maintenance history
- Slack commands for scheduling/viewing maintenance
"""

import sqlite3
import logging
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "guardian.db"


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_maintenance_tables():
    """Create maintenance tables if they don't exist."""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS maintenance_windows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                affected_miners TEXT,
                created_by TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'scheduled',
                notes TEXT
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_maint_status ON maintenance_windows(status)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_maint_times ON maintenance_windows(start_time, end_time)
        ''')
        conn.commit()


def schedule_maintenance(
    title: str,
    start_time: datetime,
    end_time: datetime,
    description: str = None,
    affected_miners: str = "all",
    created_by: str = "system"
) -> int:
    """Schedule a new maintenance window."""
    with get_db() as conn:
        cursor = conn.execute('''
            INSERT INTO maintenance_windows 
            (title, description, start_time, end_time, affected_miners, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            title,
            description,
            start_time.isoformat(),
            end_time.isoformat(),
            affected_miners,
            created_by
        ))
        conn.commit()
        return cursor.lastrowid


def get_active_maintenance():
    """Get all currently active maintenance windows."""
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM maintenance_windows
            WHERE status IN ('scheduled', 'active')
            AND start_time <= ? AND end_time >= ?
        ''', (now, now)).fetchall()
        return [dict(row) for row in rows]


def get_upcoming_maintenance(hours: int = 24):
    """Get maintenance windows starting in the next N hours."""
    now = datetime.utcnow()
    future = now + timedelta(hours=hours)
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM maintenance_windows
            WHERE status = 'scheduled'
            AND start_time BETWEEN ? AND ?
            ORDER BY start_time ASC
        ''', (now.isoformat(), future.isoformat())).fetchall()
        return [dict(row) for row in rows]


def get_all_maintenance(limit: int = 20):
    """Get all maintenance windows (recent history)."""
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM maintenance_windows
            ORDER BY start_time DESC
            LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(row) for row in rows]


def is_miner_in_maintenance(miner_id: str) -> bool:
    """Check if a specific miner is currently in a maintenance window."""
    active = get_active_maintenance()
    for window in active:
        affected = window.get('affected_miners', 'all')
        if affected == 'all':
            return True
        try:
            miner_list = json.loads(affected)
            if miner_id in miner_list or str(miner_id) in miner_list:
                return True
        except (json.JSONDecodeError, TypeError):
            if affected == miner_id or affected == str(miner_id):
                return True
    return False


def cancel_maintenance(maintenance_id: int, cancelled_by: str = "system") -> bool:
    """Cancel a scheduled maintenance window."""
    with get_db() as conn:
        cursor = conn.execute('''
            UPDATE maintenance_windows
            SET status = 'cancelled', notes = ?
            WHERE id = ? AND status = 'scheduled'
        ''', (f"Cancelled by {cancelled_by} at {datetime.utcnow().isoformat()}", maintenance_id))
        conn.commit()
        return cursor.rowcount > 0


def complete_maintenance(maintenance_id: int, notes: str = None) -> bool:
    """Mark a maintenance window as completed."""
    with get_db() as conn:
        cursor = conn.execute('''
            UPDATE maintenance_windows
            SET status = 'completed', notes = COALESCE(?, notes)
            WHERE id = ? AND status IN ('scheduled', 'active')
        ''', (notes, maintenance_id))
        conn.commit()
        return cursor.rowcount > 0


def update_maintenance_status():
    """Auto-update maintenance status based on current time."""
    now = datetime.utcnow().isoformat()
    with get_db() as conn:
        conn.execute('''
            UPDATE maintenance_windows
            SET status = 'active'
            WHERE status = 'scheduled'
            AND start_time <= ? AND end_time >= ?
        ''', (now, now))
        
        conn.execute('''
            UPDATE maintenance_windows
            SET status = 'completed'
            WHERE status = 'active'
            AND end_time < ?
        ''', (now,))
        
        conn.commit()


def format_maintenance_for_slack(windows, title: str) -> str:
    """Format maintenance windows for Slack display."""
    if not windows:
        return f":calendar: *{title}*\n\nNo maintenance windows found."
    
    lines = [f":calendar: *{title}*\n"]
    
    for w in windows:
        status_emoji = {
            'scheduled': ':clock1:',
            'active': ':wrench:',
            'completed': ':white_check_mark:',
            'cancelled': ':x:'
        }.get(w['status'], ':question:')
        
        start = datetime.fromisoformat(w['start_time'])
        end = datetime.fromisoformat(w['end_time'])
        duration = end - start
        
        lines.append(f"{status_emoji} *{w['title']}* (ID: {w['id']})")
        lines.append(f"    Start: {start.strftime('%Y-%m-%d %H:%M')} UTC")
        lines.append(f"    End: {end.strftime('%Y-%m-%d %H:%M')} UTC ({duration})")
        if w.get('description'):
            lines.append(f"    {w['description']}")
        lines.append("")
    
    return "\n".join(lines)


def cmd_maintenance(args: str = "") -> str:
    """Handle /maintenance command."""
    update_maintenance_status()
    
    parts = args.strip().split() if args else []
    
    if not parts or parts[0] == "list":
        active = get_active_maintenance()
        upcoming = get_upcoming_maintenance(hours=48)
        
        result = []
        if active:
            result.append(format_maintenance_for_slack(active, "Active Maintenance"))
        
        active_ids = {w['id'] for w in active}
        upcoming_only = [w for w in upcoming if w['id'] not in active_ids]
        
        if upcoming_only:
            result.append(format_maintenance_for_slack(upcoming_only, "Upcoming (next 48h)"))
        
        if not result:
            return ":calendar: *Maintenance Schedule*\n\nNo active or upcoming maintenance windows."
        
        return "\n\n".join(result)
    
    elif parts[0] == "all":
        windows = get_all_maintenance(limit=10)
        return format_maintenance_for_slack(windows, "Maintenance History (Last 10)")
    
    elif parts[0] == "cancel" and len(parts) >= 2:
        try:
            maint_id = int(parts[1])
            if cancel_maintenance(maint_id, "Slack user"):
                return f":white_check_mark: Maintenance #{maint_id} cancelled."
            else:
                return f":x: Could not cancel maintenance #{maint_id} (not found or already completed)."
        except ValueError:
            return ":x: Invalid maintenance ID. Usage: `maintenance cancel <id>`"
    
    else:
        return (
            ":calendar: *Maintenance Commands*\n\n"
            "`maintenance` - Show active/upcoming\n"
            "`maintenance all` - Show history\n"
            "`maintenance cancel <id>` - Cancel scheduled maintenance\n"
        )


try:
    init_maintenance_tables()
except Exception as e:
    logger.warning(f"Could not initialize maintenance tables: {e}")


if __name__ == "__main__":
    init_maintenance_tables()
    print(cmd_maintenance())
