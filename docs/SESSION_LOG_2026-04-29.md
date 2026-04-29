# Session Log — 2026-04-29 (Wednesday)

**Operator:** Bobby Fiesler (BigBobby)
**Agent:** Perplexity Computer
**Session window:** Wednesday 2026-04-29 ~05:19 PDT through ~08:21 CDT, single working segment.
**Commits shipped to `main`:**

| PR | SHA | Subject |
|---|---|---|
| #54 | `2f3bff5a8e28` | Initial branded welcome + conclusion HTML + sidebar background + brand PDFs + docs |
| #55 | `5ba091d561fa` | `.page` wrapper attempt (caused navy-on-navy bug) |
| #56 | `e0e4bbe114f1` | Light-theme rebuild, literal hex `!important` |
| #57 | `fb5b7038988c` | Sidebar PNG: reserve top 50% as flat dark navy |
| #58 | `0f849bd217cc` | Sidebar PNG: switch top zone to light blue-grey gradient |

---

## TL;DR

Yesterday's session ended with PR #54 sitting open, clean, and mergeable — the initial branded welcome/conclusion HTML plus sidebar `background.png`. That PR had passed a Playwright-rendered composite mockup review and looked correct in the preview. What the preview did not expose was how macOS Installer.app actually renders the HTML content at install time. When PR #54 merged and `make pkg` ran this morning, the visual check on the real installer revealed a white background blowing through the entire right pane — the navy background declarations on `html` and `body` had been silently stripped. That was the first of three undocumented Installer.app WebKit lockdowns discovered today.

Four more PRs and four more `make pkg` cycles followed. PR #55 introduced a `<div class="page">` wrapper with an explicit navy background — which fixed the right-pane white-out but revealed a second lockdown: CSS custom properties (`var(--text)`) do not survive Installer.app's internal color reset, so all text became invisible against the now-navy div. The pivot to a light theme came from the operator directly: "Maybe we go with a white background and navy writing or black to make it simple, i like what you are doing but maybe the program is too locked down like you said." That call was correct and unblocked the path forward. PR #56 rewrote the right pane for a white background with navy text and BTC-orange accents, all literal hex with `!important`, no CSS variables.

With the right pane finally stable, attention moved to the sidebar. PR #57 rebuilt `background.png` with the top 50% reserved as flat dark navy (`#0A1428`) to accommodate Installer.app's step-list nav overlay — but a third lockdown surfaced: the inactive step labels (\"License\", \"Destination Select\", etc.) are painted by Installer.app itself in a dim dark navy that requires a light or medium-tone background to be readable. They were invisible on the flat-navy zone. PR #58 replaced the top 555 px with a light blue-grey gradient (`#F1F4F9` → `#E1E8F2` → `#C8D2E0`) feathered into the existing artwork below. The operator's verdict on the final visual was "much better." All six nav steps became clearly readable.

The final build, `0f849bd217cc`, is shippable. It is notarized (submission `6813ec95-7abc-4768-bd06-fe4f1acdf777`, Accepted), stapled, Gatekeeper-verified, uploaded to a new GitHub Release tagged `v1.0.0-0f849bd217cc` (now Latest), and written to the USB stick. The old release `v1.0.0-978ff61126ea` has been demoted to Pre-release and kept for audit trail. The round-trip download-and-verify from GitHub passed cleanly. The three Installer.app WebKit lockdowns are now documented in `docs/RUNBOOK_PKG_REBUILD.md` so future maintainers do not rediscover them the hard way.

---

## Opening state (2026-04-29 morning)

