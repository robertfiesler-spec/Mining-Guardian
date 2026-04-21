"""
Tests for AMSClient - the BiXBiT AMS API client.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.ams_client import AMSClient


class TestAMSClientInit:
    """Test AMSClient initialization."""
    
    def test_init_with_config(self, mock_config):
        """Test client initializes with config."""
        client = AMSClient(mock_config)
        assert client.base_url == "https://test.bixbit.io/api/v1"
        assert client.session is not None
        

class TestAMSClientParsing:
    """Test AMSClient data parsing."""
    
    def test_parse_miner_status_online(self, mock_config, sample_miner_data):
        """Test parsing online miner status."""
        client = AMSClient(mock_config)
        assert sample_miner_data['status'] == 'online'
        assert len(sample_miner_data['chains']) == 3
        
    def test_parse_miner_temp(self, mock_config, sample_miner_data):
        """Test parsing miner temperature."""
        max_temp = max(c['temp'] for c in sample_miner_data['chains'])
        assert max_temp == 72
        assert max_temp < 84
