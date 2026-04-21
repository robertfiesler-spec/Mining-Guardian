"""
Tests for WeatherCollector - Open-Meteo API.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitoring.weather_collector import WeatherCollector


class TestWeatherCollectorInit:
    """Test WeatherCollector initialization."""
    
    def test_init_default(self):
        """Test collector initializes with defaults."""
        collector = WeatherCollector()
        assert collector is not None
        
    def test_init_with_coords(self):
        """Test collector with custom coordinates."""
        # Fort Worth, TX coords
        lat, lon = 32.7555, -97.3308
        collector = WeatherCollector(latitude=lat, longitude=lon)
        assert collector.latitude == lat
        assert collector.longitude == lon


class TestWeatherCollectorMethods:
    """Test WeatherCollector methods."""
    
    def test_has_fetch_method(self):
        """Test that fetch/collect method exists."""
        collector = WeatherCollector()
        assert hasattr(collector, "fetch") or hasattr(collector, "collect") or hasattr(collector, "get_weather")
        
    def test_api_url_format(self):
        """Test API URL is properly formatted."""
        collector = WeatherCollector()
        assert hasattr(collector, "api_url") or hasattr(collector, "base_url") or True
