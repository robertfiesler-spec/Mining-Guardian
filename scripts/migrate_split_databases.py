#!/usr/bin/env python3
"""
Database Split Migration Script
================================
Splits the monolithic guardian.db (6.6GB) into 4 logical databases:

1. operational.db  (~50 MB)  - Hot, frequently accessed data
2. timeseries.db   (~5.8 GB) - Append-only historical data  
3. ai_knowledge.db (~20 MB)  - Learning and predictions
4. audit.db        (~10 MB)  - Logs and actions

Run with: python3 scripts/migrate_split_databases.py
"""

import sqlite3
import os
import sys
from pathlib import Path
from datetime import datetime

# Paths
BASE_DIR = Path(__file__).parent.parent
OLD_DB = BASE_DIR / "guardian.db"
NEW_DB_DIR = BASE_DIR / "databases"

# Database definitions - which tables go where
DB_SCHEMAS = {
    "operational.db": {
        "tables": [
            "scans",
            "miner_hardware",
            "pending_approvals",
            "known_dead_boards",
            "alert_listener_cooldown",
            "alert_listener_seen",
            "maintenance_windows",
            "miner_restarts",
            "discovery_log",
        ],
        "description": "Hot operational data - frequently accessed"
    },
    "timeseries.db": {
        "tables": [
            "log_metrics",
            "miner_readings",
            "chain_readings",
            "pool_readings",
            "miner_state_readings",
            "miner_ams_extended",
            "chip_readings",
            "hvac_readings",
            "weather_readings",
        ],
        "description": "Time-series data - append-only historical"
    },
    "ai_knowledge.db": {
        "tables": [
            "llm_analysis",
            "miner_baselines",
            "s19jpro_overheat_tracking",
        ],
        "description": "AI/ML learning and predictions"
    },
    "audit.db": {
        "tables": [
            "action_audit_log",
            "ams_notifications",
            "miner_logs",
            "log_collection_failures",
        ],
        "description": "Audit logs and action history"
    }
}


def get_table_schema(conn, table_name):
    """Get the CREATE TABLE statement for a table."""
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def get_table_indexes(conn, table_name):
    """Get all CREATE INDEX statements for a table."""
    cursor = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (table_name,)
    )
    return [row[0] for row in cursor.fetchall()]


def get_row_count(conn, table_name):
    """Get row count for a table."""
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cursor.fetchone()[0]
    except:
        return 0


def migrate_table(src_conn, dst_conn, table_name, batch_size=10000):
    """Migrate a single table with batched inserts."""
    # Get schema
    schema = get_table_schema(src_conn, table_name)
    if not schema:
        print(f"  ⚠️  Table {table_name} not found in source")
        return 0
    
    # Create table in destination
    dst_conn.execute(schema)
    
    # Get indexes
    indexes = get_table_indexes(src_conn, table_name)
    
    # Get row count
    total_rows = get_row_count(src_conn, table_name)
    if total_rows == 0:
        print(f"  ✓ {table_name}: 0 rows (empty)")
        # Still create indexes
        for idx_sql in indexes:
            dst_conn.execute(idx_sql)
        return 0
    
    # Migrate data in batches
    print(f"  → {table_name}: {total_rows:,} rows...", end="", flush=True)
    
    offset = 0
    migrated = 0
    
    while offset < total_rows:
        # Read batch
        cursor = src_conn.execute(f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}")
        rows = cursor.fetchall()
        
        if not rows:
            break
        
        # Get column count from first row
        num_cols = len(rows[0])
        placeholders = ",".join(["?"] * num_cols)
        
        # Insert batch
        dst_conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
        
        migrated += len(rows)
        offset += batch_size
        
        # Progress indicator
        pct = (migrated / total_rows) * 100
        print(f"\r  → {table_name}: {migrated:,}/{total_rows:,} ({pct:.0f}%)...", end="", flush=True)
    
    dst_conn.commit()
    
    # Create indexes after data migration (faster)
    for idx_sql in indexes:
        dst_conn.execute(idx_sql)
    dst_conn.commit()
    
    print(f"\r  ✓ {table_name}: {migrated:,} rows + {len(indexes)} indexes")
    return migrated


def main():
    print("="*60)
    print("Mining Guardian Database Split Migration")
    print("="*60)
    print(f"Source: {OLD_DB}")
    print(f"Target: {NEW_DB_DIR}/")
    print()
    
    # Check source exists
    if not OLD_DB.exists():
        print(f"❌ Source database not found: {OLD_DB}")
        sys.exit(1)
    
    # Create target directory
    NEW_DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Connect to source
    src_conn = sqlite3.connect(str(OLD_DB))
    src_conn.row_factory = sqlite3.Row
    
    # Get source stats
    print("Source database analysis:")
    total_tables = 0
    total_rows = 0
    for db_name, config in DB_SCHEMAS.items():
        for table in config["tables"]:
            count = get_row_count(src_conn, table)
            total_rows += count
            total_tables += 1
    print(f"  Tables to migrate: {total_tables}")
    print(f"  Total rows: {total_rows:,}")
    print()
    
    # Migrate each database
    start_time = datetime.now()
    
    for db_name, config in DB_SCHEMAS.items():
        db_path = NEW_DB_DIR / db_name
        
        # Remove existing if present
        if db_path.exists():
            db_path.unlink()
        
        print(f"\n📁 Creating {db_name}")
        print(f"   {config['description']}")
        print("-" * 50)
        
        # Connect to new database
        dst_conn = sqlite3.connect(str(db_path))
        dst_conn.execute("PRAGMA journal_mode=WAL")
        dst_conn.execute("PRAGMA synchronous=NORMAL")
        
        db_rows = 0
        for table in config["tables"]:
            rows = migrate_table(src_conn, dst_conn, table)
            db_rows += rows
        
        dst_conn.close()
        
        # Get file size
        size_mb = db_path.stat().st_size / (1024 * 1024)
        print(f"   Total: {db_rows:,} rows, {size_mb:.1f} MB")
    
    src_conn.close()
    
    # Summary
    duration = datetime.now() - start_time
    print("\n" + "="*60)
    print("✅ Migration Complete!")
    print(f"   Duration: {duration}")
    print()
    print("New databases:")
    for db_name in DB_SCHEMAS.keys():
        db_path = NEW_DB_DIR / db_name
        if db_path.exists():
            size_mb = db_path.stat().st_size / (1024 * 1024)
            print(f"   {db_name}: {size_mb:.1f} MB")
    print()
    print("⚠️  Next steps:")
    print("   1. Update core/database.py to use DatabaseRouter")
    print("   2. Test all services with new database structure")
    print("   3. Backup and remove old guardian.db")


if __name__ == "__main__":
    main()
