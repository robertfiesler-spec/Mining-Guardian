"""
Big Star BlockChain AV-2 Plant client for S19J Pro Container HVAC.
Simple stub that returns placeholder data until WebSocket scraping is implemented.
"""
from typing import Optional, Dict
import warnings
from urllib3.exceptions import InsecureRequestWarning

warnings.filterwarnings("ignore", category=InsecureRequestWarning)

class AV2PlantClient:
    """
    Stub client for AV-2 Plant.
    Returns None for all values - HVAC client will fall back to database.
    TODO: Implement WebSocket polling for live data.
    """
    
    def __init__(self, ip: str = "192.168.189.235", username: str = "BigStar", password: str = "BigSt@r2020"):
        self.ip = ip
        self.base_url = f"https://{ip}"
        self.auth = (username, password)
    
    def get_temps(self) -> Dict[str, Optional[float]]:
        """
        Returns None for all values to trigger database fallback.
        When Mac collects HVAC data and uploads to DB, scans will show it.
        """
        return {
            "supply_temp": None,
            "return_temp": None,
            "outside_air": None,
            "container_temp": None,
            "error": "WebSocket polling not yet implemented - using DB fallback"
        }


def test_client():
    """Test the AV-2 Plant client."""
    client = AV2PlantClient()
    data = client.get_temps()
    print("AV-2 Plant Data (stub - returns None for DB fallback):")
    for key, val in data.items():
        print(f"  {key}: {val}")
    return data


if __name__ == "__main__":
    test_client()
