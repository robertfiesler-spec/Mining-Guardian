# Mining Guardian — Install Paths (architecture, 2026-05-03)

**Date:** 2026-05-03
**Supersedes:** `docs/INSTALL_PATHS_2026-05-02.md` (retained for historical context with a SUPERSEDED notice).
**Authorizing decisions:** D-18 (v1.0.3 installer scope), D-19 (operator console as 10th service), D-20 (importer stays with operator forever). All in `docs/DECISIONS.md`.
**Audit reference:** `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`.
**Status:** Authoritative as of 2026-05-03. All runbooks, customer docs, and HANDOFFs link here for the install-path question.

---

## TL;DR

Mining Guardian has **one customer install path** and **one operator development tool**. The previous architecture's "viewer-only .pkg" framing was factually wrong per the v1.0.2 .pkg audit and is hereby superseded.

| Role | Hardware | Install path | Who runs it |
|---|---|---|---|
| **Customer Mining Guardian appliance** | The Mac Mini (or future Mac) on the customer's miner LAN | **`MiningGuardian-1.0.3-<sha>.pkg`** double-click | The customer (or operator-led screen-share) |
| **Operator development tool** | Operator's laptop or any dev box | `scripts/setup.sh` (15-phase zsh installer) | The operator (Rob), for ad-hoc Mini provisioning before v1.0.3 ships, and for future operator-side dev work |

The customer Mini ALWAYS uses the .pkg. The customer never opens Terminal, never runs `git clone`, never runs `xcode-select`, never types a Slack token into a shell prompt. The operator path (`setup.sh`) is for the operator's own development purposes — it remains in the repo because v1.0.3 is not yet built; once v1.0.3 ships and is verified, the .pkg becomes the canonical install path for every Mini, including the operator's own.

The previous version of this doc (2026-05-02) said the .pkg was "viewer only" and "site config is fetched from the Mini over Tailscale" — both claims are factually wrong per the v1.0.2 .pkg audit (Section 5 of the audit doc above). The .pkg is a partial operations install today; v1.0.3 closes the gaps and becomes the full operations install per D-18.

---

## What changed since 2026-05-02

The 2026-05-02 doc was written to answer B-3 ("`.pkg` vs `setup.sh` path is unclear and inconsistent") and chose recommendation (a) from the backlog: split the .pkg as "viewer-only for end-user laptops" and `setup.sh` as "operations for the Mini." That split was a guess — nobody had read the .pkg postinstall code at the time the split was proposed.

The v1.0.2 .pkg audit (commissioned 2026-05-03 after install-day surfaced the contradiction) read the postinstall code in full and found: the .pkg is NOT viewer-only. It installs Postgres, Ollama, and 9 LaunchDaemons. It is a partial operations install. The "viewer-only" framing was guessed, not verified.

Two facts forced this rewrite:

1. **The audit found 5 hard gaps + 4 copy bugs + 4 integration bugs in v1.0.2 that make the .pkg apparently-successful but functionally-broken.** Every LaunchDaemon would crash-loop within 10 seconds of bootstrap because the `.env` does not contain AMS or Slack credentials, and the `${MG_INSTALL_ROOT}/venv` directory the launcher wrappers reference is never created. Customer would see a green "Installed" dialog and a non-functional Mini.
2. **The operator confirmed 2026-05-03 the customer-experience vision is "install easy enough for someone who barely knows a computer."** Two install paths for the same role (customer Mini) is incompatible with that vision. One path = .pkg double-click, full stop.

D-18 locks the rewrite. v1.0.3 .pkg becomes the customer install. The Mini will not be cut over until v1.0.3 is built, signed, notarized, and smoke-tested green on a clean Mac VM (UTM/Tart).

---

## The customer .pkg path (post-v1.0.3)

**Audience:** A non-technical customer on the Mac Mini that runs the fleet. Or the operator on their own Mini (operator is "customer #1" per D-10).

**Hardware:** Apple-Silicon Mac Mini (M-series) on macOS 13+ on the customer's miner LAN.

**Entry point:** `MiningGuardian-1.0.3-<sha>.pkg` (signed, notarized, stapled, distributed via private GitHub Release + USB stick fallback per Q2).

**Required customer doc:** `docs/customer/MiningGuardian_Setup_Manual.pdf` (regenerated for v1.0.3).

**Pre-install operator hand-off (operator-side, NOT customer-side):**

1. Operator (Rob) fills in `~/Desktop/MiningGuardian.conf` from the template at `installer/macos-pkg/resources/MiningGuardian.conf.template` with the customer's AMS credentials, Slack tokens, customer name, and Cloudflare API token.
2. Operator hands the customer (or screen-shares to) a USB stick or AirDrop bundle containing the .pkg + the pre-filled `MiningGuardian.conf`.
3. Customer drops `MiningGuardian.conf` on their Desktop (so postinstall.sh can find it at `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`).

**Customer-side install (the only thing the customer types):**

