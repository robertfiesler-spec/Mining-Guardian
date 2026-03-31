# Warehouse Mechanical System

## XpressENVYSION Building Automation / HVAC Controller

URL: https://192.168.188.235/eclypse/envysion/viewer.html?proj=XpressENVYSION#mode=view&node=AM9A91A-362-DD8-B1A-B46M113

This is the building automation system (BAS) for the BiXBiT USA warehouse / R&D center.
It monitors and controls the mechanical side of the facility — HVAC, cooling, environmental.

## Why This Matters for Mining Guardian

The warehouse miners (Auradine AH3880s, S21 EXP Hydros, S21 Imm) are all liquid cooled.
Their chip temps are directly correlated with the facility's mechanical performance:
- If chilled water supply temp rises → hydro miners run hotter
- If ambient room temp rises → affects all equipment in the warehouse
- If a pump or cooling circuit fails → miners will thermally throttle or shut down

Correlating BAS data with miner chip temps gives early warning of cooling problems
BEFORE miners start faulting. A rising return water temp across the whole warehouse
fleet is a building problem, not a miner problem.

## Integration Plan (Future)

1. Explore the API — check if XpressENVYSION exposes a REST or BACnet/IP endpoint
2. If accessible: poll supply/return temps, ambient room temp, chiller status each scan
3. Add to FacilityMonitor alongside PDU and immersion tank data
4. Correlate: if warehouse ambient > threshold AND miner chip temps rising → flag as
   "cooling system issue" not "miner issue"

## Access Notes

- IP: 192.168.188.235 (local warehouse network — accessible from Mac Mini on-site)
- System: Distech Controls Eclypse / XpressENVYSION BAS platform
- Credentials: TBD (Rob to provide)
- Protocol: Likely BACnet/IP or REST over HTTP — needs exploration
