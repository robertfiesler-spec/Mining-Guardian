# Runbook — Rebuild .pkg + refresh USB stick + refresh GitHub Release

> Use this every time a code change lands on `main` that you want to ship as a new `.pkg`.
> Paste-along blocks. Ten minutes end-to-end if Apple notary is fast. Mac zsh.

> **Audience reminder (B-3, 2026-05-02):** the `.pkg` you build with this runbook is for **end-user (customer) laptops** — the viewer-only payload. It is **not** the install path for the Mac Mini operations server. The Mini uses `scripts/setup.sh` directly. See `docs/INSTALL_PATHS_2026-05-02.md` for the role/path matrix and rationale.

## Pre-flight (30 seconds)

```zsh
# 1. Are you on main with no local changes?
cd ~/Documents/GitHub/Mining-Guardian
git status

# 2. Pull latest
git checkout main
git pull --ff-only

# 3. Confirm the change you expect is actually there
git log -1 --stat
```

If `git pull --ff-only` rejects, you have local commits or uncommitted work. Stop, sort that out before continuing.

## Block Pre-A — Populate the vendor wheelhouse (D-18 Gap 5, P-010 hard gate)

> **One-time per build host. Re-run this only when `installer/macos-pkg/payload-requirements.txt` changes.**
> Skipping this block is now a hard build error — `build_pkg.sh` step 4e exits 43 if `${HOME}/MiningGuardian-vendor/python-wheels/` is missing or empty (P-010, 2026-05-04). Catching it here saves an Apple notarization round-trip on a dead .pkg.

Why this exists: `postinstall.sh::step_create_venv` runs `pip install --no-index --find-links <payload>/python-wheels --only-binary=:all: -r <payload>/requirements.txt` on the customer Mac. No network for pip. The wheels must be vendored offline at build time, on the operator's Mac, against the macOS Apple Silicon target ABI.

> **Build host vs customer Mac (P-026, 2026-05-05).** The build host still uses Homebrew `python@3.12` to *download* the wheelhouse (so wheel ABI tags match). The customer Mac mini no longer needs Homebrew at all — the `.pkg` now vendors its own Python 3.12 interpreter (Block Pre-B). Do not skip Pre-B.

```zsh
# 1. Confirm Homebrew python@3.12 is installed on the build host.
#    This is BUILD-HOST ONLY — used for `pip download` to populate the
#    wheelhouse with the right cp312 ABI tags. The CUSTOMER Mac does NOT
#    need Homebrew or python@3.12; Block Pre-B vendors a relocatable
#    Python 3.12 runtime into the .pkg payload (P-026).
/opt/homebrew/opt/python@3.12/bin/python3.12 --version
# Expect: Python 3.12.x
# If missing: brew install python@3.12

# 2. Make a clean wheelhouse — wipe any older download to avoid mixing
#    stale wheels from a previous payload-requirements.txt.
rm -rf "${HOME}/MiningGuardian-vendor/python-wheels"
mkdir -p "${HOME}/MiningGuardian-vendor/python-wheels"

# 3. Download the FULL transitive closure for macosx_11_0_arm64 / cp312.
#    --only-binary=:all: refuses sdists (no compiler on the customer Mini).
#    --platform / --python-version / --implementation / --abi force the
#    correct wheel ABI tags even when running this on a different host.
/opt/homebrew/opt/python@3.12/bin/python3.12 -m pip download \
    --only-binary=:all: \
    --platform macosx_11_0_arm64 \
    --python-version 3.12 \
    --implementation cp \
    --abi cp312 \
    -d "${HOME}/MiningGuardian-vendor/python-wheels" \
    -r installer/macos-pkg/payload-requirements.txt

# 4. Sanity-count what landed. Expect ~80-150 wheels (full transitive
#    closure of the 49 lines in payload-requirements.txt).
ls "${HOME}/MiningGuardian-vendor/python-wheels"/*.whl | wc -l
```

**If pip download fails on a specific package**, the most common causes are:

