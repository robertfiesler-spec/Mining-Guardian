# Installer Screen Approval Log

Every installer screen must be approved by Bobby before we move to the next one.
This log tracks every screen, every revision, every approval.

---

## Approval Workflow

1. Computer builds the screen and commits to `installer-build`
2. Computer renders a visual preview (terminal screenshot / SVG export)
3. Bobby reviews — approves or requests changes
4. If changes requested: revise, re-render, re-review
5. When approved: log it here and move to next screen

---

## Screens

### Screen 0 — Branding System
- **Status:** Pending Bobby's approval
- **Built:** 2026-04-21
- **Deliverables:**
  - `branding/` folder with curated logos (19 primary assets)
  - `branding/BRANDING.md` — complete brand system doc
  - Color palette extracted from hero artwork
  - Typography, voice, tone defined
- **Reviewer notes:** _awaiting_
- **Approval:** _pending_

### Screen 1 — Welcome
- **Status:** Mockup only, awaiting approval of direction
- **Built:** 2026-04-21 (mockup)
- **Preview:** `installer/previews/screen1_welcome.svg` / `.png`
- **Reviewer notes:** _awaiting_
- **Approval:** _pending_

### Screen 2 — Pre-Flight Check
- **Status:** Not started
- **Notes:** Will build after Screen 1 approval

### Screen 3 — Site Configuration
- **Status:** Not started

### Screen 4 — AMS Connection
- **Status:** Not started

### Screen 5 — Fleet Discovery
- **Status:** Not started

### Screen 6 — Slack Setup
- **Status:** Not started

### Screen 7 — Local LLM Setup
- **Status:** Not started

### Screen 8 — HVAC (Optional)
- **Status:** Not started

### Screen 9 — Review
- **Status:** Not started

### Screen 10 — Installation
- **Status:** Not started

### Screen 11 — Verification
- **Status:** Not started
