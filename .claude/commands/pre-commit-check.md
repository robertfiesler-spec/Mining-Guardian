---
suggest_when:
  - signal: edits_since_commit
    value: 5
    cooldown: 30
    message: "Ready to commit? `/pre-commit-check` verifies coverage, techdebt, and docs first"
  - signal: file_extension
    value: ".ts"
    min_edits: 4
    cooldown: 30
    message: "TypeScript changes ready — `/pre-commit-check` before committing"
---

# Pre-Commit Check

Verify test coverage, techdebt, and documentation before committing changes.

## Your Task

Run comprehensive pre-commit validation on changed files:
1. **Test coverage** - Ensure new code has corresponding tests
2. **Tech debt** - Find duplicated code and missed abstractions
3. **Documentation** - Check if docs need updating
4. **Code quality** - No console.logs, proper exports

This command is **required before `/create-commit`** (unless `--no-verify` is used).

$ARGUMENTS

## Step 0: Detect Base Branch

```bash
BASE_BRANCH=""
if git rev-parse --verify origin/staging >/dev/null 2>&1; then
  BASE_BRANCH="origin/staging"
elif git rev-parse --verify origin/master >/dev/null 2>&1; then
  BASE_BRANCH="origin/master"
elif git rev-parse --verify origin/main >/dev/null 2>&1; then
  BASE_BRANCH="origin/main"
fi
echo "Comparing against: $BASE_BRANCH"
```

## Step 1: Identify Changed Files

Get list of changed source files (excluding tests):

```bash
git diff --name-only ${BASE_BRANCH}...HEAD | grep -E '\.(ts|tsx)$' | grep -v '\.test\.' | grep -v '\.spec\.'
```

Categorize changes:
- **New files**: Files that don't exist in base branch
- **Modified files**: Files that exist in both but have changes
- **API routes**: Files in `app/api/`
- **Hooks**: Files in `hooks/`
- **Lib functions**: Files in `lib/`
- **Components**: Files in `components/`

## Step 1.5: Formatting Check

Run the project formatter on changed files before any other analysis:

```bash
# Detect formatter (check in order)
if command -v prettier &>/dev/null || [ -f "node_modules/.bin/prettier" ]; then
  npx prettier --check $(git diff --name-only ${BASE_BRANCH}...HEAD | grep -E '\.(ts|tsx|js|jsx|json|css|md)$' | tr '\n' ' ')
elif [ -f "ruff.toml" ] || grep -q '\[tool.ruff\]' pyproject.toml 2>/dev/null; then
  ruff format --check $(git diff --name-only ${BASE_BRANCH}...HEAD | grep '\.py$' | tr '\n' ' ')
fi
```

**If formatting fails**: Run the formatter with `--write` to fix, then re-stage the files. Report what was fixed.

## Step 2: Test Coverage Analysis

For each category of changed files, check for corresponding tests:

| Source Location | Expected Test Location |
|-----------------|----------------------|
| `lib/[module]/[name].ts` | `__tests__/unit/[module]/[name].test.ts` |
| `lib/utils/[name].ts` | `__tests__/unit/utils/[name].test.ts` |
| `hooks/use-[name].ts` | `__tests__/hooks/use-[name].test.ts` |
| `app/api/[...path]/route.ts` | `__tests__/api/[...path].test.ts` |
| `components/[name].tsx` | `__tests__/components/[name].test.tsx` |

### Check Process

1. For each new/modified source file:
   - Check if a corresponding test file exists
   - If test file exists, check if it was also modified (tests updated with code)
   - For new exported functions, verify they have test coverage

2. For critical modules (auth, payments, data mutations), require 100% function coverage

### Report Missing Tests

```markdown
### Test Coverage

| File | Status | Action Needed |
|------|--------|---------------|
| `lib/shipping/providers/uber-freight.ts` | ⚠️ | Missing tests for `tenderLtlLoad()` |
| `hooks/use-purchase-label.ts` | ❌ | No test file exists |
```

## Step 3: Documentation Analysis

Check if documentation needs updating based on changes:

### 3.1: README Updates

If any of these changed, README may need updates:

| Change Type | README Section |
|-------------|----------------|
| New feature in `app/` | Features list |
| New API routes | API documentation |
| New environment variables | Environment Variables section |
| New scripts in `package.json` | Available Scripts section |

### 3.2: Plan File Status

If `docs/plans/` contains plan files:

1. Check if plan items match implemented code
2. Verify completed items are marked `[x]`
3. Suggest archiving completed plans

```bash
# Find active plan files
find docs/plans -maxdepth 1 -name "*.md" -not -path "*/archive/*"
```

### 3.3: Architecture Docs

If changes affect:
- Database models → Check `docs/architecture/data-flow.md`
- External integrations → Check `docs/architecture/external-services.md`
- System design → Check `docs/architecture/system-overview.md`

## Step 4: Export Analysis

For new/modified TypeScript files, identify exported functions that lack tests:

```bash
# Find exports in changed files
grep -E "^export (async )?function|^export const" <file>
```

Cross-reference with test files to find untested exports.

## Step 5: Tech Debt Analysis

**Run `/techdebt --staged`** to check for duplicated code in staged files.

```markdown
Running tech debt analysis on staged files...
```

This delegates to the `/techdebt` command which checks for:
- Inline reimplementations of existing utilities
- Redundant new helpers that duplicate existing ones
- Extraction opportunities (repeated code patterns)

Include the `/techdebt` results in the final report under "### ⚠️ Tech Debt".

## Step 6: Generate Report

Output a structured report:

```markdown
## Pre-Commit Check Results

### ✅ Test Coverage

| Category | Files | Tested | Coverage |
|----------|-------|--------|----------|
| Lib functions | 5 | 4 | 80% |
| Hooks | 3 | 1 | 33% |
| API routes | 4 | 2 | 50% |
| Components | 2 | 2 | 100% |

### ⚠️ Missing Tests

| File | Untested Exports |
|------|------------------|
| `lib/shipping/providers/uber-freight.ts` | `tenderLtlLoad()` |
| `hooks/use-purchase-label.ts` | entire file |

### ⚠️ Documentation Gaps

| Change | Suggested Update |
|--------|------------------|
| New shipping feature | Add to README Features section |
| New env vars (UBER_FREIGHT_*) | Add to README Environment Variables |

### ⚠️ Plan Files

| Plan | Status | Action |
|------|--------|--------|
| `ltl-tender-purchase.md` | 7/7 complete | Archive to `docs/plans/archive/` |

---

**Summary:** X issues found

**Blocking (must fix before commit):**
- [ ] Critical function `tenderLtlLoad()` has no tests

**Warnings (should fix):**
- [ ] 2 hooks missing test files
- [ ] README needs shipping section
- [ ] Plan file should be archived
```

## Step 7: Token Budget Check

Check that toolkit component file sizes are within configured token budgets. This prevents context bloat as the toolkit grows.

```bash
# Detect script location
if [ -f ".claude/scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT=".claude/scripts/token-budget.sh"
elif [ -f "$HOME/.claude/scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT="$HOME/.claude/scripts/token-budget.sh"
elif [ -f "./scripts/token-budget.sh" ]; then
  BUDGET_SCRIPT="./scripts/token-budget.sh"
fi

if [ -n "$BUDGET_SCRIPT" ]; then
  "$BUDGET_SCRIPT" --check
fi
```

If budget violations are found, include them in the report:

```markdown
### Token Budget

| Component | Tokens | Budget | Status |
|-----------|--------|--------|--------|
| commands/iterate.md | 7,335 | 8,000 | WARN |
```

**Severity**: Warnings are non-blocking. Failures (exceeding `failAtPercent`) are blocking.

For the full report, suggest: `./scripts/token-budget.sh --report`

## Step 8: Eval Gate (Auto-Detected)

This step only runs if the project has an `evals/` directory. Standard projects without evals skip this entirely.

### 8.1: Detect Eval Infrastructure

```bash
EVAL_DIR=""
if [ -d "evals/scripts" ]; then
  EVAL_DIR="evals"
elif [ -d ".claude/evals/scripts" ]; then
  EVAL_DIR=".claude/evals"
fi
```

If `EVAL_DIR` is empty, skip to Step 9.

### 8.2: Run Automated Eval Checks

If `$EVAL_DIR/scripts/run-evals.sh` exists, run it:

```bash
"$EVAL_DIR/scripts/run-evals.sh"
```

This runs all automated suites (token budgets, decision rule consistency, cross-references, scenario structure). Capture pass/fail counts from the output.

If `$EVAL_DIR/scripts/measure-tokens.sh` exists AND a baseline exists at `$EVAL_DIR/baselines/token-baseline.json`, also run token comparison:

```bash
"$EVAL_DIR/scripts/measure-tokens.sh" --compare
```

