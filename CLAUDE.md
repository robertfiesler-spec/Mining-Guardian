# Mining Guardian

AI-powered Bitcoin mining fleet monitor for BiXBiT USA, Fort Worth TX.
Monitors 58 miners across liquid-cooled hydro racks and an immersion tank.
Provides automated remediation, Slack approval workflow, Grafana dashboards,
and a continuously-learning two-tier LLM system.

**The single sentence version:** Mining Guardian is a learning loop. Every scan
feeds the local LLM, every operator decision refines its rules, every week
Claude deeply re-analyzes the fleet, and every month all customer deployments
share knowledge. The LLM getting smarter is the main feature of the product.

**Where it runs (current):** A single Mac Mini at the customer site, packaged
as a signed-and-notarized `.pkg` installer. Postgres 16 catalog, Ollama
locally, Slack Socket Mode outbound only, no public ingress. Operator reaches
the Mini via Tailscale or local LAN.

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
3. **`docs/DECISIONS.md`** — the canonical log of locked decisions. Every entry is binding unless explicitly superseded by a later entry. Read it before proposing anything that touches Postgres passwords, Ollama models, install dates, or the cutover gate.
4. **`README.md`** — current system architecture, fleet, services, cron jobs
5. **`AI_ROADMAP.md`** — what's built, what's next, hard deadlines
6. **`docs/ROADMAP_TO_MAC_MINI_2026-05-05.md`** — day-by-day cutover plan and the 8-criterion exit gate (D-11)
7. **`REPAIR_LOG.md`** — skim the most recent entries. Running record of bugs found and fixes applied in plain English. Reading it prevents rediscovering problems we already solved.
8. **`docs/LATENT_BUGS.md`** — known bugs that aren't blocking but should not be re-discovered. Skim before any code change.
9. **`docs/MG_UNIFIED_TODO_LIST.md`** — the canonical open-work list. Every fix PR flips a row from 🔴 OPEN to ✅ DONE in the same commit. Read it before claiming something is "next."
10. **Most recent SESSION_LOG** — daily session logs are kept under `docs/archive/2026-04/SESSION_LOG_YYYY-MM-DD.md` once a day rolls over. They are historical context, not live plans. Read the most recent one for orientation.
11. **Git state** — run `git status`, `git log --oneline -20`, `git branch -a`. Note any uncommitted changes, non-main branches, or unmerged work.
12. **Open PRs** — `gh pr list` to see what's in flight.

### Then — and only then — come back with a 5-section report

1. **Project vision** (one paragraph, your own words) — confirm you understand where Mining Guardian is going: a Mac Mini appliance at customer sites, two-tier AI (local Ollama for scans + Claude for weekly training), 8 AI features wired into the scan loop, federated monthly knowledge merge across customers, all data plane local.
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
web page as a "pragmatic replacement" for the LLM, which would have removed the
LLM from the operator decision flow — the main feature of the product. Bobby
caught it. This section exists so the next session doesn't need to.

**Vision Anchor 1 — The LLM IS the product.** The main feature of Mining Guardian
is the LLM getting smarter over time. Every scan feeds it. Every denial refines
it. Every week Claude deeply re-analyzes the fleet. Every month all customer
deployments share knowledge. Any solution that removes the LLM from the
operator's decision flow is the wrong solution, even if it works technically,
even if it's faster to build, even if it's "more reliable." If you find yourself
designing something that bypasses the LLM, STOP and ask.

**Vision Anchor 2 — The Mac Mini is THE product.** A single Mac Mini at the
customer site running the full stack — Postgres, app, Ollama, Grafana — with
no public ingress and only outbound internet. Every decision is evaluated by:
"does this make install/operation easier, harder, or neutral?" The answer should
never be "harder." Local-first, always.

**Vision Anchor 3 — Scale-first, always.** At 58 miners we can get away with
almost anything. At 5,000 miners we cannot. Every new piece of code, every
training prompt, every Claude API call pattern should be designed as if it will
run on a fleet 100x the current size. `train_cohort.py` is the reference for
this — read its docstring before writing anything new that touches the learning
loop.

