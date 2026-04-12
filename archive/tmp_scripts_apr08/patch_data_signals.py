#!/usr/bin/env python3
"""Fix the stale '5 min' frequency labels in the Data Signals table on the AI
dashboard. Bobby caught this yesterday — production scans run every 60 minutes
now, not 5 minutes. The labels were left over from when the scan interval was
300 seconds.

Approach: two-tier labels.
  - AMS WebSocket signals: '60 min + 15s alerts' (honest about both cadences)
  - Pool / PDU / HVAC / Weather: '60 min' (they piggyback on the daemon scan)
  - CGMiner Logs derived metrics: '60 min' (they're parsed from logs collected
    once per scan cycle, NOT once per 6 hours as the table previously claimed)
  - AMS REST API / AMS Extended: '60 min'
  - Hardware identity (chip die/bin, PCB version, etc.): 'Once' (immutable)
"""

PATH = '/Users/BigBobby/Documents/GitHub/Mining Gaurdian/api/ai_dashboard_api.py'

with open(PATH) as f:
    src = f.read()

old_table = '''DATA_SIGNALS = [
    ("Hashrate %", "AMS WebSocket", "5 min"), ("Chip Temperature", "AMS WebSocket", "5 min"),
    ("Board Temperature", "AMS WebSocket", "5 min"), ("Board Voltage", "Chain Readings", "5 min"),
    ("Board Frequency", "Chain Readings", "5 min"), ("Board HW Errors", "Chain Readings", "5 min"),
    ("Board Power (W)", "Chain Readings", "5 min"), ("Pool Accepted Shares", "Pool Readings", "5 min"),
    ("Pool Rejected Shares", "Pool Readings", "5 min"), ("Pool Rejection Rate", "Calculated", "5 min"),
    ("PDU Power (kW)", "PDU API", "5 min"), ("Miner Consumption (W)", "AMS WebSocket", "5 min"),
    ("Uptime", "AMS WebSocket", "5 min"), ("Error Codes", "AMS WebSocket", "5 min"),
    ("Firmware Version", "AMS WebSocket", "5 min"), ("Current Profile", "AMS WebSocket", "5 min"),
    ("Supply Water Temp", "HVAC BAS API", "5 min"), ("Return Water Temp", "HVAC BAS API", "5 min"),
    ("Differential Pressure", "HVAC BAS API", "5 min"), ("Outside Temperature", "Open-Meteo", "5 min"),
    ("Outside Humidity", "Open-Meteo", "5 min"), ("Per-Chip Hashrate", "CGMiner Logs", "6 hrs"),
    ("PSU Voltage", "CGMiner Logs", "6 hrs"), ("System CPU/Memory", "CGMiner Logs", "6 hrs"),
    ("Board Attach/Detach", "CGMiner Logs", "6 hrs"), ("Board Serial Number", "CGMiner Logs", "Once"),
    ("Chip Die/Bin/Grade", "CGMiner Logs", "Once"), ("PCB/BOM Version", "CGMiner Logs", "Once"),
    ("Control Board Type", "CGMiner Logs", "Once"), ("PSU Version", "CGMiner Logs", "Once"),
    ("AMS Notifications", "AMS REST API", "5 min"), ("Map Location (X,Y)", "AMS Extended", "5 min"),
]'''

new_table = '''DATA_SIGNALS = [
    # AMS WebSocket signals — pulled per scan (60 min) + monitored continuously
    # by the alert listener every 15 seconds for urgent state changes
    ("Hashrate %", "AMS WebSocket", "60 min + 15s alerts"),
    ("Chip Temperature", "AMS WebSocket", "60 min + 15s alerts"),
    ("Board Temperature", "AMS WebSocket", "60 min + 15s alerts"),
    ("Miner Consumption (W)", "AMS WebSocket", "60 min + 15s alerts"),
    ("Uptime", "AMS WebSocket", "60 min"),
    ("Error Codes", "AMS WebSocket", "60 min + 15s alerts"),
    ("Firmware Version", "AMS WebSocket", "60 min"),
    ("Current Profile", "AMS WebSocket", "60 min"),
    # Chain Readings — per-board structured data, parsed each scan
    ("Board Voltage", "Chain Readings", "60 min"),
    ("Board Frequency", "Chain Readings", "60 min"),
    ("Board HW Errors", "Chain Readings", "60 min"),
    ("Board Power (W)", "Chain Readings", "60 min"),
    # Pool Readings — share counts pulled each scan
    ("Pool Accepted Shares", "Pool Readings", "60 min"),
    ("Pool Rejected Shares", "Pool Readings", "60 min"),
    ("Pool Rejection Rate", "Calculated", "60 min"),
    # PDU — per-outlet power draw, polled with the scan
    ("PDU Power (kW)", "PDU API", "60 min"),
    # HVAC BAS — supply/return water temps, pressures, polled with the scan
    ("Supply Water Temp", "HVAC BAS API", "60 min"),
    ("Return Water Temp", "HVAC BAS API", "60 min"),
    ("Differential Pressure", "HVAC BAS API", "60 min"),
    # Weather — Open-Meteo API call per scan
    ("Outside Temperature", "Open-Meteo", "60 min"),
    ("Outside Humidity", "Open-Meteo", "60 min"),
    # CGMiner Logs — parsed each scan from logs collected once per cycle
    ("Per-Chip Hashrate", "CGMiner Logs", "60 min"),
    ("PSU Voltage", "CGMiner Logs", "60 min"),
    ("System CPU/Memory", "CGMiner Logs", "60 min"),
    ("Board Attach/Detach", "CGMiner Logs", "60 min"),
    # Hardware identity — parsed once and stored permanently (immutable)
    ("Board Serial Number", "CGMiner Logs", "Once"),
    ("Chip Die/Bin/Grade", "CGMiner Logs", "Once"),
    ("PCB/BOM Version", "CGMiner Logs", "Once"),
    ("Control Board Type", "CGMiner Logs", "Once"),
    ("PSU Version", "CGMiner Logs", "Once"),
    # AMS REST + Extended — scan-cadence pulls
    ("AMS Notifications", "AMS REST API", "60 min + 15s alerts"),
    ("Map Location (X,Y)", "AMS Extended", "60 min"),
]'''

if old_table not in src:
    print("ERROR: DATA_SIGNALS table not found exactly as expected")
    exit(1)

src = src.replace(old_table, new_table)
with open(PATH, 'w') as f:
    f.write(src)

print("PATCHED DATA_SIGNALS table:")
print("  - All '5 min' labels updated to '60 min' (or '60 min + 15s alerts' for live-monitored AMS signals)")
print("  - Stale '6 hrs' CGMiner Logs labels corrected to '60 min'")
print("  - 'Once' labels (hardware identity) preserved")
