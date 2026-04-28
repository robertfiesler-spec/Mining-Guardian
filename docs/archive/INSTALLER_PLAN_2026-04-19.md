> **HISTORICAL — ARCHIVED 2026-04-28**
>
> This file was extracted from the `installer-build` branch before that branch
> was archived as `archive/installer-build-20260428`. It pre-dates the
> Postgres migration (2026-04-23), the D-13 RAM-detected Ollama model
> decision (2026-04-28), and the Option γ cutover scope. It is preserved here
> for historical reference and as design input for the active installer
> branch `mg/pr26-mac-mini-installer`. **Do not treat it as the current
> installer spec.** The live spec lives on `mg/pr26-mac-mini-installer`.

---

# Mining Guardian — Installer Build Master Plan
## The Complete Blueprint for Customer Deployment

**Author:** Computer (Lead Architect)
**Created:** April 19, 2026
**Branch:** `installer-build`
**Target:** Mac Mini (macOS primary, Linux secondary)
**Timeline:** 2 weeks → Mac Mini arrival early May 2026

---

## Executive Summary

This document is the single source of truth for building the Mining Guardian customer installer. It replaces and supersedes the original `DEPLOYMENT.md` spec where that spec was incomplete or wrong. Every screen, every script, every file, every validation step is defined here. Nothing gets built without being in this plan first.

The installer is a Rich-based terminal wizard (`wizard.py`) that walks a customer through setup in ~15 minutes with zero ambiguity. Professional, colorful, impossible to mess up.

---

## What Already Exists (Audit Results)

Before building anything, here's what we have to work with:

### Usable As-Is
- **`branding/`** — 9 logo assets (PNG, transparent variants, icon, wordmark, stacked)
- **`.env.example`** — Complete env var reference (AMS, Slack, LLM, HVAC, PDU, Claude, Catalog, OpenClaw) — 60+ variables documented
- **`config/config_template.json`** — Working config with profile_map examples (S19JPro, AH3880, S21EXPHyd, S21Imm)
- **`deploy/*.service`** — 8 systemd unit files (Linux path, but templates are correct)
- **`intelligence-catalog/`** — Full catalog API with Docker Compose, schema SQL, 238-model index

### Usable But Needs Rework
- **`scripts/setup.sh`** — Old BiXBiT-branded zsh script. Has the right bones (venv, .env, config, launchd, Slack test) but:
  - Hardcoded paths (`/Users/BigBobby/`)
  - Missing most services (only installs main daemon, not all 8)
  - No Grafana/Prometheus setup
  - No LLM setup
  - No fleet discovery
  - No verification beyond a single test scan
  - Read-based input (no validation, no color, no error recovery)
- **`scripts/start_guardian.sh`** — Hardcoded to BigBobby's path. Needs to be generated dynamically.
- **`deploy/*.service`** — All hardcoded to `/root/Mining-Gaurdian`. Need to be templates with `{{INSTALL_DIR}}` placeholders.

### Does Not Exist Yet (Must Build)
- `wizard.py` — Interactive Rich-based configuration wizard
- `install.sh` — New entry point (replaces setup.sh)
- `setup_services.py` — Cross-platform service installer (launchd + systemd)
- `import_dashboards.py` — Grafana dashboard provisioning
- `first_run.py` — Fleet discovery and calibration
- `verify.py` — Post-install health check
- `update.sh` — Update mechanism preserving config/DB
- `uninstall.sh` — Clean removal
- Grafana dashboard JSON exports (need to export all 6 from current Grafana)
- `prometheus.yml` template
- Grafana provisioning configs (datasource + dashboard auto-import)
- `launchd/` plist templates for macOS
- `requirements.txt` — Consolidated dependency list

---

## Architecture Decision: Why Rich, Not a Web UI

The installer runs in Terminal. Not a browser. Reasons:
1. **Zero dependencies at install time** — Rich is a pip package, not a web server
2. **SSH-compatible** — Customer might SSH into the Mac Mini for setup
3. **Copy-paste friendly** — Every value entered can be logged and reproduced
4. **Professional** — Rich gives us full-color panels, progress bars, tables, tree views, and spinners that look better than most web forms
5. **Deterministic** — No browser rendering differences, no CORS, no port conflicts during install

---

## The 11 Screens

Each screen is a self-contained step. The wizard saves progress after each screen so if it crashes or the user quits, they resume where they left off (state saved to `~/.mining-guardian-install.json`).

Screen navigation: `[Enter]` to proceed, `[B]` to go back, `[Q]` to quit (with save).