**Vision Anchor 4 — Federated learning across customer sites.** Each customer
Mac Mini exports `knowledge.json` monthly. Bobby combines all site knowledge
into `master_knowledge.json` using `combine_knowledge.py` (with optional
refinement passes through Claude + local LLM for higher-quality synthesis).
Master gets pushed back to every site. No internet required for the sync — USB
or manual transfer is acceptable. Every customer's fleet makes every other
customer's fleet smarter. This is the long-term moat.

**Vision Anchor 5 — Bitcoin SHA-256 miners ONLY.** Mining Guardian's catalog,
fleet, and AI training are scoped to Bitcoin SHA-256 mining hardware. Do not
add support for altcoin miners, GPU mining rigs, or non-SHA-256 ASICs. If a
session is tempted to broaden scope, stop. The product narrows to Bitcoin
SHA-256 by deliberate choice — the operational rules, AMS endpoints, firmware
quirks, and pool conventions are all SHA-256-specific.

**Vision Anchor 6 — Local-only, no cloud-only dependencies.** The Mac Mini
deployment must function without any cloud-only service. Tailscale and Slack
are the only outbound dependencies for normal operation; Claude API is used
only for weekly training (Sunday) and is non-blocking for the operational
loop. Do not introduce a cloud service that the operational loop depends on
synchronously. Local-first beats convenient cloud integration every time.

**Vision Anchor 7 — Catalog is sacred.** The Mining Intelligence Catalog
(`intelligence-catalog/`) is the live research database. 321 Bitcoin SHA-256
miners seeded from `intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv`,
plus parsers for Bitmain / MicroBT / Canaan / Auradine / Bitdeer, plus the
dual-writer and feedback-loop. This is live code. Do not delete it, do not
rename its directory, do not confuse it with the deprecated `intelligence/`
directory (deleted in the 2026-04-29 doc sweep). When in doubt: catalog data
flows through `intelligence-catalog/`, not `intelligence/`.

---

## Failure Modes to Avoid — Documented Because They Happened

**Failure mode 1 — "Let me propose an alternative."** On April 9 2026, a session
proposed building a keyword-matching `/ask` page instead of fixing the
conversational layer. The existing plan was already written down with a 4-step
build checklist. The session never read that file. **If you're about to propose
an alternative to something that sounds like an existing plan, STOP and search
the docs first. Then execute the existing plan or report what's blocking it —
do not invent a new one.**

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
The afternoon of April 9 a session hit a skill-loading blocker, got frustrated,
and pivoted to "just build a webpage instead." The correct answer was to keep
digging on the skill-loading problem, or read the docs, or ask for help.
Frustration is not a reason to abandon architecture.

**Failure mode 5 — Ignoring time budgets.** When Bobby says "30 minutes hard
cap," that is a commitment, not a suggestion. At the cap, stop and pivot to the
fallback. Do not "just keep going for 5 more minutes." This happened on April 8
(WSL2/Docker debug, budgeted 30 min, ate 2 hours). Set a budget before starting
debug work; respect it when you hit it.

**Failure mode 6 — `cp config_template.json config.json`** on any host. This has
happened twice. Every time it destroys the live AMS credentials and Slack
tokens. Never run this command. Never suggest this command. If you're about to
modify `config.json`, back it up first: `cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)`.

**Failure mode 7 — Working from stale mental model of paths or names.** This
has happened multiple times: agent referenced the old typo'd repo name
(`Mining-Gaurdian`) after the rename, referenced SQLite `guardian.db` after
the Postgres migration, referenced `installer-build` branch after it was
archived, referenced the deprecated `intelligence/` path after Bucket 7.1.
**Always verify path, branch, schema, and command syntax against the current
repo before running anything destructive or proposing a plan.**

