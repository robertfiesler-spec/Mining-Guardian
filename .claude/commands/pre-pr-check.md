---
suggest_when:
  - signal: edits_since_commit
    value: 15
    cooldown: 30
    message: "Many uncommitted changes — `/pre-pr-check` validates before PR"
---
# Pre-PR Check

Run comprehensive checks to ensure changes are ready for a pull request.

## Your Task

Execute all pre-PR checks and report results. Follow each step in order.

$ARGUMENTS

## Step 0a: Detect Depth Mode

Check `$ARGUMENTS` for `--quick`, `--deep`, or `--force`. If **no depth flag detected**, suggest based on context:

- If changed files touch auth, payments, or user data → suggest `--deep`
- If only a few files changed (< 5) and no security-sensitive paths → default is fine
- If user says "fast" or "quick check" → apply `--quick`

> **Which check depth?**
>
> | Mode | Flag | What it does |
> |------|------|-------------|
> | **Standard** (default) | _(none)_ | Full checks with quick security/compliance scans |
> | **Quick** | `--quick` | Skip tests — lint, types, and hygiene only |
> | **Deep** | `--deep` | Full OWASP security, compliance, and WCAG audits |
>
> _Recommended: `--deep` for security-sensitive changes (auth, payments, APIs)._

If the intent is clear from context (e.g., user said "quick check before PR"), skip the prompt and apply the appropriate flag.

## Step 0b: Detect Base Branch

First, determine the base branch to compare against:

```bash
# Try to get the upstream branch (where current branch tracks)
BASE_BRANCH=$(git rev-parse --abbrev-ref @{upstream} 2>/dev/null)

# If no upstream is set, try common defaults
if [ -z "$BASE_BRANCH" ]; then
  if git rev-parse --verify origin/staging >/dev/null 2>&1; then
    BASE_BRANCH="origin/staging"
  elif git rev-parse --verify origin/master >/dev/null 2>&1; then
    BASE_BRANCH="origin/master"
  elif git rev-parse --verify origin/main >/dev/null 2>&1; then
    BASE_BRANCH="origin/main"
  else
    echo "Error: Could not determine base branch"
    exit 1
  fi
fi

echo "Comparing against base branch: $BASE_BRANCH"
```

Store the BASE_BRANCH for use in subsequent steps.

## Step 0.5: Git Hygiene Checks

**These checks run first** - fundamental git workflow validation for team development.

### 0.5.1: Branch Protection

```bash
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Block if on protected branch
if [ "$CURRENT_BRANCH" = "main" ] || [ "$CURRENT_BRANCH" = "master" ]; then
  echo "❌ BLOCKED: You are on '$CURRENT_BRANCH'. Create a feature branch first."
  exit 1
fi
```

**Why**: Direct commits to main/master bypass code review and can break the build for everyone. Always work on feature branches.

**If blocked**:

```bash
# Create a branch from your current changes
git checkout -b feature/your-feature-name
# Or if you already committed to main accidentally:
git checkout -b feature/your-feature-name
git checkout main
git reset --hard origin/main
```

### 0.5.2: Branch Naming Convention

```bash
# Check branch name follows convention
if ! echo "$CURRENT_BRANCH" | grep -qE "^(feature|fix|hotfix|refactor|chore|docs|test)/[a-z0-9-]+$"; then
  echo "⚠️ WARNING: Branch '$CURRENT_BRANCH' doesn't follow naming convention"
fi
```

**Required format**: `<type>/<description>`

| Prefix      | Use For                 | Example                       |
| ----------- | ----------------------- | ----------------------------- |
| `feature/`  | New functionality       | `feature/user-authentication` |
| `fix/`      | Bug fixes               | `fix/login-redirect-loop`     |
| `hotfix/`   | Urgent production fixes | `hotfix/payment-crash`        |
| `refactor/` | Code restructuring      | `refactor/api-client`         |
| `chore/`    | Maintenance tasks       | `chore/update-dependencies`   |
| `docs/`     | Documentation only      | `docs/api-readme`             |
| `test/`     | Test additions          | `test/checkout-flow`          |

