# Mining Guardian v1.0.3 — Night Pause After Postinstall Failure

```yaml
date: 2026-05-04
session_id: manual (Mac mini install round 2 — paused at night, postinstall log not yet read)
last_commit_on_main: 2f0861b — docs(v103): rebuilding-after-P-015 handoff for Mini install round 2
build_source_commit: cf1691e2998c — fix(installer): D-18 P-015 make preinstall arch gate Rosetta-safe
agent: Computer (autonomous agent)
repo: Mining-Guardian
scope: installer / Mac Mini install only — docs-only night pause; no source/build script changes
```

This file is a docs-only checkpoint. Rob is going to bed. The latest corrected
v1.0.3 package built from `cf1691e` was transferred to the Mac mini, passed
checksum + Gatekeeper, ran preinstall successfully with the new P-015 Rosetta-
safe arch gate, then the installer failed during the package-scripts phase.
The postinstall log was **not** read before pausing. The next session must
start by reading that log — do not rerun anything until the failure is known.

The earlier handoffs from today —
`docs/handoffs/HANDOFF_2026-05-04.md` (post-P-009 EOD),
`docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md` (post-P-012,
before the first `sudo installer` run), and
`docs/handoffs/HANDOFF_2026-05-04_REBUILDING_AFTER_P015.md` (waiting on the
P-015 rebuild) — remain valid as historical context. This file picks up where
the third one ended and captures the round-2 install attempt outcome.

The release-notes file `docs/RELEASE_NOTES_v1.0.3.md` already contains the
P-013 / P-014 / P-015 root-cause and fix narratives. This handoff does NOT
duplicate them. It captures the live install timeline through `cf1691e` and
gives the next session a copy-pasteable resume path that begins at the log.

---

## Standing rules from Rob (carry forward)

- Over-document everything so future sessions have a reference point.
- Go slow and do it right; no shortcuts.
- Ask questions only when needed, and document Rob's answers.
- This workstream is only about the installer and installing on the new Mac mini.
- Do not fix Grafana right now.
- Do not rush the install.

---

## Very important next-session warning

Do **not** rerun the installer.

Do **not** uninstall.

Do **not** clean `/Library/Application Support/MiningGuardian`,
`/var/log/mining-guardian`, or `/etc/mining-guardian`.

The next session must start by reading the postinstall log to determine
exactly why the latest install failed. Do not change source or build scripts
in this PR — diagnosis first, P-016 (or whatever it gets called) lands as its
own fix PR.

---

## Latest package (round 2)

The most recent package built and transferred to the Mac mini is:

```text
MiningGuardian-1.0.3-cf1691e2998c.pkg
```

Built from source commit:

```text
cf1691e2998c00f4392cade3da49edf0adcf2129
```

Build-Mac package path:

```text
/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-cf1691e2998c.pkg
```

Build-Mac SHA sidecar:

```text
/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256
```

Mac mini package path:

```text
/Users/miningguardian/Downloads/MiningGuardian-1.0.3-cf1691e2998c.pkg
```

Mac mini local checksum file created:

```text
/Users/miningguardian/Downloads/MINI-MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256
```

---

## Latest build result (recap)

The `cf1691e` package build succeeded.

Important successful build lines:

```text
[build_pkg] step 4d OK: scripts staged as preinstall/postinstall (extensionless, executable) — P-013
pkgbuild: Adding top-level preinstall script
pkgbuild: Adding top-level postinstall script
[resign_wheel] summary: 108 wheel(s) processed — 168 Mach-O signed, 168 RECORD line(s) rewritten, 75 pure-Python wheel(s) skipped, 0 failure(s)
status: Accepted
The staple and validate action worked!
source=Notarized Developer ID
origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
```

Final build output:

```text
Version:    1.0.3
Git SHA:    cf1691e2998c
Pkg:        /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-cf1691e2998c.pkg
SHA-256:    /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256
```

Apple notary submission ID:

```text
d6682014-2c43-4510-99e1-0014993213d9
```

---

## Transfer and verification on the Mac mini

Transferred over SCP to:

```text
miningguardian@100.69.66.32:~/Downloads/
```

Transfer completed:

```text
MiningGuardian-1.0.3-cf1691e2998c.pkg          100% 493MB
MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256   100% 159
```

