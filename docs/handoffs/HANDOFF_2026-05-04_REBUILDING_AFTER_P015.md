# Mining Guardian v1.0.3 — Rebuilding After P-015 (Mini Install Round 2)

```yaml
date: 2026-05-04
session_id: manual (post-P-015 — package rebuild in progress on operator laptop, no successful Mini install yet)
last_commit_on_main: cf1691e — fix(installer): D-18 P-015 make preinstall arch gate Rosetta-safe
agent: Computer (autonomous agent)
repo: Mining-Guardian
scope: installer / Mac Mini install only — docs-only snapshot while `make pkg` runs
```

This file is a docs-only snapshot of where the v1.0.3 install effort sits while
Rob waits for `make pkg` to finish on his laptop after merging P-015. It is
intentionally a checkpoint, not a new feature plan.

The two earlier handoffs from today —
`docs/handoffs/HANDOFF_2026-05-04.md` (post-P-009 EOD) and
`docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md` (post-P-012,
before the first `sudo installer` run) — are still valid as historical context.
This file picks up where that second one ended.

The release-notes file `docs/RELEASE_NOTES_v1.0.3.md` already contains the full
P-013 / P-014 / P-015 root-cause and fix narratives. This handoff does NOT
duplicate them — it captures the live install timeline that has played out
across `a35728d → 46761f1 → 2b48f98 → cf1691e` and gives the operator a
copy-pasteable resume path for the next install attempt.

---

## Where the Mini actually is right now

- **Mini hardware:** Apple Silicon (M-series). Confirmed 2026-05-04 by the
  operator running, on the Mini, the diagnostic from the P-015 PR description:

  ```
  uname -m                                      # arm64
  sysctl -n hw.optional.arm64                   # 1
  sysctl -n sysctl.proc_translated              # 0 (or 1 if Terminal launched under Rosetta)
  ```

  This is the canonical evidence that the Mini is M-series — it overrules any
  contrary reading from `uname -m` alone, which is the exact bug P-015 fixed.

- **Install state:** payload-only carryover from `a35728d` was manually cleaned
  on 2026-05-04 (see "Cleanup that already happened" below). The most recent
  install attempt was the `2b48f98` build, which DID run preinstall (proving
  P-013 + P-014 worked) but hard-failed inside `gate_apple_silicon` because the
  preinstall in that build still used `uname -m` instead of
  `sysctl hw.optional.arm64`. P-015 (`cf1691e`) is the fix.

- **Postinstall has NEVER run successfully on this Mini.** No `.env`, no `venv`,
  no Postgres container, no LaunchDaemons, no scheduled jobs, no
  `bin/uninstall.sh`. Do not claim, log, or report otherwise.

- **What is on disk on the Mini right now (expected — NOT a successful install):**
  - `/var/log/mining-guardian/install-preinstall.log` from the `2b48f98`
    failed-preinstall attempt. Contains the FATAL exit-12 line referenced in
    the P-015 root cause.
  - The `/var/log/mining-guardian/` directory itself MAY remain after cleanup —
    that is fine; preinstall in `cf1691e` is idempotent on log-dir creation.
  - Everything under `/Library/Application Support/MiningGuardian` from the
    earlier payload-only install was removed during cleanup.
  - No `/etc/mining-guardian/install-receipt.json`. Confirmed absent.
  - No `pkgutil` receipt for `com.miningguardian.installer.core`. Confirmed
    absent (`pkgutil --pkgs | grep -i miningguardian` returns nothing).

---

## The four-step live timeline since PR #129

This section is the chronological story of today's installer attempts so the
next session does not have to reconstruct it from PRs:

### Step 1 — `a35728d` (P-012 build) installed payload-only

`MiningGuardian-1.0.3-a35728dcfc8c.pkg` installed on the Mini. Apple-confirmed
"install completed" dialog, BUILD_STAMP.json wrote v1.0.3, but ZERO postinstall
artifacts. `/var/log/install.log` showed PackageKit extracted the payload + wrote
the receipt + logged "Installed Mining Guardian (1.0.3)" but ZERO
preinstall/postinstall script execution lines. Root cause: pkgbuild scripts were
staged as `preinstall.sh` / `postinstall.sh` (with `.sh`); PackageKit only
honors extensionless `preinstall` / `postinstall`. Fix: PR #130 (P-013).

### Step 2 — manual Mini cleanup (between Step 1 and Step 3)

The operator manually cleaned the payload-only install on the Mini:

```
sudo pkgutil --forget com.miningguardian.installer.core    # idempotent
pkgutil --pkgs | grep -i miningguardian                    # confirmed empty
sudo rm -rf "/Library/Application Support/MiningGuardian"
sudo rm -rf /var/log/mining-guardian /etc/mining-guardian
ls -la "/Library/Application Support/MiningGuardian" 2>&1  # No such file or directory
```

After this, the Mini was clean from the operating system's point of view —
no payload, no receipt, no install root, no log dir, no `/etc/mining-guardian`.
The `2b48f98` install in Step 4 below proceeded against this clean state.

### Step 3 — `46761f1` (P-013 build) failed safely at the leftover-`*.sh` guard

First `make pkg` after PR #130 merged aborted at the new P-013
belt-and-suspenders guard with:

```
[build_pkg] step 4d FAIL: leftover top-level *.sh in scripts staging dir:
  /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/stage/scripts/build_pkg.sh
[build_pkg] FATAL (43) step 4d: top-level *.sh files in .../build/stage/scripts after rename
```

This was the guard catching a regression — `build_pkg.sh` lived in the same
source dir as `preinstall.sh` / `postinstall.sh` and was being rsync'd into the
package-script staging dir. No .pkg was produced, no Apple notarization
round-trip was burned. Fix: PR #131 (P-014) added `--exclude 'build_pkg.sh'`
to the step 4d rsync.

### Step 4 — `2b48f98` (P-014 build) installed; preinstall ran; arch gate failed

`MiningGuardian-1.0.3-2b48f98e6b77.pkg` was built, signed, notarized, and
stapled successfully on the laptop. Transferred to the Mini by `scp`; local
SHA-256 sidecar created on the Mini and verified; `spctl --assess --type install`
accepted the package; the operator's pre-filled
`~/Desktop/MiningGuardian.conf` was still on the Desktop and still valid (per
the B-2 schema in `installer/macos-pkg/resources/MiningGuardian.conf.template`).

The `sudo installer -pkg ... -target /` run THIS time DID execute the scripts
(the P-013 + P-014 fixes worked). The preinstall hard-failed inside
`gate_apple_silicon` with `FATAL (12) this build supports Apple Silicon (arm64)
only; detected 'x86_64'`. Postinstall never ran. The detailed log is at
`/var/log/mining-guardian/install-preinstall.log` on the Mini.

The hardware is Apple Silicon (proven in Step 0 above). The bug was that
`gate_apple_silicon` used `/usr/bin/uname -m`, which reports the architecture of
the CALLING process — and Installer.app was spawning the preinstall under a
Rosetta-translated `/bin/bash` (Terminal.app set to "Open using Rosetta", or the
sudo invocation translated). The kernel-authoritative
`sysctl hw.optional.arm64` was always `1` on this hardware. Fix: PR #132 (P-015).

### Step 5 — `cf1691e` (P-015 build) — IN PROGRESS as this handoff is written

P-015 merged. Rob pulled `cf1691e` on the laptop. `make pkg` is running. The
expected output is `MiningGuardian-1.0.3-cf1691e2998c.pkg` (build-stamp short
SHA = `cf1691e2998c`).

**No install has been attempted from `cf1691e` yet at the time this handoff is
committed.** Do not claim otherwise. Do not edit this handoff to claim
otherwise — write a successor handoff once the install has actually run and
been verified.

---

## Operator resume — exact steps after `make pkg` finishes

These steps assume Rob is at his laptop and the build just finished. Each step
is verified-as-it-goes; do not run multiple steps without checking the
intermediate state.

### Step A — verify the laptop build artifact

On the laptop, in `/Users/BigBobby/Documents/GitHub/Mining-Guardian/`:

```
ls -lh build/MiningGuardian-1.0.3-*.pkg build/MiningGuardian-1.0.3-*.pkg.sha256
git log -1 --format=%h    # must be cf1691e (or newer if more PRs merged)
shasum -a 256 build/MiningGuardian-1.0.3-cf1691e*.pkg
diff <(awk '{print $1}' build/MiningGuardian-1.0.3-cf1691e*.pkg.sha256) \
     <(shasum -a 256 build/MiningGuardian-1.0.3-cf1691e*.pkg | awk '{print $1}')
```

The diff must be empty. The filename suffix on disk should be the short SHA of
the build commit. If it is anything other than `cf1691e2998c` — STOP and figure
out why before transferring to the Mini.

Optional sanity probe (catches a Step-4d regression of the kind P-013/P-014
were chasing) — expand the .pkg and confirm the Scripts archive has
extensionless `preinstall` and `postinstall`:

```
pkgutil --expand build/MiningGuardian-1.0.3-cf1691e*.pkg /tmp/mg-pkg-check
ls /tmp/mg-pkg-check/core.pkg/Scripts/
# MUST show:    preinstall  postinstall  lib/  resign_wheel.py
# MUST NOT show: preinstall.sh  postinstall.sh  build_pkg.sh
rm -rf /tmp/mg-pkg-check
```

### Step B — transfer to the Mini

Use `scp` (the path the previous transfers used). USB and AirDrop are also
fine; the choice is operator's. Examples assume the Mini is reachable at its
Tailscale name `mac-mini` or its LAN IP — substitute whichever the operator
is using.

```
# From the laptop:
scp build/MiningGuardian-1.0.3-cf1691e*.pkg \
    build/MiningGuardian-1.0.3-cf1691e*.pkg.sha256 \
    BigBobby@mac-mini:~/Downloads/
```

### Step C — verify on the Mini before installing

On the Mini:

```
cd ~/Downloads
ls -lh MiningGuardian-1.0.3-cf1691e*.pkg MiningGuardian-1.0.3-cf1691e*.pkg.sha256
shasum -a 256 MiningGuardian-1.0.3-cf1691e*.pkg
# Compare the printed hash to the one inside the .sha256 sidecar:
cat MiningGuardian-1.0.3-cf1691e*.pkg.sha256
spctl --assess --type install MiningGuardian-1.0.3-cf1691e*.pkg
# Expected: accepted
#           source=Notarized Developer ID
#           origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
pkgutil --check-signature MiningGuardian-1.0.3-cf1691e*.pkg
# Expected: status: signed by a developer certificate issued by Apple
```

If any of those three checks (sha256 match, spctl accepted, pkgutil signed)
fails — STOP. Do not run `sudo installer`. Investigate first.

### Step D — confirm Desktop conf is still in place and valid

```
ls -l "/Users/$USER/Desktop/MiningGuardian.conf"
head -20 "/Users/$USER/Desktop/MiningGuardian.conf"   # confirm the keys, never paste secrets into chat
```

The conf has been on the Desktop since the `2b48f98` round; the contents have
not been edited and still match the v1.0.3 B-2 schema. If by accident it has
been moved or edited since the prior attempt, copy a fresh template from
`installer/macos-pkg/resources/MiningGuardian.conf.template` and re-fill it
before installing.

### Step E — clean up the failed-preinstall log (optional, recommended)

The previous `2b48f98` attempt left `/var/log/mining-guardian/install-preinstall.log`
on the Mini. The new install will append, so the FATAL line from the prior
attempt will still be in the file. To make the next log read clean:

```
sudo rm -f /var/log/mining-guardian/install-preinstall.log
```

