# BiXBiT Container Sensor Reference

**Created:** April 10, 2026  
**Source:** AMS Container Dashboard Screenshots  
**Purpose:** Complete reference for container monitoring integration

---

## Container Summary View (List Page)

| Field | Example Value | Notes |
|-------|---------------|-------|
| Total Power | 505.58 kW | Sum of ASIC + Infrastructure |
| Hashrate | 26.89 PH/s | Container total |
| Miners | 71 (70 ON, 1 OFF) | Count with status |
| Container Health | 1/0/0/0 | Critical/Warning/Caution/Normal counts |

---

## Hydraulics Section

### Core Sensors

| Sensor | Name | Unit | Example | Thresholds |
|--------|------|------|---------|------------|
| PT01 | Supply Line Pressure | MPa | 0.29 | High: 0.4, Ultra-High: 0.7 |
| PT02 | Return Line Pressure | MPa | 0.19 | Ultra-Low: 0.01, Low: 0.02 |
| TT01 | Supply Line Temp | °C | 30.76 | Low: 20, High: 45, Ultra-High: 50 |
| TT02 | Return Line Temp | °C | 38.16 | (none shown) |
| FT01 | Flow on Feed | m³/h | 58.45 | Ultra-Low: 10, Low: 50 |
| ET01 | Electrical Conductivity | µS/cm | 1,572.73 | High: 2,406 |

### Pumps & Cooling

| Sensor | Name | Unit | Example | Notes |
|--------|------|------|---------|-------|
| P01 | Main Pump Frequency | Hz | 41 | Set: 42, Range: 30-40 |
| P02 | Secondary Pump | Hz | (paired with P01) | |
| P11 | Filling Pump | On/Off | Off | Tank maintenance |
| Dry Cooler | Fan Frequency | Hz | 20 | Set: 20, Range: 20-60 |
| VD01 | Bypass Valve Position | % | 0.33 | Flow control |

### Filter Monitoring

| Sensor | Name | Unit | Example | Threshold |
|--------|------|------|---------|-----------|
| PT03 | Before Filter Pressure | MPa | 0.41 | High: 0.7 |
| PT04 | After Filter Pressure | MPa | 0.38 | High: 0.7 |
| PT05 | High Pressure | MPa | N/A | |

**Insight:** `PT03 - PT04` = Filter pressure differential. Increasing = filter blockage.

### Level & Safety

| Sensor | Name | Status |
|--------|------|--------|
| Tank Level | Coolant Level | Normal |
| LS01 | Level Switch 1 | (visual only) |
| LS02 | Level Switch 2 | (visual only) |
| Leakage | Leak Detection | Normal |
| Smoke Detector | Fire Detection | Normal |


---

## Electrical Section

### Power Meter Zones

| Meter | Zone | Example kW | Notes |
|-------|------|------------|-------|
| PMM1 | Racks 1-3 | 148.24 kW | ASIC power zone 1 |
| PMM2 | Racks 4-6 | 347.36 kW | ASIC power zone 2 |
| PMM3 | Infrastructure | 9.45 kW | Pumps, fans, controls |

### Per-Zone Electrical Details

Each PMM provides:
- Voltage per phase: Ua, Ub, Uc (V)
- Current per phase: Ia, Ib, Ic (A)
- Frequency (Hz)
- Electricity consumption (kWh) — cumulative
- Operating Power (kW) — real-time
- Temperature (°C)

**Example PMM2 (heaviest load):**
| Metric | Value |
|--------|-------|
| Ua/Ub/Uc | 231.99V / 233.61V / 233.36V |
| Ia/Ib/Ic | 503.23A / 506.69A / 506.02A |
| Frequency | 60.01 Hz |
| Consumption | 83,571.7 kWh |
| Power | 347.36 kW |
| Temperature | 29.9°C |

---

## Environmental Section

### Inside Container

| Sensor | Name | Example | Threshold |
|--------|------|---------|-----------|
| TT21 | Inside Room Temp | 0°C | (sensor issue) |
| TT22 | Inside Room Temp | 29.9°C | High: 0°C (config issue) |
| TT41 | Distribution Cabinet | 29.8°C | |
| TT43 | Control Cabinet | 32.3°C | |
| Fan G21 | Ventilation Fan 1 | Off | |
| Fan G22 | Ventilation Fan 2 | Off | |

