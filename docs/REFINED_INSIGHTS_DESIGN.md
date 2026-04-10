# Refined Fleet Intelligence System — Design Document

**Created:** April 10, 2026  
**Status:** Ready to implement  
**Author:** Bobby + Claude session

---

## Overview

The Refined Fleet Intelligence system produces **permanent, data-backed insights** that accumulate over time. Unlike weekly operational summaries that get replaced, these insights persist and get updated as new data refines the numbers.

**Example of a refined insight:**
> **PCB/BOM Failure:** PCB=0110/BOM=0020 boards averaging 13.6% hashrate while PCB=0130/BOM=0010 hit 73.5%. Reject all 0110/0020 combinations.

This is the **flagship feature** of the Grafana dashboard — the selling point for customers.

---

## Architecture

### Who Generates Insights
- **Claude only** — both at R&D Home (daily) and customer sites (monthly via master push)
- Qwen is NOT involved in refined insight generation
- Customers have internet by default; can turn it off if they want

### Site Identification
- Bobby's mine: `R&D Home`
- Customer sites: Named during Mac Mini setup following a standard format

### Storage Model: `refined_insights`

```json
{
  "refined_insights": {
    "0110_0020_boards_hydro": {
      "category": "PCB/BOM Failure",
      "topic": "0110_0020_boards",
      "insight": "PCB=0110/BOM=0020 boards averaging 13.6% hashrate...",
      "action": "REJECT",
      "confidence": "HIGH",
      "cooling_type": "HYDRO",
      "miner_type": "Antminer S19J Pro",
      "data_source": "847 chip readings over 14 days",
      "miners_affected": ["53482", "64407"],
      "data_points": 847,
      "site_id": "R&D Home",
      "first_seen": "2026-04-06",
      "last_updated": "2026-04-10",
      "update_history": []
    }
  }
}
```

### Update Logic
- **Small changes (<5%)** → Update in place, log old value to `update_history`
- **Significant changes (>5%) or conclusion change** → Add new insight noting the change

---

## Categories (Comprehensive)

### Hardware — Miner Components

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Chip Quality** | Chip bin grades, die/tech grades, failure rates by bin | `miner_hardware.chip_bin`, `chip_die`, `chip_technology` |
| **PCB/BOM Failure** | Board version combinations, manufacturing batch issues | `miner_hardware.pcb_version`, `bom_version` |
| **Serial Batch Pattern** | Production run defects (same SN prefix = same batch) | `miner_hardware.serial_number` (first 8 chars) |
| **PSU Reliability** | Model performance at stock vs overclock, lifespan by cooling type | `miner_hardware.psu_version`, consumption vs rated |
| **Hashboard Reliability** | Per-board failure rates, position correlations | `miner_hardware.board_index`, `chain_readings` |
| **Control Board Reliability** | Failure patterns by control board type | `miner_hardware.control_board` |
| **Fan Performance** | Fan health for air-cooled mines | Fan RPM from logs (air-cooled only) |
| **Firmware Insight** | Version differences, update results (before/after) | `miner_readings.firmware_version`, change detection |

### Hardware — Error Codes

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Error Code Patterns** | Correlate error codes to hardware failures | `miner_readings.error_codes` |

**Known Antminer S19 Error Codes (to populate in Intelligence Catalog):**
- Chain communication failures
- Chip detection failures (0 ASIC, low chip count)
- PSU voltage/power issues
- Temperature sensor failures
- Fan failures

### Environmental — Miner Level

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Temperature Patterns** | Chip/board temp trends by cooling type | `chain_readings.temp_chip`, `temp_board` |
| **Cooling Type Comparison** | Air vs Hydro vs Immersion performance | Miner profile `cooling_type` field |

### Environmental — Container Level

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Supply/Return Delta-T** | Temperature differential = heat load indicator | `TT01`, `TT02` |
| **Flow Rate Correlation** | Low flow = cooling failure prediction | `FT01` |
| **Coolant Quality** | Conductivity trends predict replacement | `ET01` |
| **Filter Health** | Pressure differential = blockage indicator | `PT03 - PT04` |
| **Pump Performance** | Frequency trends = pump degradation | `P01`, `P02` frequency |
| **Outside Environment** | Ambient temp/humidity vs container performance | `TRT01`, humidity |

### Electrical — Container Level

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Phase Balance** | Voltage/current balance across phases | `PMM1/2/3` phase data |
| **Per-Rack Power** | Rack zone efficiency comparisons | `PMM1` (racks 1-3), `PMM2` (racks 4-6) |
| **Infrastructure Ratio** | Cooling overhead vs compute power | `PMM3` / total |
| **Cabinet Temperatures** | Distribution/control cabinet health | `TT41`, `TT43` |


### Operational — Remediation Effectiveness

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Restart Effectiveness** | Success rates by model, cohort, cooling type | `miner_restarts` |
| **PDU Cycle Effectiveness** | Power cycle vs restart comparison | PDU cycling logs |
| **Network Performance** | Pool failures, stratum reconnects | `pool_readings` |
| **Approval Pattern** | Which actions get approved vs denied | `action_audit_log` |

### Fleet-Level — Miner Classification

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Parts Donor** | Chronic flaggers that should be dismantled | Flag frequency |
| **Golden Miner** | Consistent high performers to study | Hashrate consistency |
| **AMS Alert Noise** | Suppressing false positive patterns | Alert history |

### Procurement — Business Decisions

| Category | Description | Data Source |
|----------|-------------|-------------|
| **Procurement Action** | Stop buying / buy more decisions | Cross-category analysis |

---

## Confidence Thresholds

Stored in `config.json` → `insight_thresholds` (adjustable later):

| Confidence | Data Points | Time Span | Separation |
|------------|-------------|-----------|------------|
| HIGH | 100+ | 7+ days | >20% difference |
| MEDIUM | 25-99 | 3-7 days | 10-20% difference |
| LOW | <25 | <3 days | <10% difference |

---

## Dashboard Layout

### Panel 1: "Fleet Intelligence" (Permanent)
- Scrollable list of refined insights
- Accumulates over time
- Never replaced, only updated

### Panel 2: "This Week's Summary" (Rolling)
- Weekly operational narrative
- Replaced each week
- Claude's plain-English summary of what happened

---

## Prompt Structure

Claude receives a structured prompt containing:

1. **Miner hardware data** (chip bins, PCB/BOM, PSU, board positions)
2. **Performance data** (hashrate by board, error codes, restart outcomes)
3. **Container data** (when available) — temps, flow, electrical
4. **Weather correlation** (outside temp/humidity vs performance)
5. **Historical insights** (existing refined_insights for update consideration)

Claude responds with:
- A narrative summary for Panel 2
- A JSON block of refined insights for Panel 1

---

## Generation Schedule

| Site Type | Frequency | Method |
|-----------|-----------|--------|
| R&D Home (Bobby's mine) | Daily | Claude API after Pass 1 |
| Customer Sites | Monthly | Master knowledge push |

---

## Implementation Files

| File | Purpose |
|------|---------|
| `ai/train_cohort.py` | Add refined insights section to prompt |
| `ai/insight_manager.py` | Parse Claude JSON, merge into knowledge.json |
| `api/ai_dashboard_api.py` | Serve Panel 1 from refined_insights |
| `config.json` | Add insight_thresholds |

---

## Migration Plan

The legacy April 6 insight (PCB/BOM failure analysis) will be migrated to the new `refined_insights` format as the gold standard example.
