# Runbook — Mining Guardian Distribution Cycle (Q2)

**Companion to:** `docs/RUNBOOK_2026-04-28_pkg_build.md` (which produces the .pkg).

This runbook picks up **after** `make pkg` has produced a signed, notarized, stapled, Gatekeeper-blessed `.pkg` in `build/`. Its job is to get that .pkg into all three install paths:

1. Private GitHub Release on `robertfiesler-spec/Mining-Guardian`
2. USB stick fallback ("MG Install" or any ExFAT-formatted equivalent)
3. (Implicit) operator's local `build/` folder — already there from `make pkg`

Estimated wall-clock time: **15–25 minutes**, mostly upload bandwidth + Apple round trips you've already paid in the build runbook.

---

## Variables (replace per release)

| Var | Example | How to find it |
|---|---|---|
| `VERSION` | `1.0.0-978ff61126ea` | from `.pkg` filename: `MiningGuardian-<VERSION>.pkg` |
| `BUILD_SHA` | `978ff61126ea` | last 12 chars of `VERSION` |
| `BUILD_SHA_FULL` | `978ff61126ea8acd21a41aa9d29293c9ec96dc0d` | `git rev-parse <BUILD_SHA>` |
| `TAG` | `v1.0.0-978ff61126ea` | `v<VERSION>` |
| `PKG_SHA256` | `c7030d69f56cf846014745c37eead0e5b79b10f0e29701d28ea1d550ceb765f8` | `cat build/MiningGuardian-<VERSION>.pkg.sha256` |
| `NOTARY_ID` | `2c4130a4-13e6-4783-9b06-b7969ccb36aa` | from the `make pkg` output ("Submission ID:") |

Set these in your shell before running the runbook:

```bash
VERSION="1.0.0-978ff61126ea"
BUILD_SHA="978ff61126ea"
TAG="v${VERSION}"
PKG="build/MiningGuardian-${VERSION}.pkg"
SHA="${PKG}.sha256"
REPO="robertfiesler-spec/Mining-Guardian"
```

---

## Block A — Pre-flight (~5 sec)

```bash
cd ~/Documents/GitHub/Mining-Guardian

# Files exist?
ls -la "$PKG" "$SHA"

# What hash did the build script record?
cat "$SHA"

# Will Gatekeeper accept it right now?
spctl -a -vvv -t install "$PKG"
```

Pass conditions:
- Both files exist
- `spctl` says `accepted` and `source=Notarized Developer ID`
- `cat "$SHA"` matches the value from `make pkg`'s closing banner

If any of these fail, do NOT proceed. Re-run `make pkg` (the build runbook).

---

## Block B — Tag the build commit (~5 sec)

The tag must point at the **build SHA**, not at current `main`. The .pkg filename embeds the build SHA, the notarization is tied to that exact tree, and anyone checking out the tag must get the exact source that produced this binary.

```bash
# Confirm the build SHA exists in your repo
git rev-parse "${BUILD_SHA}"

# Annotated tag with all the receipts
git tag -a "${TAG}" "${BUILD_SHA}" -m "Mining Guardian v${VERSION%-*} (build ${BUILD_SHA})

Build artifact:
  MiningGuardian-${VERSION}.pkg
  SHA-256: $(cat "$SHA" | awk '{print $1}')

Signing:
  Developer ID Installer:   Robert Fiesler (ARJZ5FYU94)
  Developer ID Application: Robert Fiesler (ARJZ5FYU94)

Notarization:
  Submission ID: <NOTARY_ID>
  Status: Accepted

Stapled: yes
Gatekeeper: accepted, source=Notarized Developer ID"

git push origin "${TAG}"
```

Verify it landed:

```bash
gh api "repos/${REPO}/git/refs/tags/${TAG}" --jq '.ref'
# Expect: refs/tags/v1.0.0-...
```

---

## Block C — Release notes (~2 min)

Generate from a template. Lives at `docs/RELEASE_NOTES_<VERSION>.md`.

Required sections (copy from `RELEASE_NOTES_v1.0.0.md` as the template):

