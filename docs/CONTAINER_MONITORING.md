# Container Monitoring — Research Notes

## Overview
AMS containers represent the physical cooling infrastructure units (hydro/immersion tanks).
Each container houses multiple miners and monitors the cooling system independently from the miners themselves.

Container health directly affects miner performance:
- Supply water temp rising → chip temps rise
- Pump fault → miners overheat within minutes
- Low flow rate → inadequate cooling
- Leakage → immediate shutdown risk

## Container List Data (per container)
Available from the containers list page:

| Field | Description |
|---|---|
| Container ID | Numeric ID (331, 332, etc.) |
| Container name | User-defined name |
| Status | Auto-run / Manual / Stop |
| Hashrate | Total TH/s across all miners in container |
| Miners | Count — online / offline |
| ASIC Consumption | Total miner power draw (kW) |
| Infrastructure consumption | Cooling system power draw (kW) |
| PUE | Power Usage Effectiveness ratio |
| Supply pressure (PT01) | MPa |
| Supply temp (TT01) | °C |
| Return pressure (PT02) | MPa |
| Return temp (TT02) | °C |
| Main pump frequency (P01/P02) | Hz |
| Filling pump (P11) | Status |
| Dry cooler frequency | Hz |
| Fan G21 | Status |
| Fan G22 | Status |
| Container Health | Critical / Warning / Caution / OK counts |

## Container Detail — Tech Parameters (Cooling tab)

### Status Indicators
| Sensor | Description |
|---|---|
| Tank Level | High / Low / Normal |
| P11 Filling pump | Status |
| Leakage | Leak / OK |
| Smoke detector | Smoke / OK |

### System Indicators
| Sensor | Field | Value | Thresholds |
|---|---|---|---|
| PT01 | Supply Line Pressure | MPa | High: 426, Ultra-High: 520 |
| TT01 | Supply Line Temp | °C | Low: -57.5, High: -17, Ultra-High: -11 |
| PT02 | Return Line Pressure | MPa | Ultra-Low: 62, Low: 120 |
| TT02 | Return Line Temp | °C | — |
| Pump P01 | Frequency | Hz | Set: 44, Range: 30-60 |
| Dry Cooler | Frequency | Hz | Set: 43, Range: 20-60 |
| FT01 | Flow on feed | m³/h | Ultra-Low: 43, Low: 76 |
| ET01 | Electrical conductivity | µS/cm | High: 13.5 |
| PT03 | Before filter pressure | MPa | High: 610 |
| PT04 | After filter pressure | MPa | High: 560 |
| PT05 | High pressure | MPa | — |

### Parameters Inside the Room
| Sensor | Description |
|---|---|
| TT21 | Inside room temperature (°C) |
| TT22 | Inside room temperature (°C) |
| Fan G21 | Fan status |
| Fan G22 | Fan status |

### Outside Parameters
| Sensor | Description |
|---|---|
| TRT01 | Outside temperature (°C) |
| Outside humidity | % |

## Container Detail — Alarms System

Two severity levels:

### Emergency Alarms (Critical — immediate action required)
- Fan Group G21/G22 Fault
- Temperature Humidity Sensor Fault
- EV001 Electric Bypass Valve Fault
- TT01 Supply Temperature Sensor Fault
- PT01 Supply Pressure Sensor Fault
- PT02 Return Pressure Sensor Fault
- TT02 Return Temperature Sensor Fault
- P01 Main Circulation Pump Inverter Fault
- P11 Makeup Pump Fault
- FT01 Flow Meter Sensor Fault
- Dry Cooler Inverter Fault
- PMM1/PMM2/PMM3 Power Meter Communication Offline
- TT41 Distribution Cabinet Temperature Sensor Fault
- TT22 Equipment Cabin Temperature Sensor Fault
- TT21 Engine Room Temperature Sensor Fault
- TT42 Control Cabinet Temperature Sensor Fault
- VFG01 Inverter Communication Offline
- V101 External Fill Valve Close Fault
- V102 Storage Tank Valve Close Fault
- PT03/PT04 Pressure Sensor Fault

### Warning Alarms (Monitor — action may be needed)
- Dry Cooler Motor Protector Trip
- Main Circulation Pump Overcurrent
- Dry Cooler Inverter Overcurrent
- Power Protector Trip
- LL Low Level Switch Alarm
- Equipment Cabin Smoke
- PLC Error
- System Error
- SPD1/SPD2 Distribution Cabinet Surge Alarm
- LH High Level Switch Alarm
- G21/G22 Leak Sensor Alarm
- SS1/SS2 Distribution Cabinet/Engine Room Smoke
- ET01 High Conductivity
- Insufficient Fill Flow
- VF01 Inverter Offline
- FT01 Ultra-Low Supply Flow
- TT01 Ultra-High Supply Temperature
- TT21/TT22 Engine Room/Equipment Cabin High Temperature
- PMM1/PMM2/PMM3 Distribution Cabinet Voltage/Frequency Abnormal

## Container Detail — Farm Tab
Visual grid showing all miners in the container by rack, color-coded by:
- Temperature
- Hashrate
- Power

Sub-tabs: Farm view | Miners list

## Container Detail — Events Tab
Command history for the container:
- Reset
- V101 Valve Switch
- Main/Backup Pump switch
- Primary External Fill
- Status: Pending / Success / Error

## System Consumption (Power Meters)
| Meter | Racks | kW |
|---|---|---|
| PMM1 | Racks 1-3 | ~40 kW |
| PMM2 | Racks 4-6 | ~41 kW |
| PMM3 | Infrastructure | ~42 kW |

## Mining Guardian Integration Plan

### When to build
- When live container access is available for validation in the customer's BiXBiT workspace
- Container alerts can be wired into the existing Approval API + Slack notifier rather than a separate agent

### What to monitor per scan
Priority sensors to pull every scan:
1. TT01 — Supply line temp (leading indicator for miner chip temps)
2. TT02 — Return line temp (delta vs supply shows heat load)
3. FT01 — Flow rate (low flow = cooling failure imminent)
4. PT01/PT02 — Supply/return pressure
5. P01 pump frequency (pump health)
6. Active alarm count — emergency vs warning
7. Tank level, leakage, smoke status

### Correlation rules
- TT01 rising + miner chip temps rising = cooling system stressed
- FT01 below 76 m³/h = warning, below 43 m³/h = emergency
- Any emergency alarm = post to Slack immediately regardless of miner scan cycle
- Leakage detected = immediate Slack alert + consider miner shutdown recommendation

### API endpoints needed (to be confirmed)
- Container list: likely GET /containers or /container
- Container detail: likely GET /container/{id}
- Container params: likely WSS container/ws or similar
- Container alarms: likely GET /container/{id}/alarms

### Multi-Workspace Authentication
Currently containers live in a separate workspace from miners (USA 188) for testing purposes only.
In production, containers and miners will be in the SAME workspace.
No multi-workspace complexity needed — one login, one workspace, everything together.

*Status: Pending live container access in USA 188 workspace*
