---
suggest_when:
  - signal: file_extension
    value: ".tsx"
    min_edits: 3
    cooldown: 25
    message: "React component edits — `/rams` for accessibility + visual design audit"
---

# /rams - Accessibility & Visual Design Audit

A Claude-powered design engineer that reviews code for accessibility and visual design issues, then offers fixes.

Inspired by the methodology of [rams.ai](https://rams.ai). This command does NOT require installing the rams.ai CLI - Claude performs the audit directly using the same principles and severity classifications.

## Your Task

Audit the specified files (or recent changes) for accessibility and visual design issues. Report findings by severity with line numbers, code snippets, and fix suggestions.

$ARGUMENTS

## Step 1: Determine Scope

**If argument provided**: Audit that file or directory
**If `--staged` or `--changes`**: Audit staged/changed files only
**If no argument**: Ask user or default to `app/`, `components/`, `src/`

Filter to relevant files:
```bash
# Find React component files
find [path] -name "*.tsx" -o -name "*.jsx" | head -50
```

## Step 2: Load Review Criteria

Load both skills for comprehensive coverage:
- `accessibility` skill - WCAG 2.1 patterns
- `ui-design` skill - Vercel Web Interface Guidelines

## Step 3: Audit Each File

For each file, check for issues in order of severity:

### Critical Issues (Must Fix)

**Accessibility:**
| Issue | Pattern to Find | WCAG |
|-------|-----------------|------|
| Missing alt text | `<img` without `alt` | 1.1.1 |
| Icon button no label | `<button>` with only icon child, no `aria-label` | 4.1.2 |
| Form input no label | `<input` without associated `<label` or `aria-label` | 1.3.1 |
| Non-semantic click | `<div onClick` or `<span onClick` without `role` + `tabIndex` | 2.1.1 |
| Link without href | `<a onClick` without `href` | 2.1.1 |

**Visual Design:**
| Issue | Pattern to Find |
|-------|-----------------|
| Focus outline removed | `outline-none` or `outline: none` without replacement |
| Color-only status | Status/error indicated only by color class |

### Serious Issues (Should Fix)

**Accessibility:**
| Issue | Pattern to Find | WCAG |
|-------|-----------------|------|
| Touch target too small | Interactive element < 44px on mobile | 2.5.5 |
| Missing keyboard handler | `onClick` without `onKeyDown` on non-button | 2.1.1 |
| Positive tabIndex | `tabIndex={[1-9]}` | 2.4.3 |
| autoFocus misuse | `autoFocus` on non-modal elements | 2.4.3 |

**Visual Design:**
| Issue | Pattern to Find |
|-------|-----------------|
| `transition: all` | Animates unintended properties |
| Missing loading state | Form submit without loading indicator |
| No reduced motion | Animation without `prefers-reduced-motion` check |

### Moderate Issues (Consider Fixing)

**Accessibility:**
| Issue | Pattern to Find | WCAG |
|-------|-----------------|------|
| Skipped heading | h1 followed by h3 (skipping h2) | 1.3.1 |
| Generic link text | `>click here<` or `>learn more<` without context | 2.4.4 |
| Missing lang attribute | `<html` without `lang` | 3.1.1 |

**Visual Design:**
| Issue | Pattern to Find |
|-------|-----------------|
| Inconsistent spacing | Mixed spacing values (p-3, p-4, p-5 in same component) |
| Magic color values | Hardcoded hex/rgb instead of design tokens |
| Nested border radius | Child radius > parent radius |
| Missing dark mode | `bg-white` or `text-black` without dark: variant |

## Step 4: Report Findings

Use this format:

```
══════════════════════════════════════════════════════════════
 /rams - Accessibility & Visual Design Audit
══════════════════════════════════════════════════════════════

Files scanned: [N]
Issues found: [X] critical, [Y] serious, [Z] moderate

──────────────────────────────────────────────────────────────
 CRITICAL ([N] issues)
──────────────────────────────────────────────────────────────

[A11Y] path/to/file.tsx:42
  Missing alt text on image

  → <img src={user.avatar} className="rounded-full" />

  Fix: Add descriptive alt text
  → <img src={user.avatar} alt={`${user.name}'s avatar`} className="rounded-full" />

  WCAG: 1.1.1 Non-text Content

[A11Y] path/to/file.tsx:67
  Icon button without accessible name

  → <button onClick={onClose}><XIcon /></button>

  Fix: Add aria-label
  → <button onClick={onClose} aria-label="Close dialog"><XIcon aria-hidden="true" /></button>

  WCAG: 4.1.2 Name, Role, Value

──────────────────────────────────────────────────────────────
 SERIOUS ([N] issues)
──────────────────────────────────────────────────────────────

[DESIGN] path/to/file.tsx:89
  Focus outline removed without replacement

  → <button className="outline-none bg-blue-500">Submit</button>

  Fix: Add visible focus indicator
  → <button className="focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 bg-blue-500">Submit</button>

──────────────────────────────────────────────────────────────
 MODERATE ([N] issues)
──────────────────────────────────────────────────────────────

[A11Y] path/to/file.tsx:15
  Heading hierarchy skipped (h1 → h3)

  → <h1>Dashboard</h1>
    ...
    <h3>Recent Activity</h3>

  Fix: Use sequential heading levels
  → <h2>Recent Activity</h2>

  WCAG: 1.3.1 Info and Relationships

══════════════════════════════════════════════════════════════
 SUMMARY
══════════════════════════════════════════════════════════════

Category Breakdown:
  Accessibility: [N] issues ([X] critical, [Y] serious, [Z] moderate)
  Visual Design: [N] issues ([X] critical, [Y] serious, [Z] moderate)

Score: [NN]/100

[If critical issues exist:]
⚠️  Critical issues must be fixed before merging.

[If no critical issues:]
✓  No critical issues. Consider fixing serious issues.
```

## Step 5: Offer Auto-Fix

After reporting, if fixable issues exist:

> **Auto-fixable issues found: [N]**
>
> I can automatically fix:
> - [N] missing alt="" on decorative images
> - [N] aria-label additions to icon buttons
> - [N] focus ring replacements for outline-none
>
> Would you like me to apply these fixes?

**Auto-fixable patterns:**
| Issue | Auto-fix |
|-------|----------|
| Decorative image no alt | Add `alt=""` |
| Icon button no label | Add `aria-label="[inferred from icon name]"` |
| outline-none alone | Replace with `focus-visible:ring-2 focus-visible:ring-offset-2` |
| Missing aria-hidden on icons | Add `aria-hidden="true"` to icon inside labeled button |

## Quick Mode (`--quick`)

When `--quick` is passed:
1. Only check for **Critical** issues
2. Skip moderate/stylistic checks
3. Faster for pre-commit/CI use

Output format for quick mode:
```
/rams --quick: [N] critical issues found

[If issues:]
CRITICAL:
  path/file.tsx:42 - Missing alt text on image
  path/file.tsx:67 - Icon button without accessible name

Run `/rams` for full audit.

[If no issues:]
✓ No critical accessibility or design issues found.
```

## Arguments

| Argument | Description |
|----------|-------------|
| `[path]` | File or directory to audit |
| `--quick` | Critical issues only (fast) |
| `--staged` | Only audit staged files |
| `--changes` | Only audit uncommitted changes |
| `--fix` | Auto-fix without prompting |
| `--json` | Output as JSON (for tooling) |

## Examples

```bash
# Audit specific file
/rams components/Button.tsx

# Audit all components
/rams components/

# Quick check before commit
/rams --quick --staged

# Auto-fix all fixable issues
/rams --fix

# CI-friendly output
/rams --quick --json
```

## Related

- `/review` - Full code review (includes /rams checks)
- `/pre-pr-check` - Pre-PR validation (includes /rams --quick)
- `accessibility` skill - Detailed WCAG patterns with code examples
- `ui-design` skill - Visual design guidelines with code examples
- `@rules/design-system/` - Always-apply UI/UX design rules:
  - `accessibility.md` - WCAG requirements checklist
  - `foundations.md` - Color, typography, spacing scales
  - `components.md` - Button, form, copywriting guidelines

## Suggested Next

- `/review` — full code review alongside accessibility findings
- `/design-check` — design system compliance check
- `/create-commit` — commit after applying accessibility fixes
