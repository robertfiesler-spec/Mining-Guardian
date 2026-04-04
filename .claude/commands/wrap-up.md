---
suggest_when:
  - signal: total_tool_calls
    value: 60
    cooldown: 60
    message: "Long session — consider `/wrap-up` to capture learnings before ending"
---

# /wrap-up - End Session Summary

Summarize the session, extract learnings, and update progress tracking before ending work.

## Usage

```
/wrap-up [options]
```

$ARGUMENTS

## Your Task

Close the current session cleanly: summarize accomplishments, capture learnings, note blockers, and leave breadcrumbs for the next session.

## Step 1: Gather Session Activity

Review what happened this session:

1. **Git log** — commits made since session start (or last checkpoint)
2. **Files changed** — `git diff --stat` against the session baseline
3. **Plan progress** — if a plan is active, how many items were completed
4. **Tasks status** — query Tasks API for current state

```bash
# Recent commits this session
git log --oneline --since="4 hours ago"

# Files changed
git diff --stat HEAD~5 2>/dev/null || git diff --stat
```

## Step 2: Summarize Accomplishments

Write a concise summary of what was achieved:

```markdown
## Session Summary

**Duration**: [approximate time]
**Commits**: [N] commits
**Plan progress**: [X]/[Y] items ([Z]%)

### Completed
- [Task/story 1] — [one-line description]
- [Task/story 2] — [one-line description]

### In Progress
- [Task/story] — [what's left to do]

### Blockers
- [Blocker description] — [what's needed to unblock]
```

## Step 3: Extract Learnings

Review the session for reusable insights. For each learning:

1. **What was discovered?** — pattern, pitfall, or technique
2. **Is it reusable?** — would this help in future sessions or projects
3. **Should it become a rule?** — if yes, suggest `/learn` to formalize it

Write learnings to **both** directories:

```bash
mkdir -p .ai/memory/learnings .ai/memory/staging
```

### 3a: Session record → `learnings/`

**Path**: `.ai/memory/learnings/[YYYYMMDD]-[topic].json`

```json
{
  "id": "learning-[unique-id]",
  "topic": "[Topic]",
  "context": "[what prompted this learning]",
  "insight": "[What was learned — specific, actionable]",
  "example": "[Code snippet or scenario demonstrating the learning]",
  "applies_to": ["Situation 1", "Situation 2"],
  "timestamp": "[ISO-8601 timestamp]",
  "last_seen": "[ISO-8601 timestamp]"
}
```

### 3b: Staging entry → `staging/` (feeds `/evolve`)

For each learning that is reusable (not just session-specific), also write a staging entry so it enters the `/evolve` promotion pipeline:

**Path**: `.ai/memory/staging/[YYYYMMDD]-[topic].json`

```json
{
  "id": "learn-[unique-id]",
  "pattern": "[Pattern name — same as topic]",
  "category": "[component | data-flow | error-handling | testing | integration | workflow | security | performance]",
  "source": "[file or feature where discovered]",
  "problem": "[What situation this pattern addresses]",
  "solution": "[The pattern — brief, actionable description]",
  "code_example": "[Optional code snippet]",
  "when_to_use": ["Situation 1", "Situation 2"],
  "when_not_to_use": ["Anti-pattern situation"],
  "proposed_rule": "[Concise rule text if promoting to a rule]",
  "proposed_target": "[skill-name | rules/file.md | memory-only]",
  "first_seen": "[ISO-8601 timestamp]",
  "last_seen": "[ISO-8601 timestamp]",
  "usage_count": 1,
  "failures": 0,
  "confidence": 0.7,
  "promoted": false
}
```

**When to skip staging**: Session-specific learnings that won't generalize (e.g., "had to restart the dev server") should go to `learnings/` only. Only stage patterns that could become permanent rules or skills.

If no learnings worth capturing, skip this step. Not every session produces learnings.

## Step 4: Update Auto-Memory

Review the session for insights that should persist across future conversations. These are distinct from toolkit learnings (code patterns) — auto-memory captures knowledge about the **user, project, and workflow**.

Scan the conversation for:

1. **User insights** — role, preferences, expertise, communication style discovered this session
2. **Feedback/corrections** — times the user redirected your approach (include the *why* so you can judge edge cases later)
3. **Project context** — goals, decisions, constraints, or ongoing work not derivable from code or git history
4. **External references** — URLs, tools, dashboards, or external systems the user pointed you to

