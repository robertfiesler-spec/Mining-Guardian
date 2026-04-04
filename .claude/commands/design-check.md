---
suggest_when:
  - signal: file_extension
    value: ".tsx"
    min_edits: 3
    cooldown: 25
    message: "Edited React components — `/design-check` validates design system compliance"
---
# /design-check - Design System Compliance

Validate UI code against the design system rules in `rules/design-system/`.

## Your Task

Audit the specified files for design system violations. Check foundations (color, typography, spacing), components (buttons, forms), and accessibility requirements.

$ARGUMENTS

## Step 1: Load Design System Rules

Read and internalize all design system rules:

```
@rules/design-system/_index.md      # Core principles
@rules/design-system/foundations.md # Color, typography, spacing
@rules/design-system/components.md  # Buttons, forms, copywriting
@rules/design-system/accessibility.md # WCAG requirements
```

## Step 2: Determine Scope

**If argument provided**: Check that file or directory
**If `--staged`**: Check staged files only
**If no argument**: Check `app/`, `components/`, `src/`

Filter to UI files:
```bash
find [path] -name "*.tsx" -o -name "*.jsx" -o -name "*.css" | head -50
```

## Step 3: Check Each Category

### Foundations Checks

| Rule | Pattern to Find | Violation |
|------|-----------------|-----------|
| Body text size | `text-sm`, `text-xs` on body content | Body text < 18px |
| Line height | `leading-tight`, `leading-none` on paragraphs | Line height < 1.5 for body |
| Pure black text | `text-black`, `#000000`, `rgb(0,0,0)` | Avoid pure black |
| Pure black bg | `bg-black` without opacity | Avoid pure black |
| Light grey text | `text-gray-300`, `text-gray-400` on content | Low contrast text |
| Magic colors | Hardcoded hex/rgb not in design tokens | Use design tokens |
| Inconsistent spacing | Mixed spacing values in same component | Use spacing scale |
| Line length | Prose content without `max-w-prose` or width constraint | Lines > 75 chars |

### Component Checks

| Rule | Pattern to Find | Violation |
|------|-----------------|-----------|
| Multiple primary buttons | Multiple `variant="primary"` or primary-styled buttons in same view | One primary per view |
| Right-aligned buttons | `justify-end`, `text-right` on button containers | Left-align buttons |
| Disabled buttons | `disabled` prop without explanation | Avoid disabled states |
| Placeholder as label | `<input placeholder="...">` without `<label>` | Never use placeholder as label |
| Submit button text | `>Submit<`, `>Send<` generic text | Describe the action |
| Touch target size | Interactive elements < 44px | Min 44×44px targets |
| Form field hints | Hints after inputs instead of before | Display hints above fields |

### Accessibility Checks

| Rule | Pattern to Find | Violation |
|------|-----------------|-----------|
| Contrast ratio | Light text on light bg, dark on dark | 4.5:1 for text, 3:1 for UI |
| Color-only meaning | Status/state indicated only by color | Add icon, text, or pattern |
| Missing focus state | `outline-none` without replacement | Visible focus required |
| Touch target | Clickable elements < 44×44px | Min 44×44px |
| Icon-only buttons | `<button><Icon/></button>` without label | Add aria-label |
| Form labels | `<input>` without associated `<label>` | Label all inputs |
| Heading hierarchy | h1 followed by h3 (skipping h2) | Sequential headings |
| Link text | `>click here<`, `>learn more<` generic | Descriptive link text |
| Motion | Animations without `prefers-reduced-motion` | Respect motion preference |

### Copywriting Checks

| Rule | Pattern to Find | Violation |
|------|-----------------|-----------|
| Title Case | `Button Text Like This` | Use sentence case |
| "Click here" links | `>click here<`, `>here<` | Descriptive link text |
| "My" in labels | `>My Account<`, `>My Settings<` | Use "Your" or nothing |
| Full stops in buttons | `>Save.<`, `>Submit.<` | No periods in buttons |
| Written numbers | `>five items<`, `>three options<` | Use numerals (5, 3) |

## Step 4: Report Findings

