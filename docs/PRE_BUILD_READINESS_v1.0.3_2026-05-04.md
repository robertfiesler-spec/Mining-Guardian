# Pre-build readiness audit — v1.0.3 — 2026-05-04

```yaml
date:           2026-05-04
written_by:     Computer (autonomous agent), per workstream P-009
scope:          repo-source static analysis only — no build, no sign, no notarize, no host access
input_decisions: D-18 (v1.0.3 scope), D-19 (operator console), D-20 (importer is operator-only)
input_audit:    docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md
input_handoff:  docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md (Step 4 of D-18 implementation plan)
last_main_sha:  c450d12 (P-008, end of source-tree closure work)
this_pr_branch: mg/v103-version-bump-and-release-notes
```

> Per workstream P-009: surface every static blocker between the source tree as it
> stands at the end of P-008 + this PR's version bump and a clean
> build/sign/notarize tomorrow morning on the operator's laptop. **Read-only**:
> no host paths poked, no Apple keychain queried, no live system touched. The
> deliverable is a punch list the operator can run down before invoking
> `./installer/macos-pkg/scripts/build_pkg.sh`.

---

## TL;DR — verdict

**The source tree is ready to build, sign, and notarize v1.0.3 on the operator's laptop.** Every D-18 audit gap that is in v1.0.3 scope (Gaps 1, 2, 4, 5 + Copy bugs 1-4 + Integration bugs 1, 2, 4 + D-19 console foundation + D-20 importer reconciliation) is closed in code, exercised by an installer test, and asserted in `build_pkg.sh` post-assembly. The version stamp the build pipeline reads from `pyproject.toml` reads `1.0.3` after this PR. The release notes file (`docs/RELEASE_NOTES_v1.0.3.md`) lands in this PR alongside the version bump, satisfying the v1.0.2 release-bump pattern.

**No source-tree blockers identified.** The remaining work is operator-side: build / sign / notarize / staple / clean-VM smoke test / Mini install. None of those are static-analyzable from a Linux agent — by design.

**Two items are deferred from v1.0.3 by explicit operator direction** and tracked in the unified TODO list, NOT closed in this audit:

- Row 4 — Gap 3 — Grafana vendoring + provisioning + 11th LaunchDaemon.
- Row 9 — Cloudflare Tunnel + Access auto-provisioning.

---

## Section 1 — Version-stamp readiness

### 1.1 Authoritative version locations

There is **one** authoritative version location in this repo, established in PR #110 (v1.0.2 release bump):

| File | Line | Role | State at end of P-009 |
|---|---|---|---|
| `pyproject.toml` | 3 | Single source of truth — read by `build_pkg.sh::step_3_stamp_build` via `python3 -c "import re; m=re.search(r'^version\s*=\s*[\"\']([^\"\']+)', open('pyproject.toml').read(), re.M); print(m.group(1))"` | `version = "1.0.3"` ✅ |

### 1.2 Other places that mention a version literal — surveyed and verified non-authoritative

| File | Reference | Role | Action |
|---|---|---|---|
| `api/approval_api.py:126` | `version="1.0.0"` (FastAPI app metadata) | Unrelated to release stamp; was 1.0.0 at v1.0.1 + v1.0.2 too | No change — out of scope |
| `api/dashboard_api.py:146` | `version="1.0.0"` (FastAPI app metadata) | Same as above | No change — out of scope |
| `console/main.py:59` | `version="1.0.3-d19-foundation"` (FastAPI app metadata for the new console) | Descriptive label set by P-006 | No change — accurate description of the foundation milestone |
| `installer/macos-pkg/resources/welcome.html:181` | `Mining Guardian · v1.0` (eyebrow text) | Generic marketing label, unchanged across point releases | No change — generic label is correct |
| `installer/macos-pkg/resources/MiningGuardian.conf.template:21` | `# .PKG INSTALL PATH (D-18 Gap 1, v1.0.3)` | Comment | No change — comment correctly attributes to v1.0.3 |
| `installer/macos-pkg/resources/launchd/**` | various `v1.0.3` headers | Comments | No change — accurate attribution |
| `installer/macos-pkg/scripts/postinstall.sh` | various `v1.0.2` / `v1.0.3` historical comments | Comments | No change — historical accuracy is the point |
| `installer/macos-pkg/scripts/build_pkg.sh` | various `v1.0.2` / `v1.0.3` historical comments | Comments | No change — accurate attribution |

