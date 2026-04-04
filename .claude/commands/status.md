---
suggest_when:
  - signal: edits_since_commit
    value: 10
    cooldown: 30
    message: "Many edits since last commit — `/status` to review progress"
  - signal: total_tool_calls
    value: 25
    cooldown: 30
    message: "Mid-session — `/status` for a quick progress check"
  - signal: session_start
    condition: uncommitted_changes
    message: "Uncommitted changes from a previous session — `/status --history` to see what happened"
  - signal: session_start
    condition: incomplete_plan
    message: "Active plan with pending stories — `/status --history` for a session summary"
---

# Status

Show the current state of checkpoints, git changes, and session info.

## Cost Optimization

**This is a lightweight command.** It only runs git commands and reads checkpoint files. No code analysis or complex reasoning required - consider using `haiku` model if available.

## Your Task

Display a comprehensive status report. Follow these steps:

$ARGUMENTS

## Step 1: List Checkpoints

Find all checkpoint files:

```bash
ls -la .claude/checkpoints/*.md 2>/dev/null
```

For each checkpoint, extract from the filename:

- Timestamp
- Task name

Display as a table:

```markdown
### Checkpoints

| Date       | Time     | Task          | File                               |
| ---------- | -------- | ------------- | ---------------------------------- |
| 2024-01-15 | 14:30:22 | add-user-auth | `20240115-143022-add-user-auth.md` |
```

If no checkpoints exist, show: "No checkpoints found. Run `/project:checkpoint` to create one."

## Step 2: Git Status

Show current git state:

```bash
# Current branch
git branch --show-current

# Uncommitted changes
git status --short

# Commits ahead/behind
git status --branch --short | head -1
```

Display:

```markdown
### Git Status

**Branch**: `feature/my-branch`
**Tracking**: `origin/feature/my-branch` (2 ahead, 0 behind)

**Uncommitted Changes:**

- M `src/file1.ts`
- A `src/file2.ts`
- ?? `src/file3.ts` (untracked)
```

## Step 3: Changed Files Summary

Show files changed compared to main branch:

```bash
git diff --name-only master...HEAD 2>/dev/null || git diff --name-only main...HEAD
```

Categorize by type:

- Source files
- Test files
- Config files
- Documentation

```markdown
### Files Changed (vs master)

**Source (5):**

- `src/components/Button.tsx`
- `src/lib/utils.ts`

**Tests (2):**

- `__tests__/Button.test.tsx`

**Config (1):**

- `package.json`
```

## Step 4: Recent Checkpoint Preview

If checkpoints exist, show a preview of the most recent one:

```markdown
### Latest Checkpoint Preview

**File**: `20240115-143022-add-user-auth.md`
**Status**: in progress

> Task Summary: Implementing user authentication with JWT tokens...

**Pending Items**: 3 items remaining
```

## Output Format

Combine all sections into a single status report:

```markdown
## Project Status

### Checkpoints (3 total)

| Date | Time | Task |
| ---- | ---- | ---- |
| ...  | ...  | ...  |

### Git Status

**Branch**: `feature/xxx`
...

### Files Changed (vs master)

...

### Latest Checkpoint

...

---

**Quick Actions:**

- Run `/project:checkpoint` to save current state
- Run `/project:catchup` to restore from checkpoint
```

## Arguments

- `--checkpoints` - Only show checkpoint list
- `--git` - Only show git status
- `--files` - Only show changed files
- `--verbose` - Show full checkpoint contents instead of preview
- `--history` - Include session history synthesis (sessions, plans, key decisions)
- `--tasks` - Include Tasks API progress in history output
- `--brief` - Minimal history output (last session + next action). Requires `--history`
- `--sessions N` - Number of past sessions to show (default: 3). Requires `--history`

## Step 5: Session History (--history flag only)

Skip this step unless `$ARGUMENTS` contains `--history`.

When `--history` is present, gather and synthesize session history after the standard status sections above.

### 5a. Session State & Archive

Read `.ai/memory/session-state.json` for the last session's branch, files, tasks, timestamp.

List files in `.ai/memory/sessions/` (most recent first). Read the top N archives (default 3, or value from `--sessions`).

Each archive JSON contains:
- `timestamp`, `branch`, `last_files`, `uncommitted`
- `commits_made` — array of one-line commit summaries
- `task_progress` — `{ total, completed, planName, nextStory }`
- `active_task`, `todos`
- `session_duration_estimate_ms`

### 5b. Active Plans

Read plan files from `docs/plans/` (JSON or Markdown). For each plan:
- Count total stories vs completed (`passes: true`)
- Identify the next incomplete story

### 5c. Checkpoints & Decisions

List `.ai/memory/checkpoints/` — read the 2 most recent checkpoint files for key decisions and pending items.

### 5d. Session Summary

Read `.ai/memory/session-summary.md` if it exists.

### 5e. Tasks API (--tasks flag only)

If `$ARGUMENTS` also contains `--tasks`:
```
TaskList -> group by status (completed, in_progress, pending)
```
If Tasks API is unavailable, skip gracefully.

### 5f. Synthesize

Combine all data into additional sections appended after the standard status output:

```markdown
### Recent Sessions
- **[date, relative time]**: [1-2 sentence summary from commits + task progress]
- **[date, relative time]**: [summary]

### Active Plan: [name] ([completed]/[total] stories)
**Next up**: [next incomplete story title]
**Progress**: [visual progress bar or fraction]

### Key Decisions (from checkpoints)
- [Decision 1 — brief summary]
- [Decision 2 — brief summary]
```

### Brief Mode (--history --brief)

If both `--history` and `--brief` are present, replace the full history synthesis with:

```markdown
**Last session**: [1-sentence summary]
**Next**: [single suggested action]
```

### After History Output

Present the summary, then ask:

> Ready to continue? You can:
> - `/iterate` to resume the active plan
> - `/remind` for current session context
> - Ask me anything about the project state

Do NOT take actions until the user responds.

## Suggested Next

| If... | Run |
|-------|-----|
| Uncommitted work to save | `/create-commit` — generate a conventional commit |
| Plan items pending | `/iterate` — execute plan items in batches |
| Long session, save checkpoint | `/checkpoint` — save session progress for later recovery |
| Need full session history | `/status --history` — synthesize past sessions and plans |