---

### Screen 1: Welcome

```
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║          ⛏️  MINING GUARDIAN — INSTALLER v1.0                ║
║                                                              ║
║    The most intelligent Bitcoin mining fleet manager          ║
║    on the planet. Local-first. AI-powered. Zero cloud.       ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

  Welcome! This wizard will set up Mining Guardian on this
  machine in about 15 minutes.

  What we'll do:
  ─────────────────────────────────────────────────────────────
   1.  Check this machine meets requirements
   2.  Configure your site identity
   3.  Connect to your BiXBiT AMS
   4.  Discover your miner fleet
   5.  Set up Slack notifications
   6.  Set up local AI (optional)
   7.  Review everything
   8.  Install all services
   9.  Verify everything works
  ─────────────────────────────────────────────────────────────

  Estimated time: 10-15 minutes
  You can quit anytime — progress is saved automatically.

  [Press Enter to begin]
```

**What happens:** Display only. Sets the tone. On Enter, proceed to Screen 2.

---

### Screen 2: Pre-Flight Check

```
╔══════════════════════════════════════════════════════════════╗
║  PRE-FLIGHT CHECK                                    [2/11] ║
╚══════════════════════════════════════════════════════════════╝

  Checking system requirements...

  ✅  Operating System     macOS 14.2 (Sonoma) — ARM64
  ✅  Python               3.12.1 (/usr/bin/python3)
  ✅  RAM                  16 GB (16 GB recommended)
  ✅  Disk Space           218 GB free (20 GB minimum)
  ✅  Network              LAN active (en0: 192.168.1.50)
  ✅  Internet             Connected (for initial setup only)
  ✅  Homebrew             Installed (needed for Prometheus/Grafana)
  ⚠️  Grafana              Not installed — will install in Step 8
  ⚠️  Prometheus           Not installed — will install in Step 8
  ⚠️  Ollama               Not installed — optional, configure in Step 6

  ─────────────────────────────────────────────────────────────
  Result: READY TO PROCEED (3 items will be installed later)
  ─────────────────────────────────────────────────────────────

  [Enter] Continue    [Q] Quit
```

**What happens behind the scenes:**
- `platform.system()` + `platform.machine()` → OS and arch
- `sys.version` → Python version (require 3.11+, hard fail below)
- `psutil.virtual_memory()` → RAM check (warn < 16GB, fail < 8GB)
- `shutil.disk_usage()` → Disk space (warn < 50GB, fail < 20GB)
- `socket` check → LAN interface detection
- `requests.get("https://httpbin.org/ip")` → Internet check
- `shutil.which("brew")` → Homebrew (macOS only — if missing, offer to install)
- `shutil.which("grafana-server")` → Grafana presence
- `shutil.which("prometheus")` → Prometheus presence
- `shutil.which("ollama")` → Ollama presence

**Hard Fails (cannot continue):**
- Python < 3.11
- RAM < 8 GB
- Disk < 20 GB
- No network interface

**Soft Warnings (continue with note):**
- RAM < 16 GB → "Local LLM may be slow"
- No Homebrew → "Will need Homebrew for Grafana/Prometheus — install it?"
- No internet → "Needed for Slack setup. Offline install available but limited."

---

### Screen 3: Site Configuration

```
╔══════════════════════════════════════════════════════════════╗
║  SITE CONFIGURATION                                  [3/11] ║
╚══════════════════════════════════════════════════════════════╝

  Tell us about this mining site.

  Site Name:          [USA 188                    ]
  Site ID:            [usa-188] (auto-generated, editable)
  Operator Name:      [Bobby Fiesler              ]
  Install Directory:  [~/mining-guardian] (recommended)

  ─────────────────────────────────────────────────────────────
  These values identify this site in logs, Slack messages,
  and the knowledge federation system.
  ─────────────────────────────────────────────────────────────

  [Enter] Continue    [B] Back    [Q] Quit
```

**What happens:**
- Rich `Prompt` for each field with validation
- Site ID auto-generated from site name (lowercase, hyphens, no spaces)
- Install directory defaults to `~/mining-guardian`, validated for write access
- All values saved to install state file

**Validation:**
- Site Name: 1-50 chars, not empty
- Site ID: lowercase alphanumeric + hyphens only, 1-30 chars
- Operator Name: 1-50 chars
- Install Dir: Must be writable, must have 20GB+ free on that volume

---

### Screen 4: AMS Connection

