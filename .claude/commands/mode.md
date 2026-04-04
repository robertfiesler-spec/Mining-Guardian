---
suggest_when:
  - signal: total_tool_calls
    value: 35
    cooldown: 60
    message: "Consider `/mode` to optimize your workflow (dev, review, debug, deploy, research, orchestrate)"
---

# /mode - Switch Context Mode

Switch the active context mode to configure behavior for a specific task type.

## Usage

```
/mode <name>
```

$ARGUMENTS

## Available Modes

| Mode | Context File | Purpose |
|------|-------------|---------|
| `dev` | `contexts/dev.md` | Fast iteration: build, test, commit |
| `review` | `contexts/review.md` | Code review: read-only analysis, structured feedback |
| `debug` | `contexts/debug.md` | Debugging: observe, hypothesize, fix, verify |
| `deploy` | `contexts/deploy.md` | Deployment: checklists, staging-first, rollback plans |
| `research` | `contexts/research.md` | Research: evaluate tools, compare alternatives |
| `orchestrate` | `contexts/orchestrate.md` | Orchestration: multi-agent coordination, parallel tasks |

## Your Task

1. Parse the mode name from arguments
2. Validate it is one of: `dev`, `review`, `debug`, `deploy`, `research`, `orchestrate`
3. Read the corresponding context file from `contexts/<name>.md`
4. Adopt the mindset, priorities, and constraints defined in that context
5. Confirm the mode switch to the user

## Step 1: Validate Mode

If no argument provided or invalid mode name:

```markdown
Usage: /mode <name>

Available modes: dev, review, debug, deploy, research, orchestrate

Example: /mode dev
```

## Step 2: Load Context

Read the context file:

```bash
cat contexts/<name>.md
```

Internalize its contents as your active operating context. The context defines:

- **Mindset** — how to approach the work
- **Process** — what steps to follow
- **Rules** — which rule files are always active
- **Constraints** — what NOT to do in this mode

## Step 3: Confirm Activation

```markdown
## Mode: <Name>

[One-line description from the context file]

**Active rules**: [list from context]
**Key constraint**: [most important "Do NOT" from context]

Ready. How can I help?
```

## Behavior

- Only one mode is active at a time — switching replaces the previous mode
- Mode persists for the current session until switched again
- Modes load context, not rules — they configure mindset, not hard constraints
- Global rules from CLAUDE.md always apply regardless of mode

## Arguments

| Argument | Description |
|----------|-------------|
| `<name>` | Mode to activate: `dev`, `review`, `debug`, `deploy`, `research`, `orchestrate` |
| (none) | Show usage and list available modes |

## Suggested Next

- `/kickoff` — initialize session context in the new mode
- `/iterate` — execute plan items in the activated mode
- `/remind` — quick session recap to orient in the new mode
