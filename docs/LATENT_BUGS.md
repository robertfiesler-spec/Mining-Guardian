# Latent Bugs in Mining Guardian

**Created:** April 13, 2026
**Last Updated:** May 6, 2026 (B-19 — `core/mining_guardian.py::_setup_logging` used a relative `Path("logs")` so the first-run baseline scan crashed with `PermissionError: [Errno 13] Permission denied: 'logs'` from the postinstall scripts-sandbox CWD)

This file is the canonical registry of known but unfixed defects in the Mining Guardian
codebase. Every bug here has been **observed or confirmed** during real work — none of
this is theoretical. Each entry must include enough detail that any future session can
pick up the fix without re-deriving the context.

---

## Table of Contents

| ID  | Severity | Subject                                                           | Status     |
|-----|----------|-------------------------------------------------------------------|------------|
| B-1 | Low      | predictor.py NameError (~line 4619)                               | Fixed 2026-04-14 (Phase 1, `88b5b08`) |
| B-2 | Low      | mining_guardian.py NameError in `_escalate_board_issue` (~4040)   | Fixed 2026-04-14 (Phase 1, `88b5b08`) |
| B-3 | High     | `000_bootstrap_field_log_tables.sql` non-partitioned shape trap   | Not fixed  |
| B-4 | High     | `mg_import.insert_raw_json` silently swallows ingestion errors    | Not fixed  |
| B-5 | Medium   | `mg_import.py` raw_json index targets nonexistent column          | Patched out|
| B-6 | Medium   | Retired `Mining-Gaurdian/` typo persists across 13 active docs + 8 service files | Fixed in PR-2 (path strings); 4 narrative references retained as allowed-exception; PR-3 CI lint added 2026-04-29 (PR #72) |
| B-7 | Medium   | Live migrations `002_layer2` + staging not committed to the repo  | 📘 Runbook landed (2026-04-29) — VPS exec pending |
| B-8 | High     | 3 silent NameError bugs (missing imports): `core/models.py` Tuple, `notifiers/approval_interface.py` os, `notifiers/slack_notifier.py` requests | ✅ Fixed 2026-04-29 (pre-install pyflakes sweep) |
| B-9 | Low      | `tests/run_benchmark.py` referenced by `com.miningguardian.scheduled.benchmark.plist` (hourly) + legacy `setup.sh` cron — script does not exist at HEAD | Open — `scheduled_job_launcher.sh` will exit 1 with a clear FATAL until restored. Surfaced 2026-05-04 by D-18 Gap 4 / P-007. |
| B-18 | High    | `installer/macos-pkg/scripts/preinstall.sh::gate_free_disk` checks `df -k /` (sealed APFS system volume) instead of the writable `/Library/Application Support` install target — same root cause as B-1 in `setup.sh`, missed for the .pkg path until v1.0.3 install-day repro on Mac mini | ✅ Fixed 2026-05-06 (this PR) |
| B-20 | High    | `mg_import_tool/sql/seed/001_hardware_model_aliases_tier1.sql` (12,840 row seed) used `ON CONFLICT (alias_normalized) DO NOTHING`, but the canonical `hardware.model_aliases` schema's UNIQUE constraint was changed in N6 (2026-04-27) to `(miner_model_id, alias)`. Apply would hard-fail with `there is no unique or exclusion constraint matching the ON CONFLICT specification` on the very first row. Latent because postinstall never invoked the seed file (B-21). | ✅ Fixed 2026-05-06 (P-018D) — sed-rewrote all 12,840 conflict clauses to `ON CONFLICT (miner_model_id, alias) DO NOTHING`. Header comment block added so a future regenerator does not re-emit the wrong shape. Test: `tests/installer/test_postinstall_alias_seeds.sh §2` greps both the seed and the schema and fails if they ever drift apart again. |
| B-21 | High    | `installer/macos-pkg/scripts/postinstall.sh` never applied `001_hardware_model_aliases_tier1.sql` or `002_mg_family_aliases_tier2.sql`. Importer's two-tier resolver (`mg_import_tool/resolver.py`) found empty `hardware.model_aliases` (catalog) and empty `mg.model_family_aliases` (operational) on every customer Mac mini install. Every drag-and-drop import landed in `mg.unresolved_models` with no `field_log_imports.catalog_slug` stamp. Surfaced by P-018 diagnostic 2026-05-06. | ✅ Fixed 2026-05-06 (P-018D) — new `step_apply_alias_seeds` in postinstall applies Tier-1 to `mining_guardian_catalog` and Tier-2 to `mining_guardian` (operational), idempotently, between the catalog-seed step and the ollama-install step. Reserved fresh exit code 42 to disambiguate this step's failures from 39 (catalog seed) and 41 (customer-info Desktop conf). Seed files moved from `mg_import_tool/sql/seed/` to `intelligence-catalog/seed-data/aliases/` so they survive the D-20 `mg_import*` payload-purge in `build_pkg.sh::step 4h`. Tests: `tests/installer/test_postinstall_alias_seeds.sh` (21 assertions, all green) covers static checks for seed location, conflict-clause shape, postinstall wiring, per-tier DB targeting, exit-code uniqueness, idempotency, and D-20 cleanliness. |
| B-22 | Medium  | `mg_import_tool/mg_import.py::lookup_alias` queries a `mg.model_aliases` table that is created by NO migration and seeded by NO seed file. The function is the legacy fallback used only when `import resolver` fails (i.e. dev environment misconfigured); the live two-tier resolver is `mg_import_tool/resolver.py` and reads `hardware.model_aliases` (Tier-1, catalog DB) + `mg.model_family_aliases` (Tier-2, operational DB) instead. Surfaced by P-018 diagnostic 2026-05-06. | Open (deferred) — fixing requires a behavior change to the importer (deletion of the legacy fallback). Not P-018D scope. The deferral is safe because the legacy fallback only fires when `resolver` import fails, which doesn't happen on the Mini (resolver.py ships with the importer). **Future sessions: when removing the legacy fallback path, also remove the `mg.model_aliases` references at `mg_import.py:778, 792, 804, 829, 2754` and the docstring claim at line 10–11 that the importer reads it.** |
| B-16 | Critical | Migration 007 layer-2 resolver missing `uuid-ossp`/`set_updated_at`/FK target prereqs in operational DB | ✅ Fixed 2026-05-05 (P-023) |
| B-17 | Critical | `intelligence-catalog/seed-data/seed_miner_models.sql` `INSERT INTO hardware.manufacturers` block referenced non-existent columns (`full_name`, `country`, `website`, `notes`); schema uses `legal_name` / `common_name` / `country_of_origin` / `website_url`. Hard-failed catalog-seed step on a fresh `mining_guardian_catalog`. | ✅ Fixed 2026-05-05 (P-024) |
| B-10 | High     | Apple notary rejects `.pkg` whose vendored Python wheels embed Mach-O signed by upstream maintainers (no Developer ID, no secure timestamp, no hardened runtime). Triggered by `750c089f-f0a1-4d40-bf15-e8c295828027` for v1.0.3 first build. | ✅ Fixed 2026-05-04 in PR `mg/v103-p011-wheel-resign` (P-011) — `build_pkg.sh::step_4c_resign_inner_wheels` calls `installer/macos-pkg/scripts/lib/resign_wheel.py` which extracts every `*.whl` in `<payload>/python-wheels/`, codesigns inner Mach-O (`.so`/`.dylib`) with `--options runtime --timestamp`, rewrites `*.dist-info/RECORD` (sha256 + size) so pip still installs the wheel offline, and re-zips. Post-rewrite verify catches RECORD/contents drift. **Future sessions: do NOT vendor wheels with C extensions without re-signing them — the build will silently sign and notarize a .pkg that pip can install but Apple will reject. Run `tests/installer/test_wheel_resign.sh` after touching `payload-requirements.txt`.** |
| B-11 | Critical | macOS PackageKit silently ignores any pkg-build script not named EXACTLY `preinstall` or `postinstall` (no extension). v1.0.3 build `MiningGuardian-1.0.3-a35728dcfc8c.pkg` shipped with `preinstall.sh` / `postinstall.sh` in its Scripts archive: install reported success, payload + receipt landed, scripts NEVER fired. Mac mini ended up with a payload-only install (no `.env`, no venv, no Postgres bootstrap, no LaunchDaemons, no `/etc/mining-guardian/install-receipt.json`). | ✅ Fixed 2026-05-04 in PR `mg/v103-p013-pkg-scripts-naming` (P-013) — `build_pkg.sh::step_4_assemble_payload` step 4d now `mv -f` the staged scripts into extensionless names (`${SCRIPTS_DIR}/preinstall`, `${SCRIPTS_DIR}/postinstall`), chmod 0755, and refuses to proceed if any `*.sh` file remains at the top level of the staging dir (find -maxdepth 1 + `_die 43`). Source files keep the `.sh` extension so editor / shellcheck / `bash -n` keep working. Tests: `tests/installer/test_pkg_scripts_naming.sh` (15 assertions, all green) — covers source presence + executable, the rename live-line, the chmod 0755 line, the find-guard, and a drift check against any future stray `${SCRIPTS_DIR}/(pre\|post)install.sh` reference outside the rename block. **Future sessions: never reference `${SCRIPTS_DIR}/preinstall.sh` or `${SCRIPTS_DIR}/postinstall.sh` outside the rename block — Apple's `man pkgbuild` is explicit that only `preinstall` / `postinstall` (no extension) are honored.** Detection: `pkgutil --expand <pkg> /tmp/x && ls /tmp/x/core.pkg/Scripts/` must show two files named `preinstall` and `postinstall`, not `preinstall.sh` / `postinstall.sh`. The a35728d package on the Mac mini is NOT shippable; cleanup + rebuild + reinstall path lives in the PR description and `docs/RUNBOOK_PKG_REBUILD.md` Block-Cleanup. |
| B-13 | High     | `install_colima.sh::install_colima_runtime` runs `sudo -u <op> colima start ...` and `sudo -u <op> docker ...` without explicit PATH propagation. macOS `sudo -u` strips the inherited PATH and substitutes sudoers' `secure_path` (typically `/usr/bin:/bin:/usr/sbin:/sbin` — note the absence of `/usr/local/bin`), so colima's `os/exec.LookPath("limactl")` and docker's colima-context lookup cannot see the binaries we just installed two lines earlier. Observed live on 2026-05-05 against `MiningGuardian-1.0.3-32ec2dcad973.pkg`: postinstall logged `INFO copied colima + lima (VZ-only, no QEMU) to /usr/local/bin` and `INFO colima will run as miningguardian (home=/Users/miningguardian)`, then `colima start` exited with `lima compatibility error: error checking Lima version: exec: "limactl": executable file not found in $PATH` and postinstall fail 31. Same trap applies to the 10 `sudo -u <op> docker` invocations in `postinstall.sh::step_apply_migrations` and `step_provision_catalog_db_and_seed` once colima is up. | ✅ Fixed 2026-05-05 in PR `mg/p019-colima-limactl-path` (P-019) — added `_op_path` helpers in `install_colima.sh` and `postinstall.sh` returning a PATH that starts with `/usr/local/bin`; every `sudo -u` site that invokes `colima` or `docker` now wraps with `/usr/bin/env PATH="$(_op_path)" HOME="${op_home}"`. New `_verify_limactl` in `install_colima.sh` asserts limactl is at the install destination *before* invoking `colima start`, so a missing limactl produces a clear "limactl not found at /usr/local/bin/limactl" log line rather than the misleading colima `$PATH` error. Sites updated: 5 in `install_colima.sh` (1 colima-start, 4 docker — load/rm/run/exec), 10 in `postinstall.sh` (docker exec/cp). `install_ollama.sh::pull_llm_model` is unchanged because it invokes `/usr/local/bin/ollama` by absolute path and ollama does not shell out to find sibling helpers. Detection: every `sudo -u "${op_user}"` line in `install_colima.sh` is followed within 3 lines by a `/usr/bin/env PATH=` line; `bash tests/installer/test_postinstall_colima_path.sh` exits 0. Tests: new `tests/installer/test_postinstall_colima_path.sh` (21 assertions — `_op_path`/`_verify_limactl` shape, PATH-order, `sudo -u` site wrap audit, runtime: `_op_path` value contains `/usr/local/bin`, `_verify_limactl` rc=0 for present file + non-zero with message for missing, wrapped `env PATH` actually locates a stub limactl in a stripped-PATH env with negative control proving the bug recurs unwrapped, P-019 audit marker, `bash -n`). |
| B-12 | High     | `installer/macos-pkg/scripts/lib/install_colima.sh` and `install_ollama.sh` still resolve the operator account via the legacy `${SUDO_USER:-${USER}}` pattern (8 sites in `install_colima.sh`, 1 in `install_ollama.sh`). P-016 (2026-05-05) replaced this pattern in `postinstall.sh` with the `_resolve_install_user` helper exported as `MG_INSTALL_OPERATOR_USER`, but the helper libs were not updated in that PR. Installer.app exports `USER=root` and does NOT export `SUDO_USER`, so the legacy pattern picks `root` — `install_colima.sh::install_colima_runtime` then assigns `home="/Users/root"` (line 107) and runs `sudo -u root colima start`, which would either fail (`/Users/root` does not exist on a stock customer Mac) or run colima as root (wrong owner for the operator-side `~/.colima` config). The bug has NOT been observed live yet because P-017 (2026-05-05) caused the helpers to exit on the missing-payload check (line 60 of install_colima.sh) BEFORE reaching the user-resolution sites. Once P-017 lands, the next install will hit B-12 unless fixed. | ✅ Fixed 2026-05-05 in PR `mg/p018-helper-user-resolution` (P-018) — both helper libs now define an `_op_user` resolver that prefers the `MG_INSTALL_OPERATOR_USER` value postinstall.sh exports, with three fallback probes (`SUDO_USER` → `stat -f '%Su' /dev/console` → `/Users/*/Desktop/MiningGuardian.conf` scan) and a fail-loud `_die "refusing to run … as root"` when no non-root candidate resolves. Every `chown` / `sudo -u` / `home="…"` site in `install_colima.sh` (3 functions, 8 sites) and `install_ollama.sh` (1 function, 1 site) now derives its user from `_op_user`. Detection: `grep -nE 'SUDO_USER:-\$\{USER\}' installer/macos-pkg/scripts/lib/*.sh \| sed -E 's/^[0-9]+://' \| grep -vE '^[[:space:]]*#'` returns nothing (only doc comments cite the legacy pattern). Tests: new `tests/installer/test_postinstall_helper_user_resolver.sh` (26 assertions — pattern eradication, four-probe shape, root-refusal guards, runtime resolver behavior with mocked `/dev/console` + fake `/Users` tree, P-018 audit marker). All adjacent installer suites still green: 12 + 12 + 9 + 17 + 11 + 76 + 24 + 26 + 115 + 50. |
| B-18 | High     | `installer/macos-pkg/scripts/preinstall.sh::gate_free_disk` reads `df -k /` to enforce the 20 GB free-disk floor. Modern macOS (Catalina+) splits the boot volume into a SEALED read-only system volume mounted at `/` and a writable Data volume mounted at `/System/Volumes/Data`; `df -k /` reports the system volume's free slack, which is unrelated to install capacity. Same root cause as B-1 (closed in v1.0.2 for `scripts/setup.sh`) but the .pkg path's preinstall script was missed. Observed live on 2026-05-04 against `MiningGuardian-1.0.3` on a new Mac mini: Finder showed ~167 GB free, `df -g /` reported ~22 GB available, preinstall logged `FATAL (14) only 19 GB free on /; require 20 GB+` and Installer.app aborted. | ✅ Fixed 2026-05-06 in PR (this branch) — `gate_free_disk` now targets the writable install location `/Library/Application Support` (parent of `MG_INSTALL_ROOT`). Source-of-truth order matches the v1.0.2 setup.sh fix: (1) `diskutil info <target>` → "Container Free Space" byte count (authoritative APFS container free), (2) `df -k <target>` (writable target, NOT `/`), (3) `df -k /System/Volumes/Data` (last-ditch fallback). The diagnostic log line records all four probes (`df /`, `df <target>`, `df /System/Volumes/Data`, `diskutil container free for <target>`) so a future regression is obvious from one grep. The failure message embeds the misleading `df /` value so confused operators can match the diagnostic to what they see in Terminal. New `installer/macos-pkg/scripts/tests/test_preinstall_disk_gate.sh` (7 assertions — v1.0.3 regression scenario, low-APFS-free fail, diskutil-unavailable df fallback, data-volume last-ditch fallback, all-probes-fail diagnostic shape, log shape, regression guard against future code reintroducing `df /` as the gate's single source of truth) all green. Detection (operator-side, after install): `grep gate_free_disk /var/log/mining-guardian/install-preinstall.log` shows the four-probe line and an `OK` line whose source is `diskutil container free space for /Library/Application Support`. **Future sessions: never gate disk space on `df /` on macOS — the sealed system volume is not where the install lives. Mirror the diskutil-first / df-target / df-data fallback chain.** |
| B-14 | Critical | `build_pkg.sh::step_4b_codesign_inner_binaries` re-signs every vendored Mach-O with Developer ID Application + hardened runtime + secure timestamp **without passing `--entitlements`**, which strips the upstream `com.apple.security.virtualization` entitlement that lima-vm/lima signs into `limactl` and `lima-driver-vz` at build time. On Apple Silicon, `colima start --vm-type vz` then progresses through Lima version handshake and disk-image conversion, but the VZ driver subprocess fails with `Error Domain=VZErrorDomain Code=2 "Invalid virtual machine configuration. The process doesn't have the com.apple.security.virtualization entitlement."` Observed live on 2026-05-05 against `MiningGuardian-1.0.3-47efd658f16a.pkg`: ha.stderr.log captured the exact entitlement rejection; postinstall log reaches `[ollama] INFO limactl present at /usr/local/bin/limactl`, then `Starting VZ...` followed by `fatal: error starting vm: exit status 1`. Apple notary does NOT catch this — the entitlement is legal to omit; failure surfaces only at install-time `colima start`. | ✅ Fixed 2026-05-05 in PR `mg/p020-p021-vz-entitlement-codesign` (P-021) — added `installer/macos-pkg/scripts/lib/vz.entitlements` (mirrors upstream `lima-vm/lima/vz.entitlements`, declares `com.apple.security.virtualization` + the two `network.{server,client}` keys lima ships with). `step_4b_codesign_inner_binaries` defines a `vz_binary_names` set (`limactl`, `lima-driver-vz`, `lima`); for any loose Mach-O whose basename matches the set, the codesign call now passes `--entitlements "$vz_entitlements"` alongside `--options runtime --timestamp --sign "$APPLE_DEV_ID_APPLICATION"`. Non-VZ binaries (colima, docker, qemu-img) keep the previous no-entitlements path — over-broad entitlement application is itself a notarization risk. Build-time verify-after-sign greps `codesign -d --entitlements - <bin>` output for `com.apple.security.virtualization` and exits 44 if absent on any VZ binary, so the build hard-fails rather than burning a notarization round-trip on a .pkg whose VZ binaries are missing the entitlement. Tests: new `tests/installer/test_build_pkg_vz_entitlement.sh` (26 assertions, all green) — plist shape + parse, entitlement-key declaration, build_pkg.sh wiring (entitlements path, vz_binary_names list, --entitlements pass, verify-after-sign, mandatory limactl-presence), runtime smoke test of the limactl source-location resolver in 3 scenarios (Lima 1.x layout, Lima 2.x layout, both-missing → non-zero), audit markers, `bash -n`. Detection (operator-side, after install): `codesign -d --entitlements - /usr/local/bin/limactl 2>/dev/null \| grep -q com.apple.security.virtualization`. |
| B-15 | Medium   | `install_colima.sh::install_colima_runtime` resolved limactl from a single hard-coded path (`${src}/limactl`) for Lima 1.x layouts. Lima 2.x ships `limactl` under `${src}/bin/limactl` instead — so a vendor dir built from a Lima 2.x release would `install` exit non-zero (set -e) without a clear log line. The bug has not yet bitten because the customer build vendor dir happened to use Lima 1.x layout, but as upstream Colima/Lima updates roll forward into the operator's `~/MiningGuardian-vendor/`, the next vendor refresh would silently regress. | ✅ Fixed 2026-05-05 in PR `mg/p020-p021-vz-entitlement-codesign` (P-020) — `install_colima_runtime` now walks both `${src}/limactl` and `${src}/bin/limactl`, picks whichever exists, logs the source path on success, and exits with a clear `_die "vendored limactl not found at ${src}/limactl or ${src}/bin/limactl (P-020)"` when neither is present. Build-side belt-and-suspenders: `step_4b_codesign_inner_binaries` asserts `find -type f -name 'limactl'` returns at least one match anywhere under runtime/, so the build hard-fails (exit 44) before signing/notarization if the vendor layout has hidden limactl elsewhere entirely. Tests: covered by the same `tests/installer/test_build_pkg_vz_entitlement.sh` runtime block (3 scenarios — Lima 1.x present, Lima 2.x present, neither). |
| B-19 | High     | `core/mining_guardian.py::_setup_logging` used a relative `log_dir = Path("logs")`. The hourly scanner runs from the launchd `WorkingDirectory` so the relative path normally lands inside the install root, but `postinstall.sh::step_baseline_scan` invoked the same entry point as `sudo -u miningguardian python …/mining_guardian.py --once` from postinstall's CWD — the Installer.app scripts sandbox under `/tmp/PKInstallSandbox.<rand>/Scripts/...`. Without a `cd` and without `MG_INSTALL_ROOT`, `Path("logs")` resolved to `<sandbox>/logs` which the unprivileged `miningguardian` user could not create, and the first-run baseline scan crashed before writing any data. Round-9b of the v1.0.3 customer Mac mini install (`MiningGuardian-1.0.3-2a3de50c4af2.pkg`, main `2a3de50`) hit this on 2026-05-06 with `PermissionError: [Errno 13] Permission denied: 'logs'` at `core/mining_guardian.py` line 63. | ✅ Fixed 2026-05-06 in PR `mg/p028-absolute-logs-path` (P-028) — new `_resolve_log_dir()` helper resolves the logs directory in three tiers: (1) `MG_LOG_DIR` env var (explicit override), (2) `MG_INSTALL_ROOT` env var (canonical install root → `<root>/logs`), (3) the parent of `core/mining_guardian.py` itself (i.e. the repo / install root inferred from the file location). `_setup_logging()` calls the helper and uses `mkdir(parents=True, exist_ok=True)`. `postinstall.sh::step_baseline_scan` now `cd`s into `${MG_INSTALL_ROOT}` AND passes `MG_INSTALL_ROOT=…` via `/usr/bin/env` into the scanner subprocess (belt and suspenders). Every launcher wrapper (10 services + the generic `scheduled_job_launcher.sh`) now `export MG_INSTALL_ROOT="${INSTALL_ROOT}"` before `exec`'ing python, so any future caller that drops the `cd` still picks the correct logs dir. Tests: new `tests/installer/test_absolute_logs_path.sh` (20 assertions, all green) — `_resolve_log_dir` defined, `_setup_logging` calls it, no relative `Path("logs")` literal anywhere under `core/` (with negative control proving the test catches the regression), `step_baseline_scan` exports MG_INSTALL_ROOT + cds, every launcher wrapper exports MG_INSTALL_ROOT, runtime test of the resolver in three modes (MG_INSTALL_ROOT honored, fallback to repo root, MG_LOG_DIR override), P-028 audit markers in both `core/mining_guardian.py` and `installer/macos-pkg/scripts/postinstall.sh`. **Future sessions: never use a relative `Path("logs")` or `"logs/"` for any file written by Mining Guardian. Always anchor on `MG_INSTALL_ROOT` (env) or the source file's resolved parent.** |
| B-17 | Critical | `intelligence-catalog/seed-data/seed_miner_models.sql` (committed 2026-04-11 by `compile_all_miners.py`, before catalog schema N6 / 2026-04-27 settled the canonical `hardware.manufacturers` column names) opened its BEGIN transaction with `INSERT INTO hardware.manufacturers (brand, full_name, country, website, notes) VALUES …` for 11 brands. The schema (`intelligence-catalog/seed-data/intelligence_catalog_schema.sql` lines 445–473) has `legal_name` (NOT NULL), `common_name` (NOT NULL), `country_of_origin`, `website_url`, `metadata JSONB` — not `full_name` / `country` / `website` / `notes`. `deploy_schema.sql` (which postinstall runs immediately before the seed file) already seeds **all 17 manufacturers** (lines 92–116) using the correct column names, so the seed file's block was dead duplicate code that masked the schema/seed drift until the v1.0.3 install. Observed live on 2026-05-05 against `MiningGuardian-1.0.3-dd482af746ad.pkg` (built from main `dd482af` after P-023 cleared the migration-007 prereq bug). The install progressed past every prior gate (operational migrations 001 → 006 → 006a → 007 succeeded, `mining_guardian_catalog` created, `deploy_schema.sql` applied — log printed `Schema deployment complete \| sources_count 23 \| manufacturers_count 17`), then `seed_miner_models.sql` line 39 hard-failed with `ERROR: column "full_name" of relation "manufacturers" does not exist / [postinstall] FATAL (39) seed_miner_models.sql apply failed against mining_guardian_catalog`. | ✅ Fixed 2026-05-05 in PR `mg/p024-catalog-seed-manufacturers-schema` (P-024) — removed the broken `INSERT INTO hardware.manufacturers` block (lines 25–39) from `seed_miner_models.sql`; the file now contains miner_models INSERTs only (320 rows preserved, BEGIN/COMMIT envelope unchanged). Manufacturers are owned exclusively by `deploy_schema.sql`. Source generator `intelligence-catalog/seed-data/compile_all_miners.py::write_sql` updated in the same change so future `python compile_all_miners.py` runs do not re-emit the broken block. **No `build_pkg.sh`, postinstall, payload-rsync, or notarization-relevant change** — pure SQL/Python source fix; the catalog-seed step in postinstall is unchanged. Idempotency on re-install is preserved (the removed block was already `ON CONFLICT (brand) DO NOTHING` and `deploy_schema.sql` owns the rows). Tests: new `tests/installer/test_catalog_seed_schema_compat.sh` (17 assertions, all green) — file presence, regression check that `seed_miner_models.sql` no longer contains an `INSERT INTO hardware.manufacturers`, **column-existence walk that extracts every column referenced by every `INSERT INTO hardware.<table> (...)` in the seed file (5440 column references across 320 INSERT blocks) and verifies each exists in the catalog schema bundle (1232 unique column identifiers across `intelligence_catalog_schema.sql` + v2 + v3 + `staging_schema.sql`)** — this catches schema/seed column drift on any catalog table, not just `hardware.manufacturers`; named regression assertions for the four broken column names (`full_name`/`country`/`website`/`notes`) and the four canonical names (`legal_name`/`common_name`/`country_of_origin`/`website_url`); brand-coverage check that `deploy_schema.sql` seeds every brand referenced by `seed_miner_models.sql` (14 brands). All adjacent installer suites still green: `test_postinstall_catalog_seed.sh` 24/24 (seed row count + apply ordering), `test_postinstall_env_handoff.sh`, `test_migration_007_prereqs.sh`. Detection (operator-side, after install): `docker exec mining-guardian-db psql -U mg -d mining_guardian_catalog -tAc "SELECT count(*) FROM hardware.miner_models;"` returns 320 and `… "SELECT count(*) FROM hardware.manufacturers;"` returns 17. **Future sessions: never add an `INSERT INTO hardware.manufacturers` to `seed_miner_models.sql`. Manufacturer rows live in `deploy_schema.sql` exclusively. If a new brand is needed, add it to the `deploy_schema.sql` INSERT (using the canonical `legal_name`/`common_name`/`country_of_origin`/`website_url` columns) AND extend the `public.manufacturer_brand` enum. The new regression test §2/§4 will catch any attempt to put manufacturer inserts back into the seed file.** |
| B-16 | Critical | `migrations/007_layer2_resolver.sql` (relocated 2026-05-04 in P-004 from `mg_import_tool/sql/migrations/002_layer2_and_learning_foundation.sql` as part of the D-20 importer-payload reconciliation) calls `uuid_generate_v4()`, attaches `EXECUTE FUNCTION set_updated_at()` triggers, and declares FKs into `hardware.miner_models(id)` / `pool.mining_pools(id)`. The importer-side original ran against the catalog DB `mining_guardian_catalog` where `intelligence-catalog/seed-data/intelligence_catalog_schema.sql` provides the `uuid-ossp` extension, the trigger function, and the FK target tables. The operational DB `mining_guardian` (where `step_apply_migrations` actually applies these migrations) has none of those prerequisites — it's a separate database from the catalog DB on the same Colima container. P-004 relocated the SQL but not the prereq context, so on a fresh customer Mac mini install 007's first `uuid_generate_v4()` call hard-fails with `ERROR: function uuid_generate_v4() does not exist / [postinstall] FATAL (32) migration 007_layer2_resolver.sql failed`. Observed live on 2026-05-05 against `MiningGuardian-1.0.3-b66b86440400.pkg` (built from main `b66b864` after P-022 cleared the env-handoff bug). The byte-identical contract from P-004 (`tests/installer/test_d20_importer_payload_reconciliation.sh §8`) prevents patching 006 or 007 in place. | ✅ Fixed 2026-05-05 in PR `mg/p023-migration-007-layer2-prereqs` (P-023) — new `migrations/006a_layer2_prereqs.sql` runs lexically between 006 and 007 (no rename of either; byte-identical contract preserved) and bootstraps exactly what 007 needs in the operational DB: (1) `CREATE EXTENSION IF NOT EXISTS "uuid-ossp"` + `pg_trgm`, (2) `CREATE OR REPLACE FUNCTION public.set_updated_at()` mirroring the catalog DB definition, (3) stub `hardware.miner_models(id UUID PRIMARY KEY)` + `pool.mining_pools(id UUID PRIMARY KEY)` so 007's FK declarations resolve. Stubs are intentionally minimal (id-only) — the operational DB never stores authoritative catalog rows; the FK columns in `mg.*` tables are populated by application code with UUID pointers into the catalog DB and are nullable, so the FK constraint is satisfied trivially. Idempotent (`CREATE EXTENSION IF NOT EXISTS` / `CREATE OR REPLACE FUNCTION` / `CREATE SCHEMA IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS`); verified clean re-apply on Postgres 17 against a fresh DB and against a DB that already has a real catalog-shape `hardware.miner_models` (no clobber, seeded rows preserved). No `build_pkg.sh`, payload, or notarization-relevant code touched — pure new SQL file in `migrations/`, picked up automatically by `step_apply_migrations`'s `*.sql` glob. Tests: new `tests/installer/test_migration_007_prereqs.sh` (16 assertions, all green) — file presence + balanced BEGIN/COMMIT, prereq-coverage walks (every `uuid_generate_v4()` caller is preceded by a uuid-ossp creator; every `set_updated_at()` user is preceded by a definer; every FK to `hardware.miner_models`/`pool.mining_pools` is preceded by a creator), P-023 audit marker, `step_apply_migrations` glob check, RUNTIME (opt-in via `MG_RUN_PG_TESTS=1`) end-to-end fresh-DB apply with idempotency re-apply check. All adjacent installer suites still green: `test_d20_importer_payload_reconciliation` 32/32 (006/007 still byte-identical to importer-side originals), `test_postinstall_env_handoff` 38/38, `test_postinstall_payload_path` 12/12, `test_postinstall_catalog_seed` 24/24, `test_pkg_scripts_naming` 17/17. Detection (operator-side, after install): `docker exec mining-guardian-db psql -U mg -d mining_guardian -c "SELECT extname FROM pg_extension WHERE extname='uuid-ossp';"` returns one row; `SELECT to_regclass('hardware.miner_models'), to_regclass('pool.mining_pools');` returns two non-NULL values. **Future sessions: never relocate a migration from `mg_import_tool/sql/migrations/` into the canonical operational chain without verifying it is self-contained against `mining_guardian` (operational DB) prereqs — the importer's catalog DB has very different defaults.** |

---

## Severity Definitions

- **High** — Active defect with confirmed evidence; can corrupt data, hide failures,
  or block a future operator from running a script as-documented. Must be fixed before
  the May-5-class install gate or explicitly waived.
- **Medium** — Confirmed defect, but the workaround in place is stable. Will bite a
  future operator who reads the docs/code literally and doesn't know about the patch.
- **Low** — Code-review finding only; never observed at runtime.

---

# High-Severity Bugs

## B-3 — `000_bootstrap_field_log_tables.sql` migration trap

**Severity:** High
**Status:** Fixed 2026-04-28 in PR (this commit). The `knowledge.field_log_raw_json` block in `000_bootstrap_field_log_tables.sql` was rebased onto the canonical PARTITIONED shape introduced by `002_layer2_and_learning_foundation.sql`. Verified end-to-end against a Postgres 17 instance: (a) fresh run of 000 produces a structural diff of zero against the same table built by 002 alone, (b) re-running 000 is idempotent (NOTICE skips, no errors), (c) 002 layered on top of 000 is a clean no-op for the raw_json section.
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/sql/migrations/000_bootstrap_field_log_tables.sql`

### Description

The `000_bootstrap_field_log_tables.sql` migration creates `field_log_imports` and
`field_log_raw_json` as **non-partitioned** tables, and includes a `file_path_in_archive`
column that does not exist on the live partitioned variant currently running in the
`mining-guardian-db` Postgres 16 container.

Applying this migration on top of the live DB would either (a) fail outright on the
shape mismatch, or (b) — worse — succeed against an empty schema and produce a
different table layout than the one production has been running on for weeks. Either
outcome is data-corruption-grade for any future operator who runs the migrations
in numerical order without reading the addendum.

### Evidence

- During the 2026-04-27 live-DB migration session, the operator deliberately skipped
  `000_bootstrap_field_log_tables.sql` and only applied `002_layer2` plus the staging
  migration. See `docs/SESSION_LOG_2026-04-27.md` addendum #3.
- A diff between the migration's `CREATE TABLE` and the live `\d field_log_imports`
  output confirms the partitioning clause and the `file_path_in_archive` column are
  the disagreement points.

### Reproduction

Any future fresh-install path that runs `mg_import_tool/sql/migrations/*.sql` in
order will trip this. The current "live DB" was built by applying `001_initial_schema.sql`
plus the partition-aware schema delivered manually months ago, so `000_*` was never
exercised in production.

### Fix Applied

1. ✅ Rebased `000_bootstrap_field_log_tables.sql` onto the partitioned shape the
   live DB uses: dropped `file_path_in_archive` and `raw_content`, added
   `PARTITION BY RANGE (ingested_at)` with quarterly children for 2026-Q2 →
   2027-Q1, switched primary key to `(id, ingested_at)`, and replaced the
   `(archive_filename, file_path_in_archive)` unique constraint with the three
   non-unique indexes that 002 already declares (`idx_raw_json_entity`,
   `idx_raw_json_archive`, `idx_raw_json_sha`).
2. ✅ Idempotent: every CREATE in the rebased block uses `IF NOT EXISTS`
   (table, partitions, indexes), so re-running the migration on a DB that
   already has 002 applied is a no-op. Verified via two consecutive runs
   against a fresh Postgres 17 instance — second run produced only NOTICE
   skips, no errors.
3. ⏳ Pending follow-up (NOT in this PR): regression test in
   `tests/test_migrations.py` that diffs post-migration schema vs canonical.
   The test infrastructure does not yet exist; this is tracked separately.
4. ✅ This entry updated with the rebase status above.

**Open follow-up:** the runtime DDL bootstrap inside `mg_import.py` (lines
~929-969 and ~1287-1296) still creates the OLD non-partitioned shape. That
write path, plus the silent-swallow in `insert_raw_json`, is tracked as
B-4 / B-5. Fixing the migration file unblocks them but does not in itself
resolve the runtime divergence.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- `docs/DECISIONS.md` D-1 (Postgres-as-canonical)
- B-4, B-5 below — coupled runtime issues in `mg_import.py`

---

## B-4 — `mg_import.insert_raw_json` silently swallows ingestion errors

**Severity:** High
**Status:** Fixed 2026-04-28 in PR (this commit). `insert_raw_json()` was rewritten to (a) write to the canonical 7-column partitioned `knowledge.field_log_raw_json` table — `(entity_label, archive_filename, source_file, parser, raw_payload, sha256, ingested_at)` — instead of the legacy `(archive_filename, file_path_in_archive, raw_content)` triple, and (b) replace the silent `except Exception: pass` with `log.error(..., exc_info=True); raise` so failures surface immediately. Walker `_insert_archive_raw_json_files()` was rewritten to take `shape` + `archive_meta`, return per-call stats `{scanned, inserted, skipped, failed}`, log every per-file failure at ERROR, and have the call site log loudly when `stats.failed > 0`. The archive-level blob now uses `parser='<shape>:archive_meta'` with the archive's own sha256.

**Backfill of 124 rows missing from the 2026-04-27 import:** out of scope for this PR. Tracked as a Bucket-1 follow-up — needs the on-disk archives and a one-shot script that walks them through the new canonical writer.

**Runtime invariant assertion** (`raw_json_count >= imports_count * 0.95` at end of `run_full_import.py`): ✅ **Done 2026-04-29** in PR #71 (Bucket 5). The driver now ends every non-dry-run import with a read-only count check that compares `knowledge.field_log_raw_json` against `knowledge.field_log_imports` and exits with code 3 (distinct from the existing code 1 = per-archive failure) if `raw_json_count < imports_count * --raw-json-min-ratio` (default 0.95). Configurable via `--raw-json-min-ratio` and `--no-raw-json-check`. The check is read-only and tolerant of a missing/unreachable DB — a transient error logs a warning and lets the import succeed, matching the existing pattern in `_load_existing_filenames`. See `_raw_json_invariant_check()` in `mg_import_tool/tools/run_full_import.py`.

**Verification (re-run any time):**

```bash
# The invariant check function is present in the driver:
grep -n '_raw_json_invariant_check\|raw_json_min_ratio\|B-4 invariant\|B-4 INVARIANT VIOLATION' \
  mg_import_tool/tools/run_full_import.py
# Should return: function definition (~line 291), CLI flags (~250-260), exit-code branch (~570),
#                summary line (~565), and the OK/VIOLATION log lines (~350-359).
```
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/mg_import.py` — `insert_raw_json()` function

### Description

`insert_raw_json()` opens an autocommit-isolated connection and wraps the entire
insert in a broad `try / except Exception: pass`. Any failure — schema mismatch,
unique-constraint violation, JSON type error, network blip, anything — is swallowed
silently. The outer caller never sees the failure, no log line is produced, and the
import driver happily reports "all archives processed" while the raw-JSON table has
been left starved.

### Evidence

After the 2026-04-27 live import of 127 archives:

```
mining_guardian=# SELECT count(*) FROM field_log_raw_json;
 count
-------
     3

mining_guardian=# SELECT count(*) FROM field_log_imports;
 count
-------
   127
```

127 imports succeeded. 124 raw-JSON inserts failed silently. The discrepancy was only
caught because the operator ran the post-import baseline diff (Block H of the runbook).
With no diff, the silent loss would have shipped to production.

### Reproduction

Any archive whose top-level JSON shape doesn't match the (currently undocumented)
constraints on `field_log_raw_json` will trigger the swallow. The exact failing shape
is not yet known because, by definition, the exception is discarded before it can
be logged.

### Fix Plan

1. Replace the bare `except Exception: pass` with `except Exception as e: logger.error(...);
   raise` (or, if the autocommit isolation is intentional, log + re-raise inside the
   connection's `__exit__`).
2. Add a unit test that injects a deliberately malformed JSON shape and asserts the
   exception propagates.
3. Backfill the 124 missing rows from the on-disk archives once root cause is known.
4. Add a runtime invariant check at the end of `run_full_import.py`:
   `assert raw_json_count >= imports_count * 0.95` (or similar threshold) and fail
   loudly if violated.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- B-5 below — the index patch is part of why raw-JSON inserts were failing

---

# Medium-Severity Bugs

## B-5 — `mg_import.py` raw_json index targets nonexistent column

**Severity:** Medium
**Status:** Fixed 2026-04-28 in PR (this commit). The runtime bootstrap `CREATE TABLE knowledge.field_log_raw_json` inside `mg_import.py` was rebased onto the canonical PARTITIONED shape (8 columns, partition by range on `ingested_at`, quarterly children for 2026 q2/q3/q4 + 2027 q1, PK `(id, ingested_at)`, three non-unique indexes `idx_raw_json_entity` / `idx_raw_json_archive` / `idx_raw_json_sha`) — mirrors the rebased `000_bootstrap_field_log_tables.sql` from the B-3 fix. The patched-out unique-index comment block (the `2026-04-27` marker plus the commented-out `CREATE UNIQUE INDEX ... (archive_filename, file_path_in_archive)`) was removed entirely: the canonical shape has no `file_path_in_archive` column, and the three non-unique indexes provide the lookup paths we need. `insert_raw_json()` no longer uses `ON CONFLICT`. All statements are `IF NOT EXISTS`, so the live DB is unaffected.
**Discovered:** 2026-04-27 (PR #25 addendum #3)
**Location:** `mg_import_tool/mg_import.py` lines 1315-1316 (historical; now removed)

### Description

The `mg_import.py` driver attempted to `CREATE INDEX ... ON field_log_raw_json
(raw_json_jsonb_field)` against the live partitioned table, but the live partitioned
variant does **not** have a `raw_json_jsonb_field` column — that column only exists
on the non-partitioned shape from the (broken) `000_bootstrap_field_log_tables.sql`
migration (see B-3).

The lines were commented out during the 2026-04-27 import to unblock the run, with
the marker:

```python
# 2026-04-27: partitioned raw_json table — see docs/SESSION_LOG addendum #3
```

The patch is stable but it's a surface-level fix. The *real* fix is to converge
the partitioned-vs-non-partitioned schema disagreement (which is B-3), then restore
the index against the correct column name.

### Evidence

`git blame` on `mg_import.py:1315-1316` shows the comment-out commit on the
`mg/pr25-bulk-import-tools` branch, merged via PR #25.

### Reproduction

Any operator who reverts the comment-out without first fixing B-3 will hit:
```
psycopg2.errors.UndefinedColumn: column "raw_json_jsonb_field" does not exist
```

### Fix Plan

B-3 root cause was fixed 2026-04-28 (the migration file is now correct), but
the runtime DDL inside `mg_import.py` is a separate write path that ALSO
needs to converge before this index can be restored:

1. Update the runtime bootstrap CREATE TABLE in `mg_import.py` (~lines 1287-1296)
   to match the canonical partitioned shape — same columns, partition key,
   and quarterly partitions as the rebased 000 migration. Until this is done,
   `mg_import.py` running against a fresh DB will create the wrong shape and
   then 002 will fail with an `ALREADY EXISTS` mismatch.
2. Update `insert_raw_json()` (~line 929) to write to the canonical column set
   (`entity_label, archive_filename, source_file, parser, raw_payload, sha256,
   ingested_at`) instead of the legacy `(archive_filename, file_path_in_archive,
   raw_content)` triple. This is the same code path that B-4 (silent swallow)
   touches — fix both together.
3. Once the writer is canonical, replace the patched-out index (lines
   1315-1316) with the appropriate index against the partitioned shape —
   most likely `(archive_filename, sha256)` rather than
   `(archive_filename, file_path_in_archive)`. Use `CREATE INDEX CONCURRENTLY`
   if running against a populated table.
4. Remove the `# 2026-04-27` marker comment.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- B-3 (root cause — fixed 2026-04-28 in this PR)
- B-4 (silent swallow — same `mg_import.py` write path)
- PR #25 (squashed as `6f0b5a2`)

---

## B-6 — Retired `Mining-Gaurdian/` typo persists across 13 active docs + 8 service files

**Severity:** Medium
**Status:** Fixed (path strings) in PR-2 (`docs/b6-typo-cleanup`); 4 files retain the typo as narrative / historical reference and are added to the allowed-exception list. Closed.
**Discovered:** 2026-04-28 (this session, while reviewing post-rename cleanup)
**Original scope:** `docs/CRON_SCHEDULE.md` (single file)
**Expanded scope (verified 2026-04-28 on `main` @ `9ff9925`):** 8 `deploy/*.service` files + 13 currently-active docs. Full breakdown below.
**Fix scope (PR-2, 2026-04-28):** 65 path-string hits across 17 files were replaced with `Mining-Guardian`. 8 hits across 4 files were retained as historical / warning references (see updated allowed-exception table).

> **2026-04-29 PM context:** The Hostinger VPS (srv1549463 / 187.124.247.182) is decommissioned for Mining Guardian as of the 2026-04-30 Mac Mini install. References to "freshly-provisioned VPS" in this bug entry are historical context — the VPS was the deployment target when B-6 was discovered. The Mac Mini is now the operational host. The `deploy/*.service` systemd units remain in the repo as historical reference; the Mac Mini uses launchd `.plist` files instead.

### Description

On Sunday 2026-04-26, the VPS directory was renamed from `/root/Mining-Gaurdian/`
(typo, missing the `r`) to `/root/Mining-Guardian/` (correct spelling) as part of
PR #1. The cron jobs documented in `docs/CRON_SCHEDULE.md` still reference the old
typoed path, and so do the rest of the documents and systemd unit files listed
below. Any operator who copies these onto a freshly-provisioned VPS will end up
writing to a directory that does not exist — silent failure, since cron's stderr
is mailed to root and routinely ignored, and a `systemd` unit with a bad
`WorkingDirectory` will refuse to start with a confusing error.

The actual cron jobs and systemd units running on the live Hostinger VPS
(187.124.247.182) were updated in place during the 2026-04-26 rename, so
production is fine. The risk is purely "future re-install copies stale doc /
stale unit file."

When this entry was first written (PR #30, 2026-04-28 morning) the scope was
recorded as `docs/CRON_SCHEDULE.md` only. A follow-up audit later that morning
(during preparation of `docs/REMAINING_WORK_2026-04-28.md`, PR #34) re-grepped
the full repo and found the typo persists in many more places. This entry is
the corrected record of that scope.

### Evidence — full repo grep on `main` @ `9ff9925` (2026-04-28)

Command: `grep -rln 'Mining-Gaurdian' . --exclude-dir=.git`

#### To-fix scope — currently-active files (21 files, 73 hits)

**`deploy/*.service` — 8 files, 29 hits.** Every systemd unit on the VPS
references the typoed path. These get installed on every fresh host.

| File | Hits |
|---|---|
| `deploy/approval-api.service` | 4 |
| `deploy/dashboard-api.service` | 4 |
| `deploy/intelligence-report.service` | 3 |
| `deploy/mining-guardian-alerts.service` | 3 |
| `deploy/mining-guardian.service` | 4 |
| `deploy/overnight-automation.service` | 4 |
| `deploy/slack-commands.service` | 3 |
| `deploy/slack-listener.service` | 4 |

**Repo-root docs — 4 files, 17 hits.** These are the first docs anyone reads.

| File | Hits |
|---|---|
| `CLAUDE.md` | 5 |
| `DEPLOYMENT_CHECKLIST.md` | 6 |
| `README.md` | 1 |
| `REPAIR_LOG.md` | 5 |

**`docs/` active references — 9 files, 27 hits.**

| File | Hits |
|---|---|
| `docs/CRON_SCHEDULE.md` | 10 |
| `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` | 4 |
| `docs/DAILY_DEEP_DIVE_DESIGN.md` | 3 |
| `docs/DIRECT_LOG_COLLECTION.md` | 3 |
| `docs/MORNING_KICKOFF_PROMPT.md` | 2 |
| `docs/TESTING.md` | 2 |
| `docs/SECURITY.md` | 1 |
| `docs/LOG_COLLECTION_ARCHITECTURE.md` | 1 |
| `docs/MG_UNIFIED_TODO_LIST.md` | 1 |

#### Allowed-exception scope — references the typo as data, do NOT replace

Updated 2026-04-28 after PR-2. The four files in the lower group below were
originally on the to-fix list; case-by-case review during PR-2 found that
each one quotes the typo as historical / warning context where replacing it
would destroy meaning. They are now allowed-exceptions.

| File | Hits | Why allowed |
|---|---|---|
| `docs/LATENT_BUGS.md` | 8 | This entry — quotes the typo string as the bug's identity |
| `docs/REMAINING_WORK_2026-04-28.md` | 2 | Bucket 2 references the typo as the bug name (PR #34) |
| `archive/installer-build-20260428` (git tag) | n/a | Frozen by design, not in working tree |
| `CLAUDE.md` | 5 | Failure-mode example (L193), do-not-use warnings about old VPS path (L379, L496), Repo Rename History entry (L514–515) |
| `README.md` | 1 | "Original 2024 repo name had an intentional typo `Mining-Gaurdian`” — historical context inside backticks (L503) |
| `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` | 1 | "Known gotchas" entry that explicitly names the historical typo path so a future operator can recognize it (L237) |
| `docs/MG_UNIFIED_TODO_LIST.md` | 1 | Rename log row — "Rename `Mining-Gaurdian` → `Mining-Guardian` (289 typos)" (L31) |

A CI lint (Optional PR-3) must whitelist all seven files above plus the
`archive/installer-build-20260428` git tag.

#### Leave-as-historical-record scope — preserved verbatim per the
"comprehensive + over-document always" lock

These are dated handoff / log files that capture what was true on the day they
were written. Editing them would falsify the historical record.

**2026-04-29 update (PR #91 doc sweep):** the `docs/SESSION_LOG_*`,
`docs/HANDOFF_*`, `docs/SESSION_HANDOFF_*`, and `docs/DB_STATE_*` files
were relocated into `docs/archive/2026-04/` as part of the install-eve doc
sweep. The lint allow-list now uses a `docs/archive/` directory prefix to
cover all of them in one entry. `docs/RESUME_HERE_2026_04_08_EVENING.md`
was removed entirely during the same sweep (its content was superseded by
the Mac Mini runbook), so it no longer needs an allow-list entry.

| File | Hits |
|---|---|
| `NEXT_SESSION.md` (post-banner body, banner-superseded by PR #31) | 5 |
| `docs/archive/2026-04/SESSION_LOG_2026-04-09.md` | 2 |
| `docs/archive/2026-04/SESSION_LOG_2026-04-16.md` | 1 |
| `docs/SESSION_2026-04-13_S21_TEST_AND_FIXES.md` | 6 |
| `docs/archive/2026-04/SESSION_HANDOFF_2026-04-24.md` | 2 |
| `docs/archive/2026-04/HANDOFF_2026_04_09_MIDMORNING.md` | 7 |
| `docs/DEMO_DAY_HANDOFF_2026_04_08.md` | 2 |
| `docs/archive/2026-04/DB_STATE_2026-04-22.md` | 2 |
| `docs/archive/2026-04/DB_STATE_2026-04-23.md` | 7 |
| `docs/S15_APPLIED.txt` | 1 |
| `docs/STATE_OF_THE_SYSTEM_2026-05-02.md` (D-16 cutover doc — historical narrative on the pre-2026-04-26 typo path) | 1 |
| `docs/handoffs/HANDOFF_2026-05-02.md` (D-15 handoff protocol — historical narrative) | 1 |
| `docs/handoffs/**` (catch-all per D-15 — every dated handoff is a frozen historical record) | n/a |
| `docs/archive/**` (catch-all for all archived handoffs / session logs) | n/a |

#### Leave-as-frozen-by-design scope

| Path | Files | Hits | Why frozen |
|---|---|---|---|
| `archive/fix_scripts_apr10-12/**` | 16 | 32 | Frozen one-shot fix scripts from April 10–12 |
| `archive/session_artifacts/**` | 2 | 5 | Frozen per-session artifacts |
| `archive/tmp_scripts_apr08/**` | 22 | 65 | Frozen April 8 temp scripts |
| `fixes/2026-04-13/**` | 6 | 12 | Frozen single-day fix scripts |

#### Leave-as-build-artifact scope

| File | Hits | Why ignored |
|---|---|---|
| `.coverage` | 27 | Binary coverage artifact, regenerated on next test run |

### Reproduction

Any greenfield deploy that copies these systemd units or follows any of the
13 listed active docs as its source of truth will install services or crons
pointing at the wrong path. `mining-guardian.service` failing to start is the
most user-visible breakage; the rest are silent until first scheduled run.

### Fix Plan

This bug was fixed in two PRs:

**PR-1 — Bug registry update (PR #35, merged `2888ada`).** Expanded the B-6
entry to match the verified blast radius. No source changes. Got the registry
telling the truth before any path replacement ran.

**PR-2 — Path replacement and narrative cleanup (this commit).** Applied via
targeted-sed across 16 pure-path-only files (8 `deploy/*.service`, all of
`docs/CRON_SCHEDULE.md`, plus `DEPLOYMENT_CHECKLIST.md`, `REPAIR_LOG.md`, and
7 other docs in `docs/` whose only hits were path commands). The 5 mixed
files got per-line review: `MAC_MINI_DEPLOYMENT_RUNBOOK.md` had two path
lines replaced and one stale "Known gotchas" block rewritten to current
paths; `README.md` L503 was rewritten to remove the stale "intentional typo"
claim while preserving the historical context; `CLAUDE.md`,
`MG_UNIFIED_TODO_LIST.md`, and the rewritten `MAC_MINI_DEPLOYMENT_RUNBOOK.md`
L237 retain the typo string as historical / warning context and are now
allowed-exceptions (table above).

Final verification on the PR-2 branch: 65 path-string hits replaced across
17 files; 8 narrative hits intentionally retained across 4 files. Zero
working-tree hits of `Mining-Gaurdian` outside the seven-file
allowed-exception list.

**Optional PR-3 — CI lint** that fails on `Mining-Gaurdian` outside the
seven-file allowed-exception list above plus the
`archive/installer-build-20260428` tag. ✅ **Done 2026-04-29** in PR #72
(Bucket 5). Implemented as `scripts/lint_mining_gaurdian_typo.sh` plus a
GitHub Actions workflow `.github/workflows/lint.yml` that runs the
script on every push and PR. The script:

- greps `Mining-Gaurdian` across the working tree (excluding `.git`)
- filters out an explicit allow-list anchored to repo-relative paths
- prints every disallowed hit with its line numbers, exits 1
- has a `--list` flag for unfiltered hit listing during local audits
- self-includes both the script and the workflow in the allow-list (both
  must contain the typo string by necessity — the script greps for it,
  the workflow names the job after it)

**2026-04-29 PM allow-list refresh (in this same PR #72):** the doc-sweep
(PR #91) merged earlier the same day moved the `SESSION_LOG_*`, `HANDOFF_*`,
`SESSION_HANDOFF_*`, and `DB_STATE_*` files into `docs/archive/2026-04/`
and deleted `RESUME_HERE_2026_04_08_EVENING.md`. The allow-list was
updated in lockstep: individual stale path entries replaced with a
`^\./docs/archive/` directory prefix; `^\./\.github/workflows/lint\.yml$`
added for the workflow self-reference. Lint re-verified clean (62 hits,
all inside the allow-list) before merge.

The allow-list is kept in lockstep with this entry's `Allowed-exception
scope` and `Leave-as-historical-record scope` tables; any new entry must
be added to BOTH the table here and the lint script's `ALLOWED_PATTERNS`
in the same PR. The lint script's header documents this convention.

**Verification (re-run any time):**

```bash
# Confirm the lint runs clean against the current working tree:
scripts/lint_mining_gaurdian_typo.sh
# Should exit 0 with: "B-6 lint: clean (all NN hits are inside the allowed-exception list)."

# Confirm the regression guard fires on a deliberately-bad file:
echo '# Mining-Gaurdian regression test marker' > /tmp/lint_canary.md
cp /tmp/lint_canary.md ./tests_lint_canary.md
scripts/lint_mining_gaurdian_typo.sh ; echo "exit=$?"
# Should exit 1 with the disallowed-hits report.
rm -f tests_lint_canary.md /tmp/lint_canary.md
```

**Optional PR-4** — One-line historical note at the top of
`docs/CRON_SCHEDULE.md` explaining the 2026-04-26 rename. Not yet opened
— may be folded into PR-3 or skipped, depending on reviewer call.

### References

- PR #1 (2026-04-26) — VPS directory rename
- PR #30 (2026-04-28) — original B-6 entry, single-file scope
- PR #34 (2026-04-28) — `docs/REMAINING_WORK_2026-04-28.md`, where the
  expanded scope was first surfaced
- `docs/CLAUDE.md` — Repo paths section

---

## B-7 — Live migrations `002_layer2` + staging not committed to the repo  📘 Runbook landed (2026-04-29)

**Severity:** Medium
**Status:** 📘 Paste-along VPS runbook landed in PR (2026-04-29); commit-execution itself happens VPS-side per runbook (operator must SSH to root@srv1549463, `pg_dump --schema-only`, diff against operator candidates, then commit the canonical files + `migrations/README.md` and flip this entry to ✅ Fixed in the same commit).
**Discovered:** 2026-04-28 (this session, post-import audit)
**Location:** `migrations/` — should contain `002_layer2_*.sql` and the staging
migration; currently contains only `001_initial_schema.sql` and
`migrate_sqlite_to_postgres.py`.

### Description

During the 2026-04-27 live-DB cutover, two migrations were applied to the running
Postgres 16 container:

1. `002_layer2_*.sql` — adds the layer-2 partitioned tables and indexes.
2. The staging migration — wires up the staging schema used by `mg_import_tool`.

Both were applied from the operator's local working copy. Neither was committed
to the repo. The repo's `migrations/` directory therefore does **not** describe
the current shape of the live DB; anyone reconstructing the DB from the repo will
end up at `001_initial_schema.sql` only.

### Evidence

```bash
$ ls migrations/
001_initial_schema.sql
migrate_sqlite_to_postgres.py
```

vs. the live DB which has the layer-2 partitioned tables present and populated
with 127 rows.

### Reproduction

A fresh `git clone` + `docker compose up` + `psql -f migrations/*.sql` will produce
a DB that cannot accept the import driver's INSERTs (column mismatch, partition
not declared).

### Fix Plan

1. Locate the two `.sql` files on the operator's local disk (likely under the
   working clone or `/tmp/` from the 2026-04-27 session).
2. Verify they are byte-identical to what was applied in production by diffing
   against the `pg_catalog`-extracted DDL of the live DB.
3. Commit them as `migrations/002_layer2_<descriptive_suffix>.sql` and
   `migrations/003_staging_<descriptive_suffix>.sql`, in the order they were
   applied.
4. Add a `migrations/README.md` that explains the apply order and what each file
   does.
5. Update `docs/CLAUDE.md` and `docs/SESSION_LOG_2026-04-27.md` to point at the
   committed paths.

### References

- `docs/SESSION_LOG_2026-04-27.md` — addendum #3
- PR #25 (squashed as `6f0b5a2`)
- `docs/DECISIONS.md` D-1 (Postgres-as-canonical)
- `docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md` — paste-along VPS runbook (2026-04-29)

### Doc-side Fix Landed — 2026-04-29

The paste-along VPS runbook now lives at
`docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md`. It walks the operator through
pre-flight, mandatory snapshot, `pg_dump --schema-only` extraction of layer-2 +
staging, byte-level diff against any operator-side candidate `.sql` files, a
decision table for which artefact to commit (candidate vs. live-extracted),
canonical commit paths (`migrations/002_layer2_<suffix>.sql` and
`migrations/004_staging_<suffix>.sql` — slot 003 is already taken by
`003_c5_notify_triggers.sql`, so the staging migration lands at slot 004),
`migrations/README.md` apply-order boilerplate, and the exact LATENT_BUGS.md
flip the operator must include in the same commit to mark this entry ✅ Fixed.

Verification (the runbook itself is now committed to the repo):

```bash
ls docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md
# docs/RUNBOOK_BUCKET_5.7_COMMIT_LIVE_MIGRATIONS.md

grep -c 'B-7' docs/LATENT_BUGS.md
# >= 3   (index row + detail header + this section)
```

When the operator runs the runbook on the VPS and pushes the resulting
migrations + `README.md`, this entry flips from 📘 to ✅ in the same commit per
the `work.projects.mining_guardian.todo_sync` convention.

---

# Low-Severity Bugs

## B-1 — `predictor.py` NameError (~line 4619) — ✅ FIXED

**Severity:** Low
**Status:** Fixed 2026-04-14 in Phase 1 (commit `88b5b08`). The prediction loop in `ai/predictor.py` was crashing immediately with a `NameError` because it referenced bare `miner_id` and `ip` variables that weren't in scope — they were keys on the `m` dict from the SQL query result. The exception was caught by a broad `except` block and logged at DEBUG level, so it looked like the predictor was running but finding no signals when in reality it never analyzed a single miner. Fix: corrected the references to `m["miner_id"]` and `m["ip"]`. See `docs/REPAIR_LOG.md` entry "2026-04-14 · Prediction loop was silently dead — NameError on miner_id/ip".
**Discovered:** 2026-04-12 (code review)
**Location:** `ai/predictor.py` (file is now 1,006 lines; original line ~4619 reference was pre-refactor)

### Verification (re-run any time)

```bash
# B-1 fix is the m["miner_id"] / m["ip"] references inside the prediction loop
grep -n 'm\["miner_id"\]\|m\["ip"\]' ai/predictor.py
# Should return matches around lines 178–191 in the predict() function
```

### Open follow-up (NOT in this PR)

A regression unit test that injects a mocked DB cursor returning a row dict and asserts the predict path runs without `NameError` is still wanted (the original fix-plan asked for one). Tracked as Bucket 5 sub-task; deferred to a follow-up PR so this entry can be flipped without scope creep.

### References

- `docs/REPAIR_LOG.md` 2026-04-14 entry "Prediction loop was silently dead"
- Phase 1 commit `88b5b08`

---

## B-2 — `mining_guardian.py` NameError in `_escalate_board_issue` (~line 4040) — ✅ FIXED

**Severity:** Low
**Status:** Fixed 2026-04-14 in Phase 1 (commit `88b5b08`). The `_escalate_board_issue()` method in `core/mining_guardian.py` referenced an `issue` variable that was never defined in its scope and crashed with `NameError` every time an escalation triggered. Like the predictor bug, the exception was caught silently. Fix: rewrote the function to use the parameters actually passed in (`miner_id`, `ip`, `model`, `dead_idx`, `reason`) consistently. The current implementation lives at `core/mining_guardian.py:1348`. See `docs/REPAIR_LOG.md` entry "2026-04-14 · Board escalation crashed on undefined `issue` variable".
**Discovered:** 2026-04-12 (code review)
**Location:** `core/mining_guardian.py:1348` (file is now 2,638 lines; original line ~4040 reference was pre-refactor)

### Verification (re-run any time)

```bash
# B-2 fix is that _escalate_board_issue uses its parameters consistently
# and references no bare "issue" variable.
grep -n -A 4 'def _escalate_board_issue' core/mining_guardian.py
# Signature should read: (self, miner_id, ip, model, dead_idx, reason) — not "issue"
# Confirm body is clean of the old bug:
awk '/def _escalate_board_issue/,/^    def [a-zA-Z_][a-zA-Z_]*\(/' core/mining_guardian.py | grep -c '\bissue\b'
# Should print 0 (no bare "issue" references inside the function body)
```

### Open follow-up (NOT in this PR)

A regression unit test that exercises `_escalate_board_issue` with a mocked AMS client + DB and asserts it runs to completion is still wanted. Tracked as Bucket 5 sub-task; deferred to a follow-up PR so this entry can be flipped without scope creep.

### References

- `docs/REPAIR_LOG.md` 2026-04-14 entry "Board escalation crashed on undefined `issue` variable"
- Phase 1 commit `88b5b08`

---

## B-8 — 3 silent NameError bugs (missing imports) — ✅ FIXED

**Severity:** High (any path that exercises these modules crashes immediately)

**Status:** Fixed 2026-04-29 in the pre-install pyflakes sweep on freshly merged main (post PR #83). The fixes are tiny one-line import additions; no behavior change for callers, the affected code paths now actually run instead of crashing on first reference.

**Discovery date:** 2026-04-29 (pyflakes scan during install-day prep)

**Locations:**

1. `core/models.py:183` — `RemediationCooldown._last_remediated: Dict[Tuple[str, str], datetime]` referenced `Tuple` without importing it.
   - **Fix:** added `Tuple` to the existing `from typing import Any, Dict, List, Optional` line.
2. `notifiers/approval_interface.py:25` — `ApprovalInterface.request_approval` calls `os.isatty(0)` without importing `os`.
   - **Fix:** added `import os` to the module imports.
3. `notifiers/slack_notifier.py` (lines 88, 170, 242, 559) — `SlackNotifier` calls `requests.post(...)` and `requests.get(...)` without importing `requests`.
   - **Fix:** added `import requests` to the module imports.

**Why these went unnoticed:**
Like B-1 and B-2, the calling sites were wrapped in broad `try/except Exception:` blocks that silently swallowed `NameError`. The code paths registered as a no-op rather than a crash. The webhook fallback in `slack_notifier.py` (the `requests.post` at line 88) had likely never fired because the SDK path was the default; the user-info lookup at line 170 also lived inside a `try/except`.

**Evidence:**
```
$ pyflakes core/models.py notifiers/approval_interface.py notifiers/slack_notifier.py
core/models.py:183:37: undefined name 'Tuple'
notifiers/approval_interface.py:25:16: undefined name 'os'
notifiers/slack_notifier.py:88:17: undefined name 'requests'
notifiers/slack_notifier.py:170:20: undefined name 'requests'
notifiers/slack_notifier.py:242:17: undefined name 'requests'
notifiers/slack_notifier.py:559:24: undefined name 'requests'
```

**Verification (post-fix):**
```
$ pyflakes core/models.py notifiers/approval_interface.py notifiers/slack_notifier.py | grep "undefined name"
(no output — all clean)
$ python3 -m py_compile core/models.py notifiers/approval_interface.py notifiers/slack_notifier.py
(syntax OK)
```

**Why pyflakes ran now:** This is the install-day-eve final pass. The three modules had been touched many times during the SQLite-to-Postgres flip and the post-extraction module split (April 21, 2026, when models, notifiers, and approval logic were carved out of the monolith), but no one had run a static-analysis sweep across the whole tree. With every PR now merged into `main`, the sweep ran on a clean slate and surfaced the leftovers.

### References

- pyflakes 3.4.0 scan, 2026-04-29 21:14 UTC
- Same swallow-NameError pattern documented for B-1 and B-2 above
- Module-extraction history: 2026-04-21 monolith decomposition

---

## B-9 — `tests/run_benchmark.py` referenced by hourly benchmark plist but missing at HEAD

**Severity:** Low
**Status:** Open. Audited 2026-05-04 against PR #123 (D-18 Gap 4 / P-007) and
explicitly waived as a P-007 merge blocker. See "Merge-readiness audit" below.

**Surfaced:** 2026-05-04 by D-18 Gap 4 / P-007 during the cron→launchd cutover.
The file has never existed in any branch in this repo's git history
(`git log --all -- tests/run_benchmark.py` returns empty), so this is not a
regression — the prior `crontab` entry was equally broken, just silently
(no FDA on macOS 14, no fail-loud, no operator-visible signal).

**Location:**

- `installer/macos-pkg/resources/launchd/scheduled/com.miningguardian.scheduled.benchmark.plist`
  invokes `scheduled_job_launcher.sh tests/run_benchmark.py benchmark` hourly
  (`StartInterval=3600`).
- `docs/CRON_SCHEDULE.md` row "Hourly | Benchmark | run_benchmark.py".
- `scripts/setup.sh::phase_10_scheduled` comment block, line 827.
- `console/task_registry.py` declares `task_key="benchmark"` row 11 so the
  D-19 operator console renders the row regardless.

**Behavior at install (intentional):**

`scheduled_job_launcher.sh` exits 1 with the literal line
`[scheduled_job_launcher][benchmark] FATAL: entrypoint not found: /Library/Application Support/MiningGuardian/tests/run_benchmark.py`
on every hourly fire until the script is restored. The launcher writes a
`logs/scheduled/benchmark.last-run.json` stamp with `exit_code=1`, which the
D-19 operator console will surface as a red row on `/tasks`. **This is the
opposite of the cron-era silent-failure mode that motivated D-18 Gap 4 in
the first place** — fail-loud + operator-visible is the design.

**Why this is NOT `tests/run_benchmark.sh`:** A `tests/run_benchmark.sh` does
exist at HEAD, but it is the interactive 60-hour S21 immersion firmware
benchmark with manual operator profile-change prompts and 60+ hours of
sleeps. It is the wrong shape for an hourly cron entrypoint and must not
be substituted.

### Merge-readiness audit (PR #123, P-007), 2026-05-04

**Decision:** Not a P-007 merge blocker. PR #123 ships as authored.

**Reasoning:**

1. PR #123's scope is the cron→launchd cutover (Gap 4). It does not introduce
   the missing-script defect — the script has never existed.
2. The launcher's FATAL-on-missing-entrypoint behavior is the explicit
   design fix for the cron-era silent failure that motivated this PR. Any
   "noisy logs once an hour" complaint cuts in the right direction: fail-loud
   beats fail-silent, every time.
3. Inventing an hourly benchmark script in this PR would violate scope
   discipline (no drive-by feature work) and the task constraint "do not
   invent broad benchmark functionality" the audit task carried explicitly.
4. The customer-readiness impact is bounded: one stamped-failed row in the
   D-19 operator console, hourly. No data corruption, no service-loop
   interference, no Slack noise (this plist does not post to Slack).

**Future fix paths (not in PR #123):**

- **Path A — restore the script.** Recover/author a `tests/run_benchmark.py`
  that does the hourly performance sample described by `docs/CRON_SCHEDULE.md`
  ("Performance tracking"). This is the right long-term answer once the
  intended sample shape is decided. Out of scope here.
- **Path B — disable the plist until A lands.** A small follow-up PR can
  add `<key>Disabled</key><true/>` to `com.miningguardian.scheduled.benchmark.plist`
  so launchd registers the schedule (operator console row stays) but does
  not fire it hourly. Pure noise reduction; reversible by deleting two
  lines once Path A lands.
- **Path C — drop the row entirely.** If "Hourly Benchmark" turns out to
  not be wanted on customer Minis at all, remove the plist + launcher arg
  + `task_registry.py` row + `CRON_SCHEDULE.md` row in one PR.

The choice between A/B/C is a product question for Bobby, not a P-007
mechanical fix. P-007 is delivered as scoped.

### References

- PR #123 (`mg/v103-gap4-scheduled-launchd`) merge-readiness audit, 2026-05-04
- `docs/CRON_SCHEDULE.md` row "Hourly | Benchmark"
- `installer/macos-pkg/resources/launchd/launchers/scheduled_job_launcher.sh`
  exit-1-on-missing-entrypoint contract (lines 57-60)
- `console/task_registry.py` row `task_key="benchmark"` for D-19 console visibility

---

## B-21 — Customer Mac mini install required Homebrew + python@3.12 — ✅ FIXED (P-026, 2026-05-05)

- **Severity:** P0 — blocked Round 9 of the v1.0.3 customer Mac mini install.
- **Status:** ✅ FIXED in PR `mg/p026-installer-owned-python-runtime` (P-026).
- **Discovered:** 2026-05-05 (Round 9, package `MiningGuardian-1.0.3-00720ab71cc4.pkg`, built off main `00720ab` after P-025 merged).
- **Symptom:** `step_create_venv` exited 38 with `python3.12 not found on this Mac; install Homebrew + python@3.12 before running the .pkg`. Postinstall had already brought up Postgres, run all 8 operational migrations, created `mining_guardian_catalog`, deployed the catalog schema, **seeded all 320 miner_models rows**, and installed all 9 launcher wrappers — then died at venv create because the customer Mac mini had no Homebrew install (and was not expected to).
- **Root cause:** pre-P-026 `installer/macos-pkg/scripts/postinstall.sh::step_create_venv` resolved Python 3.12 from `/opt/homebrew/opt/python@3.12/bin/python3.12` (Apple Silicon Homebrew default), with `/usr/local/opt/python@3.12/bin/python3.12` and `command -v python3.12` as fallbacks. That made Homebrew + `python@3.12` a hidden customer prerequisite, which violated the customer-readiness bar already documented under D-23.
- **Fix:** P-026 (this PR) makes Python 3.12 installer-owned. New `build_pkg.sh::step_4i_stage_python_runtime` vendors a relocatable Python 3.12 interpreter from `${HOME}/MiningGuardian-vendor/python-runtime/` (recommended source: python-build-standalone `install_only_stripped` for `aarch64-apple-darwin`, Python 3.12.x) into `<payload>/runtime/python/`, with full validation (Mach-O check, version 3.12.x, `import venv` works, post-rsync sanity probe). `postinstall.sh::step_create_venv` resolves the packaged interpreter (flat `bin/python3.12` OR `Python.framework` layout) BEFORE any Homebrew/PATH fallback. Customers no longer need Homebrew. Locked as **D-27** in `docs/DECISIONS.md`.
- **Tests:** new `tests/installer/test_postinstall_python_runtime.sh` (29 assertions). `tests/installer/test_postinstall_venv.sh` extended with §9 + §10 (P-026 coverage).
- **Detection-going-forward:** any future PR that resolves Python 3.12 from Homebrew or system PATH AS THE PRIMARY (Tier 1) PATH is a regression. Both test suites enforce ordering by line-number comparison.

---

# Process Notes

- New bugs go in here **before** any cleanup or refactor that would erase the
  evidence trail. Over-document — assume the next session has zero memory.
- Every entry must include: severity, status, discovery date, location, description,
  evidence (with literal output where possible), reproduction, fix plan, references.
- When a bug is fixed, do **not** delete the entry. Move it to a "Resolved" section
  at the bottom (to be added on first resolution) with the PR number, commit SHA,
  and date.
- Severity ordering inside each section is by ID, not by priority — priority is
  determined by status + the "Status" field of each entry.
