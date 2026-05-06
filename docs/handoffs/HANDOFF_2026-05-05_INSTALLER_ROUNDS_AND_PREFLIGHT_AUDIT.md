# Mining Guardian v1.0.3 — 2026-05-05 Installer Rounds Recap and Full Preflight Audit Pause

```yaml
date: 2026-05-05
session_id: docs-only checkpoint after P-024 merged; full installer preflight audit (P-025) still running as a separate subagent
last_commit_on_main: 6a48a82 — fix(installer): D-18 P-024 align catalog seed with manufacturers schema
latest_pkg_attempted_on_mini: MiningGuardian-1.0.3-dd482af746ad.pkg (Round 8, pre-P-024 merge)
agent: Computer (autonomous agent)
repo: Mining-Guardian
scope: installer / Mac Mini install only — docs-only checkpoint; no source/build script changes in this PR
```

This file is a docs-only checkpoint. It was originally written alongside
two parallel subagents (P-024 catalog seed fix + full installer preflight
audit). As of this rebase, P-024 has merged into `main` as commit
`6a48a82` (PR #142, 2026-05-05). The full installer preflight audit
subagent (now tracked as P-025) is still running and has NOT yet merged.

This handoff captures the 2026-05-05 install timeline as observed through
Round 8, records the pause state, and gives the next session a single
place to land that names what is merged, what is still in flight, and
the resume gate (D-26).

The earlier handoffs in the v1.0.3 train —
`docs/handoffs/HANDOFF_2026-05-04.md`,
`docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md`,
`docs/handoffs/HANDOFF_2026-05-04_REBUILDING_AFTER_P015.md`,
`docs/handoffs/HANDOFF_2026-05-04_NIGHT_PAUSE_POSTINSTALL_FAILURE.md`,
and `docs/handoffs/HANDOFF_2026-05-04_NEW_CHAT.md` — remain valid as
historical context. This file picks up after the P-023 merge (`dd482af`),
the immediately-following Round-8 install attempt, and the subsequent
P-024 merge (`6a48a82`).

The decisions log already contains D-13 through D-25; the new D-26 added
in this PR captures the explicit "no more Mac mini install attempts until
the full preflight audit completes" rule. See `docs/DECISIONS.md`. With
P-024 now merged, the remaining gate under D-26 is the preflight-audit
PR (P-025) plus any P0 fixes that audit surfaces.

---

## Standing rules from Rob (carry forward)

- Over-document everything so future sessions have a reference point.
- Go slow and do it right; no shortcuts.
- Ask questions only when needed, and document Rob's answers.
- This workstream is only about the installer and installing on the new
  Mac mini.
- Do not fix Grafana right now.
- Do not rush the install.
- New today (2026-05-05): stop the one-failure-at-a-time chain — do not
  run a fresh install on the Mini until BOTH P-024 (now merged) AND the
  full installer preflight audit (P-025, still in flight) are merged and
  reflected in `main`, and any P0 fixes surfaced by the audit are landed.
  Captured as D-26 in this PR.

---

## Very important next-session warning

Do NOT rerun the installer on the Mac mini.

Do NOT rebuild a fresh `.pkg` from `main` and ship it to the mini.

Do NOT uninstall or clean Postgres / Colima state on the mini until
the preflight-audit PR (P-025) is merged AND any P0 fixes it surfaces
are merged AND a fresh build off the merged `main` is ready.

The next session must:

1. Read this handoff.
2. Read `docs/MG_UNIFIED_TODO_LIST.md` rows 10o (P-023, ✅ as of `dd482af`)
   and 10p (P-024, ✅ as of `6a48a82`).
3. Read the preflight-audit PR description (whatever branch / PR number
   the audit subagent opens) and the audit doc it produces.
4. For every gap the audit surfaces: decide P0 (must fix before Mini)
   vs deferred (file as a new P-NNN row), and land any P0 fixes.
5. Only then evaluate whether a Round-9 install is appropriate.

---

## Where each workstream lives right now (2026-05-05)

### Already merged

| ID    | Topic                                                                 | Commit on main |
|-------|-----------------------------------------------------------------------|----------------|
| P-016 | Bound postinstall Cocoa alerts + operator user resolver               | `9318062`      |
| P-017 | Resolve payload path from install root                                | `bae1891`      |
| P-018 | Helper libs (install_colima.sh / install_ollama.sh) use `MG_INSTALL_OPERATOR_USER` | `32ec2dc`      |
| P-019 | Propagate PATH under `sudo -u` for Colima / docker                    | `47efd65`      |
| P-020 / P-021 | limactl source location + sign Lima VZ binaries with virtualization entitlement | `e514c12`      |
| P-022 | Export generated env (`MG_DB_PASSWORD` and friends) into the postinstall shell | `b66b864`      |
| P-023 | Migration 006a — layer-2 resolver prerequisites (`uuid-ossp`, `set_updated_at()`, `hardware.miner_models` / `pool.mining_pools` FK target stubs) | `dd482af`      |
| P-024 | Catalog seed schema alignment — strip dead `INSERT INTO hardware.manufacturers (full_name, country, website, notes)` block from `intelligence-catalog/seed-data/seed_miner_models.sql` (and from the `compile_all_miners.py` generator); manufacturer rows are owned exclusively by `deploy_schema.sql` which uses the canonical column names. New regression test `tests/installer/test_catalog_seed_schema_compat.sh` (17 assertions). PR #142 merged 2026-05-05. | `6a48a82`      |

### In flight (NOT yet on `main`)

| ID    | Topic | Status |
|-------|-------|--------|
| P-025 (preflight audit) | End-to-end audit of the rest of the installer / postinstall path that has NOT been exercised live yet (uninstall script install, console plist registration, scheduled-job plists, log-collector plist, Ollama install, daily/weekly cron staging, anything downstream of `step_provision_catalog_db_and_seed`). Output: a single audit doc enumerating every untested step, its current code path, and any prerequisite gaps the audit finds. Any P0 gaps surfaced may be fixed in the audit PR or filed as new P-NNN rows with explicit "must-fix-before-Mini" gating. | 🟡 — branch and PR opened by the audit subagent; do not duplicate. |

This handoff does NOT include the preflight audit. Its commits live on
its own branch and will land via its own PR. This PR is documentation
only.

---

## Round-8 install timeline (`dd482af` → catalog seed mismatch)

`MiningGuardian-1.0.3-dd482af746ad.pkg` was built from `dd482af` (P-023
merged), transferred to the Mac mini, passed checksum + Gatekeeper, and
was installed with `sudo installer -pkg ... -target /`.

The postinstall log progressed considerably further than any prior round:

```
INFO operator user resolved: miningguardian
INFO Desktop conf parsed
INFO .env written mode 0600
INFO loaded generated env keys into postinstall shell: MG_DB_PASSWORD CATALOG_API_KEY INTERNAL_API_SECRET …
INFO step_provision_postgres preflight OK: required env keys present
INFO limactl present at /usr/local/bin/limactl
INFO Colima VZ started
INFO postgres image loaded
INFO mining_guardian ready
INFO applying 001_…sql
INFO applying 003_…sql
INFO applying 004_drop_dead_stubs.sql
INFO applying 004_system_settings.sql
INFO applying 005_…sql
INFO applying 006_…sql
INFO applying 006a_layer2_prereqs.sql        ← P-023 fix landing live for the first time
INFO applying 007_layer2_resolver.sql        ← P-023 unblocks 007 (the prior FATAL)
INFO all migrations applied
INFO step_provision_catalog_db_and_seed: creating mining_guardian_catalog
INFO applying intelligence_catalog_schema.sql
INFO applying seed_miner_models.sql
ERROR: column "full_name" of relation "hardware.manufacturers" does not exist
[postinstall] FATAL (39) catalog seed seed_miner_models.sql failed
```

Exit code `39` is the reserved code for "Gap 2 — catalog seed failed"
per the existing postinstall reservations (cross-check
`tests/installer/test_postinstall_catalog_seed.sh`). The proximate
failure is the `hardware.manufacturers.full_name` mismatch; the
P-024 subagent owns the precise fix.

This is the FURTHEST any install round has progressed. P-022 unblocked
env handoff into postgres provisioning. P-023 unblocked migration 007's
prerequisites. The next failure is in the catalog seed, downstream of
both. Each successive round has surfaced exactly one new bug per round —
which is the pattern Rob is now stopping (D-26).

---

## What this means for the unified TODO list

Row updates accompanying this PR are docs-only:

1. Row 10o (P-023) — already ✅ on `main` (its merged-state field was
   landed by the P-023 PR `dd482af`). This PR appends the Round-8 live
   confirmation that 006a/007 ran clean against the operational DB.
2. Row 10p (P-024) — already ✅ on `main` as of `6a48a82` (PR #142
   merged 2026-05-05). The P-024 row's narrative was authored by the
   P-024 PR; this PR does not rewrite it.
3. Row 13 (Install on Mini + screenshots) — Round 8 outcome appended,
   noting the catalog seed mismatch (now fixed in P-024). Row stays 🔴
   — install is NOT verified live.
4. Row 11 (Build, sign, notarize, staple v1.0.3 .pkg) — updated to
   reference the `dd482af` build and the D-26 block on the next rebuild
   (now waiting on P-025 + any P0 fixes the audit surfaces). Stays 🟡.

A new row 10q is added for the full installer preflight audit (P-025).
The status field is intentionally short ("🔴 — owned by the preflight
audit subagent") because the authoritative narrative belongs in that
PR's description.

The build/install rows (11, 12, 13) stay 🟡 / 🔴 — nothing in this PR
changes their status. Status flips on those rows happen only once the
preflight audit (P-025) and any P0 fixes it surfaces are merged AND a
fresh `.pkg` built from the merged `main` is ready to ship to the Mini.

---

## D-26 — the new locked decision

Captured in `docs/DECISIONS.md` in this PR.

Plain-language summary (the canonical version is in DECISIONS.md):

After eight rounds of "build, ship to Mini, watch postinstall fail at the
next step," Rob is locking the rule that no further `.pkg` install
attempts on the Mac mini happen until the full installer preflight audit
completes and any gaps it finds are merged. The pattern of fixing one
postinstall step per round is wasting build cycles, exposing the customer
mini to half-installed states (Colima profiles, Postgres containers,
partial schemas), and producing operator cleanup work between every
round.

The D-26 rule applies until:

1. P-024 is merged (catalog seed mismatch fixed) — ✅ done, merged
   2026-05-05 as `6a48a82` (PR #142).
2. The full installer preflight audit PR (P-025) is merged AND every
   P0 gap it surfaces is also merged. Gaps may be fixed in the audit PR
   itself or filed as new P-NNN rows in the unified TODO list with
   explicit "must-fix-before-Mini" gating.
3. A fresh `.pkg` is built from the merged `main` AND validated through
   whichever validation path the audit recommends (the D-22 skip-VM
   decision is explicitly NOT widened by D-26).

D-26 does NOT alter:

- D-18 (v1.0.3 installer scope)
- D-22 (Mac Mini is the first clean-target install — but D-26 narrows
  when that install happens)
- D-23 (customer onboarding UX gaps remain forward-looking)
- D-24 / D-25 (script naming + arch gate are already merged)

D-26 explicitly rescinds the implicit "ship the next .pkg as soon as the
next single fix lands" pattern that the train has been following since
P-013.

---

## Operator state on the Mac mini right now (after Round 8)

`bin/uninstall.sh` is still NOT installed (its installer step runs after
`step_provision_catalog_db_and_seed`, which is exactly where Round 8
failed). Cleanup is manual.

The Round-8 attempt got far enough to:

- Bring up Colima VZ and load the postgres image
- Bring up the operational DB `mining_guardian`
- Apply migrations 001 → 006a → 007 → all subsequent
- Create the catalog DB `mining_guardian_catalog`
- Apply `intelligence_catalog_schema.sql`
- Begin `seed_miner_models.sql` and fail on the column mismatch

So the mini currently has BOTH databases up, the operational DB fully
migrated, and the catalog DB partially populated (schema applied, seed
not). LaunchDaemons are NOT loaded yet (their step runs after the seed).
The `.env` file at `/Library/Application Support/MiningGuardian/.env` is
in place mode 0600 with the rotated AMS + Slack credentials.

Do not run cleanup yet. The next install will be against a fresh build
off merged `main` (P-024 + preflight audit). Cleanup happens at that
point, not now. If for any reason cleanup is needed before then — e.g.,
the mini reboots and a partial daemon set tries to load — the cleanup
template lives in the prior handoff
`docs/handoffs/HANDOFF_2026-05-04_NIGHT_PAUSE_POSTINSTALL_FAILURE.md`
under "Operator cleanup before next reinstall." That template is still
the canonical one; D-26 does not change cleanup mechanics, only timing.

---

## Round count

| Round | Source commit | Outcome | Fixed by |
|-------|---------------|---------|----------|
| 1 | `2b48f98` (P-014)         | preinstall arch gate FATAL under Rosetta | P-015 / `cf1691e` |
| 2 | `cf1691e` (P-015)         | postinstall payload path FATAL | P-016 / P-017 |
| 3 | `9318062` (P-016)         | helper-lib operator-user resolution | P-018 / `32ec2dc` |
| 4 | `32ec2dc` (P-018)         | PATH under `sudo -u` for Colima | P-019 / `47efd65` |
| 5 | `47efd65` (P-019)         | limactl source + VZ entitlement | P-020 / P-021 / `e514c12` |
| 6 | `e514c12` (P-020/P-021)   | env handoff to postgres provisioning | P-022 / `b66b864` |
| 7 | `b66b864` (P-022)         | migration 007 missing prerequisites | P-023 / `dd482af` |
| 8 | `dd482af` (P-023)         | catalog seed `hardware.manufacturers.full_name` mismatch | P-024 / `6a48a82` (merged 2026-05-05) |

Eight rounds. P-024 is now merged as `6a48a82`. Rob's call is that
Round 9 is not happening until the preflight audit (P-025) is merged and
any P0 fixes it surfaces are landed. That is D-26.

---

## Resume path for the next session

1. Read this handoff.
2. Read `docs/DECISIONS.md` D-26. Understand that no Round-9 install
   happens until the preflight audit (P-025) and any P0 fixes it
   surfaces are merged.
3. P-024 is already merged as `6a48a82`. Confirm in `git log --oneline
   main` if needed. Row 10p in `MG_UNIFIED_TODO_LIST.md` is ✅.
4. Read the preflight audit PR (open as of writing — branch / PR number
   set by the audit subagent) and read the audit doc it produces.
5. For every gap the audit finds, decide: fix in the audit PR or open a
   new P-NNN row. Do NOT bundle gap fixes into a Mini install attempt.
6. After the audit PR (and any P0 fix PRs) merge, build a fresh `.pkg`
   off merged `main` with `installer/macos-pkg/scripts/build_pkg.sh`.
   Confirm signed + notarized + stapled. The build artifact name will
   be `MiningGuardian-1.0.3-<new-sha>.pkg`.
7. Run cleanup on the Mac mini per the
   `HANDOFF_2026-05-04_NIGHT_PAUSE_POSTINSTALL_FAILURE.md` template.
8. Then — and only then — install on the Mini.

If a Round 9 fails at a step the preflight audit said was clean, that is
a regression in the audit, not a continuation of the P-013 → P-024 chain.
Investigate it that way.

---

## What this PR changes

- `docs/handoffs/HANDOFF_2026-05-05_INSTALLER_ROUNDS_AND_PREFLIGHT_AUDIT.md`
  (this file) — new; rebased after P-024 merged into `main`.
- `docs/MG_UNIFIED_TODO_LIST.md` — appends Round-8 outcome to row 13;
  adds row 10q (preflight audit / P-025) as a 🔴 placeholder pointing
  at the in-flight subagent PR; updates row 11 to reference the
  `dd482af` build and the D-26 block on the next rebuild. Row 10p
  (P-024) is already on `main` as ✅ from PR #142 — this PR does not
  rewrite that row.
- `docs/DECISIONS.md` — adds D-26 (revised wording: P-024 is recorded
  as merged; the remaining gate is the preflight audit P-025 plus any
  P0 fixes the audit surfaces).

This PR does NOT touch:

- Source code (`installer/`, `core/`, `api/`, `console/`, `migrations/`,
  `intelligence-catalog/`, `mg_import_tool/`)
- Build scripts (`installer/macos-pkg/scripts/build_pkg.sh`, `setup.sh`)
- Tests
- Any catalog SQL or seed files

The preflight audit subagent owns the audit doc. This PR owns the docs
checkpoint and the D-26 lock.

---

# Addendum 2026-05-05 — Round 9 outcome + P-026 (installer-owned Python 3.12 runtime)

> Branch: `mg/p026-installer-owned-python-runtime` (this PR).
> Status: source fix complete and tested in repo; Round 10 install GATED on PR merge AND on operator running RUNBOOK "Block Pre-B" once on build host.

## Round 9 outcome

P-025 (the preflight audit P0 fixes) merged as `00720ab` (PR #144) and the post-P-025 build was installed on the customer Mac mini:

- Package: `MiningGuardian-1.0.3-00720ab71cc4.pkg`
- Built from main: `00720ab71cc45a1cf9e32a382f40f382f6c8955d`
- Gatekeeper / notarization: accepted
- Mac mini location: `/Users/miningguardian/Downloads/MiningGuardian-1.0.3-00720ab71cc4.pkg`

Postinstall progressed past every prior gate (env keys exported, Colima VZ
started, postgres image loaded, all 8 operational migrations applied,
`mining_guardian_catalog` created, `deploy_schema.sql` applied —
`Schema deployment complete | sources_count 23 | manufacturers_count 17`,
**catalog seed verified at 320 rows**, all 9 launcher wrappers installed),
then exited 38 in `step_create_venv` with:

```text
2026-05-05T22:13:39Z [postinstall] FATAL (38) python3.12 not found on this Mac;
install Homebrew + python@3.12 before running the .pkg (operator setup manual covers this)
```

## P-026 — root cause + decision

Pre-P-026 `step_create_venv` resolved Python 3.12 from
`/opt/homebrew/opt/python@3.12/bin/python3.12` (Apple Silicon Homebrew),
falling back to `/usr/local/opt/python@3.12/bin/python3.12` (Intel) and
`command -v python3.12`. That made Homebrew + `python@3.12` a hidden
customer prerequisite. The customer Mac mini did not have Homebrew, and
was not expected to — the Mini ships as a single-purpose appliance.

**Operator decision (Rob, 2026-05-05):** "yes include it in the installer
and whatever else might pop up as the install keeps going". The .pkg
MUST own its own Python 3.12 runtime; customers MUST NOT be required to
install Homebrew or any other Python prerequisite. **Locked as D-27 in
`docs/DECISIONS.md`.**

## P-026 — three coordinated changes

1. **Build-time vendor (`build_pkg.sh::step_4i_stage_python_runtime`).**
   Operator populates `${HOME}/MiningGuardian-vendor/python-runtime/` once
   per build host with python-build-standalone (Astral's relocatable CPython
   tarballs, `install_only_stripped` for `aarch64-apple-darwin`, Python
   3.12.x). Step 4i validates: vendor dir exists; `python3.12` binary
   present (accepts both flat `bin/python3.12` and framework
   `Python.framework/Versions/3.12/bin/python3.12` layouts); binary is
   Mach-O; reports Python 3.12.x; `import venv` succeeds; rsync into
   `<payload>/runtime/python/` preserves layout exactly; post-rsync sanity
   probe. Any failure exits 43 with self-pointing log line. The bulk
   runtime rsync at step 4c excludes `python-runtime/` so step 4i is the
   single owner of the python tree.

2. **Codesign (`build_pkg.sh::step_4b_codesign_inner_binaries`).** No new
   code path — the existing recursive `find $runtime_dir` Mach-O walk
   picks up every binary under `<payload>/runtime/python/` automatically
   (the `python3.12` binary itself, every `.so` extension, any `.dylib`
   shipped with the framework). Each gets re-signed with Developer ID
   Application + hardened runtime + secure timestamp. The
   `Python.framework` alternate layout is caught by Pass 1 (.framework
   as a unit, `--deep` re-seal).

3. **Install-time consume (`postinstall.sh::step_create_venv`).** Resolves
   the packaged interpreter FIRST: Tier 1 = `${MG_PKG_PAYLOAD}/runtime/python/bin/python3.12`
   (flat) OR `${MG_PKG_PAYLOAD}/runtime/python/Python.framework/Versions/3.12/bin/python3.12`
   (framework); Tier 2 (dev / smoke-test fallback only) = Homebrew + PATH,
   logged as `WARN`. Sanity-checks Python 3.12.x (refuses 3.11/3.13 — the
   cp312 wheelhouse would not match). New error string on miss points at
   `build_pkg.sh::step_4i_stage_python_runtime` and
   `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B".

## Tradeoff

P-026 is a complete source fix + build guardrail. It does NOT ship a
usable .pkg until the operator runs Block Pre-B once on the build host
to populate `${HOME}/MiningGuardian-vendor/python-runtime/`. Until then,
`make pkg` exits 43 at step 4i. Deliberately favors a hard build failure
over a notarization round-trip on a half-broken .pkg.

## Tests

All 22 installer suites green. New `tests/installer/test_postinstall_python_runtime.sh`
(29 assertions). `tests/installer/test_postinstall_venv.sh` extended with
§9 + §10 (P-026 coverage); shellcheck baseline bumped 3→5 (postinstall) +
5→6 (build_pkg.sh).

## Operator next steps

1. Mac mini cleanup (Round 9 left state on disk):

   ```bash
   sudo /bin/launchctl bootout system /Library/LaunchDaemons/com.miningguardian.*.plist 2>/dev/null || true
   sudo rm -rf "/Library/Application Support/MiningGuardian"
   sudo rm -rf /var/log/mining-guardian
   sudo -u miningguardian /usr/local/bin/colima stop --force 2>/dev/null || true
   sudo -u miningguardian /usr/local/bin/colima delete --force 2>/dev/null || true
   ```

2. Merge this PR.

3. On the build host, run `docs/RUNBOOK_PKG_REBUILD.md` "Block Pre-B"
   once to populate `${HOME}/MiningGuardian-vendor/python-runtime/`.

4. Re-run Block Pre-A's `pip download` against the newly-vendored
   interpreter (so wheel ABI tags match exactly):

   ```zsh
   "${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12" -m pip download \
       --only-binary=:all: --platform macosx_11_0_arm64 \
       --python-version 3.12 --implementation cp --abi cp312 \
       -d "${HOME}/MiningGuardian-vendor/python-wheels" \
       -r installer/macos-pkg/payload-requirements.txt
   ```

5. `make pkg` from merged main.

6. Reinstall on Mac mini. Expected new log lines:

   ```text
   [postinstall] INFO using installer-owned Python interpreter (packaged-flat): /Library/Application Support/MiningGuardian/runtime/python/bin/python3.12 (Python 3.12.x)
   [postinstall] INFO created venv at /Library/Application Support/MiningGuardian/venv
   [postinstall] INFO venv ready at /Library/Application Support/MiningGuardian/venv (NN requirement lines installed)
   ```