| Symptom | Cause | Fix |
|---|---|---|
| `Could not find a version that satisfies the requirement X (from versions: ...)` for a package that lists only sdists | Package has no arm64 cp312 wheel on PyPI | Pin a different version that does (`pip index versions X`), update `payload-requirements.txt` |
| `weasyprint`, `psycopg2-binary`, `cryptography`, `paramiko` resolver complaints | Build-host Python is 3.13 or 3.14, not 3.12 | Re-run with the explicit `/opt/homebrew/opt/python@3.12/bin/python3.12` path |
| Empty wheelhouse with no error | Network blocked / VPN | Disconnect VPN, retry |

After this block succeeds you do NOT need to re-run it for subsequent builds unless `installer/macos-pkg/payload-requirements.txt` changes. The wheelhouse is intentionally outside the repo (`${HOME}/MiningGuardian-vendor/`) so it never gets committed.

## Block Pre-B — Populate the Python runtime (P-026, 2026-05-05)

> **One-time per build host. Re-run only when bumping Python 3.12 patch level.**
> Skipping this block is now a hard build error — `build_pkg.sh` step 4i exits 43 if `${HOME}/MiningGuardian-vendor/python-runtime/` is missing, broken, the wrong version, or wrong tarball flavor (P-026, 2026-05-05). Catching it at build time saves an Apple notarization round-trip on a dead .pkg.

Why this exists: pre-P-026 the customer Mac mini had to have Homebrew `python@3.12` already installed — the .pkg's postinstall reached for `/opt/homebrew/opt/python@3.12/bin/python3.12`. Round 9 of the Mac mini install (2026-05-05, package `MiningGuardian-1.0.3-00720ab71cc4.pkg`) hit it live: `FATAL (38) python3.12 not found on this Mac`. Operator decision (Rob, 2026-05-05): "yes include it in the installer and whatever else might pop up as the install keeps going". The .pkg now owns its own Python 3.12 runtime; customers no longer need Homebrew on the Mini.

