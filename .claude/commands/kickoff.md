---
suggest_when:
  - signal: session_start
    condition: no_agent_context
    message: "No project context loaded — run `/kickoff` to initialize the session"
---

# Kickoff

Initialize a new Claude session by reading all project workflow context.

## Your Task

Read and internalize the Document & Clear workflow for this project. This is the FIRST command to run in any new session.

$ARGUMENTS

## Step 1: Read Core Documentation

Read these files to understand the project workflow:

```
CLAUDE.md                           # Primary workflow documentation
.claude/commands/create-plan.md     # How to create Plans
.claude/commands/iterate.md         # How to execute with document & clear
.claude/commands/checkpoint.md      # How to save state
.claude/commands/catchup.md         # How to restore state
```

Internalize:

- The Document & Clear loop
- Adaptive batching rules
- Commit conventions
- When and how to checkpoint

## Step 2: Check Current State

### Active Plan

```bash
ls -t docs/plans/*.md 2>/dev/null | head -1
```

If a Plan exists:

1. Read it fully
2. Extract the branch name from `**Branch**: <branch-name>` in the plan header
3. **Check if branch was merged** (stale plan detection):

```bash
# Check if the plan's branch exists and if it was merged to main
PLAN_BRANCH="<extracted-branch-name>"
git branch -a --merged main 2>/dev/null | grep -q "$PLAN_BRANCH" && echo "MERGED"
```

4. If branch was merged → **Plan is stale**:
   - Report: "⚠️ Plan `<filename>` appears complete (branch `<branch>` was merged to main)"
   - Offer to archive: "Run `mv docs/plans/<file> docs/plans/archive/` to archive, or delete it"
   - Do NOT suggest continuing work on this plan

5. If branch exists and not merged → Plan is active:
   - Note which items are complete vs pending
   - Identify where work left off

### Recent Checkpoints

```bash
ls -t .ai/memory/checkpoints/*.md 2>/dev/null | head -3
```

If checkpoints exist:

- Read the most recent one
- Note the last completed item
- Review any context notes

### Pyramid Summaries

```bash
ls .claude/pyramid/L1-overview.md 2>/dev/null
```

If pyramid summaries exist:
- Read L1 (`L1-overview.md`) for project orientation
- Report staleness by comparing `.pyramid-meta.json` git SHA to current HEAD
- If 50+ commits stale: suggest running `/summarize` to refresh

If no pyramid summaries exist:
- Note: "No pyramid summaries found. Run `/summarize` to generate multi-resolution project context."

### ACS Memory System

```bash
if [[ -n "${ACS_URL:-}" ]]; then
  source ~/.claude/scripts/lib/acs-client.sh
  acs_print_status
else
  echo "ACS: Not configured (set ACS_URL to enable cross-project memory)"
fi
```

### Git State

```bash
git branch --show-current
git status --short
git log --oneline -5
```

Note:

- Current branch
- Any uncommitted changes
- Recent commit history

## Step 3: Report Initialization Status

Present a summary:

```markdown
## Session Initialized

**Workflow**: Document & Clear (aggressive context clearing)

### Project State

| Aspect              | Status                                       |
| ------------------- | -------------------------------------------- |
| Branch              | `feature/xyz`                                |
| Active Plan         | `docs/plans/feature-name.md` or **STALE** ⚠️ |
| Plan Progress       | 5/12 items (42%) or "Merged - needs cleanup" |
| Last Checkpoint     | `20240115-143022-feature-batch.md`           |
| Uncommitted Changes | None                                         |
| Pyramid Summaries   | Fresh / Stale (N commits) / Not generated    |
| ACS Memory          | Connected (N memories) / Not configured      |

### Workflow Commands

| Command          | Use When                              |
| ---------------- | ------------------------------------- |
| `/create-plan`   | Starting a NEW feature                |
| `/iterate`       | Continuing work on active Plan        |
| `/status`        | Checking current progress             |
| `/verify`        | Quick lint/typecheck/test             |
| `/pre-pr-check`  | Ready to create PR                    |

### Recommended Next Action

[Based on state, suggest one of:]

- "No active Plan. Run `/create-plan` to start a new feature."
- "Active Plan found. Run `/iterate` to continue."
- "Uncommitted changes detected. Review with `git diff` before continuing."
- "Plan complete. Run `/pre-pr-check` to finalize."
- "**Stale plan detected.** Branch was merged. Delete or archive the plan file before continuing."

---

**Ready to proceed.** What would you like to work on?
```

## Step 4: Wait for Direction

After reporting status, wait for user instruction. Do NOT:

- Automatically start implementing
- Make assumptions about what to do next
- Run iterate without explicit instruction

The user will tell you what to do:

- `/create-plan` - Start new feature
- `/iterate` - Continue work
- Something else - Follow their lead

## When to Use This Command

- **First session** on this project
- **After long break** when context is stale
- **New team member** learning the workflow
- **Confused state** when unsure what's happening

## Difference from /remind

| `/kickoff`          | `/remind`                 |
| ------------------- | ------------------------- |
| Full orientation    | Quick recap               |
| Reads workflow docs | Reviews conversation only |
| Reports all state   | Focuses on session recap  |
| Waits for direction | Instant summary           |
| Use: new session    | Use: mid-session          |

## Arguments

- `--quick` - Skip reading workflow docs, just report state
- `--verbose` - Show full checkpoint contents, not just summary

## Suggested Next

| If... | Run |
|-------|-----|
| Ready to plan work | `/create-plan` — break a feature into atomic stories |
| Know what to work on | `/iterate` — execute plan items in batches |
| Want to check existing progress | `/status` — show git state and plan progress |