```
╔══════════════════════════════════════════════════════════════╗
║  AMS CONNECTION                                      [4/11] ║
╚══════════════════════════════════════════════════════════════╝

  Connect to your BiXBiT AMS (Advanced Mining System).

  AMS URL:         [https://api.bixbit.io/api/v1   ]
  Email:           [operator@example.com            ]
  Password:        [••••••••••••                    ]
  Workspace ID:    [                                ]

  ─────────────────────────────────────────────────────────────
  Testing connection...

  ✅  Login successful
  ✅  Workspace "USA 188" selected
  ✅  Found 247 miners in workspace
  ✅  API key retrieved: 70dd4d72-****-****-****-********93ca

  Connection verified! 247 miners detected.
  ─────────────────────────────────────────────────────────────

  [Enter] Continue    [B] Back    [Q] Quit
```

**What happens:**
- Prompt for AMS URL (default: `https://api.bixbit.io/api/v1`)
- Prompt for email, password (masked input), workspace ID
- On Enter after all fields: immediately test the connection
  - `POST /auth/login` → get token
  - `GET /workspaces/{id}` → verify workspace exists
  - `GET /miners` → count miners
  - Extract API key from workspace settings
- If login fails: red error panel, retry prompt ("Check credentials and try again")
- If workspace fails: show available workspaces in a numbered list, let user pick
- On success: show green confirmation with miner count
- Store: AMS URL, email, password, workspace ID, API key, miner count

**Validation:**
- AMS URL must be reachable (timeout 10s)
- Login must succeed
- Workspace must exist and contain at least 1 miner

---

### Screen 5: Fleet Discovery

```
╔══════════════════════════════════════════════════════════════╗
║  FLEET DISCOVERY                                     [5/11] ║
╚══════════════════════════════════════════════════════════════╝

  Scanning your fleet from AMS...

  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 247/247 miners

  Fleet Summary:
  ┌──────────────────────┬───────┬────────┬─────────┐
  │ Model                │ Count │ TH/s   │ Cooling  │
  ├──────────────────────┼───────┼────────┼─────────┤
  │ Antminer S21 EXP Hyd │    45 │ 430    │ Hydro   │
  │ Antminer S21 Imm     │   120 │ 200    │ Immersn │
  │ Teraflux AH3880      │    50 │ 300-600│ Hydro   │
  │ Antminer S19J Pro    │    32 │ 104-160│ Air     │
  │ Total                │   247 │        │         │
  └──────────────────────┴───────┴────────┴─────────┘

  Firmware Detection:
  • 195 miners: BiXBiT firmware (profile ranges detected)
  •  50 miners: Auradine firmware (named profiles: eco/turbo)
  •   2 miners: Stock firmware (fixed hashrate)

  PDU Mapping:
  • 215 miners mapped to PDU outlets
  •  32 miners have NO PDU (S19J Pro units — flagged)

  ─────────────────────────────────────────────────────────────
  Fleet profile will be saved to miner_specs.json.
  You can adjust individual miner specs later.
  ─────────────────────────────────────────────────────────────

  [Enter] Accept & Continue    [E] Edit a model    [B] Back
```

**What happens:**
- Full AMS scan using existing `mining_guardian.py` scan logic (import and call directly)
- Group miners by model string from AMS
- For each model group:
  - Match against Intelligence Catalog (`unified_miner_index.json`) for specs
  - Detect firmware type from AMS data (BiXBiT = profile ranges, Auradine = named profiles, Stock = fixed)
  - Auto-detect profile ranges from AMS profile data
- Scan PDU endpoints if available
- Build `miner_specs.json` from discovered fleet
- `[E]` opens a sub-menu to override specs for any model (stock TH/s, max TH/s, board count)

**Intelligence Catalog Integration:**
- The installer ships with a bundled copy of `unified_miner_index.json` (238 models)
- When a miner model is discovered, look it up in the catalog for: board count, cooling type, stock hashrate, chip type
- If a model is NOT in the catalog: flag it in yellow, prompt operator to enter specs manually
- This is the first place the catalog proves its value to the customer

**Per-Miner Override Sub-Screen (if [E] pressed):**
```
  Select model to edit:
  1. Antminer S21 EXP Hyd (45 units)
  2. Antminer S21 Imm (120 units)
  3. Teraflux AH3880 (50 units)
  4. Antminer S19J Pro (32 units)

  Choice: [2]

  Antminer S21 Imm — Current specs:
    Stock TH/s: 200    Max TH/s: 270    Boards: 3    Cooling: Immersion

  Edit field (or Enter to keep):
    Stock TH/s [200]: ___
    Max TH/s [270]: ___
    Board count [3]: ___

  ⚠️  Note: 3 S21 Imm units have different specs in AMS.
  Would you like to set per-miner overrides? [y/N]
```

