# AI Toolkit Workflow

The core development loop optimizes for **clean context over continuous execution**. Work in focused batches, checkpoint state, clear context, and resume.

## The Loop

```
┌─────────────────────────────────────────────────────────────────┐
│  /kickoff          → Initialize session, read project context   │
│       ↓                                                         │
│  /feature          → Create Plan with implementation checklist  │
│       ↓                                                         │
│  /iterate          → Execute items, verify, commit, checkpoint  │
│       ↓                                                         │
│  [STOP]            → Clear context (/clear or /compact)         │
│       ↓                                                         │
│  /catchup          → Restore from checkpoint                    │
│       ↓                                                         │
│  /iterate          → Continue next batch...                     │
│       ↓                                                         │
│  [Repeat until Plan complete]                                   │
│       ↓                                                         │
│  /pre-pr-check     → Final validation                           │
│       ↓                                                         │
│  /create-pr        → Open pull request                          │
└─────────────────────────────────────────────────────────────────┘
```

## Command Reference

| Command         | Purpose                         | When to Use                                      |
| --------------- | ------------------------------- | ------------------------------------------------ |
| `/kickoff`      | Full session initialization     | First session, after long break, new team member |
| `/feature`      | Create implementation Plan      | Starting new feature, improvement, or bug fix    |
| `/iterate`      | Execute Plan items in batches   | Active development                               |
| `/ai-loop`      | Autonomous execution with TUI   | Well-defined, routine tasks                      |
| `/checkpoint`   | Save session state manually     | Before clearing, at natural stopping points      |
| `/catchup`      | Restore context from checkpoint | After `/clear`, resuming work                    |
| `/status`       | Show git state and progress     | Checking current state                           |
| `/verify`       | Quick lint, typecheck, tests    | After changes, before commits                    |
| `/pre-pr-check` | Full validation suite           | Ready to create PR                               |
| `/create-pr`    | Generate structured PR          | Feature complete                                 |

## Adaptive Batching

`/iterate` automatically sizes batches based on item complexity:

| Complexity | Batch Size | Examples                          |
| ---------- | ---------- | --------------------------------- |
| Simple     | 2-3 items  | Config changes, imports, renaming |
| Medium     | 1-2 items  | New function, component update    |
| Complex    | 1 item     | New feature, multi-file refactor  |

**When in doubt, batch smaller.** Clean context > fewer interruptions.

## Prompt Caching Hygiene

Use these practices in long-running sessions and autonomous loops:

- Keep prompt prefixes stable: static instructions/tools first, dynamic data later.
- Avoid unnecessary model switches mid-session; switching can reset cache advantages.
- Avoid changing tool sets during active sessions unless required.
- Prefer incremental message-based updates over rewriting core prompt anchors.

These guidelines complement (not replace) verification and checkpoint workflows.

## Key Files

- **Plans**: `docs/plans/[feature-name].md` - Human-readable checklists
- **Plans (JSON)**: `docs/plans/[feature-name].json` - Machine-readable for autonomous mode
- **Checkpoints**: `.claude/checkpoints/[timestamp]-[task].md` - Session state snapshots
- **Progress**: `.claude/state/progress.txt` - Append-only learnings (autonomous mode)

---

## Autonomous Execution (Ralph-Style)

For well-defined, routine tasks, use autonomous mode which runs without human intervention.

### Starting Autonomous Mode

```bash
/kickoff           # Initialize
/feature           # Creates both .md and .json Plans
/ai-loop --tui --max 30  # Start with TUI dashboard (recommended)
# OR
/ai-loop --max 30     # Traditional mode (text output only)
```

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  loop.sh (orchestrator)                                         │
│       │                                                         │
│       ├──→ Check for interrupted session → offer resume         │
│       ├──→ Initialize session state (.claude/state/session.json)│
│       ├──→ Launch TUI dashboard (if --tui flag)                 │
│       │                                                         │
│       ├──→ Spawn fresh Claude instance                          │
│       │         │                                               │
│       │         ├──→ Read prd.json → find next story            │
│       │         ├──→ Load agent based on story type             │
│       │         ├──→ Implement ONE story                        │
│       │         ├──→ Verify (lint, typecheck, test)             │
│       │         ├──→ Commit via /create-commit                  │
│       │         ├──→ Update prd.json (passes: true)             │
│       │         ├──→ Append learnings to progress.txt           │
│       │         └──→ Exit (or <promise>COMPLETE</promise>)      │
│       │                                                         │
│       ├──→ Update session state after each iteration            │
│       ├──→ Check for pause/quit signals from TUI                │
│       ├──→ Detect completion → EXIT SUCCESS                     │
│       └──→ No completion → NEXT ITERATION                       │
└─────────────────────────────────────────────────────────────────┘
```

### TUI Dashboard

The TUI provides a live dashboard for monitoring autonomous execution:

```
╭─────────────────────────────────────────────────────────────────╮
│ AI Toolkit                                    Elapsed: 01:23:45 │
╰─────────────────────────────────────────────────────────────────╯

  Progress                                              3/8 · 37%
  ████████████░░░░░░░░░░░░░░░░░░░░░░░░░

  Status: Running · Iteration 4

