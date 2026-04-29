#!/usr/bin/env python3
"""
Migrate Split SQLite Databases to PostgreSQL
=============================================
Migrates data from the 4 split SQLite databases to PostgreSQL.

Usage: python3 scripts/migrate_to_postgres.py
"""

import sqlite3
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_batch
import os
from pathlib import Path
from datetime import datetime
import sys

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

# Paths
BASE_DIR = Path(__file__).parent.parent
SQLITE_DIR = BASE_DIR / "databases"

# PostgreSQL connection settings — password MUST come from environment.
# This script is also guarded by MG_ALLOW_MIGRATION=1 (see decision D-6).
PG_CONFIG = {
    'host': os.environ.get('MG_DB_HOST', 'localhost'),
    'port': int(os.environ.get('MG_DB_PORT', '5432')),
    'dbname': os.environ.get('MG_DB_NAME', 'mining_guardian'),
    'user': os.environ.get('MG_DB_USER', 'guardian_app'),
    'password': os.environ.get('MG_DB_PASSWORD') or (_ for _ in ()).throw(
        EnvironmentError("MG_DB_PASSWORD must be set in environment to run this migration script.")
    ),
}

# SQLite databases and their tables
SQLITE_DBS = {
    'operational.db': [
        'scans', 'miner_hardware', 'pending_approvals', 'known_dead_boards',
        'alert_listener_cooldown', 'alert_listener_seen', 'maintenance_windows',
        'miner_restarts', 'discovery_log'
    ],
    'timeseries.db': [
        'log_metrics', 'miner_readings', 'chain_readings', 'pool_readings',
        'miner_state_readings', 'miner_ams_extended', 'chip_readings',
        'hvac_readings', 'weather_readings'
    ],
    'ai_knowledge.db': [
        'llm_analysis', 'miner_baselines', 's19jpro_overheat_tracking'
    ],
    'audit.db': [
        'action_audit_log', 'ams_notifications', 'miner_logs', 'log_collection_failures'
    ]
}

# SQLite to PostgreSQL type mapping
TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'REAL': 'DOUBLE PRECISION',
    'TEXT': 'TEXT',
    'BLOB': 'BYTEA',
    'NUMERIC': 'NUMERIC',
}


def sqlite_type_to_pg(sqlite_type):
    """Convert SQLite type to PostgreSQL type."""
    sqlite_type = sqlite_type.upper() if sqlite_type else 'TEXT'
    for sqlite_t, pg_t in TYPE_MAP.items():
        if sqlite_t in sqlite_type:
            return pg_t
    return 'TEXT'