**Failure mode 8 — Pasting heredocs with em-dashes or `#` comments into the
Mac terminal.** This hangs the shell at a continuation prompt waiting for a
quote it'll never see. If you need to paste a multi-line block on the Mac
terminal, write the file on the agent side, have the operator `curl` it down,
or use single-line commands with no inline comments. If the shell hangs,
Ctrl+C, and switch to a heredoc-free approach. Captured 2026-04-28.

**Failure mode 9 — Stacking feature PRs on top of other feature PRs.** Captured
2026-04-29. PR #87 was branched off PR #60's branch instead of `main`. PR #89
was branched off PR #88's branch instead of `main`. Both required rebases and
risked carrying unmerged code into the wrong commit history. **Every feature
PR branches off `main`. Period.** The only exception is a pure follow-up to a
PR already merged. Stacked branches are how unrelated history slips into a
review.

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
| **Locked decisions log** | `docs/DECISIONS.md` |
| **Day-by-day cutover plan + 8-criterion exit gate** | `docs/ROADMAP_TO_MAC_MINI_2026-05-05.md` |
| **Running record of bugs and fixes (layman terms)** | `REPAIR_LOG.md` |
| **Known non-blocking bugs** | `docs/LATENT_BUGS.md` |
| **Canonical open-work list** | `docs/MG_UNIFIED_TODO_LIST.md` |
| **AI feature status, roadmap, hard deadlines** | `AI_ROADMAP.md` |
| **Overall system architecture, fleet, services** | `README.md` |

### Tier 2 — Architecture and design

| Topic | Authoritative source |
|---|---|
| Full capabilities list (today + future) | `docs/CAPABILITIES.md` |
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
| Web GUI operator console | `docs/WEB_GUI_OPERATOR_CONSOLE.md` |
| Operator schedules | `docs/OPERATOR_SCHEDULES.md` |
| Per-model profile maps and rated TH/s | `miner_specs.json` + `docs/PROFILE_MAP_QUESTIONS.md` |

### Tier 3 — Mac Mini installer and deployment

| Topic | Authoritative source |
|---|---|
| Mac Mini deployment runbook | `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` |
| `.pkg` build runbook | `docs/RUNBOOK_PKG_REBUILD.md`, `docs/RUNBOOK_2026-04-28_pkg_build.md` |
| `.pkg` distribution runbook | `docs/RUNBOOK_DISTRIBUTION_v1.0.0.md` |
| Deployment checklist | `DEPLOYMENT_CHECKLIST.md` |
| Release notes | `docs/RELEASE_NOTES_v1.0.0.md` |
| Customer-facing brochure (PDF) | `docs/customer/MiningGuardian_Brochure.pdf` |
| Customer-facing program instructions (PDF) | `docs/customer/MiningGuardian_Program_Instructions.pdf` |
| Customer-facing setup manual (PDF) | `docs/customer/MiningGuardian_Setup_Manual.pdf` |

### Tier 4 — Postgres catalog (Mining Intelligence Catalog)

| Topic | Authoritative source |
|---|---|
| Mining Intelligence Catalog (live, in-repo) | `intelligence-catalog/` |
| Catalog seed data (321 SHA-256 miners) | `intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv` |
| Catalog seed README | `intelligence-catalog/seed-data/README.md` |
| Intelligence catalog status | `docs/INTELLIGENCE_CATALOG_STATUS.md` |
| Intelligence report API | `docs/INTELLIGENCE_REPORT_API.md` |
| Catalog orphan tables | `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md` |
| Empty stub tables | `docs/EMPTY_STUB_TABLES.md` |
| Bulk import tooling | `mg_import_tool/` |

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
| Operator schedules | `docs/OPERATOR_SCHEDULES.md` |
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

### Tier 7 — Audits and historical

Audit reports, session logs, and historical handoffs are kept under
`docs/archive/2026-04/` for paper-trail purposes. Read them when investigating
something they cover; do not treat them as live plans. Examples (not
exhaustive): `SESSION_LOG_*.md`, `SESSION_HANDOFF_*.md`, `POSTGRES_MIGRATION_*`,
`DB_STATE_*`, `AUDIT_SUMMARY_2026-04-13.md`.

