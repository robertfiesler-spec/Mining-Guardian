"""
Tests for Dashboard API endpoints.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDashboardAPIImports:
    """Test Dashboard API can be imported."""
    
    def test_import_dashboard_api(self):
        """Test dashboard_api module imports without error."""
        from api import dashboard_api
        assert dashboard_api is not None
        
    def test_has_app_object(self):
        """Test dashboard_api has FastAPI app object."""
        from api import dashboard_api
        assert hasattr(dashboard_api, 'app')


class TestDashboardAPIEndpoints:
    """Test Dashboard API endpoint definitions."""
    
    def test_fleet_latest_route_exists(self):
        """Test /fleet/latest route is defined."""
        from api.dashboard_api import app
        routes = [r.path for r in app.routes]
        assert '/fleet/latest' in routes
        
    def test_miners_flagged_route_exists(self):
        """Test /miners/flagged route is defined."""
        from api.dashboard_api import app
        routes = [r.path for r in app.routes]
        assert '/miners/flagged' in routes
        
    def test_temps_history_route_exists(self):
        """Test /temps/history route is defined."""
        from api.dashboard_api import app
        routes = [r.path for r in app.routes]
        assert '/temps/history' in routes


class TestDashboardAPIRateLimiting:
    """Test rate limiting is configured."""
    
    def test_limiter_exists(self):
        """Test rate limiter is configured."""
        from api.dashboard_api import limiter
        assert limiter is not None
