---
suggest_when:
  - signal: edits_since_commit
    value: 15
    cooldown: 45
    message: "Large changeset — `/techdebt` to check for duplication before committing"
---

# Tech Debt

Find and eliminate duplicated code, redundant helpers, and missed abstraction opportunities. Focuses on DRY violations where existing utilities could be used or where new abstractions should be extracted.

## Your Task

Analyze the codebase (or staged changes) to identify:
1. **Duplicated logic** that should use existing helpers
2. **Redundant helpers** that duplicate existing utilities
3. **Extraction opportunities** where repeated patterns should become shared utilities

$ARGUMENTS

## Step 1: Parse Arguments

| Argument        | Example                    | Description                              |
| --------------- | -------------------------- | ---------------------------------------- |
| `--staged`      |                            | Only analyze staged files (for pre-commit) |
| `--path <dir>`  | `--path src/components`    | Limit analysis to specific directory     |
| `--fix`         |                            | Auto-fix simple duplications             |
| `--report`      |                            | Generate detailed report file            |
| `<file>`        | `src/utils/auth.ts`        | Analyze specific file                    |

Default (no args): Analyze entire `src/` directory.

## Step 2: Discover Existing Utilities

First, catalog existing helper functions and utilities in the codebase:

### 2.1 Find Utility Files

```bash
# Common utility locations
find src -type f \( -name "*.ts" -o -name "*.tsx" \) | grep -E "(utils|helpers|lib|shared|common)"
```

### 2.2 Extract Function Signatures

For each utility file, extract exported functions:

```markdown
## Existing Utilities

### src/lib/utils.ts
- `cn(...classes)` - Merge Tailwind classes
- `formatDate(date, format?)` - Format dates
- `slugify(text)` - Convert to URL slug

### src/utils/validation.ts
- `isValidEmail(email)` - Email validation
- `isValidPhone(phone)` - Phone validation
- `sanitizeInput(input)` - XSS sanitization

### src/hooks/useDebounce.ts
- `useDebounce(value, delay)` - Debounce hook
```

Store this catalog for comparison.

## Step 3: Analyze for Duplications

### 3.1 Inline Reimplementations

Look for code that reimplements existing utilities:

```typescript
// ❌ BAD: Reimplementing cn() utility
const classes = [baseClass, isActive && 'active', className]
  .filter(Boolean)
  .join(' ');

// ✅ GOOD: Use existing utility
const classes = cn(baseClass, isActive && 'active', className);
```

**Common patterns to detect:**
- Manual class merging (when `cn`/`clsx` exists)
- Inline date formatting (when `formatDate` exists)
- Manual debouncing (when `useDebounce` exists)
- Repeated validation regex (when validators exist)
- Manual API error handling (when `handleApiError` exists)

### 3.2 Redundant New Helpers

Look for newly created helpers that duplicate existing ones:

```typescript
// ❌ BAD: New helper that duplicates existing
// src/features/auth/utils.ts
export function combineClassNames(...classes: string[]) {
  return classes.filter(Boolean).join(' ');
}

// ✅ EXISTING: src/lib/utils.ts already has cn()
```

### 3.3 Copy-Paste Code Blocks

Find similar code blocks across files:

```typescript
// File A: src/components/UserCard.tsx
const fullName = user.firstName + ' ' + user.lastName;
const initials = user.firstName[0] + user.lastName[0];

// File B: src/components/UserAvatar.tsx
const fullName = user.firstName + ' ' + user.lastName;
const initials = user.firstName[0] + user.lastName[0];

// 🔧 EXTRACT: Create src/utils/user.ts
export const getFullName = (user: User) => `${user.firstName} ${user.lastName}`;
export const getInitials = (user: User) => `${user.firstName[0]}${user.lastName[0]}`;
```

## Step 4: Report Findings

### Summary Report

```markdown
## Tech Debt Report

**Analyzed**: 47 files
**Issues Found**: 12

### By Category

| Category                  | Count | Severity |
| ------------------------- | ----- | -------- |
| Inline reimplementations  | 5     | Medium   |
| Redundant helpers         | 2     | High     |
| Extraction opportunities  | 5     | Low      |

### Critical Issues (Fix Now)

#### 1. Redundant Helper: `combineClassNames`
**File**: `src/features/auth/utils.ts:15`
**Issue**: Duplicates existing `cn()` from `src/lib/utils.ts`
**Fix**: Delete and use `cn()` instead

```diff
- import { combineClassNames } from './utils';
+ import { cn } from '@/lib/utils';