If a topic is not in this table AND not in any of these files, then and only
then is it a candidate for a new doc. Update this table when you add one.

---

## Stack Context — One Phase, Mac Mini

Mining Guardian runs on a single Mac Mini at the customer site. There is no
secondary host, no cloud catalog, no remote LLM. Everything below describes
the live deployment.

- **Language:** Python 3.12+ on the customer Mac Mini. Python 3.14.3 on
  Bobby's Mac (development workstation).
- **Primary daemon:** `core/mining_guardian.py` — scans every hour, runs all
  8 AI features in `loop()` after each scan.
- **Dashboard API:** `api/dashboard_api.py` — FastAPI on port 8585. Serves
  Prometheus metrics, Retool endpoints, Grafana iframes, and `/query/*`
  endpoints.
- **Approval API:** `api/approval_api.py` — FastAPI on port 8686, localhost-
  bound. Handles APPROVE/DENY/approve_selected and Slack interactive
  block_actions. Web GUI mode selector and operator schedules also live here.
- **Database engine:** PostgreSQL 16 (`postgres:16-bookworm` image). Postgres
  is the canonical store. SQLite is no longer in the data plane.
- **Database name:** `mining_guardian` (operational catalog). Operational
  password is `MG_DB_PASSWORD` from `.env`, never committed.
- **Container name:** `mining-guardian-db` (the Postgres container that hosts
  the operational database).
- **Monitoring:** Prometheus + Grafana, 6 dashboards.
- **Two-tier AI:**
  - **Local LLM** — runs on every scan (~4.6s per analysis). Ollama natively
    on the Mac Mini at `http://localhost:11434/api/generate`. Model is
    selected at install time by RAM detection (D-13):
    - 16 GB RAM (e.g., base Mac Mini M4) picks `llama3.2:3b` (q4 default)
    - 24 GB RAM or more picks `qwen2.5:14b-instruct-q4_K_M`
    - Customer can override the auto-pick before download.
  - **Claude API** — Sonnet, used for weekly deep training (`train_cohort.py`,
    Sundays at the time set in `docs/CRON_SCHEDULE.md`) and ad-hoc deep
    analysis. Cost ~$1-2/month at current scale. Bobby's proof-of-concept
    mine keeps Claude weekly; production customer Mac Minis can opt out and
    use local LLM only.
- **Network:** Mini sits on the miner LAN `192.168.188.0/24`. Tailscale
  installed for remote operator access only — data plane stays local
  (D-9). `CATALOG_DB_HOST=localhost`.
- **Public ingress:** none. Slack Socket Mode is outbound-only. Operator
  reaches the Mini via Tailscale or local LAN.
- **Process supervision:** `launchd` plists for the daemon, dashboard API,
  approval API, log collector, and weekly training. Migrations 001-005 run
  on first boot via the installer's preflight phase.

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
  customer-Mini equivalent path).
- **NEVER refer to SQLite as live.** SQLite was retired during the 2026-04-23
  Postgres migration. Any reference to `guardian.db` as a current data source
  is a bug.
- **NEVER add a second Slack Socket Mode consumer.** The MG bot owns Socket
  Mode for this workspace. Adding another Socket Mode consumer will break
  Slack message routing.
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
- **Catalog directory is `intelligence-catalog/`, never `intelligence/`.** The
  legacy `intelligence/` directory was deleted in the 2026-04-29 doc sweep.
  Any new path reference to `intelligence/` is a bug.

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

**Defer to the agent on plumbing decisions.** Bobby has stated: "no need to
wait for me on decisions i am always going to defer to your recommendation."
For mechanical / plumbing choices (which directory, which file pattern, which
verification command), pick the recommendation and proceed. Reserve the
"ask first" pattern for genuinely ambiguous product or scope decisions.

---

## Repo Conventions

- **Repo name:** `Mining-Guardian` (hyphen, no space). The GitHub remote is
  `robertfiesler-spec/Mining-Guardian`.
