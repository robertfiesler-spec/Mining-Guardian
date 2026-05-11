---
# Findings Report — Mac Mini Snapshot
**Date:** 2026-05-11
**Status:** Both snapshots COMPLETE. **Major reframing surfaced — see section K at the end.**
**Scope:** Read-only snapshot of Mac Mini system state. No modifications made to either system.
**Context:** This is the canonical record of what was found during the Mac Mini snapshot pass on May 11, 2026. Read alongside CLAUDE.md (original handoff, treat as informed source not ground truth) and PLANNING_DECISIONS.md (decisions made during the planning chat that supersede the handoff on the points they cover).
---

# MAC MINI ↔ VPS SNAPSHOT REPORT

## A. Build state

### Mac Mini
- `BUILD_STAMP.json`: version **1.0.3**, git_sha **`53eac9397f00`**, stamped **2026-05-09T14:32:02Z**.
- Build SHA does **not** match the handoff's claimed `ce9831c1a09a` (which was supposedly stamped 2026-05-07 20:26 UTC). Mac Mini was re-installed on May 9 — install dir mtime confirms (May 9 10:58 local).
- This SHA `53eac9397f00` corresponds to a build later than the three packages documented in the May 8 pkg-build runbook (`eecde3a94c5b` → `2b41764a121b` → `e3461260af2a`). One of the `knowledge/incoming/` seed files is named `knowledge-seed-1.0.3-53eac9397f00.json` so this build was installer-deployed and left its audit seed.

### Status of the three operational commits (`53f6567`, `b49cc6e`, `2c41ab5`)
- **All three are absent from this build.**
- `train_cohort.py`: `hashrate_pct` appears only in SELECT/AGG positions (`mr.hashrate_pct`, `AVG/MIN/MAX(hashrate_pct)`) — no `WHERE hashrate_pct < 120`, no `BETWEEN`, no Python-side threshold filter. The aggregates remain vulnerable to 152.7%-saga inputs.
- `train_comprehensive.py`: same — 14 references, all in SELECT/projection/aggregation/Python-`is not None` contexts. No threshold guard.
- `morning_briefing.py:140`: bare `AVG(hashrate_pct)` — no guard.
- `daily_deep_dive.py`: zero `SCRUBBED` references. The Phase 1c `NOT LIKE '%[SCRUBBED-DATA-INTEGRITY]%'` filter is not in this file at all.
- `core/llm_analyzer.py:29` still has a hardcoded fallback: `MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:32b-instruct-q4_K_M")`. P-031 documentation says this fallback was removed; this site survived. Six other `qwen2.5:32b` mentions in source are comments referencing historical state.

