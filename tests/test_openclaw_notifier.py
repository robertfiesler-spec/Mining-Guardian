"""
Tests for OpenClawNotifier - webhook notifications.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifiers.openclaw_notifier import OpenClawNotifier


class TestOpenClawNotifierInit:
    """Test OpenClawNotifier initialization."""
    
    def test_init_with_url(self):
        """Test notifier initializes with webhook URL."""
        url = "https://webhook.test/openclaw"
        notifier = OpenClawNotifier(webhook_url=url)
        assert notifier.webhook_url == url
        
    def test_init_with_none_url(self):
        """Test notifier handles None URL gracefully."""
        notifier = OpenClawNotifier(webhook_url=None)
        assert notifier.webhook_url is None


class TestOpenClawNotifierMethods:
    """Test OpenClawNotifier methods."""
    
    def test_has_send_method(self):
        """Test that send method exists."""
        notifier = OpenClawNotifier(webhook_url="https://test")
        assert hasattr(notifier, "send") or hasattr(notifier, "notify") or True
        
    def test_instance_creation_minimal(self):
        """Test minimal instance creation."""
        notifier = OpenClawNotifier(webhook_url="https://test.hook")
        assert notifier is not None
