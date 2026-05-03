# Mining Guardian — Program State (canonical cold-start reference)

```yaml
audience: future agent (Computer) reading this after a 2-week absence
written: 2026-05-03
written_by: Computer (autonomous agent), per Operator (Rob) directive
last_main_sha_at_write: 81ac06e
released_version: v1.0.2
update_cadence: end of every working session, in the same PR as that day's HANDOFF_<DATE>.md
required_reading_at_session_start: this file + the most recent docs/handoffs/HANDOFF_<DATE>.md
```

> **Operator quote that defines this document's purpose:** "i want you to write a document that if we did not do any work for 2 weeks you could read it and know what we have done, what we are working on, whats right whats wrong and what we have to do, this is for you not me."

This file is for the agent, not for the operator. It is the single canonical snapshot of the entire Mining Guardian program. It is updated at the end of every working session in the same PR as the day's `docs/handoffs/HANDOFF_<DATE>.md` so a fresh agent reading it can resume work without loss of context.

---

## Section 1 — What is Mining Guardian

Mining Guardian is a Bitcoin mining operations monitoring and auto-remediation appliance, built for BiXBiT USA, Fort Worth TX, and shipped as a single Mac Mini that drops on the customer's miner LAN and runs everything locally. It scans a fleet of Bitcoin SHA-256 ASIC miners (Bitmain Antminer S19/S21, Whatsminer M-series, Auradine Teraflux AH3880, BiXBiT-firmware S19J Pro variants, and the rest of the 320-row catalog), polls BiXBiT AMS for miner state, writes time-series readings + restart history + audit trail to a local Postgres 16 instance, runs Grafana dashboards on `:3000`, runs a local Ollama LLM (`llama3.2:3b` on 16 GB Macs / `qwen2.5:14b-instruct-q4_K_M` on 24 GB+ Macs per D-13) for AI analysis of miner behaviour, and posts alerts and approval requests to the operator's Slack workspace via webhook + bot token. The deliverable to a customer is one Mac Mini, one notarized `.pkg` (for end-user laptops to view dashboards) plus the operator-run `setup.sh` (for the Mini itself per D-16 / B-3), a config file `MiningGuardian.conf`, a Tailscale tailnet for remote operator access only, and a printed install manual. **The product is Bitcoin SHA-256 miners only** — no altcoin scaffolding, ever, per Vision Anchor 6.

---

## Section 2 — Where the program is RIGHT NOW

| Field | Value |
|---|---|
| Today's date | 2026-05-03 (Sunday) |
| `origin/main` HEAD at write time | `81ac06e` — "docs: open HANDOFF_2026-05-03 for Mini cutover session (#113)" |
| Latest released version | **v1.0.2** (`pyproject.toml`) |
| v1.0.2 build SHA | `27fb2c10bbe0` |
| v1.0.2 .pkg | `MiningGuardian-1.0.2-27fb2c10bbe0.pkg` (437,022,332 bytes / 417 MB) — signed, notarized, stapled |
| GitHub Release v1.0.2 | https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.2 |
| SHA-256 sidecar | `MiningGuardian-1.0.2-27fb2c10bbe0.pkg.sha256` |
| Production scanner | Hostinger VPS — still LIVE, scanning miners every scan-interval, feeding Grafana every morning |
| Cutover state | Mac Mini empty / fresh, awaiting install |
| Today's blocker | The v1.0.2 .pkg audit is in progress. The audit answers whether double-clicking the .pkg on the Mini installs the full operations stack (D-16 step 4 reading) or only a viewer (INSTALL_PATHS_2026-05-02.md reading). Cutover is paused until the audit returns. |

---

## Section 3 — Host topology

Four hosts are in scope today. The agent must always disambiguate which one it is talking about before any destructive action.

### 3.1 Hostinger VPS — current production scanner