1. Build artifact metadata (filename, size, SHA-256, build duration)
2. Signing & notarization chain (every stage of every signing pass + notarytool submission ID + spctl results)
3. Cert SHA-1 fingerprints (`Developer ID Application`, `Developer ID Installer`)
4. Install instructions — Option A (GitHub) + Option B (USB)
5. "What does NOT happen at install" (zero internet, zero telemetry, zero cloud)
6. Verifying after install (`pkgutil --pkg-info`, `xcrun stapler validate`)
7. Known issues (Lima 2.x VZ-only on Apple Silicon, intermediate CA requirement)
8. Provenance — how to reproduce this exact .pkg from source
9. Changelog of PRs since previous release
10. Full notarization submission ledger (every Invalid + the final Accepted)

---

## Block D — Repo visibility check + GitHub Release (~30 sec)

```bash
# Ensure repo is private (Q2 locked decision)
gh api "repos/${REPO}" --jq '.private'
# Expect: true

# If false, flip it:
gh repo edit "${REPO}" --visibility private --accept-visibility-change-consequences

# Create the release
gh release create "${TAG}" \
  --repo "${REPO}" \
  --title "Mining Guardian v${VERSION%-*} (build ${BUILD_SHA})" \
  --notes-file "docs/RELEASE_NOTES_${VERSION}.md" \
  --latest
```

---

## Block E — Upload assets (~2–5 min, bandwidth-bound)

```bash
gh release upload "${TAG}" \
  --repo "${REPO}" \
  "${PKG}" \
  "${SHA}" \
  --clobber
```

The `--clobber` flag is idempotent — re-running after a hiccup overwrites instead of erroring out.

Verify server-side:

```bash
gh api "repos/${REPO}/releases/tags/${TAG}" \
  --jq '{name: .name, assets: [.assets[] | {name: .name, size: .size, state: .state}]}'
```

Pass: both assets `state: uploaded`, sizes match local exactly.

---

## Block F — Round-trip verification (THE critical check, ~2 min)

This is the only step that proves a customer Mac will accept the .pkg. Server-side size match only proves bytes were uploaded; this proves the staple survived GitHub's CDN.

```bash
mkdir -p ~/Downloads/mg_release_test && cd ~/Downloads/mg_release_test

gh release download "${TAG}" --repo "${REPO}" --clobber
ls -la

# 1. Hash check
shasum -a 256 -c "MiningGuardian-${VERSION}.pkg.sha256"

# 2. Gatekeeper check on downloaded file
spctl -a -vvv -t install "MiningGuardian-${VERSION}.pkg"

# 3. (Bonus) confirm "internet download" attribute is present
xattr "MiningGuardian-${VERSION}.pkg"
```

Pass conditions:
- `shasum -c`: `OK`
- `spctl`: `accepted`, `source=Notarized Developer ID`
- `xattr`: shows `com.apple.provenance` (Sequoia+) or `com.apple.quarantine` (older macOS)

If `spctl` fails at this stage, the staple did not survive the upload — re-run Block E with `--clobber`.

---

## Block G — USB stick fallback (~5 min)

### G.1 — Format the stick

The stick must be **ExFAT** or APFS. FAT32 has a 4 GB per-file cap that bites future fatter releases.

```bash
# Replace "MG Install" with whatever you named the stick
diskutil info "/Volumes/MG Install" | grep -E "Volume Name|File System|Volume Total Space|Volume Free Space|Read-Only"

# If File System is "MS-DOS FAT32", reformat:
diskutil eraseVolume ExFAT "MG Install" "/Volumes/MG Install"
```

### G.2 — Write INSTALL.txt onto the stick

Use a plain heredoc (single-quoted terminator). Keep blocks **short** — long heredocs are paste-fragile.

```bash
cat > "/Volumes/MG Install/INSTALL.txt" <<'MGEOF'
Mining Guardian v<VERSION> - USB Install (Offline Fallback)
=========================================================

Build:    <BUILD_SHA>
Built:    <BUILD_DATE>
Signed:   Developer ID Installer: Robert Fiesler (ARJZ5FYU94)
Notarized + stapled (Apple submission <NOTARY_ID>)

INSTALL STEPS
-------------
1. Plug this stick into the target Mac.
2. Open Terminal.
3. Verify the file (one line):

   shasum -a 256 "/Volumes/MG Install/MiningGuardian-<VERSION>.pkg"

   Expected:
   <PKG_SHA256>

4. Confirm Gatekeeper trust:

   spctl -a -vvv -t install "/Volumes/MG Install/MiningGuardian-<VERSION>.pkg"

   Expected: accepted, source=Notarized Developer ID

5. Install (one of):
   A) Double-click the .pkg in Finder, OR
   B) sudo installer -pkg "/Volumes/MG Install/MiningGuardian-<VERSION>.pkg" -target /

VERIFY AFTER INSTALL
--------------------
   pkgutil --pkg-info com.miningguardian.pkg
   xcrun stapler validate /Applications/Ollama.app

POLICY
------
Bitcoin SHA-256 miners only. Local-only. Do not redistribute.
MGEOF

ls -la "/Volumes/MG Install/INSTALL.txt"
```

