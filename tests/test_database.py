"""
Tests for the GuardianDB database layer.
Created April 21, 2026 as part of Phase 4 testing infrastructure.
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime

# Add parent directory to path for imports
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import GuardianDB


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = GuardianDB(db_path=path)
    yield db
    os.unlink(path)


class TestGuardianDB:
    """Tests for GuardianDB class."""

    def test_init_creates_tables(self, temp_db):
        """Test that database initialization creates required tables."""
        with temp_db._connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
        
        # Check for essential tables
        assert "scans" in tables
        assert "miner_readings" in tables
        assert "action_audit_log" in tables
        assert "pending_approvals" in tables

    def test_save_scan(self, temp_db):
        """Test saving a scan with miners."""
        miners = [
            {
                "miner_id": "12345",
                "ip": "192.168.188.10",
                "model": "Antminer S19JPro",
                "status": "ONLINE",
                "hashrate": 104000,
                "temp_chip": 72.0,
            }
        ]
        issues = []
        
        scan_id = temp_db.save_scan(miners, issues)
        
        assert scan_id is not None
        assert scan_id > 0

    def test_get_audit_log_empty(self, temp_db):
        """Test getting audit log when empty."""
        result = temp_db.get_audit_log()
        assert result == []

    def test_log_action(self, temp_db):
        """Test logging an action to the audit log."""
        temp_db.log_action(
            miner_id="12345",
            ip="192.168.188.10",
            model="Antminer S19JPro",
            problem="LOW_HASHRATE",
            action_taken="RESTART",
            decision="APPROVED",
            approved_by="Bobby",
            slack_user_id="U07AGTT8CLD",
            scan_id=1,
            notes="Test action"
        )
        
        result = temp_db.get_audit_log()
        assert len(result) == 1
        assert result[0]["miner_id"] == "12345"
        assert result[0]["action_taken"] == "RESTART"
        assert result[0]["decision"] == "APPROVED"

    def test_latest_scan_id_empty(self, temp_db):
        """Test getting latest scan ID when no scans exist."""
        result = temp_db._latest_scan_id()
        assert result is None

    def test_latest_scan_id_after_scan(self, temp_db):
        """Test getting latest scan ID after saving a scan."""
        miners = [{"miner_id": "123", "status": "ONLINE"}]
        scan_id = temp_db.save_scan(miners, [])
        
        result = temp_db._latest_scan_id()
        assert result == scan_id


class TestDatabaseConnection:
    """Tests for database connection handling."""

    def test_wal_mode_enabled(self, temp_db):
        """Test that WAL journal mode is enabled."""
        with temp_db._connect() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
        assert mode.lower() == "wal"

    def test_busy_timeout_set(self, temp_db):
        """Test that busy timeout is configured."""
        with temp_db._connect() as conn:
            cursor = conn.execute("PRAGMA busy_timeout")
            timeout = cursor.fetchone()[0]
        assert timeout == 30000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
