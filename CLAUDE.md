# Mining Guardian

AI-powered Bitcoin mining fleet monitor for BiXBiT USA, Fort Worth TX.
Monitors 58 miners across liquid-cooled hydro racks and an immersion tank.
Provides automated remediation, Slack approval workflow, Grafana dashboards,
and a continuously-learning two-tier LLM system.

**The single sentence version:** Mining Guardian is a learning loop. Every scan
feeds the local LLM, every operator decision refines its rules, every week
Claude deeply re-analyzes the fleet, and every month all customer deployments
share knowledge. The LLM getting smarter is the main feature of the product.

---

## Session Kickoff Protocol — READ THIS EVERY TIME

**Every new Claude session for Mining Guardian starts by reading the repo before
taking any action.** This is not optional. This is not a suggestion. This exists
because on April 9 2026 a session skipped this step, spent hours proposing
alternatives to plans that were already documented, and then had to be forcibly
stopped and redirected. Don't be that session.

### Required reading, in order, before ANY action or question

1. **This file** (`CLAUDE.md`) — every rule in this file is binding
2. **`docs/VISION.md`** — the consolidated canonical plan (all the scattered docs synthesized into one)
3. **`README.md`** — current system architecture, fleet, services, cron jobs
4. **`AI_ROADMAP.md`** — what's built, what's next, hard deadlines
5. **Most recent handoff note** — look in `docs/` for `RESUME_HERE_*` or `HANDOFF_*` files, read the latest by date
6. **`REPAIR_LOG.md`** — skim the most recent entries. This is the running record of bugs found and fixes applied in plain English. Reading it prevents rediscovering problems we already solved and gives context on recent code changes.
7. **Git state** — run `git status`, `git log --oneline -20`, `git branch -a`. Note any uncommitted changes, non-main branches, or unmerged work (especially `installer-build` as the Mac mini deadline approaches).

### Then — and only then — come back with a 5-section report

1. **Project vision** (one paragraph, your own words) — confirm you understand where Mining Guardian is going: Mac mini appliance at customer sites, two-tier AI (local Qwen for scans + Claude for weekly training), 8 AI features wired into the scan loop, federated monthly knowledge merge across customers, OpenClaw as the conversational brain routing Block Kit actions via Socket Mode on the Mac mini with no public ingress.
2. **What the last session was doing** — from the most recent resume/handoff note, in 3-5 sentences.
3. **Production health right now** — which services are up, any log errors, knowledge.json freshness and counts, anything notable from the morning briefing.
4. **Current top priority, per the docs** — whatever the existing roadmap says is next. Not your opinion. Not an alternative. What the docs say.
5. **Short list of questions the docs genuinely don't answer.** Zero if the docs are sufficient. Maximum three. If you're tempted to ask a fourth, pick the most reasonable interpretation and note the assumption in your response instead.

Then wait for confirmation before starting real work.

---

## Vision Anchors — The Rules That Can Never Change Mid-Session

These exist because on April 9 2026 a session proposed building a keyword-based
web page as a "pragmatic replacement" for OpenClaw, which would have removed the
LLM from the operator decision flow — the main feature of the product. Bobby
caught it. This section exists so the next session doesn't need to.

**Vision Anchor 1 — The LLM IS the product.** The main feature of Mining Guardian
is the LLM getting smarter over time. Every scan feeds it. Every denial refines
it. Every week Claude deeply re-analyzes the fleet. Every month all customer
deployments share knowledge. Any solution that removes the LLM from the
operator's decision flow is the wrong solution, even if it works technically,
even if it's faster to build, even if it's "more reliable." If you find yourself
designing something that bypasses the LLM, STOP and ask.

**Vision Anchor 2 — OpenClaw is the conversational brain, not a replacement
target.** OpenClaw owns Slack Socket Mode. It routes DMs and @mentions to the
local LLM. On the Mac mini it will also route Block Kit button clicks back to
the local approval API (no public ingress required — Socket Mode is outbound
only). OpenClaw is part of the plan, not an obstacle to work around. If OpenClaw
is broken, the answer is to fix OpenClaw, not to build around it.

