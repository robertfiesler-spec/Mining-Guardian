# Mining Guardian — Full Capabilities

BiXBiT USA | Fort Worth, TX | April 2026

---

## What It Does Today

### 🔍 Fleet Monitoring
- Scans all 58 miners every hourutes via AMS WebSocket API
- Three-tier hashrate evaluation:
  - Tier 1: Parses live BiXBiT firmware profile strings (exact rated TH/s)
  - Tier 2: Known model specs from miner_specs.json
  - Tier 3: 3-day learned baseline for unknown models
- Per-board hashboard analysis — detects which specific board is dead
- Offline verification — checks miner directly before flagging (avoids false alarms)
- Temperature monitoring — 84°C red only (no yellow tier), same threshold across all cooling types
- Sensor error detection — flags invalid temp readings separately from true overheats
- PDU power reading always takes priority over miner-reported consumption
- AMS sync detection — catches when AMS says offline but miner is actually alive
- AMS notifications pulled every scan — catches issues Mining Guardian's rules might miss

### 🧠 Two-Tier AI Intelligence
- **Local (Qwen 32B on RTX 4090):** Runs on every scan, ~4.6 seconds per analysis
  - Diagnoses issues, recommends actions, identifies patterns
  - All responses reference actual miner IPs and real data
- **Cloud (Claude API):** Used for deep intelligence tasks
  - Conversational fleet Q&A with full history context
  - Weekly deep training (Sundays 3am)
  - Knowledge merges and synthesis

### 💬 Conversational Fleet Intelligence (Slack)
Ask anything in #mining-guardian and get a fleet-aware answer:
- `status` — current fleet overview
- `hot` — miners in yellow/red temp zone
- `dead` — known dead boards
- `btc` — Bitcoin price + revenue estimate
- `knowledge` — what AI has learned about your fleet
- `audit` — last 10 actions with timestamps
- `overnight` — full overnight report
- `predict` — which miners are most likely to fail next (pattern-based)
- `miner 192.168.188.36` — 14-day deep dive on one miner
- Any natural language question — AI answers with real fleet data, history, patterns

### ✅ Approval System
- Every scan with actionable miners posts a numbered list in the thread
- Reply options: `APPROVE`, `DENY`, `approve 1,3`, `approve .36,.46`
- Pre-approval context posts before execution showing 7-day flag history
- Audit trail logs every decision with timestamp, user, and outcome
- Known dead board miners are automatically excluded from approval queue

### 🔴 Dead Board Lifecycle (Fully Automated)
1. Dead board detected → restart + log collection (before and after)
2. Board still dead → AMS ticket auto-created with full diagnostic description
3. Next Slack report → one-time notice: "ticket created, miner removed"
4. All future reports → miner silently suppressed
5. Board physically repaired → resolve in AMS → monitoring resumes automatically

### 🌙 Overnight Automation (10pm–6am)
- First firmware restart attempt → executes automatically (no approval needed)
- First PDU cycle attempt → executes automatically
- Already restarted tonight → skips, holds for morning
- Dead board restart → always manual, always your call
- No PDU assigned → always manual, always your call
- 6am: posts overnight summary via OpenClaw to Slack
- 7am: morning briefing cron with full overnight report

### 📊 Retool Dashboard (dashboard.fieslerfamily.com)
- Live stat tiles: fleet totals, online/offline, issue counts
- Currently Flagged table: real-time from latest scan
- Warehouse Power chart: live PDU + immersion tank readings, 30s refresh
- Environment chart: 5-day supply/return water + outside temp + humidity trend
- AI Insights panel: last 20 LLM analyses with miner IDs and response times

### 🏭 Dual HVAC Systems (April 2026)
**Two separate cooling systems monitored:**

**Warehouse HVAC (192.168.188.235)** — Serves Hydros, S21 Immersion, AH3880
- Supply/return water temps, differential pressure, ΔT
- CW pump 1 & 2 VFD frequencies, CT fan 1 & 2 VFD frequencies
- Alarm detection: leak, tower vibration, CT fault, pump fault

**S19J Pro Container (192.168.189.235)** — Serves S19J Pros only
- Supply/return water temps, ΔT, container space temp, outside air temp
- CT fans manually at 100% (no VFD feedback — intentional)
- CT trip detection, CWP trip detection, leak/basin alarms

**Architecture:** Mac polls both systems every hour, pushes to VPS API.
All AI analysis uses correct HVAC system per miner type.