For each notable insight, save it to Claude Code's auto-memory using the Write tool (frontmatter format with `name`, `description`, `type` fields). Update `MEMORY.md` index accordingly.

**Skip if**: nothing new was learned about the user or project this session. Not every session produces auto-memory entries — only save what will meaningfully improve future conversations.

## Step 5: Sweep for Uncaptured TODOs

Before closing the session, scan for work items that were mentioned but not tracked:

1. **Conversation review** — look for deferred work, "we should also...", "that's a bug", "let's do that later" mentions that weren't captured
2. **Git diff check** — scan for new `TODO:`, `FIXME:`, `HACK:`, or `XXX:` comments added during this session:

```bash
COMMIT_COUNT=$(git log --oneline --since="4 hours ago" 2>/dev/null | wc -l | tr -d ' ')
[ "$COMMIT_COUNT" -lt 1 ] && COMMIT_COUNT=1
git diff HEAD~${COMMIT_COUNT} -- '*.ts' '*.tsx' '*.js' '*.jsx' 2>/dev/null | grep '^+.*\(TODO\|FIXME\|HACK\|XXX\):' || true
```

3. **Present findings** — for each uncaptured item, show it and offer to add via `/create-todo`:

```markdown
### Uncaptured TODOs Found

1. `TODO: refactor auth middleware` (src/middleware.ts:42) — **Add to TODO.md?**
2. Conversation: "we should also handle the rate limit case" — **Add to TODO.md?**

→ Type numbers to add (e.g., "1, 2"), "all", or "skip"
```

For each approved item, use `/create-todo` with `--source wrap-up` to track provenance.

**After adding items to TODO.md**, auto-commit and push so TODOs sync across machines:

```bash
git add TODO.md
git commit -m "chore: capture session TODOs"
git push
```

If the current branch has already been merged, detect this and offer to commit on the default branch instead:

```bash
# Check if current branch is merged
BRANCH=$(git branch --show-current)
DEFAULT=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||')
if git branch --merged "$DEFAULT" 2>/dev/null | grep -q "$BRANCH"; then
  echo "Branch '$BRANCH' is already merged. Commit TODO.md on '$DEFAULT' instead? (yes/no)"
fi
```

**If nothing found**: Skip silently — don't mention it.

## Step 6: Update Progress Tracking

If a plan is active:

1. Ensure all completed items are marked in the plan file
2. Update Tasks API with current status
3. Note the next item to work on

If no plan, update any informal tracking (progress.txt, session state).

## Step 7: Create Final Checkpoint

Delegate to `/checkpoint` to save the full session state:

```markdown
/checkpoint --task "[session summary]"
```

This ensures the next session can pick up where this one left off.

## Step 8: Report

Output the wrap-up:

```markdown
## Session Wrap-Up

**Date**: [date]
**Branch**: [branch]

### Accomplished
- [Item 1]
- [Item 2]

### Learnings Captured
- [Learning 1] → `.ai/memory/learnings/[file]`
- (none this session)

### Auto-Memory Updated
- [Memory 1] — [type]: [brief description]
- (none this session)

### TODOs Captured
- [TODO 1] → TODO.md (category)
- (none this session)

### Next Session
1. [First thing to do when resuming]
2. [Second thing to do]

### Blockers (if any)
- [Blocker] — needs: [what's required]

---
Session ended. Run `/iterate` next time to auto-restore context.
```

## Arguments

| Argument | Description |
|----------|-------------|
| `--brief` | Short summary, skip learning extraction |
| `--no-checkpoint` | Skip the checkpoint step |
| `--learnings-only` | Only extract learnings, skip summary |

## Related

- `/checkpoint` — called automatically to save session state
- `/learn` — formalize a learning as a permanent rule
- `/iterate` — auto-restores from wrap-up checkpoint
- `.ai/memory/learnings/` — where learnings are stored
- `.ai/memory/checkpoints/` — where checkpoints are stored

## Suggested Next

- `/create-pr` — open PR after session wrap-up
- `/evolve` — promote staged learnings to permanent rules
- `/memory-clean` — archive old memory entries
