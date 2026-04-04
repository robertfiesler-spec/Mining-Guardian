---
suggest_when:
  - signal: total_tool_calls
    value: 50
    cooldown: 45
    message: "Extended session — `/compliance-check` to validate patterns and complexity"
  - signal: file_extension
    value: ".tsx"
    min_edits: 6
    cooldown: 30
    message: "Heavy React edits — `/compliance-check` to verify skill compliance"
---

# Compliance Check

Validates code against all defined skills, rules, and patterns. Ensures the codebase follows established standards.

## Usage

```
/compliance-check [options]
```

$ARGUMENTS

## Step 0: Detect Scope

Determine what to check:

```bash
# If on feature branch, check changed files
if [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ] && [ "$(git rev-parse --abbrev-ref HEAD)" != "master" ]; then
  BASE_BRANCH=$(git rev-parse --abbrev-ref @{upstream} 2>/dev/null || echo "origin/main")
  FILES=$(git diff --name-only ${BASE_BRANCH}...HEAD | grep -E '\.(ts|tsx)$')
else
  # On main branch, check staged files or all source files
  FILES=$(git diff --cached --name-only | grep -E '\.(ts|tsx)$')
fi
```

If `--all` flag passed, check entire codebase (warning: may be slow).

## Step 1: TypeScript Compliance

**Source:** `rules/typescript.md`, `CLAUDE.md`

| Check                                 | Pattern                                                  | Severity |
| ------------------------------------- | -------------------------------------------------------- | -------- |
| No `any` types                        | `grep -E ": any\b" `                                     | High     |
| No `@ts-ignore`                       | `grep "@ts-ignore"`                                      | High     |
| No `@ts-expect-error` without comment | `grep "@ts-expect-error$"`                               | Medium   |
| Explicit return types on exports      | `export (async )?function.*\).*{` without `: ReturnType` | Medium   |
| Interface over type for objects       | `type.*=.*{` (prefer interface)                          | Low      |

**Automated:** ESLint with `@typescript-eslint` rules covers most of these.

```bash
pnpm eslint --rule '@typescript-eslint/no-explicit-any: error' $FILES
```

## Step 2: React Patterns Compliance

**Source:** `skills/react-patterns/SKILL.md`, `CLAUDE.md`

### 2.1 Server vs Client Components

| Check                      | What to Verify                                     | Severity           |
| -------------------------- | -------------------------------------------------- | ------------------ |
| Unnecessary `'use client'` | Client directive without hooks/events/browser APIs | Medium             |
| Missing `'use client'`     | useState/useEffect without directive               | High (build fails) |

```bash
# Find 'use client' files and check if they actually need it
for file in $(grep -l "'use client'" $FILES); do
  if ! grep -qE "(useState|useEffect|useRef|useCallback|useMemo|onClick|onChange|onSubmit|window\.|document\.|localStorage)" "$file"; then
    echo "WARN: $file may not need 'use client'"
  fi
done
```

### 2.2 Component Structure

| Check                        | Pattern                                     | Severity |
| ---------------------------- | ------------------------------------------- | -------- |
| Named exports                | `export default function` in non-page files | Medium   |
| Props interface naming       | `interface.*Props` convention               | Low      |
| No prop drilling (>3 levels) | Manual review                               | Low      |

### 2.3 Hooks Rules

| Check                     | Pattern                              | Severity |
| ------------------------- | ------------------------------------ | -------- |
| Missing deps in useEffect | ESLint `react-hooks/exhaustive-deps` | High     |
| Hooks in conditionals     | ESLint `react-hooks/rules-of-hooks`  | High     |

```bash
pnpm eslint --rule 'react-hooks/exhaustive-deps: warn' --rule 'react-hooks/rules-of-hooks: error' $FILES
```

## Step 3: Accessibility Compliance

**Source:** `skills/accessibility/SKILL.md`

### 3.1 Static Checks

| Check                      | Pattern                                              | Severity |
| -------------------------- | ---------------------------------------------------- | -------- |
| Images without alt         | `<img` without `alt=`                                | Critical |
| Icon buttons without label | `<button>.*Icon.*</button>` without `aria-label`     | Critical |
| Inputs without labels      | `<input` without associated `<label` or `aria-label` | Critical |
| onClick on div/span        | `<div onClick` or `<span onClick`                    | High     |
| Removed focus outline      | `outline-none` without `focus-visible:` replacement  | High     |
| Positive tabIndex          | `tabIndex={[1-9]}`                                   | Medium   |

