# Mining Guardian v1.0.3 — Paused Before Mac Mini Install

```yaml
date: 2026-05-04
session_id: manual (post-P-012 — package built, signed, notarized, transferred, paused before sudo installer)
last_commit_on_main: a35728d — fix(installer): D-18 P-012 resign_wheel.py compat with macOS python3
agent: Computer (autonomous agent)
repo: Mining-Guardian
scope: installer / Mac Mini install only — not a multi-track session
```

This file is the canonical, in-repo handoff for the v1.0.3 install pause point. Do not rely on shared workspace files or chat history alone — this doc is the source of truth for the next session.

---

## Pause point — exact

The Mac Mini is staged. The package is sitting in `~/Downloads`. Every pre-install verification has passed. The next command — and the only command Rob has not yet run — is:

```bash
cd ~/Downloads
sudo installer -pkg "MiningGuardian-1.0.3-a35728dcfc8c.pkg" -target /
```

Rob explicitly chose to pause here because he was called into a meeting. He wants screenshots when we resume. Do not rush this step.

---

## Why this handoff exists

Rob's standing rules:

- Over-document everything so future sessions have a reference point.
- Go slow and do it right; no shortcuts.
- When Rob answers decision questions, document the question and answer so future sessions do not re-ask.
- This chat / workstream is only about fixing the installer and installing on the new Mac Mini.
- Do not fix Grafana right now.
- Do not rush the install. Rob wants screenshots along the way when we resume.

The shared workspace at `/home/user/workspace/HANDOFF_2026-05-04_PAUSED_BEFORE_MINI_INSTALL.md` and `/home/user/workspace/INSTALLER_UX_GAP_NOTE_2026-05-04.txt` were not in the repo. Per the standing rules above, this committed file makes the same content discoverable by any future session via `git log` / `git grep`.

---

## Final built package

Built on Rob's laptop (`/Users/BigBobby/Documents/GitHub/Mining-Guardian/`) from `main`.

| Field | Value |
|---|---|
| Final source commit | `a35728dcfc8c613a23323ef35cac3160384a4932` |
| Package filename | `MiningGuardian-1.0.3-a35728dcfc8c.pkg` |
| Package size | 493 MB |
| Build path on laptop | `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-a35728dcfc8c.pkg` |
| SHA-256 sidecar | `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256` |
| Apple notary submission ID | `1598b56f-f4da-4926-a319-6567a4d6d5bf` |
| Notary status | Accepted |
| Stapling | "The staple and validate action worked. The validate action worked." |
| Gatekeeper on build Mac | accepted, source=Notarized Developer ID, origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94) |

Build output as recorded:

```text
Version: 1.0.3
Git SHA: a35728dcfc8c
Pkg: /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-a35728dcfc8c.pkg
SHA-256: /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256
```

---

## Transfer chain

USB and AirDrop both used; the AirDrop path is the one the Mini ended up consuming.

USB volume `MG Install` listing as written:

```text
MiningGuardian-1.0.3-a35728dcfc8c.pkg              493M
MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256       159B
USB-MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256   104B
```

USB-local checksum verification:

```text
MiningGuardian-1.0.3-a35728dcfc8c.pkg: OK
```

The Mac Mini lacked a convenient USB port / adapter, so Rob AirDropped the package from the laptop to the Mini. Files landed at:

```text
/Users/miningguardian/Downloads/MiningGuardian-1.0.3-a35728dcfc8c.pkg
/Users/miningguardian/Downloads/USB-MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256
```

---

## Mac Mini verification — already passed

These ran on the Mini before the meeting interrupted. Re-run them at resume time before invoking `installer`.

Checksum:

```bash
cd ~/Downloads
shasum -a 256 -c USB-MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256
```

Result:

```text
MiningGuardian-1.0.3-a35728dcfc8c.pkg: OK
```

Gatekeeper:

```bash
spctl --assess --type install -vv MiningGuardian-1.0.3-a35728dcfc8c.pkg
```

Result:

```text
MiningGuardian-1.0.3-a35728dcfc8c.pkg: accepted
source=Notarized Developer ID
origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
```

---

## Desktop config — already created and validated

Per D-18 Gap 1 / P-005, postinstall reads `/Users/${SUDO_USER}/Desktop/MiningGuardian.conf`. The Mini did not have one initially (`ls: /Users/miningguardian/Desktop/MiningGuardian.conf: No such file or directory`); Rob created it manually with `nano` from the v1.0.3 template.