**Conclusion:** the only file that materially affects the .pkg filename, signing, and notarization is `pyproject.toml`. Bumped 1.0.2 → 1.0.3 in this PR. No drift risk.

### 1.3 Future drift guard

This PR adds `tests/installer/test_release_notes_version_drift.sh` which asserts:

1. `pyproject.toml` parses to a semver string `vX.Y.Z`.
2. `docs/RELEASE_NOTES_v${VERSION}.md` exists for that exact version.
3. The first heading in the release notes file matches the version (`# Mining Guardian v1.0.3`).
4. No older `RELEASE_NOTES_*.md` file claims a version `>= ${VERSION}` that would shadow the current release.

This protects against a future "I bumped pyproject but forgot the notes" or vice-versa.

---

## Section 2 — Build pipeline readiness (`build_pkg.sh` static analysis)

The pipeline has 9 steps, with assertions added across the v1.0.3 PR train. All exit codes are reserved and documented in the script header.

| Step | Purpose | Asserts | Exit code on failure | State |
|---|---|---|---|---|
| 1 | Verify Apple cert + notarization creds reachable | `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` parseable | 41 | Verified static |
| 2 | Refuse to build with dirty git tree | `git diff-index --quiet HEAD --` | 42 | Verified static |
| 3 | Stamp build with git SHA + version | `pyproject.toml` parses to a version | implicit (python crash) | Now stamps `1.0.3` ✅ |
| 4a | Assemble payload — rsync include list | `mg_import_tool/***` excluded (D-20, P-004) | n/a (rsync) | Verified static |
| 4e + 4f | Vendor Python wheels (Gap 5, P-002) | `payload-requirements.txt` resolves | n/a (pip) | Verified static |
| 4g | Catalog seed staged in payload (Gap 2, P-003) | `find <payload>/intelligence-catalog/seed-data -name 'seed_miner_models.sql'` | 44 | Verified static |
| 4h | No `mg_import*` paths in customer payload (D-20, P-004) | `find <payload> -name 'mg_import*' \| head -1` empty | 43 | Verified static |
| 4i | 11 scheduled-task plists present (Gap 4, P-007) | `find <payload>/launchd/scheduled -name '*.plist' \| wc -l == 11` | 47 | Verified static |
| 4j | `bin/uninstall.sh` present + executable (Copy bug 3, P-008) | `[[ -x ${PKG_DIR}/resources/uninstall.sh ]]` | 48 | Verified static |
| 5 | Sign payload with Developer ID Installer cert | `productbuild` exit 0 | 44 | Operator-side, not statically verifiable |
| 6 | Submit to notarization via `notarytool` | exit 0 + status `Accepted` | 45 | Operator-side, not statically verifiable |
| 7 | Staple notarization ticket | `xcrun stapler staple` exit 0 | 46 | Operator-side, not statically verifiable |
| 8 | Drop final .pkg in `build/` with sha256 sidecar | sha256 file present | implicit | Operator-side, not statically verifiable |
| 9 | Print install command for operator | n/a | n/a | n/a |

**Static-analysis conclusion:** every step that can fail before the cert is touched has an assertion. No new assertions are needed for v1.0.3 — the existing P-002/P-003/P-004/P-007/P-008 assertions cover every gap that v1.0.3 closes.

---

## Section 3 — Test surface readiness

Tests that exist at HEAD on this branch:

| Suite | File | Assertion count | Coverage |
|---|---|---|---|
| Postinstall venv (Gap 5) | `tests/installer/test_postinstall_venv.sh` | 24 | venv creation, vendored wheels, payload-requirements pinning |
| Postinstall catalog seed (Gap 2) | `tests/installer/test_postinstall_catalog_seed.sh` | 24 | catalog DB creation, schema bundle, 320-row seed, build assertion |
| D-20 importer payload reconciliation | `tests/installer/test_d20_importer_payload_reconciliation.sh` | 32 | rsync include list, post-assembly find assertion, migrations 006+007 |
| Postinstall customer info (Gap 1) | `tests/installer/test_postinstall_customer_info.sh` | 76 | Desktop conf flow, validation rules, .env shape, Cocoa dialog, generated secrets |
| Postinstall scheduled jobs (Gap 4) | `tests/installer/test_postinstall_scheduled_jobs.sh` | 115 | 11 plists, scheduling primitive, launcher invocation, postinstall ordering, build assertion, console label drift |
| Installer copy (Copy bugs 1, 2, 4) | `tests/installer/test_installer_copy.sh` | 43 | service/scheduled-job counts, no-cron wording, no-Grafana-control claim, port URLs, all 10 service labels in verify block |
| Uninstall script (Copy bug 3) | `tests/installer/test_uninstall_script.sh` | 50 | source presence, mode 0755, bash syntax, all 21 plist labels, drift check vs `postinstall.sh`, all flags, data-preservation default, root + non-TTY guards |
| Console (D-19, P-006) | `tests/console/` | 63 | FastAPI app, task registry, launchctl wrapper, system-state probes, pending-approvals, INTERNAL_API_SECRET sentinel |
| **NEW** Release notes drift (P-009) | `tests/installer/test_release_notes_version_drift.sh` | _stamped on PR_ | pyproject ↔ release notes coupling |

**Total installer + console at end of P-008:** 364 + 63 = **427 assertions**. All green per `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md` EOD addendum.

This PR adds the version-drift test, bringing the floor to ~430+ assertions (final count stamped in HANDOFF_2026-05-04.md after the test runs).

---

## Section 4 — D-18 audit gaps — pass / fail status

| Gap / Bug | v1.0.3 status | Closed in | Static-verified? |
|---|---|---|---|
| Gap 1 — Customer-info collection | ✅ closed | P-005 | Yes — postinstall calls `step_collect_customer_info` before `step_layout_install_root` |
| Gap 2 — Catalog DB + 320-row seed | ✅ closed | P-003 | Yes — postinstall calls `step_provision_catalog_db_and_seed`; build asserts seed staged |
| Gap 3 — Grafana vendoring + provisioning + LaunchDaemon | 🔴 deferred | _row 4_ | n/a — explicit operator deferral |
| Gap 4 — Scheduled-tasks launchd plists | ✅ closed | P-007 | Yes — 11 plists shipped, build asserts presence |
| Gap 5 — Python venv + pip install | ✅ closed | P-002 | Yes — postinstall calls `step_create_venv`; wheels vendored |
| Copy bug 1 — "four services" | ✅ closed | P-008 | Yes — `tests/installer/test_installer_copy.sh` asserts "ten" |
| Copy bug 2 — wrong dashboard / approval port | ✅ closed | P-008 | Yes — same test asserts `:8585` / `:8686` / `:8787` |
| Copy bug 3 — `bin/uninstall.sh` does not exist | ✅ closed | P-008 | Yes — file present in source tree, build assertion 4j |
| Copy bug 4 — verify code block enumerates only 4 services | ✅ closed | P-008 | Yes — same test asserts all 10 labels |
| Integration bug 1 — `MG_DB_PASSWORD` flow | ✅ closed | P-005 | Yes — `step_drop_dotenv` generates secret in-process |
| Integration bug 2 — `GUARDIAN_PG_USER` vs `PGUSER` | ✅ closed | P-005 | Yes — both keys written |
| Integration bug 3 — Tailscale handling | 🔵 partial | postinstall surfaces Cocoa dialog | Yes — operator-side `tailscale up` is by design |
| Integration bug 4 — All customer-tunable .env keys missing | ✅ closed | P-005 | Yes — `.env` shape mirrors `setup.sh::phase_07_secrets` |

**Conclusion:** every D-18 audit gap that is in v1.0.3 scope is statically verified closed.