```
══════════════════════════════════════════════════════════════
 /design-check - Design System Compliance
══════════════════════════════════════════════════════════════

Files scanned: [N]
Violations: [X] foundations, [Y] components, [Z] accessibility

──────────────────────────────────────────────────────────────
 FOUNDATIONS ([N] violations)
──────────────────────────────────────────────────────────────

[TYPOGRAPHY] path/to/file.tsx:42
  Body text below minimum size

  → <p className="text-sm text-gray-600">...</p>

  Rule: Body text must be 18px minimum
  Fix: Use text-base (16px) or text-lg (18px) for body content

  → <p className="text-lg text-gray-600">...</p>

[COLOR] path/to/file.tsx:67
  Pure black text

  → <h1 className="text-black">Title</h1>

  Rule: Avoid pure black (#000) - causes eye strain
  Fix: Use gray-900 or a dark shade from your palette

  → <h1 className="text-gray-900">Title</h1>

──────────────────────────────────────────────────────────────
 COMPONENTS ([N] violations)
──────────────────────────────────────────────────────────────

[BUTTON] path/to/file.tsx:89
  Multiple primary buttons in same view

  → <Button variant="primary">Save</Button>
    ...
    <Button variant="primary">Continue</Button>

  Rule: Use a single primary button per view
  Fix: Make secondary actions use secondary/tertiary variants

  → <Button variant="secondary">Save</Button>
    <Button variant="primary">Continue</Button>

[FORM] path/to/file.tsx:112
  Placeholder used as label

  → <input placeholder="Email address" />

  Rule: Never use placeholder text as labels
  Fix: Add visible label above input

  → <label htmlFor="email">Email address</label>
    <input id="email" placeholder="you@example.com" />

──────────────────────────────────────────────────────────────
 ACCESSIBILITY ([N] violations)
──────────────────────────────────────────────────────────────

[A11Y] path/to/file.tsx:134
  Focus outline removed without replacement

  → <button className="outline-none">Submit</button>

  Rule: All interactive elements need visible focus indicators
  Fix: Add focus-visible ring

  → <button className="focus-visible:ring-2 focus-visible:ring-offset-2">Submit</button>

══════════════════════════════════════════════════════════════
 SUMMARY
══════════════════════════════════════════════════════════════

Compliance Score: [NN]/100

Category Breakdown:
  Foundations:   [N] violations
  Components:    [N] violations
  Accessibility: [N] violations
  Copywriting:   [N] violations

[If violations exist:]
Run `/design-check --fix` to auto-fix [N] violations.

[If no violations:]
✓ All files comply with design system rules.
```

## Step 5: Offer Auto-Fix

After reporting, if fixable violations exist:

> **Auto-fixable violations: [N]**
>
> I can automatically fix:
> - [N] text-black → text-gray-900
> - [N] outline-none → focus-visible:ring-2
> - [N] text-sm → text-base on body content
>
> Would you like me to apply these fixes?

**Auto-fixable patterns:**

| Violation | Auto-fix |
|-----------|----------|
| `text-black` | → `text-gray-900` |
| `bg-black` | → `bg-gray-950` |
| `outline-none` alone | → `focus-visible:ring-2 focus-visible:ring-offset-2` |
| `text-sm` on body | → `text-base` |
| `leading-tight` on body | → `leading-relaxed` |

## Arguments

| Argument | Description |
|----------|-------------|
| `[path]` | File or directory to check |
| `--staged` | Only check staged files |
| `--fix` | Auto-fix violations without prompting |
| `--category <name>` | Check only: foundations, components, accessibility, copywriting |
| `--strict` | Fail on any violation (for CI) |
| `--json` | Output as JSON |

## Examples

```bash
# Check specific file
/design-check components/Button.tsx

# Check all components
/design-check components/

# Quick check before commit
/design-check --staged

# Auto-fix all fixable issues
/design-check --fix

# Check only typography/spacing
/design-check --category foundations

# CI mode - exit 1 on violations
/design-check --strict
```

## Related

- `/rams` - Accessibility & visual design audit (broader scope)
- `/review` - Full code review
- `/pre-pr-check` - Pre-PR validation
- `@rules/design-system/` - The rules being enforced
- `ui-design` skill - Implementation patterns

## Suggested Next

| If... | Run |
|-------|-----|
| Violations found, need to fix manually | `/iterate` — work through fixes systematically |
| Want a broader accessibility audit | `/rams` — accessibility and visual design audit |
| Fixes applied, ready to commit | `/create-commit` — generate a conventional commit |
