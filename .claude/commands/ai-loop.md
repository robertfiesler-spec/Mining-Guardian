---
suggest_when:
  - signal: session_start
    condition: stalled_loop
    message: "Loop stalled — same story repeated without progress. Run `cat .claude/state/loop-diagnostics.jsonl | jq .` to see iteration details, then fix the blocker before restarting `/ai-loop`"
---
# AI Loop (Autonomous Execution)

Start Ralph-style autonomous execution. Spawns fresh Claude instances until all Plan stories complete.

## Cost Optimization

**Use `--max` to cap iterations.** Default auto-calculates based on remaining stories (stories × 2, capped at 200). For cost control:

- Set explicit `--max N` based on your budget
- Monitor progress with `--tui` dashboard
- Stop early with `Ctrl+C` if progress stalls

**Fresh context each iteration** reduces token accumulation but spawns new sessions. Cost is predictable per-iteration.

## Usage

```bash
/ai-loop [options]
```

$ARGUMENTS

## Step 0: Detect Flags

Check `$ARGUMENTS` for flags. If **no flags detected**, check context and suggest:

- If no plan exists in `docs/plans/` → warn: _"No plan found. Run `/create-plan` first, or did you mean `/iterate`?"_
- If plan has many remaining stories (10+) → suggest: _"Large plan detected ([N] stories). Set `--max` to cap iterations? Default auto-calculates to [N×2]."_
- If user seems cautious → suggest `--dry-run` first

Available flags (prompt only when helpful):

| Flag | When to suggest |
|------|----------------|
| `--max N` | Large plans or cost-conscious — caps iteration count |
| `--dry-run` | First time running, unfamiliar plan — preview without executing |
| `--notify` | Long-running plans — get a macOS notification on completion |
| `--verbose` | Debugging loop behavior |

If the user provides a clear intent (e.g., `/ai-loop --max 20`), skip the prompt and proceed.

## What This Does

Autonomous mode runs a bash script that:

1. Finds the active `prd.json` in `docs/plans/`
2. Spawns a fresh Claude instance for each iteration
3. Each iteration implements ONE story
4. Continues until all stories pass or max iterations reached

```
┌─────────────────────────────────────────────────────────────────┐
│  /ai-loop --max 30                                              │
│       ↓                                                         │
│  loop.sh starts                                                 │
│       ↓                                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ITERATION N                                            │   │
│  │       ↓                                                 │   │
│  │  Fresh Claude instance                                  │   │
│  │       ↓                                                 │   │
│  │  Read prd.json → find next story (passes: false)        │   │
│  │       ↓                                                 │   │
│  │  Load appropriate agent (tdd-guide, etc.)               │   │
│  │       ↓                                                 │   │
│  │  Implement story                                        │   │
│  │       ↓                                                 │   │
│  │  Verify (lint, typecheck, test)                         │   │
│  │       ↓                                                 │   │
│  │  Commit with /create-commit                             │   │
│  │       ↓                                                 │   │
│  │  Update prd.json (passes: true)                         │   │
│  │       ↓                                                 │   │
│  │  Append learnings to progress.txt                       │   │
│  │       ↓                                                 │   │
│  │  [All done?] → Output <promise>COMPLETE</promise>       │   │
│  │  [More to do?] → Exit iteration                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│       ↓                                                         │
│  [COMPLETE signal?] → Exit loop, suggest /pre-pr-check         │
│  [No signal?] → Next iteration                                  │
│       ↓                                                         │
│  Repeat until complete or max iterations                        │
└─────────────────────────────────────────────────────────────────┘
```

## Reuse-First Context Injection

Each iteration automatically injects reuse context from the plan into the spawned Claude instance's prompt:

| Story Has | What Gets Injected |
|-----------|-------------------|
| `reuse` field | **Mandatory file references**: "Read these files before implementing" with paths, descriptions, and reuse method (import/extend/copy-and-adapt/follow-pattern) |
| `constraints` field | **DO NOT directives**: Explicit rules about what must not be recreated from scratch |
| Neither | **Soft reminder**: "Before creating new components, hooks, or utilities, search for existing similar code" (~2 lines) |

This ensures fresh Claude instances — which have no memory of previous iterations — know about existing code they should reuse rather than rebuild.