**Vision Anchor 3 — The Mac mini is THE product.** The VPS, the Cloudflare
tunnels, the systemd services, the `fieslerfamily.com` domains — all of it is
R&D scaffolding. The real product is a single Mac mini running docker-compose at
a customer site, with no public ingress, only outbound internet. Every decision
is evaluated by: "does this make the May 5-9 migration easier, harder, or
neutral?" The answer should never be "harder."

**Vision Anchor 4 — Scale-first, always.** At 58 miners we can get away with
almost anything. At 5,000 miners we cannot. Every new piece of code, every
training prompt, every Claude API call pattern should be designed as if it will
run on a fleet 100x the current size. `train_cohort.py` is the reference for
this — read its docstring before writing anything new that touches the learning
loop.

**Vision Anchor 5 — Federated learning across customer sites.** Each customer
Mac mini exports `knowledge.json` monthly. Bobby combines all site knowledge
into `master_knowledge.json` using `combine_knowledge.py` (with optional
refinement passes through Claude + local LLM for higher-quality synthesis).
Master gets pushed back to every site. No internet required for the sync — USB
or manual transfer is acceptable. Every customer's fleet makes every other
customer's fleet smarter. This is the long-term moat.

---

## Failure Modes to Avoid — Documented Because They Happened

**Failure mode 1 — "Let me propose an alternative."** On April 9, a session
proposed building a keyword-matching `/ask` page instead of fixing OpenClaw. The
existing plan (wire OpenClaw to `guardian.db` via a query skill) was written
down in `docs/RESUME_HERE_2026_04_08_EVENING.md` with a 4-step build checklist.
The session never read that file. **If you're about to propose an alternative to
something that sounds like an existing plan, STOP and search the docs first.
Then execute the existing plan or report what's blocking it — do not invent a
new one.**

**Failure mode 2 — "Let me ask 60 clarifying questions."** Same session, same
day. The session asked Bobby for project vision, federation loop details, LLM
architecture, customer deployment shape, installer strategy, etc. Every single
answer was already in the docs the session hadn't read. **If you find yourself
drafting a clarifying question, first ask: is this answered in `docs/VISION.md`,
`README.md`, `AI_ROADMAP.md`, or `docs/*`? If yes, re-read and answer it
yourself. If no, it's a real question — add it to your short list.**

**Failure mode 3 — Creating `VISION.md v2` when `VISION.md` already exists.**
If you find yourself about to create a new file with `VISION`, `PLAN`, `ROADMAP`,
`ARCHITECTURE`, `DESIGN`, or similar in the name, STOP. That file almost
certainly already exists. Go find it first. If it exists and is outdated, update
it. If it exists and is correct, use it. Only create a new file if you have
confirmed that none of the existing docs cover the topic.

**Failure mode 4 — Treating tool frustration as a reason to bypass the tool.**
OpenClaw took days to get conversational. The afternoon of April 9 a session hit
a skill-loading blocker, got frustrated, and pivoted to "just build a webpage
instead." The correct answer was to keep digging on the skill-loading problem,
or read the OpenClaw docs, or ask for help. Frustration is not a reason to
abandon architecture.

**Failure mode 5 — Ignoring time budgets.** When Bobby says "30 minutes hard
cap," that is a commitment, not a suggestion. At the cap, stop and pivot to the
fallback. Do not "just keep going for 5 more minutes." This happened on April 8
(WSL2/Docker debug, budgeted 30 min, ate 2 hours) and again on April 9 (OpenClaw
skill loading, no budget was set but should have been). Set a budget before
starting debug work; respect it when you hit it.

**Failure mode 6 — `cp config_template.json config.json`** on the VPS. This has
happened twice. Every time it destroys the live AMS credentials and Slack
tokens. Never run this command. Never suggest this command. If you're about to
modify `config.json`, back it up first: `cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)`.

