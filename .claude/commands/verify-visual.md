---
suggest_when:
  - signal: file_extension
    value: ".tsx"
    min_edits: 3
    cooldown: 30
    message: "UI components changed — `/verify-visual` to catch rendering issues with screenshots"
  - signal: file_extension
    value: ".css"
    min_edits: 2
    cooldown: 30
    message: "Styles changed — `/verify-visual` for visual regression check"
---

# Verify Visual

Browser-based visual verification of rendered UI using agent-browser.

## Your Task

Capture and analyze visual state of a URL, including screenshots and accessibility snapshots. Report findings and optionally compare against baselines.

$ARGUMENTS

## Prerequisites

- **agent-browser**: Will be auto-installed if missing
- **Dev server**: Must be running at target URL (script will warn if not)

## Step 1: Parse Arguments

The command accepts these arguments:

| Argument            | Example                       | Description                    |
| ------------------- | ----------------------------- | ------------------------------ |
| `<url>`             | `http://localhost:3000/login` | URL to verify (required)       |
| `--compare`         |                               | Compare against baseline       |
| `--update-baseline` |                               | Accept current as new baseline |
| `--full`            |                               | Full-page screenshot           |
| `--strict`          |                               | Fail on visual regression      |
| `--route <name>`    | `--route login-page`          | Custom route name              |

If no URL provided, prompt user for one.

## Step 2: Run Browser Verification

Execute the browser-verify.sh script:

```bash
# Basic capture
.claude/scripts/browser-verify.sh "$URL"

# With baseline comparison
.claude/scripts/browser-verify.sh --compare "$URL"

# Full page with custom route name
.claude/scripts/browser-verify.sh --full --route "$ROUTE" "$URL"

# Update baseline
.claude/scripts/browser-verify.sh --update-baseline "$URL"

# Strict mode (fail on regression)
.claude/scripts/browser-verify.sh --compare --strict "$URL"
```

## Step 3: Read Captured Artifacts

After script runs, read the captured files:

1. **Screenshot**: `.claude/visual/current/{route}-{timestamp}.png`
2. **Accessibility Snapshot**: `.claude/visual/snapshots/{route}-{timestamp}.json`
3. **Diff Image** (if comparing): `.claude/visual/diffs/{route}-diff-{timestamp}.png`

Use the Read tool to view the screenshot image and analyze it visually.

## Step 4: Analyze Screenshot

Examine the captured screenshot for:

**Layout Issues**

- Elements overflowing or misaligned
- Unexpected gaps or overlapping content
- Broken responsive behavior
- Missing or broken images

**Styling Issues**

- Incorrect colors or contrast
- Font rendering problems
- Missing visual states (hover, focus, active)
- Icon/image sizing issues

**Content Issues**

- Placeholder or test data visible
- Truncated text
- Missing or broken UI elements

## Step 5: Analyze Accessibility Snapshot

Parse the JSON snapshot and check for:

**Semantic Structure**

- Heading hierarchy (h1 should be unique, proper nesting)
- Landmark regions (main, nav, header, footer)
- List structures for grouped items

**Interactive Elements**

- Buttons and links have accessible names
- Form inputs have associated labels
- ARIA roles are appropriate

**Common Issues**

```json
// BAD: Empty name
{ "role": "button", "name": "" }

// BAD: Unlabeled input
{ "role": "textbox", "name": "" }

// BAD: Generic image
{ "role": "img", "name": "" }
```

## Step 6: Report Results

### Success Report

```markdown
## Visual Verification: PASS

**URL**: http://localhost:3000/login
**Route**: login
**Captured**: 2024-01-15 14:30:52

### Screenshot Analysis

No visual issues detected.

### Accessibility Snapshot

| Metric    | Count            |
| --------- | ---------------- |
| Headings  | h1:1, h2:2, h3:0 |
| Landmarks | main:1, nav:1    |
| Forms     | 1 form, 3 inputs |
| Buttons   | 2 (all labeled)  |
| Links     | 5 (all labeled)  |

**Status**: All elements have accessible names.

### Baseline Comparison

[UNCHANGED | NO_BASELINE | N/A]

### Artifacts

- Screenshot: `.claude/visual/current/login-20240115-143052.png`
- Snapshot: `.claude/visual/snapshots/login-20240115-143052.json`

---

Visual verification complete. No issues found.
```

### Report with Issues

```markdown
## Visual Verification: WARN

**URL**: http://localhost:3000/login
**Route**: login
**Captured**: 2024-01-15 14:30:52

### Screenshot Analysis

**Issues Found (2)**:

1. **Layout**: Submit button extends beyond form container
   - Location: Bottom-right of login form
   - Recommendation: Add overflow handling or adjust button width

2. **Content**: "TODO: Add forgot password link" visible
   - Location: Below password field
   - Recommendation: Remove placeholder text or implement feature

### Accessibility Snapshot

| Metric    | Count            |
| --------- | ---------------- |
| Headings  | h1:1, h2:2, h3:0 |
| Landmarks | main:1, nav:0    |
| Forms     | 1 form, 3 inputs |
| Buttons   | 2 (1 unlabeled)  |
| Links     | 3 (all labeled)  |

**Issues Found (2)**:

1. **Missing nav landmark**: Page has navigation but no `<nav>` element
   - Recommendation: Wrap navigation in `<nav>` element

2. **Unlabeled button**: Icon button lacks accessible name
   - Element: `{ "role": "button", "name": "" }`
   - Recommendation: Add `aria-label` to icon button

### Baseline Comparison

**Status**: CHANGED (1,247 pixels differ)
**Diff**: `.claude/visual/diffs/login-diff-20240115-143052.png`

Visual regression detected. Review the diff image to determine if intentional.

### Artifacts

- Screenshot: `.claude/visual/current/login-20240115-143052.png`
- Snapshot: `.claude/visual/snapshots/login-20240115-143052.json`
- Diff: `.claude/visual/diffs/login-diff-20240115-143052.png`

---

Visual verification complete with warnings. Review findings above.
```

## Error Handling

| Scenario                    | Behavior                                  |
| --------------------------- | ----------------------------------------- |
| agent-browser not installed | Attempt auto-install, warn if fails       |
| URL not accessible          | Report error, suggest starting dev server |
| Screenshot fails            | Report error with details                 |
| No baseline exists          | Inform user, suggest `--update-baseline`  |

## Agent Loading

This command automatically loads the `visual-verifier` agent for analysis assistance.

## Related Commands

| Command            | Use                                     |
| ------------------ | --------------------------------------- |
| `/verify`          | Code verification (lint, types, tests)  |
| `/verify --visual` | Code verification + visual verification |
| `/iterate`         | Runs visual verification for UI stories |
| `/rams`            | Full accessibility + design audit       |

## Suggested Next

- `/rams` — full accessibility + design audit after visual review
- `/review` — code review incorporating visual findings
- `/create-commit` — commit after applying visual fixes
