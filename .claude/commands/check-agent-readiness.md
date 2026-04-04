---
suggest_when:
  - signal: session_start
    condition: no_agent_context
    message: "No agent context file found — run `/check-agent-readiness` to audit this repo"
---
# Check Agent Readiness

Audit a repository's readiness for autonomous AI agent execution. Checks 7 dimensions of infrastructure that agents need to work reliably: type safety, tests, formatting, linting, CI, agent context, and git hygiene.

## Usage

```
/check-agent-readiness [options]
```

Options:
- `--fix` — Bootstrap missing infrastructure with confirmation prompts
- `--json` — Output machine-readable JSON results

$ARGUMENTS

## Step 1: Detect Stack

Determine the project's language/framework stack by checking for marker files:

```bash
# Check in priority order
if [ -f "package.json" ]; then
  echo "STACK: node"
elif [ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "requirements.txt" ]; then
  echo "STACK: python"
elif [ -f "Cargo.toml" ]; then
  echo "STACK: rust"
elif [ -f "go.mod" ]; then
  echo "STACK: go"
elif [ -f "Makefile" ]; then
  echo "STACK: make"
else
  echo "STACK: unknown"
fi
```

For **Node** projects, also parse `package.json` to extract:
- `scripts` object (for detecting test/lint/typecheck/format commands)
- `dependencies` and `devDependencies` (for detecting installed tools)

Store detected stack and parsed data for use in subsequent steps.

## Step 2: Check Type Safety (Weight: 15)

Determine if the project has a type checking system configured.

| Stack | Pass | Warn | Fail |
|-------|------|------|------|
| **Node** | `tsconfig.json` exists AND (`typecheck`/`type-check`/`tsc` script in package.json OR `typescript` in devDeps) | `tsconfig.json` exists but no typecheck script | Neither found |
| **Python** | `mypy` or `pyright` in deps/devDeps AND config file (`mypy.ini`, `pyrightconfig.json`, or `[tool.mypy]` in `pyproject.toml`) | Tool in deps but no config | Neither found |
| **Rust** | Always pass (compiler enforces types) | — | — |
| **Go** | Always pass (compiler enforces types) | — | — |
| **Unknown** | `tsconfig.json` or type checker config found | — | No type checking detected |

**Detail string examples:**
- Pass: `"TypeScript configured with typecheck script"`
- Warn: `"tsconfig.json found but no typecheck script in package.json"`
- Fail: `"No type checking configured"`

## Step 3: Check Test Infrastructure (Weight: 20)

Determine if the project has a test runner and tests.

| Stack | Pass | Warn | Fail |
|-------|------|------|------|
| **Node** | `test` script in package.json AND test config file (`vitest.config.*`, `jest.config.*`, `.mocharc.*`) AND at least one `*.test.*` or `*.spec.*` file found | `test` script exists but no test files found, OR test files exist but no `test` script | Neither test script nor test files |
| **Python** | `pytest` in deps AND `tests/` or `test_*.py` files exist | `pytest` in deps but no test files, or test files but no pytest | No test infrastructure |
| **Rust** | `#[test]` or `tests/` directory found (cargo test is built-in) | — | No test files found |
| **Go** | `*_test.go` files found (go test is built-in) | — | No test files found |
| **Unknown** | Any test config or test files found | — | No test infrastructure detected |

To check for test files, use glob patterns:
```bash
# Node
find . -name "*.test.*" -o -name "*.spec.*" | head -5

# Python
find . -name "test_*.py" -o -name "*_test.py" | head -5

# Go
find . -name "*_test.go" | head -5
```

## Step 4: Check Formatter (Weight: 10)

Determine if a code formatter is configured.

| Stack | Pass | Warn | Fail |
|-------|------|------|------|
| **Node** | `prettier` or `biome` in devDeps AND config file (`.prettierrc*`, `biome.json`, `.editorconfig`) AND `format` or `format:check` script | Tool in devDeps but no format script | No formatter detected |
| **Python** | `black` or `ruff` in deps AND config in `pyproject.toml` | Tool in deps but no config | No formatter detected |
| **Rust** | `rustfmt.toml` or `.rustfmt.toml` found (rustfmt is built-in) | — | Custom config missing (still has default rustfmt) |
| **Go** | Always pass (gofmt is built-in and standard) | — | — |
| **Unknown** | Any formatter config found | — | No formatter detected |