Required / validated fields (no values reproduced — secrets stay on the Mini):

```text
CUSTOMER_NAME
AMS_URL
AMS_EMAIL
AMS_PASSWORD
AMS_WORKSPACE_ID
SLACK_WEBHOOK_URL
SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET
AUTHORIZED_SLACK_USER_IDS
SLACK_APP_TOKEN
SCAN_INTERVAL
MG_DRY_RUN
```

Installer-owned values that should NEVER be placed in this Desktop conf:

```text
MG_DB_PASSWORD          # generated by openssl rand -hex 32 in step_drop_dotenv (D-18 Integration bug 1)
CATALOG_API_KEY         # generated likewise
INTERNAL_API_SECRET     # generated likewise — never leaves the Mini
ports                   # 8585 dashboard / 8686 approval / 8787 console
127.0.0.1 bindings      # localhost-only for all three
AUTO_APPROVE_ENABLED    # locked false at install time per D-2
```

### Q&A captured this session — do not re-ask

- **Q: Should quotes stay around values?** A: Yes — keep the quotes; replace only the text inside the quotes.
- **Q: Slack token formats?** A: `SLACK_BOT_TOKEN` must start with `xoxb-`. `SLACK_APP_TOKEN` must start with `xapp-`.
- **Q: One key was wrong — `REPLACE_ME_SITE_NAME="R & D"` was used instead of `CUSTOMER_NAME="R & D"`.** Corrected before the shape check ran. Surfaced an installer UX gap (see customer-onboarding section below).

### Shape checks that passed

```bash
grep -E '^SLACK_WEBHOOK_URL="https://hooks\.slack\.com/' ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK webhook"
grep -E '^SLACK_BOT_TOKEN="xoxb-'                        ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK bot token"
grep -E '^AMS_WORKSPACE_ID="[0-9]+"'                     ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK workspace id"
grep -E '^AMS_EMAIL=".*@'                                ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK email"
grep -E '^CUSTOMER_NAME=".+"'                            ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK customer name"
grep -E '^AUTHORIZED_SLACK_USER_IDS="U[A-Z0-9]+'         ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK approvers"
grep -E '^MG_DRY_RUN="(true|false)"'                     ~/Desktop/MiningGuardian.conf >/dev/null && echo "OK dry-run"
```

All seven `OK` lines printed. Permissions:

```text
-rw------- 1 miningguardian staff 583 May 4 10:22 /Users/miningguardian/Desktop/MiningGuardian.conf
```

---

## Decision: skip the separate clean-VM smoke test

D-18's verification gate originally required a clean macOS 14 VM smoke test (UTM/Tart) before any Mini install. Today Rob explicitly skipped that step.

- **Question on the table:** Set up a clean VM, use the Mac Mini as the first clean target, or use a clean-volume test?
- **Rob's answer:** Skip VM setup. Use the Mac Mini as the first clean-target install. Reason: no VM available; he wanted to transfer the installer over the network rather than buy/use a USB-C adapter or burn a day on a UTM image.
- **Implication:** The Mini becomes the first clean-target install. We proceed slowly, capture screenshots, and do not skip any of the post-install verification.
- **Mitigation:** Every other safeguard from D-18 still applies. Postinstall step ordering is unchanged: customer-info validation runs BEFORE any system change; if it fails, exit code 41 + Cocoa dialog and no system state is touched. The `bin/uninstall.sh` shipped in P-008 is the rollback if anything goes wrong.

This is captured as a new locked decision in `docs/DECISIONS.md` (D-22).

---

## v1.0.3 PR train recap (already on `main`, do not redo)

