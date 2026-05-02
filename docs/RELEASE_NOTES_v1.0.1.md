# Mining Guardian v1.0.1

**Release date:** 2026-05-01
**Build SHA:** _stamped at build time by_ `installer/macos-pkg/scripts/build_pkg.sh`
**Distribution:** Private GitHub Release + USB stick fallback (no public registry, no cloud-only dependencies)

---

## What this release is

A **release-blocker hotfix** on top of v1.0.0. v1.0.0 failed to install on macOS 26 (Tahoe) with the dialog *"This package is incompatible with this version of macOS"* — the installer was rejected by the signed-system-volume (SSV) write protections before any payload was extracted. v1.0.1 fixes that and ships two cosmetic / consistency fixes alongside.

Bitcoin SHA-256 miners only. Local-only by design.

---

## Fixes (3)

### B-13 — Tahoe SSV release blocker (🚨 the headline)

**Symptom (v1.0.0):** Customer double-clicks the .pkg on a Mac running macOS 26.4.1 Tahoe, walks through Welcome → License → Installation Type → enters their administrator password, then immediately hits the dialog *"This package is incompatible with this version of macOS."* No payload is extracted, no LaunchDaemons load, no install fragments are left behind on disk. (See `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` row B-13 for the forensic capture from 2026-05-01 16:04 PDT.)

**Root cause:** The v1.0.0 .pkg was built with `--install-location "/"` and a payload structured as `payload/MiningGuardian/...` and `payload/migrations/...`. On extraction this would have written `/MiningGuardian/` and `/migrations/` directly at the system-volume root, which Tahoe's SSV blocks. Compounding this, `postinstall.sh` hardcoded `/usr/local/MiningGuardian` as the install root — a path that on Tahoe is a firmlink from the data volume and works at a shell prompt with sudo, but is not an Apple-blessed install-location target for notarized .pkg files.

**Fix (v1.0.1):**

- `installer/macos-pkg/scripts/build_pkg.sh` — `--install-location` is now `/Library/Application Support/MiningGuardian` (Apple HIG-compliant, writable on the data volume, universally accepted by SSV). The payload root no longer wraps in a `MiningGuardian/` directory; files lay down directly at the install location.
- `installer/macos-pkg/scripts/postinstall.sh` — `MG_INSTALL_ROOT` and the baseline-scan paths now reference `/Library/Application Support/MiningGuardian`.
- All 9 LaunchDaemon plists updated to the new path (8 in `installer/macos-pkg/resources/launchd/`, 1 in `deploy/`).
- All 9 launcher wrappers updated.
- `scripts/setup.sh` — manual install path now matches the .pkg path so both install routes converge on the same `MG_INSTALL_ROOT`.
- `scripts/install_grafana_provisioning.sh`, `scripts/restore_from_snapshot.sh` — same path update.
- Customer-facing copy in `welcome.html`, `conclusion.html`, `license.txt`, `DEPLOYMENT_CHECKLIST.md`, `docs/RUNBOOK_BUCKET_6E_SANDBOX_TEST.md`, and `installer/macos-pkg/resources/launchd/README.md` — same path update.

### B-12 — Dark-mode rendering on the installer Welcome and Conclusion screens

**Symptom (v1.0.0):** When the host Mac is set to dark appearance and the .pkg is opened, Installer.app's WebKit auto-inverts unstyled surfaces. The hero sidebar branding (shield + pickaxes + Bitcoin coin + MINING GUARDIAN wordmark) collapses to dark gray text-only, and the inline code chips (`/Library/Application Support/MiningGuardian`, `127.0.0.1:5432`, `llama3.2:3b`) render as solid black rectangles. Body copy is readable but the install feels broken at first glance.

**Root cause:** `welcome.html` and `conclusion.html` both lacked a `color-scheme` declaration and a `prefers-color-scheme: dark` media-query override. Installer.app's WebKit honored the host's dark appearance and clobbered the brand palette.

**Fix (v1.0.1):**

- Added `<meta name="color-scheme" content="light only">` to both files.
- Added `:root, html { color-scheme: light only; }` at the top of each stylesheet.
- Added an explicit `@media (prefers-color-scheme: dark)` block that re-asserts every brand color literal with `!important` as belt-and-suspenders.
- Set `background: #FFFFFF !important` on `html, body` so the page never goes transparent over a dark host.

Tested in both light and dark host appearance on macOS 26.4.1 — both render identically.

### B-11 — Welcome copy claimed `llama3.2:3b` but `setup.sh` always installed `qwen2.5:14b`

**Symptom (v1.0.0):** The .pkg Welcome screen tells the operator the model is selected from RAM tier (16 GB → `llama3.2:3b`, 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`), matching locked decision D-13. But `scripts/setup.sh` ignored RAM and force-pulled `qwen2.5:14b-instruct-q4_K_M` on every Mac including 16 GB tier. The two install paths disagreed.

**Root cause:** `phase_08_ollama` in `scripts/setup.sh` was written before D-13 was locked; it never got the RAM-tier branching the .pkg path's `installer/macos-pkg/scripts/lib/detect_ram.sh` already implements.

**Fix (v1.0.1):** `phase_08_ollama` now reads `sysctl -n hw.memsize` and selects `qwen2.5:14b-instruct-q4_K_M` for ≥24 GB, `llama3.2:3b` otherwise, matching `detect_ram.sh` exactly. The selected model is exported as `MG_INSTALL_LLM_MODEL` so the Slack confirmation message and the install receipt agree. Customer Welcome copy needs no change — it was already correct against D-13.

---

## Out of scope for this release

The May 1 install attempt logged backlog items B-1 through B-13. Of those, **B-11, B-12, B-13 ship in v1.0.1**. The remaining items remain open and will be triaged separately:

- B-1 — APFS-naive disk pre-flight (false-negative at 36 GB free)
- B-2 — Phase 2 customer-info UX is unusable raw `read` prompts
- B-3 — `.pkg` vs `setup.sh` choice is not surfaced
- B-4 — Xcode CLT manual install required mid-install
- B-5 — GitHub auth wall (resolved this session via public repo, doc-only follow-up)
- B-6 — Tahoe auto-update mid-install drag
- B-7 — `--dry-run-install` doesn't skip Phase 2 prompts
- B-8 — dry-run requires sudo
- B-9 — Catalog count drift (313 vs 320)
- B-10 — Runbook says `bash setup.sh` but it's `#!/bin/zsh`

See `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` for the full forensic record of each.

---

## Build + install commands

Build (operator's Mac, must have Apple Developer cert + `~/MiningGuardian-vendor/`):

```bash
cd ~/code/Mining-Guardian
git checkout main
git pull
./installer/macos-pkg/scripts/build_pkg.sh
# Output: build/MiningGuardian-1.0.1-<sha>.pkg
```

Install (customer's Mac, requires admin password):

```bash
sudo installer -pkg MiningGuardian-1.0.1-<sha>.pkg -target /
# Or just double-click in Finder.
```

Uninstall:

```bash
sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh
```

---

## Verification

After install, the operator should see:

```bash
ls -ld "/Library/Application Support/MiningGuardian"
#  drwxr-xr-x  ... root  staff  ...

sudo launchctl print system/com.miningguardian.scanner | head -5
#  service = scanner
#  state = running

ls /Library/Application\ Support/MiningGuardian/logs/
#  scanner.out.log  dashboard_api.out.log  ...
```

---

**Mining Guardian — Bitcoin SHA-256 fleet observability, on your hardware, on your terms.**
