# Runbook — 2026-05-08 — Build, sign, notarize, and staple `MiningGuardian-1.0.3-eecde3a94c5b.pkg`

**Audience:** future-Bobby (or any operator) verifying which pkg corresponds to which `main` commit, plus any agent reading the pkg state at session start.
**Scope:** **build receipt for the post-P-031 v1.0.3 .pkg.** This is NOT the comprehensive build-from-scratch runbook — for that, see `docs/RUNBOOK_2026-04-28_pkg_build.md` and `docs/RUNBOOK_PKG_REBUILD.md`. This file is the audit trail for the build that happened on 2026-05-08.

---

## Identity

| Field | Value |
|---|---|
| Source `main` commit | `eecde3a` (full SHA `eecde3a94c5bfb3e102d50596eb25a1b447e7356`) |
| Source `main` commit message | `Merge pull request #165 from robertfiesler-spec/mg/p031-ollama-model-from-env` |
| Pkg path on build Mac | `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-eecde3a94c5b.pkg` |
| Pkg SHA-256 | `dbe5c653ec375eec696df3538aef8d7525d852f1f7e5a4795162f7c836fe49ec` |
| Pkg sidecar | `MiningGuardian-1.0.3-eecde3a94c5b.pkg.sha256` (next to the pkg, contains the SHA-256 above) |
| Pkg size | ~510 MB |
| Build host | Bobby's Mac (Tailscale `100.103.185.53`, `/Users/BigBobby`) |
| Build commands invoked from | **Mac Terminal directly** — the agent bridge could not run `pkgbuild` against the build host today (a known limitation; not a regression) |
| Signing identity | `Developer ID Installer: Robert Fiesler (ARJZ5FYU94)` |
| Notarization submission ID | `0c886b5e-024a-4770-b6ad-894655f27a93` |
| Notarization status | Accepted |
| Stapler | `xcrun stapler validate` returned `The validate action worked!` |
| Gatekeeper | `spctl --assess -t install -v` returned `accepted` with source `Notarized Developer ID` |
| `pkgutil --check-signature` | trusted by the Apple notary service |
| Signed timestamp | `2026-05-08 18:10:51 +0000` |

---

## What this build contains (delta from the prior build on the Mini)

The Mini is currently running `MiningGuardian-1.0.3-b6ecb6a7c0ee.pkg`
(post-P-028). This new build adds the four PRs merged on 2026-05-08:

| PR | P-NN | Headline |
|----|------|----------|
| #162 | P-030 | scanner: add `ai/` to early `sys.path` so `run_once()` resolves `knowledge_manager` |
| #163 | P-032 | discovery-sink: chmod atomic-write tmp file to 0664 before replace |
| #164 | P-029 (knowledge) | installer: ship baseline `knowledge.json` (3.74 MB, SHA-256 prefix `2edea974d711`, 96 profiles / 133 fingerprints / 61 insights) in payload; D-29 locked |
| #165 | P-031 | scanner+ai+installer: resolve Ollama model from env, drop never-pulled `qwen2.5:32b` fallback |

For the full PR-by-PR detail, see
`docs/handoffs/HANDOFF_2026-05-08_P030_P032_P029_P031_DAY_LOG.md`.

---

## Why the build had to be invoked from the Mac Terminal directly

The agent bridge in this session could exec arbitrary commands on
the agent's sandbox (Linux), but could not exec `pkgbuild` /
`productbuild` / `codesign` / `xcrun notarytool` against the build
Mac. Bobby's Mac was reachable for read-side operations (file
list, log read, git operations), but not for the pkg toolchain.
This is consistent with prior weeks; the build path has always
required Bobby's Mac. Captured here so future sessions don't try
to delegate `pkgbuild` to the bridge.

---

## Pre-install verification (paste-along on the Mini or build Mac)

Before installing on the Mini, all of these must succeed. **Stop
and do not install if any of the four checks fails.**

```bash
# 1. SHA-256 must match the sidecar.
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian/build
shasum -a 256 MiningGuardian-1.0.3-eecde3a94c5b.pkg
cat MiningGuardian-1.0.3-eecde3a94c5b.pkg.sha256
# Both must print:
#   dbe5c653ec375eec696df3538aef8d7525d852f1f7e5a4795162f7c836fe49ec
```

```bash
# 2. Pkg must be signed by the trusted Developer ID Installer cert
#    AND notarized by Apple. pkgutil walks the chain.
pkgutil --check-signature MiningGuardian-1.0.3-eecde3a94c5b.pkg
# Expected output includes:
#   Status: signed by a developer certificate issued by Apple for distribution
#   Notarization: trusted by the Apple notary service
#   Signed Time: 2026-05-08 18:10:51 +0000
#   1. Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
```

```bash
# 3. Stapler must validate the notarization ticket embedded in the pkg.
xcrun stapler validate MiningGuardian-1.0.3-eecde3a94c5b.pkg
# Expected: The validate action worked!
```

```bash
# 4. Gatekeeper must accept the pkg as Notarized Developer ID.
spctl --assess -t install -v MiningGuardian-1.0.3-eecde3a94c5b.pkg
# Expected: accepted
#           source=Notarized Developer ID
```

If any of the four returns a different value, **stop**. Do not
install. The pkg may have been modified or rebuilt since the
build above.

---

## Install on the Mini (paste-along)

Once all four pre-install checks pass:

```bash
# 1. Copy the pkg + sidecar to the Mini (Tailscale or USB, operator's choice).
#    Example via Tailscale (Bobby's Mac → Mini):
scp /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-eecde3a94c5b.pkg \
    /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-eecde3a94c5b.pkg.sha256 \
    miningguardian@100.69.66.32:/tmp/

# 2. On the Mini, re-verify SHA-256 matches the sidecar.
ssh miningguardian@100.69.66.32 'cd /tmp && shasum -a 256 -c MiningGuardian-1.0.3-eecde3a94c5b.pkg.sha256'
# Expected: MiningGuardian-1.0.3-eecde3a94c5b.pkg: OK

# 3. On the Mini, re-verify Gatekeeper still accepts (in case of in-flight tampering).
ssh miningguardian@100.69.66.32 'spctl --assess -t install -v /tmp/MiningGuardian-1.0.3-eecde3a94c5b.pkg'
# Expected: accepted, source=Notarized Developer ID

# 4. On the Mini, install.
ssh miningguardian@100.69.66.32 'sudo installer -pkg /tmp/MiningGuardian-1.0.3-eecde3a94c5b.pkg -target /'
# Expected: rc=0
```

---

## Post-install verification (paste-along on the Mini)

Run these after the `installer` command returns rc=0:

```bash
# A. Postinstall log markers (P-029 knowledge upgrade branch).
sudo grep -E 'P-029: preserved existing runtime knowledge.json' \
  /Library/Application\ Support/MiningGuardian/logs/install.log
# Expected: exactly one line.

sudo grep -E 'P-029: staged packaged seed' \
  /Library/Application\ Support/MiningGuardian/logs/install.log
# Expected: exactly one line referencing
#   incoming/knowledge-seed-1.0.3-eecde3a.json
```

```bash
# B. .env contains OLLAMA_URL + OLLAMA_MODEL (P-031).
sudo grep -E '^OLLAMA_URL=|^OLLAMA_MODEL=' \
  /Library/Application\ Support/MiningGuardian/.env
# Expected:
#   OLLAMA_URL=http://127.0.0.1:11434/api/generate
#   OLLAMA_MODEL=llama3.2:3b              (16 GB tier)   OR
#   OLLAMA_MODEL=qwen2.5:14b-instruct-q4_K_M   (24 GB+ tier per D-13)
```

```bash
# C. config.json has the env: placeholders (P-031).
sudo python3 -c '
import json
with open("/Library/Application Support/MiningGuardian/config.json") as f:
    c = json.load(f)
print("ollama_url   =", c.get("ollama_url"))
print("ollama_model =", c.get("ollama_model"))
'
# Expected:
#   ollama_url   = env:OLLAMA_URL
#   ollama_model = env:OLLAMA_MODEL
```

```bash
# D. All 10 services loaded; none exit-127-looping.
sudo launchctl list | grep com.miningguardian | wc -l
# Expected: at least 10 (10 services + 11 scheduled-job plists may
# also appear; counter inclusive of both).
sudo launchctl print system/com.miningguardian.scanner | head -40
# Expected: 'last exit code = 0' or 'pid = <nonzero>' (running).
```

After at least one full scan completes (give it ~5 minutes after
install for the first scan window):

```bash
# E. discovery sink at 0664 (P-032).
stat -f '%Lp %N' \
  /Library/Application\ Support/MiningGuardian/cron_tracking/scanner_discovery/latest_findings.json
# Expected: 664 ...latest_findings.json
# Repeat after a second scan; the value must NOT drift back to 600.
```

```bash
# F. No knowledge_manager import error (P-030).
sudo grep -E 'Knowledge update skipped|No module named .knowledge_manager.' \
  /Library/Application\ Support/MiningGuardian/logs/guardian.log
# Expected: no matches on any timestamp newer than the install.
```

```bash
# G. No Ollama 404 error (P-031).
sudo grep -E 'Qwen scan analysis failed: HTTP Error 404' \
  /Library/Application\ Support/MiningGuardian/logs/guardian.log
# Expected: no matches on any timestamp newer than the install.
```

```bash
# H. No Permission denied in scanner stderr.
sudo grep -E 'Permission denied' \
  /Library/Application\ Support/MiningGuardian/logs/scanner.err.log
# Expected: no matches.
```

If A through H all return the expected values, the install is
green and the four PRs merged today have all taken effect on the
Mini.

---

## Catalog parity audit (run after install — gates ROBS-PC / VPS decommissioning)

Per the weekend audit-and-migrate strategy, ROBS-PC and the VPS
stay up until the Mini's catalog has parity with the canonical
post-cutover state. Run this on the Mini once SSH access is
restored or by the operator directly:

```bash
sudo docker exec mining-guardian-db psql -U mg_catalog -d mining_guardian_catalog -c "
  SELECT 'miner_models'   AS t, COUNT(*) FROM hardware.miner_models
  UNION ALL SELECT 'model_aliases',  COUNT(*) FROM hardware.model_aliases
  UNION ALL SELECT 'manufacturers',  COUNT(*) FROM hardware.manufacturers
  UNION ALL SELECT 'sources',        COUNT(*) FROM hardware.sources
  UNION ALL SELECT 'contributors',   COUNT(*) FROM hardware.contributors
  UNION ALL SELECT 'field_registry', COUNT(*) FROM hardware.field_registry
;"
```

Expected baselines:

| Table | Expected count |
|---|---|
| `hardware.miner_models` | 320 |
| `hardware.model_aliases` | 14338 |
| `hardware.manufacturers` | 17 |
| `hardware.sources` | 15 |
| `hardware.contributors` | 1 |
| `hardware.field_registry` | 0 (intentional baseline) |

If all six match, parity is proven and ROBS-PC / VPS can be
decommissioned in a separate, deliberate session. If any value
differs, **stop** and do not decommission — the canonical copy on
ROBS-PC + the historical archive on the VPS remain the safety net.

---

## Reference

- Canonical handoff: `docs/handoffs/HANDOFF_2026-05-08.md`
- Long-form day log: `docs/handoffs/HANDOFF_2026-05-08_P030_P032_P029_P031_DAY_LOG.md`
- D-29 (knowledge.json filesystem contract): `docs/DECISIONS.md` D-29
- D-13 (RAM-tier LLM model selection): `docs/DECISIONS.md` D-13
- Comprehensive build-from-scratch runbook: `docs/RUNBOOK_2026-04-28_pkg_build.md`
- Rebuild + USB + GitHub Release runbook: `docs/RUNBOOK_PKG_REBUILD.md`
- Apple Developer credentials notes (off-repo): `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt`

---

## Post-build update (2026-05-08 evening)

The `MiningGuardian-1.0.3-eecde3a94c5b.pkg` documented above was
**installed on the customer Mini** later the same day. Build stamp
on the Mini matches `eecde3a94c5bfb3e102d50596eb25a1b447e7356`.
Post-install verification passed every gate — see
`docs/handoffs/HANDOFF_2026-05-08.md` "Post-install verification on
the Mini" for the full list (knowledge.json size + sha + profile
counts; OLLAMA env / config.json correct; scanner completed and
persisted to Postgres; `latest_findings.json` mode 0664).

Two new latent bugs surfaced live-only (the test suite did not catch
them) and were fixed and merged the same day as **PR #168** (P-034
Qwen scan path + P-035 KnowledgeManager `total_flags` backfill +
writer-race sweep across 7 sites), squash `33bac6f` on merge
`1327060`. **PR #167** (P-034-only) was closed as superseded by #168;
no code from #167 reached `main`.

PR #168 is **pure Python source** — no installer, payload,
postinstall, plist, schema, migration, or notarization changes. As a
result this `eecde3a` package remains a valid distribution artifact
and **was NOT regenerated**. The package on the Mini is the same one
documented above (SHA-256 still
`dbe5c653ec375eec696df3538aef8d7525d852f1f7e5a4795162f7c836fe49ec`).

The decision matrix for delivering the P-034 + P-035 fix to the Mini
(git pull vs. rebuild from `main` 1327060) is in
`docs/handoffs/HANDOFF_2026-05-08.md` under "Next exact steps". For
fresh-install media for the next customer Mini, a rebuild from `main`
1327060 is the recommended step so the new build does not ship with
the same drift.

---

## Late afternoon update (2026-05-08) — `2b41764` rebuild + Mini install + B-45 / P-036 surfaced

After the eecde3a-based audit above, the operator decided to deliver
P-034 + P-035 to the Mini via a fresh package rebuild (Outcome B in
the handoff decision matrix), since the install tree on the Mini is
not git-managed (`git rev-parse --is-inside-work-tree` returned
`not_git`). The rebuild ran from main commit `2b41764` (the merge
commit for PR #166 / docs handoff), which had `33bac6f` (P-034 +
P-035) as a direct ancestor.

| Field | Value |
|---|---|
| Source `main` commit | `2b41764` (full SHA `2b417642121b...`) |
| Source `main` commit message | `Merge pull request #166 from robertfiesler-spec/docs/handoff-2026-05-08-pkg-build` |
| Pkg path on build Mac | `build/MiningGuardian-1.0.3-2b41764a121b.pkg` |
| Pkg SHA-256 (corrected sidecar) | `463ca8d69d4e86ed9be96a76432628f83ee34f00b0764edad73a2c7f85b67387` |
| Notarization | submitted, accepted, stapled, validated |
| Gatekeeper | `spctl --assess -t install -v` → accepted (Notarized Developer ID) |
| Install on Mini | `installer -pkg ... -target /` rc=0 |
| Build stamp on Mini | `version=1.0.3 / git_sha=2b41764a121b / stamped_utc=2026-05-08T20:18:17Z` |

**Note on the SHA-256 sidecar:** the sidecar had to be **regenerated**
(the first sidecar value did not match the actual pkg bytes once the
final stapled artifact was on disk). The corrected sidecar value
above is the only one to use; do not refer to any earlier value as
canonical.

### Postinstall behavior on the Mini (2b41764 build)

All as designed:

- preserved the existing runtime `knowledge.json` (upgrade branch),
- staged the packaged seed under
  `${MG_INSTALL_ROOT}/knowledge/incoming/knowledge-seed-1.0.3-2b41764a121b.json`
  (deterministic name — short SHA matches the build),
- reconciled the Postgres `mg` role and re-verified TCP auth,
- preserved `config.json`,
- finished cleanly.

### What the first scan after install proved (P-034 / P-035 working)

The first post-install scan ran with **exit code 0** and persisted
to Postgres. Logs confirmed every earlier-today fix took effect:

- ❌ `Errno 2 No such file or directory: '/root/Mining-Guardian/knowledge.json.tmp'` — gone (P-034)
- ❌ `Knowledge update skipped: 'total_flags'` — gone (P-035 backfill)
- ❌ `No module named 'knowledge_manager'` — gone (P-030 sys.path)
- ❌ `Qwen scan analysis failed: HTTP Error 404` — gone (P-031 model resolver)
- ✅ `INFO llm_scan_analyses written` lines now appear; the canonical
  file's `llm_scan_analyses` array reached 176 entries — Vision
  Anchor 1's training stream is finally accumulating.

### The new failure mode the same scan exposed (B-45 / P-036)

P-035's `core.file_lock.locked_knowledge_update` and
`atomic_write_json` create a temp file in the parent directory of
the path they were given and call `os.replace(tmp, path)`. When
`path` is the P-029 compat symlink at
`${MG_INSTALL_ROOT}/knowledge.json`, POSIX `rename` overwrites the
**symlink** with a regular file rather than updating the target.
Every active writer computes its target as `_ROOT / "knowledge.json"`
which in the install layout IS the symlink — so the first writer to
fire after install broke the compat path immediately.

Live observation on the Mini at 15:43 (the same day):

- `${MG_INSTALL_ROOT}/knowledge/knowledge.json` (canonical) —
  intact: 3,739,968 bytes, sha256
  `2edea974d711ac0ca648e796468cdb8ca0779fe32539f97a41b8b2f1a921820c`,
  96 miner_profiles, 133 miner_fingerprints, 176 llm_scan_analyses.
- `${MG_INSTALL_ROOT}/knowledge.json` (was symlink) — replaced by a
  root-owned **regular file of 948 bytes**.
- Reads via canonical path kept working; reads via the compat path
  silently saw a stale 948-byte file. A divergence that would
  compound over time. Vision Anchor 1 risk.

### Manual mitigation applied on the Mini before the next scan window

(Already done — listed here for the audit trail, not as instructions.)

1. Quarantined the bad regular file under
   `${MG_INSTALL_ROOT}/knowledge/quarantine/knowledge-json-regular-file-<timestamp>.json`.
2. Removed the regular file at the symlink path.
3. Recreated the symlink:
   `ln -s knowledge/knowledge.json /Library/Application\ Support/MiningGuardian/knowledge.json`
4. `chown -h miningguardian:staff` on the link.
5. Verified with `ls -la` — leading character is `l` (symlink); the
   canonical file is intact.

### P-036 fix landed on `main` after the mitigation

PR #169 (`mg/p036-knowledge-symlink-preserve-canonical-resolver`,
squash `906fa4a`, merge `fab6694`) was opened, reviewed, and merged
the same evening. The fix routes both `locked_knowledge_update` and
`atomic_write_json` through a new private helper
`_resolve_write_target(path)` that, if the supplied path is a
symlink whose target's parent exists, returns the symlink's target
as the rename destination. The temp file lands in the **target's**
parent and `os.replace` lands on the canonical file, leaving the
symlink itself untouched. The lock file is keyed off the resolved
target so two writers — one given the symlink, one given the
canonical path — serialize against the same flock.

Tests on `main` at `fab6694`:

- `tests/test_p036_knowledge_symlink_preserve.py` — **9/9 PASS** (new)
- `tests/test_p035_knowledge_persistence_hardening.py` — **26/26 PASS** (no regression)
- `tests/test_p022_discovery_sink.py` — **23/23 OK** (no regression)

### Status of `2b41764` package — superseded for new install media

The `2b41764` package is **operational and installed on the Mini**,
but it lacks the P-036 fix. It is therefore **superseded for new
install media** by the rebuild from `main` at `fab6694`. The
`fab6694` build is the recommended next-install artifact for both
the existing customer Mini (delivers the P-036 fix) and any
fresh-install media for the next customer.

The `2b41764` package and its corrected sidecar should NOT be
regenerated, deleted, or modified — they are the audit trail for
the install that uncovered B-45.

### Resume from here — `fab6694` rebuild + Mini install (paste-along)

The full one-at-a-time resume sequence (build → notarize → staple →
spctl → transfer → install → verify symlink survives the next scan
→ run VPS/ROBS-PC shutdown gates) is in
`docs/handoffs/HANDOFF_2026-05-08.md` under
`⏸ PAUSED EOD 2026-05-08 — read this FIRST before anything else` →
"Resume plan — pick up here in 1–2 hours (one-at-a-time)". That
section is the canonical resume checklist; this runbook is the
build-receipt half of the same story.

---

## Late evening update (2026-05-08) — `e3461260af2a` package built tonight

After PR #170 (PM pause docs handoff) merged as `e346126`, the
operator built the post-P-036 .pkg from the latest `main` so it would
be ready for tomorrow morning's install. **The package has been
built, signed, notarized, and `spctl`-accepted on the build Mac, but
has NOT been copied to or installed on the Mini yet.**