Because the `.sha256` sidecar references the laptop build path, a Mac-mini-
local SHA file was created:

```bash
cd ~/Downloads
shasum -a 256 MiningGuardian-1.0.3-cf1691e2998c.pkg > MINI-MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256
shasum -a 256 -c MINI-MiningGuardian-1.0.3-cf1691e2998c.pkg.sha256
```

Result:

```text
MiningGuardian-1.0.3-cf1691e2998c.pkg: OK
```

Gatekeeper check on the Mac mini:

```bash
spctl --assess --type install -vv MiningGuardian-1.0.3-cf1691e2998c.pkg
```

Result:

```text
MiningGuardian-1.0.3-cf1691e2998c.pkg: accepted
source=Notarized Developer ID
origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
```

---

## Desktop config file

The Desktop config file exists and permissions are correct:

```bash
ls -l ~/Desktop/MiningGuardian.conf
```

Result:

```text
-rw-------  1 miningguardian  staff  583 May  4 10:22 /Users/miningguardian/Desktop/MiningGuardian.conf
```

Earlier all seven config shape checks passed:

```text
OK webhook
OK bot token
OK workspace id
OK email
OK customer name
OK approvers
OK dry-run
```

**Do not print the file contents** unless absolutely required. It contains
secrets (Slack bot token, webhook, customer info).

---

## Installation attempt with the cf1691e package

Command run on the Mac mini:

```bash
sudo installer -pkg "MiningGuardian-1.0.3-cf1691e2998c.pkg" -target /
```

Installer output:

```text
installer: Package name is Mining Guardian
installer: Installing at base path /
installer: The install failed. (The Installer encountered an error that caused the installation to fail. Contact the software manufacturer for assistance. An error occurred while running scripts from the package "MiningGuardian-1.0.3-cf1691e2998c.pkg".)
```

This explicit "running scripts from the package" wording means PackageKit
got past payload extraction and into the package-scripts phase, then a
script failed.

---

## Preinstall result (NEW evidence — P-015 confirmed working)

The old failed preinstall log (from the `2b48f98` round-1 attempt) was cleared
before this attempt:

```bash
sudo rm -f /var/log/mining-guardian/install-preinstall.log
```

The new preinstall log was read after the cf1691e attempt:

```bash
sudo cat /var/log/mining-guardian/install-preinstall.log
```

Important result: **preinstall passed, all gates green.**

Preinstall log excerpt (verbatim):

```text
2026-05-04T23:48:43Z [preinstall] Mining Guardian preinstall starting (pid=5432)
2026-05-04T23:48:43Z [preinstall] Installer payload: /private/tmp/PKInstallSandbox.cpbk65/Scripts/com.miningguardian.installer.core.GcDjGb
2026-05-04T23:48:43Z [preinstall] Target volume: /
2026-05-04T23:48:43Z [preinstall] OK gate_root: running as root
2026-05-04T23:48:43Z [preinstall] OK gate_macos_version: 26.4.1 >= 13.0
2026-05-04T23:48:43Z [preinstall] gate_apple_silicon probes: hw.optional.arm64='1' (rc=0) sysctl.proc_translated='1' (rc=0) uname -m='x86_64'
2026-05-04T23:48:43Z [preinstall] WARN gate_apple_silicon: preinstall is running under Rosetta 2 translation (sysctl.proc_translated=1); hardware is Apple Silicon so install will proceed
2026-05-04T23:48:43Z [preinstall] OK gate_apple_silicon: hw.optional.arm64=1 (Apple Silicon hardware confirmed; uname -m='x86_64')
2026-05-04T23:48:43Z [detect_ram] INFO RAM=16GB → model=llama3.2:3b (fallback=no)
2026-05-04T23:48:43Z [preinstall] OK gate_ram: 16 GB >= 16 GB; model=llama3.2:3b
2026-05-04T23:48:43Z [preinstall] OK gate_free_disk: 30 GB free >= 20 GB
2026-05-04T23:48:43Z [preinstall] OK gate_applications_writable
2026-05-04T23:48:43Z [preinstall] OK gate_no_conflict: clean host
2026-05-04T23:48:43Z [preinstall] All preinstall gates passed; handing off to Installer.app payload phase
```

