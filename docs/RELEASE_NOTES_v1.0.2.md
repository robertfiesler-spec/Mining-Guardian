# Mining Guardian v1.0.2

**Release date:** 2026-05-02
**Build SHA:** _stamped at build time by_ `installer/macos-pkg/scripts/build_pkg.sh`
**Distribution:** Private GitHub Release + USB stick fallback (no public registry, no cloud-only dependencies)

---

## What this release is

An **installer UX hardening release** on top of v1.0.1. v1.0.1 fixed the Tahoe SSV release blocker (B-13) and shipped two cosmetic fixes (B-11, B-12). The 2026-05-01 install attempt on the operations Mac Mini surfaced 10 more installer bugs (B-1 through B-10) — most of them in the operator path (`scripts/setup.sh`), some doc-level. v1.0.2 closes seven of those ten plus a new architecture decision that splits the operator path from the customer path cleanly.

The v1.0.2 .pkg payload is identical in shape to v1.0.1 (no SSV / signing / notarization changes). All seven backlog closures are in `scripts/setup.sh`, the runbooks, and the install-path documentation. The Mac Mini install can now be retried from a clean checkout.

Bitcoin SHA-256 miners only. Local-only by design.

---

## Fixes (7)

### B-1 — APFS-naive disk pre-flight false-negative (PR [#106](https://github.com/robertfiesler-spec/Mining-Guardian/pull/106))

**Symptom (v1.0.1):** Phase 1 of `scripts/setup.sh` rejected the new Mac Mini with *"insufficient disk space — need 50 GB free, have 36 GB"*, even though the volume actually had 195 GB available. The check used `df -h /` which on APFS reports the *file-system used* not the *container free*, so any APFS volume with healthy snapshots looked falsely full.

**Fix:** `phase_01_environment` now reads `Container Free Space` from `diskutil info /` (parses the byte count between the parens, integer-divides by 1073741824 for GB). On parse failure it falls back to `df` with a clear warning. Tested on a Tahoe Mini that previously failed the gate at 36 GB; same volume now correctly reports 195 GB free.

### B-2 — Phase 2 customer info is unusable interactive `read` prompts (PR [#108](https://github.com/robertfiesler-spec/Mining-Guardian/pull/108))

**Symptom (v1.0.1):** Phase 2 collected site config (AMS URL, Slack tokens, workspace ID, etc.) via 12 sequential `read` prompts with no validation, no review, and no edit-after-mistake path. One typo on field 3 meant restarting from field 1; mistakes only surfaced in Phase 7 when `.env` was written.

**Fix:** Replaced the prompt loop with a config-file approach. New `installer/macos-pkg/resources/MiningGuardian.conf.template` ships a fully commented site config; new `--config-file=PATH` flag on `setup.sh` sources the file, validates every key fail-fast, and skips all prompts. New zsh helpers: `mg_source_config`, `mg_validate_site_config`, `mg_resolve_site_config`. Validation rules cover URL schemes, email format, integer types, and the Slack token prefixes (`xoxb-`, `xapp-`, `https://hooks.slack.com/`). Verified offline against four test cases (one valid, three invalid) under zsh.

### B-3 — `.pkg` vs `setup.sh` install-path confusion (PR [#109](https://github.com/robertfiesler-spec/Mining-Guardian/pull/109))

**Symptom (v1.0.1):** Two installer entry points (`scripts/setup.sh` and the signed `.pkg`) but no authoritative architecture doc explaining who each is for. The runbook said one thing, the customer Setup Manual implied another, and the May 1 install attempt lost time to the question *"should the Mini run setup.sh or double-click the .pkg?"*

**Fix:** Adopted recommendation (a) from the backlog entry: **operations server (Mini) and end-user laptop (customer) are different roles and deserve different installers**.

- Mini = `scripts/setup.sh` — full Postgres + Grafana + Ollama + Tailscale + scheduled-tasks stack.
- End-user laptop = `.pkg` double-click — viewer-only payload, signed and notarized.

New authoritative doc `docs/INSTALL_PATHS_2026-05-02.md` is the single source of truth, linked from `RUNBOOK_INSTALL_DAY_2026-04-30.md` §4 and the `RUNBOOK_PKG_REBUILD.md` header.