### Outside Environment

| Sensor | Name | Example |
|--------|------|---------|
| TRT01 | Outside Temperature | 23.69°C |
| (unnamed) | Outside Humidity | 27.48% |

---

## Alarms Section

Two severity levels:
1. **Emergency Alarms** — Critical issues requiring immediate attention
2. **Warning & Info Alarms** — Non-critical notifications

Alarm states available via API for monitoring.

---

## PDU Section

### PDU Summary

| Field | Example |
|-------|---------|
| Outlets | 20/20 |
| Voltage | 372.86 V |
| Current | 136.74 A |
| Power | 90.77 kW |
| Counter | 15.86 MWh |

### Per-Outlet Data

| Field | Description |
|-------|-------------|
| Voltage | Per-outlet voltage (V) |
| Current | Per-outlet current (A) |
| Power | Per-outlet power (kW/W) |
| Counter | Cumulative energy (kWh/MWh) |
| Turn On/Off | Toggle switch |
| Miner ID | Linked miner (if assigned) |

### Phase Balance

| Phase | Voltage | Current |
|-------|---------|---------|
| 1 | 373.1 V | 136.5 A |
| 2 | 372.9 V | 136.72 A |
| 3 | 372.6 V | 137.02 A |

### PDU Sensors

| Index | Temperature | Humidity |
|-------|-------------|----------|
| 0 | N/A | 0% |


---

## Miner Info Modal

### Overview Tab

| Field | Example | Notes |
|-------|---------|-------|
| Miner ID | #64640 | AMS internal ID |
| Model | Teraflux AH3880 | |
| Hashrate | 565.8 TH/s | Real-time |
| Temperature | Board 66°C, Chip 58°C | |
| Consumption | 9.91 kW | |
| Efficiency | 17.52 W/TH | |
| Cooling | Hydro | Cooling type indicator |

### PSU Info

| Field | Example |
|-------|---------|
| PSU ID | #270/14 |
| PSU Temp | 53°C |
| Aim | 0 |

### Network Info

| Field | Example |
|-------|---------|
| DHCP | Disabled |
| MAC | 04:25:E8:85:51:82 |
| IP Private | 10.21.15.54 |

### Firmware Info

| Field | Example |
|-------|---------|
| Model | teraflux-ah3880 |
| Version | 2.22 |
| Vendor | Auradine |
| AMS | AM-804-controller-5a |
| Profile | customThs 595 |

### Pools

| Field | Description |
|-------|-------------|
| URL | Stratum endpoint |
| Worker | Worker name |
| Pool Type | user/solo |
| Priority | Failover order (0 = primary) |
| Status | ALIVE/DEAD |
| Difficulty | Current difficulty |
| Accepted | Accepted shares |
| Rej | Rejected shares |

### Boards Table

| Field | Description |
|-------|-------------|
| Chain | Board index (0, 1, 2) |
| Voltage | Board voltage |
| Freq | Operating frequency (MHz) |
| Hashrate | Per-board hashrate |
| HW errors | Hardware error count |
| Temperature | Board/Chip temps |

---

## Key Correlations for AI Analysis

### Thermal Performance
- **Delta-T** = `TT02 - TT01` (return - supply) = heat extracted
- **Low delta-T** = low heat load OR high flow rate
- **High delta-T** = high heat load OR low flow rate

### Cooling Efficiency
- **FT01 vs P01** = Flow rate should correlate with pump frequency
- **Dry cooler frequency vs TRT01** = Outside temp drives cooler speed

### Filter Health
- **PT03 - PT04** = Filter differential pressure
- Increasing over time = filter needs cleaning/replacement

### Electrical Health
- **Phase imbalance** = Current difference > 5% between phases
- **PMM3 ratio** = Infrastructure / Total power (should be ~2%)

### Container PUE
- `PUE = Total Power / ASIC Power`
- Example: 505.58 / 496.12 = 1.019 (excellent)