The recommended source is **python-build-standalone** (Astral's relocatable CPython tarballs, also used by `uv`, Rye, `hatch`, `mise`). Pick the `install_only_stripped` variant for `aarch64-apple-darwin`, Python 3.12.x. Anything else (a Homebrew Cellar tree, a hand-built `./configure --prefix=...` install) is rejected by step 4i because the install names will be hard-coded to the build-host paths and the relocatable invariants we depend on do not hold.

```zsh
# 1. Pick the latest Python 3.12.x install_only_stripped tarball for
#    aarch64-apple-darwin from Astral's python-build-standalone Releases:
#    https://github.com/astral-sh/python-build-standalone/releases
#    Tarball name pattern (example, replace with the latest):
#      cpython-3.12.7+20241016-aarch64-apple-darwin-install_only_stripped.tar.gz
#
#    Set the URL once and the rest of the block reuses it. Pinning a
#    specific date+release tag (the `+YYYYMMDD` suffix) is REQUIRED for
#    reproducible builds.
PYTHON_BUILD_STANDALONE_URL="https://github.com/astral-sh/python-build-standalone/releases/download/20241016/cpython-3.12.7+20241016-aarch64-apple-darwin-install_only_stripped.tar.gz"

# 2. Wipe any older runtime — refuse to mix patch levels.
rm -rf "${HOME}/MiningGuardian-vendor/python-runtime"
mkdir -p "${HOME}/MiningGuardian-vendor/python-runtime"

# 3. Download and extract. The install_only_stripped variant unpacks
#    into a top-level `python/` directory; we strip that one component
#    so the binary lands at ${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12
#    (the "flat" layout build_pkg.sh::step_4i accepts).
curl -fL "$PYTHON_BUILD_STANDALONE_URL" \
    | tar -xz -C "${HOME}/MiningGuardian-vendor/python-runtime" --strip-components 1

# 4. Sanity-check what landed.
"${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12" --version
# Expect: Python 3.12.x

# 5. Confirm the venv module is importable (rejects the build/ variant).
"${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12" -c 'import venv; print("venv OK")'
# Expect: venv OK

# 6. Confirm the binary is Mach-O (rejects accidentally-Linux tarball).
file -b "${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12"
# Expect: Mach-O 64-bit executable arm64
```

**Alternate accepted layout — Python.framework.** Some redistributions ship `Python.framework/Versions/3.12/...` instead of a flat `bin/lib/include` tree. `build_pkg.sh::step_4i` accepts either layout. If you use the framework variant, extract so the binary lands at `${HOME}/MiningGuardian-vendor/python-runtime/Python.framework/Versions/3.12/bin/python3.12`.

**After Pre-B succeeds, re-run Block Pre-A using the packaged interpreter** so the wheel ABI tags match the runtime exactly:

```zsh
# Replace the build-host Homebrew python in Block Pre-A's `pip download`
# with the just-vendored runtime. This guarantees the wheelhouse and
# runtime are CPython-version-compatible.
"${HOME}/MiningGuardian-vendor/python-runtime/bin/python3.12" -m pip download \
    --only-binary=:all: \
    --platform macosx_11_0_arm64 \
    --python-version 3.12 \
    --implementation cp \
    --abi cp312 \
    -d "${HOME}/MiningGuardian-vendor/python-wheels" \
    -r installer/macos-pkg/payload-requirements.txt
```

**Build-time guardrails (build_pkg.sh::step_4i, P-026):**

| Failure | Build outcome | Fix |
|---|---|---|
| `${HOME}/MiningGuardian-vendor/python-runtime/` missing | exit 43 | Run Block Pre-B above |
| `bin/python3.12` not present and framework variant not present | exit 43 | Wrong tarball flavor — pick `install_only` or `install_only_stripped` |
| Binary is not Mach-O (e.g. accidentally pulled the Linux tarball) | exit 43 | Pick the `aarch64-apple-darwin` build |
| Binary reports a non-3.12 version | exit 43 | Wrong tarball — pick a `cpython-3.12.x+YYYYMMDD` release |
| `import venv` fails | exit 43 | Wrong tarball variant — pick `install_only` (the `build` variant ships only the C compile artifacts) |
| Post-rsync sanity check fails | exit 43 | Filesystem issue (broken symlinks, lost executable bits) — re-extract from scratch |

After this block succeeds you do NOT need to re-run it for subsequent builds unless you bump the Python 3.12 patch level. Just like the wheelhouse, the runtime is intentionally outside the repo (`${HOME}/MiningGuardian-vendor/`) so it never gets committed.

## Block A — Build, sign, notarize, staple (one command)

```zsh
make pkg
```

`build_pkg.sh` runs end-to-end:
1. `productbuild` → unsigned `.pkg`
2. `productsign` → signed with **Developer ID Installer: Robert Fiesler (ARJZ5FYU94)**
3. `xcrun notarytool submit --wait` → Apple notary (expect **Accepted** in 3–5 min)
4. `xcrun stapler staple` → ticket attached to the file

Look for these lines at the end:
```
✓ submission status: Accepted
✓ stapled
✓ build/MiningGuardian-1.0.0-<newsha>.pkg
```

**The `<newsha>` is the NEW short hash. Keep it on screen — you'll paste it 4 more times.**

## Block B — Capture the new artifact identity

```zsh
# new file path (tab-complete the sha after typing -1.0.0-)
NEW_PKG=$(ls -1t build/MiningGuardian-1.0.0-*.pkg | head -1)
echo "New pkg: $NEW_PKG"

# sha
NEW_SHA=$(shasum -a 256 "$NEW_PKG" | awk '{print $1}')
echo "sha256: $NEW_SHA"

# extract the short id from the filename (the bit between -1.0.0- and .pkg)
NEW_SHORT=$(basename "$NEW_PKG" .pkg | sed 's/MiningGuardian-1.0.0-//')
echo "short id: $NEW_SHORT"
```

## Block C — Verify locally before shipping

```zsh
# Gatekeeper check
spctl --assess --type install --verbose=4 "$NEW_PKG"
# Expect: "$NEW_PKG: accepted" + "source=Notarized Developer ID"

# Stapled ticket present
xcrun stapler validate "$NEW_PKG"
# Expect: "The validate action worked!"

# Notarization receipt embedded
codesign -dv --verbose=4 "$NEW_PKG" 2>&1 | grep -i "notarization\|TeamIdentifier"
```

If ANY of these fail, do NOT ship. Re-read the build log.

## Block D — Refresh the USB stick (do NOT erase)

The "MG Install" stick is ExFAT and persistent. We replace the file, we do not reformat.

```zsh
# 1. Plug the stick in. Wait for it to mount.
ls /Volumes/ | grep -i "MG Install"
# Expect: "MG Install"

# 2. List what's there now
ls -lh "/Volumes/MG Install/"

# 3. Remove the old .pkg (the unbranded c7030d6...65f8 one, or whatever the prior was)
rm "/Volumes/MG Install/"MiningGuardian-1.0.0-*.pkg

# 4. Copy the new one
cp "$NEW_PKG" "/Volumes/MG Install/"

# 5. Update INSTALL.txt with the new sha (regenerate from template)
cat > "/Volumes/MG Install/INSTALL.txt" <<EOF
Mining Guardian v1.0.0 — install instructions

1. Double-click MiningGuardian-1.0.0-${NEW_SHORT}.pkg
2. Follow the installer prompts
3. macOS will check Apple's notarization (one network call) — let it
4. After install, run from /Applications/Mining Guardian/

Verify integrity (optional):
  shasum -a 256 MiningGuardian-1.0.0-${NEW_SHORT}.pkg
  Expected: ${NEW_SHA}

Signed by:    Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
Notarized:   Yes (stapled)
Bitcoin SHA-256 miners only.

Built: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
EOF

# 6. Verify the copy is good
shasum -a 256 "/Volumes/MG Install/MiningGuardian-1.0.0-${NEW_SHORT}.pkg"
# Expect the same sha as $NEW_SHA above

# 7. Eject
diskutil eject "MG Install"
```

**Why we don't erase:** ExFAT is fine, the stick is healthy, we already verified round-trip Gatekeeper acceptance from this stick. Erasing buys nothing, costs time, and risks the stick. Just replace the file.

## Block E — Refresh the GitHub Release

Two options. Pick based on whether the new build is "same release, replaced asset" or "new release tag."

### E.1 — Same tag, replace the asset (most common; new build of same version)

```zsh
# Replace the asset on the existing release
gh release upload "v1.0.0-${NEW_SHORT}" "$NEW_PKG" \
  --repo robertfiesler-spec/Mining-Guardian \
  --clobber
```

Wait — that won't work because the tag itself encodes the short id. So in practice:

### E.2 — New tag for the new build (recommended; one-to-one mapping)

```zsh
# 1. Tag the new build
git tag -a "v1.0.0-${NEW_SHORT}" -m "v1.0.0 build ${NEW_SHORT}"
git push origin "v1.0.0-${NEW_SHORT}"

# 2. Create the release (private, draft first if you want to inspect)
gh release create "v1.0.0-${NEW_SHORT}" \
  --repo robertfiesler-spec/Mining-Guardian \
  --title "v1.0.0 build ${NEW_SHORT}" \
  --notes-file docs/RELEASE_NOTES_v1.0.0.md \
  --prerelease=false \
  "$NEW_PKG"

# 3. (Optional) delete the prior build's release if it's now obsolete
# gh release delete "v1.0.0-978ff61126ea" --repo robertfiesler-spec/Mining-Guardian --yes
# git tag -d "v1.0.0-978ff61126ea"
# git push origin :refs/tags/v1.0.0-978ff61126ea
```

**Decision rule:** keep the prior release's assets alive for ~24h after a new build, in case someone has a download in progress. Then delete.

## Block F — Update RELEASE_NOTES + RUNBOOK with the new sha

```zsh
# 1. RELEASE_NOTES_v1.0.0.md — find the sha line, update with new
sed -i '' "s/c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8/${NEW_SHA}/g" \
  docs/RELEASE_NOTES_v1.0.0.md

# 2. Same for RUNBOOK_DISTRIBUTION_v1.0.0.md if it pins the old sha
sed -i '' "s/c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8/${NEW_SHA}/g" \
  docs/RUNBOOK_DISTRIBUTION_v1.0.0.md

# 3. Commit
git add docs/RELEASE_NOTES_v1.0.0.md docs/RUNBOOK_DISTRIBUTION_v1.0.0.md
git commit -m "docs: update v1.0.0 sha to ${NEW_SHORT} (post-rebuild)"
git push origin main
```

## Block G — Round-trip verification (the acceptance test)

```zsh
# Download from the GitHub Release back to a fresh location, verify
mkdir -p /tmp/mg_roundtrip && cd /tmp/mg_roundtrip
gh release download "v1.0.0-${NEW_SHORT}" \
  --repo robertfiesler-spec/Mining-Guardian \
  --pattern "*.pkg"

# 1. sha matches
shasum -a 256 MiningGuardian-1.0.0-${NEW_SHORT}.pkg
# Expect: ${NEW_SHA}

# 2. Gatekeeper accepts the downloaded copy
spctl --assess --type install --verbose=4 MiningGuardian-1.0.0-${NEW_SHORT}.pkg
# Expect: "accepted" + "source=Notarized Developer ID"

# 3. Provenance attribute (Sequoia+ marks files downloaded from internet)
xattr MiningGuardian-1.0.0-${NEW_SHORT}.pkg
# Expect: com.apple.provenance + com.apple.quarantine
```

If all three pass, the new build is **shippable across all three install paths**: local `build/`, GitHub Release download, USB stick.

## Block H — Tell future-you what just happened

Add a 5-line entry to `docs/SESSION_LOG_<today>.md`:

```
## Rebuild ${NEW_SHORT} — <timestamp>
- New pkg: build/MiningGuardian-1.0.0-${NEW_SHORT}.pkg
- sha256: ${NEW_SHA}
- Notarization: Accepted (submission <id from notarytool log>)
- USB stick refreshed, GitHub Release v1.0.0-${NEW_SHORT} created
- Round-trip from GitHub: PASS
```

Commit. Done.

## Common failures and fixes

| Symptom | Cause | Fix |
|---|---|---|
| `make pkg` errors at productsign | Keychain locked | `security unlock-keychain ~/Library/Keychains/login.keychain-db` |
| notarytool says "In Progress" >10 min | Apple notary slow | Wait. It can take up to 30 min on bad days. Don't kill `make pkg`. |
| notarytool says "Invalid" | Inner binary not codesigned, or .app bundle seal broken, or vendored Python wheel `.so` not signed (P-011) | First check the auto-fetched detail log next to the .pkg: `build/MiningGuardian-<version>-<sha>.notarization-detail.json` (P-011 added this auto-fetch). If it lists rejections under `python-wheels/*.whl/*.so`, P-011's `step_4c_resign_inner_wheels` should have caught them — confirm `installer/macos-pkg/scripts/lib/resign_wheel.py` ran and that the `[resign_wheel]` summary line shows `0 failure(s)`. If `.app` / `.framework` rejections appear, this is the PR #51 path: check the bundle's `_CodeSignature/CodeResources` seal. Manual fetch fallback: `xcrun notarytool log <submission-id> --keychain-profile mg-notary`. |
| `spctl --assess` says "rejected" on the downloaded copy | staple didn't survive download | Re-staple, re-upload. Apple CDNs sometimes strip xattrs; the stapled ticket should NOT be one of those (it's embedded). |
| USB shows old file even after `cp` | macOS Finder cached, or `cp` didn't actually finish | `sync && diskutil eject "MG Install"`, replug, verify |