1. Double-click `MiningGuardian-1.0.3-<sha>.pkg` in Finder.
2. Type their Mac admin password once when Installer.app prompts.
3. Wait ~5-15 minutes (most of it is the one-time Ollama model pull at first install).
4. Done. Mining Guardian runs.

**What the v1.0.3 .pkg actually installs (per D-18 closing the v1.0.2 audit gaps):**

- Apple Installer.app GUI: Welcome → License → Destination → Installation Type → Install → Conclusion.
- Preinstall gates: macOS ≥ 13, Apple Silicon, RAM ≥ 16 GB, free disk ≥ 20 GB on `/`, `/Applications` writable, no conflicting prior install.
- Postinstall reads `~/Desktop/MiningGuardian.conf`, validates per B-2 rules (AMS_URL `http(s)://`, AMS_EMAIL `@`, AMS_WORKSPACE_ID integer, SLACK_WEBHOOK_URL `hooks.slack.com`, SLACK_BOT_TOKEN `xoxb-`, SLACK_APP_TOKEN optional `xapp-`, MG_DRY_RUN boolean), aborts with a Cocoa dialog if missing or invalid.
- Colima VM boot + Postgres 16 container on `127.0.0.1:5432` with three databases: `mining_guardian`, `mining_guardian_test`, `mining_guardian_catalog`.
- 320-row Bitcoin SHA-256 miner catalog seed applied to `mining_guardian_catalog` per D-18 Gap 2.
- Python venv at `${MG_INSTALL_ROOT}/venv` + vendored `pip install -r requirements.txt` per D-18 Gap 5.
- Ollama install + RAM-tier model pull per D-13 (`llama3.2:3b` for 16 GB, `qwen2.5:14b-instruct-q4_K_M` for 24 GB+; one network call).
- Grafana install + provisioning per D-18 Gap 3, on `:3000` LAN-only.
- 11 scheduled-task launchd plists per D-18 Gap 4 (replacing the `setup.sh phase_10_cron` crontab entries).
- 10 service LaunchDaemons (the existing 9 + the customer operator console per D-19), all bootstrapped via `launchctl bootstrap`.
- `.env` written with the full set of customer-tunable + installer-generated keys per D-18 Integration bug 4.
- Cloudflare Tunnel + Access setup per D-19 (operator's API token from the Desktop conf).
- `bin/uninstall.sh` shipped per D-18 Copy bug 3 (option a). SHIPPED 2026-05-04 in P-008 — bootouts all 10 service + 11 scheduled-job LaunchDaemons, removes Postgres container, removes `${MG_INSTALL_ROOT}` (preserves `postgres-data/` by default; `--purge-data` opt-in), supports `--help` / `--dry-run` / `--yes` / `--purge-logs`.
- Welcome and Conclusion HTML showing correct service counts (10) and ports (`:8585` dashboard, `:8686` approval API, `:8787` operator console — moved from :8686 → :8787 in P-006 to avoid collision with approval API; `:3000` Grafana). SHIPPED 2026-05-04 in P-008 (PR `mg/v103-p008-installer-copy-and-uninstall`).
- Install receipt at `/etc/mining-guardian/install-receipt.json` with version + git SHA + RAM tier + LLM model.
- Non-blocking baseline scan at the end so the customer's first dashboard load has data within ~30 seconds.

**Properties of this path:**

- Zero Terminal interaction by the customer.
- Zero `xcode-select`, zero `git clone`, zero Homebrew dependency, zero GitHub auth wall (per B-4 / B-5 evaporating on the .pkg path).
- Apple-style UX with Welcome / License / Conclusion HTML.
- Signed with Apple Team ID `ARJZ5FYU94`, notarized via key `FPZJ87B3QF`, stapled.
- One network call at first install (Ollama model pull).

**This path is for the customer Mini — and only this path. The .pkg is the customer install. v1.0.2 .pkg is NOT this path — it is a partial implementation that should not be clicked on the Mini per D-18.**

---

## The operator development tool: `scripts/setup.sh`

**Audience:** The operator (Rob), for development purposes only.

**Hardware:** Operator's laptop, a dev VM, or — TODAY ONLY, until v1.0.3 ships — the Mini for ad-hoc provisioning that is NOT the customer install path.

**Why `setup.sh` is no longer the canonical Mini install path:**

The 2026-05-02 doc said `setup.sh` was the Mini's installer because the v1.0.2 .pkg path was assumed to be "viewer-only" — an assumption the audit refuted. With v1.0.3 closing all gaps, the .pkg becomes the canonical Mini installer. `setup.sh` reverts to its development role.

**Why `setup.sh` is still in the repo:**

- v1.0.3 is not yet built. Until v1.0.3 ships, `setup.sh` is the only path that fully provisions a Mini (with Grafana, catalog seed, scheduled tasks, customer config). For the period between today and v1.0.3 verification, `setup.sh` remains the operator's tool for local dev work.
- `setup.sh` exercises every code path that v1.0.3's postinstall must replicate. It is the reference implementation for the v1.0.3 build. Removing it before v1.0.3 ships would erase the reference.
- Post-v1.0.3, `setup.sh` is retained for operator-side dev environments (e.g., Rob spinning up a fresh Mini to test a new feature without burning a notarization cycle).

**This path is for the operator. The customer never sees `setup.sh`. The customer never opens a Terminal.**

---

## Role / path matrix (post-v1.0.3)

| Question | Customer Mini | Operator dev box |
|---|---|---|
| Which installer? | `MiningGuardian-1.0.3-<sha>.pkg` double-click | `scripts/setup.sh` (zsh, 15 phases) |
| Terminal? | No | Yes |
| `xcode-select`? | No | Yes (B-4) |
| `git clone`? | No | Yes |
| GitHub account? | No (.pkg distributed via USB or operator-side download) | No (repo public) |
| Site config (AMS, Slack, etc.)? | Pre-filled by operator on a USB-staged `~/Desktop/MiningGuardian.conf` | Operator types in `--config-file=PATH` flag |
| What's installed? | Full operations stack: Postgres + Grafana + Ollama + Tailscale-aware + 10 LaunchDaemons + 11 scheduled-task plists + console (D-19) | Full operations stack via `phase_03` through `phase_15` |
| Catalog importer (`mg_import_tool/`)? | NOT included in the .pkg per D-20 | Available in the repo for operator use |
| Console (D-19)? | Yes — 10th service, Cloudflare-fronted at `mg.fieslerfamily.com` | Available locally at `127.0.0.1:8686` |
| Runtime data ownership | This Mini, per D-16 | This dev box (separate from production data) |
| What runbook? | `MiningGuardian_Setup_Manual.pdf` (customer-facing, regenerated for v1.0.3) | `RUNBOOK_INSTALL_DAY_2026-04-30.md` + `MAC_MINI_DEPLOYMENT_RUNBOOK.md` |

---

## What today's Mini cutover does NOT do

Per D-18, the Mini is NOT installed today. v1.0.2 .pkg is broken per the audit. `setup.sh` could provision the Mini today, but doing so before v1.0.3 ships means the Mini would not match the canonical customer install path — and the operator's "be the first customer" mantra (D-10) requires the Mini to receive the same install every other customer will receive. **The Mini cutover slips until v1.0.3 is built, signed, notarized, and smoke-tested green on a clean Mac VM.**

The Hostinger VPS continues running production. ROBS-PC's catalog volume stays intact (containers DOWN per D-16 do-not-touch list). VPS decommission and ROBS-PC container shutdown — both originally Monday 2026-05-04 morning per D-16 — are explicitly deferred until v1.0.3 ships.

---

## Frequently confused

- **"The .pkg is viewer-only"** — was claimed in the 2026-05-02 doc, refuted by the audit. The .pkg is a partial operations install (postinstall installs Postgres, Ollama, 9 LaunchDaemons). v1.0.3 closes the gaps and makes it the full operations install.
- **"The customer needs to run setup.sh on their Mini"** — false. The customer's path is the .pkg double-click, full stop. `setup.sh` is operator-only.
- **"setup.sh is being deleted"** — false. `setup.sh` stays in the repo as the operator dev tool. It is no longer the canonical Mini install path.
- **"v1.0.2 is fine — it's signed and notarized"** — false. Apple's signing chain has nothing to do with whether the postinstall actually configures the system correctly. The audit shows v1.0.2 .pkg installs a partial system whose every LaunchDaemon crashes on first start.
- **"The .pkg should bundle `mg_import_tool/`"** — false per D-20. The importer stays with the operator forever. The customer .pkg never bundles it. (If it does for code-coupling reasons, no LaunchDaemon or console UI surfaces it.)
- **"The customer types AMS credentials at install time"** — false. The customer never types a credential. The operator pre-fills the `MiningGuardian.conf` on a USB stick (or AirDrop). The customer drops the file on their Desktop, then double-clicks the .pkg.

---

## Reverse links

- `docs/INSTALL_PATHS_2026-05-02.md` — the predecessor doc with the now-superseded "viewer only" framing. Retained for historical context only.
- `docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md` — the audit that triggered this rewrite.
- `docs/DECISIONS.md` D-18, D-19, D-20 — the locked decisions this doc implements.
- `docs/DECISIONS.md` D-16 — Mini cutover sequencing, amended by D-18.
- `docs/DECISIONS.md` D-13 — RAM-tier LLM model selection (preserved, no change).
- `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` B-3 — the original install-path question that this doc fully answers.
- `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` — operator-side install runbook (still references `setup.sh` as the Mini path; the section-4 link will be updated to point here in a follow-up PR alongside the v1.0.3 build).
- `docs/RUNBOOK_PKG_REBUILD.md` — operator-only build procedure, header note will be updated to point here in the same follow-up PR.
- `docs/customer/MiningGuardian_Setup_Manual.pdf` — customer-facing setup manual, regenerated for v1.0.3 with the post-v1.0.3 .pkg flow.
