"""
Tests for WeatherCollector - Open-Meteo API client.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from monitoring.weather_collector import WeatherCollector


class TestWeatherCollectorInit:
    """Test WeatherCollector initialization."""
    
    def test_init_with_defaults(self):
        """Test collector initializes with default Fort Worth coords."""
        collector = WeatherCollector()
        assert collector is not None
        assert collector.latitude == 32.7555
        assert collector.longitude == -97.3308
        
    def test_init_with_custom_coords(self):
        """Test collector initializes with custom coordinates."""
        collector = WeatherCollector(latitude=32.7767, longitude=-96.7970)
        assert collector.latitude == 32.7767
        assert collector.longitude == -96.7970


class TestWeatherCollectorMethods:
    """Test WeatherCollector methods."""
    
    def test_has_fetch_method(self):
        """Test that collector has fetch method."""
        collector = WeatherCollector()
        assert hasattr(collector, 'fetch')
        
    def test_coordinates_are_floats(self):
        """Test coordinates are numeric."""
        collector = WeatherCollector(latitude=32.7767, longitude=-96.7970)
        assert isinstance(collector.latitude, (int, float))
        assert isinstance(collector.longitude, (int, float))
