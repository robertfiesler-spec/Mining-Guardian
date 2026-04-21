# HVAC Systems Documentation

**Last Updated:** 2026-04-21

## Overview

Mining Guardian monitors **TWO separate HVAC/cooling systems** at the BiXBiT USA Fort Worth facility. Each miner type correlates with its specific cooling system.

## System Mapping

| Miner Model | HVAC System | IP Address | Notes |
|-------------|-------------|------------|-------|
| S19JPro | s19jpro | 192.168.189.235 | Container cooling |
| S21 EXP Hydro | warehouse | 192.168.188.235 | Warehouse HVAC |
| S21 Imm | warehouse | 192.168.188.235 | Warehouse HVAC |
| AH3880 Auradine | warehouse | 192.168.188.235 | Warehouse HVAC |

**Simple Rule**: S19JPro → s19jpro system. Everything else → warehouse.

---

## Warehouse HVAC (192.168.188.235)

**Serves**: Hydros, S21 Immersion miners
**Controller**: Distech Eclypse (BACnet)
**Client**: clients/hvac_client.py

### Sensors (BACnet Points)
| Point | OID | Description |
|-------|-----|-------------|
| Supply Temp | AI-101 | Chilled water supply temperature (°F) |
| Return Temp | AI-102 | Chilled water return temperature (°F) |
| Diff Pressure | AI-103 | Differential pressure (PSI) |
| CW Pump 1 | AO-101 | Chilled water pump 1 VFD % |
| CW Pump 2 | AO-102 | Chilled water pump 2 VFD % |
| CT Fan 1 | AO-103 | Cooling tower fan 1 VFD % |
| CT Fan 2 | AO-104 | Cooling tower fan 2 VFD % |
| Leak Alarm | BV-22 | Leak detection (active = alarm) |
| Basin Level | BI-302 | Basin level switch |

### Typical Values
- Supply: ~75°F
- Return: ~86°F
- Delta-T: ~11°F
- Note: Low delta-T is intentional and will rise as outside temps climb

---

## S19J Pro Container (192.168.189.235)

**Serves**: S19J Pro miners only
**Controller**: Distech Eclypse running Big Star BlockChain AV-2 Plant
**Interface**: ENVYSION (DGLux visualization)
**Client**: clients/av2_plant_client.py

### API Details (Discovered 2026-04-21)

**Endpoint:**
POST https://192.168.189.235/eclypse/dgapi

**Authentication:**
- Session: GET /eclypse/dguser/session
- Basic Auth: BigStar/BigSt@r2020

**Request Format (Polling):**
{
  "requests": [],
  "subscription": "DG<subscription_id>"
}

**Response Format:**
{
  "subscription": "DG<subscription_id>",
  "responses": [{
    "method": "UpdateSubscription",
    "values": [{
      "path": "/Data/Plant/CDWST",
      "value": 83.6,
      "unit": "°F",
      "formatted": "83.6°F",
      "status": "ok",
      "lastUpdate": "2026-04-21T10:57:34.340-05:00"
    }]
  }]
}

### Data Paths

| Path | Description | Field in Client |
|------|-------------|-----------------|
| /Data/Plant/OAT | Outside Air Temp (°F) | outside_air |
| /Data/Plant/ContainerSpaceTemp | Container Ceiling Temp (°F) | container_temp |
| /Data/Plant/CDWST | Condenser Water Supply Temp (°F) | supply_temp |
| /Data/Plant/CDWRT | Condenser Water Return Temp (°F) | return_temp |
| /Data/Plant/CWP1_Fdbk | CW Pump 1 Speed Feedback (%) | cwp1_speed |
| /Data/Plant/CWP2_Fdbk | CW Pump 2 Speed Feedback (%) | cwp2_speed |
| /Data/Plant/CT1VSDFdbk | Cooling Tower Fan 1 VFD Feedback (%) | ct_fan_speed |

### Typical Values
- Supply: ~83°F
- Return: ~98°F
- Delta-T: ~15°F
- Container Temp: ~93°F
- Outside Air: varies

### Network Access Note
**IMPORTANT:** VPS cannot reach 192.168.189.x directly.
This subnet routes through ROBS-PC Tailscale (100.110.87.1).

Options for data collection:
1. Call from ROBS-PC and push to VPS
2. Proxy through ROBS-PC Tailscale route
3. Mac Mini (when arrives) with facility network access

### ⚠️ CT Fan Note
**The S19J Pro container CT fans are manually set to 100%.**

- No VFD feedback will appear in HVAC data
- CT1_VFD and CT2_VFD will show 0%
- **This is intentional and NOT an equipment fault**
- Do NOT flag missing fan feedback as a problem

---

## Data Collection Architecture

### Warehouse (192.168.188.235)
- **Client**: clients/hvac_client.py (BACnet polling)
- **Access**: VPS can reach via ROBS-PC Tailscale route

### S19J Pro Container (192.168.189.235)
- **Client**: clients/av2_plant_client.py (DGLux API)
- **Access**: Requires ROBS-PC or facility network access
- **API**: Subscription-based polling via POST /eclypse/dgapi

### VPS API Endpoints
- **POST /api/hvac/ingest** - Receives data from collectors
- **GET /api/hvac/latest** - Returns latest readings per system

### Database Storage
Table: hvac_readings
- system_id: 'warehouse' or 's19jpro'
- recorded_at: Timestamp
- supply_temp_f, return_temp_f, delta_t_f
- outside_air_f, container_temp_f (s19jpro only)
- cwp1_vfd_pct, cwp2_vfd_pct, ct1_vfd_pct, ct2_vfd_pct
- leak_alarm

---

## AI Integration

All AI scripts automatically select the correct HVAC system based on miner model:

hvac_system = 's19jpro' if model.startswith('S19JPro') else 'warehouse'

### Files with Multi-System Support
- clients/hvac_client.py - Warehouse BACnet polling
- clients/av2_plant_client.py - S19J Pro DGLux API
- ai/hvac_correlator.py - System-aware correlation
- ai/daily_deep_dive.py - Per-miner HVAC selection
- ai/local_llm_analyzer.py - Shows both systems in prompts
- ai/predictor.py - System-aware predictions
- ai/action_diversity.py - Fleet-level defaults to warehouse

---

## Operator Rules

1. **Do NOT investigate HVAC** when delta-T is low — it is intentional
2. **S19J Pro CT fans at 100%** — no VFD feedback shown, this is normal
3. Compare miners to THEIR cooling system only
4. Temperature threshold for alerts: **84°C chip temp** (not 76°C)

---

## Credentials

Both systems use the same Eclypse BAS credentials:
- Username: BigStar
- Password: BigSt@r2020
- Stored in: VPS .env (ECLYPSE_USER, ECLYPSE_PASS)

---