### B-7 — `--dry-run-install` did not skip Phase 2 prompts (PR [#108](https://github.com/robertfiesler-spec/Mining-Guardian/pull/108))

**Symptom (v1.0.1):** `sudo zsh setup.sh --dry-run-install` still asked for AMS creds, Slack tokens, etc. interactively. Defeated the purpose of dry-run and made smoke-testing the installer impossible without real customer data.

**Fix:** When `DRY_RUN_INSTALL=true` and no `--config-file=PATH` is supplied, Phase 2 fills in placeholder values (`DRY-RUN-SITE`, `dry-run@example.invalid`, `xoxb-dry-run-placeholder`, etc.) and continues. Phase 2 emits a clear `[DRY-RUN]` marker so the placeholders cannot be mistaken for real config.

### B-8 — `setup.sh` required sudo even for `--dry-run-install` (PR [#108](https://github.com/robertfiesler-spec/Mining-Guardian/pull/108))

**Symptom (v1.0.1):** Pre-flight calls failed without sudo even when no changes were being made.

**Fix:** The root-EUID check at line 102 was already gated on `[[ "${DRY_RUN_INSTALL}" != "true" ]]` (this part was correct in v1.0.1). The remaining piece was that Phase 2 still demanded interactive sudo-protected input even in dry-run — that is resolved as part of B-7 above. As of v1.0.2 a non-root user can run `zsh scripts/setup.sh --dry-run-install` from a clean checkout and watch every phase preview without entering a password.

### B-9 — Catalog count drift (313 vs 320) (PR [#107](https://github.com/robertfiesler-spec/Mining-Guardian/pull/107))

**Symptom (v1.0.1):** Multiple docs (`CLAUDE.md`, `README.md`, `AI_ROADMAP.md`, `docs/CAPABILITIES.md`, several runbooks) referenced 313 catalog rows. The actual catalog has been 320 since PR #102 (Bitaxe; 7 open-source SHA-256 miners added 2026-04-26).

**Fix (and a doctrine clarification):** Updated 17 files to reflect 320. **More importantly:** locked the rule that the catalog is a living, growing list — not a static count. Hardcoded numbers in docs are now framed as "current count at vX.Y.Z; source of truth is `intelligence-catalog/seed-data/seed_miner_models.sql`." The Grafana Intelligence Report dropdown must read the count dynamically (`SELECT count(*) FROM hardware.miner_models` or a templated variable), not display a fixed label. New doc `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md` captures the rule.

### B-10 — Runbook said `bash setup.sh` but it's `#!/bin/zsh` (PR [#106](https://github.com/robertfiesler-spec/Mining-Guardian/pull/106))

**Symptom (v1.0.1):** `RUNBOOK_INSTALL_DAY_2026-04-30.md` Phase 4 paste-block said `bash scripts/setup.sh`. The script's shebang is `#!/bin/zsh` and it uses zsh-only syntax (`read VAR?prompt`, `read -s VAR?prompt`). Operators copy-pasting the runbook produced confusing parse errors mid-install.

**Fix:** Runbook now says `zsh scripts/setup.sh` everywhere. Verified the four other repo scripts that share an install path (`preflight_install_day.sh`, `seed_catalog.sh`, `db_maintenance.sh`, `lint_mining_gaurdian_typo.sh`) all use bash shebangs and are correct as-is — no copy-paste collisions.

---

## Backlog status (B-1 through B-13)

The May 1 install attempt logged backlog items B-1 through B-13. As of v1.0.2:

- ✅ **B-1, B-2, B-3, B-7, B-8, B-9, B-10** — closed in v1.0.2 (this release)
- ✅ **B-11, B-12, B-13** — closed in v1.0.1
- 🔵 **B-4** (Xcode CLT manual install) — N/A on the customer `.pkg` path per D-16; remains a doc-only follow-up for the operator path
- 🔵 **B-5** (GitHub auth wall) — already resolved by going public; doc-only follow-up
- 🔴 **B-6** (Tahoe auto-update mid-install drag) — open; not a v1.0.2 blocker

See `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` for the full forensic record.

---

## How to build, install, and uninstall v1.0.2

### Build (the operator's laptop, not the Mini)