| Field | Value |
|---|---|
| Source `main` commit | `e346126` (full SHA `e3461260af2a5cc8b40497a019009c4430a1fa32`) |
| Source `main` commit message | `Merge pull request #170 from robertfiesler-spec/docs/handoff-2026-05-08-pm-p036-mini-paused-eod` |
| Pkg path on build Mac | `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-e3461260af2a.pkg` |
| Pkg sidecar | `/Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.3-e3461260af2a.pkg.sha256` |
| Pkg SHA-256 | `6b82bd3954366de3388f74e6c29d60ffe6f1c611e9bde9835bdfa089f0f8706c` |
| Pkg size | ~510 MB |
| Signing identity | `Developer ID Installer: Robert Fiesler (ARJZ5FYU94)` |
| `pkgutil --check-signature` | signed by Apple-issued Developer ID cert; Notarization trusted by the Apple notary service; signed with trusted timestamp `2026-05-09 00:31:15 +0000` |
| `spctl --assess -t install -v` | `accepted`; source `Notarized Developer ID`; origin `Developer ID Installer: Robert Fiesler (ARJZ5FYU94)` |
| `xcrun stapler validate` (via bridge) | **failed** — CloudKit `NSPOSIXErrorDomain` "Operation not permitted" / "validate action failed Error 68" — bridge-only environmental restriction; not a notarization failure (see below) |
| Installed on Mini | **NOT YET** — copy + install is the first action tomorrow morning |

### What this build contains (delta from what's installed on the Mini)

The Mini is currently running `MiningGuardian-1.0.3-2b41764a121b.pkg`
(post-P-035, lacks P-036). The new `e3461260af2a` package adds
exactly one functional PR over that — **PR #169 (P-036, the
symlink-preserving file_lock fix)** — plus the 2026-05-08 evening
documentation merged in PR #170.

### Bridge stapler caveat — why `spctl` and `pkgutil` are the authoritative gates

The bridge that ran `xcrun stapler validate` against the build Mac
tonight returned a CloudKit `NSPOSIXErrorDomain` error — "Operation
not permitted" / "validate action failed Error 68". That code path
needs CloudKit access permissions the bridge does not have in this
session. **It is NOT a notarization failure:**

- `spctl --assess -t install -v` accepted the pkg as **Notarized
  Developer ID**, with origin `Developer ID Installer: Robert
  Fiesler (ARJZ5FYU94)`.
- `pkgutil --check-signature` reported the package is signed by a
  developer certificate issued by Apple for distribution AND that
  the **notarization is trusted by the Apple notary service**, with
  signed timestamp `2026-05-09 00:31:15 +0000`.

If a clean stapler receipt is desired for the audit trail, the
operator may optionally re-run `xcrun stapler validate
build/MiningGuardian-1.0.3-e3461260af2a.pkg` directly from the Mac
Terminal tomorrow morning — that is not a bridge invocation and is
expected to succeed. **Do not block the install on the bridge
stapler error.** `spctl` and `pkgutil` are the authoritative gates
and both passed.

### Tomorrow morning — exact first actions

Run these from the build Mac tomorrow morning, one at a time. The
canonical step-by-step (with R-1 through R-8) is in
`docs/handoffs/HANDOFF_2026-05-08.md` under "Resume plan — pick up
tomorrow morning (one-at-a-time)". Quick reference:

```bash
# 1. Verify the artifact is intact on the build Mac
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian/build
shasum -a 256 MiningGuardian-1.0.3-e3461260af2a.pkg
cat          MiningGuardian-1.0.3-e3461260af2a.pkg.sha256
# Both must print:
#   6b82bd3954366de3388f74e6c29d60ffe6f1c611e9bde9835bdfa089f0f8706c

# 2. Re-verify Apple gates
pkgutil --check-signature MiningGuardian-1.0.3-e3461260af2a.pkg
spctl --assess -t install -v MiningGuardian-1.0.3-e3461260af2a.pkg

# 2b. (Optional) Re-run stapler validate from the Mac Terminal directly
xcrun stapler validate MiningGuardian-1.0.3-e3461260af2a.pkg

# 3. Copy to Mini + re-verify there
scp MiningGuardian-1.0.3-e3461260af2a.pkg \
    MiningGuardian-1.0.3-e3461260af2a.pkg.sha256 \
    miningguardian@100.69.66.32:/tmp/
ssh miningguardian@100.69.66.32 'cd /tmp && \
  shasum -a 256 -c MiningGuardian-1.0.3-e3461260af2a.pkg.sha256 && \
  spctl --assess -t install -v /tmp/MiningGuardian-1.0.3-e3461260af2a.pkg && \
  pkgutil --check-signature   /tmp/MiningGuardian-1.0.3-e3461260af2a.pkg | head -20'

# 4. Install
ssh miningguardian@100.69.66.32 'sudo installer -pkg /tmp/MiningGuardian-1.0.3-e3461260af2a.pkg -target /'

# 5. Verify build stamp BEFORE kickstarting the scanner
ssh miningguardian@100.69.66.32 'sudo cat "/Library/Application Support/MiningGuardian/build_stamp.json"'
# Expected: git_sha contains "e3461260af2a"

# 6. Verify symlink BEFORE kickstart
ssh miningguardian@100.69.66.32 'ls -la "/Library/Application Support/MiningGuardian/knowledge.json"'
# Expected: leading character 'l' (symlink)

# 7. Kickstart scanner ONCE; verify symlink survives + invariants stay green
ssh miningguardian@100.69.66.32 'sudo launchctl kickstart -k system/com.miningguardian.scanner'
sleep 90
# Then run the grep invariants from the handoff R-7b block.
```

After R-7 passes, continue to **R-8 — passover audit shutdown
gates** (catalog row counts, Ollama local tags, no traffic to
ROBS-PC `100.110.87.1` or VPS `100.106.123.83`, optional ROBS-PC
staging research dump). All four gates are gated on the
`e3461260af2a` install completing cleanly first.