### G.3 — Copy the .pkg + sidecar onto the stick

```bash
# Source: the verified-clean download folder from Block F
cp ~/Downloads/mg_release_test/MiningGuardian-${VERSION}.pkg          "/Volumes/MG Install/"
cp ~/Downloads/mg_release_test/MiningGuardian-${VERSION}.pkg.sha256   "/Volumes/MG Install/"
ls -la "/Volumes/MG Install/"
```

### G.4 — Verify the stick

```bash
cd "/Volumes/MG Install/"
shasum -a 256 -c "MiningGuardian-${VERSION}.pkg.sha256"
spctl -a -vvv -t install "/Volumes/MG Install/MiningGuardian-${VERSION}.pkg"
```

### G.5 — Eject cleanly

```bash
cd ~ && diskutil eject "/Volumes/MG Install"
```

ExFAT writes are buffered. Yanking without ejecting can corrupt the filesystem. Always eject.

---

## Block H — Documentation PR (~5 min)

```bash
git checkout -b docs/<DATE>-distribution-${TAG#v}

# 1. Append distribution addendum to docs/SESSION_LOG_<DATE>.md
# 2. Append Section 14.x flip to docs/MG_UNIFIED_TODO_LIST.md
# 3. Add docs/RELEASE_NOTES_<VERSION>.md (already drafted in Block C)
# 4. (If runbook updates needed) edit this file

git add docs/
git commit -m "docs: distribution v${VERSION%-*} (${BUILD_SHA}) shipped — release + USB"
git push -u origin "docs/<DATE>-distribution-${TAG#v}"

gh pr create \
  --repo "${REPO}" \
  --base main \
  --title "docs: distribution v${VERSION%-*} (${BUILD_SHA}) shipped" \
  --body "..."
```

Squash-merge per the locked branch cadence (one narrow branch per PR, deleted after merge).

---

## Pass-fail gate for the whole runbook

A release is shippable when **all six** of these are true:

1. Block A — local `spctl` accepts the .pkg
2. Block B — `git push` of the annotated tag succeeded
3. Block D — `gh api .../releases/tags/${TAG}` returns the release
4. Block E — both assets `state: uploaded`, sizes match
5. Block F — round-trip download passes `shasum -c` AND `spctl` AND `xattr` shows internet-download attribute
6. Block G.4 — USB copy passes `shasum -c` AND `spctl`

Skip any of these at your peril.

---

## What can go wrong (and what to do)

| Symptom | Cause | Fix |
|---|---|---|
| `gh release upload` hangs | Slow upload connection | Wait. If still hung after 5 min, Ctrl+C and re-run with `--clobber` |
| Block F `spctl` says rejected | Staple didn't survive upload | Re-run Block E with `--clobber` |
| `xattr` shows neither `quarantine` nor `provenance` | File didn't go through "internet path" | Make sure you're running on the **downloaded** copy, not the local `build/` copy |
| FAT32 4 GB error | Wrong filesystem | Reformat to ExFAT (Block G.1) |
| Heredoc paste hangs at `>` continuation prompt | EOF token didn't paste cleanly | Ctrl+C, split into smaller paste blocks |
| `gh repo edit` says "consent required" | Privacy-flip needs explicit confirmation flag | Add `--accept-visibility-change-consequences` |

---

## Glossary

- **Build SHA** — the git commit hash baked into the .pkg filename. The notarization is tied to this exact source tree.
- **Notary submission ID** — the UUID Apple returns from `notarytool submit`. Permanent record of "this binary was Accepted on date X."
- **Staple** — `xcrun stapler staple` embeds Apple's "yes I notarized this" ticket into the .pkg, so the target Mac doesn't need internet to verify trust.
- **Gatekeeper assessment** — `spctl -a -t install` runs the same trust check macOS runs at install time.
- **Round-trip verification** — pretending to be a customer: download from the real URL, hash, run Gatekeeper, confirm.

---

*Bitcoin SHA-256 miners only. Local-only. Postgres-as-truth.*
