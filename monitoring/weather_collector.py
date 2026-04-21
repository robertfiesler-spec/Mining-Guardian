"""
Weather Collector
Extracted from mining_guardian.py on April 21, 2026

Collects ambient temperature and humidity from Open-Meteo API.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

class WeatherCollector:
    API_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, latitude: float = 32.7555, longitude: float = -97.3308):
        self.latitude  = latitude
        self.longitude = longitude

    def fetch(self) -> Optional[Dict[str, Any]]:
        """Fetch current conditions and today's forecast from Open-Meteo."""
        try:
            resp = requests.get(self.API_URL, params={
                "latitude":         self.latitude,
                "longitude":        self.longitude,
                "current":          ["temperature_2m", "relative_humidity_2m", "apparent_temperature"],
                "daily":            ["temperature_2m_max", "temperature_2m_min",
                                     "relative_humidity_2m_max", "relative_humidity_2m_min"],
                "temperature_unit": "fahrenheit",
                "timezone":         "America/Chicago",
                "forecast_days":    1,
            }, timeout=10)
            resp.raise_for_status()
            data    = resp.json()
            current = data.get("current", {})
            daily   = data.get("daily", {})
            return {
                "temp_f":       current.get("temperature_2m"),
                "humidity_pct": current.get("relative_humidity_2m"),
                "feels_like_f": current.get("apparent_temperature"),
                "temp_high_f":  daily.get("temperature_2m_max", [None])[0],
                "temp_low_f":   daily.get("temperature_2m_min", [None])[0],
                "humidity_max": daily.get("relative_humidity_2m_max", [None])[0],
                "humidity_min": daily.get("relative_humidity_2m_min", [None])[0],
            }
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
            return None


