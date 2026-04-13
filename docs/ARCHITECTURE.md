# Mining Guardian — System Architecture

**Last updated:** April 13, 2026
**Author:** Computer, directed by Bobby Fiesler

This document describes the complete system architecture of Mining Guardian, including all hardware, all databases, all network paths, the deployment topology, and the planned migration timeline.

---

## 1. Architecture Overview

Mining Guardian is an AI-first autonomous Bitcoin mining fleet monitoring system. The architecture spans four physical locations today and consolidates to three after the Mac mini migration in May 2026.

```
┌──────────────────────────────────────────────────────────────────────┐
│                BiXBiT USA — Fort Worth, TX                          │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  58 Liquid-Cooled Miners (192.168.188.0/24 subnet)          │    │
│  │  S19J Pro (45) · S21 EXP Hydro (2) · S21 Imm (2)           │    │
│  │  Teraflux AH3880 (2) · BiXBiT AMS manages all              │    │
│  └────────────────────────┬─────────────────────────────────────┘    │
│                           │ LAN                                      │
│  ┌────────────────────────┴─────────────────────────────────────┐    │
│  │  ROBS-PC (Windows 11, Tailscale 100.110.87.1)               │    │
│  │  ├── Tailscale subnet gateway (192.168.188.0/24 → VPS)      │    │
│  │  ├── Ollama + Qwen 2.5 32B Q4 on RTX 4090 (port 11434)     │    │
│  │  ├── Mining Intelligence Catalog DB (PostgreSQL 16, Docker)  │    │
│  │  │   └── mining-guardian-db container, port 5432             │    │
│  │  └── AMD Ryzen 7 7800X3D, 32 GB RAM, 2 TB SSD              │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  HVAC Systems                                                │    │
│  │  ├── Warehouse: Distech Eclypse @ 192.168.188.235           │    │
│  │  └── S19J Pro CT: @ 192.168.189.235                         │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  PDUs                                                        │    │
│  │  ├── orient_RPDU 163 @ 192.168.188.15                       │    │
│  │  └── orient_RPDU 164 @ 192.168.188.16                       │    │
│  └──────────────────────────────────────────────────────────────┘    │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  External HDD (Samsung SSD 860 EVO 1TB, Drive D:)           │    │
│  │  └── D:\MiningGuardian\                                     │    │
│  │      ├── db-backups/ (daily, weekly, pre-migration)         │    │
│  │      ├── intelligence-catalog/ (research-csv, seed-data)    │    │
│  │      ├── guardian-ai/ (models, training-data)               │    │
│  │      ├── fleet-logs/ (archive)                              │    │
│  │      └── docs/                                              │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
         │ Tailscale VPN
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Hostinger VPS (187.124.247.182 / Tailscale 100.106.123.83)        │
│  *** TEMPORARY R&D SCAFFOLDING — migrates to Mac mini May 5-9 ***  │
│                                                                      │
│  ├── mining-guardian (systemd)        — fleet scanner, every hour   │
│  ├── dashboard-api (systemd :8585)    — REST + Prometheus /metrics  │
│  ├── approval-api (systemd :8686)     — APPROVE/DENY, localhost     │
│  ├── slack-listener (systemd)         — polls threads for approvals │
│  ├── slack-commands (systemd)         — fleet intelligence bot      │
│  ├── overnight-automation (systemd)   — auto-actions 8pm–6am       │
│  ├── cloudflared (systemd)            — TEMPORARY tunnels           │
│  ├── Prometheus (systemd :9090)       — metrics, 30s scrape         │
│  ├── Grafana (systemd :3000)          — 6 dashboards                │
│  └── OpenClaw (Docker :18789)         — Slack Socket Mode + LLM    │
└──────────────────────────────────────────────────────────────────────┘
         │ Outbound only
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│  External Services (all outbound, no public ingress)                │
│  ├── BiXBiT AMS API (api-staging.dev.bixbit.io)                    │
│  ├── Slack (Socket Mode + chat.postMessage)                         │
│  ├── Anthropic Claude API (weekly training only, Sundays 3am)       │
│  ├── Open-Meteo (weather, free, no key)                             │
│  └── GitHub (code + knowledge_backup.json daily 4am)                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Two Database Architecture

Mining Guardian operates two completely independent databases:

### guardian.db (Production — SQLite on VPS)
- **Purpose:** Real-time fleet operations. Every scan writes here. Every action logged here.
- **Engine:** SQLite with WAL mode
- **Tables:** 16+ (scans, miner_readings, chain_readings, pool_readings, action_audit_log, etc.)
- **Size:** ~1 GB max
- **Backup:** Rolling copies to Big-Bobby-T9 + daily knowledge to GitHub

### mining_guardian / Intelligence Catalog (Research — PostgreSQL 16 on ROBS-PC)
- **Purpose:** Comprehensive miner hardware knowledge base. Specs, parts, chips, repairs, market data.
- **Engine:** PostgreSQL 16 in Docker
- **Tables:** 90 across 10 schemas
- **Columns:** 2,363
- **Seed data:** 313 Bitcoin SHA-256 miner variants
- **Size:** Currently small, designed for 50-100 GB, 1 TB ceiling
- **Backup:** pg_dump to `D:\MiningGuardian\db-backups\`

The two databases never share a write path. Guardian may eventually do read-only lookups against the catalog for spec verification, but Guardian never depends on the catalog being available.

---

## 3. Two-Tier AI System

| Tier | Model | Hardware | Used For | Cost |
|------|-------|----------|----------|------|
| Local | Qwen 2.5 32B Q4_K_M | RTX 4090 (24 GB VRAM) on ROBS-PC | Every-scan analysis (~4.6s), denial processing, daily deep dive | Free |
| Cloud | Claude Sonnet | Anthropic API | Weekly cohort training (Sunday 3am), ad-hoc deep analysis | ~$1-2/mo |

Key architectural rules:
- Ollama on VPS stopped to save CPU — all LLM queries route to ROBS-PC over Tailscale
- Claude path does NOT fall back to Ollama during outages — scan loop never blocks on Claude
- Production customer Mac minis use local LLM only — Claude API is proof-of-concept
- `model_used` in `llm_analysis` always reflects the actual backend that ran

---

## 4. Network Topology

### Tailscale Mesh

| Node | Tailscale IP | Role |
|------|-------------|------|
| ROBS-PC | 100.110.87.1 | Subnet gateway (192.168.188.0/24), LLM host, Intelligence Catalog DB |
| Hostinger VPS | 100.106.123.83 | Mining Guardian daemon, all services |

### Facility Subnet (192.168.188.0/24)

| IP | Device |
|----|--------|
| 192.168.188.1 | Gateway/Router |
| 192.168.188.15 | PDU orient_RPDU 163 |
| 192.168.188.16 | PDU orient_RPDU 164 |
| 192.168.188.22–.55 | Miners (58 total) |
| 192.168.188.47 | ROBS-PC |
| 192.168.188.235 | Warehouse HVAC (Distech Eclypse) |
| 192.168.189.235 | S19J Pro CT HVAC |

### Data Flow

```
Miners → AMS API → VPS (Mining Guardian) → Slack
                                         → Grafana
                                         → guardian.db
                                         → Qwen 32B (ROBS-PC via Tailscale)
                                         → Claude API (weekly only)