**Why**: Consistent naming helps team members understand what a branch does at a glance. It also enables automation (auto-labeling PRs, release notes generation).

**If warning**:

```bash
# Rename your branch
git branch -m feature/descriptive-name
```

### 0.5.3: Commit Message Format

```bash
# Get commits unique to this branch
COMMITS=$(git log ${BASE_BRANCH}..HEAD --pretty=format:"%s")

# Check each commit follows conventional format
echo "$COMMITS" | while read -r msg; do
  if ! echo "$msg" | grep -qE "^(feat|fix|refactor|perf|test|docs|chore|style)(\(.+\))?: .{1,72}$"; then
    echo "⚠️ Bad commit message: $msg"
  fi
done
```

**Required format**: `<type>(<scope>): <description>`

| Type       | Use For                          | Example                                  |
| ---------- | -------------------------------- | ---------------------------------------- |
| `feat`     | New feature                      | `feat(auth): add Google OAuth login`     |
| `fix`      | Bug fix                          | `fix(cart): prevent negative quantities` |
| `refactor` | Code change (no new feature/fix) | `refactor(api): simplify error handling` |
| `perf`     | Performance improvement          | `perf(images): add lazy loading`         |
| `test`     | Adding/updating tests            | `test(checkout): add payment flow tests` |
| `docs`     | Documentation                    | `docs(readme): add setup instructions`   |
| `chore`    | Maintenance                      | `chore(deps): update React to 18.2`      |
| `style`    | Formatting (no code change)      | `style: fix indentation`                 |

**Why**: Consistent commit messages enable:

- Automatic changelog generation
- Easier code review (understand intent)
- Better `git log` and `git blame` output
- Semantic versioning automation

**If warning**:

```bash
# Reword your last commit
git commit --amend -m "feat(scope): proper message"

# Reword multiple commits (interactive rebase)
git rebase -i ${BASE_BRANCH}
# Change 'pick' to 'reword' for commits to fix
```

### 0.5.4: PR Size Check

```bash
# Count lines changed
LINES_CHANGED=$(git diff --stat ${BASE_BRANCH}...HEAD | tail -1 | grep -oE '[0-9]+' | head -1)
FILES_CHANGED=$(git diff --name-only ${BASE_BRANCH}...HEAD | wc -l | tr -d ' ')

if [ "$LINES_CHANGED" -gt 400 ]; then
  echo "⚠️ WARNING: Large PR ($LINES_CHANGED lines, $FILES_CHANGED files)"
  echo "   Consider splitting into smaller PRs for easier review."
fi

if [ "$LINES_CHANGED" -gt 800 ]; then
  echo "❌ BLOCKED: PR too large ($LINES_CHANGED lines)"
  echo "   PRs over 800 lines are hard to review thoroughly."
  echo "   Split into smaller, focused PRs."
fi
```

**Size guidelines**:

| Lines Changed | Status     | Guidance                       |
| ------------- | ---------- | ------------------------------ |
| < 200         | ✅ Ideal   | Fast, thorough review possible |
| 200-400       | ✅ OK      | Acceptable for features        |
| 400-800       | ⚠️ Warning | Consider splitting             |
| > 800         | ❌ Blocked | Must split                     |

**Why**: Large PRs have problems:

- Reviewers get fatigued and miss issues
- Harder to understand the full change
- Higher risk of merge conflicts
- Longer time to merge (blocks other work)

**If blocked/warning**:

1. Identify logical boundaries in your changes
2. Create separate branches for each concern
3. Submit as a series of smaller PRs
4. Use PR descriptions to link related PRs

### 0.5.5: Linked Issue Check

