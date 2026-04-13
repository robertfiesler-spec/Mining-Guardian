# HVAC Systems Documentation

## Overview

Mining Guardian monitors **TWO separate HVAC/cooling systems** at the BiXBiT USA Fort Worth facility. Each miner type correlates with its specific cooling system.

## System Mapping

| Miner Model | HVAC System | IP Address | Notes |
|-------------|-------------|------------|-------|
| S19JPro | s19jpro | 192.168.189.235 | Container cooling |
| S21 EXP Hydro | warehouse | 192.168.188.235 | Warehouse HVAC |
| S21 Imm | warehouse | 192.168.188.235 | Warehouse HVAC |
| AH3880 Auradine | warehouse | 192.168.188.235 | Warehouse HVAC |

**Simple Rule**: `S19JPro` → s19jpro system. Everything else → warehouse.

## Warehouse HVAC (192.168.188.235)

**Serves**: Hydros, S21 Immersion miners

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

## S19J Pro Container (192.168.189.235)

**Serves**: S19J Pro miners only

### Sensors (BACnet Points)
| Point | OID | Description |
|-------|-----|-------------|
| Supply Temp (CDWST) | AI-105 | Supply water temperature (°F) |
| Return Temp (CDWRT) | AI-106 | Return water temperature (°F) |
| Outside Air (OAT) | AI-107 | Outside air temperature (°F) |
| Container Temp | AI-108 | Container space temperature (°F) |
| CW Pump 1 Feedback | AI-102 | Pump 1 speed feedback % |
| CW Pump 2 Feedback | AI-103 | Pump 2 speed feedback % |
| CT Fan 1 VFD | AO-101 | Cooling tower fan 1 (see note below) |
| CT Fan 2 VFD | AO-102 | Cooling tower fan 2 (see note below) |
| Leak Alarm | BI-301 | Leak detection |
| Basin Level | BI-302 | Basin level switch |
| CWP1 Trip | BI-201 | Pump 1 trip alarm |
| CWP2 Trip | BI-202 | Pump 2 trip alarm |
| CT Trip | BI-205 | Cooling tower trip alarm |

### Typical Values
- Supply: ~89°F
- Return: ~103°F
- Delta-T: ~14°F
- Container Temp: ~94°F

### ⚠️ IMPORTANT: CT Fan Note
**The S19J Pro container CT fans are manually set to 100%.**

- No VFD feedback will appear in HVAC data
- CT1_VFD and CT2_VFD will show 0%
- **This is intentional and NOT an equipment fault**
- Do NOT flag missing fan feedback as a problem

## Data Collection

### Mac HVAC Collector
- **Location**: /Users/BigBobby/Documents/GitHub/mac-scripts/hvac_collector.py
- **Service**: com.bixbit.hvac-collector (launchd)
- **Interval**: Every 5 minutes
- **Function**: Polls both BAS controllers, pushes to VPS API

The Mac collector is required because the VPS cannot reach the local network directly.

### VPS API Endpoints
- **POST /api/hvac/ingest** - Receives data from Mac collector
- **GET /api/hvac/latest** - Returns latest readings per system

### Database Storage
Table: `hvac_readings`
- `system_id`: 'warehouse' or 's19jpro'
- `recorded_at`: Timestamp
- `supply_temp_f`, `return_temp_f`, `delta_t_f`
- `outside_air_f`, `container_temp_f` (s19jpro only)
- `cwp1_vfd_pct`, `cwp2_vfd_pct`, `ct1_vfd_pct`, `ct2_vfd_pct`
- `leak_alarm`

## AI Integration

All AI scripts automatically select the correct HVAC system based on miner model:

```python
hvac_system = 's19jpro' if model.startswith('S19JPro') else 'warehouse'
```

### Files Updated for Multi-System Support
- `clients/hvac_client.py` - Multi-system polling
- `ai/hvac_correlator.py` - System-aware correlation
- `ai/daily_deep_dive.py` - Per-miner HVAC selection
- `ai/local_llm_analyzer.py` - Shows both systems in prompts
- `ai/predictor.py` - System-aware predictions
- `ai/action_diversity.py` - Fleet-level defaults to warehouse

## Operator Rules

1. **Do NOT investigate HVAC** when delta-T is low — it's intentional
2. **S19J Pro CT fans at 100%** — no VFD feedback shown, this is normal
3. Compare miners to THEIR cooling system only
4. Temperature threshold for alerts: **84°C chip temp** (not 76°C)

## Credentials

Both systems use the same Eclypse BAS credentials:
- Username: `BigStar`
- Password: `BigSt@r2020`
- Stored in: VPS `.env` (ECLYPSE_USER, ECLYPSE_PASS)

---
*Last updated: April 13, 2026*
