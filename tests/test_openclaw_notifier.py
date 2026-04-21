"""
Tests for OpenClawNotifier - OpenClaw webhook client.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifiers.openclaw_notifier import OpenClawNotifier


class TestOpenClawNotifierInit:
    """Test OpenClawNotifier initialization."""
    
    def test_init_with_webhook_url(self):
        """Test notifier initializes with webhook URL."""
        url = 'https://test.openclaw.webhook'
        notifier = OpenClawNotifier(webhook_url=url)
        assert notifier.webhook_url == url
        
    def test_init_with_none_url(self):
        """Test notifier handles None URL."""
        notifier = OpenClawNotifier(webhook_url=None)
        assert notifier.webhook_url is None


class TestOpenClawNotifierMethods:
    """Test OpenClawNotifier methods."""
    
    def test_has_send_scan_method(self):
        """Test that notifier has send_scan method."""
        notifier = OpenClawNotifier(webhook_url='https://test.url')
        assert hasattr(notifier, 'send_scan')
        
    def test_instance_creation(self):
        """Test notifier can be instantiated."""
        notifier = OpenClawNotifier(webhook_url='https://test.url')
        assert notifier is not None