```zsh
cd ~/Documents/GitHub/Mining-Guardian
git pull --ff-only origin main
git log -1 --format=%h   # capture the SHA for the filename
./installer/macos-pkg/scripts/build_pkg.sh
# Output: build/MiningGuardian-1.0.2-<sha>.pkg
# Output: build/MiningGuardian-1.0.2-<sha>.pkg.sha256
# Output: build/MiningGuardian-1.0.2-<sha>.notarization-log.txt
```

`build_pkg.sh` reads the version from `pyproject.toml` (single source of truth — now `1.0.2`), stamps it into the build receipt, signs with Apple Developer ID Installer (`Robert Fiesler — ARJZ5FYU94`), submits for notarization (key `FPZJ87B3QF`), and staples the ticket.

### Install (customer end-user laptop — the `.pkg` path)

```zsh
sudo installer -pkg MiningGuardian-1.0.2-<sha>.pkg -target /
# OR double-click the .pkg in Finder.
```

### Install (operations Mac Mini — the `setup.sh` path)

Per B-3 / `docs/INSTALL_PATHS_2026-05-02.md`, the Mini does NOT use the `.pkg`. It uses `setup.sh`:

```zsh
git clone https://github.com/robertfiesler-spec/Mining-Guardian.git
cd Mining-Guardian
chmod +x scripts/setup.sh
# Dry-run first (no sudo, no real config — B-7 / B-8 fixes):
DRY_RUN_INSTALL=true zsh scripts/setup.sh
# Real run with site config (B-2 fix):
sudo -E zsh scripts/setup.sh --config-file=/path/to/MiningGuardian.conf
```

The site config template ships at `installer/macos-pkg/resources/MiningGuardian.conf.template`.

### Verify

```zsh
shasum -a 256 MiningGuardian-1.0.2-<sha>.pkg
pkgutil --check-signature MiningGuardian-1.0.2-<sha>.pkg
# Expected: "Signed by a developer certificate issued by Apple for distribution"
# Expected: Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
spctl --assess --type install MiningGuardian-1.0.2-<sha>.pkg
# Expected: "accepted" + "Notarized Developer ID"
```

### Uninstall (customer laptop)

Same as v1.0.1: `sudo /Library/Application\ Support/MiningGuardian/uninstall.sh` — no path changes in this release.

---

## PRs in this release

- [#106](https://github.com/robertfiesler-spec/Mining-Guardian/pull/106) — B-1 APFS container disk check + B-10 runbook bash→zsh
- [#107](https://github.com/robertfiesler-spec/Mining-Guardian/pull/107) — B-9 catalog count drift → 320 + Grafana SQL-driven rule
- [#108](https://github.com/robertfiesler-spec/Mining-Guardian/pull/108) — B-2 config-file UX + B-7 dry-run skip Phase 2 + B-8 dry-run no sudo
- [#109](https://github.com/robertfiesler-spec/Mining-Guardian/pull/109) — B-3 install path split (.pkg = end-user, setup.sh = Mini ops)

Plus [#105](https://github.com/robertfiesler-spec/Mining-Guardian/pull/105) — Handoff protocol (D-15) + state of system + post-cutover masters (D-16). Doc-only; lays the groundwork for the Monday cutover.

---

## What's not in this release

- B-4 / B-5 / B-6 (see backlog status above)
- The catalog count itself does not change in v1.0.2; stays at 320 (last bumped in v1.0.1 train via PR #102). The next catalog growth lands as a separate `feat(catalog)` PR.
- No DB schema migrations.
- No Postgres / Grafana / Ollama version bumps.
- No `.pkg` payload changes from v1.0.1. The signature, notarization, and SSV behavior are identical.

---

## Reverse links

- `docs/INSTALLER_UX_BACKLOG_2026-05-01.md` — B-1 through B-13 forensic record
- `docs/INSTALL_PATHS_2026-05-02.md` — install-path architecture (B-3 close-out)
- `docs/CATALOG_DYNAMIC_COUNT_RULE_2026-05-02.md` — catalog-count rule (B-9 close-out)
- `docs/MG_UNIFIED_TODO_LIST.md` §17 — backlog status
- `docs/RELEASE_NOTES_v1.0.1.md` — previous release
- `docs/DECISIONS.md` D-15, D-16 — handoff protocol and post-cutover masters
