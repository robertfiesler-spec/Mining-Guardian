---
suggest_when:
  - signal: session_start
    condition: incomplete_plan
    cooldown: 60
    message: "Ready to execute a plan at scale? `/orchestrate` spawns parallel agents to tackle it concurrently"
  - signal: session_start
    condition: no_plan_many_edits
    cooldown: 60
    message: "Working on a big feature? `/orchestrate` can split it across parallel worktree agents"
---

# /orchestrate - Launch Multitask Workflow

Spawn parallel worktree-based agents from a PRD file or inline task list.

## Usage

```
/orchestrate [options]
```

$ARGUMENTS

## Your Task

Set up and launch parallel Claude instances working on independent tasks. This is the entry point for multi-agent development workflows.

## Step 1: Parse Task Input

Determine the task source (first match wins):

| Input | Source |
|-------|--------|
| `--prd <path>` | Load a PRD file (JSON or Markdown) |
| `--tasks "desc1" "desc2"` | Inline task descriptions |
| `--from <file>` | Task file (.txt, .yaml, .json) |
| `--auto` | Auto-detect plans in `docs/plans/` |
| (none) | Prompt user for input |

If no input provided, ask:

```markdown
How would you like to define tasks?

1. **PRD file** — provide a path to a JSON or Markdown PRD
2. **Inline tasks** — describe 2-5 tasks to run in parallel
3. **Auto-detect** — find existing plans in docs/plans/
```

## Step 2: Validate Prerequisites

Before spawning agents, verify:

```bash
# Clean working tree
git status --porcelain

# Dependencies installed
ls node_modules/.package-lock.json 2>/dev/null || ls node_modules 2>/dev/null

# No existing multitask session (or offer recovery)
cat .claude/state/multitask-session.json 2>/dev/null | jq -r '.status' 2>/dev/null
```

**Blockers:**
- Uncommitted changes: "Commit or stash changes first"
- Missing dependencies: "Run `pnpm install` first"
- Existing session running: Offer recovery options (resume, stop, cleanup)

## Step 3: Prepare Tasks

**From PRD**: Extract stories, group into parallelizable sets based on `depends` graph.

**From inline tasks**: Auto-generate minimal plan files in `docs/plans/`:

```bash
# Each task becomes a one-story plan
# Branch: feature/[kebab-case-task-name]
# Plan: docs/plans/[task-name].json
```

**From auto-detect**: Find all `.json` files in `docs/plans/` with incomplete stories.

Show the execution plan:

```markdown
## Orchestration Plan

**Instances**: [N] parallel agents
**Estimated iterations**: [total across all instances]

| Instance | Branch | Plan | Stories |
|----------|--------|------|---------|
| 1 | feature/auth | auth.json | 8 |
| 2 | feature/api | api.json | 6 |
| 3 | feature/ui | ui.json | 5 |

Confirm to launch? (y/n)
```

## Step 4: Launch Agents

Delegate to the multitask script:

```bash
.claude/scripts/multitask.sh \
  --plans=[comma-separated plan paths] \
  --tui \
  --max=[iterations per instance]
```

Each instance:
1. Gets its own git worktree (`../repo-wt-[branch]/`)
2. Gets a fresh `pnpm install`
3. Runs `/ai-loop` autonomously
4. Tracks progress in its own session state

## Step 5: Monitor Progress

Default: TUI dashboard launches automatically.

```markdown
## Monitoring

**Dashboard**: TUI active (press `q` to quit, `s` to stop all)
**Logs**: `.claude/state/multitask-instance-N.log`
**State**: `.claude/state/multitask-session.json`

To monitor from another terminal:
  tail -f .claude/state/multitask.log
```

If `--web-viewer` is used, launch the web dashboard at `http://localhost:8000`.

## Step 6: Completion

When all instances finish (or user stops):

```markdown
## Orchestration Complete

| Instance | Branch | Progress | Status |
|----------|--------|----------|--------|
| 1 | feature/auth | 8/8 (100%) | Complete |
| 2 | feature/api | 6/6 (100%) | Complete |
| 3 | feature/ui | 4/5 (80%) | Stopped |

### Next Steps
1. Review branches: `git log --oneline feature/auth feature/api feature/ui`
2. Merge completed branches to main
3. Clean up worktrees: `.claude/scripts/multitask.sh --cleanup-all`
4. Run `/pre-pr-check` on merged result
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--prd <path>` | Path to PRD file (JSON or Markdown) |
| `--tasks "d1" "d2"` | Inline task descriptions |
| `--from <file>` | Load tasks from file (.txt, .yaml, .json) |
| `--auto` | Auto-detect plans in docs/plans/ |
| `--max <N>` | Max iterations per instance (default: 50) |
| `--web-viewer` | Launch web dashboard at localhost:8000 |
| `--no-tui` | Disable TUI, use log output |
| `--recover` | Resume crashed session |
| `--cleanup` | Remove existing worktrees first |

## Related

- `/multitask` — the full-featured multitask command (this is the streamlined launcher)
- `/ai-loop` — what each spawned instance runs internally
- `/plan` — create plans before orchestrating
- `/create-plan` — full planning with PRD conversion
- `agents/orchestrator.md` — coordination and delegation logic
- `contexts/orchestrate.md` — orchestration mode context

## Suggested Next

- `/multitask` — parallel worktrees for independent workstreams
- `/pipeline` — graph-based orchestration for dependent tasks
- `/monitor` — TUI dashboard to track spawned agents