## Step 5: Check Linter (Weight: 10)

Determine if a linter is configured.

| Stack | Pass | Warn | Fail |
|-------|------|------|------|
| **Node** | `eslint` or `biome` in devDeps AND `lint` script in package.json AND config file (`.eslintrc*`, `eslint.config.*`, `biome.json`) | Tool in devDeps but no lint script | No linter detected |
| **Python** | `ruff`, `flake8`, or `pylint` in deps AND config present | Tool in deps but no config | No linter detected |
| **Rust** | Always pass (clippy is built-in with cargo) | — | — |
| **Go** | `golangci-lint` config (`.golangci.yml`) found | — | No linter config (go vet is built-in but limited) |
| **Unknown** | Any linter config found | — | No linter detected |

## Step 6: Check CI Pipeline (Weight: 15)

Check for continuous integration configuration.

Look for these files:
```bash
# Check common CI config locations
ls .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null
ls .gitlab-ci.yml 2>/dev/null
ls .circleci/config.yml 2>/dev/null
ls Jenkinsfile 2>/dev/null
ls .travis.yml 2>/dev/null
ls bitbucket-pipelines.yml 2>/dev/null
```

| Status | Condition |
|--------|-----------|
| **Pass** | At least one CI config file found AND it references test/lint/typecheck steps |
| **Warn** | CI config found but minimal (no test/lint steps detected) |
| **Fail** | No CI configuration found |

If CI config is found, spot-check the content for keywords like `test`, `lint`, `typecheck`, `tsc`, `check` to determine if it's substantive.

## Step 7: Check Agent Context File (Weight: 20)

Check for files that tell agents how to work in this project.

```bash
# Check for agent context files
ls CLAUDE.md .claude/CLAUDE.md AGENTS.md AGENTS.json .github/copilot-instructions.md CONVENTIONS.md 2>/dev/null
```

