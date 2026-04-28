# Mining Guardian v1.0.0

**Release date:** 2026-04-28
**Build SHA:** `978ff61126ea8acd21a41aa9d29293c9ec96dc0d`
**Tag:** [`v1.0.0-978ff61126ea`](https://github.com/robertfiesler-spec/Mining-Guardian/releases/tag/v1.0.0-978ff61126ea)
**Distribution:** Private GitHub Release + USB stick fallback (no public registry, no cloud-only dependencies)

---

## What this release is

The first **signed, notarized, and Gatekeeper-blessed** macOS installer for Mining Guardian. Double-click the `.pkg`, walk through the standard macOS installer, and the full local stack (Colima VM, Docker CLI, Ollama runtime, vendored Python wheels, scripts, and configs) lands on disk in one shot. No `curl | bash`, no Homebrew dance, no internet round-trip required after the .pkg is on the target Mac.

Bitcoin SHA-256 miners only. Local-only by design.

---

## Build artifact

| Field | Value |
|---|---|
| Filename | `MiningGuardian-1.0.0-978ff61126ea.pkg` |
| Size | 392,562,726 bytes (~374 MB) |
| SHA-256 | `c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8` |
| Built from | `978ff61126ea` (PR #51 — bundle re-seal fix) |
| Built on | 2026-04-28, Apple Silicon Mac, macOS |
| Build script | `installer/macos-pkg/scripts/build_pkg.sh` |
| Build duration | 6 min 33 sec end-to-end |

A sidecar `MiningGuardian-1.0.0-978ff61126ea.pkg.sha256` is published alongside the .pkg. Always verify the hash before installing.

---

## Signing & notarization chain

| Stage | Identity / ID | Result |
|---|---|---|
| Inner Mach-O codesign (loose) | `Developer ID Application: Robert Fiesler (ARJZ5FYU94)` | 5 binaries signed |
| Bundle re-seal (`.app` / `.framework`) | `Developer ID Application: Robert Fiesler (ARJZ5FYU94)` | 1 bundle (Ollama.app) |
| Local strict verify | `codesign --verify --deep --strict` | passed |
| pkgbuild + productbuild | n/a | passed |
| productsign | `Developer ID Installer: Robert Fiesler (ARJZ5FYU94)` | passed |
| Apple notarytool submission | `2c4130a4-13e6-4783-9b06-b7969ccb36aa` | **Accepted** |
| Stapler | `xcrun stapler staple` | passed |
| Gatekeeper assessment | `spctl -a -t install` | `accepted`, `source=Notarized Developer ID` |

### Certificate fingerprints

```
Developer ID Application: Robert Fiesler (ARJZ5FYU94)
  SHA-1: 3A92362E47C40BE6A9A60C8D4EAB85E5CA0EB3D5

Developer ID Installer:   Robert Fiesler (ARJZ5FYU94)
  SHA-1: 2CB9429B5D64274D152E2CD5A8E0E66D1DB26AB9
```

Both certificates chain through Apple's Developer ID intermediates (DeveloperIDG2CA + DeveloperIDCA) and the Apple Root CA — all present in System keychain on the build host.

---

## Install instructions (target Mac)

### Option A — from this GitHub Release

```bash
# 1. Download the .pkg and the .sha256 sidecar to ~/Downloads
#    (use the GitHub Release page or `gh release download`)

cd ~/Downloads

# 2. Verify the hash
shasum -a 256 -c MiningGuardian-1.0.0-978ff61126ea.pkg.sha256
# Expected: MiningGuardian-1.0.0-978ff61126ea.pkg: OK

# 3. (Optional) confirm Gatekeeper is happy with this exact file
spctl -a -vvv -t install MiningGuardian-1.0.0-978ff61126ea.pkg
# Expected: accepted   source=Notarized Developer ID

# 4. Install — double-click in Finder, OR install headless:
sudo installer -pkg MiningGuardian-1.0.0-978ff61126ea.pkg -target /
```

### Option B — from USB stick

The .pkg, the .sha256 sidecar, and an `INSTALL.txt` file are mirrored on a USB stick for offline installs. Same commands as Option A — just point at the USB volume instead of `~/Downloads`.

### What gets installed

- Mining Guardian Python application (vendored wheels, no `pip install` at install time)
- Colima VM bootstrap (lightweight Linux VM for the local container runtime)
- Docker CLI (vendored — Colima 2.x does not bundle `docker`)
- Ollama runtime (`Ollama.app` bundle)
- Mining Guardian configs, launchd helpers, and `mg` CLI wrapper

### What does NOT happen at install time

- No internet calls
- No phoning home
- No telemetry
- No cloud account required
- No Homebrew, no `pip install`, no `npm install`

---

## Verifying after install

```bash
# Confirm staple sticks on the installed bundle (sanity)
xcrun stapler validate /Applications/Ollama.app

# Confirm the installer receipt is recorded
pkgutil --pkg-info com.miningguardian.pkg
```

---

## Known issues / things to know

- **Lima 2.x is VZ-only on Apple Silicon.** The `lima-guestagent.Darwin-aarch64.gz` was intentionally removed from the payload — it's a Linux guest agent that does nothing on macOS hosts. (Discovered + cleaned in PR #51.)
- **Apple intermediate CAs must be in the build host's System keychain** to sign. If `security find-identity -v -p codesigning` returns 0 valid identities, install `DeveloperIDG2CA.cer` and `DeveloperIDCA.cer` from Apple PKI before rebuilding. (This bit us once during this build cycle — documented in `docs/RUNBOOK_2026-04-28_pkg_build.md`.)
- **Notarization can take 5–10 min** end-to-end. The build script uses `notarytool submit --wait` so the pipeline blocks until Apple responds.

---

## Provenance — how to reproduce this exact .pkg

```bash
git clone https://github.com/robertfiesler-spec/Mining-Guardian.git
cd Mining-Guardian
git checkout v1.0.0-978ff61126ea
# Populate /Users/<you>/Documents/Apple Cert/CREDENTIALS_NOTES.txt
# with the 6 APPLE_* keys (see docs/RUNBOOK_2026-04-28_pkg_build.md)
make pkg
```

The resulting `.pkg` should hash to a different value than this release (timestamps + your own signing identity), but the **payload content** will be byte-identical.

---

## Changelog since pre-1.0

| PR | SHA | Subject |
|---|---|---|
| #48 | `07d1ec8` | Vendor Docker CLI into .pkg payload |
| #49 | `df936f3` | Read version from pyproject.toml; drop wrong-path mining_guardian.py grep |
| #50 | `ad986a5` | Codesign inner Mach-O binaries before pkgbuild (notarization fix v1) |
| #51 | `978ff61` | Re-seal `.app`/`.framework` bundles instead of breaking their seal (notarization fix v2) |
| #52 | `acb4744` | Docs: 2026-04-28 session log + .pkg build runbook + unified todo update |

---

## Notarization submission ledger (full history)

| Submission ID | Source SHA | Result |
|---|---|---|
| `ce730e52-460e-4220-a790-2f50b41401fa` | `df936f3c2781` | Invalid — 6 unsigned inner Mach-O binaries |
| `63236a3b-6a0d-4944-bb43-48de27ad6cda` | `ad986a5dc738` | Invalid — `Ollama.app` seal broken by deep find re-sign |
| **`2c4130a4-13e6-4783-9b06-b7969ccb36aa`** | **`978ff61126ea`** | **Accepted ✅** |

---

## Reference docs

- `docs/SESSION_LOG_2026-04-28.md` — full chronological session log
- `docs/RUNBOOK_2026-04-28_pkg_build.md` — paste-along runbook (Blocks A–F) for future builds
- `docs/MG_UNIFIED_TODO_LIST.md` — Section 14 covers Bucket 3 status

---

*Mining Guardian — local-only, Bitcoin SHA-256 miners, no cloud dependencies.*
