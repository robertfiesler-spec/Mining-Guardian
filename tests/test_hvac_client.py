"""
Tests for HVACClient - Distech Eclypse BACnet client.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clients.hvac_client import HVACClient, SYSTEMS


class TestHVACClientInit:
    """Test HVACClient initialization."""
    
    def test_init_warehouse_default(self):
        """Test client initializes with warehouse (default)."""
        client = HVACClient()
        assert client.system_id == 'warehouse'
        assert client.ip == '192.168.188.235'
        
    def test_init_container_system(self):
        """Test client initializes with container system."""
        client = HVACClient(system_id='s19jpro')
        assert client.system_id == 's19jpro'
        assert client.ip == '192.168.189.235'
        
    def test_init_invalid_system_raises(self):
        """Test client raises error for invalid system."""
        with pytest.raises(ValueError) as exc_info:
            HVACClient(system_id='invalid_system')
        assert 'Unknown HVAC system' in str(exc_info.value)


class TestHVACClientConfiguration:
    """Test HVACClient configuration."""
    
    def test_systems_dict_has_warehouse(self):
        """Test SYSTEMS has warehouse configuration."""
        assert 'warehouse' in SYSTEMS
        assert 'ip' in SYSTEMS['warehouse']
        
    def test_systems_dict_has_container(self):
        """Test SYSTEMS has container configuration."""
        assert 's19jpro' in SYSTEMS
        assert 'ip' in SYSTEMS['s19jpro']
        
    def test_base_url_format(self):
        """Test base URL is properly formatted."""
        client = HVACClient()
        assert 'https://' in client.base_url
        assert '/api/rest/v1/protocols/bacnet' in client.base_url
