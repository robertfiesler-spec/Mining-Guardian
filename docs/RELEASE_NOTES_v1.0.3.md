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
| P-010 | Wheelhouse hard-fail in `build_pkg.sh` step 4e | `mg/v103-p010-wheelhouse-fail-hard` | _stamped on merge_ | `295aec3` |
| P-011 | Re-sign Mach-O inside vendored Python wheels (Apple notary `Invalid` for `750c089f-…`) | `mg/v103-p011-wheel-resign` | _stamped on merge_ | `d8bbed5` |
| P-012 | `resign_wheel.py` 3.9 compat for `/usr/bin/python3` on macOS | `mg/v103-p012-resign-wheel-py39-compat` | _stamped on merge_ | `a35728d` |
| P-013 | pkgbuild scripts must be staged with extensionless names (`preinstall`, `postinstall`); `MiningGuardian-1.0.3-a35728dcfc8c.pkg` was payload-only because PackageKit silently ignored `preinstall.sh` / `postinstall.sh` | `mg/v103-p013-pkg-scripts-naming` | _this PR_ | _stamped on merge_ |
| P-014 | `build_pkg.sh` step 4d rsync excludes `build_pkg.sh` itself from scripts staging — first `make pkg` after P-013 merged hit the new P-013 leftover-`*.sh` guard because `build_pkg.sh` lives next to `preinstall.sh`/`postinstall.sh` and was being rsync'd into the package-script staging dir | `mg/v103-d18-p014-staging-exclude-build-pkg` | _this PR_ | _stamped on merge_ |
| P-015 | Preinstall arch gate Rosetta-safe (`sysctl hw.optional.arm64`, never `uname -m`) — `MiningGuardian-1.0.3-2b48f98e6b77.pkg` first install on customer Mac mini hard-failed at `gate_apple_silicon` because `/usr/bin/uname -m` returned `x86_64` under a Rosetta-translated `/bin/bash` even though the Mac is M-series | `mg/v103-d18-p015-arch-gate-rosetta-safe` | _this PR_ | _stamped on merge_ |

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

### P-013 — pkgbuild scripts must be staged with extensionless names (this PR)

**Problem:**
On 2026-05-04 Rob installed signed/notarized v1.0.3 build `a35728d` on the customer Mac mini with `sudo installer -pkg "MiningGuardian-1.0.3-a35728dcfc8c.pkg" -target /`. The installer reported success and `BUILD_STAMP.json` showed v1.0.3 `a35728dcfc8c` at `/Library/Application Support/MiningGuardian`. But every postinstall artifact was missing — no `/etc/mining-guardian/install-receipt.json`, no `/var/log/mining-guardian/install-postinstall.log`, no `.env`, no `venv`, no `logs`, no `postgres-data`, no `bin/`. `/var/log/install.log` showed PackageKit extracted the payload + wrote the receipt + logged "Installed Mining Guardian (1.0.3)", but ZERO preinstall/postinstall script execution lines.

**Root cause:**
Apple's `pkgbuild --scripts` honors EXACTLY two top-level filenames in the Scripts archive: `preinstall` and `postinstall`, with NO extension. From `man pkgbuild`: *"If this directory contains scripts named preinstall and/or postinstall, these will be ran as the top-level scripts of the package."* PackageKit silently ignores any other filename — including `preinstall.sh` and `postinstall.sh`. `build_pkg.sh::step_4_assemble_payload` step 4d staged the scripts under their repo names `preinstall.sh` / `postinstall.sh`, so PackageKit silently ignored them — payload was laid down, BOM + receipt were written, install reported "success", and the scripts NEVER fired.

**Fix:**
`build_pkg.sh::step_4_assemble_payload` step 4d now `mv -f` the staged scripts into extensionless names inside `${BUILD_DIR}/stage/scripts/`:

```
${SCRIPTS_DIR}/preinstall.sh  → ${SCRIPTS_DIR}/preinstall   (chmod 0755)
${SCRIPTS_DIR}/postinstall.sh → ${SCRIPTS_DIR}/postinstall  (chmod 0755)
```

After the rename, step 4d runs `find -maxdepth 1 -type f -name '*.sh'` against the staging dir and aborts the build with exit 43 if anything `*.sh` remains at the top level (belt-and-suspenders against a future refactor that copies instead of moves). Source files retain the `.sh` extension on disk so editor highlighting, shellcheck, and `bash -n` keep working — the rename only happens at build-time staging.

**Tests:**
- `tests/installer/test_pkg_scripts_naming.sh` — 15 assertions, all green. Covers source-tree `.sh` presence + executable bits, `bash -n`, the rename live-line, the chmod 0755 line, the `find` guard, the post-rename `[[ -x ]]` assertions, and a "no stray live reference to `${SCRIPTS_DIR}/(pre|post)install.sh` outside the rename block" drift check.
- All 9 prior installer test suites still green; `build_pkg.sh` shellcheck baseline unchanged at 2.