---

## Document Map — Where the Canonical Plan Lives

When a topic comes up, these are the authoritative sources. Read the existing
doc before proposing anything.

| Topic | Authoritative source |
|---|---|
| Overall system architecture, fleet, services | `README.md` |
| AI feature status, roadmap, hard deadlines | `AI_ROADMAP.md` |
| **Consolidated single-source-of-truth vision** | **`docs/VISION.md`** |
| **Running record of bugs, misunderstandings, and fixes (layman terms)** | **`REPAIR_LOG.md`** |
| Full capabilities list (what the product does today + future) | `docs/CAPABILITIES.md` |
| OpenClaw integration design (5-phase plan) | `docs/OPENCLAW_INTEGRATION.md` |
| Cloudflare removal before Mac mini arrival | `docs/CLOUDFLARE_MIGRATION.md` |
| Daily log capture + 14-day rolling baseline (firmware regression detection) | `docs/DAILY_LOG_CAPTURE_VISION.md` |
| Open log uploader (any-vendor, any-format ingestion) | `docs/OPEN_LOG_UPLOADER_VISION.md` |
| Mining Intelligence Catalog (PostgreSQL research DB) | `intelligence/README.md` |
| Mac mini deployment spec + installer wizard | `installer/DEPLOYMENT.md` (on `installer-build` branch) |
| How to feed logs to Claude for analysis | `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md` |
| Container/warehouse mechanical monitoring (future) | `docs/CONTAINER_MONITORING.md` + `docs/WAREHOUSE_MECHANICAL.md` |
| Grafana + Prometheus plan | `docs/GRAFANA_PROMETHEUS_PLAN.md` |
| Per-model profile maps and rated TH/s | `miner_specs.json` + `docs/PROFILE_MAP_QUESTIONS.md` (completed) |
| AMS API endpoints and auth flow | `docs/AMS_API.md` |
| Auradine AH3880 direct API reference | `docs/AURADINE_API.md` |
| BiXBiT firmware direct API (port 4029) | `docs/BIXBIT_DIRECT_API.md` |
| WhatsMiner Extended Partner API | `docs/WHATSMINER_API.md` |

If a topic is not in this list AND not in any of these files, then and only then
is it a candidate for a new doc. Update this table when you add one.

---

## Stack Context

- **Language:** Python 3.12
- **Primary daemon:** `core/mining_guardian.py` — scans every 5 min, runs all 8 AI features in `loop()` after each scan
- **Dashboard API:** `api/dashboard_api.py` — FastAPI on port 8585, serves Prometheus metrics, Retool endpoints, Grafana iframes, and the `/query/*` endpoints that OpenClaw's guardian-db skill will consume
- **Approval API:** `api/approval_api.py` — FastAPI on port 8686, localhost-bound, handles APPROVE/DENY/approve_selected + Slack interactive block_actions (the latter will be re-routed through OpenClaw Socket Mode when Cloudflare comes off)
- **Database:** SQLite at `guardian.db` — 16 tables. Never delete, never truncate, never overwrite.
- **Monitoring:** Prometheus + Grafana, 6 dashboards. During R&D phase served via `grafana.fieslerfamily.com`; becomes `http://mac-mini-ip:3000` at customer sites.
- **Two-tier AI:**
  - Local: Qwen 2.5 32B Q4 on ROBS-PC RTX 4090, reachable via Tailscale at `http://100.110.87.1:11434`. Runs on every scan (~4.6s per analysis). Must stay on.
  - Cloud: Claude Sonnet API for weekly deep training (`train_cohort.py`, Sundays 3am) and ad-hoc deep analysis. Cost ~$1-2/month at current scale. Used only at the proof-of-concept mine — production customer Mac minis use local LLM only.