- **Default branch:** `main`. Tagged `📦 v1.0.0` and (post-install-day)
  `v1.0.0-install-ready`.
- **Active local clone (Mac):** `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`
  — no quotes needed (no spaces, no special characters).
- **Customer Mac Mini clone:** installed by the `.pkg` to its own runtime
  location; the operator does not interact with the repo there.
- **Python files use venv** — always `source venv/bin/activate` on the dev Mac
  before running scripts. On macOS dev workstations, `python3` is fine.
- **Commit messages:** brief description of what changed and why. Conventional
  prefixes welcome and recommended (`feat:`, `fix:`, `docs:`, `chore:`,
  `refactor:`, `test:`).
- **Always test imports before pushing:** `python3 -m py_compile <file>`.
- **PR cadence:** every code or doc change goes through a PR. Squash-merge
  to main, delete branch on merge.
- **Branch naming:** `mg/prNN-<short-name>` for feature/installer work,
  `docs/<short-name>` for doc-only changes, `archive/<branch>-YYYYMMDD`
  for archived branches.
- **Every fix PR flips its `MG_UNIFIED_TODO_LIST.md` row from 🔴 OPEN to ✅
  DONE in the same commit.** No separate "update the todo" follow-up PR.
- **Never branch a feature PR off another open feature PR — always off `main`.**
  Lessons: PR #60→#87 stack and PR #89→#90 stack both required rework.

### Repo Rename History

- **2026-04-26 (Sunday)** — `Mining-Gaurdian` → `Mining-Guardian`. The original
  typo was an intentional joke that became a real maintenance problem (every
  command needed quoting; tab completion was awkward; new contributors thought
  it was a typo). Rename was the cleaner long-term fix.
- **2026-04-28 (Tuesday)** — Bobby's local Mac clone re-cloned with the
  correct name. Old folder archived as `Mining Gaurdian.OLD-20260428`.

### Database Migration History

- **Pre-2026-04-23** — SQLite at `guardian.db` was the operational store.
  Retired.
- **2026-04-23 → 2026-04-24** — Migrated to PostgreSQL 16. Container
  `mining-guardian-db` (`postgres:16-bookworm`) hosts the operational database
  `mining_guardian`. The migration script lives at
  `migrations/migrate_sqlite_to_postgres.py` gated by `MG_ALLOW_MIGRATION=1`
  (D-6). The historical migration plan and per-day status reports are archived
  under `docs/archive/2026-04/`.

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
hardware failure.

**OPERATOR RULE — 20-minute post-restart grace period:**
After any restart (manual OR overnight auto), suppress the miner from action
recommendations for 20 minutes. Wait for `minerStatus = 0` (mining) before
evaluating hashrate or recommending next steps.

**Hashrate thresholds:** Flag if below 80% of rated TH/s. Rated TH/s is
resolved via the three-tier system (BiXBiT profile parse → `miner_specs.json`
lookup → 3-day running baseline for unknowns).

---

## Working Practices

### Document as you go, not after

Every session that adds a feature or makes a design decision MUST update the
relevant docs in the SAME commit as the code. No deferring documentation
to "later." This rule was added at end of day April 9 2026 because the
morning session had been shipping code without documentation updates, which
is the same silent-skip pattern we keep diagnosing in the code itself.

What this means in practice:

- If you write a new module or rewrite a function significantly, commit the
  code change TOGETHER with a `REPAIR_LOG.md` entry (or a session-log entry
  for that day, or updated design doc) explaining what changed and why.
- If you discover a new operator rule, update CLAUDE.md (and/or
  `docs/OPERATOR_RULES.md`) in the same commit as the code that enforces it.
- If you find a degraded miner or a production anomaly, flag it in
  `REPAIR_LOG.md` (or `docs/LATENT_BUGS.md` for non-blocking issues) before
  the session ends.
- If you make a decision that will affect future sessions, capture it in
  `docs/DECISIONS.md` as a new D-N entry before moving on.