Therefore P-015 worked end-to-end on the live Mac mini: the kernel-authoritative
`sysctl hw.optional.arm64=1` reading correctly accepted the host as Apple
Silicon even though the preinstall process itself was running under Rosetta
2 translation (`sysctl.proc_translated=1`, `uname -m=x86_64`). The Rosetta
context is logged as a WARN line for diagnostics; it does not block the
install. P-015's design intent and the live behavior agree.

---

## Current suspected failure location (NOT YET CONFIRMED)

Because preinstall passed and the installer still failed during the
package-scripts phase, the most likely failure location is **postinstall**
(or one of its sub-steps). The exit codes the postinstall and the build
assertions are wired to use today are documented in
`installer/macos-pkg/scripts/postinstall.sh` and the row-by-row notes in
`docs/MG_UNIFIED_TODO_LIST.md` 1.2.

That suspicion is **not yet confirmed**. The next session must read the
postinstall log first, before forming any other hypothesis.

Rob attempted on the Mac mini:

```bash
sudo ls -la /var/log/mining-guardian
```

but the terminal returned:

```text
zsh: parse error near `)'
```

That parse error was almost certainly caused by a stray pasted character on
the operator's terminal, not by the command itself. The very next step is to
re-run a clean log-directory listing.

---

## Next session — first commands (run one at a time on the Mac mini SSH session)

### Step 1 — list the log directory

```bash
sudo ls -la /var/log/mining-guardian
```

Expected: should show at least:

```text
install-preinstall.log
```

If postinstall started, it may also show:

```text
install-postinstall.log
```

Do not delete or move anything in this directory.

### Step 2 — if `install-postinstall.log` exists, read the end

```bash
sudo tail -n 120 /var/log/mining-guardian/install-postinstall.log
```

Look for the last `[postinstall] step_*` line and the FATAL/exit code that
follows. The exit codes wired into postinstall today (per `MG_UNIFIED_TODO_LIST.md`
1.2 row notes) are roughly:

- 38 — `step_create_venv` failure (Gap 5 / P-001)
- 39 — `step_provision_catalog_db_and_seed` failure (Gap 2 / P-002)
- 40 — `step_install_scheduled_plists_and_bootstrap` failure (Gap 4 / P-007)
- 41 — `step_collect_customer_info` failure (Gap 1 / P-005, Desktop conf)

Match the observed exit code against that map before forming a P-016 fix
plan. If the failure code is something else, follow the postinstall log
contents — do not guess.

### Step 3 — if no postinstall log exists, inspect macOS install log around the cf1691e attempt

```bash
sudo grep -nE 'Mining Guardian|MiningGuardian|com\.miningguardian|postinstall|preinstall|PackageKit|cf1691e' /var/log/install.log | tail -220
```

This catches the case where postinstall never started (e.g., Apple's
PackageKit rejected the script archive for a reason that bypassed both
preinstall WARN/OK and our log file).

### Step 4 — only after the logs are captured, check partial artifacts

```bash
ls -ld "/Library/Application Support/MiningGuardian" 2>&1
ls -la "/Library/Application Support/MiningGuardian" 2>/dev/null | head -50
sudo ls -la /etc/mining-guardian 2>&1
```

This tells the next session whether the payload landed and how far postinstall
got before exiting. Compare against the v1.0.3 payload shape documented in
`docs/RELEASE_NOTES_v1.0.3.md` (venv, postgres-data, bin/, logs/, etc.).

**Do not cleanup before these logs are captured.** A reset before the log is
read forfeits the only diagnostic evidence we have.

---

## Current Mini state summary

- Mac mini hardware is Apple Silicon (M-series).
- `sysctl -n hw.optional.arm64` returns `1` (kernel-authoritative).
- The Terminal/installer process is running under Rosetta 2:

  ```text
  sysctl.proc_translated='1'
  uname -m='x86_64'
  ```

- P-015 successfully handles that and lets preinstall pass.
- The cf1691e install failed after preinstall, most likely in postinstall.
- The exact postinstall failure has **not** yet been read — next session priority #1.
- Desktop `MiningGuardian.conf` exists, mode `0600`, all 7 shape checks
  previously green. Do not modify it.
- No partial-install cleanup has been performed since the failure. The
  `/Library/Application Support/MiningGuardian/`, `/var/log/mining-guardian/`,
  and `/etc/mining-guardian/` paths are in whatever state postinstall left
  them — that is intentional and is the diagnostic surface for next session.

---

## Prior resolved install blockers today (recap, in order)

### a35728d — payload-only install (silent script ignore)

The `a35728d` package installed only payload because pkgbuild scripts were
named `preinstall.sh` / `postinstall.sh`. macOS PackageKit honors only the
extensionless filenames `preinstall` / `postinstall` and silently ignored
the `.sh` variants — payload + receipt were laid down, scripts never ran.

Fixed by P-013 / PR #130.

### 46761f1 — build guard failure (build_pkg.sh in scripts staging)

After P-013, the next `make pkg` aborted at the new P-013 belt-and-suspenders
guard with `step 4d FAIL: leftover top-level *.sh in scripts staging dir:
${SCRIPTS_DIR}/build_pkg.sh`. The step 4d rsync was pulling
`installer/macos-pkg/scripts/build_pkg.sh` into the package-script staging
dir alongside `preinstall` / `postinstall`.

Fixed by P-014 / PR #131 (rsync `--exclude 'build_pkg.sh'`).

### 2b48f98 — Apple Silicon false negative under Rosetta

The `2b48f98` package successfully ran preinstall but hard-failed at
`gate_apple_silicon` with `FATAL (12) detected 'x86_64'` on a documented
M-series box. Root cause: `gate_apple_silicon` compared `uname -m` against
`arm64`. Under Rosetta-translated Terminal/Installer, `uname -m` returns
`x86_64` even on Apple Silicon hardware. The kernel-authoritative indicator
is `sysctl hw.optional.arm64`, which does not change under Rosetta.

Fixed by P-015 / PR #132 (read `sysctl -n hw.optional.arm64` first; fall
back to `uname -m` only when sysctl is unreadable; defensive — never accept
`x86_64` on no-other-evidence).

### cf1691e — current failure (postinstall, not yet read)

The `cf1691e` package:

- built successfully,
- transferred successfully to the Mac mini,
- checksum passed,
- Gatekeeper passed,
- preinstall passed (P-015 confirmed working live),
- failed later in package-scripts phase, almost certainly in postinstall.

**Exact failure still pending.** No code in the repo is being changed in
this handoff PR — diagnosis comes first.

---

## Documentation already in GitHub

Recent doc PRs already merged:

- PR #129 — paused before Mini install + onboarding UX gaps.
- PR #130 — P-013 script naming fix.
- PR #131 — P-014 exclude `build_pkg.sh` from script staging.
- PR #132 — P-015 Rosetta-safe architecture gate.
- PR #133 — rebuilding-after-P-015 handoff (waiting on `make pkg` to finish).

This handoff is the next doc PR. It captures the round-2 install timeline
(`cf1691e` build green → install failed in scripts → preinstall log read →
postinstall log not yet read → night pause).

---

## Do not do next

- Do not rerun the installer.
- Do not uninstall.
- Do not delete the install root (`/Library/Application Support/MiningGuardian/`).
- Do not delete `/var/log/mining-guardian` or any file inside it.
- Do not delete `/etc/mining-guardian` or any file inside it.
- Do not edit `.env` or the Desktop `MiningGuardian.conf`.
- Do not troubleshoot Grafana.
- Do not switch to Cloudflare or Tailscale setup.
- Do not change source files, build scripts, or notarization plumbing in
  this handoff PR. A P-016 (or equivalent) source fix is its own PR after
  the postinstall log identifies the failure.

First priority is the log:

```bash
sudo ls -la /var/log/mining-guardian
sudo tail -n 120 /var/log/mining-guardian/install-postinstall.log
```

Then decide whether a P-016 source fix is needed and open it as its own PR
off `main` (no stacked branches — Failure Mode 9 in `CLAUDE.md`).

---

## Why this is a docs-only PR

This handoff exists to lock the round-2 install state into version control
before Rob sleeps. The actual diagnostic step (reading the postinstall log)
requires a live SSH session on the Mac mini, which Rob cannot run tonight.
Capturing the state now prevents the next session from rediscovering what
worked (cf1691e build, transfer, Gatekeeper, preinstall + P-015) and what
remains unknown (the postinstall failure mode), which is exactly the
context-loss failure pattern this handoff protocol was created to prevent
(`docs/handoffs/README.md`).