╭─ Activity ──────────────────────────────────────────────────────╮
│ 11:42:15  US-3 completed (commit: def5678)                      │
│ 11:42:00  Verification passed                                   │
│ 11:40:30  Running tests...                                      │
╰─────────────────────────────────────────────────────────────────╯

  [p] pause  [r] resume  [q] quit  [l] logs  [s] status
```

**Keyboard Controls:**

| Key | Action | Description                           |
| --- | ------ | ------------------------------------- |
| `p` | Pause  | Pauses after current story completes  |
| `r` | Resume | Continues from paused state           |
| `q` | Quit   | Graceful exit with state preservation |
| `l` | Logs   | Full scrollable activity log          |
| `s` | Status | Detailed session information          |

### Monitoring (Traditional Mode)

```bash
# Watch progress in real-time
tail -f .claude/state/progress.txt

# Check story status
cat docs/plans/feature.json | jq '.stories[] | {id, title, passes}'

# Stop gracefully
touch .claude/state/.stop-loop
```

### Session Persistence

Session state is automatically managed - no manual `/checkpoint` or `/catchup` needed in autonomous mode.

**Automatic Features:**

- **Auto-save**: State saved every 30 seconds and after each story completion
- **Crash recovery**: Interrupted sessions detected on startup, prompts to resume
- **Resume**: Continue from last completed story after interruption

**Session State Location:** `.claude/state/session.json`

```json
{
  "status": "running",
  "progress": { "total_stories": 8, "completed": 3, "current_iteration": 4 },
  "plan": { "name": "user-auth", "branch": "feature/user-auth" },
  "activity_log": [...]
}
```

**Resume Interrupted Session:**

```bash
./scripts/loop.sh --tui
# If interrupted session detected:
# "Found interrupted session from 2026-01-18 10:30. Resume? [Y/n]"
```

### When to Use Each Mode

| Scenario          | Mode          | Why                          |
| ----------------- | ------------- | ---------------------------- |
| New codebase      | `/iterate`    | Need to learn patterns       |
| Complex decisions | `/iterate`    | Human judgment required      |
| CRUD operations   | `/ai-loop --tui` | Predictable, visual feedback |
| Test coverage     | `/ai-loop --tui` | Repetitive, monitor progress |
| Refactoring       | `/ai-loop`       | Mechanical transformations   |
| Long-running task | `/ai-loop --tui` | Pause/resume as needed       |

---

## Hello World Example

A complete walkthrough using all workflow features.

### Scenario: Add a "Hello World" API endpoint

**Step 1: Initialize Session**

```
> /kickoff
```

Reads CLAUDE.md, checks for active Plans, reports git state. Output:

```
## Session Initialized
**Workflow**: Document & Clear
**Branch**: main
**Active Plan**: None
**Recommended**: Run `/feature` to start a new feature.
```

**Step 2: Create the Plan**

```
> /feature
```

Claude asks for feature details:

- **Name**: Hello World API
- **Problem**: Need a simple health check endpoint
- **Solution**: GET /api/hello returns { message: "Hello, World!" }
- **Acceptance**: Returns 200 with JSON, has test coverage

Creates `docs/plans/hello-world-api.md`:

```markdown
# Plan: Hello World API

**Type**: New Feature
**Status**: In Progress
**Branch**: feature/hello-world-api

## Implementation Checklist

### Phase 1: Setup

- [ ] **Setup** Create feature branch
  - Files: N/A (git)
  - Test: Branch exists

### Phase 2: Core

- [ ] **API** Create GET /api/hello endpoint
  - Files: `app/api/hello/route.ts`
  - Test: Returns { message: "Hello, World!" }

### Phase 3: Testing

- [ ] **Test** Add endpoint tests
  - Files: `__tests__/api/hello.test.ts`
  - Test: All tests pass

### Phase 4: Finalize

- [ ] **Docs** Update API documentation
  - Files: `docs/api.md`
  - Test: Endpoint documented
```

**Step 3: First Iteration**

```
> /iterate
```

Claude assesses: "Items are simple → batch size: 2"

Executes:

1. Creates branch `feature/hello-world-api`
2. Creates `app/api/hello/route.ts`
3. Runs verification: `pnpm lint && pnpm typecheck && pnpm test`
4. Commits: `feat(api): add hello world endpoint`
5. Updates Plan (marks items [x])
6. Creates checkpoint

Output:

```
## Batch Complete
**Plan**: hello-world-api
**This Session**: 2 items completed
**Total Progress**: 2/4 (50%)

### Checkpoint Saved
`.claude/checkpoints/20240115-143022-hello-world-batch.md`

**Next Steps**:
1. Clear context: /clear
2. Restore: /catchup
3. Continue: /iterate
```

**Step 4: Clear and Resume**

```
> /clear
> /catchup
```

Reads checkpoint, reviews changed files, reports:

```
## Context Restored
**From Checkpoint**: 20240115-143022-hello-world-batch.md
**Task**: Hello World API
**Progress**: 2/4 items

