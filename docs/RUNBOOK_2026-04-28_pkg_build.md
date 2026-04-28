# Runbook — 2026-04-28 — Building, signing, and notarizing the Mining Guardian .pkg

**Audience:** future-Bobby (or any operator) on a clean Mac with the repo cloned.
**Goal:** turn `main` into a signed, notarized, stapled, Gatekeeper-accepted `.pkg` that the customer can double-click.
**Reading order:** read this once end-to-end before you run anything. Then run from the top.

This document is **paste-along**: every shell block is intended to be copy-pasted into Terminal as-is.

---

## Block A — One-time host setup (only needed if certs/keys were never installed)

If the Mac you're on has never built the `.pkg` before, you need:

1. Both Developer ID certs in the login keychain.
2. Both Apple intermediate CAs in the System keychain (otherwise `find-identity -v` returns 0 valid identities — see Block X for the diagnosis).
3. The `.p8` notarization key on disk.
4. `CREDENTIALS_NOTES.txt` populated with 6 `KEY=VALUE` lines.

### A.1 — Import the leaf certs (and their private keys)

The two `.cer` files plus their private keys live in `/Users/BigBobby/Documents/Apple Cert/`:

```bash
cd "$HOME/Documents/Apple Cert"
ls -1 | grep -E '\.(cer|p12|p8)$'
```

Expected:

```
AuthKey_FPZJ87B3QF.p8
developerID_application.cer
developerID_installer2.cer
```

If the certs were imported through Keychain Access GUI (the normal path on a developer Mac), they're already in `~/Library/Keychains/login.keychain-db`. Verify:

```bash
security find-identity -p basic -v
```

Expected (after Block A.2 if intermediates are missing):

```
1) 3A92362E47C40BE6A9A60C8D4EAB85E5CA0EB3D5 "Developer ID Application: Robert Fiesler (ARJZ5FYU94)"
2) 2CB9429B5D64274D152E2CD5A8E0E66D1DB26AB9 "Developer ID Installer: Robert Fiesler (ARJZ5FYU94)"
     2 valid identities found
```

If you see `0 valid identities found` even though both `.cer`s are imported, do Block A.2.

### A.2 — Import the Apple intermediate CAs

This was the bug that bit us on 2026-04-28 morning. The leaf certs need a complete chain back to Apple Root CA, and the two intermediates aren't installed by default.

```bash
cd /tmp
curl -sO https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
curl -sO https://www.apple.com/certificateauthority/DeveloperIDCA.cer
sudo security import DeveloperIDG2CA.cer -k /Library/Keychains/System.keychain
sudo security import DeveloperIDCA.cer   -k /Library/Keychains/System.keychain
```

Then re-run `security find-identity -p basic -v`. You should now see 2 valid identities.

**Ignore:** the Keychain Access GUI showing "certificate is not trusted" in red on the leaf certs. This is a known cosmetic-only macOS UI bug. `codesign` and `productsign` work correctly. Do not try to "fix" it.

### A.3 — Populate CREDENTIALS_NOTES.txt

The build script reads exactly 6 `KEY=VALUE` lines from this file and ignores everything else. The file path is hardcoded in `build_pkg.sh`:

```
/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt
```

The bottom of that file must contain a block exactly like this (the prose above can be anything):

```
APPLE_TEAM_ID=ARJZ5FYU94
APPLE_NOTARIZATION_KEY_ID=FPZJ87B3QF
APPLE_NOTARIZATION_ISSUER_UUID=f53661a7-931a-4976-8f8e-82353256931a
APPLE_NOTARIZATION_KEY_PATH=/Users/BigBobby/Documents/Apple Cert/AuthKey_FPZJ87B3QF.p8
APPLE_DEV_ID_INSTALLER=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
APPLE_DEV_ID_APPLICATION=Developer ID Application: Robert Fiesler (ARJZ5FYU94)
```

Verify:

```bash
grep '^APPLE_' "$HOME/Documents/Apple Cert/CREDENTIALS_NOTES.txt"
```

Should print exactly 6 lines, in the order above.

### A.4 — Populate the vendor directory

`step_4_assemble_payload` rsyncs `~/MiningGuardian-vendor/` into the .pkg payload. It must contain four subdirs:

```
~/MiningGuardian-vendor/
├── colima/        # Colima + lima binaries (arm64), libexec/bin/, share/lima/
├── docker/        # static arm64 docker CLI binary
├── images/        # postgres-16-bookworm.tar (saved from `docker save`)
└── ollama/        # Ollama.app drag-copied from the dmg
```

Total ~767 MB on 2026-04-28. Verify:

```bash
du -sh "$HOME/MiningGuardian-vendor"
ls -1  "$HOME/MiningGuardian-vendor"
```

If any subdir is missing, the build proceeds (with a WARN that postinstall will fail at install time on the customer Mac). Don't ship a .pkg without all four.