Report automated results:

```markdown
### Eval Gate

**Automated Checks:**

| Suite | Passed | Failed |
|-------|--------|--------|
| Token Budget Compliance | 4 | 0 |
| Decision Rule Consistency | 6 | 0 |
| Scenario Structure | 9 | 0 |
| Cross-References | 2 | 0 |

**Token Comparison vs Baseline:**

| Section | Before | After | Delta |
|---------|--------|-------|-------|
| Context Management | 120 | 125 | +5 |
| Available Commands | 890 | 920 | +30 |
```

Automated failures are **blocking** — they must be fixed before committing.

### 8.3: Surface Behavioral Scenarios for Human Review

Determine which scenarios are relevant by checking which files changed:

```bash
# Get changed files
CHANGED=$(git diff --name-only HEAD 2>/dev/null || git diff --name-only --cached)

# Map changed files to scenario directories
RELEVANT_SCENARIOS=()

# Rules/CLAUDE.md changes → check scenarios that test those rules
for scenario_dir in "$EVAL_DIR"/scenarios/*/; do
  [ -d "$scenario_dir" ] || continue
  dir_name=$(basename "$scenario_dir")

  # Match scenarios to changed files by convention:
  # - evals/scenarios/context-management/ ↔ rules/agents.md, CLAUDE.md "Context Management"
  # - evals/scenarios/<topic>/ ↔ rules/<topic>.md, commands/<topic>.md
  # If ANY rule, command, agent, or CLAUDE.md changed, surface ALL scenarios
  if echo "$CHANGED" | grep -qE "^(rules/|commands/|agents/|CLAUDE\.md|evals/)"; then
    for scenario in "$scenario_dir"*.md; do
      [ -f "$scenario" ] && RELEVANT_SCENARIOS+=("$scenario")
    done
  fi
done
```

If relevant scenarios exist, present them as a human review checklist:

```markdown
**Behavioral Scenarios (Human Review Required):**

The following scenarios should be verified in a fresh session before merging changes to rules, commands, or agent definitions. These cannot be tested automatically — they require observing Claude's actual behavior.

| # | Scenario | Tests | File |
|---|----------|-------|------|
| 1 | Codebase Exploration | Agent delegation on 3+ file reads | `evals/scenarios/context-management/scenario-exploration.md` |
| 2 | Direct Edit | Stay in main for single file edits | `evals/scenarios/context-management/scenario-direct-edit.md` |
| 3 | Mixed Task | Research + edit combined workflow | `evals/scenarios/context-management/scenario-mixed-task.md` |

**For each scenario, verify:**
- [ ] Expected behavior matches (checked in fresh session)
- [ ] No anti-patterns observed
- [ ] Quality criteria met

Have you verified the relevant behavioral scenarios? (yes/skip/details)
```

- If user says **"yes"** → pass, continue to Step 9
- If user says **"skip"** → log as skipped in report, continue (non-blocking but noted)
- If user says **"details"** → read and display each relevant scenario file so they can review the expected behaviors inline

### 8.4: Include in Report

Add eval results to the final report:

```markdown
### Eval Gate

- **Automated**: X/Y passed (Z failed) [PASS/FAIL]
- **Token regression**: [none detected / +N tokens in Section X]
- **Behavioral scenarios**: [verified / skipped / N/A]
```

If no `evals/` directory was found, this section does not appear in the report.

---

## Step 9: Offer Fixes

If issues are found, offer to help:

1. **Missing tests**: "Would you like me to create tests for `tenderLtlLoad()`?"
2. **Documentation gaps**: "Would you like me to add a shipping section to README?"
3. **Plan cleanup**: "Would you like me to archive the completed plan?"

## Arguments

- `--quick` - Only check test coverage, skip documentation analysis
- `--fix` - Automatically fix issues (create missing tests, update docs)
- `--strict` - Treat warnings as errors (block commit)

## Integration with Git Hooks

This command can be integrated as a pre-commit hook:

```bash
# .husky/pre-commit
claude "/pre-commit-check --strict"
```

## Examples

### Basic usage
```
/pre-commit-check
```

### Quick mode (tests only)
```
/pre-commit-check --quick
```

### Auto-fix mode
```
/pre-commit-check --fix
```

## Suggested Next

- `/create-commit` — commit after all checks pass
- `/deslop` — remove AI artifacts if deslop check flags issues
- `/verify` — lighter-weight alternative (lint, typecheck, tests only)