**`main` tip at session start:** `9e24a94` (PR #53 — the prior session's distribution runbook and miscellaneous doc work).

**PR #54 state:** open, clean, mergeable, rebased onto `9e24a94`. This PR had been built and reviewed the prior evening (see 2026-04-28 evening addendum). It contained the initial `welcome.html`, `conclusion.html`, `background.png`, three customer PDFs, and the docs README. The composite Playwright mockups had passed visual review, but those mockups rendered the HTML in a standalone WebKit context — not inside Installer.app's constrained environment. That distinction would prove material within the first `make pkg` of the morning.

**GitHub Release:** `v1.0.0-978ff61126ea` was the sole release, tagged Latest. Assets: `MiningGuardian-1.0.0-978ff61126ea.pkg` (392,562,726 bytes) + `.sha256` sidecar. Stapled, notarized, Gatekeeper-accepted.

**USB stick ("MG Install"):** ExFAT, held `MiningGuardian-1.0.0-978ff61126ea.pkg` + `.sha256` + `INSTALL.txt`. The stick had been refreshed during the afternoon addendum of 2026-04-28. Contents still valid, but the `.pkg` inside was the unbranded build — the same one about to be superseded.

**Local build folder:** `~/Documents/GitHub/Mining-Guardian/build/` contained `MiningGuardian-1.0.0-978ff61126ea.pkg` from the prior session. The build chain was clean and the signing identities were confirmed valid.

---

## Chronological work

### Build #1 — PR #54 → `2f3bff5a8e28`

**Notarization submission:** `9f34a1ea-a5df-4d28-bbed-e4ca74170765` — Accepted.

PR #54 merged into `main`. Robert ran:

```zsh
cd ~/Documents/GitHub/Mining-Guardian
git checkout main && git pull --ff-only
make pkg
```

The build completed cleanly. `build_pkg.sh` ran all nine steps: `pkgbuild` → `productbuild` → `productsign` → step_4b codesign inner binaries → assemble → notarize → staple → sha256 sidecar → Gatekeeper check. Apple returned Accepted in approximately four minutes.

**Visual check #1:** Robert opened the new `.pkg` to step through the Installer.app UI. The right pane — the main content area displaying `welcome.html` — showed a white background. The dark navy page background declared on `html` and `body` in the HTML was not rendering. All the text was readable (since it was dark-on-white), but the branded dark theme was entirely absent. The sidebar `background.png` was rendering correctly in the left column.

**Diagnosis — Lockdown #1:** Installer.app's internal stylesheet forces `html` and `body` to `background: transparent`. Any `background-color` or `background` declaration on those elements is overridden before the HTML is rendered in the installer's WebKit view. The Playwright composite mockup had shown the correct dark background because it rendered the HTML in a full standalone browser context with no such override. The installer environment is not a full browser context.

**Decision:** do not re-notarize on this build. The signing is clean and the binary is correct — only the visual presentation needs adjustment. Push a targeted CSS fix in a new PR.

---

### Build #2 — PR #55 → `5ba091d561fa`

**Notarization submission:** `6b6596c0-67f8-44da-bb5d-9346e1e90f2c` — Accepted.

The fix attempt for Lockdown #1 was to wrap all visible content in a `<div class="page">` and paint the navy background on that div rather than on `html` or `body`. The CSS:

```css
.page {
  background-color: var(--bg);   /* #0A1428 */
  min-height: 100vh;
  padding: 32px 36px;
}
```

This was logical: if Installer.app strips `html`/`body` background, paint it on a child div that Installer.app has no reason to touch.

`make pkg` ran, notarization came back Accepted.

**Visual check #2:** The navy background now rendered on the right pane. But all body text had vanished. The pane was navy with no visible copy — a solid dark rectangle. Robert identified the issue precisely: "ok i can barely see it but if you look where i put the red box there is writing, but it is navy on navy so it cant be seen."

**Diagnosis — Lockdown #2:** Installer.app injects a stylesheet reset that strips `color` from the cascade. The `color: var(--text)` declaration resolving to `#E6ECF5` was being wiped, leaving browser-default `color: black` in place — which is invisible on `#0A1428`. This is a CSS custom property (variable) survival problem: the custom property itself was defined correctly in `:root`, but the cascade reset fired after variable resolution, not before, so the computed `color` was overwritten back to the UA default.

---

### The pivot

After Build #2's navy-on-navy result, Robert stepped back from the individual CSS debugging loop and offered a different frame:

> "Maybe we go with a white background and navy writing or black to make it simple, i like what you are doing but maybe the program is too locked down like you said"

This was the right call. The underlying constraint — Installer.app's internal stylesheet is not fully documented and is not overridable through normal CSS specificity — means that fighting the dark theme in the right pane was going to produce an unpredictable series of regressions. A white-background theme works *with* Installer.app's defaults rather than against them. The design language (navy text `#0A1428`, BTC-orange accents `#F7931A`) could survive the light theme intact. The branded PDF documents, the sidebar art, and the conclusion screen's success indicator all carry the brand weight. The right-pane HTML does not need to be dark to be on-brand.

The operator also established the session's working principle early on:

> "step by step please i need to focus" / "i have ocd and i hate slop or messes"

This framing was useful: rather than trying to fix all three lockdowns simultaneously in a single PR, each build cycle targeted one clearly defined problem. The session's five-PR structure reflects that discipline.

---

### Build #3 — PR #56 → `e0e4bbe114f1`

**Notarization submission:** `03f4a5c7-0798-4d06-9366-66fc5d1e6c18` — Accepted.

Complete light-theme rebuild of both `welcome.html` and `conclusion.html`. Key decisions:

- **`html`, `body` background:** removed entirely. Let Installer.app's default white show through. This resolves Lockdown #1 by not fighting it.
- **All text colors:** replaced every `var(--*)` reference with literal hex and `!important`. No CSS custom properties remain in the `color` or `background-color` declarations. This resolves Lockdown #2 by not relying on the variable cascade.
- **Navy text:** `color: #0A1428 !important` on all body copy.
- **BTC orange accents:** `color: #F7931A !important` on eyebrow text, `sudo` keyword, bullet accents.
- **Card surfaces:** `background-color: #F5F7FA !important` (very light grey) with `border: 1px solid #D0D8E4 !important`.

Representative snippet from `welcome.html` after PR #56:

```css
body {
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
  color: #0A1428 !important;
  margin: 0;
  padding: 24px 28px;
}
h1 {
  color: #0A1428 !important;
  font-size: 22px;
  font-weight: 700;
}
.accent {
  color: #F7931A !important;
}
.card {
  background-color: #F5F7FA !important;
  border: 1px solid #D0D8E4 !important;
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
```

`make pkg` ran, notarization Accepted.

**Visual check #3:** Right pane confirmed good. Navy-on-white text rendered correctly. BTC-orange accents visible. Card surfaces readable. No missing copy, no invisible text. However, Robert noticed a problem with the sidebar: the step-list nav (\"Introduction\", \"License\", \"Destination Select\", \"Installation Type\", \"Installation\", \"Summary\") was dim or invisible. He captured a screenshot with a red box around the affected zone. The sidebar `background.png` was a full-bleed dark navy image, and Installer.app's own nav overlay was painting step labels in a muted dark tone that disappeared into the navy art.

This was a separate problem from the right-pane lockdowns — the sidebar is driven by `background.png`, not by HTML. The next two PRs addressed it.

---

### Build #4 — PR #57 → `fb5b7038988c`

**Notarization submission:** `e549d551-f0be-492a-a95c-8caa43a9c238` — Accepted.

**Approach:** rebuild `background.png` with the top 50% of the image reserved as a flat solid dark navy (`#0A1428`) band. The reasoning was: Installer.app overlays its nav step-list in the top portion of the sidebar; if the background under those labels matches or is close to the step-label color, they become invisible. A flat, known-color zone would at least make the geometry predictable.

The image was generated using the nano_banana_2 img2img pipeline with the Hero shield reference as the control input, constrained to paint the artwork in the lower half of the 620×1111 canvas and leave the top 310 px as flat `#0A1428`. The lower half retained the Hero shield + crossed pickaxes + Bitcoin orb + electric-blue circuit lines + "MINING GUARDIAN" wordmark from the original `background.png`.

`make pkg` ran, notarization Accepted.

**Visual check #4:** The active step — "Introduction", highlighted in Installer.app's brighter style — was now readable against the navy zone. The remaining five inactive steps were still invisible. They had not appeared.

**Diagnosis — Lockdown #3:** Installer.app paints its inactive step labels in a dim, muted dark navy tone (approximately `#1A2744` or similar system color). That color is only legible against a light or medium-tone background. A flat dark-navy background under those labels produces zero contrast — the same lockdown class as the body-text issue, but applied to the sidebar art rather than the HTML. Installer.app's active step is painted in a brighter blue-white and survives on dark; the inactive steps do not.

The flat `#0A1428` top zone was the correct idea structurally (reserve the top for the nav) but the wrong color choice (dark on dark is still dark on dark).

---

### Build #5 — PR #58 → `0f849bd217cc`

**Notarization submission:** `6813ec95-7abc-4768-bd06-fe4f1acdf777` — Accepted.

**Approach:** replace the top 555 px of `background.png` with a light blue-grey gradient running `#F1F4F9` → `#E1E8F2` → `#C8D2E0`, then feather the boundary from y=540 through y=600 into the existing dark navy artwork below. This kept the Hero shield artwork intact in the lower portion of the sidebar and gave Installer.app's inactive step labels a light-toned zone to render against. The entire operation was a pure Python PIL post-process — no AI re-generation, no changes to the lower half of the image.

Core of the PIL script:

```python
from PIL import Image, ImageDraw
import numpy as np

img = Image.open("background.png").convert("RGBA")
arr = np.array(img, dtype=np.float32)

# Top gradient: #F1F4F9 at y=0, #E1E8F2 at y=277, #C8D2E0 at y=554
for y in range(555):
    t = y / 554.0
    if t < 0.5:
        r = 241 + (225 - 241) * (t / 0.5)
        g = 244 + (232 - 244) * (t / 0.5)
        b = 249 + (242 - 249) * (t / 0.5)
    else:
        r = 225 + (200 - 225) * ((t - 0.5) / 0.5)
        g = 232 + (210 - 232) * ((t - 0.5) / 0.5)
        b = 242 + (224 - 242) * ((t - 0.5) / 0.5)
    arr[y, :, 0] = r
    arr[y, :, 1] = g
    arr[y, :, 2] = b
    arr[y, :, 3] = 255

# Feather zone y=540..600: blend gradient into existing art
for y in range(540, 601):
    alpha = (y - 540) / 60.0          # 0.0 at y=540 → 1.0 at y=600
    arr[y] = arr[y] * alpha + original_arr[y] * (1.0 - alpha)

result = Image.fromarray(arr.astype(np.uint8), "RGBA")
result.save("background.png")
```

`make pkg` ran, notarization Accepted.

**Visual check #5:** Robert's response: "much better." All six nav steps — Introduction, License, Destination Select, Installation Type, Installation, Summary — were clearly readable in the sidebar. The gradient light zone provided sufficient contrast for both the active (bright) and inactive (dim) step label styles that Installer.app paints. The lower-half artwork was undisturbed.

Build `0f849bd217cc` was confirmed shippable.

---

## The three Installer.app WebKit lockdowns (consolidated)

Five build cycles over the course of the morning produced a complete map of the constraints that Installer.app imposes on its embedded HTML and sidebar PNG content. These are not documented by Apple in the Distribution XML reference or the `productbuild` man page. They are captured here and in `docs/RUNBOOK_PKG_REBUILD.md` so that any future maintainer working on installer branding does not rediscover them through iteration.

### Lockdown #1: `html` / `body` `background` is forced transparent

Installer.app's internal stylesheet overrides any `background`, `background-color`, or `background-image` declaration placed on the `html` or `body` elements. The override fires at a specificity level that cannot be beaten by author stylesheets, including `!important` declarations on those specific selectors.

**Effect:** a dark-themed HTML page that looks correct in a browser preview renders with a white background in the actual installer.

**Workaround:** do not paint backgrounds on `html` or `body`. Either (a) design for the white default — let Installer.app's default show through and build the visual language around light-on-white — or (b) paint backgrounds on inner wrapper divs (though see Lockdown #2 for the color cascade complication). The light-theme approach chosen in PR #56 is the most reliable path: work with the default, not against it.

### Lockdown #2: CSS custom properties do not survive for `color` declarations

`var(--custom-property)` references are resolved correctly in a standalone WebKit context. Inside Installer.app, an injected stylesheet reset wipes the `color` property cascade after CSS variable resolution, reverting computed colors to the UA default (black on white, or black on whatever background is now showing). The result is that `color: var(--text)` is effectively ignored even when `--text` is defined in `:root`.

**Effect:** all text painted with CSS variables becomes invisible or reverts to an unintended color. The navy-on-navy bug observed after PR #55 was this lockdown: the page background was correctly dark (from a div background, bypassing Lockdown #1), but all text reverted to black and was invisible against `#0A1428`.

**Workaround:** use literal hex values for every `color` declaration in installer HTML, and append `!important` to all of them. No CSS custom properties should remain in any `color`, `background-color`, or `border-color` declaration. Defining variables in `:root` for development convenience is fine; they must be inlined to literal hex before committing to `installer/macos-pkg/resources/`.

### Lockdown #3: Sidebar PNG nav zone must be light-toned

Installer.app renders its step-list nav (the left column of installer steps) as an overlay on top of `background.png`. Active steps are painted in a bright blue-white tone. Inactive steps are painted in a dim, muted dark navy (approximately `#1A2744` based on visual inspection — the exact value is a system color and may vary with macOS version). The dim inactive-step color requires a light or medium-tone background to be readable. A dark-navy background produces zero contrast against inactive labels; they become invisible.

**Effect:** all inactive nav steps disappear into the sidebar artwork when the top portion of `background.png` is dark-toned. The active step may still be visible (bright on dark is legible) while all five other steps are not.

**Workaround:** reserve the top ~50% of `background.png` (approximately 555 px of a 1111 px tall canvas, which maps to the nav zone at typical sidebar widths) as a light or medium-tone zone. A light blue-grey gradient (`#F1F4F9` at the top transitioning to `#C8D2E0` at the midpoint) provides sufficient contrast for both the bright active and dim inactive step label styles. Place artwork (logo, wordmark, shield) in the lower half of the canvas where it does not interfere with the nav overlay. Feather the boundary between the light zone and the art zone over ~60 px to avoid a hard visual seam.

---

## Notarization submission ledger

All five submissions today were Accepted by Apple. The visual failures described above were rendering-environment issues in Installer.app's WebKit, not signing or notarization rejections. Apple's notary service validates code signing, hardened runtime, and binary hygiene — it has no visibility into how HTML content renders inside the installer UI.

| # | Submission ID | Build SHA | Visual verdict |
|---|---|---|---|
| 1 | `9f34a1ea-a5df-4d28-bbed-e4ca74170765` | `2f3bff5a8e28` | White right-pane background — Lockdown #1 exposed |
| 2 | `6b6596c0-67f8-44da-bb5d-9346e1e90f2c` | `5ba091d561fa` | Navy-on-navy text — Lockdown #2 exposed |
| 3 | `03f4a5c7-0798-4d06-9366-66fc5d1e6c18` | `e0e4bbe114f1` | Right pane good; sidebar nav invisible — Lockdown #3 exposed |
| 4 | `e549d551-f0be-492a-a95c-8caa43a9c238` | `fb5b7038988c` | Active nav step visible; inactive still invisible |
| 5 | `6813ec95-7abc-4768-bd06-fe4f1acdf777` | `0f849bd217cc` | All six nav steps readable — approved |

---

## Block D — USB stick refresh

The USB stick ("MG Install", ExFAT, never erased) entered the session holding the `978ff61126ea` build:

```
MiningGuardian-1.0.0-978ff61126ea.pkg
MiningGuardian-1.0.0-978ff61126ea.pkg.sha256
INSTALL.txt
```

After Build #5 was confirmed shippable, the stick was refreshed:

1. **Copy new pkg + sidecar.** The new files follow the same basename convention established in the prior session:
   ```zsh
   cp build/MiningGuardian-1.0.0-0f849bd217cc.pkg \
      "/Volumes/MG Install/MiningGuardian-1.0.0-0f849bd217cc.pkg"
   cp build/MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256 \
      "/Volumes/MG Install/MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256"
   ```
2. **Verify hash on-stick.** `shasum -a 256 -c` run against the sidecar from the stick's working directory — passed.
3. **Gatekeeper check on-stick copy.**
   ```zsh
   spctl -a -t install -vv \
     "/Volumes/MG Install/MiningGuardian-1.0.0-0f849bd217cc.pkg"
   ```
   Result: `accepted`, `source=Notarized Developer ID`. The staple survived the file copy.
4. **Rewrite `INSTALL.txt`.** Replaced the prior file with updated metadata:
   - Build SHA: `0f849bd217cc`
   - SHA-256: (the new checksum from the sidecar)
   - Notarization submission ID: `6813ec95-7abc-4768-bd06-fe4f1acdf777`
   - Install command: `sudo installer -pkg MiningGuardian-1.0.0-0f849bd217cc.pkg -target /`
5. **Remove old files.** Deleted `MiningGuardian-1.0.0-978ff61126ea.pkg`, `MiningGuardian-1.0.0-978ff61126ea.pkg.sha256`, and the prior `INSTALL.txt` from the stick.
6. **Eject.** `diskutil eject "/Volumes/MG Install"` — clean eject confirmed.

The stick was never erased or reformatted. ExFAT format is unchanged from the prior session. The only operations were file-level: copy new, verify, remove old, eject.

---

## Block E — GitHub Release

After the USB refresh, a new GitHub Release was created for `0f849bd217cc`.

**Tag creation:**

```zsh
git tag -a v1.0.0-0f849bd217cc \
  -m "MiningGuardian 1.0.0 build 0f849bd217cc — branded installer, light theme, sidebar gradient" \
  0f849bd217cc
git push origin v1.0.0-0f849bd217cc
```

**Draft release + asset upload:**

```zsh
gh release create v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  --title "MiningGuardian 1.0.0 — 0f849bd217cc (branded)" \
  --notes-file docs/RELEASE_NOTES_v1.0.0.md \
  --draft

gh release upload v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  build/MiningGuardian-1.0.0-0f849bd217cc.pkg \
  build/MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256
```

The sidecar filename on the first upload attempt used an absolute path, which caused GitHub to store the asset with the full path string as its display name. The sidecar was deleted from the draft and re-uploaded with the basename only:

```zsh
gh release delete-asset v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  "MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256"   # (by asset id via gh api)

gh release upload v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256
```

**Publish as Latest:**

```zsh
gh release edit v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  --draft=false \
  --latest
```

**Demote old release to Pre-release:**

```zsh
gh release edit v1.0.0-978ff61126ea \
  --repo robertfiesler-spec/Mining-Guardian \
  --prerelease \
  --latest=false
```

The old release `v1.0.0-978ff61126ea` was not deleted. Keeping it as Pre-release preserves the audit trail: any stakeholder who downloaded the unbranded build can compare checksums against that release and confirm what they have. Deletion would break that chain.

Both releases are now visible on the private repo's Releases page. The new one carries the Latest badge. The old one is labeled Pre-release with no Latest designation.

---

## Block G — Round-trip verify

After publishing, a fresh download was performed from the GitHub Release to confirm the CDN-delivered copy was intact and Gatekeeper-accepted:

```zsh
cd /tmp
mkdir mg_rtrip_0f849 && cd mg_rtrip_0f849

gh release download v1.0.0-0f849bd217cc \
  --repo robertfiesler-spec/Mining-Guardian \
  --pattern "*.pkg" --pattern "*.sha256"

shasum -a 256 -c MiningGuardian-1.0.0-0f849bd217cc.pkg.sha256
# MiningGuardian-1.0.0-0f849bd217cc.pkg: OK

spctl -a -t install -vv MiningGuardian-1.0.0-0f849bd217cc.pkg
# MiningGuardian-1.0.0-0f849bd217cc.pkg: accepted
# source=Notarized Developer ID
```

Both checks passed. The staple survived GitHub's CDN delivery, consistent with the prior session's observation that `xcrun stapler staple` embeds the notarization ticket inside the `.pkg` file itself. `xattr` on the downloaded file showed `com.apple.provenance` (macOS Sequoia's replacement for `com.apple.quarantine`), confirming macOS treated the file as a genuine internet download and still trusted it through Gatekeeper.

The round-trip verify is the definitive shippability gate. A passing result here means the file a customer downloads from the private GitHub Release link will install without a Gatekeeper warning on any Mac that trusts Apple's notarization chain.

---

## State of repo at end of session

**`main` tip:** `0f849bd217cc` (PR #58).

All five PRs from today (#54–#58) are merged. Their source branches are safe to delete — all work is in `main` with no uncommitted or unpushed state.

| Item | State |
|---|---|
| `main` tip | `0f849bd217cc` |
| PRs #54–#58 | Merged, branches deletable |
| Tag `v1.0.0-0f849bd217cc` | Exists, pushed to origin |
| GitHub Release `v1.0.0-0f849bd217cc` | Published, Latest |
| GitHub Release `v1.0.0-978ff61126ea` | Pre-release, kept for audit trail |
| USB stick "MG Install" | `0f849bd217cc` build, hash-verified, Gatekeeper-accepted |
| `docs/RUNBOOK_PKG_REBUILD.md` | Updated with all three Installer.app lockdowns |

GitHub Release and USB stick are in sync: both carry `MiningGuardian-1.0.0-0f849bd217cc.pkg` with matching checksums.

The three stale experiment branches (`feature/fast-cohort-analysis`, `feature/intelligence-catalog`, `pre-prod-audit-2026-04-25`) remain diverged but are non-blocking, same status as prior session.

---

## What's still TODO

The operator's standing framework for outstanding work, unchanged in structure from prior sessions:

🔴 **Bucket 1 — critical / blocking**

- D-14 PR 5/5 — final piece of the data pipeline, gated on Mac Mini physical install
- 124 missing `raw_json` rows from the 2026-04-27 import — backfill needed before Mini goes live
- Runtime invariant assertion in `run_full_import.py` — guard against silent partial imports

🟡 **Bucket 2 — important but non-blocking**

- CI lint job for typo regression
- B-7 migrations `002_layer2` + staging not committed
- VPS GitHub PAT rotation (the `agp_019dd5a1-…` token is expired; direct `git push` is broken; the `gh api` Git Data path is the current workaround)
- Delete `scripts/cleanup_ams_logs.py`

🟢 **Bucket 3 — .pkg branding: DONE today**

- Five PRs, five `make pkg` cycles, three Installer.app lockdowns documented
- Build `0f849bd217cc` is notarized, stapled, branded, and shippable
- USB and GitHub Release in sync

🟢 **Bucket 4 — per-customer hardware ops**

- Power cycle miner 53476
- Inspect hashboards on 53494 and 53521
- 53482 underperforming — root cause TBD
- HVAC re-enable + remove `hvac_work_apr2026` hardware fact from the catalog

---

## Closing note

Five PRs is a lot of iteration for what is, structurally, a CSS and PNG problem. The reason it took five is that the constraint surface was invisible until the real installer rendered the real HTML on real macOS. The Playwright composite mockup was accurate for everything except the three things that Installer.app's WebKit environment overrides: the `html`/`body` background layer, the CSS custom-property color cascade, and the sidebar nav text contrast requirements. None of those constraints are documented in Apple's installer toolchain references. They had to be found by running `make pkg` and looking at the result.

The operator's framing throughout — "I would rather be late and perfect than early and wrong" and "always comprehensive, and always over document" — describes exactly why five build cycles is the right answer rather than a failing. Each cycle produced a complete notarized artifact with a stable SHA, a clear diagnosis, and a documented fix. The three lockdowns are now in `docs/RUNBOOK_PKG_REBUILD.md`. A future maintainer who needs to restyle `welcome.html` or replace `background.png` will find the constraints written down before they hit them.

The branded `.pkg` is shippable to customers. The USB stick is ready. The GitHub Release is live. The unbranded build `978ff61126ea` is preserved as Pre-release for audit continuity. Today's work was about visual polish, but the discipline that produced it — narrow PRs, one problem per cycle, document the diagnosis before writing the fix — is the same discipline the rest of the codebase is built on. The lessons learned from Lockdowns #1, #2, and #3 are now baked into the runbook and will not need to be relearned.

*— end of 2026-04-29 session*
