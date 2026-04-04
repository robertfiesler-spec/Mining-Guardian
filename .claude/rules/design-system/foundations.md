# Foundations: Color, Typography & Spacing

## Color

### Palette Structure

Use a monochromatic palette with defined purposes:

| Token | Purpose |
|-------|---------|
| `primary` | Actions (buttons, links) |
| `text-primary` | Heading text (darkest) |
| `text-secondary` | Secondary text (dark) |
| `border-strong` | Dark borders (medium) |
| `border-subtle` | Light borders (light) |
| `surface` | Backgrounds (lightest) |

### System Colors

| Color | Status | Usage |
|-------|--------|-------|
| Red | Error | Failures requiring urgent attention |
| Amber | Warning | Caution, risky actions |
| Green | Success | Completed actions, positive messages |

### Color Rules

- ❌ Avoid pure black (`#000000`) - causes eye strain
- ❌ Don't use brand color on non-interactive elements
- ✅ Use 1 brand color for interactive elements
- ✅ Use black and white as foundations; add color purposefully
- For contrast ratios and color-as-meaning rules, see `accessibility.md`

---

## Typography

### Font Selection

- Use a single sans-serif typeface for most interfaces
- Optionally add a second typeface for headings only
- Use only regular (400) and bold (700) weights

### Type Scale (1.250 ratio)

| Token | Size | Weight | Usage |
|-------|------|--------|-------|
| `h1` | 44px | Bold | Page titles |
| `h2` | 36px | Bold | Section headers |
| `h3` | 28px | Bold | Subsections |
| `h4` | 22px | Bold | Card headers |
| `body` | 18px | Regular | Body text |
| `small` | 15px | Regular | Captions, hints |

### Typography Rules

- ✅ Make long body text 18px minimum
- ✅ Use at least 1.5 line-height for body text
- ✅ Decrease line-height as font size increases
- ✅ Keep line length 45-75 characters
- ✅ Left-align text for readability
- ✅ Decrease letter-spacing for large text (headings)
- ❌ Avoid light grey text
- ❌ Avoid pure black text

---

## Spacing

### Spacing Scale

| Token | Value | Usage |
|-------|-------|-------|
| `xs` | 8px | Tight gaps, icon padding |
| `sm` | 16px | Related elements |
| `md` | 24px | Default component spacing |
| `lg` | 32px | Section gaps |
| `xl` | 48px | Major sections |
| `2xl` | 80px | Page sections |

### Shadow Scale

| Token | Usage |
|-------|-------|
| `shadow-sm` | Subtle elevation, hover states |
| `shadow-md` | Cards, dropdowns |
| `shadow-lg` | Modals, overlays |

### Border Radius Scale

| Token | Value | Usage |
|-------|-------|-------|
| `rounded-sm` | 8px | Small elements (badges, chips) |
| `rounded-md` | 16px | Cards, inputs |
| `rounded-lg` | 32px | Large containers, hero sections |

### Layout Rules

- ✅ Group related elements using proximity
- ✅ Use depth (shadows) to create hierarchy
- ✅ Align to a 12-column grid for main layout
- ✅ Space elements based on how closely related they are
- ✅ Be generous with white space
- ✅ Keep related actions close (Fitts's Law)
- ✅ Ensure important content is visible above the fold

---

## Machine Enforcement

These rules are enforced automatically by `design-lint.sh`. Violations block commits and PRs.

### Enforced Spacing Rules

- **NEVER** use raw numeric Tailwind spacing utilities: `mt-3`, `px-4`, `gap-2`, `p-8`, etc.
- **ALWAYS** use semantic spacing tokens: `mt-xs`, `px-sm`, `gap-md`, `p-lg`, etc.
- Exception marker: `{/* ds-exception: <reason> */}` on the preceding line

### Enforced Color Rules

- **NEVER** use arbitrary color values: `text-[#xxx]`, `bg-[#xxx]`, `border-[#xxx]`
- **NEVER** use raw hex/rgb/hsl in inline styles
- **NEVER** use `text-black` or `bg-black` (pure black)
- **ALWAYS** use design token color classes from the palette

### Enforced Typography Rules

- **NEVER** use arbitrary font sizes: `text-[44px]`, `text-[15px]`
- **ALWAYS** use typography scale tokens: `text-h1`, `text-h2`, `text-body`, `text-small`
- **NEVER** use `leading-none` or `leading-tight` on body text

### Enforced Accessibility Rules (from `accessibility.md`)

- **NEVER** use `outline-none` or `outline: none` without a `focus-visible` replacement
- **ALWAYS** add `alt` attribute to `<img>` elements
- **ALWAYS** add `aria-label` to icon-only buttons

### Exception Format

```tsx
{/* ds-exception: <short reason> */}
<div className="mt-3">...</div>
```

Exceptions are tracked and reported. Stale exceptions should be removed during periodic review.

---

For spacing application patterns (forms, containers, page layout), see `spacing-patterns.md`.