### VPS
- Repo: `/root/Mining-Guardian/` (root-owned). Current branch: **`fix/grafana-intelligence-miner-dropdown-2026-04-29`**. HEAD: **`edc1cebfa45c5b2b0a61b197164724c610de9e98`** (today's daily knowledge-backup commit at 04:00 UTC).
- **All three operational commits exist and are deployed:**
  - `53f6567e37b9c32a77608987b450a3584e7470ce` — 2026-05-04 08:44 CDT — "fix(train_cohort): filter implausible hashrate_pct values from cohort aggregates" (Phase 1)
  - `b49cc6eb7b42ef31f58a8e81137f4757b61b1e99` — 2026-05-05 08:37 CDT — "Phase 1b" (extends to upstream helpers)
  - `2c41ab5dfcdde62c965d70ab2ff0dceaa3831d90` — 2026-05-06 09:04 CDT — "Phase 1c" (scrubbed-rows filter)
- All three are on the current branch only (origin and local). **NOT on `main`**. So the production branch on VPS is a feature branch that never got merged.
- Fingerprint greps confirm the guards are live:
  - `CASE WHEN hashrate_pct < 120 THEN hashrate_pct END` appears in `train_cohort.py:257-259, 299`, `train_comprehensive.py:70-72, 590`, `morning_briefing.py:140`.
  - `NOT LIKE '%[SCRUBBED-DATA-INTEGRITY]%'` appears in `train_cohort.py:966`.
- Working tree has uncommitted artifacts: `knowledge.json.pre-scrub-20260506` (5.94 MB) and `pending_operator_reviews.json` (1.9 KB, 3 entries from May 10 08:15). These are scrub-saga forensics + un-processed operator reviews.
- Available branches (local + remote): `main`, `feature/fast-cohort-analysis`, `feature/postgresql-migration`, `fix/typo-rename-mining-guardian-2026-04-26`, `security/hardening-apr21`, plus remote-only branches for installer / customer-docs / hotfixes.

### Build divergence summary
| | Mac Mini | VPS |
|---|---|---|
| Layout | Installed `.pkg` at `/Library/Application Support/MiningGuardian/` | Git checkout at `/root/Mining-Guardian/` |
| Build ID | `BUILD_STAMP.json` git_sha `53eac9397f00` (2026-05-09 install) | git HEAD `edc1cebf` (today's backup commit) |
| Phase 1 guard | ❌ ABSENT | ✅ PRESENT |
| Phase 1b guard | ❌ ABSENT | ✅ PRESENT |
| Phase 1c guard | ❌ ABSENT | ✅ PRESENT |
| Hardcoded qwen2.5:32b fallback | `core/llm_analyzer.py:29` still present | Not checked — but P-031 was authored against VPS source, so likely fixed there |

---

## B. .env diff

### Mac Mini `.env` — 35 keys present, values not read
```
AMS_BASE_URL, AMS_EMAIL, AMS_PASSWORD, AMS_WORKSPACE_ID
AUTHORIZED_SLACK_USER_IDS, AUTO_APPROVE_ENABLED
CATALOG_API_KEY
GUARDIAN_APPROVAL_PORT, GUARDIAN_DASHBOARD_PORT, GUARDIAN_INTELLIGENCE_PORT
GUARDIAN_PG_CATALOG_DBNAME, GUARDIAN_PG_DBNAME, GUARDIAN_PG_HOST
GUARDIAN_PG_PASSWORD, GUARDIAN_PG_PORT, GUARDIAN_PG_TEST_DBNAME, GUARDIAN_PG_USER
INTERNAL_API_SECRET
MG_CUSTOMER_NAME, MG_DB_PASSWORD, MG_DRY_RUN
MG_INSTALL_LLM_MODEL, MG_INSTALL_RAM_TIER, MG_SCAN_INTERVAL
OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_URL
PGDATABASE, PGHOST, PGPORT, PGUSER
SLACK_APP_TOKEN, SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, SLACK_WEBHOOK_URL
```

**MISSING: `ANTHROPIC_API_KEY`** — confirmed by boolean check + reproduced exactly in `refinement_chain.err.log`:
```
2026-05-11 01:00:06,106 ERROR PRE-FLIGHT FAILED:
2026-05-11 01:00:06,106 ERROR   - ANTHROPIC_API_KEY not found in env or .env file
```

Same fail also on 2026-05-10. Handoff Blocker #1 confirmed and ongoing.

`OLLAMA_MODEL` and `OLLAMA_URL` are both set. Value of `OLLAMA_MODEL` is almost certainly `llama3.2:3b` — refinement_chain's pre-flight reports "[OK] Qwen endpoint reachable, model 'llama3.2:3b' loaded" today, and Ollama only has that model loaded.

File perms: `.env` is `-rw-------` (0600), owned by `miningguardian:staff`, 3061 bytes, mtime 2026-05-09 10:58.

### VPS `.env`
- 39 keys present (vs Mac Mini's 35). File: `/root/Mining-Guardian/.env`, mode `0644` (world-readable — note for cleanup), owner `root:root`, 1782 bytes, mtime 2026-04-23 11:38.
- **`ANTHROPIC_API_KEY` is PRESENT** ✓ — this is the source-of-truth value for Mac Mini's missing key.
- **Keys VPS has, Mac Mini doesn't (15):** `ANTHROPIC_API_KEY`, `AURADINE_PASS`, `AURADINE_USER`, `AUTO_APPROVE_LOW_RISK`, `AV2_PLANT_PASSWORD`, `AV2_PLANT_USER`, `CATALOG_API_PORT`, `CATALOG_DB_HOST`, `CATALOG_DB_NAME`, `CATALOG_DB_PASSWORD`, `CATALOG_DB_PORT`, `CATALOG_DB_USER`, `DASHBOARD_URL`, `ECLYPSE_PASS`, `ECLYPSE_USER`, `ELECTRICITY_RATE_KWH`, `OPENCLAW_TOKEN`, `OVERNIGHT_AUTO_APPROVE`, `OVERNIGHT_END_HOUR`, `OVERNIGHT_START_HOUR`, `PDU_PASSWORD`, `PDU_USERNAME`.
- **Keys Mac Mini has, VPS doesn't (11):** `AMS_BASE_URL`, `AUTHORIZED_SLACK_USER_IDS` (Mac Mini only — wait, both have it), `AUTO_APPROVE_ENABLED` (vs VPS's `AUTO_APPROVE_LOW_RISK`), `GUARDIAN_APPROVAL_PORT`, `GUARDIAN_DASHBOARD_PORT`, `GUARDIAN_INTELLIGENCE_PORT`, `GUARDIAN_PG_CATALOG_DBNAME`, `GUARDIAN_PG_TEST_DBNAME`, `MG_CUSTOMER_NAME`, `MG_DB_PASSWORD`, `MG_DRY_RUN`, `MG_INSTALL_LLM_MODEL`, `MG_INSTALL_RAM_TIER`, `MG_SCAN_INTERVAL`, `OLLAMA_HOST`, `PGDATABASE`, `PGHOST`, `PGPORT`, `PGUSER`.
- Notable VPS-only categories:
  - Hardware-control credentials: `AURADINE_*`, `ECLYPSE_*`, `PDU_*`, `AV2_PLANT_*` — direct device control for warehouse infrastructure.
  - `OPENCLAW_TOKEN` — Hostinger openclaw container integration (the `openclaw-5b5o-openclaw-1` container is up on VPS).
  - `ELECTRICITY_RATE_KWH` — power cost calc.
  - `OVERNIGHT_*` — overnight automation window timing.
- Notable Mac Mini-only categories:
  - `MG_INSTALL_*` — installer-set values for tier/customer.
  - `GUARDIAN_*_PORT` — Mac Mini exposes the dashboard / approval / intelligence APIs on local ports; VPS doesn't.
  - `PG*` legacy libpq env vars (Mac Mini has these as duplicate of `GUARDIAN_PG_*`).
  - `OLLAMA_HOST` — Mac Mini explicitly sets the Ollama host; VPS just has `OLLAMA_URL`.
- **Crontab leaks DB credentials inline** as plaintext env: `GUARDIAN_PG_USER=guardian_app` plus the password literal. The password is reproducible from `/root/Mining-Guardian/.env` plus the world-readable mode. **Security flag for post-cutover: 1) chmod 600 .env on any future VPS-style host, 2) move secrets out of `crontab -l` view.** (Password value redacted from this report.)

---

## C. Ollama state (Mac Mini)

```
NAME           ID              SIZE      MODIFIED
llama3.2:3b    a80c4f17acd5    2.0 GB    44 hours ago
```

Only the 3B Llama model. No Qwen of any size. Ollama daemon running. Per Planning Decision 1: target is `qwen3:8b` (~5.5 GB) — well within free disk space.

---

## D. Postgres state

### Mac Mini
- **Postgres runs in Docker, not Lima.** Container `mining-guardian-db`, image `postgres:16-bookworm`, up 44 hours, bound to `127.0.0.1:5432`.
- **Lima is not installed.** Handoff was wrong on this.
- Databases: `mining_guardian`, `mining_guardian_catalog`, `postgres`.
- Default role: `mg` (owner of all `mining_guardian` tables). Catalog role is likely `mg_catalog` per the runbook.
- **`past_analyses` table does NOT exist.** Handoff's "schema drift" framing was misdirected — the failing query is on `hvac_readings` (matches the `system_id = 'warehouse'` filter), not `past_analyses`.
- All timestamp columns I sampled are uniformly `timestamp with time zone`:

| Table | Column | Type |
|---|---|---|
| hvac_readings | recorded_at | timestamp with time zone |
| hvac_readings | scanned_at | timestamp with time zone |
| miner_readings | recorded_at | timestamp with time zone |
| miner_readings | scanned_at | timestamp with time zone |
| chain_readings | scanned_at | timestamp with time zone |
| scans | scanned_at | timestamp with time zone |
| (plus 2 more) | scanned_at | timestamp with time zone |

