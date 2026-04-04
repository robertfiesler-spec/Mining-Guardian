---
suggest_when:
  - signal: file_extension
    value: ".test.ts"
    min_edits: 1
    cooldown: 30
    message: "Editing tests — `/tdd` structures red-green-refactor cycles"
---
# /tdd - Test-Driven Development Workflow

Drive implementation through strict red-green-refactor cycles with coverage targets.

## Usage

```
/tdd [options]
```

$ARGUMENTS

## Your Task

Guide test-first implementation using the `tdd-guide` agent. Every line of production code must be justified by a failing test.

## Step 1: Define Interfaces

Before writing any tests, establish the contract:

1. **Read the feature/story requirements** from the active plan or user description
2. **Define TypeScript interfaces** for inputs, outputs, and dependencies
3. **Identify boundaries** — what is being tested vs mocked
4. **Confirm with user**: "Here are the interfaces I'll test against. Proceed?"

```typescript
// Example: define the contract before any implementation
interface AuthService {
  login(credentials: LoginCredentials): Promise<AuthResult>;
  logout(token: string): Promise<void>;
}
```

## Step 2: RED — Write Failing Tests

Load the `tdd-guide` agent for strict TDD enforcement.

For each behavior:

1. Write **one** failing test using AAA pattern (Arrange, Act, Assert)
2. Name tests as behavior specs: `"returns error when credentials are invalid"`
3. Run the test — confirm it **fails** for the right reason
4. Do NOT write the next test until this one passes

```bash
# Run the specific test file
pnpm vitest run --reporter=verbose [test-file]
```

**Test quality checklist:**
- Isolated (no shared mutable state)
- Deterministic (same result every run)
- Fast (mock external dependencies)
- Descriptive name (reads like a specification)

## Step 3: GREEN — Minimal Implementation

Write the **minimum** code to make the failing test pass:

1. No extra features, no premature abstractions
2. Hardcode values if that makes the test pass — next tests will force generalization
3. Run the test — confirm it **passes**
4. Run the full suite — confirm no regressions

```bash
# Run full suite after each GREEN step
pnpm vitest run
```

## Step 4: REFACTOR — Clean While Green

With all tests passing, improve code quality:

1. Remove duplication between production code and tests
2. Extract named constants, helper functions
3. Improve naming and readability
4. Run tests after each change — they must stay green
5. Add **no new behavior** during refactor

## Step 5: Repeat Until Complete

Cycle through RED-GREEN-REFACTOR for each behavior. Track progress:

```markdown
### TDD Progress

| Cycle | Behavior | RED | GREEN | REFACTOR |
|-------|----------|-----|-------|----------|
| 1 | [spec] | pass | pass | pass |
| 2 | [spec] | pass | pass | pass |
| 3 | [spec] | ... | ... | ... |
```

## Step 6: Verify Coverage

After all behaviors are implemented:

```bash
pnpm vitest run --coverage
```

**Coverage targets:**
- Statements: 80%+
- Branches: 80%+
- Functions: 80%+
- Lines: 80%+

If coverage is below 80%, identify untested paths and add tests (back to Step 2).

## Step 7: Final Review

1. Run lint and typecheck: `pnpm lint && pnpm typecheck`
2. Verify all tests pass: `pnpm vitest run`
3. Review test names — they should read as a feature specification
4. Confirm no `any` types, no skipped tests, no `.only` left behind

## Output Format

After completion, report:

```markdown
## TDD Complete: [Feature Name]

**Cycles**: [N] red-green-refactor cycles
**Tests**: [N] specs written
**Coverage**: [X]% statements, [X]% branches

### Behaviors Specified
1. [test name] — [file:line]
2. [test name] — [file:line]

### Files Created/Modified
- `src/[file].ts` — implementation
- `__tests__/[file].test.ts` — specs
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--file <path>` | Target file to develop with TDD |
| `--coverage <N>` | Override coverage target (default: 80) |
| `--unit-only` | Skip integration tests, unit only |
| `--from-plan` | Pull next Test story from active plan |

## Related

- **Agent**: `tdd-guide` — loaded automatically for TDD enforcement
- **Skill**: `testing` — mocking, coverage, and test strategy patterns
- `/iterate` — loads tdd-guide for Test-type plan items
- `/verify` — runs lint, typecheck, and test suite

## Suggested Next

| If... | Run |
|-------|-----|
| Tests pass, ready to verify the build | `/verify` — run lint, typecheck, and full test suite |
| Coverage gaps found | Continue `/tdd` cycle — add tests for untested paths |
| Done with feature implementation | `/create-commit` — generate a conventional commit |