- **Conversational layer:** OpenClaw Docker container on VPS during R&D, becomes a docker-compose service alongside Mining Guardian on the Mac mini. Owns Slack Socket Mode. Routes DMs to the local LLM. Verified delivering replies to Bobby's Slack user `U07AGTT8CLD` as of April 8 2026.
- **Infrastructure (TEMPORARY):** Hostinger KVM 8 VPS at `187.124.247.182`, Tailscale `100.106.123.83`, 8 systemd services, 3 Cloudflare tunnels. **All of this disappears between May 5–9 2026** when the Mac mini arrives. See the Deployment Target section below.

---

## Critical Safety Rules — Never Violate

- **NEVER `cp config_template.json config.json`** — overwrites AMS credentials and Slack tokens. Has happened twice. Never again.
- **NEVER delete or truncate `guardian.db`** — all historical fleet data, audit log, and training context lives here. If you need to reset something, back it up first and archive the old one.
- **NEVER add Bolt/slack-bolt** — OpenClaw owns Socket Mode. Adding another Socket Mode consumer will break Slack.
- **Pool management and miner settings are explicitly OUT OF SCOPE.** Mining Guardian does not change pools. Mining Guardian does not change miner passwords. These are dangerous and not our job.
- **Dead board issues on S19JPros are suppressed after ticket creation** — do not re-raise them, do not add new flagging logic for them. The ticket flow handles it.
- **Never reproduce credentials in chat or in commits.** `.env` is gitignored. Keep it that way.

---

## Working Principles (locked April 9 2026)

**The 2-vs-10 rule.** When facing a choice between a quick fix and a proper fix,
the question is not "which is faster" — it is "which leaves us better off for
the rest of the project." The rule: if we can fix it in 2 minutes and it will be
OK, OR in 10 minutes and it will be right and better for the future, pick right.
No more going back and re-doing things. We have ~3 weeks to finish the core
product — every re-do costs more than a deliberate up-front fix.

**Work slowly and verify.** Before editing a file, read it. Before running a
command that changes state, say what it does and why. Before assuming a library,
API, or tool works a certain way, check. Small verification steps are cheap;
cleanup after a wrong assumption is expensive. **And before proposing
alternatives to an existing plan, read the existing plan.**

**Scope discipline during edits.** When editing a file for purpose A, do NOT
also fix unrelated issue B in the same edit — even if B is obvious and easy.
Note B separately and handle it as its own task. Mixing scopes is how we lose
the ability to cleanly revert a change.

**Stop-and-check before irreversible actions.** Commits are reversible. Pushes
are reversible-with-effort. Production config edits are reversible-if-backed-up.
Config files overwritten via `cp` are sometimes not recoverable. When in the
last category, back up first, always.

**Time budgets are hard caps.** When a debug path has a stated budget (e.g.,
"30 min max on WSL2"), that budget is a commitment, not a suggestion. At the
cap, stop and pivot to the fallback — do not keep banging. Bobby can always
override the cap in the moment if he chooses, but the default is to respect it.

**No drive-by fixes on unrelated code.** If you notice a bug in a file you're
not currently editing for another reason, write it down and move on. Do not fix
it in the current commit. Cross-cutting cleanups are their own PRs.

---

## Deployment Target (locked April 9 2026)

**The product is a single Mac mini running a docker-compose stack at a customer
site, with normal internet access.** Between now and May 1 2026 we are building
features on a Hostinger VPS with Cloudflare tunnels and host-level systemd
services because that is the dev environment we have. None of that is the
product. On May 5–9 2026 the Mac mini arrives, we containerize Mining Guardian,
and the whole stack moves to the mini. Between now and then, every new piece of
code, config, or infrastructure decision is evaluated by one question:

> *"Does this make the May 5–9 migration easier, harder, or neutral?"*

The answer should never be "harder." Easier or neutral are both fine.

**Design stance: open and useful by default, tightenable by choice.**

The Mac mini has full internet access. Grafana dashboards, the Mining Guardian
dashboard, and the approval API should all be reachable from anywhere the
customer wants to reach them — operator's phone, laptop, office, wherever. Slack
works normally. Outbound HTTPS works normally. Claude API for weekly training
works normally. Monthly knowledge.json sync works normally. **This is a normal
internet-connected appliance, not a hardened bunker.**