**Detection (durable):**
For any future build, expand the .pkg and inspect the Scripts archive:

```
pkgutil --expand build/MiningGuardian-1.0.3-<sha>.pkg /tmp/mg-pkg-check
ls /tmp/mg-pkg-check/core.pkg/Scripts/
# MUST show exactly:  preinstall  postinstall  lib/   (and resign_wheel.py)
# MUST NOT show:      preinstall.sh  postinstall.sh
rm -rf /tmp/mg-pkg-check
```

**Critical operator note:**
The existing `MiningGuardian-1.0.3-a35728dcfc8c.pkg` is NOT a shippable artifact. It has signed payload + valid Gatekeeper acceptance + valid receipt, but no postinstall ever ran. The Mac mini currently has a payload-only install. The cleanup + rebuild + reinstall path is in the PR description and `docs/RUNBOOK_PKG_REBUILD.md` Block-Cleanup. After P-013 lands, the next `make pkg` produces a shippable .pkg from the EXACT same source tree (no payload changes, only the staging-time rename).

### P-014 — step 4d rsync excludes `build_pkg.sh` from scripts staging (this PR)

**Problem:**
First `make pkg` after PR #130 (P-013) merged aborted at the new P-013 belt-and-suspenders guard:

```
[build_pkg] step 4d FAIL: leftover top-level *.sh in scripts staging dir:
/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/stage/scripts/build_pkg.sh
[build_pkg] FATAL (43) step 4d: top-level *.sh files in .../build/stage/scripts after rename
```

**Root cause:**
`installer/macos-pkg/scripts/build_pkg.sh` lives in the same source directory as `preinstall.sh` and `postinstall.sh`. The step 4d rsync `${PKG_DIR}/scripts/` → `${SCRIPTS_DIR}/` had no exclude, so it copied `build_pkg.sh` into the package-script staging dir alongside the two real scripts. After the .sh→extensionless rename, `build_pkg.sh` was the only stray top-level `*.sh` left — which (a) tripped the P-013 leftover-`*.sh` guard with exit 43 (working as designed — guard caught the regression before the build burned an Apple notarization round-trip), and (b) if the guard were ever removed, would re-trigger the original P-013 silent-ignore failure mode (PackageKit ignores the entire scripts archive when it sees unrecognized top-level filenames next to `preinstall`/`postinstall`).

**Fix:**
Add `--exclude 'build_pkg.sh'` to the step 4d rsync. After the fix the staging dir contains only:

```
${SCRIPTS_DIR}/preinstall      (renamed from preinstall.sh,  chmod 0755)
${SCRIPTS_DIR}/postinstall     (renamed from postinstall.sh, chmod 0755)
${SCRIPTS_DIR}/lib/            (helper shell + python files)
```

The P-013 leftover-`*.sh` guard is unchanged and continues to assert zero top-level `*.sh` after the rename — it will still catch any future stray, including a non-`build_pkg.sh` filename.

**Tests:**
- `tests/installer/test_pkg_scripts_naming.sh` — extended from 15 → 17 assertions. New §8 verifies the rsync line passes `--exclude 'build_pkg.sh'` (multiline grep so the flag can stay on its own line) and that the source has a `P-014` audit marker for cheap forensics.
- All 17 assertions green; all 9 prior installer test suites still green.

**Operator commands after merge:**

```
git checkout main
git pull --ff-only origin main
make pkg
```

The next `make pkg` should clear step 4d cleanly and proceed through pkgbuild + productbuild + productsign + notarytool.

---

### P-015 — preinstall arch gate Rosetta-safe (this PR)

**Problem:**
First install of the corrected v1.0.3 .pkg `MiningGuardian-1.0.3-2b48f98e6b77.pkg` (built from `main` 2b48f98 with P-013 + P-014 in) on the customer Mac mini hard-failed at `gate_apple_silicon`. `/var/log/mining-guardian/install-preinstall.log` showed:

```
… [preinstall] OK gate_root: running as root
… [preinstall] OK gate_macos_version: 26.4.1 >= 13.0
… [preinstall] FATAL (12) this build supports Apple Silicon (arm64) only; detected 'x86_64'
… [preinstall] Aborting install. See /var/log/mining-guardian/install-preinstall.log for full context.
```

The Mac mini is documented in `CLAUDE.md` as M-series. The signal misled.

