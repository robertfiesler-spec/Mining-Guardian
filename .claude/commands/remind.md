---
suggest_when:
  - signal: total_tool_calls
    value: 40
    cooldown: 45
    message: "Deep into the session — `/remind` for a quick recap of goals and progress"
---

# Remind

Quick session recap — summarize what this conversation has been about, what's done, what's pending, and what to do next.

## Cost Optimization

**Recommended Model**: `haiku`

This command reads conversation context and formats a summary. No code analysis, no file reads required. Use the lightest model available.

## Your Task

Review the current conversation history and produce a concise, scannable summary of the session. This helps users who run many concurrent sessions quickly recall what each one was about.

$ARGUMENTS

## Step 1: Check for Tasks

Query the Tasks API for any tracked tasks:

```
TaskList()
```

If tasks exist, note their statuses (pending, in_progress, completed). These provide structured progress data to supplement the conversation review.

## Step 2: Review Conversation History

Scan the full conversation context for:

1. **Initial request**: What did the user first ask for? What was the goal?
2. **Key decisions**: Important choices made during the session (architecture, approach, tool selection, etc.)
3. **Work completed**: Files created, files edited, commands run, features implemented, bugs fixed
4. **Errors and resolutions**: Problems encountered and how they were resolved
5. **Pending items**: Things started but not finished, or explicitly deferred
6. **Open questions**: Unresolved decisions or things the user needs to follow up on

## Step 3: Display Summary

Output a structured recap. Keep it scannable — bullet points, not paragraphs.

### When the session has activity:

```markdown
## Session Recap

**Goal**: [1-2 sentence summary of what the user originally asked for]

### Completed
- [item that was finished]
- [item that was finished]

### Pending
- [item started but not finished]
- [item explicitly deferred]

### Key Decisions
- [important choice made and why]

### Next Steps
- [what to do next to continue this work]
```

### When tasks exist, include task status:

```markdown
### Task Progress: X/Y complete

- [x] Task 1: description
- [~] Task 2: description (in progress)
- [ ] Task 3: description (pending)
```

### When the session is fresh (no meaningful activity):

```markdown
## Session Recap

No significant activity in this session yet. What would you like to work on?
```

## Guidelines

- **Be concise**: Each bullet should be one line. No long explanations.
- **Be specific**: Reference actual file names, function names, and error messages — not vague summaries.
- **Prioritize recency**: If the session is long, weight recent activity higher.
- **Include blockers**: If something failed or is blocking progress, call it out clearly.
- **Skip noise**: Don't list every file read or search performed. Focus on meaningful actions and decisions.

## Related Commands

| Command | Relationship |
|---------|-------------|
| `/status` | Git state and checkpoint details |
| `/kickoff` | Full session initialization with project context |
| `/iterate` | Continue executing plan items |
| `/plan-status` | Multi-agent plan coordination |

## Suggested Next

- `/iterate` — resume plan execution
- `/catchup` — deeper session recovery with full plan and task context
- `/status` — git state and diff details
