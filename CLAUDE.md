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

**Every new session for Mining Guardian starts by reading the repo before
taking any action.** This is not optional. This is not a suggestion. This exists
because on April 9 2026 a session skipped this step, spent hours proposing
alternatives to plans that were already documented, and then had to be forcibly
stopped and redirected. Don't be that session.

### Required reading, in order, before ANY action or question

1. **This file** (`CLAUDE.md`) — every rule in this file is binding
2. **`docs/VISION.md`** — the consolidated canonical plan (all the scattered docs synthesized into one)
3. **`docs/DECISIONS.md`** — the canonical log of locked decisions. Every entry is binding unless explicitly superseded by a later entry. Currently 13 entries (D-1 through D-13). Read it before proposing anything that touches Postgres passwords, Ollama models, install dates, or the cutover gate.
4. **`README.md`** — current system architecture, fleet, services, cron jobs
5. **`AI_ROADMAP.md`** — what's built, what's next, hard deadlines
6. **`docs/ROADMAP_TO_MAC_MINI_2026-05-05.md`** — day-by-day cutover plan and the 8-criterion exit gate (D-11)
7. **Most recent SESSION_LOG** — `docs/SESSION_LOG_YYYY-MM-DD.md` for the most recent working day. These are the daily paper trail (D-12). Read the latest by date. They often have addenda.
8. **`REPAIR_LOG.md`** — skim the most recent entries. Running record of bugs found and fixes applied in plain English. Reading it prevents rediscovering problems we already solved.
9. **`docs/LATENT_BUGS.md`** — known bugs that aren't blocking but should not be re-discovered. Skim before any code change.
10. **Git state** — run `git status`, `git log --oneline -20`, `git branch -a`. Note any uncommitted changes, non-main branches, or unmerged work.
11. **Open PRs** — `gh pr list` to see what's in flight.

### Then — and only then — come back with a 5-section report

1. **Project vision** (one paragraph, your own words) — confirm you understand where Mining Guardian is going: Mac Mini appliance at customer sites, two-tier AI (local Ollama for scans + Claude for weekly training), 8 AI features wired into the scan loop, federated monthly knowledge merge across customers, OpenClaw as the conversational brain routing Block Kit actions via Socket Mode on the Mac Mini with no public ingress.
2. **What the last session was doing** — from the most recent SESSION_LOG and any addendum, in 3-5 sentences.
3. **Production health right now** — which services are up, any log errors, knowledge.json freshness and counts, anything notable from the morning briefing.
4. **Current top priority, per the docs** — whatever the existing roadmap says is next. Not your opinion. Not an alternative. What the docs say.
5. **Short list of questions the docs genuinely don't answer.** Zero if the docs are sufficient. Maximum three. If you're tempted to ask a fourth, pick the most reasonable interpretation and note the assumption in your response instead.

Then wait for confirmation before starting real work.

### The Standing Rule on Stale Memory (added 2026-04-28)

**At the start of every Mining Guardian session, read the current GitHub repo state BEFORE proposing plans, paths, or commands.** The agent has been caught multiple times working from stale memory of file paths, branch names, schema, or command syntax that have since changed. The repo is the ground truth, not the agent's recollection of how things were last week.

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
local LLM. On the Mac Mini it will also route Block Kit button clicks back to
the local approval API (no public ingress required — Socket Mode is outbound
only). OpenClaw is part of the plan, not an obstacle to work around. If OpenClaw
is broken, the answer is to fix OpenClaw, not to build around it.

**Vision Anchor 3 — The Mac Mini is THE product.** The VPS, the Cloudflare
tunnels, the systemd services, the `fieslerfamily.com` domains, the ROBS-PC
GPU host — all of it is R&D scaffolding. The real product is a single Mac Mini
running docker-compose at a customer site, with no public ingress, only outbound
internet. Every decision is evaluated by: "does this make the cutover easier,
harder, or neutral?" The answer should never be "harder." See cutover scope
below (Option γ) — the Mini replaces BOTH the VPS AND ROBS-PC's catalog/LLM
roles. Full local-first.

**Vision Anchor 4 — Scale-first, always.** At 58 miners we can get away with
almost anything. At 5,000 miners we cannot. Every new piece of code, every
training prompt, every Claude API call pattern should be designed as if it will
run on a fleet 100x the current size. `train_cohort.py` is the reference for
this — read its docstring before writing anything new that touches the learning
loop.

**Vision Anchor 5 — Federated learning across customer sites.** Each customer
Mac Mini exports `knowledge.json` monthly. Bobby combines all site knowledge
into `master_knowledge.json` using `combine_knowledge.py` (with optional
refinement passes through Claude + local LLM for higher-quality synthesis).
Master gets pushed back to every site. No internet required for the sync — USB
or manual transfer is acceptable. Every customer's fleet makes every other
customer's fleet smarter. This is the long-term moat.

**Vision Anchor 6 — Bitcoin SHA-256 miners ONLY.** Mining Guardian's catalog,
fleet, and AI training are scoped to Bitcoin SHA-256 mining hardware. Do not
add support for altcoin miners, GPU mining rigs, or non-SHA-256 ASICs. If a
session is tempted to broaden scope, stop. The product narrows to Bitcoin
SHA-256 by deliberate choice — the operational rules, AMS endpoints, firmware
quirks, and pool conventions are all SHA-256-specific.

**Vision Anchor 7 — Local-only, no cloud-only dependencies.** The Mac Mini
deployment must function without any cloud-only service. Tailscale and Slack
are the only outbound dependencies for normal operation; Claude API is used
only for weekly training (Sunday 3 AM) and is non-blocking for the operational
loop. Do not introduce a cloud service that the operational loop depends on
synchronously. Local-first beats convenient cloud integration every time.

---

## Cutover Scope — Option γ (locked 2026-04-28)

**On Mac Mini install, the Mini replaces BOTH the Hostinger VPS AND the
ROBS-PC catalog/LLM role.** Full local-first. After cutover:

- **Hostinger VPS** — decommissioned. All 8 systemd services migrate to the
  Mini docker-compose stack. Cloudflare tunnels removed. The VPS host is
  retired or repurposed; it is not part of MG anymore.
- **ROBS-PC** — decommissioned for MG. The RTX 4090 / Qwen 32B / Tailscale
  subnet-router role goes away. The Mac Mini hosts Ollama locally with a
  RAM-detected model (D-13). The Postgres catalog moves from any ROBS-PC
  involvement to the Mini's `mining-guardian-db` container exclusively.
  ROBS-PC may continue to exist as Bobby's facility workstation, but it is
  not in the MG data plane.
