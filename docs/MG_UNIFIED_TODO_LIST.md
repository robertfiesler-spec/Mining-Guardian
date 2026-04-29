# Mining Guardian — Complete Unified To-Do List
**Compiled:** Sunday, 2026-04-26 17:35 EDT (after Sunday sprint complete, 5 PRs deployed)
**Sources merged:**
- Pre-prod audit findings (2026-04-24) — 5 CRITICAL + 8 HIGH + 7 NICE-TO-HAVE
- Security audit findings (2026-04-24) — 14 findings (S-1 through S-14)
- Locked decisions (`mg_pre_prod/DECISIONS.md`)
- OpenClaw audit (2026-04-23)
- 21-cluster gap list from CRIT manifests
- Sunday sprint outcomes (5 PRs merged)
- User backlog items (web GUI, beginner docs, Grafana provisioning)

---

## Status Legend

| Symbol | Meaning |
|---|---|
| ✅ | DONE — verified in production |
| 🟢 | DONE — code merged but not yet deployed/verified |
| 🟡 | PARTIAL — some sites fixed, others remain |
| 🔴 | OPEN — not yet started |
| ⏸ | BLOCKED — waiting on dependency |
| 🚫 | OUT OF SCOPE — explicitly deferred or removed |

---

# SECTION 1 — Already Done (Sunday Sprint + Earlier Weekend Work)

| Item | Source | Status | Notes |
|---|---|---|---|
| Rename Mining-Gaurdian → Mining-Guardian (289 typos) | PR #1 | ✅ | Merged commit `36942da` |
| CR-4 Postgres shim | PR #2 | ✅ | Merged commit `ab9f5d2`, 0 AttributeErrors holding |
| CR-2 hashrate parser (safe N/A / "80.5%") | PR #3 | ✅ | Merged `7e97fc0`, 11-case unit test passing, deployed |
| CR-5 Phase 1: `_auto_create_missing_tickets` text<timestamp cast | PR #4 | ✅ | Merged `bcfbd58`, deployed |
| CR-5 Phase 1: outcome_checker.py rewrite (CR-3 actually closed here) | PR #4 | ✅ | 9 backlogged outcome evaluations unlocked, was silent since Postgres migration |
| CR-5 Phase 1B: 3 sibling Postgres GROUP BY violations | PR #5 | ✅ | Merged `476ef30`, deployed clean |
| Dead branch cleanup (4 SHA-pinned dry-run, all deleted) | Track A | ✅ | f1b3cdc, e5626c2, e46db9b, c2ca55c |

**Bottom line of weekend so far:** 5 PRs merged, fleet running clean, outcome feedback loop alive after silent breakage since 2026-04-23.

## 1.1 Tuesday 2026-04-28 — Customer docs + .pkg installer branding (PR #54)

| Item | Status | Notes |
|---|---|---|
| Setup Manual PDF (12 pp) | 🟢 | `docs/customer/MiningGuardian_Setup_Manual.pdf` — install walkthrough, USB + GitHub paths, verify, first launch, troubleshooting |
| Program Instructions PDF (10 pp) | 🟢 | `docs/customer/MiningGuardian_Program_Instructions.pdf` — daily-usage walkthrough |
| Brochure PDF (4 pp) | 🟢 | `docs/customer/MiningGuardian_Brochure.pdf` — features + benefits + iPhone-app coming-soon callout |
| ~~Terminal-wizard brand toolkit~~ REMOVED | ⚪ | Was based on rejected pre-D-13 architecture. Real installer is the signed/notarized native macOS .pkg shipped today (`MiningGuardian-1.0.0-978ff61126ea.pkg`, sha `c7030d69…65f8`, notarization `2c4130a4`) |
| .pkg branding: style `welcome.html` + `conclusion.html` (navy + BTC orange + Apple system fonts) | 🟢 | `installer/macos-pkg/resources/` — done in PR #54, navy `#0A1428` + BTC orange `#F7931A` + electric blue `#3DA9FC`, no remote font CDN |
| .pkg branding: add `background.png` (Installer.app sidebar — already referenced in `Distribution.xml` line 35) | 🟢 | 620×1111 PNG-8 (305 KB), Hero shield + crossed pickaxes + MINING GUARDIAN wordmark |
| Rebuild + re-sign + re-notarize after branding lands | 🔴 | `make pkg` on Robert's Mac (Developer ID Installer Robert Fiesler ARJZ5FYU94 + notarytool) |
| Optional: custom Finder icon for the `.pkg` file (icns) | 🔴 | Cosmetic — only shows in Finder before install |
| Replace v1.0 dev screenshots with production UI shots | 🔴 | After dashboard ships; rebuild via `customer_docs/build_*.py` |
| Update PDFs when iPhone app ships | 🔴 | Search build scripts for "Coming soon"; refresh callouts |

**End-of-day status (4:15 PM CDT):** PR #54 is OPEN, MERGEABLE, CLEAN — single rebased commit `a2b1261` on top of main `9e24a94`. Eight files: 3 customer PDFs + `docs/customer/README.md` + `welcome.html` + `conclusion.html` + `background.png` + this TODO update. Awaiting merge + `make pkg` rebuild on Robert's Mac. The currently-distributed `.pkg` (`MiningGuardian-1.0.0-978ff61126ea.pkg`, sha `c7030d69…65f8`) on the USB stick "MG Install" and on the GitHub Release is the **unbranded** build — it stays in place until the rebuild produces a new `.pkg`, then we replace the file on the USB (do not erase) and clobber-upload to the Release. See `docs/RUNBOOK_PKG_REBUILD.md` (added in this PR) for paste-along blocks A–H.


---

# SECTION 2 — Block-Ship Security Items (CRITICAL — must close before customer goes live)

These are the **gates** between today and a real customer install. Not all need to land before the Mac Mini personal cutover, but ALL need to land before this code ever runs on a paying customer's hardware.

## 2.1. S-2 — Revoke leaked GitHub PAT 🔴 EMERGENCY

- **Where:** `docs/SECURITY.md:80` — token `<REDACTED — revoked 2026-04-24, full literal scrubbed 2026-04-27>` is still committed in cleartext
- **Action:** One-click revoke at https://github.com/settings/tokens, then commit `[REDACTED — token revoked YYYY-MM-DD]` over the literal
- **Effort:** 2 minutes
- **Why it's #1:** Anyone who reads the repo has the token. If the repo is ever public or leaked, it's already compromised. **Do this within the hour.**

## 2.2. S-1 / CRIT-1 — Purge `MiningGuardian2026!` from 29 source locations 🟡 PARTIAL

- **Where:** Currently still 29 hits in live `Mining-Guardian/` repo across:
  - `intelligence-catalog/catalog-api/catalog_api.py:45`
  - `intelligence-catalog/docker-compose.yml:34`
  - `mg_import_tool/mg_import.py` (~24 sites)
  - `scripts/migrate_to_postgres.py:29`
  - HTML form `value=` attribute at `mg_import.py:5381`
