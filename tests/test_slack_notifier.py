"""
Tests for SlackNotifier - Slack messaging.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifiers.slack_notifier import SlackNotifier


class TestSlackNotifierInit:
    """Test SlackNotifier initialization."""
    
    def test_init_with_webhook(self):
        """Test notifier initializes with webhook URL."""
        webhook = "https://hooks.slack.com/test"
        notifier = SlackNotifier(webhook_url=webhook)
        assert notifier.webhook_url == webhook
        
    def test_init_with_bot_token(self):
        """Test notifier initializes with bot token."""
        token = "xoxb-test-token"
        notifier = SlackNotifier(webhook_url=None, bot_token=token)
        assert notifier.bot_token == token
        
    def test_init_with_channel(self):
        """Test notifier initializes with channel ID."""
        channel = "C12345"
        notifier = SlackNotifier(webhook_url=None, channel_id=channel)
        assert notifier.channel_id == channel


class TestSlackNotifierFormatting:
    """Test SlackNotifier message formatting."""
    
    def test_instance_creation(self):
        """Test that SlackNotifier can be instantiated."""
        notifier = SlackNotifier(webhook_url="https://test.hook")
        assert notifier is not None
        
    def test_handles_none_webhook(self):
        """Test that None webhook is handled."""
        notifier = SlackNotifier(webhook_url=None)
        assert notifier.webhook_url is None
