# Mining Guardian — Install Paths (architecture)

> **SUPERSEDED 2026-05-03 by `INSTALL_PATHS_2026-05-03.md` per D-18.**
> The "viewer only" framing in this document is factually wrong per the v1.0.2 .pkg audit
> (`docs/audits/PKG_AUDIT_v1.0.2_FINDINGS_2026-05-03.md`). This document is retained for
> historical context only.

**Date:** 2026-05-02
**Closes backlog item:** B-3 (`docs/INSTALLER_UX_BACKLOG_2026-05-01.md`)
**Decision recorded in:** `docs/DECISIONS.md` (D-15/D-16 family)
**Status:** SUPERSEDED 2026-05-03 per D-18. Retained for historical context only.

---

## TL;DR

Mining Guardian has **two distinct install paths** for **two distinct roles**. They are not interchangeable.

| Role | Hardware | Install path | Who runs it |
|---|---|---|---|
| **Operations server** | The Mac Mini that actually runs the fleet (Postgres, Grafana, Ollama, Tailscale, the scheduled tasks) | `scripts/setup.sh` (the 15-phase zsh installer) | The site operator (today: Rob; tomorrow: a trained on-site tech) |
| **End-user laptop / viewer** | A customer's MacBook or iMac that only needs to **view** dashboards and receive alerts | `MiningGuardian-<version>-<sha>.pkg` (signed + notarized double-click installer) | A non-technical customer |

The `.pkg` is **never** the right path for the Mini. The `setup.sh` script is **never** the right path for a non-technical customer's laptop.

---

## Why two paths?

The two roles need different payloads. Bundling them into one installer was the original plan but it forced trade-offs that hurt both audiences:

- The Mini operator needs:
  - Full Postgres + Grafana + Ollama + Tailscale daemon stack
  - Scheduled-task cron entries
  - Direct fleet network access
  - The ability to run dry-runs, re-runs, and partial-phase recoveries
  - A real shell (zsh) where they can `tail` logs and re-source `.env`
- The end-user laptop needs:
  - A read-only Grafana viewer + Slack/Mail alert handler
  - Zero terminal usage
  - Apple-style Welcome → License → Install → Done UX
  - A signed, notarized binary with no `xcode-select`, no `git clone`, no GitHub auth wall

