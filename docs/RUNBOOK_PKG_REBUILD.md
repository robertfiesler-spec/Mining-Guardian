# Runbook — Rebuild .pkg + refresh USB stick + refresh GitHub Release

> Use this every time a code change lands on `main` that you want to ship as a new `.pkg`.
> Paste-along blocks. Ten minutes end-to-end if Apple notary is fast. Mac zsh.

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
| notarytool says "Invalid" | Inner binary not codesigned, or .app bundle seal broken | This is what PR #51 fixed. Check the notary log: `xcrun notarytool log <submission-id> --keychain-profile mg-notary` |
| `spctl --assess` says "rejected" on the downloaded copy | staple didn't survive download | Re-staple, re-upload. Apple CDNs sometimes strip xattrs; the stapled ticket should NOT be one of those (it's embedded). |
| USB shows old file even after `cp` | macOS Finder cached, or `cp` didn't actually finish | `sync && diskutil eject "MG Install"`, replug, verify |

## What this runbook does NOT cover

- Bumping the version number (1.0.0 → 1.0.1). That's a code change; touch `pyproject.toml`, then come here.
- New code-signing identity rotation. Separate runbook (TBD when Apple expires the cert).
- Cross-architecture builds (x86_64). Not in scope; we ship arm64 only.

---

*Written 2026-04-28. Pair with `docs/RUNBOOK_DISTRIBUTION_v1.0.0.md` (which covers the first-time chain) and `docs/SESSION_LOG_2026-04-28.md` (which covers the day this runbook was forged).*
