---
suggest_when:
  - signal: file_extension
    value: ".ts"
    min_edits: 5
    cooldown: 20
    message: "Verify changes with `/verify`"
---
# Verify

Quick verification of code quality: lint, typecheck, and tests.

## Cost Optimization

**Base command is lightweight** - runs existing tooling and reports results. The `--visual` flag adds browser automation which increases cost. Use `--visual` only when testing UI changes.

## Your Task

Run verification checks and report results. This is a lightweight alternative to `/pre-pr-check`.

$ARGUMENTS

## Step 0: Detect Flags

Check `$ARGUMENTS` for flags. If **no flags detected**, check recent edits and suggest:

- If recent edits include `.tsx` or `.css` files → suggest: _"You've been editing UI files. Add `--visual` to catch rendering issues?"_
- If this is a quick sanity check → proceed with defaults (no prompt needed)
- If user said "everything" or "full" → apply `--all`

Available modes (no need to prompt if context is clear):

| Flag | When to suggest |
|------|----------------|
| `--visual [url]` | UI/styling changes — adds browser screenshot + a11y check |
| `--all` | Want full report even if early checks fail |
| `--fix` | Lint errors — auto-fix before reporting |
| `--strict` | With `--visual` — fail on visual regression |
| `--lint-only` / `--types-only` / `--tests-only` | Only need one specific check |

If the intent is clear from context, skip the prompt and proceed.

## Verification Steps

Run these checks in sequence. Stop on first error unless `--all` is passed.

### 1. Lint Check

```bash
pnpm lint
```

**Pass**: Exit code 0 (warnings are OK)
**Fail**: Any errors reported

### 1.5. Backend Lint (Auto-Detected)

Skip this step entirely if no Python project markers are found in the repo.

If the project contains Python files and a supported linter is detected, run it:

**Detection order** (use first match):

1. `ruff.toml` exists OR `pyproject.toml` contains `[tool.ruff]` → `ruff check [dir] && ruff format --check [dir]`
2. `flake8` in `requirements.txt` or `requirements-dev.txt` → `flake8 [dir]`
3. `.pylintrc` exists → `pylint [dir]`
4. No linter found → skip with warning: "Python files found but no linter detected. Consider adding ruff."

Run scoped to each Python workspace directory (e.g., `cd apps/api && ruff check .`). In monorepos, detect workspaces by scanning for `ruff.toml`, `pyproject.toml`, `requirements.txt`, or `setup.py` up to 3 levels deep.

**Pass**: Exit code 0 from all linter commands
**Fail**: Any lint errors reported

### 2. Type Check

```bash
pnpm typecheck
```

**Pass**: Exit code 0
**Fail**: Any type errors

### 3. Test Suite

```bash
pnpm test
```

**Pass**: All tests pass
**Fail**: Any test failures

### 4. Visual Check (with `--visual`)

If `--visual` flag is provided, run browser-based visual verification:

```bash
.claude/scripts/browser-verify.sh $URL
```

**Default URL**: `http://localhost:3000` (or `DEV_SERVER_URL` if set)
**Custom URL**: Pass URL after `--visual` flag (e.g., `--visual http://localhost:3000/dashboard`)

**Pass**: Screenshot captured, no accessibility issues
**Warn**: Visual changes detected (soft failure unless `--strict`)
**Fail**: Browser verification error

## Output Format

### All Passing

```markdown
## Verify: PASS

| Check        | Status         | Time  |
| ------------ | -------------- | ----- |
| Lint         | OK             | 2.1s  |
| Backend Lint | OK (ruff)      | 1.0s  |
| Typecheck    | OK             | 4.3s  |
| Tests        | OK (47 passed) | 12.5s |
| Visual       | OK             | 3.2s  |

Ready to commit or continue.

Note: Visual check only appears when `--visual` flag is used.
Note: Backend Lint only appears when Python project markers are detected.
```

### With Failures

```markdown
## Verify: FAIL

| Check        | Status  | Time |
| ------------ | ------- | ---- |
| Lint         | OK      | 2.1s |
| Backend Lint | OK      | 1.0s |
| Typecheck    | FAIL    | 4.3s |
| Tests        | SKIPPED | -    |

### Errors

**Typecheck** (3 errors):
```

src/lib/utils.ts:42:5 - error TS2322: Type 'string' is not assignable to type 'number'.
src/lib/utils.ts:58:12 - error TS2339: Property 'foo' does not exist on type 'Bar'.
src/components/Button.tsx:15:3 - error TS2741: Property 'onClick' is missing.

```

### Suggested Fixes

1. `src/lib/utils.ts:42` - Change return type or fix the returned value
2. ...
```

## Behavior

- **Default**: Stop on first failure (fail-fast)
- **With `--all`**: Run all checks even if earlier ones fail
- **With `--fix`**: Attempt to auto-fix lint issues before reporting

## Arguments

- `--all` - Run all checks even if one fails
- `--fix` - Auto-fix lint issues (`pnpm lint --fix`)
- `--lint-only` - Only run lint check
- `--types-only` - Only run typecheck
- `--tests-only` - Only run tests
- `--quiet` - Minimal output, just pass/fail
- `--visual [url]` - Add browser-based visual verification (default: localhost:3000)
- `--strict` - Fail on visual regression (with `--visual`)

## Visual Verification

When `--visual` is passed:

1. Code checks run first (lint, typecheck, tests)
2. If code checks pass, visual verification runs
3. Captures screenshot and accessibility snapshot
4. Reports visual findings alongside code results

```bash
# Verify with visual check on default URL
/verify --visual

# Verify specific route
/verify --visual http://localhost:3000/dashboard

# Strict mode - fail on visual regression
/verify --visual --strict
```

See `/verify-visual` for standalone visual verification.

## Suggested Next

| If... | Run |
|-------|-----|
| All checks pass, ready to commit | `/create-commit` — generate a conventional commit |
| Visual issues suspected | `/verify-visual` — browser-based screenshot and a11y check |
| Failures need debugging | `/debug` — hypothesis-driven debugging workflow |