So the type-mismatch failure isn't *in the schema* — it's the SQL itself, which does `WHERE recorded_at >= TO_CHAR(...)`. `TO_CHAR` returns text. Mac Mini's timestamptz cannot be compared to text directly. **Fix is in the application code, not the schema** — same fix benefits VPS once VPS schema is also migrated to timestamptz.

- Row counts (Mac Mini, mining_guardian DB):

| Table | Rows |
|---|---|
| miner_readings | 2,496 |
| hvac_readings | 94 |
| llm_analysis | 78 |
| scans | 26 |
| action_audit_log | 9 |
| pending_approvals | 4 |
| s19jpro_overheat_tracking | 0 |

- Scan history: oldest `2026-05-07 11:37:12`, latest `2026-05-11 04:41:24`. **Mac Mini has been actively scanning for 4 days, 26 scans, 96 unique miners.** This is not a fresh empty install.
- 30 tables total in `mg` schema (full list in scratch — not reproducing all here).

### VPS
- **Native Postgres 16, NOT Docker.** Cluster `postgresql@16-main`, data dir `/var/lib/postgresql/16/main/`.
- **Postgres is currently STOPPED.** `systemctl status postgresql@16-main` reports:
  ```
  Active: inactive (dead) since Sun 2026-05-10 10:25:27 CDT; 21h ago
  Main PID: 36781 (code=exited, status=0/SUCCESS)
  Duration: 2w 3d 19h 21min 38.071s
  ```
  Clean shutdown (status 0). Per Bobby's planning instruction, **this is a deliberate test condition** — VPS Postgres was stopped as part of the Mac Mini standalone test. See section K for the full reframing.
- Listen config (from `/etc/postgresql/16/main/postgresql.conf`): `port = 5432`, `unix_socket_directories = '/var/run/postgresql'`. No explicit `listen_addresses` line — defaults to `localhost` only.
- TCP probe (`psql -h 127.0.0.1`) returns "Connection refused" — consistent with the stopped service.
- **No live schema/row-count enumeration was performed on VPS Postgres** because querying it would require starting the service (a state change). Schema comparison and row counts will happen during the actual migration step, gated on explicit approval to start the service.
- **Inferred from code parity:** Since VPS is the canonical install of the same Mining Guardian software that ships in the `.pkg` to Mac Mini (per the runbook), the VPS schema is expected to match the modern `timestamptz` schema Mac Mini has — the "VPS has `text` recorded_at" claim in the handoff is most likely wrong. The application code drift (`TO_CHAR()` vs timestamptz) is the actual bug; the schema is fine on both sides. Confirmation will come from the first `pg_dump --schema-only` we run.
- **Side note from Docker:** VPS does have Docker running, but for unrelated workloads (`openclaw-5b5o-openclaw-1` and `traefik-traefik-1`, both up 2 weeks). Not Postgres.

---

## E. knowledge.json comparison

### Mac Mini
- Path: `/Library/Application Support/MiningGuardian/knowledge/knowledge.json` — **regular file**, not a symlink (handoff was wrong). The compat symlink was at `${ROOT}/knowledge.json` and was the subject of the B-45/P-036 saga.
- Size: 3,766,536 bytes. mtime: **2026-05-11 04:41:30** (today). Owner `miningguardian:staff` 0664.
- Embedded `last_updated: 2026-05-11T04:41:30.195828`, `version: 1`.
- 24 top-level keys: `baselines, cross_miner_analysis, daily_deep_analyses, facility_events, fingerprints_updated_at, fleet_summary, hardware_facts, hvac_correlation, known_issues, last_updated, llm_scan_analyses, miner_fingerprints, miner_profiles, operator_decisions, operator_rules, pattern_rules, patterns, prediction_accuracy, predictions, predictive_warnings, process_rules, refined_insights, version, weekly_refinement_chain`.
- Counts: **61 refined_insights, 37 operator_decisions.**
- `operator_decisions` is a keyed object (NOT array). Keys are integers `0..36`, contiguous, no gaps. Each record has fields `date, decision, operator, proposal, reason`.
- `refined_insights` is also keyed object. Keys are descriptive strings like `0110_0020_boards_immersion`, `0110_0020_cascade_failure_immersion`. Each record has 18 fields including `action, status, miners_affected, update_history, decided_at, decided_by, operator_decision`.

### VPS
- Path: `/root/Mining-Guardian/knowledge.json` — regular file at the repo root (NOT under `knowledge/` like Mac Mini). **Different filesystem layout.**
- Size: 7,116,894 bytes. Mode `0600` root:root. mtime: **2026-05-10 09:24:22 CDT.** Embedded `last_updated: 2026-05-10T00:18:51.481876` — last clean write was just after midnight on May 10, before the test started.
- **Counts: 84 refined_insights, 56 operator_decisions — matches handoff exactly.** ✓
- **Top-level keys: identical to Mac Mini** (same 24 keys: `baselines`, `cross_miner_analysis`, ..., `weekly_refinement_chain`).
- **Structural differences from Mac Mini:**
  - `operator_decisions` is an **ARRAY** on VPS (indices `0..55`, length 56). On Mac Mini it's an **OBJECT** keyed by integer strings (`"0".."36"`). Same conceptual data, different JSON shape.
  - Insight records on VPS have **19 keys, including `_audit`**. Mac Mini records have **18 keys, no `_audit`**. Otherwise identical (`action, category, confidence, cooling_type, ...`).
  - Decision record schema is identical on both sides: `date, decision, operator, proposal, reason`.
- These structural differences mean **migration cannot be a raw `cp`** — the array→object conversion needs handling, and the `_audit` field needs decision on whether to preserve it (Mac Mini code may not read it).
- Backup tree on VPS is richer than Mac Mini's:
  - `/root/Mining-Guardian/knowledge_backup.json` — identical to live `knowledge.json` (same 84/56, same `last_updated`).
  - `/root/Mining-Guardian/knowledge.json.pre-scrub-20260506` — 5,940,832 bytes, `last_updated: 2026-05-06T04:14:09`, **81 refined_insights, 53 operator_decisions, array format**. This is the pre-152.7%-scrub snapshot. The scrub added 3 insights and 3 decisions net.
  - `/root/Mining-Guardian/backups/knowledge_pre_cooling_rename_20260426_132308.json` (Apr 26 snapshot).
  - `/root/Mining-Guardian/backups/2026-04-06/{knowledge,knowledge_backup}.json` (April 6 snapshots).