## What this runbook does NOT cover

- Bumping the version number (1.0.0 → 1.0.1). That's a code change; touch `pyproject.toml`, then come here.
- New code-signing identity rotation. Separate runbook (TBD when Apple expires the cert).
- Cross-architecture builds (x86_64). Not in scope; we ship arm64 only.

---

*Written 2026-04-28. Pair with `docs/RUNBOOK_DISTRIBUTION_v1.0.0.md` (which covers the first-time chain) and `docs/SESSION_LOG_2026-04-28.md` (which covers the day this runbook was forged).*

---

## Addendum 2026-05-04 — P-011 wheel re-signing (Apple notary `Invalid` on inner `.so`)

Added after the v1.0.3 first build (`MiningGuardian-1.0.3-295aec38f2ee.pkg`, submission `750c089f-f0a1-4d40-bf15-e8c295828027`) returned `Invalid` from Apple notary with rejections inside vendored Python wheels (aiohttp `_http_writer`, `_http_parser`, `_websocket/mask`, `_websocket/reader_c`; bcrypt `_bcrypt.abi3.so` x86_64+arm64 in the universal2 wheel; matplotlib's compiled extensions; etc.).

**Root cause.** Upstream Python wheels (PyPI) ship Mach-O binaries signed by their package maintainer's certificate, NOT with our Developer ID Application identity, AND without a secure timestamp, AND in many cases without hardened runtime opted in. Apple notary walks every Mach-O file inside the .pkg payload — including ones embedded inside `.whl` zip archives — and rejects the submission if any of them fails the three-criteria check. The notary log lines look like:

```
Path: Payload/.../python-wheels/aiohttp-3.13.5-cp312-cp312-macosx_*.whl/aiohttp/_http_writer.cpython-312-darwin.so
Architecture: arm64
Issue: not signed with valid Developer ID certificate
Issue: no secure timestamp
```

**The fix.** `build_pkg.sh` now runs `step_4c_resign_inner_wheels` between `step_4b_codesign_inner_binaries` (which signs loose runtime binaries) and `step_5_pkgbuild_and_sign`. The new step shells out to `installer/macos-pkg/scripts/lib/resign_wheel.py`, which for every `*.whl` in `<payload>/python-wheels/`:

1. Extracts the wheel into a temp dir.
2. Finds every Mach-O via `file -b` (covers `.so`, `.dylib`, fat universal2 binaries).
3. `codesign --force --sign "$APPLE_DEV_ID_APPLICATION" --options runtime --timestamp` on each.
4. Recomputes sha256 + size and rewrites the wheel's `*.dist-info/RECORD` manifest line for every modified file.
5. Re-zips the wheel deterministically and atomic-moves over the original.
6. Runs a post-rewrite verify pass (sha256 + size of every RECORD entry vs the actual zip bytes) — fails the build with exit 49 if RECORD has drifted, so we catch a programmer error here rather than ship a wheel that bricks `pip install` on the customer Mac.

Pure-Python wheels are skipped (no Mach-O → nothing to do, RECORD untouched, pip install still works offline).

**What this means for the operator.**

* No new manual step. `make pkg` keeps running end-to-end exactly as before. The 4c step adds maybe 10–60 s to the build depending on how many C-extension wheels are in the closure (108 wheels in the v1.0.3 closure ⇒ ~12 wheels with Mach-O ⇒ ~30–60 codesign calls plus their TSA round-trips).
* If `step_4c_resign_inner_wheels` fails, `build_pkg.sh` exits 49 with the failing wheel's name in the `[resign_wheel]` log lines just above. Common causes: keychain locked (re-run `security unlock-keychain ~/Library/Keychains/login.keychain-db`), TSA unreachable (transient — retry), or a corrupted vendored wheel (re-run Block Pre-A's `pip download`).
* If notary still returns `Invalid` after a clean P-011 build, the `step_6_notarize` auto-fetch (also added in P-011) writes the detailed JSON to `build/MiningGuardian-<version>-<sha>.notarization-detail.json` next to the summary log. Read that first before re-running.