**Root cause:**
`gate_apple_silicon` called `/usr/bin/uname -m` and compared the result to `arm64`. `uname -m` reports the architecture of the **calling process**, not the hardware. On Apple Silicon, if Installer.app spawns the preinstall under a Rosetta-translated `/bin/bash` (Terminal.app's "Open using Rosetta" preference, or `arch -x86_64 sudo installer ...`), `uname -m` returns `x86_64` even though the Mac is M-series. This is documented Apple behavior, not a hardware question.

The kernel-authoritative hardware indicator is `sysctl hw.optional.arm64`, which the kernel sets from the SoC and which does NOT change under Rosetta translation:

| Probe | Apple Silicon (native) | Apple Silicon (Rosetta) | Intel |
|---|---|---|---|
| `uname -m` | `arm64` | **`x86_64`** ← lies | `x86_64` |
| `sysctl -n hw.optional.arm64` | `1` | `1` | `0` (or missing) |
| `sysctl -n sysctl.proc_translated` | `0` | `1` | missing |

Only `hw.optional.arm64` is invariant under translation.

**Fix:**
`installer/macos-pkg/scripts/preinstall.sh::gate_apple_silicon` rewritten to read `sysctl -n hw.optional.arm64` first:

- `=1` → Apple Silicon hardware → accept regardless of `uname -m`. If `sysctl.proc_translated=1`, log a Rosetta-context WARN line so the operator knows the install proceeded under translation.
- `=0` → Intel hardware → `fail 12` with a precise error mentioning the sysctl value.
- sysctl unreadable / missing key → fall back to `uname -m`. Accept only when uname agrees with `arm64`. If uname says `x86_64` here we have NO authoritative arm64 evidence and must `fail 12` rather than risk accepting an Intel Mac.

`sysctl.proc_translated` is logged for diagnostics but does NOT gate — a Rosetta-translated preinstall on Apple Silicon hardware is a valid install; the postinstall and the daemon will run native arm64 once LaunchDaemons fire.

Intel-only support remains explicitly out of scope per `CLAUDE.md` / D-18 / Vision Anchor 2 (Mini IS the product, M-series only).

**Tests:**
- New `tests/installer/test_preinstall_arch_gate.sh` (11 assertions, all green) — 6 static drift guards (bash -n, sysctl reads, `hw_arm64` decision branch retained, `fail 12` rejection path retained, P-015 audit marker present) + 5 functional scenarios using a PATH-shadowed `sysctl`/`uname` mock harness:
  1. Native Apple Silicon (`hw.optional.arm64=1`, `proc_translated=0`, `uname -m=arm64`) → exit 0.
  2. Apple Silicon under Rosetta (`hw.optional.arm64=1`, `proc_translated=1`, `uname -m=x86_64`) → exit 0 — the bug being fixed.
  3. Intel hardware (`hw.optional.arm64=0`, `proc_translated=missing`, `uname -m=x86_64`) → exit 12.
  4. sysctl unreadable + `uname -m=x86_64` → exit 12 (defensive reject).
  5. sysctl unreadable + `uname -m=arm64` → exit 0 (defensive accept only when uname agrees).
- All 10 prior installer test suites still green.

**No build_pkg.sh / payload / notarization-relevant code touched.** Source-tree change is preinstall.sh only. The rebuilt .pkg's payload is byte-identical to 2b48f98 modulo the script-archive bytes for `preinstall`.

**Operator-side diagnostic to confirm hardware (run on the Mac mini):**

```
sysctl -n hw.optional.arm64
sysctl -n sysctl.proc_translated
uname -m
arch
system_profiler SPHardwareDataType | grep -E '^\s*(Model Identifier|Model Name|Chip):'
```

Expected on the M-series Mac mini: `hw.optional.arm64` prints `1`; `sysctl.proc_translated` prints `0` if you ran the command from a native Terminal or `1` if your Terminal is set to "Open using Rosetta"; `Model Identifier` is `MacXX,Y` (M-series) and `Chip` is `Apple Mxx`. If `hw.optional.arm64` returns `1` and the install still fails, the install had a different cause and we'll dig from `/var/log/mining-guardian/install-preinstall.log`.

**Operator commands after merge:**

```
git checkout main
git pull --ff-only origin main
make pkg
```

The rebuilt .pkg replaces `MiningGuardian-1.0.3-2b48f98e6b77.pkg`. Install path on the Mini (no payload-only carryover, no scripts ran on the prior attempt, just retry):

```
sudo rm -f /var/log/mining-guardian/install-preinstall.log
sudo installer -pkg "$HOME/Downloads/MiningGuardian-1.0.3-<new-sha>.pkg" -target /
```

If the operator's Terminal is set to "Open using Rosetta," the preinstall will now still succeed on the M-series Mini (with the diagnostic WARN line in the log). If the operator wants the entire install chain native arm64, uncheck Terminal.app → Get Info → "Open using Rosetta" before installing, OR invoke via `arch -arm64 sudo installer …`.

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
