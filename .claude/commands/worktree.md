---
suggest_when:
  - signal: session_start
    condition: incomplete_plan
    cooldown: 60
    message: "Starting feature work? `/worktree` creates an isolated branch with deps + env symlinks pre-configured"
  - signal: session_start
    condition: uncommitted_changes
    cooldown: 60
    message: "Working on a new feature? `/worktree` isolates it from main so experiments stay clean"
---

# Worktree

Create an isolated git worktree for a feature branch with dependencies installed and environment files linked.

## Usage

```bash
/worktree feature/auth-flow
/worktree feature/settings-page --cleanup
```

$ARGUMENTS

## Your Task

Set up a new git worktree so the user can develop a feature in isolation without affecting their main working directory.

### Step 1: Get Branch Name

If no branch name was provided in arguments, ask:

"What branch name should I use for the worktree? (e.g., `feature/auth-flow`)"

### Step 1.5: Check for Active Claims

Before creating the worktree, check if any active plans have file claims that might conflict with the intended work.

```bash
# Source overlap detection if available
OVERLAP_LIB=""
if [[ -f ".claude/scripts/lib/overlap-detector.sh" ]]; then
  OVERLAP_LIB=".claude/scripts/lib/overlap-detector.sh"
elif [[ -f "$HOME/.claude/scripts/lib/overlap-detector.sh" ]]; then
  OVERLAP_LIB="$HOME/.claude/scripts/lib/overlap-detector.sh"
fi

if [[ -n "$OVERLAP_LIB" ]]; then
  source "$OVERLAP_LIB"
  ACTIVE=$(get_active_plans 2>/dev/null || true)
fi
```

If active plans exist, inform the user:

```markdown
## Active Plans Detected

The following plans are currently running:

| Plan | Status | Claimed Files |
|------|--------|---------------|
| `auth-feature` | running | 5 files |

Make sure your new worktree doesn't modify files owned by these plans to avoid merge conflicts. Run `/plan-status` in the main repo for details.
```

This is informational, not blocking — the user may be working on completely unrelated files. Continue to Step 2.

### Step 2: Run Worktree Script

Execute the worktree setup script:

```bash
.claude/scripts/worktree.sh "<branch-name>" [flags]
```

Pass through any flags from arguments (e.g., `--cleanup`, `--no-install`).

### Step 3: Confirm and Offer Next Steps

After the script completes successfully, display:

```markdown
## Worktree Ready

**Branch:** `<branch-name>`
**Path:** `<worktree-path>`

### Next Steps

1. **Navigate:** `cd <worktree-path>`
2. **Plan:** Run `/create-plan` to define your feature (recommended)
3. **Work:** Start coding directly if the task is straightforward
4. **Loop:** Run `/ai-loop` for autonomous execution after planning

### Cleanup

When done, merge your branch and remove the worktree:

```bash
git merge <branch-name>
git worktree remove <worktree-path>
git branch -d <branch-name>
```

## Arguments

| Argument       | Description                                |
| -------------- | ------------------------------------------ |
| `<branch>`     | Branch name for the worktree (required)    |
| `--cleanup`    | Remove existing worktree first             |
| `--no-install` | Skip dependency installation               |
| `--no-env`     | Skip .env/.env.local symlinks              |
| `--copy-env`   | Copy env files instead of symlinking       |

## Related Commands

| Command        | Use                                |
| -------------- | ---------------------------------- |
| `/create-plan` | Plan feature work in the worktree  |
| `/iterate`     | Execute plan items                 |
| `/ai-loop`     | Autonomous execution               |
| `/multitask`   | Multiple worktrees + parallel loop |

## Suggested Next

- `/iterate` — execute plan items in the worktree
- `/ai-loop` — autonomous execution within the worktree
- `/multitask` — run multiple worktrees in parallel
