---
suggest_when:
  - signal: edits_since_commit
    value: 12
    cooldown: 30
    message: "Many uncommitted edits — `/review` to catch issues before committing"
  - signal: file_extension
    value: ".tsx"
    min_edits: 5
    cooldown: 25
    message: "Multiple component edits — `/review` for accessibility + quality check"
---

# /review Command

Comprehensive code review with accessibility, security, and design quality checks.

## Usage

```
/review [file or directory]
```

## Process

1. **Scan** the specified files for issues
2. **Categorize** by severity (Critical → Serious → Moderate → Minor)
3. **Report** findings with line numbers and fix suggestions
4. **Offer** to auto-fix issues where possible

## Review Checklist

### Critical (Must Fix)

**Security**
- [ ] No hardcoded secrets or API keys
- [ ] Input validation at trust boundaries
- [ ] Parameterized queries (no SQL injection)
- [ ] Auth checks on protected routes/actions

**Accessibility**
- [ ] Images have alt text
- [ ] Buttons/links have accessible names
- [ ] Form inputs have labels
- [ ] No div onClick without keyboard handling

### Serious (Should Fix)

**TypeScript**
- [ ] No `any` types
- [ ] Explicit return types on exports
- [ ] Proper error handling

**React**
- [ ] No unnecessary `'use client'`
- [ ] Keys on list items
- [ ] No missing dependencies in useEffect
- [ ] Proper cleanup in effects

**Performance**
- [ ] No expensive computations in render
- [ ] Large lists virtualized
- [ ] Images have dimensions

**DRY / Reuse**
- [ ] New components checked: does a similar component already exist in the codebase?
- [ ] New hooks checked: does a similar hook already exist?
- [ ] Shared logic extracted: repeated patterns across 2+ files should be consolidated
- [ ] Plan `reuse`/`constraints` honored: if the plan specified reuse directives, were they followed?

### Moderate (Consider Fixing)

**Code Style**
- [ ] Consistent naming conventions
- [ ] No magic numbers
- [ ] Early returns preferred
- [ ] Props destructured in signature

**Design**
- [ ] Focus rings visible
- [ ] Touch targets adequate (44px mobile)
- [ ] Loading states present
- [ ] Error states handled

### Minor (Nice to Have)

- [ ] Comments explain "why" not "what"
- [ ] Imports organized
- [ ] No commented-out code

## Output Format

```
═══════════════════════════════════════════════════
CODE REVIEW: [filename]
═══════════════════════════════════════════════════

CRITICAL (N issues)
───────────────────
[Category] Line X: Issue description
  → Code snippet
  Fix: Suggested fix

SERIOUS (N issues)
──────────────────
[Category] Line X: Issue description
  → Code snippet
  Fix: Suggested fix

═══════════════════════════════════════════════════
SUMMARY: X critical, Y serious, Z moderate
Score: NN/100
═══════════════════════════════════════════════════
```

## Auto-Fix

After reporting, ask:

> Would you like me to auto-fix the [N] issues that can be automatically resolved?

Auto-fixable issues:
- Missing alt="" on decorative images
- Adding aria-label to icon buttons
- Adding explicit return types
- Converting any to unknown
- Adding key props to lists

## Suggested Next

| If... | Run |
|-------|-----|
| Issues found that need fixing | `/iterate` — work through fixes systematically |
| Review passed, ready for PR | `/pre-pr-check` — full pre-PR validation |
