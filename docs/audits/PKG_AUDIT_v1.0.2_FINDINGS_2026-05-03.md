# v1.0.2 .pkg audit findings — 2026-05-03

**Status:** Authoritative. Commissioned by operator after install-day surfaced a D-16 vs INSTALL_PATHS contradiction.
**Audit method:** Read-only static analysis of postinstall, Distribution.xml, launcher wrappers, and comparison against setup.sh.
**Authorizing decision:** D-18 (this PR).
**Resolution:** v1.0.3 closes all gaps. v1.0.2 .pkg is NOT installed on the Mini. setup.sh path also deferred — Mini cutover slips until v1.0.3 is verified on a clean Mac VM.

---

# MiningGuardian-1.0.2-27fb2c10bbe0.pkg — Code Audit Findings

**Build SHA:** `27fb2c10bbe0`
**Filename:** `MiningGuardian-1.0.2-27fb2c10bbe0.pkg` (437,022,332 bytes / 417 MB)
**GitHub Release:** https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.2
**Auditor:** Computer (autonomous agent)
**Audit date:** 2026-05-03

This audit answers a single question: **what does double-clicking the v1.0.2 .pkg on a Mac actually do?** The answer drives whether the long-standing D-16 vs `INSTALL_PATHS_2026-05-02.md` contradiction resolves toward "click the .pkg on the Mini" (D-16's reading) or "never click the .pkg on the Mini, viewer-only" (INSTALL_PATHS's reading).

