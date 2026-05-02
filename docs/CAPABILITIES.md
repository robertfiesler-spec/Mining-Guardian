# Mining Guardian — Full Capabilities

BiXBiT USA | Fort Worth, TX | as of 2026-04-29 (last day before the 2026-04-30 Mac Mini install)

---

## What It Does Today

### 🔍 Fleet Monitoring
- Scans the operator's fleet on a schedule (default hourly; the operator can adjust the cadence and the active window per `docs/OPERATOR_SCHEDULES.md`) via the AMS WebSocket API
- Three-tier hashrate evaluation:
  - Tier 1: Parses live BiXBiT firmware profile strings (exact rated TH/s)
  - Tier 2: Known model specs from the Mining Intelligence Catalog (`hardware.miner_models`, 320 SHA-256 miners seeded at v1.0.2 build (count grows as models are added))
  - Tier 3: 3-day learned baseline for unknown models
- Per-board hashboard analysis — detects which specific board is dead
- Offline verification — checks miner directly before flagging (avoids false alarms)
- Temperature monitoring — 84°C red only (no yellow tier), same threshold across all cooling types
- Sensor error detection — flags invalid temp readings separately from true overheats
- PDU power reading always takes priority over miner-reported consumption
- AMS sync detection — catches when AMS says offline but miner is actually alive
- AMS notifications pulled every scan — catches issues Mining Guardian's rules might miss

### 🧠 Two-Tier AI Intelligence
- **Local (Ollama on the Mac Mini):** Runs on every scan
  - Model is auto-selected at install time based on available RAM (per D-13): `llama3.2:3b` on 16 GB hosts, `qwen2.5:14b-instruct-q4_K_M` on 24 GB+ hosts. Customer can override during install.
  - Diagnoses issues, recommends actions, identifies patterns
  - All responses reference actual miner IPs and real data
- **Cloud (Claude API, opt-in):** Used for deep intelligence tasks
  - Conversational fleet Q&A with full history context
  - Weekly deep training (Sundays 3 a.m.)
  - Knowledge merges and synthesis

### 💬 Conversational Fleet Intelligence (Slack)
Ask anything in `#mining-guardian` and get a fleet-aware answer:
- `status` — current fleet overview
- `hot` — miners in yellow/red temp zone
- `dead` — known dead boards
- `btc` — Bitcoin price + revenue estimate
- `knowledge` — what AI has learned about your fleet
- `audit` — last 10 actions with timestamps
- `overnight` — full overnight report
- `predict` — which miners are most likely to fail next (pattern-based)
- `miner <ip>` — 14-day deep dive on one miner
- Any natural language question — AI answers with real fleet data, history, patterns

### ✅ Approval System
- Every scan with actionable miners posts a numbered list in the thread (Slack and the Web GUI Operator Console)
- Reply options (Slack): `APPROVE`, `DENY`, `approve 1,3`, `approve .36,.46`
- Web GUI: per-miner approve/deny + bulk select
- Pre-approval context posts before execution showing 7-day flag history
- Audit trail logs every decision with timestamp, user, and outcome
- Known dead board miners are automatically excluded from approval queue
- **Automation mode** (per §10.1, default `manual`): `full_auto` / `semi_auto` / `manual` — operator-controlled, gates which actions execute without approval

### 🔴 Dead Board Lifecycle (Fully Automated)
1. Dead board detected → restart + log collection (before and after)
2. Board still dead → AMS ticket auto-created with full diagnostic description
3. Next Slack report → one-time notice: "ticket created, miner removed"
4. All future reports → miner silently suppressed
5. Board physically repaired → resolve in AMS → monitoring resumes automatically

### 🌙 Overnight Automation (operator-defined window, default 10 p.m.–6 a.m.)
- First firmware restart attempt → executes automatically when automation mode allows it
- First PDU cycle attempt → executes automatically when automation mode allows it
- Already restarted tonight → skips, holds for morning
- Dead board restart → always manual, always your call
- No PDU assigned → always manual, always your call
- End of window: posts overnight summary to Slack
- Morning: morning briefing cron with full overnight report

### 📊 Web GUI Operator Console (loopback on the Mac Mini)
- Live stat tiles: fleet totals, online/offline, issue counts
- Currently Flagged table: real-time from latest scan
- Approval queue with bulk select
- Schedule editor (per-job cadence + active window)
- Mode selector (`full_auto` / `semi_auto` / `manual`)
- AI Insights panel: recent LLM analyses with miner IDs and response times
- Remote operator access is via Tailscale to the Mini; the Web GUI is not exposed to the public internet.

### 🏭 Dual HVAC Systems
**Two separate cooling systems monitored:**

**Warehouse HVAC (192.168.188.235)** — Serves Hydros, S21 Immersion, AH3880
- Supply/return water temps, differential pressure, ΔT
- CW pump 1 & 2 VFD frequencies, CT fan 1 & 2 VFD frequencies
- Alarm detection: leak, tower vibration, CT fault, pump fault