Customers who want their deployment locked down (private network only, VPN-only
access, restricted outbound) get that via configuration — we expose the knobs,
they choose the settings. We do NOT pre-lock anything "for their own good."
Customer choice beats developer gate-keeping every time.

**Containerization design decisions (applies to new code TODAY, even though the
container work happens in May):**

- Do NOT hardcode VPS-specific paths, IPs, or hostnames in new code when the value can be read from config
- Do NOT add new systemd-specific features to services that will become containers (timers, socket activation, journal-specific log parsing)
- Do NOT assume Mining Guardian and OpenClaw are on different hosts — they will be two containers in the same docker-compose stack on the same Mac mini. Design inter-service communication as if they already are, using service name DNS inside a shared network and shared volumes for filesystem access
- DO favor configurable values over hardcoded ones, even if the only current value is a VPS-specific one. Swapping a config value is a May 1 one-line change. Rewriting code is not.
- DO document any temporary/throwaway values with a `# TEMP:` comment naming what the forever-value will be. Example: `# TEMP: VPS-specific, becomes "http://openclaw:18789/hooks" on May 1`. The migration should be mechanical, not archaeological.

**The "no media server" rule — scope discipline, not network discipline.**

The Mac mini runs Mining Guardian, OpenClaw, and what they need to do their
job. That's it. No adding unrelated services "because why not." No hobbyist
sprawl. Every new container or service has to earn its place by solving a real
Mining Guardian problem. This is a focused operational tool, not a home lab.

(This rule is about scope and maintenance burden, NOT about network access.
Grafana is in scope. Grafana is reachable from the internet. Both things are
true.)

**Customer installer context.** The `installer-build` branch already has a
313-line `installer/DEPLOYMENT.md` from April 6 2026 with the full local
appliance architecture, pre-flight checks, configuration wizard spec, launchd
service list, directory structure, hardware recommendations, and timeline.
**Do not write a new installer spec.** Update the existing one.

---

## Architecture Rules

- **AMS first, always.** All miner commands go through the AMS API first
  (`https://api-staging.dev.bixbit.io/api/v1`, workspace 119). Direct device
  APIs (BiXBiT port 4029, CGMiner port 4028, Auradine port 8443) are secondary
  and fallback only. AMS is the audit trail.
- **PDU power readings take priority over miner-reported consumption.** The PDU
  is the authoritative source for power draw. Miner-reported consumption is a
  fallback when no PDU is attached.
- **S19JPros have NO PDU outlet in AMS.** Offline remediation for S19JPros:
  restart → if still offline, ticket as bad PSU. No PDU cycle step.
- **Offline remediation decision tree** (implemented in `_analyze_miner`):
  1. First time offline → firmware restart
  2. Has PDU + restart already tried → PDU power cycle
  3. No PDU (S19JPros) OR PDU cycle already tried → PHYSICAL_CYCLE (ticket + human)
- **Problem descriptions stated once at top**, miners listed underneath — never
  repeat per miner. Slack messages are dense.
- **Never truncate IP lists** with "+N more" — show all miners.
- **Slack reporting throttled to 1 per hour maximum.** LLM analysis rides
  alongside the Slack post (once per hour).
- **Dead board lifecycle:** detect → restart → if still dead, auto-create AMS
  ticket → one-time Slack notice → permanent suppression in `known_dead_boards`
  table. Ticketed miners are NEVER re-raised.
- **2-restart escalation:** if a miner has 2+ failed restarts in 7 days OR 2+
  FAILURE outcomes from the outcome checker, action auto-escalates from RESTART
  to RESTART_CHECK_BOARDS → dead board flow → ticket.
- **AMS SYNC false alarm suppression:** if AMS reports offline but direct TCP
  verify shows the miner is reachable, flag as AMS SYNC for up to 10 consecutive
  scans. After 10, suppress entirely — it's a persistent AMS sync lag, not a
  miner problem.