```bash
# Check if any commit references an issue
COMMITS=$(git log ${BASE_BRANCH}..HEAD --pretty=format:"%s %b")

if ! echo "$COMMITS" | grep -qiE "(#[0-9]+|closes|fixes|resolves|relates to)"; then
  echo "⚠️ WARNING: No issue linked in commits"
  echo "   Link with: feat(scope): description (closes #123)"
  echo "   Or add 'Closes #123' in commit body"
fi
```

**How to link issues**:

```bash
# In commit message
git commit -m "feat(auth): add OAuth login (closes #42)"

# In commit body
git commit -m "feat(auth): add OAuth login

Implements Google OAuth as requested.

Closes #42"

# Multiple issues
git commit -m "fix(api): handle rate limiting

Fixes #15
Relates to #20"
```

**Why**: Linking issues to PRs:

- Provides context for reviewers
- Auto-closes issues when PR merges
- Creates traceability (why was this change made?)
- Helps with project tracking

**If warning**: This is non-blocking but recommended. Add issue reference when creating PR if not in commits.

### Git Hygiene Summary

Report results before continuing:

```markdown
### Git Hygiene

| Check             | Status | Details                       |
| ----------------- | ------ | ----------------------------- |
| Branch protection | ✅     | On `feature/user-auth`        |
| Branch naming     | ✅     | Follows convention            |
| Commit messages   | ⚠️     | 1 of 5 commits need rewording |
| PR size           | ✅     | 245 lines (acceptable)        |
| Linked issue      | ⚠️     | No issue referenced           |

**Action required**: Fix commit messages before PR.
```

## Step 1: Deslop

Run `/deslop --base $BASE_BRANCH` to remove AI-generated artifacts before validation.

This catches:

- Unnecessary comments added during development
- Defensive overkill (redundant try/catch, null checks)
- Type workarounds (`any` casts, `@ts-ignore`)
- Style inconsistencies

If changes were made, report them briefly before continuing.

## Step 2: Security Check

Run security scan based on mode:
- **Default/Quick**: `/security-check --base $BASE_BRANCH --quick`
- **Deep**: `/security-check --base $BASE_BRANCH` (full scan)

This catches:

- Hardcoded secrets, API keys, tokens
- Vulnerable dependencies (npm/pip audit)
- Common secret patterns in code
- **Deep mode adds**: OWASP pattern analysis, auth flow review, data exposure checks

If critical or high issues found, report them as blocking issues.

## Step 3: Compliance Check

Run compliance check based on mode:
- **Default/Quick**: `/compliance-check --quick`
- **Deep**: `/compliance-check` (full validation against all skills/rules)

This catches:

- TypeScript violations (`any` types, `@ts-ignore`)
- React hooks rule violations
- Obvious pattern deviations
- **Deep mode adds**: Full skill validation, DRY analysis, dead code detection

If critical issues found, report them as blocking issues.

## Step 3.5: Code Complexity Check

**This step is mandatory** - complexity issues must be addressed before PR.

Run complexity analysis on changed files:

```bash
# Get changed source files
CHANGED_FILES=$(git diff --name-only ${BASE_BRANCH}...HEAD | grep -E '\.(ts|tsx|py)$' | grep -v '\.test\.' | grep -v '\.spec\.' | grep -v 'test_')
```

### Checks (Block PR if found)

| Issue                 | Threshold            | Why It Matters                         |
| --------------------- | -------------------- | -------------------------------------- |
| Cyclomatic complexity | > 10                 | Hard to test, prone to bugs            |
| Function length       | > 50 lines           | Should be split into smaller functions |
| Nesting depth         | > 3 levels           | Use early returns instead              |
| Duplicate code        | > 15 similar lines   | Violates DRY, maintenance burden       |
| Unused exports        | Any in changed files | Dead code, confuses readers            |

### Detection Commands

