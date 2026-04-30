# 01 — Vision & Scope

---

## In one sentence

**Mining Guardian is a fleet command center for Bitcoin SHA-256 mining operators — a local-first web app that monitors miners, flags problems, asks the operator before remediating, and reports on profitability — all running on the customer's own hardware, with the operator's data never leaving their premises.**

---

## Who uses it

**Primary user (v1): the operator.** That's you. Single human at a single mining site, watching a fleet of S19/S21-class ASIC miners.

**Future users (post-v1):**
- A second operator at the same site (delegated approvals)
- A maintenance technician (read-only fleet view, no approve/deny power)
- A multi-site operator (one app, several Mac Minis)

We are explicitly NOT building for:
- Solo home miners with 1–3 machines (overkill)
- Pool operators (different problem)
- Web3 / altcoin / DeFi (not our market)
- Cloud SaaS customers (local-first is a hard rule)

---

## What problem this solves (operator's own words)

When a miner overheats at 2am, three things have to happen fast:
1. **Detect** the problem
2. **Decide** what to do (restart? throttle? leave it alone?)
3. **Act** safely (without bricking firmware or skipping a real fault)

Today most operators get a Slack ping at 2am and have to SSH into the miner half-asleep. That's slow, error-prone, and burns out the operator. Mining Guardian's existing backend already detects the problem and posts a Slack message. **The customer app's job is to be the better-than-Slack interface for steps 2 and 3** — and to give the operator confidence that the system is paying attention even when they're not.

Secondary value: **profitability and reporting.** Operators want a single screen that shows "are we making money today?" with hashrate, power draw, BTC price, and predicted P&L. The Intelligence Report feature delivers this.

---

## What v1 does (and doesn't)

### v1 features (MVP — scope-locked)

| Feature | Why it's v1 | Backend already exists? |
|---|---|---|
| **Approve/deny dashboard** for AI-suggested actions (restart, throttle, alert, no-op) with optional explanation field | Slack works today but is fiddly. The web alternative was explicitly called out in the backlog. | Yes — `approval_api.py` on port 8686 |
| **Fleet view** — list of miners with health, hashrate, temp, last seen | Replaces Grafana for basic ops; Grafana stays for power users | Yes — `dashboard-api` on port 8080 |
| **Mode selector** — Full Auto / Semi-Auto / Manual | The Semi/Manual modes are how operators learn to trust the system | Yes — `system_settings` table (migration 005) |
| **Schedule editor** — set scan cadence, pause windows, blackout hours | Customers shouldn't need cron/zsh knowledge to change schedules | Partial — `system_schedules` table (migration 005); UI is new |
| **Intelligence Report** — daily summary with fleet health, BTC price, profitability estimate, recommendations | The flagship "are we making money" screen | Yes — `intelligence_report_api.py` |
| **Settings** — Slack tokens, AMS credentials, miner site location, alert thresholds | All of these currently live in env files; non-engineers can't edit them safely | Partial — env-based today; needs DB-backed UI |
| **Login / lock screen** — single operator, password-protected | Required because the app is now reachable from any device on the LAN | New |

### v1 explicitly NOT building

- Mobile native apps (responsive web works for phone/tablet in v1)
- Multi-user permissions / roles
- Multi-tenant / multi-site management
- Pool integration
- Wallet integration / payouts
- Tax reports / accounting export
- Real-time graph dashboards (use Grafana for now)
- Public-internet exposure (LAN-only or VPN/Tailscale only — see questionnaire)

---

## What success looks like at v1

You sign off on these or v1 isn't done:

1. You can approve/deny an AI-suggested action from your phone (still on home WiFi) without opening Slack.
2. You can change the scan schedule from the app without touching cron, plists, or zsh.
3. You can show the Intelligence Report to a guest and they understand "the fleet made money today" within 10 seconds.
4. You can install the app fresh on a clean Mac Mini following only the existing install-day runbook plus one new step ("open `https://mg-mac-mini.local:8443` and log in").
5. You go a full week without SSH'ing into the Mac Mini for any operational reason.

---

## Constraints that shape every decision below

1. **Local-first.** App runs on the Mac Mini. Reachable from devices on the same LAN. Optionally reachable over Tailscale/VPN — never public internet.
2. **One operator.** No multi-user complexity in v1.
3. **No cloud LLMs.** AI features (Intelligence Report summaries, action recommendations) call the local Ollama (`qwen2.5:7b`) only.
4. **Headless host.** The Mac Mini has no monitor/keyboard post-install. The app must be 100% controllable from another device on the LAN.
5. **The brand system is locked.** See file 04. Don't relitigate colors and fonts.
6. **Voice is locked.** Confident, plain-spoken, no marketing fluff. See `branding/BRANDING.md`.
7. **Documentation is mandatory.** Every PR has a doc update. Every decision is captured in this folder.

---

## Where this fits in the bigger picture

```
┌──────────────────────────────────────────────────────────────┐
│                  Mac Mini (local, headless)                   │
│                                                                │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐ │
│  │  9 launchd  │→ │  Postgres 16 │← │  Customer App (NEW)  │ │
│  │   daemons   │  │   (3 DBs)    │  │   ↓                  │ │
│  └─────────────┘  └──────────────┘  │   Fastify/Express    │ │
│         ↓                ↑           │   serves React UI    │ │
│  ┌─────────────┐         │           │   on :8443 (HTTPS)   │ │
│  │  AMS/miners │         │           └──────────────────────┘ │
│  └─────────────┘         │                    ↑               │
│         ↓                │                    │               │
│  ┌─────────────┐  ┌──────┴──────┐             │               │
│  │   Slack     │← │ approval_api│ ←───────────┘               │
│  │ (existing)  │  │   :8686     │  (app calls same API)       │
│  └─────────────┘  └─────────────┘                             │
│                                                                │
└──────────────────────────────────────────────────────────────┘
                            ↑
                            │ HTTPS over LAN (or Tailscale)
                            │
                  ┌─────────┴─────────┐
                  │   Operator phone  │
                  │  Operator laptop  │
                  │ Operator browser  │
                  └───────────────────┘
```

The app is a **thin presentation layer** over APIs that mostly already exist. We are not rebuilding the backend. We are giving it a face.

---

*Next: read `02_QUESTIONNAIRE.md` for the decisions you have to make.*
