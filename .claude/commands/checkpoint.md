---
suggest_when:
  - signal: total_tool_calls
    value: 40
    cooldown: 60
    message: "Long session — `/checkpoint` saves progress for safe resumption"
---
# /checkpoint - Save Session Progress

Capture current session state for resumption in long-running autonomous loops.

## Usage

```
/checkpoint [options]
```

$ARGUMENTS

## Your Task

Snapshot the current session: task state, decisions made, files modified, and pending work. This is essential for `/loop` crash recovery and multi-session workflows.

## Step 1: Gather Current State

Analyze the session to extract:

1. **Current task** — what you are working on (story ID if from a plan)
2. **Task status** — `not started`, `in progress`, `blocked`, or `complete`
3. **Files modified** — list all files created or changed this session
4. **Decisions made** — architectural choices, trade-offs, rejected alternatives
5. **Pending items** — what still needs to be done
6. **Blockers** — anything preventing progress (if any)

## Step 2: Generate Checkpoint

Create a timestamped checkpoint file:

**Path**: `.ai/memory/checkpoints/[YYYYMMDD-HHMMSS]-[task-name].md`

```markdown
# Checkpoint: [Task Name]

**Created**: [ISO timestamp]
**Status**: [not started | in progress | blocked | complete]
**Branch**: [current git branch]
**Plan**: [plan file path, if any]

## Task Summary

[2-3 sentence description of current work]

## Files Modified

- `path/to/file.ts` — [brief description of changes]
- `path/to/file.ts` — [brief description of changes]

## Decisions Made

- **[Decision]**: [Rationale]. Rejected: [alternative].
- **[Decision]**: [Rationale].

## Pending Items

- [ ] [Remaining work item 1]
- [ ] [Remaining work item 2]

## Blockers

[None, or description of what's blocking progress]

## Next Steps

When resuming:

1. [First action to take]
2. [Second action to take]

## Context Notes

[Error messages, URLs, code snippets, or other context needed for resumption]
```

## Step 3: Update Session State

If `.ai/memory/` directory structure exists, also update session tracking:

```bash
mkdir -p .ai/memory/checkpoints
```

If a plan is active, update its session state to reflect the checkpoint.

## Step 4: Confirm

```markdown
## Checkpoint Saved

**Path**: `.ai/memory/checkpoints/[filename]`
**Status**: [status]
**Files captured**: [N] modified files
**Pending items**: [N] remaining

Context can be safely cleared. Run `/iterate` to auto-restore.
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--brief` | Minimal checkpoint: task, status, and files only |
| `--task <name>` | Override task name for the filename |
| `--plan <path>` | Associate with a specific plan file |

## Integration

| Trigger | Behavior |
|---------|----------|
| `/iterate` batch complete | Auto-creates checkpoint before stopping |
| `/loop` iteration end | Writes checkpoint for crash recovery |
| `/wrap-up` | Creates final checkpoint as part of session end |
| Manual `/checkpoint` | On-demand snapshot at any time |

## Related

- `/iterate` — auto-checkpoints after each batch
- `/wrap-up` — end-of-session summary with checkpoint
- `/loop` — autonomous execution with crash recovery
- `.ai/memory/checkpoints/` — where checkpoints are stored

## Suggested Next

| If... | Run |
|-------|-----|
| Ready to continue working | `/iterate` — resume executing plan items |
| Session ending | `/wrap-up` — summarize work, extract learnings, update tracking |