This is the same line that appears in the P-015 PR description ("Operator
commands after merge"). Skipping this step is harmless — it just leaves the
old FATAL line above the new run's lines.

The directory itself (`/var/log/mining-guardian/`) does not need to be removed;
the cf1691e preinstall recreates it idempotently.

### Step F — install

```
sudo installer -pkg "$HOME/Downloads/MiningGuardian-1.0.3-cf1691e*.pkg" -target /
```

Rob asked for screenshots at every screen on this run. Take them. Pause if
anything looks wrong.

### Step G — verify preinstall actually fired AND the arch gate accepted M-series

After the installer dialog finishes (whether it shows success or a Cocoa
dialog from an inner script), the FIRST thing to read is the preinstall log:

```
sudo cat /var/log/mining-guardian/install-preinstall.log
```

Expected sequence on a successful run on this Mini:

```
[preinstall] OK gate_root: running as root
[preinstall] OK gate_macos_version: <ver> >= 13.0
[preinstall] OK gate_apple_silicon: hw.optional.arm64=1 …
   (and possibly: WARN proc_translated=1 — fine, install proceeds)
[preinstall] OK gate_disk_space …
[preinstall] OK gate_ports …
[preinstall] OK gate_install_root_writable …
[preinstall] preinstall complete
```

The line that proves P-015 worked is the
`OK gate_apple_silicon: hw.optional.arm64=1` line. **If you see
`FATAL (12) this build supports Apple Silicon (arm64) only` again on this Mac
mini, the rebuild did NOT include the P-015 fix — STOP, do not retry, capture
the build SHA the .pkg actually shipped from, and verify that the laptop was
actually on `cf1691e` (or newer) when `make pkg` ran.**

### Step H — verify postinstall artifacts

If preinstall passed, postinstall should have run end-to-end. Check:

```
sudo cat /var/log/mining-guardian/install-postinstall.log
ls -la /etc/mining-guardian/install-receipt.json
ls -la /Library/Application\ Support/MiningGuardian/
ls -la /Library/Application\ Support/MiningGuardian/bin/uninstall.sh
launchctl list | grep com.miningguardian. | grep -v scheduled    # expect 10 lines
launchctl list | grep com.miningguardian.scheduled.              # expect 11 lines
```

The verification gates in `docs/RELEASE_NOTES_v1.0.3.md` ("Build & verification
gates (still required)") are the canonical pass criteria — including the
`SELECT count(*) FROM hardware.miner_models;` returning 320, the operator
console at `http://127.0.0.1:8787/`, and the welcome/conclusion HTML strings.
Walk that list verbatim. Do not skip steps.

---

## Cleanup that already happened (read-only reference)

Captured for paper-trail. Do not re-run any of these on the Mini before the
next install — the Mini has already been cleaned to this state, and re-running
them on top of a successful install would tear the install down.

```
sudo pkgutil --forget com.miningguardian.installer.core
pkgutil --pkgs | grep -i miningguardian              # empty
sudo rm -rf "/Library/Application Support/MiningGuardian"
sudo rm -rf /var/log/mining-guardian /etc/mining-guardian
ls -la "/Library/Application Support/MiningGuardian" 2>&1
   # ls: ...: No such file or directory  (the expected response)
```

These were performed manually by the operator between the `a35728d`
payload-only install (Step 1) and the `2b48f98` preinstall-failure install
(Step 4). The current Mini state is "post-cleanup, plus one failed preinstall
log file in `/var/log/mining-guardian/`". Step E above optionally clears that
log file; everything else is already gone.

---

## What is NOT in scope for this handoff

- Grafana provisioning (Gap 3, row 4 of `docs/MG_UNIFIED_TODO_LIST.md`).
  Deferred per operator instruction 2026-05-04.
- Cloudflare Tunnel + Access auto-provisioning (D-19 step 5, row 9).
  Deferred per same instruction.
- VPS decommission + ROBS-PC container shutdown (rows 14, 11-13 chain). Only
  fires AFTER the Mini is verified green per D-16 + D-18.
- Source code changes. This handoff is docs-only.
- Secrets. None of the values in `MiningGuardian.conf`, `.env`, the
  Postgres password, or the Apple notarization keys appear here.

---

## Cross-references

- `docs/RELEASE_NOTES_v1.0.3.md` — full P-001 .. P-015 narrative with PR
  cross-links and merge SHAs. Sections P-013, P-014, P-015 cover the script
  naming, `build_pkg.sh` exclude, and arch-gate-Rosetta fixes respectively.
  This handoff intentionally does not duplicate the root-cause analyses there.
- `docs/MG_UNIFIED_TODO_LIST.md` rows 10e (P-013), 10f (P-014), 10g (P-015) —
  flipped 🔴 → ✅ in the same commits as their PRs. Rows 11 (build/sign/
  notarize), 12 (clean-VM smoke test), 13 (install on Mini), 14 (VPS
  decommission) remain 🔴 — the v1.0.3 .pkg has been built three times now
  (`a35728d`, `2b48f98`, and currently rebuilding from `cf1691e`), and the
  Mini install gate (row 13) is still open until the cf1691e build verifies
  green on the Mini.
- `docs/handoffs/HANDOFF_2026-05-04.md` — D-15 EOD handoff after P-009
  merged. The "what's next on the laptop" section there is the predecessor
  to this file's "Operator resume" section.
- `docs/handoffs/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md` — paused
  state before the very first `sudo installer` run from the `a35728d` build.
- `docs/RUNBOOK_PKG_REBUILD.md` — paste-along blocks for the build, including
  the wheelhouse pre-A block (P-010) and the rebuild Block-Cleanup that the
  Mini Step 2 cleanup above mirrored.
- `docs/CONSOLE_OPERATIONS_GUIDE.md` — D-19 console verification surface;
  used in Step H above.
- `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` — the audit that
  authorized the v1.0.3 train.

---

## Successor-handoff trigger

The next session ends — successfully or not — with a successor handoff. If the
`cf1691e` install on the Mini lands clean per Step H, that handoff is the
"Mini install complete, verifying green" doc; it is the last installer-train
handoff before D-16 + D-18 verification can authorize the VPS decommission.
If the install fails again, the successor handoff captures the new failure
mode and points at the P-016 PR that fixes it.

Either way, do not edit THIS file after `cf1691e` is installed — write a
successor.