**Why this didn't bite us before v1.0.3.** Pre-v1.0.3 `.pkg` builds did not vendor Python wheels — the install assumed an internet-connected Mac that could `pip install` from PyPI at install time (out of spec for the local-first Mac Mini deployment). D-18 Gap 5 (P-002, 2026-05-04) added the offline wheelhouse to `<payload>/python-wheels/`. P-011 (this addendum) closes the loop by re-signing the wheels' inner binaries so the offline-vendored payload survives Apple notary.

**Files touched in P-011.**

| File | Change |
|---|---|
| `installer/macos-pkg/scripts/build_pkg.sh` | New `step_4c_resign_inner_wheels`; main() ordering 4 → 4b → 4c → 5; `step_6_notarize` auto-fetches detail log on failure; exit code 49 documented |
| `installer/macos-pkg/scripts/lib/resign_wheel.py` | New helper (440 lines, stdlib-only) |
| `tests/installer/test_wheel_resign.sh` | New regression test (15 assertions) |
| `docs/MG_UNIFIED_TODO_LIST.md` | New row 10c |
| `docs/RUNBOOK_PKG_REBUILD.md` | This addendum + Common failures row updated |
| `docs/DECISIONS.md` | New decision entry for the wheel-resign approach |
| `docs/LATENT_BUGS.md` | Note added so future sessions don't re-discover the same notary failure mode |