- className={combineClassNames('btn', isActive && 'btn-active')}
+ className={cn('btn', isActive && 'btn-active')}
```

#### 2. Inline Reimplementation: Date Formatting
**Files**: `src/components/Invoice.tsx:42`, `src/components/Order.tsx:28`
**Issue**: Manual date formatting when `formatDate` exists
**Fix**: Import and use existing utility

```diff
- const formatted = new Date(date).toLocaleDateString('en-US', { ... });
+ import { formatDate } from '@/lib/utils';
+ const formatted = formatDate(date, 'MM/DD/YYYY');
```

### Extraction Opportunities (Consider)

#### 3. User Name Formatting (3 occurrences)
**Files**: `UserCard.tsx`, `UserAvatar.tsx`, `UserProfile.tsx`
**Pattern**: `user.firstName + ' ' + user.lastName`
**Suggestion**: Create `getFullName(user)` utility

### Ignored (Intentional)

- `src/legacy/*` - Legacy code, separate refactor planned
```

## Step 5: Auto-Fix (If --fix)

For simple cases, apply automatic fixes:

### Safe to Auto-Fix:
- Import path changes (use existing utility)
- Simple function replacements (same signature)

### Requires Manual Review:
- Logic differences between implementations
- Different error handling
- Type signature mismatches

```markdown
## Auto-Fix Results

**Fixed**: 3 issues
**Requires Manual**: 2 issues

### Fixed Automatically

1. ✅ `src/components/Card.tsx:15` - Replaced inline class merge with `cn()`
2. ✅ `src/components/Modal.tsx:32` - Replaced inline class merge with `cn()`
3. ✅ `src/features/dashboard/utils.ts:8` - Removed redundant `formatCurrency`, using `@/lib/format`

### Requires Manual Review

1. ⚠️ `src/features/auth/utils.ts:15` - `validateEmail` has different error messages
2. ⚠️ `src/hooks/useLocalStorage.ts:1` - Similar to existing but handles SSR differently
```

## Step 6: Generate Report File (If --report)

Save detailed report:

```bash
# Output location
.claude/reports/techdebt-{timestamp}.md
```

## Staged Files Mode (--staged)

For pre-commit hook usage, only analyze staged files:

```bash
# Get staged files
git diff --cached --name-only --diff-filter=ACM | grep -E '\.(ts|tsx)$'
```

Then run analysis only on those files, comparing against the full utility catalog.

### Pre-Commit Output Format

```markdown
## Tech Debt Check: WARN

Found **2 issues** in staged files:

1. `src/components/NewFeature.tsx:45`
   Inline class merging - use `cn()` from `@/lib/utils`

2. `src/features/checkout/helpers.ts:12`
   New `formatPrice()` duplicates `formatCurrency()` from `@/lib/format`

Run `/techdebt --fix` to auto-fix, or commit with `--no-verify` to skip.
```

## Error Handling

| Scenario              | Response                                    |
| --------------------- | ------------------------------------------- |
| No src/ directory     | Look for other common dirs (app/, lib/)     |
| No utilities found    | Report clean, suggest creating utils/       |
| Parse errors          | Skip file, report in output                 |
| Too many duplications | Prioritize by severity, suggest incremental |

## Arguments

| Argument       | Description                                        |
| -------------- | -------------------------------------------------- |
| `--staged`     | Only check staged files (for pre-commit hooks)     |
| `--path <dir>` | Limit analysis to specific directory               |
| `--fix`        | Auto-fix simple duplications                       |
| `--report`     | Generate detailed markdown report                  |
| `--strict`     | Fail on any duplication (for CI)                   |
| `<file>`       | Analyze specific file                              |

## Examples

```bash
# Full codebase scan
/techdebt

# Check only staged files (pre-commit)
/techdebt --staged

# Analyze specific directory
/techdebt --path src/features/auth

# Auto-fix and generate report
/techdebt --fix --report

# Strict mode for CI
/techdebt --strict
```

## Pre-Commit Hook Integration

Add to `.claude/hooks/pre-tool-use/` or use with husky:

```bash
# .husky/pre-commit
npx claude --command "/techdebt --staged --strict"
```

Or configure in `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash(git commit*)",
        "hooks": [
          {
            "type": "command",
            "command": "claude --print '/techdebt --staged'"
          }
        ]
      }
    ]
  }
}
```

## Related Commands

| Command             | Use                                      |
| ------------------- | ---------------------------------------- |
| `/compliance-check` | Full compliance scan (includes DRY)      |
| `/review`           | Code review (catches some duplications)  |
| `/pre-commit-check` | Pre-commit validation suite              |
| `/deslop`           | Remove AI-generated artifacts            |

---

_Duplication is the root of all evil in software. Find it. Kill it._

## Suggested Next

- `/create-commit` — commit after eliminating the debt
- `/compliance-check` — verify code quality metrics after cleanup
- `/deslop` — remove AI-generated artifacts alongside tech debt