- **Anthropic Claude API** — still used by `weekly_train.py` (Sunday 3 AM
  cohort training) and ad-hoc deep analysis. Customer Mac Minis use local
  LLM only. The proof-of-concept mine (Bobby's site) keeps Claude weekly.

**The 8-criterion cutover gate (D-11) governs when the Mini is allowed to
go live.** See `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` for the live status
of each criterion. As of 2026-04-28: 7 green, 2 pending (Installer rewrite
and Customer docs).

**Pacing rule (added 2026-04-28):** Operator quote — "I am not going to go
slow to hit a May 5 install date lets roll." May 5 is no longer a pacing
constraint. We ship when ready. Quality and the cutover gate determine the
date, not a calendar.

---

## Failure Modes to Avoid — Documented Because They Happened

**Failure mode 1 — "Let me propose an alternative."** On April 9, a session
proposed building a keyword-matching `/ask` page instead of fixing OpenClaw. The
existing plan (wire OpenClaw to the catalog via a query skill) was written
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
`docs/DECISIONS.md`, `README.md`, `AI_ROADMAP.md`, or `docs/*`? If yes, re-read
and answer it yourself. If no, it's a real question — add it to your short
list.**

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

**Failure mode 7 — Working from stale mental model of paths or names.** This
has happened multiple times: agent referenced the old typo'd repo name
(`Mining-Gaurdian`) after the rename, referenced SQLite `guardian.db` after
the Postgres migration, referenced `installer-build` branch after it was
archived. **Always verify path, branch, schema, and command syntax against
the current repo before running anything destructive or proposing a plan.**

**Failure mode 8 — Pasting heredocs with em-dashes or `#` comments into the
Mac terminal.** This hangs the shell at a continuation prompt waiting for a
quote it'll never see. If you need to paste a multi-line block on the Mac
terminal, write the file on the agent side, have the operator `curl` it down,
or use single-line commands with no inline comments. If the shell hangs,
Ctrl+C, and switch to a heredoc-free approach. Captured 2026-04-28.

---

## Document Map — Where the Canonical Plan Lives (over-documented on purpose)

When a topic comes up, these are the authoritative sources. Read the existing
doc before proposing anything. Add a row to this table any time a new
canonical doc is created — never let this table go stale again.

### Tier 1 — Must-read on every kickoff

| Topic | Authoritative source |
|---|---|
| **This file** (rules, kickoff protocol, vision anchors, failure modes) | `CLAUDE.md` |
| **Consolidated single-source-of-truth vision** | `docs/VISION.md` |
| **Locked decisions log (D-1 through D-13)** | `docs/DECISIONS.md` |
| **Day-by-day cutover plan + 8-criterion exit gate** | `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` |
| **Today's session paper trail** | `docs/SESSION_LOG_YYYY-MM-DD.md` (most recent by date) |
| **Running record of bugs and fixes (layman terms)** | `REPAIR_LOG.md` |
| **Known non-blocking bugs** | `docs/LATENT_BUGS.md` |
| **AI feature status, roadmap, hard deadlines** | `AI_ROADMAP.md` |
| **Overall system architecture, fleet, services** | `README.md` |

### Tier 2 — Architecture and design

| Topic | Authoritative source |
|---|---|
| Full capabilities list (today + future) | `docs/CAPABILITIES.md` |
| OpenClaw integration design (5-phase plan) | `docs/OPENCLAW_INTEGRATION.md` |
| Cloudflare removal before Mac Mini arrival | `docs/CLOUDFLARE_MIGRATION.md` |
| Daily log capture + 14-day rolling baseline | `docs/DAILY_LOG_CAPTURE_VISION.md` |
| Open log uploader (any-vendor, any-format) | `docs/OPEN_LOG_UPLOADER_VISION.md` |
| Daily Qwen deep-dive design | `docs/DAILY_DEEP_DIVE_DESIGN.md` |
| Refined insights design | `docs/REFINED_INSIGHTS_DESIGN.md` |
| Container/warehouse mechanical monitoring (future) | `docs/CONTAINER_MONITORING.md`, `docs/WAREHOUSE_MECHANICAL.md` |
| Container sensor reference | `docs/CONTAINER_SENSOR_REFERENCE.md` |
| Grafana + Prometheus plan | `docs/GRAFANA_PROMETHEUS_PLAN.md` |
| HVAC architecture + dual-system routing | `docs/HVAC_ARCHITECTURE.md`, `docs/HVAC_SYSTEMS.md` |
| Log collection architecture | `docs/LOG_COLLECTION_ARCHITECTURE.md` |
| Direct log collection from miners | `docs/DIRECT_LOG_COLLECTION.md` |
| Confidence scoring system | `docs/CONFIDENCE_SCORING.md` |
| Fingerprints vs profiles | `docs/FINGERPRINTS_VS_PROFILES.md` |
| Feedback loop fixes | `docs/FEEDBACK_LOOP_FIXES.md` |
| Per-model profile maps and rated TH/s | `miner_specs.json` + `docs/PROFILE_MAP_QUESTIONS.md` |

### Tier 3 — Mac Mini installer and deployment

| Topic | Authoritative source |
|---|---|
| Mac Mini deployment runbook | `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` |
| Mac Mini installer spec (active branch) | `mg/pr26-mac-mini-installer` (cut from main 2026-04-28) |
| Deployment checklist | `DEPLOYMENT_CHECKLIST.md` |
| Customer-facing setup manual | (pending — gate criterion 8) |
| Customer-facing program instructions | (pending — gate criterion 8) |
| Customer-facing brochure | (pending — gate criterion 8) |

### Tier 4 — Postgres catalog and migration

| Topic | Authoritative source |
|---|---|
| Mining Intelligence Catalog (Postgres research DB) | `intelligence-catalog/seed-data/README.md` (legacy `intelligence/` deprecated — see `intelligence/DEPRECATED.md`) |
| Intelligence catalog status | `docs/INTELLIGENCE_CATALOG_STATUS.md` |
| Intelligence report API | `docs/INTELLIGENCE_REPORT_API.md` |
| Postgres migration plan | `docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md` |
| Postgres migration status (latest) | `docs/POSTGRES_MIGRATION_STATUS_2026-04-24.md` |
| Postgres staging state | `docs/POSTGRES_STAGING_STATE_2026-04-23.md` |
| Core database audit | `docs/CORE_DATABASE_AUDIT_2026-04-23.md` |
| Outside init_db audit | `docs/OUTSIDE_INIT_DB_AUDIT_2026-04-23.md` |
| Catalog orphan tables | `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` |
| Empty stub tables | `docs/EMPTY_STUB_TABLES.md` |
| DB state snapshots | `docs/DB_STATE_2026-04-22.md`, `docs/DB_STATE_2026-04-23.md` |
| Bulk import tooling | `mg_import_tool/` (PR #25) |

### Tier 5 — APIs

| Topic | Authoritative source |
|---|---|
| API reference (combined) | `docs/API_REFERENCE.md` |
| AMS API endpoints and auth flow | `docs/AMS_API.md`, `docs/AMS_INTEGRATION.md` |
| Auradine AH3880 direct API | `docs/AURADINE_API.md` |
| Auradine rollback status | `docs/AURADINE_ROLLBACK_STATUS.md` |
| BiXBiT firmware direct API (port 4029) | `docs/BIXBIT_DIRECT_API.md` |
| WhatsMiner Extended Partner API | `docs/WHATSMINER_API.md` |
| How to feed logs to Claude | `docs/HOW_TO_UPLOAD_LOGS_TO_CLAUDE.md` |

### Tier 6 — Operations and rules

| Topic | Authoritative source |
|---|---|
| Operator guide | `docs/OPERATOR_GUIDE.md` |
| Operator rules (canonical, all locked rules) | `docs/OPERATOR_RULES.md` |
| Cron schedule | `docs/CRON_SCHEDULE.md` |
| Cron reconciliation | `docs/CRON_RECONCILIATION.md` |
| Security | `docs/SECURITY.md` |
| CORS lockdown plan | `docs/CORS_LOCKDOWN_PLAN.md` |
| Slack branding checklist | `docs/SLACK_BRANDING_CHECKLIST.md` |
| Testing | `docs/TESTING.md` |
| Troubleshooting | `docs/TROUBLESHOOTING.md` |
| Repair log (chronological fixes) | `REPAIR_LOG.md`, `docs/REPAIR.md` |
| Latent bugs (known, non-blocking) | `docs/LATENT_BUGS.md` |
| Unified TODO list | `docs/MG_UNIFIED_TODO_LIST.md` |
| Morning kickoff prompt | `docs/MORNING_KICKOFF_PROMPT.md` |

### Tier 7 — Audits and historical

Audit reports and resume notes are kept for historical context. Read them
when investigating something they cover; don't treat them as live plans.

| Topic | Authoritative source |
|---|---|
| AI data audit (2026-04-10) | `docs/AI_DATA_AUDIT_2026-04-10.md` |
| Complete AI audit | `docs/COMPLETE_AI_AUDIT_2026-04-10.md`, `docs/COMPLETE_AI_AUDIT_V2_2026-04-10.md` |
| Audit summary | `AUDIT_SUMMARY_2026-04-13.md` |
| Session handoff (2026-04-24) | `docs/SESSION_HANDOFF_2026-04-24.md` |
| Resume-here notes (Apr 8) | `docs/RESUME_HERE_2026_04_08*.md` |
| Demo day handoff | `docs/DEMO_DAY_HANDOFF_2026_04_08.md` |
| Overnight test status | `docs/OVERNIGHT_TEST_STATUS_2026-04-13.md` |
| Unused data opportunities | `docs/UNUSED_DATA_OPPORTUNITIES.md` |
| Perplexity prompt drafts (catalog research) | `docs/PERPLEXITY_PROMPT_MINING_INTELLIGENCE_CATALOG*.md` |
| All `SESSION_LOG_*.md` and `RUNBOOK_*.md` | `docs/` (chronological) |

If a topic is not in this table AND not in any of these files, then and only
then is it a candidate for a new doc. Update this table when you add one.

---

## Stack Context — Phase-Gated

Mining Guardian is in transition. The R&D phase runs on a Hostinger VPS plus
ROBS-PC. The Production phase runs on a single Mac Mini at the customer site
(Option γ). Both states are documented here so any session can read this file
and know exactly which world they are in.

### Common to both phases

- **Language:** Python 3.12+ on the VPS / customer Mac. Python 3.14.3 on
  Bobby's Mac (development workstation).
- **Primary daemon:** `core/mining_guardian.py` — scans every hour, runs all
  8 AI features in `loop()` after each scan.
- **Dashboard API:** `api/dashboard_api.py` — FastAPI on port 8585. Serves
  Prometheus metrics, Retool endpoints, Grafana iframes, and `/query/*`
  endpoints that OpenClaw's guardian-db skill consumes.
- **Approval API:** `api/approval_api.py` — FastAPI on port 8686, localhost-
  bound. Handles APPROVE/DENY/approve_selected and Slack interactive
  block_actions.
- **Database engine:** PostgreSQL 16 (`postgres:16-bookworm` image). Postgres
  is the canonical store. SQLite is no longer in the data plane — see Database
  Migration History below.
- **Database name:** `mining_guardian` (operational catalog). Operational
  password is `MG_DB_PASSWORD` from `.env`, never committed.
- **Container name:** `mining-guardian-db` (the Postgres container that hosts
  the operational database, regardless of which host runs it).
- **Monitoring:** Prometheus + Grafana, 6 dashboards.
- **Two-tier AI:**
  - **Local LLM** — runs on every scan (~4.6s per analysis). Must stay on.
    Specific host and model differ by phase (see below).
  - **Claude API** — Sonnet, used for weekly deep training (`train_cohort.py`,
    Sundays at the time set in `docs/CRON_SCHEDULE.md`) and ad-hoc deep
    analysis. Cost ~$1-2/month at current scale. Production customer Mac Minis
    use local LLM only; Bobby's proof-of-concept mine keeps Claude weekly.
- **Conversational layer:** OpenClaw owns Slack Socket Mode. Routes DMs and
  @mentions to the local LLM. On the Mini it also routes Block Kit button
  clicks back to the local approval API.

### Phase A — R&D (now, until cutover)

- **Catalog/Postgres host:** ROBS-PC. Container `mining-guardian-db`
  (Postgres 16-bookworm) runs on Bobby's Windows workstation.
- **Local LLM host:** ROBS-PC. Qwen 2.5 32B Q4 served by Ollama at
  `http://100.110.87.1:11434` (Tailscale). RTX 4090 GPU. Must stay on.
  Must never sleep. Also advertises subnet `192.168.188.0/24` via Tailscale
  as the facility subnet gateway (replaced an earlier Mac Mini in this role).
- **App host:** Hostinger VPS at `187.124.247.182` (Tailscale `100.106.123.83`).
  KVM 8, 32 GB RAM, 8 vCPU. Runs 8 systemd services and 3 Cloudflare tunnels.
- **VPS path:** `/root/Mining-Guardian/` (renamed Sunday 2026-04-26 in PR #1
  from the old typo path `/root/Mining-Gaurdian/`). Do not use the old path
  in any new command.
- **Public dashboards (TEMPORARY):** `dashboard.fieslerfamily.com`,
  `slack.fieslerfamily.com`, `grafana.fieslerfamily.com` via Cloudflare tunnels.

### Phase B — Production (post-cutover, on customer Mac Mini)

- **All-in-one host:** Mac Mini. Single host runs the full stack:
  - Postgres 16 in container `mining-guardian-db`
  - Mining Guardian app (containerized via Colima docker-compose)
  - OpenClaw container alongside
  - Ollama natively (not in container — closer to Apple Silicon Metal)
  - Grafana container
- **Local LLM host:** Mac Mini, localhost. `OLLAMA_URL=http://localhost:11434/api/generate`.
- **Local LLM model:** Selected at install time by RAM detection (D-13,
  supersedes D-8):
  - 16 GB RAM (e.g., base Mac Mini M4) picks `llama3.2:3b` (q4 default)
  - 24 GB RAM or more picks `qwen2.5:14b-instruct-q4_K_M`
  - Customer can override the auto-pick before download.
- **Network:** Mini sits on the miner LAN `192.168.188.0/24`. Tailscale
  installed for remote operator access only — data plane stays local
  (D-9). `CATALOG_DB_HOST=localhost`.
- **Public ingress:** none. Slack Socket Mode is outbound-only. Operator
  reaches the Mini via Tailscale or local LAN.
- **Hostinger VPS:** decommissioned.
- **ROBS-PC:** decommissioned for MG. May continue as Bobby's facility
  workstation but is not in the MG data plane.

---

## Critical Safety Rules — Never Violate

- **NEVER `cp config_template.json config.json`** — overwrites AMS credentials
  and Slack tokens. Has happened twice. Never again.
- **NEVER drop, truncate, or `DELETE FROM` any table in the operational Postgres
  database `mining_guardian`** without an explicit backup-first step. The
  catalog, audit log, training context, and historical fleet data live here.
  This is the operational source of truth. If you need to reset something,
  back it up first (`pg_dump`) and archive the dump under
  `/Volumes/Big-Bobby-T9/Old Storage/BixBit/Mining Guardian Backups/` (or the
  customer-Mini equivalent path post-cutover).
- **NEVER refer to SQLite as live.** SQLite was retired. Any reference to
  `guardian.db` as a current data source is a bug. The leftover
  `grafana_summary.db` and `guardian.sqbpro` files at the repo root are
  historical artifacts pending cleanup; do not write to them, do not read
  from them as if they were authoritative.
- **NEVER add Bolt/slack-bolt** — OpenClaw owns Socket Mode. Adding another
  Socket Mode consumer will break Slack.
- **Pool management and miner settings are explicitly OUT OF SCOPE.** Mining
  Guardian does not change pools. Mining Guardian does not change miner
  passwords. These are dangerous and not our job.
- **Dead board issues on S19JPros are suppressed after ticket creation** —
  do not re-raise them, do not add new flagging logic for them. The ticket
  flow handles it.
- **Never reproduce credentials in chat or in commits.** `.env` is gitignored.
  Keep it that way. The operational `MG_DB_PASSWORD` rotates per D-1; never
  commit any value of it.
- **Bitcoin SHA-256 ASIC miners ONLY.** Do not extend Mining Guardian to
  altcoin miners or GPU rigs.
- **Stay local. No cloud-only dependencies in the operational loop.**

---

## Working Principles (locked April 9 2026)

**The 2-vs-10 rule.** When facing a choice between a quick fix and a proper fix,
the question is not "which is faster" — it is "which leaves us better off for
the rest of the project." The rule: if we can fix it in 2 minutes and it will be
OK, OR in 10 minutes and it will be right and better for the future, pick right.
No more going back and re-doing things. Every re-do costs more than a deliberate
up-front fix.

**Work slowly and verify.** Before editing a file, read it. Before running a
command that changes state, say what it does and why. Before assuming a library,
API, or tool works a certain way, check. Small verification steps are cheap;
cleanup after a wrong assumption is expensive. **And before proposing
alternatives to an existing plan, read the existing plan.**

**Operator quote:** "I would rather be late and perfect than early and wrong."
And: "I have OCD and I hate slop or messes." And: "I believe in over-
documentation." Internalize these. They drive every other rule.

**Scope discipline during edits.** When editing a file for purpose A, do NOT
also fix unrelated issue B in the same edit — even if B is obvious and easy.
Note B separately and handle it as its own task. Mixing scopes is how we lose
the ability to cleanly revert a change.

**Stop-and-check before irreversible actions.** Commits are reversible. Pushes
are reversible-with-effort. Production config edits are reversible-if-backed-up.
Config files overwritten via `cp` are sometimes not recoverable. When in the
last category, back up first, always.

**Time budgets are hard caps.** When a debug path has a stated budget, that
budget is a commitment, not a suggestion. At the cap, stop and pivot to the
fallback — do not keep banging. Bobby can always override the cap in the
moment if he chooses, but the default is to respect it.

**No drive-by fixes on unrelated code.** If you notice a bug in a file you're
not currently editing for another reason, write it down (in
`docs/LATENT_BUGS.md` or as its own todo) and move on. Do not fix it in the
current commit. Cross-cutting cleanups are their own PRs.

**Step-by-step pacing for the operator.** Bobby has stated: "step by step
please i need to focus." Do not bundle 10 commands into one paste-along when
2-3 verifiable steps would do. Long blocks make it harder to spot a problem.
After every state change, verify before continuing.

---

## Repo Conventions

- **Repo name (correct):** `Mining-Guardian` (hyphen, no space, correctly
  spelled). The GitHub remote is `robertfiesler-spec/Mining-Guardian`.
- **Default branch:** `main`. Tagged `📦 v1.0.0`.
- **Active local clone (Mac):** `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`
  — no quotes needed (no spaces, no special characters).
- **VPS clone path:** `/root/Mining-Guardian/`. The old typo path
  `/root/Mining-Gaurdian/` was retired Sunday 2026-04-26 in PR #1. Any
  reference to the typo path in scripts, cron jobs, or systemd unit files
  is a bug to be fixed.
- **Python files use venv** — always `source venv/bin/activate` before running
  on the VPS or the Mini. On macOS dev workstations, `python3` is fine.
- **Commit messages:** brief description of what changed and why. Conventional
  prefixes welcome and recommended (`feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`).
- **Always test imports before pushing:** `python3 -m py_compile <file>`.
- **PR cadence:** every code or doc change goes through a PR. Squash-merge
  to main, delete branch on merge. PR #1 through PR #26 set the cadence;
  match it.
- **Branch naming:** `mg/prNN-<short-name>` for feature/installer work,
  `docs/<short-name>` for doc-only changes, `archive/<branch>-YYYYMMDD`
  for archived branches.

### Repo Rename History

- **2026-04-26 (Sunday)** — `Mining-Gaurdian` → `Mining-Guardian`. Done in PR
  #1 alongside the VPS path migration `/root/Mining-Gaurdian/` →
  `/root/Mining-Guardian/`. The original typo was an intentional joke that
  became a real maintenance problem (every command needed quoting; tab
  completion was awkward; new contributors thought it was a typo). Rename was
  the cleaner long-term fix.
- **2026-04-28 (Tuesday)** — Bobby's local Mac clone re-cloned with the
  correct name. Old folder archived as `Mining Gaurdian.OLD-20260428` and
  scheduled for deletion 48 hours later if nothing is missing.

### Database Migration History

- **Pre-2026-04-23** — SQLite at `guardian.db` was the operational store.
  16 tables. Daily backups via `backup_knowledge.py`.
- **2026-04-23 → 2026-04-24** — Migration to PostgreSQL 16 executed per
  `docs/POSTGRES_MIGRATION_PLAN_2026-04-23.md`. Container `mining-guardian-db`
  (`postgres:16-bookworm`) hosts the operational database `mining_guardian`.
  Migration script at `migrations/migrate_sqlite_to_postgres.py` is gated
  by `MG_ALLOW_MIGRATION=1` (D-6) to prevent accidental re-runs.
- **2026-04-27 (afternoon)** — Bulk import tooling landed (PR #25). Live
  database re-import 127/136 archives. See `mg_import_tool/` and
  `docs/RUNBOOK_2026-04-27_afternoon.md`. Addendum #3 on
  `docs/SESSION_LOG_2026-04-27.md`.
- **Cleanup pending** — `grafana_summary.db` (SQLite at repo root) and
  `guardian.sqbpro` (DB Browser project file at repo root) are leftover
  artifacts. Tracked for removal in a future archive sweep PR.

---

## Cutover Branch and Installer Branch

- **`installer-build` (legacy)** — archived 2026-04-28 as
  `archive/installer-build-20260428`. Was 403 commits behind `main` at
  archive time. Pre-Sunday architecture; not aligned with Postgres,
  Option γ, or D-13. Do not branch from it. Read it only for historical
  context (e.g. the original 313-line `installer/DEPLOYMENT.md` from
  April 6 2026).
- **`mg/pr26-mac-mini-installer` (active)** — cut from clean `main`
  2026-04-28. This is the live installer branch. The Hybrid ~500 MB
  `.pkg` (Q1) is built here. Phase 8 of the installer encodes D-13
  (RAM-detected Ollama model).

---

## May Migration Changes — What Changes and What Stays on Mac Mini Arrival

The Mac Mini is sometimes called **May** in older docs (named April 9 2026,
back when the install was scheduled for May 5–9). The pacing rule (added
2026-04-28) removed the May 5 calendar constraint, but the codename stuck
in some docs and tags. Treat "May" and "Mac Mini" as synonyms in older
content.

### What STAYS on after Mini arrival (the permanent weekly training)

The Sunday Claude weekly training stays on forever (or at least the next
year). It is the strength of the system and is not going anywhere. On
cutover, Claude continues to receive on every Sunday run:

- **Daily logs** — all logs collected from every miner during the week
- **`llm_scan_analyses` stream** — every local-LLM hourly scan analysis
  from the week
- **Cohort analysis results** — the per-cohort Claude responses from the
  cohort pass
- **Outlier analysis results** — individual deep analyses of miners >2σ
  from their cohort
- **Operator rules** — everything extracted from the week's denials
- **Cross-miner correlations** — the SQL-based cross-miner analysis from
  `get_cross_miner_correlations`
- **Full fleet synthesis pass** — the final `build_fleet_prompt` → Claude call
- **`daily_deep_analyses` stream** — the daily Qwen 32B deep-dive fleet
  synthesis + per-miner analyses, merged into the weekly Claude prompt via
  a PERMANENT merge block in `ai/train_cohort.py` (NOT wrapped in
  TEMP_MAY_REMOVE markers). Added April 9 2026. Stays on forever.

The whole cohort → outlier → fleet pipeline stays exactly as it is. Cutover
is NOT about "turning Claude off."

### What GETS REMOVED on Mini arrival

**ONE thing only: the pre/post restart comparison summary merge layer.**

The comparison merge block in `ai/train_cohort.py` (tagged `TEMP_MAY_REMOVE`
in the code, added April 9 2026 as commit `e90c2be`) pulls the dual-model
Qwen+Claude before/after restart verdicts from `knowledge['known_issues']`
and merges them into the `all_local_llm_analyses` stream so Claude sees them
in the Sunday fleet prompt.

On Mini arrival, remove this merge block. Claude will still get everything
else listed above — this ONLY removes the per-restart comparison summaries
from the Sunday prompt.

**Why it comes off:** by Mini arrival, the local LLM will have months of
accumulated scan analyses under its belt. The separate dual-model before/
after comparison summaries will no longer add unique signal on top of what
the local LLM already captures in the regular scan analysis stream. The
merge layer was scaffolding for the current phase where the local LLM was
still learning; once it has enough accumulated context, the comparison
summaries become redundant with the scan analyses.

**How to find the removal target:** `grep -rn 'TEMP_MAY_REMOVE' .` — the
block is bracketed by `# TEMP_MAY_REMOVE:` at the top and
`# END TEMP_MAY_REMOVE` at the bottom in `ai/train_cohort.py`. Delete
everything between and including those markers. No other files need to
change for this removal.

**Everything else tagged `# TEMP:`** in the codebase is unrelated to the
Mini cutover — those are VPS-specific scaffolding (Cloudflare tunnel URLs,
VPS-specific paths, systemd-specific features) that come off for different
reasons and follow different timelines. Do not conflate them with
`TEMP_MAY_REMOVE`.

### What doesn't get touched until post-cutover decisions

- The write side of restart comparisons — `_run_post_action_log_comparison`
  in `core/mining_guardian.py` still writes comparisons to `known_issues`
  after cutover. They just stop being merged into the weekly prompt. This
  preserves operational value (Slack posting still works, in-the-moment
  comparisons still happen, the data is still in the knowledge file if
  anyone wants to inspect it) without adding them to Claude's weekly input.
- The existing `llm_scan_analyses` stream — unchanged before and after.
- The `compare:` miner_id prefix convention — unchanged, still used by the
  writer, still findable via grep.

### Origin of this rule

Captured April 9 2026 during the session that diagnosed and fixed the
silent-skip bug where the weekly trainer was reading `llm_scan_analyses`
while the per-restart comparisons were being written to `known_issues`.
See the corresponding REPAIR_LOG.md entry: "Weekly Claude training was
missing the pre/post restart comparisons" (2026-04-09). The fix is live
on main as commit `e90c2be`.

### The Daily Deep Dive — permanent, not TEMP_MAY_REMOVE

The daily Qwen deep dive (`ai/daily_deep_dive.py`) runs once a day on the
local LLM and writes to `knowledge['daily_deep_analyses']`. The Sunday
Claude weekly training merges those entries into its prompt via a permanent
merge block in `ai/train_cohort.py`. **Unlike the `TEMP_MAY_REMOVE` block
for restart comparisons, this block is NOT wrapped in removal markers and
MUST NOT be removed on Mini arrival.** The daily deep dive is the core
long-term learning mechanism for the local LLM; it is not scaffolding.

On cutover, two things happen to the daily deep dive:

1. The script moves from the VPS path `/root/Mining-Guardian/` to the Mac
   Mini deployment path
2. The `LLM_URL` config value changes from ROBS-PC Tailscale to Mac Mini
   localhost

No code changes. No merge block removal. If a future session proposes
removing the daily deep dive or its Sunday merge block, **stop and re-read
this section, REPAIR_LOG.md entry "Daily Deep Dive LLM created," and
`docs/DAILY_DEEP_DIVE_DESIGN.md`.**

### The 4-Pass Weekly Refinement Chain — error-catching between models

Added April 10 2026. The refinement chain runs after the Sunday weekly
training to catch and correct errors before the output becomes "official"
fleet guidance.

**The four passes:**

1. **Pass 1 (Qwen daily deep dive)** — already exists in
   `knowledge["daily_deep_analyses"][0]`, produced the day before
2. **Pass 2 (Claude weekly training)** — already exists in
   `knowledge["cross_miner_analysis"][0]`, produced by `train_cohort.py`
3. **Pass 3 (Qwen reflection)** — Qwen reads Claude output and identifies
   errors, disagreements, and blind spots. Written to
   `weekly_refinement_chain` immediately (resume-safe).
4. **Pass 4 (Claude merged report)** — Claude reads its original output
   plus Qwen critique, corrects errors, and produces a final merged report.

**Storage (the "both slots" rule):**
Pass 4 writes to TWO locations:

- `knowledge["weekly_refinement_chain"]` — full chain history for
  debugging/auditing
- `knowledge["cross_miner_analysis"][0]` — overwrites the original so
  Sunday merge block picks up the corrected version next week

This means the REFINED report (not the raw Claude output) becomes the
"official" cross-miner analysis that flows into future training runs.

**Resume-safety guarantees (added after a Pass 4 Anthropic 529 crash):**

- Pre-flight checks validate all dependencies before firing any model call
- WIP checkpointing after each pass (survives later crashes)
- `--resume-from {3,4}` flag allows resuming after partial failures
- `--smoke-test` validates plumbing in ~60s before burning 20+ minutes
- `--dry-run` shows plan without firing model calls

**Script location:** `ai/refinement_chain.py`

**When to run:** After weekly training completes. Currently scheduled at
1 AM per `docs/CRON_SCHEDULE.md`.

**First successful run:** April 10 2026. Qwen caught 4 Claude errors (fleet
count 47/49 to 58, inappropriate REPLACE recommendations for S21 EXP Hydro
and AH3880, re-proposed already-locked rules) and identified 2 blind spots
(miners 53482 and 64347 that Claude missed). Claude accepted all corrections
in Pass 4.

---

## Working Practices

### Document as you go, not after

Every session that adds a feature or makes a design decision MUST update the
relevant docs in the SAME commit as the code. No more deferring documentation
to "later." This rule was added at end of day April 9 2026 because the
morning session had been shipping code without documentation updates, which
is the same silent-skip pattern we keep diagnosing in the code itself.

What this means in practice:

- If you write a new module or rewrite a function significantly, commit the
  code change TOGETHER with a `REPAIR_LOG.md` entry (or `SESSION_LOG` entry
  for that day, or updated design doc) explaining what changed and why.
- If you discover a new operator rule, update CLAUDE.md (and/or
  `docs/OPERATOR_RULES.md`) in the same commit as the code that enforces it.
- If you find a degraded miner or a production anomaly, flag it in
  `REPAIR_LOG.md` (or `docs/LATENT_BUGS.md` for non-blocking issues) before
  the session ends.
- If you make a decision that will affect future sessions, capture it in
  `docs/DECISIONS.md` as a new D-N entry before moving on.

Do not split documentation into a separate "I'll do it next session" task.
Next session may not happen, or may not remember the context. The
documentation is part of the work.

### Context compaction awareness

The agent's context gets compacted periodically. When compaction happens,
recent direct conversation may be summarized and the verbatim record may
become inaccessible. This means:

- **If you find evidence in git of work you don't remember doing**, the first
  move is to read the commit content carefully. If the author identity matches
  yours, the reflog shows it came from this machine, and the commit message is
  written in your voice, accept it as your own work rather than alarming the
  operator.
- **Git is the ground truth for what happened**, not your conversation memory.
  When in doubt, `git log`, `git show`, `git reflog`.
- **This was a real incident on April 9 2026**: the agent wrote the parallel
  15-worker rewrite (`e5b9f5c`), a compaction boundary crossed, the agent lost
  direct memory of writing it, then found it in git and incorrectly assumed
  another session must have done it. Bobby had to confirm no other session
  was running. Trust git, read commits carefully, don't pattern-match on
  "I don't remember this so it must not be mine."

---

## Architecture Rules

- **AMS first, always.** All miner commands go through the AMS API first
  (`https://api-staging.dev.bixbit.io/api/v1`, workspace 119). Direct device
  APIs (BiXBiT port 4029, CGMiner port 4028, Auradine port 8443) are secondary
  and fallback only. AMS is the audit trail.
- **PDU power readings take priority over miner-reported consumption.** The
  PDU is the authoritative source for power draw. Miner-reported consumption
  is a fallback when no PDU is attached.
- **S19JPros have NO PDU outlet in AMS.** Offline remediation for S19JPros:
  restart → if still offline, ticket as bad PSU. No PDU cycle step.
- **Offline remediation decision tree** (implemented in `_analyze_miner`):
  1. First time offline → firmware restart
  2. Has PDU + restart already tried → PDU power cycle
  3. No PDU (S19JPros) OR PDU cycle already tried → PHYSICAL_CYCLE (ticket
     + human)
- **Problem descriptions stated once at top**, miners listed underneath —
  never repeat per miner. Slack messages are dense.
- **Never truncate IP lists** with "+N more" — show all miners.
- **Slack reporting throttled to 1 per hour maximum.** LLM analysis rides
  alongside the Slack post (once per hour).
- **Dead board lifecycle:** detect → restart → if still dead, auto-create AMS
  ticket → one-time Slack notice → permanent suppression in
  `known_dead_boards` table. Ticketed miners are NEVER re-raised.
- **2-restart escalation:** if a miner has 2+ failed restarts in 7 days OR
  2+ FAILURE outcomes from the outcome checker, action auto-escalates from
  RESTART to RESTART_CHECK_BOARDS → dead board flow → ticket.
- **AMS SYNC false alarm suppression:** if AMS reports offline but direct TCP
  verify shows the miner is reachable, flag as AMS SYNC for up to 10
  consecutive scans. After 10, suppress entirely — it's a persistent AMS
  sync lag, not a miner problem.

---

## Domain Conventions

**Fleet:** 58 miners, all liquid-cooled.

- ~36 Antminer S19J Pro on BiXBiT firmware (3 boards each: Chain 0, 1, 2 —
  NO Chain 3)
- 5 Antminer S19J Pro on stock firmware (3 boards each)
- 4 Antminer S19j Pro alternate model code (3 boards each)
- 2 Teraflux AH3880 on Auradine firmware (2 boards ONLY — NOT 3)
- 2 Antminer S21 EXP Hydro on BiXBiT firmware (3 boards each)
- 2 Antminer S21 Immersion on BiXBiT firmware (3 boards each)

**Hardware fact:** S19J Pro has exactly 3 boards (Chain 0, 1, 2). There is
NO Chain 3. Any insight or analysis referencing Chain 3 on an S19J Pro is
a bug.

**Miner status:** `ONLINE` / `OFFLINE` / `AMS_SYNC` (verified online via
direct TCP but AMS says offline).

**Actions:** `RESTART` / `PDU_CYCLE` / `PHYSICAL_CYCLE` / `RESTART_CHECK_BOARDS`
/ `MONITOR` / `TEMP_ACTION_REQUIRED` / `POWER_PROFILE_DOWN` / `POWER_PROFILE_UP`
/ `ECO_MODE_FLEET` / `POOL_FAILOVER` / `PREEMPTIVE_RESTART` / `MONITOR_CLOSE`.

### Operator Rules (canonical summary — full set in `docs/OPERATOR_RULES.md`)

**OPERATOR RULE — Temperature (locked April 7 2026):**
This is a liquid-cooled fleet. Chip temps of 67-73°C are NORMAL and require
no action. **Do NOT flag, warn about, or recommend action for any miner
running below 84°C.** Do NOT describe miners under 84°C as "running hot,"
"overheating," or "thermally stressed." Only chip temps ≥84°C warrant action.
**There is NO yellow tier.** The previous "76°C yellow / 86°C red" rule is
wrong and has been removed from the operator rule set. Applies to all
prompts, all LLM templates, all flagging logic.

**OPERATOR RULE — HVAC delta-T:**
Both HVAC systems are performing correctly. The supply/return water delta-T
is intentionally LOW in cooler months and will rise as outside temps climb.
**Do NOT recommend HVAC investigation based on low delta-T.** Do NOT describe
low delta-T as "minimal headroom" or "thermal stress." Assume both HVAC
systems are fine unless multiple miners simultaneously exceed 84°C.

**OPERATOR RULE — Dual HVAC Systems (added April 13 2026):**
Two separate cooling systems exist:

- **Warehouse HVAC (192.168.188.235):** Serves Hydros, S21 Immersion, AH3880
- **S19J Pro Container (192.168.189.235):** Serves S19J Pros ONLY

Simple routing rule: if model starts with "S19JPro" → use s19jpro HVAC,
otherwise → use warehouse HVAC. Mac polls both systems every hour. All AI
analysis must use the CORRECT HVAC system per miner type.

**OPERATOR RULE — S19J Pro CT Fans (added April 13 2026):**
S19J Pro container CT fans are manually set to 100%. No VFD feedback will
appear in HVAC data. This is intentional, NOT a fault. Do NOT flag missing
CT fan feedback as a problem.

**OPERATOR RULE — S19J Pro Overheating (added April 13 2026):**
When an S19J Pro shows overheating (chip temp >= 84°C):

1. Try ONE restart with log capture before/after
2. If restart does not fix it, mark as aging hardware and let it run

Do NOT repeatedly restart overheating S19J Pros. The
`s19jpro_overheat_tracking` table tracks which miners have already had
their restart attempt.

**OPERATOR RULE — Dead S19JPro boards:**
Suppressed after ticket creation. Do not re-raise. Do not add new flagging
logic for them. The `known_dead_boards` table handles this permanently.

**OPERATOR RULE — Firmware regression (added April 8 2026):**
When N+ miners of the same model show identical fault patterns within hours
of a firmware update, prefer "firmware regression" diagnosis over individual
hardware failure. The April 8 AH3880 case (two miners showing PSU trips,
voltage clipping, stratum panics within hours of the same firmware update)
corrected two HIGH-confidence LLM verdicts of "Replace PSU" to the correct
"Roll back firmware" verdict via this rule.

**OPERATOR RULE — 20-minute post-restart grace period:**
After any restart (manual OR overnight auto), suppress the miner from action
recommendations for 20 minutes. Wait for `minerStatus = 0` (mining) before
evaluating hashrate or recommending next steps.

**Hashrate thresholds:** Flag if below 80% of rated TH/s. Rated TH/s is
resolved via the three-tier system (BiXBiT profile parse → `miner_specs.json`
lookup → 3-day running baseline for unknowns).

---

## Known Infrastructure (current R&D phase — TEMPORARY)

Everything in this section disappears or migrates on cutover (Option γ).
Documenting it so any session knows what's currently in play and what is
scheduled to come off.

- **VPS:** `root@187.124.247.182`, Tailscale `100.106.123.83`, Hostinger
  KVM 8 (32 GB RAM, 8 vCPU). Runs the app, the dashboard API, the approval
  API, OpenClaw, Grafana, Prometheus, and Cloudflare tunnels. Repo at
  `/root/Mining-Guardian/`. **Decommissioned on cutover.**
- **ROBS-PC (Windows, facility R&D center):** `192.168.188.47`, Tailscale
  `100.110.87.1`, AMD Ryzen 7 7800X3D, 32 GB RAM, RTX 4090 running Ollama
  with Qwen 2.5 32B Q4 at port 11434. Hosts the operational Postgres
  container `mining-guardian-db` (Postgres 16-bookworm). Advertises subnet
  `192.168.188.0/24` via Tailscale as the facility subnet gateway.
  **Decommissioned for MG on cutover** (may continue as Bobby's facility
  workstation).
- **AMS API:** `https://api-staging.dev.bixbit.io/api/v1`, workspace 119.
  Cookie-based JWT auth (NOT bearer tokens). See `docs/AMS_API.md`.
- **Slack workspace:** Bixbitusa (`T07AYF6A7DX`)
  - Bobby's user ID: `U07AGTT8CLD`
  - Mining Guardian bot user ID: `U0APQ4VDKGC`
  - Channels: `#mining-guardian` `C0AQ8SE1448` · `#mining-guardian-alerts`
    `C0ARJP300J0` · `#mg-scans` `C0ARLJUJ3BQ` · `#mg-ai-reports` `C0ARSB1U604`
    · `#mg-approvals` `C0AR79YRZ9V` · `#mg-logs` `C0ASH2CPHBJ` ·
    `#mg-critical` `C0AUX8DNGTB`
  - Bobby's DM channel: `D0APH4RFCDT`
  - Slack App ID: `A0APJEN0GGN`
- **Cloudflare tunnels (TEMPORARY, off on cutover):**
  - `dashboard.fieslerfamily.com` → VPS:8585
  - `slack.fieslerfamily.com` → VPS:8686
  - `grafana.fieslerfamily.com` → VPS:3000
- **PDUs:** orient_RPDU 163 @ `192.168.188.15`, 164 @ `192.168.188.16`
- **HVAC (facility-specific, NOT in deployment templates):**
  - Warehouse HVAC at `192.168.188.235`
  - S19J Pro Container HVAC at `192.168.189.235`
  - Distech Eclypse BAS, credentials in `.env`
- **Cron jobs:** see `docs/CRON_SCHEDULE.md` for the canonical list with
  full crontab expressions and log paths. Summary: Pass 2 Claude training
  midnight; Pass 3+4 refinement chain 1 AM; DB maintenance 3:30 AM;
  knowledge backup 4 AM; morning briefing 7 AM; daily operator review
  8 AM; AMS cleanup 12:45 PM; log collection 1 PM; daily deep dive 4 PM;
  log failure report 4:15 PM; hourly benchmark.
- **Operator workstation (Bobby's Mac):** Apple Silicon. Active clone at
  `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`. Python 3.14.3.
  `gh` CLI 2.88.1. Drives the day-to-day repo work; RDPs into ROBS-PC
  for Windows-only tasks.

---

## Apple Developer / Notarization

For installer signing on the Mac Mini path. Credentials notes file at
`/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`. Whole
`Apple Cert/` folder backed up to external HDD.

- **Apple Dev email:** `robfiesler25@gmail.com`
- **Team ID:** `ARJZ5FYU94`
- **Notarization Key Name:** Mining Guardian Notarization
- **Notarization Key ID:** `FPZJ87B3QF`
- **Notarization Issuer ID:** `f53661a7-931a-4976-8f8e-82353256931a`
- **Developer ID Application** and **Developer ID Installer** certs both
  installed in login keychain. Expire 2031-04-28.

Never commit any credential value. Notes file lives outside the repo
intentionally.

---

## What Good Looks Like

- Clean, readable Python — no unnecessary complexity.
- Every new DB table has an index on `(miner_id, scanned_at)` or equivalent.
- Every new Prometheus metric has correct labels:
  `miner_ip, model, site, map_location`.
- LLM prompts are concise — operators are busy, 10-15 lines max response.
- Dashboard API endpoints return JSON only — no HTML except the `status_html`
  route and the Grafana iframe wrappers.
- All services restart cleanly via `systemctl` (R&D) or `launchctl` /
  `docker compose restart` (production) — no manual intervention needed.
- All new code is written with the cutover in mind — no new VPS-only or
  ROBS-PC-only assumptions.
- `# TEMP:` comments on every value that will change at cutover, naming
  the forever-value.
- Every new design decision lands in `docs/DECISIONS.md` as a new D-N entry.
- Every working day has a `docs/SESSION_LOG_YYYY-MM-DD.md` paper trail.

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

*Last major update: April 28 2026 — comprehensive refresh post-Postgres
cutover, post-rename, post-D-13. Documented Phase A (R&D) vs Phase B
(Production) stack split; Cutover Scope Option γ; Repo Rename History
(2026-04-26 typo retired); Database Migration History (SQLite retired
2026-04-23 in favor of Postgres 16); D-13 RAM-detected Ollama model
selection (supersedes D-8); installer-build branch archived in favor of
mg/pr26-mac-mini-installer; expanded Document Map to seven tiers covering
all canonical docs; added Failure Mode 7 (stale mental model) and Failure
Mode 8 (heredoc shell hang); added Vision Anchor 6 (Bitcoin SHA-256 only)
and Vision Anchor 7 (local-only); added pacing rule (May 5 not a constraint);
added DECISIONS.md, ROADMAP, LATENT_BUGS.md, and SESSION_LOG to the
mandatory kickoff reading list; fixed "every hourutes" typo in HVAC rule;
removed all SQLite-as-live language; corrected repo name and path
references throughout. Earlier major update April 9 2026 — added Session
Kickoff Protocol, Vision Anchors 1-5, Failure Modes 1-6, original Document
Map; fixed miner count 49→58; corrected temp operator rule (84°C only,
no yellow tier); added firmware regression and 20-min grace period
operator rules; added repo convention notes.*