```bash
# ESLint jsx-a11y plugin
pnpm eslint --plugin jsx-a11y --rule 'jsx-a11y/alt-text: error' --rule 'jsx-a11y/click-events-have-key-events: error' $FILES
```

### 3.2 Runtime Checks (--thorough only)

If axe-core is configured, run accessibility audit:

```bash
# Check if axe-core test exists
if [ -f "__tests__/a11y.test.ts" ]; then
  pnpm test __tests__/a11y.test.ts
fi
```

## Step 4: Security Compliance

**Source:** `rules/security.md`, `skills/security/SKILL.md`

Delegate to `/security-check --quick` for:

- Hardcoded secrets
- Dependency vulnerabilities
- Injection patterns

Additional pattern checks:

| Check                           | Pattern                                | Severity |
| ------------------------------- | -------------------------------------- | -------- |
| Console.log with sensitive data | `console.log.*password\|token\|secret` | High     |
| dangerouslySetInnerHTML         | Without DOMPurify                      | High     |
| Unvalidated API input           | API route without Zod/schema           | Medium   |

## Step 5: Data Fetching Compliance

**Source:** `skills/data-fetching/SKILL.md`

| Check                    | What to Verify                                             | Severity |
| ------------------------ | ---------------------------------------------------------- | -------- |
| Server Actions in client | `'use server'` action called from `'use client'` correctly | Low      |
| Caching strategy         | `fetch()` without cache option in RSC                      | Low      |
| Error handling           | `try/catch` around async operations                        | Medium   |

## Step 6: Code Style Compliance

**Source:** `rules/code-style.md`, `CLAUDE.md`

| Check                      | Pattern                            | Severity |
| -------------------------- | ---------------------------------- | -------- |
| Magic numbers              | Numeric literals outside constants | Low      |
| Deep nesting (>3 levels)   | Nested if/for/while                | Low      |
| Long functions (>50 lines) | Line count                         | Low      |
| Comments explaining "what" | `// [verb]s the` pattern           | Info     |

Most covered by ESLint/Prettier. Run:

```bash
pnpm lint $FILES
```

## Step 7: Testing Compliance

**Source:** `skills/testing/SKILL.md`

| Check                   | What to Verify                    | Severity |
| ----------------------- | --------------------------------- | -------- |
| New files have tests    | `*.ts(x)` → `*.test.ts(x)` exists | Medium   |
| Test naming conventions | `describe/it` structure           | Low      |
| No skipped tests        | `.skip` or `xit`                  | Low      |

```bash
# Check for skipped tests
grep -r "\.skip\|xit\(" __tests__/ && echo "WARN: Skipped tests found"
```

## Step 8: Code Complexity

**Source:** `rules/code-style.md`, `agents/refactor-cleaner.md`

Analyze code for complexity, duplication, and maintainability issues.

### 8.1 Complexity Metrics

| Check                 | Threshold         | Severity |
| --------------------- | ----------------- | -------- |
| Cyclomatic complexity | > 10 per function | Medium   |
| Function length       | > 50 lines        | Medium   |
| File length           | > 400 lines       | Low      |
| Nesting depth         | > 3 levels        | Medium   |
| Parameter count       | > 5 parameters    | Low      |

### 8.2 DRY Violations

| Check                       | Detection Method                  | Severity |
| --------------------------- | --------------------------------- | -------- |
| Duplicate code blocks       | AST comparison, 10+ similar lines | Medium   |
| Copy-paste patterns         | Near-identical logic in 2+ places | Medium   |
| Repeated conditionals       | Same if/switch logic duplicated   | Low      |
| Similar function signatures | Functions doing same thing        | Low      |

Detection approach:

```bash
# Use jscpd for copy-paste detection
npx jscpd --min-lines 10 --min-tokens 50 --reporters console $FILES

# Or manual pattern detection
# Look for functions with identical structure
```

### 8.3 Dead Code

| Check            | Detection Method             | Severity |
| ---------------- | ---------------------------- | -------- |
| Unused exports   | No imports found in codebase | Medium   |
| Unused functions | Declared but never called    | Medium   |
| Unused variables | ESLint `no-unused-vars`      | Low      |
| Unreachable code | Code after return/throw      | Medium   |

