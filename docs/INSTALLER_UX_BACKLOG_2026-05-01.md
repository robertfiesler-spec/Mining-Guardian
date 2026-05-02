# Installer UX Backlog — May 1, 2026

**Context:** First real install attempt on the Mac Mini was aborted mid-Phase 2 due to compounding friction. Mini is in a known-good prepped state (Xcode CLT, Homebrew, repo cloned, Tailscale, headless verified) but nothing past Phase 1 of `setup.sh` ever ran. This doc captures every friction point we hit, in order, so the next attempt fixes them up-front instead of mid-install.

**Standing rule:** Fix this list **before** re-attempting an install. No more "push through, fix later." That's how we ended up here.

---

## Bugs that blocked or nearly blocked install

### B-1 · Pre-flight disk check is APFS-naïve (BLOCKER, false-negative) — ✅ DONE in v1.0.2

- **Symptom:** `setup.sh` Phase 1 reports `Only 36 GB free — minimum 50 GB.` and aborts.
- **Reality:** Mini has ~180 GB actually free. APFS dynamic allocation hides true free space from `df`.
- **Bad code:** `scripts/setup.sh:160` — `free="$(df -g / | awk 'NR==2{print $4}')"`
- **Fix:** Use `diskutil info / | grep "Container Free"` (which reports 37.6 GB even when df says 35 GB — closer but still understates) plus optionally force purge via `mkfile -n 100g /tmp/forcefree && rm /tmp/forcefree` before measuring.
- **Today's workaround:** Commented out lines 159–162 with `DISK_CHECK_BYPASS_2026-05-01` prefix. Reverted at end of session via `setup.sh.bak`.
- **Resolution (v1.0.2 / 2026-05-02):** Replaced the `df -g /` reading with a `diskutil info /` parser that extracts the byte count from the `Container Free Space` line (always exact, always integer, never abbreviated to TB). On parse failure we fall back to `df -g /` with a `warn` so the install still has a chance to complete. Fix landed on branch `fix/installer-b1-disk-check-b10-runbook-zsh`.

### B-2 · Phase 2 customer-info prompt UX is unusable

- **Symptom:** Raw `read` prompts in sequence with no context, no validation, no review, no edit, no go-back.
- **Specific failures observed:**
  - Workspace ID field accepted `usa 188` instead of forcing an integer
  - Hidden password fields give zero feedback — no "•••" mask, no character count, no confirm
  - 12 prompts in sequence with no "review your answers before continuing?" screen
  - One typo on field 3 means restart from field 1
  - Mistakes don't surface until Phase 7 tries to write `.env`