---

## Addendum 2026-04-29 — Installer.app WebKit lockdowns (Branded UI gotchas)

Added after the 2026-04-29 branding-rebuild session, where five `make pkg` rebuilds were burned learning these the hard way. If you are touching anything in `installer/macos-pkg/resources/` (the welcome HTML, conclusion HTML, or sidebar `background.png`), read this section before opening a PR — it will save you four notarization rounds.

The lockdowns below are **not documented by Apple**. They were discovered empirically during the PR #54 → PR #58 visual-debug arc. Each lockdown silently breaks a different cascade — the .pkg builds, signs, notarizes, and staples cleanly through every one of them; only the visual check after `open <pkg>` reveals the bug. Plan accordingly.

### Lockdown #1 — `html`/`body` `background` is forced transparent

Installer.app's internal WebKit stylesheet overrides any `background-color` or `background` you set on the `html` or `body` element. It silently strips them and lets the Installer.app chrome show through (which is white, not your designed dark color).

**Symptom:** Welcome / conclusion panel shows white background where you painted dark; text colors that assumed your dark background now look wrong (selection-blue blocks, broken contrast).

**Workaround:** Paint your background on an **inner div**, not on `html` or `body`. Or design for the white-default and use only inner colored elements (callouts, code pills, eyebrows).