| PR # | Branch / SHA on main | Purpose |
|---|---|---|
| #117 | `mg/v103-discovery` / `8405d21` | P-001 — discovery |
| #118 | `mg/v103-gap5-postinstall-venv` / `ef89fff` | P-002 — Gap 5 venv |
| #119 | `mg/v103-gap2-catalog-db-and-seed` / `5842f3c` | P-003 — Gap 2 catalog seed |
| #120 | `mg/v103-d20-importer-payload-reconciliation` / `b76907f` | P-004 — D-20 reconciliation |
| #121 | `mg/v103-gap1-customer-info-conf` / `f63b9fe` | P-005 — Gap 1 + Integration bugs 1/2/4 |
| #122 | `mg/v103-d19-console-foundation` / `9d53856` | P-006 — D-19 console foundation |
| #123 | `mg/v103-gap4-scheduled-launchd` / `ade63ef` | P-007 — Gap 4 launchd plists |
| #124 | `mg/v103-p008-installer-copy-and-uninstall` / `c450d12` | P-008 — copy bugs + real `bin/uninstall.sh` |
| #125 | `mg/v103-version-bump-and-release-notes` / `983a95f` | P-009 — version bump + release notes + readiness audit |
| #126 | `mg/v103-p010-wheelhouse-fail-hard` / `295aec3` | P-010 — wheelhouse hard-fail before signing |
| #127 | `mg/v103-p011-wheel-resign` / `d8bbed5` | P-011 — re-sign Mach-O inside wheels |
| #128 | `mg/v103-p012-resign-wheel-py39-compat` / `a35728d` | P-012 — `resign_wheel.py` macOS python3 compat |

Build blockers encountered and resolved during this same session:

- **Missing wheelhouse.** First build warned `WARN /Users/BigBobby/MiningGuardian-vendor/python-wheels missing`. Resolution: installed Homebrew `python@3.12`, populated wheelhouse with macOS arm64 CPython 3.12 wheels (final count `108`), and PR #126 made missing wheelhouse a hard-fail before signing.
- **Apple notary rejected unsigned binaries inside wheels.** Submission `750c089f-f0a1-4d40-bf15-e8c295828027` for `MiningGuardian-1.0.3-295aec38f2ee.pkg` returned `Invalid` with 371 issues across `pandas`, `pillow`, `numpy`, `psycopg_binary`, `fonttools`, `psycopg2_binary`, `matplotlib`, `aiohttp`, `bcrypt`. Resolution in PR #127 (`step_4c_resign_inner_wheels` re-signs Mach-O inside `*.whl` and rewrites RECORD).
- **Python compat bug in helper.** First P-011 build crashed with `TypeError: write_text() got an unexpected keyword argument 'newline'` because `/usr/bin/python3` on macOS Sonoma/Sequoia is Python 3.9. Fixed in PR #128.

The successful final build's `step_4c` summary line:

```text
[resign_wheel] summary: 108 wheel(s) processed — 168 Mach-O signed, 168 RECORD line(s) rewritten, 75 pure-Python wheel(s) skipped, 0 failure(s)
[build_pkg] step 4c OK: 108 wheel(s) re-signed and RECORD-verified (P-011)
```

---

## Resume checklist — do not skip steps

When resuming, do not redo completed work. Start here.

1. Confirm Mac Mini still has the files in `~/Downloads`:

   ```bash
   cd ~/Downloads
   ls -lh MiningGuardian-1.0.3-a35728dcfc8c.pkg USB-MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256
   ```

2. Re-run checksum if any time has passed or files moved:

   ```bash
   cd ~/Downloads
   shasum -a 256 -c USB-MiningGuardian-1.0.3-a35728dcfc8c.pkg.sha256
   ```

   Expected: `MiningGuardian-1.0.3-a35728dcfc8c.pkg: OK`.

3. Re-run Gatekeeper check:

   ```bash
   spctl --assess --type install -vv MiningGuardian-1.0.3-a35728dcfc8c.pkg
   ```

   Expected: `accepted`, `source=Notarized Developer ID`, `origin=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)`.

4. Re-run the seven-line config shape check on `~/Desktop/MiningGuardian.conf`. Expected all seven `OK` lines.

5. Take a screenshot of the Mini desktop before running the installer.

6. Run the installer slowly. Capture full output and screenshots:

   ```bash
   cd ~/Downloads
   sudo installer -pkg "MiningGuardian-1.0.3-a35728dcfc8c.pkg" -target /
   ```

7. After the installer command returns, do not assume success. Verify in stages (pull exact commands from the current repo runbooks at resume time):

   - Installer exit status and final output.
   - Expected install directory (`/Library/Application Support/MiningGuardian/`) exists.
   - `.env` generated under the install root and contains the keys we expect (no AMS / Slack values reproduced in chat).
   - Python venv created under `${MG_INSTALL_ROOT}/venv`.
   - Catalog DB seed applied — `SELECT count(*) FROM hardware.miner_models;` against `mining_guardian_catalog` returns the seed row count (320 at v1.0.3 build; the count grows over time as models are added — re-read `intelligence-catalog/seed-data/seed_miner_models.sql` row count if you need the current SSOT).
   - 10 service LaunchDaemons loaded: `launchctl list | grep com.miningguardian`.
   - 11 scheduled-job LaunchDaemons loaded: `launchctl list | grep com.miningguardian.scheduled.`.
   - Console reachable at `http://127.0.0.1:8787/`; dashboard at `http://127.0.0.1:8585/`; approval API at `http://127.0.0.1:8686/`.
   - Logs show no fatal postinstall failures.