---

## Domain Conventions

**Fleet:** 58 miners, all liquid-cooled.
- ~36 Antminer S19J Pro on BiXBiT firmware
- 5 Antminer S19J Pro on stock firmware
- 4 Antminer S19j Pro (alternate AMS model code)
- 2 Teraflux AH3880 on Auradine firmware (2-board chassis — NOT 3)
- 2 Antminer S21 EXP Hydro on BiXBiT firmware
- 2 Antminer S21 Immersion on BiXBiT firmware

**Miner status:** `ONLINE` / `OFFLINE` / `AMS_SYNC` (verified online via direct
TCP but AMS says offline).

**Actions:** `RESTART` / `PDU_CYCLE` / `PHYSICAL_CYCLE` / `RESTART_CHECK_BOARDS`
/ `MONITOR` / `TEMP_ACTION_REQUIRED` / `POWER_PROFILE_DOWN` / `POWER_PROFILE_UP`
/ `ECO_MODE_FLEET` / `POOL_FAILOVER` / `PREEMPTIVE_RESTART` / `MONITOR_CLOSE`.

**OPERATOR RULE — Temperature (locked April 7 2026):**
This is a liquid-cooled fleet. Chip temps of 67-73°C are NORMAL and require no
action. **Do NOT flag, warn about, or recommend action for any miner running
below 84°C.** Do NOT describe miners under 84°C as "running hot," "overheating,"
or "thermally stressed." Only chip temps ≥84°C warrant action. **There is NO
yellow tier.** The previous "76°C yellow / 86°C red" rule is wrong and has been
removed from the operator rule set. This applies to all prompts, all LLM
templates, all flagging logic.

**OPERATOR RULE — HVAC delta-T:**
The USA 188 HVAC system is performing correctly. The supply/return water delta-T
is intentionally LOW in cooler months and will rise as outside temps climb.
**Do NOT recommend HVAC investigation based on low delta-T.** Do NOT describe
low delta-T as "minimal headroom" or "thermal stress." Assume the HVAC is fine
unless multiple miners simultaneously exceed 84°C.

**OPERATOR RULE — Dead S19JPro boards:**
Suppressed after ticket creation. Do not re-raise. Do not add new flagging
logic for them. The `known_dead_boards` table handles this permanently.

**OPERATOR RULE — Firmware regression (added April 8 2026):**
When N+ miners of the same model show identical fault patterns within hours of
a firmware update, prefer "firmware regression" diagnosis over individual
hardware failure. The April 8 AH3880 case (two miners showing PSU trips,
voltage clipping, stratum panics within hours of the same firmware update)
corrected two HIGH-confidence LLM verdicts of "Replace PSU" to the correct
"Roll back firmware" verdict via this rule.

**OPERATOR RULE — 20-minute post-restart grace period:**
After any restart (manual OR overnight auto), suppress the miner from action
recommendations for 20 minutes. Wait for minerStatus = 0 (mining) before
evaluating hashrate or recommending next steps.

**Hashrate thresholds:** Flag if below 80% of rated TH/s. Rated TH/s is resolved
via the three-tier system (BiXBiT profile parse → `miner_specs.json` lookup →
3-day running baseline for unknowns).

---

## Repo Conventions

- **Repo name has intentional space and typo:** `"Mining Gaurdian"` — always
  quote in terminal. The GitHub remote is `robertfiesler-spec/Mining-Gaurdian`.
- **Python files use venv** — always `source venv/bin/activate` before running
- **Commit messages:** brief description of what changed and why. Conventional
  prefixes welcome but not required (`feat:`, `fix:`, `docs:`, etc).
- **Always test imports before pushing:** `python3 -m py_compile <file>`
- **Repo path requires quotes in all commands** due to space and typo:
  `"/Users/BigBobby/Documents/GitHub/Mining Gaurdian"`

---

## Known Infrastructure (current R&D phase)