- **Action plan:** CRIT-1 manifest at `mg_pre_prod/manifests/CRIT-1_password_purge_manifest.md` — already specifies the surgical patch
- **Decision locked:** New password is `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` (192 bits entropy). Goes into env files only. HTML form value becomes `""`.
- **Effort:** 2-3 hours
- **Blocks:** Mac Mini cutover (running with leaked password = bad day-1 customer story)

## 2.3. S-3 — `mg_import` Flask app: no auth + binds to 0.0.0.0 🔴 OPEN

- **Where:** `mg_import_tool/mg_import.py:6163, 6178`
- **Risk:** Any LAN device can hit `POST /api/run-sql` and run `DROP DATABASE`
- **Fix path (per CRIT-3 manifest):**
  1. Default bind `127.0.0.1`, `--allow-host` flag for opt-in
  2. Startup-generated session token written to local file, required in header
  3. 8-hour session TTL (`MG_IMPORT_SESSION_TTL_SECONDS=28800`) — locked
- **Effort:** 1-2 hours
- **Blocks:** Anything that runs `mg_import` on the Mac Mini

## 2.4. S-4 — Postgres credentials passed in HTTP GET query strings 🔴 OPEN

- **Where:** `mg_import_tool/mg_import.py:3618-3619, 3922-3923, 4285-4286, 4328-4329`
- **Risk:** Password lands in every web log, browser history, proxy cache
- **Fix:** Drop all `request.args.get('password', ...)` calls. Use `DB_PASSWORD` env var only.
- **Effort:** 30 minutes
- **Note:** Folds into CRIT-1 cleanup naturally

## 2.5. S-6 — Catalog API default key is publicly known string 🔴 OPEN

- **Where:** `intelligence-catalog/catalog-api/catalog_api.py:46`, `ai/catalog_context.py:29`
- **Symptom:** `os.getenv("CATALOG_API_KEY", "CHANGE_ME_TO_A_REAL_SECRET")` silently authenticates if env var unset
- **Fix path (per CRIT-6 manifest):**
  1. Crash-on-startup if key is missing or default
  2. `setup.sh` generates unique token via `openssl rand -hex 32`, writes to `.env`
  3. Use `hmac.compare_digest()` (also closes S-12)
- **Effort:** 30 minutes

---

# SECTION 3 — Non-Block-Ship Security (HIGH/MEDIUM, before Mac Mini if time, otherwise post-cutover)

## 3.1. S-5 — Catalog API health endpoint leaks schema layout 🔴 OPEN
Add `Depends(verify_token)` OR strip `schemas` field from unauthenticated response. **15 min.**

## 3.2. S-7 — All systemd services run as root 🔴 OPEN
Create dedicated `miningguardian` user, move workdir from `/root/` to `/opt/mining-guardian/`.
Translates to LaunchAgents on Mac Mini — should be designed in NOW so Mac install doesn't bake "run as you" into the model. **1-2 hours.**

## 3.3. S-8 — `intelligence_report_api.py`: wildcard CORS + 0.0.0.0 binding 🔴 OPEN
Change `allow_origins=["*"]` → explicit allow-list, `host="0.0.0.0"` → `127.0.0.1`, methods to `["GET"]`. **30 min.**

## 3.4. S-9 — Auradine client: `admin/admin` defaults + `verify=False` global 🔴 OPEN
- Remove `admin` default for `AURADINE_PASS` — fail loud on missing env
- Cert pinning for self-signed Auradine certs (longer-term)
- **30 min for fail-loud, 2-3 hours for pinning.**

## 3.5. S-10 — Catalog API global exception handler leaks `str(exc)` 🔴 OPEN
Strip `error: str(exc)` from response, keep only `error: "Internal server error"`. Log full exc server-side already done. **15 min.**

## 3.6. S-11 — Path traversal in `/reports/{filename}` 🔴 OPEN
Add resolved-path containment check against `reports_dir`. Block null-byte and `..` patterns. **20 min.**

## 3.7. S-12 — Token comparison uses `!=` (timing attack) 🔴 OPEN
Replace `parts[1] != API_KEY` with `not hmac.compare_digest(parts[1], API_KEY)`. **5 min.** (Closes alongside S-6.)

## 3.8. S-13 — Hardcoded Tailscale IPs (100.110.87.1) as fallback 🟡 PARTIAL
- 12 hits remain in code (down from earlier — partially addressed)
- Mac Mini cutover changes context: those become `localhost` since Ollama/catalog move to Mac
- **30 min** as part of `.env` flip during install

## 3.9. S-14 — `setup.sh` uses unmasked `read` for AMS password 🔴 OPEN
Add `-s` flag to all password prompts. Echo newline after. **5 min.**
**This is part of the installer rewrite anyway** — folds in.

---

# SECTION 4 — Catalog / Database Critical Path (the big one)

This is the non-security half of the audit. It's about whether AI actually has data to think with.