8. If anything fails, the rollback is `sudo /Library/Application\ Support/MiningGuardian/bin/uninstall.sh`. Default behavior preserves `postgres-data` and `/var/log/mining-guardian` — do NOT pass `--purge-data` unless the operator explicitly asks for a clean slate.

---

## Items intentionally deferred

Do not start on these unless Rob explicitly scopes them. Each is tracked elsewhere; pointers below.

- **Grafana cleanup / provisioning** — Gap 3 in `docs/DECISIONS.md` D-18; row 4 in `docs/MG_UNIFIED_TODO_LIST.md` §1.2.
- **Cloudflare Access / Tunnel auto-provisioning** — D-19 step 5; row 9 in `docs/MG_UNIFIED_TODO_LIST.md` §1.2.
- **Installer GUI form replacing Desktop conf editing** — D-23 (added in this PR); MG_UNIFIED_TODO_LIST §18 (added in this PR).
- **Tailscale guided onboarding** — D-23; MG_UNIFIED_TODO_LIST §18.
- **Grafana dashboard JSON / datasource auto-provisioning** — D-23; tied to Gap 3 row 4.
- **Slack / AMS pre-install validation** — D-23; MG_UNIFIED_TODO_LIST §18.
- **Support-bundle export, recovery / uninstall surfacing, screenshot-ready runbook** — D-23; MG_UNIFIED_TODO_LIST §18.
- **Portal schedule-management UX, any non-installer product work** — out of scope for this workstream.

See `docs/CUSTOMER_ONBOARDING_UX_GAPS_2026-05-04.md` for the consolidated UX-gap brief.

---

## Things I currently believe that need re-verification

Older than 24 hours, mark `[VERIFY FIRST]` before acting.

1. The `MiningGuardian-1.0.3-a35728dcfc8c.pkg` on the Mini in `~/Downloads` is byte-identical to the build-Mac copy. **Last verified:** 2026-05-04 via `shasum -a 256 -c`. **Re-verify:** rerun the checksum command at resume time.
2. The Desktop conf at `/Users/miningguardian/Desktop/MiningGuardian.conf` has not been edited since the seven-line shape check passed. **Last verified:** 2026-05-04 ~10:22 local. **Re-verify:** rerun the shape-check block.
3. The Mini still has Tailscale up and reachable on `100.69.66.32` (per HANDOFF_2026-05-04 host topology). **Re-verify:** `tailscale status` on the Mini before any work that depends on remote access.
4. The Hostinger VPS is still running production. D-16 step says it stays up until the Mini is verified green. **Re-verify:** SSH the VPS and check the daemon and Postgres are responsive — do NOT decommission anything until the Mini is green per D-16 + D-18.

---

## Do not touch

- The package file itself. It is signed, notarized, stapled, and verified. Rebuilding produces a new SHA and starts another notary round-trip.
- `installer/macos-pkg/scripts/build_pkg.sh`, `postinstall.sh`, or any source under `installer/macos-pkg/` while the install is paused. Any edit invalidates the package.
- `mg_import_tool/sql/migrations/000_*` and `002_*` — operator-side bootstrap originals retained per D-20 footnote.
- The Hostinger VPS Mining Guardian stack until Mini is green.
- ROBS-PC catalog masters until Mini is green.
- Grafana provisioning. Explicitly out of scope this session per Rob.

---

## Open questions for Rob

None blocking the resume. The post-install verification step list under the "After installer command returns" section above is the next thing that needs his attention; everything until `sudo installer -pkg …` returns is mechanical re-verification.

---

## Next session start checklist

1. Read this file in full.
2. Re-verify the four "Things I currently believe" items above before acting.
3. Confirm last commit on `main` matches `a35728d` (or whatever the resume-time `main` is — do not re-build the package).
4. Walk the resume checklist top to bottom. No skipping.
5. Capture screenshots at every step Rob can see — Desktop, installer dialogs, Terminal output.
6. After the installer returns, run the staged post-install verification before reporting success.
