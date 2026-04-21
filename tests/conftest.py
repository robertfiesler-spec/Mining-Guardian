"""
Pytest fixtures for Mining Guardian tests.
"""
import os
import sys
import pytest
import tempfile

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)

@pytest.fixture  
def mock_config():
    """Return a mock GuardianConfig for testing."""
    from core.models import GuardianConfig
    return GuardianConfig(
        ams_base_url="https://test.bixbit.io/api/v1",
        ams_email="test@test.com",
        ams_password="testpass",
        ams_workspace_id=99999,
        openclaw_webhook_url="https://test.webhook",
        slack_webhook_url="https://hooks.slack.com/test",
        slack_bot_token="xoxb-test",
        dry_run=True,
        collect_logs=False,
        scan_interval_seconds=300
    )

@pytest.fixture
def sample_miner_data():
    """Return sample miner data for testing."""
    return {
        "id": 12345,
        "ip": "192.168.188.100",
        "model": "Antminer S19JPro",
        "status": "online",
        "pool_hashrate": 104000000000,
        "temp_max": 72,
        "chains": [
            {"id": 0, "hashrate": 35000000000, "chips": 126, "temp": 70},
            {"id": 1, "hashrate": 35000000000, "chips": 126, "temp": 71},
            {"id": 2, "hashrate": 34000000000, "chips": 126, "temp": 72}
        ]
    }