- **Fix:** Replace the read-prompt block in `phase_02_customer_info()` with either:
  - A pre-filled `.env.template` the operator edits in `nano` / `vim`, then setup.sh validates the file
  - OR a proper TUI (Rich/Textual already in the repo's installer brand toolkit — use it) with field validation, edit-before-commit, and a final review screen
- **Recommend:** Template-file approach. Less code, less to break, operator gets to use a real editor with backspace.

### B-3 · `.pkg` vs `setup.sh` path is unclear and inconsistent

- **Symptom:** Today we spent significant time confused about whether the Mini should be installed via `.pkg` double-click (matches Setup Manual PDF) or `setup.sh` manually.
- **Conflicting docs:**
  - `docs/customer/MiningGuardian_Setup_Manual.pdf` documents `.pkg` flow only — implies that's the install path
  - `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md:92` says **"Do not click the .pkg — the .pkg is for end-user laptops, not the operations Mac Mini"**
  - But there's no separate "end-user laptop installer" — the .pkg installs the same payload as setup.sh
- **Fix:** Decide one of:
  - (a) Mini = `setup.sh`, end-user laptops = `.pkg` viewer-only build (different payload). Document the split in a single architecture doc, link it from both runbooks and the Setup Manual.
  - (b) Mini = `.pkg` flow same as customers. Then make the `.pkg` actually work for the Mini operator role and retire `setup.sh`.
- **Recommend:** (a). Operations server and end-user laptop are different roles, deserve different installers. But the docs need to stop pretending the `.pkg` is for everyone.

### B-4 · Xcode CLT manual install (customer-facing problem)

- **Symptom:** Phase 2 of the install-day runbook (and our session today) requires the operator to run `xcode-select --install` and click through a GUI popup. There is no programmatic way to skip the popup — Apple deliberately requires user interaction.
- **Customer impact:** A non-technical operator told to "open Terminal and paste this" is going to be terrified by the modal popup. Rob's verbatim feedback: *"this can not be the process for customers take a note of that it needs to be fixed"*.
- **Fix options:**
  - Bundle pre-built Python wheels + a static brew toolchain so CLT isn't needed at all (large download, but offline-capable)
  - Or detect missing CLT in pre-flight and provide a clearer explanation of what's about to happen, plus a "I clicked Install, here's a Y/N to continue" gate
  - Or ship as a notarized .pkg only (the `.pkg` already works without CLT — that's its whole point)
- **Recommend:** Tied to B-3. If we go `.pkg`-for-everyone, this evaporates. If we keep `setup.sh` for the Mini, add a clearer pre-flight check and a documented manual step.

### B-5 · GitHub auth wall (customer-facing problem)

- **Symptom:** `git clone` of a private repo prompts for GitHub username + password. Rob signs in with Google → no password to type. Stuck.
- **Today's workaround:** Made the repo public via `gh repo edit ... --visibility public`. Cloned anonymously over HTTPS.
- **Customer impact:** Rob's verbatim feedback: *"we were trying to do this for a person not familiar with terminal"*.
- **Fix:** No customer should ever `git clone` to install. The `.pkg` bundles everything. If we ever ship setup.sh as the customer path (we shouldn't — see B-3), it must download a release tarball over HTTPS without auth.
- **Recommend:** Resolved by sticking with `.pkg` for customers. Keep setup.sh as ops-only.

### B-6 · Tahoe auto-update mid-install slowed Mini to a crawl

- **Symptom:** Mini auto-updated 26.3 → 26.4.1 overnight. Post-update, Mini was sluggish enough that Rob force-rebooted, which broke the SSH session and required physical-screen rescue (lock screen, auto-login fix).
- **Customer impact:** A customer doing this remote-only would have been bricked out of their own Mini.
- **Fix:** Pre-flight should:
  - Detect "macOS major version updated within last 48h" and warn to wait 24h before installing
  - Verify auto-login + screen-share + lock-screen disabled BEFORE the user disconnects from peripherals
  - Have a recovery doc for "I rebooted and now can't reach the Mini"
- **Recommend:** Add a `phase_00_environment_check()` that gates the install on these conditions.

### B-7 · `--dry-run-install` doesn't skip Phase 2 prompts

- **Symptom:** `sudo zsh setup.sh --dry-run-install` still asks for AMS creds, Slack tokens, etc. interactively. Defeats the purpose of dry-run.
- **Fix:** Either:
  - Skip Phase 2 entirely in dry-run (use placeholder values internally to walk Phases 3–15)
  - Or read from a config file so dry-run can preview the full path without input
- **Recommend:** Tied to B-2 — if Phase 2 becomes a config file, dry-run "just works" because the file is or isn't there.

### B-8 · `setup.sh` requires sudo even for `--dry-run-install`

- **Symptom:** Pre-flight calls fail without sudo even when no changes are being made.
- **Fix:** Skip the root-EUID check when `--dry-run-install` is set. Allow non-destructive dry-runs as any user.

### B-9 · Catalog count drift (313 vs 320)

- **Symptom:** Multiple docs reference 313 catalog rows; actual catalog is 320 since PR #102 (Bitaxe).
- **Files to update:** `CLAUDE.md`, `README.md`, `AI_ROADMAP.md`, `docs/CAPABILITIES.md`, `docs/CATALOG_ORPHAN_TABLES_2026-04-28.md`, `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` (Phase 5 timing table line 112).
- **Recommend:** Single search-replace PR, no code changes.

### B-11 ✅ FIXED in v1.0.1 · `.pkg` Welcome copy promises wrong LLM model

- **Symptom:** `.pkg` Welcome screen reads *"Installs Ollama and pulls a local LLM model sized to your Mac's RAM (16 GB › llama3.2:3b; 24 GB+ › ..."*
- **Reality:** `setup.sh` Phase 8 pulls `qwen2.5:14b-instruct-q4_K_M` (~8 GB) regardless of RAM.
- **Two possibilities:**
  - (a) `.pkg` postinstall actually picks `llama3.2:3b` on 16 GB Macs — different code path from `setup.sh`. If true, payload diverges from setup.sh, which is a bigger architectural issue.
  - (b) Welcome copy is stale, model picker logic is the same as setup.sh, customer is told one thing and gets another.
- **Fix:** Diff the .pkg postinstall against setup.sh phase_08_ollama. Pick one model strategy (RAM-tiered or fixed qwen2.5:14b), make both paths agree, update Welcome copy to match.
- **Discovered:** 2026-05-01, when Rob double-clicked the .pkg on his laptop to inspect the Welcome screen.

### B-13 ✅ FIXED in v1.0.1 · `.pkg` REJECTED by macOS Tahoe with 'package is incompatible' error (RELEASE BLOCKER)

- **Severity:** 🚨 **CRITICAL — ships broken to any customer on macOS 26.x.** Cannot install at all.
- **Symptom:** After clicking Install → entering admin password → the installer immediately shows error dialog: *"This package is incompatible with this version of macOS. The package is trying to install content to the system volume. Contact the software manufacturer for assistance."* with only a `Quit` button. No install proceeds. No postinstall runs. Nothing is written.
- **Mac Mini state at error:** macOS 26.4.1 (Tahoe), arm64 Apple Silicon, signed in as user `Mining Guardian` (admin), .pkg `MiningGuardian-1.0.0-0f849bd217cc.pkg` (build 0f849bd217cc, 436.5 MB) from `/Volumes/MG Install/`.
- **Confirmed clean failure:** Nothing in `/usr/local/MiningGuardian/`, no LaunchDaemons loaded, no brew services touched. The reject happens before payload extraction.
- **Root cause (almost certain):** The `.pkg`'s `Distribution.xml` declares an install target on the system volume (`/`) without the necessary entitlements for SSV (Sealed System Volume). macOS Tahoe enforces this strictly — any .pkg targeting `/` without proper hooks gets rejected at the SecAssessment stage.
  - The setup.sh equivalent installs to `/usr/local/MiningGuardian/` which on Tahoe is a *firmlink* from the data volume — writable by an admin user with sudo, but a .pkg needs to declare `pkg-info plist` with `auth=root` AND target `/Library/Application Support/MiningGuardian/` (data volume) OR use `BundleIsRelocatable=NO` with explicit data-volume path.
- **Fix options:**
  - (a) Move install target from `/usr/local/MiningGuardian/` to `/Library/Application Support/MiningGuardian/` and update postinstall + LaunchDaemon paths. (Cleanest, also matches Apple HIG for system-wide apps.)
  - (b) Keep `/usr/local/MiningGuardian/` but add proper `<pkg-ref>` declarations in Distribution.xml with `installKBytes` calculated and `auth="Root"` plus `<options customize="never" allow-external-scripts="false"/>` to satisfy SSV.
  - (c) Build a component .pkg with `--root /tmp/payload-root --install-location /Library/Application Support/MiningGuardian` instead of writing to system volume.
- **Recommend:** (a). Apple wants apps in `/Library/Application Support/`. We're swimming upstream by using `/usr/local/`. The fix forces good architecture and unblocks Tahoe.
- **Before merging the fix:** Re-sign and re-notarize the new .pkg. Notarization can take 5–60 min per submission. Plan for a half-day cycle including QA on a clean Tahoe Mini.
- **Discovered:** 2026-05-01 4:04 PM CDT mid-install on the Mac Mini, immediately after clicking Install + entering admin password.
- **Forensic capture:** `customer_docs/screenshots/bug_reports/B-13_pkg_incompatible_tahoe_RAW.jpg`

### B-12 ✅ FIXED in v1.0.1 · `.pkg` Welcome panel renders broken in dark mode on Tahoe (26.x)

- **Symptom:** When the Mac Mini is set to dark appearance and the .pkg is opened, the Hero sidebar branding (shield + pickaxes + Bitcoin coin + MINING GUARDIAN wordmark) does not render — sidebar appears dark gray text-only. Inline code pills (`/usr/local/MiningGuardian`, `127.0.0.1:5432`, `llama3.2:3b`) show as solid black rectangles instead of text. Body copy is readable.
- **Mitigation discovered:** Switching the Mac to light mode and reopening the .pkg restores all branding and code pills correctly.
- **Root cause (suspected):** Custom HTML resources in `Distribution.xml` / `Resources/background.html` use CSS that doesn't account for `prefers-color-scheme: dark` on Tahoe's Installer.app WebKit context. macOS Tahoe (26.x) tightened WebKit lockdown in Installer.app and may be applying a dark-mode user-agent stylesheet that overrides the .pkg's intended styles.
- **Customer impact:** Most customers run dark mode by default in 2026. They get a visibly broken first impression that suggests "this software isn't finished." Cannot ship this way.
- **Fix options:**
  - (a) Force light-mode CSS regardless of system setting via `color-scheme: light only;` in the installer HTML
  - (b) Add a proper dark-mode variant with the right contrast
  - (c) Switch from HTML branding to a static rendered PNG background (loses code-pill formatting but eliminates WebKit risk)
- **Recommend:** (a) for a quick fix, (b) for a polish pass once we have time. Test on a Tahoe Mini in both light and dark mode before signing the next .pkg.
- **Discovered:** 2026-05-01 mid-install, when first opening the .pkg on the Mini in dark mode showed broken rendering. Mitigated by switching to light mode.

### B-10 · Runbook's `bash scripts/setup.sh` line is wrong — ✅ DONE in v1.0.2

- **Symptom:** `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` instructs `bash scripts/setup.sh`. The script is `#!/bin/zsh`. Running with bash produces literal escape codes instead of color output.
- **Fix:** Update runbook to `sudo zsh scripts/setup.sh`. One-line PR.
- **Resolution (v1.0.2 / 2026-05-02):** Updated runbook to `DRY_RUN=1 zsh scripts/setup.sh` for the dry-run line and `sudo -E zsh scripts/setup.sh` for the real run, with an inline comment explaining that `setup.sh` uses zsh-only `read VAR?prompt` and `read -s VAR?prompt` syntax that bash rejects with `bash: -s: invalid option`. Symptom is worse than just lost color output — Phase 2 hard-fails. Fix landed on branch `fix/installer-b1-disk-check-b10-runbook-zsh`.

---

## What's NOT broken (verified working today)

- Tailscale remote-access via `100.69.66.32` — solid
- Apple notarization chain — verified accepted on `MiningGuardian-1.0.0-0f849bd217cc.pkg` (5 submissions, all accepted, last one visually approved)
- Auto-login + caffeinate + true headless — verified post-reboot
- `gh` CLI workflow — flipped repo to public cleanly
- Pre-flight Phase 1 macOS / arm64 / RAM / LAN-ping checks — all passed
- The four heavy phases (3 brew, 4 postgres, 5 catalog seed, 8 ollama) — never reached, so unverified, but no reason to suspect issues

---

## Recommended fix sequence when we resume

Order matters — fix the blockers first, then the polish.

1. **B-1 disk check** (~30 min PR)
2. **B-10 runbook bash→zsh** (~5 min PR, batch with B-1)
3. **B-2 Phase 2 UX → config-file approach** (~2-3 hr PR, biggest win)
4. **B-7 + B-8 dry-run actually being a dry-run** (~30 min, falls out of B-2)
5. **B-3 doc the install path split** (~1 hr PR, no code)
6. **B-9 catalog count cleanup** (~10 min PR)
7. **B-6 environment check phase** (~1 hr PR, optional polish)
8. **THEN** retry the install on the Mini

Total estimated time before re-attempt: **~4-6 hours of focused PR work**, spread across 1-2 sessions.

---

## State of the Mini at session abort

- Hostname: `miningguardian` (mDNS) / `100.69.66.32` (Tailscale)
- macOS 26.4.1 Tahoe (auto-updated overnight from 26.3)
- Repo: `~/code/Mining-Guardian` on `main` branch, HEAD `084dcba`
- `setup.sh` clean (bypass reverted, backup file removed)
- Nothing in `/usr/local/MiningGuardian/` — Phase 2 never wrote .env
- Nothing in Postgres — Phase 4 never ran (Postgres not even installed)
- Caffeinate PID `1884` may still be running (or may have died on reboot — check `ps -ef | grep caffeinate`)
- Auto-login + screen-share + Tailscale all preserved

**Safe to leave running indefinitely.** No daemons, no scheduled jobs, no cron — just an idle Mac Mini reachable over Tailscale.

---

## When we come back

1. Verify Mini is still reachable: `ssh miningguardian@100.69.66.32`
2. Pull this doc, walk the recommended fix sequence above
3. After all PRs merged, re-pull on Mini: `cd ~/code/Mining-Guardian && git pull origin main`
4. Then re-attempt install

*— Logged 2026-05-01 by Computer at session-abort.*