**To add reuse annotations to an existing plan**: `/create-plan --enrich docs/plans/my-plan.json`

**To include reuse annotations during plan creation**: The `/create-plan` refinement interview now asks about reuse opportunities and generates `reuse`/`constraints` fields automatically.

## Plan Recovery

If you cleared context after `/create-plan` and the plan wasn't copied to `docs/plans/`, the loop automatically recovers it from `.claude/plans/`. `/create-plan` embeds the JSON inside the plan-mode file, and `loop.sh` extracts it on startup:

```
No plan JSON in docs/plans/ — checking .claude/plans/ for recoverable plans...
Found recoverable plan: .claude/plans/curious-crunching-ocean.md
Recovered plan JSON → docs/plans/my-feature.json
```

No manual intervention needed — just run `/ai-loop` and it finds the plan.

## Prerequisites

Before running `/ai-loop`:

1. **Active Plan exists**: Run `/create-plan` first to create `docs/plans/[feature].json`
2. **Branch created**: Should be on the feature branch
3. **Dependencies installed**: `pnpm install` completed
4. **Tests passing**: Start from a green state

## File Claims (Multi-Loop Safety)

When `/ai-loop` starts, it registers file claims for the plan's files so that concurrent loops (in other worktrees or the main repo) can detect conflicts before editing the same files.

**On startup**, the loop:

1. Reads the plan file and extracts all `files` arrays from stories
2. Checks each file against the global claims registry (`.claude/state/file-claims.json`)
3. If no conflicts, claims the files for this plan
4. If conflicts found, warns and asks the user before proceeding

**On completion**, claims are released via `complete_plan_session()`.

This happens automatically — the `/iterate` command (which `/ai-loop` invokes per iteration) handles claim registration in its Step 0.7. No manual setup required.

**Cross-worktree visibility**: The claims registry lives at `.claude/state/file-claims.json` relative to where the loop runs. In a worktree, this is the worktree's own registry. To check for cross-worktree conflicts before creating a new worktree, use `/worktree` which checks the main repo's claims.

## Tasks Integration

The loop automatically syncs with Claude Code's Tasks API:

1. **Startup sync**: Before iterations begin, the loop ensures all plan stories have corresponding Tasks
2. **If tasks are missing**: They're created automatically from the plan file
3. **Progress tracking**: Each iteration updates task status (in_progress → completed)
4. **Cross-session persistence**: Tasks persist even if the loop is interrupted

This means you can run `/tasks` at any time to see progress, even if `/create-plan` didn't create the tasks initially.

## Starting Autonomous Mode

```bash
# Auto-calculated max based on remaining stories
/ai-loop

# Custom iteration limit (overrides auto-calculation)
/ai-loop --max 50

# Dry run (show what would happen)
/ai-loop --dry-run
```

This will:

1. **Calculate max iterations** (if `--max` not provided):
   - Read the plan file from `docs/plans/`
   - Count stories where `passes` is not `true`
   - Set `max = remaining_stories × 2` (buffer for retries)
2. Validate prerequisites
3. Start `.claude/scripts/loop.sh`
4. Show you how to monitor progress
5. Return control when complete (or stopped)

### Auto-Calculation Formula

When `--max` is not specified, calculate automatically:

```
remaining = stories where passes != true
max = remaining × 2 (minimum 5, maximum 200)
```

| Remaining Stories | Calculated Max |
|-------------------|----------------|
| 3                 | 6              |
| 10                | 20             |
| 25                | 50             |
| 50                | 100            |
| 100+              | 200 (capped)   |

## Monitoring Progress

While the loop runs:

```bash
# Watch progress in real-time
tail -f .claude/state/progress.txt

# Check story status
cat docs/plans/[feature].json | jq '.stories[] | {id, title, passes}'

# Count completed stories
cat docs/plans/[feature].json | jq '[.stories[] | select(.passes == true)] | length'

# Check iteration count
grep -c "### Iteration" .claude/state/progress.txt
```

## Stopping the Loop

### Graceful Stop (finish current iteration)

```bash
touch .claude/state/.stop-loop
```

### Immediate Stop

```bash
pkill -f loop.sh
```

## Full Application PRDs

The loop can process PRDs of any size - from single features to entire applications. Max iterations are **auto-calculated** based on remaining stories:

```
Small PRD:     5 stories  → auto: 10 iterations
Medium PRD:   20 stories  → auto: 40 iterations
Large PRD:    50 stories  → auto: 100 iterations
Full App:    100+ stories → auto: 200 iterations (capped)
```

Override with `--max` if needed: `/ai-loop --max 150`

**Why this works:**

- Each iteration gets a fresh Claude instance (no context overflow)
- Progress persists in `prd.json` - safe to stop and resume anytime
- Stories processed by `priority` field (1 = first)
- `depends` array ensures correct ordering
- One commit per story = clean git history

**Example: Building a full SaaS app**

```bash
# Load your comprehensive PRD
/create-plan --from-prd my-saas-app.json

# Let it run (might take hours for large apps)
/ai-loop --max 150 --notify

# Monitor in another terminal
tail -f .claude/state/progress.txt
```

## When to Use Autonomous vs Attended

| Scenario                        | Mode        | Why                        |
| ------------------------------- | ----------- | -------------------------- |
| Full application from PRD       | `/ai-loop`  | Many stories, no decisions |
| Well-defined CRUD operations    | `/ai-loop`  | Predictable, no decisions  |
| Test coverage tasks             | `/ai-loop`  | Repetitive, clear criteria |
| Refactoring with clear patterns | `/ai-loop`  | Mechanical transformations |
| New/unfamiliar codebase         | `/iterate`  | Need to learn patterns     |
| Complex architectural decisions | `/iterate`  | Need human judgment        |
| External API integrations       | `/iterate`  | May need debugging         |

## Recovery from Failures

If the loop stops unexpectedly:

1. **Check .claude/state/progress.txt** - See what was completed
2. **Check prd.json** - See which stories passed
3. **Check git log** - See commits made
4. **Resume**: Run `/ai-loop` again - picks up where it left off

## Learning from Loop Results

After the loop completes (or if you stop it), review for learnings:

1. **Review .claude/state/progress.txt** for patterns in issues encountered
2. **Run `/learn`** to document any recurring mistakes as rules
3. **Check for manual fixes** you had to make - these should become rules

**Common learnings to capture:**

- Patterns the loop consistently missed
- Files it forgot to update
- Test patterns that failed repeatedly
- Code style issues you had to fix

The goal: next time you run `/ai-loop` on a similar feature, it should make fewer mistakes.

## Arguments

| Flag        | Description                                              |
| ----------- | -------------------------------------------------------- |
| `--max <n>` | Maximum iterations (default: auto-calculated from plan)  |
| `--dry-run` | Show plan without executing                              |
| `--notify`  | macOS notification on completion                         |
| `--verbose` | Show detailed output                                     |

## Output

When starting:

```
Finding plan in docs/plans/...
Found: docs/plans/user-auth.json

Calculating iterations...
  Total stories: 8
  Remaining: 6 (passes != true)
  Max iterations: 12 (6 × 2)

Starting autonomous loop (max 12 iterations)
Progress: 2/8 stories complete

═══════════════════════════════════════════════════
Iteration 1/12
Next: US-3: Create login form component [UI]
═══════════════════════════════════════════════════

[Claude instance runs...]
```

When complete:

```
[SUCCESS] All stories complete!

Next steps:
  1. Run /pre-pr-check
  2. Run /create-pr
```

## Related Commands

| Command         | Use                                  |
| --------------- | ------------------------------------ |
| `/create-plan`  | Create the Plan before looping       |
| `/iterate`      | Human-attended alternative           |
| `/status`       | Check current progress               |
| `/pre-pr-check` | Run after loop completes             |
| `/learn`        | Document mistakes as permanent rules |

## Comparison with /iterate

| Aspect          | `/iterate`        | `/ai-loop`           |
| --------------- | ----------------- | -------------------- |
| Control         | Human in loop     | Script in loop       |
| Items per cycle | 1-3 (adaptive)    | 1 (always)           |
| Context         | Same session      | Fresh each iteration |
| Progress file   | Checkpoints       | progress.txt         |
| Best for        | Complex, learning | Routine, grinding    |

## Suggested Next

- `/iterate` — human-in-the-loop alternative for attended execution
- `/monitor` — TUI dashboard to watch agent progress in real time
- `/status` — check git state and progress after loop completes
- `/create-pr` — open PR after the feature is complete
