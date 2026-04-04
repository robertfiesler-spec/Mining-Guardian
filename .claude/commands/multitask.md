---
suggest_when:
  - signal: session_start
    condition: incomplete_plan
    cooldown: 60
    message: "Large plan to execute? `/multitask` runs parallel agents on isolated worktrees for concurrent development"
  - signal: total_tool_calls
    value: 25
    cooldown: 60
    message: "Complex session — `/multitask` can parallelize independent features across worktrees"
---

# Multitask (Parallel Worktree Instances)

Spin up multiple parallel AI instances on separate git worktrees for concurrent development.

## Usage

```bash
# Full PRD mode (existing)
/multitask --plans=docs/plans/auth.json,docs/plans/api.json,docs/plans/ui.json
/multitask --auto  # Auto-detect from existing plans

# Lightweight tasks (no /create-plan needed)
/multitask --tasks "Add auth login flow" "Build settings page" "Write API tests"
/multitask --from tasks.txt   # One task per line
/multitask --from tasks.yaml  # Structured YAML format

# Other options
/multitask --instances=3 --branches=feature/auth,feature/api,feature/ui
/multitask --auto --happy  # Use Happy CLI for enhanced instance management
```

$ARGUMENTS

## What This Does

Creates git worktrees and spawns independent AI instances to develop multiple features simultaneously.

```
Main Repo: ~/projects/my-app (on main branch)
     ↓
Worktree 1: ~/projects/my-app-wt-feature-auth/
  → Branch: feature/auth
  → Plan: docs/plans/auth.json
  → AI CLI (default: codex) running /ai-loop

Worktree 2: ~/projects/my-app-wt-feature-api/
  → Branch: feature/api
  → Plan: docs/plans/api.json
  → AI CLI (default: codex) running /ai-loop

Worktree 3: ~/projects/my-app-wt-feature-ui/
  → Branch: feature/ui
  → Plan: docs/plans/ui.json
  → AI CLI (default: codex) running /ai-loop
```

## How It Works

The command delegates to `.claude/scripts/multitask.sh`:

```bash
# You run this in the main conversation:
/multitask --plans docs/plans/auth.json,docs/plans/api.json

# Behind the scenes:
1. Validates prerequisites (git clean, plans exist)
2. Creates git worktrees in ../repo-wt-<branch>/
3. Copies plans and config to each worktree
4. Installs dependencies in each worktree
5. Spawns AI CLI command in background (default: `codex exec "/ai-loop --max N"`)
6. Launches monitoring dashboard (TUI or logs)
7. Tracks PIDs in .claude/state/multitask-session.json
```

### With Happy CLI (Optional)

