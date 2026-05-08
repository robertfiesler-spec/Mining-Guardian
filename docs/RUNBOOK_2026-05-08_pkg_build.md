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
