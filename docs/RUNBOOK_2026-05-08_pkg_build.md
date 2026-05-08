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