**S19J Pro Container (192.168.189.235)** — Serves S19J Pros only
- Supply/return water temps, ΔT, container space temp, outside air temp
- CT fans manually at 100% (no VFD feedback — intentional)
- CT trip detection, CWP trip detection, leak/basin alarms

**Architecture:** Mining Guardian (on the Mac Mini) polls both HVAC systems on the operator's schedule and persists readings to the operational Postgres DB. AI analysis uses the correct HVAC system per miner type.

### 🧪 Persistent Learning (Knowledge System)
- Operational outcomes write back to the Mining Intelligence Catalog continuously (D-14 live-reference architecture, no scheduled refresh) — the catalog is effectively-current to within ~100 ms of any operational write
- Patterns include: Chain[3] detachment signatures, dead board vs firmware distinction, environmental vs single-miner overheating, firmware mismatch detection, AH3880 firmware regression signatures (April 2026 case study)
- Deduplication on every catalog write
- Daily backup of the catalog DB
- Weekly deep training synthesizes accumulated data via Claude API (opt-in)

### 💾 Backup & Reliability
- Catalog DB and operational DB both backed up to local storage daily (one Postgres `pg_dump` per DB, retention configurable; default 30 days)
- Knowledge / catalog seed CSVs are versioned in the repo (`intelligence-catalog/seed-data/`)
- All MG services run under launchd on the Mac Mini and auto-restart on reboot

### 📋 Audit Trail
- Every action logged permanently: timestamp, miner, IP, model, problem, action taken, decision, who approved, Slack user ID
- Never expires, queryable by date or miner
- Used by AI for pre-approval context and pattern learning, and fed back into the catalog (D-14)

---

## What's Coming (Planned)

### 🔧 Short Term (Post Mac Mini Install)
- **Direct miner API access** — port 4028 (Bitmain/WhatsMiner), port 8443 (Auradine)
  - Enables richer diagnostics without going through AMS
  - WhatsMiner Extended Partner API: `set_user_power_limit`, `get/set_liquid_cooling`
- **Auradine AH3880 full integration** — third firmware path, turbo/eco profile switching
- **Container monitoring** — BiXBiT container system fully mapped and ready to activate (see `docs/CONTAINER_MONITORING.md`)
  - Supply/return temps, pressures, flow rate, conductivity
  - Pump frequencies, fan status, PUE, power by rack zone
  - Requires BiXBiT to grant container API access in the customer's workspace

### 📚 Near Term (When Repair Shop Data Arrives)
- **Repair shop data ingestion** — 1M+ data points + logs from partner shop
  - Failure signature library built from real-world board failures, ingested into the catalog (`market.war_stories`, `ops.failure_patterns`)
  - Dramatically improves predictive failure detection
- **Failure signature matching** — compare current log patterns against known failure signatures
  - "This CGMiner log pattern matches 87% of dead boards seen at repair shop"

### 🌐 Multi-Site (Long Term)
- **Federated knowledge** — each customer's Mac Mini exports monthly catalog deltas
- **Catalog merge tool** combines site deltas weighted by confidence
- **Master catalog snapshot** pushed back to all customers
- **USB or manual transfer** — no public internet required at remote sites
- Every BiXBiT customer's fleet makes every other customer's system smarter

### 📱 Notifications (Future)
- Critical alerts push to iPhone via Slack
- Escalation DM if same miner flagged 3+ consecutive scans and not acknowledged
- Daily revenue summary at end of each day
- Weekly performance report every Monday morning

### 🔮 Predictive Failure (Future)
- Trend analysis: hashrate declining over days, not just single-scan drops
- Power consumption anomalies (drawing more watts for same TH/s = chip degradation)
- Temperature creep detection (gradually rising over weeks = cooling system issue)
- Cross-miner correlation: multiple miners in same rack section failing = PSU problem
- Confidence-scored failure predictions: "72% chance .36 needs board replacement in 7 days"

---

## Summary

| Category | Status |
|----------|--------|
| Fleet monitoring (operator-scheduled) | ✅ Live |
| Three-tier hashrate evaluation | ✅ Live |
| Dead board detection + restart flow | ✅ Live |
| AMS ticket auto-creation | ✅ Live |
| Overnight autonomous actions (mode-gated) | ✅ Live |
| Conversational AI (ask anything) | ✅ Live |
| Predictive failure warnings (pattern-based) | ✅ Live |
| Web GUI Operator Console (§10.1, §10.2, §10.7) | ✅ Live |
| HVAC/mechanical monitoring | ✅ Live |
| Persistent learning via the Mining Intelligence Catalog (D-14) | ✅ Live |
| Dead board suppression | ✅ Live |
| Mac Mini on-site deployment | 🔶 Installs 2026-04-30 |
| Container monitoring | 🔶 Built, waiting for BiXBiT API access |
| Repair shop data ingestion | 🔶 Waiting for data |
| Auradine direct API (port 8443) | 🔶 Planned |
| Multi-site federated catalog | 🔮 Future |
| Confidence-scored failure predictions | 🔮 Future |