### Status of `2b41764` package — operational on the Mini until tomorrow morning

The `2b41764` package is **operational on the Mini at pause time**
but lacks P-036. It is **superseded for the next install** by the
`e3461260af2a` package documented above. The `2b41764` artifact and
its corrected sidecar
(`463ca8d69d4e86ed9be96a76432628f83ee34f00b0764edad73a2c7f85b67387`)
should NOT be regenerated, deleted, or modified — they are the
audit trail for the install that uncovered B-45.

### Status of `eecde3a94c5b` package — superseded; do not install

The earlier `eecde3a94c5b` package (post-P-031) is two PRs behind the
new `e3461260af2a` build (it lacks P-034 + P-035 + P-036). It should
not be installed; keep on disk as audit trail only.

---

## ✅ 2026-05-09 Saturday addendum — final installed-green build `53eac9397f00`

> Appended on 2026-05-09. Everything above this section is historical
> context — the `e3461260af2a` build was superseded by today's
> post-P-037 build before being installed on the Mini.

### Why a second build was needed

Yesterday's `e3461260af2a` package was post-P-036 only. PR #172
(P-037 — owner/mode normalization on canonical knowledge writes)
merged into `main` 2026-05-08 evening as squash `0ea9f4b` on merge
`53eac93`. P-037 is plain-Python only — no installer, payload,
postinstall, plist, schema, migration, or notarization changes —
but the Mini's installed tree is NOT git-managed (`git rev-parse
--is-inside-work-tree` → `not_git`), so delivery to the Mini
required a fresh `.pkg` rebuild. Bundling P-037 into the same
build as P-036 (rather than two separate notarization rounds) was
the cleanest path and is what the operator did this morning.

### Build receipt — `MiningGuardian-1.0.3-53eac9397f00.pkg`

```
Build Mac:           /Users/BigBobby/Documents/GitHub/Mining-Guardian
Built from:          main @ 53eac9397f00 (PR #172 P-037 merge)
Artifact:            build/MiningGuardian-1.0.3-53eac9397f00.pkg
Sidecar:             build/MiningGuardian-1.0.3-53eac9397f00.pkg.sha256
SHA-256:             bd482a2e5d1cb35eeeee584d44c57618082baccd04d93db743f8a75823ab61f4
Notarization ID:     de02bda6-c1a2-4540-98df-3304cf7a71c2
Notarization status: Accepted
spctl --assess:      accepted
                     source = Notarized Developer ID
                     origin = Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
pkgutil --check-signature: signed by Apple-issued Developer ID Installer cert
                           Notarization trusted by Apple notary service
                           Signed Time: 2026-05-09 14:33:30 +0000
xcrun stapler validate:    accepted (this morning, run from Mac Terminal directly —
                           the bridge stapler error from 2026-05-08 PM was a
                           bridge-only environmental restriction, confirmed today
                           when the same stapler ran cleanly outside the bridge)
```

### Mini install — completed 2026-05-09

```
Pkg copied to Mini:  /tmp/MiningGuardian-1.0.3-53eac9397f00.pkg
shasum -a 256 -c:    SHA_OK
Mini spctl --assess: accepted
Mini pkgutil:        trusted by Apple notary
installer rc:        0
Mini build_stamp:    version=1.0.3
                     git_sha=53eac9397f00
                     stamped_utc=2026-05-09T14:32:02Z
```

### First post-install scan — ✅ green

```
launchctl last_exit_code: 0
Postgres scan #22:        saved
Qwen analysis:            succeeded
guardian.log:             "INFO llm_scan_analyses written, now 180 entries"

Canonical knowledge file:
  path:        /Library/Application Support/MiningGuardian/knowledge/knowledge.json
  size_bytes:  3,752,370
  sha256:      c92839a4341cb490e65785cf5ec82eaa6d791aadeb9ba247ed1e8b08b05a2de4
  miner_profiles:     104
  miner_fingerprints: 133
  llm_scan_analyses:  180
  octal:       664
  owner:       miningguardian
  group:       staff                       # P-037 verified ✅

Compat symlink:
  path:        /Library/Application Support/MiningGuardian/knowledge.json
  type:        symlink (leading 'l' in ls -la)
  target:      knowledge/knowledge.json    # P-036 verified ✅ — survived the
                                           # scanner's atomic write

Discovery sink rolling snapshot:
  path:        /Library/Application Support/MiningGuardian/cron_tracking/scanner_discovery/latest_findings.json
  octal:       664
  owner:       miningguardian
  group:       staff                       # P-037 verified ✅

Log invariants (zero matches on any timestamp newer than the install):
  /root/Mining-Guardian
  Knowledge update skipped
  total_flags missing
  miner_profiles missing
  Qwen scan analysis failed: HTTP Error 404
  Permission denied
```

(Older warning lines from 2026-05-08 still exist in the rolled log
files; they are historical and are not regenerated by today's
scan.)

### Mini self-contained checks — ✅ all passed

```
Ollama tags:          curl 127.0.0.1:11434/api/tags  →  llama3.2:3b   (D-13 16-GB tier)
Dashboard/API health: 127.0.0.1:8590/health  →  status=ok, version=2.3.0,
                                                models=278, correction_rules=3
Postgres container:   docker ps  →  mining-guardian-db, 127.0.0.1:5432->5432
No old-host TCP:      lsof -i @100.110.87.1     →  NO_OLD_HOST_TCP   (ROBS-PC)
                      lsof -i @187.124.247.182  →  NO_OLD_HOST_TCP   (VPS)
                      lsof -i @100.106.123.83   →  NO_OLD_HOST_TCP   (VPS Tailscale)
```

### Catalog row counts captured (parity caveat — see HANDOFF)

```
manufacturers   = 17
miner_models    = 324
model_aliases   = 101    # diverges from older 14338 baseline; captured as
                         # follow-up parity review — does NOT block green state
                         # because dashboard health endpoint reports models=278
                         # and the catalog importer is operating without errors
contributors    = 4
field_registry  = 75
sources         = 23
```

See `docs/handoffs/HANDOFF_2026-05-08.md` "Catalog parity caveat"
under the 2026-05-09 addendum for the full reasoning. The next
session should reconcile expected vs observed and update the
canonical baseline, but the gates that matter for green state
(scanner exit, Qwen accumulation, no-traffic to old hosts) all
passed cleanly.

### Status of earlier packages

- `MiningGuardian-1.0.3-53eac9397f00.pkg` — **CURRENT, OPERATIONAL
  ON MINI.** Do not rebuild over.
- `MiningGuardian-1.0.3-e3461260af2a.pkg` — superseded by the
  53eac9397f00 build before being installed on the Mini. Lacks
  P-037. Keep on disk as audit trail only; do not install.
- `MiningGuardian-1.0.3-2b41764a121b.pkg` — was operational on the
  Mini until the 53eac9397f00 install today. Lacks P-036 + P-037.
  Keep on disk as audit trail only; do not install.
- `MiningGuardian-1.0.3-eecde3a94c5b.pkg` — three PRs behind. Audit
  trail only; do not install.

### Apple notary submissions chronology

| Submission ID | Pkg | Built from | Status | Disposition |
|---|---|---|---|---|
| (earlier) | eecde3a94c5b | post-P-031 | Accepted | superseded; audit trail only |
| (2b41764) | 2b41764a121b | post-P-035 | Accepted | superseded after 53eac9397f00 install |
| (e3461260) | e3461260af2a | post-P-036 | Accepted | superseded by 53eac9397f00 before Mini install |
| `de02bda6-c1a2-4540-98df-3304cf7a71c2` | **53eac9397f00** | **post-P-037 (current)** | **Accepted** | **OPERATIONAL ON MINI** |

### Forward caution

- **Do not regenerate, delete, or modify** the build artifact at
  `build/MiningGuardian-1.0.3-53eac9397f00.pkg` or its sidecar.
  They are the audit trail for the currently-installed Mini binary.
- **Do not decommission VPS or ROBS-PC** until the operator
  completes the controlled shutdown window (optional ROBS-PC
  research-data dump + deliberate power-off). All four passover-
  audit gates passed live on the Mini today, but the controlled-
  shutdown step is operator-driven, not automated.

---

## 2026-05-10 Sunday addendum — VPS + ROBS-PC isolation crossover (Mini sole runtime)

This addendum records the Sunday 2026-05-10 morning crossover. **No new
pkg was built or installed today.** The Mini stayed pinned at
`MiningGuardian-1.0.3-53eac9397f00.pkg` (`git_sha=53eac9397f00`,
`stamped_utc=2026-05-09T14:32:02Z`) through the entire isolation
window. The crossover stopped Mining Guardian / Grafana / Postgres on
the legacy VPS and stopped Ollama on ROBS-PC, leaving the Mini as the
**sole active Mining Guardian runtime**. Both legacy hosts remain
powered for rollback / observation; full power-off is deferred.

For the full operator-side narrative see
`docs/handoffs/HANDOFF_2026-05-08.md` under
"✅ RESOLVED 2026-05-10 — Sunday VPS + ROBS-PC isolation crossover".

### Pre-isolation Mini gate (load-bearing — captured as the rollback baseline)

```
Mini scanner last_exit_code:           0
Final Saturday scanner logs:           green (zero matches for the seven invariants on any timestamp newer than the 2026-05-09 install)
Knowledge canonical perms:             0664 miningguardian:staff   # P-037 holding
Knowledge compat symlink:              symlink (leading 'l')        # P-036 holding
Discovery sink rolling snapshot perms: 0664 miningguardian:staff   # P-037 holding
Ollama tags (curl 127.0.0.1:11434):    llama3.2:3b   # D-13 16-GB tier
Dashboard/API health:                  127.0.0.1:8590/health → status=ok
Local Postgres container:              mining-guardian-db at 127.0.0.1:5432
No old-host TCP (pre-isolation):       NO_OLD_HOST_TCP for ROBS-PC (100.110.87.1)
                                       NO_OLD_HOST_TCP for VPS (187.124.247.182)
                                       NO_OLD_HOST_TCP for VPS Tailscale (100.106.123.83)
```

The Mini was already independent of VPS + ROBS-PC at the START of the
isolation window; today's crossover is the formal sign-off, not the
cutover itself. The cutover landed in the eight-week train P-029 →
P-037 that was installed on 2026-05-09.

### ROBS-PC isolation

```
docker ps                              0 running containers
Notable processes pre-stop             Docker Desktop, Ollama
Action                                 stopped Ollama processes
Get-Process ollama* (post-stop)        no output (Ollama processes gone)
Power state after isolation            powered (kept up for rollback / staging-research dump)
MG runtime dependency after isolation  none active
```

ROBS-PC stays powered for rollback and the optional staging-research
data dump. There is no longer any Mining Guardian runtime active on
ROBS-PC.

### VPS isolation (in this exact order)

```
Initial running services pre-isolation:
  - approval-api
  - dashboard-api
  - grafana-server
  - intelligence-report
  - mining-guardian-alerts
  - mining-guardian
  - overnight-automation
  - slack-commands
  - slack-listener
  - postgresql@16-main

Order:
  1. Stop the 8 MG services + Grafana (one rollback step from
     a fully working VPS).
  2. Re-verify Mini still green BEFORE touching Postgres on the
     VPS — load-bearing safety check; confirms no Mini-side
     dependency on VPS Postgres.
  3. Stop postgresql@16-main on the VPS.
  4. Confirm only Prometheus port 9090 remains listening.

Remaining listening ports after isolation: Prometheus 9090 only
MG / Postgres / Grafana / API ports left:  none
Power state after isolation:               powered (kept up for rollback / observation window)
```

### Post-isolation Mini proof — ✅ green

```
No old-host TCP (post-isolation):      NO_OLD_HOST_TCP for all three (ROBS-PC, VPS, VPS Tailscale)
Dashboard/API health:                  127.0.0.1:8590/health → status=ok
Local Postgres container:              mining-guardian-db at 127.0.0.1:5432
Manual scanner kickstart (one shot):
  launchctl last_exit_code:            0
  Postgres scan #25 saved:             yes   # was scan #22 at the 2026-05-09 install;
                                             # 3 hourly scheduled scans completed between
                                             # Saturday and this manual kickstart — the
                                             # launchd cron path is intact end-to-end.
  Qwen analysis:                       succeeded
  guardian.log:                        "INFO llm_scan_analyses written, now 183 entries"
                                       "INFO Knowledge saved — 50 known issues, 7 patterns"

Log invariants (zero matches on any timestamp newer than the isolation window):
  /root/Mining-Guardian
  Knowledge update skipped
  Qwen scan analysis failed: HTTP Error 404
  Permission denied

Knowledge / sink perms after kickstart:
  knowledge/knowledge.json             0664 miningguardian:staff   # P-037 holds
  knowledge.json (compat symlink)      symlink (leading 'l')        # P-036 holds
  cron_tracking/scanner_discovery/
    latest_findings.json               0664 miningguardian:staff   # P-037 holds
```

### Scheduled-job audit captured (Mini-local, non-blocking — P-038 follow-up)

The morning audit of the Mini's launchd-driven scheduled jobs found
**7 failures**. None of the 7 affect the operational scan/decision
loop, the VPS / ROBS-PC isolation, or the Mini's green state. They
are recorded here for the build runbook's audit trail; the canonical
records live in:

- `docs/handoffs/HANDOFF_2026-05-08.md` (2026-05-10 RESOLVED section)
- `docs/MG_UNIFIED_TODO_LIST.md` row 10ad (P-038)
- `docs/LATENT_BUGS.md` entry B-47 (P-038)

| # | Failing job | Symptom | Fix bucket |
|---|---|---|---|
| 1 | `catalog_import` | shell heredoc bug | shell quoting |
| 2 | `log_failure_report` | `timestamptz` vs `text` cast bug | SQL cast |
| 3 | `daily_deep_dive` | `timestamptz` vs `text` cast bug | SQL cast |
| 4 | `refinement_chain` | missing `ANTHROPIC_API_KEY` | env / secret provisioning |
| 5 | `weekly_training` | missing Claude key + `datetime` slicing bug | env / secret + Python coercion |
| 6 | `db_maintenance` | Linux-native `pg_*` script (assumes Postgres on the host, not Colima) | macOS-portable rewrite |
| 7 | `ams_cleanup` | hardcoded `/root/Mining-Guardian/config.json` (legacy retired Linux dev path) | path resolution via `MG_INSTALL_ROOT` |

**Why this is non-blocking for the crossover:** items 1, 2, 3, 6, 7
are LLM-feeding / catalog-import / cleanup paths that do not gate the
operational scan/decision loop. Items 4 and 5 are Anthropic-API-keyed
paths only Bobby's proof-of-concept Mini runs, and the env-var
provisioning is independent of the crossover. **All 7 should ship in
their own small surgical PRs — do not bundle.**

### Status of earlier packages (carries forward unchanged from 2026-05-09)

`MiningGuardian-1.0.3-53eac9397f00.pkg` remains **CURRENT, OPERATIONAL
ON MINI** through the 2026-05-10 crossover. No new build was produced
today; all earlier-package "audit trail only; do not install" rules
still hold.

### Forward caution — addendum

- **Do not power off VPS or ROBS-PC** during the observation window.
  Both hosts stay powered-but-isolated until the operator makes the
  controlled-shutdown call after one clean Mini scheduled-scan cycle.
- **Do not re-enable any stopped VPS service** to "test." A rollback,
  if ever needed, is its own deliberate session — not a smoke-test
  poke.
- **Do not bundle P-038 fixes with any other concern.** Each of the
  7 scheduled-job failures is a small surgical fix; bundling them is
  how Failure Mode 9 (stacked PRs) recurs.
- The 2026-05-09 forward caution above (do not regenerate the
  53eac9397f00 build artifact; do not decommission VPS / ROBS-PC
  before the controlled-shutdown window) **all continues to apply.**