| Status | Condition |
|--------|-----------|
| **Pass** | `CLAUDE.md` or `AGENTS.md` found AND contains build/test/lint commands section |
| **Warn** | Context file found but missing build commands (agents won't know how to verify) |
| **Fail** | No agent context file found |

To spot-check for build commands, look for keywords like `build`, `test`, `lint`, `dev`, `npm run`, `cargo`, `go build`, `make` in the context file.

## Step 8: Check Git Hygiene (Weight: 10)

Check the state of the working tree.

```bash
git status --porcelain 2>/dev/null
```

| Status | Condition |
|--------|-----------|
| **Pass** | Working tree clean (no output) |
| **Warn** | Only untracked files (lines starting with `??`) |
| **Fail** | Modified/staged files present (dirty working tree) |

## Step 9: Calculate Score and Generate Report

### Scoring

Calculate the weighted score:

```
For each dimension:
  pass  = full weight points
  warn  = half weight points (rounded down)
  fail  = 0 points

Total Score = sum of all dimension scores
Max Score   = sum of all weights (100)
Percentage  = (Total Score / Max Score) * 100
```

### Grade Scale

| Score | Grade | Level |
|-------|-------|-------|
| 90-100 | A | Fully Ready |
| 75-89 | B | Ready |
| 60-74 | C | Ready with Caveats |
| 45-59 | D | Not Recommended |
| 0-44 | F | Not Ready |

### Report Output (Default)

Output a structured report:

```
## Agent Readiness Report

**Project:** {project name from package.json or directory name}
**Stack:** {detected stack}
**Score:** {score}/100 ({grade} — {level})

### Dimensions

| Dimension | Status | Score | Detail |
|-----------|--------|-------|--------|
| Type Safety | ✅/⚠️/❌ | {n}/15 | {detail string} |
| Test Infrastructure | ✅/⚠️/❌ | {n}/20 | {detail string} |
| Formatter | ✅/⚠️/❌ | {n}/10 | {detail string} |
| Linter | ✅/⚠️/❌ | {n}/10 | {detail string} |
| CI Pipeline | ✅/⚠️/❌ | {n}/15 | {detail string} |
| Agent Context | ✅/⚠️/❌ | {n}/20 | {detail string} |
| Git Hygiene | ✅/⚠️/❌ | {n}/10 | {detail string} |

### Blockers

{List any dimension with ❌ status — these should be fixed before trusting agents}

### Recommendations

{For each ⚠️ or ❌ dimension, one actionable sentence}
```

### JSON Output (`--json`)

When `--json` flag is present, output ONLY valid JSON (no markdown):

```json
{
  "project": "my-project",
  "stack": "node",
  "score": 75,
  "maxScore": 100,
  "grade": "B",
  "level": "Ready",
  "ready": true,
  "dimensions": [
    {
      "name": "Type Safety",
      "status": "pass",
      "score": 15,
      "maxScore": 15,
      "detail": "TypeScript configured with typecheck script"
    }
  ],
  "blockers": [
    {
      "dimension": "CI Pipeline",
      "detail": "No CI configuration found",
      "fix": "Add .github/workflows/ci.yml"
    }
  ]
}
```

The `ready` field is `true` when score >= 60 (grade C or better).

## Step 10: Bootstrap Missing Infrastructure (`--fix`)

**Only execute this step when the `--fix` flag is present.**

For each dimension with ⚠️ or ❌ status, propose a fix. Show the proposed change and ask for confirmation before applying.

### Fix Actions by Dimension

**Type Safety (Node):**
- If `tsconfig.json` exists but no script: Add `"typecheck": "tsc --noEmit"` to package.json scripts
- If neither: Suggest `npm install -D typescript` and scaffold a basic `tsconfig.json`

**Type Safety (Python):**
- Suggest `pip install mypy` or adding to pyproject.toml dev dependencies

**Test Infrastructure (Node):**
- If no test runner: Suggest `npm install -D vitest` and create `vitest.config.ts`
- If no test files: Create a sample `src/__tests__/example.test.ts` with a placeholder test
- If no test script: Add `"test": "vitest run"` to package.json scripts

**Test Infrastructure (Python):**
- Suggest `pip install pytest` and create `tests/test_example.py`

**Formatter (Node):**
- Suggest `npm install -D prettier` and create `.prettierrc` with sensible defaults
- Add `"format": "prettier --write ."` and `"format:check": "prettier --check ."` scripts

**Formatter (Python):**
- Suggest adding `ruff` to dev dependencies

**Linter (Node):**
- Suggest `npm install -D eslint` and create `eslint.config.js`
- Add `"lint": "eslint ."` script

**Linter (Python):**
- Suggest adding `ruff` to dev dependencies (covers both formatting and linting)

**CI Pipeline:**
- Scaffold `.github/workflows/ci.yml` with steps for lint, typecheck, and test based on detected stack:

For **Node**:
```yaml
name: CI
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm test
```

For **Python**:
```yaml
name: CI
on: [push, pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: mypy .
      - run: pytest
```

**Agent Context:**
- Delegate to `/init` command to generate a CLAUDE.md file

**Git Hygiene:**
- If dirty: Suggest `git stash` to clean working tree, or `git add -A && git commit` to commit changes
- If untracked only: Suggest reviewing untracked files and either committing or adding to `.gitignore`

### Fix Workflow

For each fix:
1. Show what will be created/modified
2. Ask "Apply this fix? (y/n)"
3. Only apply on confirmation
4. After all fixes, re-run the score calculation and show updated report

## Suggested Next

| Situation | Command |
|-----------|---------|
| Score < 60 and `--fix` not used | Re-run with `--fix` to bootstrap infrastructure |
| No CLAUDE.md found | `/init` to generate project context file |
| All dimensions pass | `/create-plan` to start building features |
| Tests missing | `/tdd` to write tests first |
| Pre-PR validation needed | `/pre-pr-check` for full validation suite |