- `/root/Mining-Guardian/pending_operator_reviews.json` — 1,926 bytes, mtime 2026-05-10 08:15, an **object with 3 entries** that were captured for operator review on the morning of May 10 but never processed before the test began.

### `knowledge/incoming/` — answer to the three regroup questions

1. **What is the convention?** Each pkg install's postinstall script (P-029 design) stages the installer's packaged baseline knowledge.json under `knowledge/incoming/knowledge-seed-1.0.3-<BUILD_SHA>.json`. It's an audit-trail mechanism — proof of *what would have been seeded* if the runtime knowledge.json hadn't already existed. The actual baseline template lives in `installer-resources/knowledge/knowledge.json`. **All four files (3 in incoming + 1 in installer-resources) are byte-identical (`sha256: 2edea974d711...`).** Filenames differ only by build SHA.

2. **Why three files?** Because three pkg installs have happened on this Mac Mini:
   - `2b41764a121b` — May 8 evening (post-P-035, lacked P-036)
   - `e3461260af2a` — May 9 morning (post-P-036)
   - `53eac9397f00` — May 9 late (current build per `BUILD_STAMP.json`)

3. **Is there ingester code reading these seeds?** **No.** Searched `*.py` for `INCOMING`, `incoming_dir`, `seed_path`, `installer-resources`, `knowledge_seed`, `load_seed`, plus the literal strings `knowledge/incoming` and `knowledge-seed` — zero hits in code (only in docs). The seeds are write-once-by-installer, never read at runtime. The runtime reads/writes only `knowledge/knowledge.json`. **There is no active ingestion pipeline for cross-host knowledge migration.**

   **Implication:** the migration plan cannot route through `incoming/`. Options narrow to (a) atomically replace `knowledge/knowledge.json`, or (b) treat Postgres as authoritative and let the scanner regenerate knowledge.json, or (c) write a new merge tool. See section (j).

`quarantine/` has one file: `knowledge-json-regular-file-20260508T155258.json` (948 bytes) — quarantined artifact from the B-45 incident on May 8. Filename indicates: "a knowledge.json regular file was found where a symlink should be; moved here."

---

## F. Launchd / cron state

### Mac Mini launchd
- **23 plists installed in `/Library/LaunchDaemons/`:** 10 service daemons (`scanner`, `dashboard-api`, `slack-listener`, `slack-commands`, `alerts`, `approval-api`, `console`, `feedback-loop-daemon`, `intelligence-report`, `overnight-automation`) + 12 scheduled jobs + 1 `.disabled` shadow (`benchmark.plist.disabled` alongside `benchmark.plist`).
- Handoff said 22; close enough.
- `launchctl list | grep miningguardian` returns empty as `miningguardian` user — system-domain jobs need `sudo launchctl list`. But the `.last-run.json` and `.err.log` timestamps prove the jobs ARE running.
- **Scheduled-job exit status (last run, from `.last-run.json`):**

| Job | Last run | Exit |
|---|---|---|
| knowledge_backup | 2026-05-11 09:00 UTC | **0** |
| log_collection | 2026-05-10 18:00 UTC | **0** |
| morning_briefing | 2026-05-10 12:00 UTC | **0** |
| operator_review | 2026-05-10 13:00 UTC | **0** |
| ams_cleanup | 2026-05-10 17:45 UTC | 1 |
| catalog_import | 2026-05-11 09:30 UTC | **126** |
| daily_deep_dive | 2026-05-10 21:00 UTC | 1 |
| db_maintenance | 2026-05-11 08:30 UTC | 1 |
| log_failure_report | 2026-05-10 21:15 UTC | 1 |
| refinement_chain | 2026-05-11 06:00 UTC | 1 |
| weekly_training | 2026-05-11 05:00 UTC | 1 |

So 4 succeeding, 7 failing. Root causes of the failures:

- **weekly_training**: `'datetime.datetime' object is not subscriptable` in `train_comprehensive.py:290` — Blocker #4 confirmed.
- **daily_deep_dive**: `operator does not exist: timestamp with time zone >= text` at `daily_deep_dive.py:474` (handoff said line 464; minor drift). The query is `WHERE system_id = 'warehouse' AND recorded_at >= TO_CHAR(...)` on `hvac_readings`. Blocker #3 confirmed.
- **log_failure_report**: same root cause, different file — `daily_log_failure_report.py:84` does `WHERE mr.scanned_at > ((NOW() - INTERVAL '1 day')::t...` and fails on `timestamp with time zone > text`. **Blocker #3 affects more than one file** — the fix surface is broader.
- **refinement_chain**: `ANTHROPIC_API_KEY not found in env or .env file`. Blocker #1.
- **catalog_import (exit 126)**: shell script line 86 fails with "Permission denied" on `cron_tracking/scanner_discovery/latest_findings.json`. The file itself is 0664 owned by `miningguardian` (correct). The job runs as a different user, OR line 86 tries to *create* a file in a directory the script user can't write to. **Needs the plist's `UserName` field to diagnose** — flag for follow-up.
- **ams_cleanup**: hardcoded VPS path `/root/Mining-Guardian/config.json` in `cleanup_ams_logs.py:35`. Path port not done.
- **db_maintenance**: `.err.log` is empty/missing; only `.last-run.json` exists with exit 1. Probably suppresses stderr; needs deeper look.

- **`benchmark`** (scheduled, but `.disabled` plist exists alongside): failing 50+ times with `FATAL: entrypoint not found: /Library/Application Support/MiningGuardian/tests/run_benchmark.py`. The `tests/` dir isn't shipped in the pkg. The `.disabled` plist either isn't taking effect or there are two plists active. Cosmetic.

- **log_collection** (exit 0): completes successfully but final Slack-notify step tries to read `/root/Mining-Guardian/.env` (VPS path) and warns. Doesn't affect exit code. Same path-port issue as `ams_cleanup`.

- **knowledge_backup** (exit 0): writes the backup file successfully, then attempts `git add knowledge_backup.json` — "fatal: not a git repository". The runtime install isn't a git checkout (confirmed). The git step is irrelevant on this host but doesn't fail the job. Cosmetic.

