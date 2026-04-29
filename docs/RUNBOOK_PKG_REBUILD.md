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