### A.5 — Clean up stale launchd agents (only on operator dev Macs)

This is a **one-shot** on operator dev Macs that ran early prototypes from typo'd paths. The customer Mini will be sealed/fresh — no cleanup needed there.

```bash
ls ~/Library/LaunchAgents/ | grep -E '(bixbit|miningguardian|mining-guardian)' || echo "clean"
```

If anything matches, do:

```bash
for plist in ~/Library/LaunchAgents/com.bixbit.*.plist ~/Library/LaunchAgents/com.miningguardian.*.plist; do
    [[ -f "$plist" ]] || continue
    label="$(basename "$plist" .plist)"
    launchctl bootout "gui/$UID/$label" 2>/dev/null || true
    rm -f "$plist"
done
ls ~/Library/LaunchAgents/  # should be MG-free
```

The `com.bixbit.mining-guardian` one had `ThrottleInterval=30` and was respawning every 30 s, spamming `~/Library/Logs/launchd_stderr.log`. If your Console is loud, this is why.

---

## Block B — Build the .pkg

```bash
cd /Users/BigBobby/Documents/GitHub/Mining-Guardian
git fetch origin
git checkout main
git pull origin main
make pkg 2>&1 | tee /tmp/mg_pkg_build_$(date +%s).log
```

This runs the 9-step pipeline in `installer/macos-pkg/scripts/build_pkg.sh`:

| # | Step | Time | Notes |
|---|---|---|---|
| 1 | Verify creds + signing identities in keychain | <1 s | Reads `CREDENTIALS_NOTES.txt`, validates both Application + Installer ID present. |
| 2 | Refuse to build with a dirty git tree | <1 s | Commit, stash, or clean before running. |
| 3 | Stamp the build with version + git SHA | <1 s | Reads `version` from `pyproject.toml`. |
| 4 | Assemble the payload | 10–30 s | rsyncs app code + vendor dir into `build/stage/payload/`. |
| 4b | Codesign inner binaries (NEW) | 30 s – 3 min | Two-pass: re-seals `.app`/`.framework` bundles via `--deep`, codesigns loose Mach-O via `--force`. Then `--verify --deep --strict`. Each `--timestamp` round-trips Apple's timestamp server. |
| 5 | pkgbuild + productbuild + productsign | 30–60 s | Outer .pkg signed with Developer ID Installer. |
| 6 | Notarize via notarytool with --wait | **5–15 min, sometimes longer** | This is the slow part. `notarytool --wait` is silent for minutes at a time. Anything <30 min is normal. |
| 7 | Staple the notarization ticket | 5 s | |
| 8 | SHA-256 sidecar + spctl Gatekeeper check | 5 s | |
| 9 | Print install banner | <1 s | |

If a step fails, the script `_die`s with an exit code 40–47 and a path to the relevant log. Common failures and recoveries are in Block C.

### B.1 — What "good" looks like

You should see, in order:

```
[build_pkg] step 1 OK: credentials reachable, both signing identities in keychain
[build_pkg] step 2 OK: clean git tree
[build_pkg] step 3 OK: stamped version=1.0.0 sha=<12-char>
[build_pkg]   vendored runtime from /Users/BigBobby/MiningGuardian-vendor
[build_pkg] step 4 OK: payload assembled at .../build/stage/payload
[build_pkg]   removed lima-guestagent.Darwin-aarch64.gz (VZ-only build, Linux guest agent unused)
[build_pkg]   re-sealed bundle: runtime/ollama/Ollama.app
[build_pkg] step 4b OK: re-sealed 1 bundle(s), codesigned 5 loose Mach-O
pkgbuild: ...
productbuild: ...
productsign: ...
[build_pkg] step 5 OK: signed pkg at .../build/MiningGuardian-1.0.0-<sha>.pkg
Conducting pre-submission checks for ... and initiating connection to the Apple notary service...
Submission ID received
  id: <new submission UUID>
Successfully uploaded file
Waiting for processing to complete. Wait timeout is set to 1800.0 second(s).
Current status: Accepted          ← this is what you want
Processing complete
[build_pkg] step 6 OK: notarization Accepted
[build_pkg] step 7 OK: notarization ticket stapled
[build_pkg] step 8 OK: SHA-256 sidecar + spctl acceptance recorded

================================================================================
 Mining Guardian .pkg build complete.

   Version:    1.0.0
   Git SHA:    <12-char>
   Pkg:        .../build/MiningGuardian-1.0.0-<sha>.pkg
   SHA-256:    .../build/MiningGuardian-1.0.0-<sha>.pkg.sha256

 To install on a target Mac:
     sudo installer -pkg ".../build/MiningGuardian-1.0.0-<sha>.pkg" -target /
================================================================================
```

---

## Block C — Recovering from notarization failures

