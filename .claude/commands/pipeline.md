---
suggest_when:
  - signal: session_start
    condition: incomplete_plan
    cooldown: 60
    message: "Plan with dependent tasks? `/pipeline` executes them as a DAG with parallel dispatch and checkpointing"
  - signal: edits_since_commit
    value: 20
    cooldown: 45
    message: "Many changes in flight — `/pipeline` can orchestrate complex multi-step workflows with resume support"
---

# Pipeline Runner

Execute graph-based pipelines with dependency tracking, parallel dispatch, and checkpointing.

## Your Task

Run the pipeline runner script to execute a pipeline definition file. The pipeline defines a DAG (directed acyclic graph) of tasks that are executed in topological order with parallel dispatch where possible.

$ARGUMENTS

## Execution

Based on the user's request, run the appropriate pipeline command:

### Run a Pipeline

```bash
.claude/scripts/pipeline.sh [OPTIONS] <pipeline.json>
```

### Resume a Failed/Paused Pipeline

```bash
.claude/scripts/pipeline.sh --resume <pipeline-id>
```

### Dry Run (Validate Only)

```bash
.claude/scripts/pipeline.sh --dry-run <pipeline.json>
```

### Check Pipeline Status

```bash
.claude/scripts/pipeline.sh --status <pipeline-id>
```

### List All Pipeline Runs

```bash
.claude/scripts/pipeline.sh --list
```

### Cancel a Running Pipeline

```bash
.claude/scripts/pipeline.sh --cancel <pipeline-id>
```

## Options

| Flag                | Description                                |
| ------------------- | ------------------------------------------ |
| `--resume <id>`     | Resume a paused/failed pipeline            |
| `--dry-run`         | Validate and show execution order          |
| `--events`          | Write NDJSON event stream                  |
| `--web-viewer`      | Update state for web viewer integration    |
| `--max-parallel=N`  | Max concurrent nodes (default: 5)          |
| `--timeout=N`       | Global timeout in seconds (0 = no timeout) |
| `--list`            | List all pipeline state files              |
| `--status <id>`     | Show status of a specific pipeline         |
| `--cancel <id>`     | Cancel a running pipeline                  |

## Pipeline Definition Format

Pipeline definitions are JSON files with this structure:

```json
{
  "pipeline": "my-pipeline",
  "version": "1.0",
  "nodes": [
    {
      "id": "lint",
      "type": "shell",
      "command": "npm run lint"
    },
    {
      "id": "test",
      "type": "shell",
      "command": "npm test"
    },
    {
      "id": "build",
      "type": "shell",
      "command": "npm run build",
      "depends": ["lint", "test"]
    }
  ]
}
```

### Node Types

| Type    | Description                                    |
| ------- | ---------------------------------------------- |
| `task`  | Command execution via AI backend (`claude`/`codex`) |
| `shell` | Direct bash execution                          |
| `plan`  | Execute a full PRD plan (requires `plan_path`) |
| `gate`  | Manual approval checkpoint                     |

### Backend Types

| Backend       | Description                           |
| ------------- | ------------------------------------- |
| `shell`       | Direct bash (default)                 |
| `claude-code` | Spawn configured AI CLI instance       |
| `manual`      | Wait for human approval (gate nodes)  |

The `claude-code` backend now resolves through `AI_PROVIDER` and uses the same runtime abstraction as `/ai-loop` and `/multitask`:

- `AI_PROVIDER=auto` (default): prefer `codex`, fallback `claude`
- `AI_PROVIDER=codex`: force `codex exec ...`
- `AI_PROVIDER=claude`: force `claude --continue -p ...`

## Monitoring

While a pipeline runs:

```bash
# Watch events in real-time
tail -f .claude/state/pipeline-<id>.events.ndjson

# Check status
.claude/scripts/pipeline.sh --status <id>

# View node logs
cat .claude/state/pipeline-<id>-node-<node-id>.log
```

## Graceful Stop

```bash
# Send stop signal (finishes current nodes, then pauses)
.claude/scripts/pipeline.sh --cancel <id>

# Resume later
.claude/scripts/pipeline.sh --resume <id>
```

## Examples

```bash
# CI pipeline
/pipeline docs/plans/examples/ci-pipeline.json

# With event stream and web viewer
/pipeline --events --web-viewer docs/plans/examples/deploy-pipeline.json

# Dry run to validate
/pipeline --dry-run docs/plans/examples/feature-pipeline.json

# Resume after failure
/pipeline --resume deploy-feature
```

## Related Commands

| Command      | Use                                    |
| ------------ | -------------------------------------- |
| `/multitask` | Parallel independent plans (worktrees) |
| `/ai-loop`   | Autonomous single-plan execution       |
| `/iterate`   | Human-in-the-loop plan execution       |
| `/monitor`   | TUI dashboard for agent monitoring     |

## Suggested Next

- `/monitor` — TUI dashboard to watch pipeline execution in real time
- `/multitask` — for independent parallel workstreams without dependencies
- `/status` — check progress after pipeline run completes
