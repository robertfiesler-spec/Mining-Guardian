#!/usr/bin/env python3
"""
Database Helper for Mining Guardian
====================================
Simple helper to get database connections.

This replaces direct sqlite3.connect() calls with routing-aware connections.

Usage:
    from core.db_helper import get_db, get_db_for_table
    
    # Get a routing connection (auto-routes based on query)
    with get_db() as conn:
        conn.execute('SELECT * FROM miner_readings')
    
    # Get connection for a specific table
    with get_db_for_table('miner_readings') as conn:
        conn.execute('SELECT * FROM miner_readings')

Created: April 22, 2026
"""

import sqlite3
from pathlib import Path
from contextlib import contextmanager

# Import router
try:
    from core.database_router import get_router, get_connection, get_db_connection
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from core.database_router import get_router, get_connection, get_db_connection

# Legacy path for backward compatibility
DB_PATH = Path(__file__).parent.parent / "guardian.db"


def get_db():
    """
    Get a routing connection that auto-routes queries to the correct database.
    
    Usage:
        from core.db_helper import get_db
        
        with get_db() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM miner_readings LIMIT 10').fetchall()
    """
    from core.db_compat import RoutingConnection
    return RoutingConnection()


def get_db_for_table(table_name: str):
    """
    Get a connection to the database containing the specified table.
    
    Usage:
        from core.db_helper import get_db_for_table
        
        with get_db_for_table('miner_readings') as conn:
            rows = conn.execute('SELECT COUNT(*) FROM miner_readings').fetchall()
    """
    return get_connection(table_name)


def get_legacy_db():
    """
    Get a direct connection to the legacy guardian.db.
    Use only for migration or compatibility testing.
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA busy_timeout=30000')
    conn.row_factory = sqlite3.Row
    return conn


# For maximum backward compatibility, provide a connect() function
def connect(db_path: str = None, **kwargs):
    """
    Drop-in replacement for sqlite3.connect().
    Routes queries to the appropriate split database.
    """
    from core.db_compat import RoutingConnection
    return RoutingConnection(db_path)


if __name__ == "__main__":
    print("Testing db_helper...")
    
    # Test routing connection
    with get_db() as conn:
        conn.row_factory = sqlite3.Row
        count = conn.execute('SELECT COUNT(*) FROM miner_readings').fetchone()[0]
        print(f"miner_readings: {count:,} rows")
    
    # Test table-specific connection  
    with get_db_for_table('action_audit_log') as conn:
        count = conn.execute('SELECT COUNT(*) FROM action_audit_log').fetchone()[0]
        print(f"action_audit_log: {count:,} rows")
    
    print("db_helper ready!")
