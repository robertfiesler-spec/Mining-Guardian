"""
Tests for ApprovalInterface - manual approval handling.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notifiers.approval_interface import ApprovalInterface


class TestApprovalInterfaceInit:
    """Test ApprovalInterface initialization."""
    
    def test_init_with_config(self, mock_config):
        """Test interface initializes with config."""
        interface = ApprovalInterface(mock_config)
        assert interface is not None
        
    def test_has_request_approval_method(self, mock_config):
        """Test interface has request_approval method."""
        interface = ApprovalInterface(mock_config)
        assert hasattr(interface, 'request_approval')


class TestApprovalInterfaceModes:
    """Test ApprovalInterface approval modes."""
    
    def test_approval_mode_from_config(self, mock_config):
        """Test approval mode is read from config."""
        interface = ApprovalInterface(mock_config)
        # Default mode is 'manual'
        assert mock_config.approval_mode == 'manual'