---

## Section 5 — D-19 + D-20 closure status

### D-19 console (10th service, port 8787)

- ✅ FastAPI app under `console/main.py` with task registry, launchctl wrapper, system-state probes, pending-approvals helpers.
- ✅ 10th LaunchDaemon plist `com.miningguardian.console.plist` + launcher `console_launcher.sh` shipped.
- ✅ Postinstall PLIST_LABELS / LAUNCHER_FILES extended to 10 services.
- ✅ `build_pkg.sh` rsync include list extended with `console/***`.
- ✅ Port collision with `api/approval_api.py:8686` resolved (console uses `:8787`).
- ✅ INTERNAL_API_SECRET sentinel test verifies no leak to browser.
- 🔴 **Step 5 — Cloudflare Tunnel + Access auto-provisioning — DEFERRED to row 9.**

### D-20 importer reconciliation

- ✅ `mg_import_tool/***` excluded from `build_pkg.sh` rsync include list (P-004).
- ✅ Cross-directory `mg_import_tool/sql/migrations/` rsync removed.
- ✅ Runtime-relevant migrations relocated to `migrations/006_field_log_bootstrap.sql` and `migrations/007_layer2_resolver.sql` (byte-identical bodies).
- ✅ Build assertion `find <payload> -name 'mg_import*' | head -1` empty — exit 43 on regression.
- ✅ Operator-side originals at `mg_import_tool/sql/migrations/` retained (importer-only bootstrap).
- ✅ `tests/installer/test_d20_importer_payload_reconciliation.sh` (32 assertions).

---

## Section 6 — Resource paths, plist labels, port table — drift checks

### 6.1 Plist labels (postinstall ↔ uninstall ↔ tests)

The 10 service labels enumerated by all four sources of truth:

```
com.miningguardian.scanner
com.miningguardian.dashboard-api
com.miningguardian.approval-api
com.miningguardian.slack-listener
com.miningguardian.slack-commands
com.miningguardian.overnight-automation
com.miningguardian.alerts
com.miningguardian.intelligence-report
com.miningguardian.console
com.miningguardian.feedback-loop-daemon
```

The 11 scheduled-job labels:

```
com.miningguardian.scheduled.morning-briefing
com.miningguardian.scheduled.weekly-training
com.miningguardian.scheduled.refinement-chain
com.miningguardian.scheduled.daily-deep-dive
com.miningguardian.scheduled.benchmark
com.miningguardian.scheduled.knowledge-backup
com.miningguardian.scheduled.log-collection
com.miningguardian.scheduled.log-failure-report
com.miningguardian.scheduled.db-maintenance
com.miningguardian.scheduled.ams-cleanup
com.miningguardian.scheduled.operator-review
```

Drift checks at HEAD:
- ✅ `installer/macos-pkg/scripts/postinstall.sh::PLIST_LABELS` (10 entries) matches the file list under `installer/macos-pkg/resources/launchd/*.plist`.
- ✅ `installer/macos-pkg/resources/uninstall.sh` enumerates all 10 + 11 = 21 labels (asserted by `tests/installer/test_uninstall_script.sh`).
- ✅ `console/task_registry.py` enumerates all 10 services + 11 scheduled jobs.
- ✅ `installer/macos-pkg/resources/conclusion.html` verify code block enumerates all 10 service labels (asserted by `tests/installer/test_installer_copy.sh`).

### 6.2 Port table (welcome.html ↔ conclusion.html ↔ postinstall.sh ↔ console main.py)

| Service | Port | Where it appears |
|---|---|---|
| Dashboard API | 8585 | `welcome.html`, `conclusion.html`, `postinstall.sh::main()`, `setup.sh::phase_07_secrets`, `api/dashboard_api.py` |
| Approval API | 8686 | `conclusion.html`, `postinstall.sh::main()`, `api/approval_api.py` |
| Operator Console | 8787 | `welcome.html`, `conclusion.html`, `postinstall.sh::main()`, `com.miningguardian.console.plist`, `console/main.py`, `docs/CONSOLE_OPERATIONS_GUIDE.md` |