If step 6 fails, the script prints `FATAL (45) notarization not accepted; see ...notarization-log.txt` and exits.

### C.1 — Get the structured log

`notarytool submit` writes a high-level log inline. The detailed JSON with per-file errors is fetched separately:

```bash
SUBMISSION_ID="<paste from the build output>"
xcrun notarytool log "$SUBMISSION_ID" \
  --key    "$HOME/Documents/Apple Cert/AuthKey_FPZJ87B3QF.p8" \
  --key-id FPZJ87B3QF \
  --issuer f53661a7-931a-4976-8f8e-82353256931a \
  /tmp/mg_notary_log_latest.json
cat /tmp/mg_notary_log_latest.json
```

The `issues[]` array has the per-file errors. Two failure modes we've seen:

### C.2 — Failure mode: vendored binary not signed

Symptom (this was rejection #1 on 2026-04-28):

```
"path": "...runtime/colima/colima",
"message": "The binary is not signed with a valid Developer ID certificate."
"message": "The signature does not include a secure timestamp."
"message": "The executable does not have the hardened runtime enabled."
```

Cause: the vendor binary ships unsigned. Fix is to re-sign it during build — already implemented in PR #50's `step_4b_codesign_inner_binaries`. If you see this on a *new* binary not currently being signed, add it to the vendor directory layout that step 4b walks.

### C.3 — Failure mode: bundle seal broken

Symptom (this was rejection #2 on 2026-04-28):

```
"path": "...runtime/ollama/Ollama.app/Contents/MacOS/Ollama",
"message": "The signature of the binary is invalid."
```

Cause: someone re-signed a Mach-O *inside* an `.app` or `.framework` without rewriting the bundle's `_CodeSignature/CodeResources` manifest. The bundle is internally inconsistent.

Fix is implemented in PR #51's two-pass step_4b. If a new failure of this shape appears on a different bundle, the same approach applies: `codesign --deep` the bundle as a unit, never walk into it with `find -type f`.

### C.4 — Diagnose locally with the same check Apple runs

Before submitting again, you can verify every bundle's seal locally:

```bash
find /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/stage/payload/runtime \
    \( -name '*.app' -o -name '*.framework' \) -prune \
    -exec codesign --verify --deep --strict {} \;
```

Empty output = all bundles pass. Any output = a bundle is broken.

`build_pkg.sh` step 4b already runs this on every bundle and `_die`s on failure. So if `make pkg` reaches step 5, the bundles are consistent.

---

## Block D — After a successful build

### D.1 — Inspect the artifact

```bash
PKG="$(ls -t /Users/BigBobby/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.0-*.pkg | head -1)"
echo "Built: $PKG"
ls -lh "$PKG" "$PKG.sha256"
pkgutil --check-signature "$PKG"
spctl -a -vv -t install "$PKG"
xcrun stapler validate "$PKG"
```

All four should succeed.

### D.2 — Distribute (Q2 locked decision)

Two channels:

1. **Private GitHub Release** on `robertfiesler-spec/Mining-Guardian`. Upload the `.pkg` plus the `.pkg.sha256` sidecar. Mark as draft until verified.
2. **USB stick fallback** for offline install. Copy the same two files onto a clean USB.

### D.3 — Install on a target Mac

```bash
sudo installer -pkg /path/to/MiningGuardian-1.0.0-<sha>.pkg -target /
```

Or double-click the .pkg in Finder. Installer.app will ask for the admin password and run preinstall + postinstall end-to-end.

---

## Block E — When NOT to use this runbook

- The `.pkg` is already built and you just need to re-distribute → skip to Block D.
- You're modifying *code*, not the installer itself → don't touch `installer/macos-pkg/`. Build_pkg.sh is fine; the issue is in the app code, find it elsewhere.
- You're adding a new *vendor* binary → drop it into `~/MiningGuardian-vendor/<subdir>/`, then run Block B. step_4b will codesign whatever Mach-O it finds.

---

## Block F — Out of scope (do not do these here)

- 🚫 **Don't sign with `Developer ID Installer` for binary codesigning.** Use the `Application` cert. Installer is *only* for the outer .pkg via productsign.
- 🚫 **Don't `codesign` individual files inside an `.app` or `.framework`.** Re-seal the bundle as a unit with `--deep`.
- 🚫 **Don't put credentials in env vars or pass them on the CLI.** `build_pkg.sh` reads only `CREDENTIALS_NOTES.txt` by design — single source of truth.
- 🚫 **Don't commit `CREDENTIALS_NOTES.txt`, `AuthKey_*.p8`, or anything from `Apple Cert/` to git.** They're gitignored, but verify before pushing.
- 🚫 **Don't try to "fix" the Keychain Access "not trusted" red text.** Cosmetic UI bug only. Tools work.

---

*— end of 2026-04-28 build runbook*
