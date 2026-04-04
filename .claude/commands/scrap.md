---
suggest_when:
  - signal: total_tool_calls
    value: 30
    cooldown: 60
    message: "Lots of back-and-forth — `/scrap` to discard and restart with a cleaner approach"
  - signal: edits_since_commit
    value: 25
    cooldown: 60
    message: "Many edits without a clean commit — `/scrap` if the current approach isn't working"
---

# /scrap

Discard current implementation and restart with a better approach.

## Purpose

When an implementation is going sideways or produces mediocre results, `/scrap` provides a clean reset:

1. Soft reset uncommitted changes
2. Analyze what went wrong
3. Re-enter plan mode with lessons learned
4. Design the elegant solution

## Usage

```
/scrap                    # Reset and re-plan current work
/scrap --keep-branch      # Keep on current branch (don't switch)
/scrap --hard             # Hard reset (discard even staged changes)
```

## Workflow

### Step 1: Assess Current State

Before scrapping, understand:

- What was attempted?
- Why isn't it working?
- What did we learn?

```markdown
## Scrap Analysis

**Attempted approach**: [What we tried]
**Why it failed**: [Root cause]
**Lessons learned**: [What to do differently]
```

### Step 2: Soft Reset

```bash
# Default: soft reset to preserve learning
git stash push -m "scrap: [brief description]"

# Or with --hard flag
git checkout -- .
git clean -fd
```

### Step 3: Re-enter Plan Mode

Automatically switch to plan mode with context:

```markdown
## Re-planning: [Feature Name]

### Previous Attempt Summary
- Approach: [what we tried]
- Failure point: [where it broke down]
- Key insight: [what we now understand]

### New Approach
[Design the elegant solution informed by failure]
```

### Step 4: Create New Plan

Generate a revised plan that:

- Avoids the pitfalls of the first attempt
- Incorporates lessons learned
- Is simpler where the first was complex
- Is more robust where the first was fragile

## Recovery Prompt

The core prompt that drives `/scrap`:

> "Knowing everything you know now, scrap this and implement the elegant solution."

This signals:
- Don't cling to sunk cost
- Use the failed attempt as learning
- Design for simplicity and correctness

## When to Use

| Situation | Use /scrap? |
|-----------|-------------|
| Code is messy but working | No - refactor instead |
| Approach is fundamentally wrong | Yes |
| Spent 30+ min with no progress | Yes |
| Tests failing, unclear why | Maybe - try `/debug` first |
| Feature creep made it complex | Yes |
| "I'd do this differently if starting over" | Yes |

## Do NOT

- Scrap working code just because it's imperfect
- Scrap without capturing lessons learned
- Skip the analysis step (you'll repeat mistakes)
- Use as escape from difficult problems (think first)

## Integration

After `/scrap`, the workflow continues:

```
/scrap → [Analysis] → Plan Mode → /create-plan → /iterate
```

The stashed changes remain available if you need to reference them:

```bash
git stash list    # See scrapped attempts
git stash show -p stash@{0}  # View what was scrapped
```

## Suggested Next

| If... | Run |
|-------|-----|
| Ready to start fresh with a new plan | `/create-plan` — break feature into atomic stories |
| Want to debug the original approach instead | `/debug` — hypothesis-driven debugging |