- If you flip an open item to done, also flip its `MG_UNIFIED_TODO_LIST.md`
  row from 🔴 OPEN to ✅ DONE in the same commit.

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

## The Daily Deep Dive — permanent

The daily Qwen deep dive (`ai/daily_deep_dive.py`) runs once a day on the
local LLM and writes to `knowledge['daily_deep_analyses']`. The Sunday
Claude weekly training merges those entries into its prompt via a permanent
merge block in `ai/train_cohort.py`. **This block is NOT scaffolding. It MUST
NOT be removed.** The daily deep dive is the core long-term learning mechanism
for the local LLM.

If a future session proposes removing the daily deep dive or its Sunday merge
block, **stop and re-read this section, the corresponding `REPAIR_LOG.md`
entry, and `docs/DAILY_DEEP_DIVE_DESIGN.md`.**

## The 4-Pass Weekly Refinement Chain

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

**Resume-safety guarantees (added after a Pass 4 Anthropic 529 crash):**

- Pre-flight checks validate all dependencies before firing any model call
- WIP checkpointing after each pass (survives later crashes)
- `--resume-from {3,4}` flag allows resuming after partial failures
- `--smoke-test` validates plumbing in ~60s before burning 20+ minutes
- `--dry-run` shows plan without firing model calls

**Script location:** `ai/refinement_chain.py`

**When to run:** After weekly training completes. Currently scheduled per
`docs/CRON_SCHEDULE.md`.

---

## Known Infrastructure (current)

- **Customer Mac Mini:** runs the full stack (Postgres, app, Ollama, Grafana,
  log collection). Connected to the miner LAN. Tailscale for remote operator
  access; data plane stays local.
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
- **PDUs:** orient_RPDU 163 @ `192.168.188.15`, 164 @ `192.168.188.16`
- **HVAC (facility-specific, NOT in deployment templates):**
  - Warehouse HVAC at `192.168.188.235`
  - S19J Pro Container HVAC at `192.168.189.235`
  - Distech Eclypse BAS, credentials in `.env`
- **Cron jobs:** see `docs/CRON_SCHEDULE.md` for the canonical list with
  full crontab expressions and log paths. Summary: weekly Claude training
  Sunday; refinement chain right after; DB maintenance early morning;
  knowledge backup; morning briefing; daily operator review; AMS cleanup;
  log collection; daily deep dive; log failure report; hourly benchmark.
- **Operator workstation (Bobby's Mac):** Apple Silicon. Active clone at
  `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`. Python 3.14.3.
  `gh` CLI 2.88.1.

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
- All services restart cleanly via `launchctl` — no manual intervention
  needed.
- All new code is written for the Mac Mini deployment — no host-specific
  assumptions outside the installer.
- Every new design decision lands in `docs/DECISIONS.md` as a new D-N entry.

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

*Last major update: April 29 2026 — full repo doc sweep (Tier 3 REWRITE).
Removed VPS / ROBS-PC / Cloudflare / fieslerfamily references (decommissioned
on Mac Mini cutover). Removed all OpenClaw references (Bucket 4 removed the
component from the system). Removed deprecated `intelligence/` references in
favor of the live `intelligence-catalog/` directory (Bucket 7.1 removed the
deprecated path). Collapsed Phase A R&D vs Phase B Production split into a
single "Mac Mini" section. Collapsed May Migration Changes section into the
Daily Deep Dive section (the comparison merge block was removed on cutover;
that move is no longer pending). Refreshed Document Map to point at docs that
exist after Tier 1 deletes and Tier 2 archives. Added Failure Mode 9 (stacked
PRs) and Vision Anchor 7 (catalog is sacred). Earlier major update April 28
2026 — comprehensive refresh post-Postgres cutover, post-rename, post-D-13.
Earlier major update April 9 2026 — added Session Kickoff Protocol, original
Vision Anchors, Failure Modes, Document Map; fixed miner count 49→58;
corrected temp operator rule (84°C only, no yellow tier).*
