#!/usr/bin/env python3
"""S21 Immersion Firmware Benchmark Test — Data Collector
=======================================================
Collects hourly data for firmware performance testing.

Test Phases:
  Phase 1: 24 hours @ Stock
  Phase 2: 12 hours @ +10% OC
  Phase 3: 12 hours @ +25% OC  
  Phase 4: 12 hours @ Max OC

Data Sources:
  - AMS API: Hashrate, chip temp, board temps, pool stats, HW errors
  - Tank B100 API (192.168.188.20): Per-port kW (no auth needed)
  - HVAC API (192.168.188.235): Outside temp, supply/return water
  
Output: CSV file for Google Sheets import
"""
import sys
import os
import json
import time
import logging
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import requests
import urllib3
urllib3.disable_warnings()

# Add parent to path for imports
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from core.mining_guardian import GuardianConfig, AMSClient

# ── Configuration ────────────────────────────────────────────────────────────

# Test miners - miner IDs mapped to tank ports
TEST_MINERS = {
    "192.168.188.22": {"miner_id": 64345, "name": "S21_Imm_22", "tank_port": 19, "stock_ths": 208, "max_ths": 360},
    "192.168.188.23": {"miner_id": 64346, "name": "S21_Imm_23", "tank_port": 20, "stock_ths": 217, "max_ths": 347},
}

# Infrastructure
TANK_IP = "192.168.188.20"
HVAC_IP = "192.168.188.235"
HVAC_USER = "BigStar"
HVAC_PASS = "BigSt@r2020"

# Test phases
PHASES = {
    1: {"name": "Stock", "duration_hours": 24},
    2: {"name": "+10% OC", "duration_hours": 12},
    3: {"name": "+25% OC", "duration_hours": 12},
    4: {"name": "Max OC", "duration_hours": 12},
}

OUTPUT_CSV = _ROOT / "tests" / "s21_imm_benchmark.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("benchmark")


@dataclass
class HourlyReading:
    timestamp: str
    phase: int
    phase_name: str
    hour_in_phase: int
    miner_ip: str
    miner_name: str
    hashrate_ths: float
    hashrate_pct: float
    rated_ths: float
    miner_power_w: float
    pdu_port_power_w: float
    chip_temp_c: float
    board0_temp_c: float
    board1_temp_c: float
    board2_temp_c: float
    supply_water_c: float
    return_water_c: float
    outside_temp_c: float
    pool_accepted: int
    pool_rejected: int
    rejection_rate_pct: float
    hw_errors: int
    uptime_hours: float
    efficiency_jth: float


# ── Tank B100 API ────────────────────────────────────────────────────────────