### Next Items
- [ ] Add endpoint tests
- [ ] Update API documentation

**Ready to continue?**
```

**Step 5: Complete the Feature**

```
> /iterate
```

Completes remaining items, checkpoints, reports:

```
## Batch Complete
**Total Progress**: 4/4 (100%)

**Feature complete!** Run `/pre-pr-check` then create PR.
```

**Step 6: Validate and Ship**

```
> /pre-pr-check
```

Runs full validation: lint, typecheck, tests, security scan, compliance check.

```
> /create-pr
```

Generates PR with summary, test plan, and checklist.

### Key Takeaways

1. **Never code without a Plan** - `/feature` creates the roadmap
2. **Work in batches** - `/iterate` handles sizing automatically
3. **Checkpoint religiously** - State is saved after every batch
4. **Clear context often** - Prevents hallucinations and drift
5. **Verify before commit** - Every item gets lint/typecheck/test

---

## Tasks Integration

The toolkit uses Claude Code's native Tasks API for persistent state tracking across sessions.

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  /create-plan    → TaskCreate (creates task for each story)     │
│       ↓                                                         │
│  /iterate        → TaskUpdate (pending → in_progress)           │
│       ↓                                                         │
│  [Work complete] → TaskUpdate (in_progress → completed)         │
│       ↓                                                         │
│  /create-pr      → Archive tasks to plan metadata               │
│       ↓                                                         │
│  /tasks-cleanup  → Remove archived tasks from active list       │
└─────────────────────────────────────────────────────────────────┘
```

### Benefits Over File-Based Tracking

| Feature             | File-Based (Fallback)       | Tasks API (Primary)           |
| ------------------- | --------------------------- | ----------------------------- |
| Session Persistence | Manual `/checkpoint` needed | Automatic cross-session       |
| Progress Visibility | Check plan files            | Native `/tasks` command       |
| Context Recovery    | `/catchup` reads files      | Automatic via `TaskList`      |
| Subagent Work       | Manual coordination         | Owner tracking, blocking deps |

### Useful Commands

- **View tasks**: `/tasks` (Claude Code built-in)
- **Archive completed**: `/tasks-cleanup --archive`
- **Restore context**: `/catchup` (auto-detects Tasks or files)

### Fallback Mode

If Tasks API is unavailable, the toolkit gracefully falls back to file-based tracking:

- Session state in `.claude/state/session.json`
- Progress in plan files (`passes: true/false`)
- Checkpoints for recovery points

---

## Session State Files

The toolkit maintains several state files during execution:

| File                         | Purpose                         | Created By     |
| ---------------------------- | ------------------------------- | -------------- |
| Claude Code Tasks            | Primary state tracking          | `/create-plan` |
| `.claude/state/session.json` | Session state (fallback)        | `/ai-loop`     |
| `.claude/state/progress.txt` | Append-only learnings log       | `/ai-loop`     |
| `.claude/state/.pause`       | Pause signal semaphore          | TUI `p` key    |
| `.claude/state/.quit`        | Quit signal semaphore           | TUI `q` key    |
| `.claude/state/.stop-loop`   | Traditional stop signal         | Manual         |
| `.claude/checkpoints/*.md`   | Session state snapshots         | `/iterate`     |
| `docs/plans/*.json`          | Machine-readable plan (stories) | `/feature`     |
| `docs/plans/*.md`            | Human-readable plan (checklist) | `/feature`     |

**State directory is gitignored** - session state is local only, not committed.

**Tasks persist in Claude Code** - visible via `/tasks`, survive context clears.

---

## Prompting Techniques

Advanced prompting patterns for senior-level productivity.

### Delegating to Subagents

When facing complex problems that benefit from more compute/reasoning:

```
Analyze this authentication flow and identify security vulnerabilities. Use subagents.
```

The `use subagents` suffix signals Claude to spawn specialized subagents for parallel exploration, keeping the main context window clean.

### Recovery Prompts

When implementation goes sideways:

| Situation | Prompt |
|-----------|--------|
| Mediocre output | "Knowing everything you know now, scrap this and implement the elegant solution." |
| Unclear if working | "Prove to me this works - diff the behavior between main and this branch." |
| Pre-PR confidence | "Grill me on these changes and don't make a PR until I pass your test." |
| Wrong direction | "Switch back to plan mode. We need to re-plan this approach." |

### Voice Dictation

For detailed, nuanced prompts, use macOS voice dictation (`fn` twice):

- More natural phrasing than typing
- Faster for complex requirements
- Better for explaining "why" behind decisions

### Visual Explanations

Ask Claude to generate visual aids for understanding:

```
Generate an ASCII diagram showing how data flows through this system.
Draw the component hierarchy as a tree structure.
Create an HTML presentation explaining this codebase to a new team member.
```

### Output Style Hints

Control how Claude explains changes:

```
# Learning mode - understand why
Explain each change you make and why it's the right approach.

# Concise mode - just do it
Make the changes without explanation. I'll ask if I need details.

# Teaching mode - quiz me
After making changes, ask me questions to verify I understand.
```

Configure default style in `config.json` under `claude.outputStyle`.