```bash
# Check for unused exports
npx ts-prune --error

# ESLint unused checks
pnpm eslint --rule 'no-unused-vars: warn' --rule '@typescript-eslint/no-unused-vars: warn' $FILES
```

### 8.4 Over-Engineering

| Check                       | Pattern                                  | Severity |
| --------------------------- | ---------------------------------------- | -------- |
| Premature abstraction       | Generic helper used only once            | Low      |
| Unnecessary indirection     | Wrapper functions that just call another | Low      |
| Over-defensive coding       | Null checks for non-nullable types       | Low      |
| Feature flags for dead code | Flags that are always true/false         | Low      |

## Output Format

```markdown
## Compliance Report

**Scope:** 15 files (feature branch changes)
**Mode:** [quick|standard|thorough]

---

### Skills Matrix

| Skill           | Files | Issues | Status     |
| --------------- | ----- | ------ | ---------- |
| TypeScript      | 15    | 0      | ✅ Pass    |
| React Patterns  | 12    | 1      | ⚠️ Warning |
| Accessibility   | 8     | 2      | ❌ Fail    |
| Security        | 15    | 0      | ✅ Pass    |
| Data Fetching   | 5     | 0      | ✅ Pass    |
| Code Style      | 15    | 3      | ⚠️ Warning |
| Testing         | 10    | 1      | ⚠️ Warning |
| Code Complexity | 15    | 4      | ⚠️ Warning |

---

### Critical Issues (must fix)

**[A11Y-001] Image missing alt text**

- File: `components/Hero.tsx:23`
- Code: `<img src={heroImage} />`
- Fix: Add `alt="Description of image"` or `alt=""` if decorative

**[A11Y-002] Button without accessible name**

- File: `components/IconButton.tsx:15`
- Code: `<button><TrashIcon /></button>`
- Fix: Add `aria-label="Delete item"`

---

### Warnings (should fix)

**[REACT-001] Unnecessary 'use client'**

- File: `components/StaticCard.tsx:1`
- Issue: No hooks or event handlers found
- Fix: Remove `'use client'` directive

**[STYLE-001] Magic number**

- File: `lib/utils/pagination.ts:12`
- Code: `const pageSize = 25;`
- Fix: Extract to named constant `DEFAULT_PAGE_SIZE`

**[COMPLEXITY-001] High cyclomatic complexity**

- File: `lib/orders/validation.ts:45`
- Function: `validateOrder` (complexity: 15, threshold: 10)
- Fix: Extract conditional branches into separate functions

**[COMPLEXITY-002] DRY violation - duplicate code**

- Files: `components/UserCard.tsx:20-45`, `components/ProfileCard.tsx:15-40`
- Issue: 25 lines of near-identical rendering logic
- Fix: Extract shared component or utility

**[COMPLEXITY-003] Unused export**

- File: `lib/utils/format.ts:89`
- Export: `formatLegacyDate` - no imports found
- Fix: Remove if truly unused, or document if external

---

### Info (consider)

**[TEST-001] Missing test file**

- File: `lib/utils/format.ts`
- Expected: `__tests__/unit/utils/format.test.ts`

---

## Summary

| Severity | Count |
| -------- | ----- |
| Critical | 2     |
| Warning  | 7     |
| Info     | 1     |

**Overall:** ❌ FAIL - Fix 2 critical issues

**Recommended actions:**

1. Fix accessibility issues before merge
2. Consider addressing warnings for code quality

---

## Complexity Issues Detected

Found **3 complexity issues** that can be automatically refactored.

> Run `@refactor-cleaner` to fix complexity issues with proper test verification?
> [Yes] [No] [Review first]
```

## Quick Mode (for pre-pr-check)

With `--quick`, run only:

1. TypeScript: No `any`, no `@ts-ignore`
2. Accessibility: Critical checks only (alt text, button labels, input labels)
3. Security: Delegate to `/security-check --quick`
4. React: ESLint hooks rules

Skip thorough code review, runtime tests, and info-level checks.

Output condensed format:

```markdown
## Quick Compliance: ✅ PASS (or ❌ FAIL)

| Check                    | Status |
| ------------------------ | ------ |
| TypeScript               | ✅     |
| Accessibility (critical) | ✅     |
| Security                 | ✅     |
| React hooks              | ✅     |

No critical issues. Run `/compliance-check` for full report.
```

## Thorough Mode

With `--thorough`:

1. All standard checks
2. Runtime accessibility tests (axe-core)
3. Test coverage analysis
4. Performance pattern review (useMemo/useCallback usage)
5. Full file-by-file report

## Arguments

| Argument            | Description                                               |
| ------------------- | --------------------------------------------------------- |
| `--quick`           | Critical checks only (for pre-pr-check integration)       |
| `--thorough`        | Deep analysis including runtime tests                     |
| `--skill <name>`    | Check specific skill only (e.g., `--skill accessibility`) |
| `--files <pattern>` | Check specific files/pattern                              |
| `--all`             | Check entire codebase (slow)                              |
| `--fix`             | Auto-fix issues where possible                            |
| `--fix-complexity`  | Auto-delegate complexity issues to refactor-cleaner       |
| `--json`            | Output as JSON for CI                                     |
| `--fail-on <level>` | Exit non-zero at level (critical/warning/info)            |

## Auto-Fix Capabilities

With `--fix`:

| Issue                                 | Auto-Fix                               |
| ------------------------------------- | -------------------------------------- |
| Missing `alt=""` on decorative images | Add `alt=""`                           |
| `any` type                            | Suggest `unknown` replacement          |
| Missing aria-label                    | Generate from context if possible      |
| Skipped tests                         | Remove `.skip`                         |
| Magic numbers                         | Extract to constant (prompts for name) |

## Complexity Fix Delegation

Complexity issues require careful refactoring with test verification. When complexity issues are found, compliance-check offers to delegate to the `refactor-cleaner` agent.

### Delegation Workflow

1. **Detection**: Compliance-check identifies complexity issues
2. **Prompt**: Ask user if they want to fix via refactor-cleaner
3. **Handoff**: Pass specific issues and files to refactor-cleaner
4. **Verification**: Refactor-cleaner ensures tests pass after each change
5. **Report**: Return summary of refactorings applied

### What Gets Delegated

| Issue Type       | Refactor-Cleaner Action                     |
| ---------------- | ------------------------------------------- |
| High complexity  | Extract functions, simplify conditionals    |
| DRY violations   | Extract shared utilities or components      |
| Unused exports   | Remove dead code (after usage verification) |
| Deep nesting     | Convert to early returns, extract helpers   |
| Long functions   | Split into smaller, focused functions       |
| Over-engineering | Inline unnecessary abstractions             |

### Manual Delegation

If you skip auto-delegation, you can manually invoke:

```
@refactor-cleaner lib/orders/validation.ts lib/utils/format.ts
```

Or for specific issues:

```
@refactor-cleaner --focus "DRY violation in UserCard and ProfileCard"
```

### With `--fix-complexity` Flag

Run compliance-check with automatic complexity fixing:

```bash
/compliance-check --fix-complexity
```

This runs the full compliance check, then automatically delegates complexity issues to refactor-cleaner without prompting.

## ESLint Plugin Requirements

For full compliance checking, ensure these ESLint plugins are installed:

```bash
pnpm add -D @typescript-eslint/eslint-plugin eslint-plugin-react-hooks eslint-plugin-jsx-a11y
```

Recommended `.eslintrc` additions:

```json
{
  "extends": [
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended"
  ],
  "rules": {
    "@typescript-eslint/no-explicit-any": "error",
    "react-hooks/exhaustive-deps": "warn",
    "jsx-a11y/alt-text": "error"
  }
}
```

## Integration with Other Commands

- `/pre-pr-check` - Runs `/compliance-check --quick` as Step 3
- `/review` - Can invoke `/compliance-check --skill accessibility,security` for focused review
- `/security-check` - Compliance-check delegates security to this command

## Related Commands

- `/security-check` - Deep security analysis
- `/review` - Manual code review with suggestions
- `/pre-pr-check` - Full pre-PR validation

## Suggested Next

- `/pre-pr-check` — full pre-PR validation (includes compliance)
- `/techdebt` — eliminate duplication and dead code found
- `/deslop` — remove AI-generated artifacts flagged by check
- `/create-commit` — commit cleanup after resolving issues