```bash
# Cyclomatic complexity (requires eslint-plugin-complexity or similar)
npx eslint --rule 'complexity: ["error", 10]' $CHANGED_FILES

# Duplicate code detection
npx jscpd --min-lines 15 --min-tokens 50 $CHANGED_FILES

# Unused exports
npx ts-prune $CHANGED_FILES
```

### On Failure

If complexity issues are found:

1. **Report each issue** with file, line, and specific problem
2. **Explain why it matters** (junior dev education)
3. **Offer to fix**: "Run `@refactor-cleaner` to automatically fix these issues?"
4. **Block PR creation** until resolved

### Example Output

```markdown
### ❌ Code Complexity

Found 3 issues that must be fixed before PR:

**[COMPLEXITY-001] High cyclomatic complexity**

- File: `lib/orders/validate.ts:45`
- Function: `validateOrder` (complexity: 14, max: 10)
- **Why**: Functions with many branches are hard to test and prone to bugs.
  Each `if/else` or `switch` case should ideally be tested separately.
- **Fix**: Extract conditional logic into separate functions like `validateItems()`, `validateShipping()`, etc.

**[COMPLEXITY-002] Function too long**

- File: `components/CheckoutForm.tsx:23`
- Function: `handleSubmit` (78 lines, max: 50)
- **Why**: Long functions do too many things. They're hard to understand and test.
- **Fix**: Split into steps: `validateForm()`, `processPayment()`, `handleSuccess()`.

**[COMPLEXITY-003] Duplicate code detected**

- Files: `lib/api/users.ts:15-35` and `lib/api/orders.ts:20-40`
- **Why**: Copy-pasted code means bugs must be fixed in multiple places.
  When one copy is updated, others are often forgotten.
- **Fix**: Extract shared logic into `lib/api/shared/fetchWithAuth.ts`.

---

> Would you like me to fix these automatically? [Yes] [No] [Explain more]

If "Yes": Delegate to `@refactor-cleaner` with specific issues.
If "Explain more": Provide detailed refactoring guidance for each issue.
```

## Step 3.7: Reuse Analysis

Check whether new code duplicates existing patterns. This runs in **all modes** (quick, default, deep).

### Detection

For each **new file** created in this branch (not just modified):

1. Extract the file's primary export (component name, hook name, utility function, API route handler)
2. Search the codebase for similar names and patterns:
   - `grep -rl "SimilarComponentName" src/ app/ lib/ hooks/ components/`
   - Check sibling directories for files with matching naming patterns
3. If a match is found, briefly compare the two implementations for structural overlap

### Checks (Warn, not block)

| Issue | Severity | Example |
|-------|----------|---------|
| New component resembles existing | Warning | `EventModal` is structurally similar to `OutageModal` |
| New hook duplicates existing | Warning | `useEventForm` duplicates logic in `useOutageForm` |
| New utility overlaps existing | Warning | `formatEventDate` is identical to `formatDate` in utils |
| New API route mirrors existing | Warning | `events/route.ts` CRUD pattern duplicates `outages/route.ts` |

### On Finding

Report as warnings (non-blocking):

```markdown
### Reuse Opportunities Found

| New File | Similar To | Overlap | Suggestion |
|----------|-----------|---------|------------|
| `app/events/event-modal.tsx` | `app/outages/outage-modal.tsx` | ~70% structural | Consider extending outage modal |
| `hooks/use-event-form.ts` | `hooks/use-outage-form.ts` | Shared validation | Extract shared form hook |

These are suggestions — review before merging. To prevent this in future plans, use `reuse` and `constraints` fields in plan stories or run `/create-plan --enrich` before execution.
```

### Deep Mode Additions

In `--deep` mode, additionally:
- Compare function signatures across new and existing files
- Flag shared patterns that should be extracted into a common module
- Suggest specific refactoring steps to consolidate duplicated code

## Step 4: Accessibility & Design Audit

Run accessibility/design check based on mode:
- **Default/Quick**: `/rams --quick`
- **Deep**: `/rams` (full audit with serious/moderate issues)