The findings below are grounded in the actual repo state at HEAD `f92869b` (PR #114 merged 2026-05-03). Every claim is sourced from a specific file + line range. Every gap is the difference between what the .pkg does and what the customer-experience vision requires.

---

## TL;DR — verdict

**Neither D-16 nor INSTALL_PATHS_2026-05-02.md is correct as written.**

- D-16 step 4 says "Install on the customer-site Mini via .pkg double-click with screenshots at every screen (Sunday afternoon)." This assumes the v1.0.2 .pkg installs the full operations stack. **It does not.**
- `INSTALL_PATHS_2026-05-02.md` says ".pkg is the viewer-only build" with "site config is fetched from the Mini over Tailscale." **The .pkg payload is not viewer-only — it is a partial operations build, missing Grafana, missing the catalog seed, missing the venv, missing scheduled tasks, missing customer-info collection, with `welcome.html` and `conclusion.html` describing a system that does not match what postinstall.sh actually creates.**

**The v1.0.2 .pkg is a partial operations installer that would produce an Apple-confirmed "install completed" dialog with a non-functional Mining Guardian on the Mini.** Every LaunchDaemon would crash-loop within seconds because the `.env` it writes does not contain the AMS/Slack credentials the launcher wrappers source. The dashboard URL in the conclusion screen (`:8080`) does not match the port the dashboard-api binds (`:8585` per `setup.sh` `phase_07_secrets`). The "four services" copy contradicts the nine services the postinstall installs. The uninstall.sh script the conclusion screen references does not exist in the payload.

**Recommendation:** v1.0.2 .pkg must NOT be clicked on the Mini. Build v1.0.3 with all gaps closed (see Section 6 below). Do not cut over the Mini until v1.0.3 is verified on a clean Mac VM.

---

## Section 1 — What the v1.0.2 .pkg actually does

Source files audited in full:

- `installer/macos-pkg/scripts/build_pkg.sh` (491 lines) — build pipeline, signs + notarizes
- `installer/macos-pkg/scripts/preinstall.sh` (231 lines) — gates the install
- `installer/macos-pkg/scripts/postinstall.sh` (435 lines) — installs the payload
- `installer/macos-pkg/scripts/lib/install_colima.sh` (195 lines) — Colima + Postgres provisioning
- `installer/macos-pkg/scripts/lib/install_ollama.sh` (141 lines) — Ollama install + model pull
- `installer/macos-pkg/resources/Distribution.xml` (96 lines) — single-step install descriptor
- `installer/macos-pkg/resources/welcome.html` (228 lines) — Welcome screen copy
- `installer/macos-pkg/resources/conclusion.html` (212 lines) — Conclusion screen copy
- `installer/macos-pkg/resources/launchd/*.plist` — 8 launchd plists
- `installer/macos-pkg/resources/launchd/launchers/*.sh` — 8 launcher wrappers
- `installer/macos-pkg/resources/MiningGuardian.conf.template` (92 lines) — site-config template (not used by the .pkg path)
- `scripts/setup.sh` (1,082 lines) — operator-path comparison

### 1.1 Preinstall gates (preinstall.sh)

The preinstall enforces these gates BEFORE any payload is laid down. All correct, all working.

| Gate | Exit code | What it checks |
|---|---|---|
| `gate_root` | 10 | Running as root via Installer.app |
| `gate_macos_version` | 11 | macOS ≥ 13.0 (Ventura) |
| `gate_apple_silicon` | 12 | `uname -m` returns `arm64` |
| `gate_ram` (delegated to `lib/detect_ram.sh`) | 13 / 20 | RAM ≥ 16 GB; writes `MG_INSTALL_RAM_TIER` + `MG_INSTALL_LLM_MODEL` to `/tmp/mg_install_env` per D-13 |
| `gate_free_disk` | 14 | df-reported free disk ≥ 20 GB on `/` |
| `gate_applications_writable` | 15 | `/Applications` exists and is writable |
| `gate_no_conflict` | 16 | If `/Applications/Mining Guardian.app` exists, refuse unless prior pkg receipt is present |

The preinstall is solid. No findings here.

### 1.2 Postinstall steps (postinstall.sh)

Postinstall runs the following steps in order (from the `main()` function, lines 410-433):

1. `step_source_env` — sources `/tmp/mg_install_env` for RAM tier + LLM model
2. `step_load_libs` — sources `lib/install_colima.sh` + `lib/install_ollama.sh`
3. `step_layout_install_root` — creates `/Library/Application Support/MiningGuardian/{bin,logs,postgres-data}`
4. `step_drop_dotenv` — sources `/tmp/mg_install_env_secret` for `MG_DB_PASSWORD` and writes `.env`
5. `step_provision_postgres` — installs Colima vendored binaries, loads vendored Postgres image, starts container `mining-guardian-db` on `127.0.0.1:5432`, creates DB `mining_guardian` with user `mg`
6. `step_apply_migrations` — applies every `<payload>/migrations/*.sql` against `mining_guardian` DB
7. `step_install_ollama_and_pull_model` — installs vendored Ollama.app, pulls the LLM model selected by RAM tier (single network call)
8. `step_install_launcher_wrappers` — copies 8 launcher wrappers from payload + 1 from `deploy/feedback_loop_daemon_launcher.sh`
9. `step_install_plists_and_bootstrap` — installs 9 launchd plists into `/Library/LaunchDaemons/` and `launchctl bootstrap`s each
10. `step_write_install_receipt` — writes `/etc/mining-guardian/install-receipt.json`
11. `step_baseline_scan` — fires a non-blocking baseline scan via `${MG_INSTALL_ROOT}/venv/bin/python`

**That is the entirety of what double-clicking the v1.0.2 .pkg does.**

### 1.3 What the .pkg payload contains

Per `build_pkg.sh` `step_4_assemble_payload` (lines 173-251), the payload includes:

- App code: `core/`, `clients/`, `notifiers/`, `monitoring/`, `api/`, `ai/`, `intelligence-catalog/`, `mg_import_tool/`, `docs/`, `branding/`, `deploy/`, `migrations/`, `pyproject.toml`, `predictor.py`, `requirements.txt` (top-level only — verified by the rsync `--include` list)
- Migrations duplicated to `<payload>/migrations/` (mg_import_tool migrations + `migrations/003_c5_notify_triggers.sql`)
- Vendored runtime under `<payload>/runtime/` IF `${HOME}/MiningGuardian-vendor/` exists at build time: Colima, lima, docker CLI, Postgres image tarball, Ollama.app
- Build stamp at `<payload>/BUILD_STAMP.json`

### 1.4 Distribution.xml — GUI flow

Per `installer/macos-pkg/resources/Distribution.xml` (lines 22-95), the customer sees this exact sequence when they double-click the v1.0.2 .pkg:

1. **Welcome screen** — renders `welcome.html`
2. **License screen** — renders `license.txt`
3. **Destination screen** — Installer.app standard "Select a Destination"
4. **Installation Type screen** — Installer.app standard "This will take X MB"
5. **Install button** — admin password prompt
6. **Progress** — preinstall.sh + payload extract + postinstall.sh
7. **Conclusion screen** — renders `conclusion.html`

There is **no choice tree** (single-step install per Q1 / `<choices-outline>` collapsed to one line), **no customer-info form**, **no AMS/Slack token input screen**. The Distribution.xml has zero hooks for collecting site config from the user. The full site-config surface is invisible to the .pkg path.

---

## Section 2 — Component-by-component table

For each customer-experience component the operator's vision requires, the table below answers: **does the v1.0.2 .pkg postinstall actually install/configure it, or does it skip it?**

| # | Component | In v1.0.2 .pkg postinstall? | In setup.sh? | Notes |
|---|---|---|---|---|
| 1 | PostgreSQL 16 | **PRESENT** | PRESENT | postinstall provisions Colima + bundled `postgres:16-bookworm` image, container `mining-guardian-db` on `127.0.0.1:5432`. Creates DB `mining_guardian` with user `mg`. Applies migrations from `<payload>/migrations/`. setup.sh phase 4 takes a different route (`brew install postgresql@16` + native instance) and creates 3 DBs (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`). |
| 2 | Grafana :3000 | **ABSENT** | PRESENT | postinstall.sh contains no Grafana logic — verified by grep `grafana` in postinstall.sh: zero matches. setup.sh `phase_11_grafana()` runs `brew services start grafana` and writes a postgres datasource yaml. The .pkg does NOT install Grafana. |
| 3 | Ollama + LLM model pull | **PRESENT** | PRESENT | postinstall installs vendored Ollama.app + pulls `${MG_INSTALL_LLM_MODEL}` per D-13 (one network call). setup.sh `phase_08_ollama()` does the same via `ollama pull` after `brew install ollama`. |
| 4 | Tailscale | **ABSENT** | PARTIAL (opt-in via `--tailscale` flag) | postinstall.sh contains no Tailscale logic — verified by grep `tailscale` in postinstall.sh: zero matches. setup.sh `phase_12_tailscale()` runs `tailscale up --accept-routes` only when the operator passes `--tailscale`. Per D-9, Tailscale is operator-side anyway, but the .pkg does not even check whether it is up. |
| 5 | The 9 LaunchDaemons | **PRESENT** | PRESENT | postinstall installs 9 plists (8 from `installer/macos-pkg/resources/launchd/` + 1 from `deploy/`) and `launchctl bootstrap`s each. setup.sh `phase_09_launchdaemons()` installs the same 9. **However:** every plist's launcher wrapper (e.g. `scanner_launcher.sh`) sources `${MG_INSTALL_ROOT}/.env` and execs Python. The `.env` written by the .pkg postinstall does NOT contain AMS/Slack credentials (see Gap 1 below) — so every service crash-loops on first start. |
| 6 | The 320-row miner catalog seed | **ABSENT** | PRESENT | postinstall.sh applies migrations from `<payload>/migrations/` but does NOT apply `intelligence-catalog/seed-data/seed_miner_models.sql` (320 rows). The migrations directory contains schema migrations only — verified by inspecting `mg_import_tool/sql/migrations/`. setup.sh `phase_05_catalog_seed()` runs both `deploy_schema.sql` and `seed_miner_models.sql`. The .pkg ships a Postgres with empty `hardware.miner_models`. |
| 7 | The scheduled tasks (cron entries) | **ABSENT** | PRESENT | postinstall.sh contains no cron logic — verified by grep `cron\|crontab\|StartCalendarInterval` in postinstall.sh: zero matches. setup.sh `phase_10_cron()` installs 11 crontab entries (weekly_train, refinement_chain, db_maintenance, backup_knowledge, morning_briefing, daily_operator_review, cleanup_ams_logs, direct_collect_logs, daily_deep_dive, daily_log_failure_report, run_benchmark) and prompts the operator for Full Disk Access. The .pkg ships zero scheduled jobs — the `daily_deep_dive`, `morning_briefing`, `weekly_train` etc. never fire. |
| 8 | Customer-info collection (AMS_URL, SLACK_BOT_TOKEN, etc.) | **ABSENT** | PRESENT (via `--config-file=PATH` per B-2) | Distribution.xml has zero customer-info screens (single-step `<choices-outline>` collapsed to one line). postinstall.sh does NOT prompt for, read, or validate customer credentials. The `MiningGuardian.conf.template` exists in the payload but the .pkg postinstall never references it. setup.sh `phase_02_customer_info()` resolves config via `--config-file=PATH` or `$EDITOR`/nano. The .pkg ships with NO AMS or Slack values written to `.env`. |
| 9 | xcode-select / git clone / Homebrew dependencies | N/A — bundled | REQUIRED on host | The .pkg vendors Colima, lima, docker CLI, Ollama.app, Postgres image. No `xcode-select` needed, no `git clone` needed, no Homebrew needed for the .pkg path. setup.sh requires xcode-select (B-4) and Homebrew (`phase_03_brew_deps()`) and `git clone`. This part of the .pkg vision actually works. |

**Summary: 4 of 9 customer-vision components are PRESENT in the .pkg postinstall (Postgres, Ollama, the 9 launchd plists, and bundled deps). 5 are ABSENT (Grafana, Tailscale, catalog seed, scheduled tasks, customer-info collection).** The 9 launchd plists are loaded but every service crashes on first start because of Gap 1 below.

---

## Section 3 — Verdict

**C — Partial / hybrid installer that masquerades as "release-grade."**

The v1.0.2 .pkg does some things (Postgres, Ollama, plist registration, vendored deps) but does not do the things that would make the Mini operational from a customer's perspective (Grafana for the dashboards mentioned in welcome.html, the 320-row catalog seed for the catalog the dashboards reference, the customer's own AMS/Slack credentials so the launchd services can start without crashing, the scheduled tasks that produce the daily briefings the operator's mantras describe, the venv that postinstall.sh's own `step_baseline_scan` references at line 400).

The .pkg is **NOT** a viewer (INSTALL_PATHS_2026-05-02.md is wrong about this).
The .pkg is **NOT** a full operations install (D-16 step 4 is wrong about this).
The .pkg is a **partial operations install whose conclusion screen claims the system is "running" when in fact every service is crash-looping.**

This is the most dangerous of the three possible failure modes: apparent success, real silence. Apple's notarization stack confirms the install completed. The "Mining Guardian — Installed" conclusion screen renders the green check pill. The customer thinks they are done. The miner fleet goes unmonitored. The customer's first impression of the product is a system that does nothing.

---

## Section 4 — Distribution.xml screens (full GUI flow walkthrough)

When the customer double-clicks `MiningGuardian-1.0.2-27fb2c10bbe0.pkg`, they see exactly this sequence, in order. Every screen is sourced from `Distribution.xml` lines 22-95 + the linked HTML / TXT files:

1. **Welcome (`welcome.html`, 228 lines).** Branded eyebrow "Mining Guardian · v1.0", h1 "Welcome", lede "Bitcoin mining-fleet observability and auto-remediation, running entirely on your hardware. No cloud, no telemetry, no shared tenancy." Bullet list "What this installer does" — claims:
   - "Lays down the Mining Guardian application at `/Library/Application Support/MiningGuardian`" — TRUE
   - "Stands up a local Postgres 16 database in a Colima-managed container, bound to `127.0.0.1:5432` only" — TRUE
   - "Installs Ollama and pulls a local LLM model sized to your Mac's RAM (16 GB → `llama3.2:3b`; 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`)" — TRUE per D-13
   - "Registers four background services so Mining Guardian comes up automatically every time this Mac boots" — **FALSE**. The postinstall installs **nine** services (`PLIST_LABELS` array in postinstall.sh lines 114-124 plus the `feedback-loop-daemon` plist from `deploy/`). This is **Copy bug 1**.
   - Callout: "One network step at first install." — TRUE (Ollama model pull)
   - "What you'll need" — Apple Silicon, macOS 13+, 16+ GB RAM, 20+ GB free disk, network for one-time model pull, admin password — TRUE
   - "What happens after install" — claims "Once the installer finishes, the four Mining Guardian services start immediately and a baseline scan runs in the background. You can open the dashboard at `http://127.0.0.1:8080/` within about 30 seconds." — **FALSE on two counts**:
     - "four services" → should be "nine" or "ten" (Copy bug 1).
     - `http://127.0.0.1:8080/` → setup.sh phase_07_secrets writes `GUARDIAN_DASHBOARD_PORT=8585`. The dashboard-api launcher exec's `${MG_INSTALL_ROOT}/api/dashboard_api.py` which reads that port. The `:8080` in welcome.html is a **stale port number** that does not match what dashboard-api binds. This is **Copy bug 2**.

2. **License (`license.txt`).** Plain text license display. No findings.

3. **Destination.** Installer.app standard.

4. **Installation Type.** Installer.app standard.

5. **Install** — admin password prompt, then preinstall.sh runs (validates the gates from Section 1.1), payload extracts to `/Library/Application Support/MiningGuardian/`, postinstall.sh runs (executes the 11 steps from Section 1.2). Total time ~3-5 min for the install + ~5-15 min for the Ollama model pull at 16 GB tier.

6. **Conclusion (`conclusion.html`, 212 lines).** Green check pill, h1 "You're up and running.", lede "All four background services are now registered with launchd and will start automatically every time this Mac boots. A first-run baseline scan is running in the background — give it about 30 seconds before opening the dashboard." Quick links table:
   - Dashboard `http://127.0.0.1:8080/` — **WRONG PORT** (Copy bug 2)
   - Approval queue `http://127.0.0.1:8081/` — also wrong; setup.sh writes `GUARDIAN_APPROVAL_PORT=8686` (Copy bug 2 extension)
   - Install log `/var/log/mining-guardian/install-postinstall.log` — TRUE
   - Service logs `/Library/Application Support/MiningGuardian/logs/` — TRUE
   - Install receipt `/etc/mining-guardian/install-receipt.json` — TRUE
   - "Verifying the four services" code block listing only 4 of 9 service labels — **WRONG** (Copy bug 4)
   - "Uninstall" section: "Run `sudo /Library/Application Support/MiningGuardian/bin/uninstall.sh` to cleanly stop all four services, drop the Postgres container, and remove `/Library/Application Support/MiningGuardian`. Your Postgres data volume is preserved at `/Library/Application Support/MiningGuardian/postgres-data` by default — pass `--purge-data` to remove it." — **WRONG**: `bin/uninstall.sh` does not exist in the repo. Verified by `find . -name uninstall.sh` — zero matches outside test fixtures. This is **Copy bug 3**.

**No screen prompts the customer for AMS URL, AMS email, AMS workspace ID, Slack webhook, or Slack tokens.** Where do those values come from in the .pkg path? The answer per code reading: nowhere. The .pkg path has no provision for collecting them. The launchd services source `.env` and find no `AMS_*` / `SLACK_*` keys, log a fatal error, and the launchd `KeepAlive=Crashed` directive (`com.miningguardian.scanner.plist` lines 41-46) restarts them — and they crash again, and again, and again, throttled by `ThrottleInterval=10` to one restart per 10 seconds.

---

## Section 5 — Code-grounded gap inventory

Five hard installation gaps. Four user-facing copy bugs. Four integration bugs (most consequential is Gap 1 / Integration bug 4: customer credentials are never collected, every launchd service crashes).

### Gap 1 — Customer-info collection (BLOCKER, system-non-functional)

- **Where it should be:** Distribution.xml `<choice>` element OR postinstall.sh reading a known-path config file.
- **What is actually there:** Distribution.xml has `<choices-outline>` collapsed to a single line (no choice tree per the Q1 hybrid .pkg lock in `installer/macos-pkg/README.md`). postinstall.sh has zero references to `MiningGuardian.conf`, `AMS_URL`, `SLACK_BOT_TOKEN`, or any customer credential.
- **Effect:** The `.env` written by `step_drop_dotenv` (postinstall.sh lines 203-243) contains only:
  - `MG_DB_PASSWORD` (sourced from `/tmp/mg_install_env_secret`)
  - `PGHOST=127.0.0.1`
  - `PGPORT=5432`
  - `PGUSER=mg`
  - `PGDATABASE=mining_guardian`
  - `MG_INSTALL_RAM_TIER`
  - `MG_INSTALL_LLM_MODEL`
  
  The `scanner_launcher.sh` (and every other launcher) sources this `.env` and execs Python. The Python entry points read `os.environ['AMS_BASE_URL']` etc. and raise `KeyError`. Every service exits non-zero. launchd's `KeepAlive=Crashed` (per `com.miningguardian.scanner.plist` lines 38-46) restarts each service every 10 seconds (ThrottleInterval). The system burns CPU on crash-loops while presenting a green "Installed" dialog.

### Gap 2 — Catalog DB + 320-row seed (BLOCKER for AI / dashboards / catalog UX) — RESOLVED in v1.0.3 (PR mg/v103-gap2-catalog-db-and-seed)

- **Where it should be:** postinstall.sh after `step_apply_migrations`, before service bootstrap.
- **What is actually there:** `step_apply_migrations` (postinstall.sh lines 251-272) walks `<payload>/migrations/*.sql` and applies each against the `mining_guardian` DB. Per `build_pkg.sh` `step_4_assemble_payload` lines 217-223, those migrations are `mg_import_tool/sql/migrations/*.sql` plus `migrations/003_c5_notify_triggers.sql`. **None of those create or seed `hardware.miner_models`.** The 320-row baseline (`intelligence-catalog/seed-data/seed_miner_models.sql`) is in the payload (`intelligence-catalog/***` is rsync-included at line 206) but is never applied. setup.sh `phase_05_catalog_seed()` applies it (`psql -U guardian_app -d mining_guardian_catalog -f seed_miner_models.sql`).
- **Effect:** `hardware.miner_models` is empty on the .pkg-installed Mini. The intelligence-report API has no catalog to reference. Every miner appears as "unknown model." AI scan analysis runs against an empty reference — Qwen returns generic guesses. The Grafana Intelligence Report dropdown (when Grafana exists, which per Gap 3 it does not) would show zero models.
- **Resolution (v1.0.3 PR mg/v103-gap2-catalog-db-and-seed, 2026-05-04):** Added `step_provision_catalog_db_and_seed` to `installer/macos-pkg/scripts/postinstall.sh`, called between `step_apply_migrations` and `step_install_ollama_and_pull_model` so catalog provisioning happens before the slow Ollama model pull (a catalog failure surfaces fast rather than after the 5–15 minute network step). The step:
  1. Creates the `mining_guardian_catalog` database in the existing `mining-guardian-db` Colima container with `OWNER mg`. Idempotent — pre-checks `pg_database` before issuing `CREATE DATABASE`.
  2. Applies the canonical catalog schema bundle via `intelligence-catalog/seed-data/deploy_schema.sql`, which `\ir`-includes the v1/v2/v3 schema files plus `staging_schema.sql`, then performs the manufacturer-brand enum extensions, then seeds `knowledge.sources`, `knowledge.contributors`, and `hardware.manufacturers`. All idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`).
  3. Applies the 320-row baseline from `intelligence-catalog/seed-data/seed_miner_models.sql` against the catalog DB. Idempotent at the row level via a `count(*) >= 320` short-circuit before re-apply.
  4. Verifies post-seed that `SELECT count(*) FROM hardware.miner_models;` returns ≥ 320, matching the D-18 verification gate floor. Hard-fails (exit 39) on any mismatch.
  - `installer/macos-pkg/scripts/build_pkg.sh` step 4g asserts `deploy_schema.sql` and `seed_miner_models.sql` are present under `<payload>/intelligence-catalog/seed-data/` after the 4a rsync, and that the seed file has ≥ 320 `INSERT INTO hardware.miner_models` rows. Hard-fails the build (exit 44) if either check fails — belt-and-suspenders against a future include-list edit silently dropping the seed.
  - Regression test at `tests/installer/test_postinstall_catalog_seed.sh` (24 assertions; gates ordering, idempotency, target DB, row-count assertion, exit code, no-network guarantee, build-time assertion, and shellcheck baseline).
  - Preserves the no-network rule (Vision Anchor 7): the only network call at install time remains the Ollama model pull. The catalog-seed step talks to the localhost Colima Postgres container exclusively.
  - Preserves D-14: the catalog DB lives in the same Postgres 16 container as the operational DB on the Mini, both reachable from any Mining Guardian process via psycopg.
  - **D-20 reconciliation deferred to a separate P-004 PR** (drop `mg_import_tool/***` from build_pkg.sh step 4a rsync; remove the cross-directory `mg_import_tool/sql/migrations/` rsync at lines 217-220; relocate the resolver-and-field-log migrations to canonical `migrations/`; add post-assembly `find ... -name 'mg_import*'` exit-43 assertion). Discovery §3.6 listed five reconciliation steps; per the operator instruction this Gap-2 PR is single-concern and the importer payload cleanup is staged for the next PR before the v1.0.3 build.

### Gap 3 — Grafana :3000 (BLOCKER for the dashboard the welcome screen promises)

- **Where it should be:** postinstall.sh as a vendored install + provisioning step.
- **What is actually there:** Zero Grafana logic in postinstall.sh — verified by `grep -i grafana installer/macos-pkg/scripts/postinstall.sh` returning no matches. The `welcome.html` text "the dashboard at `http://127.0.0.1:8080/`" suggests Grafana is up post-install but no postinstall step starts it.
- **Effect:** No Grafana on the Mini after the .pkg installs. The customer's primary surface (per the operator's vision) does not exist.

### Gap 4 — Scheduled tasks (BLOCKER for daily briefings, weekly training, deep-dives)

- **Where it should be:** postinstall.sh as a launchd plist installation step (cron is operator-only per macOS 14+ FDA constraints; launchd is the right primitive for the .pkg path).
- **What is actually there:** Zero scheduled-task logic in postinstall.sh. setup.sh `phase_10_cron()` installs 11 crontab entries (lines 815-869). The .pkg has no equivalent.
- **Effect:** No `morning_briefing.py` at 7 AM. No `daily_deep_dive.py` at 4 PM. No `weekly_train.py` Sunday midnight. No `db_maintenance.sh` at 3:30 AM. No `backup_knowledge.py` at 4 AM. No `daily_operator_review.py` at 8 AM. The operational rhythm the operator's mantras describe ("morning briefing", "deep dive", "weekly training") does not happen on a .pkg-installed Mini.

### Gap 5 — Python venv + pip install (BLOCKER for the baseline scan and every service) — RESOLVED in v1.0.3 (PR mg/v103-gap5-postinstall-venv)

- **Where it should be:** postinstall.sh as a venv-create + pip-install step.
- **What is actually there:** `step_baseline_scan` at postinstall.sh lines 392-404 executes `${MG_INSTALL_ROOT}/venv/bin/python` to fire a baseline scan — but **nothing in postinstall.sh creates `${MG_INSTALL_ROOT}/venv`.** Verified by `grep -n 'python -m venv\|virtualenv\|pip install' installer/macos-pkg/scripts/postinstall.sh` returning zero matches outside `${MG_INSTALL_ROOT}/venv/bin/python` references. Every launcher wrapper (e.g. `scanner_launcher.sh` line 16: `VENV_PYTHON="${INSTALL_ROOT}/venv/bin/python"`) checks `[[ ! -x "${VENV_PYTHON}" ]]` and exits with FATAL when missing. setup.sh `phase_06_repo_venv()` creates `python3.12 -m venv venv && pip install -r requirements.txt`.
- **Effect:** Even before the AMS/Slack credentials issue from Gap 1 fires, every launchd service exits at the first `[[ ! -x "${VENV_PYTHON}" ]]` check in its launcher wrapper. The scanner launcher's exact line: `echo "[scanner_launcher] FATAL: ${VENV_PYTHON} missing or not executable" >&2`. Every service exits 1. launchd restarts. They crash again. The baseline scan in `step_baseline_scan` itself fails because `venv/bin/python` does not exist.
- **Resolution (v1.0.3 PR mg/v103-gap5-postinstall-venv, 2026-05-04):** Added `step_create_venv` to `installer/macos-pkg/scripts/postinstall.sh`, called between `step_install_launcher_wrappers` and `step_install_plists_and_bootstrap` so launchd services see the venv at first start. The step:
  1. Resolves a Homebrew `python3.12` interpreter (Apple-supplied python3 is 3.9; refused).
  2. Creates `${MG_INSTALL_ROOT}/venv` (idempotent — re-uses an existing venv if `bin/python` is executable).
  3. Pip-installs from a vendored wheel directory at `<payload>/python-wheels/` against `<payload>/requirements.txt`, with `--no-index --find-links --only-binary=:all:` (no PyPI fallback, no source builds).
  4. Hard-fails (exit 38) if the wheels dir is empty, the requirements file is missing, or pip exits non-zero.
  - `installer/macos-pkg/scripts/build_pkg.sh` step 4e copies `${HOME}/MiningGuardian-vendor/python-wheels/` into the payload at build time; step 4f stages the canonical pin file from `installer/macos-pkg/payload-requirements.txt` (committed to git, ported from `setup.sh phase_06_repo_venv`).
  - Regression test at `tests/installer/test_postinstall_venv.sh` (24 assertions; gates ordering, offline guarantees, exit code, and shellcheck baseline).
  - Preserves the no-network-for-pip rule: the only network call at install time remains the Ollama model pull (Vision Anchor 7).

### Copy bug 1 — "four services" (welcome.html line 194, 214; conclusion.html lines 168, 188)

- welcome.html line 194: "Registers four background services" — wrong. Should be "ten" (per D-19 console becoming the 10th service in v1.0.3) or "nine" (current postinstall installs 9).
- welcome.html line 214: "the four Mining Guardian services start immediately" — same bug.
- conclusion.html line 168: "All four background services are now registered with launchd" — same.
- conclusion.html line 188: "Verifying the four services" — same.
- conclusion.html lines 190-193: code block listing 4 of 9 services — same (Copy bug 4 below names this separately as the actionable code-block fix).

### Copy bug 2 — Wrong dashboard / approval port (`:8080` / `:8081`)

- welcome.html line 216: `http://127.0.0.1:8080/` — wrong. Per `setup.sh` `phase_07_secrets` line 668, the dashboard binds `GUARDIAN_DASHBOARD_PORT=8585`. The dashboard-api plist + launcher exec the same port.
- conclusion.html line 177: `http://127.0.0.1:8080/` — same wrong port for dashboard.
- conclusion.html line 179: `http://127.0.0.1:8081/` — wrong for approval queue. setup.sh writes `GUARDIAN_APPROVAL_PORT=8686`. The approval-api plist + launcher exec `:8686`.

### Copy bug 3 — `bin/uninstall.sh` does not exist

- conclusion.html line 197: "Run `sudo /Library/Application Support/MiningGuardian/bin/uninstall.sh`" — file does not exist in the repo. Verified by `find . -name uninstall.sh -not -path './node_modules/*'` returning zero matches.
- v1.0.3 must either (a) ship a real `bin/uninstall.sh` that does `launchctl bootout` for all 10 services + removes `/Library/Application Support/MiningGuardian` + removes plists from `/Library/LaunchDaemons` + leaves `postgres-data` intact for safety, OR (b) remove the reference from conclusion.html. **D-18 mandates option (a).**

### Copy bug 4 — "Verifying the four services" code block enumerates only 4 of 9

- conclusion.html lines 190-193: lists `scanner`, `dashboard-api`, `approval-api`, `feedback-loop-daemon` only. Misses `slack-listener`, `slack-commands`, `overnight-automation`, `alerts`, `intelligence-report`. v1.0.3 conclusion.html must enumerate all 10 services (9 + console per D-19).

### Integration bug 1 — `MG_DB_PASSWORD` flow depends on out-of-band staging

- postinstall.sh `step_drop_dotenv` (lines 203-243) sources `/tmp/mg_install_env_secret` for `MG_DB_PASSWORD`. The comment on line 204 says "the .pkg build script writes it into `/tmp/mg_install_env_secret` BEFORE Installer.app runs us." But:
  - `build_pkg.sh` builds the .pkg on the operator's laptop (different machine from the Mini being installed-onto).
  - `/tmp/mg_install_env_secret` does not magically appear on the customer's Mac — it must be staged out-of-band, which is impossible for a customer who just downloaded the .pkg.
  - On any clean install, postinstall.sh fails with exit code 31: "missing per-install secret file at /tmp/mg_install_env_secret; was the pkg built correctly?"
- v1.0.3 fix: postinstall generates a random `MG_DB_PASSWORD` itself via `openssl rand -hex 32` (matching setup.sh `phase_07_secrets` line 605). No out-of-band staging.

### Integration bug 2 — `GUARDIAN_PG_USER` vs `PGUSER` mismatch

- postinstall.sh `step_drop_dotenv` line 228: `PGUSER=mg`
- setup.sh `phase_07_secrets`: `GUARDIAN_PG_USER=guardian_app`
- The Python codebase reads `GUARDIAN_PG_USER` (per `core/database_pg.py` and the dashboard-api). The .pkg writes `PGUSER` only. Even if the AMS/Slack issue (Gap 1) were fixed, the Python code would still fail to connect because it does not see `GUARDIAN_PG_USER` in the env.
- Plus: the user names disagree (`mg` vs `guardian_app`). The Postgres container created by postinstall.sh (per `lib/install_colima.sh` `provision_postgres` lines 167-171: `-e POSTGRES_USER=mg`) only has the `mg` user.
- v1.0.3 fix: postinstall writes BOTH keys with the same value (`GUARDIAN_PG_USER=mg` and `PGUSER=mg`) until the dual-naming tech debt is cleaned up. Document as tech debt in MG_UNIFIED_TODO_LIST.

### Integration bug 3 — Tailscale handling is silent

- postinstall.sh has no Tailscale logic at all. The customer might already have Tailscale up (operator pre-staged it). The customer might not. The .pkg postinstall does not check.
- For now, Tailscale is operator-side per D-9. v1.0.3 fix: postinstall surfaces a Cocoa dialog if `tailscale status` fails or returns "Logged out" — the dialog tells the operator/customer to run `tailscale up` before the system can be reached over the tailnet. Tailscale auth itself stays operator-side.

### Integration bug 4 — All customer-tunable .env keys missing

- The complete list of `.env` keys missing from the .pkg's postinstall-written `.env` (vs setup.sh's `phase_07_secrets`):
  - `AMS_BASE_URL`, `AMS_EMAIL`, `AMS_PASSWORD`, `AMS_WORKSPACE_ID`
  - `SLACK_WEBHOOK_URL`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_APP_TOKEN`, `AUTHORIZED_SLACK_USER_IDS`
  - `CATALOG_API_KEY`, `INTERNAL_API_SECRET`
  - `GUARDIAN_PG_HOST`, `GUARDIAN_PG_PORT`, `GUARDIAN_PG_USER`, `GUARDIAN_PG_DBNAME`, `GUARDIAN_PG_TEST_DBNAME`, `GUARDIAN_PG_CATALOG_DBNAME`
  - `OLLAMA_HOST`
  - `MG_DRY_RUN`, `MG_SCAN_INTERVAL`, `MG_CUSTOMER_NAME`, `AUTO_APPROVE_ENABLED`
  - `GUARDIAN_DASHBOARD_PORT`, `GUARDIAN_APPROVAL_PORT`, `GUARDIAN_INTELLIGENCE_PORT`
- v1.0.3 fix: postinstall reads the customer's pre-filled `~/Desktop/MiningGuardian.conf` (per D-18 Gap 1 resolution), validates per B-2 rules, generates the secret-only keys (`CATALOG_API_KEY`, `INTERNAL_API_SECRET`, `MG_DB_PASSWORD`) via `openssl rand -hex 32`, and writes the full `.env` matching setup.sh's `phase_07_secrets` shape.

---

## Section 6 — v1.0.3 scope and verification gate

The complete list of what v1.0.3 must do is in **D-18** (`docs/DECISIONS.md`). This section reproduces it for the audit's own self-containedness:

### v1.0.3 closes ALL of:

- **Gap 1 — Customer-info collection.** Postinstall reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf` if present, validates per B-2 rules, aborts with a Cocoa dialog if missing or invalid. Operator hands the customer a USB or AirDrop with the pre-filled `.conf`; customer drops on Desktop, double-clicks .pkg.
- **Gap 2 — Catalog DB + 320-row seed.** Postinstall creates `mining_guardian_catalog` DB in the Colima container and applies `intelligence-catalog/seed-data/seed_miner_models.sql`.
- **Gap 3 — Grafana.** Vendor `grafana.app` and provisioning yaml into the .pkg payload. Postinstall installs to `/Applications/Grafana.app`, drops provisioning into `/usr/local/etc/grafana/provisioning/`, registers as the 11th LaunchDaemon (or auto-managed by the .app), exposes `:3000`.
- **Gap 4 — Scheduled tasks.** Convert the 11 cron entries in setup.sh `phase_10_cron` to launchd `StartCalendarInterval` plists. New plist set under `installer/macos-pkg/resources/launchd/scheduled/`. Bootstrap them in postinstall after the 9 service plists.
- **Gap 5 — Python venv + pip install.** Postinstall creates `${MG_INSTALL_ROOT}/venv` and runs `pip install -r requirements.txt` from the vendored payload (no network for pip — wheels vendored).

- **Copy bug 1.** welcome.html "four background services" → "ten background services" (9 + console per D-19).
- **Copy bug 2.** welcome.html + conclusion.html dashboard URL `:8080` → correct port (`:8585` per `GUARDIAN_DASHBOARD_PORT`); approval URL `:8081` → `:8686` per `GUARDIAN_APPROVAL_PORT`.
- **Copy bug 3.** Ship a real `bin/uninstall.sh` (D-18 mandates option (a)).
- **Copy bug 4.** conclusion.html "verify these 4 services" code block updated to enumerate all 10 services (9 + console).

- **Integration bug 1.** Postinstall generates `MG_DB_PASSWORD` itself (no out-of-band staging).
- **Integration bug 2.** Postinstall writes BOTH `GUARDIAN_PG_USER` and `PGUSER` until dual-naming tech debt is cleaned.
- **Integration bug 3.** Postinstall checks `tailscale status` and surfaces a Cocoa dialog if Tailscale is not up.
- **Integration bug 4.** Postinstall reads customer Desktop `.conf` and writes the full `.env` matching setup.sh's `phase_07_secrets` shape.

### v1.0.3 verification gate (HARD, not skippable, per D-18):

1. Build, sign, notarize, staple v1.0.3 .pkg on operator's laptop.
2. Smoke-test on a clean macOS 14 VM (UTM/Tart). Required pass criteria:
   - Postgres container up, all 3 DBs created (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`).
   - `SELECT count(*) FROM hardware.miner_models;` against `mining_guardian_catalog` returns 320.
   - Grafana `:3000` reachable, returns healthy JSON, AI & Learning dashboard renders.
   - All 10 LaunchDaemons (9 + console) loaded via `launchctl list | grep miningguardian`.
   - All scheduled-task launchd plists registered.
   - `~/Desktop/MiningGuardian.conf` validation passes for valid input, fails-with-Cocoa-dialog for invalid input.
   - Console reachable at `http://127.0.0.1:8686/`, displays task list + automation toggles + approval queue (D-19).
   - Cloudflare Tunnel routes `mg.fieslerfamily.com` → console (D-19).
   - Welcome + conclusion HTML show correct service counts and ports.
   - `bin/uninstall.sh` cleanly tears down everything.
3. Only AFTER VM smoke-test passes, install on the Mini.

---

## Section 7 — Bonus findings (not in v1.0.3 critical scope, flagged for future)

These are observations the audit surfaced that are not on the v1.0.3 critical path but should be tracked:

- **The .pkg payload is ~417 MB.** Most of that is the vendored Postgres image tarball (~150 MB) and Ollama.app (~150 MB) and the LLM model is NOT vendored — it pulls at first run. Adding Grafana (.app ~120 MB) + vendored Python wheels (~50 MB for the dependency tree) brings v1.0.3 to ~600 MB. Still well under reasonable .pkg size limits.

- **Bundled vs first-run network for the LLM model.** Per `installer/macos-pkg/README.md` "Q1 hybrid ~500 MB .pkg" decision, the LLM model is the ONE network call at first install. v1.0.3 must preserve this choice — vendoring an 8 GB Qwen model would push the .pkg past distribution sanity. The "loud failure on network unreachable" pattern in `lib/install_ollama.sh` is the right safety net.

- **`mg_import_tool/` is in the .pkg payload but no LaunchDaemon surfaces it.** Per D-20, the importer stays with the operator forever. v1.0.3 audit should confirm the customer .pkg does not bundle `mg_import_tool/` (or if it does, no UI exposes it). This is a payload-content cleanup, not a critical bug.

- **`migrations/003_c5_notify_triggers.sql` is rsync'd into the payload but D-14 NOTIFY/LISTEN daemon implementation is deferred.** The migration creates triggers; the daemon that listens for the notifications is built but not yet wired into postinstall (it ships as `com.miningguardian.feedback-loop-daemon` plist but its functional value depends on the operational tables having data, which they will not on a fresh Mini for at least the first scan cycle).

- **The "Apple Developer Program enrolled and paid this afternoon ($99). Certs land in 24-48 hr" line in `docs/SESSION_LOG_2026-04-27.md` addendum #3 — those certs are already in keychain by v1.0.0, and v1.0.0 / v1.0.1 / v1.0.2 all signed cleanly per their respective release notes. Historical context, not a current issue.

- **The MG_INSTALL_LOG and MG_INSTALL_ENV files are at fixed paths (`/var/log/mining-guardian/install-postinstall.log`, `/tmp/mg_install_env`).** A re-install over the same Mac would overwrite these. Not a blocker but worth a `--force` flag in v1.0.4+.

- **Distribution.xml uses `<volume-check>` with `<allowed-os-versions><os-version min="13.0"/></allowed-os-versions>`** but the welcome screen says "macOS 13 (Ventura) or later" — these are consistent and correct, but the welcome screen should be updated to mention Tahoe explicitly since the install target is Tahoe.

- **The audit did not exercise the `lib/install_ollama.sh` model pull on a real Mac.** The pull is a single network call to `ollama.com`; per the loud-failure pattern at `_check_network` (lines 88-101), failure exits the install. This is correct but unverified at audit time. v1.0.3 smoke-test on VM exercises it.

---

## Section 8 — Reconciliation with prior decisions

- **D-16 step 4** — "Install on the customer-site Mini via .pkg double-click with screenshots at every screen (Sunday afternoon)." This step assumed the v1.0.2 .pkg was the right artifact. **D-18 amends D-16 step 4** to "Install on the customer-site Mini via v1.0.3 .pkg double-click with screenshots at every screen — when v1.0.3 is verified green on a clean Mac VM." The Monday-morning sequencing in D-16 (VPS decommission, ROBS-PC container shutdown) is deferred until v1.0.3 ships.

- **`docs/INSTALL_PATHS_2026-05-02.md`** — its "viewer-only" framing for the .pkg path is factually wrong per this audit. The .pkg path is partial-operations, not viewer-only. **D-18 supersedes** that doc with `docs/INSTALL_PATHS_2026-05-03.md`. The 2026-05-02 version is retained for historical context with a SUPERSEDED notice at the top.

- **D-13** — "16 GB → llama3.2:3b; 24 GB+ → qwen2.5:14b-instruct-q4_K_M." This decision is correctly implemented in the .pkg postinstall path via `lib/detect_ram.sh`. No change.

- **D-14** — "Both DBs in same Postgres 16 container on the Mini post-cutover." The .pkg postinstall creates the Postgres container correctly. The "both DBs" part requires the catalog seed (Gap 2) to land — v1.0.3 closes that.

- **D-15** — "Every session ends with a HANDOFF_<DATE>.md." Active. Today's HANDOFF_2026-05-03.md gets an EOD update in the same PR as this audit.

- **D-17** — "Monthly catalog sync deferred until post-cutover." Unchanged. v1.0.3's catalog seed at install time is the day-one snapshot; the recurring sync per D-17 still defers until Mini-verified-green.

---

## Section 9 — Closing assessment

The v1.0.2 .pkg is competently built (signed, notarized, stapled, Apple-blessed) but materially incomplete. It would install successfully and present a green "completed" dialog while leaving the Mini in a non-functional state. That is the worst-case outcome for the operator's customer-experience vision: apparent success, real silence.

The fix is straightforward (Section 6). v1.0.3 closes every gap with code that already exists in `scripts/setup.sh`'s 15 phases — most of v1.0.3's postinstall.sh is "port the equivalent setup.sh phase into postinstall.sh, with launchd plists replacing cron entries." The vision is right; the v1.0.2 implementation does not yet match it.
