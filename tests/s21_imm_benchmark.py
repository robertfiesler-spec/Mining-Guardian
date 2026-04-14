#!/usr/bin/env python3
"""
S21 Immersion Stock Test - Hourly Data Collection
Collects power and environmental metrics for BiXBiT firmware efficiency proof
"""
import sqlite3
import requests
import json
import time
from datetime import datetime

# Test configuration
TEST_START = "2026-04-13 08:00:00"  # This morning
MINERS = {
    "192.168.188.22": {"name": ".22", "stock_target": 208},
    "192.168.188.23": {"name": ".23", "stock_target": 217}
}
PDU_PORTS = {
    "192.168.188.22": 19,
    "192.168.188.23": 20
}

def get_miner_data(conn):
    """Get latest miner readings from AMS"""
    data = {}
    for ip in MINERS.keys():
        row = conn.execute("""
            SELECT hashrate, consumption, temp_chip, temp_board
            FROM miner_readings
            WHERE ip = ?
            ORDER BY scanned_at DESC
            LIMIT 1
        """, (ip,)).fetchone()
        
        if row:
            hashrate_mhs, consumption, temp_chip, temp_board = row
            # Convert MH/s to TH/s
            hashrate_ths = hashrate_mhs / 1000 if hashrate_mhs else 0
            data[ip] = {
                "hashrate_ths": hashrate_ths,
                "consumption_w": consumption or 0,
                "temp_chip": temp_chip or 0,
                "temp_board": temp_board or 0
            }
    return data

def get_pdu_power():
    """Get Tank B100 PDU power readings"""
    try:
        resp = requests.get("http://192.168.188.20/api/device-status", timeout=5)
        tank_data = resp.json()
        
        pdu_power = {}
        for port in tank_data.get("ports", []):
            port_num = port.get("port")
            if port_num in [19, 20]:
                power_kw = port.get("power_kw", 0)
                # Map port to IP
                for ip, port_map in PDU_PORTS.items():
                    if port_map == port_num:
                        pdu_power[ip] = power_kw * 1000  # Convert to watts
        
        return pdu_power
    except Exception as e:
        print(f"PDU Error: {e}")
        return {}

def collect_sample():
    """Collect one hourly sample"""
    conn = sqlite3.connect("/root/Mining-Gaurdian/guardian.db")
    
    # Get data
    miner_data = get_miner_data(conn)
    pdu_power = get_pdu_power()
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Calculate hours since test start
    start_dt = datetime.strptime(TEST_START, "%Y-%m-%d %H:%M:%S")
    now_dt = datetime.now()
    hours_elapsed = (now_dt - start_dt).total_seconds() / 3600
    
    print(f"=== S21 IMM STOCK TEST - Hour {hours_elapsed:.1f} ===")
    print(f"Timestamp: {timestamp}\n")
    
    # Write to CSV
    csv_path = "/root/Mining-Gaurdian/tests/s21_imm_benchmark.csv"
    
    # Create header if file doesn't exist
    try:
        with open(csv_path, 'r') as f:
            pass
    except FileNotFoundError:
        with open(csv_path, 'w') as f:
            f.write("timestamp,hours_elapsed,miner_ip,miner_name,stock_target_ths,")
            f.write("actual_hashrate_ths,hashrate_pct,chip_temp_c,board_temp_c,")
            f.write("miner_power_w,pdu_power_w,power_diff_w,power_diff_pct,")
            f.write("efficiency_jth\n")
    
    # Append data for each miner
    with open(csv_path, 'a') as f:
        for ip, miner_info in MINERS.items():
            if ip not in miner_data:
                continue
            
            md = miner_data[ip]
            pdu_w = pdu_power.get(ip, 0)
            
            stock_target = miner_info["stock_target"]
            hashrate_pct = (md["hashrate_ths"] / stock_target * 100) if stock_target > 0 else 0
            
            power_diff = pdu_w - md["consumption_w"] if pdu_w > 0 else 0
            power_diff_pct = (power_diff / md["consumption_w"] * 100) if md["consumption_w"] > 0 else 0
            
            efficiency = (pdu_w / md["hashrate_ths"]) if md["hashrate_ths"] > 0 and pdu_w > 0 else 0
            
            f.write(f"{timestamp},{hours_elapsed:.2f},{ip},{miner_info['name']},{stock_target},")
            f.write(f"{md['hashrate_ths']:.2f},{hashrate_pct:.1f},{md['temp_chip']:.1f},{md['temp_board']:.1f},")
            f.write(f"{md['consumption_w']:.0f},{pdu_w:.0f},{power_diff:.0f},{power_diff_pct:.1f},")
            f.write(f"{efficiency:.2f}\n")
            
            print(f"Miner {miner_info['name']} ({ip}):")
            print(f"  Hashrate: {md['hashrate_ths']:.2f} TH/s ({hashrate_pct:.1f}% of {stock_target})")
            print(f"  Temps: Chip {md['temp_chip']:.1f}°C, Board {md['temp_board']:.1f}°C")
            print(f"  Miner Power: {md['consumption_w']:.0f} W")
            print(f"  PDU Power:   {pdu_w:.0f} W (diff: {power_diff:+.0f} W, {power_diff_pct:+.1f}%)")
            print(f"  Efficiency:  {efficiency:.2f} J/TH")
            print()
    
    conn.close()
    print(f"Data saved to {csv_path}")

if __name__ == "__main__":
    collect_sample()
