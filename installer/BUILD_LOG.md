# Installer Build Log

Daily record of what was built, decisions made, and any deviations from `INSTALLER_PLAN.md`.

---

## 2026-04-19 (Sunday) — Planning

- Built `INSTALLER_PLAN.md` — 900-line master blueprint for the 11-screen Rich wizard
- Audited existing repo code (setup.sh, deploy/*.service, config_template.json, .env.example)
- Resolved 6 open questions from DEPLOYMENT.md
- Defined sprint plan (Week 1: screens + services, Week 2: Grafana + install + polish)
- **Deferred to next session:** actual code writing (Bobby was flying)

## 2026-04-21 (Tuesday) — Brand System + Screen 1 Mockup

### Built
- `branding/` folder — 19 curated logos organized into:
  - `logos/primary/` (6 hero logos)
  - `logos/wordmark/` (3 wordmark variants)
  - `logos/icons/` (3 app icons)
  - `logos/badges/` (3 badges)
  - `artwork/` (spectrum hero + gold BTC pieces)
  - `raw/` (original zip preserved)
- `branding/BRANDING.md` — complete brand system doc covering:
  - Color palette (extracted from hero artwork via PIL)
  - Typography (Chakra Petch / Space Grotesk / Inter / JetBrains Mono)
  - Voice & tone guidelines
  - Logo usage rules (which logo when, clearspace, minimum sizes)
  - Rich terminal color palette for the wizard
  - Asset delivery roadmap
- `installer/SCREEN_APPROVAL_LOG.md` — workflow for per-screen approval
- `installer/BUILD_LOG.md` — this file
- `installer/previews/screen1_welcome.svg` + `.png` — Screen 1 mockup rendered with brand colors

### Decisions Made
- **Comic Sans is not the brand**: Bobby likes it, but the logos scream industrial/futuristic. We use rounded, friendly copy tone instead — Comic Sans would clash with the hero aesthetic.
- **Dark only**: confirmed with Bobby. Space-black background (`#0A0E1A`) for every screen.
- **Orange is the primary accent**: Bitcoin official orange (`#F7931A`). Electric blue (`#2BB4FF`) is secondary for info/data elements.
- **Double-line corners for hero Welcome, rounded for step screens**: gives the welcome a "big moment" feel.
- **Unicode rendering caveat**: SVG→PNG via cairosvg doesn't render box-drawing chars or emoji cleanly, but real terminals on Mac will render them correctly. Real testing happens on Bobby's Mac.

### Tests Run
- `screen1_mockup.py` — renders successfully in Rich with truecolor support
- PIL color extraction confirmed brand palette

### Tomorrow's Plan
- Get Bobby's approval on Screen 1 direction
- If approved: build `installer/lib/state.py`, `installer/wizard.py` skeleton, Screen 1 real code, Screen 2 (Pre-Flight)
- Bobby tests on his Mac

### Deferrals / Open Items
- SVG versions of logos (will build later when we need web scaling)
- Monochrome menu bar icon (defer until Mac menu bar integration phase)
- Favicon set (defer until dashboard work)

---
