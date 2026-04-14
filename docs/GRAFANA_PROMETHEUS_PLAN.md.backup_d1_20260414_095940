# Grafana + Prometheus Integration Plan

Status: **Research / Future Implementation**
Decided: April 2026 — build the foundation now while small (1 site, 58 miners)
rather than retrofitting under pressure at scale (10 sites, 500+ miners).

---

## Why

- Best-in-class time-series visualization — far better than Chart.js iFrames
- Built for multi-site from day one — add a site, it appears in every dashboard automatically
- Grafana alerting becomes the notification layer long term
- When BiXBiT scales to multiple customers, the foundation is already there
- Easier to instrument 1 site correctly than to retrofit 10 sites later

---

## Target Architecture

```
Each Site (Mac Mini)
  ├── Mining Guardian → /metrics endpoint (Prometheus format)
  └── Prometheus Node Exporter (optional OS-level metrics)

Central VPS
  ├── Prometheus        — scrapes all sites, stores time-series data
  ├── Grafana           — reads Prometheus, serves all dashboards
  └── Mining Guardian   — orchestration layer (unchanged)

Cloudflare Tunnel
  └── grafana.fieslerfamily.com → VPS Grafana port
```

When site 2 is added: one new stanza in prometheus.yml.
Every Grafana dashboard shows both sites automatically.
Zero code changes to Mining Guardian core logic.

---

## Metrics to Expose (/metrics on dashboard_api.py)

Labels on all per-miner metrics: miner_ip, model, site, map_location

```
# Per-miner
mining_guardian_hashrate_pct          — % of rated TH/s
mining_guardian_temp_chip             — chip temp °F or °C
mining_guardian_pdu_power_kw          — PDU outlet power draw
mining_guardian_flagged               — 1 if currently flagged, 0 if clean
mining_guardian_dead_boards           — count of dead hashboards

# Fleet
mining_guardian_fleet_online          — miners online count
mining_guardian_fleet_offline         — miners offline count
mining_guardian_fleet_issues          — miners with active issues

# HVAC / Mechanical
mining_guardian_hvac_supply_f         — supply water temp
mining_guardian_hvac_return_f         — return water temp
mining_guardian_hvac_delta_t_f        — delta T
mining_guardian_hvac_diff_pressure    — differential pressure PSI
mining_guardian_spray_pump_on         — 1/0

# Environment
mining_guardian_outside_temp_f        — Fort Worth ambient temp
mining_guardian_humidity_pct          — ambient humidity
```

---

## Implementation Steps

### Step 1 — Add /metrics endpoint to dashboard_api.py
```bash
pip install prometheus-client
```
- Read latest scan from guardian.db
- Expose all metrics in Prometheus text format
- Auto-updated every scan cycle (every 5 min)
- Prometheus scrapes it every 30s

### Step 2 — Install Prometheus on VPS
```yaml
# /etc/prometheus/prometheus.yml
scrape_configs:
  - job_name: 'mining_guardian_usa_188'
    scrape_interval: 30s
    static_configs:
      - targets: ['localhost:8585']
    metrics_path: '/metrics'
    labels:
      site: 'usa_188'

  # Future — add one stanza per new site:
  # - job_name: 'mining_guardian_site2'
  #   static_configs:
  #     - targets: ['site2-tailscale-ip:8585']
  #   labels:
  #     site: 'site2_name'
```

### Step 3 — Install Grafana on VPS
- Add Prometheus as datasource
- Build dashboards:
  - Fleet overview — online/offline, total hashrate, power draw, issue count
  - Per-miner hashrate trends — 7-day sparklines per miner
  - Temperature heatmap — all miners color-coded by temp zone
  - HVAC correlation — supply/return/outside temp overlay
  - Power efficiency — TH/s per kW per miner (finds underperformers)
  - Flag history — which miners flagged most over any time window
  - Dead board tracker — timeline of board failures by miner
- Expose via Cloudflare tunnel: grafana.fieslerfamily.com

### Step 4 — Replace Retool chart iFrames
- Keep Retool for stat tiles and data tables (it's good at those)
- Replace chart iFrame embeds with Grafana panel embeds
- Same Retool URL, better charts, no Retool dependency for visualization

### Step 5 — Grafana Alerting (long term)
- Grafana alerts to Slack when thresholds crossed
- Gradually replaces Mining Guardian's raw Slack alerting
- Mining Guardian focuses purely on remediation logic, not notification

---

## Resource Requirements (VPS — 32GB RAM, 8 vCPU)
- Prometheus: ~200-500MB RAM, minimal CPU
- Grafana: ~200-400MB RAM, minimal CPU
- Total overhead: ~700MB-900MB — well within headroom
- Both run as systemd services alongside existing 7 services

---

## Data Architecture

```
guardian.db (SQLite)         — source of truth, all history
      ↓
/metrics endpoint            — current state only, Prometheus scrapes
      ↓
Prometheus TSDB              — time-series store for Grafana
      ↓
Grafana                      — visualization + alerting layer
```

guardian.db is never replaced — it stays as the authoritative store
for the AI knowledge system, audit logs, and approval flow.
Prometheus is purely a visualization layer on top.

---

## Multi-Site Vision

```
BiXBiT Customer Site 1 (USA)
  └── Mac Mini → /metrics → Prometheus (central VPS)

BiXBiT Customer Site 2 (future)
  └── Mac Mini → /metrics → Prometheus (central VPS)

BiXBiT Customer Site N
  └── Mac Mini → /metrics → Prometheus (central VPS)

Grafana
  └── Variable: site = {usa, site2, siteN}
  └── Every dashboard filterable by site
  └── One dashboard for all customers
```

Long term: Grafana Cloud hosted instance — one URL for the entire
BiXBiT fleet across all customer sites, all managed centrally.

---

## Notes

- Full Prometheus stack recommended over SQLite datasource plugin —
  SQLite plugin works but doesn't support multi-site federation
- Grafana alerting can eventually replace Slack-based alerting in
  Mining Guardian, keeping the codebase focused on remediation
- This is the right time to instrument — adding labels (site, model)
  now means dashboards are multi-site ready from first deployment
