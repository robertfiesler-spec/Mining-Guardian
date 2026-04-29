# Session Log — 2026-04-28 (Tuesday)

**Operator:** Bobby Fiesler (BigBobby)
**Agent:** Perplexity Computer
**Session window:** Carry-over context from 2026-04-27 evening through 2026-04-28 ~1:18 PM CDT, with notarization wait still in flight at the time of this writing.
**Commits shipped to `main`:**

| PR | SHA | Subject |
|---|---|---|
| #44 | `5e715ab` | Bucket 3 I-1: `preinstall.sh` + `lib/detect_ram.sh` |
| #45 | `048f772` | Bucket 3 I-2: `postinstall.sh` + Colima/Ollama libs + 3 launchd plists |
| #46 | `b8555c7` | Bucket 3 I-3: `Distribution.xml` + welcome/license/conclusion + Makefile `pkg` target + `build_pkg.sh` |
| #47 | `fb0cb9c` | Installer: VZ-only on Apple Silicon, drop `qemu-img`, copy lima `libexec/bin` |
| #48 | `07d1ec8` | Installer: vendor `docker` CLI into `.pkg` payload |
| #49 | `df936f3` | Installer: read `version` from `pyproject.toml` (the prior `mining_guardian.py` grep was the wrong path) |
| #50 | `ad986a5` | Installer: codesign inner Mach-O binaries before `pkgbuild` (notarization fix v1) |
| #51 | `978ff61` | Installer: re-seal `.app`/`.framework` bundles, don't break their seal (notarization fix v2) |

**Locked decisions reaffirmed today:** Q1 hybrid `.pkg` shape (~500–767 MB), Q2 distribution via private GitHub Release + USB stick, D-13 RAM-detected Ollama model (16 GB → `llama3.2:3b`, 24 GB+ → `qwen2.5:14b-instruct-q4_K_M`), cutover scope **γ** (Mini replaces both Hostinger VPS *and* ROBS-PC catalog), branch cadence Option **β** (one narrow PR per change, branch deleted after squash-merge).

---

## TL;DR

The Bucket 3 installer code is **complete and merged**. The session's load-bearing work was iterating to a clean Apple notarization — six PRs of plumbing, then two PRs of codesign correctness. As of this log being written we are mid-flight on the third notarization round (submission `2c4130a4-13e6-4783-9b06-b7969ccb36aa`), waiting on Apple. Ollama.app's bundle seal verified locally with `codesign --verify --deep --strict`, which is the same check Apple's notary service runs.

Two notarization rejections this afternoon, both diagnosed end-to-end and resolved:

- **Reject #1** (submission `ce730e52`) — 6 vendored arm64 binaries had no Developer ID Application signature, no secure timestamp, no hardened runtime. Fixed by **PR #50**.
- **Reject #2** (submission `63236a3b`) — PR #50 went too deep: it walked into `Ollama.app` with `find -type f` and broke the bundle's `_CodeSignature/CodeResources` seal by re-signing the inner Mach-O without rewriting the manifest. Fixed by **PR #51** with a two-pass codesign strategy that treats `.app`/`.framework` bundles as atomic units.

The third submission is still processing. Steps 7–9 (staple, sha256 sidecar, spctl Gatekeeper acceptance, install banner) will run automatically the moment Apple returns Accepted.

Beyond the installer, three orthogonal tracks were touched today:

- A pile of **stale launchd agents at typo paths** were discovered and bootout'd (full discovery in the "Major discoveries" section).
- The **Apple Developer cert chain was missing intermediates** so `find-identity -v` reported zero valid identities even though both certs and private keys were present. Fixed by importing `DeveloperIDG2CA.cer` and `DeveloperIDCA.cer` from `apple.com/certificateauthority/`.
- The operator chose the **"Hero"** logo direction for the eventual `.pkg` branding PR (deferred to PR #52, post-notarization).

---

## Opening state (2026-04-28 morning, before this session's PRs)

- **Origin HEAD:** `df936f3` — PR #49 (`pyproject.toml` version read), the most recent installer fix from the prior segment.
- **VPS:** srv1549463 healthy.
- **Cert keychain:** both Developer ID certs and private keys imported, but no valid identity reported by `security find-identity -p basic -v` (root cause: missing intermediate CAs — see Major Discoveries §2).
- **Vendor directory:** `/Users/BigBobby/MiningGuardian-vendor/` populated, 767 MB across `colima/`, `docker/`, `images/`, `ollama/`.
- **Stale launchd agents:** 3 leftover plists in `~/Library/LaunchAgents/` from typo'd earlier paths (`com.bixbit.mining-guardian`, `com.miningguardian.dashboard`, `com.bixbit.hvac-collector`). The `mining-guardian` one was respawning every 30 s due to `ThrottleInterval=30` and spamming `launchd_stderr.log`.
- **Six-step user walkthrough**, status entering this session:

  | # | Step | Status entering session |
  |---|---|---|
  | 1 | Sync Mac clone | ✅ done previously |
  | 2 | Delete OLD/typo paths + 3 stale launchd | ✅ done at start of segment |
  | 3 | `CREDENTIALS_NOTES.txt` 5 keys | ✅ done — needed 6th key by end of session |
  | 4 | Developer ID Installer signing identity | ✅ done after intermediate-CA fix |
  | 5 | Populate `~/MiningGuardian-vendor/` (767 MB) | ✅ done |
  | 6 | `make pkg` end-to-end | 🔄 reached step 6/9 (notarize), failed Invalid twice |

---

## Commits shipped this session (chronological)

### PR #44 — `5e715ab` — Bucket 3 I-1: preinstall.sh + lib/detect_ram.sh

The first of three "Option β" narrow PRs for the installer. Adds the preinstall script and the RAM-detect helper that picks the Ollama model per **D-13**.

- New: `installer/macos-pkg/scripts/preinstall.sh`
- New: `installer/macos-pkg/scripts/lib/detect_ram.sh`
- Validation: `bash -n` on both files
- Branch deleted after squash-merge per Option β

### PR #45 — `048f772` — Bucket 3 I-2: postinstall.sh + Colima/Ollama libs + 3 launchd plists

- New: `installer/macos-pkg/scripts/postinstall.sh`
- New: `installer/macos-pkg/scripts/lib/colima.sh`, `installer/macos-pkg/scripts/lib/ollama.sh`
- New: 4 launchd plists in `installer/macos-pkg/launchd/`
- Validation: `bash -n` + `plutil -lint` on every plist

### PR #46 — `b8555c7` — Bucket 3 I-3: Distribution.xml + branding + Makefile pkg target + build_pkg.sh

The big one. Wires the entire 9-step build pipeline.

- New: `installer/macos-pkg/resources/Distribution.xml`
- New: `installer/macos-pkg/resources/welcome.html`, `license.html`, `conclusion.html`
- New: `Makefile` `pkg` target
- New: `installer/macos-pkg/scripts/build_pkg.sh` (the orchestrator)
- Validation: `xmllint --noout` on the Distribution.xml, `bash -n` on the orchestrator

### PR #47 — `fb0cb9c` — VZ-only on Apple Silicon, drop qemu-img

After PR #46 we discovered Lima 2.x ships only the krunkit driver in `libexec/` on macOS — no QEMU binaries. Apple Silicon should use `--vm-type vz` (Apple's Virtualization.framework) anyway.

- Drop `qemu-img` from vendor expectations
- Copy `lima/libexec/bin/` so `limactl` and `limactl-mcp` ship inside the pkg

### PR #48 — `07d1ec8` — Vendor docker CLI into payload

The Mac Mini will be a sealed/fresh box, no Homebrew. We can't assume `docker` is on the operator's PATH. Vendored a static arm64 `docker` binary into `runtime/docker/docker`.

### PR #49 — `df936f3` — Read version from pyproject.toml

`build_pkg.sh` step 3 was grepping for `__version__` in repo-root `mining_guardian.py`. That file is at `core/mining_guardian.py` and contains no `__version__` attribute. Switched to parsing `pyproject.toml` (single source of truth, already has `version = "1.0.0"`).

### PR #50 — `ad986a5` — Codesign inner Mach-O binaries before pkgbuild (notarization fix v1)

First notarization rejection (`ce730e52-460e-4220-a790-2f50b41401fa`) listed 6 vendored binaries:

| Path | Why rejected |
|---|---|
| `runtime/colima/colima` | not signed with Developer ID, no secure timestamp, hardened runtime not enabled |
| `runtime/colima/bin/limactl` | same |
| `runtime/colima/libexec/lima/limactl-mcp` | same |
| `runtime/colima/libexec/lima/lima-driver-krunkit` | same |
| `runtime/colima/share/lima/lima-guestagent.Darwin-aarch64` | same, plus the Linux guest agent inside a `.gz` wrapper |
| `runtime/docker/docker` | same |

Three additional `.gz` warnings on Postgres image internals — harmless Linux man-pages, ignored.

PR #50 added `step_4b_codesign_inner_binaries()` between steps 4 and 5:

- New env var `APPLE_DEV_ID_APPLICATION` required in `CREDENTIALS_NOTES.txt` (step 1 now validates both Installer + Application identities are in keychain)
- Walks `${PAYLOAD_DIR}/runtime/`, detects every Mach-O via `/usr/bin/file`, codesigns with `--sign "$APPLE_DEV_ID_APPLICATION" --options runtime --timestamp --force`
- Deletes `runtime/colima/share/lima/lima-guestagent.Darwin-aarch64.gz` — VZ-only on Apple Silicon (per PR #47), Linux guest agent unused, and the `.gz` wrapper cannot be re-signed in place

Operator action after merge: append to `CREDENTIALS_NOTES.txt`:

```
APPLE_DEV_ID_APPLICATION=Developer ID Application: Robert Fiesler (ARJZ5FYU94)
```

Result of next `make pkg`: step 4b reported `codesigned 21 Mach-O binaries`. Notarization re-submitted.

### PR #51 — `978ff61` — Re-seal .app/.framework bundles, don't break their seal (notarization fix v2)

Second rejection (`63236a3b-6a0d-4944-bb43-48de27ad6cda`) cut the errors from 6 → 2, but introduced a new one:

```
runtime/ollama/Ollama.app/Contents/MacOS/Ollama (x86_64)  → "The signature of the binary is invalid."
runtime/ollama/Ollama.app/Contents/MacOS/Ollama (arm64)   → "The signature of the binary is invalid."
```

**Root cause:** PR #50's step_4b walked into `Ollama.app` with `find -type f` and re-signed `Contents/MacOS/Ollama` with `codesign --force`. That overwrote the binary's signature but left the bundle's outer `Contents/_CodeSignature/CodeResources` manifest still hashing the *original* binary. Internally inconsistent → notary rejects.

**Fix (PR #51) — three-stage step_4b:**

1. **Pass 1 — bundles.** `find -prune` at every `.app` and `.framework` boundary, then `codesign --deep` each bundle as a unit. `--deep` re-signs every nested helper/framework/dylib **and** rewrites the bundle's `CodeResources` so the seal stays consistent.
2. **Pass 2 — loose Mach-O.** Walk `-type f`, skip any path inside `*/*.app/*` or `*/*.framework/*` (Pass 1 owns those), codesign each Mach-O individually.
3. **Verify.** `codesign --verify --deep --strict` on every bundle. Same check Apple runs — fails locally instead of after a 5–15 min Apple round-trip.

All sign operations still use `--sign "$APPLE_DEV_ID_APPLICATION" --options runtime --timestamp --force`.

After merge, `make pkg` produced:

```
[build_pkg]   removed lima-guestagent.Darwin-aarch64.gz (VZ-only build, Linux guest agent unused)
[build_pkg]   re-sealed bundle: runtime/ollama/Ollama.app
[build_pkg] step 4b OK: re-sealed 1 bundle(s), codesigned 5 loose Mach-O
```

Loose count dropped from 21 → 5 because most of those 21 were Ollama.app internals, now correctly handled by Pass 1's `--deep` re-seal. The Ollama bundle passed `--verify --deep --strict` locally, which is the strongest local signal that Apple will accept it. Submitted to Apple as `2c4130a4-13e6-4783-9b06-b7969ccb36aa`. **Status at the time of this log: in flight.**

---

## Major discoveries this session

### 1. Three stale launchd agents at typo paths

Found in `~/Library/LaunchAgents/` from earlier development:

- `com.bixbit.mining-guardian.plist`
- `com.miningguardian.dashboard.plist`
- `com.bixbit.hvac-collector.plist`

The `mining-guardian` one had `ThrottleInterval=30` and was respawning every 30 s, spamming `launchd_stderr.log` constantly. All three were `bootout`'d cleanly and the plists deleted. Operator confirmed `~/Library/LaunchAgents/` is now empty of MG-related plists.

**Implication for the installer:** the Mac Mini will be a sealed/fresh box, so this won't recur on the customer machine. But on operator development boxes the cleanup is a one-shot manual step — captured in the runbook.

### 2. Apple intermediate CAs were missing

Symptom: `security find-identity -p basic -v` returned **0 valid identities** even though `Developer ID Application` and `Developer ID Installer` certs (plus their private keys) were both present in the login keychain.

Root cause: macOS verifies cert chains up to a known root. The Apple Developer ID chain looks like:

```
Apple Root CA → Developer ID Certification Authority (G2) → your leaf cert
```

Both intermediate CAs (`DeveloperIDG2CA.cer` and `DeveloperIDCA.cer`) were absent from the System keychain. Without them, the leaf certs were valid-but-unverifiable.

Fix:

```bash
curl -O https://www.apple.com/certificateauthority/DeveloperIDG2CA.cer
curl -O https://www.apple.com/certificateauthority/DeveloperIDCA.cer
sudo security import DeveloperIDG2CA.cer -k /Library/Keychains/System.keychain
sudo security import DeveloperIDCA.cer   -k /Library/Keychains/System.keychain
```

After that, both leaf certs reported as valid:

```
3A92362E47C40BE6A9A60C8D4EAB85E5CA0EB3D5  "Developer ID Application: Robert Fiesler (ARJZ5FYU94)"
2CB9429B5D64274D152E2CD5A8E0E66D1DB26AB9  "Developer ID Installer: Robert Fiesler (ARJZ5FYU94)"
```

**Cosmetic note:** Keychain Access GUI still shows "certificate is not trusted" in red for the two leaf certs. This is a known macOS UI bug — `codesign` and `productsign` work correctly. Documented in `CREDENTIALS_NOTES.txt` so future-Bobby doesn't try to "fix" it.

### 3. Lima 2.x is VZ-only on macOS

When laying down the vendor expectations in PR #46 we assumed `qemu-img` would ship inside Lima. It doesn't on Lima 2.x — only the krunkit driver is in `libexec/`. Apple Silicon should use `--vm-type vz` (Apple's Virtualization.framework) anyway, which doesn't need QEMU. Patched in PR #47: drop `qemu-img`, document VZ-only.

### 4. Docker CLI not bundled with Colima

Colima starts a Lima VM and exposes a Docker socket — but doesn't ship the `docker` *client* CLI. On a sealed Mini with no Homebrew, the operator wouldn't have `docker` on PATH. Vendored a static arm64 `docker` binary into `~/MiningGuardian-vendor/docker/docker` and patched the assembly step to copy it into `${PAYLOAD_DIR}/runtime/docker/`. PR #48.

### 5. `build_pkg.sh` step 3 was grepping the wrong file for the version

Was: `grep '__version__' mining_guardian.py` from repo root.
Reality: there is no repo-root `mining_guardian.py` — it's `core/mining_guardian.py`, and that file has no `__version__` attribute. Symptom: `BUILD_VERSION=0.0.0` in `BUILD_STAMP.json`.
Fix (PR #49): parse `pyproject.toml`'s `version = "1.0.0"` line via Python regex, fall back to `0.0.0` only on parse failure.

### 6. Inner binaries need codesigning AND .app bundles need re-sealing

The two-step lesson of PRs #50 and #51 — vendored binaries unsigned by their vendor need a fresh Developer ID + secure timestamp + hardened runtime, and `.app`/`.framework` bundles are pre-sealed atoms that `codesign --deep` must re-sign as units. Splitting the codesign loop into "bundles via --deep" + "loose Mach-O via --force" + "verify via --strict" was the correct shape; doing it as a flat `find -type f` was the bug.

---

## Files added/modified on `main` this session

```
Makefile                                                 (PR #46)
installer/macos-pkg/Distribution.xml                     (PR #46)
installer/macos-pkg/launchd/*.plist                      (PR #45 — 4 files)
installer/macos-pkg/resources/Distribution.xml           (PR #46)
installer/macos-pkg/resources/welcome.html               (PR #46)
installer/macos-pkg/resources/license.html               (PR #46)
installer/macos-pkg/resources/conclusion.html            (PR #46)
installer/macos-pkg/scripts/build_pkg.sh                 (PR #46, #47, #48, #49, #50, #51)
installer/macos-pkg/scripts/preinstall.sh                (PR #44)
installer/macos-pkg/scripts/postinstall.sh               (PR #45)
installer/macos-pkg/scripts/lib/detect_ram.sh            (PR #44)
installer/macos-pkg/scripts/lib/colima.sh                (PR #45)
installer/macos-pkg/scripts/lib/ollama.sh                (PR #45)
```

**Out-of-tree (operator's local Mac, NOT committed):**

- `/Users/BigBobby/Documents/Apple Cert/CREDENTIALS_NOTES.txt` — 6 `KEY=VALUE` lines at the bottom (5 prior + 1 new `APPLE_DEV_ID_APPLICATION` added today).
- `/Users/BigBobby/MiningGuardian-vendor/` — 767 MB across `colima/`, `docker/`, `images/`, `ollama/`. Required by `step_4_assemble_payload`.
- `~/Library/Keychains/login.keychain-db` — both Developer ID certs + private keys imported.
- `/Library/Keychains/System.keychain` — `DeveloperIDG2CA.cer` and `DeveloperIDCA.cer` imported.
- `~/Library/LaunchAgents/` — emptied of stale MG plists.

---

## Apple credentials snapshot (machine-readable block in CREDENTIALS_NOTES.txt)

```
APPLE_TEAM_ID=ARJZ5FYU94
APPLE_NOTARIZATION_KEY_ID=FPZJ87B3QF
APPLE_NOTARIZATION_ISSUER_UUID=f53661a7-931a-4976-8f8e-82353256931a
APPLE_NOTARIZATION_KEY_PATH=/Users/BigBobby/Documents/Apple Cert/AuthKey_FPZJ87B3QF.p8
APPLE_DEV_ID_INSTALLER=Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
APPLE_DEV_ID_APPLICATION=Developer ID Application: Robert Fiesler (ARJZ5FYU94)
```

Signing identity SHAs (verified valid in keychain after intermediate-CA fix):

| Cert | SHA-1 |
|---|---|
| Developer ID Application | `3A92362E47C40BE6A9A60C8D4EAB85E5CA0EB3D5` |
| Developer ID Installer | `2CB9429B5D64274D152E2CD5A8E0E66D1DB26AB9` |

Notarization submission ledger:

| Submission ID | Build SHA | Status | Outcome |
|---|---|---|---|
| `ce730e52-460e-4220-a790-2f50b41401fa` | `df936f3c2781` | Invalid | 6 unsigned vendored binaries → fixed by PR #50 |
| `63236a3b-6a0d-4944-bb43-48de27ad6cda` | `ad986a5dc738` | Invalid | Ollama.app bundle seal broken by over-aggressive codesign → fixed by PR #51 |
| `2c4130a4-13e6-4783-9b06-b7969ccb36aa` | `978ff61126ea` | **In flight** | (waiting on Apple at log time) |

---

## Logo direction (PR #52, deferred)

Operator chose **"Hero"** direction for installer branding:

- **`.pkg` Finder icon (square `.icns`):** `01_primary_shield_logo.png` from `setA/` — the knight helmet + crossed pickaxes + Bitcoin orb shield mark.
- **Installer window background (wide):** `04_long_horizontal_wordmark_logo.png` from `setA/` — the wide "MINING GUARDIAN" wordmark on dark background.

Source folder on operator's Mac: `/Users/BigBobby/Documents/Personal/Mining guardian logos/Icons/mining_guardian_recuts_all_sets/setA/`.

PR #52 is **not started yet** — explicitly deferred per operator direction ("one thing at a time" / "i do not want to get into this because my ocd will take off"). Will be picked up after the current notarization comes back Accepted and steps 7–9 finish. PR #52 will only touch `installer/macos-pkg/resources/` (icon.icns + background.png + a small Distribution.xml `<background>` reference) — no code changes, no risk to the now-clean signing chain.

Two assets the operator will need to surface before PR #52:

1. The original PNG of `01_primary_shield_logo.png` at ≥ 1024×1024 with transparent background.
2. The original PNG of `04_long_horizontal_wordmark_logo.png` at native resolution (preferably ≥ 1600 px wide).

JPGs were sufficient for previewing today; PR #52 needs the PNGs because (a) `.icns` requires alpha and (b) JPG quality losses compound across the 6 sizes Apple wants in an icon set.

---

## Six-step user walkthrough — status at end of session

| # | Step | Status |
|---|---|---|
| 1 | Sync Mac clone | ✅ |
| 2 | Delete OLD/typo paths + 3 stale launchd | ✅ |
| 3 | `CREDENTIALS_NOTES.txt` 6 keys | ✅ |
| 4 | Both Developer ID signing identities present | ✅ |
| 5 | Populate `~/MiningGuardian-vendor/` (767 MB) | ✅ |
| 6 | `make pkg` end-to-end | 🔄 reached step 6/9 (notarize, third attempt, awaiting Apple) |

---

## Next steps when notarization comes back

### If Accepted

The script auto-continues:

- **Step 7:** `xcrun stapler staple` then `xcrun stapler validate` on the .pkg
- **Step 8:** SHA-256 sidecar + `spctl --assess --type install -vv` (Gatekeeper acceptance check)
- **Step 9:** Print the install banner with the `sudo installer -pkg ... -target /` command

Then unblock:

1. **PR #52 — installer branding** (icon.icns + background.png). Walk operator through `sips -g pixelWidth -g pixelHeight` on the two source PNGs, then build the `.icns` via `iconutil -c icns` and wire it into `Distribution.xml`. Branch: `feat/installer-branding-icon-and-background`.
2. **Q2 distribution** — upload signed/notarized .pkg to private GitHub Release on `robertfiesler-spec/Mining-Guardian`, copy to USB stick as offline fallback.
3. **D-14 PR 5/5** — final Bucket 1 piece, gated on Mini physical install.

### If Invalid again

Fetch the structured log:

```bash
xcrun notarytool log 2c4130a4-13e6-4783-9b06-b7969ccb36aa \
  --key "$HOME/Documents/Apple Cert/AuthKey_FPZJ87B3QF.p8" \
  --key-id FPZJ87B3QF \
  --issuer f53661a7-931a-4976-8f8e-82353256931a \
  /tmp/mg_notary_log_v3.json
```

Read the `issues[]` array. Plausible remaining failure modes (in order of likelihood, all low):

1. **Postgres image `.gz` warnings escalate to errors** — the three Linux man-page archives the notary couldn't unpack. If they ever flip from `severity: warning` to `severity: error`, the fix is to extract and re-pack the postgres tarball minus those three paths, or to rely on `--force-allow-not-malicious-binary` style mitigations (none currently exist for this; the real fix would be tarball surgery).
2. **A different `.app` or `.framework` we haven't seen yet** — unlikely, since `pkgbuild` only reported `Ollama.app` and `Squirrel.framework` and both were re-sealed by Pass 1 of PR #51's step_4b.
3. **A hardened-runtime entitlement issue** on Ollama specifically — unlikely because Ollama upstream already shipped with hardened runtime, and `--options runtime` only adds, never removes.

If any of those hit, document the failure mode in this file and write PR #53.

---

## Outstanding work (broader buckets, unchanged from prior session)

🔴 **Bucket 1**

- D-14 PR 5/5 (waiting for Mini install)
- Backfill of 124 missing `raw_json` rows from the 2026-04-27 import
- Runtime invariant assertion in `run_full_import.py`

🟡 **Bucket 2**

- Optional CI lint for typo regression
- B-7 migrations `002_layer2` + staging not committed
- VPS GitHub PAT rotation
- Delete `scripts/cleanup_ams_logs.py`
- Regression test in `tests/test_migrations.py`

🟢 **Bucket 3 — installer**

- Code complete (PRs #44–#51 merged)
- Blocked on third notarization round (in flight at log time)
- Branding PR #52 deferred until notarization Accepted

🟢 **Bucket 4 — per-customer ops**

- Power cycle 53476
- Inspect 53494 / 53521 hashboards
- 53482 underperforming
- HVAC re-enable + remove `hvac_work_apr2026` hardware fact

---

## Closing note

D-7 to Mac Mini install. The `.pkg` is one Apple decision away from being a real, signed, notarized, stapled, customer-ready installer. The codesign correctness work today was the kind of thing where the second fix is much shorter than the first because the first one taught you what `--deep` really means. Tomorrow we'll either be polishing branding (best case, PR #52) or chasing a third Apple complaint (less likely, but the diagnostic loop is now well-grooved: `notarytool log` → JSON → fix → push → re-submit). Bitcoin SHA-256 miners only. Postgres-as-truth.

*— end of 2026-04-28 log*


---

## Addendum — afternoon: Q2 distribution shipped

After the morning notarization win, the operator chose **Option 2 — Q2 distribution** over branding (which becomes its own future cycle, PR #53). Reasoning: tag/upload first while the binary is fresh and bit-perfect; branding will require a second full notarization round trip, so do it as its own clean cycle later.

### Steps executed (all 9 of the distribution checklist)

1. **Pre-flight** — confirmed `MiningGuardian-1.0.0-978ff61126ea.pkg` (392,562,726 bytes), `.pkg.sha256` = `c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8`, `spctl` still reports `accepted` + `source=Notarized Developer ID`. The staple held overnight (well, over coffee).
2. **Tag** — created annotated tag `v1.0.0-978ff61126ea` on commit `978ff61126ea8acd21a41aa9d29293c9ec96dc0d` (the **build SHA**, not current `main`). Tag message embeds the SHA-256, both signing identity SHAs, and the accepted notarytool submission ID. Pushed to `origin`.
3. **Release notes** — `docs/RELEASE_NOTES_v1.0.0.md` (171 lines). Covers: artifact metadata, signing chain, install instructions, what does NOT happen at install (zero internet calls), known issues (Lima 2.x VZ-only, Apple intermediate CAs in System keychain), provenance reproduction recipe, full notarization ledger.
4. **Repo visibility** — confirmed repo was public, flipped to **private** via `gh repo edit --visibility private --accept-visibility-change-consequences` to honor the Q2 locked decision ("private GitHub Release"). Operator confirmed they were going to flip it back to private anyway.
5. **GitHub Release** — `gh release create v1.0.0-978ff61126ea --notes-file docs/RELEASE_NOTES_v1.0.0.md --latest` on `robertfiesler-spec/Mining-Guardian`. Released as `latest`, not draft, not prerelease.
6. **Asset upload** — `gh release upload` of the `.pkg` + `.sha256`. First upload succeeded in 2m22s. Operator paste-restarted (not realizing it had completed) and a second `--clobber` upload re-pushed the same bytes in 2m10s. Net effect: same release, freshly re-uploaded copy. Server-side `gh api` confirmed both assets `state: uploaded`, sizes match local exactly.
7. **Round-trip verification** — created scratch dir `~/Downloads/mg_release_test/`, downloaded both assets fresh from the GitHub Release (1m34s download), re-ran `shasum -a 256 -c` (OK), re-ran `spctl -a -t install` on the downloaded copy (`accepted`, `source=Notarized Developer ID`). Critically: `xattr` on the downloaded file showed `com.apple.provenance` (Sequoia+ replacement for `com.apple.quarantine`) — meaning macOS did treat it as a real internet download, and Gatekeeper still trusted it. **The staple survived GitHub's CDN.**
8. **USB fallback** — operator's USB stick "MG Install" was 8 GB FAT32. Reformatted to ExFAT in 5 sec via `diskutil eraseVolume ExFAT "MG Install" "/Volumes/MG Install"` (FAT32 has a 4 GB per-file cap that would bite future fatter releases; the stick was empty so nothing was lost). Wrote a 1,269-byte `INSTALL.txt` (heredoc, plain English: 5 install steps, the SHA, the spctl-expected output, the sudo install command, troubleshooting). Copied the .pkg + .sha256 onto the stick. Re-ran SHA-256 check on the stick copy (OK) and `spctl` on the stick copy (`accepted`).

### Three independent install paths now exist

1. Operator's local build folder — `~/Documents/GitHub/Mining-Guardian/build/...pkg`
2. Private GitHub Release — round-trip verified
3. USB stick "MG Install" — round-trip verified, with standalone INSTALL.txt

A future Mac with no internet, no GitHub access, no operator memory can still install Mining Guardian. That was the whole point of having a USB fallback.

### Heredoc paste lesson learned

First pass at writing `INSTALL.txt` to the USB used a single ~80-line heredoc paste-block. Terminal's continuation-prompt state suggested the closing `EOF` token didn't land cleanly. Aborted with Ctrl+C and rebuilt the step as **three short paste-blocks** (write file, copy assets, verify). Worked first try. Future runbook entries should default to small blocks; long heredocs are paste-fragile.

### USB filesystem note

ExFAT is the right format for this stick. FAT32 caps per-file size at 4 GB — fine for our 374 MB .pkg today, but this installer will only get bigger as more Ollama models / vendored wheels land. ExFAT also AppleDouble-stores xattrs as `._*` sidecar files, which is harmless metadata noise (Mac creates, Mac reads, Windows/Linux ignore).

### Submission ledger (final)

| Submission ID | Source SHA | Result |
|---|---|---|
| `ce730e52-460e-4220-a790-2f50b41401fa` | `df936f3c2781` | Invalid — 6 unsigned inner Mach-O |
| `63236a3b-6a0d-4944-bb43-48de27ad6cda` | `ad986a5dc738` | Invalid — Ollama.app seal broken |
| **`2c4130a4-13e6-4783-9b06-b7969ccb36aa`** | **`978ff61126ea`** | **Accepted ✅** |

### Closing note (afternoon)

The full Bucket 3 chain — codesign correctness → notarization → staple → tag → release → upload → round-trip → USB — is now end-to-end shippable. The next time we touch this is either (a) PR #53 branding (icon.icns + installer background.png), which means a second notarization cycle of its own; or (b) a content release that actually changes the payload. Either way the runbook is now grooved deep enough that future-us can do it without thinking. Bitcoin SHA-256 miners only. Postgres-as-truth. Stay local.

*— end of 2026-04-28 distribution addendum*


---

# 2026-04-28 — Evening addendum: .pkg installer branding (PR #54)

**Time window:** ~3:30 PM – 4:15 PM CDT
**PR:** [#54 — docs(customer)+installer(brand): three customer PDFs + .pkg branding](https://github.com/robertfiesler-spec/Mining-Guardian/pull/54)
**Branch:** `docs/customer-docs-and-installer-branding`
**Final commit:** `a2b1261984938011e293b87a4db9dd31e6c4c4d6` (rebased onto main `9e24a94`)
**State:** OPEN, MERGEABLE, mergeStateStatus CLEAN — ready to merge.

## 1. Why this addendum exists

Earlier in the day (afternoon addendum above) the PDF customer-doc work and the v1.0.0 distribution chain shipped. PR #54 then went stale because:

- The first attempt at "installer branding" was a terminal-wizard toolkit (`installer/brand/`) sized for the **rejected pre-D-13 architecture** (a Bash-driven setup wizard). The real installer is the signed/notarized native macOS `.pkg` that PR #46 introduced and PR #53 documented as shipped (`MiningGuardian-1.0.0-978ff61126ea.pkg`).
- Robert caught the mismatch ("we changed it to a pkg installer yesterday and that is what we built today isnt it?"). Confirmed correct.
- The terminal-wizard toolkit was therefore dropped from PR #54 and replaced with three pieces of native `.pkg` brand surface.

## 2. What landed in PR #54 (the brand surface)

All three files live in `installer/macos-pkg/resources/`. They are the assets `Distribution.xml` already references (welcome HTML, conclusion HTML, sidebar background art) — previously they were unstyled placeholders or absent.

| File | Size | Purpose |
|---|---|---|
| `welcome.html` | 5.7 KB | First Installer.app screen — restyled with brand tokens, lists what's about to install, names the Developer ID, warns about the one network step |
| `conclusion.html` | 5.6 KB | Final Installer.app screen — green "INSTALLED" check pill, four launchctl verification commands (with `sudo` highlighted in BTC orange), uninstall instructions, Bitcoin-only-policy footer |
| `background.png` | 305 KB (620×1111 PNG-8) | Sidebar artwork — Hero shield + crossed pickaxes + glowing Bitcoin coin + electric-blue circuit lines on a navy gradient, "MINING GUARDIAN" wordmark with electric-blue underline. Sized for crisp Retina at the ~200×350 sidebar slot Installer.app uses |

`Distribution.xml` already had `<background file="background.png" alignment="bottomleft" scaling="proportional"/>` on line 35 — **no Distribution.xml change required**. The previous build was simply falling back to plain Installer.app chrome because `background.png` did not exist.

## 3. Brand token lock-in (identical to PDFs)

| Token | Hex | Used where |
|---|---|---|
| Navy | `#0A1428` | Page background |
| Navy deep | `#050A14` | Code/URL pills |
| Surface | `#11203B` | Cards, callouts |
| Border | `#1F3A66` | Card borders, dividers |
| Electric blue | `#3DA9FC` | H2 uppercase, links, code text |
| Bitcoin orange | `#F7931A` | Eyebrow, accent rule, bullets, `sudo` keyword |
| Text | `#E6ECF5` | Body |
| Text muted | `#A8B5CC` | Secondary text |
| Success green | `#3BD16F` | "INSTALLED" check pill on conclusion |

**Typography rule:** the PDFs and `background.png` use DM Sans (TTFs shipped in `customer_docs/fonts/`). The HTML files use **Apple system fonts only** (`-apple-system, BlinkMacSystemFont, "SF Pro Text"`) — zero remote font CDN, zero offline-install breakage. Decision rationale: the `.pkg` must install cleanly on a Mac with no internet (e.g. air-gapped customer install).

## 4. PR #54 final shape

Eight files, one consolidated commit, rebased onto current `main` so the merge is clean. Diff stats (vs main `9e24a94`):

```
docs/MG_UNIFIED_TODO_LIST.md                                    +16 -0
docs/customer/MiningGuardian_Brochure.pdf                       (binary, added)
docs/customer/MiningGuardian_Program_Instructions.pdf           (binary, added)
docs/customer/MiningGuardian_Setup_Manual.pdf                   (binary, added)
docs/customer/README.md                                         +45 -0
installer/macos-pkg/resources/background.png                    (binary, added)
installer/macos-pkg/resources/conclusion.html                   +167 -31
installer/macos-pkg/resources/welcome.html                      +152 -33
```

## 5. Build / push process notes (for future-us)

### What worked
- **Git Data API end-to-end** (`gh api` with `["github"]` credentials): upload blob → create tree → create commit → PATCH ref. This is the **only** reliable push path right now.
- For binary files >100 KB (e.g. `background.png` 305 KB), write base64 to a JSON file and pass via `gh api --input file.json`. `argv` has size limits.
- Force-pushing the rebased commit: `gh api -X PATCH repos/.../git/refs/heads/<branch> -f sha=<commit> -F force=true`.

### What did NOT work
- **Direct `git push` is broken.** The local proxy token in git config (`agp_019dd5a1-…`) is expired/invalid. Don't waste time on it. Use `gh api`.

### The rebase (because main had advanced through PRs #25–#53)
The first push of PR #54 went CONFLICTING because main had moved a lot since the PR's original base. Strategy that worked:

1. Fetch the current main `MG_UNIFIED_TODO_LIST.md` from origin.
2. Splice our new "## 1.1 Tuesday 2026-04-28" section in **after** the "Bottom line of weekend so far" marker. Purely additive (+16 lines, no deletions), so no semantic conflict.
3. Build a tree on top of the **current main tree SHA**, with all 8 PR files (5 new docs/customer/* + 3 installer/macos-pkg/resources/* + 1 spliced TODO).
4. Create a single commit with `parent=main_tip`.
5. Force-update the branch ref. Result: MERGEABLE / CLEAN.

## 6. Visual review

Composite Installer.app window mockups were rendered at 1640×1008 (2× retina) showing:
- macOS titlebar with traffic-light buttons + "Install Mining Guardian" title
- Sidebar with `background.png` cover-fit, bottom-anchored
- Right pane with the HTML preview (Playwright-rendered at 620×420 viewport)
- Footer with Continue/Go Back (welcome) or Close (conclusion) buttons

Files in `/home/user/workspace/pkg_brand/`:
- `preview_window_welcome.png` (552 KB)
- `preview_window_conclusion.png` (513 KB)

Visual review: PASSED. No text wrapping issues, no truncation, no clashes.

## 7. What this PR does NOT do

- **Does not rebuild the .pkg.** The current shipped `.pkg` (`MiningGuardian-1.0.0-978ff61126ea.pkg`) still has the unstyled welcome screen. A rebuild + re-notarize on Robert's Mac is required after merge.
- **Does not refresh the USB stick.** The "MG Install" USB stick still holds the unbranded build. After the rebuild, the new `.pkg` must be copied to the stick (the stick itself does NOT need to be erased — the file just needs to be replaced).
- **Does not refresh the GitHub Release.** Same story — `gh release upload` the new `.pkg` after rebuild.

## 8. Rebuild procedure (Robert's next action on the Mac)

After PR #54 merges:

```zsh
cd ~/Documents/GitHub/Mining-Guardian
git checkout main
git pull --ff-only
make pkg
```

`build_pkg.sh` runs the full chain end-to-end:
1. `productbuild` → unsigned `.pkg`
2. `productsign` with Developer ID Installer Robert Fiesler (ARJZ5FYU94)
3. `xcrun notarytool submit --wait` (expect Accepted in ~3–5 min based on submission `2c4130a4`)
4. `xcrun stapler staple`

Output: `build/MiningGuardian-1.0.0-<newsha>.pkg`. Then re-upload to the GitHub Release and replace the file on the USB stick.

## 9. State of the repo at end of session

| Branch | vs main | Note |
|---|---|---|
| `main` | (tip `9e24a94`) | PR #53 is the head |
| `docs/customer-docs-and-installer-branding` (PR #54) | +1 ahead, 0 behind, CLEAN | Ready to merge |
| `feature/fast-cohort-analysis` | diverged 2 ahead / 202 behind | Stale experiment, not blocking |
| `feature/intelligence-catalog` | diverged 21 / 294 | Stale experiment, not blocking |
| `pre-prod-audit-2026-04-25` | diverged 47 / 294 | Stale audit branch, not blocking |
| `fix/typo-rename-…` | 0 ahead | Already merged content, branch can be deleted |
| 4× `hotfix/cr-*` branches | 0 ahead | Already merged content, branches can be deleted |
| `openclaw-integration` | 0 ahead | Already merged content, branch can be deleted |

Bottom line: every piece of work that needs to be in `main` either is in `main` or is in PR #54 waiting to merge. Nothing is uncommitted, nothing is unpushed, nothing is silently behind.

## 10. Closing note (evening)

The day went: morning (PRs #44–#51 fixed the .pkg build pipeline) → afternoon (notarized, stapled, released, USB-shipped — PR #53) → evening (the brand surface that would have looked sloppy on a customer's screen got the same DM Sans / navy / BTC-orange treatment as the PDFs — PR #54). After PR #54 merges and `make pkg` runs once more, the customer experience is end-to-end branded: the box (PDFs), the install (.pkg with our welcome + conclusion + sidebar art), and the running app. Bitcoin SHA-256 miners only. Postgres-as-truth. Stay local.

*— end of 2026-04-28 evening addendum*