If you have [Happy CLI](https://github.com/happycode-dev/happy) installed and want enhanced process management:

```bash
/multitask --plans docs/plans/auth.json,docs/plans/api.json --happy

# Uses: happy [provider run args] "/ai-loop" instead of plain provider args
# (on codex provider with --happy, this still requires Claude due to happy integration limits)
```

### AI Provider Configuration

All parallel execution entrypoints (`multitask`, `pipeline`, `ai-loop`) share the same provider controls:

- `AI_PROVIDER=auto|claude|codex` (default: `auto`; prefers codex if installed)
- `AI_PROVIDER_BIN` to pin a specific binary path/name
- `AI_PROVIDER_PRINT_ARGS` for sync prompt commands
- `AI_PROVIDER_RUN_ARGS` for background execution (default: `exec` for codex, `--continue -p` for claude)
- `AI_PROVIDER_RUN_PREFIX` optional prefix for all run invocations (for example, `happy` or `timeout`)

## Prerequisites

Before running `/multitask`:

1. **Clean working tree**: No uncommitted changes
2. **Task definitions**: Either:
   - Use `/create-plan` for each feature (full PRD mode), OR
   - Provide inline `--tasks` descriptions (lightweight mode), OR
   - Provide a `--from` task file (lightweight mode)
3. **Dependencies installed**: `pnpm install` or `npm install` completed
4. **Tests passing**: Start from green state

## Options

| Flag | Description | Example |
|------|-------------|---------|
| `--instances=N` | Number of parallel instances | `--instances=3` |
| `--branches=list` | Comma-separated branch names (auto-creates) | `--branches=feat/a,feat/b` |
| `--plans=list` | Comma-separated plan files (recommended) | `--plans=auth.json,api.json` |
| `--auto` | Auto-detect all plans in docs/plans/ | `--auto` |
| `--happy` | Use Happy CLI for instance management | `--happy` |
| `--tui` | Use TUI dashboard for monitoring (default) | `--tui` |
| `--no-tui` | Disable TUI, use log output | `--no-tui` |
| `--web-viewer` | Launch web viewer dashboard (http://localhost:8000) | `--web-viewer` |
| `--max=N` | Max iterations per instance (default: 50) | `--max=100` |
| `--auto-respawn` | Auto-respawn crashed instances during monitoring | `--auto-respawn` |
| `--max-respawn=N` | Max respawn attempts per instance (default: 3) | `--max-respawn=5` |
| `--cleanup` | Clean up existing worktrees first | `--cleanup` |
| `--recover` | Auto-recover: reattach to running, respawn crashed | `--recover` |
| `--recover-monitor` | Reattach to running instances only (no respawn) | `--recover-monitor` |
| `--tasks "d1" "d2"` | Inline task descriptions (auto-generates plans) | `--tasks "Add auth" "Build UI"` |
| `--from <file>` | Load tasks from file (.txt, .yaml, .json) | `--from tasks.txt` |
| `--force-new` | Stop existing session and start fresh (no prompt) | `--force-new` |

## Crash Recovery

When the main orchestrator crashes (kill -9, system crash, power loss), child instances continue running in their worktrees but become orphaned. On next startup, multitask detects this and offers recovery options.

### Session States

| State | Description | Typical Cause |
|-------|-------------|---------------|
| `running` | All instances still running | Orchestrator killed, instances continued |
| `mixed` | Some running, some crashed | Partial failure |
| `stopped` | All instances crashed/stopped | System reboot, all processes killed |

### Recovery Prompts

When a stale session is detected, you'll see:

```
╭─────────────────────────────────────────────────────────────────╮
│ Existing Session Detected                                      │
╰─────────────────────────────────────────────────────────────────╯

  Session: multitask-2026-02-02-145230
  Started: 2026-02-02T14:52:30Z
  State:   mixed

  Instances:
    ● #1: feature/auth [running] (PID: 12345)
    ✗ #2: feature/api [crashed] (PID: 12346)
    ● #3: feature/ui [running] (PID: 12347)

  Options:
    [r] Resume    - Reattach to 2 running, restart 1 crashed
    [s] Stop      - Stop all and start fresh
    [c] Cleanup   - Stop all and remove worktrees
    [q] Quit      - Exit without changes

  Choice [r/s/c/q]:
```

### Recovery Flags (Non-Interactive)

For scripting or automation, use flags to skip the prompt:

```bash
# Auto-recover: reattach to running + respawn crashed
./scripts/multitask.sh --recover

# Monitor only: reattach to running, don't respawn crashed
./scripts/multitask.sh --recover-monitor

# Force fresh start: stop everything and start new session
./scripts/multitask.sh --force-new --auto
```

### Manual Recovery

If you need to manually recover a specific instance:

```bash
# 1. Check which instances are running
cat .claude/state/multitask-session.json | jq '.instances[] | {instance_num, branch, status, pid}'

# 2. Resume a crashed instance in its worktree
cd ../my-app-wt-feature-api
codex exec "/ai-loop --max 50"
```

## Execution Flow

### Step 1: Parse Arguments and Validate

Claude will:
- Parse flags and validate combinations
- Ensure at least `--plans`, `--branches`, `--auto`, `--tasks`, or `--from` is provided
- Check git status (must be clean)
- Verify plans exist and are valid JSON

### Step 2: Execute Multitask Script

Claude calls the bash script:

```bash
.claude/scripts/multitask.sh \
  --plans=docs/plans/auth.json,docs/plans/api.json,docs/plans/ui.json \
  --tui \
  --max=50
```

The script handles:
- Worktree creation
- Dependency installation
- Instance spawning
- Monitoring

### Step 3: Monitor Progress

If `--tui` is enabled (default), shows dashboard:

```
╭─────────────────────────────────────────────────────────────────╮
│ Multitask Session                           3 instances running │
╰─────────────────────────────────────────────────────────────────╯

┌─ Instance 1: feature/auth ──────────────────────────────────────┐
│ Worktree: ../my-app-wt-feature-auth                             │
│ Status: Running · Iteration 5                                   │
│ Progress: 4/8 stories (50%)                                     │
│ Last: US-4 completed (commit: abc1234)                          │
└─────────────────────────────────────────────────────────────────┘

┌─ Instance 2: feature/api ───────────────────────────────────────┐
│ Worktree: ../my-app-wt-feature-api                              │
│ Status: Running · Iteration 3                                   │
│ Progress: 2/6 stories (33%)                                     │
│ Last: US-2 completed (commit: def5678)                          │
└─────────────────────────────────────────────────────────────────┘

┌─ Instance 3: feature/ui ────────────────────────────────────────┐
│ Worktree: ../my-app-wt-feature-ui                               │
│ Status: Complete ✓                                              │
│ Progress: 5/5 stories (100%)                                    │
│ Last: US-5 completed (commit: ghi9012)                          │
└─────────────────────────────────────────────────────────────────┘

  [s] stop all  [p] pause all  [r] resume all  [c] cleanup  [q] quit
```

### Step 4: Completion and Cleanup

When instances complete or you press `q`:

1. **Stop all Claude processes** gracefully
2. **Show summary** of completed work
3. **Offer merge options** for completed branches
4. **Offer cleanup** to remove worktrees

## Monitoring (No TUI Mode)

If you run with `--no-tui`, monitor via logs:

```bash
# Watch aggregated progress
tail -f .claude/state/multitask.log

# Check individual instance logs
tail -f .claude/state/multitask-instance-1.log
tail -f .claude/state/multitask-instance-2.log

# Check session state
cat .claude/state/multitask-session.json | jq .
```

## Web Viewer (Standalone)

The web viewer dashboard can be launched standalone to monitor a running multitask session from any browser at `http://localhost:8000`.

### Launch

From your **project directory** (the repo where multitask is running):

```bash
WEB_VIEWER_BASE_DIR=$(pwd) node ~/projects/ai-toolkit/scripts/web-viewer/dist/server.js
```

Or use the `--web-viewer` flag when starting multitask:

```bash
/multitask --auto --web-viewer
```

### What It Shows

- **Instance process cards**: Per-instance cards showing PID, branch, plan, status badge (running/crashed/completed/stopped), runtime duration, heartbeat freshness, and exit codes
- **Crash detail panels**: Expandable panels on each process card showing structured crash event history with timestamps, exit codes (with human-readable labels like SIGKILL/SIGTERM), and error messages
- **Plan progress**: Per-plan progress bars with story completion chips
- **Cost metrics**: Session costs (when orchestrator.json is available)
- **Live logs**: Instance log streaming via WebSocket with search highlighting and log level filtering (All/Error/Warning/Info)
- **Health summary**: Aggregate healthy/stale/crashed counts and total runtime
- **Neon Terminal theme**: Toggleable cyberpunk aesthetic with glow effects, scanlines, and monospace typography (toggle in header, persists via localStorage)

### How It Works

The web viewer reads `.claude/state/multitask-session.json` and synthesizes an orchestrator view from it. It also discovers and watches plan files referenced by each instance, displaying multi-plan progress cards.

If `orchestrator.json` exists (from a richer orchestrator), it uses that instead. Files that don't exist yet are polled until they appear -- no ENOENT crashes.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_VIEWER_BASE_DIR` | `../../` (relative to server) | Path to the project root |
| `WEB_VIEWER_PLAN` | `web-viewer` | Primary plan name to watch |

## Stopping Instances

### Graceful Stop (Recommended)

In TUI mode, press `s` to stop all instances.

Without TUI:

```bash
# Stop all instances gracefully
.claude/scripts/multitask.sh --stop

# This sends SIGTERM, waits for clean exit, then SIGKILL if needed
```

### Force Kill

```bash
# Emergency stop (not recommended - may corrupt state)
pkill -f "claude.*multitask"

# If using --happy flag:
pkill -f "happy claude.*multitask"
```

## Cleanup

After instances complete:

```bash
# Remove all worktrees created by multitask
.claude/scripts/multitask.sh --cleanup-all

# Or remove specific worktrees
git worktree remove ../my-app-wt-feature-auth
```

## Safety Features

1. **Isolation**: Each worktree has independent file state
2. **No conflicts**: Changes in one worktree don't affect others
3. **Graceful shutdown**: Ctrl+C (in TUI) stops all instances cleanly
4. **Resume support**: Can restart failed instances
5. **Resource limits**: Max 5 parallel instances by default
6. **Dependency sync**: Each worktree gets fresh npm/pnpm install

## Use Cases

### Use Case 1: Parallel Feature Development

You have 3 independent features planned:

```bash
# Create plans first
/create-plan  # Create auth plan → docs/plans/auth.json
/create-plan  # Create api plan → docs/plans/api.json
/create-plan  # Create ui plan → docs/plans/ui.json

# Run all in parallel
/multitask --plans docs/plans/auth.json,docs/plans/api.json,docs/plans/ui.json

# All 3 features develop simultaneously
# Merge when ready
```

### Use Case 2: A/B Approach Testing

Test two different implementation approaches:

```bash
# Create two plans with different approaches
/create-plan  # approach-a.json (REST API)
/create-plan  # approach-b.json (GraphQL)

/multitask --plans docs/plans/approach-a.json,docs/plans/approach-b.json

# Review both implementations, keep the better one
```

### Use Case 3: Auto-Grind Through Backlog

```bash
# Auto-detect all pending plans in docs/plans/
/multitask --auto --tui

# Toolkit grinds through all features in parallel
# Great for CRUD operations, routine tasks
```

### Use Case 4: Quick Parallel Tasks (Lightweight)

Skip `/create-plan` entirely for simple parallel work:

```bash
# Inline descriptions - each becomes a worktree instance
/multitask --tasks "Add user authentication with JWT" "Build admin dashboard page" "Write integration tests for API"

# From a text file (one task per line)
/multitask --from tasks.txt
```

Where `tasks.txt` contains:
```
# My parallel tasks
Add user authentication with JWT
Build admin dashboard page
Write integration tests for API
```

Or use YAML for more control:
```yaml
# tasks.yaml
tasks:
  - title: Add user authentication with JWT
    branch: feature/auth
  - title: Build admin dashboard page
    type: UI
  - title: Write integration tests for API
    type: Test
```

Each task auto-generates a minimal JSON PRD in `docs/plans/` with a `feature/` branch. The full pipeline (worktrees, `/ai-loop`, monitoring) works exactly the same.

### Use Case 5: Multi-Environment Testing

```bash
# Create branches for different deployment targets
/multitask \
  --branches=deploy/staging,deploy/production \
  --plans=docs/plans/release-v2.json

# Test deployment to both environments in parallel
```

## Limitations

1. **Max 5 instances** by default (configurable via `MAX_INSTANCES` env var)
2. **High CPU/memory usage** - each instance is a full Claude session
3. **No cross-instance communication** - features must be independent
4. **Requires sufficient resources** - recommend 16GB RAM for 3+ instances
5. **Plan conflicts** - features must not modify the same files

## Troubleshooting

### "No plans specified"

Provide task definitions using one of these methods:

```bash
# Full PRD mode
/multitask --plans=docs/plans/auth.json
/multitask --auto  # auto-detect from docs/plans/

# Lightweight mode (no /create-plan needed)
/multitask --tasks "Add auth" "Build settings"
/multitask --from tasks.txt
```

### "Worktree already exists"

Clean up old worktrees:

```bash
git worktree list
git worktree remove ../my-app-wt-feature-auth
```

Or use `--cleanup` flag:

```bash
/multitask --cleanup --plans ...
```

### Instance crashes or hangs

Check individual logs:

```bash
cat .claude/state/multitask-instance-1.log
```

**Automatic Recovery (Recommended)**:

```bash
# Restart multitask - it will detect the crashed session and offer recovery
.claude/scripts/multitask.sh --auto

# Or auto-recover without prompts
.claude/scripts/multitask.sh --recover
```

**Manual Recovery** (if needed):

```bash
cd ../my-app-wt-feature-auth
AI_PROVIDER=codex codex exec "/ai-loop --max 50"

# Or with Happy CLI:
happy claude --continue -p "/ai-loop --max 50" # Happy still requires Claude
```

### Orchestrator crashed (main process killed)

If you killed the main multitask process but instances are still running:

```bash
# Multitask will detect this on next run
.claude/scripts/multitask.sh --auto
# You'll see "Existing Session Detected" with recovery options

# Or auto-reattach to monitor running instances
.claude/scripts/multitask.sh --recover-monitor
```

### High memory usage

Reduce parallel instances:

```bash
# Instead of all at once:
/multitask --auto

# Run in batches:
/multitask --plans docs/plans/auth.json,docs/plans/api.json
# Wait for completion, then:
/multitask --plans docs/plans/ui.json,docs/plans/payments.json
```

## Health Monitoring

The orchestrator continuously monitors instance health during execution, writing structured data to the session file every `HEALTH_CHECK_INTERVAL` seconds (default: 10).

### What Gets Tracked

| Metric | Description |
|--------|-------------|
| `last_heartbeat` | ISO timestamp of last health check for each instance |
| `runtime_seconds` | Elapsed time since instance started |
| `exit_code` | Process exit code (0 = clean, non-zero = crash, null = running) |
| `crash_count` | Number of times an instance has crashed |
| `crash_log` | Structured array of crash events with timestamps and details |

### Auto-Respawn

Use `--auto-respawn` to automatically restart crashed instances:

```bash
/multitask --auto --auto-respawn                # Auto-restart with default 3 max attempts
/multitask --auto --auto-respawn --max-respawn=5  # Allow up to 5 restarts per instance
```

When an instance crashes and auto-respawn is enabled:
1. Exit code is captured and logged
2. Crash event is appended to the instance's `crash_log`
3. If `crash_count` < `max_respawn`, the instance is automatically restarted
4. If the limit is exceeded, a warning is logged and the instance stays down

### Web Viewer Health Display

The web viewer dashboard shows real-time health indicators:
- **Process cards**: Dedicated card per instance with PID, branch, status badge, runtime, heartbeat freshness, and exit code
- **Health dots**: Green (heartbeat < 30s), yellow (30-120s), red (crashed)
- **Runtime**: Duration display on each instance tab and process card
- **Crash badges**: Red badge with crash count — click to expand crash detail panel with event history
- **Log search**: Debounced search input with `<mark>` highlighting across log lines
- **Level filter**: Filter log lines by level (All/Error/Warning/Info) — filter state persists across tab switches
- **Health summary**: Aggregate healthy/stale/crashed counts and total runtime
- **Neon theme**: Toggle via header button for a terminal-style cyberpunk aesthetic

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_INSTANCES` | 5 | Maximum parallel instances allowed |
| `MULTITASK_WORKTREE_PREFIX` | `wt-` | Prefix for worktree directories |
| `MULTITASK_MAX_ITERATIONS` | 50 | Default max iterations per instance |
| `HEALTH_CHECK_INTERVAL` | 10 | Seconds between health checks |

## Related Commands

| Command | Use |
|---------|-----|
| `/create-plan` | Create plans before multitasking |
| `/ai-loop` | Run single autonomous session |
| `/monitor` | Monitor single loop session |
| `/status` | Check git state |
| `/tasks-cleanup` | Archive completed tasks from all instances |

## Example Session

```bash
# 1. Create three plans
/create-plan  # auth feature
/create-plan  # api feature
/create-plan  # ui feature

# 2. Start multitask
/multitask --auto --tui

# 3. Monitor dashboard (TUI launches automatically)
# Watch progress in real-time

# 4. When complete, merge branches
git checkout main
git merge feature/auth
git merge feature/api
git merge feature/ui

# 5. Clean up worktrees
.claude/scripts/multitask.sh --cleanup-all

# 6. Create PR
/create-pr
```

## Architecture Notes

- **Session state**: Tracked in `.claude/state/multitask-session.json`
- **Instance logs**: `.claude/state/multitask-instance-N.log`
- **TUI monitoring**: Node.js Ink-based dashboard (same as `/ai-loop --tui`)
- **Process management**: PIDs tracked, SIGTERM for graceful shutdown
- **Worktree naming**: `../repo-wt-<branch-name>/` to avoid conflicts

## Best Practices

1. **Define tasks**: Create plans with `/create-plan`, or use `--tasks`/`--from` for quick parallel work
2. **Independent features**: Ensure features don't conflict (different files)
3. **Monitor actively**: Use `--tui` to catch issues early
4. **Clean state**: Start with clean git tree and passing tests
5. **Resource awareness**: Don't exceed your system's capacity
6. **Merge promptly**: Merge completed branches to avoid drift

---

_Generated by `/multitask`. Managed by `.claude/scripts/multitask.sh`._

## Suggested Next

- `/monitor` — TUI dashboard to watch parallel agent progress
- `/pipeline` — for tasks with dependencies (DAG execution)
- `/status` — check overall progress across worktrees
- `/create-pr` — merge worktrees after completion
