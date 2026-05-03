# Mining Guardian v1.0.3

**Release date:** 2026-05-04 (source-tree readiness; build/sign/notarize/staple still pending on operator's laptop — see "Build & verification gates" below)
**Build SHA:** _stamped at build time by_ `installer/macos-pkg/scripts/build_pkg.sh` _from `pyproject.toml` (now `1.0.3`) and `git rev-parse --short HEAD`_
**Distribution:** Private GitHub Release + USB stick fallback (no public registry, no cloud-only dependencies)

---

## What this release is

The first **customer-grade** Mining Guardian `.pkg`. v1.0.0 / v1.0.1 / v1.0.2 each shipped as "release-grade" but were progressively closer approximations of the customer-experience vision; the v1.0.2 .pkg audit (`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`) found that the v1.0.2 build would produce an Apple-confirmed "install completed" dialog with a non-functional Mini — every LaunchDaemon crash-loops within seconds, no catalog DB, no Grafana, no scheduled tasks, no customer-info collection. **Apparent success, real silence** — the worst-case failure mode.

D-18 locked v1.0.3 as the build that closes ALL audit gaps (Gap 1, 2, 4, 5 plus four user-facing copy bugs and three of the four integration bugs) before the Mac Mini cutover. Two items are deliberately deferred from v1.0.3: **Gap 3 (Grafana vendoring + provisioning + LaunchDaemon)** and **Cloudflare Tunnel + Access auto-provisioning** — both per explicit operator direction and tracked in `docs/MG_UNIFIED_TODO_LIST.md` rows 4 + 9 for a follow-up release.

The .pkg payload shape changes meaningfully versus v1.0.2: a new Python venv is created with vendored wheels (Gap 5), the catalog DB and 320-row Bitcoin SHA-256 baseline seed are provisioned at install time (Gap 2), the customer-info Desktop conf flow replaces the never-shipped GUI form (Gap 1), eleven scheduled-task launchd plists replace the old `crontab -` install path (Gap 4), the customer-facing operator console binds at `127.0.0.1:8787` as the 10th LaunchDaemon (D-19 P-006 foundation), and a real `bin/uninstall.sh` covering all 21 daemons (10 services + 11 scheduled-jobs) ships under `${MG_INSTALL_ROOT}/bin/` (Copy bug 3).

Bitcoin SHA-256 miners only. Local-only by design.

---

## PR train (P-001 → P-009)

| P-NN | What it closes | Branch | PR | Merge SHA |
|---|---|---|---|---|
| P-001 | v1.0.3 discovery (approval-queue location, Live Action Queue panel verdict, mg_import_tool/ payload audit) — no code | `docs/discovery-2026-05-04` | [#117](https://github.com/robertfiesler-spec/Mining-Guardian/pull/117) | `8405d21` |
| P-002 | D-18 Gap 5 — Python venv + offline pip install from vendored wheels | `mg/v103-gap5-postinstall-venv` | [#118](https://github.com/robertfiesler-spec/Mining-Guardian/pull/118) | `ef89fff` |
| P-003 | D-18 Gap 2 — Catalog DB + 320-row seed at install time | `mg/v103-gap2-catalog-db-and-seed` | [#119](https://github.com/robertfiesler-spec/Mining-Guardian/pull/119) | `5842f3c` |
| P-004 | D-20 importer-payload reconciliation (mg_import_tool/ excluded from .pkg) | `mg/v103-d20-importer-payload-reconciliation` | [#120](https://github.com/robertfiesler-spec/Mining-Guardian/pull/120) | `b76907f` |
| P-005 | D-18 Gap 1 — Customer-info Desktop conf flow + Integration bugs 1/2/4 | `mg/v103-gap1-customer-info-conf` | [#121](https://github.com/robertfiesler-spec/Mining-Guardian/pull/121) | `f63b9fe` |
| P-006 | D-19 — Operator console foundation (10th LaunchDaemon, port 8787) | `mg/v103-d19-console-foundation` | [#122](https://github.com/robertfiesler-spec/Mining-Guardian/pull/122) | `9d53856` |
| P-007 | D-18 Gap 4 — 11 scheduled-task launchd plists (replaces `setup.sh::phase_10_cron`) | `mg/v103-gap4-scheduled-launchd` | [#123](https://github.com/robertfiesler-spec/Mining-Guardian/pull/123) | `ade63ef` |
| P-008 | D-18 Copy bugs 1/2/4 + Copy bug 3 real `bin/uninstall.sh` | `mg/v103-p008-installer-copy-and-uninstall` | [#124](https://github.com/robertfiesler-spec/Mining-Guardian/pull/124) | `c450d12` |
| P-009 | Version bump 1.0.2 → 1.0.3 + this RELEASE_NOTES file + pre-build readiness audit | `mg/v103-version-bump-and-release-notes` | _this PR_ | _stamped on merge_ |

---

## Fixes — the v1.0.2 audit gaps closed in v1.0.3

### Gap 5 — Python venv + offline pip install (P-002, PR [#118](https://github.com/robertfiesler-spec/Mining-Guardian/pull/118))

**Symptom (v1.0.2):** the .pkg payload shipped Python source code but never created `${MG_INSTALL_ROOT}/venv` and never installed dependencies. The launchd plists for all nine services pointed `ProgramArguments[0]` at `${MG_INSTALL_ROOT}/venv/bin/python`, so every service crash-looped on first start with `No such file or directory`.

**Fix:** New `step_create_venv` in `installer/macos-pkg/scripts/postinstall.sh` calls `python3 -m venv` against the bundled CPython, then runs `pip install --no-index --find-links=<vendored>/python-wheels -r installer/macos-pkg/payload-requirements.txt`. No network call at install time. New `installer/macos-pkg/payload-requirements.txt` is the pinned closure of what the runtime imports (FastAPI, psycopg, jinja2, htmx-friendly client deps, etc.). `build_pkg.sh` step 4e + 4f vendor the wheels into the staged payload before signing. Exit code 38 reserved for venv failures.

**Tests:** `tests/installer/test_postinstall_venv.sh` — 24 assertions, all green.

### Gap 2 — Catalog DB + 320-row seed (P-003, PR [#119](https://github.com/robertfiesler-spec/Mining-Guardian/pull/119))

**Symptom (v1.0.2):** the Postgres container the .pkg provisioned only created the operational `mining_guardian` DB. The intelligence catalog DB and its 320-row Bitcoin SHA-256 baseline never landed. Every dashboard panel and AI prompt that referenced `hardware.miner_models` returned zero rows.

**Fix:** New `step_provision_catalog_db_and_seed` in postinstall creates `mining_guardian_catalog` in the Colima container, applies the canonical schema bundle (`intelligence-catalog/seed-data/deploy_schema.sql` which `\ir`-includes v1/v2/v3 + staging schema), and seeds the 320-row baseline (`intelligence-catalog/seed-data/seed_miner_models.sql`). New `step 4g` post-assembly assertion in `build_pkg.sh` aborts the build with exit 44 if the seed files are missing from the payload. Exit code 39 reserved for catalog provisioning failures at install time.

**Why 320 specifically:** that is the count at this release per `intelligence-catalog/seed-data/seed_miner_models.sql` row count. Per `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md`, the catalog is a living list — the seed snapshot installed at v1.0.3 will be refreshed by the post-cutover monthly Tailscale-push pipeline (D-17 + D-20).

**Tests:** `tests/installer/test_postinstall_catalog_seed.sh` — 24 assertions, all green.

### D-20 — importer not in customer .pkg (P-004, PR [#120](https://github.com/robertfiesler-spec/Mining-Guardian/pull/120))

**Symptom (v1.0.2):** the `.pkg` payload bundled `mg_import_tool/` even though no LaunchDaemon or console UI surfaced it. Per D-20 (locked 2026-05-03) the importer is operator-only, forever — customer Minis are read-only consumers of catalog snapshots produced by the operator.

**Fix:** `build_pkg.sh` step 4a no longer includes `mg_import_tool/***` in the rsync include list; the cross-directory `mg_import_tool/sql/migrations/` rsync was removed. Runtime-relevant importer migrations were relocated to `migrations/006_field_log_bootstrap.sql` and `migrations/007_layer2_resolver.sql` (byte-identical bodies, idempotency preserved). New `step 4h` post-assembly assertion runs `find <payload> -name 'mg_import*'` and aborts the build with exit 43 on any match. Operator-side originals at `mg_import_tool/sql/migrations/` are intentionally retained — the importer needs its own bootstrap copy on the operator workstation.

**Tests:** `tests/installer/test_d20_importer_payload_reconciliation.sh` — 32 assertions, all green.

### Gap 1 — Customer-info Desktop conf flow + Integration bugs 1, 2, 4 (P-005, PR [#121](https://github.com/robertfiesler-spec/Mining-Guardian/pull/121))

**Symptom (v1.0.2):** the customer-info collection step the welcome screen advertised did not exist. Postinstall wrote a placeholder `.env` missing every customer-tunable key (AMS_*, SLACK_*, AUTHORIZED_SLACK_USER_IDS, AUTO_APPROVE_ENABLED). `MG_DB_PASSWORD` was staged out-of-band via `/tmp/mg_install_env_secret`, an artifact of an earlier WIP experiment that never got cleaned up. `GUARDIAN_PG_USER` and `PGUSER` disagreed across modules.

**Fix:** New `step_collect_customer_info` reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`, validates per B-2 rules (mirrors `scripts/setup.sh::mg_validate_site_config` line-for-line — URL schemes, email format, integer types, Slack token prefixes), and aborts BEFORE any system-state change with a Cocoa dialog (`osascript display dialog`) on missing or invalid input (exit code 41). `step_drop_dotenv` rewritten to consume the validated values + generate per-install secrets (`MG_DB_PASSWORD`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`) via `openssl rand -hex 32` in-process — no `/tmp` staging — and write a full `.env` matching `setup.sh::phase_07_secrets` line-for-line. Both `GUARDIAN_PG_USER` and `PGUSER` are written with value `mg` until the codebase converges on a single key name.

**Operator workflow:** operator hands customer a USB or AirDrop with a pre-filled `MiningGuardian.conf` (template at `installer/macos-pkg/resources/MiningGuardian.conf.template`); customer drops on Desktop; double-clicks .pkg. No CLI, no environment variables, no tokens visible to the customer.

**Tests:** `tests/installer/test_postinstall_customer_info.sh` — 76 assertions, all green.

### Gap 4 — Scheduled-tasks launchd plists (P-007, PR [#123](https://github.com/robertfiesler-spec/Mining-Guardian/pull/123))

**Symptom (v1.0.2):** `setup.sh::phase_10_cron` (Mini-only path) installed 11 cron entries via `crontab -`. The .pkg postinstall did NOT, so a customer Mini installed via .pkg had no morning briefing, no weekly training, no daily deep dive, no log collection, no benchmark — no recurring AI-loop work at all.

**Fix:** 11 launchd plists at `installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.<task-key-hyphenated>.plist`. 10 use `StartCalendarInterval`; the hourly benchmark uses `StartInterval=3600`. One generic launcher (`installer/macos-pkg/resources/launchd/launchers/scheduled_job_launcher.sh`) sources `.env`, dispatches by file extension (`.py` → venv python, `.sh` → bash), and writes `${INSTALL_ROOT}/logs/scheduled/<task_key>.last-run.json` for the operator console (D-19) to surface "last run" status without a DB write per fire. New `step_install_scheduled_plists_and_bootstrap` in postinstall (exit 40) and `step 4i` source-tree assertion in `build_pkg.sh` (exit 47). `scripts/setup.sh::phase_10_cron` rewritten as `phase_10_scheduled` — same 11 plists, no `crontab -` install path remains.

**Tests:** `tests/installer/test_postinstall_scheduled_jobs.sh` — 115 assertions, all green.

### D-19 — Operator console foundation (P-006, PR [#122](https://github.com/robertfiesler-spec/Mining-Guardian/pull/122))

**Symptom (v1.0.2):** no customer-facing operator console. Customer interactions all went through Slack (#mg-approvals) or, for power users, the Grafana panels (read-only and not the design intent).

**Fix:** New `console/` package — FastAPI app under `console/main.py` (Jinja2 + HTMX, no React, no node, no build step), task registry of the 10 services + 11 scheduled jobs (`console/task_registry.py`), launchctl wrapper (`console/launchd_controls.py`), system-state probes (`console/system_state.py`), pending-approvals helpers (`console/approvals.py`). Templates + static CSS under `console/templates/` and `console/static/`. New 10th LaunchDaemon plist (`com.miningguardian.console.plist`) and launcher (`console_launcher.sh`); postinstall PLIST_LABELS / LAUNCHER_FILES extended (now 10 services); `build_pkg.sh` rsync include list extended with `console/***`.

**Port note (locked 2026-05-04 in P-006 / `docs/CONSOLE_OPERATIONS_GUIDE.md`):** D-19 originally requested 8686, but `api/approval_api.py` already owns 8686 (Slack approve/deny + Bucket 9 §10.1 `/ui` GUI). The console binds to **8787** instead. The full v1.0.3 port table:

| Service | Port | Bind |
|---|---|---|
| Dashboard API | 8585 | 127.0.0.1 |
| Approval API | 8686 | 127.0.0.1 |
| Operator Console | 8787 | 127.0.0.1 |

**Approval queue scope (v1):** Approve/Deny update `pending_approvals.status` directly with `responded_by` audit. Remediation execution (RESTART / PDU_CYCLE) stays with the existing Slack flow until a unified execution library lands (post-cutover work item).

**Security:** `INTERNAL_API_SECRET` never leaks to the browser — verified by `test_internal_secret_never_appears_in_html` walking every public GET route with a sentinel value in the env. **Grafana UI explicitly untouched in this PR** (per operator clarification 2026-05-04 — Grafana is the visibility surface, the console is the control surface).

**Tests:** `tests/console/` — 63 tests, all green (`python3 -m pytest tests/console/ -q`).

### Copy bug 1, 2, 4 + Copy bug 3 — real `bin/uninstall.sh` (P-008, PR [#124](https://github.com/robertfiesler-spec/Mining-Guardian/pull/124))

**Symptom (v1.0.2):** `welcome.html` said "four background services" (off by six) and pointed at `:8080` for the dashboard (wrong port). `conclusion.html` said "All four" (off by six), enumerated only four services in its verify code block, and pointed customers at a `bin/uninstall.sh` that did not exist in the payload.

**Fix:**
- `welcome.html` — "four" → "ten background services"; added line documenting the eleven scheduled jobs (launchd wording, deliberately no `crontab` literal); added "What you'll need" bullet for the customer's Desktop `MiningGuardian.conf` hand-off; dashboard URL `:8080` → `:8585`; added operator console URL `:8787`.
- `conclusion.html` — "All four" → "All ten"; added scheduled-jobs sentence; quick-link grid shows dashboard `:8585`, approval API `:8686`, operator console `:8787`, scheduled-job log path; verify code block enumerates all 10 service labels and adds a `launchctl list | grep com.miningguardian.scheduled.` hint; uninstall blurb mentions `--dry-run` and `--purge-data`.
- New `installer/macos-pkg/resources/uninstall.sh` (mode 0755, shellcheck-clean) — covers all 10 service LaunchDaemons + 11 scheduled-job LaunchDaemons via `launchctl bootout` then plist `rm`, removes `mining-guardian-db` Postgres container (best-effort), stops `mining-guardian` Colima profile (best-effort, never fatal), removes `${MG_INSTALL_ROOT}/` content **except `postgres-data/` by default**, removes `/etc/mining-guardian/install-receipt.json`. Flags: `--help` / `--dry-run` / `--yes` / `--purge-data` / `--purge-logs`. Default behavior preserves `postgres-data` and `/var/log/mining-guardian` — data deletion is opt-in per the §"Critical Safety Rules" entry forbidding bulk deletes from `mining_guardian` without an explicit step.
- Stale `:8080` / `:8081` log lines in `installer/macos-pkg/scripts/postinstall.sh::main()` corrected to `:8585` / `:8686` / `:8787`.

**Tests:**
- `tests/installer/test_installer_copy.sh` — 43 assertions (welcome + conclusion).
- `tests/installer/test_uninstall_script.sh` — 50 assertions (uninstall + drift checks vs postinstall plist labels).

### Version bump + RELEASE_NOTES_v1.0.3.md + pre-build readiness audit (P-009 — this PR)

**Scope:**
- `pyproject.toml` `version = "1.0.2"` → `version = "1.0.3"`. This is the single source of truth — `installer/macos-pkg/scripts/build_pkg.sh::step_3_stamp_build` reads it and stamps every output file with `MiningGuardian-${BUILD_VERSION}-${BUILD_SHA}.pkg`.
- This file (`docs/RELEASE_NOTES_v1.0.3.md`) — full P-001 through P-009 record with PR cross-links and merge SHAs.
- New `docs/PRE_BUILD_READINESS_v1.0.3_2026-05-04.md` — static-analysis audit of the source tree against the audit gaps and copy bugs, the build pipeline itself, and the test surface, surfacing any remaining blocker that would stop a clean build/sign/notarize tomorrow.
- New `tests/installer/test_release_notes_version_drift.sh` — guards against a future version bump that forgets to ship the matching `RELEASE_NOTES_vX.Y.Z.md`, or a release notes file that lands without a `pyproject.toml` bump.
- `docs/MG_UNIFIED_TODO_LIST.md` row 10 (Version bump + RELEASE_NOTES_v1.0.3.md) flipped 🔴 → ✅ in the same commit. Rows 11 (build/sign/notarize), 12 (clean-VM smoke test), 13 (install on Mini), 14 (VPS decommission + ROBS-PC shutdown) remain 🔴 — the source-tree readiness PR is the LAST source-tree-only PR before the operator's laptop takes over.
- `docs/DECISIONS.md` D-18 implementation status appended with the P-009 SHIPPED entry.
- `docs/handoffs/HANDOFF_2026-05-04.md` — new EOD handoff per D-15 protocol.

**No code changes outside the version stamp.** No installer logic touched. No tests changed beyond the new drift guard. No payload shape change. The .pkg the operator builds tomorrow uses the EXACT source tree that P-001 through P-008 produced; the only delta is the version stamp on the filename and build receipt.

---

## What is NOT in v1.0.3 (deferred, with the open-row reference)

| Item | Status | Tracked at |
|---|---|---|
| Gap 3 — Grafana vendoring + provisioning + 11th LaunchDaemon | 🔴 deferred | `docs/MG_UNIFIED_TODO_LIST.md` row 4 |
| Cloudflare Tunnel + Access auto-provisioning (D-19 step 5) | 🔴 deferred | `docs/MG_UNIFIED_TODO_LIST.md` row 9 |
| Integration bug 3 — Tailscale auto-up | 🔵 partial | postinstall surfaces a Cocoa dialog if Tailscale is not up; auto-`tailscale up` is operator-side responsibility per D-19 §"Cloudflare Tunnel + Access setup" |
| `MG_INSTALL_LOG` / `MG_INSTALL_ENV` `--force` reinstall flag | 🔵 future | Audit Section 7 bonus finding — not a blocker for v1.0.3 |
| Welcome screen "Tahoe (macOS 14.x)" mention | 🔵 cosmetic | Audit Section 7 bonus finding — copy still says "macOS 13 (Ventura) or later" which is correct but doesn't surface Tahoe |
| Migration of codebase to a single PG-user key (eliminate dual `GUARDIAN_PG_USER` + `PGUSER`) | 🔵 tech debt | `docs/MG_UNIFIED_TODO_LIST.md` §3 |
| Grafana cleanup / provisioning (UI panels, dashboards) | 🔴 deferred | per operator instruction 2026-05-04: "do NOT fix Grafana right now" |

The Grafana and Cloudflare deferrals are deliberate per operator direction. Both are tracked as open rows in the unified TODO list and will land in a follow-up release. The v1.0.3 .pkg ships without them; the operator console (D-19 P-006 foundation) is sufficient for the customer's day-one operating surface.

---

## Build & verification gates (still required)

This release notes file commits the source-tree readiness for v1.0.3. The remaining gates are operator-side and HARD per D-18:

1. **Build / sign / notarize / staple** the v1.0.3 .pkg on the operator's laptop. Reads `pyproject.toml` for the version stamp; reads `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` for credentials (never committed).
2. **Smoke-test on a clean macOS 14 VM (UTM/Tart).** Required pass criteria (per `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` Section 6):
   - Postgres container up, all 3 DBs created (`mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`).
   - `SELECT count(*) FROM hardware.miner_models;` against `mining_guardian_catalog` returns 320.
   - Grafana :3000 — _N/A in v1.0.3, deferred per row 4_.
   - All 10 LaunchDaemons (9 + console) loaded via `launchctl list | grep com.miningguardian.` (excluding `.scheduled.`).
   - All 11 scheduled-task launchd plists registered: `launchctl list | grep com.miningguardian.scheduled.` returns 11 lines.
   - `~/Desktop/MiningGuardian.conf` validation passes for valid input, fails-with-Cocoa-dialog for invalid input.
   - Console reachable at `http://127.0.0.1:8787/`, displays task list + automation toggles + approval queue.
   - Cloudflare Tunnel — _N/A in v1.0.3, deferred per row 9_.
   - Welcome + conclusion HTML show correct service counts (10) and ports (8585/8686/8787).
   - `bin/uninstall.sh --dry-run` previews exactly the 21 plist labels + the postgres container + the install root, then `bin/uninstall.sh` cleanly tears down everything.
3. **Install on the Mac Mini.** Operator-driven, screenshots at every screen per D-16 step 4 (as amended by D-18).
4. **Verify Mini green** per D-16 cutover criteria.
5. **Then — and only then — VPS decommission + ROBS-PC container shutdown** per D-16.

Until step 2 passes, the Mini does not get installed. Until step 4 verifies green, the Hostinger VPS keeps running production and ROBS-PC's catalog volume stays intact.

---

## How to build, install, and uninstall v1.0.3

### Build (operator's laptop, not the Mini)

```zsh
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only origin main
git log -1 --format=%h   # capture the SHA — this becomes the filename suffix
./installer/macos-pkg/scripts/build_pkg.sh
# Output: build/MiningGuardian-1.0.3-<sha>.pkg
# Output: build/MiningGuardian-1.0.3-<sha>.pkg.sha256
# Output: build/MiningGuardian-1.0.3-<sha>.notarization-log.txt
```

`build_pkg.sh` reads the version from `pyproject.toml` (now `1.0.3`), refuses to run on a dirty git tree, vendors the Python wheels (Gap 5 — step 4e + 4f), asserts the catalog seed is staged (Gap 2 — step 4g, exit 44), asserts the customer payload contains no `mg_import*` paths (D-20 — step 4h, exit 43), asserts the 11 scheduled-task plists are present (Gap 4 — step 4i, exit 47), asserts `bin/uninstall.sh` is present and executable (Copy bug 3 — step 4j, exit 48), then signs with Apple Developer ID Installer (`Robert Fiesler — ARJZ5FYU94`), submits for notarization (key `FPZJ87B3QF`), and staples the ticket.

### Install (customer end-user, the `.pkg` path)

The customer's prerequisites:
- Mac Mini powered on, network reachable, Tahoe (macOS 14.x).
- Tailscale installed and `tailscale up` already run by the operator (Integration bug 3 — surfaces a Cocoa dialog if not up).
- `~/Desktop/MiningGuardian.conf` present, pre-filled by the operator (handed over via USB or AirDrop).

```zsh
sudo installer -pkg MiningGuardian-1.0.3-<sha>.pkg -target /
# OR double-click the .pkg in Finder.
```

What postinstall does, in order:
1. Read + validate `~/Desktop/MiningGuardian.conf` (Gap 1, P-005). Cocoa dialog + exit 41 if missing or invalid.
2. Lay out `${MG_INSTALL_ROOT}` and stage the payload.
3. Provision the Colima Postgres container, both DBs (operational + catalog), apply migrations, seed the 320-row catalog (Gap 2, P-003).
4. Create the venv and pip-install from the vendored wheels (Gap 5, P-002).
5. Generate per-install secrets (`MG_DB_PASSWORD`, `CATALOG_API_KEY`, `INTERNAL_API_SECRET`) via `openssl rand -hex 32` and write the full `.env` matching `setup.sh::phase_07_secrets` (Integration bugs 1, 2, 4 — P-005).
6. Install the 10 service LaunchDaemons (9 services + console — D-19 P-006).
7. Install the 11 scheduled-task launchd plists (Gap 4, P-007).
8. Install `bin/uninstall.sh` to `${MG_INSTALL_ROOT}/bin/` mode 0755 root:wheel (Copy bug 3, P-008).
9. Write `/etc/mining-guardian/install-receipt.json`.
10. Bootstrap the 10 service plists + 11 scheduled-task plists.

### Verify

```zsh
# Signature + notarization
shasum -a 256 MiningGuardian-1.0.3-<sha>.pkg
pkgutil --check-signature MiningGuardian-1.0.3-<sha>.pkg
spctl --assess --type install MiningGuardian-1.0.3-<sha>.pkg

# After install — service health
launchctl list | grep com.miningguardian. | grep -v scheduled    # expect 10 lines
launchctl list | grep com.miningguardian.scheduled.              # expect 11 lines

# DB health
psql -h 127.0.0.1 -U mg -d mining_guardian_catalog -c \
  'SELECT count(*) FROM hardware.miner_models;'                  # expect 320

# Operator console
curl -sf http://127.0.0.1:8787/ | head -1                        # expect HTTP 200
```

### Uninstall (customer laptop)

```zsh
# Preview first — never mutates the box
sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --dry-run

# Default uninstall — preserves postgres-data and /var/log/mining-guardian
sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh

# Full purge — operational history destroyed; combine with --yes for non-TTY
sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh --purge-data --purge-logs
```

---

## What's not changing in v1.0.3

- No DB schema migrations beyond what was already shipped in v1.0.2. Migrations 006 + 007 (P-004 D-20 importer reconciliation) are byte-identical to the importer-side originals — idempotency preserved on Minis that already had the importer-side 000 / 002 applied via earlier .pkg builds.
- No Postgres / Colima / Ollama version bumps. Same `postgres:16-bookworm` image. Same Ollama auto-RAM-tier model selection per D-13.
- No Apple signing / notarization changes. Same Developer ID Installer cert (`Robert Fiesler — ARJZ5FYU94`), same notarization key (`FPZJ87B3QF`).
- No Slack / AMS / Tailscale credential changes.
- The catalog count is still 320 at this build snapshot. Per the dynamic-count rule (`docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md`), Grafana panels and AI prompts read `count(*)` at runtime — the number floats as the catalog grows.

---

## Reverse links

- `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` — the audit that authorized v1.0.3
- `docs/discoveries/DISCOVERY_2026-05-04.md` — P-001 discovery output
- `docs/PRE_BUILD_READINESS_v1.0.3_2026-05-04.md` — P-009 pre-build static audit
- `docs/INSTALL_PATHS_2026-05-03.md` — install-path architecture (canonical)
- `docs/CONSOLE_OPERATIONS_GUIDE.md` — D-19 console operator guide
- `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md` — catalog count is dynamic, never hardcoded
- `docs/MG_UNIFIED_TODO_LIST.md` §1.2 — v1.0.3 installer train rows 1-14 (rows 1-3, 5-8, 10 closed; rows 4, 9, 11-14 open)
- `docs/DECISIONS.md` D-18 / D-19 / D-20 — locked decisions that scope this release
- `docs/handoffs/HANDOFF_2026-05-04.md` — today's session handoff
- `docs/RELEASE_NOTES_v1.0.2.md` — previous release