- **VPS:** `root@187.124.247.182`, Tailscale `100.106.123.83`, Hostinger KVM 8
  (32 GB RAM, 8 vCPU)
- **ROBS-PC (Windows, facility R&D center):** `192.168.188.47`, Tailscale
  `100.110.87.1`, RTX 4090 running Ollama + Qwen 2.5 32B Q4 at port 11434.
  Must stay on. Must never sleep. Also advertises subnet `192.168.188.0/24`
  via Tailscale as the facility subnet gateway (replaced Mac Mini in this role).
- **AMS API:** `https://api-staging.dev.bixbit.io/api/v1`, workspace 119.
  Cookie-based JWT auth (NOT bearer tokens). See `docs/AMS_API.md`.
- **Slack workspace:** Bixbitusa (`T07AYF6A7DX`)
  - Bobby's user ID: `U07AGTT8CLD`
  - Mining Guardian bot user ID: `U0APQ4VDKGC`
  - Channels: `#mining-guardian` `C0AQ8SE1448` · `#mining-guardian-alerts`
    `C0ARJP300J0` · `#mg-scans` `C0ARLJUJ3BQ` · `#mg-ai-reports` `C0ARSB1U604`
    · `#mg-approvals` `C0AR79YRZ9V` · `#mg-logs` `C0ASH2CPHBJ`
  - Bobby's DM channel: `D0APH4RFCDT`
  - Slack App ID: `A0APJEN0GGN`
- **Cloudflare tunnels (TEMPORARY, off by May 5–9):**
  - `dashboard.fieslerfamily.com` → VPS:8585
  - `slack.fieslerfamily.com` → VPS:8686
  - `grafana.fieslerfamily.com` → VPS:3000
- **PDUs:** orient_RPDU 163 @ `192.168.188.15`, 164 @ `192.168.188.16`
- **HVAC (facility-specific, NOT in deployment templates):** Distech Eclypse BAS
  at `192.168.188.235`, credentials in `.env`
- **Cron jobs on VPS:**
  - `0 3 * * 0` — `weekly_train.py` (Sun 3am, Claude cohort training)
  - `0 4 * * *` — `backup_knowledge.py` (daily 4am, pushes `knowledge_backup.json` to GitHub)
  - `0 7 * * *` — `morning_briefing.py` (daily 7am, Slack briefing)
  - `*/360 * * *` — log collection (every 6 hours)

---

## What Good Looks Like

- Clean, readable Python — no unnecessary complexity
- Every new DB table has an index on `(miner_id, scanned_at)` or equivalent
- Every new Prometheus metric has correct labels: `miner_ip, model, site, map_location`
- LLM prompts are concise — operators are busy, 10-15 lines max response
- Dashboard API endpoints return JSON only — no HTML except the `status_html` route and the Grafana iframe wrappers
- All services restart cleanly via `systemctl` — no manual intervention needed
- All new code is written with the Mac mini migration in mind — no new
  VPS-only assumptions
- `# TEMP:` comments on every value that will change at migration, naming the
  forever-value

---

## AI Toolkit

Installed: v0.5.0-alpha

### Workflow

```
/kickoff → /create-plan → /iterate → commit → /pre-pr-check → push
```

Use `/learn` immediately after correcting any mistake to make it permanent.

### Available Commands

See `.claude/WORKFLOW.md` for full command reference.

Key commands for this project:
- `/kickoff` — start session, read project context
- `/create-plan` — break feature into checklist
- `/iterate` — execute plan items in batches
- `/verify` — run linting/type checks
- `/learn` — turn a correction into a permanent rule in CLAUDE.md
- `/checkpoint` — save session state before clearing context
- `/catchup` — restore from checkpoint after `/clear`

---

*Last major update: April 9 2026 — added Session Kickoff Protocol, Vision
Anchors, Failure Modes, Document Map; fixed miner count 49→58; corrected
temp operator rule (84°C only, no yellow tier); added firmware regression
and 20-min grace period operator rules; added repo convention notes.*