This catches:

- Missing alt text on images
- Icon buttons without aria-label
- Form inputs without labels
- Focus outline removed without replacement
- Non-semantic click handlers (div onClick)
- **Deep mode adds**: Color contrast analysis, keyboard navigation audit, full WCAG 2.1 checks

If critical issues found, report them as blocking issues.

## Step 5: Identify Changed Files

Run:

```bash
git diff --name-only ${BASE_BRANCH}...HEAD
```

Categorize the changes:

- **Source files**: `app/**/*.ts(x)`, `lib/**/*.ts`, `components/**/*.tsx`, `hooks/**/*.ts`
- **Test files**: `__tests__/**/*.test.ts`, `e2e/**/*.spec.ts`
- **Config files**: `*.config.*`, `package.json`
- **Documentation**: `*.md`, `docs/**`

## Step 5.5: Backend Lint (Auto-Detected)

Check if changed files include Python files (`**/*.py`). If no Python files changed, skip this step entirely with no output.

### Python Linter Detection

Detect which linter to use (check in order, use first match):

1. **ruff** — `ruff.toml` exists OR `pyproject.toml` contains `[tool.ruff]`
   → Run: `ruff check [dir]` + `ruff format --check [dir]`
2. **flake8** — `flake8` appears in `requirements.txt` or `requirements-dev.txt`
   → Run: `flake8 [dir]`
3. **pylint** — `.pylintrc` exists
   → Run: `pylint [dir]`
4. **None found** — Skip with warning: "Python files changed but no linter detected (ruff, flake8, or pylint). Consider adding ruff."

### Workspace Detection

Scan for Python workspaces in the repo:

```bash
# Find directories with Python project markers
find . -maxdepth 3 \( -name "ruff.toml" -o -name "pyproject.toml" -o -name "requirements.txt" -o -name "setup.py" \) -not -path "*/node_modules/*" -not -path "*/.venv/*"
```

For each detected workspace, run the linter scoped to that directory. In monorepos (e.g. `apps/api/`), only lint the directories that contain changed `.py` files.

### Scoping to Changed Files

```bash
# Get changed Python files
PY_CHANGED=$(git diff --name-only ${BASE_BRANCH}...HEAD | grep '\.py$')

if [ -z "$PY_CHANGED" ]; then
  echo "No Python files changed — skipping backend lint"
  # Skip this step entirely
fi

# Determine which workspace(s) the changed files belong to
# e.g., apps/api/src/main.py → run linter in apps/api/
```

Run the detected linter scoped to each affected workspace directory.

### Report Format

Use the same table format as other checks:

```markdown
### Backend Lint (ruff)

| Workspace | Check | Status | Details |
|-----------|-------|--------|---------|
| apps/api/ | ruff check | OK | No errors |
| apps/api/ | ruff format | OK | All files formatted |
```

On failure:

```markdown
### Backend Lint (ruff)

| Workspace | Check | Status | Details |
|-----------|-------|--------|---------|
| apps/api/ | ruff check | FAIL | 3 errors |
| apps/api/ | ruff format | WARN | 2 files need formatting |

**Errors:**
- `apps/api/src/routes/users.py:42:1` E302 expected 2 blank lines
- ...
```

**Pass criteria:** Exit code 0 from all linter commands across all workspaces

If fails: List the errors with file locations and suggest fixes. Report as blocking issue.

## Step 5.8: Formatting Check

Run the project formatter on changed files before lint/typecheck:

```bash
# Get changed files that need formatting
CHANGED_FORMAT=$(git diff --name-only ${BASE_BRANCH}...HEAD | grep -E '\.(ts|tsx|js|jsx|json|css|md)$' | tr '\n' ' ')

if [ -n "$CHANGED_FORMAT" ]; then
  npx prettier --check $CHANGED_FORMAT
fi
```

