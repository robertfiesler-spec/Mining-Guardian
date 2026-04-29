#!/usr/bin/env python3
"""
migrate_sqlite_to_postgres.py
Mining Guardian — SQLite to PostgreSQL Migration

This script migrates all data from guardian.db (SQLite) to PostgreSQL.
Run with: python3 migrate_sqlite_to_postgres.py

Features:
- Batch inserts for performance (10,000 rows at a time)
- Progress tracking with ETA
- Handles large tables (18M+ rows in log_metrics)
- Preserves all data and relationships
- Creates schema if not exists

Usage:
    python3 migrate_sqlite_to_postgres.py --dry-run   # Check connectivity only
    python3 migrate_sqlite_to_postgres.py             # Full migration
    python3 migrate_sqlite_to_postgres.py --table log_metrics  # Single table

Created: 2026-04-21
"""

import os
import sys
import sqlite3
import argparse
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict, Any

# ---------------------------------------------------------------------------
# Safety guard — see docs/DECISIONS.md D-6.
# This script is destructive: it copies SQLite contents into Postgres and can
# clobber live operational data if run by mistake. Bucket 7.6 (2026-04-29) added
# this runtime guard to all three migrate_*.py scripts. To run the migration
# intentionally, set MG_ALLOW_MIGRATION=1 in the environment.
# ---------------------------------------------------------------------------
if not os.environ.get("MG_ALLOW_MIGRATION"):
    sys.stderr.write(
        "ERROR: %s is gated.\n"
        "       Set MG_ALLOW_MIGRATION=1 to run this destructive migration.\n"
        "       See docs/DECISIONS.md D-6 for context.\n"
        % Path(__file__).name
    )
    sys.exit(2)
# ---------------------------------------------------------------------------

# Add project root to path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary --break-system-packages")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# Configuration
SQLITE_PATH = _ROOT / "guardian.db"
BATCH_SIZE = 10000
LARGE_TABLE_THRESHOLD = 100000  # Tables with more rows get special handling

# PostgreSQL connection from .env
PG_CONFIG = {
    "host": os.getenv("CATALOG_DB_HOST", "100.110.87.1"),
    "port": int(os.getenv("CATALOG_DB_PORT", "5432")),
    "database": os.getenv("CATALOG_DB_NAME", "mining_guardian"),
    "user": os.getenv("CATALOG_DB_USER", "guardian_admin"),
    "password": os.getenv("CATALOG_DB_PASSWORD", ""),
}

# Table migration order (respects foreign keys)
TABLE_ORDER = [
    "scans",
    "miner_readings",
    "chain_readings",
    "pool_readings",
    "chip_readings",
    "miner_state_readings",
    "miner_ams_extended",
    "miner_logs",
    "miner_restarts",
    "miner_baselines",
    "miner_hardware",
    "hvac_readings",
    "weather_readings",
    "ams_notifications",
    "action_audit_log",
    "pending_approvals",
    "llm_analysis",
    "known_dead_boards",
    "alert_listener_seen",
    "alert_listener_cooldown",
    "log_collection_failures",
    "s19jpro_overheat_tracking",
    "discovery_log",
    "log_metrics",  # Last because it's huge
]


def get_sqlite_conn():
    """Get SQLite connection."""
    return sqlite3.connect(SQLITE_PATH)


def get_pg_conn():
    """Get PostgreSQL connection."""
    return psycopg2.connect(**PG_CONFIG)


def get_table_columns(sqlite_cur, table: str) -> List[str]:
    """Get column names for a table."""
    sqlite_cur.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in sqlite_cur.fetchall()]