---

### Screen 6: Slack Setup

```
╔══════════════════════════════════════════════════════════════╗
║  SLACK INTEGRATION                                   [6/11] ║
╚══════════════════════════════════════════════════════════════╝

  Mining Guardian uses Slack for notifications and
  approve/deny decisions.

  You need a Slack Bot with these scopes:
  • chat:write          (post messages)
  • channels:read       (find channels)
  • reactions:write     (react to messages)
  • commands            (slash commands)

  Bot Token (xoxb-...):   [                              ]
  Signing Secret:          [                              ]
  App Token (xapp-...):    [                              ]

  Main Channel:            [#mining-guardian              ]
  Authorized User IDs:     [U12345678                    ]
    (comma-separated — who can approve/deny actions)

  ─────────────────────────────────────────────────────────────
  Testing Slack connection...

  ✅  Bot token valid (Mining Guardian Bot)
  ✅  Channel #mining-guardian found
  ✅  Test message posted: "🛡️ Mining Guardian installer test"
  ✅  Authorized users verified: 1 user(s)

  ─────────────────────────────────────────────────────────────

  [Enter] Continue    [S] Skip (no Slack)    [B] Back
```

**What happens:**
- Prompt for bot token, signing secret, app token
- Prompt for main channel name (auto-prefixed with # if missing)
- Prompt for authorized user IDs
- Validation:
  - `slack_sdk.WebClient(token).auth_test()` → verify token
  - `conversations_list()` → find channel
  - `chat_postMessage()` → test post
- If token is invalid: red error, retry
- `[S]` skips Slack entirely — system runs without notifications (warn: "You will have no alerts")
- Store all Slack values

**Channel Auto-Setup Option:**
After successful connection, offer:
```
  Mining Guardian uses 6 Slack channels:
  #mining-guardian    (main alerts)
  #mg-scans          (scan reports)
  #mg-logs           (log analysis)
  #mg-ai-reports     (AI insights)
  #mg-alerts         (critical alerts)
  #mg-approvals      (approve/deny requests)

  Create missing channels automatically? [Y/n]
```

---

### Screen 7: Local LLM Setup

```
╔══════════════════════════════════════════════════════════════╗
║  LOCAL AI SETUP                                      [7/11] ║
╚══════════════════════════════════════════════════════════════╝

  Mining Guardian uses a local LLM for real-time analysis.
  This is optional but strongly recommended.

  ┌─────────────────────────────────────────────────────────┐
  │  Choose your AI setup:                                  │
  │                                                         │
  │  [1] Local Ollama (recommended if 16GB+ RAM)            │
  │      Runs on this machine. No internet needed.          │
  │                                                         │
  │  [2] Remote Ollama (via Tailscale)                      │
  │      Routes to a GPU box on your network.               │
  │                                                         │
  │  [3] Skip local AI                                      │
  │      System works without AI but loses smart analysis.  │
  └─────────────────────────────────────────────────────────┘

  Choice: [1]

  ─────────────────────────────────────────────────────────────
  Checking Ollama...

  ✅  Ollama installed (v0.6.2)
  ✅  Model: qwen2.5:32b-instruct-q4_K_M (loaded)
  ✅  Test inference: 847ms response time — excellent

  ─────────────────────────────────────────────────────────────

  Claude API Key (for weekly deep analysis):
  [sk-ant-•••••••••••••••                                    ]
  ✅  Claude API key valid (claude-sonnet-4-20250514)

  [Enter] Continue    [S] Skip all AI    [B] Back
```

**What happens:**
- Three-option menu for AI setup
- **Option 1 (Local Ollama):**
  - Check if Ollama installed (`shutil.which("ollama")`)
  - If not: "Install Ollama now? (requires Homebrew)" → `brew install ollama`
  - Check if model pulled: `ollama list`
  - If not: "Pull recommended model? (~20GB download)" → `ollama pull qwen2.5:32b-instruct-q4_K_M`
  - Test inference: send a test prompt, measure response time
  - Store: `OLLAMA_URL=http://localhost:11434`, model name
- **Option 2 (Remote Ollama):**
  - Prompt for Tailscale IP or LAN IP of GPU box
  - Test connectivity: `requests.get(f"http://{ip}:11434/api/tags")`
  - Store: `OLLAMA_URL=http://{ip}:11434`, model name
- **Option 3 (Skip):**
  - Warn: "Mining Guardian will run without AI scan analysis. Recommendations will be rule-based only."
  - Store: `OLLAMA_URL=` (empty)
- Claude API key prompt (separate from Ollama — used for weekly deep analysis)
  - Test: `anthropic.Client(key).messages.create(...)` with a tiny prompt
  - If skipped: weekly training disabled

---

### Screen 8: HVAC Configuration (Conditional)

```
╔══════════════════════════════════════════════════════════════╗
║  HVAC MONITORING (Optional)                          [8/11] ║
╚══════════════════════════════════════════════════════════════╝

  Does this site have HVAC controllers Mining Guardian
  should monitor?

  [1] Yes — Eclypse controller(s)
  [2] Yes — AV-2 Plant controller(s)
  [3] Yes — Other (Modbus/BACnet/REST)
  [4] No HVAC monitoring needed

  Choice: [4]

  ─────────────────────────────────────────────────────────────
  Skipping HVAC. You can add it later in config.json.
  ─────────────────────────────────────────────────────────────

  [Enter] Continue    [B] Back
```

**What happens:**
- If HVAC selected: prompt for controller IP, credentials, type
- Test connectivity to controller
- This screen is intentionally simple — HVAC is site-specific and most initial installs won't have it wired in yet
- Store HVAC config or skip

---

### Screen 9: Review

```
╔══════════════════════════════════════════════════════════════╗
║  REVIEW YOUR CONFIGURATION                           [9/11] ║
╚══════════════════════════════════════════════════════════════╝

  Please review everything before we install.

  ┌─ Site ──────────────────────────────────────────────────┐
  │  Name:        USA 188                                   │
  │  ID:          usa-188                                   │
  │  Operator:    Bobby Fiesler                             │
  │  Install to:  /Users/bobby/mining-guardian              │
  └─────────────────────────────────────────────────────────┘

  ┌─ AMS ───────────────────────────────────────────────────┐
  │  URL:         https://api.bixbit.io/api/v1              │
  │  Email:       operator@bixbit.com                       │
  │  Workspace:   42 (USA 188)                              │
  │  Miners:      247 detected                              │
  └─────────────────────────────────────────────────────────┘

  ┌─ Fleet ─────────────────────────────────────────────────┐
  │  S21 EXP Hyd:    45 units (BiXBiT firmware)             │
  │  S21 Imm:       120 units (BiXBiT firmware)             │
  │  AH3880:         50 units (Auradine firmware)           │
  │  S19J Pro:       32 units (BiXBiT firmware)             │
  │  PDU-mapped:    215 / 247                               │
  └─────────────────────────────────────────────────────────┘

  ┌─ Integrations ──────────────────────────────────────────┐
  │  Slack:       ✅ Connected (#mining-guardian)            │
  │  Local LLM:   ✅ Ollama (qwen2.5:32b)                  │
  │  Claude:      ✅ Weekly analysis enabled                 │
  │  HVAC:        ⏭️  Skipped                               │
  └─────────────────────────────────────────────────────────┘

  ─────────────────────────────────────────────────────────────

  [Enter] Install    [E] Edit a section    [Q] Quit (saved)
```

**What happens:**
- Read-only summary of all collected configuration
- `[E]` → numbered list of sections, pick one to jump back to that screen
- `[Enter]` → proceed to installation
- Everything displayed here comes from the install state file

---

### Screen 10: Installation

```
╔══════════════════════════════════════════════════════════════╗
║  INSTALLING MINING GUARDIAN                         [10/11] ║
╚══════════════════════════════════════════════════════════════╝

  Installing to /Users/bobby/mining-guardian...

  ✅  Created directory structure
  ✅  Created Python virtual environment
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100%  pip install
  ✅  Installed 24 Python packages
  ✅  Written config.json (14 settings)
  ✅  Written .env (28 secrets — chmod 600)
  ✅  Written miner_specs.json (4 models, 247 miners)
  ✅  Initialized guardian.db (22 tables)
  ✅  Installed 8 launchd services
  ✅  Installed Prometheus via Homebrew
  ✅  Written prometheus.yml (scrape targets configured)
  ✅  Installed Grafana via Homebrew
  ✅  Configured Grafana datasource (Prometheus)
  ✅  Imported 6 Grafana dashboards
  ✅  Started all services

  ─────────────────────────────────────────────────────────────
  Installation complete. Running verification...
  ─────────────────────────────────────────────────────────────

  [Press Enter to verify]
```

**What happens (in order):**

1. **Directory Structure**
   - Create `~/mining-guardian/` (or chosen path)
   - Copy entire repo contents (minus `.git`, `archive/`, `tests/`, `installer/`)
   - Create `logs/`, `backups/`, `dashboards/` dirs

2. **Python Environment**
   - `python3 -m venv venv`
   - `pip install -r requirements.txt` (with Rich progress bar on pip output)

3. **Configuration Files**
   - Generate `config.json` from collected wizard data + `config_template.json`
   - Generate `.env` from collected secrets
   - `chmod 600 .env`
   - Generate `miner_specs.json` from fleet discovery data
   - Copy `unified_miner_index.json` (Intelligence Catalog)

4. **Database**
   - Initialize `guardian.db` with schema (all 22 tables)
   - Run `knowledge.json` initialization
   - Set hashrate baselines to "learning" mode

5. **Services (macOS)**
   - Generate 8 launchd plist files in `~/Library/LaunchAgents/`:
     - `com.miningguardian.daemon.plist`
     - `com.miningguardian.dashboard-api.plist`
     - `com.miningguardian.approval-api.plist`
     - `com.miningguardian.slack-listener.plist`
     - `com.miningguardian.slack-commands.plist`
     - `com.miningguardian.overnight.plist`
     - `com.miningguardian.alerts.plist`
     - `com.miningguardian.intelligence-report.plist`
   - Each plist uses dynamically resolved paths (not hardcoded)
   - `launchctl load` each one

6. **Services (Linux fallback)**
   - Generate 8 systemd unit files from templates
   - `systemctl daemon-reload && systemctl enable --now` each one

7. **Prometheus**
   - macOS: `brew install prometheus` (if not present)
   - Write `prometheus.yml` with scrape targets:
     - `localhost:8585/metrics` (dashboard API)
     - `localhost:8686/metrics` (approval API)
     - `localhost:8590/metrics` (intelligence report API)
   - Start Prometheus service

8. **Grafana**
   - macOS: `brew install grafana` (if not present)
   - Configure datasource provisioning (Prometheus at `localhost:9090`)
   - Import all 6 dashboard JSONs via Grafana API:
     - Main Fleet Overview
     - Per-Miner Detail
     - AI Learning & Insights
     - Board Health
     - Pool Statistics
     - Intelligence Report
   - Set default dashboard to Main Fleet Overview
   - Start Grafana service

9. **First Run**
   - Execute first AMS scan
   - Build initial miner state readings
   - Collect first set of logs (if log collection configured)
   - Parse hardware identity for all miners
   - Set 72-hour learning window for hashrate baselines

10. **Slack Announcement**
    - Post to configured channel:
    ```
    🛡️ Mining Guardian is online
    Site: USA 188
    Fleet: 247 miners (4 models)
    Mode: DRY RUN (no actions until enabled)
    Dashboard: http://192.168.1.50:8585
    Grafana: http://192.168.1.50:3000
    ```

---

### Screen 11: Verification & Complete

```
╔══════════════════════════════════════════════════════════════╗
║  VERIFICATION                                       [11/11] ║
╚══════════════════════════════════════════════════════════════╝

  Running post-install health checks...

  Services:
  ✅  mining-guardian daemon      — running (PID 12045)
  ✅  dashboard-api (:8585)       — responding (200 OK)
  ✅  approval-api (:8686)        — responding (200 OK)
  ✅  intelligence-report (:8590) — responding (228 models loaded)
  ✅  slack-listener              — running (PID 12048)
  ✅  slack-commands              — running (PID 12049)
  ✅  overnight-automation        — running (PID 12050)
  ✅  alerts-listener             — running (PID 12051)

  External:
  ✅  Prometheus (:9090)          — scraping 3 targets
  ✅  Grafana (:3000)             — 6 dashboards loaded
  ✅  AMS connection              — stable (3/3 test scans)
  ✅  Slack                       — messages posting correctly

  Data:
  ✅  guardian.db                 — 247 miners in miner_readings
  ✅  miner_specs.json            — 4 models configured
  ✅  knowledge.json              — initialized

  ─────────────────────────────────────────────────────────────

  ╔════════════════════════════════════════════════════════════╗
  ║                                                            ║
  ║   ✅  MINING GUARDIAN IS LIVE                              ║
  ║                                                            ║
  ║   Site:       USA 188                                      ║
  ║   Fleet:      247 miners                                   ║
  ║   Dashboard:  http://192.168.1.50:8585                     ║
  ║   Grafana:    http://192.168.1.50:3000                     ║
  ║   Mode:       DRY RUN (safe mode)                          ║
  ║                                                            ║
  ║   To enable live actions:                                  ║
  ║   Edit ~/mining-guardian/config.json                       ║
  ║   Set "dry_run": false                                     ║
  ║                                                            ║
  ╚════════════════════════════════════════════════════════════╝

  Install log saved to: ~/mining-guardian/logs/install.log
```

**What happens:**
- HTTP health checks on all API ports
- `launchctl list | grep miningguardian` → verify services running
- 3 consecutive AMS scans (30s apart) → verify stable connection
- Check Grafana API for dashboard count
- Check Prometheus targets endpoint
- Query `guardian.db` for miner count
- Any failures: red error with troubleshooting hint
- All results logged to `install.log`

---

## File Manifest — What Gets Built

### installer/ directory (on this branch)

```
installer/
├── INSTALLER_PLAN.md           ← This document
├── DEPLOYMENT.md               ← Original spec (preserved for reference)
├── install.sh                  ← Entry point — OS detection, Python check, launches wizard
├── wizard.py                   ← The 11-screen Rich wizard (main file)
├── lib/
│   ├── __init__.py
│   ├── preflight.py            ← Screen 2: system checks
│   ├── ams_connect.py          ← Screen 4: AMS login + test
│   ├── fleet_discovery.py      ← Screen 5: scan + model matching
│   ├── slack_setup.py          ← Screen 6: Slack verification
│   ├── llm_setup.py            ← Screen 7: Ollama/Claude setup
│   ├── hvac_setup.py           ← Screen 8: HVAC config
│   ├── config_writer.py        ← Generates config.json, .env, miner_specs.json
│   ├── service_installer.py    ← Generates and installs launchd/systemd services
│   ├── grafana_setup.py        ← Prometheus/Grafana install + dashboard import
│   ├── first_run.py            ← Initial fleet scan + calibration
│   ├── verify.py               ← Post-install health checks
│   └── state.py                ← Install state save/resume logic
├── templates/
│   ├── config_template.json    ← Base config with all fields
│   ├── env_template            ← .env generator template
│   ├── launchd/                ← macOS plist templates (8 files)
│   │   ├── com.miningguardian.daemon.plist
│   │   ├── com.miningguardian.dashboard-api.plist
│   │   ├── com.miningguardian.approval-api.plist
│   │   ├── com.miningguardian.slack-listener.plist
│   │   ├── com.miningguardian.slack-commands.plist
│   │   ├── com.miningguardian.overnight.plist
│   │   ├── com.miningguardian.alerts.plist
│   │   └── com.miningguardian.intelligence-report.plist
│   ├── systemd/                ← Linux service templates (8 files)
│   │   └── (mirrors launchd/ structure as .service files)
│   ├── prometheus.yml.template
│   └── grafana/
│       ├── provisioning/
│       │   ├── datasources/prometheus.yml
│       │   └── dashboards/dashboards.yml
│       └── dashboards/         ← Exported dashboard JSONs (6 files)
│           ├── main-fleet-overview.json
│           ├── per-miner-detail.json
│           ├── ai-learning-insights.json
│           ├── board-health.json
│           ├── pool-statistics.json
│           └── intelligence-report.json
├── requirements.txt            ← All pip dependencies for Mining Guardian
├── update.sh                   ← Update mechanism (git pull, preserve config/DB, restart)
└── uninstall.sh                ← Clean removal (stop services, remove launchd, optionally delete data)
```

### Total file count: ~40 files

---

## Dependencies (requirements.txt)

```
# Core
requests>=2.31.0
websocket-client>=1.7.0
python-dotenv>=1.0.0

# API
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0

# Slack
slack-sdk>=3.27.0

# AI
anthropic>=0.18.0

# Monitoring
prometheus-client>=0.20.0

# Installer UI
rich>=13.7.0

# Utilities
psutil>=5.9.0
```

---

## Build Order (Sprint Plan)

### Week 1: Core Wizard + Services

| Day | Task | Files |
|-----|------|-------|
| Mon | `state.py` — save/resume logic + `wizard.py` skeleton with screen routing | `wizard.py`, `lib/state.py` |
| Mon | Screen 1 (Welcome) + Screen 2 (Pre-Flight) | `wizard.py`, `lib/preflight.py` |
| Tue | Screen 3 (Site Config) + Screen 4 (AMS Connection) | `wizard.py`, `lib/ams_connect.py` |
| Tue | Screen 5 (Fleet Discovery) — the big one | `lib/fleet_discovery.py` |
| Wed | Screen 6 (Slack) + Screen 7 (LLM) + Screen 8 (HVAC) | `lib/slack_setup.py`, `lib/llm_setup.py`, `lib/hvac_setup.py` |
| Thu | Screen 9 (Review) + `config_writer.py` | `wizard.py`, `lib/config_writer.py` |
| Thu | `requirements.txt` + `install.sh` entry point | `install.sh`, `requirements.txt` |
| Fri | `service_installer.py` + all 8 launchd plist templates | `lib/service_installer.py`, `templates/launchd/*` |
| Fri | All 8 systemd service templates (from existing `deploy/*.service`) | `templates/systemd/*` |

### Week 2: Grafana + Install + Verify + Polish

| Day | Task | Files |
|-----|------|-------|
| Mon | Export all 6 Grafana dashboards from live Grafana → JSON | `templates/grafana/dashboards/*` |
| Mon | `grafana_setup.py` — Prometheus install, Grafana install, provisioning | `lib/grafana_setup.py`, `templates/prometheus.yml.template`, `templates/grafana/provisioning/*` |
| Tue | Screen 10 (Installation) — the main install sequence | `wizard.py`, `lib/config_writer.py` |
| Tue | `first_run.py` — initial scan + calibration + learning mode | `lib/first_run.py` |
| Wed | Screen 11 (Verification) + `verify.py` | `wizard.py`, `lib/verify.py` |
| Wed | `update.sh` + `uninstall.sh` | `update.sh`, `uninstall.sh` |
| Thu | End-to-end dry run — run wizard start to finish on a clean environment | Testing |
| Thu | Bobby reviews every screen, we iterate on feedback | Polish |
| Fri | Final polish, commit, merge prep | All files |

---

## Screen Approval Process

We build each screen one at a time. For each screen:

1. I build the Rich screen with all logic
2. I take a screenshot/share the output
3. Bobby approves or requests changes
4. Once approved, we move to the next screen

No screen gets merged without Bobby's approval on the visual output.

---

## Key Design Rules

1. **Every screen fits in one terminal window** — no scrolling required (80x24 minimum)
2. **Color scheme:** Green = success, Yellow = warning, Red = error, Blue = info panels, Bold white = headers
3. **No jargon** — "AMS Connection" not "REST API Authentication". "Local AI" not "Ollama LLM Server"
4. **Every input has a default** — pressing Enter alone always does something reasonable
5. **Every connection is tested immediately** — no "trust me it'll work later"
6. **Progress saves after every screen** — crash recovery is mandatory
7. **Install log captures everything** — if something goes wrong post-install, the log tells the whole story
8. **Dry run by default** — no new install ever takes actions on miners without the operator explicitly enabling it

---

## Open Questions (Resolved from DEPLOYMENT.md)

| Original Question | Decision |
|---|---|
| Should local web dashboard replace Slack approve/deny? | **No.** Slack stays primary. Local dashboard is view-only for now. Future enhancement. |
| Ship Ollama pre-configured or installer handles it? | **Installer handles it.** Screen 7 walks through Ollama install + model pull. |
| Update mechanism — git pull or packaged releases? | **Git pull.** `update.sh` does `git pull`, preserves config/DB, restarts services. Simple and transparent. |
| Local backup strategy for guardian.db? | **Yes.** Daily cron backs up DB to `~/mining-guardian/backups/`. Time Machine is bonus, not the plan. |
| Headless (SSH-only) installation? | **Yes.** Rich works over SSH. No GUI required. This is terminal-native by design. |
| Multi-site Slack channels? | **Each site gets its own channel set.** Channel names configurable in Screen 6. No shared channels — isolation is cleaner. |

---

## Post-Install: What the Customer Has

When the installer finishes, the customer has:

- **8 services** running automatically (survive reboot)
- **Grafana** at `http://<ip>:3000` with 6 pre-loaded dashboards
- **Dashboard** at `http://<ip>:8585` with fleet overview + AI Intelligence Center
- **Intelligence Report** at `http://<ip>:8590` with full catalog search
- **Slack** posting fleet alerts to their channels
- **Local AI** analyzing every scan (if Ollama configured)
- **guardian.db** collecting data from minute one
- **Dry run mode** active — no automated actions until operator enables
- **72-hour learning window** — system learns normal hashrate baselines before alerting

The system is fully autonomous from this point. The operator's only job is to watch Slack and approve/deny when prompted.

---

*This document is the build bible. Every question about the installer starts here.*
*Branch: `installer-build`*
*Next action: Start building Screen 1 + Screen 2*