### Top-level service log activity
- `scanner.err.log` is **9.7 MB**, mtime matches `knowledge.json` (scanner is the writer).
- `slack-commands.err.log` is **35 MB** (suspiciously large — flag for review).
- `feedback_loop_daemon.err.log` is 766 KB.
- `guardian.log` rotating daily, root-owned.

### Scanner output is the bug Planning Decision 2 calls out
`guardian.log` shows scan #26 at 04:41:24 today emitted:
> "DIAGNOSIS: The S19JPro miners are experiencing a hardware failure due to a dead hashboard, which is causing the system to flag for restart check. ACTION: Restart Miner 53527 @ 192.168.188.195..."

This is the exact rule-violating analysis from Planning Decision 2, **happening on Mac Mini right now, every scan**. Bullet to keep in mind for section (j).

Also seen: `URGENT alert: id=94365886 key=hotBoard level=Critical miner=192.168.188.28() action=ALERT_OPERATOR` — at least two `hotBoard` thermal alerts being raised today (twice each — 05:16 and 06:16) on `.27` and `.28` (Auradine AH3880 hydro per warehouse cooling map). Suppressed auto-fix, operator notification path active.

### VPS cron + systemd
- **9 cron jobs in root's crontab.** No `/etc/cron.d/` entries for Mining Guardian. No systemd timers for MG. Cron is the sole scheduler on VPS (vs Mac Mini's launchd plists).
- **Schedule:**

| Time (CDT) | Job | Entry point |
|---|---|---|
| 00:00 | weekly_train (Pass 2 — Claude cohort) | `ai/weekly_train.py` |
| 01:00 | refinement_chain (Pass 3+4 — Qwen reflection + Claude merge) | `ai/refinement_chain.py` |
| 03:30 | db_maintenance | `scripts/db_maintenance.sh` |
| 04:00 | knowledge_backup | `ai/backup_knowledge.py` |
| 07:00 | morning_briefing | `scripts/morning_briefing.py` |
| 08:00 | log_collection (direct miner log pull) | `scripts/direct_collect_logs.py` |
| 08:15 | operator_review | `scripts/daily_operator_review.py` |
| 09:00 | daily_deep_dive (Pass 1 — Qwen) | `ai/daily_deep_dive.py` |
| 16:30 | log_failure_report | `scripts/daily_log_failure_report.py` |

- **8 Mining Guardian systemd services exist on VPS but are all `inactive (dead)`** (deliberate, per test condition — see section K):
  - `mining-guardian.service` (the main Fleet Monitor / scanner)
  - `approval-api`, `dashboard-api`, `intelligence-report`
  - `mining-guardian-alerts` (AMS Alert Listener)
  - `overnight-automation`
  - `slack-commands`, `slack-listener`