def get_row_count(sqlite_cur, table: str) -> int:
    """Get row count for a table."""
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
    return sqlite_cur.fetchone()[0]


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def migrate_table(sqlite_cur, pg_cur, table: str, dry_run: bool = False) -> Tuple[int, float]:
    """
    Migrate a single table from SQLite to PostgreSQL.
    Returns (rows_migrated, duration_seconds).
    """
    start_time = time.time()
    
    # Get columns and row count
    columns = get_table_columns(sqlite_cur, table)
    row_count = get_row_count(sqlite_cur, table)
    
    if row_count == 0:
        print(f"  {table}: 0 rows (empty, skipping)")
        return 0, 0.0
    
    print(f"  {table}: {row_count:,} rows", end="", flush=True)
    
    if dry_run:
        print(" [DRY RUN]")
        return row_count, 0.0
    
    # Clear target table first
    pg_cur.execute(f"TRUNCATE TABLE {table} CASCADE")
    
    # For tables with SERIAL primary key, we need to handle id specially
    # We'll insert with explicit id to preserve foreign key relationships
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table} ({col_list}) VALUES %s"
    
    # Migrate in batches
    migrated = 0
    sqlite_cur.execute(f"SELECT {col_list} FROM {table}")
    
    while True:
        rows = sqlite_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        
        # Convert rows to list of tuples
        batch = [tuple(row) for row in rows]
        execute_values(pg_cur, insert_sql, batch, page_size=BATCH_SIZE)
        
        migrated += len(rows)
        
        # Progress update for large tables
        if row_count > LARGE_TABLE_THRESHOLD:
            pct = migrated / row_count * 100
            elapsed = time.time() - start_time
            eta = (elapsed / migrated) * (row_count - migrated) if migrated > 0 else 0
            print(f"\r  {table}: {migrated:,}/{row_count:,} ({pct:.1f}%) ETA: {format_duration(eta)}    ", end="", flush=True)
    
    # Reset sequence for SERIAL columns
    if "id" in columns:
        pg_cur.execute(f"""
            SELECT setval(pg_get_serial_sequence('{table}', 'id'), 
                          COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)
        """)
    
    duration = time.time() - start_time
    print(f"\r  {table}: {migrated:,} rows migrated in {format_duration(duration)}    ")
    
    return migrated, duration


def run_schema(pg_cur):
    """Apply schema from SQL file."""
    schema_path = _ROOT / "migrations" / "001_initial_schema.sql"
    if schema_path.exists():
        print("Applying schema...")
        with open(schema_path) as f:
            pg_cur.execute(f.read())
        print("Schema applied.")
    else:
        print(f"WARNING: Schema file not found: {schema_path}")


def main():
    parser = argparse.ArgumentParser(description="Migrate Mining Guardian from SQLite to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Check connectivity and show row counts only")
    parser.add_argument("--table", type=str, help="Migrate a single table only")
    parser.add_argument("--skip-schema", action="store_true", help="Skip schema creation (assume tables exist)")
    parser.add_argument("--skip-large", action="store_true", help="Skip log_metrics (18M+ rows)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Mining Guardian — SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"Source: {SQLITE_PATH}")
    print(f"Target: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}")
    print()
    
    # Check SQLite
    if not SQLITE_PATH.exists():
        print(f"ERROR: SQLite database not found: {SQLITE_PATH}")
        sys.exit(1)
    
    # Check PostgreSQL connectivity
    try:
        pg_conn = get_pg_conn()
        pg_cur = pg_conn.cursor()
        pg_cur.execute("SELECT version()")
        pg_version = pg_cur.fetchone()[0]
        print(f"PostgreSQL connected: {pg_version[:50]}...")
    except Exception as e:
        print(f"ERROR: Cannot connect to PostgreSQL: {e}")
        sys.exit(1)
    
    # Apply schema unless skipped
    if not args.skip_schema and not args.dry_run:
        run_schema(pg_cur)
        pg_conn.commit()
    
    # Open SQLite
    sqlite_conn = get_sqlite_conn()
    sqlite_cur = sqlite_conn.cursor()
    
    # Determine tables to migrate
    tables = [args.table] if args.table else TABLE_ORDER
    if args.skip_large:
        tables = [t for t in tables if t != "log_metrics"]
    
    print()
    print("Migrating tables:")
    print("-" * 40)
    
    total_rows = 0
    total_duration = 0.0
    
    for table in tables:
        try:
            rows, duration = migrate_table(sqlite_cur, pg_cur, table, args.dry_run)
            total_rows += rows
            total_duration += duration
            
            if not args.dry_run:
                pg_conn.commit()
                
        except Exception as e:
            print(f"\nERROR migrating {table}: {e}")
            pg_conn.rollback()
            if args.table:  # Single table mode - fail
                sys.exit(1)
            # Multi-table mode - continue
            continue
    
    print()
    print("=" * 60)
    print(f"Migration complete: {total_rows:,} rows in {format_duration(total_duration)}")
    if args.dry_run:
        print("(DRY RUN - no data was actually migrated)")
    print("=" * 60)
    
    # Cleanup
    sqlite_conn.close()
    pg_conn.close()


if __name__ == "__main__":
    main()