> ## ✅ Reconciliation note — 2026-04-29 (Wednesday)
>
> All four C-items below (C4, C1, C3, C5) are **CLOSED**. They were shipped Monday 2026-04-27 (PRs #13, #15, #16, #22) but the corresponding rows in this file were never flipped. Per `docs/SESSION_LOG_2026-04-27.md` line 402: *"Wednesday is now empty. The original Wednesday roadmap items — four manufacturer parsers, the C5 feedback loop, and the catalog API verification — all landed on Monday."*
>
> See **§ 4.6 below** for closure evidence per item, and `docs/RUNBOOK_BUCKET_3_RECONCILIATION_2026-04-29.md` for the verification commands an operator can run on the live ROBS-PC catalog DB to confirm the 317-row state.
>
> The historical text of §§ 4.1–4.5 is preserved verbatim below for audit trail per the over-document doctrine.

## 4.1. C4 — Run seed SQL against catalog Postgres ✅ DONE 2026-04-27 (PR #13, merge sha `d9aca73`)
- **Symptom (historical, 2026-04-26):** `seed-data/seed_miner_models.sql` was never executed. 313-row baseline seed missing.
- **Impact (historical):** 208 catalog tables, only 5 have data. AI sees nothing.
- **Fix:** One `psql -f` invocation. Truly 30 seconds.
- **Effort:** 30 seconds. Unblocks C1.
- **What shipped (PR #13, 2026-04-27):** `scripts/seed_catalog.sh` — idempotent wrapper around `seed_miner_models.sql` with row-count guard, schema-presence check, post-flight verification, `--force` escape hatch. Live catalog DB verified at **317 rows = 313 seeded + 4 base** (`docs/SESSION_LOG_2026-04-27.md` L290, L658).

## 4.2. C1 — Catalog split-brain: enrichment writes JSON, API reads Postgres ✅ DONE 2026-04-27 (PR #15, merge sha `e0ba593`)
- **Symptom (historical):** Every AI lookup returns empty. 21 SQL queries, 0 rows.
- **Decision (locked, D-12):** Path A — dual-write Postgres + JSON with Postgres-as-truth.
- **Effort:** 4-6 hours
- **Blocks:** All AI quality. Until this is fixed, every Qwen analysis is uninformed.
- **What shipped (PR #15, 2026-04-27):** `intelligence-catalog/db/dual_writer.py` + Postgres-as-truth dual-write intake; psycopg2 UUID adapter registered in PR #16 follow-up. Catalog API now reads Postgres (verified by `intelligence-catalog/tools/verify_catalog_api_coverage.py`).

## 4.3. C3 — 5 background watchers write JSON, never to catalog DB ✅ DONE 2026-04-27 (PR #16, merge sha `817973e`)
- Aggregator (4cc981c0), Manufacturer (920d0231), Firmware (aa676933), Community (c8c4678d), Deep Enrichment (ebb3af70)
- All save to `cron_tracking/<watcher>/latest_findings.json` — these JSON files don't move to the Mac Mini
- **Fix:** Rewrite each watcher to UPSERT into catalog Postgres
- **Effort:** 3-4 hours
- **Tied to C1 fix path.**
- **What shipped (PR #16, 2026-04-27):** `intelligence-catalog/watchers/manufacturer_watcher.py` framework + per-manufacturer parsers for **Bitmain, MicroBT, Canaan, Auradine, Bitdeer** (5 of 5 — the previous 5-watcher list above was the *old* JSON-cron-tracking architecture; the new architecture replaces those with one per-manufacturer parser dispatched by `manufacturer_watcher.py`). Live watcher run produced 10 model proposals, 42 alias proposals, 1 manufacturer proposal in `staging.*` (`docs/SESSION_LOG_2026-04-27.md` L289). Idempotent re-run produced zero new rows.

## 4.4. C5 — Operational→Catalog feedback loop missing ✅ DONE 2026-04-27 (PR #22, merge sha `7105632`)
- Layer 5 of the 6-layer plan.
- No code mines `action_audit_log` / `llm_analysis` / `miner_restarts` to upsert `ops.failure_patterns`, `market.war_stories`, `hardware.model_known_issues`
- **Effort:** 2-3 hours
- **Can slip post-Mac-Mini.**
- **What shipped (PR #22, 2026-04-27):** `intelligence-catalog/db/feedback_loop.py` (725 LOC) + 13 unit tests in `intelligence-catalog/db/tests/test_feedback_loop.py`. Three sync paths (`sync_action_audit_to_failure_patterns`, `sync_llm_analysis_to_war_stories`, `sync_miner_restarts_to_known_issues`) all fail-soft and orchestrated by `run_full_feedback_loop(dry_run=False)`. Every C5 write attributed to source `bobby_operational` (`a0000000-0000-0000-0000-00000000000f`, tier2). Daemon launcher fix shipped 2026-04-29 in PR #80 (Bucket 7.5).

## 4.5. C2 — Installer does not install Postgres / Docker / catalog API ✅ DONE 2026-04-29 (Bucket 6 — PRs #74/#75/#76/#77/#79)
**This is the installer rebuild itself. See Section 7.** Closed today: `scripts/setup.sh` v2 (PR #75), 5 LaunchDaemons + 8 launcher wrappers (PR #74), restore-from-snapshot (PR #76), Grafana provisioning (PR #77), DEPLOYMENT_CHECKLIST rewrite (PR #79).

## 4.6. Verification on the live catalog DB (operator step, runtime)

The code-side work is closed. The remaining step is **runtime verification on the actual ROBS-PC catalog DB** (and later on the customer Mac Mini), which Bobby runs once at his machine. Commands and expected outputs are captured in `docs/RUNBOOK_BUCKET_3_RECONCILIATION_2026-04-29.md`. Summary of what to confirm:

- `hardware.miner_models` row count = **317** (313 seed + 4 base)
- `hardware.manufacturers` = **16**
- `knowledge.sources` = **23**
- `mg.model_family_aliases` = **1,494**
- `hardware.model_aliases` = **12,852**
- `bash scripts/seed_catalog.sh` returns exit 0 with the message `"Already seeded (>= 313 rows). Skipping."` (idempotency proof)
- `pytest intelligence-catalog/db/tests/test_feedback_loop.py` — 13/13 pass
- `pytest intelligence-catalog/db/tests/test_dual_writer.py` — all pass
- `pytest intelligence-catalog/watchers/tests/` — all 5 parser test files pass

After Bobby runs and confirms, this section can be closed entirely (move to SECTION 1 "Already Done" or archive into a closing note). Until then, leaving §§4.1–4.5 here as DONE-with-verification-pending.

---

# SECTION 5 — OpenClaw Removal (HIGH-10 from audit, N4 from findings)

## 5.1. Why now (post Sunday sprint, before Mac Mini install)

- OpenClaw is **silent no-op already** — every `send_scan()` returns immediately because `webhook_url=None`
- Removing it has zero behavioral impact, just deletes dead code
- It IS still referenced in 10 files (currently in code, not just archive)
- Don't migrate dead code to the Mac Mini

## 5.2. The exact removal checklist (from `mg/docs/OPENCLAW_AUDIT_2026-04-23.md`)

🔴 **All of these are open** (just verified — `OpenClaw` strings still present in 10 active source files):

1. 🔴 `cd /docker/openclaw-5b5o && docker compose down` (VPS, kills the dead container)
2. 🔴 Optional: `docker volume rm` on openclaw volumes
3. 🔴 Edit `core/mining_guardian.py`:
   - Remove `from notifiers.openclaw_notifier import OpenClawNotifier` (line ~74)
   - Remove `self.notifier = OpenClawNotifier(config.openclaw_webhook_url)` (line ~84)
   - Remove `openclaw_webhook_url` key from example config template (line ~2608)
4. 🔴 Edit `core/overnight_automation.py`:
   - Remove `notify_openclaw()` function (lines 375-405)
   - Remove call site at line 477
5. 🔴 Delete `notifiers/openclaw_notifier.py`
6. 🔴 Edit `core/models.py`: remove `openclaw_webhook_url` field from config dataclass (lines 63, 95)
7. 🔴 Delete `tests/test_openclaw_notifier.py`
8. 🔴 Update `tests/conftest.py` if it references OpenClaw
9. 🔴 Edit `api/slack_approval_listener.py` docstring — drop the "Socket Mode is owned by OpenClaw" note (no longer true)
10. 🔴 Run tests (should still pass — nothing real used the notifier)
11. 🔴 Commit: `refactor: remove dead OpenClaw integration`
12. 🔴 Delete `deploy/openclaw-skills/` directory (catalog-bridge inside it)

## 5.3. Optional follow-up (NOT for this PR)

- Switch `slack_approval_listener.py` and `slack_command_handler.py` from REST polling → Bolt/Socket Mode (cleaner now that OpenClaw isn't holding the socket).
- **Effort:** 4-6 hours separately. Defer.

## 5.4. Effort + when

- **Effort:** 1.5-2 hours for the surgical removal + tests + commit
- **When:** Tomorrow (Monday build day). Best done BEFORE installer rebuild so installer doesn't include OpenClaw refs.

---

# SECTION 6 — Slack Connection Audit (your specific call-out)

This wasn't a separate section in the audit doc but the user asked. Here's what's wired up now and what needs review:

## 6.1. Active Slack pieces in production

| Component | File | Port | Status | Concerns |
|---|---|---|---|---|
| Slack approval listener | `api/slack_approval_listener.py` | — | ✅ running | Polling-based (legacy from OpenClaw co-existence). Switch to Socket Mode after S5 OpenClaw removal. |
| Slack command handler | `api/slack_command_handler.py` | — | ✅ running | HMAC signature verification ✅, replay-attack window ✅ (per audit S-clean section) |
| Slack approval API | `api/approval_api.py:8686` | 8686 | ✅ running | `/slack/actions` correctly verifies HMAC + 5-min replay window ✅ |
| Slack notifier | `notifiers/slack_notifier.py` | — | active | Webhook-based, sends scan summaries |

## 6.2. What's clean (audit confirmed)

- ✅ HMAC-SHA256 signature verification on `/slack/actions`
- ✅ Replay-attack protection (5-minute timestamp window)
- ✅ Constant-time comparison (`hmac.compare_digest()`) for Slack signatures
- ✅ Approval API verify_internal() is fail-closed (no INTERNAL_API_SECRET = reject all)

## 6.3. What's open

- 🔴 `SLACK_BOT_TOKEN`, `SLACK_WEBHOOK_URL`, `SLACK_SIGNING_SECRET`, `SLACK_APP_TOKEN` all live in `.env` — must be customer-specific on Mac Mini, not copied from VPS
- 🔴 `AUTHORIZED_SLACK_USER_IDS` env var must be customer-specific (today it has Bobby's ID)
- 🔴 No rate-limiting on Slack endpoints — a flooded slash-command storm could DoS approval API. **NICE-TO-HAVE.**
- 🔴 Slack listener docstring still says "Socket Mode is owned by OpenClaw" — false after Section 5 lands
- 🔴 Bolt/Socket Mode migration (post-OpenClaw cleanup)

## 6.4. Action items

| # | Item | Effort |
|---|---|---|
| 6a | Make installer prompt for fresh Slack creds (don't copy from VPS) | 30 min (part of installer rewrite) |
| 6b | Update `AUTHORIZED_SLACK_USER_IDS` per-customer | 5 min (installer prompt) |
| 6c | Remove false OpenClaw docstring after Section 5 | 2 min |
| 6d | (Optional, later) Bolt/Socket Mode migration | 4-6 hours, defer |

---

# SECTION 7 — Installer Rebuild (the build day target)

## 7.1. Current state of `scripts/setup.sh` (177 lines)

🔴 **Severely out of date.** Misses:

- ❌ Postgres install + DB creation
- ❌ Ollama install + 14b model pull
- ❌ Catalog DB / catalog API
- ❌ 7 of 8 services (only main mining-guardian.service)
- ❌ Cron jobs (all 9)
- ❌ Grafana
- ❌ Tailscale (optional)
- ❌ S-7 hardening (dedicated user)
- ❌ S-14 fix (`read -s`)
- ❌ S-6 fix (generate API key, write to `.env`)
- ❌ References `mining_guardian.py` at repo root — moved to `core/mining_guardian.py`
- ❌ References `com.bixbit.mining-guardian.plist` template that doesn't exist
- ❌ Only 6 pip packages — repo needs 49

## 7.2. Installer v2 — required functionality

| Phase | What it should do |
|---|---|
| 1. Pre-flight | Check macOS 14+, arm64, 16+ GB RAM, ≥50 GB free, on miner LAN |
| 2. Customer info | Site name, AMS creds (with `-s` masked), Slack creds, scan interval, install mode (dry-run default) |
| 3. Brew + deps | Install Homebrew, postgresql@16, python@3.12, git, ollama, grafana, tailscale |
| 4. Postgres | Create `guardian_app` user, 3 databases (`mining_guardian`, `mining_guardian_test`, catalog), apply schemas |
| 5. Catalog seed | Run `seed-data/seed_miner_models.sql` (closes C4) |
| 6. Repo + venv | Clone repo, create venv, `pip install -r requirements.txt` (49 packages) |
| 7. Secrets | Generate new `MG_DB_PASSWORD`, generate `CATALOG_API_KEY` via openssl, write `.env` chmod 600 |
| 8. Ollama | Pull `qwen2.5:14b-instruct-q4_K_M`, smoke-test |
| 9. LaunchAgents | Render 8 plists from templates with `$HOME` / `$USER` substitution, `launchctl load` each |
| 10. Cron | Install all 9 jobs, prompt user to grant Full Disk Access to `/usr/sbin/cron` |
| 11. Grafana | Restore `grafana.db` if migration data present, otherwise blank install + provision dashboards |
| 12. Tailscale (opt) | `tailscale up` interactive |
| 13. Smoke test | Test scan, fetch AMS miners, verify all 8 services responding |
| 14. Post-install | Slack ping, `dry_run: true` confirm, cheat-sheet of common commands |
| 15. Optional restore | `--restore-from-snapshot=<tarball>` flag for Mac-Mini-from-VPS migration |

## 7.3. Subtasks for build day

| # | Item | Effort |
|---|---|---|
| 7a | Inventory current `setup.sh` vs reality (Track I-1) | 30 min |
| 7b | Write 8 plist templates in `deploy/launchd/` | 1 hour |
| 7c | Rewrite `setup.sh` (Track I-2) | 4-5 hours |
| 7d | Build `restore_from_snapshot.sh` (separate) | 1.5 hours |
| 7e | Sandbox test on fresh user account / macOS VM | 1 hour |
| 7f | ✅ DONE 2026-04-29 (PR — Bucket 6f) — `DEPLOYMENT_CHECKLIST.md` rewritten for Mac-Mini era (410 lines, 7 sections: prerequisites, install .pkg, post-install state checks, restore-from-snapshot path, operator sign-off, common failure modes, rollback plan + Appendix A preserves the April 15 VPS-era checklist verbatim). Verify: `wc -l DEPLOYMENT_CHECKLIST.md` (→ 410) and `grep -c 'launchd\|launchctl\|brew services' DEPLOYMENT_CHECKLIST.md` (→ ≥7 macOS-era references). Will be filled in with observed-reality values from sandbox-test exec (PR Bucket 6e). | ✅ |
| 7g | Add Grafana provisioning yaml (datasource + dashboards) | 1.5 hours |

**Total build day: ~10-11 hours, may bleed into Tuesday morning.**

---

# SECTION 8 — Orphan Code / Dead Stubs (audit findings H1, H3, N1, N2)

## 8.1. Confirmed dead

| Item | Source | Action |
|---|---|---|
| `chip_readings` table — 0 reads, 0 writes | H1 | 🔴 Drop OR wire to AMS per-chip extraction. Recommend drop. |
| `log_collection_failures` table — 0 reads, 0 writes | H3 | 🔴 Drop OR wire. Recommend drop. |
| `s19jpro_overheat_tracking` — model-specific hack | N2 | 🔴 Promote to generic `model_overheat_tracking` OR fold into `ops.failure_patterns` |
| `guardian.db` (0 bytes) | observed | 🔴 Delete the empty SQLite stub at repo root |
| `databases/*.db` — empty stubs | observed | 🔴 Delete (or move to `archive/sqlite_stubs/`) |
| `migrations/migrate_sqlite_to_postgres.py` | DECISIONS.md #6 | 🟢 Has guard already (raise unless `MG_ALLOW_MIGRATION=1`). Defer deletion to post-Mac-Mini. |

## 8.2. Underused (audit-flagged but live)

| Item | Source | Action |
|---|---|---|
| `llm_analysis` (6r/3w, 1008 rows) | H4 | 🔴 Add precision/recall dashboard + prompt drift detection. Defer post-Mac-Mini. |
| `miner_baselines` (4r/3w, VPS populated, catalog 0) | H5 | 🔴 Wire to cross-miner anomaly detection. Layer 3 of the 6-layer plan. |
| `pending_operator_reviews.json` | H6 | 🔴 Promote from JSON to DB-backed table. **Defer.** |
| `discovery_log` not piped to enrichment | H7 | 🔴 Build promotion cron from `acknowledged=0` → deep enrichment queue. |
| `knowledge.freshness_log` empty | H8 | 🔴 Wire freshness writes from enrichment watchers. |
| `alert_listener_seen` / `cooldown` (1r/1w) | N1 | 🟢 Probably OK — leave alone. |
| 123 empty `knowledge.research_*` tables | N5 | 🟢 Auto-create on import. Fine to leave. |
| 4 versions of catalog schema in repo | N6 | 🔴 Consolidate into one canonical schema before Mac Mini |
| Grafana intelligence report uses JSON catalog | N7 | 🔴 Re-point to Postgres after C1 lands |

## 8.3. Effort

- Drop dead stubs + clean up 4 schema versions: **2 hours**
- Wire underused tables (H5, H7, H8): **3-4 hours each, defer**
- 4 schema consolidation: **2 hours, do before Mac Mini**

---

# SECTION 9 — Audit Decisions Already Locked (DECISIONS.md)

These are the **answers**, not the work. Listed for reference so nothing contradicts them:

| # | Decision | Implementation Status |
|---|---|---|
| 1 | New `MG_DB_PASSWORD` = `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` | 🔴 Pending CRIT-1 apply |
| 2 | `auto_approve_enabled` defaults to **False** | ⏸ Status unknown — needs grep verify |
| 3 | `outcome_checker.py` → full rewrite via psycopg | ✅ Done in PR #4 |
| 4 | mg_import session TTL = 28800s (8 hours) | 🔴 Pending CRIT-3 apply |
| 5a | mg_import HTML password input value = `""` | 🔴 Pending CRIT-1 |
| 5b | `docs/SESSION_HANDOFF_2026-04-24.md` keeps literal + adds top note | 🔴 Pending |
| 5c | Run fresh `grep` before CRIT-1 apply | 🟢 Process step (do at apply time) |
| 6 | `migrate_to_postgres.py` raises on import unless `MG_ALLOW_MIGRATION=1` | ⏸ Needs verify in current code |

---

# SECTION 10 — User Backlog (your direct call-outs from this weekend)

| # | Item | Source | Status |
|---|---|---|---|
| 10.1 | Web GUI on `approval_api.py:8686` for approve/deny with explanation field | Sunday user msg | 🔴 Backlog (not for build day) |
| 10.2 | Mode selector: Full Auto / Semi Auto / Manual on the same web GUI | Sunday user msg | 🔴 Backlog |
| 10.3 | Grafana provisioning section in installer | Sunday user msg | 🟢 In Section 7.2 phase 11 |
| 10.4 | Setup Manual (beginner-friendly, with images) | Sunday user msg | 🔴 Post-Mac-Mini |
| 10.5 | Program Instructions doc (beginner-friendly) | Sunday user msg | 🔴 Post-Mac-Mini |
| 10.6 | 8-10 page Product Brochure (with images) | Sunday user msg | 🔴 Post-Mac-Mini |

---

# SECTION 11 — Recommended Execution Order

This is what I'd tackle, in this order, if you asked me to drive it:

## 🔥 Tonight (within 1 hour)
1. **S-2** Revoke GitHub PAT (2 min, click)
2. Sleep on the rest

## 📅 Monday 2026-04-27 — Build Day (8-10 hours)
3. **OpenClaw removal** (Section 5) — surgical PR, ~1.5 hr
4. **CRIT-1 password purge** (S-1, S-4) — ~3 hr
5. **CRIT-3 mg_import auth** (S-3) — ~1.5 hr
6. **CRIT-6 catalog API hardening** (S-5, S-6, S-12) — ~1 hr
7. **C4 seed catalog** (30 sec) + verify 313 rows present
8. Start **installer rewrite** (Section 7) — ~4 hr (will spill to Tuesday)

## 📅 Tuesday 2026-04-28 — Installer + Sandbox
9. **Finish installer rewrite** — ~3 hr
10. **Sandbox test** on fresh macOS user account or VM — 1 hr
11. **Plist templates** for 8 services — 1 hr
12. **`restore_from_snapshot.sh`** script — 1.5 hr
13. **Update DEPLOYMENT_CHECKLIST.md** — 30 min

## 📅 Wednesday 2026-04-29 — Real Install on Mac Mini
14. Run installer in customer mode with your existing creds
15. Document every paper cut as we go
16. Restore VPS data via `restore_from_snapshot.sh`
17. Live verification, swap DNS / cron / Slack notifier targets to Mac
18. Begin 24-48 hr burn-in

## 📅 Thursday-Friday — Burn-in + remaining HIGH/MEDIUM
19. **S-7** dedicated service user (now we know LaunchAgent design)
20. **S-8** intelligence_report_api CORS + binding
21. **S-9** Auradine `admin/admin` purge
22. **S-10** exception sanitization
23. **S-11** path traversal fix
24. **S-13** remove remaining 12 Tailscale IP fallbacks
25. **S-14** `read -s` (probably already in installer rewrite)

## 📅 Following week — Catalog + AI loop work
26. **C1** catalog split-brain (4-6 hr)
27. **C3** rewrite 5 watchers to write to catalog DB (3-4 hr)
28. **C5** operational→catalog feedback loop (2-3 hr)
29. **N6** consolidate 4 catalog schema versions
30. **H5/H7/H8** wire underused tables

## 📅 Backlog (no urgency)
31. Web GUI with mode selector (10.1, 10.2)
32. Beginner docs (10.4, 10.5, 10.6)
33. Bolt/Socket Mode migration (post-OpenClaw)
34. CR-7 password purge in env files (BLOCKED until DB rotation)
35. Audit ↔ main reconciliation (29 vs 212 commit divergence)

---

# SECTION 12 — Total Effort Estimate

| Phase | Hours |
|---|---|
| Tonight | 0.05 (just the revoke) |
| Monday build day | 8-10 |
| Tuesday | 6-7 |
| Wednesday install + verify | 6-8 |
| Thursday-Friday hardening | 4-6 |
| Following week catalog/AI loop | 12-15 |
| Backlog (open-ended) | 20+ |

**Critical path to a real Mac Mini install:** ~22-25 hours of focused work over Mon-Wed.
**Critical path to "ship to a paying customer":** add another 10-15 hours for HIGH/MEDIUM security + catalog data plane.

---

# SECTION 13 — What's Explicitly Out of Scope

| Item | Why |
|---|---|
| 🚫 OpenClaw branch / OpenClaw work | User said "OUT OF SCOPE" repeatedly |
| 🚫 Cloud-only services | User said "stay local, stay away from cloud-only" |
| 🚫 Non-SHA256 miners | User said "Bitcoin SHA-256 miners ONLY" |
| 🚫 Calling SQLite "live" anywhere | User explicitly forbade |
| 🚫 The word "scrape" / "crawl" | User explicitly forbade |
| 🚫 Audit ↔ main full reconciliation (29 vs 212 commits) | Defer until post-Mac-Mini stability |
| 🚫 CR-7 password purge from env files | BLOCKED until DB rotation |

---

**End of unified list. This is the canonical to-do for everything still open across security, database, OpenClaw, Slack audit, orphan code, installer, and backlog.**

---

# SECTION 14 — Update 2026-04-28 (Tuesday) — Bucket 3 Installer Status

Added after the Tuesday installer-build session. **Does not invalidate Sections 1–13** — those represent the broader sprint plan; this section is a focused delta on Bucket 3 (the macOS installer) only. For full session detail see `SESSION_LOG_2026-04-28.md`.

## 14.1 Bucket 3 PRs merged this session

| PR | SHA | Subject | Status |
|---|---|---|---|
| #44 | `5e715ab` | I-1: preinstall.sh + lib/detect_ram.sh | 🟢 merged |
| #45 | `048f772` | I-2: postinstall.sh + Colima/Ollama libs + 4 launchd plists | 🟢 merged |
| #46 | `b8555c7` | I-3: Distribution.xml + branding HTML + Makefile pkg target + build_pkg.sh | 🟢 merged |
| #47 | `fb0cb9c` | VZ-only on Apple Silicon, drop qemu-img, copy lima libexec/bin | 🟢 merged |
| #48 | `07d1ec8` | Vendor docker CLI into .pkg payload | 🟢 merged |
| #49 | `df936f3` | Read version from pyproject.toml (was wrong path) | 🟢 merged |
| #50 | `ad986a5` | Codesign inner Mach-O binaries before pkgbuild (notarization fix v1) | 🟢 merged |
| #51 | `978ff61` | Re-seal .app/.framework bundles, don't break their seal (notarization fix v2) | 🟢 merged |

## 14.2 Bucket 3 — still open

| Item | Status | Notes |
|---|---|---|
| Notarization of submission `2c4130a4-13e6-4783-9b06-b7969ccb36aa` | ⏸ in flight | Awaiting Apple Accepted/Invalid for build SHA `978ff61126ea` |
| `make pkg` steps 7–9 (staple, sha256, spctl, banner) | ⏸ BLOCKED on notarization | Auto-runs on Accepted; nothing operator needs to do |
| **PR #52** — installer branding (icon.icns + background.png) | 🔴 OPEN, deferred | Locked direction: "Hero". Source PNGs at `Mining guardian logos/Icons/mining_guardian_recuts_all_sets/setA/{01_primary_shield_logo,04_long_horizontal_wordmark_logo}.png`. Will only touch `installer/macos-pkg/resources/`, no code. Picked up *after* notarization Accepted per operator direction "one thing at a time". |
| Q2 distribution — upload signed/notarized .pkg to private GitHub Release | 🔴 OPEN | Plus USB stick offline fallback. Out of scope for `build_pkg.sh`. |
| D-14 PR 5/5 (final Bucket 1 piece) | ⏸ BLOCKED | Gated on Mini physical install. |

## 14.3 Apple credentials — final shape

All six `KEY=VALUE` entries now live at the bottom of `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` (NOT in git):

```
APPLE_TEAM_ID=ARJZ5FYU94
APPLE_NOTARIZATION_KEY_ID=FPZJ87B3QF
APPLE_NOTARIZATION_ISSUER_UUID=f53661a7-931a-4976-8f8e-82353256931a
APPLE_NOTARIZATION_KEY_PATH=/Users/BigBobby/Documents/Apple Cert/AuthKey_FPZJ87B3QF.p8
APPLE_DEV_ID_INSTALLER=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
APPLE_DEV_ID_APPLICATION=Developer ID Application: Robert Fiesler (ARJZ5FYU94)
```

Verified valid signing identities in keychain (after intermediate-CA fix — see SESSION_LOG_2026-04-28.md § Major Discoveries #2):

| Cert | SHA-1 |
|---|---|
| Developer ID Application | `3A92362E47C40BE6A9A60C8D4EAB85E5CA0EB3D5` |
| Developer ID Installer | `2CB9429B5D64274D152E2CD5A8E0E66D1DB26AB9` |

## 14.4 Notarization submission ledger

| Submission ID | Build SHA | Status | Outcome |
|---|---|---|---|
| `ce730e52-460e-4220-a790-2f50b41401fa` | `df936f3c2781` | Invalid | 6 unsigned vendored binaries → fixed by PR #50 |
| `63236a3b-6a0d-4944-bb43-48de27ad6cda` | `ad986a5dc738` | Invalid | Ollama.app bundle seal broken → fixed by PR #51 |
| `2c4130a4-13e6-4783-9b06-b7969ccb36aa` | `978ff61126ea` | ⏸ in flight | Awaiting Apple |

## 14.5 New "Out of Scope (deferred)" entries

| Item | Why |
|---|---|
| 🚫 Logo PR #52 mid-flight | "one thing at a time" — operator OCD, no logo work until notarization green |
| 🚫 Editing CREDENTIALS_NOTES.txt prose half | All future agents: write/parse only the `KEY=VALUE` block at the bottom; the prose half above is for future-Bobby's eyes |

*— end of 2026-04-28 update*


---

## Section 14.6 — Q2 distribution shipped (2026-04-28 PM)

### Status flip

| Bucket 3 line item | Old status | New status |
|---|---|---|
| Q2 distribution — upload signed/notarized .pkg to private GitHub Release | 🔴 OPEN | ✅ DONE |
| Q2 distribution — USB stick offline fallback | 🔴 OPEN | ✅ DONE |
| Notarization (third try) | ⏸ in flight | ✅ Accepted (`2c4130a4`) |
| Repo visibility | public | private (per locked Q2 decision) |
| **PR #53** — installer branding | 🔴 OPEN, deferred | 🔴 OPEN, deferred (unchanged) |

### Distribution artifacts (single source of truth)

| Asset | Location | SHA-256 |
|---|---|---|
| `MiningGuardian-1.0.0-978ff61126ea.pkg` | Private GitHub Release `v1.0.0-978ff61126ea` + USB "MG Install" + `~/Documents/GitHub/Mining-Guardian/build/` | `c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8` |
| `.pkg.sha256` sidecar | Same three locations | n/a |
| `INSTALL.txt` (USB-only) | `/Volumes/MG Install/INSTALL.txt` | n/a (1,269 bytes, plain English) |

### Tag

`v1.0.0-978ff61126ea` → commit `978ff61126ea8acd21a41aa9d29293c9ec96dc0d` (PR #51, the build SHA — **not** current `main`). Annotated tag, message embeds full SHA-256, both signing identity SHAs, and the accepted `notarytool` submission ID.

### Release URL

[robertfiesler-spec/Mining-Guardian releases v1.0.0-978ff61126ea](https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.0-978ff61126ea)

### Round-trip verification proof

| Check | Result |
|---|---|
| `shasum -c` on GitHub-downloaded copy | OK |
| `spctl -a -t install` on GitHub-downloaded copy | accepted, Notarized Developer ID |
| `xattr` on GitHub-downloaded copy | `com.apple.provenance` (Sequoia+ "internet download" mark) |
| `shasum -c` on USB copy | OK |
| `spctl -a -t install` on USB copy | accepted, Notarized Developer ID |

The staple survived GitHub's CDN. The .pkg installs from any of the three locations without a Gatekeeper prompt on a clean Mac.

### Runbook for future Q2 cycles

`docs/RUNBOOK_DISTRIBUTION_v1.0.0.md` is the paste-along block for any future release. Pre-flight → tag → notes → release → upload → round-trip → USB → docs PR. Drop-in replacement of version strings is the only edit needed.

### Outstanding Bucket 3 work

| Item | Status |
|---|---|
| **PR #53 — installer branding** (Hero direction: `01_primary_shield_logo.png` as Finder icon, `04_long_horizontal_wordmark_logo.png` as installer background) | 🔴 OPEN, deferred |

Branding will trigger a fresh notarization round trip (binary content changes), which means a new `v1.0.x` tag + new GitHub Release. Today's release stays as the canonical v1.0.0 baseline.

*— end of 2026-04-28 distribution addendum*


---

# SECTION 15 — Update 2026-04-29 (Wednesday) — .pkg branding shipped

Added after the Wednesday branding-rebuild session. **Does not invalidate Sections 1–14** — focused delta on Bucket 3's final piece (the branded macOS Installer.app UI). For full session detail see `SESSION_LOG_2026-04-29.md`. For the lockdowns we discovered (so future maintainers don't burn the same five rebuilds), see `RUNBOOK_PKG_REBUILD.md` § "Addendum 2026-04-29 — Installer.app WebKit lockdowns".

## 15.1 Status flips

| Bucket 3 line item | Old status (after 2026-04-28 PM) | New status (2026-04-29) |
|---|---|---|
| **PR #54** — installer branding (Hero direction) | 🔴 OPEN, deferred | ✅ DONE (merged + superseded by #56–#58 visual fixes) |
| Branded Installer.app UI (welcome / conclusion / sidebar) | not started | ✅ DONE — build `0f849bd217cc` |
| GitHub Release for branded build | n/a | ✅ DONE — `v1.0.0-0f849bd217cc` is **Latest** |
| USB stick "MG Install" — branded build | held the unbranded `978ff61126ea` | ✅ DONE — replaced with `0f849bd217cc`, INSTALL.txt rewritten, ejected |
| Round-trip verify from GitHub on a fresh download | n/a | ✅ PASS (`shasum -c` OK + `spctl -a -t install` accepted) |
| Old release `v1.0.0-978ff61126ea` | Latest | demoted to Pre-release (kept for audit trail) |

**Bucket 3 is closed.** Every remaining .pkg-related thing is now a downstream Bucket 1 / Bucket 4 task (real Mac Mini install + customer rollout), not a build-pipeline task.

## 15.2 PRs merged this session

| PR | SHA | Subject | Build verdict |
|---|---|---|---|
| #54 | `2f3bff5a8e28` | Initial branded welcome + conclusion HTML + sidebar background + brand PDFs + docs | white-bg bug (Lockdown #1) |
| #55 | `5ba091d561fa` | `.page` wrapper attempt to fix Lockdown #1 | navy-on-navy (Lockdown #2) |
| #56 | `e0e4bbe114f1` | Light-theme rebuild — literal hex `!important`, drop CSS variables | right pane locked in; sidebar nav still hidden (Lockdown #3) |
| #57 | `fb5b7038988c` | Sidebar PNG: top 50% reserved as flat dark navy | active step OK, inactive too dim |
| #58 | `0f849bd217cc` | Sidebar PNG: top zone switched to light blue-grey gradient | **clean — all six nav steps readable, shipped** |

Five PRs, five `make pkg` rebuilds, five notary submissions (every one Accepted by Apple — these were visual not signing rejections). Detailed ledger in § 15.4.

## 15.3 Three Installer.app WebKit lockdowns we discovered

Documented in full in `RUNBOOK_PKG_REBUILD.md` § Addendum 2026-04-29. Brief tag:

1. **`html`/`body` `background` is forced transparent.** Workaround: paint inner divs only.
2. **CSS custom properties don't survive for `color`.** Workaround: literal hex `!important`.
3. **Sidebar PNG nav-zone must be light-toned.** Workaround: reserve top 50% (y=0..540) as `#F1F4F9`→`#E1E8F2` gradient, feather y=540..600, artwork in bottom 50%.

If you touch anything in `installer/macos-pkg/resources/` in the future, read the addendum first. It will save you four rebuilds.

## 15.4 Notarization submission ledger (this session)

| # | Submission ID | Build SHA | Outcome |
|---|---|---|---|
| 1 | `9f34a1ea-a5df-4d28-bbed-e4ca74170765` | `2f3bff5a8e28` (PR #54) | Apple Accepted; visual reject (Lockdown #1) |
| 2 | `6b6596c0-67f8-44da-bb5d-9346e1e90f2c` | `5ba091d561fa` (PR #55) | Apple Accepted; visual reject (Lockdown #2) |
| 3 | `03f4a5c7-0798-4d06-9366-66fc5d1e6c18` | `e0e4bbe114f1` (PR #56) | Apple Accepted; right pane good, sidebar reject (Lockdown #3) |
| 4 | `e549d551-f0be-492a-a95c-8caa43a9c238` | `fb5b7038988c` (PR #57) | Apple Accepted; partial sidebar fix |
| 5 | **`6813ec95-7abc-4768-bd06-fe4f1acdf777`** | **`0f849bd217cc` (PR #58)** | **Apple Accepted; visual clean — shipped** |

Cumulative project total (since 2026-04-28): 8 notarization submissions, 5 visual-clean visuals, 1 shipped artifact, 0 Apple-side rejections.

## 15.5 Distribution artifacts (current source of truth)

| Asset | Location | SHA-256 |
|---|---|---|
| `MiningGuardian-1.0.0-0f849bd217cc.pkg` | Private GitHub Release `v1.0.0-0f849bd217cc` (Latest) + USB "MG Install" + `~/Documents/GitHub/Mining-Guardian/build/` | `1e65fe7827ffba2c8cd4daa0c2a42218bb156798521278fd0e567b0cef53a646` |
| `.pkg.sha256` sidecar (basename format) | Same three locations | n/a |
| `INSTALL.txt` (USB-only) | `/Volumes/MG Install/INSTALL.txt` | n/a (rewritten 2026-04-29) |

Tag: `v1.0.0-0f849bd217cc` → commit `0f849bd217ccba0ecceeda652550e131d7cd71a3` (PR #58 merge).

Release URL: [robertfiesler-spec/Mining-Guardian releases v1.0.0-0f849bd217cc](https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.0-0f849bd217cc)

## 15.6 What's next (carry-over to 2026-04-30 and beyond)

Bucket 3 done. Remaining sprint priorities, restated:

| Bucket | Item | Status |
|---|---|---|
| 🔴 1 | D-14 PR 5/5 (final Bucket 1 piece) | ⏸ BLOCKED on Mini physical install |
| 🔴 1 | Backfill 124 missing `raw_json` rows | OPEN |
| 🔴 1 | Runtime invariant assertion | OPEN |
| 🟡 2 | CI lint pipeline | OPEN |
| 🟡 2 | B-7 migrations 002 | OPEN |
| 🟡 2 | VPS PAT rotation (S-2 was emergency Sunday — confirm rotation cycle) | OPEN |
| 🟡 2 | Delete `cleanup_ams_logs.py` | OPEN |
| 🟡 2 | **Grafana intelligence dashboard — miner dropdown is hard-coded, must auto-expand from DB** | OPEN — see § 15.6.1 |
| 🟢 3 | .pkg branding | ✅ **DONE 2026-04-29** |
| 🟢 4 | Power cycle 53476 | OPEN |
| 🟢 4 | Inspect 53494 / 53521 / 53482 | OPEN |
| 🟢 4 | HVAC | OPEN |

See `STUDY_NOTE_2026-04-30.docx` for tomorrow's review packet.

### 15.6.1 Grafana miner-dropdown auto-expand bug (filed 2026-04-29)

**Symptom (operator-reported 2026-04-29):** The intelligence Grafana page has a fixed/hard-coded list of miner serial numbers in its template-variable dropdown. New miners discovered in the daily search runs do not appear, so not all miners actually present in the database are visible in the dashboard. Operator currently cannot select miners that exist in Postgres.

**Root cause (likely):** The dashboard JSON has a `templating.list[]` entry of `type: "custom"` with a literal value list, instead of `type: "query"` driven by a SQL query against the canonical miners table.

**Fix shape:**
1. Identify the canonical miners table on Postgres (probably `miners` or `mining_miners` — confirm during fix; do **not** read from JSON catalog, that path is on its way out per C1).
2. Replace the `custom` template variable with a `query` variable, definition roughly:
   ```sql
   SELECT DISTINCT serial_number AS __value, hostname AS __text
   FROM miners
   WHERE active = true
   ORDER BY hostname;
   ```
   (exact column names TBD — verify against `\d miners` first).
3. Set `refresh: 2` ("On Time Range Change") so the dropdown re-queries the DB every time the dashboard loads. Alternative: `refresh: 1` ("On Dashboard Load") if cost is a concern.
4. Set `multi: true` and `includeAll: true` so the operator can pick one, several, or all miners.
5. Test: add a new test miner to the DB, reload the dashboard, confirm it appears without dashboard JSON edits.
6. Provision the fix into `installer/grafana/dashboards/intelligence.json` (or wherever this dashboard lives) so the Mac Mini install gets the corrected version on first boot — do not just hot-fix the running Grafana on the VPS.

**Effort estimate:** 30-60 min once we're at a Mac with Grafana access. Bucket 2 not Bucket 1 — does not block the Mini install, but should ship before any customer sees the dashboard.

**Cross-reference:** Section 7.2 Phase 11 ("Grafana provisioning") and Section 7.3 7g ("Add Grafana provisioning yaml") already plan a Grafana provisioning yaml for the installer — this fix should land inside that provisioning yaml so it's never re-introduced.

## 15.7 Stale branches OK to delete

Confirmed zero-ahead, content already in `main`:

- `fix/typo-rename-mining-guardian-2026-04-26`
- 4× `hotfix/cr-*-2026-04-2[56]`
- `openclaw-integration`
- `docs/customer-docs-and-installer-branding` (PR #54 source — superseded)
- `feature/installer-page-wrapper` (PR #55 source — superseded)
- `feature/installer-light-theme` (PR #56 source — superseded)
- `fix/installer-sidebar-background-nav-zone` (PR #57 source — superseded)
- `fix/installer-sidebar-light-top-zone` (PR #58 source — current main)

Stale experiments — **do NOT delete without asking**:

- `feature/fast-cohort-analysis` (diverged 2 ahead / 202 behind)
- `feature/intelligence-catalog` (diverged 21 / 294)
- `pre-prod-audit-2026-04-25` (diverged 47 / 294)

*— end of 2026-04-29 update*

---

# SECTION 16 — Update 2026-04-29 (late) — Bucket 10 repo-docs audit

## 16.1 Bucket 10 — Full repo documentation cleanup sweep

| Step | Status | Notes |
|---|---|---|
| Bucket 10 audit + planning doc | 🟡 IN PROGRESS — PLAN PUBLISHED | `docs/BUCKET_10_REPO_DOCS_AUDIT_2026-04-29.md` (this PR) inventories all 104 `*.md` files at root + `docs/`, reference-counts each, tiers them A/B/C, and proposes the move/citation-update plan |
| Bucket 10 execute (move + cite) | 🔴 OPEN | Follow-up PR after Bobby resolves the 8 verify-first cases listed in §9 of the audit doc. Net moves ~25–30 files, citation updates ~15–20 lines |

## 16.2 What this audit found

- **104 markdown files total** at root (8) + `docs/` (96)
- **15 files with 0 incoming references** → Tier A archive-immediately
- **20 files with 1 incoming reference** → Tier B-1 (most cite only `CLAUDE.md`'s tracker tables — drop the row + archive)
- **13 files with 2 incoming references** → Tier B-2 (mostly KEEP — vendor APIs and active runbooks)
- **56 files with 3+ refs** → Tier C keep

## 16.3 Doctrine

- Archive ≠ delete. Move to `docs/_archive/2026-04/` so files stay in repo history and on disk.
- Per "comprehensive + over-document always": only the explicitly-superseded and the dated session/handoff files leave the active doc tree. Vendor API docs, design specs, runbooks, and any file referenced from Python source stay.
- 8 borderline files flagged verify-first for Bobby — defer until reviewed.
