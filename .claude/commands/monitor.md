---
suggest_when:
  - signal: total_tool_calls
    value: 15
    cooldown: 30
    message: "Running parallel agents? `/monitor` launches a TUI dashboard to track all active sessions"
  - signal: session_start
    condition: incomplete_plan
    cooldown: 120
    message: "Have agents running? `/monitor` shows real-time progress across all worktrees"
---

# Monitor

Launch the TUI dashboard for monitoring agents without requiring `/ai-loop` to be running.

## Usage

```bash
/monitor
```

$ARGUMENTS

## What This Does

Launches the standalone TUI dashboard that displays:

- Current session state from `.claude/state/session.json`
- Orchestrator state from `.claude/state/orchestrator.json`
- Progress tracking and activity logs
- Real-time updates as agents work

## Your Task

1. **Verify Node.js is available**

   Check that Node.js is installed (required for the Ink TUI).

2. **Launch the TUI**

   Execute the TUI wrapper script:

   ```bash
   ./scripts/tui-wrapper.sh
   ```

   Or if running from an installed toolkit:

   ```bash
   ./.claude/scripts/tui-wrapper.sh
   ```

3. **Provide keyboard controls reference**

   The TUI supports these controls:

   | Key   | Action | Description                           |
   | ----- | ------ | ------------------------------------- |
   | `o`   | Orch   | Switch to orchestrator view           |
   | `l`   | Logs   | Opens scrollable activity log viewer  |
   | `s`   | Status | Opens full session details viewer     |
   | `h`   | Help   | Show keyboard shortcuts               |
   | `q`   | Quit   | Exit the TUI                          |
   | `Esc` | Back   | Returns to dashboard from detail view |

## Use Cases

| Scenario                            | Why Use `/monitor`                      |
| ----------------------------------- | --------------------------------------- |
| `/ai-loop` running in another terminal | Monitor progress without interrupting   |
| Debugging session state             | Inspect `.claude/state/` files visually |
| After crash/restart                 | Check what state was preserved          |
| Learning the TUI                    | Explore without running autonomous mode |

## Behavior Notes

- **No active session**: TUI shows "waiting for session" message
- **Session exists**: Displays current progress, activity, and status
- **AI-loop running elsewhere**: Shows real-time updates from shared state files
- **Dependencies**: Auto-installs and builds TUI on first run if needed

## Related Commands

| Command    | Use                                 |
| ---------- | ----------------------------------- |
| `/ai-loop` | Start autonomous execution with TUI |
| `/status`  | Quick text-based status check       |
| `/catchup` | Restore context from checkpoint     |

## Suggested Next

- `/ai-loop` — start autonomous execution to monitor
- `/status` — quick text-based status without launching TUI
- `/catchup` — restore context from checkpoint after monitoring