### 🧪 Persistent Learning (Knowledge System)
- knowledge.json updates after every scan
- 58 miners, 50 known issues, 22 refined insights, 6 operator rules (as of Apr 2026)
- Patterns include: Chain[3] detachment signatures, dead board vs firmware distinction,
  environmental vs single-miner overheating, firmware mismatch detection
- Deduplication runs on every save — patterns never repeat
- Daily backup to GitHub at 4am
- Weekly deep training synthesizes all accumulated data via Claude API

### 💾 Backup & Reliability
- guardian.db backed up to Big-Bobby-T9 every hour (when Mac is connected)
- Rolling 12 copies + daily snapshots (30 days retention)
- VPS has its own live copy growing continuously
- knowledge_backup.json pushed to GitHub daily
- All 7 services auto-restart on VPS reboot
- Mac completely optional — everything runs on VPS + Windows PC

### 📋 Audit Trail
- Every action logged permanently: timestamp, miner, IP, model, problem,
  action taken, decision, who approved, Slack user ID
- Never expires, queryable by date or miner
- Used by AI for pre-approval context and pattern learning

---

## What's Coming (Planned)

### 🔧 Short Term (When Mac Mini Arrives)
- **Mac Mini on-site deployment** — replaces VPS, lives on the mining network directly
- **Direct miner API access** — port 4028 (Bitmain/WhatsMiner), port 8443 (Auradine)
  - Enables richer diagnostics without going through AMS
  - WhatsMiner Extended Partner API: set_user_power_limit, get/set_liquid_cooling
- **Auradine AH3880 full integration** — third firmware path, turbo/eco profile switching
- **Container monitoring** — BiXBiT container system fully mapped and ready to activate
  - Supply/return temps, pressures, flow rate, conductivity
  - Pump frequencies, fan status, PUE, power by rack zone
  - Requires BiXBiT to grant container API access

### 📚 Near Term (When Repair Shop Data Arrives)
- **Repair shop data ingestion** — 1M+ data points + logs from partner shop
  - Failure signature library built from real-world board failures
  - combine_knowledge.py merges external knowledge into master_knowledge.json
  - Dramatically improves predictive failure detection
- **Failure signature matching** — compare current log patterns against known failure signatures
  - "This CGMiner log pattern matches 87% of dead boards seen at repair shop"

### 🤖 OpenClaw Deep Integration (Next Major Phase)
Right now OpenClaw is a smart Slack writer. The next phase makes it the coordination brain:

- **OpenClaw queries the database directly** — instead of receiving pre-packaged data,
  it pulls whatever it needs: flag history, patterns, audit logs, HVAC trends
- **Approval reasoning** — before showing you the approval list, OpenClaw evaluates each
  miner against history and says: "I recommend approving .46 but not .195 — here's why"
- **Autonomous ticket creation** — OpenClaw notices a pattern (3 dead boards this month,
  all S19JPros, all Chain[3]) and creates an AMS investigation ticket automatically
- **Proactive outreach** — OpenClaw messages you when it detects a slow decline:
  "Miner .227 has dropped 18 TH/s over 72 hours. Matches early dead board signature."
- **Post-action learning** — after every restart, OpenClaw records what worked and what
  didn't, building a personal knowledge base of your specific fleet's failure patterns

### 🌐 Multi-Site (Long Term)
- **Federated knowledge** — each Mac Mini exports monthly knowledge.json
- **combine_knowledge.py** merges all sites weighted by confidence
- **master_knowledge.json** pushed back to all customers
- **USB or manual transfer** — no internet required at remote sites
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
| Fleet monitoring (all 58 miners) | ✅ Live |
| Three-tier hashrate evaluation | ✅ Live |
| Dead board detection + restart flow | ✅ Live |
| AMS ticket auto-creation | ✅ Live |
| Overnight autonomous actions | ✅ Live |
| Conversational AI (ask anything) | ✅ Live |
| Predictive failure warnings | ✅ Live (pattern-based) |
| Retool dashboard | ✅ Live |
| HVAC/mechanical monitoring | ✅ Live |
| Persistent learning knowledge base | ✅ Live |
| Dead board suppression | ✅ Live |
| Container monitoring | 🔶 Built, waiting for access |
| Repair shop data ingestion | 🔶 Waiting for data |
| Mac Mini on-site deployment | 🔶 Delayed ~1 month |
| Auradine direct API (port 8443) | 🔶 Planned |
| OpenClaw deep integration | 🔶 Planned |
| Multi-site federated knowledge | 🔮 Future |
| Confidence-scored failure predictions | 🔮 Future |