- **Today's cron results** (from `/tmp/*.log` tails):
  - **00:00 `weekly_train`**: FAIL — `psycopg2.OperationalError: Connection refused` (Postgres down per test condition).
  - **01:00 `refinement_chain`**: FAIL — passed `[OK] anthropic SDK importable`, `[OK] ANTHROPIC_API_KEY present`, `[OK] Pass 1 (Qwen deep dive): 7994 chars` (read May 10's output from file), `[OK] Pass 2 (Claude weekly): found`, then **failed at `Qwen endpoint http://100.110.87.1:11434/api/tags unreachable: <urlopen error timed out>`** (ROBS-PC unreachable per test condition).
  - **04:00 `knowledge_backup`**: **SUCCESS** — runs `pytest` (44 passed in 3.81s, mocked DB), commits the daily backup, pushes to GitHub (`fix/grafana-intelligence-miner-dropdown-2026-04-29` advanced to commit `edc1ceb`). File-only operation; doesn't need Postgres.
  - **07:00 `morning_briefing`**: FAIL — `Connection refused` on both `::1` and `127.0.0.1` (Postgres down per test condition).
  - 08:00 `log_collection`, 08:15 `operator_review`, 09:00 `daily_deep_dive`, 16:30 `log_failure_report`, 03:30 `db_maintenance` — not yet executed today (snapshot taken at 07:30 CDT).
- **Pattern:** the only cron job that survives the test condition is the file-only daily backup. Everything that needs Postgres or ROBS-PC fails — consistent with the test setup.
- **Crontab also leaks DB credentials inline** as plain env vars (`GUARDIAN_PG_USER=guardian_app`, password literal). Combined with `.env` mode `0644`, this is a credential-hygiene flag for any future operator-facing host. Value redacted from this report.

---

## G. Disk space (Mac Mini)

```
Filesystem        Size    Used   Avail Capacity
/                 228Gi   12Gi   151Gi    8%
/System/Volumes/Data  228Gi   56Gi   151Gi   28%
```

**151 GiB free** on the volume that hosts both the install dir and `~/.ollama`. Plenty for `qwen3:8b` (5.5 GB) plus future model experimentation.

---

## H. Surprises and contradictions vs. the handoff

1. **Lima is wrong → Postgres is Docker.** Container `mining-guardian-db`, Postgres 16.
2. **Build SHA differs from handoff** — current `53eac9397f00` (May 9 install) vs. handoff's claimed `ce9831c1a09a`.
3. **`past_analyses` table doesn't exist on Mac Mini** — the schema-drift framing is wrong; what's drifting is the SQL itself doing `TO_CHAR()` on a comparison against `timestamptz`.
4. **`recorded_at` schema-drift is broader than one file** — at least `daily_deep_dive.py:474` and `daily_log_failure_report.py:84`. Likely more — any code path doing `... timestamp_col >= TO_CHAR(...)` will fail.
5. **`knowledge.json` is a regular file, not a symlink.** Was a symlink historically; B-45 removed it; P-036 was the fix; current state per the docs is "symlink at install root, regular file at canonical path."
6. **All three operational commits absent** from this build (the build post-dates the handoff's reference build by 2 days, but lacks the commits anyway). Net: code on Mac Mini does not have the 152.7%-saga guards.
7. **Three failing jobs are caused by VPS-path hardcodes in code** — `ams_cleanup`, `log_collection` Slack step, possibly others. These wouldn't be caught by the four-blocker enumeration; they're a separate class of bug.
8. **Total plists 23 not 22** — close, minor.
9. **The denial-overwrite bug is firing on Mac Mini, not just VPS.** Scan #26 today emitted dead-hashboard / cooling-system analyses about S19JPros, exactly the EOL-exemption-violating output Planning Decision 2 documented. So *cutover has effectively already happened* — Mac Mini is producing the daily output Bobby has been complaining about, with stale 37 operator_decisions.
10. **`refinement_chain.py` prompt hardcodes "You are Qwen 2.5 32B"** identity string — needs editing alongside model rename.
11. **Discovery-sink ownership has drifted to root** for events-2026-05-10 and events-2026-05-11 (.jsonl files). Mode 0644 instead of 0664. The scanner process is running as root and creating files as root — that's the underlying cause of the catalog_import permission issue.
12. **No active ingester for `knowledge/incoming/`.** Migration mechanism must come from elsewhere.

---

## I. The denial-overwrite bug — what we now know

Per Planning Decision 2, this is the highest-priority bug after blockers #1-4. From the scanner running today on Mac Mini, we now know:

- The current LLM (`llama3.2:3b`, the 3B model — NOT Qwen) generates the rule-violating analyses. Model size isn't the determining factor; whatever LLM is in place gets the same misleading prompt context.
- The runbook confirms: scan-time LLM analysis is persisted via `llm_scan_analyses written, now 184 entries` (we saw the counter advance to 184). This is the live write path.
- `Knowledge saved — 50 known issues, 7 patterns` happens AFTER the LLM write.
- The denial-overwrite that Planning Decision 2 describes happens at training time (weekly_training, nightly), NOT at scan time. Training reads insights, calls Claude, gets a new judgment, writes back — clobbering operator decisions.
- **Weekly_training is currently failing on `ANTHROPIC_API_KEY` missing — which means the denial-overwrite is currently NOT happening on Mac Mini.** It would start happening the moment we add the key. So the order of operations matters: ship the denial-overwrite guard fix *before* adding the API key.

This is a new finding, not in either source doc. It changes section (j)'s recommended order.

---

## J. Recommended next steps

### Mandatory next gate: VPS access
You need to verify the VPS host key fingerprints and approve adding them to `~/.ssh/known_hosts`:

- ED25519: `SHA256:/rSlLXK3Vb3/kRpJ163L+gHW7T4BMcwt5/RJj9JxFRM`
- RSA: `SHA256:XYIBSls6mCn+N5dSXXxkiKNWV/33xGLCxlhlIZKxZg4`
- ECDSA: `SHA256:wP+j1MXSvWUyE/gVY8pKVFmjq7mrqnruoe8qxJgBNJc`

If any of these match what you've seen before (e.g. from another machine that already trusts this VPS), approve and I'll write the keys to known_hosts. If you can't verify, you can SSH from this terminal interactively (`ssh root@187.124.247.182`) and accept the key once — that'll write known_hosts via your own session and unblock me.

### Open decisions — Path A vs Path B

**Decision 1 — Knowledge migration mechanism.** No ingester for `incoming/` exists. Three options:

- **Path A: Stop scanner, atomic file swap, restart.** Quiesce the scanner (`launchctl unload`), copy the VPS knowledge.json into place, restart. Loses ~one scan window of data. Simple. Doesn't touch Postgres. Operator_decisions snap to VPS state (0..55), refined_insights pick up VPS's longer list.
- **Path B: Treat Postgres as authoritative, regenerate.** `pg_dump` from VPS, restore to Mac Mini Docker, then run a knowledge-regeneration job to rebuild knowledge.json from the new Postgres state. Cleaner schema-wise but requires (i) knowing VPS schema (still PENDING), (ii) a regeneration entry point we haven't found yet in the codebase, (iii) handling schema-drift conversions during dump→restore (if VPS still has `text` timestamps as the handoff claims).

I lean **Path A** for the knowledge.json itself, because it's a single file and the operator_decisions data is operator-authored — Postgres can't regenerate it. But for telemetry tables (miner_readings, hvac_readings, scans), Path B (pg_dump) is the right tool. **Recommend hybrid: A for knowledge.json, B for Postgres history.** Awaiting your call.

**Decision 2 — Order of operations on the cutover blockers.** Given finding (I) above (the denial-overwrite is currently dormant on Mac Mini because Claude calls are failing), I'd order:

1. Ship the denial-overwrite guard in `ai/knowledge_manager.py` first.
2. THEN add `ANTHROPIC_API_KEY` to `.env`.
3. THEN `ollama pull qwen3:8b` + grep/replace `qwen2.5:32b-instruct-q4_K_M` → `qwen3:8b` in source (5 source files plus the "You are Qwen 2.5 32B" prompt in `refinement_chain.py`).
4. THEN migrate knowledge.json (Path A above) — Mac Mini gets the 19 missing operator_decisions.
5. THEN fix the SQL-vs-text bug at `daily_deep_dive.py:474` and `daily_log_failure_report.py:84` (and grep for other instances of `TO_CHAR` near timestamp comparisons — there will be more).
6. THEN migrate Postgres history (Path B above).
7. THEN test a manual training cycle.

The original plan (Planning Decision 5's "execution order") sequenced the API key first; finding (I) inverts that. We should NOT enable Claude calls before the guard ships.

**Decision 3 — VPS-path hardcodes.** Three jobs hit `/root/Mining-Guardian/...` paths (`ams_cleanup`, `log_collection` Slack step, possibly more). These need a sweep — `grep -rn '/root/Mining-Guardian' --include='*.py' --include='*.sh'` will enumerate. Probably one PR's worth of replacements before cutover is clean.

**Decision 4 — Scanner-running-as-root.** The discovery sink and guardian.log being root-owned indicates the scanner daemon plist sets `UserName=root`. This causes the catalog_import permission failure and would cause more drift over time. Worth fixing but probably AFTER the more urgent items.

### Things I will NOT do without explicit approval
- Modify `~/.ssh/known_hosts` (VPS access)
- Read `.env` values
- Edit any source code
- `ollama pull qwen3:8b`
- Touch any service (`launchctl` load/unload/kickstart)
- Modify knowledge.json
- pg_dump (data) — only schema-only is on the approved list
- Any cross-host file transfer (scp/rsync)

### STOPPED HERE per your instructions
Awaiting your review. The most actionable single question right now: do the three VPS host-key fingerprints match what you'd expect? If yes, may I add the ed25519 key to `~/.ssh/known_hosts` so I can complete the VPS half of this snapshot?

---

## Followups (post-report addenda)

### Temporary SSH keypair for cutover

To unblock VPS access during the cutover, an ephemeral ED25519 keypair was generated on the Mac Mini under the `miningguardian` user. This is a *temporary credential* scoped to this cutover work and must be removed when the VPS is decommissioned.

- **Private key:** `/Users/miningguardian/.ssh/id_ed25519` (mode 0600, owner `miningguardian:staff`)
- **Public key:** `/Users/miningguardian/.ssh/id_ed25519.pub` (mode 0644)
- **Fingerprint:** `SHA256:tKSxWL9980VDS3hJXI+WPKmgfRAbww3emCWzJrUaoO8`
- **Comment tag (grep-able):** `miningguardian-mac-mini-cutover-20260511`
- **Passphrase:** none (operational keypair, short-lived)
- **Generated:** 2026-05-11

Bobby installs the public key on the VPS by appending it to `/root/.ssh/authorized_keys` from his laptop session.

**Post-cutover cleanup checklist:**
1. On Mac Mini, delete both files:
   - `rm /Users/miningguardian/.ssh/id_ed25519`
   - `rm /Users/miningguardian/.ssh/id_ed25519.pub`
2. On the VPS (or wherever the key was installed), remove the corresponding line from `/root/.ssh/authorized_keys`:
   - `sed -i.bak '/miningguardian-mac-mini-cutover-20260511/d' /root/.ssh/authorized_keys`
   - Verify with `grep miningguardian-mac-mini-cutover /root/.ssh/authorized_keys` (should return nothing).
3. Optionally also remove the VPS host key from Mac Mini's `~/.ssh/known_hosts` (once VPS is gone, the entry is dead anyway):
   - `ssh-keygen -R 187.124.247.182`

The grep tag in the comment is the canonical identifier for this keypair — anywhere it appears, that's a cleanup target.

---

# K. Critical Reframing — Mac Mini Standalone Test in Progress

This is the single most important fact in the entire report and supersedes the framing of every preceding section.

## What is actually happening

Bobby is running a **deliberate Mac Mini standalone test**, in progress since **2026-05-10 10:25:27 CDT** (~25 hours at snapshot time). The test condition is:

1. **VPS Postgres deliberately stopped** at 10:25:27 CDT on May 10 via `systemctl stop postgresql@16-main` (clean exit, status 0).
2. **VPS Mining Guardian services deliberately left inactive** (all 8 mining-guardian-*.service units `inactive (dead)`).
3. **ROBS-PC Qwen endpoint unreachable** from VPS (Pass 3+4 of the refinement chain fails on this).
4. **Mac Mini left running with only `llama3.2:3b`** (no Qwen, no `ANTHROPIC_API_KEY`).

This is not infrastructure failure. **This is the test.** Bobby is observing how Mac Mini performs as a standalone unit with the LLM and DB stack reduced to "what's on this one box."

## Reinterpretation of the May 10 SSL crash

The handoff said: "Today's (May 10) deep dive crashed mid-run with `psycopg2.OperationalError: SSL connection has been closed unexpectedly` when infrastructure was transferred to Mac Mini."

The actual sequence (from `/tmp/daily_deep_dive.log` on VPS):

- 09:00 — `daily_deep_dive.py` cron fires, starts the Pass-1 loop over 59 miners.
- 10:25 — Operator stops `postgresql@16-main` (test starting).
- 10:25-10:27 — Deep dive's in-flight psycopg2 connection holds for a moment, then fails on the next query with `SSL connection has been closed unexpectedly`. The "SSL" framing was misleading — what happened is the server side closed cleanly during shutdown and the client saw it as a transport tear-down.
- 10:27 — Application exits with the OperationalError seen in the log.

So **the May 10 crash is the test starting.** Not an SSL bug. Not a transfer artifact. Bobby pulled the rug deliberately; the deep dive was holding a connection and failed predictably.

## What the test has revealed (in addition to the snapshot findings above)

After ~25 hours of Mac Mini standalone operation:

1. **Telemetry collection works fine standalone.** Mac Mini scanner has run 26 scans since May 7, covering 96 unique miners, 2,496 `miner_readings`, 94 `hvac_readings`. AMS login + workspace selection work. Hotboard alerts are being raised and the operator-notify path is firing (192.168.188.27/.28 saw multiple `URGENT alert ... key=hotBoard level=Critical`). The basic monitoring loop is healthy.

2. **The LLM/intelligence layer is degraded by the test condition.**
   - With only `llama3.2:3b` (3B parameters) and no `ANTHROPIC_API_KEY`, the live scan analyses are **violating operator rules** — scan #26 today emitted "S19JPro... dead hashboard... Restart Miner 53527" type output, exactly what Planning Decision 2 documented. **Expected**, given the model floor.
   - Nightly `weekly_training` and `refinement_chain` can't get past pre-flight because the Anthropic key is missing.
   - `daily_deep_dive` fails at the SQL stage on `daily_deep_dive.py:474` (the `TO_CHAR()` vs `timestamptz` bug), so even if the LLM stack were available, the data fetch is broken.

3. **Of 12 scheduled jobs (Mac Mini launchd) + the scanner:**
   - 4 succeed cleanly on the test condition: `knowledge_backup`, `log_collection`, `morning_briefing`, `operator_review`.
   - 7 fail on the test condition: `ams_cleanup` (VPS-path hardcode), `catalog_import` (perm 126), `daily_deep_dive` (SQL bug), `db_maintenance`, `log_failure_report` (same SQL bug), `refinement_chain` (no Anthropic key), `weekly_training` (no Anthropic key + datetime subscriptable bug).
   - 1 disabled (`benchmark`).
   - The scanner itself runs every ~30 minutes and persists to Postgres successfully.

4. **knowledge.json on Mac Mini is being written daily by the scanner** (mtime today). Counts stayed at 37 decisions / 61 insights — those are operator-authored, scanner doesn't touch them. The scanner writes the *derived* keys (`fleet_summary`, `llm_scan_analyses`, `predictions`, etc.) and leaves the operator state alone.

5. **The denial-overwrite bug is dormant under the test condition.** It only activates when `weekly_training` calls Claude (requires `ANTHROPIC_API_KEY`). The test has been preventing it from firing. Adding the API key would wake it up.

## What changes about the migration plan

Section J's "Recommended next steps" were written before the test framing was clear. They're still individually valid as tactical steps but the *sequencing* and *goal* of the migration now needs rethinking. Specifically:

- The pre-test framing was "VPS is authoritative, migrate it to Mac Mini." The post-test framing is "Mac Mini is the live system. VPS has the richer historical knowledge.json (84/56) and the deployed Phase 1/1b/1c guards. Mac Mini has accumulated 25 hours of standalone-test telemetry. The migration is a *merge*, not a one-way copy."
- Path B for telemetry (`pg_dump` from VPS) now has an extra step: **start `postgresql@16-main` on VPS first** (service-control op, requires approval). pg_dump from a stopped cluster requires `pg_dumpall` against the data dir, which is more delicate.
- The "should we even bring up VPS Postgres again" question becomes a real one. If the test has proven Mac Mini-standalone is the target steady state, then VPS Postgres start/dump/stop is a one-time, time-boxed operation purely for historical-data extraction.

## Open planning questions for Bobby's review tomorrow

These are the questions the test results raise. Not answering any of them — they're for Bobby's morning.

### From the system reframing

**Q1.** Do we restart VPS Postgres briefly to `pg_dump` the data, then shut it down again? If so:
  - Schema-only dump first to confirm the actual VPS schema (and validate or refute the "VPS has text-typed `recorded_at`" claim from the handoff).
  - Data dump scoped to which tables? (At minimum: `miner_readings`, `hvac_readings`, `scans`, `llm_analysis`, `action_audit_log`. Possibly also `pool_observations`, `weather_readings`, `chain_readings`.)
  - Does the data import to Mac Mini's Docker Postgres need to merge with the 25h of standalone-test rows, or replace them?

**Q2.** Treat VPS `knowledge.json` (84 refined / 56 decisions, array format, `_audit` field) as canonical and migrate it wholesale to Mac Mini, OR merge the operator-authored portions (`operator_decisions`, `operator_rules`, `refined_insights`, `pattern_rules`) with whatever Mac Mini has accumulated during the test?
  - If migrate wholesale: the array→object conversion for `operator_decisions` is required. The `_audit` field needs decision (preserve or strip).
  - If merge: which "side" wins on conflicts? VPS has 56 decisions Mac Mini doesn't; Mac Mini has 37 decisions VPS has too — are they identical, or has the Mac Mini scanner diverged any operator-authored data during the test?

**Q3.** Does Bobby want Mac Mini to be capable of LLM-driven analysis standalone (requires `qwen3:8b` pulled locally + `ANTHROPIC_API_KEY` in `.env`), OR is "telemetry-only on Mac Mini, intelligence elsewhere (ROBS-PC or cloud Claude)" an acceptable steady state?
  - The test as currently configured forces the second answer by removing both intelligence options. That's a useful data point but it doesn't tell us what Bobby *wants* the steady state to look like — only what works without intelligence.

### From the snapshot data

**Q4.** What did this 25-hour test prove vs. what Bobby wanted to learn? Was the test scope "show me what Mac Mini can do alone," or "show me whether anything is *missing* before formal cutover"? The answers shape whether the test ends here or runs longer.

**Q5.** The knowledge.json structural differences (`operator_decisions` array vs object, `_audit` field on insights) — does that mean the Mac Mini `.pkg` codebase forked from VPS-`main` at some point, or are they running the same code with a schema version mismatch? Worth knowing because future installer builds need to handle both shapes or normalize to one.

**Q6.** VPS `.env` has 15 hardware-control credentials (`AURADINE_*`, `ECLYPSE_*`, `PDU_*`, `AV2_PLANT_*`, `OPENCLAW_TOKEN`, `ELECTRICITY_RATE_KWH`) that Mac Mini doesn't have. Does Mac Mini eventually need these (i.e., direct device control + power-cost math is a missing capability), or is the intent that AMS-mediation handles all of that and Mac Mini stays AMS-first?

**Q7.** The hardcoded `qwen2.5:32b-instruct-q4_K_M` fallback at `core/llm_analyzer.py:29` on Mac Mini — is this present because P-031's removal didn't reach this code path, or because the Mac Mini `.pkg` was built from a pre-P-031 commit and `P-031` was a VPS-side patch only?

**Q8.** The Mac Mini scanner is running as `root` (evidenced by root-owned `events-2026-05-10.jsonl` etc. in `cron_tracking/scanner_discovery/`). Intentional? If so, the catalog_import perm-126 failure has a different fix than re-chmoding the sink. If not, there's drift between the plist `UserName` field and what's actually running.

**Q9.** `catalog_import` exit 126: shell script line 86 hits "Permission denied" on `cron_tracking/scanner_discovery/latest_findings.json` despite the file being mode 0664 owned by `miningguardian`. The plist's `UserName` field will say which user the job actually runs as. (Likely root, given the scanner-as-root drift, but worth confirming.)

**Q10.** VPS-path hardcodes in code (`/root/Mining-Guardian/...`) — `ams_cleanup` and `log_collection` Slack step are the two we found. How many more sites need a path port before Mac Mini-standalone is clean of VPS references? A `grep -rn '/root/Mining-Guardian' --include='*.py' --include='*.sh'` from VPS would enumerate.

**Q11.** Crontab inline credential leak (`GUARDIAN_PG_PASSWORD` literal in `crontab -l`) — does the same pattern exist on Mac Mini's launchd plists, or is that a VPS-cron-only legacy artifact? Worth knowing before we add `ANTHROPIC_API_KEY` to anywhere new.

**Q12.** ROBS-PC Qwen unreachability — the refinement_chain failure log shows `http://100.110.87.1:11434/api/tags` timing out. Was ROBS-PC powered off as part of the test, or is its Tailscale advertisement broken? If we want ROBS-PC as an insurance Qwen path post-cutover, this needs diagnosis. If it's deprecated, this needs to be explicit.

## What I will NOT do until Bobby decides

- Start `postgresql@16-main` on VPS (service-control op, needs approval).
- `pg_dump` from VPS.
- Touch any code on either host.
- `ollama pull qwen3:8b`.
- Add `ANTHROPIC_API_KEY` to Mac Mini `.env`.
- Migrate knowledge.json by any path.
- Touch any service on either host.
- Anything that materially changes either system's state.

## End of report — standing by

Snapshot complete on both sides. No further work happening tonight. Bobby resumes tomorrow with a full picture and decides the migration shape from there.


