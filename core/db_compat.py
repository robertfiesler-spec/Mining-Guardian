#!/usr/bin/env python3
"""
Database Compatibility Layer for Mining Guardian
=================================================
This module provides backward compatibility for code that still uses:
    sqlite3.connect('guardian.db')

It intercepts connections and routes queries to the correct split database
based on the table being accessed.

Usage:
    # Old code (still works):
    conn = sqlite3.connect('guardian.db')
    conn.execute('SELECT * FROM miner_readings')
    
    # This module automatically routes to timeseries.db

Created: April 22, 2026
"""

import sqlite3
import logging
import re
from pathlib import Path
from typing import Optional, Set

from core.database_router import get_router, TABLE_ROUTING, DATABASES

logger = logging.getLogger(__name__)

# Base directory for databases
DB_DIR = Path(__file__).parent.parent / "databases"
LEGACY_DB = Path(__file__).parent.parent / "guardian.db"


def extract_table_from_query(query: str) -> Optional[str]:
    """Extract the primary table name from a SQL query."""
    query_upper = query.upper().strip()
    
    # Common patterns
    patterns = [
        r'FROM\s+([\w]+)',           # SELECT ... FROM table
        r'INTO\s+([\w]+)',           # INSERT INTO table
        r'UPDATE\s+([\w]+)',         # UPDATE table
        r'DELETE\s+FROM\s+([\w]+)', # DELETE FROM table
        r'TABLE\s+([\w]+)',          # CREATE TABLE, DROP TABLE
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_upper)
        if match:
            table = match.group(1).lower()
            if table in TABLE_ROUTING:
                return table
    
    return None


class RoutingConnection:
    """
    A connection wrapper that routes queries to the correct split database.
    
    This allows old code using sqlite3.connect('guardian.db') to continue
    working while transparently using the split databases.
    """
    
    def __init__(self, legacy_path: str = None):
        self._router = get_router()
        self._connections = {}
        self._current_db = None
        self.row_factory = None
        
    def _get_conn_for_table(self, table_name: str) -> sqlite3.Connection:
        """Get or create connection for a specific table's database."""
        db_name = TABLE_ROUTING.get(table_name)
        if not db_name:
            # Unknown table - fall back to operational.db
            db_name = "operational.db"
            logger.warning(f"Unknown table '{table_name}', routing to {db_name}")
        
        if db_name not in self._connections:
            db_path = DB_DIR / db_name
            conn = sqlite3.connect(str(db_path), timeout=30)
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=30000')
            if self.row_factory:
                conn.row_factory = self.row_factory
            self._connections[db_name] = conn
        
        self._current_db = db_name
        return self._connections[db_name]
    
    def _get_conn_for_query(self, query: str) -> sqlite3.Connection:
        """Analyze query and return the appropriate connection."""
        table = extract_table_from_query(query)
        if table:
            return self._get_conn_for_table(table)
        
        # Can't determine table - use operational as default
        return self._get_conn_for_table('scans')
    
    def execute(self, query: str, params=None):
        """Execute a query, routing to the correct database."""
        conn = self._get_conn_for_query(query)
        if self.row_factory:
            conn.row_factory = self.row_factory
        if params:
            return conn.execute(query, params)
        return conn.execute(query)
    
    def executemany(self, query: str, params_list):
        """Execute many queries, routing to the correct database."""
        conn = self._get_conn_for_query(query)
        return conn.executemany(query, params_list)
    
    def executescript(self, script: str):
        """Execute a script - routes to operational.db by default."""
        conn = self._get_conn_for_table('scans')
        return conn.executescript(script)
    
    def commit(self):
        """Commit all open connections."""
        for conn in self._connections.values():
            conn.commit()
    
    def rollback(self):
        """Rollback all open connections."""
        for conn in self._connections.values():
            conn.rollback()
    
    def close(self):
        """Close all open connections."""
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
    
    def cursor(self):
        """Return a cursor for the default database."""
        conn = self._get_conn_for_table('scans')
        return conn.cursor()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect_routed(db_path: str = None, **kwargs) -> RoutingConnection:
    """
    Create a routing connection that mimics sqlite3.connect() but routes
    queries to the appropriate split database.
    
    This is a drop-in replacement for sqlite3.connect('guardian.db').
    """
    return RoutingConnection(db_path)


# For direct imports
def get_db_connection():
    """Get a routing connection for use with split databases."""
    return RoutingConnection()


if __name__ == "__main__":
    # Test the compatibility layer
    print("Testing DB Compatibility Layer")
    print("=" * 40)
    
    # Test query table extraction
    test_queries = [
        "SELECT * FROM miner_readings WHERE id > 100",
        "INSERT INTO action_audit_log (timestamp) VALUES (?)",
        "UPDATE pending_approvals SET status = 'DONE'",
        "DELETE FROM known_dead_boards WHERE id = 5",
        "SELECT m.*, c.* FROM miner_readings m JOIN chain_readings c",
    ]
    
    for query in test_queries:
        table = extract_table_from_query(query)
        db = TABLE_ROUTING.get(table, "unknown") if table else "unknown"
        print(f"  Query: {query[:50]}...")
        print(f"  -> Table: {table}, DB: {db}")
        print()
    
    # Test actual connections
    print("Testing connections...")
    with RoutingConnection() as conn:
        conn.row_factory = sqlite3.Row
        
        # This should route to timeseries.db
        result = conn.execute("SELECT COUNT(*) FROM miner_readings").fetchone()
        print(f"  miner_readings count: {result[0]:,}")
        
        # This should route to operational.db
        result = conn.execute("SELECT COUNT(*) FROM scans").fetchone()
        print(f"  scans count: {result[0]:,}")
        
        # This should route to audit.db
        result = conn.execute("SELECT COUNT(*) FROM action_audit_log").fetchone()
        print(f"  action_audit_log count: {result[0]:,}")
    
    print()
    print("Compatibility layer ready!")