def get_tank_port_power(port: int) -> Optional[float]:
    """Get power (in Watts) for a specific tank port."""
    try:
        r = requests.get(f"http://{TANK_IP}/api/device-status", timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        ports = data.get("power_ports", [])
        if port <= len(ports):
            p = ports[port - 1]  # 0-indexed
            power_kw = (float(p.get("power_a", 0) or 0) +
                       float(p.get("power_b", 0) or 0) +
                       float(p.get("power_c", 0) or 0))
            return power_kw * 1000  # Convert to Watts
        return None
    except Exception as e:
        logger.error("Tank API error: %s", e)
        return None


def get_tank_temps() -> Dict[str, float]:
    """Get tank inlet/outlet temps."""
    try:
        r = requests.get(f"http://{TANK_IP}/api/device-status", timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        tank = data.get("tank", {})
        return {
            "tank_in_c": float(tank.get("in_temp", 0) or 0),
            "tank_out_c": float(tank.get("out_temp", 0) or 0),
        }
    except Exception as e:
        logger.error("Tank temp error: %s", e)
        return {}


# ── HVAC API ─────────────────────────────────────────────────────────────────

def get_hvac_data() -> Dict[str, float]:
    """Get HVAC data (supply/return water, outside temp)."""
    result = {"supply_water_c": 0.0, "return_water_c": 0.0, "outside_temp_c": 0.0}
    try:
        # Get analog inputs (temps)
        r = requests.get(
            f"https://{HVAC_IP}/api/rest/v1/protocols/bacnet/local/objects/analog-input",
            auth=(HVAC_USER, HVAC_PASS), verify=False, timeout=15, allow_redirects=True
        )
        if r.status_code == 200:
            for obj in r.json():
                oid = str(obj.get("object-identifier", "")).split(",")[-1] if "," in str(obj.get("object-identifier", "")) else ""
                val = float(obj.get("present-value", 0) or 0)
                if oid == "101":  # Supply water
                    result["supply_water_c"] = val
                elif oid == "102":  # Return water
                    result["return_water_c"] = val
                elif oid == "107":  # Outside air
                    result["outside_temp_c"] = val
    except Exception as e:
        logger.error("HVAC API error: %s", e)
    return result


# ── Data Collection ──────────────────────────────────────────────────────────

def find_miner_data(miners: List[Dict], miner_id: int) -> Optional[Dict]:
    """Find miner in list by ID."""
    for m in miners:
        if m.get("id") == miner_id:
            return m
    return None


def collect_hourly_reading(miner_ip: str, miner_info: Dict, miners: List[Dict],
                           phase: int, hour: int, hvac: Dict, tank_temps: Dict) -> Optional[HourlyReading]:
    miner_id = miner_info["miner_id"]
    tank_port = miner_info["tank_port"]
    stock_ths = miner_info["stock_ths"]
    
    ams_data = find_miner_data(miners, miner_id)
    if not ams_data:
        logger.error("Miner %s (ID %s) not found in AMS data", miner_ip, miner_id)
        return None
    
    # Get PDU power
    pdu_power = get_tank_port_power(tank_port)
    
    # Extract AMS data
    hashrate_ths = float(ams_data.get("hashrate", 0) or 0) / 1000  # GH/s to TH/s
    miner_power = float(ams_data.get("consumption", 0) or 0)
    chip_temp = float(ams_data.get("tempChip", 0) or 0)
    uptime_sec = int(ams_data.get("upTime", 0) or 0)
    hw_errors = int(ams_data.get("hwErrors", 0) or 0)
    
    # Board temps from chains
    chains = ams_data.get("chains", [])
    board_temps = []
    for c in chains[:3]:
        temp = float(c.get("tempBoard", 0) or c.get("temp", 0) or 0)
        board_temps.append(temp)
    while len(board_temps) < 3:
        board_temps.append(0.0)
    
    # Pool stats
    pools = ams_data.get("pools", [])
    accepted = sum(int(p.get("accepted", 0) or 0) for p in pools)
    rejected = sum(int(p.get("rejected", 0) or 0) for p in pools)
    rej_rate = (rejected / (accepted + rejected) * 100) if (accepted + rejected) > 0 else 0
    
    # Calculate efficiency
    efficiency = miner_power / hashrate_ths if hashrate_ths > 0 else 0
    hashrate_pct = (hashrate_ths / stock_ths * 100) if stock_ths > 0 else 0
    
    return HourlyReading(
        timestamp=datetime.now().isoformat(),
        phase=phase, phase_name=PHASES[phase]["name"], hour_in_phase=hour,
        miner_ip=miner_ip, miner_name=miner_info["name"],
        hashrate_ths=round(hashrate_ths, 2), hashrate_pct=round(hashrate_pct, 1),
        rated_ths=round(stock_ths, 2),
        miner_power_w=round(miner_power, 1),
        pdu_port_power_w=round(pdu_power, 1) if pdu_power else 0,
        chip_temp_c=round(chip_temp, 1),
        board0_temp_c=round(board_temps[0], 1),
        board1_temp_c=round(board_temps[1], 1),
        board2_temp_c=round(board_temps[2], 1),
        supply_water_c=round(tank_temps.get("tank_in_c", hvac.get("supply_water_c", 0)), 1),
        return_water_c=round(tank_temps.get("tank_out_c", hvac.get("return_water_c", 0)), 1),
        outside_temp_c=round(hvac.get("outside_temp_c", 0), 1),
        pool_accepted=accepted, pool_rejected=rejected,
        rejection_rate_pct=round(rej_rate, 3),
        hw_errors=hw_errors, uptime_hours=round(uptime_sec / 3600, 2),
        efficiency_jth=round(efficiency, 2)
    )


def init_csv():
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_CSV.exists():
        return
    headers = ["Timestamp","Phase","Phase_Name","Hour_In_Phase","Miner_IP","Miner_Name",
               "Hashrate_TH","Hashrate_Pct","Rated_TH","Miner_Power_W","PDU_Power_W",
               "Chip_Temp_C","Board0_Temp_C","Board1_Temp_C","Board2_Temp_C",
               "Supply_Water_C","Return_Water_C","Outside_Temp_C",
               "Pool_Accepted","Pool_Rejected","Rejection_Rate_Pct",
               "HW_Errors","Uptime_Hours","Efficiency_JTH"]
    with open(OUTPUT_CSV, "w", newline="") as f:
        csv.writer(f).writerow(headers)


def append_reading(r: HourlyReading):
    row = [r.timestamp, r.phase, r.phase_name, r.hour_in_phase, r.miner_ip, r.miner_name,
           r.hashrate_ths, r.hashrate_pct, r.rated_ths, r.miner_power_w, r.pdu_port_power_w,
           r.chip_temp_c, r.board0_temp_c, r.board1_temp_c, r.board2_temp_c,
           r.supply_water_c, r.return_water_c, r.outside_temp_c,
           r.pool_accepted, r.pool_rejected, r.rejection_rate_pct,
           r.hw_errors, r.uptime_hours, r.efficiency_jth]
    with open(OUTPUT_CSV, "a", newline="") as f:
        csv.writer(f).writerow(row)


def run_collection(phase: int, hour: int):
    logger.info("=" * 60)
    logger.info("COLLECTING: Phase %d (%s), Hour %d", phase, PHASES[phase]["name"], hour)
    logger.info("=" * 60)
    
    init_csv()
    
    # Load config and connect to AMS
    config = GuardianConfig.from_file(_ROOT / "config.json")
    ams = AMSClient(config)
    
    # Get all miners
    logger.info("Fetching miners from AMS...")
    miners = ams.get_miners()
    logger.info("Got %d miners from AMS", len(miners))
    
    # Get environmental data
    hvac = get_hvac_data()
    tank_temps = get_tank_temps()
    logger.info("Tank: in=%.1f°C, out=%.1f°C", tank_temps.get("tank_in_c", 0), tank_temps.get("tank_out_c", 0))
    logger.info("HVAC: outside=%.1f°C", hvac.get("outside_temp_c", 0))
    
    for miner_ip, info in TEST_MINERS.items():
        logger.info("Collecting %s (%s)...", miner_ip, info["name"])
        reading = collect_hourly_reading(miner_ip, info, miners, phase, hour, hvac, tank_temps)
        if reading:
            append_reading(reading)
            logger.info("  Hashrate: %.2f TH/s (%.1f%%)", reading.hashrate_ths, reading.hashrate_pct)
            logger.info("  Power: %.1f W (miner) / %.1f W (PDU)", reading.miner_power_w, reading.pdu_port_power_w)
            logger.info("  Efficiency: %.2f J/TH", reading.efficiency_jth)
            logger.info("  Temps: chip=%.1f°C, boards=[%.1f, %.1f, %.1f]°C",
                       reading.chip_temp_c, reading.board0_temp_c, reading.board1_temp_c, reading.board2_temp_c)
        else:
            logger.error("  Failed to collect data!")
    
    logger.info("Done. CSV: %s", OUTPUT_CSV)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, required=True)
    parser.add_argument("--hour", type=int, required=True)
    args = parser.parse_args()
    
    if args.phase not in PHASES:
        print(f"Error: Phase must be 1-4")
        sys.exit(1)
    
    run_collection(args.phase, args.hour)