**If formatting fails**: Run `npx prettier --write` on failing files, stage them, and report what was fixed. This prevents lint failures caused by formatting issues.

**Pass criteria:** All changed files pass formatter check.

## Step 6: Run Lint Check

```bash
pnpm lint
```

**Pass criteria:** Exit code 0, no errors (warnings OK)

If fails: List the errors and suggest fixes.

## Step 7: Run Type Check

```bash
pnpm typecheck
```

**Pass criteria:** Exit code 0, no type errors

If fails: List the type errors with file locations.

## Step 8: Run Tests

```bash
pnpm test
```

**Pass criteria:** All tests pass

If fails: Show failing tests and suggest investigation.

**Note:** If user passed `--quick` argument, skip this step and Step 9.

## Step 9: Check Test Coverage for Changed Files

For each changed source file, check if corresponding test file exists:

| Source File                   | Expected Test File                     |
| ----------------------------- | -------------------------------------- |
| `app/api/[resource]/route.ts` | `__tests__/api/[resource].test.ts`     |
| `lib/utils/[name].ts`         | `__tests__/unit/utils/[name].test.ts`  |
| `components/[name].tsx`       | `__tests__/components/[name].test.tsx` |
| `hooks/use-[name].ts`         | `__tests__/hooks/use-[name].test.ts`   |

**Pass criteria:** New source files have corresponding test files, OR existing test files were modified along with source files.

Report which files are missing tests.

## Step 10: Check Documentation (Soft Check - Warnings Only)

Analyze changed files and warn if documentation may need updates:

| Changed Files                | Check For                  | Warning If Missing                         |
| ---------------------------- | -------------------------- | ------------------------------------------ |
| `app/api/**/*.ts` (new)      | `lib/openapi.ts` updated   | ⚠️ New API route may need OpenAPI docs     |
| `app/api/**/*.ts` (modified) | `lib/openapi.ts` touched   | ⚠️ API changes may need OpenAPI updates    |
| `.factory/droids/*.md`       | `AGENTS.md` updated        | ⚠️ New droid should be documented          |
| `.factory/commands/*.md`     | `AGENTS.md` updated        | ⚠️ New command should be documented        |
| `.claude/commands/*.md`      | `AGENTS.md` updated        | ⚠️ New Claude command should be documented |
| `.factory/skills/**`         | `AGENTS.md` updated        | ⚠️ New skill should be documented          |
| `lib/models/*.ts`            | Consider schema docs       | ⚠️ Model changes may need documentation    |
| `.env.example` additions     | `README.md` mentions       | ⚠️ New env vars should be in README        |
| `package.json` scripts       | `README.md` or `AGENTS.md` | ⚠️ New scripts should be documented        |

This is a **SOFT CHECK** - warnings only, does not block PR creation.

## Step 11: Validate OpenAPI Spec (if modified)

If `lib/openapi.ts` was modified:

1. Check TypeScript compiles
2. Verify documented paths correspond to actual routes in `app/api/`
3. Warn about API routes not in OpenAPI spec

## Output Format

Report results in this format:

```markdown
## Pre-PR Check Results

### ✅ Git Hygiene

| Check             | Status | Details                |
| ----------------- | ------ | ---------------------- |
| Branch protection | ✅     | On `feature/user-auth` |
| Branch naming     | ✅     | Follows convention     |
| Commit messages   | ✅     | 5/5 follow format      |
| PR size           | ✅     | 245 lines              |
| Linked issue      | ✅     | Closes #42             |

### ✅ Deslop

Removed 3 unnecessary comments, 1 redundant try/catch.

### ✅ Security

No secrets detected. Dependencies clean.

### ✅ Compliance

TypeScript, React hooks all passing.

### ✅ Code Complexity

No complexity issues found. Functions are well-structured.

### ✅ Accessibility & Design

No critical a11y or design issues found.

### ✅ Backend Lint (ruff)

| Workspace | Check | Status | Details |
|-----------|-------|--------|---------|
| apps/api/ | ruff check | ✅ | No errors |
| apps/api/ | ruff format | ✅ | All files formatted |

_(Skipped if no Python files changed)_

### ✅ Lint

No errors found.

### ✅ Type Check

No type errors.

### ✅ Tests

[X] tests passed ([Y] suites)

### ⚠️ Test Coverage

Missing tests for:

- `lib/utils/new-helper.ts` → Create `__tests__/unit/utils/new-helper.test.ts`

### ⚠️ Documentation (Soft Check)

| Change                          | Suggested Action        |
| ------------------------------- | ----------------------- |
| New: `app/api/widgets/route.ts` | Add to `lib/openapi.ts` |

### ✅ OpenAPI Validation

- [x] documented paths verified
- All routes exist

---

**Summary:** X/14 checks passed, Y warnings (Git Hygiene, Deslop, Security, Compliance, Complexity, A11y, Backend Lint, Lint, Types, Tests, Coverage, Docs, OpenAPI)

**Blocking Issues:**

- [ ] Issue 1
- [ ] Issue 2

**Warnings (non-blocking):**

- [ ] Warning 1
- [ ] Warning 2

Ready to create PR after addressing blocking issues.
```

## Quick Mode

If `--quick` is passed as an argument:

1. **Run git hygiene checks** (always mandatory - cannot skip)
2. Run deslop, security check (quick), compliance check (quick)
3. **Run code complexity check** (always mandatory - cannot skip)
4. Run rams (quick), backend lint (if Python files changed), lint, and typecheck
5. Skip test execution and coverage check
6. Report: "Quick check passed. Run full `/pre-pr-check` to verify tests."

**Note:** Git hygiene and code complexity checks are never skipped, even in quick mode. These are fundamental guardrails for junior developers.

## Deep Mode

If `--deep` is passed as an argument:

1. **Run git hygiene checks** (always mandatory)
2. Run deslop
3. Run **full** `/security-check --base $BASE_BRANCH` (OWASP analysis, auth flow review)
4. Run **full** `/compliance-check` (all skills/rules, DRY analysis)
5. **Run code complexity check** (always mandatory)
6. Run **full** `/rams` (WCAG 2.1 audit, keyboard navigation)
7. Run backend lint (if Python files changed), lint, typecheck, tests, and coverage
8. Report comprehensive results

**When to use `--deep`**:
- Security-sensitive changes (auth, payments, user data)
- Major features or architectural changes
- Before releases or important milestones
- When onboarding new team members (educational value)

## Arguments

- `--quick` - Skip test execution, only run lint and typecheck
- `--deep` - Run full versions of all checks (security, compliance, rams) instead of quick scans
- `--force` - Continue even if checks fail (not recommended)

## Mode Comparison

| Check | `--quick` | Default | `--deep` |
|-------|-----------|---------|----------|
| Git hygiene | Full | Full | Full |
| Deslop | Full | Full | Full |
| Security | `--quick` | `--quick` | **Full** |
| Compliance | `--quick` | `--quick` | **Full** |
| Code complexity | Full | Full | Full |
| RAMS (a11y/design) | `--quick` | `--quick` | **Full** |
| Formatting | Full | Full | Full |
| Backend Lint | Full (if `.py` changed) | Full (if `.py` changed) | Full (if `.py` changed) |
| Lint | Full | Full | Full |
| Typecheck | Full | Full | Full |
| Tests | **Skip** | Full | Full |
| Coverage | **Skip** | Full | Full |

**When to use `--deep`**: Security-sensitive changes (auth, payments, API endpoints), major features, or before important releases.

## Suggested Next

| If... | Run |
|-------|-----|
| All checks pass | `/create-pr` — generate a structured pull request |
| Design issues found | `/design-check --fix` — fix design system violations |
| Security warnings | `/security-check --owasp` — full OWASP Top 10 audit |