```css
/* WRONG — Installer.app strips this */
body { background: #0A1428; color: #fff; }

/* RIGHT — paint the wrapper div */
body { padding: 32px; }
.page {
  background: #0A1428;
  color: #fff;
  padding: 24px;
  border-radius: 8px;
}
```

(The PR #55 attempt used a `.page` wrapper as the fix for Lockdown #1 — it succeeded at painting the navy background but immediately ran into Lockdown #2.)

### Lockdown #2 — CSS custom properties don't survive for `color`

`var(--x)` for `color` declarations works fine in standalone WebKit (Safari preview, `open file://welcome.html`) but **does not** work inside Installer.app. Installer.app injects an internal stylesheet that resets `color` after page load, breaking the cascade that CSS variables rely on.

**Symptom:** All text appears in the same color as the background — invisible. Eyebrows, headings, body, code, links — everything. The background paint works (Lockdown #1 worked-around), but text is gone.

**Workaround:** Use **literal hex values** for every `color` declaration, with `!important`. No CSS variables for color. Other property types (e.g. `background`, `border-color`, `padding`) survive variables fine — only `color` is reset.

```css
/* WRONG — works in Safari, breaks in Installer.app */
:root { --text: #0A1428; }
body { color: var(--text); }

/* RIGHT — literal hex, !important */
body { color: #0A1428 !important; }
h1, h2, h3 { color: #0A1428 !important; }
.eyebrow { color: #F7931A !important; }
code { color: #0A1428 !important; }
```

### Lockdown #3 — Sidebar PNG nav-zone tone

Installer.app paints its own step-list nav text overlay in the **top ~50%** of the sidebar (the strip running down the left side of the installer window). The labels are "Introduction / License / Destination Select / Installation Type / Installation / Summary". The active step is rendered in a brighter blue (readable on most backgrounds), but the inactive steps are rendered in a **dim/muted dark navy** that requires a **light or medium-tone background** to be readable.

If your `background.png` puts dark artwork (like a navy Hero shield) in that top zone, the inactive nav steps disappear into the artwork.

**Symptom:** "Introduction" is readable but the five inactive steps below it look completely missing or render as faint shadow. Active-step navigation works during install, but a static screenshot shows what looks like a one-step installer.

**Workaround:** Design `background.png` (620×1111) in two zones:

| Y range | Treatment |
|---|---|
| 0..540 | **Light or medium-tone** background. `#F1F4F9` (light cool grey) → `#E1E8F2` is a known-good gradient. Reserve this zone — no artwork, no dark colors. |
| 540..600 | Feather/transition zone — alpha-blend the seam color into the artwork below. 60px is enough to avoid a hard horizontal line. |
| 600..1111 | Your branding artwork — Hero shield, wordmark, etc. Can be as dark as you want; nav text doesn't reach this zone. |

`Distribution.xml` should keep `<background ... alignment="bottomleft" scaling="proportional"/>` — that anchors the artwork to the bottom regardless of the sidebar's actual rendered height, which keeps the feather seam stable across macOS versions.

### Visual-check protocol

Because all three lockdowns build/notarize cleanly, the only way to catch them is to actually open the .pkg and look:

```zsh
open ~/Documents/GitHub/Mining-Guardian/build/MiningGuardian-1.0.0-<sha>.pkg
```

Take a screenshot of the welcome screen. Verify:

1. **Right pane:** background is the color you intended (Lockdown #1 check), all text is readable in the colors you intended (Lockdown #2 check)
2. **Sidebar:** all six nav steps clearly visible — "Introduction" + the five inactive ones (Lockdown #3 check)
3. **Sidebar artwork:** anchored at the bottom, no hard horizontal seam where it meets the light zone

Click "Continue" once and re-screenshot the License panel — same sidebar, but the active-step highlight has moved. This catches any seam issue that only shows up at certain nav positions.

**Cancel out — do not actually install** during visual checks. We're testing the rendered Installer.app UI, not the install flow itself.

### When to repeat the rebuild cycle

If any of the three checks fails: fix the file, push as a new PR (single-file binary swap if it's `background.png`, or HTML edit if it's welcome/conclusion), merge, and run `make pkg` again. Each rebuild + notary round-trip is ~6-10 min. Budget 4-5 cycles the first time you touch any branded surface; budget 1 cycle once the lockdowns are internalized.

### Files in this lockdown family

| File | Lockdown surface | Test |
|---|---|---|
| `installer/macos-pkg/resources/welcome.html` | #1, #2 | right-pane visual check on welcome screen |
| `installer/macos-pkg/resources/conclusion.html` | #1, #2 | right-pane visual check after install (or simulated by clicking through to Summary) |
| `installer/macos-pkg/resources/background.png` | #3 | sidebar nav-zone visual check |
| `installer/macos-pkg/resources/Distribution.xml` | none of the three; controls layout/scaling/alignment of the above | — |

### Provenance for this addendum

Discovered during PR #54 → PR #58 (2026-04-29). Five `make pkg` rebuilds, five notary submissions (all Accepted by Apple — these were visual not signing rejections):

| # | Submission ID | Build SHA | Lockdown that broke it |
|---|---|---|---|
| 1 | `9f34a1ea-a5df-4d28-bbed-e4ca74170765` | `2f3bff5a8e28` (PR #54) | #1 — body bg stripped |
| 2 | `6b6596c0-67f8-44da-bb5d-9346e1e90f2c` | `5ba091d561fa` (PR #55) | #2 — `var(--text)` reset |
| 3 | `03f4a5c7-0798-4d06-9366-66fc5d1e6c18` | `e0e4bbe114f1` (PR #56) | #3 — sidebar nav-zone (right pane finally clean) |
| 4 | `e549d551-f0be-492a-a95c-8caa43a9c238` | `fb5b7038988c` (PR #57) | #3 — flat dark navy too dark for inactive nav |
| 5 | `6813ec95-7abc-4768-bd06-fe4f1acdf777` | `0f849bd217cc` (PR #58) | none — clean |

Full chronological narrative in `docs/SESSION_LOG_2026-04-29.md`.