def get_sqlite_schema(conn, table_name):
    """Get column info from SQLite table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = []
    primary_key = None
    for row in cursor.fetchall():
        col_id, name, col_type, notnull, default, pk = row
        columns.append({
            'name': name,
            'type': col_type,
            'notnull': notnull,
            'default': default,
            'pk': pk
        })
        if pk:
            primary_key = name
    return columns, primary_key


def create_pg_table(pg_conn, table_name, columns, primary_key):
    """Create PostgreSQL table from SQLite schema."""
    col_defs = []
    for col in columns:
        pg_type = sqlite_type_to_pg(col['type'])
        
        # Handle auto-increment primary key
        if col['pk'] and col['name'] == 'id':
            col_def = f"{col['name']} SERIAL PRIMARY KEY"
        else:
            col_def = f"{col['name']} {pg_type}"
            if col['notnull']:
                col_def += " NOT NULL"
        
        col_defs.append(col_def)
    
    # Drop table if exists
    with pg_conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
    
    # Create table
    create_sql = f"CREATE TABLE {table_name} (\n  " + ",\n  ".join(col_defs) + "\n)"
    
    with pg_conn.cursor() as cur:
        cur.execute(create_sql)
    
    pg_conn.commit()
    return True


def migrate_table_data(sqlite_conn, pg_conn, table_name, batch_size=5000):
    """Migrate data from SQLite to PostgreSQL."""
    # Get column names
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Get total rows
    total = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    if total == 0:
        return 0
    
    # Build INSERT statement
    col_names = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
    
    # Migrate in batches
    migrated = 0
    offset = 0
    
    while offset < total:
        # Read batch from SQLite
        rows = sqlite_conn.execute(
            f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}"
        ).fetchall()
        
        if not rows:
            break
        
        # Insert into PostgreSQL
        with pg_conn.cursor() as cur:
            execute_batch(cur, insert_sql, rows, page_size=1000)
        pg_conn.commit()
        
        migrated += len(rows)
        offset += batch_size
        
        # Progress
        pct = (migrated / total) * 100
        print(f"\r    {table_name}: {migrated:,}/{total:,} ({pct:.0f}%)...", end='', flush=True)
    
    print(f"\r    {table_name}: {migrated:,} rows migrated")
    
    # Reset sequence if table has serial primary key
    if 'id' in columns:
        with pg_conn.cursor() as cur:
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE(MAX(id), 0) + 1, false) FROM {table_name}")
        pg_conn.commit()
    
    return migrated


def create_indexes(pg_conn):
    """Create indexes for better query performance."""
    indexes = [
        # Operational
        "CREATE INDEX IF NOT EXISTS idx_scans_scanned_at ON scans(scanned_at)",
        "CREATE INDEX IF NOT EXISTS idx_pending_approvals_status ON pending_approvals(status)",
        "CREATE INDEX IF NOT EXISTS idx_maintenance_status ON maintenance_windows(status)",
        
        # Timeseries
        "CREATE INDEX IF NOT EXISTS idx_miner_readings_miner_scanned ON miner_readings(miner_id, scanned_at)",
        "CREATE INDEX IF NOT EXISTS idx_miner_readings_scanned_at ON miner_readings(scanned_at)",
        "CREATE INDEX IF NOT EXISTS idx_chain_readings_miner ON chain_readings(miner_id, scanned_at)",
        "CREATE INDEX IF NOT EXISTS idx_log_metrics_miner_type ON log_metrics(miner_id, metric_type)",
        "CREATE INDEX IF NOT EXISTS idx_log_metrics_recorded ON log_metrics(recorded_at)",
        "CREATE INDEX IF NOT EXISTS idx_hvac_readings_recorded ON hvac_readings(recorded_at)",
        "CREATE INDEX IF NOT EXISTS idx_weather_readings_recorded ON weather_readings(recorded_at)",
        
        # Audit
        "CREATE INDEX IF NOT EXISTS idx_audit_date ON action_audit_log(date)",
        "CREATE INDEX IF NOT EXISTS idx_audit_miner ON action_audit_log(miner_id)",
        "CREATE INDEX IF NOT EXISTS idx_ams_notifications_miner ON ams_notifications(miner_id)",
    ]
    
    print("\nCreating indexes...")
    with pg_conn.cursor() as cur:
        for idx_sql in indexes:
            try:
                cur.execute(idx_sql)
                print(f"  Created: {idx_sql.split('idx_')[1].split(' ')[0]}")
            except Exception as e:
                print(f"  Warning: {e}")
    pg_conn.commit()


def main():
    print("=" * 60)
    print("Mining Guardian: SQLite to PostgreSQL Migration")
    print("=" * 60)
    
    # Connect to PostgreSQL
    print("\nConnecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print(f"  Connected to {PG_CONFIG['dbname']} on {PG_CONFIG['host']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        sys.exit(1)
    
    total_migrated = 0
    start_time = datetime.now()
    
    # Migrate each SQLite database
    for db_file, tables in SQLITE_DBS.items():
        db_path = SQLITE_DIR / db_file
        
        if not db_path.exists():
            print(f"\nSkipping {db_file} (not found)")
            continue
        
        print(f"\n📁 Migrating {db_file}")
        print("-" * 40)
        
        sqlite_conn = sqlite3.connect(str(db_path))
        
        for table in tables:
            try:
                # Get schema
                columns, pk = get_sqlite_schema(sqlite_conn, table)
                if not columns:
                    print(f"  {table}: skipped (no columns)")
                    continue
                
                # Create PostgreSQL table
                create_pg_table(pg_conn, table, columns, pk)
                
                # Migrate data
                rows = migrate_table_data(sqlite_conn, pg_conn, table)
                total_migrated += rows
                
            except Exception as e:
                print(f"  {table}: ERROR - {e}")
        
        sqlite_conn.close()
    
    # Create indexes
    create_indexes(pg_conn)
    
    # Summary
    duration = datetime.now() - start_time
    print("\n" + "=" * 60)
    print("✅ Migration Complete!")
    print(f"  Duration: {duration}")
    print(f"  Total rows migrated: {total_migrated:,}")
    print("\nPostgreSQL connection string:")
    print(f"  postgresql://{PG_CONFIG['user']}:****@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
    
    pg_conn.close()


if __name__ == "__main__":
    main()
