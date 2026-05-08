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

## 1.2 v1.0.3 installer train (D-18 — locked 2026-05-03)

The PR train below closes the v1.0.2 .pkg audit gaps (`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`). Order is locked in D-18 implementation plan and `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md`.

| # | Audit Gap / Bug | Status | PR / Notes |
|---|---|---|---|
| 1 | Gap 5 — Python venv + offline pip install | ✅ | PR `mg/v103-gap5-postinstall-venv` (2026-05-04) — `step_create_venv` + vendored wheels + payload-requirements.txt + tests/installer/test_postinstall_venv.sh; exit code 38 reserved |
| 2 | Gap 2 — Catalog DB + 320-row seed | ✅ | PR `mg/v103-gap2-catalog-db-and-seed` (2026-05-04) — `step_provision_catalog_db_and_seed` (creates `mining_guardian_catalog`, applies `deploy_schema.sql`, seeds 320 rows from `seed_miner_models.sql`); `build_pkg.sh` step 4g asserts seed staged in payload; exit code 39 reserved; exit code 44 in build for missing seed; `tests/installer/test_postinstall_catalog_seed.sh` (24 assertions). |
| 2b | P-004 — D-20 importer-payload reconciliation | ✅ | PR `mg/v103-d20-importer-payload-reconciliation` (2026-05-04) — `build_pkg.sh` 4a no longer includes `mg_import_tool/***`; cross-directory `mg_import_tool/sql/migrations/` rsync removed; runtime-relevant importer migrations relocated to `migrations/006_field_log_bootstrap.sql` and `migrations/007_layer2_resolver.sql` (byte-identical bodies, idempotency preserved); new `step 4h` post-assembly assertion `find … -name 'mg_import*'` aborts with exit 43 if any match. Operator-side originals in `mg_import_tool/sql/migrations/` retained — D-20 footnote (importer is operator-only forever; importer needs its own bootstrap copy). Tests: `tests/installer/test_d20_importer_payload_reconciliation.sh` (32 assertions, all green); existing catalog-seed and venv tests still green; build_pkg.sh shellcheck warnings 5→2 (improvement). Closes the v1.0.3 D-20 violation flagged in discovery §3.6 BEFORE the v1.0.3 build PR fires. |
| 3 | Gap 1 — Customer-info Desktop conf flow + Integration bugs 1/2/4 | ✅ | PR `mg/v103-gap1-customer-info-conf` (2026-05-04, P-005) — `step_collect_customer_info` reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`, validates per B-2 rules (mirrors `setup.sh::mg_validate_site_config`), Cocoa dialog (`osascript display dialog`) + exit 41 on missing/invalid (runs BEFORE any system-state change). `step_drop_dotenv` rewritten: generates `MG_DB_PASSWORD` / `CATALOG_API_KEY` / `INTERNAL_API_SECRET` via `openssl rand -hex 32` (closes Integration bug 1 — no `/tmp/mg_install_env_secret` staging); writes BOTH `GUARDIAN_PG_USER=mg` and `PGUSER=mg` (Integration bug 2); writes full `.env` matching `setup.sh::phase_07_secrets` shape including `AMS_*`/`SLACK_*`/`AUTO_APPROVE_ENABLED=false` (Integration bug 4). Tests: `tests/installer/test_postinstall_customer_info.sh` (76 assertions, all green); existing venv (24/24), catalog seed (24/24), and D-20 importer (32/32) tests still green. shellcheck warnings: 3 → 3 (no regression). |
| 4 | Gap 3 — Grafana vendoring + provisioning + LaunchDaemon | 🔴 | Vendor `grafana.app`, provisioning yaml, 11th LaunchDaemon |
| 5 | Gap 4 — Scheduled-tasks launchd plists (replaces setup.sh phase_10 cron) | ✅ | PR `mg/v103-gap4-scheduled-launchd` (2026-05-04, P-007) — 11 launchd plists under `installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.*.plist` (10 × `StartCalendarInterval` + 1 × `StartInterval=3600` for the hourly benchmark). One generic `scheduled_job_launcher.sh` under `installer/macos-pkg/resources/launchd/launchers/` (sources `.env`, dispatches `.py`/`.sh`, stamps `logs/scheduled/<task_key>.last-run.json` for the operator console). New `step_install_scheduled_plists_and_bootstrap` in `postinstall.sh` (exit code 40 reserved) called after the 10 service plists. New `step 4i` assertion in `build_pkg.sh` (exit code 47 reserved). `setup.sh::phase_10_cron` rewritten as `phase_10_scheduled` (now installs the same launchd plists; no `crontab -` install path remains). `console/task_registry.py` extended with the 11th `refinement_chain` task that P-006 had bundled into `weekly_training`. Tests: `tests/installer/test_postinstall_scheduled_jobs.sh` (115 assertions, all green); existing venv (24/24), catalog seed (24/24), customer-info (76/76), and D-20 importer (32/32) tests still green; console suite still 63/63. Shellcheck baselines unchanged (postinstall 3, build_pkg 2). |
| 6 | D-19 console (10th service, Cloudflare-fronted) | 🟡 | **Foundation landed** 2026-05-04 in P-006 (branch `mg/v103-d19-console-foundation`): FastAPI/Jinja2/HTMX under `console/` (5 modules + 6 templates + CSS), `com.miningguardian.console.plist` + `console_launcher.sh`, postinstall PLIST_LABELS/LAUNCHER_FILES extended to 10 services, build_pkg.sh rsync include `console/***`. **Port 8787, NOT 8686** — 8686 is owned by `api/approval_api.py`; conflict and rationale documented in `docs/CONSOLE_OPERATIONS_GUIDE.md` (new file). 59/59 tests green (`tests/console/`). Approve/Deny update `pending_approvals.status` directly; remediation execution stays with the existing Slack flow until a unified library lands (post-cutover). `INTERNAL_API_SECRET` never leaks (verified by sentinel test). **Grafana UI explicitly untouched** per operator clarification 2026-05-04. **Still open under this row:** Cloudflare Tunnel + Access auto-provisioning (D-19 step 5 — see also row 9). |
| 7 | Copy bug 1+2+4 — welcome.html/conclusion.html service counts + ports | ✅ | PR `mg/v103-p008-installer-copy-and-uninstall` (2026-05-04, P-008) — `welcome.html` updated: "four" → "ten background services", added "eleven scheduled jobs" line with launchd wording (no `crontab` literal), Desktop `MiningGuardian.conf` hand-off mentioned, dashboard URL `:8080` → `:8585`, console URL `:8787` added. `conclusion.html` updated: "All four" → "All ten", verify code block enumerates all 10 services + scheduled-jobs `launchctl list \| grep` hint, quick-link grid shows dashboard `:8585` / approval API `:8686` / operator console `:8787` / scheduled-job logs path, uninstall blurb mentions `--dry-run` / `--purge-data`. Stale `:8080` / `:8081` log lines in `postinstall.sh::main()` corrected to `:8585` / `:8686` / `:8787`. Tests: `tests/installer/test_installer_copy.sh` (43 assertions, all green) — covers service/scheduled-job counts, no-cron wording, no Grafana-control claim, port URLs, all 10 service labels in verify block, branding spelling. |
| 8 | Copy bug 3 — real `bin/uninstall.sh` | ✅ | PR `mg/v103-p008-installer-copy-and-uninstall` (2026-05-04, P-008) — new `installer/macos-pkg/resources/uninstall.sh` (mode 0755, shellcheck-clean) covers all 10 service LaunchDaemons + 11 scheduled-job LaunchDaemons via `launchctl bootout` then plist `rm`, removes `mining-guardian-db` Postgres container (best-effort), stops the `mining-guardian` Colima profile (best-effort, never fatal), removes `/Library/Application Support/MiningGuardian/` (preserving the `postgres-data/` subdir by default), removes `/etc/mining-guardian/install-receipt.json`. Flags: `--help` / `--dry-run` / `--yes` / `--purge-data` / `--purge-logs`. **Default behavior preserves `postgres-data` and `/var/log/mining-guardian` — data deletion is opt-in via `--purge-data` per the §"Critical Safety Rules" entry forbidding bulk deletes from `mining_guardian` without an explicit step.** Refuses to run as non-root (exit 1); refuses non-TTY without `--yes` (exit 1); rejects unknown flags with exit 2; reserves exit codes 10/11/12/13 for hard failures. Wired into `postinstall.sh` via new `step_install_uninstall_script` (installs to `${MG_INSTALL_ROOT}/bin/uninstall.sh` mode 0755 root:wheel) and `build_pkg.sh` step 4j source-tree assertion (exit 48 reserved). Tests: `tests/installer/test_uninstall_script.sh` (50 assertions, all green) — covers source presence + mode 0755, bash syntax, all 21 plist labels (10 + 11), drift check vs `postinstall.sh`, all flag implementations, data-preservation default, root + non-TTY guards, postinstall wiring, build_pkg assertion, conclusion.html path agreement, `--help` exits 0 without root, unknown-flag exits 2. |
| 9 | Cloudflare Tunnel + Access setup | 🔴 | Postinstall step gated on Cloudflare token in Desktop conf |
| 10x | P-029 (knowledge — 2026-05-08) — installer payload missing `knowledge.json`; every fresh customer install starts cold (zero `miner_profiles` / `miner_fingerprints` / `refined_insights`), degrading Vision Anchor 1 (the LLM IS the product) and blocking Vision Anchor 4 (federated learning bootstrap) | ✅ | **Merged 2026-05-08 as PR #164 (squash commit `282a74e`, on merge `0140717`).** Branch `mg/p029-knowledge-json-installer-payload` (P-029 knowledge — NOT to be confused with the merged row 10v `mg/p029-postinstall-env-shell-safe-and-config-json` or row 10u `mg/p029-parameter-rule-config-load`; same P-number was reused for distinct work). **Fix:** (1) Repo seed at `installer/macos-pkg/resources/knowledge/knowledge.json` (3,739,968 bytes, SHA-256 prefix `2edea974d711`, 96 profiles / 133 fingerprints / 61 insights, internal `last_updated` 2026-04-29) — copied from the canonical `knowledge_backup.json` superset identified by the May 2026 inventory. (2) `build_pkg.sh` step 4l stages the seed into `<payload>/installer-resources/knowledge/knowledge.json` with build-time JSON validation (parse + at least one of `{miner_profiles, miner_fingerprints, refined_insights}`). Build hard-fails (`_die 43`) on missing or malformed seed. (3) `postinstall.sh::step_install_knowledge_json` runs after `step_normalize_discovery_sink_perms` and before `step_drop_dotenv` — fresh-install branch creates `${MG_INSTALL_ROOT}/knowledge/{,incoming,backups}` (miningguardian:staff 0775), copies seed to active path (0664), creates compat symlink at `${MG_INSTALL_ROOT}/knowledge.json` so existing callers (`ai/ai_score.py`, `ai/action_diversity.py`, `ai/backup_knowledge.py`, `core/mining_guardian.py:2403`) keep working without code change, validates JSON, emits `INFO P-029: installed knowledge.json path="…" size=… sha256=… miner_profiles=… miner_fingerprints=… refined_insights=…` proof line. Upgrade branch leaves the active file untouched, stages the packaged seed alongside as `${MG_INSTALL_ROOT}/knowledge/incoming/knowledge-seed-<version>-<sha>.json`, emits preservation + staging proof lines. Idempotent: deterministic incoming filename means a second run over the same payload produces no drift. (4) `docs/DECISIONS.md` D-29 locks the filesystem contract, ownership/mode rules, fresh/upgrade behavior, and — critically — the **section-level merge rules for the future monthly federated update**: `miner_profiles` / `miner_fingerprints` prefer newer `last_updated`, never delete site keys absent from master; `refined_insights` / `pattern_rules` append-unique by `id`; `operator_decisions` / `baselines` / `operator_rules` are **site-only** (master must not include them); `cross_miner_analysis[0]` is owned by Sunday weekly training and not replaced; `daily_deep_analyses` append-unique by date, never deleted; `hardware_facts` overlay (master wins on shared keys, site-only keys preserved); tombstones explicitly NOT supported in v1. Same `miningguardian:staff` 0775/0664 pattern as P-027. **Tests:** new `tests/installer/test_p029_knowledge_json_installer.sh` (46 assertions, all green) — §1 scripts parse, §2 seed at canonical repo path with size + JSON shape, §3 build_pkg.sh step 4l block + marker + payload staging path + proof log + JSON validation, §4 postinstall constant declared readonly + step defined + orchestration order, §5 fresh-install runtime smoke (active file created, JSON parses, compat symlink resolves to same content, dirs created, proof log line correct shape including counts), §6 upgrade runtime smoke (active file content preserved verbatim, packaged seed staged under incoming/ with version+sha tag, both proof lines present), §7 ownership/mode static checks (0775 dirs, 0664 files, chown to MG_INSTALL_OPERATOR_USER:staff), §8 malformed seed in payload triggers exit-43 fail() with P-029 (knowledge) tag, §9 fresh-install on-disk modes confirmed (file 0664, dirs 0775), §10 upgrade idempotence (second run preserves active + leaves incoming seed at the same deterministic name). All 24 installer suites continue to pass; pre-existing 1-fail in `test_postinstall_scheduled_jobs.sh` and 1-fail in `test_uninstall_script.sh` are untouched. **Out-of-scope (deliberately deferred — see D-29 "NOT in this PR"):** the merge implementation `ai/apply_master_update.py`, backup rotation under `knowledge/backups/`, signed monthly payloads, two-Mini E2E test bench. The merge contract is locked in D-29 so the follow-up implementation cannot drift. **No P-031, no P-033, no `ai/apply_master_update.py` in this PR.** Status 🟡 until merge + new build. Flips to ✅ on merge. |
| 10z | P-030 — scanner `run_once()` failed to import `ai/knowledge_manager.py` under postinstall + LaunchDaemon CWDs; every scan logged `Knowledge update skipped: No module named 'knowledge_manager'`; the scan completed but produced no knowledge update (Vision Anchor 1 silent regression) | ✅ | **Merged 2026-05-08 as PR #162 (squash commit `b4627b5`, on merge `18e5a03`).** Branch `mg/p030-ai-syspath-run-once` (P-030). **Fix:** one-line addition to `core/mining_guardian.py` — early `sys.path.insert(0, str(_ROOT / "ai"))` after `_ROOT = Path(__file__).resolve().parent.parent`, so the bundled `ai/` package directory is searched before the system path at module import time, before `from knowledge_manager import …`. Insert is idempotent (guarded against duplicate entries on re-import) and best-effort (graceful when `_ROOT / "ai"` does not exist). **No installer / build / payload / notarization / schema / migration changes** — pure 1-line `sys.path` insert + 5 unit tests. **Tests:** new `tests/test_ai_syspath_run_once.py` (5 assertions, all green) — (a) `ai/` is the first non-empty entry in `sys.path` after `core.mining_guardian` is imported, (b) `knowledge_manager` resolves to `ai/knowledge_manager.py` after the insert, (c) `run_once()` does not raise `ModuleNotFoundError` when invoked under a CWD that is not the install root, (d) the import order is stable across re-imports (idempotency), (e) the scanner still runs when `_ROOT / 'ai'` does not exist (graceful degradation). Combined with P-031: `pytest tests/test_ai_syspath_run_once.py tests/test_p031_ollama_config.py -v` reports **29 passed**. **Operator check after install:** on the Mini, `grep -E 'Knowledge update skipped|No module named .knowledge_manager.' /Library/Application\ Support/MiningGuardian/logs/guardian.log` should return zero matches on any timestamp newer than the install. Flipped to ✅ on merge. |
| 10w | P-032 — `core/discovery_sink.py::_atomic_write_json` rewrites `latest_findings.json` at mode 0600 on every scan, undoing the P-027 postinstall normalization | ✅ | **Merged 2026-05-08 as PR #163 (squash commit `a98fa3a`, on merge `85e9a33`).** Branch `mg/p032-discovery-sink-atomic-write-mode` (P-032) — Investigation found that `_atomic_write_json` opens the temp file via `tempfile.mkstemp(...)` (which creates the file at 0600 by design) and then calls `os.replace(tmp, target)`. POSIX `rename` (and Python's `os.replace`) preserves the source file's mode bits when overwriting the destination — the net effect was that every hourly scan rewrote `${MG_INSTALL_ROOT}/cron_tracking/scanner_discovery/latest_findings.json` as 0600, even after P-027's postinstall step healed it to 0664 (group-readable+writable, world-readable) for cross-account cron readers. The cron-driven catalog-import job runs under a different account on customer Macs, so a 0600 snapshot is unreadable to it; the symptom was P-027's healing being silently undone within the next scan window. **Fix:** one-line addition — `os.chmod(tmp_name, 0o664)` between `os.fsync(...)` and `os.replace(tmp_name, path)` in `core/discovery_sink.py::_atomic_write_json`. The chmod is umask-independent (explicit numeric mode), so the behaviour holds under both umask 022 (server default) and umask 002 (developer-typical). Doc-comment expanded to cite P-027 and explain why the explicit chmod is required despite the file being daemon-written. **No `build_pkg.sh`, payload, postinstall, schema, migration, or notarization changes** — pure 1-line Python fix in one helper, plus a comment block. **Tests:** `tests/test_p022_discovery_sink.py` extended with new `TestAtomicWritePermissions` class (4 tests, all green) — (a) first write under umask 022 lands at 0664, (b) first write under umask 002 lands at 0664, (c) every subsequent scan keeps the file at 0664 (the actual bug — once-on-first-write would not have been enough), (d) a pre-existing 0600 file on disk (the broken pre-P-032 state customer Mini will have) is healed to 0664 by the next scan. All 23 tests in the suite pass (19 existing + 4 new). **Out-of-scope (deliberately narrow):** the `events-YYYY-MM-DD.jsonl` audit-trail file is created via `open(..., "a")` and depends on the daemon umask — that's a separate (and much smaller) drift if it exists, and is NOT addressed here per the narrow-scope instruction. P-027's postinstall already chmods the JSONL on install/upgrade. **No P-029, P-030, P-031, or installer package build in this PR.** Status 🟡 until merge. Flips to ✅ on merge. |
| 10y | P-031 — every Python LLM call site falls back to `qwen2.5:32b-instruct-q4_K_M` (the never-pulled model); customer Mac mini logs `Qwen scan analysis failed: HTTP Error 404: Not Found` every scan, breaking Vision Anchor 1 (the LLM IS the product) | ✅ | **Merged 2026-05-08 as PR #165 (squash commit `0d8f73d`, on merge `eecde3a`).** Branch `mg/p031-ollama-model-from-env` (P-031) — D-13 has the installer pull `llama3.2:3b` on a 16 GB Mini and `qwen2.5:14b-instruct-q4_K_M` on a 24 GB+ Mini, writing the choice into `MG_INSTALL_LLM_MODEL` in `.env`. Pre-P-031 the .env writer never exported `OLLAMA_MODEL`; `GuardianConfig` had no `ollama_model` / `ollama_url` field; `step_drop_config_json` did not surface either key. Every Python call site (`core/mining_guardian.py:2386`, `ai/local_llm_analyzer.py:90`, `ai/daily_deep_dive.py:151`, `ai/refinement_chain.py:158/258`, `ai/combine_knowledge.py:39`) therefore fell through `getattr(self.config, "ollama_model", "qwen2.5:32b-instruct-q4_K_M")` to a model that no D-13 install path ever pulls. Ollama returned 404 for every scan. **Fix:** (1) New `core/ollama_config.py` with `resolve_ollama_url()` / `resolve_ollama_model()` — env-first chain `OLLAMA_MODEL` → `MG_INSTALL_LLM_MODEL` → `llama3.2:3b` (D-13 small-tier default chosen deliberately: a too-small fallback still hits a real model on the 24 GB tier; a too-big fallback hits nothing on the 16 GB tier). (2) `core/models.py::GuardianConfig` gains `ollama_url` / `ollama_model` fields, populated by `from_file` via the helper; `env:OLLAMA_URL` / `env:OLLAMA_MODEL` placeholders that resolve to an unset env var now fall through gracefully instead of raising `EnvironmentError`. (3) `core/mining_guardian.py` Qwen post-scan analyzer + the four sibling AI scripts now resolve via the helper; no remaining quoted `qwen2.5:32b` literal. (4) `installer/macos-pkg/scripts/postinstall.sh::step_drop_dotenv` writes `OLLAMA_URL=http://127.0.0.1:11434/api/generate` and `OLLAMA_MODEL=${MG_INSTALL_LLM_MODEL_Q}` to `.env`. (5) `step_drop_config_json` injects `cfg["ollama_url"] = "env:OLLAMA_URL"` and `cfg["ollama_model"] = "env:OLLAMA_MODEL"` into the materialized `config.json`. **No `build_pkg.sh`, payload, plist, or notarization changes** — pure Python helper + 5-call-site refactor + 4 lines of postinstall additions. **Tests:** new `tests/test_p031_ollama_config.py` (24 assertions, all green) covering: helper unit tests for both resolvers (env precedence, D-13 default, no 32B in any branch, no retired-host default), `GuardianConfig.from_file` integration (env placeholder resolution, unset-placeholder graceful fallback, literal config wins, defaults), and a parametrized lock that no quoted `qwen2.5:32b` survives in any of the five call sites. New `tests/installer/test_p031_ollama_env_and_config.sh` (10 assertions, all green) covers `step_drop_dotenv` writing both keys and `step_drop_config_json` injecting both env: placeholders, plus a no-32B-string-literal sweep across the same five call sites. Existing `tests/test_models.py` 17/17, `tests/installer/test_postinstall_env_handoff.sh` 38/38, `tests/installer/test_postinstall_env_shell_safe.sh` 64/64, `tests/installer/test_p029_knowledge_json_installer.sh` 46/46, `tests/installer/test_p027_discovery_sink_perms.sh` 18/18, `tests/installer/test_p028_upgrade_stale_scripts_cleanup.sh` 23/23 all still green — none regressed by the .env / config.json additions. **Out-of-scope (deliberately deferred):** P-033 is NOT in this PR. **No P-033, no `combine_knowledge.py` rework beyond the resolver swap, no Sunday-training prompt edits.** Status 🟡 until merge + new build. Flips to ✅ on merge. |
| 10aa | P-034 + P-035 (knowledge / LLM persistence hardening — 2026-05-08) — Bundled fix: (1) `core/mining_guardian.py:2409` Qwen post-scan persistence block hard-codes `/root/Mining-Guardian/knowledge.json` (legacy Linux dev path that does not exist on the Mac Mini install tree) — every scan logs `Qwen scan analysis failed: [Errno 2] No such file or directory` even though the Qwen call succeeds; the `llm_scan_analyses` stream weekly_train.py reads stops accumulating (Vision Anchor 1 — the LLM IS the product). (2) `ai/knowledge_manager.py::update_from_scan` line 123 does `profile["total_flags"] += 1` against pre-existing seeded miner_profiles entries that may lack the key; live evidence on Mini install eecde3a — 3 of 96 seeded profiles in `installer/macos-pkg/resources/knowledge/knowledge.json` lack `total_flags`; scanner logs `Knowledge update skipped: 'total_flags'` and that miner's scan-result accumulation silently skips for the affected scan. (3) Six remaining hand-rolled `tmp + os.replace` writers (`ai/daily_deep_dive.py`, `ai/train_cohort.py`, `ai/refinement_chain.py`, `ai/outcome_checker.py` ×2, `ai/local_llm_analyzer.py`) race the Qwen scan analyzer and KnowledgeManager.save under concurrent write; daily_deep_dive used a non-atomic `KNOWLEDGE_PATH.write_text(...)` (highest priority — a crash mid-write left a half-written knowledge.json). | 🟡 | Branch `mg/p034-p035-knowledge-persistence-hardening` (this PR, 2026-05-08, P-034 + P-035) — Consolidated PR. **Supersedes PR #167** (the P-034-only branch) — the audit found that shipping P-034 alone leaves the `KeyError: 'total_flags'` (B-35) and the six writer-race surfaces in place; one consolidated PR + one rebuild beats two separate rebuilds for closely-related persistence work. **Fix:** (1) **P-034** — `core/mining_guardian.py` Qwen block now resolves the path via `_ROOT / "knowledge.json"` and routes the read-modify-write through `core.file_lock.locked_knowledge_update` — the canonical helper every other knowledge writer uses for atomic write + flock. (2) **P-035 / B-35** — `update_from_scan` defensively `setdefault`s `total_flags` / `last_flagged` / `issue_history` before mutation; the `chronic`-ranking read sites at line 252-258 in `build_context_prompt` use `.get(...)` and `or []` defensively. (3) **Writer hardening** — `ai/daily_deep_dive.py::_save_to_knowledge` (was `KNOWLEDGE_PATH.write_text(...)` — non-atomic), `ai/train_cohort.py` cross_miner_analysis write at line 1088, `ai/refinement_chain.py::save_knowledge`, `ai/outcome_checker.py::_update_miner_profile` and `_validate_prediction`, `ai/local_llm_analyzer.py::_store_analysis` all routed through `locked_knowledge_update`. `ai/combine_knowledge.py::main` switches to `core.file_lock.atomic_write_json` for the federated master_knowledge.json (single-writer; flock not needed but the helper centralizes the temp-file-then-rename guarantee), with an inline-atomic-write fallback for the federated-master host where `core/` may not be on `sys.path`. (4) **Docstring sweep** — `ai/daily_deep_dive.py`, `ai/refinement_chain.py`, `ai/backup_knowledge.py`, `ai/weekly_train.py` headers no longer reference `/root/Mining-Guardian` cron lines or `ROBS-PC`; they now point at `${MG_INSTALL_ROOT}` and `docs/CRON_SCHEDULE.md`. Bulk `scripts/*` legacy operator-tool edits explicitly out of scope. **No `build_pkg.sh`, payload, postinstall, plist, schema, migration, or notarization changes** — pure Python source fixes across one core file + seven AI files + four docstring files. **Tests:** new `tests/test_p035_knowledge_persistence_hardening.py` (26 assertions) — §1 P-034 path/locked-write fix (5 assertions); §2 P-035 KnowledgeManager defensive backfill (4 assertions: live seed exhibits the bug shape, KnowledgeManager loads real seed without KeyError, `update_from_scan` against seed-shaped profile sets `total_flags=1` and never raises, static-source check that all three `setdefault` calls precede the `+= 1`); §3 P-035 writer hardening (parametrized × 7 writers + AST walks: every active writer imports `locked_knowledge_update`, no `os.replace(*, KNOWLEDGE_PATH)` AST call, no `KNOWLEDGE_PATH.write_text(...)` AST call); §4 combine_knowledge uses atomic_write_json. All 26 tests pass locally (24 with psycopg2 unavailable; 2 skipped — covered by static-source check). **Existing suites — none regressed:** `tests/test_p031_ollama_config.py` 24/24, `tests/test_ai_syspath_run_once.py` 5/5 (P-030), `tests/test_p022_discovery_sink.py` 23/23 (P-032), `tests/installer/test_p029_knowledge_json_installer.sh` 46/46 (P-029 knowledge), `tests/installer/test_p031_ollama_env_and_config.sh` 10/10. **Out-of-scope:** P-033 is NOT in this PR. The dead `from pathlib import Path as _P` import at `core/mining_guardian.py:2357` is left in place per scope discipline. Bulk docstring edits across `scripts/*` legacy operator tools are not in scope. **Live verification (operator-side, after merge — fix is plain-Python so no .pkg rebuild required, just `git pull` + service restart on the Mini):** `tail -F "/Library/Application Support/MiningGuardian/logs/guardian.log" \| grep -E 'Qwen scan analysis\|llm_scan_analyses written\|Knowledge update skipped'` — should show `INFO Qwen scan analysis: ...` followed by `INFO llm_scan_analyses written, now N entries` on the next scan; `Knowledge update skipped: 'total_flags'` should NEVER reappear. Then `python3 -c 'import json; k=json.load(open("/Library/Application Support/MiningGuardian/knowledge.json")); print(len(k.get("llm_scan_analyses",[])))'` — should be ≥ 1 and increment by ~1 per scan. **Recommendation:** because this PR is plain-Python only (no installer / payload / schema / migration changes), no .pkg rebuild is required. Existing installs can pull the fix via `git pull` + service restart. A rebuild remains a sensible next step to roll the fix into fresh-install media for new customer Minis. Status 🟡 until merge. Flips to ✅ on merge. **Update 2026-05-08 PM:** ✅ Merged as PR #168 (squash `33bac6f`, on merge `1327060`). Live install on the Mini surfaced a follow-up B-45 / P-036 — the symlink-replacement bug below. |
| 10ab | P-036 (symlink-preserving knowledge writes — 2026-05-08) — Bundled fix that complements P-034 + P-035. After installing package `2b41764` on the Mac Mini, the canonical `${MG_INSTALL_ROOT}/knowledge/knowledge.json` (3,739,968 bytes, 96 profiles, 133 fingerprints, 176 `llm_scan_analyses`) remained intact, but the P-029 compatibility symlink at `${MG_INSTALL_ROOT}/knowledge.json` was replaced by a root-owned **regular file** of 948 bytes at 15:43 the same day. Root cause: P-035's `core.file_lock.locked_knowledge_update` and `atomic_write_json` write to a temp file in the parent directory and call `os.replace(tmp, knowledge_path)`. When `knowledge_path` is the symlink (which is exactly what every active writer's `_ROOT / "knowledge.json"` resolves to in the install layout), `os.replace` overwrites the **symlink** with a regular file rather than updating the symlink's target. Subsequent reads via the canonical `knowledge/knowledge.json` path therefore continued to work, but reads via the legacy compat path saw a stale 948-byte file — a divergence that would silently grow over time as the two paths drifted. Vision Anchor 1 risk (the LLM IS the product). | ✅ | **Merged 2026-05-08 as PR #169 (squash `906fa4a`, on merge `fab6694`).** Branch `mg/p036-knowledge-symlink-preserve-canonical-resolver` (P-036). **Fix:** `core/file_lock.py` gains a private `_resolve_write_target(path)` helper that, if the supplied path is a symlink whose target's parent directory exists, returns the symlink's target as the rename destination. `locked_knowledge_update` and `atomic_write_json` both route through it: the temp file is created in the **target's** parent directory and `os.replace` lands on the canonical file, leaving the symlink itself untouched. The lock file (`<path>.lock`) is also keyed off the resolved target so two writers — one given the symlink, one given the canonical path — serialize against the same flock. Non-symlink paths (the dev checkout, the broken-symlink edge case, missing paths) fall through unchanged. **Out-of-scope (deliberately):** no writer-side path constants change in this PR — every active writer still uses `_ROOT / "knowledge.json"` and the file_lock helper does the right thing transparently. **Tests on `main` at `fab6694`:** new `tests/test_p036_knowledge_symlink_preserve.py` 9/9 PASS — locked write through symlink preserves the link, canonical file is what actually gets updated, no regression to the live B-45 shape, `atomic_write_json` preserves both relative- and absolute-target symlinks, regular non-symlink paths and missing paths are unchanged, broken-symlink edge case falls back gracefully, end-to-end `KnowledgeManager.save()` through the compat symlink keeps the symlink intact. **Existing suites — none regressed:** `tests/test_p035_knowledge_persistence_hardening.py` 26/26 PASS, `tests/test_p022_discovery_sink.py` 23/23 OK. **Mini state at PR #169 merge time:** the `2b41764` package was already installed on the Mini BEFORE this PR was merged, so the installed Mini binary still contains the symlink-replacement bug. Manual mitigation has been applied (quarantined the 948-byte regular file under `${MG_INSTALL_ROOT}/knowledge/quarantine/`, recreated the symlink with `ln -s knowledge/knowledge.json …` + `chown -h miningguardian:staff` on the link). The Mini's installed tree is NOT git-managed (`git rev-parse --is-inside-work-tree` → `not_git`), so delivery to the Mini requires a fresh `.pkg` rebuild from `main` at `fab6694` — `git pull` + service restart cannot work on this install. Resume plan in `docs/handoffs/HANDOFF_2026-05-08.md` under `⏸ PAUSED EOD 2026-05-08`. **Verification after fab6694 install:** `ls -la "/Library/Application Support/MiningGuardian/knowledge.json"` MUST still show leading `l` (symlink) after the first scan completes — if a regular file appears at that path, P-036 did not take effect. |
| 10u | P-029 — `core/models.py::ParameterRule` lost its `@dataclass` decorator so `GuardianConfig.from_file` crashes with `TypeError: ParameterRule() takes no arguments` after copying `config.example.json` → `config.json` (scanner + `api/ams_alert_listener.py` both fail to start) | ✅ | Merged 2026-05-06 as commit `96e0308` (PR #149) — Branch `mg/p029-parameter-rule-config-load` (P-029) — Round 9b of the customer Mac mini install (post-P-028 build) reached the launchd phase; the operator copied the installer-emitted `config.example.json` to `config.json` and shell-quoted the `.env`, then the scanner and `api/ams_alert_listener.py` both crashed at start-up with `TypeError: ParameterRule() takes no arguments` at `core/models.py:88` (`rules = [ParameterRule(**item) for item in raw.get("rules", [])]`). Stack origins: `core/mining_guardian.py:2630` and `api/ams_alert_listener.py:199` (each calls `GuardianConfig.from_file(config_path)` on boot). **Root cause:** `ParameterRule` was declared as a bare `class` with PEP 526 class-level annotations and field defaults that *look* like a dataclass — but the `@dataclass` decorator was missing, so Python never synthesized an `__init__`. `ParameterRule()` (no args) silently worked because `object.__init__` accepts that, which is why `tests/test_models.py::TestParameterRule` (which constructs `ParameterRule()` and then mutates `rule.key = …` etc.) passed for weeks while the kwarg-construction path inside `GuardianConfig.from_file` was broken in production. The bug surfaced only on the customer Mini because `config.example.json` carries 2 rules (hashrate + chip temp) — every prior install was operator-edited `config.json` written by hand against an older codebase that already had `@dataclass`, and never round-tripped through `from_file` against the current source tree. **Fix:** add `@dataclass` back to `ParameterRule` in `core/models.py`. Make `key` / `operator` / `expected` `Optional` with `None` defaults so the legacy bare-construction path that existing tests depend on (`ParameterRule()` then `rule.key = "x"`) continues to work — those defaults never reach production because `evaluate()` short-circuits to `False` on the resulting unset operator. New `recommended_fix: Optional[Any] = None` and `note: str = ""` defaults stay (they were already correct). One-line P-029 audit comment cites the failing call site and the kwargs the example config emits. **No other module touched** — this is a 1-class fix in `core/models.py`. **No installer / build / payload / notarization / schema / migration changes.** **Tests:** existing `tests/test_models.py` extended (9 → 17 assertions, all green): new `TestParameterRuleConstruction` class drives the failing kwarg path with the exact rule dicts emitted by `core/mining_guardian.py::write_example_config`'s `EXAMPLE_CONFIG` (`expected: 85` / `expected: [40, 80]` — list-shaped JSON-decoded value works with the existing `low, high = self.expected` unpacking); `test_construct_no_args_still_works` locks in the legacy mutate-after-construct pattern existing tests use. New `TestGuardianConfigFromFile` class writes a tempfile mirroring the customer-side `config.example.json` shape and asserts `GuardianConfig.from_file(...)` returns 2 real `ParameterRule` instances whose `evaluate()` answers correctly on representative actual values, plus two negative paths (`rules` empty, `rules` key missing entirely — both must produce `cfg.rules == []`). New `TestExampleConfigShapeDrift::test_fixture_keys_match_source` greps `core/mining_guardian.py` for the EXAMPLE_CONFIG rule keys (`key`, `operator`, `expected`, `severity`, `recommended_fix`, `note`) so a future trim of either side fails loudly with a self-pointing message; the test fixture is duplicated inline rather than imported from `core.mining_guardian` because that module pulls heavy deps (`websocket`, etc.) that the model unit tests should not require. Test environment safety: `setup_method`/`teardown_method` save and restore `AMS_*` env vars so the test temporarily overriding them does not contaminate subsequent tests. **Operator cleanup before next reinstall** (the post-P-028 install fully bootstrapped — all 10 LaunchDaemons + 11 scheduled jobs are loaded, but every service is exit-127-looping at boot because `from_file` raises before the FastAPI / scanner main loops can start): use the installed uninstaller — `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --yes --purge-data --purge-logs`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. Detection (operator-side, after install): `launchctl print system/com.miningguardian.scanner \| grep -E 'last exit code'` shows `last exit code = 0` (or running pid > 0); `tail -n 50 /Library/Application\ Support/MiningGuardian/logs/scanner.err.log` shows no `TypeError: ParameterRule() takes no arguments`. **Out-of-scope (and deliberately not in this PR):** the broader question "should the installer write `config.json` directly from the customer's Desktop conf instead of only emitting `config.example.json`?" was raised in the handoff but is held for a separate row — that's a postinstall-shape change with its own test surface (Desktop conf → `config.json` mapping, `.env` keys overlap, dry-run handling) and conflating it with this 1-class TypeError fix would violate the §"Scope discipline during edits" rule. The narrow contract restored here — `config.example.json` → manual copy → `config.json` → `GuardianConfig.from_file` succeeds — is exactly what the customer just did and is expected to keep working under any future installer-writes-config flow. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10v | P-029 — postinstall.sh writes shell-unsafe `.env` (customer name `R & D` parses as `MG_CUSTOMER_NAME=R` + `&` + `D`; every launcher's `set -a; source .env` exits 127 with `D: command not found`); also (a) `mg` Postgres role keeps the prior install's password on retry over existing `${MG_INSTALL_ROOT}/postgres-data/` so dashboard root returns 500 with `password authentication failed for user "mg"`; (b) no `config.json` materialized at install time so scanner / approval_api / ams_alert_listener crash-loop on the missing file. | 🟡 | Branch `mg/p029-postinstall-env-shell-safe-and-config-json` (this PR, 2026-05-06, P-029) — Round-9b smoke on the customer Mac mini (post-`23a5af7` install — first build to clear P-028) found three follow-on bugs once the install completed cleanly. (1) **Shell-unsafe .env values.** `step_drop_dotenv` wrote `KEY=${VALUE}` raw, so customer name `R & D` produced `MG_CUSTOMER_NAME=R & D` on disk. Every launcher wrapper does `set -a; source "${ENV_FILE}"; set +a` — bash interprets the line as `MG_CUSTOMER_NAME=R` (assignment) + `&` (background) + `D` (lookup of `D`). Customer Mini logged `D: command not found` for every service, exit 127, all 10 LaunchDaemons failed to start. Same trap fires for `&`, `$`, `` ` ``, `"`, `'`, `;`, `(`, `)`, `\`, `*`, `?`, `[`, `]`, `<`, `>`, `|`, `#`, leading/trailing whitespace, and globs that may match a real file. (2) **Stale Postgres password on retry.** `provision_postgres` (`lib/install_colima.sh` L355-369) runs `docker rm -f <container>` then `docker run … -v ${pgdata}:/var/lib/postgresql/data -e POSTGRES_PASSWORD="$MG_DB_PASSWORD"`. Postgres only honors `POSTGRES_PASSWORD` on FIRST initdb of a fresh data directory; a re-install over an existing `pgdata` volume inherits the prior install's role passwords and ignores the new env var. Round-9b followed earlier failed installs whose `mg` role still carried a prior `openssl rand -hex 32` value — `psql -U mg` from the dashboard hit `password authentication failed for user "mg"` over TCP 127.0.0.1:5432, dashboard `/` returned 500. `docker exec psql -U mg` from inside the container uses peer auth on the unix socket and so worked — that masked the bug through migrations and the catalog seed apply. (3) **No `config.json` materialized.** Every long-running service (`core/mining_guardian.py`, `api/approval_api.py`, `api/ams_alert_listener.py`, `core/overnight_automation.py`) reads `config.json` from the install root for profile_map, model_aliases, miner_filters, scan/slack intervals, and approval_mode. Pre-P-029 the postinstall never wrote that file, so `core/mining_guardian.py::__main__` fell into its `write_example_config()` fallback, exited with `Create config.json from config.example.json, then re-run.`, scanner / approval_api / ams_alert_listener crash-looped, dashboard root returned 500. **Fix:** three coordinated changes in `installer/macos-pkg/scripts/postinstall.sh` plus one in `build_pkg.sh`. (1) New `_shq` helper (single-quote + `'\''` close-reopen escape). `step_drop_dotenv` pre-quotes every customer-tunable + secret value into a *_Q twin (`CUSTOMER_NAME_Q`, `AMS_*_Q`, `SLACK_*_Q`, `_MG_PWD_Q`, `_CAT_KEY_Q`, `_INT_SEC_Q`, etc.) BEFORE the heredoc and the heredoc references ONLY the *_Q variant. The on-disk .env round-trips arbitrary input — `R & D`, `&`, `$`, `` ` ``, `"`, `'`, `;`, `(`, `)`, `\`, `*`, `?`, leading/trailing whitespace, glob chars — exactly through `set -a; source` regardless of customer input. (2) New `step_reconcile_postgres_password` runs immediately after `provision_postgres` returns ready, before migrations. It always issues `ALTER USER mg WITH PASSWORD '...'` against the running container via stdin (`printf | docker exec -i psql`), so the password value never appears in `ps`. Idempotent: on a fresh initdb the new password equals the env-supplied password (no-op); on a re-install over existing pgdata it heals the role. Followed by a TCP-auth verification (`psql -h 127.0.0.1 -U mg -d postgres`) so a regression here surfaces with a clear log line BEFORE migrations begin. Hardens against any future change to `provision_postgres` that breaks first-time password setup. (3) New `step_drop_config_json` writes `${MG_INSTALL_ROOT}/config.json` from the vendored `config_template.json` merged with `env:KEY` placeholders for `ams_email`/`ams_password`/`ams_workspace_id`/`slack_webhook_url`/`slack_bot_token` (so `GuardianConfig._resolve` reads the values from the .env every launcher already sources — no secrets in `config.json`), `dry_run` from `MG_DRY_RUN`, `approval_mode` defaulting to `"manual"` (D-2). Idempotent: refuses to overwrite an existing `config.json` so operator edits to `profile_map` survive a re-install. (4) `build_pkg.sh` 4a rsync gains `--include 'config/***'` so `config_template.json` ships in the payload at `<payload>/config/config_template.json`. Reconcile + drop_config_json wire into `main()` between `provision_postgres → step_apply_migrations` and `step_create_venv → step_install_plists_and_bootstrap` respectively. Exit code 31 reused for reconcile (Postgres provisioning class) and config-template miss (consistent with secret-related bail-outs). **Tests:** new `tests/installer/test_postinstall_env_shell_safe.sh` (64 assertions, all green) — §1 file presence + bash -n parse, §2 P-029 audit marker, §3 `_shq` helper defined and uses canonical `'\''` escape, §4 step_drop_dotenv computes a *_Q twin via `_shq` for every customer-tunable + secret value, §5 .env heredoc references ONLY *_Q twins for trap-prone keys (no raw `${CUSTOMER_NAME}` etc.), §6 functional smoke — extracted `_shq` round-trips 22 pathological inputs (`R & D`, `&`, `$`, `` ` ``, `"`, `'`, `\`, `;`, `|`, leading/trailing space, `*?[abc]`, `$VAR`, `(parens)`, `<redirect>`, `{braces}`, tab-embedded, plain, empty, double-amp-nest) under `set -a; source`, §7 functional smoke — full `step_drop_dotenv` driver with `CUSTOMER_NAME='R & D'` plus an AMS_PASSWORD containing `& ' $()` round-trips through the launcher's exact `set -a; source` pattern, §8 counter-test — the OLD unquoted heredoc style FAILS for `R & D` (proves the test catches the regression), §9 `step_reconcile_postgres_password` defined, ordered after `step_provision_postgres` and before `step_apply_migrations`, sends the password via stdin not `psql -c`, §10 `step_drop_config_json` defined, ordered after `step_create_venv` and before `step_install_plists_and_bootstrap`, has overwrite guard, `build_pkg.sh` includes `config/***`, source template present, §11 functional smoke — drives `step_drop_config_json` against a scratch payload, asserts JSON shape (`env:` placeholders, profile_map present, approval_mode=manual, dry_run=true) and the second-run idempotence (operator-edited file preserved). `tests/installer/test_postinstall_env_handoff.sh` extended +1 OK (the existing extracted-driver pattern now also pulls `_shq`); password / catalog / internal extraction sed strips the new surrounding single quotes so the leak-protection assertions still grep the install log for the raw secret values. All 24 installer suites green: `test_postinstall_env_shell_safe` 64/64, `test_postinstall_env_handoff` 38/38, `test_postinstall_customer_info` 76/76, `test_postinstall_venv` 37/37, `test_postinstall_payload_path` 12/12, `test_postinstall_helper_user_resolver` 26/26, `test_postinstall_user_resolver` 12/12, `test_postinstall_python_runtime` 38/38, `test_postinstall_catalog_seed` 24/24, `test_postinstall_scheduled_jobs` 115/115, `test_postinstall_cocoa_alert_bounded` 9/9, `test_pkg_scripts_naming` 17/17, `test_uninstall_script` 50/50, `test_p025_installer_resources` 27/27, `test_postinstall_colima_path` 21/21, `test_absolute_logs_path` 20/20, `test_d20_importer_payload_reconciliation` 32/32, `test_catalog_seed_schema_compat` 20/20, `test_release_notes_version_drift` 9/9, `test_wheel_resign` 17/17, `test_build_pkg_vz_entitlement`, `test_migration_007_prereqs` 8/8, `test_preinstall_arch_gate` 11/11, `test_installer_copy`. Shellcheck baselines unchanged (postinstall 3 = SC2034 + 2× SC2024). **Operator cleanup before next reinstall:** the `23a5af7` install brought the system fully up but with broken services (every LaunchDaemon exit 127, no working `mg` Postgres password, no `config.json`). Use the installed uninstaller — `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --yes --purge-data --purge-logs`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. Expected new postinstall log lines: `INFO Postgres role 'mg' password reconciled (P-029)` → `INFO Postgres TCP auth verified for role 'mg' (P-029)` → all 8 migrations apply → catalog seed verified at 320 rows → `INFO writing /Library/Application Support/MiningGuardian/config.json` → `INFO wrote config.json at /Library/Application Support/MiningGuardian/config.json (P-029)` → all 10 LaunchDaemons + 11 scheduled-job plists bootstrap → first-run baseline scan writes `${MG_INSTALL_ROOT}/logs/guardian.log` (P-028 contract). Detection (operator-side, after install): `set -a; source "/Library/Application Support/MiningGuardian/.env"; set +a; printf '%s\n' "$MG_CUSTOMER_NAME"` prints the customer name verbatim with no `command not found` errors; `psql -h 127.0.0.1 -U mg -d mining_guardian -c 'SELECT 1' </dev/null` (with the .env-sourced password) returns `1`; `cat "/Library/Application Support/MiningGuardian/config.json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ams_email"])'` prints `env:AMS_EMAIL`; `launchctl print system/com.miningguardian.scanner | head` shows the service running. Round-10 install GATED on this PR merging. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10t | P-028 — `core/mining_guardian.py::_setup_logging` resolves `Path("logs")` relatively; first-run baseline scan crashes with `PermissionError: [Errno 13] Permission denied: 'logs'` because postinstall's CWD is the Installer.app scripts sandbox (B-19) | 🟡 | Branch `mg/p028-absolute-logs-path` (this PR, 2026-05-06, P-028) — Round 9b of the v1.0.3 customer Mac mini install (`MiningGuardian-1.0.3-2a3de50c4af2.pkg`, main `2a3de50`) installed cleanly through postinstall, all 10 services + 11 scheduled jobs bootstrapped. Then the first-run baseline scan crashed in `_setup_logging` (line 63 in HEAD): `PermissionError: [Errno 13] Permission denied: 'logs'` at `log_dir.mkdir(exist_ok=True)`. **Root cause:** `step_baseline_scan` invoked the scanner via `sudo -u miningguardian python "${MG_INSTALL_ROOT}/core/mining_guardian.py" --once` from postinstall's CWD — the Installer.app scripts sandbox at `/tmp/PKInstallSandbox.<rand>/Scripts/...`. With no `cd` and no env var contract, `Path("logs")` resolved against the sandbox CWD; the `mkdir` call then tried to create a relative `logs/` directory which the unprivileged miningguardian user cannot write into the sealed system volume. The launchd-managed services do NOT hit the same trap because every service plist sets `WorkingDirectory=/Library/Application Support/MiningGuardian` AND every launcher wrapper does `cd "${INSTALL_ROOT}"` before exec — but that mitigation only works for the launchd code path, not the postinstall direct invocation, and is silent if any future caller drops the cd. **Fix:** three coordinated changes. (1) **`core/mining_guardian.py`** — new `_resolve_log_dir()` helper that resolves the logs directory in three tiers: (a) `MG_LOG_DIR` env var (explicit override; expanduser+resolve), (b) `MG_INSTALL_ROOT` env var (canonical install root → `<root>/logs`), (c) the parent-of-this-file path resolved at module load (`_ROOT / "logs"` where `_ROOT = Path(__file__).resolve().parent.parent`). `_setup_logging()` now calls the helper and uses `mkdir(parents=True, exist_ok=True)`. (2) **`installer/macos-pkg/scripts/postinstall.sh::step_baseline_scan`** — `cd "${MG_INSTALL_ROOT}"` AND pass `MG_INSTALL_ROOT="${MG_INSTALL_ROOT}"` via `/usr/bin/env` into the scanner subprocess (belt + suspenders). (3) **Every launcher wrapper** (10 services + the generic `scheduled_job_launcher.sh`) — `export MG_INSTALL_ROOT="${INSTALL_ROOT}"` before `exec`'ing python, so any future caller that drops the `cd` still picks the correct logs dir, and any module that uses the scanner's `_resolve_log_dir()` indirectly (Bucket-9 console, scheduled jobs) gets the same behavior. **No `build_pkg.sh`, payload, notarization, schema, or migration changes** — pure source fix in one Python helper plus shell glue. **Tests:** new `tests/installer/test_absolute_logs_path.sh` (20 assertions, all green) — §1 `_resolve_log_dir` defined in `core/mining_guardian.py`, §2 `_setup_logging` body calls `_resolve_log_dir()`, §3 no code-level `Path("logs")` literal anywhere under `core/` (with negative control proving the test catches the regression), §4 `step_baseline_scan` exports `MG_INSTALL_ROOT` and `cd`s into install root, §5 every one of the 10 launcher wrappers exports `MG_INSTALL_ROOT`, §6 runtime — with `MG_INSTALL_ROOT="/tmp/.../Application Support/MiningGuardian"` (path with a space) the resolver lands on `<root>/logs` from a CWD elsewhere, §7 runtime — fallback to repo-root/logs when both env vars are unset, plus a negative control that runs the OLD `Path("logs").resolve()` from the same CWD and asserts it lands somewhere else (proves the test catches the bug), §8 runtime — `MG_LOG_DIR` override wins, §9 P-028 audit markers in both source files. **Sister-test sanity:** `tests/installer/test_postinstall_payload_path.sh` 12/12 green (no regression). Adjacent suites unaffected (no shell-flag or path-resolution changes elsewhere). **Exit-127 services note:** the customer-side smoke output also showed launchd services failing with exit 127. The plists set `WorkingDirectory` and the launchers `cd "${INSTALL_ROOT}"`, so the launchd path SHOULD avoid the relative-logs PermissionError — exit 127 typically means the wrapper's `exec` could not find the venv python or the `set -a; source .env` failed on a malformed key. P-028 does NOT directly diagnose exit-127 (no launchd error log was captured); but the launcher hardening here removes one ambiguity (every wrapper now exports `MG_INSTALL_ROOT` so a future `_resolve_log_dir()` call from any module under launchd cannot silently fall back to a CWD-based path). A separate row will track exit-127 once the operator captures the launchd error log per `tail -F /Library/Application\ Support/MiningGuardian/logs/scanner.err.log` immediately after `launchctl bootstrap`. **Operator cleanup before next reinstall** (the `2a3de50` install got past every postinstall step including all 10 LaunchDaemons + 11 scheduled jobs being installed; the install ROOT is fully laid down): use the installed `bin/uninstall.sh` — `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --yes --purge-data --purge-logs`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. The new postinstall log should reach `INFO triggering first-run baseline scan (non-blocking)` and the scanner subprocess should write `${MG_INSTALL_ROOT}/logs/guardian.log` instead of crashing with PermissionError. Detection (operator-side, after install): `ls "/Library/Application Support/MiningGuardian/logs/"` shows `guardian.log` plus `guardian_<DATE>.log`; no stray `/logs/` directory exists under `/`. Status 🟡 until merge + new build; flips to ✅ on merge. Closes B-19. |
| 10s | P-027 — postinstall step_create_venv: quote every command-exec use of `${py312}` so the resolved interpreter under `/Library/Application Support/MiningGuardian/runtime/python/bin/python3.12` works (path contains a space) | 🟡 | Branch `mg/p027-postinstall-py312-quoting` (this PR, 2026-05-06, P-027) — Round 9 of the Mac mini install on the post-P-026 build (`MiningGuardian-1.0.3-d0ba6c40a323.pkg`, main `d0ba6c4`) progressed past every prior gate AND past the new P-026 installer-owned-runtime resolver (log printed `INFO using installer-owned Python interpreter (packaged-flat): /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12`), then exited 38 with `FATAL (38) resolved Python interpreter /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12 reports version '', expected '3.12'; vendored wheels are cp312 only (P-026)`. The same log line carried the smoking gun: `(/tmp/PKInstallSandbox.../postinstall: line 1279: /Library/Application: No such file or directory)`. **Root cause:** three lines in `step_create_venv` (1279/1281/1289 in the post-P-026 file) used `$(${py312} --version 2>&1)` and `${py312} -c '…'` — unquoted command-substitutions of a path containing a space. Word-splitting ran `/Library/Application` as the command, which exited 127 with an empty stdout. The version-probe substitution returned the empty string and the next assertion `[[ "$py_ver" != "3.12" ]]` fired exit 38. The bug was masked through P-013→P-026 because the resolved path used to be Homebrew (`/opt/homebrew/...`, no spaces); P-026's installer-owned runtime moved the resolved path under `MG_PKG_PAYLOAD=/Library/Application Support/MiningGuardian/`, exposing the latent quoting bug. The venv-create call at line 1299 was already correctly quoted (`"$py312" -m venv "$venv_dir"`) — only the version-probe sites needed fixing. **Fix:** quote every command-exec use of `$py312` / `${py312}` in `installer/macos-pkg/scripts/postinstall.sh::step_create_venv`. (1) Line 1288 — `$("$py312" --version 2>&1)` (was `$(${py312} --version 2>&1)`). (2) Line 1290 — same fix in the WARN branch for the dev/smoke-test fallback. (3) Line 1298 — `$("$py312" -c 'import sys; …')`. Test-context uses (`[[ -z "$py312" ]]`, `[[ -x "$py312" ]]`) and string-interpolation in error messages were already safe. New explanatory comment cites P-027 with the failure log line. **No `build_pkg.sh`, payload, notarization, or migration changes** — pure shell quoting fix in postinstall.sh, ~7 lines touched. **Tests:** `tests/installer/test_postinstall_python_runtime.sh` extended from 29 → 38 assertions: §10 static — every command-exec use of `${py312}` is quoted (grep guard against `$(${py312} ...)` and leading-word `${py312} ...` outside log/fail string contexts), the three known-correct quoted forms are present, and a `P-027` audit marker exists in `postinstall.sh`. §11 functional smoke — builds a scratch tree at `${TMPDIR}/Application Support/MiningGuardian/runtime/python/bin/python3.12` (path contains a space), drops a tiny `python3.12` shim that prints `Python 3.12.7` and `3.12`, runs the same `$("$py312" --version)` / `$("$py312" -c '...')` patterns, asserts both succeed; counter-test runs the OLD unquoted form and asserts it fails (so the test actually catches the regression). All 22 installer suites green: `test_postinstall_python_runtime` 38/38, `test_postinstall_venv` 37/37, `test_postinstall_payload_path` 12/12, `test_postinstall_helper_user_resolver` 26/26, `test_postinstall_user_resolver` 12/12, `test_postinstall_colima_path` 21/21, `test_postinstall_customer_info` 76/76, `test_postinstall_catalog_seed` 24/24, `test_postinstall_scheduled_jobs` 115/115, `test_postinstall_cocoa_alert_bounded` 9/9, `test_pkg_scripts_naming` 17/17, `test_uninstall_script` 50/50, `test_p025_installer_resources`, `test_d20_importer_payload_reconciliation` 32/32, `test_catalog_seed_schema_compat` 20/20, `test_release_notes_version_drift`, `test_wheel_resign` 17/17, `test_build_pkg_vz_entitlement`, `test_migration_007_prereqs`, `test_postinstall_env_handoff`, `test_preinstall_arch_gate`, `test_installer_copy`. **Operator cleanup before next reinstall** (the `d0ba6c4` install got past venv-resolver + version-probe but exit-38'd before the venv was created, before LaunchDaemons, before `bin/uninstall.sh` was installed): `sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null \|\| true`, `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null \|\| true`, `sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null \|\| true`. Then operator: rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls — `${HOME}/MiningGuardian-vendor/python-runtime/` is already populated from the P-026 round so no Block Pre-B re-run is required. Expected new postinstall log lines: `INFO using installer-owned Python interpreter (packaged-flat): /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12 (Python 3.12.7)` (now correctly populated) → `INFO created venv at /Library/Application Support/MiningGuardian/venv` → `INFO venv ready at ...` → `step_install_plists_and_bootstrap`. Round-10 install GATED on this PR merging. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10r | P-026 — Installer-owned Python 3.12 runtime; remove Homebrew prerequisite from customer Mac mini install path | ✅ | Merged 2026-05-05 as commit `d0ba6c4` — Branch `mg/p026-installer-owned-python-runtime` (2026-05-05, P-026) — supersedes the implicit Homebrew + python@3.12 prerequisite that bit Round 9 of the Mac mini install. P-025 (row 10q) merged as `00720ab` (PR #144) and unblocked Round 9; the post-P-025 build (`MiningGuardian-1.0.3-00720ab71cc4.pkg`) was installed on the customer Mac mini and progressed past every prior gate (env keys exported, Colima VZ started, postgres image loaded, `mining_guardian` ready, all 8 operational migrations applied, `mining_guardian_catalog` created, `deploy_schema.sql` applied — `Schema deployment complete \| sources_count 23 \| manufacturers_count 17`, **catalog seed verified at 320 rows**, all 9 launcher wrappers installed). Then `step_create_venv` exited 38 with `FATAL (38) python3.12 not found on this Mac; install Homebrew + python@3.12 before running the .pkg (operator setup manual covers this)`. **Root cause:** pre-P-026 `step_create_venv` resolved Python 3.12 from `/opt/homebrew/opt/python@3.12/bin/python3.12` (the Apple Silicon Homebrew default), with `/usr/local/opt/python@3.12/bin/python3.12` and `command -v python3.12` as fallbacks. The customer Mac mini did not have Homebrew installed, and was not expected to — the Mini ships as a single-purpose appliance. Operator decision (Rob, 2026-05-05): "yes include it in the installer and whatever else might pop up as the install keeps going". Locked as **D-27** in `docs/DECISIONS.md`. **Fix:** three coordinated changes in this PR. (1) **build_pkg.sh** — new `step_4i_stage_python_runtime` (inside `step_4_assemble_payload`, between the bulk runtime rsync and the wheelhouse rsync). Operator populates `${HOME}/MiningGuardian-vendor/python-runtime/` once with python-build-standalone (`install_only_stripped` for `aarch64-apple-darwin`, Python 3.12.x). Validates: vendor dir exists; `python3.12` binary present (accepts both flat `bin/python3.12` and framework `Python.framework/Versions/3.12/bin/python3.12` layouts); binary is Mach-O; reports Python 3.12.x; `import venv` succeeds; rsync into `<payload>/runtime/python/`; post-rsync sanity probe. Any failure exits 43 with self-pointing log line. The bulk runtime rsync at step 4c excludes `python-runtime/` so step 4i is the single owner of the python tree. (2) **build_pkg.sh step 4b** — no new code path. The existing recursive `find $runtime_dir` Mach-O walk picks up every binary under `<payload>/runtime/python/` automatically. (3) **postinstall.sh::step_create_venv** — resolves the packaged interpreter FIRST (Tier 1 = `${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12` flat OR `${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12` framework); Tier 2 (dev / smoke-test fallback only) = Homebrew + PATH; logged as `WARN`. Sanity-checks Python 3.12.x — refuses non-3.12 with a clear error. New error string on miss points at `build_pkg.sh::step_4i_stage_python_runtime` and `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B". **Operator runbook:** new `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B — populate the Python runtime" with python-build-standalone download + extraction + verification, plus the note to re-run Block Pre-A's `pip download` against the newly-vendored interpreter so wheel ABI tags match. **Tradeoff:** P-026 is a complete source fix + build guardrail. It does NOT ship a usable `.pkg` until the operator runs Block Pre-B once; until then `make pkg` exits 43 at step 4i with a clear pointer. Deliberately favors a hard build failure over a notarization round-trip on a half-broken .pkg. **Tests:** new `tests/installer/test_postinstall_python_runtime.sh` (29 assertions, all green). `tests/installer/test_postinstall_venv.sh` extended with §9 (postinstall) + §10 (build_pkg). All 22 installer suites green. **Operator cleanup before next reinstall** (the `00720ab` install got past venv / no LaunchDaemons / no `bin/uninstall.sh`): `sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null \|\| true`, `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null \|\| true`, `sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null \|\| true`. Then operator: (a) populates `${HOME}/MiningGuardian-vendor/python-runtime/` per `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B"; (b) re-runs Block Pre-A's `pip download` against the new vendored interpreter; (c) rebuilds + signs + notarizes a new `.pkg` from the merged main; (d) reinstalls. Expected new postinstall log lines: `INFO using installer-owned Python interpreter (packaged-flat): ...` → `INFO created venv at ...` → `INFO venv ready at ...` → `step_install_plists_and_bootstrap`. Round-10 install GATED on this PR merging. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10q | P-025 — Pre-build full preflight audit P0 fixes (A-2 catalog schema `primary_source_id` default; A-3 stage installer-owned launchd/uninstall.sh resources into payload + repoint postinstall path resolvers; A-4 add `scripts/***` to payload rsync) | ✅ | **Merged 2026-05-05 as commit `00720ab` (PR #144).** Branch `mg/p025-preflight-p0-fixes` (2026-05-05, P-025) — supersedes the original "preflight audit subagent" placeholder for row 10q (the audit ran, found three P0 blockers, this PR fixes them). P-024 (row 10p, merged as `6a48a82`) cleared the manufacturer-column drift. Before rebuilding the .pkg, a full pre-build audit caught three P0 blockers chained behind P-024: A-2 — `intelligence-catalog/seed-data/intelligence_catalog_schema.sql:822` declares `primary_source_id UUID NOT NULL REFERENCES knowledge.sources(id)` but all 320 `INSERT INTO hardware.miner_models` rows in `seed_miner_models.sql` omit it; the seed transaction would have rolled back on the very first row with `null value in column "primary_source_id" violates not-null constraint` (same exit-39 path as P-024, one column to the right). **Fix:** add `DEFAULT 'a0000000-0000-0000-0000-00000000000e'::uuid` to the schema column — that UUID is the `catalog_research_2026` row already seeded by `deploy_schema.sql:78`, applied before `seed_miner_models.sql`. A-3 — `${SCRIPT_DIR}/../resources/...` does not exist at install time. P-017 fixed `MG_PKG_PAYLOAD` resolution but `postinstall.sh` still read four installer-owned trees (PLISTS_SRC, LAUNCHERS_SRC, SCHEDULED_PLISTS_SRC, UNINSTALL_SH_SRC) through `${SCRIPT_DIR}/../resources/...`, which resolves inside Installer.app's private scripts sandbox where productbuild --resources content does NOT land. Service plist install (exit 37), scheduled bootstrap (exit 40), and `step_install_uninstall_script` (exit 37) would have all hit this. **Fix:** new `build_pkg.sh` step 4k stages `installer/macos-pkg/resources/launchd/` and `resources/uninstall.sh` into the customer payload at `<payload>/installer-resources/`; `postinstall.sh` adds an `INSTALLER_RESOURCES_SRC` resolver (payload-first / dev-fallback) and the four readonly source-path constants derive from it. The legacy `installer/macos-pkg/resources/` tree continues to feed `productbuild --resources` for Distribution.xml / branding / welcome / conclusion / license metadata-only content. A-4 — 6 of 11 scheduled-job plists invoke entrypoints under `scripts/*.{py,sh}` but `scripts/***` was missing from the 4a rsync include list; plists would install and every scheduled run would exit 1 with `entrypoint not found`. **Fix:** add `--include 'scripts/***'` plus a step-4b assertion that `<payload>/scripts/` plus the 6 scheduled `scripts/` entrypoints are readable after the rsync. The `tests/run_benchmark.py` entrypoint is a known pre-existing latent bug (the .py never existed in HEAD, the .sh does — see plist comment + `docs/LATENT_BUGS.md`) and is NOT in P-025 scope. **Tests:** new `tests/installer/test_p025_installer_resources.sh` (27 assertions, all green) — §1 `bash -n` parses both `postinstall.sh` and `build_pkg.sh`, §2 `INSTALLER_RESOURCES_SRC` declared with payload-first / dev-fallback two-branch resolver and marked readonly, §3 all four readonly source-path constants (`PLISTS_SRC`, `LAUNCHERS_SRC`, `SCHEDULED_PLISTS_SRC`, `UNINSTALL_SH_SRC`) derive from `INSTALLER_RESOURCES_SRC`, §4 NO install-time path-constant assignment in `postinstall.sh` still reads `${SCRIPT_DIR}/../resources/...` (comments + dev-fallback exempt), §5 `build_pkg.sh` step 4k stages `resources/launchd/` and `resources/uninstall.sh` into `<payload>/installer-resources/`, §6 `build_pkg.sh` asserts `<payload>/scripts/` after the 4a rsync, §7 4a rsync list contains `--include 'scripts/***'`, §8 every scheduled-plist `ProgramArguments` entrypoint resolves in the source tree (or is the documented latent bug). `test_catalog_seed_schema_compat.sh` extended with §6 (3 assertions: schema column carries `DEFAULT '<canonical UUID>'`, `deploy_schema.sql` still seeds the canonical UUID, seed file still omits the column). All 21 installer tests green: `test_uninstall_script.sh`, `test_postinstall_payload_path.sh`, `test_postinstall_scheduled_jobs.sh`, `test_pkg_scripts_naming.sh`, `test_d20_importer_payload_reconciliation.sh`, etc. **No new install attempt on the Mini before this PR merges** (per operator instruction 2026-05-05; D-26 gate). Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10p | P-024 — `seed_miner_models.sql` `INSERT INTO hardware.manufacturers` block uses non-existent columns (`full_name`, `country`, `website`, `notes`); schema has `legal_name` / `common_name` / `country_of_origin` / `website_url` | ✅ | Merged 2026-05-05 as commit `6a48a82` (PR #142) — confirmed in Round 8 (`MiningGuardian-1.0.3-dd482af746ad.pkg`): postinstall reached `step_provision_catalog_db_and_seed`, created `mining_guardian_catalog`, applied `intelligence_catalog_schema.sql`, then exited 39 inside `seed_miner_models.sql` on the schema mismatch this PR fixes. Branch `mg/p024-catalog-seed-manufacturers-schema` (2026-05-05, P-024) — P-023 (row 10o, merged as `dd482af`) cleared the migration-007 prereq bug. `MiningGuardian-1.0.3-dd482af746ad.pkg` was installed on the customer Mac mini; postinstall progressed through every prior gate (env keys exported, Colima VZ started, postgres image loaded, `mining_guardian` ready, all 8 operational migrations applied — 001 → 006 → 006a → 007 included, `mining_guardian_catalog` created, `deploy_schema.sql` applied — log printed `Schema deployment complete \| sources_count 23 \| manufacturers_count 17`). Then `seed_miner_models.sql` line 39 hard-failed: `ERROR: column "full_name" of relation "manufacturers" does not exist / [postinstall] FATAL (39) seed_miner_models.sql apply failed against mining_guardian_catalog`. **Root cause:** `intelligence-catalog/seed-data/seed_miner_models.sql` opened its BEGIN transaction with `INSERT INTO hardware.manufacturers (brand, full_name, country, website, notes) VALUES …` for 11 brands. Those four non-`brand` column names are wrong — the schema (`intelligence_catalog_schema.sql` lines 445–473) has `legal_name` (NOT NULL), `common_name` (NOT NULL), `country_of_origin`, `website_url`, `metadata JSONB`. The block was dead duplicate code anyway: `deploy_schema.sql` (which postinstall runs *before* `seed_miner_models.sql`) already seeds **all 17 manufacturer rows** at lines 92–116 using the correct column names, covering every brand the broken block tried to insert. The seed file was generated 2026-04-11 by `intelligence-catalog/seed-data/compile_all_miners.py::write_sql` BEFORE the catalog schema N6 (2026-04-27) settled the canonical column names, and never got refreshed — the broken preamble survived the catalog-schema cleanup. **Fix:** delete the 13-line `INSERT INTO hardware.manufacturers (...)` block (former lines 25–39) from `seed_miner_models.sql`. Replace with a comment that points at `deploy_schema.sql` as the single owner of manufacturer seeding. `BEGIN;` / `COMMIT;` envelope and the 320 `INSERT INTO hardware.miner_models` rows stay byte-untouched. Make the same change in `compile_all_miners.py::write_sql` preamble so future `python compile_all_miners.py` regenerations don't re-emit the broken block. Idempotency on re-install: preserved (the removed block was already `ON CONFLICT (brand) DO NOTHING` and `deploy_schema.sql` owns the rows). **No `build_pkg.sh`, postinstall, payload-rsync, or notarization-relevant change** — pure SQL/Python source fix; the catalog-seed step in postinstall is unchanged. **Tests:** new `tests/installer/test_catalog_seed_schema_compat.sh` (17 assertions, all green) — §1 file presence, §2 `seed_miner_models.sql` does NOT `INSERT INTO hardware.manufacturers` (P-024 regression — the broken block must never come back), §3 every column referenced in any `INSERT INTO hardware.<table> (...)` in `seed_miner_models.sql` exists as a `CREATE TABLE` column in the catalog schema bundle (`intelligence_catalog_schema.sql` + v2 + v3 + `staging_schema.sql`) — awk extracts 1232 unique column identifiers from the schema and checks all 5440 column references across 320 INSERT blocks resolve, catching schema/seed column drift on any catalog table not just `manufacturers`, §4 `hardware.manufacturers` schema has the canonical column names AND `seed_miner_models.sql` does NOT reference the broken names, §5 `deploy_schema.sql` seeds every brand referenced by the seed file (14 brands). All adjacent installer suites still green: `test_postinstall_catalog_seed.sh` 24/24 (seed row count + apply ordering), `test_postinstall_env_handoff.sh` 38/38, `test_migration_007_prereqs.sh`, `test_d20_importer_payload_reconciliation` 32/32. **Operator cleanup before next reinstall** (the `dd482af` attempt got far enough to bring up Postgres, apply all 8 operational migrations, create `mining_guardian_catalog`, and apply the catalog schema; the catalog DB exists but its `hardware.miner_models` table is empty because the seed transaction rolled back; `bin/uninstall.sh` is NOT installed yet — `step_install_uninstall_script` runs after `step_provision_catalog_db_and_seed`). Manually: `sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null \|\| true`, `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null \|\| true`, `sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null \|\| true`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. The new postinstall log should reach `INFO applying catalog schema (deploy_schema.sql)`, then `Schema deployment complete \| sources_count 23 \| manufacturers_count 17`, then `INFO seeding 320 Bitcoin SHA-256 miner models into mining_guardian_catalog`, then `INFO catalog seed verified: hardware.miner_models has 320 rows`, then `step_install_ollama_and_pull_model`. Detection (operator-side, after install): `docker exec mining-guardian-db psql -U mg -d mining_guardian_catalog -tAc "SELECT count(*) FROM hardware.miner_models;"` returns 320, `… "SELECT count(*) FROM hardware.manufacturers;"` returns 17. **Future sessions: never add an `INSERT INTO hardware.manufacturers` to `seed_miner_models.sql`. Manufacturers are owned by `deploy_schema.sql` exclusively. The new regression test §2/§4 will catch any attempt to put manufacturer inserts back into the seed file.** Round-9 install remains BLOCKED by D-26 until the preflight audit (P-025, row 10q) and any P0 fixes it surfaces are merged. |
| 10o | P-023 — Migration 007 layer-2 resolver fails on fresh `mining_guardian` DB: missing `uuid-ossp` extension, `set_updated_at()` function, and FK target tables | ✅ | Merged 2026-05-05 as commit `dd482af` — Branch `mg/p023-migration-007-layer2-prereqs` (2026-05-05, P-023) — P-022 (row 10n, merged as `b66b864`) cleared the env-handoff bug. `MiningGuardian-1.0.3-b66b86440400.pkg` was installed on the customer Mac mini; postinstall progressed through every prior gate (env keys exported, limactl present, Colima VZ started, postgres image loaded, `mining_guardian` ready, migrations 001/003/004_drop_dead_stubs/004_system_settings/005/006 applied). Then `step_apply_migrations` failed inside `007_layer2_resolver.sql` with `ERROR: function uuid_generate_v4() does not exist / LINE 2: id UUID PRIMARY KEY DEFAULT uuid_generate_v4() / [postinstall] FATAL (32) migration 007_layer2_resolver.sql failed`. **Root cause:** 007 was relocated (P-004, D-20 reconciliation, 2026-05-04) from `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql` into the canonical operational migrations chain. The importer-side original ran against the catalog DB `mining_guardian_catalog`, where its prerequisites — the `uuid-ossp` extension, the `public.set_updated_at()` trigger function, and the `hardware.miner_models` / `pool.mining_pools` FK target tables — are all created by `intelligence-catalog/seed-data/intelligence_catalog_schema.sql`. The operational DB `mining_guardian` is a SEPARATE database (provisioned by `step_provision_catalog_db_and_seed` later in postinstall, in a different DB on the same Colima container) and has none of those prerequisites; 007's first `uuid_generate_v4()` call fails immediately. The byte-identical contract from P-004 (`tests/installer/test_d20_importer_payload_reconciliation.sh §8`) prevents patching 006 or 007 in place — the file bodies must continue to match the importer-side originals. **Fix:** new `migrations/006a_layer2_prereqs.sql` runs lexically between 006 and 007 (no rename of either) and creates exactly what 007 needs in the operational DB: (1) `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` + `pg_trgm`, (2) `CREATE OR REPLACE FUNCTION public.set_updated_at()` mirroring the catalog DB definition, (3) stub `hardware.miner_models(id UUID PRIMARY KEY)` and `pool.mining_pools(id UUID PRIMARY KEY)` so 007's FK declarations resolve. The stubs are intentionally minimal (id-only) because the operational DB never stores authoritative catalog rows; the FK columns in `mg.*` tables here are populated by application code with UUID pointers into the catalog DB and are nullable, so the FK constraint is satisfied trivially. The byte-identical 006 and 007 are NOT touched. **Idempotency:** `CREATE EXTENSION IF NOT EXISTS` / `CREATE OR REPLACE FUNCTION` / `CREATE SCHEMA IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` — entire body wrapped in BEGIN/COMMIT, safe to re-apply. Verified on PG 17 against a fresh DB and against a DB with a real catalog-shape `hardware.miner_models` (no clobber, seeded rows preserved). **No `build_pkg.sh`, payload, or notarization-relevant code changed** — pure new SQL file in `migrations/`, picked up automatically by `step_apply_migrations`'s `*.sql` glob. **Tests:** new `tests/installer/test_migration_007_prereqs.sh` (16 assertions, all green) — §1 file presence + balanced BEGIN/COMMIT, §2 every migration that calls `uuid_generate_v4()` is preceded (lexically) by a migration that creates the `uuid-ossp` extension, §3 every migration that does `EXECUTE FUNCTION set_updated_at()` is preceded by a migration that defines it, §4 every migration that declares `REFERENCES hardware.miner_models(id)` / `REFERENCES pool.mining_pools(id)` is preceded by a migration that creates that target table, §5 P-023 audit marker, §6 `step_apply_migrations` still globs `*.sql`, §7 RUNTIME (opt-in via `MG_RUN_PG_TESTS=1`) — fresh-DB end-to-end apply of every `migrations/*.sql` in lexical order with `-v ON_ERROR_STOP=1`, post-condition checks for `uuid-ossp`/`set_updated_at()`/`hardware.miner_models`/`pool.mining_pools`/`mg.*` (5 tables), and idempotency check (re-apply 006a + 007 succeeds). All adjacent installer suites still green: `test_d20_importer_payload_reconciliation` 32/32 (006/007 still byte-identical to importer-side originals), `test_postinstall_env_handoff` 38/38, `test_postinstall_payload_path` 12/12, `test_postinstall_catalog_seed` 24/24, `test_pkg_scripts_naming` 17/17. **Operator cleanup before next reinstall** (the `b66b864` attempt got far enough to bring up Postgres and apply migrations 001 → 006, but 007 failed; Postgres has the operational schema partially populated and `mining_guardian_catalog` was never created): `bin/uninstall.sh` is NOT installed yet (still runs after `step_provision_postgres`). Manually: `sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null \|\| true`, `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null \|\| true`, `sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null \|\| true`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. The new postinstall log should reach `INFO applying 006a_layer2_prereqs.sql`, then `INFO applying 007_layer2_resolver.sql` (now succeeds), then `INFO all migrations applied`, then `INFO catalog seed verified: hardware.miner_models has 320 rows`. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10n | P-022 — `step_drop_dotenv` must export `MG_DB_PASSWORD` (and friends) into the postinstall shell, not just into a `local` frame | ✅ | Merged 2026-05-05 as commit `b66b864` — Branch `mg/p022-postinstall-env-handoff` (2026-05-05, P-022) — P-020/P-021 (rows 10l/10m, merged as `e514c12`) cleared the VZ entitlement and limactl source-location bugs. `MiningGuardian-1.0.3-e514c122367a.pkg` was installed on the customer Mac mini; postinstall progressed through every prior gate (operator user resolved, Desktop conf read, `.env` written mode 0600, limactl present, Colima VZ started, postgres image loaded, persistent volume created). Then `provision_postgres` exited 31 with `FATAL MG_DB_PASSWORD missing from environment; postinstall did not source .env`. **Root cause:** `step_drop_dotenv` declared the three generated secrets (`MG_DB_PASSWORD`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`) as bash `local` variables, then called `export MG_DB_PASSWORD` as the last line of the function. In bash, `export` on a `local` only marks the EXPORT attribute on that local — once the function returns, the local goes out of scope and the calling shell never sees the value. `step_provision_postgres` then ran with `MG_DB_PASSWORD` unset and `provision_postgres` (in `lib/install_colima.sh`) bailed. The trap was masked through P-015 → P-021 because every prior failure exited 31 BEFORE `provision_postgres` got control. **Fix:** `step_drop_dotenv` no longer declares the secrets `local` (they land at script-shell scope). The trailing `export` is widened to cover every helper-required key — `MG_DB_PASSWORD`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`, plus the `GUARDIAN_PG_HOST/PORT/USER/PASSWORD/DBNAME/CATALOG_DBNAME` and `PGHOST/PORT/USER/DATABASE` family. New `INFO loaded generated env keys into postinstall shell: <key names>` log line — names only, NEVER values; the on-disk `.env` (mode 0600) is the only place any secret value appears. `step_provision_postgres` now does a fail-fast preflight check (empty `MG_DB_PASSWORD` / `GUARDIAN_PG_USER` / `PGUSER` / `GUARDIAN_PG_DBNAME` raises `fail 31` with `step_drop_dotenv did not export required env keys: …` BEFORE calling `install_colima_runtime`), so any future regression converts the 30-second crawl through colima/docker into an immediate FATAL with a self-pointing log line — no half-installed system to clean up. **No `build_pkg.sh`, payload, or notarization-relevant code changed** — pure shell-level bash-scoping fix. **Tests:** new `tests/installer/test_postinstall_env_handoff.sh` (38 assertions, all green) — §1 no `local MG_DB_PASSWORD/CATALOG_API_KEY/INTERNAL_API_SECRET`, §2 every required key on an `export` line (13 keys), §3 `loaded generated env keys` log marker present + names key, §4 `step_provision_postgres` preflight precedes `install_colima_runtime ||`, §5 NO log line interpolates `${MG_DB_PASSWORD}`/`${CATALOG_API_KEY}`/`${INTERNAL_API_SECRET}`/`${GUARDIAN_PG_PASSWORD}` (leak prevention), §6 RUNTIME — extracted `step_drop_dotenv` driver in stripped-env subshell proves `MG_DB_PASSWORD` (length ≥ 32), `CATALOG_API_KEY`, `INTERNAL_API_SECRET`, `GUARDIAN_PG_USER=mg`, `PGUSER=mg`, `GUARDIAN_PG_DBNAME=mining_guardian` all survive the function return (the ACTUAL bug fix), §7 RUNTIME — install log written by the function does NOT contain the generated secret values (extracted from the .env file then grepped against the log), §8 P-022 audit marker, §9 `bash -n`. All adjacent installer suites still green: `test_postinstall_user_resolver` 12/12, `test_postinstall_helper_user_resolver` 26/26, `test_postinstall_colima_path` 21/21, `test_postinstall_payload_path` 12/12, `test_postinstall_customer_info` 76/76, `test_postinstall_cocoa_alert_bounded` 9/9. **Operator cleanup before next reinstall** (the `e514c12` attempt got far enough to start Colima and load the postgres image; nothing inside Postgres was created, but the Colima VM IS running and must be cleaned): `bin/uninstall.sh` is NOT installed yet (step_install_uninstall_script runs after step_provision_postgres). Manually: `sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null \|\| true`, `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null \|\| true`, `sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null \|\| true`, then operator rebuilds + signs + notarizes a new .pkg from the merged main and reinstalls. The new postinstall log should reach `INFO loaded generated env keys into postinstall shell: MG_DB_PASSWORD …`, then `INFO step_provision_postgres preflight OK: required env keys present`, then `INFO postgres ready after Ns`, then `INFO catalog seed verified: hardware.miner_models has 320 rows`. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10m | P-021 — `build_pkg.sh` must re-pass `com.apple.security.virtualization` entitlement when re-signing Lima/Colima VZ binaries | ✅ | Merged 2026-05-05 as commit `e514c12` — Branch `mg/p020-p021-vz-entitlement-codesign` (2026-05-05, P-021) — P-019 (row 10k) cleared the PATH-propagation bug, putting the install on the path to actually start the VZ VM. Build `MiningGuardian-1.0.3-47efd658f16a.pkg` was installed on the customer Mac mini; postinstall progressed all the way through `[ollama] INFO limactl present at /usr/local/bin/limactl`, then `colima start` info lines, downloading + converting image, `Starting VZ...`, then `fatal: error starting vm: exit status 1`. `ha.stderr.log` captured the definitive failure: `Error Domain=VZErrorDomain Code=2 Description="Invalid virtual machine configuration. The process doesn't have the "com.apple.security.virtualization" entitlement."` **Root cause:** upstream lima-vm/lima's Makefile signs `_output/bin/limactl` and `_output/libexec/lima/lima-driver-vz` with `codesign -f -v --entitlements vz.entitlements -s -` so each binary carries `com.apple.security.virtualization`. Our `build_pkg.sh::step_4b_codesign_inner_binaries` then re-signs every vendored Mach-O with `codesign --force --sign "$APPLE_DEV_ID_APPLICATION" --options runtime --timestamp` (no `--entitlements`). codesign's `--force` REPLACES the entire signature including embedded entitlements, so every VZ-needing binary loses the virtualization entitlement. Apple notary does NOT catch this — the entitlement is legal to omit; failure surfaces only at install-time `colima start --vm-type vz`. **Fix:** new `installer/macos-pkg/scripts/lib/vz.entitlements` (mirrors upstream lima's plist — declares `com.apple.security.virtualization` plus `network.{server,client}` matching upstream). `step_4b` defines a `vz_binary_names` set (`limactl`, `lima-driver-vz`, `lima`); for any loose Mach-O whose basename matches the set, the codesign call now passes `--entitlements "$vz_entitlements"`. Non-VZ binaries (colima, docker, qemu-img) keep the no-entitlements path — over-broad entitlement application is itself a notarization risk. Build-time verify-after-sign greps `codesign -d --entitlements - <bin>` output for `com.apple.security.virtualization` on every VZ-needing binary and exits 44 if absent, so the build hard-fails before notarization burns a round-trip on a .pkg whose VZ binaries are missing the entitlement. **No `postinstall.sh` or payload-shape changes** — pure build-time signing logic; install-time behavior is unchanged once limactl carries the entitlement again. **Tests:** new `tests/installer/test_build_pkg_vz_entitlement.sh` (26 assertions, all green) — plist shape + parse, build_pkg.sh wiring (entitlements path, vz_binary_names list, --entitlements pass, basename matching, verify-after-sign, mandatory limactl-presence check), 3 runtime scenarios for the limactl source-location resolver (Lima 1.x layout, Lima 2.x layout, both-missing → non-zero exit with documented FATAL), audit markers, `bash -n`. All adjacent installer suites still green: `test_postinstall_colima_path` 21/21, `test_pkg_scripts_naming` 17/17, `test_postinstall_helper_user_resolver` 26/26, `test_postinstall_user_resolver` 12/12, `test_postinstall_payload_path` 12/12, `test_preinstall_arch_gate` 11/11, `test_postinstall_cocoa_alert_bounded` 9/9, `test_d20_importer_payload_reconciliation` 32/32, `test_postinstall_catalog_seed` 24/24, `test_postinstall_venv` 26/26, `test_postinstall_scheduled_jobs` 115/115, `test_uninstall_script` 50/50, `test_postinstall_customer_info` 76/76, `test_wheel_resign` 17/17. **Operator cleanup before next reinstall** (the 47efd65 attempt got far enough to install the runtime + try `colima start`; nothing inside the VM was created, so no Postgres state to clean): `bin/uninstall.sh` should now exist at `/Library/Application Support/MiningGuardian/bin/uninstall.sh` from the 47efd65 install — prefer `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --yes --purge-data --purge-logs`. If that path is missing, do it manually: `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, `sudo /usr/local/bin/colima delete --force 2>/dev/null \|\| true`, `sudo rm -f /usr/local/bin/{colima,limactl,lima,docker} /usr/local/bin/*.lima 2>/dev/null`, `sudo rm -rf /usr/local/libexec/lima /usr/local/share/lima 2>/dev/null`, `sudo rm -rf /Users/miningguardian/.colima /Users/miningguardian/.lima 2>/dev/null`. Then operator rebuilds + signs + notarizes a new .pkg from the merged main, and reinstalls. Detection (after install): `codesign -d --entitlements - /usr/local/bin/limactl 2>/dev/null \| grep com.apple.security.virtualization` must print one match. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10l | P-020 — `install_colima.sh` must locate `limactl` in either Lima 1.x (`${src}/limactl`) or Lima 2.x (`${src}/bin/limactl`) layouts | ✅ | Merged 2026-05-05 as commit `e514c12` — Branch `mg/p020-p021-vz-entitlement-codesign` (2026-05-05, P-020) — coupled with P-021 because both surfaced from the same install round and ship in the same PR. Earlier code agents were asked to fix the "missing limactl" symptom and stalled; the actual symptom on 47efd65 was VZ entitlement (P-021), not a missing limactl. But the underlying source-location fragility is real: `install_colima_runtime` resolved limactl from a single hard-coded path (`${src}/limactl`) for Lima 1.x layouts. Lima 2.x ships `limactl` under `${src}/bin/limactl` instead, so a vendor dir built from a Lima 2.x release would `install` exit non-zero (set -e) without a clear log line. The bug hasn't bitten yet because the operator's vendor dir happened to use Lima 1.x layout, but as upstream Colima/Lima updates roll forward into `~/MiningGuardian-vendor/`, the next vendor refresh would silently regress. **Fix:** `install_colima_runtime` now walks both `${src}/limactl` and `${src}/bin/limactl`, picks whichever exists, logs the source path on success, and exits with a clear `_die "vendored limactl not found at ${src}/limactl or ${src}/bin/limactl (P-020)"` when neither is present. Build-side belt-and-suspenders: `step_4b_codesign_inner_binaries` asserts `find -type f -name 'limactl'` returns at least one match anywhere under runtime/, so the build hard-fails (exit 44) before signing/notarization if the vendor layout has hidden limactl elsewhere entirely. **No payload or notarization-relevant code changed** — pure shell-level path resolution. **Tests:** covered by the same `tests/installer/test_build_pkg_vz_entitlement.sh` runtime block (3 scenarios). Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10k | P-019 — installer must propagate PATH (incl. `/usr/local/bin`) under `sudo -u` so colima/docker can find `limactl` | ✅ | Merged 2026-05-05 as commit `47efd65` — Branch `mg/p019-colima-limactl-path` (2026-05-05, P-019) — P-018 (row 10j) cleared the operator-user resolution bug, putting the next install attempt on the path to actually run `colima start` as the operator. Build `MiningGuardian-1.0.3-32ec2dcad973.pkg` (main `32ec2dc`) was installed clean on the customer Mac mini; postinstall progressed all the way through `INFO copied colima + lima (VZ-only, no QEMU) to /usr/local/bin` and `INFO colima will run as miningguardian (home=/Users/miningguardian)`, then `colima start` exited with `lima compatibility error: error checking Lima version: exec: "limactl": executable file not found in $PATH`. **Root cause:** macOS `sudo -u <op>` strips the inherited `PATH` and substitutes sudoers' `secure_path` (typically `/usr/bin:/bin:/usr/sbin:/sbin` — note the absence of `/usr/local/bin`). `colima` then uses Go's `os/exec.LookPath("limactl")` to resolve its lima sibling, and that lookup obeys the child PATH — so even though `install_colima_runtime` had just installed `limactl` to `/usr/local/bin` two lines earlier, colima could not see it. The same trap applies to every `docker` invocation under `sudo -u` (migration apply, catalog seed, postgres bootstrap), since `docker` is a shim that resolves `colima` for context discovery. **Fix:** add `_op_path` helpers in `install_colima.sh` and `postinstall.sh` that return a PATH starting with `/usr/local/bin`; every `sudo -u` site that invokes `colima` or `docker` now wraps with `/usr/bin/env PATH="$(_op_path)" HOME="${op_home}"` so the child process sees the binaries we just installed. New `_verify_limactl` in `install_colima.sh` asserts limactl exists at the install destination *before* invoking `colima start`, so a missing limactl produces a clear "limactl not found at /usr/local/bin/limactl" log line instead of the misleading colima `$PATH` error. Sites updated: `install_colima.sh::install_colima_runtime` (1 colima-start invocation), `install_colima.sh::load_postgres_image` (1 docker-load), `install_colima.sh::provision_postgres` (3 docker calls — rm/run/exec), and `postinstall.sh` (10 docker exec/cp invocations across `step_apply_migrations` and `step_provision_catalog_db_and_seed`). `install_ollama.sh::pull_llm_model` is unchanged — it invokes `/usr/local/bin/ollama` by absolute path and ollama does not shell out to find sibling helpers. **No `build_pkg.sh`, payload, or notarization-relevant code changed** — pure shell-level PATH hygiene. **Tests:** new `tests/installer/test_postinstall_colima_path.sh` (21 assertions, all green) — `_op_path`/`_verify_limactl` definition presence, PATH-order check (/usr/local/bin first), `sudo -u` site wrap audit (every colima/docker call wrapped with `/usr/bin/env PATH=…`), runtime: `_op_path` value contains /usr/local/bin, `_verify_limactl` returns 0 for present executable + non-zero with explicit message for missing, `env PATH=…` actually locates a stub `limactl` in a stripped-PATH environment (with negative control proving the bug recurs without the wrap), P-019 audit marker, `bash -n` parse. All adjacent installer suites still green: `test_postinstall_helper_user_resolver` 26/26, `test_postinstall_user_resolver` 12/12, `test_postinstall_payload_path` 12/12, `test_postinstall_cocoa_alert_bounded` 9/9, `test_pkg_scripts_naming` 17/17, `test_preinstall_arch_gate` 11/11, `test_postinstall_customer_info` 76/76, `test_postinstall_catalog_seed` 24/24, `test_postinstall_venv` 26/26, `test_postinstall_scheduled_jobs` 115/115, `test_uninstall_script` 50/50. **Operator cleanup before next reinstall** (the 32ec2dc attempt got far enough to lay down the install root and `.env`, then died inside install_colima.sh before colima ever started; no Postgres container was created, no LaunchDaemons were bootstrapped): `bin/uninstall.sh` was not installed in this round either, so do it manually — `sudo rm -rf "/Library/Application Support/MiningGuardian"`, `sudo rm -rf /var/log/mining-guardian`, and `sudo /usr/local/bin/colima delete --force 2>/dev/null \|\| true` (best-effort — colima never started so nothing to clean, but the command is safe to run unconditionally). Then operator rebuilds + signs + notarizes a new .pkg from the merged main, and reinstalls. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10j | P-018 — installer helper libs must use `MG_INSTALL_OPERATOR_USER`, not `${SUDO_USER:-${USER}}` | ✅ | Merged 2026-05-05 as commit `32ec2dc` — Branch `mg/p018-helper-user-resolution` (2026-05-05, P-018) — P-017 (row 10i) cleared the payload-path bug, putting the next install on the path to actually execute `install_colima_runtime` and `pull_llm_model`. Both helper libs still resolved the operator account through the legacy `${SUDO_USER:-${USER}}` pattern P-016 (row 10h) replaced in `postinstall.sh`. Under Installer.app, `USER=root` is exported and `SUDO_USER` is unset, so the legacy pattern picks `root` — `install_colima_runtime` would have set `home="/Users/root"` and run `sudo -u root colima start` (wrong owner — colima state would land in `/var/root/.colima` rather than the operator's home; `docker load` and the postgres `docker run` calls would then fail because the docker socket lives under the operator's home). `pull_llm_model` would have pulled the model into `/var/root/.ollama`, invisible to the launchd ollama service that runs as the operator. Tracked as B-12 in `docs/LATENT_BUGS.md`. **Fix:** each helper lib now defines an `_op_user` resolver that prefers `MG_INSTALL_OPERATOR_USER` (exported by `postinstall.sh::main()` before either helper is sourced) and falls back through three bounded probes (`SUDO_USER` → `stat -f '%Su' /dev/console` → `/Users/*/Desktop/MiningGuardian.conf` scan), refusing to silently return `root` when no real operator account resolves. `install_colima.sh::install_colima_runtime` also resolves `op_home` via `dscl . -read /Users/<u> NFSHomeDirectory` rather than hard-coding `/Users/<u>`, so a relocated home directory does not silently fail. Every `chown` / `sudo -u` / `home="…"` site in `install_colima.sh` (8 sites across `install_colima_runtime` / `load_postgres_image` / `provision_postgres`) and `install_ollama.sh` (1 site in `pull_llm_model`) now derives its user from `_op_user`. **No `postinstall.sh`, `build_pkg.sh`, payload, or notarization-relevant code changed** — pure helper-lib logic. **Tests:** new `tests/installer/test_postinstall_helper_user_resolver.sh` (26 assertions, all green) — pattern-eradication grep, four-probe presence, `!= "root"` guard counts, refusal message, runtime resolver behavior with stubbed `/usr/bin/stat` + fake `/Users` tree (3 scenarios: MG_INSTALL_OPERATOR_USER=miningguardian, Installer.app env falls through to Desktop scan, empty environment returns non-zero rather than `root`), P-018 audit marker. All adjacent installer suites still green (test_postinstall_user_resolver 12/12, test_postinstall_payload_path 12/12, test_postinstall_cocoa_alert_bounded 9/9, test_pkg_scripts_naming 17/17, test_preinstall_arch_gate 11/11, test_postinstall_customer_info 76/76, test_postinstall_catalog_seed 24/24, test_postinstall_venv 26/26, test_postinstall_scheduled_jobs 115/115, test_uninstall_script 50/50). **Operator cleanup before next reinstall** (after the P-017 build attempt at `9318062` which left install root + `.env` but no Colima/Postgres/services on the Mini): `bin/uninstall.sh` is NOT installed yet, so do it manually — `sudo rm -rf "/Library/Application Support/MiningGuardian"` and `sudo rm -rf /var/log/mining-guardian`, then operator rebuilds + signs + notarizes a new .pkg from the merged main, then reinstalls. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10i | P-017 — postinstall MG_PKG_PAYLOAD must resolve to install root, not scripts sandbox | ✅ | Merged 2026-05-05 as commit `bae1891` — Branch `mg/p017-payload-path-install-root` — first install of the P-016 build `MiningGuardian-1.0.3-9318062cad3e.pkg` on the customer Mac mini progressed past Bug A and Bug B from P-016 (operator user resolved to `miningguardian`, Desktop conf read, `.env` written) and exited 31 in `install_colima_runtime` with `FATAL vendored colima runtime not found at /tmp/PKInstallSandbox.sJTxI0/Scripts/com.miningguardian.installer.core.Hy5Eby/../payload/runtime/colima`. **Root cause:** with `pkgbuild --root ${PAYLOAD_DIR} --scripts ${SCRIPTS_DIR} --install-location "/Library/Application Support/MiningGuardian"`, Installer.app at install time extracts the *scripts* archive into a private sandbox under `/tmp/PKInstallSandbox.<rand>/Scripts/...` and the *payload* archive directly to the install location — those are TWO DIFFERENT directories. `postinstall.sh` set `MG_PKG_PAYLOAD="${SCRIPT_DIR}/../payload"`, which resolved to a path inside the scripts sandbox that does not exist (the scripts sandbox holds only the script archive contents). Every payload-relative read (runtime/colima, intelligence-catalog/seed-data, deploy/feedback_loop_daemon_launcher.sh, python-wheels/, requirements.txt, deploy/*.plist, BUILD_STAMP.json, migrations/) would have failed; install_colima.sh's check fired first because it runs first in step_provision_postgres. **Fix:** at script-load time, prefer `${MG_INSTALL_ROOT}` (where Installer.app lays the payload at install time, same as `pkgbuild --install-location`); fall back to `${SCRIPT_DIR}/../payload` only when `${MG_INSTALL_ROOT}/runtime` is absent (dev / smoke-test invocations of postinstall.sh outside a real .pkg). No build_pkg.sh changes — the .pkg layout itself is correct, only the install-time path resolution was wrong. **Tests:** new `tests/installer/test_postinstall_payload_path.sh` (12 assertions, all green). **Latent companion (now closed):** `install_colima.sh` / `install_ollama.sh` legacy `${SUDO_USER:-${USER}}` pattern — see row 10j (P-018). |
| 10h | P-016 — postinstall hang fix (`_cocoa_alert` osascript) + operator-user resolver | 🟡 | Branch `mg/p016-postinstall-desktop-user-resolution` (2026-05-05, P-016) — corrected diagnosis of the cf1691e install failure (row 13). Postinstall log stops after `INFO loaded helper libs` with no FATAL line. `/var/log/install.log` shows `PackageKit: Terminating PKInstallTask(pid:5521). Task has exceeded its 600 seconds of runtime.` and **no `unbound variable`** line. The 600 s timeout rules out a fast `set -u` crash — bash did not exit on variable expansion; the script was alive but blocked. **Two distinct bugs:** **Bug A (the actual hang)** — `step_collect_customer_info` resolved `desktop_user="root"` (Installer.app exports `USER=root`), looked at `/Users/root/Desktop/MiningGuardian.conf` which doesn't exist, called `_conf_fail` → `_cocoa_alert`, which ran `osascript display dialog` synchronously with no timeout. Postinstall runs as root with no Window Server connection; the dialog blocks forever, PackageKit's 600 s watchdog kills the script, no FATAL line is written. **Bug B (wrong target file)** — even after fixing Bug A, the legacy `${SUDO_USER:-${USER}}` would still pick `root` (Installer.app's `USER=root`), so the customer's actual conf at `/Users/miningguardian/Desktop/MiningGuardian.conf` would never be found and the install would correctly fail 41 instead of succeeding. **Fix A:** `_cocoa_alert` is now hard-bounded with `with giving up after 5` (AppleScript) + a pure-bash `kill -KILL` watchdog (10 s wall-clock cap, no `timeout(1)` dependency since macOS does not ship coreutils) + delivery via `launchctl asuser <uid> sudo -u <console_user>` so the dialog can render in the GUI session. **Fix B:** new `_resolve_install_user()` helper with three probes (`SUDO_USER` → `stat -f '%Su' /dev/console` → `/Users/*/Desktop/MiningGuardian.conf` scan), exported as `MG_INSTALL_OPERATOR_USER` at the top of `main()`. All 22 in-line `${SUDO_USER:-${USER}}` sites replaced. Added env-probe log line in `main()`. **Tests:** new `tests/installer/test_postinstall_cocoa_alert_bounded.sh` (9/9 green) — including a runtime test that stubs osascript to `sleep 600` and asserts `_cocoa_alert` returns within 15 wall-clock seconds, directly proving the cf1691e timeout cannot recur. Existing `tests/installer/test_postinstall_user_resolver.sh` (12/12 green) — runtime test now mirrors actual Installer.app env (`SUDO_USER` unset, `USER=root`) and asserts the resolver returns `miningguardian` via the Desktop scan instead of `root`. All 253 prior installer test assertions still green; shellcheck baseline unchanged at 3. **Diagnosis confirmation gate (operator-side):** `sudo grep -nE 'unbound\|exceeded\|MiningGuardian\|postinstall\|cf1691e' /var/log/install.log \| tail -120`. The cf1691e attempt shows the 600 s timeout line and **no** unbound-variable line, confirming Bug A. **No build_pkg.sh, payload, or notarization-relevant code changed** — pure postinstall logic. Status 🟡 until merge + new build; flips to ✅ on merge. |
| 10g | P-015 — preinstall arch gate Rosetta-safe (sysctl hw.optional.arm64) | ✅ | PR `mg/v103-d18-p015-arch-gate-rosetta-safe` (2026-05-04, P-015) — first install of the corrected v1.0.3 .pkg `MiningGuardian-1.0.3-2b48f98e6b77.pkg` (built from main 2b48f98 with the P-013/P-014 script-naming fixes) on the customer Mac mini hard-failed at `gate_apple_silicon`: `/var/log/mining-guardian/install-preinstall.log` showed `OK gate_root` + `OK gate_macos_version: 26.4.1 >= 13.0` + `FATAL (12) this build supports Apple Silicon (arm64) only; detected 'x86_64'` on a documented M-series box. **Root cause:** `gate_apple_silicon` called `/usr/bin/uname -m` and compared to `arm64`. `uname -m` reports the architecture of the CURRENT PROCESS, not the hardware. On Apple Silicon, if Installer.app spawns the preinstall under a Rosetta-translated `/bin/bash` (Terminal.app set to "Open using Rosetta", or `arch -x86_64 sudo installer ...`), `uname -m` returns `x86_64` even though the Mac is M-series. The kernel-authoritative hardware indicator is `sysctl hw.optional.arm64`, which is set by the kernel based on the SoC and does NOT change under Rosetta translation (`=1` on Apple Silicon, `=0`/missing on Intel). **Fix:** `gate_apple_silicon` rewritten to read `sysctl -n hw.optional.arm64` first (accept on `=1`, reject 12 on `=0`); logs `sysctl.proc_translated` for diagnostics with a Rosetta-context warning if `=1`; falls back to `uname -m` only when sysctl is unreadable, accepting only when uname agrees with `arm64` (defensive — never accept x86_64 on no-other-evidence). Intel-only support remains explicitly out of scope (CLAUDE.md / D-18 / Vision Anchor 2). Tests: new `tests/installer/test_preinstall_arch_gate.sh` (11 assertions, all green) — 6 static drift guards (bash -n, sysctl reads, hw_arm64 branch, fail 12 still present, P-015 audit marker) + 5 functional scenarios using a PATH-shadowed sysctl/uname mock harness (native arm64; arm64 under Rosetta with uname=x86_64 — the bug; Intel rejected; sysctl-missing+uname-x86_64 defensive reject; sysctl-missing+uname-arm64 defensive accept). All prior installer suites still green. **No build_pkg.sh, payload, or notarization-relevant code changed** — pure preinstall logic, so the pkg the operator rebuilds after merge will hash differently only because of the script-archive bytes. |
| 10b | P-010 — Wheelhouse hard-fail + runbook | ✅ | PR `mg/v103-p010-wheelhouse-fail-hard` (2026-05-04, P-010) — `build_pkg.sh` step 4e now exits 43 when `${HOME}/MiningGuardian-vendor/python-wheels/` is missing entirely (previously WARN-and-proceed, which produced a signed/notarized .pkg whose postinstall step_create_venv would exit 38 on the customer Mac, burning an Apple notarization round-trip). Mirrors the existing exit-43 behavior for an empty wheelhouse. New "Block Pre-A" in `docs/RUNBOOK_PKG_REBUILD.md` documents the one-time `pip download` invocation (Apple Silicon `cp312` ABI, `macosx_11_0_arm64`, `--only-binary=:all:`). Tests: 2 new assertions in `tests/installer/test_postinstall_venv.sh` (no WARN-and-proceed branch, `_die 43` for missing wheelhouse). |
| 10c | P-011 — Re-sign Mach-O inside vendored wheels | ✅ | PR `mg/v103-p011-wheel-resign` (2026-05-04, P-011) — Apple notary submission `750c089f-f0a1-4d40-bf15-e8c295828027` for the v1.0.3 first build (`MiningGuardian-1.0.3-295aec38f2ee.pkg`) returned `Invalid` because vendored Python wheels (aiohttp, bcrypt universal2, matplotlib, etc.) ship `.so` / `.dylib` binaries signed by their package maintainers, NOT with our Developer ID Application + secure timestamp + hardened runtime. New build step `step_4c_resign_inner_wheels` in `build_pkg.sh` invokes `installer/macos-pkg/scripts/lib/resign_wheel.py` to: (1) extract every `*.whl` in `<payload>/python-wheels/`, (2) `codesign --force --sign "$APPLE_DEV_ID_APPLICATION" --options runtime --timestamp` every inner Mach-O detected via `file -b`, (3) recompute sha256 + size and rewrite each wheel's `*.dist-info/RECORD` manifest, (4) re-zip deterministically and atomic-move over the original wheel, (5) post-rewrite verify that RECORD entries match actual zip bytes (catches programmer error before notary). Pure-Python wheels are skipped (no Mach-O → nothing to do, RECORD untouched, pip install still works offline). Exit code 49 reserved for wheel-signing failures (60 = arg/env, 61 = wheel I/O, 62 = codesign, 63 = RECORD/verify, in the helper's own scheme; build_pkg.sh translates all of those into `_die 49`). Build-time low-risk improvement: when notary returns non-Accepted, `step_6_notarize` now auto-fetches the detailed JSON via `xcrun notarytool log <id>` to `<pkg>.notarization-detail.json` (auto-fetch failure does not mask the original `_die 45`). Tests: new `tests/installer/test_wheel_resign.sh` (15 assertions, all green) covering Python syntax, main() ordering, exit-code 49 wiring, identity guard, synthetic wheel functional round-trip with mocked codesign (RECORD rewrite, verify, tamper detection), build_pkg.sh wiring, notary detail-log auto-fetch, and shellcheck baseline (≤ 7). All 7 prior installer tests still green (390 assertions across the suite). After merge: operator must re-build the .pkg per `docs/RUNBOOK_PKG_REBUILD.md` (Block A) — the current `MiningGuardian-1.0.3-295aec38f2ee.pkg` is rejected by Apple notary and is NOT a shippable artifact. |
| 10d | P-012 — Mac /usr/bin/python3 (3.9) compat in resign_wheel.py | ✅ | PR `mg/v103-p012-resign-wheel-py39-compat` (2026-05-04, P-012) — first `make pkg` after P-011 merged crashed in `step_4c_resign_inner_wheels` with `TypeError: write_text() got an unexpected keyword argument 'newline'` at `installer/macos-pkg/scripts/lib/resign_wheel.py:206`. Root cause: `pathlib.Path.write_text(newline=...)` was added in Python 3.10; `build_pkg.sh` runs the helper via `/usr/bin/python3`, which on current macOS (Sonoma/Sequoia) is the Apple-stub Python 3.9 — the kwarg raises `TypeError` before any signing or notarization happens. Fix: switched the single offending call to the file-handle form `record_path.open("w", encoding="utf-8", newline="") as fh: fh.write(...)`, which has been available since Python 3.0 and preserves the exact same byte semantics (we already preserve original `\r\n` vs `\n` trailers per-line when assembling `new_lines`, so writer-side `newline=""` keeps line endings byte-identical). No other 3.10+-only API is used in `resign_wheel.py` (the `from __future__ import annotations` covers the `set[str]` / `list[str]` PEP 585 generics under 3.9). Tests: `tests/installer/test_wheel_resign.sh` extended from 15 → 17 assertions: §10 AST-walks the source for any `Path.write_text(..., newline=...)` / `Path.read_text(..., newline=...)` (3.13+) reintroduction, §11 monkey-patches `Path.write_text` to raise the same `TypeError` 3.9 raises and asserts `_rewrite_record()` still completes successfully. Both regression guards verified to fail against the pre-fix file before passing against the fix. The package was NOT produced; no signing or notary submission was burned. |
| 10f | P-014 — step 4d rsync excludes `build_pkg.sh` from scripts staging | ✅ | PR `mg/v103-d18-p014-staging-exclude-build-pkg` (2026-05-04, P-014) — first `make pkg` after PR #130 (P-013) merged aborted at the new P-013 belt-and-suspenders guard with `step 4d FAIL: leftover top-level *.sh in scripts staging dir: ${SCRIPTS_DIR}/build_pkg.sh`. Root cause: `build_pkg.sh` lives in `installer/macos-pkg/scripts/` alongside `preinstall.sh` and `postinstall.sh`, and the step 4d rsync `${PKG_DIR}/scripts/` → `${SCRIPTS_DIR}/` pulled it into the package-script staging dir. After the .sh→extensionless rename, `build_pkg.sh` remained as a stray top-level `*.sh`, which (a) tripped the P-013 leftover-`*.sh` guard with exit 43 (working as designed — guard caught the regression), and (b) if the guard were ever removed, would re-trigger the original P-013 silent-ignore failure. Fix: add `--exclude 'build_pkg.sh'` to the step 4d rsync so only `preinstall.sh`, `postinstall.sh`, and `lib/` reach `${SCRIPTS_DIR}/`. P-013 guard is unchanged and still asserts zero top-level `*.sh` after the rename. Tests: `tests/installer/test_pkg_scripts_naming.sh` extended from 15 → 17 assertions (new §8 verifies the rsync line passes `--exclude 'build_pkg.sh'` and that the source has a `P-014` audit marker). All 17 assertions green; all 9 prior installer test suites still green. |
| 10e | P-013 — pkgbuild scripts must be named `preinstall`/`postinstall` (no `.sh`) | ✅ | PR `mg/v103-p013-pkg-scripts-naming` (2026-05-04, P-013) — Rob installed signed/notarized v1.0.3 build `a35728d` on the customer Mac mini on 2026-05-04 with `sudo installer -pkg ...`. Installer reported success and BUILD_STAMP.json showed v1.0.3 `a35728dcfc8c` at `/Library/Application Support/MiningGuardian`, but EVERY postinstall artifact was missing — no `/etc/mining-guardian/install-receipt.json`, no `/var/log/mining-guardian/install-postinstall.log`, no `.env`, no `venv`, no `logs`, no `postgres-data`, no `bin/`. `/var/log/install.log` showed PackageKit extracted the payload + wrote the receipt + Installed "Mining Guardian" (1.0.3), but ZERO preinstall/postinstall script execution lines. **Root cause:** Apple's `pkgbuild --scripts` honors EXACTLY two top-level filenames in the Scripts archive: `preinstall` and `postinstall`, with NO extension (per `man pkgbuild` and macOS PackageKit). `build_pkg.sh::step_4_assemble_payload` step 4d staged the scripts under their repo names `preinstall.sh` / `postinstall.sh`, so PackageKit silently ignored them — payload was laid down, BOM + receipt were written, "success" was reported, scripts never fired. Fix: step 4d now `mv -f` the staged scripts to extensionless names (`preinstall`, `postinstall`) inside `${BUILD_DIR}/stage/scripts/`, chmod's them 0755, then `find -maxdepth 1 -type f -name '*.sh'` aborts the build with exit 43 if anything `*.sh` is left at the top of the staging dir (belt-and-suspenders against a future refactor that copies instead of moves). Source files retain the `.sh` extension so editor highlighting, shellcheck, and `bash -n` keep working — the rename only happens at build-time staging. Tests: new `tests/installer/test_pkg_scripts_naming.sh` (15 assertions, all green) — covers source-tree `.sh` presence + executable, `bash -n`, the rename live-line, the chmod 0755 line, the `find` guard, the post-rename `[[ -x ]]` assertions, and a "no stray live reference to `${SCRIPTS_DIR}/(pre\|post)install.sh` outside the rename block" drift check. All 9 prior installer test suites still green. build_pkg.sh shellcheck baseline unchanged at 2. **Critical operator note:** the existing v1.0.3 `MiningGuardian-1.0.3-a35728dcfc8c.pkg` is NOT a shippable artifact — it has signed payload + valid receipt but no postinstall. The Mac mini currently has a payload-only install. Cleanup + rebuild + reinstall path is in the PR description and `docs/RUNBOOK_PKG_REBUILD.md` Block-Cleanup. |
| 10 | Version bump + RELEASE_NOTES_v1.0.3.md | ✅ | PR `mg/v103-version-bump-and-release-notes` (2026-05-04, P-009) — `pyproject.toml` 1.0.2 → 1.0.3 (single source of truth read by `installer/macos-pkg/scripts/build_pkg.sh::step_3_stamp_build`); new `docs/RELEASE_NOTES_v1.0.3.md` documents the P-001..P-009 PR train with cross-links and merge SHAs, the deferred items (Gap 3 row 4 + Cloudflare row 9) with the open-row pointers, the v1.0.3 verification gate (clean macOS 14 VM smoke test, HARD, not skippable), and the "what's not changing" envelope (no schema/Postgres/Ollama/cert changes); new `docs/PRE_BUILD_READINESS_v1.0.3_2026-05-04.md` is a static-analysis audit of the source tree against every D-18 audit gap, the `build_pkg.sh` 9-step pipeline, the test surface, and the plist-label / port-table drift checks — verdict: zero source-tree blockers. New `tests/installer/test_release_notes_version_drift.sh` (9 assertions, all green) guards the `pyproject.toml` ↔ `docs/RELEASE_NOTES_vX.Y.Z.md` ↔ `build_pkg.sh` SSOT coupling against future release-bump drift. D-18 implementation status appended in `docs/DECISIONS.md`. New EOD handoff at `docs/handoffs/HANDOFF_2026-05-04.md`. **No installer logic touched. No payload shape change.** Only the version stamp the build pipeline reads. The .pkg the operator builds tomorrow uses the EXACT source tree that P-001..P-008 produced. |
| 11 | Build, sign, notarize, staple v1.0.3 .pkg | 🟡 | Operator's laptop — most recent build `MiningGuardian-1.0.3-d0ba6c40a323.pkg` (from main `d0ba6c4`, P-026 merged) was installed on the customer Mac mini and progressed past every prior gate AND past the P-026 installer-owned-runtime resolver, then exited 38 in `step_create_venv` with `reports version '', expected '3.12'` — root cause is the unquoted `${py312}` command-substitutions splitting on the space in `/Library/Application Support/MiningGuardian/`, tracked as P-027 (row 10s). Earlier builds in the train (`00720ab`, `dd482af`, `b66b864`, `e514c12`, `47efd65`, `32ec2dc`, `9318062`, `cf1691e`, `a35728d`, `46761f1`, `2b48f98`) are NOT shippable — superseded. Status stays 🟡 — **next rebuild + Mini install (Round 10) gated on P-027 (row 10s) merging**. The vendor dir `${HOME}/MiningGuardian-vendor/python-runtime/` was populated for the P-026 round and does not need a Block Pre-B re-run. |
| 12 | Smoke-test on clean Mac VM (UTM/Tart) | 🔴 | D-18 verification gate (HARD) — has NOT been run; the operator went straight from build → Mini install on each round of the P-013→P-015 train. Still owed before a paying customer Mini cutover. |
| 13 | Install on Mini + screenshots | 🔴 | **Round 10 NOT YET ATTEMPTED — GATED on P-027 (row 10s) merging.** **Round 9b (2026-05-05, `d0ba6c4` — first build with the P-026 installer-owned-Python runtime merged):** package transferred OK, Gatekeeper accepted, preinstall green, postinstall progressed past every prior gate AND past the new installer-owned-Python resolver (log printed `INFO using installer-owned Python interpreter (packaged-flat): /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12`). Then `step_create_venv` exited 38 with `FATAL (38) resolved Python interpreter /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12 reports version '', expected '3.12'`, with the smoking-gun line `(/tmp/.../postinstall: line 1279: /Library/Application: No such file or directory)` immediately preceding. **Root cause:** unquoted `${py312}` command-substitution split on the space in `MG_PKG_PAYLOAD`. Diagnosis + fix tracked as P-027 (row 10s). **Round 9 (2026-05-05, `00720ab` — first build with the P-025 preflight P0 fixes merged):** package transferred OK, Gatekeeper accepted, preinstall green, postinstall progressed past every prior gate (env keys exported, Colima VZ started, postgres image loaded, `mining_guardian` ready, all 8 operational migrations applied, `mining_guardian_catalog` created, `deploy_schema.sql` applied — `Schema deployment complete \| sources_count 23 \| manufacturers_count 17`, **catalog seed verified at 320 rows**, all 9 launcher wrappers installed). Then `step_create_venv` exited 38 with `python3.12 not found on this Mac; install Homebrew + python@3.12 before running the .pkg`. **Root cause:** pre-P-026 the .pkg required Homebrew + `python@3.12` on the customer Mac as a hidden prerequisite. Operator decision (Rob, 2026-05-05): "yes include it in the installer and whatever else might pop up as the install keeps going". Diagnosis + fix tracked as P-026 (row 10r); locked as **D-27** in `docs/DECISIONS.md`. Round 8 (2026-05-05, `dd482af`) was fixed by P-024 / `6a48a82`. Round 7 (2026-05-05, `b66b864`) was fixed by P-023 / `dd482af`. Round 6 (2026-05-05, `e514c12`) was fixed by P-022 / `b66b864`. Round 5 (2026-05-05, `47efd65`) was fixed by P-020/P-021 / `e514c12`. Round 4 (2026-05-05, `32ec2dc`) was fixed by P-019 / `47efd65`. Round 3 (2026-05-05, `9318062`) was fixed by P-017 / `bae1891`. Round 2 (2026-05-04 night, `cf1691e`) — fixed by P-016 + P-018. Round 1 (`2b48f98`, blocked at `gate_apple_silicon` under Rosetta) was fixed by P-015 / PR #132 and is no longer the blocker. |
| 14 | VPS decommission + ROBS-PC container shutdown | 🔴 | Only AFTER Mini verified green per D-16 + D-18 |

**Operator constraints (from D-18 + HANDOFF_2026-05-04_NEW_CHAT.md):** No Mini install before v1.0.3 verified. No VPS decommission before Mini verified. No `setup.sh` on Mini before v1.0.3 (per INSTALL_PATHS_2026-05-03.md).


---

# SECTION 2 — Block-Ship Security Items (CRITICAL — must close before customer goes live)

These are the **gates** between today and a real customer install. Not all need to land before the Mac Mini personal cutover, but ALL need to land before this code ever runs on a paying customer's hardware.

> **2026-04-29 reality-check (this PR):** The bulk of §2 was already shipped earlier in code but the TODO had not been updated. As of this commit, S-1, S-2, S-3, S-4, S-6, and S-12 are all ✅ DONE. The remaining open items in the security buckets are S-5, S-7, S-8, S-9, S-10, S-11, S-13, S-14 (§3). Every "DONE" claim in this section now includes an inline `grep` you can run to verify the assertion at HEAD.

## 2.1. S-2 — Revoke leaked GitHub PAT ✅ DONE

- **Action taken:** Token revoked at GitHub on 2026-04-24; the cleartext literal in `docs/SECURITY.md:80` was scrubbed 2026-04-27 and replaced with `[REDACTED — token revoked 2026-04-24]`.
- **Verification:**
  ```bash
  grep -rn "ghp_\|github_pat_" --include="*.md" --include="*.py" --include="*.sh" .
  # → zero matches
  ```

## 2.2. S-1 / CRIT-1 — Purge `MiningGuardian2026!` from 29 source locations ✅ DONE

**Reality check 2026-04-29 (during top-to-bottom execution):** This was already done in code, the TODO was stale. All four critical code sites read `MG_DB_PASSWORD` from the environment with crash-on-missing semantics. The HTML form `value=` attribute is empty. The remaining 9 hits in the repo are all doc-only historical context (DECISIONS.md, this file, ROADMAP, SESSION_HANDOFF_2026-04-24.md, manifests describing the original finding).

- **Code sites verified env-based:**
  - `mg_import_tool/mg_import.py:57` — `os.environ.get("MG_DB_PASSWORD")` + crash-on-missing message
  - `scripts/migrate_to_postgres.py:30` — env-based
  - `intelligence-catalog/catalog-api/catalog_api.py:49` — env-based
  - `intelligence-catalog/docker-compose.yml` — env-based via `${MG_DB_PASSWORD}`
- **Decision locked (still authoritative):** New password is `tX-fhG#iJdm{V?>uuZ35G-Y)O5<UeN=5` (192 bits entropy). Goes into env files only. HTML form value is `""`.
- **Verification:**
  ```bash
  # zero hits in code (only doc-only historical references):
  grep -rn "MiningGuardian2026!" --include="*.py" --include="*.yml" \
    --include="*.yaml" --include="*.sh" --include="*.sql"
  # → no matches

  # env-based reads in place:
  grep -n "MG_DB_PASSWORD" mg_import_tool/mg_import.py | head
  ```

## 2.3. S-3 / CRIT-3 — `mg_import` Flask app: no auth + binds to 0.0.0.0 ✅ DONE

**Reality check 2026-04-29:** Already shipped in `mg_import_tool/mg_import.py`. Default bind is `127.0.0.1`, session token + `@require_login` decorator are applied to every privileged route, and 8-hour session TTL is enforced via `MG_IMPORT_SESSION_TTL_SECONDS=28800` (locked).

- **Verified in code:**
  - `mg_import.py:6553-6580` — CRIT-3 default-loopback comment, bind reads `MG_IMPORT_BIND` (default `127.0.0.1`), with explicit `0.0.0.0` warning when overridden
  - `mg_import.py:145-154` — TTL parsed from `MG_IMPORT_SESSION_TTL_SECONDS` (default 28800), validated ≥60s
  - `mg_import.py:189` — `require_login` decorator definition
  - `mg_import.py:254` — `hmac.compare_digest` for session-token comparison (defeats timing oracles)
  - `mg_import_tool/tests/test_crit3_auth.py` — coverage exists
- **Verification:**
  ```bash
  grep -n "require_login\|MG_IMPORT_SESSION_TTL\|MG_IMPORT_BIND" mg_import_tool/mg_import.py | head -20
  grep -c "@require_login" mg_import_tool/mg_import.py
  # → many; every privileged route is gated
  ```

## 2.4. S-4 — Postgres credentials passed in HTTP GET query strings ✅ DONE

**Fixed 2026-04-29 in PR #62 (`fix/s4-drop-password-querystring-2026-04-29`).** All four sites in `mg_import_tool/mg_import.py` (`_get_conn_params_from_args`, `unresolved_sample`, `browse_tables`, `browse_rows`) had their `request.args.get('password')` fallback removed. Password now comes only from `MG_DB_PASSWORD` via `_db_password()` (which already crashes on missing env, courtesy CRIT-1).

- **The other four querystring overrides** (`host`, `port`, `database`, `user`) are intentionally **not** changed in PR #62 — narrower blast radius, `@require_login` already gates these routes. Tracked separately under Bucket 2 hardening.
- **Verification:**
  ```bash
  grep -n "request.args.get('password')" mg_import_tool/mg_import.py
  # → zero matches
  ```

## 2.5. S-6 / CRIT-6 — Catalog API default key is publicly known string ✅ DONE

**Reality check 2026-04-29:** Already shipped. The catalog-api now refuses to start when the API key is missing, empty, or set to the literal `CHANGE_ME_TO_A_REAL_SECRET`, and uses `hmac.compare_digest` for token comparison (also closes S-12).

- **Verified in code:**
  - `intelligence-catalog/catalog-api/catalog_api.py:56-72` — startup rejects None / `""` / `CHANGE_ME_TO_A_REAL_SECRET`, length ≥ 32 enforced
  - `intelligence-catalog/catalog-api/catalog_api.py:148-158` — auth uses `hmac.compare_digest(submitted, API_KEY)` (constant-time)
  - `intelligence-catalog/catalog-api/test_crit6_hardening.py` — coverage exists, including a source-level assert that `hmac.compare_digest` appears
- **Still TODO inside Bucket 6 (installer rebuild):** `setup.sh` should generate the token via `openssl rand -hex 32` and write it to `.env`. Tracked there.
- **Verification:**
  ```bash
  grep -n "CHANGE_ME_TO_A_REAL_SECRET\|hmac.compare_digest" \
    intelligence-catalog/catalog-api/catalog_api.py
  ```

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

## 3.7. S-12 — Token comparison uses `!=` (timing attack) ✅ DONE
Closed alongside S-6 (see §2.5). `intelligence-catalog/catalog-api/catalog_api.py:148-158` uses `hmac.compare_digest(submitted, API_KEY)`. Verified 2026-04-29.

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

## 4.1. C4 — Run seed SQL against catalog Postgres 🔴 OPEN
- **Symptom:** `seed-data/seed_miner_models.sql` was never executed. 320-row baseline seed missing (313 + 7 Bitaxe added in PR #102, 2026-04-30).
- **Impact:** 208 catalog tables, only 5 have data. AI sees nothing.
- **Fix:** One `psql -f` invocation. Truly 30 seconds.
- **Effort:** 30 seconds. Unblocks C1.

## 4.2. C1 — Catalog split-brain: enrichment writes JSON, API reads Postgres 🔴 OPEN
- **Symptom:** Every AI lookup returns empty. 21 SQL queries, 0 rows.
- **Decision needed:** Path A (dual-write Postgres + JSON, recommended) vs B (rewrite API to read JSON) vs C (sync job)
- **Effort:** 4-6 hours
- **Blocks:** All AI quality. Until this is fixed, every Qwen analysis is uninformed.

## 4.3. C3 — 5 background watchers write JSON, never to catalog DB 🔴 OPEN
- Aggregator (4cc981c0), Manufacturer (920d0231), Firmware (aa676933), Community (c8c4678d), Deep Enrichment (ebb3af70)
- All save to `cron_tracking/<watcher>/latest_findings.json` — these JSON files don't move to the Mac Mini
- **Fix:** Rewrite each watcher to UPSERT into catalog Postgres
- **Effort:** 3-4 hours
- **Tied to C1 fix path.**

## 4.4. C5 — Operational→Catalog feedback loop missing 🔴 OPEN
- Layer 5 of the 6-layer plan.
- No code mines `action_audit_log` / `llm_analysis` / `miner_restarts` to upsert `ops.failure_patterns`, `market.war_stories`, `hardware.model_known_issues`
- **Effort:** 2-3 hours
- **Can slip post-Mac-Mini.**

## 4.5. C2 — Installer does not install Postgres / Docker / catalog API 🔴 OPEN
**This is the installer rebuild itself. See Section 7.**

---

# SECTION 5 — OpenClaw Removal (HIGH-10 from audit, N4 from findings) — ✅ DONE 2026-04-29 (Bucket 4 / PR #69)

## 5.1. Status: ✅ COMPLETE

OpenClaw was a silent no-op already (every `send_scan()` returned immediately because `webhook_url=None`). Removal has zero behavioral impact and was needed before Mac Mini installer rebuild so dead code is not shipped.

## 5.2. Reality-check vs. original audit checklist

When Bucket 4 was opened, a fresh audit revealed most of the original 12-item OpenClaw audit checklist had **already been done in earlier weeks** but the unified TODO never reflected it (same drift pattern PR #63 captured for S-1/S-3/S-6/S-12). The actual remaining work was much smaller than the checklist suggested.

| # | Original audit item | Actual state when Bucket 4 opened | Action taken in PR #69 |
|---|---|---|---|
| 1 | `docker compose down` on VPS openclaw-5b5o | VPS-side action — out of repo scope | (operator runs on VPS; no repo change needed) |
| 2 | `docker volume rm` openclaw volumes | VPS-side, optional | (operator runs on VPS; no repo change needed) |
| 3 | `core/mining_guardian.py` import + init + config template | Already clean — no `OpenClaw` strings remained | No change needed |
| 4 | `core/overnight_automation.py` `notify_openclaw()` + call site | Already clean | No change needed |
| 5 | Delete `notifiers/openclaw_notifier.py` | File no longer existed | No change needed |
| 6 | `core/models.py` config dataclass field | Already clean | No change needed |
| 7 | Delete `tests/test_openclaw_notifier.py` | File no longer existed | No change needed |
| 8 | `tests/conftest.py` references | Already clean | No change needed |
| 9 | `api/slack_approval_listener.py` docstring | Already clean | No change needed |
| 10 | Run tests | n/a — no code changes to behaviour | Confirmed no functional code touched |
| 11 | Commit | — | PR #69 |
| 12 | Delete `deploy/openclaw-skills/` directory | 7 files still present, zero importers | **Deleted** in PR #69 |
| extra | `intelligence/docker-compose.yml` comment naming OpenClaw | Stale comment | Replaced with neutral wording + Bucket-4 breadcrumb |
| extra | `mining_guardian_policy.json` line 351 description | Stale description | Replaced: "Raise alert in the operations dashboard or notifier channel for human review" |
| extra | `.env.example` 5-line OpenClaw stub | Stale stub block | Replaced with Bucket-4 breadcrumb explaining old `OPENCLAW_*` env vars are obsolete |
| extra | `scripts/setup.sh` line 101 `"openclaw_webhook_url": null,` in generated config-template heredoc | Stale config-template line | **Removed** in PR #69 |

## 5.3. Verification (re-run any time)

```bash
# Should return only the four intentional Bucket-4 historical breadcrumbs in
# .env.example and intelligence/docker-compose.yml — nothing in code.
grep -ri "openclaw" . \
  --exclude-dir=archive --exclude-dir=mg_pre_prod --exclude-dir=mg_rename_dryrun \
  --exclude-dir=docs --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv \
  --exclude="*.md" --exclude="*.pyc" --exclude=".coverage"
```

## 5.4. Optional follow-up (NOT in this PR)

- Switch `slack_approval_listener.py` and `slack_command_handler.py` from REST polling → Bolt/Socket Mode. Tracked in Bucket 2 / Section 6.
- **Effort:** 4-6 hours separately. Already partially completed in earlier Bucket 2 work; remainder lives in installer rebuild (Bucket 6).

## 5.5. Sweep update 2026-04-29 PM — Section 5 closed

All Section 5 work has landed. Status flips:

| 5.2 step | Old status | New status | Reference |
|---|---|---|---|
| 1. `docker compose down` on `/docker/openclaw-5b5o` | 🔴 OPEN | ✅ DONE | Operational DB host shutdown — historical, not relevant on Mac Mini |
| 2. `docker volume rm` on openclaw volumes | 🔴 OPEN | ✅ DONE | Same as #1 |
| 3. Edit `core/mining_guardian.py` (drop `OpenClawNotifier` import + init + config key) | 🔴 OPEN | ✅ DONE | Removed during Section 5 surgical PR |
| 4. Edit `core/overnight_automation.py` (drop `notify_openclaw()` + call site) | 🔴 OPEN | ✅ DONE | Same |
| 5. Delete `notifiers/openclaw_notifier.py` | 🔴 OPEN | ✅ DONE | Same |
| 6. Edit `core/models.py` (drop `openclaw_webhook_url` field) | 🔴 OPEN | ✅ DONE | Same |
| 7. Delete `tests/test_openclaw_notifier.py` | 🔴 OPEN | ✅ DONE | Confirmed gone in 2026-04-29 doc-sweep test inventory (77 active tests, no openclaw test row) |
| 8. Update `tests/conftest.py` if it references OpenClaw | 🔴 OPEN | ✅ DONE | Verified clean |
| 9. Edit `api/slack_approval_listener.py` docstring (drop the "Socket Mode is owned by OpenClaw" line) | 🔴 OPEN | ✅ DONE | Verified clean |
| 10. Run tests | 🔴 OPEN | ✅ DONE | 77/77 active tests pass |
| 11. Commit `refactor: remove dead OpenClaw integration` | 🔴 OPEN | ✅ DONE | Merged to main pre-sweep |
| 12. Delete `deploy/openclaw-skills/` directory | 🔴 OPEN | ✅ DONE | Removed in repo-doc-sweep Commit 2 (2026-04-29) |

Doc-side cleanup (this sweep) also closes the **6.3 / 6.4** items that depended on Section 5:

| 6.x item | Old status | New status |
|---|---|---|
| 6.3 "Slack listener docstring still says 'Socket Mode is owned by OpenClaw'" | 🔴 OPEN | ✅ DONE (docstring removed in Section 5 PR) |
| 6.3 / 10 row "Bolt/Socket Mode migration (post-OpenClaw cleanup)" | 🔴 OPEN | 🟢 DEFERRED (still open as a **post-install** item; explicitly NOT on critical path — see 5.3) |
| 6.4 row 6c "Remove false OpenClaw docstring after Section 5" | 🔴 OPEN | ✅ DONE |

**OpenClaw is fully removed from the active tree.** Section 5 above is preserved verbatim as the historical record of how the removal was scoped and executed. Do not edit the original 5.1–5.4 narrative — append future deltas here in 5.5+.

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

## 7.1. Current state of `scripts/setup.sh` — ✅ REWRITTEN 2026-04-29 (Bucket 6b)

**Old state (177 lines, BiXBiT-branded shell, severely out of date)** rewritten as the 883-line, 15-phase customer macOS installer v2 in Bucket 6b. Reality-check of the original gap list:

- ✅ Postgres install + DB creation (Phase 4)
- ✅ Ollama install + 14b model pull (Phase 8)
- ✅ Catalog DB / catalog API (Phase 4 + Phase 5 seed)
- ✅ 8 of 8 services (plists from PR #74 / Bucket 6a, rendered + bootstrapped in Phase 9)
- ✅ Cron jobs (all 9 + 1 hourly benchmark) (Phase 10)
- 📘 Grafana — Bucket 6b writes a placeholder provisioning yaml; Bucket 6d ships the real datasources + dashboards
- ✅ Tailscale (optional, behind `--tailscale` flag) (Phase 12)
- ❌ S-7 hardening (dedicated user) — deferred; setup.sh has a TODO block citing §3.2
- ✅ S-14 fix (`read -s` at 5 password-prompt sites) (Phase 2)
- ✅ S-6 fix (generate `CATALOG_API_KEY` via `openssl rand -hex 32`, write to `.env` mode 0600) (Phase 7)
- ✅ References `core/mining_guardian.py` (the moved location) throughout
- ✅ References the 8 real plists from Bucket 6a; old `com.bixbit.mining-guardian.plist` reference removed
- ✅ Pip install honors `requirements.txt` if present, fallback pinned set otherwise (Phase 6)

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
| 7b | Write 8 plist templates in `installer/macos-pkg/resources/launchd/` | ✅ DONE 2026-04-29 (PR — Bucket 6a) |
| 7c | Rewrite `setup.sh` (Track I-2) | ✅ DONE 2026-04-29 (PR — Bucket 6b, 883 lines, 15 phases, S-13/S-14 folded in, 6d-grafana + 6c-restore stubs delegate cleanly) |
| 7d | ✅ DONE 2026-04-29 (PR — Bucket 6c) — `scripts/restore_from_snapshot.sh` (572 lines, 8 phases, --tarball/--skip-postgres-restore/--skip-grafana-restore/--dry-run, paste-along VPS tarball-build hints at bottom). Verify: `wc -l scripts/restore_from_snapshot.sh` and `git ls-tree HEAD scripts/restore_from_snapshot.sh` (mode 100755). | ✅ |
| 7e | 📘 Runbook landed 2026-04-29 (PR — Bucket 6e) — `docs/RUNBOOK_BUCKET_6E_SANDBOX_TEST.md` (397 lines: pre-flight, 15 phase-by-phase test procedure, restore-pass procedure, failure-mode catalog, exit criteria). Robert exec on fresh user account / VM — sandbox exec pending. Verify: `wc -l docs/RUNBOOK_BUCKET_6E_SANDBOX_TEST.md`. | 📘 |
| 7f | ✅ DONE 2026-04-29 (PR — Bucket 6f) — `DEPLOYMENT_CHECKLIST.md` rewritten for Mac-Mini era (410 lines, 7 sections: prerequisites, install .pkg, post-install state checks, restore-from-snapshot path, operator sign-off, common failure modes, rollback plan + Appendix A preserves the April 15 VPS-era checklist verbatim). Verify: `wc -l DEPLOYMENT_CHECKLIST.md` (→ 410) and `grep -c 'launchd\|launchctl\|brew services' DEPLOYMENT_CHECKLIST.md` (→ ≥7 macOS-era references). Will be filled in with observed-reality values from sandbox-test exec (PR Bucket 6e). | ✅ |
| 7g | ✅ DONE 2026-04-29 (PR — Bucket 6d) — `installer/macos-pkg/resources/grafana/` (full bundle: 2 datasources YAML, dashboard provider YAML, 3 dashboards JSON, README) + `scripts/install_grafana_provisioning.sh` helper. Verify: `find installer/macos-pkg/resources/grafana -type f \| sort` and `python3 -c "import json; [json.load(open(f)) for f in __import__('glob').glob('installer/macos-pkg/resources/grafana/dashboards/*.json')]"`. | ✅ |
| 7h | ✅ DONE 2026-04-29 (PR — Bucket 6 final close-out) — `installer/macos-pkg/scripts/postinstall.sh` refreshed for the 9-service install matrix. Grew `PLIST_LABELS` from 4 → 9 (added slack-listener, slack-commands, overnight-automation, alerts, intelligence-report). Replaced `step_generate_launcher_wrappers` (4 inline cat-heredocs) with `step_install_launcher_wrappers` that copies the 8 canonical wrappers from `installer/macos-pkg/resources/launchd/launchers/` (PR #74) into `${MG_INSTALL_ROOT}/bin/`, then keeps the lone `feedback_loop_daemon_launcher.sh` heredoc for parity with PR #41 payload. Replaced the triple-explicit `install -m 0644 …` plist copies with a loop over `PLIST_LABELS` (8 from `resources/launchd/`, 9th from `payload/deploy/`). Added exit code 37 ("launcher wrapper or plist source missing in payload"). Receipt JSON gains `service_count` field. Verify on Mac sandbox: `sudo /var/log/mining-guardian/install-postinstall.log` shows 9 "INFO bootstrapped …" lines + 9 "INFO installed launcher: …" lines + `launchctl print system/com.miningguardian.scanner` (and the other 8 labels) returns mode=Running. | ✅ |

**Total build day: ~10-11 hours, may bleed into Tuesday morning.**

---

# SECTION 8 — Orphan Code / Dead Stubs (audit findings H1, H3, N1, N2)

## 8.1. Confirmed dead

| Item | Source | Action |
|---|---|---|
| `chip_readings` table — 0 reads, 0 writes | H1 | ✅ DONE 2026-04-29 (PR — Bucket 7.2) — dropped via `migrations/004_drop_dead_stubs.sql` (`DROP INDEX IF EXISTS idx_chip_miner; DROP TABLE IF EXISTS chip_readings;`). CREATE block removed from `migrations/001_initial_schema.sql` (replaced with comment pointer). VPS Postgres confirmed 0 rows pre-drop on 2026-04-29; no FK dependents, no views, no live writers in non-archive code. SQLite-era references in `core/database.py` + `core/database_router.py` intentionally left for the SQLite-retirement bucket. Authority + verify-after-merge: `docs/RUNBOOK_BUCKET_7.2_DROP_DEAD_STUBS.md`. |
| `log_collection_failures` table — 0 reads, 0 writes | H3 | ✅ DONE 2026-04-29 (PR — Bucket 7.2) — dropped via the same migration `004_drop_dead_stubs.sql` (`DROP INDEX IF EXISTS idx_log_failures_miner, idx_log_failures_date; DROP TABLE IF EXISTS log_collection_failures;`). CREATE block removed from `migrations/001_initial_schema.sql`. VPS Postgres confirmed 0 rows pre-drop; failure events are surfaced through `discovery_log` + Slack notifier path instead. |
| `s19jpro_overheat_tracking` — model-specific hack | N2 | ✅ Phase 1 handler archived in PR #84 (Bucket 7.3, 2026-04-29) — `core/s19jpro_overheat_handler.py` was zero-caller dead code, moved to `archive/sqlite_phase1/`. Postgres table kept (intentional per `docs/EMPTY_STUB_TABLES.md`). Promote-to-generic OR fold-into-`ops.failure_patterns` deferred to whoever next implements Operator Rule #6 in the live code path — that's a feature-design decision, not cleanup. |
| `guardian.db` (0 bytes) | observed | ✅ DONE 2026-04-29 — empty stub deleted in earlier cleanup; verified absent in the 2026-04-29 doc-sweep tree audit |
| `databases/*.db` — empty stubs | observed | 🔴 Delete (or move to `archive/sqlite_stubs/`) |
| `migrations/migrate_sqlite_to_postgres.py` + `scripts/migrate_split_databases.py` + `scripts/migrate_to_postgres.py` | DECISIONS.md #6 | ✅ DONE 2026-04-29 (PR #83 — Bucket 7.6). All three scripts now exit 2 with stderr message unless `MG_ALLOW_MIGRATION=1`. Defer hard-deletion to post-Mac-Mini. |
| `intelligence/` directory (12 files, ~250 KB) — unpatched duplicates of `intelligence-catalog/seed-data/` schemas + Docker-era tuning | DEPRECATED.md (2026-04-27) | ✅ DONE 2026-04-29 (PR — Bucket 7.1) — entire `intelligence/` directory deleted: 10 blobs (3 schema duplicates with the 7 latent bugs PR #12 already fixed in canonical copies, the Docker compose, the postgres-tuning.conf for ROBS-PC, the deprecated README + DEPRECATED.md tombstone, the 244-page paper PDF duplicate, the schema_inventory.json, the .env.example, and 2 docs/ markdowns). Pre-flight verified zero code refs (grep across `*.py *.sh *.yml *.yaml *.toml *.json` returned 0). Authority + full inventory: `docs/RUNBOOK_BUCKET_7.1_INTELLIGENCE_DIR_REMOVAL.md`. Closes 8.2 row N6 ("4 versions of catalog schema in repo") in the same commit. |

## 8.2. Underused (audit-flagged but live)

| Item | Source | Action |
|---|---|---|
| `llm_analysis` (6r/3w, 1008 rows) | H4 | 🔴 Add precision/recall dashboard + prompt drift detection. Defer post-Mac-Mini. |
| `miner_baselines` (4r/3w, operational DB populated, catalog 0) | H5 | 🔴 Wire to cross-miner anomaly detection. Layer 3 of the 6-layer plan. (Note 2026-04-29: "VPS populated" wording dropped — the operational DB now lives on the Mac Mini per D-14; baseline rows are still those previously synced from the historical operational DB.) |
| `pending_operator_reviews.json` | H6 | 🔴 Promote from JSON to DB-backed table. **Defer.** |
| `discovery_log` not piped to enrichment | H7 | 🔴 Build promotion cron from `acknowledged=0` → deep enrichment queue. |
| `knowledge.freshness_log` empty | H8 | 🔴 Wire freshness writes from enrichment watchers. |
| `alert_listener_seen` / `cooldown` (1r/1w) | N1 | 🟢 Probably OK — leave alone. |
| 123 empty `knowledge.research_*` tables | N5 | 🟢 Auto-create on import. Fine to leave. |
| 4 versions of catalog schema in repo | N6 | ✅ DONE 2026-04-29 (PR — Bucket 7.1) — the 3 unpatched duplicates under `intelligence/database/` were the divergent versions; deleted with the full `intelligence/` directory in this PR. Canonical schema is now uniquely `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` (+ v2 + v3 additions). |
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
| 6 | `migrate_to_postgres.py` raises on import unless `MG_ALLOW_MIGRATION=1` | ✅ Done in PR #83 (Bucket 7.6, 2026-04-29). Guard now also covers `migrate_sqlite_to_postgres.py` and `migrate_split_databases.py`. |

---

# SECTION 10 — User Backlog (your direct call-outs from this weekend)

| # | Item | Source | Status |
|---|---|---|---|
| 10.1 | Web GUI on `approval_api.py:8686` for approve/deny with explanation field | Sunday user msg | ✅ **DONE 2026-04-29 PM** — see `docs/WEB_GUI_OPERATOR_CONSOLE.md`, `api/static/approval_ui.html`, new `/ui` `/gui/approve` `/gui/deny` endpoints |
| 10.2 | Mode selector: Full Auto / Semi Auto / Manual on the same web GUI | Sunday user msg | ✅ **DONE 2026-04-29 PM** — `system_settings` table (migration 004) + `/mode` GET/POST + `run_overnight_cycle` mode ceiling. 10/10 tests pass. |
| 10.3 | Grafana provisioning section in installer | Sunday user msg | 🟢 In Section 7.2 phase 11 |
| 10.4 | Setup Manual (beginner-friendly, with images) | Sunday user msg | 🔴 Post-Mac-Mini |
| 10.5 | Program Instructions doc (beginner-friendly) | Sunday user msg | 🔴 Post-Mac-Mini |
| 10.6 | 8-10 page Product Brochure (with images) | Sunday user msg | 🔴 Post-Mac-Mini |
| 10.7 | Operator schedule control — retime overnight window + interval daemons from Web GUI | 2026-04-29 user msg | ✅ **DONE 2026-04-29 PM** — `system_schedules` table (migration 005) + `/schedules` GET/POST + Schedules tab in `approval_ui.html` + hot-reload in 4 daemons. 23/23 tests pass. See `docs/OPERATOR_SCHEDULES.md`. |

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
7. **C4 seed catalog** (30 sec) + verify 320 rows present (313 baseline + 7 Bitaxe in PR #102)
8. Start **installer rewrite** (Section 7) — ~4 hr (will spill to Tuesday)

## 📅 Tuesday 2026-04-28 — Installer + Sandbox
9. **Finish installer rewrite** — ~3 hr
10. **Sandbox test** on fresh macOS user account or VM — 1 hr
11. **Plist templates** for 8 services — 1 hr
12. **`restore_from_snapshot.sh`** script — 1.5 hr
13. **Update DEPLOYMENT_CHECKLIST.md** — 30 min

## 📅 Wednesday 2026-04-29 — ~~Real Install on Mac Mini~~ — MOVED TO 2026-04-30

> **Update 2026-04-29 PM:** The real install was rescheduled from Wednesday → Thursday 2026-04-30 to give a full day of repo polish (this sweep, PR triage, branch cleanup, security re-sweep, code cleanup, preflight, `v1.0.0-install-ready` tag). See ROADMAP_TO_MAC_MINI header banner for the canonical date. The four checklist items below remain the planned sequence — only the calendar date moved by one day.

14. Run installer in customer mode with existing creds (~~Wed~~ Thu morning)
15. Document every paper cut as we go
16. ~~Restore VPS data via `restore_from_snapshot.sh`~~ — superseded. Per D-14, no live VPS data is being copied to the Mac Mini; the Mini stands up its own operational DB from migrations 001–005 + 320-row catalog seed. The `restore_from_snapshot.sh` script remains in the tree as an **optional** tool for any future operator who explicitly wants to re-import a historical operational-DB snapshot, but it is **not** part of the canonical Mac Mini install path.
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
| 🟡 2 | CI lint pipeline | ✅ **DONE 2026-04-29** — `scripts/lint_mining_gaurdian_typo.sh` + `.github/workflows/lint.yml` (PR #72, B-6 regression guard). Allow-list refreshed for post-PR-#91 archive layout (62 hits all inside list). |
| 🟡 2 | B-7 migrations 002 | OPEN |
| 🟡 2 | GitHub PAT rotation (S-2 was emergency Sunday — confirm rotation cycle. Renamed 2026-04-29: this rotation was for the GitHub Personal Access Token, not anything VPS-specific.) | OPEN |
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
6. Provision the fix into `installer/grafana/dashboards/intelligence.json` (or wherever this dashboard lives) so the Mac Mini install gets the corrected version on first boot — do not just hot-fix the running Grafana instance ad-hoc.

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

# SECTION 16 — New buckets added 2026-04-29 (mid-Bucket-6 user feedback)

## 16.1 Customer-facing scheduling UI (Bucket 9 sub-item) 🔴 OPEN

The launchd plists landed in Bucket 6a (PR #74) and the cron entries that
Bucket 6b's `setup.sh` writes are the *plumbing*. The customer-facing
Mining Guardian app needs a **non-terminal interface** so site operators
who don't know cron or zsh can:

- Set up scan / cron schedules (pick interval, hour-of-day, weekly cadence).
- Toggle full-auto vs. dry-run vs. paused mode.
- Stop / pause / resume scheduled events without `launchctl bootout` or
  `crontab -e`.

**Why it lives in Bucket 9:** the only audience until the customer app
ships is the operator (Robert), and he is comfortable in a terminal. The
GUI / mode-selector work in Bucket 9 is the right home; this entry
ensures schedule control is a first-class feature of that GUI rather
than an afterthought.

**Internals when the GUI ships:** every control maps to existing plumbing
— schedule changes rewrite `crontab` + the relevant LaunchDaemon
`StartInterval`/`StartCalendarInterval` keys; pause sends
`launchctl bootout`; resume sends `launchctl bootstrap`. No new daemon
type is introduced.

## 16.2 Bucket 10 — Full repo doc cleanup sweep 🔴 OPEN

The reality-check pattern from PR #63 / PR #70 / PR #69 is reactive—
flip stale TODO entries to ✅ once we trip over them. Bucket 10 is the
**proactive** version: walk every doc under the repo, audit it against
current code/state, classify into one of

- **keep as-is** (still accurate),
- **update in place** (mostly right, one or two facts to flip),
- **move to `archive/`** (historical, not current truth, but worth keeping),
- **delete** (instructions for work already done, runbooks for paths
  we no longer take, dead reference material with no archival value).

### Target inventory (first-pass, will be refined when Bucket 10 starts)

| Area | Likely action |
|---|---|
| `docs/SESSION_LOG_2026-04-*.md` | move to `archive/session_logs/` |
| `docs/RUNBOOK_2026-04-*` (afternoon, etc.) | archive once superseded |
| `docs/POSTGRES_MIGRATION_*.md` (status \| plan \| state) | archive once cutover stable |
| `docs/REMAINING_WORK_2026-04-28.md` | reality-check, then archive or delete |
| `docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md` | archive |
| `docs/CRON_RECONCILIATION.md` | reality-check after Bucket 6b ships |
| `REPAIR_LOG.md` | trim entries older than 30 days into archive |
| Root-level `*.md` (CAPABILITIES, NEXT_SESSION, SESSION_COMPLETE, etc.) | reality-check each; most are stale |
| `.claude/` agents/commands/skills | audit which still apply |
| `archive/` | re-prune (already-archived material that's now truly dead) |

### Process (Bucket 10 cadence)

One PR per logical group, not one giant PR. Suggested groupings:

1. PR — archive old session logs (`SESSION_LOG_2026-04-*`).
2. PR — archive Postgres-cutover docs (cutover stable now).
3. PR — reality-check root-level `*.md`.
4. PR — trim REPAIR_LOG.
5. PR — prune `archive/` of truly dead material.
6. PR — `.claude/` audit.

Each PR includes a verification block: a brief "why this is safe to
delete/archive" note per file, plus the standard `grep` confirming no
active code references the doc.

### Why this matters

The operator has been bitten three times in a single session by stale
docs (PR #63, PR #69, PR #70 reality-checks). The runtime defense—
work.projects.mining_guardian.todo_sync, every fix PR flips its
TODO entry in the same commit—stays in force as the steady-state
guardrail. Bucket 10 is the one-time **deep cleanse** that brings the
repo into a state where the runtime defense actually works against
a clean baseline.

---

# SECTION 17 — Update 2026-05-01 (Friday) — v1.0.1 hotfix (Tahoe SSV + dark-mode + model copy)

## 17.1 Status flips

| Row | From | To | Notes |
|---|---|---|---|
| **B-13** — `.pkg` rejected by macOS Tahoe SSV with *"package is incompatible with this version of macOS"* (RELEASE BLOCKER) | 🔴 OPEN | ✅ DONE | Fix landed in this PR. `--install-location` moved from `/` to `/Library/Application Support/MiningGuardian`; payload root no longer wraps in `MiningGuardian/`; `MG_INSTALL_ROOT` updated everywhere. See `docs/RELEASE_NOTES_v1.0.1.md` for the full path-change matrix. |
| **B-12** — `.pkg` Welcome panel renders broken in dark mode on Tahoe (sidebar branding invisible, code chips solid black) | 🔴 OPEN | ✅ DONE | `welcome.html` and `conclusion.html` get `<meta name="color-scheme" content="light only">`, `:root, html { color-scheme: light only; }`, and an explicit `@media (prefers-color-scheme: dark)` block that re-asserts every brand color literal with `!important`. |
| **B-11** — `.pkg` Welcome copy promises RAM-tier model selection, but `setup.sh` Phase 8 force-pulls `qwen2.5:14b-instruct-q4_K_M` regardless of RAM | 🔴 OPEN | ✅ DONE | `phase_08_ollama` now reads `sysctl -n hw.memsize` and selects `qwen2.5:14b-instruct-q4_K_M` for ≥24 GB, `llama3.2:3b` otherwise. Matches `installer/macos-pkg/scripts/lib/detect_ram.sh` exactly. Per locked decision D-13. Welcome copy was already correct against D-13; setup.sh was the offender. |
| Bump version in `pyproject.toml` from 1.0.0 → 1.0.1 | 🔴 OPEN | ✅ DONE | |
| Add `docs/RELEASE_NOTES_v1.0.1.md` | 🔴 OPEN | ✅ DONE | Full root-cause writeup, fix matrix, build/install/uninstall commands, verification block. |

## 17.2 What this PR does NOT fix

The May 1 install attempt logged backlog items B-1 through B-13. Of those, **only B-11/B-12/B-13 ship in v1.0.1**. The remaining items remain 🔴 OPEN:

- B-1 — APFS-naive disk pre-flight (false-negative at 36 GB free) — ✅ DONE in v1.0.2
- B-2 — Phase 2 customer-info UX is unusable raw `read` prompts — ✅ DONE in v1.0.2 (config-file approach: `MiningGuardian.conf.template` + `--config-file=PATH` + validation in `mg_validate_site_config`)
- B-3 — `.pkg` vs `setup.sh` choice not surfaced — ✅ DONE in v1.0.2 (resolved by `docs/INSTALL_PATHS_2026-05-02.md` — Mini = `setup.sh`, end-user laptop = `.pkg` viewer-only — plus runbook cross-links)
- B-4 — Xcode CLT manual install required mid-install (resolved by `.pkg` install path per D-16; doc-only follow-up)
- B-5 — GitHub auth wall (resolved by going public; doc-only follow-up)
- B-6 — Tahoe auto-update mid-install drag
- B-7 — `--dry-run-install` doesn't skip Phase 2 prompts — ✅ DONE in v1.0.2 (placeholder values when dry-run and no `--config-file`)
- B-8 — dry-run requires sudo — ✅ DONE in v1.0.2 (root check already bypassed; B-7 closed the last gap)
- B-9 — Catalog count drift (313 vs 320 — and the count grows; Grafana dropdown must be SQL-driven, not hardcoded) — ✅ DONE in v1.0.2
- B-10 — Runbook says `bash setup.sh` but it's `#!/bin/zsh` — ✅ DONE in v1.0.2

Logged but **not yet a backlog row**: the conclusion.html still says "four services" in two places, but postinstall.sh boots 9. Will be **B-14 — conclusion.html service-count drift (4 vs 9)** in a follow-up PR; out of scope for v1.0.1.

See `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` rows B-1 through B-13 for the full forensic record.

## 17.3 Re-sign + re-notarize required

`build_pkg.sh` cannot run in the agent sandbox — it requires:

- macOS host (`uname -s` Darwin)
- `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` (private)
- `~/MiningGuardian-vendor/` populated with Colima, lima, Ollama.app, postgres-16-bookworm.tar
- Internet for Apple notarization (5–60 min wait per submission)

After this PR merges, the operator runs `./installer/macos-pkg/scripts/build_pkg.sh` on his laptop. Output: `build/MiningGuardian-1.0.1-<sha>.pkg`. Replaces the broken v1.0.0 .pkg on the USB stick + GitHub Release.

## 17.4 QA on Mini after rebuild

| Step | Expected |
|---|---|
| `pkgutil --check-signature MiningGuardian-1.0.1-<sha>.pkg` | "Signed by a developer certificate issued by Apple for distribution" + Developer ID Installer: Robert Fiesler (ARJZ5FYU94) |
| `spctl --assess --type install MiningGuardian-1.0.1-<sha>.pkg` | "accepted" + "Notarized Developer ID" |
| Double-click on Tahoe Mini, dark mode | Welcome screen renders with full branding, code chips visible, no black rectangles |
| Click Install → enter admin password | Install proceeds (B-13 fix). No "package is incompatible with this version of macOS" dialog. |
| `ls -ld "/Library/Application Support/MiningGuardian"` | exists, root:wheel-ish ownership |
| `sudo launchctl print system/com.miningguardian.scanner \| head -5` | service = scanner, state = running |
| `cat /etc/mining-guardian/install-receipt.json` | `install_root: "/Library/Application Support/MiningGuardian"`, `llm_model: "llama3.2:3b"` (16 GB Mini) |

If any step fails, `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh` is the rollback. The `setup.sh` path remains a backstop (also at the new install root after this PR).

# SECTION 18 — Update 2026-05-04 (Monday EOD addendum) — v1.0.3 install paused before `sudo installer`

## 18.1 Status flips landed in this PR (`docs/v103-paused-before-mini-install-2026-05-04`)

| Row | From | To | Notes |
|---|---|---|---|
| §1.2 row 11 — Build, sign, notarize, staple v1.0.3 .pkg | 🔴 OPEN | ✅ DONE | `MiningGuardian-1.0.3-a35728dcfc8c.pkg` from commit `a35728d`. Notary submission `1598b56f-f4da-4926-a319-6567a4d6d5bf` accepted. Stapled. Gatekeeper accepted on build Mac. SHA-256 sidecar at `build/MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256`. See `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`. |
| §1.2 row 12 — Smoke-test on clean Mac VM (UTM/Tart) | 🔴 OPEN | 🚫 SKIPPED (per D-22) | Operator decision 2026-05-04: skip VM, use Mac Mini as the first clean-target install. D-22 captures the rationale and the unchanged D-18 pass criteria, evaluated post-install on the Mini. |
| §1.2 row 13 — Install on Mini + screenshots | 🔴 OPEN | 🟡 STAGED — paused before `sudo installer` | Package on Mini at `/Users/miningguardian/Downloads/MiningGuardian-1.0.3-a35728dcfc8c.pkg`; checksum and Gatekeeper passed; Desktop conf created and shape-checked (7/7 OK); operator paused for a meeting. Resume per `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`. |

## 18.2 Customer-onboarding UX gaps — forward-looking, NOT v1.0.3 scope (per D-23)

These rows track gaps the 2026-05-04 install staging surfaced. They are forward-looking ONLY. The v1.0.3 .pkg already on the Mini ships unchanged. See `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md` for the consolidated brief.

| # | UX Gap | Status | Notes |
|---|---|---|---|
| 18-1 | Replace hand-edited Desktop `MiningGuardian.conf` with native installer form (Installer.app pane plugin) or first-run setup assistant with format hints, inline validation, live credential testing | 🔴 OPEN | Triggered by 2026-05-04 incident where `nano`-edited conf had `REPLACE_ME_SITE_NAME` instead of `CUSTOMER_NAME`. Acceptance: customer never sees `nano`, never types a config-key name, every credential is verified live before any system change. |
| 18-2 | Tailscale guided onboarding (detect state, install if missing, walk customer through `tailscale up`, show Mini's tailnet name + URLs, add a second device) | 🔴 OPEN | Operator quote: "customers can use the free Tailscale option for a small/two-computer setup." Acceptance: customer with no prior Tailscale account ends up with a working tailnet and at least one of their other devices joined; never copies an auth key by hand. |
| 18-3 | Grafana dashboard auto-provisioning — vendor `Grafana.app`, drop datasource + dashboard provisioning yaml, vendor every dashboard JSON, register 11th LaunchDaemon if needed, open AI & Learning dashboard on first boot | 🔴 OPEN | Tied to D-18 Gap 3 / row 4 of §1.2. Default Grafana admin credentials must be rotated per-install (same `openssl rand -hex 32` discipline as `MG_DB_PASSWORD`). Acceptance: no "Import JSON" step; no manual datasource setup. |
| 18-4 | Pre-install Slack / AMS connectivity validation (Slack webhook ping, AMS `/api/v1/login` round-trip, workspace ID resolution) before any system state change | 🔴 OPEN | Today validation is shape-only (regex format checks). Acceptance: typo in AMS password or Slack signing secret blocks "Continue" with a plain-language error; customer fixes in-place without re-running .pkg. |
| 18-5 | Support-bundle export (single command + console button) — last 24h logs from each of 10 services + `launchctl list` + last-run JSON stamps + service status + redacted `.env` shape + version + commit SHA + notarization status, into one tar.gz on Desktop | 🔴 OPEN | Acceptance: zero credential values leave the Mini; operator can reproduce customer state without further questions. |
| 18-6 | `MG_DRY_RUN=true` safe-default for customer-facing templates + dry-run banner in operator console + one-click "Switch to live mode" gated on confirmation | 🔴 OPEN | Acceptance: new customer cannot accidentally enable live remediation on day one; banner is impossible to miss when in dry-run. |
| 18-7 | Surface recovery / uninstall in operator console — "Reset Mining Guardian" button that runs `bin/uninstall.sh --dry-run` first, shows preview, asks confirmation; destructive `--purge-data` requires red affordance + double-confirm; "Re-run setup assistant" for credential rotation | 🔴 OPEN | P-008 already shipped `bin/uninstall.sh` with data-preserving default. This row wires it into the console UI. |
| 18-8 | Screenshot-ready customer runbook PDF/web doc walking every dialog in order with annotated screenshots; updated whenever a dialog string changes | 🔴 OPEN | Acceptance: nontechnical customer can install end-to-end with the PDF and no live support. |

**All §18 rows are forward-looking under D-23.** Do NOT pull any of them into the current pause-resume work. Open a separate work train against `main` after the Mini install is verified green.

