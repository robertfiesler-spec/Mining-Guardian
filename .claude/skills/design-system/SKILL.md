---
name: design-system
description: Design system enforcement router. Activates on ANY UI task to ensure design docs are consulted before implementation. Routes through canonical rules, enforces token usage, and validates compliance. Use when building, modifying, or reviewing UI components.
---

# Design System Skill

Deterministic routing layer for design system enforcement. Every UI task passes through this skill before implementation begins.

## When This Activates

- Building new UI components or pages
- Modifying existing React/Vue/Svelte components
- Writing CSS, Tailwind classes, or styled-components
- Reviewing frontend code for compliance
- Implementing forms, modals, or interactive elements

## Routing Pipeline

Before writing ANY UI code, follow this pipeline:

```
Task received
  → Load design rules (@rules/design-system/)
  → Check if component/pattern exists in shared library
  → Use design tokens (NEVER raw values)
  → Implement
  → Run /design-check on changed files
```

### Step 1: Load Canonical Rules

ALWAYS read these before UI work:

```
@rules/design-system/_index.md        # Core principles
@rules/design-system/foundations.md    # Color, typography, spacing tokens
@rules/design-system/spacing-patterns.md  # Vertical rhythm, form spacing
@rules/design-system/components.md    # Buttons, forms, copywriting
@rules/design-system/accessibility.md # WCAG requirements
@rules/design-system/page-patterns.md # Cross-page consistency (list, detail, form, dashboard)
```

### Step 1.5: Check Page Archetype Consistency

When building or modifying a **page** (not just a component):

1. Identify the page archetype (list, detail, form, dashboard)
2. Find an existing page of the same type in the codebase
3. Read it and match its structure — same elements, order, placement
4. Check project CLAUDE.md for `### Page Patterns` overrides

### Step 2: Use Design Tokens — Never Raw Values

**Spacing** — Use semantic tokens, never numeric utilities:

```tsx
// ✅ Correct: semantic spacing tokens
<div className="mt-xs mb-sm gap-md p-lg">

// ❌ Wrong: raw numeric utilities
<div className="mt-3 mb-4 gap-6 p-8">
```

See `@rules/design-system/foundations.md` → Spacing Scale for the full token map.

**Color** — Use palette tokens, never raw hex/rgb/hsl:

```tsx
// ✅ Correct: design tokens
<p className="text-primary bg-surface border-border-subtle">

// ❌ Wrong: raw color values
<p className="text-[#1a1a1a] bg-[#fafafa] border-[#e5e5e5]">
```

**Typography** — Use scale constants, never raw sizes:

```tsx
// ✅ Correct: typography scale
<h1 className="text-h1 font-bold">  // 44px bold
<p className="text-body leading-relaxed">  // 18px, 1.5+ line-height

// ❌ Wrong: raw sizing
<h1 className="text-[44px] font-bold">
<p className="text-sm leading-tight">
```

### Step 3: Use Shared Wrappers

Before building a component, check if a shared wrapper exists:

```tsx
// ✅ Correct: shared form wrapper
import { FormField } from '@/components/ui/FormField';
<FormField label="Email" hint="We'll never share this">
  <Input type="email" />
</FormField>

// ❌ Wrong: raw primitives
<div>
  <label>Email</label>
  <input type="email" placeholder="Email" />
</div>
```

### Step 4: Validate After Implementation

After writing UI code, run design-system lint:

```bash
# Check changed files
/design-check --staged

# Or run the deterministic linter directly
.claude/scripts/design-lint.sh --staged
```

## Exception Handling

When a design rule must be broken for legitimate reasons:

```tsx
{/* ds-exception: marketing hero needs custom brand gradient */}
<div className="bg-gradient-to-r from-[#6366f1] to-[#8b5cf6]">
```

Rules:
- Use `ds-exception:` marker with inline reason
- Exceptions are auditable — `/design-check` reports them
- Review exceptions periodically as tech debt

## Anti-Patterns to Block

See `@rules/design-system/foundations.md` → Machine Enforcement for the full list of enforced rules (spacing, color, typography, accessibility). Key violations this skill catches early:

- Raw numeric spacing (`mt-3`) → use semantic tokens (`mt-sm`)
- Hardcoded colors (`text-[#xxx]`) → use design token classes
- Raw font sizes (`text-[44px]`) → use typography scale (`text-h1`)
- Missing labels or focus indicators → see `accessibility.md`

## Enforcement Layers

This skill is one layer in a multi-layer enforcement model:

| Layer | Mechanism | When |
|-------|-----------|------|
| **1. This skill** | Routes agent through design docs | Before implementation |
| **2. PostToolUse hook** | `a11y-design-check.sh` warns on critical a11y issues | After each file edit |
| **3. Deterministic lint** | `design-lint.sh` catches token/spacing/color violations | On demand or pre-commit |
| **4. Pre-commit gate** | Staged-file design lint blocks noncompliant commits | Before git commit |
| **5. CI gate** | Same lint contract runs in CI, blocks PR merge | On pull request |

## Related

- `@rules/design-system/` — Canonical rules (the source of truth)
- `/design-check` — Claude-powered compliance audit (broader, judgment-based)
- `/rams` — Accessibility & visual design audit
- `.claude/scripts/design-lint.sh` — Deterministic lint script (automated)