```

---

## 5. Migration Timeline

### Phase 1: Current State (Now — May 4, 2026)
- VPS runs all Mining Guardian services
- ROBS-PC runs LLM + Intelligence Catalog DB
- Cloudflare tunnels provide temporary access to dashboards
- All data lives on VPS + ROBS-PC + Big-Bobby-T9

### Phase 2: Mac Mini Arrival (May 5–9, 2026)
- Mac mini arrives, runs docker-compose stack:
  - mining-guardian (Python)
  - openclaw (Slack Socket Mode)
  - prometheus (:9090)
  - grafana (:3000)
  - ollama (Qwen 32B)
- All Cloudflare tunnels removed
- VPS decommissioned
- No public ingress at customer sites
- Dashboards at `http://mac-mini-ip:3000` and `:8585`

### Phase 3: Ollama Migration (Post-Mac Mini)
- Qwen 2.5 32B moves from ROBS-PC (RTX 4090) to Mac mini
- ROBS-PC retains: Intelligence Catalog DB, subnet gateway
- Each customer Mac mini runs its own local LLM

### Phase 4: NAS Migration (July 2026)
- UGREEN NASync iDX6011 Pro arrives
- Intelligence Catalog PostgreSQL moves from ROBS-PC to NAS
- Migration: `pg_dump` → file copy → `pg_restore` (~20 min for 60 GB)
- NAS specs: Intel Core Ultra 7 255H, 64 GB RAM, 6×SATA + 2×NVMe, dual 10 GbE
- ROBS-PC freed of DB duties, stays as subnet gateway

### Phase 5: Customer Deployment Model (Ongoing)
- 1 Mac mini per customer site (1-2 containers, max ~500 miners each)
- ROBS-PC = MASTER Intelligence Catalog (golden copy)
- Customer Mac minis get READ copies updated monthly
- Monthly federation: each site exports knowledge → Bobby merges → master pushed back
- No internet required for knowledge sync (USB/sneakernet works)

---

## 6. Backup Topology

### guardian.db (Production)
1. **Big-Bobby-T9 drive** — Mac cron every 5 min: rolling 12 copies + daily snapshots (30 days)
2. **GitHub** — `knowledge_backup.json` daily 4am push
3. **VPS local** — live database file

### Intelligence Catalog (Research)
1. **Primary** — Live DB on ROBS-PC Docker container
2. **Local backup** — `D:\MiningGuardian\db-backups\` (daily pg_dump, 14-day retention)
3. **Off-site** — Encrypted nightly to Backblaze B2 (planned, 30-day remote retention)

### 3-2-1 Rule Target
- 3 copies of all data
- 2 different media (SSD + cloud)
- 1 off-site

---

## 7. Slack Channel Architecture

| Channel | Purpose |
|---------|---------|
| #mining-guardian | Main channel — operator commands, fleet intelligence bot |
| #mining-guardian-alerts | Urgent alerts (offline, dead boards) |
| #mg-scans | Raw scan data dumps |
| #mg-ai-reports | AI analysis posts (1/hour), morning kickoff |
| #mg-approvals | Approval requests with Block Kit buttons |
| #mg-logs | Log collection status, failure reports |

---

## 8. Security Model

- All credentials in `.env` on VPS — never in source code, 17 keys required
- Postgres Intelligence Catalog password: randomly generated 32 chars, stored only on ROBS-PC
- approval_api.py: localhost bind, CORS restricted, shared secret required, Slack signature + replay protection
- dashboard_api.py: CORS locked to known domains, XSS escaping, param bounds clamped
- Slack: authorized user allowlist via `AUTHORIZED_SLACK_USER_IDS`
- No public ingress at customer sites — outbound only (AMS, Slack Socket Mode, Claude API, Open-Meteo)
- Pool management and miner settings are out of scope (security policy)

---

*Update this document whenever the architecture changes — new hardware, new services, migration milestones, or topology changes.*