Trying to satisfy both in one installer is what produced backlog items B-2, B-3, B-4, B-5, and B-7. Splitting them resolves all five at the architecture level (B-2/B-7 also got direct fixes in PR #108; B-4/B-5 are now N/A for end-users because the `.pkg` path doesn't `xcode-select` or `git clone`).

---

## The operations path: `scripts/setup.sh`

**Audience:** Site operator (technical; trained on the runbooks).

**Hardware:** The dedicated Mac Mini that will run the fleet 24×7.

**Entry point:** `scripts/setup.sh`

**Required runbooks (read in order):**
1. `docs/RUNBOOK_HEADLESS_ADDENDUM_2026-04-30.md` — read first if the Mini will run without keyboard/monitor.
2. `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` — the canonical 15-phase install flow.
3. `docs/MAC_MINI_DEPLOYMENT_RUNBOOK.md` — post-install verification.

**Invocation (high level):**
```zsh
git clone https://github.com/robertfiesler-spec/Mining-Guardian.git
cd Mining-Guardian
chmod +x scripts/setup.sh
# Dry-run first (no sudo needed; no real config needed):
DRY_RUN_INSTALL=true zsh scripts/setup.sh
# Then real run with site config (per B-2 fix in PR #108):
sudo -E zsh scripts/setup.sh --config-file=/path/to/MiningGuardian.conf
```

**Site config template:** `installer/macos-pkg/resources/MiningGuardian.conf.template` (added in PR #108).

**Properties of this path:**
- Requires `xcode-select --install` for command-line tools (B-4 unresolved for ops; documented).
- Requires zsh (B-10 fixed in PR #106).
- Requires sudo for the real run; dry-run does not (B-8 fixed in PR #108).
- Phases 1–15 are itemised in `RUNBOOK_INSTALL_DAY_2026-04-30.md`.
- Failures are recoverable — re-run the script; idempotent phases skip already-completed work.

**This path is for the Mini. Do not click the `.pkg` on the Mini.**

---

## The end-user path: the `.pkg`

**Audience:** A customer's non-technical user on their personal MacBook or iMac.

**Hardware:** Any Apple-Silicon Mac running macOS 14 or 15 with > 16 GB free disk.

**Entry point:** `MiningGuardian-<version>-<sha>.pkg` (signed, notarized, stapled).

**Required customer doc:** `docs/customer/MiningGuardian_Setup_Manual.pdf`.

**Invocation:**
1. Customer receives the `.pkg` (USB stick, AirDrop, or a download link from the operator).
2. Customer double-clicks the file.
3. Apple Installer opens → Welcome → License → Destination → Installation Type → Install.
4. Customer enters their Mac password once when prompted.
5. Done. Mining Guardian appears in `/Applications/Mining Guardian/`.

**Properties of this path:**
- No Terminal interaction.
- No `xcode-select` (the `.pkg` postinstall is fully self-contained — that is its whole point; B-4 evaporates here).
- No `git clone` (B-5 evaporates here).
- No GitHub auth wall (B-5 evaporates here).
- No Phase 2 prompts (the `.pkg` payload is the viewer-only build; site config is fetched from the Mini over Tailscale, not entered locally).
- Apple-style UX with Welcome / License / Conclusion HTML — handled by `installer/macos-pkg/resources/`.
- Signed with Apple Team ID `ARJZ5FYU94` and notarized via key `FPZJ87B3QF`.

**Build/refresh procedure:** `docs/RUNBOOK_PKG_REBUILD.md` — operator-only. Customers never see this.

**This path is for end-user laptops. Do not run setup.sh on end-user laptops.**

---

## Role / path matrix

| Question | Mini (ops) | End-user laptop |
|---|---|---|
| Which installer do I use? | `setup.sh` | `.pkg` double-click |
| Do I need to type in a Terminal? | Yes | No |
| Do I need `xcode-select`? | Yes (B-4) | No |
| Do I need to `git clone`? | Yes | No |
| Do I need a GitHub account? | No (repo public) | No |
| Do I need to enter site config (AMS, Slack, etc.)? | Yes — via `--config-file=PATH` (B-2) | No — fetched from Mini over Tailscale |
| What does the install ship? | Postgres + Grafana + Ollama + Tailscale + scheduled tasks + viewer | Viewer only |
| Who owns the runtime data? | This machine (post-cutover, per D-16) | The Mini (over Tailscale) |
| What runbook do I read? | `RUNBOOK_INSTALL_DAY_2026-04-30.md` | `MiningGuardian_Setup_Manual.pdf` |

---

## What the runbooks now say

- `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` (Mini operator) — section 4 retains the warning *"Do not click the .pkg — the .pkg is for end-user laptops, not the operations Mac Mini"* and now links to **this doc** for the rationale.
- `docs/RUNBOOK_PKG_REBUILD.md` (`.pkg` build operator) — header note now explicitly states that the `.pkg` it produces is for end-user laptops, not for the Mini, and links here.
- `docs/customer/MiningGuardian_Setup_Manual.pdf` (customer) — already documents the `.pkg` flow and only the `.pkg` flow. No edit required; this file is binary and source-controlled separately. The next regeneration will add a one-line "this manual is for the end-user laptop install; if you are setting up the Mining Guardian operations server, see your operator runbook" footer on the cover page.

---

## Frequently confused

- **"The .pkg installs the same payload as setup.sh"** — was true at v1.0.0. False at v1.0.1+. The `.pkg` payload is the viewer-only build; the postinstall does **not** run the 15 setup phases. (See B-11 / B-12 / B-13 in INSTALLER_UX_BACKLOG.)
- **"I can use the .pkg on the Mini to save time"** — no. The `.pkg` doesn't bring up Postgres or Ollama or the scheduled tasks. It will appear to install successfully and then nothing will work.
- **"I can use setup.sh on a customer's laptop to give them more features"** — no. setup.sh tries to bind Postgres on :5432 and pull a 9 GB LLM. A customer's laptop has neither the disk budget nor the use-case.

---

## Reverse links

- `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` (B-3 entry)
- `docs/MG_UNIFIED_TODO_LIST.md` (B-3 row)
- `docs/RUNBOOK_INSTALL_DAY_2026-04-30.md` (section 4)
- `docs/RUNBOOK_PKG_REBUILD.md` (header)
- `docs/DECISIONS.md` (D-15, D-16)