**Drift check at HEAD:** `tests/installer/test_installer_copy.sh` asserts the welcome + conclusion HTML port references match the canonical table. No `:8080` / `:8081` literals remain in `welcome.html` / `conclusion.html` / `postinstall.sh::main()`.

### 6.3 Catalog seed path (build assertion ↔ postinstall ↔ source)

- ✅ Source: `intelligence-catalog/seed-data/seed_miner_models.sql` (320 rows) and `intelligence-catalog/seed-data/deploy_schema.sql`.
- ✅ Build assertion (step 4g): `find ${PAYLOAD_DIR}/intelligence-catalog/seed-data -name 'seed_miner_models.sql'` — exit 44 on miss.
- ✅ Postinstall: `step_provision_catalog_db_and_seed` reads from `${PAYLOAD_PREFIX}/intelligence-catalog/seed-data/seed_miner_models.sql`.

---

## Section 7 — Static blockers identified — punch list

**None.**

The source tree at the end of P-008 + this PR's pyproject bump is statically clean for the build to proceed. Every gap that is in v1.0.3 scope is closed in code, exercised by an installer test, and asserted by `build_pkg.sh` post-assembly.

---

## Section 8 — Remaining work that is NOT static-analyzable

These are the v1.0.3 gates that cannot be verified from a Linux agent. They are listed here for the operator's reference, in execution order:

1. **Operator's laptop:** `git pull --ff-only origin main` + `./installer/macos-pkg/scripts/build_pkg.sh`. Output: `build/MiningGuardian-1.0.3-<sha>.pkg` with `.sha256` sidecar and `.notarization-log.txt`.
2. **Operator's laptop:** spin up a clean macOS 14 VM (UTM/Tart). Drop the .pkg in. Drop a valid `MiningGuardian.conf` on the VM Desktop. Double-click. Walk every screen. Run the verification checklist from `docs/RELEASE_NOTES_v1.0.3.md` "Verify" section.
3. **Operator's laptop → Mac Mini:** if step 2 passes ALL criteria, install on the Mini. Screenshots at every screen per D-16 step 4.
4. **Operator's laptop:** verify the Mini meets the D-16 cutover criteria (operational paper trail, AI loop running, scheduled jobs firing, console reachable over Tailscale).
5. **Operator's laptop:** if step 4 verifies green — and only then — VPS decommission + ROBS-PC container shutdown per D-16.

**Failure modes to watch for in step 2 (clean-VM smoke test):**
- Postgres container fails to start because Colima isn't installed → postinstall should hard-fail, not warn (review `lib/install_colima.sh` log on smoke-test failure).
- Catalog DB seed fails because the schema bundle's `\ir` paths don't resolve → review `intelligence-catalog/seed-data/deploy_schema.sql` line 1 against the staged payload directory layout.
- `pip install` from vendored wheels fails because the venv's pip can't find a wheel → confirm `payload-requirements.txt` matches what the runtime actually imports (the pin set was vetted at P-002 against the frozen production environment, but a fresh macOS 14 venv could have arch-specific wheel mismatches; if so, vendor the platform wheel).
- Cocoa dialog never surfaces because the install ran without a SUDO_USER → `step_collect_customer_info` falls back to `/Users/Shared/MiningGuardian.conf` per the implementation; verify on the VM.
- 11 scheduled-task plists registered but `launchctl list` shows them in `0` state → check the `scheduled_job_launcher.sh` exit code on first fire; common cause is missing `.env` source.

---

## Section 9 — Sign-off

Per workstream P-009: **safe to merge this PR. Safe to invoke `build_pkg.sh` against the merged commit.** No source-tree blockers remain. Every D-18 / D-19 / D-20 in-scope item is closed in code, exercised by tests, and asserted in the build pipeline.

The deferral list (Grafana row 4, Cloudflare row 9) is explicit, tracked, and per operator direction. The clean-VM smoke test gate (D-18) is HARD per locked decision; it is not skippable and is not statically replaceable.

End of pre-build readiness audit.