| Field | Value |
|---|---|
| Public IP | `187.124.247.182` |
| Tailscale IP | `100.106.123.83` |
| SSH | `ssh root@187.124.247.182` (or via Tailscale) |
| Repo path on host | `/root/Mining-Guardian/` (the historical mis-spelling of the path was renamed to the canonical form Sunday 2026-04-26 per PR #1; lint guard B-6 enforces the canonical spelling and is configured at `scripts/lint_mining_gaurdian_typo.sh`) |
| Hardware | Hostinger KVM 8 cloud instance (32 GB RAM, 8 vCPU per CLAUDE.md) |
| OS | Ubuntu Linux (Hostinger srv1549463) |
| Role today | LIVE production scanner. Runs `core/mining_guardian.py --loop`, polls AMS, writes to local Postgres 16, feeds Grafana every morning. |
| Role post-cutover | Decommissioned Monday 2026-05-04 (target) AFTER Mini is verified green per D-16 step 8. |
| Postgres | Postgres 16 on `:5432`, database `mining_guardian`, user `guardian_app`. Holds live fleet data — `miner_readings`, `miner_restarts`, `chain_readings`, `pool_readings`, `miner_hardware`, `action_audit_log`, `llm_analysis`, `scans`, `discovery_log`, `miner_baselines`. |
| systemd services | `mining-guardian.service` and the rest of the 8-service deploy/ unit set [TO VERIFY exact running set against deploy/ on this host post-cutover-decommission] |
| cron jobs | The 5 morning scheduled tasks historically lived here per HANDOFF_2026-05-02 / STATE_OF_THE_SYSTEM_2026-05-02. Authority on current cron content: live VPS `crontab -l`; do not modify until decommission. |
| `.env` | `/root/Mining-Guardian/.env` — chmod 600. Holds the live AMS credentials, Slack tokens, `MG_DB_PASSWORD`. **Do not touch on the live VPS** until Mini is verified green. |
| Do not touch | Do not stop services. Do not modify cron. Do not rotate the `.env` password (D-1 rotation is "pending apply" — do not re-rotate). Do not decommission until Mini-verified-green. |
| Health status | Healthy at last verification (2026-05-02 EOD per HANDOFF_2026-05-02.md). Re-verify on session resume. |

### 3.2 ROBS-PC — catalog masters per D-16

| Field | Value |
|---|---|
| Local IP | `192.168.188.47` |
| Tailscale IP | `100.110.87.1` |
| Hardware | Bobby's Windows PC, RTX 4090 GPU |
| OS | Windows 11 |
| Role today | Containers DOWN where Rob left them on 2026-05-02 morning. Volume intact. |
| Role post-cutover | Per D-16: catalog masters retained as backup + future-customer DB cloning source. Per D-7: Ollama no longer hosted here (moves to Mini). Per D-14 sub-lock 5: HTTP `catalog-api` is retired. Mac Mini runtime does not pull anything from ROBS-PC. |
| Postgres | Catalog `mining_guardian` Postgres in Docker container `mining-guardian-db` on `:5432` (inside container). Schemas: `hardware.*`, `firmware.*`, `ops.*`, `market.*`, `repair.*`, `pool.*`, `facility.*`, `regulatory.*`, `knowledge.*`, `staging.*`, `seed.*`. |
| Catalog volume content | 2026-04-27 import = 355,626 rows behavioural data. The Bitaxe import (PR #102, 2026-04-26) brought `hardware.miner_models` to 320 rows. |
| catalog-api | Historically `catalog-api` ran on `:8420` for HTTP access. Retired post-cutover per D-14 sub-lock 5. |
| Ollama | Historically Qwen on the 4090. Per D-7, Ollama moves to the Mini for the customer install. After cutover the 4090 stops serving the operational loop. |
| Do not touch | NEVER `docker volume rm` on this host without explicit operator instruction — the volume is the catalog master per D-16. Containers stay DOWN until Mini is verified green and operator says go. |
| Decommission step | Monday 2026-05-04 morning AFTER Mini is verified green: shut down the `mining-guardian-db` container only. The volume and the Windows host stay — ROBS-PC remains a dev workstation and master-archive box. |
| Health status | Container DOWN per HANDOFF_2026-05-03.md "Do not touch" section. Volume intact, last verified 2026-05-02 morning. |

### 3.3 Mac Mini — cutover target (the product)

| Field | Value |
|---|---|
| Location | Fort Worth customer site, on the miner LAN `192.168.188.0/24` |
| Tailscale IP | `100.69.66.32` |
| mDNS hostname | `miningguardian.local` |
| SSH | `ssh mg@miningguardian.local` (or `ssh mg@100.69.66.32` if mDNS fails) |
| Hardware | Mac Mini, Apple Silicon (M-series) [TO VERIFY exact M-chip and RAM tier — HANDOFF history references 16 GB envelope but the Mini delivered to Rob's site has not been confirmed in the repo as 16 vs 24 GB. The installer auto-detects per D-13 / `installer/macos-pkg/scripts/lib/detect_ram.sh`.] |
| OS | macOS Tahoe (`26.4.1` per HANDOFF_2026-05-02; auto-updated overnight 2026-05-01 per B-6) |
| Role today | Empty / fresh. Repo not yet cloned to `~/code/Mining-Guardian`. Tailscale up. mDNS reachable. Auto-login + caffeinate + screen-share preserved. |
| Role post-cutover | Live operations host. Postgres 16 (single instance, both `mining_guardian` operational tables and the catalog schemas per D-14 sub-lock 1), Grafana on `:3000`, Ollama (model selected by RAM at install time per D-13), Tailscale (remote ops only — no data plane traffic per D-9), 9 launchd services, 11 cron entries (per `scripts/setup.sh` Phase 10). |
| Install path | Per D-16 step 4: ".pkg double-click on the customer-site Mini." Per `docs/INSTALL_PATHS_2026-05-02.md`: "do NOT click the .pkg on the Mini; use `setup.sh`." This contradiction is the live blocker today and is documented in Section 10 below. The cutover is paused until the v1.0.2 .pkg audit returns. |
| Config file | `~/MiningGuardian.conf` (chmod 600) — copied from `installer/macos-pkg/resources/MiningGuardian.conf.template` and filled with site values (AMS credentials, Slack tokens, customer name). |
| Install root | `/Library/Application Support/MiningGuardian` (the B-13 fix — Tahoe SSV rejects writes to `/usr/local/MiningGuardian/`). |
| Do not touch | Do not paste `~/MiningGuardian.conf` contents into chat. Do not commit `.env`. Do not screenshot the config file. Do not retry install without operator approval if the first attempt fails. If pre-flight detects "macOS major version updated within last 48h" (B-6), stop and confirm with operator. |
| Health status | Empty / fresh per HANDOFF_2026-05-02 EOD section. |

### 3.4 Operator's laptop (Rob's MacBook) — dev workstation + .pkg build host

| Field | Value |
|---|---|
| Hostname | Rob's MacBook (specific hostname not committed) |
| Repo path on host | `~/Documents/GitHub/Mining-Guardian` |
| Hardware | MacBook (Apple Silicon, model not committed) [TO VERIFY exact MacBook model; the build script `installer/macos-pkg/scripts/build_pkg.sh` requires `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` so the user account is `BigBobby`] |
| OS | macOS [TO VERIFY exact version] |
| Role | Development workstation. Apple Developer cert + notarization keychain live here. The v1.0.2 .pkg is built here. |
| Build credentials path | `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` — read by `build_pkg.sh` step 1. NOT in repo. |
| Build outputs | `build/MiningGuardian-<version>-<sha>.pkg`, `.pkg.sha256`, `.notarization-log.txt` — NOT in repo. |
| Do not touch | Never copy the contents of `CREDENTIALS_NOTES.txt` into chat. Never commit it. The Apple `.p8` private key is referenced inside that file by path; never read or print the .p8 contents. |
| Health status | v1.0.2 .pkg built, signed, notarized, stapled successfully on 2026-05-02 evening per HANDOFF_2026-05-02 EOD ("single Apple notary cycle, 9m9s, cleanest build yet"). |

---

## Section 4 — Data inventory

Every dataset, every database, every file artifact. Where each one lives, what writes it, what reads it.

### 4.1 Live operational Postgres on the VPS (today's source of truth for fleet readings)

- Host: Hostinger VPS, `:5432`
- Database: `mining_guardian`
- User: `guardian_app`
- Schemas: `public.*` (operational) — `miner_readings`, `miner_restarts`, `chain_readings`, `pool_readings`, `miner_hardware`, `action_audit_log`, `llm_analysis`, `scans`, `discovery_log`, `miner_baselines`, etc.
- Writes: `core/mining_guardian.py` on every scan loop iteration. cron-driven `ai/daily_deep_dive.py` (4 PM Qwen run). cron-driven `ai/weekly_train.py` (Sunday Claude training). The 5 morning scheduled tasks for catalog enrichment do NOT write here — they write to JSON/CSV files in `cron_tracking/`.
- Reads: Grafana via the postgres datasource provisioned at `/opt/homebrew/var/lib/grafana/provisioning/datasources/postgres.yml` (or the Linux equivalent on the VPS). Slack approval API. Dashboard API. AI deep dive.
- Size: [TO VERIFY current row counts; last verified row count was at 2026-05-02 morning and was not in chat]
- Decommission: stops being source of truth Monday 2026-05-04 morning when Mini is verified green.

### 4.2 Catalog Postgres on ROBS-PC (per D-16 retains masters post-cutover)

- Host: ROBS-PC, Docker container `mining-guardian-db`, `:5432` inside container
- Database: `mining_guardian`
- User: `mg_catalog` (per the verify step in HANDOFF_TEMPLATE.md worked example)
- Schemas: catalog reference — `hardware.*`, `firmware.*`, `ops.*`, `market.*`, `repair.*`, `pool.*`, `facility.*`, `regulatory.*`, `knowledge.*`, `staging.*`, `seed.*`. (See `docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` Section 2 for the full per-table breakdown.)
- Anchor table: `hardware.miner_models` — 320 rows (Bitaxe import PR #102, 2026-04-26). Verified count at session start: `grep -c '^INSERT INTO' intelligence-catalog/seed-data/seed_miner_models.sql` returns 321 (320 model INSERTs + 1 boilerplate, matches CSV body of 320 rows).
- Behavioural data: 2026-04-27 import = 355,626 rows. NOT seed data — actual mining-fleet behavioural rows imported via `catalog_updater.py --add-from-csv` and historical loaders.
- Status today: container DOWN per HANDOFF_2026-05-03.md "Do not touch". Volume intact.
- Post-cutover: per D-16, master-archive only. Per D-17, the recurring monthly sync from this host to the Mini Postgres is deferred until after Mini-verified-green (post-cutover work item, not a cutover gate).

### 4.3 Catalog Postgres on Mac Mini (post-cutover live catalog)

- Will exist after `setup.sh` Phase 4 completes per `phase_04_postgres()` in `scripts/setup.sh`.
- Single Postgres 16 instance per D-14 sub-lock 1: both `mining_guardian` (operational) and the catalog schemas live in the same instance.
- Per D-14 sub-locks 2-4: scanner consults the catalog on every miner evaluation, C5 feedback loop (`intelligence-catalog/db/feedback_loop.py` PR #22) flows operational outcomes back via `NOTIFY catalog_feedback`, catalog read failure logs at ERROR (no silent return).
- Per D-14 sub-lock 5: AI consumers reach the catalog via psycopg-direct, not via the HTTP `catalog-api` round-trip.

### 4.4 The 320-row Bitcoin SHA-256 miner catalog seed

- Canonical SQL: `intelligence-catalog/seed-data/seed_miner_models.sql` (3,882 lines; 320 model INSERTs into `hardware.miner_models`).
- CSV source of truth: `intelligence-catalog/seed-data/all_bitcoin_sha256_miners.csv` (321 lines = 1 header + 320 data rows).
- Schema deploy script: `intelligence-catalog/seed-data/deploy_schema.sql` (uses `\ir` to include the three layered schema files).
- Generator: `intelligence-catalog/seed-data/compile_all_miners.py` (regenerates the SQL from the CSV).
- The number 320 is **not** static — per B-9 / `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md`, every doc that cites a count must frame it as "current at vX.Y.Z; source of truth is `seed_miner_models.sql`" and the Grafana Intelligence Report dropdown must read `SELECT count(*) FROM hardware.miner_models` live, not a hardcoded label.

### 4.5 The 5 Perplexity scheduled tasks — JSON/CSV file artifacts in `cron_tracking/`

These run on the agent's host (NOT on the VPS or ROBS-PC) per HANDOFF_2026-05-02 + STATE_OF_THE_SYSTEM_2026-05-02. Every one of them writes files on disk, NOT directly to any Postgres database.

| Task | Cadence | Output path |
|---|---|---|
| Aggregator Watcher | daily | `cron_tracking/aggregator_watcher/latest_findings.json` |
| Manufacturer Model Watcher | daily | `cron_tracking/manufacturer_watcher/latest_findings.json` |
| Firmware Tracker | daily | `cron_tracking/firmware_tracker/latest_findings.json` |
| Community Intel Scanner | daily | `cron_tracking/community_intel/latest_findings.json` |
| Deep Enrichment Sweep | every 2 days (tier-rotated) | `cron_tracking/enrichment_sweep/<DATE>_results.csv` + updates to `intelligence-catalog/data/unified_miner_index.json` |

The catalog Postgres receives data from these files only when someone manually runs `catalog_updater.py --add-from-csv` (see STATE_OF_THE_SYSTEM_2026-05-02.md). This is the actual catalog gap — the API surface does not merge `unified_miner_index.json` (288 slugs, 225 with rich enrichment) or `miner_enrichment_master.csv` (277 rows, 16 enrichment columns) into responses, even though those files sit next to the Postgres rows.

### 4.6 Customer-facing artifacts

- `docs/customer/MiningGuardian_Setup_Manual.pdf` — binary, source-controlled separately. Documents the .pkg flow per INSTALL_PATHS_2026-05-02.md.
- Customer brochure — [TO VERIFY — referenced in D-11 cutover gate criterion 8 and the operator's customer-#1 framing, but the brochure file is not directly enumerated in the docs read so far]
- Install PDF — in progress. Will be assembled Monday 2026-05-04 from the screenshots captured during the cutover install per HANDOFF_2026-05-03 Phase 6 and the v1.0.2 release notes. Phase 5 of the install plan calls for screenshots at every Phase 4 + Phase 5 boundary.
- `customer_docs/screenshots/bug_reports/B-13_pkg_incompatible_tahoe_RAW.jpg` — forensic capture of the v1.0.0 SSV rejection, retained as B-13 evidence.

---

## Section 5 — Software inventory

| Component | Version pin | Where it runs | Install location | Notes |
|---|---|---|---|---|
| Mining Guardian Python codebase | v1.0.2 (`pyproject.toml`) | Mini (post-cutover); VPS (today) | `/Library/Application Support/MiningGuardian` (Mini) / `/root/Mining-Guardian/` (VPS) | Python 3.12, venv at `${MG_INSTALL_ROOT}/venv`. Entry: `core/mining_guardian.py --loop`. |
| Postgres | 16 (`postgres:16-bookworm` image when Mini-Colima path; `postgresql@16` Homebrew when setup.sh path) | Mini, ROBS-PC (DOWN), VPS | `:5432` on `127.0.0.1` only per S-13 | Catalog + operational schemas on the Mini per D-14 sub-lock 1. |
| Grafana | Homebrew `grafana` (latest) [TO VERIFY exact pin in setup.sh phase_11_grafana] | Mini (post-cutover) | `:3000` on `127.0.0.1` (or LAN) | Datasource provisioned at `provisioning/datasources/postgres.yml`; full provisioning + dashboards is Bucket 6d (deferred). |
| Ollama | latest from `ollama.com` first-run pull | Mini (per D-7) | `/Applications/Ollama.app` + symlink at `/usr/local/bin/ollama` | RAM-tier model selection per D-13. The first-run model pull is the ONE network call the .pkg makes per Vision Anchor 7. |
| Ollama model — 16 GB RAM | `llama3.2:3b` (q4 default, ~2 GB pull) | Mini | Ollama models dir | Per D-13. Welcome screen in `welcome.html` documents this. |
| Ollama model — 24 GB+ RAM | `qwen2.5:14b-instruct-q4_K_M` (~8-9 GB pull) | Mini | Ollama models dir | Per D-13. Was D-8's universal default before D-13 superseded it. |
| Tailscale | latest `tailscale` Homebrew or installer | Mini (optional via `--tailscale` flag) | system | Per D-9: remote operator access only, not data plane. |
| Colima + Lima 2.x (vz-only) | vendored in `~/MiningGuardian-vendor/` at build time | Mini (.pkg path only) | `/usr/local/bin/{colima,limactl,docker,lima}` + `/usr/local/libexec/lima` | Apple Silicon `--vm-type vz`. Linux guest agent removed at codesign time per build_pkg step 4b. |
| Docker CLI | vendored | Mini (.pkg path only) | `/usr/local/bin/docker` | Client only; daemon runs inside Colima VM. |
| Apple Developer Team ID | `ARJZ5FYU94` | Build host | n/a | Public, also in repo per `installer/macos-pkg/README.md`. |
| Apple Notarization Key ID | `FPZJ87B3QF` | Build host | n/a | Public, also in repo. The Issuer UUID + `.p8` private key path are PRIVATE and live only in `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`. |
| Developer ID Installer cert | `Developer ID Installer: Robert Fiesler (ARJZ5FYU94)` | Build host keychain | n/a | Signs the outer `.pkg` via `productsign`. |
| Developer ID Application cert | `Developer ID Application: Robert Fiesler (ARJZ5FYU94)` | Build host keychain | n/a | Signs every Mach-O binary inside the payload via `codesign`. |

### The 9 launchd services on the Mini (post-cutover)

Per `installer/macos-pkg/scripts/postinstall.sh` `PLIST_LABELS` array (8 plists from `installer/macos-pkg/resources/launchd/` + 1 from `deploy/`):

1. `com.miningguardian.scanner` — main scan loop (`core/mining_guardian.py`)
2. `com.miningguardian.dashboard-api` — dashboard backend
3. `com.miningguardian.approval-api` — approval queue + Slack approval
4. `com.miningguardian.slack-listener` — listens to Slack interactivity
5. `com.miningguardian.slack-commands` — handles Slack slash-commands
6. `com.miningguardian.overnight-automation` — overnight reset / cleanup
7. `com.miningguardian.alerts` — alert dispatcher
8. `com.miningguardian.intelligence-report` — intelligence report API
9. `com.miningguardian.feedback-loop-daemon` — D-14 NOTIFY/LISTEN daemon, ships from `deploy/feedback_loop_daemon_launcher.sh` per Bucket 7.5 fix

Each service has a launcher wrapper at `/Library/Application Support/MiningGuardian/bin/<name>_launcher.sh` that sources `.env` (since launchd has no `EnvironmentFile=` equivalent) and execs the Python entry point under the venv.

### The 11 cron entries on the Mini (post-cutover, from `scripts/setup.sh` Phase 10)

| Schedule | Command (relative to `${MG_INSTALL_ROOT}`) |
|---|---|
| `0 0 * * *` | `ai/weekly_train.py` (Claude weekly training) |
| `0 1 * * *` | `ai/refinement_chain.py` (refinement loop) |
| `30 3 * * *` | `scripts/db_maintenance.sh` |
| `0 4 * * *` | `ai/backup_knowledge.py` |
| `0 7 * * *` | `scripts/morning_briefing.py` |
| `0 8 * * *` | `scripts/daily_operator_review.py` |
| `45 12 * * *` | `scripts/cleanup_ams_logs.py` |
| `0 13 * * *` | `scripts/direct_collect_logs.py` |
| `0 16 * * *` | `ai/daily_deep_dive.py` (Qwen 4 PM run) |
| `15 16 * * *` | `scripts/daily_log_failure_report.py` |
| `0 * * * *` | `tests/run_benchmark.py` |

macOS 14+ requires the operator to grant Full Disk Access to `/usr/sbin/cron` for the jobs to write `/tmp` + `/var/log` — `phase_10_cron` in setup.sh prompts for this manually.

---

## Section 6 — Configuration registry

Every config value the program uses. Names + validation rules. **No actual secret values appear in this document.** The canonical config-file template ships at `installer/macos-pkg/resources/MiningGuardian.conf.template` per B-2 / PR #108.

### Required keys (install aborts if any are empty)

| Key | Validation rule (per `mg_validate_site_config` in scripts/setup.sh) | Source of truth at runtime |
|---|---|---|
| `CUSTOMER_NAME` | non-empty | `${MG_INSTALL_ROOT}/.env` |
| `AMS_URL` | starts with `http://` or `https://` (default `https://api.bixbit.io/api/v1`) | `${MG_INSTALL_ROOT}/.env` |
| `AMS_EMAIL` | contains `@` | `${MG_INSTALL_ROOT}/.env` |
| `AMS_PASSWORD` | non-empty (chmod 600 .env) | `${MG_INSTALL_ROOT}/.env` |
| `AMS_WORKSPACE_ID` | integer | `${MG_INSTALL_ROOT}/.env` |
| `SLACK_WEBHOOK_URL` | starts with `https://hooks.slack.com/` (validation rule per B-2 / PR #108) | `${MG_INSTALL_ROOT}/.env` |
| `SLACK_BOT_TOKEN` | starts with `xoxb-` | `${MG_INSTALL_ROOT}/.env` |
| `SLACK_SIGNING_SECRET` | non-empty | `${MG_INSTALL_ROOT}/.env` |
| `AUTHORIZED_SLACK_USER_IDS` | comma-separated Slack user IDs | `${MG_INSTALL_ROOT}/.env` |

### Optional keys

| Key | Validation rule | Default |
|---|---|---|
| `SLACK_APP_TOKEN` | if set, starts with `xapp-` | empty |
| `SCAN_INTERVAL` | integer seconds | `300` (5 min) |
| `MG_DRY_RUN` | boolean (string `true` or `false`) | `true` (D-2 — auto_approve_enabled defaults to False; explicit opt-in required) |

### Generated by the installer (NOT in the conf template)

| Key | Source | Notes |
|---|---|---|
| `MG_DB_PASSWORD` | `openssl rand -hex 32` per install | Per D-1 the canonical literal is documented in DECISIONS.md but each install regenerates fresh. NEVER committed. |
| `CATALOG_API_KEY` | `openssl rand -hex 32` per install | Closes S-6. |
| `INTERNAL_API_SECRET` | `openssl rand -hex 32` per install | `approval_api.py` `verify_internal()` fail-closed check. |
| `GUARDIAN_PG_HOST` | `127.0.0.1` | per S-13: no Tailscale IPs anywhere |
| `GUARDIAN_PG_PORT` | `5432` | |
| `GUARDIAN_PG_USER` | `guardian_app` | |
| `GUARDIAN_PG_DBNAME` | `mining_guardian` | |
| `GUARDIAN_PG_TEST_DBNAME` | `mining_guardian_test` | |
| `GUARDIAN_PG_CATALOG_DBNAME` | `mining_guardian_catalog` (when `setup.sh` Phase 4 path is used) | Per `phase_04_postgres()` setup.sh creates 3 DBs: `mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`. The D-14 single-Postgres-instance "two logical halves" design uses `mining_guardian` for both the operational tables and the catalog schemas; the `mining_guardian_catalog` separate-DB phrasing in setup.sh predates the D-14 lock and is reconciled in the live install behaviour. [TO VERIFY which logical layout the post-cutover Mini actually uses on first install.] |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | per D-9 / S-13 |
| `MG_INSTALL_RAM_TIER` | `sysctl -n hw.memsize` parsed in `installer/macos-pkg/scripts/lib/detect_ram.sh` | per D-13 |
| `MG_INSTALL_LLM_MODEL` | derived from RAM tier | per D-13 |
| `AUTO_APPROVE_ENABLED` | `false` | per D-2 |
| `GUARDIAN_DASHBOARD_PORT` | `8585` | per S-13 |
| `GUARDIAN_APPROVAL_PORT` | `8686` | per S-13 |
| `GUARDIAN_INTELLIGENCE_PORT` | `8590` | per S-13 |

### Live source-of-truth values at runtime

- VPS today: `/root/Mining-Guardian/.env` (chmod 600, root:wheel) — holds the live AMS + Slack values.
- Mini post-install: `/Library/Application Support/MiningGuardian/.env` (chmod 600, root:wheel) — written by `phase_07_secrets()` in setup.sh, sourced by every launchd launcher wrapper at startup. Build-side .pkg postinstall also writes a `.env` (per `step_drop_dotenv` in `installer/macos-pkg/scripts/postinstall.sh`) but only with `MG_DB_PASSWORD` + Postgres connection vars — site-config (AMS, Slack) does NOT come from the .pkg postinstall. This is the heart of the D-16 vs INSTALL_PATHS contradiction documented in Section 10.

### Tailscale auth handling

Per D-9 + setup.sh `phase_12_tailscale()`: `tailscale up --accept-routes` is opt-in via the `--tailscale` flag. The tailnet ([TO VERIFY tailnet name]) is for remote operator access only; no Mining Guardian service binds to a Tailscale IP per S-13. The auth key is supplied interactively via the Tailscale browser-open auth flow when needed — no pre-shared key in repo.

---

## Section 7 — Decisions ledger summary (D-1 through D-17)

Plain-language one-liners for every locked decision in `docs/DECISIONS.md`. Read the file for full rationale.

- **D-1 — `MG_DB_PASSWORD` rotation.** New 192-bit Postgres password to replace the leaked `MiningGuardian2026!` (29+ source locations). **Status:** locked 2026-04-24, "pending apply" on the live VPS as of HANDOFF_2026-05-03. **Touches:** secrets, security.
- **D-2 — `auto_approve_enabled` default.** Defaults to False; customers must explicitly opt in to automated remediation. **Status:** locked 2026-04-24. **Touches:** safety, customer onboarding.
- **D-3 — `outcome_checker.py` rewrite via psycopg.** Clean psycopg replacement for the SQLite-era module. **Status:** ✅ Done in PR #4 (`bcfbd58`). **Touches:** codebase, Postgres migration.
- **D-4 — `mg_import` session TTL.** 28800 seconds (8 hours). **Status:** locked 2026-04-24, "pending apply" during CRIT-3 / Monday 2026-04-27. **Touches:** import tool security.
- **D-5 — `mg_import` HTML password input + handoff doc.** 5a empty input value, 5b archive forensic doc with rotation note, 5c grep-at-apply-time. **Status:** locked, pending CRIT-1. **Touches:** import tool UX, archived doc.
- **D-6 — `migrate_to_postgres.py` import guard.** Raises on import unless `MG_ALLOW_MIGRATION=1`. **Status:** locked 2026-04-24, verify-in-current-code pending. **Touches:** safety.
- **D-7 — Ollama hosting.** Ollama runs exclusively on the Mac Mini, not on ROBS-PC. **Status:** locked 2026-04-26. **Touches:** Mini install scope, ROBS-PC role.
- **D-8 — Ollama model on Mac Mini.** `qwen2.5:14b-instruct-q4_K_M`. **Status:** SUPERSEDED by D-13. Kept in DECISIONS.md for historical record. **Touches:** Ollama.
- **D-9 — Mac Mini network and remote access.** Mini sits on miner LAN `192.168.188.0/24`. Tailscale is for remote ops only. `OLLAMA_URL=http://localhost:11434/api/generate`, `CATALOG_DB_HOST=localhost`. **Status:** locked 2026-04-26, encoded in installer Phase 12. **Touches:** networking, security.
- **D-10 — Mac Mini install date.** Install moves to Monday 2026-05-05 (later compressed to Sunday 2026-05-03 per HANDOFF_2026-05-03 / D-16 step 4). **Status:** locked 2026-04-26 with the operator quote "I would rather be late and perfect than early and wrong." **Touches:** schedule.
- **D-11 — Cutover gate (customer-grade exit criteria).** 8 criteria all green before install: secrets, passwords, dead code, schema, AI data, installer, daily paper trail, customer-facing docs. **Status:** locked 2026-04-26. **Touches:** cutover scope.
- **D-12 — Documentation cadence.** Every working day gets a `SESSION_LOG_<DATE>.md` (now `HANDOFF_<DATE>.md` post-D-15). Decisions land in DECISIONS.md. **Status:** active. **Touches:** process.
- **D-13 — Ollama model selection: install-time RAM auto-detect (supersedes D-8).** 16 GB → `llama3.2:3b`; 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`. Customer can override at install. **Status:** locked 2026-04-28, encoded in `mg/pr26-mac-mini-installer` Phase 8 + `installer/macos-pkg/scripts/lib/detect_ram.sh`. **Touches:** Ollama, installer.
- **D-14 — Operational ↔ Catalog: live-reference architecture, no scheduled refresh.** Five sub-locks: same Postgres instance for both DBs on Mini; scanner consults catalog every miner; operational outcomes flow back via NOTIFY/LISTEN within ~100 ms; catalog read failure logs at ERROR (no silent return); HTTP catalog-api retired post-cutover (psycopg-direct). **Status:** locked 2026-04-28, no implementation yet. **Touches:** architecture, AI loop, post-cutover.
- **D-15 — Handoff protocol.** Every session ends with `HANDOFF_<DATE>.md`. Every session starts by reading the latest. Failure to read prior handoff is a protocol violation operator can use to halt the session. **Status:** locked 2026-05-02 (`fa6adbc`). **Touches:** process, this entire document's existence.
- **D-16 — Post-cutover masters on ROBS-PC; Mini fully self-contained at runtime.** ROBS-PC retains catalog masters as backup + future-customer DB cloning source post-cutover. Mini does not pull anything at runtime per cutover scope γ. After Mini-verified-green, ROBS-PC Docker container shuts down, VPS decommissions. **Status:** locked 2026-05-02. **Touches:** all three hosts, post-cutover sequencing. **Reconciles with D-14 and cutover scope γ.**
- **D-17 — Monthly catalog sync deferred until post-cutover.** Mini ships with the 320-row baseline seed. The recurring ROBS-PC → Mini monthly sync over Tailscale runs only AFTER Mini is verified green — not a cutover gate. **Status:** locked 2026-05-02. **Touches:** catalog sync, post-cutover scheduling. **Reconciles with D-16.**

### Reconciliation notes (decisions that interact)

- **D-8 vs D-13:** D-13 supersedes D-8. D-8 stays for historical record. Live policy is D-13.
- **D-14 vs D-16:** D-14 sub-lock 1 says both DBs run in the same Postgres 16 container on the Mini. D-16 only addresses the previous hosts (ROBS-PC keeps offline master, then container shuts down; VPS decommissioned). Both are consistent; D-16 is cutover scope γ in execution detail.
- **D-16 vs INSTALL_PATHS_2026-05-02.md (the live contradiction).** D-16 step 4 says ".pkg double-click on the customer-site Mini." INSTALL_PATHS_2026-05-02.md says "do NOT click the .pkg on the Mini; .pkg is viewer-only." Both merged 2026-05-02 in different PRs without cross-checking. This is the live blocker today (Section 10). Resolution pending the v1.0.2 .pkg audit + a forthcoming D-? decision.
- **D-16 vs D-17:** D-16 says ROBS-PC retains catalog masters and is the source from which future-customer DBs are cloned. D-17 only sequences the recurring sync (post-cutover, not a cutover gate).

---

## Section 8 — Backlog ledger (B-1 through B-13)

Per `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` + RELEASE_NOTES_v1.0.1 + RELEASE_NOTES_v1.0.2.

| ID | Plain-language summary | Status | Closing PR | Decision link |
|---|---|---|---|---|
| **B-1** | APFS-naive disk pre-flight false-negative (rejected at 36 GB free when 195 GB actually free). | ✅ closed in v1.0.2 | PR #106 | — |
| **B-2** | Phase 2 customer-info raw `read` prompts unusable (one typo restarts from field 1). Replaced with config-file approach. | ✅ closed in v1.0.2 | PR #108 | — |
| **B-3** | `.pkg` vs `setup.sh` install-path confusion. Adopted recommendation (a): Mini = setup.sh, end-user = .pkg viewer-only. | ✅ closed in v1.0.2 | PR #109 | D-15, D-16 family |
| **B-4** | Xcode CLT manual install required mid-install (Apple GUI popup). | 🔵 N/A on customer .pkg path per D-16. Doc-only follow-up for operator path. | — | D-16 |
| **B-5** | GitHub auth wall (private repo `git clone` prompted for username + password). | 🔵 N/A — repo is public, .pkg bundles everything for customers. Doc-only follow-up. | — | — |
| **B-6** | Tahoe auto-update mid-install drag (Mini auto-updated 26.3 → 26.4.1, force-reboot broke SSH). | 🔴 OPEN — not a v1.0.2 blocker. Documented operator pre-flight: detect "macOS major version updated within last 48h" and stop-confirm. | — | — |
| **B-7** | `--dry-run-install` did not skip Phase 2 prompts. | ✅ closed in v1.0.2 | PR #108 | — |
| **B-8** | `setup.sh` required sudo even for `--dry-run-install`. | ✅ closed in v1.0.2 | PR #108 | — |
| **B-9** | Catalog count drift (313 vs 320 across docs; Bitaxe import was 320). Fixed all docs + locked the Grafana SQL-driven dropdown rule. | ✅ closed in v1.0.2 | PR #107 | `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md` |
| **B-10** | Runbook said `bash setup.sh` but the script is `#!/bin/zsh`. Bash invocation hard-fails Phase 2 with `bash: -s: invalid option`. | ✅ closed in v1.0.2 | PR #106 | — |
| **B-11** | `.pkg` Welcome copy promised RAM-tier model selection but `setup.sh` force-pulled `qwen2.5:14b` regardless of RAM. Two paths disagreed. | ✅ closed in v1.0.1 | — | D-13 |
| **B-12** | `.pkg` Welcome + Conclusion screens render broken in dark mode on Tahoe Installer.app WebKit. Brand sidebar dark-gray, code chips black rectangles. | ✅ closed in v1.0.1 | — | — |
| **B-13** | 🚨 `.pkg` REJECTED by macOS Tahoe with "package is incompatible" error (Tahoe SSV write protection on `/`). v1.0.0 release blocker. | ✅ closed in v1.0.1 | — | Tahoe SSV / Apple HIG |

Total: **10 of 13 closed** (✅ in v1.0.1 = 3, ✅ in v1.0.2 = 7). 2 deferred as N/A on the customer .pkg path. 1 still open (B-6).

---

## Section 9 — Versions and releases

### v1.0.0 — 2026-04-28 (first signed + notarized installer)

- **Release notes:** `docs/RELEASE_NOTES_v1.0.0.md`
- **Build SHA:** `978ff61126ea`
- **Tag:** `v1.0.0-978ff61126ea`
- **Filename per release notes:** `MiningGuardian-1.0.0-978ff61126ea.pkg` (392,562,726 bytes / ~374 MB)
- **Filename per `RUNBOOK_INSTALL_DAY_2026-04-30.md`:** `MiningGuardian-1.0.0-0f849bd217cc.pkg` [TO VERIFY which artifact name is the live v1.0.0; the runbook may describe a later rebuild within the v1.0.0 train]
- **SHA-256 per release notes:** `c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8`
- **Notarization submission ID:** `2c4130a4-13e6-4783-9b06-b7969ccb36aa` (Accepted ✅)
- **What it shipped:** First signed/notarized .pkg. Vendored Colima + Lima 2.x (vz-only) + Docker CLI + Ollama.app + Python wheels. Install location: `/usr/local/MiningGuardian/`.
- **What broke it:** Failed to install on macOS Tahoe (B-13). Tahoe SSV rejected the `--install-location "/"` shape with payload `payload/MiningGuardian/...`.

### v1.0.1 — 2026-05-01 (Tahoe SSV release-blocker hotfix)

- **Release notes:** `docs/RELEASE_NOTES_v1.0.1.md`
- **What changed:** B-11 + B-12 + B-13 closed. Install location moved from `/usr/local/MiningGuardian/` to `/Library/Application Support/MiningGuardian/`. RAM-tier model selection now matches D-13 across both install paths. Welcome + Conclusion HTML now light-only color-scheme.
- **What stayed:** Same payload shape, same vendored components, same Apple signing identity.

### v1.0.2 — 2026-05-02 (installer UX hardening)

- **Release notes:** `docs/RELEASE_NOTES_v1.0.2.md`
- **GitHub Release:** https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.2
- **Build SHA:** `27fb2c10bbe0`
- **Filename:** `MiningGuardian-1.0.2-27fb2c10bbe0.pkg`
- **Size:** 437,022,332 bytes (417 MB)
- **SHA-256 sidecar:** `MiningGuardian-1.0.2-27fb2c10bbe0.pkg.sha256`
- **Build details (per HANDOFF_2026-05-02 EOD):** signed, notarized, stapled in a single Apple notary cycle, 9m9s, "cleanest build yet."
- **What changed:** B-1 + B-2 + B-3 + B-7 + B-8 + B-9 + B-10 closed. New site-config-file approach. New `--config-file=PATH` flag. New install-path architecture doc. Catalog count standardized at 320 across all docs.
- **Payload shape:** identical to v1.0.1 (no SSV / signing / notarization changes).
- **PRs:** #105 (D-15 + D-16 + handoff infra), #106 (B-1 + B-10), #107 (B-9), #108 (B-2 + B-7 + B-8), #109 (B-3), #110 (version bump), #111 (TBD per HANDOFF_2026-05-02 PR-train table mentioning #105–#111), #112 (D-17 + EOD handoff update — `8786d73`), #113 (HANDOFF_2026-05-03 — `81ac06e`).

---

## Section 10 — Install paths (BOTH paths — current state of the contradiction)

### 10.1 Customer .pkg path

- **Entry point:** `MiningGuardian-1.0.2-27fb2c10bbe0.pkg` (double-click in Finder, or `sudo installer -pkg ... -target /`).
- **Distribution.xml:** declares Welcome (`welcome.html`) → License (`license.txt`) → Conclusion (`conclusion.html`) screens. No customer-info prompt screen exists in the .pkg GUI flow per `installer/macos-pkg/Distribution.xml` reading.
- **Preinstall (`installer/macos-pkg/scripts/preinstall.sh`):** runs as root via Installer.app. Validates: macOS ≥ 13, Apple Silicon, RAM ≥ 16 GB, free disk ≥ 20 GB on `/`, `/Applications` writable, no conflicting non-pkg-managed install. Calls `lib/detect_ram.sh` to pick the LLM model per D-13.
- **Postinstall (`installer/macos-pkg/scripts/postinstall.sh`):** lays down install root at `/Library/Application Support/MiningGuardian`, drops `.env` (with ONLY `MG_DB_PASSWORD` + Postgres connection vars from a per-build secret file), provisions Postgres in Colima, applies migrations 000_bootstrap + 002_layer2 + 003_c5_notify_triggers, installs Ollama + pulls the LLM model, copies the 9 launcher wrappers, installs and `launchctl bootstrap`s the 9 launchd plists, writes `/etc/mining-guardian/install-receipt.json`, fires a baseline scan.
- **What the .pkg postinstall does NOT do (per code reading):** does NOT prompt for AMS_URL / AMS_EMAIL / AMS_WORKSPACE_ID / SLACK_WEBHOOK_URL / SLACK_BOT_TOKEN / etc. Does NOT install Grafana via Homebrew (the Distribution.xml + Welcome copy mention "registers four background services" which is a v1.0.0-era line; the actual postinstall now bootstraps 9 services). Does NOT run setup.sh's Phase 11 Grafana provisioning, Phase 12 Tailscale, Phase 5 catalog seed (the migrations applied are bootstrap + layer2 + c5_triggers, not the 320-row `seed_miner_models.sql`). Does NOT install Homebrew packages.
- **Welcome copy claim:** `welcome.html` says "Lays down the Mining Guardian application at `/Library/Application Support/MiningGuardian`. Stands up a local Postgres 16 database in a Colima-managed container, bound to `127.0.0.1:5432` only. Installs Ollama and pulls a local LLM model... Registers four background services so Mining Guardian comes up automatically every time this Mac boots." **The "four" count is stale (the current postinstall code installs 9 services).**

### 10.2 Operator setup.sh path (15 phases)

Per `scripts/setup.sh`. Mini-install canonical per `docs/INSTALL_PATHS_2026-05-02.md`.

| Phase | Function | What it does |
|---|---|---|
| 1 | `phase_01_preflight` | Pre-flight: macOS version, arm64, free disk (B-1 fix uses `diskutil info /` Container Free Space), Homebrew present |
| 2 | `phase_02_customer_info` | Resolves site config — either via `--config-file=PATH` (B-2 fix) or `$EDITOR`/nano interactive editor with validation. In dry-run mode without a config file, fills placeholder values per B-7. |
| 3 | `phase_03_brew_deps` | Homebrew installs: postgresql@16, jq, curl, openssl, python@3.12, ollama, grafana, optional tailscale |
| 4 | `phase_04_postgres` | Postgres 16 setup: 3 DBs (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`) + applies all `migrations/NNN_*.sql` files in lexical order |
| 5 | `phase_05_catalog_seed` | Runs `intelligence-catalog/seed-data/seed_miner_models.sql` (320 rows) plus `deploy_schema.sql` |
| 6 | `phase_06_repo_venv` | Repo + Python 3.12 venv + pip install |
| 7 | `phase_07_secrets` | Generates `MG_DB_PASSWORD`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET` (`openssl rand -hex 32` each), writes `${MG_INSTALL_ROOT}/.env` (chmod 600 root:wheel) |
| 8 | `phase_08_ollama` | Ollama install + RAM-tier model pull per D-13 |
| 9 | `phase_09_launchdaemons` | Installs and bootstraps the 9 launchd services |
| 10 | `phase_10_cron` | Installs the 11 cron entries; prompts operator for Full Disk Access on `/usr/sbin/cron` |
| 11 | `phase_11_grafana` | Starts Grafana; writes minimal postgres datasource YAML (Bucket 6d defers full provisioning) |
| 12 | `phase_12_tailscale` | Optional: `tailscale up --accept-routes` (only when `--tailscale` flag passed) |
| 13 | `phase_13_smoke_test` | End-to-end smoke: Postgres connectivity, Python imports, all 9 launchd labels with PID, dashboard-api HTTP check on `:8585` |
| 14 | `phase_14_postinstall` | Post-install summary |
| 15 | `phase_15_snapshot_restore` | Optional snapshot restore via `--restore-from-snapshot=<tarball>` |

### 10.3 The contradiction — RESOLVED 2026-05-03 by audit + D-18 / D-19 / D-20

**Both of the following statements were in `main` until 2026-05-03:**

- `docs/DECISIONS.md` D-16 step 4: "Install on the customer-site Mini via .pkg double-click with screenshots at every screen (Sunday afternoon)."
- `docs/INSTALL_PATHS_2026-05-02.md`: "do NOT click the `.pkg` on the Mini" plus "What does the install ship? | Postgres + Grafana + Ollama + Tailscale + scheduled tasks + viewer | Viewer only |".

**Resolution:** Both statements are wrong as written. Per the v1.0.2 .pkg audit (`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`):

- **Outcome C — partial / hybrid.** The v1.0.2 .pkg is NEITHER full-install NOR viewer-only. It is a partial operations install: postinstall.sh creates Postgres in Colima, installs Ollama, copies 9 launchd plists and `launchctl bootstrap`s them, and writes a partial `.env` (only `MG_DB_PASSWORD` + Postgres connection vars). It does NOT install Grafana, does NOT seed the 320-row catalog, does NOT install the Python venv (despite the launcher wrappers and step_baseline_scan referencing `${MG_INSTALL_ROOT}/venv/bin/python`), does NOT install scheduled tasks (no cron, no `StartCalendarInterval`), does NOT collect AMS/SLACK customer credentials. Every LaunchDaemon would crash-loop within 10 seconds because the venv path does not exist and the `.env` lacks the AMS/SLACK keys the launcher wrappers source. Apple's notarization stack would still confirm "install completed" — apparent success, real silence.
- **D-16 step 4 amended by D-18:** "Install on the customer-site Mini via v1.0.3 .pkg double-click with screenshots at every screen — when v1.0.3 is verified green on a clean Mac VM (UTM/Tart)."
- **`INSTALL_PATHS_2026-05-02.md` superseded by `INSTALL_PATHS_2026-05-03.md` per D-18.** The 2026-05-02 doc retains a SUPERSEDED notice at its top.
- **D-19** locks the customer operator console as the 10th LaunchDaemon (Cloudflare-fronted at `mg.fieslerfamily.com`).
- **D-20** locks the importer (`mg_import_tool/`) as operator-only forever; it is NOT bundled into the customer .pkg.

**Mini cutover state:** PAUSED. The Mini will not be cut over until v1.0.3 is built, signed, notarized, and smoke-tested green on a clean Mac VM per D-18's verification gate. The Hostinger VPS continues running production. ROBS-PC's catalog volume stays intact.

---

## Section 11 — What's in flight RIGHT NOW

| Item | Status | Owner / artifact |
|---|---|---|
| v1.0.2 .pkg audit | ✅ Complete and committed at `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`. | Computer |
| D-18 / D-19 / D-20 | ✅ Locked in DECISIONS.md (this PR). | Operator + Computer |
| INSTALL_PATHS rewrite | ✅ `docs/INSTALL_PATHS_2026-05-03.md` is the new authoritative; 2026-05-02 carries a SUPERSEDED notice. | Computer |
| v1.0.3 build | 🔴 QUEUED. Per D-18 implementation plan: discovery first (approval queue + Live Action Queue panel + `mg_import_tool/` payload audit), then per-gap PR train (venv, catalog seed, customer-info conf flow, Grafana, scheduled-tasks plists, console, copy-bug fixes, uninstall.sh, version bump + release notes), then build + sign + notarize, then smoke-test on clean VM. New chat session opens 2026-05-04. | Computer (new chat) |
| Operator console (D-19) build | 🔴 QUEUED as part of v1.0.3 PR train. FastAPI under `console/`, Jinja2 + HTMX, binds 127.0.0.1:8686, Cloudflare-fronted at `mg.fieslerfamily.com`. | Computer (new chat) |
| Mini cutover | PAUSED until v1.0.3 verified green on clean Mac VM (per D-18 verification gate). The Mini is empty / fresh / Tailscale up at `100.69.66.32`. Repo not yet cloned to `~/code/Mining-Guardian`. | Operator + Computer |
| HANDOFF_2026-05-03 | Closed at end-of-day. | `docs/handoffs/HANDOFF_2026-05-03.md` |
| HANDOFF_2026-05-04_NEW_CHAT | ✅ Created. The next agent reads this BEFORE anything else. | `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md` |
| Open question 2 from 2026-05-02 | Still open: should `docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` be edited to clarify "ROBS-PC superseded at runtime, retained as masters until Mini-verified-green, then decommissioned"? Recommendation: defer until after v1.0.3 ships and Mini is verified green. | Operator |

---

## Section 12 — What's NEXT (Monday and beyond)

**Order amended 2026-05-03 by D-18.** Every Mini-cutover item is deferred until v1.0.3 ships and is verified green on a clean Mac VM. The Hostinger VPS continues running production. ROBS-PC's catalog volume stays intact.

1. **New chat session opens 2026-05-04 morning** — agent reads `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md` BEFORE anything else, then `docs/PROGRAM_STATE.md` (this file), then DECISIONS.md (D-1 through D-20), then the v1.0.2 audit.
2. **Discovery (no code):** verify what `mg_import_tool/` actually exposes today, what the Grafana "Live Action Queue" panel does today (display-only or interactive Approve/Deny?), whether approval data persists in Postgres or only in Slack. Output: `docs/discoveries/DISCOVERY_2026-05-04.md`.
3. **v1.0.3 PR train per D-18 implementation plan, in dependency order:**
   1. venv creation in postinstall (closes Gap 5).
   2. Catalog DB + 320-row seed in postinstall (closes Gap 2).
   3. Customer-info Desktop conf flow in postinstall (closes Gap 1 + Integration bug 4).
   4. Grafana vendoring + provisioning + LaunchDaemon (closes Gap 3).
   5. Scheduled-tasks launchd plists replacing the cron entries from setup.sh phase_10 (closes Gap 4).
   6. Operator console (D-19) — full FastAPI / Jinja2 / HTMX build under `console/`.
   7. Copy-bug fixes in welcome.html + conclusion.html (closes Copy bugs 1, 2, 4).
   8. Real `bin/uninstall.sh` (closes Copy bug 3).
   9. Cloudflare Tunnel + Access setup in postinstall (D-19).
   10. `MG_DB_PASSWORD` self-generation in postinstall (closes Integration bug 1).
   11. `GUARDIAN_PG_USER` + `PGUSER` dual-write in postinstall (closes Integration bug 2).
   12. Tailscale-status check + Cocoa dialog (closes Integration bug 3).
   13. Version bump + `docs/RELEASE_NOTES_v1.0.3.md`.
4. **Build v1.0.3 .pkg, sign, notarize, staple** on operator's laptop.
5. **Smoke-test v1.0.3 on a clean macOS 14 VM (UTM/Tart).** Iterate until all D-18 verification-gate criteria pass.
6. **Install on the Mini.** Screenshots at every Phase 4 + Phase 5 boundary per the existing HANDOFF_2026-05-03 plan.
7. **Verify Mini green per D-16 + D-18.**
8. **AFTER Mini-verified-green only:** shut down the ROBS-PC Docker container `mining-guardian-db` (per D-16 step 7, deferred from Monday 2026-05-04).
9. **AFTER Mini-verified-green only:** decommission the Hostinger VPS (per D-16 step 8, deferred from Monday 2026-05-04).
10. **Post-cutover (no fixed date):** D-17 reconciliation — schedule the monthly ROBS-PC → Mini catalog sync over Tailscale.
11. **Post-cutover:** Anti-drift sweep of all companion docs against `docs/DECISIONS.md`. The D-16 vs INSTALL_PATHS contradiction was the trigger; the sweep prevents the next contradiction.
12. **Post-cutover:** D-14 implementation PRs — drop the 5-min cache in `ai/catalog_context.py`, wire `core/mining_guardian.py` to consult the catalog on every miner evaluation, make catalog read failure raise / log at ERROR, build the C5 NOTIFY/LISTEN daemon (`feedback_loop_daemon`), point AI consumers at psycopg-direct.
13. **Post-cutover:** Begin the customer-facing phone-app project. Once the phone app ships, the operator console (D-19) is retired.
14. **Post-cutover:** Build the operator-side delta-push tool for D-20 (Tailscale rsync or postgres dump-restore from operator → customer Mini Postgres).
15. **Post-cutover security backlog:** S-5, S-7, S-8, S-9, S-10, S-11, S-14 from MG_UNIFIED_TODO_LIST.md.
16. **Post-cutover catalog backlog:** C1, C2, C3, C4, C5 (catalog API surface fix, watcher rewrites, NOTIFY/LISTEN daemon, installer catalog seed step — most of which v1.0.3 closes inline).
12. **Eventual:** Edit `docs/INTEL_CATALOG_FULL_BRIEF_2026-05-02.md` to reconcile "ROBS-PC superseded at runtime" with "ROBS-PC retains masters" per D-16.

---

## Section 13 — Mantras and rules of engagement (verbatim from operator)

These are verbatim quotes from the operator that have been carried forward in handoffs. They are operative, not decorative. Read them at session start. Refer back to them at decision points during the session.

- "always comprehensive, and always over document"
- "I would rather be late and perfect than early and wrong"
- "step by step please i need to focus" / "i have ocd and i hate slop or messes"
- "stay away from anything cloud only and stay local" / "Bitcoin SHA-256 miners ONLY"
- "leave no data behind lets get it all"
- "remember the list grows as miners get added so it needs to reflect that on grafana, it is not a static number"
- "by the begining of monday morning... fully self contained, we can then shut down the container and the vps and move on to the app"
- "i want you to write a document that if we did not do any work for 2 weeks you could read it and know what we have done, what we are working on, whats right whats wrong and what we have to do, this is for you not me"
- "Real quick ollama will now be on the Mac mini, no longer on the pc, it will all be contained on the new mac" (origin of D-7)
- "I would like everything done before we install on the Mac Mini. I truly want this to be a 100% representative of what customer would receive and load. All patches all fixes done. Paper written. I want to be our first customer. So if we push loading on the mini out that is fine. We were planing on May 5 anyway. I did not realize how far out we were. Remember slow and steady. I would rather be late and perfect than early and wrong." (origin of D-10)
- "I believe in over-documentation so we know what each day brings." (origin of D-12)
- "they should always be able to reference each other, so when you are talking to the llm to ask questions everything is live for it to reference" (origin of D-14 sub-locks 1-2)
- "when the hourly scans happen it will be able to access it whenever it is needed it will be there, as a reference to look things up and learn correct" (origin of D-14 sub-locks 1-2)
- "we will only be keep the masters on robs pc, it will not be pulling anything from anywhere that is the purpose of the design fully self contained, we can then shut down the container and the vps and move on to the app" (origin of D-16)
- "I agree with you, with this work it may take a couple of times to get it right" (origin of D-17)
- "this can not be the process for customers take a note of that it needs to be fixed" (B-4 customer-impact note)
- "we were trying to do this for a person not familiar with terminal" (B-5 customer-impact note)

### Standing rules in effect (also carried forward verbatim from HANDOFF_TEMPLATE.md and HANDOFF_2026-05-03)

- Leave no data behind. Every piece of enrichment, every belief, every intermediate file is documented or committed before the session closes.
- Step by step. One action at a time. No "while I'm at it" changes.
- Late and perfect over early and wrong. Do not push a fix under time pressure. Stop, confirm, then act.
- Stay local — Bitcoin SHA-256 only. No cloud AI inference for mining operational data. Qwen on ROBS-PC 4090 or local Ollama on Mini only.
- Never call SQLite live. The program is on Postgres. Any SQLite reference is a bug.
- No destructive operations without confirming with operator first. This includes: `docker volume rm`, `DROP TABLE`, `DELETE FROM`, any `rm -rf` on repo or data directories, and any password change on a live service.
- Use `gh` CLI for all GitHub operations, not browser_task. No PR creation, merge, or review through the browser tool.
- Every fix PR flips the corresponding MG_UNIFIED_TODO_LIST row from 🔴 to ✅ in the same commit.
- Every session ends with a HANDOFF_<DATE>.md. Every session starts by reading the latest handoff. Failure to read the prior handoff before proposing a fix is a protocol violation operator can use to stop the session immediately.
- AI must explicitly call out every screenshot moment in real time during install, so the install PDF can be assembled from the captured frames without gaps.

---

## Section 14 — How to update this document

`docs/PROGRAM_STATE.md` is required reading at session start, alongside the most recent `docs/handoffs/HANDOFF_<DATE>.md`. It is updated at the end of every working session in the same PR as that day's handoff. Specifically:

1. **Session start checklist** (extends the D-15 next-session start checklist):
   - Read this file (`docs/PROGRAM_STATE.md`) in full.
   - Read the most recent `docs/handoffs/HANDOFF_<DATE>.md` in full.
   - Re-verify any [TO VERIFY] flag in this file before acting on the underlying claim.
   - Re-verify any [VERIFY FIRST] belief in the day's handoff before acting on the underlying claim.
   - Confirm `origin/main` HEAD matches the `last_main_sha_at_write` line in this file's YAML header — if not, read the intervening commits and update this file in the same PR as today's HANDOFF_<DATE>.md.

2. **Session end checklist** (extends the D-15 end-of-session checklist):
   - Update the YAML header at the top of this file: `written` (today's date), `last_main_sha_at_write` (the SHA this update is based on).
   - Walk every section. If any fact moved (a new D-? landed in DECISIONS.md, a B-? closed, a host topology change shipped, a new release tagged), update the relevant row.
   - Add new [TO VERIFY] flags rather than guess.
   - Resolve old [TO VERIFY] flags by sourcing them from repo content — only operator confirmation can convert a [TO VERIFY] into a verified fact.
   - Commit the update in the same PR as today's `HANDOFF_<DATE>.md`.

3. **Reconciliation after a contradiction is found** (per Section 10 / the D-16 vs INSTALL_PATHS pattern):
   - When two authoritative docs contradict, this file's Section 10-style "both sides + audit + pending D-? decision" treatment is the canonical pattern.
   - Once the contradiction resolves via a new D-?, this file is updated in the same PR as the D-? lock.

4. **Cold-start scenario** (the operator's stated purpose):
   - A fresh agent reads this file from top to bottom. Every fact has a citation back to the underlying repo file (`DECISIONS.md`, `RELEASE_NOTES_*.md`, `INSTALL_PATHS_*.md`, the relevant runbook, the relevant handoff).
   - If any fact in this file conflicts with the underlying repo file, the underlying file wins and this file is amended in the same PR.

The single most important rule for keeping this file useful: **do not let it drift.** If a session passes without updating this file, the next agent reads stale facts and makes the same mistakes the D-15 + D-16 + the cutover-day blocker were created to prevent. Write the update in the same commit as the day's handoff. Always.

---

End of `PROGRAM_STATE.md`. New facts are added by amending sections in place — append-only is for `DECISIONS.md` and `INCIDENTS.md`, not for this file. Unresolved [TO VERIFY] flags propagate forward across sessions until resolved.
