"""
Big Star BlockChain AV-2 Plant client for S19J Pro Container HVAC.
Uses Distech Eclypse dgapi subscription-based polling.

API discovered via Chrome DevTools:
- Endpoint: POST https://{ip}/eclypse/dgapi
- Auth: Session-based with dguser/session endpoint
- Data: Subscription model returns real-time sensor values
"""
import os
import json
import logging
import requests
import warnings
from typing import Optional, Dict, Any
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime

warnings.filterwarnings("ignore", category=InsecureRequestWarning)
logger = logging.getLogger(__name__)


class AV2PlantClient:
    """
    Client for AV-2 Plant HVAC via Distech Eclypse dgapi.
    
    Data paths discovered:
    - /Data/Plant/OAT              - Outside Air Temp (°F)
    - /Data/Plant/ContainerSpaceTemp - Container Ceiling Temp (°F)  
    - /Data/Plant/CDWST            - Condenser Water Supply Temp (°F)
    - /Data/Plant/CDWRT            - Condenser Water Return Temp (°F)
    - /Data/Plant/CWP1_Fdbk        - CW Pump 1 Speed Feedback (%)
    - /Data/Plant/CWP2_Fdbk        - CW Pump 2 Speed Feedback (%)
    - /Data/Plant/CT1VSDFdbk       - Cooling Tower Fan 1 VSD Feedback (%)
    """

    # Data paths to subscribe to
    DATA_PATHS = [
        "/Data/Plant/OAT",
        "/Data/Plant/ContainerSpaceTemp",
        "/Data/Plant/CDWST",
        "/Data/Plant/CDWRT",
        "/Data/Plant/CWP1_Fdbk",
        "/Data/Plant/CWP2_Fdbk",
        "/Data/Plant/CT1VSDFdbk",
    ]

    def __init__(self, ip: str = "192.168.189.235",
                 username: str = "", password: str = ""):
        username = username or os.getenv("AV2_PLANT_USER", "BigStar")
        password = password or os.getenv("AV2_PLANT_PASSWORD", "BigSt@r2020")
        self.ip = ip
        self.base_url = f"https://{ip}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = False
        self.timeout = 10
        self._subscription_id: Optional[str] = None

    def _login(self) -> bool:
        """Establish session with the Eclypse controller."""
        try:
            # Get session
            resp = self.session.get(
                f"{self.base_url}/eclypse/dguser/session",
                auth=(self.username, self.password),
                timeout=self.timeout
            )
            if resp.status_code == 200:
                logger.debug("AV2 Plant: Session established")
                return True
            else:
                logger.warning("AV2 Plant: Session failed - %s", resp.status_code)
                return False
        except Exception as e:
            logger.warning("AV2 Plant: Login error - %s", e)
            return False

    def _create_subscription(self) -> Optional[str]:
        """Create a subscription for the data points we want."""
        try:
            # Generate a subscription ID
            import hashlib
            import time
            sub_id = "DG" + hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
            
            # Build subscription request
            subscribe_requests = []
            for path in self.DATA_PATHS:
                subscribe_requests.append({
                    "method": "Subscribe",
                    "path": path,
                    "name": sub_id
                })
            
            payload = {
                "requests": subscribe_requests,
                "subscription": sub_id
            }
            
            resp = self.session.post(
                f"{self.base_url}/eclypse/dgapi",
                json=payload,
                auth=(self.username, self.password),
                timeout=self.timeout
            )
            
            if resp.status_code == 200:
                self._subscription_id = sub_id
                logger.debug("AV2 Plant: Subscription created - %s", sub_id)
                return sub_id
            else:
                logger.warning("AV2 Plant: Subscription failed - %s", resp.status_code)
                return None
        except Exception as e:
            logger.warning("AV2 Plant: Subscription error - %s", e)
            return None

    def _poll_subscription(self) -> Dict[str, Any]:
        """Poll the subscription for current values."""
        if not self._subscription_id:
            if not self._login():
                return {}
            if not self._create_subscription():
                return {}
        
        try:
            payload = {
                "requests": [],
                "subscription": self._subscription_id
            }
            
            resp = self.session.post(
                f"{self.base_url}/eclypse/dgapi",
                json=payload,
                auth=(self.username, self.password),
                timeout=self.timeout
            )
            
            if resp.status_code == 200:
                data = resp.json()
                values = {}
                
                # Parse response
                if "responses" in data and len(data["responses"]) > 0:
                    for item in data["responses"]:
                        if "values" in item:
                            for v in item["values"]:
                                values[v["path"]] = {
                                    "value": v.get("value"),
                                    "unit": v.get("unit"),
                                    "formatted": v.get("formatted"),
                                    "status": v.get("status"),
                                    "lastUpdate": v.get("lastUpdate")
                                }
                
                return values
            else:
                # Reset subscription on error
                self._subscription_id = None
                return {}
        except Exception as e:
            logger.warning("AV2 Plant: Poll error - %s", e)
            self._subscription_id = None
            return {}

    def get_temps(self) -> Dict[str, Optional[float]]:
        """
        Get temperature readings from AV-2 Plant.
        
        Returns dict with keys:
        - supply_temp: Condenser Water Supply Temp (°F)
        - return_temp: Condenser Water Return Temp (°F)
        - outside_air: Outside Air Temp (°F)
        - container_temp: Container Ceiling Temp (°F)
        - cwp1_speed: CW Pump 1 Speed (%)
        - cwp2_speed: CW Pump 2 Speed (%)
        - ct_fan_speed: Cooling Tower Fan Speed (%)
        - timestamp: ISO timestamp of reading
        """
        result = {
            "supply_temp": None,
            "return_temp": None,
            "outside_air": None,
            "container_temp": None,
            "cwp1_speed": None,
            "cwp2_speed": None,
            "ct_fan_speed": None,
            "timestamp": None,
            "error": None
        }
        
        try:
            values = self._poll_subscription()
            
            if not values:
                result["error"] = "No data from AV2 Plant API"
                return result
            
            # Map paths to result keys
            path_map = {
                "/Data/Plant/CDWST": "supply_temp",
                "/Data/Plant/CDWRT": "return_temp",
                "/Data/Plant/OAT": "outside_air",
                "/Data/Plant/ContainerSpaceTemp": "container_temp",
                "/Data/Plant/CWP1_Fdbk": "cwp1_speed",
                "/Data/Plant/CWP2_Fdbk": "cwp2_speed",
                "/Data/Plant/CT1VSDFdbk": "ct_fan_speed",
            }
            
            for path, key in path_map.items():
                if path in values and values[path].get("value") is not None:
                    result[key] = round(values[path]["value"], 1)
            
            result["timestamp"] = datetime.now().isoformat()
            return result
            
        except Exception as e:
            result["error"] = str(e)
            logger.warning("AV2 Plant: get_temps error - %s", e)
            return result

    def get_all_data(self) -> Dict[str, Any]:
        """Get all available data with full metadata."""
        return self._poll_subscription()


def test_client():
    """Test the AV-2 Plant client."""
    logging.basicConfig(level=logging.DEBUG)
    client = AV2PlantClient()
    
    print("Testing AV-2 Plant Client...")
    print(f"Endpoint: https://{client.ip}/eclypse/dgapi")
    print()
    
    data = client.get_temps()
    print("Temperature Data:")
    for key, val in data.items():
        print(f"  {key}: {val}")
    
    return data


if __name__ == "__main__":
    test_client()
