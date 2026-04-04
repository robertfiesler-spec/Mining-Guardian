---
suggest_when:
  - signal: edits_since_commit
    value: 8
    cooldown: 30
    message: "Consider `/create-commit` to checkpoint your work"
---
# Create Commit

Generate a commit message and create a commit.

## Usage

```
/create-commit [options]
```

$ARGUMENTS

## Process

1. **Run pre-commit checks** (test coverage, techdebt, docs)
2. **Identify** files modified in the current session (atomic commits)
3. **Analyze** those changes to understand the work done
4. **Generate** a commit message following conventions
5. **Stage** only session files (not unrelated changes)
6. **Commit** with the generated message

**Atomic Commits**: Only commit work from the current session. If there are pre-existing unstaged changes or untracked files unrelated to the session, leave them uncommitted.

## Step 0: Auto-Run Pre-Commit Check

**AUTOMATICALLY RUN** `/pre-commit-check` before proceeding with commit.

```markdown
## Running Pre-Commit Checks...

[Execute /pre-commit-check internally - do not ask user, just run it]
```

This validates:
- Test coverage for changed files
- No duplicated code / missed abstractions (techdebt)
- Documentation updates if needed
- No console.log statements

**If checks pass:** Continue to Step 1.

**If checks fail:**
1. Show the issues found
2. Ask: "Would you like me to fix these issues?"
3. If yes, run `/pre-commit-check --fix` then retry
4. If no, ask if they want to proceed anyway (not recommended)
5. Do NOT auto-proceed with commit when issues exist

**Skip checks with `--no-verify`:**
```bash
/create-commit --no-verify  # Skips pre-commit checks entirely
```

Only honor `--no-verify` when explicitly provided by the user.

## Step 1: Review Changes

Check git state:

```bash
# Staged changes
git diff --cached --stat

# Unstaged changes
git diff --stat

# Untracked files
git status --short
```

Analyze what changed:

- New files added
- Files modified
- Files deleted
- File types (source, test, config, docs)

## Step 2: Generate Commit Message

Format:

- **First line**: Clear action summary (aim for ~50-72 chars if possible, but clarity > brevity)
- **Blank line**
- **Body**: Detailed bullet points explaining:
  - What was changed and why
  - Breaking changes (if any)
  - Migration notes (if applicable)
  - Related issues/PRs (if any)

### Commit Type Prefixes

| Type       | When to Use                                |
| ---------- | ------------------------------------------ |
| `feat`     | New feature or capability                  |
| `fix`      | Bug fix                                    |
| `refactor` | Code restructuring without behavior change |
| `perf`     | Performance improvement                    |
| `test`     | Adding or updating tests                   |
| `docs`     | Documentation only                         |
| `chore`    | Build, tooling, or maintenance             |
| `style`    | Formatting, whitespace (no code change)    |

### Examples

**Simple feature:**

```
feat(auth): add OAuth2 login with Google

- Implements OAuth2 flow using NextAuth.js
- Adds Google provider configuration
- Creates login button component
```

**Bug fix:**

```
fix(api): handle null response from external service

- Adds null check before parsing response
- Returns empty array instead of crashing
- Fixes #123
```

**Breaking change:**

```
feat(api)!: change response format for /users endpoint

BREAKING CHANGE: Response now returns { data: users[] } instead of users[]

- Wraps response in data object for consistency
- Migration: Update client code to access response.data
```

## Step 3: Stage Files (Atomic Commits)

**Default behavior**: Only stage files that were modified during this session.

```bash
# Stage specific files modified in this session
git add path/to/file1.ts path/to/file2.ts
```

**Identifying session files**:

- Files you created or edited with Write/Edit tools
- Files modified as part of the task the user requested
- NOT: Pre-existing unstaged changes unrelated to the session
- NOT: Untracked files the user didn't ask you to create

**Only use `--all` when**:

- User explicitly requests "commit everything"
- You're certain all changes are related to the current work

## Step 4: Create Commit

```bash
git commit -m "$(cat <<'EOF'
type(scope): summary line

- Bullet point explaining change
- Another bullet point

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

## Plan-Aware Mode

When called with `--plan`, `--item`, and `--progress` flags, append Plan context to the commit message:

```bash
/create-commit --all --plan "user-auth" --item "Create login endpoint" --progress "3/8"
```

Generates:

```
feat(auth): add login API endpoint

- Implements POST /api/auth/login
- Validates credentials against database
- Returns JWT on success

Implements: "Create login endpoint"
Plan: user-auth (3/8 complete)

Co-Authored-By: Claude <noreply@anthropic.com>
```

This mode is automatically used by `/iterate` to maintain traceability between commits and Plan items.

## Output Format

After committing:

```markdown
## Commit Created

**Hash**: `abc1234`
**Message**:
```

feat(component): add loading state to Button

- Adds isLoading prop
- Shows spinner when loading
- Disables button during loading state

```

**Files Changed**: 3
- M `src/components/Button.tsx`
- M `src/components/Button.test.tsx`
- A `src/components/Spinner.tsx`

**Stats**: +45 -12
```

## Arguments

| Argument           | Description                                                  |
| ------------------ | ------------------------------------------------------------ |
| `--all`            | Stage ALL changes (use with caution - breaks atomic commits) |
| `--amend`          | Amend the previous commit (use with caution)                 |
| `--dry-run`        | Show what would be committed without committing              |
| `--scope <name>`   | Override auto-detected scope                                 |
| `--type <type>`    | Override auto-detected commit type                           |
| `--no-verify`      | Skip pre-commit hooks                                        |
| `--plan <name>`    | Plan name for Plan-aware mode                                |
| `--item <text>`    | Checklist item text being implemented                        |
| `--progress <x/y>` | Progress indicator (e.g., "3/8")                             |

## Related Commands

| Command             | Use                                  |
| ------------------- | ------------------------------------ |
| `/iterate`          | Calls this command with Plan context |
| `/pre-pr-check`     | Full validation before PR            |
| `/compliance-check` | Check code against standards         |
| `/create-pr`        | Create pull request after commits    |

## Suggested Next

- `/create-pr` — open pull request after committing
- `/iterate` — continue with next plan item
- `/status` — verify git state after commit
