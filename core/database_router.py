#!/usr/bin/env python3
"""
Database Router for Mining Guardian
====================================
Routes database queries to the appropriate split database:
- operational.db  - Hot, frequently accessed data
- timeseries.db   - Append-only historical data
- ai_knowledge.db - Learning and predictions
- audit.db        - Logs and actions

Created: April 22, 2026
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Database directory
DB_DIR = Path(__file__).parent.parent / "databases"

# Table to database mapping
TABLE_ROUTING = {
    # operational.db - Hot data
    "scans": "operational.db",
    "miner_hardware": "operational.db",
    "pending_approvals": "operational.db",
    "known_dead_boards": "operational.db",
    "alert_listener_cooldown": "operational.db",
    "alert_listener_seen": "operational.db",
    "maintenance_windows": "operational.db",
    "miner_restarts": "operational.db",
    "discovery_log": "operational.db",
    
    # timeseries.db - Historical data
    "log_metrics": "timeseries.db",
    "miner_readings": "timeseries.db",
    "chain_readings": "timeseries.db",
    "pool_readings": "timeseries.db",
    "miner_state_readings": "timeseries.db",
    "miner_ams_extended": "timeseries.db",
    "chip_readings": "timeseries.db",
    "hvac_readings": "timeseries.db",
    "weather_readings": "timeseries.db",
    
    # ai_knowledge.db - AI/ML data
    "llm_analysis": "ai_knowledge.db",
    "miner_baselines": "ai_knowledge.db",
    "s19jpro_overheat_tracking": "ai_knowledge.db",
    
    # audit.db - Audit logs
    "action_audit_log": "audit.db",
    "ams_notifications": "audit.db",
    "miner_logs": "audit.db",
    "log_collection_failures": "audit.db",
}

# Database file list
DATABASES = ["operational.db", "timeseries.db", "ai_knowledge.db", "audit.db"]


class DatabaseRouter:
    """
    Routes database operations to the correct split database.
    
    Usage:
        router = DatabaseRouter()
        
        # Get connection for a specific table
        with router.connection("miner_readings") as conn:
            conn.execute("SELECT * FROM miner_readings LIMIT 10")
        
        # Get connection for a specific database
        with router.db_connection("operational.db") as conn:
            conn.execute("SELECT * FROM scans")
    """
    
    def __init__(self, db_dir: Path = None):
        self.db_dir = db_dir or DB_DIR
        self._connections: Dict[str, sqlite3.Connection] = {}
        self._verify_databases()
    
    def _verify_databases(self):
        """Verify all split databases exist."""
        missing = []
        for db_name in DATABASES:
            db_path = self.db_dir / db_name
            if not db_path.exists():
                missing.append(db_name)
        
        if missing:
            logger.warning(f"Missing databases: {missing}. Run migrate_split_databases.py first.")
    
    def get_db_for_table(self, table_name: str) -> str:
        """Get the database filename for a given table."""
        db_name = TABLE_ROUTING.get(table_name)
        if not db_name:
            raise ValueError(f"Unknown table: {table_name}. Add it to TABLE_ROUTING.")
        return db_name
    
    def get_db_path(self, db_name: str) -> Path:
        """Get the full path for a database."""
        return self.db_dir / db_name
    
    @contextmanager
    def connection(self, table_name: str):
        """
        Get a connection to the database containing the specified table.
        
        Usage:
            with router.connection("miner_readings") as conn:
                conn.execute("SELECT * FROM miner_readings")
        """
        db_name = self.get_db_for_table(table_name)
        db_path = self.get_db_path(db_name)
        
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    @contextmanager
    def db_connection(self, db_name: str):
        """
        Get a connection to a specific database by name.
        
        Usage:
            with router.db_connection("operational.db") as conn:
                conn.execute("SELECT * FROM scans")
        """
        if db_name not in DATABASES:
            raise ValueError(f"Unknown database: {db_name}")
        
        db_path = self.get_db_path(db_name)
        
        conn = sqlite3.connect(str(db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def execute_on_table(self, table_name: str, query: str, params: tuple = ()):
        """Execute a query on the database containing the specified table."""
        with self.connection(table_name) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    
    def execute_on_db(self, db_name: str, query: str, params: tuple = ()):
        """Execute a query on a specific database."""
        with self.db_connection(db_name) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()


# Global router instance
_router: Optional[DatabaseRouter] = None


def get_router() -> DatabaseRouter:
    """Get the global DatabaseRouter instance."""
    global _router
    if _router is None:
        _router = DatabaseRouter()
    return _router


# Convenience functions
def get_connection(table_name: str):
    """Get a connection context manager for a table."""
    return get_router().connection(table_name)


def get_db_connection(db_name: str):
    """Get a connection context manager for a database."""
    return get_router().db_connection(db_name)


if __name__ == "__main__":
    # Test the router
    router = DatabaseRouter()
    
    print("Database Router Test")
    print("=" * 40)
    
    for table, db in sorted(TABLE_ROUTING.items()):
        print(f"  {table} -> {db}")
    
    print()
    print("Testing connections...")
    
    for db_name in DATABASES:
        try:
            with router.db_connection(db_name) as conn:
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
                table_names = [t[0] for t in tables if not t[0].startswith('sqlite_')]
                print(f"  {db_name}: {len(table_names)} tables - {', '.join(table_names)}")
        except Exception as e:
            print(f"  {db_name}: ERROR - {e}")
    
    print()
    print("Router ready!")
